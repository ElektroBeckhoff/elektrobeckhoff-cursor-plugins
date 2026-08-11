"""Uniform MCP error shapes for TwinCAT tools (confirm, export guards, …)."""
from __future__ import annotations

from typing import Any, Optional


def confirm_refused(
    operation: str,
    *,
    example_args: Optional[dict[str, Any]] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Standard refusal when confirm=true is required but missing."""
    op = (operation or "operation").strip()
    example = dict(example_args or {})
    example.setdefault("confirm", True)
    data: dict[str, Any] = {
        "success": False,
        "ok": False,
        "error_code": "confirm_required",
        "required_args": ["confirm"],
        "example_next_call": {"tool": op, **example},
        "error": f"Refused: set confirm=true to run {op}",
        "message": f"Refused: set confirm=true to run {op}",
    }
    if extra:
        data.update(extra)
    return data


def error_result(
    error_code: str,
    message: str,
    *,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "success": False,
        "ok": False,
        "error_code": error_code,
        "error": message,
        "message": message,
    }
    if extra:
        data.update(extra)
    return data
