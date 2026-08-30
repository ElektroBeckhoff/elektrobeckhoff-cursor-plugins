"""LSP utility functions and converters between twincat_core and lsprotocol types."""
from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from typing import Optional, Union

import lsprotocol.types as lsp

from ..semantic.symbols import Symbol, SymbolKind
from ..syntax.diagnostics import DiagnosticSeverity, SyntaxDiagnostic
from ..syntax.span import Position, SourceSpan, offset_to_line_col
from ..xml.types import CdataSpan


def uri_to_path(uri: str) -> Path:
    """Convert an LSP document URI to a resolved local Path."""
    parsed = urllib.parse.urlparse(uri)
    path_str = urllib.parse.unquote(parsed.path)
    if os.name == "nt" and path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
        path_str = path_str[1:]
    return Path(path_str).resolve()


def path_to_uri(path: Union[Path, str]) -> str:
    """Convert a local Path or string path to an LSP file:// URI."""
    p = Path(path).resolve()
    return p.as_uri()


def position_to_lsp(pos: Position) -> lsp.Position:
    """Convert 1-based core Position to 0-based LSP Position."""
    return lsp.Position(
        line=max(0, pos.line - 1),
        character=max(0, pos.col - 1),
    )


def position_from_lsp(lsp_pos: lsp.Position) -> Position:
    """Convert 0-based LSP Position to 1-based core Position."""
    return Position(
        line=lsp_pos.line + 1,
        col=lsp_pos.character + 1,
        offset=0,
    )


def span_to_range(span: SourceSpan) -> lsp.Range:
    """Convert core SourceSpan to LSP Range."""
    return lsp.Range(
        start=position_to_lsp(span.start),
        end=position_to_lsp(span.end),
    )


def range_to_span(r: lsp.Range) -> SourceSpan:
    """Convert LSP Range to core SourceSpan."""
    return SourceSpan(
        start=position_from_lsp(r.start),
        end=position_from_lsp(r.end),
    )


DIAGNOSTIC_SEVERITY_MAP = {
    DiagnosticSeverity.ERROR: lsp.DiagnosticSeverity.Error,
    DiagnosticSeverity.WARNING: lsp.DiagnosticSeverity.Warning,
    DiagnosticSeverity.INFO: lsp.DiagnosticSeverity.Information,
    DiagnosticSeverity.HINT: lsp.DiagnosticSeverity.Hint,
}


def diagnostic_to_lsp(diag: SyntaxDiagnostic) -> lsp.Diagnostic:
    """Convert core SyntaxDiagnostic to LSP Diagnostic."""
    return lsp.Diagnostic(
        range=span_to_range(diag.span),
        message=diag.message,
        severity=DIAGNOSTIC_SEVERITY_MAP.get(diag.severity, lsp.DiagnosticSeverity.Error),
        code=diag.code,
        source="twincat",
    )


SYMBOL_KIND_MAP = {
    SymbolKind.VARIABLE: lsp.SymbolKind.Variable,
    SymbolKind.CONSTANT: lsp.SymbolKind.Constant,
    SymbolKind.POU: lsp.SymbolKind.Class,
    SymbolKind.FUNCTION_BLOCK: lsp.SymbolKind.Class,
    SymbolKind.FUNCTION: lsp.SymbolKind.Function,
    SymbolKind.PROGRAM: lsp.SymbolKind.Module,
    SymbolKind.METHOD: lsp.SymbolKind.Method,
    SymbolKind.PROPERTY: lsp.SymbolKind.Property,
    SymbolKind.ACTION: lsp.SymbolKind.Method,
    SymbolKind.INTERFACE: lsp.SymbolKind.Interface,
    SymbolKind.STRUCT: lsp.SymbolKind.Struct,
    SymbolKind.ENUM: lsp.SymbolKind.Enum,
    SymbolKind.UNION: lsp.SymbolKind.Struct,
    SymbolKind.ALIAS: lsp.SymbolKind.TypeParameter,
    SymbolKind.STRUCT_FIELD: lsp.SymbolKind.Field,
    SymbolKind.ENUM_MEMBER: lsp.SymbolKind.EnumMember,
    SymbolKind.GVL: lsp.SymbolKind.Package,
}


def symbol_to_document_symbol(sym: Symbol) -> lsp.DocumentSymbol:
    """Convert core Symbol to LSP DocumentSymbol."""
    kind = SYMBOL_KIND_MAP.get(sym.kind, lsp.SymbolKind.Variable)
    r = span_to_range(sym.span)
    detail = sym.type_ref or sym.kind.value
    return lsp.DocumentSymbol(
        name=sym.name,
        kind=kind,
        range=r,
        selection_range=r,
        detail=detail,
        children=[],
    )


def cdata_span_to_lsp_location(span: CdataSpan, raw_text: str, file_path: Path) -> lsp.Location:
    """Convert a CdataSpan in raw XML text to an LSP Location pointing to the content body."""
    start_line, start_col = offset_to_line_col(raw_text, span.content_start)
    end_line, end_col = offset_to_line_col(raw_text, span.content_end)

    src_span = SourceSpan.from_bounds(
        start_line=start_line,
        start_col=start_col,
        start_offset=span.content_start,
        end_line=end_line,
        end_col=end_col,
        end_offset=span.content_end,
    )
    return lsp.Location(uri=path_to_uri(file_path), range=span_to_range(src_span))
