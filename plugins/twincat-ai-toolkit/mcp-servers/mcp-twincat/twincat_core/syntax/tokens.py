"""Token definitions, channels, and TokenType enum for IEC 61131-3 ST + TwinCAT."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Tuple

from .span import SourceSpan


class TokenChannel(IntEnum):
    DEFAULT = 0  # Semantic tokens for parsing
    TRIVIA = 1   # Whitespace, comments, pragmas, newlines


class TokenType(IntEnum):
    # Special
    EOF = 0
    UNKNOWN = 1

    # Trivia
    WHITESPACE = 10
    NEWLINE = 11
    LINE_COMMENT = 12
    BLOCK_COMMENT = 13
    PRAGMA = 14

    # Identifiers & Literals
    IDENTIFIER = 20
    INT_LITERAL = 21
    REAL_LITERAL = 22
    HEX_LITERAL = 23
    BIN_LITERAL = 24
    TYPED_LITERAL = 25    # T#5s, TIME#100ms, DT#..., INT#42, etc.
    STRING_LITERAL = 26   # '...'
    WSTRING_LITERAL = 27  # "..."
    BOOL_LITERAL = 28     # TRUE, FALSE
    DIRECT_ADDRESS = 29   # %I*, %QX0.0, %MW10
    PARTIAL_ACCESS = 30   # %X0, %B1, %W2, %D0, %L0

    # Keywords - POU & Scope
    KEYWORD_PROGRAM = 40
    KEYWORD_END_PROGRAM = 41
    KEYWORD_FUNCTION_BLOCK = 42
    KEYWORD_END_FUNCTION_BLOCK = 43
    KEYWORD_FUNCTION = 44
    KEYWORD_END_FUNCTION = 45
    KEYWORD_METHOD = 46
    KEYWORD_END_METHOD = 47
    KEYWORD_PROPERTY = 48
    KEYWORD_END_PROPERTY = 49
    KEYWORD_ACTION = 50
    KEYWORD_END_ACTION = 51
    KEYWORD_INTERFACE = 52
    KEYWORD_END_INTERFACE = 53

    # Keywords - Variables & Blocks
    KEYWORD_VAR = 60
    KEYWORD_VAR_INPUT = 61
    KEYWORD_VAR_OUTPUT = 62
    KEYWORD_VAR_IN_OUT = 63
    KEYWORD_VAR_GLOBAL = 64
    KEYWORD_VAR_TEMP = 65
    KEYWORD_VAR_STAT = 66
    KEYWORD_VAR_INST = 67
    KEYWORD_VAR_CONFIG = 68
    KEYWORD_END_VAR = 69
    KEYWORD_CONSTANT = 70
    KEYWORD_RETAIN = 71
    KEYWORD_PERSISTENT = 72
    KEYWORD_AT = 73
    KEYWORD_VAR_EXTERNAL = 74
    KEYWORD_VAR_GENERIC = 75
    KEYWORD_NON_RETAIN = 76
    KEYWORD_READ_ONLY = 77
    KEYWORD_READ_WRITE = 78

    # Keywords - Types & Structs
    KEYWORD_TYPE = 80
    KEYWORD_END_TYPE = 81
    KEYWORD_STRUCT = 82
    KEYWORD_END_STRUCT = 83
    KEYWORD_UNION = 84
    KEYWORD_END_UNION = 85
    KEYWORD_ARRAY = 86
    KEYWORD_OF = 87
    KEYWORD_POINTER = 88
    KEYWORD_REFERENCE = 89

    # Keywords - OOP & Modifiers
    KEYWORD_EXTENDS = 90
    KEYWORD_IMPLEMENTS = 91
    KEYWORD_ABSTRACT = 92
    KEYWORD_FINAL = 93
    KEYWORD_PUBLIC = 94
    KEYWORD_PROTECTED = 95
    KEYWORD_PRIVATE = 96
    KEYWORD_INTERNAL = 97
    KEYWORD_THIS = 98
    KEYWORD_SUPER = 99

    # Keywords - Control Flow
    KEYWORD_IF = 110
    KEYWORD_THEN = 111
    KEYWORD_ELSIF = 112
    KEYWORD_ELSE = 113
    KEYWORD_END_IF = 114
    KEYWORD_CASE = 115
    KEYWORD_END_CASE = 116
    KEYWORD_FOR = 117
    KEYWORD_TO = 118
    KEYWORD_BY = 119
    KEYWORD_DO = 120
    KEYWORD_END_FOR = 121
    KEYWORD_WHILE = 122
    KEYWORD_END_WHILE = 123
    KEYWORD_REPEAT = 124
    KEYWORD_UNTIL = 125
    KEYWORD_END_REPEAT = 126
    KEYWORD_RETURN = 127
    KEYWORD_EXIT = 128
    KEYWORD_CONTINUE = 129
    KEYWORD_JMP = 130

    # Keywords - Operators / Built-in
    KEYWORD_AND = 140
    KEYWORD_OR = 141
    KEYWORD_XOR = 142
    KEYWORD_NOT = 143
    KEYWORD_MOD = 144
    KEYWORD_AND_THEN = 145
    KEYWORD_OR_ELSE = 146
    KEYWORD_ADR = 147
    KEYWORD_SIZEOF = 148
    KEYWORD_REF = 149
    KEYWORD_NEW = 150       # __NEW
    KEYWORD_DELETE = 151    # __DELETE
    KEYWORD_TRY = 152       # __TRY
    KEYWORD_CATCH = 153     # __CATCH
    KEYWORD_FINALLY = 154   # __FINALLY
    KEYWORD_ENDTRY = 155    # __ENDTRY
    KEYWORD_QUERYINTERFACE = 156   # __QUERYINTERFACE
    KEYWORD_QUERYPOINTER = 157     # __QUERYPOINTER
    KEYWORD_ISVALIDREF = 158       # __ISVALIDREF
    KEYWORD_VARINFO = 159          # __VARINFO
    KEYWORD_POUNAME = 160          # __POUNAME
    KEYWORD_POSITION = 161         # __POSITION
    KEYWORD_BITADR = 162           # BITADR
    KEYWORD_ADRREF = 163           # ADRREF
    KEYWORD_XSIZEOF = 164          # XSIZEOF
    KEYWORD_INDEXOF = 165          # INDEXOF
    KEYWORD_EXPT = 166             # EXPT
    KEYWORD_LOWER_BOUND = 167      # LOWER_BOUND
    KEYWORD_UPPER_BOUND = 168      # UPPER_BOUND

    # Punctuators & Operators
    SEMICOLON = 170       # ;
    COLON = 171           # :
    COMMA = 172           # ,
    DOT = 173             # .
    RANGE = 174           # ..
    ASSIGN = 175          # :=
    OUTPUT_ASSIGN = 176   # =>
    REF_ASSIGN = 177      # ?= or REF=
    POINTER_DEREF = 178   # ^
    PAREN_OPEN = 179      # (
    PAREN_CLOSE = 180     # )
    BRACKET_OPEN = 181    # [
    BRACKET_CLOSE = 182   # ]

    # Comparison & Arithmetic Operators
    EQ = 190              # =
    NE = 191              # <>
    LT = 192              # <
    LE = 193              # <=
    GT = 194              # >
    GE = 195              # >=
    PLUS = 196            # +
    MINUS = 197           # -
    STAR = 198            # *
    SLASH = 199           # /
    POWER = 200           # **


KEYWORDS_MAP: dict[str, TokenType] = {
    "PROGRAM": TokenType.KEYWORD_PROGRAM,
    "END_PROGRAM": TokenType.KEYWORD_END_PROGRAM,
    "FUNCTION_BLOCK": TokenType.KEYWORD_FUNCTION_BLOCK,
    "END_FUNCTION_BLOCK": TokenType.KEYWORD_END_FUNCTION_BLOCK,
    "FUNCTION": TokenType.KEYWORD_FUNCTION,
    "END_FUNCTION": TokenType.KEYWORD_END_FUNCTION,
    "METHOD": TokenType.KEYWORD_METHOD,
    "END_METHOD": TokenType.KEYWORD_END_METHOD,
    "PROPERTY": TokenType.KEYWORD_PROPERTY,
    "END_PROPERTY": TokenType.KEYWORD_END_PROPERTY,
    "ACTION": TokenType.KEYWORD_ACTION,
    "END_ACTION": TokenType.KEYWORD_END_ACTION,
    "INTERFACE": TokenType.KEYWORD_INTERFACE,
    "END_INTERFACE": TokenType.KEYWORD_END_INTERFACE,
    "VAR": TokenType.KEYWORD_VAR,
    "VAR_INPUT": TokenType.KEYWORD_VAR_INPUT,
    "VAR_OUTPUT": TokenType.KEYWORD_VAR_OUTPUT,
    "VAR_IN_OUT": TokenType.KEYWORD_VAR_IN_OUT,
    "VAR_GLOBAL": TokenType.KEYWORD_VAR_GLOBAL,
    "VAR_TEMP": TokenType.KEYWORD_VAR_TEMP,
    "VAR_STAT": TokenType.KEYWORD_VAR_STAT,
    "VAR_INST": TokenType.KEYWORD_VAR_INST,
    "VAR_CONFIG": TokenType.KEYWORD_VAR_CONFIG,
    "VAR_EXTERNAL": TokenType.KEYWORD_VAR_EXTERNAL,
    "VAR_GENERIC": TokenType.KEYWORD_VAR_GENERIC,
    "NON_RETAIN": TokenType.KEYWORD_NON_RETAIN,
    "READ_ONLY": TokenType.KEYWORD_READ_ONLY,
    "READ_WRITE": TokenType.KEYWORD_READ_WRITE,
    "END_VAR": TokenType.KEYWORD_END_VAR,
    "CONSTANT": TokenType.KEYWORD_CONSTANT,
    "RETAIN": TokenType.KEYWORD_RETAIN,
    "PERSISTENT": TokenType.KEYWORD_PERSISTENT,
    "AT": TokenType.KEYWORD_AT,
    "TYPE": TokenType.KEYWORD_TYPE,
    "END_TYPE": TokenType.KEYWORD_END_TYPE,
    "STRUCT": TokenType.KEYWORD_STRUCT,
    "END_STRUCT": TokenType.KEYWORD_END_STRUCT,
    "UNION": TokenType.KEYWORD_UNION,
    "END_UNION": TokenType.KEYWORD_END_UNION,
    "ARRAY": TokenType.KEYWORD_ARRAY,
    "OF": TokenType.KEYWORD_OF,
    "POINTER": TokenType.KEYWORD_POINTER,
    "REFERENCE": TokenType.KEYWORD_REFERENCE,
    "EXTENDS": TokenType.KEYWORD_EXTENDS,
    "IMPLEMENTS": TokenType.KEYWORD_IMPLEMENTS,
    "ABSTRACT": TokenType.KEYWORD_ABSTRACT,
    "FINAL": TokenType.KEYWORD_FINAL,
    "PUBLIC": TokenType.KEYWORD_PUBLIC,
    "PROTECTED": TokenType.KEYWORD_PROTECTED,
    "PRIVATE": TokenType.KEYWORD_PRIVATE,
    "INTERNAL": TokenType.KEYWORD_INTERNAL,
    "THIS": TokenType.KEYWORD_THIS,
    "SUPER": TokenType.KEYWORD_SUPER,
    "IF": TokenType.KEYWORD_IF,
    "THEN": TokenType.KEYWORD_THEN,
    "ELSIF": TokenType.KEYWORD_ELSIF,
    "ELSE": TokenType.KEYWORD_ELSE,
    "END_IF": TokenType.KEYWORD_END_IF,
    "CASE": TokenType.KEYWORD_CASE,
    "END_CASE": TokenType.KEYWORD_END_CASE,
    "FOR": TokenType.KEYWORD_FOR,
    "TO": TokenType.KEYWORD_TO,
    "BY": TokenType.KEYWORD_BY,
    "DO": TokenType.KEYWORD_DO,
    "END_FOR": TokenType.KEYWORD_END_FOR,
    "WHILE": TokenType.KEYWORD_WHILE,
    "END_WHILE": TokenType.KEYWORD_END_WHILE,
    "REPEAT": TokenType.KEYWORD_REPEAT,
    "UNTIL": TokenType.KEYWORD_UNTIL,
    "END_REPEAT": TokenType.KEYWORD_END_REPEAT,
    "RETURN": TokenType.KEYWORD_RETURN,
    "EXIT": TokenType.KEYWORD_EXIT,
    "CONTINUE": TokenType.KEYWORD_CONTINUE,
    "JMP": TokenType.KEYWORD_JMP,
    "AND": TokenType.KEYWORD_AND,
    "OR": TokenType.KEYWORD_OR,
    "XOR": TokenType.KEYWORD_XOR,
    "NOT": TokenType.KEYWORD_NOT,
    "MOD": TokenType.KEYWORD_MOD,
    "AND_THEN": TokenType.KEYWORD_AND_THEN,
    "OR_ELSE": TokenType.KEYWORD_OR_ELSE,
    "ADR": TokenType.KEYWORD_ADR,
    "SIZEOF": TokenType.KEYWORD_SIZEOF,
    "REF": TokenType.KEYWORD_REF,
    "__NEW": TokenType.KEYWORD_NEW,
    "__DELETE": TokenType.KEYWORD_DELETE,
    "__TRY": TokenType.KEYWORD_TRY,
    "__CATCH": TokenType.KEYWORD_CATCH,
    "__FINALLY": TokenType.KEYWORD_FINALLY,
    "__ENDTRY": TokenType.KEYWORD_ENDTRY,
    "__QUERYINTERFACE": TokenType.KEYWORD_QUERYINTERFACE,
    "__QUERYPOINTER": TokenType.KEYWORD_QUERYPOINTER,
    "__ISVALIDREF": TokenType.KEYWORD_ISVALIDREF,
    "__VARINFO": TokenType.KEYWORD_VARINFO,
    "__POUNAME": TokenType.KEYWORD_POUNAME,
    "__POSITION": TokenType.KEYWORD_POSITION,
    "BITADR": TokenType.KEYWORD_BITADR,
    "ADRREF": TokenType.KEYWORD_ADRREF,
    "XSIZEOF": TokenType.KEYWORD_XSIZEOF,
    "INDEXOF": TokenType.KEYWORD_INDEXOF,
    "EXPT": TokenType.KEYWORD_EXPT,
    "LOWER_BOUND": TokenType.KEYWORD_LOWER_BOUND,
    "UPPER_BOUND": TokenType.KEYWORD_UPPER_BOUND,
    "TRUE": TokenType.BOOL_LITERAL,
    "FALSE": TokenType.BOOL_LITERAL,
}


@dataclass(frozen=True, slots=True)
class Token:
    """Individual source token with exact span, channel, and trivia attachments."""
    type: TokenType
    value: str
    span: SourceSpan
    channel: TokenChannel = TokenChannel.DEFAULT
    leading_trivia: Tuple[Token, ...] = field(default_factory=tuple)
    trailing_trivia: Tuple[Token, ...] = field(default_factory=tuple)

    @property
    def is_trivia(self) -> bool:
        return self.channel == TokenChannel.TRIVIA

    def __repr__(self) -> str:
        return f"<{self.type.name} '{self.value}' at {self.span}>"
