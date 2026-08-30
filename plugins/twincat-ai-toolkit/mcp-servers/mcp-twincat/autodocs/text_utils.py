"""Text, comment, and extends extraction helpers."""
import os
import re
from pathlib import Path

from autodocs.constants import QUAL

def _source_link_line(file_path: Path, out_file: Path | None) -> str:
    """Build a 'Source: [filename](relpath)' Markdown line linking to the original TwinCAT file."""
    if out_file is None:
        return f"\nSource: `{file_path.name}`\n"
    rel = Path(os.path.relpath(file_path, out_file.parent)).as_posix()
    return f"\nSource: [`{file_path.name}`](<{rel}>)\n"


def strip_tc_attributes(s: str) -> str:
    """
    Remove TwinCAT attribute pragmas such as:
      {attribute 'TcEncoding':='UTF-8'}
    anywhere in the string (case-insensitive). Safe for multi-attributes and multi-line text.
    """
    return re.sub(r"\{\s*attribute\b[^}]*\}", "", s, flags=re.IGNORECASE)


def strip_comments(s: str) -> str:
    """
    Remove TwinCAT/IEC comments from a string:
      - Block comments: (* ... *)
      - Line comments: // ...
    Returns the cleaned text (preserving line breaks where possible).
    """
    if not s:
        return ""
    s = re.sub(r"\(\*.*?\*\)", "", s, flags=re.DOTALL)
    s = re.sub(r"//.*?$", "", s, flags=re.MULTILINE)
    return s


def extract_pou_extends(main_decl: str) -> str:
    """
    Extract the base type from a POU signature line like:
      FUNCTION_BLOCK Name EXTENDS BaseType
      PROGRAM Name EXTENDS BaseType
      FUNCTION Name EXTENDS BaseType
    Returns the base type or empty string.
    """
    if not main_decl:
        return ""
    s = strip_tc_attributes(main_decl)
    m = re.search(
        r"^\s*(FUNCTION_BLOCK|PROGRAM|FUNCTION)\b[^\n]*?\bEXTENDS\s+(?P<base>[A-Za-z_][\w\.]*)",
        s,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return m.group("base").strip() if m else ""


def extract_itf_extends(main_decl: str) -> str:
    """
    Extract the base type from an Interface signature line like:
      INTERFACE I_Name EXTENDS I_Base
    Returns the base type or empty string.
    """
    if not main_decl:
        return ""
    s = strip_tc_attributes(main_decl)
    m = re.search(
        r"^\s*INTERFACE\b[^\n]*?\bEXTENDS\s+(?P<base>[A-Za-z_][\w\.]*)",
        s,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return m.group("base").strip() if m else ""


def extract_struct_extends(decl_text: str) -> str:
    """
    Extract the base struct from a STRUCT EXTENDS clause inside a TcDUT declaration body.
    Returns the base struct name or empty string.
    """
    if not decl_text:
        return ""
    s = strip_comments(strip_tc_attributes(decl_text))
    m = re.search(
        r"\bSTRUCT\b\s+(?:EXTENDS\s+(?P<base>[A-Za-z_]\w+))", s, flags=re.IGNORECASE
    )
    return (m.group("base") or "").strip() if m and m.group("base") else ""


def extract_dut_extends(decl_no_attr: str) -> str:
    """
    Extract base type on TYPE line:
      TYPE [QUAL] Name EXTENDS Base : STRUCT|UNION
    Returns the base type or empty string.
    """
    m = re.search(
        rf"^\s*TYPE{QUAL}\s+\w+\s+EXTENDS\s+(?P<base>[A-Za-z_][\w\.]*)\s*:\s*(STRUCT|UNION)\b",
        decl_no_attr,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    return m.group("base").strip() if m else ""


def has_hide_attribute(text: str) -> bool:
    """
    Detect the TwinCAT attribute:
      {attribute 'hide'}
    (case-insensitive, single or double quotes).
    """
    return bool(
        re.search(r"\{\s*attribute\s*['\"]hide['\"]\s*\}", text, flags=re.IGNORECASE)
    )


def localname(tag: str) -> str:
    """
    Return the local XML tag name without namespace.
    Example: '{ns}POU' -> 'POU'
    """
    return tag.split("}", 1)[1] if "}" in tag else tag


def clean_return_type(ret_raw: str) -> str:
    """
    Produce a pristine return type taken from a METHOD signature line.

    This function is intentionally defensive:
    - Strips TwinCAT attribute pragmas (e.g., {attribute '...'}).
    - Removes complete inline block comments `(* ... *)`.
    - If a block comment starts on the line but does not close on the same line,
      everything from `(*` to end-of-line is dropped to avoid leaking description text
      into the return type.
    - Removes single-line comments introduced by `//`.
    - Trims trailing semicolons and normalizes whitespace.

    Args:
        ret_raw: Raw return-type fragment as captured from the METHOD line (after the colon).

    Returns:
        Cleaned return type string suitable for Markdown rendering.
    """
    if not ret_raw:
        return ""
    s = strip_tc_attributes(ret_raw)
    # Remove well-formed inline block comments.
    s = re.sub(r"\(\*.*?\*\)", "", s, flags=re.DOTALL)
    # In case a block comment starts but does not close on the same line, drop the tail.
    s = re.sub(r"\(\*.*$", "", s)
    # Cut off inline line-comments.
    s = s.split("//", 1)[0]
    # Trim and normalize.
    s = s.strip().rstrip(";").strip()
    s = re.sub(r"\s+", " ", s)
    return s
def _strip_block_comments(s: str) -> str:
    """Remove all `(* ... *)` block comments (depth-aware for nested comments)."""
    out = []
    i, n = 0, len(s)
    while i < n:
        if i < n - 1 and s[i] == "(" and s[i + 1] == "*":
            _, end = _scan_block_comment(s, i + 2)
            i = end
        else:
            out.append(s[i])
            i += 1
    return "".join(out)


def _extract_block_comment_texts(s: str) -> list:
    """
    Extract inner text of all top-level `(* ... *)` block comments.
    Depth-aware: nested `(* *)` are stripped from the inner text.
    Returns a list of inner-text strings.
    """
    results = []
    i, n = 0, len(s)
    while i < n:
        if i < n - 1 and s[i] == "(" and s[i + 1] == "*":
            inner, end = _scan_block_comment(s, i + 2)
            txt = inner.strip()
            if txt:
                results.append(txt)
            i = end
        else:
            i += 1
    return results


def _scan_block_comment(s: str, start: int) -> tuple:
    """
    Depth-aware block comment scanner.
    *start* points to the first character AFTER the opening '(*'.
    Returns (inner_text, end_pos) where end_pos is the position AFTER
    the closing '*)'.  Inner nested '(*' / '*)' delimiters are stripped.
    """
    n = len(s)
    depth, j = 1, start
    parts = []
    while j < n - 1 and depth > 0:
        c0, c1 = s[j], s[j + 1]
        if c0 == "(" and c1 == "*":
            depth += 1
            j += 2
        elif c0 == "*" and c1 == ")":
            depth -= 1
            j += 2
        else:
            if depth >= 1:
                parts.append(c0)
            j += 1
    if j == n - 1 and depth > 0:
        parts.append(s[j])
        j += 1
    return "".join(parts), j

