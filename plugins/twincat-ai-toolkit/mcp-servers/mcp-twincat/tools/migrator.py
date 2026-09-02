"""
FBD/FUP and CFC to Structured Text migration MCP tools for TwinCAT 3.
"""

from __future__ import annotations

import contextlib
import io
import os
from typing import Any

from migrator.fbd import main as fup_main
from migrator.cfc import main as cfc_main
from migrator.router import main as unified_main
from .common import _clean_path, _json

_AUTO_GEN_MARKER = "AUTO-GENERATED"
_TC_EXTENSIONS = {".tcpou", ".tcdut", ".tcgvl", ".tcio"}


def _detect_member_filter(file_path: str) -> str:
    """Detect whether a TcPOU file contains only methods, actions, or properties.

    Returns a member_filter value ("all_methods", "all_actions",
    "all_properties") when exactly one member type is present, otherwise "".
    """
    try:
        with open(file_path, "r", encoding="utf-8-sig") as fh:
            content = fh.read()
    except Exception:
        return ""

    has_method = "<Method " in content or "<Method>" in content
    has_action = "<Action " in content or "<Action>" in content
    has_property = "<Property " in content or "<Property>" in content

    types_found = sum([has_method, has_action, has_property])
    if types_found == 1:
        if has_method:
            return "all_methods"
        if has_action:
            return "all_actions"
        if has_property:
            return "all_properties"
    return ""


def _file_has_auto_generated(file_path: str) -> bool:
    """Check if a file contains the AUTO-GENERATED migration marker."""
    try:
        with open(file_path, "r", encoding="utf-8-sig") as fh:
            head = fh.read(4096)
        return _AUTO_GEN_MARKER in head
    except Exception:
        return False


def _collect_format_targets(
    input_path: str, output_path: str, swap: bool, force: bool
) -> list[str]:
    """Determine which output files/directories to format after migration.

    Returns a list of absolute file paths that are TwinCAT ST files
    with the AUTO-GENERATED marker.
    """
    inp = os.path.abspath(input_path)

    if swap or force:
        if os.path.isfile(inp):
            candidates = [inp]
        elif os.path.isdir(inp):
            candidates = []
            for root, _dirs, files in os.walk(inp):
                for f in files:
                    if os.path.splitext(f)[1].lower() in _TC_EXTENSIONS:
                        candidates.append(os.path.join(root, f))
        else:
            return []
        return [c for c in candidates if _file_has_auto_generated(c)]

    if output_path:
        target = os.path.abspath(output_path)
    elif os.path.isfile(inp):
        stem, ext = os.path.splitext(inp)
        target = f"{stem}_st_generated{ext}"
    elif os.path.isdir(inp):
        parent = os.path.dirname(inp)
        base = os.path.basename(inp)
        candidates = []
        for entry in os.listdir(parent):
            if entry.startswith(f"{base}_st_generated"):
                full = os.path.join(parent, entry)
                if os.path.isdir(full):
                    candidates.append(full)
        if not candidates:
            return []
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        target = candidates[0]
    else:
        return []

    if not os.path.exists(target):
        return []

    if os.path.isfile(target):
        if _file_has_auto_generated(target):
            return [target]
        return []

    result = []
    for root, _dirs, files in os.walk(target):
        for f in files:
            if os.path.splitext(f)[1].lower() in _TC_EXTENSIONS:
                fp = os.path.join(root, f)
                if _file_has_auto_generated(fp):
                    result.append(fp)
    return result


