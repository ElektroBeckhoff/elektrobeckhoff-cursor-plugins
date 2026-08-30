"""On-demand Beckhoff InfoSys type provider for dynamic external library resolution."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..syntax.span import SourceSpan
from .symbols import Symbol, SymbolKind

logger = logging.getLogger("twincat-core.semantic.infosys")

DEFAULT_SPAN = SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)


class InfoSysTypeProvider:
    """Provides on-demand TypeDescriptors dynamically loaded from offline Beckhoff InfoSys (.mshc)."""

    _instance: Optional[InfoSysTypeProvider] = None

    def __init__(self) -> None:
        self._index: Optional[Any] = None
        self._cache: dict[str, Optional[Any]] = {}
        self._init_attempted: bool = False

    @classmethod
    def get_instance(cls) -> InfoSysTypeProvider:
        if cls._instance is None:
            cls._instance = InfoSysTypeProvider()
        return cls._instance

    def _ensure_index(self) -> Optional[Any]:
        if self._index is not None:
            return self._index
        if self._init_attempted:
            return None

        self._init_attempted = True
        try:
            import os
            from infosys_mshc import InfoSysMshcIndex
            from infosys_mshc.paths import resolve_mshc_path

            mshc_path = resolve_mshc_path()
            if not mshc_path or not os.path.isfile(mshc_path):
                logger.debug(f"InfoSys MSHC archive not installed or not found at: {mshc_path}")
                return None

            self._index = InfoSysMshcIndex(mshc_path=mshc_path)
            return self._index
        except Exception as e:
            logger.debug(f"InfoSys MSHC archive unavailable: {e}")
            return None

    def lookup_type(self, name: str) -> Optional[Any]:
        """Look up a Beckhoff type, function block, function, struct, or interface by name from offline InfoSys."""
        if not name:
            return None

        clean_name = name.strip()
        # Strip library prefix if provided e.g. "Tc3_IotBase.FB_IotHttpClient" -> "FB_IotHttpClient"
        if "." in clean_name:
            clean_name = clean_name.split(".")[-1].strip()

        key = clean_name.lower()
        if key in self._cache:
            return self._cache[key]

        index = self._ensure_index()
        if not index:
            self._cache[key] = None
            return None

        try:
            from .type_index import TypeDescriptor

            res = index.search(clean_name, limit=10)
            results = res.get("results", []) if isinstance(res, dict) else []
            if not results:
                self._cache[key] = None
                return None

            # Find best match: exact canonical/title match or suffix match
            matched_entry = None
            for entry in results:
                canon = entry.get("canonical_name", "").strip().lower()
                title = entry.get("title", "").strip().lower()
                if canon == key or title == key:
                    matched_entry = entry
                    break
                if title.endswith(f".{key}") or title.endswith(f" {key}") or title.endswith(f":{key}"):
                    matched_entry = entry
                    break

            if not matched_entry:
                self._cache[key] = None
                return None

            page_path = matched_entry.get("path") if matched_entry else None
            if not page_path:
                self._cache[key] = None
                return None

            page = index.read_page(page_path, max_methods=250, max_params=250)
            if not page:
                self._cache[key] = None
                return None

            title = page.get("canonical_name") or page.get("title") or clean_name
            sym_type_raw = str(page.get("sym_type") or page.get("type") or matched_entry.get("type", "")).upper()
            description = page.get("description", "")
            syntax = page.get("syntax", "")
            ret_type = page.get("return_type")

            # 1. Map entity kind (Function Block vs Function vs Struct vs Interface vs Enum)
            upper_title = title.upper()
            kind = None

            if (
                "FUNCTION_BLOCK" in sym_type_raw
                or "FUNCTION_BLOCK" in syntax.upper()
                or upper_title.startswith("FB_")
            ):
                kind = SymbolKind.FUNCTION_BLOCK
            elif (
                "INTERFACE" in sym_type_raw
                or "ITF" in sym_type_raw
                or upper_title.startswith("I_")
                or upper_title.startswith("ITC")
            ):
                kind = SymbolKind.INTERFACE
            elif (
                "STRUCT" in sym_type_raw
                or "STRUCTURE" in sym_type_raw
                or "STRUCT" in syntax.upper()
                or upper_title.startswith("ST_")
                or upper_title.endswith("STRUCT")
            ):
                kind = SymbolKind.STRUCT
            elif "ENUM" in sym_type_raw or upper_title.startswith("E_"):
                kind = SymbolKind.ENUM
            elif (
                "FUNCTION" in sym_type_raw
                or "FUNCTION " in syntax.upper()
                or upper_title.startswith("F_")
                or ret_type is not None
            ):
                kind = SymbolKind.FUNCTION

            if kind is None:
                self._cache[key] = None
                return None

            library_name = page.get("library") or matched_entry.get("library") or ""

            desc = TypeDescriptor(
                name=title,
                kind=kind,
                base_type_name=ret_type,
                namespace=library_name,
                is_external=True,
            )

            # 2. Create root symbol for the type
            root_sym = Symbol(
                name=title,
                kind=kind,
                span=DEFAULT_SPAN,
                type_ref=ret_type if kind == SymbolKind.FUNCTION else title,
                doc_comment=description or f"Beckhoff library entity {title} ({library_name})",
            )
            desc.symbol = root_sym

            # 3. Add fields (Inputs, Outputs, Parameters, Struct Fields)
            inputs = page.get("inputs", []) or []
            outputs = page.get("outputs", []) or []
            params = page.get("parameters", []) or []

            for p in inputs:
                p_name = p.get("name", "").strip() if isinstance(p, dict) else getattr(p, "name", "").strip()
                p_type = p.get("type", "BOOL").strip() if isinstance(p, dict) else getattr(p, "type", "BOOL").strip()
                p_desc = p.get("description", "") if isinstance(p, dict) else getattr(p, "description", "")
                if p_name:
                    sym = Symbol(
                        name=p_name,
                        kind=SymbolKind.VARIABLE if kind != SymbolKind.STRUCT else SymbolKind.STRUCT_FIELD,
                        span=DEFAULT_SPAN,
                        type_ref=p_type,
                        doc_comment=p_desc,
                        parent_symbol=root_sym,
                        var_block_type="VAR_INPUT" if kind != SymbolKind.STRUCT else "STRUCT_FIELD",
                    )
                    desc.add_field(sym)

            for p in outputs:
                p_name = p.get("name", "").strip() if isinstance(p, dict) else getattr(p, "name", "").strip()
                p_type = p.get("type", "BOOL").strip() if isinstance(p, dict) else getattr(p, "type", "BOOL").strip()
                p_desc = p.get("description", "") if isinstance(p, dict) else getattr(p, "description", "")
                if p_name:
                    sym = Symbol(
                        name=p_name,
                        kind=SymbolKind.VARIABLE if kind != SymbolKind.STRUCT else SymbolKind.STRUCT_FIELD,
                        span=DEFAULT_SPAN,
                        type_ref=p_type,
                        doc_comment=p_desc,
                        parent_symbol=root_sym,
                        var_block_type="VAR_OUTPUT" if kind != SymbolKind.STRUCT else "STRUCT_FIELD",
                    )
                    desc.add_field(sym)

            for p in params:
                p_name = p.get("name", "").strip() if isinstance(p, dict) else getattr(p, "name", "").strip()
                p_type = p.get("type", "BOOL").strip() if isinstance(p, dict) else getattr(p, "type", "BOOL").strip()
                p_desc = p.get("description", "") if isinstance(p, dict) else getattr(p, "description", "")
                if p_name:
                    sym = Symbol(
                        name=p_name,
                        kind=SymbolKind.VARIABLE if kind != SymbolKind.STRUCT else SymbolKind.STRUCT_FIELD,
                        span=DEFAULT_SPAN,
                        type_ref=p_type,
                        doc_comment=p_desc,
                        parent_symbol=root_sym,
                        var_block_type="VAR_INPUT" if kind != SymbolKind.STRUCT else "STRUCT_FIELD",
                    )
                    desc.add_field(sym)

            # 4. Fallback for fields from syntax block if table was empty
            if not desc.fields and syntax:
                from ..syntax.parser import parse_declaration
                try:
                    s_to_parse = syntax
                    if not s_to_parse.strip().startswith(("FUNCTION", "FUNCTION_BLOCK", "TYPE", "INTERFACE")):
                        s_to_parse = f"FUNCTION_BLOCK {title}\n" + s_to_parse
                    ast, _, _ = parse_declaration(s_to_parse)
                    if ast and getattr(ast, "var_blocks", None):
                        for vb in ast.var_blocks:
                            for v in vb.variables:
                                sym = Symbol(
                                    name=v.name,
                                    kind=SymbolKind.VARIABLE if kind != SymbolKind.STRUCT else SymbolKind.STRUCT_FIELD,
                                    span=DEFAULT_SPAN,
                                    type_ref=v.type_name,
                                    parent_symbol=root_sym,
                                    var_block_type=vb.block_type.upper() if getattr(vb, "block_type", None) else "VAR",
                                )
                                desc.add_field(sym)
                    elif ast and getattr(ast, "definition", None) and hasattr(ast.definition, "fields"):
                        for f in ast.definition.fields:
                            sym = Symbol(
                                name=f.name,
                                kind=SymbolKind.STRUCT_FIELD,
                                span=DEFAULT_SPAN,
                                type_ref=f.type_name,
                                parent_symbol=root_sym,
                                var_block_type="STRUCT_FIELD",
                            )
                            desc.add_field(sym)
                except Exception:
                    pass

            # 5. Add methods
            methods = page.get("methods", []) or []
            for m in methods:
                m_name = m.get("name", "").strip() if isinstance(m, dict) else getattr(m, "name", "").strip()
                m_desc = m.get("description", "") if isinstance(m, dict) else getattr(m, "description", "")
                m_sig = m.get("signature", "") if isinstance(m, dict) else getattr(m, "signature", "")
                if m_name:
                    m_sym = Symbol(
                        name=m_name,
                        kind=SymbolKind.METHOD,
                        span=DEFAULT_SPAN,
                        type_ref=m_sig if m_sig else None,
                        doc_comment=m_desc,
                        parent_symbol=root_sym,
                    )
                    desc.add_method(m_sym)

            # 6. Add properties
            properties = page.get("properties", []) or []
            for prop in properties:
                prop_name = prop.get("name", "").strip() if isinstance(prop, dict) else getattr(prop, "name", "").strip()
                prop_type = prop.get("type", "BOOL").strip() if isinstance(prop, dict) else getattr(prop, "type", "BOOL").strip()
                prop_desc = prop.get("description", "") if isinstance(prop, dict) else getattr(prop, "description", "")
                if prop_name:
                    p_sym = Symbol(
                        name=prop_name,
                        kind=SymbolKind.PROPERTY,
                        span=DEFAULT_SPAN,
                        type_ref=prop_type,
                        doc_comment=prop_desc,
                        parent_symbol=root_sym,
                    )
                    desc.add_property(p_sym)

            self._cache[key] = desc
            return desc

        except Exception as e:
            logger.debug(f"Error fetching InfoSys page for {clean_name}: {e}")
            self._cache[key] = None
            return None
