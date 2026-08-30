"""TwinCAT Core Semantic Analysis Layer — Symbols, Scopes, TypeIndex, and Resolver."""
from .resolver import SymbolResolver
from .scopes import Scope, ScopeKind
from .symbol_table import SymbolTable
from .symbols import Symbol, SymbolKind
from .type_index import BUILTIN_TYPES, TypeDescriptor, TypeIndex

__all__ = [
    "Symbol",
    "SymbolKind",
    "Scope",
    "ScopeKind",
    "TypeDescriptor",
    "TypeIndex",
    "BUILTIN_TYPES",
    "SymbolTable",
    "SymbolResolver",
]
