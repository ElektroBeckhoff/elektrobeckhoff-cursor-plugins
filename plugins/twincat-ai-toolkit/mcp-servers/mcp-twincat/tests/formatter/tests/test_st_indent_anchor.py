"""Unit tests for column-anchor indent engine."""
from __future__ import annotations

from formatter.config import IndentConfig
from formatter.st_indent_anchor import apply_column_anchor_indentation

CFG = IndentConfig()


class TestIfEndIfAnchor:
    def test_end_if_at_if_column(self):
        lines = [
            "IF NOT bInit THEN",
            "    bInit := TRUE;",
            "END_IF",
        ]
        out, _ = apply_column_anchor_indentation(lines, CFG, force_all=True)
        assert out[0] == "IF NOT bInit THEN"
        assert out[1] == "    bInit := TRUE;"
        assert out[2] == "END_IF"

    def test_nested_if_elsif(self):
        lines = [
            "IF NOT bRef THEN",
            "    IF (fTargPos < fActlPos) THEN",
            "        nStep := 100;",
            "    ELSIF (fTargPos > fActlPos) THEN",
            "        nStep := 200;",
            "    END_IF",
            "END_IF",
        ]
        out, _ = apply_column_anchor_indentation(lines, CFG, force_all=True)
        assert out[2].startswith("        nStep")
        assert out[3].startswith("    ELSIF")
        assert out[5].startswith("    END_IF")
        assert out[6] == "END_IF"


class TestCaseAnchor:
    def test_case_label_and_statement_cols(self):
        lines = [
            "CASE nStep OF",
            "",
            "    0:",
            "        A_Init();",
            "END_CASE",
        ]
        out, _ = apply_column_anchor_indentation(lines, CFG, force_all=True)
        assert out[2] == "    0:"
        assert out[3] == "        A_Init();"
        assert out[4] == "END_CASE"


class TestPreserveRaw:
    def test_identity_on_golden_indent(self):
        lines = [
            "        IF fActlPos <= fTargPos_Int THEN",
            "            nStep := 0;",
            "        END_IF",
        ]
        out, _ = apply_column_anchor_indentation(lines, CFG)
        assert out == lines

    def test_bool_continuation_preserved(self):
        lines = [
            "_b := a AND_THEN",
            "    b AND_THEN",
            "    c;",
        ]
        out, _ = apply_column_anchor_indentation(lines, CFG)
        assert out == lines
