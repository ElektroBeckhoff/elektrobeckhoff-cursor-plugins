#!/usr/bin/env python3
"""
Shared base module for TwinCAT 3 graphical-to-ST migration tools.

Contains format-agnostic components used by both the FBD/NWL and CFC
migrators: IR dataclasses, ST code generation, constants, XML helpers,
validation, file I/O, backup, logging, reporting, and CLI argument parsing.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import traceback
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

SCRIPT_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class OperandNode:
    name: str = ""
    type_str: str = ""
    is_lvalue: bool = False
    is_instance: bool = False
    flags: int = 0
    xml_id: str = ""
    comment: str = ""
    is_null: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.name or self.name == '""' or self.name == ""


@dataclass
class BoxNode:
    box_type: str = ""
    call_type: str = ""
    instance: Optional[OperandNode] = None
    input_items: List[Union[BoxNode, OperandNode]] = field(default_factory=list)
    output_items: List[OperandNode] = field(default_factory=list)
    input_param_names: List[str] = field(default_factory=list)
    input_param_types: List[str] = field(default_factory=list)
    output_param_names: List[str] = field(default_factory=list)
    output_param_types: List[str] = field(default_factory=list)
    input_flags: List[int] = field(default_factory=list)
    en: bool = False
    eno: bool = False
    st_snippet: List[str] = field(default_factory=list)
    xml_id: str = ""


@dataclass
class DemuxNode:
    input: Optional[OperandNode] = None
    xml_id: str = ""


@dataclass
class AssignNode:
    outputs: List[OperandNode] = field(default_factory=list)
    rvalue: Optional[Union[BoxNode, OperandNode, "AssignNode", DemuxNode]] = None
    flags: int = 0
    xml_id: str = ""


@dataclass
class NwlNetwork:
    index: int = 0
    comment: str = ""
    title: str = ""
    label: str = ""
    out_commented: bool = False
    items: List[Union[BoxNode, AssignNode, DemuxNode]] = field(default_factory=list)
    xml_id: str = ""


@dataclass
class ActionInfo:
    name: str = ""
    impl_type: str = ""
    networks: List[NwlNetwork] = field(default_factory=list)
    st_code: str = ""
    xml_element: Any = None


@dataclass
class StNetwork:
    index: int = 0
    comment_header: str = ""
    lines: List[str] = field(default_factory=list)
    todos: List[str] = field(default_factory=list)
    out_commented: bool = False


@dataclass
class TcFile:
    path: Path = field(default_factory=Path)
    file_type: str = ""
    encoding: str = "utf-8"
    xml_tree: Any = None
    xml_root: Any = None
    pou_name: str = ""
    pou_type: str = ""
    pou_id: str = ""
    special_func: str = ""
    declaration: str = ""
    impl_type: str = ""
    networks: List[NwlNetwork] = field(default_factory=list)
    actions: List[ActionInfo] = field(default_factory=list)
    generated_st: str = ""
    st_networks: List[StNetwork] = field(default_factory=list)
    todos: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    edge_vars: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class MigrationConfig:
    input_path: str = ""
    output_path: str = ""
    recursive: bool = False
    backup: bool = True
    force: bool = False
    swap: bool = False
    batch_dir: Optional[str] = None
    backup_dir: Optional[str] = None
    dry_run: bool = False
    analyze_only: bool = False
    log_enabled: bool = True
    report_enabled: bool = True
    config_file: str = ""
    encoding: str = "utf-8"
    strict: bool = False
    preserve_ids: bool = True
    preserve_comments: bool = True
    mark_todo: bool = True
    fail_on_unclear: bool = True
    log_level: str = "INFO"


# ---------------------------------------------------------------------------
# Generated header
# ---------------------------------------------------------------------------

def calculate_accuracy(tc: 'TcFile') -> float:
    """Calculate migration accuracy as percentage with two decimals (0.00-100.00).

    Based on the ratio of problem items to total items (networks or
    ST-networks).  Each TODO counts as 1 failed item, each warning
    as 0.5.  Files with zero items default to 100 when clean,
    0 when issues exist.
    """
    total = max(len(tc.networks), len(tc.st_networks), 1)
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
        Name of the migration tool, e.g. ``"twincat_fbd_to_st_migrator"``
        or ``"twincat_cfc_to_st_migrator"``.
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

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
            "  Default:         Write ST to new *_ST_Generated file. Original untouched.\n"
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
                         "For single files: output is <stem>_ST_Generated<suffix>. "
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


# ---------------------------------------------------------------------------
# File collection
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS = {".tcpou", ".tcgvl", ".tcdut"}


def collect_input_files(cfg: MigrationConfig) -> List[Path]:
    p = Path(cfg.input_path)
    if p.is_file():
        if p.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [p]
        logging.warning("Unsupported file type: %s", p.suffix)
        return []
    if p.is_dir():
        results = []
        pattern = "**/*" if cfg.recursive else "*"
        for ext in SUPPORTED_EXTENSIONS:
            results.extend(p.glob(f"{pattern}{ext}"))
            results.extend(p.glob(f"{pattern}{ext.upper()}"))
        seen = set()
        unique = []
        for f in sorted(results):
            key = str(f).lower()
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique
    logging.error("Input path does not exist: %s", p)
    return []


# ---------------------------------------------------------------------------
# XML parser
# ---------------------------------------------------------------------------

def load_file(path: Path, encoding: str = "utf-8") -> Optional[TcFile]:
    tc = TcFile(path=path, encoding=encoding)
    tc.file_type = path.suffix.lower()

    for enc in [encoding, "utf-8-sig", "utf-8", "latin-1"]:
        try:
            raw = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        tc.errors.append(f"Cannot decode file with any known encoding: {path}")
        return tc

    try:
        tc.xml_tree = ET.ElementTree(ET.fromstring(raw))
        tc.xml_root = tc.xml_tree.getroot()
    except ET.ParseError as exc:
        tc.errors.append(f"XML parse error: {exc}")
        return tc

    pou = tc.xml_root.find("POU")
    if pou is None:
        pou = tc.xml_root.find("GVL")
    if pou is None:
        pou = tc.xml_root.find("DUT")
    if pou is None:
        for child in tc.xml_root:
            pou = child
            break

    if pou is not None:
        tc.pou_name = pou.get("Name", "")
        tc.pou_id = pou.get("Id", "")
        tc.special_func = pou.get("SpecialFunc", "")

        decl = pou.find("Declaration")
        if decl is not None and decl.text:
            tc.declaration = decl.text.strip()
            tc.pou_type = _detect_pou_type(tc.declaration)

        impl = pou.find("Implementation")
        if impl is not None:
            tc.impl_type = _detect_impl_type(impl)

        for action_el in pou.findall("Action"):
            ai = ActionInfo(name=action_el.get("Name", ""), xml_element=action_el)
            action_impl = action_el.find("Implementation")
            if action_impl is not None:
                ai.impl_type = _detect_impl_type(action_impl)
            tc.actions.append(ai)

    return tc


def _detect_pou_type(declaration: str) -> str:
    first_line = declaration.strip().split("\n")[0].strip().upper() if declaration else ""
    for kw in ["PROGRAM", "FUNCTION_BLOCK", "FUNCTION", "METHOD", "ACTION", "PROPERTY",
               "INTERFACE", "STRUCT", "ENUM", "TYPE"]:
        if first_line.startswith(kw):
            return kw
    return "UNKNOWN"


def _detect_impl_type(impl_element) -> str:
    for tag in ["ST", "NWL", "CFC", "SFC", "IL", "LD"]:
        if impl_element.find(tag) is not None:
            return tag
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _get_v_str(element, name: str) -> str:
    for child in element:
        if child.tag == "v" and child.get("n") == name:
            raw = (child.text or "").strip()
            return _strip_quotes(raw)
    return ""


def _find_v(element, name: str):
    for child in element:
        if child.tag == "v" and child.get("n") == name:
            return child
    return None


def _find_child_by_name(element, name: str):
    for child in element:
        if child.get("n") == name:
            return child
    return None


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


# ---------------------------------------------------------------------------
# ST code generator
# ---------------------------------------------------------------------------

INFIX_OPERATORS = {"And": "AND", "Or": "OR", "Xor": "XOR"}
COMPARISON_OPS = {"EQ": "=", "NE": "<>", "GT": ">", "LT": "<", "GE": ">=", "LE": "<="}
ARITHMETIC_OPS = {"ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "MOD"}
CONVERSION_FUNCS = {
    "INT_TO_REAL", "REAL_TO_INT", "BOOL_TO_INT", "INT_TO_BOOL",
    "DINT_TO_REAL", "REAL_TO_DINT", "LREAL_TO_REAL", "REAL_TO_LREAL",
    "INT_TO_DINT", "DINT_TO_INT", "TO_INT", "TO_REAL", "TO_BOOL",
    "TO_DINT", "TO_LREAL", "TO_STRING", "TO_WORD", "TO_DWORD",
    "BYTE_TO_INT", "INT_TO_BYTE", "WORD_TO_INT", "INT_TO_WORD",
}
IEC_FUNCTIONS = {
    "MUX", "LIMIT", "MAX", "MIN",
    "SHL", "SHR", "ROL", "ROR",
    "ABS", "SQRT", "LN", "LOG", "EXP", "EXPT",
    "SIN", "COS", "TAN", "ASIN", "ACOS", "ATAN",
    "TRUNC", "SIZEOF", "ADR", "BITADR", "INDEXOF",
}
FB_CALL_TYPES = {"FunctionBlock", "Function", "Program", "Method"}


def _clean_bool_expr(expr: str) -> str:
    """Remove redundant OR FALSE / AND TRUE from boolean expressions."""
    expr = re.sub(r'\s+OR\s+FALSE\b', '', expr)
    expr = re.sub(r'\bFALSE\s+OR\s+', '', expr)
    expr = re.sub(r'\s+AND\s+TRUE\b', '', expr)
    expr = re.sub(r'\bTRUE\s+AND\s+', '', expr)
    return expr.strip()


def _apply_input_flag(expr: str, flag: int, box: BoxNode, input_idx: int,
                      tc: TcFile, hoisted: List[str]) -> str:
    if not expr:
        return expr
    logic_flag = flag & 0x07
    if logic_flag == 0:
        return expr
    if logic_flag & 1:
        if " " in expr and not expr.startswith("("):
            return f"NOT ({expr})"
        return f"NOT {expr}"
    if logic_flag in (2, 4):
        edge_type = "R_TRIG" if logic_flag == 2 else "F_TRIG"
        suffix = "PosEdge" if logic_flag == 2 else "NegEdge"
        inst = box.instance.name if box.instance else f"Box{box.xml_id or input_idx}"
        clean = re.sub(r'[\[\].\s]', '_', inst)
        pname = (box.input_param_names[input_idx]
                 if input_idx < len(box.input_param_names) else f"In{input_idx}")
        edge_name = f"fb_{clean}_{pname}_{suffix}"
        hoisted.append(f"{edge_name}(CLK := {expr});")
        if (edge_name, edge_type) not in tc.edge_vars:
            tc.edge_vars.append((edge_name, edge_type))
        return f"{edge_name}.Q"
    return expr


def _build_demux_merge_map(networks: List[NwlNetwork]) -> Tuple[
        Dict[str, List[Tuple[str, str]]], set]:
    """Pre-scan networks for Demux patterns that can be merged into FB calls.

    Returns:
        merge_map: {instance_name: [(param_name, target_var), ...]}
        skip_networks: set of network indices that are fully merged
    """
    merge_map: Dict[str, List[Tuple[str, str]]] = {}
    skip_networks: set = set()

    for nw in networks:
        demux_source: Optional[OperandNode] = None
        has_demux = False
        for item in nw.items:
            if isinstance(item, DemuxNode):
                has_demux = True
                if item.input and not item.input.is_empty:
                    demux_source = item.input

        if not has_demux or not demux_source:
            continue

        src = demux_source.name
        dot_pos = src.rfind(".")
        if dot_pos <= 0:
            continue

        inst_name = src[:dot_pos]
        param_name = src[dot_pos + 1:]

        targets: List[Tuple[str, str]] = []
        all_resolved = True
        for item in nw.items:
            if isinstance(item, DemuxNode):
                continue
            if isinstance(item, AssignNode):
                if isinstance(item.rvalue, DemuxNode):
                    for o in item.outputs:
                        if not o.is_empty:
                            targets.append((o.name, o.type_str))
                else:
                    all_resolved = False
            else:
                all_resolved = False

        if targets:
            if inst_name not in merge_map:
                merge_map[inst_name] = []
            for t_name, t_type in targets:
                merge_map[inst_name].append((param_name, t_name, t_type))
            if all_resolved:
                skip_networks.add(nw.index)

    return merge_map, skip_networks


def convert_networks_to_st(tc: TcFile, cfg: MigrationConfig) -> None:
    tc.st_networks = []
    tc.todos = []
    tc.edge_vars = []
    all_lines: List[str] = []

    demux_merge_map, demux_skip = _build_demux_merge_map(tc.networks)

    for nw in tc.networks:
        if nw.index in demux_skip:
            continue

        stn = StNetwork(index=nw.index, out_commented=nw.out_commented)

        header_parts = []
        if nw.title:
            header_parts.append(f"Title: {nw.title}")
        if nw.comment:
            header_parts.append(nw.comment)

        nw_label = f"Network {nw.index + 1}"
        comment_text = ": ".join(header_parts) if header_parts else ""
        oc_suffix = " [OutCommented]" if nw.out_commented else ""
        if comment_text:
            stn.comment_header = f"(* FBD {nw_label}: {comment_text}{oc_suffix} *)"
        else:
            stn.comment_header = f"(* FBD {nw_label}{oc_suffix} *)"

        if nw.out_commented:
            commented_lines = _generate_network_code(nw, tc, cfg, demux_merge_map)
            wrapped = ["(* OutCommented network:"]
            for line in commented_lines:
                wrapped.append(f"   {line}")
            wrapped.append("*)")
            stn.lines = wrapped
        else:
            todos_before = len(tc.todos)
            generated = _generate_network_code(nw, tc, cfg, demux_merge_map)
            new_todos = tc.todos[todos_before:]
            if new_todos and cfg.mark_todo:
                reasons = []
                for t in new_todos:
                    clean = t.replace("// TODO [FBD Migration]: ", "").replace("// TODO: ", "")
                    reasons.append(clean)
                reason_str = "; ".join(reasons)
                wrapped = [f"(* TODO [FBD Migration]: Network {nw.index + 1} - migration incomplete"]
                wrapped.append(f"   Reason: {reason_str}")
                wrapped.append(f"   Best-effort ST:")
                for line in generated:
                    wrapped.append(f"   {line}")
                wrapped.append("*)")
                stn.lines = wrapped
            else:
                stn.lines = generated

        stn.todos = [t for t in tc.todos if t not in [x for s in tc.st_networks for x in s.todos]]
        tc.st_networks.append(stn)

    for stn in tc.st_networks:
        if stn.comment_header:
            all_lines.append(stn.comment_header)
        all_lines.extend(stn.lines)
        all_lines.append("")

    tc.generated_st = "\n".join(all_lines).rstrip() + "\n"

    for action in tc.actions:
        if action.networks:
            action_merge_map, action_skip = _build_demux_merge_map(action.networks)
            action_lines: List[str] = []
            for nw in action.networks:
                if nw.index in action_skip:
                    continue
                todos_before = len(tc.todos)
                code = _generate_network_code(nw, tc, cfg, action_merge_map)
                new_todos = tc.todos[todos_before:]
                if new_todos and cfg.mark_todo:
                    reasons = []
                    for t in new_todos:
                        clean = t.replace("// TODO [FBD Migration]: ", "").replace("// TODO: ", "")
                        reasons.append(clean)
                    reason_str = "; ".join(reasons)
                    action_lines.append(f"(* TODO [FBD Migration]: Action '{action.name}' Network {nw.index + 1} - migration incomplete")
                    action_lines.append(f"   Reason: {reason_str}")
                    action_lines.append(f"   Best-effort ST:")
                    for line in code:
                        action_lines.append(f"   {line}")
                    action_lines.append("*)")
                else:
                    action_lines.extend(code)
                action_lines.append("")
            action.st_code = "\n".join(action_lines).rstrip() + "\n"


def _generate_network_code(nw: NwlNetwork, tc: TcFile, cfg: MigrationConfig,
                           demux_merge_map: Optional[Dict[str, List[Tuple[str, str]]]] = None) -> List[str]:
    lines: List[str] = []

    demux_source: Optional[OperandNode] = None
    for item in nw.items:
        if isinstance(item, DemuxNode) and item.input and not item.input.is_empty:
            demux_source = item.input

    for item in nw.items:
        if isinstance(item, DemuxNode):
            continue
        if isinstance(item, AssignNode):
            if (isinstance(item.rvalue, DemuxNode)
                    and (item.rvalue.input is None or item.rvalue.input.is_empty)):
                if demux_source:
                    item.rvalue = OperandNode(
                        name=demux_source.name,
                        type_str=demux_source.type_str,
                        xml_id=demux_source.xml_id,
                    )
                else:
                    targets = [o.name for o in item.outputs if not o.is_empty]
                    todo = (f"// TODO [FBD Migration]: BoxTreeDemux RValue for "
                            f"'{', '.join(targets)}' - no demux source found in network")
                    lines.append(todo)
                    tc.todos.append(todo)
                    continue
            lines.extend(_gen_assign(item, tc, cfg, demux_merge_map))
        elif isinstance(item, BoxNode):
            lines.extend(_gen_top_level_box(item, tc, cfg, demux_merge_map))
    return lines


def _is_return_assign(assign: AssignNode) -> bool:
    """BoxTreeAssign with output '???' and Flags=8 is a FBD RETURN element."""
    return (assign.outputs
            and all(o.name == "???" and o.flags == 8 for o in assign.outputs))


def _gen_assign(assign: AssignNode, tc: TcFile, cfg: MigrationConfig,
                demux_merge_map: Optional[Dict[str, List[Tuple[str, str]]]] = None) -> List[str]:
    lines: List[str] = []
    if assign.rvalue is None:
        return lines

    if _is_return_assign(assign):
        hoisted: List[str] = []
        cond = _gen_expression(assign.rvalue, tc, cfg, hoisted)
        cond = _clean_bool_expr(cond)
        lines.extend(hoisted)
        if cond and cond.upper() not in ("TRUE", "1"):
            lines.append(f"IF {cond} THEN")
            lines.append("    RETURN;")
            lines.append("END_IF")
        else:
            lines.append("RETURN;")
        return lines

    if isinstance(assign.rvalue, DemuxNode):
        if assign.rvalue.input and not assign.rvalue.input.is_empty:
            targets = [o for o in assign.outputs if not o.is_empty]
            for target in targets:
                lines.append(f"{target.name} := {assign.rvalue.input.name};")
        else:
            targets = [o.name for o in assign.outputs if not o.is_empty]
            todo = (f"// TODO [FBD Migration]: Unresolved BoxTreeDemux for "
                    f"'{', '.join(targets)}' - empty demux input")
            lines.append(todo)
            tc.todos.append(todo)
        return lines

    if isinstance(assign.rvalue, AssignNode):
        inner_lines = _gen_assign(assign.rvalue, tc, cfg, demux_merge_map)
        lines.extend(inner_lines)
        inner_targets = [o for o in assign.rvalue.outputs if not o.is_empty]
        outer_targets = [o for o in assign.outputs if not o.is_empty]
        if inner_targets and outer_targets:
            for ot in outer_targets:
                lines.append(f"{ot.name} := {inner_targets[0].name};")
        elif outer_targets:
            for ot in outer_targets:
                todo = (f"// TODO [FBD Migration]: Chained assignment for '{ot.name}' "
                        f"- inner assign has no resolvable output")
                lines.append(todo)
                tc.todos.append(todo)
        return lines

    if isinstance(assign.rvalue, BoxNode) and assign.rvalue.call_type in FB_CALL_TYPES:
        hoisted: List[str] = []
        box = assign.rvalue
        assign_targets = [o for o in assign.outputs if not o.is_empty]
        fb_out_names = box.output_param_names
        fb_out_types = box.output_param_types
        null_idx = next((i for i, o in enumerate(box.output_items) if o.is_null), 0)
        assign_out_param = fb_out_names[null_idx] if null_idx < len(fb_out_names) else (
            fb_out_names[0] if fb_out_names else "")
        negated = bool(assign.flags & 1)

        inst_name = (box.box_type if box.call_type in ("Function", "Program", "Method")
                     else (box.instance.name if box.instance else ""))

        param_targets: Dict[str, List[Tuple[str, str, bool]]] = {}

        for i, out_op in enumerate(box.output_items):
            if not out_op.is_empty and i < len(fb_out_names) and fb_out_names[i]:
                param_targets.setdefault(fb_out_names[i], []).append(
                    (out_op.name, out_op.type_str, False))

        if assign_out_param:
            for out_op in assign_targets:
                param_targets.setdefault(assign_out_param, []).append(
                    (out_op.name, out_op.type_str, negated))

        if demux_merge_map and inst_name in demux_merge_map:
            for entry in demux_merge_map[inst_name]:
                pname = entry[0]
                target = entry[1]
                t_type = entry[2] if len(entry) == 3 else ""
                param_targets.setdefault(pname, []).append((target, t_type, False))

        inline_outs: List[Tuple[str, str, str]] = []
        post_call_lines: List[str] = []

        for pname, targets in param_targets.items():
            p_idx = next((j for j, n in enumerate(fb_out_names) if n == pname), -1)
            p_type = fb_out_types[p_idx] if 0 <= p_idx < len(fb_out_types) else ""

            if len(targets) == 1 and not targets[0][2]:
                target, t_type, _ = targets[0]
                if p_type and t_type and _check_type_mismatch(p_type, t_type):
                    inline_outs.append((pname,
                        f"{target} (* TYPE MISMATCH: {p_type} -> {t_type} *)", ""))
                else:
                    inline_outs.append((pname, target, t_type))
            else:
                for target, t_type, is_neg in targets:
                    neg_prefix = "NOT " if is_neg else ""
                    if p_type and t_type and _check_type_mismatch(p_type, t_type):
                        post_call_lines.append(
                            f"{target} := {neg_prefix}{inst_name}.{pname}; "
                            f"(* TYPE MISMATCH: {p_type} -> {t_type} *)")
                    else:
                        post_call_lines.append(
                            f"{target} := {neg_prefix}{inst_name}.{pname};")

        fb_lines = _gen_fb_call(box, tc, cfg, hoisted, inline_outs,
                                skip_output_items=True)
        lines.extend(hoisted)
        lines.extend(fb_lines)
        if post_call_lines:
            lines.append("")
            lines.append(f"(* {inst_name} output mappings *)")
            lines.extend(_align_assignments(post_call_lines))
        return lines

    hoisted: List[str] = []
    rvalue_expr = _gen_expression(assign.rvalue, tc, cfg, hoisted)
    rvalue_expr = _clean_bool_expr(rvalue_expr)
    if assign.flags & 1 and rvalue_expr:
        if " " in rvalue_expr and not rvalue_expr.startswith("("):
            rvalue_expr = f"NOT ({rvalue_expr})"
        else:
            rvalue_expr = f"NOT {rvalue_expr}"
    lines.extend(hoisted)
    targets = [o for o in assign.outputs if not o.is_empty]
    if not rvalue_expr or rvalue_expr.strip() == "":
        for target in targets:
            todo = (f"// TODO [FBD Migration]: Empty RValue for '{target.name}'"
                    f" - verify assignment source in original FBD")
            lines.append(todo)
            tc.todos.append(todo)
    else:
        for target in targets:
            prefix = f"{target.name} := "
            wrapped = _wrap_bool_chain(rvalue_expr, prefix)
            if wrapped != prefix + rvalue_expr:
                lines.append(f"{wrapped};")
            else:
                lines.append(f"{prefix}{rvalue_expr};")
        if len(targets) > 1:
            lines[-len(targets):] = _align_assignments(lines[-len(targets):])
    return lines


def _gen_top_level_box(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                       demux_merge_map: Optional[Dict[str, List[Tuple[str, str]]]] = None) -> List[str]:
    if box.call_type in FB_CALL_TYPES:
        hoisted: List[str] = []
        extra_outs: Optional[List[Tuple[str, str]]] = None
        inst_name = box.box_type if box.call_type in ("Function", "Program", "Method") else (box.instance.name if box.instance else "")
        if demux_merge_map and inst_name in demux_merge_map:
            extra_outs = list(demux_merge_map[inst_name])
        lines = _gen_fb_call(box, tc, cfg, hoisted, extra_outs)
        result = list(hoisted) + lines
        return result

    if box.call_type == "Action":
        return [f"{box.box_type}();"]

    if box.box_type == "EXECUTE" and box.st_snippet:
        hoisted: List[str] = []
        en_expr = ""
        if box.input_items:
            en_expr = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            en_expr = _clean_bool_expr(en_expr)
        lines = list(hoisted)
        if en_expr and en_expr.upper() not in ("TRUE", "1"):
            lines.append(f"IF {en_expr} THEN")
            for s in box.st_snippet:
                lines.append(f"    {s}")
            lines.append("END_IF")
        else:
            lines.extend(box.st_snippet)
        return lines

    if box.box_type == "RET" or box.box_type == "RETURN":
        return ["RETURN;"]

    if box.box_type == "JMP":
        label = ""
        if box.output_items:
            for o in box.output_items:
                if not o.is_empty:
                    label = o.name
                    break
        if label:
            todo = f"// TODO [FBD Migration]: JMP {label} - convert jump to IF/ELSE structure"
            tc.todos.append(todo)
            return [todo]
        todo = "// TODO [FBD Migration]: JMP - no label found"
        tc.todos.append(todo)
        return [todo]

    if not box.input_items and box.call_type in ("", "None") and not box.instance:
        return [f"{box.box_type}();"]

    hoisted: List[str] = []
    expr = _gen_expression(box, tc, cfg, hoisted)
    expr = _clean_bool_expr(expr)
    result = list(hoisted)
    outputs = [o for o in box.output_items if not o.is_empty]
    if outputs:
        raw = [f"{o.name} := {expr};" for o in outputs]
        if len(raw) > 1:
            result.extend(_align_assignments(raw))
        else:
            result.extend(raw)
    elif expr:
        result.append(f"{expr};")
    return result


def _align_assignments(lines: List[str]) -> List[str]:
    """Align := operators across multiple assignment lines."""
    parsed: List[Tuple[str, str]] = []
    for line in lines:
        idx = line.find(":=")
        if idx > 0:
            parsed.append((line[:idx].rstrip(), line[idx:]))
        else:
            parsed.append((line, ""))
    if not parsed or all(r == "" for _, r in parsed):
        return lines
    max_lhs = max(len(lhs) for lhs, rhs in parsed if rhs)
    result = []
    for lhs, rhs in parsed:
        if rhs:
            result.append(f"{lhs.ljust(max_lhs)} {rhs}")
        else:
            result.append(lhs)
    return result


def _check_type_mismatch(param_type: str, target_type: str) -> bool:
    if not param_type or not target_type:
        return False
    return param_type.upper().strip() != target_type.upper().strip()


_BOOL_OPS_RE = re.compile(r'\s+(OR|AND|XOR)\s+')


def _format_call_params(mappings: List[Tuple[str, str, str]], indent: str = "    ") -> List[str]:
    """Align := and => operators in parameter lists.

    Each mapping is (param_name, operator, value).
    Returns formatted lines WITHOUT trailing comma/semicolon.
    Long boolean chains (OR / AND / XOR with 3+ operands) are broken
    across multiple lines, each operator aligned below the first operand.
    """
    if not mappings:
        return []
    named = [(n, op, v) for n, op, v in mappings if n]
    positional = [(n, op, v) for n, op, v in mappings if not n]
    if not named:
        return [f"{indent}{v}" for _, _, v in positional]
    max_name = max(len(n) for n, _, _ in named)
    lines = []
    for n, op, v in positional:
        lines.append(f"{indent}{v}")
    for n, op, v in named:
        prefix = f"{indent}{n.ljust(max_name)} {op} "
        formatted = _wrap_bool_chain(v, prefix)
        lines.append(formatted)
    return lines


def _split_top_level(expr: str, op: str) -> List[str]:
    """Split *expr* by *op* only at parenthesis depth 0."""
    parts: List[str] = []
    depth = 0
    current: List[str] = []
    tokens = expr.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == op and depth == 0 and current:
            parts.append(" ".join(current))
            current = []
        else:
            depth += tok.count("(") - tok.count(")")
            current.append(tok)
        i += 1
    if current:
        parts.append(" ".join(current))
    return parts


def _wrap_bool_chain(expr: str, prefix: str) -> str:
    """Break long boolean chains across lines with aligned operators.

    Only wraps when the expression contains 3+ operands joined by the
    same boolean operator (OR / AND / XOR) at parenthesis depth 0.
    """
    for op in ("OR", "AND", "XOR"):
        parts = _split_top_level(expr, op)
        if len(parts) >= 3:
            continuation_indent = " " * len(prefix)
            joined = [f"{parts[0]} {op}"]
            for i, p in enumerate(parts[1:], 1):
                if i < len(parts) - 1:
                    joined.append(f"{continuation_indent}{p} {op}")
                else:
                    joined.append(f"{continuation_indent}{p}")
            return prefix + ("\n".join(joined))
    return prefix + expr


def _gen_fb_call(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                 hoisted: List[str],
                 extra_outputs: Optional[List[Tuple[str, str]]] = None,
                 skip_output_items: bool = False) -> List[str]:
    if box.call_type in ("Function", "Program", "Method"):
        inst_name = box.box_type
    elif box.instance and box.instance.name:
        inst_name = box.instance.name
    else:
        todo = f"// TODO: FB call without instance for {box.box_type}"
        tc.todos.append(todo)
        return [todo]
    param_names = box.input_param_names
    input_items = box.input_items

    mappings: List[Tuple[str, str, str]] = []
    for i, inp in enumerate(input_items):
        pname = param_names[i] if i < len(param_names) and param_names[i] else ""

        expr = _gen_expression(inp, tc, cfg, hoisted)
        expr = _clean_bool_expr(expr)
        flag = box.input_flags[i] if i < len(box.input_flags) else 0
        expr = _apply_input_flag(expr, flag, box, i, tc, hoisted)
        if not expr:
            continue
        if _is_default_skip(expr, pname, inp):
            continue
        mappings.append((pname, ":=", expr))

    out_names = box.output_param_names
    out_types = box.output_param_types
    if not skip_output_items:
        out_items = box.output_items
        for i, out_op in enumerate(out_items):
            if not out_op.is_empty and i < len(out_names) and out_names[i]:
                p_type = out_types[i] if i < len(out_types) else ""
                t_type = out_op.type_str
                if _check_type_mismatch(p_type, t_type):
                    mappings.append((out_names[i], "=>",
                                     f"{out_op.name} (* TYPE MISMATCH: {p_type} -> {t_type} *)"))
                else:
                    mappings.append((out_names[i], "=>", out_op.name))

    if extra_outputs:
        for extra in extra_outputs:
            if len(extra) == 3:
                pname, target, t_type = extra
            else:
                pname, target = extra[0], extra[1]
                t_type = ""
            p_idx = next((j for j, n in enumerate(out_names) if n == pname), -1)
            p_type = out_types[p_idx] if 0 <= p_idx < len(out_types) else ""
            if p_type and t_type and _check_type_mismatch(p_type, t_type):
                mappings.append((pname, "=>",
                                 f"{target} (* TYPE MISMATCH: {p_type} -> {t_type} *)"))
            else:
                mappings.append((pname, "=>", target))

    if not mappings:
        return [f"{inst_name}();"]

    formatted = _format_call_params(mappings)
    lines = [f"{inst_name}("]
    for i, p in enumerate(formatted):
        if i < len(formatted) - 1:
            lines.append(f"{p},")
        else:
            lines.append(f"{p});")
    return lines


def _gen_function_call_expr(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                            hoisted: List[str]) -> str:
    func_name = box.box_type
    param_names = box.input_param_names
    indent = "        "

    mappings: List[Tuple[str, str]] = []
    for i, inp in enumerate(box.input_items):
        pname = param_names[i] if i < len(param_names) and param_names[i] else ""
        expr = _gen_expression(inp, tc, cfg, hoisted)
        expr = _clean_bool_expr(expr)
        flag = box.input_flags[i] if i < len(box.input_flags) else 0
        expr = _apply_input_flag(expr, flag, box, i, tc, hoisted)
        if not expr:
            continue
        if _is_default_skip(expr, pname, inp):
            continue
        mappings.append((pname, expr))

    if not mappings:
        return f"{func_name}()"

    named = [(n, v) for n, v in mappings if n]
    positional = [v for n, v in mappings if not n]

    if not named:
        return f"{func_name}({', '.join(positional)})"

    max_name = max(len(n) for n, _ in named)
    parts: List[str] = []
    for v in positional:
        parts.append(f"{indent}{v}")
    for n, v in named:
        parts.append(f"{indent}{n.ljust(max_name)} := {v}")

    inner = ",\n".join(parts)
    return f"{func_name}(\n{inner})"


def _is_default_skip(expr: str, pname: str, inp) -> bool:
    if isinstance(inp, OperandNode) and inp.is_empty:
        return True
    if not expr or expr == "":
        return True
    return False


def _gen_expression(node: Union[BoxNode, OperandNode, AssignNode, None], tc: TcFile,
                    cfg: MigrationConfig, hoisted: List[str]) -> str:
    if node is None:
        return ""

    if isinstance(node, OperandNode):
        if node.is_empty:
            return ""
        return node.name

    if isinstance(node, AssignNode):
        assign_lines = _gen_assign(node, tc, cfg)
        hoisted.extend(assign_lines)
        targets = [o for o in node.outputs if not o.is_empty]
        if targets:
            return targets[0].name
        return ""

    if isinstance(node, BoxNode) and node.box_type == "EXECUTE" and node.st_snippet:
        hoisted.extend(node.st_snippet)
        return ""

    box = node

    if box.call_type in INFIX_OPERATORS:
        return _gen_bool_expression(box, tc, cfg, hoisted)

    if box.call_type == "Not" or box.box_type == "NOT":
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            if " " in inner and not inner.startswith("("):
                return f"NOT ({inner})"
            return f"NOT {inner}"
        return "NOT ???"

    op_str = COMPARISON_OPS.get(box.box_type)
    if op_str:
        expr = _gen_infix_op(box, op_str, tc, cfg, hoisted)
        return f"({expr})" if expr else expr

    op_str = ARITHMETIC_OPS.get(box.box_type)
    if op_str:
        return _gen_infix_op(box, op_str, tc, cfg, hoisted)

    if box.box_type.upper() in CONVERSION_FUNCS or box.box_type.upper().startswith("TO_"):
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            return f"{box.box_type}({inner})"
        return f"{box.box_type}()"

    if box.box_type == "SEL":
        return _gen_sel(box, tc, cfg, hoisted)

    if box.box_type.upper() in IEC_FUNCTIONS:
        return _gen_iec_func(box, tc, cfg, hoisted)

    if box.box_type in ("MOVE", "ASSIGN"):
        if box.input_items:
            return _gen_expression(box.input_items[0], tc, cfg, hoisted)
        return ""

    if box.box_type == "JMP":
        label = ""
        if box.input_items:
            label = _gen_expression(box.input_items[0], tc, cfg, hoisted)
        if not label and box.output_items:
            for o in box.output_items:
                if not o.is_empty:
                    label = o.name
                    break
        if label:
            return f"(* TODO [FBD Migration]: JMP {label} - verify jump target *)"
        return "(* TODO [FBD Migration]: JMP - no label found *)"

    if box.box_type == "RET" or box.box_type == "RETURN":
        return "RETURN"

    if box.call_type in FB_CALL_TYPES:
        return _gen_fb_inline_expr(box, tc, cfg, hoisted)

    if box.call_type == "Action":
        return box.box_type

    if box.call_type == "Operator":
        return _gen_operator_call(box, tc, cfg, hoisted)

    if box.call_type == "Conversion":
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            return f"{box.box_type}({inner})"
        return f"{box.box_type}()"

    if box.box_type and box.input_items:
        return _gen_unknown_box(box, tc, cfg, hoisted)

    if box.box_type and not box.input_items and box.call_type in ("", "None"):
        return f"{box.box_type}()"

    if box.box_type:
        todo = f"(* TODO: Unknown box type '{box.box_type}' call_type='{box.call_type}' *)"
        tc.todos.append(todo)
        if cfg.mark_todo:
            return todo
        return f"{box.box_type}()"

    return ""


def _is_fully_wrapped(expr: str) -> bool:
    """Return True only if the outermost parens span the entire expression."""
    if not expr.startswith("("):
        return False
    depth = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0:
            return i == len(expr) - 1
    return False


def _gen_bool_expression(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                         hoisted: List[str]) -> str:
    op_word = INFIX_OPERATORS.get(box.call_type, "AND")
    parts: List[str] = []
    for i, inp in enumerate(box.input_items):
        expr = _gen_expression(inp, tc, cfg, hoisted)
        if not expr:
            continue
        flag = box.input_flags[i] if i < len(box.input_flags) else 0
        expr = _apply_input_flag(expr, flag, box, i, tc, hoisted)
        parts.append(expr)

    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]

    needs_parens = any(" OR " in p or " AND " in p or " XOR " in p for p in parts)
    if needs_parens:
        wrapped = []
        for p in parts:
            if (" OR " in p or " AND " in p or " XOR " in p) and not _is_fully_wrapped(p):
                wrapped.append(f"({p})")
            else:
                wrapped.append(p)
        parts = wrapped

    return f" {op_word} ".join(parts)


def _gen_infix_op(box: BoxNode, op: str, tc: TcFile, cfg: MigrationConfig,
                  hoisted: List[str]) -> str:
    exprs = []
    for inp in box.input_items:
        e = _gen_expression(inp, tc, cfg, hoisted)
        if e:
            exprs.append(e)
    if len(exprs) == 2:
        return f"{exprs[0]} {op} {exprs[1]}"
    if len(exprs) == 1:
        return exprs[0]
    return f" {op} ".join(exprs)


def _gen_sel(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
             hoisted: List[str]) -> str:
    exprs = [_gen_expression(inp, tc, cfg, hoisted) for inp in box.input_items]
    while len(exprs) < 3:
        exprs.append("???")
    return f"SEL({exprs[0]}, {exprs[1]}, {exprs[2]})"


def _gen_iec_func(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                  hoisted: List[str]) -> str:
    exprs = []
    for inp in box.input_items:
        e = _gen_expression(inp, tc, cfg, hoisted)
        if e:
            exprs.append(e)
    args = ", ".join(exprs)
    return f"{box.box_type}({args})"


def _gen_fb_inline_expr(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                        hoisted: List[str]) -> str:
    """Hoist nested FB call or inline function call, return expression reference."""
    if box.call_type in ("Function", "Program", "Method"):
        return _gen_function_call_expr(box, tc, cfg, hoisted)
    if not box.instance or not box.instance.name:
        todo = f"(* TODO [FBD Migration]: FB call without instance: {box.box_type} *)"
        tc.todos.append(todo)
        return todo

    inst = box.instance.name
    fb_lines = _gen_fb_call(box, tc, cfg, hoisted)
    hoisted.extend(fb_lines)

    out_names = box.output_param_names
    if out_names and out_names[0]:
        return f"{inst}.{out_names[0]}"
    return inst


def _gen_operator_call(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                       hoisted: List[str]) -> str:
    op_str = COMPARISON_OPS.get(box.box_type)
    if op_str:
        expr = _gen_infix_op(box, op_str, tc, cfg, hoisted)
        return f"({expr})" if expr else expr
    op_str = ARITHMETIC_OPS.get(box.box_type)
    if op_str:
        return _gen_infix_op(box, op_str, tc, cfg, hoisted)

    if box.box_type.upper() in CONVERSION_FUNCS:
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            return f"{box.box_type}({inner})"

    if box.box_type.upper() in IEC_FUNCTIONS:
        return _gen_iec_func(box, tc, cfg, hoisted)

    if box.input_items:
        exprs = []
        for inp in box.input_items:
            e = _gen_expression(inp, tc, cfg, hoisted)
            if e:
                exprs.append(e)
        args = ", ".join(exprs)
        return f"{box.box_type}({args})"
    return f"{box.box_type}()"


def _gen_unknown_box(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                     hoisted: List[str]) -> str:
    if box.instance:
        inst = box.instance.name
        param_names = box.input_param_names
        parts = []
        for i, inp in enumerate(box.input_items):
            expr = _gen_expression(inp, tc, cfg, hoisted)
            if not expr:
                continue
            if i < len(param_names) and param_names[i]:
                parts.append(f"{param_names[i]} := {expr}")
            else:
                parts.append(expr)
        if parts:
            args = ", ".join(parts)
            return f"(* {inst}({args}) *)"
        return f"(* {inst}() *)"

    exprs = []
    for inp in box.input_items:
        e = _gen_expression(inp, tc, cfg, hoisted)
        if e:
            exprs.append(e)
    args = ", ".join(exprs)
    todo = f"(* TODO: {box.box_type}({args}) *)"
    tc.todos.append(todo)
    return todo


# ---------------------------------------------------------------------------
# GUID regeneration
# ---------------------------------------------------------------------------

def _regenerate_guids(xml_text: str) -> str:
    def _new_guid(match):
        return f'Id="{{{str(uuid.uuid4())}}}"'
    return re.sub(r'Id="\{[0-9a-fA-F\-]+\}"', _new_guid, xml_text)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Backup and file operations
# ---------------------------------------------------------------------------

def create_backup(path: Path, backup_dir: Optional[Path] = None,
                  input_root: Optional[Path] = None) -> Optional[Path]:
    """Create a backup copy of *path* before it is overwritten.

    When *backup_dir* is given (directory-level backup), the file is
    copied into *backup_dir* keeping its relative position from
    *input_root*.  Otherwise a timestamped copy is placed next to the
    original.
    """
    try:
        if backup_dir is not None:
            if input_root is not None:
                try:
                    rel = path.relative_to(input_root)
                except ValueError:
                    rel = Path(path.name)
            else:
                rel = Path(path.name)
            backup_path = backup_dir / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
            backup_name = f"{path.stem}_backup_{ts}{path.suffix}"
            backup_path = path.parent / backup_name
        shutil.copy2(str(path), str(backup_path))
        return backup_path
    except Exception as exc:
        logging.error("Backup failed: %s", exc)
        return None


def write_output_file(content: str, path: Path, encoding: str = "utf-8") -> bool:
    try:
        fd, tmp_path = tempfile.mkstemp(
            suffix=path.suffix, prefix=f".{path.stem}_tmp_", dir=str(path.parent))
        try:
            os.write(fd, content.encode(encoding))
            os.close(fd)
            fd = -1
            os.replace(tmp_path, str(path))
        except BaseException:
            if fd >= 0:
                os.close(fd)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        return True
    except Exception as exc:
        logging.error("Write failed for %s: %s", path, exc)
        return False


def can_replace(tc: TcFile, cfg: MigrationConfig, backup_path: Optional[Path]) -> Tuple[bool, str]:
    checks = [
        (bool(tc.path and tc.path.is_file()), "Original file readable"),
        (tc.file_type in SUPPORTED_EXTENSIONS, "File type supported"),
        (bool(tc.pou_name), "POU recognized"),
        (tc.impl_type in ("NWL", "CFC"), "FBD/FUP or CFC logic detected"),
        (bool(tc.declaration), "Declarations preserved"),
        (bool(tc.generated_st and tc.generated_st.strip()), "ST implementation generated"),
        (not tc.errors, "No critical errors"),
        (cfg.backup is False or backup_path is not None, "Backup created or disabled"),
        (cfg.force, "--force is set"),
        (not cfg.dry_run, "Not in dry-run mode"),
    ]
    for condition, desc in checks:
        if not condition:
            return False, f"Pre-condition failed: {desc}"
    return True, "All pre-conditions met"


# ---------------------------------------------------------------------------
# Logging and reporting
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Output path and print helpers
# ---------------------------------------------------------------------------

def _resolve_output_path(source: Path, cfg: MigrationConfig) -> Path:
    if cfg.output_path:
        out = Path(cfg.output_path)
        if out.is_dir():
            return out / f"{source.stem}_ST{source.suffix}"
        return out
    return source.parent / f"{source.stem}_ST_Generated{source.suffix}"


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
