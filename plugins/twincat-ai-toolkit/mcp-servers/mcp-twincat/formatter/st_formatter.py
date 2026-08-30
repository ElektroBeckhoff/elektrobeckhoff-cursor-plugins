"""ST Formatter core engine: indentation, spacing, blank lines, keyword casing.

Operates on ST source text line-by-line with context awareness.
Does NOT handle alignment or line wrapping (see st_alignment.py, st_line_wrapper.py).
Supports {formatting.disable}/{formatting.enable} markers (and legacy
{stweep.disable}/{stweep.enable}) to skip formatting for marked regions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from formatter.config import IndentConfig, SpacesConfig
from formatter.constants import (
    INDENT_SIZE_DEFAULT,
    ST_KEYWORDS,
    VAR_BLOCK_KEYWORDS,
)
from formatter.st_string_scan import iter_st_string_spans, sub_st_string_literals


# ---------------------------------------------------------------------------
# Patterns (pre-compiled)
# ---------------------------------------------------------------------------

_RE_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)
_RE_PRAGMA = re.compile(r"\{[^}]*\}")
_RE_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_RE_MULTI_SPACE = re.compile(r"  +")
_RE_SPACE_BEFORE_SEMI = re.compile(r"\s+;")
_RE_ASSIGN_OP = re.compile(r"(?<!\S)(\s*):=(\s*)(?!\S)|(\S):=|:=(\S)")
_RE_ASSIGN_NO_SPACE = re.compile(r"(?<! ):=|:=(?! )")
_RE_OUT_ASSIGN = re.compile(r"\s*=>\s*")
_RE_KEYWORD = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(ST_KEYWORDS, key=len, reverse=True)) + r")\b", re.IGNORECASE)

_RE_TYPED_LITERAL = re.compile(
    r"\b(T|TIME|LT|LTIME|D|DATE|LD|LDATE|TOD|TIME_OF_DAY|LTOD|DT|DATE_AND_TIME|LDT|BOOL|BYTE|WORD|DWORD|LWORD|SINT|INT|DINT|LINT|USINT|UINT|UDINT|ULINT|REAL|LREAL|STRING|WSTRING)#",
    re.IGNORECASE,
)
_RE_TIME_LITERAL = re.compile(
    r"\b(T|TIME|LT|LTIME)#([0-9A-Za-z_.-]+)",
    re.IGNORECASE,
)

# Formatting disable/enable markers (case-insensitive)
# Supports both {formatting.disable} and legacy {stweep.disable}
_RE_DISABLE_PRAGMA = re.compile(r"\{\s*(?:stweep|formatting)\.disable\s*\}", re.IGNORECASE)
_RE_ENABLE_PRAGMA = re.compile(r"\{\s*(?:stweep|formatting)\.enable\s*\}", re.IGNORECASE)
_RE_DISABLE_COMMENT = re.compile(r"\(\*\s*(?:stweep|formatting)\.disable\s*\*\)", re.IGNORECASE)
_RE_ENABLE_COMMENT = re.compile(r"\(\*\s*(?:stweep|formatting)\.enable\s*\*\)", re.IGNORECASE)

_VAR_OPENERS = frozenset({
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT",
    "VAR_GLOBAL", "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG",
})

_INDENT_AFTER = frozenset({
    "THEN", "DO", "ELSE", "STRUCT", "UNION", "__TRY", "__FINALLY",
})

_DEINDENT_BEFORE = frozenset({
    "END_IF", "END_FOR", "END_WHILE", "END_REPEAT", "END_CASE",
    "END_STRUCT", "END_TYPE", "END_UNION",
    "END_VAR",
    "END_METHOD", "END_ACTION", "END_PROPERTY",
    "END_PROGRAM", "END_FUNCTION_BLOCK", "END_FUNCTION",
    "ELSIF", "ELSE", "UNTIL",
    "__ENDTRY", "__CATCH", "__FINALLY",
})

_INDENT_AND_DEINDENT = frozenset({
    "ELSIF", "ELSE", "UNTIL",
    "__CATCH", "__FINALLY",
})

_CONTROL_FLOW_WITH_BODY = frozenset({
    "IF", "FOR", "WHILE", "REPEAT", "CASE", "__TRY",
})

_CONTROL_FLOW_ENDERS = frozenset({
    "END_IF", "END_FOR", "END_WHILE", "END_REPEAT", "END_CASE", "__ENDTRY",
})


_RE_ASSIGN_LACK_LEFT = re.compile(r"(\S):=")
_RE_ASSIGN_LACK_RIGHT = re.compile(r":=(\S)")
_RE_ASSIGN_NO_SPACE_PUNC = re.compile(r":= ([,;)])")

_RE_COMP_EQ_GT = re.compile(r"=\s+>")
_RE_COMP_LT_GT = re.compile(r"<\s+>")
_RE_COMP_LT_EQ = re.compile(r"<\s+=")
_RE_COMP_GT_EQ = re.compile(r">\s+=")
_RE_COMP_NE_COLLAPSE_LEFT = re.compile(r"(\S)\s{2,}<>(?=\s|\)|;|$)")
_RE_COMP_NE_COLLAPSE_RIGHT = re.compile(r"<>(\s{2,})")
_RE_COMP_EQ_COLLAPSE_LEFT = re.compile(r"(\S)\s{2,}=(?!=)(?=\s|\)|;|$|\S)")
_RE_COMP_EQ_COLLAPSE_RIGHT = re.compile(r"(?<![:<]=)=(?!=)(\s{2,})")

_RE_SEMI_SPACE = re.compile(r"\s+;")
_RE_REF_ARROW_REPAIR = re.compile(r"(?<![:<])=\s+>")

_RE_WORD_OP_COLLAPSE_LEFT = re.compile(r"(\S)\s{2,}\b(MOD|AND|OR|XOR|AND_THEN|OR_ELSE)\b", re.IGNORECASE)
_RE_WORD_OP_COLLAPSE_RIGHT = re.compile(r"\b(MOD|AND|OR|XOR|AND_THEN|OR_ELSE|NOT)\s{2,}(?=\S)", re.IGNORECASE)
_RE_ARITH_COLLAPSE_LEFT = re.compile(r"(\S)\s{2,}(\+|\-|\*|/|\*\*)(?=\s|\S)")
_RE_ARITH_COLLAPSE_RIGHT = re.compile(r"(\+|\-|\*|/|\*\*)\s{2,}(?=\S)")
_RE_COMMA_SPACE_BEFORE = re.compile(r"\s+,(?=\s|\S|$)")
_RE_COMMA_SPACE_AFTER = re.compile(r",\s{2,}(?=\S)")
_RE_PAREN_OPEN_COLLAPSE = re.compile(r"\(\s{2,}(?=\S)")
_RE_PAREN_CLOSE_COLLAPSE = re.compile(r"(?<=\S)\s{2,}\)")
_RE_BRACKET_OPEN_COLLAPSE = re.compile(r"\[\s{2,}(?=\S)")
_RE_BRACKET_CLOSE_COLLAPSE = re.compile(r"(?<=\S)\s{2,}\]")
_RE_CARET_SPACE = re.compile(r"\s+\^")
_RE_DOT_MEMBER = re.compile(r"(?<=[A-Za-z0-9_\^\]\)])\s*\.\s*(?=[A-Za-z_])")


@dataclass(slots=True)
class _MaskEntry:
    """Represents a masked region in source (comment/string/pragma)."""
    start: int
    end: int
    placeholder: str
    original: str


@dataclass(slots=True)
class DisableRegion:
    """A region of code where formatting is disabled."""
    start_line: int
    end_line: int  # -1 means until end of source


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def split_disable_regions(source: str) -> list[tuple[str, bool]]:
    """Split source into (text, should_format) segments based on disable markers.

    Recognizes:
      {formatting.disable} / {formatting.enable}    (pragma form)
      (*formatting.disable*) / (*formatting.enable*)  (comment form)
      {stweep.disable} / {stweep.enable}            (legacy compat)
      (*formatting.disable*) / (*formatting.enable*) (generic comment)

    All markers are case-insensitive. Forms can be intermixed.
    Disabled regions preserve original content verbatim.
    """
    lines = source.split("\n")
    segments: list[tuple[str, bool]] = []
    current_lines: list[str] = []
    formatting_enabled = True

    for line in lines:
        stripped = line.strip()

        if formatting_enabled:
            if _RE_DISABLE_PRAGMA.fullmatch(stripped) or _RE_DISABLE_COMMENT.fullmatch(stripped):
                if current_lines:
                    segments.append(("\n".join(current_lines), True))
                    current_lines = []
                current_lines.append(line.rstrip())
                formatting_enabled = False
                continue
        else:
            if _RE_ENABLE_PRAGMA.fullmatch(stripped) or _RE_ENABLE_COMMENT.fullmatch(stripped):
                current_lines.append(line.rstrip())
                segments.append(("\n".join(current_lines), False))
                current_lines = []
                formatting_enabled = True
                continue

        current_lines.append(line)

    if current_lines:
        segments.append(("\n".join(current_lines), formatting_enabled))

    return segments


def format_st_code(
    source: str,
    *,
    indent_size: int = INDENT_SIZE_DEFAULT,
    indent_config: IndentConfig | None = None,
    uppercase_keywords: bool = True,
    reindent: bool = True,
    force_reindent: bool = False,
    max_consecutive_blanks: int = 1,
    normalize_spaces: bool = False,
    spaces: SpacesConfig | None = None,
) -> str:
    """Format Structured Text code (core pass).

    Applies:
    - Tab-to-space conversion (always)
    - Multi-space normalization (only if normalize_spaces=True)
    - Comparison/comma/semicolon spacing (when *spaces* config provided)
    - Keyword uppercasing
    - Trailing whitespace removal
    - Blank line clamping (max_consecutive_blanks)

    When reindent=True, also recomputes indentation (experimental).
    Does NOT apply alignment or line wrapping.
    """
    if spaces is None:
        spaces = SpacesConfig()

    if not source.strip():
        return source

    source = _normalize_line_endings(source)
    tabs_predominant = _uses_tabs_predominantly(source)
    if not tabs_predominant:
        source = _convert_tabs_to_spaces(source, indent_size)
    if normalize_spaces:
        source = _normalize_inline_spaces(source)

    source = _normalize_code_tokens(
        source,
        uppercase_keywords=uppercase_keywords,
        normalize_comparisons=bool(spaces.around_comparison_operator or spaces.around_equality_operator),
        normalize_semicolons=bool(not spaces.before_semicolon),
    )

    lines = source.split("\n")
    if reindent:
        from formatter.st_indent_anchor import apply_column_anchor_indentation

        icfg = indent_config or IndentConfig(size=indent_size)
        if icfg.size != indent_size:
            icfg = replace(icfg, size=indent_size)
        lines, _stack = apply_column_anchor_indentation(
            lines, icfg,
            force_all=icfg.reindent and not tabs_predominant,
        )
    lines = _normalize_blank_lines(lines, max_consecutive=max_consecutive_blanks)
    lines = _strip_trailing(lines)

    result = "\n".join(lines)

    if source.endswith("\n") and not result.endswith("\n"):
        result += "\n"

    return result


# ---------------------------------------------------------------------------
# Operator spacing and token normalization
# ---------------------------------------------------------------------------


def _normalize_code_tokens(
    source: str,
    *,
    uppercase_keywords: bool = True,
    normalize_comparisons: bool = True,
    normalize_semicolons: bool = True,
) -> str:
    """Unified single-pass code token normalization (keywords, assigns, comparisons, semicolons)."""
    masks, masked = _mask_non_code(source)
    if uppercase_keywords:
        masked = _RE_KEYWORD.sub(lambda m: m.group(0).upper(), masked)
        masked = _RE_TYPED_LITERAL.sub(lambda m: m.group(1).upper() + "#", masked)
        masked = _RE_TIME_LITERAL.sub(lambda m: m.group(1).upper() + "#" + m.group(2).upper(), masked)

    lines = masked.split("\n")
    result_lines = []
    for line in lines:
        if ":=" in line:
            line = _RE_ASSIGN_LACK_LEFT.sub(r"\1 :=", line)
            line = _RE_ASSIGN_LACK_RIGHT.sub(r":= \1", line)
            line = _RE_ASSIGN_NO_SPACE_PUNC.sub(r":=\1", line)

        if normalize_comparisons:
            if "=" in line or "<" in line or ">" in line:
                line = _RE_COMP_EQ_GT.sub("=>", line)
                line = _RE_COMP_LT_GT.sub("<>", line)
                line = _RE_COMP_LT_EQ.sub("<=", line)
                line = _RE_COMP_GT_EQ.sub(">=", line)
                line = _RE_COMP_NE_COLLAPSE_LEFT.sub(r"\1 <>", line)
                line = _RE_COMP_NE_COLLAPSE_RIGHT.sub("<> ", line)
                line = _RE_COMP_EQ_COLLAPSE_LEFT.sub(r"\1 =", line)
                line = _RE_COMP_EQ_COLLAPSE_RIGHT.sub("= ", line)

            line = _RE_WORD_OP_COLLAPSE_LEFT.sub(r"\1 \2", line)
            line = _RE_WORD_OP_COLLAPSE_RIGHT.sub(r"\1 ", line)
            line = _RE_ARITH_COLLAPSE_LEFT.sub(r"\1 \2", line)
            line = _RE_ARITH_COLLAPSE_RIGHT.sub(r"\1 ", line)
            line = _RE_COMMA_SPACE_BEFORE.sub(",", line)
            line = _RE_COMMA_SPACE_AFTER.sub(", ", line)
            line = _RE_PAREN_OPEN_COLLAPSE.sub("(", line)
            line = _RE_PAREN_CLOSE_COLLAPSE.sub(r")", line)
            line = _RE_BRACKET_OPEN_COLLAPSE.sub("[", line)
            line = _RE_BRACKET_CLOSE_COLLAPSE.sub(r"]", line)
            line = _RE_CARET_SPACE.sub("^", line)
            line = _RE_DOT_MEMBER.sub(".", line)

        if normalize_semicolons and ";" in line:
            indent_len = len(line) - len(line.lstrip(" "))
            indent = line[:indent_len]
            content = line[indent_len:]
            content = _RE_SEMI_SPACE.sub(";", content)
            line = indent + content

        result_lines.append(line)

    combined = "\n".join(result_lines)
    if "=" in combined:
        combined = _RE_REF_ARROW_REPAIR.sub("=>", combined)

    return _unmask(combined, masks)


def _normalize_assign_spacing(source: str) -> str:
    """Normalize spacing around ':=' to at least ' := '."""
    return _normalize_code_tokens(
        source,
        uppercase_keywords=False,
        normalize_comparisons=False,
        normalize_semicolons=False,
    )


def _normalize_comparison_spacing(source: str) -> str:
    """Collapse excess whitespace around ``=``, ``<>``, ``<=``, ``>=`` (not ``:=`` / ``=>``)."""
    masks, masked = _mask_non_code(source)
    lines = masked.split("\n")
    result_lines: list[str] = []

    for line in lines:
        if "=" in line or "<" in line or ">" in line:
            line = _RE_COMP_EQ_GT.sub("=>", line)
            line = _RE_COMP_LT_GT.sub("<>", line)
            line = _RE_COMP_LT_EQ.sub("<=", line)
            line = _RE_COMP_GT_EQ.sub(">=", line)
            line = _RE_COMP_NE_COLLAPSE_LEFT.sub(r"\1 <>", line)
            line = _RE_COMP_NE_COLLAPSE_RIGHT.sub("<> ", line)
            line = _RE_COMP_EQ_COLLAPSE_LEFT.sub(r"\1 =", line)
            line = _RE_COMP_EQ_COLLAPSE_RIGHT.sub("= ", line)
        result_lines.append(line)

    return _unmask("\n".join(result_lines), masks)


def _normalize_semicolon_spacing(source: str) -> str:
    """Remove space immediately before semicolons in code (not leading indent)."""
    masks, masked = _mask_non_code(source)
    lines = masked.split("\n")
    result_lines: list[str] = []
    for line in lines:
        if ";" in line:
            indent_len = len(line) - len(line.lstrip(" "))
            indent = line[:indent_len]
            content = line[indent_len:]
            content = _RE_SEMI_SPACE.sub(";", content)
            line = indent + content
        result_lines.append(line)
    return _unmask("\n".join(result_lines), masks)


def _repair_ref_arrow_spacing(source: str) -> str:
    """Repair ``= >`` broken REF/output arrows back to ``=>``."""
    if "=" not in source:
        return source
    masks, masked = _mask_non_code(source)
    repaired = _RE_REF_ARROW_REPAIR.sub("=>", masked)
    return _unmask(repaired, masks)


# ---------------------------------------------------------------------------
# Keyword Casing
# ---------------------------------------------------------------------------


def _uppercase_keywords(source: str) -> str:
    """Uppercase all ST keywords, preserving strings/comments/pragmas."""
    masks, masked_source = _mask_non_code(source)
    masked_source = _RE_KEYWORD.sub(lambda m: m.group(0).upper(), masked_source)
    return _unmask(masked_source, masks)


# ---------------------------------------------------------------------------
# Masking (protect comments, strings, pragmas from modification)
# ---------------------------------------------------------------------------


def _mask_non_code(source: str) -> tuple[list[_MaskEntry], str]:
    """Replace comments, strings, and pragmas with placeholders."""
    if "(*" not in source and "//" not in source and "'" not in source and '"' not in source and "{" not in source:
        return [], source

    from formatter.constants import TokenType
    from formatter.st_lexer import tokenize

    masks: list[_MaskEntry] = []
    out_chunks = []
    counter = 0

    for tok in tokenize(source):
        if tok.type in (TokenType.COMMENT_BLOCK, TokenType.COMMENT_LINE, TokenType.STRING, TokenType.PRAGMA):
            prefix = {
                TokenType.COMMENT_BLOCK: "BC",
                TokenType.COMMENT_LINE: "LC",
                TokenType.STRING: "SL",
                TokenType.PRAGMA: "PG",
            }[tok.type]
            placeholder = f"\x00{prefix}{counter}\x00"
            masks.append(_MaskEntry(
                start=0,
                end=len(tok.value),
                placeholder=placeholder,
                original=tok.value,
            ))
            counter += 1
            out_chunks.append(placeholder)
        elif tok.type != TokenType.EOF:
            out_chunks.append(tok.value)

    return masks, "".join(out_chunks)


def _unmask(source: str, masks: list[_MaskEntry]) -> str:
    """Restore original content from placeholders."""
    if not masks:
        return source
    for entry in reversed(masks):
        source = source.replace(entry.placeholder, entry.original)
    return source


# ---------------------------------------------------------------------------
# Indentation
# ---------------------------------------------------------------------------


def _apply_indentation(lines: list[str], indent_size: int) -> list[str]:
    """Recompute indentation based on ST block structure."""
    result: list[str] = []
    level = 0
    in_var_block = False
    in_type_block = False
    in_case_block = False
    case_level = 0
    in_block_comment = False

    for raw_line in lines:
        stripped = raw_line.strip()

        if not stripped:
            result.append("")
            continue

        if in_block_comment:
            result.append(raw_line)
            if "*)" in stripped:
                in_block_comment = False
            continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            indent = " " * (level * indent_size)
            result.append(indent + stripped)
            continue

        code_part = _strip_comments_and_strings_for_analysis(stripped)
        first_token = _get_first_keyword(code_part)

        deindent_this = False
        indent_next = False

        if first_token in _DEINDENT_BEFORE:
            deindent_this = True
            if first_token in _INDENT_AND_DEINDENT:
                indent_next = True

        if first_token == "END_VAR":
            in_var_block = False
            deindent_this = True

        if first_token == "END_TYPE":
            in_type_block = False
            deindent_this = True

        if first_token == "END_CASE":
            in_case_block = False
            level = case_level
            deindent_this = False

        if deindent_this and level > 0:
            level -= 1

        if in_type_block and stripped.startswith(")") and level > 0:
            level -= 1

        indent = " " * (level * indent_size)
        result.append(indent + stripped)

        if indent_next:
            level += 1
            continue

        if first_token in _VAR_OPENERS:
            in_var_block = True
            level += 1
            continue

        if first_token == "TYPE":
            in_type_block = True
            level += 1
            if stripped.rstrip().endswith("("):
                level += 1
            continue

        if first_token == "CASE":
            in_case_block = True
            case_level = level
            level += 1
            continue

        if _line_ends_with_keyword(code_part, "THEN"):
            level += 1
            continue

        if _line_ends_with_keyword(code_part, "DO"):
            level += 1
            continue

        if first_token == "REPEAT":
            level += 1
            continue

        if first_token in ("STRUCT", "UNION"):
            level += 1
            continue

        if in_case_block and _is_case_label(code_part):
            pass

    return result


def _case_block_depth(lines: list[str], line_index: int) -> int:
    """Return nesting depth of active CASE blocks before *line_index*."""
    depth = 0
    for i in range(line_index + 1):
        upper = _strip_comments_and_strings_for_analysis(lines[i]).upper()
        if upper.startswith("CASE "):
            depth += 1
        elif upper == "END_CASE":
            depth = max(0, depth - 1)
    return depth


def fix_end_if_indent_safe(
    lines: list[str],
    indent_size: int,
    *,
    rebuilt: list[bool] | None = None,
) -> list[str]:
    """Fix END_IF indent only when safe.

    Rules (never under-dedent relative to raw):
    1. Rebuilt END_IF lines (from join/wrap passes): use structural indent.
    2. Outside CASE: over-indented END_IF (raw col > expected col) → dedent.

    Leaves under-indented and in-CASE END_IF unchanged.
    """
    if not lines:
        return lines

    expected_lines = _apply_indentation(lines, indent_size)
    if len(expected_lines) != len(lines):
        return lines

    if rebuilt is not None and len(rebuilt) != len(lines):
        rebuilt = None

    result = list(lines)
    for idx, (original, expected) in enumerate(zip(lines, expected_lines)):
        if original.strip().upper() != "END_IF":
            continue

        orig_col = len(original) - len(original.lstrip())
        exp_col = len(expected) - len(expected.lstrip())
        if orig_col == exp_col:
            continue

        if rebuilt is not None and rebuilt[idx]:
            result[idx] = expected
            continue

        if orig_col > exp_col and _case_block_depth(lines, idx) == 0:
            result[idx] = expected

    return result


def _get_first_keyword(code: str) -> str:
    """Extract the first keyword-like token from a code line."""
    code = code.lstrip()
    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", code)
    if match:
        word = match.group(0).upper()
        if word in ST_KEYWORDS:
            return word
    return ""


def _line_ends_with_keyword(code: str, keyword: str) -> bool:
    """Check if line ends with a specific keyword (ignoring trailing comments)."""
    code = code.rstrip()
    return bool(re.search(r"\b" + keyword + r"\s*$", code, re.IGNORECASE))


def _is_case_label(code: str) -> bool:
    """Check if line is a CASE label (e.g. '0:', 'E_State.Init:')."""
    code = code.strip()
    stripped_comment = _RE_LINE_COMMENT.sub("", code)
    stripped_comment = _RE_BLOCK_COMMENT.sub("", stripped_comment).strip()
    if stripped_comment.endswith(":") and ":=" not in stripped_comment:
        return True
    return False


def _strip_comments_and_strings_for_analysis(line: str) -> str:
    """Remove comments and strings for structural analysis only."""
    result = _RE_BLOCK_COMMENT.sub("", line)
    result = _RE_LINE_COMMENT.sub("", result)
    result = sub_st_string_literals(result, lambda _lit: "''")
    return result.strip()


# ---------------------------------------------------------------------------
# Blank Lines
# ---------------------------------------------------------------------------


def _normalize_blank_lines(lines: list[str], *, max_consecutive: int = 1) -> list[str]:
    """Clamp consecutive blank lines to max_consecutive.

    Preserves all lines inside block comments.
    """
    result: list[str] = []
    blank_count = 0
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if in_block_comment:
            result.append(line)
            if "*)" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            blank_count = 0
            result.append(line)
            continue
        if not stripped:
            blank_count += 1
            if blank_count <= max_consecutive:
                result.append("")
        else:
            blank_count = 0
            result.append(line)

    while result and not result[-1].strip():
        result.pop()
    while result and not result[0].strip():
        result.pop(0)

    return result


# ---------------------------------------------------------------------------
# Whitespace
# ---------------------------------------------------------------------------


def _uses_tabs_predominantly(source: str) -> bool:
    """Check if source uses tabs for indentation on most indented lines.

    Returns True if >50% of non-empty lines start with a tab.
    Tabs are preserved in such code blocks to avoid breaking indentation.
    """
    lines = source.split("\n")
    indented = [l for l in lines if l and l[0] in (" ", "\t")]
    if len(indented) < 3:
        return False
    tab_lines = sum(1 for l in indented if l[0] == "\t")
    return tab_lines / len(indented) > 0.5


def _strip_trailing(lines: list[str]) -> list[str]:
    """Remove trailing whitespace from all lines.

    Preserves trailing whitespace inside block comments.
    """
    result: list[str] = []
    in_block_comment = False
    for line in lines:
        stripped = line.strip()
        if in_block_comment:
            result.append(line)
            if "*)" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            result.append(line)
            continue
        result.append(line.rstrip())
    return result


def _normalize_line_endings(source: str) -> str:
    """Normalize to LF."""
    return source.replace("\r\n", "\n").replace("\r", "\n")


def _convert_tabs_to_spaces(source: str, tab_size: int = 4) -> str:
    """Convert tabs to spaces using tab-stop positions.

    Preserves tabs inside block comments (* ... *).
    Expands each tab to the number of spaces needed to reach the next
    tab-stop column (multiples of tab_size).
    """
    lines = source.split("\n")
    result = []
    in_block_comment = False
    for line in lines:
        if "\t" not in line:
            if not in_block_comment and "(*" in line and "*)" not in line:
                in_block_comment = True
            elif in_block_comment and "*)" in line:
                in_block_comment = False
            result.append(line)
            continue

        if in_block_comment:
            # Preserve tabs inside block comments
            if "*)" in line:
                in_block_comment = False
            result.append(line)
            continue

        # Check if this line starts/contains a block comment
        if "(*" in line and "*)" not in line:
            in_block_comment = True

        expanded = ""
        col = 0
        inside_comment = False
        i = 0
        chars = line
        while i < len(chars):
            if not inside_comment and chars[i:i+2] == "(*":
                inside_comment = True
                expanded += "(*"
                col += 2
                i += 2
                continue
            if inside_comment and chars[i:i+2] == "*)":
                inside_comment = False
                expanded += "*)"
                col += 2
                i += 2
                continue
            if chars[i] == "\t" and not inside_comment:
                spaces = tab_size - (col % tab_size)
                expanded += " " * spaces
                col += spaces
            else:
                expanded += chars[i]
                col += 1
            i += 1
        result.append(expanded)
    return "\n".join(result)


_RE_MULTI_SPACE = re.compile(r" {2,}")


def _normalize_inline_spaces(source: str) -> str:
    """Collapse multiple consecutive spaces to one within code.

    Preserves: leading indentation, content inside strings and block
    comments, space before inline comments (// ...).
    """
    lines = source.split("\n")
    result = []
    in_block_comment = False

    for line in lines:
        if in_block_comment:
            if "*)" in line:
                in_block_comment = False
            result.append(line)
            continue

        if "(*" in line and "*)" not in line:
            in_block_comment = True
            result.append(line)
            continue

        if not _RE_MULTI_SPACE.search(line):
            result.append(line)
            continue

        indent_len = len(line) - len(line.lstrip(" "))
        indent = line[:indent_len]
        content = line[indent_len:]

        normalized = _collapse_spaces_safe(content)
        result.append(indent + normalized)

    return "\n".join(result)


def _collapse_spaces_safe(content: str) -> str:
    """Collapse multi-spaces in a single line, protecting strings/comments."""
    spans = list(iter_st_string_spans(content))
    if not spans:
        return _collapse_spaces_in_plain(content)

    parts: list[str] = []
    last = 0
    for start, end in spans:
        parts.append(_collapse_spaces_in_plain(content[last:start]))
        parts.append(content[start:end])
        last = end
    parts.append(_collapse_spaces_in_plain(content[last:]))
    return "".join(parts)


def _collapse_spaces_in_plain(content: str) -> str:
    """Collapse multi-spaces outside string literals (comments preserved)."""
    out = []
    i = 0
    n = len(content)

    while i < n:
        ch = content[i]

        if ch == "(" and i + 1 < n and content[i + 1] == "*":
            end = content.find("*)", i + 2)
            if end != -1:
                out.append(content[i:end + 2])
                i = end + 2
            else:
                out.append(content[i:])
                break
            continue

        if ch == "/" and i + 1 < n and content[i + 1] == "/":
            out.append(content[i:])
            break

        if ch == " ":
            # Preserve multi-space padding before ':=' (alignment padding)
            j = i + 1
            while j < n and content[j] == " ":
                j += 1
            if j < n - 1 and content[j] == ":" and content[j + 1] == "=":
                out.append(content[i:j])
                i = j
            else:
                out.append(" ")
                i = j
            continue

        out.append(ch)
        i += 1

    return "".join(out)
