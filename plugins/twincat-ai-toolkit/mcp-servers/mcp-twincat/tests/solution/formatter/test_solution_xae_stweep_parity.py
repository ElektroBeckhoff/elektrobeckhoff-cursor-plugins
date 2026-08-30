"""XAE STweep Golden File parity verification on Solution files."""
from __future__ import annotations

import filecmp
import shutil
import tempfile
from pathlib import Path
import pytest

from formatter.file_processor import process_file
from formatter.config import load_config


_MCP_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_SYNTAX_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures" / "golden" / "syntax"
RAW_SYNTAX_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures" / "raw" / "syntax"
CONFIG = load_config()


class TestSolutionXaeStweepParity:
    """Verifies that Python Formatter matches golden XAE STweep outputs."""

    def test_golden_file_parity_syntax_subset(self):
        if not GOLDEN_SYNTAX_DIR.is_dir() or not RAW_SYNTAX_DIR.is_dir():
            pytest.skip("Golden or raw fixtures dir missing")

        raw_files = list(RAW_SYNTAX_DIR.glob("*.*"))
        tested_count = 0
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            for raw_file in raw_files[:15]:
                golden_file = GOLDEN_SYNTAX_DIR / raw_file.name
                if not golden_file.is_file():
                    continue
                tmp_file = tmp_root / raw_file.name
                shutil.copy2(raw_file, tmp_file)

                res = process_file(str(tmp_file), CONFIG, dry_run=False, sort_xml=True, validate=False)
                assert res.success is True, f"Formatting failed on {raw_file.name}: {res.errors}"

                # Compare formatted output with golden fixture
                assert filecmp.cmp(str(tmp_file), str(golden_file), shallow=False), (
                    f"Byte mismatch against golden for {raw_file.name}"
                )
                tested_count += 1

        assert tested_count >= 5
