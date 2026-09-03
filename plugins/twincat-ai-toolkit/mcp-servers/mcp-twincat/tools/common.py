"""
Common utility and path resolution functions for TwinCAT MCP Server tools.
"""

from __future__ import annotations

import os
import re
import glob
import json
import xml.etree.ElementTree as ET
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Union

from twincat_plcproj_ops import read_project_info
from twincat_core.constants import (
    DEFAULT_PROJECT_EXCLUDES,
    TOOLKIT_ROOT_DIR,
    _EXCLUDES_LOWER,
    filter_scan_dirnames,
    is_internal_toolkit_path,
    should_skip_dir,
)

_SLN_PROJECT_RE = re.compile(
    r'^Project\("[^"]*"\)\s*=\s*"[^"]*"\s*,\s*"([^"]+\.tsproj)"',
    re.MULTILINE,
)


def _json(obj: Any) -> str:
    """Serialize an object (including dataclasses) to formatted JSON."""
    if hasattr(obj, "__dataclass_fields__"):
        return json.dumps(asdict(obj), indent=2, ensure_ascii=False)
    return json.dumps(obj, indent=2, ensure_ascii=False)


def _as_dict(obj: Any) -> dict:
    """Convert dataclass, dict, or scalar object to a dict."""
    if hasattr(obj, "__dataclass_fields__"):
        return asdict(obj)
    if isinstance(obj, dict):
        return dict(obj)
    return {"value": obj}


def _clean_path(p: Any) -> str:
    """Clean and normalize a path string (strips quotes, whitespace, expands vars/user)."""
    if not p:
        return ""
    cleaned = str(p).strip().strip('"').strip("'")
    if not cleaned:
        return ""
    return os.path.expanduser(os.path.expandvars(cleaned))


def _find_repo_root(start_path: str = "") -> str:
    """Find the git repo root by walking upward from start_path."""
    if start_path:
        d = os.path.dirname(start_path) if os.path.isfile(start_path) else start_path
    else:
        d = os.getcwd()
    for _ in range(8):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


def _scan_plcproj_in_dir(dir_path: str) -> List[str]:
    """Walk a directory tree and collect .plcproj files (excluding known noise)."""
    results = []
    dir_path = _clean_path(dir_path)
    if not os.path.isdir(dir_path):
        return results
    for dirpath, dirnames, filenames in os.walk(dir_path):
        filter_scan_dirnames(dirnames, dirpath)
        for f in filenames:
            if f.lower().endswith(".plcproj"):
                cand = os.path.normpath(os.path.join(dirpath, f))
                results.append(cand)
    return results


def _read_proj_name(plcproj_path: str) -> str:
    """Read project name from .plcproj XML."""
    try:
        return read_project_info(plcproj_path).get("name", "")
    except Exception:
        return ""


def _read_plcproj_meta(plcproj_path: str) -> dict:
    """Read structured project metadata from .plcproj XML."""
    if not plcproj_path or not os.path.isfile(plcproj_path):
        return {}
    try:
        info = read_project_info(plcproj_path)
        keys = (
            "title", "version", "company", "name", "released",
            "project_category", "is_library_project", "plcproj_path",
        )
        return {k: info[k] for k in keys if k in info}
    except Exception:
        return {}


def _parse_xti(xti_path: str) -> Optional[Dict[str, str]]:
    """Parse a .xti file -> extract Name and resolve PrjFilePath to absolute."""
    try:
        tree = ET.parse(xti_path)
        root = tree.getroot()
    except Exception:
        return None

    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
    proj = root.find(f"{ns}Project") if ns else root.find("Project")
    if proj is None:
        return None

    name = proj.get("Name", "")
    prj_file_path = proj.get("PrjFilePath", "")
    if not prj_file_path:
        return None

    xti_dir = os.path.dirname(xti_path)
    abs_plcproj = os.path.normpath(os.path.join(xti_dir, prj_file_path))

    if not os.path.isfile(abs_plcproj):
        return None

    return {"name": name, "plcproj_path": abs_plcproj}


