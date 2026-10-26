"""Load reviewed, role-scoped interaction excerpts for Scene reranking."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from roleplay.evidence.loader import PROJECT_DIR
from roleplay.evidence.schema import RoleplayEvidenceEntry, validate_role_id


DEFAULT_TRACE_DIR = PROJECT_DIR / "local_data" / "roleplay_scene_traces"


def load_trace_documents(
    role_id: str,
    cards: Sequence[RoleplayEvidenceEntry],
    *,
    directory: Path = DEFAULT_TRACE_DIR,
) -> dict[str, str] | None:
    """Return short reranker documents, or None when this role has no trace set.

    A trace set must cover the entire current card set and match authored scene
    metadata, so a stale snapshot cannot quietly affect the ranking.
    """
    validate_role_id(role_id)
    path = directory / f"{role_id}.jsonl"
    if not path.exists():
        if role_id == "tendou_kei":
            raise FileNotFoundError(f"Kei interaction traces are missing: {path}")
        return None

    cards_by_id = {card.id: card for card in cards}
    if len(cards_by_id) != len(cards):
        raise ValueError("scene-card IDs must be unique before loading interaction traces")
    documents: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from error
        if not isinstance(entry, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        scene_id = entry.get("id")
        if not isinstance(scene_id, str) or scene_id not in cards_by_id:
            raise ValueError(f"{path}:{line_number}: unknown Scene ID {scene_id!r}")
        if scene_id in documents:
            raise ValueError(f"{path}:{line_number}: duplicate Scene ID {scene_id}")
        card = cards_by_id[scene_id]
        if entry.get("scene") != card.scene or entry.get("relationship_context") != card.relationship_context:
            raise ValueError(f"{path}:{line_number}: Scene metadata differs from current card {scene_id}")
        trace = entry.get("interaction_trace")
        if not isinstance(trace, str) or not trace.strip():
            raise ValueError(f"{path}:{line_number}: missing interaction_trace")
        parts = ["[Scene ID]", scene_id, "[Scene]", card.scene]
        if card.relationship_context:
            parts.extend(("[Relationship Context]", card.relationship_context))
        parts.extend(("[Interaction Trace]", trace.strip()))
        documents[scene_id] = "\n".join(parts)
    missing = cards_by_id.keys() - documents.keys()
    if missing:
        raise ValueError(f"{path}: missing Scene IDs {sorted(missing)}")
    return documents
