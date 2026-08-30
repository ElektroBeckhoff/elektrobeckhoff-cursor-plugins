"""Source position and span data structures for exact token and node mapping."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Position:
    """1-based line and column, and 0-based character offset."""
    line: int
    col: int
    offset: int

    def offset_by(self, line_offset: int, col_offset: int = 0, char_offset: int = 0) -> Position:
        new_line = self.line + line_offset
        new_col = self.col + col_offset if self.line == 1 else self.col
        new_char = self.offset + char_offset
        return Position(line=new_line, col=new_col, offset=new_char)

    def __repr__(self) -> str:
        return f"{self.line}:{self.col}"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    """Exact source text range from start position to end position."""
    start: Position
    end: Position

    @property
    def length(self) -> int:
        return self.end.offset - self.start.offset

    def offset_by(self, line_offset: int, col_offset: int = 0, char_offset: int = 0) -> SourceSpan:
        return SourceSpan(
            start=self.start.offset_by(line_offset, col_offset, char_offset),
            end=self.end.offset_by(line_offset, col_offset, char_offset),
        )

    @classmethod
    def from_bounds(
        cls,
        start_line: int,
        start_col: int,
        start_offset: int,
        end_line: int,
        end_col: int,
        end_offset: int,
    ) -> SourceSpan:
        return cls(
            start=Position(line=start_line, col=start_col, offset=start_offset),
            end=Position(line=end_line, col=end_col, offset=end_offset),
        )

    @classmethod
    def merge(cls, first: SourceSpan, last: SourceSpan) -> SourceSpan:
        return cls(start=first.start, end=last.end)

    def contains_offset(self, offset: int) -> bool:
        return self.start.offset <= offset <= self.end.offset

    def __repr__(self) -> str:
        return f"[{self.start.line}:{self.start.col}..{self.end.line}:{self.end.col}]"


def offset_to_line_col(text: str, offset: int) -> tuple[int, int]:
    """Calculate 1-based line and 1-based column for a 0-based character offset in text.

    Correctly handles Unix (LF) and Windows (CRLF) line endings.
    """
    if offset <= 0:
        return 1, 1
    if offset >= len(text):
        offset = len(text)

    # If offset points to '\n' preceded by '\r', it is the second byte of CRLF on the current line
    if offset < len(text) and text[offset] == "\n" and offset > 0 and text[offset - 1] == "\r":
        lines_before = text[: offset - 1].splitlines(keepends=True)
        cur_line = len(lines_before) + 1 if (lines_before and lines_before[-1].endswith(("\n", "\r"))) else max(1, len(lines_before))
        last_line_len = len(lines_before[-1]) if (lines_before and not lines_before[-1].endswith(("\n", "\r"))) else 0
        return cur_line, last_line_len + 2

    lines_before = text[:offset].splitlines(keepends=True)
    if not lines_before:
        return 1, 1
    if lines_before[-1].endswith(("\n", "\r")):
        return len(lines_before) + 1, 1
    return len(lines_before), len(lines_before[-1]) + 1


def line_col_to_offset(text: str, line: int, col: int) -> int:
    """Calculate 0-based character offset for 1-based line and 1-based column in text."""
    if line <= 1:
        return max(0, col - 1)
    lines = text.splitlines(keepends=True)
    if line > len(lines):
        return len(text)
    return sum(len(l) for l in lines[: line - 1]) + max(0, col - 1)

