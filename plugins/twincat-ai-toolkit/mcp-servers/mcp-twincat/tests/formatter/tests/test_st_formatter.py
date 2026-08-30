"""Tests for the ST Formatter core engine."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.st_formatter import format_st_code


class TestKeywordCasing:
    def test_uppercase_keywords(self):
        result = format_st_code("if x then\n    y := 1;\nend_if")
        assert "IF" in result
        assert "THEN" in result
        assert "END_IF" in result

    def test_preserves_identifiers(self):
        result = format_st_code("IF myVar THEN\n    nCount := 1;\nEND_IF")
        assert "myVar" in result
        assert "nCount" in result

    def test_preserves_strings(self):
        result = format_st_code("sName := 'if then else';")
        assert "'if then else'" in result

    def test_preserves_comments(self):
        result = format_st_code("(* if then else *)\nIF x THEN\nEND_IF")
        assert "(* if then else *)" in result


class TestIndentation:
    """Full structural reindent via apply_column_anchor_indentation(force_all=True)."""

    def _reindent(self, code: str) -> list[str]:
        from formatter.config import IndentConfig
        from formatter.st_indent_anchor import apply_column_anchor_indentation

        lines, _ = apply_column_anchor_indentation(
            code.split("\n"), IndentConfig(), force_all=True,
        )
        return lines

    def test_if_then(self):
        lines = self._reindent("IF x THEN\ny := 1;\nEND_IF")
        assert lines[0] == "IF x THEN"
        assert lines[1] == "    y := 1;"
        assert lines[2] == "END_IF"

    def test_for_do(self):
        lines = self._reindent("FOR i := 0 TO 10 DO\nx := i;\nEND_FOR")
        assert lines[1].startswith("    ")
        assert lines[2] == "END_FOR"
        assert not lines[2].startswith(" ")

    def test_var_block(self):
        lines = self._reindent("VAR\nx : INT;\ny : BOOL;\nEND_VAR")
        assert lines[0] == "VAR"
        assert lines[1].startswith("    ")
        assert lines[2].startswith("    ")
        assert lines[3] == "END_VAR"

    def test_case_statement(self):
        lines = self._reindent("CASE nState OF\n0:\nx := 1;\n1:\ny := 2;\nEND_CASE")
        assert lines[0] == "CASE nState OF"
        assert "END_CASE" in lines

    def test_nested_if(self):
        lines = self._reindent("IF a THEN\nIF b THEN\nx := 1;\nEND_IF\nEND_IF")
        assert lines[0] == "IF a THEN"
        assert lines[1] == "    IF b THEN"
        assert lines[2] == "        x := 1;"
        assert lines[3] == "    END_IF"
        assert lines[4] == "END_IF"

    def test_elsif(self):
        lines = self._reindent(
            "IF a THEN\nx := 1;\nELSIF b THEN\nx := 2;\nELSE\nx := 3;\nEND_IF"
        )
        assert lines[2] == "ELSIF b THEN"
        assert lines[3] == "    x := 2;"
        assert lines[4] == "ELSE"
        assert lines[5] == "    x := 3;"

    def test_type_struct(self):
        lines = self._reindent(
            "TYPE ST_Test :\nSTRUCT\nfield1 : INT;\nfield2 : BOOL;\nEND_STRUCT\nEND_TYPE"
        )
        assert lines[0] == "TYPE ST_Test :"
        assert lines[1] == "    STRUCT"
        assert lines[2] == "        field1 : INT;"
        assert lines[3] == "        field2 : BOOL;"
        assert lines[4] == "    END_STRUCT"
        assert lines[5] == "END_TYPE"


class TestBlankLines:
    def test_max_one_blank(self):
        code = "x := 1;\n\n\n\ny := 2;"
        result = format_st_code(code)
        assert "\n\n\n" not in result

    def test_no_leading_trailing_blanks(self):
        code = "\n\nIF x THEN\nEND_IF\n\n"
        result = format_st_code(code)
        assert not result.startswith("\n")


class TestWhitespace:
    def test_no_trailing_whitespace(self):
        code = "x := 1;   \ny := 2;  "
        result = format_st_code(code)
        for line in result.split("\n"):
            assert line == line.rstrip()


class TestFixEndIfIndentSafe:
    def test_dedents_over_indented_end_if_outside_case(self):
        from formatter.st_formatter import fix_end_if_indent_safe

        lines = [
            "IF b THEN",
            "    x := 1;",
            "    END_IF",
        ]
        result = fix_end_if_indent_safe(lines, 4)
        assert result[-1] == "END_IF"

    def test_preserves_case_block_end_if_indent(self):
        from formatter.st_formatter import fix_end_if_indent_safe

        lines = [
            "CASE n OF",
            "    1:",
            "        IF x THEN",
            "            y := 1;",
            "        END_IF",
            "END_CASE",
        ]
        result = fix_end_if_indent_safe(lines, 4)
        assert result[4] == "        END_IF"

    def test_rebuilt_end_if_uses_structural_indent(self):
        from formatter.st_formatter import fix_end_if_indent_safe

        lines = ["IF x THEN", "    y := 1;", "    END_IF"]
        rebuilt = [False, True, True]
        result = fix_end_if_indent_safe(lines, 4, rebuilt=rebuilt)
        assert result[-1] == "END_IF"
