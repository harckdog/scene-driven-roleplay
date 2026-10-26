"""Character profile infrastructure for the future Roleplay mode."""

from roles.registry import RoleRegistry, get_role, list_roles
from roles.schema import RoleProfile, RoleProfileError

__all__ = [
    "RoleProfile",
    "RoleProfileError",
    "RoleRegistry",
    "get_role",
    "list_roles",
]
