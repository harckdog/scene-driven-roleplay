"""Role discovery and duplicate-safe registry APIs."""

from __future__ import annotations

from pathlib import Path

from roles.loader import RoleProfileLoadError, load_profiles
from roles.schema import RoleProfile


DEFAULT_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"


class RoleRegistry:
    """Read-only registry of unique character profiles."""

    def __init__(self, profiles: list[RoleProfile]) -> None:
        """Create a registry and reject duplicate role identifiers.

        Args:
            profiles: Validated role profiles.

        Raises:
            RoleProfileLoadError: If two profiles have the same identifier.
        """
        self._profiles: dict[str, RoleProfile] = {}
        for profile in profiles:
            if profile.id in self._profiles:
                raise RoleProfileLoadError(f"duplicate role id: {profile.id}")
            self._profiles[profile.id] = profile

    @classmethod
    def from_directory(cls, directory: str | Path = DEFAULT_PROFILES_DIR) -> "RoleRegistry":
        """Load a registry from a profile directory."""
        return cls(load_profiles(directory))

    def list(self) -> list[RoleProfile]:
        """Return registered profiles ordered by display name and identifier."""
        return sorted(self._profiles.values(), key=lambda profile: (profile.display_name, profile.id))

    def get(self, role_id: str) -> RoleProfile:
        """Return one profile by identifier.

        Raises:
            KeyError: If the role is not registered.
        """
        return self._profiles[role_id]


def list_roles(directory: str | Path = DEFAULT_PROFILES_DIR) -> list[RoleProfile]:
    """Discover roles without any UI dependency."""
    return RoleRegistry.from_directory(directory).list()


def get_role(role_id: str, directory: str | Path = DEFAULT_PROFILES_DIR) -> RoleProfile:
    """Load one role by identifier without any UI dependency."""
    return RoleRegistry.from_directory(directory).get(role_id)
