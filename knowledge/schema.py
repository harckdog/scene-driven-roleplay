"""Typed, conservative schema for local knowledge-base documents."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class KnowledgeSchemaError(ValueError):
    """Raised when local knowledge-base metadata is invalid."""


def validate_knowledge_base_id(value: object) -> str:
    """Validate an ID used as a local directory and index filename."""
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise KnowledgeSchemaError(
            "knowledge base id must use lowercase letters, digits, '_' or '-', "
            "start with a letter, and be at most 64 characters"
        )
    return value


@dataclass(frozen=True)
class KnowledgeBaseManifest:
    """Public metadata for one independently indexed local knowledge base."""

    id: str
    display_name: str
    description: str = ""
    schema_version: int = 1

    @classmethod
    def from_mapping(cls, raw: object) -> "KnowledgeBaseManifest":
        if not isinstance(raw, dict):
            raise KnowledgeSchemaError("manifest must be a JSON object")
        version = raw.get("schema_version", 1)
        if version != 1:
            raise KnowledgeSchemaError("manifest.schema_version must be 1")
        base_id = validate_knowledge_base_id(raw.get("id"))
        display_name = _required_text(raw.get("display_name"), "manifest.display_name")
        description = _optional_text(raw.get("description"), "manifest.description")
        return cls(id=base_id, display_name=display_name, description=description)


@dataclass(frozen=True)
class KnowledgeDocument:
    """One source unit that can later be embedded and retrieved as a whole."""

    id: str
    text: str
    title: str = ""
    source: str = ""
    tags: tuple[str, ...] = ()
    parent_id: str | None = None
    chunk_index: int = 1
    chunk_count: int = 1

    @classmethod
    def from_mapping(cls, raw: object, *, location: str) -> "KnowledgeDocument":
        if not isinstance(raw, dict):
            raise KnowledgeSchemaError(f"{location}: document must be a JSON object")
        document_id = _required_id(raw.get("id"), f"{location}.id")
        text = _required_text(raw.get("text"), f"{location}.text")
        title = _optional_text(raw.get("title"), f"{location}.title")
        source = _optional_text(raw.get("source"), f"{location}.source")
        raw_tags: Any = raw.get("tags", [])
        if not isinstance(raw_tags, list) or not all(isinstance(tag, str) and tag.strip() for tag in raw_tags):
            raise KnowledgeSchemaError(f"{location}.tags must be an array of non-empty strings")
        return cls(id=document_id, text=text, title=title, source=source, tags=tuple(tag.strip() for tag in raw_tags))


def _required_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise KnowledgeSchemaError(f"{field} must be a lowercase identifier")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeSchemaError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: object, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise KnowledgeSchemaError(f"{field} must be a string")
    return value.strip()
