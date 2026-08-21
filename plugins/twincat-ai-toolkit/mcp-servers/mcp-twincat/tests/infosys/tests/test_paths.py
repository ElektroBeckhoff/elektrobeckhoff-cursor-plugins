"""Unit tests for infosys_mshc.paths module."""

import os
import pytest
from infosys_mshc.paths import (
    DEFAULT_MSHC_PATH,
    default_mshc_path,
    discover_mshc,
    fts5_db_path_for,
    get_cache_dir,
    resolve_mshc_path,
)


def test_get_cache_dir():
    cache_dir = get_cache_dir()
    assert os.path.isdir(cache_dir)
    assert "twincat-mcp-infosys-mshc" in cache_dir


def test_fts5_db_path_for():
    db_path = fts5_db_path_for(r"C:\test\folder\BKINFOSYS3_VS_100_EN-US.10.mshc")
    assert db_path.endswith("_fts5_BKINFOSYS3_VS_100_EN-US.10.db")
    assert os.path.dirname(db_path) == get_cache_dir()


def test_resolve_mshc_path_explicit():
    explicit = r"C:\custom\path\custom.mshc"
    resolved = resolve_mshc_path(file_path=explicit)
    assert resolved == explicit


def test_resolve_mshc_path_default():
    resolved_en = resolve_mshc_path(language="en")
    assert resolved_en is not None
    assert resolved_en.endswith(".mshc")


def test_discover_mshc_nonexistent():
    res = discover_mshc("NON_EXISTENT_LANG_XYZ")
    assert res is None


def test_default_mshc_path_returns_string():
    path = default_mshc_path()
    assert isinstance(path, str)
    assert path.endswith(".mshc")
    assert DEFAULT_MSHC_PATH == path
