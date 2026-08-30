"""Project Graph and structural data models for TwinCAT .plcproj projects."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set


@dataclass(slots=True)
class CompileItem:
    """An included source file in a .plcproj project."""
    rel_path: str
    abs_path: Path
    item_type: str  # "TcPOU", "TcDUT", "TcGVL", "TcIO", "TcTTO", etc.
    sub_type: str = "Code"
    exclude_from_build: bool = False


@dataclass(slots=True)
class FolderItem:
    """A virtual/physical folder listed in a .plcproj project."""
    rel_path: str
    exclude_from_build: bool = False


@dataclass(slots=True)
class LibraryReference:
    """An external library reference or placeholder reference."""
    name: str
    namespace: Optional[str] = None
    default_resolution: str = ""
    is_placeholder: bool = True


@dataclass(slots=True)
class PlcProject:
    """Representation of an entire TwinCAT PLC project rooted at a .plcproj file."""
    project_path: Path
    project_name: str
    target_archive: Optional[str] = None
    compile_items: dict[str, CompileItem] = field(default_factory=dict)  # lowercase rel_path -> CompileItem
    folders: dict[str, FolderItem] = field(default_factory=dict)         # lowercase rel_path -> FolderItem
    library_references: list[LibraryReference] = field(default_factory=list)

    @property
    def root_dir(self) -> Path:
        return self.project_path.parent

    def get_compile_item(self, rel_or_abs_path: Path | str) -> Optional[CompileItem]:
        if isinstance(rel_or_abs_path, Path):
            try:
                rel = rel_or_abs_path.relative_to(self.root_dir).as_posix().lower()
            except ValueError:
                rel = rel_or_abs_path.name.lower()
        else:
            rel = rel_or_abs_path.replace("\\", "/").lower()
        return self.compile_items.get(rel)

    def is_excluded(self, rel_path: str) -> bool:
        norm = rel_path.replace("\\", "/").lower()
        item = self.compile_items.get(norm)
        if item and item.exclude_from_build:
            return True
        # Check folder excludes
        parts = norm.split("/")
        for i in range(1, len(parts)):
            parent_folder = "/".join(parts[:i])
            folder_item = self.folders.get(parent_folder)
            if folder_item and folder_item.exclude_from_build:
                return True
        return False
