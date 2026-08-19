"""CFC migration pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from migrator.cfc.mapper import inject_exec_order_comments, map_cfc_to_ir
from migrator.cfc.parser import parse_cfc_graph
from migrator.cfc.types import CFCGraph
from migrator.cfc.xml_patch import write_cfc_st_to_xml
from migrator.codegen import convert_networks_to_st
from migrator.constants import SCRIPT_VERSION
from migrator.pipeline import main_from_process_file, write_migration_output
from migrator.reporting import MigrationLogger, MigrationReport, _print_dry_run
from migrator.types import MigrationConfig, TcFile
from migrator.validation import build_generated_header, calculate_accuracy, validate_generated_st
from migrator.xml_reader import load_file

CFC_SOURCE_TYPE = "CFC"
CFC_TOOL_NAME = "migrator.cfc"


def _print_cfc_analysis(tc: TcFile, graph: CFCGraph) -> None:
    print(f"\n{'=' * 60}")
    print(f"CFC ANALYSIS: {tc.path.name}")
    print(f"{'=' * 60}")
    print(f"  POU Name:       {tc.pou_name}")
    print(f"  POU Type:       {tc.pou_type}")
    print(f"  Implementation: {tc.impl_type}")

    boxes = [e for e in graph.elements.values() if e.element_type == "box"]
    inputs = [e for e in graph.elements.values() if e.element_type == "input"]
    outputs = [e for e in graph.elements.values() if e.element_type == "output"]

    print(f"  Elements:       {len(graph.elements)} total")
    print(f"    Boxes:        {len(boxes)}")
    print(f"    Inputs:       {len(inputs)}")
    print(f"    Outputs:      {len(outputs)}")
    print(f"  Connections:    {len(graph.connections)}")
    print(f"  Exec order:     {len(graph.execution_order)} elements")

    for elem in boxes:
        kind = elem.kind_of_call
        if kind == "FunctionBlock":
            print(f"    FB: {elem.box_type} inst={elem.instance_name}")
        else:
            print(f"    Op: {elem.box_type}")

    for elem in outputs:
        print(f"    Out: {elem.var_name}")
    print()


def process_file(
    path: Path,
    cfg: MigrationConfig,
    mlog: MigrationLogger,
    report: MigrationReport,
) -> bool:
    mlog.log(f"Processing: {path}")

    tc = load_file(path, cfg.encoding)
    if tc is None:
        mlog.log("  ERROR: Cannot load file")
        return False

    if tc.errors:
        for e in tc.errors:
            mlog.log(f"  ERROR: {e}")
        report.add(tc, None, None, False)
        return False

    mlog.log(f"  File type: {tc.file_type}")
    mlog.log(f"  POU: {tc.pou_name} ({tc.pou_type})")
    mlog.log(f"  Implementation: {tc.impl_type}")

    if tc.file_type in (".tcgvl", ".tcdut"):
        mlog.log(f"  SKIP: {tc.file_type} has no implementation to migrate")
        return True

    if tc.impl_type != "CFC":
        if tc.impl_type in ("NWL", "SFC", "IL"):
            mlog.log(f"  SKIP: {tc.impl_type} - use FBD migrator for NWL")
            tc.warnings.append(f"{tc.impl_type} not a CFC implementation")
        else:
            mlog.log(f"  SKIP: Implementation is {tc.impl_type}, not CFC")
        return True

    graph = parse_cfc_graph(tc)
    if graph is None:
        mlog.log("  ERROR: Failed to parse CFC graph")
        tc.errors.append("CFC graph parsing failed")
        report.add(tc, None, None, False)
        return False

    mlog.log(
        f"  CFC elements: {len(graph.elements)} "
        f"(boxes: {sum(1 for e in graph.elements.values() if e.element_type == 'box')}, "
        f"inputs: {sum(1 for e in graph.elements.values() if e.element_type == 'input')}, "
        f"outputs: {sum(1 for e in graph.elements.values() if e.element_type == 'output')})"
    )
    mlog.log(f"  Connections: {len(graph.connections)}")
    mlog.log(f"  Execution order: {len(graph.execution_order)} elements")

    if cfg.analyze_only:
        mlog.log("  ANALYZE-ONLY: No ST generation")
        _print_cfc_analysis(tc, graph)
        report.add(tc, None, None, False)
        return True

    tc.networks = map_cfc_to_ir(graph, tc)
    mlog.log(
        f"  IR networks: {len(tc.networks)}, "
        f"items: {sum(len(nw.items) for nw in tc.networks)}"
    )

    convert_networks_to_st(tc, cfg)
    inject_exec_order_comments(tc)

    mlog.log(f"  ST generated: {len(tc.generated_st.splitlines())} lines")
    if tc.todos:
        mlog.log(f"  TODOs: {len(tc.todos)}")
        for t in tc.todos:
            mlog.log(f"    {t}")

    valid = validate_generated_st(tc, cfg)
    if tc.warnings:
        for w in tc.warnings:
            mlog.log(f"  WARNING: {w}")
    if tc.errors:
        for e in tc.errors:
            mlog.log(f"  ERROR: {e}")

    acc = calculate_accuracy(tc)
    tm_count = tc.generated_st.count("TYPE MISMATCH:")
    header = build_generated_header(
        CFC_SOURCE_TYPE, tc.path.name, CFC_TOOL_NAME, SCRIPT_VERSION, acc, tm_count
    )
    tc.generated_st = header + tc.generated_st

    if not valid and cfg.strict:
        mlog.log("  ABORTED: Validation failed in strict mode")
        report.add(tc, None, None, False)
        return False

    if cfg.dry_run:
        acc = calculate_accuracy(tc)
        mlog.log(f"  DRY-RUN: No files changed (Accuracy: {acc:.2f} %)")
        _print_dry_run(tc, cfg)
        report.add(tc, None, None, False)
        return True

    new_file = not cfg.force
    xml_content = write_cfc_st_to_xml(tc, regenerate_ids=new_file)
    if xml_content is None:
        mlog.log("  ERROR: Failed to generate output XML")
        tc.errors.append("XML generation failed")
        report.add(tc, None, None, False)
        return False

    return write_migration_output(tc, cfg, mlog, report, xml_content)


def main(argv: Optional[List[str]] = None) -> int:
    return main_from_process_file(process_file, "TwinCAT CFC-to-ST Migrator", argv)
