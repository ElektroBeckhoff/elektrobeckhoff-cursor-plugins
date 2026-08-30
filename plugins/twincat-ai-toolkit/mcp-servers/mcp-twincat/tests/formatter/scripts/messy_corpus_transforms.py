"""Messy transforms for formatter round-trip testing (Option B).

Permanent raw corpus (``fixtures/raw/``) stays unformatted messy while
``format(raw) == golden`` for every paired file under ``fixtures/golden/``.

Transforms (formatter byte-restores all):
- keyword casing, trailing whitespace, CASE label merge
- VAR type-colon de-align (no init lines)
- ``:=`` / type-colon de-align in implementation, FB/IF calls, struct inits
- enum member ``:=`` de-align (decimal, ``2#``, ``16#`` literals and expression RHS)
- METHOD/TYPE header colon spacing (semicolon-comment gaps disabled — collides with column alignment)
- indent drift in implementation (reindent restores)
- comparison ``=`` / ``<>`` excess spacing (core pass collapses; enum/decl skipped)
- **structural** statement join (adjacent ``;``-terminated assignments → one line)
- **structural** inline-THEN (standalone ``THEN`` merged back onto preceding IF/ELSIF)
- **structural** call collapse (multiline ``Fb(`` joined back to single line)

Still skipped (would break syntax, alignment, or XML): ``{attribute}`` pragma *content*;
comma spacing in enum comment columns; extra blank lines (enum group separators).
"""
from __future__ import annotations

import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parents[3]
if str(_MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(_MCP_ROOT))

from formatter.st_string_scan import sub_st_string_literals

RE_CDATA_CONTENT = re.compile(r"(<!\[CDATA\[)(.*?)(\]\]>)", re.DOTALL)
RE_DISABLE_REGION = re.compile(
    r"(\{(?:stweep|formatting)\.disable\}|\(\*(?:stweep|formatting)\.disable\*\))"
    r"(.*?)"
    r"(\{(?:stweep|formatting)\.enable\}|\(\*(?:stweep|formatting)\.enable\*\))",
    re.IGNORECASE | re.DOTALL,
)
RE_CASE_LABEL_ONLY = re.compile(r"^(\s+)(\d+):\s*$")
RE_ENUM_MEMBER = re.compile(
    r"^\s*(?:\{[^{}]*\}\s*)?\w+\s*:=\s*(?:\d+|2#[01_]+|16#[0-9A-Fa-f_]+)",
    re.IGNORECASE,
)
RE_ENUM_EXPR_MEMBER = re.compile(
    r"^\s*(?:\{[^{}]*\}\s*)?\w+\s*:=\s*.+\+",
    re.IGNORECASE,
)
RE_PURE_PRAGMA = re.compile(r"^\s*\{[^}]*\}\s*$")
RE_TYPE_COLON = re.compile(r"(\S)(\s+)(:)(?!=)")
RE_TYPE_HEADER = re.compile(r"^\s*TYPE\s+\w+\s*:", re.IGNORECASE)
RE_METHOD_HEADER = re.compile(r"^\s*(?:METHOD|PROPERTY)\b", re.IGNORECASE)
RE_STRUCT_INIT_OPEN = re.compile(r"^\s*\(\s*[A-Za-z_]\w*\s*:=", re.IGNORECASE)
RE_PRAGMA = re.compile(r"\{[^{}]*\}")
RE_SEMICOLON_COMMENT = re.compile(r"(;\s*)(\(\*)")
RE_COMPARISON_OPS = re.compile(r"(<>|<=|>=|(?<![:<>=!])=(?!=))")
RE_END_KEYWORD = re.compile(
    r"^\s*(?:END_\w+|ELSE|ELSIF)\b",
    re.IGNORECASE,
)
RE_MULTI_VAR_DECL = re.compile(
    r"^(\s*)(?:\{[^{}]*\}\s*)?([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)+)\s*:",
    re.IGNORECASE,
)
_RE_DISABLE_PRAGMA = re.compile(r"\{\s*(?:stweep|formatting)\.disable\s*\}", re.IGNORECASE)
_RE_ENABLE_PRAGMA = re.compile(r"\{\s*(?:stweep|formatting)\.enable\s*\}", re.IGNORECASE)
_RE_DISABLE_COMMENT = re.compile(r"\(\*\s*(?:stweep|formatting)\.disable\s*\*\)", re.IGNORECASE)
_RE_ENABLE_COMMENT = re.compile(r"\(\*\s*(?:stweep|formatting)\.enable\s*\*\)", re.IGNORECASE)

