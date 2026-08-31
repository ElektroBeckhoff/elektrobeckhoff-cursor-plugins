"""TwinCAT Language Server implementation using pygls and twincat_core."""
from __future__ import annotations

import logging
import os
import re
import threading
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
    handle_format_section,
    handle_formatting,
    handle_hover,
    handle_implementation,
    handle_range_formatting,
    handle_type_definition,
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
        if not logging.getLogger().isEnabledFor(logging.DEBUG):
            logging.getLogger("pygls").setLevel(logging.WARNING)
        self.workspace_index = workspace_index or WorkspaceIndex()
        self.workspace_roots: list[Path] = []
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        @self.feature(lsp.INITIALIZE)
        def on_initialize(params: lsp.InitializeParams) -> lsp.InitializeResult:
            # Collect all workspace roots without performing blocking IO during handshake
            self.workspace_roots = []
            if params.workspace_folders:
                for wf in params.workspace_folders:
                    p = uri_to_path(wf.uri)
                    if p.exists() and p not in self.workspace_roots:
                        self.workspace_roots.append(p)
            elif params.root_uri:
                p = uri_to_path(params.root_uri)
                if p.exists() and p not in self.workspace_roots:
                    self.workspace_roots.append(p)

            return lsp.InitializeResult(
                capabilities=lsp.ServerCapabilities(
                    text_document_sync=lsp.TextDocumentSyncOptions(
                        open_close=True,
                        change=lsp.TextDocumentSyncKind.Full,
                    ),
                    document_formatting_provider=True,
                    document_range_formatting_provider=True,
                    definition_provider=True,
                    type_definition_provider=True,
                    implementation_provider=True,
                    hover_provider=True,
                    completion_provider=lsp.CompletionOptions(
                        trigger_characters=[".", "^", ":"],
                        resolve_provider=False,
                    ),
                    document_symbol_provider=True,
                )
            )

        @self.feature(lsp.INITIALIZED)
        def on_initialized(params: lsp.InitializedParams) -> None:
            # Start background asynchronous workspace indexing
            if self.workspace_roots:
                threading.Thread(
                    target=self._background_load_workspaces,
                    daemon=True,
                    name="twincat-workspace-indexer",
                ).start()

        @self.feature(lsp.TEXT_DOCUMENT_DID_OPEN)
        def on_did_open(params: lsp.DidOpenTextDocumentParams) -> None:
            file_path = uri_to_path(params.text_document.uri)
            self._ensure_file_project_indexed(file_path)
            text = params.text_document.text
            self.workspace_index.update_file(file_path, text=text, declaration_only=False)
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
                self.workspace_index.update_file(file_path, text=text, declaration_only=False)
                self._publish_diagnostics(params.text_document.uri, file_path)

        @self.feature(lsp.TEXT_DOCUMENT_DID_CLOSE)
        def on_did_close(params: lsp.DidCloseTextDocumentParams) -> None:
            file_path = uri_to_path(params.text_document.uri)
            # Re-read from disk if still on disk
            if file_path.exists():
                self.workspace_index.update_file(file_path, declaration_only=False)

        @self.feature(lsp.TEXT_DOCUMENT_FORMATTING)
        def on_formatting(params: lsp.DocumentFormattingParams) -> list[lsp.TextEdit]:
            try:
                doc = self.workspace.get_text_document(params.text_document.uri)
                unsaved = doc.source
            except Exception:
                unsaved = None
            return handle_formatting(self.workspace_index, params, unsaved_text=unsaved)

        @self.feature(lsp.TEXT_DOCUMENT_RANGE_FORMATTING)
        def on_range_formatting(params: lsp.DocumentRangeFormattingParams) -> list[lsp.TextEdit]:
            try:
                doc = self.workspace.get_text_document(params.text_document.uri)
                unsaved = doc.source
            except Exception:
                unsaved = None
            return handle_range_formatting(self.workspace_index, params, unsaved_text=unsaved)

        @self.feature("twincat/formatSection")
        def on_format_section(params: Any) -> dict[str, Any]:
            text_doc = _get_param(params, "textDocument") or _get_param(params, "text_document")
            uri = None
            if isinstance(text_doc, dict):
                uri = text_doc.get("uri")
            elif text_doc is not None:
                uri = getattr(text_doc, "uri", None)
            if not uri:
                uri = _get_param(params, "uri")

            if not uri:
                return {"edits": [], "sectionName": "", "success": False}

            pos_data = _get_param(params, "position", {})
            if isinstance(pos_data, dict):
                line = pos_data.get("line", 0)
                character = pos_data.get("character", 0)
            else:
                line = getattr(pos_data, "line", 0)
                character = getattr(pos_data, "character", 0)

            lsp_pos = lsp.Position(line=line, character=character)

            try:
                doc = self.workspace.get_text_document(uri)
                unsaved = doc.source
            except Exception:
                unsaved = None

            file_path = uri_to_path(uri)
            return handle_format_section(self.workspace_index, file_path, lsp_pos, unsaved_text=unsaved)

        @self.feature(lsp.TEXT_DOCUMENT_DEFINITION)
        def on_definition(params: lsp.DefinitionParams) -> Optional[lsp.Location]:
            file_path = uri_to_path(params.text_document.uri)
            self._ensure_file_project_indexed(file_path)
            return handle_definition(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_TYPE_DEFINITION)
        def on_type_definition(params: lsp.TypeDefinitionParams) -> Optional[lsp.Location]:
            file_path = uri_to_path(params.text_document.uri)
            self._ensure_file_project_indexed(file_path)
            return handle_type_definition(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_IMPLEMENTATION)
        def on_implementation(params: lsp.ImplementationParams) -> Optional[lsp.Location]:
            file_path = uri_to_path(params.text_document.uri)
            self._ensure_file_project_indexed(file_path)
            return handle_implementation(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_HOVER)
        def on_hover(params: lsp.HoverParams) -> Optional[lsp.Hover]:
            file_path = uri_to_path(params.text_document.uri)
            self._ensure_file_project_indexed(file_path)
            return handle_hover(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_COMPLETION)
        def on_completion(params: lsp.CompletionParams) -> lsp.CompletionList:
            file_path = uri_to_path(params.text_document.uri)
            self._ensure_file_project_indexed(file_path)
            return handle_completion(self.workspace_index, params)

        @self.feature(lsp.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
        def on_document_symbol(params: lsp.DocumentSymbolParams) -> list[lsp.DocumentSymbol]:
            file_path = uri_to_path(params.text_document.uri)
            self._ensure_file_project_indexed(file_path)
            return handle_document_symbol(self.workspace_index, params)

    def _publish_diagnostics(self, uri: str, file_path: Path) -> None:
        """Publish diagnostics to client for given file."""
        diags = get_diagnostics_for_file(self.workspace_index, file_path)
        self.text_document_publish_diagnostics(
            lsp.PublishDiagnosticsParams(uri=uri, diagnostics=diags)
        )

    def _ensure_file_project_indexed(self, file_path: Path) -> None:
        """Ensure the enclosing .plcproj and sibling TwinCAT files are indexed for a newly opened or hovered file."""
        if not file_path.exists():
            return
        curr = file_path.parent
        for _ in range(8):
            if not curr or curr == curr.parent:
                break
            try:
                plcprojs = [p for p in curr.iterdir() if p.is_file() and p.suffix.lower() == ".plcproj"]
                if plcprojs:
                    for p in plcprojs:
                        self.workspace_index.add_plcproj(p)
                    break
            except Exception:
                pass
            curr = curr.parent

    def _background_load_workspaces(self) -> None:
        """Background thread target to load all workspace roots."""
        for root in self.workspace_roots:
            try:
                self._load_workspace(root)
            except Exception as e:
                logger.warning(f"Error loading workspace root {root}: {e}")

    def _load_workspace(self, root_path: Path) -> None:
        """Discover all .plcproj projects or index TwinCAT files in workspace using fast pruned walk."""
        plcproj_files: list[Path] = []
        tc_files: list[Path] = []
        ignore_dirs = {
            ".git", "node_modules", ".venv", "venv", "dist", "build",
            ".vs", ".pytest_cache", "bin", "obj", "__pycache__", ".logs",
        }

        for dirpath, dirnames, filenames in os.walk(root_path):
            dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]
            for f in filenames:
                ext = Path(f).suffix.lower()
                if ext == ".plcproj":
                    plcproj_files.append(Path(dirpath) / f)
                elif ext in (".tcpou", ".tcdut", ".tcgvl", ".tcio"):
                    tc_files.append(Path(dirpath) / f)

        # 1. Index PLC projects first
        for p in plcproj_files:
            try:
                self.workspace_index.add_plcproj(p)
                logger.info(f"Indexed PLC project: {p}")
            except Exception as e:
                logger.warning(f"Could not load .plcproj {p}: {e}")

        # 2. Index standalone .Tc* files not belonging to any .plcproj
        for f in tc_files:
            if f.resolve() not in self.workspace_index.indexed_files:
                try:
                    self.workspace_index.update_file(f, declaration_only=True)
                except Exception:
                    pass
        logger.info(f"Workspace indexing complete for {root_path}: {len(self.workspace_index.indexed_files)} files indexed.")


def create_lsp_server(workspace_index: Optional[WorkspaceIndex] = None) -> TwinCatLanguageServer:
    """Factory creating an initialized TwinCAT Language Server."""
    return TwinCatLanguageServer(workspace_index=workspace_index)
