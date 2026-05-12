"""
TwinCAT MCP Server for Cursor IDE.

Exposes TcXaeShell build automation, FBD/FUP-to-ST migration, and
CFC-to-ST migration as MCP tools that Cursor can call directly:
status check, solution open, CheckAllObjects, build, error retrieval,
library export, close, FBD-to-ST migration, and CFC-to-ST migration.

Transport: stdio  (Cursor starts this process as a child)
COM:       All TcXaeShell interaction runs on a dedicated STA thread
           managed by twincat_automation_interface.TcAutomationInterface (TE1000).
"""

import io
import os
import re
import sys
import glob
import json
import logging
import contextlib
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Union
from dataclasses import asdict

_server_dir = os.path.dirname(os.path.abspath(__file__))
for _subdir in ("migrator", "automation_interface", "plcproj"):
    _p = os.path.join(_server_dir, _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# stdout is the MCP JSON-RPC wire -- all logging goes to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("twincat-mcp")

from mcp.server.fastmcp import FastMCP
from twincat_automation_interface import TcAutomationInterface, HAS_WIN32
from twincat_fbd_to_st_migrator import main as fup_main
from twincat_cfc_to_st_migrator import main as cfc_main
from twincat_plcproj_ops import main as plcproj_main, read_project_info
from twincat_unified_migrator import main as unified_main

mcp = FastMCP("TwinCAT")

_bridge: Optional[TcAutomationInterface] = None


def _get_bridge() -> TcAutomationInterface:
    global _bridge
    if _bridge is None:
        _bridge = TcAutomationInterface()
    return _bridge


def _json(obj) -> str:
    if hasattr(obj, "__dataclass_fields__"):
        return json.dumps(asdict(obj), indent=2, ensure_ascii=False)
    return json.dumps(obj, indent=2, ensure_ascii=False)


# ================================================================
#  twincat_plcproj_info  (pure XML -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
def twincat_plcproj_info(plcproj_path: str = "") -> str:
    """Read TwinCAT PLC project metadata from .plcproj XML.

    Returns Title, Version, Company, Name, Released.
    Does NOT require a running TcXaeShell instance.
    Leave plcproj_path empty for auto-detection."""

    if not plcproj_path:
        plcproj_path = _auto_detect_plcproj()
        if not plcproj_path:
            return _json({"error": "No .plcproj found. Provide plcproj_path."})

    try:
        return _json(read_project_info(plcproj_path))
    except Exception as exc:
        return _json({"error": str(exc)})


# ================================================================
#  twincat_status
# ================================================================

@mcp.tool()
def twincat_status() -> str:
    """Check whether TcXaeShell (TwinCAT XAE) is installed and running.

    Returns availability info without opening anything."""

    if not HAS_WIN32:
        return _json({
            "xae_available": False,
            "running_instance": False,
            "message": "pywin32 not installed (Windows + TwinCAT XAE required)",
        })
    try:
        return _json(_get_bridge().get_status())
    except Exception as exc:
        return _json({"error": str(exc)})


# ================================================================
#  twincat_open
# ================================================================

@mcp.tool()
def twincat_open(
    path: str = "",
    plcproj_path: str = "",
    sln_path: str = "",
    proj_name: str = "",
    timeout_seconds: int = 180,
) -> str:
    """Open a TwinCAT solution in XAE and locate the PLC project.

    Accepts a single 'path' parameter that can be:
      - A .plcproj file  (opens directly)
      - A .sln file      (resolves via .tsproj/.xti XML to .plcproj)
      - A folder          (scans for .sln or .plcproj automatically)

    If the solution contains multiple PLC projects, returns an error
    with the full list of available projects and their .plcproj paths.

    Legacy parameters (plcproj_path, sln_path, proj_name) are still
    supported for backward compatibility but 'path' is preferred.

    Behaviour:
      - If XAE is running with the correct solution: reuse it.
      - If XAE is running with a different solution: start a
        separate XAE instance (the user's solution stays open).
      - If XAE is running with no solution: open the requested one.
      - If XAE is not running: start a new instance."""

    if path:
        resolved = _resolve_path(path)
        if isinstance(resolved, dict):
            return _json(resolved)
        plcproj_path = resolved

    if not path and not plcproj_path and not sln_path:
        return _json({
            "success": False,
            "error": "No path provided. Pass path=, plcproj_path=, or sln_path=.",
        })

    if not proj_name and plcproj_path:
        proj_name = _read_proj_name(plcproj_path)

    bridge = _get_bridge()
    bridge._plcproj_file_path = plcproj_path or None

    try:
        return _json(bridge.open_solution(
            sln_path=sln_path or None,
            plcproj_path=plcproj_path or None,
            proj_name=proj_name or None,
            timeout_s=timeout_seconds,
        ))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_reload
# ================================================================

@mcp.tool()
def twincat_reload(timeout_seconds: int = 180) -> str:
    """Reload the TwinCAT solution from disk (close without save, reopen).

    NOT needed after editing .TcPOU / .TcDUT / .TcGVL content --
    twincat_check_all_objects re-reads those from disk automatically.

    REQUIRED after changes to project structure files:
      - .plcproj  (added/removed POUs, version changes, references)
      - .tsproj   (project configuration changes)
      - .sln      (solution-level changes)

    Also useful when XAE is in an inconsistent state, e.g. after
    a failed build left stale data in memory.

    Takes ~5-10 seconds (polls for readiness instead of fixed timer).
    Requires twincat_open to have been called at least once."""

    try:
        return _json(_get_bridge().reload_solution(timeout_s=timeout_seconds))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_check_all_objects
# ================================================================

@mcp.tool()
def twincat_check_all_objects() -> str:
    """Run CheckAllObjects on the open PLC project.

    This is the PRIMARY validation tool for library projects.
    It re-reads files from disk and compiles ALL objects -- not just
    those referenced from MAIN.  A normal Build would miss errors
    in unreferenced POUs.

    Returns structured JSON with compile result AND all errors,
    warnings, and infos -- no separate twincat_get_output_log call needed.

    Response fields: success, method, error_count, warning_count,
    errors[], warnings[], infos[], message.
    Always inspect warning_count and warnings[] even when success=true.

    No twincat_reload needed -- CheckAllObjects reads from disk.
    Requires twincat_open to have been called."""

    try:
        return _json(_get_bridge().check_all_objects())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_build
# ================================================================

@mcp.tool()
def twincat_build(timeout_seconds: int = 180) -> str:
    """Rebuild the TwinCAT solution.

    Detects PLC compile success via _CompileInfo timestamps
    combined with SolutionBuild.LastBuildInfo.  Returns structured
    success/failure info AND all errors, warnings, and infos --
    no separate twincat_get_output_log call needed.

    Response fields: success, elapsed_seconds, build_state,
    last_build_info, compile_info_updated, error_count, errors[],
    warnings[], infos[], message.

    Requires twincat_open to have been called."""

    try:
        return _json(_get_bridge().build(timeout_s=timeout_seconds))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_get_output_log
# ================================================================

@mcp.tool()
def twincat_get_output_log() -> str:
    """Read the full build / check output from XAE.

    NOTE: twincat_build and twincat_check_all_objects now include
    errors, warnings, and infos automatically.  This tool is only
    needed if you want to re-read the output log independently.

    Returns structured JSON with three severity lists:
      - errors:   compile errors (with file_name, line, description)
      - warnings: compiler warnings (with file_name, line, description)
      - infos:    build messages (memory sizes, phases, summary)

    Each entry has: severity, description, file_name, line, project.
    'count' is the number of ERRORS only."""

    try:
        return _json(_get_bridge().get_output_log())
    except Exception as exc:
        return _json({"count": 0, "errors": [], "warnings": [], "infos": [], "error": str(exc)})


# ================================================================
#  twincat_export_library
# ================================================================

@mcp.tool()
def twincat_export_library(
    output_dir: str = "",
    plcproj_path: str = "",
) -> str:
    """Export the PLC project as .library and .compiled-library.

    The .library is also installed into the local library repository.
    Default output: Versions/<ProjectVersion>/ in the repository root.

    Requires a successful build first."""

    if not plcproj_path:
        plcproj_path = _auto_detect_plcproj()

    info = _read_plcproj_meta(plcproj_path)
    title = info.get("title", "Unknown")
    version = info.get("version", "0.0.0.0")

    if not output_dir:
        repo = _find_repo_root()
        output_dir = os.path.join(repo or os.getcwd(), "Versions", version)

    try:
        return _json(
            _get_bridge().export_library(output_dir, title, version)
        )
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_close
# ================================================================

@mcp.tool()
def twincat_close(force_quit: bool = False) -> str:
    """Release the MCP session and clean up.

    Only closes what WE opened:
      - If MCP started a new XAE instance: quit it.
      - If MCP opened a solution into an existing empty XAE: close
        the solution, leave XAE running.
      - If MCP just attached to the user's session: detach, touch
        nothing.

    The user's own XAE instances and solutions are never affected.

    Set force_quit=true to always terminate XAE (use with caution).

    Resets internal state so the next twincat_open starts fresh."""

    global _bridge
    try:
        result = _get_bridge().close(force_quit=force_quit)
        _bridge = None
        return _json(result)
    except Exception as exc:
        _bridge = None
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_fup_migrate  (pure Python -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
def twincat_fup_migrate(
    input: str,
    output: str = "",
    recursive: bool = False,
    backup: bool = True,
    force: bool = False,
    swap: bool = False,
    dry_run: bool = False,
    analyze_only: bool = False,
    log: bool = True,
    report: bool = True,
    config: str = "",
    encoding: str = "utf-8",
    strict: bool = False,
    preserve_ids: bool = True,
    preserve_comments: bool = True,
    mark_todo: bool = True,
    fail_on_unclear: bool = True,
    log_level: str = "INFO",
) -> str:
    """Convert TwinCAT 3 FBD/FUP .TcPOU implementations to Structured Text.

    Parses NWL XML, generates functionally identical ST code, preserves
    declarations, comments, attributes, and GUIDs.  Supports single
    files and recursive folder processing with backup, swap, force,
    dry-run, and analyze-only modes.

    ALWAYS start with dry_run=true or analyze_only=true before actual
    migration.

    Does NOT require a running TcXaeShell instance.  Works on any OS.

    Args:
        input: REQUIRED. Path to a .TcPOU/.TcGVL/.TcDUT file or folder.
        output: Explicit output path. Empty = auto (default/swap mode).
        recursive: Recurse into subfolders when input is a directory.
        backup: Create backup before modification (recommended).
        force: DESTRUCTIVE. Overwrite original in-place (GUIDs kept).
        swap: Backup original, write ST to original path.
        dry_run: SAFE. Preview only, zero files written.
        analyze_only: SAFE. Inspect FBD structure, no ST generation.
        log: Write migration log file.
        report: Write migration report file.
        config: Path to JSON config file (CLI params take precedence).
        encoding: File encoding (auto-fallback: utf-8-sig, latin-1).
        strict: Abort on any TODO marker. Blocks force without backup.
        preserve_ids: Keep original GUIDs in force mode.
        preserve_comments: Keep FBD comments as ST header blocks.
        mark_todo: Wrap untranslatable logic in TODO comment blocks.
        fail_on_unclear: Warn on TODO markers (abort with strict=true).
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""

    argv = ["--input", input]

    if output:
        argv.extend(["--output", output])
    if recursive:
        argv.append("--recursive")
    if not backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")
    if swap:
        argv.append("--swap")
    if dry_run:
        argv.append("--dry-run")
    if analyze_only:
        argv.append("--analyze-only")
    if not log:
        argv.append("--no-log")
    if not report:
        argv.append("--no-report")
    if config:
        argv.extend(["--config", config])
    if encoding != "utf-8":
        argv.extend(["--encoding", encoding])
    if strict:
        argv.append("--strict")
    if not mark_todo:
        argv.append("--no-mark-todo")
    if not fail_on_unclear:
        argv.append("--no-fail-on-unclear")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = fup_main(argv)
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


# ================================================================
#  twincat_cfc_migrate  (pure Python -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
def twincat_cfc_migrate(
    input: str,
    output: str = "",
    recursive: bool = False,
    backup: bool = True,
    force: bool = False,
    swap: bool = False,
    dry_run: bool = False,
    analyze_only: bool = False,
    log: bool = True,
    report: bool = True,
    config: str = "",
    encoding: str = "utf-8",
    strict: bool = False,
    preserve_ids: bool = True,
    preserve_comments: bool = True,
    mark_todo: bool = True,
    fail_on_unclear: bool = True,
    log_level: str = "INFO",
) -> str:
    """Convert TwinCAT 3 CFC .TcPOU implementations to Structured Text.

    Parses CFC XML (CFCInputElement, CFCOutputElement, CFCBoxElement),
    resolves execution order from XML serialization, generates
    functionally equivalent ST code, preserves declarations, comments,
    attributes, and GUIDs.  Supports single files and recursive folder
    processing with backup, swap, force, dry-run, and analyze-only modes.

    ALWAYS start with dry_run=true or analyze_only=true before actual
    migration.

    Does NOT require a running TcXaeShell instance.  Works on any OS.

    Args:
        input: REQUIRED. Path to a .TcPOU file or folder containing CFC POUs.
        output: Explicit output path. Empty = auto (default/swap mode).
        recursive: Recurse into subfolders when input is a directory.
        backup: Create backup before modification (recommended).
        force: DESTRUCTIVE. Overwrite original in-place (GUIDs kept).
        swap: Backup original, write ST to original path.
        dry_run: SAFE. Preview only, zero files written.
        analyze_only: SAFE. Inspect CFC structure, no ST generation.
        log: Write migration log file.
        report: Write migration report file.
        config: Path to JSON config file (CLI params take precedence).
        encoding: File encoding (auto-fallback: utf-8-sig, latin-1).
        strict: Abort on any TODO marker. Blocks force without backup.
        preserve_ids: Keep original GUIDs in force mode.
        preserve_comments: Keep CFC comments as ST header blocks.
        mark_todo: Wrap untranslatable logic in TODO comment blocks.
        fail_on_unclear: Warn on TODO markers (abort with strict=true).
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""

    argv = ["--input", input]

    if output:
        argv.extend(["--output", output])
    if recursive:
        argv.append("--recursive")
    if not backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")
    if swap:
        argv.append("--swap")
    if dry_run:
        argv.append("--dry-run")
    if analyze_only:
        argv.append("--analyze-only")
    if not log:
        argv.append("--no-log")
    if not report:
        argv.append("--no-report")
    if config:
        argv.extend(["--config", config])
    if encoding != "utf-8":
        argv.extend(["--encoding", encoding])
    if strict:
        argv.append("--strict")
    if not mark_todo:
        argv.append("--no-mark-todo")
    if not fail_on_unclear:
        argv.append("--no-fail-on-unclear")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = cfc_main(argv)
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


# ================================================================
#  twincat_migrate  (pure Python -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
def twincat_migrate(
    input: str,
    output: str = "",
    recursive: bool = False,
    backup: bool = True,
    force: bool = False,
    swap: bool = False,
    dry_run: bool = False,
    analyze_only: bool = False,
    log: bool = True,
    report: bool = True,
    config: str = "",
    encoding: str = "utf-8",
    strict: bool = False,
    preserve_ids: bool = True,
    preserve_comments: bool = True,
    mark_todo: bool = True,
    fail_on_unclear: bool = True,
    log_level: str = "INFO",
) -> str:
    """Convert TwinCAT 3 FBD/FUP and CFC implementations to Structured Text
    in a single pass.

    Auto-detects the implementation type (NWL / CFC) per file and routes
    to the appropriate converter.  Produces a single combined report and
    shared backup directory.  Files that are already ST or use unsupported
    languages (SFC, IL, LD) are skipped gracefully.

    ALWAYS start with dry_run=true or analyze_only=true before actual
    migration.

    Does NOT require a running TcXaeShell instance.  Works on any OS.

    Args:
        input: REQUIRED. Path to a .TcPOU file or folder.
        output: Explicit output path. Empty = auto (default/swap mode).
        recursive: Recurse into subfolders when input is a directory.
        backup: Create backup before modification (recommended).
        force: DESTRUCTIVE. Overwrite original in-place (GUIDs kept).
        swap: Backup original, write ST to original path.
        dry_run: SAFE. Preview only, zero files written.
        analyze_only: SAFE. Inspect structure, no ST generation.
        log: Write migration log file.
        report: Write migration report file.
        config: Path to JSON config file (CLI params take precedence).
        encoding: File encoding (auto-fallback: utf-8-sig, latin-1).
        strict: Abort on any TODO marker. Blocks force without backup.
        preserve_ids: Keep original GUIDs in force mode.
        preserve_comments: Keep comments as ST header blocks.
        mark_todo: Wrap untranslatable logic in TODO comment blocks.
        fail_on_unclear: Warn on TODO markers (abort with strict=true).
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""

    argv = ["--input", input]

    if output:
        argv.extend(["--output", output])
    if recursive:
        argv.append("--recursive")
    if not backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")
    if swap:
        argv.append("--swap")
    if dry_run:
        argv.append("--dry-run")
    if analyze_only:
        argv.append("--analyze-only")
    if not log:
        argv.append("--no-log")
    if not report:
        argv.append("--no-report")
    if config:
        argv.extend(["--config", config])
    if encoding != "utf-8":
        argv.extend(["--encoding", encoding])
    if strict:
        argv.append("--strict")
    if not mark_todo:
        argv.append("--no-mark-todo")
    if not fail_on_unclear:
        argv.append("--no-fail-on-unclear")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = unified_main(argv)
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


# ================================================================
#  twincat_plcproj_verify  (pure Python -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
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

    argv = ["--input", input, "--verify-only"]

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


# ================================================================
#  twincat_plcproj_sync  (pure Python -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
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

    IMPORTANT: After syncing the .plcproj, call twincat_reload() before
    twincat_check_all_objects() because .plcproj is a structural file.

    Does NOT require a running TcXaeShell instance. Works on any OS.

    Args:
        input: REQUIRED. Path to a .plcproj file or project root directory.
        force: Skip verify and always rebuild from disk.
        dry_run: SAFE. Preview only, no files written.
        backup: Create timestamped backup before writing (recommended).
        skip_folder_sync: Skip Folder ItemGroup sync.
        ensure_object_guids: Repair missing/duplicate GUIDs in Tc* files.
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""

    argv = ["--input", input]

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


# ================================================================
#  Path resolver  (.sln / .tsproj / .xti / .plcproj / folder)
# ================================================================

_SLN_PROJECT_RE = re.compile(
    r'^Project\("[^"]*"\)\s*=\s*"[^"]*"\s*,\s*"([^"]+\.tsproj)"',
    re.MULTILINE,
)

_EXCLUDES_LOWER = {"samples", "samples_", "versions", "_libraries", ".git", "node_modules"}


def _resolve_path(path: str) -> Union[str, dict]:
    """Resolve a user-supplied path to an absolute .plcproj path.

    Accepts:
      - A .plcproj file   → returned as-is (normalised)
      - A .sln file       → XML chain: .sln → .tsproj → .xti → .plcproj
      - A directory        → scan for .sln first, then .plcproj

    Returns either a plcproj path (str) or an error dict.
    """
    path = os.path.abspath(path)
    lower = path.lower()

    if lower.endswith(".plcproj"):
        if not os.path.isfile(path):
            return {"success": False, "error": f"File not found: {path}"}
        return path

    if lower.endswith(".sln"):
        if not os.path.isfile(path):
            return {"success": False, "error": f"File not found: {path}"}
        return _resolve_sln(path)

    if os.path.isdir(path):
        return _resolve_directory(path)

    return {"success": False, "error": f"Path is not a .plcproj, .sln, or directory: {path}"}


def _resolve_sln(sln_path: str) -> Union[str, dict]:
    """Resolve .sln → .tsproj → .xti files → list of .plcproj entries."""
    sln_dir = os.path.dirname(sln_path)

    try:
        with open(sln_path, "r", encoding="utf-8-sig") as f:
            sln_text = f.read()
    except Exception as exc:
        return {"success": False, "error": f"Cannot read .sln: {exc}"}

    tsproj_matches = _SLN_PROJECT_RE.findall(sln_text)
    if not tsproj_matches:
        return {"success": False, "error": f"No .tsproj reference found in {sln_path}"}

    tsproj_path = os.path.normpath(os.path.join(sln_dir, tsproj_matches[0]))
    if not os.path.isfile(tsproj_path):
        return {"success": False, "error": f".tsproj not found: {tsproj_path}"}

    return _resolve_tsproj(tsproj_path, sln_path)


def _resolve_tsproj(tsproj_path: str, sln_path: str) -> Union[str, dict]:
    """Parse .tsproj XML → read <Plc><Project File="*.xti"/> → resolve each .xti."""
    tsproj_dir = os.path.dirname(tsproj_path)
    config_plc_dir = os.path.join(tsproj_dir, "_Config", "PLC")

    try:
        tree = ET.parse(tsproj_path)
        root = tree.getroot()
    except Exception as exc:
        return {"success": False, "error": f"Cannot parse .tsproj: {exc}"}

    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
    plc_node = root.find(f".//{ns}Plc") if ns else root.find(".//Plc")
    if plc_node is None:
        plc_node = root.find(f".//{ns}Project/{ns}Plc") if ns else root.find(".//Project/Plc")
    if plc_node is None:
        return {"success": False, "error": f"No <Plc> section found in {tsproj_path}"}

    projects: List[Dict[str, str]] = []
    for proj_elem in plc_node.findall(f"{ns}Project" if ns else "Project"):
        xti_file = proj_elem.get("File", "")
        if not xti_file:
            continue
        xti_path = os.path.normpath(os.path.join(config_plc_dir, xti_file))
        if not os.path.isfile(xti_path):
            continue
        info = _parse_xti(xti_path)
        if info:
            projects.append(info)

    if len(projects) == 0:
        return {"success": False, "error": f"No PLC projects found in {tsproj_path}"}

    if len(projects) == 1:
        return projects[0]["plcproj_path"]

    return {
        "success": False,
        "error": "multiple_plc_projects",
        "message": (
            f"Found {len(projects)} PLC projects in solution. "
            f"Pass the exact path to the desired .plcproj file."
        ),
        "solution": sln_path,
        "available_projects": projects,
    }


def _parse_xti(xti_path: str) -> Optional[Dict[str, str]]:
    """Parse a .xti file → extract Name and resolve PrjFilePath to absolute."""
    try:
        tree = ET.parse(xti_path)
        root = tree.getroot()
    except Exception:
        return None

    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
    proj = root.find(f"{ns}Project") if ns else root.find("Project")
    if proj is None:
        return None

    name = proj.get("Name", "")
    prj_file_path = proj.get("PrjFilePath", "")
    if not prj_file_path:
        return None

    xti_dir = os.path.dirname(xti_path)
    abs_plcproj = os.path.normpath(os.path.join(xti_dir, prj_file_path))

    if not os.path.isfile(abs_plcproj):
        return None

    return {"name": name, "plcproj_path": abs_plcproj}


def _resolve_directory(dir_path: str) -> Union[str, dict]:
    """Resolve a directory by scanning for .sln, then falling back to .plcproj."""
    sln_files = glob.glob(os.path.join(dir_path, "*.sln"))
    if len(sln_files) == 1:
        return _resolve_sln(sln_files[0])
    if len(sln_files) > 1:
        return {
            "success": False,
            "error": "multiple_solutions",
            "message": (
                f"Found {len(sln_files)} .sln files in {dir_path}. "
                f"Pass the exact .sln or .plcproj path."
            ),
            "available_solutions": [os.path.normpath(s) for s in sorted(sln_files)],
        }

    plcproj_files = _scan_plcproj_in_dir(dir_path)
    if len(plcproj_files) == 1:
        return plcproj_files[0]
    if len(plcproj_files) > 1:
        projects = []
        for p in plcproj_files:
            name = _read_proj_name(p) or os.path.splitext(os.path.basename(p))[0]
            projects.append({"name": name, "plcproj_path": p})
        return {
            "success": False,
            "error": "multiple_plc_projects",
            "message": (
                f"Found {len(plcproj_files)} .plcproj files in {dir_path}. "
                f"Pass the exact .plcproj path."
            ),
            "available_projects": projects,
        }

    return {"success": False, "error": f"No .sln or .plcproj found in {dir_path}"}


def _scan_plcproj_in_dir(dir_path: str, max_depth: int = 5) -> List[str]:
    """Walk a directory tree and collect .plcproj files (excluding known noise)."""
    results = []
    for dirpath, dirnames, filenames in os.walk(dir_path):
        parts_lower = {p.lower() for p in dirpath.split(os.sep)}
        if parts_lower & _EXCLUDES_LOWER:
            dirnames.clear()
            continue
        depth = dirpath.replace(dir_path, "").count(os.sep)
        if depth > max_depth:
            dirnames.clear()
            continue
        for f in filenames:
            if f.lower().endswith(".plcproj"):
                results.append(os.path.normpath(os.path.join(dirpath, f)))
    return results


# ================================================================
#  Internal helpers
# ================================================================

def _auto_detect_plcproj() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(script_dir))

    excludes = {"samples", "versions", "_libraries", ".git", "node_modules"}

    for root_dir in (repo_root, os.getcwd()):
        if not os.path.isdir(root_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(root_dir):
            parts = set(p.lower() for p in dirpath.split(os.sep))
            if parts & excludes:
                dirnames.clear()
                continue
            depth = dirpath.replace(root_dir, "").count(os.sep)
            if depth > 5:
                dirnames.clear()
                continue
            for f in filenames:
                if f.endswith(".plcproj"):
                    return os.path.join(dirpath, f)
    return ""


def _read_proj_name(plcproj_path: str) -> str:
    try:
        return read_project_info(plcproj_path).get("name", "")
    except Exception:
        return ""


def _read_plcproj_meta(plcproj_path: str) -> dict:
    if not plcproj_path or not os.path.isfile(plcproj_path):
        return {}
    try:
        info = read_project_info(plcproj_path)
        return {k: info[k] for k in ("title", "version", "company", "name")}
    except Exception:
        return {}


def _find_repo_root() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.dirname(os.path.dirname(script_dir))
    if os.path.isdir(os.path.join(candidate, ".git")):
        return candidate
    d = os.getcwd()
    for _ in range(5):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return ""


# ================================================================
#  Entry point
# ================================================================

if __name__ == "__main__":
    mcp.run()
