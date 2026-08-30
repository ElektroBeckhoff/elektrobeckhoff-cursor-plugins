"""Golden-file tests: raw TwinCAT sources -> autodocs markdown == golden."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autodocs.markdown import write_or_update_markdown
from autodocs.parsers.dut import parse_tcDut
from autodocs.parsers.gvl import parse_tcGvl
from autodocs.parsers.itf import parse_tcItf
from autodocs.parsers.pou import parse_tcPou
from autodocs.type_index import build_type_index

RAW_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden"

_PARSERS = {
    ".TcPOU": parse_tcPou,
    ".TcIO": parse_tcItf,
    ".TcDUT": parse_tcDut,
    ".TcGVL": parse_tcGvl,
}

_RAW_FILES = sorted(
    p
    for p in RAW_DIR.iterdir()
    if p.suffix in _PARSERS
    and p.is_file()
    and not p.name.endswith(("_Base.TcPOU", "_Base.TcIO", "_Base.TcDUT"))
)

_RE_TIMESTAMP = re.compile(
    r"_Automatically generated on \d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_"
)
_RE_SOURCE_LINK = re.compile(
    r"Source: \[`([^`]+)`\]\(<[^>]+>\)"
)


def _normalise(text: str) -> str:
    text = _RE_TIMESTAMP.sub("_Automatically generated on TIMESTAMP_", text)
    text = _RE_SOURCE_LINK.sub(r"Source: [`\1`](<FILENAME>)", text)
    return text


def _render_raw(raw_file: Path, tmp_path: Path) -> str | None:
    type_index = build_type_index(RAW_DIR)
    parser = _PARSERS[raw_file.suffix]
    docs_root = tmp_path / "docs"
    out_file = docs_root / (raw_file.stem + ".md")
    parsed = parser(raw_file, type_index, out_file, docs_root)
    if parsed is None:
        return None
    out_file.parent.mkdir(parents=True, exist_ok=True)
    write_or_update_markdown(out_file, parsed["title"], parsed["sections"])
    return out_file.read_text(encoding="utf-8")


@pytest.mark.parametrize("raw_file", _RAW_FILES, ids=[f.stem for f in _RAW_FILES])
def test_autodocs_golden(raw_file: Path, tmp_path: Path):
    golden = GOLDEN_DIR / (raw_file.stem + ".md")
    if raw_file.name.endswith("_Hidden.TcPOU") or raw_file.name.endswith("_Hidden.TcDUT") or raw_file.name.endswith("_Hidden.TcGVL"):
        assert parser_result_is_none(raw_file, tmp_path)
        assert not golden.exists(), f"Hidden fixture should not have golden: {golden.name}"
        return

    assert golden.exists(), f"Missing golden file: {golden.name}"
    actual = _render_raw(raw_file, tmp_path)
    assert actual is not None
    expected = golden.read_text(encoding="utf-8")
    assert _normalise(actual) == _normalise(expected), f"Golden mismatch: {raw_file.name}"


def parser_result_is_none(raw_file: Path, tmp_path: Path) -> bool:
    type_index = build_type_index(RAW_DIR)
    parser = _PARSERS[raw_file.suffix]
    out_file = tmp_path / (raw_file.stem + ".md")
    return parser(raw_file, type_index, out_file, tmp_path) is None
