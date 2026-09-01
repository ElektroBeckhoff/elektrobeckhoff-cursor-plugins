"""
TwinCAT MCP Server for Cursor IDE.

Exposes TcXaeShell build automation, runtime control (TE1000 + ADS),
Usermode Runtime (TC170x), FBD/FUP-to-ST and CFC-to-ST migration as MCP tools:
status/open/check/build/export/close, target/activate/start/tasks,
UmRT start/stop, ADS mode + PLC + variable R/W, ST formatting,
migrators, plcproj, InfoSys.

Transport: stdio  (Cursor starts this process as a child)
COM:       TcXaeShell via STA thread (twincat_automation_interface / TE1000)
ADS:       pyads client (ads/twincat_ads_client) for runtime & symbols
UmRT:      TC170x Usermode Runtime controller (umrt/twincat_umrt_controller)
"""

import io
import os
import re
import sys
import glob
import json
import logging
import threading
import contextlib
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Union
from dataclasses import asdict

_server_dir = os.path.dirname(os.path.abspath(__file__))
if _server_dir not in sys.path:
    sys.path.insert(0, _server_dir)
for _subdir in (
    "migrator", "automation_interface", "plcproj", "ads", "umrt",
):
    _p = os.path.join(_server_dir, _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from migrator._bootstrap import setup_migrator_paths  # noqa: E402

setup_migrator_paths()

# stdout is the MCP JSON-RPC wire -- all logging goes to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("twincat-mcp")

from mcp.server.fastmcp import FastMCP
from twincat_automation_interface import TcAutomationInterface, HAS_WIN32
from migrator.fbd import main as fup_main
from migrator.cfc import main as cfc_main
from twincat_plcproj_ops import main as plcproj_main, read_project_info
from migrator.router import main as unified_main
from infosys_mshc import (
    InfoSysMshcIndex,
    format_page_markdown,
    format_search_markdown,
    resolve_mshc_path,
)
import extension_ops

# Automatically check & update VS Code extension in background on MCP startup
threading.Thread(target=extension_ops.auto_update_if_needed, daemon=True).start()

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


def _as_dict(obj) -> dict:
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return dict(obj)
    return {"value": obj}


def _target_is_mcp_umrt() -> bool:
    """True when XAE target NetId matches the running MCP UmRT instance."""
    return bool(_target_context().get("target_is_mcp_umrt"))


def _target_context(net_id: str = "") -> dict:
    """Resolve whether a runtime-control NetId is the MCP Usermode Runtime.

    net_id empty → use current XAE target (when a session is open).
    """
    umrt_id = ""
    umrt_running = False
    try:
        umrt = _get_umrt()
        umrt_id = umrt.get_mcp_ams_net_id_if_running() or ""
        umrt_running = bool(umrt_id)
        if not umrt_id:
            try:
                st = umrt.status()
                umrt_id = getattr(st, "mcp_ams_net_id", "") or ""
            except Exception:
                pass
    except Exception as exc:
        log.debug("UmRT context failed: %s", exc)

    target = (net_id or "").strip()
    if not target:
        try:
            if HAS_WIN32:
                tid = _get_bridge().get_target_net_id()
                if getattr(tid, "success", False):
                    target = (tid.net_id or "").strip()
        except Exception as exc:
            log.debug("XAE target context failed: %s", exc)

    is_umrt = bool(umrt_id and target and target == umrt_id and umrt_running)
    return {
        "target_net_id": target,
        "mcp_umrt_net_id": umrt_id,
        "mcp_umrt_running": umrt_running,
        "target_is_mcp_umrt": is_umrt,
    }


def _attach_target_safety(data: dict, operation: str, net_id: str = "") -> dict:
    """Warn when activate/start/stop/mode hits a non-MCP-UmRT target."""
    from user_actions import attach_non_umrt_target_warning

    ctx = _target_context(net_id)
    return attach_non_umrt_target_warning(
        data,
        operation=operation,
        target_net_id=ctx["target_net_id"],
        mcp_umrt_net_id=ctx["mcp_umrt_net_id"],
        mcp_umrt_running=ctx["mcp_umrt_running"],
        target_is_mcp_umrt=ctx["target_is_mcp_umrt"],
    )


def _enrich_umrt_runtime_result(result, operation: str = "runtime control") -> dict:
    """Attach license / I/O prompts, structured activate flags, non-UmRT safety.

    Agents must use activate_ok / boot_ok / licenses_ok — not log-tail text.
    Trial license user_action_required is attached only on detected license errors.
    """
    from user_actions import (
        attach_user_actions,
        looks_like_license_error,
        umrt_activate_actions,
    )
    from runtime_messages import (
        infer_build_outcome,
        looks_like_activate_canceled,
        looks_like_boot_written,
    )

    data = _as_dict(result)
    op = (operation or "").strip()
    is_activate = op.endswith("activate") or "activate" in op
    is_start = op.endswith("start") and "plc" not in op
    com_ok = bool(data.get("success"))
    blob = f"{data.get('message', '')} {data.get('error', '')}"
    license_err = looks_like_license_error(blob)

    # Prefer messages since last activate baseline (avoids stale pagefaults).
    try:
        msgs = _get_bridge().get_runtime_messages(since_last_activate=True)
        md = _as_dict(msgs)
        data["runtime_findings"] = md.get("findings") or []
        data["has_blocking_runtime_error"] = bool(
            md.get("has_blocking_runtime_error")
            if "has_blocking_runtime_error" in md
            else md.get("has_blocking_error")
        )
        data["history_incomplete"] = bool(md.get("history_incomplete", True))
        if md.get("sys_manager_errors"):
            data["sys_manager_errors"] = md["sys_manager_errors"]
        if any(f.get("id") == "license" for f in data["runtime_findings"]):
            license_err = True
        pane_blob = "\n".join([
            md.get("twincat_output") or "",
            md.get("build_output_tail") or "",
            md.get("sys_manager_errors") or "",
            blob,
        ])
        canceled = looks_like_activate_canceled(pane_blob, blob)
        boot_written = looks_like_boot_written(pane_blob) or (
            com_ok and is_activate and not canceled
        )
        data["build_outcome"] = infer_build_outcome(pane_blob)
        if data["runtime_findings"]:
            ids = sorted({f.get("id") for f in data["runtime_findings"] if f.get("id")})
            data["message"] = (
                (data.get("message") or "")
                + f" | runtime_findings={','.join(ids)} "
                "(inspect via twincat_runtime_messages)"
            ).strip(" |")
    except Exception as exc:
        log.debug("runtime message enrich failed: %s", exc)
        data.setdefault("runtime_findings", [])
        data.setdefault("has_blocking_runtime_error", False)
        canceled = looks_like_activate_canceled(blob)
        boot_written = False
        data["build_outcome"] = infer_build_outcome(blob)
        data["history_incomplete"] = True

    blocking = bool(data.get("has_blocking_runtime_error"))
    if is_activate:
        if not com_ok:
            status = "failed"
            activate_ok = False
        elif canceled or blocking:
            status = "canceled" if canceled else "failed"
            activate_ok = False
        else:
            status = "success"
            activate_ok = True
        boot_ok = bool(activate_ok and boot_written and not blocking)
        data["status"] = status
        data["activate_ok"] = activate_ok
        data["boot_written"] = bool(boot_written)
        data["boot_ok"] = boot_ok
        if not activate_ok:
            data["success"] = False
        try:
            prereqs = _get_bridge()._ensure_prereqs()
            prereqs["last_activate_ok"] = activate_ok
            prereqs["last_boot_ok"] = boot_ok
        except Exception:
            pass
    elif is_start:
        start_ok = bool(com_ok and not blocking and not looks_like_activate_canceled(blob))
        data["status"] = "success" if start_ok else ("failed" if not com_ok else "failed")
        data["boot_ok"] = start_ok
        data["activate_ok"] = data.get("activate_ok")
        if not start_ok:
            data["success"] = False
        try:
            prereqs = _get_bridge()._ensure_prereqs()
            prereqs["last_boot_ok"] = start_ok
        except Exception:
            pass

    data["licenses_ok"] = (False if license_err else True)
    data["blocking_license_issue"] = bool(license_err)
    data["license_states"] = []

    # I/O prereq: only attach when not already satisfied
    io_needed = True
    try:
        prereqs = _get_bridge()._ensure_prereqs()
        if prereqs.get("io_disabled_all"):
            io_needed = False
        data["prereqs"] = dict(prereqs)
    except Exception:
        data["prereqs"] = {}

    action_ids = umrt_activate_actions(
        license_error=license_err,
        include_io=io_needed and (_target_is_mcp_umrt() or blocking),
    )
    if action_ids:
        data = attach_user_actions(data, *action_ids)

    ctx = _target_context()
    data["target_net_id"] = ctx.get("target_net_id") or data.get("target_net_id") or ""
    return _attach_target_safety(data, operation=operation)


# ================================================================
#  twincat_plcproj_info  (pure XML -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
def twincat_plcproj_info(plcproj_path: str = "") -> str:
    """Read TwinCAT PLC project metadata from .plcproj XML.

    Returns Title, Version, Company, Name, Released.
    Does NOT require a running TcXaeShell instance.
    Leave plcproj_path empty for auto-detection."""

    resolved = _resolve_plcproj_path(plcproj_path)
    if not resolved:
        return _json({"error": "No .plcproj found. Provide plcproj_path."})

    try:
        return _json(read_project_info(resolved))
    except Exception as exc:
        return _json({"error": str(exc)})


# ================================================================
#  twincat_workspace_symbols & twincat_symbol_lookup (Core Semantic)
# ================================================================

@mcp.tool()
def twincat_workspace_symbols(
    query: str = "",
    plcproj_path: str = "",
    limit: int = 50,
) -> str:
    """Search for symbols (POUs, DUTs, GVLs, methods, variables) across the TwinCAT project using twincat_core.

    query: Search substring to filter symbol names (optional)
    plcproj_path: Path to .plcproj file (optional, auto-detected if omitted)
    limit: Max results to return (default: 50)"""
    try:
        from twincat_core.project import get_shared_workspace

        p_path = _resolve_plcproj_path(plcproj_path)
        workspace = get_shared_workspace(p_path if p_path else None)
        symbols = workspace.find_symbols(query=query, limit=limit)

        results = []
        for s in symbols:
            results.append({
                "name": s.name,
                "kind": s.kind.value,
                "type_ref": s.type_ref,
                "file": str(s.file_path) if s.file_path else "",
                "line": s.span.start.line if s.span else 0,
                "doc": s.doc_comment,
            })
        return _json({"total": len(results), "symbols": results})
    except Exception as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def twincat_symbol_lookup(
    symbol_name: str,
    scope_pou: str = "",
    plcproj_path: str = "",
) -> str:
    """Resolve a symbol or member access chain (e.g. 'fbMotor.stParam.fSpeed', 'TON.IN', 'Tc2_Standard.CONCAT').

    symbol_name: Identifier or chained member expression to resolve (e.g. 'fbAxis.M_GetStatus().bRunning')
    scope_pou: Enclosing POU or method name for local context (optional)
    plcproj_path: Path to .plcproj file (optional, auto-detected if omitted)"""
    try:
        from twincat_core.project import get_shared_workspace

        p_path = _resolve_plcproj_path(plcproj_path)
        workspace = get_shared_workspace(p_path if p_path else None)
        sym = workspace.lookup_symbol(symbol_name, scope_pou=scope_pou or None)
        if not sym:
            return _json({
                "found": False,
                "symbol_name": symbol_name,
                "message": f"Symbol '{symbol_name}' could not be resolved.",
            })

        return _json({
            "found": True,
            "name": sym.name,
            "kind": sym.kind.value,
            "type_ref": sym.type_ref,
            "file": str(sym.file_path) if sym.file_path else "",
            "line": sym.span.start.line if sym.span else 0,
            "doc": sym.doc_comment,
            "initial_value": sym.initial_value,
        })
    except Exception as exc:
        return _json({"error": str(exc)})


# ================================================================
#  twincat_check_syntax (Fast Headless Syntax & Semantic Validator)
# ================================================================

@mcp.tool()
def twincat_check_syntax(
    path: str = "",
    recursive: bool = True,
    include_warnings: bool = True,
) -> str:
    """Validate TwinCAT 3 IEC 61131-3 Structured Text syntax and semantics using twincat_core.

    Fast, headless validator (no Visual Studio or TcXaeShell required, works cross-platform).
    Performs full ST syntax parsing, AST construction, and semantic verification:
      - Lossless XML CDATA integrity
      - Lexer & token errors
      - Declaration rules (TC-DECL-001..007: explicit return types, constant inits, array bounds, etc.)
      - Statement & expression rules (TC-STMT-*, TC-EXPR-*: loop bounds, jumps, assignment targets)
      - Semantic rules (TC-SEM-001..007: unknown types, duplicate identifiers, interface conformance,
        cyclic inheritance, abstract instantiations, type mismatches, narrowing/precision loss warnings)

    path: File (.TcPOU, .TcDUT, .TcGVL, .TcIO), directory, .plcproj, or .sln. If empty, auto-detects project.
    recursive: Scan subdirectories recursively when path is a directory (default: True).
    include_warnings: Include severity=WARNING items (e.g. TC-SEM-007 narrowing warnings) (default: True).
    """
    try:
        from pathlib import Path
        from twincat_core.project import WorkspaceIndex
        from twincat_core.semantic.diagnostics import run_semantic_analysis
        from twincat_core.syntax.diagnostics import DiagnosticSeverity

        target_path: Optional[Path] = None
        if path:
            p = Path(path).resolve()
            if not p.exists():
                return _json({"success": False, "error": f"Path does not exist: {path}"})
            target_path = p
        else:
            auto_p = _resolve_plcproj_path()
            if auto_p:
                target_path = Path(auto_p).resolve()
            else:
                target_path = Path.cwd().resolve()

        files_to_check: list[Path] = []
        workspace: Optional[WorkspaceIndex] = None

        if target_path.is_file():
            if target_path.suffix.lower() == ".plcproj":
                workspace = WorkspaceIndex.from_plcproj(target_path)
                if workspace.project:
                    files_to_check = [
                        item.abs_path
                        for item in workspace.project.compile_items.values()
                        if not item.exclude_from_build and item.abs_path.is_file()
                    ]
            elif target_path.suffix.lower() == ".sln":
                resolved = _resolve_sln(str(target_path))
                if isinstance(resolved, dict) and not resolved.get("success", True):
                    return _json(resolved)
                plcproj_p = Path(resolved if isinstance(resolved, str) else resolved["plcproj_path"])
                workspace = WorkspaceIndex.from_plcproj(plcproj_p)
                if workspace.project:
                    files_to_check = [
                        item.abs_path
                        for item in workspace.project.compile_items.values()
                        if not item.exclude_from_build and item.abs_path.is_file()
                    ]
            elif target_path.suffix.lower() in (".tcpou", ".tcdut", ".tcgvl", ".tcio"):
                # Single file: find if parent has plcproj to build full symbol context
                plcs = list(target_path.parent.glob("*.plcproj")) or list(target_path.parent.parent.glob("*.plcproj"))
                if plcs:
                    workspace = WorkspaceIndex.from_plcproj(plcs[0])
                else:
                    workspace = WorkspaceIndex()
                files_to_check = [target_path]
            else:
                return _json({"success": False, "error": f"Unsupported file type: {target_path.suffix}"})
        elif target_path.is_dir():
            plcs = list(target_path.glob("*.plcproj")) or list(target_path.glob("**/*.plcproj"))
            if plcs:
                workspace = WorkspaceIndex.from_plcproj(plcs[0])
                if workspace.project:
                    files_to_check = [
                        item.abs_path
                        for item in workspace.project.compile_items.values()
                        if not item.exclude_from_build and item.abs_path.is_file()
                    ]
            else:
                workspace = WorkspaceIndex()
                pattern = "**/*" if recursive else "*"
                candidates: list[Path] = []
                for ext in (".TcPOU", ".TcDUT", ".TcGVL", ".TcIO"):
                    candidates.extend(target_path.glob(f"{pattern}{ext}"))
                    if ext.lower() != ext:
                        candidates.extend(target_path.glob(f"{pattern}{ext.lower()}"))
                seen_f: set[Path] = set()
                for f in candidates:
                    rf = f.resolve()
                    if rf not in seen_f and rf.is_file():
                        seen_f.add(rf)
                        files_to_check.append(rf)

        if not workspace:
            workspace = WorkspaceIndex()

        if not files_to_check:
            return _json({
                "success": True,
                "path": str(target_path),
                "total_files": 0,
                "error_count": 0,
                "warning_count": 0,
                "message": "No TwinCAT source files found to validate.",
                "diagnostics": [],
            })

        for f in files_to_check:
            workspace.update_file(f)

        diagnostics_list = []
        error_count = 0
        warning_count = 0

        for f in files_to_check:
            indexed = workspace.get_file(f)
            if not indexed:
                continue

            file_diags = list(indexed.diagnostics)
            semantic_diags = run_semantic_analysis(workspace, f)
            file_diags.extend(semantic_diags)

            for d in file_diags:
                sev_str = "error" if d.severity == DiagnosticSeverity.ERROR else (
                    "warning" if d.severity == DiagnosticSeverity.WARNING else "info"
                )
                if sev_str == "error":
                    error_count += 1
                elif sev_str == "warning":
                    warning_count += 1
                    if not include_warnings:
                        continue
                elif not include_warnings:
                    continue

                line_num = d.span.start.line if d.span else 1
                col_num = d.span.start.col if d.span else 1

                diagnostics_list.append({
                    "file": f.name,
                    "path": str(f),
                    "line": line_num,
                    "column": col_num,
                    "severity": sev_str,
                    "code": d.code or "TC-SYNTAX",
                    "message": d.message,
                })

        return _json({
            "success": error_count == 0,
            "path": str(target_path),
            "total_files": len(files_to_check),
            "error_count": error_count,
            "warning_count": warning_count,
            "diagnostics": diagnostics_list,
        })
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_status
# ================================================================

@mcp.tool()
def twincat_status() -> str:
    """Diagnose TcXaeShell / MCP session health and VS Code extension status without opening a solution.

    Reports XAE install/running state, per-instance solution paths and
    COM-busy flags (modal dialog), visible TcXaeShell message boxes,
    MCP session binding, SilentMode, recent auto-dismissed dialogs,
    SysManager error text, twincat_runtime_started, target_net_id,
    and VS Code / Cursor extension installation status.

    If ``dte_busy`` or ``blocking_dialogs`` is set: READ those fields.
    For ``auto_dismissable=true`` reload prompts call
    ``twincat_dismiss_safe_dialogs`` once, then retry the original tool
    once. Do not narrate manual XAE clicking. Non-auto-dismissable dialogs
    → stop and tell the user the dialog text.
    """

    ext_status = extension_ops.get_extension_status()

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
        })
    try:
        status_dict = _as_dict(_get_bridge().get_status())
        status_dict["vscode_extension"] = ext_status
        return _json(status_dict)
    except Exception as exc:
        return _json({"error": str(exc), "vscode_extension": ext_status})


