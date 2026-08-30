"""Syntax and CST/AST parsing tests across all real Solution files."""
from __future__ import annotations

from pathlib import Path
import pytest

from twincat_core.xml.reader import read_tc_xml_file
from twincat_core.xml.types import CdataKind
from twincat_core.syntax.parser import parse_declaration, parse_implementation


class TestSolutionSyntaxParsing:
    """Verifies that all ST code embedded in real solution XML files parses cleanly."""

    def test_parse_all_solution_declarations(self, all_solution_files):
        parsed_count = 0
        decl_kinds = (
            CdataKind.POU_DECLARATION,
            CdataKind.DUT_DECLARATION,
            CdataKind.GVL_DECLARATION,
            CdataKind.ITF_DECLARATION,
            CdataKind.METHOD_DECLARATION,
            CdataKind.PROPERTY_DECLARATION,
        )
        for file_path in all_solution_files:
            if file_path.suffix.lower() == ".tctto":
                continue
            tc_doc = read_tc_xml_file(file_path)
            decl_spans = [s for s in tc_doc.cdata_spans if s.kind in decl_kinds]
            for span in decl_spans:
                if not span.content.strip():
                    continue
                ast_node, cst_nodes, diags = parse_declaration(span.content)
                assert not diags, f"Unexpected declaration diagnostics in {file_path.name}: {diags}"
                assert ast_node is not None or len(cst_nodes) > 0, f"Failed to parse declaration in {file_path.name}"
                parsed_count += 1

        assert parsed_count >= 50

    def test_parse_all_solution_implementations(self, all_solution_files):
        impl_count = 0
        impl_kinds = (
            CdataKind.POU_IMPLEMENTATION,
            CdataKind.METHOD_IMPLEMENTATION,
            CdataKind.ACTION_IMPLEMENTATION,
            CdataKind.PROPERTY_GET_IMPLEMENTATION,
            CdataKind.PROPERTY_SET_IMPLEMENTATION,
        )
        for file_path in all_solution_files:
            if file_path.suffix.lower() == ".tctto":
                continue
            tc_doc = read_tc_xml_file(file_path)
            impl_spans = [s for s in tc_doc.cdata_spans if s.kind in impl_kinds]
            for span in impl_spans:
                if not span.content.strip():
                    continue
                stmts, cst_nodes, diags = parse_implementation(span.content)
                assert not diags, f"Unexpected implementation diagnostics in {file_path.name}: {diags}"
                assert isinstance(stmts, list), f"Expected list of statements in {file_path.name}"
                impl_count += 1

        assert impl_count >= 20

    def test_parse_all_formatter_fixtures_zero_diagnostics(self):
        """Verifies that all 300+ formatter fixture files parse with zero false positive diagnostics."""
        fixture_dir = Path(__file__).resolve().parents[2] / "formatter" / "fixtures"
        fixture_files = [f for f in fixture_dir.rglob("*") if f.suffix.lower() in (".tcpou", ".tcdut", ".tcgvl", ".tcio")]
        assert len(fixture_files) >= 100, f"Expected at least 100 fixture files, found {len(fixture_files)} at {fixture_dir}"

        for f in fixture_files:
            tc_doc = read_tc_xml_file(f)
            for span in tc_doc.cdata_spans:
                if not span.content.strip():
                    continue
                if span.is_declaration:
                    ast_node, cst_nodes, diags = parse_declaration(span.content)
                    assert not diags, f"Unexpected declaration diagnostics in fixture {f.name}: {diags}"
                elif span.is_implementation:
                    stmts, cst_nodes, diags = parse_implementation(span.content)
                    assert not diags, f"Unexpected implementation diagnostics in fixture {f.name}: {diags}"
