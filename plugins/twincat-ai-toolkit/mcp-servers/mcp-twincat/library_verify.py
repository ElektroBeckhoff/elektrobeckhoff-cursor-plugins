"""Verify exported library version vs sample reference / Boot _Libraries."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional


_VERSION_RX = re.compile(r"(\d+\.\d+\.\d+\.\d+)")


def _find_libraries_dirs(start: str, max_depth: int = 5) -> list[Path]:
    root = Path(start)
    if not root.exists():
        return []
    found: list[Path] = []
    if root.is_file():
        root = root.parent
    for dirpath, dirnames, _files in os.walk(root):
        depth = Path(dirpath).relative_to(root).parts
        if len(depth) > max_depth:
            dirnames.clear()
            continue
        for d in list(dirnames):
            if d.lower() in ("_libraries", "libraries"):
                found.append(Path(dirpath) / d)
    return found


def _versions_in_dir(lib_dir: Path, library_name: str = "") -> list[str]:
    versions: list[str] = []
    name_l = (library_name or "").lower()
    try:
        for p in lib_dir.rglob("*"):
            if not p.is_file():
                continue
            s = p.name
            if name_l and name_l not in s.lower() and name_l not in str(p).lower():
                continue
            m = _VERSION_RX.search(s)
            if m:
                versions.append(m.group(1))
    except OSError:
        pass
    return sorted(set(versions))


def verify_library_versions(
    *,
    expected_version: str,
    library_name: str = "",
    sample_plcproj_path: str = "",
    sample_reference_version: str = "",
    search_roots: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Compare expected export version vs sample reference and Boot/_Libraries."""
    expected = (expected_version or "").strip()
    sample_ref = (sample_reference_version or "").strip()
    roots = list(search_roots or [])
    if sample_plcproj_path:
        roots.append(sample_plcproj_path)

    boot_versions: list[str] = []
    scanned: list[str] = []
    for root in roots:
        for lib_dir in _find_libraries_dirs(root):
            scanned.append(str(lib_dir))
            boot_versions.extend(_versions_in_dir(lib_dir, library_name))

    boot_versions = sorted(set(boot_versions))
    mismatches: list[str] = []
    if sample_ref and expected and sample_ref != expected:
        mismatches.append(
            f"sample_reference_version={sample_ref} != expected={expected}"
        )
    if expected and boot_versions and expected not in boot_versions:
        mismatches.append(
            f"expected={expected} not found in Boot/_Libraries "
            f"(found={boot_versions})"
        )

    incomplete = not scanned
    ok = not mismatches and not incomplete and bool(expected)

    next_actions: list[str] = []
    if mismatches or incomplete:
        next_actions = ["refresh_references", "rebuild", "activate"]

    return {
        "success": ok,
        "ok": ok,
        "expected_version": expected,
        "library_name": library_name or "",
        "sample_reference_version": sample_ref,
        "boot_library_versions": boot_versions,
        "scanned_library_dirs": scanned,
        "mismatches": mismatches,
        "verify_incomplete": incomplete,
        "next_actions": next_actions,
        "message": (
            "Library version matches sample/boot"
            if ok
            else (
                "Library verify incomplete (no _Libraries folder found)"
                if incomplete
                else "Library version mismatch: " + "; ".join(mismatches)
            )
        ),
        "error_code": (
            "" if ok else ("verify_incomplete" if incomplete else "library_version_mismatch")
        ),
    }
