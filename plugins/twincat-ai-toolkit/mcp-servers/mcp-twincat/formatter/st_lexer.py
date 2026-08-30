"""Token-based ST lexer with pre-compiled regex scanner.

Uses a single-pass combined regex for maximum performance.
Generator-based to avoid building full token list in memory.
"""
from __future__ import annotations

from typing import Generator

from formatter.constants import (
    SCANNER_PATTERN,
    SCANNER_TOKEN_MAP,
    ST_KEYWORDS,
    TokenType,
)
from formatter.types import Token


def tokenize(source: str) -> Generator[Token, None, None]:
    """Tokenize IEC 61131-3 Structured Text source code.

    Yields Token objects in source order. Keywords are recognized by
    case-insensitive lookup against the ST_KEYWORDS frozenset.
    Unterminated comments/strings produce UNKNOWN tokens (no crash).
    """
    line = 1
    col = 1

    for match in SCANNER_PATTERN.finditer(source):
        group_name = match.lastgroup
        if group_name is None:
            continue

        value = match.group()
        token_type = SCANNER_TOKEN_MAP[group_name]

        if token_type == TokenType.IDENTIFIER:
            upper = value.upper()
            if upper in ST_KEYWORDS:
                token_type = TokenType.KEYWORD
                value = upper

        yield Token(type=token_type, value=value, line=line, col=col)

        if token_type == TokenType.NEWLINE:
            line += value.count("\n")
            col = 1
        elif token_type == TokenType.COMMENT_BLOCK:
            newlines = value.count("\n")
            if newlines:
                line += newlines
                col = len(value) - value.rfind("\n")
            else:
                col += len(value)
        else:
            col += len(value)

    yield Token(type=TokenType.EOF, value="", line=line, col=col)


def tokenize_to_list(source: str) -> list[Token]:
    """Convenience: tokenize and collect all tokens into a list."""
    return list(tokenize(source))


def tokens_without_whitespace(source: str) -> list[Token]:
    """Tokenize and filter out whitespace/newline tokens."""
    return [
        t for t in tokenize(source)
        if t.type not in (TokenType.WHITESPACE, TokenType.NEWLINE, TokenType.EOF)
    ]
