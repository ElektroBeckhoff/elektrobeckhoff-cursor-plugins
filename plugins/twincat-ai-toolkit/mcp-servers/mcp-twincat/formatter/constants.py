"""Central constants for the TwinCAT3 ST Formatter.

All magic values, keyword sets, regex patterns, and limits live here.
No other module should define these — import from constants.
"""
from __future__ import annotations

import re
from enum import IntEnum

# ---------------------------------------------------------------------------
# Token Types
# ---------------------------------------------------------------------------


class TokenType(IntEnum):
    KEYWORD = 0
    IDENTIFIER = 1
    NUMBER = 2
    STRING = 3
    OPERATOR = 4
    COMMENT_BLOCK = 5
    COMMENT_LINE = 6
    PRAGMA = 7
    WHITESPACE = 8
    NEWLINE = 9
    SEMICOLON = 10
    COLON = 11
    ASSIGN = 12
    OUTPUT_ASSIGN = 13
    COMMA = 14
    PAREN_OPEN = 15
    PAREN_CLOSE = 16
    BRACKET_OPEN = 17
    BRACKET_CLOSE = 18
    DOT = 19
    RANGE = 20
    POINTER_DEREF = 21
    EOF = 22
    UNKNOWN = 23


# ---------------------------------------------------------------------------
# IEC 61131-3 + TwinCAT Keywords
# ---------------------------------------------------------------------------

ST_KEYWORDS: frozenset[str] = frozenset({
    # Program Organisation Units
    "PROGRAM", "END_PROGRAM",
    "FUNCTION_BLOCK", "END_FUNCTION_BLOCK",
    "FUNCTION", "END_FUNCTION",
    "METHOD", "END_METHOD",
    "PROPERTY", "END_PROPERTY",
    "ACTION", "END_ACTION",
    "INTERFACE", "END_INTERFACE",
    # Variable declarations
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT",
    "VAR_GLOBAL", "VAR_TEMP", "VAR_STAT", "VAR_INST",
    "END_VAR",
    "CONSTANT", "PERSISTENT", "RETAIN",
    "AT",
    # Control flow
    "IF", "THEN", "ELSIF", "ELSE", "END_IF",
    "CASE", "OF", "END_CASE",
    "FOR", "TO", "BY", "DO", "END_FOR",
    "WHILE", "END_WHILE",
    "REPEAT", "UNTIL", "END_REPEAT",
    "RETURN", "EXIT", "CONTINUE", "JMP",
    # Boolean / bitwise
    "AND", "OR", "NOT", "XOR", "MOD",
    "AND_THEN", "OR_ELSE",
    # Literals
    "TRUE", "FALSE",
    # Data types
    "BOOL", "BYTE", "WORD", "DWORD", "LWORD",
    "SINT", "INT", "DINT", "LINT",
    "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL",
    "STRING", "WSTRING",
    "TIME", "LTIME", "DATE", "TIME_OF_DAY", "TOD", "DATE_AND_TIME", "DT",
    "LDATE", "LTIME_OF_DAY", "LTOD", "LDATE_AND_TIME", "LDT",
    "ANY", "ANY_BIT", "ANY_INT", "ANY_REAL", "ANY_NUM", "ANY_STRING",
    # Structured types
    "ARRAY", "STRUCT", "END_STRUCT", "TYPE", "END_TYPE", "UNION", "END_UNION",
    # OOP
    "EXTENDS", "IMPLEMENTS",
    "ABSTRACT", "FINAL",
    "OVERRIDE",
    "PROTECTED", "PRIVATE", "PUBLIC", "INTERNAL",
    "THIS", "SUPER",
    # Pointer / Reference
    "POINTER", "REFERENCE",
    # Operators as keywords
    "ADR", "SIZEOF", "REF",
    "__NEW", "__DELETE",
    "__ISVALIDREF",
    "__QUERYINTERFACE", "__QUERYPOINTER",
    "__TRY", "__CATCH", "__FINALLY", "__ENDTRY",
    "__VARINFO", "__POUNAME", "__POSITION",
    "VAR_CONFIG",
})

# Keywords that open a new indent level
INDENT_OPENERS: frozenset[str] = frozenset({
    "IF", "ELSIF", "ELSE",
    "FOR", "WHILE", "REPEAT",
    "CASE",
    "STRUCT",
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT",
    "VAR_GLOBAL", "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG",
    "METHOD", "ACTION", "PROPERTY",
    "PROGRAM", "FUNCTION_BLOCK", "FUNCTION",
    "__TRY", "__CATCH", "__FINALLY",
})

