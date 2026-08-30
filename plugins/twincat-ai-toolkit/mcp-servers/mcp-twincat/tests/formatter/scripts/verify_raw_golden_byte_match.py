#!/usr/bin/env python3
"""Byte-exact verification runner and utilities for raw vs golden formatter fixtures.

Walks ``fixtures/golden/**`` recursively; every TwinCAT file with a matching
``fixtures/raw/<same-relative-path>`` partner is a byte-match pair.

Usage (from mcp-twincat root)::

    python tests/formatter/scripts/verify_raw_golden_byte_match.py
    python tests/formatter/scripts/verify_raw_golden_byte_match.py --write-cache --diff
    python tests/formatter/scripts/verify_raw_golden_byte_match.py --failures-only
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures"
RAW_DIR = FIXTURES_DIR / "raw"
GOLDEN_DIR = FIXTURES_DIR / "golden"
CACHE_DIR = _MCP_ROOT / "tests" / "formatter" / ".cache"
FAILURES_CACHE = CACHE_DIR / "fixture_failures.json"

_EXTENSIONS = (".TcPOU", ".TcDUT", ".TcGVL", ".TcIO")

_CONFIG = None


def _get_config():
    global _CONFIG
    if _CONFIG is None:
        sys.path.insert(0, str(_MCP_ROOT))
        from formatter.config import load_config

        _CONFIG = load_config()
    return _CONFIG


def paired_files(*, require_raw: bool = True) -> list[tuple[Path, Path]]:
    """Return ``(raw, golden)`` pairs for every golden fixture with a raw counterpart."""
    pairs: list[tuple[Path, Path]] = []
    if not GOLDEN_DIR.is_dir():
        return pairs
    for golden in sorted(GOLDEN_DIR.rglob("*")):
        if not golden.is_file() or golden.suffix not in _EXTENSIONS:
            continue
        rel = golden.relative_to(GOLDEN_DIR)
        raw = RAW_DIR / rel
        if require_raw and not raw.is_file():
            continue
        pairs.append((raw, golden))
    return pairs


def golden_without_raw() -> list[str]:
    """Golden files that have no raw partner (should be empty in a healthy corpus)."""
    missing: list[str] = []
    for golden in sorted(GOLDEN_DIR.rglob("*")):
        if not golden.is_file() or golden.suffix not in _EXTENSIONS:
            continue
        rel = golden.relative_to(GOLDEN_DIR)
        if not (RAW_DIR / rel).is_file():
            missing.append(str(rel).replace("\\", "/"))
    return missing


def rel_path(path: Path) -> str:
    for base in (RAW_DIR, GOLDEN_DIR):
        try:
            return str(path.relative_to(base)).replace("\\", "/")
        except ValueError:
            pass
    return path.name


def format_to_bytes(raw_path: Path) -> bytes:
    """Format a file to a temp directory and return its exact formatted bytes."""
    sys.path.insert(0, str(_MCP_ROOT))
    from formatter.file_processor import process_file

    config = _get_config()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / raw_path.name
        shutil.copy2(raw_path, tmp_path)
        result = process_file(str(tmp_path), config, dry_run=False, sort_xml=True, validate=False)
        if not result.success:
            raise RuntimeError(f"{rel_path(raw_path)}: {result.errors}")
        return tmp_path.read_bytes()


@dataclass
class FileMatchResult:
    rel: str
    matched: bool
    error: str | None = None
    diff_lines: list[str] = field(default_factory=list)
    line_numbers: list[int] = field(default_factory=list)
    diff_count: int = 0


@dataclass
class ByteMatchReport:
    total: int
    matched: int
    failures: list[FileMatchResult]
    elapsed_s: float
    errors: list[FileMatchResult] = field(default_factory=list)

    @property
    def failed_count(self) -> int:
        return len(self.failures) + len(self.errors)


def _line_diffs(got_text: str, exp_text: str, *, max_lines: int = 8) -> tuple[list[str], list[int], int]:
    got_lines = got_text.splitlines()
    exp_lines = exp_text.splitlines()
    count = sum(1 for a, b in zip(got_lines, exp_lines) if a != b)
    count += abs(len(got_lines) - len(exp_lines))
    snippets: list[str] = []
    nums: list[int] = []
    for i, (a, b) in enumerate(zip(got_lines, exp_lines), start=1):
        if a == b:
            continue
        nums.append(i)
        if len(snippets) < max_lines:
            snippets.append(f"  L{i:4d}: expected: {b!r}")
            snippets.append(f"         got:      {a!r}")
    if len(nums) > max_lines:
        snippets.append(f"  ... ({len(nums) - max_lines} more lines differ)")
    return snippets, nums, count


def compare_pair(raw: Path, golden: Path, *, with_diff: bool = False) -> FileMatchResult:
    rel = str(golden.relative_to(GOLDEN_DIR)).replace("\\", "/")
    try:
        formatted = format_to_bytes(raw)
        expected = golden.read_bytes()
    except Exception as exc:  # noqa: BLE001
        return FileMatchResult(rel=rel, matched=False, error=str(exc))

    if formatted == expected:
        return FileMatchResult(rel=rel, matched=True)

    result = FileMatchResult(rel=rel, matched=False)
    if with_diff:
        got_text = formatted.decode("utf-8-sig", errors="replace")
        exp_text = expected.decode("utf-8-sig", errors="replace")
        result.diff_lines, result.line_numbers, result.diff_count = _line_diffs(got_text, exp_text)
    return result


def _worker_compare(args: tuple[str, str, bool]) -> FileMatchResult:
    raw_s, golden_s, with_diff = args
    return compare_pair(Path(raw_s), Path(golden_s), with_diff=with_diff)


def run_byte_match(
    files: list[tuple[Path, Path]] | None = None,
    *,
    parallel: int = 0,
    with_diff: bool = False,
    progress: bool = False,
) -> ByteMatchReport:
    """Compare formatted raw bytes against golden for *files* (default: full corpus)."""
    pairs = files if files is not None else paired_files()
    t0 = time.perf_counter()
    matched = 0
    failures: list[FileMatchResult] = []
    errors: list[FileMatchResult] = []

    workers = parallel if parallel > 0 else min(8, (os.cpu_count() or 4))

    if workers <= 1 or len(pairs) <= 1:
        for i, (raw, golden) in enumerate(pairs, start=1):
            res = compare_pair(raw, golden, with_diff=with_diff)
            if res.error:
                errors.append(res)
            elif res.matched:
                matched += 1
            else:
                failures.append(res)
            if progress and i % 50 == 0:
                print(f"  ... {i}/{len(pairs)}", flush=True)
    else:
        args = [(str(r), str(g), with_diff) for r, g in pairs]
        done = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_worker_compare, a) for a in args]
            for fut in as_completed(futures):
                result = fut.result()
                done += 1
                if result.error:
                    errors.append(result)
                elif result.matched:
                    matched += 1
                else:
                    failures.append(result)
                if progress and done % 50 == 0:
                    print(f"  ... {done}/{len(pairs)}", flush=True)

    failures.sort(key=lambda r: r.rel)
    errors.sort(key=lambda r: r.rel)
    return ByteMatchReport(
        total=len(pairs),
        matched=matched,
        failures=failures,
        errors=errors,
        elapsed_s=time.perf_counter() - t0,
    )


def load_failures_cache() -> list[str]:
    if not FAILURES_CACHE.is_file():
        return []
    data = json.loads(FAILURES_CACHE.read_text(encoding="utf-8"))
    return list(data.get("failures", []))


def save_failures_cache(failures: list[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"failures": sorted(set(failures)), "count": len(set(failures))}
    FAILURES_CACHE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def pairs_for_rels(rels: list[str]) -> list[tuple[Path, Path]]:
    out: list[tuple[Path, Path]] = []
    for rel in rels:
        rel_norm = rel.replace("\\", "/")
        raw = RAW_DIR / rel_norm
        golden = GOLDEN_DIR / rel_norm
        if raw.is_file() and golden.is_file():
            out.append((raw, golden))
    return out


def unified_diff_text(raw: Path, golden: Path, *, context: int = 2) -> str:
    got = format_to_bytes(raw).decode("utf-8-sig", errors="replace").splitlines(keepends=True)
    exp = golden.read_bytes().decode("utf-8-sig", errors="replace").splitlines(keepends=True)
    return "".join(
        unified_diff(exp, got, fromfile=f"golden/{rel_path(raw)}", tofile=f"formatted/{rel_path(raw)}", n=context)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Byte-match raw fixtures against golden corpus.")
    parser.add_argument("--quiet", action="store_true", help="Only print summary line")
    parser.add_argument("--diff", action="store_true", help="Include diff snippets for failures")
    parser.add_argument("--write-cache", action="store_true", help="Write failure rel-paths to cache")
    parser.add_argument("--failures-only", action="store_true", help="Re-check cached failures only")
    parser.add_argument("--parallel", type=int, default=0, help="Worker count (0=auto)")
    parser.add_argument("files", nargs="*", help="Optional rel-paths under raw/ to check")
    args = parser.parse_args()

    missing = golden_without_raw()
    if missing and not args.quiet:
        print(f"WARNING: {len(missing)} golden file(s) without raw partner:", file=sys.stderr)
        for m in missing[:5]:
            print(f"  {m}", file=sys.stderr)

    if args.files:
        pairs = pairs_for_rels(args.files)
    elif args.failures_only:
        rels = load_failures_cache()
        if not rels:
            print("No failures cache — run full match first with --write-cache")
            return 0
        pairs = pairs_for_rels(rels)
    else:
        pairs = paired_files()

    if not pairs:
        print("No paired fixtures found.")
        return 1

    report = run_byte_match(pairs, parallel=args.parallel, with_diff=args.diff, progress=not args.quiet)

    if args.write_cache and report.failures:
        save_failures_cache([f.rel for f in report.failures])

    if args.quiet:
        print(f"{report.matched}/{report.total} ({report.elapsed_s:.2f}s)")
    else:
        print(f"\n{report.matched}/{report.total} matched in {report.elapsed_s:.2f}s")
        if report.errors:
            print(f"Errors ({len(report.errors)}):")
            for e in report.errors[:10]:
                print(f"  {e.rel}: {e.error}")
        if report.failures:
            print(f"Failures ({len(report.failures)}):")
            for f in report.failures[:20]:
                print(f"  {f.rel}")
                if args.diff and f.diff_lines:
                    for line in f.diff_lines:
                        print(f"    {line}")

    if args.files and len(args.files) == 1 and report.failures and args.diff:
        raw, golden = pairs[0]
        print(unified_diff_text(raw, golden))

    return 0 if report.matched == report.total and not report.errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
