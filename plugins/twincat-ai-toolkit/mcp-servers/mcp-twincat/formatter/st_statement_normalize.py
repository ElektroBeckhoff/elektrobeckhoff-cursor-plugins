"""Statement normalizer for IEC 61131-3 Structured Text.

Ensures one statement per line by splitting at statement boundaries:
semicolons, control-flow keywords (THEN/DO/OF/ELSE/ELSIF/END_*),
and declaration block boundaries (VAR/END_VAR).

Respects parenthesized expressions, string literals, block comments,
and pragmas.  Runs BEFORE format_st_code in the pipeline so that the
column-anchor indent engine can properly indent the resulting lines.
"""
from __future__ import annotations

import re

from formatter.st_string_scan import iter_st_string_spans

_RE_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_PRAGMA = re.compile(r"\{[^}]*\}")
_RE_LINE_COMMENT = re.compile(r"//[^\n]*")
_RE_FMT_MARKER = re.compile(
    r"\(\*\s*formatting\.(?:dis|en)able\s*\*\)",
    re.IGNORECASE,
)

_SPLIT_AFTER_KW: frozenset[str] = frozenset({
    "THEN", "DO", "ELSE", "REPEAT",
    "END_IF", "END_CASE", "END_FOR", "END_WHILE", "END_REPEAT",
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT",
    "VAR_GLOBAL", "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG",
    "END_VAR",
    "END_FUNCTION_BLOCK", "END_FUNCTION", "END_PROGRAM",
    "END_METHOD", "END_PROPERTY", "END_ACTION",
    "STRUCT", "UNION",
    "END_TYPE", "END_STRUCT", "END_UNION",
    "__TRY", "__FINALLY", "__ENDTRY",
})

_VAR_MODIFIERS: frozenset[str] = frozenset({
    "CONSTANT", "PERSISTENT", "RETAIN",
})

_SPLIT_BEFORE_KW: frozenset[str] = frozenset({
    "ELSE", "ELSIF", "UNTIL",
    "END_IF", "END_CASE", "END_FOR", "END_WHILE", "END_REPEAT",
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT",
    "VAR_GLOBAL", "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG",
    "END_VAR",
    "FUNCTION_BLOCK", "FUNCTION", "PROGRAM",
    "END_FUNCTION_BLOCK", "END_FUNCTION", "END_PROGRAM",
    "METHOD", "PROPERTY", "ACTION",
    "END_METHOD", "END_PROPERTY", "END_ACTION",
    "TYPE", "END_TYPE", "STRUCT", "UNION", "END_STRUCT", "END_UNION",
    "__TRY", "__CATCH", "__FINALLY", "__ENDTRY",
})

# END_* keywords: only split-before when actual code precedes (not just comments)
_SPLIT_BEFORE_CODE_ONLY: frozenset[str] = frozenset({
    "ELSE", "ELSIF", "UNTIL",
    "END_IF", "END_CASE", "END_FOR", "END_WHILE", "END_REPEAT",
    "END_VAR",
    "END_FUNCTION_BLOCK", "END_FUNCTION", "END_PROGRAM",
    "END_METHOD", "END_PROPERTY", "END_ACTION",
    "END_TYPE", "END_STRUCT", "END_UNION",
    "__CATCH", "__FINALLY", "__ENDTRY",
})


_RE_STANDALONE_DIRECTIVE = re.compile(
    r"^\{(?:FORMATTING\.|IF\s|ELSE\}|END_IF\}|REGION\s|ENDREGION\})",
    re.IGNORECASE,
)


def _is_standalone_directive(pragma_text: str) -> bool:
    """True for pragmas that must be on their own line (not attribute annotations)."""
    return _RE_STANDALONE_DIRECTIVE.match(pragma_text) is not None


def normalize_statements(source: str) -> str:
    """Split compressed ST code into one-statement-per-line canonical form.

    Idempotent on already-normalized code.  Returns the normalized source.
    """
    lines = source.split("\n")
    result: list[str] = []
    in_block_comment = False
    case_depth = 0
    paren_depth = 0
    decl_paren_depth = 0

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

        split, case_depth, paren_depth, decl_paren_depth = (
            _split_line_statements(line, case_depth, paren_depth, decl_paren_depth)
        )
        result.extend(split)

        # Track inline unclosed block comments (e.g. `IF x THEN (* multi-line...`)
        if _has_unclosed_block_comment(stripped):
            in_block_comment = True

    return "\n".join(result)


