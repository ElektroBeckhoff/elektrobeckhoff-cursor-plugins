"""Path discovery and resolution for InfoSys MSHC archives and caches."""

import glob as _glob
import os
import tempfile
from typing import List, Optional, Tuple

from infosys_mshc.constants import (
    HELPLIB_ROOTS,
    LANG_FOLDER,
    MSHC_PATTERN,
)


def discover_mshc(lang_folder: str) -> Optional[str]:
    """Auto-discover the newest BKINFOSYS3 .mshc for a language.

    Searches all VisualStudio* catalogs, picks the file with the highest
    version number so it works across VS shells (12/15/16/17) and InfoSys
    update versions (.9, .10, .11, ...).
    """
    candidates: List[Tuple[int, str]] = []
    pattern = MSHC_PATTERN.format(lang_folder=lang_folder)
    for root in HELPLIB_ROOTS:
        if not os.path.isdir(root):
            continue
        search = os.path.join(
            root, "VisualStudio*", "ContentStore", lang_folder, pattern
        )
        for path in _glob.glob(search):
            try:
                base = os.path.splitext(os.path.basename(path))[0]
                ver = int(base.rsplit(".", 1)[-1])
            except (ValueError, IndexError):
                ver = 0
            candidates.append((ver, path))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


_discover_mshc = discover_mshc


def default_mshc_path() -> str:
    """Return the best available EN-US MSHC path, with fallback to legacy."""
    found = discover_mshc("EN-US")
    if found:
        return found
    return os.path.join(
        HELPLIB_ROOTS[0],
        "VisualStudio15",
        "ContentStore",
        "EN-US",
        "BKINFOSYS3_VS_100_EN-US.9.mshc",
    )


_default_mshc_path = default_mshc_path

DEFAULT_MSHC_PATH = default_mshc_path()


def resolve_mshc_path(language: str = "en", file_path: str = "") -> str:
    """Resolve the .mshc file path from language code or explicit path."""
    if file_path:
        return file_path
    lang = language.lower().strip()
    lang_folder = LANG_FOLDER.get(lang, "EN-US")
    found = discover_mshc(lang_folder)
    if found:
        return found
    return DEFAULT_MSHC_PATH


def get_cache_dir() -> str:
    """Return path to the temporary cache directory for InfoSys FTS5 DBs."""
    d = os.path.join(tempfile.gettempdir(), "twincat-mcp-infosys-mshc")
    os.makedirs(d, exist_ok=True)
    return d


_cache_dir = get_cache_dir


def fts5_db_path_for(mshc_path: str) -> str:
    """Derive a SQLite FTS5 database path in temp dir, keyed by mshc basename."""
    base = os.path.splitext(os.path.basename(mshc_path))[0]
    return os.path.join(get_cache_dir(), f"_fts5_{base}.db")


_fts5_db_path_for = fts5_db_path_for
