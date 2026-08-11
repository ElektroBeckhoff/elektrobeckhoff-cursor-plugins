"""
TwinCAT ADS client wrapper (pyads / TcAdsDll).

Used for runtime mode control (System Service port 10000), PLC start/stop,
and symbolic variable read/write. Independent of the TE1000 COM bridge.

Symbol path rules (verified on TwinCAT 4026 / Tc3_EB_BA sample + UmRT):

* Prefer the full instance path, e.g.
  ``P_Sample_Room.fbDaliLight1._bValidLightControl`` or
  ``…._fbLight.bError``. Nested members work even when absent from
  ``get_all_symbols()`` (list often shows only top-level instances).
* Private ``VAR`` members (``_`` prefix, no hide pragma): R/W by full path.
* ``{attribute 'hide'}`` on an **entire FB type** (typical library base):
  members are still R/W via a concrete instance path of a derived FB
  (inheritance does not block ADS).
* ``{attribute 'hide'}`` on a **single** variable / PROPERTY / VAR_STAT:
  no ADS symbol → path R/W fails (1808).
* PLC must be RUN (not INVALID); call WriteControl RUN on port 851 if needed.
* Whole FB/ENUM/STRING reads may need an explicit ``PLCTYPE_*`` — pyads
  type inference can raise ``NoneType`` on complex types; prefer member paths.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

log = logging.getLogger("twincat-mcp")

HAS_PYADS = False
try:
    import pyads
    HAS_PYADS = True
except ImportError:
    pyads = None  # type: ignore


# ADS System Service / common PLC ports
PORT_SYSTEM_SERVICE = 10000
PORT_PLC_RUNTIME_1 = 851

_MODE_MAP = {
    "run": "ADSSTATE_RUN",
    "config": "ADSSTATE_CONFIG",
    "stop": "ADSSTATE_STOP",
}

_PLC_TYPE_MAP = {
    "BOOL": "BOOL",
    "BYTE": "BYTE",
    "WORD": "WORD",
    "DWORD": "DWORD",
    "SINT": "SINT",
    "USINT": "USINT",
    "INT": "INT",
    "UINT": "UINT",
    "DINT": "DINT",
    "UDINT": "UDINT",
    "LINT": "LINT",
    "ULINT": "ULINT",
    "REAL": "REAL",
    "LREAL": "LREAL",
    "STRING": "STRING",
}


def ads_available() -> bool:
    return HAS_PYADS


def parse_symbol_list(raw: Any) -> list[str]:
    """Parse a symbol list from JSON array, list, or newline/comma text."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [p.strip() for p in re.split(r"[\n,;]+", text) if p.strip()]


def parse_symbol_value_map(raw: Any) -> dict[str, Any]:
    """Parse ``{path: value, ...}`` from dict or JSON object string."""
    if isinstance(raw, dict):
        return {str(k).strip(): v for k, v in raw.items() if str(k).strip()}
    text = str(raw or "").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("values must be a JSON object {\"path\": value, ...}")
    return {str(k).strip(): v for k, v in data.items() if str(k).strip()}


