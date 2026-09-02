"""Session lifecycle: status, open, reload, close, ROT/registry."""
from __future__ import annotations

import glob
import logging
import os
import re
import sys
import time
from dataclasses import asdict
from typing import Optional

from results import (
    StatusResult,
    OpenResult,
    ReloadResult,
    CloseResult,
)


log = logging.getLogger("twincat-mcp")


def _tai():
    return sys.modules["twincat_automation_interface"]


class SessionOpsMixin:
    def get_status(self, timeout_s: int = 5) -> StatusResult:
        try:
            return self._call_sta(self._impl_get_status, timeout=timeout_s)
        except Exception as exc:
            log.warning(
                "get_status timed out or failed (%s) -- returning degraded status", exc
            )
            return StatusResult(
                xae_available=True,
                running_instance=False,
                message=f"Status check timed out after {timeout_s}s: {exc}",
            )

    def open_solution(
        self,
        sln_path: Optional[str] = None,
        plcproj_path: Optional[str] = None,
        proj_name: Optional[str] = None,
        timeout_s: int = 180,
        xae_version: Optional[str] = None,
    ) -> OpenResult:
        return self._call_sta(
            self._impl_open_solution,
            sln_path, plcproj_path, proj_name, timeout_s, xae_version,
            timeout=timeout_s + 60,
        )
    def reload_solution(self, timeout_s: int = 180) -> ReloadResult:
        return self._call_sta(
            self._impl_reload_solution, timeout_s, timeout=timeout_s + 60
        )

    def close(self, force_quit: bool = False) -> CloseResult:
        return self._call_sta(self._impl_close, force_quit, timeout=30)
    @staticmethod
    def _extract_pid_from_moniker(moniker_name: str) -> Optional[int]:
        """Extract PID from moniker like '!TcXaeShell.DTE.17.0:23572'."""
        if ":" in moniker_name:
            suffix = moniker_name.rsplit(":", 1)[-1]
            if suffix.isdigit():
                return int(suffix)
        return None

    @classmethod
    def _get_dte_pid(cls, dte, moniker: str = "") -> Optional[int]:
        """Get the OS process ID of a DTE instance via moniker or main window handle."""
        if moniker:
            from_mon = cls._extract_pid_from_moniker(moniker)
            if from_mon is not None:
                return from_mon
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

    @staticmethod
    def _save_if_dirty(dte, label: str = "") -> bool:
        """Save the solution if it has unsaved changes. Returns True if saved."""
        try:
            if dte.Solution.IsOpen and not dte.Solution.Saved:
                log.warning("Unsaved changes detected%s -- saving before close",
                            f" ({label})" if label else "")
                dte.Solution.Close(True)
                return True
        except Exception as exc:
            log.debug("_save_if_dirty check failed: %s", exc)
        return False

    def _quit_dte(self, dte, sln_label: str, pid: Optional[int] = None) -> bool:
        """Quit a DTE and ensure the process is actually dead.

        Returns True if the process was force-killed (i.e. Quit() timed out).
        """
        if not pid:
            pid = self._get_dte_pid(dte)
        try:
            self._save_if_dirty(dte, sln_label)
            dte.Solution.Close(False)
            dte.Quit()
        except Exception as exc:
            log.warning("Quit() failed for '%s': %s", sln_label, exc)

        if not pid:
            return False
        deadline = time.time() + _tai()._QUIT_WAIT_S
        while time.time() < deadline:
            if not self._is_pid_alive(pid):
                log.info("Process PID %d exited after Quit()", pid)
                return False
            time.sleep(_tai()._QUIT_POLL_S)
        log.warning("Process PID %d survived Quit() -- force-killing", pid)
        self._force_kill_pid(pid)
        return True

    def _cleanup_com(self):
        self._quit_all_instances()
        self._reset_state()

    def _quit_all_instances(self) -> int:
        """Quit every XAE instance we created (registry + active).

        Returns the number of instances that required a force-kill.
        """
        seen_ids = set()
        force_killed = 0
        if self._dte and self._created_new:
            seen_ids.add(id(self._dte))
            if self._quit_dte(self._dte, self._sln_path or "active"):
                force_killed += 1
            self._dte = None
            self._sys_man = None
            self._plc_proj_item = None
        for key, state in list(self._instances.items()):
            dte = state.get("dte")
            if dte and id(dte) not in seen_ids and state.get("created_new"):
                if self._quit_dte(dte, state.get("sln_path", key),
                                  pid=state.get("pid")):
                    force_killed += 1
            state["dte"] = None
            state["sys_man"] = None
            state["plc_proj_item"] = None
        self._instances.clear()
        return force_killed

    def _save_active_to_registry(self):
        """Persist current active session to the instance registry."""
        if not self._dte or not self._sln_path:
            return
        key = _tai()._canonical_path(self._sln_path)
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
            key = _tai()._canonical_path(self._sln_path)
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
                except Exception as exc:
                    if self._is_call_rejected(exc):
                        log.debug("Instance busy (modal dialog?), "
                                  "skipping prune: %s",
                                  state.get("sln_path", key))
                        continue
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
            actual_sln = _tai()._canonical_path(str(dte.Solution.FullName))
            if actual_sln != norm_sln:
                log.warning(
                    "Cached DTE solution changed: expected '%s', got '%s' "
                    "-- removing stale entry", norm_sln, actual_sln,
                )
                self._kill_orphaned_entry(state, norm_sln)
                return False
        except Exception as exc:
            if self._is_call_rejected(exc):
                log.warning("Cached DTE for '%s' is busy (modal dialog?) "
                            "-- restoring anyway", stored_sln)
            else:
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
        if not self._plcproj_file_path or not _tai().os.path.isfile(self._plcproj_file_path):
            self._plcproj_file_path = self._detect_plcproj_path()
        elif self._sln_path:
            sln_dir = _tai().os.path.dirname(self._sln_path)
            repo = self._find_git_root(self._sln_path) or sln_dir
            norm_plc = _tai().os.path.abspath(self._plcproj_file_path)
            if not (norm_plc.startswith(_tai().os.path.abspath(sln_dir)) or norm_plc.startswith(_tai().os.path.abspath(repo))):
                self._plcproj_file_path = self._detect_plcproj_path()
        self._ensure_silent_mode()
        log.info("Re-attached to cached XAE instance for '%s'",
                 self._sln_path)
        return True

    def _ensure_prog_id(self, preferred: Optional[str] = None) -> str:
        """Resolve and cache the TcXaeShell ProgID for COM calls."""
        if preferred:
            self._prog_id = _tai()._resolve_prog_id(preferred)
        elif not self._prog_id:
            self._prog_id = _tai()._resolve_prog_id()
        return self._prog_id

    def _enumerate_rot_dtes(self, prog_id_filter: Optional[str] = None):
        """Yield ``(prog_id, moniker_name, dte)`` for every running TcXaeShell.

        TcXaeShell registers ROT monikers as ``!TcXaeShell.DTE.X.Y:pid``.
        ``GetActiveObject`` only returns one instance per ProgID; ROT
        enumeration is required when multiple solutions are open.
        """
        if not _tai().HAS_WIN32:
            return
        try:
            rot = _tai().pythoncom.GetRunningObjectTable()
            enum = rot.EnumRunning()
            ctx = _tai().pythoncom.CreateBindCtx(0)
        except Exception as exc:
            log.debug("ROT enumeration unavailable: %s", exc)
            return

        prefixes = tuple(
            f"!{p}" for p in getattr(_tai(), "_ROT_PROG_ID_PREFIXES", (_tai()._PROG_ID_PREFIX,))
        )
        while True:
            try:
                mons = enum.Next(1)
            except Exception:
                break
            if not mons:
                break
            try:
                name = mons[0].GetDisplayName(ctx, None)
            except Exception:
                continue
            if not any(name.startswith(p) for p in prefixes):
                continue
            # "!TcXaeShell.DTE.17.0:23572" -> "TcXaeShell.DTE.17.0"
            body = name[1:]
            prog_id = body.split(":", 1)[0]
            if prog_id_filter and prog_id != prog_id_filter:
                continue
            try:
                obj = rot.GetObject(mons[0])
                dte = _tai().win32com.client.Dispatch(
                    obj.QueryInterface(_tai().pythoncom.IID_IDispatch)
                )
                yield prog_id, name, dte
            except Exception as exc:
                log.debug("ROT GetObject failed for %s: %s", name, exc)

    def _read_dte_solution_path(
        self, dte, *, retry_on_busy: bool = True,
    ) -> tuple[bool, str]:
        """Return ``(is_open, canonical_sln_path)`` for a DTE instance.

        When *retry_on_busy* is False (e.g. ``twincat_status``), a busy
        DTE returns ``(False, "")`` immediately instead of waiting.
        """
        try:
            is_open = bool(dte.Solution.IsOpen)
            if not is_open:
                return False, ""
            return True, _tai()._canonical_path(str(dte.Solution.FullName))
        except Exception as exc:
            if self._is_call_rejected(exc):
                if not retry_on_busy:
                    return False, ""
                try:
                    is_open = self._retry_com(
                        lambda: bool(dte.Solution.IsOpen),
                        max_retries=5, delay_s=1,
                    )
                    if not is_open:
                        return False, ""
                    return True, _tai()._canonical_path(str(self._retry_com(
                        lambda: dte.Solution.FullName,
                        max_retries=3, delay_s=1,
                    )))
                except Exception:
                    return False, ""
            return False, ""

    def _probe_dte_busy(self, dte) -> bool:
        """Return True if *dte* rejects COM with RPC_E_CALL_REJECTED (modal)."""
        if dte is None:
            return False
        try:
            _ = dte.MainWindow.Caption
            return False
        except Exception as exc:
            return self._is_call_rejected(exc)

    def _find_dte_by_solution(
        self,
        norm_sln: str,
        prog_id_filter: Optional[str] = None,
    ):
        """Find a running XAE whose open solution matches *norm_sln*.

        Returns ``(prog_id, dte)`` or ``(None, None)``.
        """
        if not norm_sln:
            return None, None
        for prog_id, moniker, dte in self._enumerate_rot_dtes(prog_id_filter):
            is_open, actual = self._read_dte_solution_path(dte)
            if is_open and actual == norm_sln:
                log.info("ROT match: %s has solution '%s'", moniker, norm_sln)
                return prog_id, dte
        return None, None

    def _find_empty_dte(self, prog_id_filter: Optional[str] = None):
        """Find a running XAE with no solution open.

        Returns ``(prog_id, dte)`` or ``(None, None)``.
        When *prog_id_filter* is None, prefers newer registered versions.
        """
        candidates = list(self._enumerate_rot_dtes(prog_id_filter))
        if not prog_id_filter:
            candidates.sort(
                key=lambda t: _tai()._prog_id_version_key(t[0]), reverse=True,
            )
        for prog_id, moniker, dte in candidates:
            is_open, _ = self._read_dte_solution_path(dte)
            if not is_open:
                log.info("ROT empty instance: %s", moniker)
                return prog_id, dte
        return None, None

    def _prefer_running_prog_id(
        self, preferred: Optional[str] = None,
    ) -> Optional[str]:
        """Pick ProgID for a *new* instance when none was requested.

        Priority:
          1. Explicit *preferred*
          2. A version that is already running (newest among running)
          3. None (caller falls back to newest registered)
        """
        if preferred:
            return preferred
        running: set[str] = set()
        for prog_id, _, _ in self._enumerate_rot_dtes():
            running.add(prog_id)
        if not running:
            return None
        for prog_id in _tai()._discover_registered_prog_ids():
            if prog_id in running:
                log.info("Preferring already-running XAE version %s (%s)",
                         _tai()._tc_version_label(prog_id), prog_id)
                return prog_id
        return next(iter(running))

    def _try_get_active_dte(self, prog_id: Optional[str] = None):
        """Attach to a running TcXaeShell ROT instance, if available."""
        candidates = [prog_id] if prog_id else _tai()._discover_registered_prog_ids()
        for candidate in candidates:
            if not candidate:
                continue
            try:
                dte = _tai().win32com.client.GetActiveObject(candidate)
                try:
                    _ = dte.MainWindow.Caption
                except Exception as caption_exc:
                    if self._is_call_rejected(caption_exc):
                        log.info("GetActiveObject(%s) OK but DTE busy "
                                 "(modal dialog?) -- attaching anyway",
                                 candidate)
                    else:
                        raise
                self._prog_id = candidate
                return dte
            except Exception as exc:
                log.debug("GetActiveObject(%s) failed: %s", candidate, exc)
        return None

    def _attach_dte(self, dte, prog_id: str, created_new: bool = False):
        """Bind *dte* as the active session and enable SilentMode."""
        self._dte = dte
        self._prog_id = prog_id
        self._created_new = created_new
        self._ensure_silent_mode()

    def _open_result(
        self,
        success: bool,
        message: str,
        *,
        created_new: bool = False,
        solution_path: str = "",
        plc_name: str = "",
    ) -> OpenResult:
        attached_ver = _tai()._tc_version_label(self._prog_id)
        requested = getattr(self, "_open_requested_xae", "") or ""
        pin_honored = getattr(self, "_open_pin_honored", None)
        pin_reason = getattr(self, "_open_pin_ignored_reason", "") or ""
        pid = self._get_dte_pid(self._dte) if self._dte else None
        instance_id = self._prog_id or ""
        if pid:
            instance_id = f"{instance_id}|pid={pid}" if instance_id else f"pid={pid}"
        open_solutions = []
        try:
            for key, state in (getattr(self, "_instances", {}) or {}).items():
                open_solutions.append({
                    "solution_path": state.get("sln_path") or key,
                    "xae_version": _tai()._tc_version_label(state.get("prog_id")),
                    "prog_id": state.get("prog_id") or "",
                    "pid": state.get("pid"),
                })
        except Exception:
            pass
        return OpenResult(
            success=success,
            solution_path=solution_path or (self._sln_path or ""),
            plc_project_name=plc_name,
            created_new_instance=created_new,
            xae_prog_id=self._prog_id or "",
            xae_version=attached_ver,
            message=message,
            requested_xae_version=requested,
            attached_xae_version=attached_ver,
            attached_instance_id=instance_id,
            pin_honored=pin_honored,
            pin_ignored_reason=pin_reason,
            open_solutions=open_solutions,
        )

    def _set_open_pin_state(
        self,
        requested: str,
        preferred_prog_id: Optional[str],
        *,
        ignored_reason: str = "",
    ):
        self._open_requested_xae = requested or ""
        if not preferred_prog_id:
            self._open_pin_honored = None
            self._open_pin_ignored_reason = ""
            return
        if ignored_reason:
            self._open_pin_honored = False
            self._open_pin_ignored_reason = ignored_reason
            return
        if self._prog_id and self._prog_id == preferred_prog_id:
            self._open_pin_honored = True
            self._open_pin_ignored_reason = ""
        elif self._prog_id:
            self._open_pin_honored = False
            self._open_pin_ignored_reason = (
                ignored_reason
                or (
                    f"attached {_tai()._tc_version_label(self._prog_id)} "
                    f"instead of requested {requested}"
                )
            )
        else:
            self._open_pin_honored = None
            self._open_pin_ignored_reason = ""

    def _create_dte_from_prog_id(self, prog_id: str):
        """Create a new out-of-process DTE for the given ProgID."""
        import winreg as _wreg

        _key = _wreg.OpenKey(_wreg.HKEY_CLASSES_ROOT, f"{prog_id}\\CLSID")
        _clsid_str = _wreg.QueryValueEx(_key, None)[0]
        _key.Close()
        clsid = _tai().pywintypes.IID(_clsid_str)
        dispatch = _tai().pythoncom.CoCreateInstance(
            clsid, None, _tai().pythoncom.CLSCTX_LOCAL_SERVER,
            _tai().pythoncom.IID_IDispatch,
        )
        self._prog_id = prog_id
        return _tai().win32com.client.Dispatch(dispatch)
    def _impl_get_status(self) -> StatusResult:
        self._prune_stale_instances()
        cached_slns = list(self._instances.keys())
        registered = _tai()._discover_registered_prog_ids()

        blocking_dialogs = self._enumerate_xae_dialogs()
        dismissed_recent = list(self._dismissed_dialogs[-20:])
        if dismissed_recent:
            self._dismissed_dialogs.clear()

        mcp_plc = ""
        if self._plc_proj_item and self._dte:
            try:
                mcp_plc = str(self._plc_proj_item.Name)
            except Exception:
                mcp_plc = ""

        mcp_session_active = bool(self._dte and self._is_dte_alive())
        mcp_sln = self._sln_path or ""
        silent_mode = self._read_silent_mode() if mcp_session_active else None
        sys_errs = self._read_sys_manager_errors()
        runtime_started = self._read_twincat_runtime_started()
        target_net_id = ""
        if hasattr(self, "_read_target_net_id_safe"):
            target_net_id = self._read_target_net_id_safe()

        # Enumerate ALL running instances via ROT (not just GetActiveObject)
        running: list[dict] = []
        start_rot_t = time.time()
        for prog_id, moniker, dte in self._enumerate_rot_dtes():
            if time.time() - start_rot_t > 3.0:
                log.warning("ROT status iteration exceeded 3.0s budget -- returning partial list")
                break
            pid = self._get_dte_pid(dte, moniker=moniker)
            busy = self._probe_dte_busy(dte)
            is_open, sln = False, ""
            if not busy:
                is_open, sln = self._read_dte_solution_path(
                    dte, retry_on_busy=False,
                )
            entry = {
                "prog_id": prog_id,
                "xae_version": _tai()._tc_version_label(prog_id),
                "moniker": moniker,
                "solution_path": sln if is_open else "",
                "dte_busy": busy,
            }
            if pid is not None:
                entry["pid"] = pid
            running.append(entry)

        def _build_message(base: str) -> str:
            parts = [base]
            busy_n = sum(1 for r in running if r.get("dte_busy"))
            if busy_n:
                parts.append(
                    f"{busy_n} instance(s) COM-busy (modal dialog?)"
                )
            if blocking_dialogs:
                auto = sum(
                    1 for d in blocking_dialogs if d.get("auto_dismissable")
                )
                parts.append(
                    f"{len(blocking_dialogs)} TcXaeShell dialog(s) visible"
                    f" ({auto} auto-dismissable)"
                )
            if mcp_session_active:
                parts.append("MCP session active")
            elif self._dte:
                parts.append("MCP session stale")
            if sys_errs:
                parts.append("SysManager has error messages")
            return " | ".join(parts)

        prereqs = {}
        if hasattr(self, "_ensure_prereqs"):
            try:
                prereqs = dict(self._ensure_prereqs())
            except Exception:
                prereqs = {}
        elif hasattr(self, "_prereqs") and isinstance(self._prereqs, dict):
            prereqs = dict(self._prereqs)
        if target_net_id and "target_net_id" not in prereqs:
            prereqs["target_net_id"] = target_net_id

        common_kw = dict(
            instances=running,
            mcp_session_active=mcp_session_active,
            mcp_solution_path=mcp_sln,
            mcp_plc_project_name=mcp_plc,
            silent_mode=silent_mode,
            blocking_dialogs=blocking_dialogs,
            dismissed_dialogs_recent=dismissed_recent,
            sys_manager_errors=sys_errs,
            twincat_runtime_started=runtime_started,
            target_net_id=target_net_id,
            prereqs=prereqs,
        )

        if running:
            primary = running[0]
            versions = ", ".join(
                f"{r['xae_version'] or r['prog_id']}"
                f"{'=' + os.path.basename(r['solution_path']) if r['solution_path'] else '=empty'}"
                f"{'(busy)' if r.get('dte_busy') else ''}"
                for r in running
            )
            msg = (
                f"TcXaeShell running: {len(running)} instance(s) [{versions}]"
            )
            if cached_slns:
                msg += f" | {len(cached_slns)} cached"
            return StatusResult(
                xae_available=True,
                running_instance=True,
                solution_path=primary["solution_path"],
                plc_project_name=mcp_plc,
                message=_build_message(msg),
                **common_kw,
            )

        # Fallback probe via GetActiveObject
        for prog_id in registered:
            try:
                dte = _tai().win32com.client.GetActiveObject(prog_id)
                busy = self._probe_dte_busy(dte)
                is_open, sln = self._read_dte_solution_path(
                    dte, retry_on_busy=False,
                )
                if not is_open and not busy:
                    try:
                        sln = (
                            str(dte.Solution.FullName)
                            if dte.Solution.IsOpen else ""
                        )
                    except Exception:
                        sln = ""
                running = [{
                    "prog_id": prog_id,
                    "xae_version": _tai()._tc_version_label(prog_id),
                    "moniker": "",
                    "solution_path": sln,
                    "dte_busy": busy,
                }]
                common_kw["instances"] = running
                return StatusResult(
                    xae_available=True,
                    running_instance=True,
                    solution_path=sln,
                    plc_project_name=mcp_plc,
                    message=_build_message(
                        f"TcXaeShell is running ({prog_id})"
                    ),
                    **common_kw,
                )
            except Exception as exc:
                log.debug("GetActiveObject probe failed for %s: %s", prog_id, exc)

        if registered:
            return StatusResult(
                xae_available=True,
                running_instance=False,
                message=_build_message(
                    f"TcXaeShell is installed ({registered[0]}) but not running"
                ),
                **common_kw,
            )

        return StatusResult(
            xae_available=False,
            running_instance=False,
            message=_build_message(
                "TcXaeShell not available: no registered ProgID found"
            ),
            **common_kw,
        )

    def _read_silent_mode(self) -> Optional[bool]:
        """Read TcAutomationSettings.SilentMode from the active DTE."""
        if not self._dte:
            return None
        try:
            settings = self._dte.GetObject("TcAutomationSettings")
            return bool(settings.SilentMode)
        except Exception as exc:
            log.debug("SilentMode read failed: %s", exc)
            return None

    def _read_sys_manager_errors(self) -> str:
        """Return ITcSysManager2.GetLastErrorMessages when SysMan is bound."""
        if not self._sys_man:
            return ""
        try:
            msgs = self._sys_man.GetLastErrorMessages()
            return str(msgs) if msgs else ""
        except Exception as exc:
            log.debug("GetLastErrorMessages failed: %s", exc)
            return ""

    def _read_twincat_runtime_started(self) -> Optional[bool]:
        """Return ITcSysManager.IsTwinCATStarted when SysMan is bound."""
        if not self._sys_man:
            return None
        try:
            return bool(self._sys_man.IsTwinCATStarted())
        except Exception as exc:
            log.debug("IsTwinCATStarted failed: %s", exc)
            return None

    # -------- open --------

    def _impl_open_solution(
        self, sln_path, plcproj_path, proj_name, timeout_s,
        xae_version=None,
    ) -> OpenResult:
        self._prune_stale_instances()

        preferred_prog_id: Optional[str] = None
        self._open_requested_xae = (xae_version or "").strip()
        self._open_pin_honored = None
        self._open_pin_ignored_reason = ""
        if xae_version:
            try:
                preferred_prog_id = _tai()._normalize_xae_version(xae_version)
            except ValueError as exc:
                return self._open_result(False, str(exc))
            if preferred_prog_id:
                # Prefer as filter only — do NOT mutate self._prog_id here.
                # Early _ensure_prog_id would overwrite the bound shell before
                # a solution-switch saves the active session to the registry.
                log.info("XAE version requested: %s (%s)",
                         xae_version, preferred_prog_id)

        expected_sln = sln_path
        if not expected_sln and plcproj_path:
            expected_sln = self._find_sln_near(plcproj_path)

        if plcproj_path:
            self._plcproj_file_path = plcproj_path
        elif self._sln_path and expected_sln and _tai()._canonical_path(expected_sln) != _tai()._canonical_path(self._sln_path):
            self._plcproj_file_path = None

        if expected_sln and not _tai().os.path.isfile(expected_sln):
            return self._open_result(
                False, f"Solution file not found: {expected_sln}",
            )

        norm_expected = (
            _tai()._canonical_path(expected_sln) if expected_sln else ""
        )

        # 0. If we already hold a DTE, verify it still matches
        if self._dte and norm_expected:
            is_open, current_sln = self._read_dte_solution_path(self._dte)
            if is_open and current_sln == norm_expected:
                log.info("Correct solution already bound to session")
            else:
                if self._dte and is_open:
                    self._save_active_to_registry()
                log.info("Active session solution mismatch -- searching ROT")
                self._dte = None
                self._sys_man = None
                self._plc_proj_item = None
                self._sln_path = None
                if not plcproj_path:
                    self._plcproj_file_path = None

        # 1. Registry: re-attach to a previously tracked instance
        if not self._dte and norm_expected:
            if self._restore_from_registry(norm_expected):
                if preferred_prog_id and self._prog_id and (
                    self._prog_id != preferred_prog_id
                ):
                    reason = (
                        f"solution already open in "
                        f"{_tai()._tc_version_label(self._prog_id)}; "
                        f"pin {xae_version} ignored"
                    )
                    log.warning(
                        "Registry instance is %s but %s was requested -- "
                        "keeping matching solution",
                        self._prog_id, preferred_prog_id,
                    )
                    self._set_open_pin_state(
                        xae_version or "", preferred_prog_id,
                        ignored_reason=reason,
                    )
                else:
                    self._set_open_pin_state(
                        xae_version or "", preferred_prog_id,
                    )
                return self._open_result(
                    True,
                    "Re-attached to existing XAE instance",
                    plc_name=(
                        str(self._plc_proj_item.Name)
                        if self._plc_proj_item else ""
                    ),
                )

        # 2. ROT: find ANY running instance that already has this solution
        #    (fixes multi-instance: GetActiveObject only sees one DTE)
        if not self._dte and norm_expected:
            # Prefer requested version when both have it (unlikely), else any
            prog_id, dte = (None, None)
            if preferred_prog_id:
                prog_id, dte = self._find_dte_by_solution(
                    norm_expected, preferred_prog_id,
                )
            if not dte:
                prog_id, dte = self._find_dte_by_solution(norm_expected)
            if dte and prog_id:
                if preferred_prog_id and prog_id != preferred_prog_id:
                    reason = (
                        f"solution already open in "
                        f"{_tai()._tc_version_label(prog_id)}; "
                        f"pin {xae_version} ignored"
                    )
                    log.warning(
                        "Solution is open in %s (%s), not requested %s -- "
                        "attaching to the running instance",
                        _tai()._tc_version_label(prog_id), prog_id,
                        preferred_prog_id,
                    )
                    self._set_open_pin_state(
                        xae_version or "", preferred_prog_id,
                        ignored_reason=reason,
                    )
                else:
                    self._set_open_pin_state(
                        xae_version or "", preferred_prog_id,
                    )
                self._attach_dte(dte, prog_id, created_new=False)
                self._we_opened_solution = False
                log.info("Attached to ROT instance with matching solution (%s)",
                         prog_id)

        # 3. ROT: empty instance of preferred / already-running version
        if not self._dte and expected_sln:
            empty_filter = preferred_prog_id or self._prefer_running_prog_id()
            prog_id, dte = self._find_empty_dte(empty_filter)
            if not dte and preferred_prog_id:
                # No empty of preferred version -- don't steal another version's empty
                pass
            elif not dte and empty_filter:
                prog_id, dte = self._find_empty_dte(None)
            if dte and prog_id:
                self._attach_dte(dte, prog_id, created_new=False)
                log.info("XAE running but no solution open -- opening %s",
                         expected_sln)
                try:
                    self._retry_com(
                        self._dte.Solution.Open, expected_sln,
                        max_retries=5, delay_s=2,
                    )
                    self._wait_for_solution_open(timeout_s)
                    self._we_opened_solution = True
                except Exception as exc:
                    log.warning("Failed to open solution in empty XAE: %s", exc)
                    self._dte = None

        # 4. Fallback: GetActiveObject (single instance per ProgID)
        if not self._dte:
            attach_prog = preferred_prog_id or self._prefer_running_prog_id()
            dte = self._try_get_active_dte(attach_prog)
            if dte:
                self._attach_dte(dte, self._prog_id or attach_prog or "",
                                 created_new=False)
                log.info("Attached to running TcXaeShell (%s)", self._prog_id)
                if norm_expected:
                    is_open, current_sln = self._read_dte_solution_path(self._dte)
                    if is_open and current_sln == norm_expected:
                        log.info("Correct solution already open")
                    elif not is_open:
                        log.info("XAE running but no solution open -- opening %s",
                                 expected_sln)
                        self._retry_com(
                            self._dte.Solution.Open, expected_sln,
                            max_retries=5, delay_s=2,
                        )
                        self._wait_for_solution_open(timeout_s)
                        self._we_opened_solution = True
                    else:
                        # Wrong solution -- do NOT reuse; search already done in ROT
                        log.info(
                            "GetActiveObject has '%s' -- not matching '%s'; "
                            "will start a separate instance",
                            current_sln, expected_sln,
                        )
                        self._save_active_to_registry()
                        self._dte = None

        # 5. No matching XAE -> start a new instance of the right version
        if not self._dte:
            if not expected_sln:
                return self._open_result(
                    False, "No .sln path and no running XAE instance",
                )
            create_prog = (
                preferred_prog_id
                or self._prefer_running_prog_id()
                or self._ensure_prog_id()
            )
            try:
                self._dte = self._create_new_dte(
                    expected_sln, timeout_s, prog_id=create_prog,
                )
            except Exception as exc:
                self._reset_state()
                if self._is_access_denied(exc):
                    log.warning("E_ACCESSDENIED creating new XAE: %s", exc)
                    return self._open_result(
                        False,
                        "Cannot start a new XAE instance -- another "
                        "instance is blocking COM access (E_ACCESSDENIED). "
                        "Close the other TcXaeShell manually, or call "
                        "twincat_close(force_quit=true) first.",
                    )
                raise

        # 6. Verify the correct solution is actually loaded
        if norm_expected:
            actual = ""
            try:
                actual = _tai()._canonical_path(
                    str(self._dte.Solution.FullName)
                )
            except Exception as exc:
                log.debug("Could not read Solution.FullName: %s", exc)
            if actual and actual != norm_expected:
                return self._open_result(
                    False,
                    f"SOLUTION MISMATCH: Expected '{expected_sln}', "
                    f"but XAE loaded '{self._dte.Solution.FullName}'. "
                    f"Close TcXaeShell manually and retry.",
                    solution_path=str(self._dte.Solution.FullName),
                )

        # 7. SystemManager
        self._sys_man = self._get_system_manager()
        if not self._sys_man:
            dte_sln = self._try_read_dte_sln()
            return self._open_result(
                False, "SystemManager not reachable",
                solution_path=dte_sln,
            )

        # 8. PLC project in tree
        if not proj_name:
            proj_name = self._guess_proj_name()
        self._plc_proj_item = self._find_plc_project_with_retry(
            proj_name, timeout_s=min(timeout_s, 60),
        )
        if not self._plc_proj_item:
            dte_sln = self._try_read_dte_sln()
            return self._open_result(
                False,
                f"PLC project '{proj_name}' not found in XAE tree. "
                f"Loaded solution: {dte_sln}",
                solution_path=dte_sln,
            )

        self._sln_path = str(self._dte.Solution.FullName)
        if not self._plcproj_file_path or not _tai().os.path.isfile(self._plcproj_file_path):
            self._plcproj_file_path = self._detect_plcproj_path()
        elif self._sln_path:
            sln_dir = _tai().os.path.dirname(self._sln_path)
            repo = self._find_git_root(self._sln_path) or sln_dir
            norm_plc = _tai().os.path.abspath(self._plcproj_file_path)
            if not (norm_plc.startswith(_tai().os.path.abspath(sln_dir)) or norm_plc.startswith(_tai().os.path.abspath(repo))):
                self._plcproj_file_path = self._detect_plcproj_path()
        # New solution open clears I/O prereq (devices may differ)
        if hasattr(self, "_ensure_prereqs"):
            prereqs = self._ensure_prereqs()
            prereqs["io_disabled_all"] = False
            prereqs["last_activate_ok"] = None
            prereqs["last_boot_ok"] = None
        if preferred_prog_id and not getattr(self, "_open_pin_ignored_reason", ""):
            self._set_open_pin_state(xae_version or "", preferred_prog_id)
        elif not preferred_prog_id:
            self._set_open_pin_state("", None)
        self._save_active_to_registry()
        plc_name = ""
        try:
            plc_name = str(self._retry_com(lambda: self._plc_proj_item.Name, max_retries=3, delay_s=0.5))
        except Exception:
            pass
        return self._open_result(
            True,
            "Solution open, PLC project found",
            created_new=self._created_new,
            plc_name=plc_name,
        )

    def _create_new_dte(
        self, expected_sln: str, timeout_s: int, prog_id: Optional[str] = None,
    ):
        """Start a truly new TcXaeShell process via CLSCTX_LOCAL_SERVER.

        Dispatch(prog_id) uses CLSCTX_SERVER which includes INPROC_SERVER
        and may reconnect to an existing process instead of spawning a new
        one.  Using CoCreateInstance with LOCAL_SERVER only ensures a fresh
        out-of-process DTE.
        """
        if prog_id:
            self._prog_id = prog_id
        else:
            prog_id = self._ensure_prog_id()
        log.info("Creating new TcXaeShell via CoCreateInstance(LOCAL_SERVER) "
                 "(%s / %s) for %s",
                 prog_id, _tai()._tc_version_label(prog_id), expected_sln)

        self._dte = self._create_dte_from_prog_id(prog_id)
        self._created_new = True
        self._we_opened_solution = True
        log.info("New TcXaeShell DTE created successfully (%s)", prog_id)

        for _init_retry in range(10):
            try:
                self._dte.SuppressUI = False
                self._dte.MainWindow.Visible = True
                self._dte.UserControl = True
                break
            except Exception as _init_exc:
                if self._is_retryable_com_error(_init_exc) and _init_retry < 9:
                    log.info("XAE not ready yet (retry %d/10): %s",
                             _init_retry + 1, _init_exc)
                    _tai().pythoncom.PumpWaitingMessages()
                    time.sleep(2)
                else:
                    raise

        self._ensure_silent_mode()

        self._wait_for_xae_idle(timeout_s)
        self._ensure_correct_solution(expected_sln, timeout_s)
        return self._dte

    def _ensure_correct_solution(self, expected_sln: str, timeout_s: int):
        """After Dispatch, ensure the correct solution is loaded.

        XAE may have auto-loaded its MRU solution during startup.
        If so, close it and open the requested one.
        Safe here because we own this XAE instance (_created_new).
        """
        norm_expected = _tai()._canonical_path(expected_sln)

        try:
            is_open = bool(self._dte.Solution.IsOpen)
        except Exception:
            is_open = False

        if is_open:
            current = _tai()._canonical_path(str(self._dte.Solution.FullName))
            if current == norm_expected:
                log.info("Correct solution already loaded by XAE")
                self._wait_for_solution_open(timeout_s)
                return
            log.info("XAE auto-loaded '%s' instead of '%s' -- switching",
                     current, norm_expected)
            if not self._save_if_dirty(self._dte, current):
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
            _tai().pythoncom.PumpWaitingMessages()
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
            _tai().pythoncom.PumpWaitingMessages()
            try:
                is_open = bool(self._dte.Solution.IsOpen)
            except Exception:
                is_open = False

            if is_open == last_open:
                stable_count += 1
            else:
                stable_count = 0
            last_open = is_open

            if is_open and stable_count >= _tai()._STABLE_OPEN_POLLS:
                log.info("XAE startup settled (solution open) after %.1fs",
                         time.time() - start)
                # Extra pump to let SystemManager register
                for _ in range(4):
                    _tai().pythoncom.PumpWaitingMessages()
                    time.sleep(0.5)
                return
            if not is_open and stable_count >= _tai()._STABLE_CLOSED_POLLS:
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
            _tai().pythoncom.PumpWaitingMessages()
            try:
                if not self._dte.Solution.IsOpen:
                    log.info("Solution closed after %.1fs",
                             time.time() - start)
                    time.sleep(1)
                    _tai().pythoncom.PumpWaitingMessages()
                    return
            except Exception as exc:
                log.debug("Solution.IsOpen check failed (treating as closed): %s", exc)
                return
            time.sleep(0.5)
        log.warning("Timeout (%ds) waiting for solution to close", timeout_s)

    def _guess_proj_name(self) -> str:
        """Derive PLC project name from plcproj metadata, then sln basename."""
        if self._plcproj_file_path and os.path.isfile(self._plcproj_file_path):
            name = self._read_plcproj_name(self._plcproj_file_path)
            if name:
                return name
        try:
            sln_name = os.path.basename(str(self._dte.Solution.FullName))
            return os.path.splitext(sln_name)[0]
        except Exception:
            return ""

    @staticmethod
    def _read_plcproj_name(plcproj_path: str) -> str:
        """Read <Name> from .plcproj XML (no external dependencies)."""
        try:
            import xml.etree.ElementTree as _ET
            _tree = _ET.parse(plcproj_path)
            _ns = {"ms": "http://schemas.microsoft.com/developer/msbuild/2003"}
            el = _tree.getroot().find(".//ms:Name", _ns)
            if el is not None and el.text:
                return el.text.strip()
        except Exception:
            pass
        return os.path.splitext(os.path.basename(plcproj_path))[0]

    def _try_read_dte_sln(self) -> str:
        """Read Solution.FullName from the active DTE, empty on failure."""
        try:
            return str(self._dte.Solution.FullName)
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
            _tai().pythoncom.PumpWaitingMessages()
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
            _tai().pythoncom.PumpWaitingMessages()
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
            _tai().pythoncom.PumpWaitingMessages()
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
            f"TIPC^{proj_name}^{proj_name} Instanz^{proj_name} Project",
            f"TIPC^{proj_name}^{proj_name} Instanz^{proj_name} Projekt",
            f"TIPC^{proj_name}^{proj_name} Instance",
            f"TIPC^{proj_name}^{proj_name} Instanz",
            f"TIPC^{proj_name} Instance^{proj_name} Project",
            f"TIPC^{proj_name} Instance^{proj_name} Projekt",
            f"TIPC^{proj_name} Instanz^{proj_name} Project",
            f"TIPC^{proj_name} Instanz^{proj_name} Projekt",
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
                or name.endswith(" Instanz")
            ):
                if self._is_plc_project_item(child):
                    return child
            found = self._walk_tree(child, depth + 1)
            if found:
                return found
        return None

    @staticmethod
    def _find_git_root(start: str) -> str:
        """Walk upward from start to find a directory containing .git."""
        d = os.path.dirname(start) if os.path.isfile(start) else start
        for _ in range(8):
            if os.path.isdir(os.path.join(d, ".git")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
        return ""

    def _detect_plcproj_path(self) -> Optional[str]:
        """Auto-detect the .plcproj file from the solution directory tree."""
        if not self._sln_path:
            return None
        sln_dir = os.path.dirname(self._sln_path)
        if not os.path.isdir(sln_dir):
            return None

        # 1. Try reading directly from plc_proj_item
        plc_item = getattr(self, "_plc_proj_item", None)
        if plc_item:
            try:
                if hasattr(plc_item, "FileName") and plc_item.FileName:
                    fn = str(plc_item.FileName)
                    if fn.endswith(".plcproj") and os.path.isfile(fn):
                        return os.path.abspath(fn)
            except Exception:
                pass
            try:
                if hasattr(plc_item, "FileNames"):
                    fn = str(plc_item.FileNames(1))
                    if fn.endswith(".plcproj") and os.path.isfile(fn):
                        return os.path.abspath(fn)
            except Exception:
                pass

        proj_name = self._normalize_proj_name(
            str(plc_item.Name)
        ) if plc_item else ""

        from twincat_core.constants import filter_scan_dirnames
        first_match = None
        for dirpath, dirnames, files in os.walk(sln_dir):
            filter_scan_dirnames(dirnames, dirpath)
            for f in files:
                if not f.endswith(".plcproj"):
                    continue
                found = os.path.abspath(os.path.join(dirpath, f))
                if proj_name and os.path.splitext(f)[0].lower() == proj_name.lower():
                    log.info("Auto-detected plcproj by name '%s': %s", proj_name, found)
                    return found
                if first_match is None:
                    first_match = found

        if first_match:
            log.info("Auto-detected plcproj (first match in solution dir): %s", first_match)
            return first_match
        return None

    @staticmethod
    def _find_sln_near(plcproj_path: str) -> Optional[str]:
        d = os.path.dirname(plcproj_path)
        for _ in range(5):
            for f in glob.glob(os.path.join(d, "*.sln")):
                return f
            d = os.path.dirname(d)
        return None

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
        log.info("Reload: closing solution ...")
        try:
            if not self._save_if_dirty(self._dte, sln_path):
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
            force_killed = self._quit_all_instances()
            self._reset_state()
            msg = f"All XAE instances quit ({count} tracked)"
            if force_killed:
                msg += (f" -- WARNING: {force_killed} instance(s) "
                        f"required force-kill (unsaved data may be lost)")
            return CloseResult(success=True, message=msg)

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
                    was_killed = self._quit_dte(self._dte, self._sln_path or "active")
                    msg = "XAE quit"
                    if was_killed:
                        msg += " (force-killed after timeout)"
                elif self._we_opened_solution:
                    try:
                        if self._dte.Solution.IsOpen:
                            if not self._save_if_dirty(self._dte, self._sln_path or ""):
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
        self._msg_baseline = None
        self._open_requested_xae = ""
        self._open_pin_honored = None
        self._open_pin_ignored_reason = ""
        if hasattr(self, "_prereqs"):
            self._prereqs = {
                "io_disabled_all": False,
                "last_activate_ok": None,
                "last_boot_ok": None,
                "target_net_id": "",
            }

