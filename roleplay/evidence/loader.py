"""Load local roleplay scene-card evidence without legacy schema support."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from roleplay.evidence.schema import (
    RoleplayEvidenceEntry,
    RoleplayEvidenceError,
    validate_role_id,
)


PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_EVIDENCE_DIR = PROJECT_DIR / "local_data" / "roleplay_evidence"


class RoleplayEvidenceLoadError(ValueError):
    """Raised when a local scene-card JSONL file cannot be parsed or validated."""


def evidence_path(role_id: str, *, directory: str | Path = DEFAULT_EVIDENCE_DIR) -> Path:
    """Return the JSONL path for one validated role's scene cards."""
    validate_role_id(role_id)
    return Path(directory) / f"{role_id}.jsonl"


def load_evidence(
    role_id: str,
    *,
    evidence_directory: str | Path = DEFAULT_EVIDENCE_DIR,
) -> list[RoleplayEvidenceEntry]:
    """Load one role's v3 scene cards in stable source-file order.

    The card stores its own selected source text for readability and flexible
    scene composition. ``source_refs`` remain provenance metadata; this loader
    deliberately does not impose v2's index-by-index text equality requirement.
    """
    path = evidence_path(role_id, directory=evidence_directory)
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RoleplayEvidenceLoadError(f"{path}: could not read evidence ({error})") from error

    entries: list[RoleplayEvidenceEntry] = []
    seen_ids: set[str] = set()
    next_orders: dict[str, int] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise RoleplayEvidenceLoadError(
                f"{path}:{line_number}: invalid JSON ({error.msg})"
            ) from error
        try:
            entry = RoleplayEvidenceEntry.from_mapping(raw)
        except RoleplayEvidenceError as error:
            raise RoleplayEvidenceLoadError(f"{path}:{line_number}: {error}") from error
        if entry.id in seen_ids:
            raise RoleplayEvidenceLoadError(f"{path}:{line_number}: duplicate card id: {entry.id}")
        if entry.role_id != role_id:
            raise RoleplayEvidenceLoadError(
                f"{path}:{line_number}: role_id must match evidence file role {role_id}"
            )
        if entry.trajectory_order == 0:
            order = next_orders.get(entry.trajectory_id, 0) + 1
            entry = replace(entry, trajectory_order=order)
        next_orders[entry.trajectory_id] = max(next_orders.get(entry.trajectory_id, 0), entry.trajectory_order)
        seen_ids.add(entry.id)
        entries.append(entry)
    return entries
