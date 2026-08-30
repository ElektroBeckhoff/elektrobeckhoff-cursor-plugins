"""Symbol definitions and symbol metadata for TwinCAT semantic analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Optional

from ..syntax.span import SourceSpan


class SymbolKind(StrEnum):
    VARIABLE = "variable"
    CONSTANT = "constant"
    POU = "pou"
    FUNCTION_BLOCK = "function_block"
    FUNCTION = "function"
    PROGRAM = "program"
    METHOD = "method"
    PROPERTY = "property"
    ACTION = "action"
    INTERFACE = "interface"
    STRUCT = "struct"
    ENUM = "enum"
    UNION = "union"
    ALIAS = "alias"
    STRUCT_FIELD = "struct_field"
    ENUM_MEMBER = "enum_member"
    GVL = "gvl"


@dataclass(slots=True)
class Symbol:
    """Represents a declared symbol (variable, function block, method, type, etc.)."""
    name: str
    kind: SymbolKind
    span: SourceSpan
    file_path: Optional[Path] = None
    type_ref: Optional[str] = None
    access: str = "PUBLIC"  # PUBLIC, PROTECTED, PRIVATE, INTERNAL
    is_constant: bool = False
    is_retain: bool = False
    is_persistent: bool = False
    is_static: bool = False
    parent_symbol: Optional[Symbol] = None
    doc_comment: Optional[str] = None
    initial_value: Optional[str] = None
    address: Optional[str] = None
    qualified_only: bool = False
    is_abstract: bool = False
    var_block_type: str = "VAR"

    @property
    def display_name(self) -> str:
        if self.type_ref:
            return f"{self.name} : {self.type_ref}"
        return self.name

    def __repr__(self) -> str:
        return f"Symbol({self.kind.value} {self.name!r} : {self.type_ref!r} at {self.span})"
