"""Byte-exact formatter parity: format(raw) == golden for every paired fixture.

Drop new files into ``fixtures/raw/`` and ``fixtures/golden/`` (same relative path);
they are picked up automatically on the next test run.

Fast iteration::

    python tests/formatter/scripts/verify_raw_golden_byte_match.py --write-cache
    python tests/formatter/scripts/verify_raw_golden_byte_match.py --failures-only --diff
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_MCP_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_MCP_ROOT))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter"))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter" / "scripts"))

from formatter.config import load_config
from formatter.file_processor import process_file
from verify_raw_golden_byte_match import (
    golden_without_raw,
    load_failures_cache,
    paired_files,
    pairs_for_rels,
    rel_path,
    run_byte_match,
    save_failures_cache,
)

CONFIG = load_config()
_KNOWN_DIFFS = frozenset()


@pytest.fixture(scope="session")
def paired_file_list() -> list[tuple[Path, Path]]:
    pairs = paired_files()
    assert pairs, "No raw/golden pairs found under fixtures/"
    missing = golden_without_raw()
    assert not missing, f"Golden without raw partner: {missing[:5]}"
    return pairs


def test_fixture_pair_count(paired_file_list: list[tuple[Path, Path]]):
    """Every golden file must have a raw partner."""
    assert len(paired_file_list) >= 50


def test_fixture_byte_match_all(paired_file_list: list[tuple[Path, Path]]):
    """format(raw) must equal golden byte-for-byte for the full corpus."""
    report = run_byte_match(paired_file_list, parallel=min(8, __import__("os").cpu_count() or 4))
    failures = [f.rel for f in report.failures if f.rel not in _KNOWN_DIFFS]

    if failures:
        save_failures_cache(failures)

    assert report.matched == report.total, (
        f"Match {report.matched}/{report.total} in {report.elapsed_s:.1f}s — "
        f"failures: {failures[:10]}"
    )
    if failures:
        pytest.fail(f"Unexpected diffs ({len(failures)}): " + ", ".join(failures[:10]))


@pytest.mark.fast
def test_fixture_byte_match_failures_only():
    """Re-check only cached failures (fast loop after full run wrote cache)."""
    rels = load_failures_cache()
    if not rels:
        pytest.skip("No failures cache — run test_fixture_byte_match_all first")

    pairs = pairs_for_rels(rels)
    assert pairs, "Failures cache paths missing from disk"

    report = run_byte_match(pairs, parallel=1, with_diff=False)
    still = [f.rel for f in report.failures if f.rel not in _KNOWN_DIFFS]
    assert not still, f"Still failing ({len(still)}): {still[:10]}"


def test_golden_idempotent_all(paired_file_list: list[tuple[Path, Path]]):
    """Every golden file must be formatter-idempotent."""
    not_idempotent: list[str] = []
    for _raw, golden in paired_file_list:
        result = process_file(str(golden), CONFIG, dry_run=True, sort_xml=False, validate=False)
        if result.changed:
            not_idempotent.append(rel_path(_raw))
    assert not not_idempotent, f"Golden not idempotent ({len(not_idempotent)}): {not_idempotent[:10]}"
