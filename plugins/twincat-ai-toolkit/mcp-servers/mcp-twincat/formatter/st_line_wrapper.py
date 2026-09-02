"""ST Formatter line wrapping logic.

Handles:
- Hard line length limit enforcement
- FB call multiline wrapping (>4 params)
- Struct init wrapping (>3 fields)
- Array init wrapping (>30 elements)
- Binary operator wrap points
"""
from __future__ import annotations

import re

from formatter.constants import (
    MAX_LINE_LENGTH_DEFAULT,
    MAX_PARAMS_SINGLE_LINE,
    MAX_STRUCT_INIT_SINGLE_LINE,
    MULTILINE_CALL_INDENT,
)
from formatter.st_call_expr import split_single_line_call
from formatter.st_string_scan import iter_st_string_spans
from formatter.st_alignment import _find_colon_pos, _strip_strings


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_RE_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_TRAILING_BC = re.compile(r"\s*\(\*.*?\*\)\s*$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_long_lines(
    lines: list[str],
    *,
    max_length: int = MAX_LINE_LENGTH_DEFAULT,
    max_params_single: int = MAX_PARAMS_SINGLE_LINE,
    call_indent: int = MULTILINE_CALL_INDENT,
) -> list[str]:
    """Apply line wrapping rules to formatted lines.

    1. Wrap FB calls with >max_params_single parameters
    2. Wrap embedded calls in param/assignment lines (recursive)
    3. Wrap lines exceeding max_length at binary operators
    """
    result: list[str] = []
    for line in lines:
        wrapped = _try_wrap_if_condition_call(line, max_params_single, call_indent)
        if wrapped:
            result.extend(wrapped)
            continue

        wrapped = _try_wrap_nested_call(line, max_params_single, call_indent)
        if wrapped:
            result.extend(wrapped)
            continue

        if len(line) <= max_length and not _needs_call_wrap(line, max_params_single):
            embedded = _try_wrap_embedded_call(
                line, max_params_single, call_indent, max_length,
            )
            if embedded:
                result.extend(embedded)
            else:
                result.append(line)
            continue

        wrapped = _try_wrap_fb_call(line, max_params_single, call_indent)
        if wrapped:
            result.extend(wrapped)
            continue

        wrapped = _try_wrap_embedded_call(line, max_params_single, call_indent, max_length)
        if wrapped:
            result.extend(wrapped)
            continue

        if len(line) > max_length:
            label_result = _try_wrap_case_label_list(line)
            if label_result:
                result.extend(label_result)
                continue
            assign_chain = _try_wrap_bool_assign_at_assign(line, max_length)
            if assign_chain:
                result.extend(assign_chain)
            else:
                chain_result = _wrap_bool_chain(line, max_length)
                if chain_result:
                    result.extend(chain_result)
                else:
                    assign_result = _try_wrap_assignment(line, max_length)
                    if assign_result:
                        result.extend(assign_result)
                    else:
                        wrapped = _wrap_at_operator(line, max_length)
                        result.extend(wrapped)
        else:
            result.append(line)

    # Recursive pass: re-wrap any newly created lines that still exceed limits
    # or contain embedded calls needing wrapping.
    changed = True
    max_passes = 4
    while changed and max_passes > 0:
        max_passes -= 1
        changed = False
        next_result: list[str] = []
        for line in result:
            wrapped = _try_wrap_nested_call(line, max_params_single, call_indent)
            if wrapped and wrapped != [line]:
                next_result.extend(wrapped)
                changed = True
                continue

            wrapped = _try_wrap_embedded_call(line, max_params_single, call_indent, max_length)
            if wrapped and wrapped != [line]:
                next_result.extend(wrapped)
                changed = True
                continue

            if len(line) <= max_length:
                next_result.append(line)
                continue

            wrapped = _try_wrap_fb_call(line, max_params_single, call_indent)
            if wrapped:
                next_result.extend(wrapped)
                changed = True
                continue

            chain_result = _wrap_bool_chain(line, max_length)
            if chain_result:
                next_result.extend(chain_result)
                changed = True
                continue

            next_result.append(line)

        result = next_result

    return result


