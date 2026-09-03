"""Real end-to-end integration tests for TwinCAT XAE Automation Interface tools
executed directly against the real TwinCAT 3 Solution in a live TcXaeShell instance.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

from twincat_automation_interface import TcAutomationInterface, HAS_WIN32
from tools.solution import (
    twincat_status,
    twincat_open,
    twincat_check_all_objects,
    twincat_build,
    twincat_get_output_log,
    twincat_reload,
    twincat_stweep_status,
    twincat_export_check_artifacts,
    twincat_close,
)
from tools.target_io import (
    twincat_task_list,
    twincat_task_info,
    twincat_io_list,
)


def _is_xae_available() -> bool:
    if not HAS_WIN32:
        return False
    try:
        res = json.loads(twincat_status())
        return bool(res.get("xae_available", False))
    except Exception:
        return False


@pytest.mark.skipif(not _is_xae_available(), reason="TwinCAT XAE not available on this machine")
class TestSolutionXaeRealLiveWorkflow:
    """Performs full end-to-end live testing of all TwinCAT XAE MCP tools
    directly against the real TwinCAT 3 Solution.
    """

    def test_01_twincat_status_discovery(self):
        res_str = twincat_status()
        res = json.loads(res_str)

        assert res.get("xae_available") is True
        assert "instances" in res
        assert "vscode_extension" in res

    def test_02_twincat_open_solution(self, solution_paths):
        sln_file = str(solution_paths["sln_file"])
        res_str = twincat_open(path=sln_file, timeout_seconds=120)
        res = json.loads(res_str)

        assert res.get("success") is True, f"twincat_open failed: {res}"
        assert os.path.normcase(res.get("solution_path", "")) == os.path.normcase(sln_file)
        assert "plc-project" in res.get("plc_project_name", "").lower()

    def test_03_twincat_status_mcp_session(self, solution_paths):
        res_str = twincat_status()
        res = json.loads(res_str)

        assert res.get("mcp_session_active") is True
        sln_file = str(solution_paths["sln_file"])
        assert os.path.normcase(res.get("mcp_solution_path", "")) == os.path.normcase(sln_file)

    def test_04_twincat_check_all_objects(self):
        res_str = twincat_check_all_objects()
        res = json.loads(res_str)

        assert res.get("success") is True, f"CheckAllObjects failed: {res}"
        assert res.get("error_count") == 0, f"Expected 0 compiler errors in Solution, got: {res.get('errors')}"

    def test_05_twincat_build(self):
        res_str = twincat_build(timeout_seconds=90, full_rebuild=False)
        res = json.loads(res_str)

        assert res.get("success") is True, f"Build failed: {res}"
        assert res.get("error_count") == 0

    def test_06_twincat_get_output_log(self):
        res_str = twincat_get_output_log()
        res = json.loads(res_str)

        assert "infos" in res or "errors" in res or "warnings" in res
        assert "message" in res

    def test_07_twincat_task_list_and_info(self):
        res_str = twincat_task_list()
        res = json.loads(res_str)

        assert res.get("success") is True
        tasks = res.get("tasks", [])
        assert len(tasks) >= 1
        task_names = [t.get("name") for t in tasks]
        assert "PlcTask" in task_names

        info_str = twincat_task_info(task_path="PlcTask")
        info = json.loads(info_str)
        assert info.get("success") is True

    def test_08_twincat_io_list(self):
        res_str = twincat_io_list()
        res = json.loads(res_str)

        assert res.get("success") is True
        assert "devices" in res

    def test_09_twincat_stweep_status(self):
        res_str = twincat_stweep_status()
        res = json.loads(res_str)

        assert res.get("success") is True
        assert "installed" in res

    def test_10_twincat_export_check_artifacts(self, solution_paths):
        plc_dir = str(solution_paths["plc_proj_dir"])
        res_str = twincat_export_check_artifacts(
            output_dir=plc_dir,
            project_title="plc_project",
            project_version="0.1.0",
        )
        res = json.loads(res_str)

        assert "all_present" in res
        assert "artifacts" in res

    def test_11_twincat_reload(self):
        res_str = twincat_reload(timeout_seconds=90)
        res = json.loads(res_str)

        assert res.get("success") is True, f"Reload failed: {res}"

    def test_12_twincat_close_session(self):
        res_str = twincat_close(force_quit=True)
        res = json.loads(res_str)

        assert res.get("success") is True, f"Close failed: {res}"
