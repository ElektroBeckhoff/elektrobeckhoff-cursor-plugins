#!/usr/bin/env python3
"""Exhaustive 4-gate canonical fixpoint verification runner for the ST formatter.

For every RAW/GOLDEN fixture pair the following four gates must hold:

  1. format(raw)              == golden   (production formatting)
  2. format(golden)           == golden   (idempotence)
  3. format(collapse(golden)) == golden   (canonical from golden)
  4. format(collapse(raw))    == golden   (canonical from raw)

Usage (from mcp-twincat root)::

    python tests/formatter/scripts/verify_4gate_fixpoint.py --all

Exit code is 0 only when ALL gates pass for ALL files with 0 skips.
"""
from __future__ import annotations

import io
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_MCP_ROOT))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter" / "scripts"))

from formatter.config import load_config
from formatter.file_processor import process_file

FIXTURES_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures"
RAW_DIR = FIXTURES_DIR / "raw"
GOLDEN_DIR = FIXTURES_DIR / "golden"
EXTENSIONS = {".TcPOU", ".TcDUT", ".TcGVL", ".TcIO"}

CONFIG = load_config()

# ---------------------------------------------------------------------------
# Collapse helpers
# ---------------------------------------------------------------------------

_RE_IMPL_CDATA = re.compile(r"(<ST><!\[CDATA\[)(.*?)(\]\]></ST>)", re.DOTALL)
_RE_LINE_COMMENT = re.compile(r"//([^\n]*)")
_RE_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_DISABLE = re.compile(
    r"(?:\{|\(\*\s*@?|//\s*@?)(?:stweep\.disable|formatting\.disable|formatter:\s*off)",
    re.IGNORECASE,
)
_RE_ENABLE = re.compile(
    r"(?:\}|\*\)|//\s*@?)(?:stweep\.enable|formatting\.enable|formatter:\s*on)",
    re.IGNORECASE,
)


def _collapse_group(lines: list[str]) -> str:
    """Join a blank-line-delimited group into a single line."""
    return " ".join(l.strip() for l in lines if l.strip())


def _is_standalone_comment(stripped: str) -> bool:
    """True when line is entirely block comment(s) with no code."""
    sans = _RE_BLOCK_COMMENT.sub("", stripped).strip()
    return not sans and "(*" in stripped


def _has_leading_bc_with_code(stripped: str) -> bool:
    """True when line starts with block comment(s) followed by code."""
    if not stripped.startswith("(*"):
        return False
    tmp = stripped
    while tmp.startswith("(*"):
        end = tmp.find("*)", 2)
        if end < 0:
            return False
        tmp = tmp[end + 2:].lstrip()
    return bool(tmp)


def _has_code_and_trailing_bc(stripped: str) -> bool:
    """True when line has code/keywords before a trailing (* ... *)."""
    if not stripped.rstrip().endswith("*)"):
        return False
    pos = stripped.rfind("(*")
    if pos < 0:
        return False
    before = stripped[:pos]
    before_clean = _RE_BLOCK_COMMENT.sub("", before).strip()
    return bool(before_clean)


def _find_line_comment_pos(s: str) -> int:
    """Return index of // in s that is outside of string literals, or -1."""
    in_sq = False
    in_dq = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "'" and not in_dq:
            if in_sq and i + 1 < n and s[i + 1] == "'":
                i += 2
                continue
            in_sq = not in_sq
        elif c == '"' and not in_sq:
            if in_dq and i + 1 < n and s[i + 1] == '"':
                i += 2
                continue
            in_dq = not in_dq
        elif not in_sq and not in_dq:
            if c == "/" and i + 1 < n and s[i + 1] == "/":
                return i
        i += 1
    return -1


def _has_dollar_quote_string(s: str) -> bool:
    """True if line has a $' or $" string escape pattern."""
    return "$'" in s or '$"' in s


def _has_colon_equal(s: str) -> bool:
    """True if line contains := or => outside of comments/strings."""
    return ":=" in s or "=>" in s or s.rstrip().endswith(",") or s.rstrip().endswith("(") or (s.rstrip().endswith(");") and ":=" not in s and "AND" not in s and "OR" not in s)


