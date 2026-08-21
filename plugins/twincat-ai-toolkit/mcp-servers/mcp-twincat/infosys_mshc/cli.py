"""Command-line interface for InfoSys MSHC searching and reading."""

import argparse
import json
import sys
from typing import List, Optional

from infosys_mshc.index import InfoSysMshcIndex
from infosys_mshc.paths import resolve_mshc_path


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point for InfoSys MSHC documentation tool."""
    parser = argparse.ArgumentParser(
        prog="infosys_mshc",
        description="Search and read local Beckhoff TwinCAT InfoSys offline documentation (.mshc).",
    )
    parser.add_argument(
        "--search", "-s",
        type=str,
        default="",
        help="Search query (e.g. 'FB_IotMqttClient', 'PID controller')",
    )
    parser.add_argument(
        "--read", "-r",
        type=str,
        default="",
        help="Path inside the MSHC archive to read (e.g. 'tf6701_.../3391835403.html')",
    )
    parser.add_argument(
        "--mode", "-m",
        choices=["auto", "title", "symbol", "fulltext"],
        default="auto",
        help="Search mode (default: auto)",
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        default=10,
        help="Maximum search results to return (default: 10)",
    )
    parser.add_argument(
        "--lang",
        type=str,
        default="en",
        help="Language code ('en' or 'de', default: 'en')",
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default="",
        help="Explicit path to BKINFOSYS3 .mshc archive",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output raw JSON instead of formatted text",
    )

    args = parser.parse_args(argv)

    if not args.search and not args.read:
        parser.print_help(sys.stderr)
        return 1

    mshc_path = resolve_mshc_path(language=args.lang, file_path=args.file)

    try:
        idx = InfoSysMshcIndex(mshc_path)
        if args.search:
            result = idx.search(args.search, limit=args.limit, mode=args.mode)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                _print_search_result(result)
            return 0
        elif args.read:
            page = idx.read_page(args.read)
            if args.json:
                print(json.dumps(page, indent=2))
            else:
                _print_page_result(page)
            return 0
    except FileNotFoundError as exc:
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if args.json:
            print(json.dumps({"success": False, "error": str(exc)}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


def _print_search_result(result: dict) -> None:
    query = result.get("query", "")
    mode = result.get("mode", "auto")
    count = result.get("count", 0)
    results = result.get("results", [])

    print(f"Query: '{query}' (mode: {mode}) — Found {count} result(s):")
    print("-" * 60)
    for i, item in enumerate(results, start=1):
        score = item.get("score", 0)
        title = item.get("title", "")
        sym_type = item.get("type", "")
        comp = item.get("component", "")
        path = item.get("path", "")
        desc = item.get("description", "")
        snippet = item.get("snippet", "")

        print(f"[{i}] [{score:3d}%] {title} ({sym_type}) — {comp}")
        print(f"    Path: {path}")
        if desc:
            print(f"    Desc: {desc}")
        if snippet:
            print(f"    Snippet: {snippet}")
        print()


def _print_page_result(page: dict) -> None:
    title = page.get("title", "")
    sym_type = page.get("type", "")
    comp = page.get("component", "")
    desc = page.get("description", "")
    syntax = page.get("syntax", "")

    print(f"=== {title} ({sym_type}) ===")
    if comp:
        print(f"Component: {comp}")
    if desc:
        print(f"Description: {desc}")
    if syntax:
        print("\n--- Syntax ---")
        print(syntax)

    inputs = page.get("inputs", [])
    if inputs:
        print("\n--- Inputs ---")
        for inp in inputs:
            print(f"  {inp.get('name', '')} : {inp.get('type', '')} — {inp.get('description', '')}")

    outputs = page.get("outputs", [])
    if outputs:
        print("\n--- Outputs ---")
        for out in outputs:
            print(f"  {out.get('name', '')} : {out.get('type', '')} — {out.get('description', '')}")

    methods = page.get("methods", [])
    if methods:
        print("\n--- Methods ---")
        for m in methods:
            print(f"  {m.get('name', '')} — {m.get('description', '')}")

    reqs = page.get("requirements", {})
    if reqs:
        print("\n--- Requirements ---")
        for k, v in reqs.items():
            print(f"  {k}: {v}")
