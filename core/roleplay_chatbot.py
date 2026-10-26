"""Scene-only RolePlay conversation orchestration."""

from __future__ import annotations

import json
import logging
import re
import warnings
from time import perf_counter

from config import (
    KNOWLEDGE_CHUNK_MAX_CHARS,
    KNOWLEDGE_CHUNK_OVERLAP_CHARS,
    KNOWLEDGE_RETRIEVAL_LIMIT,
    KNOWLEDGE_RETRIEVAL_MIN_SCORE,
    ROLEPLAY_MAX_CONTEXT_MESSAGES,
    ROLEPLAY_MEMORY_ENABLED,
    ROLEPLAY_SCENE_ONLY_TOP_K,
    ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS,
    ROLEPLAY_SCENE_RETRIEVER_MODE,
    ROLEPLAY_SCENE_RERANKER_MODEL_PATH,
    ROLEPLAY_SCENE_RERANK_CANDIDATES,
    ROLEPLAY_TIMING,
    VISION_MODEL,
)
from knowledge.loader import KnowledgeLoadError, load_documents
from knowledge.chunker import chunk_documents
from knowledge.retriever import RetrievedKnowledge, retrieve_indexed as retrieve_knowledge_indexed
from llm.client import call
from memory.embedder import Embedder
from memory.local_embedder import get_local_embedder
from roleplay.evidence.loader import load_evidence
from roleplay.evidence.interaction_retriever import interaction_query, rank_all_scenes
from roleplay.evidence.interaction_trace import load_trace_documents
from roleplay.evidence.qwen_reranker import QwenSceneReranker
from roleplay.evidence.relationship_pre_retrieval import rescore_relationship_candidates
from roleplay.evidence.retriever import RetrievedSceneCard, retrieve_indexed
from roleplay.session_manager import DEFAULT_SESSION_KEY, append_turn, get_history, get_session, set_initial_background_from_narration
from roleplay.narration import background_prompt, model_input
from roleplay.visual_scene import scene_prompt
from roleplay.memory.retriever import retrieve_context as retrieve_memory_context
from roleplay.memory.service import schedule_auto_update
from roleplay.sticker_messages import RoleplayReply
from roleplay.sticker_llm_selector import (
    SceneDialogueExcerpt,
    select_sticker_for_text,
    select_stickers_for_texts,
)
from roles.prompt_builder import build_scene_only_prompt_parts
from roles.registry import get_role
from roles.stickers.registry import StickerRegistry
from roles.stickers.schema import AFFECT_FAMILIES, StickerDefinition

_scene_embedder: Embedder | None = None
LOGGER = logging.getLogger(__name__)
_RELATIONSHIP_SCENE_POOL = 100

def _relationship_ranked_scenes(
    candidates: list[RetrievedSceneCard], role_id: str, session_id: str | None,
    *, limit: int, relationship_level: float | None = None,
) -> list[RetrievedSceneCard]:
    """Apply relationship scoring before cosine Top-K or Qwen reranking."""
    level = relationship_level if relationship_level is not None else get_session(role_id, session_id)["relationship_level"]
    scored = rescore_relationship_candidates(
        candidates, relationship_level=level, lambda_floor=0.10,
        beta_pos=0.07, beta_neg=0.03, activation_start=0.50,
    )
    return [RetrievedSceneCard(item.card, item.pre_retrieval_score) for item in scored[:limit]]


def _get_scene_embedder() -> Embedder:
    """Reuse the deployed local embedder across all Roleplay retrieval paths."""
    global _scene_embedder
    if _scene_embedder is None:
        _scene_embedder = get_local_embedder()
    return _scene_embedder


