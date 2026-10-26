"""
summary/generator.py

负责维护 Conversation Summary。

职责：
    - 判断是否需要更新 Summary
    - 调用 LLM 生成新的 Summary
    - 保存 Summary
"""

from config import SUMMARY_UPDATE_THRESHOLD
from llm.client import call
from llm.utils import history_to_text
from prompts.manager import get_summary_prompt
from session.manager import load as load_session
from summary.manager import load as load_summary
from summary.manager import save as save_summary




def should_update(history: list, last_index: int) -> bool:
    """
    判断是否需要更新摘要。

    Parameters
    ----------
    history
        完整历史消息。

    last_index
        已经摘要到的位置。

    Returns
    -------
    bool
    """

    return len(history) - last_index >= SUMMARY_UPDATE_THRESHOLD


def generate(
    history: list,
    old_summary: str,
    mode: str,
) -> str:

    prompt = get_summary_prompt(mode)

    history_text = history_to_text(history)

    user_content = f"""
Existing Summary:

{old_summary}

New Conversation:

{history_text}

Please update the summary.
"""

    messages = [
        {
            "role": "system",
            "content": prompt,
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]

    return call(messages)


def refresh(mode: str) -> str | None:
    """
    刷新 Conversation Summary。
    """

    session = load_session(mode)

    history = session

    record = load_summary(mode)

    last_index = record["last_index"]

    if not should_update(history, last_index):
        return None

    new_history = history[last_index:]

    new_summary = generate(
        history=new_history,
        old_summary=record["summary"],
        mode=mode,
    )

    record["summary"] = new_summary
    record["last_index"] = len(history)

    save_summary(mode, record)

    return new_summary
