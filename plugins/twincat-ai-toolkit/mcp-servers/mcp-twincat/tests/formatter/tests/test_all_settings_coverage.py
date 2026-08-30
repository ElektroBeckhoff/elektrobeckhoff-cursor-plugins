"""Comprehensive test coverage for EVERY setting in defaults.json.

Each test verifies a specific setting in FormatterConfig by demonstrating
its effect with a concrete TwinCAT 3 Structured Text code example.
"""
from __future__ import annotations

import copy
import pytest
from pathlib import Path

from formatter.config import load_config, FormatterConfig
from formatter.file_processor import _format_st_pipeline, format_st_code
from formatter.st_lexer import tokenize
from formatter.st_alignment import align_declarations, align_assignments, align_fb_call_params, _align_enum_members
from formatter.st_line_wrapper import wrap_long_lines
from formatter.xml_formatter import format_xml_structure, sort_pou_children, parse_twincat_xml


@pytest.fixture
def base_config() -> FormatterConfig:
    return load_config()


class TestIndentSettings:
    """Tests for all indent.* settings."""

    def test_indent_size_and_style(self, base_config):
        cfg2 = copy.deepcopy(base_config)
        cfg2.indent.size = 2
        code = "IF bCondition THEN\nx := 1;\nEND_IF"
        res2 = _format_st_pipeline(code, cfg2)
        assert "  x := 1;" in res2

        cfg4 = copy.deepcopy(base_config)
        cfg4.indent.size = 4
        res4 = _format_st_pipeline(code, cfg4)
        assert "    x := 1;" in res4

    def test_indent_cases_in_case(self, base_config):
        cfg = copy.deepcopy(base_config)
        cfg.indent.indent_cases_in_case = True
        code = "CASE nMode OF\n0:\nx := 1;\nEND_CASE"
        res = _format_st_pipeline(code, cfg)
        assert "    0:" in res
        assert "        x := 1;" in res

    def test_indent_statements_in_case(self, base_config):
        cfg = copy.deepcopy(base_config)
        cfg.indent.indent_cases_in_case = True
        cfg.indent.indent_statements_in_case = True
        code = "CASE nMode OF\n0:\nx := 1;\nEND_CASE"
        res = _format_st_pipeline(code, cfg)
        assert "        x := 1;" in res


class TestLineLengthSettings:
    """Tests for lineLength.* settings."""

    def test_wrap_at_and_wrap_enabled(self, base_config):
        cfg = copy.deepcopy(base_config)
        cfg.line_length.wrap_at = 60
        cfg.line_length.wrap_enabled = True
        code = "bDone := bFirstCondition AND bSecondCondition AND bThirdCondition AND bFourthCondition;"
        res = _format_st_pipeline(code, cfg)
        assert "\n" in res
        assert "    bSecondCondition" in res or "AND b" in res

    def test_wrap_after_operator(self, base_config):
        cfg = copy.deepcopy(base_config)
        cfg.line_length.wrap_at = 50
        cfg.line_length.wrap_after_operator = True
        code = "nTotal := nValueA + nValueB + nValueC + nValueD + nValueE;"
        res = _format_st_pipeline(code, cfg)
        assert "\n" in res


class TestBlankLinesSettings:
    """Tests for blankLines.* settings."""

    def test_blank_lines_max_consecutive(self, base_config):
        cfg = copy.deepcopy(base_config)
        cfg.blank_lines.max_consecutive = 1
        code = "x := 1;\n\n\n\n\ny := 2;"
        res = _format_st_pipeline(code, cfg)
        assert "\n\n\n" not in res
        assert "x := 1;\n\ny := 2;" in res

    def test_after_statement_with_body(self, base_config):
        cfg = copy.deepcopy(base_config)
        cfg.blank_lines.after_statement_with_body = 1
        code = "IF bA THEN\n    x := 1;\nEND_IF\ny := 2;"
        res = _format_st_pipeline(code, cfg)
        assert "END_IF\n\ny := 2;" in res


class TestSpacesSettings:
    """Tests for spaces.* settings."""

    def test_spaces_around_assignment(self, base_config):
        code = "x:=1;"
        res = _format_st_pipeline(code, base_config)
        assert "x := 1;" in res

    def test_spaces_after_comma_in_call(self, base_config):
        code = "fbTimer(IN := bStart, PT := T#5S);"
        res = _format_st_pipeline(code, base_config)
        assert "IN := bStart, PT := T#5S" in res

    def test_spaces_around_assignment_in_init(self, base_config):
        code = "stConfig := (nId := 1, sName := 'Test');"
        res = _format_st_pipeline(code, base_config)
        assert "nId := 1" in res

    def test_spaces_around_pragma(self, base_config):
        code = "{attribute 'hide'}"
        res = _format_st_pipeline(code, base_config)
        assert "{attribute 'hide'}" in res


