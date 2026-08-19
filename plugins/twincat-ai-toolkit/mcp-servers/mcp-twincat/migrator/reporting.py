"""Migration logging, reporting, and console output helpers."""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import SCRIPT_VERSION
from .io_utils import _resolve_output_path
from .types import AssignNode, BoxNode, MigrationConfig, TcFile
from .validation import calculate_accuracy


class MigrationLogger:
    def __init__(self, enabled: bool, base_path: Path, prefix: str = ""):
        self.enabled = enabled
        self.entries: List[str] = []
        ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
        pfx = f"{prefix}_" if prefix else ""
        self.log_path = base_path / f"{pfx}migration_log_{ts}.txt"

    def log(self, msg: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] {msg}"
        self.entries.append(entry)
        logging.info(msg)

    def save(self):
        if not self.enabled or not self.entries:
            return
        try:
            self.log_path.write_text("\n".join(self.entries), encoding="utf-8")
        except Exception as exc:
            logging.error("Cannot write log: %s", exc)


class MigrationReport:
    def __init__(self, enabled: bool, base_path: Path, prefix: str = ""):
        self.enabled = enabled
        self.file_reports: List[Dict[str, Any]] = []
        ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
        pfx = f"{prefix}_" if prefix else ""
        self.report_path = base_path / f"{pfx}migration_report_{ts}.txt"

    def add(self, tc: TcFile, backup_path: Optional[Path], output_path: Optional[Path],
            replaced: bool):
        acc = calculate_accuracy(tc) if tc.generated_st else None
        entry = {
            "source": str(tc.path),
            "pou_name": tc.pou_name,
            "pou_type": tc.pou_type,
            "impl_type_before": tc.impl_type,
            "impl_type_after": "ST" if tc.generated_st else tc.impl_type,
            "networks": len(tc.networks),
            "st_lines": len(tc.generated_st.splitlines()) if tc.generated_st else 0,
            "backup": str(backup_path) if backup_path else "none",
            "output": str(output_path) if output_path else "none",
            "replaced": replaced,
            "accuracy": acc,
            "todos": tc.todos,
            "warnings": tc.warnings,
            "errors": tc.errors,
            "stats": tc.stats,
        }
        self.file_reports.append(entry)

    def save(self):
        if not self.enabled or not self.file_reports:
            return
        lines = [
            f"TwinCAT Migration Report",
            f"Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Script version: {SCRIPT_VERSION}",
            f"Files processed: {len(self.file_reports)}",
            "=" * 70,
            "",
        ]
        converted = [r for r in self.file_reports if r["accuracy"] is not None]
        skipped = [r for r in self.file_reports if r["accuracy"] is None]
        failed = [r for r in converted if r["errors"]]
        success = [r for r in converted if not r["errors"]]

        acc_values = [r["accuracy"] for r in converted if r["accuracy"] is not None]
        overall_acc = round(sum(acc_values) / len(acc_values), 2) if acc_values else 100.0

        lines.append(f"Converted:       {len(converted)}")
        lines.append(f"Skipped:         {len(skipped)}")
        lines.append(f"Success:         {len(success)}")
        lines.append(f"Failed:          {len(failed)}")
        lines.append(f"Overall Accuracy: {overall_acc:.2f} %")
        lines.append("=" * 70)
        lines.append("")

        for r in self.file_reports:
            lines.append(f"File: {r['source']}")
            lines.append(f"  POU: {r['pou_name']} ({r['pou_type']})")
            lines.append(f"  Language before: {r['impl_type_before']}")
            lines.append(f"  Language after:  {r['impl_type_after']}")
            lines.append(f"  Networks: {r['networks']}")
            lines.append(f"  ST lines: {r['st_lines']}")
            if r["accuracy"] is not None:
                lines.append(f"  Accuracy: {r['accuracy']:.2f} %")
            lines.append(f"  Backup: {r['backup']}")
            lines.append(f"  Output: {r['output']}")
            lines.append(f"  Replaced: {r['replaced']}")
            if r["stats"]:
                lines.append(f"  Stats: {r['stats']}")
            if r["todos"]:
                lines.append(f"  TODOs ({len(r['todos'])}):")
                for t in r["todos"][:20]:
                    lines.append(f"    - {t}")
            if r["warnings"]:
                lines.append(f"  Warnings ({len(r['warnings'])}):")
                for w in r["warnings"]:
                    lines.append(f"    - {w}")
            if r["errors"]:
                lines.append(f"  ERRORS ({len(r['errors'])}):")
                for e in r["errors"]:
                    lines.append(f"    ! {e}")
            lines.append("-" * 70)
            lines.append("")

        lines.extend(_final_checklist())

        try:
            self.report_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:
            logging.error("Cannot write report: %s", exc)


