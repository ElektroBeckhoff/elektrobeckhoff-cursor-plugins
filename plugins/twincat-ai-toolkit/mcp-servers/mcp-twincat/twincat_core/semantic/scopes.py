"""Hierarchical lexical scopes for TwinCAT IEC 61131-3."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Dict, Iterator, List, Optional

from .symbols import Symbol


class ScopeKind(StrEnum):
    GLOBAL = "global"
    POU = "pou"
    METHOD = "method"
    PROPERTY = "property"
    ACTION = "action"
    BLOCK = "block"
    STRUCT = "struct"
    ENUM = "enum"
    GVL = "gvl"


class Scope:
    """A lexical or type scope containing case-insensitive symbols and parent/child links."""

    def __init__(
        self,
        kind: ScopeKind,
        name: str = "",
        parent: Optional[Scope] = None,
        owner_symbol: Optional[Symbol] = None,
    ) -> None:
        self.kind = kind
        self.name = name
        self.parent = parent
        self.owner_symbol = owner_symbol
        self.children: list[Scope] = []
        self._symbols: dict[str, Symbol] = {}
        if parent:
            parent.children.append(self)

    def define(self, symbol: Symbol) -> None:
        """Register a symbol in this scope (case-insensitive key)."""
        key = symbol.name.lower()
        self._symbols[key] = symbol

    def remove(self, name: str) -> Optional[Symbol]:
        """Remove a symbol from this scope."""
        return self._symbols.pop(name.lower(), None)

    def resolve_local(self, name: str) -> Optional[Symbol]:
        """Resolve a symbol in this immediate scope only."""
        return self._symbols.get(name.lower())

    def resolve_hierarchical(self, name: str, stop_at_kind: Optional[ScopeKind] = ScopeKind.GLOBAL) -> Optional[Symbol]:
        """Resolve a symbol by walking up the scope tree (handles shadowing, stops before global root by default)."""
        sym = self.resolve_local(name)
        if sym is not None:
            return sym
        if self.parent is not None:
            if stop_at_kind is not None and self.parent.kind == stop_at_kind:
                return None
            return self.parent.resolve_hierarchical(name, stop_at_kind=stop_at_kind)
        return None

    @property
    def symbols(self) -> dict[str, Symbol]:
        """Expose dictionary of symbols in this immediate scope."""
        return self._symbols

    def get_all_symbols(self) -> list[Symbol]:
        """Get all symbols defined in this immediate scope."""
        return list(self._symbols.values())

    def __iter__(self) -> Iterator[Symbol]:
        return iter(self._symbols.values())

    def __repr__(self) -> str:
        return f"Scope({self.kind.value} {self.name!r}, symbols={len(self._symbols)}, children={len(self.children)})"
