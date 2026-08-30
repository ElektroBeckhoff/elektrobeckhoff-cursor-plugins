"""ST Formatter alignment logic: declarations, assignments, FB call params.

Handles column alignment for:
- Variable declarations (colon, assignment, comments)
- Assignment groups in implementation
- FB call parameter alignment
"""
from __future__ import annotations

import re
from typing import Sequence

from formatter.constants import VAR_BLOCK_KEYWORDS, MULTILINE_CALL_INDENT
from formatter.st_parse_utils import is_if_wrapped_call_opener
from formatter.st_string_scan import sub_st_string_literals


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_RE_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
_RE_INLINE_COMMENT = re.compile(r"\(\*.*?\*\)\s*$")
_RE_DECL_LINE = re.compile(
    r"^(\s*)"                   # leading indent
    r"([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)"  # name(s)
    r"(\s*:\s*)"                # colon
    r"(.+)$"                    # type + optional init + comment
)
_RE_ASSIGN_LINE = re.compile(
    r"^(\s*\S+\s*):=\s*(.*)$"
)
_RE_STRUCT_INIT_OPEN = re.compile(
    r"^\s*\(\s*[A-Za-z_]\w*\s*:=",
    re.IGNORECASE,
)
_RE_STRUCT_PAREN_OPEN = re.compile(r"^\(\s*,?\s*$")
_RE_ARRAY_STRUCT_OPEN = re.compile(r"^(\s*)([\w.^]+(?:\[[^\]]*\])?)\s*:=\s*\[(?:\(\s*)?$")
_RE_ELEMENT_CLOSE = re.compile(r"^\s*\),\s*$")
_RE_ELEMENT_SEP = re.compile(r"^\s*\),\s*\(\s*$")
_RE_ELEMENT_OPEN = re.compile(r"^\s*\(\s*$")
_RE_ARRAY_STRUCT_END = re.compile(r"^(\s*)(?:\)\s*)?\];?\s*$")


def _strip_strings(text: str) -> str:
    """Replace string literal contents with dots, preserving length for safe index use."""
    if "'" not in text and '"' not in text:
        return text
    return sub_st_string_literals(
        text,
        lambda lit: "'" + "." * (len(lit) - 2) + "'" if lit.startswith("'") else '"' + "." * (len(lit) - 2) + '"',
    )


def _find_line_comment_pos(text: str) -> int:
    """Find position of '//' line comment start outside string literals, or -1."""
    if "//" not in text:
        return -1
    masked = _strip_strings(text)
    return masked.find("//")



# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def align_declarations(lines: list[str], *, max_line_length: int = 0,
                       align_init_operator: bool = True,
                       max_init_type_spread: int = 999,
                       align_enum_initializers: bool = True,
                       align_address_assignments: bool = True,
                       max_enum_members_single_line: int = 5,
                       decl_comment_preserve_tight_gap: bool = True,
                       decl_comment_preserve_source_gap: int = 1,
                       decl_comment_preserve_max_col_delta: int = 1,
                       decl_split_outlier_median_multiplier: float = 1.5,
                       decl_split_outlier_median_add: int = 20) -> list[str]:
    """Align colons, types, assignments, and comments in VAR/STRUCT/ENUM blocks.

    Groups consecutive declaration lines and aligns:
    1. ':' to the same column
    2. ':=' initializers to the same column (when align_init_operator=True and spread <= threshold)
    3. '(* *)' inline comments to the same column
    Also handles ENUM member alignment (name := value, with comments).

    If max_line_length > 0, outlier lines that would push the group beyond
    the limit are split into their own sub-groups (aligned independently).
    align_init_operator: if True, pad types to align ':=' in a column.
    max_init_type_spread: skip ':=' alignment when type length spread exceeds this.
    """
    result: list[str] = []
    in_var_block = False
    in_struct_block = False
    in_enum_block = False
    in_block_comment = False
    decl_group: list[str] = []
    enum_group: list[str] = []

    def _flush_decl() -> None:
        if decl_group:
            result.extend(_align_group(
                decl_group,
                max_line_length,
                align_init_operator=align_init_operator,
                max_init_type_spread=max_init_type_spread,
                align_address_assignments=align_address_assignments,
                decl_comment_preserve_tight_gap=decl_comment_preserve_tight_gap,
                decl_comment_preserve_source_gap=decl_comment_preserve_source_gap,
                decl_comment_preserve_max_col_delta=decl_comment_preserve_max_col_delta,
                decl_split_outlier_median_multiplier=decl_split_outlier_median_multiplier,
                decl_split_outlier_median_add=decl_split_outlier_median_add,
            ))
            decl_group.clear()

    for line in lines:
        stripped_line = line.strip()

        # Track multi-line block comments
        if in_block_comment:
            _flush_decl()
            if in_enum_block:
                enum_group.append(line)
            else:
                result.append(line)
            if "*)" in stripped_line:
                in_block_comment = False
            continue

        if stripped_line.startswith("(*") and "*)" not in stripped_line:
            in_block_comment = True
            _flush_decl()
            if in_enum_block:
                enum_group.append(line)
            else:
                result.append(line)
            continue

        stripped = line.strip().upper()
        first_word = stripped.split()[0] if stripped.split() else ""

        # Detect enum block: "TYPE Name : (" pattern
        if not in_enum_block and not in_var_block:
            upper_stripped = stripped_line.upper()
            if (upper_stripped.startswith("TYPE ") and ": (" in upper_stripped
                    or upper_stripped.startswith("TYPE ") and ":(" in upper_stripped):
                in_enum_block = True
                enum_group = [_normalize_type_header_colon(line)]
                continue
            if stripped_line == "(" and result and result[-1].strip().upper().startswith("TYPE ") and result[-1].strip().endswith(":"):
                prev = result.pop().rstrip()
                in_enum_block = True
                enum_group = [f"{prev} ("]
                continue

        if in_enum_block:
            enum_group.append(line)
            # Check for closing paren (enum body end)
            code_part = stripped_line
            comment_match = _RE_INLINE_COMMENT.search(code_part)
            if comment_match:
                code_part = code_part[:comment_match.start()].rstrip()
            if code_part.startswith(")") or ") " in code_part.upper():
                if align_enum_initializers:
                    enum_group = split_inline_enum_members(
                        enum_group,
                        max_members_per_line=max_enum_members_single_line,
                        max_line_length=max_line_length,
                    )
                    result.extend(_align_enum_members(enum_group))
                else:
                    result.extend(enum_group)
                enum_group = []
                in_enum_block = False
            continue

        if first_word == "TYPE" and any(k in stripped_line.upper() for k in ("STRUCT", "UNION")):
            in_struct_block = True
            in_var_block = True
            _flush_decl()
            result.append(_normalize_type_header_colon(line))
            continue

        if first_word in VAR_BLOCK_KEYWORDS or first_word in ("STRUCT", "UNION"):
            if first_word in ("STRUCT", "UNION"):
                in_struct_block = True
            in_var_block = True
            _flush_decl()
            if first_word == "UNION" and result and result[-1].strip().upper().startswith("TYPE ") and result[-1].strip().endswith(":"):
                prev = result.pop().rstrip()
                result.append(f"{prev} UNION")
                continue
            result.append(line)
            continue

        if first_word in ("END_VAR", "END_STRUCT", "END_UNION"):
            in_var_block = False
            in_struct_block = False
            _flush_decl()
            result.append(line)
            continue

        if in_var_block:
            if stripped_line and not stripped_line.startswith("//") and not stripped_line.startswith("(*"):
                # Inline pragma + declaration (e.g., {attribute 'TcEncoding':='UTF-8'} _var : TYPE;)
                if stripped_line.startswith("{") and "}" in stripped_line:
                    close_brace = stripped_line.index("}") + 1
                    remainder = stripped_line[close_brace:].strip()
                    if remainder and _has_decl_colon(remainder):
                        decl_group.append(line)
                        continue

                if _has_decl_colon(stripped_line) or _is_multiline_decl_opener(stripped_line):
                    if not stripped_line.startswith("{"):
                        decl_group.append(line)
                        continue
                elif stripped_line.startswith("{"):
                    # Standalone pragma breaks alignment group
                    _flush_decl()
                    result.append(line)
                    continue

            _flush_decl()
            result.append(line)
        else:
            result.append(line)

    _flush_decl()
    if enum_group:
        if align_enum_initializers:
            enum_group = split_inline_enum_members(
                enum_group,
                max_members_per_line=max_enum_members_single_line,
                max_line_length=max_line_length,
            )
            result.extend(_align_enum_members(enum_group))
        else:
            result.extend(enum_group)

    return result


def align_assignments(
    lines: list[str], *,
    max_spread: int = 12,
    max_line_length: int = 0,
    bool_literal_min_group_lines: int = 3,
    bool_literal_name_spread_max: int = 2,
    assign_already_aligned_max_gap: int = 1,
    compact_group_min_lines: int = 4,
    compact_group_max_over_pad: int = 3,
    compact_three_line_count: int = 3,
    compact_three_line_over_pad: int = 2,
    compact_pair_assigns: bool = True,
    compact_pair_min_over_pad: int = 8,
    three_line_assign_group_count: int = 3,
    three_line_assign_group_min_spread: int = 12,
    three_line_assign_group_max_lhs_len: int = 36,
    three_line_assign_group_min_qualified_count: int = 2,
    three_line_assign_group_extra_pad: int = 2,
) -> list[str]:
    """Align ':=' in consecutive assignment groups in implementation code.

    Groups of 2+ consecutive simple assignments get their ':=' aligned.
    max_spread: skip alignment if max-min LHS name length exceeds this.
    max_line_length: when > 0, a simple assignment exceeding this length
        is included in the current group but forces a group split (the line
        will be wrapped later and should not inflate following groups).
    """
    result: list[str] = []
    group: list[str] = []
    in_block_comment = False

    overlength_flush = False

    def _flush_group(*, following: list[str] | None = None) -> None:
        nonlocal overlength_flush
        if len(group) >= 2:
            result.extend(_align_assign_group(
                group, max_spread,
                max_line_length=max_line_length,
                bool_literal_min_group_lines=bool_literal_min_group_lines,
                bool_literal_name_spread_max=bool_literal_name_spread_max,
                assign_already_aligned_max_gap=assign_already_aligned_max_gap,
                compact_group_min_lines=compact_group_min_lines,
                compact_group_max_over_pad=compact_group_max_over_pad,
                compact_three_line_count=compact_three_line_count,
                compact_three_line_over_pad=compact_three_line_over_pad,
                compact_pair_assigns=compact_pair_assigns,
                compact_pair_min_over_pad=compact_pair_min_over_pad,
                three_line_assign_group_count=three_line_assign_group_count,
                three_line_assign_group_min_spread=three_line_assign_group_min_spread,
                three_line_assign_group_max_lhs_len=three_line_assign_group_max_lhs_len,
                three_line_assign_group_min_qualified_count=three_line_assign_group_min_qualified_count,
                three_line_assign_group_extra_pad=three_line_assign_group_extra_pad,
            ))
        elif len(group) == 1:
            if overlength_flush:
                result.append(group[0])
            else:
                result.append(_align_orphan_to_following_assign(group[0], following or []))
        else:
            result.extend(group)
        overlength_flush = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if in_block_comment:
            _flush_group()
            group = []
            result.append(line)
            if "*)" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            _flush_group()
            group = []
            result.append(line)
            continue

        if _is_enum_member_line(line):
            _flush_group(following=lines[i:])
            group = []
            result.append(line)
        elif _is_simple_assignment(line):
            group.append(line)
            if max_line_length > 0 and len(line.rstrip()) > max_line_length:
                overlength_flush = True
                _flush_group(following=lines[i + 1:])
                group = []
        elif _is_ref_assign_line(line) and group:
            group.append(line)
        else:
            _flush_group(following=lines[i:])
            group = []
            result.append(line)

    _flush_group()
    return result


