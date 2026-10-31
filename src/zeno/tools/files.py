from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from src.zeno.agent.deps import AgentDeps
from src.zeno.tools.helpers import (
    read_utils, 
    files_utils, 
    write_utils,
    edit_utils
)

READ_TOOL_NAME = "read"
WRITE_TOOL_NAME = "write"
EDIT_TOOL_NAME = "edit"


def read(
    ctx: RunContext[AgentDeps],
    path: str,
    offset: int | None = None,
    limit: int | None = None,
) -> str:
    """read file with 1 intexed, number lines"""

    target = files_utils._resolve_in_cwd(ctx.deps.cwd, path)
    if not target.exists():
        raise ModelRetry(f"No such file: {path!r}")
    if target.is_dir():
        raise ModelRetry(f"{path!r} is dir; use bash tools to list contents")

    try:
        content = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ModelRetry(f"Could not read {path!r}: {e}") from e

    return read_utils._rendered_numbered(
        content=content, path=path, offset=offset, limit=limit
    )
    
def write(
    ctx: RunContext[AgentDeps],
    path: str,
    content: str
) -> str:
    """Write a file with ``content``"""
    
    target = files_utils._resolve_in_cwd(ctx.deps.cwd, path)
    if target.is_dir():
        raise ModelRetry(f"{path!r} is dir; choose file path")
    
    target.parent.mkdir(parents=True, exist_ok=True)
    
    write_utils._atomic_write_bytes(target=target, content=content.encode("utf-8"))
    
    base = f"Wrote {path!r} | length:{len(content)}"
    return write_utils._enrich(base=base, cwd=ctx.deps.cwd, path=path)
    
def edit(
    ctx: RunContext[AgentDeps], 
    path: str, 
    old_str: str, 
    new_str: str
) -> str:
    """REplace unique occurance of ``old_str`` wo ``new_str``"""

    if old_str.strip() == "":
        raise ModelRetry("old_str is empty; give exact text to replace")
    
    target = files_utils._resolve_in_cwd(ctx.deps.cwd, path)
    if not target.is_file():
        raise ModelRetry(f"No such file to edit: {path!r}")
    
    try:
        raw = target.read_bytes().decode("utf-8")
    except(OSError, UnicodeDecodeError) as e:
        raise ModelRetry(f"Could not read {path!r} to edit: {e}") from e
    
    final = edit_utils._apply_edit(raw, old_str, new_str)
    write_utils._atomic_write_bytes(target=target, data=final.encode("utf-8"))
    
    base = f"Edited {path!r} (replaced 1 occurance)"
    return write_utils._enrich(base=base, cwd=ctx.deps.cwd, path=path)
