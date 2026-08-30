"""TwinCAT Language Server implementation using pygls and twincat_core."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

import lsprotocol.types as lsp
from pygls.lsp.server import LanguageServer

from ..project.workspace_index import WorkspaceIndex
from .handlers import (
    get_diagnostics_for_file,
    handle_completion,
    handle_definition,
    handle_document_symbol,
    handle_formatting,
    handle_hover,
    handle_implementation,
    handle_virtual_st_get,
    handle_virtual_st_map_location,
    handle_virtual_st_save,
)
from .utils import uri_to_path

logger = logging.getLogger("twincat-lsp")


def _get_param(params: Any, key: str, default: Any = None) -> Any:
    """Safely extract parameter from dict, pygls Object, dataclass, or namespace."""
    if params is None:
        return default
    if isinstance(params, dict):
        return params.get(key, default)
    if hasattr(params, key):
        val = getattr(params, key)
        return val if val is not None else default
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower()
    if hasattr(params, snake):
        val = getattr(params, snake)
        return val if val is not None else default
    camel = "".join(word.capitalize() if i > 0 else word for i, word in enumerate(key.split("_")))
    if hasattr(params, camel):
        val = getattr(params, camel)
        return val if val is not None else default
    return default


class TwinCatLanguageServer(LanguageServer):
    """LSP Server for TwinCAT 3 Structured Text and XML files (thin adapter over twincat_core)."""

    def __init__(
        self,
        name: str = "twincat-lsp",
        version: str = "0.1.0",
        workspace_index: Optional[WorkspaceIndex] = None,
    ) -> None:
        super().__init__(name=name, version=version)
        self.workspace_index = workspace_index or WorkspaceIndex()
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        @self.feature(lsp.INITIALIZE)
        def on_initialize(params: lsp.InitializeParams) -> lsp.InitializeResult:
            root_path = None
            if params.root_uri:
                root_path = uri_to_path(params.root_uri)
            elif params.workspace_folders:
                root_path = uri_to_path(params.workspace_folders[0].uri)

            if root_path and root_path.exists():
                self._load_workspace(root_path)

            return lsp.InitializeResult(
                capabilities=lsp.ServerCapabilities(
                    text_document_sync=lsp.TextDocumentSyncOptions(
                        open_close=True,
                        change=lsp.TextDocumentSyncKind.Full,
                    ),
                    document_formatting_provider=True,
                    definition_provider=True,
                    implementation_provider=True,
                    hover_provider=True,
                    completion_provider=lsp.CompletionOptions(
                        trigger_characters=[".", "^", ":"],
                        resolve_provider=False,
                    ),
                    document_symbol_provider=True,
                )
            )

        @self.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
        def on_did_open(params: lsp.DidOpenTextDocumentParams) -> None:
            file_path = uri_to_path(params.text_document.uri)
            text = params.text_document.text
            self.workspace_index.update_file(file_path, text=text)
            self._publish_diagnostics(params.text_document.uri, file_path)

        @self.feature(lsp.TEXT_DOCUMENT_DID_CHANGE)
        def on_did_change(params: lsp.DidChangeTextDocumentParams) -> None:
            file_path = uri_to_path(params.text_document.uri)
            try:
                doc = self.workspace.get_text_document(params.text_document.uri)
                text = doc.source
            except Exception:
                text = params.content_changes[0].text if params.content_changes else None

            if text is not None:
                self.workspace_index.update_file(file_path, text=text)
                self._publish_diagnostics(params.text_document.uri, file_path)

        @self.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
        def on_did_close(params: lsp.DidCloseTextDocumentParams) -> None:
            file_path = uri_to_path(params.text_document.uri)
            # Re-read from disk if still on disk
            if file_path.exists():
                self.workspace_index.update_file(file_path)

        @self.feature(lsp.TEXT_DOCUMENT_FORMATTING)
        def on_formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit]:
            try:
                doc = self.workspace.get_text_document(params.text_document.uri)
                unsaved = doc.source
            except Exception:
                unsaved = None
            return handle_formatting(self.workspace_index, params, unsaved_text=unsaved)

        @self.feature(lsp.TEXT_DOCUMENT_DEFINITION)
        def on_definition(params: lsp.DefinitionParams) -> Optional[lsp.Location]:
            return handle_definition(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_IMPLEMENTATION)
        def on_implementation(params: lsp.ImplementationParams) -> Optional[lsp.Location]:
            return handle_implementation(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_HOVER)
        def on_hover(params: lsp.HoverParams) -> Optional[lsp.Hover]:
            return handle_hover(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_COMPLETION)
        def on_completion(params: lsp.CompletionParams) -> lsp.CompletionList:
            return handle_completion(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
        def on_document_symbol(params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol]:
            return handle_document_symbol(self.workspace_index, params)

        @self.feature("twincat/virtualSt/get")
        def on_virtual_st_get(params: Any) -> dict:
            uri = _get_param(params, "uri", "")
            return handle_virtual_st_get(self.workspace_index, uri)

        @self.feature("twincat/virtualSt/save")
        def on_virtual_st_save(params: Any) -> dict:
            uri = _get_param(params, "uri", "")
            virtual_st = _get_param(params, "virtualSt", "") or _get_param(params, "virtual_st", "")
            return handle_virtual_st_save(self.workspace_index, uri, virtual_st)

        @self.feature("twincat/virtualSt/mapLocation")
        def on_virtual_st_map_location(params: Any) -> dict:
            uri = _get_param(params, "uri", "")
            line = int(_get_param(params, "line", 1))
            col = int(_get_param(params, "col", 1))
            direction = _get_param(params, "direction", "toXml")
            return handle_virtual_st_map_location(self.workspace_index, uri, line, col, direction)

    def _publish_diagnostics(self, uri: str, file_path: Path) -> None:
        """Publish diagnostics to client for given file."""
        diags = get_diagnostics_for_file(self.workspace_index, file_path)
        self.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(uri=uri, diagnostics=diags)
        )

    def _load_workspace(self, root_path: Path) -> None:
        """Discover .plcproj projects or index TwinCAT files in workspace."""
        plcproj_files = list(root_path.glob("**/*.plcproj"))
        if plcproj_files:
            try:
                self.workspace_index = WorkspaceIndex.from_plcproj(plcproj_files[0])
                self.workspace_index.index_all_project_files()
                logger.info(f"Initialized WorkspaceIndex from {plcproj_files[0]}")
                return
            except Exception as e:
                logger.warning(f"Could not load .plcproj: {e}")

        # Index all .Tc* files under root
        for ext in ("*.TcPOU", "*.TcDUT", "*.TcGVL", "*.TcIO"):
            for f in root_path.glob(f"**/{ext}"):
                try:
                    self.workspace_index.update_file(f)
                except Exception:
                    pass


def create_lsp_server(workspace_index: Optional[WorkspaceIndex] = None) -> TwinCatLanguageServer:
    """Factory creating an initialized TwinCAT Language Server."""
    return TwinCatLanguageServer(workspace_index=workspace_index)
