"""TwinCAT Language Server (LSP) Adapter."""
from .handlers import (
    get_diagnostics_for_file,
    handle_completion,
    handle_definition,
    handle_document_symbol,
    handle_format_section,
    handle_formatting,
    handle_hover,
    handle_implementation,
    handle_range_formatting,
    handle_type_definition,
)
from .server import TwinCatLanguageServer, create_lsp_server
from .utils import (
    cdata_span_to_lsp_location,
    diagnostic_to_lsp,
    path_to_uri,
    position_from_lsp,
    position_to_lsp,
    range_to_span,
    span_to_range,
    symbol_to_document_symbol,
    uri_to_path,
)

__all__ = [
    "TwinCatLanguageServer",
    "create_lsp_server",
    "uri_to_path",
    "path_to_uri",
    "position_to_lsp",
    "position_from_lsp",
    "span_to_range",
    "range_to_span",
    "cdata_span_to_lsp_location",
    "diagnostic_to_lsp",
    "symbol_to_document_symbol",
    "handle_definition",
    "handle_type_definition",
    "handle_implementation",
    "handle_hover",
    "handle_completion",
    "handle_document_symbol",
    "handle_formatting",
    "handle_range_formatting",
    "handle_format_section",
    "get_diagnostics_for_file",
]
