from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

from src.zeno.entities import events


EventSink = Callable[[events.Event], None]

@dataclass(slots=True)
class VerboseFlag:
    """The live Verbose Mode toggle (Ctrl+O): show Explore Subagent activity in the TUI.

    A MUTABLE object on the deps — deliberately, and for the same reason
    :class:`~zeno.permissions.gate.PermissionGate` is one: the user flips it MID-TURN (Ctrl+O
    while a fan-out is running), so every reader must see the new value on its very next read. The
    ``agent`` tool's child sink therefore reads ``enabled`` at EMIT time, never captures it at spawn
    time. Off by default (ADR-0013 §8 amendment).
    """

    enabled: bool = False

    def toggle(self) -> bool:
        """Flip the flag in place and return the NEW state (what the keybind renders)."""
        self.enabled = not self.enabled
        return self.enabled

@dataclass(slots=True)
class AgentDeps:
    """What an agent run carries: cwd, event sink, gate, decsion resolvers, task store"""

    cwd: Path
    emit: EventSink
    # gate:
    active_agent: object = field(
        default_factory=lambda: SimpleNamespace(
            name="build",
            tools={
                "read",
                "write",
                "edit",
                "bash",
            },
            prompt="",
        )
    )
    mode: str = "default"
    verbose: VerboseFlag = field(default_factory=VerboseFlag)
    harness_home: Path | None = None
    repo_root: Path | None = None
    context_window_tokens: int | None = None

    def __post_init__(self) -> None:
        """Default the harness + repo roots to the current working directory."""
        if self.harness_home is None:
            self.harness_home = self.cwd
        if self.repo_root is None:
            self.repo_root = self.cwd