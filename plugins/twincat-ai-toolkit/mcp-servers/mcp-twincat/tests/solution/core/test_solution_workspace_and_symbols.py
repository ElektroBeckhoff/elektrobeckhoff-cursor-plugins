"""Multi-level Symbol Resolution and WorkspaceIndex tests on the real Solution."""
from __future__ import annotations

from pathlib import Path
import pytest

from twincat_core.semantic.symbols import SymbolKind


class TestSolutionWorkspaceAndSymbols:
    """Verifies symbol indexation and multi-level resolution on the real solution."""

    def test_workspace_indexes_all_solution_files(self, solution_workspace):
        indexed_files = list(solution_workspace.indexed_files.keys())
        assert len(indexed_files) >= 50

        file_names = [p.name for p in indexed_files]
        assert "FB_Syntax_AbstractBase.TcPOU" in file_names
        assert "FB_Syntax_Derived.TcPOU" in file_names
        assert "GVL_Syntax_Global.TcGVL" in file_names
        assert "ST_Syntax_Mini.TcDUT" in file_names
        assert "I_Syntax_BaseDevice.TcIO" in file_names

    def test_resolve_gvl_and_global_symbols(self, solution_workspace):
        res = solution_workspace.lookup_symbol("GVL_Syntax_Global")
        assert res is not None
        assert res.name == "GVL_Syntax_Global"
        assert res.kind == SymbolKind.GVL

    def test_resolve_pou_and_methods(self, solution_workspace):
        res_fb = solution_workspace.lookup_symbol("FB_Syntax_Derived")
        assert res_fb is not None
        assert res_fb.kind == SymbolKind.FUNCTION_BLOCK

        res_m = solution_workspace.lookup_symbol("M_Execute", scope_pou="FB_Syntax_Derived")
        assert res_m is not None
        assert res_m.kind == SymbolKind.METHOD

    def test_resolve_standard_library_symbols_in_solution(self, solution_workspace):
        res_ton = solution_workspace.lookup_symbol("TON")
        assert res_ton is not None
        assert res_ton.kind == SymbolKind.FUNCTION_BLOCK

        res_rtrig = solution_workspace.lookup_symbol("R_TRIG")
        assert res_rtrig is not None
        assert res_rtrig.kind == SymbolKind.FUNCTION_BLOCK

        res_f_concat = solution_workspace.lookup_symbol("CONCAT")
        assert res_f_concat is not None
        assert res_f_concat.kind == SymbolKind.FUNCTION

    def test_chained_member_resolution(self, solution_workspace):
        res_member = solution_workspace.resolver.resolve_member_access(
            target_type_name="ST_Syntax_Mini",
            member_name="nId",
        )
        assert res_member is not None
        assert res_member.name == "nId"