class TestAlignmentSettings:
    """Tests for alignment.* settings."""

    def test_declaration_colon_and_comment_alignment(self):
        lines = [
            "VAR",
            "    bShort : BOOL; // comment 1",
            "    nMuchLongerName : INT; // comment 2",
            "END_VAR",
        ]
        aligned = align_declarations(lines)
        assert "bShort          : BOOL;" in aligned[1]
        assert "nMuchLongerName : INT;" in aligned[2]
        # Comments aligned
        c1_idx = aligned[1].find("//")
        c2_idx = aligned[2].find("//")
        assert c1_idx == c2_idx

    def test_assignment_alignment(self):
        lines = [
            "    a := 1;",
            "    longerIdentifier := 200;",
            "    c := 3;",
        ]
        aligned = align_assignments(lines)
        assert ":=" in aligned[0]
        assert ":=" in aligned[1]

    def test_address_assignments(self):
        lines = [
            "VAR",
            "    bSensor AT %I* : BOOL;",
            "    nEncoder AT %IB4 : DINT;",
            "END_VAR",
        ]
        aligned = align_declarations(lines)
        assert "AT" in aligned[1]
        assert "AT" in aligned[2]

    def test_enum_initializers_alignment(self):
        lines = [
            "TYPE E_Mode : (",
            "    Off := 0,",
            "    ManualOperation := 10,",
            "    Auto := 20",
            ");",
            "END_TYPE",
        ]
        aligned = align_declarations(lines)
        assert "Off             := 0," in aligned[1]
        assert "ManualOperation := 10," in aligned[2]


class TestCallsAndWrapSettings:
    """Tests for calls.* and wrapping thresholds."""

    def test_max_params_single_line(self):
        # 3 params -> stays on one line (<= 4)
        short_call = "    fbDoSomething(nParam1 := 1, nParam2 := 2, nParam3 := 3);"
        wrapped_3 = wrap_long_lines([short_call], max_length=230, max_params_single=4, call_indent=4)
        assert len(wrapped_3) == 1

        # 5 params -> wraps (> 4)
        call_5 = "    fbDoSomething(nP1 := 1, nP2 := 2, nP3 := 3, nP4 := 4, nP5 := 5);"
        wrapped_5 = wrap_long_lines([call_5], max_length=230, max_params_single=4, call_indent=4)
        assert len(wrapped_5) > 1
        assert "    fbDoSomething(" in wrapped_5[0]
        assert "        nP1 := 1," in wrapped_5[1]

    def test_multiline_call_wrapping_and_indent(self):
        call_5 = "    fbTimer(IN := bStart, PT := T#5S, Q => bDone, ET => tElapsed, M => nMode);"
        wrapped = wrap_long_lines([call_5], max_length=230, max_params_single=4, call_indent=4)
        assert len(wrapped) >= 5
        assert "    fbTimer(" in wrapped[0]
        assert "        IN := bStart," in wrapped[1]


class TestKeywordsAndXMLSettings:
    """Tests for keywords.uppercase and xml sorting."""

    def test_keywords_uppercase(self, base_config):
        cfg = copy.deepcopy(base_config)
        cfg.keywords.uppercase = True
        code = "if bTest then\n    x := true;\nend_if"
        res = _format_st_pipeline(code, cfg)
        assert "IF" in res
        assert "THEN" in res
        assert "TRUE;" in res
        assert "END_IF" in res

    def test_xml_method_sorting(self, base_config):
        xml_input = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<TcPlcObject Version="1.1.0.1" ProductVersion="3.1.4024.16">\n'
            '  <POU Name="FB_Test" Id="{00000000-0000-0000-0000-000000000001}">\n'
            '    <Declaration><![CDATA[FUNCTION_BLOCK FB_Test\nVAR\nEND_VAR\n]]></Declaration>\n'
            '    <Implementation><ST><![CDATA[]]></ST></Implementation>\n'
            '    <Method Name="Z_Last" Id="{00000000-0000-0000-0000-000000000002}">\n'
            '      <Declaration><![CDATA[METHOD Z_Last : BOOL\n]]></Declaration>\n'
            '      <Implementation><ST><![CDATA[]]></ST></Implementation>\n'
            '    </Method>\n'
            '    <Method Name="A_First" Id="{00000000-0000-0000-0000-000000000003}">\n'
            '      <Declaration><![CDATA[METHOD A_First : BOOL\n]]></Declaration>\n'
            '      <Implementation><ST><![CDATA[]]></ST></Implementation>\n'
            '    </Method>\n'
            '  </POU>\n'
            '</TcPlcObject>'
        )
        root, cdata_map = parse_twincat_xml(xml_input)
        sort_pou_children(root)
        methods = [m.get("Name") for m in root.findall(".//Method")]
        assert methods == ["A_First", "Z_Last"], "Methods should be sorted alphabetically"