KEYWORDS = [
    "IF", "THEN", "ELSE", "ELSIF", "END_IF",
    "FOR", "TO", "BY", "DO", "END_FOR",
    "WHILE", "END_WHILE", "REPEAT", "UNTIL", "END_REPEAT",
    "CASE", "OF", "END_CASE",
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_GLOBAL",
    "VAR_STAT", "END_VAR", "CONSTANT", "PERSISTENT", "RETAIN",
    "FUNCTION_BLOCK", "FUNCTION", "PROGRAM", "METHOD", "PROPERTY",
    "END_FUNCTION_BLOCK", "END_FUNCTION", "END_PROGRAM", "END_METHOD", "END_PROPERTY",
    "STRUCT", "END_STRUCT", "TYPE", "END_TYPE",
    "RETURN", "EXIT", "CONTINUE",
    "TRUE", "FALSE",
    "AND", "OR", "NOT", "XOR", "MOD",
    "AND_THEN", "OR_ELSE",
    "BOOL", "INT", "UINT", "DINT", "UDINT", "SINT", "USINT",
    "LINT", "ULINT", "REAL", "LREAL", "STRING", "BYTE", "WORD", "DWORD", "LWORD",
    "ARRAY", "POINTER", "REFERENCE",
    "IMPLEMENTS", "EXTENDS", "ABSTRACT",
]
RE_KEYWORD = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(KEYWORDS, key=len, reverse=True)) + r")\b"
)

EXTENSIONS = (".TcPOU", ".TcDUT", ".TcGVL", ".TcIO")


