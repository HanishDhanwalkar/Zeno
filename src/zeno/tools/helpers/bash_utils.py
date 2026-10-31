from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from src.zeno.config.settings import settings
from src.zeno.tools.helpers.exec import ExecResult


def _resolve_timeout(timeout: float | None) -> float:
    """Resolve the effective timeout: default from settings, clamped to the configured max.

    A model-supplied value is clamped to ``settings.bash_timeout_s`` (the model cannot extend
    its own leash) and must be positive (else a model-correctable :class:`ModelRetry`).
    """
    if timeout is None:
        return settings.bash_timeout_s
    if timeout <= 0:
        raise ModelRetry("timeout must be a positive number of seconds.")
    return min(timeout, settings.bash_timeout_s)


def _render(result: ExecResult, *, timeout_s: float) -> str:
    """Render an :class:`ExecResult` into the model-facing reply (status + truncated streams).

    A header states the exit code (flagging a timeout); each non-empty stream is appended as a
    labelled, truncated section (empty streams omitted). A non-empty ``result.note`` is appended
    last; an empty ``note`` (every ``none``-mode result) leaves the output **byte-identical** to
    before the field existed (ADR-0011 §2).
    """
    if result.timed_out:
        header = (
            f"Command timed out after {timeout_s:g}s and was terminated "
            f"(exit code {result.exit_code}). Partial output below."
        )
    else:
        header = f"Exit code: {result.exit_code}."

    sections = [header]
    stdout_section = _stream_section("stdout", result.stdout)
    if stdout_section:
        sections.append(stdout_section)
    stderr_section = _stream_section("stderr", result.stderr)
    if stderr_section:
        sections.append(stderr_section)
    if result.note:
        sections.append(result.note)
    return "\n\n".join(sections)


def _stream_section(label: str, content: str) -> str | None:
    """Format one captured stream as a labelled"""
    if content == "":
        return None
    body = content.text.rstrip("\n")

    return f"{label}:\n{body}"
