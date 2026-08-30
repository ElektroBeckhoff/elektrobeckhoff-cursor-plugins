"""Canonical formatter gate: collapse(golden) -> format == golden.

Collapses all ST implementation CDATA blocks to compressed one-liners
(preserving blank lines as structural separators), then formats and
asserts the result is byte-identical to the original golden.

This is the acceptance test for the canonical ST formatter (Fixpunkt):
any input, no matter how compressed, must produce the same golden output.

Declaration CDATA is left intact (blank-line alignment groups and
attribute-pragma annotations are context-dependent).
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest

_MCP_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_MCP_ROOT))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter"))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter" / "scripts"))

from formatter.config import load_config
from formatter.file_processor import process_file
from verify_raw_golden_byte_match import GOLDEN_DIR
from verify_4gate_fixpoint import _collapse_and_encode

CONFIG = load_config()


def _format_collapsed(golden_path: Path) -> tuple[bytes, bytes]:
    """Return (formatted_collapsed, golden_bytes) for comparison."""
    golden_bytes = golden_path.read_bytes()
    payload = _collapse_and_encode(golden_bytes)

    with tempfile.NamedTemporaryFile(suffix=golden_path.suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        tmp_path.write_bytes(payload)
        result = process_file(
            str(tmp_path), CONFIG,
            dry_run=False, sort_xml=True, validate=False,
        )
        if not result.success:
            raise RuntimeError(f"format failed: {result.errors}")
        return tmp_path.read_bytes(), golden_bytes
    finally:
        tmp_path.unlink(missing_ok=True)


def _collect_fixtures() -> list[pytest.param]:
    params: list[pytest.param] = []
    if GOLDEN_DIR.is_dir():
        for ext in ("*.TcPOU", "*.TcDUT", "*.TcGVL", "*.TcIO"):
            for f in sorted(GOLDEN_DIR.rglob(ext)):
                rel = f.relative_to(GOLDEN_DIR).as_posix()
                params.append(pytest.param(rel, id=f.name))
    return params


@pytest.mark.parametrize("rel_path", _collect_fixtures())
def test_collapse_then_format_matches_golden(rel_path: str):
    """format(collapse(golden)) must equal golden byte-for-byte."""
    rel = rel_path.replace("/", "\\") if sys.platform == "win32" else rel_path
    golden_path = GOLDEN_DIR / rel
    if not golden_path.is_file():
        pytest.skip(f"Golden not found: {golden_path}")

    formatted, expected = _format_collapsed(golden_path)
    if formatted == expected:
        return

    got_lines = formatted.decode("utf-8-sig", errors="replace").splitlines()
    exp_lines = expected.decode("utf-8-sig", errors="replace").splitlines()
    diffs: list[str] = []
    for i, (g, e) in enumerate(zip(got_lines, exp_lines), 1):
        if g != e:
            diffs.append(f"L{i} got: {g!r}")
            diffs.append(f"L{i} exp: {e!r}")
            if len(diffs) >= 20:
                break
    if len(got_lines) != len(exp_lines):
        diffs.append(f"line count: got={len(got_lines)} exp={len(exp_lines)}")

    pytest.fail(
        f"collapse->format != golden for {golden_path.name}\n"
        + "\n".join(diffs[:20])
    )
