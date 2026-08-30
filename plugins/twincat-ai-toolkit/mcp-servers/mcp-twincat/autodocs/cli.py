"""CLI for TwinCAT autodocs generation."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from autodocs.paths import resolve_output_root
from autodocs.pipeline import process_folder


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autodocs",
        description="Generate Markdown API docs from TwinCAT source (.TcPOU/.TcDUT/.TcGVL/.TcIO)",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Solution folder containing TwinCAT sources (required; directory with .sln)",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional repo/project root; docs go to <output>/docs/. "
        "Default: auto-detect from input (README.md / .git walk, else parent of input).",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress console log output",
    )
    parser.add_argument(
        "--write-log",
        action="store_true",
        default=False,
        help="Write docs/autodocs.log (default: disabled)",
    )
    parser.add_argument(
        "--toc-timestamp",
        action="store_true",
        default=False,
        help="Include timestamp in TOC lines (default: disabled)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input)

    if not input_path.exists():
        print(f"ERROR: Input path does not exist: {input_path}", file=sys.stderr)
        return 1
    if not input_path.is_dir():
        print(f"ERROR: Input path is not a directory: {input_path}", file=sys.stderr)
        return 1

    output_path = resolve_output_root(input_path, args.output or None)
    output_path.mkdir(parents=True, exist_ok=True)

    verbose = not args.quiet
    if verbose and not str(args.output).strip():
        print(f"Auto-detected repo root: {output_path}")

    report = process_folder(
        input_path,
        output_path,
        verbose=verbose,
        write_log=args.write_log,
        include_toc_timestamp=args.toc_timestamp,
    )
    return 1 if report.errors > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
