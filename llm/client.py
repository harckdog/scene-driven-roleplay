"""
llm/client.py

LLM Provider

负责统一调用大语言模型。
"""

import json
from functools import lru_cache
from urllib.parse import urlparse

from openai import OpenAI

from config import (
    API_KEY,
    BASE_URL,
    DEBUG,
    LLM_CACHE_METRICS,
    LLM_API_FORMAT,
    MODEL,
)


def _normalize_base_url(base_url: str | None) -> str | None:
    """Accept an API root or a pasted Chat Completions endpoint."""
    if base_url is None:
        return None
    cleaned = base_url.rstrip("/")
    for suffix in ("/chat/completions", "/responses"):
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    return cleaned + "/"


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """Create the provider client only when generation actually needs it."""
    if not API_KEY:
        raise RuntimeError("LLM_API_KEY is required for model generation")
    return OpenAI(api_key=API_KEY, base_url=_normalize_base_url(BASE_URL))


def call(
    messages: list,
    *,
    model: str | None = None,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
    response_schema: dict | None = None,
    max_output_tokens: int | None = None,
    usage_label: str | None = None,
) -> str:
    """
    Call LLM.

    Parameters
    ----------
    messages : list
        OpenAI message format.

    model : str | None

    temperature : float | None

    reasoning_effort : str | None
        Provider-specific reasoning setting. ``"none"`` disables thinking
        where the provider offers that option.

    response_schema : dict | None
        Optional JSON Schema. Responses providers enforce it; Moonshot's JSON
        mode guarantees valid JSON, with the schema also stated in the prompt.

    max_output_tokens : int | None
        Output budget; Chat Completions maps this to max_completion_tokens.

    usage_label : str | None
        Local label for optional token metrics; never sent to the provider.

    Returns
    -------
    str
    """

    if max_output_tokens is not None and max_output_tokens < 1:
        raise ValueError("max_output_tokens must be positive")

    if _resolve_api_format(BASE_URL, LLM_API_FORMAT) == "chat_completions":
        response = _call_chat_completions(
            messages, model=model or MODEL, temperature=temperature,
            reasoning_effort=reasoning_effort, response_schema=response_schema,
            max_output_tokens=max_output_tokens,
        )
        text = _extract_chat_text(response)
    else:
        response = _call_responses(
            messages, model=model or MODEL, temperature=temperature,
            reasoning_effort=reasoning_effort, response_schema=response_schema,
            max_output_tokens=max_output_tokens,
        )
        text = _extract_output_text(response)
    if LLM_CACHE_METRICS:
        print(_format_cache_usage(response, model or MODEL, usage_label))
    if not text:
        raise RuntimeError("模型未返回可显示的文本内容。")
    if DEBUG:
        print("=" * 60)
        print("Raw LLM response:")
        print(text)
        print("=" * 60)
    return text


def _resolve_api_format(base_url: str | None, configured: str) -> str:
    if configured != "auto":
        return configured
    path = urlparse(base_url or "").path.rstrip("/").lower()
    # Chat Completions is the common OpenAI-compatible endpoint. DeepSeek's
    # Responses API remains the existing project default for that provider.
    if path.endswith("/responses"):
        return "responses"
    if path.endswith("/chat/completions"):
        return "chat_completions"
    if _is_deepseek(base_url):
        return "responses"
    return "chat_completions"


def _is_moonshot(base_url: str | None) -> bool:
    host = (urlparse(base_url or "").hostname or "").lower()
    return host in {"api.moonshot.cn", "api.moonshot.ai"}


def _is_glm(base_url: str | None) -> bool:
    host = (urlparse(base_url or "").hostname or "").lower()
    return host in {"open.bigmodel.cn", "api.z.ai"}


def _is_deepseek(base_url: str | None) -> bool:
    host = (urlparse(base_url or "").hostname or "").lower()
    return host in {"api.deepseek.com", "api.deepseek.cn"}


def _is_openai(base_url: str | None) -> bool:
    return (urlparse(base_url or "").hostname or "").lower() == "api.openai.com"


def _call_responses(messages: list, *, model: str | None, temperature: float | None,
                    reasoning_effort: str | None, response_schema: dict | None,
                    max_output_tokens: int | None) -> object:
    extra_body: dict[str, object] = {}
    if reasoning_effort is not None:
        extra_body["reasoning"] = {"effort": reasoning_effort}
    request: dict[str, object] = {
        "model": model,
        "input": messages,
        "temperature": temperature,
    }
    if response_schema is not None:
        request["text"] = {
            "format": {
                "type": "json_schema",
                "name": "roleplay_response",
                "schema": response_schema,
            }
        }
    if extra_body:
        request["extra_body"] = extra_body
    if max_output_tokens is not None:
        request["max_output_tokens"] = max_output_tokens
    return _client().responses.create(**request)


