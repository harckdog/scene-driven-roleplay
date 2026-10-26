"""Shared automatic and developer-triggered roleplay memory updates."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock, Thread
from typing import Any
from uuid import uuid4

from config import ROLEPLAY_MEMORY_ENABLED
from roleplay.memory import generator
from roleplay.memory.manager import load, save
from roleplay.session_manager import get_session, get_turns
from roles.registry import get_role


_UPDATE_LOCKS: dict[str, Lock] = {}
_LOCK_GUARD = Lock()


def _lock(role_id: str) -> Lock:
    with _LOCK_GUARD:
        return _UPDATE_LOCKS.setdefault(role_id, Lock())


def should_auto_update(role_id: str) -> bool:
    """Return whether completed, unprocessed user turns meet this role's interval."""
    if not ROLEPLAY_MEMORY_ENABLED:
        return False
    record = load(role_id)
    session = get_session(role_id)
    return bool(record["settings"]["auto_update_enabled"]) and session["completed_turn_count"] - record["memory_checkpoint_turn"] >= record["settings"]["update_every_turns"]


def schedule_auto_update(role_id: str) -> None:
    """Start a best-effort background update after a successful chat turn."""
    if should_auto_update(role_id):
        Thread(target=_background_update, args=(role_id,), daemon=True, name=f"roleplay-memory-{role_id}").start()


def _background_update(role_id: str) -> None:
    try:
        update(role_id, scope="pending")
    except Exception as error:
        record = load(role_id)
        record["last_error"] = str(error)
        record["revision"] += 1
        save(role_id, record)


def update(role_id: str, *, scope: str = "pending", turn_ids: list[str] | None = None) -> dict[str, Any]:
    """Extract and commit a role's selected or pending complete conversation turns.

    Selected turns deliberately do not advance the contiguous automatic checkpoint.
    """
    if not ROLEPLAY_MEMORY_ENABLED:
        raise RuntimeError("Roleplay memory is disabled.")
    if scope not in {"pending", "selected"}:
        raise ValueError("scope must be pending or selected")
    selected_ids = set(turn_ids or [])
    if scope == "selected" and not selected_ids:
        raise ValueError("selected updates require at least one turn_id")
    with _lock(role_id):
        memory_record = load(role_id)
        session = get_session(role_id)
        all_turns = get_turns(role_id)
        if scope == "pending":
            start = memory_record["memory_checkpoint_turn"]
            turns = all_turns[start:session["completed_turn_count"]]
        else:
            turns = [turn for turn in all_turns if turn["turn_id"] in selected_ids]
            if len(turns) != len(selected_ids):
                raise ValueError("one or more selected turn_ids do not exist")
        if not turns:
            return {"status": "no_changes", "record": deepcopy(memory_record)}
        profile = get_role(role_id)
        summary, candidates = generator.generate(
            turns=turns,
            existing_memories=memory_record["memories"],
            remember=profile.memory_policy.remember,
            ignore=profile.memory_policy.ignore,
        )
        valid_ids = {turn["turn_id"] for turn in turns}
        if any(not set(candidate["source_turn_ids"]).issubset(valid_ids) for candidate in candidates):
            raise ValueError("memory model referenced a turn outside the requested range")
        current = load(role_id)
        current_session = get_session(role_id)
        if current["revision"] != memory_record["revision"] or current_session["session_id"] != session["session_id"]:
            raise RuntimeError("conversation or memory changed while extraction was running")
        existing = {(item["kind"], item["content"]) for item in current["memories"] if item["status"] == "active"}
        added = 0
        now = datetime.now(timezone.utc).isoformat()
        for candidate in candidates:
            key = (candidate["kind"], candidate["content"])
            if key in existing:
                continue
            current["memories"].append({"id": f"mem_{uuid4().hex}", "kind": candidate["kind"], "content": candidate["content"], "status": "active", "importance": candidate["importance"], "pinned": False, "source_turn_ids": candidate["source_turn_ids"], "created_at": now, "updated_at": now})
            existing.add(key)
            added += 1
        if summary:
            current["summary"] = summary[:1200]
        if scope == "pending":
            current["memory_checkpoint_turn"] = session["completed_turn_count"]
        current["last_error"] = None
        current["last_updated_at"] = now
        current["revision"] += 1
        save(role_id, current)
        return {"status": "updated", "added": added, "processed_turn_ids": [turn["turn_id"] for turn in turns], "record": deepcopy(current)}
