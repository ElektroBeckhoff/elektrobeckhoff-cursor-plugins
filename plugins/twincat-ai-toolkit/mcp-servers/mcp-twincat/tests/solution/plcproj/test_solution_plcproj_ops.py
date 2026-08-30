"""PlcProject model and PLCProj-Ops integration tests against the real Solution."""
from __future__ import annotations

from pathlib import Path
import pytest

from twincat_core.project.plcproj_parser import parse_plcproj_file
from plcproj.twincat_plcproj_ops import verify_plcproj, sync_plcproj, PlcProjConfig, read_project_info


class TestSolutionPlcProjOps:
    """Verifies that .plcproj operations work reliably with the real TwinCAT 3 Solution."""

    def test_parse_solution_plcproj_metadata(self, solution_paths):
        plcproj_path = solution_paths["plcproj_file"]
        project = parse_plcproj_file(plcproj_path)

        assert project.project_name == "plc_project"
        assert len(project.compile_items) >= 50
        assert len(project.folders) >= 2

        folder_paths = list(project.folders.keys())
        assert "syntax" in folder_paths
        assert "samples" in folder_paths

        # Verify referenced standard libraries
        lib_names = [lib.name for lib in project.library_references]
        assert any("Tc2_Standard" in name for name in lib_names)
        assert any("Tc2_System" in name for name in lib_names)
        assert any("Tc3_Module" in name for name in lib_names)

    def test_verify_plcproj_integrity_on_solution(self, solution_paths):
        plcproj_path = solution_paths["plcproj_file"]
        res = verify_plcproj(plcproj_path)

        assert res.ok is True
        assert len(res.missing_compile) == 0

    def test_sync_plcproj_dry_run_on_solution(self, solution_paths):
        plcproj_path = str(solution_paths["plcproj_file"])
        cfg = PlcProjConfig(input_path=plcproj_path, dry_run=True, force=True, backup=False)
        sync_res = sync_plcproj(cfg)

        assert sync_res.success is True
        assert sync_res.compile_count >= 50

    def test_read_project_info(self, solution_paths):
        plcproj_path = str(solution_paths["plcproj_file"])
        info = read_project_info(plcproj_path)
        assert info["name"] == "plc_project"
        assert info["version"] is not None
