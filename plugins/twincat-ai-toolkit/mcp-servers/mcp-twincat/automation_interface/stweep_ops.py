"""STweep (GeBa) Format-code via EnvDTE — not a Beckhoff AI API.

Verified on TwinCAT 4024 + 4026 / TcXaeShell:
  - OtherContextMenus.PlcCodeWinContextMenu.Formatcode  (editor / open file)
  - OtherContextMenus.PlcFolder.Formatcode               (SE folder, EN / 4024)
  - OtherContextMenus.SPSOrdner.Formatcode               (SE folder, DE / 4026)

UI right-click Format on a Solution Explorer *folder* uses PlcFolder/SPSOrdner
Formatcode once. Automation cannot do that today: UIHierarchyItem.Select fails
on the VS PlatformUI marshaler
(``Method '…UIHierarchyItemMarshaler.Select' not found``). Folder / project
scope therefore walks formattable files and runs the editor command after
ItemOperations.OpenFile (then closes the document). Use
``twincat_format_cancel`` to abort a running multi-file job between files.
CLI (STweep.CLI) is intentionally never invoked.
"""
from __future__ import annotations

import glob
import logging
import os
import re
import sys
import threading
import time
import xml.etree.ElementTree as ET
from typing import Optional

from dataclasses import asdict

from results import (
    StweepFormatCancelResult,
    StweepFormatProgressResult,
    StweepFormatResult,
    StweepStatusResult,
)

log = logging.getLogger("twincat-mcp")

STWEEP_CMD_EDITOR = "OtherContextMenus.PlcCodeWinContextMenu.Formatcode"
# Same command GUID/ID; shell language / TwinCAT version differs in the name.
STWEEP_CMD_FOLDER = "OtherContextMenus.SPSOrdner.Formatcode"
STWEEP_CMD_FOLDER_EN = "OtherContextMenus.PlcFolder.Formatcode"
STWEEP_CMD_FOLDERS = (STWEEP_CMD_FOLDER_EN, STWEEP_CMD_FOLDER)
STWEEP_CMD_LICENSE = "STweep.License"
STWEEP_COMMAND_GUID = "{3395FA64-3C7F-4FB2-9551-CE197238B175}"

# Settle after Formatcode: STweep dirties the buffer in ~50ms; ActiveDocument
# often becomes unavailable after ~0.3-0.5s. Save on first dirty + short post
# using a held Document ref — do not use a long min_wait floor.
_STWEEP_POST_DIRTY_S = 0.15
_STWEEP_POLL_S = 0.05
_STWEEP_CLEAN_POLLS = 10  # ~0.5s with real sleep; fast under tests mocking sleep
_STWEEP_SETTLE_MAX_S = 2.5

# TwinCAT ST objects STweep can format via the XAE editor command.
# Includes interfaces (.TcIO) — same ST source as POUs/DUTs/GVLs.
_FORMATABLE_EXTS = {".tcpou", ".tcgvl", ".tcdut", ".tcio"}
_PROJECT_EXTS = {".plcproj"}

# Matched case-insensitively against COM / dialog text when Formatcode fails.
_LICENSE_ERROR_MARKERS = (
    "stweepfortwincatdoesnothaveavalidlicense",
    "your copy of stweep",
    "does not have a valid license",
    "doesnothaveavalidlicense",
    "keine gültige lizenz",
    "keine gueltige lizenz",
    "not have a valid license",
)

_DAYS_RE = re.compile(
    r"(\d+)\s+of\s+(\d+)\s+days\s+remain",
    re.IGNORECASE,
)


def _tai():
    return sys.modules["twincat_automation_interface"]


def _is_license_error_text(text: str) -> bool:
    low = (text or "").lower().replace(" ", "")
    if not low:
        return False
    for marker in _LICENSE_ERROR_MARKERS:
        if marker.replace(" ", "") in low:
            return True
    return False


