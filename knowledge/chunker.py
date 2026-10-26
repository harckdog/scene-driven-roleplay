"""Paragraph-aware deterministic chunking for long local source documents."""

from __future__ import annotations

from dataclasses import replace
import re

from knowledge.schema import KnowledgeDocument


def chunk_documents(documents: list[KnowledgeDocument], *, max_chars: int, overlap_chars: int) -> list[KnowledgeDocument]:
    """Split long documents while preserving parent identity and source metadata."""
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("chunk settings require 0 <= overlap_chars < max_chars")
    return [chunk for document in documents for chunk in chunk_document(document, max_chars=max_chars, overlap_chars=overlap_chars)]


def chunk_document(document: KnowledgeDocument, *, max_chars: int, overlap_chars: int) -> list[KnowledgeDocument]:
    if len(document.text) <= max_chars:
        return [replace(document, parent_id=document.parent_id or document.id, chunk_index=1, chunk_count=1)]
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", document.text) if part.strip()]
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(_hard_chunks(paragraph, max_chars=max_chars, overlap_chars=overlap_chars))
        elif not current:
            current = paragraph
        elif len(current) + 2 + len(paragraph) <= max_chars:
            current += "\n\n" + paragraph
        else:
            pieces.append(current)
            current = paragraph
    if current:
        pieces.append(current)
    count = len(pieces)
    return [replace(document, id=f"{document.id}-chunk-{number:03d}", text=text, parent_id=document.id, chunk_index=number, chunk_count=count) for number, text in enumerate(pieces, start=1)]


def _hard_chunks(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    step = max_chars - overlap_chars
    return [text[start:start + max_chars] for start in range(0, len(text), step)]
