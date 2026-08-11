"""
User-facing action prompts for the TwinCAT MCP agent.

Trial licenses and some XAE dialogs cannot be completed via Automation
Interface (security code / CAPTCHA). Tools attach these prompts so the
agent must ask the human to finish the step before continuing.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

# Keywords that indicate a missing / violated TwinCAT runtime license
_LICENSE_ERROR_MARKERS = (
    "license not found",
    "license violation",
    "checking twincat licenses",
    "tc3 plc",
    "licenseid",
)


ACTION_TRIAL_LICENSE = {
    "id": "umrt_trial_license",
    "ask_user": True,
    "severity": "blocking",
    "title": "Activate 7-day trial licenses on the Usermode Runtime target",
    "why": (
        "UmRT needs the same runtime licenses as a real target (e.g. TC3 PLC). "
        "The Automation Interface cannot enter the trial security code — "
        "this step is manual in XAE."
    ),
    "instructions": [
        "In TcXaeShell/XAE set the Target to the MCP Usermode Runtime AmsNetId.",
        "Open SYSTEM → License.",
        "Tab Manage Licenses / Order Information (Runtime): select missing "
        "licenses (at least TC3 PLC / TC1200 and any TF* used by the project).",
        "Click \"7 Days Trial License…\" and type the displayed security code.",
        "Confirm, then call twincat_activate + twincat_start again "
        "(or Restart TwinCAT).",
    ],
    "agent_must": (
        "Stop and ask the user to perform the trial-license steps above. "
        "Do not retry activate/start in a loop until the user confirms licenses "
        "are active."
    ),
}

ACTION_IO_DISABLE = {
    "id": "umrt_io_disabled",
    "ask_user": False,
    "severity": "prerequisite",
    "title": "Disable physical I/O before activating on Usermode Runtime",
    "why": (
        "Usermode Runtime has no EtherCAT; active I/O often fails SAFEOP "
        "with AdsError 1823. Prefer twincat_io_set_disabled(all_devices=true)."
    ),
    "instructions": [
        "Call twincat_io_list, then twincat_io_set_disabled("
        "all_devices=true, disabled=true, confirm=true) before twincat_activate.",
    ],
    "agent_must": (
        "Ensure I/O devices under TIID are Disabled before UmRT activate."
    ),
}

ACTION_UMRT_WINDOW = {
    "id": "umrt_console_window",
    "ask_user": False,
    "severity": "info",
    "title": "Usermode Runtime console window",
    "why": (
        "TcSystemServiceUm normally opens a minimized console (Start.bat uses "
        "start /min). window_mode=hidden launches without a visible window — "
        "useful for MCP — but interactive keys (r/c/x) are then unavailable; "
        "use twincat_start (COM) for Run."
    ),
}

ACTION_NON_UMRT_TARGET = {
    "id": "non_umrt_target_control",
    "ask_user": True,
    "severity": "warning",
    "title": "Runtime control targets a non-Usermode-Runtime system",
    "why": (
        "Activate / StartRestart / ADS WriteControl (RUN/CONFIG/STOP) / PLC "
        "start-stop are executing against an AMS NetId that is NOT the MCP "
        "Usermode Runtime instance. That usually means a real IPC, local "
        "realtime target, or another TwinCAT system — not the safe UmRT sandbox."
    ),
    "instructions": [
        "Confirm with the user that controlling this target is intended.",
        "For UmRT systemtests: twincat_umrt_start → twincat_set_target("
        "mcp UmRT NetId) before activate/start/plc_start.",
        "Call twincat_umrt_status / twincat_get_target and compare NetIds.",
    ],
    "agent_must": (
        "Treat this as live target control. Tell the user the target NetId is "
        "not the MCP Usermode Runtime and get explicit confirmation before "
        "further activate/start/stop/mode changes on that system."
    ),
}


_CATALOG = {
    ACTION_TRIAL_LICENSE["id"]: ACTION_TRIAL_LICENSE,
    ACTION_IO_DISABLE["id"]: ACTION_IO_DISABLE,
    ACTION_UMRT_WINDOW["id"]: ACTION_UMRT_WINDOW,
    ACTION_NON_UMRT_TARGET["id"]: ACTION_NON_UMRT_TARGET,
}


def looks_like_license_error(text: str) -> bool:
    t = (text or "").lower()
    return any(m in t for m in _LICENSE_ERROR_MARKERS)


def get_actions(*ids: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for aid in ids:
        if not aid or aid in seen:
            continue
        action = _CATALOG.get(aid)
        if action:
            out.append(dict(action))
            seen.add(aid)
    return out


def attach_user_actions(
    payload: dict[str, Any],
    *action_ids: str,
    force_trial_on_license_error: bool = True,
) -> dict[str, Any]:
    """Merge user_action_required into a tool result dict (copy)."""
    data = dict(payload or {})
    ids = list(action_ids)
    blob = " ".join(
        str(data.get(k, ""))
        for k in ("message", "error", "sys_manager_errors")
    )
    if force_trial_on_license_error and looks_like_license_error(blob):
        if ACTION_TRIAL_LICENSE["id"] not in ids:
            ids.insert(0, ACTION_TRIAL_LICENSE["id"])
        data["license_error_detected"] = True

    actions = get_actions(*ids)
    if not actions:
        return data

    existing = list(data.get("user_action_required") or [])
    have = {a.get("id") for a in existing if isinstance(a, dict)}
    for a in actions:
        if a["id"] not in have:
            existing.append(a)
    data["user_action_required"] = existing

    # Surface a short agent hint in message when blocking actions present
    blocking = [a for a in existing if a.get("severity") == "blocking"]
    if blocking and data.get("success") is not False:
        hint = blocking[0].get("agent_must") or blocking[0].get("title")
        msg = (data.get("message") or "").rstrip()
        suffix = f" | USER ACTION REQUIRED: {hint}"
        if suffix.strip() not in msg:
            data["message"] = (msg + suffix).strip(" |")
    elif blocking and data.get("success") is False:
        hint = blocking[0].get("agent_must") or blocking[0].get("title")
        msg = (data.get("message") or data.get("error") or "").rstrip()
        suffix = f" | USER ACTION REQUIRED: {hint}"
        if "USER ACTION REQUIRED" not in msg:
            data["message"] = (msg + suffix).strip(" |")
    return data


def umrt_activate_actions(
    *,
    license_error: bool = False,
    include_io: bool = True,
) -> list[str]:
    """Action IDs for activate/start enrichment.

    Trial license is attached only when a license error was detected —
    never solely because the target is UmRT.
    """
    ids: list[str] = []
    if license_error:
        ids.append(ACTION_TRIAL_LICENSE["id"])
    if include_io:
        ids.append(ACTION_IO_DISABLE["id"])
    return ids


def attach_non_umrt_target_warning(
    payload: dict[str, Any],
    *,
    operation: str,
    target_net_id: str,
    mcp_umrt_net_id: str = "",
    mcp_umrt_running: bool = False,
    target_is_mcp_umrt: bool = False,
) -> dict[str, Any]:
    """Annotate runtime-control results when the target is not MCP UmRT.

    Does not block the operation (confirm=true already gated it) — surfaces
    ``warnings``, ``target_is_mcp_umrt``, and ``user_action_required`` so the
    agent understands it is steering a real/external TwinCAT system.
    """
    data = dict(payload) if isinstance(payload, dict) else {}

    data["target_net_id"] = target_net_id or ""
    data["mcp_umrt_net_id"] = mcp_umrt_net_id or ""
    data["mcp_umrt_running"] = bool(mcp_umrt_running)
    data["target_is_mcp_umrt"] = bool(target_is_mcp_umrt)
    data["runtime_control_operation"] = operation or ""

    if target_is_mcp_umrt:
        return data

    tgt = target_net_id or "(unknown)"
    umrt = mcp_umrt_net_id or "(MCP UmRT not running / unknown)"
    warning = (
        f"SAFETY: {operation or 'runtime control'} targets AMS NetId {tgt}, "
        f"which is NOT the MCP Usermode Runtime ({umrt}). "
        "This affects a real/external TwinCAT system (IPC, local RT, …)."
    )
    warnings = list(data.get("warnings") or [])
    if warning not in warnings:
        warnings.append(warning)
    data["warnings"] = warnings

    data = attach_user_actions(
        data,
        ACTION_NON_UMRT_TARGET["id"],
        force_trial_on_license_error=False,
    )

    # attach_user_actions only suffixes message for severity=blocking;
    # force a visible WARNING marker for agents.
    msg = (data.get("message") or "").rstrip()
    marker = " | WARNING: non-UmRT target control"
    if marker.strip() not in msg:
        data["message"] = (msg + marker + f" (net_id={tgt})").strip(" |")
    return data
