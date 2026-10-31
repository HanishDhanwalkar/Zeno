from __future__ import annotations

import asyncio
import enum
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING

from src.zeno.entities import events

if TYPE_CHECKING:
    from src.zeno.tui.app import InputIntent

EventSink = Callable[[events.Event], None]


class _InteractionQueues:
    """Small queue container for steering and follow-up text from the prompt loop."""

    def __init__(self) -> None:
        self.steering: asyncio.Queue[str] = asyncio.Queue()
        self.follow_up: asyncio.Queue[str] = asyncio.Queue()

    def drain_steering(self) -> list[str]:
        items: list[str] = []
        while not self.steering.empty():
            items.append(self.steering.get_nowait())
        return items

    def drain_follow_up(self) -> list[str]:
        items: list[str] = []
        while not self.follow_up.empty():
            items.append(self.follow_up.get_nowait())
        return items

    def clear(self) -> None:
        self.drain_steering()
        self.drain_follow_up()


class Boundary(enum.Enum):
    """A point in a turn where the runner may inject queued input or stop"""

    MODEL_REQUEST = "model_request"
    WOULD_STOP = "would_stop"


class TurnContext:
    """What a turn handler may do while the runner drives it — currently just :meth:`emit`."""

    __slots__ = ("_sink", "prompt", "turn_id")

    def __init__(self, turn_id: int, prompt: str, sink: EventSink) -> None:
        self.turn_id = turn_id
        self.prompt = prompt
        self._sink = sink

    def emit(self, event: events.Event) -> None:
        """Stream one event to the TUI."""
        self._sink(event)
        
# A turn handler ``yield``s a Boundary and is sent back the messages drained at that boundary.
TurnHandler = Callable[[TurnContext], AsyncGenerator[Boundary, list[str]]]


class Phase(enum.Enum):
    """The single-flight phase machine (ADR-0002 §4).

    ``DISPATCHING`` is the synchronous window between accepting a turn and the turn task
    actually starting — it exists so the busy state is observable *before the first await*.
    """

    IDLE = "idle"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    
class Runner:
    """Drives turns one at a time, draining the queues and honoring abort at boundaries."""

    def __init__(
        self, 
        turn_handler: TurnHandler,
        *,
        on_event: EventSink
    ) -> None:
        self._turn_handler = turn_handler
        self._on_event = on_event
        self.queues = _InteractionQueues()
        self._phase = Phase.IDLE
        self._abort = False
        self._turn_task: asyncio.Task[None] | None = None
        self._next_turn_id = 0
        
    @property
    def phase(self) -> Phase:
        """The current phase of the single-flight machine."""
        return self._phase
    
    @property
    def active_turns(self) -> int:
        """How many turns are in flight (0 or 1 — single-flight)."""
        return 1 if self._turn_task is not None and not self._turn_task.done() else 0

    async def submit(self, text: str, intent: InputIntent) -> None:
        """Route one user submission by intent (ADR-0002 §4).

        On idle this starts a turn; while busy it enqueues on the steering or follow-up queue. The
        phase is set synchronously, before the first ``await``, so a racing submit cannot slip a
        second turn in.
        """
        # Import locally to avoid a module-level cycle (app imports the runner).
        from src.zeno.tui.app import InputIntent as _InputIntent

        if self.active_turns:
            if intent is _InputIntent.FOLLOW_UP:
                await self.queues.follow_up.put(text)
            else:
                await self.queues.steering.put(text)
            return

        # --- single-flight critical section: no await before the phase is set ---
        self._phase = Phase.DISPATCHING
        self._abort = False
        turn_id = self._next_turn_id
        self._next_turn_id += 1
        self._turn_task = asyncio.ensure_future(self._run_turn(turn_id, text))
        # ------------------------------------------------------------------------

    def abort(self) -> None:
        """Set the cooperative-abort flag (``Esc``); the turn stops at the next boundary."""
        self._abort = True

    async def wait_idle(self) -> None:
        """Block until the in-flight turn (if any) has finished and the runner is idle."""
        task = self._turn_task
        if task is not None:
            await task

    async def _run_turn(self, turn_id: int, prompt: str) -> None:
        """Drive one whole turn: phase RUNNING, then loop the handler's boundaries."""
        self._phase = Phase.RUNNING
        ctx = TurnContext(turn_id, prompt, self._on_event)
        self._on_event(events.TurnStarted(turn_id=turn_id, prompt=prompt))
        aborted = False

        agen = self._turn_handler(ctx)
        try:
            sent: list[str] = []
            boundary = await agen.asend(None)
            while True:
                if self._abort:
                    aborted = True
                    break
                if boundary is Boundary.MODEL_REQUEST:
                    sent = self.queues.drain_steering()
                elif boundary is Boundary.WOULD_STOP:
                    sent = self.queues.drain_follow_up()
                else:  # pragma: no cover - defensive
                    raise RuntimeError(f"unknown boundary: {boundary!r}")
                try:
                    boundary = await agen.asend(sent)
                except StopAsyncIteration:
                    break
        except Exception as exc:
            print("turn %d failed", turn_id)
            import traceback
            traceback.print_exc()
            self._on_event(events.AgentError(message=str(exc)))
        finally:
            await agen.aclose()
            if aborted:
                # keep completed history, drop pending input, back to idle.
                self.queues.clear()
            self._on_event(events.TurnFinished(turn_id=turn_id, aborted=aborted))
            self._phase = Phase.IDLE
            self._abort = False
            self._turn_task = None