# ---------------------------------------------------------------------------
# IF-condition call wrapping
# ---------------------------------------------------------------------------

_RE_IF_KW_PREFIX = re.compile(
    r"^(\s*)(IF|ELSIF|WHILE|UNTIL)\s+(NOT\s+)?",
    re.IGNORECASE,
)


def _try_wrap_if_condition_call(
    line: str, max_params: int, call_indent: int,
) -> list[str] | None:
    """Wrap a call that forms the entire IF/ELSIF/WHILE/UNTIL condition.

    Mirrors the join heuristic in ``_join_short_multiline_calls``:
    wraps when params > max_params, or when params = max_params
    and the first param is itself a function call.
    """
    stripped = line.rstrip()
    masked = _mask_strings_and_comments(stripped)
    m = _RE_IF_KW_PREFIX.match(masked)
    if not m:
        return None

    pos = m.end()
    while pos < len(masked) and masked[pos] == " ":
        pos += 1

    id_start = pos
    while pos < len(masked) and (masked[pos].isalnum() or masked[pos] in "_.^"):
        pos += 1
    if pos == id_start:
        return None

    while pos < len(masked) and masked[pos] == " ":
        pos += 1
    if pos >= len(masked) or masked[pos] != "(":
        return None

    open_paren = pos
    depth = 1
    pos += 1
    while pos < len(masked) and depth > 0:
        if masked[pos] == "(":
            depth += 1
        elif masked[pos] == ")":
            depth -= 1
        pos += 1
    if depth != 0:
        return None
    close_paren = pos - 1

    rest = stripped[close_paren + 1 :].strip().upper()
    if rest not in ("THEN", "DO", ""):
        return None

    suffix = stripped[close_paren + 1 :].strip()
    params = _split_params(stripped[open_paren + 1 : close_paren])
    if len(params) <= 1:
        return None

    if len(params) <= max_params:
        return None

    indent_str = stripped[: len(m.group(1))]
    prefix = stripped[: open_paren + 1]
    param_indent = indent_str + " " * call_indent

    result: list[str] = [prefix]
    for i, param in enumerate(params):
        param = param.strip()
        is_last = i == len(params) - 1
        if is_last:
            close = ")" + (" " + suffix if suffix else "")
            result.append(f"{param_indent}{param}{close}")
        else:
            result.append(_append_comma_before_trailing_bc(param_indent, param))

    return result


# ---------------------------------------------------------------------------
# FB Call Wrapping
# ---------------------------------------------------------------------------


def _needs_call_wrap(line: str, max_params: int) -> bool:
    """Check if line is an FB call that exceeds param count limit."""
    split = split_single_line_call(line)
    if not split:
        return False
    params = _split_params(split.params)
    return len(params) > max_params


def _append_comma_before_trailing_bc(indent: str, param: str, suffix: str = ",") -> str:
    """Place *suffix* (comma) before a trailing ``(* ... *)`` block comment."""
    stripped = param.strip()
    bc_start = stripped.rfind("(*")
    if bc_start > 0:
        bc_end = stripped.find("*)", bc_start)
        if bc_end >= 0 and bc_end + 2 >= len(stripped.rstrip()):
            before = stripped[:bc_start].rstrip()
            comment = stripped[bc_start:].rstrip()
            return f"{indent}{before}{suffix} {comment}"
    return f"{indent}{stripped}{suffix}"


def _try_wrap_fb_call(
    line: str, max_params: int, call_indent: int
) -> list[str] | None:
    """Wrap FB call to multiline format if it exceeds param limit."""
    split = split_single_line_call(line)
    if not split:
        return None

    full_prefix = split.prefix
    params_str = split.params
    has_semi = split.has_semicolon
    indent_len = len(full_prefix) - len(full_prefix.lstrip())
    indent_str = " " * indent_len
    params = _split_params(params_str)
    trailing_comma = params_str.rstrip().endswith(",")

    if len(params) <= max_params:
        return None

    param_indent = indent_str + " " * call_indent
    result: list[str] = [f"{full_prefix}("]

    for i, param in enumerate(params):
        param = param.strip()
        is_last = i == len(params) - 1
        if is_last:
            close = ");" if has_semi else ")"
            suffix = "," + close if trailing_comma else close
            result.append(f"{param_indent}{param}{suffix}")
        else:
            result.append(_append_comma_before_trailing_bc(param_indent, param))

    return result


