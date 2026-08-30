"""Unit tests for parse_tcPou."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodocs.parsers.pou import parse_tcPou
from autodocs.type_index import build_type_index

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"


@pytest.fixture
def type_index():
    return build_type_index(RAW)


def test_pou_basic_sections(type_index, tmp_path):
    result = parse_tcPou(RAW / "pou_FB_Basic.TcPOU", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "INPUT" in result["sections"]
    assert "OUTPUT" in result["sections"]
    assert "IN_OUT" in result["sections"]
    assert "## Description" in result["sections"]["DESCRIPTION"]


def test_pou_methods(type_index, tmp_path):
    result = parse_tcPou(RAW / "pou_FB_Methods.TcPOU", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "## Methods" in result["sections"]["METHODS"]


def test_pou_properties(type_index, tmp_path):
    result = parse_tcPou(RAW / "pou_FB_Properties.TcPOU", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "## Properties" in result["sections"]["PROPERTIES"]


def test_pou_function_return(type_index, tmp_path):
    result = parse_tcPou(RAW / "pou_Func_Return.TcPOU", type_index, tmp_path / "out.md", tmp_path)
    assert result is not None
    assert "RETURN" in result["sections"]


def test_pou_hidden_returns_none(type_index, tmp_path):
    assert parse_tcPou(RAW / "pou_Hidden.TcPOU", type_index, tmp_path / "out.md", tmp_path) is None
