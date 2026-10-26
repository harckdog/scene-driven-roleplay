"""Read-only catalog views for local knowledge-base management."""

from __future__ import annotations

import json

from config import KNOWLEDGE_BASE_DIR, KNOWLEDGE_INDEX_DIR, MODE_KNOWLEDGE_BASES
from knowledge.loader import KnowledgeLoadError, load_documents, load_manifest
from roles.registry import list_roles


def list_catalog() -> list[dict]:
    """List configured and discovered bases without changing local data."""
    bindings: dict[str, list[str]] = {}
    for mode, base_id in MODE_KNOWLEDGE_BASES.items():
        if base_id:
            bindings.setdefault(base_id, []).append(f"mode:{mode}")
    for role in list_roles():
        base_id = role.roleplay.knowledge_base_id
        if base_id:
            bindings.setdefault(base_id, []).append(f"role:{role.id}")
    if KNOWLEDGE_BASE_DIR.is_dir():
        for path in KNOWLEDGE_BASE_DIR.iterdir():
            if path.is_dir():
                bindings.setdefault(path.name, [])
    return [_summary(base_id, sorted(bound_to)) for base_id, bound_to in sorted(bindings.items())]


def get_catalog_entry(base_id: str) -> dict:
    """Return one safe detailed base view, raising KeyError when unknown."""
    for entry in list_catalog():
        if entry["id"] == base_id:
            return entry
    raise KeyError(base_id)


def _summary(base_id: str, bound_to: list[str]) -> dict:
    try:
        manifest = load_manifest(base_id)
        documents = load_documents(base_id) if manifest else []
    except KnowledgeLoadError as error:
        return {"id": base_id, "display_name": base_id, "bound_to": bound_to, "document_count": 0, "index_entry_count": 0, "status": "invalid", "error": str(error), "documents": []}
    index_path = KNOWLEDGE_INDEX_DIR / f"{base_id}.json"
    index_entries = 0
    if index_path.is_file():
        try:
            raw = json.loads(index_path.read_text(encoding="utf-8"))
            index_entries = len(raw.get("entries", {})) if isinstance(raw, dict) and isinstance(raw.get("entries"), dict) else 0
        except (OSError, json.JSONDecodeError):
            pass
    status = "ready" if manifest and index_path.is_file() else "not_built"
    return {
        "id": base_id,
        "display_name": manifest.display_name if manifest else base_id,
        "bound_to": bound_to,
        "document_count": len(documents),
        "index_entry_count": index_entries,
        "status": status,
        "error": None,
        "documents": [{"id": item.parent_id or item.id, "title": item.title or item.id, "source": item.source or None, "tags": list(item.tags)} for item in documents],
    }
