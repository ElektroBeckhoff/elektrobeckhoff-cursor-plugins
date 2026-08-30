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


def _scan_block_comment(source: str, start: int) -> int:
    """Scan (* ... *) taking nested comments into account. Returns end offset."""
    depth = 1
    i = start + 2
    n = len(source)
    while i < n:
        if i + 1 < n and source[i] == "(" and source[i + 1] == "*":
            depth += 1
            i += 2
        elif i + 1 < n and source[i] == "*" and source[i + 1] == ")":
            depth -= 1
            i += 2
            if depth == 0:
                return i
        else:
            i += 1
    return n


def _scan_string_literal(source: str, start: int, quote_char: str) -> int:
    """Scan IEC 61131-3 string literal with dollar escapes ($N, $') or doubled quotes ('' / "")."""
    i = start + 1
    n = len(source)
    while i < n:
        c = source[i]
        if c == "$" and i + 1 < n:
            i += 2
        elif c == quote_char:
            if i + 1 < n and source[i + 1] == quote_char:
                i += 2  # Doubled quote escape
            else:
                return i + 1
        elif c in ("\r", "\n"):
            return i  # Unterminated on newline
        else:
            i += 1
    return n


def tokenize(source: str) -> Generator[Token, None, None]:
    """Tokenize IEC 61131-3 Structured Text source code.

    Yields Token objects in source order. Keywords are recognized by
    case-insensitive lookup against the ST_KEYWORDS frozenset.
    Unterminated comments/strings produce UNKNOWN tokens (no crash).
    """
    line = 1
    col = 1
    n = len(source)
    idx = 0
    scanner_match = SCANNER_PATTERN.match

    while idx < n:
        # 1. Nested block comments (* ... (* ... *) ... *)
        if idx + 1 < n and source[idx] == "(" and source[idx + 1] == "*":
            end_idx = _scan_block_comment(source, idx)
            value = source[idx:end_idx]
            tok_line, tok_col = line, col
            newlines = value.count("\n")
            if newlines:
                line += newlines
                col = len(value) - value.rfind("\n")
            else:
                col += len(value)
            idx = end_idx
            yield Token(type=TokenType.COMMENT_BLOCK, value=value, line=tok_line, col=tok_col)
            continue

        # 2. String literals with $ escapes and doubled quotes
        if source[idx] in ("'", '"'):
            quote_char = source[idx]
            end_idx = _scan_string_literal(source, idx, quote_char)
            value = source[idx:end_idx]
            tok_line, tok_col = line, col
            newlines = value.count("\n")
            if newlines:
                line += newlines
                col = len(value) - value.rfind("\n")
            else:
                col += len(value)
            idx = end_idx
            yield Token(type=TokenType.STRING, value=value, line=tok_line, col=tok_col)
            continue

        match = scanner_match(source, idx)
        if match is None:
            value = source[idx]
            yield Token(type=TokenType.UNKNOWN, value=value, line=line, col=col)
            col += 1
            idx += 1
            continue

        group_name = match.lastgroup
        value = match.group()
        token_type = SCANNER_TOKEN_MAP[group_name]

        if token_type == TokenType.IDENTIFIER:
            upper = value.upper()
            if upper in ST_KEYWORDS:
                token_type = TokenType.KEYWORD
                value = upper

        tok_line, tok_col = line, col
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

        idx = match.end()
        yield Token(type=token_type, value=value, line=tok_line, col=tok_col)

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
