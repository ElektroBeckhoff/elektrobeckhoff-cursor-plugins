"""Tests for the ST Lexer."""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.st_lexer import tokenize, tokenize_to_list, tokens_without_whitespace
from formatter.constants import TokenType


class TestBasicTokenization:
    def test_keyword_recognition(self):
        tokens = tokens_without_whitespace("IF x THEN")
        assert tokens[0].type == TokenType.KEYWORD
        assert tokens[0].value == "IF"
        assert tokens[2].type == TokenType.KEYWORD
        assert tokens[2].value == "THEN"

    def test_case_insensitive_keywords(self):
        tokens = tokens_without_whitespace("if Then end_if")
        assert tokens[0].value == "IF"
        assert tokens[1].value == "THEN"
        assert tokens[2].value == "END_IF"

    def test_identifier(self):
        tokens = tokens_without_whitespace("myVar")
        assert tokens[0].type == TokenType.IDENTIFIER
        assert tokens[0].value == "myVar"

    def test_number_integer(self):
        tokens = tokens_without_whitespace("42")
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "42"

    def test_number_hex(self):
        tokens = tokens_without_whitespace("16#FF")
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "16#FF"

    def test_number_real(self):
        tokens = tokens_without_whitespace("3.14")
        assert tokens[0].type == TokenType.NUMBER
        assert tokens[0].value == "3.14"

    def test_string_literal(self):
        tokens = tokens_without_whitespace("'hello'")
        assert tokens[0].type == TokenType.STRING
        assert tokens[0].value == "'hello'"

    def test_assign_operator(self):
        tokens = tokens_without_whitespace("x := 5")
        assert tokens[1].type == TokenType.ASSIGN
        assert tokens[1].value == ":="

    def test_output_assign(self):
        tokens = tokens_without_whitespace("y => z")
        assert tokens[1].type == TokenType.OUTPUT_ASSIGN
        assert tokens[1].value == "=>"

    def test_semicolon(self):
        tokens = tokens_without_whitespace("x;")
        assert tokens[1].type == TokenType.SEMICOLON

    def test_colon(self):
        tokens = tokens_without_whitespace("x : INT")
        assert tokens[1].type == TokenType.COLON


class TestComments:
    def test_line_comment(self):
        tokens = tokenize_to_list("x := 5; // comment\ny := 6;")
        comment_tokens = [t for t in tokens if t.type == TokenType.COMMENT_LINE]
        assert len(comment_tokens) == 1
        assert "comment" in comment_tokens[0].value

    def test_block_comment(self):
        tokens = tokenize_to_list("x := (* hello *) 5;")
        comment_tokens = [t for t in tokens if t.type == TokenType.COMMENT_BLOCK]
        assert len(comment_tokens) == 1
        assert "hello" in comment_tokens[0].value

    def test_multiline_block_comment(self):
        tokens = tokenize_to_list("(* line1\nline2 *)")
        comment_tokens = [t for t in tokens if t.type == TokenType.COMMENT_BLOCK]
        assert len(comment_tokens) == 1


class TestPragma:
    def test_pragma(self):
        tokens = tokens_without_whitespace("{attribute 'hide'}")
        assert tokens[0].type == TokenType.PRAGMA
        assert "attribute" in tokens[0].value


class TestOperators:
    def test_comparison(self):
        tokens = tokens_without_whitespace("x <> y")
        assert tokens[1].type == TokenType.OPERATOR
        assert tokens[1].value == "<>"

    def test_less_equal(self):
        tokens = tokens_without_whitespace("x <= y")
        assert tokens[1].type == TokenType.OPERATOR
        assert tokens[1].value == "<="

    def test_plus(self):
        tokens = tokens_without_whitespace("a + b")
        assert tokens[1].type == TokenType.OPERATOR
        assert tokens[1].value == "+"

    def test_range(self):
        tokens = tokens_without_whitespace("1..10")
        assert tokens[1].type == TokenType.RANGE


class TestPositionTracking:
    def test_line_tracking(self):
        tokens = tokenize_to_list("a\nb\nc")
        identifiers = [t for t in tokens if t.type == TokenType.IDENTIFIER]
        assert identifiers[0].line == 1
        assert identifiers[1].line == 2
        assert identifiers[2].line == 3

    def test_eof_at_end(self):
        tokens = tokenize_to_list("x")
        assert tokens[-1].type == TokenType.EOF


class TestEdgeCases:
    def test_empty_input(self):
        tokens = tokenize_to_list("")
        assert len(tokens) == 1
        assert tokens[0].type == TokenType.EOF

    def test_whitespace_only(self):
        tokens = tokenize_to_list("   \n\t\n  ")
        non_ws = [t for t in tokens if t.type not in (TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.EOF)]
        assert len(non_ws) == 0

    def test_and_then_keyword(self):
        tokens = tokens_without_whitespace("a AND_THEN b")
        assert tokens[1].type == TokenType.KEYWORD
        assert tokens[1].value == "AND_THEN"