def _top_level_assign_positions(line: str) -> list[int]:
    """Return character indices of top-level ``:=`` operators in *line*."""
    cm = _RE_INLINE_COMMENT.search(line)
    code = line[:cm.start()] if cm else line
    pos_lc = _find_line_comment_pos(code)
    if pos_lc >= 0:
        code = code[:pos_lc]
    code = re.sub(r"\{[^{}]*\}", lambda m: " " * len(m.group()), code)
    masked = _strip_strings(code)
    depth = 0
    positions: list[int] = []
    i = 0
    while i < len(masked) - 1:
        if masked[i] == "(":
            depth += 1
        elif masked[i] == ")":
            depth -= 1
        elif masked[i] == ":" and masked[i + 1] == "=" and depth == 0:
            positions.append(i)
            i += 1
        i += 1
    return positions


def _realign_assign_to_col(line: str, target_col: int) -> str:
    pos = _find_assign_pos(line)
    if pos < 0:
        return line
    lhs = line[:pos].rstrip()
    rhs = line[pos:].lstrip()
    if not rhs.startswith(":="):
        return line
    padding = max(1, target_col - len(lhs))
    return lhs + " " * padding + rhs


def _align_chained_section(section: list[str]) -> list[str]:
    """Align single ``:=`` followers to the second ``:=`` of a preceding chained line.

    Anchor scope is sequential: a chained line sets the column for following single
    assignments until a blank line, ``IF`` block, unrelated single assign, or a new
    chained line. Nested ``IF`` bodies get their own scope (fixes ELSIF branches and
    avoids pulling anchors from inner blocks onto earlier outer lines).
    """

    def _should_follow_anchor(line: str) -> bool:
        stripped = line.strip()
        if not stripped or _has_decl_colon(stripped) or _is_multiline_decl_opener(stripped):
            return False
        return len(_top_level_assign_positions(line)) == 1

    def _process_lines(lines: list[str]) -> list[str]:
        out: list[str] = []
        anchor: int | None = None
        follower_mode = False
        i = 0
        while i < len(lines):
            line = lines[i]
            block, i = _take_if_block(lines, i)
            if block is not None:
                anchor = None
                follower_mode = False
                out.append(block[0])
                out.extend(_process_lines(block[1:-1]))
                out.append(block[-1])
                continue

            if not line.strip():
                anchor = None
                follower_mode = False
                out.append(line)
                i += 1
                continue

            positions = _top_level_assign_positions(line)
            if len(positions) == 2:
                anchor = positions[1]
                follower_mode = True
                out.append(line)
            elif (
                anchor is not None
                and follower_mode
                and _is_ref_assign_line(line)
            ):
                out.append(_realign_ref_to_col(line, anchor))
            elif (
                len(positions) == 1
                and anchor is not None
                and follower_mode
                and _should_follow_anchor(line)
            ):
                out.append(_realign_assign_to_col(line, anchor))
            else:
                if len(positions) == 1:
                    anchor = None
                    follower_mode = False
                out.append(line)
            i += 1
        return out

    return _process_lines(section)


def _take_if_block(lines: list[str], start: int) -> tuple[list[str] | None, int]:
    """Return a nested ``IF … THEN … END_IF`` block starting at *start*."""
    if start >= len(lines):
        return None, start
    stripped = lines[start].strip().upper()
    if not (stripped.startswith("IF ") and "THEN" in stripped):
        return None, start
    block = [lines[start]]
    i = start + 1
    depth = 1
    while i < len(lines) and depth > 0:
        inner = lines[i]
        block.append(inner)
        s = inner.strip().upper()
        if s.startswith("IF ") and "THEN" in s:
            depth += 1
        elif s.startswith("END_IF"):
            depth -= 1
        i += 1
    return block, i


def align_chained_init_assignments(lines: list[str]) -> list[str]:
    """Align init-method assigns to chained ``InitX := _bValidX :=`` second-``:=`` column."""
    result: list[str] = []
    section: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip().upper()
        if stripped.startswith("IF ") and "THEN" in stripped:
            if section:
                result.extend(_align_chained_section(section))
                section = []
            result.append(line)
            i += 1
            body: list[str] = []
            depth = 1
            while i < len(lines) and depth > 0:
                inner = lines[i]
                inner_stripped = inner.strip().upper()
                if inner_stripped.startswith("IF ") and "THEN" in inner_stripped:
                    depth += 1
                elif inner_stripped.startswith("END_IF"):
                    depth -= 1
                    if depth == 0:
                        result.extend(_align_chained_section(body))
                        result.append(inner)
                        i += 1
                        break
                if depth > 0:
                    body.append(inner)
                i += 1
            continue
        if not stripped:
            if section:
                result.extend(_align_chained_section(section))
                section = []
            result.append(line)
            i += 1
            continue
        section.append(line)
        i += 1
    if section:
        result.extend(_align_chained_section(section))
    return result


_RE_CHAINED_ASSIGN_RESET = re.compile(
    r"^\s*[A-Za-z_]\w*\s*:=\s*[A-Za-z_]\w*\s*:=\s*FALSE;\s*$",
    re.IGNORECASE,
)


def _assign_lhs_name(line: str) -> str | None:
    """Return the assigned identifier name from a simple ``lhs := rhs;`` line."""
    pos = _find_assign_pos(line)
    if pos < 0 or len(_top_level_assign_positions(line)) != 1:
        return None
    lhs = line[:pos].strip()
    if not lhs:
        return None
    return lhs.split()[-1]


def _realign_assign_group_to_col(group: list[str], target_col: int) -> list[str]:
    result: list[str] = []
    for line in group:
        if _is_ref_assign_line(line):
            result.append(_realign_ref_to_col(line, target_col))
        else:
            result.append(_realign_assign_to_col(line, target_col))
    return result


def _realign_init_injection_if_body(body: list[str], lhs_gaps: dict[str, int]) -> list[str]:
    """Realign IF-body assignments to gaps established in the init preamble."""
    if not lhs_gaps:
        return body

    result: list[str] = []
    group: list[str] = []

    def _target_col_for_line(line: str) -> int | None:
        name = _assign_lhs_name(line)
        if name is None and _is_ref_assign_line(line):
            pos = _find_ref_pos(line)
            if pos >= 0:
                name = line[:pos].strip().split()[-1]
        if not name or name not in lhs_gaps:
            return None
        pos = _find_assign_pos(line) if not _is_ref_assign_line(line) else _find_ref_pos(line)
        if pos < 0:
            return None
        lhs_len = len(line[:pos].rstrip())
        return lhs_len + lhs_gaps[name]

    def _flush_group() -> None:
        nonlocal group
        if not group:
            return
        targets = [_target_col_for_line(gl) for gl in group]
        if targets and all(t is not None for t in targets):
            result.extend(_realign_assign_group_to_col(group, max(t for t in targets if t is not None)))
        else:
            result.extend(group)
        group = []

    for line in body:
        if _is_simple_assignment(line) or (_is_ref_assign_line(line) and group):
            group.append(line)
        else:
            _flush_group()
            result.append(line)
    _flush_group()
    return result


def align_init_injection_if_bodies(lines: list[str]) -> list[str]:
    """Align IF-body assignments in chained injection methods.

    Preserves the wide ``:=`` column from zero-reset preamble lines when the
    same identifiers are assigned inside the following ``IF`` block.
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not _RE_CHAINED_ASSIGN_RESET.match(line):
            result.append(line)
            i += 1
            continue

        preamble = [line]
        lhs_gaps: dict[str, int] = {}
        i += 1
        while i < len(lines):
            current = lines[i]
            stripped = current.strip()
            upper = stripped.upper()
            if upper.startswith("IF ") and "THEN" in upper:
                break
            pos = _find_assign_pos(current)
            if pos >= 0 and len(_top_level_assign_positions(current)) == 1:
                name = _assign_lhs_name(current)
                if name:
                    lhs_gaps[name] = _assign_gap_before_op(current, pos)
            elif _is_ref_assign_line(current):
                ref_pos = _find_ref_pos(current)
                if ref_pos >= 0:
                    name = current[:ref_pos].strip().split()[-1]
                    if name:
                        lhs_gaps[name] = ref_pos - len(current[:ref_pos].rstrip())
            preamble.append(current)
            i += 1

        result.extend(preamble)

        if i >= len(lines):
            continue

        result.append(lines[i])
        i += 1
        depth = 1
        body: list[str] = []
        while i < len(lines) and depth > 0:
            inner = lines[i]
            inner_upper = inner.strip().upper()
            if inner_upper.startswith("IF ") and "THEN" in inner_upper:
                depth += 1
            elif inner_upper.startswith("END_IF"):
                depth -= 1
                if depth == 0:
                    result.extend(_realign_init_injection_if_body(body, lhs_gaps))
                    result.append(inner)
                    i += 1
                    break
            if depth > 0:
                body.append(inner)
            i += 1

    return result


_RE_CHAINED_ASSIGN_TRUE = re.compile(
    r"^\s*[A-Za-z_]\w*\s*:=\s*[A-Za-z_]\w*\s*:=\s*TRUE;\s*$",
    re.IGNORECASE,
)


def align_pre_chained_true_orphans(lines: list[str]) -> list[str]:
    """Align a lone assign before chained ``a := b := TRUE`` to the second ``:=`` column."""
    result: list[str] = []
    for i, line in enumerate(lines):
        if (
            i + 1 < len(lines)
            and len(_top_level_assign_positions(line)) <= 1
            and (_is_simple_assignment(line) or _is_ref_assign_line(line))
        ):
            nxt = lines[i + 1]
            positions = _top_level_assign_positions(nxt)
            if len(positions) == 2 and _RE_CHAINED_ASSIGN_TRUE.match(nxt.strip()):
                if _is_ref_assign_line(line):
                    result.append(_realign_ref_to_col(line, positions[1]))
                else:
                    result.append(_realign_assign_to_col(line, positions[1]))
                continue
        result.append(line)
    return result


def align_ref_to_preceding_assign(lines: list[str]) -> list[str]:
    """Align ``REF=`` to the assignment column of the immediately preceding line."""
    result: list[str] = []
    for line in lines:
        if _is_ref_assign_line(line) and result:
            prev = result[-1]
            positions = _top_level_assign_positions(prev)
            if len(positions) == 2:
                assign_col = positions[1]
            else:
                assign_col = _find_assign_pos(prev)
            ref_col = _find_ref_pos(line)
            if assign_col >= 0 and ref_col >= 0 and ref_col != assign_col:
                result.append(_realign_ref_to_col(line, assign_col))
                continue
        result.append(line)
    return result


_RE_ENUM_MEMBER = re.compile(
    r"^(\s+)"                              # indent
    r"(\{[^{}]*\}\s*)?"                     # optional attribute pragma
    r"([A-Za-z_]\w*)"                      # name
    r"\s*:=\s*"                            # assign op
    r"([+-]?\d+|2#[01_]+|16#[0-9A-Fa-f_]+)" # decimal, binary, or hex literal (with optional sign)
    r"(,?)"                                # optional comma (no surrounding ws)
    r"\s*"                                 # skip whitespace
    r"((?:\(\*.*?\*\)|//[^\n]*))?"         # optional block or line comment
    r"\s*$"
)

_RE_ENUM_EXPR_MEMBER = re.compile(
    r"^(\s+)"                              # indent
    r"(\{[^{}]*\}\s*)?"                     # optional attribute pragma
    r"([A-Za-z_]\w*)"                      # name
    r"\s*:=\s*"                            # assign op
    r"(.+?)"                               # expression RHS
    r"(,?)"                                # optional trailing comma
    r"\s*"                                 # skip whitespace
    r"((?:\(\*.*?\*\)|//[^\n]*))?"         # optional block or line comment
    r"\s*$"
)


def _is_enum_member_line(line: str) -> bool:
    """True for enum member lines already aligned by ``_align_enum_members``."""
    if line.rstrip().endswith(";"):
        return False
    return bool(_RE_ENUM_MEMBER.match(line) or _RE_ENUM_EXPR_MEMBER.match(line))


def split_inline_enum_members(
    enum_lines: list[str],
    *,
    max_members_per_line: int = 5,
    max_line_length: int = 0,
) -> list[str]:
    """Split comma-separated enum members onto separate lines when over limit or too long."""
    if not enum_lines or max_members_per_line <= 0:
        return enum_lines

    wrap_at = max_line_length if max_line_length > 0 else 99999
    result: list[str] = [enum_lines[0]]

    for line in enum_lines[1:]:
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue

        code_part = stripped
        comment_match = _RE_INLINE_COMMENT.search(code_part)
        trailing_comment = ""
        if comment_match:
            trailing_comment = comment_match.group(0).strip()
            code_part = code_part[: comment_match.start()].rstrip()

        if code_part.startswith(")"):
            result.append(line)
            continue

        members = _split_enum_line_members(line)
        if (
            len(members) <= 1
            or (len(members) <= max_members_per_line and len(line.rstrip()) <= wrap_at)
        ):
            result.append(line)
            continue

        indent_match = re.match(r"^(\s*)", line)
        base_indent = indent_match.group(1) if indent_match else "    "
        for idx, member in enumerate(members):
            suffix = ""
            if idx == len(members) - 1 and trailing_comment:
                suffix = " " + trailing_comment
            result.append(f"{base_indent}{member}{suffix}")

    return result


def _split_enum_line_members(line: str) -> list[str]:
    """Return comma-separated enum member fragments at depth 0, or [] if not splittable."""
    comment_start = len(line)
    for marker in ("(*", "//"):
        pos = line.find(marker)
        if pos >= 0:
            comment_start = min(comment_start, pos)
    code = line[:comment_start].rstrip()
    if "," not in code:
        return []

    indent_match = re.match(r"^(\s*)", code)
    indent_len = len(indent_match.group(1)) if indent_match else 0
    body = code[indent_len:]
    parts = _split_top_level_commas(body)
    members = [part.strip() for part in parts if part.strip()]
    return members if len(members) > 1 else []


def _split_top_level_commas(text: str) -> list[str]:
    """Split *text* on commas not nested in (), [], or strings."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    quote = ""

    for ch in text:
        if in_string:
            current.append(ch)
            if ch == quote:
                in_string = False
            continue
        if ch in ("'", '"'):
            in_string = True
            quote = ch
            current.append(ch)
            continue
        if ch in "([":
            depth += 1
            current.append(ch)
            continue
        if ch in ")]":
            depth = max(0, depth - 1)
            current.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)

    if current:
        parts.append("".join(current))
    return parts


