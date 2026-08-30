"""Central fixtures and path helpers for real TwinCAT 3 Solution integration tests."""
from __future__ import annotations

from pathlib import Path
from typing import Generator, List
import pytest
from lsprotocol import types as lsp

from twincat_core.project.workspace_index import WorkspaceIndex, get_shared_workspace
from twincat_core.lsp.server import TwinCatLanguageServer


SOLUTION_ROOT = Path(__file__).resolve().parents[4] / "solution" / "twincat3-solution"
SLN_FILE = SOLUTION_ROOT / "twincat3-solution.sln"
TSPROJ_FILE = SOLUTION_ROOT / "twincat3-solution" / "twincat3-solution.tsproj"
PLC_PROJECT_DIR = SOLUTION_ROOT / "twincat3-solution" / "plc-project"
PLCPROJ_FILE = PLC_PROJECT_DIR / "plc-project.plcproj"
SYNTAX_DIR = PLC_PROJECT_DIR / "syntax"
SAMPLES_DIR = PLC_PROJECT_DIR / "samples"
LIBRARIES_DIR = PLC_PROJECT_DIR / "_Libraries"


@pytest.fixture(scope="session")
def solution_paths() -> dict[str, Path]:
    return {
        "solution_root": SOLUTION_ROOT,
        "sln_file": SLN_FILE,
        "tsproj_file": TSPROJ_FILE,
        "plc_proj_dir": PLC_PROJECT_DIR,
        "plcproj_file": PLCPROJ_FILE,
        "syntax_dir": SYNTAX_DIR,
        "samples_dir": SAMPLES_DIR,
        "libraries_dir": LIBRARIES_DIR,
    }


@pytest.fixture(scope="session")
def all_solution_files(solution_paths) -> list[Path]:
    """Returns all TwinCAT XML object files in the real solution."""
    exts = {".tcpou", ".tcdut", ".tcgvl", ".tcio", ".tctto"}
    plc_dir = solution_paths["plc_proj_dir"]
    files = [p for p in plc_dir.rglob("*.*") if p.suffix.lower() in exts]
    assert len(files) >= 50, f"Expected at least 50 solution files, found {len(files)}"
    return sorted(files)


@pytest.fixture(scope="session")
def solution_workspace(solution_paths) -> WorkspaceIndex:
    """Provides a shared WorkspaceIndex initialized from the real solution."""
    ws = get_shared_workspace(solution_paths["plcproj_file"], force_refresh=True)
    return ws


@pytest.fixture(scope="session")
def solution_lsp_server(solution_workspace) -> TwinCatLanguageServer:
    """Provides a TwinCatLanguageServer instance with the solution workspace pre-loaded."""
    srv = TwinCatLanguageServer()
    return srv
