"""Type index and type descriptors for TwinCAT IEC 61131-3 types with dynamic InfoSys provider."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .builtin_catalog import (
    build_standard_global_functions,
    build_standard_type_descriptors,
)
from .infosys_provider import InfoSysTypeProvider
from .symbol_table import compute_proximity
from .symbols import Symbol, SymbolKind

BUILTIN_TYPES: Set[str] = {
    # Booleans & Bits
    "bool", "bit",
    # Bit strings & Integers
    "byte", "word", "dword", "lword",
    "sint", "int", "dint", "lint",
    "usint", "uint", "udint", "ulint",
    # Reals
    "real", "lreal",
    # Strings
    "string", "wstring",
    # Time & Date
    "time", "ltime", "date", "ldate", "tod", "time_of_day",
    "ltod", "ltime_of_day", "dt", "date_and_time", "ldt",
    # Special & System
    "pointer", "reference", "array", "any", "any_type",
    "pvoid", "hresult", "guid", "interface", "timestruct", "st_libversion",
    "t_maxstring", "t_amsnetid", "t_amsport",
}


@dataclass(slots=True)
class TypeDescriptor:
    """Detailed structural information about a declared type (FB, STRUCT, ENUM, etc.)."""
    name: str
    kind: SymbolKind
    extends_name: Optional[str] = None
    implements_names: list[str] = field(default_factory=list)
    fields: dict[str, Symbol] = field(default_factory=dict)         # lowercase_name -> field Symbol
    methods: dict[str, Symbol] = field(default_factory=dict)       # lowercase_name -> method Symbol
    properties: dict[str, Symbol] = field(default_factory=dict)   # lowercase_name -> property Symbol
    enum_members: dict[str, Symbol] = field(default_factory=dict) # lowercase_name -> member Symbol
    file_path: Optional[Path] = None
    symbol: Optional[Symbol] = None
    base_type_name: Optional[str] = None  # e.g. for ALIAS or ENUM base type
    namespace: Optional[str] = None       # e.g. "Tc2_Standard", "Tc3_Module"
    is_external: bool = False
    is_abstract: bool = False

    def add_field(self, sym: Symbol) -> None:
        self.fields[sym.name.lower()] = sym

    def add_method(self, sym: Symbol) -> None:
        self.methods[sym.name.lower()] = sym

    def add_property(self, sym: Symbol) -> None:
        self.properties[sym.name.lower()] = sym

    def add_enum_member(self, sym: Symbol) -> None:
        self.enum_members[sym.name.lower()] = sym


class TypeIndex:
    """Project-wide index of all types (built-in, library, InfoSys on-demand, and user-defined)."""

    def __init__(self) -> None:
        self._types: dict[str, list[TypeDescriptor]] = {}  # lowercase_name -> list of TypeDescriptor
        self._libraries: dict[str, set[str]] = {}          # lowercase_library_name -> set of lowercase type names
        self._init_builtins()

    def _init_builtins(self) -> None:
        for t_name in BUILTIN_TYPES:
            upper_name = t_name.upper()
            self.register_type(TypeDescriptor(
                name=upper_name,
                kind=SymbolKind.ALIAS,
            ))

    def register_type(self, descriptor: TypeDescriptor) -> None:
        """Register or update a type descriptor with multi-file support."""
        key = descriptor.name.lower()
        if key not in self._types:
            self._types[key] = []

        if descriptor.file_path:
            res_path = descriptor.file_path.resolve()
            descriptor.file_path = res_path
            self._types[key] = [
                d for d in self._types[key]
                if not (d.file_path and d.file_path == res_path)
            ]

        self._types[key].append(descriptor)

    def remove_types_by_file(self, file_path: Path) -> None:
        """Remove all types defined in the given file (used for incremental re-indexing)."""
        res_path = file_path.resolve()
        for k in list(self._types.keys()):
            self._types[k] = [
                d for d in self._types[k]
                if not (d.file_path is not None and d.file_path == res_path)
            ]
            if not self._types[k]:
                del self._types[k]

    def register_library_type(self, library_name: str, type_name: str) -> None:
        """Associate a type with a specific library namespace (e.g. 'Tc2_Standard')."""
        lib_key = library_name.lower()
        if lib_key not in self._libraries:
            self._libraries[lib_key] = set()
        self._libraries[lib_key].add(type_name.lower())

    def get_library_types(self, library_name: str) -> set[str]:
        """Get all type names registered under a library namespace."""
        return self._libraries.get(library_name.lower(), set())

    def get_type(self, name: str, context_path: Optional[Path] = None) -> Optional[TypeDescriptor]:
        """Look up type descriptor with proximity matching and on-demand InfoSys fallback."""
        if not name:
            return None

        cleaned = self.clean_type_name(name)
        key = cleaned.lower()

        # 1. Direct or library-qualified lookup in registered types
        candidates = self._types.get(key)
        if not candidates and "." in key:
            lib_prefix, type_suffix = key.split(".", 1)
            candidates = self._types.get(type_suffix)

        if candidates:
            if len(candidates) == 1 or not context_path:
                return candidates[0]
            return max(candidates, key=lambda d: compute_proximity(context_path, d.file_path))

        # 2. On-demand dynamic lookup from Beckhoff InfoSys (.mshc)
        infosys_desc = InfoSysTypeProvider.get_instance().lookup_type(cleaned)
        if infosys_desc is not None:
            self.register_type(infosys_desc)
            if infosys_desc.namespace:
                self.register_library_type(infosys_desc.namespace, infosys_desc.name)
            return infosys_desc

        return None

    @staticmethod
    def clean_type_name(raw: str) -> str:
        """Extract the core identifier from a complex type signature."""
        s = raw.strip()
        if not s:
            return ""
        if re.match(r"^REFERENCE\s+TO\s+", s, re.IGNORECASE):
            s = re.sub(r"^REFERENCE\s+TO\s+", "", s, flags=re.IGNORECASE).strip()
        if re.match(r"^POINTER\s+TO\s+", s, re.IGNORECASE):
            s = re.sub(r"^POINTER\s+TO\s+", "", s, flags=re.IGNORECASE).strip()
        m_arr = re.search(r"\bOF\s+(.+)$", s, re.IGNORECASE)
        if m_arr:
            s = m_arr.group(1).strip()
        if "(" in s:
            s = s.split("(")[0].strip()
        if "[" in s:
            s = s.split("[")[0].strip()
        return s.strip()

    def is_builtin(self, name: str) -> bool:
        cleaned = self.clean_type_name(name).lower()
        return cleaned in BUILTIN_TYPES

    def get_inheritance_chain(self, type_name: str, context_path: Optional[Path] = None) -> list[str]:
        """Get ordered list of base type names (starting from immediate parent)."""
        chain: list[str] = []
        visited: set[str] = set()
        curr = self.get_type(type_name, context_path=context_path)
        while curr and curr.extends_name:
            ext = curr.extends_name
            ext_key = ext.lower()
            if ext_key in visited:
                break  # avoid cyclic inheritance loop
            visited.add(ext_key)
            chain.append(ext)
            curr = self.get_type(ext, context_path=context_path)
        return chain

    def find_field(
        self,
        type_name: str,
        field_name: str,
        inherit: bool = True,
        context_path: Optional[Path] = None,
        visited: Optional[set[str]] = None,
    ) -> Optional[Symbol]:
        """Look up a member/field in a struct or FB, optionally checking base classes."""
        if visited is None:
            visited = set()
        clean = self.clean_type_name(type_name)
        key = clean.lower()
        if not key or key in visited:
            return None
        visited.add(key)

        t_desc = self.get_type(clean, context_path=context_path)
        if not t_desc:
            return None
        f_key = field_name.lower()
        if f_key in t_desc.fields:
            return t_desc.fields[f_key]
        if inherit and t_desc.extends_name:
            return self.find_field(t_desc.extends_name, field_name, inherit=True, context_path=context_path, visited=visited)
        return None

    def find_method(
        self,
        type_name: str,
        method_name: str,
        inherit: bool = True,
        context_path: Optional[Path] = None,
        visited: Optional[set[str]] = None,
    ) -> Optional[Symbol]:
        """Look up a method in a FB or Interface, optionally checking base classes/interfaces."""
        if visited is None:
            visited = set()
        clean = self.clean_type_name(type_name)
        key = clean.lower()
        if not key or key in visited:
            return None
        visited.add(key)

        t_desc = self.get_type(clean, context_path=context_path)
        if not t_desc:
            return None
        m_key = method_name.lower()
        if m_key in t_desc.methods:
            return t_desc.methods[m_key]
        if inherit:
            if t_desc.extends_name:
                res = self.find_method(t_desc.extends_name, method_name, inherit=True, context_path=context_path, visited=visited)
                if res:
                    return res
            if t_desc.kind == SymbolKind.INTERFACE:
                for itf in t_desc.implements_names:
                    res = self.find_method(itf, method_name, inherit=True, context_path=context_path, visited=visited)
                    if res:
                        return res
        return None

    def find_property(
        self,
        type_name: str,
        prop_name: str,
        inherit: bool = True,
        context_path: Optional[Path] = None,
        visited: Optional[set[str]] = None,
    ) -> Optional[Symbol]:
        """Look up a property in a FB or Interface, optionally checking base classes/interfaces."""
        if visited is None:
            visited = set()
        clean = self.clean_type_name(type_name)
        key = clean.lower()
        if not key or key in visited:
            return None
        visited.add(key)

        t_desc = self.get_type(clean, context_path=context_path)
        if not t_desc:
            return None
        p_key = prop_name.lower()
        if p_key in t_desc.properties:
            return t_desc.properties[p_key]
        if inherit:
            if t_desc.extends_name:
                res = self.find_property(t_desc.extends_name, prop_name, inherit=True, context_path=context_path, visited=visited)
                if res:
                    return res
            if t_desc.kind == SymbolKind.INTERFACE:
                for itf in t_desc.implements_names:
                    res = self.find_property(itf, prop_name, inherit=True, context_path=context_path, visited=visited)
                    if res:
                        return res
        return None

    def get_all_fields(
        self,
        type_name: str,
        context_path: Optional[Path] = None,
        visited: Optional[set[str]] = None,
    ) -> dict[str, Symbol]:
        """Get all fields including inherited fields from base classes/structs."""
        if visited is None:
            visited = set()
        clean = self.clean_type_name(type_name)
        key = clean.lower()
        if not key or key in visited:
            return {}
        visited.add(key)

        t_desc = self.get_type(clean, context_path=context_path)
        if not t_desc:
            return {}

        fields: dict[str, Symbol] = {}
        if t_desc.extends_name:
            base_fields = self.get_all_fields(t_desc.extends_name, context_path=context_path, visited=visited)
            fields.update(base_fields)

        fields.update(t_desc.fields)
        return fields

    def get_all_methods(
        self,
        type_name: str,
        context_path: Optional[Path] = None,
        visited: Optional[set[str]] = None,
    ) -> dict[str, Symbol]:
        """Get all methods including inherited methods from base classes or extended interfaces."""
        if visited is None:
            visited = set()
        clean = self.clean_type_name(type_name)
        key = clean.lower()
        if not key or key in visited:
            return {}
        visited.add(key)

        t_desc = self.get_type(clean, context_path=context_path)
        if not t_desc:
            return {}

        methods: dict[str, Symbol] = {}
        if t_desc.extends_name:
            base_methods = self.get_all_methods(t_desc.extends_name, context_path=context_path, visited=visited)
            methods.update(base_methods)

        if t_desc.kind == SymbolKind.INTERFACE:
            for itf in t_desc.implements_names:
                itf_methods = self.get_all_methods(itf, context_path=context_path, visited=visited)
                methods.update(itf_methods)

        methods.update(t_desc.methods)
        return methods

    def get_all_properties(
        self,
        type_name: str,
        context_path: Optional[Path] = None,
        visited: Optional[set[str]] = None,
    ) -> dict[str, Symbol]:
        """Get all properties including inherited properties from base classes or extended interfaces."""
        if visited is None:
            visited = set()
        clean = self.clean_type_name(type_name)
        key = clean.lower()
        if not key or key in visited:
            return {}
        visited.add(key)

        t_desc = self.get_type(clean, context_path=context_path)
        if not t_desc:
            return {}

        properties: dict[str, Symbol] = {}
        if t_desc.extends_name:
            base_props = self.get_all_properties(t_desc.extends_name, context_path=context_path, visited=visited)
            properties.update(base_props)

        if t_desc.kind == SymbolKind.INTERFACE:
            for itf in t_desc.implements_names:
                itf_props = self.get_all_properties(itf, context_path=context_path, visited=visited)
                properties.update(itf_props)

        properties.update(t_desc.properties)
        return properties

    def find_enum_member(self, type_name: str, member_name: str, context_path: Optional[Path] = None) -> Optional[Symbol]:
        """Look up an enum member inside an Enum type."""
        t_desc = self.get_type(type_name, context_path=context_path)
        if not t_desc:
            return None
        return t_desc.enum_members.get(member_name.lower())

    def get_all_user_types(self) -> list[TypeDescriptor]:
        res: list[TypeDescriptor] = []
        for descs in self._types.values():
            for d in descs:
                if d.file_path is not None:
                    res.append(d)
        return res
