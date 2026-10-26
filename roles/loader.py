"""Loading character profiles from UTF-8 YAML and JSON documents."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from roles.schema import RoleProfile, RoleProfileError


SUPPORTED_SUFFIXES = {".json", ".yaml", ".yml"}


class RoleProfileLoadError(ValueError):
    """Raised when a profile file cannot be decoded or validated."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently replacing earlier values."""


def _construct_unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode) -> dict:
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while loading a role profile",
                node.start_mark,
                f"duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=True)
    return mapping


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_profile(path: str | Path) -> RoleProfile:
    """Load and validate one role profile document.

    Args:
        path: YAML or JSON profile path.

    Returns:
        Typed role profile.

    Raises:
        RoleProfileLoadError: If the file extension, syntax, or schema is invalid.
    """
    profile_path = Path(path)
    if profile_path.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise RoleProfileLoadError(f"{profile_path}: expected .json, .yaml, or .yml")

    try:
        text = profile_path.read_text(encoding="utf-8")
    except OSError as error:
        raise RoleProfileLoadError(f"{profile_path}: could not read profile ({error})") from error

    try:
        data = (
            json.loads(text)
            if profile_path.suffix.lower() == ".json"
            else yaml.load(text, Loader=_UniqueKeyLoader)
        )
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise RoleProfileLoadError(f"{profile_path}: invalid profile syntax ({error})") from error

    try:
        return RoleProfile.from_mapping(data)
    except RoleProfileError as error:
        raise RoleProfileLoadError(f"{profile_path}: {error}") from error


def load_profiles(directory: str | Path) -> list[RoleProfile]:
    """Load all supported profile files from one directory in stable order.

    Args:
        directory: Profile directory.

    Returns:
        Validated role profiles sorted by filename.
    """
    profile_dir = Path(directory)
    if not profile_dir.is_dir():
        raise RoleProfileLoadError(f"{profile_dir}: profile directory does not exist")

    paths = sorted(
        path
        for path in profile_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    )
    return [load_profile(path) for path in paths]
