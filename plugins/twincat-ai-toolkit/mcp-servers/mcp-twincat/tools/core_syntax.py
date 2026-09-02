"""
Core syntax, AST, semantic diagnostics, and symbol resolution MCP tools for TwinCAT 3.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional

from twincat_plcproj_ops import read_project_info
from twincat_core.constants import is_internal_toolkit_path
from .common import (
    _clean_path,
    _find_repo_root,
    _json,
    _resolve_plcproj_path,
    _resolve_sln,
    _EXCLUDES_LOWER,
)


def twincat_plcproj_info(plcproj_path: str = "") -> str:
    """Read TwinCAT PLC project metadata from .plcproj XML.

    Returns Title, Version, Company, Name, Released.
    Does NOT require a running TcXaeShell instance.
    Leave plcproj_path empty for auto-detection."""
    resolved = _resolve_plcproj_path(plcproj_path)
    if not resolved:
        return _json({"error": "No .plcproj found. Provide plcproj_path."})

    try:
        return _json(read_project_info(resolved))
    except Exception as exc:
        return _json({"error": str(exc)})


def twincat_workspace_symbols(
    query: str = "",
    plcproj_path: str = "",
    limit: int = 50,
) -> str:
    """Search for symbols (POUs, DUTs, GVLs, methods, variables) across the TwinCAT project using twincat_core.

    query: Search substring to filter symbol names (optional)
    plcproj_path: Path to .plcproj file (optional, auto-detected if omitted)
    limit: Max results to return (default: 50)"""
    try:
        from twincat_core.project import get_shared_workspace

        p_path = _resolve_plcproj_path(plcproj_path)
        workspace = get_shared_workspace(p_path if p_path else None)
        symbols = workspace.find_symbols(query=query, limit=limit)

        results = []
        for s in symbols:
            results.append({
                "name": s.name,
                "kind": s.kind.value,
                "type_ref": s.type_ref,
                "file": str(s.file_path) if s.file_path else "",
                "line": s.span.start.line if s.span else 0,
                "doc": s.doc_comment,
            })
        return _json({"total": len(results), "symbols": results})
    except Exception as exc:
        return _json({"error": str(exc)})


def twincat_symbol_lookup(
    symbol_name: str,
    scope_pou: str = "",
    plcproj_path: str = "",
) -> str:
    """Resolve a symbol or member access chain (e.g. 'fbMotor.stParam.fSpeed', 'TON.IN', 'Tc2_Standard.CONCAT').

    symbol_name: Identifier or chained member expression to resolve (e.g. 'fbAxis.M_GetStatus().bRunning')
    scope_pou: Enclosing POU or method name for local context (optional)
    plcproj_path: Path to .plcproj file (optional, auto-detected if omitted)"""
    try:
        from twincat_core.project import get_shared_workspace

        p_path = _resolve_plcproj_path(plcproj_path)
        workspace = get_shared_workspace(p_path if p_path else None)
        sym = workspace.lookup_symbol(symbol_name, scope_pou=scope_pou or None)
        if not sym:
            return _json({
                "found": False,
                "symbol_name": symbol_name,
                "message": f"Symbol '{symbol_name}' could not be resolved.",
            })

        return _json({
            "found": True,
            "name": sym.name,
            "kind": sym.kind.value,
            "type_ref": sym.type_ref,
            "file": str(sym.file_path) if sym.file_path else "",
            "line": sym.span.start.line if sym.span else 0,
            "doc": sym.doc_comment,
            "initial_value": sym.initial_value,
        })
    except Exception as exc:
        return _json({"error": str(exc)})


def twincat_check_syntax(
    path: str = "",
    recursive: bool = True,
    include_warnings: bool = True,
) -> str:
    """Validate TwinCAT 3 IEC 61131-3 Structured Text syntax and semantics using twincat_core.

    Fast, headless validator (no Visual Studio or TcXaeShell required, works cross-platform).
    Performs full ST syntax parsing, AST construction, and semantic verification:
      - Lossless XML CDATA integrity
      - Lexer & token errors
      - Declaration rules (TC-DECL-001..007: explicit return types, constant inits, array bounds, etc.)
      - Statement & expression rules (TC-STMT-*, TC-EXPR-*: loop bounds, jumps, assignment targets)
      - Semantic rules (TC-SEM-001..007: unknown types, duplicate identifiers, interface conformance,
        cyclic inheritance, abstract instantiations, type mismatches, narrowing/precision loss warnings)

    path: File (.TcPOU, .TcDUT, .TcGVL, .TcIO), directory, .plcproj, or .sln. If empty, auto-detects project.
    recursive: Scan subdirectories recursively when path is a directory (default: True).
    include_warnings: Include severity=WARNING items (e.g. TC-SEM-007 narrowing warnings) (default: True).
    """
    try:
        from twincat_core.project import get_shared_workspace
        from twincat_core.semantic.diagnostics import run_semantic_analysis
        from twincat_core.syntax.diagnostics import DiagnosticSeverity

        target_path: Optional[Path] = None
        cleaned_path = _clean_path(path)
        if cleaned_path:
            p = Path(cleaned_path)
            if not p.is_absolute() and not p.exists():
                found_candidate: Optional[Path] = None
                # 1. Search in active bridge solution/plcproj directory
                try:
                    from .solution import _get_bridge
                    b = _get_bridge()
                    if b:
                        b_sln = _clean_path(b._call_sta(lambda: b._sln_path, timeout=2) or "")
                        b_plc = _clean_path(b._call_sta(lambda: b._plcproj_file_path, timeout=2) or "")
                        search_dirs = []
                        if b_plc and os.path.isfile(b_plc):
                            search_dirs.append(Path(b_plc).parent)
                        if b_sln and os.path.isfile(b_sln):
                            search_dirs.append(Path(b_sln).parent)
                            b_repo = _find_repo_root(b_sln)
                            if b_repo and Path(b_repo) not in search_dirs:
                                search_dirs.append(Path(b_repo))
                        for sdir in search_dirs:
                            direct = sdir / p
                            if direct.is_file():
                                found_candidate = direct.resolve()
                                break
                            for match in sdir.rglob(p.name):
                                if match.is_file():
                                    found_candidate = match.resolve()
                                    break
                            if found_candidate:
                                break
                except Exception:
                    pass

                # 2. Search in workspace project root if already indexed
                if not found_candidate:
                    try:
                        from twincat_core.project import get_shared_workspace
                        ws = get_shared_workspace()
                        if ws:
                            if ws.project:
                                proj_root = ws.project.root_dir
                                direct = proj_root / p
                                if direct.is_file():
                                    found_candidate = direct.resolve()
                                else:
                                    for match in proj_root.rglob(p.name):
                                        if match.is_file():
                                            found_candidate = match.resolve()
                                            break
                            if not found_candidate and getattr(ws, "root_dir", None):
                                r_dir = Path(ws.root_dir)
                                direct = r_dir / p
                                if direct.is_file():
                                    found_candidate = direct.resolve()
                                else:
                                    for match in r_dir.rglob(p.name):
                                        if match.is_file():
                                            found_candidate = match.resolve()
                                            break
                            if not found_candidate and getattr(ws, "indexed_files", None):
                                for f in ws.indexed_files:
                                    if Path(f).name.lower() == p.name.lower():
                                        found_candidate = Path(f).resolve()
                                        break
                    except Exception:
                        pass

                # 3. Search near CWD / repo root
                if not found_candidate:
                    cwd = Path.cwd()
                    for match in cwd.rglob(p.name):
                        if is_internal_toolkit_path(match):
                            continue
                        if match.is_file():
                            found_candidate = match.resolve()
                            break

                if found_candidate:
                    p = found_candidate
                else:
                    p = p.resolve()
            else:
                p = p.resolve()

            if not p.exists():
                return _json({"success": False, "error": f"Path does not exist: {path}"})
            target_path = p
        else:
            auto_p = _resolve_plcproj_path()
            if auto_p:
                target_path = Path(auto_p).resolve()
            else:
                target_path = Path.cwd().resolve()

        files_to_check: list[Path] = []
        workspace = get_shared_workspace(target_path)

        if target_path.is_file():
            if target_path.suffix.lower() == ".plcproj":
                if workspace.project:
                    files_to_check = [
                        item.abs_path
                        for item in workspace.project.compile_items.values()
                        if not item.exclude_from_build and item.abs_path.is_file()
                    ]
            elif target_path.suffix.lower() == ".sln":
                resolved = _resolve_sln(str(target_path))
                if isinstance(resolved, dict) and not resolved.get("success", True):
                    return _json(resolved)
                plcproj_p = Path(resolved if isinstance(resolved, str) else resolved["plcproj_path"])
                workspace = get_shared_workspace(plcproj_p)
                if workspace.project:
                    files_to_check = [
                        item.abs_path
                        for item in workspace.project.compile_items.values()
                        if not item.exclude_from_build and item.abs_path.is_file()
                    ]
            elif target_path.suffix.lower() in (".tcpou", ".tcdut", ".tcgvl", ".tcio"):
                files_to_check = [target_path]
            else:
                return _json({"success": False, "error": f"Unsupported file type: {target_path.suffix}"})
        elif target_path.is_dir():
            if workspace.project and (
                target_path == workspace.project.root_dir.resolve()
                or target_path == workspace.project.project_path.parent.resolve()
            ):
                files_to_check = [
                    item.abs_path
                    for item in workspace.project.compile_items.values()
                    if not item.exclude_from_build and item.abs_path.is_file()
                ]
            else:
                pattern = "**/*" if recursive else "*"
                candidates: list[Path] = []
                for ext in (".TcPOU", ".TcDUT", ".TcGVL", ".TcIO"):
                    candidates.extend(target_path.glob(f"{pattern}{ext}"))
                    if ext.lower() != ext:
                        candidates.extend(target_path.glob(f"{pattern}{ext.lower()}"))
                seen_f: set[Path] = set()
                for f in candidates:
                    rf = f.resolve()
                    if rf not in seen_f and rf.is_file():
                        seen_f.add(rf)
                        files_to_check.append(rf)

        if not workspace:
            workspace = get_shared_workspace()

        if not files_to_check:
            return _json({
                "success": True,
                "path": str(target_path),
                "total_files": 0,
                "error_count": 0,
                "warning_count": 0,
                "message": "No TwinCAT source files found to validate.",
                "diagnostics": [],
            })

        for f in files_to_check:
            workspace.update_file(f)

        diagnostics_list = []
        error_count = 0
        warning_count = 0

        for f in files_to_check:
            indexed = workspace.get_file(f)
            if not indexed:
                continue

            file_diags = list(indexed.diagnostics)
            semantic_diags = run_semantic_analysis(workspace, f)
            file_diags.extend(semantic_diags)

            for d in file_diags:
                sev_str = "error" if d.severity == DiagnosticSeverity.ERROR else (
                    "warning" if d.severity == DiagnosticSeverity.WARNING else "info"
                )
                if sev_str == "error":
                    error_count += 1
                elif sev_str == "warning":
                    warning_count += 1
                    if not include_warnings:
                        continue
                elif not include_warnings:
                    continue

                line_num = d.span.start.line if d.span else 1
                col_num = d.span.start.col if d.span else 1

                diagnostics_list.append({
                    "file": f.name,
                    "path": str(f),
                    "line": line_num,
                    "column": col_num,
                    "severity": sev_str,
                    "code": d.code or "TC-SYNTAX",
                    "message": d.message,
                })

        return _json({
            "success": error_count == 0,
            "path": str(target_path),
            "total_files": len(files_to_check),
            "error_count": error_count,
            "warning_count": warning_count,
            "diagnostics": diagnostics_list,
        })
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


def register_tools(mcp: Any) -> None:
    """Register core syntax and symbol tools on FastMCP server."""
    mcp.tool()(twincat_plcproj_info)
    mcp.tool()(twincat_workspace_symbols)
    mcp.tool()(twincat_symbol_lookup)
    mcp.tool()(twincat_check_syntax)
