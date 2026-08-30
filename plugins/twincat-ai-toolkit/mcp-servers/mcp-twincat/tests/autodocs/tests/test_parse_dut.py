"""Unit tests for parse_tcDut."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodocs.parsers.dut import parse_tcDut
from autodocs.type_index import build_type_index

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"


@pytest.fixture
def type_index():
    return build_type_index(RAW)


def test_dut_enum(type_index, tmp_path):
    result = parse_tcDut(RAW / "dut_Enum.TcDUT", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "## Enum" in result["sections"]["DUT"]


def test_dut_struct(type_index, tmp_path):
    result = parse_tcDut(RAW / "dut_Struct.TcDUT", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "## Struct" in result["sections"]["DUT"]


def test_dut_union(type_index, tmp_path):
    result = parse_tcDut(RAW / "dut_Union.TcDUT", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "## Union" in result["sections"]["DUT"]


def test_dut_hidden_returns_none(type_index, tmp_path):
    assert parse_tcDut(RAW / "dut_Hidden.TcDUT", type_index, tmp_path / "out.md", tmp_path) is None
