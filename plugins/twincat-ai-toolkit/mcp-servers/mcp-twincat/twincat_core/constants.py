"""
Central constants and path helpers for twincat_core and TwinCAT 3 tooling.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Set, Union

# Root directory of the TwinCAT AI toolkit plugin
TOOLKIT_ROOT_DIR: Path = Path(__file__).resolve().parents[2]

# Standard directory names excluded during project and source discovery
DEFAULT_PROJECT_EXCLUDES: frozenset[str] = frozenset({
    ".git",
    ".github",
    "node_modules",
    "_libraries",
    "_compileinfo",
    "versions",
    "samples",
    "samples_",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    ".cursor",
    "bin",
    "obj",
})

# Backward compatibility alias
_EXCLUDES_LOWER: Set[str] = set(DEFAULT_PROJECT_EXCLUDES)


def is_internal_toolkit_path(p: Union[str, Path]) -> bool:
    """Check if a path is located inside the internal toolkit/plugin directory (e.g. test fixtures, test solutions)."""
    try:
        target = Path(p).resolve()
        if TOOLKIT_ROOT_DIR in target.parents or target == TOOLKIT_ROOT_DIR:
            return True
        norm = str(target).replace("\\", "/").lower()
        if "/plugins/twincat-ai-toolkit" in norm or "/mcp-servers/mcp-twincat/" in norm:
            return True
        return False
    except Exception:
        return False


def should_skip_dir(
    dir_name: str,
    dir_path: Optional[Union[str, Path]] = None,
    *,
    exclude_internal_toolkit: bool = False,
) -> bool:
    """Check if a directory should be skipped during TwinCAT project and source discovery."""
    d_lower = dir_name.lower()
    if d_lower in DEFAULT_PROJECT_EXCLUDES or d_lower.startswith(".pytest"):
        return True
    if exclude_internal_toolkit and dir_path is not None:
        return is_internal_toolkit_path(dir_path)
    return False


def filter_scan_dirnames(
    dirnames: list[str],
    current_dirpath: Optional[Union[str, Path]] = None,
    *,
    exclude_internal_toolkit: bool = False,
) -> None:
    """In-place filter for os.walk dirnames list to eliminate excluded and optionally internal toolkit directories."""
    filtered = []
    base = Path(current_dirpath) if current_dirpath else None
    for d in dirnames:
        p = (base / d) if (base and exclude_internal_toolkit) else None
        if not should_skip_dir(d, p, exclude_internal_toolkit=exclude_internal_toolkit):
            filtered.append(d)
    dirnames[:] = filtered
