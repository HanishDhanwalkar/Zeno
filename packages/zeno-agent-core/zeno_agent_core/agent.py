"""The agent reasoning loop.

Stateless across requests: Node sends the full (pruned) message list each run.
``AgentLoop.run`` is an async generator that yields structured stream events:

    {type:"text_delta", content}
    {type:"tool_call", id, name, args}
    {type:"tool_result", id, name, result}
    {type:"stop", reason}
    {type:"error", message}

Cancellation is cooperative via an ``asyncio.Event``. A permission callback can
gate individual tool calls (used by Node to confirm dangerous bash commands).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, AsyncIterator

from .tools import TOOL_SCHEMAS, ToolExecutor

PermissionCb = Callable[[str, str, dict], Awaitable[dict]]
MAX_ITERATIONS = 25


async def _allow_all(call_id: str, name: str, args: dict) -> dict:
    return {"allow": True}


def _sanitize_messages(messages: list[dict]) -> list[dict]:
    """Convert tool_calls arguments from objects to JSON strings for Azure compatibility.
    Also removes any surrogate characters that can't be encoded to UTF-8."""
    sanitized = []
    for msg in messages:
        msg = dict(msg)  # Create a copy

        # Sanitize content to remove surrogates
        if "content" in msg and isinstance(msg["content"], str):
            msg["content"] = msg["content"].encode(
                "utf-8", errors="replace").decode("utf-8")

        # Sanitize tool_calls arguments
        if msg.get("role") == "assistant" and "tool_calls" in msg:
            msg["tool_calls"] = [
                {
                    **tc,
                    "function": {
                        **tc.get("function", {}),
                        "arguments": (
                            json.dumps(tc["function"]["arguments"])
                            if isinstance(tc["function"].get("arguments"), dict)
                            else tc["function"].get("arguments", "{}")
                        ),
                    },
                }
                for tc in msg["tool_calls"]
            ]

        sanitized.append(msg)
    return sanitized


class AgentLoop:
    def __init__(
        self,
        adapter: Any,
        executor: ToolExecutor,
        permission_cb: PermissionCb | None = None,
    ) -> None:
        self.adapter = adapter
        self.executor = executor
        self.permission_cb = permission_cb or _allow_all

    async def run(
        self,
        messages: list[dict],
        system_prompt: str = "",
        tools: list[dict] | None = None,
        cancel_event: asyncio.Event | None = None,
    ) -> AsyncIterator[dict]:
        tools = tools or TOOL_SCHEMAS
        cancel_event = cancel_event or asyncio.Event()
        working = _sanitize_messages(list(messages))

        for _ in range(MAX_ITERATIONS):
            if cancel_event.is_set():
                yield {"type": "stop", "reason": "cancelled"}
                return

            text_parts: list[str] = []
            tool_calls: list[dict] = []
            stop_reason = "stop"

            try:
                async for event in self.adapter.run(system_prompt, working, tools):
                    if cancel_event.is_set():
                        yield {"type": "stop", "reason": "cancelled"}
                        return

                    etype = event.get("type")
                    if etype == "text_delta":
                        text_parts.append(event.get("content", ""))
                        yield event
                    elif etype == "tool_call":
                        tool_calls.append(event)
                        yield event
                    elif etype == "stop":
                        stop_reason = event.get("reason", "stop")
            except Exception as exc:  # provider failure
                yield {"type": "error", "message": f"model error: {exc}"}
                yield {"type": "stop", "reason": "error"}
                return

            # Record the assistant turn.
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(text_parts),
            }
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": c["id"],
                        "type": "function",
                        "function": {
                            "name": c["name"],
                            "arguments": json.dumps(c.get("args", {})),
                        },
                    }
                    for c in tool_calls
                ]
            working.append(assistant_msg)

            if not tool_calls:
                yield {"type": "stop", "reason": stop_reason}
                return

            # Execute each tool call (with optional permission gating).
            for call in tool_calls:
                if cancel_event.is_set():
                    yield {"type": "stop", "reason": "cancelled"}
                    return

                call_id = call["id"]
                name = call["name"]
                args = call.get("args", {}) or {}

                decision = await self.permission_cb(call_id, name, args)
                if not decision.get("allow", True):
                    reason = decision.get("reason", "denied by user")
                    result = {
                        "output": "",
                        "truncated": False, 
                        "error": reason
                    }
                else:
                    updated = decision.get("updatedArgs")
                    if updated is not None:
                        args = updated
                    result = await asyncio.to_thread(
                        self.executor.execute, name, args
                    )

                yield {
                    "type": "tool_result",
                    "id": call_id,
                    "name": name,
                    "result": result,
                }
                working.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": name,
                        "content": _format_tool_result(result),
                    }
                )

        yield {"type": "stop", "reason": "max_iterations"}


def _format_tool_result(result: dict) -> str:
    if result.get("error"):
        return f"ERROR: {result['error']}"
    out = result.get("output", "")
    if result.get("truncated"):
        out += "\n[... output truncated ...]"
    return out