def _collapse_impl_cdata(content: str) -> str:
    """Collapse ST implementation CDATA into minimal lines.

    Preserves line breaks for:
      - // comments converted to (* *)
      - Multi-line block comments (unclosed (* on a line)
      - (* formatting.disable *) regions
      - Blank lines (structural separators)
      - Standalone block comments
      - Lines with leading block comments before code
      - Lines with code before trailing block comments
      - Lines with $' / $" string escape patterns
      - Distinct := assignment statements (to avoid alignment drift)
    """
    result_lines: list[str] = []
    current_group: list[str] = []
    block_comment_depth = 0
    in_disable = False

    def _flush() -> None:
        if current_group:
            result_lines.append(_collapse_group(current_group))
            current_group.clear()

    for line in content.split("\n"):
        stripped = line.strip()

        if not stripped:
            _flush()
            result_lines.append("")
            continue

        if _RE_DISABLE.search(stripped):
            in_disable = True
        if in_disable:
            _flush()
            result_lines.append(stripped)
            if _RE_ENABLE.search(stripped):
                in_disable = False
            continue

        if stripped.startswith("{"):
            _flush()
            result_lines.append(stripped)
            continue

        if _find_line_comment_pos(line) >= 0:
            _flush()
            result_lines.append(stripped)
            continue

        if _has_dollar_quote_string(line):
            _flush()
            result_lines.append(stripped)
            continue

        bc_delta = line.count("(*") - line.count("*)")

        if block_comment_depth > 0:
            _flush()
            result_lines.append(line)
            block_comment_depth = max(0, block_comment_depth + bc_delta)
            continue

        if bc_delta > 0:
            _flush()
            result_lines.append(line)
            block_comment_depth += bc_delta
            continue

        if _is_standalone_comment(stripped):
            _flush()
            result_lines.append(stripped)
            continue

        if _has_leading_bc_with_code(stripped):
            _flush()
            result_lines.append(stripped)
            continue

        if _has_code_and_trailing_bc(stripped):
            _flush()
            result_lines.append(stripped)
            continue

        if _has_colon_equal(stripped) and current_group:
            _flush()
            result_lines.append(stripped)
            continue

        current_group.append(stripped)

    _flush()
    return "\n".join(result_lines)


def _collapse_and_encode(xml_bytes: bytes) -> bytes:
    """Collapse implementation CDATA in xml_bytes and return new bytes."""
    has_bom = xml_bytes.startswith(b"\xef\xbb\xbf")
    encoding = "utf-8-sig" if has_bom else "utf-8"
    text = xml_bytes.decode(encoding)

    def _replace_cdata(m: re.Match) -> str:
        open_tag, body, close_tag = m.groups()
        normalized = body.replace("\r\n", "\n").replace("\r", "\n")
        collapsed = _collapse_impl_cdata(normalized)
        return f"{open_tag}{collapsed}{close_tag}"

    collapsed_text = _RE_IMPL_CDATA.sub(_replace_cdata, text)

    crlf = "\r\n" if "\r\n" in text else "\n"
    if crlf == "\r\n":
        collapsed_text = collapsed_text.replace("\r\n", "\n").replace("\n", "\r\n")

    out = collapsed_text.encode("utf-8")
    if has_bom and not out.startswith(b"\xef\xbb\xbf"):
        out = b"\xef\xbb\xbf" + out
    return out


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------

