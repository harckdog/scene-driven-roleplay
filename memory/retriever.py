"""Ranking logic for relevant long-term memories."""

from __future__ import annotations

from dataclasses import dataclass

from memory.embedder import Embedder, Embedding
from memory.local_embedder import get_local_embedder
from memory.index import (
    fingerprint,
    load as load_index,
    remove_missing,
    save as save_index,
    upsert,
)


@dataclass(frozen=True)
class RetrievedMemory:
    """A memory selected for use in the current conversation."""

    content: str
    score: float


def retrieve(
    query: str,
    memories: list[str],
    *,
    embedder: Embedder | None = None,
    limit: int = 5,
    min_score: float = 0.30,
) -> list[RetrievedMemory]:
    """Return the most relevant memories for a question.

    Args:
        query: Current user message.
        memories: Stable memories associated with the active mode.
        embedder: Embedding implementation to use. Defaults to the deployed local model.
        limit: Maximum number of returned memories.
        min_score: Inclusive similarity threshold.

    Returns:
        Memories sorted from most to least relevant.
    """
    if not query.strip() or limit <= 0:
        return []

    provider = embedder or get_local_embedder()
    query_embedding = provider.embed(query)
    ranked = [
        RetrievedMemory(content=memory, score=_cosine_similarity(query_embedding, provider.embed(memory)))
        for memory in memories
        if memory.strip()
    ]
    return sorted(
        (item for item in ranked if item.score >= min_score),
        key=lambda item: item.score,
        reverse=True,
    )[:limit]


def retrieve_indexed(
    mode: str,
    query: str,
    memories: list[str],
    *,
    embedder: Embedder,
    limit: int = 5,
    min_score: float = 0.30,
) -> list[RetrievedMemory]:
    """Retrieve memories with a persistent dense-vector index.

    Only missing memory vectors are generated. Vectors are invalidated when the
    active embedding model identifier changes.

    Args:
        mode: Conversation mode.
        query: Current user message.
        memories: Stable memories associated with the mode.
        embedder: Local dense-vector embedding provider.
        limit: Maximum number of returned memories.
        min_score: Inclusive similarity threshold.

    Returns:
        Memories sorted from most to least relevant.

    Raises:
        ValueError: If the provider has no stable ``model_id`` attribute.
    """
    if not query.strip() or limit <= 0:
        return []

    model_id = getattr(embedder, "model_id", None)
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("indexed retrieval requires an embedder with a model_id")

    valid_memories = [memory for memory in memories if memory.strip()]
    index = load_index(mode, model_id)
    original_keys = set(index["entries"])
    remove_missing(index, valid_memories)

    missing_memories = [
        memory
        for memory in valid_memories
        if fingerprint(memory) not in index["entries"]
    ]
    if missing_memories:
        for memory, vector in zip(missing_memories, embedder.embed_many(missing_memories)):
            upsert(index, memory, vector)

    if missing_memories or original_keys != set(index["entries"]):
        save_index(mode, index)

    query_embedding = embedder.embed(query)
    ranked = [
        RetrievedMemory(
            content=memory,
            score=_cosine_similarity(query_embedding, index["entries"][fingerprint(memory)]["vector"]),
        )
        for memory in valid_memories
    ]
    return sorted(
        (item for item in ranked if item.score >= min_score),
        key=lambda item: item.score,
        reverse=True,
    )[:limit]


def _cosine_similarity(left: Embedding, right: Embedding) -> float:
    """Calculate cosine similarity between equal-length vectors."""
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same length")
    return sum(left_value * right_value for left_value, right_value in zip(left, right))