def _format_after_migrate(
    input_path: str,
    output_path: str,
    swap: bool,
    force: bool,
    dry_run: bool,
    analyze_only: bool,
    exit_code: int,
) -> dict:
    """Run Python formatter on migration output files.

    Returns a dict with formatting summary to attach to the migration result.
    Silently returns an empty dict if no formatting is needed or possible.
    """
    if exit_code != 0 or dry_run or analyze_only:
        return {}

    targets = _collect_format_targets(input_path, output_path, swap, force)
    if not targets:
        return {}

    from formatter.config import load_config
    from formatter.file_processor import process_batch
    from formatter.types import FormatRegion, FormatScope, MemberFilter as MF

    total_formatted = 0
    total_errors = 0
    file_results = []

    for fpath in targets:
        mf_str = _detect_member_filter(fpath)
        scope = None
        if mf_str:
            scope = FormatScope(
                region=FormatRegion.IMPLEMENTATION,
                member_filter=MF(mf_str),
            )

        try:
            cfg = load_config(project_root=os.path.dirname(fpath))
            batch = process_batch(
                [fpath], cfg,
                dry_run=False,
                validate=True,
                format_st=True,
                format_xml=True,
                sort_xml=False,
                scope=scope,
            )
            for r in batch.results:
                entry = {"file": os.path.basename(r.path), "changed": r.changed, "success": r.success}
                if r.errors:
                    entry["errors"] = list(r.errors)
                file_results.append(entry)
            total_formatted += batch.formatted
            total_errors += batch.errors
        except Exception as exc:
            file_results.append({"file": os.path.basename(fpath), "changed": False, "success": False, "errors": [str(exc)]})
            total_errors += 1

    return {
        "format_after_migrate": {
            "files_total": len(targets),
            "files_formatted": total_formatted,
            "files_errors": total_errors,
            "results": file_results,
        }
    }


