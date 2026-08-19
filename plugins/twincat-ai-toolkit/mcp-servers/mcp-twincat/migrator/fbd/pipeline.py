"""FBD/FUP migration pipeline."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from migrator.codegen import convert_networks_to_st
from migrator.constants import SCRIPT_VERSION
from migrator.fbd.parser import parse_nwl_networks
from migrator.fbd.xml_patch import write_st_to_xml
from migrator.pipeline import main_from_process_file, write_migration_output
from migrator.reporting import MigrationLogger, MigrationReport, _print_analysis, _print_dry_run
from migrator.types import MigrationConfig, TcFile
from migrator.validation import build_generated_header, calculate_accuracy, validate_generated_st
from migrator.xml_reader import load_file

FBD_SOURCE_TYPE = "FBD/FUP"
FBD_TOOL_NAME = "migrator.fbd"


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

    if tc.impl_type != "NWL":
        if tc.impl_type in ("CFC", "SFC", "IL"):
            mlog.log(f"  SKIP: {tc.impl_type} migration not supported")
            tc.warnings.append(f"{tc.impl_type} migration not supported")
        else:
            mlog.log(f"  SKIP: Implementation is {tc.impl_type}, not FBD/NWL")
        return True

    parse_nwl_networks(tc)
    mlog.log(f"  Networks parsed: {len(tc.networks)}")
    for nw in tc.networks:
        mlog.log(
            f"    Network {nw.index + 1}: {len(nw.items)} items"
            + (", OutCommented" if nw.out_commented else "")
        )

    action_nwl_count = sum(1 for a in tc.actions if a.networks)
    if action_nwl_count:
        mlog.log(f"  Actions with NWL: {action_nwl_count}")

    if cfg.analyze_only:
        mlog.log("  ANALYZE-ONLY: No ST generation")
        _print_analysis(tc)
        report.add(tc, None, None, False)
        return True

    convert_networks_to_st(tc, cfg)

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
        FBD_SOURCE_TYPE, tc.path.name, FBD_TOOL_NAME, SCRIPT_VERSION, acc, tm_count
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
    xml_content = write_st_to_xml(tc, regenerate_ids=new_file)
    if xml_content is None:
        mlog.log("  ERROR: Failed to generate output XML")
        tc.errors.append("XML generation failed")
        report.add(tc, None, None, False)
        return False

    return write_migration_output(tc, cfg, mlog, report, xml_content)


def main(argv: Optional[List[str]] = None) -> int:
    return main_from_process_file(process_file, "TwinCAT FBD-to-ST Migrator", argv)