def _has_unindented_structural_blocks(source: str) -> bool:
    """True if structural indentation appears to be completely missing."""
    lines = source.split("\n")
    has_block = False
    in_bc = False
    code_lines: list[str] = []
    for l in lines:
        s = l.strip()
        if not s:
            continue
        if in_bc:
            if "*)" in s:
                in_bc = False
            continue
        if "(*" in s and "*)" not in s:
            in_bc = True
            continue
        u = s.upper()
        if u.startswith(("IF ", "FOR ", "WHILE ", "CASE ", "REPEAT", "__TRY")):
            has_block = True
        code_lines.append(l)
    if not has_block or len(code_lines) < 3:
        return False
    return all(not l[0:1].isspace() for l in code_lines)


def did_normalize(source: str) -> bool:
    """Return True if normalize_statements would change *source*
    or if structural indentation appears to be missing."""
    if normalize_statements(source) != source:
        return True
    return _has_unindented_structural_blocks(source)


def normalize_and_check(source: str) -> tuple[str, bool]:
    """Normalize statements and return (normalized_source, was_normalized)."""
    normalized = normalize_statements(source)
    if normalized != source:
        return normalized, True
    return normalized, _has_unindented_structural_blocks(source)


def _has_unclosed_block_comment(text: str) -> bool:
    """True if *text* contains ``(*`` without a matching ``*)``.

    Integrated scan: ``'`` inside block comments is ignored (not a string
    delimiter), and ``(*``/``*)`` inside strings are ignored.
    """
    depth = 0
    in_string = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_string:
            if c == "'" and i + 1 < n and text[i + 1] == "'":
                i += 2
                continue
            if c == "'":
                in_string = False
            i += 1
            continue
        if depth > 0:
            if c == "*" and i + 1 < n and text[i + 1] == ")":
                depth -= 1
                i += 2
                continue
            i += 1
            continue
        if c == "'":
            in_string = True
            i += 1
            continue
        if c == "(" and i + 1 < n and text[i + 1] == "*":
            depth += 1
            i += 2
            continue
        i += 1
    return depth > 0


def _build_mask(text: str) -> str:
    """Replace strings, block comments, line comments, and pragmas with \\x01.

    Block comments are masked first so that ``'`` inside comments (e.g.
    ``FB's``) is not misinterpreted as a string delimiter.
    """
    if "(*" not in text and "//" not in text and "'" not in text and '"' not in text and "{" not in text:
        return text

    chars = list(text)

    # 1. Block comments first (take priority over string detection)
    for m in _RE_BLOCK_COMMENT.finditer(text):
        for i in range(m.start(), m.end()):
            chars[i] = "\x01"

    # 2. Strings: scan a comment-safe copy so ' inside (* *) is ignored
    safe = list(text)
    for i, c in enumerate(chars):
        if c == "\x01":
            safe[i] = " "
    for start, end in iter_st_string_spans("".join(safe)):
        for i in range(start, end):
            chars[i] = "\x01"

    # 3. Line comments and pragmas — scan masked text so that
    # // and { } inside already-masked strings are not misinterpreted.
    masked_so_far = "".join(chars)
    for m in _RE_LINE_COMMENT.finditer(masked_so_far):
        for i in range(m.start(), m.end()):
            chars[i] = "\x01"

    masked_so_far = "".join(chars)
    for m in _RE_PRAGMA.finditer(masked_so_far):
        for i in range(m.start(), m.end()):
            chars[i] = "\x01"

    # 4. Mask unclosed block comments: (* without matching *) on this line
    for j in range(len(chars) - 1):
        if chars[j] != "\x01" and text[j] == "(" and chars[j + 1] != "\x01" and text[j + 1] == "*":
            for k in range(j, len(chars)):
                chars[k] = "\x01"
            break

    return "".join(chars)


def _extract_word(mask: str, pos: int) -> str:
    """Extract an uppercase word at *pos* from the mask."""
    if pos >= len(mask) or not (mask[pos].isalpha() or mask[pos] == "_"):
        return ""
    end = pos
    while end < len(mask) and (mask[end].isalnum() or mask[end] == "_"):
        end += 1
    return mask[pos:end].upper()


