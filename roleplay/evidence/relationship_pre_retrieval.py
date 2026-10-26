"""Relationship-aware rescoring of dense Scene candidates."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from roleplay.evidence.retriever import RetrievedSceneCard
from roleplay.evidence.schema import RoleplayEvidenceEntry


@dataclass(frozen=True)
class RelationshipScoredScene:
    card: RoleplayEvidenceEntry
    semantic_score: float
    relation_floor: float
    affection_expression: float
    relationship_level: float
    relation_gap: float
    floor_penalty: float
    activation: float
    positive_bonus: float
    defensive_penalty: float
    pre_retrieval_score: float


def rescore_relationship_candidates(
    candidates: Sequence[RetrievedSceneCard],
    *,
    relationship_level: float,
    lambda_floor: float,
    beta_pos: float = 0.0,
    beta_neg: float = 0.0,
    activation_start: float = 0.5,
) -> list[RelationshipScoredScene]:
    """Rescore by floor eligibility and the Scene's expression of affection."""
    if not isinstance(relationship_level, (int, float)) or isinstance(relationship_level, bool) or not isfinite(relationship_level):
        raise ValueError("relationship_level must be a finite number")
    for name, value in (("lambda_floor", lambda_floor), ("beta_pos", beta_pos), ("beta_neg", beta_neg)):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a finite non-negative number")
    if not isinstance(activation_start, (int, float)) or isinstance(activation_start, bool) or not isfinite(activation_start) or not 0 <= activation_start < 1:
        raise ValueError("activation_start must be from 0.0 up to but not including 1.0")
    level = min(1.0, max(0.0, float(relationship_level)))
    activation = max(0.0, (level - activation_start) / (1.0 - activation_start))
    ranked = []
    for item in candidates:
        floor = item.card.relation_floor
        affection = item.card.affection_expression
        gap = max(0.0, floor - level)
        floor_penalty = float(lambda_floor) * gap
        positive_bonus = float(beta_pos) * activation * max(affection, 0.0) if floor <= level else 0.0
        defensive_penalty = float(beta_neg) * activation * max(-affection, 0.0)
        ranked.append(RelationshipScoredScene(
            card=item.card,
            semantic_score=item.score,
            relation_floor=floor,
            affection_expression=affection,
            relationship_level=level,
            relation_gap=gap,
            floor_penalty=floor_penalty,
            activation=activation,
            positive_bonus=positive_bonus,
            defensive_penalty=defensive_penalty,
            pre_retrieval_score=item.score - floor_penalty + positive_bonus - defensive_penalty,
        ))
    return sorted(ranked, key=lambda item: item.pre_retrieval_score, reverse=True)
