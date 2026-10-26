"""Load and safely resolve manifest-driven roleplay sticker packs."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from roles.stickers.schema import StickerManifestError, StickerPack


SUPPORTED_SUFFIXES = {".json", ".yaml", ".yml"}
PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PACKS_DIR = Path(__file__).resolve().parent / "packs"
DEFAULT_ASSETS_ROOT = PROJECT_DIR / "assets" / "stickers"


class StickerPackLoadError(ValueError):
    """Raised when a sticker manifest cannot be decoded or validated."""


def load_sticker_pack(path: str | Path) -> StickerPack:
    """Load one UTF-8 YAML or JSON sticker-pack manifest."""
    manifest_path = Path(path)
    if manifest_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise StickerPackLoadError(f"{manifest_path}: expected .json, .yaml, or .yml")
    try:
        text = manifest_path.read_text(encoding="utf-8")
        data = json.loads(text) if manifest_path.suffix.lower() == ".json" else yaml.safe_load(text)
    except OSError as error:
        raise StickerPackLoadError(f"{manifest_path}: could not read manifest ({error})") from error
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise StickerPackLoadError(f"{manifest_path}: invalid manifest syntax ({error})") from error
    try:
        return StickerPack.from_mapping(data)
    except StickerManifestError as error:
        raise StickerPackLoadError(f"{manifest_path}: {error}") from error


def load_sticker_packs(directory: str | Path = DEFAULT_PACKS_DIR) -> list[StickerPack]:
    """Load all supported pack manifests from a directory in stable order."""
    pack_dir = Path(directory)
    if not pack_dir.is_dir():
        raise StickerPackLoadError(f"{pack_dir}: sticker-pack directory does not exist")
    paths = sorted(
        path for path in pack_dir.iterdir() if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    return [load_sticker_pack(path) for path in paths]


def resolve_sticker_asset(file: str, *, project_dir: Path = PROJECT_DIR) -> Path | None:
    """Resolve one manifest path, returning ``None`` for missing or unsafe files.

    A missing asset intentionally does not invalidate the pack: callers can keep text
    chat available and simply omit the unusable sticker from presentation choices.
    """
    assets_root = (project_dir / "assets" / "stickers").resolve()
    candidate = (project_dir / file).resolve()
    try:
        candidate.relative_to(assets_root)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
