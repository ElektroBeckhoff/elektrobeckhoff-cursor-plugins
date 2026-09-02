"""
Offline Beckhoff InfoSys documentation (.mshc) search and read MCP tools.
"""

from __future__ import annotations

from typing import Any, Dict

from infosys_mshc import (
    InfoSysMshcIndex,
    resolve_mshc_path,
    format_search_markdown,
    format_page_markdown,
)
from .common import _json

_infosys_mshc_cache: Dict[str, InfoSysMshcIndex] = {}


def _get_infosys_mshc(language: str = "en", file_path: str = "") -> InfoSysMshcIndex:
    import sys
    srv = sys.modules.get("server")
    if srv and "_get_infosys_mshc" in srv.__dict__ and srv._get_infosys_mshc is not _get_infosys_mshc:
        return srv._get_infosys_mshc(language, file_path)
    mshc = resolve_mshc_path(language, file_path)
    if mshc not in _infosys_mshc_cache:
        _infosys_mshc_cache[mshc] = InfoSysMshcIndex(mshc)
    return _infosys_mshc_cache[mshc]


def twincat_infosys_mshc_search(
    query: str,
    language: str = "en",
    file_path: str = "",
    limit: int = 10,
    mode: str = "auto",
    auto_read: bool = True,
    library: str = "",
    parent: str = "",
    format: str = "markdown",
) -> str:
    """Search the local Beckhoff InfoSys offline documentation (.mshc).

    Searches the locally installed TwinCAT 3 documentation archive
    (~55k pages) for FB_, ST_, E_, I_, F_, M_, P_ symbols, articles, attributes,
    and any documentation content.

    language: "en" (default) for English docs, "de" for German docs.

    Modes:
      - auto (default): exact title > prefix > substring > BM25 fulltext
      - title: title-only matching
      - symbol: title-only, filtered to IEC symbols (FB, ST, E, I, F, M, P)
      - fulltext: BM25-ranked keyword search (SQLite FTS5), fast (~1-3ms)

    Optional filters:
      - library: filter to a specific library (e.g. "Tc3_JsonXml", "Tc3_IotBase")
      - parent: filter to a specific parent symbol (e.g. "FB_JsonDomParser")

    Output format:
      - format: "markdown" (default, token-efficient table/codeblock layout) or "json"

    auto_read (default True): When the top result scores 100,
    automatically reads the page structure (syntax, inputs, outputs, methods, requirements)
    without full text bloat to preserve LLM token budget.

    Requires TwinCAT 3 offline documentation installed via
    Help > Add and Remove Help Content in TcXaeShell."""
    try:
        idx = _get_infosys_mshc(language, file_path)
        result = idx.search(
            query,
            limit=limit,
            mode=mode,
            library=library,
            parent=parent,
        )
        if (
            auto_read
            and result.get("count", 0) >= 1
            and result["results"][0].get("score") == 100
        ):
            top = result["results"][0]
            try:
                page = idx.read_page(top["path"], include_full_text=False)
                result["auto_read"] = page
            except Exception:
                pass

        if format == "json":
            return _json(result)
        return format_search_markdown(result)
    except FileNotFoundError as exc:
        err_code = "MSHC_NOT_INSTALLED" if "not found" in str(exc).lower() else "PAGE_NOT_FOUND"
        if format == "json":
            return _json({"success": False, "error_code": err_code, "error": str(exc)})
        return f"**Error [{err_code}]:** {exc}"
    except Exception as exc:
        if format == "json":
            return _json({"success": False, "error_code": "INTERNAL_ERROR", "error": str(exc)})
        return f"**Error [INTERNAL_ERROR]:** {exc}"


def twincat_infosys_mshc_read(
    path: str,
    language: str = "en",
    file_path: str = "",
    include_full_text: bool = False,
    format: str = "markdown",
) -> str:
    """Read a specific page from the local Beckhoff InfoSys offline documentation (.mshc).

    Returns structured content including title, library, parent symbol, syntax block,
    VAR_INPUT/VAR_OUTPUT tables, methods list, and requirements.

    language: "en" (default) for English docs, "de" for German docs.
    include_full_text: default False to save tokens (<500 tokens). Set True for full unparsed body.
    format: "markdown" (default, token-efficient layout) or "json".

    Use twincat_infosys_mshc_search first to find the internal path,
    then pass it here to read the page content."""
    try:
        idx = _get_infosys_mshc(language, file_path)
        page = idx.read_page(path, include_full_text=include_full_text)
        if format == "json":
            return _json(page)
        return format_page_markdown(page)
    except FileNotFoundError as exc:
        err_code = "MSHC_NOT_INSTALLED" if "not found" in str(exc).lower() else "PAGE_NOT_FOUND"
        if format == "json":
            return _json({"success": False, "error_code": err_code, "error": str(exc)})
        return f"**Error [{err_code}]:** {exc}"
    except Exception as exc:
        if format == "json":
            return _json({"success": False, "error_code": "INTERNAL_ERROR", "error": str(exc)})
        return f"**Error [INTERNAL_ERROR]:** {exc}"


def register_tools(mcp: Any) -> None:
    """Register InfoSys offline documentation tools on FastMCP server."""
    mcp.tool()(twincat_infosys_mshc_search)
    mcp.tool()(twincat_infosys_mshc_read)