# Keywords that close an indent level
INDENT_CLOSERS: frozenset[str] = frozenset({
    "END_IF", "END_FOR", "END_WHILE", "END_REPEAT", "END_CASE",
    "END_STRUCT", "END_TYPE", "END_UNION",
    "END_VAR",
    "END_METHOD", "END_ACTION", "END_PROPERTY",
    "END_PROGRAM", "END_FUNCTION_BLOCK", "END_FUNCTION",
    "ELSIF", "ELSE", "UNTIL",
    "__ENDTRY", "__CATCH", "__FINALLY",
})

# Keywords that are data types (for declaration context detection)
TYPE_KEYWORDS: frozenset[str] = frozenset({
    "BOOL", "BYTE", "WORD", "DWORD", "LWORD",
    "SINT", "INT", "DINT", "LINT",
    "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL",
    "STRING", "WSTRING",
    "TIME", "LTIME", "DATE", "TOD", "DT",
    "LDATE", "LTOD", "LDT",
    "ANY", "ANY_BIT", "ANY_INT", "ANY_REAL", "ANY_NUM", "ANY_STRING",
    "ARRAY", "POINTER", "REFERENCE",
})

# VAR block openers (for alignment context)
VAR_BLOCK_KEYWORDS: frozenset[str] = frozenset({
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT",
    "VAR_GLOBAL", "VAR_TEMP", "VAR_STAT", "VAR_INST", "VAR_CONFIG",
})

# Binary operators requiring spaces
BINARY_OPERATORS: frozenset[str] = frozenset({
    "+", "-", "*", "/",
    "=", "<>", "<", ">", "<=", ">=",
    ":=",
    "AND", "OR", "XOR", "MOD", "NOT",
    "AND_THEN", "OR_ELSE",
})

# ---------------------------------------------------------------------------
# File Extensions
# ---------------------------------------------------------------------------

FORMATTABLE_EXTENSIONS: frozenset[str] = frozenset({
    ".tcpou", ".tcdut", ".tcgvl", ".tcio",
})

# ---------------------------------------------------------------------------
# XML Constants
# ---------------------------------------------------------------------------

XML_POU_CHILD_ORDER: tuple[str, ...] = (
    "Declaration", "Implementation", "Folder", "Method", "Action", "Property",
)

XML_ATTRIBUTE_ORDER: dict[str, tuple[str, ...]] = {
    "TcPlcObject": ("Version", "ProductVersion"),
    "POU": ("Name", "Id", "SpecialFunc"),
    "DUT": ("Name", "Id"),
    "GVL": ("Name", "Id", "ParameterList"),
    "Itf": ("Name", "Id"),
    "Method": ("Name", "Id", "FolderPath"),
    "Action": ("Name", "Id", "FolderPath"),
    "Property": ("Name", "Id", "FolderPath"),
    "Folder": ("Name", "Id"),
    "Get": ("Name", "Id"),
    "Set": ("Name", "Id"),
}

# Valid SpecialFunc values for POU elements
VALID_SPECIAL_FUNC: frozenset[str] = frozenset({
    "None", "PRG_INIT", "PRG_EXIT",
})

# ---------------------------------------------------------------------------
# Regex Patterns (pre-compiled at module load for performance)
# ---------------------------------------------------------------------------

