"""LSP request and notification handler implementations calling twincat_core."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

import lsprotocol.types as lsp

from ..project.workspace_index import IndexedFile, WorkspaceIndex
from ..semantic.diagnostics import run_semantic_analysis
from ..semantic.scopes import Scope
from ..semantic.symbols import Symbol, SymbolKind
from ..syntax.lexer import tokenize_st
from ..syntax.span import Position, SourceSpan, line_col_to_offset, offset_to_line_col
from ..syntax.tokens import Token, TokenType
from ..xml.types import CdataKind, CdataSpan
from .utils import (
    cdata_span_to_lsp_location,
    diagnostic_to_lsp,
    path_to_uri,
    position_from_lsp,
    span_to_range,
    symbol_to_document_symbol,
    uri_to_path,
)

ST_KEYWORDS = [
    "IF", "THEN", "ELSE", "ELSIF", "END_IF",
    "CASE", "OF", "END_CASE",
    "FOR", "TO", "BY", "DO", "END_FOR",
    "WHILE", "END_WHILE",
    "REPEAT", "UNTIL", "END_REPEAT",
    "RETURN", "EXIT", "CONTINUE",
    "VAR", "END_VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_TEMP", "VAR_STAT", "VAR_GLOBAL",
    "CONSTANT", "PERSISTENT", "RETAIN",
    "TRUE", "FALSE", "NOT", "AND", "OR", "XOR", "MOD",
    "THIS", "SUPER",
    "FUNCTION", "FUNCTION_BLOCK", "PROGRAM", "METHOD", "PROPERTY", "ACTION", "INTERFACE",
    "TYPE", "STRUCT", "END_STRUCT", "END_TYPE",
]


def find_token_at_position(
    tokens: Sequence[Token], line: int, col: int
) -> tuple[Optional[Token], Optional[Token], Optional[Token]]:
    """Locate the semantic token under the cursor (1-based line & col).

    Returns:
        (target_token, prev_token, prev_prev_token)
    """
    semantic_tokens = [t for t in tokens if not t.is_trivia]
    target_idx = -1

    for idx, tok in enumerate(semantic_tokens):
        s = tok.span
        if s.start.line == line:
            if s.start.col <= col <= s.end.col:
                target_idx = idx
                break
        elif s.start.line < line < s.end.line:
            target_idx = idx
            break
        elif s.end.line == line and col <= s.end.col:
            target_idx = idx
            break

    if target_idx < 0:
        return None, None, None

    target = semantic_tokens[target_idx]
    prev = semantic_tokens[target_idx - 1] if target_idx > 0 else None
    prev_prev = semantic_tokens[target_idx - 2] if target_idx > 1 else None

    return target, prev, prev_prev


def get_effective_scope_for_file(
    index: WorkspaceIndex,
    file_path: Path,
    position: Position,
    matched_span: Optional[CdataSpan] = None,
) -> Scope:
    """Find the most specific POU, method, or action scope for the given cursor position with file isolation."""
    indexed = index.get_file(file_path)
    if not indexed or not indexed.top_level_ast:
        return index.symbol_table.global_scope

    # 1. First priority: look for scope declared in this exact file
    pou_scope = index.symbol_table.get_file_pou_scope(file_path)
    if not pou_scope:
        pou_name = getattr(indexed.top_level_ast, "name", "")
        pou_scope = index.symbol_table.find_pou_scope(pou_name, context_path=file_path)
        if not pou_scope:
            gvl_scope = index.symbol_table.find_gvl_scope(pou_name, context_path=file_path)
            if gvl_scope:
                return gvl_scope
            return index.symbol_table.global_scope

    if not matched_span:
        return pou_scope

    # Check if cursor is inside a Method or Action CDATA span
    if matched_span.parent_name and matched_span.parent_name.lower() != pou_scope.name.lower():
        for child in pou_scope.children:
            if child.owner_symbol and child.owner_symbol.name.lower() == matched_span.parent_name.lower():
                return child

    return pou_scope


def resolve_symbol_at_cursor(
    index: WorkspaceIndex, file_path: Path, pos: Position
) -> Optional[Symbol]:
    """Resolve identifier symbol at cursor position using twincat_core.semantic."""
    indexed = index.get_file(file_path)
    if not indexed:
        return None

    raw_text = indexed.xml_doc.raw_text
    # Calculate 0-based character offset in full file
    target_offset = line_col_to_offset(raw_text, pos.line, pos.col)

    # Check if target_offset falls within a CDATA span
    matched_span = None
    for span in indexed.xml_doc.cdata_spans:
        if span.content_start <= target_offset <= span.content_end:
            matched_span = span
            break

    # If the file is an XML TcPlcObject and cursor is outside all CDATA blocks,
    # cursor is on XML markup tags (e.g. <Implementation>, <POU>) -> no ST symbol.
    if indexed.xml_doc.cdata_spans and not matched_span:
        return None

    scope = get_effective_scope_for_file(index, file_path, pos, matched_span=matched_span)

    if matched_span:
        # Cursor is inside a CDATA block: tokenize this CDATA content
        rel_offset = target_offset - matched_span.content_start
        tokens, _ = tokenize_st(matched_span.content, include_trivia=True)

        # Find token by offset
        semantic_tokens = [t for t in tokens if not t.is_trivia]
        target_idx = -1
        for idx, tok in enumerate(semantic_tokens):
            if tok.span.start.offset <= rel_offset <= tok.span.end.offset:
                target_idx = idx
                break

        if target_idx < 0:
            return None

        target_tok = semantic_tokens[target_idx]
        prev_tok = semantic_tokens[target_idx - 1] if target_idx > 0 else None
        prev_prev_tok = semantic_tokens[target_idx - 2] if target_idx > 1 else None
    else:
        # Plain ST file (.st)
        tokens, _ = tokenize_st(raw_text, include_trivia=True)
        target_tok, prev_tok, prev_prev_tok = find_token_at_position(tokens, pos.line, pos.col)
        semantic_tokens = [t for t in tokens if not t.is_trivia]
        target_idx = -1

    if not target_tok or target_tok.type not in (
        TokenType.IDENTIFIER,
        TokenType.KEYWORD_THIS,
        TokenType.KEYWORD_SUPER,
    ):
        return None

    # 1. Named Call Parameter: e.g. "fbTimer(IN := TRUE)" or "fbRTrig(CLK => bDone)"
    if (
        matched_span
        and target_idx >= 0
        and target_idx + 1 < len(semantic_tokens)
        and semantic_tokens[target_idx + 1].type in (TokenType.ASSIGN, TokenType.OUTPUT_ASSIGN)
    ):
        nesting = 0
        call_open_idx = -1
        for b_idx in range(target_idx - 1, -1, -1):
            tok = semantic_tokens[b_idx]
            if tok.type in (TokenType.PAREN_CLOSE, TokenType.BRACKET_CLOSE):
                nesting += 1
            elif tok.type in (TokenType.PAREN_OPEN, TokenType.BRACKET_OPEN):
                if nesting > 0:
                    nesting -= 1
                else:
                    call_open_idx = b_idx
                    break

        if call_open_idx > 0:
            caller_tokens = []
            c_idx = call_open_idx - 1
            while c_idx >= 0:
                tok = semantic_tokens[c_idx]
                if tok.type in (
                    TokenType.IDENTIFIER,
                    TokenType.KEYWORD_THIS,
                    TokenType.KEYWORD_SUPER,
                    TokenType.DOT,
                    TokenType.POINTER_DEREF,
                    TokenType.INT_LITERAL,
                    TokenType.BRACKET_OPEN,
                    TokenType.BRACKET_CLOSE,
                ):
                    caller_tokens.insert(0, tok)
                    c_idx -= 1
                else:
                    break

            if caller_tokens:
                caller_str = "".join(t.value for t in caller_tokens)
                caller_sym = index.resolver.resolve_chain(caller_str, scope) or index.resolver.resolve_identifier(caller_str, scope)
                if caller_sym:
                    callee_type_name = caller_sym.type_ref or caller_sym.name
                    type_desc = index.type_index.get_type(callee_type_name, context_path=file_path)
                    if type_desc:
                        t_lower = target_tok.value.lower()
                        for f_name, f_sym in type_desc.fields.items():
                            if f_name.lower() == t_lower:
                                return f_sym
                        for p_name, p_sym in type_desc.properties.items():
                            if p_name.lower() == t_lower:
                                return p_sym

    # 2. Chained Member Access: e.g. "fbStation1.fbMotor.stParam.fSpeed" or "stData.field"
    if prev_tok and prev_tok.type == TokenType.DOT:
        if matched_span and target_idx >= 0:
            chain_tokens = [target_tok]
            curr_idx = target_idx - 1
            while curr_idx >= 0:
                tok = semantic_tokens[curr_idx]
                if tok.type in (
                    TokenType.IDENTIFIER,
                    TokenType.KEYWORD_THIS,
                    TokenType.KEYWORD_SUPER,
                    TokenType.DOT,
                    TokenType.POINTER_DEREF,
                    TokenType.INT_LITERAL,
                    TokenType.BRACKET_OPEN,
                    TokenType.BRACKET_CLOSE,
                    TokenType.PAREN_OPEN,
                    TokenType.PAREN_CLOSE,
                ):
                    chain_tokens.append(tok)
                    curr_idx -= 1
                else:
                    break
            chain_tokens.reverse()
            chain_str = "".join(t.value for t in chain_tokens)
            resolved_chain = index.resolver.resolve_chain(chain_str, scope)
            if resolved_chain:
                return resolved_chain

        if prev_prev_tok and prev_prev_tok.type == TokenType.IDENTIFIER:
            target_obj = index.resolver.resolve_identifier(prev_prev_tok.value, scope)
            if target_obj and target_obj.type_ref:
                return index.resolver.resolve_member_access(target_obj.type_ref, target_tok.value, scope)
            type_desc = index.type_index.get_type(prev_prev_tok.value, context_path=file_path)
            if type_desc:
                return index.resolver.resolve_member_access(type_desc.name, target_tok.value, scope)

    # 3. Regular identifier resolution (Local -> OOP / Member -> Global / GVL)
    return index.resolver.resolve_identifier(target_tok.value, scope)


def handle_definition(
    index: WorkspaceIndex, params: lsp.DefinitionParams
) -> Optional[lsp.Location]:
    """Handle textDocument/definition request."""
    file_path = uri_to_path(params.text_document.uri)
    pos = position_from_lsp(params.position)

    sym = resolve_symbol_at_cursor(index, file_path, pos)
    if not sym or not sym.file_path or not sym.span:
        return None

    # Only navigate if the target file exists on disk (same file or in solution)
    if not sym.file_path.exists():
        return None

    target_uri = path_to_uri(sym.file_path)
    target_range = span_to_range(sym.span)
    return lsp.Location(uri=target_uri, range=target_range)


def handle_implementation(
    index: WorkspaceIndex, params: lsp.ImplementationParams
) -> Union[lsp.Location, list[lsp.Location], None]:
    """Handle textDocument/implementation request (Ctrl+F12).

    Navigates to the implementation body of a POU, Method, Action,
    or all FBs/methods implementing an Interface / Interface Method.
    Returns None for external libraries where source code is unavailable on disk.
    """
    file_path = uri_to_path(params.text_document.uri)
    pos = position_from_lsp(params.position)

    sym = resolve_symbol_at_cursor(index, file_path, pos)
    if not sym:
        return None

    # 1. External symbols (no file_path on disk) -> implementation unavailable on disk
    if not sym.file_path or not sym.file_path.exists():
        return None

    # 2. Case: Interface -> find all FBs in the solution implementing this interface
    if sym.kind == SymbolKind.INTERFACE:
        itf_name = sym.name.lower()
        locations: list[lsp.Location] = []
        for indexed in index.indexed_files.values():
            if indexed.file_path.suffix.lower() == ".tcpou":
                type_desc = index.type_index.get_type(indexed.xml_doc.root_object_name, context_path=file_path)
                if type_desc and any(itf.lower() == itf_name for itf in type_desc.implements_names):
                    impl_span = indexed.xml_doc.get_implementation_span()
                    if impl_span:
                        locations.append(cdata_span_to_lsp_location(impl_span, indexed.xml_doc.raw_text, indexed.file_path))
                    else:
                        decl_span = indexed.xml_doc.get_declaration_span()
                        if decl_span:
                            locations.append(cdata_span_to_lsp_location(decl_span, indexed.xml_doc.raw_text, indexed.file_path))
        if locations:
            return locations if len(locations) > 1 else locations[0]
        return None

    # 3. Case: Method (either on POU or Interface)
    if sym.kind == SymbolKind.METHOD:
        indexed = index.get_file(sym.file_path)
        if indexed and indexed.file_path.suffix.lower() == ".tcio":
            # Interface method -> find all implementing methods across FBs
            itf_name = indexed.xml_doc.root_object_name.lower()
            m_name = sym.name.lower()
            locations = []
            for other_indexed in index.indexed_files.values():
                if other_indexed.file_path.suffix.lower() == ".tcpou":
                    type_desc = index.type_index.get_type(other_indexed.xml_doc.root_object_name, context_path=file_path)
                    if type_desc and any(itf.lower() == itf_name for itf in type_desc.implements_names):
                        for span in other_indexed.xml_doc.cdata_spans:
                            if span.kind == CdataKind.METHOD_IMPLEMENTATION and span.parent_name.lower() == m_name:
                                locations.append(cdata_span_to_lsp_location(span, other_indexed.xml_doc.raw_text, other_indexed.file_path))
            if locations:
                return locations if len(locations) > 1 else locations[0]
            return None

        # Regular POU Method -> find its METHOD_IMPLEMENTATION span
        if indexed:
            for span in indexed.xml_doc.cdata_spans:
                if span.kind == CdataKind.METHOD_IMPLEMENTATION and span.parent_name.lower() == sym.name.lower():
                    return cdata_span_to_lsp_location(span, indexed.xml_doc.raw_text, sym.file_path)

        return lsp.Location(uri=path_to_uri(sym.file_path), range=span_to_range(sym.span))

    # 4. Case: Property (either on POU or Interface)
    if sym.kind == SymbolKind.PROPERTY:
        indexed = index.get_file(sym.file_path)
        if indexed and indexed.file_path.suffix.lower() == ".tcio":
            # Interface property -> find all implementing properties across FBs
            itf_name = indexed.xml_doc.root_object_name.lower()
            p_name = sym.name.lower()
            locations = []
            for other_indexed in index.indexed_files.values():
                if other_indexed.file_path.suffix.lower() == ".tcpou":
                    type_desc = index.type_index.get_type(other_indexed.xml_doc.root_object_name, context_path=file_path)
                    if type_desc and any(itf.lower() == itf_name for itf in type_desc.implements_names):
                        for span in other_indexed.xml_doc.cdata_spans:
                            if span.kind in (CdataKind.PROPERTY_GET_IMPLEMENTATION, CdataKind.PROPERTY_SET_IMPLEMENTATION) and span.parent_name.lower() == p_name:
                                locations.append(cdata_span_to_lsp_location(span, other_indexed.xml_doc.raw_text, other_indexed.file_path))
            if locations:
                return locations if len(locations) > 1 else locations[0]
            return None

        # Regular POU Property -> find its PROPERTY_GET_IMPLEMENTATION / PROPERTY_SET_IMPLEMENTATION spans
        if indexed:
            locations = []
            for span in indexed.xml_doc.cdata_spans:
                if span.kind in (CdataKind.PROPERTY_GET_IMPLEMENTATION, CdataKind.PROPERTY_SET_IMPLEMENTATION) and span.parent_name.lower() == sym.name.lower():
                    locations.append(cdata_span_to_lsp_location(span, indexed.xml_doc.raw_text, sym.file_path))
            if locations:
                return locations if len(locations) > 1 else locations[0]

        return lsp.Location(uri=path_to_uri(sym.file_path), range=span_to_range(sym.span))

    # 5. Case: Action -> find ACTION_IMPLEMENTATION span
    if sym.kind == SymbolKind.ACTION:
        indexed = index.get_file(sym.file_path)
        if indexed:
            for span in indexed.xml_doc.cdata_spans:
                if span.kind == CdataKind.ACTION_IMPLEMENTATION and span.parent_name.lower() == sym.name.lower():
                    return cdata_span_to_lsp_location(span, indexed.xml_doc.raw_text, sym.file_path)
        return lsp.Location(uri=path_to_uri(sym.file_path), range=span_to_range(sym.span))

    # 6. Case: POU / FB / Function / Program -> find POU_IMPLEMENTATION span
    if sym.kind in (SymbolKind.POU, SymbolKind.FUNCTION_BLOCK, SymbolKind.FUNCTION, SymbolKind.PROGRAM):
        indexed = index.get_file(sym.file_path)
        if indexed:
            impl_span = indexed.xml_doc.get_implementation_span()
            if impl_span:
                return cdata_span_to_lsp_location(impl_span, indexed.xml_doc.raw_text, sym.file_path)
        return lsp.Location(uri=path_to_uri(sym.file_path), range=span_to_range(sym.span))

    # 7. Case: Variable / Instance / Field / Parameter -> resolve type's implementation
    if sym.kind in (SymbolKind.VARIABLE, SymbolKind.CONSTANT, SymbolKind.STRUCT_FIELD) and sym.type_ref:
        type_desc = index.type_index.get_type(sym.type_ref, context_path=file_path)
        if type_desc and type_desc.file_path and type_desc.file_path.exists():
            if type_desc.kind == SymbolKind.INTERFACE:
                itf_name = type_desc.name.lower()
                locations = []
                for indexed in index.indexed_files.values():
                    if indexed.file_path.suffix.lower() == ".tcpou":
                        t_desc = index.type_index.get_type(indexed.xml_doc.root_object_name, context_path=file_path)
                        if t_desc and any(itf.lower() == itf_name for itf in t_desc.implements_names):
                            impl_span = indexed.xml_doc.get_implementation_span()
                            if impl_span:
                                locations.append(cdata_span_to_lsp_location(impl_span, indexed.xml_doc.raw_text, indexed.file_path))
                if locations:
                    return locations if len(locations) > 1 else locations[0]
                return None
            elif type_desc.kind in (SymbolKind.FUNCTION_BLOCK, SymbolKind.POU, SymbolKind.FUNCTION, SymbolKind.PROGRAM):
                indexed = index.get_file(type_desc.file_path)
                if indexed:
                    impl_span = indexed.xml_doc.get_implementation_span()
                    if impl_span:
                        return cdata_span_to_lsp_location(impl_span, indexed.xml_doc.raw_text, type_desc.file_path)
                return lsp.Location(uri=path_to_uri(type_desc.file_path), range=span_to_range(type_desc.symbol.span if type_desc.symbol else sym.span))
            elif type_desc.kind in (SymbolKind.STRUCT, SymbolKind.ENUM, SymbolKind.UNION, SymbolKind.ALIAS):
                indexed = index.get_file(type_desc.file_path)
                if indexed:
                    decl_span = indexed.xml_doc.get_declaration_span()
                    if decl_span:
                        return cdata_span_to_lsp_location(decl_span, indexed.xml_doc.raw_text, type_desc.file_path)
                return lsp.Location(uri=path_to_uri(type_desc.file_path), range=span_to_range(type_desc.symbol.span if type_desc.symbol else sym.span))

        return None

    # 7. Default fallback
    return lsp.Location(uri=path_to_uri(sym.file_path), range=span_to_range(sym.span))


def handle_type_definition(
    index: WorkspaceIndex, params: lsp.TypeDefinitionParams
) -> Optional[lsp.Location]:
    """Handle textDocument/typeDefinition request.

    Navigates to the type definition of a variable, constant, field, parameter,
    or the type declaration itself (POU, Struct DUT, Enum DUT, Interface).
    """
    file_path = uri_to_path(params.text_document.uri)
    pos = position_from_lsp(params.position)

    sym = resolve_symbol_at_cursor(index, file_path, pos)
    if not sym:
        return None

    type_to_find = sym.type_ref or sym.name
    type_desc = index.type_index.get_type(type_to_find, context_path=file_path)
    if type_desc and type_desc.file_path and type_desc.file_path.exists():
        indexed = index.get_file(type_desc.file_path)
        if indexed:
            decl_span = indexed.xml_doc.get_declaration_span()
            if decl_span:
                return cdata_span_to_lsp_location(decl_span, indexed.xml_doc.raw_text, type_desc.file_path)
        return lsp.Location(
            uri=path_to_uri(type_desc.file_path),
            range=span_to_range(type_desc.symbol.span if type_desc.symbol and type_desc.symbol.span else sym.span),
        )

    if sym.file_path and sym.file_path.exists() and sym.span:
        return lsp.Location(uri=path_to_uri(sym.file_path), range=span_to_range(sym.span))

    return None


def _format_iec_decl_block(lines: list[str]) -> str:
    """Format and column-align ST declaration lines using the project's ST formatter engine."""
    if not lines:
        return ""
    try:
        from formatter.st_alignment import align_declarations
        return "\n".join(align_declarations(lines))
    except Exception:
        return "\n".join(lines)


