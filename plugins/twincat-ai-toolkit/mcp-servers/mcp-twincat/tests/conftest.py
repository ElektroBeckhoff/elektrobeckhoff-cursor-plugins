"""Centralized sys.path configuration for all test modules."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))

from migrator._bootstrap import setup_migrator_paths  # noqa: E402

setup_migrator_paths()

# Flat-module subdirs (not migrator — handled by setup_migrator_paths).
for _subdir in (
    "automation_interface",
    "plcproj",
    "infosys_mshc",
    "ads",
    "umrt",
    "systemtest",
    "formatter",
):
    _p = str(_root / _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)
