"""Minimal JSON-RPC 2.0 server over stdio (NDJSON).

stdin/stdout carry one JSON object per line. stdout is reserved exclusively for
RPC; all logging goes to stderr. stdin is read on a dedicated thread (reliable
across platforms, incl. Windows) and fed into an asyncio queue.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from typing import Any, Awaitable, Callable

Handler = Callable[[dict], Awaitable[Any]]


def log(*args: Any) -> None:
    print("[zeno-agent-core]", *args, file=sys.stderr, flush=True)


def _sanitize_for_json(obj: Any) -> Any:
    """Recursively sanitize objects to remove surrogate characters that break JSON encoding."""
    if isinstance(obj, str):
        # Remove surrogates and replace problematic characters
        try:
            # Encode to utf-8 with replace, then decode - this removes surrogates
            return obj.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        except Exception:
            return obj
    elif isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_for_json(item) for item in obj]
    else:
        return obj


class JsonRpcServer:
    def __init__(self) -> None:
        self._request_handlers: dict[str, Handler] = {}
        self._notification_handlers: dict[str, Handler] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._write_lock = threading.Lock()
        self._tasks: set[asyncio.Task] = set()

    # -- registration -----------------------------------------------------
    def on_request(self, method: str, handler: Handler) -> None:
        self._request_handlers[method] = handler

    def on_notification(self, method: str, handler: Handler) -> None:
        self._notification_handlers[method] = handler

    # -- outbound ---------------------------------------------------------
    def _write(self, obj: dict) -> None:
        obj = _sanitize_for_json(obj)
        line = json.dumps(obj, ensure_ascii=False)
        with self._write_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def notify(self, method: str, params: dict | None = None) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _respond(self, req_id: Any, result: Any = None, error: dict | None = None) -> None:
        msg: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id}
        if error is not None:
            msg["error"] = error
        else:
            msg["result"] = result
        self._write(msg)

    # -- inbound ----------------------------------------------------------
    def _stdin_reader(self) -> None:
        for line in sys.stdin:
            if self._loop is None:
                break
            self._loop.call_soon_threadsafe(self._queue.put_nowait, line)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, None)

    def _track(self, coro: Awaitable[Any]) -> None:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _dispatch(self, msg: dict) -> None:
        method = msg.get("method")
        params = msg.get("params") or {}
        req_id = msg.get("id")

        if method is None:
            return  # responses to our own requests: unused for now

        if req_id is not None:
            handler = self._request_handlers.get(method)
            if handler is None:
                self._respond(req_id, error={"code": -32601, "message": f"method not found: {method}"})
                return
            try:
                result = await handler(params)
                self._respond(req_id, result=result)
            except Exception as exc:  # pragma: no cover - defensive
                log("request handler error:", method, exc)
                self._respond(req_id, error={"code": -32000, "message": str(exc)})
        else:
            handler = self._notification_handlers.get(method)
            if handler is None:
                log("unhandled notification:", method)
                return
            try:
                await handler(params)
            except Exception as exc:  # pragma: no cover - defensive
                log("notification handler error:", method, exc)

    async def serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        reader = threading.Thread(target=self._stdin_reader, daemon=True)
        reader.start()

        while True:
            line = await self._queue.get()
            if line is None:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as exc:
                log("invalid JSON on stdin:", exc)
                continue
            # Dispatch concurrently so notifications (e.g. cancel) aren't blocked
            # behind a long-running request.
            self._track(self._dispatch(msg))
