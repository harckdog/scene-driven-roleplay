"""Persistent, model-bound vector cache for one local knowledge base."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from config import KNOWLEDGE_INDEX_DIR
from knowledge.schema import validate_knowledge_base_id


INDEX_SCHEMA_VERSION = 1


def index_path(base_id: str) -> Path:
    """Return one safe, isolated index path."""
    return KNOWLEDGE_INDEX_DIR / f"{validate_knowledge_base_id(base_id)}.json"


def fingerprint(text: str) -> str:
    """Return the source-sensitive fingerprint used to invalidate a vector."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_index(base_id: str, model_id: str) -> dict[str, Any]:
    """Return an empty model-bound index record."""
    return {"version": INDEX_SCHEMA_VERSION, "knowledge_base_id": base_id, "model_id": model_id, "entries": {}}


def load(base_id: str, model_id: str) -> dict[str, Any]:
    """Load valid entries only when they share the active embedding model."""
    path = index_path(base_id)
    if not path.is_file():
        return default_index(base_id, model_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_index(base_id, model_id)
    if (
        not isinstance(raw, dict)
        or raw.get("version") != INDEX_SCHEMA_VERSION
        or raw.get("knowledge_base_id") != base_id
        or raw.get("model_id") != model_id
        or not isinstance(raw.get("entries"), dict)
    ):
        return default_index(base_id, model_id)
    entries: dict[str, dict[str, Any]] = {}
    for document_id, entry in raw["entries"].items():
        vector = entry.get("vector") if isinstance(entry, dict) else None
        source_fingerprint = entry.get("fingerprint") if isinstance(entry, dict) else None
        if isinstance(document_id, str) and isinstance(source_fingerprint, str) and isinstance(vector, list) and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector):
            entries[document_id] = {"fingerprint": source_fingerprint, "vector": [float(value) for value in vector]}
    record = default_index(base_id, model_id)
    record["entries"] = entries
    return record


def save(base_id: str, record: dict[str, Any]) -> None:
    """Atomically write an index cache; source files are never changed."""
    path = index_path(base_id)
    KNOWLEDGE_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
