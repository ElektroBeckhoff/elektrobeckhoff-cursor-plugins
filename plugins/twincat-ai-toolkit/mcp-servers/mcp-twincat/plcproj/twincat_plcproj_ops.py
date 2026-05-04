#!/usr/bin/env python3
"""
TwinCAT 3 PlcProject File Operations.

Verify and sync .plcproj files against the actual disk state.  Optionally
repair missing / duplicate / invalid object GUIDs in Tc* source files.

Usage:
    python twincat_plcproj_ops.py --input "path/to/project"
    python twincat_plcproj_ops.py --input "path/to/project" --verify-only
    python twincat_plcproj_ops.py --input "path/to/project" --force
    python twincat_plcproj_ops.py --input "path/to/project" --dry-run
    python twincat_plcproj_ops.py --input "path/to/project" --ensure-object-guids
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import re
import shutil
import sys
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

SCRIPT_VERSION = "1.0.0"

log = logging.getLogger("plcproj-ops")

# ================================================================
#  Constants
# ================================================================

DEFAULT_COMPILE_EXTENSIONS: Set[str] = {
    ".tcpou", ".tcdut", ".tcio", ".tcgvl", ".tctto",
}

EXCLUDED_DIR_NAMES: Set[str] = {
    "_compileinfo", "_libraries", ".git", "bin", "obj",
}

COMPILE_PATTERN = r"(?s)  <ItemGroup>\s*<Compile Include=\"[^\"]+\">.*?</ItemGroup>"
FOLDER_PATTERN = r"(?s)  <ItemGroup>\s*(?:<Folder Include=\"[^\"]+\"(?:\s*/>|\s*>.*?</Folder>)\s*)+</ItemGroup>"

NL = "\r\n"


# ================================================================
#  Data classes
# ================================================================

@dataclass
class PlcProjConfig:
    """CLI / MCP configuration."""
    input_path: str = ""
    plcproj_path: str = ""
    verify_only: bool = False
    force: bool = False
    dry_run: bool = False
    backup: bool = True
    skip_folder_sync: bool = False
    ensure_object_guids: bool = False
    compile_extensions: Set[str] = field(default_factory=lambda: set(DEFAULT_COMPILE_EXTENSIONS))
    log_level: str = "INFO"


@dataclass
class DiskState:
    """Result of scanning the project directory."""
    base_dir: str = ""
    ordered: List[str] = field(default_factory=list)
    folder_set: Set[str] = field(default_factory=set)


@dataclass
class VerifyResult:
    """Outcome of verifying plcproj vs. disk."""
    ok: bool = True
    exit_code: int = 0
    error_message: Optional[str] = None
    missing_compile: List[str] = field(default_factory=list)
    extra_compile: List[str] = field(default_factory=list)
    folder_missing: List[str] = field(default_factory=list)
    folder_extra: List[str] = field(default_factory=list)
    efb_folders: Dict[str, str] = field(default_factory=dict)
    efb_compile: Dict[str, str] = field(default_factory=dict)


@dataclass
class GuidRepairEntry:
    """Single GUID repair action."""
    file_name: str = ""
    reason: str = ""


@dataclass
class SyncReport:
    """Outcome of a sync operation."""
    success: bool = True
    verify_result: Optional[VerifyResult] = None
    compile_count: int = 0
    folder_count: int = 0
    plcproj_written: bool = False
    plcproj_unchanged: bool = False
    guids_repaired: List[GuidRepairEntry] = field(default_factory=list)
    dry_run: bool = False
    warnings: List[str] = field(default_factory=list)


# ================================================================
#  Path helpers
# ================================================================

def _read_text_raw(path: Path) -> str:
    """Read a file preserving exact newlines (no universal-newline translation)."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, ValueError):
            continue
    return raw.decode("utf-8", errors="replace")


