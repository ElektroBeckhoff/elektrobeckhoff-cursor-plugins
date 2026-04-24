"""
TwinCAT MCP Server for Cursor IDE.

Exposes TcXaeShell build automation as MCP tools that Cursor can call
directly: status check, solution open, CheckAllObjects, build, error
retrieval, library export, and close.

Transport: stdio  (Cursor starts this process as a child)
COM:       All TcXaeShell interaction runs on a dedicated STA thread
           managed by com_bridge.ComBridge.
"""

import os
import sys
import json
import logging
import xml.etree.ElementTree as ET
from typing import Optional
from dataclasses import asdict

# stdout is the MCP JSON-RPC wire -- all logging goes to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("twincat-mcp")

from mcp.server.fastmcp import FastMCP
from com_bridge import ComBridge, HAS_WIN32

mcp = FastMCP("TwinCAT")

_bridge: Optional[ComBridge] = None


def _get_bridge() -> ComBridge:
    global _bridge
    if _bridge is None:
        _bridge = ComBridge()
    return _bridge


def _json(obj) -> str:
    if hasattr(obj, "__dataclass_fields__"):
        return json.dumps(asdict(obj), indent=2, ensure_ascii=False)
    return json.dumps(obj, indent=2, ensure_ascii=False)


# ================================================================
#  twincat_project_info  (pure XML -- no COM / no XAE needed)
# ================================================================

@mcp.tool()
def twincat_project_info(plcproj_path: str = "") -> str:
    """Read TwinCAT PLC project metadata from .plcproj XML.

    Returns Title, Version, Company, Name, Released.
    Does NOT require a running TcXaeShell instance.
    Leave plcproj_path empty for auto-detection."""

    if not plcproj_path:
        plcproj_path = _auto_detect_plcproj()
        if not plcproj_path:
            return _json({"error": "No .plcproj found. Provide plcproj_path."})

    if not os.path.isfile(plcproj_path):
        return _json({"error": f"File not found: {plcproj_path}"})

    try:
        tree = ET.parse(plcproj_path)
        ns = {"ms": "http://schemas.microsoft.com/developer/msbuild/2003"}

        def txt(xpath: str) -> str:
            el = tree.getroot().find(xpath, ns)
            return el.text.strip() if el is not None and el.text else ""

        title = txt(".//ms:Title") or txt(".//ms:Name")
        version = txt(".//ms:ProjectVersion") or "0.0.0.0"

        return _json({
            "title": title,
            "version": version,
            "company": txt(".//ms:Company"),
            "name": txt(".//ms:Name"),
            "released": txt(".//ms:Released"),
            "plcproj_path": plcproj_path,
        })
    except Exception as exc:
        return _json({"error": str(exc)})


# ================================================================
#  twincat_status
# ================================================================

@mcp.tool()
def twincat_status() -> str:
    """Check whether TcXaeShell (TwinCAT XAE) is installed and running.

    Returns availability info without opening anything."""

    if not HAS_WIN32:
        return _json({
            "xae_available": False,
            "running_instance": False,
            "message": "pywin32 not installed (Windows + TwinCAT XAE required)",
        })
    try:
        return _json(_get_bridge().get_status())
    except Exception as exc:
        return _json({"error": str(exc)})


# ================================================================
#  twincat_open
# ================================================================

@mcp.tool()
def twincat_open(
    sln_path: str = "",
    plcproj_path: str = "",
    proj_name: str = "",
    timeout_seconds: int = 180,
    force_switch: bool = False,
) -> str:
    """Open a TwinCAT solution in XAE and locate the PLC project.

    Attaches to a running instance when available, otherwise starts
    a new TcXaeShell.  Searches the XAE project tree for the PLC
    project node (needed by build / check / export tools).

    If a DIFFERENT solution is already open, returns an error with
    details.  Set force_switch=true to close the current solution
    and open the correct one (use with caution -- unsaved changes
    in the current solution will be lost!).

    Leave paths empty for auto-detection."""

    if not plcproj_path:
        plcproj_path = _auto_detect_plcproj()
    if not proj_name and plcproj_path:
        proj_name = _read_proj_name(plcproj_path)

    bridge = _get_bridge()
    bridge._plcproj_file_path = plcproj_path or None

    try:
        return _json(bridge.open_solution(
            sln_path=sln_path or None,
            plcproj_path=plcproj_path or None,
            proj_name=proj_name or None,
            timeout_s=timeout_seconds,
            force_switch=force_switch,
        ))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_reload
# ================================================================

@mcp.tool()
def twincat_reload(timeout_seconds: int = 180) -> str:
    """Reload the TwinCAT solution from disk (close without save, reopen).

    NOT needed after editing .TcPOU / .TcDUT / .TcGVL content --
    twincat_check_all_objects re-reads those from disk automatically.

    REQUIRED after changes to project structure files:
      - .plcproj  (added/removed POUs, version changes, references)
      - .tsproj   (project configuration changes)
      - .sln      (solution-level changes)

    Also useful when XAE is in an inconsistent state, e.g. after
    a failed build left stale data in memory.

    Takes ~5-10 seconds (polls for readiness instead of fixed timer).
    Requires twincat_open to have been called at least once."""

    try:
        return _json(_get_bridge().reload_solution(timeout_s=timeout_seconds))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_check_all_objects
