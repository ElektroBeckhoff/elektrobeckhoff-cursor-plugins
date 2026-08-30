"""Diagnostics and error reporting structures for ST parsing and linting."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Optional

from .span import SourceSpan


class DiagnosticSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


@dataclass(frozen=True, slots=True)
class SyntaxDiagnostic:
    """Represents a syntax, type, or parsing diagnostic with source position."""
    message: str
    span: SourceSpan
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    code: Optional[str] = None

    def __repr__(self) -> str:
        return f"{self.severity.upper()}: {self.message} at {self.span}"
