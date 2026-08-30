"""Concrete Syntax Tree (CST) nodes for 100% loss-free syntax tree representation."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Sequence, Union

from .span import SourceSpan
from .tokens import Token


class CstNodeKind(StrEnum):
    DECLARATION_ROOT = "declaration_root"
    POU_SIGNATURE = "pou_signature"
    METHOD_SIGNATURE = "method_signature"
    PROPERTY_SIGNATURE = "property_signature"
    INTERFACE_SIGNATURE = "interface_signature"
    TYPE_SIGNATURE = "type_signature"
    VAR_BLOCK = "var_block"
    VAR_DECLARATION = "var_declaration"
    STRUCT_BLOCK = "struct_block"
    ENUM_BLOCK = "enum_block"
    UNION_BLOCK = "union_block"
    ENUM_MEMBER = "enum_member"
    STATEMENT_BLOCK = "statement_block"
    ASSIGN_STMT = "assign_stmt"
    CALL_STMT = "call_stmt"
    IF_STMT = "if_stmt"
    ELSIF_BRANCH = "elsif_branch"
    ELSE_BRANCH = "else_branch"
    CASE_STMT = "case_stmt"
    CASE_BRANCH = "case_branch"
    FOR_STMT = "for_stmt"
    WHILE_STMT = "while_stmt"
    REPEAT_STMT = "repeat_stmt"
    RETURN_STMT = "return_stmt"
    EXIT_STMT = "exit_stmt"
    CONTINUE_STMT = "continue_stmt"
    JMP_STMT = "jmp_stmt"
    LABEL_STMT = "label_stmt"
    TRY_CATCH_STMT = "try_catch_stmt"
    EXPRESSION = "expression"
    ERROR_NODE = "error_node"


CstElement = Union[Token, "CstNode"]


@dataclass(slots=True)
class CstNode:
    """A CST node holding child tokens, child CST nodes, and the enclosing span."""
    kind: CstNodeKind
    span: SourceSpan
    children: list[CstElement] = field(default_factory=list)

    def get_tokens(self) -> list[Token]:
        """Flatten all terminal tokens contained within this subtree in source order."""
        tokens: list[Token] = []
        for child in self.children:
            if isinstance(child, Token):
                tokens.append(child)
            else:
                tokens.extend(child.get_tokens())
        return tokens

    def to_text(self) -> str:
        """Reconstruct the original text from all terminal tokens."""
        return "".join(t.value for t in self.get_tokens())

    def __repr__(self) -> str:
        return f"CstNode({self.kind.value}, {self.span}, children={len(self.children)})"