def _is_excluded_dir(rel_path: str) -> bool:
    """Check whether the first path segment is an excluded directory."""
    norm = rel_path.replace("/", os.sep).replace("\\", os.sep).lstrip(os.sep)
    if not norm:
        return False
    first = norm.split(os.sep)[0]
    return first.lower() in EXCLUDED_DIR_NAMES


def _relative_path(base: str, full: str) -> str:
    """Compute backslash-separated relative path (TwinCAT convention)."""
    base_norm = os.path.normpath(base)
    full_norm = os.path.normpath(full)
    if not full_norm.lower().startswith(base_norm.lower()):
        raise ValueError(f"Path not under base: {full}")
    rel = full_norm[len(base_norm):]
    rel = rel.lstrip(os.sep).lstrip("/")
    return rel.replace("/", "\\")


def resolve_plcproj_path(
    plcproj_path: str = "",
    project_root: str = "",
) -> Path:
    """Find and validate the .plcproj file path.

    Either provide an explicit plcproj_path or a project_root directory
    containing exactly one .plcproj file.
    """
    if plcproj_path:
        p = Path(plcproj_path).resolve()
        if not p.is_file():
            raise FileNotFoundError(f"plcproj not found: {plcproj_path}")
        return p

    if not project_root:
        raise ValueError("Specify --input (plcproj path or project root directory).")

    root = Path(project_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"ProjectRoot not found: {project_root}")

    candidates = list(root.glob("*.plcproj"))
    if len(candidates) == 0:
        raise FileNotFoundError(f"No .plcproj under: {root}")
    if len(candidates) > 1:
        names = ", ".join(c.name for c in candidates)
        raise ValueError(f"Multiple .plcproj in {root} -- specify explicit path. Found: {names}")
    return candidates[0].resolve()


# ================================================================
#  Disk scanning
# ================================================================

def scan_disk_state(
    proj_file: Path,
    extensions: Set[str] | None = None,
    skip_folder_sync: bool = False,
) -> DiskState:
    """Scan the project directory for Tc* source files and subfolders."""
    if extensions is None:
        extensions = DEFAULT_COMPILE_EXTENSIONS

    base = str(proj_file.parent)
    ext_lower = {e.lower() for e in extensions}

    compile_files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = _relative_path(base, dirpath) if dirpath != base else ""
        if rel_dir and _is_excluded_dir(rel_dir):
            dirnames.clear()
            continue
        dirnames[:] = [
            d for d in dirnames
            if not _is_excluded_dir(os.path.join(rel_dir, d) if rel_dir else d)
        ]
        for fname in filenames:
            _, ext = os.path.splitext(fname)
            if ext.lower() in ext_lower:
                full = os.path.join(dirpath, fname)
                compile_files.append(_relative_path(base, full))

    compile_files = sorted(set(compile_files), key=lambda s: s.lower())

    ordered: List[str] = []
    plc_task = "PlcTask.TcTTO"
    if any(f.lower() == plc_task.lower() for f in compile_files):
        matched = next(f for f in compile_files if f.lower() == plc_task.lower())
        ordered.append(matched)
        compile_files = [f for f in compile_files if f.lower() != plc_task.lower()]
    ordered.extend(compile_files)

    folder_set: Set[str] = set()
    if not skip_folder_sync:
        for dirpath, dirnames, _ in os.walk(base):
            rel_dir = _relative_path(base, dirpath) if dirpath != base else ""
            if rel_dir and _is_excluded_dir(rel_dir):
                dirnames.clear()
                continue
            dirnames[:] = [
                d for d in dirnames
                if not _is_excluded_dir(os.path.join(rel_dir, d) if rel_dir else d)
            ]
            if rel_dir:
                folder_set.add(rel_dir)

    return DiskState(base_dir=base, ordered=ordered, folder_set=folder_set)


# ================================================================
#  ExcludeFromBuild parsing
# ================================================================

