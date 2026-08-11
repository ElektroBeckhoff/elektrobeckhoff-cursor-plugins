"""Path helpers for TwinCAT Automation Interface."""
import os


def _canonical_path(p: str) -> str:
    """Canonical, case-folded absolute path (resolves symlinks, junctions, subst)."""
    try:
        resolved = os.path.realpath(p)
    except (OSError, ValueError):
        resolved = os.path.abspath(p)
    return os.path.normcase(resolved)
