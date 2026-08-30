"""Data types for the TwinCAT3 ST Formatter.

All dataclasses, enums, and type aliases used across the formatter package.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum
from typing import Literal

from formatter.constants import TokenType


# ---------------------------------------------------------------------------
# Region / Scope Filtering
# ---------------------------------------------------------------------------


class FormatRegion(StrEnum):
    """Which region(s) of a TwinCAT file to format."""

    ALL = "all"
    DECLARATION = "declaration"
    IMPLEMENTATION = "implementation"


class MemberFilter(StrEnum):
    """Which members to include when formatting."""

    ALL = "all"
    ALL_METHODS = "all_methods"
    ALL_ACTIONS = "all_actions"
    ALL_PROPERTIES = "all_properties"


@dataclass(frozen=True, slots=True)
class FormatScope:
    """Scope specification for partial formatting.

    Determines which parts of a TwinCAT file to format.
    Default: format everything.
    """

    region: FormatRegion = FormatRegion.ALL
    member_filter: MemberFilter | None = None
    member_name: str = ""  # specific member name (overrides member_filter)


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Token:
    """Single lexer token with position information."""

    type: TokenType
    value: str
    line: int
    col: int


# ---------------------------------------------------------------------------
# Format Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FormatResult:
    """Result of formatting a single file."""

    path: str
    success: bool
    changed: bool
    original_hash: str = ""
    formatted_hash: str = ""
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    diff: str = ""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Single validation finding."""

    level: Literal["error", "warning"]
    file: str
    line: int
    message: str
    rule: str


@dataclass(slots=True)
class WriteSummary:
    """Result of a safe file write operation."""

    path: str
    written: bool = False
    backup_path: str = ""
    original_hash: str = ""
    new_hash: str = ""
    error: str = ""


# ---------------------------------------------------------------------------
# Exit Codes (CLI)
# ---------------------------------------------------------------------------


class ExitCode(IntEnum):
    SUCCESS = 0
    FILES_CHANGED = 1
    ERROR = 2
    VALIDATION_ERROR = 3
    CONFIG_ERROR = 4


# ---------------------------------------------------------------------------
# Batch Results
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BatchResult:
    """Aggregated result from processing multiple files."""

    total: int = 0
    formatted: int = 0
    unchanged: int = 0
    errors: int = 0
    validation_issues: list[ValidationIssue] = field(default_factory=list)
    results: list[FormatResult] = field(default_factory=list)