# ================================================================
#  twincat_extension_* tools
# ================================================================

@mcp.tool()
def twincat_extension_status() -> str:
    """Check the installation and version status of the TwinCAT 3 VS Code / Cursor extension.

    Reports whether 'elektrobeckhoff.twincat-iecst' is installed in Cursor/VS Code,
    its installed version, available local VSIX version, and whether an update is available.
    """
    try:
        return _json(extension_ops.get_extension_status())
    except Exception as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def twincat_extension_install(force: bool = True) -> str:
    """Install or update the TwinCAT 3 Structured Text VS Code / Cursor extension from local VSIX.

    Builds or packages the .vsix package from the local repository if necessary, then invokes
    the editor CLI ('cursor' or 'code') to install/update the extension with syntax highlighting
    and language server capabilities.
    """
    try:
        return _json(extension_ops.install_extension(force=force))
    except Exception as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def twincat_extension_build() -> str:
    """Build the local TwinCAT 3 VS Code extension VSIX package from source.

    Packages all extension manifests, grammars, and bundled assets into twincat-iecst.vsix.
    """
    try:
        return _json(extension_ops.build_vsix())
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
      - A folder          (scans for .sln or .plcproj automatically)

    If the solution contains multiple PLC projects, returns an error
    with the full list of available projects and their .plcproj paths.

    Legacy parameters (plcproj_path, sln_path, proj_name) are still
    supported for backward compatibility but 'path' is preferred.

    xae_version (optional): which TwinCAT XAE shell to use.
      - \"4024\" or \"15.0\" -> TcXaeShell 4024 (VS2017)
      - \"4026\" or \"17.0\" -> TcXaeShell 4026 (VS2022)
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

    resolved_sln = ""
    if path and path.lower().endswith(".sln"):
        resolved_sln = os.path.abspath(path)
    elif sln_path:
        resolved_sln = os.path.abspath(sln_path)

    if path:
        resolved = _resolve_path(path)
        if isinstance(resolved, dict):
            err_code = resolved.get("error", "")
            if err_code in ("multiple_plc_projects", "multiple_solutions"):
                return _json(resolved)
            if resolved_sln:
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
        proj_name = _read_proj_name(plcproj_path)

    bridge = _get_bridge()
    bridge._plcproj_file_path = plcproj_path or None

    try:
        return _json(bridge.open_solution(
            sln_path=resolved_sln or sln_path or None,
            plcproj_path=plcproj_path or None,
            proj_name=proj_name or None,
            timeout_s=timeout_seconds,
            xae_version=xae_version or None,
        ))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_reload
