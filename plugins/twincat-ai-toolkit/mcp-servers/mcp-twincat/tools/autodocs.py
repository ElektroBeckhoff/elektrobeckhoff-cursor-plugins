"""
API documentation generator MCP tools for TwinCAT 3 source libraries.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Any

from autodocs.paths import resolve_output_root
from autodocs.pipeline import process_folder
from .common import _clean_path, _json


def twincat_autodocs(
    input: str,
    output: str = "",
    write_log: bool = False,
    toc_timestamp: bool = False,
) -> str:
    """Generate Markdown API docs from TwinCAT source (.TcPOU/.TcDUT/.TcGVL/.TcIO).

    Writes mirrored .md under <output>/docs/, updates README.md TOC block
    and docs/toc.md. Does not require TcXaeShell.

    Args:
        input: REQUIRED. Solution folder (or repo root) containing TwinCAT sources.
        output: Optional repo/project root. Default: auto-detect from input
            (walk up for README.md / .git, else parent of input). Docs always
            land in <resolved-root>/docs/."""
    input_path = Path(_clean_path(input))
    clean_output = _clean_path(output)

    if not input_path.exists():
        return _json({
            "success": False,
            "error": f"Input path does not exist: {input}",
            "files_created": [],
            "skipped_hidden": 0,
            "errors": 1,
            "duration_sec": 0.0,
            "output": "",
            "repo_root": "",
            "log": "",
        })
    if not input_path.is_dir():
        return _json({
            "success": False,
            "error": f"Input path is not a directory: {input}",
            "files_created": [],
            "skipped_hidden": 0,
            "errors": 1,
            "duration_sec": 0.0,
            "output": "",
            "repo_root": "",
            "log": "",
        })

    try:
        output_path = resolve_output_root(input_path, clean_output or None)
    except Exception as exc:
        return _json({
            "success": False,
            "error": str(exc),
            "files_created": [],
            "skipped_hidden": 0,
            "errors": 1,
            "duration_sec": 0.0,
            "output": "",
            "repo_root": "",
            "log": "",
        })

    output_path.mkdir(parents=True, exist_ok=True)
    repo_root = str(output_path)

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            report = process_folder(
                input_path,
                output_path,
                verbose=True,
                write_log=write_log,
                include_toc_timestamp=toc_timestamp,
            )
    except Exception as exc:
        return _json({
            "success": False,
            "error": str(exc),
            "files_created": [],
            "skipped_hidden": 0,
            "errors": 1,
            "duration_sec": 0.0,
            "output": "",
            "repo_root": repo_root,
            "log": buf.getvalue(),
        })

    log_text = buf.getvalue()
    if report.log_lines:
        log_text = "\n".join(report.log_lines)

    return _json({
        "success": report.success,
        "files_created": report.files_created,
        "skipped_hidden": report.skipped_hidden,
        "errors": report.errors,
        "duration_sec": report.duration_sec,
        "output": report.output,
        "repo_root": repo_root,
        "log": log_text,
    })


def register_tools(mcp: Any) -> None:
    """Register autodocs tool on FastMCP server."""
    mcp.tool()(twincat_autodocs)
