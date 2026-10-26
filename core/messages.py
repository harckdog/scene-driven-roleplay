from pprint import pprint

from prompts.manager import get_prompt
from context.manager import build_context, build_context_with_sources
from config import DEBUG

def debug_context(mode: str, context: list) -> None:
    """
    打印发送给 LLM 的 Context。
    """

    if not DEBUG:
        return

    print("=" * 60)
    print(f"Mode: {mode}")
    print(f"Context Length: {len(context)}")
    print("=" * 60)

    for msg in context:
        pprint(msg)

    print("=" * 60)

def build_messages(mode: str, message: str) -> list:
    """
    构建发送给 LLM 的 messages。
    """

    context = build_context(mode, message)

    debug_context(mode, context)

    messages = [
        {
            "role": "system",
            "content": get_prompt(mode)
        },
        *context,
        {
            "role": "user",
            "content": message
        }
    ]



    return messages


def build_messages_with_sources(mode: str, message: str) -> tuple[list, list]:
    """Build one request and retain retrieved knowledge provenance for its caller."""
    context, sources = build_context_with_sources(mode, message)
    debug_context(mode, context)
    return ([{"role": "system", "content": get_prompt(mode)}, *context, {"role": "user", "content": message}], sources)