def _retrieve_world_references(message: str, profile) -> list[RetrievedKnowledge]:
    """Retrieve role-bound world facts without mixing them into scene evidence.

    An absent or invalid local lore base leaves profile and scene-card roleplay
    usable, just like a role without any scene cards.
    """
    base_id = profile.roleplay.knowledge_base_id
    if base_id is None:
        return []
    try:
        documents = load_documents(base_id)
    except KnowledgeLoadError as error:
        warnings.warn(
            f"Roleplay knowledge base '{base_id}' is unavailable: {error}",
            RuntimeWarning,
            stacklevel=2,
        )
        return []
    documents = chunk_documents(documents, max_chars=KNOWLEDGE_CHUNK_MAX_CHARS, overlap_chars=KNOWLEDGE_CHUNK_OVERLAP_CHARS)
    if not documents:
        return []
    return retrieve_knowledge_indexed(
        base_id,
        message,
        documents,
        embedder=_get_scene_embedder(),
        limit=KNOWLEDGE_RETRIEVAL_LIMIT,
        min_score=KNOWLEDGE_RETRIEVAL_MIN_SCORE,
    )


def chat(message: str, role_id: str) -> str:
    """Return the visible text for existing text-only Roleplay callers."""
    return chat_structured(message, role_id).text


def chat_structured(message: str, role_id: str, *, session_id: str | None = None, image_data_url: str | None = None, message_kind: str = "dialogue") -> RoleplayReply:
    """Legacy-compatible single value view of a possibly split roleplay reply."""
    replies = chat_structured_many(message, role_id, session_id=session_id, image_data_url=image_data_url, message_kind=message_kind)
    if len(replies) == 1:
        return replies[0]
    return RoleplayReply(text="\n".join(reply.text for reply in replies), sticker_id=None)


def chat_structured_many(message: str, role_id: str, *, session_id: str | None = None, image_data_url: str | None = None, message_kind: str = "dialogue") -> tuple[RoleplayReply, ...]:
    return chat_structured_many_with_sources(message, role_id, session_id=session_id, image_data_url=image_data_url, message_kind=message_kind)[0]


def _current_user_input(text: str, image_data_url: str | None) -> dict[str, object]:
    """Build the only multimodal item in a roleplay generation request.

    The active provider receives the image in the current user message only.
    Historical turns remain text-only by design.
    """
    if not image_data_url:
        return {"role": "user", "content": text}
    return {
        "role": "user",
        "content": [
            {"type": "input_text", "text": text},
            {"type": "input_image", "image_url": image_data_url, "detail": "auto"},
        ],
    }


def generate_reminder_replies(role_id: str, reminder: str) -> tuple[RoleplayReply, ...]:
    """Generate a short in-character reminder without creating a user turn."""
    cleaned_reminder = reminder.strip()
    if not cleaned_reminder:
        raise ValueError("reminder requires text")
    profile = get_role(role_id)
    session = get_session(role_id)
    stable_prompt, _ = build_scene_only_prompt_parts(
        profile, [], relationship_level=session["relationship_level"],
    )
    history = get_history(role_id)[-ROLEPLAY_MAX_CONTEXT_MESSAGES:]
    messages = [{"role": "system", "content": stable_prompt}]
    if session.get("background"):
        messages.append({"role": "system", "content": background_prompt(session["background"])})
    if session.get("visual_scene_id"):
        messages.append({"role": "system", "content": scene_prompt(session["visual_scene_id"])})
    messages.extend(
        {"role": item["role"], "content": model_input(item["content"]["text"], item.get("message_kind", "dialogue"))}
        for item in history if item["content"]["text"].strip()
    )
    messages.append({"role": "user", "content": (
        "[系统事件：定时提醒已到]\n"
        f"提醒事项：{cleaned_reminder}\n"
        "这不是老师新发来的消息。请主动给老师发送一条简短的、符合角色的提醒；"
        "要让老师能清楚知道该做什么。只写一条回复，不要解释这个系统事件。"
    )})
    call_options = {
        "reasoning_effort": "none",
        "response_schema": _scene_only_response_schema(1),
        "max_output_tokens": ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS,
        "usage_label": "roleplay_generator",
    }
    _, texts, affects = _generate_scene_only_with_retry(messages, call_options, 1)
    if not texts:
        raise RuntimeError("模型未返回可显示的提醒内容。")
    text = _normalize_role_name(role_id, texts[0])
    affect = affects[0] if affects else None
    try:
        stickers = StickerRegistry.from_directory().list_available(profile.sticker_pack)
        sticker_id = select_sticker_for_text(
            user_text=f"定时提醒：{cleaned_reminder}", reply_text=text,
            stickers=stickers, model_call=call,
            relationship_level=session["relationship_level"],
            affect_family=affect["family"] if affect else None,
            visible_affect=affect["visible"] if affect else None,
        )
    except Exception:
        LOGGER.warning("Reminder sticker selection failed for role=%s", role_id)
        sticker_id = None
    return (RoleplayReply(text=text, sticker_id=sticker_id),)


