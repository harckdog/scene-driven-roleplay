"""Role-isolated, structured session persistence for Roleplay mode."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from threading import RLock
from math import isfinite
from typing import Any
from uuid import uuid4

from config import ROLEPLAY_SESSION_DIR
from roleplay.visual_scene import SCENES, normalize_scene_id


_ROLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SESSION_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_STICKER_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SPEECH_HABIT_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_VALID_ROLES = {"user", "assistant", "system"}

RoleplayMessage = dict[str, Any]
SESSION_SCHEMA_VERSION = 5
DEFAULT_SESSION_KEY = "default"
DEFAULT_RELATIONSHIP_LEVEL = 0.50
MAX_SESSION_BACKGROUND_CHARS = 4000
_LOCKS: dict[tuple[str, str], RLock] = {}
_LOCKS_GUARD = RLock()


def _validate_role_id(role_id: str) -> None:
    """Reject invalid role identifiers before constructing a file path."""
    if not _ROLE_ID_PATTERN.fullmatch(role_id):
        raise ValueError("role_id must contain lowercase letters, digits, and underscores")


def _session_key(session_id: str | None) -> str:
    """Normalize a public session key without allowing path fragments."""
    key = DEFAULT_SESSION_KEY if session_id is None else session_id
    if not isinstance(key, str) or not _SESSION_KEY_PATTERN.fullmatch(key):
        raise ValueError("session_id must contain letters, digits, underscores, or hyphens")
    return key


def _session_path(role_id: str, session_id: str | None = None) -> Path:
    """Return one role-local session path; preserve the legacy default path."""
    _validate_role_id(role_id)
    key = _session_key(session_id)
    if key == DEFAULT_SESSION_KEY:
        return ROLEPLAY_SESSION_DIR / f"{role_id}.json"
    return ROLEPLAY_SESSION_DIR / role_id / f"{key}.json"


def _timestamp() -> str:
    """Create a portable UTC timestamp for newly persisted messages."""
    return datetime.now(timezone.utc).isoformat()


def _lock(role_id: str, session_id: str | None = None) -> RLock:
    """Return the in-process persistence lock for one role-local session."""
    _validate_role_id(role_id)
    key = _session_key(session_id)
    with _LOCKS_GUARD:
        return _LOCKS.setdefault((role_id, key), RLock())


def _new_record() -> dict[str, Any]:
    return {
        "schema_version": SESSION_SCHEMA_VERSION,
        "session_id": f"session_{uuid4().hex}",
        "revision": 0,
        "completed_turn_count": 0,
        "runtime_state": None,
        "relationship_level": DEFAULT_RELATIONSHIP_LEVEL,
        "background": "",
        "visual_scene_id": "",
        "messages": [],
    }


def _normalize_expression(value: object) -> dict[str, Any] | None:
    """Validate optional diagnostic expression metadata from structured replies."""
    if not isinstance(value, dict) or set(value) != {"primary_affect", "intensity", "styles"}:
        return None
    primary = value.get("primary_affect")
    intensity = value.get("intensity")
    styles = value.get("styles")
    if (
        not isinstance(primary, str)
        or not isinstance(intensity, str)
        or intensity not in {"mild", "medium", "high", "extreme"}
        or not isinstance(styles, list)
        or any(not isinstance(style, str) for style in styles)
    ):
        return None
    return {"primary_affect": primary, "intensity": intensity, "styles": styles}


def _normalize_content(value: object) -> dict[str, Any] | None:
    """Normalize legacy text or structured content without accepting file paths.

    The ``sticker_id`` is deliberately an opaque identifier. Asset paths remain in
    manifests and are never stored in a conversation record.
    """
    if isinstance(value, str):
        return {"text": value, "sticker_id": None}
    if not isinstance(value, dict):
        return None

    text = value.get("text", "")
    sticker_id = value.get("sticker_id")
    if not isinstance(text, str):
        return None
    if sticker_id is not None and (
        not isinstance(sticker_id, str) or not _STICKER_ID_PATTERN.fullmatch(sticker_id)
    ):
        return None
    if not text.strip() and sticker_id is None:
        return None
    content: dict[str, Any] = {"text": text, "sticker_id": sticker_id}
    if "expression" in value:
        expression = _normalize_expression(value.get("expression"))
        if expression is None:
            return None
        content["expression"] = expression
    if "speech_habit_ids" in value:
        content["speech_habit_ids"] = _normalize_speech_habit_ids(value.get("speech_habit_ids"))
    return content


def _normalize_speech_habit_ids(value: object) -> list[str]:
    """Keep a bounded, syntactically safe optional diagnostic list."""
    if not isinstance(value, list):
        return []
    accepted: list[str] = []
    for item in value:
        if isinstance(item, str) and _SPEECH_HABIT_ID_PATTERN.fullmatch(item) and item not in accepted:
            accepted.append(item)
        if len(accepted) == 2:
            break
    return accepted


def normalize_message(item: object, *, assign_timestamp: bool = False) -> RoleplayMessage | None:
    """Return a safe structured message, including legacy text-only records.

    Legacy ``content: \"hello\"`` records are read as
    ``content: {text: \"hello\", sticker_id: null}`` without requiring a manual
    migration. A timestamp is created only before writing a normalized record.
    """
    if not isinstance(item, dict) or item.get("role") not in _VALID_ROLES:
        return None
    content = _normalize_content(item.get("content"))
    if content is None:
        return None
    created_at = item.get("created_at")
    if created_at is not None and (not isinstance(created_at, str) or not created_at.strip()):
        return None
    if created_at is None and assign_timestamp:
        created_at = _timestamp()

    message: RoleplayMessage = {"role": item["role"], "content": content}
    if item["role"] == "user" and item.get("message_kind") == "narration":
        message["message_kind"] = "narration"
    if created_at is not None:
        message["created_at"] = created_at
    message_id = item.get("message_id")
    if message_id is not None and isinstance(message_id, str) and message_id:
        message["message_id"] = message_id
    turn_id = item.get("turn_id")
    if turn_id is not None and isinstance(turn_id, str) and turn_id:
        message["turn_id"] = turn_id
    event_type = item.get("event_type")
    if event_type in {"turn", "reminder", "legacy_unknown"}:
        message["event_type"] = event_type
    return message


def load_record(role_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Load one versioned session record, safely reading legacy message arrays."""
    path = _session_path(role_id, session_id)
    if not path.exists():
        return _new_record()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _new_record()
    if isinstance(raw, list):
        record = _new_record()
        record["messages"] = [
            {**message, "event_type": "legacy_unknown"}
            for item in raw
            if (message := normalize_message(item)) is not None
        ]
        return record
    if not isinstance(raw, dict) or not isinstance(raw.get("messages"), list):
        return _new_record()
    record = _new_record()
    record["session_id"] = raw.get("session_id") if isinstance(raw.get("session_id"), str) and raw["session_id"] else record["session_id"]
    record["revision"] = raw.get("revision") if isinstance(raw.get("revision"), int) and raw["revision"] >= 0 else 0
    record["completed_turn_count"] = raw.get("completed_turn_count") if isinstance(raw.get("completed_turn_count"), int) and raw["completed_turn_count"] >= 0 else 0
    record["runtime_state"] = _normalize_runtime_state(raw.get("runtime_state"))
    record["relationship_level"] = _normalize_relationship_level(raw.get("relationship_level"))
    record["background"] = _normalize_background(raw.get("background"))
    record["visual_scene_id"] = normalize_scene_id(raw.get("visual_scene_id"))
    record["messages"] = [
        message for item in raw["messages"] if (message := normalize_message(item)) is not None
    ]
    return record


def load(role_id: str, session_id: str | None = None) -> list[RoleplayMessage]:
    """Load valid messages for one character in normalized structured form."""
    return load_record(role_id, session_id)["messages"]


def save_record(role_id: str, record: dict[str, Any], session_id: str | None = None) -> None:
    """Atomically persist a versioned role session record."""
    normalized = _new_record()
    normalized["session_id"] = record.get("session_id") if isinstance(record.get("session_id"), str) and record["session_id"] else normalized["session_id"]
    normalized["revision"] = record.get("revision") if isinstance(record.get("revision"), int) and record["revision"] >= 0 else 0
    normalized["completed_turn_count"] = record.get("completed_turn_count") if isinstance(record.get("completed_turn_count"), int) and record["completed_turn_count"] >= 0 else 0
    normalized["runtime_state"] = _normalize_runtime_state(record.get("runtime_state"))
    normalized["relationship_level"] = _normalize_relationship_level(record.get("relationship_level"))
    normalized["background"] = _normalize_background(record.get("background"))
    normalized["visual_scene_id"] = normalize_scene_id(record.get("visual_scene_id"))
    normalized["messages"] = [
        message for item in record.get("messages", [])
        if (message := normalize_message(item, assign_timestamp=True)) is not None
    ]
    for message in normalized["messages"]:
        message.setdefault("message_id", f"msg_{uuid4().hex}")
        message.setdefault("event_type", "legacy_unknown")
    path = _session_path(role_id, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def save(role_id: str, history: list[RoleplayMessage], session_id: str | None = None) -> None:
    """Persist a role-specific session in the current structured schema."""
    with _lock(role_id, session_id):
        record = load_record(role_id, session_id)
        record["messages"] = history
        record["revision"] += 1
        save_record(role_id, record, session_id)


def append(
    role_id: str,
    role: str,
    text: str = "",
    *,
    sticker_id: str | None = None,
    event_type: str = "legacy_unknown",
    session_id: str | None = None,
) -> None:
    """Append a non-turn event or legacy-compatible message to one session."""
    if role not in _VALID_ROLES:
        raise ValueError(f"unsupported message role: {role}")
    if event_type not in {"reminder", "legacy_unknown"}:
        raise ValueError("append only supports reminder or legacy_unknown events")
    content: dict[str, Any] = {"text": text, "sticker_id": sticker_id}
    message = normalize_message({"role": role, "content": content}, assign_timestamp=True)
    if message is None:
        raise ValueError("message requires text or a valid sticker_id")
    with _lock(role_id, session_id):
        record = load_record(role_id, session_id)
        message["message_id"] = f"msg_{uuid4().hex}"
        message["event_type"] = event_type
        record["messages"].append(message)
        record["revision"] += 1
        save_record(role_id, record, session_id)


def _normalize_runtime_state(value: object) -> dict[str, Any] | None:
    """Preserve historical state data without loading the retired state engine."""
    return deepcopy(value) if isinstance(value, dict) else None


def _normalize_relationship_level(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value) and 0 <= value <= 1:
        return float(value)
    return DEFAULT_RELATIONSHIP_LEVEL


def _normalize_background(value: object) -> str:
    if not isinstance(value, str) or len(value) > MAX_SESSION_BACKGROUND_CHARS:
        return ""
    return value.strip()


def set_relationship_level(role_id: str, relationship_level: float, session_id: str | None = None) -> float:
    """Persist an explicit Scene-retrieval relationship level for one session."""
    if (
        not isinstance(relationship_level, (int, float))
        or isinstance(relationship_level, bool)
        or not isfinite(relationship_level)
        or not 0 <= relationship_level <= 1
    ):
        raise ValueError("relationship_level must be a finite number from 0.0 to 1.0")
    with _lock(role_id, session_id):
        record = load_record(role_id, session_id)
        record["relationship_level"] = float(relationship_level)
        record["revision"] += 1
        save_record(role_id, record, session_id)
    return float(relationship_level)


def set_initial_background_from_narration(role_id: str, text: str, session_id: str | None = None) -> bool:
    """Persist first-turn narration as session context before generation."""
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_SESSION_BACKGROUND_CHARS:
        raise ValueError(f"initial narration must be 1 to {MAX_SESSION_BACKGROUND_CHARS} characters")
    with _lock(role_id, session_id):
        record = load_record(role_id, session_id)
        if record["completed_turn_count"] or record["background"]:
            return False
        record["background"] = text.strip()
        record["revision"] += 1
        save_record(role_id, record, session_id)
    return True


def set_visual_scene(role_id: str, scene_id: str, session_id: str | None = None) -> str:
    """Persist a player's explicit location selection for one conversation."""
    if not isinstance(scene_id, str) or scene_id not in SCENES:
        raise ValueError("Unknown visual scene")
    with _lock(role_id, session_id):
        record = load_record(role_id, session_id)
        if scene_id != record["visual_scene_id"]:
            record["visual_scene_id"] = scene_id
            record["revision"] += 1
            save_record(role_id, record, session_id)
        return scene_id


def append_turn(
    role_id: str,
    user_text: str,
    replies: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    message_kind: str = "dialogue",
) -> int:
    """Atomically append a complete user turn and its reply bubbles."""
    if not user_text.strip() or not replies:
        raise ValueError("a roleplay turn requires a user message and at least one reply")
    if message_kind not in {"dialogue", "narration"}:
        raise ValueError("message_kind must be dialogue or narration")
    with _lock(role_id, session_id):
        record = load_record(role_id, session_id)
        turn_id = f"turn_{uuid4().hex}"
        pending: list[RoleplayMessage] = []
        user = normalize_message({"role": "user", "content": {"text": user_text, "sticker_id": None}, "message_kind": message_kind}, assign_timestamp=True)
        assert user is not None
        pending.append(user)
        for reply in replies:
            candidate = normalize_message({"role": "assistant", "content": reply}, assign_timestamp=True)
            if candidate is None:
                raise ValueError("invalid assistant reply")
            pending.append(candidate)
        for message in pending:
            message["message_id"] = f"msg_{uuid4().hex}"
            message["turn_id"] = turn_id
            message["event_type"] = "turn"
        record["messages"].extend(pending)
        record["completed_turn_count"] += 1
        record["revision"] += 1
        save_record(role_id, record, session_id)
        return record["completed_turn_count"]


def get_history(role_id: str, session_id: str | None = None) -> list[RoleplayMessage]:
    """Return a safe copy of one character's normalized session."""
    return deepcopy(load(role_id, session_id))


def get_session(role_id: str, session_id: str | None = None) -> dict[str, Any]:
    """Return a safe copy of the versioned session metadata and messages."""
    return deepcopy(load_record(role_id, session_id))


def create_session(role_id: str, background: str = "") -> tuple[str, dict[str, Any]]:
    """Create an empty, independent session inside one character namespace."""
    _validate_role_id(role_id)
    if not isinstance(background, str) or len(background) > MAX_SESSION_BACKGROUND_CHARS:
        raise ValueError(f"background must be at most {MAX_SESSION_BACKGROUND_CHARS} characters")
    session_id = f"rp_{uuid4().hex}"
    record = _new_record()
    record["background"] = background.strip()
    with _lock(role_id, session_id):
        save_record(role_id, record, session_id)
    return session_id, deepcopy(record)


def list_sessions(role_id: str) -> list[dict[str, Any]]:
    """List role-local sessions without exposing their message contents."""
    _validate_role_id(role_id)
    keys = [DEFAULT_SESSION_KEY]
    directory = ROLEPLAY_SESSION_DIR / role_id
    if directory.exists():
        keys.extend(sorted(path.stem for path in directory.glob("*.json") if _SESSION_KEY_PATTERN.fullmatch(path.stem)))
    result: list[dict[str, Any]] = []
    for key in keys:
        record = load_record(role_id, key)
        messages = record["messages"]
        result.append({
            "session_id": key,
            "record_id": record["session_id"],
            "revision": record["revision"],
            "completed_turn_count": record["completed_turn_count"],
            "background": record["background"],
            "last_message_at": messages[-1].get("created_at") if messages else None,
        })
    return result


def get_turns(role_id: str, turn_ids: set[str] | None = None, *, session_id: str | None = None) -> list[dict[str, Any]]:
    """Return persisted complete turns in chronological order."""
    record = load_record(role_id, session_id)
    grouped: dict[str, list[RoleplayMessage]] = {}
    order: list[str] = []
    for message in record["messages"]:
        turn_id = message.get("turn_id")
        if message.get("event_type") != "turn" or not isinstance(turn_id, str):
            continue
        if turn_id not in grouped:
            grouped[turn_id] = []
            order.append(turn_id)
        grouped[turn_id].append(message)
    return [
        {"turn_id": turn_id, "messages": deepcopy(grouped[turn_id])}
        for turn_id in order
        if turn_ids is None or turn_id in turn_ids
    ]


def clear(role_id: str, session_id: str | None = None) -> None:
    """Clear one character's session without affecting other roles."""
    with _lock(role_id, session_id):
        save_record(role_id, _new_record(), session_id)
    # Keep durable facts, but a new session must not inherit the old turn
    # checkpoint or rolling summary. The local import avoids a module cycle.
    if _session_key(session_id) == DEFAULT_SESSION_KEY:
        from roleplay.memory.manager import reset_session_progress
        reset_session_progress(role_id)
