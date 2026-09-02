"""Robust ST call / designator recognition for the formatter.

Handles all TwinCAT callee shapes used for multiline FB/method calls:

- ``FbName(`` / ``fbInst(``
- ``fbInst.Method(``
- ``arrFb[i](`` / ``arrFb[i].Method(``
- ``foo.bar[i].baz[j].Meth(``
- ``arr[foo[1]].Meth(`` (nested index expressions)
- ``THIS^.Method(`` / ``SUPER^.Method(`` / ``pFb^.Method(``
- ``result := arr[i].Method(`` (assignment call openers)
- ``IF NOT arr[i].Method(`` (control-flow call openers)

Indexer brackets are depth-counted (not ``[^\\]]+``), so nested ``[]``
and ``()`` inside indexes are accepted.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from formatter.st_string_scan import iter_st_string_spans

_RE_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RE_LEADING_WS = re.compile(r"^[ \t]*")
_RE_CONTROL_OPEN = re.compile(
    r"^(IF|ELSIF|WHILE|UNTIL)\b",
    re.IGNORECASE,
)
_RE_OPTIONAL_NOT = re.compile(r"^NOT\b\s*", re.IGNORECASE)

# Statement / block keywords that must not be treated as call callees.
_NON_CALL_PRIMARIES = frozenset({
    "IF", "ELSIF", "ELSE", "THEN", "END_IF",
    "CASE", "OF", "END_CASE",
    "FOR", "TO", "BY", "DO", "END_FOR",
    "WHILE", "END_WHILE",
    "REPEAT", "UNTIL", "END_REPEAT",
    "RETURN", "EXIT", "CONTINUE", "JMP",
    "TYPE", "END_TYPE", "STRUCT", "END_STRUCT", "UNION", "END_UNION",
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_GLOBAL",
    "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG", "END_VAR",
    "PROGRAM", "END_PROGRAM", "FUNCTION_BLOCK", "END_FUNCTION_BLOCK",
    "FUNCTION", "END_FUNCTION", "METHOD", "END_METHOD",
    "PROPERTY", "END_PROPERTY", "ACTION", "END_ACTION",
    "INTERFACE", "END_INTERFACE",
    "AND", "OR", "XOR", "AND_THEN", "OR_ELSE", "MOD",
    "TRUE", "FALSE",
})


@dataclass(frozen=True, slots=True)
class CallOpenerMatch:
    """Multiline call opener: indent + validated callee ending with ``(``."""

    indent: str
    callee: str

    def group(self, n: int) -> str:
        """Compat with ``re.Match.group(1)`` used by indent helpers."""
        if n == 1:
            return self.indent
        raise IndexError(n)


@dataclass(frozen=True, slots=True)
class SingleLineCall:
    """Split single-line ``prefix(params)`` / ``prefix(params);``."""

    prefix: str
    params: str
    has_semicolon: bool


def _skip_ws(text: str, i: int) -> int:
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    return i


def _string_span_map(text: str) -> list[tuple[int, int]]:
    return list(iter_st_string_spans(text))


def _in_string(spans: list[tuple[int, int]], idx: int) -> bool:
    for start, end in spans:
        if start <= idx < end:
            return True
        if idx < start:
            return False
    return False


def _skip_string_if_any(text: str, i: int, spans: list[tuple[int, int]]) -> int:
    for start, end in spans:
        if i == start:
            return end
        if i < start:
            break
    return i


def scan_st_designator(text: str, start: int = 0) -> int | None:
    """Scan a TwinCAT designator from *start*; return exclusive end or ``None``.

    Grammar (practical subset used by call sites)::

        designator ::= primary selector*
        primary    ::= IDENT
        selector   ::= '.' IDENT
                     | '^' ['.' IDENT]
                     | '[' balanced_brackets ']'
    """
    n = len(text)
    i = _skip_ws(text, start)
    if i >= n:
        return None

    m = _RE_IDENT.match(text, i)
    if not m:
        return None
    primary = m.group(0)
    if primary.upper() in _NON_CALL_PRIMARIES:
        return None
    i = m.end()
    spans = _string_span_map(text)

    while i < n:
        j = _skip_ws(text, i)
        if j >= n:
            break

        ch = text[j]
        if ch == "^":
            i = j + 1
            k = _skip_ws(text, i)
            if k < n and text[k] == ".":
                k = _skip_ws(text, k + 1)
                m2 = _RE_IDENT.match(text, k)
                if not m2:
                    return None
                i = m2.end()
            continue

        if ch == ".":
            k = _skip_ws(text, j + 1)
            m2 = _RE_IDENT.match(text, k)
            if not m2:
                return None
            i = m2.end()
            continue

        if ch == "[":
            depth = 1
            k = j + 1
            while k < n and depth > 0:
                if _in_string(spans, k):
                    k = _skip_string_if_any(text, k, spans)
                    continue
                c = text[k]
                if c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                elif c == "(":
                    # allow function calls inside index expressions
                    pass
                k += 1
            if depth != 0:
                return None
            i = k
            continue

        break

    return i if i > start else None


def _strip_line_comment(code: str) -> str:
    """Remove a trailing ``//`` comment outside strings."""
    spans = _string_span_map(code)
    i = 0
    n = len(code)
    while i < n - 1:
        if _in_string(spans, i):
            i = _skip_string_if_any(code, i, spans)
            continue
        if code[i : i + 2] == "//":
            return code[:i].rstrip()
        i += 1
    return code.rstrip()


def _callee_after_optional_assign(prefix: str) -> str | None:
    """Return the callee designator from a call prefix (may include ``:=``)."""
    code = prefix.rstrip()
    if not code:
        return None

    # Struct / array init openers: ``st := (`` or ``arr := [(``
    if re.search(r":=\s*$", code) or re.search(r":=\s*\[\s*$", code):
        return None

    assign_idx = code.rfind(":=")
    if assign_idx >= 0:
        rhs = code[assign_idx + 2:].lstrip()
        return rhs if rhs else None

    # Declaration FB ctor ``name : Type(`` is not a statement call — designator
    # scan of the full prefix fails on the type colon, so callers reject it.
    return code

def is_st_call_callee(expr: str) -> bool:
    """True when *expr* is exactly one ST designator (call target)."""
    text = expr.strip()
    if not text:
        return False
    end = scan_st_designator(text, 0)
    return end is not None and _skip_ws(text, end) >= len(text)


def match_multiline_call_opener(line: str) -> CallOpenerMatch | None:
    """Match a standalone multiline call opener line ending with ``(``."""
    raw = line.rstrip("\r\n")
    if not raw.strip():
        return None

    indent_m = _RE_LEADING_WS.match(raw)
    indent = indent_m.group(0) if indent_m else ""
    body = _strip_line_comment(raw[len(indent):]).rstrip()
    if not body.endswith("("):
        return None

    before = body[:-1].rstrip()
    if not before:
        return None

    # Control-flow openers are handled separately (IF/WHILE + designator).
    if _RE_CONTROL_OPEN.match(before):
        return None

    callee = _callee_after_optional_assign(before)
    if callee is None or not is_st_call_callee(callee):
        return None

    return CallOpenerMatch(indent=indent, callee=callee.strip())


def match_control_call_opener(line: str) -> CallOpenerMatch | None:
    """Match ``IF|ELSIF|WHILE|UNTIL [NOT] <designator>(`` openers."""
    raw = line.rstrip("\r\n")
    indent_m = _RE_LEADING_WS.match(raw)
    indent = indent_m.group(0) if indent_m else ""
    body = _strip_line_comment(raw[len(indent):]).rstrip()
    if not body.endswith("("):
        return None

    m = _RE_CONTROL_OPEN.match(body)
    if not m:
        return None

    rest = body[m.end():].lstrip()
    not_m = _RE_OPTIONAL_NOT.match(rest)
    if not_m:
        rest = rest[not_m.end():]

    before = rest[:-1].rstrip()  # drop trailing '('
    if not is_st_call_callee(before):
        return None

    return CallOpenerMatch(indent=indent, callee=before.strip())


def find_trailing_paren_pair(code: str) -> tuple[int, int] | None:
    """Return ``(open_idx, close_idx)`` of the rightmost top-level ``()`` pair."""
    spans = _string_span_map(code)
    stack: list[int] = []
    last_pair: tuple[int, int] | None = None
    i = 0
    n = len(code)
    while i < n:
        if _in_string(spans, i):
            i = _skip_string_if_any(code, i, spans)
            continue
        ch = code[i]
        if ch == "(":
            stack.append(i)
        elif ch == ")":
            if not stack:
                return None
            open_i = stack.pop()
            if not stack:
                last_pair = (open_i, i)
        i += 1
    if stack:
        return None
    return last_pair


def split_single_line_call(line: str) -> SingleLineCall | None:
    """Split a single-line FB/method call into prefix, params, and semicolon flag."""
    raw = line.rstrip("\r\n")
    code = _strip_line_comment(raw)
    if not code.strip():
        return None

    has_semi = code.rstrip().endswith(";")
    if has_semi:
        code = code.rstrip()[:-1].rstrip()

    pair = find_trailing_paren_pair(code)
    if pair is None:
        return None
    open_i, close_i = pair
    if close_i != len(code) - 1:
        # Trailing tokens after the call — not a simple call statement
        return None

    prefix = code[:open_i]
    params = code[open_i + 1 : close_i]
    callee = _callee_after_optional_assign(prefix)
    if callee is None or not is_st_call_callee(callee):
        return None

    return SingleLineCall(prefix=prefix, params=params, has_semicolon=has_semi)