def _word_boundary(mask: str, pos: int, word_len: int) -> bool:
    """True when the word at *pos* has non-identifier chars on both sides."""
    if pos > 0 and (mask[pos - 1].isalnum() or mask[pos - 1] == "_"):
        return False
    end = pos + word_len
    if end < len(mask) and (mask[end].isalnum() or mask[end] == "_"):
        return False
    return True


def _skip_ws_and_masked(mask: str, start: int, text: str | None = None) -> int:
    """Skip whitespace, masked regions, and unclosed block comments.

    Also handles ``(*`` that was not closed on this line (multi-line
    block comment) — everything from ``(*`` to the end is protected.
    """
    i = start
    n = len(mask)
    while i < n:
        if mask[i] in (" ", "\t", "\x01"):
            i += 1
            continue
        if text is not None and i + 1 < n and text[i] == "(" and text[i + 1] == "*":
            return n
        break
    return i


def _paren_depth_at(mask: str, pos: int) -> int:
    """Parenthesis nesting depth at *pos* (counting unmasked '(' and ')')."""
    d = 0
    for i in range(pos):
        if mask[i] == "(":
            d += 1
        elif mask[i] == ")":
            d = max(0, d - 1)
    return d


def _has_content_after(text: str, pos: int) -> bool:
    return bool(text[pos:].strip())


def _has_content_before(text: str, pos: int) -> bool:
    return bool(text[:pos].strip())


def _has_code_before(mask: str, pos: int) -> bool:
    """True when there is unmasked code (not just comments/pragmas) before *pos*."""
    for i in range(pos):
        if mask[i] not in (" ", "\t", "\x01"):
            return True
    return False