# ================================================================

@mcp.tool()
def twincat_reload(timeout_seconds: int = 180) -> str:
    """Reload the TwinCAT solution from disk (close without save, reopen).

    ONLY required after the .plcproj file was changed (version bump,
    added/removed Compile entries, library references, plcproj sync).

    NOT needed after editing .TcPOU / .TcDUT / .TcGVL / .TcIO content --
    twincat_check_all_objects re-reads those from disk automatically.
    Do NOT reload for .tsproj / .sln / source-only edits.

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
def twincat_build(timeout_seconds: int = 180, full_rebuild: bool = False) -> str:
    """Build the TwinCAT solution.

    By default runs an incremental build (Build.BuildSolution).
    Set full_rebuild=true to delete all outputs and recompile
    everything (Build.RebuildSolution) -- slower but guaranteed clean.

    Detects PLC compile success via _CompileInfo timestamps
    combined with SolutionBuild.LastBuildInfo.  Returns structured
    success/failure info AND all errors, warnings, and infos --
    no separate twincat_get_output_log call needed.

    Response fields: success, elapsed_seconds, build_state,
    last_build_info, compile_info_updated, error_count, errors[],
    warnings[], infos[], message.

    Requires twincat_open to have been called."""

    try:
        return _json(_get_bridge().build(
            timeout_s=timeout_seconds, full_rebuild=full_rebuild,
        ))
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
#  STweep format (XAE DTE) — twincat_stweep_* tools
# ================================================================

@mcp.tool()
def twincat_stweep_status(probe_license: bool = False) -> str:
    """Detect STweep install and Formatcode DTE commands (no UI by default).

    STweep is a third-party XAE extension — not a Beckhoff Automation Interface
    API. Default probes (background, no window):
      - filesystem: TcXaeShell Extensions\\\\GeBa Engineering\\\\STweep*
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


@mcp.tool()
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


@mcp.tool()
def twincat_stweep_format_cancel() -> str:
    """Cancel a running multi-file STweep format job.

    Sets a cancel flag; the job stops after the current file finishes
    (does not hard-kill mid-Formatcode). Poll twincat_stweep_format_progress until
    running=false / phase=canceled. Safe while STA is busy."""

    try:
        return _json(_get_bridge().cancel_format())
    except Exception as exc:
        return _json({"success": False, "canceled": False, "error": str(exc)})


@mcp.tool()
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
            path=path,
            recursive=recursive,
            timeout_s=timeout_seconds,
            confirm=confirm,
            wait=wait,
        ))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_export_library
# ================================================================

@mcp.tool()
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


@mcp.tool()
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