def _align_enum_members(enum_lines: list[str]) -> list[str]:
    """Align ':=' and inline comments in enum member lines.

    Input: full enum block from 'TYPE ... : (' through ')...;'.
    Member lines (name := value/expr) get realigned.
    Blank lines act as group separators; each group is aligned independently.
    """
    if not enum_lines:
        return enum_lines

    result = list(enum_lines)

    # Collect member indices grouped by blank lines.
    member_groups: list[list[tuple[int, str, str, str, str, str, str]]] = []
    current_group: list[tuple[int, str, str, str, str, str, str]] = []

    def _flush_group() -> None:
        nonlocal current_group
        if current_group:
            member_groups.append(current_group)
            current_group = []

    for i, line in enumerate(enum_lines):
        stripped = line.strip()
        if not stripped:
            _flush_group()
            continue
        m = _RE_ENUM_MEMBER.match(line) or _RE_ENUM_EXPR_MEMBER.match(line)
        if m:
            indent, pragma, name, value, comma, comment = m.groups()
            current_group.append(
                (i, indent, pragma or "", name, value.strip(), comma or "", (comment or "").strip())
            )
            continue
        _flush_group()

    _flush_group()

    is_open_paren_style = bool(
        enum_lines
        and enum_lines[0].strip().upper().startswith("TYPE ")
        and enum_lines[0].strip().endswith("(")
    )

    for group in member_groups:
        if len(group) < 2:
            if is_open_paren_style:
                for idx, indent, pragma, name, value, comma, comment in group:
                    result[idx] = f"        {pragma}{name} := {value}{comma}" + (f" {comment}" if comment else "")
            continue

        max_name_len = max(len(m[3]) for m in group)
        has_any_comment = any(m[6] for m in group)
        pending_comments: list[tuple[int, str, str]] = []

        for idx, indent, pragma, name, value, comma, comment in group:
            cur_indent = "        " if is_open_paren_style else indent
            name_padded = name.ljust(max_name_len)
            prefix = f"{cur_indent}{pragma}{name_padded}"
            if comment:
                pending_comments.append((idx, f"{prefix} := {value}{comma}", comment))
            else:
                result[idx] = f"{prefix} := {value}{comma}"

        if pending_comments:
            comment_col = max(len(code) + 1 for _, code, _ in pending_comments)
            for idx, code, comment in pending_comments:
                gap = max(1, comment_col - len(code))
                result[idx] = code + " " * gap + comment

    if is_open_paren_style:
        for idx in range(1, len(result)):
            stripped = result[idx].strip()
            if stripped.startswith(")"):
                result[idx] = "    " + stripped
            elif stripped and ":=" not in stripped:
                result[idx] = "        " + stripped

    return result

    return result


def align_inline_comments(lines: list[str]) -> list[str]:
    """Align trailing ``(* *)`` comments in consecutive code lines.

    Groups lines that end with an inline block comment. Each group is padded so
    comments start at ``max(code_end + 1)`` (end-of-line comment style).
    """
    result: list[str] = []
    group: list[str] = []
    in_block_comment = False

    def _flush() -> None:
        nonlocal group
        if len(group) < 2:
            result.extend(group)
        else:
            parsed: list[tuple[str, str | None, str | None]] = []
            for line in group:
                cm = _RE_INLINE_COMMENT.search(line)
                if cm and line.strip().endswith("*)"):
                    parsed.append((line, line[:cm.start()].rstrip(), cm.group(0).strip()))
                else:
                    parsed.append((line, None, None))
            comment_lines = [(code, comment) for _, code, comment in parsed if code is not None]
            if len(comment_lines) < 2:
                result.extend(group)
            else:
                comment_col = max(len(code) + 1 for code, _ in comment_lines)
                for line, code, comment in parsed:
                    if code is None:
                        result.append(line)
                    else:
                        gap = max(1, comment_col - len(code))
                        result.append(code + " " * gap + comment)
        group = []

    for line in lines:
        stripped = line.strip()

        if in_block_comment:
            _flush()
            result.append(line)
            if "*)" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            _flush()
            result.append(line)
            continue

        if "(**)" in stripped:
            _flush()
            result.append(line)
            continue

        if _is_enum_member_line(line):
            _flush()
            result.append(line)
        elif _is_assign_with_inline_comment(line):
            group.append(line)
        else:
            _flush()
            result.append(line)

    _flush()
    return result


def _strip_comments_and_strings(line: str) -> str:
    """Strip block comments, line comments, and string literals from line."""
    code = _RE_BLOCK_COMMENT.sub(" ", line)
    pos_lc = _find_line_comment_pos(code)
    if pos_lc >= 0:
        code = code[:pos_lc]
    return _strip_strings(code)


def _count_brackets_delta(line: str) -> int:
    """Return net change in [ ] bracket depth for line outside comments and strings."""
    code = _strip_comments_and_strings(line)
    return code.count("[") - code.count("]")


def _is_multiline_array_opener(line: str) -> bool:
    """True for lines opening a multiline array initializer, e.g. ``... := [`` or ``... : ARRAY[...] OF Type[``."""
    stripped = line.strip()
    if "[" not in stripped:
        return False
    code = _RE_BLOCK_COMMENT.sub(" ", stripped).rstrip()
    pos_lc = _find_line_comment_pos(code)
    if pos_lc >= 0:
        code = code[:pos_lc].rstrip()
    if not code:
        return False
    assign_pos = _find_top_level_assign_pos(code)
    if assign_pos >= 0:
        rhs = code[assign_pos + 2:].strip()
        if rhs in ("[", "[("):
            return True
    colon_pos = _find_colon_pos(code)
    if colon_pos >= 0 and re.search(r"\bOF\s+[A-Za-z_]\w*\s*\[$", code):
        return True
    return False


