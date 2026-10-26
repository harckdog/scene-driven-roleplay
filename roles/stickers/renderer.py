"""Gradio messages-format rendering adapter for manifest-backed stickers."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from roles.stickers.loader import resolve_sticker_asset
from roles.stickers.registry import StickerRegistry


def resolve_render_asset(sticker_id: str | None, *, pack_id: str | None, registry: StickerRegistry) -> Path | None:
    """Return a safe local image path for one currently available sticker."""
    sticker = registry.get_available(pack_id, sticker_id)
    return resolve_sticker_asset(sticker.file) if sticker is not None else None


def render_message_content(
    text: str,
    sticker_id: str | None,
    *,
    pack_id: str | None,
    registry: StickerRegistry,
) -> str | dict[str, str] | None:
    """Return text, or Gradio 6's native ``{'path': filepath}`` media content."""
    asset_path = resolve_render_asset(sticker_id, pack_id=pack_id, registry=registry)
    if asset_path is not None and not text:
        return {"path": str(asset_path), "alt_text": "角色表情"}
    return _clean_visible_text(text) or None


def render_history(
    history: list[dict[str, Any]],
    *,
    pack_id: str | None,
    registry: StickerRegistry,
) -> list[dict[str, Any]]:
    """Render every persisted message in Gradio's current messages format."""
    rendered: list[dict[str, Any]] = []
    for message in history:
        role = message["role"]
        if role not in {"user", "assistant"}:
            continue
        content = message["content"]
        text = _clean_visible_text(content["text"])
        if text:
            rendered.append({"role": role, "content": text})
        if role == "assistant":
            asset_path = resolve_render_asset(content["sticker_id"], pack_id=pack_id, registry=registry)
            if asset_path is not None:
                rendered.append(
                    {"role": "assistant", "content": {"path": str(asset_path), "alt_text": "角色表情"}}
                )
    return rendered


def _clean_visible_text(text: str) -> str:
    """Hide legacy model-echoed sticker metadata from visible messages."""
    return re.sub(r"\s*\[Assistant sent sticker: [^\]]*\]", "", text).strip()