def _resolve_tsproj(tsproj_path: str, sln_path: str) -> Union[str, dict]:
    """Parse .tsproj XML -> resolve PLC projects via .xti or inline PrjFilePath."""
    tsproj_dir = os.path.dirname(tsproj_path)
    config_plc_dir = os.path.join(tsproj_dir, "_Config", "PLC")

    try:
        tree = ET.parse(tsproj_path)
        root = tree.getroot()
    except Exception as exc:
        return {"success": False, "error": f"Cannot parse .tsproj: {exc}"}

    ns = root.tag.split("}")[0] + "}" if "}" in root.tag else ""
    plc_node = root.find(f".//{ns}Plc") if ns else root.find(".//Plc")
    if plc_node is None:
        plc_node = root.find(f".//{ns}Project/{ns}Plc") if ns else root.find(".//Project/Plc")
    if plc_node is None:
        return {"success": False, "error": f"No <Plc> section found in {tsproj_path}"}

    projects: List[Dict[str, str]] = []
    for proj_elem in plc_node.findall(f"{ns}Project" if ns else "Project"):
        xti_file = proj_elem.get("File", "")
        if xti_file:
            candidates = [
                os.path.normpath(os.path.join(config_plc_dir, xti_file)),
                os.path.normpath(os.path.join(tsproj_dir, xti_file)),
            ]
            for xti_path in candidates:
                if os.path.isfile(xti_path):
                    info = _parse_xti(xti_path)
                    if info:
                        projects.append(info)
                        break
            if projects:
                continue

        prj_file_path = proj_elem.get("PrjFilePath", "")
        if prj_file_path:
            abs_plcproj = os.path.normpath(
                os.path.join(tsproj_dir, prj_file_path)
            )
            if os.path.isfile(abs_plcproj):
                name = proj_elem.get("Name", "")
                projects.append({"name": name, "plcproj_path": abs_plcproj})

    if len(projects) == 0:
        return {"success": False, "error": f"No PLC projects found in {tsproj_path}"}

    if len(projects) == 1:
        return projects[0]["plcproj_path"]

    return {
        "success": False,
        "error": "multiple_plc_projects",
        "message": (
            f"Found {len(projects)} PLC projects in solution. "
            f"Pass the exact path to the desired .plcproj file."
        ),
        "solution": sln_path,
        "available_projects": projects,
    }


def _resolve_sln(sln_path: str) -> Union[str, dict]:
    """Resolve .sln -> .tsproj -> .xti files -> list of .plcproj entries."""
    sln_path = _clean_path(sln_path)
    sln_dir = os.path.dirname(sln_path)

    try:
        with open(sln_path, "r", encoding="utf-8-sig") as f:
            sln_text = f.read()
    except Exception as exc:
        return {"success": False, "error": f"Cannot read .sln: {exc}"}

    tsproj_matches = _SLN_PROJECT_RE.findall(sln_text)
    if not tsproj_matches:
        return {"success": False, "error": f"No .tsproj reference found in {sln_path}"}

    tsproj_path = os.path.normpath(os.path.join(sln_dir, tsproj_matches[0]))
    if not os.path.isfile(tsproj_path):
        return {"success": False, "error": f".tsproj not found: {tsproj_path}"}

    return _resolve_tsproj(tsproj_path, sln_path)


