"""Type compatibility, conversion validation, and narrowing diagnostics for IEC 61131-3 and TwinCAT 3."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

from .symbols import SymbolKind

if TYPE_CHECKING:
    from .type_index import TypeDescriptor, TypeIndex

_RE_PREFIX = re.compile(r"^(?:VAR_INST|VAR_STAT|VAR_TEMP|VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR)\s+", re.IGNORECASE)


class TypeCheckResultKind(StrEnum):
    COMPATIBLE = "compatible"               # No diagnostic
    NARROWING_WARNING = "narrowing_warning" # TC-SEM-007 (Warning: implicit narrowing, sign change, precision loss)
    TYPE_MISMATCH_ERROR = "type_mismatch"  # TC-SEM-006 (Error: incompatible types)


@dataclass(frozen=True, slots=True)
class TypeCheckResult:
    kind: TypeCheckResultKind
    message: Optional[str] = None
    code: Optional[str] = None


# Elementary Type Bit Sizes and Ranks
SIGNED_INTS: dict[str, tuple[int, int]] = {  # type -> (bit_size, rank)
    "SINT": (8, 1),
    "INT": (16, 2),
    "DINT": (32, 3),
    "LINT": (64, 4),
}

UNSIGNED_INTS: dict[str, tuple[int, int]] = {
    "USINT": (8, 1),
    "UINT": (16, 2),
    "UDINT": (32, 3),
    "ULINT": (64, 4),
}

BIT_STRINGS: dict[str, tuple[int, int]] = {
    "BYTE": (8, 1),
    "WORD": (16, 2),
    "DWORD": (32, 3),
    "LWORD": (64, 4),
    "HRESULT": (32, 3),
}

FLOATS: dict[str, tuple[int, int]] = {
    "REAL": (32, 1),
    "LREAL": (64, 2),
}

TIME_TYPES: dict[str, tuple[int, int]] = {
    "TIME": (32, 1),
    "LTIME": (64, 2),
}

DATE_TYPES: dict[str, tuple[int, int]] = {
    "DATE": (32, 1),
    "LDATE": (64, 2),
}

TOD_TYPES: dict[str, tuple[int, int]] = {
    "TOD": (32, 1),
    "TIME_OF_DAY": (32, 1),
    "LTOD": (64, 2),
    "LTIME_OF_DAY": (64, 2),
}

DT_TYPES: dict[str, tuple[int, int]] = {
    "DT": (32, 1),
    "DATE_AND_TIME": (32, 1),
    "LDT": (64, 2),
}

STRING_TYPES: Set[str] = {"STRING", "WSTRING"}
BOOLEAN_TYPES: Set[str] = {"BOOL", "BIT", "TRUE", "FALSE"}

GENERIC_TYPES: Set[str] = {
    "ANY",
    "ANY_TYPE",
    "ANY_BIT",
    "ANY_INT",
    "ANY_REAL",
    "ANY_NUM",
    "ANY_STRING",
    "ANY_DATE",
    "PVOID",
    "__SYSTEM",
    "__SYSTEM.VAR_INFO",
}


def _clean_type_str(type_str: str) -> str:
    """Extract clean base type string in uppercase."""
    t = type_str.strip()
    if not t:
        return ""
    t = _RE_PREFIX.sub("", t).strip()
    if ":" in t:
        # e.g. "BOOL VAR_INST _nState : INT" -> take the last part after the colon
        t = t.rsplit(":", 1)[-1].strip()
    u = t.upper()
    if u in ("TRUE", "FALSE"):
        return "BOOL"
    if u.startswith("POINTER TO"):
        inner = t[10:].strip()
        return f"POINTER TO {_clean_type_str(inner)}"
    if u.startswith("REFERENCE TO"):
        inner = t[12:].strip()
        return f"REFERENCE TO {_clean_type_str(inner)}"
    if "[" in t:
        t = t.split("[")[0].strip()
    if "(" in t:
        t = t.split("(")[0].strip()
    u2 = t.upper()
    if u2 in ("TRUE", "FALSE"):
        return "BOOL"
    return u2


def _is_8bit_string(t: str, type_index: Optional[TypeIndex] = None, context_path: Optional[Path] = None) -> bool:
    """Check if type represents an 8-bit ASCII string (STRING, STRING(n), T_MaxString, alias)."""
    if not t:
        return False
    u = t.upper().strip()
    if u.startswith("WSTRING"):
        return False
    if u in ("STRING", "STRING_LITERAL", "T_MAXSTRING", "T_AMSNETID", "ANY_STRING"):
        return True
    if u.startswith("STRING(") or u.startswith("STRING [") or u.startswith("STRING "):
        return True
    if (u.startswith("T_") or u.startswith("TYPE_") or u.startswith("ST_")) and u.endswith("STRING") and not u.endswith("WSTRING"):
        return True
    if u.endswith("STRING") and not u.endswith("WSTRING") and not (u.startswith("FB_") or u.startswith("I_") or u.startswith("E_") or u.startswith("F_")):
        return True
    if type_index:
        desc = type_index.get_type(u, context_path=context_path)
        if desc and desc.kind == SymbolKind.ALIAS and desc.base_type_name:
            return _is_8bit_string(desc.base_type_name, type_index, context_path)
    return False


def _is_16bit_string(t: str, type_index: Optional[TypeIndex] = None, context_path: Optional[Path] = None) -> bool:
    """Check if type represents a 16-bit Unicode string (WSTRING, WSTRING(n), alias)."""
    if not t:
        return False
    u = t.upper().strip()
    if u in ("WSTRING", "WSTRING_LITERAL", "ANY_WSTRING"):
        return True
    if u.startswith("WSTRING(") or u.startswith("WSTRING [") or u.startswith("WSTRING "):
        return True
    if (u.startswith("T_") or u.startswith("TYPE_") or u.startswith("ST_")) and u.endswith("WSTRING"):
        return True
    if u.endswith("WSTRING") and not (u.startswith("FB_") or u.startswith("I_") or u.startswith("E_") or u.startswith("F_")):
        return True
    if type_index:
        desc = type_index.get_type(u, context_path=context_path)
        if desc and desc.kind == SymbolKind.ALIAS and desc.base_type_name:
            return _is_16bit_string(desc.base_type_name, type_index, context_path)
    return False


def _is_any_string_type(t: str, type_index: Optional[TypeIndex] = None, context_path: Optional[Path] = None) -> bool:
    return _is_8bit_string(t, type_index, context_path) or _is_16bit_string(t, type_index, context_path)


def _is_interface_type(t: str, type_index: Optional[TypeIndex] = None, context_path: Optional[Path] = None) -> bool:
    """Check if type name represents an Interface in IEC 61131-3 / TwinCAT 3."""
    if not t:
        return False
    u = t.upper().strip()
    if u in ("INT", "INT_LITERAL", "INT64", "INT32", "INT16", "INT8", "INDEX", "INIT"):
        return False
    if u in ("INTERFACE", "__INTERFACE", "I_UNKNOWN", "ITFID"):
        return True
    if "." in u:
        u = u.split(".")[-1].strip()
    if u.startswith("I_") or u.startswith("ITF_"):
        return True
    if type_index:
        desc = type_index.get_type(t, context_path=context_path)
        if desc and desc.kind == SymbolKind.INTERFACE:
            return True
    return False


def _is_fb_type(t: str, type_index: Optional[TypeIndex] = None, context_path: Optional[Path] = None) -> bool:
    """Check if type name represents a Function Block in IEC 61131-3 / TwinCAT 3."""
    if not t:
        return False
    u = t.upper().strip()
    if u in ("POU", "FUNCTION_BLOCK", "FB"):
        return True
    if "." in u:
        u = u.split(".")[-1].strip()
    if u.startswith("FB_"):
        return True
    if type_index:
        desc = type_index.get_type(t, context_path=context_path)
        if desc and desc.kind in (SymbolKind.FUNCTION_BLOCK, SymbolKind.POU):
            return True
    return False


def _is_null_or_zero(s: str) -> bool:
    if not s:
        return False
    u = s.upper().strip()
    return u in ("0", "16#0", "0#0", "NULL", "NULL_PTR", "PVOID", "INT_LITERAL", "ANY_INT")


def _implements_interface(
    s_desc: Any,
    target_itf_name: str,
    type_index: Any,
    context_path: Optional[Path] = None,
    visited: Optional[set[str]] = None,
) -> bool:
    """Check if a symbol/type implements or extends target interface directly or transitively."""
    if visited is None:
        visited = set()
    s_name_lower = s_desc.name.lower()
    if s_name_lower in visited:
        return False
    visited.add(s_name_lower)

    target_lower = target_itf_name.lower()

    # 1. Direct implements / extends interface list
    for itf in s_desc.implements_names:
        if itf.lower() == target_lower:
            return True
        itf_desc = type_index.get_type(itf, context_path=context_path)
        if itf_desc and _implements_interface(itf_desc, target_itf_name, type_index, context_path, visited):
            return True

    # 2. Check base class (extends_name)
    if s_desc.extends_name:
        base_desc = type_index.get_type(s_desc.extends_name, context_path=context_path)
        if base_desc and _implements_interface(base_desc, target_itf_name, type_index, context_path, visited):
            return True

    return False


def _inherits_from_class(
    s_desc: Any,
    target_class_name: str,
    type_index: Any,
    context_path: Optional[Path] = None,
    visited: Optional[set[str]] = None,
) -> bool:
    """Check if a POU inherits from a target class directly or transitively (multi-level EXTENDS)."""
    if visited is None:
        visited = set()
    s_name_lower = s_desc.name.lower()
    if s_name_lower in visited:
        return False
    visited.add(s_name_lower)

    target_lower = target_class_name.lower()
    curr = s_desc.extends_name
    while curr:
        if curr.lower() == target_lower:
            return True
        curr_desc = type_index.get_type(curr, context_path=context_path)
        if not curr_desc or curr_desc.name.lower() in visited:
            break
        visited.add(curr_desc.name.lower())
        curr = curr_desc.extends_name

    return False


def check_type_assignment(
    target_type: Optional[str],
    source_type: Optional[str],
    type_index: Optional[TypeIndex] = None,
    context_path: Optional[Path] = None,
) -> TypeCheckResult:
    """Check assignment compatibility from source_type to target_type (target := source)."""
    if not target_type or not source_type:
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    t_clean = _clean_type_str(target_type)
    s_clean = _clean_type_str(source_type)

    if not t_clean or not s_clean:
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # 1. Generic & Wildcard types (ANY, ANY_TYPE, PVOID, __SYSTEM.*)
    if (
        t_clean in ("ANY", "ANY_TYPE", "PVOID")
        or s_clean in ("ANY", "ANY_TYPE", "PVOID")
        or t_clean.startswith("__SYSTEM.")
        or s_clean.startswith("__SYSTEM.")
    ):
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # Unwrap ALIAS / Subrange types if needed
    if type_index:
        t_desc = type_index.get_type(t_clean, context_path=context_path)
        if t_desc and t_desc.kind == SymbolKind.ALIAS and t_desc.base_type_name:
            unwrapped_t = _clean_type_str(t_desc.base_type_name)
            if unwrapped_t and unwrapped_t != t_clean:
                t_clean = unwrapped_t

        s_desc = type_index.get_type(s_clean, context_path=context_path)
        if s_desc and s_desc.kind == SymbolKind.ALIAS and s_desc.base_type_name:
            unwrapped_s = _clean_type_str(s_desc.base_type_name)
            if unwrapped_s and unwrapped_s != s_clean:
                s_clean = unwrapped_s

    # 2. Identical types
    if t_clean == s_clean:
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    all_ints = {**SIGNED_INTS, **UNSIGNED_INTS, **BIT_STRINGS}
    is_t_8str = _is_8bit_string(t_clean, type_index, context_path)
    is_s_8str = _is_8bit_string(s_clean, type_index, context_path)
    is_t_16str = _is_16bit_string(t_clean, type_index, context_path)
    is_s_16str = _is_16bit_string(s_clean, type_index, context_path)

    # 2b. Literal & Polymorphic Integer Types (ANY_INT, INT_LITERAL, ANY_NUM, ANY_BIT)
    if s_clean in ("ANY_INT", "INT_LITERAL", "ANY_NUM", "ANY_BIT"):
        if t_clean in all_ints or t_clean in FLOATS or t_clean in ("ANY_INT", "ANY_NUM", "ANY_BIT", "ANY_REAL"):
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if (
            t_clean.startswith("POINTER TO")
            or t_clean == "POINTER"
            or t_clean.startswith("REFERENCE TO")
            or t_clean == "REFERENCE"
            or _is_interface_type(t_clean, type_index, context_path)
        ):
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        # TIME / LTIME accept integer-tick literals in TwinCAT
        if t_clean in TIME_TYPES or t_clean in DATE_TYPES or t_clean in TOD_TYPES or t_clean in DT_TYPES:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if t_clean in BOOLEAN_TYPES:
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot convert integer literal to '{target_type}'",
                code="TC-SEM-006",
            )
        if is_t_8str or is_t_16str:
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot convert integer literal to '{target_type}' without TO_STRING()",
                code="TC-SEM-006",
            )
        # Unknown / external-library aliases (e.g. Tc2_Utilities T_FILETIME64 : ULINT)
        # are not in the local type index — TwinCAT accepts integer literals for them.
        t_desc_lit = type_index.get_type(t_clean, context_path=context_path) if type_index else None
        if t_desc_lit is None:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        # Known STRUCT / ENUM / FB / INTERFACE targets reject bare integer literals
        if t_desc_lit.kind in (
            SymbolKind.STRUCT,
            SymbolKind.ENUM,
            SymbolKind.FUNCTION_BLOCK,
            SymbolKind.POU,
            SymbolKind.INTERFACE,
            SymbolKind.UNION,
        ):
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot convert integer literal to '{target_type}'",
                code="TC-SEM-006",
            )
        # Known ALIAS / other typed aliases already unwrapped above; residual → compatible
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    if s_clean in ("ANY_REAL", "REAL_LITERAL"):
        if t_clean in FLOATS or t_clean in ("ANY_REAL", "ANY_NUM"):
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if t_clean in all_ints:
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message=f"Implicit conversion from floating point literal to integer '{target_type}': fractional part will be truncated",
                code="TC-SEM-007",
            )
        if t_clean in BOOLEAN_TYPES:
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot convert floating point literal to '{target_type}'",
                code="TC-SEM-006",
            )
        if is_t_8str or is_t_16str:
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot convert floating point literal to '{target_type}' without TO_STRING()",
                code="TC-SEM-006",
            )
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert floating point literal to '{target_type}'",
            code="TC-SEM-006",
        )

    if t_clean in ("ANY_INT", "ANY_NUM", "ANY_BIT"):
        if s_clean in all_ints:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if s_clean in FLOATS:
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message=f"Implicit conversion from floating point '{source_type}' to integer: fractional part will be truncated",
                code="TC-SEM-007",
            )
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert type '{source_type}' to '{target_type}'",
            code="TC-SEM-006",
        )

    # 3. References & Pointers & Zero / Null
    if _is_null_or_zero(s_clean):
        if (
            t_clean.startswith("POINTER TO")
            or t_clean == "POINTER"
            or t_clean.startswith("REFERENCE TO")
            or t_clean == "REFERENCE"
            or _is_interface_type(t_clean, type_index, context_path)
        ):
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    if t_clean.startswith("REFERENCE TO") or t_clean == "REFERENCE":
        target_inner = t_clean[12:].strip() if t_clean.startswith("REFERENCE TO") else "ANY"
        if s_clean.startswith("REFERENCE TO"):
            source_inner = s_clean[12:].strip()
            return check_type_assignment(target_inner, source_inner, type_index, context_path)
        return check_type_assignment(target_inner, s_clean, type_index, context_path)

    if s_clean.startswith("REFERENCE TO") or s_clean == "REFERENCE":
        source_inner = s_clean[12:].strip() if s_clean.startswith("REFERENCE TO") else "ANY"
        return check_type_assignment(t_clean, source_inner, type_index, context_path)

    if t_clean.startswith("POINTER TO") or t_clean == "POINTER":
        if _is_null_or_zero(s_clean) or s_clean.startswith("POINTER TO"):
            if _is_null_or_zero(s_clean) or t_clean == "POINTER TO BYTE" or s_clean == "POINTER TO BYTE":
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
            if t_clean == s_clean:
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot convert pointer '{source_type}' to '{target_type}' without explicit conversion",
                code="TC-SEM-006",
            )
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot assign non-pointer type '{source_type}' to pointer '{target_type}'",
            code="TC-SEM-006",
        )

    if s_clean.startswith("POINTER TO") or s_clean == "POINTER":
        # Allowing pointer assignment to PVOID or memory-sized integers/bit-strings in low-level code
        if t_clean in ("PVOID", "DWORD", "LWORD", "UDINT", "ULINT"):
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot assign pointer type '{source_type}' to non-pointer '{target_type}'",
            code="TC-SEM-006",
        )

    # 4. OOP & Interface Conformance Check
    t_desc = type_index.get_type(t_clean, context_path=context_path) if type_index else None
    s_desc = type_index.get_type(s_clean, context_path=context_path) if type_index else None

    all_primitive_types = set(all_ints.keys()) | BOOLEAN_TYPES | {"STRING", "WSTRING"} | set(FLOATS.keys()) | set(TIME_TYPES.keys()) | set(DATE_TYPES.keys())

    # Target is Interface
    if _is_interface_type(t_clean, type_index, context_path):
        if _is_null_or_zero(s_clean):
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if s_clean in all_primitive_types or is_s_8str or is_s_16str:
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot assign primitive type '{source_type}' to interface '{target_type}'",
                code="TC-SEM-006",
            )
        is_source_itf = _is_interface_type(s_clean, type_index, context_path)
        is_source_fb = _is_fb_type(s_clean, type_index, context_path)
        # In TwinCAT, assigning an FB, Interface, or external library type to an Interface is valid
        if is_source_itf or is_source_fb or s_desc is None or t_desc is None:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if s_desc and _implements_interface(s_desc, t_clean, type_index, context_path):
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if s_desc and s_desc.kind == SymbolKind.STRUCT:
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot assign STRUCT '{source_type}' to interface '{target_type}'",
                code="TC-SEM-006",
            )
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # Source is Interface but Target is Primitive
    if _is_interface_type(s_clean, type_index, context_path):
        if t_clean in all_primitive_types or is_t_8str or is_t_16str:
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot assign interface '{source_type}' to primitive type '{target_type}'",
                code="TC-SEM-006",
            )

    # Target is base FB / POU, Source is derived FB (EXTENDS multi-level)
    if t_desc and s_desc:
        if t_desc.kind in (SymbolKind.POU, SymbolKind.FUNCTION_BLOCK):
            if _inherits_from_class(s_desc, t_clean, type_index, context_path):
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # 5. Booleans
    if t_clean in BOOLEAN_TYPES:
        if s_clean in BOOLEAN_TYPES:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert non-boolean type '{source_type}' to '{target_type}'",
            code="TC-SEM-006",
        )

    if s_clean in BOOLEAN_TYPES:
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert boolean type '{source_type}' to '{target_type}'",
            code="TC-SEM-006",
        )

    # 6. Strings (STRING, STRING(n), T_MaxString, WSTRING, aliases)
    if (is_t_8str or is_t_16str) and (is_s_8str or is_s_16str):
        if is_t_8str and is_s_8str:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if is_t_16str and is_s_16str:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        if is_t_16str and is_s_8str:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)  # Widening STRING to WSTRING
        if is_t_8str and is_s_16str:
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message="Implicit conversion from 'WSTRING' to 'STRING': possible loss of non-ASCII characters",
                code="TC-SEM-007",
            )

    if (is_t_8str or is_t_16str) != (is_s_8str or is_s_16str):
        if is_t_8str or is_t_16str:
            if s_clean in all_ints or s_clean in ("ANY_INT", "INT_LITERAL", "ANY_NUM", "ANY_BIT"):
                return TypeCheckResult(
                    TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                    message=f"Cannot convert integer type '{source_type}' to '{target_type}' without TO_STRING()",
                    code="TC-SEM-006",
                )
            if s_clean in FLOATS or s_clean in ("ANY_REAL", "REAL_LITERAL"):
                return TypeCheckResult(
                    TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                    message=f"Cannot convert floating point type '{source_type}' to '{target_type}' without TO_STRING()",
                    code="TC-SEM-006",
                )
        if is_s_8str or is_s_16str:
            if t_clean in all_ints:
                return TypeCheckResult(
                    TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                    message=f"Cannot convert string type '{source_type}' to integer '{target_type}' without conversion",
                    code="TC-SEM-006",
                )
            if t_clean in FLOATS:
                return TypeCheckResult(
                    TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                    message=f"Cannot convert string type '{source_type}' to float '{target_type}' without conversion",
                    code="TC-SEM-006",
                )

    # 7. Date & Time Types
    for type_group, name in (
        (TIME_TYPES, "TIME"),
        (DATE_TYPES, "DATE"),
        (TOD_TYPES, "TOD"),
        (DT_TYPES, "DT"),
    ):
        if t_clean in type_group or s_clean in type_group:
            if t_clean in type_group and s_clean in type_group:
                t_rank = type_group[t_clean][1]
                s_rank = type_group[s_clean][1]
                if t_rank >= s_rank:
                    return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
                return TypeCheckResult(
                    TypeCheckResultKind.NARROWING_WARNING,
                    message=f"Implicit conversion from '{source_type}' to '{target_type}': possible loss of data",
                    code="TC-SEM-007",
                )
            return TypeCheckResult(
                TypeCheckResultKind.TYPE_MISMATCH_ERROR,
                message=f"Cannot convert time/date type '{source_type}' to '{target_type}'",
                code="TC-SEM-006",
            )

    # 8. Floating Point Numbers (REAL, LREAL)
    if t_clean in FLOATS or s_clean in FLOATS:
        if t_clean in FLOATS and s_clean in FLOATS:
            t_rank = FLOATS[t_clean][1]
            s_rank = FLOATS[s_clean][1]
            if t_rank >= s_rank:
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message=f"Implicit conversion from '{source_type}' to '{target_type}': possible loss of precision",
                code="TC-SEM-007",
            )

        # Integer/BitString to Float
        if t_clean in FLOATS and (s_clean in SIGNED_INTS or s_clean in UNSIGNED_INTS or s_clean in BIT_STRINGS):
            s_size = (
                SIGNED_INTS.get(s_clean, (0, 0))[0]
                or UNSIGNED_INTS.get(s_clean, (0, 0))[0]
                or BIT_STRINGS.get(s_clean, (0, 0))[0]
            )
            if t_clean == "LREAL" and s_size <= 32:
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
            if t_clean == "REAL" and s_size <= 16:
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message=f"Implicit conversion from '{source_type}' to '{target_type}': possible loss of precision",
                code="TC-SEM-007",
            )

        # Float to Integer/BitString
        if s_clean in FLOATS and (t_clean in SIGNED_INTS or t_clean in UNSIGNED_INTS or t_clean in BIT_STRINGS):
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message=f"Implicit conversion from floating point '{source_type}' to integer '{target_type}': fractional part will be truncated",
                code="TC-SEM-007",
            )

        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert '{source_type}' to '{target_type}'",
            code="TC-SEM-006",
        )

    # 9. Integer & Bit-String Conversions (SINT, INT, DINT, LINT, USINT, UINT, UDINT, ULINT, BYTE, WORD, DWORD, LWORD, HRESULT)
    if t_clean in all_ints and s_clean in all_ints:
        # In TwinCAT 3 ST, numeric and bit-string assignments are freely supported and coerced
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # 10. Complex / User Types (DUTs, Structs, FBs) Mismatch
    if (
        t_clean not in all_ints
        and s_clean not in all_ints
        and t_clean not in BOOLEAN_TYPES
        and s_clean not in BOOLEAN_TYPES
    ):
        if type_index:
            t_desc = type_index.get_type(t_clean, context_path=context_path)
            s_desc = type_index.get_type(s_clean, context_path=context_path)
            # If either type is from an external library or not indexed locally, assume compatible
            if not t_desc or not s_desc:
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
            if t_desc.name.lower() == s_desc.name.lower():
                return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        else:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert type '{source_type}' to '{target_type}'",
            code="TC-SEM-006",
        )

    return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
