"""Schema for source-aware, human-authored roleplay scene cards."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import Any


EVIDENCE_SCHEMA_VERSION = 4
_ROLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_ENTRY_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_LINE_KINDS = frozenset({"dialogue", "narration", "annotation"})
_LINE_SOURCES = frozenset({"raw", "annotated"})
_REVIEW_STATUSES = frozenset({"draft", "reviewed"})
_TRAJECTORY_MODES = frozenset({"sequential", "independent"})
_SOURCE_SUFFIXES = frozenset({".json", ".yml", ".yaml", ".txt"})


class RoleplayEvidenceError(ValueError):
    """Raised when a scene-card evidence entry is malformed or unsafe."""


@dataclass(frozen=True)
class SourceReference:
    """Portable source identifier retained at scene-card granularity."""

    source_id: str


@dataclass(frozen=True)
class SceneCardLine:
    """One human-readable scene-card line, raw source text or a marked note."""

    speaker: str
    kind: str
    source: str
    text: str
    sticker_id: str | None = None


@dataclass(frozen=True)
class RoleplayEvidenceEntry:
    """A complete small scene, with target dialogue and context kept together."""

    schema_version: int
    id: str
    role_id: str
    scene: str
    source_refs: tuple[SourceReference, ...]
    lines: tuple[SceneCardLine, ...]
    sticker_ids: tuple[str, ...]
    review_status: str
    trajectory_id: str
    trajectory_order: int
    trajectory_mode: str
    relationship_context: str | None = None
    transfer_limits: tuple[str, ...] = ()
    source_mode: str | None = None
    relation_floor: float = 0.0
    affection_expression: float = 0.0

    @classmethod
    def from_mapping(cls, data: object) -> "RoleplayEvidenceEntry":
        """Validate one converted scene-card JSONL object."""
        root = _mapping(data, "entry")
        version = _required_int(root, "schema_version")
        if version not in {3, EVIDENCE_SCHEMA_VERSION}:
            raise RoleplayEvidenceError(
                f"schema_version: expected 3 or {EVIDENCE_SCHEMA_VERSION}, received {version}"
            )
        entry_id = _required_str(root, "id")
        if not _ENTRY_ID_PATTERN.fullmatch(entry_id):
            raise RoleplayEvidenceError("id: use letters, digits, dot, underscore, or hyphen")
        role_id = _required_str(root, "role_id")
        validate_role_id(role_id)
        lines = _lines(_required(root, "lines"))
        source_refs = _source_refs(_required(root, "source_refs"))
        if not any(line.speaker == role_id and line.source == "raw" for line in lines):
            raise RoleplayEvidenceError("lines: expected at least one raw line spoken by role_id")
        review_status = _required_str(root, "review_status")
        if review_status not in _REVIEW_STATUSES:
            raise RoleplayEvidenceError(
                f"review_status: expected one of {', '.join(sorted(_REVIEW_STATUSES))}"
            )
        return cls(
            schema_version=version,
            id=entry_id,
            role_id=role_id,
            scene=_required_str(root, "scene"),
            source_refs=source_refs,
            lines=lines,
            sticker_ids=_sticker_ids(root.get("sticker_ids", [])),
            review_status=review_status,
            # v3 evidence remains readable.  Its source document is the only
            # safe trajectory identity available, and source-file order is
            # reconstructed deterministically by the loader when possible.
            trajectory_id=_optional_trajectory_id(root.get("trajectory_id"), source_refs=source_refs),
            trajectory_order=_optional_trajectory_order(root.get("trajectory_order")),
            trajectory_mode=_optional_trajectory_mode(root.get("trajectory_mode")),
            relationship_context=_optional_text(root.get("relationship_context"), "relationship_context"),
            transfer_limits=_optional_text_list(root.get("transfer_limits"), "transfer_limits"),
            source_mode=_optional_text(root.get("source_mode"), "source_mode"),
            relation_floor=_relation_floor(root.get("relation_floor", 0.0)),
            affection_expression=_affection_expression(root.get("affection_expression", 0.0)),
        )

    def searchable_text(self) -> str:
        """Return all scene text for semantic scenario retrieval."""
        return "\n".join(line.text for line in self.lines)

    def target_text(self) -> str:
        """Return only raw lines spoken by the target role for prompt examples."""
        return "\n".join(
            line.text for line in self.lines if line.speaker == self.role_id and line.source == "raw"
        )


def validate_role_id(role_id: str) -> None:
    """Validate a role identifier before using it in an evidence path."""
    if not _ROLE_ID_PATTERN.fullmatch(role_id):
        raise ValueError("role_id must contain lowercase letters, digits, and underscores")


def _relation_floor(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or not 0.0 <= value <= 1.0:
        raise RoleplayEvidenceError("relation_floor: expected a finite number from 0.0 to 1.0")
    return float(value)


def _affection_expression(value: object) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or not -1.0 <= value <= 1.0:
        raise RoleplayEvidenceError("affection_expression: expected a finite number from -1.0 to 1.0")
    return float(value)


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RoleplayEvidenceError(f"{field}: expected an object")
    return value


def _required(data: dict[str, Any], key: str, prefix: str = "") -> object:
    if key not in data:
        field = f"{prefix}.{key}" if prefix else key
        raise RoleplayEvidenceError(f"{field}: required field is missing")
    return data[key]


def _required_str(data: dict[str, Any], key: str, prefix: str = "") -> str:
    field = f"{prefix}.{key}" if prefix else key
    value = _required(data, key, prefix)
    if not isinstance(value, str) or not value.strip():
        raise RoleplayEvidenceError(f"{field}: expected a non-empty string")
    return value.strip()


def _required_int(data: dict[str, Any], key: str) -> int:
    value = _required(data, key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RoleplayEvidenceError(f"{key}: expected an integer")
    return value


def _optional_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RoleplayEvidenceError(f"{field}: expected a non-empty string")
    return value.strip()


def _optional_text_list(value: object, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise RoleplayEvidenceError(f"{field}: expected a list of non-empty strings")
    items = tuple(item.strip() for item in value)
    if len(set(items)) != len(items):
        raise RoleplayEvidenceError(f"{field}: duplicate entry")
    return items


def _source_refs(value: object) -> tuple[SourceReference, ...]:
    if not isinstance(value, list) or not value:
        raise RoleplayEvidenceError("source_refs: expected a non-empty list")
    refs: list[SourceReference] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        source = _mapping(item, f"source_refs[{index}]")
        source_id = _source_id(_required_str(source, "source_id", f"source_refs[{index}]"))
        if source_id in seen:
            raise RoleplayEvidenceError(f"source_refs[{index}].source_id: duplicate source")
        seen.add(source_id)
        refs.append(SourceReference(source_id=source_id))
    return tuple(refs)


def _lines(value: object) -> tuple[SceneCardLine, ...]:
    if not isinstance(value, list) or not value:
        raise RoleplayEvidenceError("lines: expected a non-empty list")
    lines: list[SceneCardLine] = []
    for index, item in enumerate(value):
        line = _mapping(item, f"lines[{index}]")
        kind = _required_str(line, "kind", f"lines[{index}]")
        if kind not in _LINE_KINDS:
            raise RoleplayEvidenceError(
                f"lines[{index}].kind: expected one of {', '.join(sorted(_LINE_KINDS))}"
            )
        source = _required_str(line, "source", f"lines[{index}]")
        if source not in _LINE_SOURCES:
            raise RoleplayEvidenceError(
                f"lines[{index}].source: expected one of {', '.join(sorted(_LINE_SOURCES))}"
            )
        lines.append(
            SceneCardLine(
                speaker=_required_str(line, "speaker", f"lines[{index}]"),
                kind=kind,
                source=source,
                text=_required_str(line, "text", f"lines[{index}]"),
                sticker_id=_optional_sticker_id(line, f"lines[{index}]"),
            )
        )
    return tuple(lines)


def _optional_sticker_id(data: dict[str, Any], prefix: str) -> str | None:
    """Read an optional per-line sticker reference while retaining v3 compatibility."""
    value = data.get("sticker_id")
    if value is None:
        return None
    if not isinstance(value, str) or not _ROLE_ID_PATTERN.fullmatch(value):
        raise RoleplayEvidenceError(f"{prefix}.sticker_id: use lowercase letters, digits, and underscores")
    return value


def _sticker_ids(value: object) -> tuple[str, ...]:
    """Read optional stable sticker identifiers without binding evidence to one pack."""
    if not isinstance(value, list):
        raise RoleplayEvidenceError("sticker_ids: expected a list")
    sticker_ids: list[str] = []
    seen: set[str] = set()
    for index, sticker_id in enumerate(value):
        if not isinstance(sticker_id, str) or not _ROLE_ID_PATTERN.fullmatch(sticker_id):
            raise RoleplayEvidenceError(
                f"sticker_ids[{index}]: use lowercase letters, digits, and underscores"
            )
        if sticker_id in seen:
            raise RoleplayEvidenceError(f"sticker_ids[{index}]: duplicate sticker ID")
        seen.add(sticker_id)
        sticker_ids.append(sticker_id)
    return tuple(sticker_ids)


def _source_id(value: str) -> str:
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    suffix = normalized.rsplit("/", maxsplit=1)[-1].lower()
    suffix = suffix[suffix.rfind(".") :] if "." in suffix else ""
    if (
        suffix not in _SOURCE_SUFFIXES
        or any(part in {"", ".", ".."} for part in parts)
        or normalized.startswith("/")
        or ":" in normalized
    ):
        allowed = ", ".join(sorted(_SOURCE_SUFFIXES))
        raise RoleplayEvidenceError(
            f"source_refs.source_id: expected a safe relative source path ({allowed})"
        )
    return normalized


def _optional_trajectory_id(value: object, *, source_refs: tuple[SourceReference, ...]) -> str:
    """Read stable trajectory metadata while deriving a safe legacy default."""
    if value is None:
        return source_refs[0].source_id
    if not isinstance(value, str) or not value.strip() or not _ENTRY_ID_PATTERN.fullmatch(value.strip()):
        raise RoleplayEvidenceError("trajectory_id: use letters, digits, dot, underscore, or hyphen")
    return value.strip()


def _optional_trajectory_order(value: object) -> int:
    """Read an optional positive ordinal; the loader fills legacy ordering."""
    if value is None:
        return 0
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RoleplayEvidenceError("trajectory_order: expected a positive integer")
    return value


def _optional_trajectory_mode(value: object) -> str:
    """Read trajectory topology, retaining sequential behavior for old cards."""
    if value is None:
        return "sequential"
    if not isinstance(value, str) or value not in _TRAJECTORY_MODES:
        raise RoleplayEvidenceError("trajectory_mode: expected sequential or independent")
    return value
