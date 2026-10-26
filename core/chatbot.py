from config import ROLEPLAY
from llm.client import call
from core.messages import build_messages, build_messages_with_sources

from session.manager import append as _append_session

from summary.generator import refresh as refresh_summary

from memory.manager import (
    load as load_memory,
    need_update as memory_needs_update,
    update as update_memory,
)

from memory.generator import generate as generate_memory


def save(
    mode: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """
    Save current conversation.
    """

    _append_session(mode, "user", user_message)
    _append_session(mode, "assistant", assistant_message)


def _update_summary(mode: str) -> str | None:
    """
    Update conversation summary.

    Returns
    -------
    str | None
        Latest summary when it was refreshed.
    """

    return refresh_summary(mode)


def _update_memory(
    mode: str,
) -> None:
    """
    Update long-term memory.
    """

    should_update, latest_summary = memory_needs_update(mode)
    if not should_update or not latest_summary:
        return

    memory = load_memory(mode)

    new_memory = generate_memory(
        mode=mode,
        summary=latest_summary,
        memory=memory,
    )

    update_memory(
        mode,
        new_memory,
    )


def chat(
    message: str,
    history: list,
    mode: str,
    role_id: str | None = None,
) -> str:
    """
    Entry of Gradio ChatInterface.
    """

    if mode == ROLEPLAY:
        if not role_id:
            raise ValueError("请选择一个角色后再开始角色扮演。")
        from core.roleplay_chatbot import chat as roleplay_chat

        return roleplay_chat(message, role_id)

    return chat_with_sources(message, history, mode, role_id)[0]


def chat_with_sources(
    message: str,
    history: list,
    mode: str,
    role_id: str | None = None,
) -> tuple[str, list]:
    """Return a normal reply with this turn's retrieved knowledge chunks."""
    if mode == ROLEPLAY:
        if not role_id:
            raise ValueError("roleplay message requires role_id")
        from core.roleplay_chatbot import chat_structured_many_with_sources
        replies, sources = chat_structured_many_with_sources(message, role_id)
        return "\n".join(reply.text for reply in replies), sources
    messages, sources = build_messages_with_sources(
        mode=mode,
        message=message,
    )

    response = call(messages)

    save(
        mode=mode,
        user_message=message,
        assistant_message=response,
    )

    summary = _update_summary(mode)

    if summary is not None:
        _update_memory(mode=mode)

    return response, sources
