"""Centralized sys.path configuration for all test modules."""
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
for _subdir in ("migrator", "automation_interface", "plcproj"):
    _p = str(_root / _subdir)
    if _p not in sys.path:
        sys.path.insert(0, _p)
