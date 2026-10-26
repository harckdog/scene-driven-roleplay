"""Persistent local vector index for roleplay scene-card retrieval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from roleplay.evidence.schema import validate_role_id


PROJECT_DIR = Path(__file__).resolve().parents[2]
INDEX_DIR = PROJECT_DIR / "local_data" / "roleplay_indexes"
INDEX_SCHEMA_VERSION = 2


def index_path(role_id: str) -> Path:
    """Return the role-isolated local vector-index path."""
    validate_role_id(role_id)
    return INDEX_DIR / f"{role_id}.json"


def fingerprint(text: str) -> str:
    """Return a stable fingerprint for one scene card's retrieval text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def default_index(role_id: str, model_id: str) -> dict[str, Any]:
    """Create an empty, model-bound index record."""
    return {
        "version": INDEX_SCHEMA_VERSION,
        "role_id": role_id,
        "model_id": model_id,
        "entries": {},
    }


def load(role_id: str, model_id: str) -> dict[str, Any]:
    """Load only an index compatible with the requested embedding model."""
    path = index_path(role_id)
    if not path.is_file():
        return default_index(role_id, model_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_index(role_id, model_id)
    if (
        not isinstance(raw, dict)
        or raw.get("version") != INDEX_SCHEMA_VERSION
        or raw.get("role_id") != role_id
        or raw.get("model_id") != model_id
        or not isinstance(raw.get("entries"), dict)
    ):
        return default_index(role_id, model_id)

    valid_entries: dict[str, dict[str, Any]] = {}
    for card_id, entry in raw["entries"].items():
        if not isinstance(card_id, str) or not isinstance(entry, dict):
            continue
        card_fingerprint = entry.get("fingerprint")
        vector = entry.get("vector")
        if (
            isinstance(card_fingerprint, str)
            and isinstance(vector, list)
            and all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in vector)
        ):
            valid_entries[card_id] = {
                "fingerprint": card_fingerprint,
                "vector": [float(value) for value in vector],
            }
    record = default_index(role_id, model_id)
    record["entries"] = valid_entries
    return record


def save(role_id: str, record: dict[str, Any]) -> None:
    """Atomically persist one role's local vector index."""
    path = index_path(role_id)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