def _chat_scene_only(
    message: str,
    role_id: str,
    *,
    session_id: str | None = None,
    image_data_url: str | None = None,
    message_kind: str = "dialogue",
) -> tuple[tuple[RoleplayReply, ...], list[RetrievedKnowledge]]:
    """A reversible generator baseline with Scene RAG, memory, and lore."""
    started_at = perf_counter()
    profile = get_role(role_id)
    user_text = message.strip()
    if not user_text and not image_data_url:
        raise ValueError("roleplay message requires text or image")
    user_text = user_text or "（发送了一张图片）"
    session_record = get_session(role_id, session_id)
    relationship_level = session_record["relationship_level"]
    session_background = session_record.get("background", "")
    visual_scene_id = session_record.get("visual_scene_id", "")
    history = get_history(role_id, session_id)[-ROLEPLAY_MAX_CONTEXT_MESSAGES:]
    # Keep the existing transcript for continuity, but expose only visible text.
    text_history = [
        {"role": item["role"], "content": model_input(item["content"]["text"], item.get("message_kind", "dialogue"))}
        for item in history if item["content"]["text"].strip()
    ]
    checkpoint = perf_counter()
    setup_seconds = checkpoint - started_at
    try:
        cards = load_evidence(role_id)
        scenes = []
        if cards and ROLEPLAY_SCENE_RETRIEVER_MODE == "qwen":
            try:
                recalled = retrieve_indexed(
                    role_id, user_text, cards,
                    embedder=_get_scene_embedder(),
                    limit=min(_RELATIONSHIP_SCENE_POOL, len(cards)),
                    min_score=-1.0,
                )
                recalled = _relationship_ranked_scenes(
                    recalled, role_id, session_id, limit=ROLEPLAY_SCENE_RERANK_CANDIDATES,
                    relationship_level=relationship_level,
                )
                query = interaction_query(
                    history, user_text,
                    character_name=profile.display_name,
                    user_role=profile.roleplay.user_role or "用户",
                )
                scenes = rank_all_scenes(
                    [item.card for item in recalled], query,
                    scorer=QwenSceneReranker(ROLEPLAY_SCENE_RERANKER_MODEL_PATH),
                    limit=ROLEPLAY_SCENE_ONLY_TOP_K,
                    documents_by_id=load_trace_documents(role_id, cards),
                )
            except Exception:
                LOGGER.warning("Qwen scene ranking failed for role=%s; falling back to cosine", role_id)
                dense = retrieve_indexed(
                    role_id, user_text, cards,
                    embedder=_get_scene_embedder(),
                    limit=min(_RELATIONSHIP_SCENE_POOL, len(cards)),
                    min_score=-1.0,
                )
                scenes = _relationship_ranked_scenes(
                    dense, role_id, session_id, limit=ROLEPLAY_SCENE_ONLY_TOP_K,
                    relationship_level=relationship_level,
                )
        elif cards:
            dense = retrieve_indexed(
                role_id, user_text, cards,
                embedder=_get_scene_embedder(),
                limit=min(_RELATIONSHIP_SCENE_POOL, len(cards)),
                min_score=-1.0,
            )
            scenes = _relationship_ranked_scenes(
                dense, role_id, session_id, limit=ROLEPLAY_SCENE_ONLY_TOP_K,
                relationship_level=relationship_level,
            )
    except Exception:
        LOGGER.warning("Scene-only retrieval failed for role=%s; continuing without scenes", role_id)
        scenes = []
    scene_retrieval_seconds = perf_counter() - checkpoint
    checkpoint = perf_counter()
    memory_context = None
    if ROLEPLAY_MEMORY_ENABLED and (session_id or DEFAULT_SESSION_KEY) == DEFAULT_SESSION_KEY:
        try:
            memory_context = retrieve_memory_context(role_id, user_text)
        except Exception:
            LOGGER.warning("Scene-only memory retrieval failed for role=%s; continuing without memory", role_id)
    memory_retrieval_seconds = perf_counter() - checkpoint
    checkpoint = perf_counter()
    try:
        world_references = _retrieve_world_references(user_text, profile)
    except Exception:
        LOGGER.warning("Scene-only knowledge retrieval failed for role=%s; continuing without lore", role_id)
        world_references = []
    knowledge_retrieval_seconds = perf_counter() - checkpoint
    checkpoint = perf_counter()
    stable_prompt, retrieved_context = build_scene_only_prompt_parts(
        profile, scenes, memory_context=memory_context,
        retrieved_knowledge=world_references,
        relationship_level=relationship_level,
    )
    messages = [{"role": "system", "content": stable_prompt}, *text_history]
    if session_background:
        messages.insert(1, {"role": "system", "content": background_prompt(session_background)})
    if visual_scene_id:
        messages.insert(2 if session_background else 1, {"role": "system", "content": scene_prompt(visual_scene_id)})
    if retrieved_context:
        messages.append({"role": "system", "content": retrieved_context})
    messages.append(_current_user_input(model_input(user_text, message_kind), image_data_url))
    split = profile.roleplay.message_split
    call_options = {"model": VISION_MODEL if image_data_url else None, "reasoning_effort": "none", "max_output_tokens": ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS, "usage_label": "roleplay_generator"}
    if split.enabled:
        call_options["response_schema"] = _scene_only_response_schema(split.max_messages)
    prompt_seconds = perf_counter() - checkpoint
    checkpoint = perf_counter()
    raw, reply_texts, affects = _generate_scene_only_with_retry(
        messages, call_options, split.max_messages if split.enabled else 1,
    )
    generator_seconds = perf_counter() - checkpoint
    checkpoint = perf_counter()
    reply_texts = tuple(_normalize_role_name(role_id, text) for text in reply_texts)
    if not reply_texts:
        raise RuntimeError("模型未返回可显示的文本内容。")
    if len(affects) != len(reply_texts):
        LOGGER.warning(
            "Roleplay affect count mismatch for role=%s: texts=%d affects=%d",
            role_id, len(reply_texts), len(affects),
        )
        affects = (None,) * len(reply_texts)
    affect_families = tuple(affect["family"] if affect else None for affect in affects)
    visible_affects = tuple(affect["visible"] if affect else None for affect in affects)
    missing_affect_bubbles = [
        index for index, affect in enumerate(affects, start=1) if affect is None
    ]
    if split.enabled and missing_affect_bubbles:
        LOGGER.warning(
            "Roleplay affect missing for bubbles=%s role=%s; family gate skipped for them; raw=%s",
            missing_affect_bubbles, role_id, raw[:300],
        )
    for index, (family, visible) in enumerate(zip(affect_families, visible_affects), start=1):
        if family:
            LOGGER.info(
                "Roleplay affect role=%s bubble=%d family=%s visible=%s",
                role_id, index, family, visible,
            )
    try:
        stickers = StickerRegistry.from_directory().list_available(profile.sticker_pack)
    except Exception:
        LOGGER.warning("Scene-only sticker loading failed for role=%s; keeping text", role_id)
        stickers = []
    excerpt_cache: dict[str | None, tuple[SceneDialogueExcerpt, ...]] = {}

    def excerpts_for(family: str | None) -> tuple[SceneDialogueExcerpt, ...]:
        if family not in excerpt_cache:
            excerpt_cache[family] = _scene_dialogue_excerpts(
                scenes, stickers, profile=profile, affect_family=family, limit=4,
            )
        return excerpt_cache[family]

    selector_user_text = model_input(user_text, message_kind)
    groups: dict[str | None, list[int]] = {}
    for index, family in enumerate(affect_families):
        groups.setdefault(family, []).append(index)
    selected: list[str | None] = [None] * len(reply_texts)
    for family, indices in groups.items():
        group_texts = [reply_texts[index] for index in indices]
        group_visibles = [visible_affects[index] for index in indices]
        try:
            if len(indices) == 1:
                selected[indices[0]] = select_sticker_for_text(
                    user_text=selector_user_text,
                    reply_text=group_texts[0],
                    stickers=stickers, model_call=call,
                    relationship_level=relationship_level,
                    affect_family=family,
                    visible_affect=group_visibles[0],
                    scene_dialogue_excerpts=excerpts_for(family),
                )
            else:
                group_sticker_ids = select_stickers_for_texts(
                    user_text=selector_user_text,
                    reply_texts=group_texts,
                    stickers=stickers, model_call=call,
                    relationship_level=relationship_level,
                    affect_family=family,
                    visible_affects=group_visibles,
                    scene_dialogue_excerpts=excerpts_for(family),
                )
                for index, sticker_id in zip(indices, group_sticker_ids):
                    selected[index] = sticker_id
        except Exception:
            LOGGER.warning(
                "Scene-only sticker selection failed for role=%s family=%s indices=%s",
                role_id, family, indices,
            )
    sticker_ids = tuple(selected)
    if len(reply_texts) > 1 and not any(sticker_ids):
        LOGGER.warning(
            "Multi-bubble sticker selection returned no stickers for role=%s affects=%s",
            role_id, affect_families,
        )
    replies = [
        RoleplayReply(text=reply_text, sticker_id=sticker_id)
        for reply_text, sticker_id in zip(reply_texts, sticker_ids)
    ]
    sticker_seconds = perf_counter() - checkpoint
    checkpoint = perf_counter()
    append_turn(
        role_id, user_text,
        [{"text": reply.text, "sticker_id": reply.sticker_id} for reply in replies],
        session_id=session_id, message_kind=message_kind,
    )
    if ROLEPLAY_MEMORY_ENABLED and (session_id or DEFAULT_SESSION_KEY) == DEFAULT_SESSION_KEY:
        try:
            schedule_auto_update(role_id)
        except Exception:
            LOGGER.warning("Scene-only memory update scheduling failed for role=%s", role_id)
    if ROLEPLAY_TIMING:
        print(
            "[roleplay scene-only timing] "
            f"role={role_id} affects={list(affect_families)} setup={setup_seconds:.3f}s "
            f"scene_retrieval={scene_retrieval_seconds:.3f}s "
            f"memory_retrieval={memory_retrieval_seconds:.3f}s "
            f"knowledge_retrieval={knowledge_retrieval_seconds:.3f}s "
            f"prompt={prompt_seconds:.3f}s generator={generator_seconds:.3f}s "
            f"sticker={sticker_seconds:.3f}s "
            f"stickers={[reply.sticker_id for reply in replies]} "
            f"persistence={perf_counter() - checkpoint:.3f}s "
            f"total={perf_counter() - started_at:.3f}s bubbles={len(replies)}"
        )
    return tuple(replies), world_references


