"""
VS Code and Cursor extension management MCP tools for TwinCAT 3 IEC 61131-3.
"""

from __future__ import annotations

from typing import Any
import extension_ops
from .common import _json


def twincat_extension_status() -> str:
    """Check the installation and version status of the TwinCAT 3 VS Code / Cursor extension.

    Reports whether 'elektrobeckhoff.twincat-iecst' is installed in Cursor/VS Code,
    its installed version, available local VSIX version, and whether an update is available.
    """
    try:
        return _json(extension_ops.get_extension_status())
    except Exception as exc:
        return _json({"error": str(exc)})


def twincat_extension_install(force: bool = True) -> str:
    """Install or update the TwinCAT 3 Structured Text VS Code / Cursor extension from local VSIX.

    Builds or packages the .vsix package from the local repository if necessary, then invokes
    the editor CLI ('cursor' or 'code') to install/update the extension with syntax highlighting
    and language server capabilities.
    """
    try:
        return _json(extension_ops.install_extension(force=force))
    except Exception as exc:
        return _json({"error": str(exc)})


def twincat_extension_build() -> str:
    """Build the local TwinCAT 3 VS Code extension VSIX package from source.

    Packages all extension manifests, grammars, and bundled assets into twincat-iecst.vsix.
    """
    try:
        return _json(extension_ops.build_vsix())
    except Exception as exc:
        return _json({"error": str(exc)})


def register_tools(mcp: Any) -> None:
    """Register extension tools on FastMCP server."""
    mcp.tool()(twincat_extension_status)
    mcp.tool()(twincat_extension_install)
    mcp.tool()(twincat_extension_build)
