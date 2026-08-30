"""VAR block and enum/struct declaration parsing."""
import re

from autodocs.constants import QUAL, SECTION_KEYS
from autodocs.text_utils import (
    _scan_block_comment,
    _strip_block_comments,
    strip_tc_attributes,
)

def parse_enum_members(enum_body: str):
    """
    Parse enum members inside the '( ... )' list of a TYPE declaration.
    Returns a list of tuples (name, value, comment).

    Rules:
      - Line comments after a comma belong to the PREVIOUS item.
      - Block comments are collected as the current item's comment.
      - Nested block comments (* (*inner*) outer *) are handled via depth tracking.
      - Stray '*)' at end of line comments is stripped.
      - {attribute ...} pragmas are ignored.
    """
    items = []
    if not enum_body:
        return items

    s = enum_body
    i, n = 0, len(s)
    buf = []
    cbuf = []
    in_line = False
    block_depth = 0

    def _clean_comment():
        raw = " ".join(x.strip() for x in "".join(cbuf).splitlines()).strip()
        raw = re.sub(r"\(\*|\*\)", "", raw).strip()
        raw = re.sub(r"\s*\*\)\s*$", "", raw).strip()
        return raw

    def finalize_item():
        nonlocal buf, cbuf
        token = strip_tc_attributes("".join(buf)).strip()
        if token:
            m = re.match(r"^(?P<name>[A-Za-z_]\w*)(?:\s*:=\s*(?P<val>.*))?$", token)
            if m:
                name = m.group("name").strip()
                val = (m.group("val") or "").strip()
                comment = _clean_comment()
                items.append((name, val, comment))
        buf.clear()
        cbuf.clear()

    while i < n:
        c = s[i]
        c2 = s[i + 1] if i + 1 < n else ""

        if block_depth > 0:
            if c == "(" and c2 == "*":
                block_depth += 1
                i += 2
            elif c == "*" and c2 == ")":
                block_depth -= 1
                i += 2
            else:
                cbuf.append(c)
                i += 1
            continue

        if in_line:
            if c == "\n":
                in_line = False
            else:
                cbuf.append(c)
            i += 1
            continue

        if c == "(" and c2 == "*":
            block_depth = 1
            i += 2
            continue
        if c == "/" and c2 == "/":
            in_line = True
            i += 2
            continue

        if c == ",":
            j = i + 1
            while j < n and s[j] in " \t":
                j += 1
            if j + 1 < n and s[j] == "(" and s[j + 1] == "*":
                inner, j = _scan_block_comment(s, j + 2)
                cbuf.append(inner)
            elif j + 1 < n and s[j] == "/" and s[j + 1] == "/":
                j += 2
                while j < n and s[j] != "\n":
                    cbuf.append(s[j])
                    j += 1
            finalize_item()
            i = j
            continue

        buf.append(c)
        i += 1

    finalize_item()
    return items


def extract_struct_like_body(decl_text: str, kind: str) -> str:
    """
    Extract the inner body between STRUCT/UNION and END_STRUCT/END_UNION.
    Returns the inner text or ''.
    """
    if not decl_text:
        return ""
    if kind.upper() == "STRUCT":
        m = re.search(
            r"\bSTRUCT\b(.*?)\bEND_STRUCT\b", decl_text, flags=re.IGNORECASE | re.DOTALL
        )
    else:
        m = re.search(
            r"\bUNION\b(.*?)\bEND_UNION\b", decl_text, flags=re.IGNORECASE | re.DOTALL
        )
    return m.group(1).strip() if m else ""


def extract_var_blocks_from_declaration(decl_text: str):
    """
    Collect all regions between VAR_* (including modifiers like CONSTANT/RETAIN) and END_VAR.

    Returns a dict with keys: {"INPUT": [<block>, ...], "OUTPUT": [...], "IN_OUT": [...]}
    Each list contains raw block strings without outer VAR_* / END_VAR lines.
    """
    blocks = {"INPUT": [], "OUTPUT": [], "IN_OUT": []}
    if not decl_text or not decl_text.strip():
        return blocks

    txt = decl_text
    pattern = r"(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT)\b(?:[^\S\r\n]+[A-Z_ ]+)?[^\S\r\n]*(.*?)(?=END_VAR\b)"
    for m in re.finditer(pattern, txt, flags=re.DOTALL | re.IGNORECASE):
        header = m.group(1).upper()
        body = m.group(2).strip()
        key = SECTION_KEYS[header]
        if body:
            blocks[key].append(body)

    return blocks


