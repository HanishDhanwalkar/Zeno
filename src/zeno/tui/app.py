from __future__ import annotations

import asyncio
import enum
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings, KeyPressEvent
from prompt_toolkit.patch_stdout import patch_stdout
from pydantic_ai.messages import ModelMessage
from rich.console import Console
from rich.text import Text

from src.zeno.entities import events
from src.zeno.tui import render
from src.zeno.agent.deps import AgentDeps
from src.zeno.agent.loop import AgentTurnHandler
from src.zeno.agent.factory import build_agent
from src.zeno.config.settings import settings, llm_model_settings
from src.zeno.harness.runner import Runner, Phase

_ASSISTANT_PREFIX = "Zeno "

# slash cmds
_CLEAR_COMMAND = "/clear"

_PROMPT = "> "

_DEFAULT_AGENT = "build"


def _resolve_workspace(repo: str | None) -> tuple[Path, Path | None]:
    """Resolve the active workspace root and repo root for the session.

    If ``repo`` is explicitly given and points to a local path, it wins. Otherwise the current
    working directory is used, and if that directory is inside a git repo we use the git root.
    """
    base = Path.cwd().resolve()
    if repo:
        candidate = Path(repo).expanduser().resolve()
        if candidate.exists():
            base = candidate
    repo_root = None
    try:
        import subprocess

        result = subprocess.run(
            ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        repo_root = Path(result.stdout.strip()).resolve()
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
        repo_root = None
    if repo_root is None:
        repo_root = base
    return base, repo_root


async def run_app(
    console: Console | None = None,
    *,
    agent: str = _DEFAULT_AGENT,
    mode: str | None = None,
    repo: str | None = None,
) -> None:

    console = console or Console()

    agent_name = agent
    agent = build_agent()

    _on_event = _make_event_sink(console)
    tool_scope, repo_root = _resolve_workspace(repo)
    harness_home = Path.cwd().resolve()

    deps = AgentDeps(
        cwd=tool_scope,
        harness_home=harness_home,
        repo_root=repo_root,
        emit=_on_event,
        context_window_tokens=None,  # TODO
    )

    def emit_line(text: str) -> None:
        console.print(render.render_event(events.AssistantTextDelta(text=text)))

    def toggle_verbose() -> None:
        # Mutates the flag ON ``deps`` (never a captured copy), so a fan-out already in flight sees
        # the new state on its very next child event (ADR-0013 §8 amendment).
        emit_line(verbose_switch_confirmation(deps.verbose.toggle()))

    handler = AgentTurnHandler(
        agent,
        deps=deps,
        message_history=[],
    )
    runner = Runner(handler, on_event=_on_event)

    session: PromptSession[object] = PromptSession(
        key_bindings=_build_key_bindings(on_toggle_verbose=toggle_verbose),
        # Skills are a harness artifact → complete from Harness Home, not the Workspace (§6).
        completer=SlashCompleter(harness_home),
        complete_while_typing=True,
        # Re-render the footer on a timer so the spinner animates while a turn runs.
        refresh_interval=_FOOTER_REFRESH_S,
        # ``handler`` / ``runner`` are bound a few lines below; the lambda runs only during the
        # prompt loop (after they exist), so the late-bound reference is safe.
        bottom_toolbar=lambda: _bottom_toolbar(deps, handler, runner),
    )
    
    # The active model id per provider (same mapping as factory._build_model's branches).
    active_model = {
        "gemini": llm_model_settings.gemini_model,
        "openrouter": llm_model_settings.openrouter_model,
        "ollama": llm_model_settings.ollama_model,
    }[settings.llm_provider]
    console.print(
        render.render_event(
            events.AssistantTextDelta(
                text=startup_banner(settings.llm_provider, active_model)
            )
        )
    )
    
    with patch_stdout(raw=True):
        while True:
            try:
                submitted = await session.prompt_async(_PROMPT)
            except EOFError:  # Ctrl-D
                break

            intent, text = _interpret(submitted)

            if is_quit_command(text):
                break

            if intent is InputIntent.ABORT:
                print("abort intent: setting cooperative-abort flag")
                runner.abort()
                continue

            if is_clear_command(text):
                await _handle_clear_command(handler, runner, cwd=harness_home, emit=emit_line)
                continue

            print(
                f"submit intent={intent.value} phase={runner.phase.value} text={text}"
            )
            await runner.submit(text, intent)


    # # On-exit LSP teardown (ADR-0007 §6): best-effort + idempotent; never blocks exit or masks
    # # the ``Decode - bye.`` line.
    # try:
    #     await shutdown_lsp_servers()
    # except Exception:
    #     logger.warning("lsp shutdown on exit failed; continuing shutdown", exc_info=True)

    console.print(render.render_event(events.AssistantTextDelta(text="Zeno - bye.")))
    


class InputIntent(enum.Enum):
    """What the user signalled with the submitted line (ADR-0002 §4-5).

    Plain ``Enter`` → STEER (new turn when idle, steer when busy); ``Alt+Enter`` → FOLLOW_UP;
    ``Esc`` → ABORT.
    """

    STEER = "steer"
    FOLLOW_UP = "follow-up"
    ABORT = "abort"


def _make_event_sink(console: Console) -> Callable[[events.Event], None]:
    """Build the harness event sink that renders events append-style above the pinned prompt.

    Owns the one piece of state the pure renderer cannot: the once-per-turn ``Zeno `` prefix,
    printed before a turn's first answer delta and re-armed on each ``TurnStarted``.
    """
    # Streamed deltas are LINE-BUFFERED: ``patch_stdout()`` redraws output above the live prompt
    # and corrupts partial-line writes, so we accumulate and print only COMPLETE lines (split on
    # the model's own ``\n``), flushing the partial tail when the turn ends or any non-streamed
    # event interrupts.
    state = {"need_prefix": False, "buffer": "", "style": render.CONVERSATION_BG}

    def _emit_line(text: str) -> None:
        style = state["style"]
        if state["need_prefix"] and style == render.CONVERSATION_BG:
            console.print(Text(_ASSISTANT_PREFIX + text, style=style))
            state["need_prefix"] = False
        else:
            console.print(Text(text, style=style))

    def _flush() -> None:
        if state["buffer"]:
            _emit_line(state["buffer"])
            state["buffer"] = ""

    def _stream(text: str, style: str) -> None:
        if state["buffer"] and state["style"] != style:
            _flush()  # a different stream kind (thinking vs answer) ended — close its line
        state["style"] = style
        state["buffer"] += text
        while "\n" in state["buffer"]:
            line, state["buffer"] = state["buffer"].split("\n", 1)
            _emit_line(line)

    def on_event(event: events.Event) -> None:
        if isinstance(event, events.AssistantTextDelta):
            _stream(event.text, render.CONVERSATION_BG)
            return
        if isinstance(event, events.ThinkingDelta):
            _stream(event.text, "dim italic")
            return
        # Non-streamed event: flush the buffered partial line, arm a new turn's prefix on
        # TurnStarted, then render the event on its own line.
        _flush()
        if isinstance(event, events.TurnStarted):
            state["need_prefix"] = True
        console.print(render.render_event(event))

    return on_event


class SlashCompleter(Completer):
    """Autocomplete the slash commands + project skills as the user types ``/``.

    Built once per session from ``load_skills(cwd)``. Fires **only** while the line-before-cursor
    is a single ``/`` token (no space yet), so normal prose and command arguments never trigger it.
    """

    def __init__(self, cwd: Path) -> None:
        self._meta = {
            # _AGENT_COMMAND: "switch the active agent (/agent <name>)",
            # _MODE_COMMAND: "switch the permission mode (/mode <name>)",
            # _COMPACT_COMMAND: "compact the conversation now",
            _CLEAR_COMMAND: "clear the conversation (summarizes to memory first)",
            # _QUIT_COMMAND: "exit Zeno",
        }
        # self._meta.update(
        #     {f"/{name}": skill.description for name, skill in load_skills(cwd).items()}
        # )

    def get_completions(self, document, complete_event):  # type: ignore[no-untyped-def]
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for command in sorted(self._meta):
            if command.startswith(text):
                yield Completion(
                    command, start_position=-len(text), display_meta=self._meta[command]
                )


_QUIT_COMMAND = "/quit"


def is_quit_command(line: str) -> bool:
    """True when the user asked to quit via ``/quit`` or a common plain-text alias."""
    stripped = line.strip().lower()
    return stripped in {_QUIT_COMMAND, "quit", "exit"}


# Inline lines for ``/clear`` (unlike ``/compact`` there is no event to render, so it confirms).
_CLEAR_DONE = "Zeno - conversation cleared."
_CLEAR_NOTHING = "Zeno - nothing to clear yet."
_CLEAR_BUSY = "Zeno - busy; try /clear again once the turn finishes."


async def _handle_clear_command(
    handler: AgentTurnHandler,
    runner: Runner,
    *,
    cwd: Path,
    emit: Callable[[str], None],
) -> None:
    """Wipe the conversation now — the ``/clear`` command (compaction-to-zero).

    Idle-only, like ``/compact``. **Summarize, then wipe**: the pre-clear history feeds the same
    non-fatal MEMORY.md write-back the quit path runs, then ``handler.clear()`` resets and rides a
    ``clear`` marker into the session log so ``--resume`` replays to the post-clear state.
    """
    if runner.phase is not Phase.IDLE:
        emit(_CLEAR_BUSY)
        return
    if not handler.message_history:
        emit(_CLEAR_NOTHING)
        return
    # await extract_on_exit(handler.message_history, cwd) # TODO: MEMORY
    handler.clear()
    emit(_CLEAR_DONE)


def is_clear_command(line: str) -> bool:
    """True when ``line`` is the ``/clear`` command (ignoring surrounding whitespace)."""
    return line.strip() == _CLEAR_COMMAND


def verbose_switch_confirmation(enabled: bool) -> str:
    """The one-line confirmation rendered after a Ctrl+O verbose toggle (ADR-0013 §8 amendment)."""
    if enabled:
        return "Zeno - verbose: on (subagent activity shown)."
    return "Zeno - verbose: off."

def startup_banner(provider: str, model: str) -> str:
    """The one-line startup banner: provider:model"""
    return f"Zeno - {provider}:{model} - type a line; /quit exits."


_FOOTER_REFRESH_S = 0.1


def _bottom_toolbar(
    deps: AgentDeps,
    # gate: PermissionGate,
    handler: AgentTurnHandler,
    runner: Runner,
    # decisions: DecisionChannel,
) -> HTML:
    """The footer as prompt_toolkit formatted text: a busy spinner + context fill gauge + live hint.

    Called on every render with live state, so the footer updates immediately after an agent/mode
    switch. The spinner shows only while the turn is ACTIVELY working — hidden when idle and when
    the turn is paused on the DecisionChannel awaiting a human (else it would read "working…"
    while the user is the one being asked to type). The gauge (ADR-0006 §9) reads the handler's
    public ``last_input_tokens`` over the run's resolved window (``deps.context_window_tokens``,
    task 123 — falling back to the configured one when nothing resolved it), so the gauge and the
    compaction trigger can never disagree about the denominator; ``warn_at`` / ``danger_at`` are the
    fill lines derived from the same reserve fractions the compaction cascade fires on.
    """
    window = deps.context_window_tokens
    last_tokens = handler.last_input_tokens
    if window is None or window <= 0:
        fraction = 0.0
    else:
        fraction = last_tokens / window
    warn_at = 1 - 0.40
    danger_at = 1 - 0.20
    label, color = render.context_gauge(fraction, warn_at=warn_at, danger_at=danger_at)

    agent_name = getattr(getattr(deps, "active_agent", None), "name", "build")
    mode_name = getattr(deps, "mode", "default")
    hint = footer_hint(agent_name, mode_name, verbose=deps.verbose.enabled)
    if runner.phase is Phase.IDLE:  # or decisions.pending:
        spinner = ""
    else:
        frame = render.spinner_frame(int(time.monotonic() / _FOOTER_REFRESH_S))
        spinner = f'<style fg="cyan">{frame} working…</style> '
    return HTML(f'{spinner}<style fg="{color}">{label}</style> <b>{hint}</b>')


def footer_hint(agent: str, mode: str, *, verbose: bool) -> str:
    """The bottom-toolbar hint: the live agent + mode + verbose state, then the interaction keys.

    Pure and string-returning; :func:`_bottom_toolbar` supplies the live ``agent`` / ``mode`` /
    ``verbose`` each render (ADR-0003 §9) so the footer updates after a switch. The footer is the ONLY
    place Ctrl+O is discoverable, so it names both the key and the current state.
    """
    return (
        f"agent:{agent} mode:{mode} verbose:{'on' if verbose else 'off'} | Enter steer | "
        "Alt+Enter follow-up | Esc abort | Shift+Tab mode | Ctrl+O verbose | "
        "/clear /quit"
    )


def _build_key_bindings(*, on_toggle_verbose: Callable[[], None]) -> KeyBindings:
    """Register follow-up (Alt+Enter), abort (Esc), mode-cycle (Shift+Tab), verbose (Ctrl+O).

    Alt+Enter / Esc accept the prompt with an explicit ``(intent, text)`` result. Shift+Tab and
    Ctrl+O do NOT submit: they mutate live state (the gate mode / the verbose flag) and invalidate
    the app so the toolbar redraws, leaving the typed buffer intact — a half-typed prompt survives
    a toggle (ADR-0003 §9; ADR-0013 §8 amendment).
    """
    bindings = KeyBindings()

    @bindings.add("escape", "enter")
    def _follow_up(event: KeyPressEvent) -> None:
        event.app.exit(result=(InputIntent.FOLLOW_UP, event.app.current_buffer.text))

    @bindings.add("escape")
    def _abort(event: KeyPressEvent) -> None:
        event.app.exit(result=(InputIntent.ABORT, event.app.current_buffer.text))

    @bindings.add("c-o")
    def _toggle_verbose(event: KeyPressEvent) -> None:
        on_toggle_verbose()
        event.app.invalidate()  # redraw the bottom toolbar with the new verbose state

    return bindings


def _interpret(submitted: object) -> tuple[InputIntent, str]:
    """Normalize ``prompt_async`` results into an ``(intent, text)`` pair.

    A plain ``Enter`` returns the line as a ``str`` (intent ``STEER``); the keybindings
    return an explicit ``(intent, text)`` tuple.
    """
    if isinstance(submitted, tuple):
        intent, text = submitted
        return intent, text
    return InputIntent.STEER, str(submitted)