def _read_stweep_license_wizard() -> Optional[dict]:
    """Read QlmLicenseWizard STATIC labels only (never EDIT / activation keys)."""
    tai = _tai()
    if not tai.HAS_WIN32GUI:
        return None

    found: list[dict] = []

    def enum_cb(hwnd, _):
        try:
            if not tai.win32gui.IsWindowVisible(hwnd):
                return True
            title = tai.win32gui.GetWindowText(hwnd) or ""
            cls = tai.win32gui.GetClassName(hwnd) or ""
            key = (title + " " + cls).lower()
            if not (
                "qlmlicensewizard" in key
                or "stweep license" in key
                or (
                    "license" in key
                    and "stweep" in key
                )
            ):
                # Also accept class containing QlmLicenseWizard with empty title
                if "qlmlicensewizard" not in cls.lower() and "qlmlicense" not in cls.lower():
                    # scan child captions for wizard identity
                    child_blob = []

                    def peek(child, __):
                        try:
                            t = tai.win32gui.GetWindowText(child) or ""
                            if t:
                                child_blob.append(t)
                        except Exception:
                            pass
                        return True

                    try:
                        tai.win32gui.EnumChildWindows(hwnd, peek, None)
                    except Exception:
                        return True
                    blob_l = " ".join(child_blob).lower()
                    if "stweep license wizard" not in blob_l and (
                        "stweep for twincat" not in blob_l
                        or "license" not in blob_l
                    ):
                        return True

            statics: list[str] = []

            def child_cb(child, __):
                try:
                    cname = tai.win32gui.GetClassName(child) or ""
                    # Windows Forms STATIC only — skip EDIT (keys!)
                    if "static" not in cname.lower() and "label" not in cname.lower():
                        return True
                    text = (tai.win32gui.GetWindowText(child) or "").strip()
                    if text:
                        statics.append(text)
                except Exception:
                    pass
                return True

            try:
                tai.win32gui.EnumChildWindows(hwnd, child_cb, None)
            except Exception:
                return True

            if not statics:
                return True

            blob = " | ".join(statics)
            blob_l = blob.lower()
            if "stweep" not in blob_l and "license" not in blob_l:
                return True

            activated = "your license is activated" in blob_l or (
                "lizenz ist aktiviert" in blob_l
            )
            not_act = (
                "not activated" in blob_l
                or "nicht aktiviert" in blob_l
                or "no valid license" in blob_l
            )
            days_remain = None
            days_total = None
            detail = ""
            for line in statics:
                m = _DAYS_RE.search(line)
                if m:
                    days_remain = int(m.group(1))
                    days_total = int(m.group(2))
                    detail = line.strip()
                    break
            if activated and not detail:
                detail = "Your license is activated."
            if not_act and not activated:
                detail = detail or "License is not activated."

            license_ok = True if activated and not not_act else (
                False if not_act else None
            )
            state = (
                "activated" if license_ok is True
                else "not_activated" if license_ok is False
                else "unknown"
            )
            found.append({
                "hwnd": int(hwnd),
                "license_ok": license_ok,
                "license_state": state,
                "license_detail": detail,
                "license_days_remain": days_remain,
                "license_days_total": days_total,
            })
        except Exception:
            pass
        return True

    try:
        tai.win32gui.EnumWindows(enum_cb, None)
    except Exception as exc:
        log.debug("EnumWindows license wizard failed: %s", exc)
        return None

    # Prefer a conclusive activated/not_activated result
    for item in found:
        if item.get("license_ok") is not None:
            return item
    return found[0] if found else None


def _close_stweep_license_wizard(hwnd) -> None:
    """Close license wizard via Finish button or WM_CLOSE (no secrets logged)."""
    tai = _tai()
    if not tai.HAS_WIN32GUI or not hwnd:
        return
    BM_CLICK = 0x00F5
    try:
        finish_hwnd = None

        def child_cb(child, _):
            nonlocal finish_hwnd
            try:
                cname = tai.win32gui.GetClassName(child) or ""
                text = (tai.win32gui.GetWindowText(child) or "").strip()
                if "button" in cname.lower() and text.lower() in (
                    "finish", "fertig stellen", "schließen", "close",
                ):
                    finish_hwnd = child
                    return False
            except Exception:
                pass
            return True

        try:
            tai.win32gui.EnumChildWindows(int(hwnd), child_cb, None)
        except Exception:
            pass
        if finish_hwnd:
            tai.win32gui.PostMessage(finish_hwnd, BM_CLICK, 0, 0)
            time.sleep(0.2)
        tai.win32gui.PostMessage(int(hwnd), tai.win32con.WM_CLOSE, 0, 0)
    except Exception as exc:
        log.debug("Close STweep license wizard failed: %s", exc)


def _stweep_extension_globs() -> list[str]:
    roots = []
    pf86 = os.environ.get("ProgramFiles(x86)") or r"C:\Program Files (x86)"
    pf = os.environ.get("ProgramFiles") or r"C:\Program Files"
    for root in (pf86, pf):
        roots.append(
            os.path.join(
                root,
                "Beckhoff",
                "TcXaeShell",
                "Common7",
                "IDE",
                "Extensions",
                "GeBa Engineering",
                "STweep for TwinCAT*",
            )
        )
    return roots


def discover_stweep_installs() -> list[dict]:
    """Return installed STweep XAE extension folders (filesystem probe)."""
    found: list[dict] = []
    seen: set[str] = set()
    for pattern in _stweep_extension_globs():
        for path in glob.glob(pattern):
            if not os.path.isdir(path):
                continue
            key = os.path.normcase(os.path.abspath(path))
            if key in seen:
                continue
            seen.add(key)
            version = _read_vsix_version(path)
            found.append({"path": path, "version": version})
    return found


def _read_vsix_version(ext_dir: str) -> str:
    manifest = os.path.join(ext_dir, "extension.vsixmanifest")
    if not os.path.isfile(manifest):
        return ""
    try:
        root = ET.parse(manifest).getroot()
        # Default VS namespace
        for el in root.iter():
            if el.tag.endswith("Identity"):
                return (el.attrib.get("Version") or "").strip()
    except Exception as exc:
        log.debug("STweep vsixmanifest parse failed: %s", exc)
    return ""