def _format_var_block(title: str, symbols: Sequence[Symbol], is_struct: bool = False) -> list[str]:
    """Format a variable block (VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT, STRUCT) with clean indentation and comments."""
    if not symbols:
        return []
    res = [title]
    for s in symbols:
        comm = f" // {' '.join(s.doc_comment.split())}" if s.doc_comment else ""
        init_part = f" := {s.initial_value}" if s.initial_value else ""
        res.append(f"    {s.name} : {s.type_ref or 'BOOL'}{init_part};{comm}")
    if not is_struct:
        res.append("END_VAR")
    return res


def format_hover_for_symbol(
    index: WorkspaceIndex, sym: Symbol, file_path: Path
) -> lsp.Hover:
    """Render rich, structured IEC-conforming hover documentation for a resolved Symbol."""
    type_name_to_lookup = sym.name if sym.kind in (
        SymbolKind.POU,
        SymbolKind.FUNCTION_BLOCK,
        SymbolKind.FUNCTION,
        SymbolKind.PROGRAM,
        SymbolKind.STRUCT,
        SymbolKind.ENUM,
        SymbolKind.INTERFACE,
        SymbolKind.ALIAS,
    ) else sym.type_ref

    type_desc = None
    if type_name_to_lookup:
        type_desc = index.type_index.get_type(type_name_to_lookup, context_path=file_path)

    lines: list[str] = []

    # 1. Declaration Signature Block in iecst
    if sym.kind in (SymbolKind.POU, SymbolKind.FUNCTION_BLOCK, SymbolKind.PROGRAM):
        header = f"FUNCTION_BLOCK {sym.name}"
        if type_desc and type_desc.extends_name:
            header += f" EXTENDS {type_desc.extends_name}"
        if type_desc and type_desc.implements_names:
            header += f" IMPLEMENTS {', '.join(type_desc.implements_names)}"

        st_decl = [header]
        if type_desc and type_desc.fields:
            # ONLY public interface: VAR_INPUT, VAR_IN_OUT, VAR_OUTPUT (internal VAR is excluded)
            inputs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_INPUT"]
            in_outs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_IN_OUT"]
            outputs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_OUTPUT"]

            # Fallback for external library types from InfoSys where var_block_type might be default
            if not inputs and not in_outs and not outputs and type_desc.is_external:
                for f in type_desc.fields.values():
                    f_name_lower = f.name.lower()
                    if f_name_lower.startswith(("berror", "bdone", "bbusy", "hrerror", "eerror", "q", "et")):
                        outputs.append(f)
                    else:
                        inputs.append(f)

            if inputs:
                st_decl.extend(_format_var_block("VAR_INPUT", inputs))
            if in_outs:
                st_decl.extend(_format_var_block("VAR_IN_OUT", in_outs))
            if outputs:
                st_decl.extend(_format_var_block("VAR_OUTPUT", outputs))

        lines.append(f"```iecst\n" + _format_iec_decl_block(st_decl) + "\n```")

    elif sym.kind == SymbolKind.STRUCT:
        st_decl = [f"TYPE {sym.name} :", "STRUCT"]
        if type_desc and type_desc.fields:
            for f in type_desc.fields.values():
                comm = f" // {' '.join(f.doc_comment.split())}" if f.doc_comment else ""
                init_part = f" := {f.initial_value}" if f.initial_value else ""
                st_decl.append(f"    {f.name} : {f.type_ref or 'INT'}{init_part};{comm}")
        st_decl.extend(["END_STRUCT", "END_TYPE"])
        lines.append(f"```iecst\n" + _format_iec_decl_block(st_decl) + "\n```")

    elif sym.kind == SymbolKind.ENUM:
        members_str = ", ".join(type_desc.enum_members.keys()) if type_desc and type_desc.enum_members else "..."
        st_decl = [f"TYPE {sym.name} :", f"    ({members_str});", "END_TYPE"]
        lines.append(f"```iecst\n" + _format_iec_decl_block(st_decl) + "\n```")

    elif sym.kind == SymbolKind.INTERFACE:
        header = f"INTERFACE {sym.name}"
        if type_desc and type_desc.implements_names:
            header += f" EXTENDS {', '.join(type_desc.implements_names)}"
        lines.append(f"```iecst\n{header}\n```")

    elif sym.kind == SymbolKind.FUNCTION:
        ret_type = (
            type_desc.base_type_name
            if (type_desc and type_desc.base_type_name)
            else (sym.type_ref if sym.type_ref and sym.type_ref.upper() != sym.name.upper() else "BOOL")
        )
        st_decl = [f"FUNCTION {sym.name} : {ret_type}"]
        if type_desc and type_desc.fields:
            inputs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_INPUT"]
            in_outs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_IN_OUT"]
            outputs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_OUTPUT"]
            if not inputs and not in_outs and not outputs:
                inputs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() != "VAR"]

            if inputs:
                st_decl.extend(_format_var_block("VAR_INPUT", inputs))
            if in_outs:
                st_decl.extend(_format_var_block("VAR_IN_OUT", in_outs))
            if outputs:
                st_decl.extend(_format_var_block("VAR_OUTPUT", outputs))
        lines.append(f"```iecst\n" + _format_iec_decl_block(st_decl) + "\n```")

    elif sym.kind == SymbolKind.METHOD:
        access_str = f"{sym.access} " if sym.access and sym.access.upper() != "PUBLIC" else ""
        ret_type = f" : {sym.type_ref}" if sym.type_ref else ""
        st_decl = [f"METHOD {access_str}{sym.name}{ret_type}"]

        # Resolve method parameters from scope if available
        method_params: list[Symbol] = []
        if sym.file_path:
            pou_scope = index.symbol_table.get_file_pou_scope(sym.file_path)
            if not pou_scope and sym.parent_symbol:
                pou_scope = index.symbol_table.find_pou_scope(sym.parent_symbol.name, context_path=sym.file_path)
            if pou_scope:
                for child in pou_scope.children:
                    if child.owner_symbol and child.owner_symbol.name.lower() == sym.name.lower():
                        method_params = list(child.symbols.values())
                        break

        if method_params:
            inputs = [p for p in method_params if (p.var_block_type or "").upper() == "VAR_INPUT"]
            in_outs = [p for p in method_params if (p.var_block_type or "").upper() == "VAR_IN_OUT"]
            outputs = [p for p in method_params if (p.var_block_type or "").upper() == "VAR_OUTPUT"]
            if inputs:
                st_decl.extend(_format_var_block("VAR_INPUT", inputs))
            if in_outs:
                st_decl.extend(_format_var_block("VAR_IN_OUT", in_outs))
            if outputs:
                st_decl.extend(_format_var_block("VAR_OUTPUT", outputs))

        lines.append(f"```iecst\n" + _format_iec_decl_block(st_decl) + "\n```")

    elif sym.kind == SymbolKind.PROPERTY:
        access_str = f"{sym.access} " if sym.access and sym.access.upper() != "PUBLIC" else ""
        ret_type = f" : {sym.type_ref}" if sym.type_ref else ""
        lines.append(f"```iecst\nPROPERTY {access_str}{sym.name}{ret_type}\n```")

    else:
        # Variable / Field / Constant / Alias
        type_str = f" : {sym.type_ref}" if sym.type_ref else ""
        kind_str = sym.kind.value.upper()
        lines.append(f"```iecst\n({kind_str}) {sym.name}{type_str}\n```")

        # If variable is an FB instance, also render the FB's public signature block
        if type_desc and type_desc.kind in (SymbolKind.FUNCTION_BLOCK, SymbolKind.POU) and type_desc.fields:
            inputs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_INPUT"]
            in_outs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_IN_OUT"]
            outputs = [f for f in type_desc.fields.values() if (f.var_block_type or "").upper() == "VAR_OUTPUT"]
            if inputs or in_outs or outputs:
                fb_sub = [f"FUNCTION_BLOCK {type_desc.name}"]
                if inputs:
                    fb_sub.extend(_format_var_block("VAR_INPUT", inputs))
                if in_outs:
                    fb_sub.extend(_format_var_block("VAR_IN_OUT", in_outs))
                if outputs:
                    fb_sub.extend(_format_var_block("VAR_OUTPUT", outputs))
                lines.append(f"```iecst\n" + _format_iec_decl_block(fb_sub) + "\n```")

    # 2. Metadata details (Type summary & Library origin)
    meta_parts: list[str] = []
    parent_desc = None
    if sym.parent_symbol:
        parent_desc = index.type_index.get_type(sym.parent_symbol.name, context_path=file_path)

    eff_lib = (type_desc.namespace if type_desc and type_desc.namespace else None) or (parent_desc.namespace if parent_desc and parent_desc.namespace else None)
    if eff_lib:
        meta_parts.append(f"**Library:** `{eff_lib}`")

    if sym.kind in (SymbolKind.METHOD, SymbolKind.PROPERTY, SymbolKind.ACTION) and sym.parent_symbol:
        meta_parts.append(f"**Defined in:** `{sym.parent_symbol.name}`")
    elif type_desc:
        if sym.kind not in (
            SymbolKind.POU,
            SymbolKind.FUNCTION_BLOCK,
            SymbolKind.STRUCT,
            SymbolKind.ENUM,
            SymbolKind.INTERFACE,
            SymbolKind.FUNCTION,
        ) and sym.type_ref:
            type_label = type_desc.kind.value.replace("_", " ").title()
            meta_parts.append(f"**Type:** `{type_desc.name}` ({type_label})")
    elif sym.file_path:
        meta_parts.append(f"**Defined in:** `{sym.file_path.name}`")

    if meta_parts:
        lines.append(" | ".join(meta_parts))

    # 3. Properties and Methods summary if available on POU/FB/Interface
    if type_desc and sym.kind in (
        SymbolKind.POU,
        SymbolKind.FUNCTION_BLOCK,
        SymbolKind.INTERFACE,
        SymbolKind.VARIABLE,
    ):
        if type_desc.properties:
            lines.append("**Properties:**\n" + "\n".join(f"- `{p.name}`" + (f" : `{p.type_ref}`" if p.type_ref else "") for p in type_desc.properties.values()))
        if type_desc.methods:
            lines.append("**Methods:**\n" + "\n".join(f"- `{m.name}()`" + (f" : `{m.type_ref}`" if m.type_ref else "") for m in type_desc.methods.values()))

    # 4. Doc Comments / Description
    if sym.doc_comment:
        lines.append(f"{sym.doc_comment}")
    if type_desc and type_desc.symbol and type_desc.symbol.doc_comment and type_desc.symbol.doc_comment != sym.doc_comment:
        lines.append(f"{type_desc.symbol.doc_comment}")

    # 5. Initial value
    if sym.initial_value:
        lines.append(f"*Initial value:* `{sym.initial_value}`")

    content = lsp.MarkupContent(
        kind=lsp.MarkupKind.Markdown,
        value="\n\n".join(l for l in lines if l).strip(),
    )
    return lsp.Hover(contents=content, range=span_to_range(sym.span) if sym.span else None)


