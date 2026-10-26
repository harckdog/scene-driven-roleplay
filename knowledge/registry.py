"""Resolve the optional knowledge-base binding for each conversation mode."""

from __future__ import annotations

from config import MODE_KNOWLEDGE_BASES
from knowledge.schema import validate_knowledge_base_id


def knowledge_base_for_mode(mode: str) -> str | None:
    """Return one configured base ID, or ``None`` when a mode has no base."""
    if mode not in MODE_KNOWLEDGE_BASES:
        raise KeyError(f"unknown mode: {mode}")
    base_id = MODE_KNOWLEDGE_BASES[mode]
    return validate_knowledge_base_id(base_id) if base_id is not None else None