class StweepOpsMixin:
    def get_stweep_status(self, probe_license: bool = False) -> StweepStatusResult:
        """Status without UI by default.

        ``probe_license=True`` opens the visible STweep License wizard (optional).
        Normal path: install + commands only; license is verified fail-fast on
        the first ``format_code`` attempt.
        """
        timeout = 90 if probe_license else 60
        result = self._call_sta(
            self._impl_get_stweep_status, probe_license, timeout=timeout,
        )
        # Progress is lock-based (no STA) so it stays visible while format runs.
        result.format_progress = asdict(self.get_format_progress())
        return result

    def cancel_format(self) -> StweepFormatCancelResult:
        """Request cancel of the running multi-file format job.

        Stops between files (does not kill a mid-file Formatcode call).
        Safe to call while STA is busy — only flips a flag.
        """
        self._ensure_format_progress_state()
        with self._stweep_format_lock:
            running = bool(self._stweep_format_progress.get("running"))
            if not running:
                return StweepFormatCancelResult(
                    success=True,
                    canceled=False,
                    was_running=False,
                    message="No format job running",
                )
            self._format_cancel_requested = True
            self._stweep_format_progress["message"] = (
                "Cancel requested — stopping after current file…"
            )
            self._stweep_format_progress["updated_unix"] = time.time()
        return StweepFormatCancelResult(
            success=True,
            canceled=True,
            was_running=True,
            message=(
                "Cancel requested. Job stops after the current file finishes "
                "(poll twincat_format_progress until running=false)."
            ),
        )

    def get_format_progress(self) -> StweepFormatProgressResult:
        """Read live format job progress (safe while format holds the STA)."""
        self._ensure_format_progress_state()
        with self._stweep_format_lock:
            p = dict(self._stweep_format_progress)
        started = float(p.get("started_unix") or 0.0)
        updated = float(p.get("updated_unix") or 0.0)
        now = time.time()
        elapsed = 0.0
        if started:
            end = now if p.get("running") else (updated or now)
            elapsed = max(0.0, round(end - started, 1))
        return StweepFormatProgressResult(
            success=True,
            running=bool(p.get("running")),
            phase=str(p.get("phase") or "idle"),
            target=str(p.get("target") or ""),
            files_total=int(p.get("files_total") or 0),
            files_done=int(p.get("files_done") or 0),
            files_formatted=int(p.get("files_formatted") or 0),
            files_failed=int(p.get("files_failed") or 0),
            current_file=str(p.get("current_file") or ""),
            percent=float(p.get("percent") or 0.0),
            started_unix=started,
            updated_unix=updated,
            elapsed_s=elapsed,
            message=str(p.get("message") or ""),
            result=p.get("result"),
        )

    def format_code(
        self,
        path: str = "",
        recursive: bool = True,
        timeout_s: int = 300,
        confirm: bool = False,
        wait: bool = True,
    ) -> StweepFormatResult:
        """Format via STweep Formatcode.

        ``wait=True`` (default): block until finished (progress still updated).
        ``wait=False``: start on a background thread and return immediately;
        poll ``get_format_progress`` / ``twincat_format_progress`` until
        ``running`` is false. Prefer wait=false for large folders/projects.
        """
        self._ensure_format_progress_state()
        with self._stweep_format_lock:
            if self._stweep_format_progress.get("running"):
                return StweepFormatResult(
                    success=False,
                    method="busy",
                    target=path or "",
                    message=(
                        "A format job is already running. "
                        "Poll twincat_format_progress until running=false."
                    ),
                )
            # Claim the job slot before leaving the lock (sync or async).
            now = time.time()
            self._format_cancel_requested = False
            self._stweep_format_progress.update({
                "running": True,
                "phase": "starting",
                "target": path or "",
                "files_total": 0,
                "files_done": 0,
                "files_formatted": 0,
                "files_failed": 0,
                "current_file": "",
                "percent": 0.0,
                "started_unix": now,
                "updated_unix": now,
                "message": "Starting format job…",
                "result": None,
            })

        if not wait:
            return self._start_format_code_async(
                path, recursive, timeout_s, confirm,
            )

        try:
            return self._call_sta(
                self._impl_format_code,
                path,
                recursive,
                timeout_s,
                confirm,
                timeout=timeout_s + 90,
            )
        except Exception as exc:
            self._finish_format_progress(StweepFormatResult(
                success=False,
                method="error",
                target=path or "",
                message=str(exc),
            ))
            raise

    def _ensure_format_progress_state(self) -> None:
        if not hasattr(self, "_stweep_format_lock"):
            self._stweep_format_lock = threading.Lock()
        if not hasattr(self, "_format_cancel_requested"):
            self._format_cancel_requested = False
        if not hasattr(self, "_stweep_format_progress"):
            self._stweep_format_progress = {
                "running": False,
                "phase": "idle",
                "target": "",
                "files_total": 0,
                "files_done": 0,
                "files_formatted": 0,
                "files_failed": 0,
                "current_file": "",
                "percent": 0.0,
                "started_unix": 0.0,
                "updated_unix": 0.0,
                "message": "",
                "result": None,
            }

    def _cancel_requested(self) -> bool:
        return bool(getattr(self, "_format_cancel_requested", False))

    def _update_format_progress(self, **kwargs) -> None:
        self._ensure_format_progress_state()
        with self._stweep_format_lock:
            self._stweep_format_progress.update(kwargs)
            self._stweep_format_progress["updated_unix"] = time.time()
            total = int(self._stweep_format_progress.get("files_total") or 0)
            done = int(self._stweep_format_progress.get("files_done") or 0)
            if total > 0:
                self._stweep_format_progress["percent"] = round(
                    100.0 * min(done, total) / total, 1,
                )
            elif self._stweep_format_progress.get("phase") == "done":
                self._stweep_format_progress["percent"] = 100.0

    def _finish_format_progress(self, result: StweepFormatResult) -> None:
        phase = "done" if result.success else "error"
        if result.method == "unlicensed":
            phase = "error"
        if result.canceled or result.method == "canceled":
            phase = "canceled"
        self._format_cancel_requested = False
        self._update_format_progress(
            running=False,
            phase=phase,
            current_file="",
            files_total=result.files_total,
            files_formatted=result.files_formatted,
            files_failed=result.files_failed,
            files_done=result.files_formatted + result.files_failed,
            percent=(
                100.0
                if result.files_total and (
                    result.files_formatted + result.files_failed
                ) >= result.files_total
                else (
                    round(
                        100.0
                        * (result.files_formatted + result.files_failed)
                        / result.files_total,
                        1,
                    )
                    if result.files_total
                    else (100.0 if result.success else 0.0)
                )
            ),
            message=result.message,
            result=asdict(result),
        )

    def _start_format_code_async(
        self,
        path: str,
        recursive: bool,
        timeout_s: int,
        confirm: bool,
    ) -> StweepFormatResult:
        # Job slot already claimed by format_code(); only launch the worker.
        def runner():
            try:
                result = self._call_sta(
                    self._impl_format_code,
                    path,
                    recursive,
                    timeout_s,
                    confirm,
                    timeout=timeout_s + 90,
                )
                # _impl_format_code already finalizes progress; keep as safety net
                prog = self.get_format_progress()
                if prog.running or prog.result is None:
                    self._finish_format_progress(result)
            except Exception as exc:
                log.exception("Async STweep format failed: %s", exc)
                fail = StweepFormatResult(
                    success=False,
                    method="error",
                    target=path or "",
                    message=str(exc),
                )
                self._finish_format_progress(fail)

        threading.Thread(
            target=runner, name="STweep-Format-Async", daemon=True,
        ).start()
        return StweepFormatResult(
            success=True,
            method="async_started",
            target=path or "",
            async_started=True,
            message=(
                "Format started in background. "
                "Poll twincat_format_progress until running=false."
            ),
        )

    def _impl_get_stweep_status(
        self, probe_license: bool = False,
    ) -> StweepStatusResult:
        installs = discover_stweep_installs()
        installed = bool(installs)
        version = next((i["version"] for i in installs if i.get("version")), "")
        paths = [i["path"] for i in installs]

        commands: dict = {}
        dte_attached = bool(self._dte)
        if self._dte:
            for name in (
                STWEEP_CMD_EDITOR,
                *STWEEP_CMD_FOLDERS,
                STWEEP_CMD_LICENSE,
            ):
                try:
                    cmd = self._dte.Commands.Item(name)
                    commands[name] = {
                        "present": True,
                        "available": bool(cmd.IsAvailable),
                        "guid": str(getattr(cmd, "Guid", "") or ""),
                        "id": int(getattr(cmd, "ID", 0) or 0),
                    }
                except Exception as exc:
                    commands[name] = {
                        "present": False,
                        "available": False,
                        "error": str(exc),
                    }

        commands_loaded = any(
            commands.get(name, {}).get("present")
            for name in (STWEEP_CMD_EDITOR, *STWEEP_CMD_FOLDERS)
        )
        license_cmd = bool(commands.get(STWEEP_CMD_LICENSE, {}).get("present"))

        license_ok: Optional[bool] = getattr(self, "_stweep_license_ok", None)
        license_state = "unknown"
        license_detail = ""
        days_remain: Optional[int] = None
        days_total: Optional[int] = None

        if not installed and not commands_loaded:
            return StweepStatusResult(
                success=False,
                installed=False,
                version=version,
                install_paths=paths,
                commands=commands,
                commands_loaded=False,
                dte_attached=dte_attached,
                license_ok=False,
                license_state="not_installed",
                ready=False,
                message=(
                    "STweep for TwinCAT not found under TcXaeShell Extensions "
                    "and no Formatcode DTE commands registered."
                ),
            )

        if not dte_attached:
            license_state = "needs_session"
        elif not commands_loaded and not license_cmd:
            license_state = "commands_missing"
            license_ok = False
        elif probe_license and license_cmd:
            probed = self._probe_license_wizard()
            license_ok = probed.get("license_ok")
            license_state = probed.get("license_state") or "unknown"
            license_detail = probed.get("license_detail") or ""
            days_remain = probed.get("license_days_remain")
            days_total = probed.get("license_days_total")
            self._stweep_license_ok = license_ok
            self._stweep_license_detail = license_detail
        elif license_ok is True:
            license_state = "activated"
            license_detail = getattr(self, "_stweep_license_detail", "") or ""
        elif license_ok is False:
            license_state = "not_activated"

        # ready = can attempt format without opening the license wizard.
        # License is confirmed fail-fast on first format_code (or optional probe).
        ready = bool(
            (installed or commands_loaded)
            and commands_loaded
            and license_ok is not False
        )

        msg_parts = []
        if installed:
            msg_parts.append(
                f"STweep installed ({version or 'version unknown'})"
            )
        else:
            msg_parts.append("STweep install folder not found on disk")
        if commands_loaded:
            msg_parts.append("Formatcode DTE commands loaded")
        elif dte_attached:
            msg_parts.append(
                "extension on disk but Formatcode commands not in this DTE "
                "(restart XAE after install?)"
            )
        elif installed:
            msg_parts.append(
                "open a TwinCAT solution (twincat_open) to probe DTE commands"
            )
        if license_state == "activated":
            msg_parts.append(
                license_detail or "license activated"
            )
        elif license_state == "not_activated":
            msg_parts.append("license NOT activated")
        elif license_state == "needs_session":
            msg_parts.append("license unknown until format (no XAE session)")
        elif license_state == "unknown":
            msg_parts.append(
                "license unknown until first format "
                "(optional probe_license=true opens STweep License wizard)"
            )

        return StweepStatusResult(
            success=installed or commands_loaded,
            installed=installed or commands_loaded,
            version=version,
            install_paths=paths,
            commands=commands,
            commands_loaded=commands_loaded,
            dte_attached=dte_attached,
            license_ok=license_ok,
            license_state=license_state,
            license_detail=license_detail,
            license_days_remain=days_remain,
            license_days_total=days_total,
            ready=ready,
            message="; ".join(msg_parts),
        )

    def _probe_license_wizard(self) -> dict:
        """Open STweep menu License wizard, read STATIC status, close it.

        Never returns Activation Key / EDIT field contents.
        ``STweep.License`` is modal — a watcher closes the wizard.
        """
        tai = _tai()
        if not tai.HAS_WIN32GUI:
            return {
                "license_ok": None,
                "license_state": "unknown",
                "license_detail": "win32gui unavailable for license wizard",
            }

        captured: dict = {}
        stop = threading.Event()

        def watcher():
            deadline = time.time() + 45
            while not stop.is_set() and time.time() < deadline:
                try:
                    info = _read_stweep_license_wizard()
                    if info:
                        captured.update(info)
                        _close_stweep_license_wizard(info.get("hwnd"))
                        return
                except Exception as exc:
                    log.debug("STweep license watcher: %s", exc)
                stop.wait(0.25)

        thr = threading.Thread(
            target=watcher, name="STweep-License-Watcher", daemon=True,
        )
        thr.start()
        try:
            self._retry_com(
                self._dte.ExecuteCommand, STWEEP_CMD_LICENSE,
                max_retries=2, delay_s=1,
            )
        except Exception as exc:
            if _is_license_error_text(str(exc)):
                return {
                    "license_ok": False,
                    "license_state": "not_activated",
                    "license_detail": "STweep.License failed (unlicensed)",
                }
            log.debug("STweep.License ExecuteCommand: %s", exc)
        finally:
            stop.set()
            thr.join(timeout=5)

        if not captured:
            # Wizard may already have been closed; try one read pass
            try:
                info = _read_stweep_license_wizard()
                if info:
                    captured.update(info)
                    _close_stweep_license_wizard(info.get("hwnd"))
            except Exception:
                pass

        if not captured:
            return {
                "license_ok": None,
                "license_state": "unknown",
                "license_detail": (
                    "STweep.License opened but wizard text was not readable"
                ),
            }

        return {
            "license_ok": captured.get("license_ok"),
            "license_state": captured.get("license_state") or "unknown",
            "license_detail": captured.get("license_detail") or "",
            "license_days_remain": captured.get("license_days_remain"),
            "license_days_total": captured.get("license_days_total"),
        }

    def _impl_format_code(
        self,
        path: str,
        recursive: bool,
        timeout_s: int,
        confirm: bool = False,
    ) -> StweepFormatResult:
        result: Optional[StweepFormatResult] = None
        started = time.time()
        self._update_format_progress(
            running=True,
            phase="starting",
            target=(path or "").strip(),
            files_total=0,
            files_done=0,
            files_formatted=0,
            files_failed=0,
            current_file="",
            percent=0.0,
            started_unix=started,
            message="Preparing format…",
            result=None,
        )
        try:
            result = self._impl_format_code_body(
                path, recursive, timeout_s, confirm,
            )
            return result
        finally:
            if result is not None:
                self._finish_format_progress(result)
            else:
                self._finish_format_progress(StweepFormatResult(
                    success=False,
                    method="error",
                    target=(path or "").strip(),
                    message="Format aborted unexpectedly",
                ))

    def _impl_format_code_body(
        self,
        path: str,
        recursive: bool,
        timeout_s: int,
        confirm: bool = False,
    ) -> StweepFormatResult:
        if not self._dte:
            return StweepFormatResult(
                success=False,
                message="No XAE instance. Call twincat_open first.",
            )

        path = (path or "").strip()
        project_scope = self._is_project_format_scope(path)
        if project_scope and not confirm:
            return StweepFormatResult(
                success=False,
                target=path or (self._plcproj_file_path or ""),
                message=(
                    "Whole-project format requires confirm=true. "
                    "Without confirm only a file or folder path is allowed "
                    "(not empty path, not .plcproj, not the PLC project root)."
                ),
            )

        # No license wizard UI here — install/commands only.
        # License is verified on the first Formatcode call (fail-fast).
        status = self._impl_get_stweep_status(probe_license=False)
        if not status.installed:
            return StweepFormatResult(
                success=False,
                method="unavailable",
                installed=False,
                license_ok=status.license_ok,
                license_state=status.license_state,
                license_detail=status.license_detail,
                message="STweep is not installed. " + status.message,
            )
        if not status.commands_loaded:
            return StweepFormatResult(
                success=False,
                method="unavailable",
                installed=status.installed,
                license_ok=status.license_ok,
                license_state=status.license_state,
                license_detail=status.license_detail,
                message=(
                    "STweep Formatcode DTE commands not registered. "
                    + status.message
                ),
            )
        # Cached negative from a previous fail-fast
        if getattr(self, "_stweep_license_ok", None) is False:
            return StweepFormatResult(
                success=False,
                method="unlicensed",
                installed=status.installed,
                license_ok=False,
                license_state="not_activated",
                license_detail=getattr(self, "_stweep_license_detail", "") or "",
                message=(
                    "STweep license not activated (cached from earlier format). "
                    "Open STweep > License in XAE, then retry."
                ),
            )

        try:
            files = self._resolve_format_targets(path, recursive)
        except FileNotFoundError as exc:
            return StweepFormatResult(
                success=False,
                target=path or "",
                installed=status.installed,
                license_ok=status.license_ok,
                license_state=status.license_state,
                message=str(exc),
            )
        except ValueError as exc:
            return StweepFormatResult(
                success=False,
                target=path or "",
                installed=status.installed,
                license_ok=status.license_ok,
                license_state=status.license_state,
                message=str(exc),
            )

        if not files:
            return StweepFormatResult(
                success=False,
                target=path or "",
                files_total=0,
                installed=status.installed,
                license_ok=status.license_ok,
                license_state=status.license_state,
                message=(
                    "No formattable TwinCAT ST files "
                    "(.TcPOU/.TcGVL/.TcDUT/.TcIO) found for the given target."
                ),
            )

        formatted: list[str] = []
        failed: list[dict] = []
        deadline = time.time() + max(30, timeout_s)
        # Per-file editor path — SE folder Formatcode needs UIHierarchy.Select
        # which is broken on TcXaeShell PlatformUI marshaler (see module doc).
        method = "DTE_Editor_Formatcode_per_file"
        command = STWEEP_CMD_EDITOR
        target = path or (self._plcproj_file_path or "")
        canceled = False

        self._update_format_progress(
            running=True,
            phase="formatting",
            target=target,
            files_total=len(files),
            files_done=0,
            files_formatted=0,
            files_failed=0,
            current_file="",
            message=(
                f"Formatting 0/{len(files)} file(s) "
                f"(per-file OpenFile; cancel via twincat_format_cancel)…"
            ),
        )

        for index, file_path in enumerate(files, start=1):
            if self._cancel_requested():
                canceled = True
                self._update_format_progress(
                    message=(
                        f"Canceled after {len(formatted)}/{len(files)} file(s)"
                    ),
                )
                break
            self._update_format_progress(
                current_file=file_path,
                message=f"Formatting {index}/{len(files)}: {os.path.basename(file_path)}",
            )
            if time.time() > deadline:
                failed.append({
                    "path": file_path,
                    "error": "timeout before formatting remaining files",
                })
                self._update_format_progress(
                    files_failed=len(failed),
                    files_done=len(formatted) + len(failed),
                )
                continue
            try:
                self._format_one_file(file_path, deadline)
                formatted.append(file_path)
                # First successful format proves license without wizard UI
                self._stweep_license_ok = True
                self._stweep_license_detail = (
                    "license ok (verified by successful Formatcode)"
                )
            except Exception as exc:
                err = str(exc)
                if self._cancel_requested() or "format canceled" in err.lower():
                    canceled = True
                    break
                log.warning("STweep format failed for %s: %s", file_path, exc)
                wizard = None
                try:
                    wizard = _read_stweep_license_wizard()
                    if wizard and wizard.get("hwnd"):
                        _close_stweep_license_wizard(wizard.get("hwnd"))
                except Exception:
                    pass
                license_hit = _is_license_error_text(err) or (
                    wizard is not None
                    and wizard.get("license_ok") is False
                ) or (
                    wizard is not None
                    and "activated" not in (
                        (wizard.get("license_state") or "")
                    )
                    and wizard.get("license_ok") is not True
                    and _is_license_error_text(
                        wizard.get("license_detail") or ""
                    )
                )
                # License wizard appearing mid-format with not-activated text
                if wizard and wizard.get("license_ok") is False:
                    license_hit = True
                if license_hit:
                    self._stweep_license_ok = False
                    detail = ""
                    if wizard:
                        detail = wizard.get("license_detail") or ""
                    return StweepFormatResult(
                        success=False,
                        method="unlicensed",
                        command=command,
                        target=target,
                        files_total=len(files),
                        files_formatted=len(formatted),
                        files_failed=1,
                        formatted=formatted,
                        failed=[{"path": file_path, "error": err}],
                        installed=status.installed,
                        license_ok=False,
                        license_state="not_activated",
                        license_detail=detail,
                        message=(
                            "STweep license error on first format — aborted. "
                            + (detail or err)
                        ),
                    )
                failed.append({"path": file_path, "error": err})

            self._update_format_progress(
                files_formatted=len(formatted),
                files_failed=len(failed),
                files_done=len(formatted) + len(failed),
            )

        if canceled:
            msg = (
                f"Canceled: formatted {len(formatted)}/{len(files)} file(s) "
                f"via {command} (per-file OpenFile)"
            )
            if failed:
                msg += f" | {len(failed)} failed before cancel"
            license_ok = getattr(self, "_stweep_license_ok", None)
            license_state = (
                "activated" if license_ok is True
                else "not_activated" if license_ok is False
                else "unknown"
            )
            return StweepFormatResult(
                success=False,
                method="canceled",
                command=command,
                target=target,
                files_total=len(files),
                files_formatted=len(formatted),
                files_failed=len(failed),
                formatted=formatted,
                failed=failed,
                installed=status.installed,
                license_ok=license_ok,
                license_state=license_state,
                license_detail=getattr(self, "_stweep_license_detail", "") or "",
                message=msg,
                canceled=True,
            )

        success = bool(formatted) and not failed
        msg = (
            f"Formatted {len(formatted)}/{len(files)} file(s) via {command} "
            f"(per-file OpenFile; SE folder Formatcode needs UIHierarchy.Select)"
        )
        if failed:
            msg += f" | {len(failed)} failed"

        license_ok = getattr(self, "_stweep_license_ok", None)
        license_state = (
            "activated" if license_ok is True
            else "not_activated" if license_ok is False
            else "unknown"
        )
        return StweepFormatResult(
            success=success,
            method=method,
            command=command,
            target=target,
            files_total=len(files),
            files_formatted=len(formatted),
            files_failed=len(failed),
            formatted=formatted,
            failed=failed,
            installed=status.installed,
            license_ok=license_ok,
            license_state=license_state,
            license_detail=getattr(self, "_stweep_license_detail", "") or "",
            message=msg,
        )

    def _is_project_format_scope(self, path: str) -> bool:
        """True when the request targets the whole PLC project.

        Free scopes: a single ST file, or a normal folder that is not the
        PLC project root. Project scope (needs confirm): empty path,
        ``.plcproj``, or the project root directory.
        """
        path = (path or "").strip()
        if not path:
            return True

        abs_path = os.path.abspath(path)
        if os.path.isfile(abs_path):
            return os.path.splitext(abs_path)[1].lower() in _PROJECT_EXTS

        if not os.path.isdir(abs_path):
            return False

        root = self._default_plc_source_root()
        if root and os.path.normcase(os.path.abspath(root)) == os.path.normcase(
            abs_path
        ):
            return True

        try:
            for name in os.listdir(abs_path):
                if name.lower().endswith(".plcproj"):
                    return True
        except OSError:
            pass
        return False

    def _resolve_format_targets(
        self, path: str, recursive: bool,
    ) -> list[str]:
        path = (path or "").strip()
        if not path:
            root = self._default_plc_source_root()
            if not root:
                raise ValueError(
                    "No path given and no PLC project directory known. "
                    "Pass a file/folder path, or call twincat_open with a "
                    "plcproj and confirm=true for whole-project format."
                )
            return self._collect_formattable_files(root, recursive=True)

        abs_path = os.path.abspath(path)
        if os.path.isfile(abs_path):
            ext = os.path.splitext(abs_path)[1].lower()
            # Project file → format all ST objects under the project folder
            if ext in _PROJECT_EXTS:
                return self._collect_formattable_files(
                    os.path.dirname(abs_path), recursive=True,
                )
            if ext not in _FORMATABLE_EXTS:
                raise ValueError(
                    f"Unsupported file type '{ext}'. "
                    "Expected .TcPOU, .TcGVL, .TcDUT, .TcIO "
                    "(or .plcproj with confirm=true)."
                )
            return [abs_path]
        if os.path.isdir(abs_path):
            return self._collect_formattable_files(abs_path, recursive)
        raise FileNotFoundError(f"Path not found: {abs_path}")

    def _default_plc_source_root(self) -> str:
        if self._plcproj_file_path and os.path.isfile(self._plcproj_file_path):
            return os.path.dirname(self._plcproj_file_path)
        # Fallback: directory of open solution's nested PLC folder heuristic
        if self._sln_path and os.path.isfile(self._sln_path):
            return os.path.dirname(self._sln_path)
        return ""

    @staticmethod
    def _collect_formattable_files(root: str, recursive: bool) -> list[str]:
        out: list[str] = []
        if recursive:
            for dirpath, _dirnames, filenames in os.walk(root):
                for name in filenames:
                    if os.path.splitext(name)[1].lower() in _FORMATABLE_EXTS:
                        out.append(os.path.join(dirpath, name))
        else:
            try:
                for name in os.listdir(root):
                    full = os.path.join(root, name)
                    if (
                        os.path.isfile(full)
                        and os.path.splitext(name)[1].lower() in _FORMATABLE_EXTS
                    ):
                        out.append(full)
            except OSError:
                return []
        out.sort(key=lambda p: p.lower())
        return out

    def _command_available(self, name: str) -> bool:
        try:
            return bool(self._dte.Commands.Item(name).IsAvailable)
        except Exception:
            return False

    def _resolve_folder_format_command(self) -> str:
        """Return the SE Formatcode command name registered in this shell."""
        for name in STWEEP_CMD_FOLDERS:
            try:
                self._dte.Commands.Item(name)
                return name
            except Exception:
                continue
        return ""

    def _format_one_file(self, file_path: str, deadline: float) -> None:
        tai = _tai()
        if self._cancel_requested():
            raise RuntimeError("format canceled")
        self._retry_com(
            self._dte.ItemOperations.OpenFile, file_path,
            max_retries=8, delay_s=1,
        )

        while time.time() < deadline:
            if self._cancel_requested():
                self._close_active_if_path(file_path)
                raise RuntimeError("format canceled")
            tai.pythoncom.PumpWaitingMessages()
            if self._command_available(STWEEP_CMD_EDITOR):
                break
            time.sleep(0.2)
        else:
            # Fallback: SE folder command if the file is the active selection
            folder_cmd = self._resolve_folder_format_command()
            if folder_cmd:
                try:
                    self._retry_com(
                        self._dte.ExecuteCommand,
                        "SolutionExplorer.SyncWithActiveDocument",
                        max_retries=3, delay_s=1,
                    )
                except Exception as exc:
                    log.debug("SyncWithActiveDocument: %s", exc)
                self._retry_com(
                    self._dte.ExecuteCommand, folder_cmd,
                    max_retries=5, delay_s=1,
                )
                doc = self._capture_document(file_path)
                self._wait_and_save_active(file_path, deadline, doc=doc)
                self._close_active_if_path(file_path, doc=doc)
                return
            raise RuntimeError(
                f"STweep editor Formatcode not available for '{file_path}'. "
                "Is the PLC editor open and is STweep licensed?"
            )

        doc = self._capture_document(file_path)
        self._retry_com(
            self._dte.ExecuteCommand, STWEEP_CMD_EDITOR,
            max_retries=5, delay_s=1,
        )
        self._wait_and_save_active(file_path, deadline, doc=doc)
        # Close so multi-file jobs do not leave dozens of editor tabs open
        # (UI folder Formatcode does not open each object as a document).
        self._close_active_if_path(file_path, doc=doc)

    def _capture_document(self, file_path: str):
        """Return ActiveDocument when it matches *file_path* (best-effort)."""
        try:
            doc = self._dte.ActiveDocument
            if doc is None:
                return None
            full = str(doc.FullName or "")
            if full and os.path.normcase(full) != os.path.normcase(file_path):
                return None
            return doc
        except Exception:
            return None

    def _doc_matches_path(self, doc, file_path: str) -> bool:
        if doc is None:
            return False
        try:
            full = str(doc.FullName or "")
        except Exception:
            return False
        if not full:
            return True
        return os.path.normcase(full) == os.path.normcase(file_path)

    def _doc_saved_state(self, doc) -> Optional[bool]:
        """Return Saved flag, or None if the COM object is unusable."""
        if doc is None:
            return None
        try:
            return bool(doc.Saved)
        except Exception:
            return None

    def _close_active_if_path(self, file_path: str, doc=None) -> None:
        """Close the formatted document (held ref preferred; already saved)."""
        candidates = []
        if doc is not None:
            candidates.append(doc)
        try:
            ad = self._dte.ActiveDocument
            if ad is not None and ad not in candidates:
                candidates.append(ad)
        except Exception:
            pass
        for candidate in candidates:
            if not self._doc_matches_path(candidate, file_path):
                continue
            try:
                # vsSaveChangesNo — we already saved when dirty
                self._retry_com(candidate.Close, False, max_retries=3, delay_s=0.5)
                return
            except Exception as exc:
                log.debug("Close after format %s: %s", file_path, exc)

    def _save_format_document(self, file_path: str, doc=None) -> None:
        """Save dirty buffer via held Document, else ActiveDocument."""
        candidates = []
        if doc is not None:
            candidates.append(doc)
        try:
            ad = self._dte.ActiveDocument
            if ad is not None and ad not in candidates:
                candidates.append(ad)
        except Exception:
            pass
        for candidate in candidates:
            if not self._doc_matches_path(candidate, file_path):
                continue
            try:
                if not bool(candidate.Saved):
                    self._retry_com(candidate.Save, max_retries=5, delay_s=0.5)
                return
            except Exception as exc:
                log.debug("Document.Save after format %s: %s", file_path, exc)

    def _wait_and_save_active(
        self, file_path: str, deadline: float, doc=None,
    ) -> None:
        """Save as soon as STweep dirties the buffer (held Document preferred).

        Live measurements: dirty ~50ms after Formatcode; ActiveDocument often
        dies after ~0.3s. A 1.2s min_wait misses the save window. On first
        dirty, wait ``_STWEEP_POST_DIRTY_S`` then Save on the held ref.
        """
        tai = _tai()
        end_wait = min(deadline, time.time() + _STWEEP_SETTLE_MAX_S)
        held = doc if doc is not None else self._capture_document(file_path)
        clean_polls = 0

        while time.time() < end_wait:
            if self._cancel_requested():
                break
            tai.pythoncom.PumpWaitingMessages()

            saved = self._doc_saved_state(held)
            if saved is None:
                # Held ref died — try ActiveDocument (may still be valid briefly)
                held = self._capture_document(file_path)
                saved = self._doc_saved_state(held)

            if saved is False:
                # Formatter is writing; short post then persist immediately.
                time.sleep(_STWEEP_POST_DIRTY_S)
                tai.pythoncom.PumpWaitingMessages()
                break

            # Still clean: allow a short grace for late dirty, then treat as no-op
            clean_polls += 1
            if clean_polls >= _STWEEP_CLEAN_POLLS:
                break
            time.sleep(_STWEEP_POLL_S)

        self._save_format_document(file_path, held)