_RE_NESTED_CALL_START = re.compile(r"^[A-Za-z_]\w*\s*\(")


def _try_wrap_nested_call(
    line: str, max_params: int, call_indent: int,
) -> list[str] | None:
    """Wrap outer call when its single argument is a nested call needing wrap.

    Detects ``Outer( Inner( named := ..., ...))`` and splits at ``Outer(``,
    placing the inner call on a continuation line.  The recursive pass in
    ``wrap_long_lines`` then wraps the inner call's parameters.
    """
    if "(" not in line or ":=" not in line:
        return None
    stripped = line.rstrip()
    masked = _mask_strings_and_comments(stripped)
    indent_len = len(line) - len(line.lstrip())

    i = 0
    n = len(masked)
    while i < n:
        ch = masked[i]
        if (ch.isalpha() or ch == "_") and (i == 0 or not (masked[i - 1].isalnum() or masked[i - 1] == "_")):
            j = i
            while j < n and (masked[j].isalnum() or masked[j] == "_"):
                j += 1
            k = j
            while k < n and masked[k] == " ":
                k += 1
            if k < n and masked[k] == "(":
                open_paren = k
                depth = 1
                p = k + 1
                while p < n and depth > 0:
                    if masked[p] == "(":
                        depth += 1
                    elif masked[p] == ")":
                        depth -= 1
                    p += 1
                if depth != 0:
                    i = j
                    continue
                close_paren = p - 1

                params = _split_params(stripped[open_paren + 1 : close_paren])
                if len(params) == 1:
                    inner = params[0].strip()
                    inner_m = _RE_NESTED_CALL_START.match(inner)
                    if inner_m and ":=" in inner:
                        inner_open = len(inner_m.group()) - 1
                        if inner_open >= 0:
                            inner_depth = 1
                            ip = inner_open + 1
                            while ip < len(inner) and inner_depth > 0:
                                if inner[ip] == "(":
                                    inner_depth += 1
                                elif inner[ip] == ")":
                                    inner_depth -= 1
                                ip += 1
                            inner_close = ip - 1
                            inner_params = _split_params(inner[inner_open + 1 : inner_close])
                            if len(inner_params) > max_params:
                                prefix = stripped[: open_paren + 1]
                                suffix = stripped[close_paren:]
                                param_indent = " " * (indent_len + call_indent)
                                return [prefix, f"{param_indent}{inner}{suffix}"]
            i = j
            continue
        i += 1
    return None