def _jsonable_ads_value(value: Any) -> Any:
    """Make ADS values JSON-serializable for MCP responses."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray)):
        return list(value)
    if isinstance(value, dict):
        return {str(k): _jsonable_ads_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable_ads_value(v) for v in value]
    # enums / ctypes — fall back to str
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def require_pyads():
    if not HAS_PYADS:
        raise RuntimeError(
            "pyads is not installed. Run: pip install pyads  "
            "Requires TwinCAT ADS runtime (TcAdsDll) on Windows."
        )


def local_net_id() -> str:
    """Return local AMS NetId, or 127.0.0.1.1.1 as fallback."""
    require_pyads()
    try:
        return str(pyads.Connection.get_local_address().netid)  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        # Older / alternate API
        return str(pyads.get_local_address())  # type: ignore[attr-defined]
    except Exception:
        return "127.0.0.1.1.1"


def _ads_state_const(name: str):
    """Resolve ADSSTATE_* from pyads (module-level or ADSState enum)."""
    if hasattr(pyads, name):
        return getattr(pyads, name)
    ads_state = getattr(pyads, "ADSState", None)
    if ads_state is not None and hasattr(ads_state, name):
        return getattr(ads_state, name)
    raise AttributeError(f"pyads has no {name}")


def _ads_state_name(value: Any) -> str:
    try:
        if hasattr(value, "name"):
            return str(value.name)
        for name in (
            "ADSSTATE_INVALID", "ADSSTATE_IDLE", "ADSSTATE_RESET",
            "ADSSTATE_INIT", "ADSSTATE_START", "ADSSTATE_RUN",
            "ADSSTATE_STOP", "ADSSTATE_SAVECFG", "ADSSTATE_LOADCFG",
            "ADSSTATE_POWERFAILURE", "ADSSTATE_POWERGOOD",
            "ADSSTATE_ERROR", "ADSSTATE_SHUTDOWN", "ADSSTATE_SUSPEND",
            "ADSSTATE_RESUME", "ADSSTATE_CONFIG", "ADSSTATE_RECONFIG",
        ):
            try:
                if int(_ads_state_const(name)) == int(value):
                    return name
            except (AttributeError, TypeError, ValueError):
                continue
        return str(value)
    except Exception:
        return str(value)


def _resolve_ads_state(mode: str):
    key = (mode or "").strip().lower()
    attr = _MODE_MAP.get(key)
    if not attr:
        raise ValueError(
            f"Unknown mode '{mode}'. Use: run, config, stop"
        )
    return _ads_state_const(attr)


def coerce_write_value(
    value: Any, plc_type: Optional[str] = None,
) -> tuple[Any, Optional[str]]:
    """Convert a user value (often str from MCP) to a Python/PLC value.

    Returns (converted_value, pyads_type_string_or_None).
    """
    type_key = (plc_type or "").strip().upper() or None
    pyads_type = _PLC_TYPE_MAP.get(type_key) if type_key else None

    if isinstance(value, bool):
        return value, pyads_type or "BOOL"
    if isinstance(value, (int, float)) and type_key != "STRING":
        if type_key == "BOOL":
            return bool(value), "BOOL"
        if type_key in ("REAL", "LREAL"):
            return float(value), pyads_type
        if type_key:
            return int(value), pyads_type
        return value, pyads_type

    s = str(value).strip()
    if type_key == "BOOL" or (not type_key and s.lower() in ("true", "false", "1", "0")):
        if s.lower() in ("true", "1"):
            return True, "BOOL"
        if s.lower() in ("false", "0"):
            return False, "BOOL"

    if type_key in ("REAL", "LREAL"):
        return float(s), pyads_type
    if type_key in (
        "BYTE", "WORD", "DWORD", "SINT", "USINT", "INT", "UINT",
        "DINT", "UDINT", "LINT", "ULINT",
    ):
        return int(s, 0), pyads_type
    if type_key == "STRING":
        return s, "STRING"

    # Infer
    if not type_key:
        try:
            if "." in s or "e" in s.lower():
                return float(s), "LREAL"
            return int(s, 0), "DINT"
        except ValueError:
            return s, "STRING"
    return s, pyads_type


class AdsClient:
    """Thin context-manager around pyads.Connection."""

    def __init__(self, net_id: str, port: int = PORT_PLC_RUNTIME_1):
        require_pyads()
        self.net_id = net_id
        self.port = int(port)
        self._conn: Any = None

    def __enter__(self) -> "AdsClient":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def open(self) -> None:
        if self._conn is not None:
            return
        self._conn = pyads.Connection(self.net_id, self.port)
        self._conn.open()
        log.info("ADS connected %s:%s", self.net_id, self.port)

    def close(self) -> None:
        if self._conn is None:
            return
        try:
            self._conn.close()
        except Exception as exc:
            log.debug("ADS close failed: %s", exc)
        finally:
            self._conn = None

    def read_state(self) -> dict:
        ads_state, device_state = self._conn.read_state()
        return {
            "success": True,
            "ads_state": _ads_state_name(ads_state),
            "ads_state_raw": int(ads_state),
            "device_state": int(device_state),
            "message": "OK",
        }

    def set_ads_state(self, mode: str) -> dict:
        target = int(_resolve_ads_state(mode))
        try:
            current = self._conn.read_state()
            device_state = int(current[1])
        except Exception:
            device_state = 0
        # pyads requires data + plc_datatype even when unused by the device
        plc_int = getattr(pyads, "PLCTYPE_INT", None) or getattr(pyads, "PLCTYPE_UINT", int)
        self._conn.write_control(target, device_state, 0, plc_int)
        after = self.read_state()
        after["requested_mode"] = (mode or "").strip().lower()
        after["message"] = f"WriteControl -> {after.get('ads_state')}"
        return after

    def read_by_name(self, symbol: str) -> dict:
        """Read by full ADS path (see module docstring for hide/private rules)."""
        value = self._conn.read_by_name(symbol)
        return {
            "success": True,
            "symbol": symbol,
            "value": value,
            "value_type": type(value).__name__,
            "message": "OK",
        }

    def write_by_name(
        self,
        symbol: str,
        value: Any,
        plc_type: Optional[str] = None,
    ) -> dict:
        """Write by full ADS path (see module docstring for hide/private rules)."""
        converted, typ = coerce_write_value(value, plc_type)
        if typ:
            # pyads constants: PLCTYPE_BOOL etc.
            plc_const = getattr(pyads, f"PLCTYPE_{typ}", None)
            if plc_const is not None:
                self._conn.write_by_name(symbol, converted, plc_const)
            else:
                self._conn.write_by_name(symbol, converted)
        else:
            self._conn.write_by_name(symbol, converted)
        return {
            "success": True,
            "symbol": symbol,
            "value": converted,
            "plc_type": typ or "",
            "message": "OK",
        }

    def read_list_by_name(
        self,
        symbols: list[str],
        ads_sub_commands: int = 500,
    ) -> dict:
        """Read many symbols in one call (pyads Sum-Command / chunked).

        Returns ``values`` dict path→value. Failed symbols (if the ADS call
        fails entirely) surface as error; per-symbol failures depend on pyads.
        """
        names = [str(s).strip() for s in (symbols or []) if str(s).strip()]
        if not names:
            return {
                "success": False,
                "values": {},
                "count": 0,
                "message": "symbols list is empty",
            }
        chunk = max(1, min(int(ads_sub_commands or 500), 500))
        try:
            raw = self._conn.read_list_by_name(
                names, ads_sub_commands=chunk,
            )
        except Exception as exc:
            return {
                "success": False,
                "values": {},
                "count": 0,
                "requested": names,
                "message": f"read_list_by_name failed: {exc}",
            }
        values: dict[str, Any] = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                values[str(k)] = _jsonable_ads_value(v)
        return {
            "success": True,
            "values": values,
            "count": len(values),
            "requested_count": len(names),
            "ads_sub_commands": chunk,
            "message": f"Read {len(values)}/{len(names)} symbol(s)",
        }

    def write_list_by_name(
        self,
        values: dict[str, Any],
        ads_sub_commands: int = 500,
    ) -> dict:
        """Write many symbols in one call (pyads Sum-Command / chunked)."""
        payload: dict[str, Any] = {}
        for key, val in (values or {}).items():
            name = str(key).strip()
            if not name:
                continue
            converted, _typ = coerce_write_value(val, None)
            payload[name] = converted
        if not payload:
            return {
                "success": False,
                "written": [],
                "count": 0,
                "message": "values dict is empty",
            }
        chunk = max(1, min(int(ads_sub_commands or 500), 500))
        try:
            result = self._conn.write_list_by_name(
                payload, ads_sub_commands=chunk,
            )
        except Exception as exc:
            return {
                "success": False,
                "written": [],
                "count": 0,
                "message": f"write_list_by_name failed: {exc}",
            }
        written = list(payload.keys())
        return {
            "success": True,
            "written": written,
            "count": len(written),
            "ads_sub_commands": chunk,
            "pyads_result": result if isinstance(result, dict) else {},
            "message": f"Wrote {len(written)} symbol(s)",
        }

    def list_symbols(
        self,
        prefix: str = "",
        name_contains: str = "",
        type_contains: str = "",
        regex: str = "",
        max_symbols: int = 500,
        include_type: bool = True,
    ) -> dict:
        """List top-level ADS symbols (filtered).

        ``get_all_symbols()`` often omits nested / private paths — those can
        still be R/W via ``read_by_name`` / ``write_by_name`` with the full
        instance path (see module docstring).
        """
        try:
            raw = self._conn.get_all_symbols()
        except Exception as exc:
            return {
                "success": False,
                "symbols": [],
                "total_unfiltered": 0,
                "returned": 0,
                "truncated": False,
                "message": f"get_all_symbols failed: {exc}",
            }

        prefix_l = (prefix or "").strip()
        contains_l = (name_contains or "").strip().lower()
        type_l = (type_contains or "").strip().lower()
        rx = None
        if regex and str(regex).strip():
            try:
                rx = re.compile(str(regex).strip(), re.I)
            except re.error as exc:
                return {
                    "success": False,
                    "symbols": [],
                    "total_unfiltered": 0,
                    "returned": 0,
                    "truncated": False,
                    "message": f"Invalid regex: {exc}",
                }

        limit = max(1, min(int(max_symbols or 500), 5000))
        out: list[dict] = []
        total = 0
        truncated = False
        for entry in raw or []:
            name = str(getattr(entry, "name", "") or "")
            if not name:
                continue
            total += 1
            sym_type = str(
                getattr(entry, "symbol_type", None)
                or getattr(entry, "type", None)
                or ""
            )
            if prefix_l and not name.startswith(prefix_l):
                continue
            if contains_l and contains_l not in name.lower():
                continue
            if type_l and type_l not in sym_type.lower():
                continue
            if rx and not rx.search(name):
                continue
            if len(out) >= limit:
                truncated = True
                continue  # keep counting total
            item: dict[str, Any] = {"name": name}
            if include_type:
                item["type"] = sym_type
                comment = str(getattr(entry, "comment", "") or "")
                if comment:
                    item["comment"] = comment
            out.append(item)

        return {
            "success": True,
            "symbols": out,
            "total_unfiltered": total,
            "returned": len(out),
            "truncated": truncated,
            "filters": {
                "prefix": prefix_l,
                "name_contains": name_contains or "",
                "type_contains": type_contains or "",
                "regex": regex or "",
                "max_symbols": limit,
            },
            "message": (
                f"{len(out)} symbol(s)"
                + (f" (truncated, total matched scan={total})" if truncated else f" of {total}")
            ),
        }
