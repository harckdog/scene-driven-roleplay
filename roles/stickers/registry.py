"""Read-only sticker pack registry independent from UI and LLM code."""

from __future__ import annotations

from pathlib import Path

from roles.stickers.loader import (
    DEFAULT_PACKS_DIR,
    StickerPackLoadError,
    load_sticker_packs,
    resolve_sticker_asset,
)
from roles.stickers.schema import StickerDefinition, StickerPack


class StickerRegistry:
    """Expose only enabled, locally available stickers from unique packs."""

    def __init__(self, packs: list[StickerPack]) -> None:
        self._packs: dict[str, StickerPack] = {}
        self._available: dict[str, dict[str, StickerDefinition]] = {}
        for pack in packs:
            if pack.id in self._packs:
                raise StickerPackLoadError(f"duplicate sticker pack id: {pack.id}")
            self._packs[pack.id] = pack
            # Availability is a property of the local static pack. Resolve it
            # once so rendering a long transcript does not stat every asset
            # once per assistant message.
            self._available[pack.id] = {
                sticker.id: sticker
                for sticker in pack.stickers
                if sticker.enabled and resolve_sticker_asset(sticker.file) is not None
            }

    @classmethod
    def from_directory(cls, directory: str | Path = DEFAULT_PACKS_DIR) -> "StickerRegistry":
        """Load a registry from a manifest directory."""
        return cls(load_sticker_packs(directory))

    def get_pack(self, pack_id: str | None) -> StickerPack | None:
        """Return a pack when configured, otherwise ``None``."""
        return self._packs.get(pack_id) if pack_id else None

    def list_available(self, pack_id: str | None) -> list[StickerDefinition]:
        """Return enabled stickers whose files currently exist locally."""
        return list(self._available.get(pack_id or "", {}).values())

    def get_available(self, pack_id: str | None, sticker_id: str | None) -> StickerDefinition | None:
        """Return one enabled, locally available sticker by public identifier."""
        if not sticker_id:
            return None
        return self._available.get(pack_id or "", {}).get(sticker_id)

    def get_definition(self, pack_id: str | None, sticker_id: str | None) -> StickerDefinition | None:
        """Return reviewed semantics even when the asset cannot be rendered."""
        if not pack_id or not sticker_id:
            return None
        pack = self._packs.get(pack_id)
        if pack is None:
            return None
        return next((item for item in pack.stickers if item.id == sticker_id), None)