def _split_line_statements(
    line: str,
    initial_case_depth: int = 0,
    initial_depth: int = 0,
    initial_decl_paren_depth: int = 0,
) -> tuple[list[str], int, int, int]:
    """Split one physical line at statement boundaries.

    Returns (result_lines, final_case_depth, final_depth,
    final_decl_paren_depth) to allow the caller to carry state across lines.
    """
    stripped = line.strip()
    if not stripped:
        return [line], initial_case_depth, initial_depth, initial_decl_paren_depth

    indent = line[: len(line) - len(line.lstrip())]

    # Fast path: short lines rarely need splitting
    if len(stripped) < 10 and initial_depth == 0:
        return [line], initial_case_depth, initial_depth, initial_decl_paren_depth

    mask = _build_mask(stripped)

    splits: list[int] = []

    # Standalone compiler directives: split before/after
    for pm in _RE_PRAGMA.finditer(stripped):
        content = pm.group().upper()
        if not _is_standalone_directive(content):
            continue
        ps, pe = pm.start(), pm.end()
        if _has_code_before(mask, ps):
            splits.append(ps)
        rest = _skip_ws_and_masked(mask, pe, stripped)
        if rest < len(mask):
            splits.append(pe)

    # {attribute} pragmas: split between consecutive ones.
    attr_pragmas = [
        m for m in _RE_PRAGMA.finditer(stripped)
        if m.group().upper().startswith("{ATTRIBUTE") and mask[m.start()] != "\x01"
    ]
    for ai in range(len(attr_pragmas) - 1):
        cur_end = attr_pragmas[ai].end()
        nxt_start = attr_pragmas[ai + 1].start()
        between = stripped[cur_end:nxt_start].strip()
        if not between:
            splits.append(nxt_start)

    # After last {attribute} pragma: split if a block comment follows
    if attr_pragmas:
        last_ae = attr_pragmas[-1].end()
        ap_after = last_ae
        sn = len(stripped)
        while ap_after < sn and stripped[ap_after] in (" ", "\t"):
            ap_after += 1
        if (ap_after + 1 < sn
                and stripped[ap_after] == "("
                and stripped[ap_after + 1] == "*"):
            splits.append(ap_after)

    # (* formatting.disable/enable *) block-comment markers
    for fm in _RE_FMT_MARKER.finditer(stripped):
        fs, fe = fm.start(), fm.end()
        if _has_code_before(mask, fs):
            splits.append(fs)
        rest = _skip_ws_and_masked(mask, fe, stripped)
        if rest < len(mask):
            splits.append(fe)

    # Standalone block comments with text: split after (* ... *) when
    # anything follows and no actual code precedes.
    # Decorative markers like (**) or (***) are excluded (no word characters).
    for bc in _RE_BLOCK_COMMENT.finditer(stripped):
        bs, be = bc.start(), bc.end()
        inner = stripped[bs + 2 : be - 2]
        if not any(c.isalpha() for c in inner):
            continue
        if _has_code_before(mask, bs):
            continue
        after = be
        while after < len(mask) and stripped[after] in (" ", "\t"):
            after += 1
        if after < len(mask):
            splits.append(be)

    depth = initial_depth
    case_depth = initial_case_depth
    seen_case = False
    decl_paren_depth = initial_decl_paren_depth
    i = 0
    n = len(mask)

    while i < n:
        ch = mask[i]

        if ch == "\x01":
            i += 1
            continue

        if ch in ("(", "["):
            if depth == 0 and ch == "(":
                j = i - 1
                while j >= 0 and mask[j] in (" ", "\t", "\x01"):
                    j -= 1
                if j >= 0 and mask[j] == ":":
                    before_colon = stripped[:j].upper()
                    if re.search(r"\bTYPE\b", before_colon):
                        decl_paren_depth = 1
                        after = _skip_ws_and_masked(mask, i + 1, stripped)
                        if after < n and stripped[after] not in (")", "]"):
                            splits.append(after)
            depth += 1
            i += 1
            continue
        if ch in (")", "]"):
            if ch == ")" and depth == decl_paren_depth and decl_paren_depth > 0:
                if _has_code_before(mask, i):
                    splits.append(i)
                decl_paren_depth = 0
            depth = max(0, depth - 1)
            i += 1
            continue

        if depth > 0:
            if ch == "," and depth == decl_paren_depth and decl_paren_depth > 0:
                j = i + 1
                while j < n and stripped[j] in (" ", "\t"):
                    j += 1
                # Skip inline comments (keep with current member)
                if (j + 1 < n and stripped[j] == "(" and stripped[j + 1] == "*"):
                    bc_close = stripped.find("*)", j + 2)
                    if bc_close >= 0:
                        j = bc_close + 2
                        while j < n and stripped[j] in (" ", "\t"):
                            j += 1
                elif (j + 1 < n and stripped[j] == "/" and stripped[j + 1] == "/"):
                    j = n
                if j < n:
                    splits.append(j)
            i += 1
            continue

        # Semicolon — split before next code (keeps trailing comments with ;)
        if ch == ";":
            semi_after = i + 1
            sa_ws = semi_after
            while sa_ws < n and stripped[sa_ws] in (" ", "\t"):
                sa_ws += 1
            sa_split = False
            if (sa_ws + 1 < n
                    and stripped[sa_ws] == "("
                    and stripped[sa_ws + 1] == "*"):
                sa_bc_close = stripped.find("*)", sa_ws + 2)
                if sa_bc_close >= 0:
                    sa_inner = stripped[sa_ws + 2 : sa_bc_close]
                    if any(c.isalpha() for c in sa_inner):
                        sa_bc_end = sa_bc_close + 2
                        code_after = _skip_ws_and_masked(
                            mask, sa_bc_end, stripped)
                        if code_after < n:
                            splits.append(sa_bc_end)
                            sa_split = True
            if not sa_split:
                code_pos = _skip_ws_and_masked(mask, semi_after, stripped)
                if code_pos < n:
                    splits.append(code_pos)
            i += 1
            continue

        # CASE label colon — split after (inside CASE blocks only)
        if ch == ":" and case_depth > 0:
            if i + 1 < n and mask[i + 1] != "=":
                colon_after = i + 1
                code_pos = _skip_ws_and_masked(mask, colon_after, stripped)
                if code_pos < n:
                    # Check for text block comment between colon and code
                    ca_ws = colon_after
                    while ca_ws < n and stripped[ca_ws] in (" ", "\t"):
                        ca_ws += 1
                    if (ca_ws + 1 < n
                            and stripped[ca_ws] == "("
                            and stripped[ca_ws + 1] == "*"):
                        ca_bc_close = stripped.find("*)", ca_ws + 2)
                        if ca_bc_close >= 0:
                            ca_inner = stripped[ca_ws + 2 : ca_bc_close]
                            bc_end_pos = ca_bc_close + 2
                            rest_pos = _skip_ws_and_masked(mask, bc_end_pos, stripped)
                            if any(c.isalpha() for c in ca_inner):
                                if rest_pos < n:
                                    splits.append(bc_end_pos)
                            else:
                                splits.append(colon_after)
                        else:
                            splits.append(colon_after)
                    else:
                        splits.append(colon_after)
            i += 1
            continue

        # Keyword detection
        if ch.isalpha() or ch == "_":
            word = _extract_word(mask, i)
            word_len = len(word)

            if not word or not _word_boundary(mask, i, word_len):
                i += 1
                continue

            if word == "CASE":
                case_depth += 1
                seen_case = True
            elif word == "END_CASE":
                case_depth = max(0, case_depth - 1)

            end = i + word_len

            # Split AFTER keyword (skip trailing comments, split before next code)
            if word in _SPLIT_AFTER_KW:
                if word == "ELSE":
                    rest = stripped[end:].lstrip()
                    if rest.startswith(":"):
                        i = end
                        continue
                after = end
                # END_* keywords: skip optional trailing semicolon (END_WHILE;)
                if word.startswith("END_"):
                    while after < n and mask[after] in (" ", "\t"):
                        after += 1
                    if after < n and mask[after] == ";":
                        after += 1
                # VAR keywords: skip modifiers (CONSTANT, PERSISTENT, RETAIN)
                elif word.startswith("VAR"):
                    while after < n:
                        while after < n and mask[after] in (" ", "\t"):
                            after += 1
                        mod = _extract_word(mask, after)
                        if mod in _VAR_MODIFIERS:
                            after += len(mod)
                        else:
                            break

                # Text block comment after keyword with code following →
                # split before AND after the comment so it gets its own line.
                # If the comment is a trailing annotation (no code after), keep
                # it on the keyword line (e.g. ELSE (*automatic-mode*)).
                after_ws = after
                while after_ws < n and stripped[after_ws] in (" ", "\t"):
                    after_ws += 1
                split_done = False
                if (after_ws + 1 < n
                        and stripped[after_ws] == "("
                        and stripped[after_ws + 1] == "*"):
                    bc_close = stripped.find("*)", after_ws + 2)
                    if bc_close >= 0:
                        inner = stripped[after_ws + 2 : bc_close]
                        if any(c.isalpha() for c in inner):
                            bc_end = bc_close + 2
                            code_after = _skip_ws_and_masked(
                                mask, bc_end, stripped)
                            if code_after < n:
                                splits.append(after_ws)
                                splits.append(bc_end)
                                split_done = True
                if not split_done:
                    code_pos = _skip_ws_and_masked(mask, after, stripped)
                    if code_pos < n:
                        splits.append(code_pos)

            # OF: only in CASE context
            if word == "OF" and seen_case:
                code_pos = _skip_ws_and_masked(mask, end, stripped)
                if code_pos < n:
                    splits.append(code_pos)
                seen_case = False

            # __CATCH: skip optional (exc) before splitting after
            if word == "__CATCH":
                after = end
                while after < n and mask[after] in (" ", "\t"):
                    after += 1
                if after < n and mask[after] == "(":
                    p_depth = 1
                    after += 1
                    while after < n and p_depth > 0:
                        if mask[after] == "(":
                            p_depth += 1
                        elif mask[after] == ")":
                            p_depth -= 1
                        after += 1
                code_pos = _skip_ws_and_masked(mask, after, stripped)
                if code_pos < n:
                    splits.append(code_pos)

            # Split BEFORE keyword
            if word in _SPLIT_BEFORE_KW:
                if word in _SPLIT_BEFORE_CODE_ONLY:
                    if _has_code_before(mask, i):
                        splits.append(i)
                elif _has_content_before(stripped, i):
                    splits.append(i)

            i = end
            continue

        i += 1

    if not splits:
        return [line], case_depth, depth, decl_paren_depth

    # Deduplicate and sort
    unique = sorted(set(splits))

    parts: list[str] = []
    last = 0
    for pos in unique:
        segment = stripped[last:pos].strip()
        if segment:
            parts.append(segment)
        last = pos

    remaining = stripped[last:].strip()
    if remaining:
        parts.append(remaining)

    if len(parts) <= 1:
        return [line], case_depth, depth, decl_paren_depth

    return [indent + p for p in parts], case_depth, depth, decl_paren_depth
