"""Stable, retrieval-only view of a validated Scene Card."""

from __future__ import annotations

from dataclasses import dataclass

from roleplay.evidence.schema import RoleplayEvidenceEntry


@dataclass(frozen=True)
class SceneDialogueLine:
    speaker: str
    text: str


@dataclass(frozen=True)
class SceneCard:
    scene_id: str
    scene: str
    relationship_context: str | None
    dialogue: tuple[SceneDialogueLine, ...]
    source: str
    source_mode: str | None

    @classmethod
    def from_entry(cls, entry: RoleplayEvidenceEntry) -> "SceneCard":
        """Keep only authored fields; stickers and inferred labels never enter ranking."""
        return cls(
            scene_id=entry.id,
            scene=entry.scene,
            relationship_context=entry.relationship_context,
            dialogue=tuple(
                SceneDialogueLine(line.speaker, line.text)
                for line in entry.lines if line.source == "raw"
            ),
            source=entry.source_refs[0].source_id,
            source_mode=entry.source_mode,
        )

    def reranker_document(self) -> str:
        """Render interaction evidence without inventing affect or behavior tags."""
        lines = ["[Scene]", self.scene]
        if self.relationship_context:
            lines.extend(("[Relationship Context]", self.relationship_context))
        lines.extend(("[Dialogue]", *(f"{line.speaker}: {line.text}" for line in self.dialogue)))
        return "\n".join(lines)
