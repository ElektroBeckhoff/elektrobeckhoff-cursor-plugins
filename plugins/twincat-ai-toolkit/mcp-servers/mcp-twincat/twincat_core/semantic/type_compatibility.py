"""Type compatibility, conversion validation, and narrowing diagnostics for IEC 61131-3 and TwinCAT 3."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

from .symbols import SymbolKind

if TYPE_CHECKING:
    from .type_index import TypeIndex


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
BOOLEAN_TYPES: Set[str] = {"BOOL", "BIT"}

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
    if t.upper().startswith("POINTER TO"):
        inner = t[10:].strip()
        return f"POINTER TO {_clean_type_str(inner)}"
    if t.upper().startswith("REFERENCE TO"):
        inner = t[12:].strip()
        return f"REFERENCE TO {_clean_type_str(inner)}"
    if "[" in t:
        t = t.split("[")[0].strip()
    if "(" in t:
        t = t.split("(")[0].strip()
    return t.upper()


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

    # 1. Generic & Wildcard types (ANY, PVOID, __SYSTEM.*)
    if (
        t_clean in GENERIC_TYPES
        or s_clean in GENERIC_TYPES
        or t_clean.startswith("__SYSTEM.")
        or s_clean.startswith("__SYSTEM.")
    ):
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # 2. Identical types
    if t_clean == s_clean:
        return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # 3. Pointers & References
    if t_clean.startswith("POINTER TO") or t_clean == "POINTER":
        if s_clean in ("PVOID", "0", "NULL", "16#0") or s_clean.startswith("POINTER TO"):
            if s_clean in ("PVOID", "0", "NULL", "16#0") or t_clean == "POINTER TO BYTE" or s_clean == "POINTER TO BYTE":
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
    if type_index:
        t_desc = type_index.get_type(t_clean, context_path=context_path)
        s_desc = type_index.get_type(s_clean, context_path=context_path)

        if t_desc and s_desc:
            # Target is Interface, Source is POU implementing it
            if t_desc.kind == SymbolKind.INTERFACE and s_desc.kind in (SymbolKind.POU, SymbolKind.FUNCTION_BLOCK):
                if t_clean.lower() in [i.lower() for i in s_desc.implements_names]:
                    return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

            # Target is base FB, Source is derived FB (EXTENDS)
            if s_desc.extends_name and s_desc.extends_name.upper() == t_clean:
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

    # 6. Strings
    if t_clean in STRING_TYPES or s_clean in STRING_TYPES:
        if t_clean == "WSTRING" and s_clean == "STRING":
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)  # Widening
        if t_clean == "STRING" and s_clean == "WSTRING":
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message="Implicit conversion from 'WSTRING' to 'STRING': possible loss of non-ASCII characters",
                code="TC-SEM-007",
            )
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert string type '{source_type}' to '{target_type}'",
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

    # 9. Signed Integers to Signed Integers
    if t_clean in SIGNED_INTS and s_clean in SIGNED_INTS:
        t_rank = SIGNED_INTS[t_clean][1]
        s_rank = SIGNED_INTS[s_clean][1]
        if t_rank >= s_rank:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        return TypeCheckResult(
            TypeCheckResultKind.NARROWING_WARNING,
            message=f"Implicit conversion from '{source_type}' to '{target_type}': possible loss of data",
            code="TC-SEM-007",
        )

    # 10. Unsigned Integers to Unsigned Integers
    if t_clean in UNSIGNED_INTS and s_clean in UNSIGNED_INTS:
        t_rank = UNSIGNED_INTS[t_clean][1]
        s_rank = UNSIGNED_INTS[s_clean][1]
        if t_rank >= s_rank:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        return TypeCheckResult(
            TypeCheckResultKind.NARROWING_WARNING,
            message=f"Implicit conversion from '{source_type}' to '{target_type}': possible loss of data",
            code="TC-SEM-007",
        )

    # 11. Bit Strings to Bit Strings
    if t_clean in BIT_STRINGS and s_clean in BIT_STRINGS:
        t_rank = BIT_STRINGS[t_clean][1]
        s_rank = BIT_STRINGS[s_clean][1]
        if t_rank >= s_rank:
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
        return TypeCheckResult(
            TypeCheckResultKind.NARROWING_WARNING,
            message=f"Implicit conversion from '{source_type}' to '{target_type}': possible loss of data",
            code="TC-SEM-007",
        )

    # 12. Cross-group Numeric / BitString conversions (Sign change / Size mismatch)
    all_ints = {**SIGNED_INTS, **UNSIGNED_INTS, **BIT_STRINGS}
    if t_clean in all_ints and s_clean in all_ints:
        t_size = all_ints[t_clean][0]
        s_size = all_ints[s_clean][0]

        if s_size > t_size:
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message=f"Implicit conversion from '{source_type}' to '{target_type}': possible loss of data and sign change",
                code="TC-SEM-007",
            )
        if s_size == t_size and (t_clean in SIGNED_INTS) != (s_clean in SIGNED_INTS):
            return TypeCheckResult(
                TypeCheckResultKind.NARROWING_WARNING,
                message=f"Implicit conversion from '{source_type}' to '{target_type}': possible change of sign",
                code="TC-SEM-007",
            )
        if s_size < t_size:
            if s_clean in SIGNED_INTS and t_clean not in SIGNED_INTS:
                return TypeCheckResult(
                    TypeCheckResultKind.NARROWING_WARNING,
                    message=f"Implicit conversion from signed '{source_type}' to unsigned '{target_type}': possible change of sign",
                    code="TC-SEM-007",
                )
            return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)

    # 13. Complex / User Types (DUTs, Structs, FBs) Mismatch
    if (
        t_clean not in all_ints
        and s_clean not in all_ints
        and t_clean not in BOOLEAN_TYPES
        and s_clean not in BOOLEAN_TYPES
    ):
        return TypeCheckResult(
            TypeCheckResultKind.TYPE_MISMATCH_ERROR,
            message=f"Cannot convert type '{source_type}' to '{target_type}'",
            code="TC-SEM-006",
        )

    return TypeCheckResult(TypeCheckResultKind.COMPATIBLE)
