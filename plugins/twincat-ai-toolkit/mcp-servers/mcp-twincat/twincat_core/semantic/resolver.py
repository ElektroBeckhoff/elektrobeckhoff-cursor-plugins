"""Symbol resolution engine for Level 1 (Local), Level 2 (Member/OOP), Level 3 (Global/GVL), Level 4 (Chains), and Level 5 (Libraries)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from ..syntax.ast import (
    AddressOfExpr,
    BinaryExpr,
    CallExpr,
    DerefExpr,
    Expression,
    IdentifierExpr,
    IndexExpr,
    LiteralExpr,
    MemberAccessExpr,
    UnaryExpr,
)
from ..syntax.span import SourceSpan
from .scopes import Scope, ScopeKind
from .symbol_table import SymbolTable
from .symbols import Symbol, SymbolKind
from .type_index import TypeIndex


class SymbolResolver:
    """Performs multi-level symbol resolution and type inference with proximity support."""

    def __init__(self, symbol_table: SymbolTable, type_index: TypeIndex) -> None:
        self.symbol_table = symbol_table
        self.type_index = type_index

    def _get_context_path(self, current_scope: Optional[Scope]) -> Optional[Path]:
        if not current_scope:
            return None
        pou = self._find_enclosing_pou_scope(current_scope)
        if pou and pou.owner_symbol and pou.owner_symbol.file_path:
            return pou.owner_symbol.file_path
        if current_scope.owner_symbol and current_scope.owner_symbol.file_path:
            return current_scope.owner_symbol.file_path
        return None

    # =========================================================================
    # Level 1: Local & Lexical Resolution
    # =========================================================================

    def resolve_identifier(self, name: str, current_scope: Scope) -> Optional[Symbol]:
        """Resolve an unqualified identifier using Level 1 -> Level 2 -> Level 3 search rules."""
        if not name:
            return None

        context_path = self._get_context_path(current_scope)

        # 1. Level 1: Hierarchical Scope Walk (Local variables, Temp, Inputs, Outputs, Shadowing)
        sym = current_scope.resolve_hierarchical(name)
        if sym is not None:
            return sym

        # 2. Level 2: FB Inheritance Search (Base class variables/methods/properties if within POU/Method)
        pou_scope = self._find_enclosing_pou_scope(current_scope)
        if pou_scope and pou_scope.owner_symbol:
            fb_type_name = pou_scope.owner_symbol.name
            # Check fields in base classes
            inherited_field = self.type_index.find_field(fb_type_name, name, inherit=True, context_path=context_path)
            if inherited_field:
                return inherited_field
            # Check methods in base classes
            inherited_method = self.type_index.find_method(fb_type_name, name, inherit=True, context_path=context_path)
            if inherited_method:
                return inherited_method
            # Check properties in base classes
            inherited_prop = self.type_index.find_property(fb_type_name, name, inherit=True, context_path=context_path)
            if inherited_prop:
                return inherited_prop

        # 3. Level 3: GVL search (unqualified GVL variables from GVLs without {attribute 'qualified_only'})
        for gvl_candidates in self.symbol_table.gvl_scopes.values():
            for _, gvl_scope in gvl_candidates:
                if gvl_scope.owner_symbol and not gvl_scope.owner_symbol.qualified_only:
                    gvl_sym = gvl_scope.resolve_local(name)
                    if gvl_sym:
                        return gvl_sym

        # 4. Level 3: Global Symbols (POU names, Global Types, Functions) with proximity
        global_sym = self.symbol_table.find_global_symbol(name, context_path=context_path)
        if global_sym is not None:
            return global_sym

        # 5. Level 3: Unqualified Enum member search
        enum_sym = self.type_index.find_unqualified_enum_member(name, context_path=context_path)
        if enum_sym is not None:
            return enum_sym

        # 6. Level 5: Standard Library & Built-in types/functions (e.g. TON, R_TRIG, CONCAT)
        t_desc = self.type_index.get_type(name, context_path=context_path)
        if t_desc:
            if t_desc.symbol is not None:
                return t_desc.symbol
            synthetic_sym = Symbol(
                name=t_desc.name,
                kind=t_desc.kind,
                span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0),
                type_ref=t_desc.base_type_name or t_desc.name,
            )
            t_desc.symbol = synthetic_sym
            return synthetic_sym

        return None

    # =========================================================================
    # Level 2: Member Access & OOP Resolution
    # =========================================================================

    def resolve_member_access(
        self,
        target_type_name: str,
        member_name: str,
        current_scope: Optional[Scope] = None,
    ) -> Optional[Symbol]:
        """Resolve a member on a typed instance or type (e.g. stData.field or fbMotor.M_Start or E_State.Running)."""
        if not target_type_name or not member_name:
            return None

        context_path = self._get_context_path(current_scope)
        clean_type = self.type_index.clean_type_name(target_type_name)

        # 1. Check if target is a GVL (e.g. GVL_Sensors.fTemp)
        gvl_scope = self.symbol_table.find_gvl_scope(clean_type, context_path=context_path)
        if gvl_scope:
            return gvl_scope.resolve_local(member_name)

        # 2. Check if target is an Enum (e.g. E_Color.Red)
        enum_member = self.type_index.find_enum_member(clean_type, member_name, context_path=context_path)
        if enum_member:
            return enum_member

        # 3. Check Struct / FB fields
        field_sym = self.type_index.find_field(clean_type, member_name, inherit=True, context_path=context_path)
        if field_sym:
            return field_sym

        # 4. Check FB / Interface methods
        method_sym = self.type_index.find_method(clean_type, member_name, inherit=True, context_path=context_path)
        if method_sym:
            return method_sym

        # 5. Check Properties
        prop_sym = self.type_index.find_property(clean_type, member_name, inherit=True, context_path=context_path)
        if prop_sym:
            return prop_sym

        # 6. Level 5: Library Namespace resolution (e.g. Tc2_Standard.TON or Tc2_System.MEMCPY)
        lib_types = self.type_index.get_library_types(clean_type)
        if lib_types or clean_type.lower().startswith("tc") or clean_type.lower() in ("standard", "system", "utilities", "iot"):
            # 1. Check global functions first (e.g. conversions)
            fn_sym = self.symbol_table.find_global_symbol(member_name, context_path=context_path)
            if fn_sym:
                return fn_sym
            # 2. Check types/FBs/functions from InfoSys / TypeIndex (e.g. TON, MEMCPY, FB_JsonSaxWriter)
            t_desc = self.type_index.get_type(member_name, context_path=context_path)
            if t_desc and t_desc.symbol:
                return t_desc.symbol
            if t_desc:
                return Symbol(
                    name=t_desc.name,
                    kind=t_desc.kind,
                    span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0),
                    type_ref=t_desc.base_type_name or t_desc.name,
                )

        return None

    def resolve_qualified_gvl(self, gvl_name: str, var_name: str, current_scope: Optional[Scope] = None) -> Optional[Symbol]:
        """Resolve a variable inside a specific GVL."""
        context_path = self._get_context_path(current_scope)
        gvl_scope = self.symbol_table.find_gvl_scope(gvl_name, context_path=context_path)
        if not gvl_scope:
            return None
        return gvl_scope.resolve_local(var_name)

    # =========================================================================
    # Level 4: Chained Member Resolution
    # =========================================================================

    def resolve_chain(
        self,
        chain_or_expr: Union[str, Expression],
        current_scope: Scope,
    ) -> Optional[Symbol]:
        """Resolve arbitrary multi-level chained member access, array indexing, and dereferencing (Level 4)."""
        if isinstance(chain_or_expr, str):
            ast_expr = self._parse_chain_string_to_expr(chain_or_expr)
            if not ast_expr:
                return None
            return self._resolve_chain_expr(ast_expr, current_scope)
        elif isinstance(chain_or_expr, Expression):
            return self._resolve_chain_expr(chain_or_expr, current_scope)
        return None

    def _resolve_chain_expr(self, expr: Expression, current_scope: Scope) -> Optional[Symbol]:
        context_path = self._get_context_path(current_scope)

        if isinstance(expr, IdentifierExpr):
            upper_name = expr.name.upper()
            if upper_name in ("THIS", "SUPER"):
                pou_scope = self._find_enclosing_pou_scope(current_scope)
                if pou_scope and pou_scope.owner_symbol:
                    if upper_name == "THIS":
                        return pou_scope.owner_symbol
                    else:
                        t_desc = self.type_index.get_type(pou_scope.owner_symbol.name, context_path=context_path)
                        if t_desc and t_desc.extends_name:
                            base_desc = self.type_index.get_type(t_desc.extends_name, context_path=context_path)
                            if base_desc and base_desc.symbol:
                                return base_desc.symbol
                            return Symbol(
                                name=t_desc.extends_name,
                                kind=SymbolKind.FUNCTION_BLOCK,
                                span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0),
                            )
            return self.resolve_identifier(expr.name, current_scope)

        if isinstance(expr, MemberAccessExpr):
            member_name = expr.member_name

            # Evaluate target expression
            target_sym = self._resolve_chain_expr(expr.target, current_scope)
            if target_sym:
                target_type = target_sym.type_ref or target_sym.name
                res = self.resolve_member_access(target_type, member_name, current_scope)
                if res:
                    return res

            target_type = self.infer_expression_type(expr.target, current_scope)
            if target_type:
                res = self.resolve_member_access(target_type, member_name, current_scope)
                if res:
                    return res

            if isinstance(expr.target, IdentifierExpr):
                res = self.resolve_member_access(expr.target.name, member_name, current_scope)
                if res:
                    return res

            return None

        if isinstance(expr, DerefExpr):
            target_sym = self._resolve_chain_expr(expr.target, current_scope)
            if target_sym and target_sym.type_ref:
                clean_target = self.type_index.clean_type_name(target_sym.type_ref)
                t_desc = self.type_index.get_type(clean_target, context_path=context_path)
                if t_desc and t_desc.symbol:
                    return t_desc.symbol
                return Symbol(
                    name=clean_target,
                    kind=SymbolKind.STRUCT,
                    span=target_sym.span,
                    type_ref=clean_target,
                )
            return target_sym

        if isinstance(expr, IndexExpr):
            target_sym = self._resolve_chain_expr(expr.target, current_scope)
            if target_sym and target_sym.type_ref:
                clean_target = self.type_index.clean_type_name(target_sym.type_ref)
                t_desc = self.type_index.get_type(clean_target, context_path=context_path)
                if t_desc and t_desc.symbol:
                    return t_desc.symbol
                return Symbol(
                    name=clean_target,
                    kind=SymbolKind.STRUCT,
                    span=target_sym.span,
                    type_ref=clean_target,
                )
            return target_sym

        if isinstance(expr, CallExpr):
            return self._resolve_chain_expr(expr.callee, current_scope)

        return None

    def infer_expression_type(self, expr: Optional[Expression], current_scope: Scope) -> Optional[str]:
        """Infer the type name of an ST expression."""
        if expr is None:
            return None
        context_path = self._get_context_path(current_scope)

        if isinstance(expr, LiteralExpr):
            if expr.literal_type == "INT_LITERAL":
                return "ANY_INT"
            if expr.literal_type == "REAL_LITERAL":
                return "ANY_REAL" if "e" not in expr.value.lower() else "LREAL"
            if expr.literal_type == "BOOL_LITERAL":
                return "BOOL"
            if expr.literal_type == "STRING_LITERAL":
                return "STRING"
            if expr.literal_type == "WSTRING_LITERAL":
                return "WSTRING"
            if expr.literal_type == "TYPED_LITERAL":
                prefix = expr.value.split("#")[0].upper()
                if prefix in ("T", "TIME"):
                    return "TIME"
                if prefix in ("LT", "LTIME"):
                    return "LTIME"
                if prefix in ("DT", "DATE_AND_TIME"):
                    return "DT"
                if prefix in ("TOD", "TIME_OF_DAY"):
                    return "TOD"
                if prefix in ("LTOD", "LTIME_OF_DAY"):
                    return "LTOD"
                if prefix in ("D", "DATE"):
                    return "DATE"
                if prefix in ("LD", "LDATE"):
                    return "LDATE"
                if prefix in ("LDT", "DATE_AND_LTIME"):
                    return "LDT"
                if prefix in ("16", "8", "2"):
                    return "ANY_INT"
                return prefix
            return "ANY_INT"

        if isinstance(expr, IdentifierExpr):
            upper_name = expr.name.upper()
            pou_scope = self._find_enclosing_pou_scope(current_scope)
            if upper_name == "THIS":
                return pou_scope.owner_symbol.name if (pou_scope and pou_scope.owner_symbol) else None
            if upper_name == "SUPER":
                if pou_scope and pou_scope.owner_symbol:
                    t_desc = self.type_index.get_type(pou_scope.owner_symbol.name, context_path=context_path)
                    return t_desc.extends_name if t_desc else None
                return None

            sym = self.resolve_identifier(expr.name, current_scope)
            return sym.type_ref if sym else None

        if isinstance(expr, MemberAccessExpr):
            target_type = self.infer_expression_type(expr.target, current_scope)
            if not target_type:
                if isinstance(expr.target, IdentifierExpr):
                    target_type = expr.target.name
            if target_type:
                member_sym = self.resolve_member_access(target_type, expr.member_name, current_scope)
                if member_sym:
                    return member_sym.type_ref

                # Optional naming fallback when target is an FB instance and member is unresolved
                # (e.g. external FB like FB_IoT_Utilities_Time where members aren't in index)
                m_name = expr.member_name
                clean_target = self.type_index.clean_type_name(target_type).upper()
                is_fb = (
                    clean_target.startswith("FB_")
                    or "TON" in clean_target
                    or "TOF" in clean_target
                    or "TP" in clean_target
                    or (isinstance(expr.target, IdentifierExpr) and expr.target.name.lower().startswith(("_fb", "fb")))
                )
                if is_fb and len(m_name) >= 2:
                    if m_name.startswith("t") and (m_name[1].isupper() or m_name[1] == "_"):
                        return "TIME"
                    if m_name.startswith("b") and (m_name[1].isupper() or m_name[1] == "_"):
                        return "BOOL"
                    if m_name.startswith("n") and (m_name[1].isupper() or m_name[1] == "_"):
                        return "DINT"
                    if m_name.startswith("f") and (m_name[1].isupper() or m_name[1] == "_"):
                        return "LREAL"
                    if m_name.startswith("s") and (m_name[1].isupper() or m_name[1] == "_"):
                        return "STRING"
                    if m_name.startswith("hr") and (m_name[1].isupper() or m_name[1] == "_"):
                        return "HRESULT"

            return None

        if isinstance(expr, DerefExpr):
            target_type = self.infer_expression_type(expr.target, current_scope)
            if target_type:
                return self.type_index.clean_type_name(target_type)
            return None

        if isinstance(expr, IndexExpr):
            target_type = self.infer_expression_type(expr.target, current_scope)
            if target_type:
                return self.type_index.clean_type_name(target_type)
            return None

        if isinstance(expr, AddressOfExpr):
            target_t = self.infer_expression_type(expr.target, current_scope)
            if target_t:
                inner_t = target_t.strip()
                while inner_t.upper().startswith("REFERENCE TO "):
                    inner_t = inner_t[13:].strip()
                if expr.is_ref:
                    return f"REFERENCE TO {inner_t}"
                return f"POINTER TO {inner_t}"
            return "PVOID"

        if isinstance(expr, CallExpr):
            if isinstance(expr.callee, IdentifierExpr):
                # 1. Standard IEC Conversion Functions & Builtins
                upper_callee = expr.callee.name.upper()
                if upper_callee.startswith("TO_"):
                    return upper_callee[3:]
                if "_TO_" in upper_callee:
                    return upper_callee.split("_TO_")[-1]
                if upper_callee in ("SIZEOF", "XSIZEOF", "LEN", "BITADR", "INDEXOF"):
                    return "UDINT"
                if upper_callee in ("LOWER_BOUND", "UPPER_BOUND"):
                    return "DINT"
                if upper_callee in ("__ISVALIDREF", "__QUERYINTERFACE", "__QUERYPOINTER"):
                    return "BOOL"
                if upper_callee in ("__POUNAME", "__POSITION"):
                    return "STRING"
                if upper_callee in ("CONCAT", "MID", "LEFT", "RIGHT", "INSERT", "DELETE", "REPLACE"):
                    return "STRING"
                if upper_callee in ("WCONCAT", "WMID", "WLEFT", "WRIGHT", "WINSERT", "WDELETE", "WREPLACE"):
                    return "WSTRING"
                if upper_callee in ("ABS", "SQRT", "LN", "LOG", "EXP", "SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN", "TRUNC", "ROUND", "FLOOR", "CEIL", "EXPT"):
                    if expr.args:
                        return self.infer_expression_type(expr.args[0].value, current_scope) or "LREAL"
                    return "LREAL"
                if upper_callee == "SEL":
                    if len(expr.args) >= 3:
                        return self.infer_expression_type(expr.args[1].value, current_scope) or self.infer_expression_type(expr.args[2].value, current_scope)
                    elif len(expr.args) >= 2:
                        return self.infer_expression_type(expr.args[1].value, current_scope)
                    return "ANY"
                if upper_callee == "MUX":
                    if len(expr.args) >= 2:
                        choice_types = [self.infer_expression_type(a.value, current_scope) for a in expr.args[1:]]
                        if any(t == "LREAL" for t in choice_types if t):
                            return "LREAL"
                        if any(t == "REAL" for t in choice_types if t):
                            return "REAL"
                        if any(t == "ANY_REAL" for t in choice_types if t):
                            return "ANY_REAL"
                        first_t = next((t for t in choice_types if t and t not in ("ANY_INT", "ANY_REAL", "ANY")), None)
                        return first_t or choice_types[0] or "ANY"
                    return "ANY"
                if upper_callee == "LIMIT":
                    if len(expr.args) >= 2:
                        return self.infer_expression_type(expr.args[1].value, current_scope) or self.infer_expression_type(expr.args[0].value, current_scope)
                    elif expr.args:
                        return self.infer_expression_type(expr.args[0].value, current_scope)
                    return "ANY_NUM"
                if upper_callee in ("MIN", "MAX"):
                    if expr.args:
                        arg_types = [self.infer_expression_type(a.value, current_scope) for a in expr.args]
                        if any(t == "LREAL" for t in arg_types if t):
                            return "LREAL"
                        if any(t == "REAL" for t in arg_types if t):
                            return "REAL"
                        if any(t == "ANY_REAL" for t in arg_types if t):
                            return "ANY_REAL"
                        first_t = next((t for t in arg_types if t and t not in ("ANY_INT", "ANY_REAL", "ANY")), None)
                        return first_t or arg_types[0] or "ANY_NUM"
                    return "ANY_NUM"
                if upper_callee in ("SHL", "SHR", "ROL", "ROR"):
                    if expr.args:
                        return self.infer_expression_type(expr.args[0].value, current_scope) or "ANY_BIT"
                    return "ANY_BIT"
                if upper_callee == "ADR":
                    if expr.args:
                        target_t = self.infer_expression_type(expr.args[0].value, current_scope)
                        if target_t:
                            return f"POINTER TO {target_t}"
                    return "PVOID"
                if upper_callee == "ADRINST":
                    return "PVOID"

                # 2. Scope-resolved functions / methods / POUs
                func_sym = self.resolve_identifier(expr.callee.name, current_scope)
                if func_sym and func_sym.type_ref:
                    return func_sym.type_ref

            callee_type = self.infer_expression_type(expr.callee, current_scope)
            if callee_type:
                return callee_type
            return None

        if isinstance(expr, BinaryExpr):
            op = expr.op.upper()
            if op in ("=", "<>", "<", ">", "<=", ">="):
                return "BOOL"
            if op in (":=", "REF=", "?="):
                return self.infer_expression_type(expr.right, current_scope) or self.infer_expression_type(expr.left, current_scope)
            if op in ("AND", "OR", "XOR"):
                left_t = self.infer_expression_type(expr.left, current_scope)
                right_t = self.infer_expression_type(expr.right, current_scope)
                # Use raw upper type strings — do NOT use clean_type_name (strips POINTER TO)
                clean_l = left_t.upper().strip() if left_t else ""
                clean_r = right_t.upper().strip() if right_t else ""
                # Bitwise operations on BYTE, WORD, DWORD, LWORD or integer types
                if clean_l and clean_l not in ("BOOL", "BIT", "ANY_INT"):
                    return left_t
                if clean_r and clean_r not in ("BOOL", "BIT", "ANY_INT"):
                    return right_t
                if clean_l == "ANY_INT" or clean_r == "ANY_INT":
                    return "ANY_INT"
                return "BOOL"
            if op in ("+", "-", "*", "/", "MOD", "EXPT"):
                left_t = self.infer_expression_type(expr.left, current_scope)
                right_t = self.infer_expression_type(expr.right, current_scope)
                # Preserve POINTER TO / REFERENCE TO — clean_type_name would strip them
                clean_l = left_t.upper().strip() if left_t else ""
                clean_r = right_t.upper().strip() if right_t else ""
                if clean_l == "LREAL" or clean_r == "LREAL":
                    return "LREAL"
                if clean_l == "REAL" or clean_r == "REAL":
                    return "REAL"
                if clean_l and clean_l not in ("ANY_INT", "ANY_REAL", "ANY"):
                    return left_t
                if clean_r and clean_r not in ("ANY_INT", "ANY_REAL", "ANY"):
                    return right_t
                return left_t or right_t
            return None

        if isinstance(expr, UnaryExpr):
            if expr.op.upper() == "NOT":
                operand_t = self.infer_expression_type(expr.operand, current_scope)
                if operand_t:
                    clean_op = operand_t.upper().strip()
                    if clean_op not in ("BOOL", "BIT"):
                        return operand_t
                return "BOOL"
            return self.infer_expression_type(expr.operand, current_scope)

        return None

    def _find_enclosing_pou_scope(self, scope: Scope) -> Optional[Scope]:
        curr: Optional[Scope] = scope
        while curr is not None:
            if curr.kind == ScopeKind.POU:
                return curr
            curr = curr.parent
        return None

    def _parse_chain_string_to_expr(self, s: str) -> Optional[Expression]:
        from ..syntax.lexer import Lexer
        from ..syntax.parser_statements import StatementParser
        try:
            lexer = Lexer(s)
            tokens = lexer.tokenize_all(include_trivia=False)
            parser = StatementParser(tokens, lexer.diagnostics)
            return parser.parse_expression()
        except Exception:
            return None
