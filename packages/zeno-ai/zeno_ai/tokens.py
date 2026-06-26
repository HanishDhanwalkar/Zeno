"""token counter"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterable

import tiktoken

_DEFAULT_MODEL = "gpt-4o-mini" # TODO: move this to global config


@lru_cache(maxsize=32)
def _get_encoding(model: str):
    try:
        return tiktoken.encoding_for_model(model)
    except KeyError:
        return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str | None, model: str = _DEFAULT_MODEL) -> int:
    """Count tokens in a string using tiktoken."""
    if not text:
        return 0
    encoding = _get_encoding(model)
    return len(encoding.encode(text))


def _content_to_text(content: Any) -> str:
    """Flatten a message ``content`` field (str or list-of-parts) to text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
        return " ".join(parts)
    return str(content)


def count_message_tokens(messages: Iterable[dict], model: str = _DEFAULT_MODEL) -> int:
    """Estimate total tokens across chat messages.

    This counts message content plus tool call names/arguments.
    """
    total = 0
    for msg in messages:
        total += count_tokens(_content_to_text(msg.get("content")), model=model)

        total += count_tokens(msg.get("role"), model=model)

        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            total += count_tokens(fn.get("name"), model=model)
            args = fn.get("arguments")
            total += count_tokens(args if isinstance(args, str) else str(args), model=model)

        if "name" in msg:
            total += count_tokens(msg.get("name"), model=model)

    return total


if __name__ == "__main__":
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Summarize this file."},
    ]

    print(count_tokens("Hello! How can I assist you today?", model="gpt-4o-mini"))
    print(count_message_tokens(messages, model="gpt-4o-mini"))
