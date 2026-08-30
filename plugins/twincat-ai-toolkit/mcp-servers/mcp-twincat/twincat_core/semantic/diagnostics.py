"""Semantic analysis and diagnostic validation for TwinCAT IEC 61131-3 code."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Set

from ..syntax.ast import PouDecl
from ..syntax.diagnostics import DiagnosticSeverity, SyntaxDiagnostic
from ..syntax.span import SourceSpan
from .symbols import SymbolKind
from .type_index import BUILTIN_TYPES

if TYPE_CHECKING:
    from ..project.workspace_index import WorkspaceIndex

RE_ARRAY_OF = re.compile(r'ARRAY\s*\[.*?\]\s*OF\s+(.+)', re.IGNORECASE | re.DOTALL)
RE_POINTER_TO = re.compile(r'POINTER\s+TO\s+(.+)', re.IGNORECASE)
RE_REFERENCE_TO = re.compile(r'REFERENCE\s+TO\s+(.+)', re.IGNORECASE)
RE_STRING_LEN = re.compile(r'^(?:W?STRING)\s*\(\s*\d+\s*\)$', re.IGNORECASE)


def extract_base_type_name(type_ref: str) -> str:
    """Extract clean base type identifier from complex type reference (ARRAY, POINTER, STRING length, FB_init params, etc.)."""
    cleaned = type_ref.strip()
    if not cleaned:
        return ""

    if RE_STRING_LEN.match(cleaned):
        return "WSTRING" if cleaned.upper().startswith("W") else "STRING"

    m_arr = RE_ARRAY_OF.match(cleaned)
    if m_arr:
        return extract_base_type_name(m_arr.group(1))

    m_ptr = RE_POINTER_TO.match(cleaned)
    if m_ptr:
        return extract_base_type_name(m_ptr.group(1))

    m_ref = RE_REFERENCE_TO.match(cleaned)
    if m_ref:
        return extract_base_type_name(m_ref.group(1))

    # Strip trailing bracketed FB_init or subrange params: e.g. "FB_Name [ ( ... ) ]" -> "FB_Name"
    if "[" in cleaned:
        cleaned = cleaned.split("[")[0].strip()

    # Strip trailing parenthesized arguments: e.g. "STRING(255)" -> "STRING", "FB_Name(1, 2)" -> "FB_Name"
    if "(" in cleaned:
        cleaned = cleaned.split("(")[0].strip()

    return cleaned


def run_semantic_analysis(index: WorkspaceIndex, file_path: Path) -> List[SyntaxDiagnostic]:
    """Perform semantic validation (type resolution, duplicate symbols) for a file."""
    indexed = index.get_file(file_path)
    if not indexed:
        return []

    diagnostics: List[SyntaxDiagnostic] = []

    # 1. Validate type existence and check duplicate identifiers
    seen_scope_names: dict[str, set[str]] = {}

    for sym in indexed.declared_symbols:
        if sym.kind in (
            SymbolKind.VARIABLE,
            SymbolKind.CONSTANT,
            SymbolKind.STRUCT_FIELD,
            SymbolKind.METHOD,
            SymbolKind.PROPERTY,
            SymbolKind.ACTION,
            SymbolKind.ENUM_MEMBER,
        ):
            # Check duplicate identifier within immediate parent scope
            parent_key = str(sym.parent_symbol.name if sym.parent_symbol else "root").lower()
            if parent_key not in seen_scope_names:
                seen_scope_names[parent_key] = set()

            name_lower = sym.name.lower()
            if name_lower in seen_scope_names[parent_key]:
                if sym.span and sym.span.start.line > 0:
                    diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Duplicate identifier '{sym.name}' in scope",
                            span=sym.span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-SEM-002",
                        )
                    )
            else:
                seen_scope_names[parent_key].add(name_lower)

        # Validate variable / field types and abstract instantiation
        if sym.kind in (SymbolKind.VARIABLE, SymbolKind.CONSTANT, SymbolKind.STRUCT_FIELD) and sym.type_ref:
            base_type = extract_base_type_name(sym.type_ref)
            if not base_type or base_type.lower() in BUILTIN_TYPES:
                continue

            # Ignore generic / runtime / system compiler keywords
            base_upper = base_type.upper().replace(" ", "")
            if base_upper in ("ANY", "ANY_TYPE", "PVOID", "__SYSTEM") or base_upper.startswith("__SYSTEM."):
                continue

            # Look up type in TypeIndex (includes project DUTs, FBs, and on-demand InfoSys MSHC types)
            type_desc = index.type_index.get_type(base_type, context_path=file_path)
            if type_desc is not None:
                # TC-SEM-005: Cannot instantiate ABSTRACT FUNCTION_BLOCK
                if type_desc.is_abstract and sym.span and sym.span.start.line > 0:
                    diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"Cannot instantiate ABSTRACT FUNCTION_BLOCK '{base_type}' in variable '{sym.name}'",
                            span=sym.span,
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-SEM-005",
                        )
                    )
                continue

            # Check if it's a global symbol or POU in symbol table
            if index.symbol_table.find_global_symbol(base_type, context_path=file_path) is not None:
                continue
            if index.symbol_table.find_pou_scope(base_type, context_path=file_path) is not None:
                continue
            if index.symbol_table.find_gvl_scope(base_type, context_path=file_path) is not None:
                continue

            # Type not found anywhere
            if sym.span and sym.span.start.line > 0:
                diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"Unknown type '{sym.type_ref}'",
                        span=sym.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-SEM-001",
                    )
                )

    # 2. Interface Conformance Validation (TC-SEM-003)
    if isinstance(indexed.top_level_ast, PouDecl) and indexed.top_level_ast.implements_names:
        pou_name = indexed.top_level_ast.name or file_path.stem
        pou_type_desc = index.type_index.get_type(pou_name, context_path=file_path)
        pou_methods = set(pou_type_desc.methods.keys()) if pou_type_desc else set()
        pou_props = set(pou_type_desc.properties.keys()) if pou_type_desc else set()

        for itf_name in indexed.top_level_ast.implements_names:
            itf_desc = index.type_index.get_type(itf_name, context_path=file_path)
            if itf_desc and itf_desc.kind == SymbolKind.INTERFACE:
                for m_name, m_sym in itf_desc.methods.items():
                    if m_name.lower() not in pou_methods:
                        diagnostics.append(
                            SyntaxDiagnostic(
                                message=f"FUNCTION_BLOCK '{pou_name}' does not implement interface '{itf_name}' method '{m_sym.name}'",
                                span=indexed.top_level_ast.span,
                                severity=DiagnosticSeverity.ERROR,
                                code="TC-SEM-003",
                            )
                        )
                for p_name, p_sym in itf_desc.properties.items():
                    if p_name.lower() not in pou_props:
                        diagnostics.append(
                            SyntaxDiagnostic(
                                message=f"FUNCTION_BLOCK '{pou_name}' does not implement interface '{itf_name}' property '{p_sym.name}'",
                                span=indexed.top_level_ast.span,
                                severity=DiagnosticSeverity.ERROR,
                                code="TC-SEM-003",
                            )
                        )

    # 3. Inheritance Cycle Detection (TC-SEM-004)
    if isinstance(indexed.top_level_ast, PouDecl) and indexed.top_level_ast.extends_name:
        pou_name = indexed.top_level_ast.name or file_path.stem
        visited = [pou_name.lower()]
        curr = indexed.top_level_ast.extends_name
        while curr:
            curr_lower = curr.lower()
            if curr_lower in visited:
                diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"Cyclic inheritance detected in '{pou_name}' (extends '{curr}')",
                        span=indexed.top_level_ast.span,
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-SEM-004",
                    )
                )
                break
            visited.append(curr_lower)
            curr_desc = index.type_index.get_type(curr, context_path=file_path)
            curr = curr_desc.extends_name if curr_desc else None

    return diagnostics
