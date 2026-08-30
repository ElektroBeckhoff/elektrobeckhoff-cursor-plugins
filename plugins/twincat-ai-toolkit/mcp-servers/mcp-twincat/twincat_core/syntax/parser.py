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


def validate_st_syntax_in_xml(xml_source: str) -> list[str]:
    """Parse all declaration and implementation CDATA blocks in an XML string and return fatal syntax errors.

    Fast, headless validator used as a safety gate before and after file operations (formatting, migration, docs).
    """
    from ..xml.reader import read_tc_xml
    from .diagnostics import DiagnosticSeverity

    syntax_errors: list[str] = []
    try:
        doc = read_tc_xml(xml_source)
        for span in doc.cdata_spans:
            if not span.content.strip():
                continue
            if span.is_declaration:
                _, _, diags = parse_declaration(span.content)
                for d in diags:
                    if d.severity == DiagnosticSeverity.ERROR:
                        syntax_errors.append(f"Declaration error: {d.message} (line {d.span.start.line})")
            elif span.is_implementation:
                _, _, diags = parse_implementation(span.content)
                for d in diags:
                    if d.severity == DiagnosticSeverity.ERROR:
                        syntax_errors.append(f"Implementation error: {d.message} (line {d.span.start.line})")
    except Exception as exc:
        syntax_errors.append(f"XML parse error: {exc}")
    return syntax_errors

