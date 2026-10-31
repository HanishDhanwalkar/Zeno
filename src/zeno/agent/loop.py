from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    UserPromptPart,
    ToolReturnPart,
    ModelResponse,
)
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults, ToolDenied
# from pydantic_ai.usage import RunUsage

from src.zeno.agent.deps import AgentDeps
from src.zeno.entities import events
from src.zeno.harness.runner import TurnContext, Boundary

if TYPE_CHECKING:
    from pydantic_ai.agent import AbstractAgent
    # from pydantic_ai.models import Model


class AgentTurnHandler:
    """runs ``agent.iter()`` - turn handler, carries history

    One instance per REPL session: it owns the cross-turn ``message_history``;
        - calling it with a :class:`~src.zeno.harness.runner.TurnContext` returns the async generator the runner drives.
        - ``session_id=`` makes each turn one tracing ``chat_turn`` root span grouped into a per-session Thread (ADR-0014 §4).
    """

    def __init__(
        self,
        agent: AbstractAgent[AgentDeps, str | DeferredToolRequests],
        *,
        deps: AgentDeps,
        message_history: list[ModelMessage] | None = None,
    ) -> None:

        self._agent = agent
        self._deps = deps
        self.message_history: list[ModelMessage] = list(message_history or [])
        self._persisted_count = len(self.message_history)
        self._session_log = None
        self._announced_tool_calls: set[str] = set()

        self._last_input_tokens = 0

    @property
    def last_input_tokens(self) -> int:
        """Current token estimate for the context gauge; defaults to zero until a real value exists."""
        return self._last_input_tokens

    async def __call__(self, *ctx: TurnContext) -> AsyncGenerator[Boundary, list[str]]:
        """Run one harness turn as a sequence of legs.

        The underlying Pydantic AI run is driven through the supported `Agent.run()` lifecycle rather
        than a custom stream loop. Each prompt leg hits one model request, then the runner waits at
        the `WOULD_STOP` boundary for any follow-up input.
        """
        turn_context = ctx[0] if ctx else None
        if turn_context is None:
            raise TypeError("TurnContext is required")
        next_prompt: str | None = turn_context.prompt
        pending_results: DeferredToolRequests | None = None

        try:
            while True:
                steering = yield Boundary.MODEL_REQUEST

                if pending_results is not None:
                    self._append_steering(steering=steering)
                    output = await self._run_turn(
                        turn_context,
                        deferred_results=pending_results,
                    )
                    pending_results = None
                else:
                    prompt = self._compose_prompt(next_prompt, steering)
                    next_prompt = None

                    if prompt is None:
                        output = ""
                        self._persist_turn()
                        follow_ups = yield Boundary.WOULD_STOP
                        if not follow_ups:
                            return
                        next_prompt = "\n".join(follow_ups)
                        continue

                    output = await self._run_turn(turn_context, prompt=prompt)

                if isinstance(output, DeferredToolResults):
                    pending_results = await self._resolve_deferred(turn_context, output)
                    continue

                if isinstance(output, str):
                    parsed_tool_call = self._parse_text_tool_call(output)
                    if parsed_tool_call is not None:
                        pending_results = await self._run_text_tool_call(
                            turn_context, parsed_tool_call
                        )
                        if pending_results is not None:
                            continue
                    turn_context.emit(events.AssistantTextDelta(text=output))

                self._persist_turn()
                follow_ups = yield Boundary.WOULD_STOP
                if not follow_ups:
                    return
                next_prompt = "\n".join(follow_ups)

        finally:
            self._persist_turn()

    @staticmethod
    def _compose_prompt(base: str | None, steering: list[str]) -> str | None:
        """Prepend drained steering to the leg's user prompt; ``None`` means nothing to send."""
        parts = [*steering]
        if base is not None:
            parts.append(base)
        if not parts:
            return None
        return "\n".join(parts)

    @staticmethod
    def _parse_text_tool_call(content: Any) -> tuple[str, dict[str, Any]] | None:
        """Normalize a model response that embeds a JSON tool call as plain text."""
        if not isinstance(content, str):
            return None

        candidate = content.strip()
        bash_block = re.fullmatch(
            r"```(?:bash|sh)[ \t]*\r?\n(.*?)\r?\n```",
            candidate,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if bash_block is not None and bash_block.group(1).strip():
            return "bash", {"command": bash_block.group(1).strip()}

        if candidate.endswith("```"):
            closing_fence = len(candidate) - 3
            opening_fence = candidate.rfind("```", 0, closing_fence)
            if opening_fence >= 0:
                fenced = candidate[opening_fence : closing_fence + 3].splitlines()
                if (
                    len(fenced) >= 3
                    and fenced[0].strip().casefold() in {"```", "```json"}
                    and fenced[-1].strip() == "```"
                ):
                    candidate = "\n".join(fenced[1:-1]).strip()

        decoder = json.JSONDecoder()
        for index, character in enumerate(candidate):
            if character != "{":
                continue
            try:
                value, end = decoder.raw_decode(candidate, index)
            except json.JSONDecodeError:
                continue
            if candidate[end:].strip():
                continue
            if (
                isinstance(value, dict)
                and set(value) == {"name", "arguments"}
                and isinstance(value["name"], str)
                and isinstance(value["arguments"], dict)
            ):
                return value["name"], value["arguments"]
        return None

    async def _run_text_tool_call(
        self, ctx: TurnContext, parsed: tuple[str, dict[str, Any]]
    ) -> DeferredToolResults | None:
        """Execute a parsed JSON tool call from a plain-text assistant response."""
        tool_name, arguments = parsed
        tool = self._agent._function_toolset.tools.get(tool_name)
        if tool is None:
            return None

        tool_call_id = f"call_{uuid4().hex}"
        call = ToolCallPart(
            tool_name=tool_name,
            args=arguments,
            tool_call_id=tool_call_id,
        )
        result = await self._execute_tool_call(ctx, call)
        return DeferredToolRequests(calls=[call]).build_results(calls={tool_call_id: result})

    async def _execute_tool_call(
        self,
        ctx: TurnContext,
        call: ToolCallPart,
    ) -> Any:
        """Execute one tool call in the same way the SDK would, but outside the approval gate."""
        tool = self._agent._function_toolset.tools.get(call.tool_name)
        if tool is None:
            raise KeyError(f"unknown tool for deferred execution: {call.tool_name!r}")

        arguments = call.args or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"command": arguments}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}

        ctx.emit(
            events.ToolCallStarted(
                tool_call_id=call.tool_call_id,
                name=call.tool_name,
                args=json.dumps(arguments, default=str),
            )
        )

        target = tool.function
        if getattr(tool, "takes_ctx", False):
            result = target(self._deps, **arguments)
        else:
            result = target(**arguments)

        if hasattr(result, "__await__"):
            result = await result

        ctx.emit(
            events.ToolResult(
                tool_call_id=call.tool_call_id,
                name=call.tool_name,
                args=json.dumps(arguments, default=str),
            )
        )
        return result

    def _append_steering(self, steering: list[str]) -> None:
        """Append steering to the history as a user message before a deferred resume.

        A resume leg carries no new ``user_prompt``, so steering cannot ride the prompt (ADR-0002 §4).
        """
        if not steering:
            return
        content = "\n".join(steering)
        print("appending steering to history before deferred resume: %r", content)
        self.message_history.append(
            ModelRequest(parts=[UserPromptPart(content=content)])
        )

    async def _run_turn(
        self,
        ctx: TurnContext,
        *,
        prompt: str | None = None,
        deferred_results: DeferredToolRequests | None = None,
    ) -> str | DeferredToolRequests:
        """Run one supported agent leg and return the final output.

        The custom node-streaming path is intentionally avoided here because pydantic-ai requires a
        stream to be fully finished before the next `run()` can begin; the direct `Agent.run()` call
        is the stable lifecycle for this app's single-turn prompt loop.
        """
        del ctx
        result = await self._agent.run(
            user_prompt=prompt,
            deps=self._deps,
            message_history=self.message_history,
            deferred_tool_results=deferred_results,
        )
        self.message_history = result.all_messages()
        self._persisted_count = min(self._persisted_count, len(self.message_history))
        return result.output

    async def _stream_model_node(
        self, ctx: TurnContext, node: object, run: object
    ) -> None:
        """Stream one model-request node, emitting text/thinking deltas as they arrive."""
        try:
            async with node.stream(run.ctx) as request_stream:  # type: ignore[attr-defined]
                async for event in request_stream:
                    self._emit_for_stream_event(ctx, event)
        except Exception:
            # The app is still under construction; fail safely by dropping the stream instead of
            # crashing the prompt loop. The user can still quit or retry.
            return

    async def _stream_tool_node(
        self, ctx: TurnContext, node: object, run: object
    ) -> None:
        """Stream one call-tools node, emitting ToolCallStarted / ToolResult (ADR-0002 §6)."""
        try:
            async with node.stream(run.ctx) as tool_stream:  # type: ignore[attr-defined]
                async for event in tool_stream:
                    self._emit_for_tool_event(ctx, event)
        except Exception:
            return

    def _emit_for_stream_event(self, ctx: TurnContext, event: object) -> None:
        """Best-effort model-stream bridge; intentionally permissive for the current local app."""
        delta = getattr(event, "delta", None)
        if isinstance(delta, str) and delta:
            ctx.emit(events.AssistantTextDelta(text=delta))
            return
        text = getattr(event, "content", None)
        if isinstance(text, str) and text:
            ctx.emit(events.AssistantTextDelta(text=text))

    def _emit_for_tool_event(self, ctx: TurnContext, event: object) -> None:
        """Best-effort tool stream bridge; currently ignored unless it carries explicit metadata."""
        if hasattr(event, "tool_name") and hasattr(event, "tool_call_id"):
            ctx.emit(
                events.ToolCallStarted(
                    tool_call_id=str(getattr(event, "tool_call_id", "")),
                    name=str(getattr(event, "tool_name", "")),
                    args=str(getattr(event, "args", "")),
                )
            )

    def _persist_turn(self) -> None:
        """Append the messages beyond the persisted-count cursor to the session log.

        No-op when no log is wired or nothing is new; a write failure is logged and swallowed —
        persistence must never break the turn.
        """
        if self._session_log is None:
            return
        new_messages = self.message_history[self._persisted_count :]
        if not new_messages:
            return
        try:
            self._session_log.append_turn(new_messages)
        except OSError:
            print("failed to persist turn to session log", exc_info=True)
            return
        self._persisted_count = len(self.message_history)

    def _heal_dangling_tool_calls(self) -> None:
        """Heal a history ending in unprocessed tool calls before a new-prompt leg.

        A crashed leg (a tool's ``ModelRetry`` budget exhausted mid-resume) or an Esc-abort while
        a permission prompt is pending leaves the history's last message a ``ModelResponse`` whose
        tool calls never got results — pydantic-ai then rejects EVERY later prompt ("unprocessed
        tool calls"), bricking the session. Synthesize one interrupted-tool return per dangling
        call so the next leg is accepted; a deferred *resume* leg never comes through here (it
        needs the dangling call for its ``DeferredToolResults``). Covers a ``--resume`` of a
        crash-persisted log too — the seeded history heals on the first prompt.
        """
        if not self.message_history:
            return
        last = self.message_history[-1]
        if not isinstance(last, ModelResponse) or not last.tool_calls:
            return
        print(
            "healing %d unprocessed tool call(s) left by a crashed or aborted turn",
            len(last.tool_calls),
        )
        returns = [
            ToolReturnPart(
                tool_name=call.tool_name,
                tool_call_id=call.tool_call_id,
                content=(
                    "Tool call interrupted before completing (the turn crashed or was aborted); "
                    "re-issue it if still needed."
                ),
            )
            for call in last.tool_calls
        ]
        self.message_history.append(ModelRequest(parts=returns))

    async def _resolve_deferred(
        self, ctx: TurnContext, requests: DeferredToolRequests
    ) -> DeferredToolResults:
        """Turn a deferred pause into ``DeferredToolResults`` via the gate + the resolver (ADR-0003 §3).

        Allow maps to ``True``; deny to ``ToolDenied`` so the model sees the reason on the resume leg.
        External execution requests are executed here as well, so tool calls are not silently dropped
        when the model returns them as a deferred-call payload.
        """
        approvals: dict[str, bool | ToolDenied] = {}
        calls: dict[str, Any] = {}

        for call in requests.approvals:
            decision = await self._decide(ctx, call)
            if decision == "allow":
                approvals[call.tool_call_id] = True
            else:
                approvals[call.tool_call_id] = ToolDenied(decision)

        for call in requests.calls:
            calls[call.tool_call_id] = await self._execute_tool_call(ctx, call)

        return requests.build_results(approvals=approvals, calls=calls)

    async def _decide(self, ctx: TurnContext, call: object) -> str:
        """Default permission decision while the gate is not fully wired in this scaffold."""
        del ctx, call
        return "allow"

    def clear(self) -> None:
        """Reset the conversation to empty — the body of ``/clear``.

        Appends a ``clear`` marker FIRST (when a log is wired) so ``--resume`` replays to the
        post-clear state; ``OSError`` is logged and swallowed. The summarize-before-wipe memory
        write-back lives at the call site (``tui/app.py``).
        """
        if self._session_log is not None:
            try:
                self._session_log.append_clear()
            except OSError:
                print("failed to persist the clear marker", exc_info=True)
        self.message_history = []
        self._persisted_count = 0
        self._last_input_tokens = 0
        self._announced_tool_calls.clear()