def _format_bytes(in_bytes: bytes, suffix: str) -> bytes:
    """Format in_bytes through the production file_processor pipeline."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / f"temp{suffix}"
        tmp_path.write_bytes(in_bytes)
        result = process_file(str(tmp_path), CONFIG, dry_run=False, sort_xml=True, validate=False)
        if not result.success:
            raise RuntimeError(f"Formatter error: {result.errors}")
        return tmp_path.read_bytes()


def _first_diff(got: bytes, exp: bytes, *, max_chars: int = 120) -> str:
    """Return a short diagnostic string showing where got and exp first differ."""
    got_str = got.decode("utf-8-sig", errors="replace")
    exp_str = exp.decode("utf-8-sig", errors="replace")
    got_lines = got_str.splitlines()
    exp_lines = exp_str.splitlines()
    for i, (g, e) in enumerate(zip(got_lines, exp_lines), 1):
        if g != e:
            return (
                f"  First diff at line {i}:\n"
                f"    GOT: {g[:max_chars]!r}\n"
                f"    EXP: {e[:max_chars]!r}"
            )
    if len(got_lines) != len(exp_lines):
        return f"  Line count mismatch: got {len(got_lines)} lines, expected {len(exp_lines)}"
    return "  (Byte-level difference, content looks identical)"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Run 4-gate fixpoint checks on formatter fixtures."
    )
    parser.add_argument(
        "--all", action="store_true", help="Run all 4 gates on all fixtures"
    )
    parser.add_argument(
        "files", nargs="*", help="Optional specific fixture paths to check"
    )
    args = parser.parse_args()

    t0 = time.perf_counter()

    if args.files:
        pairs = []
        for f in args.files:
            p = Path(f)
            if not p.is_file():
                p_raw = RAW_DIR / f
                p_golden = GOLDEN_DIR / f
            else:
                rel = p.relative_to(RAW_DIR) if RAW_DIR in p.parents else p.relative_to(GOLDEN_DIR)
                p_raw = RAW_DIR / rel
                p_golden = GOLDEN_DIR / rel
            if p_raw.is_file() and p_golden.is_file():
                pairs.append((p_raw, p_golden))
            else:
                print(f"ERROR: cannot resolve pair for {f}", file=sys.stderr)
                return 1
    else:
        pairs = []
        for g in sorted(GOLDEN_DIR.rglob("*")):
            if g.is_file() and g.suffix in EXTENSIONS:
                rel = g.relative_to(GOLDEN_DIR)
                r = RAW_DIR / rel
                if r.is_file():
                    pairs.append((r, g))

    missing_raw = []
    for g in sorted(GOLDEN_DIR.rglob("*")):
        if g.is_file() and g.suffix in EXTENSIONS:
            rel = g.relative_to(GOLDEN_DIR)
            if not (RAW_DIR / rel).is_file():
                missing_raw.append(str(rel))

    orphan_raw = []
    for r in sorted(RAW_DIR.rglob("*")):
        if r.is_file() and r.suffix in EXTENSIONS:
            rel = r.relative_to(RAW_DIR)
            if not (GOLDEN_DIR / rel).is_file():
                orphan_raw.append(str(rel))

    if missing_raw:
        print(f"FATAL: {len(missing_raw)} golden files have no raw partner:")
        for m in missing_raw[:10]:
            print(f"  {m}")
        return 1
    if orphan_raw:
        print(f"FATAL: {len(orphan_raw)} raw files have no golden partner:")
        for m in orphan_raw[:10]:
            print(f"  {m}")
        return 1

    total = len(pairs)
    gate_raw = 0
    gate_golden = 0
    gate_collapse_golden = 0
    gate_collapse_raw = 0
    failures: list[str] = []

    for idx, (raw, golden) in enumerate(pairs, 1):
        rel = str(raw.relative_to(RAW_DIR)).replace("\\", "/")
        raw_bytes = raw.read_bytes()
        golden_bytes = golden.read_bytes()
        suffix = raw.suffix

        if idx % 100 == 0 or idx == total:
            print(f"  [{idx}/{total}] ...", flush=True)

        # Gate 1: format(raw) == golden
        try:
            fmt_raw = _format_bytes(raw_bytes, suffix)
        except Exception as exc:
            failures.append(f"GATE1 ERROR {rel}: {exc}")
            continue
        if fmt_raw == golden_bytes:
            gate_raw += 1
        else:
            failures.append(f"GATE1 FAIL {rel}: format(raw) != golden\n{_first_diff(fmt_raw, golden_bytes)}")

        # Gate 2: format(golden) == golden
        try:
            fmt_golden = _format_bytes(golden_bytes, suffix)
        except Exception as exc:
            failures.append(f"GATE2 ERROR {rel}: {exc}")
            continue
        if fmt_golden == golden_bytes:
            gate_golden += 1
        else:
            failures.append(f"GATE2 FAIL {rel}: format(golden) != golden\n{_first_diff(fmt_golden, golden_bytes)}")

        # Gate 3: format(collapse(golden)) == golden
        try:
            collapsed_golden = _collapse_and_encode(golden_bytes)
            fmt_cg = _format_bytes(collapsed_golden, suffix)
        except Exception as exc:
            failures.append(f"GATE3 ERROR {rel}: {exc}")
            continue
        if fmt_cg == golden_bytes:
            gate_collapse_golden += 1
        else:
            failures.append(f"GATE3 FAIL {rel}: format(collapse(golden)) != golden\n{_first_diff(fmt_cg, golden_bytes)}")

        # Gate 4: format(collapse(raw)) == golden
        try:
            collapsed_raw = _collapse_and_encode(raw_bytes)
            fmt_cr = _format_bytes(collapsed_raw, suffix)
        except Exception as exc:
            failures.append(f"GATE4 ERROR {rel}: {exc}")
            continue
        if fmt_cr == golden_bytes:
            gate_collapse_raw += 1
        else:
            failures.append(f"GATE4 FAIL {rel}: format(collapse(raw)) != golden\n{_first_diff(fmt_cr, golden_bytes)}")

    elapsed = time.perf_counter() - t0

    print()
    print("=" * 60)
    print(f"RAW files:             {total}")
    print(f"Golden matched:        {total}/{total}")
    print(f"Raw->Golden:           {gate_raw}/{total}")
    print(f"Golden->Golden:        {gate_golden}/{total}")
    print(f"Collapsed(G)->Golden:  {gate_collapse_golden}/{total}")
    print(f"Collapsed(R)->Golden:  {gate_collapse_raw}/{total}")
    print(f"Skipped:               0")
    print(f"Missing Golden:        {len(missing_raw)}")
    print(f"Missing Raw:           {len(orphan_raw)}")
    print(f"Failures:              {len(failures)}")
    print(f"Elapsed:               {elapsed:.1f}s")
    print("=" * 60)

    if failures:
        print()
        print(f"--- {len(failures)} failure(s) ---")
        for f in failures:
            print(f)
            print()
        return 1

    print("\nALL GATES PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
