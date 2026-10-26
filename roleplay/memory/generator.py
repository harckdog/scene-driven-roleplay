"""LLM-backed extraction of evidence-bound roleplay memories."""

from __future__ import annotations

import json
from typing import Any

from llm.client import call


_KINDS = ["user_fact", "preference", "shared_episode", "commitment", "relationship_fact"]


def generate(*, turns: list[dict[str, Any]], existing_memories: list[dict[str, Any]], remember: tuple[str, ...], ignore: tuple[str, ...]) -> tuple[str, list[dict[str, Any]]]:
    """Return a concise summary and validated candidate memories for complete turns."""
    messages = _messages(turns, existing_memories, remember, ignore)
    response = call(messages, reasoning_effort="none", response_schema=_schema())
    return _parse(response)


def _messages(turns: list[dict[str, Any]], existing: list[dict[str, Any]], remember: tuple[str, ...], ignore: tuple[str, ...]) -> list[dict[str, str]]:
    transcript: list[str] = []
    for turn in turns:
        transcript.append(f"[Turn ID: {turn['turn_id']}]")
        for message in turn["messages"]:
            transcript.append(f"{message['role']}: {message['content']['text']}")
    old = "\n".join(f"- {item['content']}" for item in existing if item["status"] == "active") or "(none)"
    return [
        {"role": "system", "content": "Extract only stable, evidence-bound roleplay memories. Keep a concise rolling summary. Never infer a user fact from the assistant's invention, a sticker, or an original-work reference. Remember explicit preferences, confirmed agreements, meaningful shared episodes, and explicit relationship boundaries. Assistant dialogue may document one shared episode, but must never be generalized into a stable character rule, preference, sensitivity, or response template (for example, 'the character always hides feelings' or 'usually denies affection') unless independent user evidence explicitly establishes it. Ignore greetings, transient mood, unsupported assumptions, and private reasoning. Return only the required JSON."},
        {"role": "user", "content": f"Role preferences to remember:\n- " + "\n- ".join(remember or ("explicit long-term preferences and agreements",)) + f"\n\nIgnore:\n- " + "\n- ".join(ignore or ("greetings and unconfirmed details",)) + f"\n\nExisting active memories:\n{old}\n\nComplete conversation turns:\n" + "\n".join(transcript)},
    ]


def _schema() -> dict[str, Any]:
    return {"type": "object", "properties": {"summary": {"type": "string"}, "memories": {"type": "array", "items": {"type": "object", "properties": {"kind": {"type": "string", "enum": _KINDS}, "content": {"type": "string", "minLength": 1}, "importance": {"type": "number", "minimum": 0, "maximum": 1}, "source_turn_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["kind", "content", "importance", "source_turn_ids"], "additionalProperties": False}}}, "required": ["summary", "memories"], "additionalProperties": False}


def _parse(response: str) -> tuple[str, list[dict[str, Any]]]:
    try:
        data = json.loads(response)
    except json.JSONDecodeError as error:
        raise ValueError("memory model returned invalid JSON") from error
    if not isinstance(data, dict) or set(data) != {"summary", "memories"} or not isinstance(data["summary"], str) or not isinstance(data["memories"], list):
        raise ValueError("memory model returned an invalid shape")
    candidates: list[dict[str, Any]] = []
    for item in data["memories"]:
        if not isinstance(item, dict) or set(item) != {"kind", "content", "importance", "source_turn_ids"}:
            raise ValueError("memory model returned an invalid candidate")
        if item["kind"] not in _KINDS or not isinstance(item["content"], str) or not item["content"].strip() or not isinstance(item["importance"], (int, float)) or not isinstance(item["source_turn_ids"], list) or any(not isinstance(value, str) for value in item["source_turn_ids"]):
            raise ValueError("memory model returned an invalid candidate")
        candidates.append({"kind": item["kind"], "content": item["content"].strip(), "importance": max(0.0, min(1.0, float(item["importance"]))), "source_turn_ids": item["source_turn_ids"]})
    return data["summary"].strip(), candidates