def _scene_dialogue_excerpts(
    scenes: list[RetrievedSceneCard],
    stickers: list[StickerDefinition],
    *,
    profile,
    affect_family: str | None = None,
    limit: int = 4,
) -> tuple[SceneDialogueExcerpt, ...]:
    """Keep a few in-context Scene reactions for the sticker selector.

    The Excerpts are demonstrations of how the character reacted in similar
    situations, not facts about the current turn.  They are deliberately short:
    the selector already has the current reply and the family constraint.
    """
    family_by_id = {
        item.id: item.affect.primary for item in stickers if item.affect is not None
    }
    available_ids = {item.id for item in stickers}
    excerpts: list[SceneDialogueExcerpt] = []
    seen: set[tuple[str, str]] = set()
    for item in scenes:
        card = item.card
        raw_lines = [line for line in card.lines if line.source == "raw"]
        for index, line in enumerate(raw_lines):
            if line.sticker_id is None or line.sticker_id not in available_ids:
                continue
            family = family_by_id.get(line.sticker_id)
            if affect_family and family is not None and family != affect_family:
                continue
            key = (card.id, line.sticker_id)
            if key in seen:
                continue
            seen.add(key)
            start = max(0, index - 1)
            end = min(len(raw_lines), index + 2)
            excerpt_lines = tuple(
                f"{profile.display_name if context_line.speaker == profile.id else context_line.speaker}："
                f"{context_line.text}"
                for context_line in raw_lines[start:end]
            )
            excerpts.append(
                SceneDialogueExcerpt(
                    card.id, card.scene, line.sticker_id, excerpt_lines,
                    index - start,
                )
            )
            if len(excerpts) >= limit:
                return tuple(excerpts)
    return tuple(excerpts)


