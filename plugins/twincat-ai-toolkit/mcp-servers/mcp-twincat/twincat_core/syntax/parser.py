"""Main parsing API for IEC 61131-3 ST Declarations and Implementation Bodies."""
from __future__ import annotations

from typing import List, Optional, Tuple

from .ast import AstNode, PouDecl, Statement, TypeDecl, VarBlock
from .cst import CstNode
from .diagnostics import SyntaxDiagnostic
from .lexer import Lexer
from .parser_declarations import DeclarationParser
from .parser_statements import StatementParser
from .tokens import Token


def parse_declaration(source: str) -> tuple[Optional[AstNode], list[CstNode], list[SyntaxDiagnostic]]:
    """Parse an ST declaration string (POU, METHOD, PROPERTY, TYPE, INTERFACE, or GVL VAR blocks).

    Returns:
        (ast_root, cst_nodes, diagnostics)
    """
    lexer = Lexer(source)
    tokens = lexer.tokenize_all(include_trivia=True)
    parser = DeclarationParser(tokens, lexer.diagnostics)
    ast_root, cst_nodes = parser.parse_declaration_file()
    return ast_root, cst_nodes, parser.diagnostics


def parse_implementation(source: str) -> tuple[list[Statement], list[CstNode], list[SyntaxDiagnostic]]:
    """Parse an ST implementation code body (statements and expressions).

    Returns:
        (statements, cst_nodes, diagnostics)
    """
    lexer = Lexer(source)
    tokens = lexer.tokenize_all(include_trivia=True)
    parser = StatementParser(tokens, lexer.diagnostics)
    statements, cst_nodes = parser.parse_statements()
    return statements, cst_nodes, parser.diagnostics
