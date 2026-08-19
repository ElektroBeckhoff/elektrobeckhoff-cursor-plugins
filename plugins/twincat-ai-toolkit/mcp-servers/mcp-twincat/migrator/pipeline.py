"""Shared migration pipeline helpers (output write + batch runner)."""
from __future__ import annotations

import datetime
import logging
import shutil
import traceback
from pathlib import Path
from typing import Callable, List, Optional

from migrator.cli import load_config, parse_arguments
from migrator.constants import SCRIPT_VERSION
from migrator.io_utils import (
    _resolve_output_path,
    can_replace,
    collect_input_files,
    create_backup,
    write_output_file,
)
from migrator.reporting import MigrationLogger, MigrationReport
from migrator.types import MigrationConfig, TcFile

ProcessFileFn = Callable[[Path, MigrationConfig, MigrationLogger, MigrationReport], bool]
CompletionMessageFn = Callable[[MigrationReport, MigrationLogger, int, int], str]


def write_migration_output(
    tc: TcFile,
    cfg: MigrationConfig,
    mlog: MigrationLogger,
    report: MigrationReport,
    xml_content: str,
) -> bool:
    """Write migrated XML using force / swap / default output modes."""
    use_swap = cfg.swap and not cfg.force and not cfg.output_path
    backup_path: Optional[Path] = None

    if cfg.force:
        if cfg.backup:
            bkp_dir = Path(cfg.backup_dir) if cfg.backup_dir else None
            inp_root = Path(cfg.input_path) if cfg.backup_dir else None
            backup_path = create_backup(tc.path, bkp_dir, inp_root)
            if backup_path is None:
                mlog.log("  ERROR: Backup failed, will not force-overwrite")
                tc.errors.append("Backup creation failed")
                report.add(tc, None, None, False)
                return False
            mlog.log(f"  Backup: {backup_path}")
        elif cfg.strict:
            mlog.log("  ERROR: Strict mode requires backup for --force")
            tc.errors.append("Strict mode: cannot force-overwrite without backup")
            report.add(tc, None, None, False)
            return False
        else:
            mlog.log("  WARNING: Force-overwriting without backup!")

        replaceable, reason = can_replace(tc, cfg, backup_path)
        if not replaceable:
            mlog.log(f"  BLOCKED: {reason}")
            report.add(tc, backup_path, None, False)
            return False

        ok = write_output_file(xml_content, tc.path, tc.encoding)
        if ok:
            mlog.log(f"  FORCE-OVERWRITTEN: {tc.path}")
        else:
            mlog.log("  ERROR: Force-overwrite failed")
        report.add(tc, backup_path, tc.path, ok)
        return ok

    if use_swap:
        if cfg.batch_dir:
            input_root = Path(cfg.input_path)
            try:
                rel = tc.path.relative_to(input_root)
            except ValueError:
                rel = Path(tc.path.name)
            backup_path = Path(cfg.batch_dir) / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
            backup_path = tc.path.parent / f"{tc.path.stem}_backup_{ts}{tc.path.suffix}"
        try:
            shutil.copy2(str(tc.path), str(backup_path))
        except Exception as exc:
            mlog.log(f"  ERROR: Cannot copy to backup: {exc}")
            tc.errors.append(f"Swap backup failed: {exc}")
            report.add(tc, None, None, False)
            return False
        mlog.log(f"  BACKUP: {backup_path}")

        ok = write_output_file(xml_content, tc.path, tc.encoding)
        if ok:
            mlog.log(f"  OUTPUT: {tc.path} (original path)")
        else:
            mlog.log("  ERROR: Write failed, restoring original from backup")
            try:
                shutil.copy2(str(backup_path), str(tc.path))
            except Exception:
                mlog.log(f"  CRITICAL: Restore failed! Backup at {backup_path}")
        report.add(tc, backup_path, tc.path if ok else None, False)
        return ok

    if cfg.batch_dir:
        input_root = Path(cfg.input_path)
        try:
            rel = tc.path.relative_to(input_root)
        except ValueError:
            rel = Path(tc.path.name)
        output_path = Path(cfg.batch_dir) / rel
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = _resolve_output_path(tc.path, cfg)
    ok = write_output_file(xml_content, output_path, tc.encoding)
    if ok:
        mlog.log(f"  OUTPUT: {output_path}")
    else:
        mlog.log(f"  ERROR: Write failed: {output_path}")
    report.add(tc, None, output_path, False)
    return ok


def _setup_batch_dirs(cfg: MigrationConfig) -> Path:
    """Configure ``cfg.batch_dir`` / ``cfg.backup_dir`` for directory inputs."""
    input_p = Path(cfg.input_path)
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
        return base_path

    return input_p.parent if input_p.is_file() else input_p


def run_batch(
    cfg: MigrationConfig,
    process_file_fn: ProcessFileFn,
    tool_title: str,
    *,
    completion_message: Optional[CompletionMessageFn] = None,
) -> int:
    """Shared main() loop: logging setup, batch dirs, file loop, report save."""
    input_p = Path(cfg.input_path)
    prefix = input_p.stem.lower() if input_p.is_file() else input_p.name.lower()
    base_path = _setup_batch_dirs(cfg)

    mlog = MigrationLogger(cfg.log_enabled, base_path, prefix)
    report = MigrationReport(cfg.report_enabled, base_path, prefix)

    mlog.log(f"{tool_title} v{SCRIPT_VERSION}")
    mlog.log(f"Input: {cfg.input_path}")
    mlog.log(
        f"Mode: {'dry-run' if cfg.dry_run else 'analyze-only' if cfg.analyze_only else 'migrate'}"
    )
    mlog.log(
        f"Force: {cfg.force}, Swap: {cfg.swap}, Backup: {cfg.backup}, Strict: {cfg.strict}"
    )

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
            result = process_file_fn(f, cfg, mlog, report)
            if result:
                success_count += 1
            else:
                fail_count += 1
        except Exception as exc:
            mlog.log(f"EXCEPTION processing {f}: {exc}")
            mlog.log(traceback.format_exc())
            fail_count += 1

    if completion_message is not None:
        summary = completion_message(report, mlog, success_count, fail_count)
    else:
        acc_values = [
            r["accuracy"] for r in report.file_reports if r.get("accuracy") is not None
        ]
        overall_acc = round(sum(acc_values) / len(acc_values), 2) if acc_values else 100.0
        summary = (
            f"\nMigration complete. Success: {success_count}, Failed: {fail_count}, "
            f"Accuracy: {overall_acc:.2f} %"
        )
        mlog.log(
            f"Done. Success: {success_count}, Failed: {fail_count}, "
            f"Accuracy: {overall_acc:.2f} %"
        )

    print(summary)

    mlog.save()
    report.save()

    if mlog.enabled and mlog.entries:
        print(f"Log: {mlog.log_path}")
    if report.enabled and report.file_reports:
        print(f"Report: {report.report_path}")

    return 0 if fail_count == 0 else 1


def main_from_process_file(
    process_file_fn: ProcessFileFn,
    tool_title: str,
    argv: Optional[List[str]] = None,
    *,
    completion_message: Optional[CompletionMessageFn] = None,
) -> int:
    """CLI entry helper: parse args, configure logging, run batch."""
    cfg = parse_arguments(argv)
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )
    cfg = load_config(cfg)
    return run_batch(cfg, process_file_fn, tool_title, completion_message=completion_message)