RE_LONE_THEN = re.compile(r"^\s*THEN\s*$", re.IGNORECASE)
RE_IF_ELSIF_LINE = re.compile(
    r"^\s*(?:IF|ELSIF)\b",
    re.IGNORECASE,
)
RE_SIMPLE_STMT = re.compile(
    r"^\s*\w[\w.^]*\s*:=\s*.+;\s*$",
)
RE_FB_CALL_OPEN = re.compile(r"^(\s*)([\w.^]+)\(\s*$")
RE_CONTROL_KW_LINE = re.compile(
    r"^\s*(?:IF|FOR|WHILE|CASE|REPEAT|END_|ELSE|ELSIF|RETURN|EXIT|CONTINUE)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MessyProfile:
    """Tunable messy-transform aggressiveness (defaults: aggressive post-985/985)."""

    keyword_lower_prob: float = 0.95
    operator_mess_threshold_impl: float = 0.30
    operator_mess_threshold_var: float = 0.45
    case_merge_prob: float = 0.95
    trailing_ws_prob: float = 0.65
    semicolon_comment_gap_prob: float = 0.0
    indent_mess_prob: float = 0.40
    comparison_mess_prob: float = 0.35
    multi_var_decl_mess_prob: float = 0.55
    mess_enum_members: bool = True
    mess_struct_init_openers: bool = True
    mess_method_headers: bool = True
    mess_type_headers: bool = True
    mess_complex_rhs: bool = True
    # Structural transforms (Phase 5 canonical formatter)
    statement_join_prob: float = 0.0
    inline_then_prob: float = 0.60
    call_collapse_prob: float = 0.35


DEFAULT_MESSY_PROFILE = MessyProfile()


def mess_file_text(
    text: str,
    *,
    seed: int = 42,
    file_seed: int = 0,
    profile: MessyProfile | None = None,
) -> str:
    rng = random.Random((seed ^ file_seed) & 0xFFFFFFFF)
    profile = profile or DEFAULT_MESSY_PROFILE

    def replace_cdata(match: re.Match[str]) -> str:
        prefix, content, suffix = match.group(1), match.group(2), match.group(3)
        if not content.strip():
            return match.group(0)
        return prefix + _mess_cdata(content, rng, profile) + suffix

    return RE_CDATA_CONTENT.sub(replace_cdata, text)


def mess_directory_in_place(
    target_dir: Path,
    *,
    seed: int = 42,
    profile: MessyProfile | None = None,
) -> int:
    count = 0
    profile = profile or DEFAULT_MESSY_PROFILE
    for src in sorted(target_dir.rglob("*")):
        if src.suffix not in EXTENSIONS:
            continue
        raw = src.read_bytes()
        had_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig").replace("\r\n", "\n")
        file_seed = hash(src.as_posix()) & 0xFFFFFFFF
        messed = mess_file_text(text, seed=seed, file_seed=file_seed, profile=profile)
        messed = messed.replace("\n", "\r\n")
        payload = messed.encode("utf-8")
        if had_bom:
            payload = b"\xef\xbb\xbf" + payload
        src.write_bytes(payload)
        count += 1
    return count


def _mess_cdata(content: str, rng: random.Random, profile: MessyProfile) -> str:
    parts: list[tuple[str, str]] = []
    last_end = 0
    for match in RE_DISABLE_REGION.finditer(content):
        if match.start() > last_end:
            parts.append(("format", content[last_end:match.start()]))
        parts.append(("skip", match.group()))
        last_end = match.end()
    if last_end < len(content):
        remaining = content[last_end:]
        disable_start = re.search(
            r"\{(?:stweep|formatting)\.disable\}|\(\*(?:stweep|formatting)\.disable\*\)",
            remaining,
            re.IGNORECASE,
        )
        if disable_start:
            parts.append(("format", remaining[: disable_start.start()]))
            parts.append(("skip", remaining[disable_start.start() :]))
        else:
            parts.append(("format", remaining))

    result_parts: list[str] = []
    for kind, text in parts:
        if kind == "skip":
            result_parts.append(text)
        else:
            result_parts.append(_mess_formattable_cdata(text, rng, profile))
    return "".join(result_parts)


def _mess_formattable_cdata(content: str, rng: random.Random, profile: MessyProfile) -> str:
    lines = content.split("\n")
    out: list[str] = []
    in_block_comment = False
    in_decl = True
    in_var_block = False
    enum_paren_depth = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        upper = stripped.upper()

        if in_block_comment:
            out.append(line)
            if "*)" in stripped:
                in_block_comment = False
            i += 1
            continue

        if stripped.startswith("(*") and "*)" not in stripped:
            in_block_comment = True
            out.append(line)
            i += 1
            continue

        if not stripped:
            out.append(line)
            i += 1
            continue

        if upper.startswith("TYPE ") and "(" in stripped:
            enum_paren_depth += stripped.count("(") - stripped.count(")")
        elif enum_paren_depth > 0:
            enum_paren_depth += stripped.count("(") - stripped.count(")")
            if enum_paren_depth <= 0:
                enum_paren_depth = 0

        if upper.startswith(("VAR", "VAR_")):
            in_var_block = True
            in_decl = True
        elif upper.startswith(("TYPE ", "STRUCT ")):
            in_decl = True
        if upper == "END_VAR" and enum_paren_depth == 0:
            in_var_block = False
            in_decl = False
        elif upper in ("END_TYPE", "END_STRUCT") and enum_paren_depth == 0:
            in_decl = False

        merged = _try_merge_case_label(lines, i, rng, in_decl=in_decl, profile=profile)
        if merged is not None:
            line, skip = merged
            i += skip
        else:
            i += 1

        in_enum_body = enum_paren_depth > 0
        skip_spacing = (
            (RE_TYPE_HEADER.match(line) is not None and not profile.mess_type_headers)
            or (RE_METHOD_HEADER.match(line) is not None and not profile.mess_method_headers)
            or (
                RE_STRUCT_INIT_OPEN.match(line) is not None
                and not profile.mess_struct_init_openers
            )
            or RE_PURE_PRAGMA.match(line) is not None
            or (in_decl and not in_var_block and not in_enum_body)
        )

        line = _randomize_keyword_case(line, rng, profile)
        line = _mess_multi_var_decl(line, rng, in_var_block=in_var_block, profile=profile)
        line = _mess_indent(line, rng, in_decl=in_decl, profile=profile)
        line = _mess_operator_spacing(
            line,
            rng,
            in_var_block=in_var_block,
            in_enum_body=in_enum_body,
            skip_spacing=skip_spacing,
            profile=profile,
        )
        line = _mess_comparison_spacing(
            line, rng, in_decl=in_decl, in_enum_body=in_enum_body, profile=profile
        )
        line = _mess_semicolon_comment_gap(line, rng, profile)
        if rng.random() < profile.trailing_ws_prob and not (
            RE_ENUM_MEMBER.match(line) or RE_ENUM_EXPR_MEMBER.match(line)
        ):
            stripped_only = line.strip()
            if (
                _RE_DISABLE_PRAGMA.fullmatch(stripped_only)
                or _RE_DISABLE_COMMENT.fullmatch(stripped_only)
                or _RE_ENABLE_PRAGMA.fullmatch(stripped_only)
                or _RE_ENABLE_COMMENT.fullmatch(stripped_only)
            ):
                pass
            else:
                line = line.rstrip() + "  "
        out.append(line)

    # Structural transforms (multi-line, applied after per-line transforms)
    out = _join_adjacent_statements(out, rng, profile.statement_join_prob)
    out = _inline_then(out, rng, profile.inline_then_prob)
    out = _collapse_multiline_calls(out, rng, profile.call_collapse_prob)

    return "\n".join(out)


def _try_merge_case_label(
    lines: list[str],
    index: int,
    rng: random.Random,
    *,
    in_decl: bool,
    profile: MessyProfile,
) -> tuple[str, int] | None:
    if in_decl or rng.random() > profile.case_merge_prob:
        return None
    match = RE_CASE_LABEL_ONLY.match(lines[index])
    if not match:
        return None
    indent, label = match.group(1), match.group(2)
    j = index + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines):
        return None
    body = lines[j].strip()
    if not body or body.startswith("(*") or body.upper().startswith(("CASE ", "END_CASE", "ELSE")):
        return None
    if body.endswith(";") or ":=" in body:
        return f"{indent}{label}: {body}", j - index + 1
    return None


