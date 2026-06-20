"""Deterministic, offline 'mock' provider.

Lets the entire Node<->Python pipeline be exercised end-to-end without any
network access or API keys. It understands a tiny directive DSL embedded in the
latest user message so tests can drive tool calls:

    [[tool:read {"path": "README.md"}]]

When the most recent message is a tool result, the mock "summarises" by echoing
that the tool ran and stops. Otherwise, with no directive, it streams back an
echo of the user's text.
"""

from __future__ import annotations

import json
import re
from typing import Any, AsyncIterator

_TOOL_DIRECTIVE = re.compile(r"\[\[tool:([a-zA-Z_][\w]*)\s*(\{.*?\})?\s*\]\]", re.DOTALL)


def _last_of_role(messages: list[dict], role: str) -> dict | None:
    for msg in reversed(messages):
        if msg.get("role") == role:
            return msg
    return None


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            p if isinstance(p, str) else str(p.get("text", "")) for p in content
        )
    return "" if content is None else str(content)


async def run(
    prompt: str,
    messages: list[dict],
    tools: list[dict],
    stream: bool = True,
    **_: Any,
) -> AsyncIterator[dict]:
    last = messages[-1] if messages else None

    # If we just received tool output, wrap up.
    if last is not None and last.get("role") == "tool":
        tool_name = last.get("name", "tool")
        for chunk in (f"Observed result from `{tool_name}`. ", "Done."):
            yield {"type": "text_delta", "content": chunk}
        yield {"type": "stop", "reason": "stop"}
        return

    user = _last_of_role(messages, "user")
    user_text = _text(user.get("content")) if user else ""

    directives = list(_TOOL_DIRECTIVE.finditer(user_text))
    if directives:
        for i, m in enumerate(directives):
            name = m.group(1)
            raw_args = m.group(2) or "{}"
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {"_raw": raw_args}
            yield {
                "type": "tool_call",
                "id": f"mock-{i}",
                "name": name,
                "args": args,
            }
        yield {"type": "stop", "reason": "tool_calls"}
        return

    # Plain echo, streamed word-by-word.
    reply = user_text.strip() or "Hello from the Zeno mock provider."
    echo = f"(mock) {reply}"
    for word in echo.split(" "):
        yield {"type": "text_delta", "content": word + " "}
    yield {"type": "stop", "reason": "stop"}
