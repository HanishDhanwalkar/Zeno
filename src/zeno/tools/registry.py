

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from collections.abc import Awaitable, Callable

from pydantic_ai import Agent, DeferredToolRequests, RunContext
from pydantic_ai.tools import ToolDefinition

from src.zeno.agent.deps import AgentDeps
from src.zeno.permissions.types import ToolKind
from src.zeno.tools import files
from src.zeno.tools import bash


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One registered tool: ``name``, ``func``, it's class. ``reties``
    ``kind`` is tool's permission classification
    ``func`` is bare tool function (takes ``ctx`` as its 1st arg)
    """
    name: str
    func: Callable[..., object]
    kind: ToolKind
    retries: int | None = None


TOOL_SPECS: list[ToolSpec] = [
    # read_only tools
    ToolSpec(name=files.READ_TOOL_NAME, func=files.read, kind=ToolKind.READ_ONLY),
    ToolSpec(name=files.WRITE_TOOL_NAME, func=files.write, kind=ToolKind.FILE_EDIT),
    ToolSpec(name=files.EDIT_TOOL_NAME, func=files.edit, kind=ToolKind.FILE_EDIT),
    ToolSpec(name=bash.BASH_TOOL_NAME, func=bash.bash, kind=ToolKind.OTHER),
]

TOOL_KIND: dict[str, ToolKind] = {spec.name: spec.kind for spec in TOOL_SPECS}


def register_tools(agent: Agent[AgentDeps, str | DeferredToolRequests]) -> None:
    """Register every :data:`TOOL_SPECS` function on ``agent`` with per-agent restriction (ADR-0003 §6).

    Called once by the factory. Each tool takes ``ctx: RunContext[AgentDeps]`` first, so it is
    registered with ``agent.tool`` (context-aware), not ``agent.tool_plain``. 
    Each is registered with a per-tool ``prepare=`` callback (:func:`_restrict_to_active_agent`) that hides the tool —
    returns ``None`` so it is absent from the model's schema **for that run** — when it is not in
    ``ctx.deps.active_agent.tools``. One Agent, no rebuild: switching the active agent changes the
    visible tool set on the next turn (spike-confirmed against pydantic-ai 2.22). ``retries=None``
    (every tool but ``agent``) leaves the Agent's default budget in place.
    """
    for spec in TOOL_SPECS:
        agent.tool(spec.func, prepare=_prepare_for(spec.name), retries=spec.retries)
    print(f"registered {len(TOOL_SPECS)} tools: { [s.name for s in TOOL_SPECS]}")


def _prepare_for(
    tool_name: str,
) -> Callable[[RunContext[AgentDeps], ToolDefinition], Awaitable[ToolDefinition | None]]:
    """Build the ``prepare=`` callback for ``tool_name`` — active-agent restriction, plus bash's description.

    Every tool gets :func:`_restrict_to_active_agent`; ``bash`` additionally gets its mode-specific
    description via :func:`zeno.tools.bash.bash_description` (ADR-0011 §4). ``none`` mode returns the
    definition untouched; ``docker`` / ``modal`` return a :func:`dataclasses.replace` copy with the
    sandbox paragraph appended (``tool_def`` is rebuilt fresh per run, so composing from it is safe).
    """
    restrict = _restrict_to_active_agent(tool_name)
    if tool_name != bash.BASH_TOOL_NAME:
        return restrict

    async def prepare(
        ctx: RunContext[AgentDeps], tool_def: ToolDefinition
    ) -> ToolDefinition | None:
        prepared = await restrict(ctx, tool_def)
        if prepared is None:
            return None
        base = prepared.description or ""
        describe = getattr(bash, "bash_description", None)
        if describe is None:
            return prepared
        described = describe(base)
        if described == base:
            return prepared  # none mode: no change → byte-identical (untouched definition)
        return dataclasses.replace(prepared, description=described)

    return prepare

def _restrict_to_active_agent(
    tool_name: str,
) -> Callable[[RunContext[AgentDeps], ToolDefinition], Awaitable[ToolDefinition | None]]:
    """Build the per-tool ``prepare=`` callback hiding ``tool_name`` when the agent disallows it.

    ``prepare`` runs at schema-build time per run; returning ``None`` drops the tool from the
    model-facing schema. Reading ``ctx.deps.active_agent.tools`` makes the active agent's
    allowlist take effect per turn with no rebuild (ADR-0003 §6).
    """

    async def prepare(
        ctx: RunContext[AgentDeps], tool_def: ToolDefinition
    ) -> ToolDefinition | None:
        active = getattr(ctx.deps, "active_agent", None)
        tools = getattr(active, "tools", None)
        if tools is None:
            return tool_def
        if tool_name in tools:
            return tool_def
        return None

    return prepare