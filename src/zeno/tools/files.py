from __future__ import annotations

from pydantic_ai import Agent, DeferredToolRequests, RunContext

from src.zeno.agent.deps import AgentDeps

READ_TOOL_NAME = "read"


def read(
    ctx: RunContext[AgentDeps],
    path: str,
    offset: int | None = None,
    limit: int | None = None
) -> str:
    """read file with 1 intexed, number lines"""
    pass