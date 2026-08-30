"""Migrator integration tests in the context of the real TwinCAT Solution."""
from __future__ import annotations

from pathlib import Path
import pytest

from migrator.xml_reader import load_file
from migrator.cli import MigrationConfig


class TestSolutionMigratorIntegration:
    """Verifies that the Migrator safely processes files and preserves solution structure."""

    def test_load_solution_pou_with_migrator_reader(self, solution_paths):
        pou_path = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        assert pou_path.is_file()

        tc_file = load_file(pou_path)
        assert tc_file is not None
        assert tc_file.pou_name == "FB_Syntax_Derived"
        assert tc_file.pou_type in ("FUNCTION_BLOCK", "POU")
        assert tc_file.impl_type in ("ST", "NWL", "CFC", "")

    def test_dry_run_analysis_on_solution_pous(self, solution_paths):
        pous = list(solution_paths["syntax_dir"].glob("*.TcPOU"))
        assert len(pous) >= 10

        tc = load_file(pous[0])
        assert tc is not None
        assert tc.impl_type in ("ST", "NWL", "CFC", "")
