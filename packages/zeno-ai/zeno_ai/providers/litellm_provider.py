"""Real LLM provider backed by litellm (lazy-imported).

litellm normalises many providers (openai, anthropic, gemini, ...) behind one
streaming API. It is only imported when this provider is actually used, so the
core stays dependency-free for offline/mock runs.

Translates litellm's streaming chunks into Zeno's structured event dicts:
    {type:"text_delta", content}
    {type:"tool_call", id, name, args}
    {type:"stop", reason}
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator


async def run(
    prompt: str,
    messages: list[dict],
    tools: list[dict],
    stream: bool = True,
    *,
    model: str,
    **opts: Any,
) -> AsyncIterator[dict]:
    try:
        import litellm  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on install
        raise RuntimeError(
            "litellm is not installed. Install it (pip install litellm) or use "
            "model='mock' for offline runs."
        ) from exc

    call_messages = list(messages)
    if prompt and not any(m.get("role") == "system" for m in call_messages):
        call_messages = [{"role": "system", "content": prompt}, *call_messages]

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": call_messages,
        "stream": True,
    }
    if tools:
        kwargs["tools"] = tools
    kwargs.update(opts)

    # Accumulate streamed tool-call fragments by index.
    tool_acc: dict[int, dict] = {}
    finish_reason = "stop"

    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        choice = chunk.choices[0]
        delta = choice.delta

        text = getattr(delta, "content", None)
        if text:
            yield {"type": "text_delta", "content": text}

        for tc in getattr(delta, "tool_calls", None) or []:
            idx = getattr(tc, "index", 0) or 0
            slot = tool_acc.setdefault(idx, {"id": None, "name": "", "args": ""})
            if getattr(tc, "id", None):
                slot["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is not None:
                if getattr(fn, "name", None):
                    slot["name"] = fn.name
                if getattr(fn, "arguments", None):
                    slot["args"] += fn.arguments

        if getattr(choice, "finish_reason", None):
            finish_reason = choice.finish_reason

    for idx in sorted(tool_acc):
        slot = tool_acc[idx]
        try:
            args = json.loads(slot["args"]) if slot["args"] else {}
        except json.JSONDecodeError:
            args = {"_raw": slot["args"]}
        yield {
            "type": "tool_call",
            "id": slot["id"] or f"call-{idx}",
            "name": slot["name"],
            "args": args,
        }

    yield {"type": "stop", "reason": finish_reason}