def twincat_fup_migrate(
    input: str,
    output: str = "",
    recursive: bool = False,
    backup: bool = True,
    force: bool = False,
    swap: bool = False,
    dry_run: bool = False,
    analyze_only: bool = False,
    log: bool = True,
    report: bool = True,
    config: str = "",
    encoding: str = "utf-8",
    strict: bool = False,
    preserve_ids: bool = True,
    preserve_comments: bool = True,
    mark_todo: bool = True,
    fail_on_unclear: bool = True,
    log_level: str = "INFO",
) -> str:
    """Convert TwinCAT 3 FBD/FUP .TcPOU implementations to Structured Text.

    Parses NWL XML, generates functionally identical ST code, preserves
    declarations, comments, attributes, and GUIDs. Supports single
    files and recursive folder processing with backup, swap, force,
    dry-run, and analyze-only modes.

    ALWAYS start with dry_run=true or analyze_only=true before actual
    migration.

    Does NOT require a running TcXaeShell instance. Works on any OS.

    Args:
        input: REQUIRED. Path to a .TcPOU/.TcGVL/.TcDUT file or folder.
        output: Explicit output path. Empty = auto (default/swap mode).
        recursive: Recurse into subfolders when input is a directory.
        backup: Create backup before modification (recommended).
        force: DESTRUCTIVE. Overwrite original in-place (GUIDs kept).
        swap: Backup original, write ST to original path.
        dry_run: SAFE. Preview only, zero files written.
        analyze_only: SAFE. Inspect FBD structure, no ST generation.
        log: Write migration log file.
        report: Write migration report file.
        config: Path to JSON config file (CLI params take precedence).
        encoding: File encoding (auto-fallback: utf-8-sig, latin-1).
        strict: Abort on any TODO marker. Blocks force without backup.
        preserve_ids: Keep original GUIDs in force mode.
        preserve_comments: Keep FBD comments as ST header blocks.
        mark_todo: Wrap untranslatable logic in TODO comment blocks.
        fail_on_unclear: Warn on TODO markers (abort with strict=true).
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""
    input = _clean_path(input)
    output = _clean_path(output)
    config = _clean_path(config)

    argv = ["--input", input]

    if output:
        argv.extend(["--output", output])
    if recursive:
        argv.append("--recursive")
    if not backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")
    if swap:
        argv.append("--swap")
    if dry_run:
        argv.append("--dry-run")
    if analyze_only:
        argv.append("--analyze-only")
    if not log:
        argv.append("--no-log")
    if not report:
        argv.append("--no-report")
    if config:
        argv.extend(["--config", config])
    if encoding != "utf-8":
        argv.extend(["--encoding", encoding])
    if strict:
        argv.append("--strict")
    if not mark_todo:
        argv.append("--no-mark-todo")
    if not fail_on_unclear:
        argv.append("--no-fail-on-unclear")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = fup_main(argv)
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 1
    except Exception as exc:
        return _json({
            "success": False,
            "exit_code": 1,
            "output": buf.getvalue(),
            "error": str(exc),
        })

    result = {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    }
    fmt = _format_after_migrate(input, output, swap, force, dry_run, analyze_only, exit_code)
    result.update(fmt)
    return _json(result)


def twincat_cfc_migrate(
    input: str,
    output: str = "",
    recursive: bool = False,
    backup: bool = True,
    force: bool = False,
    swap: bool = False,
    dry_run: bool = False,
    analyze_only: bool = False,
    log: bool = True,
    report: bool = True,
    config: str = "",
    encoding: str = "utf-8",
    strict: bool = False,
    preserve_ids: bool = True,
    preserve_comments: bool = True,
    mark_todo: bool = True,
    fail_on_unclear: bool = True,
    log_level: str = "INFO",
) -> str:
    """Convert TwinCAT 3 CFC .TcPOU implementations to Structured Text.

    Parses CFC XML (CFCInputElement, CFCOutputElement, CFCBoxElement),
    resolves execution order from XML serialization, generates
    functionally equivalent ST code, preserves declarations, comments,
    attributes, and GUIDs. Supports single files and recursive folder
    processing with backup, swap, force, dry-run, and analyze-only modes.

    ALWAYS start with dry_run=true or analyze_only=true before actual
    migration.

    Does NOT require a running TcXaeShell instance. Works on any OS.

    Args:
        input: REQUIRED. Path to a .TcPOU file or folder containing CFC POUs.
        output: Explicit output path. Empty = auto (default/swap mode).
        recursive: Recurse into subfolders when input is a directory.
        backup: Create backup before modification (recommended).
        force: DESTRUCTIVE. Overwrite original in-place (GUIDs kept).
        swap: Backup original, write ST to original path.
        dry_run: SAFE. Preview only, zero files written.
        analyze_only: SAFE. Inspect CFC structure, no ST generation.
        log: Write migration log file.
        report: Write migration report file.
        config: Path to JSON config file (CLI params take precedence).
        encoding: File encoding (auto-fallback: utf-8-sig, latin-1).
        strict: Abort on any TODO marker. Blocks force without backup.
        preserve_ids: Keep original GUIDs in force mode.
        preserve_comments: Keep CFC comments as ST header blocks.
        mark_todo: Wrap untranslatable logic in TODO comment blocks.
        fail_on_unclear: Warn on TODO markers (abort with strict=true).
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""
    input = _clean_path(input)
    output = _clean_path(output)
    config = _clean_path(config)

    argv = ["--input", input]

    if output:
        argv.extend(["--output", output])
    if recursive:
        argv.append("--recursive")
    if not backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")
    if swap:
        argv.append("--swap")
    if dry_run:
        argv.append("--dry-run")
    if analyze_only:
        argv.append("--analyze-only")
    if not log:
        argv.append("--no-log")
    if not report:
        argv.append("--no-report")
    if config:
        argv.extend(["--config", config])
    if encoding != "utf-8":
        argv.extend(["--encoding", encoding])
    if strict:
        argv.append("--strict")
    if not mark_todo:
        argv.append("--no-mark-todo")
    if not fail_on_unclear:
        argv.append("--no-fail-on-unclear")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = cfc_main(argv)
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 1
    except Exception as exc:
        return _json({
            "success": False,
            "exit_code": 1,
            "output": buf.getvalue(),
            "error": str(exc),
        })

    result = {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    }
    fmt = _format_after_migrate(input, output, swap, force, dry_run, analyze_only, exit_code)
    result.update(fmt)
    return _json(result)


