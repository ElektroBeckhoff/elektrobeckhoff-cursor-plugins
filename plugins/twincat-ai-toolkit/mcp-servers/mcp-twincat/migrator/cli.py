"""CLI argument parsing and configuration loading."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List, Optional

from .types import MigrationConfig


def parse_arguments(argv: Optional[List[str]] = None) -> MigrationConfig:
    p = argparse.ArgumentParser(
        description=(
            "TwinCAT 3 graphical-to-ST migration tool (FBD/FUP + CFC).\n"
            "\n"
            "Converts .TcPOU files containing FBD/NWL or CFC implementations to\n"
            "functionally identical Structured Text (ST) code. Preserves declarations,\n"
            "comments, attributes, IDs and project structure.\n"
            "\n"
            "SAFETY MODES (no files modified):\n"
            "  --dry-run        Parse, convert, preview result. Zero file writes.\n"
            "  --analyze-only   Parse and inspect structure. No ST generation.\n"
            "\n"
            "OUTPUT MODES (files created/modified):\n"
            "  Default:         Write ST to new *_st_generated file. Original untouched.\n"
            "  --swap:          Backup original, write ST to original path.\n"
            "  --force / -f:    Overwrite original in-place (backup created unless --no-backup).\n"
            "\n"
            "PRIORITY: --dry-run > --analyze-only > --force > --swap > default"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    p.add_argument("--input", required=True,
                   help=("REQUIRED. Absolute or relative path to a single .TcPOU/.TcGVL/.TcDUT "
                         "file or a project folder. When a folder is given, all supported files "
                         "in that folder are processed (combine with --recursive for subfolders). "
                         "GVL and DUT files are loaded but skipped during migration (no implementation)."))

    p.add_argument("--output", default="",
                   help=("Optional. Explicit output path. "
                         "Single file: if a directory, output is <dir>/<stem>_ST<suffix>; "
                         "if a file path, that exact path is used. "
                         "Folder input: the directory structure is mirrored into the given path. "
                         "When set, --swap is ignored and the original file is never modified. "
                         "When empty (default), output location is determined by --swap/--no-swap. "
                         "Default: '' (empty, auto-determined)."))

    p.add_argument("--recursive", action="store_true",
                   help=("Only relevant when --input is a folder. When set, recursively search "
                         "all subfolders for .TcPOU/.TcGVL/.TcDUT files. Without this flag, "
                         "only files in the top-level folder are processed. Default: false."))

    p.add_argument("--backup", action="store_true", default=True,
                   help=("Create a backup copy of the original file before any modification. "
                         "In --force mode: backup is named <stem>_backup_<timestamp><suffix> "
                         "for single files, or mirrored into a <folder>_backup_<timestamp>/ "
                         "directory for folder input. "
                         "Backup is ALWAYS recommended. Default: true."))

    p.add_argument("--no-backup", dest="backup", action="store_false",
                   help=("DANGEROUS. Disable backup creation. If combined with --force, the "
                         "original file is overwritten with NO recovery option. In --strict "
                         "mode, --force without backup is blocked entirely. "
                         "Only use this if you have external version control (e.g. git)."))

    p.add_argument("--force", "-f", action="store_true",
                   help=("DESTRUCTIVE. Overwrite the original .TcPOU file in-place with the "
                         "generated ST version. The original implementation is permanently "
                         "replaced. GUIDs are preserved (not regenerated). A backup is created "
                         "unless --no-backup is set. Takes priority over --swap. "
                         "Use only when you are certain the migration is correct. Default: false."))

    p.add_argument("--swap", action="store_true", default=False,
                   help=("Renames/copies the original file to a backup location, "
                         "then writes the new ST version to the ORIGINAL file path. This ensures "
                         "the TwinCAT project automatically references the new ST file without "
                         "manual re-linking. GUIDs are regenerated (new file identity). "
                         "For single files: backup is <stem>_backup_<timestamp><suffix>. "
                         "For folders: backups go into a <folder>_backup_<timestamp>/ mirror. "
                         "Ignored when --force or --output is set. Default: false."))

    p.add_argument("--no-swap", dest="swap", action="store_false",
                   help=("DEFAULT MODE. Write the generated ST file to a NEW path instead of the "
                         "original. The original file is NEVER touched. "
                         "For single files: output is <stem>_st_generated<suffix>. "
                         "For folders: output goes into <folder>_st_generated_<timestamp>/. "
                         "Safe for testing migration quality before committing changes."))

    p.add_argument("--dry-run", action="store_true",
                   help=("SAFE READ-ONLY. Parses source, generates ST in memory, prints a preview "
                         "of the first 50 lines, and reports statistics. ZERO files are written "
                         "to disk (no output, no backup, no log, no report files). "
                         "Use this to preview migration results before actual execution. "
                         "Takes highest priority -- overrides all other output modes. Default: false."))

    p.add_argument("--analyze-only", action="store_true",
                   help=("SAFE READ-ONLY. Parses the source structure and prints a detailed "
                         "analysis (network/element count, items, box types, actions). "
                         "Does NOT generate any ST code. ZERO files are written to disk. "
                         "Use this to inspect complexity before deciding on migration. "
                         "Default: false."))

    p.add_argument("--log", action="store_true", default=True,
                   help=("Write a detailed migration log file (<prefix>_migration_log_<ts>.txt) "
                         "to the output directory. Contains timestamps, per-file status, warnings, "
                         "errors, and TODO markers. Default: true."))

    p.add_argument("--no-log", dest="log", action="store_false",
                   help="Suppress log file creation. Console output is unaffected. Default: false.")

    p.add_argument("--report", action="store_true", default=True,
                   help=("Write a migration report file (<prefix>_migration_report_<ts>.txt) "
                         "to the output directory. Contains per-file summary, statistics, TODOs, "
                         "warnings, errors, and a post-migration checklist. Default: true."))

    p.add_argument("--no-report", dest="report", action="store_false",
                   help="Suppress report file creation. Default: false.")

    p.add_argument("--config", default="",
                   help=("Optional. Path to a JSON configuration file. Keys in the JSON override "
                         "CLI defaults. Supported keys: backup, force, swap, recursive, dryRun, "
                         "strict, createLog, createReport, preserveComments, preserveIds, "
                         "markUnclearLogicWithTodo, failOnUnclearLogic, encoding, logLevel. "
                         "CLI flags always take final precedence over config file values. "
                         "Default: '' (no config file)."))

    p.add_argument("--encoding", default="utf-8",
                   help=("File encoding for reading input files and writing output files. "
                         "The parser tries this encoding first, then falls back to utf-8-sig, "
                         "utf-8, and latin-1 automatically. Default: 'utf-8'."))

    p.add_argument("--strict", action="store_true",
                   help=("Abort migration for a file if ANY unclear logic (TODO marker) is "
                         "detected. In strict mode, --force without --backup is also blocked. "
                         "Use this for safety-critical projects where incomplete migration must "
                         "not be deployed. Default: false."))

    p.add_argument("--preserve-ids", action="store_true", default=True,
                   help=("Preserve original XML element IDs in the output when using --force. "
                         "When creating new files (--swap or --no-swap), GUIDs are always "
                         "regenerated regardless of this flag. Default: true."))

    p.add_argument("--preserve-comments", action="store_true", default=True,
                   help=("Preserve FBD network comments and titles as ST comment headers in the "
                         "generated code. Each network gets a // ==== header block. Default: true."))

    p.add_argument("--mark-todo", action="store_true", default=True,
                   help=("When a FBD network or element cannot be fully translated to ST, wrap "
                         "the best-effort ST code in a (* TODO [FBD Migration]: ... *) comment "
                         "block with the specific parsing error. Default: true."))

    p.add_argument("--no-mark-todo", dest="mark_todo", action="store_false",
                   help=("Disable TODO marking. Untranslatable networks are silently output as "
                         "best-effort ST without comment wrapping. NOT recommended. Default: false."))

    p.add_argument("--fail-on-unclear", action="store_true", default=True,
                   help=("Log a warning when TODO markers are present after migration. "
                         "Combined with --strict, this causes the migration to abort. "
                         "Without --strict, this only adds warnings to the log. Default: true."))

    p.add_argument("--no-fail-on-unclear", dest="fail_on_unclear", action="store_false",
                   help=("Do not warn about TODO markers. Use only if you plan to review all "
                         "generated ST manually. Default: false."))

    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help=("Console output verbosity. DEBUG shows all internal parsing details. "
                         "INFO shows per-file progress and summaries. WARNING shows only issues. "
                         "ERROR shows only failures. Does not affect log file content (always "
                         "captures INFO level). Default: 'INFO'."))

    args = p.parse_args(argv)
    cfg = MigrationConfig(
        input_path=args.input,
        output_path=args.output,
        recursive=args.recursive,
        backup=args.backup,
        force=args.force,
        swap=args.swap,
        dry_run=args.dry_run,
        analyze_only=args.analyze_only,
        log_enabled=args.log,
        report_enabled=args.report,
        config_file=args.config,
        encoding=args.encoding,
        strict=args.strict,
        preserve_ids=args.preserve_ids,
        preserve_comments=args.preserve_comments,
        mark_todo=args.mark_todo,
        fail_on_unclear=args.fail_on_unclear,
        log_level=args.log_level,
    )
    return cfg


def load_config(cfg: MigrationConfig) -> MigrationConfig:
    if not cfg.config_file:
        return cfg
    p = Path(cfg.config_file)
    if not p.is_file():
        logging.warning("Config file not found: %s", cfg.config_file)
        return cfg
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        mapping = {
            "backup": "backup", "force": "force", "swap": "swap", "recursive": "recursive",
            "dryRun": "dry_run", "strict": "strict", "createLog": "log_enabled",
            "createReport": "report_enabled", "preserveComments": "preserve_comments",
            "preserveIds": "preserve_ids", "markUnclearLogicWithTodo": "mark_todo",
            "failOnUnclearLogic": "fail_on_unclear", "encoding": "encoding",
            "logLevel": "log_level",
        }
        for json_key, attr in mapping.items():
            if json_key in data:
                setattr(cfg, attr, data[json_key])
    except Exception as exc:
        logging.warning("Failed to load config: %s", exc)
    return cfg