def _parse_efb_folders(folder_block_xml: str) -> Dict[str, str]:
    """Extract folder paths with ExcludeFromBuild and their value (true/false)."""
    efb: Dict[str, str] = {}
    for m in re.finditer(
        r'<Folder Include="([^"]+)"[^>]*>\s*<ExcludeFromBuild>(true|false)</ExcludeFromBuild>',
        folder_block_xml, re.DOTALL | re.IGNORECASE,
    ):
        efb[m.group(1).lower()] = m.group(2).lower()
    return efb


def _parse_efb_compile(compile_block_xml: str) -> Dict[str, str]:
    """Extract compile paths with ExcludeFromBuild and their value (true/false).

    Two-step: isolate each <Compile>...</Compile> block first, then check
    for ExcludeFromBuild inside that block (avoids cross-boundary matches).
    """
    efb: Dict[str, str] = {}
    for m in re.finditer(
        r'<Compile Include="([^"]+)"[^>]*>([\s\S]*?)</Compile>',
        compile_block_xml,
    ):
        inner = m.group(2)
        efb_m = re.search(
            r'<ExcludeFromBuild>(true|false)</ExcludeFromBuild>',
            inner, re.IGNORECASE,
        )
        if efb_m:
            efb[m.group(1).lower()] = efb_m.group(1).lower()
    return efb


# ================================================================
#  XML block builders
# ================================================================

def build_compile_block(
    ordered: List[str],
    nl: str = NL,
    efb_compile: Dict[str, str] | None = None,
) -> str:
    """Build the <ItemGroup> XML block for Compile entries.

    *efb_compile* maps lowered relative paths to ``"true"`` or ``"false"``
    for the ``<ExcludeFromBuild>`` child element.  Paths not in the dict
    get no tag (TwinCAT default = compiled).
    """
    _efb = {k.lower(): v for k, v in (efb_compile or {}).items()}
    parts = [f"  <ItemGroup>{nl}"]
    for rel in ordered:
        parts.append(f'    <Compile Include="{rel}">{nl}')
        parts.append(f"      <SubType>Code</SubType>{nl}")
        val = _efb.get(rel.lower())
        if val is not None:
            parts.append(f"      <ExcludeFromBuild>{val}</ExcludeFromBuild>{nl}")
        parts.append(f"    </Compile>{nl}")
    parts.append("  </ItemGroup>")
    return "".join(parts)


def build_folder_block(
    folder_set: Set[str],
    nl: str = NL,
    efb_folders: Dict[str, str] | None = None,
) -> str:
    """Build the <ItemGroup> XML block for Folder entries.

    *efb_folders* maps lowered folder paths to ``"true"`` or ``"false"``
    for the ``<ExcludeFromBuild>`` child element.  Folders not in the
    dict are written as self-closing tags (TwinCAT default).
    """
    _efb = {k.lower(): v for k, v in (efb_folders or {}).items()}
    parts: List[str] = []
    for f in sorted(folder_set, key=lambda s: s.lower()):
        val = _efb.get(f.lower())
        if val is not None:
            parts.append(
                f'    <Folder Include="{f}">{nl}'
                f'      <ExcludeFromBuild>{val}</ExcludeFromBuild>{nl}'
                f'    </Folder>'
            )
        else:
            parts.append(f'    <Folder Include="{f}" />')
    return f"  <ItemGroup>{nl}" + nl.join(parts) + f"{nl}  </ItemGroup>"


# ================================================================
#  Verify
# ================================================================

