

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from collections.abc import Callable

from pydantic_ai import Agent, DeferredToolRequests, RunContext
from pydantic_ai import ToolDefination

from zeno.permissions.types import ToolKind
from zeno.tools.files import read


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
    ToolSpec(name=files.READ_TOOL_NAME, read, "read_only", 3)
]
