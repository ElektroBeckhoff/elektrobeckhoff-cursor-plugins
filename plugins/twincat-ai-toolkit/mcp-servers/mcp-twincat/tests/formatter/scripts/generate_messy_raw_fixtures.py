#!/usr/bin/env python3
"""Refresh raw fixtures from golden and apply messy transforms in place.

Usage (from mcp-twincat root)::

    python tests/formatter/scripts/generate_messy_raw_fixtures.py --from-golden
    python tests/formatter/scripts/generate_messy_raw_fixtures.py --from-golden --target raw/syntax
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_MCP_ROOT = Path(__file__).resolve().parents[3]
_FIXTURES = _MCP_ROOT / "tests" / "formatter" / "fixtures"
sys.path.insert(0, str(_MCP_ROOT))
sys.path.insert(0, str(_MCP_ROOT / "tests" / "formatter" / "scripts"))

from messy_corpus_transforms import DEFAULT_MESSY_PROFILE, MessyProfile, mess_directory_in_place  # noqa: E402

RAW_DIR = _FIXTURES / "raw"
GOLDEN_DIR = _FIXTURES / "golden"
EXTENSIONS = {".TcPOU", ".TcDUT", ".TcGVL", ".TcIO"}


def sync_from_golden(golden_dir: Path, target_dir: Path) -> int:
    """Copy golden tree into target and remove stale files."""
    if not golden_dir.is_dir():
        raise FileNotFoundError(f"golden not found: {golden_dir}")

    golden_files = {
        path.relative_to(golden_dir)
        for path in golden_dir.rglob("*")
        if path.is_file()
    }
    copied = 0
    for rel in sorted(golden_files):
        src = golden_dir / rel
        dst = target_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    if target_dir.is_dir():
        for dst in target_dir.rglob("*"):
            if not dst.is_file():
                continue
            rel = dst.relative_to(target_dir)
            if rel not in golden_files:
                dst.unlink()

    return copied


def main() -> int:
    parser = argparse.ArgumentParser(description="Copy golden → raw and apply messy transforms.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default: 42)")
    parser.add_argument(
        "--target",
        type=Path,
        default=RAW_DIR,
        help="Raw directory or subfolder to mess (default: entire raw/)",
    )
    parser.add_argument(
        "--from-golden",
        action="store_true",
        help="Refresh target from matching golden subtree before messing",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=None,
        help="Golden source (default: fixtures/golden, or matching subtree)",
    )
    args = parser.parse_args()

    golden_src = args.golden
    if golden_src is None:
        if args.target == RAW_DIR or args.target.resolve() == RAW_DIR.resolve():
            golden_src = GOLDEN_DIR
        else:
            rel = args.target.resolve().relative_to(RAW_DIR.resolve())
            golden_src = GOLDEN_DIR / rel

    if not args.target.is_dir() and not args.from_golden:
        print(f"ERROR: target not found: {args.target}", file=sys.stderr)
        return 1

    if args.from_golden:
        args.target.mkdir(parents=True, exist_ok=True)
        copied = sync_from_golden(golden_src, args.target)
        print(f"Synced {copied} files from {golden_src} -> {args.target}")

    count = mess_directory_in_place(
        args.target,
        seed=args.seed,
        profile=DEFAULT_MESSY_PROFILE,
    )
    print(f"Messy corpus written in place: {count} files under {args.target}")
    print(
        f"Profile: aggressive (keyword={DEFAULT_MESSY_PROFILE.keyword_lower_prob}, "
        f"enum={DEFAULT_MESSY_PROFILE.mess_enum_members}, "
        f"struct_init={DEFAULT_MESSY_PROFILE.mess_struct_init_openers}, "
        f"indent={DEFAULT_MESSY_PROFILE.indent_mess_prob})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
