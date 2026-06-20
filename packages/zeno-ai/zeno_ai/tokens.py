"""Approximate token counting.

Deliberately dependency-free and rough. A real tokenizer (tiktoken) can be a
drop-in replacement later; the rest of the system only relies on these two
functions, so swapping the heuristic is contained here.
"""

from __future__ import annotations

from typing import Any, Iterable

# Rough average of characters-per-token for English + code across common
# tokenizers. Used as a fallback heuristic.
_CHARS_PER_TOKEN = 4


def count_tokens(text: str | None) -> int:
    """Estimate the number of tokens in a string."""
    if not text:
        return 0
    # Blend a word-based and char-based estimate; max() keeps us from
    # under-counting dense code with few spaces.
    words = len(text.split())
    chars = len(text)
    return max(words, chars // _CHARS_PER_TOKEN, 1)


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
                # common shapes: {"type":"text","text":...} / {"text":...}
                parts.append(str(part.get("text") or part.get("content") or ""))
        return " ".join(parts)
    return str(content)


def count_message_tokens(messages: Iterable[dict]) -> int:
    """Estimate total tokens across a list of chat messages.

    Includes a small per-message overhead to approximate role/formatting
    tokens, and accounts for tool calls / tool results.
    """
    total = 0
    for msg in messages:
        total += 4  # per-message overhead
        total += count_tokens(_content_to_text(msg.get("content")))

        for call in msg.get("tool_calls") or []:
            fn = call.get("function") or {}
            total += count_tokens(fn.get("name"))
            args = fn.get("arguments")
            total += count_tokens(args if isinstance(args, str) else str(args))

        if "name" in msg:
            total += count_tokens(msg.get("name"))
    return total
