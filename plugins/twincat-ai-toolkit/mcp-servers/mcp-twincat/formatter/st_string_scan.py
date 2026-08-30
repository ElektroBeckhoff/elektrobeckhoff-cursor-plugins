"""Scan IEC 61131-3 ST string literals including Influx/SQL dollar-quoted regions.

Inside a single-quoted ST string, ``$'...$'`` (Influx/SQL dollar quoting) is treated
as one escaped unit so inner ``'`` characters do not terminate the ST string early.

Short fragments like ``'$'`` (no closing ``$'``) still terminate at the next ``'``.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator


def _find_dollar_quote_close(source: str, start: int) -> int:
    """Find closing ``$'`` for an Influx/SQL dollar-quoted region.

    Skips ``'$'`` ST fragments (single-quoted ``$`` only) which also contain
    a ``$'`` substring but are not dollar-quote closers. Search is limited to
    the current source line because ST string literals do not span lines.
    """
    line_end = source.find("\n", start)
    if line_end == -1:
        line_end = len(source)
    i = start
    while True:
        pos = source.find("$'", i)
        if pos == -1 or pos >= line_end:
            return -1
        if pos > 0 and source[pos - 1] == "'":
            i = pos + 2
            continue
        return pos


def iter_st_string_spans(source: str) -> Iterator[tuple[int, int]]:
    """Yield ``(start, end)`` half-open spans of ST string literals in *source*."""
    if "'" not in source and '"' not in source:
        return

    i = 0
    n = len(source)
    while i < n:
        quote = source[i]
        if quote not in ("'", '"'):
            q1 = source.find("'", i)
            q2 = source.find('"', i)
            if q1 == -1 and q2 == -1:
                break
            if q1 == -1:
                i = q2
            elif q2 == -1:
                i = q1
            else:
                i = min(q1, q2)
            quote = source[i]

        start = i
        i += 1
        content_start = i
        while i < n:
            if quote == "'" and source[i : i + 2] == "''":
                if i == content_start:
                    i = start + 2
                    break
                i += 2
                continue
            if quote == '"' and source[i : i + 2] == '""':
                if i == content_start:
                    i = start + 2
                    break
                i += 2
                continue
            if quote == '"' and source[i : i + 2] == '$"':
                i += 2
                continue
            if quote == "'" and source[i : i + 2] == "$'":
                if i + 2 < n and source[i + 2] == "'":
                    i += 2
                    if i < n and source[i] == quote:
                        i += 1
                    break
                close = _find_dollar_quote_close(source, i + 2)
                if close != -1:
                    i = close + 2
                    continue
                if source[i + 1] == "'":
                    i += 2
                    break
            if source[i] == quote:
                i += 1
                break
            i += 1
        yield start, i


def sub_st_string_literals(source: str, repl: Callable[[str], str]) -> str:
    """Replace each string literal in *source* with ``repl(literal_text)``."""
    if "'" not in source and '"' not in source:
        return source

    spans = list(iter_st_string_spans(source))
    if not spans:
        return source

    parts: list[str] = []
    last = 0
    for start, end in spans:
        parts.append(source[last:start])
        parts.append(repl(source[start:end]))
        last = end
    parts.append(source[last:])
    return "".join(parts)
