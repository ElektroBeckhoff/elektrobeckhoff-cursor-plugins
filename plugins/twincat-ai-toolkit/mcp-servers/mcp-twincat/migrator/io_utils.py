"""File collection, backup, and output path helpers."""
from __future__ import annotations

import datetime
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .constants import SUPPORTED_EXTENSIONS
from .types import MigrationConfig, TcFile


def collect_input_files(cfg: MigrationConfig) -> List[Path]:
    p = Path(cfg.input_path)
    if p.is_file():
        if p.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [p]
        logging.warning("Unsupported file type: %s", p.suffix)
        return []
    if p.is_dir():
        results = []
        pattern = "**/*" if cfg.recursive else "*"
        for ext in SUPPORTED_EXTENSIONS:
            results.extend(p.glob(f"{pattern}{ext}"))
            results.extend(p.glob(f"{pattern}{ext.upper()}"))
        seen = set()
        unique = []
        for f in sorted(results):
            key = str(f).lower()
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique
    logging.error("Input path does not exist: %s", p)
    return []


def create_backup(path: Path, backup_dir: Optional[Path] = None,
                  input_root: Optional[Path] = None) -> Optional[Path]:
    """Create a backup copy of *path* before it is overwritten.

    When *backup_dir* is given (directory-level backup), the file is
    copied into *backup_dir* keeping its relative position from
    *input_root*.  Otherwise a timestamped copy is placed next to the
    original.
    """
    try:
        if backup_dir is not None:
            if input_root is not None:
                try:
                    rel = path.relative_to(input_root)
                except ValueError:
                    rel = Path(path.name)
            else:
                rel = Path(path.name)
            backup_path = backup_dir / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
            backup_name = f"{path.stem}_backup_{ts}{path.suffix}"
            backup_path = path.parent / backup_name
        shutil.copy2(str(path), str(backup_path))
        return backup_path
    except Exception as exc:
        logging.error("Backup failed: %s", exc)
        return None


def write_output_file(content: str, path: Path, encoding: str = "utf-8") -> bool:
    from twincat_core.xml.safe_io import write_file_safe
    summary = write_file_safe(path, content.encode(encoding), backup=False)
    if summary.error:
        logging.error("Write failed for %s: %s", path, summary.error)
        return False
    return True


def can_replace(tc: TcFile, cfg: MigrationConfig, backup_path: Optional[Path]) -> Tuple[bool, str]:
    checks = [
        (bool(tc.path and tc.path.is_file()), "Original file readable"),
        (tc.file_type in SUPPORTED_EXTENSIONS, "File type supported"),
        (bool(tc.pou_name), "POU recognized"),
        (tc.impl_type in ("NWL", "CFC"), "FBD/FUP or CFC logic detected"),
        (bool(tc.declaration), "Declarations preserved"),
        (bool(tc.generated_st and tc.generated_st.strip()), "ST implementation generated"),
        (not tc.errors, "No critical errors"),
        (cfg.backup is False or backup_path is not None, "Backup created or disabled"),
        (cfg.force, "--force is set"),
        (not cfg.dry_run, "Not in dry-run mode"),
    ]
    for condition, desc in checks:
        if not condition:
            return False, f"Pre-condition failed: {desc}"
    return True, "All pre-conditions met"


def _resolve_output_path(source: Path, cfg: MigrationConfig) -> Path:
    if cfg.output_path:
        out = Path(cfg.output_path)
        if out.is_dir():
            return out / f"{source.stem}_ST{source.suffix}"
        return out
    return source.parent / f"{source.stem}_st_generated{source.suffix}"