def _try_wrap_embedded_call(
    line: str,
    max_params: int,
    call_indent: int,
    max_length: int,
) -> list[str] | None:
    """Wrap a call embedded in an assignment or parameter line.

    Handles patterns like ``param := CallName(arg1 := ..., arg2 := ...),``
    where the call has named params and exceeds *max_params* or *max_length*.

    Always picks the FIRST (outermost) matching call so that the recursive
    pass can then wrap inner calls independently.  When the full RHS would
    fit on a single continuation line after a ``:=`` split, returns ``None``
    so that ``_try_wrap_assignment`` can handle it with Style A instead.
    """
    if "(" not in line or ":=" not in line:
        return None
    stripped = line.rstrip()
    masked = _mask_strings_and_comments(stripped)
    indent_len = len(line) - len(line.lstrip())

    best_start = -1
    best_open = -1
    best_close = -1

    i = 0
    n = len(masked)
    while i < n:
        ch = masked[i]
        if (ch.isalpha() or ch == "_") and (i == 0 or not (masked[i - 1].isalnum() or masked[i - 1] == "_")):
            j = i
            while j < n and (masked[j].isalnum() or masked[j] == "_"):
                j += 1
            k = j
            while k < n and masked[k] == " ":
                k += 1
            if k < n and masked[k] == "(" and best_start < 0:
                open_paren = k
                depth = 1
                p = k + 1
                while p < n and depth > 0:
                    if masked[p] == "(":
                        depth += 1
                    elif masked[p] == ")":
                        depth -= 1
                    p += 1
                close_paren = p - 1

                call_content = masked[open_paren + 1 : close_paren]
                if ":=" in call_content:
                    params = _split_params(stripped[open_paren + 1 : close_paren])
                    has_named = any(":=" in pr for pr in params)
                    if has_named and len(params) > 1 and (len(params) > max_params or len(line) > max_length):
                        best_start = i
                        best_open = open_paren
                        best_close = close_paren
                elif len(line) > max_length:
                    params = _split_params(stripped[open_paren + 1 : close_paren])
                    if len(params) > max_params:
                        best_start = i
                        best_open = open_paren
                        best_close = close_paren
                    elif len(params) > 1:
                        assign_idx = masked.find(":=")
                        if assign_idx >= 0 and assign_idx < i:
                            between = stripped[assign_idx + 2 : i].strip()
                            if not between:
                                best_start = i
                                best_open = open_paren
                                best_close = close_paren
            i = j
            continue
        i += 1

    if best_start < 0:
        return None

    # Defer to _try_wrap_assignment (Style A) instead of call-param wrapping
    # when ALL of:
    #   1. There is an assignment ':=' before the matched call
    #   2. The call has <= max_params params (doesn't need wrapping by count)
    #   3. The ':=' continuation line fits in max_length
    #   4. The line is a statement (;-terminated), not a param inside an outer
    #      call — param lines end with , or ), and after deferral the
    #      continuation line cannot be re-wrapped by any later pass.
    assign_idx = masked.find(":=")
    if assign_idx >= 0 and assign_idx < best_start:
        call_params = _split_params(stripped[best_open + 1 : best_close])
        if len(call_params) <= max_params:
            rhs = stripped[assign_idx + 2 :].strip()
            cont_line = " " * indent_len + "    " + rhs
            if len(cont_line) <= max_length:
                line_core = _RE_TRAILING_BC.sub("", stripped).rstrip()
                if line_core.endswith(";"):
                    return None

    prefix = stripped[:best_open + 1]
    suffix_start = best_close
    suffix = stripped[suffix_start:]
    params = _split_params(stripped[best_open + 1 : best_close])

    if len(params) <= 1:
        return None

    param_indent = " " * (indent_len + call_indent)
    result: list[str] = [prefix]
    for i_p, param in enumerate(params):
        param = param.strip()
        is_last = i_p == len(params) - 1
        if is_last:
            result.append(f"{param_indent}{param}{suffix}")
        else:
            result.append(_append_comma_before_trailing_bc(param_indent, param))

    return result


def _split_params(params_str: str) -> list[str]:
    """Split parameter string by commas, respecting nesting."""
    params: list[str] = []
    depth = 0
    current = ""

    masked = _mask_strings(params_str)

    for i, ch in enumerate(masked):
        if ch == "(" or ch == "[":
            depth += 1
            current += params_str[i]
        elif ch == ")" or ch == "]":
            depth -= 1
            current += params_str[i]
        elif ch == "," and depth == 0:
            params.append(current)
            current = ""
        else:
            current += params_str[i]

    if current.strip():
        params.append(current)

    idx = 1
    while idx < len(params):
        p = params[idx].lstrip()
        if p.startswith("(*"):
            bc_end = p.find("*)")
            if bc_end >= 0:
                bc_end += 2
                after_bc = p[bc_end:].lstrip()
                if after_bc:
                    bc = p[:bc_end]
                    params[idx - 1] = params[idx - 1].rstrip() + " " + bc
                    params[idx] = " " + after_bc
        idx += 1

    return params


# ---------------------------------------------------------------------------
# Operator Wrapping
# ---------------------------------------------------------------------------

_WRAP_OPERATORS = re.compile(
    r"\s+(AND|OR|XOR|AND_THEN|OR_ELSE|\+|-)\s+", re.IGNORECASE
)

_CHAIN_OPS: tuple[str, ...] = ("AND_THEN", "OR_ELSE", "AND", "OR", "XOR")

_RE_CONDITION_PREFIX = re.compile(
    r"^(\s*(?:IF|ELSIF|WHILE)\s+)(.*)$", re.IGNORECASE
)
_RE_ASSIGN_PREFIX = re.compile(r"^(\s*\S+\s*:=\s*)(.*)$", re.DOTALL)


