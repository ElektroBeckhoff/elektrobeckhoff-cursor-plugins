"""Autodocs configuration and result types."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AutodocsConfig:
    """Input/output paths for autodocs generation."""

    input_path: Path
    output_path: Path
    verbose: bool = True


@dataclass
class ParseResult:
    """Structured parse output from a single source file."""

    title: str
    sections: dict[str, str]


@dataclass
class AutodocsReport:
    """Summary returned by process_folder."""

    success: bool
    files_created: list[str] = field(default_factory=list)
    skipped_hidden: int = 0
    errors: int = 0
    duration_sec: float = 0.0
    output: str = ""
    log_lines: list[str] = field(default_factory=list)
    timestamp: str = ""
