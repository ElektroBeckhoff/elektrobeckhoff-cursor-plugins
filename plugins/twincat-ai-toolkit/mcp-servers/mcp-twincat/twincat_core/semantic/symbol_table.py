"""Symbol table for project-wide and file-level scopes."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .builtin_catalog import build_standard_global_functions
from .scopes import Scope, ScopeKind
from .symbols import Symbol, SymbolKind


def compute_proximity(context_path: Optional[Path], candidate_path: Optional[Path]) -> int:
    """Compute hierarchical path proximity (number of shared ancestor folder components)."""
    if not context_path or not candidate_path:
        return 0
    try:
        c_parts = context_path.resolve().parts
        cand_parts = candidate_path.resolve().parts
        common_len = 0
        for p1, p2 in zip(c_parts, cand_parts):
            if p1.lower() == p2.lower():
                common_len += 1
            else:
                break
        # Exact same file gets highest score
        if context_path.resolve() == candidate_path.resolve():
            common_len += 100
        return common_len
    except Exception:
        return 0


class SymbolTable:
    """Manages the global root scope, POU/Method sub-scopes, and file-associated symbols."""

    def __init__(self) -> None:
        self.global_scope = Scope(kind=ScopeKind.GLOBAL, name="<Global>")
        self.file_scopes: dict[Path, list[Scope]] = {}  # file_path -> list of scopes defined in it
        self.pou_scopes: dict[str, list[Tuple[Optional[Path], Scope]]] = {}  # lowercase POU name -> list of (path, scope)
        self.gvl_scopes: dict[str, list[Tuple[Optional[Path], Scope]]] = {}  # lowercase GVL name -> list of (path, scope)
        self.global_symbols: dict[str, list[Symbol]] = {}  # lowercase name -> list of Symbol
        self.library_scopes: dict[str, Scope] = {}      # lowercase library name -> library scope
        self._init_builtins()

    def _init_builtins(self) -> None:
        """Register standard IEC / TwinCAT built-in functions in global scope."""
        funcs = build_standard_global_functions()
        for fn in funcs:
            self.define_global(fn)

    def define_global(self, symbol: Symbol) -> None:
        """Register a top-level symbol (POU, DUT, GVL, ITF, or Global Variable) in global scope."""
        self.global_scope.define(symbol)
        key = symbol.name.lower()
        if key not in self.global_symbols:
            self.global_symbols[key] = []

        if symbol.file_path:
            res_path = symbol.file_path.resolve()
            symbol.file_path = res_path
            self.global_symbols[key] = [
                s for s in self.global_symbols[key]
                if not (s.file_path and s.file_path == res_path)
            ]
            self._track_file_scope(res_path, self.global_scope)

        self.global_symbols[key].append(symbol)

    def create_pou_scope(self, pou_symbol: Symbol, file_path: Optional[Path] = None) -> Scope:
        """Create and register a POU scope under global scope."""
        scope = Scope(
            kind=ScopeKind.POU,
            name=pou_symbol.name,
            parent=self.global_scope,
            owner_symbol=pou_symbol,
        )
        key = pou_symbol.name.lower()
        if key not in self.pou_scopes:
            self.pou_scopes[key] = []

        res_path = file_path.resolve() if file_path else None
        if res_path:
            self.pou_scopes[key] = [
                item for item in self.pou_scopes[key]
                if not (item[0] and item[0] == res_path)
            ]
            self._track_file_scope(res_path, scope)

        self.pou_scopes[key].append((res_path, scope))
        return scope

    def create_gvl_scope(self, gvl_symbol: Symbol, file_path: Optional[Path] = None) -> Scope:
        """Create and register a GVL scope under global scope."""
        scope = Scope(
            kind=ScopeKind.GVL,
            name=gvl_symbol.name,
            parent=self.global_scope,
            owner_symbol=gvl_symbol,
        )
        key = gvl_symbol.name.lower()
        if key not in self.gvl_scopes:
            self.gvl_scopes[key] = []

        res_path = file_path.resolve() if file_path else None
        if res_path:
            self.gvl_scopes[key] = [
                item for item in self.gvl_scopes[key]
                if not (item[0] and item[0] == res_path)
            ]
            self._track_file_scope(res_path, scope)

        self.gvl_scopes[key].append((res_path, scope))
        return scope

    def create_method_scope(self, method_symbol: Symbol, parent_scope: Scope, file_path: Optional[Path] = None) -> Scope:
        """Create and register a method or action scope under a POU scope."""
        scope = Scope(
            kind=ScopeKind.METHOD,
            name=method_symbol.name,
            parent=parent_scope,
            owner_symbol=method_symbol,
        )
        if file_path:
            self._track_file_scope(file_path.resolve(), scope)
        return scope

    def remove_file(self, file_path: Path) -> None:
        """Remove all symbols, POU scopes, and GVL scopes originating from the specified file."""
        res_path = file_path.resolve()

        scopes = self.file_scopes.pop(res_path, [])
        for sc in scopes:
            if sc.owner_symbol:
                self.global_scope.remove(sc.owner_symbol.name)
            for sym in list(sc.symbols.values()):
                if sym.file_path and sym.file_path == res_path:
                    sc.remove(sym.name)
                    self.global_scope.remove(sym.name)

        # Remove from pou_scopes
        for k in list(self.pou_scopes.keys()):
            self.pou_scopes[k] = [
                item for item in self.pou_scopes[k]
                if not (item[0] and item[0] == res_path)
            ]
            if not self.pou_scopes[k]:
                del self.pou_scopes[k]

        # Remove from gvl_scopes
        for k in list(self.gvl_scopes.keys()):
            self.gvl_scopes[k] = [
                item for item in self.gvl_scopes[k]
                if not (item[0] and item[0] == res_path)
            ]
            if not self.gvl_scopes[k]:
                del self.gvl_scopes[k]

        # Remove from global_symbols
        for k in list(self.global_symbols.keys()):
            self.global_symbols[k] = [
                s for s in self.global_symbols[k]
                if not (s.file_path and s.file_path == res_path)
            ]
            if not self.global_symbols[k]:
                del self.global_symbols[k]

    def _track_file_scope(self, file_path: Path, scope: Scope) -> None:
        res = file_path.resolve()
        if res not in self.file_scopes:
            self.file_scopes[res] = []
        if scope not in self.file_scopes[res]:
            self.file_scopes[res].append(scope)

    def get_file_scopes(self, file_path: Path) -> list[Scope]:
        """Retrieve all scopes registered specifically for a given file."""
        res = file_path.resolve()
        return self.file_scopes.get(res, [])

    def get_file_pou_scope(self, file_path: Path) -> Optional[Scope]:
        """Retrieve top-level POU or GVL scope declared in the given file."""
        for sc in self.get_file_scopes(file_path):
            if sc.kind in (ScopeKind.POU, ScopeKind.GVL):
                return sc
        return None

    def find_pou_scope(self, name: str, context_path: Optional[Path] = None) -> Optional[Scope]:
        """Look up POU scope with optional proximity matching for context file."""
        candidates = self.pou_scopes.get(name.lower(), [])
        if not candidates:
            return None
        if len(candidates) == 1 or not context_path:
            return candidates[0][1]
        return max(candidates, key=lambda item: compute_proximity(context_path, item[0]))[1]

    def find_gvl_scope(self, name: str, context_path: Optional[Path] = None) -> Optional[Scope]:
        """Look up GVL scope with optional proximity matching for context file."""
        candidates = self.gvl_scopes.get(name.lower(), [])
        if not candidates:
            return None
        if len(candidates) == 1 or not context_path:
            return candidates[0][1]
        return max(candidates, key=lambda item: compute_proximity(context_path, item[0]))[1]

    def find_global_symbol(self, name: str, context_path: Optional[Path] = None) -> Optional[Symbol]:
        """Look up global symbol with proximity matching for context file."""
        candidates = self.global_symbols.get(name.lower(), [])
        if not candidates:
            return self.global_scope.resolve_local(name)
        if len(candidates) == 1 or not context_path:
            return candidates[0]
        return max(candidates, key=lambda s: compute_proximity(context_path, s.file_path))
