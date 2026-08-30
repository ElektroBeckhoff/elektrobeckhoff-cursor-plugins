"""Integration tests for pygls LSP handlers against real Solution files."""
from __future__ import annotations

from pathlib import Path
import pytest
from lsprotocol import types as lsp

from twincat_core.lsp.handlers import (
    handle_document_symbol,
    handle_formatting,
    handle_definition,
    handle_hover,
)
from twincat_core.lsp.utils import path_to_uri


class TestSolutionLspHandlers:
    """Verifies that LSP handlers function properly on real solution POUs."""

    def test_lsp_document_symbols_on_solution_pou(self, solution_workspace, solution_paths):
        pou_file = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        params = lsp.DocumentSymbolParams(text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)))
        symbols = handle_document_symbol(solution_workspace, params)
        assert len(symbols) > 0
        symbol_names = [s.name for s in symbols]
        assert any("FB_Syntax_Derived" in s.name for s in symbols)

    def test_lsp_formatting_on_solution_pou(self, solution_workspace, solution_paths):
        pou_file = solution_paths["syntax_dir"] / "FB_Syntax_Derived.TcPOU"
        params = lsp.DocumentFormattingParams(
            text_document=lsp.TextDocumentIdentifier(uri=path_to_uri(pou_file)),
            options=lsp.FormattingOptions(tab_size=4, insert_spaces=True),
        )
        edits = handle_formatting(solution_workspace, params)
        assert edits is not None
        assert isinstance(edits, list)
