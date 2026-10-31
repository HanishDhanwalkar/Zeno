from __future__ import annotations

from pathlib import Path
from pydantic_ai import ModelRetry, RunContext


def _rendered_numbered(
    content: str, path: str, *, offset: int | None, limit: int | None
) -> str:
    """Number ``content`` lines"""
    start = 1 if offset is None else max(offset, 1)
    line_limit = None if limit is None else max(limit, 0)

    numbered = _number_lines(content=content, start=start, limit=line_limit)
    if numbered is None:
        raise ModelRetry(f"{path!r} has no line {start}: offset is past the end line")

    # res = transcate(numbered) # TODO: implement trancation
    # text = numbered.rstrip("\n")

    return numbered.rstrip("\n")


def _number_lines(content: str, *, start: int, limit: int | None) -> str | None:
    """Render ``content`` as ``<lineno>\\t<line>`` for ``[start, start+limit)`` (``None`` = to end).

    Line numbers are absolute (1-indexed) so a windowed read re-pages correctly. Returns
    ``None`` when ``start`` is past the last line (the caller turns that into a ``ModelRetry``).
    """
    lines = content.splitlines()
    if start > len(lines):
        return None
    window = (
        lines[start - 1 :] if limit is None else lines[start - 1 : start - 1 + limit]
    )
    return "\n".join(f"{start + i}\t{line}" for i, line in enumerate(window))


