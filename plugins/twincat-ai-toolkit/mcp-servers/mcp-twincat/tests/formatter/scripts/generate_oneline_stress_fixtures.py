#!/usr/bin/env python3
"""Generate one-liner (maximally collapsed) stress test versions of ALL RAW fixture files.

Reads every file from fixtures/raw/, collapses all ST/CDATA content to
minimal line count using the same collapse logic as verify_4gate_fixpoint.py,
and writes the result to fixtures/oneline/ preserving the relative
directory structure.

Usage (from mcp-twincat root)::

    python tests/formatter/scripts/generate_oneline_stress_fixtures.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_MCP_ROOT))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter" / "scripts"))

from verify_4gate_fixpoint import (
    _collapse_impl_cdata,
    _find_line_comment_pos,
    _has_dollar_quote_string,
    _RE_DISABLE,
    _RE_ENABLE,
)

FIXTURES_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures"
RAW_DIR = FIXTURES_DIR / "raw"
OUT_DIR = FIXTURES_DIR / "oneline"
EXTENSIONS = {".TcPOU", ".TcDUT", ".TcGVL", ".TcIO"}

_RE_DECL_CDATA = re.compile(
    r"(<Declaration><!\[CDATA\[)(.*?)(\]\]></Declaration>)", re.DOTALL
)


def _collapse_decl_aggressive(content: str) -> str:
    """Aggressively collapse Declaration CDATA to minimal lines.

    Only preserves line breaks for:
      - // line comments (would absorb subsequent code)
      - Unclosed (* block comment openers (multi-line comments)
      - (* formatting.disable *) regions
      - Blank lines (structural separators)
      - Lines with $' string patterns
    Everything else (including standalone and trailing block comments)
    is joined into single lines per blank-line group.
    """
    result_lines: list[str] = []
    current_group: list[str] = []
    block_comment_depth = 0
    in_disable = False

    def _flush() -> None:
        if current_group:
            result_lines.append(" ".join(l.strip() for l in current_group if l.strip()))
            current_group.clear()

    for line in content.split("\n"):
        stripped = line.strip()

        if in_disable:
            result_lines.append(line)
            if _RE_ENABLE.search(stripped):
                in_disable = False
            continue
        if _RE_DISABLE.search(stripped):
            _flush()
            result_lines.append(line)
            in_disable = True
            continue

        if block_comment_depth > 0:
            result_lines.append(line)
            block_comment_depth += stripped.count("(*") - stripped.count("*)")
            if block_comment_depth < 0:
                block_comment_depth = 0
            continue

        if not stripped:
            _flush()
            result_lines.append("")
            continue

        lc_pos = _find_line_comment_pos(stripped)
        if lc_pos >= 0:
            _flush()
            result_lines.append(stripped)
            continue

        if _has_dollar_quote_string(stripped):
            _flush()
            result_lines.append(stripped)
            continue

        opens = stripped.count("(*")
        closes = stripped.count("*)")
        if opens > closes:
            _flush()
            result_lines.append(line)
            block_comment_depth = opens - closes
            continue

        current_group.append(stripped)

    _flush()
    return "\n".join(result_lines)


def _collapse_decl_cdata(xml_text: str) -> str:
    """Collapse all <Declaration> CDATA blocks aggressively."""
    def _sub(m: re.Match[str]) -> str:
        prefix, content, suffix = m.group(1), m.group(2), m.group(3)
        collapsed = _collapse_decl_aggressive(content)
        if not collapsed.strip():
            return prefix + suffix
        return prefix + collapsed + "\n" + suffix
    return _RE_DECL_CDATA.sub(_sub, xml_text)


def _collapse_all(xml_text: str) -> str:
    """Collapse both Declaration and ST CDATA blocks."""
    result = _collapse_impl_cdata(xml_text)
    result = _collapse_decl_cdata(result)
    return result


def main() -> None:
    raw_files = sorted(
        f for f in RAW_DIR.rglob("*")
        if f.is_file() and f.suffix in EXTENSIONS
    )

    if not raw_files:
        print("ERROR: no RAW files found")
        sys.exit(1)

    created = 0
    errors = 0

    for raw_path in raw_files:
        rel = raw_path.relative_to(RAW_DIR)
        out_path = OUT_DIR / rel

        try:
            raw_bytes = raw_path.read_bytes()
            raw_text = raw_bytes.decode("utf-8")
            collapsed = _collapse_all(raw_text)

            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(collapsed.encode("utf-8"))
            created += 1
        except Exception as e:
            print(f"ERROR: {rel}: {e}")
            errors += 1

    print(f"\nGenerated {created} one-liner files in {OUT_DIR.relative_to(_MCP_ROOT)}")
    if errors:
        print(f"Errors: {errors}")
        sys.exit(1)
    else:
        print("Errors: 0")


if __name__ == "__main__":
    main()
