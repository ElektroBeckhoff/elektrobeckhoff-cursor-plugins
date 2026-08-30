"""Safe file writer: atomic writes, backup, rollback, hash verification."""
from __future__ import annotations

from pathlib import Path
from formatter.types import WriteSummary
from twincat_core.xml.safe_io import write_file_safe as core_write_file_safe


class SafeFileWriter:
    """Atomic file writes with backup and rollback capability delegating to twincat_core.xml.safe_io."""

    def write_safe(
        self,
        path: str,
        content: bytes,
        *,
        backup: bool = True,
        delete_backup_on_success: bool = True,
    ) -> WriteSummary:
        res = core_write_file_safe(
            path,
            content,
            backup=backup,
            delete_backup_on_success=delete_backup_on_success,
        )
        return WriteSummary(
            path=res.path,
            written=res.written,
            original_hash=res.original_hash,
            new_hash=res.new_hash,
            backup_path=res.backup_path,
            error=res.error,
        )
