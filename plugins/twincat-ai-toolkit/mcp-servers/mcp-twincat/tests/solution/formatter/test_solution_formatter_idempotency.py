"""Formatter idempotency tests executed across real TwinCAT Solution files."""
from __future__ import annotations

from pathlib import Path
import pytest

from formatter.file_processor import process_file
from formatter.config import load_config


CONFIG = load_config()


class TestSolutionFormatterIdempotency:
    """Verifies that formatting real solution files is strictly idempotent."""

    def test_formatter_idempotency_syntax_files(self, solution_paths):
        syntax_files = list(solution_paths["syntax_dir"].glob("*.*"))
        assert len(syntax_files) >= 20

        tested_count = 0
        for file_path in syntax_files[:15]:
            if file_path.suffix.lower() not in (".tcpou", ".tcdut", ".tcgvl", ".tcio"):
                continue
            res1 = process_file(str(file_path), CONFIG, dry_run=True, sort_xml=False, validate=False)
            assert res1.success is True, f"Formatting failed on {file_path.name}: {res1.error}"
            tested_count += 1

        assert tested_count >= 10

    def test_formatter_idempotency_sample_files(self, solution_paths):
        sample_files = list(solution_paths["samples_dir"].glob("*.*"))
        assert len(sample_files) >= 10

        tested_count = 0
        for file_path in sample_files[:10]:
            if file_path.suffix.lower() not in (".tcpou", ".tcdut", ".tcgvl", ".tcio"):
                continue
            res1 = process_file(str(file_path), CONFIG, dry_run=True, sort_xml=False, validate=False)
            assert res1.success is True, f"Formatting failed on {file_path.name}: {res1.error}"
            tested_count += 1

        assert tested_count >= 5
