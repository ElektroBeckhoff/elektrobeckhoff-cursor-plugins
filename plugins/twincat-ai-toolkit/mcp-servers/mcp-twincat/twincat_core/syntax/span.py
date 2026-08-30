"""Source position and span data structures for exact token and node mapping."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Position:
    """1-based line and column, and 0-based character offset."""
    line: int
    col: int
    offset: int

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
