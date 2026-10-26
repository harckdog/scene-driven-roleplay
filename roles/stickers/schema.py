"""Typed schema for roleplay sticker-pack manifests."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


STICKER_SCHEMA_VERSION = 1
_IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
ALLOWED_STICKER_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
INTENSITIES = frozenset({"mild", "medium", "high", "extreme"})
# The coarse families shared by the generator's private affect annotation and
# sticker manifests.  Sticker manifests use ``affect.primary`` for this value,
# so the family gate can exclude wrong-family candidates without asking the
# selector to infer the family from surface wording.
AFFECT_FAMILIES = (
    "neutral",
    "gentle",
    "troubled",
    "embarrassed",
    "moved",
    "happy",
    "angry",
    "resigned",
)


class StickerManifestError(ValueError):
    """Raised when a sticker-pack manifest is malformed or unsafe."""


@dataclass(frozen=True)
class StickerAffect:
    """Structured affect family used by the second-generation selector."""

    primary: str
    secondary: tuple[str, ...] = ()


@dataclass(frozen=True)
class StickerDefinition:
    """One local, preset emotional sticker declared by a pack."""

    id: str
    file: str
    label: str
    description: str
    emotion_tags: tuple[str, ...]
    enabled: bool
    fallback_cues: tuple[str, ...] = ()
    fallback_priority: int = 0
    affect: StickerAffect | None = None
    intensity: str = "medium"
    dialogue_acts: tuple[str, ...] = ()
    expression_styles: tuple[str, ...] = ()
    usage_scenarios: tuple[str, ...] = ()
    avoid_when: tuple[str, ...] = ()
    contrast_with: tuple[tuple[str, str], ...] = ()

    def selection_text(self) -> str:
        """Return structured semantics suitable for prompts or future retrieval."""
        affect = self.affect
        parts = [self.label, self.description]
        if affect is not None:
            parts.append(f"primary affect: {affect.primary}")
            if affect.secondary:
                parts.append(f"secondary affect: {'; '.join(affect.secondary)}")
        parts.append(f"intensity: {self.intensity}")
        if self.dialogue_acts:
            parts.append(f"dialogue acts: {'; '.join(self.dialogue_acts)}")
        if self.expression_styles:
            parts.append(f"expression styles: {'; '.join(self.expression_styles)}")
        if self.usage_scenarios:
            parts.append(f"use when: {'; '.join(self.usage_scenarios)}")
        if self.avoid_when:
            parts.append(f"avoid when: {'; '.join(self.avoid_when)}")
        return "\n".join(parts)


@dataclass(frozen=True)
class StickerPack:
    """Validated sticker pack associated with a character profile."""

    schema_version: int
    id: str
    display_name: str
    stickers: tuple[StickerDefinition, ...]

    @classmethod
    def from_mapping(cls, data: object) -> "StickerPack":
        """Build a typed sticker pack from decoded YAML or JSON data."""
        root = _mapping(data, "sticker pack")
        version = _required_int(root, "schema_version")
        if version != STICKER_SCHEMA_VERSION:
            raise StickerManifestError(
                f"schema_version: expected {STICKER_SCHEMA_VERSION}, received {version}"
            )

        pack_id = _identifier(_required_str(root, "id"), "id")
        stickers_value = root.get("stickers", [])
        if not isinstance(stickers_value, list):
            raise StickerManifestError("stickers: expected a list")

        sticker_ids: set[str] = set()
        stickers: list[StickerDefinition] = []
        for index, item in enumerate(stickers_value):
            sticker = _mapping(item, f"stickers[{index}]")
            sticker_id = _identifier(_required_str(sticker, "id", f"stickers[{index}]"), f"stickers[{index}].id")
            if sticker_id in sticker_ids:
                raise StickerManifestError(f"duplicate sticker id: {sticker_id}")
            sticker_ids.add(sticker_id)
            stickers.append(
                StickerDefinition(
                    id=sticker_id,
                    file=_asset_file(_required_str(sticker, "file", f"stickers[{index}]"), index),
                    label=_required_str(sticker, "label", f"stickers[{index}]"),
                    description=_required_str(sticker, "description", f"stickers[{index}]"),
                    emotion_tags=_string_list(sticker.get("emotion_tags", []), f"stickers[{index}].emotion_tags"),
                    enabled=_optional_bool(sticker, "enabled", f"stickers[{index}]", default=True),
                    fallback_cues=_string_list(
                        sticker.get("fallback_cues", []),
                        f"stickers[{index}].fallback_cues",
                    ),
                    fallback_priority=_optional_non_negative_int(
                        sticker,
                        "fallback_priority",
                        f"stickers[{index}]",
                        default=0,
                    ),
                    affect=_optional_affect(sticker.get("affect"), f"stickers[{index}].affect"),
                    intensity=_optional_intensity(sticker.get("intensity"), f"stickers[{index}].intensity"),
                    dialogue_acts=_string_list(sticker.get("dialogue_act", []), f"stickers[{index}].dialogue_act"),
                    expression_styles=_string_list(sticker.get("expression_style", []), f"stickers[{index}].expression_style"),
                    usage_scenarios=_string_list(sticker.get("usage_scenarios", []), f"stickers[{index}].usage_scenarios"),
                    avoid_when=_string_list(sticker.get("avoid_when", []), f"stickers[{index}].avoid_when"),
                    contrast_with=_contrast_mapping(sticker.get("contrast_with", {}), f"stickers[{index}].contrast_with"),
                )
            )

        valid_ids = {sticker.id for sticker in stickers}
        for sticker in stickers:
            for other_id, _reason in sticker.contrast_with:
                if other_id not in valid_ids or other_id == sticker.id:
                    raise StickerManifestError(f"stickers[{sticker.id}].contrast_with: unknown sticker id: {other_id}")

        return cls(
            schema_version=version,
            id=pack_id,
            display_name=_required_str(root, "display_name"),
            stickers=tuple(stickers),
        )


def _mapping(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StickerManifestError(f"{field}: expected an object")
    return value


def _required(data: dict[str, Any], key: str, prefix: str = "") -> object:
    if key not in data:
        field = f"{prefix}.{key}" if prefix else key
        raise StickerManifestError(f"{field}: required field is missing")
    return data[key]


def _required_str(data: dict[str, Any], key: str, prefix: str = "") -> str:
    field = f"{prefix}.{key}" if prefix else key
    value = _required(data, key, prefix)
    if not isinstance(value, str) or not value.strip():
        raise StickerManifestError(f"{field}: expected a non-empty string")
    return value.strip()


def _required_int(data: dict[str, Any], key: str) -> int:
    value = _required(data, key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise StickerManifestError(f"{key}: expected an integer")
    return value


def _optional_bool(data: dict[str, Any], key: str, prefix: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise StickerManifestError(f"{prefix}.{key}: expected a boolean")
    return value


def _optional_non_negative_int(
    data: dict[str, Any],
    key: str,
    prefix: str,
    *,
    default: int,
) -> int:
    value = data.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StickerManifestError(f"{prefix}.{key}: expected a non-negative integer")
    return value


def _optional_affect(value: object, field: str) -> StickerAffect | None:
    """Read an optional structured affect declaration without breaking v1 packs."""
    if value is None:
        return None
    data = _mapping(value, field)
    primary = data.get("primary")
    if not isinstance(primary, str) or not primary.strip():
        raise StickerManifestError(f"{field}.primary: expected a non-empty string")
    if primary.strip() not in AFFECT_FAMILIES:
        raise StickerManifestError(
            f"{field}.primary: expected one of {', '.join(AFFECT_FAMILIES)}"
        )
    return StickerAffect(primary=primary.strip(), secondary=_string_list(data.get("secondary", []), f"{field}.secondary"))


def _optional_intensity(value: object, field: str) -> str:
    """Read categorical intensity, defaulting legacy packs to medium."""
    if value is None:
        return "medium"
    if not isinstance(value, str) or value not in INTENSITIES:
        raise StickerManifestError(f"{field}: expected one of {', '.join(sorted(INTENSITIES))}")
    return value


def _contrast_mapping(value: object, field: str) -> tuple[tuple[str, str], ...]:
    """Read concise sibling distinctions used to explain close sticker choices."""
    if value is None:
        return ()
    data = _mapping(value, field)
    pairs: list[tuple[str, str]] = []
    for sticker_id, reason in data.items():
        if not isinstance(sticker_id, str) or not _IDENTIFIER_PATTERN.fullmatch(sticker_id):
            raise StickerManifestError(f"{field}: invalid sticker id: {sticker_id!r}")
        if not isinstance(reason, str) or not reason.strip():
            raise StickerManifestError(f"{field}.{sticker_id}: expected a non-empty string")
        pairs.append((sticker_id, reason.strip()))
    return tuple(pairs)


def _string_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise StickerManifestError(f"{field}: expected a list of strings")
    values: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise StickerManifestError(f"{field}[{index}]: expected a non-empty string")
        values.append(item.strip())
    return tuple(values)


def _identifier(value: str, field: str) -> str:
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise StickerManifestError(
            f"{field}: use lowercase letters, digits, and underscores; it must start with a letter"
        )
    return value


def _asset_file(value: str, index: int) -> str:
    """Validate a project-relative path before filesystem resolution."""
    normalized = value.replace("\\", "/")
    parts = normalized.split("/")
    if (
        not normalized.startswith("assets/stickers/")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise StickerManifestError(
            f"stickers[{index}].file: must be a relative path inside assets/stickers"
        )
    if not any(normalized.lower().endswith(suffix) for suffix in ALLOWED_STICKER_SUFFIXES):
        raise StickerManifestError(
            f"stickers[{index}].file: expected PNG, JPEG, or WebP asset"
        )
    return normalized
