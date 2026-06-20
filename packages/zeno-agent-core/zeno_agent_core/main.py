"""Entry point: wires the RPC server to the agent loop and tools.

Run as ``python -m zeno_agent_core.main`` (Node spawns it). Sends
``system/ready`` once imports are done so Node knows the warm start completed.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# force utf-8 encoding for stout/stderr for windows to handle unicode
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    
    
# Make the sibling zeno-ai package importable without an install step.
_PKG_ROOT = Path(__file__).resolve().parents[2]
_ZENO_AI = _PKG_ROOT / "zeno-ai"
if _ZENO_AI.is_dir():
    sys.path.insert(0, str(_ZENO_AI))

from zeno_ai import LLMAdapter  # noqa: E402

from .agent import AgentLoop  # noqa: E402
from .rpc import JsonRpcServer, log  # noqa: E402
from .tools import TOOL_SCHEMAS, ToolExecutor  # noqa: E402


class Runtime:
    def __init__(self, server: JsonRpcServer) -> None:
        self.server = server
        # streamId -> asyncio.Event for cancellation
        self._cancels: dict[str, asyncio.Event] = {}
        # (streamId, callId) -> Future[decision]
        self._permissions: dict[tuple[str, str], asyncio.Future] = {}

    # -- handlers ---------------------------------------------------------
    async def handle_run(self, params: dict) -> dict:
        stream_id = str(params.get("streamId", "default"))
        messages = params.get("messages", [])
        system_prompt = params.get("systemPrompt", "")
        tools = params.get("tools") or TOOL_SCHEMAS
        model = params.get("model", "mock")
        project_root = params.get("projectRoot") or os.getcwd()
        gate_permissions = bool(params.get("gatePermissions", True))

        adapter = LLMAdapter(model=model)
        executor = ToolExecutor(root=project_root)
        cancel_event = asyncio.Event()
        self._cancels[stream_id] = cancel_event

        async def permission_cb(call_id: str, name: str, args: dict) -> dict:
            if not gate_permissions:
                return {"allow": True}
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._permissions[(stream_id, call_id)] = fut
            self.server.notify(
                "stream/permissionRequest",
                {"streamId": stream_id, "callId": call_id, "name": name, "args": args},
            )
            try:
                return await fut
            finally:
                self._permissions.pop((stream_id, call_id), None)

        loop = AgentLoop(adapter, executor, permission_cb=permission_cb)
        final_reason = "stop"
        try:
            async for event in loop.run(
                messages, system_prompt, tools, cancel_event=cancel_event
            ):
                etype = event["type"]
                if etype == "text_delta":
                    self.server.notify(
                        "stream/textDelta",
                        {"streamId": stream_id, "content": event["content"]},
                    )
                elif etype == "tool_call":
                    self.server.notify(
                        "stream/toolCall",
                        {
                            "streamId": stream_id,
                            "id": event["id"],
                            "name": event["name"],
                            "args": event.get("args", {}),
                        },
                    )
                elif etype == "tool_result":
                    self.server.notify(
                        "stream/toolResult",
                        {
                            "streamId": stream_id,
                            "id": event["id"],
                            "name": event["name"],
                            "result": event["result"],
                        },
                    )
                elif etype == "error":
                    self.server.notify(
                        "stream/error",
                        {"streamId": stream_id, "message": event["message"]},
                    )
                elif etype == "stop":
                    final_reason = event["reason"]
        except Exception as exc:  # pragma: no cover - defensive
            log("run failed:", exc)
            self.server.notify(
                "stream/error", {"streamId": stream_id, "message": str(exc)}
            )
            final_reason = "error"
        finally:
            self._cancels.pop(stream_id, None)
            # Resolve any dangling permission futures so the loop can unwind.
            for key in [k for k in self._permissions if k[0] == stream_id]:
                fut = self._permissions.pop(key, None)
                if fut and not fut.done():
                    fut.set_result({"allow": False, "reason": "stream ended"})

        self.server.notify("stream/end", {"streamId": stream_id, "reason": final_reason})
        return {"ok": True, "reason": final_reason}

    async def handle_cancel(self, params: dict) -> None:
        stream_id = str(params.get("streamId", "default"))
        event = self._cancels.get(stream_id)
        if event is not None:
            event.set()

    async def handle_permission_decision(self, params: dict) -> None:
        stream_id = str(params.get("streamId", "default"))
        call_id = str(params.get("callId", ""))
        fut = self._permissions.get((stream_id, call_id))
        if fut is not None and not fut.done():
            fut.set_result(
                {
                    "allow": bool(params.get("allow", False)),
                    "reason": params.get("reason", ""),
                    "updatedArgs": params.get("updatedArgs"),
                }
            )


async def amain() -> None:
    server = JsonRpcServer()
    runtime = Runtime(server)
    server.on_request("agent/run", runtime.handle_run)
    server.on_notification("stream/cancel", runtime.handle_cancel)
    server.on_notification("permission/decision", runtime.handle_permission_decision)

    server.notify("system/ready", {"providers": ["mock", "litellm"]})
    log("ready")
    await server.serve()


def main() -> None:
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