def verify_plcproj(
    proj_file: Path,
    extensions: Set[str] | None = None,
    skip_folder_sync: bool = False,
) -> VerifyResult:
    """Compare .plcproj Compile/Folder ItemGroups against actual disk state."""
    state = scan_disk_state(proj_file, extensions, skip_folder_sync)

    xml = _read_text_raw(proj_file)
    compile_match = re.search(COMPILE_PATTERN, xml)
    if not compile_match:
        return VerifyResult(
            ok=False, exit_code=2,
            error_message="Could not find Compile ItemGroup block in plcproj.",
        )

    proj_compile = re.findall(r'<Compile Include="([^"]+)"', compile_match.group())
    expected_compile = {p.lower() for p in state.ordered}
    actual_compile = {p.lower() for p in proj_compile}

    missing_compile = [p for p in state.ordered if p.lower() not in actual_compile]
    extra_compile = sorted(
        {p for p in proj_compile if p.lower() not in expected_compile},
        key=lambda s: s.lower(),
    )

    efb_compile = _parse_efb_compile(compile_match.group())

    ok = len(missing_compile) == 0 and len(extra_compile) == 0
    folder_missing: List[str] = []
    folder_extra: List[str] = []
    efb_folders: Dict[str, str] = {}

    if not skip_folder_sync:
        tail = xml[compile_match.end():]
        folder_match = re.search(FOLDER_PATTERN, tail)
        if not folder_match:
            return VerifyResult(
                ok=False, exit_code=2,
                error_message="No Folder-only ItemGroup found after Compile block.",
                missing_compile=missing_compile,
                extra_compile=extra_compile,
            )
        efb_folders = _parse_efb_folders(folder_match.group())
        proj_folder_raw = re.findall(r'<Folder Include="([^"]+)"', folder_match.group())
        proj_folders = [p for p in proj_folder_raw if not _is_excluded_dir(p)]

        expected_folder = {p.lower() for p in state.folder_set}
        actual_folder = {p.lower() for p in proj_folders}

        folder_missing = sorted(
            [p for p in state.folder_set if p.lower() not in actual_folder],
            key=lambda s: s.lower(),
        )
        folder_extra = sorted(
            {p for p in proj_folders if p.lower() not in expected_folder},
            key=lambda s: s.lower(),
        )
        ok = ok and len(folder_missing) == 0 and len(folder_extra) == 0

    if ok:
        return VerifyResult(
            ok=True, exit_code=0,
            efb_folders=efb_folders, efb_compile=efb_compile,
        )

    return VerifyResult(
        ok=False, exit_code=1,
        missing_compile=missing_compile,
        extra_compile=extra_compile,
        folder_missing=folder_missing,
        folder_extra=folder_extra,
        efb_folders=efb_folders,
        efb_compile=efb_compile,
    )


# ================================================================
#  XML replacement
# ================================================================

def replace_xml_blocks(
    xml: str,
    compile_block: str,
    folder_block: str,
    skip_folder_sync: bool = False,
) -> str:
    """Replace Compile and Folder ItemGroup blocks in plcproj XML."""
    # Use lambda to avoid re.sub interpreting backslashes in paths as backreferences
    new_xml = re.sub(COMPILE_PATTERN, lambda _: compile_block, xml, count=1)

    if not skip_folder_sync:
        if re.search(FOLDER_PATTERN, new_xml):
            new_xml = re.sub(FOLDER_PATTERN, lambda _: folder_block, new_xml, count=1)
        else:
            if compile_block not in new_xml:
                raise RuntimeError("Internal error: compile block not found after replace.")
            new_xml = new_xml.replace(compile_block, compile_block + NL + folder_block, 1)

    return new_xml


# ================================================================
#  GUID repair
# ================================================================

_ROOT_TAG_RE = re.compile(r"<(POU|GVL|Itf|DUT)\s+([^>]+)>", re.IGNORECASE)
_ID_ATTR_RE = re.compile(r'\s+Id="([^"]*)"', re.IGNORECASE)
_NAME_ATTR_RE = re.compile(r'(Name="[^"]*")', re.IGNORECASE)


def _is_valid_guid(value: str) -> bool:
    """Check whether *value* is a valid GUID (with or without braces)."""
    t = value.strip().strip("{}")
    try:
        uuid.UUID(t)
        return True
    except ValueError:
        return False


