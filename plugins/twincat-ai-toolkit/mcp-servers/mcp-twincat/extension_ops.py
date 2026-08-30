"""TwinCAT VS Code / Cursor Extension management operations.

Provides packaging, status diagnostics, and automated installation/updates
for the local TwinCAT 3 Structured Text VS Code extension.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional


EXTENSION_PUBLISHER = "ElektroBeckhoff"
EXTENSION_NAME = "twincat-iecst"
EXTENSION_FULL_ID = f"{EXTENSION_PUBLISHER}.{EXTENSION_NAME}".lower()


def get_extension_dir() -> Path:
    """Return the absolute path to the vscode-extension directory."""
    # From plugins/twincat-ai-toolkit/mcp-servers/mcp-twincat/ -> plugins/twincat-ai-toolkit/vscode-extension
    mcp_dir = Path(__file__).resolve().parent
    ext_dir = mcp_dir.parent.parent / "vscode-extension"
    return ext_dir


def get_vsix_path() -> Path:
    """Return the expected path of the packaged VSIX file."""
    return get_extension_dir() / f"{EXTENSION_NAME}.vsix"


def get_package_json() -> Dict[str, Any]:
    """Read and return the parsed package.json from the extension directory."""
    pkg_path = get_extension_dir() / "package.json"
    if not pkg_path.is_file():
        return {}
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def build_vsix(force_rebuild_js: bool = True) -> Dict[str, Any]:
    """Build a standard VSIX package from the vscode-extension directory.

    If force_rebuild_js is True and npm is available, runs 'npm run build' first
    to recompile TypeScript / bundle dist/extension.js.
    """
    ext_dir = get_extension_dir()
    pkg = get_package_json()
    if not pkg:
        return {
            "success": False,
            "error": f"package.json not found in {ext_dir}",
        }

    dist_js = ext_dir / "dist" / "extension.js"
    npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_cmd and (force_rebuild_js or not dist_js.is_file()):
        try:
            subprocess.run(
                [npm_cmd, "run", "build"],
                cwd=str(ext_dir),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
        except Exception as exc:
            if not dist_js.is_file():
                return {
                    "success": False,
                    "error": f"Failed to build extension.js via npm: {exc}",
                }

    if not dist_js.is_file():
        return {
            "success": False,
            "error": f"extension.js missing at {dist_js}. Run 'npm run build' first.",
        }

    vsix_path = get_vsix_path()
    version = pkg.get("version", "0.1.0")
    display_name = pkg.get("displayName", EXTENSION_NAME)
    description = pkg.get("description", "")
    categories = ",".join(pkg.get("categories", ["Programming Languages"]))
    tags = ",".join(pkg.get("keywords", ["twincat", "plc", "structured text"]))
    engine = pkg.get("engines", {}).get("vscode", "^1.85.0")

    content_types = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="json" ContentType="application/json"/>\n'
        '  <Default Extension="vsixmanifest" ContentType="text/xml"/>\n'
        '  <Default Extension="js" ContentType="application/javascript"/>\n'
        '  <Default Extension="md" ContentType="text/markdown"/>\n'
        '  <Default Extension="txt" ContentType="text/plain"/>\n'
        "</Types>"
    )

    manifest = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011" '
        'xmlns:d="http://schemas.microsoft.com/developer/vsx-schema-design/2011">\n'
        "  <Metadata>\n"
        f'    <Identity Language="en-US" Id="{pkg.get("name", EXTENSION_NAME)}" '
        f'Version="{version}" Publisher="{pkg.get("publisher", EXTENSION_PUBLISHER)}"/>\n'
        f"    <DisplayName>{display_name}</DisplayName>\n"
        f'    <Description xml:space="preserve">{description}</Description>\n'
        f"    <Tags>{tags}</Tags>\n"
        f"    <Categories>{categories}</Categories>\n"
        "    <GalleryFlags>Public</GalleryFlags>\n"
        "    <Properties>\n"
        f'      <Property Id="Microsoft.VisualStudio.Code.Engine" Value="{engine}" />\n'
        '      <Property Id="Microsoft.VisualStudio.Code.ExtensionDependencies" Value="" />\n'
        '      <Property Id="Microsoft.VisualStudio.Code.ExtensionPack" Value="" />\n'
        '      <Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="workspace" />\n'
        '      <Property Id="Microsoft.VisualStudio.Code.LocalizedLanguages" Value="" />\n'
        "    </Properties>\n"
        "  </Metadata>\n"
        "  <Installation>\n"
        '    <InstallationTarget Id="Microsoft.VisualStudio.Code"/>\n'
        "  </Installation>\n"
        "  <Dependencies/>\n"
        "  <Assets>\n"
        '    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true" />\n'
        '    <Asset Type="Microsoft.VisualStudio.Code.Details" Path="extension/README.md" Addressable="true" />\n'
        "  </Assets>\n"
        "</PackageManifest>"
    )

    files_to_pack = [
        ("package.json", ext_dir / "package.json"),
        ("dist/extension.js", dist_js),
        ("language-configuration.json", ext_dir / "language-configuration.json"),
        ("README.md", ext_dir / "README.md"),
    ]

    # Include all syntax grammar files
    syn_dir = ext_dir / "syntaxes"
    if syn_dir.is_dir():
        for syn_file in syn_dir.glob("*.json"):
            if syn_file.is_file():
                files_to_pack.append((f"syntaxes/{syn_file.name}", syn_file))

    # Include all theme files
    theme_dir = ext_dir / "themes"
    if theme_dir.is_dir():
        for theme_file in theme_dir.glob("*.json"):
            if theme_file.is_file():
                files_to_pack.append((f"themes/{theme_file.name}", theme_file))

    # Bundle twincat_core Python package directly into extension/server/
    mcp_dir = Path(__file__).resolve().parent
    core_dir = mcp_dir / "twincat_core"
    if core_dir.is_dir():
        for py_file in core_dir.rglob("*"):
            if (
                py_file.is_file()
                and not py_file.name.endswith((".pyc", ".pyo"))
                and "__pycache__" not in py_file.parts
            ):
                rel = py_file.relative_to(mcp_dir)
                files_to_pack.append((f"server/{rel.as_posix()}", py_file))

    try:
        with zipfile.ZipFile(vsix_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("extension.vsixmanifest", manifest)
            for arcname, fpath in files_to_pack:
                if fpath.is_file():
                    zf.write(fpath, f"extension/{arcname}")

        return {
            "success": True,
            "vsix_path": str(vsix_path),
            "version": version,
            "size_bytes": vsix_path.stat().st_size,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Failed to package VSIX: {exc}",
        }


def detect_editor_cli() -> Optional[str]:
    """Detect 'cursor' or 'code' CLI executable in PATH or standard install paths."""
    # 1. PATH search
    for name in ["cursor.cmd", "cursor", "code.cmd", "code"]:
        path = shutil.which(name)
        if path:
            return path

    # 2. Windows LocalAppData Cursor check
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        cursor_cli = Path(local_app_data) / "Programs" / "cursor" / "resources" / "app" / "bin" / "cursor.cmd"
        if cursor_cli.is_file():
            return str(cursor_cli)
        code_cli = Path(local_app_data) / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"
        if code_cli.is_file():
            return str(code_cli)

    return None


def get_installed_extensions(cli_path: Optional[str] = None) -> Dict[str, str]:
    """Return dictionary of installed extension IDs -> version strings."""
    cli = cli_path or detect_editor_cli()
    if not cli:
        return {}

    try:
        res = subprocess.run(
            [cli, "--list-extensions", "--show-versions"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if res.returncode != 0:
            return {}

        installed: Dict[str, str] = {}
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if "@" in line:
                ext_id, ver = line.split("@", 1)
                installed[ext_id.strip().lower()] = ver.strip()
            else:
                installed[line.lower()] = "unknown"
        return installed
    except Exception:
        return {}


def get_extension_status() -> Dict[str, Any]:
    """Get the current installation and version status of the TwinCAT extension."""
    pkg = get_package_json()
    available_version = pkg.get("version", "0.1.0")
    vsix_path = get_vsix_path()

    cli = detect_editor_cli()
    cli_name = Path(cli).stem.lower() if cli else None

    installed_map = get_installed_extensions(cli)
    installed_version = installed_map.get(EXTENSION_FULL_ID)
    is_installed = installed_version is not None

    needs_update = False
    if is_installed and installed_version != "unknown":
        # Compare versions
        needs_update = installed_version != available_version

    if not is_installed:
        status = "not_installed"
        action = "TwinCAT 3 Structured Text extension is not installed. Call 'twincat_extension_install' to install it."
    elif needs_update:
        status = "update_available"
        action = f"Extension update available ({installed_version} -> {available_version}). Call 'twincat_extension_install' to update."
    else:
        status = "up_to_date"
        action = "Extension is installed and up-to-date."

    return {
        "extension_id": f"{pkg.get('publisher', EXTENSION_PUBLISHER)}.{pkg.get('name', EXTENSION_NAME)}",
        "display_name": pkg.get("displayName", EXTENSION_NAME),
        "available_version": available_version,
        "vsix_exists": vsix_path.is_file(),
        "vsix_path": str(vsix_path) if vsix_path.is_file() else None,
        "editor_cli": cli_name,
        "installed": is_installed,
        "installed_version": installed_version,
        "needs_update": needs_update,
        "status": status,
        "recommendation": action,
    }


def install_extension(force: bool = True, rebuild_vsix: bool = True) -> Dict[str, Any]:
    """Install or update the TwinCAT VS Code extension from the local VSIX file."""
    vsix_path = get_vsix_path()

    # Always re-package fresh when rebuild_vsix is True, or if VSIX is missing
    if rebuild_vsix or not vsix_path.is_file():
        pack_res = build_vsix(force_rebuild_js=True)
        if not pack_res.get("success"):
            return {
                "success": False,
                "error": f"Failed to build VSIX before installation: {pack_res.get('error')}",
            }

    cli = detect_editor_cli()
    if not cli:
        return {
            "success": False,
            "error": "No 'cursor' or 'code' CLI executable found in PATH or standard installation locations.",
            "manual_install_instructions": (
                f"Please open Cursor/VS Code, press Ctrl+Shift+P, select 'Extensions: Install from VSIX...', "
                f"and choose '{vsix_path}'."
            ),
        }

    cmd = [cli, "--install-extension", str(vsix_path)]
    if force:
        cmd.append("--force")

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if res.returncode == 0:
            # Refresh status
            status = get_extension_status()
            return {
                "success": True,
                "message": f"Successfully installed extension from {vsix_path.name}.",
                "cli_output": res.stdout.strip(),
                "status": status,
            }
        else:
            return {
                "success": False,
                "error": f"CLI install failed (exit {res.returncode}): {res.stderr.strip() or res.stdout.strip()}",
            }
    except Exception as exc:
        return {
            "success": False,
            "error": f"Exception during extension installation: {exc}",
        }


def auto_update_if_needed() -> Optional[Dict[str, Any]]:
    """Automatically check and install/update the extension in the background if missing or outdated."""
    try:
        status = get_extension_status()
        if not status.get("installed") or status.get("needs_update"):
            vsix_path = get_vsix_path()
            rebuild = not vsix_path.is_file()
            return install_extension(force=True, rebuild_vsix=rebuild)
    except Exception:
        pass
    return None