@mcp.tool()
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
    progress → twincat_export_check_artifacts → retry only if missing."""

    from export_guards import export_echo_fields, validate_export_target

    bridge = _get_bridge()
    sln_path = bridge._call_sta(lambda: bridge._sln_path, timeout=5) or ""
    plcproj_from_bridge = bridge._call_sta(
        lambda: bridge._plcproj_file_path, timeout=5,
    ) or ""

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


@mcp.tool()
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

    Empty output_dir/title/version → uses last export progress fields."""

    try:
        return _json(_get_bridge().check_export_artifacts(
            output_dir=output_dir,
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
        if _bridge is not None:
            _bridge.shutdown()
        _bridge = None
        return _json(result)
    except Exception as exc:
        if _bridge is not None:
            _bridge.shutdown()
        _bridge = None
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  Runtime / target (TE1000 COM — requires twincat_open)
# ================================================================

@mcp.tool()
def twincat_get_target() -> str:
    """Get the TwinCAT target AMS NetId (ITcSysManager2.GetTargetNetId).

    Requires an open XAE session (twincat_open)."""
    try:
        return _json(_get_bridge().get_target_net_id())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_set_target(net_id: str, confirm: bool = False) -> str:
    """Set the TwinCAT target AMS NetId (ITcSysManager2.SetTargetNetId).

    Requires confirm=true. Requires an open XAE session (twincat_open).
    Example net_id: \"5.80.201.232.1.1\" or \"127.0.0.1.1.1\".

    Safety: if net_id is not the running MCP Usermode Runtime, the result
    includes warnings + user_action_required (non_umrt_target_control)."""
    try:
        raw = _as_dict(_get_bridge().set_target_net_id(net_id, confirm=confirm))
        return _json(_attach_target_safety(
            raw, operation="twincat_set_target", net_id=net_id,
        ))
    except Exception as exc:
        return _json(_attach_target_safety(
            {"success": False, "error": str(exc)},
            operation="twincat_set_target",
            net_id=net_id,
        ))


@mcp.tool()
def twincat_activate(confirm: bool = False) -> str:
    """Activate the TwinCAT configuration (ITcSysManager.ActivateConfiguration).

    Same as \"Activate Configuration\" / Save To Registry in XAE. Writes the
    boot project to the selected target. Does NOT start TwinCAT — call
    twincat_start afterwards. Requires confirm=true and twincat_open.

    Structured fields: status, activate_ok, boot_written, boot_ok,
    build_outcome, licenses_ok, has_blocking_runtime_error. Use activate_ok
    (not log tails). Trial-license user_action_required only when a license
    error is detected. Disable I/O via twincat_io_set_disabled before UmRT
    activate (prereq is remembered for the session).

    Safety: non-UmRT targets get warnings + non_umrt_target_control
    (real IPC / external system)."""
    try:
        raw = _get_bridge().activate_configuration(confirm=confirm)
        return _json(_enrich_umrt_runtime_result(raw, operation="twincat_activate"))
    except Exception as exc:
        from user_actions import attach_user_actions, looks_like_license_error
        data = {"success": False, "error": str(exc), "activate_ok": False,
                "status": "failed", "licenses_ok": None}
        if looks_like_license_error(str(exc)):
            data = attach_user_actions(data, "umrt_trial_license")
            data["licenses_ok"] = False
            data["blocking_license_issue"] = True
        return _json(_attach_target_safety(data, operation="twincat_activate"))


@mcp.tool()
def twincat_start(confirm: bool = False) -> str:
    """Start or restart TwinCAT on the target (ITcSysManager.StartRestartTwinCAT).

    If TwinCAT is stopped it starts; if already running it restarts.
    TE1000 has no StopTwinCAT — use twincat_set_runtime_mode(mode=\"config\")
    via ADS to enter Config mode. Requires confirm=true and twincat_open.

    Structured fields: status, boot_ok, licenses_ok, has_blocking_runtime_error.
    Trial-license user_action_required only when license errors are detected.

    Safety: non-UmRT targets get warnings + non_umrt_target_control."""
    try:
        raw = _get_bridge().start_restart_twincat(confirm=confirm)
        return _json(_enrich_umrt_runtime_result(raw, operation="twincat_start"))
    except Exception as exc:
        from user_actions import attach_user_actions, looks_like_license_error
        data = {"success": False, "error": str(exc), "boot_ok": False,
                "status": "failed", "licenses_ok": None}
        if looks_like_license_error(str(exc)):
            data = attach_user_actions(data, "umrt_trial_license")
            data["licenses_ok"] = False
            data["blocking_license_issue"] = True
        return _json(_attach_target_safety(data, operation="twincat_start"))


@mcp.tool()
def twincat_task_list() -> str:
    """List Real-Time tasks under TIRT (ITcSmTreeItem children).

    Returns name, path_name, item_sub_type for each task.
    Requires twincat_open."""
    try:
        return _json(_get_bridge().list_tasks())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_task_info(task_path: str = "") -> str:
    """Get detailed task info via ProduceXml (cycle time, priority, …).

    task_path: full path (e.g. \"TIRT^PlcTask\") or bare task name.
    Requires twincat_open."""
    try:
        return _json(_get_bridge().get_task_info(task_path))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_io_list() -> str:
    """List I/O devices under TIID with Disabled state (ITcSmTreeItem).

    Needed before Usermode Runtime activate: UmRT has no EtherCAT; leave
    physical I/O disabled (InfoSys TC170x Limitations). Requires twincat_open."""
    try:
        return _json(_get_bridge().list_io_devices())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_io_set_disabled(
    path: str = "",
    disabled: bool = True,
    all_devices: bool = False,
    confirm: bool = False,
) -> str:
    """Enable/disable I/O devices via ITcSmTreeItem.Disabled (SMDS_DISABLED=1).

    Use before twincat_activate when targeting Usermode Runtime so SAFEOP
    does not fail on missing EtherCAT/hardware (AdsError 1823).

    path: full \"TIID^…\" or bare device name. Or set all_devices=true.
    Requires confirm=true and twincat_open.
    On success with all_devices=true, sets session prereq io_disabled_all."""
    try:
        data = _as_dict(_get_bridge().set_io_disabled(
            path=path,
            disabled=disabled,
            all_devices=all_devices,
            confirm=confirm,
        ))
        try:
            data["prereqs"] = dict(_get_bridge()._ensure_prereqs())
        except Exception:
            pass
        return _json(data)
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  Usermode Runtime (TC170x — own MCP instance)
# ================================================================

_umrt_controller = None


def _get_umrt():
    global _umrt_controller
    if _umrt_controller is None:
        from twincat_umrt_controller import UmrtController
        _umrt_controller = UmrtController()
    return _umrt_controller


def _umrt_instance_arg(instance: str = "") -> str:
    """Empty instance → this MCP session's default UmRT name."""
    if instance and str(instance).strip():
        return str(instance).strip()
    return _get_umrt().mcp_instance


@mcp.tool()
def twincat_umrt_status() -> str:
    """Status of TwinCAT 3 Usermode Runtime (TC170x) instances.

    Reports install paths, all ProgramData instances, running state,
    PIDs, and AmsNetIds. Marks this MCP session's instance
    (workspace-scoped name, or TWINCAT_UMRT_INSTANCE / pid mode).
    Does not require XAE / twincat_open."""
    try:
        from twincat_umrt_controller import status_to_dict
        return _json(status_to_dict(_get_umrt().status()))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_umrt_start(
    instance: str = "",
    confirm: bool = False,
    window_mode: str = "minimized",
) -> str:
    """Start a TwinCAT Usermode Runtime instance (TC170x).

    Default instance is session-scoped (UmRT_CursorMCP_<workspaceHash>),
    created from UmRT_Template on first start. Override with instance= or
    env TWINCAT_UMRT_INSTANCE. For one UmRT per MCP process set
    TWINCAT_UMRT_SESSION_MODE=pid. Runs alongside UmRT_Default / other
    sessions. Requires confirm=true. ADS tools then default to this NetId.

    window_mode:
      - minimized (default): Beckhoff Start.bat → minimized console window
      - hidden: no console window (CREATE_NO_WINDOW); preferred for MCP.
        Mode changes via twincat_start (COM), not console keys r/c/x.

    Returns umrt_console_window info. I/O disable is a non-blocking
    prerequisite reminder only when not yet satisfied in the MCP session.
    Trial-license user_action_required is NOT attached on start — only when
    activate/start later detect a license error (ask user in skill Step 0
    if licenses are unknown)."""
    try:
        from twincat_umrt_controller import op_to_dict
        from user_actions import attach_user_actions
        from mcp_errors import confirm_refused

        if not confirm:
            return _json(confirm_refused(
                "twincat_umrt_start",
                example_args={
                    "instance": instance or "",
                    "window_mode": window_mode or "minimized",
                    "confirm": True,
                },
            ))

        data = op_to_dict(
            _get_umrt().start(
                instance=_umrt_instance_arg(instance),
                confirm=confirm,
                window_mode=window_mode or "minimized",
            )
        )
        action_ids = ["umrt_console_window"]
        io_needed = True
        try:
            if HAS_WIN32 and _get_bridge()._ensure_prereqs().get("io_disabled_all"):
                io_needed = False
        except Exception:
            pass
        if io_needed:
            action_ids.append("umrt_io_disabled")
        return _json(attach_user_actions(data, *action_ids))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_umrt_stop(
    instance: str = "",
    confirm: bool = False,
) -> str:
    """Stop a TwinCAT Usermode Runtime instance by process name match.

    Empty instance stops this MCP session's default UmRT only — not the
    user's UmRT_Default or other sessions. Requires confirm=true."""
    try:
        from twincat_umrt_controller import op_to_dict
        from mcp_errors import confirm_refused

        if not confirm:
            return _json(confirm_refused(
                "twincat_umrt_stop",
                example_args={"instance": instance or "", "confirm": True},
            ))
        return _json(op_to_dict(
            _get_umrt().stop(instance=_umrt_instance_arg(instance),
                             confirm=confirm)
        ))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  ADS runtime / variables (pyads — XAE optional)
# ================================================================

def _resolve_ads_net_id(net_id: str = "") -> str:
    """Prefer explicit net_id, else running MCP UmRT, else session, else local."""
    if net_id and str(net_id).strip():
        return str(net_id).strip()
    try:
        umrt_id = _get_umrt().get_mcp_ams_net_id_if_running()
        if umrt_id:
            return umrt_id
    except Exception as exc:
        log.debug("ADS net_id from UmRT failed: %s", exc)
    try:
        if HAS_WIN32:
            bridge = _get_bridge()
            if bridge._sys_man or bridge._dte:
                tid = bridge.get_target_net_id()
                if getattr(tid, "success", False) and tid.net_id:
                    return tid.net_id
    except Exception as exc:
        log.debug("ADS net_id from session failed: %s", exc)
    from twincat_ads_client import local_net_id
    return local_net_id()


@mcp.tool()
def twincat_runtime_state(net_id: str = "", plc_port: int = 851) -> str:
    """Read TwinCAT System + PLC ADS readiness.

    Returns system ads_state (port 10000), plc_ads_state (plc_port, default
    851), ready_for_ads, blocking_reasons, and optional COM IsTwinCATStarted.
    ready_for_ads is true only when system and PLC are RUN and there is no
    fresh blocking runtime error. net_id optional — defaults to MCP UmRT,
    then session target, else local."""
    from twincat_ads_client import AdsClient, ads_available
    from readiness import compose_readiness

    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    plc_port = int(plc_port or 851)
    try:
        with AdsClient(resolved, port=10000) as ads:
            state = ads.read_state()
        system_ads = str(state.get("ads_state") or "")
        plc_ads = ""
        plc_err = ""
        try:
            with AdsClient(resolved, port=plc_port) as plc:
                plc_state = plc.read_state()
            plc_ads = str(plc_state.get("ads_state") or "")
            state["plc_device_state"] = plc_state.get("device_state")
        except Exception as exc:
            plc_err = str(exc)
            state["plc_error"] = plc_err

        com_started = None
        blocking = None
        try:
            if HAS_WIN32:
                st = _get_bridge().get_status()
                com_started = getattr(st, "twincat_runtime_started", None)
                try:
                    msgs = _get_bridge().get_runtime_messages(since_last_activate=True)
                    blocking = bool(getattr(msgs, "has_blocking_error", False))
                except Exception:
                    pass
        except Exception:
            pass
        state["com_is_twincat_started"] = com_started
        state["net_id"] = resolved
        ready = compose_readiness(
            system_ads_state=system_ads,
            plc_ads_state=plc_ads,
            plc_port=plc_port,
            has_blocking_runtime_error=blocking,
            net_id=resolved,
        )
        if plc_err and not plc_ads:
            ready["blocking_reasons"].append("plc_ads_read_failed")
            ready["ready_for_ads"] = False
        state.update(ready)
        return _json(state)
    except Exception as exc:
        return _json({"success": False, "net_id": resolved, "error": str(exc)})


@mcp.tool()
def twincat_set_runtime_mode(
    mode: str = "config",
    net_id: str = "",
    confirm: bool = False,
) -> str:
    """Set TwinCAT runtime mode via ADS System Service WriteControl.

    mode: \"run\" | \"config\" | \"stop\". This is how TwinCAT is stopped /
    switched to Config (TE1000 has no StopTwinCAT).
    Requires confirm=true. net_id optional.

    Safety: warns when the resolved NetId is not the MCP Usermode Runtime."""
    from twincat_ads_client import AdsClient, ads_available

    if not confirm:
        from mcp_errors import confirm_refused
        return _json(confirm_refused(
            "twincat_set_runtime_mode",
            example_args={"mode": mode, "net_id": net_id, "confirm": True},
        ))
    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=10000) as ads:
            result = ads.set_ads_state(mode)
        result["net_id"] = resolved
        return _json(_attach_target_safety(
            result,
            operation=f"twincat_set_runtime_mode({mode})",
            net_id=resolved,
        ))
    except Exception as exc:
        return _json(_attach_target_safety(
            {"success": False, "net_id": resolved, "error": str(exc)},
            operation=f"twincat_set_runtime_mode({mode})",
            net_id=resolved,
        ))


@mcp.tool()
def twincat_plc_start(
    net_id: str = "",
    port: int = 851,
    confirm: bool = False,
) -> str:
    """Start the PLC runtime via ADS WriteControl (AdsState.RUN).

    Default port 851 (first PLC runtime). Requires confirm=true.
    Response includes ready_for_ads after the mode change.

    Safety: warns when the resolved NetId is not the MCP Usermode Runtime."""
    from twincat_ads_client import AdsClient, ads_available
    from readiness import compose_readiness

    if not confirm:
        from mcp_errors import confirm_refused
        return _json(confirm_refused(
            "twincat_plc_start",
            example_args={"net_id": net_id, "port": port, "confirm": True},
        ))
    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=port) as ads:
            result = ads.set_ads_state("run")
        result["net_id"] = resolved
        result["port"] = port
        result["plc_start_ok"] = bool(result.get("success", True))
        sys_ads = ""
        try:
            with AdsClient(resolved, port=10000) as sys_ads_client:
                sys_ads = str(sys_ads_client.read_state().get("ads_state") or "")
        except Exception:
            pass
        plc_ads = str(result.get("ads_state") or "RUN")
        result.update(compose_readiness(
            system_ads_state=sys_ads,
            plc_ads_state=plc_ads,
            plc_port=port,
            plc_start_ok=result["plc_start_ok"],
            net_id=resolved,
        ))
        return _json(_attach_target_safety(
            result, operation="twincat_plc_start", net_id=resolved,
        ))
    except Exception as exc:
        return _json(_attach_target_safety(
            {"success": False, "net_id": resolved, "port": port, "error": str(exc),
             "plc_start_ok": False, "ready_for_ads": False},
            operation="twincat_plc_start",
            net_id=resolved,
        ))


