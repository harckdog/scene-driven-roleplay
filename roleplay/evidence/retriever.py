"""Semantic retrieval over local, source-aware roleplay scene cards."""

from __future__ import annotations

from dataclasses import dataclass

from memory.embedder import Embedder, Embedding
from roleplay.evidence import index
from roleplay.evidence.schema import RoleplayEvidenceEntry


@dataclass(frozen=True)
class RetrievedSceneCard:
    """One semantically relevant scene card with its normalized similarity score."""

    card: RoleplayEvidenceEntry
    score: float


def retrieval_text(
    card: RoleplayEvidenceEntry,
) -> str:
    """Build R1 retrieval text from scene context and raw performance text.

    Sticker semantics are resolved only after recall, preventing affect labels
    from becoming a shortcut into the candidate set.
    """
    raw_context = "\n".join(line.text for line in card.lines if line.source == "raw")
    parts = [
        f"场景：{card.scene}",
        f"轨迹：{card.trajectory_id} / {card.trajectory_order} / {card.trajectory_mode}",
        f"关系语境：{card.relationship_context}" if card.relationship_context else "",
        raw_context,
    ]
    return "\n".join(part for part in parts if part).strip()


def retrieve_indexed(
    role_id: str,
    query: str,
    cards: list[RoleplayEvidenceEntry],
    *,
    embedder: Embedder,
    limit: int = 3,
    min_score: float = 0.30,
) -> list[RetrievedSceneCard]:
    """Retrieve role-isolated scene cards with an incremental local vector cache.

    Only changed cards are embedded again. A model-ID change invalidates all
    existing vectors, preventing incompatible embedding spaces from mixing.
    """
    if not query.strip() or limit <= 0:
        return []
    model_id = getattr(embedder, "model_id", None)
    if not isinstance(model_id, str) or not model_id:
        raise ValueError("indexed scene-card retrieval requires an embedder with a model_id")

    cards_by_id = {card.id: card for card in cards}
    if len(cards_by_id) != len(cards):
        raise ValueError("scene-card IDs must be unique before retrieval")
    record = index.load(role_id, model_id)
    entries = record["entries"]
    changed = False
    expected_ids = set(cards_by_id)
    if set(entries) != expected_ids:
        record["entries"] = {card_id: entry for card_id, entry in entries.items() if card_id in expected_ids}
        entries = record["entries"]
        changed = True

    missing: list[RoleplayEvidenceEntry] = []
    for card in cards:
        card_fingerprint = index.fingerprint(retrieval_text(card))
        cached = entries.get(card.id)
        if not isinstance(cached, dict) or cached.get("fingerprint") != card_fingerprint:
            missing.append(card)

    if missing:
        vectors = embedder.embed_many([retrieval_text(card) for card in missing])
        if len(vectors) != len(missing):
            raise ValueError("embedder returned an unexpected number of scene-card vectors")
        for card, vector in zip(missing, vectors):
            entries[card.id] = {
                "fingerprint": index.fingerprint(retrieval_text(card)),
                "vector": vector,
            }
        changed = True
    if changed:
        index.save(role_id, record)

    query_embedding = embedder.embed(query)
    ranked = [
        RetrievedSceneCard(card=card, score=_cosine_similarity(query_embedding, entries[card.id]["vector"]))
        for card in cards
    ]
    ranked = sorted(
        (item for item in ranked if item.score >= min_score),
        key=lambda item: item.score,
        reverse=True,
    )
    return ranked[:limit]


def _cosine_similarity(left: Embedding, right: Embedding) -> float:
    """Calculate cosine similarity between two normalized dense vectors."""
    if len(left) != len(right):
        raise ValueError("embedding vectors must have the same length")
    return sum(left_value * right_value for left_value, right_value in zip(left, right))
