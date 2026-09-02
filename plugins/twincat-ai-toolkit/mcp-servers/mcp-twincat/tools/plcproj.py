"""
PlcProject file verification and synchronization MCP tools for TwinCAT 3.
"""

from __future__ import annotations

import contextlib
import io
from typing import Any

from twincat_plcproj_ops import main as plcproj_main
from .common import _clean_path, _json


def twincat_plcproj_verify(
    input: str,
    skip_folder_sync: bool = False,
    log_level: str = "INFO",
) -> str:
    """Verify that a TwinCAT .plcproj matches the actual files on disk.

    Read-only check. Compares Compile and Folder ItemGroups against the
    project directory tree. Reports missing/extra entries.

    Does NOT require a running TcXaeShell instance. Works on any OS.

    Args:
        input: REQUIRED. Path to a .plcproj file or project root directory.
        skip_folder_sync: Skip Folder ItemGroup verification.
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""
    argv = ["--input", _clean_path(input), "--verify-only"]

    if skip_folder_sync:
        argv.append("--skip-folder-sync")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = plcproj_main(argv)
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 1
    except Exception as exc:
        return _json({
            "success": False,
            "exit_code": 1,
            "output": buf.getvalue(),
            "error": str(exc),
        })

    return _json({
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    })


def twincat_plcproj_sync(
    input: str,
    force: bool = False,
    dry_run: bool = False,
    backup: bool = True,
    skip_folder_sync: bool = False,
    ensure_object_guids: bool = False,
    log_level: str = "INFO",
) -> str:
    """Sync a TwinCAT .plcproj file to match the actual files on disk.

    Rebuilds the Compile and Folder ItemGroup blocks from the project
    directory tree. By default verifies first -- use force=true after
    adding or removing Tc* files on disk.

    IMPORTANT: After syncing the .plcproj, tell the user that XAE must
    reload before the next compile. Do NOT call twincat_open /
    twincat_reload / twincat_check_all_objects unless the user explicitly
    asks to validate or compile thoroughly.

    Does NOT require a running TcXaeShell instance. Works on any OS.

    Args:
        input: REQUIRED. Path to a .plcproj file or project root directory.
        force: Skip verify and always rebuild from disk.
        dry_run: SAFE. Preview only, no files written.
        backup: Create timestamped backup before writing (recommended).
        skip_folder_sync: Skip Folder ItemGroup sync.
        ensure_object_guids: Repair missing/duplicate GUIDs in Tc* files.
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""
    argv = ["--input", _clean_path(input)]

    if force:
        argv.append("--force")
    if dry_run:
        argv.append("--dry-run")
    if not backup:
        argv.append("--no-backup")
    if skip_folder_sync:
        argv.append("--skip-folder-sync")
    if ensure_object_guids:
        argv.append("--ensure-object-guids")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = plcproj_main(argv)
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 1
    except Exception as exc:
        return _json({
            "success": False,
            "exit_code": 1,
            "output": buf.getvalue(),
            "error": str(exc),
        })

    return _json({
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    })


def register_tools(mcp: Any) -> None:
    """Register plcproj tools on FastMCP server."""
    mcp.tool()(twincat_plcproj_verify)
    mcp.tool()(twincat_plcproj_sync)
