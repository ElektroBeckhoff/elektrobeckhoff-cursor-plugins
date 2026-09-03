"""Semantic analysis and diagnostic validation for TwinCAT IEC 61131-3 code."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Set

from ..syntax.ast import (
    AddressOfExpr,
    AssignStmt,
    BinaryExpr,
    CallArg,
    CallExpr,
    CallStmt,
    CaseStmt,
    DerefExpr,
    Expression,
    ForStmt,
    IdentifierExpr,
    IfStmt,
    IndexExpr,
    LiteralExpr,
    MemberAccessExpr,
    PouDecl,
    RangeExpr,
    RepeatStmt,
    Statement,
    UnaryExpr,
    WhileStmt,
)
from ..syntax.diagnostics import DiagnosticSeverity, SyntaxDiagnostic
from ..syntax.parser_statements import StatementParser
from ..syntax.span import SourceSpan, offset_to_line_col
from .scopes import Scope
from .symbols import SymbolKind
from .type_compatibility import TypeCheckResultKind, check_type_assignment, _clean_type_str
from .type_index import BUILTIN_TYPES

if TYPE_CHECKING:
    from ..project.workspace_index import WorkspaceIndex

_RE_PREFIX = re.compile(r"^(?:VAR_INST|VAR_STAT|VAR_TEMP|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR)\s+", re.IGNORECASE)
RE_ARRAY_OF = re.compile(r'ARRAY\s*\[.*?\]\s*OF\s+(.+)', re.IGNORECASE | re.DOTALL)
RE_POINTER_TO = re.compile(r'POINTER\s+TO\s+(.+)', re.IGNORECASE)
RE_REFERENCE_TO = re.compile(r'REFERENCE\s+TO\s+(.+)', re.IGNORECASE)
RE_STRING_LEN = re.compile(r'^(?:W?STRING)\s*\(\s*\d+\s*\)$', re.IGNORECASE)


def extract_base_type_name(type_ref: str) -> str:
    """Extract clean base type identifier from complex type reference (ARRAY, POINTER, STRING length, FB_init params, etc.)."""
    cleaned = type_ref.strip()
    if not cleaned:
        return ""

    cleaned = _RE_PREFIX.sub("", cleaned).strip()
    if ":" in cleaned:
        cleaned = cleaned.rsplit(":", 1)[-1].strip()

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


def _fast_infer_literal_type(val: str) -> Optional[str]:
    """Fast type inference for common literal initial values without StatementParser."""
    v_upper = val.upper()
    if v_upper in ("TRUE", "FALSE"):
        return "BOOL"
    if (val.startswith("'") and val.endswith("'")) or v_upper.startswith("STRING#'"):
        return "STRING_LITERAL"
    if (val.startswith('"') and val.endswith('"')) or v_upper.startswith("WSTRING#\""):
        return "WSTRING_LITERAL"
    if v_upper.startswith(("T#", "TIME#", "LT#", "LTIME#", "D#", "DATE#", "LD#", "LDATE#", "TOD#", "TIME_OF_DAY#", "LTOD#", "LTIME_OF_DAY#", "DT#", "DATE_AND_TIME#", "LDT#", "DATE_AND_LTIME#")):
        prefix = v_upper.split("#", 1)[0]
        if prefix in ("T", "TIME"):
            return "TIME"
        if prefix in ("LT", "LTIME"):
            return "LTIME"
        if prefix in ("D", "DATE"):
            return "DATE"
        if prefix in ("LD", "LDATE"):
            return "LDATE"
        if prefix in ("TOD", "TIME_OF_DAY"):
            return "TOD"
        if prefix in ("LTOD", "LTIME_OF_DAY"):
            return "LTOD"
        if prefix in ("DT", "DATE_AND_TIME"):
            return "DT"
        if prefix in ("LDT", "DATE_AND_LTIME"):
            return "LDT"
        return prefix
    if v_upper.startswith(("INT#", "DINT#", "SINT#", "LINT#", "UINT#", "UDINT#", "USINT#", "ULINT#", "BYTE#", "WORD#", "DWORD#", "LWORD#", "REAL#", "LREAL#")):
        return v_upper.split("#", 1)[0]
    if v_upper.startswith(("16#", "8#", "2#")):
        return "INT_LITERAL"
    if val.isdigit() or (val.startswith(("-", "+")) and val[1:].isdigit()):
        return "INT_LITERAL"
    if "." in val:
        parts = val.split(".")
        if len(parts) == 2 and (parts[0].isdigit() or (parts[0].startswith(("-", "+")) and parts[0][1:].isdigit())) and parts[1].isdigit():
            return "REAL_LITERAL"
    return None


def _has_unresolved_base_class(
    pou_name: str,
    type_index: Any,
    context_path: Optional[Path] = None,
) -> bool:
    """Check if any base class in the EXTENDS chain cannot be found in TypeIndex."""
    visited = set()
    curr_name: Optional[str] = pou_name
    while curr_name:
        clean = type_index.clean_type_name(curr_name)
        key = clean.lower()
        if not key or key in visited:
            break
        visited.add(key)
        t_desc = type_index.get_type(clean, context_path=context_path)
        if not t_desc:
            return True
        if not t_desc.extends_name:
            break
        curr_name = t_desc.extends_name
    return False


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

            # TC-SEM-001 (Unknown type) is deactivated to prevent false positives when working
            # with custom external libraries (*.compiled-library) whose source types are not indexed.

    # 2. Interface Conformance Validation (TC-SEM-003)
    if (
        isinstance(indexed.top_level_ast, PouDecl)
        and indexed.top_level_ast.implements_names
        and not indexed.top_level_ast.is_abstract
    ):
        pou_name = indexed.top_level_ast.name or file_path.stem
        pou_type_desc = index.type_index.get_type(pou_name, context_path=file_path)
        if not (pou_type_desc and pou_type_desc.is_abstract):
            pou_methods = index.type_index.get_all_methods(pou_name, context_path=file_path)
            pou_props = index.type_index.get_all_properties(pou_name, context_path=file_path)

            for itf_name in indexed.top_level_ast.implements_names:
                itf_desc = index.type_index.get_type(itf_name, context_path=file_path)
                if itf_desc and itf_desc.kind == SymbolKind.INTERFACE:
                    req_methods = index.type_index.get_all_methods(itf_name, context_path=file_path)
                    req_props = index.type_index.get_all_properties(itf_name, context_path=file_path)

                    for m_name, m_sym in req_methods.items():
                        if m_name.lower() not in pou_methods:
                            if _has_unresolved_base_class(pou_name, index.type_index, file_path):
                                continue
                            diagnostics.append(
                                SyntaxDiagnostic(
                                    message=f"FUNCTION_BLOCK '{pou_name}' does not implement interface '{itf_name}' method '{m_sym.name}'",
                                    span=indexed.top_level_ast.span,
                                    severity=DiagnosticSeverity.ERROR,
                                    code="TC-SEM-003",
                                )
                            )
                    for p_name, p_sym in req_props.items():
                        if p_name.lower() not in pou_props:
                            if _has_unresolved_base_class(pou_name, index.type_index, file_path):
                                continue
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

    # 4. Initial Value Type Validation for Declared Symbols
    for sym in indexed.declared_symbols:
        if (
            sym.kind in (SymbolKind.VARIABLE, SymbolKind.CONSTANT, SymbolKind.STRUCT_FIELD)
            and sym.initial_value
            and sym.type_ref
        ):
            init_val = sym.initial_value.strip()
            # Skip composite struct/array constructors to avoid false positives on nested elements
            if not init_val.startswith("(") and not init_val.startswith("["):
                try:
                    init_t = _fast_infer_literal_type(init_val)
                    if not init_t:
                        p = StatementParser.from_source(init_val)
                        init_expr = p.parse_expression()
                        if init_expr:
                            _validate_expression_identifiers(
                                init_expr,
                                index.symbol_table.global_scope,
                                index,
                                file_path,
                                diagnostics,
                                line_offset=sym.span.start.line - 1 if sym.span else 0,
                                col_offset=sym.span.start.column - 1 if sym.span else 0,
                                char_offset=sym.span.start.offset if sym.span else 0,
                            )
                            init_t = index.resolver.infer_expression_type(init_expr, index.symbol_table.global_scope)
                    if init_t:
                        res = check_type_assignment(sym.type_ref, init_t, index.type_index, file_path)
                        if res.kind == TypeCheckResultKind.TYPE_MISMATCH_ERROR and sym.span and sym.span.start.line > 0:
                            diagnostics.append(
                                SyntaxDiagnostic(
                                    message=f"Initial value for '{sym.name}': {res.message}",
                                    span=sym.span,
                                    severity=DiagnosticSeverity.ERROR,
                                    code="TC-SEM-006",
                                )
                            )
                        elif res.kind == TypeCheckResultKind.NARROWING_WARNING and sym.span and sym.span.start.line > 0:
                            diagnostics.append(
                                SyntaxDiagnostic(
                                    message=f"Initial value for '{sym.name}': {res.message}",
                                    span=sym.span,
                                    severity=DiagnosticSeverity.WARNING,
                                    code="TC-SEM-007",
                                )
                            )
                except Exception:
                    pass

    # 5. Implementation Statements Type & Conversion Validation (TC-SEM-006, TC-SEM-007)
    for cdata_span, scope, stmts in indexed.implementation_statements:
        cdata_start_line, cdata_start_col = offset_to_line_col(indexed.xml_doc.raw_text, cdata_span.content_start)
        line_offset = cdata_start_line - 1
        col_offset = cdata_start_col - 1
        char_offset = cdata_span.content_start

        for stmt in stmts:
            _validate_statement(stmt, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    return diagnostics


BUILTIN_KEYWORDS = {
    "THIS", "SUPER", "TRUE", "FALSE", "NULL", "16#0", "0",
}

TC_4026_KEYWORDS: dict[str, str] = {
    "__POSITION": "TwinCAT 3.1 Build 4026 or higher",
    "__POUNAME": "TwinCAT 3.1 Build 4026 or higher",
}

BUILTIN_FUNCS = {
    "SIZEOF", "XSIZEOF", "LEN", "BITADR", "INDEXOF", "LOWER_BOUND", "UPPER_BOUND",
    "CONCAT", "MID", "LEFT", "RIGHT", "INSERT", "DELETE", "REPLACE",
    "WCONCAT", "WMID", "WLEFT", "WRIGHT", "WINSERT", "WDELETE", "WREPLACE",
    "ABS", "SQRT", "LN", "LOG", "EXP", "SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN",
    "TRUNC", "ROUND", "FLOOR", "CEIL", "EXPT", "SEL", "MUX", "LIMIT", "MIN", "MAX",
    "SHL", "SHR", "ROL", "ROR", "ADR", "ADRINST", "TEST_AND_SET", "TESTANDSET",
    "__SYSTEM", "__QUERYINTERFACE", "__QUERYPOINTER", "__ISVALIDREF", "__POUNAME", "__POSITION", "__VARINFO",
}


def _validate_expression_identifiers(
    expr: Optional[Expression],
    scope: Scope,
    index: WorkspaceIndex,
    file_path: Path,
    diagnostics: list[SyntaxDiagnostic],
    line_offset: int = 0,
    col_offset: int = 0,
    char_offset: int = 0,
) -> None:
    if expr is None:
        return

    def _offset(s: Optional[SourceSpan]) -> SourceSpan:
        if s is None:
            return SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)
        return s.offset_by(line_offset, col_offset, char_offset)

    if isinstance(expr, IdentifierExpr):
        name = expr.name.strip()
        name_upper = name.upper()
        if not name:
            return
        if name_upper in TC_4026_KEYWORDS:
            diagnostics.append(
                SyntaxDiagnostic(
                    message=f"Operator '{name}' requires {TC_4026_KEYWORDS[name_upper]}",
                    span=_offset(expr.span),
                    severity=DiagnosticSeverity.WARNING,
                    code="TC-SEM-4026",
                )
            )
            return
        if name_upper in BUILTIN_KEYWORDS or name_upper.startswith("__") or name_upper.startswith("%"):
            return
        if name_upper.startswith("TO_") or "_TO_" in name_upper:
            return
        if name_upper in BUILTIN_FUNCS:
            return
        if index.resolver.resolve_identifier(name, scope) is not None:
            return
        if index.type_index.get_type(name, context_path=file_path) is not None:
            return
        if index.type_index.find_unqualified_enum_member(name, context_path=file_path) is not None:
            return
        if index.symbol_table.find_gvl_scope(name, context_path=file_path) is not None:
            return
        if index.symbol_table.find_pou_scope(name, context_path=file_path) is not None:
            return
        if index.symbol_table.find_global_symbol(name, context_path=file_path) is not None:
            return

        # TC-SEM-008 (Undeclared identifier) is deactivated to prevent false positives when referencing
        # external library enums, GVLs, POUs, and symbols from unindexed compiled libraries.

    elif isinstance(expr, MemberAccessExpr):
        _validate_expression_identifiers(expr.target, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(expr, IndexExpr):
        _validate_expression_identifiers(expr.target, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        for idx_e in expr.indices:
            _validate_expression_identifiers(idx_e, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(expr, CallExpr):
        _validate_expression_identifiers(expr.callee, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        for arg in expr.args:
            if arg.value is not None:
                _validate_expression_identifiers(arg.value, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(expr, BinaryExpr):
        _validate_expression_identifiers(expr.left, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        _validate_expression_identifiers(expr.right, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(expr, UnaryExpr):
        _validate_expression_identifiers(expr.operand, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(expr, AddressOfExpr):
        _validate_expression_identifiers(expr.target, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(expr, DerefExpr):
        _validate_expression_identifiers(expr.target, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(expr, RangeExpr):
        _validate_expression_identifiers(expr.start, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        _validate_expression_identifiers(expr.end, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)


def _validate_statement(
    stmt: Statement,
    scope: Scope,
    index: WorkspaceIndex,
    file_path: Path,
    diagnostics: list[SyntaxDiagnostic],
    line_offset: int = 0,
    col_offset: int = 0,
    char_offset: int = 0,
) -> None:
    def _offset(s: Optional[SourceSpan]) -> SourceSpan:
        if s is None:
            return SourceSpan.from_bounds(1, 1, 0, 1, 1, 0)
        return s.offset_by(line_offset, col_offset, char_offset)

    if isinstance(stmt, AssignStmt):
        _validate_expression_identifiers(stmt.target, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        _validate_expression_identifiers(stmt.value, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

        target_t = index.resolver.infer_expression_type(stmt.target, scope)
        value_t = index.resolver.infer_expression_type(stmt.value, scope)
        if target_t and value_t:
            effective_target_t = target_t
            if stmt.assign_op == ":=" and target_t.upper().startswith("REFERENCE TO"):
                effective_target_t = target_t[12:].strip()
            res = check_type_assignment(effective_target_t, value_t, index.type_index, file_path)
            if res.kind == TypeCheckResultKind.TYPE_MISMATCH_ERROR:
                diagnostics.append(
                    SyntaxDiagnostic(
                        message=res.message or f"Cannot convert type '{value_t}' to '{target_t}'",
                        span=_offset(stmt.span),
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-SEM-006",
                    )
                )
            elif res.kind == TypeCheckResultKind.NARROWING_WARNING:
                diagnostics.append(
                    SyntaxDiagnostic(
                        message=res.message or f"Implicit conversion from '{value_t}' to '{target_t}'",
                        span=_offset(stmt.span),
                        severity=DiagnosticSeverity.WARNING,
                        code="TC-SEM-007",
                    )
                )

    elif isinstance(stmt, CallStmt):
        _validate_expression_identifiers(stmt.call, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(stmt, IfStmt):
        _validate_expression_identifiers(stmt.condition, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        cond_t = index.resolver.infer_expression_type(stmt.condition, scope)
        cond_clean = _clean_type_str(cond_t) if cond_t else ""
        if cond_clean and cond_clean not in ("BOOL", "BIT", "ANY", "ANY_TYPE", "PVOID") and not cond_clean.startswith("__SYSTEM"):
            diagnostics.append(
                SyntaxDiagnostic(
                    message=f"IF condition expression must be of type 'BOOL', found '{cond_t}'",
                    span=_offset(stmt.condition.span),
                    severity=DiagnosticSeverity.ERROR,
                    code="TC-SEM-006",
                )
            )
        for s in stmt.then_body:
            _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        for branch in stmt.elsifs:
            _validate_expression_identifiers(branch.condition, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
            b_cond_t = index.resolver.infer_expression_type(branch.condition, scope)
            b_cond_clean = _clean_type_str(b_cond_t) if b_cond_t else ""
            if b_cond_clean and b_cond_clean not in ("BOOL", "BIT", "ANY", "ANY_TYPE", "PVOID") and not b_cond_clean.startswith("__SYSTEM"):
                diagnostics.append(
                    SyntaxDiagnostic(
                        message=f"ELSIF condition expression must be of type 'BOOL', found '{b_cond_t}'",
                        span=_offset(branch.condition.span),
                        severity=DiagnosticSeverity.ERROR,
                        code="TC-SEM-006",
                    )
                )
            for s in branch.body:
                _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        if stmt.else_branch:
            for s in stmt.else_branch.body:
                _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(stmt, WhileStmt):
        _validate_expression_identifiers(stmt.condition, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        cond_t = index.resolver.infer_expression_type(stmt.condition, scope)
        cond_clean = _clean_type_str(cond_t) if cond_t else ""
        if cond_clean and cond_clean not in ("BOOL", "BIT", "ANY", "ANY_TYPE", "PVOID") and not cond_clean.startswith("__SYSTEM"):
            diagnostics.append(
                SyntaxDiagnostic(
                    message=f"WHILE condition expression must be of type 'BOOL', found '{cond_t}'",
                    span=_offset(stmt.condition.span),
                    severity=DiagnosticSeverity.ERROR,
                    code="TC-SEM-006",
                )
            )
        for s in stmt.body:
            _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(stmt, RepeatStmt):
        _validate_expression_identifiers(stmt.condition, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        cond_t = index.resolver.infer_expression_type(stmt.condition, scope)
        cond_clean = _clean_type_str(cond_t) if cond_t else ""
        if cond_clean and cond_clean not in ("BOOL", "BIT", "ANY", "ANY_TYPE", "PVOID") and not cond_clean.startswith("__SYSTEM"):
            diagnostics.append(
                SyntaxDiagnostic(
                    message=f"REPEAT UNTIL condition expression must be of type 'BOOL', found '{cond_t}'",
                    span=_offset(stmt.condition.span),
                    severity=DiagnosticSeverity.ERROR,
                    code="TC-SEM-006",
                )
            )
        for s in stmt.body:
            _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(stmt, ForStmt):
        _validate_expression_identifiers(stmt.start_expr, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        _validate_expression_identifiers(stmt.end_expr, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        if stmt.by_expr:
            _validate_expression_identifiers(stmt.by_expr, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

        loop_var_sym = index.resolver.resolve_identifier(stmt.loop_var, scope)
        if loop_var_sym is not None and loop_var_sym.type_ref:
            start_t = index.resolver.infer_expression_type(stmt.start_expr, scope)
            end_t = index.resolver.infer_expression_type(stmt.end_expr, scope)
            if start_t:
                res_s = check_type_assignment(loop_var_sym.type_ref, start_t, index.type_index, file_path)
                if res_s.kind == TypeCheckResultKind.TYPE_MISMATCH_ERROR:
                    diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"FOR loop start value: {res_s.message}",
                            span=_offset(stmt.start_expr.span),
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-SEM-006",
                        )
                    )
            if end_t:
                res_e = check_type_assignment(loop_var_sym.type_ref, end_t, index.type_index, file_path)
                if res_e.kind == TypeCheckResultKind.TYPE_MISMATCH_ERROR:
                    diagnostics.append(
                        SyntaxDiagnostic(
                            message=f"FOR loop end value: {res_e.message}",
                            span=_offset(stmt.end_expr.span),
                            severity=DiagnosticSeverity.ERROR,
                            code="TC-SEM-006",
                        )
                    )
        for s in stmt.body:
            _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)

    elif isinstance(stmt, CaseStmt):
        _validate_expression_identifiers(stmt.expression, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        for branch in stmt.branches:
            for val_e in branch.values:
                _validate_expression_identifiers(val_e, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
            for s in branch.body:
                _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
        if stmt.else_branch:
            for s in stmt.else_branch.body:
                _validate_statement(s, scope, index, file_path, diagnostics, line_offset, col_offset, char_offset)