@mcp.tool()
def twincat_plc_stop(
    net_id: str = "",
    port: int = 851,
    confirm: bool = False,
) -> str:
    """Stop the PLC runtime via ADS WriteControl (AdsState.STOP).

    Default port 851. Requires confirm=true.

    Safety: warns when the resolved NetId is not the MCP Usermode Runtime."""
    from twincat_ads_client import AdsClient, ads_available

    if not confirm:
        from mcp_errors import confirm_refused
        return _json(confirm_refused(
            "twincat_plc_stop",
            example_args={"net_id": net_id, "port": port, "confirm": True},
        ))
    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=port) as ads:
            result = ads.set_ads_state("stop")
        result["net_id"] = resolved
        result["port"] = port
        return _json(_attach_target_safety(
            result, operation="twincat_plc_stop", net_id=resolved,
        ))
    except Exception as exc:
        return _json(_attach_target_safety(
            {"success": False, "net_id": resolved, "port": port, "error": str(exc)},
            operation="twincat_plc_stop",
            net_id=resolved,
        ))


@mcp.tool()
def twincat_runtime_messages(
    max_chars: int = 12000,
    since_last_activate: bool = False,
    since_timestamp: float = 0.0,
) -> str:
    """Read TwinCAT runtime / activate messages from the XAE Output window.

    Returns TwinCAT + Build pane text, GetLastErrorMessages, classified
    findings, error_count/warning_count, has_blocking_runtime_error, sources,
    and history_incomplete. Prefer since_last_activate=true after
    twincat_activate to avoid stale pagefaults. ADS Logger history is not
    available (history_incomplete). Requires twincat_open."""
    try:
        return _json(_get_bridge().get_runtime_messages(
            max_chars=max_chars,
            since_last_activate=since_last_activate,
            since_timestamp=since_timestamp,
        ))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_verify_library_on_target(
    expected_version: str = "",
    library_name: str = "",
    library_plcproj_path: str = "",
    sample_plcproj_path: str = "",
    sample_reference_version: str = "",
    search_root: str = "",
) -> str:
    """Compare exported library version vs sample reference and Boot/_Libraries.

    Pass expected_version (or library_plcproj_path to read ProjectVersion).
    Optionally sample_reference_version / sample_plcproj_path and search_root
    (solution folder). On mismatch returns next_actions:
    refresh_references → rebuild → activate. If _Libraries is not found,
    verify_incomplete=true (not a fake PASS)."""
    from library_verify import verify_library_versions

    expected = (expected_version or "").strip()
    lib_name = (library_name or "").strip()
    if library_plcproj_path and os.path.isfile(library_plcproj_path):
        meta = _read_plcproj_meta(library_plcproj_path)
        if not expected:
            expected = meta.get("version") or ""
        if not lib_name:
            lib_name = meta.get("title") or meta.get("name") or ""

    roots: list[str] = []
    if search_root:
        roots.append(search_root)
    if sample_plcproj_path:
        roots.append(sample_plcproj_path)
    try:
        if HAS_WIN32:
            sln = _get_bridge()._call_sta(
                lambda: _get_bridge()._sln_path, timeout=5,
            ) or ""
            if sln:
                roots.append(sln)
    except Exception:
        pass

    return _json(verify_library_versions(
        expected_version=expected,
        library_name=lib_name,
        sample_plcproj_path=sample_plcproj_path,
        sample_reference_version=sample_reference_version,
        search_roots=roots,
    ))


@mcp.tool()
def twincat_umrt_e2e(
    sln_path: str,
    xae_version: str = "",
    window_mode: str = "hidden",
    plc_port: int = 851,
    symbol_prefix: str = "",
    read_symbols: str = "",
    write_symbol: str = "",
    write_value: str = "",
    write_plc_type: str = "",
    skip_write: bool = False,
    confirm: bool = False,
) -> str:
    """Run the full UmRT systemtest chain (same steps as twincat3-umrt-systemtest).

    Requires confirm=true. Orchestrates: UmRT start → license pre-flight check →
    open (auto-detects open TcXaeShell/VS instances) → I/O disable →
    set target → activate → start → runtime_messages → sys/PLC RUN →
    ADS symbols + read_list (+ optional write). Prefer this over 12 separate
    tool calls when running an online test. Uses live TwinCAT on this host."""
    from mcp_errors import confirm_refused

    if not confirm:
        return _json(confirm_refused(
            "twincat_umrt_e2e",
            example_args={
                "sln_path": sln_path,
                "xae_version": xae_version or "",
                "confirm": True,
            },
        ))
    if not sln_path or not os.path.isfile(sln_path):
        return _json({
            "success": False,
            "ok": False,
            "error_code": "sln_not_found",
            "error": f"Solution not found: {sln_path}",
            "message": f"Solution not found: {sln_path}",
        })

    try:
        from systemtest.umrt_chain import (
            SystemtestConfig,
            build_live_backends,
            run_umrt_systemtest,
        )
    except Exception as exc:
        return _json({
            "success": False,
            "error": f"umrt_chain import failed: {exc}",
        })

    reads: list[str] = []
    if read_symbols and str(read_symbols).strip():
        try:
            parsed = json.loads(read_symbols)
            if isinstance(parsed, list):
                reads = [str(x) for x in parsed]
            else:
                reads = [s.strip() for s in str(read_symbols).split(",") if s.strip()]
        except json.JSONDecodeError:
            reads = [s.strip() for s in str(read_symbols).split(",") if s.strip()]

    config = SystemtestConfig(
        sln_path=sln_path,
        xae_version=xae_version or "",
        window_mode=window_mode or "hidden",
        plc_port=int(plc_port or 851),
        symbol_prefix=symbol_prefix or "",
        read_symbols=reads,
        write_symbol=write_symbol or "",
        write_value=write_value or "",
        write_plc_type=write_plc_type or "",
        skip_write=bool(skip_write),
    )
    try:
        report = run_umrt_systemtest(config, build_live_backends())
        return _json({
            "success": bool(report.passed),
            "ok": bool(report.passed),
            "passed": bool(report.passed),
            "net_id": report.net_id,
            "ask_user": list(report.ask_user or []),
            "summary_lines": list(report.summary_lines or []),
            "checklist": report.format_checklist(),
            "steps": [
                {
                    "name": s.name,
                    "passed": s.passed,
                    "detail": s.detail,
                }
                for s in report.steps
            ],
            "message": "UmRT E2E PASS" if report.passed else "UmRT E2E FAIL",
        })
    except Exception as exc:
        return _json({"success": False, "ok": False, "error": str(exc)})


