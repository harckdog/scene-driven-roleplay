"""Load JSONL and Markdown source documents from an isolated knowledge base."""

from __future__ import annotations

import json
from pathlib import Path

from config import KNOWLEDGE_BASE_DIR, KNOWLEDGE_INDEX_DIR
from knowledge.schema import KnowledgeBaseManifest, KnowledgeDocument, KnowledgeSchemaError, validate_knowledge_base_id


class KnowledgeLoadError(ValueError):
    """Raised when a configured local knowledge base cannot be loaded safely."""


def knowledge_base_path(base_id: str, *, directory: str | Path = KNOWLEDGE_BASE_DIR) -> Path:
    """Return the validated directory for one local knowledge base."""
    return Path(directory) / validate_knowledge_base_id(base_id)


def index_path(base_id: str) -> Path:
    """Return the future vector-index path without creating it."""
    return KNOWLEDGE_INDEX_DIR / f"{validate_knowledge_base_id(base_id)}.json"


def load_manifest(base_id: str, *, directory: str | Path = KNOWLEDGE_BASE_DIR) -> KnowledgeBaseManifest | None:
    """Load a base manifest, returning ``None`` when its directory is absent."""
    path = knowledge_base_path(base_id, directory=directory) / "manifest.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        manifest = KnowledgeBaseManifest.from_mapping(raw)
    except (OSError, json.JSONDecodeError, KnowledgeSchemaError) as error:
        raise KnowledgeLoadError(f"{path}: invalid manifest ({error})") from error
    if manifest.id != base_id:
        raise KnowledgeLoadError(f"{path}: manifest id must match directory name '{base_id}'")
    return manifest


def load_documents(base_id: str, *, directory: str | Path = KNOWLEDGE_BASE_DIR) -> list[KnowledgeDocument]:
    """Load ``documents.jsonl`` plus every ``documents/**/*.md`` file.

    An absent base is intentionally empty. Existing bases require a manifest,
    so accidental folders do not silently become model context.
    """
    base_path = knowledge_base_path(base_id, directory=directory)
    if not base_path.is_dir():
        return []
    if load_manifest(base_id, directory=directory) is None:
        raise KnowledgeLoadError(f"{base_path}: manifest.json is required")

    documents: list[KnowledgeDocument] = []
    jsonl_path = base_path / "documents.jsonl"
    if jsonl_path.is_file():
        for line_number, line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                documents.append(KnowledgeDocument.from_mapping(json.loads(line), location=f"{jsonl_path}:{line_number}"))
            except (json.JSONDecodeError, KnowledgeSchemaError) as error:
                raise KnowledgeLoadError(f"{jsonl_path}:{line_number}: invalid document ({error})") from error

    markdown_root = base_path / "documents"
    if markdown_root.is_dir():
        for markdown_path in sorted(markdown_root.rglob("*.md")):
            relative = markdown_path.relative_to(markdown_root).with_suffix("")
            document_id = "md_" + "_".join(relative.parts).lower().replace("-", "_")
            try:
                text = markdown_path.read_text(encoding="utf-8").strip()
            except OSError as error:
                raise KnowledgeLoadError(f"{markdown_path}: could not read document ({error})") from error
            if text:
                documents.append(KnowledgeDocument(id=document_id, title=markdown_path.stem, text=text, source=markdown_path.relative_to(base_path).as_posix()))

    duplicates = _duplicate_ids(documents)
    if duplicates:
        raise KnowledgeLoadError(f"{base_path}: duplicate document ids: {', '.join(sorted(duplicates))}")
    return documents


def _duplicate_ids(documents: list[KnowledgeDocument]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for document in documents:
        if document.id in seen:
            duplicates.add(document.id)
        seen.add(document.id)
    return duplicates
