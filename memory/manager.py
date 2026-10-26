"""Versioned persistence for long-term memories."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from config import MEMORY_DIR
from summary.manager import load as load_summary


MEMORY_SCHEMA_VERSION = 1


def _memory_path(mode: str) -> Path:
    """Return the storage path for one chat mode.

    Args:
        mode: Conversation mode.

    Returns:
        JSON file path for the mode.
    """
    return MEMORY_DIR / f"{mode}.json"


def _default_record(mode: str) -> dict[str, Any]:
    """Create an empty memory record for a mode."""
    return {
        "version": MEMORY_SCHEMA_VERSION,
        "mode": mode,
        "last_summary_index": 0,
        "memories": [],
    }


def _now() -> str:
    """Return the current UTC timestamp in ISO 8601 form."""
    return datetime.now(timezone.utc).isoformat()


def _normalize_memories(raw_memories: object) -> list[dict[str, str]]:
    """Validate new records and migrate legacy string memories in memory.

    Args:
        raw_memories: Raw ``memories`` collection or legacy list.

    Returns:
        Validated memory entries.
    """
    if not isinstance(raw_memories, list):
        return []

    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_memories:
        if isinstance(item, str):
            content = item.strip()
            created_at = ""
        elif isinstance(item, dict):
            content = item.get("content", "").strip() if isinstance(item.get("content"), str) else ""
            created_at = item.get("created_at", "") if isinstance(item.get("created_at"), str) else ""
        else:
            continue

        if content and content not in seen:
            normalized.append({"content": content, "created_at": created_at})
            seen.add(content)
    return normalized


def load_record(mode: str) -> dict[str, Any]:
    """Load a normalized versioned memory record.

    Legacy ``["memory"]`` files are read safely and migrated on the next write.

    Args:
        mode: Conversation mode.

    Returns:
        Normalized memory record.
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    path = _memory_path(mode)
    if not path.exists():
        return _default_record(mode)

    try:
        with open(path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError):
        return _default_record(mode)

    if isinstance(raw, list):
        record = _default_record(mode)
        record["memories"] = _normalize_memories(raw)
        return record

    if not isinstance(raw, dict):
        return _default_record(mode)

    record = _default_record(mode)
    record["version"] = raw.get("version") if isinstance(raw.get("version"), int) else MEMORY_SCHEMA_VERSION
    record["mode"] = raw.get("mode") if isinstance(raw.get("mode"), str) else mode
    last_index = raw.get("last_summary_index", 0)
    record["last_summary_index"] = last_index if isinstance(last_index, int) and last_index >= 0 else 0
    record["memories"] = _normalize_memories(raw.get("memories", []))
    return record


def save_record(mode: str, record: dict[str, Any]) -> None:
    """Persist a normalized memory record.

    Args:
        mode: Conversation mode.
        record: Memory record to write.
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    normalized = _default_record(mode)
    normalized["last_summary_index"] = record.get("last_summary_index", 0)
    normalized["memories"] = _normalize_memories(record.get("memories", []))
    with open(_memory_path(mode), "w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)


def load(mode: str) -> list[str]:
    """Return memory content strings for existing callers.

    Args:
        mode: Conversation mode.

    Returns:
        Stable memory strings.
    """
    return [item["content"] for item in load_record(mode)["memories"]]


def save(mode: str, memories: list[str]) -> None:
    """Save content strings using the versioned schema.

    Args:
        mode: Conversation mode.
        memories: Memory strings to persist.
    """
    previous = load_record(mode)
    previous["memories"] = [{"content": item, "created_at": _now()} for item in memories]
    save_record(mode, previous)


def append(mode: str, content: str) -> None:
    """Add one stable memory if it does not already exist.

    Args:
        mode: Conversation mode.
        content: Memory text.
    """
    update(mode, [content], mark_summary_processed=False)


def clear(mode: str) -> None:
    """Clear all memories and reset the processing checkpoint.

    Args:
        mode: Conversation mode.
    """
    save_record(mode, _default_record(mode))


def update(
    mode: str,
    memories: list[str],
    *,
    mark_summary_processed: bool = True,
) -> None:
    """Merge newly extracted memories and advance the summary checkpoint.

    Args:
        mode: Conversation mode.
        memories: Candidate memory strings.
        mark_summary_processed: Whether the current summary has been processed.
    """
    record = load_record(mode)
    existing = {item["content"] for item in record["memories"]}
    for content in memories:
        cleaned = content.strip()
        if cleaned and cleaned not in existing:
            record["memories"].append({"content": cleaned, "created_at": _now()})
            existing.add(cleaned)

    if mark_summary_processed:
        record["last_summary_index"] = load_summary(mode)["last_index"]
    save_record(mode, record)


def need_update(mode: str, threshold: int = 20) -> tuple[bool, str]:
    """Determine whether an unprocessed summary warrants memory extraction.

    Args:
        mode: Conversation mode.
        threshold: Minimum summary length required for extraction.

    Returns:
        Whether extraction is needed and the current summary text.
    """
    summary_record = load_summary(mode)
    summary = summary_record["summary"]
    memory_record = load_record(mode)
    has_unprocessed_summary = summary_record["last_index"] > memory_record["last_summary_index"]
    return has_unprocessed_summary and len(summary) >= threshold, summary
