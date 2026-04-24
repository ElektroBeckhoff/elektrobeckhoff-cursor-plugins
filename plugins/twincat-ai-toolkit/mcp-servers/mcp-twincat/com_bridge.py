"""
STA-threaded COM bridge for TcXaeShell automation.

All COM interactions run on a dedicated Single-Threaded Apartment thread
to satisfy Windows COM threading requirements.  The public API is
thread-safe and can be called from any thread (including asyncio pools).
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

PROG_ID = "TcXaeShell.DTE.15.0"
RPC_E_CALL_REJECTED = -2147418111  # 0x80010001 signed

HAS_WIN32 = False
try:
    import pythoncom
    import win32com.client
    import pywintypes
    HAS_WIN32 = True
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
    message: str = ""

@dataclass
class BuildResult:
    success: bool
    elapsed_seconds: float = 0.0
    build_state: int = 0
    last_build_info: int = 0
    compile_info_updated: bool = False
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


class ComBridge:
    """Thread-safe bridge to TcXaeShell COM automation."""

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
        status, value = result_q.get(timeout=timeout)
        if status == "error":
            raise value
        return value

    def _cleanup_com(self):
        if self._created_new and self._dte:
            try:
                self._dte.Solution.Close(False)
                self._dte.Quit()
            except Exception:
                pass
        self._reset_state()

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

    def get_errors(self) -> ErrorsResult:
        return self._call_sta(self._impl_get_errors, timeout=30)

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
        # Try attaching to a running instance
        try:
            dte = win32com.client.GetActiveObject(PROG_ID)
            sln = str(dte.Solution.FullName) if dte.Solution.IsOpen else ""
            plc = str(self._plc_proj_item.Name) if self._plc_proj_item else ""
            return StatusResult(
                xae_available=True,
                running_instance=True,
                solution_path=sln,
                plc_project_name=plc,
                message="TcXaeShell is running",
            )
        except Exception:
            pass

        # Check whether the COM class is registered (lightweight)
        try:
            import winreg
            winreg.OpenKey(
                winreg.HKEY_CLASSES_ROOT, f"{PROG_ID}\\CLSID"
            ).Close()
            return StatusResult(
                xae_available=True,
                running_instance=False,
                message="TcXaeShell is installed but not running",
            )
        except Exception as exc:
            return StatusResult(
                xae_available=False,
                running_instance=False,
                message=f"TcXaeShell not available: {exc}",
            )

    # -------- open --------

    def _impl_open_solution(
        self, sln_path, plcproj_path, proj_name, timeout_s,
    ) -> OpenResult:
        if plcproj_path:
            self._plcproj_file_path = plcproj_path

        expected_sln = sln_path
        if not expected_sln and plcproj_path:
            expected_sln = self._find_sln_near(plcproj_path)

        norm_expected = (
            os.path.normcase(os.path.abspath(expected_sln))
            if expected_sln else ""
        )

        # 1. Try attaching to a running instance
        if not self._dte:
            try:
                self._dte = win32com.client.GetActiveObject(PROG_ID)
                self._created_new = False
                log.info("Attached to running TcXaeShell")
            except Exception:
                self._dte = None

        # 2. If attached, check whether the loaded solution matches
        if self._dte and norm_expected:
            current_sln = ""
            sln_is_open = False
            try:
                sln_is_open = bool(self._dte.Solution.IsOpen)
                if sln_is_open:
                    current_sln = os.path.normcase(
                        os.path.abspath(str(self._dte.Solution.FullName))
                    )
            except Exception:
                pass

            if not sln_is_open:
                log.info("XAE running but no solution open -- opening %s",
                         expected_sln)
                self._dte.Solution.Open(expected_sln)
                self._wait_for_solution_open(timeout_s)
                self._we_opened_solution = True
            elif current_sln == norm_expected:
                log.info("Correct solution already open")
            else:
                # Wrong solution open -- leave it alone, start a
                # separate XAE instance for our solution.
                raw_current = str(self._dte.Solution.FullName)
                log.info(
                    "XAE has '%s' open -- starting separate instance "
                    "for '%s'",
                    raw_current, expected_sln,
                )
                self._dte = None  # release the attached instance

        # 3. No XAE available -> start a new instance
        if not self._dte:
            if not expected_sln:
                return OpenResult(
                    success=False,
                    message="No .sln path and no running XAE instance",
                )
            log.info("Starting new TcXaeShell with %s", expected_sln)
            self._dte = win32com.client.Dispatch(PROG_ID)
            self._created_new = True
            self._we_opened_solution = True
            self._dte.SuppressUI = False
            self._dte.MainWindow.Visible = True
            self._dte.UserControl = False

            self._wait_for_xae_idle(timeout_s)
            self._ensure_correct_solution(expected_sln, timeout_s)

        # 4. Verify the correct solution is actually loaded
        if norm_expected:
            actual = ""
            try:
                actual = os.path.normcase(
                    os.path.abspath(str(self._dte.Solution.FullName))
                )
            except Exception:
                pass
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
        self._plc_proj_item = self._find_plc_project(proj_name)
        if not self._plc_proj_item:
            current = ""
            try:
                current = str(self._dte.Solution.FullName)
            except Exception:
                pass
            return OpenResult(
                success=False,
                message=(
                    f"PLC project '{proj_name}' not found in XAE tree. "
                    f"Loaded solution: {current}"
                ),
            )

        self._sln_path = str(self._dte.Solution.FullName)
        return OpenResult(
            success=True,
            solution_path=self._sln_path,
            plc_project_name=str(self._plc_proj_item.Name),
            created_new_instance=self._created_new,
            message="Solution open, PLC project found",
        )

    def _ensure_correct_solution(self, expected_sln: str, timeout_s: int):
        """After Dispatch, ensure the correct solution is loaded.

        XAE may have auto-loaded its MRU solution during startup.
        If so, close it and open the requested one.
        Safe here because we own this XAE instance (_created_new).
        """
        norm_expected = os.path.normcase(os.path.abspath(expected_sln))

        try:
            is_open = bool(self._dte.Solution.IsOpen)
        except Exception:
            is_open = False

        if is_open:
            current = os.path.normcase(
                os.path.abspath(str(self._dte.Solution.FullName))
            )
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

            if is_open and stable_count >= 6:
                log.info("XAE startup settled (solution open) after %.1fs",
                         time.time() - start)
                # Extra pump to let SystemManager register
                for _ in range(4):
                    pythoncom.PumpWaitingMessages()
                    time.sleep(0.5)
                return
            if not is_open and stable_count >= 10:
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
            except Exception:
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

    def _wait_for_solution_open(self, timeout_s: int):
        start = time.time()
        while not self._dte.Solution.IsOpen:
            if time.time() - start > timeout_s:
                raise TimeoutError(
                    f"Timeout ({timeout_s}s) waiting for Solution.IsOpen"
                )
            pythoncom.PumpWaitingMessages()
            time.sleep(1)

        while time.time() - start < timeout_s:
            pythoncom.PumpWaitingMessages()
            try:
                proj = self._dte.Solution.Projects.Item(1)
                _ = proj.Object
                elapsed = round(time.time() - start, 1)
                log.info("Solution ready (SystemManager reachable) after %ss", elapsed)
                return
            except Exception as exc:
                if not self._is_call_rejected(exc):
                    pass
            time.sleep(1)

        raise TimeoutError(
            f"Timeout ({timeout_s}s) waiting for SystemManager"
        )

    def _get_system_manager(self):
        for retry in range(15):
            try:
                return self._dte.Solution.Projects.Item(1).Object
            except Exception as exc:
                if self._is_call_rejected(exc):
                    log.info("RPC_E_CALL_REJECTED, retry %d/15", retry + 1)
                    pythoncom.PumpWaitingMessages()
                    time.sleep(3)
                else:
                    raise
        return None

    def _find_plc_project(self, proj_name):
        lookup_paths = [
            f"TIPC^{proj_name}^{proj_name} Project",
            f"TIPC^{proj_name}^{proj_name} Instance^{proj_name} Project",
            f"TIPC^{proj_name} Instance^{proj_name} Project",
        ]
        for path in lookup_paths:
            try:
                item = self._sys_man.LookupTreeItem(path)
                if item:
                    log.info("PLC project found at: %s", path)
                    return item
            except Exception:
                continue

        # Fallback: walk the tree
        try:
            tipc = self._sys_man.LookupTreeItem("TIPC")
            return self._walk_tree(tipc, 0)
        except Exception:
            return None

    def _walk_tree(self, node, depth):
        if depth > 4:
            return None
        try:
            count = int(node.ChildCount)
        except Exception:
            return None
        for i in range(1, count + 1):
            try:
                child = node.Child(i)
                if str(child.Name).endswith("Project"):
                    return child
                found = self._walk_tree(child, depth + 1)
                if found:
                    return found
            except Exception:
                continue
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
            self._plc_proj_item.CheckAllObjects()
            self._wait_for_compile_complete(max_seconds=60)
            return CheckResult(
                success=True,
                method="ITcPlcIECProject",
                message="CheckAllObjects completed via PLC project interface",
            )
        except Exception as exc1:
            log.warning("CheckAllObjects interface failed: %s", exc1)

        self._clear_build_pane()

        # Fallback: DTE menu command
        try:
            self._dte.ExecuteCommand("Build.Checkallobjects")
            self._wait_for_compile_complete(max_seconds=60)
            return CheckResult(
                success=True,
                method="DTE_Command",
                message="CheckAllObjects completed via DTE command (fallback)",
            )
        except Exception as exc2:
            return CheckResult(
                success=False,
                method="unavailable",
                message=(
                    f"CheckAllObjects unavailable. "
                    f"Interface: {exc1} | DTE: {exc2}"
                ),
            )

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
        self._dte.ExecuteCommand("Build.RebuildSolution")

        time.sleep(2)
        build_started = False
        while True:
            pythoncom.PumpWaitingMessages()
            state = int(self._dte.Solution.SolutionBuild.BuildState)
            if state == 2:
                build_started = True
            if build_started and state != 2:
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

        ok = ci_updated and last_info == 0
        return BuildResult(
            success=ok,
            elapsed_seconds=elapsed,
            build_state=bstate,
            last_build_info=last_info,
            compile_info_updated=ci_updated,
            message="Build OK" if ok else "Build FAILED",
        )

    # -------- errors --------

    def _impl_get_errors(self) -> ErrorsResult:
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
        build_text = ""

        try:
            output_win = None
            for i in range(1, self._dte.Windows.Count + 1):
                w = self._dte.Windows.Item(i)
                if str(getattr(w, "Caption", "")).lower() == "output":
                    output_win = w.Object
                    break
            if not output_win:
                return ErrorsResult(message="Output window not found")

            panes = output_win.OutputWindowPanes
            twincat_text = ""
            for i in range(1, panes.Count + 1):
                try:
                    pane = panes.Item(i)
                    name = str(pane.Name).lower()
                    if "build" in name or "erstellen" in name:
                        doc = pane.TextDocument
                        sel = doc.Selection
                        sel.SelectAll()
                        build_text = str(sel.Text)
                    elif name == "twincat":
                        doc = pane.TextDocument
                        sel = doc.Selection
                        sel.SelectAll()
                        twincat_text = str(sel.Text)
                except Exception:
                    continue

            if build_text and twincat_text:
                build_text = build_text + "\n" + twincat_text
            elif twincat_text:
                build_text = twincat_text

            if not build_text:
                return ErrorsResult(
                    message="Build output pane empty or not found"
                )
        except Exception as exc:
            return ErrorsResult(
                message=f"Could not read Build output: {exc}"
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

        sln_path = ""
        try:
            sln_path = str(self._dte.Solution.FullName)
        except Exception:
            pass
        if not sln_path:
            return ReloadResult(
                success=False,
                message="No solution path available for reload.",
            )

        proj_name = ""
        if self._plc_proj_item:
            try:
                proj_name = str(self._plc_proj_item.Name).replace(" Project", "")
            except Exception:
                pass

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
            self._plc_proj_item = self._find_plc_project(proj_name)

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
        """Close only what WE opened.

        - ``_created_new``: We started XAE → close solution + quit.
        - ``_we_opened_solution``: We opened a solution into an
          existing empty XAE → close the solution, leave XAE running.
        - Otherwise: We just attached to the user's session →
          detach, touch nothing.
        - ``force_quit=True``: Always quit XAE (use with caution).
        """
        msg = ""
        try:
            if self._dte:
                if self._created_new or force_quit:
                    self._dte.Solution.Close(False)
                    self._dte.Quit()
                    msg = "XAE quit"
                elif self._we_opened_solution:
                    try:
                        if self._dte.Solution.IsOpen:
                            self._dte.Solution.Close(False)
                    except Exception:
                        pass
                    msg = "Solution closed"
                else:
                    msg = "Detached (solution untouched)"

            self._reset_state()
            return CloseResult(success=True, message=msg or "Session released")
        except Exception as exc:
            self._reset_state()
            return CloseResult(success=False, message=f"Close error: {exc}")

    def _reset_state(self):
        self._dte = None
        self._sys_man = None
        self._plc_proj_item = None
        self._created_new = False
        self._we_opened_solution = False

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

    def _clear_build_pane(self):
        """Clear the Build output pane so polling only sees fresh output."""
        try:
            for i in range(1, self._dte.Windows.Count + 1):
                w = self._dte.Windows.Item(i)
                if str(getattr(w, "Caption", "")).lower() == "output":
                    panes = w.Object.OutputWindowPanes
                    for j in range(1, panes.Count + 1):
                        pane = panes.Item(j)
                        name = str(pane.Name).lower()
                        if "build" in name or "erstellen" in name:
                            pane.Clear()
                            return
        except Exception as exc:
            log.warning("Could not clear Build pane: %s", exc)

    def _wait_for_compile_complete(self, max_seconds: int = 60):
        """Poll the Build output pane until 'Compile complete' appears."""
        start = time.time()
        while time.time() - start < max_seconds:
            pythoncom.PumpWaitingMessages()
            text = self._read_build_pane_text()
            if text and "compile complete" in text.lower():
                log.info("Compile complete detected after %.1fs",
                         time.time() - start)
                return
            time.sleep(0.5)
        log.warning("Timeout (%ds) waiting for 'Compile complete'", max_seconds)

    def _read_build_pane_text(self) -> str:
        """Read current text from the Build output pane."""
        try:
            for i in range(1, self._dte.Windows.Count + 1):
                w = self._dte.Windows.Item(i)
                if str(getattr(w, "Caption", "")).lower() == "output":
                    panes = w.Object.OutputWindowPanes
                    for j in range(1, panes.Count + 1):
                        pane = panes.Item(j)
                        name = str(pane.Name).lower()
                        if "build" in name or "erstellen" in name:
                            doc = pane.TextDocument
                            sel = doc.Selection
                            sel.SelectAll()
                            return str(sel.Text)
        except Exception:
            pass
        return ""

    def _wait_for_idle(self, max_seconds: int = 30):
        for _ in range(max_seconds * 2):
            pythoncom.PumpWaitingMessages()
            time.sleep(0.5)
            try:
                state = int(self._dte.Solution.SolutionBuild.BuildState)
                if state != 2:
                    return
            except Exception:
                pass

    @staticmethod
    def _is_call_rejected(exc: Exception) -> bool:
        if hasattr(exc, "hresult") and exc.hresult == RPC_E_CALL_REJECTED:
            return True
        for arg in getattr(exc, "args", ()):
            if isinstance(arg, int) and arg == RPC_E_CALL_REJECTED:
                return True
        return False
