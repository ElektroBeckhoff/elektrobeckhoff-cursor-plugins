"""Typed Abstract Syntax Tree (AST) for IEC 61131-3 ST and TwinCAT 3 extensions."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import List, Optional, Sequence, Union

from .span import SourceSpan


class AstNodeKind(StrEnum):
    # Declarations
    POU_DECL = "pou_decl"
    METHOD_DECL = "method_decl"
    PROPERTY_DECL = "property_decl"
    ACTION_DECL = "action_decl"
    INTERFACE_DECL = "interface_decl"
    TYPE_DECL = "type_decl"
    VAR_BLOCK = "var_block"
    VAR_DECL = "var_decl"
    STRUCT_TYPE = "struct_type"
    ENUM_TYPE = "enum_type"
    UNION_TYPE = "union_type"
    ENUM_MEMBER = "enum_member"

    # Statements
    ASSIGN_STMT = "assign_stmt"
    CALL_STMT = "call_stmt"
    IF_STMT = "if_stmt"
    CASE_STMT = "case_stmt"
    FOR_STMT = "for_stmt"
    WHILE_STMT = "while_stmt"
    REPEAT_STMT = "repeat_stmt"
    RETURN_STMT = "return_stmt"
    EXIT_STMT = "exit_stmt"
    CONTINUE_STMT = "continue_stmt"
    EMPTY_STMT = "empty_stmt"
    ERROR_STMT = "error_stmt"

    # Expressions
    IDENTIFIER_EXPR = "identifier_expr"
    LITERAL_EXPR = "literal_expr"
    BINARY_EXPR = "binary_expr"
    UNARY_EXPR = "unary_expr"
    MEMBER_ACCESS_EXPR = "member_access_expr"
    INDEX_EXPR = "index_expr"
    DEREF_EXPR = "deref_expr"
    CALL_EXPR = "call_expr"
    CALL_ARG = "call_arg"
    PAREN_EXPR = "paren_expr"
    RANGE_EXPR = "range_expr"
    ADDRESS_OF_EXPR = "address_of_expr"
    ERROR_EXPR = "error_expr"


@dataclass(slots=True)
class AstNode:
    """Base class for all AST nodes with exact source span."""
    span: SourceSpan


# =========================================================================
# Expressions
# =========================================================================

@dataclass(slots=True)
class Expression(AstNode):
    pass


@dataclass(slots=True)
class IdentifierExpr(Expression):
    name: str = ""


@dataclass(slots=True)
class LiteralExpr(Expression):
    value: str = ""
    literal_type: str = ""  # "INT", "REAL", "STRING", "TYPED", "BOOL", "HEX"


@dataclass(slots=True)
class BinaryExpr(Expression):
    op: str = ""
    left: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    right: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))


@dataclass(slots=True)
class UnaryExpr(Expression):
    op: str = ""
    operand: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))


@dataclass(slots=True)
class MemberAccessExpr(Expression):
    target: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    member_name: str = ""


@dataclass(slots=True)
class IndexExpr(Expression):
    target: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    indices: list[Expression] = field(default_factory=list)


@dataclass(slots=True)
class DerefExpr(Expression):
    target: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))


@dataclass(slots=True)
class CallArg(AstNode):
    name: Optional[str] = None  # None for positional, e.g. "IN" for named "IN := TRUE"
    value: Optional[Expression] = None
    assign_op: str = ":="       # ":=", "=>", "?="


@dataclass(slots=True)
class CallExpr(Expression):
    callee: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    args: list[CallArg] = field(default_factory=list)


@dataclass(slots=True)
class AddressOfExpr(Expression):
    target: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    is_ref: bool = False  # True for REF=, False for ADR()


@dataclass(slots=True)
class RangeExpr(Expression):
    start: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    end: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))


@dataclass(slots=True)
class ErrorExpr(Expression):
    raw_text: str = ""


# =========================================================================
# Statements
# =========================================================================

@dataclass(slots=True)
class Statement(AstNode):
    pass


@dataclass(slots=True)
class AssignStmt(Statement):
    target: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    value: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    assign_op: str = ":="  # ":=" or "?="


@dataclass(slots=True)
class CallStmt(Statement):
    call: CallExpr = field(default_factory=lambda: CallExpr(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))


@dataclass(slots=True)
class ElsifBranch(AstNode):
    condition: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class ElseBranch(AstNode):
    body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class IfStmt(Statement):
    condition: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    then_body: list[Statement] = field(default_factory=list)
    elsifs: list[ElsifBranch] = field(default_factory=list)
    else_branch: Optional[ElseBranch] = None


@dataclass(slots=True)
class CaseBranch(AstNode):
    values: list[Expression] = field(default_factory=list)
    body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class CaseStmt(Statement):
    expression: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    branches: list[CaseBranch] = field(default_factory=list)
    else_branch: Optional[ElseBranch] = None


@dataclass(slots=True)
class ForStmt(Statement):
    loop_var: str = ""
    start_expr: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    end_expr: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    by_expr: Optional[Expression] = None
    body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class WhileStmt(Statement):
    condition: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class RepeatStmt(Statement):
    condition: Expression = field(default_factory=lambda: Expression(span=SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)))
    body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class ReturnStmt(Statement):
    pass


@dataclass(slots=True)
class ExitStmt(Statement):
    pass


@dataclass(slots=True)
class ContinueStmt(Statement):
    pass


@dataclass(slots=True)
class JmpStmt(Statement):
    label: str = ""


@dataclass(slots=True)
class LabelStmt(Statement):
    label: str = ""


@dataclass(slots=True)
class TryCatchStmt(Statement):
    try_body: list[Statement] = field(default_factory=list)
    catch_var: Optional[str] = None
    catch_body: list[Statement] = field(default_factory=list)
    finally_body: list[Statement] = field(default_factory=list)


@dataclass(slots=True)
class EmptyStmt(Statement):
    pass


@dataclass(slots=True)
class ErrorStmt(Statement):
    raw_text: str = ""


# =========================================================================
# Declarations
# =========================================================================

@dataclass(slots=True)
class PragmaAttribute(AstNode):
    name: str = ""
    value: Optional[str] = None
    raw_text: str = ""


@dataclass(slots=True)
class VarDecl(AstNode):
    name: str = ""
    type_name: str = ""
    initial_value: Optional[str] = None
    comment: Optional[str] = None
    pragmas: list[PragmaAttribute] = field(default_factory=list)
    address: Optional[str] = None  # e.g. "%I* : BOOL"
    is_constant: bool = False
    is_retain: bool = False
    is_persistent: bool = False
    is_non_retain: bool = False
    is_read_only: bool = False


@dataclass(slots=True)
class VarBlock(AstNode):
    block_type: str = "VAR"  # VAR, VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT, VAR_GLOBAL, VAR_TEMP, VAR_STAT, VAR_INST, VAR_CONFIG, VAR_EXTERNAL, VAR_GENERIC CONSTANT
    is_constant: bool = False
    is_retain: bool = False
    is_persistent: bool = False
    is_non_retain: bool = False
    is_read_only: bool = False
    variables: list[VarDecl] = field(default_factory=list)
    pragmas: list[PragmaAttribute] = field(default_factory=list)


@dataclass(slots=True)
class EnumMember(AstNode):
    name: str = ""
    value: Optional[str] = None
    comment: Optional[str] = None
    pragmas: list[PragmaAttribute] = field(default_factory=list)


@dataclass(slots=True)
class EnumType(AstNode):
    base_type: str = "INT"
    members: list[EnumMember] = field(default_factory=list)


@dataclass(slots=True)
class StructType(AstNode):
    fields: list[VarDecl] = field(default_factory=list)
    extends_type: Optional[str] = None


@dataclass(slots=True)
class UnionType(AstNode):
    fields: list[VarDecl] = field(default_factory=list)


@dataclass(slots=True)
class TypeDecl(AstNode):
    name: str = ""
    definition: Union[EnumType, StructType, UnionType, str] = ""
    extends_type: Optional[str] = None
    access_modifier: str = "PUBLIC"  # PUBLIC, PROTECTED, PRIVATE, INTERNAL
    pragmas: list[PragmaAttribute] = field(default_factory=list)
    comment: Optional[str] = None


@dataclass(slots=True)
class InterfaceDecl(AstNode):
    name: str = ""
    extends_interfaces: list[str] = field(default_factory=list)
    methods: list["MethodDecl"] = field(default_factory=list)
    properties: list["PropertyDecl"] = field(default_factory=list)
    comment: Optional[str] = None
    pragmas: list[PragmaAttribute] = field(default_factory=list)


@dataclass(slots=True)
class MethodDecl(AstNode):
    name: str = ""
    return_type: Optional[str] = None
    access_modifier: str = "PUBLIC"  # PUBLIC, PROTECTED, PRIVATE, INTERNAL
    is_abstract: bool = False
    is_final: bool = False
    var_blocks: list[VarBlock] = field(default_factory=list)
    comment: Optional[str] = None
    pragmas: list[PragmaAttribute] = field(default_factory=list)


@dataclass(slots=True)
class PropertyDecl(AstNode):
    name: str = ""
    type_name: str = ""
    access_modifier: str = "PUBLIC"
    is_abstract: bool = False
    var_blocks: list[VarBlock] = field(default_factory=list)
    comment: Optional[str] = None
    pragmas: list[PragmaAttribute] = field(default_factory=list)


@dataclass(slots=True)
class PouDecl(AstNode):
    pou_type: str = "FUNCTION_BLOCK"  # FUNCTION_BLOCK, PROGRAM, FUNCTION
    name: str = ""
    return_type: Optional[str] = None
    extends_name: Optional[str] = None
    implements_names: list[str] = field(default_factory=list)
    access_modifier: str = "PUBLIC"
    is_abstract: bool = False
    is_final: bool = False
    var_blocks: list[VarBlock] = field(default_factory=list)
    comment: Optional[str] = None
    pragmas: list[PragmaAttribute] = field(default_factory=list)


@dataclass(slots=True)
class ActionDecl(AstNode):
    name: str = ""
    var_blocks: list[VarBlock] = field(default_factory=list)
    comment: Optional[str] = None
    pragmas: list[PragmaAttribute] = field(default_factory=list)
