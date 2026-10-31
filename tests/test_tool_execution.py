import asyncio
from pathlib import Path
from types import SimpleNamespace

from pydantic_ai.messages import ToolCallPart
from pydantic_ai.tools import DeferredToolRequests

from src.zeno.agent.deps import AgentDeps
from src.zeno.agent.factory import build_agent
from src.zeno.agent.loop import AgentTurnHandler
from src.zeno.harness.runner import TurnContext


def _make_ctx() -> TurnContext:
    return TurnContext(turn_id=1, prompt='probe', sink=lambda event: None)


def test_parse_text_tool_call_normalizes_json() -> None:
    parsed = AgentTurnHandler._parse_text_tool_call(
        '{"name":"bash","arguments":{"command":"echo hello"}}'
    )
    assert parsed == ('bash', {'command': 'echo hello'})


def test_resolve_deferred_executes_tool_calls() -> None:
    deps = AgentDeps(
        cwd=Path.cwd(),
        harness_home=Path.cwd(),
        repo_root=Path.cwd(),
        emit=lambda event: None,
        active_agent=SimpleNamespace(name='build', tools={'bash'}, prompt=''),
    )
    agent = build_agent()
    handler = AgentTurnHandler(agent, deps=deps)
    requests = DeferredToolRequests(
        calls=[
            ToolCallPart(
                tool_name='bash',
                args={'command': 'echo hello'},
                tool_call_id='call_1',
            )
        ]
    )

    result = asyncio.run(handler._resolve_deferred(_make_ctx(), requests))

    assert result.calls['call_1']
    assert 'hello' in str(result.calls['call_1'])
