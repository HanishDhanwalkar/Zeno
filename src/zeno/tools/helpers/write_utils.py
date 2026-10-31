from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _atomic_write_bytes(target: Path, data: bytes) -> None:
    """Write ``data`` to ``target`` atomically-ish (sibling temp file + ``os.replace``).

    A reader never sees a half-written file and a crash mid-write leaves the original intact;
    the temp file shares ``target``'s directory so the rename stays on one filesystem
    (``os.replace`` is atomic only within a filesystem).
    """
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".zeno-write-")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    
def _enrich(base: str, cwd: Path, path: str) -> str:
    """Append an errors-only LSP diagnostics block to a successful ``.py`` write/edit (ADR-0007).

    ``base`` (the exact ``Wrote …`` / ``Edited …`` string) is returned **unchanged** unless the
    just-written file has LSP *errors* (severity ``1``), in which case the block is appended as
    ``f"{base}\\n\\n{summary}"``. Best-effort and silent — it **swallows every exception**, so it
    can never change or break the write/edit return; no extra permission gate. In ``modal`` it is
    best-effort-disabled: host ``ty`` cannot reach the remote Workspace filesystem (ADR-0012 §7);
    ``none`` + ``docker`` run it against a real host path.
    """
    
    if not path.lower().endswith(".py"):
        return base
    try:
        # TODO
        # summary = _format_lsp_errors(lsp_service.diagnostics_on_edit(cwd, path))
        summary = None
    except Exception as exc:  # best-effort: an enricher failure never touches the edit's return
        return base
    if summary is None:
        return base
    return f"{base}\n\n{summary}"