def align_array_struct_inits(
    lines: list[str],
    *,
    field_indent_step: int = 4,
) -> list[str]:
    """Align and canonically indent multiline array initializers.

    Indents array elements by +field_indent_step spaces relative to the declaration/assignment base,
    aligns struct fields inside multiline tuples, and aligns closing ]; to base indent.
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        if _is_multiline_array_opener(lines[i]):
            block, i = _format_multiline_array_block(lines, i, field_indent_step=field_indent_step)
            result.extend(block)
        else:
            result.append(lines[i])
            i += 1
    return result


def _format_multiline_array_block(
    lines: list[str],
    start: int,
    *,
    field_indent_step: int,
) -> tuple[list[str], int]:
    opener_line = lines[start]
    indent_len = len(opener_line) - len(opener_line.lstrip())
    raw_indent = opener_line[:indent_len]
    if "\t" in raw_indent:
        base_indent = " " * len(raw_indent.expandtabs(4))
    else:
        base_indent = raw_indent
    field_indent = base_indent + (" " * field_indent_step)
    sub_field_indent = field_indent + (" " * field_indent_step)

    raw_inner: list[str] = []
    close_line: str | None = None
    i = start + 1
    depth = 1

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("END_") or stripped.startswith("VAR") or stripped.startswith("FUNCTION") or stripped.startswith("PROGRAM"):
            break

        delta = _count_brackets_delta(line)
        depth += delta

        if depth <= 0:
            close_line = line
            i += 1
            break

        if stripped in ("];", "]", ")];", ")]);"):
            close_line = line
            i += 1
            break

        raw_inner.append(line)
        i += 1

    out: list[str] = [opener_line]

    has_expanded_struct_elements = any(ln.strip() == "(" for ln in raw_inner) and any(ln.strip() in (")", "),") for ln in raw_inner)

    if opener_line.strip().endswith(":= [("):
        elements: list[list[str]] = [[]]
        for ln in raw_inner:
            st = ln.strip()
            if st in ("), (", "),("):
                elements.append([])
            elif st in ("),", ")"):
                elements.append([])
            elif st == "(":
                continue
            elif ":=" in ln or st:
                elements[-1].append(ln)

        valid_elements = [g for g in elements if any(x.strip() for x in g)]
        flat_fields = [ln for group in valid_elements for ln in group if ln.strip()]
        aligned_flat = _align_init_field_lines(flat_fields, sub_field_indent)

        cursor = 0
        for ei, group in enumerate(valid_elements):
            count = len([x for x in group if x.strip()])
            out.extend(aligned_flat[cursor : cursor + count])
            cursor += count
            if ei < len(valid_elements) - 1:
                out.append(f"{base_indent}), (")
    elif has_expanded_struct_elements:
        curr_fields: list[str] = []
        in_struct = False

        for ln in raw_inner:
            st = ln.strip()
            if not st:
                out.append("")
                continue
            if st == "(":
                in_struct = True
                curr_fields = []
                out.append(field_indent + "(")
            elif st in (")", "),"):
                if curr_fields:
                    aligned = _align_init_field_lines(curr_fields, sub_field_indent)
                    out.extend(aligned)
                    curr_fields = []
                in_struct = False
                out.append(field_indent + st)
            elif in_struct:
                curr_fields.append(ln)
            else:
                out.append(field_indent + st)
        if curr_fields:
            aligned = _align_init_field_lines(curr_fields, sub_field_indent)
            out.extend(aligned)
    else:
        for ln in raw_inner:
            st = ln.strip()
            if not st:
                out.append("")
            else:
                out.append(field_indent + st)

    if close_line is not None:
        out.append(base_indent + close_line.strip())
    else:
        out.append(base_indent + "];")

    return out, i


def _align_init_field_lines(field_lines: list[str], field_indent: str) -> list[str]:
    """Align ``:=`` and trailing ``(* *)`` comments for struct/array-init fields."""
    if not field_lines:
        return field_lines

    stripped_rows = [field_indent + line.strip() for line in field_lines if line.strip()]
    if len(stripped_rows) < 2:
        return stripped_rows

    fake_block = [field_indent + "("] + stripped_rows
    aligned = _align_call_params(fake_block)
    body = aligned[1:] if len(aligned) > 1 else stripped_rows
    return _align_field_line_comments(body)


def _align_field_line_comments(lines: list[str]) -> list[str]:
    """Column-align trailing block comments on consecutive init field lines."""
    if len(lines) < 2:
        return lines

    parsed: list[tuple[str, str, str | None]] = []
    for line in lines:
        cm = _RE_INLINE_COMMENT.search(line)
        if cm and line.strip().endswith("*)"):
            parsed.append((line, line[: cm.start()].rstrip(), cm.group(0).strip()))
        else:
            parsed.append((line, None, None))

    comment_rows = [(code, comment) for _, code, comment in parsed if code is not None]
    if len(comment_rows) < 2:
        return lines

    comment_col = max(len(code) + 1 for code, _ in comment_rows)
    result: list[str] = []
    for line, code, comment in parsed:
        if code is None:
            result.append(line)
        else:
            gap = max(1, comment_col - len(code))
            result.append(code + " " * gap + comment)
    return result


def align_fb_call_params(lines: list[str]) -> list[str]:
    """Align ':=' / '=>' in multiline FB call and struct-init parameter blocks.

    Detects patterns like:
        FbName(
                param1 := val1,
                param2 := val2);
        IF FindAndSplit(
                param1 := val1,
                ...
                paramN := valN)
        (   field1 := val1,
            field2 := val2)
    And aligns the ':=' operators.
    """
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if _opens_param_block(stripped):
            group = [line]
            depth = stripped.count("(") - stripped.count(")")
            i += 1
            while i < len(lines) and depth > 0:
                group.append(lines[i])
                depth += lines[i].count("(") - lines[i].count(")")
                i += 1
            result.extend(_align_call_params(group))
        else:
            result.append(line)
            i += 1
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_type_header_colon(line: str) -> str:
    """Normalize ``TYPE Name    :`` to golden ``TYPE Name :`` spacing."""
    match = re.match(r"^(\s*TYPE\s+\w+)\s+(:)(.*)$", line, re.IGNORECASE)
    if not match:
        return line
    return f"{match.group(1)} {match.group(2)}{match.group(3)}"


_RE_METHOD_PROPERTY_HEADER = re.compile(
    r"^(\s*(?:METHOD|PROPERTY)\b(?:\s+(?:PRIVATE|PROTECTED|PUBLIC|INTERNAL|ABSTRACT|FINAL))*"
    r"\s+\S+)\s+(:)(.*)$",
    re.IGNORECASE,
)


def _normalize_method_property_header_colon(line: str) -> str:
    """Normalize ``METHOD Foo    : BOOL`` to golden single-space colon."""
    match = _RE_METHOD_PROPERTY_HEADER.match(line)
    if not match:
        return line
    return f"{match.group(1)} {match.group(2)}{match.group(3)}"


_RE_DECL_ADDRESS = re.compile(
    r"^(.+?)\s+(AT\s+%[IQMTXBW][A-Za-z0-9.*]*)\s*$",
    re.IGNORECASE,
)


def _split_decl_name_address(name_part: str) -> tuple[str, str | None]:
    """Split ``name AT %I*`` into base name and address suffix."""
    match = _RE_DECL_ADDRESS.match(name_part.strip())
    if not match:
        return name_part, None
    return match.group(1).strip(), match.group(2).strip()


def normalize_header_and_comment_spacing(lines: list[str]) -> list[str]:
    """Normalize TYPE/METHOD/PROPERTY header colons (idempotent on golden spacing)."""
    result: list[str] = []
    for line in lines:
        line = _normalize_method_property_header_colon(_normalize_type_header_colon(line))
        result.append(line)
    return result


_RE_MULTI_VAR_NAME_DECL = re.compile(
    r"^(\s*(?:\{[^{}]*\}\s*)?)([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+)(\s*:.*)$",
    re.IGNORECASE,
)


def normalize_multi_var_name_commas(lines: list[str]) -> list[str]:
    """Ensure single space after commas in multi-name VAR/decl lines (``a, b : T``)."""
    result: list[str] = []
    for line in lines:
        match = _RE_MULTI_VAR_NAME_DECL.match(line)
        if match:
            prefix, names, suffix = match.groups()
            names = re.sub(r"\s*,\s*", ", ", names)
            line = prefix + names + suffix
        result.append(line)
    return result


def _align_group(group: list[str], max_line_length: int = 0, *,
                 align_init_operator: bool = True,
                 max_init_type_spread: int = 999,
                 align_address_assignments: bool = True,
                 decl_comment_preserve_tight_gap: bool = True,
                 decl_comment_preserve_source_gap: int = 1,
                 decl_comment_preserve_max_col_delta: int = 1,
                 decl_split_outlier_median_multiplier: float = 1.5,
                 decl_split_outlier_median_add: int = 20) -> list[str]:
    """Align a group of declaration lines at ':', ':=', and comments.

    Alignment rules (from golden fixtures):
    1. Names padded to align ':'
    2. Type written as-is (NOT padded to equal width)
    3. Init values written as-is
    4. Comments aligned to same column (max of all prefix lengths + gap)

    If max_line_length > 0 and the aligned result would exceed the limit,
    outlier lines (those with very long types that force excessive padding
    on other lines) are split into their own sub-group.
    """
    if not group:
        return group

    pragma_lines: list[tuple[int, str]] = []
    decl_lines: list[tuple[int, str]] = []

    for i, line in enumerate(group):
        stripped = line.strip()
        if stripped.startswith("{") and "}" in stripped:
            close_pos = stripped.index("}") + 1
            remainder = stripped[close_pos:].strip()
            if remainder and ":" in _strip_strings(remainder):
                decl_lines.append((i, line))
            else:
                pragma_lines.append((i, line))
        elif stripped.startswith("{"):
            pragma_lines.append((i, line))
        else:
            decl_lines.append((i, line))

    if not decl_lines:
        return group

    parsed = [_parse_decl(line) for _, line in decl_lines]
    valid = [p for p in parsed if p is not None]

    if not valid:
        return group

    # Calculate max "effective name width" — includes pragma prefix.
    # Aligns ':' to the same column for ALL lines, treating
    # inline pragmas as part of the prefix before the colon.
    # The indent field contains base_indent + optional pragma_prefix.
    # Find the common base indent (smallest indent that is purely whitespace).
    base_indent_len = min(
        (len(p[4]) - len(p[4].lstrip()) for p in valid if p[4].lstrip() == ""),
        default=min(len(p[4]) - len(p[4].lstrip()) for p in valid),
    )
    # Effective name width: everything after base_indent before colon.
    # When AT-direct variables are present, align base names and address tokens separately.
    address_splits = [_split_decl_name_address(p[0]) for p in valid]
    use_address_align = align_address_assignments and any(addr for _, addr in address_splits)

    if use_address_align:
        max_base_name_len = max(len(base) for base, _ in address_splits)
        max_address_len = max((len(addr) for _, addr in address_splits if addr), default=0)
        at_block_width = max_base_name_len + 1 + max_address_len
        max_name_len = max(len(p[4][base_indent_len:]) + at_block_width for p in valid)
        for p in valid:
            if _split_decl_name_address(p[0])[1] is None:
                max_name_len = max(max_name_len, len(p[4][base_indent_len:]) + len(p[0]))
    else:
        max_name_len = max(len(p[4][base_indent_len:]) + len(p[0]) for p in valid)
    for _, line in decl_lines:
        opener_width = _decl_opener_name_width(line, base_indent_len)
        if opener_width is not None:
            max_name_len = max(max_name_len, opener_width)

    # Build init-type alignment: pad types to align ':=' within consecutive init runs.
    # Skip alignment for runs where the type length spread exceeds max_init_type_spread.
    prefixes: list[str] = []
    init_max_by_idx: dict[int, int] = {}
    run_start = -1
    run_max = 0
    run_min = 0
    run_indices: list[int] = []
    for i, p in enumerate(parsed):
        if p is not None and p[2]:  # has init
            tlen = len(p[1])
            if run_start < 0:
                run_start = i
                run_min = tlen
            run_max = max(run_max, tlen)
            run_min = min(run_min, tlen)
            run_indices.append(i)
        else:
            if run_indices and (run_max - run_min) <= max_init_type_spread:
                for ri in run_indices:
                    init_max_by_idx[ri] = run_max
            run_start = -1
            run_max = 0
            run_min = 0
            run_indices = []
    if run_indices and (run_max - run_min) <= max_init_type_spread:
        for ri in run_indices:
            init_max_by_idx[ri] = run_max

    for i, p in enumerate(parsed):
        if p is None:
            prefixes.append("")
            continue
        name_part, type_part, init_part, _, indent = p
        base_name, address_part = _split_decl_name_address(name_part)
        if use_address_align and address_part:
            name_prefix = (
                base_name.ljust(max_base_name_len)
                + " "
                + address_part.ljust(max_address_len)
            )
            effective_prefix_len = len(indent[base_indent_len:]) + len(name_prefix)
        elif use_address_align:
            name_prefix = name_part.ljust(max_name_len)
            effective_prefix_len = len(indent[base_indent_len:]) + len(name_prefix)
        else:
            effective_prefix_len = len(indent[base_indent_len:]) + len(name_part)
            name_prefix = name_part
        pad_needed = max_name_len - effective_prefix_len
        prefix = indent + name_prefix + " " * pad_needed + " : "
        if init_part and align_init_operator and i in init_max_by_idx:
            prefix += type_part.ljust(init_max_by_idx[i]) + " := " + init_part + ";"
        elif init_part:
            prefix += type_part + " := " + init_part + ";"
        else:
            prefix += type_part + ";"
        prefixes.append(prefix)

    # Find comment alignment columns per CONSECUTIVE COMMENT RUN.
    comment_cols: dict[int, int] = {}
    run_indices: list[int] = []

    def _flush_comment_run(indices: list[int]) -> None:
        if not indices:
            return
        run_max_prefix = max(len(prefixes[ri]) for ri in indices)
        run_col = run_max_prefix + 1
        for ri in indices:
            _, orig_line = decl_lines[ri]
            source_col = _source_comment_col(orig_line)
            if (decl_comment_preserve_tight_gap
                    and source_col >= 0
                    and len(prefixes[ri]) < run_max_prefix
                    and source_col < run_col
                    and (run_col - source_col) <= decl_comment_preserve_max_col_delta
                    and _source_comment_gap(orig_line) == decl_comment_preserve_source_gap):
                # Shorter line: skip inherited padding from a slightly longer sibling.
                comment_cols[ri] = max(len(prefixes[ri]) + 1, source_col)
            else:
                comment_cols[ri] = run_col

    for i, p in enumerate(parsed):
        has_comment = p is not None and p[3]
        if has_comment:
            run_indices.append(i)
        else:
            _flush_comment_run(run_indices)
            run_indices = []
    _flush_comment_run(run_indices)

    aligned: dict[int, str] = {}
    for (idx, _orig_line), p, prefix, i in zip(decl_lines, parsed, prefixes, range(len(parsed))):
        if p is None:
            aligned[idx] = _orig_line
            continue
        _name_part, _type_part, _init_part, comment_part, _indent = p

        if comment_part and i in comment_cols and comment_cols[i] > len(prefix):
            padding = " " * (comment_cols[i] - len(prefix))
            result_line = prefix + padding + comment_part
        elif comment_part:
            result_line = prefix + " " + comment_part
        else:
            result_line = prefix

        result_line = result_line.rstrip()
        aligned[idx] = result_line

    for idx, line in pragma_lines:
        aligned[idx] = line

    init_type_width = max(init_max_by_idx.values()) if init_max_by_idx else None
    for di, (gi, orig_line) in enumerate(decl_lines):
        if parsed[di] is not None:
            continue
        if not _is_multiline_decl_opener(orig_line.strip()):
            continue
        aligned[gi] = _format_multiline_decl_opener(
            orig_line,
            base_indent_len=base_indent_len,
            max_name_len=max_name_len,
            init_type_width=init_type_width,
        )

    result = [aligned[i] for i in range(len(group))]

    # --- Group-Splitting: if alignment pushed lines beyond max_line_length ---
    if max_line_length > 0 and any(len(l) > max_line_length for l in result):
        return _split_and_realign(
            group,
            parsed,
            decl_lines,
            max_line_length,
            align_init_operator=align_init_operator,
            max_init_type_spread=max_init_type_spread,
            decl_comment_preserve_tight_gap=decl_comment_preserve_tight_gap,
            decl_comment_preserve_source_gap=decl_comment_preserve_source_gap,
            decl_comment_preserve_max_col_delta=decl_comment_preserve_max_col_delta,
            decl_split_outlier_median_multiplier=decl_split_outlier_median_multiplier,
            decl_split_outlier_median_add=decl_split_outlier_median_add,
        )

    return result


def _split_and_realign(
    group: list[str],
    parsed: list[tuple[str, str, str, str, str] | None],
    decl_lines: list[tuple[int, str]],
    max_line_length: int,
    *,
    align_init_operator: bool = True,
    max_init_type_spread: int = 999,
    decl_comment_preserve_tight_gap: bool = True,
    decl_comment_preserve_source_gap: int = 1,
    decl_comment_preserve_max_col_delta: int = 1,
    decl_split_outlier_median_multiplier: float = 1.5,
    decl_split_outlier_median_add: int = 20,
) -> list[str]:
    """Split a group with outliers: isolate them with blank lines, keep order.

    Strategy:
    - Find lines whose type+init length is significantly above median
    - Keep them at their original position but isolate with blank lines
    - Each resulting sub-group is aligned independently
    - Outlier lines stay unpadded (single-line groups)

    Output: group1_aligned + blank + outlier + blank + group2_aligned + ...
    """
    decl_kw = {
        "decl_comment_preserve_tight_gap": decl_comment_preserve_tight_gap,
        "decl_comment_preserve_source_gap": decl_comment_preserve_source_gap,
        "decl_comment_preserve_max_col_delta": decl_comment_preserve_max_col_delta,
    }
    # Compute "content width" for each line in the group
    widths_by_idx: dict[int, int] = {}
    for i, p in enumerate(parsed):
        if p is None:
            widths_by_idx[i] = 0
            continue
        _, type_part, init_part, _, _ = p
        widths_by_idx[i] = len(type_part) + (len(init_part) + 4 if init_part else 0)

    # Build a mapping from decl_lines index → group index
    decl_to_group: dict[int, int] = {}
    for di, (gi, _) in enumerate(decl_lines):
        decl_to_group[di] = gi

    positive_widths = sorted(w for w in widths_by_idx.values() if w > 0)
    if len(positive_widths) < 2:
        return _align_group(group, 0, align_init_operator=align_init_operator,
                            max_init_type_spread=max_init_type_spread, **decl_kw)

    median_width = positive_widths[len(positive_widths) // 2]
    threshold = max(
        median_width * decl_split_outlier_median_multiplier,
        median_width + decl_split_outlier_median_add,
    )

    # Identify outlier indices (relative to parsed/decl_lines list)
    outlier_parsed_indices: set[int] = set()
    for i, w in widths_by_idx.items():
        if w > threshold:
            outlier_parsed_indices.add(i)

    if not outlier_parsed_indices or len(outlier_parsed_indices) >= len(widths_by_idx):
        return _align_group(group, 0, align_init_operator=align_init_operator,
                            max_init_type_spread=max_init_type_spread, **decl_kw)

    # Map parsed indices back to group indices
    outlier_group_indices: set[int] = set()
    for pi in outlier_parsed_indices:
        if pi < len(decl_lines):
            outlier_group_indices.add(decl_lines[pi][0])

    # Build result: split into sub-groups at outlier positions, insert blank lines
    result: list[str] = []
    current_sub: list[str] = []

    for i, line in enumerate(group):
        if i in outlier_group_indices:
            # Flush preceding sub-group
            if current_sub:
                result.extend(_align_group(current_sub, 0, align_init_operator=align_init_operator,
                                           max_init_type_spread=max_init_type_spread, **decl_kw))
                result.append("")  # blank line before outlier
            # Outlier as standalone (minimal alignment = just itself)
            result.extend(_align_group([line], 0, align_init_operator=align_init_operator,
                                       max_init_type_spread=max_init_type_spread, **decl_kw))
            result.append("")  # blank line after outlier
            current_sub = []
        else:
            current_sub.append(line)

    # Flush remaining sub-group
    if current_sub:
        # Remove trailing blank line if the group ends with one
        if result and result[-1] == "":
            pass  # keep it — it separates outlier from this group
        result.extend(_align_group(current_sub, 0, align_init_operator=align_init_operator,
                                   max_init_type_spread=max_init_type_spread, **decl_kw))

    # Clean up: remove trailing blank line at the very end
    while result and result[-1] == "":
        result.pop()

    return result


def _source_comment_col(line: str) -> int:
    """Return the column of an inline ``(* *)`` comment in *line*."""
    cm = _RE_INLINE_COMMENT.search(line)
    if not cm:
        return -1
    return cm.start()


def _source_comment_gap(line: str) -> int:
    """Return spaces between the last ``;`` and an inline ``(* *)`` comment."""
    cm = _RE_INLINE_COMMENT.search(line)
    if not cm:
        return 0
    code = line[:cm.start()].rstrip()
    semi = code.rfind(";")
    if semi < 0:
        return cm.start() - len(code)
    return cm.start() - semi - 1


def _decl_opener_name_width(line: str, base_indent_len: int) -> int | None:
    """Effective name width for a multiline declaration opener (``name : type :=``)."""
    cm = _RE_INLINE_COMMENT.search(line)
    code = line[:cm.start()].rstrip() if cm else line.rstrip()
    pos_lc = _find_line_comment_pos(code)
    if pos_lc >= 0:
        code = code[:pos_lc].rstrip()
    if code.endswith(";"):
        return None
    content = code.strip()
    colon_pos = _find_colon_pos(content)
    if colon_pos < 0:
        return None
    name_part = content[:colon_pos].strip()
    indent_match = re.match(r"^(\s*)", line)
    indent = indent_match.group(1) if indent_match else ""
    return len(indent[base_indent_len:]) + len(name_part)


def _format_multiline_decl_opener(
    line: str,
    *,
    base_indent_len: int,
    max_name_len: int,
    init_type_width: int | None,
) -> str:
    """Format ``name : type :=`` opener lines for multiline declaration inits."""
    cm = _RE_INLINE_COMMENT.search(line)
    comment = (" " + cm.group(0).strip()) if cm else ""
    code = line[:cm.start()].rstrip() if cm else line.rstrip()
    pos_lc = _find_line_comment_pos(code)
    if pos_lc >= 0:
        trail = code[pos_lc + 2:]
        comment = " // " + trail.strip() + comment
        code = code[:pos_lc].rstrip()

    if base_indent_len > 0:
        indent = " " * base_indent_len
    else:
        indent_match = re.match(r"^(\s*)", line)
        indent = indent_match.group(1) if indent_match else ""
    content = code.strip()
    colon_pos = _find_colon_pos(content)
    assign_pos = _find_top_level_assign_pos(content)
    if colon_pos < 0:
        return line
    if assign_pos < 0:
        name = content[:colon_pos].strip()
        type_part = content[colon_pos + 1:].strip()
        effective_prefix_len = len(indent[base_indent_len:]) + len(name)
        pad_needed = max(0, max_name_len - effective_prefix_len)
        prefix = indent + name + " " * pad_needed + " : " + type_part
        return prefix.rstrip() + comment

    name = content[:colon_pos].strip()
    type_part = content[colon_pos + 1:assign_pos].strip()
    effective_prefix_len = len(indent[base_indent_len:]) + len(name)
    pad_needed = max(0, max_name_len - effective_prefix_len)
    prefix = indent + name + " " * pad_needed + " : "
    after_assign = content[assign_pos + 2:].strip()
    if init_type_width is not None and init_type_width > 0:
        prefix += type_part.ljust(init_type_width) + " :="
    else:
        prefix += type_part + " :="
    if after_assign:
        prefix += " " + after_assign
    return prefix.rstrip() + comment


def _find_top_level_assign_pos(content: str) -> int:
    """Find ':=' at parenthesis depth 0 (declaration init, not FB-param init)."""
    if ":=" not in content:
        return -1
    masked = _strip_strings(content)
    if "(*" in masked:
        masked = _RE_BLOCK_COMMENT.sub(lambda m: " " * len(m.group(0)), masked)
    depth = 0
    i = 0
    while i < len(masked) - 1:
        ch = masked[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and masked[i + 1] == "=" and depth == 0:
            return i
        i += 1
    return -1


def _parse_decl(line: str) -> tuple[str, str, str, str, str] | None:
    """Parse declaration line into (name, type, init, comment, indent).

    Handles inline pragma prefix (e.g. {attribute ...} _var : TYPE;)
    Returns None for multiline declarations (lines not ending with ;).
    """
    comment = ""
    cm = _RE_INLINE_COMMENT.search(line)
    if cm:
        comment = cm.group(0).strip()
        line = line[:cm.start()].rstrip()

    pos_lc = _find_line_comment_pos(line)
    if pos_lc >= 0:
        comment = "// " + line[pos_lc + 2:].strip()
        line = line[:pos_lc].rstrip()

    # Multiline declaration guard: if code doesn't end with ; it's a continuation
    code_stripped = line.strip()
    if code_stripped and not code_stripped.endswith(";"):
        return None

    indent_match = re.match(r"^(\s*)", line)
    indent = indent_match.group(1) if indent_match else ""
    content = line.strip()

    # Handle inline pragma prefix
    pragma_prefix = ""
    if content.startswith("{") and "}" in content:
        close_pos = content.index("}") + 1
        remainder = content[close_pos:].strip()
        if remainder and ":" in _strip_strings(remainder):
            pragma_prefix = content[:close_pos] + " "
            content = remainder

    if ":" not in _strip_strings(content):
        return None

    colon_pos = _find_colon_pos(content)
    if colon_pos < 0:
        return None

    name_part = content[:colon_pos].strip()
    rest = content[colon_pos + 1:].strip()

    init_part = ""
    assign_pos = _find_top_level_assign_pos(rest)
    if assign_pos >= 0:
        type_part = rest[:assign_pos].strip().rstrip(";")
        init_rest = rest[assign_pos + 2:].strip()
        if init_rest.endswith(";"):
            init_rest = init_rest[:-1].rstrip()
        init_part = init_rest
    else:
        type_part = rest.rstrip(";").strip()

    # Prepend pragma to indent for reconstruction
    if pragma_prefix:
        indent = indent + pragma_prefix

    return name_part, type_part, init_part, comment, indent


def _find_colon_pos(content: str) -> int:
    """Find position of declaration colon (not := or :: or time-literal separator).

    Skips colons inside strings, block comments, := pairs, :: pairs,
    and colons between digits (time/date literal separators like TOD#19:00:00).
    """
    if ":" not in content:
        return -1
    safe_content = _strip_strings(content)
    i = 0
    while i < len(safe_content):
        if safe_content[i] == "(" and i + 1 < len(safe_content) and safe_content[i + 1] == "*":
            end = safe_content.find("*)", i + 2)
            i = end + 2 if end >= 0 else len(safe_content)
        elif safe_content[i] == ":":
            if i + 1 < len(safe_content) and safe_content[i + 1] == "=":
                i += 2
            elif i + 1 < len(safe_content) and safe_content[i + 1] == ":":
                i += 2
            elif (
                i > 0
                and safe_content[i - 1].isdigit()
                and i + 1 < len(safe_content)
                and safe_content[i + 1].isdigit()
            ):
                # Time/date literal separator (e.g. TOD#19:00:00), not name3 : TYPE.
                i += 1
            else:
                return i
        else:
            i += 1
    return -1


def _is_ref_assign_line(line: str) -> bool:
    """True for ``name REF= value;`` lines (no ``:=``)."""
    stripped = line.strip()
    if ":=" in stripped:
        return False
    return bool(re.search(r"\bREF=\s*\S", stripped))


def _assign_operator_target_col(
    group: list[str],
    lhs_lens: list[int],
    *,
    max_line_length: int = 0,
    three_line_assign_group_count: int = 3,
    three_line_assign_group_min_spread: int = 12,
    three_line_assign_group_max_lhs_len: int = 36,
    three_line_assign_group_min_qualified_count: int = 2,
    three_line_assign_group_extra_pad: int = 2,
) -> int:
    """Target ``:=`` / ``REF=`` column for an assignment group."""
    if not lhs_lens:
        return 0
    spread = max(lhs_lens) - min(lhs_lens)
    assign_only = [line for line in group if _find_assign_pos(line) >= 0]
    has_overlength = (
        max_line_length > 0
        and any(len(line.rstrip()) > max_line_length for line in assign_only)
    )
    qualified_lhs = [
        line[: _find_assign_pos(line)].lstrip()
        for line in assign_only
        if "." in line[: _find_assign_pos(line)]
    ]
    same_base_variable = bool(
        qualified_lhs
        and len({lhs.split(".")[0] for lhs in qualified_lhs}) == 1
    )
    if (
        not has_overlength
        and three_line_assign_group_count > 0
        and three_line_assign_group_extra_pad > 0
        and len(assign_only) == three_line_assign_group_count
        and spread > three_line_assign_group_min_spread
        and max(lhs_lens) == three_line_assign_group_max_lhs_len
        and len(qualified_lhs) >= three_line_assign_group_min_qualified_count
        and same_base_variable
        and all("[" not in line[: _find_assign_pos(line)] for line in assign_only)
    ):
        return max(lhs_lens) + three_line_assign_group_extra_pad
    return max(lhs_lens) + 1


def _find_ref_pos(line: str) -> int:
    """Return index of ``R`` in ``REF=`` for a reference assignment line."""
    m = re.search(r"\bREF=", line)
    return m.start() if m else -1


def _realign_ref_to_col(line: str, target_col: int) -> str:
    pos = _find_ref_pos(line)
    if pos < 0:
        return line
    lhs = line[:pos].rstrip()
    rhs = line[pos:].lstrip()
    padding = max(1, target_col - len(lhs))
    return lhs + " " * padding + rhs


def _following_assign_col(line: str) -> int | None:
    """Column of a usable ``:=`` anchor on the next line (assignment or call opener)."""
    if _is_simple_assignment(line):
        return _find_assign_pos(line)
    stripped = line.strip()
    if ":=" not in stripped or stripped.endswith(";"):
        return None
    pos = _find_assign_pos(line)
    if pos < 0:
        return None
    lhs = line[:pos].rstrip()
    name = lhs.strip()
    if not name or "." in name:
        return None
    return pos


def _align_orphan_to_following_assign(orphan: str, following: list[str]) -> str:
    """Align a lone ``:=`` line to the next line that contains ``:=``."""
    if not _is_simple_assignment(orphan):
        return orphan
    orphan_indent = len(orphan) - len(orphan.lstrip())
    saw_blank = False
    for fl in following:
        if not fl.strip():
            saw_blank = True
            continue
        if saw_blank:
            return orphan
        fl_indent = len(fl) - len(fl.lstrip())
        if fl_indent != orphan_indent:
            return orphan
        anchor_col = _following_assign_col(fl)
        if anchor_col is not None:
            return _realign_assign_to_col(orphan, anchor_col)
        break
    return orphan


def _align_assign_group(
    group: list[str],
    max_spread: int = 12,
    *,
    max_line_length: int = 0,
    bool_literal_min_group_lines: int = 3,
    bool_literal_name_spread_max: int = 2,
    assign_already_aligned_max_gap: int = 1,
    compact_group_min_lines: int = 4,
    compact_group_max_over_pad: int = 3,
    compact_three_line_count: int = 3,
    compact_three_line_over_pad: int = 2,
    compact_pair_assigns: bool = True,
    compact_pair_min_over_pad: int = 8,
    three_line_assign_group_count: int = 3,
    three_line_assign_group_min_spread: int = 12,
    three_line_assign_group_max_lhs_len: int = 36,
    three_line_assign_group_min_qualified_count: int = 2,
    three_line_assign_group_extra_pad: int = 2,
) -> list[str]:
    """Align ``:=`` and ``REF=`` operators in a group of assignment lines."""
    lhs_lens: list[int] = []
    for line in group:
        if _is_ref_assign_line(line):
            pos = _find_ref_pos(line)
        else:
            pos = _find_assign_pos(line)
        if pos >= 0:
            lhs_lens.append(len(line[:pos].rstrip()))

    if not lhs_lens:
        return group

    has_ref = any(_is_ref_assign_line(line) for line in group)
    assign_positions = [_find_assign_pos(line) for line in group if _find_assign_pos(line) >= 0]

    if not has_ref and len(group) >= bool_literal_min_group_lines:
        all_bool_literals = all(
            re.match(r"^\s*\S+\s*:=\s*(TRUE|FALSE);\s*$", line) for line in group
        )
        if all_bool_literals:
            name_spread = max(len(line[:_find_assign_pos(line)].rstrip()) for line in group) - min(
                len(line[:_find_assign_pos(line)].rstrip()) for line in group
            )
            if name_spread <= bool_literal_name_spread_max:
                assign_positions = [_find_assign_pos(line) for line in group]
                if len(set(assign_positions)) == 1:
                    return group

    assign_pairs = [(line, pos) for line in group for pos in [_find_assign_pos(line)] if pos >= 0]
    expected_target = _assign_operator_target_col(
        group,
        lhs_lens,
        max_line_length=max_line_length,
        three_line_assign_group_count=three_line_assign_group_count,
        three_line_assign_group_min_spread=three_line_assign_group_min_spread,
        three_line_assign_group_max_lhs_len=three_line_assign_group_max_lhs_len,
        three_line_assign_group_min_qualified_count=three_line_assign_group_min_qualified_count,
        three_line_assign_group_extra_pad=three_line_assign_group_extra_pad,
    )

    if has_ref and assign_positions and len(set(assign_positions)) == 1:
        assign_col = assign_positions[0]
        ref_cols = [_find_ref_pos(line) for line in group if _find_ref_pos(line) >= 0]
        if (
            ref_cols
            and len(set(ref_cols)) == 1
            and ref_cols[0] == assign_col
            and assign_col >= expected_target
        ):
            return group

    if len(assign_pairs) >= 2 and len({pos for _, pos in assign_pairs}) == 1:
        assign_col = assign_pairs[0][1]
        if assign_col > expected_target:
            return group
        if assign_col == expected_target:
            gaps = [_assign_gap_before_op(line, pos) for line, pos in assign_pairs]
            if max(gaps) <= assign_already_aligned_max_gap:
                return group
            over_pad = assign_col - expected_target
            if (compact_group_min_lines > 0
                    and len(assign_pairs) >= compact_group_min_lines
                    and 0 < over_pad <= compact_group_max_over_pad):
                return _compact_assign_group([line for line, _ in assign_pairs], assign_col)
            if (compact_three_line_count > 0
                    and len(assign_pairs) == compact_three_line_count
                    and over_pad == compact_three_line_over_pad):
                return _compact_assign_group([line for line, _ in assign_pairs], assign_col)
            if (compact_pair_assigns and len(assign_pairs) == 2 and over_pad >= compact_pair_min_over_pad):
                lhs_lens_in_group = [len(line[:assign_col].rstrip()) for line, _ in assign_pairs]
                max_lhs = max(lhs_lens_in_group) if lhs_lens_in_group else 0
                if (max(lhs_lens_in_group) - min(lhs_lens_in_group) == 0
                        and assign_col <= max_lhs + 3):
                    return _compact_assign_group([line for line, _ in assign_pairs], assign_col)
            return group

    if assign_positions and len(set(assign_positions)) == 1:
        if assign_positions[0] == expected_target:
            if not has_ref:
                return group
            ref_cols = [_find_ref_pos(line) for line in group if _find_ref_pos(line) >= 0]
            if (
                ref_cols
                and len(set(ref_cols)) == 1
                and ref_cols[0] == assign_positions[0]
            ):
                return group

    min_indent = min(len(l) - len(l.lstrip()) for l in group if l.strip())
    name_lens = [l - min_indent for l in lhs_lens]
    if name_lens and max(name_lens) - min(name_lens) > max_spread:
        return group

    target = _assign_operator_target_col(
        group,
        lhs_lens,
        max_line_length=max_line_length,
        three_line_assign_group_count=three_line_assign_group_count,
        three_line_assign_group_min_spread=three_line_assign_group_min_spread,
        three_line_assign_group_max_lhs_len=three_line_assign_group_max_lhs_len,
        three_line_assign_group_min_qualified_count=three_line_assign_group_min_qualified_count,
        three_line_assign_group_extra_pad=three_line_assign_group_extra_pad,
    )

    result: list[str] = []
    for line in group:
        if _is_ref_assign_line(line):
            result.append(_realign_ref_to_col(line, target))
            continue
        pos = _find_assign_pos(line)
        if pos < 0:
            result.append(line)
            continue
        lhs = line[:pos].rstrip()
        rhs = line[pos + 2:].lstrip()
        padding = max(1, target - len(lhs))
        result.append(lhs + " " * padding + ":= " + rhs)
    return result


def align_for_body_assignments(
    lines: list[str],
    *,
    indent_size: int = 4,
    max_spread: int = 12,
    bool_literal_min_group_lines: int = 3,
    bool_literal_name_spread_max: int = 2,
    assign_already_aligned_max_gap: int = 1,
    align_for_body_min_group_lines: int = 3,
    align_for_body_long_rhs_len_threshold: int = 30,
    align_for_body_min_lhs_spread_for_alignment: int = 3,
    compact_pair_assigns: bool = True,
    compact_pair_min_over_pad: int = 8,
) -> list[str]:
    """Align ``:=`` for assignments at the same indent inside each ``FOR`` body.

    Aligns across ``IF``/``CONTINUE`` barriers within a loop body.
    """
    result = list(lines)
    for_depth = 0
    for_start = -1
    in_block_comment = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        if in_block_comment:
            if "*)" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            continue

        upper = stripped.upper()
        if upper.startswith("FOR ") and upper.endswith(" DO"):
            for_depth += 1
            for_start = i
            continue

        if upper == "END_FOR" and for_depth > 0:
            for_depth -= 1
            if for_depth == 0 and for_start >= 0:
                _align_for_region_assignments(
                    result,
                    for_start + 1,
                    i,
                    indent_size=indent_size,
                    max_spread=max_spread,
                    bool_literal_min_group_lines=bool_literal_min_group_lines,
                    bool_literal_name_spread_max=bool_literal_name_spread_max,
                    assign_already_aligned_max_gap=assign_already_aligned_max_gap,
                    align_for_body_min_group_lines=align_for_body_min_group_lines,
                    align_for_body_long_rhs_len_threshold=align_for_body_long_rhs_len_threshold,
                    align_for_body_min_lhs_spread_for_alignment=align_for_body_min_lhs_spread_for_alignment,
                    compact_pair_assigns=compact_pair_assigns,
                    compact_pair_min_over_pad=compact_pair_min_over_pad,
                )
                for_start = -1
            continue

    return result


def _align_for_region_assignments(
    lines: list[str],
    start: int,
    end: int,
    *,
    indent_size: int,
    max_spread: int,
    bool_literal_min_group_lines: int,
    bool_literal_name_spread_max: int,
    assign_already_aligned_max_gap: int,
    align_for_body_min_group_lines: int,
    align_for_body_long_rhs_len_threshold: int,
    align_for_body_min_lhs_spread_for_alignment: int,
    compact_pair_assigns: bool,
    compact_pair_min_over_pad: int,
) -> None:
    """Align same-indent assignments within ``lines[start:end]`` (FOR body)."""
    if start >= end:
        return

    for_line = lines[start - 1]
    for_indent = len(for_line) - len(for_line.lstrip())
    body_indent = for_indent + indent_size

    runs: list[list[int]] = []
    current_run: list[int] = []
    for i in range(start, end):
        line = lines[i]
        if not line.strip():
            if current_run:
                runs.append(current_run)
                current_run = []
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent == body_indent and _is_simple_assignment(line) and _has_simple_assign_lhs(line):
            current_run.append(i)
        else:
            if current_run:
                runs.append(current_run)
                current_run = []
    if current_run:
        runs.append(current_run)

    for assign_indices in runs:
        if len(assign_indices) < align_for_body_min_group_lines:
            continue

        group = [lines[i] for i in assign_indices]
        if not _should_loose_align_for_group(
            group,
            bool_literal_min_group_lines=bool_literal_min_group_lines,
            bool_literal_name_spread_max=bool_literal_name_spread_max,
            align_for_body_long_rhs_len_threshold=align_for_body_long_rhs_len_threshold,
            align_for_body_min_lhs_spread_for_alignment=align_for_body_min_lhs_spread_for_alignment,
        ):
            continue

        aligned = _align_assign_group(
            group,
            max_spread,
            bool_literal_min_group_lines=bool_literal_min_group_lines,
            bool_literal_name_spread_max=bool_literal_name_spread_max,
            assign_already_aligned_max_gap=assign_already_aligned_max_gap,
            compact_pair_assigns=compact_pair_assigns,
            compact_pair_min_over_pad=compact_pair_min_over_pad,
        )
        for idx, new_line in zip(assign_indices, aligned):
            lines[idx] = new_line


_RE_SIMPLE_ASSIGN_LHS = re.compile(r"^\s*[A-Za-z_]\w*\s*:=")


def _has_simple_assign_lhs(line: str) -> bool:
    """True when LHS is a single identifier (no field/array subscript before ':=')."""
    return bool(_RE_SIMPLE_ASSIGN_LHS.match(line))


def _should_loose_align_for_group(
    group: list[str],
    *,
    bool_literal_min_group_lines: int,
    bool_literal_name_spread_max: int,
    align_for_body_long_rhs_len_threshold: int,
    align_for_body_min_lhs_spread_for_alignment: int,
) -> bool:
    """Skip FOR-body align for compact bool/literal groups that should stay unpadded."""
    if len(group) >= bool_literal_min_group_lines and all(
        re.match(r"^\s*\S+\s*:=\s*(TRUE|FALSE);\s*$", line) for line in group
    ):
        lhs_lens = [len(line[:_find_assign_pos(line)].rstrip()) for line in group if _find_assign_pos(line) >= 0]
        if lhs_lens and max(lhs_lens) - min(lhs_lens) <= bool_literal_name_spread_max:
            return False

    lhs_lens: list[int] = []
    long_rhs = False
    for line in group:
        pos = _find_assign_pos(line)
        if pos < 0:
            continue
        lhs_lens.append(len(line[:pos].rstrip()))
        rhs = line[pos + 2:].strip()
        if len(rhs) > align_for_body_long_rhs_len_threshold:
            long_rhs = True
    if not lhs_lens:
        return False
    if long_rhs:
        return True
    return max(lhs_lens) - min(lhs_lens) >= align_for_body_min_lhs_spread_for_alignment


def expand_tight_assignment_spacing(lines: list[str]) -> list[str]:
    """Normalize ``name:= rhs`` / ``name:=rhs`` to ``name := rhs`` before alignment passes."""
    result: list[str] = []
    for line in lines:
        if not _is_simple_assignment(line):
            result.append(line)
            continue
        pos = _find_assign_pos(line)
        if pos < 0:
            result.append(line)
            continue
        lhs = line[:pos].rstrip()
        gap = pos - len(lhs)
        if gap > 0:
            result.append(line)
            continue
        rhs = line[pos + 2:].lstrip()
        result.append(lhs + " := " + rhs)
    return result


def compact_orphan_overpadded_assigns(lines: list[str], *, min_gap: int = 3,
                                        max_gap: int = 0,
                                        simple_identifier_only: bool = False,
                                        expression_rhs_max_gap: int = 0,
                                        expression_rhs_min_gap_floor: int = 10,
                                        skip_rhs_or_and_chain: bool = True) -> list[str]:
    """Compact single assignments over-padded vs their LHS when not in an aligned block.

    When *max_gap* > 0, only compact lines whose padding gap is in [min_gap, max_gap].
    When *simple_identifier_only* is true, only compact when RHS is a bare identifier,
    unless *expression_rhs_max_gap* > 0 and gap <= that limit (messy-source orphan noise).
    """
    result: list[str] = []
    for i, line in enumerate(lines):
        if not _is_simple_assignment(line):
            result.append(line)
            continue
        pos = _find_assign_pos(line)
        if pos < 0:
            result.append(line)
            continue
        lhs = line[:pos].rstrip()
        gap = pos - len(lhs)
        if gap < min_gap:
            result.append(line)
            continue
        if max_gap > 0 and gap > max_gap:
            result.append(line)
            continue
        same_col_neighbor = False
        for j in (i - 1, i + 1):
            if 0 <= j < len(lines) and _is_simple_assignment(lines[j]):
                if _find_assign_pos(lines[j]) == pos:
                    same_col_neighbor = True
                    break
        if same_col_neighbor:
            result.append(line)
            continue
        rhs = line[pos + 2:].lstrip()
        if simple_identifier_only:
            if not re.match(r"^[A-Za-z_]\w*;\s*$", rhs):
                min_expr_gap = max(min_gap, expression_rhs_min_gap_floor)
                if expression_rhs_max_gap <= 0 or gap < min_expr_gap or gap > expression_rhs_max_gap:
                    result.append(line)
                    continue
        if skip_rhs_or_and_chain and (" OR " in rhs.upper() or " AND " in rhs.upper()):
            result.append(line)
            continue
        result.append(lhs + " := " + rhs)
    return result


def compact_same_col_outlier_assigns(lines: list[str], *, min_gap: int = 8,
                                     lhs_delta: int = 2) -> list[str]:
    """Compact over-padded lines that share a ``:=`` column with longer siblings."""
    assign_rows: list[tuple[int, int, int]] = []
    for i, line in enumerate(lines):
        if not _is_simple_assignment(line):
            continue
        pos = _find_assign_pos(line)
        if pos < 0:
            continue
        lhs_len = len(line[:pos].rstrip())
        gap = pos - lhs_len
        if gap >= min_gap:
            assign_rows.append((i, pos, lhs_len))

    compact_indices: set[int] = set()
    by_col: dict[int, list[tuple[int, int]]] = {}
    for i, pos, lhs_len in assign_rows:
        by_col.setdefault(pos, []).append((i, lhs_len))

    for pos, entries in by_col.items():
        if len(entries) < 2:
            continue
        max_lhs = max(l for _, l in entries)
        for i, lhs_len in entries:
            if lhs_len < max_lhs - lhs_delta:
                compact_indices.add(i)

    result = list(lines)
    for i in compact_indices:
        line = result[i]
        pos = _find_assign_pos(line)
        lhs = line[:pos].rstrip()
        rhs = line[pos + 2:].lstrip()
        result[i] = lhs + " := " + rhs
    return result


def _compact_assign_group(group: list[str], assign_col: int) -> list[str]:
    """Re-align an over-padded group that already shares the ':=' column."""
    lhs_lens = [len(line[:assign_col].rstrip()) for line in group]
    target = max(lhs_lens) + 1
    result: list[str] = []
    for line in group:
        pos = _find_assign_pos(line)
        if pos < 0:
            result.append(line)
            continue
        lhs = line[:pos].rstrip()
        rhs = line[pos + 2:].lstrip()
        padding = max(1, target - len(lhs))
        result.append(lhs + " " * padding + ":= " + rhs)
    return result


def _assign_gap_before_op(line: str, pos: int) -> int:
    """Return whitespace count between LHS content and ':='."""
    lhs = line[:pos].rstrip()
    return pos - len(lhs)


def _find_assign_pos(line: str) -> int:
    """Find position of ':=' avoiding strings/comments."""
    masked = _strip_strings(line)
    masked = _RE_BLOCK_COMMENT.sub(lambda m: " " * len(m.group()), masked)
    return masked.find(":=")


def _align_call_params(param_lines: list[str]) -> list[str]:
    """Align ':=' / '=>' in FB call parameter lines.

    Groups params by indent level and aligns each group separately.
    Target per group = indent + max(name_len_in_group) + 1.
    """
    if len(param_lines) < 2:
        return param_lines

    opener = param_lines[0].strip()
    struct_init = (
        _RE_STRUCT_INIT_OPEN.match(param_lines[0]) is not None
        or (opener.startswith("(") and _find_assign_pos(param_lines[0]) >= 0)
    )
    if struct_init:
        result: list[str] = []
        params = param_lines
    else:
        result = [param_lines[0]]
        params = param_lines[1:]

    # Group lines by indent level, splitting at indent changes
    # (multiline continuations break alignment groups)
    indent_groups: list[list[tuple[int, str]]] = []
    current_indent = -1
    current_group: list[tuple[int, str]] = []
    non_assign_streak = 0

    for idx, line in enumerate(params):
        pos = _find_assign_pos(line)
        if pos < 0:
            pos = line.find("=>")
        if pos < 0:
            # Non-assign line: track but check indent
            line_indent = len(line) - len(line.lstrip())
            if current_indent >= 0 and line_indent != current_indent:
                non_assign_streak += 1
            current_group.append((idx, line))
            continue

        lhs = line[:pos].rstrip()
        indent_len = len(lhs) - len(lhs.lstrip())

        # Split group if indent changed OR non-assign lines interrupted
        if current_indent < 0:
            current_indent = indent_len
            current_group.append((idx, line))
        elif indent_len == current_indent and non_assign_streak == 0:
            current_group.append((idx, line))
        else:
            if current_group:
                indent_groups.append(current_group)
            current_indent = indent_len
            current_group = [(idx, line)]
        non_assign_streak = 0

    if current_group:
        indent_groups.append(current_group)

    # Align each group separately
    aligned: dict[int, str] = {}
    for group in indent_groups:
        name_lens: list[int] = []
        for _, line in group:
            pos = _find_assign_pos(line)
            if pos < 0:
                pos = line.find("=>")
            if pos >= 0:
                lhs = line[:pos].rstrip()
                name_lens.append(len(lhs.lstrip()))

        if not name_lens:
            continue

        group_indent = 0
        for _, line in group:
            pos = _find_assign_pos(line)
            if pos < 0:
                pos = line.find("=>")
            if pos >= 0:
                lhs = line[:pos].rstrip()
                group_indent = len(lhs) - len(lhs.lstrip())
                break

        target = group_indent + max(name_lens) + 1

        for idx, line in group:
            pos = _find_assign_pos(line)
            if pos < 0:
                pos = line.find("=>")
            if pos >= 0:
                lhs = line[:pos].rstrip()
                rhs = line[pos:]
                padding = target - len(lhs)
                if padding < 1:
                    padding = 1
                aligned[idx] = lhs + " " * padding + rhs
            else:
                aligned[idx] = line

    # Build final result preserving order
    for idx, line in enumerate(params):
        result.append(aligned.get(idx, line))

    if struct_init and result and _RE_STRUCT_INIT_OPEN.match(result[0]):
        result = _apply_struct_init_opener_offset(result)

    return result


def _apply_struct_init_opener_offset(lines: list[str]) -> list[str]:
    """Align ``( field :=`` opener using ``:=`` one column right of continuation fields."""
    cont_rows: list[tuple[int, int, str]] = []
    for idx, line in enumerate(lines[1:], start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(")"):
            continue
        pos = _find_assign_pos(line)
        if pos >= 0:
            cont_rows.append((idx, pos, line))
    if not cont_rows:
        return lines

    result = list(lines)
    cont_positions = [pos for _, pos, _ in cont_rows]
    if len(set(cont_positions)) > 1:
        target = max(len(line[:pos].rstrip()) for _, pos, line in cont_rows) + 1
        for idx, pos, line in cont_rows:
            lhs = line[:pos].rstrip()
            rhs = line[pos:].lstrip()
            padding = max(1, target - len(lhs))
            result[idx] = lhs + " " * padding + rhs
        cont_col = target
    else:
        cont_col = cont_positions[0]

    opener_pos = _find_assign_pos(result[0])
    if opener_pos < 0:
        return result

    target_opener = cont_col + 1
    if opener_pos == target_opener:
        return result

    line = result[0]
    lhs = line[:opener_pos].rstrip()
    rhs = line[opener_pos:].lstrip()
    padding = max(1, target_opener - len(lhs))
    result[0] = lhs + " " * padding + rhs
    return result


_RE_BOOL_CHAIN_OP = re.compile(r"\bAND_THEN\b|\bOR_ELSE\b", re.IGNORECASE)


def _is_simple_assignment(line: str) -> bool:
    """Check if line is a simple 'x := expr;' assignment.

    Excludes control flow and complex boolean chains (AND_THEN/OR_ELSE
    at top level outside parentheses).
    Allows lines with nested := inside function call parameters.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("//") or stripped.startswith("(*"):
        return False
    if ":=" not in stripped:
        return False
    if stripped.startswith("{"):
        return False
    if stripped.startswith("IF") or stripped.startswith("ELSIF"):
        return False
    if stripped.startswith("FOR") or stripped.startswith("WHILE"):
        return False
    if "'" in stripped or '"' in stripped:
        code = _strip_strings(stripped)
    else:
        code = stripped
    if "(*" in code:
        code = _RE_BLOCK_COMMENT.sub("", code)
    if not code.rstrip().endswith(";"):
        return False
    # Count only top-level := (depth 0) — nested := inside calls are OK
    top_level_assigns = 0
    first_assign_pos = -1
    depth = 0
    min_depth = 0
    i = 0
    while i < len(code) - 1:
        if code[i] == "(":
            depth += 1
        elif code[i] == ")":
            depth -= 1
            if depth < min_depth:
                min_depth = depth
        elif code[i] == ":" and code[i + 1] == "=" and depth == 0:
            top_level_assigns += 1
            if first_assign_pos < 0:
                first_assign_pos = i
        i += 1
    if top_level_assigns != 1:
        return False
    colon_pos = _find_colon_pos(code)
    if colon_pos >= 0 and colon_pos < first_assign_pos:
        return False
    # Negative depth = closing someone else's paren → part of multiline call
    if min_depth < 0:
        return False
    # Exclude lines with AND_THEN/OR_ELSE at depth 0 (complex boolean chains)
    rhs = code[first_assign_pos + 2:]
    if _RE_BOOL_CHAIN_OP.search(rhs):
        depth = 0
        for m in _RE_BOOL_CHAIN_OP.finditer(rhs):
            d = 0
            for i in range(m.start()):
                if rhs[i] == "(":
                    d += 1
                elif rhs[i] == ")":
                    d -= 1
            if d == 0:
                return False
    return True


def _looks_like_call_start(line: str) -> bool:
    """Heuristic: line ends with '(' and has an identifier or array index before it."""
    stripped = line.rstrip()
    if not stripped.endswith("("):
        idx = stripped.rfind("(")
        if idx < 0:
            return False
    return bool(re.search(r"(?:[A-Za-z_]\w*|\])\s*\($", stripped))


def _opens_param_block(stripped: str) -> bool:
    """True when a line opens a multiline named-parameter block to align."""
    if _is_call_open(stripped):
        return True
    if is_if_wrapped_call_opener(stripped):
        return True
    if _RE_STRUCT_INIT_OPEN.match(stripped):
        return True
    if _RE_STRUCT_PAREN_OPEN.match(stripped):
        return True
    return False


def _is_call_open(stripped: str) -> bool:
    """Determine if a stripped line opens an FB call (not a struct/array initializer).

    FB call:  FbName(
    NOT:      stConfig := (        (struct init)
    NOT:      arrFacade := [(      (array-of-struct init)
    NOT:      varName := FuncCall(  (assignment with call - single line possible)
    NOT:      IF FuncCall(          (control flow with function condition)
    """
    if not stripped:
        return False
    if ");" in stripped:
        return False
    upper = stripped.upper()
    if upper.startswith(("IF ", "ELSIF ", "WHILE ", "UNTIL ")):
        return False
    if ":=" in stripped:
        # := followed by ( or [( is a struct/array initializer, not an FB call
        assign_idx = stripped.rfind(":=")
        after_assign = stripped[assign_idx + 2:].strip()
        if after_assign.startswith("(") or after_assign.startswith("[("):
            return False
        # := followed by Identifier( is an assigned call → still align
        if re.search(r"[A-Za-z_]\w*\s*\($", after_assign):
            return True
        return False
    if stripped.endswith("("):
        return _looks_like_call_start(stripped)
    if "(" in stripped:
        return _looks_like_call_start(stripped)
    return False


def _is_multiline_decl_opener(stripped_line: str) -> bool:
    """True for ``name : TYPE :=`` or ``name : ARRAY[...] OF Type[`` opener lines without a terminating semicolon."""
    code = _RE_INLINE_COMMENT.sub("", stripped_line).rstrip()
    pos_lc = _find_line_comment_pos(code)
    if pos_lc >= 0:
        code = code[:pos_lc].rstrip()
    if not code or code.endswith(";"):
        return False
    if _find_colon_pos(code) < 0:
        return False
    if _find_top_level_assign_pos(code) >= 0:
        return True
    return bool(re.search(r"\bOF\s+[A-Za-z_]\w*\s*\[$", code))


def _is_assign_with_inline_comment(line: str) -> bool:
    """True for implementation-style assignments with a trailing ``(* *)`` comment."""
    if "(**)" in line:
        return False
    if _parse_decl(line) is not None:
        return False
    stripped = line.strip()
    if not (":=" in line and stripped.endswith("*)")):
        return False
    cm = _RE_INLINE_COMMENT.search(line)
    if not cm:
        return False
    return True


def _has_decl_colon(stripped_line: str) -> bool:
    """Check if line contains a declaration colon in the code portion.

    Ignores colons inside comments, strings, :=, ::, and time literals.
    Also requires the line ends with ';' (excludes multiline continuations).
    """
    # Strip inline comment for analysis
    code = _RE_INLINE_COMMENT.sub("", stripped_line).rstrip()
    pos_lc = _find_line_comment_pos(code)
    if pos_lc >= 0:
        code = code[:pos_lc].rstrip()
    # Must end with ';' to be a complete declaration line
    if not code.endswith(";"):
        return False
    return _find_colon_pos(code) >= 0