def _normalize_guid(value: str) -> str:
    """Normalize a GUID string to lowercase without braces."""
    t = value.strip().strip("{}")
    return str(uuid.UUID(t)).lower()


def _build_root_open_tag(tag: str, attrs_no_id: str, guid_d: str) -> str:
    """Reconstruct the root open tag with a single Id attribute after Name."""
    id_attr = f' Id="{{{guid_d}}}"'
    trimmed = attrs_no_id.strip()
    if re.search(r"Name\s*=", trimmed, re.IGNORECASE):
        new_attrs = _NAME_ATTR_RE.sub(r"\1" + id_attr, trimmed, count=1)
    else:
        new_attrs = (id_attr.lstrip() + " " + trimmed).strip()
    return f"<{tag} {new_attrs}>"


@dataclass
class _Phase1Result:
    content: str
    guid_key: Optional[str]
    modified: bool
    reason: str


def _repair_object_id_phase1(content: str) -> _Phase1Result:
    """Normalize the root element Id attribute of a single Tc* file."""
    m = _ROOT_TAG_RE.search(content)
    if not m:
        return _Phase1Result(content, None, False, "no_root")

    tag = m.group(1)
    attrs = m.group(2)
    id_matches = list(_ID_ATTR_RE.finditer(attrs))

    valid_keys: List[str] = []
    for im in id_matches:
        if _is_valid_guid(im.group(1)):
            valid_keys.append(_normalize_guid(im.group(1)))
    unique_valid = sorted(set(valid_keys))

    attrs_no_id = _ID_ATTR_RE.sub("", attrs).strip()

    def _replace(guid_d: str, reason: str) -> _Phase1Result:
        new_open = _build_root_open_tag(tag, attrs_no_id, guid_d)
        new_content = content[:m.start()] + new_open + content[m.end():]
        return _Phase1Result(new_content, guid_d.lower(), True, reason)

    if len(id_matches) == 0:
        return _replace(str(uuid.uuid4()), "missing")

    if len(id_matches) == 1:
        if len(unique_valid) == 1:
            return _Phase1Result(content, unique_valid[0], False, "ok")
        return _replace(str(uuid.uuid4()), "invalid")

    # Multiple Id attributes
    if len(unique_valid) == 1:
        g = str(uuid.UUID(unique_valid[0]))
        reason = "multi_attr"
    else:
        g = str(uuid.uuid4())
        reason = "multi_attr_invalid"
    return _replace(g, reason)


def _set_root_tag_id(content: str, new_guid_d: str) -> str:
    """Replace or insert the Id attribute on the root Tc* element."""
    m = _ROOT_TAG_RE.search(content)
    if not m:
        return content
    tag = m.group(1)
    attrs = m.group(2)
    new_id = f'Id="{{{new_guid_d}}}"'

    if _ID_ATTR_RE.search(attrs):
        new_attrs = _ID_ATTR_RE.sub(f" {new_id}", attrs, count=1)
    elif re.search(r"Name\s*=", attrs, re.IGNORECASE):
        new_attrs = _NAME_ATTR_RE.sub(rf"\1 {new_id}", attrs, count=1)
    else:
        new_attrs = (new_id + " " + attrs).strip()

    new_open = f"<{tag} {new_attrs}>"
    return content[:m.start()] + new_open + content[m.end():]


