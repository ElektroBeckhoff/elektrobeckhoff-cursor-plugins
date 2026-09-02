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


from bisect import bisect_right
from functools import lru_cache


@lru_cache(maxsize=256)
def _get_line_starts(text: str) -> tuple[int, ...]:
    starts = [0]
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == "\r":
            if i + 1 < n and text[i + 1] == "\n":
                i += 2
            else:
                i += 1
            starts.append(i)
        elif ch == "\n":
            i += 1
            starts.append(i)
        else:
            i += 1
    return tuple(starts)


def offset_to_line_col(text: str, offset: int) -> tuple[int, int]:
    """Calculate 1-based line and 1-based column for a 0-based character offset in text.

    Correctly handles Unix (LF) and Windows (CRLF) line endings.
    """
    if offset <= 0:
        return 1, 1
    if offset >= len(text):
        offset = len(text)

    starts = _get_line_starts(text)
    line_idx = bisect_right(starts, offset) - 1
    return line_idx + 1, offset - starts[line_idx] + 1


def line_col_to_offset(text: str, line: int, col: int) -> int:
    """Calculate 0-based character offset for 1-based line and 1-based column in text."""
    if line <= 1:
        return max(0, col - 1)
    starts = _get_line_starts(text)
    if line > len(starts):
        return len(text)
    line_start = starts[line - 1]
    return min(len(text), line_start + max(0, col - 1))

