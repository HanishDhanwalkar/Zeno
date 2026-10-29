from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from src.zeno.entities import events


EventSink = Callable[[events.Event], None]

@dataclass(slots=True)
class AgentDeps:
    """What an agent run carries: cwd, event sink, gate, decsion resolvers, task store"""

    cwd: Path
    emit: EventSink
    # gate: 
    # active_agent: AgentDef
    harness_home: Path | None = None
    context_window_tokens: int | None = None
    
    def __post__init(self) -> None:
        """``harness_home`` to ``cwd``"""
        if self.harness_home is None:
            self.harness_home = self.cwd