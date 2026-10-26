"""Semantic retrieval for isolated local knowledge bases."""

from __future__ import annotations

from dataclasses import dataclass

from knowledge import index
from knowledge.schema import KnowledgeDocument
from memory.embedder import Embedder, Embedding
from memory.local_embedder import get_local_embedder


@dataclass(frozen=True)
class RetrievedKnowledge:
    """One ranked knowledge document with its similarity score."""

    document: KnowledgeDocument
    score: float


def retrieval_text(document: KnowledgeDocument) -> str:
    """Return all semantic fields while keeping the raw body intact."""
    parts = [document.title, document.source, " ".join(document.tags), document.text]
    return "\n".join(part for part in parts if part).strip()


def retrieve(
    query: str,
    documents: list[KnowledgeDocument],
    *,
    embedder: Embedder | None = None,
    limit: int = 3,
    min_score: float = 0.30,
) -> list[RetrievedKnowledge]:
    """Rank sources without a persistent cache (offline fallback)."""
    if not query.strip() or limit <= 0:
        return []
    provider = embedder or get_local_embedder()
    query_vector = provider.embed(query)
    ranked = [RetrievedKnowledge(document, _cosine_similarity(query_vector, provider.embed(retrieval_text(document)))) for document in documents]
    return _top_results(ranked, limit=limit, min_score=min_score)


def retrieve_indexed(
    base_id: str,
    query: str,
    documents: list[KnowledgeDocument],
    *,
    embedder: Embedder,
    limit: int = 3,
    min_score: float = 0.30,
) -> list[RetrievedKnowledge]:
    """Retrieve with an incremental local vector cache tied to ``model_id``."""
    if not query.strip() or limit <= 0:
        return []
    model_id = getattr(embedder, "model_id", None)
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("indexed knowledge retrieval requires an embedder with a model_id")
    document_by_id = {document.id: document for document in documents}
    if len(document_by_id) != len(documents):
        raise ValueError("knowledge document IDs must be unique")

    record = index.load(base_id, model_id)
    entries = record["entries"]
    expected_ids = set(document_by_id)
    changed = False
    if set(entries) != expected_ids:
        record["entries"] = {document_id: entry for document_id, entry in entries.items() if document_id in expected_ids}
        entries = record["entries"]
        changed = True
    missing = [document for document in documents if entries.get(document.id, {}).get("fingerprint") != index.fingerprint(retrieval_text(document))]
    if missing:
        vectors = embedder.embed_many([retrieval_text(document) for document in missing])
        if len(vectors) != len(missing):
            raise ValueError("embedder returned an unexpected number of document vectors")
        for document, vector in zip(missing, vectors):
            entries[document.id] = {"fingerprint": index.fingerprint(retrieval_text(document)), "vector": vector}
        changed = True
    if changed:
        index.save(base_id, record)

    query_vector = embedder.embed(query)
    ranked = [RetrievedKnowledge(document, _cosine_similarity(query_vector, entries[document.id]["vector"])) for document in documents]
    return _top_results(ranked, limit=limit, min_score=min_score)


def _top_results(results: list[RetrievedKnowledge], *, limit: int, min_score: float) -> list[RetrievedKnowledge]:
    return sorted((item for item in results if item.score >= min_score), key=lambda item: item.score, reverse=True)[:limit]


def _cosine_similarity(left: Embedding, right: Embedding) -> float:
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same length")
    return sum(left_value * right_value for left_value, right_value in zip(left, right))
