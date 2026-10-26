"""Candidate-based LLM selection for finite roleplay sticker packs."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from typing import Callable, Sequence

from roles.stickers.schema import AFFECT_FAMILIES, StickerDefinition


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SceneStickerReference:
    """An authored sticker association on a retrieved Scene, never a mandate."""

    scene_id: str
    scene_summary: str
    sticker_id: str
    line_text: str | None = None


@dataclass(frozen=True)
class SceneDialogueExcerpt:
    """A short, in-context reaction example from a retrieved Scene."""

    scene_id: str
    scene_summary: str
    sticker_id: str
    lines: tuple[str, ...]
    sticker_line_index: int = 0


def _family_candidates(
    stickers: Sequence[StickerDefinition], affect_family: str | None,
) -> tuple[tuple[StickerDefinition, ...], bool]:
    """Return candidates for one family and whether the gate actually applied."""
    candidates = tuple(stickers)
    if not affect_family:
        return candidates, False
    if affect_family not in AFFECT_FAMILIES:
        LOGGER.warning("Unknown affect family=%s; disabling family gate", affect_family)
        return candidates, False
    tagged = tuple(item for item in candidates if item.affect is not None)
    if not tagged:
        # Legacy packs have no affect metadata.  Keep them usable instead of
        # silently returning no sticker for every turn.
        LOGGER.info("Sticker pack has no affect metadata; ignoring family=%s", affect_family)
        return candidates, False
    matched = tuple(item for item in tagged if item.affect.primary == affect_family)
    if not matched:
        LOGGER.warning("No stickers for affect family=%s; refusing to cross families", affect_family)
    return matched, True


def _call_selector(
    model_call: Callable,
    messages: list[dict[str, str]],
    schema: dict,
    max_output_tokens: int,
) -> str:
    """Call the selector, retrying once when the provider returns no visible text.

    Some providers spend the completion budget on hidden reasoning before
    emitting the small JSON object.  A 128/192-token budget can therefore end
    with an empty ``content`` while the request itself succeeded.  Retrying with
    a larger budget preserves the family gate instead of dropping the sticker.
    """
    try:
        return model_call(
            messages, reasoning_effort="none", response_schema=schema,
            max_output_tokens=max_output_tokens, usage_label="roleplay_sticker",
        )
    except RuntimeError as error:
        LOGGER.warning(
            "Sticker selection returned no text (%s); retrying with 1024 output tokens",
            str(error)[:120],
        )
        return model_call(
            messages, reasoning_effort="none", response_schema=schema,
            max_output_tokens=1024, usage_label="roleplay_sticker",
        )


def select_sticker_for_text(
    *,
    user_text: str,
    reply_text: str,
    stickers: Sequence[StickerDefinition],
    model_call: Callable,
    scene_sticker_references: Sequence[SceneStickerReference] = (),
    relationship_level: float | None = None,
    affect_family: str | None = None,
    visible_affect: str | None = None,
    scene_dialogue_excerpts: Sequence[SceneDialogueExcerpt] = (),
) -> str | None:
    """Choose one available sticker after unconstrained text generation."""
    if not stickers:
        return None
    candidates, gated = _family_candidates(stickers, affect_family)
    if not candidates:
        return None
    candidate_ids = {item.id for item in candidates}
    prompt_lines = _selection_prompt_lines(
        user_text=user_text, stickers=candidates,
        scene_sticker_references=scene_sticker_references,
        relationship_level=relationship_level,
        affect_family=affect_family if gated else None,
        visible_affect=visible_affect,
        scene_dialogue_excerpts=scene_dialogue_excerpts,
    )
    prompt_lines.append(f"角色最终回复：{reply_text}")
    prompt = "\n".join(prompt_lines)
    schema = {
        "type": "object",
        "properties": {"sticker_id": {"type": ["string", "null"], "enum": [item.id for item in candidates] + [None]}},
        "required": ["sticker_id"],
        "additionalProperties": False,
    }
    try:
        raw = _call_selector(
            model_call, _selection_messages(prompt), schema, max_output_tokens=512,
        )
    except Exception as error:
        LOGGER.warning(
            "Sticker selection failed: %s: %s",
            type(error).__name__, str(error)[:200],
        )
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.warning("Sticker selection returned invalid JSON: %s", raw[:200])
        return None
    selected = value.get("sticker_id") if isinstance(value, dict) else None
    if isinstance(selected, str) and selected not in candidate_ids:
        LOGGER.warning(
            "Sticker selection returned id outside family=%s: %s",
            affect_family if gated else None, selected,
        )
        return None
    selected = selected if isinstance(selected, str) else None
    LOGGER.info(
        "Sticker selection family=%s candidates=%d selected=%s",
        affect_family if gated else None, len(candidates), selected,
    )
    return selected


def select_stickers_for_texts(
    *,
    user_text: str,
    reply_texts: Sequence[str],
    stickers: Sequence[StickerDefinition],
    model_call: Callable,
    scene_sticker_references: Sequence[SceneStickerReference] = (),
    relationship_level: float | None = None,
    affect_family: str | None = None,
    visible_affect: str | None = None,
    visible_affects: Sequence[str | None] = (),
    scene_dialogue_excerpts: Sequence[SceneDialogueExcerpt] = (),
) -> tuple[str | None, ...]:
    """Select all bubble stickers in one model request to conserve provider RPM."""
    if not reply_texts:
        return ()
    if not stickers:
        return (None,) * len(reply_texts)
    if len(reply_texts) == 1:
        return (select_sticker_for_text(
            user_text=user_text, reply_text=reply_texts[0], stickers=stickers,
            model_call=model_call, scene_sticker_references=scene_sticker_references,
            relationship_level=relationship_level,
            affect_family=affect_family,
            visible_affect=visible_affects[0] if visible_affects else visible_affect,
            scene_dialogue_excerpts=scene_dialogue_excerpts,
        ),)
    candidates, gated = _family_candidates(stickers, affect_family)
    if not candidates:
        return (None,) * len(reply_texts)
    candidate_ids = {item.id for item in candidates}
    prompt_lines = _selection_prompt_lines(
        user_text=user_text, stickers=candidates,
        scene_sticker_references=scene_sticker_references,
        relationship_level=relationship_level,
        affect_family=affect_family if gated else None,
        visible_affect=visible_affect if not visible_affects else None,
        scene_dialogue_excerpts=scene_dialogue_excerpts,
    )
    prompt_lines.append(
        "以下是本轮中需要为本组选图的多个气泡（可能只是同一轮的一部分）。"
        "按序为每条气泡独立选一张贴图或 null；"
        "不能把另一条气泡里的表情、动作当作本条气泡的依据。"
    )
    for index, reply in enumerate(reply_texts, start=1):
        prompt_lines.append(f"气泡 {index}：{reply}")
        if index <= len(visible_affects) and visible_affects[index - 1]:
            prompt_lines.append(f"气泡 {index} 的可见反应：{visible_affects[index - 1]}")
    prompt_lines.append(f"返回 sticker_ids 数组，严格包含 {len(reply_texts)} 项，顺序与气泡一致。")
    schema = {
        "type": "object",
        "properties": {"sticker_ids": {
            "type": "array", "minItems": len(reply_texts), "maxItems": len(reply_texts),
            "items": {"type": ["string", "null"], "enum": [item.id for item in candidates] + [None]},
        }},
        "required": ["sticker_ids"], "additionalProperties": False,
    }
    try:
        raw = _call_selector(
            model_call, _selection_messages("\n".join(prompt_lines)), schema,
            max_output_tokens=max(512, 64 * len(reply_texts)),
        )
    except Exception as error:
        LOGGER.warning(
            "Multi-bubble sticker selection failed: %s: %s",
            type(error).__name__, str(error)[:200],
        )
        return (None,) * len(reply_texts)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        LOGGER.warning("Multi-bubble sticker selection returned invalid JSON: %s", raw[:200])
        return (None,) * len(reply_texts)
    selected = value.get("sticker_ids") if isinstance(value, dict) else None
    if not isinstance(selected, list) or len(selected) != len(reply_texts):
        LOGGER.warning("Multi-bubble sticker selection returned invalid count: %r", selected)
        return (None,) * len(reply_texts)
    invalid = [
        item for item in selected
        if isinstance(item, str) and item not in candidate_ids
    ]
    if invalid:
        LOGGER.warning(
            "Multi-bubble sticker selection returned ids outside family=%s: %s",
            affect_family if gated else None, invalid,
        )
    result = tuple(
        item if isinstance(item, str) and item in candidate_ids else None
        for item in selected
    )
    if not any(result):
        LOGGER.warning(
            "Multi-bubble sticker selection returned all null: %r (family=%s candidates=%d)",
            selected, affect_family if gated else None, len(candidates),
        )
    LOGGER.info(
        "Multi-bubble sticker selection family=%s candidates=%d selected=%s",
        affect_family if gated else None, len(candidates), result,
    )
    return result


def _selection_prompt_lines(
    *, user_text: str, stickers: Sequence[StickerDefinition],
    scene_sticker_references: Sequence[SceneStickerReference],
    relationship_level: float | None,
    affect_family: str | None = None,
    visible_affect: str | None = None,
    scene_dialogue_excerpts: Sequence[SceneDialogueExcerpt] = (),
) -> list[str]:
    candidate_ids = {item.id for item in stickers}
    descriptions = "\n\n".join(
        f"id={item.id}\n{item.selection_text()}" for item in stickers
    )
    scene_reference_lines = []
    seen_references: set[tuple[str, str]] = set()
    for reference in scene_sticker_references:
        key = (reference.scene_id, reference.sticker_id)
        if reference.sticker_id not in candidate_ids or key in seen_references:
            continue
        seen_references.add(key)
        scene_reference_lines.append(
            f"scene_id={reference.scene_id}; scene={reference.scene_summary[:100]}; "
            f"sticker_id={reference.sticker_id}"
            + (f"; 对应台词={reference.line_text[:80]}" if reference.line_text else "")
        )
        if len(scene_reference_lines) >= 20:
            break
    prompt_lines = [
        "你只负责为已经写好的角色回复选择一张合适的贴图，不修改或续写台词。",
        "根据角色回复和本轮可见反应选图，不要把台词中的否认、警告或引用直接当成角色表情。",
        "没有明确合适的贴图时返回 null；不要为了每条消息都有贴图而勉强选择。",
        "只能选择下列贴图 ID 或 null；不得使用贴图描述中的情境创造当前对话事实。",
    ]
    if affect_family:
        prompt_lines.append(
            f"本轮目标情绪类别：{affect_family}。只能从下列同一类别的贴图中选择；不要跨类别。"
            "同一类别内，优先选择能承载当前情绪的最低强度贴图；"
            "只有文本或可见反应明确呈现更强演出时才升级。"
        )
    if visible_affect:
        prompt_lines.append(f"台词中实际呈现的可见反应：{visible_affect}")
        prompt_lines.append("以这条可见反应为主要依据；台词的字面语气只作线索。")
    prompt_lines.append(f"可用贴图：\n{descriptions}")
    if relationship_level is not None and relationship_level > 0.85:
        scope = "在本轮目标情绪类别内，" if affect_family else ""
        prompt_lines.append(
            f"当前会话处于已确认交往的高好感度阶段。{scope}若这条最终回复实际呈现温柔、安心、亲近、"
            "含蓄喜欢或柔和的害羞，优先选择视觉上相符的柔和亲近贴图。"
            "在正常对话中，也尽量使用柔和的贴图。"
            "关系阶段只是同样合适的贴图之间的软偏好：不要把严肃、抗议、拒绝或不适的可见反应改判成甜蜜，"
            "也不要补出回复里没有的强烈脸红、拥抱等表现；有自然匹配时可优先考虑同类别中更柔和的贴图，没有自然匹配时仍返回 null。"
        )
    prompt_lines.append(f"用户本轮消息：{user_text}")
    if scene_dialogue_excerpts:
        prompt_lines.append(
            "相似场景中的实际对话（只作角色反应参考，不是当前事实；不要照搬其中的台词）："
        )
        for excerpt in scene_dialogue_excerpts[:4]:
            marked_lines = [
                (
                    f"{line}  [贴图：{excerpt.sticker_id}]"
                    if line_index == excerpt.sticker_line_index
                    else line
                )
                for line_index, line in enumerate(excerpt.lines)
            ]
            prompt_lines.append(
                "\n".join((f"【{excerpt.scene_summary[:80]}】", *marked_lines))
            )
    elif scene_reference_lines:
        prompt_lines.extend((
            "检索 Scene 曾关联的贴图（仅作可选参考，不代表当前气泡的情绪或事实；不能仅因为 Scene 用过就选，也不能因为场景没有贴图就代表该场景下没产生情绪因此返回null，当前回复不支持时返回 null）：",
            *scene_reference_lines,
        ))
    if affect_family:
        prompt_lines.append(f"再次确认：只能选择 {affect_family} 类别的贴图，或返回 null。")
    return prompt_lines


def _selection_messages(prompt: str) -> list[dict[str, str]]:
    """GLM Chat Completions rejects conversations containing only system messages."""
    return [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "请根据以上角色回复选图，只返回符合指定格式的结果。"},
    ]
