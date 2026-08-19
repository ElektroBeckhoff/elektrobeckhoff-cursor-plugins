"""Validation and accuracy helpers for generated ST code."""
from __future__ import annotations

import datetime

from .types import (
    AssignNode,
    BoxNode,
    DemuxNode,
    MigrationConfig,
    OperandNode,
    TcFile,
)


def calculate_accuracy(tc: TcFile) -> float:
    """Calculate migration accuracy as percentage with two decimals (0.00-100.00).

    Based on the ratio of problem items to total items.  Each TODO counts
    as 1 failed item, each warning as 0.5.  Uses the item count within
    networks as denominator when it exceeds the network count (e.g. CFC
    packs many statements into a single network).
    """
    item_count = sum(len(nw.items) for nw in tc.networks)
    total = max(len(tc.networks), len(tc.st_networks), item_count, 1)
    penalty = len(tc.todos) + len(tc.warnings) * 0.5
    if penalty <= 0:
        return 100.0
    return max(0.0, round((total - penalty) / total * 100, 2))


def build_generated_header(source_type: str, source_file: str,
                           tool_name: str, version: str = "",
                           accuracy: float = 100.0,
                           type_mismatches: int = 0) -> str:
    """Build a uniform warning header for auto-generated ST code.

    Parameters
    ----------
    source_type : str
        The original implementation language, e.g. ``"FBD/FUP"`` or ``"CFC"``.
    source_file : str
        Filename of the source ``.TcPOU`` being migrated.
    tool_name : str
        Name of the migration tool, e.g. ``"migrator.fbd"`` or ``"migrator.cfc"``.
    version : str
        Script version string, e.g. ``"1.0.0"``.
    accuracy : float
        Migration accuracy percentage (0.00-100.00).
    type_mismatches : int
        Number of TYPE MISMATCH occurrences in the generated code.
    """
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ver_line = f"   Version:          {version}\n" if version else ""
    acc_line = f"   Accuracy:         {accuracy:.2f} %\n"
    if type_mismatches > 0:
        tm_line = f"   Type Mismatches:  {type_mismatches} !\n"
    else:
        tm_line = ""
    return (
        f"(* {'=' * 76}\n"
        f"   AUTO-GENERATED from {source_type} by {tool_name}\n"
        f"   Source:           {source_file}\n"
        f"{ver_line}"
        f"   Date:             {ts}\n"
        f"{acc_line}"
        f"{tm_line}"
        f"\n"
        f"   WARNING: This code was automatically converted from a "
        f"{source_type} implementation.\n"
        f"   Statement order is derived from the execution order stored "
        f"in the XML.\n"
        f"   MANUAL VERIFICATION REQUIRED before productive use.\n"
        f"   {'=' * 76} *)\n"
        f"\n"
    )


def validate_generated_st(tc: TcFile, cfg: MigrationConfig) -> bool:
    ok = True

    if not tc.generated_st.strip():
        tc.errors.append("Generated ST is empty")
        ok = False

    if not tc.pou_name:
        tc.warnings.append("POU name not detected")

    if not tc.pou_type or tc.pou_type == "UNKNOWN":
        tc.warnings.append("POU type not detected")

    nwl_vars = set()
    for nw in tc.networks:
        _collect_vars(nw.items, nwl_vars)

    st_text = tc.generated_st
    missing = []
    for var in nwl_vars:
        clean = var.split(".")[-1] if "." in var else var
        if clean and clean not in st_text and var not in st_text:
            if not clean.startswith("'") and clean not in ("TRUE", "FALSE", ""):
                missing.append(var)

    if missing:
        tc.warnings.append(f"Variables from NWL not found in ST: {', '.join(missing[:10])}")

    expected_networks = len(tc.networks)
    if tc.impl_type == "CFC":
        actual_separators = tc.generated_st.count("(* CFC Exec Order:")
        if expected_networks > 0 and actual_separators == 0:
            tc.warnings.append(
                f"CFC exec-order comments missing: expected at least 1, found 0"
            )
    else:
        actual_separators = tc.generated_st.count("(* FBD Network ")
        if actual_separators < expected_networks:
            tc.warnings.append(
                f"Network count mismatch: {expected_networks} networks, "
                f"{actual_separators} comment blocks"
            )

    if tc.todos and cfg.fail_on_unclear:
        tc.warnings.append(f"Contains {len(tc.todos)} TODO markers")
        if cfg.strict:
            tc.errors.append("Strict mode: TODOs present, aborting")
            ok = False

    type_mismatches = tc.generated_st.count("TYPE MISMATCH:")
    tc.stats = {
        "networks": len(tc.networks),
        "st_lines": len(tc.generated_st.splitlines()),
        "todos": len(tc.todos),
        "warnings": len(tc.warnings),
        "errors": len(tc.errors),
        "type_mismatches": type_mismatches,
        "variables_referenced": len(nwl_vars),
    }

    return ok


def _collect_vars(items, var_set: set):
    for item in items:
        if isinstance(item, DemuxNode):
            if item.input and not item.input.is_empty:
                var_set.add(item.input.name)
        elif isinstance(item, AssignNode):
            for o in item.outputs:
                if not o.is_empty:
                    var_set.add(o.name)
            if item.rvalue:
                if isinstance(item.rvalue, AssignNode):
                    _collect_vars([item.rvalue], var_set)
                elif isinstance(item.rvalue, DemuxNode):
                    if item.rvalue.input and not item.rvalue.input.is_empty:
                        var_set.add(item.rvalue.input.name)
                else:
                    _collect_vars_node(item.rvalue, var_set)
        elif isinstance(item, BoxNode):
            _collect_vars_node(item, var_set)


def _collect_vars_node(node, var_set: set):
    if isinstance(node, OperandNode):
        if not node.is_empty and node.name not in ("TRUE", "FALSE"):
            var_set.add(node.name)
        return
    if isinstance(node, BoxNode):
        if node.instance and not node.instance.is_empty:
            var_set.add(node.instance.name)
        for inp in node.input_items:
            _collect_vars_node(inp, var_set)
        for out in node.output_items:
            if not out.is_empty:
                var_set.add(out.name)