def _randomize_keyword_case(line: str, rng: random.Random, profile: MessyProfile) -> str:
    comment_start = len(line)
    for marker in ("(*", "//"):
        pos = line.find(marker)
        if pos >= 0:
            comment_start = min(comment_start, pos)
    code_part = line[:comment_start]
    suffix = line[comment_start:]

    protected_parts: list[str] = []

    def save_part(lit: str) -> str:
        protected_parts.append(lit)
        return f"__PH{len(protected_parts) - 1}__"

    protected, pragmas = _protect_pragmas(code_part)
    protected = sub_st_string_literals(protected, save_part)

    def maybe_lower(match: re.Match[str]) -> str:
        return match.group().lower() if rng.random() < profile.keyword_lower_prob else match.group()

    result = RE_KEYWORD.sub(maybe_lower, protected)
    for idx, part in enumerate(protected_parts):
        result = result.replace(f"__PH{idx}__", part)
    result = _restore_pragmas(result, pragmas)
    return result + suffix


def _protect_pragmas(code: str) -> tuple[str, list[str]]:
    pragmas: list[str] = []

    def save(match: re.Match[str]) -> str:
        pragmas.append(match.group())
        return f"__PR{len(pragmas) - 1}__"

    return RE_PRAGMA.sub(save, code), pragmas


def _restore_pragmas(code: str, pragmas: list[str]) -> str:
    for idx, pragma in enumerate(pragmas):
        code = code.replace(f"__PR{idx}__", pragma)
    return code


