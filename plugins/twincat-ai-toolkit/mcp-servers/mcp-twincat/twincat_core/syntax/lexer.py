"""Lossless Lexer for IEC 61131-3 Structured Text and TwinCAT 3 pragmas/attributes."""
from __future__ import annotations

import re
from typing import Iterator, List

from .diagnostics import DiagnosticSeverity, SyntaxDiagnostic
from .span import Position, SourceSpan
from .tokens import KEYWORDS_MAP, Token, TokenChannel, TokenType

# Multi-word and compound keywords scanner regex
_RE_COMPOUND_KEYWORDS = re.compile(
    r"\b(FUNCTION_BLOCK|END_FUNCTION_BLOCK|END_PROGRAM|END_FUNCTION|END_METHOD|"
    r"END_PROPERTY|END_ACTION|END_INTERFACE|END_STRUCT|END_TYPE|END_UNION|END_VAR|"
    r"END_IF|END_CASE|END_FOR|END_WHILE|END_REPEAT|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|"
    r"VAR_GLOBAL|VAR_TEMP|VAR_STAT|VAR_INST|VAR_CONFIG|VAR_EXTERNAL|VAR_GENERIC|NON_RETAIN|READ_ONLY|READ_WRITE|AND_THEN|OR_ELSE|"
    r"LOWER_BOUND|UPPER_BOUND|"
    r"__NEW|__DELETE|__TRY|__CATCH|__FINALLY|__ENDTRY|__QUERYINTERFACE|__QUERYPOINTER|__ISVALIDREF|__VARINFO|__POUNAME|__POSITION)\b",
    re.IGNORECASE,
)

# Typed Literals (e.g. T#5s, TIME#100ms, DT#2026-08-30-11:00:00, INT#42, 16#FF, 2#1010, E_Enum#Member)
_RE_TYPED_OR_BASED_LITERAL = re.compile(
    r"\b(?:"
    r"(?:16#[0-9A-Fa-f_]+)"
    r"|(?:8#[0-7_]+)"
    r"|(?:2#[01_]+)"
    r"|(?:[A-Za-z_][A-Za-z0-9_]*#[^\s;,)=}\]]+)"
    r")",
    re.IGNORECASE,
)

_RE_DIRECT_ADDRESS = re.compile(r"%(?:I|Q|M)(?:\*|[XBWDL]?[0-9]+(?:\.[0-9]+)*)", re.IGNORECASE)
_RE_PARTIAL_ACCESS = re.compile(r"%[XBWDL][0-9]+", re.IGNORECASE)

_RE_NUMBER = re.compile(r"\b\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?\b")

_RE_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _scan_block_comment(source: str, start: int) -> int:
    """Scan (* ... *) taking nested comments into account. Returns end offset."""
    depth = 1
    i = start
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


def _scan_pragma(source: str, start: int) -> int:
    """Scan {attribute ...} or {pragma ...}. Returns end offset."""
    idx = source.find("}", start)
    return idx + 1 if idx != -1 else len(source)


