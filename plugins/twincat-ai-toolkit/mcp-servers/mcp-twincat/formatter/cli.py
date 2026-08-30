"""CLI interface for the TwinCAT3 ST Formatter.

Provides argparse-based command line with dry-run, diff, check, verbose, etc.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from formatter.config import FormatterConfig, config_to_dict, load_config
from formatter.diff_reporter import format_file_status, format_summary, format_validation_report
from formatter.file_processor import discover_files, discover_project_files, process_batch
from formatter.types import ExitCode, FormatRegion, FormatScope, MemberFilter


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="formatter",
        description="TwinCAT3 Structured Text Formatter — format .TcPOU, .TcDUT, .TcGVL, .TcIO files",
    )

    parser.add_argument(
        "paths",
        nargs="*",
        default=["."],
        help="Files or directories to format (default: current directory)",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check", "-c",
        action="store_true",
        help="Exit 1 if files would change (CI mode)",
    )
    mode_group.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Do not write files, only report",
    )
    mode_group.add_argument(
        "--validate-only", "-V",
        action="store_true",
        help="Only run XML validation, no formatting",
    )

    parser.add_argument(
        "--diff", "-d",
        action="store_true",
        help="Show unified diff output (implies --dry-run)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output per file",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only output errors",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        default=None,
        help="Keep .bak files after successful format",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create backup files",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Custom JSON config file",
    )
    parser.add_argument(
        "--no-xml",
        action="store_true",
        help="Only format ST code, skip XML formatting",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip XML validation",
    )
    parser.add_argument(
        "--no-syntax-check",
        action="store_true",
        help="Skip post-format syntax integrity check (saves ~3ms/file)",
    )
    parser.add_argument(
        "--normalize-spaces",
        action="store_true",
        help="Collapse multiple consecutive spaces to one (aggressive; may break existing alignment)",
    )
    parser.add_argument(
        "--sort",
        action="store_true",
        default=None,
        help="Force-enable XML element sorting (Methods/Actions/Properties alphabetically)",
    )
    parser.add_argument(
        "--no-sort",
        action="store_true",
        help="Disable XML element sorting (overrides config)",
    )
    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        default=True,
        help="Recurse into directories (default: True)",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Do not recurse into directories",
    )
    parser.add_argument(
        "--include",
        metavar="GLOB",
        help="Only format files matching glob (e.g. '*.TcPOU')",
    )
    parser.add_argument(
        "--exclude",
        metavar="GLOB",
        help="Exclude files matching glob",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help="Number of parallel workers (default: auto)",
    )
    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Print active configuration and exit",
    )

    # Region/Member Scope
    scope_group = parser.add_argument_group("scope", "Limit formatting to specific regions/members")
    scope_group.add_argument(
        "--region",
        choices=["all", "declaration", "implementation"],
        default="all",
        help="Format only Declaration or Implementation sections (default: all)",
    )
    scope_group.add_argument(
        "--member",
        metavar="NAME",
        help="Format only a specific Method/Action/Property by name",
    )
    scope_group.add_argument(
        "--methods",
        action="store_true",
        help="Format all Methods only",
    )
    scope_group.add_argument(
        "--actions",
        action="store_true",
        help="Format all Actions only",
    )
    scope_group.add_argument(
        "--properties",
        action="store_true",
        help="Format all Properties only",
    )

    # Project discovery
    parser.add_argument(
        "--project",
        metavar="PATH",
        help="Path to .sln or .plcproj — discovers all TwinCAT files in the project",
    )

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """Execute the CLI and return exit code."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.diff:
        args.dry_run = True

    try:
        config = load_config(
            config_path=args.config,
            project_root=Path(args.paths[0]).resolve() if args.paths else None,
        )
    except Exception as e:
        print(f"formatter: config error: {e}", file=sys.stderr)
        return ExitCode.CONFIG_ERROR

    if args.show_config:
        import json
        print(json.dumps(config_to_dict(config), indent=2))
        return ExitCode.SUCCESS

    if args.no_backup:
        config.safety.backup = False
    elif args.backup:
        config.safety.delete_backup_on_success = False

    # Build scope from CLI arguments
    scope = _build_scope(args)

    # Discover files (project or path-based)
    if args.project:
        files = discover_project_files(args.project)
    else:
        recursive = not args.no_recursive
        files = discover_files(
            args.paths,
            recursive=recursive,
            include=args.include,
            exclude=args.exclude,
        )

    if not files:
        if not args.quiet:
            print("formatter: no formattable files found")
        return ExitCode.SUCCESS

    if args.validate_only:
        batch = process_batch(
            files, config,
            dry_run=True,
            validate=True,
            format_st=False,
            format_xml=False,
            max_workers=args.workers,
        )
    else:
        if args.no_syntax_check:
            config.safety.syntax_check = False
        if args.normalize_spaces:
            config.spaces.normalize_inline = True
        # Determine sort_xml: CLI flags override config
        if args.no_sort:
            sort_xml = False
        elif args.sort:
            sort_xml = True
        else:
            sort_xml = any([config.xml.sort_methods, config.xml.sort_actions, config.xml.sort_properties])

        batch = process_batch(
            files, config,
            dry_run=args.dry_run or args.check or args.diff,
            validate=not args.no_validate,
            format_st=True,
            format_xml=not args.no_xml,
            sort_xml=sort_xml,
            max_workers=args.workers,
            scope=scope,
        )

    if not args.quiet:
        for result in batch.results:
            line = format_file_status(result, verbose=args.verbose)
            if line:
                print(line)
            if args.diff and result.diff:
                print(result.diff)

        if batch.validation_issues:
            print(format_validation_report(batch))

        print(f"\n{format_summary(batch)}")

    if batch.errors > 0:
        return ExitCode.ERROR

    if args.validate_only and batch.validation_issues:
        has_errors = any(i.level == "error" for i in batch.validation_issues)
        if has_errors:
            return ExitCode.VALIDATION_ERROR

    if args.check and batch.formatted > 0:
        return ExitCode.FILES_CHANGED

    return ExitCode.SUCCESS


def _build_scope(args: argparse.Namespace) -> FormatScope | None:
    """Build FormatScope from CLI arguments. Returns None if all defaults."""
    region = FormatRegion(args.region)
    member_name = args.member or ""
    member_filter: MemberFilter | None = None

    if args.methods:
        member_filter = MemberFilter.ALL_METHODS
    elif args.actions:
        member_filter = MemberFilter.ALL_ACTIONS
    elif args.properties:
        member_filter = MemberFilter.ALL_PROPERTIES

    if region == FormatRegion.ALL and not member_name and member_filter is None:
        return None

    return FormatScope(
        region=region,
        member_filter=member_filter,
        member_name=member_name,
    )


if __name__ == "__main__":
    sys.exit(run_cli())
