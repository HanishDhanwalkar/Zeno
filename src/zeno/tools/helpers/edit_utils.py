from __future__ import annotations

from pydantic_ai import ModelRetry

# UTF-8 BOM: stripped before matching, restored verbatim on write so an edit never drops/adds it.
_UTF8_BOM = "﻿"


def _apply_edit(raw_text: str, old_string: str, new_string: str) -> str:
    """Apply edit's unique-match replacement to ``raw_text``"""
    had_bom = raw_text.startswith(_UTF8_BOM)
    body = raw_text[len(_UTF8_BOM) :] if had_bom else raw_text

    eol = _detect_eol(body)
    normalized = _to_lf(body)
    needle = _to_lf(old_string)
    new_normalized = _replace_unique(normalized, needle, _to_lf(new_string))
    restored = new_normalized.replace("\n", eol) if eol != "\n" else new_normalized
    return (_UTF8_BOM + restored) if had_bom else restored


def _detect_eol(text: str) -> str:
    """Return the dominant line-ending style of ``text``: CRLF checked first, then lone CR, else LF."""
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text:
        return "\r"
    return "\n"


def _to_lf(text: str) -> str:
    """Normalize CRLF and lone-CR line endings to LF (so matching is newline-agnostic)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _replace_unique(haystack: str, needle: str, replacement: str) -> str:
    """Replace the single occurrence of ``needle`` in ``haystack`` (exact, then fuzzy)."""
    exact = haystack.count(needle)
    if exact == 1:
        return haystack.replace(needle, replacement, 1)
    if exact > 1:
        raise ModelRetry(
            f"old_string is ambiguous, {exact} matches found; add surrounding context to "
            "old_string so it identifies exactly one location."
        )

    span = _fuzzy_unique_span(haystack, needle)
    if span is None:
        raise ModelRetry(
            "old_string not found in the file; it must match the file's current text "
            "(check for typos, indentation, or stale content)."
        )
    start, end = span
    return haystack[:start] + replacement + haystack[end:]


def _fuzzy_unique_span(haystack: str, needle: str) -> tuple[int, int] | None:
    """Find the unique ``[start, end)`` span in ``haystack`` matching ``needle`` after whitespace collapse.

    Scans spans that begin/end on non-whitespace and keeps those whose :func:`_normalize_ws`
    form equals the normalized ``needle``. Returns the single match, ``None`` for zero, and
    raises :class:`pydantic_ai.ModelRetry` (``ambiguous``) for more than one *distinct* span.
    Cold path (exact match missed, bounded files, human-gated), so the all-pairs scan is fine.
    """
    target = _normalize_ws(needle)
    if target == "":
        return None

    starts = [i for i, ch in enumerate(haystack) if not ch.isspace()]
    ends = [i + 1 for i, ch in enumerate(haystack) if not ch.isspace()]
    matches: list[tuple[int, int]] = []
    for start in starts:
        for end in ends:
            if end <= start:
                continue
            if _normalize_ws(haystack[start:end]) == target:
                matches.append((start, end))

    # Keep the shortest end per start: longer ends differ only by whitespace already absorbed.
    minimal = _minimal_spans(matches)
    if not minimal:
        return None
    if len(minimal) > 1:
        raise ModelRetry(
            f"old_string is ambiguous, {len(minimal)} matches found (after normalizing "
            "whitespace); add surrounding context so it identifies exactly one location."
        )
    return minimal[0]


def _normalize_ws(text: str) -> str:
    """Collapse whitespace runs to single spaces and strip the ends — the fuzzy-match key."""
    return " ".join(text.split())


def _minimal_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Reduce ``spans`` to the distinct minimal-length match per start (distinct starts → ambiguous upstream)."""
    shortest_by_start: dict[int, tuple[int, int]] = {}
    for start, end in spans:
        current = shortest_by_start.get(start)
        if current is None or end < current[1]:
            shortest_by_start[start] = (start, end)
    return sorted(shortest_by_start.values())