def _parse_chained_binary_line(line: str) -> tuple[str, int, int, str] | None:
    """Return (lhs_prefix, expr_start, expr_end, suffix) for a chain-wrap candidate.

    *suffix* is a stripped trailing keyword such as `` THEN`` or `` DO`` that
    must be re-appended to the last wrapped segment.
    """
    stripped = line.rstrip()

    m = _RE_ASSIGN_PREFIX.match(stripped)
    if m:
        lhs = m.group(1)
        expr_start = len(lhs)
        while expr_start < len(stripped) and stripped[expr_start] == " ":
            expr_start += 1
        return lhs, expr_start, len(stripped), ""

    m = _RE_CONDITION_PREFIX.match(stripped)
    if m:
        lhs = m.group(1)
        rhs = m.group(2).rstrip()
        suffix = ""
        if rhs.upper().endswith(" THEN"):
            suffix = " THEN"
            rhs = rhs[:-5].rstrip()
        elif rhs.upper().endswith(" DO"):
            suffix = " DO"
            rhs = rhs[:-3].rstrip()
        expr_end = len(lhs) + len(rhs)
        expr_start = len(lhs)
        while expr_start < expr_end and stripped[expr_start] == " ":
            expr_start += 1
        return lhs, expr_start, expr_end, suffix

    # Fallback: plain expression (continuation line after := split, etc.)
    indent_len = len(line) - len(line.lstrip())
    if indent_len < len(stripped):
        lhs = " " * indent_len
        rhs_text = stripped[indent_len:].rstrip()
        suffix = ""
        rhs_upper = rhs_text.upper()
        if rhs_upper.endswith(" THEN"):
            suffix = " THEN"
            expr_end = len(stripped) - 5
            while expr_end > indent_len and stripped[expr_end - 1] == " ":
                expr_end -= 1
        elif rhs_upper.endswith(" DO"):
            suffix = " DO"
            expr_end = len(stripped) - 3
            while expr_end > indent_len and stripped[expr_end - 1] == " ":
                expr_end -= 1
        else:
            expr_end = len(stripped)
        return lhs, indent_len, expr_end, suffix

    return None