def _resolve_directory(dir_path: str) -> Union[str, dict]:
    """Resolve a directory by scanning for .sln, then falling back to .plcproj."""
    dir_path = _clean_path(dir_path)
    if not os.path.isdir(dir_path):
        return {"success": False, "error": f"Directory not found: {dir_path}"}

    sln_files = glob.glob(os.path.join(dir_path, "*.sln"))
    if not sln_files:
        # Check direct subdirectories for .sln
        try:
            for entry in os.scandir(dir_path):
                if entry.is_dir() and entry.name.lower() not in _EXCLUDES_LOWER:
                    sub_slns = glob.glob(os.path.join(entry.path, "*.sln"))
                    sln_files.extend(sub_slns)
        except OSError:
            pass

    if len(sln_files) == 1:
        return _resolve_sln(sln_files[0])
    if len(sln_files) > 1:
        return {
            "success": False,
            "error": "multiple_solutions",
            "message": (
                f"Found {len(sln_files)} .sln files in {dir_path}. "
                f"Pass the exact .sln or .plcproj path."
            ),
            "available_solutions": [os.path.normpath(s) for s in sorted(sln_files)],
        }

    plcproj_files = _scan_plcproj_in_dir(dir_path)
    if len(plcproj_files) == 1:
        return plcproj_files[0]
    if len(plcproj_files) > 1:
        projects = []
        for p in plcproj_files:
            name = _read_proj_name(p) or os.path.splitext(os.path.basename(p))[0]
            projects.append({"name": name, "plcproj_path": p})
        return {
            "success": False,
            "error": "multiple_plc_projects",
            "message": (
                f"Found {len(plcproj_files)} .plcproj files in {dir_path}. "
                f"Pass the exact .plcproj path."
            ),
            "available_projects": projects,
        }

    return {"success": False, "error": f"No .sln or .plcproj found in {dir_path}"}


def _resolve_path(path: str) -> Union[str, dict]:
    """Resolve a user-supplied path to an absolute .plcproj path.

    Accepts:
      - A .plcproj file   -> returned as-is (normalised)
      - A .sln file       -> XML chain: .sln -> .tsproj -> .xti -> .plcproj
      - A directory       -> scan for .sln first, then .plcproj

    Returns either a plcproj path (str) or an error dict.
    """
    path = _clean_path(path)
    if not path:
        return {"success": False, "error": "Path is empty"}
    path = os.path.abspath(path)
    lower = path.lower()

    if lower.endswith(".plcproj"):
        if not os.path.isfile(path):
            return {"success": False, "error": f"File not found: {path}"}
        return path

    if lower.endswith(".sln"):
        if not os.path.isfile(path):
            return {"success": False, "error": f"File not found: {path}"}
        return _resolve_sln(path)

    if os.path.isdir(path):
        return _resolve_directory(path)

    return {"success": False, "error": f"Path is not a .plcproj, .sln, or directory: {path}"}


def _auto_detect_plcproj(sln_path: str = "", bridge_sln_getter: Any = None) -> str:
    """Find the first .plcproj file near the solution, active bridge, or git repo root."""
    search_roots: list[str] = []
    sln_path = _clean_path(sln_path)
    explicit_sln = bool(sln_path) and os.path.isfile(sln_path) and sln_path.lower().endswith((".sln", ".tsproj"))
    if sln_path:
        sln_dir = os.path.dirname(sln_path) if os.path.isfile(sln_path) else sln_path
        if os.path.isdir(sln_dir) and (explicit_sln or not is_internal_toolkit_path(sln_dir)):
            search_roots.append(sln_dir)
        repo = _find_repo_root(sln_path)
        if repo and repo != sln_dir and os.path.isdir(repo) and (explicit_sln or not is_internal_toolkit_path(repo)):
            search_roots.append(repo)
    if not search_roots and not bridge_sln_getter:
        try:
            from .solution import _get_bridge
            b = _get_bridge()
            if b:
                bridge_sln_getter = lambda: b._call_sta(lambda: b._sln_path, timeout=2)
        except Exception:
            pass
    if not search_roots and bridge_sln_getter:
        try:
            b_sln = bridge_sln_getter() or ""
            b_sln = _clean_path(b_sln)
            if b_sln and os.path.isfile(b_sln):
                b_dir = os.path.dirname(b_sln)
                if os.path.isdir(b_dir):
                    search_roots.append(b_dir)
                b_repo = _find_repo_root(b_sln)
                if b_repo and b_repo != b_dir and os.path.isdir(b_repo):
                    search_roots.append(b_repo)
                explicit_sln = True
        except Exception:
            pass

    if not search_roots:
        cwd = os.getcwd()
        if not is_internal_toolkit_path(cwd):
            search_roots.append(cwd)

    for root_dir in search_roots:
        if not os.path.isdir(root_dir) or (not explicit_sln and is_internal_toolkit_path(root_dir)):
            continue
        for dirpath, dirnames, filenames in os.walk(root_dir):
            filter_scan_dirnames(dirnames, dirpath, exclude_internal_toolkit=not explicit_sln)
            for f in filenames:
                if f.lower().endswith(".plcproj"):
                    cand = os.path.abspath(os.path.join(dirpath, f))
                    if explicit_sln or not is_internal_toolkit_path(cand):
                        return cand
    return ""


