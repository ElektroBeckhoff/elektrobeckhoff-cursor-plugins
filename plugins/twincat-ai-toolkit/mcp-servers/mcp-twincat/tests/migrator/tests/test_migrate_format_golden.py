"""Golden-file tests: raw FBD/CFC -> migrate -> format == golden.

Each raw fixture in fixtures/migrator/raw/ is migrated to ST, then
formatted by the ST formatter.  The result is compared against the
corresponding golden file in fixtures/migrator/golden/ (with GUIDs
and timestamps normalised so tests stay deterministic).

To regenerate golden files after intentional changes:
    python tests/_generate_golden.py
"""

import sys
import os
import re
import shutil
import io
import contextlib

import pytest
from pathlib import Path

from migrator.fbd import main as fup_main
from migrator.cfc import main as cfc_main
from formatter.config import load_config
from formatter.file_processor import process_batch

RAW_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden"

_RAW_FILES = sorted(RAW_DIR.glob("*.TcPOU"))


def _migrate(src: Path, dst: Path) -> int:
    name_lower = src.name.lower()
    main_fn = cfc_main if name_lower.startswith("cfc_") else fup_main
    argv = [
        "--input", str(src),
        "--output", str(dst),
        "--no-log", "--no-report", "--no-backup",
    ]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return main_fn(argv)


def _format(path: Path) -> bool:
    cfg = load_config(project_root=str(path.parent))
    cfg.safety.syntax_check = False
    batch = process_batch(
        [str(path)], cfg,
        dry_run=False, validate=True,
        format_st=True, format_xml=True,
        sort_xml=False, scope=None,
    )
    return batch.errors == 0


@pytest.fixture
def work_dir(tmp_path):
    return tmp_path


_RE_GUID = re.compile(r'\{[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\}')
_RE_DATE = re.compile(r'Date:\s+\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')


def _normalise(text: str) -> str:
    """Replace GUIDs and timestamps so comparisons are stable."""
    text = _RE_GUID.sub("{00000000-0000-0000-0000-000000000000}", text)
    text = _RE_DATE.sub("Date:             0000-00-00 00:00:00", text)
    return text


@pytest.mark.parametrize(
    "raw_file",
    _RAW_FILES,
    ids=[f.stem for f in _RAW_FILES],
)
def test_migrate_and_format_matches_golden(raw_file: Path, work_dir: Path):
    golden = GOLDEN_DIR / raw_file.name
    assert golden.exists(), f"Golden file missing: {golden}"

    out_file = work_dir / raw_file.name
    exit_code = _migrate(raw_file, out_file)
    assert exit_code == 0, f"Migration failed for {raw_file.name}"
    assert out_file.exists()

    fmt_ok = _format(out_file)
    assert fmt_ok, f"Formatting failed for {raw_file.name}"

    actual = _normalise(out_file.read_text(encoding="utf-8-sig"))
    expected = _normalise(golden.read_text(encoding="utf-8-sig"))

    if actual != expected:
        _write_diff(raw_file.name, expected, actual)
        pytest.fail(
            f"{raw_file.name}: migrated+formatted output differs from golden.\n"
            f"Re-run: python tests/_generate_golden.py"
        )


def _write_diff(name: str, expected: str, actual: str):
    """Print a unified diff for easier debugging."""
    import difflib
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile=f"golden/{name}",
        tofile=f"actual/{name}",
        n=3,
    )
    sys.stderr.write("".join(diff)[:5000])