class Lexer:
    """Lossless lexical analyzer for Structured Text source."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.length = len(source)
        self.offset = 0
        self.line = 1
        self.col = 1
        self.diagnostics: list[SyntaxDiagnostic] = []

    def _make_position(self) -> Position:
        return Position(line=self.line, col=self.col, offset=self.offset)

    def _advance(self, count: int) -> None:
        if count <= 0:
            return
        if count == 1:
            if self.offset < self.length:
                ch = self.source[self.offset]
                self.offset += 1
                if ch == "\n":
                    self.line += 1
                    self.col = 1
                elif ch == "\r":
                    if self.offset < self.length and self.source[self.offset] == "\n":
                        pass
                    else:
                        self.line += 1
                        self.col = 1
                else:
                    self.col += 1
            return

        end_off = min(self.offset + count, self.length)
        segment = self.source[self.offset : end_off]
        if "\n" not in segment and "\r" not in segment:
            self.offset = end_off
            self.col += len(segment)
            return

        for ch in segment:
            self.offset += 1
            if ch == "\n":
                self.line += 1
                self.col = 1
            elif ch == "\r":
                if self.offset < self.length and self.source[self.offset] == "\n":
                    pass
                else:
                    self.line += 1
                    self.col = 1
            else:
                self.col += 1

    def tokenize_all(self, include_trivia: bool = True) -> list[Token]:
        """Tokenize entire source into a list of Tokens."""
        tokens: list[Token] = []
        for tok in self:
            if include_trivia or not tok.is_trivia:
                tokens.append(tok)
        return tokens

    def __iter__(self) -> Iterator[Token]:
        while self.offset < self.length:
            yield self._next_token()
        eof_pos = self._make_position()
        yield Token(
            type=TokenType.EOF,
            value="",
            span=SourceSpan(start=eof_pos, end=eof_pos),
            channel=TokenChannel.DEFAULT,
        )

    def _next_token(self) -> Token:
        start_pos = self._make_position()
        ch = self.source[self.offset]
        next_ch = self.source[self.offset + 1] if self.offset + 1 < self.length else ""

        # 1. Whitespace
        if ch in (" ", "\t"):
            start = self.offset
            while self.offset < self.length and self.source[self.offset] in (" ", "\t"):
                self._advance(1)
            val = self.source[start : self.offset]
            return Token(
                type=TokenType.WHITESPACE,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
                channel=TokenChannel.TRIVIA,
            )

        # 2. Newlines
        if ch == "\r" or ch == "\n":
            start = self.offset
            if ch == "\r" and next_ch == "\n":
                self._advance(2)
            else:
                self._advance(1)
            val = self.source[start : self.offset]
            return Token(
                type=TokenType.NEWLINE,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
                channel=TokenChannel.TRIVIA,
            )

        # 3. Line comment //
        if ch == "/" and next_ch == "/":
            start = self.offset
            while self.offset < self.length and self.source[self.offset] not in ("\r", "\n"):
                self._advance(1)
            val = self.source[start : self.offset]
            return Token(
                type=TokenType.LINE_COMMENT,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
                channel=TokenChannel.TRIVIA,
            )

        # 4. Block comment (* ... *)
        if ch == "(" and next_ch == "*":
            start = self.offset
            end_offset = _scan_block_comment(self.source, self.offset + 2)
            self._advance(end_offset - self.offset)
            val = self.source[start : self.offset]
            if not val.endswith("*)"):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Unterminated block comment",
                        span=SourceSpan(start=start_pos, end=self._make_position()),
                        severity=DiagnosticSeverity.ERROR,
                    )
                )
            return Token(
                type=TokenType.BLOCK_COMMENT,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
                channel=TokenChannel.TRIVIA,
            )

        # 5. Pragma { ... }
        if ch == "{":
            start = self.offset
            end_offset = _scan_pragma(self.source, self.offset + 1)
            self._advance(end_offset - self.offset)
            val = self.source[start : self.offset]
            if not val.endswith("}"):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Unterminated pragma attribute",
                        span=SourceSpan(start=start_pos, end=self._make_position()),
                        severity=DiagnosticSeverity.ERROR,
                    )
                )
            return Token(
                type=TokenType.PRAGMA,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
                channel=TokenChannel.TRIVIA,
            )

        # 6. Direct Addressing (%I*, %QX0.0, %MW10) or Partial Access (%X0, %B1)
        if ch == "%":
            m_dir = _RE_DIRECT_ADDRESS.match(self.source, self.offset)
            if m_dir:
                val = m_dir.group(0)
                self._advance(len(val))
                return Token(
                    type=TokenType.DIRECT_ADDRESS,
                    value=val,
                    span=SourceSpan(start=start_pos, end=self._make_position()),
                )
            m_part = _RE_PARTIAL_ACCESS.match(self.source, self.offset)
            if m_part:
                val = m_part.group(0)
                self._advance(len(val))
                return Token(
                    type=TokenType.PARTIAL_ACCESS,
                    value=val,
                    span=SourceSpan(start=start_pos, end=self._make_position()),
                )

        # 7. Strings
        if ch == "'":
            start = self.offset
            end_offset = _scan_string_literal(self.source, self.offset, "'")
            self._advance(end_offset - self.offset)
            val = self.source[start : self.offset]
            if not (len(val) >= 2 and val.endswith("'")):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Unterminated single-quote string literal",
                        span=SourceSpan(start=start_pos, end=self._make_position()),
                    )
                )
            return Token(
                type=TokenType.STRING_LITERAL,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        if ch == '"':
            start = self.offset
            end_offset = _scan_string_literal(self.source, self.offset, '"')
            self._advance(end_offset - self.offset)
            val = self.source[start : self.offset]
            if not (len(val) >= 2 and val.endswith('"')):
                self.diagnostics.append(
                    SyntaxDiagnostic(
                        message="Unterminated double-quote string literal",
                        span=SourceSpan(start=start_pos, end=self._make_position()),
                    )
                )
            return Token(
                type=TokenType.WSTRING_LITERAL,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        # 8. Typed / Base literals (T#5s, 16#FF, etc.)
        m_typed = _RE_TYPED_OR_BASED_LITERAL.match(self.source, self.offset)
        if m_typed:
            val = m_typed.group(0)
            self._advance(len(val))
            return Token(
                type=TokenType.TYPED_LITERAL,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        # 9. Numbers (Floats / Integers)
        m_num = _RE_NUMBER.match(self.source, self.offset)
        if m_num:
            val = m_num.group(0)
            self._advance(len(val))
            ttype = TokenType.REAL_LITERAL if ("." in val or "e" in val.lower()) else TokenType.INT_LITERAL
            return Token(
                type=ttype,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        # 10. Multi-character operators and punctuators
        if ch == ":" and next_ch == "=":
            self._advance(2)
            return Token(
                type=TokenType.ASSIGN,
                value=":=",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        if ch == "=" and next_ch == ">":
            self._advance(2)
            return Token(
                type=TokenType.OUTPUT_ASSIGN,
                value="=>",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        if ch == "?" and next_ch == "=":
            self._advance(2)
            return Token(
                type=TokenType.REF_ASSIGN,
                value="?=",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        if ch == "." and next_ch == ".":
            self._advance(2)
            return Token(
                type=TokenType.RANGE,
                value="..",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        if ch == "<" and next_ch == ">":
            self._advance(2)
            return Token(
                type=TokenType.NE,
                value="<>",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        if ch == "<" and next_ch == "=":
            self._advance(2)
            return Token(
                type=TokenType.LE,
                value="<=",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        if ch == ">" and next_ch == "=":
            self._advance(2)
            return Token(
                type=TokenType.GE,
                value=">=",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        if ch == "*" and next_ch == "*":
            self._advance(2)
            return Token(
                type=TokenType.POWER,
                value="**",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        # REF= assignment operator
        if self.source[self.offset : self.offset + 4].upper() == "REF=":
            self._advance(4)
            return Token(
                type=TokenType.REF_ASSIGN,
                value=self.source[self.offset - 4 : self.offset],
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        # 11. Single-character punctuation / operators
        single_ops = {
            ";": TokenType.SEMICOLON,
            ":": TokenType.COLON,
            ",": TokenType.COMMA,
            ".": TokenType.DOT,
            "^": TokenType.POINTER_DEREF,
            "(": TokenType.PAREN_OPEN,
            ")": TokenType.PAREN_CLOSE,
            "[": TokenType.BRACKET_OPEN,
            "]": TokenType.BRACKET_CLOSE,
            "=": TokenType.EQ,
            "<": TokenType.LT,
            ">": TokenType.GT,
            "+": TokenType.PLUS,
            "-": TokenType.MINUS,
            "*": TokenType.STAR,
            "/": TokenType.SLASH,
        }
        if ch in single_ops:
            self._advance(1)
            return Token(
                type=single_ops[ch],
                value=ch,
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        # 12. Compound keywords or Identifiers
        m_compound = _RE_COMPOUND_KEYWORDS.match(self.source, self.offset)
        if m_compound:
            val = m_compound.group(0)
            self._advance(len(val))
            ttype = KEYWORDS_MAP.get(val.upper(), TokenType.IDENTIFIER)
            return Token(
                type=ttype,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        m_id = _RE_IDENTIFIER.match(self.source, self.offset)
        if m_id:
            val = m_id.group(0)
            self._advance(len(val))
            upper_val = val.upper()
            ttype = KEYWORDS_MAP.get(upper_val, TokenType.IDENTIFIER)
            return Token(
                type=ttype,
                value=val,
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )

        # 13. Unknown single character fallback (never crash)
        self._advance(1)
        self.diagnostics.append(
            SyntaxDiagnostic(
                message=f"Unexpected character: {ch!r}",
                span=SourceSpan(start=start_pos, end=self._make_position()),
            )
        )
        return Token(
            type=TokenType.UNKNOWN,
            value=ch,
            span=SourceSpan(start=start_pos, end=self._make_position()),
        )


def tokenize_st(source: str, include_trivia: bool = True) -> tuple[list[Token], list[SyntaxDiagnostic]]:
    """Tokenize Structured Text source and return (tokens, diagnostics)."""
    lexer = Lexer(source)
    tokens = lexer.tokenize_all(include_trivia=include_trivia)
    return tokens, lexer.diagnostics
