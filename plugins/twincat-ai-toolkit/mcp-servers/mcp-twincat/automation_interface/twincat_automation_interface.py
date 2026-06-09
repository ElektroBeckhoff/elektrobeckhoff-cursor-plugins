"""
TwinCAT 3 Automation Interface (TE1000) COM bridge for TcXaeShell.

Implements the Beckhoff TwinCAT 3 Automation Interface (TE1000) on a dedicated
Single-Threaded Apartment thread to satisfy Windows COM threading requirements.
The public API is thread-safe and can be called from any thread (including
asyncio pools).

Reference: https://infosys.beckhoff.com/content/1031/tc3_automationinterface/
"""

import os
import re
import sys
import time
import glob
import threading
import queue
import logging
from typing import Optional
from dataclasses import dataclass, field, asdict

log = logging.getLogger("twincat-mcp")

# TwinCAT XAE shell ProgIDs follow Visual Studio versioning:
#   TcXaeShell.DTE.15.0 -> VS2017 / TwinCAT 4024
#   TcXaeShell.DTE.17.0 -> VS2022 / TwinCAT 4026
_PROG_ID_PREFIX = "TcXaeShell.DTE."
_DEFAULT_PROG_ID = f"{_PROG_ID_PREFIX}17.0"
# Backward-compatible alias for callers/tests that import PROG_ID.
PROG_ID = _DEFAULT_PROG_ID


def _discover_registered_prog_ids() -> list[str]:
    """Return registered TcXaeShell DTE ProgIDs, newest VS version first."""
    import winreg

    found: list[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "") as root:
            idx = 0
            while True:
                try:
                    name = winreg.EnumKey(root, idx)
                    idx += 1
                except OSError:
                    break
                if not name.startswith(_PROG_ID_PREFIX):
                    continue
                try:
                    winreg.OpenKey(
                        winreg.HKEY_CLASSES_ROOT, f"{name}\\CLSID"
                    ).Close()
                    found.append(name)
                except OSError:
                    continue
    except OSError:
        pass

    def _version_key(prog_id: str) -> tuple[int, ...]:
        suffix = prog_id[len(_PROG_ID_PREFIX):]
        parts: list[int] = []
        for piece in suffix.split("."):
            try:
                parts.append(int(piece))
            except ValueError:
                parts.append(-1)
        return tuple(parts)

    found.sort(key=_version_key, reverse=True)
    return found


def _resolve_prog_id(preferred: Optional[str] = None) -> str:
    """Pick the best TcXaeShell ProgID for COM access.

    Priority:
      1. Explicit preferred ProgID when registered
      2. Running ROT instance (newest registered version first)
      3. Newest registered ProgID
      4. Default fallback (_DEFAULT_PROG_ID)
    """
    registered = _discover_registered_prog_ids()
    if preferred and preferred in registered:
        return preferred

    for prog_id in registered:
        try:
            win32com.client.GetActiveObject(prog_id)
            return prog_id
        except Exception:
            continue

    if registered:
        return registered[0]
    return preferred or _DEFAULT_PROG_ID


def _canonical_path(p: str) -> str:
    """Canonical, case-folded absolute path (resolves symlinks, junctions, subst)."""
    try:
        resolved = os.path.realpath(p)
    except (OSError, ValueError):
        resolved = os.path.abspath(p)
    return os.path.normcase(resolved)
RPC_E_CALL_REJECTED = -2147418111   # 0x80010001 signed
RPC_S_SERVER_UNAVAILABLE = -2147023174  # 0x800706BA signed
E_ACCESSDENIED = -2147024891  # 0x80070005 signed

_QUIT_WAIT_S = 8
_QUIT_POLL_S = 0.3

_VS_BUILD_STATE_IN_PROGRESS = 2
_VS_BUILD_STATE_DONE = 3
_STABLE_OPEN_POLLS = 6     # ~3s at 0.5s interval
_STABLE_CLOSED_POLLS = 10  # ~5s at 0.5s interval

HAS_WIN32 = False
HAS_WIN32GUI = False
try:
    import pythoncom
    import win32com.client
    import pywintypes
    HAS_WIN32 = True
except ImportError:
    pass
try:
    import win32gui
    import win32con
    HAS_WIN32GUI = True
except ImportError:
    pass

# --------------- Result dataclasses ---------------

@dataclass
class StatusResult:
    xae_available: bool
    running_instance: bool
    solution_path: str = ""
    plc_project_name: str = ""
    message: str = ""

@dataclass
class OpenResult:
    success: bool
    solution_path: str = ""
    plc_project_name: str = ""
    created_new_instance: bool = False
    message: str = ""

@dataclass
class CheckResult:
    success: bool
    method: str = ""
    error_count: int = 0
    warning_count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    message: str = ""

@dataclass
class BuildResult:
    success: bool
    elapsed_seconds: float = 0.0
    build_state: int = 0
    last_build_info: int = 0
    compile_info_updated: bool = False
    error_count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    message: str = ""

@dataclass
class ErrorEntry:
    severity: str = ""
    description: str = ""
    file_name: str = ""
    line: int = 0
    column: int = 0
    project: str = ""

@dataclass
class ErrorsResult:
    count: int = 0
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    infos: list = field(default_factory=list)
    message: str = ""

@dataclass
class ExportResult:
    success: bool
    library_path: str = ""
    compiled_library_path: str = ""
    library_size_kb: float = 0.0
    compiled_library_size_kb: float = 0.0
    message: str = ""

@dataclass
class ReloadResult:
    success: bool
    elapsed_seconds: float = 0.0
    message: str = ""

@dataclass
class CloseResult:
    success: bool
    message: str = ""


def require_win32():
    if not HAS_WIN32:
        raise RuntimeError(
            "pywin32 is not installed. Run: pip install pywin32  "
            "This tool requires Windows with TwinCAT XAE."
        )


