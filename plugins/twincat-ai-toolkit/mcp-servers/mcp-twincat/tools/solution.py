"""
Solution, build automation, STweep formatting, and library export MCP tools for TwinCAT 3.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

from twincat_automation_interface import TcAutomationInterface, HAS_WIN32
import extension_ops
from .common import (
    _as_dict,
    _clean_path,
    _find_repo_root,
    _json,
    _read_plcproj_meta,
    _read_proj_name,
    _resolve_path,
    _resolve_plcproj_path,
)

log = logging.getLogger("twincat-mcp.solution")

_bridge: Optional[TcAutomationInterface] = None


def _get_bridge() -> TcAutomationInterface:
    global _bridge
    import sys
    srv = sys.modules.get("server")
    if srv and "_get_bridge" in srv.__dict__ and srv._get_bridge is not _get_bridge:
        return srv._get_bridge()
    if _bridge is None:
        _bridge = TcAutomationInterface()
    return _bridge


def _active_resolve_path(path: str):
    import sys
    srv = sys.modules.get("server")
    if srv and "_resolve_path" in srv.__dict__ and srv._resolve_path is not _resolve_path:
        return srv._resolve_path(path)
    return _resolve_path(path)


def _active_read_proj_name(plcproj_path: str) -> str:
    import sys
    srv = sys.modules.get("server")
    if srv and "_read_proj_name" in srv.__dict__ and srv._read_proj_name is not _read_proj_name:
        return srv._read_proj_name(plcproj_path)
    return _read_proj_name(plcproj_path)


def twincat_status() -> str:
    """Diagnose TcXaeShell / MCP session health and VS Code extension status without opening a solution.

    Reports XAE install/running state, per-instance solution paths and
    COM-busy flags (modal dialog), visible TcXaeShell message boxes,
    MCP session binding, SilentMode, recent auto-dismissed dialogs,
    SysManager error text, twincat_runtime_started, target_net_id,
    active log file path, and VS Code / Cursor extension installation status.

    If ``dte_busy`` or ``blocking_dialogs`` is set: READ those fields.
    For ``auto_dismissable=true`` reload prompts call
    ``twincat_dismiss_safe_dialogs`` once, then retry the original tool
    once. Do not narrate manual XAE clicking. Non-auto-dismissable dialogs
    -> stop and tell the user the dialog text.
    """
    ext_status = extension_ops.get_extension_status()
    try:
        from mcp_version import MCP_SERVER_VERSION
    except Exception:
        MCP_SERVER_VERSION = "1.0.0"
    try:
        from mcp_logging import get_log_path
        log_path = get_log_path()
    except Exception:
        log_path = ""

    if not HAS_WIN32:
        return _json({
            "xae_available": False,
            "running_instance": False,
            "instances": [],
            "mcp_session_active": False,
            "blocking_dialogs": [],
            "dismissed_dialogs_recent": [],
            "message": "pywin32 not installed (Windows + TwinCAT XAE required)",
            "vscode_extension": ext_status,
            "log_file": log_path,
            "mcp_server_version": MCP_SERVER_VERSION,
        })
    try:
        status_dict = _as_dict(_get_bridge().get_status())
        status_dict["vscode_extension"] = ext_status
        status_dict["log_file"] = log_path
        status_dict["mcp_server_version"] = MCP_SERVER_VERSION
        return _json(status_dict)
    except Exception as exc:
        log.error("twincat_status failed: %s", exc, exc_info=True)
        return _json({"error": str(exc), "vscode_extension": ext_status, "log_file": log_path, "mcp_server_version": MCP_SERVER_VERSION})


def twincat_open(
    path: str = "",
    plcproj_path: str = "",
    sln_path: str = "",
    proj_name: str = "",
    timeout_seconds: int = 50,
    xae_version: str = "",
) -> str:
    """Open a TwinCAT solution in XAE and locate the PLC project.

    XAE pin / attach: response includes requested_xae_version,
    attached_xae_version, pin_honored, pin_ignored_reason,
    created_new_instance, attached_instance_id, open_solutions[].
    If the solution is already open in another shell, MCP attaches to that
    instance even when xae_version differs (pin_honored=false).

    Accepts a single 'path' parameter that can be:
      - A .plcproj file  (opens directly)
      - A .sln file      (resolves via .tsproj/.xti XML to .plcproj)
      - A folder         (scans for .sln or .plcproj automatically)

    If the solution contains multiple PLC projects, returns an error
    with the full list of available projects and their .plcproj paths.

    Legacy parameters (plcproj_path, sln_path, proj_name) are still
    supported for backward compatibility but 'path' is preferred.

    xae_version (optional): which TwinCAT XAE shell to use.
      - "4024" or "15.0" -> TcXaeShell 4024 (VS2017)
      - "4026" or "17.0" -> TcXaeShell 4026 (VS2022)
      - empty (default): attach to a running instance that already has
        the solution; if starting new, prefer an already-running shell
        version, else the newest registered ProgID.

    Behaviour:
      - Searches ALL running XAE instances (ROT) for the matching solution
        -- required when multiple solutions are open.
      - If XAE is running with the correct solution: reuse it.
      - If XAE is running with a different solution: start a
        separate XAE instance (the user's solution stays open).
      - If XAE is running with no solution: open the requested one.
      - If XAE is not running: start a new instance."""

    path = _clean_path(path)
    sln_path = _clean_path(sln_path)
    plcproj_path = _clean_path(plcproj_path)

    resolved_sln = ""
    if path and path.lower().endswith(".sln"):
        resolved_sln = os.path.abspath(path)
    elif sln_path:
        resolved_sln = os.path.abspath(sln_path)

    if path:
        resolved = _active_resolve_path(path)
        if isinstance(resolved, dict):
            err_code = resolved.get("error", "")
            if err_code == "multiple_solutions":
                return _json(resolved)
            if err_code == "multiple_plc_projects":
                if resolved_sln:
                    avail = resolved.get("available_projects", [])
                    chosen = None
                    sln_base = os.path.splitext(os.path.basename(resolved_sln))[0].lower()
                    for p in avail:
                        p_name = p.get("name", "").lower()
                        if p_name == sln_base:
                            chosen = p.get("plcproj_path")
                            break
                    if not chosen:
                        for p in avail:
                            p_name = p.get("name", "").lower()
                            if not any(k in p_name for k in ("sample", "test", "demo", "app")):
                                chosen = p.get("plcproj_path")
                                break
                    if not chosen and avail:
                        chosen = avail[0].get("plcproj_path")
                    if chosen:
                        plcproj_path = chosen
                        proj_name = _active_read_proj_name(chosen)
                else:
                    return _json(resolved)
            elif resolved_sln:
                log.warning(
                    "plcproj resolver failed for %s (%s) — "
                    "proceeding with sln_path for ROT attach",
                    path, err_code,
                )
            else:
                return _json(resolved)
        else:
            plcproj_path = resolved

    if not path and not plcproj_path and not sln_path:
        return _json({
            "success": False,
            "error": "No path provided. Pass path=, plcproj_path=, or sln_path=.",
        })

    if not proj_name and plcproj_path:
        proj_name = _active_read_proj_name(plcproj_path)

    bridge = _get_bridge()

    try:
        log.info("twincat_open: opening sln='%s', plc='%s' (timeout=%ss)", resolved_sln or sln_path, plcproj_path, timeout_seconds)
        res = bridge.open_solution(
            sln_path=resolved_sln or sln_path or None,
            plcproj_path=plcproj_path or None,
            proj_name=proj_name or None,
            timeout_s=timeout_seconds,
            xae_version=xae_version or None,
        )
        s_ok = getattr(res, "success", res.get("success") if isinstance(res, dict) else False)
        s_msg = getattr(res, "message", res.get("message") if isinstance(res, dict) else "")
        log.info("twincat_open completed: success=%s, msg='%s'", s_ok, s_msg)
        return _json(res)
    except Exception as exc:
        log.error("twincat_open failed: %s", exc, exc_info=True)
        return _json({"success": False, "error": str(exc)})


def twincat_reload(timeout_seconds: int = 50) -> str:
    """Reload the TwinCAT solution from disk (close without save, reopen).

    ONLY required after the .plcproj file was changed (version bump,
    added/removed Compile entries, library references, plcproj sync).

    NOT needed after editing .TcPOU / .TcDUT / .TcGVL / .TcIO content --
    twincat_check_all_objects re-reads those from disk automatically.
    Do NOT reload for .tsproj / .sln / source-only edits.

    Takes ~5-10 seconds (polls for readiness instead of fixed timer).
    Requires twincat_open to have been called at least once."""
    try:
        log.info("twincat_reload: reloading solution (timeout=%ss)", timeout_seconds)
        res = _get_bridge().reload_solution(timeout_s=timeout_seconds)
        s_ok = getattr(res, "success", res.get("success") if isinstance(res, dict) else False)
        s_msg = getattr(res, "message", res.get("message") if isinstance(res, dict) else "")
        log.info("twincat_reload completed: success=%s, msg='%s'", s_ok, s_msg)
        return _json(res)
    except Exception as exc:
        log.error("twincat_reload failed: %s", exc, exc_info=True)
        return _json({"success": False, "error": str(exc)})


def twincat_check_all_objects() -> str:
    """Run CheckAllObjects on the open PLC project.

    This is the PRIMARY validation tool for library projects.
    It re-reads files from disk and compiles ALL objects -- not just
    those referenced from MAIN. A normal Build would miss errors
    in unreferenced POUs.

    Returns structured JSON with compile result AND all errors,
    warnings, and infos -- no separate twincat_get_output_log call needed.

    Response fields: success, method, error_count, warning_count,
    errors[], warnings[], infos[], message.
    Always inspect warning_count and warnings[] even when success=true.

    No twincat_reload needed -- CheckAllObjects reads from disk.
    Requires twincat_open to have been called."""
    try:
        log.info("twincat_check_all_objects: running check")
        res = _get_bridge().check_all_objects()
        s_ok = getattr(res, "success", res.get("success") if isinstance(res, dict) else False)
        err_c = getattr(res, "error_count", res.get("error_count", 0) if isinstance(res, dict) else 0)
        log.info("twincat_check_all_objects completed: success=%s, errors=%s", s_ok, err_c)
        return _json(res)
    except Exception as exc:
        log.error("twincat_check_all_objects failed: %s", exc, exc_info=True)
        return _json({"success": False, "error": str(exc)})


def twincat_build(timeout_seconds: int = 50, full_rebuild: bool = False) -> str:
    """Build the TwinCAT solution.

    By default runs an incremental build (Build.BuildSolution).
    Set full_rebuild=true to delete all outputs and recompile
    everything (Build.RebuildSolution) -- slower but guaranteed clean.

    Detects PLC compile success via _CompileInfo timestamps
    combined with SolutionBuild.LastBuildInfo. Returns structured
    success/failure info AND all errors, warnings, and infos --
    no separate twincat_get_output_log call needed.

    Response fields: success, elapsed_seconds, build_state,
    last_build_info, compile_info_updated, error_count, errors[],
    warnings[], infos[], message.

    Requires twincat_open to have been called."""
    try:
        log.info("twincat_build: starting build (full_rebuild=%s, timeout=%ss)", full_rebuild, timeout_seconds)
        res = _get_bridge().build(
            timeout_s=timeout_seconds, full_rebuild=full_rebuild,
        )
        s_ok = getattr(res, "success", res.get("success") if isinstance(res, dict) else False)
        err_c = getattr(res, "error_count", res.get("error_count", 0) if isinstance(res, dict) else 0)
        log.info("twincat_build completed: success=%s, errors=%s", s_ok, err_c)
        return _json(res)
    except Exception as exc:
        log.error("twincat_build failed: %s", exc, exc_info=True)
        return _json({"success": False, "error": str(exc)})


def twincat_get_output_log() -> str:
    """Read the full build / check output from XAE.

    NOTE: twincat_build and twincat_check_all_objects now include
    errors, warnings, and infos automatically. This tool is only
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


def twincat_stweep_status(probe_license: bool = False) -> str:
    """Detect STweep install and Formatcode DTE commands (no UI by default).

    STweep is a third-party XAE extension — not a Beckhoff Automation Interface
    API. Default probes (background, no window):
      - filesystem: TcXaeShell Extensions\\GeBa Engineering\\STweep*
      - DTE commands when twincat_open session exists

    License: by default NOT opened in the UI. Verified fail-fast on the first
    twincat_stweep_format call. Optional probe_license=true opens STweep > License
    wizard briefly (reads STATIC status only; never returns activation keys).

    Response: success, installed, version, install_paths[], commands{},
    commands_loaded, dte_attached, license_ok, license_state, license_detail,
    license_days_remain, license_days_total, ready, message,
    format_progress{} (live job snapshot; also via twincat_stweep_format_progress)."""
    try:
        return _json(_get_bridge().get_stweep_status(
            probe_license=probe_license,
        ))
    except Exception as exc:
        return _json({"success": False, "installed": False, "error": str(exc)})


def twincat_stweep_format_progress() -> str:
    """Poll live STweep format job progress (no STA / safe while formatting).

    Use after twincat_stweep_format(..., wait=false) for large folders/projects.
    Also works during a blocking wait=true call if the client can poll in parallel.

    Response: running, phase (idle|starting|formatting|done|error|canceled),
    target, files_total/done/formatted/failed, current_file, percent,
    elapsed_s, message, result{} (final StweepFormatResult when finished)."""
    try:
        return _json(_get_bridge().get_format_progress())
    except Exception as exc:
        return _json({"success": False, "running": False, "error": str(exc)})


def twincat_stweep_format_cancel() -> str:
    """Cancel a running multi-file STweep format job.

    Sets a cancel flag; the job stops after the current file finishes
    (does not hard-kill mid-Formatcode). Poll twincat_stweep_format_progress until
    running=false / phase=canceled. Safe while STA is busy."""
    try:
        return _json(_get_bridge().cancel_format())
    except Exception as exc:
        return _json({"success": False, "canceled": False, "error": str(exc)})


def twincat_stweep_format(
    path: str = "",
    recursive: bool = True,
    timeout_seconds: int = 300,
    confirm: bool = False,
    wait: bool = False,
) -> str:
    """Format Structured Text via STweep \"Format code\" in the open XAE shell.

    Uses EnvDTE ExecuteCommand. Does not use STweep.CLI.

    IMPORTANT — folder vs UI: Right-click Format on a Solution Explorer folder
    uses PlcFolder/SPSOrdner.Formatcode once. Automation cannot Select SE
    items (UIHierarchyItemMarshaler.Select missing on TcXaeShell), so MCP
    walks files and runs editor Formatcode after OpenFile, then closes the
    document. Cancel with twincat_stweep_format_cancel (between files).

    Preflight (same session as twincat_open, no license window):
      - STweep installed on disk
      - Formatcode DTE commands loaded
      - license: fail-fast on first Formatcode error (aborts remaining files)

    Allowed without confirm (file / folder only):
      - file: .TcPOU / .TcGVL / .TcDUT / .TcIO
      - folder: formattable files in that folder (not the PLC project root)

    Whole-project format requires confirm=true:
      - path empty (open PLC project)
      - path to a .plcproj
      - path to the PLC project root directory (folder containing .plcproj)

    wait=false (default): start in background (method=async_started) and poll
    twincat_stweep_format_progress until running=false. wait=true only for short sync
    checks; if timeout_seconds>90, wait is coerced to async (Cursor idle -32001).
    Per-file editor Formatcode availability is capped (~8s) then folder fallback
    or fail — never spins for the full job timeout.

    Requires twincat_open first (same bridge session as build/check).

    Response: success, method, command, target, files_*, installed,
    license_ok, license_state, license_detail, async_started, canceled,
    message."""
    try:
        return _json(_get_bridge().format_code(
            path=_clean_path(path),
            recursive=recursive,
            timeout_s=timeout_seconds,
            confirm=confirm,
            wait=wait,
        ))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


def twincat_dismiss_safe_dialogs() -> str:
    """Dismiss idle XAE \"file changed outside\" reload prompts (Yes/Ja).

    Use when twincat_status.blocking_dialogs has auto_dismissable=true.
    Clears the sequential dialog queue (not parallel windows). Then
    twincat_status again and retry the original MCP call once.

    Do NOT narrate manual XAE clicking. If remaining dialogs are not
    auto_dismissable, stop and tell the user the dialog text."""
    try:
        return _json(_get_bridge().dismiss_safe_dialogs())
    except Exception as exc:
        return _json({
            "success": False,
            "dismissed_count": 0,
            "error": str(exc),
            "message": str(exc),
        })


def twincat_export_progress() -> str:
    """Poll live library-export job progress (no STA / safe while exporting).

    Use after twincat_export_library(..., wait=false). Also works during a
    blocking wait=true call from another agent turn. Fields: running, phase
    (starting/checking/exporting_library/exporting_compiled/done/error),
    percent, elapsed_s, message, result{} (final ExportResult when finished).

    After Cursor -32001: poll here first (job may still be running). If idle
    and unclear, call twincat_export_check_artifacts before re-exporting."""
    try:
        return _json(_get_bridge().get_export_progress())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


def twincat_export_library(
    output_dir: str = "",
    plcproj_path: str = "",
    library: bool = True,
    compiled_library: bool = True,
    install_library: bool = True,
    install_compiled_library: bool = False,
    force: bool = False,
    wait: bool = False,
    timeout_seconds: int = 1800,
) -> str:
    """Export the PLC project as .library and/or .compiled-library.

    What gets EXPORTED (written to output_dir):
      library=true             -> exports .library file
      compiled_library=true    -> exports .compiled-library file

    What gets INSTALLED (into the local TwinCAT library repository):
      install_library=true              -> installs .library
      install_compiled_library=true     -> installs .compiled-library

    Defaults: export both, install only .library.

    Title and version are auto-read from the .plcproj file.
    Default output: <git_repo_root>/Versions/<ProjectVersion>/
    Runs CheckAllObjects automatically before export -- fails if errors exist.

    Guards: refuses ProjectVersion 0.0.0.0 and non-library projects unless
    force=true. Always echoes resolved_plcproj_path, project_title,
    project_version, output_dir. Prefer an explicit plcproj_path when a
    sample solution is open.

    IMPORTANT — Cursor MCP idle timeout: long blocking exports often hit
    MCP error -32001 even when XAE finishes successfully. Default wait=false
    starts the job in background (method=async_started); poll
    twincat_export_progress until running=false, then read result{}.
    wait=true with timeout_seconds>90 is coerced to async. After -32001:
    progress -> twincat_export_check_artifacts -> retry only if missing."""
    from export_guards import export_echo_fields, validate_export_target

    output_dir = _clean_path(output_dir)
    plcproj_path = _clean_path(plcproj_path)

    bridge = _get_bridge()

    def _sync_and_get_session():
        if bridge._dte and bridge._is_dte_alive():
            try:
                actual_sln = str(bridge._dte.Solution.FullName)
                if actual_sln:
                    bridge._sln_path = actual_sln
                    if not bridge._plcproj_file_path or not os.path.isfile(bridge._plcproj_file_path):
                        bridge._plcproj_file_path = bridge._detect_plcproj_path()
                    else:
                        sln_dir = os.path.dirname(actual_sln)
                        repo = _find_repo_root(actual_sln) or sln_dir
                        norm_plc = os.path.abspath(bridge._plcproj_file_path)
                        if not (norm_plc.startswith(os.path.abspath(sln_dir)) or norm_plc.startswith(os.path.abspath(repo))):
                            bridge._plcproj_file_path = bridge._detect_plcproj_path()
            except Exception:
                pass
        return (bridge._sln_path or "", bridge._plcproj_file_path or "")

    sln_path, plcproj_from_bridge = bridge._call_sta(_sync_and_get_session, timeout=5) or ("", "")

    plcproj_explicit = bool(plcproj_path and str(plcproj_path).strip())
    resolved_plcproj = _resolve_plcproj_path(
        plcproj_path=plcproj_path,
        sln_path=sln_path,
        plcproj_from_bridge=plcproj_from_bridge,
    )
    plcproj_path = resolved_plcproj

    if not plcproj_path or not os.path.isfile(plcproj_path):
        return _json({
            "success": False,
            "ok": False,
            "error_code": "plcproj_not_found",
            "error": (
                f"Cannot find .plcproj file. "
                f"Searched from: {sln_path or 'cwd'}. "
                f"Pass plcproj_path explicitly."
            ),
            "message": (
                f"Cannot find .plcproj file. "
                f"Searched from: {sln_path or 'cwd'}. "
                f"Pass plcproj_path explicitly."
            ),
        })

    info = _read_plcproj_meta(plcproj_path)
    title = info.get("title") or info.get("name") or "Unknown"
    version = info.get("version") or "0.0.0.0"

    if not output_dir:
        repo = _find_repo_root(sln_path or plcproj_path)
        if not repo:
            repo = os.path.dirname(sln_path) if sln_path else os.getcwd()
        output_dir = os.path.join(repo, "Versions", version)

    refused = validate_export_target(
        plcproj_path=plcproj_path,
        info=info,
        output_dir=output_dir,
        plcproj_from_bridge=plcproj_from_bridge,
        plcproj_explicit=plcproj_explicit,
        force=force,
    )
    if refused:
        return _json(refused)

    echo = export_echo_fields(
        plcproj_path=plcproj_path, info=info, output_dir=output_dir,
    )
    try:
        result = _as_dict(
            bridge.export_library(
                output_dir, title, version,
                library=library,
                compiled_library=compiled_library,
                install_library=install_library,
                install_compiled_library=install_compiled_library,
                wait=wait,
                timeout_s=timeout_seconds,
            )
        )
        result.update(echo)
        return _json(result)
    except Exception as exc:
        err = {"success": False, "ok": False, "error": str(exc), "message": str(exc)}
        err.update(echo)
        return _json(err)


def twincat_export_check_artifacts(
    output_dir: str = "",
    project_title: str = "",
    project_version: str = "",
    library: bool = True,
    compiled_library: bool = True,
) -> str:
    """Check whether export artifacts exist on disk (no STA / safe anytime).

    After Cursor MCP -32001 on export: (1) twincat_export_progress — if
    running=true keep polling; (2) if idle/unclear call this tool; (3) if
    all_present=true treat as success — do NOT re-export; (4) only if
    missing retry twincat_export_library once with wait=false.

    Empty output_dir/title/version -> uses last export progress fields."""
    try:
        return _json(_get_bridge().check_export_artifacts(
            output_dir=_clean_path(output_dir),
            project_title=project_title,
            project_version=project_version,
            library=library,
            compiled_library=compiled_library,
        ))
    except Exception as exc:
        return _json({
            "success": False,
            "all_present": False,
            "error": str(exc),
            "message": str(exc),
        })


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
        if _bridge is not None:
            _bridge.shutdown()
        _bridge = None
        return _json(result)
    except Exception as exc:
        if _bridge is not None:
            _bridge.shutdown()
        _bridge = None
        return _json({"success": False, "error": str(exc)})


def register_tools(mcp: Any) -> None:
    """Register solution, build, STweep, and export tools on FastMCP server."""
    mcp.tool()(twincat_status)
    mcp.tool()(twincat_open)
    mcp.tool()(twincat_reload)
    mcp.tool()(twincat_check_all_objects)
    mcp.tool()(twincat_build)
    mcp.tool()(twincat_get_output_log)
    mcp.tool()(twincat_stweep_status)
    mcp.tool()(twincat_stweep_format_progress)
    mcp.tool()(twincat_stweep_format_cancel)
    mcp.tool()(twincat_stweep_format)
    mcp.tool()(twincat_dismiss_safe_dialogs)
    mcp.tool()(twincat_export_progress)
    mcp.tool()(twincat_export_library)
    mcp.tool()(twincat_export_check_artifacts)
    mcp.tool()(twincat_close)
