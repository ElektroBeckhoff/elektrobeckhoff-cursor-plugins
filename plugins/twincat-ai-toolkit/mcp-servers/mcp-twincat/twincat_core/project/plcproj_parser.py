"""Parser for TwinCAT .plcproj MSBuild project files."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .project_graph import CompileItem, FolderItem, LibraryReference, PlcProject


def parse_plcproj_file(plcproj_path: Path) -> PlcProject:
    """Parse a .plcproj file from disk and construct a PlcProject model."""
    path = plcproj_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PlcProj file not found: {path}")

    content = path.read_text(encoding="utf-8-sig")
    return parse_plcproj_content(content, project_path=path)


def parse_plcproj_content(content: str, project_path: Path) -> PlcProject:
    """Parse .plcproj XML content and construct a PlcProject model."""
    root_dir = project_path.parent
    root = ET.fromstring(content)

    # Strip XML namespace if present
    def _local(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    project_name = project_path.stem
    compile_items: dict[str, CompileItem] = {}
    folders: dict[str, FolderItem] = {}
    lib_refs: list[LibraryReference] = []

    for elem in root:
        elem_tag = _local(elem.tag)

        if elem_tag == "PropertyGroup":
            for child in elem:
                c_tag = _local(child.tag)
                if c_tag == "Name" and child.text:
                    project_name = child.text.strip()

        elif elem_tag == "ItemGroup":
            for child in elem:
                c_tag = _local(child.tag)
                include_val = child.get("Include", "")
                if not include_val:
                    continue

                norm_rel = include_val.replace("\\", "/")
                key = norm_rel.lower()

                # Check ExcludeFromBuild child
                efb = False
                sub_type = "Code"
                for sub in child:
                    s_tag = _local(sub.tag)
                    if s_tag == "ExcludeFromBuild" and sub.text:
                        efb = sub.text.strip().lower() == "true"
                    elif s_tag == "SubType" and sub.text:
                        sub_type = sub.text.strip()

                if c_tag == "Compile":
                    abs_p = (root_dir / norm_rel).resolve()
                    ext = abs_p.suffix.lstrip(".")
                    compile_items[key] = CompileItem(
                        rel_path=norm_rel,
                        abs_path=abs_p,
                        item_type=ext,
                        sub_type=sub_type,
                        exclude_from_build=efb,
                    )

                elif c_tag == "Folder":
                    folders[key] = FolderItem(
                        rel_path=norm_rel,
                        exclude_from_build=efb,
                    )

                elif c_tag in ("PlaceholderReference", "LibraryReference"):
                    ns = None
                    def_res = ""
                    for sub in child:
                        s_tag = _local(sub.tag)
                        if s_tag == "Namespace" and sub.text:
                            ns = sub.text.strip()
                        elif s_tag == "DefaultResolution" and sub.text:
                            def_res = sub.text.strip()

                    lib_refs.append(
                        LibraryReference(
                            name=include_val,
                            namespace=ns,
                            default_resolution=def_res,
                            is_placeholder=(c_tag == "PlaceholderReference"),
                        )
                    )

    return PlcProject(
        project_path=project_path.resolve(),
        project_name=project_name,
        compile_items=compile_items,
        folders=folders,
        library_references=lib_refs,
    )
