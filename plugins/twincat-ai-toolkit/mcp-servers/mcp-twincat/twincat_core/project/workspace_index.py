"""Incremental Workspace Index integrating XML, Syntax AST/CST, and Semantic Resolution."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..semantic.resolver import SymbolResolver
from ..semantic.scopes import Scope, ScopeKind
from ..semantic.symbol_table import SymbolTable
from ..semantic.symbols import Symbol, SymbolKind
from ..semantic.type_index import TypeDescriptor, TypeIndex
from ..syntax.ast import (
    AstNode,
    EnumType,
    InterfaceDecl,
    MethodDecl,
    PouDecl,
    PropertyDecl,
    StructType,
    TypeDecl,
    UnionType,
    VarBlock,
    VarDecl,
    Statement,
)
from ..syntax.cst import CstNode
from ..syntax.diagnostics import SyntaxDiagnostic
from ..syntax.parser import parse_declaration, parse_implementation
from ..syntax.span import SourceSpan, offset_to_line_col
from ..xml.reader import read_tc_xml, read_tc_xml_file
from ..xml.types import CdataKind, CdataSpan, TcXmlDocument
from .plcproj_parser import parse_plcproj_file
from .project_graph import CompileItem, PlcProject


@dataclass(slots=True)
class IndexedFile:
    """Cached parsing and semantic indexing output for a single file."""
    file_path: Path
    content_hash: str
    xml_doc: TcXmlDocument
    top_level_ast: Optional[AstNode] = None
    cst_nodes: list[CstNode] = field(default_factory=list)
    diagnostics: list[SyntaxDiagnostic] = field(default_factory=list)
    declared_symbols: list[Symbol] = field(default_factory=list)
    implementation_statements: list[tuple[CdataSpan, Scope, list[Statement]]] = field(default_factory=list)
    has_full_implementation: bool = False


class WorkspaceIndex:
    """Project-wide incremental index for TwinCAT 3 source files."""

    def __init__(self, project: Optional[PlcProject] = None) -> None:
        self.project: Optional[PlcProject] = project
        self.projects: list[PlcProject] = [project] if project else []
        self._indexed_plcprojs: set[Path] = set()
        self.type_index = TypeIndex()
        self.symbol_table = SymbolTable()
        self.resolver = SymbolResolver(self.symbol_table, self.type_index)
        self.indexed_files: dict[Path, IndexedFile] = {}
        if self.project:
            self._register_project_libraries(self.project)
            if self.project.project_path:
                self._indexed_plcprojs.add(self.project.project_path.resolve())

    def _register_project_libraries(self, project: Optional[PlcProject] = None) -> None:
        proj = project or self.project
        if not proj:
            return
        for lib in proj.library_references:
            lib_name = lib.name.split(",")[0].strip()
            if lib.namespace:
                self.type_index.register_library_type(lib.namespace, lib_name)
            self.type_index.register_library_type(lib_name, lib_name)

    def add_plcproj(self, plcproj_path: Path) -> None:
        """Parse a .plcproj and index all its compile items and library references."""
        p = plcproj_path.resolve()
        if p in self._indexed_plcprojs:
            return
        self._indexed_plcprojs.add(p)
        try:
            proj = parse_plcproj_file(p)
            if not self.project:
                self.project = proj
            self.projects.append(proj)
            self._register_project_libraries(proj)

            # Prioritize DUTs and GVLs first so all types and globals are registered
            duts_gvls = []
            pous_itfs = []
            for item in proj.compile_items.values():
                if item.exclude_from_build or not item.abs_path.is_file():
                    continue
                itype = item.item_type.lower()
                if itype in ("tcdut", "tcgvl"):
                    duts_gvls.append(item)
                elif itype in ("tcpou", "tcio"):
                    pous_itfs.append(item)

            for item in duts_gvls:
                try:
                    self.update_file(item.abs_path, declaration_only=True)
                except Exception:
                    continue

            for item in pous_itfs:
                try:
                    self.update_file(item.abs_path, declaration_only=True)
                except Exception:
                    continue
        except Exception:
            pass

    @classmethod
    def from_plcproj(cls, plcproj_path: Path) -> "WorkspaceIndex":
        """Construct and index an entire PLC project from its .plcproj file."""
        project = parse_plcproj_file(plcproj_path)
        index = cls(project=project)
        index.index_all_project_files()
        return index

    def index_all_project_files(self) -> None:
        """Scan and index all compile items in the current project."""
        if not self.project:
            return

        for item in self.project.compile_items.values():
            if item.exclude_from_build:
                continue
            if item.abs_path.is_file() and item.item_type.lower() in ("tcpou", "tcdut", "tcgvl", "tcio"):
                try:
                    self.update_file(item.abs_path, declaration_only=True)
                except Exception as ex:
                    # Log or record diagnostic, don't crash entire indexing
                    continue

    def update_file(
        self,
        file_path: Path,
        text: Optional[str] = None,
        declaration_only: bool = False,
    ) -> IndexedFile:
        """Incrementally index or re-index a single TwinCAT file."""
        path = file_path.resolve()

        if text is None:
            xml_doc = read_tc_xml_file(path)
            content_bytes = xml_doc.raw_text.encode("utf-8")
        else:
            xml_doc = read_tc_xml(text, file_path=path)
            content_bytes = text.encode("utf-8")

        chash = hashlib.sha256(content_bytes).hexdigest()

        # Check cache
        if path in self.indexed_files:
            existing = self.indexed_files[path]
            if existing.content_hash == chash:
                if declaration_only or existing.has_full_implementation:
                    return existing

        # Remove old symbols and types associated with this file
        self.remove_file(path)

        declared_symbols: list[Symbol] = []
        all_cst_nodes: list[CstNode] = []
        all_diags: list[SyntaxDiagnostic] = []
        top_level_ast: Optional[AstNode] = None

        active_pou_symbol: Optional[Symbol] = None
        active_pou_scope: Optional[Scope] = None
        active_pou_type_desc: Optional[TypeDescriptor] = None
        method_scopes: dict[str, Scope] = {}
        property_scopes: dict[str, Scope] = {}
        implementation_statements: list[tuple[CdataSpan, Scope, list[Statement]]] = []

        default_span = SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)

        for span in xml_doc.cdata_spans:
            if not span.content.strip():
                continue

            cdata_start_line, cdata_start_col = offset_to_line_col(xml_doc.raw_text, span.content_start)
            line_offset = cdata_start_line - 1
            col_offset = cdata_start_col - 1
            char_offset = span.content_start

            # 1. Top-Level POU / DUT / GVL / ITF Declarations
            if span.kind in (
                CdataKind.POU_DECLARATION,
                CdataKind.DUT_DECLARATION,
                CdataKind.GVL_DECLARATION,
                CdataKind.ITF_DECLARATION,
            ):
                ast_node, cst_nodes, diags = parse_declaration(span.content)
                all_cst_nodes.extend(cst_nodes)
                all_diags.extend(
                    SyntaxDiagnostic(d.message, d.span.offset_by(line_offset, col_offset, char_offset), d.severity, d.code)
                    for d in diags
                )
                if top_level_ast is None:
                    top_level_ast = ast_node

                node_span = ast_node.span.offset_by(line_offset, col_offset, char_offset) if ast_node and ast_node.span else default_span

                if isinstance(ast_node, PouDecl):
                    kind_map = {
                        "FUNCTION_BLOCK": SymbolKind.FUNCTION_BLOCK,
                        "FUNCTION": SymbolKind.FUNCTION,
                        "PROGRAM": SymbolKind.PROGRAM,
                        "GVL": SymbolKind.GVL,
                    }
                    p_kind = kind_map.get(ast_node.pou_type.upper(), SymbolKind.POU)
                    if span.kind == CdataKind.GVL_DECLARATION:
                        p_kind = SymbolKind.GVL

                    if p_kind == SymbolKind.GVL:
                        name = xml_doc.root_object_name or (ast_node.name if ast_node.name and ast_node.name.upper() != "GVL" else "") or path.stem
                    else:
                        name = ast_node.name or xml_doc.root_object_name or path.stem

                    pou_sym = Symbol(
                        name=name,
                        kind=p_kind,
                        span=node_span,
                        file_path=path,
                        type_ref=ast_node.return_type,
                        access=ast_node.access_modifier,
                        doc_comment=ast_node.comment,
                        is_abstract=ast_node.is_abstract,
                    )
                    self.symbol_table.define_global(pou_sym)
                    declared_symbols.append(pou_sym)

                    active_pou_symbol = pou_sym
                    if p_kind == SymbolKind.GVL:
                        active_pou_scope = self.symbol_table.create_gvl_scope(pou_sym, path)
                    else:
                        active_pou_scope = self.symbol_table.create_pou_scope(pou_sym, path)

                    # Register in TypeIndex
                    type_desc = TypeDescriptor(
                        name=name,
                        kind=p_kind,
                        extends_name=ast_node.extends_name,
                        implements_names=ast_node.implements_names,
                        file_path=path,
                        symbol=pou_sym,
                        is_abstract=ast_node.is_abstract,
                    )
                    active_pou_type_desc = type_desc

                    # Register variables in POU / GVL
                    for v_block in ast_node.var_blocks:
                        for v in v_block.variables:
                            v_sym = Symbol(
                                name=v.name,
                                kind=SymbolKind.VARIABLE,
                                span=v.span.offset_by(line_offset, col_offset, char_offset) if v.span else node_span,
                                file_path=path,
                                type_ref=v.type_name,
                                is_constant=v_block.is_constant or v.is_constant,
                                is_retain=v_block.is_retain or v.is_retain,
                                is_persistent=v_block.is_persistent or v.is_persistent,
                                initial_value=v.initial_value,
                                address=v.address,
                                parent_symbol=pou_sym,
                                doc_comment=v.comment,
                                var_block_type=v_block.block_type.upper() if getattr(v_block, "block_type", None) else "VAR",
                            )
                            active_pou_scope.define(v_sym)
                            type_desc.add_field(v_sym)
                            declared_symbols.append(v_sym)

                    self.type_index.register_type(type_desc)

                elif isinstance(ast_node, TypeDecl):
                    name = ast_node.name or xml_doc.root_object_name or path.stem
                    type_sym = Symbol(
                        name=name,
                        kind=SymbolKind.STRUCT if isinstance(ast_node.definition, StructType) else SymbolKind.ENUM,
                        span=node_span,
                        file_path=path,
                        doc_comment=ast_node.comment,
                    )
                    self.symbol_table.define_global(type_sym)
                    declared_symbols.append(type_sym)

                    if isinstance(ast_node.definition, StructType):
                        s_desc = TypeDescriptor(
                            name=name,
                            kind=SymbolKind.STRUCT,
                            extends_name=ast_node.definition.extends_type or ast_node.extends_type,
                            file_path=path,
                            symbol=type_sym,
                        )
                        for f in ast_node.definition.fields:
                            f_sym = Symbol(
                                name=f.name,
                                kind=SymbolKind.STRUCT_FIELD,
                                span=f.span.offset_by(line_offset, col_offset, char_offset) if f.span else node_span,
                                file_path=path,
                                type_ref=f.type_name,
                                initial_value=f.initial_value,
                                parent_symbol=type_sym,
                                doc_comment=f.comment,
                                var_block_type="STRUCT_FIELD",
                            )
                            s_desc.add_field(f_sym)
                            declared_symbols.append(f_sym)
                        self.type_index.register_type(s_desc)

                    elif isinstance(ast_node.definition, EnumType):
                        e_desc = TypeDescriptor(
                            name=name,
                            kind=SymbolKind.ENUM,
                            base_type_name=ast_node.definition.base_type,
                            file_path=path,
                            symbol=type_sym,
                        )
                        for m in ast_node.definition.members:
                            m_sym = Symbol(
                                name=m.name,
                                kind=SymbolKind.ENUM_MEMBER,
                                span=m.span.offset_by(line_offset, col_offset, char_offset) if m.span else node_span,
                                file_path=path,
                                type_ref=name,
                                initial_value=m.value,
                                parent_symbol=type_sym,
                                doc_comment=m.comment,
                            )
                            e_desc.add_enum_member(m_sym)
                            declared_symbols.append(m_sym)
                        self.type_index.register_type(e_desc)

                    elif isinstance(ast_node.definition, UnionType):
                        u_desc = TypeDescriptor(
                            name=name,
                            kind=SymbolKind.UNION,
                            file_path=path,
                            symbol=type_sym,
                        )
                        for f in ast_node.definition.fields:
                            f_sym = Symbol(
                                name=f.name,
                                kind=SymbolKind.STRUCT_FIELD,
                                span=f.span.offset_by(line_offset, col_offset, char_offset) if f.span else node_span,
                                file_path=path,
                                type_ref=f.type_name,
                                parent_symbol=type_sym,
                                doc_comment=f.comment,
                            )
                            u_desc.add_field(f_sym)
                            declared_symbols.append(f_sym)
                        self.type_index.register_type(u_desc)

                    elif isinstance(ast_node.definition, str):
                        # Alias Type
                        a_desc = TypeDescriptor(
                            name=name,
                            kind=SymbolKind.ALIAS,
                            base_type_name=ast_node.definition,
                            file_path=path,
                            symbol=type_sym,
                        )
                        self.type_index.register_type(a_desc)

                elif isinstance(ast_node, InterfaceDecl):
                    name = ast_node.name or xml_doc.root_object_name or path.stem
                    itf_sym = Symbol(
                        name=name,
                        kind=SymbolKind.INTERFACE,
                        span=node_span,
                        file_path=path,
                        doc_comment=ast_node.comment,
                    )
                    self.symbol_table.define_global(itf_sym)
                    declared_symbols.append(itf_sym)

                    active_pou_symbol = itf_sym
                    active_pou_scope = self.symbol_table.create_pou_scope(itf_sym, path)

                    itf_desc = TypeDescriptor(
                        name=name,
                        kind=SymbolKind.INTERFACE,
                        implements_names=ast_node.extends_interfaces,
                        file_path=path,
                        symbol=itf_sym,
                    )
                    active_pou_type_desc = itf_desc
                    self.type_index.register_type(itf_desc)

                elif isinstance(ast_node, VarBlock):
                    # Bare GVL VarBlock
                    gvl_name = xml_doc.root_object_name or path.stem
                    gvl_sym = Symbol(
                        name=gvl_name,
                        kind=SymbolKind.GVL,
                        span=node_span,
                        file_path=path,
                    )
                    self.symbol_table.define_global(gvl_sym)
                    declared_symbols.append(gvl_sym)

                    gvl_scope = self.symbol_table.create_gvl_scope(gvl_sym, path)
                    for v in ast_node.variables:
                        v_sym = Symbol(
                            name=v.name,
                            kind=SymbolKind.VARIABLE,
                            span=v.span.offset_by(line_offset, col_offset, char_offset) if v.span else node_span,
                            file_path=path,
                            type_ref=v.type_name,
                            is_constant=ast_node.is_constant or v.is_constant,
                            is_retain=ast_node.is_retain or v.is_retain,
                            is_persistent=ast_node.is_persistent or v.is_persistent,
                            initial_value=v.initial_value,
                            parent_symbol=gvl_sym,
                            doc_comment=v.comment,
                            var_block_type="VAR_GLOBAL",
                        )
                        gvl_scope.define(v_sym)
                        declared_symbols.append(v_sym)

            # 2. Method Declarations
            elif span.kind == CdataKind.METHOD_DECLARATION:
                ast_node, cst_nodes, diags = parse_declaration(span.content)
                all_cst_nodes.extend(cst_nodes)
                all_diags.extend(
                    SyntaxDiagnostic(d.message, d.span.offset_by(line_offset, col_offset, char_offset), d.severity, d.code)
                    for d in diags
                )

                node_span = ast_node.span.offset_by(line_offset, col_offset, char_offset) if ast_node and ast_node.span else default_span

                if isinstance(ast_node, MethodDecl) and active_pou_scope:
                    m_name = ast_node.name or span.parent_name or "Method"
                    m_sym = Symbol(
                        name=m_name,
                        kind=SymbolKind.METHOD,
                        span=node_span,
                        file_path=path,
                        type_ref=ast_node.return_type,
                        access=ast_node.access_modifier,
                        parent_symbol=active_pou_symbol,
                        doc_comment=ast_node.comment,
                    )
                    active_pou_scope.define(m_sym)
                    if active_pou_type_desc:
                        active_pou_type_desc.add_method(m_sym)
                    declared_symbols.append(m_sym)

                    m_scope = self.symbol_table.create_method_scope(m_sym, active_pou_scope, path)
                    method_scopes[m_name.lower()] = m_scope
                    for v_block in ast_node.var_blocks:
                        for v in v_block.variables:
                            mv_sym = Symbol(
                                name=v.name,
                                kind=SymbolKind.VARIABLE,
                                span=v.span.offset_by(line_offset, col_offset, char_offset) if v.span else node_span,
                                file_path=path,
                                type_ref=v.type_name,
                                is_constant=v_block.is_constant or v.is_constant,
                                is_retain=v_block.is_retain or v.is_retain,
                                is_persistent=v_block.is_persistent or v.is_persistent,
                                initial_value=v.initial_value,
                                address=v.address,
                                parent_symbol=m_sym,
                                doc_comment=v.comment,
                                var_block_type=v_block.block_type.upper() if getattr(v_block, "block_type", None) else "VAR",
                            )
                            m_scope.define(mv_sym)
                            declared_symbols.append(mv_sym)

            # 3. Property Declarations
            elif span.kind == CdataKind.PROPERTY_DECLARATION:
                ast_node, cst_nodes, diags = parse_declaration(span.content)
                all_cst_nodes.extend(cst_nodes)
                all_diags.extend(
                    SyntaxDiagnostic(d.message, d.span.offset_by(line_offset, col_offset, char_offset), d.severity, d.code)
                    for d in diags
                )

                node_span = ast_node.span.offset_by(line_offset, col_offset, char_offset) if ast_node and ast_node.span else default_span

                if isinstance(ast_node, PropertyDecl) and active_pou_scope:
                    p_name = ast_node.name or span.parent_name or "Property"
                    prop_sym = Symbol(
                        name=p_name,
                        kind=SymbolKind.PROPERTY,
                        span=node_span,
                        file_path=path,
                        type_ref=ast_node.type_name,
                        access=ast_node.access_modifier,
                        parent_symbol=active_pou_symbol,
                        doc_comment=ast_node.comment,
                    )
                    active_pou_scope.define(prop_sym)
                    if active_pou_type_desc:
                        active_pou_type_desc.add_property(prop_sym)
                    declared_symbols.append(prop_sym)

                    p_scope = self.symbol_table.create_method_scope(prop_sym, active_pou_scope, path)
                    property_scopes[p_name.lower()] = p_scope

            elif span.kind in (CdataKind.PROPERTY_GET_DECLARATION, CdataKind.PROPERTY_SET_DECLARATION):
                ast_node, cst_nodes, diags = parse_declaration(span.content)
                all_cst_nodes.extend(cst_nodes)
                all_diags.extend(
                    SyntaxDiagnostic(d.message, d.span.offset_by(line_offset, col_offset, char_offset), d.severity, d.code)
                    for d in diags
                )
                node_span = ast_node.span.offset_by(line_offset, col_offset, char_offset) if ast_node and ast_node.span else default_span
                p_name = span.parent_name or "Property"
                p_scope = property_scopes.get(p_name.lower())
                if p_scope and ast_node:
                    v_blocks = [ast_node] if isinstance(ast_node, VarBlock) else getattr(ast_node, "var_blocks", [])
                    for v_block in v_blocks:
                        for v in v_block.variables:
                            pv_sym = Symbol(
                                name=v.name,
                                kind=SymbolKind.VARIABLE,
                                span=v.span.offset_by(line_offset, col_offset, char_offset) if v.span else node_span,
                                file_path=path,
                                type_ref=v.type_name,
                                is_constant=v_block.is_constant or v.is_constant,
                                is_retain=v_block.is_retain or v.is_retain,
                                is_persistent=v_block.is_persistent or v.is_persistent,
                                initial_value=v.initial_value,
                                address=v.address,
                                parent_symbol=p_scope.owner_symbol,
                                doc_comment=v.comment,
                                var_block_type=v_block.block_type.upper() if getattr(v_block, "block_type", None) else "VAR",
                            )
                            p_scope.define(pv_sym)
                            declared_symbols.append(pv_sym)

            # 4. Implementation Bodies (POU, Method, Action, Property)
            elif span.is_implementation:
                if not declaration_only:
                    stmts, cst_nodes, diags = parse_implementation(span.content)
                    all_cst_nodes.extend(cst_nodes)
                    all_diags.extend(
                        SyntaxDiagnostic(d.message, d.span.offset_by(line_offset, col_offset, char_offset), d.severity, d.code)
                        for d in diags
                    )

                    impl_scope = active_pou_scope or self.symbol_table.global_scope
                    if span.kind == CdataKind.METHOD_IMPLEMENTATION and span.parent_name:
                        m_scope = method_scopes.get(span.parent_name.lower())
                        if m_scope:
                            impl_scope = m_scope
                    elif span.kind in (CdataKind.PROPERTY_GET_IMPLEMENTATION, CdataKind.PROPERTY_SET_IMPLEMENTATION) and span.parent_name:
                        p_scope = property_scopes.get(span.parent_name.lower())
                        if p_scope:
                            impl_scope = p_scope

                    implementation_statements.append((span, impl_scope, stmts))

                if span.kind == CdataKind.ACTION_IMPLEMENTATION and active_pou_scope and span.parent_name:
                    start_line, start_col = offset_to_line_col(xml_doc.raw_text, span.content_start)
                    end_line, end_col = offset_to_line_col(xml_doc.raw_text, span.content_end)
                    action_span = SourceSpan.from_bounds(
                        start_line=start_line,
                        start_col=start_col,
                        start_offset=span.content_start,
                        end_line=end_line,
                        end_col=end_col,
                        end_offset=span.content_end,
                    )
                    action_sym = Symbol(
                        name=span.parent_name,
                        kind=SymbolKind.ACTION,
                        span=action_span,
                        file_path=path,
                        parent_symbol=active_pou_symbol,
                    )
                    active_pou_scope.define(action_sym)
                    if active_pou_type_desc:
                        active_pou_type_desc.add_method(action_sym)
                    declared_symbols.append(action_sym)

        indexed = IndexedFile(
            file_path=path,
            content_hash=chash,
            xml_doc=xml_doc,
            top_level_ast=top_level_ast,
            cst_nodes=all_cst_nodes,
            diagnostics=all_diags,
            declared_symbols=declared_symbols,
            implementation_statements=implementation_statements,
            has_full_implementation=not declaration_only,
        )
        self.indexed_files[path] = indexed
        return indexed

    def remove_file(self, file_path: Path) -> None:
        """Remove a file from the workspace index, symbol table, and type index."""
        path = file_path.resolve()
        self.indexed_files.pop(path, None)
        self.type_index.remove_types_by_file(path)
        self.symbol_table.remove_file(path)

    def get_file(self, file_path: Path) -> Optional[IndexedFile]:
        """Retrieve indexed file metadata if present."""
        return self.indexed_files.get(file_path.resolve())

    def find_symbols(self, query: str = "", limit: int = 100) -> list[Symbol]:
        """Search for symbols across all indexed files, types, and global scopes."""
        q = query.strip().lower()
        results: list[Symbol] = []
        seen_names: set[str] = set()

        # 1. Search declared symbols in indexed files
        for indexed in self.indexed_files.values():
            for sym in indexed.declared_symbols:
                if not q or q in sym.name.lower():
                    key = f"{sym.kind.value}:{sym.name}:{sym.file_path}"
                    if key not in seen_names:
                        seen_names.add(key)
                        results.append(sym)
                        if len(results) >= limit:
                            return results

        # 2. Search global symbols
        for sym in self.symbol_table.global_scope:
            if not q or q in sym.name.lower():
                key = f"{sym.kind.value}:{sym.name}"
                if key not in seen_names:
                    seen_names.add(key)
                    results.append(sym)
                    if len(results) >= limit:
                        return results

        return results

    def lookup_symbol(
        self,
        symbol_or_chain: str,
        scope_pou: Optional[str] = None,
        file_path: Optional[Path] = None,
    ) -> Optional[Symbol]:
        """Resolve a symbol or member chain (e.g. 'fbMotor.stParam.fSpeed' or 'TON.IN') with proximity."""
        scope = self.symbol_table.global_scope

        if scope_pou:
            p_scope = self.symbol_table.find_pou_scope(scope_pou, context_path=file_path)
            if p_scope:
                scope = p_scope
        elif file_path:
            p_scope = self.symbol_table.get_file_pou_scope(file_path)
            if p_scope:
                scope = p_scope

        return self.resolver.resolve_chain(symbol_or_chain, scope)


_SHARED_WORKSPACE: Optional[WorkspaceIndex] = None


def get_shared_workspace(path_or_plcproj: Optional[Path | str] = None, force_refresh: bool = False) -> WorkspaceIndex:
    """Retrieve or create the shared singleton WorkspaceIndex for MCP and tooling."""
    global _SHARED_WORKSPACE
    if path_or_plcproj is not None:
        p = Path(path_or_plcproj).resolve()
        
        target_proj_path: Optional[Path] = None
        if p.is_file() and p.suffix.lower() == ".plcproj":
            target_proj_path = p
        elif p.is_dir():
            plcs = list(p.glob("*.plcproj")) or list(p.glob("**/*.plcproj"))
            if plcs:
                target_proj_path = plcs[0].resolve()

        already_loaded = False
        if _SHARED_WORKSPACE is not None and not force_refresh:
            if _SHARED_WORKSPACE.project and target_proj_path:
                already_loaded = (_SHARED_WORKSPACE.project.project_path.resolve() == target_proj_path)
            elif _SHARED_WORKSPACE.project and not target_proj_path:
                already_loaded = (_SHARED_WORKSPACE.project.root_dir.resolve() == p)
            elif not _SHARED_WORKSPACE.project and not target_proj_path and _SHARED_WORKSPACE.indexed_files:
                already_loaded = True

        if not already_loaded or force_refresh:
            if target_proj_path:
                _SHARED_WORKSPACE = WorkspaceIndex.from_plcproj(target_proj_path)
            elif p.is_dir():
                _SHARED_WORKSPACE = WorkspaceIndex()
                for ext in ("*.TcPOU", "*.TcDUT", "*.TcGVL", "*.TcIO"):
                    for f in p.glob(f"**/{ext}"):
                        _SHARED_WORKSPACE.update_file(f)
            else:
                _SHARED_WORKSPACE = WorkspaceIndex()
    elif _SHARED_WORKSPACE is None:
        _SHARED_WORKSPACE = WorkspaceIndex()

    return _SHARED_WORKSPACE

