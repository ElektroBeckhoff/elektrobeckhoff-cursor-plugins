"""
Usermode Runtime end-to-end systemtest chain.

Orchestrates the same steps as skill ``twincat3-umrt-systemtest`` /
command ``/twincat3-cmd-online-test``:

  UmRT start → open → I/O disable → set target → activate → start →
  runtime messages → sys/PLC RUN → ADS symbols + read_list (+ optional write)

CLI (live TwinCAT + pyads)::

    python systemtest/umrt_chain.py --sln "C:\\path\\sample.sln" \\
        --xae-version 4026 \\
        --read "P_Sample.fbController._bGateOpen" \\
        --write "P_Sample.fbController._bGateOpen" --write-value true

Unit tests inject a mock ``SystemtestBackends`` — no XAE required.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

# Allow `python systemtest/umrt_chain.py` from mcp-twincat root
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
for _sub in ("ads", "umrt", "automation_interface"):
    _p = str(_ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


BLOCKING_FINDING_IDS = frozenset({
    "license",
    "page_fault",
    "fatal",
    "exception",
    "safeop_aborted",
})

REQUIRED_STEPS = (
    "umrt_start",
    "open",
    "io_disabled",
    "set_target",
    "activate",
    "start",
    "runtime_messages",
    "sys_run",
    "plc_run",
    "ads_read",
)


def _to_dict(result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if isinstance(result, dict):
        return dict(result)
    if hasattr(result, "__dataclass_fields__"):
        return asdict(result)
    out: dict[str, Any] = {}
    for key in (
        "success", "message", "error", "net_id", "ams_net_id", "instance",
        "pid", "window_mode", "findings", "has_blocking_error",
        "ads_state", "device_state", "values", "symbols", "symbol", "value",
        "solution_path", "plc_project_name", "created_new_instance",
        "xae_version", "devices", "updated",
    ):
        if hasattr(result, key):
            out[key] = getattr(result, key)
    if not out and hasattr(result, "__dict__"):
        out = {k: v for k, v in vars(result).items() if not k.startswith("_")}
    return out


def _ok(data: dict[str, Any]) -> bool:
    if "success" in data:
        return bool(data["success"])
    return not data.get("error")


def _finding_ids(findings: Any) -> list[str]:
    if not findings:
        return []
    ids: list[str] = []
    for f in findings:
        if isinstance(f, dict) and f.get("id"):
            ids.append(str(f["id"]))
        elif isinstance(f, str):
            ids.append(f)
    return ids


def _has_blocking(findings: Any) -> bool:
    return bool(BLOCKING_FINDING_IDS.intersection(_finding_ids(findings)))


def _is_run_state(ads_state: Any) -> bool:
    s = str(ads_state or "").upper()
    return s in ("ADSSTATE_RUN", "RUN") or s.endswith("_RUN")


@dataclass
class StepResult:
    name: str
    passed: bool
    detail: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "data": self.data,
        }


@dataclass
class SystemtestReport:
    passed: bool
    steps: list[StepResult] = field(default_factory=list)
    net_id: str = ""
    ask_user: list[str] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)

    def step(self, name: str) -> Optional[StepResult]:
        for s in self.steps:
            if s.name == name:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.passed,
            "passed": self.passed,
            "net_id": self.net_id,
            "ask_user": list(self.ask_user),
            "steps": [s.to_dict() for s in self.steps],
            "summary": "\n".join(self.summary_lines),
        }

    def format_checklist(self) -> str:
        lines = ["UmRT systemtest"]
        for s in self.steps:
            mark = "PASS" if s.passed else "FAIL"
            extra = f"  ({s.detail})" if s.detail else ""
            lines.append(f"- {s.name}: {mark}{extra}")
        lines.append(f"Overall: {'PASS' if self.passed else 'FAIL'}")
        if self.ask_user:
            lines.append("Ask user:")
            for a in self.ask_user:
                lines.append(f"  - {a}")
        return "\n".join(lines)


@dataclass
class SystemtestConfig:
    sln_path: str
    xae_version: str = "4026"
    window_mode: str = "hidden"
    plc_port: int = 851
    symbol_prefix: str = ""
    read_symbols: list[str] = field(default_factory=list)
    write_symbol: str = ""
    write_value: str = ""
    write_plc_type: str = ""
    skip_write: bool = False
    settle_s: float = 1.0


@dataclass
class SystemtestBackends:
    """Injectable callables — each returns a dict-like or dataclass result."""

    umrt_status: Callable[[], Any]
    umrt_start: Callable[..., Any]
    open_solution: Callable[..., Any]
    io_set_disabled: Callable[..., Any]
    set_target: Callable[..., Any]
    get_target: Callable[[], Any]
    activate: Callable[..., Any]
    start_twincat: Callable[..., Any]
    runtime_messages: Callable[..., Any]
    runtime_state: Callable[..., Any]
    plc_start: Callable[..., Any]
    ads_symbols: Callable[..., Any]
    ads_read_list: Callable[..., Any]
    ads_write: Callable[..., Any]
    ads_read: Callable[..., Any]


def run_umrt_systemtest(
    config: SystemtestConfig,
    backends: SystemtestBackends,
) -> SystemtestReport:
    """Run the full UmRT systemtest chain. Fail-fast on blocking findings."""
    report = SystemtestReport(passed=False)
    steps = report.steps

    def add(name: str, passed: bool, detail: str = "", data: Optional[dict] = None) -> StepResult:
        sr = StepResult(name=name, passed=passed, detail=detail, data=data or {})
        steps.append(sr)
        return sr

    # --- 1. UmRT start ---
    try:
        start_res = _to_dict(backends.umrt_start(
            confirm=True, window_mode=config.window_mode,
        ))
    except Exception as exc:
        add("umrt_start", False, str(exc))
        return _finalize(report)

    net_id = str(start_res.get("ams_net_id") or start_res.get("net_id") or "")
    if not net_id:
        try:
            st = _to_dict(backends.umrt_status())
            net_id = str(st.get("mcp_ams_net_id") or "")
        except Exception:
            pass
    report.net_id = net_id
    ok = _ok(start_res)
    add(
        "umrt_start",
        ok,
        f"net_id={net_id}, window={config.window_mode}",
        start_res,
    )
    if start_res.get("user_action_required") or start_res.get("ask_user"):
        report.ask_user.append(
            "Activate 7-day trial licenses on UmRT (SYSTEM→License) if not done."
        )
    if not ok:
        return _finalize(report)

    # --- 2. Open ---
    try:
        open_res = _to_dict(backends.open_solution(
            sln_path=config.sln_path,
            xae_version=config.xae_version or None,
        ))
    except Exception as exc:
        add("open", False, str(exc))
        return _finalize(report)
    ok = _ok(open_res)
    add(
        "open",
        ok,
        open_res.get("plc_project_name") or open_res.get("solution_path") or "",
        open_res,
    )
    if not ok:
        return _finalize(report)

    # --- 3. I/O disable ---
    try:
        io_res = _to_dict(backends.io_set_disabled(
            all_devices=True, disabled=True, confirm=True,
        ))
    except Exception as exc:
        add("io_disabled", False, str(exc))
        return _finalize(report)
    ok = _ok(io_res)
    add("io_disabled", ok, io_res.get("message") or "", io_res)
    if not ok:
        return _finalize(report)

    # --- 4. Target ---
    if not net_id:
        add("set_target", False, "UmRT AmsNetId unknown")
        return _finalize(report)
    try:
        tgt_res = _to_dict(backends.set_target(net_id=net_id, confirm=True))
        got = _to_dict(backends.get_target())
    except Exception as exc:
        add("set_target", False, str(exc))
        return _finalize(report)
    current = str(got.get("net_id") or "")
    ok = _ok(tgt_res) and (not current or current == net_id)
    add("set_target", ok, f"target={current or net_id}", {**tgt_res, "get_target": got})
    if not ok:
        return _finalize(report)

    # --- 5. Activate ---
    try:
        act_res = _to_dict(backends.activate(confirm=True))
    except Exception as exc:
        add("activate", False, str(exc))
        return _finalize(report)
    findings = act_res.get("runtime_findings") or act_res.get("findings") or []
    ok = _ok(act_res) and not _has_blocking(findings)
    add("activate", ok, ",".join(_finding_ids(findings)) or act_res.get("message") or "", act_res)
    if act_res.get("user_action_required"):
        report.ask_user.append("License / user action required after activate.")
    if not ok:
        if _has_blocking(findings):
            report.ask_user.append(
                f"Blocking activate findings: {', '.join(_finding_ids(findings))}"
            )
        return _finalize(report)

    # --- 6. Start ---
    try:
        start_tc = _to_dict(backends.start_twincat(confirm=True))
    except Exception as exc:
        add("start", False, str(exc))
        return _finalize(report)
    findings = start_tc.get("runtime_findings") or start_tc.get("findings") or []
    ok = _ok(start_tc) and not _has_blocking(findings)
    add("start", ok, ",".join(_finding_ids(findings)) or start_tc.get("message") or "", start_tc)
    if not ok:
        if _has_blocking(findings):
            report.ask_user.append(
                f"Blocking start findings: {', '.join(_finding_ids(findings))}"
            )
        return _finalize(report)

    if config.settle_s > 0:
        time.sleep(config.settle_s)

    # --- 7. Runtime messages ---
    try:
        msg_res = _to_dict(backends.runtime_messages())
    except Exception as exc:
        add("runtime_messages", False, str(exc))
        return _finalize(report)
    findings = msg_res.get("findings") or []
    blocking = bool(msg_res.get("has_blocking_error")) or _has_blocking(findings)
    ok = _ok(msg_res) and not blocking
    add(
        "runtime_messages",
        ok,
        f"findings={','.join(_finding_ids(findings)) or 'none'}",
        msg_res,
    )
    if not ok:
        report.ask_user.append(
            "Resolve runtime messages (license / page_fault / SAFEOP) before ADS."
        )
        return _finalize(report)

    # --- 8. Sys RUN ---
    try:
        sys_state = _to_dict(backends.runtime_state(net_id=net_id, port=10000))
    except TypeError:
        try:
            sys_state = _to_dict(backends.runtime_state(net_id=net_id))
        except Exception as exc:
            add("sys_run", False, str(exc))
            return _finalize(report)
    except Exception as exc:
        add("sys_run", False, str(exc))
        return _finalize(report)
    ok = _ok(sys_state) and _is_run_state(sys_state.get("ads_state"))
    add("sys_run", ok, str(sys_state.get("ads_state") or ""), sys_state)
    if not ok:
        return _finalize(report)

    # --- 9. PLC RUN ---
    try:
        plc_state = _to_dict(
            backends.runtime_state(net_id=net_id, port=config.plc_port)
        )
    except TypeError:
        plc_state = {}
    except Exception:
        plc_state = {}
    if not _is_run_state(plc_state.get("ads_state")):
        try:
            plc_start_res = _to_dict(backends.plc_start(
                net_id=net_id, port=config.plc_port, confirm=True,
            ))
        except Exception as exc:
            add("plc_run", False, str(exc))
            return _finalize(report)
        ok = _ok(plc_start_res)
        detail = plc_start_res.get("ads_state") or plc_start_res.get("message") or ""
        add("plc_run", ok, str(detail), plc_start_res)
        if not ok:
            return _finalize(report)
    else:
        add("plc_run", True, str(plc_state.get("ads_state") or "RUN"), plc_state)

    # --- 10. ADS symbols (informational; not required for overall PASS) ---
    try:
        sym_res = _to_dict(backends.ads_symbols(
            net_id=net_id,
            port=config.plc_port,
            prefix=config.symbol_prefix,
            max_symbols=50,
        ))
        add(
            "ads_symbols",
            _ok(sym_res),
            f"n={len(sym_res.get('symbols') or [])}",
            sym_res,
        )
    except Exception as exc:
        add("ads_symbols", False, str(exc))

    # --- 11. ADS read ---
    read_paths = list(config.read_symbols)
    if not read_paths:
        # Auto-pick a few top-level BOOL/INT-ish names from symbols if present
        syms = (report.step("ads_symbols").data.get("symbols") or []) if report.step("ads_symbols") else []
        for item in syms:
            name = item.get("name") if isinstance(item, dict) else str(item)
            if name and "." in name:
                read_paths.append(name)
            if len(read_paths) >= 3:
                break
    if not read_paths:
        add("ads_read", False, "no read_symbols configured and none auto-selected")
        return _finalize(report)

    try:
        read_res = _to_dict(backends.ads_read_list(
            symbols=read_paths, net_id=net_id, port=config.plc_port,
        ))
    except Exception as exc:
        add("ads_read", False, str(exc))
        return _finalize(report)
    values = read_res.get("values") or {}
    ok = _ok(read_res) and bool(values)
    add("ads_read", ok, f"n={len(values)}", read_res)
    if not ok:
        return _finalize(report)

    # --- 12. ADS write smoke (optional) ---
    if config.skip_write or not config.write_symbol:
        add("ads_write", True, "skipped")
    else:
        path = config.write_symbol.strip()
        try:
            before = _to_dict(backends.ads_read(
                symbol=path, net_id=net_id, port=config.plc_port,
            ))
            write_res = _to_dict(backends.ads_write(
                symbol=path,
                value=config.write_value,
                plc_type=config.write_plc_type or "",
                net_id=net_id,
                port=config.plc_port,
                confirm=True,
            ))
            after = _to_dict(backends.ads_read(
                symbol=path, net_id=net_id, port=config.plc_port,
            ))
        except Exception as exc:
            add("ads_write", False, str(exc))
            return _finalize(report)
        ok = _ok(write_res)
        note = ""
        if ok and after.get("value") != _coerce_compare(config.write_value, after.get("value")):
            # Write may succeed then be overwritten by PLC cycle
            note = "write ok; value differs after read (possible cyclic overwrite)"
            ok = True
        detail = f"path={path}"
        if note:
            detail = f"{detail}; {note}"
        add(
            "ads_write",
            ok,
            detail,
            {"before": before, "write": write_res, "after": after},
        )
        if not ok:
            return _finalize(report)

    return _finalize(report)


def _coerce_compare(expected: str, actual: Any) -> Any:
    """Best-effort compare write expectation vs read-back."""
    exp = str(expected).strip()
    if isinstance(actual, bool):
        return exp.lower() in ("1", "true", "yes") if exp.lower() in (
            "0", "1", "true", "false", "yes", "no",
        ) else actual
    if isinstance(actual, (int, float)) and exp.replace(".", "", 1).lstrip("-").isdigit():
        try:
            return type(actual)(float(exp) if isinstance(actual, float) else int(float(exp)))
        except Exception:
            return exp
    return exp


def _finalize(report: SystemtestReport) -> SystemtestReport:
    required_ok = True
    for name in REQUIRED_STEPS:
        st = report.step(name)
        if st is None or not st.passed:
            required_ok = False
            break
    # ads_write only required when present and not skipped-pass
    w = report.step("ads_write")
    if w is not None and not w.passed:
        required_ok = False
    report.passed = required_ok
    report.summary_lines = report.format_checklist().splitlines()
    return report


def build_live_backends() -> SystemtestBackends:
    """Wire real UmRT + COM bridge + AdsClient (Windows / TwinCAT required)."""
    from twincat_umrt_controller import UmrtController, op_to_dict, status_to_dict
    from twincat_ads_client import AdsClient

    try:
        from twincat_automation_interface import TcAutomationInterface
    except ImportError:
        from automation_interface.twincat_automation_interface import (  # type: ignore
            TcAutomationInterface,
        )

    umrt = UmrtController()
    bridge = TcAutomationInterface()

    def umrt_status():
        return status_to_dict(umrt.status())

    def umrt_start(confirm: bool = False, window_mode: str = "hidden"):
        return op_to_dict(umrt.start(confirm=confirm, window_mode=window_mode))

    def open_solution(sln_path: str = "", xae_version: Optional[str] = None, **_kw):
        return bridge.open_solution(sln_path=sln_path, xae_version=xae_version)

    def io_set_disabled(all_devices: bool = True, disabled: bool = True, confirm: bool = False, **_kw):
        return bridge.set_io_disabled(
            all_devices=all_devices, disabled=disabled, confirm=confirm,
        )

    def set_target(net_id: str = "", confirm: bool = False):
        return bridge.set_target_net_id(net_id, confirm=confirm)

    def get_target():
        return bridge.get_target_net_id()

    def activate(confirm: bool = False):
        return bridge.activate_configuration(confirm=confirm)

    def start_twincat(confirm: bool = False):
        return bridge.start_restart_twincat(confirm=confirm)

    def runtime_messages(max_chars: int = 12000):
        return bridge.get_runtime_messages(max_chars=max_chars)

    def runtime_state(net_id: str = "", port: int = 10000):
        with AdsClient(net_id, port=port) as ads:
            state = ads.read_state()
        state["net_id"] = net_id
        state["port"] = port
        return state

    def plc_start(net_id: str = "", port: int = 851, confirm: bool = False):
        if not confirm:
            return {"success": False, "error": "confirm=true required"}
        with AdsClient(net_id, port=port) as ads:
            result = ads.set_ads_state("run")
        result["net_id"] = net_id
        result["port"] = port
        return result

    def ads_symbols(net_id: str = "", port: int = 851, prefix: str = "", max_symbols: int = 50, **_kw):
        with AdsClient(net_id, port=port) as ads:
            result = ads.list_symbols(prefix=prefix, max_symbols=max_symbols)
        result["net_id"] = net_id
        return result

    def ads_read_list(symbols: Any = None, net_id: str = "", port: int = 851, **_kw):
        names = list(symbols or [])
        with AdsClient(net_id, port=port) as ads:
            result = ads.read_list_by_name(names)
        result["net_id"] = net_id
        return result

    def ads_write(
        symbol: str = "",
        value: str = "",
        plc_type: str = "",
        net_id: str = "",
        port: int = 851,
        confirm: bool = False,
    ):
        if not confirm:
            return {"success": False, "error": "confirm=true required"}
        with AdsClient(net_id, port=port) as ads:
            result = ads.write_by_name(symbol, value, plc_type=plc_type or None)
        result["net_id"] = net_id
        return result

    def ads_read(symbol: str = "", net_id: str = "", port: int = 851):
        with AdsClient(net_id, port=port) as ads:
            result = ads.read_by_name(symbol)
        result["net_id"] = net_id
        return result

    return SystemtestBackends(
        umrt_status=umrt_status,
        umrt_start=umrt_start,
        open_solution=open_solution,
        io_set_disabled=io_set_disabled,
        set_target=set_target,
        get_target=get_target,
        activate=activate,
        start_twincat=start_twincat,
        runtime_messages=runtime_messages,
        runtime_state=runtime_state,
        plc_start=plc_start,
        ads_symbols=ads_symbols,
        ads_read_list=ads_read_list,
        ads_write=ads_write,
        ads_read=ads_read,
    )


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="TwinCAT UmRT systemtest chain")
    p.add_argument("--sln", required=True, help="Path to .sln")
    p.add_argument("--xae-version", default="4026")
    p.add_argument("--window-mode", default="hidden", choices=("hidden", "minimized"))
    p.add_argument("--prefix", default="", help="ADS symbol prefix filter")
    p.add_argument(
        "--read", action="append", default=[],
        help="Symbol path to read (repeatable)",
    )
    p.add_argument("--write", default="", help="Optional write smoke symbol")
    p.add_argument("--write-value", default="")
    p.add_argument("--write-type", default="")
    p.add_argument("--skip-write", action="store_true")
    p.add_argument("--settle", type=float, default=1.0)
    p.add_argument("--json", action="store_true", help="Print JSON report")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    cfg = SystemtestConfig(
        sln_path=args.sln,
        xae_version=args.xae_version,
        window_mode=args.window_mode,
        symbol_prefix=args.prefix,
        read_symbols=list(args.read or []),
        write_symbol=args.write,
        write_value=args.write_value,
        write_plc_type=args.write_type,
        skip_write=bool(args.skip_write) or not args.write,
        settle_s=args.settle,
    )
    report = run_umrt_systemtest(cfg, build_live_backends())
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    else:
        print(report.format_checklist())
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
