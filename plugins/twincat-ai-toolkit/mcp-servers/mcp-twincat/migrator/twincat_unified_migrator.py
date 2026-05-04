#!/usr/bin/env python3
"""
Unified TwinCAT 3 FBD/FUP + CFC to Structured Text (ST) Migration Tool.

Auto-detects the implementation type (NWL / CFC) per file and routes
to the appropriate converter.  Produces a single combined report and
shared backup directory.

Usage:
    python twincat_unified_migrator.py --input "path/to/File.TcPOU"
    python twincat_unified_migrator.py --input "path/to/project" --recursive
    python twincat_unified_migrator.py --input "path/to/project" --recursive --dry-run
    python twincat_unified_migrator.py --input "path/to/project" --recursive --force
"""

from __future__ import annotations

import datetime
import logging
import sys
import traceback
from pathlib import Path
from typing import List, Optional

from twincat_migrator_base import (
    MigrationConfig,
    MigrationLogger,
    MigrationReport,
    SCRIPT_VERSION,
    collect_input_files,
    load_config,
    load_file,
    parse_arguments,
)
from twincat_fbd_to_st_migrator import process_file as fbd_process_file
from twincat_cfc_to_st_migrator import process_file as cfc_process_file

TOOL_NAME = "twincat_unified_migrator"


# ---------------------------------------------------------------------------
# Per-file router
# ---------------------------------------------------------------------------

def process_file(
    path: Path,
    cfg: MigrationConfig,
    mlog: MigrationLogger,
    report: MigrationReport,
) -> bool:
    """Load a Tc* file, detect its implementation type, and delegate to
    the matching converter (FBD or CFC).  Files that are already ST or
    use unsupported languages are skipped gracefully.
    """
    tc = load_file(path, cfg.encoding)
    if tc is None:
        mlog.log(f"Processing: {path}")
        mlog.log(f"  ERROR: Cannot load file")
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
        mlog.log(f"  SKIP: Already Structured Text")
        return True

    mlog.log(f"Processing: {path}")
    mlog.log(f"  SKIP: {tc.impl_type} not supported by unified migrator")
    return True


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    cfg = parse_arguments(argv)
    logging.basicConfig(level=getattr(logging, cfg.log_level, logging.INFO),
                        format="%(levelname)s: %(message)s")
    cfg = load_config(cfg)

    input_p = Path(cfg.input_path)
    prefix = input_p.stem.lower() if input_p.is_file() else input_p.name.lower()
    ts_batch = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")

    if input_p.is_dir() and not cfg.dry_run and not cfg.analyze_only:
        use_swap = cfg.swap and not cfg.force and not cfg.output_path
        if cfg.output_path and not cfg.force:
            bd = Path(cfg.output_path)
            bd.mkdir(parents=True, exist_ok=True)
            cfg.batch_dir = str(bd)
            base_path = bd
        elif use_swap:
            batch_name = f"{input_p.name}_backup_{ts_batch}"
            bd = input_p.parent / batch_name
            bd.mkdir(parents=True, exist_ok=True)
            cfg.batch_dir = str(bd)
            base_path = bd
        elif not cfg.force:
            batch_name = f"{input_p.name}_st_generated_{ts_batch}"
            bd = input_p.parent / batch_name
            bd.mkdir(parents=True, exist_ok=True)
            cfg.batch_dir = str(bd)
            base_path = bd
        else:
            base_path = input_p

        if cfg.force and cfg.backup:
            bkp_name = f"{input_p.name}_backup_{ts_batch}"
            bkp_dir = input_p.parent / bkp_name
            bkp_dir.mkdir(parents=True, exist_ok=True)
            cfg.backup_dir = str(bkp_dir)
    else:
        base_path = input_p.parent if input_p.is_file() else input_p

    mlog = MigrationLogger(cfg.log_enabled, base_path, prefix)
    report = MigrationReport(cfg.report_enabled, base_path, prefix)

    mlog.log(f"TwinCAT Unified Migrator v{SCRIPT_VERSION}")
    mlog.log(f"Input: {cfg.input_path}")
    mlog.log(f"Mode: {'dry-run' if cfg.dry_run else 'analyze-only' if cfg.analyze_only else 'migrate'}")
    mlog.log(f"Force: {cfg.force}, Swap: {cfg.swap}, Backup: {cfg.backup}, Strict: {cfg.strict}")

    files = collect_input_files(cfg)
    if not files:
        mlog.log("No supported files found.")
        print("No supported files found.")
        mlog.save()
        return 1

    mlog.log(f"Files to process: {len(files)}")

    success_count = 0
    fail_count = 0

    for f in files:
        try:
            result = process_file(f, cfg, mlog, report)
            if result:
                success_count += 1
            else:
                fail_count += 1
        except Exception as exc:
            mlog.log(f"EXCEPTION processing {f}: {exc}")
            mlog.log(traceback.format_exc())
            fail_count += 1

    acc_values = [r["accuracy"] for r in report.file_reports if r.get("accuracy") is not None]
    overall_acc = round(sum(acc_values) / len(acc_values), 2) if acc_values else 100.0

    nwl_count = sum(1 for r in report.file_reports if r.get("impl_type_before") == "NWL")
    cfc_count = sum(1 for r in report.file_reports if r.get("impl_type_before") == "CFC")
    skip_count = success_count - nwl_count - cfc_count

    mlog.log(f"Done. FBD: {nwl_count}, CFC: {cfc_count}, Skipped: {skip_count}, "
             f"Failed: {fail_count}, Accuracy: {overall_acc:.2f} %")
    print(f"\nMigration complete. FBD: {nwl_count}, CFC: {cfc_count}, "
          f"Skipped: {skip_count}, Failed: {fail_count}, Accuracy: {overall_acc:.2f} %")

    mlog.save()
    report.save()

    if mlog.enabled and mlog.entries:
        print(f"Log: {mlog.log_path}")
    if report.enabled and report.file_reports:
        print(f"Report: {report.report_path}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