@mcp.tool()
def twincat_ads_symbols(
    prefix: str = "",
    name_contains: str = "",
    type_contains: str = "",
    regex: str = "",
    max_symbols: int = 500,
    net_id: str = "",
    port: int = 851,
) -> str:
    """List top-level ADS symbols on the PLC (filtered).

    Filters: prefix (e.g. \"P_Sample.\"), name_contains, type_contains
    (e.g. \"FB_Lib\"), regex. max_symbols default 500 (cap 5000).
    Nested/private paths are often missing here but still R/W via
    twincat_ads_read/write with the full instance path (incl. members of
    library FBs whose type has {attribute 'hide'}; not single-var hide).
    PLC must be RUN (twincat_plc_start if ADSSTATE_INVALID)."""
    from twincat_ads_client import AdsClient, ads_available

    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=port) as ads:
            result = ads.list_symbols(
                prefix=prefix,
                name_contains=name_contains,
                type_contains=type_contains,
                regex=regex,
                max_symbols=max_symbols,
            )
        result["net_id"] = resolved
        result["port"] = port
        return _json(result)
    except Exception as exc:
        return _json({
            "success": False,
            "net_id": resolved,
            "port": port,
            "error": str(exc),
        })


@mcp.tool()
def twincat_ads_read(
    symbol: str,
    net_id: str = "",
    port: int = 851,
) -> str:
    """Read a PLC variable by full ADS symbol path.

    Examples: \"MAIN.bEnable\", \"P_Sample.fbController._bGateOpen\",
    \"P_Sample.fbDevice1._bValid\" (member of hide base FB).
    Nested/private paths work even if absent from twincat_ads_symbols.
    Single-variable {attribute 'hide'} / hide PROPERTY → not found.
    For many symbols at once use twincat_ads_read_list. Default port 851."""
    from twincat_ads_client import AdsClient, ads_available

    if not symbol or not str(symbol).strip():
        return _json({"success": False, "error": "symbol is empty"})
    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=port) as ads:
            result = ads.read_by_name(symbol.strip())
        result["net_id"] = resolved
        result["port"] = port
        return _json(result)
    except Exception as exc:
        return _json({
            "success": False,
            "symbol": symbol,
            "net_id": resolved,
            "port": port,
            "error": str(exc),
        })


@mcp.tool()
def twincat_ads_read_list(
    symbols: str,
    net_id: str = "",
    port: int = 851,
    ads_sub_commands: int = 500,
) -> str:
    """Read many PLC variables in one ADS Sum-Command batch.

    symbols: JSON array '[\"MAIN.bEnable\", \"P_Sample.…\"]' or
    newline/comma-separated paths. Uses pyads read_list_by_name (chunked by
    ads_sub_commands, default/max 500). Returns values map path→value.
    Prefer this over many twincat_ads_read calls for large lists."""
    from twincat_ads_client import AdsClient, ads_available, parse_symbol_list

    names = parse_symbol_list(symbols)
    if not names:
        return _json({"success": False, "error": "symbols list is empty"})
    if len(names) > 2000:
        return _json({
            "success": False,
            "error": f"Too many symbols ({len(names)}); max 2000 per call",
        })
    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=port) as ads:
            result = ads.read_list_by_name(
                names, ads_sub_commands=ads_sub_commands,
            )
        result["net_id"] = resolved
        result["port"] = port
        return _json(result)
    except Exception as exc:
        return _json({
            "success": False,
            "net_id": resolved,
            "port": port,
            "error": str(exc),
        })


@mcp.tool()
def twincat_ads_write(
    symbol: str,
    value: str,
    plc_type: str = "",
    net_id: str = "",
    port: int = 851,
    confirm: bool = False,
) -> str:
    """Write a PLC variable by full ADS symbol path.

    Same path rules as twincat_ads_read (nested/private OK; type-level hide
    OK via instance path; single-var hide not accessible).
    value is a string, converted via plc_type when given
    (BOOL, INT, DINT, UINT, UDINT, REAL, LREAL, STRING, BYTE, WORD, DWORD)
    or inferred. For many symbols use twincat_ads_write_list.
    Requires confirm=true."""
    from twincat_ads_client import AdsClient, ads_available
    from mcp_errors import confirm_refused

    if not confirm:
        return _json(confirm_refused(
            "twincat_ads_write",
            example_args={
                "symbol": symbol,
                "value": value,
                "plc_type": plc_type,
                "net_id": net_id,
                "port": port,
                "confirm": True,
            },
        ))
    if not symbol or not str(symbol).strip():
        return _json({"success": False, "error": "symbol is empty"})
    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=port) as ads:
            result = ads.write_by_name(
                symbol.strip(), value, plc_type=plc_type or None,
            )
        result["net_id"] = resolved
        result["port"] = port
        return _json(result)
    except Exception as exc:
        return _json({
            "success": False,
            "symbol": symbol,
            "net_id": resolved,
            "port": port,
            "error": str(exc),
        })


@mcp.tool()
def twincat_ads_write_list(
    values: str,
    net_id: str = "",
    port: int = 851,
    ads_sub_commands: int = 500,
    confirm: bool = False,
) -> str:
    """Write many PLC variables in one ADS Sum-Command batch.

    values: JSON object '{\"MAIN.bEnable\": true, \"P_Sample.…._nX\": 2}'.
    Uses pyads write_list_by_name (chunked). Requires confirm=true."""
    from twincat_ads_client import (
        AdsClient, ads_available, parse_symbol_value_map,
    )
    from mcp_errors import confirm_refused

    if not confirm:
        return _json(confirm_refused(
            "twincat_ads_write_list",
            example_args={
                "values": values,
                "net_id": net_id,
                "port": port,
                "confirm": True,
            },
        ))
    try:
        payload = parse_symbol_value_map(values)
    except Exception as exc:
        return _json({"success": False, "error": f"Invalid values JSON: {exc}"})
    if not payload:
        return _json({"success": False, "error": "values object is empty"})
    if len(payload) > 2000:
        return _json({
            "success": False,
            "error": f"Too many symbols ({len(payload)}); max 2000 per call",
        })
    if not ads_available():
        return _json({"success": False, "error": "pyads not installed. pip install pyads"})
    resolved = _resolve_ads_net_id(net_id)
    try:
        with AdsClient(resolved, port=port) as ads:
            result = ads.write_list_by_name(
                payload, ads_sub_commands=ads_sub_commands,
            )
        result["net_id"] = resolved
        result["port"] = port
        return _json(result)
    except Exception as exc:
        return _json({
            "success": False,
            "net_id": resolved,
            "port": port,
            "error": str(exc),
        })


# ================================================================
#  Post-migration ST formatting helper
# ================================================================

_AUTO_GEN_MARKER = "AUTO-GENERATED"
_TC_EXTENSIONS = {".tcpou", ".tcdut", ".tcgvl", ".tcio"}


def _detect_member_filter(file_path: str) -> str:
    """Detect whether a TcPOU file contains only methods, actions, or properties.

    Returns a member_filter value ("all_methods", "all_actions",
    "all_properties") when exactly one member type is present, otherwise "".
    """
    try:
        with open(file_path, "r", encoding="utf-8-sig") as fh:
            content = fh.read()
    except Exception:
        return ""

    has_method = "<Method " in content or "<Method>" in content
    has_action = "<Action " in content or "<Action>" in content
    has_property = "<Property " in content or "<Property>" in content

    types_found = sum([has_method, has_action, has_property])
    if types_found == 1:
        if has_method:
            return "all_methods"
        if has_action:
            return "all_actions"
        if has_property:
            return "all_properties"
    return ""


def _file_has_auto_generated(file_path: str) -> bool:
    """Check if a file contains the AUTO-GENERATED migration marker."""
    try:
        with open(file_path, "r", encoding="utf-8-sig") as fh:
            head = fh.read(4096)
        return _AUTO_GEN_MARKER in head
    except Exception:
        return False


def _collect_format_targets(
    input_path: str, output_path: str, swap: bool, force: bool
) -> list[str]:
    """Determine which output files/directories to format after migration.

    Returns a list of absolute file paths that are TwinCAT ST files
    with the AUTO-GENERATED marker.
    """
    inp = os.path.abspath(input_path)

    if swap or force:
        if os.path.isfile(inp):
            candidates = [inp]
        elif os.path.isdir(inp):
            candidates = []
            for root, _dirs, files in os.walk(inp):
                for f in files:
                    if os.path.splitext(f)[1].lower() in _TC_EXTENSIONS:
                        candidates.append(os.path.join(root, f))
        else:
            return []
        return [c for c in candidates if _file_has_auto_generated(c)]

    if output_path:
        target = os.path.abspath(output_path)
    elif os.path.isfile(inp):
        stem, ext = os.path.splitext(inp)
        target = f"{stem}_st_generated{ext}"
    elif os.path.isdir(inp):
        parent = os.path.dirname(inp)
        base = os.path.basename(inp)
        candidates = []
        for entry in os.listdir(parent):
            if entry.startswith(f"{base}_st_generated"):
                full = os.path.join(parent, entry)
                if os.path.isdir(full):
                    candidates.append(full)
        if not candidates:
            return []
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        target = candidates[0]
    else:
        return []

    if not os.path.exists(target):
        return []

    if os.path.isfile(target):
        if _file_has_auto_generated(target):
            return [target]
        return []

    result = []
    for root, _dirs, files in os.walk(target):
        for f in files:
            if os.path.splitext(f)[1].lower() in _TC_EXTENSIONS:
                fp = os.path.join(root, f)
                if _file_has_auto_generated(fp):
                    result.append(fp)
    return result