RE_COMMENT_BLOCK = re.compile(r"\(\*.*?\*\)", re.DOTALL)
RE_COMMENT_LINE = re.compile(r"//[^\n]*")
RE_STRING_SINGLE = re.compile(r"'(?:[^'\\]|\\.)*'")
RE_STRING_DOUBLE = re.compile(r'"(?:[^"\\]|\\.)*"')
# IEC 61131-3 ST: escaped quote is doubled ('' inside '...'), not backslash.
RE_ST_STRING_SINGLE = re.compile(r"'(?:''|[^'])*'")
RE_ST_STRING_DOUBLE = re.compile(r'"(?:""|[^"])*"')
RE_ST_STRING_LIT = re.compile(
    r"'(?:''|[^'])*'|\"(?:\"\"|[^\"]*)\"",
)
RE_PRAGMA = re.compile(r"\{[^}]*\}")
RE_GUID = re.compile(
    r"\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}"
)
RE_NUMBER = re.compile(
    r"(?:"
    r"(?i:16#[0-9A-Fa-f_]+)"
    r"|(?i:8#[0-7_]+)"
    r"|(?i:2#[01_]+)"
    r"|(?i:T#[\d_]+(?:d|h|m|s|ms|us|ns)(?:[\d_]+(?:h|m|s|ms|us|ns))*)"
    r"|(?i:(?:TIME|LTIME|DATE_AND_TIME|TIME_OF_DAY|DATE|TOD|DT|LDATE|LTOD|LDT|BYTE|WORD|DWORD|LWORD|SINT|INT|DINT|LINT|USINT|UINT|UDINT|ULINT|REAL|LREAL|D))#[^\s;,)\]]+"
    r"|\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?"
    r")"
)
RE_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
RE_WHITESPACE = re.compile(r"[ \t]+")
RE_NEWLINE = re.compile(r"\r\n|\r|\n")
RE_ASSIGN = re.compile(r":=")
RE_OUTPUT_ASSIGN = re.compile(r"=>")
RE_RANGE = re.compile(r"\.\.")
RE_POINTER_DEREF = re.compile(r"\^")
RE_COMPARISON = re.compile(r"<>|<=|>=|=|(?:\?=)|<|>")

# Master scanner: ordered by priority (longest match first)
_TOKEN_PATTERNS: list[tuple[TokenType, re.Pattern[str]]] = [
    (TokenType.NEWLINE, RE_NEWLINE),
    (TokenType.WHITESPACE, RE_WHITESPACE),
    (TokenType.COMMENT_BLOCK, re.compile(r"\(\*.*?\*\)", re.DOTALL)),
    (TokenType.COMMENT_LINE, re.compile(r"//[^\n]*")),
    (TokenType.PRAGMA, re.compile(r"\{[^}]*\}")),
    (TokenType.STRING, re.compile(r"'(?:''|\$[^\r\n]|[^'$\r\n])*'|\"(?:\"\"|\$[^\r\n]|[^\"$\r\n])*\"")),
    (TokenType.NUMBER, RE_NUMBER),
    (TokenType.ASSIGN, RE_ASSIGN),
    (TokenType.OUTPUT_ASSIGN, RE_OUTPUT_ASSIGN),
    (TokenType.RANGE, RE_RANGE),
    (TokenType.POINTER_DEREF, RE_POINTER_DEREF),
    (TokenType.OPERATOR, RE_COMPARISON),
    (TokenType.SEMICOLON, re.compile(r";")),
    (TokenType.COLON, re.compile(r":")),
    (TokenType.COMMA, re.compile(r",")),
    (TokenType.PAREN_OPEN, re.compile(r"\(")),
    (TokenType.PAREN_CLOSE, re.compile(r"\)")),
    (TokenType.BRACKET_OPEN, re.compile(r"\[")),
    (TokenType.BRACKET_CLOSE, re.compile(r"\]")),
    (TokenType.DOT, re.compile(r"\.")),
    (TokenType.OPERATOR, re.compile(r"[+\-*/%&|~^?]")),
    (TokenType.IDENTIFIER, RE_IDENTIFIER),
    (TokenType.UNKNOWN, re.compile(r"[^\s]")),
]

# Build combined scanner regex for performance (single pass)
_SCANNER_PATTERN = re.compile(
    "|".join(f"(?P<T{i}>{p.pattern})" for i, (_, p) in enumerate(_TOKEN_PATTERNS)),
    re.DOTALL,
)
SCANNER_PATTERN = _SCANNER_PATTERN
SCANNER_TOKEN_MAP: dict[str, TokenType] = {
    f"T{i}": tt for i, (tt, _) in enumerate(_TOKEN_PATTERNS)
}

# ---------------------------------------------------------------------------
# Formatting Limits (defaults)
# ---------------------------------------------------------------------------

MAX_LINE_LENGTH_DEFAULT = 230
MAX_PARAMS_SINGLE_LINE = 4
MAX_STRUCT_INIT_SINGLE_LINE = 3
MAX_ARRAY_INIT_SINGLE_LINE = 30
MAX_ENUM_MEMBERS_SINGLE_LINE = 5
INDENT_SIZE_DEFAULT = 4
XML_INDENT_SIZE_DEFAULT = 2
MULTILINE_CALL_INDENT = 8  # 2x indent for multiline FB call params