def _final_checklist() -> List[str]:
    return [
        "",
        "=" * 70,
        "POST-MIGRATION CHECKLIST",
        "=" * 70,
        " 1. Open project in TwinCAT 3 XAE",
        " 2. Build / CheckAllObjects",
        " 3. Check compiler errors",
        " 4. Check compiler warnings",
        " 5. Verify task assignment",
        " 6. Verify I/O mapping",
        " 7. Verify visualizations / HMI",
        " 8. Verify ADS / OPC-UA access",
        " 9. Verify retain / persistent data",
        "10. Check online-change behavior",
        "11. Compare runtime behavior with old version",
        "12. Check timer / counter behavior",
        "13. Check safety logic",
        "14. Check limit values",
        "15. Perform commissioning test",
        "16. Verify backup is restorable",
        "",
    ]


def _print_analysis(tc: TcFile):
    print(f"\n{'=' * 60}")
    print(f"ANALYSIS: {tc.path.name}")
    print(f"{'=' * 60}")
    print(f"  POU Name:       {tc.pou_name}")
    print(f"  POU Type:       {tc.pou_type}")
    print(f"  Implementation: {tc.impl_type}")
    print(f"  Networks:       {len(tc.networks)}")
    for nw in tc.networks:
        status = " [OutCommented]" if nw.out_commented else ""
        print(f"    Network {nw.index + 1}: {len(nw.items)} items{status}")
        for item in nw.items:
            if isinstance(item, BoxNode):
                print(f"      BoxTreeBox: {item.box_type} (call={item.call_type})")
            elif isinstance(item, AssignNode):
                targets = [o.name for o in item.outputs if not o.is_empty]
                print(f"      Assign -> {', '.join(targets)}")
    if tc.actions:
        print(f"  Actions: {len(tc.actions)}")
        for a in tc.actions:
            print(f"    {a.name}: {a.impl_type}, {len(a.networks)} networks")
    print()


def _print_dry_run(tc: TcFile, cfg: MigrationConfig):
    print(f"\n{'=' * 60}")
    print(f"DRY-RUN: {tc.path.name}")
    print(f"{'=' * 60}")
    print(f"  File type:    {tc.file_type}")
    print(f"  POU:          {tc.pou_name} ({tc.pou_type})")
    print(f"  Impl before:  {tc.impl_type}")
    print(f"  Impl after:   ST")
    print(f"  Networks:     {len(tc.networks)}")
    print(f"  ST lines:     {len(tc.generated_st.splitlines())}")
    acc = calculate_accuracy(tc)
    print(f"  Accuracy:     {acc:.2f} %")
    print(f"  TODOs:        {len(tc.todos)}")
    print(f"  Warnings:     {len(tc.warnings)}")
    print(f"  Errors:       {len(tc.errors)}")
    use_swap = cfg.swap and not cfg.force and not cfg.output_path
    if cfg.force:
        if cfg.backup:
            ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
            print(f"  Would backup: {tc.path.stem}_backup_{ts}{tc.path.suffix}")
        print(f"  Would force-overwrite: {tc.path}")
    elif use_swap:
        if cfg.batch_dir:
            print(f"  Would backup:  -> {cfg.batch_dir}/<relative path>")
        else:
            ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
            print(f"  Would backup:  {tc.path.stem}_backup_{ts}{tc.path.suffix}")
        print(f"  Would create:  {tc.path} (ST at original path)")
    else:
        if cfg.batch_dir:
            print(f"  Would create:  {cfg.batch_dir}/<relative path>")
        else:
            out = _resolve_output_path(tc.path, cfg)
            print(f"  Would create: {out}")
    if tc.todos:
        print(f"  TODO locations:")
        for t in tc.todos[:10]:
            print(f"    {t}")
    print()
    print("--- Generated ST preview (first 50 lines) ---")
    for line in tc.generated_st.splitlines()[:50]:
        print(f"  {line}")
    print("--- end preview ---\n")
