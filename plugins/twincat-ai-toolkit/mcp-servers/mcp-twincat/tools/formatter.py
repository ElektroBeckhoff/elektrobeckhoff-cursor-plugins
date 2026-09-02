"""
Structured Text Python formatter MCP tools for TwinCAT 3 (file-based, no COM required).
"""

from __future__ import annotations

import os
import threading
from typing import Any

from .common import _clean_path, _json, _resolve_plcproj_path

_format_lock = threading.Lock()
_format_progress: dict = {}


def twincat_format(
    path: str = "",
    recursive: bool = True,
    dry_run: bool = False,
    validate: bool = True,
    format_xml: bool = True,
    sort_elements: bool = False,
    config_path: str = "",
    region: str = "all",
    member: str = "",
    member_filter: str = "",
    project: str = "",
) -> str:
    """Format TwinCAT3 ST files (*.TcPOU, *.TcDUT, *.TcGVL, *.TcIO).

    Pure Python file-based formatter — no XAE/COM needed.
    Formats ST code (indentation, alignment, wrapping, keywords) AND
    XML structure (attribute order, element sorting, CDATA handling).

    path: file or directory to format (auto-detected if omitted)
    recursive: recurse into subdirectories (default True)
    dry_run: report changes without writing (default False)
    validate: run XML validation checks (default True)
    format_xml: format XML structure (default True)
    sort_elements: sort XML elements alphabetically (default False; opt-in)
    config_path: custom .stformat.json config file path (optional)
    region: "all" (default), "declaration", or "implementation" — limit to specific code sections
    member: specific Method/Action/Property name to format (e.g. "M_Init")
    member_filter: "all_methods", "all_actions", or "all_properties" — format only that member type
    project: path to .sln or .plcproj — discovers all TwinCAT files (overrides path)"""
    from formatter.config import load_config
    from formatter.file_processor import discover_files, discover_project_files, process_batch
    from formatter.types import FormatRegion, FormatScope, MemberFilter as MF

    path = _clean_path(path)
    project = _clean_path(project)
    config_path = _clean_path(config_path)

    if not path and not project:
        auto_p = _resolve_plcproj_path()
        if auto_p:
            project = auto_p
        else:
            path = os.getcwd()

    global _format_progress
    with _format_lock:
        _format_progress = {"status": "running", "path": path or project, "files_done": 0, "files_total": 0}

    try:
        cfg_root = project if project and os.path.isdir(project) else (path if os.path.isdir(path) else os.path.dirname(path or project))
        cfg = load_config(config_path=config_path or None, project_root=cfg_root or os.getcwd())

        # Build scope
        scope = None
        fmt_region = FormatRegion(region) if region != "all" else FormatRegion.ALL
        mf = None
        if member_filter:
            mf = MF(member_filter)
        if fmt_region != FormatRegion.ALL or member or mf:
            scope = FormatScope(region=fmt_region, member_filter=mf, member_name=member)

        # Discover files
        if project:
            files = discover_project_files(project)
        else:
            files = discover_files([path], recursive=recursive)

        with _format_lock:
            _format_progress["files_total"] = len(files)

        if not files:
            return _json({"success": True, "message": "No formattable files found", "files": 0})

        batch = process_batch(
            files, cfg,
            dry_run=dry_run,
            validate=validate,
            format_st=True,
            format_xml=format_xml,
            sort_xml=sort_elements,
            scope=scope,
        )

        with _format_lock:
            _format_progress = {"status": "done", "files_done": batch.total, "files_total": batch.total}

        results_list = []
        for r in batch.results:
            entry = {"file": os.path.basename(r.path), "changed": r.changed, "success": r.success}
            if r.errors:
                entry["errors"] = list(r.errors)
            if r.warnings:
                entry["warnings"] = list(r.warnings)
            if r.diff:
                entry["diff"] = r.diff
            results_list.append(entry)

        return _json({
            "success": batch.errors == 0,
            "total": batch.total,
            "formatted": batch.formatted,
            "unchanged": batch.unchanged,
            "errors": batch.errors,
            "dry_run": dry_run,
            "results": results_list,
        })
    except Exception as exc:
        with _format_lock:
            _format_progress = {"status": "error", "error": str(exc)}
        return _json({"success": False, "error": str(exc)})


def twincat_format_progress() -> str:
    """Poll the progress of a running twincat_format operation."""
    with _format_lock:
        return _json(_format_progress)


def twincat_format_validate(
    path: str,
    recursive: bool = True,
    config_path: str = "",
) -> str:
    """Validate TwinCAT3 XML files without formatting.

    Checks: GUID format/uniqueness, Name match, required elements,
    SpecialFunc values, FolderPath consistency, interface rules.

    path: file or directory to validate
    recursive: recurse into subdirectories (default True)
    config_path: custom config file path (optional)"""
    from formatter.config import load_config
    from formatter.file_processor import discover_files, process_batch

    try:
        cfg = load_config(config_path=config_path or None, project_root=path if os.path.isdir(path) else os.path.dirname(path))
        files = discover_files([path], recursive=recursive)

        if not files:
            return _json({"success": True, "message": "No files to validate", "files": 0})

        batch = process_batch(
            files, cfg,
            dry_run=True,
            validate=True,
            format_st=False,
            format_xml=False,
        )

        issues_list = []
        for issue in batch.validation_issues:
            issues_list.append({
                "level": issue.level,
                "file": os.path.basename(issue.file),
                "line": issue.line,
                "rule": issue.rule,
                "message": issue.message,
            })

        return _json({
            "success": len([i for i in batch.validation_issues if i.level == "error"]) == 0,
            "total_files": batch.total,
            "issues": issues_list,
        })
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


def twincat_format_config(
    project_path: str = "",
    config_path: str = "",
) -> str:
    """Show the active formatter configuration.

    Shows merged config (defaults + user overrides from .stformat.json).

    project_path: project root to search for .stformat.json (optional)
    config_path: explicit config file to load (optional)"""
    from formatter.config import load_config, config_to_dict

    try:
        cfg = load_config(config_path=config_path or None, project_root=project_path or None)
        return _json({"success": True, "config": config_to_dict(cfg)})
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


def register_tools(mcp: Any) -> None:
    """Register Python ST formatter tools on FastMCP server."""
    mcp.tool()(twincat_format)
    mcp.tool()(twincat_format_progress)
    mcp.tool()(twincat_format_validate)
    mcp.tool()(twincat_format_config)
