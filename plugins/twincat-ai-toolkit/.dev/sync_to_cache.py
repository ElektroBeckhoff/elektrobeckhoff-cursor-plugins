#!/usr/bin/env python3
"""Sync local twincat-ai-toolkit plugin development files directly into Cursor's local plugin cache.

Allows manual local testing and live updates without waiting for GitHub Marketplace release.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Set

# Directories/files to ignore during synchronization
IGNORE_PATTERNS = {
    "__pycache__",
    ".pytest_cache",
    ".git",
    "node_modules",
    ".dev",
    "*.pyc",
    "*.pyo",
    "*.pyd",
    ".mypy_cache",
    ".ruff_cache",
}


def should_ignore(path: Path) -> bool:
    for part in path.parts:
        if part in IGNORE_PATTERNS or part.startswith(".pytest_cache"):
            return True
        if part.endswith(".pyc") or part.endswith(".pyo"):
            return True
    return False


def get_source_plugin_dir() -> Path:
    # Source is parent of .dev/
    return Path(__file__).resolve().parent.parent


def get_cursor_plugins_root() -> Path:
    user_home = Path.home()
    return user_home / ".cursor" / "plugins"


def find_target_cache_dirs(plugins_root: Path) -> List[Path]:
    targets: Set[Path] = set()

    if not plugins_root.is_dir():
        print(f"[!] Cursor plugins root not found at: {plugins_root}")
        return []

    # 1. Look in cache/elektrobeckhoff-cursor-plugins/twincat-ai-toolkit/
    cache_base = plugins_root / "cache" / "elektrobeckhoff-cursor-plugins" / "twincat-ai-toolkit"
    if cache_base.is_dir():
        for item in cache_base.iterdir():
            if item.is_dir():
                targets.add(item)

    # 2. Look in marketplaces/
    marketplaces = plugins_root / "marketplaces"
    if marketplaces.is_dir():
        for p in marketplaces.glob("**/twincat-ai-toolkit"):
            if p.is_dir() and ".dev" not in p.parts:
                targets.add(p)

    # 3. Fallback: if no cache folder exists yet, create default cache folder
    if not targets:
        default_target = cache_base / "local-dev"
        default_target.mkdir(parents=True, exist_ok=True)
        targets.add(default_target)

    return sorted(list(targets))


def build_and_install_vsix(source_dir: Path, install_to_editor: bool = True) -> None:
    """Ensure the latest VSIX package is built and optionally installed into Cursor/VSCode."""
    ext_dir = source_dir / "vscode-extension"
    if not ext_dir.is_dir():
        return

    mcp_dir = source_dir / "mcp-servers" / "mcp-twincat"
    if mcp_dir.is_dir() and str(mcp_dir) not in sys.path:
        sys.path.insert(0, str(mcp_dir))

    try:
        import extension_ops  # noqa: E402
        print("[*] Packaging twincat-iecst.vsix...")
        res = extension_ops.build_vsix()
        if res.get("success"):
            print(f"[+] VSIX built successfully ({res.get('size_bytes', 0):,} bytes)")
        else:
            print(f"[!] Warning building VSIX: {res.get('error')}")

        if install_to_editor:
            print("[*] Installing/updating extension in Cursor/VS Code...")
            inst_res = extension_ops.install_extension(force=True)
            if inst_res.get("success"):
                print(f"[+] Extension installed into editor: {inst_res.get('message')}")
            else:
                print(f"[!] Note on extension install: {inst_res.get('error')}")
    except Exception as exc:
        print(f"[!] Note: Could not process VSIX: {exc}")


def sync_directory(src: Path, dst: Path) -> int:
    """Synchronize source directory to destination directory, returning number of files copied."""
    dst.mkdir(parents=True, exist_ok=True)
    copied_count = 0

    # Copy files
    for root, dirs, files in os.walk(src):
        rel_root = Path(root).relative_to(src)

        # Filter out ignored directories in-place
        dirs[:] = [d for d in dirs if not should_ignore(rel_root / d)]

        target_root = dst / rel_root
        target_root.mkdir(parents=True, exist_ok=True)

        for f in files:
            src_file = Path(root) / f
            rel_file = rel_root / f
            if should_ignore(rel_file):
                continue

            dst_file = target_root / f
            # Check if copy needed (mtime or size difference)
            needs_copy = True
            if dst_file.is_file():
                try:
                    s_stat = src_file.stat()
                    d_stat = dst_file.stat()
                    if s_stat.st_size == d_stat.st_size and s_stat.st_mtime <= d_stat.st_mtime:
                        needs_copy = False
                except OSError:
                    needs_copy = True

            if needs_copy:
                try:
                    shutil.copy2(src_file, dst_file)
                    copied_count += 1
                except Exception as exc:
                    print(f"    [!] Error copying {rel_file}: {exc}")

    # Ensure .cache-complete exists in destination root
    cache_complete = dst / ".cache-complete"
    try:
        cache_complete.touch(exist_ok=True)
    except OSError:
        pass

    return copied_count


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Sync local twincat-ai-toolkit plugin to Cursor cache.")
    parser.add_argument("--no-install-ext", action="store_true", help="Skip installing the VSIX extension into Cursor/VS Code.")
    args = parser.parse_args()

    print("=" * 65)
    print(" TwinCAT AI Toolkit - Local Cursor Plugin Cache Synchronizer")
    print("=" * 65)

    source_dir = get_source_plugin_dir()
    print(f"Source plugin directory:\n  {source_dir}\n")

    build_and_install_vsix(source_dir, install_to_editor=not args.no_install_ext)

    plugins_root = get_cursor_plugins_root()
    targets = find_target_cache_dirs(plugins_root)

    if not targets:
        print("[!] No target cache directories found.")
        return

    print(f"\nFound {len(targets)} target cache location(s):")
    for t in targets:
        print(f"  -> {t}")

    print("\nSyncing files...")
    total_copied = 0
    for target in targets:
        count = sync_directory(source_dir, target)
        print(f"  [+] Updated {target.name}: {count} file(s) synchronized.")
        total_copied += count

    print("-" * 65)
    print(f"SUCCESS: Synchronized {total_copied} file(s) across all cache locations.")
    print("Tip: In Cursor, press Ctrl+Shift+P -> 'Developer: Reload Window' to apply changes.")
    print("=" * 65)


if __name__ == "__main__":
    main()