def _mess_multi_var_decl(
    line: str,
    rng: random.Random,
    *,
    in_var_block: bool,
    profile: MessyProfile,
) -> str:
    if not in_var_block or rng.random() > profile.multi_var_decl_mess_prob:
        return line
    m = RE_MULTI_VAR_DECL.match(line)
    if not m:
        return line
    indent, names = m.group(1), m.group(2)
    style = rng.randrange(3)
    if style == 0:
        messed_names = re.sub(r"\s*,\s*", ",", names)
    elif style == 1:
        messed_names = re.sub(r"\s*,\s*", ", ", names)
    else:
        messed_names = re.sub(r"\s*,\s*", ",  ", names)
    rest = line[m.end() - 1:]  # keep ``: TYPE...`` suffix
    return f"{indent}{messed_names}{rest}"


def _mess_indent(
    line: str,
    rng: random.Random,
    *,
    in_decl: bool,
    profile: MessyProfile,
) -> str:
    if (
        in_decl
        or RE_END_KEYWORD.match(line)
        or RE_METHOD_HEADER.match(line)
        or rng.random() > profile.indent_mess_prob
    ):
        return line
    stripped = line.lstrip(" ")
    if not stripped:
        return line
    lead = len(line) - len(stripped)
    delta = rng.choice([-4, -2, -1, 1, 2, 4])
    new_lead = max(0, lead + delta)
    return (" " * new_lead) + stripped


def _mess_comparison_spacing(
    line: str,
    rng: random.Random,
    *,
    in_decl: bool,
    in_enum_body: bool,
    profile: MessyProfile,
) -> str:
    if in_decl or in_enum_body or ":=" in line or "=>" in line or rng.random() > profile.comparison_mess_prob:
        return line
    if not RE_COMPARISON_OPS.search(line):
        return line
    comment_start = len(line)
    for marker in ("(*", "//"):
        pos = line.find(marker)
        if pos >= 0:
            comment_start = min(comment_start, pos)
    code = line[:comment_start]
    suffix = line[comment_start:]
    if "<>" in code:
        code = re.sub(r"\s*<>\s*", "  <>  ", code, count=1)
    code = re.sub(r"(?<![:<>=!])\s*=\s*(?![=>])", "  =  ", code)
    return code + suffix


def _mess_semicolon_comment_gap(line: str, rng: random.Random, profile: MessyProfile) -> str:
    if rng.random() > profile.semicolon_comment_gap_prob:
        return line
    m = RE_SEMICOLON_COMMENT.search(line)
    if not m:
        return line
    extra = " " * rng.randint(2, 4)
    return line[: m.start()] + ";" + extra + m.group(2) + line[m.end() :]


def _mess_operator_spacing(
    line: str,
    rng: random.Random,
    *,
    in_var_block: bool,
    in_enum_body: bool,
    skip_spacing: bool,
    profile: MessyProfile,
) -> str:
    if skip_spacing:
        return line
    if RE_ENUM_MEMBER.match(line) and not profile.mess_enum_members:
        return line
    if RE_ENUM_EXPR_MEMBER.match(line) and not profile.mess_enum_members:
        return line
    if re.search(r":=\s*$", line.split("(*")[0]):
        return line

    comment_start = len(line)
    for marker in ("(*", "//"):
        pos = line.find(marker)
        if pos >= 0:
            comment_start = min(comment_start, pos)
    code = line[:comment_start]
    suffix = line[comment_start:]
    if not code.strip():
        return line

    threshold = (
        profile.operator_mess_threshold_var
        if in_var_block
        else profile.operator_mess_threshold_impl
    )
    if in_enum_body:
        threshold = min(1.0, threshold + 0.15)
    if rng.random() > threshold:
        return line

    protected, pragmas = _protect_pragmas(code)
    join_styles = (":=", " :=", " := ")

    if in_var_block and not in_enum_body:
        if ":=" in protected:
            return line
        protected = _mess_type_colon_segment(protected, rng)
    elif ":=" in protected:
        if _has_complex_rhs(line) and not in_enum_body and not profile.mess_complex_rhs:
            return line
        left, right = protected.split(":=", 1)
        join = join_styles[rng.randrange(len(join_styles))]
        protected = left.rstrip() + join + right.lstrip()

    return _restore_pragmas(protected, pragmas) + suffix