def twincat_migrate(
    input: str,
    output: str = "",
    recursive: bool = False,
    backup: bool = True,
    force: bool = False,
    swap: bool = False,
    dry_run: bool = False,
    analyze_only: bool = False,
    log: bool = True,
    report: bool = True,
    config: str = "",
    encoding: str = "utf-8",
    strict: bool = False,
    preserve_ids: bool = True,
    preserve_comments: bool = True,
    mark_todo: bool = True,
    fail_on_unclear: bool = True,
    log_level: str = "INFO",
) -> str:
    """Convert TwinCAT 3 FBD/FUP and CFC implementations to Structured Text
    in a single pass.

    Auto-detects the implementation type (NWL / CFC) per file and routes
    to the appropriate converter. Produces a single combined report and
    shared backup directory. Files that are already ST or use unsupported
    languages (SFC, IL, LD) are skipped gracefully.

    ALWAYS start with dry_run=true or analyze_only=true before actual
    migration.

    Does NOT require a running TcXaeShell instance. Works on any OS.

    Args:
        input: REQUIRED. Path to a .TcPOU file or folder.
        output: Explicit output path. Empty = auto (default/swap mode).
        recursive: Recurse into subfolders when input is a directory.
        backup: Create backup before modification (recommended).
        force: DESTRUCTIVE. Overwrite original in-place (GUIDs kept).
        swap: Backup original, write ST to original path.
        dry_run: SAFE. Preview only, zero files written.
        analyze_only: SAFE. Inspect structure, no ST generation.
        log: Write migration log file.
        report: Write migration report file.
        config: Path to JSON config file (CLI params take precedence).
        encoding: File encoding (auto-fallback: utf-8-sig, latin-1).
        strict: Abort on any TODO marker. Blocks force without backup.
        preserve_ids: Keep original GUIDs in force mode.
        preserve_comments: Keep comments as ST header blocks.
        mark_todo: Wrap untranslatable logic in TODO comment blocks.
        fail_on_unclear: Warn on TODO markers (abort with strict=true).
        log_level: Verbosity: DEBUG, INFO, WARNING, ERROR."""
    input = _clean_path(input)
    output = _clean_path(output)
    config = _clean_path(config)

    argv = ["--input", input]

    if output:
        argv.extend(["--output", output])
    if recursive:
        argv.append("--recursive")
    if not backup:
        argv.append("--no-backup")
    if force:
        argv.append("--force")
    if swap:
        argv.append("--swap")
    if dry_run:
        argv.append("--dry-run")
    if analyze_only:
        argv.append("--analyze-only")
    if not log:
        argv.append("--no-log")
    if not report:
        argv.append("--no-report")
    if config:
        argv.extend(["--config", config])
    if encoding != "utf-8":
        argv.extend(["--encoding", encoding])
    if strict:
        argv.append("--strict")
    if not mark_todo:
        argv.append("--no-mark-todo")
    if not fail_on_unclear:
        argv.append("--no-fail-on-unclear")
    if log_level != "INFO":
        argv.extend(["--log-level", log_level])

    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            exit_code = unified_main(argv)
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 1
    except Exception as exc:
        return _json({
            "success": False,
            "exit_code": 1,
            "output": buf.getvalue(),
            "error": str(exc),
        })

    result = {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "output": buf.getvalue(),
    }
    fmt = _format_after_migrate(input, output, swap, force, dry_run, analyze_only, exit_code)
    result.update(fmt)
    return _json(result)


def register_tools(mcp: Any) -> None:
    """Register migration tools on FastMCP server."""
    mcp.tool()(twincat_fup_migrate)
    mcp.tool()(twincat_cfc_migrate)
    mcp.tool()(twincat_migrate)
