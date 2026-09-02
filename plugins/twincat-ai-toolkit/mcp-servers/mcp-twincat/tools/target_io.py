"""
Target AMS NetId, configuration activation, task inspection, and I/O management MCP tools.
"""

from __future__ import annotations

from typing import Any

from .common import _as_dict, _json
from .solution import _get_bridge
from .umrt import _attach_target_safety, _enrich_umrt_runtime_result


def twincat_get_target() -> str:
    """Get the TwinCAT target AMS NetId (ITcSysManager2.GetTargetNetId).

    Requires an open XAE session (twincat_open)."""
    try:
        return _json(_get_bridge().get_target_net_id())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


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
        data = {
            "success": False,
            "error": str(exc),
            "activate_ok": False,
            "status": "failed",
            "licenses_ok": None,
        }
        if looks_like_license_error(str(exc)):
            data = attach_user_actions(data, "umrt_trial_license")
            data["licenses_ok"] = False
            data["blocking_license_issue"] = True
        return _json(_attach_target_safety(data, operation="twincat_activate"))


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
        data = {
            "success": False,
            "error": str(exc),
            "boot_ok": False,
            "status": "failed",
            "licenses_ok": None,
        }
        if looks_like_license_error(str(exc)):
            data = attach_user_actions(data, "umrt_trial_license")
            data["licenses_ok"] = False
            data["blocking_license_issue"] = True
        return _json(_attach_target_safety(data, operation="twincat_start"))


def twincat_task_list() -> str:
    """List Real-Time tasks under TIRT (ITcSmTreeItem children).

    Returns name, path_name, item_sub_type for each task.
    Requires twincat_open."""
    try:
        return _json(_get_bridge().list_tasks())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


def twincat_task_info(task_path: str = "") -> str:
    """Get detailed task info via ProduceXml (cycle time, priority, …).

    task_path: full path (e.g. \"TIRT^PlcTask\") or bare task name.
    Requires twincat_open."""
    try:
        return _json(_get_bridge().get_task_info(task_path))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


def twincat_io_list() -> str:
    """List I/O devices under TIID with Disabled state (ITcSmTreeItem).

    Needed before Usermode Runtime activate: UmRT has no EtherCAT; leave
    physical I/O disabled (InfoSys TC170x Limitations). Requires twincat_open."""
    try:
        return _json(_get_bridge().list_io_devices())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


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


def register_tools(mcp: Any) -> None:
    """Register target and I/O management tools on FastMCP server."""
    mcp.tool()(twincat_get_target)
    mcp.tool()(twincat_set_target)
    mcp.tool()(twincat_activate)
    mcp.tool()(twincat_start)
    mcp.tool()(twincat_task_list)
    mcp.tool()(twincat_task_info)
    mcp.tool()(twincat_io_list)
    mcp.tool()(twincat_io_set_disabled)