def _mess_type_colon_segment(segment: str, rng: random.Random) -> str:
    match = RE_TYPE_COLON.search(segment)
    if not match:
        return segment
    left = match.group(1)
    gap = " " * rng.randint(1, 8)
    replacement = f"{left}{gap}:"
    return segment[: match.start()] + replacement + segment[match.end() :]


def _has_complex_rhs(line: str) -> bool:
    if ":=" not in line:
        return False
    rhs = line.split(":=", 1)[1]
    upper = rhs.upper()
    return "(" in rhs or " AND" in upper or " OR" in upper


# ---------------------------------------------------------------------------
# Structural transforms (Phase 5 — canonical formatter coverage)
# ---------------------------------------------------------------------------


def _join_adjacent_statements(
    lines: list[str], rng: random.Random, prob: float
) -> list[str]:
    """Join two adjacent simple assignment statements onto one line."""
    if prob <= 0:
        return lines
    result: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if (
            RE_SIMPLE_STMT.match(line)
            and not RE_CONTROL_KW_LINE.match(line)
            and rng.random() < prob
            and i + 1 < len(lines)
        ):
            nxt = lines[i + 1]
            nxt_stripped = nxt.strip()
            if (
                RE_SIMPLE_STMT.match(nxt)
                and not RE_CONTROL_KW_LINE.match(nxt)
                and not nxt_stripped.startswith(("(*", "//"))
            ):
                result.append(line.rstrip() + " " + nxt_stripped)
                i += 2
                continue
        result.append(line)
        i += 1
    return result


def _inline_then(lines: list[str], rng: random.Random, prob: float,
                  *, max_joined_len: int = 228) -> list[str]:
    """Merge standalone THEN back onto the preceding IF/ELSIF line (conservative).

    Only joins THEN to the immediately preceding line when that line starts
    with IF or ELSIF, does not end with a block comment, and the joined
    result stays within *max_joined_len* characters.
    """
    if prob <= 0:
        return lines
    result: list[str] = []
    for i, line in enumerate(lines):
        if (
            RE_LONE_THEN.match(line)
            and result
            and rng.random() < prob
        ):
            prev = result[-1]
            if RE_IF_ELSIF_LINE.match(prev):
                prev_stripped = prev.strip()
                prev_upper = prev_stripped.upper()
                if (
                    not prev_upper.endswith("THEN")
                    and not prev_upper.endswith("DO")
                    and not prev_stripped.endswith("*)")
                    and len(prev.rstrip()) + 5 <= max_joined_len
                ):
                    result[-1] = prev.rstrip() + " " + line.strip()
                    continue
        result.append(line)
    return result


def _collapse_multiline_calls(
    lines: list[str], rng: random.Random, prob: float,
    *, max_params: int = 3, max_len: int = 230,
) -> list[str]:
    """Collapse multiline FB calls back onto a single line (conservative).

    Only collapses when the joined result has at most *max_params* top-level
    parameters and fits within *max_len* characters — otherwise the formatter
    would re-wrap and produce different indentation than the golden.
    """
    if prob <= 0:
        return lines
    result: list[str] = []
    i = 0
    while i < len(lines):
        m = RE_FB_CALL_OPEN.match(lines[i])
        if not m or rng.random() >= prob:
            result.append(lines[i])
            i += 1
            continue

        opener = lines[i].rstrip()
        j = i + 1
        depth = 1
        param_lines: list[str] = []
        while j < len(lines) and depth > 0:
            s = lines[j].strip()
            if not s:
                j += 1
                continue
            for ch in s:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            param_lines.append(s)
            j += 1

        if depth != 0 or not param_lines:
            result.append(lines[i])
            i += 1
            continue

        joined = opener + " ".join(param_lines)
        joined = re.sub(r"  +", " ", joined)

        n_commas = 0
        d = 0
        for ch in joined:
            if ch == "(":
                d += 1
            elif ch == ")":
                d -= 1
            elif ch == "," and d <= 1:
                n_commas += 1
        n_params = n_commas + 1

        if n_params <= max_params and len(joined) <= max_len:
            result.append(joined)
            i = j
        else:
            result.append(lines[i])
            i += 1

    return result
