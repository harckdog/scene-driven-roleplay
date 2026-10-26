"""Explicit write operations for JSONL knowledge documents and vector caches."""
from __future__ import annotations

import json
from pathlib import Path

from config import EMBEDDING_DEVICE, KNOWLEDGE_CHUNK_MAX_CHARS, KNOWLEDGE_CHUNK_OVERLAP_CHARS, LOCAL_EMBEDDING_MODEL_DIR
from knowledge.chunker import chunk_documents
from knowledge.index import index_path
from knowledge.loader import KnowledgeLoadError, knowledge_base_path, load_documents, load_manifest
from knowledge.retriever import retrieve_indexed
from knowledge.schema import KnowledgeDocument, KnowledgeSchemaError
from memory.embedder import SentenceTransformerEmbedder


def add_jsonl_document(base_id: str, raw: dict) -> KnowledgeDocument:
    manifest = load_manifest(base_id)
    if manifest is None:
        raise KnowledgeLoadError(f"knowledge base '{base_id}' has no manifest")
    document = KnowledgeDocument.from_mapping(raw, location="request")
    existing = load_documents(base_id)
    if any(item.id == document.id for item in existing):
        raise KnowledgeLoadError(f"document id already exists: {document.id}")
    path = knowledge_base_path(base_id) / "documents.jsonl"
    needs_leading_newline = path.is_file() and path.stat().st_size > 0 and not path.read_bytes().endswith((b"\n", b"\r"))
    with path.open("a", encoding="utf-8", newline="\n") as file:
        if needs_leading_newline:
            file.write("\n")
        file.write(json.dumps(raw, ensure_ascii=False) + "\n")
    return document


def delete_jsonl_document(base_id: str, document_id: str) -> bool:
    path = knowledge_base_path(base_id) / "documents.jsonl"
    if not path.is_file():
        return False
    kept: list[str] = []
    removed = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise KnowledgeLoadError(f"{path}: invalid JSONL ({error})") from error
        if raw.get("id") == document_id:
            removed = True
        else:
            kept.append(json.dumps(raw, ensure_ascii=False))
    if removed:
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return removed


def rebuild_index(base_id: str) -> int:
    documents = chunk_documents(load_documents(base_id), max_chars=KNOWLEDGE_CHUNK_MAX_CHARS, overlap_chars=KNOWLEDGE_CHUNK_OVERLAP_CHARS)
    if not LOCAL_EMBEDDING_MODEL_DIR.is_dir():
        raise FileNotFoundError(f"local embedding model was not found: {LOCAL_EMBEDDING_MODEL_DIR}")
    path = index_path(base_id)
    if path.is_file(): path.unlink()
    if not documents: return 0
    embedder = SentenceTransformerEmbedder(LOCAL_EMBEDDING_MODEL_DIR, device=EMBEDDING_DEVICE)
    retrieve_indexed(base_id, "index rebuild", documents, embedder=embedder, min_score=2.0)
    return len(documents)