class TcAutomationInterface:
    """Thread-safe TwinCAT 3 Automation Interface (TE1000) bridge to TcXaeShell."""

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
        self._instances: dict = {}  # norm_sln_path → instance state dict
        if HAS_WIN32:
            self._thread.start()

    # ==================== STA event loop ====================

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

    # --------------- Modal dialog auto-dismiss ---------------

    _SAFE_DIALOG_PATTERNS = [
        "modified outside the environment",  # EN: XAE file-change dialog
        "file has been modified outside",    # EN: alternate wording
        "modified outside of twincat",       # EN: TwinCAT-specific variant
        "außerhalb der umgebung geändert",   # DE: XAE file-change dialog
        "außerhalb von twincat xae",         # DE: TwinCAT-specific variant
        "datei neu laden",                   # DE: "Datei neu laden?" prompt
    ]

    _POLL_IDLE_S = 0.5
    _POLL_BURST_S = 0.15

    def _dialog_dismiss_worker(self, stop_event: threading.Event):
        """Background worker that auto-dismisses known XAE modal dialogs.

        Runs alongside every COM call to prevent the STA thread from
        getting stuck on a modal dialog (e.g. "project modified outside
        of TwinCAT XAE -- reload?").  Only dismisses dialogs whose text
        matches a known safe pattern.

        When multiple files are modified, XAE shows one dialog per file
        in sequence.  After a successful dismiss the worker switches to
        a fast burst-poll so that the whole queue is cleared quickly.
        """
        if not HAS_WIN32GUI:
            return

        IDYES = 6  # MessageBox button ID for "Yes"/"Ja"

        while not stop_event.is_set():
            dismissed_any = False
            try:
                dismissed = []

                def enum_cb(hwnd, _):
                    if not win32gui.IsWindowVisible(hwnd):
                        return True
                    if win32gui.GetWindowText(hwnd) != "TcXaeShell":
                        return True
                    if win32gui.GetClassName(hwnd) != "#32770":
                        return True

                    dialog_texts = []
                    def enum_children(child_hwnd, _):
                        if win32gui.GetClassName(child_hwnd) == "Static":
                            text = win32gui.GetWindowText(child_hwnd)
                            if text:
                                dialog_texts.append(text.lower())
                        return True

                    try:
                        win32gui.EnumChildWindows(hwnd, enum_children, None)
                    except Exception:
                        return True

                    full_text = " ".join(dialog_texts)
                    if any(p in full_text for p in self._SAFE_DIALOG_PATTERNS):
                        win32gui.PostMessage(
                            hwnd, win32con.WM_COMMAND, IDYES, 0,
                        )
                        dismissed.append(hwnd)
                    return True

                win32gui.EnumWindows(enum_cb, None)

                for hwnd in dismissed:
                    log.info(
                        "Auto-dismissed TcXaeShell dialog (hwnd=%s)", hwnd,
                    )
                dismissed_any = bool(dismissed)
            except Exception as exc:
                log.debug("Dialog watcher error: %s", exc)

            delay = self._POLL_BURST_S if dismissed_any else self._POLL_IDLE_S
            stop_event.wait(delay)

    @staticmethod
    def _get_dte_pid(dte) -> Optional[int]:
        """Get the OS process ID of a DTE instance via its main window handle."""
        try:
            import ctypes
            hwnd = int(dte.MainWindow.HWnd)
            if not hwnd:
                return None
            pid = ctypes.c_ulong()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return pid.value if pid.value else None
        except Exception:
            return None

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        """Check if a process with the given PID is still running."""
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
            )
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(
                    handle, ctypes.byref(exit_code),
                )
                return exit_code.value == STILL_ACTIVE
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception:
            return False

    @staticmethod
    def _force_kill_pid(pid: int):
        """Terminate a process by PID."""
        try:
            import ctypes
            PROCESS_TERMINATE = 0x0001
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_TERMINATE, False, pid,
            )
            if handle:
                ctypes.windll.kernel32.TerminateProcess(handle, 1)
                ctypes.windll.kernel32.CloseHandle(handle)
                log.info("Force-killed process PID %d", pid)
        except Exception as exc:
            log.warning("Failed to force-kill PID %d: %s", pid, exc)

    def _quit_dte(self, dte, sln_label: str, pid: Optional[int] = None):
        """Quit a DTE and ensure the process is actually dead."""
        if not pid:
            pid = self._get_dte_pid(dte)
        try:
            dte.Solution.Close(False)
            dte.Quit()
        except Exception as exc:
            log.warning("Quit() failed for '%s': %s", sln_label, exc)

        if not pid:
            return
        deadline = time.time() + _QUIT_WAIT_S
        while time.time() < deadline:
            if not self._is_pid_alive(pid):
                log.info("Process PID %d exited after Quit()", pid)
                return
            time.sleep(_QUIT_POLL_S)
        log.warning("Process PID %d survived Quit() -- force-killing", pid)
        self._force_kill_pid(pid)

    def _cleanup_com(self):
        self._quit_all_instances()
        self._reset_state()

    def _quit_all_instances(self):
        """Quit every XAE instance we created (registry + active)."""
        seen_ids = set()
        if self._dte and self._created_new:
            seen_ids.add(id(self._dte))
            self._quit_dte(self._dte, self._sln_path or "active")
            self._dte = None
            self._sys_man = None
            self._plc_proj_item = None
        for key, state in list(self._instances.items()):
            dte = state.get("dte")
            if dte and id(dte) not in seen_ids and state.get("created_new"):
                self._quit_dte(dte, state.get("sln_path", key),
                               pid=state.get("pid"))
            state["dte"] = None
            state["sys_man"] = None
            state["plc_proj_item"] = None
        self._instances.clear()

    def _save_active_to_registry(self):
        """Persist current active session to the instance registry."""
        if not self._dte or not self._sln_path:
            return
        key = _canonical_path(self._sln_path)
        existing = self._instances.get(key)
        if existing and existing.get("created_new") and not self._created_new:
            self._created_new = True
            log.info("Restored ownership flag from registry for '%s'",
                     self._sln_path)
        pid = self._get_dte_pid(self._dte)
        if existing and existing.get("pid") and not pid:
            pid = existing["pid"]
        self._instances[key] = {
            "dte": self._dte,
            "sys_man": self._sys_man,
            "plc_proj_item": self._plc_proj_item,
            "created_new": self._created_new,
            "we_opened_solution": self._we_opened_solution,
            "sln_path": self._sln_path,
            "plcproj_file_path": self._plcproj_file_path,
            "pid": pid,
            "prog_id": self._prog_id,
        }
        log.info("Saved instance to registry: '%s' (pid=%s, created_new=%s, %d total)",
                 self._sln_path, pid, self._created_new, len(self._instances))

    def _remove_active_from_registry(self):
        """Remove the currently active session from the registry."""
        if self._sln_path:
            key = _canonical_path(self._sln_path)
            if self._instances.pop(key, None) is not None:
                log.info("Removed instance from registry: '%s' (%d remaining)",
                         self._sln_path, len(self._instances))

    def _prune_stale_instances(self):
        """Remove registry entries whose XAE process is no longer running."""
        pruned = 0
        for key in list(self._instances):
            state = self._instances[key]
            pid = state.get("pid")
            if pid and not self._is_pid_alive(pid):
                log.info("Pruned dead instance (PID %d gone): %s",
                         pid, state.get("sln_path", key))
                del self._instances[key]
                pruned += 1
                continue
            if not pid:
                try:
                    _ = state["dte"].MainWindow.Caption
                except Exception:
                    log.info("Pruned stale instance (COM unreachable): %s",
                             state.get("sln_path", key))
                    self._kill_orphaned_entry(state, key)
                    pruned += 1
        if pruned:
            log.info("Pruned %d stale instance(s), %d remaining",
                     pruned, len(self._instances))

    def _kill_orphaned_entry(self, state: dict, key: str):
        """Remove a registry entry and kill its process if we own it."""
        pid = state.get("pid")
        created_new = state.get("created_new", False)
        self._instances.pop(key, None)
        if created_new and pid and self._is_pid_alive(pid):
            log.warning("Killing orphaned process PID %d ('%s')",
                        pid, state.get("sln_path", key))
            self._force_kill_pid(pid)

    def _restore_from_registry(self, norm_sln: str) -> bool:
        """Try to restore a cached session.  Returns True on success."""
        state = self._instances.get(norm_sln)
        if not state:
            return False
        dte = state["dte"]
        stored_sln = state.get("sln_path", norm_sln)
        try:
            _ = dte.MainWindow.Caption
            actual_sln = _canonical_path(str(dte.Solution.FullName))
            if actual_sln != norm_sln:
                log.warning(
                    "Cached DTE solution changed: expected '%s', got '%s' "
                    "-- removing stale entry", norm_sln, actual_sln,
                )
                self._kill_orphaned_entry(state, norm_sln)
                return False
        except Exception:
            log.warning("Cached DTE for '%s' is stale -- removing",
                        stored_sln)
            self._kill_orphaned_entry(state, norm_sln)
            return False
        self._dte = dte
        self._sys_man = state["sys_man"]
        self._plc_proj_item = state["plc_proj_item"]
        self._created_new = state["created_new"]
        self._we_opened_solution = state["we_opened_solution"]
        self._sln_path = state["sln_path"]
        self._plcproj_file_path = state.get("plcproj_file_path")
        self._prog_id = state.get("prog_id") or self._prog_id
        log.info("Re-attached to cached XAE instance for '%s'",
                 self._sln_path)
        return True

    def _ensure_prog_id(self, preferred: Optional[str] = None) -> str:
        """Resolve and cache the TcXaeShell ProgID for COM calls."""
        if preferred:
            self._prog_id = _resolve_prog_id(preferred)
        elif not self._prog_id:
            self._prog_id = _resolve_prog_id()
        return self._prog_id

    def _try_get_active_dte(self, prog_id: Optional[str] = None):
        """Attach to a running TcXaeShell ROT instance, if available."""
        candidates = [prog_id] if prog_id else _discover_registered_prog_ids()
        for candidate in candidates:
            if not candidate:
                continue
            try:
                dte = win32com.client.GetActiveObject(candidate)
                _ = dte.MainWindow.Caption
                self._prog_id = candidate
                return dte
            except Exception as exc:
                log.debug("GetActiveObject(%s) failed: %s", candidate, exc)
        return None

    def _create_dte_from_prog_id(self, prog_id: str):
        """Create a new out-of-process DTE for the given ProgID."""
        import winreg as _wreg

        _key = _wreg.OpenKey(_wreg.HKEY_CLASSES_ROOT, f"{prog_id}\\CLSID")
        _clsid_str = _wreg.QueryValueEx(_key, None)[0]
        _key.Close()
        clsid = pywintypes.IID(_clsid_str)
        dispatch = pythoncom.CoCreateInstance(
            clsid, None, pythoncom.CLSCTX_LOCAL_SERVER,
            pythoncom.IID_IDispatch,
        )
        self._prog_id = prog_id
        return win32com.client.Dispatch(dispatch)

    def shutdown(self):
        if HAS_WIN32 and self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout=15)

    # ==================== Public API (thread-safe) ====================

    def get_status(self) -> StatusResult:
        return self._call_sta(self._impl_get_status)

    def open_solution(
        self,
        sln_path: Optional[str] = None,
        plcproj_path: Optional[str] = None,
        proj_name: Optional[str] = None,
        timeout_s: int = 180,
    ) -> OpenResult:
        return self._call_sta(
            self._impl_open_solution,
            sln_path, plcproj_path, proj_name, timeout_s,
            timeout=timeout_s + 60,
        )

    def check_all_objects(self) -> CheckResult:
        return self._call_sta(self._impl_check_all_objects, timeout=120)

    def build(self, timeout_s: int = 180) -> BuildResult:
        return self._call_sta(self._impl_build, timeout_s, timeout=timeout_s + 60)

    def get_output_log(self) -> ErrorsResult:
        return self._call_sta(self._impl_get_output_log, timeout=30)

    def export_library(
        self, output_dir: str, title: str, version: str
    ) -> ExportResult:
        return self._call_sta(
            self._impl_export_library, output_dir, title, version, timeout=120
        )

    def reload_solution(self, timeout_s: int = 180) -> ReloadResult:
        return self._call_sta(
            self._impl_reload_solution, timeout_s, timeout=timeout_s + 60
        )

    def close(self, force_quit: bool = False) -> CloseResult:
        return self._call_sta(self._impl_close, force_quit, timeout=30)

    # ==================== STA implementations ====================

    def _impl_get_status(self) -> StatusResult:
        self._prune_stale_instances()
        cached_slns = list(self._instances.keys())
        registered = _discover_registered_prog_ids()

        # Try attaching to any running instance (newest shell first)
        for prog_id in registered:
            try:
                dte = win32com.client.GetActiveObject(prog_id)
                sln = str(dte.Solution.FullName) if dte.Solution.IsOpen else ""
                plc = ""
                if self._plc_proj_item and self._dte:
                    try:
                        plc = str(self._plc_proj_item.Name)
                    except Exception:
                        plc = ""
                msg = f"TcXaeShell is running ({prog_id})"
                if cached_slns:
                    msg += f" | {len(cached_slns)} cached instance(s)"
                return StatusResult(
                    xae_available=True,
                    running_instance=True,
                    solution_path=sln,
                    plc_project_name=plc,
                    message=msg,
                )
            except Exception as exc:
                log.debug("GetActiveObject probe failed for %s: %s", prog_id, exc)

        # Check whether any shell COM class is registered
        if registered:
            return StatusResult(
                xae_available=True,
                running_instance=False,
                message=(
                    f"TcXaeShell is installed ({registered[0]}) but not running"
                ),
            )

        return StatusResult(
            xae_available=False,
            running_instance=False,
            message="TcXaeShell not available: no registered ProgID found",
        )

    # -------- open --------

    def _impl_open_solution(
        self, sln_path, plcproj_path, proj_name, timeout_s,
    ) -> OpenResult:
        self._prune_stale_instances()

        if plcproj_path:
            self._plcproj_file_path = plcproj_path

        expected_sln = sln_path
        if not expected_sln and plcproj_path:
            expected_sln = self._find_sln_near(plcproj_path)

        if expected_sln and not os.path.isfile(expected_sln):
            return OpenResult(
                success=False,
                message=f"Solution file not found: {expected_sln}",
            )

        norm_expected = (
            _canonical_path(expected_sln) if expected_sln else ""
        )

        # 1. Try attaching to a running instance
        if not self._dte:
            self._dte = self._try_get_active_dte()
            if self._dte:
                self._created_new = False
                log.info("Attached to running TcXaeShell (%s)", self._prog_id)

        # 2. If attached, check whether the loaded solution matches
        if self._dte and norm_expected:
            current_sln = ""
            sln_is_open = False
            dte_is_alive = True
            try:
                sln_is_open = bool(self._dte.Solution.IsOpen)
                if sln_is_open:
                    current_sln = _canonical_path(
                        str(self._dte.Solution.FullName)
                    )
            except Exception:
                dte_is_alive = False
                log.warning("DTE appears stale (Solution inaccessible) "
                            "-- dropping reference")
                self._dte = None

            if not self._dte:
                pass  # fall through to step 3
            elif not sln_is_open and dte_is_alive:
                log.info("XAE running but no solution open -- opening %s",
                         expected_sln)
                self._dte.Solution.Open(expected_sln)
                self._wait_for_solution_open(timeout_s)
                self._we_opened_solution = True
            elif current_sln == norm_expected:
                log.info("Correct solution already open")
            else:
                # Wrong solution open -- save current state, then switch.
                raw_current = str(self._dte.Solution.FullName)
                log.info(
                    "XAE has '%s' open -- switching to '%s'",
                    raw_current, expected_sln,
                )
                self._save_active_to_registry()
                self._dte = None

        # 2b. Check instance registry for a cached session
        if not self._dte and norm_expected:
            if self._restore_from_registry(norm_expected):
                return OpenResult(
                    success=True,
                    solution_path=self._sln_path,
                    plc_project_name=(
                        str(self._plc_proj_item.Name)
                        if self._plc_proj_item else ""
                    ),
                    created_new_instance=False,
                    message="Re-attached to existing XAE instance",
                )

        # 3. No XAE available -> start a new instance
        if not self._dte:
            if not expected_sln:
                return OpenResult(
                    success=False,
                    message="No .sln path and no running XAE instance",
                )
            try:
                self._dte = self._create_new_dte(expected_sln, timeout_s)
            except Exception as exc:
                self._reset_state()
                if self._is_access_denied(exc):
                    log.warning("E_ACCESSDENIED creating new XAE: %s", exc)
                    return OpenResult(
                        success=False,
                        message=(
                            "Cannot start a new XAE instance -- another "
                            "instance is blocking COM access (E_ACCESSDENIED). "
                            "Close the other TcXaeShell manually, or call "
                            "twincat_close(force_quit=true) first."
                        ),
                    )
                raise

        # 4. Verify the correct solution is actually loaded
        if norm_expected:
            actual = ""
            try:
                actual = _canonical_path(
                    str(self._dte.Solution.FullName)
                )
            except Exception as exc:
                log.debug("Could not read Solution.FullName: %s", exc)
            if actual and actual != norm_expected:
                return OpenResult(
                    success=False,
                    solution_path=str(self._dte.Solution.FullName),
                    message=(
                        f"SOLUTION MISMATCH: Expected '{expected_sln}', "
                        f"but XAE loaded '{self._dte.Solution.FullName}'. "
                        f"Close TcXaeShell manually and retry."
                    ),
                )

        # 5. SystemManager
        self._sys_man = self._get_system_manager()
        if not self._sys_man:
            return OpenResult(
                success=False,
                message="SystemManager not reachable",
            )

        # 6. PLC project in tree
        if not proj_name:
            proj_name = self._guess_proj_name()
        self._plc_proj_item = self._find_plc_project_with_retry(
            proj_name, timeout_s=min(timeout_s, 60),
        )
        if not self._plc_proj_item:
            current = ""
            try:
                current = str(self._dte.Solution.FullName)
            except Exception as exc:
                log.debug("Could not read Solution.FullName: %s", exc)
            return OpenResult(
                success=False,
                message=(
                    f"PLC project '{proj_name}' not found in XAE tree. "
                    f"Loaded solution: {current}"
                ),
            )

        self._sln_path = str(self._dte.Solution.FullName)
        self._save_active_to_registry()
        return OpenResult(
            success=True,
            solution_path=self._sln_path,
            plc_project_name=str(self._plc_proj_item.Name),
            created_new_instance=self._created_new,
            message="Solution open, PLC project found",
        )

    def _create_new_dte(self, expected_sln: str, timeout_s: int):
        """Start a truly new TcXaeShell process via CLSCTX_LOCAL_SERVER.

        Dispatch(prog_id) uses CLSCTX_SERVER which includes INPROC_SERVER
        and may reconnect to an existing process instead of spawning a new
        one.  Using CoCreateInstance with LOCAL_SERVER only ensures a fresh
        out-of-process DTE.
        """
        prog_id = self._ensure_prog_id()
        log.info("Creating new TcXaeShell via CoCreateInstance(LOCAL_SERVER) "
                 "(%s) for %s", prog_id, expected_sln)

        self._dte = self._create_dte_from_prog_id(prog_id)
        self._created_new = True
        self._we_opened_solution = True
        log.info("New TcXaeShell DTE created successfully (%s)", prog_id)

        for _init_retry in range(10):
            try:
                self._dte.SuppressUI = False
                self._dte.MainWindow.Visible = True
                self._dte.UserControl = False
                break
            except Exception as _init_exc:
                if self._is_retryable_com_error(_init_exc) and _init_retry < 9:
                    log.info("XAE not ready yet (retry %d/10): %s",
                             _init_retry + 1, _init_exc)
                    pythoncom.PumpWaitingMessages()
                    time.sleep(2)
                else:
                    raise

        try:
            settings = self._dte.GetObject("TcAutomationSettings")
            settings.SilentMode = True
            log.info("TcAutomationSettings.SilentMode enabled")
        except Exception:
            log.debug("SilentMode not available (requires Build >= 4020)")

        self._wait_for_xae_idle(timeout_s)
        self._ensure_correct_solution(expected_sln, timeout_s)
        return self._dte

    def _ensure_correct_solution(self, expected_sln: str, timeout_s: int):
        """After Dispatch, ensure the correct solution is loaded.

        XAE may have auto-loaded its MRU solution during startup.
        If so, close it and open the requested one.
        Safe here because we own this XAE instance (_created_new).
        """
        norm_expected = _canonical_path(expected_sln)

        try:
            is_open = bool(self._dte.Solution.IsOpen)
        except Exception:
            is_open = False

        if is_open:
            current = _canonical_path(str(self._dte.Solution.FullName))
            if current == norm_expected:
                log.info("Correct solution already loaded by XAE")
                self._wait_for_solution_open(timeout_s)
                return
            log.info("XAE auto-loaded '%s' instead of '%s' -- switching",
                     current, norm_expected)
            self._dte.Solution.Close(False)
            self._wait_for_solution_closed()

        self._dte.Solution.Open(expected_sln)
        self._wait_for_solution_open(timeout_s)

    def _wait_for_xae_idle(self, timeout_s: int):
        """Wait for XAE to finish its startup / auto-load sequence."""
        start = time.time()
        log.info("Waiting for XAE startup to settle ...")

        # Phase 1: wait until MainWindow is accessible
        for _ in range(timeout_s * 2):
            pythoncom.PumpWaitingMessages()
            try:
                _ = self._dte.MainWindow.Caption
                break
            except Exception:
                time.sleep(0.5)

        # Phase 2: let auto-load finish -- poll until Solution.IsOpen
        # stabilizes (either True or stays False for 5 seconds)
        stable_count = 0
        last_open = None
        while time.time() - start < min(timeout_s, 60):
            pythoncom.PumpWaitingMessages()
            try:
                is_open = bool(self._dte.Solution.IsOpen)
            except Exception:
                is_open = False

            if is_open == last_open:
                stable_count += 1
            else:
                stable_count = 0
            last_open = is_open

            if is_open and stable_count >= _STABLE_OPEN_POLLS:
                log.info("XAE startup settled (solution open) after %.1fs",
                         time.time() - start)
                # Extra pump to let SystemManager register
                for _ in range(4):
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.5)
                return
            if not is_open and stable_count >= _STABLE_CLOSED_POLLS:
                log.info("XAE startup settled (no solution) after %.1fs",
                         time.time() - start)
                return
            time.sleep(0.5)

        elapsed = round(time.time() - start, 1)
        log.info("XAE startup wait completed after %ss", elapsed)

    def _wait_for_solution_closed(self, timeout_s: int = 30):
        """Wait until Solution.IsOpen becomes False."""
        start = time.time()
        while time.time() - start < timeout_s:
            pythoncom.PumpWaitingMessages()
            try:
                if not self._dte.Solution.IsOpen:
                    log.info("Solution closed after %.1fs",
                             time.time() - start)
                    time.sleep(1)
                    pythoncom.PumpWaitingMessages()
                    return
            except Exception as exc:
                log.debug("Solution.IsOpen check failed (treating as closed): %s", exc)
                return
            time.sleep(0.5)
        log.warning("Timeout (%ds) waiting for solution to close", timeout_s)

    def _guess_proj_name(self) -> str:
        """Derive PLC project name from the loaded solution file name."""
        try:
            sln_name = os.path.basename(str(self._dte.Solution.FullName))
            return os.path.splitext(sln_name)[0]
        except Exception:
            return ""

    @staticmethod
    def _normalize_proj_name(name: str) -> str:
        """Strip localized PLC nested-project suffixes (EN/DE)."""
        for suffix in (" Project", " Projekt"):
            if name.endswith(suffix):
                return name[: -len(suffix)]
        return name

    def _wait_for_solution_open(self, timeout_s: int):
        start = time.time()
        while time.time() - start < timeout_s:
            pythoncom.PumpWaitingMessages()
            try:
                if self._dte.Solution.IsOpen:
                    break
            except Exception as exc:
                log.debug("Solution.IsOpen probe failed: %s", exc)
            time.sleep(1)
        else:
            raise TimeoutError(
                f"Timeout ({timeout_s}s) waiting for Solution.IsOpen"
            )

        while time.time() - start < timeout_s:
            pythoncom.PumpWaitingMessages()
            try:
                proj = self._dte.Solution.Projects.Item(1)
                _ = proj.Object
                elapsed = round(time.time() - start, 1)
                log.info("Solution ready (SystemManager reachable) after %ss", elapsed)
                return
            except Exception as exc:
                log.debug("SystemManager not yet reachable: %s", exc)
            time.sleep(1)

        raise TimeoutError(
            f"Timeout ({timeout_s}s) waiting for SystemManager"
        )

    def _get_system_manager(self):
        return self._retry_com(
            lambda: self._dte.Solution.Projects.Item(1).Object,
            max_retries=15, delay_s=3,
        )

    def _find_plc_project_with_retry(
        self, proj_name: str, timeout_s: int = 30,
    ):
        """Find PLC project node, retrying while the XAE tree lazy-loads."""
        start = time.time()
        while True:
            item = self._find_plc_project(proj_name)
            if item:
                return item
            elapsed = time.time() - start
            if elapsed >= timeout_s:
                break
            pythoncom.PumpWaitingMessages()
            time.sleep(1)
        return None

    def _find_plc_project(self, proj_name):
        # Primary: ITcProjectRoot.NestedProject (4026+ hides nested project from
        # LookupTreeItem and Child enumeration; works in EN and DE shells).
        try:
            plc_root = self._sys_man.LookupTreeItem(f"TIPC^{proj_name}")
            if hasattr(plc_root, "NestedProject"):
                nested = plc_root.NestedProject
                if nested and self._is_plc_project_item(nested):
                    log.info(
                        "PLC project found via NestedProject: %s",
                        nested.Name,
                    )
                    return nested
        except Exception as exc:
            log.debug("NestedProject lookup for '%s' failed: %s", proj_name, exc)

        lookup_paths = [
            f"TIPC^{proj_name}^{proj_name} Project",
            f"TIPC^{proj_name}^{proj_name} Projekt",
            f"TIPC^{proj_name}^{proj_name} Instance^{proj_name} Project",
            f"TIPC^{proj_name}^{proj_name} Instance^{proj_name} Projekt",
            f"TIPC^{proj_name}^{proj_name} Instance",
            f"TIPC^{proj_name} Instance^{proj_name} Project",
            f"TIPC^{proj_name} Instance^{proj_name} Projekt",
        ]
        for path in lookup_paths:
            try:
                item = self._sys_man.LookupTreeItem(path)
                if item and self._is_plc_project_item(item):
                    log.info("PLC project found at: %s", path)
                    return item
            except Exception as exc:
                log.debug("LookupTreeItem('%s') failed: %s", path, exc)
                continue

        # Fallback: walk the tree for a node exposing PLC project methods
        try:
            tipc = self._sys_man.LookupTreeItem("TIPC")
            return self._walk_tree(tipc, 0)
        except Exception as exc:
            log.debug("TIPC node lookup failed: %s", exc)
            return None

    @staticmethod
    def _is_plc_project_item(item) -> bool:
        """True when *item* exposes PLC project automation methods."""
        return (
            hasattr(item, "CheckAllObjects")
            or hasattr(item, "SaveAsLibrary")
        )

    def _walk_tree(self, node, depth):
        if depth > 8:
            return None
        try:
            if self._is_plc_project_item(node):
                return node
        except Exception:
            pass
        try:
            count = int(node.ChildCount)
        except Exception:
            return None
        for i in range(1, count + 1):
            try:
                child = node.Child(i)
            except Exception:
                continue
            name = str(child.Name)
            if (
                name.endswith("Project")
                or name.endswith("Projekt")
                or name.endswith(" Instance")
            ):
                if self._is_plc_project_item(child):
                    return child
            found = self._walk_tree(child, depth + 1)
            if found:
                return found
        return None

    @staticmethod
    def _find_sln_near(plcproj_path: str) -> Optional[str]:
        d = os.path.dirname(plcproj_path)
        for _ in range(5):
            for f in glob.glob(os.path.join(d, "*.sln")):
                return f
            d = os.path.dirname(d)
        return None

    # -------- check all objects --------

    def _impl_check_all_objects(self) -> CheckResult:
        if not self._plc_proj_item:
            return CheckResult(
                success=False,
                message="No PLC project. Call twincat_open first.",
            )

        self._flush_file_change_notifications()
        self._clear_build_pane()

        # Primary: ITcPlcIECProject.CheckAllObjects()
        try:
            self._retry_com(lambda: self._plc_proj_item.CheckAllObjects())
            self._wait_for_compile_complete(max_seconds=60)
            result = CheckResult(
                success=True,
                method="ITcPlcIECProject",
                message="CheckAllObjects completed via PLC project interface",
            )
            return self._merge_errors_into_check(result)
        except Exception as exc1:
            log.warning("CheckAllObjects interface failed: %s", exc1)

        self._clear_build_pane()

        # Fallback: DTE menu command
        try:
            self._retry_com(self._dte.ExecuteCommand, "Build.Checkallobjects")
            self._wait_for_compile_complete(max_seconds=60)
            result = CheckResult(
                success=True,
                method="DTE_Command",
                message="CheckAllObjects completed via DTE command (fallback)",
            )
            return self._merge_errors_into_check(result)
        except Exception as exc2:
            return CheckResult(
                success=False,
                method="unavailable",
                message=(
                    f"CheckAllObjects unavailable. "
                    f"Interface: {exc1} | DTE: {exc2}"
                ),
            )

    def _merge_errors_into_check(self, result: CheckResult) -> CheckResult:
        err = self._impl_get_output_log()
        result.error_count = err.count
        result.warning_count = len(err.warnings)
        result.errors = err.errors
        result.warnings = err.warnings
        result.infos = err.infos
        if err.count > 0:
            result.success = False
            result.message += f" | {err.count} error(s)"
        if err.warnings:
            result.message += f" | {len(err.warnings)} warning(s)"
        return result

    # -------- build --------

    def _impl_build(self, timeout_s: int) -> BuildResult:
        if not self._dte:
            return BuildResult(
                success=False,
                message="No XAE instance. Call twincat_open first.",
            )

        ci_dir = self._compile_info_dir()
        ci_before = self._newest_compile_info_mtime(ci_dir)

        self._clear_build_pane()
        start = time.time()
        self._retry_com(self._dte.ExecuteCommand, "Build.RebuildSolution")

        time.sleep(2)
        build_started = False
        while True:
            pythoncom.PumpWaitingMessages()
            state = int(self._dte.Solution.SolutionBuild.BuildState)
            if state == _VS_BUILD_STATE_IN_PROGRESS:
                build_started = True
            if build_started and state != _VS_BUILD_STATE_IN_PROGRESS:
                break
            elapsed = time.time() - start
            if not build_started and elapsed > 15:
                break
            if elapsed > timeout_s:
                return BuildResult(
                    success=False,
                    elapsed_seconds=round(elapsed, 1),
                    message=f"Build timeout ({timeout_s}s)",
                )
            time.sleep(0.5)

        time.sleep(1)
        elapsed = round(time.time() - start, 1)
        last_info = int(self._dte.Solution.SolutionBuild.LastBuildInfo)
        bstate = int(self._dte.Solution.SolutionBuild.BuildState)

        ci_updated = False
        if ci_dir and os.path.isdir(ci_dir):
            ci_updated = self._newest_compile_info_mtime(ci_dir) > ci_before

        ok = last_info == 0 and (ci_updated or ci_dir is None)

        err = self._impl_get_output_log()

        return BuildResult(
            success=ok,
            elapsed_seconds=elapsed,
            build_state=bstate,
            last_build_info=last_info,
            compile_info_updated=ci_updated,
            error_count=err.count,
            errors=err.errors,
            warnings=err.warnings,
            infos=err.infos,
            message="Build OK" if ok else "Build FAILED",
        )

    # -------- errors --------

    def _impl_get_output_log(self) -> ErrorsResult:
        if not self._dte:
            return ErrorsResult(message="No XAE instance")

        # TcXaeShell Isolated Shell does NOT support dte.ToolWindows.
        # Access windows via dte.Windows collection instead.
        return self._errors_from_build_output()

    def _errors_from_build_output(self) -> ErrorsResult:
        """Parse the Build pane of the Output window via dte.Windows.

        Only parses the LAST build session (from the last "------" header).
        """
        errors: list[dict] = []
        warnings: list[dict] = []
        summary_line = ""

        build_text = self._read_pane_text(self._get_output_pane("build"))
        twincat_text = self._read_pane_text(self._get_output_pane("twincat"))

        if build_text and twincat_text:
            build_text = build_text + "\n" + twincat_text
        elif twincat_text:
            build_text = twincat_text

        if not build_text:
            return ErrorsResult(
                message="Build output pane empty or not found"
            )

        # Only parse from the LAST build header ("------ Build started"
        # or "------ Erstellen gestartet") to avoid duplicates from
        # accumulated output.
        lines = build_text.splitlines()
        last_header_idx = 0
        for idx, line in enumerate(lines):
            if line.strip().startswith("------"):
                last_header_idx = idx

        infos: list[dict] = []

        for line in lines[last_header_idx:]:
            stripped = line.strip()
            if not stripped:
                continue
            low = stripped.lower()

            if "compile complete" in low or "build complete" in low:
                summary_line = stripped
                infos.append(asdict(ErrorEntry(
                    severity="info", description=stripped,
                )))
                continue

            if stripped.startswith("------"):
                infos.append(asdict(ErrorEntry(
                    severity="info", description=stripped,
                )))
                continue

            entry = self._parse_build_line(stripped)
            if entry:
                if ": error" in low or ": fehler" in low:
                    entry.severity = "error"
                    errors.append(asdict(entry))
                elif ": warning" in low or ": warnung" in low:
                    entry.severity = "warning"
                    warnings.append(asdict(entry))
            else:
                project = ""
                desc = stripped
                m_proj = re.match(r"^(.+?)\s{2,}(PLC\..+)$", stripped)
                if m_proj:
                    desc = m_proj.group(1)
                    project = m_proj.group(2)
                infos.append(asdict(ErrorEntry(
                    severity="info", description=desc, project=project,
                )))

        msg_parts = []
        if errors:
            msg_parts.append(f"{len(errors)} error(s)")
        if warnings:
            msg_parts.append(f"{len(warnings)} warning(s)")
        if infos:
            msg_parts.append(f"{len(infos)} info(s)")
        if summary_line:
            msg_parts.append(summary_line)
        msg = " | ".join(msg_parts) if msg_parts else "No output"

        return ErrorsResult(
            count=len(errors),
            errors=errors,
            warnings=warnings,
            infos=infos,
            message=msg,
        )

    @staticmethod
    def _parse_build_line(line: str) -> Optional[ErrorEntry]:
        """Parse a TwinCAT build output line into an ErrorEntry.

        Two known formats:
          Error:   <path>.TcPOU(<line>) : error: <message>
          Warning: <path>.TcPOU;<FB>.<Method>(<line>) : warning: <message>
        """
        if ": warning" not in line.lower() and ": error" not in line.lower():
            return None

        file_name = ""
        line_no = 0
        description = line

        colon_parts = line.split(" : ", 1)
        if len(colon_parts) == 2:
            location = colon_parts[0]
            description = colon_parts[1]

            m = re.search(r"\((\d+)\)", location)
            if m:
                line_no = int(m.group(1))

            if ";" in location:
                file_name = location.split(";")[0]
            else:
                file_name = re.sub(r"\(\d+\)\s*$", "", location).strip()

        return ErrorEntry(
            description=description,
            file_name=file_name,
            line=line_no,
        )

    # -------- export --------

    def _impl_export_library(
        self, output_dir: str, title: str, version: str
    ) -> ExportResult:
        if not self._plc_proj_item:
            return ExportResult(
                success=False,
                message="No PLC project. Call twincat_open first.",
            )

        _INVALID_PATH_CHARS = set('<>:"/\\|?*')
        filename_part = f"{title}-{version}"
        if any(c in _INVALID_PATH_CHARS for c in filename_part):
            return ExportResult(
                success=False,
                message=f"Invalid characters in title/version: {filename_part}",
            )

        os.makedirs(output_dir, exist_ok=True)
        lib = os.path.join(output_dir, f"{title}-{version}.library")
        comp = os.path.join(output_dir, f"{title}-{version}.compiled-library")

        result = ExportResult(success=True)

        try:
            self._plc_proj_item.SaveAsLibrary(lib, True)
            result.library_path = lib
            result.library_size_kb = round(os.path.getsize(lib) / 1024, 1)
        except Exception as exc:
            result.success = False
            result.message = f".library export failed: {exc}"
            return result

        try:
            self._plc_proj_item.SaveAsLibrary(comp, False)
            result.compiled_library_path = comp
            result.compiled_library_size_kb = round(
                os.path.getsize(comp) / 1024, 1
            )
        except Exception as exc:
            result.success = False
            result.message = f".compiled-library export failed: {exc}"
            return result

        result.message = (
            f"Exported {result.library_size_kb} KB .library + "
            f"{result.compiled_library_size_kb} KB .compiled-library"
        )
        return result

    # -------- reload --------

    def _impl_reload_solution(self, timeout_s: int) -> ReloadResult:
        """Close solution WITHOUT saving, then reopen it.

        This forces XAE to re-read all .TcPOU / .TcDUT / .TcGVL files
        from disk, picking up any changes made externally (e.g. by Cursor).
        """
        if not self._dte:
            return ReloadResult(
                success=False,
                message="No XAE instance. Call twincat_open first.",
            )

        if not self._is_dte_alive():
            log.warning("DTE is stale (not reachable) -- resetting session")
            self._reset_state()
            return ReloadResult(
                success=False,
                message=(
                    "XAE instance is no longer reachable (stale COM reference). "
                    "Call twincat_open to start a new session."
                ),
            )

        sln_path = ""
        try:
            sln_path = str(self._dte.Solution.FullName)
        except Exception as exc:
            log.debug("Could not read Solution.FullName for reload: %s", exc)
        if not sln_path:
            return ReloadResult(
                success=False,
                message="No solution path available for reload.",
            )

        proj_name = self._guess_proj_name()
        if not proj_name and self._plc_proj_item:
            try:
                proj_name = self._normalize_proj_name(
                    str(self._plc_proj_item.Name)
                )
            except Exception as exc:
                log.debug("Could not read PLC project name: %s", exc)

        start = time.time()
        log.info("Reload: closing solution (no save) ...")
        try:
            self._dte.Solution.Close(False)
            self._wait_for_solution_closed()
        except Exception as exc:
            return ReloadResult(
                success=False,
                message=f"Failed to close solution: {exc}",
            )

        self._sys_man = None
        self._plc_proj_item = None

        log.info("Reload: reopening %s ...", sln_path)
        try:
            self._dte.Solution.Open(sln_path)
            self._wait_for_solution_open(timeout_s)
        except Exception as exc:
            return ReloadResult(
                success=False,
                message=f"Failed to reopen solution: {exc}",
            )

        self._sys_man = self._get_system_manager()
        if not self._sys_man:
            return ReloadResult(
                success=False,
                elapsed_seconds=round(time.time() - start, 1),
                message="Reload: SystemManager not reachable after reopen",
            )

        if proj_name:
            self._plc_proj_item = self._find_plc_project_with_retry(
                proj_name, timeout_s=min(timeout_s, 60),
            )

        elapsed = round(time.time() - start, 1)
        plc_ok = self._plc_proj_item is not None
        return ReloadResult(
            success=plc_ok,
            elapsed_seconds=elapsed,
            message=(
                f"Solution reloaded from disk in {elapsed}s"
                + (", PLC project found" if plc_ok else ", PLC project NOT found")
            ),
        )

    # -------- close --------

    def _impl_close(self, force_quit: bool = False) -> CloseResult:
        """Close the active session (or all sessions with force_quit).

        Without force_quit:
          - Closes/detaches only the *active* XAE session.
          - Other cached instances in the registry stay alive.

        With force_quit=True:
          - Quits ALL tracked XAE instances (active + registry).
        """
        if force_quit:
            count = len(self._instances)
            log.info("force_quit: closing %d tracked instance(s)", count)
            self._quit_all_instances()
            self._reset_state()
            return CloseResult(
                success=True,
                message=f"All XAE instances quit ({count} tracked)",
            )

        msg = ""
        try:
            if self._dte and not self._is_dte_alive():
                log.warning("DTE is stale -- releasing without Quit")
                self._remove_active_from_registry()
                self._reset_state()
                return CloseResult(
                    success=True,
                    message="Session released (XAE was already gone)",
                )

            if self._dte:
                if self._created_new:
                    self._quit_dte(self._dte, self._sln_path or "active")
                    msg = "XAE quit"
                elif self._we_opened_solution:
                    try:
                        if self._dte.Solution.IsOpen:
                            self._dte.Solution.Close(False)
                    except Exception as exc:
                        log.debug("Solution.Close failed during detach: %s", exc)
                    msg = "Solution closed"
                else:
                    msg = "Detached (solution untouched)"

            self._remove_active_from_registry()
            self._reset_state()
            remaining = len(self._instances)
            if remaining:
                msg += f" ({remaining} other instance(s) still cached)"
            return CloseResult(success=True, message=msg or "Session released")
        except Exception as exc:
            self._remove_active_from_registry()
            self._reset_state()
            return CloseResult(success=False, message=f"Close error: {exc}")

    def _reset_state(self):
        self._dte = None
        self._sys_man = None
        self._plc_proj_item = None
        self._created_new = False
        self._we_opened_solution = False
        self._sln_path = None
        self._plcproj_file_path = None

    # ==================== Helpers (STA thread only) ====================

    def _compile_info_dir(self) -> Optional[str]:
        if self._plcproj_file_path:
            return os.path.join(
                os.path.dirname(self._plcproj_file_path), "_CompileInfo"
            )
        return None

    @staticmethod
    def _newest_compile_info_mtime(ci_dir: Optional[str]) -> float:
        if not ci_dir or not os.path.isdir(ci_dir):
            return 0.0
        files = glob.glob(os.path.join(ci_dir, "*.compileinfo"))
        return max((os.path.getmtime(f) for f in files), default=0.0)

    def _flush_file_change_notifications(self):
        """Pump COM messages so XAE processes FileSystemWatcher events.

        XAE detects external file changes via OS notifications, but only
        processes them during COM message pumping.  Without this, calling
        CheckAllObjects immediately after a disk write may compile the
        stale in-memory version.
        """
        for _ in range(6):
            pythoncom.PumpWaitingMessages()
            time.sleep(0.5)

    def _get_output_pane(self, name_filter: str = "build") -> Optional[object]:
        """Find an OutputWindowPane by name substring (case-insensitive).

        For "build", also matches "erstellen" (German locale).
        """
        try:
            for i in range(1, self._dte.Windows.Count + 1):
                w = self._dte.Windows.Item(i)
                if str(getattr(w, "Caption", "")).lower() == "output":
                    panes = w.Object.OutputWindowPanes
                    for j in range(1, panes.Count + 1):
                        pane = panes.Item(j)
                        name = str(pane.Name).lower()
                        if name_filter in name:
                            return pane
                        if name_filter == "build" and "erstellen" in name:
                            return pane
        except Exception as exc:
            log.debug("Failed to find output pane '%s': %s", name_filter, exc)
        return None

    @staticmethod
    def _read_pane_text(pane) -> str:
        """Read all text from an OutputWindowPane."""
        if not pane:
            return ""
        try:
            doc = pane.TextDocument
            sel = doc.Selection
            sel.SelectAll()
            return str(sel.Text)
        except Exception as exc:
            log.debug("Failed to read pane text: %s", exc)
            return ""

    def _clear_build_pane(self):
        """Clear the Build output pane so polling only sees fresh output."""
        pane = self._get_output_pane("build")
        if not pane:
            return
        try:
            pane.Clear()
        except Exception as exc:
            log.warning("Could not clear Build pane: %s", exc)

    _COMPILE_COMPLETE_MARKERS = (
        "compile complete",
        "kompilierung abgeschlossen",
        "erstellen abgeschlossen",
        "build abgeschlossen",
        "0 errors, 0 warnings",
        "0 fehler, 0 warnungen",
    )

    def _wait_for_compile_complete(self, max_seconds: int = 60):
        """Poll output panes until a compile-complete marker appears."""
        start = time.time()
        while time.time() - start < max_seconds:
            pythoncom.PumpWaitingMessages()
            build_text = self._read_build_pane_text()
            twincat_text = self._read_pane_text(
                self._get_output_pane("twincat")
            )
            combined = "\n".join(t for t in (build_text, twincat_text) if t)
            if combined:
                low = combined.lower()
                if any(m in low for m in self._COMPILE_COMPLETE_MARKERS):
                    log.info("Compile complete detected after %.1fs",
                             time.time() - start)
                    return
            time.sleep(0.5)
        log.warning("Timeout (%ds) waiting for compile complete", max_seconds)

    def _read_build_pane_text(self) -> str:
        """Read current text from the Build output pane."""
        return self._read_pane_text(self._get_output_pane("build"))


    def _retry_com(self, func, *args, max_retries=5, delay_s=2):
        """Call *func* with retry on transient COM errors (RPC_E_CALL_REJECTED).

        Same pattern already used in _get_system_manager and _create_new_dte,
        extracted here for reuse at other unprotected COM call sites.
        """
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

    _RETRYABLE_HRESULTS = {RPC_E_CALL_REJECTED, RPC_S_SERVER_UNAVAILABLE}

    @staticmethod
    def _is_call_rejected(exc: Exception) -> bool:
        return TcAutomationInterface._is_retryable_com_error(exc)

    @staticmethod
    def _is_retryable_com_error(exc: Exception) -> bool:
        retryable = TcAutomationInterface._RETRYABLE_HRESULTS
        if hasattr(exc, "hresult") and exc.hresult in retryable:
            return True
        for arg in getattr(exc, "args", ()):
            if isinstance(arg, int) and arg in retryable:
                return True
        return False

    @staticmethod
    def _is_access_denied(exc: Exception) -> bool:
        """Check if a COM exception contains E_ACCESSDENIED (0x80070005).

        pywintypes.com_error wraps DISP_E_EXCEPTION with the real scode
        in excepinfo[5], e.g.:
        (-2147352567, 'Ausnahmefehler...', (0, None, None, None, 0, -2147024891), None)
        """
        if hasattr(exc, "hresult") and exc.hresult == E_ACCESSDENIED:
            return True
        args = getattr(exc, "args", ())
        for arg in args:
            if isinstance(arg, int) and arg == E_ACCESSDENIED:
                return True
            if isinstance(arg, tuple) and len(arg) >= 6:
                if isinstance(arg[5], int) and arg[5] == E_ACCESSDENIED:
                    return True
        return False

    def _is_dte_alive(self) -> bool:
        """Quick health check -- can we still talk to the DTE?"""
        if not self._dte:
            return False
        try:
            _ = self._dte.MainWindow.Caption
            return True
        except Exception:
            return False