# ================================================================

@mcp.tool()
def twincat_check_all_objects() -> str:
    """Run CheckAllObjects on the open PLC project.

    This is the PRIMARY validation tool for library projects.
    It re-reads files from disk and compiles ALL objects -- not just
    those referenced from MAIN.  A normal Build would miss errors
    in unreferenced POUs.

    Standard workflow after editing PLC code:
      1. twincat_check_all_objects   (validates everything)
      2. twincat_get_errors          (read results)

    No twincat_reload needed -- CheckAllObjects reads from disk.
    Requires twincat_open to have been called."""

    try:
        return _json(_get_bridge().check_all_objects())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_build
# ================================================================

@mcp.tool()
def twincat_build(timeout_seconds: int = 180) -> str:
    """Rebuild the TwinCAT solution.

    Detects PLC compile success via _CompileInfo timestamps
    combined with SolutionBuild.LastBuildInfo.  Returns structured
    success/failure info.

    Requires twincat_open to have been called."""

    try:
        return _json(_get_bridge().build(timeout_s=timeout_seconds))
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_get_errors
# ================================================================

@mcp.tool()
def twincat_get_errors() -> str:
    """Read the full build / check output from XAE.

    Returns structured JSON with three severity lists:
      - errors:   compile errors (with file_name, line, description)
      - warnings: compiler warnings (with file_name, line, description)
      - infos:    build messages (memory sizes, phases, summary)

    Each entry has: severity, description, file_name, line, project.
    'count' is the number of ERRORS only.

    Use after twincat_build or twincat_check_all_objects.
    The infos list is useful for monitoring build progress,
    memory usage, and debugging sample projects live."""

    try:
        return _json(_get_bridge().get_errors())
    except Exception as exc:
        return _json({"count": 0, "errors": [], "warnings": [], "infos": [], "error": str(exc)})


# ================================================================
#  twincat_export_library
# ================================================================

@mcp.tool()
def twincat_export_library(
    output_dir: str = "",
    plcproj_path: str = "",
) -> str:
    """Export the PLC project as .library and .compiled-library.

    The .library is also installed into the local library repository.
    Default output: Versions/<ProjectVersion>/ in the repository root.

    Requires a successful build first."""

    if not plcproj_path:
        plcproj_path = _auto_detect_plcproj()

    info = _read_plcproj_meta(plcproj_path)
    title = info.get("title", "Unknown")
    version = info.get("version", "0.0.0.0")

    if not output_dir:
        repo = _find_repo_root()
        output_dir = os.path.join(repo or os.getcwd(), "Versions", version)

    try:
        return _json(
            _get_bridge().export_library(output_dir, title, version)
        )
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  twincat_close
# ================================================================

@mcp.tool()
def twincat_close() -> str:
    """Close the TwinCAT solution and release COM resources.

    Only closes instances that were started by this MCP server.
    Instances that were already running are left untouched."""

    try:
        return _json(_get_bridge().close())
    except Exception as exc:
        return _json({"success": False, "error": str(exc)})


# ================================================================
#  Internal helpers
# ================================================================

def _auto_detect_plcproj() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(os.path.dirname(script_dir))

    excludes = {"samples", "versions", "_libraries", ".git", "node_modules"}

    for root_dir in (repo_root, os.getcwd()):
        if not os.path.isdir(root_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(root_dir):
            parts = set(p.lower() for p in dirpath.split(os.sep))
            if parts & excludes:
                dirnames.clear()
                continue
            depth = dirpath.replace(root_dir, "").count(os.sep)
            if depth > 5:
                dirnames.clear()
                continue
            for f in filenames:
                if f.endswith(".plcproj"):
                    return os.path.join(dirpath, f)
    return ""


def _read_proj_name(plcproj_path: str) -> str:
    try:
        ns = {"ms": "http://schemas.microsoft.com/developer/msbuild/2003"}
        el = ET.parse(plcproj_path).getroot().find(".//ms:Name", ns)
        return el.text.strip() if el is not None and el.text else ""
    except Exception:
        return ""


def _read_plcproj_meta(plcproj_path: str) -> dict:
    if not plcproj_path or not os.path.isfile(plcproj_path):
        return {}
    try:
        tree = ET.parse(plcproj_path)
        ns = {"ms": "http://schemas.microsoft.com/developer/msbuild/2003"}

        def txt(xp: str) -> str:
            el = tree.getroot().find(xp, ns)
            return el.text.strip() if el is not None and el.text else ""

        return {
            "title": txt(".//ms:Title") or txt(".//ms:Name"),
            "version": txt(".//ms:ProjectVersion") or "0.0.0.0",
            "company": txt(".//ms:Company"),
            "name": txt(".//ms:Name"),
        }
    except Exception:
        return {}


def _find_repo_root() -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidate = os.path.dirname(os.path.dirname(script_dir))
    if os.path.isdir(os.path.join(candidate, ".git")):
        return candidate
    d = os.getcwd()
    for _ in range(5):
        if os.path.isdir(os.path.join(d, ".git")):
            return d
        d = os.path.dirname(d)
    return ""


# ================================================================
#  Entry point
# ================================================================

if __name__ == "__main__":
    mcp.run()
