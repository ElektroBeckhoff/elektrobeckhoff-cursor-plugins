"""IEC 61131-3 Standard Type Conversion & Elementary Built-in Functions Catalog.

Only contains core IEC 61131-3 standard type conversions and elementary arithmetic/math operators.
All library-specific functions, Function Blocks, Structs, and Interfaces (e.g. Tc2_Standard, Tc2_System,
Tc3_Module, Tc3_JsonXml, Tc3_IotBase, Tc3_IoT_Utilities) are dynamically resolved on-demand via
the Beckhoff InfoSys Provider (twincat_core.semantic.infosys_provider).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..syntax.span import SourceSpan
from .symbols import Symbol, SymbolKind

DEFAULT_SPAN = SourceSpan.from_bounds(0, 0, 0, 0, 0, 0)


def build_standard_type_descriptors() -> dict[str, Any]:
    """Empty - all library types, structs, and function blocks are resolved dynamically via InfoSys."""
    return {}


def build_standard_global_functions() -> list[Symbol]:
    """Create Symbol list for standard IEC 61131-3 conversion and elementary math functions."""
    funcs: list[Symbol] = []

    def add_fn(name: str, ret_type: str, doc: str = "") -> None:
        funcs.append(
            Symbol(
                name=name,
                kind=SymbolKind.FUNCTION,
                span=DEFAULT_SPAN,
                type_ref=ret_type,
                doc_comment=doc or f"Standard IEC 61131-3 function {name}",
            )
        )

    # Standard IEC Type Conversions (TO_*, *_TO_*)
    types_list = [
        "BOOL", "BYTE", "WORD", "DWORD", "LWORD",
        "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
        "REAL", "LREAL", "TIME", "LTIME", "DATE", "DT", "TOD", "STRING", "WSTRING",
    ]
    for target in types_list:
        add_fn(f"TO_{target}", target, f"Converts value to {target}.")
        for src in types_list:
            if src != target:
                add_fn(f"{src}_TO_{target}", target, f"Converts {src} to {target}.")

    # Elementary Math / Arithmetic functions defined by IEC 61131-3 standard
    add_fn("TRUNC", "DINT", "Truncates REAL/LREAL to integer (towards zero).")
    add_fn("ROUND", "DINT", "Rounds REAL/LREAL to nearest integer.")
    add_fn("ABS", "LREAL", "Returns absolute value of number.")
    add_fn("SQRT", "LREAL", "Returns square root.")
    add_fn("LN", "LREAL", "Returns natural logarithm.")
    add_fn("LOG", "LREAL", "Returns base-10 logarithm.")
    add_fn("EXP", "LREAL", "Returns exponential function e^x.")
    add_fn("SIN", "LREAL", "Returns sine.")
    add_fn("COS", "LREAL", "Returns cosine.")
    add_fn("TAN", "LREAL", "Returns tangent.")
    add_fn("ASIN", "LREAL", "Returns arc sine.")
    add_fn("ACOS", "LREAL", "Returns arc cosine.")
    add_fn("ATAN", "LREAL", "Returns arc tangent.")

    return funcs