def _format_after_migrate(
    input_path: str,
    output_path: str,
    swap: bool,
    force: bool,
    dry_run: bool,
    analyze_only: bool,
    exit_code: int,
) -> dict:
    """Run Python formatter on migration output files.

    Returns a dict with formatting summary to attach to the migration result.
    Silently returns an empty dict if no formatting is needed or possible.
    """
    if exit_code != 0 or dry_run or analyze_only:
        return {}

    targets = _collect_format_targets(input_path, output_path, swap, force)
    if not targets:
        return {}

    from formatter.config import load_config
    from formatter.file_processor import process_batch
    from formatter.types import FormatRegion, FormatScope, MemberFilter as MF

    total_formatted = 0
    total_errors = 0
    file_results = []

    for fpath in targets:
        mf_str = _detect_member_filter(fpath)
        scope = None
        if mf_str:
            scope = FormatScope(
                region=FormatRegion.IMPLEMENTATION,
                member_filter=MF(mf_str),
            )

        try:
            cfg = load_config(project_root=os.path.dirname(fpath))
            batch = process_batch(
                [fpath], cfg,
                dry_run=False,
                validate=True,
                format_st=True,
                format_xml=True,
                sort_xml=False,
                scope=scope,
            )
            for r in batch.results:
                entry = {"file": os.path.basename(r.path), "changed": r.changed, "success": r.success}
                if r.errors:
                    entry["errors"] = list(r.errors)
                file_results.append(entry)
            total_formatted += batch.formatted
            total_errors += batch.errors
        except Exception as exc:
            file_results.append({"file": os.path.basename(fpath), "changed": False, "success": False, "errors": [str(exc)]})
            total_errors += 1

    return {
        "format_after_migrate": {
            "files_total": len(targets),
            "files_formatted": total_formatted,
            "files_errors": total_errors,
            "results": file_results,
        }
    }


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

    result = {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    }
    fmt = _format_after_migrate(input, output, swap, force, dry_run, analyze_only, exit_code)
    result.update(fmt)
    return _json(result)


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

    result = {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    }
    fmt = _format_after_migrate(input, output, swap, force, dry_run, analyze_only, exit_code)
    result.update(fmt)
    return _json(result)


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

    result = {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    }
    fmt = _format_after_migrate(input, output, swap, force, dry_run, analyze_only, exit_code)
    result.update(fmt)
    return _json(result)


# ================================================================
#  twincat_autodocs  (pure Python -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
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

    from pathlib import Path

    from autodocs.paths import resolve_output_root
    from autodocs.pipeline import process_folder

    input_path = Path(input)

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
        output_path = resolve_output_root(input_path, output or None)
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
    """Parse .tsproj XML → resolve PLC projects via .xti or inline PrjFilePath."""
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
        if xti_file:
            xti_path = os.path.normpath(os.path.join(config_plc_dir, xti_file))
            if os.path.isfile(xti_path):
                info = _parse_xti(xti_path)
                if info:
                    projects.append(info)
                    continue

        prj_file_path = proj_elem.get("PrjFilePath", "")
        if prj_file_path:
            abs_plcproj = os.path.normpath(
                os.path.join(tsproj_dir, prj_file_path)
            )
            if os.path.isfile(abs_plcproj):
                name = proj_elem.get("Name", "")
                projects.append({"name": name, "plcproj_path": abs_plcproj})

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

