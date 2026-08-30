"""Unit tests for parse_tcItf."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodocs.parsers.itf import parse_tcItf
from autodocs.type_index import build_type_index

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"


@pytest.fixture
def type_index():
    return build_type_index(RAW)


def test_itf_basic(type_index, tmp_path):
    result = parse_tcItf(RAW / "itf_Basic.TcIO", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "## Methods" in result["sections"]["METHODS"]
    assert "## Properties" in result["sections"]["PROPERTIES"]


def test_itf_extends(type_index, tmp_path):
    result = parse_tcItf(RAW / "itf_Extends.TcIO", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "Extends" in result["sections"]["SIGNATURE"]