def _is_word_boundary(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _count_top_level_chain_ops(
    masked: str, expr_start: int, expr_end: int, *, target_depth: int = 0,
) -> int:
    """Count boolean chain operators at *target_depth* in an expression slice."""
    count = 0
    for op in _CHAIN_OPS:
        search_from = expr_start
        while True:
            idx = masked.upper().find(op, search_from, expr_end)
            if idx < 0:
                break
            before_ok = idx == 0 or not _is_word_boundary(masked[idx - 1])
            after_idx = idx + len(op)
            after_ok = after_idx >= len(masked) or not _is_word_boundary(masked[after_idx])
            if before_ok and after_ok:
                depth = 0
                for i in range(expr_start, idx):
                    if masked[i] == "(":
                        depth += 1
                    elif masked[i] == ")":
                        depth -= 1
                if depth == target_depth:
                    count += 1
            search_from = idx + len(op)
    return count


def _split_top_level_chain_ops(
    line: str, expr_start: int, expr_end: int, *, target_depth: int = 0,
) -> list[str]:
    """Split expression into segments at chain ops at *target_depth*."""
    masked = _mask_strings_and_comments(line)
    parts: list[str] = []
    last_split = expr_start
    while last_split < expr_end and line[last_split] == " ":
        last_split += 1
    expr_start = last_split

    depth = 0
    i = expr_start
    while i < expr_end:
        if masked[i] == "(":
            depth += 1
            i += 1
        elif masked[i] == ")":
            depth -= 1
            i += 1
        elif depth == target_depth:
            matched = False
            for op in _CHAIN_OPS:
                if masked[i:i + len(op)].upper() == op:
                    before_ok = i == 0 or not _is_word_boundary(masked[i - 1])
                    after_idx = i + len(op)
                    after_ok = after_idx >= len(masked) or not _is_word_boundary(masked[after_idx])
                    if before_ok and after_ok:
                        end = i + len(op)
                        parts.append(line[last_split:end].strip())
                        last_split = end
                        while last_split < expr_end and line[last_split] == " ":
                            last_split += 1
                        i = last_split
                        matched = True
                        break
            if not matched:
                i += 1
        else:
            i += 1

    if last_split < expr_end:
        parts.append(line[last_split:expr_end].strip())

    return parts


def wrap_chained_binary_expression(
    line: str,
    max_length: int,
    *,
    force: bool = False,
) -> list[str] | None:
    """Wrap AND_THEN/OR_ELSE chains one operand per line (chained-binary style).

    Supports assignments and IF/ELSIF/WHILE conditions. Continuation lines align to
    the first operand column. Wraps when *force* is True or the line exceeds
    *max_length* and contains at least one chain operator.

    When no depth-0 operators exist but the expression is parenthesized,
    splits at depth 1 (operators inside the outermost parentheses).
    """
    parsed = _parse_chained_binary_line(line)
    if parsed is None:
        return None

    lhs, expr_start, expr_end, suffix = parsed
    masked = _mask_strings_and_comments(line)

    depth = 0
    top_level_ops = _count_top_level_chain_ops(masked, expr_start, expr_end)
    if top_level_ops < 1:
        top_level_ops = _count_top_level_chain_ops(
            masked, expr_start, expr_end, target_depth=1,
        )
        if top_level_ops < 1:
            return None
        depth = 1

    if not force and len(line) <= max_length:
        return None

    parts = _split_top_level_chain_ops(
        line, expr_start, expr_end, target_depth=depth,
    )
    if len(parts) <= 1:
        return None

    if (depth == 1
            and suffix
            and expr_start < len(line.rstrip())
            and line.rstrip()[expr_start] == "("
            and lhs.strip().upper().startswith(("IF", "ELSIF", "WHILE"))):
        cont_indent = " " * (expr_start + 1)
    else:
        cont_indent = " " * expr_start
    result = [lhs + parts[0]]
    for part in parts[1:]:
        result.append(cont_indent + part)
    if suffix and result:
        result[-1] = result[-1].rstrip() + suffix
    return result


def _try_wrap_case_label_list(line: str) -> list[str] | None:
    """Wrap comma-separated CASE label lists onto separate lines."""
    stripped = line.strip()
    if not stripped.endswith(":") or ":=" in stripped:
        return None
    indent = " " * (len(line) - len(line.lstrip()))
    commas: list[int] = []
    depth = 0
    in_str = False
    i = 0
    while i < len(stripped):
        ch = stripped[i]
        if in_str:
            if ch == "'" and i + 1 < len(stripped) and stripped[i + 1] == "'":
                i += 2
                continue
            if ch == "'":
                in_str = False
            i += 1
            continue
        if ch == "'":
            in_str = True
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            commas.append(i)
        i += 1
    if not commas:
        return None
    parts: list[str] = []
    prev = 0
    for ci in commas:
        parts.append(stripped[prev:ci + 1].strip())
        prev = ci + 1
    parts.append(stripped[prev:].strip())
    return [indent + p for p in parts]


def _has_depth0_wrap_operator(text: str) -> bool:
    """Return True when *text* has a wrappable operator at paren-depth 0."""
    masked = _mask_strings_and_comments(text)
    for m in _WRAP_OPERATORS.finditer(masked):
        d = 0
        for ch in masked[: m.start()]:
            if ch == "(":
                d += 1
            elif ch == ")":
                d = max(0, d - 1)
        if d == 0:
            return True
    return False


def _try_wrap_assignment(line: str, max_length: int) -> list[str] | None:
    """Wrap a long assignment after ':=' (ST assignment wrap style).

    Used for member-access RHS without top-level bool/arithmetic operators.
    Skips lines already split after ':=' or with depth-0 operator chains.
    """
    if len(line) <= max_length:
        return None
    stripped = line.rstrip()
    if stripped.endswith(":="):
        return None
    m = _RE_ASSIGN_PREFIX.match(stripped)
    if not m:
        return None
    rhs = m.group(2).strip()
    if not rhs or _has_depth0_wrap_operator(rhs):
        return None
    indent_match = re.match(r"^(\s*)", line)
    base_indent = indent_match.group(1) if indent_match else ""
    first = stripped[: m.start(2)].rstrip()
    if first.endswith(":="):
        pre_assign = first[:-2].rstrip()
        first = pre_assign + " :="
    if len(first) > max_length:
        return None
    cont_indent = base_indent + "    "
    second = cont_indent + rhs
    if len(second) <= max_length:
        return [first, second]
    tail = _wrap_at_operator(second, max_length)
    if len(tail) == 1 and len(tail[0]) > max_length:
        return None
    return [first, *tail]


_RE_CHAIN_OP_WORD = re.compile(r"\b(AND_THEN|OR_ELSE|AND|OR|XOR)\b", re.IGNORECASE)


def _has_depth0_chain_op(text: str) -> bool:
    """Return True when *text* contains a boolean chain operator at paren-depth 0."""
    masked = _mask_strings_and_comments(text)
    depth = 0
    i = 0
    while i < len(masked):
        ch = masked[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        i += 1
    depth = 0
    for m in _RE_CHAIN_OP_WORD.finditer(masked):
        d = 0
        for ch in masked[: m.start()]:
            if ch == "(":
                d += 1
            elif ch == ")":
                d = max(0, d - 1)
        if d == 0:
            return True
    return False


def _try_wrap_bool_assign_at_assign(line: str, max_length: int) -> list[str] | None:
    """Split a boolean-chain assignment at ``:=`` first, then wrap the RHS.

    Style A: ``lhs :=`` alone, RHS on continuation line(s) at base+4.
    Style B: ``lhs := first_operand OP`` with continuation at expr_start.

    Strategy:
    - If the full RHS fits on ONE continuation line at base+4 → Style A.
    - If Style B (chain wrap at expr_start) would produce overlength lines
      that Style A can avoid → Style A with chain-wrapped RHS.
    - Otherwise let ``_wrap_bool_chain`` handle it (Style B).

    Only fires for standalone assignments (ending with ``;``).
    """
    if len(line) <= max_length:
        return None
    stripped = line.rstrip()
    if not stripped.endswith(";"):
        return None
    m = _RE_ASSIGN_PREFIX.match(stripped)
    if not m:
        return None
    rhs = m.group(2).strip()
    if not rhs:
        return None
    if not _has_depth0_chain_op(rhs):
        return None
    base_indent = " " * (len(line) - len(line.lstrip()))
    first = stripped[: m.start(2)].rstrip()
    cont_indent = base_indent + "    "
    second = cont_indent + rhs

    if len(second) <= max_length:
        return [first, second]

    style_b = wrap_chained_binary_expression(line, max_length)
    if style_b and all(len(l) <= max_length for l in style_b):
        return None

    chain_wrapped = wrap_chained_binary_expression(second, max_length)
    if chain_wrapped:
        return [first] + chain_wrapped
    op_wrapped = _wrap_at_operator(second, max_length)
    if len(op_wrapped) > 1:
        return [first] + op_wrapped
    return None


def _try_wrap_assign_chain(line: str, max_length: int) -> list[str] | None:
    """Split a standalone assignment at ``:=``, then chain-wrap the RHS.

    Only fires for lines ending with ``;`` (standalone assignments), not for
    parameter assignments ending with ``,``.  Produces the 'Style A' layout
    where ``:=`` sits alone on the first line and the boolean chain
    continues at base_indent + 4.
    """
    if len(line) <= max_length:
        return None
    stripped = line.rstrip()
    if not stripped.endswith(";"):
        return None
    m = _RE_ASSIGN_PREFIX.match(stripped)
    if not m:
        return None
    rhs = m.group(2).strip()
    if not rhs:
        return None
    if not _has_depth0_chain_op(rhs):
        return None

    base_indent = " " * (len(line) - len(line.lstrip()))
    first = stripped[: m.end(1)].rstrip()
    cont_indent = base_indent + "    "
    second = cont_indent + rhs

    if len(second) <= max_length:
        return [first, second]

    chain_wrapped = wrap_chained_binary_expression(second, max_length)
    if chain_wrapped:
        return [first] + chain_wrapped

    op_wrapped = _wrap_at_operator(second, max_length)
    if len(op_wrapped) > 1:
        return [first] + op_wrapped

    return None


def _wrap_bool_chain(line: str, max_length: int) -> list[str] | None:
    """Wrap boolean chains (AND_THEN/OR_ELSE) when the line exceeds *max_length*."""
    return wrap_chained_binary_expression(line, max_length)


def _wrap_at_operator(line: str, max_length: int) -> list[str]:
    """Wrap a long line after a binary operator."""
    if len(line) <= max_length:
        return [line]

    indent_match = re.match(r"^(\s*)", line)
    base_indent = indent_match.group(1) if indent_match else ""
    cont_indent = base_indent + "    "

    masked = _mask_strings_and_comments(line)

    best_pos = -1
    for m in _WRAP_OPERATORS.finditer(masked):
        pos = m.end()
        if pos <= max_length:
            best_pos = pos

    if best_pos <= 0:
        return [line]

    first = line[:best_pos].rstrip()
    rest = line[best_pos:].lstrip()

    result = [first]
    remaining = cont_indent + rest

    if len(remaining) > max_length:
        result.extend(_wrap_at_operator(remaining, max_length))
    else:
        result.append(remaining)

    return result


# ---------------------------------------------------------------------------
# Assignment Join (inverse of assignment wrap)
# ---------------------------------------------------------------------------

_RE_STMT_START = re.compile(
    r"^(?:IF|ELSIF|ELSE|CASE|END_|FOR|WHILE|REPEAT|RETURN|EXIT|CONTINUE|JMP|__TRY|__CATCH|__FINALLY|__ENDTRY)\b",
    re.IGNORECASE,
)


def _is_impl_assign_continuation_opener(line: str) -> bool:
    """True when *line* opens a wrapped implementation assignment (not a VAR decl)."""
    stripped = line.strip()
    if not stripped.endswith(":="):
        return False
    code = _RE_BLOCK_COMMENT.sub("", stripped)
    code = _strip_strings(code)
    colon = _find_colon_pos(code)
    assign = code.find(":=")
    if colon >= 0 and assign > colon:
        return False
    return True


def join_wrapped_assignments(lines: list[str], *, max_length: int) -> list[str]:
    """Join ``lhs :=`` + indented continuation when the result fits *max_length*."""
    result: list[str] = []
    i = 0
    in_block_comment = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if in_block_comment:
            result.append(line)
            if "*)" in stripped:
                in_block_comment = False
            i += 1
            continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            result.append(line)
            i += 1
            continue

        if i + 1 < len(lines):
            cur = line.rstrip()
            nxt = lines[i + 1]
            nxt_stripped = nxt.strip()
            if (
                cur.endswith(":=")
                and _is_impl_assign_continuation_opener(line)
                and nxt_stripped
                and nxt_stripped.endswith(";")
                and not nxt_stripped.startswith("(*")
                and not _RE_STMT_START.match(nxt_stripped)
            ):
                base_indent = len(line) - len(line.lstrip())
                cont_indent = len(nxt) - len(nxt.lstrip())
                if cont_indent > base_indent:
                    joined = cur + " " + nxt_stripped
                    if len(joined) <= max_length:
                        result.append(joined)
                        i += 2
                        continue

        result.append(line)
        i += 1

    return result


# ---------------------------------------------------------------------------
# Masking Helpers
# ---------------------------------------------------------------------------


def _mask_string_spans(text: str, result: list[str]) -> None:
    for start, end in iter_st_string_spans(text):
        for i in range(start + 1, end - 1):
            result[i] = " "


def _mask_strings(text: str) -> str:
    """Replace string content with spaces for safe parsing."""
    result = list(text)
    _mask_string_spans(text, result)
    return "".join(result)


def _mask_strings_and_comments(text: str) -> str:
    """Replace strings and block comments with spaces."""
    if "'" not in text and '"' not in text and "(*" not in text:
        return text
    result = list(text)
    if "'" in text or '"' in text:
        _mask_string_spans(text, result)
    if "(*" in text:
        for m in _RE_BLOCK_COMMENT.finditer(text):
            for i in range(m.start() + 2, m.end() - 2):
                result[i] = " "
    return "".join(result)
