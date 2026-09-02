"""TwinCAT Core Engine - Unified foundation for TwinCAT3 tooling."""
__version__ = "0.1.0"

from . import constants, lsp, project, semantic, syntax, xml
from .constants import (
    DEFAULT_PROJECT_EXCLUDES,
    TOOLKIT_ROOT_DIR,
    filter_scan_dirnames,
    is_internal_toolkit_path,
    should_skip_dir,
)

__all__ = [
    "constants",
    "xml",
    "syntax",
    "semantic",
    "project",
    "lsp",
    "DEFAULT_PROJECT_EXCLUDES",
    "TOOLKIT_ROOT_DIR",
    "is_internal_toolkit_path",
    "should_skip_dir",
    "filter_scan_dirnames",
]
