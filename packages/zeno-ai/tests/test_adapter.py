import asyncio

from zeno_ai.adapter import LLMAdapter


def _collect(adapter, messages, tools=None):
    async def _run():
        return [e async for e in adapter.run("sys prompt", messages, tools or [])]

    return asyncio.run(_run())


def test_mock_echoes_user_text():
    adapter = LLMAdapter(model="mock")
    events = _collect(adapter, [{"role": "user", "content": "ping"}])
    assert events[-1] == {"type": "stop", "reason": "stop"}
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert "ping" in text


def test_mock_emits_tool_call_on_directive():
    adapter = LLMAdapter(model="mock")
    events = _collect(
        adapter,
        [{"role": "user", "content": '[[tool:read {"path": "README.md"}]]'}],
    )
    calls = [e for e in events if e["type"] == "tool_call"]
    assert len(calls) == 1
    assert calls[0]["name"] == "read"
    assert calls[0]["args"] == {"path": "README.md"}
    assert events[-1] == {"type": "stop", "reason": "tool_calls"}


def test_mock_summarises_after_tool_result():
    adapter = LLMAdapter(model="mock")
    events = _collect(
        adapter,
        [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "content": None},
            {"role": "tool", "name": "read", "content": "file contents"},
        ],
    )
    text = "".join(e["content"] for e in events if e["type"] == "text_delta")
    assert "read" in text
    assert events[-1]["reason"] == "stop"
