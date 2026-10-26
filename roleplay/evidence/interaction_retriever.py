"""Full-scene interaction-aware retrieval, independent of generation prompts."""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Protocol, Sequence

from roleplay.evidence.retriever import RetrievedSceneCard
from roleplay.evidence.scene_view import SceneCard
from roleplay.evidence.schema import RoleplayEvidenceEntry


class SceneScorer(Protocol):
    def score(self, query: str, documents: Sequence[str]) -> list[float]: ...


def interaction_query(
    history: Sequence[dict[str, Any]],
    current_user_text: str,
    *,
    character_name: str,
    user_role: str,
    recent_turns: int = 3,
) -> str:
    """Keep the last complete social turns without State or generated labels."""
    if recent_turns < 1:
        raise ValueError("recent_turns must be positive")
    user_positions = [index for index, item in enumerate(history) if item.get("role") == "user"]
    start = user_positions[-min(recent_turns, len(user_positions))] if user_positions else len(history)
    recent: list[str] = []
    for item in history[start:]:
        role = item.get("role")
        if role not in {"user", "assistant"} or item.get("event_type") == "reminder":
            continue
        content = item.get("content")
        text = content.get("text") if isinstance(content, dict) else content
        if isinstance(text, str) and text.strip():
            label = user_role if role == "user" else character_name
            recent.append(f"{label}: {text.strip()[:300]}")
    return "\n".join((
        "[Recent Dialogue]", *recent,
        "[Current User Turn]", current_user_text.strip(),
        "[Minimal Current Context]", f"Character: {character_name}; user: {user_role}.",
    ))


def rank_all_scenes(
    cards: Sequence[RoleplayEvidenceEntry],
    query: str,
    *,
    scorer: SceneScorer,
    limit: int,
    documents_by_id: Mapping[str, str] | None = None,
) -> list[RetrievedSceneCard]:
    """Score every Scene once, then return the highest-ranked original cards."""
    if not query.strip() or limit <= 0 or not cards:
        return []
    if documents_by_id is None:
        documents = [SceneCard.from_entry(card).reranker_document() for card in cards]
    else:
        try:
            documents = [documents_by_id[card.id] for card in cards]
        except KeyError as error:
            raise ValueError(f"missing reranker document for Scene {error.args[0]}") from error
        if any(not isinstance(document, str) or not document.strip() for document in documents):
            raise ValueError("reranker documents must be nonempty strings")
    scores = scorer.score(query, documents)
    if len(scores) != len(cards) or any(
        not isinstance(score, (int, float)) or isinstance(score, bool) or not isfinite(score)
        for score in scores
    ):
        raise ValueError("scene reranker returned invalid scores")
    ranked = sorted(
        (RetrievedSceneCard(card, float(score)) for card, score in zip(cards, scores)),
        key=lambda item: item.score,
        reverse=True,
    )
    return ranked[:limit]
