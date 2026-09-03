"""Runtime control via ITcSysManager (target / activate / start / tasks)."""
from __future__ import annotations

import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from typing import Optional

from results import (
    TargetResult,
    ActivateResult,
    StartResult,
    TaskListResult,
    TaskInfoResult,
    IoListResult,
    IoDisableResult,
    RuntimeMessagesResult,
    SMDS_NOT_DISABLED,
    SMDS_DISABLED,
)
from runtime_messages import (
    classify_runtime_text,
    severity_summary,
    tail_text,
    text_since_baseline,
)

# mcp_errors lives one level above automation_interface/
_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SERVER_ROOT not in sys.path:
    sys.path.insert(0, _SERVER_ROOT)
from mcp_errors import confirm_refused  # noqa: E402

log = logging.getLogger("twincat-mcp")


def _tai():
    return sys.modules["twincat_automation_interface"]


def _apply_confirm_refused(result_cls, operation: str, example_args: dict):
    data = confirm_refused(operation, example_args=example_args)
    kwargs = {
        "success": False,
        "message": data["message"],
    }
    fields = getattr(result_cls, "__dataclass_fields__", {})
    if "error_code" in fields:
        kwargs["error_code"] = data["error_code"]
    if "required_args" in fields:
        kwargs["required_args"] = data["required_args"]
    if "example_next_call" in fields:
        kwargs["example_next_call"] = data["example_next_call"]
    if "net_id" in fields and "net_id" in example_args:
        kwargs["net_id"] = example_args.get("net_id") or ""
    if "path" in fields and "path" in example_args:
        kwargs["path"] = example_args.get("path") or ""
    return result_cls(**kwargs)