def _call_chat_completions(messages: list, *, model: str | None, temperature: float | None,
                           reasoning_effort: str | None, response_schema: dict | None,
                           max_output_tokens: int | None) -> object:
    chat_messages = [_as_chat_message(message) for message in messages]
    request: dict[str, object] = {"model": model, "messages": chat_messages}
    if temperature is not None:
        request["temperature"] = temperature
    if max_output_tokens is not None:
        # max_tokens works across most Chat Completions-compatible providers.
        # OpenAI and Moonshot accept the newer max_completion_tokens spelling.
        request["max_completion_tokens" if (_is_openai(BASE_URL) or _is_moonshot(BASE_URL)) else "max_tokens"] = max_output_tokens
    if reasoning_effort == "none" and _is_moonshot(BASE_URL):
        request["extra_body"] = {"thinking": {"type": "disabled"}}
    elif reasoning_effort == "none" and _is_glm(BASE_URL) and (model or "").lower().startswith("glm-5.3"):
        # GLM-5.3 requires thinking; its lowest supported effort is low.
        request["extra_body"] = {"reasoning_effort": "low"}
    elif reasoning_effort not in {None, "none"}:
        raise ValueError(f"Unsupported Chat Completions reasoning effort: {reasoning_effort}")
    if response_schema is not None:
        request["response_format"] = {"type": "json_object"}
        chat_messages.insert(0, {
            "role": "system",
            "content": "只返回符合以下 JSON Schema 的 JSON 对象，不要附加文字："
                       + json.dumps(response_schema, ensure_ascii=False, separators=(",", ":")),
        })
    return _client().chat.completions.create(**request)


def _as_chat_message(message: dict) -> dict:
    content = message.get("content")
    if not isinstance(content, list):
        return message
    parts = []
    for part in content:
        if part.get("type") == "input_text":
            parts.append({"type": "text", "text": part["text"]})
        elif part.get("type") == "input_image":
            parts.append({"type": "image_url", "image_url": {"url": part["image_url"]}})
        else:
            parts.append(part)
    return {**message, "content": parts}


def _extract_chat_text(response: object) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    content = getattr(getattr(choices[0], "message", None), "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()
    return ""


def _format_cache_usage(response: object, model: str | None, label: str | None) -> str:
    """Summarize provider-reported cache usage without logging prompt content."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return f"[llm cache] label={label or 'unspecified'} model={model} usage=unavailable"
    input_tokens = _usage_field(usage, "input_tokens")
    if input_tokens is None:
        input_tokens = _usage_field(usage, "prompt_tokens")
    output_tokens = _usage_field(usage, "output_tokens")
    if output_tokens is None:
        output_tokens = _usage_field(usage, "completion_tokens")
    details = _usage_field(usage, "input_tokens_details")
    cached = _usage_field(details, "cached_tokens")
    if cached is None:
        cached = _usage_field(_usage_field(usage, "prompt_tokens_details"), "cached_tokens")
    if cached is None:
        cached = _usage_field(usage, "prompt_cache_hit_tokens")
    uncached = _usage_field(usage, "prompt_cache_miss_tokens")
    if uncached is None and isinstance(input_tokens, int) and isinstance(cached, int):
        uncached = input_tokens - cached
    return (
        f"[llm cache] label={label or 'unspecified'} model={model} "
        f"input={input_tokens} cached={cached} uncached={uncached} output={output_tokens}"
    )


def _usage_field(value: object, name: str) -> object:
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _extract_output_text(response: object) -> str:
    """Extract text safely from an OpenAI Responses API result.

    Some OpenAI-compatible providers include non-text output parts whose
    ``text`` attribute is ``None``. Accessing ``response.output_text`` then
    raises while joining the provider response. This extractor keeps only
    non-empty text values.

    Args:
        response: Responses API result object.

    Returns:
        Concatenated visible text, or an empty string when none is present.
    """
    texts: list[str] = []
    for output in getattr(response, "output", []) or []:
        if getattr(output, "type", None) not in {None, "message"}:
            continue
        for content in getattr(output, "content", []) or []:
            if getattr(content, "type", None) not in {None, "output_text", "text"}:
                continue
            value = getattr(content, "text", None)
            if isinstance(value, str) and value.strip():
                texts.append(value)
    return "".join(texts).strip()
