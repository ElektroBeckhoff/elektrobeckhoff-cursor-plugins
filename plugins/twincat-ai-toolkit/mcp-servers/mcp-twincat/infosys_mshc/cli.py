"""Command-line interface for InfoSys MSHC searching and reading."""

import argparse
import json
import sys
from typing import List, Optional

from infosys_mshc.index import InfoSysMshcIndex
from infosys_mshc.markdown import format_page_markdown, format_search_markdown
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
        "--library",
        type=str,
        default="",
        help="Filter search results by library name (e.g. 'Tc3_JsonXml')",
    )
    parser.add_argument(
        "--parent",
        type=str,
        default="",
        help="Filter search results by parent symbol (e.g. 'FB_JsonDomParser')",
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
        "--format", "-F",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format: text, json, or markdown (default: text)",
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output raw JSON instead of formatted text (alias for --format json)",
    )
    parser.add_argument(
        "--include-full-text",
        action="store_true",
        help="Include full unparsed page text in read response",
    )

    args = parser.parse_args(argv)

    if not args.search and not args.read:
        parser.print_help(sys.stderr)
        return 1

    out_fmt = "json" if args.json else args.format

    mshc_path = resolve_mshc_path(language=args.lang, file_path=args.file)

    try:
        idx = InfoSysMshcIndex(mshc_path)
        if args.search:
            result = idx.search(
                args.search,
                limit=args.limit,
                mode=args.mode,
                library=args.library,
                parent=args.parent,
            )
            if out_fmt == "json":
                print(json.dumps(result, indent=2))
            elif out_fmt == "markdown":
                print(format_search_markdown(result))
            else:
                _print_search_result(result)
            return 0
        elif args.read:
            page = idx.read_page(
                args.read,
                include_full_text=args.include_full_text,
            )
            if out_fmt == "json":
                print(json.dumps(page, indent=2))
            elif out_fmt == "markdown":
                print(format_page_markdown(page))
            else:
                _print_page_result(page)
            return 0
    except FileNotFoundError as exc:
        err_code = "MSHC_NOT_INSTALLED" if "not found" in str(exc).lower() else "PAGE_NOT_FOUND"
        if out_fmt == "json":
            print(json.dumps({"success": False, "error_code": err_code, "error": str(exc)}, indent=2))
        else:
            print(f"Error [{err_code}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        if out_fmt == "json":
            print(json.dumps({"success": False, "error_code": "INTERNAL_ERROR", "error": str(exc)}, indent=2))
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
        lib = item.get("library", "")
        parent = item.get("parent", "")
        comp = item.get("component", "")
        path = item.get("path", "")
        desc = item.get("description", "")
        snippet = item.get("snippet", "")

        lib_str = f" [{lib}]" if lib else ""
        parent_str = f" (parent: {parent})" if parent else ""
        print(f"[{i}] [{score:3d}%] {title} ({sym_type}){lib_str}{parent_str} — {comp}")
        print(f"    Path: {path}")
        if desc:
            print(f"    Desc: {desc}")
        if snippet:
            print(f"    Snippet: {snippet}")
        print()


def _print_page_result(page: dict) -> None:
    title = page.get("title", "")
    sym_type = page.get("type", "")
    lib = page.get("library", "")
    parent = page.get("parent", "")
    comp = page.get("component", "")
    desc = page.get("description", "")
    syntax = page.get("syntax", "")

    print(f"=== {title} ({sym_type}) ===")
    if lib:
        print(f"Library: {lib}")
    if parent:
        print(f"Parent: {parent}")
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
