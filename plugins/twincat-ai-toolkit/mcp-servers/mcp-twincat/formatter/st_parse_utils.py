"""Shared ST structural analysis helpers for indentation."""
from __future__ import annotations

import re

from formatter.constants import ST_KEYWORDS
from formatter.st_string_scan import sub_st_string_literals

_RE_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_LINE_COMMENT = re.compile(r"//.*$", re.MULTILINE)

# Multiline IF/ELSIF/WHILE/UNTIL condition ending in an unclosed call ``(``.
RE_IF_MULTILINE_CALL = re.compile(
    r"^(\s*)"
    r"(?:IF|ELSIF|WHILE|UNTIL)\s+"
    r"(?:NOT\s+)?"
    r"(?:"
    r"(?:THIS\^\.|SUPER\^\.|[A-Za-z_]\w*\^\.|__)\S+?\("
    r"|[A-Za-z_]\w*\s*\("
    r")",
    re.IGNORECASE,
)


def strip_comments_and_strings(line: str) -> str:
    """Remove comments and strings for structural analysis only."""
    result = _RE_BLOCK_COMMENT.sub("", line)
    result = _RE_LINE_COMMENT.sub("", result)
    result = sub_st_string_literals(result, lambda _lit: "''")
    return result.strip()


def get_first_keyword(code: str) -> str:
    """Extract the first keyword-like token from a code line."""
    code = code.lstrip()
    match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", code)
    if match:
        word = match.group(0).upper()
        if word in ST_KEYWORDS:
            return word
    return ""


def line_ends_with_keyword(code: str, keyword: str) -> bool:
    """Check if line ends with a specific keyword (ignoring trailing comments)."""
    code = code.rstrip()
    return bool(re.search(r"\b" + keyword + r"\s*$", code, re.IGNORECASE))


def is_case_label(code: str) -> bool:
    """Check if line is a CASE label (e.g. '0:', 'E_State.Init:')."""
    code = code.strip()
    stripped_comment = _RE_LINE_COMMENT.sub("", code)
    stripped_comment = _RE_BLOCK_COMMENT.sub("", stripped_comment)
    uc = stripped_comment.find("(*")
    if uc >= 0:
        stripped_comment = stripped_comment[:uc]
    stripped_comment = stripped_comment.strip()
    if stripped_comment.endswith(":") and ":=" not in stripped_comment:
        return True
    return False


def is_if_wrapped_call_opener(stripped: str) -> bool:
    """True for multiline IF/ELSIF conditions ending in an unclosed call ``(``."""
    return stripped.endswith("(") and RE_IF_MULTILINE_CALL.match(stripped) is not None
