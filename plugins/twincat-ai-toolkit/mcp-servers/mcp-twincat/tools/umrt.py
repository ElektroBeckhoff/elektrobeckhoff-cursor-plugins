"""
TwinCAT Usermode Runtime (TC170x), runtime mode, messages, and E2E systemtest MCP tools.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from twincat_automation_interface import HAS_WIN32
from .common import _as_dict, _clean_path, _find_repo_root, _json, _read_plcproj_meta
from .solution import _get_bridge

log = logging.getLogger("twincat-mcp.umrt")

_umrt_controller = None


def _get_umrt():
    global _umrt_controller
    import sys
    srv = sys.modules.get("server")
    if srv and "_get_umrt" in srv.__dict__ and srv._get_umrt is not _get_umrt:
        return srv._get_umrt()
    if _umrt_controller is None:
        from twincat_umrt_controller import UmrtController
        _umrt_controller = UmrtController()
    return _umrt_controller


def _umrt_instance_arg(instance: str = "") -> str:
    """Empty instance -> this MCP session's default UmRT name."""
    if instance and str(instance).strip():
        return str(instance).strip()
    return _get_umrt().mcp_instance


def _target_context(net_id: str = "") -> dict:
    """Resolve whether a runtime-control NetId is the MCP Usermode Runtime.

    net_id empty -> use current XAE target (when a session is open).
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


def _target_is_mcp_umrt() -> bool:
    """True when XAE target NetId matches the running MCP UmRT instance."""
    return bool(_target_context().get("target_is_mcp_umrt"))


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
      - minimized (default): Beckhoff Start.bat -> minimized console window
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
    refresh_references -> rebuild -> activate. If _Libraries is not found,
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

    Requires confirm=true. Orchestrates: UmRT start -> license pre-flight check ->
    open (auto-detects open TcXaeShell/VS instances) -> I/O disable ->
    set target -> activate -> start -> runtime_messages -> sys/PLC RUN ->
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
    sln_path = _clean_path(sln_path)
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


def register_tools(mcp: Any) -> None:
    """Register Usermode Runtime, mode control, and systemtest tools on FastMCP server."""
    mcp.tool()(twincat_umrt_status)
    mcp.tool()(twincat_umrt_start)
    mcp.tool()(twincat_umrt_stop)
    mcp.tool()(twincat_runtime_state)
    mcp.tool()(twincat_set_runtime_mode)
    mcp.tool()(twincat_plc_start)
    mcp.tool()(twincat_plc_stop)
    mcp.tool()(twincat_runtime_messages)
    mcp.tool()(twincat_verify_library_on_target)
    mcp.tool()(twincat_umrt_e2e)