def handle_hover(
    index: WorkspaceIndex, params: lsp.HoverParams
) -> Optional[lsp.Hover]:
    """Handle textDocument/hover request."""
    file_path = uri_to_path(params.text_document.uri)
    pos = position_from_lsp(params.position)

    sym = resolve_symbol_at_cursor(index, file_path, pos)
    if not sym:
        return None

    return format_hover_for_symbol(index, sym, file_path)


def handle_completion(
    index: WorkspaceIndex, params: lsp.CompletionParams
) -> lsp.CompletionList:
    """Handle textDocument/completion request for member access and scope completion."""
    file_path = uri_to_path(params.text_document.uri)
    pos = position_from_lsp(params.position)

    indexed = index.get_file(file_path)
    raw_text = indexed.xml_doc.raw_text if indexed else (file_path.read_text(encoding="utf-8") if file_path.exists() else "")

    target_offset = line_col_to_offset(raw_text, pos.line, pos.col)

    matched_span = None
    if indexed:
        for span in indexed.xml_doc.cdata_spans:
            if span.content_start <= target_offset <= span.content_end:
                matched_span = span
                break

    scope = get_effective_scope_for_file(index, file_path, pos, matched_span=matched_span)

    if matched_span:
        rel_offset = max(0, target_offset - matched_span.content_start)
        cdata_prefix = matched_span.content[:rel_offset]
        if not cdata_prefix or cdata_prefix.endswith(("\n", "\r")):
            prefix_line = ""
        else:
            prefix_line = cdata_prefix.splitlines()[-1]
    else:
        line_idx = params.position.line
        col_idx = params.position.character
        raw_lines = raw_text.splitlines()
        prefix_line = raw_lines[line_idx][:col_idx] if 0 <= line_idx < len(raw_lines) else ""

    items: list[lsp.CompletionItem] = []

    # 1. Member Access Completion: e.g. "fbTimer.", "stConfig.f", "pDevice^.", "THIS^."
    re_member = re.search(r'([A-Za-z_][A-Za-z0-9_\^\[\].]*)\.([A-Za-z0-9_]*)$', prefix_line)
    if re_member:
        chain_expr = re_member.group(1)
        filter_prefix = re_member.group(2).lower()

        target_sym = index.resolver.resolve_chain(chain_expr, scope) or index.resolver.resolve_identifier(chain_expr, scope)
        if target_sym:
            type_name = target_sym.type_ref if target_sym.kind in (
                SymbolKind.VARIABLE,
                SymbolKind.CONSTANT,
                SymbolKind.STRUCT_FIELD,
            ) and target_sym.type_ref else target_sym.name

            type_desc = index.type_index.get_type(type_name, context_path=file_path)
            if type_desc:
                for f in type_desc.fields.values():
                    if not filter_prefix or f.name.lower().startswith(filter_prefix):
                        items.append(
                            lsp.CompletionItem(
                                label=f.name,
                                kind=lsp.CompletionItemKind.Field,
                                detail=f": {f.type_ref or 'BOOL'}",
                                documentation=f.doc_comment or None,
                            )
                        )
                for m in type_desc.methods.values():
                    if not filter_prefix or m.name.lower().startswith(filter_prefix):
                        items.append(
                            lsp.CompletionItem(
                                label=m.name,
                                kind=lsp.CompletionItemKind.Method,
                                detail=f"() : {m.type_ref}" if m.type_ref else "()",
                                documentation=m.doc_comment or None,
                                insert_text=m.name,
                            )
                        )
                for p in type_desc.properties.values():
                    if not filter_prefix or p.name.lower().startswith(filter_prefix):
                        items.append(
                            lsp.CompletionItem(
                                label=p.name,
                                kind=lsp.CompletionItemKind.Property,
                                detail=f": {p.type_ref or 'BOOL'}",
                                documentation=p.doc_comment or None,
                            )
                        )
                for em in type_desc.enum_members.values():
                    if not filter_prefix or em.name.lower().startswith(filter_prefix):
                        items.append(
                            lsp.CompletionItem(
                                label=em.name,
                                kind=lsp.CompletionItemKind.EnumMember,
                                detail=f": {type_desc.name}",
                                documentation=em.doc_comment or None,
                            )
                        )

            # Check GVL Scope if target is a GVL
            if target_sym.kind == SymbolKind.GVL:
                gvl_scope = index.symbol_table.find_gvl_scope(target_sym.name, context_path=file_path)
                if gvl_scope:
                    for s in gvl_scope.symbols.values():
                        if not filter_prefix or s.name.lower().startswith(filter_prefix):
                            items.append(
                                lsp.CompletionItem(
                                    label=s.name,
                                    kind=lsp.CompletionItemKind.Variable,
                                    detail=f": {s.type_ref or 'INT'}",
                                    documentation=s.doc_comment or None,
                                )
                            )

            # Check POU Scope if target is a POU
            if target_sym.kind in (SymbolKind.POU, SymbolKind.FUNCTION_BLOCK):
                pou_scope = index.symbol_table.find_pou_scope(target_sym.name, context_path=file_path)
                if pou_scope:
                    for s in pou_scope.symbols.values():
                        if not filter_prefix or s.name.lower().startswith(filter_prefix):
                            kind_val = (
                                lsp.CompletionItemKind.Method
                                if s.kind == SymbolKind.METHOD
                                else (
                                    lsp.CompletionItemKind.Property
                                    if s.kind == SymbolKind.PROPERTY
                                    else lsp.CompletionItemKind.Field
                                )
                            )
                            items.append(
                                lsp.CompletionItem(
                                    label=s.name,
                                    kind=kind_val,
                                    detail=f": {s.type_ref or ''}",
                                    documentation=s.doc_comment or None,
                                )
                            )

        return lsp.CompletionList(is_incomplete=False, items=items)

    # 2. General Scope Completion (Local symbols, Global symbols, Types, Keywords)
    seen: set[str] = set()

    # Local & Enclosing Scope Variables
    curr_scope: Optional[Scope] = scope
    while curr_scope is not None:
        for s in curr_scope.symbols.values():
            s_lower = s.name.lower()
            if s_lower not in seen:
                seen.add(s_lower)
                kind_val = (
                    lsp.CompletionItemKind.Method
                    if s.kind == SymbolKind.METHOD
                    else (
                        lsp.CompletionItemKind.Property
                        if s.kind == SymbolKind.PROPERTY
                        else lsp.CompletionItemKind.Variable
                    )
                )
                items.append(
                    lsp.CompletionItem(
                        label=s.name,
                        kind=kind_val,
                        detail=f": {s.type_ref or s.kind.value}",
                        documentation=s.doc_comment or None,
                    )
                )
        curr_scope = curr_scope.parent

    # Global Symbols (POUs, GVLs, Global Functions)
    for s_list in index.symbol_table.global_symbols.values():
        for s in s_list:
            s_lower = s.name.lower()
            if s_lower not in seen:
                seen.add(s_lower)
                kind_val = (
                    lsp.CompletionItemKind.Function
                    if s.kind == SymbolKind.FUNCTION
                    else (
                        lsp.CompletionItemKind.Class
                        if s.kind in (SymbolKind.FUNCTION_BLOCK, SymbolKind.POU)
                        else (
                            lsp.CompletionItemKind.Module
                            if s.kind == SymbolKind.GVL
                            else lsp.CompletionItemKind.Variable
                        )
                    )
                )
                items.append(
                    lsp.CompletionItem(
                        label=s.name,
                        kind=kind_val,
                        detail=f": {s.type_ref or s.kind.value}",
                        documentation=s.doc_comment or None,
                    )
                )

    # Types from TypeIndex (DUTs, Interfaces, FBs)
    for t in index.type_index.get_all_user_types():
        t_lower = t.name.lower()
        if t_lower not in seen:
            seen.add(t_lower)
            kind_val = (
                lsp.CompletionItemKind.Struct
                if t.kind == SymbolKind.STRUCT
                else (
                    lsp.CompletionItemKind.Enum
                    if t.kind == SymbolKind.ENUM
                    else (
                        lsp.CompletionItemKind.Interface
                        if t.kind == SymbolKind.INTERFACE
                        else lsp.CompletionItemKind.Class
                    )
                )
            )
            items.append(
                lsp.CompletionItem(
                    label=t.name,
                    kind=kind_val,
                    detail=f"({t.kind.value})",
                    documentation=t.symbol.doc_comment if t.symbol else None,
                )
            )

    # ST Keywords
    for kw in ST_KEYWORDS:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            items.append(
                lsp.CompletionItem(
                    label=kw,
                    kind=lsp.CompletionItemKind.Keyword,
                )
            )

    return lsp.CompletionList(is_incomplete=False, items=items)


