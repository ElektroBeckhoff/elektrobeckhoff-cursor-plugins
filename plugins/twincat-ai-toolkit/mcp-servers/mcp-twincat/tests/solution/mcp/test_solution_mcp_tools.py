"""Integration tests for MCP Server tools against the real TwinCAT 3 Solution."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from server import (
    twincat_plcproj_info,
    twincat_symbol_lookup,
    twincat_workspace_symbols,
    twincat_plcproj_verify,
)


class TestSolutionMcpTools:
    """Verifies that MCP tools operate accurately on the real Solution."""

    def test_mcp_plcproj_info(self, solution_paths):
        plcproj_path = str(solution_paths["plcproj_file"])
        res_str = twincat_plcproj_info(plcproj_path)
        res = json.loads(res_str)

        assert res.get("name") == "plc_project" or res.get("project_name") == "plc_project"

    def test_mcp_symbol_lookup_fb(self, solution_paths):
        plcproj_path = str(solution_paths["plcproj_file"])
        res_str = twincat_symbol_lookup("FB_Syntax_Derived", plcproj_path=plcproj_path)
        res = json.loads(res_str)

        assert res["found"] is True
        assert res["name"] == "FB_Syntax_Derived"
        assert res["kind"] == "function_block"

    def test_mcp_symbol_lookup_gvl(self, solution_paths):
        plcproj_path = str(solution_paths["plcproj_file"])
        res_str = twincat_symbol_lookup("GVL_Syntax_Global", plcproj_path=plcproj_path)
        res = json.loads(res_str)

        assert res["found"] is True
        assert res["name"] == "GVL_Syntax_Global"
        assert res["kind"] == "gvl"

    def test_mcp_workspace_symbols_query(self, solution_paths):
        plcproj_path = str(solution_paths["plcproj_file"])
        res_str = twincat_workspace_symbols("Syntax", plcproj_path=plcproj_path)
        res = json.loads(res_str)

        assert res["total"] > 0
        names = [s["name"] for s in res["symbols"]]
        assert any("FB_Syntax" in n for n in names)

    def test_mcp_plcproj_verify(self, solution_paths):
        plcproj_path = str(solution_paths["plcproj_file"])
        res_str = twincat_plcproj_verify(plcproj_path)
        res = json.loads(res_str)

        assert res["success"] is True
        assert res["exit_code"] == 0