def _strip_outer_quotes(s: str) -> str:
    """
    Strip surrounding single or double quotes, if present.
    """
    s = s.strip()
    if (len(s) >= 2) and (s[0] == s[-1]) and s[0] in ("'", '"'):
        return s[1:-1]
    return s


def parse_declarations_from_block(block_text: str):
    """
    Parse a combined VAR_* body (possibly merged from multiple blocks) into declarations.

    Returns a list of tuples: (name, vtype, init, comment)

    Notes:
      - Supports multiple variable names separated by ',' for a single type.
      - Collects block comments '(* ... *)' and line comments '//' after the semicolon
        as the comment for that declaration.
      - Preserves initializers, stripping outer quotes for string-like values.
    """
    results = []
    if not block_text:
        return results

    buf = []

    def flush_statement():
        """
        Process the buffered text up to and including ';' into a single declaration.
        """
        nonlocal buf
        if not buf:
            return

        stmt = " ".join(s.strip() for s in buf).strip()
        stmt = strip_tc_attributes(stmt).strip()
        buf = []
        if not stmt or ";" not in stmt:
            return

        before, after = stmt.split(";", 1)
        before = strip_tc_attributes(before).strip()
        after = after.strip()

        # Collect comments appearing after the semicolon.
        # Depth-aware scan: handles nested (* (*inner*) outer *) and
        # respects // line comments (everything after // is literal text,
        # not block-comment syntax).
        comment_parts = []
        i_c, n_c, depth = 0, len(after), 0
        blk_start = -1
        line_comment_start = -1
        while i_c < n_c - 1:
            c0, c1 = after[i_c], after[i_c + 1]
            if depth == 0 and c0 == "/" and c1 == "/":
                line_comment_start = i_c + 2
                break
            if c0 == "(" and c1 == "*":
                if depth == 0:
                    blk_start = i_c + 2
                depth += 1
                i_c += 2
            elif c0 == "*" and c1 == ")":
                depth -= 1
                if depth == 0 and blk_start >= 0:
                    inner = after[blk_start:i_c].strip()
                    inner = re.sub(r"\(\*|\*\)", "", inner).strip()
                    if inner:
                        comment_parts.append(inner)
                    blk_start = -1
                i_c += 2
            else:
                i_c += 1

        if line_comment_start >= 0:
            lc = after[line_comment_start:].strip()
            lc = re.sub(r"\(\*.*?\*\)", "", lc, flags=re.DOTALL).strip()
            lc = re.sub(r"\s*\*\)\s*$", "", lc)
            if lc:
                comment_parts.append(lc)
        comment = " ".join(comment_parts).strip()

        before = _strip_block_comments(before).strip()
        if ":" not in before:
            return
        left, right = before.split(":", 1)
        left = strip_tc_attributes(left).strip()
        right = strip_tc_attributes(right).strip()

        names = [n.strip() for n in left.split(",") if n.strip()]

        init = ""
        if ":=" in right:
            type_part, init_part = right.split(":=", 1)
            vtype = type_part.strip()
            init = _strip_outer_quotes(init_part.strip())
        else:
            vtype = right

        vtype = re.sub(r"\s+", " ", vtype)

        for name in names:
            if name:
                results.append((name, vtype, init, comment))

    for raw in block_text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        line_no_attr = strip_tc_attributes(line).strip()
        if not line_no_attr:
            continue
        stripped_for_check = _strip_block_comments(line_no_attr).strip()
        if stripped_for_check.startswith("//") and ":" not in stripped_for_check and ";" not in stripped_for_check:
            continue
        buf.append(line_no_attr)
        if ";" in line_no_attr:
            flush_statement()

    flush_statement()
    return results


# --------------------------------------------------------------------
# Cross-reference index & type linking
# --------------------------------------------------------------------


