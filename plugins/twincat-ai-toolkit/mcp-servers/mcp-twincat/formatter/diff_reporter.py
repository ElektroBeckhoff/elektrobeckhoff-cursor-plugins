"""Diff reporter for dry-run / verbose mode.

Generates unified diffs and summary reports.
"""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Sequence

from formatter.types import FormatResult, BatchResult


def generate_diff(path: str, original: str, formatted: str, *, context: int = 3) -> str:
    """Generate unified diff between original and formatted content."""
    original_lines = original.splitlines(keepends=True)
    formatted_lines = formatted.splitlines(keepends=True)

    filename = Path(path).name
    diff = difflib.unified_diff(
        original_lines,
        formatted_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        n=context,
    )
    return "".join(diff)


def format_file_status(result: FormatResult, *, verbose: bool = False) -> str:
    """Format a single file result for console output."""
    name = Path(result.path).name

    if result.errors:
        errors = "; ".join(result.errors)
        return f"formatter: {name} ... ERROR: {errors}"

    if not result.success:
        return f"formatter: {name} ... FAILED"

    if result.changed:
        return f"formatter: {name} ... formatted"

    if verbose:
        return f"formatter: {name} ... unchanged"

    return ""


def format_summary(batch: BatchResult) -> str:
    """Generate summary line for batch processing."""
    parts: list[str] = []
    parts.append(f"{batch.total} files checked")

    if batch.formatted > 0:
        parts.append(f"{batch.formatted} formatted")
    if batch.errors > 0:
        parts.append(f"{batch.errors} errors")
    if batch.unchanged > 0:
        parts.append(f"{batch.unchanged} unchanged")

    return f"Summary: {', '.join(parts)}"


def format_validation_report(batch: BatchResult) -> str:
    """Format validation issues as a readable report."""
    if not batch.validation_issues:
        return ""

    lines: list[str] = []
    lines.append(f"\nValidation: {len(batch.validation_issues)} issues found\n")

    for issue in sorted(batch.validation_issues, key=lambda i: (i.file, i.line)):
        prefix = "ERROR" if issue.level == "error" else "WARN"
        file_name = Path(issue.file).name
        lines.append(f"  [{prefix}] {file_name}:{issue.line} [{issue.rule}] {issue.message}")

    return "\n".join(lines)
