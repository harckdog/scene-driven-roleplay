"""The visible Scene-only reply passed to persistence and the web UI."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleplayReply:
    text: str
    sticker_id: str | None = None
