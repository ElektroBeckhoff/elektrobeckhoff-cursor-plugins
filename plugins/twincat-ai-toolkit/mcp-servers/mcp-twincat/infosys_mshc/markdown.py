"""Markdown formatting utilities for InfoSys MSHC documentation responses."""

from typing import Any, Dict


def format_search_markdown(result: Dict[str, Any]) -> str:
    """Format an MSHC search result dictionary into clean, token-efficient Markdown."""
    query = result.get("query", "")
    mode = result.get("mode", "auto")
    count = result.get("count", 0)
    results = result.get("results", [])

    lines = [f"### InfoSys Search: `{query}` (Mode: {mode}, Results: {count})", ""]
    if not results:
        lines.append("No results found.")
        return "\n".join(lines)

    lines.append("| # | Score | Symbol | Type | Library | Parent | Path |")
    lines.append("|---|---|---|---|---|---|---|")
    for i, item in enumerate(results, start=1):
        score = item.get("score", 0)
        title = item.get("title", "")
        sym_type = item.get("type", "")
        lib = item.get("library", "")
        parent = item.get("parent", "")
        path = item.get("path", "")
        lines.append(
            f"| {i} | {score}% | `{title}` | `{sym_type}` | {lib} | {parent} | `{path}` |"
        )

    lines.append("")
    snippets = [
        item
        for item in results
        if item.get("snippet") or item.get("description")
    ]
    if snippets:
        lines.append("#### Snippets & Descriptions")
        for item in snippets[:5]:
            title = item.get("title", "")
            desc = item.get("description", "")
            snip = item.get("snippet", "")
            lines.append(f"- **`{title}`**")
            if desc:
                lines.append(f"  {desc}")
            if snip:
                lines.append(f"  > {snip}")

    auto_read = result.get("auto_read")
    if auto_read and isinstance(auto_read, dict):
        lines.append("")
        lines.append("---")
        lines.append(format_page_markdown(auto_read))

    return "\n".join(lines).strip()


def format_page_markdown(page: Dict[str, Any]) -> str:
    """Format a documentation page dictionary into structured Markdown with IEC codeblocks."""
    title = page.get("title", "")
    sym_type = page.get("type", "")
    lib = page.get("library", "")
    parent = page.get("parent", "")
    comp = page.get("component", "")
    desc = page.get("description", "")
    syntax = page.get("syntax", "")

    header_parts = [f"`{title}`"]
    if sym_type:
        header_parts.append(f"(`{sym_type}`)")
    lines = [f"## {' '.join(header_parts)}", ""]

    meta_info = []
    if lib:
        meta_info.append(f"**Library:** `{lib}`")
    if parent:
        meta_info.append(f"**Parent:** `{parent}`")
    if comp:
        meta_info.append(f"**Component:** `{comp}`")
    if meta_info:
        lines.append(" | ".join(meta_info))
        lines.append("")

    if desc:
        lines.append(desc)
        lines.append("")

    if syntax:
        lines.append("### Syntax")
        lines.append("```iecst")
        lines.append(syntax)
        lines.append("```")
        lines.append("")

    inputs = page.get("inputs", [])
    if inputs:
        lines.append("### Inputs (VAR_INPUT)")
        lines.append("| Name | Type | Description |")
        lines.append("|---|---|---|")
        for inp in inputs:
            lines.append(
                f"| `{inp.get('name', '')}` | `{inp.get('type', '')}` | {inp.get('description', '')} |"
            )
        lines.append("")

    outputs = page.get("outputs", [])
    if outputs:
        lines.append("### Outputs (VAR_OUTPUT)")
        lines.append("| Name | Type | Description |")
        lines.append("|---|---|---|")
        for out in outputs:
            lines.append(
                f"| `{out.get('name', '')}` | `{out.get('type', '')}` | {out.get('description', '')} |"
            )
        lines.append("")

    parameters = page.get("parameters", [])
    if parameters:
        lines.append("### Parameters / InOuts")
        lines.append("| Name | Type | Description |")
        lines.append("|---|---|---|")
        for p in parameters:
            lines.append(
                f"| `{p.get('name', '')}` | `{p.get('type', '')}` | {p.get('description', '')} |"
            )
        lines.append("")

    methods = page.get("methods", [])
    if methods:
        shown = page.get("methods_shown", len(methods))
        total = page.get("methods_total", len(methods))
        hdr = (
            f"### Methods ({shown}/{total})"
            if total > shown
            else "### Methods"
        )
        lines.append(hdr)
        lines.append("| Method | Description |")
        lines.append("|---|---|")
        for m in methods:
            lines.append(f"| `{m.get('name', '')}` | {m.get('description', '')} |")
        lines.append("")

    reqs = page.get("requirements", {})
    if reqs:
        lines.append("### Requirements")
        for k, v in reqs.items():
            lines.append(f"- **{k}:** {v}")
        lines.append("")

    full_text = page.get("full_text", "")
    if full_text:
        lines.append("### Full Text")
        lines.append(full_text)
        lines.append("")

    if page.get("truncated"):
        lines.append("> *Note: Response content was truncated to fit token limits.*")

    return "\n".join(lines).strip()
