"""Integration tests for TwinCAT Automation Interface against the real Solution."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from twincat_automation_interface import TcAutomationInterface
from tools.common import (
    _auto_detect_plcproj,
    _resolve_plcproj_path,
    _resolve_path,
    _read_plcproj_meta,
)
from tools.solution import (
    twincat_status,
    twincat_open,
)
from tools.core_syntax import twincat_check_syntax
from automation_interface.stweep_ops import StweepOpsMixin


class TestSolutionAutomationInterface:
    """Verifies that Automation Interface path resolution, session operations,
    and diagnostics operate 100% accurately against the real Solution.
    """

    def test_auto_detect_plcproj_on_real_solution(self, solution_paths):
        sln_file = str(solution_paths["sln_file"])
        expected_plcproj = str(solution_paths["plcproj_file"])

        detected = _auto_detect_plcproj(sln_file)
        assert os.path.normcase(detected) == os.path.normcase(expected_plcproj)

    def test_resolve_plcproj_path_from_sln_on_real_solution(self, solution_paths):
        sln_file = str(solution_paths["sln_file"])
        expected_plcproj = str(solution_paths["plcproj_file"])

        resolved = _resolve_plcproj_path(sln_path=sln_file)
        assert os.path.normcase(resolved) == os.path.normcase(expected_plcproj)

    def test_resolve_plcproj_path_basename_match(self, solution_paths):
        sln_file = str(solution_paths["sln_file"])
        expected_plcproj = str(solution_paths["plcproj_file"])

        # Resolve using bare name "plc-project"
        resolved = _resolve_plcproj_path(plcproj_path="plc-project", sln_path=sln_file)
        assert os.path.normcase(resolved) == os.path.normcase(expected_plcproj)

    def test_resolve_path_on_real_solution(self, solution_paths):
        sln_file = str(solution_paths["sln_file"])
        expected_plcproj = str(solution_paths["plcproj_file"])

        res = _resolve_path(sln_file)
        assert isinstance(res, str)
        assert os.path.normcase(res) == os.path.normcase(expected_plcproj)

    def test_read_plcproj_metadata_from_real_solution(self, solution_paths):
        plcproj_file = str(solution_paths["plcproj_file"])
        meta = _read_plcproj_meta(plcproj_file)

        assert meta.get("name") == "plc_project"
        assert meta.get("version") is not None
        assert "is_library_project" in meta

    def test_stweep_collect_formattable_files_on_real_solution(self, solution_paths):
        plc_dir = str(solution_paths["plc_proj_dir"])
        files = StweepOpsMixin._collect_formattable_files(plc_dir, recursive=True)

        assert len(files) >= 50
        exts = {os.path.splitext(f)[1].lower() for f in files}
        assert ".tcpou" in exts
        assert ".tcdut" in exts
        assert ".tcgvl" in exts
        assert ".tcio" in exts

    def test_twincat_status_diagnostics(self):
        res_str = twincat_status()
        res = json.loads(res_str)

        assert "xae_available" in res
        assert "running_instance" in res
        assert "instances" in res
        assert "mcp_session_active" in res

    def test_twincat_check_syntax_on_solution_project(self, solution_paths):
        plcproj_file = str(solution_paths["plcproj_file"])
        res_str = twincat_check_syntax(path=plcproj_file)
        res = json.loads(res_str)

        assert res.get("success") is True
        assert res.get("total_files") >= 50

    def test_twincat_check_syntax_on_single_solution_file(self, solution_paths):
        syntax_pou = solution_paths["syntax_dir"] / "FB_Syntax_ControlFlow.TcPOU"
        res_str = twincat_check_syntax(path=str(syntax_pou))
        res = json.loads(res_str)

        assert res.get("success") is True
        assert res.get("total_files") == 1
        assert res.get("error_count") == 0

    def test_session_ops_detect_plcproj_and_sln_paths(self, solution_paths):
        with patch.object(TcAutomationInterface, "__init__", lambda self: None):
            bridge = TcAutomationInterface.__new__(TcAutomationInterface)

        sln_file = str(solution_paths["sln_file"])
        expected_plcproj = str(solution_paths["plcproj_file"])

        bridge._sln_path = sln_file
        bridge._plc_proj_item = None
        bridge._instances = {}

        detected_plc = bridge._detect_plcproj_path()
        assert detected_plc is not None
        assert os.path.normcase(detected_plc) == os.path.normcase(expected_plcproj)

    def test_twincat_open_tool_on_real_solution(self, solution_paths):
        sln_file = str(solution_paths["sln_file"])
        expected_plcproj = str(solution_paths["plcproj_file"])

        mock_bridge = MagicMock()
        mock_bridge.open_solution.return_value = {
            "success": True,
            "opened": True,
            "sln_path": sln_file,
            "plcproj_path": expected_plcproj,
        }

        with patch("tools.solution._get_bridge", return_value=mock_bridge):
            res_str = twincat_open(path=sln_file)
            res = json.loads(res_str)

            assert res.get("success") is True
            mock_bridge.open_solution.assert_called_once()
            call_kwargs = mock_bridge.open_solution.call_args.kwargs
            assert os.path.normcase(call_kwargs["sln_path"]) == os.path.normcase(sln_file)
            assert os.path.normcase(call_kwargs["plcproj_path"]) == os.path.normcase(expected_plcproj)
