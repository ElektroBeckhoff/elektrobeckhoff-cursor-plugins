"""Compose ADS / PLC readiness summaries for MCP agents."""
from __future__ import annotations

from typing import Any, Optional


def compose_readiness(
    *,
    system_ads_state: str = "",
    plc_ads_state: str = "",
    plc_port: int = 851,
    plc_start_ok: Optional[bool] = None,
    has_blocking_runtime_error: Optional[bool] = None,
    net_id: str = "",
) -> dict[str, Any]:
    """Return readiness fields; ready_for_ads only when system+PLC are RUN."""
    sys_s = (system_ads_state or "").strip().upper()
    plc_s = (plc_ads_state or "").strip().upper()
    reasons: list[str] = []

    if not sys_s:
        reasons.append("system_ads_state_unknown")
    elif sys_s != "RUN":
        reasons.append(f"system_ads_state={sys_s}")

    if not plc_s:
        reasons.append("plc_ads_state_unknown")
    elif plc_s != "RUN":
        reasons.append(f"plc_ads_state={plc_s}")

    if has_blocking_runtime_error:
        reasons.append("has_blocking_runtime_error")

    if plc_start_ok is False:
        reasons.append("plc_start_failed")

    ready = (
        sys_s == "RUN"
        and plc_s == "RUN"
        and not has_blocking_runtime_error
        and plc_start_ok is not False
    )

    return {
        "system_ads_state": system_ads_state or "",
        "plc_ads_state": plc_ads_state or "",
        "plc_port": int(plc_port or 851),
        "plc_start_ok": plc_start_ok,
        "ready_for_ads": ready,
        "blocking_reasons": reasons,
        "net_id": net_id or "",
    }
