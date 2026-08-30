"""Safe file writer: atomic writes, backup, rollback, hash verification.

Guarantees: the original file is NEVER corrupted.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from formatter.types import WriteSummary
from formatter.utils import compute_sha256


class SafeFileWriter:
    """Atomic file writes with backup and rollback capability."""

    def write_safe(
        self,
        path: str,
        content: bytes,
        *,
        backup: bool = True,
        delete_backup_on_success: bool = True,
    ) -> WriteSummary:
        """Write content to file atomically.

        Steps:
        1. Hash original file
        2. Write to temp file (.tmp suffix, same directory)
        3. If backup=True: copy original to .bak
        4. Atomic rename temp -> target (os.replace)
        5. Verify final hash
        6. On failure: rollback (.bak -> original)
        """
        target = Path(path)
        summary = WriteSummary(path=path)

        if not target.parent.exists():
            summary.error = f"Parent directory does not exist: {target.parent}"
            return summary

        original_hash = ""
        if target.exists():
            if not os.access(target, os.W_OK):
                summary.error = f"File is read-only: {path}"
                return summary
            original_bytes = target.read_bytes()
            original_hash = compute_sha256(original_bytes)
            summary.original_hash = original_hash

        new_hash = compute_sha256(content)
        summary.new_hash = new_hash

        if original_hash == new_hash:
            summary.written = False
            return summary

        backup_path = ""
        try:
            if backup and target.exists():
                backup_path = str(target) + ".bak"
                shutil.copy2(str(target), backup_path)
                summary.backup_path = backup_path

            fd, tmp_path = tempfile.mkstemp(
                suffix=".tmp",
                dir=str(target.parent),
            )
            try:
                os.write(fd, content)
                os.close(fd)

                os.replace(tmp_path, str(target))
            except Exception:
                os.close(fd) if not os.get_inheritable(fd) else None
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            verify_hash = compute_sha256(target.read_bytes())
            if verify_hash != new_hash:
                if backup_path and os.path.exists(backup_path):
                    os.replace(backup_path, str(target))
                summary.error = "Hash verification failed after write"
                return summary

            if delete_backup_on_success and backup_path and os.path.exists(backup_path):
                os.unlink(backup_path)
                summary.backup_path = ""

            summary.written = True
            return summary

        except OSError as e:
            if backup_path and os.path.exists(backup_path):
                try:
                    os.replace(backup_path, str(target))
                except OSError:
                    pass
            summary.error = f"Write failed: {e}"
            return summary

    def rollback(self, path: str) -> bool:
        """Restore file from .bak backup if it exists."""
        backup_path = path + ".bak"
        if os.path.exists(backup_path):
            try:
                os.replace(backup_path, path)
                return True
            except OSError:
                return False
        return False
