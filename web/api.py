"""JSON API shared by the Momotalk frontend and existing Python chat core.

This module intentionally has no frontend dependency.  The Vue application can
be developed and tested separately while all conversation state remains owned
by the existing Python session managers.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
import re
from typing import Literal
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query
from openai import APIStatusError
from pydantic import BaseModel, Field

from config import APP_TIMEZONE, BASE_URL, DEFAULT_ROLE_ID, MODES, PROJECT_DIR, ROLEPLAY, ROLEPLAY_MEMORY_ENABLED, VISION_MODEL
from knowledge.catalog import get_catalog_entry, list_catalog
from knowledge.loader import KnowledgeLoadError
from knowledge.manage import add_jsonl_document, delete_jsonl_document, rebuild_index
from core.chatbot import chat_with_sources
from core.roleplay_chatbot import chat_structured_many_with_sources
from roleplay.session_manager import clear as clear_roleplay_history
from roleplay.session_manager import get_history as get_roleplay_history
from roleplay.session_manager import get_session as get_roleplay_session
from roleplay.session_manager import get_turns as get_roleplay_turns
from roleplay.session_manager import create_session as create_roleplay_session
from roleplay.session_manager import list_sessions as list_roleplay_sessions
from roleplay.session_manager import set_relationship_level as set_roleplay_relationship_level
from roleplay.session_manager import set_visual_scene as set_roleplay_visual_scene
from roleplay.session_manager import MAX_SESSION_BACKGROUND_CHARS
from roleplay.memory.manager import load as load_roleplay_memory
from roleplay.memory.manager import update_settings as update_roleplay_memory_settings
from roleplay.memory.service import update as update_roleplay_memory
from roleplay.alarms import Alarm, cancel_alarm, create_alarm, delete_alarm_history, list_alarms
from roles.registry import get_role, list_roles
from roles.stickers.loader import resolve_sticker_asset
from roles.stickers.registry import StickerRegistry
from session.manager import clear_history, get_history


router = APIRouter(prefix="/api", tags=["conversation"])
_IMAGE_DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|gif|webp));base64,([A-Za-z0-9+/]+={0,2})$")
_MAX_INLINE_IMAGE_BYTES = 8 * 1024 * 1024


class SendMessageRequest(BaseModel):
    """One user message sent from the Momotalk frontend."""

    mode: str = Field(description="One configured assistant mode.")
    text: str = Field(default="", max_length=20_000)
    role_id: str | None = Field(default=None, description="Required for roleplay mode.")
    session_id: str | None = Field(default=None, description="Optional role-local Roleplay session key.")
    image_data_url: str | None = Field(default=None, description="Optional current-turn image as a data URL.")
    message_kind: Literal["dialogue", "narration"] = "dialogue"


class MessageContent(BaseModel):
    """A frontend-safe message including an optional locally served sticker URL."""

    role: Literal["user", "assistant"]
    text: str
    sticker_id: str | None = None
    sticker_url: str | None = None
    created_at: str | None = None
    message_kind: Literal["dialogue", "narration"] = "dialogue"


class ConversationResponse(BaseModel):
    """All persisted messages belonging to one isolated conversation."""

    mode: str
    role_id: str | None = None
    session_id: str | None = None
    messages: list[MessageContent]
    visual_scene_id: str | None = None
    retrieved_sources: list["RetrievedSource"] = []


class RoleplaySessionContent(BaseModel):
    session_id: str
    record_id: str
    revision: int
    completed_turn_count: int
    background: str = ""
    last_message_at: str | None = None


class CreateRoleplaySessionRequest(BaseModel):
    background: str = Field(default="", max_length=MAX_SESSION_BACKGROUND_CHARS)


class SelectVisualSceneRequest(BaseModel):
    scene_id: str


class VisualSceneContent(BaseModel):
    scene_id: str


class AlarmRequest(BaseModel):
    """One local reminder associated with a roleplay conversation."""

    role_id: str
    text: str = Field(min_length=1, max_length=500)
    due_at: datetime


class AlarmContent(BaseModel):
    id: str
    role_id: str
    text: str
    due_at: str
    status: Literal["pending", "delivered", "cancelled"]
    created_at: str
    delivered_at: str | None = None


class ServerTimeContent(BaseModel):
    timezone: str
    local_time: str
    default_alarm_time: str


class KnowledgeDocumentContent(BaseModel):
    id: str
    title: str
    source: str | None
    tags: list[str]


class KnowledgeBaseContent(BaseModel):
    id: str
    display_name: str
    bound_to: list[str]
    document_count: int
    index_entry_count: int
    status: Literal["ready", "not_built", "invalid"]
    error: str | None = None
    documents: list[KnowledgeDocumentContent]

class KnowledgeDocumentRequest(BaseModel):
    id: str
    title: str = ""
    source: str = ""
    tags: list[str] = []
    text: str


class RetrievedSource(BaseModel):
    id: str
    title: str
    source: str | None = None
    chunk_index: int = 1
    chunk_count: int = 1


class RoleplayMemoryContent(BaseModel):
    id: str
    kind: str
    content: str
    status: str
    importance: float
    pinned: bool
    source_turn_ids: list[str]
    created_at: str
    updated_at: str


class RoleplayMemoryResponse(BaseModel):
    role_id: str
    enabled: bool
    revision: int
    completed_turn_count: int
    memory_checkpoint_turn: int
    pending_turn_count: int
    summary: str
    settings: dict[str, bool | int]
    memories: list[RoleplayMemoryContent]
    last_error: str | None = None
    last_updated_at: str | None = None


class RoleplayMemorySettingsRequest(BaseModel):
    auto_update_enabled: bool | None = None
    update_every_turns: int | None = Field(default=None, ge=1, le=100)


class RoleplayRelationshipSettings(BaseModel):
    role_id: str
    session_id: str
    relationship_level: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class RoleplayRelationshipSettingsRequest(BaseModel):
    relationship_level: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)


class RoleplayMemoryUpdateRequest(BaseModel):
    scope: Literal["pending", "selected"] = "pending"
    turn_ids: list[str] = Field(default_factory=list, max_length=100)


class RoleplayMemoryUpdateResponse(BaseModel):
    status: Literal["updated", "no_changes"]
    added: int = 0
    processed_turn_ids: list[str] = Field(default_factory=list)
    memory: RoleplayMemoryResponse


def _require_mode(mode: str) -> None:
    if mode not in MODES:
        raise HTTPException(status_code=404, detail=f"Unknown mode: {mode}")


def _require_role(role_id: str | None) -> str:
    selected_role_id = role_id or DEFAULT_ROLE_ID
    try:
        get_role(selected_role_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Unknown role: {selected_role_id}") from error
    return selected_role_id


def _validated_image_data_url(value: str | None) -> str | None:
    """Accept a bounded inline image without retaining it on the server."""
    if value is None:
        return None
    match = _IMAGE_DATA_URL.fullmatch(value)
    if match is None:
        raise HTTPException(status_code=422, detail="图片必须是 JPEG、PNG、GIF 或 WebP 的 base64 data URL。")
    try:
        decoded = base64.b64decode(match.group(2), validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(status_code=422, detail="图片 data URL 无法解码。") from None
    if not decoded or len(decoded) > _MAX_INLINE_IMAGE_BYTES:
        raise HTTPException(status_code=422, detail="图片不能为空，且编码前不得超过 8 MiB。")
    host = (urlparse(BASE_URL or "").hostname or "").lower()
    if host in {"open.bigmodel.cn", "api.z.ai"}:
        if match.group(1) not in {"image/jpeg", "image/png"} or len(decoded) > 5 * 1024 * 1024:
            raise HTTPException(status_code=422, detail="当前 GLM 视觉接口只接受不超过 5 MiB 的 JPEG 或 PNG 图片。")
    return value


@lru_cache(maxsize=1)
def _sticker_registry() -> StickerRegistry:
    """Reuse static pack metadata while serializing a Momotalk transcript."""
    return StickerRegistry.from_directory()


def _sticker_url(role_id: str, sticker_id: str | None) -> str | None:
    """Expose an existing local sticker through the server's fixed assets route."""
    if not sticker_id:
        return None
    return _cached_sticker_url(role_id, sticker_id)


