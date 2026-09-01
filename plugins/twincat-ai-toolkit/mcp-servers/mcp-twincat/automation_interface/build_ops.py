"""Build / CheckAllObjects / export / output-pane parsing."""
from __future__ import annotations

import glob
import logging
import os
import re
import sys
import threading
import time
from dataclasses import asdict
from typing import Optional

from results import (
    CheckResult,
    BuildResult,
    ErrorEntry,
    ErrorsResult,
    ExportResult,
    ExportProgressResult,
    ExportArtifactsCheckResult,
)

_EXPORT_HEARTBEAT_S = 1.0


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
        wait: bool = False,
        timeout_s: int = 1800,
    ) -> ExportResult:
        """Export PLC project as .library and/or .compiled-library.

        ``wait=False`` (default, same as MCP ``twincat_export_library``): start
        on a background thread and return immediately; poll
        ``get_export_progress`` / ``twincat_export_progress`` until ``running``
        is false. ``wait=True``: block until finished (progress still updated).
        Prefer wait=false — Cursor MCP idle-timeouts long blocking tool calls
        even when XAE export succeeds. ``wait=true`` with
        ``timeout_s`` above the Cursor idle guard is coerced to async.
        """
        from mcp_idle import (
            async_coerced_message,
            should_coerce_wait_to_async,
        )

        coerced = should_coerce_wait_to_async(wait, timeout_s)
        if coerced:
            wait = False

        self._ensure_export_progress_state()
        with self._export_lock:
            if self._export_progress.get("running"):
                return ExportResult(
                    success=False,
                    method="busy",
                    message=(
                        "An export job is already running. "
                        "Poll twincat_export_progress until running=false."
                    ),
                    output_dir=output_dir,
                    project_title=title,
                    project_version=version,
                )
            now = time.time()
            start_msg = "Starting export job…"
            if coerced:
                start_msg = async_coerced_message("twincat_export_progress")
            self._export_progress.update({
                "running": True,
                "phase": "starting",
                "output_dir": output_dir or "",
                "project_title": title or "",
                "project_version": version or "",
                "percent": 0.0,
                "started_unix": now,
                "updated_unix": now,
                "message": start_msg,
                "result": None,
            })

        if not wait:
            result = self._start_export_library_async(
                output_dir, title, version,
                library, compiled_library,
                install_library, install_compiled_library,
                timeout_s,
            )
            if coerced and result.async_started:
                result.message = (
                    async_coerced_message("twincat_export_progress")
                    + " "
                    + (result.message or "")
                )
            return result

        try:
            result = self._run_export_sta(
                output_dir, title, version,
                library, compiled_library,
                install_library, install_compiled_library,
                timeout_s,
            )
            self._finish_export_progress(result)
            return result
        except Exception as exc:
            fail = ExportResult(
                success=False,
                method="error",
                message=str(exc),
                output_dir=output_dir,
                project_title=title,
                project_version=version,
            )
            self._finish_export_progress(fail)
            raise

    def get_export_progress(self) -> ExportProgressResult:
        """Read live export job progress (safe while export holds the STA)."""
        self._ensure_export_progress_state()
        with self._export_lock:
            p = dict(self._export_progress)
        started = float(p.get("started_unix") or 0.0)
        updated = float(p.get("updated_unix") or 0.0)
        elapsed = 0.0
        if started > 0:
            end = updated if not p.get("running") and updated > 0 else time.time()
            elapsed = max(0.0, round(end - started, 1))

        res_dict = p.get("result") or {}
        artifacts_on_disk = bool(res_dict.get("artifacts_on_disk"))
        artifacts = list(res_dict.get("artifacts") or [])
        lib_path = str(res_dict.get("library_path") or "")
        comp_path = str(res_dict.get("compiled_library_path") or "")

        # If phase is done and not already checked, verify artifacts on disk
        if not p.get("running") and p.get("phase") == "done" and not artifacts:
            out_dir = str(p.get("output_dir") or "")
            title = str(p.get("project_title") or "")
            ver = str(p.get("project_version") or "")
            if out_dir and title and ver:
                try:
                    check = self.check_export_artifacts(out_dir, title, ver)
                    artifacts_on_disk = check.all_present
                    artifacts = check.artifacts
                    for a in artifacts:
                        if a.get("kind") == "library" and a.get("exists"):
                            lib_path = a.get("path", "")
                        elif a.get("kind") == "compiled_library" and a.get("exists"):
                            comp_path = a.get("path", "")
                except Exception:
                    pass

        return ExportProgressResult(
            success=True,
            running=bool(p.get("running")),
            phase=str(p.get("phase") or "idle"),
            output_dir=str(p.get("output_dir") or ""),
            project_title=str(p.get("project_title") or ""),
            project_version=str(p.get("project_version") or ""),
            percent=float(p.get("percent") or 0.0),
            started_unix=started,
            updated_unix=updated,
            elapsed_s=elapsed,
            message=str(p.get("message") or ""),
            result=p.get("result"),
            artifacts_on_disk=artifacts_on_disk,
            artifacts=artifacts,
            library_path=lib_path,
            compiled_library_path=comp_path,
        )

    def _ensure_export_progress_state(self) -> None:
        if not hasattr(self, "_export_lock"):
            self._export_lock = threading.Lock()
        if not hasattr(self, "_export_progress"):
            self._export_progress = {
                "running": False,
                "phase": "idle",
                "output_dir": "",
                "project_title": "",
                "project_version": "",
                "percent": 0.0,
                "started_unix": 0.0,
                "updated_unix": 0.0,
                "message": "",
                "result": None,
            }

    def _update_export_progress(self, **kwargs) -> None:
        self._ensure_export_progress_state()
        with self._export_lock:
            self._export_progress.update(kwargs)
            self._export_progress["updated_unix"] = time.time()

    def _finish_export_progress(self, result: ExportResult) -> None:
        phase = "done" if result.success else "error"
        if result.method == "busy":
            return
        with self._export_lock:
            cur_pct = float(self._export_progress.get("percent") or 0.0)
        self._update_export_progress(
            running=False,
            phase=phase,
            percent=100.0 if phase == "done" else cur_pct,
            message=result.message or phase,
            result=asdict(result),
        )

    def _start_export_library_async(
        self,
        output_dir: str,
        title: str,
        version: str,
        library: bool,
        compiled_library: bool,
        install_library: bool,
        install_compiled_library: bool,
        timeout_s: int,
    ) -> ExportResult:
        def runner():
            try:
                result = self._run_export_sta(
                    output_dir, title, version,
                    library, compiled_library,
                    install_library, install_compiled_library,
                    timeout_s,
                )
                self._finish_export_progress(result)
            except Exception as exc:
                fail = ExportResult(
                    success=False,
                    method="error",
                    message=str(exc),
                    output_dir=output_dir,
                    project_title=title,
                    project_version=version,
                )
                if self.get_export_progress().running:
                    self._finish_export_progress(fail)

        threading.Thread(
            target=runner, name="TwinCAT-Export-Async", daemon=True,
        ).start()
        return ExportResult(
            success=True,
            method="async_started",
            async_started=True,
            output_dir=output_dir,
            project_title=title,
            project_version=version,
            message=(
                "Export started in background. "
                "Poll twincat_export_progress until running=false."
            ),
        )

    def _run_export_sta(
        self,
        output_dir: str,
        title: str,
        version: str,
        library: bool,
        compiled_library: bool,
        install_library: bool,
        install_compiled_library: bool,
        timeout_s: int,
    ) -> ExportResult:
        """Run export on STA with a progress heartbeat while COM blocks."""
        stop = threading.Event()
        started = time.time()

        def heartbeat():
            while not stop.wait(_EXPORT_HEARTBEAT_S):
                try:
                    prog = self.get_export_progress()
                    phase = prog.phase or "exporting"
                    elapsed = max(0.0, time.time() - started)
                    self._update_export_progress(
                        message=(
                            f"{phase} in progress (elapsed={elapsed:.0f}s)…"
                        ),
                    )
                except Exception:
                    pass

        hb = threading.Thread(
            target=heartbeat, name="TwinCAT-Export-Heartbeat", daemon=True,
        )
        hb.start()
        try:
            return self._call_sta(
                self._impl_export_library, output_dir, title, version,
                library, compiled_library,
                install_library, install_compiled_library,
                timeout=max(120, int(timeout_s) + 60),
            )
        finally:
            stop.set()

    def check_export_artifacts(
        self,
        output_dir: str = "",
        project_title: str = "",
        project_version: str = "",
        library: bool = True,
        compiled_library: bool = True,
    ) -> ExportArtifactsCheckResult:
        """Filesystem-only verify of expected export artifacts (no STA)."""
        self._ensure_export_progress_state()
        with self._export_lock:
            p = dict(self._export_progress)
        out = (output_dir or str(p.get("output_dir") or "")).strip()
        title = (project_title or str(p.get("project_title") or "")).strip()
        version = (
            project_version or str(p.get("project_version") or "")
        ).strip()
        if not out or not title or not version:
            return ExportArtifactsCheckResult(
                success=False,
                all_present=False,
                output_dir=out,
                project_title=title,
                project_version=version,
                message=(
                    "Need output_dir, project_title, and project_version "
                    "(or a prior export progress snapshot with those fields)."
                ),
            )
        artifacts = self._expected_export_artifacts(
            out, title, version, library, compiled_library,
        )
        all_present = bool(artifacts) and all(
            a.get("exists") and float(a.get("size_kb") or 0) > 0
            for a in artifacts
        )
        return ExportArtifactsCheckResult(
            success=True,
            all_present=all_present,
            output_dir=out,
            project_title=title,
            project_version=version,
            artifacts=artifacts,
            message=(
                "All requested export artifacts present on disk"
                if all_present
                else "One or more export artifacts missing or zero-size"
            ),
        )

    @staticmethod
    def _expected_export_artifacts(
        output_dir: str,
        title: str,
        version: str,
        library: bool,
        compiled_library: bool,
    ) -> list:
        items = []
        if library:
            path = os.path.join(output_dir, f"{title}-{version}.library")
            items.append(BuildOpsMixin._artifact_stat(path, "library"))
        if compiled_library:
            path = os.path.join(
                output_dir, f"{title}-{version}.compiled-library",
            )
            items.append(
                BuildOpsMixin._artifact_stat(path, "compiled-library"),
            )
        return items

    @staticmethod
    def _artifact_stat(path: str, kind: str) -> dict:
        exists = os.path.isfile(path)
        size_kb = 0.0
        if exists:
            try:
                size_kb = round(os.path.getsize(path) / 1024, 1)
            except OSError:
                exists = False
        return {
            "path": path,
            "kind": kind,
            "exists": exists,
            "size_kb": size_kb,
        }

    @staticmethod
    def _verify_export_file(path: str, kind: str) -> tuple[bool, float, str]:
        """Return (ok, size_kb, error_message)."""
        if not os.path.isfile(path):
            return False, 0.0, f"{kind} missing on disk: {path}"
        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return False, 0.0, f"{kind} unreadable: {path} ({exc})"
        if size <= 0:
            return False, 0.0, f"{kind} is zero-size: {path}"
        return True, round(size / 1024, 1), ""
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
        exc1_str: str | None = None
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
            exc1_str = str(exc1)
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
                    f"Interface: {exc1_str} | DTE: {exc2}"
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

        self._update_export_progress(
            phase="checking", percent=5.0,
            message="CheckAllObjects before export…",
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
            os.path.dirname(self._plcproj_file_path) if getattr(self, "_plcproj_file_path", None) else "",
            self._find_git_root(self._plcproj_file_path) if getattr(self, "_plcproj_file_path", None) else "",
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
        result = ExportResult(
            success=True,
            output_dir=output_dir,
            project_title=title,
            project_version=version,
        )
        msg_parts: list[str] = []
        steps = (1 if library else 0) + (1 if compiled_library else 0)
        done_steps = 0
        artifacts: list = []

        # --- .library ---
        if library:
            lib_path = os.path.join(output_dir, f"{title}-{version}.library")
            self._update_export_progress(
                phase="exporting_library",
                percent=20.0,
                message=f"SaveAsLibrary → {os.path.basename(lib_path)}",
            )
            try:
                self._plc_proj_item.SaveAsLibrary(lib_path, install_library)
            except Exception as exc:
                result.success = False
                result.message = f".library export failed: {exc}"
                result.artifacts = artifacts
                return result
            ok, size_kb, err = self._verify_export_file(lib_path, ".library")
            artifacts.append(self._artifact_stat(lib_path, "library"))
            if not ok:
                result.success = False
                result.library_path = lib_path
                result.artifacts = artifacts
                result.artifacts_on_disk = False
                result.message = err
                return result
            result.library_path = lib_path
            result.library_size_kb = size_kb
            label = f"{size_kb} KB .library"
            if install_library:
                label += " (installed)"
            msg_parts.append(label)
            done_steps += 1
            self._update_export_progress(
                percent=20.0 + 70.0 * (done_steps / max(1, steps)),
                message=f"Exported {label}",
            )

        # --- .compiled-library ---
        if compiled_library:
            comp_path = os.path.join(
                output_dir, f"{title}-{version}.compiled-library",
            )
            self._update_export_progress(
                phase="exporting_compiled",
                percent=20.0 + 70.0 * (done_steps / max(1, steps)),
                message=f"SaveAsLibrary → {os.path.basename(comp_path)}",
            )
            try:
                self._plc_proj_item.SaveAsLibrary(
                    comp_path, install_compiled_library,
                )
            except Exception as exc:
                result.success = False
                result.message = f".compiled-library export failed: {exc}"
                result.artifacts = artifacts
                return result
            ok, size_kb, err = self._verify_export_file(
                comp_path, ".compiled-library",
            )
            artifacts.append(
                self._artifact_stat(comp_path, "compiled-library"),
            )
            if not ok:
                result.success = False
                result.compiled_library_path = comp_path
                result.artifacts = artifacts
                result.artifacts_on_disk = False
                result.message = err
                return result
            result.compiled_library_path = comp_path
            result.compiled_library_size_kb = size_kb
            label = f"{size_kb} KB .compiled-library"
            if install_compiled_library:
                label += " (installed)"
            msg_parts.append(label)
            done_steps += 1
            self._update_export_progress(
                percent=20.0 + 70.0 * (done_steps / max(1, steps)),
                message=f"Exported {label}",
            )

        result.artifacts = artifacts
        result.artifacts_on_disk = bool(artifacts) and all(
            a.get("exists") and float(a.get("size_kb") or 0) > 0
            for a in artifacts
        )
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

