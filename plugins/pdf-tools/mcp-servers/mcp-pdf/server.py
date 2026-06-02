"""
PDF Tools MCP Server for Cursor IDE.

Exposes opendataloader-pdf conversion as MCP tools that Cursor can call
directly: status check, PDF-to-Markdown/JSON/HTML conversion, and hybrid
mode for complex documents (scans, borderless tables, formulas, charts).

Transport: stdio  (Cursor starts this process as a child)

IMPORTANT: opendataloader-pdf spawns a Java subprocess whose logging
(java.util.logging) writes to stdout. Since MCP uses stdout as the
JSON-RPC wire, we must redirect fd 1 → fd 2 during conversion calls
to prevent Java log lines from corrupting the protocol stream.
"""

import contextlib
import json
import logging
import os
import subprocess
import sys
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("pdf-mcp")

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("PDF Tools")


@contextlib.contextmanager
def _stdout_to_stderr():
    """Redirect fd 1 (stdout) to fd 2 (stderr) at the OS level.

    This ensures child processes (Java JVM) cannot write log output
    into the MCP JSON-RPC channel. Python-level sys.stdout is also
    swapped so any print() calls go to stderr.
    """
    stdout_fd = os.dup(1)
    os.dup2(2, 1)
    old_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old_stdout
        os.dup2(stdout_fd, 1)
        os.close(stdout_fd)


def _check_java() -> tuple[bool, str]:
    """Return (available, version_string) for Java."""
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stderr or result.stdout
        for line in output.splitlines():
            if "version" in line.lower():
                return True, line.strip()
        return True, output.splitlines()[0].strip() if output.strip() else "unknown"
    except FileNotFoundError:
        return False, "Java not found in PATH"
    except Exception as e:
        return False, f"Error checking Java: {e}"


def _check_opendataloader() -> tuple[bool, str]:
    """Return (available, version_string) for opendataloader-pdf."""
    try:
        import opendataloader_pdf
        version = getattr(opendataloader_pdf, "__version__", "installed (version unknown)")
        return True, str(version)
    except ImportError:
        return False, "opendataloader-pdf not installed. Run: pip install opendataloader-pdf"


@mcp.tool()
def pdf_status() -> str:
    """Check whether opendataloader-pdf and Java 11+ are installed.

    Returns installation status for both dependencies.
    Call this before pdf_convert to verify prerequisites."""

    java_ok, java_info = _check_java()
    odl_ok, odl_info = _check_opendataloader()

    status = {
        "java": {"installed": java_ok, "info": java_info},
        "opendataloader_pdf": {"installed": odl_ok, "info": odl_info},
        "ready": java_ok and odl_ok,
    }

    if not status["ready"]:
        missing = []
        if not java_ok:
            missing.append("Java 11+ (https://adoptium.net)")
        if not odl_ok:
            missing.append("opendataloader-pdf (pip install opendataloader-pdf)")
        status["action_required"] = f"Install missing: {', '.join(missing)}"

    return json.dumps(status, indent=2, ensure_ascii=False)


