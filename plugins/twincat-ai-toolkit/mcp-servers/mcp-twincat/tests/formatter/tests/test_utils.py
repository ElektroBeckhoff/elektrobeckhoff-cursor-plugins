"""Tests for formatter utility functions."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.utils import (
    normalize_line_endings,
    strip_trailing_whitespace,
    compute_sha256,
    indent_lines,
    deindent_lines,
    is_blank_line,
    count_leading_spaces,
    clamp_blank_lines,
    align_at_char,
)


class TestNormalizeLineEndings:
    def test_crlf_to_lf(self):
        assert normalize_line_endings("a\r\nb") == "a\nb"

    def test_cr_to_lf(self):
        assert normalize_line_endings("a\rb") == "a\nb"

    def test_mixed(self):
        assert normalize_line_endings("a\r\nb\rc\nd") == "a\nb\nc\nd"

    def test_to_crlf(self):
        assert normalize_line_endings("a\nb", "\r\n") == "a\r\nb"


class TestStripTrailingWhitespace:
    def test_removes_trailing_spaces(self):
        assert strip_trailing_whitespace("x   \ny  ") == "x\ny"

    def test_preserves_content(self):
        assert strip_trailing_whitespace("hello") == "hello"


class TestComputeSha256:
    def test_known_hash(self):
        h = compute_sha256(b"hello")
        assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_empty(self):
        h = compute_sha256(b"")
        assert h == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class TestIndentLines:
    def test_basic_indent(self):
        result = indent_lines("a\nb", 1, 4)
        assert result == "    a\n    b"

    def test_empty_lines_not_indented(self):
        result = indent_lines("a\n\nb", 1, 4)
        assert result == "    a\n\n    b"

    def test_level_2(self):
        result = indent_lines("x", 2, 4)
        assert result == "        x"


class TestDeindentLines:
    def test_removes_common_indent(self):
        result = deindent_lines("    a\n    b")
        assert result == "a\nb"

    def test_preserves_relative(self):
        result = deindent_lines("    a\n        b")
        assert result == "a\n    b"


class TestIsBlankLine:
    def test_empty(self):
        assert is_blank_line("")
        assert is_blank_line("   ")
        assert is_blank_line("\t")

    def test_not_blank(self):
        assert not is_blank_line("x")
        assert not is_blank_line("  x")


class TestCountLeadingSpaces:
    def test_spaces(self):
        assert count_leading_spaces("    x") == 4

    def test_tab(self):
        assert count_leading_spaces("\tx") == 4

    def test_none(self):
        assert count_leading_spaces("x") == 0


class TestClampBlankLines:
    def test_clamps_to_one(self):
        result = clamp_blank_lines(["a", "", "", "", "b"])
        assert result == ["a", "", "b"]

    def test_allows_one(self):
        result = clamp_blank_lines(["a", "", "b"])
        assert result == ["a", "", "b"]


class TestAlignAtChar:
    def test_aligns_colon(self):
        lines = ["x : int", "longname : bool"]
        result = align_at_char(lines, ":")
        assert result[0].index(":") == result[1].index(":")
