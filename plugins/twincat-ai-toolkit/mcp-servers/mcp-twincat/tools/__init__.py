"""
TwinCAT MCP Server tools package.
"""

from __future__ import annotations

from typing import Any

from . import (
    ads,
    autodocs,
    common,
    core_syntax,
    extension,
    formatter,
    infosys,
    migrator,
    plcproj,
    solution,
    target_io,
    umrt,
)


def register_all_tools(mcp: Any) -> None:
    """Register all modular MCP tools on the FastMCP application."""
    core_syntax.register_tools(mcp)
    solution.register_tools(mcp)
    extension.register_tools(mcp)
    target_io.register_tools(mcp)
    umrt.register_tools(mcp)
    ads.register_tools(mcp)
    migrator.register_tools(mcp)
    autodocs.register_tools(mcp)
    plcproj.register_tools(mcp)
    infosys.register_tools(mcp)
    formatter.register_tools(mcp)