def repair_object_guids(
    base_dir: str,
    extensions: Set[str] | None = None,
    dry_run: bool = False,
) -> List[GuidRepairEntry]:
    """Fix missing, invalid, or duplicate object GUIDs in Tc* source files.

    Phase 1: Per-file normalization (missing, invalid, multi-attribute).
    Phase 2: Cross-file deduplication.
    """
    if extensions is None:
        extensions = DEFAULT_COMPILE_EXTENSIONS
    ext_lower = {e.lower() for e in extensions}
    repairs: List[GuidRepairEntry] = []

    targets: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(base_dir):
        rel = _relative_path(base_dir, dirpath) if dirpath != base_dir else ""
        if rel and _is_excluded_dir(rel):
            dirnames.clear()
            continue
        dirnames[:] = [
            d for d in dirnames
            if not _is_excluded_dir(os.path.join(rel, d) if rel else d)
        ]
        for fname in sorted(filenames):
            _, ext = os.path.splitext(fname)
            if ext.lower() in ext_lower:
                targets.append(Path(dirpath) / fname)

    path_to_text: Dict[str, str] = {}
    path_to_guid: Dict[str, Optional[str]] = {}
    path_to_reason: Dict[str, str] = {}

    for fp in targets:
        orig = _read_text_raw(fp)
        r = _repair_object_id_phase1(orig)
        path_to_text[str(fp)] = r.content
        path_to_guid[str(fp)] = r.guid_key
        path_to_reason[str(fp)] = r.reason

    # Phase 2: deduplicate across files
    by_key: Dict[str, List[str]] = {}
    for p, gk in path_to_guid.items():
        if gk is None:
            continue
        by_key.setdefault(gk, []).append(p)

    for key, paths in by_key.items():
        if len(paths) <= 1:
            continue
        sorted_paths = sorted(paths)
        for dup_path in sorted_paths[1:]:
            new_g = str(uuid.uuid4())
            path_to_text[dup_path] = _set_root_tag_id(path_to_text[dup_path], new_g)
            path_to_reason[dup_path] = "duplicate_across_files"

    for fp in targets:
        p = str(fp)
        final = path_to_text[p]
        orig = _read_text_raw(fp)
        if final == orig:
            continue

        reason = path_to_reason[p]
        entry = GuidRepairEntry(file_name=fp.name, reason=reason)
        repairs.append(entry)

        if dry_run:
            log.info("DRY RUN - would fix object Id (%s): %s", reason, fp.name)
        else:
            fp.write_text(final, encoding="utf-8", newline="")
            log.info("Fixed object Id (%s): %s", reason, fp.name)

    return repairs


# ================================================================
#  Backup
# ================================================================

