"""Pure utility functions for the TwinCAT3 ST Formatter.

All functions are side-effect-free and operate only on their arguments.
No file I/O, no global state mutation.
"""
from __future__ import annotations

import hashlib
import re
from typing import Sequence


def normalize_line_endings(text: str, ending: str = "\n") -> str:
    """Normalize all line endings to the specified style."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if ending != "\n":
        normalized = normalized.replace("\n", ending)
    return normalized


def strip_trailing_whitespace(text: str) -> str:
    """Remove trailing whitespace from each line."""
    return "\n".join(line.rstrip() for line in text.split("\n"))


def compute_sha256(data: bytes) -> str:
    """Compute SHA-256 hex digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def indent_lines(text: str, level: int, size: int = 4) -> str:
    """Indent all non-empty lines by level * size spaces."""
    prefix = " " * (level * size)
    lines = text.split("\n")
    return "\n".join(
        (prefix + line) if line.strip() else line
        for line in lines
    )


def deindent_lines(text: str) -> str:
    """Remove common leading whitespace from all lines."""
    lines = text.split("\n")
    non_empty = [line for line in lines if line.strip()]
    if not non_empty:
        return text
    min_indent = min(count_leading_spaces(line) for line in non_empty)
    if min_indent == 0:
        return text
    return "\n".join(
        line[min_indent:] if line.strip() else line
        for line in lines
    )


def is_blank_line(line: str) -> bool:
    """Check if a line is empty or whitespace-only."""
    return not line.strip()


def count_leading_spaces(line: str) -> int:
    """Count leading space characters (not tabs)."""
    count = 0
    for ch in line:
        if ch == " ":
            count += 1
        elif ch == "\t":
            count += 4
        else:
            break
    return count


def clamp_blank_lines(lines: Sequence[str], max_consecutive: int = 1) -> list[str]:
    """Reduce consecutive blank lines to at most max_consecutive."""
    result: list[str] = []
    blank_count = 0
    for line in lines:
        if is_blank_line(line):
            blank_count += 1
            if blank_count <= max_consecutive:
                result.append(line)
        else:
            blank_count = 0
            result.append(line)
    return result


def align_at_char(
    lines: list[str],
    char: str,
    *,
    min_col: int = 0,
    only_first: bool = True,
) -> list[str]:
    """Align lines at the first occurrence of char.

    Pads with spaces so all occurrences of char start at the same column.
    Lines without char are returned unchanged.
    """
    positions: list[int] = []
    for line in lines:
        pos = line.find(char)
        if pos >= 0:
            positions.append(pos)

    if not positions:
        return lines

    target_col = max(max(positions), min_col)
    result: list[str] = []
    for line in lines:
        pos = line.find(char)
        if pos >= 0 and pos < target_col:
            padding = target_col - pos
            if only_first:
                result.append(line[:pos] + " " * padding + line[pos:])
            else:
                result.append(line[:pos] + " " * padding + line[pos:])
        else:
            result.append(line)
    return result


def safe_read_file(path: str) -> tuple[bytes, str]:
    """Read file bytes and detect encoding.

    Returns (raw_bytes, encoding). Supports UTF-8 BOM and plain UTF-8.
    """
    with open(path, "rb") as f:
        raw = f.read()

    if raw.startswith(b"\xef\xbb\xbf"):
        return raw, "utf-8-sig"
    return raw, "utf-8"


def split_into_groups(
    lines: list[str],
    separator: re.Pattern[str] | None = None,
) -> list[list[str]]:
    """Split lines into groups separated by blank lines or pattern matches."""
    groups: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if is_blank_line(line) or (separator and separator.match(line)):
            if current:
                groups.append(current)
                current = []
            if is_blank_line(line):
                continue
        current.append(line)
    if current:
        groups.append(current)
    return groups