@mcp.tool()
def pdf_convert(
    input_path: str,
    output_dir: str = "",
    format: str = "markdown",
    image_output: str = "off",
    use_struct_tree: bool = False,
) -> str:
    """Convert PDF file(s) to Markdown, JSON, HTML, or text.

    Uses opendataloader-pdf for deterministic local extraction.
    Supports digital PDFs with correct reading order, tables, headings,
    lists, and images. No GPU required.

    Args:
        input_path: Path to a PDF file or folder containing PDFs.
                    Separate multiple paths with commas.
        output_dir: Output directory for converted files.
                    Defaults to a sibling 'output/' folder next to input.
        format: Output format(s). Comma-separated: markdown, json, html, text, tagged-pdf.
                Default: "markdown".
        image_output: Image handling: "off" (skip), "embedded" (Base64), "external" (files).
                      Default: "off".
        use_struct_tree: Use native PDF structure tags when available. Default: false.
    """
    import opendataloader_pdf

    paths = [p.strip() for p in input_path.split(",") if p.strip()]
    if not paths:
        return json.dumps({"success": False, "error": "No input path provided."})

    for p in paths:
        if not os.path.exists(p):
            return json.dumps({"success": False, "error": f"Path not found: {p}"})

    if not output_dir:
        first = paths[0]
        if os.path.isfile(first):
            output_dir = os.path.join(os.path.dirname(first), "output")
        else:
            output_dir = os.path.join(first, "output")

    os.makedirs(output_dir, exist_ok=True)

    kwargs = {
        "input_path": paths if len(paths) > 1 else paths[0],
        "output_dir": output_dir,
        "format": format,
    }

    if image_output != "off":
        kwargs["image_output"] = image_output

    if use_struct_tree:
        kwargs["use_struct_tree"] = True

    try:
        with _stdout_to_stderr():
            opendataloader_pdf.convert(**kwargs)
    except Exception as e:
        log.error("pdf_convert failed: %s", e)
        return json.dumps({
            "success": False,
            "error": str(e),
            "hint": "Ensure Java 11+ is installed and input is a valid PDF.",
        }, indent=2, ensure_ascii=False)

    output_files = []
    for root, _dirs, files in os.walk(output_dir):
        for f in files:
            full = os.path.join(root, f)
            output_files.append(full)

    return json.dumps({
        "success": True,
        "output_dir": output_dir,
        "files": output_files,
        "format": format,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
def pdf_convert_hybrid(
    input_path: str,
    output_dir: str = "",
    format: str = "markdown",
    hybrid: str = "docling-fast",
    hybrid_mode: str = "",
    force_ocr: bool = False,
    ocr_lang: str = "",
    image_output: str = "off",
    use_struct_tree: bool = False,
) -> str:
    """Convert complex PDFs using hybrid mode (AI backend + local processing).

    Hybrid mode routes complex pages (scanned content, borderless tables,
    formulas, charts) to an AI backend for higher accuracy. Simple pages
    stay local. The backend runs locally -- no cloud required.

    IMPORTANT: The hybrid backend server must be running before calling this.
    Start it with: opendataloader-pdf-hybrid --port 5002

    Args:
        input_path: Path to a PDF file or folder. Comma-separated for multiple.
        output_dir: Output directory. Defaults to sibling 'output/' folder.
        format: Output format(s): markdown, json, html, text. Default: "markdown".
        hybrid: Hybrid backend name. Default: "docling-fast".
        hybrid_mode: "full" for formula/picture enrichment, empty for auto.
        force_ocr: Force OCR for scanned/image-based PDFs. Default: false.
        ocr_lang: OCR language codes, comma-separated (e.g. "en,de,ko"). Default: auto.
        image_output: "off", "embedded" (Base64), "external" (files). Default: "off".
        use_struct_tree: Use native PDF structure tags. Default: false.
    """
    import opendataloader_pdf

    paths = [p.strip() for p in input_path.split(",") if p.strip()]
    if not paths:
        return json.dumps({"success": False, "error": "No input path provided."})

    for p in paths:
        if not os.path.exists(p):
            return json.dumps({"success": False, "error": f"Path not found: {p}"})

    if not output_dir:
        first = paths[0]
        if os.path.isfile(first):
            output_dir = os.path.join(os.path.dirname(first), "output")
        else:
            output_dir = os.path.join(first, "output")

    os.makedirs(output_dir, exist_ok=True)

    kwargs = {
        "input_path": paths if len(paths) > 1 else paths[0],
        "output_dir": output_dir,
        "format": format,
        "hybrid": hybrid,
    }

    if hybrid_mode:
        kwargs["hybrid_mode"] = hybrid_mode
    if force_ocr:
        kwargs["force_ocr"] = True
    if ocr_lang:
        kwargs["ocr_lang"] = ocr_lang
    if image_output != "off":
        kwargs["image_output"] = image_output
    if use_struct_tree:
        kwargs["use_struct_tree"] = True

    try:
        with _stdout_to_stderr():
            opendataloader_pdf.convert(**kwargs)
    except Exception as e:
        log.error("pdf_convert_hybrid failed: %s", e)
        hint = "Ensure the hybrid backend is running: opendataloader-pdf-hybrid --port 5002"
        return json.dumps({
            "success": False,
            "error": str(e),
            "hint": hint,
        }, indent=2, ensure_ascii=False)

    output_files = []
    for root, _dirs, files in os.walk(output_dir):
        for f in files:
            full = os.path.join(root, f)
            output_files.append(full)

    return json.dumps({
        "success": True,
        "output_dir": output_dir,
        "files": output_files,
        "format": format,
        "hybrid": hybrid,
    }, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run(transport="stdio")