class RuntimeOpsMixin:
    """TE1000 runtime operations (ITcSysManager / ITcSysManager2 / TIRT)."""

    def get_target_net_id(self) -> TargetResult:
        return self._call_sta(self._impl_get_target_net_id)

    def set_target_net_id(self, net_id: str, confirm: bool = False) -> TargetResult:
        return self._call_sta(self._impl_set_target_net_id, net_id, confirm)

    def activate_configuration(self, confirm: bool = False) -> ActivateResult:
        return self._call_sta(self._impl_activate_configuration, confirm, timeout=60)

    def start_restart_twincat(self, confirm: bool = False) -> StartResult:
        return self._call_sta(self._impl_start_restart_twincat, confirm, timeout=60)

    def list_tasks(self) -> TaskListResult:
        return self._call_sta(self._impl_list_tasks)

    def get_task_info(self, task_path: str = "") -> TaskInfoResult:
        return self._call_sta(self._impl_get_task_info, task_path)

    def list_io_devices(self) -> IoListResult:
        return self._call_sta(self._impl_list_io_devices)

    def set_io_disabled(
        self,
        path: str = "",
        disabled: bool = True,
        all_devices: bool = False,
        confirm: bool = False,
    ) -> IoDisableResult:
        return self._call_sta(
            self._impl_set_io_disabled, path, disabled, all_devices, confirm,
        )

    def get_runtime_messages(
        self,
        max_chars: int = 12000,
        since_last_activate: bool = False,
        since_timestamp: float = 0.0,
    ) -> RuntimeMessagesResult:
        """TwinCAT Output pane + SysMan errors + classified findings."""
        return self._call_sta(
            self._impl_get_runtime_messages,
            max_chars,
            since_last_activate,
            since_timestamp,
        )

    def _ensure_prereqs(self) -> dict:
        if not hasattr(self, "_prereqs") or self._prereqs is None:
            self._prereqs = {
                "io_disabled_all": False,
                "last_activate_ok": None,
                "last_boot_ok": None,
                "target_net_id": "",
            }
        return self._prereqs

    def _snapshot_output_baseline(self) -> dict:
        """Record pane lengths before activate for since_last_activate windowing."""
        twincat_text = ""
        build_text = ""
        try:
            twincat_text = self._read_pane_text(self._get_output_pane("twincat")) or ""
        except Exception:
            pass
        try:
            build_text = self._read_pane_text(self._get_output_pane("build")) or ""
        except Exception:
            pass
        baseline = {
            "twincat_len": len(twincat_text),
            "build_len": len(build_text),
            "activate_unix": time.time(),
        }
        self._msg_baseline = baseline
        return baseline

    def _require_sys_man(self, result_cls):
        if not self._sys_man:
            return result_cls(
                success=False,
                message="No SysManager — call twincat_open first",
            )
        return None

    def _impl_get_target_net_id(self) -> TargetResult:
        err = self._require_sys_man(TargetResult)
        if err:
            return err
        try:
            net_id = str(self._sys_man.GetTargetNetId())
            return TargetResult(success=True, net_id=net_id, message="OK")
        except Exception as exc:
            return TargetResult(
                success=False,
                message=f"GetTargetNetId failed: {exc}",
            )

    def _impl_set_target_net_id(self, net_id: str, confirm: bool) -> TargetResult:
        if not confirm:
            return _apply_confirm_refused(
                TargetResult,
                "twincat_set_target",
                {"net_id": net_id or "", "confirm": True},
            )
        err = self._require_sys_man(TargetResult)
        if err:
            return err
        net_id = (net_id or "").strip()
        if not net_id:
            return TargetResult(success=False, message="net_id is empty")
        try:
            self._sys_man.SetTargetNetId(net_id)
            actual = str(self._sys_man.GetTargetNetId())
            prereqs = self._ensure_prereqs()
            prereqs["target_net_id"] = actual
            return TargetResult(
                success=True,
                net_id=actual,
                message=f"Target NetId set to {actual}",
            )
        except Exception as exc:
            msgs = ""
            try:
                msgs = str(self._sys_man.GetLastErrorMessages() or "")
            except Exception:
                pass
            return TargetResult(
                success=False,
                message=f"SetTargetNetId failed: {exc}"
                        + (f" | {msgs}" if msgs else ""),
            )

    def _impl_activate_configuration(self, confirm: bool) -> ActivateResult:
        if not confirm:
            return _apply_confirm_refused(
                ActivateResult,
                "twincat_activate",
                {"confirm": True},
            )
        err = self._require_sys_man(ActivateResult)
        if err:
            return err
        try:
            self._snapshot_output_baseline()
            self._sys_man.ActivateConfiguration()
            return ActivateResult(
                success=True,
                message="Configuration activated (ActivateConfiguration). "
                        "Call twincat_start to start/restart TwinCAT.",
            )
        except Exception as exc:
            msgs = ""
            try:
                msgs = str(self._sys_man.GetLastErrorMessages() or "")
            except Exception:
                pass
            return ActivateResult(
                success=False,
                message=f"ActivateConfiguration failed: {exc}"
                        + (f" | {msgs}" if msgs else ""),
            )

    def _impl_start_restart_twincat(self, confirm: bool) -> StartResult:
        if not confirm:
            return _apply_confirm_refused(
                StartResult,
                "twincat_start",
                {"confirm": True},
            )
        err = self._require_sys_man(StartResult)
        if err:
            return err
        try:
            self._sys_man.StartRestartTwinCAT()
            started = None
            try:
                started = bool(self._sys_man.IsTwinCATStarted())
            except Exception:
                pass
            return StartResult(
                success=True,
                message="StartRestartTwinCAT completed"
                        + (f" (IsTwinCATStarted={started})" if started is not None else ""),
            )
        except Exception as exc:
            msgs = ""
            try:
                msgs = str(self._sys_man.GetLastErrorMessages() or "")
            except Exception:
                pass
            return StartResult(
                success=False,
                message=f"StartRestartTwinCAT failed: {exc}"
                        + (f" | {msgs}" if msgs else ""),
            )

    def _impl_list_tasks(self) -> TaskListResult:
        err = self._require_sys_man(TaskListResult)
        if err:
            return err
        try:
            root = self._sys_man.LookupTreeItem("TIRT")
        except Exception as exc:
            return TaskListResult(
                success=False,
                message=f"LookupTreeItem(TIRT) failed: {exc}",
            )
        tasks = []
        try:
            count = int(root.ChildCount)
        except Exception as exc:
            return TaskListResult(
                success=False,
                message=f"TIRT.ChildCount failed: {exc}",
            )
        for i in range(1, count + 1):
            try:
                child = root.Child(i)
                entry = {
                    "name": str(child.Name),
                    "path_name": str(getattr(child, "PathName", "") or ""),
                    "item_sub_type": int(getattr(child, "ItemSubType", 0) or 0),
                }
                tasks.append(entry)
            except Exception as exc:
                log.debug("TIRT child %d failed: %s", i, exc)
        return TaskListResult(
            success=True,
            tasks=tasks,
            message=f"{len(tasks)} task(s)",
        )

    def _impl_get_task_info(self, task_path: str) -> TaskInfoResult:
        err = self._require_sys_man(TaskInfoResult)
        if err:
            return err
        path = (task_path or "").strip()
        if not path:
            return TaskInfoResult(
                success=False,
                message="task_path is empty (e.g. TIRT^Task 1)",
            )
        if not path.upper().startswith("TIRT"):
            path = f"TIRT^{path}" if "^" not in path else path
        try:
            item = self._sys_man.LookupTreeItem(path)
        except Exception as exc:
            return TaskInfoResult(
                success=False,
                message=f"LookupTreeItem('{path}') failed: {exc}",
            )
        xml = ""
        try:
            xml = str(item.ProduceXml())
        except Exception as exc:
            return TaskInfoResult(
                success=False,
                message=f"ProduceXml failed: {exc}",
            )
        task = {
            "name": str(getattr(item, "Name", "") or ""),
            "path_name": str(getattr(item, "PathName", "") or path),
            "item_sub_type": int(getattr(item, "ItemSubType", 0) or 0),
        }
        task.update(_parse_task_xml(xml))
        return TaskInfoResult(
            success=True,
            task=task,
            xml=xml,
            message="OK",
        )

    def _impl_list_io_devices(self) -> IoListResult:
        err = self._require_sys_man(IoListResult)
        if err:
            return err
        try:
            root = self._sys_man.LookupTreeItem("TIID")
        except Exception as exc:
            return IoListResult(
                success=False,
                message=f"LookupTreeItem(TIID) failed: {exc}",
            )
        devices = []
        try:
            count = int(root.ChildCount)
        except Exception as exc:
            return IoListResult(
                success=False,
                message=f"TIID.ChildCount failed: {exc}",
            )
        for i in range(1, count + 1):
            child = _tree_child(root, i)
            if child is None:
                continue
            name = _com_attr_str(child, "Name")
            path_name = _com_attr_str(child, "PathName")
            if not path_name and name:
                path_name = f"TIID^{name}"
            disabled_raw = _read_disabled_raw(child)
            sub_type = 0
            try:
                sub_type = int(getattr(child, "ItemSubType", 0) or 0)
            except Exception:
                sub_type = 0
            devices.append({
                "name": name,
                "path": path_name,
                "disabled": _raw_to_disabled_bool(disabled_raw),
                "disabled_raw": disabled_raw,
                "item_sub_type": sub_type,
            })
        return IoListResult(
            success=True,
            devices=devices,
            message=f"{len(devices)} I/O device(s)",
        )

    def _impl_set_io_disabled(
        self,
        path: str,
        disabled: bool,
        all_devices: bool,
        confirm: bool,
    ) -> IoDisableResult:
        if not confirm:
            return _apply_confirm_refused(
                IoDisableResult,
                "twincat_io_set_disabled",
                {
                    "path": (path or "").strip(),
                    "disabled": disabled,
                    "all_devices": all_devices,
                    "confirm": True,
                },
            )
        err = self._require_sys_man(IoDisableResult)
        if err:
            return err

        target_raw = SMDS_DISABLED if disabled else SMDS_NOT_DISABLED
        path = (path or "").strip()

        if all_devices:
            listed = self._impl_list_io_devices()
            if not listed.success:
                return IoDisableResult(success=False, message=listed.message)
            paths = [d["path"] for d in listed.devices if d.get("path")]
            if not paths:
                return IoDisableResult(
                    success=False,
                    message="No I/O devices under TIID",
                )
        elif path:
            paths = [_normalize_tiid_path(path)]
        else:
            return IoDisableResult(
                success=False,
                message="Provide path (e.g. 'TIID^Device 1 …') or all_devices=true",
            )

        changed: list[dict] = []
        errors: list[str] = []
        for p in paths:
            try:
                item = self._sys_man.LookupTreeItem(p)
            except Exception as exc:
                errors.append(f"{p}: LookupTreeItem failed: {exc}")
                continue
            try:
                item.Disabled = target_raw
            except Exception as exc:
                # Some shells accept bool
                try:
                    item.Disabled = bool(disabled)
                except Exception:
                    errors.append(f"{p}: set Disabled failed: {exc}")
                    continue
            after_raw = _read_disabled_raw(item)
            changed.append({
                "path": p,
                "disabled": _raw_to_disabled_bool(after_raw),
                "disabled_raw": after_raw,
            })

        if not changed:
            return IoDisableResult(
                success=False,
                path=path or (paths[0] if paths else ""),
                message="Failed to set Disabled: " + "; ".join(errors),
            )

        ok_all = not errors
        first = changed[0]
        prereqs = self._ensure_prereqs()
        if ok_all and all_devices and disabled:
            prereqs["io_disabled_all"] = True
        elif all_devices and not disabled:
            prereqs["io_disabled_all"] = False
        return IoDisableResult(
            success=ok_all,
            path=first["path"] if len(changed) == 1 else "",
            disabled=first.get("disabled"),
            disabled_raw=first.get("disabled_raw"),
            changed=changed,
            message=(
                f"Set Disabled={'true' if disabled else 'false'} on "
                f"{len(changed)} device(s)"
                + (f" | errors: {'; '.join(errors)}" if errors else "")
            ),
        )

    def _impl_get_runtime_messages(
        self,
        max_chars: int,
        since_last_activate: bool = False,
        since_timestamp: float = 0.0,
    ) -> RuntimeMessagesResult:
        if not self._dte and not self._sys_man:
            return RuntimeMessagesResult(
                success=False,
                message="No XAE session — call twincat_open first",
                note=(
                    "XAE TwinCAT Output + GetLastErrorMessages. "
                    "ADS Logger port 100 has no portable history API in pyads."
                ),
                history_incomplete=True,
            )
        limit = max(1000, min(int(max_chars or 12000), 100000))
        twincat_text = ""
        build_text = ""
        try:
            twincat_text = self._read_pane_text(self._get_output_pane("twincat")) or ""
        except Exception as exc:
            log.debug("TwinCAT pane read failed: %s", exc)
        try:
            build_text = self._read_pane_text(self._get_output_pane("build")) or ""
        except Exception as exc:
            log.debug("Build pane read failed: %s", exc)
        sys_errs = ""
        try:
            sys_errs = self._read_sys_manager_errors() or ""
        except Exception as exc:
            log.debug("GetLastErrorMessages failed: %s", exc)

        baseline = getattr(self, "_msg_baseline", None) or {}
        use_window = bool(since_last_activate and baseline)
        history_incomplete = True
        if use_window:
            twincat_window = text_since_baseline(
                twincat_text, int(baseline.get("twincat_len") or 0),
            )
            build_window = text_since_baseline(
                build_text, int(baseline.get("build_len") or 0),
            )
            # Pane cleared/rotated: window equals full text → mark incomplete
            if (
                int(baseline.get("twincat_len") or 0) >= len(twincat_text)
                and twincat_text
            ):
                history_incomplete = True
            else:
                history_incomplete = False
            twincat_tail = tail_text(twincat_window, limit)
            build_tail = tail_text(build_window, limit // 2)
        else:
            twincat_tail = tail_text(twincat_text, limit)
            build_tail = tail_text(build_text, limit // 2)
            history_incomplete = True

        # since_timestamp is advisory (pane lines are not always ISO-sortable)
        _ = since_timestamp

        findings = classify_runtime_text(twincat_tail, sys_errs, build_tail)
        counts = severity_summary(findings)
        blocking = any(f.get("severity") == "error" for f in findings)
        ids = sorted({f["id"] for f in findings})
        msg = (
            f"{len(findings)} finding(s): {', '.join(ids)}"
            if findings
            else "No page-fault/license/SAFEOP/fatal patterns in recent output"
        )
        if use_window:
            msg = f"[since_last_activate] {msg}"
        return RuntimeMessagesResult(
            success=True,
            twincat_output=twincat_tail,
            build_output_tail=build_tail,
            sys_manager_errors=sys_errs,
            findings=findings,
            has_blocking_error=blocking,
            has_blocking_runtime_error=blocking,
            error_count=counts["error_count"],
            warning_count=counts["warning_count"],
            sources={
                "runtime": bool(twincat_tail.strip()),
                "build": bool(build_tail.strip()),
                "ads_logger": False,
            },
            history_incomplete=history_incomplete,
            since_last_activate=use_window,
            message=msg,
            note=(
                "Sources: XAE Output pane 'TwinCAT' (runtime) + 'Build', "
                "ITcSysManager.GetLastErrorMessages. "
                "ADS Logger (port 100) history is not available (incomplete). "
                "Prefer since_last_activate=true after twincat_activate."
            ),
        )

    def _read_target_net_id_safe(self) -> str:
        if not self._sys_man:
            return ""
        try:
            return str(self._sys_man.GetTargetNetId() or "")
        except Exception as exc:
            log.debug("GetTargetNetId failed: %s", exc)
            return ""


def _normalize_tiid_path(path: str) -> str:
    p = (path or "").strip()
    if not p:
        return p
    if p.upper().startswith("TIID"):
        return p
    return f"TIID^{p}"


def _tree_child(root, index: int):
    """COM Child access varies (Child(i) vs Child[i])."""
    try:
        return root.Child(index)
    except Exception:
        pass
    try:
        return root.Child[index]
    except Exception as exc:
        log.debug("tree child %s failed: %s", index, exc)
        return None


def _com_attr_str(item, name: str) -> str:
    """Read a COM string attribute; swallow CALL_REJECTED / missing props."""
    try:
        val = getattr(item, name, "")
    except Exception as exc:
        log.debug("COM attr %s failed: %s", name, exc)
        return ""
    if val is None:
        return ""
    return str(val)


def _read_disabled_raw(item) -> Optional[int]:
    try:
        val = item.Disabled
    except Exception:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        if isinstance(val, bool):
            return SMDS_DISABLED if val else SMDS_NOT_DISABLED
        return None


def _raw_to_disabled_bool(raw: Optional[int]) -> Optional[bool]:
    if raw is None:
        return None
    return int(raw) != SMDS_NOT_DISABLED


def _parse_task_xml(xml: str) -> dict:
    """Extract common task parameters from ProduceXml output."""
    out = {"cycle_time": "", "priority": ""}
    if not xml:
        return out
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        # fallback regex
        m = re.search(r"<CycleTime[^>]*>([^<]+)</CycleTime>", xml, re.I)
        if m:
            out["cycle_time"] = m.group(1).strip()
        m = re.search(r"<Priority[^>]*>([^<]+)</Priority>", xml, re.I)
        if m:
            out["priority"] = m.group(1).strip()
        return out

    def _find_text(names: tuple[str, ...]) -> str:
        for el in root.iter():
            tag = el.tag.split("}")[-1] if isinstance(el.tag, str) else ""
            if tag in names and el.text:
                return el.text.strip()
        return ""

    out["cycle_time"] = _find_text(("CycleTime", "CycleTicks", "fCycleTime"))
    out["priority"] = _find_text(("Priority", "nPriority"))
    return out
