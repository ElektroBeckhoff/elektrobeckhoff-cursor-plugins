"""Integration tests with real fixture files (auto-discovered from fixtures/golden/)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from formatter.config import load_config
from formatter.file_processor import process_file, discover_files

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "golden")


def _fixture_files():
    if not os.path.isdir(FIXTURES_DIR):
        return []
    return discover_files([FIXTURES_DIR], recursive=True)


class TestIdempotency:
    """Formatting an already-formatted file should produce no changes."""

    @pytest.mark.parametrize("filepath", _fixture_files(), ids=lambda p: os.path.relpath(p, FIXTURES_DIR))
    def test_format_is_idempotent(self, filepath, tmp_path):
        import shutil

        tmp_file = str(tmp_path / os.path.basename(filepath))
        shutil.copy2(filepath, tmp_file)

        cfg = load_config()
        process_file(tmp_file, cfg, dry_run=False)

        result2 = process_file(tmp_file, cfg, dry_run=True)
        assert not result2.changed, (
            f"File {os.path.relpath(filepath, FIXTURES_DIR)} is not idempotent"
        )


class TestValidation:
    """All fixture files should pass validation."""

    @pytest.mark.parametrize("filepath", _fixture_files(), ids=lambda p: os.path.relpath(p, FIXTURES_DIR))
    def test_validates_without_errors(self, filepath):
        cfg = load_config()
        result = process_file(filepath, cfg, dry_run=True, format_st=False, format_xml=False)
        errors = [e for e in result.errors if "error" in e.lower() or "[" in e]
        assert result.success or not errors, f"Validation errors: {result.errors}"


class TestDiscoverFiles:
    def test_finds_fixture_files(self):
        files = _fixture_files()
        assert len(files) >= 5
        extensions = {os.path.splitext(f)[1].lower() for f in files}
        assert ".tcpou" in extensions
        assert ".tcdut" in extensions
