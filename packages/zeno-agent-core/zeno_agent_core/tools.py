"""The four tools: read, write, edit, bash.

All execution happens here in Python. Each tool returns a structured result
dict: ``{output, truncated, exitCode?, error?}``. Tools never raise for
expected failure modes (missing file, bad match, command failure); they encode
the problem in ``error`` so the agent loop keeps running.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

READ_MAX_LINES = 200
BASH_MAX_LINES = 1000
BASH_TIMEOUT_SEC = 120


def _result(
    output: str = "",
    *,
    truncated: bool = False,
    error: str | None = None,
    exit_code: int | None = None,
) -> dict[str, Any]:
    res: dict[str, Any] = {"output": output, "truncated": truncated}
    if error is not None:
        res["error"] = error
    if exit_code is not None:
        res["exitCode"] = exit_code
    return res


class ToolExecutor:
    """Executes tools relative to a project root."""

    def __init__(self, root: str | os.PathLike[str] | None = None) -> None:
        self.root = Path(root or os.getcwd()).resolve()

    # -- path helpers -----------------------------------------------------
    def _resolve(self, path: str) -> Path:
        p = Path(path)
        if not p.is_absolute():
            p = self.root / p
        return p

    # -- dispatch ---------------------------------------------------------
    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = {
            "read": self.read,
            "write": self.write,
            "edit": self.edit,
            "bash": self.bash,
        }.get(name)
        if handler is None:
            return _result(error=f"unknown tool: {name}")
        try:
            return handler(**args)
        except TypeError as exc:
            return _result(error=f"bad arguments for {name}: {exc}")
        except Exception as exc:  # defensive: never crash the loop
            return _result(error=f"{type(exc).__name__}: {exc}")

    # -- tools ------------------------------------------------------------
    def read(
        self, path: str, offset: int = 0, limit: int = READ_MAX_LINES
    ) -> dict[str, Any]:
        p = self._resolve(path)
        if not p.exists():
            # Try case-insensitive search in the same directory
            try:
                parent = p.parent
                if parent.exists():
                    # Search for case-insensitive match
                    path_lower = p.name.lower()
                    for sibling in parent.iterdir():
                        if sibling.name.lower() == path_lower and sibling.is_file():
                            p = sibling
                            break
            except (OSError, ValueError):
                pass
            
            # If still not found, suggest similar files
            if not p.exists():
                suggestions = ""
                try:
                    parent = p.parent
                    if parent.exists():
                        files = [f.name for f in parent.iterdir() if f.is_file()]
                        if files:
                            suggestions = f"\nAvailable files: {', '.join(sorted(files)[:10])}"
                except (OSError, ValueError):
                    pass
                return _result(error=f"file not found: {path}{suggestions}")

        if p.is_dir():
            return _result(error=f"path is a directory: {path}")

        limit = min(int(limit), READ_MAX_LINES)
        offset = max(int(offset), 0)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return _result(error=f"could not read {path}: {exc}")

        lines = text.splitlines()
        window = lines[offset : offset + limit]
        numbered = "\n".join(
            f"{offset + i + 1:6}|{line}" for i, line in enumerate(window)
        )
        truncated = (offset + limit) < len(lines) or offset > 0
        return _result(numbered, truncated=truncated)

    def write(self, path: str, content: str) -> dict[str, Any]:
        p = self._resolve(path)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except OSError as exc:
            return _result(error=f"could not write {path}: {exc}")
        n = content.count("\n") + 1 if content else 0
        return _result(f"wrote {len(content)} bytes ({n} lines) to {path}")

    def edit(self, path: str, old_string: str, new_string: str) -> dict[str, Any]:
        p = self._resolve(path)
        if not p.exists():
            return _result(error=f"file not found: {path}")
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            return _result(error=f"could not read {path}: {exc}")

        if old_string == new_string:
            return _result(error="old_string and new_string are identical")

        count = text.count(old_string)
        if count == 0:
            return _result(error="old_string not found in file")
        if count > 1:
            return _result(
                error=f"old_string is not unique ({count} matches); add more context"
            )

        updated = text.replace(old_string, new_string, 1)
        try:
            p.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return _result(error=f"could not write {path}: {exc}")
        return _result(f"edited {path} (1 replacement)")

    async def bash(
        self, command: str, timeout: int = BASH_TIMEOUT_SEC, cwd: str | None = None, inputs: str | None = None
    ) -> dict[str, Any]:
        """Run a shell command asynchronously using asyncio subprocesses.

        Using ``asyncio.create_subprocess_shell`` keeps everything on the event
        loop — no thread blocking, no Windows pipe-drain deadlocks that plagued
        the old ``subprocess.run`` approach.
        """
        workdir = self._resolve(cwd) if cwd else self.root
        stdin_data = inputs.encode("utf-8", errors="replace") if inputs is not None else None

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
            )
        except OSError as exc:
            return _result(error=f"could not run command: {exc}")

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(input=stdin_data),
                timeout=float(timeout),
            )
        except asyncio.TimeoutError:
            # Kill gracefully then drain — all async, no deadlock risk.
            try:
                proc.kill()
            except OSError:
                pass
            try:
                await asyncio.wait_for(proc.communicate(), timeout=5.0)
            except (asyncio.TimeoutError, OSError):
                pass
            return _result(
                error=f"command timed out after {timeout}s",
                exit_code=124,
            )

        stdout = stdout_b.decode("utf-8", errors="replace") if stdout_b else ""
        stderr = stderr_b.decode("utf-8", errors="replace") if stderr_b else ""
        rc = proc.returncode if proc.returncode is not None else 1

        if inputs is not None:
            # Show a clear session summary when inputs were supplied.
            parts = [
                "=" * 60,
                "SCRIPT EXECUTION WITH INPUTS",
                f"Command: {command}",
                f"Inputs provided: {repr(inputs)}",
                "=" * 60,
                "",
            ]
            if stdout:
                parts += ["[STDOUT]", stdout]
            if stderr:
                parts += ["[STDERR]", stderr]
            parts.append(
                "[CONTEXT: Script completed successfully with provided inputs]"
                if rc == 0
                else f"[CONTEXT: Script exited with code {rc}]"
            )
            combined = "\n".join(parts)
        else:
            combined = stdout + stderr
            if rc != 0:
                combined += f"\n[Exit Code: {rc}]"

        lines = combined.splitlines()
        truncated = len(lines) > BASH_MAX_LINES
        if truncated:
            lines = lines[:BASH_MAX_LINES]

        return _result("\n".join(lines), truncated=truncated, exit_code=rc)


# Tool schemas advertised to the model (OpenAI function-calling shape).
TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file with line numbers. Max 200 lines per call.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "description": "0-based start line"},
                    "limit": {"type": "integer", "description": "max lines (<=200)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create or overwrite a file with the given content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": "Replace an exact, unique old_string with new_string.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string"},
                    "new_string": {"type": "string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command and capture stdout/stderr. If the script waits for input (times out after 3s), you can provide inputs using the 'inputs' parameter.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)"},
                    "inputs": {
                        "type": "string",
                        "description": "Inputs to send to the script stdin, separated by newlines. Example: 'yes\\n42\\nno\\n' for multiple inputs"
                    },
                },
                "required": ["command"],
            },
        },
    },
]
