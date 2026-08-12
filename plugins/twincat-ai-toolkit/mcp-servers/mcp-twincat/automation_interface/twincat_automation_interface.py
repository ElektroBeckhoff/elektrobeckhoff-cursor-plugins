"""
TwinCAT 3 Automation Interface (TE1000) COM bridge for TcXaeShell.

Implements the Beckhoff TwinCAT 3 Automation Interface (TE1000) on a dedicated
Single-Threaded Apartment thread to satisfy Windows COM threading requirements.
The public API is thread-safe and can be called from any thread (including
asyncio pools).

Reference: https://infosys.beckhoff.com/content/1031/tc3_automationinterface/

This module is the public facade: helpers and result types are re-exported here
so existing imports and unittest patches keep working.
"""

from __future__ import annotations

import atexit
import logging
import os  # noqa: F401  — re-exported for unittest patches
import queue
import threading
import time
from typing import Optional

from results import (  # noqa: F401
    StatusResult,
    OpenResult,
    CheckResult,
    BuildResult,
    ErrorEntry,
    ErrorsResult,
    ExportResult,
    ExportProgressResult,
    ReloadResult,
    CloseResult,
    TargetResult,
    ActivateResult,
    StartResult,
    TaskListResult,
    TaskInfoResult,
    IoListResult,
    IoDisableResult,
    RuntimeMessagesResult,
    StweepStatusResult,
    StweepFormatResult,
    StweepFormatProgressResult,
    StweepFormatCancelResult,
    SMDS_NOT_DISABLED,
    SMDS_DISABLED,
)
from progids import (  # noqa: F401
    PROG_ID,
    _PROG_ID_PREFIX,
    _DEFAULT_PROG_ID,
    _XAE_VERSION_ALIASES,
    _PROG_ID_TO_TC_VERSION,
    _prog_id_version_key,
    _discover_registered_prog_ids,
    _normalize_xae_version,
    _tc_version_label,
    _resolve_prog_id,
)
from paths import _canonical_path  # noqa: F401
from com_retry import (  # noqa: F401
    RPC_E_CALL_REJECTED,
    RPC_S_SERVER_UNAVAILABLE,
    E_ACCESSDENIED,
    _QUIT_WAIT_S,
    _QUIT_POLL_S,
    _VS_BUILD_STATE_IN_PROGRESS,
    _VS_BUILD_STATE_DONE,
    _STABLE_OPEN_POLLS,
    _STABLE_CLOSED_POLLS,
    _RETRYABLE_HRESULTS,
    is_call_rejected,
    is_retryable_com_error,
    is_access_denied,
)
from dialogs import DialogOpsMixin
from session_ops import SessionOpsMixin
from build_ops import BuildOpsMixin
from runtime_ops import RuntimeOpsMixin
from stweep_ops import StweepOpsMixin

log = logging.getLogger("twincat-mcp")

HAS_WIN32 = False
HAS_WIN32GUI = False
pythoncom = None  # type: ignore
win32com = None  # type: ignore
pywintypes = None  # type: ignore
win32gui = None  # type: ignore
win32con = None  # type: ignore

try:
    import pythoncom as _pythoncom
    import win32com.client as _win32com_client
    import win32com as _win32com
    import pywintypes as _pywintypes
    pythoncom = _pythoncom
    win32com = _win32com
    pywintypes = _pywintypes
    HAS_WIN32 = True
except ImportError:
    pass

try:
    import win32gui as _win32gui
    import win32con as _win32con
    win32gui = _win32gui
    win32con = _win32con
    HAS_WIN32GUI = True
except ImportError:
    pass


def require_win32():
    if not HAS_WIN32:
        raise RuntimeError(
            "pywin32 is not installed. Run: pip install pywin32  "
            "This tool requires Windows with TwinCAT XAE."
        )