def handle_document_symbol(
    index: WorkspaceIndex, params: lsp.DocumentSymbolParams
) -> list[lsp.DocumentSymbol]:
    """Handle textDocument/documentSymbol request."""
    file_path = uri_to_path(params.text_document.uri)
    indexed = index.get_file(file_path)
    if not indexed:
        return []

    symbols: list[lsp.DocumentSymbol] = []
    pou_symbol: Optional[lsp.DocumentSymbol] = None

    for sym in indexed.declared_symbols:
        doc_sym = symbol_to_document_symbol(sym)
        if sym.kind in (
            SymbolKind.POU,
            SymbolKind.FUNCTION_BLOCK,
            SymbolKind.FUNCTION,
            SymbolKind.PROGRAM,
            SymbolKind.STRUCT,
            SymbolKind.ENUM,
            SymbolKind.INTERFACE,
            SymbolKind.GVL,
        ):
            pou_symbol = doc_sym
            symbols.append(doc_sym)
        else:
            if pou_symbol is not None:
                if pou_symbol.children is None:
                    pou_symbol.children = []
                pou_symbol.children.append(doc_sym)
            else:
                symbols.append(doc_sym)

    return symbols


def handle_formatting(
    index: WorkspaceIndex,
    params: lsp.DocumentFormattingParams,
    unsaved_text: Optional[str] = None,
) -> list[lsp.TextEdit]:
    """Handle textDocument/formatting request using twincat_core + formatter."""
    from formatter.config import FormatterConfig
    from formatter.file_processor import process_file
    import tempfile

    file_path = uri_to_path(params.text_document.uri)
    config = FormatterConfig()

    text_to_format = unsaved_text
    if text_to_format is None:
        indexed = index.get_file(file_path)
        text_to_format = indexed.xml_doc.raw_text if indexed else file_path.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_p = Path(tmpdir) / file_path.name
        tmp_p.write_bytes(text_to_format.encode("utf-8"))

        res = process_file(str(tmp_p), config, format_xml=True, dry_run=False)
        if not res.success or not res.changed:
            return []

        formatted_bytes = tmp_p.read_bytes()
        formatted_text = formatted_bytes.decode("utf-8-sig" if formatted_bytes.startswith(b"\xef\xbb\xbf") else "utf-8")

    # Compute full document range
    lines = text_to_format.splitlines()
    line_count = len(lines)
    last_line_len = len(lines[-1]) if lines else 0
    full_range = lsp.Range(
        start=lsp.Position(line=0, character=0),
        end=lsp.Position(line=max(0, line_count - 1), character=last_line_len),
    )

    return [lsp.TextEdit(range=full_range, new_text=formatted_text)]


def get_diagnostics_for_file(
    index: WorkspaceIndex, file_path: Path
) -> list[lsp.Diagnostic]:
    """Retrieve syntax and semantic diagnostics for a file from WorkspaceIndex."""
    indexed = index.get_file(file_path)
    if not indexed:
        return []

    diags = list(indexed.diagnostics)
    # Add semantic analysis diagnostics
    semantic_diags = run_semantic_analysis(index, file_path)
    diags.extend(semantic_diags)

    return [diagnostic_to_lsp(d) for d in diags]
