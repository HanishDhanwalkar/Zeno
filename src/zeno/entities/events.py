"""event union the harness emits"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class TurnStarted:
    turn_id: int
    prompt: str
    kind: Literal["turn_started"] = "turn_started"


@dataclass(frozen=True, slots=True)
class TurnFinished:
    turn_id: int
    aborted: bool = False
    kind: Literal["turn_finished"] = "turn_finished"


@dataclass(frozen=True, slots=True)
class AssistantTextDelta:
    text: str
    kind: Literal["assistant_text_delta"] = "assistant_text_delta"


@dataclass(frozen=True, slots=True)
class ThinkingDelta:
    text: str
    kind: Literal["thinking_delta"] = "thinking_delta"


@dataclass(frozen=True, slots=True)
class ToolCallStarted:
    tool_call_id: str
    name: str
    args: str
    child_index: int | None = None
    kind: Literal["tool_call_started"] = "tool_call_started"
    

@dataclass(frozen=True, slots=True)
class ToolResult:
    tool_call_id: str
    name: str
    args: str
    child_index: int | None = None
    kind: Literal["tool_result"] = "tool_result"

@dataclass(frozen=True, slots=True)
class PermissionRequested:
    tool_call_id: str
    name: str
    args: str
    kind: Literal["permission_requested"] = "permission_requested"


@dataclass(frozen=True, slots=True)
class AskUserRequested:
    question: str
    kind: Literal["ask_user_requested"] = "ask_user_requested"


@dataclass(frozen=True, slots=True)
class TaskListUpdated:
    tasks: list[str]
    kind: Literal["task_list_updated"] = "task_list_updated"


@dataclass(frozen=True, slots=True)
class ContextCompacted:
    before_tokens: int
    kept_messages: int
    kind: Literal["context_compacted"] = "context_compacted"


@dataclass(frozen=True, slots=True)
class ContextMicrocompacted:
    before_tokens: int
    elided_count: int
    kind: Literal["context_microcompacted"] = "context_microcompacted"


@dataclass(frozen=True, slots=True)
class AgentError:
    message: str
    kind: Literal["agent_error"] = "agent_error"


Event = (
    TurnStarted
    | TurnFinished
    | AssistantTextDelta
    | ThinkingDelta
    | ToolCallStarted
    | ToolResult
    | PermissionRequested
    | AskUserRequested
    | TaskListUpdated
    | ContextCompacted
    | ContextMicrocompacted
    | AgentError
)
