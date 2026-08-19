"""Ensure ``migrator/`` on sys.path does not shadow stdlib ``types``."""
from __future__ import annotations

import importlib
import os
import sys

_MIGRATOR_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_MIGRATOR_DIR)
_MIGRATOR_DIR_NORM = os.path.normcase(os.path.normpath(_MIGRATOR_DIR))


def _path_matches_migrator(entry: str) -> bool:
    if not entry:
        return False
    candidate = os.path.normcase(os.path.normpath(os.path.join(_ROOT_DIR, entry)))
    if candidate == _MIGRATOR_DIR_NORM:
        return True
    return os.path.normcase(os.path.normpath(entry)) == _MIGRATOR_DIR_NORM


def setup_migrator_paths() -> None:
    """Configure sys.path for package imports and legacy flat module names."""
    sys.path[:] = [p for p in sys.path if not _path_matches_migrator(p)]
    if _ROOT_DIR not in sys.path:
        sys.path.insert(0, _ROOT_DIR)

    # Lock stdlib ``types`` in sys.modules before migrator/ is re-added.
    importlib.import_module("types")
    importlib.import_module("migrator.types")

    if _MIGRATOR_DIR not in sys.path:
        sys.path.insert(0, _MIGRATOR_DIR)


setup_migrator_paths()