@lru_cache(maxsize=256)
def _cached_sticker_url(role_id: str, sticker_id: str) -> str | None:
    """Resolve repeated transcript sticker IDs without reloading role YAML."""
    profile = get_role(role_id)
    sticker = _sticker_registry().get_available(profile.sticker_pack, sticker_id)
    if sticker is None or resolve_sticker_asset(sticker.file) is None:
        return None
    return f"/local-assets/{sticker.file.removeprefix('assets/')}"


def _asset_url(asset_path: str | None) -> str | None:
    """Return a URL only for an existing file safely located below assets/."""
    if not asset_path:
        return None
    assets_root = (PROJECT_DIR / "assets").resolve()
    candidate = (PROJECT_DIR / asset_path).resolve()
    try:
        candidate.relative_to(assets_root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return f"/local-assets/{asset_path.removeprefix('assets/')}"


def _normal_messages(mode: str) -> list[MessageContent]:
    return [
        MessageContent(role=item["role"], text=item["content"])
        for item in get_history(mode)
        if item["role"] in {"user", "assistant"}
    ]


def _roleplay_messages(role_id: str, session_id: str | None = None) -> list[MessageContent]:
    messages: list[MessageContent] = []
    for item in get_roleplay_history(role_id, session_id):
        if item["role"] not in {"user", "assistant"}:
            continue
        content = item["content"]
        sticker_id = content["sticker_id"] if item["role"] == "assistant" else None
        messages.append(
            MessageContent(
                role=item["role"],
                text=content["text"],
                sticker_id=sticker_id,
                sticker_url=_sticker_url(role_id, sticker_id),
                created_at=item.get("created_at"),
                message_kind=item.get("message_kind", "dialogue"),
            )
        )
    return messages


def _source_content(results) -> list[RetrievedSource]:
    """Expose only document metadata for this response, never vector data."""
    return [
        RetrievedSource(
            id=item.document.parent_id or item.document.id,
            title=item.document.title or item.document.parent_id or item.document.id,
            source=item.document.source or None,
            chunk_index=item.document.chunk_index,
            chunk_count=item.document.chunk_count,
        )
        for item in results
    ]


def _memory_content(role_id: str, record: dict | None = None) -> RoleplayMemoryResponse:
    """Render role memory state without exposing raw session text or model prompts."""
    memory = record or load_roleplay_memory(role_id)
    session = get_roleplay_session(role_id)
    pending = max(0, session["completed_turn_count"] - memory["memory_checkpoint_turn"])
    return RoleplayMemoryResponse(
        role_id=role_id,
        enabled=ROLEPLAY_MEMORY_ENABLED,
        revision=memory["revision"],
        completed_turn_count=session["completed_turn_count"],
        memory_checkpoint_turn=memory["memory_checkpoint_turn"],
        pending_turn_count=pending,
        summary=memory["summary"],
        settings=memory["settings"],
        memories=memory["memories"],
        last_error=memory["last_error"],
        last_updated_at=memory["last_updated_at"],
    )


def _alarm_content(alarm: Alarm) -> AlarmContent:
    """Render alarm times in the configured local timezone for the browser."""
    return AlarmContent(
        id=alarm.id,
        role_id=alarm.role_id,
        text=alarm.text,
        due_at=alarm.due_datetime.astimezone(ZoneInfo(APP_TIMEZONE)).isoformat(),
        status=alarm.status,
        created_at=alarm.created_at,
        delivered_at=alarm.delivered_at,
    )


@router.get("/knowledge-bases", response_model=list[KnowledgeBaseContent])
def list_knowledge_bases() -> list[dict]:
    """Read-only management catalog; no source/index files are modified."""
    return list_catalog()


@router.get("/knowledge-bases/{base_id}", response_model=KnowledgeBaseContent)
def read_knowledge_base(base_id: str) -> dict:
    try:
        return get_catalog_entry(base_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Unknown knowledge base: {base_id}") from error

@router.post("/knowledge-bases/{base_id}/documents", response_model=KnowledgeBaseContent)
def create_knowledge_document(base_id: str, request: KnowledgeDocumentRequest) -> dict:
    try:
        add_jsonl_document(base_id, request.model_dump())
        return get_catalog_entry(base_id)
    except (KnowledgeLoadError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

@router.delete("/knowledge-bases/{base_id}/documents/{document_id}", response_model=KnowledgeBaseContent)
def remove_knowledge_document(base_id: str, document_id: str) -> dict:
    try:
        if not delete_jsonl_document(base_id, document_id): raise HTTPException(status_code=404, detail="JSONL document not found")
        return get_catalog_entry(base_id)
    except KnowledgeLoadError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

@router.post("/knowledge-bases/{base_id}/rebuild-index", response_model=KnowledgeBaseContent)
def rebuild_knowledge_index(base_id: str) -> dict:
    try:
        rebuild_index(base_id)
        return get_catalog_entry(base_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/modes")
def list_modes() -> list[dict[str, str | None]]:
    """Return UI-selectable assistant modes without frontend-specific labels."""
    return [
        {
            "id": mode,
            "display_name": values["display_name"],
            "avatar_url": _asset_url(values.get("avatar")),
        }
        for mode, values in MODES.items()
    ]


@router.get("/roles")
def list_role_profiles() -> list[dict[str, str | int | bool | None]]:
    """Return public identity information needed by the Momotalk role selector."""
    return [
        {
            "id": profile.id,
            "display_name": profile.display_name,
            "full_name": profile.identity.full_name,
            "opening_message": profile.roleplay.opening_message,
            "avatar_url": _asset_url(profile.avatar),
            "message_split_enabled": profile.roleplay.message_split.enabled,
            "message_split_delay_ms": profile.roleplay.message_split.display_interval_ms,
        }
        for profile in list_roles()
    ]


@router.get("/roles/{role_id}/memory", response_model=RoleplayMemoryResponse)
def read_roleplay_memory(role_id: str) -> RoleplayMemoryResponse:
    """Read one selected character's isolated memory state and update progress."""
    selected_role_id = _require_role(role_id)
    return _memory_content(selected_role_id)


@router.get("/roles/{role_id}/relationship", response_model=RoleplayRelationshipSettings)
def read_roleplay_relationship(role_id: str, session_id: str = Query(default="default")) -> RoleplayRelationshipSettings:
    """Read the session-local value used by Scene pre-retrieval."""
    selected_role_id = _require_role(role_id)
    try:
        record = get_roleplay_session(selected_role_id, session_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RoleplayRelationshipSettings(role_id=selected_role_id, session_id=session_id, relationship_level=record["relationship_level"])


@router.patch("/roles/{role_id}/relationship", response_model=RoleplayRelationshipSettings)
def patch_roleplay_relationship(role_id: str, request: RoleplayRelationshipSettingsRequest, session_id: str = Query(default="default")) -> RoleplayRelationshipSettings:
    """Update one session's explicit retrieval level without rewriting memories."""
    selected_role_id = _require_role(role_id)
    try:
        level = set_roleplay_relationship_level(selected_role_id, request.relationship_level, session_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RoleplayRelationshipSettings(role_id=selected_role_id, session_id=session_id, relationship_level=level)


@router.patch("/roles/{role_id}/memory/settings", response_model=RoleplayMemoryResponse)
def patch_roleplay_memory_settings(role_id: str, request: RoleplayMemorySettingsRequest) -> RoleplayMemoryResponse:
    """Persist auto-update settings for exactly one character."""
    selected_role_id = _require_role(role_id)
    if request.auto_update_enabled is None and request.update_every_turns is None:
        raise HTTPException(status_code=422, detail="at least one memory setting is required")
    record = update_roleplay_memory_settings(
        selected_role_id,
        auto_update_enabled=request.auto_update_enabled,
        update_every_turns=request.update_every_turns,
    )
    return _memory_content(selected_role_id, record)


@router.get("/roles/{role_id}/memory/turns")
def read_roleplay_memory_turns(role_id: str) -> list[dict[str, object]]:
    """List stable complete-turn IDs for the developer's selected-update workflow."""
    selected_role_id = _require_role(role_id)
    return [
        {
            "turn_id": turn["turn_id"],
            "preview": " ".join(
                message["content"]["text"].strip()
                for message in turn["messages"]
                if message["role"] == "user"
            )[:160],
        }
        for turn in get_roleplay_turns(selected_role_id)
    ]


@router.post("/roles/{role_id}/memory/updates", response_model=RoleplayMemoryUpdateResponse)
def create_roleplay_memory_update(role_id: str, request: RoleplayMemoryUpdateRequest) -> RoleplayMemoryUpdateResponse:
    """Run an explicit pending or selected-turn memory extraction synchronously."""
    selected_role_id = _require_role(role_id)
    try:
        result = update_roleplay_memory(selected_role_id, scope=request.scope, turn_ids=request.turn_ids)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=409 if isinstance(error, RuntimeError) else 422, detail=str(error)) from error
    return RoleplayMemoryUpdateResponse(
        status=result["status"],
        added=result.get("added", 0),
        processed_turn_ids=result.get("processed_turn_ids", []),
        memory=_memory_content(selected_role_id, result["record"]),
    )


@router.get("/alarms", response_model=list[AlarmContent])
def read_alarms(role_id: str = Query()) -> list[AlarmContent]:
    """List the selected role's scheduled and delivered reminders."""
    selected_role_id = _require_role(role_id)
    return [_alarm_content(alarm) for alarm in list_alarms(selected_role_id)]


@router.get("/time", response_model=ServerTimeContent)
def read_server_time() -> ServerTimeContent:
    """Expose the same authoritative local clock used by roleplay and alarms."""
    now = datetime.now(ZoneInfo(APP_TIMEZONE))
    return ServerTimeContent(
        timezone=APP_TIMEZONE,
        local_time=now.isoformat(),
        default_alarm_time=(now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"),
    )


@router.post("/alarms", response_model=AlarmContent, status_code=201)
def schedule_alarm(request: AlarmRequest) -> AlarmContent:
    """Schedule a local reminder using server time as the source of truth."""
    selected_role_id = _require_role(request.role_id)
    try:
        return _alarm_content(create_alarm(selected_role_id, request.text, request.due_at))
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/alarms/{alarm_id}", response_model=AlarmContent)
def remove_alarm(alarm_id: str, role_id: str = Query()) -> AlarmContent:
    """Cancel one pending reminder belonging to the selected role."""
    selected_role_id = _require_role(role_id)
    alarm = cancel_alarm(alarm_id)
    if alarm is None or alarm.role_id != selected_role_id:
        raise HTTPException(status_code=404, detail="Alarm not found")
    return _alarm_content(alarm)


@router.delete("/alarms/{alarm_id}/history", status_code=204)
def remove_alarm_history(alarm_id: str, role_id: str = Query()) -> None:
    """Delete a delivered or cancelled reminder from the local history."""
    selected_role_id = _require_role(role_id)
    try:
        alarm = delete_alarm_history(alarm_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if alarm is None or alarm.role_id != selected_role_id:
        raise HTTPException(status_code=404, detail="Alarm not found")


@router.get("/roleplay/sessions", response_model=list[RoleplaySessionContent])
def read_roleplay_sessions(role_id: str = Query()) -> list[RoleplaySessionContent]:
    """List independent sessions with their persistent opening backgrounds."""
    return [RoleplaySessionContent(**item) for item in list_roleplay_sessions(_require_role(role_id))]


@router.post("/roleplay/sessions", response_model=RoleplaySessionContent, status_code=201)
def create_roleplay_session_endpoint(role_id: str = Query(), request: CreateRoleplaySessionRequest | None = None) -> RoleplaySessionContent:
    """Create an empty conversation namespace for the selected character."""
    selected_role_id = _require_role(role_id)
    session_id, record = create_roleplay_session(selected_role_id, request.background if request else "")
    return RoleplaySessionContent(
        session_id=session_id,
        record_id=record["session_id"],
        revision=record["revision"],
        completed_turn_count=record["completed_turn_count"],
        background=record["background"],
        last_message_at=None,
    )


@router.put("/roleplay/scene", response_model=VisualSceneContent)
def select_roleplay_visual_scene(
    request: SelectVisualSceneRequest,
    role_id: str = Query(),
    session_id: str | None = Query(default=None),
) -> VisualSceneContent:
    """Use the location explicitly selected in the visual-novel UI."""
    selected_role_id = _require_role(role_id)
    try:
        scene_id = set_roleplay_visual_scene(selected_role_id, request.scene_id, session_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return VisualSceneContent(scene_id=scene_id)


@router.get("/conversations", response_model=ConversationResponse)
def read_conversation(
    mode: str = Query(),
    role_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
) -> ConversationResponse:
    """Read one normal-mode or roleplay conversation in a unified UI format."""
    _require_mode(mode)
    if mode == ROLEPLAY:
        selected_role_id = _require_role(role_id)
        return ConversationResponse(
            mode=mode,
            role_id=selected_role_id,
            session_id=session_id,
            messages=_roleplay_messages(selected_role_id, session_id),
            visual_scene_id=get_roleplay_session(selected_role_id, session_id)["visual_scene_id"],
        )
    return ConversationResponse(mode=mode, messages=_normal_messages(mode))


@router.post("/messages", response_model=ConversationResponse)
def send_message(request: SendMessageRequest) -> ConversationResponse:
    """Run existing chat logic, then return the authoritative persisted transcript."""
    _require_mode(request.mode)
    text = request.text.strip()
    image_data_url = _validated_image_data_url(request.image_data_url)
    if not text and image_data_url is None:
        raise HTTPException(status_code=422, detail="Message text must not be blank")
    if request.mode == ROLEPLAY:
        selected_role_id = _require_role(request.role_id)
        if request.message_kind == "narration":
            if image_data_url is not None:
                raise HTTPException(status_code=422, detail="旁白不能同时附带图片。")
            try:
                session_record = get_roleplay_session(selected_role_id, request.session_id)
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            if not session_record["completed_turn_count"] and not session_record["background"] and len(text) > MAX_SESSION_BACKGROUND_CHARS:
                raise HTTPException(status_code=422, detail=f"首轮旁白不能超过 {MAX_SESSION_BACKGROUND_CHARS} 字。")
        try:
            _, sources = chat_structured_many_with_sources(
                text,
                selected_role_id,
                session_id=request.session_id,
                image_data_url=image_data_url,
                message_kind=request.message_kind,
            )
        except APIStatusError as error:
            if image_data_url is None:
                raise
            if error.status_code == 429:
                raise HTTPException(
                    status_code=503,
                    detail=f"视觉模型 {VISION_MODEL} 当前请求过多（上游 HTTP 429），请稍后重试或设置其他 VISION_MODEL。",
                ) from error
            raise HTTPException(
                status_code=502,
                detail=(
                    f"识图请求被模型接口拒绝（上游 HTTP {error.status_code}，模型 {VISION_MODEL}）。"
                    "请检查 VISION_MODEL 是否为当前 BASE_URL 支持的视觉模型，以及图片格式和额度。"
                ),
            ) from error
        return ConversationResponse(
            mode=request.mode,
            role_id=selected_role_id,
            session_id=request.session_id,
            messages=_roleplay_messages(selected_role_id, request.session_id),
            visual_scene_id=get_roleplay_session(selected_role_id, request.session_id)["visual_scene_id"],
            retrieved_sources=_source_content(sources),
        )
    if image_data_url is not None:
        raise HTTPException(status_code=422, detail="当前仅角色扮演模式支持识图。")
    _, sources = chat_with_sources(text, [], request.mode)
    return ConversationResponse(mode=request.mode, messages=_normal_messages(request.mode), retrieved_sources=_source_content(sources))


@router.delete("/conversations", response_model=ConversationResponse)
def delete_conversation(
    mode: str = Query(),
    role_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
) -> ConversationResponse:
    """Clear exactly one selected conversation and leave all other modes intact."""
    _require_mode(mode)
    if mode == ROLEPLAY:
        selected_role_id = _require_role(role_id)
        clear_roleplay_history(selected_role_id, session_id)
        return ConversationResponse(mode=mode, role_id=selected_role_id, session_id=session_id, messages=[])
    clear_history(mode)
    return ConversationResponse(mode=mode, messages=[])


def asset_directory() -> str:
    """Return the single static root used by the API host for local UI assets."""
    return str(PROJECT_DIR / "assets")
