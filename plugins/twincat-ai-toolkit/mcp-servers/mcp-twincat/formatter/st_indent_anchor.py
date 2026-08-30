"""Column-anchor indentation engine for IEC 61131-3 Structured Text.

When reindent is enabled, the engine walks block structure and applies
column-anchor rules (IF/CASE/FOR: body at anchor+indent, close at anchor).
By default only *structural* lines whose column differs from the computed
anchor are rewritten; assignments, FB-call parameters, and bool-chain
continuations keep their raw indent so downstream alignment passes stay
byte-stable.

Pass ``force_all=True`` to rewrite every line (used in unit tests).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from formatter.config import IndentConfig
from formatter.constants import VAR_BLOCK_KEYWORDS
from formatter.st_parse_utils import (
    get_first_keyword,
    is_case_label,
    line_ends_with_keyword,
    strip_comments_and_strings,
)


@dataclass
class _IfFrame:
    anchor: int
    body: int


@dataclass
class _CaseFrame:
    anchor: int
    label: int | None = None


@dataclass
class _LoopFrame:
    anchor: int
    body: int


@dataclass
class _BlockFrame:
    anchor: int
    body: int


Frame = _IfFrame | _CaseFrame | _LoopFrame | _BlockFrame

_RE_BOOL_CONTINUATION = re.compile(
    r"^\s*(?:AND_THEN|OR_ELSE|XOR|OR)\b",
    re.IGNORECASE,
)
_RE_OPERATOR_CONTINUATION_END = re.compile(
    r"(?:[+\-*/&]|(?<=\s)(?:AND|OR|XOR|AND_THEN|OR_ELSE))\s*$",
    re.IGNORECASE,
)

_RE_DISABLE_MARKER = re.compile(r"^\(\*\*+\)\s*")

_STRUCTURAL_KEYWORDS = frozenset({
    "IF", "ELSIF", "ELSE", "END_IF",
    "CASE", "END_CASE",
    "FOR", "WHILE", "END_FOR", "END_WHILE",
    "REPEAT", "END_REPEAT", "UNTIL",
    "TYPE", "END_TYPE", "STRUCT", "UNION", "END_STRUCT", "END_UNION",
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_GLOBAL",
    "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG", "END_VAR",
    "END_METHOD", "END_ACTION", "END_PROPERTY",
    "END_PROGRAM", "END_FUNCTION_BLOCK", "END_FUNCTION",
    "__TRY", "__CATCH", "__FINALLY", "__ENDTRY",
})


def apply_column_anchor_indentation(
    lines: list[str],
    config: IndentConfig,
    *,
    initial_stack: list[Frame] | None = None,
    force_all: bool = False,
) -> tuple[list[str], list[Frame]]:
    """Recompute indentation using column-anchor block rules."""
    size = config.size
    stack: list[Frame] = list(initial_stack) if initial_stack else []
    result: list[str] = []
    in_block_comment = False

    for idx, raw_line in enumerate(lines):
        if in_block_comment:
            result.append(raw_line)
            if "*)" in raw_line.strip():
                in_block_comment = False
            continue

        stripped = raw_line.strip()

        if not stripped:
            result.append("")
            continue

        if _RE_BOOL_CONTINUATION.match(raw_line):
            result.append(raw_line.rstrip("\r"))
            continue

        if idx > 0 and raw_line.startswith(" ") and not stripped.startswith(("END_", "ELSE", "ELSIF", "UNTIL")):
            prev_line = ""
            for p_idx in range(idx - 1, -1, -1):
                if lines[p_idx].strip():
                    prev_line = lines[p_idx].rstrip()
                    break
            if _RE_OPERATOR_CONTINUATION_END.search(prev_line):
                result.append(raw_line.rstrip("\r"))
                continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            result.append(raw_line.rstrip("\r"))
            continue

        code = strip_comments_and_strings(stripped)
        first = get_first_keyword(code)

        raw_col = len(raw_line) - len(raw_line.lstrip())
        col, stack = _resolve_line(
            first, code, stripped, stack, size, config, lines, idx,
            raw_col=raw_col, force_all=force_all,
        )
        should_reindent = force_all or _should_apply_reindent(
            first, code, stripped, raw_line, col, stack, size, config,
        )
        if should_reindent:
            result.append(_emit_line(raw_line, stripped, col, force_all))
        else:
            result.append(raw_line.rstrip("\r"))

        if "(*" in stripped and "*)" not in stripped:
            in_block_comment = True

    return result, stack


def _emit_line(raw_line: str, stripped: str, col: int, force_all: bool) -> str:
    raw_col = len(raw_line) - len(raw_line.lstrip())
    if not force_all and raw_col == col:
        return raw_line.rstrip("\r")
    return " " * col + stripped


def _next_non_blank(lines: list[str], start: int) -> tuple[int, str]:
    for j in range(start + 1, len(lines)):
        s = lines[j].strip()
        if s:
            return j, s
    return -1, ""


def _is_comment_only(stripped: str) -> bool:
    return strip_comments_and_strings(stripped) == ""


def _label_col(case: _CaseFrame, size: int, config: IndentConfig) -> int:
    if config.indent_cases_in_case:
        return case.anchor + size
    return case.anchor


def _case_comment_col(
    case: _CaseFrame,
    lines: list[str],
    idx: int,
    size: int,
    config: IndentConfig,
) -> int:
    nxt_idx, nxt_stripped = _next_non_blank(lines, idx)
    if nxt_idx >= 0:
        nxt_code = strip_comments_and_strings(nxt_stripped)
        nxt_first = get_first_keyword(nxt_code)
        if is_case_label(nxt_code):
            return _label_col(case, size, config)
        if nxt_first == "ELSE" and (
            _is_case_else_line(nxt_code) or nxt_code.strip().upper() == "ELSE"
        ):
            if config.indent_else_case:
                return _label_col(case, size, config)
            return case.anchor
    if case.label is not None and config.indent_statements_in_case:
        return case.label + size
    return _label_col(case, size, config)


def _statement_col(stack: list[Frame], size: int, config: IndentConfig) -> int:
    if not stack:
        return 0
    top = stack[-1]
    if isinstance(top, _IfFrame):
        return top.body
    if isinstance(top, _LoopFrame):
        return top.body
    if isinstance(top, _BlockFrame):
        return top.body
    if isinstance(top, _CaseFrame):
        if top.label is not None and config.indent_statements_in_case:
            return top.label + size
        return _label_col(top, size, config)
    return 0


def _should_apply_reindent(
    first: str,
    code: str,
    stripped: str,
    raw_line: str,
    new_col: int,
    stack: list[Frame],
    size: int,
    config: IndentConfig,
) -> bool:
    if "\t" in raw_line:
        return False
    raw_col = len(raw_line) - len(raw_line.lstrip())
    if raw_col == new_col:
        return False
    if first in ("STRUCT", "UNION"):
        return True
    if first.startswith("END_") or first == "UNTIL":
        return True
    if stripped.upper().startswith(("{REGION", "{ENDREGION", "{IF ", "{ELSIF ", "{ELSE}", "{END_IF}")):
        return True
    if _find_case_frame(stack) is not None and is_case_label(code):
        return True
    if _find_case_frame(stack) is not None and _is_comment_only(stripped):
        return True
    if (stripped == ")" or stripped == ");" or stripped.startswith(") ")) and any(isinstance(f, _BlockFrame) for f in stack):
        return True
    return False


def _find_if_frame(stack: list[Frame]) -> _IfFrame | None:
    for frame in reversed(stack):
        if isinstance(frame, _IfFrame):
            return frame
    return None


def _find_case_frame(stack: list[Frame]) -> _CaseFrame | None:
    for frame in reversed(stack):
        if isinstance(frame, _CaseFrame):
            return frame
    return None


def _case_block_depth(stack: list[Frame]) -> int:
    return sum(1 for f in stack if isinstance(f, _CaseFrame))


def _is_case_else_line(code: str) -> bool:
    upper = code.strip().upper()
    return upper == "ELSE:" or upper.startswith("ELSE:")


def _is_case_else_context(stack: list[Frame]) -> bool:
    """True when the innermost IF/CASE frame is a CaseFrame (ELSE → CASE ELSE)."""
    for frame in reversed(stack):
        if isinstance(frame, _CaseFrame):
            return True
        if isinstance(frame, _IfFrame):
            return False
    return False


def _resolve_line(
    first: str,
    code: str,
    stripped: str,
    stack: list[Frame],
    size: int,
    config: IndentConfig,
    lines: list[str],
    idx: int,
    raw_col: int = 0,
    force_all: bool = False,
) -> tuple[int, list[Frame]]:
    case_frame = _find_case_frame(stack)

    if case_frame is not None and _is_comment_only(stripped):
        if not is_case_label(code):
            if not stack or isinstance(stack[-1], _CaseFrame):
                col = _case_comment_col(case_frame, lines, idx, size, config)
                return col, stack
            col = _statement_col(stack, size, config)
            return col, stack

    if first == "END_IF":
        frame = _find_if_frame(stack)
        if frame is not None:
            _pop_if(stack)
            if _RE_DISABLE_MARKER.match(stripped):
                return frame.body, stack
            return frame.anchor, stack
        return _statement_col(stack, size, config), stack

    if first == "END_CASE":
        for i in range(len(stack) - 1, -1, -1):
            if isinstance(stack[i], _CaseFrame):
                anchor = stack[i].anchor
                del stack[i:]
                return anchor, stack
        return _statement_col(stack, size, config), stack

    if first in ("END_FOR", "END_WHILE"):
        for i in range(len(stack) - 1, -1, -1):
            if isinstance(stack[i], _LoopFrame):
                anchor = stack[i].anchor
                del stack[i:]
                return anchor, stack
        return _statement_col(stack, size, config), stack

    if first == "END_REPEAT":
        for i in range(len(stack) - 1, -1, -1):
            if isinstance(stack[i], _BlockFrame):
                anchor = stack[i].anchor
                del stack[i:]
                return anchor, stack
        return _statement_col(stack, size, config), stack

    if first == "__ENDTRY":
        for i in range(len(stack) - 1, -1, -1):
            if isinstance(stack[i], _BlockFrame):
                anchor = stack[i].anchor
                del stack[i:]
                return anchor, stack
        return _statement_col(stack, size, config), stack

    if first in ("__CATCH", "__FINALLY"):
        for i in range(len(stack) - 1, -1, -1):
            if isinstance(stack[i], _BlockFrame):
                anchor = stack[i].anchor
                stack[i:] = [_BlockFrame(anchor=anchor, body=anchor + size)]
                return anchor, stack
        return _statement_col(stack, size, config), stack

    if first in (
        "END_VAR", "END_TYPE", "END_STRUCT", "END_UNION",
        "END_METHOD", "END_ACTION", "END_PROPERTY",
        "END_PROGRAM", "END_FUNCTION_BLOCK", "END_FUNCTION",
    ) or stripped.upper().startswith(("{ENDREGION", "{END_IF}")):
        if stack and isinstance(stack[-1], _BlockFrame):
            anchor = stack[-1].anchor
            stack.pop()
            return anchor, stack
        return max(0, _statement_col(stack, size, config) - size), stack

    if stripped.upper().startswith(("{ELSIF ", "{ELSE}")):
        if stack and isinstance(stack[-1], _BlockFrame):
            return stack[-1].anchor, stack
        return _statement_col(stack, size, config), stack

    if first == "UNTIL":
        for i in range(len(stack) - 1, -1, -1):
            if isinstance(stack[i], _BlockFrame):
                anchor = stack[i].anchor
                if line_ends_with_keyword(code, "UNTIL"):
                    stack[i] = _BlockFrame(anchor=anchor, body=anchor + size)
                return anchor, stack
        return _statement_col(stack, size, config), stack

    if first == "ELSIF" and _find_if_frame(stack) is not None:
        return _find_if_frame(stack).anchor, stack  # type: ignore[union-attr]

    if first == "ELSE" and _find_if_frame(stack) is not None and not _is_case_else_context(stack):
        return _find_if_frame(stack).anchor, stack  # type: ignore[union-attr]

    if case_frame is not None:
        is_label = is_case_label(code)
        is_case_else = first == "ELSE" and _is_case_else_context(stack)
        if is_label:
            label_col = _label_col(case_frame, size, config)
            case_frame.label = label_col
            return label_col, stack
        if is_case_else:
            if config.indent_else_case:
                label_col = _label_col(case_frame, size, config)
            else:
                label_col = case_frame.anchor
            case_frame.label = label_col
            return label_col, stack
        code_s = code.strip()
        if (isinstance(stack[-1], _CaseFrame)
                and code_s.endswith(",")
                and ":=" not in code_s
                and "(" not in code_s):
            return _label_col(case_frame, size, config), stack

    col = _statement_col(stack, size, config)
    if not stack and not force_all and raw_col > 0:
        col = raw_col

    if first in VAR_BLOCK_KEYWORDS:
        stack.append(_BlockFrame(anchor=col, body=col + size))
        return col, stack

    if first == "TYPE":
        stack.append(_BlockFrame(anchor=col, body=col + size))
        if stripped.rstrip().endswith("(") and config.indent_derived_types:
            stack.append(_BlockFrame(anchor=col + size, body=col + size * 2))
        return col, stack

    if first in ("STRUCT", "UNION"):
        stack.append(_BlockFrame(anchor=col, body=col + size))
        return col, stack

    if first == "CASE":
        stack.append(_CaseFrame(anchor=col))
        return col, stack

    if first == "REPEAT":
        stack.append(_BlockFrame(anchor=col, body=col + size))
        return col, stack

    if first == "IF" or (first == "ELSIF" and _find_if_frame(stack) is None):
        body = col + size if not config.indent_then_in_if else col + size * 2
        stack.append(_IfFrame(anchor=col, body=body))
        return col, stack

    if first in ("FOR", "WHILE"):
        body = col + size if not config.indent_do_in_for else col + size * 2
        stack.append(_LoopFrame(anchor=col, body=body))
        return col, stack

    if first == "__TRY" or stripped.upper().startswith(("{REGION", "{IF ")):
        stack.append(_BlockFrame(anchor=col, body=col + size))
        return col, stack

    if stack and isinstance(stack[-1], _BlockFrame) and stripped.startswith(")"):
        if len(stack) >= 2 and isinstance(stack[-2], _BlockFrame):
            inner = stack[-1]
            if inner.body == inner.anchor + size:
                stack.pop()
                return inner.anchor, stack

    return col, stack


def _pop_if(stack: list[Frame]) -> None:
    for i in range(len(stack) - 1, -1, -1):
        if isinstance(stack[i], _IfFrame):
            del stack[i:]
            return
