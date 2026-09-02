"""
ADS client variables and symbols MCP tools for TwinCAT runtime inspection.
"""

from __future__ import annotations

from typing import Any

from .common import _json
from .umrt import _resolve_ads_net_id, _attach_target_safety


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


def twincat_ads_read(
    symbol: str,
    net_id: str = "",
    port: int = 851,
) -> str:
    """Read a PLC variable by full ADS symbol path.

    Examples: \"MAIN.bEnable\", \"P_Sample.fbController._bGateOpen\",
    \"P_Sample.fbDevice1._bValid\" (member of hide base FB).
    Nested/private paths work even if absent from twincat_ads_symbols.
    Single-variable {attribute 'hide'} / hide PROPERTY -> not found.
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


def twincat_ads_read_list(
    symbols: str,
    net_id: str = "",
    port: int = 851,
    ads_sub_commands: int = 500,
) -> str:
    """Read many PLC variables in one ADS Sum-Command batch.

    symbols: JSON array '[\"MAIN.bEnable\", \"P_Sample.…\"]' or
    newline/comma-separated paths. Uses pyads read_list_by_name (chunked by
    ads_sub_commands, default/max 500). Returns values map path->value.
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


def register_tools(mcp: Any) -> None:
    """Register ADS variable and symbol tools on FastMCP server."""
    mcp.tool()(twincat_ads_symbols)
    mcp.tool()(twincat_ads_read)
    mcp.tool()(twincat_ads_read_list)
    mcp.tool()(twincat_ads_write)
    mcp.tool()(twincat_ads_write_list)
