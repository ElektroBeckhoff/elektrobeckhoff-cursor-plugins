"""Tests for formatter constants module."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.constants import (
    ST_KEYWORDS,
    INDENT_OPENERS,
    INDENT_CLOSERS,
    FORMATTABLE_EXTENSIONS,
    TokenType,
    SCANNER_PATTERN,
    SCANNER_TOKEN_MAP,
    XML_ATTRIBUTE_ORDER,
    XML_POU_CHILD_ORDER,
    VAR_BLOCK_KEYWORDS,
    BINARY_OPERATORS,
)


class TestSTKeywords:
    def test_keywords_are_uppercase(self):
        for kw in ST_KEYWORDS:
            assert kw == kw.upper(), f"Keyword {kw!r} not uppercase"

    def test_contains_common_keywords(self):
        common = {"IF", "THEN", "ELSE", "END_IF", "VAR", "END_VAR", "FOR", "WHILE"}
        assert common.issubset(ST_KEYWORDS)

    def test_contains_twincat_extensions(self):
        assert "AND_THEN" in ST_KEYWORDS
        assert "OR_ELSE" in ST_KEYWORDS
        assert "__NEW" in ST_KEYWORDS
        assert "__DELETE" in ST_KEYWORDS

    def test_frozenset_type(self):
        assert isinstance(ST_KEYWORDS, frozenset)


class TestTokenType:
    def test_all_types_defined(self):
        assert TokenType.KEYWORD == 0
        assert TokenType.EOF == 22
        assert len(TokenType) == 24

    def test_is_intenum(self):
        assert int(TokenType.KEYWORD) == 0


class TestFormattableExtensions:
    def test_contains_all_twincat_extensions(self):
        assert ".tcpou" in FORMATTABLE_EXTENSIONS
        assert ".tcdut" in FORMATTABLE_EXTENSIONS
        assert ".tcgvl" in FORMATTABLE_EXTENSIONS
        assert ".tcio" in FORMATTABLE_EXTENSIONS

    def test_extensions_are_lowercase(self):
        for ext in FORMATTABLE_EXTENSIONS:
            assert ext == ext.lower()
            assert ext.startswith(".")


class TestXmlConstants:
    def test_pou_child_order(self):
        assert XML_POU_CHILD_ORDER[0] == "Declaration"
        assert XML_POU_CHILD_ORDER[1] == "Implementation"
        assert "Method" in XML_POU_CHILD_ORDER
        assert "Property" in XML_POU_CHILD_ORDER

    def test_attribute_order_has_required_tags(self):
        assert "TcPlcObject" in XML_ATTRIBUTE_ORDER
        assert "POU" in XML_ATTRIBUTE_ORDER
        assert "DUT" in XML_ATTRIBUTE_ORDER
        assert "GVL" in XML_ATTRIBUTE_ORDER
        assert "Itf" in XML_ATTRIBUTE_ORDER

    def test_pou_attribute_order(self):
        order = XML_ATTRIBUTE_ORDER["POU"]
        assert order[0] == "Name"
        assert order[1] == "Id"


class TestScannerPattern:
    def test_scanner_compiles(self):
        assert SCANNER_PATTERN is not None

    def test_scanner_map_matches_patterns(self):
        for key in SCANNER_TOKEN_MAP:
            assert key.startswith("T")
