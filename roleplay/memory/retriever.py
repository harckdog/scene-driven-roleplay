"""Deterministic fallback retrieval for active roleplay memories."""

from __future__ import annotations

from memory.local_embedder import get_local_embedder
from memory.retriever import retrieve

from roleplay.memory.manager import active_memories, load


def retrieve_context(role_id: str, query: str, *, limit: int = 5, max_chars: int = 1200) -> str:
    """Render a stable summary plus relevant active role memories as reference."""
    memories = active_memories(role_id)
    summary = load(role_id).get("summary", "").strip()
    if not memories and not summary:
        return ""
    pinned = [item for item in memories if item["pinned"]]
    candidates = [item for item in memories if not item["pinned"]]
    by_content = {item["content"]: item for item in candidates}
    ranked = retrieve(query, list(by_content), embedder=get_local_embedder(), limit=limit, min_score=0.0)
    selected = pinned[:3] + [by_content[item.content] for item in ranked if item.content not in {entry["content"] for entry in pinned}]
    blocks: list[str] = []
    remaining = max_chars
    if summary:
        summary_text = f"- [stable relationship summary] {summary}"
        if len(summary_text) <= remaining:
            blocks.append(summary_text)
            remaining -= len(summary_text)
    for memory in selected:
        text = f"- [{memory['kind']}] {memory['content']}"
        if len(text) > remaining:
            break
        blocks.append(text)
        remaining -= len(text)
    return "\n".join(blocks)