def _auto_detect_plcproj(sln_path: str = "") -> str:
    """Find the first .plcproj file near the solution or git repo root."""
    excludes = {"samples", "versions", "_libraries", ".git", "node_modules", "_compileinfo"}

    search_roots: list[str] = []
    if sln_path:
        sln_dir = os.path.dirname(sln_path) if os.path.isfile(sln_path) else sln_path
        if os.path.isdir(sln_dir):
            search_roots.append(sln_dir)
        repo = _find_repo_root(sln_path)
        if repo and repo != sln_dir and os.path.isdir(repo):
            search_roots.append(repo)
    if not search_roots:
        try:
            bridge = _get_bridge()
            b_sln = bridge._call_sta(lambda: bridge._sln_path, timeout=2) or ""
            if b_sln and os.path.isfile(b_sln):
                b_dir = os.path.dirname(b_sln)
                if os.path.isdir(b_dir):
                    search_roots.append(b_dir)
                b_repo = _find_repo_root(b_sln)
                if b_repo and b_repo != b_dir and os.path.isdir(b_repo):
                    search_roots.append(b_repo)
        except Exception:
            pass

    if not search_roots:
        search_roots.append(os.getcwd())

    for root_dir in search_roots:
        if not os.path.isdir(root_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [d for d in dirnames if d.lower() not in excludes]
            for f in filenames:
                if f.lower().endswith(".plcproj"):
                    return os.path.abspath(os.path.join(dirpath, f))
    return ""


def _resolve_plcproj_path(
    plcproj_path: str = "",
    sln_path: str = "",
    plcproj_from_bridge: str = "",
) -> str:
    """Resolve .plcproj path with strict priority:
    1. Explicit non-empty parameter (absolute, relative, or basename).
    2. Active XAE session (plcproj_from_bridge or search in active solution dir).
    3. Auto-detection near sln_path or cwd.
    """
    if plcproj_path and str(plcproj_path).strip():
        raw = str(plcproj_path).strip().strip('"').strip("'")
        if os.path.isabs(raw) and os.path.isfile(raw):
            return os.path.abspath(os.path.normpath(raw))

        # Check relative paths
        candidates = []
        if sln_path:
            sln_dir = os.path.dirname(sln_path) if os.path.isfile(sln_path) else sln_path
            candidates.append(os.path.join(sln_dir, raw))
            repo = _find_repo_root(sln_path)
            if repo and repo != sln_dir:
                candidates.append(os.path.join(repo, raw))
        candidates.append(os.path.join(os.getcwd(), raw))
        candidates.append(os.path.abspath(raw))
        for c in candidates:
            if os.path.isfile(c):
                return os.path.abspath(os.path.normpath(c))

        # Check basename match
        base_name = raw if raw.lower().endswith(".plcproj") else f"{raw}.plcproj"
        search_dirs = []
        if sln_path:
            sln_dir = os.path.dirname(sln_path) if os.path.isfile(sln_path) else sln_path
            if os.path.isdir(sln_dir):
                search_dirs.append(sln_dir)
            repo = _find_repo_root(sln_path)
            if repo and repo not in search_dirs and os.path.isdir(repo):
                search_dirs.append(repo)
        if not search_dirs:
            search_dirs.append(os.getcwd())

        excludes = {"samples", "versions", "_libraries", ".git", "node_modules", "_compileinfo"}
        for sdir in search_dirs:
            if not os.path.isdir(sdir):
                continue
            for dirpath, dirnames, files in os.walk(sdir):
                dirnames[:] = [d for d in dirnames if d.lower() not in excludes]
                for f in files:
                    if f.lower() == base_name.lower():
                        return os.path.abspath(os.path.join(dirpath, f))

    # Priority 2: Active bridge session
    if plcproj_from_bridge and os.path.isfile(plcproj_from_bridge):
        return os.path.abspath(os.path.normpath(plcproj_from_bridge))

    # Priority 3: Auto-detect from sln_path or bridge
    if sln_path:
        found = _auto_detect_plcproj(sln_path)
        if found:
            return found

    return _auto_detect_plcproj("")


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
        keys = (
            "title", "version", "company", "name", "released",
            "project_category", "is_library_project", "plcproj_path",
        )
        return {k: info[k] for k in keys if k in info}
    except Exception:
        return {}


def _find_repo_root(start_path: str = "") -> str:
    """Find the git repo root by walking upward from start_path."""
    if start_path:
        d = os.path.dirname(start_path) if os.path.isfile(start_path) else start_path
    else:
        d = os.getcwd()
    for _ in range(8):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


# ================================================================
#  twincat_infosys_mshc_search / twincat_infosys_mshc_read
# ================================================================

_infosys_mshc_cache: Dict[str, InfoSysMshcIndex] = {}


def _get_infosys_mshc(language: str = "en", file_path: str = "") -> InfoSysMshcIndex:
    mshc = resolve_mshc_path(language, file_path)
    if mshc not in _infosys_mshc_cache:
        _infosys_mshc_cache[mshc] = InfoSysMshcIndex(mshc)
    return _infosys_mshc_cache[mshc]


@mcp.tool()
def twincat_infosys_mshc_search(
    query: str,
    language: str = "en",
    file_path: str = "",
    limit: int = 10,
    mode: str = "auto",
    auto_read: bool = True,
    library: str = "",
    parent: str = "",
    format: str = "markdown",
) -> str:
    """Search the local Beckhoff InfoSys offline documentation (.mshc).

    Searches the locally installed TwinCAT 3 documentation archive
    (~55k pages) for FB_, ST_, E_, I_, F_, M_, P_ symbols, articles, attributes,
    and any documentation content.

    language: "en" (default) for English docs, "de" for German docs.

    Modes:
      - auto (default): exact title > prefix > substring > BM25 fulltext
      - title: title-only matching
      - symbol: title-only, filtered to IEC symbols (FB, ST, E, I, F, M, P)
      - fulltext: BM25-ranked keyword search (SQLite FTS5), fast (~1-3ms)

    Optional filters:
      - library: filter to a specific library (e.g. "Tc3_JsonXml", "Tc3_IotBase")
      - parent: filter to a specific parent symbol (e.g. "FB_JsonDomParser")

    Output format:
      - format: "markdown" (default, token-efficient table/codeblock layout) or "json"

    auto_read (default True): When the top result scores 100,
    automatically reads the page structure (syntax, inputs, outputs, methods, requirements)
    without full text bloat to preserve LLM token budget.

    Requires TwinCAT 3 offline documentation installed via
    Help > Add and Remove Help Content in TcXaeShell."""

    try:
        idx = _get_infosys_mshc(language, file_path)
        result = idx.search(
            query,
            limit=limit,
            mode=mode,
            library=library,
            parent=parent,
        )
        if (
            auto_read
            and result.get("count", 0) >= 1
            and result["results"][0].get("score") == 100
        ):
            top = result["results"][0]
            try:
                page = idx.read_page(top["path"], include_full_text=False)
                result["auto_read"] = page
            except Exception:
                pass

        if format == "json":
            return _json(result)
        return format_search_markdown(result)
    except FileNotFoundError as exc:
        err_code = "MSHC_NOT_INSTALLED" if "not found" in str(exc).lower() else "PAGE_NOT_FOUND"
        if format == "json":
            return _json({"success": False, "error_code": err_code, "error": str(exc)})
        return f"**Error [{err_code}]:** {exc}"
    except Exception as exc:
        if format == "json":
            return _json({"success": False, "error_code": "INTERNAL_ERROR", "error": str(exc)})
        return f"**Error [INTERNAL_ERROR]:** {exc}"


@mcp.tool()
def twincat_infosys_mshc_read(
    path: str,
    language: str = "en",
    file_path: str = "",
    include_full_text: bool = False,
    format: str = "markdown",
) -> str:
    """Read a specific page from the local Beckhoff InfoSys offline documentation (.mshc).

    Returns structured content including title, library, parent symbol, syntax block,
    VAR_INPUT/VAR_OUTPUT tables, methods list, and requirements.

    language: "en" (default) for English docs, "de" for German docs.
    include_full_text: default False to save tokens (<500 tokens). Set True for full unparsed body.
    format: "markdown" (default, token-efficient layout) or "json".

    Use twincat_infosys_mshc_search first to find the internal path,
    then pass it here to read the page content."""

    try:
        idx = _get_infosys_mshc(language, file_path)
        page = idx.read_page(path, include_full_text=include_full_text)
        if format == "json":
            return _json(page)
        return format_page_markdown(page)
    except FileNotFoundError as exc:
        err_code = "MSHC_NOT_INSTALLED" if "not found" in str(exc).lower() else "PAGE_NOT_FOUND"
        if format == "json":
            return _json({"success": False, "error_code": err_code, "error": str(exc)})
        return f"**Error [{err_code}]:** {exc}"
    except Exception as exc:
        if format == "json":
            return _json({"success": False, "error_code": "INTERNAL_ERROR", "error": str(exc)})
        return f"**Error [INTERNAL_ERROR]:** {exc}"


# ================================================================
#  Python ST formatter (file-based, no COM) — twincat_format_* tools
# ================================================================

import threading

_format_lock = threading.Lock()
_format_progress: dict = {}


@mcp.tool()
def twincat_format(
    path: str,
    recursive: bool = True,
    dry_run: bool = False,
    validate: bool = True,
    format_xml: bool = True,
    sort_elements: bool = False,
    config_path: str = "",
    region: str = "all",
    member: str = "",
    member_filter: str = "",
    project: str = "",
) -> str:
    """Format TwinCAT3 ST files (*.TcPOU, *.TcDUT, *.TcGVL, *.TcIO).

    Pure Python file-based formatter ÔÇö no XAE/COM needed.
    Formats ST code (indentation, alignment, wrapping, keywords) AND
    XML structure (attribute order, element sorting, CDATA handling).

    path: file or directory to format
    recursive: recurse into subdirectories (default True)
    dry_run: report changes without writing (default False)
    validate: run XML validation checks (default True)
    format_xml: format XML structure (default True)
    sort_elements: sort XML elements alphabetically (default False; opt-in)
    config_path: custom .stformat.json config file path (optional)
    region: "all" (default), "declaration", or "implementation" ÔÇö limit to specific code sections
    member: specific Method/Action/Property name to format (e.g. "M_Init")
    member_filter: "all_methods", "all_actions", or "all_properties" ÔÇö format only that member type
    project: path to .sln or .plcproj ÔÇö discovers all TwinCAT files (overrides path)"""

    from formatter.config import load_config, config_to_dict
    from formatter.file_processor import discover_files, discover_project_files, process_batch
    from formatter.types import FormatRegion, FormatScope, MemberFilter as MF

    global _format_progress
    with _format_lock:
        _format_progress = {"status": "running", "path": path, "files_done": 0, "files_total": 0}

    try:
        cfg = load_config(config_path=config_path or None, project_root=path if os.path.isdir(path) else os.path.dirname(path))

        # Build scope
        scope = None
        fmt_region = FormatRegion(region) if region != "all" else FormatRegion.ALL
        mf = None
        if member_filter:
            mf = MF(member_filter)
        if fmt_region != FormatRegion.ALL or member or mf:
            scope = FormatScope(region=fmt_region, member_filter=mf, member_name=member)

        # Discover files
        if project:
            files = discover_project_files(project)
        else:
            files = discover_files([path], recursive=recursive)

        with _format_lock:
            _format_progress["files_total"] = len(files)

        if not files:
            return _json({"success": True, "message": "No formattable files found", "files": 0})

        batch = process_batch(
            files, cfg,
            dry_run=dry_run,
            validate=validate,
            format_st=True,
            format_xml=format_xml,
            sort_xml=sort_elements,
            scope=scope,
        )

        with _format_lock:
            _format_progress = {"status": "done", "files_done": batch.total, "files_total": batch.total}

        results_list = []
        for r in batch.results:
            entry = {"file": os.path.basename(r.path), "changed": r.changed, "success": r.success}
            if r.errors:
                entry["errors"] = list(r.errors)
            if r.warnings:
                entry["warnings"] = list(r.warnings)
            if r.diff:
                entry["diff"] = r.diff
            results_list.append(entry)

        return _json({
            "success": batch.errors == 0,
            "total": batch.total,
            "formatted": batch.formatted,
            "unchanged": batch.unchanged,
            "errors": batch.errors,
            "dry_run": dry_run,
            "results": results_list,
        })
    except Exception as exc:
        with _format_lock:
            _format_progress = {"status": "error", "error": str(exc)}
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_format_progress() -> str:
    """Poll the progress of a running twincat_format operation."""
    with _format_lock:
        return _json(_format_progress)


@mcp.tool()
def twincat_format_validate(
    path: str,
    recursive: bool = True,
    config_path: str = "",
) -> str:
    """Validate TwinCAT3 XML files without formatting.

    Checks: GUID format/uniqueness, Name match, required elements,
    SpecialFunc values, FolderPath consistency, interface rules.

    path: file or directory to validate
    recursive: recurse into subdirectories (default True)
    config_path: custom config file path (optional)"""

    from formatter.config import load_config
    from formatter.file_processor import discover_files, process_batch

    try:
        cfg = load_config(config_path=config_path or None, project_root=path if os.path.isdir(path) else os.path.dirname(path))
        files = discover_files([path], recursive=recursive)

        if not files:
            return _json({"success": True, "message": "No files to validate", "files": 0})

        batch = process_batch(
            files, cfg,
            dry_run=True,
            validate=True,
            format_st=False,
            format_xml=False,
        )

        issues_list = []
        for issue in batch.validation_issues:
            issues_list.append({
                "level": issue.level,
                "file": os.path.basename(issue.file),
                "line": issue.line,
                "rule": issue.rule,
                "message": issue.message,
            })

        return _json({
            "success": len([i for i in batch.validation_issues if i.level == "error"]) == 0,
            "total_files": batch.total,
            "issues": issues_list,
        })
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


@mcp.tool()
def twincat_format_config(
    project_path: str = "",
    config_path: str = "",
) -> str:
    """Show the active formatter configuration.

    Shows merged config (defaults + user overrides from .stformat.json).

    project_path: project root to search for .stformat.json (optional)
    config_path: explicit config file to load (optional)"""

    from formatter.config import load_config, config_to_dict

    try:
        cfg = load_config(config_path=config_path or None, project_root=project_path or None)
        return _json({"success": True, "config": config_to_dict(cfg)})
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  Entry point
# ================================================================

if __name__ == "__main__":
    mcp.run()
