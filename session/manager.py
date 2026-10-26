"""
session_manager.py

负责管理不同模式的 Session。

当前版本：
- JSON 持久化
- 每个模式对应一个 JSON 文件

所有消息均采用 OpenAI Message 格式：

{
    "role": "user" | "assistant" | "system",
    "content": "..."
}
"""

import json
from pathlib import Path
from copy import deepcopy
from config import SESSION_DIR

# Session 存储目录
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# 支持的模式
MODES = [
    "chat",
    "paper",
    "exam",
    "brainstorm",
    "latex",
]

def _get_session_file(mode: str) -> Path:
    """
    获取指定模式对应的 JSON 文件路径。
    """
    return SESSION_DIR / f"{mode}.json"


def load(mode: str) -> list:
    """
    从 JSON 文件读取 Session。
    """

    file = _get_session_file(mode)

    if not file.exists():
        return []
    try:
        with open(file, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(history, list):
        return []

    return [
        item
        for item in history
        if isinstance(item, dict)
        and item.get("role") in {"user", "assistant", "system"}
        and isinstance(item.get("content"), str)
    ]


def save(mode: str, history: list):
    """
    将 Session 保存到 JSON。
    """

    file = _get_session_file(mode)

    with open(file, "w", encoding="utf-8") as f:
        json.dump(
            history,
            f,
            ensure_ascii=False,
            indent=4,
        )


def get_history(mode: str) -> list:
    """
    获取指定模式的聊天记录。
    """

    return deepcopy(load(mode))


def append(mode: str, role: str, content: str):
    """
    添加一条消息。
    """

    history = load(mode)

    history.append(
        {
            "role": role,
            "content": content,
        }
    )
    save(mode, history)


def set_history(mode: str, history: list):
    """
    用新的历史覆盖当前 Session。
    """

    save(mode, history)


def clear_history(mode: str):
    """
    清空指定模式聊天记录。
    """

    save(mode, [])


def get_modes() -> list:
    """
    返回所有模式。
    """

    return MODES.copy()