def _scene_only_response_schema(max_messages: int) -> dict:
    """Keep the Generator output limited to visible text plus per-bubble affect."""
    return {
        "type": "object",
        "properties": {
            "replies": {
                "type": "array", "minItems": 1, "maxItems": max_messages,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "minLength": 1},
                        "affect": {
                            "type": "object",
                            "properties": {
                                "family": {"type": "string", "enum": list(AFFECT_FAMILIES)},
                                "visible": {"type": "string", "minLength": 1, "maxLength": 120},
                            },
                            "required": ["family", "visible"],
                            "additionalProperties": False,
                        },
                    },
                    "required": ["text", "affect"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["replies"],
        "additionalProperties": False,
    }


def _scene_only_reply_texts(raw: str, max_messages: int) -> tuple[str, ...]:
    """Read a bubble batch while accepting plain text from older providers."""
    return _scene_only_parse(raw, max_messages)[0]


def _scene_only_parse(
    raw: str, max_messages: int,
) -> tuple[tuple[str, ...], tuple[dict[str, str] | None, ...]]:
    """Read visible bubbles and each bubble's optional private affect."""
    data = _scene_only_json_object(raw)
    root_affect = _scene_only_affect(data)  # legacy/turn-level fallback
    return _scene_only_fit_bubble_items(
        _scene_only_bubble_items(data, raw, root_affect), max_messages,
    )


def _scene_only_json_object(raw: str) -> object:
    """Decode a JSON object, including one wrapped in a Markdown fence."""
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        data = None
    if data is None and isinstance(raw, str):
        decoder = json.JSONDecoder()
        for index, character in enumerate(raw):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(raw[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and (
                "replies" in candidate or "text" in candidate
            ):
                data = candidate
                break
    return data


def _scene_only_bubble_items(
    data: object, raw: str, root_affect: dict[str, str] | None,
) -> list[tuple[str, dict[str, str] | None]]:
    """Extract visible bubble text and its own private affect from provider output."""
    items: list[tuple[str, dict[str, str] | None]] = []
    if isinstance(data, dict) and isinstance(data.get("replies"), list):
        for item in data["replies"]:
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            affect = _normalize_affect_value(item.get("affect")) or root_affect
            items.append((text.strip(), affect))
        return items
    if isinstance(data, dict) and isinstance(data.get("text"), str):
        return [(data["text"].strip(), root_affect)]
    if isinstance(data, str):
        return [(data.strip(), root_affect)]
    if isinstance(raw, str) and raw.strip():
        return [(raw.strip(), root_affect)]
    return []


def _scene_only_fit_bubble_items(
    items: list[tuple[str, dict[str, str] | None]], max_messages: int,
) -> tuple[tuple[str, ...], tuple[dict[str, str] | None, ...]]:
    """Split one long bubble and cap overflow while keeping affects aligned."""
    items = [(text, affect) for text, affect in items if text]
    if len(items) == 1 and max_messages > 1:
        text, affect = items[0]
        beats = _scene_only_split_visible_beats(text)
        if len(beats) > 1:
            items = [(beat, affect) for beat in beats]
    if len(items) > max_messages:
        overflow = items[max_messages - 1:]
        items = [
            *items[:max_messages - 1],
            ("\n".join(text for text, _ in overflow), overflow[-1][1]),
        ]
    return (
        tuple(text for text, _ in items),
        tuple(affect for _, affect in items),
    )


def _scene_only_affect(data: object) -> dict[str, str] | None:
    """Read a legacy/turn-level affect object from a decoded response."""
    if not isinstance(data, dict):
        return None
    return _normalize_affect_value(data.get("affect"))


def _normalize_affect_value(value: object) -> dict[str, str] | None:
    """Validate one private affect label without making it a generation input."""
    if not isinstance(value, dict):
        return None
    family = value.get("family")
    if family not in AFFECT_FAMILIES:
        LOGGER.warning("Invalid roleplay affect family=%r; continuing without family gate", family)
        return None
    visible = value.get("visible")
    visible = visible.strip()[:120] if isinstance(visible, str) else ""
    return {"family": family, "visible": visible}


def _generate_scene_only_with_retry(
    messages: list[dict], call_options: dict, max_messages: int,
) -> tuple[str, tuple[str, ...], tuple[dict[str, str] | None, ...]]:
    """Generate visible text, retrying once when the model returns none.

    A provider can return an empty completion or an empty ``replies`` array
    when hidden reasoning consumes the completion budget.  The retry increases
    the budget and adds an explicit reminder before the current user message;
    it does not add a second generation stage or change the persona.
    """
    def attempt(
        call_messages: list[dict], options: dict,
    ) -> tuple[str, tuple[str, ...], tuple[dict[str, str] | None, ...]]:
        try:
            raw = call(call_messages, **options)
        except RuntimeError as error:
            if "模型未返回可显示的文本内容" not in str(error):
                raise
            raw = ""
        texts, affects = _scene_only_parse(raw, max_messages)
        return raw, texts, affects

    raw, texts, affects = attempt(messages, call_options)
    if texts:
        return raw, texts, affects

    LOGGER.warning(
        "Roleplay generator returned no visible text; retrying once; raw=%s",
        raw[:500],
    )
    retry_options = dict(call_options)
    base = retry_options.get("max_output_tokens") or ROLEPLAY_GENERATOR_MAX_OUTPUT_TOKENS
    retry_options["max_output_tokens"] = max(int(base) * 2, 2048)
    retry_messages = [
        *messages[:-1],
        {
            "role": "system",
            "content": (
                "上一次输出没有可显示的 text。请重新回答，必须至少返回一条 "
                "replies[].text；每条 reply 都要带自己的 affect，"
                "不要返回空数组、空文本或只返回 affect。"
            ),
        },
        messages[-1],
    ]
    raw, texts, affects = attempt(retry_messages, retry_options)
    if texts:
        return raw, texts, affects
    LOGGER.warning("Roleplay generator retry returned no visible text; raw=%s", raw[:500])
    raise RuntimeError("模型未返回可显示的文本内容。")


def _scene_only_split_visible_beats(text: str) -> tuple[str, ...]:
    """Split newline-formatted action/dialogue beats without rewriting prose."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return (text,)
    action_line = lambda line: bool(re.fullmatch(r"（[^\n]+）", line))
    if not any(action_line(line) for line in lines):
        paragraphs = tuple(part.strip() for part in re.split(r"\n\s*\n", text) if part.strip())
        return paragraphs if len(paragraphs) > 1 else (text,)
    bubbles: list[str] = []
    current: list[str] = []
    has_dialogue = False
    for line in lines:
        is_action = action_line(line)
        if current and (is_action or has_dialogue):
            bubbles.append("\n".join(current))
            current = []
            has_dialogue = False
        current.append(line)
        if not is_action:
            has_dialogue = True
    if current:
        bubbles.append("\n".join(current))
    return tuple(bubbles)


def chat_structured_many_with_sources(
    message: str,
    role_id: str,
    *,
    session_id: str | None = None,
    image_data_url: str | None = None,
    message_kind: str = "dialogue",
) -> tuple[tuple[RoleplayReply, ...], list[RetrievedKnowledge]]:
    """Persist one Scene-only turn and return its visible reply bubbles."""
    if message_kind not in {"dialogue", "narration"}:
        raise ValueError("message_kind must be dialogue or narration")
    if message_kind == "narration":
        if image_data_url:
            raise ValueError("narration cannot include an image")
        set_initial_background_from_narration(role_id, message, session_id)
    return _chat_scene_only(
        message, role_id, session_id=session_id,
        image_data_url=image_data_url, message_kind=message_kind,
    )


def _normalize_role_name(role_id: str, text: str) -> str:
    """Correct a known generated name typo without changing user messages."""
    return text.replace("柯伊", "凯伊") if role_id == "tendou_kei" else text
