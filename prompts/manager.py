"""
prompt/manager.py
"""

from config import PAPER, EXAM, CHAT

from prompts.chat.base import BASE_PROMPT
from prompts.chat.paper import PAPER_PROMPT
from prompts.chat.exam import EXAM_PROMPT
from prompts.chat.chat import CHAT_PROMPT
from prompts.chat.formatting import MATH_FORMAT_PROMPT

from prompts.summary.default import DEFAULT_SUMMARY_PROMPT
from prompts.summary.paper import PAPER_SUMMARY_PROMPT
from prompts.summary.exam import EXAM_SUMMARY_PROMPT
from prompts.summary.chat import CHAT_SUMMARY_PROMPT

from prompts.memory.base import BASE_MEMORY_PROMPT
from prompts.memory.paper import PAPER_MEMORY_PROMPT
from prompts.memory.exam import EXAM_MEMORY_PROMPT
from prompts.memory.chat import CHAT_MEMORY_PROMPT

CHAT_PROMPTS = {
    PAPER: PAPER_PROMPT,
    EXAM: EXAM_PROMPT,
    CHAT: CHAT_PROMPT
}

SUMMARY_PROMPTS = {
    PAPER: PAPER_SUMMARY_PROMPT,
    EXAM: EXAM_SUMMARY_PROMPT,
    CHAT: CHAT_SUMMARY_PROMPT
}

MEMORY_PROMPTS = {
    PAPER: PAPER_MEMORY_PROMPT,
    EXAM: EXAM_MEMORY_PROMPT,
    CHAT: CHAT_MEMORY_PROMPT
}

def get_prompt(mode: str) -> str:
    """
    获取聊天 Prompt。
    """
    return BASE_PROMPT + MATH_FORMAT_PROMPT + CHAT_PROMPTS.get(mode, "")


def get_summary_prompt(mode: str) -> str:
    """
    获取摘要 Prompt。
    """
    return SUMMARY_PROMPTS.get(mode, DEFAULT_SUMMARY_PROMPT)

def get_memory_prompt(mode: str) -> str:
    """
    获取记忆 Prompt。
    """
    return MEMORY_PROMPTS.get(mode, BASE_MEMORY_PROMPT)
