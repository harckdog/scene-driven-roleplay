import json


def generate(mode: str, summary: str, memory: list[str]) -> list[str]:
    """
    Generate new long-term memories from the conversation summary.

    Args:
        mode: Current chat mode.
        summary: Conversation summary.
        memory: Existing memories.

    Returns:
        List of newly extracted memories.
    """

    from llm.client import call

    messages = _build_messages(mode, summary, memory)
    return _parse(call(messages))


def _build_messages(
    mode: str,
    summary: str,
    memory: list[str]
) -> list[dict]:
    """
    Build messages for memory extraction.
    """

    from prompts.manager import get_memory_prompt

    prompt = get_memory_prompt(mode)

    if memory:
        memory_text = "\n".join(
            f"- {item}" for item in memory
        )
    else:
        memory_text = "None"

    user_content = f"""
Existing Memories

{memory_text}

Conversation Summary

{summary}
"""

    return [
        {
            "role": "system",
            "content": prompt,
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]


def _parse(response: str) -> list[str]:
    """
    Parse LLM response.
    """

    response = response.strip()

    if response.startswith("```json"):
        response = response[7:]

    if response.startswith("```"):
        response = response[3:]

    if response.endswith("```"):
        response = response[:-3]

    response = response.strip()

    try:
        result = json.loads(response)

        if not isinstance(result, list):
            return []

        return [
            item.strip()
            for item in result
            if isinstance(item, str) and item.strip()
        ]

    except (json.JSONDecodeError, TypeError):
        return []
