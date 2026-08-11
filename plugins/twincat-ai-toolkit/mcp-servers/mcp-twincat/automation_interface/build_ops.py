"""Build / CheckAllObjects / export / output-pane parsing."""
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
    CheckResult,
    BuildResult,
    ErrorEntry,
    ErrorsResult,
    ExportResult,
)


log = logging.getLogger("twincat-mcp")


def _tai():
    return sys.modules["twincat_automation_interface"]


class BuildOpsMixin:
    def check_all_objects(self) -> CheckResult:
        return self._call_sta(self._impl_check_all_objects, timeout=120)

    def build(self, timeout_s: int = 180, full_rebuild: bool = False) -> BuildResult:
        return self._call_sta(self._impl_build, timeout_s, full_rebuild, timeout=timeout_s + 60)

    def get_output_log(self) -> ErrorsResult:
        return self._call_sta(self._impl_get_output_log, timeout=30)

    def export_library(
        self,
        output_dir: str,
        title: str,
        version: str,
        library: bool = True,
        compiled_library: bool = True,
        install_library: bool = True,
        install_compiled_library: bool = False,
    ) -> ExportResult:
        """Export PLC project as .library and/or .compiled-library.

        Args:
            output_dir: Target directory for exported files.
            title: Library title (used in filename).
            version: Library version (used in filename).
            library: Export .library file.
            compiled_library: Export .compiled-library file.
            install_library: Install .library into local TwinCAT repo.
            install_compiled_library: Install .compiled-library into local TwinCAT repo.
        """
        return self._call_sta(
            self._impl_export_library, output_dir, title, version,
            library, compiled_library,
            install_library, install_compiled_library,
            timeout=120,
        )
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
        # The COM call returns synchronously when done. A short poll catches
        # late output; 4026 may not write to the Build pane at all.
        # Extended retry budget (10 × 3s = 30s) to survive modal dialogs
        # being dismissed or file-reload settling.
        try:
            self._retry_com(
                lambda: self._plc_proj_item.CheckAllObjects(),
                max_retries=10, delay_s=3,
            )
            self._wait_for_compile_complete(max_seconds=8)
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
            self._retry_com(
                self._dte.ExecuteCommand, "Build.Checkallobjects",
                max_retries=10, delay_s=3,
            )
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

    def _impl_build(self, timeout_s: int, full_rebuild: bool = False) -> BuildResult:
        if not self._dte:
            return BuildResult(
                success=False,
                message="No XAE instance. Call twincat_open first.",
            )

        ci_dir = self._compile_info_dir()
        ci_before = self._newest_compile_info_mtime(ci_dir)

        cmd = "Build.RebuildSolution" if full_rebuild else "Build.BuildSolution"
        self._clear_build_pane()
        start = time.time()
        self._retry_com(self._dte.ExecuteCommand, cmd, max_retries=10, delay_s=3)

        time.sleep(2)
        build_started = False
        while True:
            _tai().pythoncom.PumpWaitingMessages()
            try:
                state = int(self._dte.Solution.SolutionBuild.BuildState)
            except Exception as poll_exc:
                if self._is_retryable_com_error(poll_exc):
                    log.debug("BuildState poll busy, retrying: %s", poll_exc)
                    time.sleep(1)
                    continue
                raise
            if state == _tai()._VS_BUILD_STATE_IN_PROGRESS:
                build_started = True
            if build_started and state != _tai()._VS_BUILD_STATE_IN_PROGRESS:
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
        last_info = int(self._retry_com(
            lambda: self._dte.Solution.SolutionBuild.LastBuildInfo,
        ))
        bstate = int(self._retry_com(
            lambda: self._dte.Solution.SolutionBuild.BuildState,
        ))

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

            if any(m in low for m in self._COMPILE_COMPLETE_MARKERS) or "build complete" in low:
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
        self,
        output_dir: str,
        title: str,
        version: str,
        library: bool,
        compiled_library: bool,
        install_library: bool,
        install_compiled_library: bool,
    ) -> ExportResult:
        if not self._plc_proj_item:
            return ExportResult(
                success=False,
                message="No PLC project. Call twincat_open first.",
            )

        if not library and not compiled_library:
            return ExportResult(
                success=False,
                message="Nothing to export: both library and "
                        "compiled_library are false.",
            )

        check = self._impl_check_all_objects()
        if not check.success:
            return ExportResult(
                success=False,
                message=(
                    f"CheckAllObjects failed with {check.error_count} error(s). "
                    f"Fix all errors before exporting."
                ),
            )

        _INVALID_PATH_CHARS = set('<>:"/\\|?*')
        filename_part = f"{title}-{version}"
        if any(c in _INVALID_PATH_CHARS for c in filename_part):
            return ExportResult(
                success=False,
                message=f"Invalid characters in title/version: {filename_part}",
            )

        norm_out = os.path.realpath(output_dir)
        allowed_roots = [os.path.realpath(d) for d in [
            os.environ.get("TEMP", ""),
            os.environ.get("TMP", ""),
            os.path.dirname(self._sln_path) if self._sln_path else "",
            self._find_git_root(self._sln_path) if self._sln_path else "",
        ] if d]
        if not any(norm_out.startswith(r) for r in allowed_roots):
            return ExportResult(
                success=False,
                message=(
                    f"output_dir '{output_dir}' is outside allowed paths "
                    f"(solution dir, git repo root, or TEMP). Refusing to write."
                ),
            )

        os.makedirs(output_dir, exist_ok=True)
        result = ExportResult(success=True)
        msg_parts: list[str] = []

        # --- .library ---
        if library:
            lib_path = os.path.join(output_dir, f"{title}-{version}.library")
            try:
                self._plc_proj_item.SaveAsLibrary(lib_path, install_library)
                result.library_path = lib_path
                result.library_size_kb = round(os.path.getsize(lib_path) / 1024, 1)
                label = f"{result.library_size_kb} KB .library"
                if install_library:
                    label += " (installed)"
                msg_parts.append(label)
            except Exception as exc:
                result.success = False
                result.message = f".library export failed: {exc}"
                return result

        # --- .compiled-library ---
        if compiled_library:
            comp_path = os.path.join(output_dir, f"{title}-{version}.compiled-library")
            try:
                self._plc_proj_item.SaveAsLibrary(comp_path, install_compiled_library)
                result.compiled_library_path = comp_path
                result.compiled_library_size_kb = round(
                    os.path.getsize(comp_path) / 1024, 1
                )
                label = f"{result.compiled_library_size_kb} KB .compiled-library"
                if install_compiled_library:
                    label += " (installed)"
                msg_parts.append(label)
            except Exception as exc:
                result.success = False
                result.message = f".compiled-library export failed: {exc}"
                return result

        result.message = "Exported " + " + ".join(msg_parts)
        return result
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
            _tai().pythoncom.PumpWaitingMessages()
            time.sleep(0.5)


    _OUTPUT_WINDOW_CAPTIONS = {"output", "ausgabe"}

    def _get_output_pane(self, name_filter: str = "build") -> Optional[object]:
        """Find an OutputWindowPane by name substring (case-insensitive).

        For "build", also matches "erstellen" (German locale).
        The Output window caption is "Output" in English and "Ausgabe" in German.
        """
        try:
            for i in range(1, self._dte.Windows.Count + 1):
                w = self._dte.Windows.Item(i)
                if str(getattr(w, "Caption", "")).lower() in self._OUTPUT_WINDOW_CAPTIONS:
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
            _tai().pythoncom.PumpWaitingMessages()
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