def _resolve_plcproj_path(
    plcproj_path: str = "",
    sln_path: str = "",
    plcproj_from_bridge: str = "",
    bridge_sln_getter: Any = None,
) -> str:
    """Resolve .plcproj path with strict priority:
    1. Explicit non-empty parameter (absolute, relative, or basename).
    2. Active XAE session (plcproj_from_bridge or search in active solution dir).
    3. Auto-detection near sln_path or cwd.
    """
    plcproj_path = _clean_path(plcproj_path)
    sln_path = _clean_path(sln_path)
    plcproj_from_bridge = _clean_path(plcproj_from_bridge)

    if not plcproj_from_bridge:
        try:
            from .solution import _get_bridge
            b = _get_bridge()
            if b:
                plcproj_from_bridge = _clean_path(
                    b._call_sta(lambda: b._plcproj_file_path, timeout=2) or ""
                )
                if not sln_path:
                    sln_path = _clean_path(
                        b._call_sta(lambda: b._sln_path, timeout=2) or ""
                    )
        except Exception:
            pass

    explicit_sln = bool(sln_path) and os.path.isfile(sln_path) and sln_path.lower().endswith((".sln", ".tsproj"))
    if plcproj_path:
        raw = plcproj_path
        if os.path.isabs(raw) and os.path.isfile(raw):
            return os.path.abspath(os.path.normpath(raw))

        # Check relative paths
        candidates = []
        if sln_path:
            sln_dir = os.path.dirname(sln_path) if os.path.isfile(sln_path) else sln_path
            candidates.append(os.path.join(sln_dir, raw))
            repo = _find_repo_root(sln_path)
            if repo and repo != sln_dir:
                candidates.append(os.path.join(repo, raw))
        candidates.append(os.path.join(os.getcwd(), raw))
        candidates.append(os.path.abspath(raw))
        for c in candidates:
            if os.path.isfile(c) and (explicit_sln or not is_internal_toolkit_path(c)):
                return os.path.abspath(os.path.normpath(c))

        # Check basename match
        base_name = raw if raw.lower().endswith(".plcproj") else f"{raw}.plcproj"
        search_dirs = []
        if sln_path:
            sln_dir = os.path.dirname(sln_path) if os.path.isfile(sln_path) else sln_path
            if os.path.isdir(sln_dir) and (explicit_sln or not is_internal_toolkit_path(sln_dir)):
                search_dirs.append(sln_dir)
            repo = _find_repo_root(sln_path)
            if repo and repo not in search_dirs and os.path.isdir(repo) and (explicit_sln or not is_internal_toolkit_path(repo)):
                search_dirs.append(repo)
        if not search_dirs:
            cwd = os.getcwd()
            if not is_internal_toolkit_path(cwd):
                search_dirs.append(cwd)

        for sdir in search_dirs:
            if not os.path.isdir(sdir) or (not explicit_sln and is_internal_toolkit_path(sdir)):
                continue
            for dirpath, dirnames, files in os.walk(sdir):
                filter_scan_dirnames(dirnames, dirpath, exclude_internal_toolkit=not explicit_sln)
                for f in files:
                    if f.lower() == base_name.lower():
                        cand = os.path.abspath(os.path.join(dirpath, f))
                        if explicit_sln or not is_internal_toolkit_path(cand):
                            return cand

    # Priority 2: Active bridge session
    if plcproj_from_bridge and os.path.isfile(plcproj_from_bridge):
        return os.path.abspath(os.path.normpath(plcproj_from_bridge))

    # Priority 3: Auto-detect from sln_path or bridge
    if sln_path:
        found = _auto_detect_plcproj(sln_path, bridge_sln_getter=bridge_sln_getter)
        if found:
            return found

    return _auto_detect_plcproj("", bridge_sln_getter=bridge_sln_getter)
