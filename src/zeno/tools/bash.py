"""``bash`` tool — run a shell command under the executor seam"""

from __future__ import annotations
from pathlib import Path

from pydantic_ai import ApprovalRequired, ModelRetry, RunContext

from src.zeno.agent.deps import AgentDeps
from src.zeno.tools.helpers.exec import CommandExecutor, LocalExecutor, ExecResult, _get_executor
from src.zeno.tools.helpers import bash_utils

BASH_TOOL_NAME = "bash"


def bash_description(base: str) -> str:
    """Return the bash tool description, preserving the base schema text."""
    return base


# Keep the bash tool and the shared executor seam aligned: tests patching the executor on this
# module should still drive the singleton used by the shell runner.
_EXECUTOR: CommandExecutor = LocalExecutor()


def reset_executor() -> None:
    """Restore the default local executor and keep both references in sync."""
    global _EXECUTOR
    _EXECUTOR = LocalExecutor()
    from src.zeno.tools.helpers import exec as exec_mod

    exec_mod._EXECUTOR = _EXECUTOR


async def close_executor() -> None:
    global _EXECUTOR
    executor = _EXECUTOR
    _EXECUTOR = LocalExecutor()
    from src.zeno.tools.helpers import exec as exec_mod

    exec_mod._EXECUTOR = _EXECUTOR

    aclose = getattr(executor, "aclose", None)
    if aclose is not None:
        await aclose()
        return
    close = getattr(executor, "close", None)
    if close is not None:
        close()


async def bash(
    ctx: RunContext[AgentDeps],
    command: str,
    timeout: float | None = None,
) -> str:
    """Run a shell ``command`` in the working directory and report its result.
    
    ``command`` runs through a shell (pipes, redirects, ``&&`` all work) under
    ``ctx.deps.cwd``. ``timeout`` is an optional wall-clock limit in seconds; it defaults to
    ``settings.bash_timeout_s`` and is clamped to that maximum (a model cannot ask for longer).
    The reply states the exit code, notes a timeout if one happened, and includes each non-empty
    stream (truncated to 2000 lines / 50 KB with the full content spilled to a temp-file path on
    overflow).
    """
    if not command.strip():
        raise ModelRetry("command is empty; provide a shell command to run.")
    
    timeout_s = bash_utils._resolve_timeout(timeout)
    
    res = await _get_executor().run(
        command=command,
        cwd=ctx.deps.cwd,
        timeout_s=timeout_s
    )
    
    return bash_utils._render(result=res, timeout_s=timeout_s)