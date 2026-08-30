#!/usr/bin/env python3
"""Write format(raw) bytes to golden for all paired fixtures."""
from __future__ import annotations

import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_MCP_ROOT))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter" / "scripts"))

from verify_raw_golden_byte_match import format_to_bytes, paired_files  # noqa: E402


def main() -> int:
    pairs = paired_files()
    updated = 0
    for raw, golden in pairs:
        out = format_to_bytes(raw)
        if golden.read_bytes() != out:
            golden.write_bytes(out)
            updated += 1
    print(f"Synced golden from format(raw): {updated}/{len(pairs)} files changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
