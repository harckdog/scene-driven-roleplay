# llm/utils.py

def history_to_text(history: list) -> str:
    """
    将 Chat History 转换成文本。
    """

    return "\n".join(
        f"{m['role'].capitalize()}: {m['content']}"
        for m in history
    )