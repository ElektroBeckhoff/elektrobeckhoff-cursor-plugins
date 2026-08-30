"""XML Formatter for TwinCAT3 files.

Handles:
- Element sorting (Declaration, Implementation, Folder, Method, Action, Property)
- Attribute ordering per element type
- Indentation of XML structure
- CDATA block parsing and preservation
- FolderPath grouping
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Sequence

from formatter.constants import (
    XML_ATTRIBUTE_ORDER,
    XML_INDENT_SIZE_DEFAULT,
    XML_POU_CHILD_ORDER,
)
from formatter.xml_writer import CDATA_MARKER, serialize_twincat_xml


# ---------------------------------------------------------------------------
# CDATA-aware XML parsing
# ---------------------------------------------------------------------------

_RE_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)


def parse_twincat_xml(raw_text: str) -> tuple[ET.Element, dict[str, str]]:
    """Parse TwinCAT XML with CDATA preservation.

    Returns the root element and a dict mapping placeholder IDs to CDATA content.
    CDATA sections are replaced with markers before parsing, then restored during serialization.
    """
    cdata_map: dict[str, str] = {}
    counter = 0

    def _replace_cdata(m: re.Match[str]) -> str:
        nonlocal counter
        key = f"__CDATA_{counter}__"
        cdata_map[key] = m.group(1)
        counter += 1
        return f"{CDATA_MARKER}{key}{CDATA_MARKER}"

    prepared = _RE_CDATA.sub(_replace_cdata, raw_text)

    xml_decl = ""
    if prepared.startswith("<?xml"):
        end = prepared.find("?>")
        if end >= 0:
            xml_decl = prepared[: end + 2]
            prepared = prepared[end + 2:].lstrip()

    root = ET.fromstring(prepared)
    return root, cdata_map


def restore_cdata(text: str, cdata_map: dict[str, str]) -> str:
    """Replace CDATA placeholders with original CDATA content.

    The xml_writer outputs: <![CDATA[__CDATA_N__]]>
    This replaces them with: <![CDATA[actual_content]]>
    """
    for key, content in cdata_map.items():
        text = text.replace(f"<![CDATA[{key}]]>", f"<![CDATA[{content}]]>")
    return text


# ---------------------------------------------------------------------------
# Element Sorting
# ---------------------------------------------------------------------------


def sort_pou_children(root: ET.Element) -> None:
    """Sort children of POU/DUT/GVL/Itf elements according to canonical order.

    Order: Declaration, Implementation, Folder, then Methods/Actions/Properties
    (grouped by FolderPath, alphabetically within groups).
    """
    for container in _find_containers(root):
        _sort_container_children(container)


def _find_containers(root: ET.Element) -> list[ET.Element]:
    """Find all POU, DUT, GVL, Itf elements that need child sorting."""
    containers: list[ET.Element] = []
    tag = _local_tag(root.tag)
    if tag in ("POU", "DUT", "GVL", "Itf"):
        containers.append(root)
    for child in root:
        containers.extend(_find_containers(child))
    return containers


def _sort_container_children(container: ET.Element) -> None:
    """Sort children of a single POU/DUT/GVL/Itf element.

    Observed TwinCAT XAE pattern (96% of golden files):
      1. Declaration  (always first)
      2. Implementation  (always second)
      3. Folder elements  (sorted alphabetically by Name, case-insensitive)
      4. ALL remaining elements (Method/Property/Action) sorted FLAT
         alphabetically by Name (case-insensitive), regardless of type
         or FolderPath attribute.
    """
    children = list(container)
    if not children:
        return

    declaration: list[ET.Element] = []
    implementation: list[ET.Element] = []
    folders: list[ET.Element] = []
    members: list[ET.Element] = []

    for child in children:
        tag = _local_tag(child.tag)
        if tag == "Declaration":
            declaration.append(child)
        elif tag == "Implementation":
            implementation.append(child)
        elif tag == "Folder":
            folders.append(child)
        elif tag in ("Method", "Action", "Property"):
            members.append(child)
        else:
            declaration.append(child)

    folders.sort(key=lambda e: e.get("Name", "").casefold())
    members.sort(key=lambda e: e.get("Name", "").casefold())

    sorted_children: list[ET.Element] = []
    sorted_children.extend(declaration)
    sorted_children.extend(implementation)
    sorted_children.extend(folders)
    sorted_children.extend(members)

    container[:] = sorted_children


# ---------------------------------------------------------------------------
# Full XML Format Pipeline
# ---------------------------------------------------------------------------


def format_xml_structure(
    raw_text: str,
    *,
    indent_size: int = XML_INDENT_SIZE_DEFAULT,
    sort_elements: bool = False,
    line_ending: str = "\n",
) -> tuple[str, dict[str, str]]:
    """Format XML structure: parse, sort, reserialize.

    Returns (formatted_xml_with_placeholders, cdata_map).
    Caller must call restore_cdata() after ST formatting the CDATA contents.
    """
    xml_decl = '<?xml version="1.0" encoding="utf-8"?>'
    if raw_text.startswith("<?xml"):
        end = raw_text.find("?>")
        if end >= 0:
            xml_decl = raw_text[:end + 2].strip()

    root, cdata_map = parse_twincat_xml(raw_text)

    if sort_elements:
        sort_pou_children(root)

    formatted = serialize_twincat_xml(
        root,
        indent_size=indent_size,
        line_ending=line_ending,
        xml_declaration=xml_decl,
    )

    return formatted, cdata_map


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _local_tag(tag: str) -> str:
    """Strip namespace from tag."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
