"""Versioned local persistence for roleplay memories."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from config import (
    ROLEPLAY_MEMORY_AUTO_UPDATE_ENABLED,
    ROLEPLAY_MEMORY_DIR,
    ROLEPLAY_MEMORY_UPDATE_EVERY_TURNS,
)
from roleplay.evidence.schema import validate_role_id


MEMORY_SCHEMA_VERSION = 1
_KINDS = {"user_fact", "preference", "shared_episode", "commitment", "relationship_fact"}
_STATUSES = {"active", "completed", "cancelled", "superseded", "forgotten"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(role_id: str) -> Path:
    validate_role_id(role_id)
    return ROLEPLAY_MEMORY_DIR / f"{role_id}.json"


def _default(role_id: str) -> dict[str, Any]:
    return {
        "version": MEMORY_SCHEMA_VERSION,
        "role_id": role_id,
        "revision": 0,
        "memory_checkpoint_turn": 0,
        "summary": "",
        "settings": {
            "auto_update_enabled": ROLEPLAY_MEMORY_AUTO_UPDATE_ENABLED,
            "update_every_turns": ROLEPLAY_MEMORY_UPDATE_EVERY_TURNS,
        },
        "memories": [],
        "last_error": None,
        "last_updated_at": None,
    }


def _normalize_memory(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    content = value.get("content")
    kind = value.get("kind")
    if not isinstance(content, str) or not content.strip() or not isinstance(kind, str) or kind not in _KINDS:
        return None
    status = value.get("status", "active")
    if status not in _STATUSES:
        return None
    importance = value.get("importance", 0.5)
    if not isinstance(importance, (int, float)) or isinstance(importance, bool):
        importance = 0.5
    source_turn_ids = value.get("source_turn_ids", [])
    if not isinstance(source_turn_ids, list) or any(not isinstance(item, str) for item in source_turn_ids):
        source_turn_ids = []
    return {
        "id": value.get("id") if isinstance(value.get("id"), str) and value["id"] else f"mem_{uuid4().hex}",
        "kind": kind,
        "content": content.strip(),
        "status": status,
        "importance": max(0.0, min(1.0, float(importance))),
        "pinned": bool(value.get("pinned", False)),
        "source_turn_ids": source_turn_ids,
        "created_at": value.get("created_at") if isinstance(value.get("created_at"), str) else _now(),
        "updated_at": value.get("updated_at") if isinstance(value.get("updated_at"), str) else _now(),
    }


def load(role_id: str) -> dict[str, Any]:
    """Load one role's normalized memory record without treating corruption as data."""
    record = _default(role_id)
    path = _path(role_id)
    if not path.exists():
        return record
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        record["last_error"] = "Memory record could not be read; it was left unchanged."
        return record
    if not isinstance(raw, dict) or raw.get("role_id") != role_id:
        return record
    record["revision"] = raw.get("revision") if isinstance(raw.get("revision"), int) and raw["revision"] >= 0 else 0
    record["memory_checkpoint_turn"] = raw.get("memory_checkpoint_turn") if isinstance(raw.get("memory_checkpoint_turn"), int) and raw["memory_checkpoint_turn"] >= 0 else 0
    record["summary"] = raw.get("summary") if isinstance(raw.get("summary"), str) else ""
    settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
    enabled = settings.get("auto_update_enabled")
    interval = settings.get("update_every_turns")
    record["settings"] = {
        "auto_update_enabled": enabled if isinstance(enabled, bool) else ROLEPLAY_MEMORY_AUTO_UPDATE_ENABLED,
        "update_every_turns": interval if isinstance(interval, int) and interval > 0 else ROLEPLAY_MEMORY_UPDATE_EVERY_TURNS,
    }
    record["memories"] = [item for value in raw.get("memories", []) if (item := _normalize_memory(value)) is not None]
    record["last_error"] = raw.get("last_error") if isinstance(raw.get("last_error"), str) else None
    record["last_updated_at"] = raw.get("last_updated_at") if isinstance(raw.get("last_updated_at"), str) else None
    return record


def save(role_id: str, record: dict[str, Any]) -> None:
    """Atomically write a validated role memory record."""
    normalized = _default(role_id)
    normalized["revision"] = record.get("revision") if isinstance(record.get("revision"), int) and record["revision"] >= 0 else 0
    normalized["memory_checkpoint_turn"] = record.get("memory_checkpoint_turn") if isinstance(record.get("memory_checkpoint_turn"), int) and record["memory_checkpoint_turn"] >= 0 else 0
    normalized["summary"] = record.get("summary") if isinstance(record.get("summary"), str) else ""
    normalized["settings"] = record.get("settings") if isinstance(record.get("settings"), dict) else normalized["settings"]
    normalized["memories"] = [item for value in record.get("memories", []) if (item := _normalize_memory(value)) is not None]
    normalized["last_error"] = record.get("last_error") if isinstance(record.get("last_error"), str) else None
    normalized["last_updated_at"] = record.get("last_updated_at") if isinstance(record.get("last_updated_at"), str) else None
    path = _path(role_id)
    ROLEPLAY_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def update_settings(role_id: str, *, auto_update_enabled: bool | None = None, update_every_turns: int | None = None) -> dict[str, Any]:
    """Update only validated runtime settings for one role."""
    if update_every_turns is not None and update_every_turns < 1:
        raise ValueError("update_every_turns must be positive")
    record = load(role_id)
    if auto_update_enabled is not None:
        record["settings"]["auto_update_enabled"] = auto_update_enabled
    if update_every_turns is not None:
        record["settings"]["update_every_turns"] = update_every_turns
    record["revision"] += 1
    save(role_id, record)
    return deepcopy(record)


def active_memories(role_id: str) -> list[dict[str, Any]]:
    """Return only memories that remain eligible for model context."""
    return [item for item in load(role_id)["memories"] if item["status"] == "active"]


def reset_session_progress(role_id: str) -> None:
    """Start a new conversation's checkpoints without deleting long-term facts."""
    record = load(role_id)
    record["memory_checkpoint_turn"] = 0
    record["summary"] = ""
    record["last_error"] = None
    record["revision"] += 1
    save(role_id, record)
