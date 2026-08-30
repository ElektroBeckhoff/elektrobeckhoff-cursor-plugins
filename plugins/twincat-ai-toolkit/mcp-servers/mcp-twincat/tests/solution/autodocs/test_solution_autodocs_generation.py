"""AutoDocs generation integration tests against real Solution files."""
from __future__ import annotations

import tempfile
from pathlib import Path
import json
import pytest

from server import twincat_autodocs
from autodocs.parsers.pou import parse_tcPou
from autodocs.type_index import build_type_index


class TestSolutionAutoDocsGeneration:
    """Verifies that AutoDocs generates accurate documentation from real solution files."""

    def test_parse_solution_pou(self, solution_paths):
        pou_file = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        type_idx = {}
        res = parse_tcPou(pou_file, type_index=type_idx, docs_root=solution_paths["syntax_dir"])
        assert res is not None
        assert res["title"] == "FB_Syntax_Derived"
        assert "sections" in res

    def test_build_type_index_on_solution(self, solution_paths):
        idx = build_type_index(solution_paths["syntax_dir"])
        assert len(idx) > 0
        assert "fb_syntax_derived" in idx or "st_syntax_mini" in idx

    def test_autodocs_pipeline_on_solution_syntax_folder(self, solution_paths):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_root = Path(tmp_dir)
            res_str = twincat_autodocs(
                input=str(solution_paths["syntax_dir"]),
                output=str(out_root),
                write_log=False,
            )
            res = json.loads(res_str)
            assert res["success"] is True
            assert len(res["files_created"]) > 0
            docs_dir = out_root / "docs"
            assert docs_dir.is_dir()
            md_files = list(docs_dir.glob("*.md"))
            assert len(md_files) > 0