def create_backup(proj_file: Path) -> Path:
    """Create a timestamped backup of the plcproj file."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{proj_file.stem}_{ts}{proj_file.suffix}.bak"
    backup_path = proj_file.parent / backup_name
    shutil.copy2(str(proj_file), str(backup_path))
    log.info("Backup created: %s", backup_path.name)
    return backup_path


# ================================================================
#  Sync (main pipeline)
# ================================================================

def sync_plcproj(cfg: PlcProjConfig) -> SyncReport:
    """Full sync pipeline: resolve, scan, optionally verify, rebuild, write."""
    report = SyncReport(dry_run=cfg.dry_run)

    try:
        # Resolve plcproj
        input_p = Path(cfg.input_path)
        if input_p.is_file() and input_p.suffix.lower() == ".plcproj":
            proj_file = resolve_plcproj_path(plcproj_path=cfg.input_path)
        else:
            proj_file = resolve_plcproj_path(project_root=cfg.input_path)
    except (FileNotFoundError, ValueError) as exc:
        report.success = False
        report.warnings.append(str(exc))
        return report

    log.info("plcproj: %s", proj_file)

    state = scan_disk_state(proj_file, cfg.compile_extensions, cfg.skip_folder_sync)
    report.compile_count = len(state.ordered)
    report.folder_count = len(state.folder_set)

    xml = _read_text_raw(proj_file)
    compile_match = re.search(COMPILE_PATTERN, xml)
    if not compile_match:
        report.success = False
        report.warnings.append("Could not find Compile ItemGroup block in plcproj.")
        return report

    # Verify (unless force)
    if not cfg.force:
        vr = verify_plcproj(proj_file, cfg.compile_extensions, cfg.skip_folder_sync)
        report.verify_result = vr
        if not vr.ok:
            report.success = False
            report.warnings.append(
                "plcproj out of sync with disk. Use force=true after adding/removing files."
            )
            return report
        log.info("Verify OK - plcproj matches disk.")
    else:
        log.info("Skip verify (force); plcproj will be rebuilt from disk.")

    # Extract existing ExcludeFromBuild info before rebuilding
    efb_compile = _parse_efb_compile(compile_match.group())

    tail = xml[compile_match.end():]
    folder_match_sync = re.search(FOLDER_PATTERN, tail)
    efb_folders = _parse_efb_folders(folder_match_sync.group()) if folder_match_sync else {}

    # Build new XML blocks (preserving ExcludeFromBuild)
    compile_block = build_compile_block(state.ordered, efb_compile=efb_compile)
    folder_block = ""
    if not cfg.skip_folder_sync:
        folder_block = build_folder_block(state.folder_set, efb_folders=efb_folders)

    new_xml = replace_xml_blocks(xml, compile_block, folder_block, cfg.skip_folder_sync)

    if new_xml == xml:
        log.info("plcproj unchanged (already matches disk).")
        report.plcproj_unchanged = True
        report.plcproj_written = False
    elif cfg.dry_run:
        log.info("DRY RUN - would write: %s", proj_file)
        report.plcproj_written = False
    else:
        try:
            if cfg.backup:
                create_backup(proj_file)
            proj_file.write_text(new_xml, encoding="utf-8", newline="")
            log.info("Updated plcproj: %s", proj_file)
            report.plcproj_written = True
        except PermissionError as exc:
            report.success = False
            report.warnings.append(f"Cannot write plcproj (permission denied): {exc}")
            return report

    log.info("Compile items: %d", report.compile_count)
    if not cfg.skip_folder_sync:
        log.info("Folder items: %d", report.folder_count)

    # GUID repair
    if cfg.ensure_object_guids:
        repairs = repair_object_guids(state.base_dir, cfg.compile_extensions, cfg.dry_run)
        report.guids_repaired = repairs

    return report


# ================================================================
#  Project info
# ================================================================

def read_project_info(plcproj_path: str) -> Dict[str, Any]:
    """Read TwinCAT PLC project metadata from .plcproj XML.

    Returns a dict with keys: title, version, company, name, released,
    plcproj_path.  Raises FileNotFoundError or ET.ParseError on failure.
    Does NOT require a running TcXaeShell instance.
    """
    p = Path(plcproj_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"plcproj not found: {plcproj_path}")

    tree = ET.parse(str(p))
    ns = {"ms": "http://schemas.microsoft.com/developer/msbuild/2003"}

    def _txt(xpath: str) -> str:
        el = tree.getroot().find(xpath, ns)
        return el.text.strip() if el is not None and el.text else ""

    return {
        "title":        _txt(".//ms:Title") or _txt(".//ms:Name"),
        "version":      _txt(".//ms:ProjectVersion") or "0.0.0.0",
        "company":      _txt(".//ms:Company"),
        "name":         _txt(".//ms:Name"),
        "released":     _txt(".//ms:Released"),
        "plcproj_path": str(p),
    }


# ================================================================
#  CLI
# ================================================================

def parse_arguments(argv: List[str] | None = None) -> PlcProjConfig:
    """Parse command-line arguments into a PlcProjConfig."""
    parser = argparse.ArgumentParser(
        description="TwinCAT 3 PlcProject verify / sync tool.",
    )
    parser.add_argument("--input", required=True,
                        help="Path to .plcproj file or project root directory.")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only verify; do not write anything.")
    parser.add_argument("--force", action="store_true",
                        help="Skip verify and rebuild plcproj from disk.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only, no files written.")
    parser.add_argument("--no-backup", action="store_true",
                        help="Skip backup before writing.")
    parser.add_argument("--skip-folder-sync", action="store_true",
                        help="Do not sync Folder ItemGroup.")
    parser.add_argument("--ensure-object-guids", action="store_true",
                        help="Repair missing/duplicate object GUIDs in Tc* files.")
    parser.add_argument("--compile-extensions", nargs="+",
                        default=None,
                        help="File extensions to include (default: .TcPOU .TcDUT .TcIO .TcGVL .TcTTO).")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Log verbosity.")

    args = parser.parse_args(argv)

    extensions = DEFAULT_COMPILE_EXTENSIONS
    if args.compile_extensions:
        extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.compile_extensions}

    return PlcProjConfig(
        input_path=args.input,
        verify_only=args.verify_only,
        force=args.force,
        dry_run=args.dry_run,
        backup=not args.no_backup,
        skip_folder_sync=args.skip_folder_sync,
        ensure_object_guids=args.ensure_object_guids,
        compile_extensions=extensions,
        log_level=args.log_level,
    )


def main(argv: List[str] | None = None) -> int:
    """CLI entry point (also called by MCP tool wrapper)."""
    cfg = parse_arguments(argv)

    logging.basicConfig(
        level=getattr(logging, cfg.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )

    try:
        if cfg.verify_only:
            input_p = Path(cfg.input_path)
            if input_p.is_file() and input_p.suffix.lower() == ".plcproj":
                proj_file = resolve_plcproj_path(plcproj_path=cfg.input_path)
            else:
                proj_file = resolve_plcproj_path(project_root=cfg.input_path)

            vr = verify_plcproj(proj_file, cfg.compile_extensions, cfg.skip_folder_sync)
            state = scan_disk_state(proj_file, cfg.compile_extensions, cfg.skip_folder_sync)

            if vr.ok:
                folder_info = f", {len(state.folder_set)} Folder" if not cfg.skip_folder_sync else ""
                efb_parts: List[str] = []
                efb_f_true = sum(1 for v in vr.efb_folders.values() if v == "true")
                efb_c_true = sum(1 for v in vr.efb_compile.values() if v == "true")
                if efb_f_true:
                    efb_parts.append(f"{efb_f_true} folder excluded")
                if efb_c_true:
                    efb_parts.append(f"{efb_c_true} file excluded")
                efb_info = f", {', '.join(efb_parts)}" if efb_parts else ""
                print(f"OK: plcproj matches disk ({len(state.ordered)} Compile{folder_info}{efb_info}).")
                return 0

            if vr.error_message:
                print(f"ERROR: {vr.error_message}", file=sys.stderr)

            print("VERIFY FAILED: plcproj out of sync with disk.")
            if vr.missing_compile:
                print("  Compile on disk, missing in plcproj:")
                for p in vr.missing_compile:
                    print(f"    {p}")
            if vr.extra_compile:
                print("  Compile in plcproj, not on disk:")
                for p in vr.extra_compile:
                    print(f"    {p}")
            if vr.folder_missing:
                print("  Folder on disk, missing in plcproj:")
                for p in vr.folder_missing:
                    print(f"    {p}")
            if vr.folder_extra:
                print("  Folder in plcproj, no directory on disk:")
                for p in vr.folder_extra:
                    print(f"    {p}")

            return vr.exit_code

        report = sync_plcproj(cfg)

        if not report.success:
            for w in report.warnings:
                print(f"WARNING: {w}")
            if report.verify_result:
                vr = report.verify_result
                if vr.missing_compile:
                    print("  Compile on disk, missing in plcproj:")
                    for p in vr.missing_compile:
                        print(f"    {p}")
                if vr.extra_compile:
                    print("  Compile in plcproj, not on disk:")
                    for p in vr.extra_compile:
                        print(f"    {p}")
                if vr.folder_missing:
                    print("  Folder on disk, missing in plcproj:")
                    for p in vr.folder_missing:
                        print(f"    {p}")
                if vr.folder_extra:
                    print("  Folder in plcproj, no directory on disk:")
                    for p in vr.folder_extra:
                        print(f"    {p}")
            return 1

        return 0

    except Exception as exc:
        log.error("Fatal error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
