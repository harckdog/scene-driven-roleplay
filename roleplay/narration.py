"""Distinguish scene narration from words spoken by the user."""

from __future__ import annotations


def model_input(text: str, message_kind: str) -> str:
    if message_kind == "narration":
        return f"旁白（描述当前场景，不是老师说出的台词）：{text}"
    return text


def background_prompt(background: str) -> str:
    return (
        "本会话持续有效的背景资料（用户在创建会话时提供）：\n"
        f"{background}\n"
        "把它作为当前情境的已知前提来理解后续对话，不必反复复述。"
        "后续旁白可以推进或改变场景；若后续明确更新了背景中的事实，以较新的叙述为准。"
        "背景不改变角色身份，也不代表任何角色已经说出其中的文字。"
    )