class TcAutomationInterface(
    DialogOpsMixin,
    SessionOpsMixin,
    BuildOpsMixin,
    RuntimeOpsMixin,
    StweepOpsMixin,
):
    """Thread-safe TwinCAT 3 Automation Interface (TE1000) bridge to TcXaeShell."""

    _RETRYABLE_HRESULTS = _RETRYABLE_HRESULTS

    def __init__(self):
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._sta_loop, daemon=True, name="COM-STA"
        )
        self._dte = None
        self._sys_man = None
        self._plc_proj_item = None
        self._created_new = False
        self._we_opened_solution = False
        self._sln_path: Optional[str] = None
        self._plcproj_file_path: Optional[str] = None
        self._prog_id: Optional[str] = None
        self._instances: dict = {}
        self._dismissed_dialogs: list[str] = []
        self._prereqs: dict = {
            "io_disabled_all": False,
            "last_activate_ok": None,
            "last_boot_ok": None,
            "target_net_id": "",
        }
        self._msg_baseline: Optional[dict] = None
        self._open_requested_xae: str = ""
        self._open_pin_honored: Optional[bool] = None
        self._open_pin_ignored_reason: str = ""
        self._stweep_license_ok: Optional[bool] = None
        self._stweep_license_detail: str = ""
        self._stweep_format_lock = threading.Lock()
        self._format_cancel_requested = False
        self._stweep_format_progress: dict = {
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
        if HAS_WIN32:
            self._thread.start()
            atexit.register(self.shutdown)

    def _sta_loop(self):
        pythoncom.CoInitialize()
        try:
            while True:
                pythoncom.PumpWaitingMessages()
                try:
                    item = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item is None:
                    break
                func, args, kwargs, result_q = item
                try:
                    result = func(*args, **kwargs)
                    result_q.put(("ok", result))
                except Exception as e:
                    result_q.put(("error", e))
        finally:
            self._cleanup_com()
            pythoncom.CoUninitialize()

    def _call_sta(self, func, *args, timeout=300, **kwargs):
        require_win32()
        result_q: queue.Queue = queue.Queue()
        self._queue.put((func, args, kwargs, result_q))

        stop_event = threading.Event()
        watcher = threading.Thread(
            target=self._dialog_dismiss_worker,
            args=(stop_event,),
            daemon=True,
            name="Dialog-Watcher",
        )
        watcher.start()

        try:
            status, value = result_q.get(timeout=timeout)
        finally:
            stop_event.set()
            watcher.join(timeout=5)

        if status == "error":
            raise value
        return value

    def shutdown(self):
        if HAS_WIN32 and self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout=15)

    def _cleanup_com(self):
        self._quit_all_instances()
        self._reset_state()

    def _ensure_silent_mode(self):
        if not self._dte:
            return
        for attempt in range(6):
            try:
                settings = self._dte.GetObject("TcAutomationSettings")
                settings.SilentMode = True
                log.info("TcAutomationSettings.SilentMode enabled")
                return
            except Exception as exc:
                if self._is_retryable_com_error(exc) and attempt < 5:
                    log.info("SilentMode COM busy (attempt %d/6): %s",
                             attempt + 1, exc)
                    pythoncom.PumpWaitingMessages()
                    time.sleep(2)
                    continue
                if self._is_retryable_com_error(exc):
                    log.warning("SilentMode COM still busy after 6 attempts")
                else:
                    log.debug("SilentMode not available "
                              "(requires Build >= 4020): %s", exc)
                return

    def _retry_com(self, func, *args, max_retries=5, delay_s=2):
        for attempt in range(max_retries):
            try:
                return func(*args)
            except Exception as exc:
                if self._is_retryable_com_error(exc) and attempt < max_retries - 1:
                    log.info("Retryable COM error (attempt %d/%d): %s",
                             attempt + 1, max_retries, exc)
                    pythoncom.PumpWaitingMessages()
                    time.sleep(delay_s)
                else:
                    raise

    @staticmethod
    def _is_call_rejected(exc: Exception) -> bool:
        return is_call_rejected(exc)

    @staticmethod
    def _is_retryable_com_error(exc: Exception) -> bool:
        return is_retryable_com_error(exc)

    @staticmethod
    def _is_access_denied(exc: Exception) -> bool:
        return is_access_denied(exc)

    def _is_dte_alive(self) -> bool:
        if not self._dte:
            return False
        try:
            _ = self._dte.MainWindow.Caption
            return True
        except Exception as exc:
            if self._is_call_rejected(exc):
                log.debug("DTE alive but busy (modal dialog?): %s", exc)
                return True
            return False
