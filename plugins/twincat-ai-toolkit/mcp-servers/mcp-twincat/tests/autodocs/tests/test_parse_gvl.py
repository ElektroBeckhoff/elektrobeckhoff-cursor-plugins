"""Unit tests for parse_tcGvl."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodocs.parsers.gvl import parse_tcGvl
from autodocs.type_index import build_type_index

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"


@pytest.fixture
def type_index():
    return build_type_index(RAW)


def test_gvl_basic(type_index, tmp_path):
    result = parse_tcGvl(RAW / "gvl_Basic.TcGVL", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "### Variables" in result["sections"]["GVL"]
    assert "### Constants" in result["sections"]["GVL"]


def test_gvl_hidden_returns_none(type_index, tmp_path):
    assert parse_tcGvl(RAW / "gvl_Hidden.TcGVL", type_index, tmp_path / "out.md", tmp_path) is None
