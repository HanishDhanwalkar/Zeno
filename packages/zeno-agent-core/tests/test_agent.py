import asyncio

from zeno_ai import LLMAdapter
from zeno_agent_core.agent import AgentLoop
from zeno_agent_core.tools import ToolExecutor


def _run_loop(loop_obj, messages, **kw):
    async def _go():
        return [e async for e in loop_obj.run(messages, **kw)]

    return asyncio.run(_go())


def test_loop_plain_text(tmp_path):
    loop = AgentLoop(LLMAdapter("mock"), ToolExecutor(tmp_path))
    events = _run_loop(loop, [{"role": "user", "content": "hi"}])
    assert events[-1] == {"type": "stop", "reason": "stop"}
    assert any(e["type"] == "text_delta" for e in events)


def test_loop_executes_tool_then_finishes(tmp_path):
    (tmp_path / "data.txt").write_text("the contents")
    loop = AgentLoop(LLMAdapter("mock"), ToolExecutor(tmp_path))
    events = _run_loop(
        loop,
        [{"role": "user", "content": '[[tool:read {"path": "data.txt"}]]'}],
    )
    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    results = [e for e in events if e["type"] == "tool_result"]
    assert "the contents" in results[0]["result"]["output"]
    assert events[-1]["type"] == "stop"


def test_loop_permission_denied_blocks_tool(tmp_path):
    (tmp_path / "data.txt").write_text("secret")

    async def deny(call_id, name, args):
        return {"allow": False, "reason": "nope"}

    loop = AgentLoop(LLMAdapter("mock"), ToolExecutor(tmp_path), permission_cb=deny)
    events = _run_loop(
        loop, [{"role": "user", "content": '[[tool:read {"path": "data.txt"}]]'}]
    )
    results = [e for e in events if e["type"] == "tool_result"]
    assert results[0]["result"]["error"] == "nope"


def test_loop_allow_with_null_updated_args(tmp_path):
    # Mirrors the RPC decision shape where updatedArgs is present but null.
    (tmp_path / "data.txt").write_text("payload")

    async def allow(call_id, name, args):
        return {"allow": True, "reason": "ok", "updatedArgs": None}

    loop = AgentLoop(LLMAdapter("mock"), ToolExecutor(tmp_path), permission_cb=allow)
    events = _run_loop(
        loop, [{"role": "user", "content": '[[tool:read {"path": "data.txt"}]]'}]
    )
    results = [e for e in events if e["type"] == "tool_result"]
    assert "error" not in results[0]["result"]
    assert "payload" in results[0]["result"]["output"]


def test_loop_cancellation(tmp_path):
    cancel = asyncio.Event()
    cancel.set()
    loop = AgentLoop(LLMAdapter("mock"), ToolExecutor(tmp_path))
    events = _run_loop(
        loop, [{"role": "user", "content": "hi"}], cancel_event=cancel
    )
    assert events[-1] == {"type": "stop", "reason": "cancelled"}
