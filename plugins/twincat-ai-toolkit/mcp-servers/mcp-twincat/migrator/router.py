"""Unified FBD/CFC auto-routing migrator."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from migrator.cfc.pipeline import process_file as cfc_process_file
from migrator.fbd.pipeline import process_file as fbd_process_file
from migrator.pipeline import main_from_process_file
from migrator.reporting import MigrationLogger, MigrationReport
from migrator.types import MigrationConfig
from migrator.xml_reader import load_file

TOOL_NAME = "migrator.auto"


def process_file(
    path: Path,
    cfg: MigrationConfig,
    mlog: MigrationLogger,
    report: MigrationReport,
) -> bool:
    """Load a Tc* file, detect implementation type, delegate to FBD or CFC."""
    tc = load_file(path, cfg.encoding)
    if tc is None:
        mlog.log(f"Processing: {path}")
        mlog.log("  ERROR: Cannot load file")
        return False

    if tc.errors:
        mlog.log(f"Processing: {path}")
        for e in tc.errors:
            mlog.log(f"  ERROR: {e}")
        report.add(tc, None, None, False)
        return False

    if tc.file_type in (".tcgvl", ".tcdut"):
        mlog.log(f"Processing: {path}")
        mlog.log(f"  SKIP: {tc.file_type} has no implementation to migrate")
        return True

    if tc.impl_type == "NWL":
        return fbd_process_file(path, cfg, mlog, report)

    if tc.impl_type == "CFC":
        return cfc_process_file(path, cfg, mlog, report)

    if tc.impl_type == "ST":
        mlog.log(f"Processing: {path}")
        mlog.log("  SKIP: Already Structured Text")
        return True

    mlog.log(f"Processing: {path}")
    mlog.log(f"  SKIP: {tc.impl_type} not supported by unified migrator")
    return True


def _unified_completion_message(
    report: MigrationReport,
    mlog: MigrationLogger,
    success_count: int,
    fail_count: int,
) -> str:
    acc_values = [r["accuracy"] for r in report.file_reports if r.get("accuracy") is not None]
    overall_acc = round(sum(acc_values) / len(acc_values), 2) if acc_values else 100.0

    nwl_count = sum(1 for r in report.file_reports if r.get("impl_type_before") == "NWL")
    cfc_count = sum(1 for r in report.file_reports if r.get("impl_type_before") == "CFC")
    skip_count = success_count - nwl_count - cfc_count

    mlog.log(
        f"Done. FBD: {nwl_count}, CFC: {cfc_count}, Skipped: {skip_count}, "
        f"Failed: {fail_count}, Accuracy: {overall_acc:.2f} %"
    )
    return (
        f"\nMigration complete. FBD: {nwl_count}, CFC: {cfc_count}, "
        f"Skipped: {skip_count}, Failed: {fail_count}, Accuracy: {overall_acc:.2f} %"
    )


def main(argv: Optional[List[str]] = None) -> int:
    return main_from_process_file(
        process_file,
        "TwinCAT Unified Migrator",
        argv,
        completion_message=_unified_completion_message,
    )
