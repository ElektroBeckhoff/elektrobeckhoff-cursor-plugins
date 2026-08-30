"""XML Writer with CDATA preservation.

Custom XML serializer because ElementTree.write() does not preserve CDATA blocks.
Handles TwinCAT-specific XML structure with controlled indentation and attribute ordering.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from formatter.constants import XML_ATTRIBUTE_ORDER, XML_INDENT_SIZE_DEFAULT


# Special marker for CDATA content in element text (XML-safe placeholder)
CDATA_MARKER = "___CDATA_PLACEHOLDER___"


def serialize_twincat_xml(
    root: ET.Element,
    *,
    indent_size: int = XML_INDENT_SIZE_DEFAULT,
    line_ending: str = "\n",
    xml_declaration: str = '<?xml version="1.0" encoding="utf-8"?>',
) -> str:
    """Serialize XML tree with CDATA preservation.

    CDATA blocks are written as <![CDATA[...]]> (not XML-escaped).
    Attributes are ordered according to XML_ATTRIBUTE_ORDER.
    """
    lines: list[str] = []
    if xml_declaration:
        lines.append(xml_declaration)

    _serialize_element(root, lines, level=0, indent_size=indent_size)

    result = line_ending.join(lines)
    return result


def _serialize_element(
    elem: ET.Element,
    lines: list[str],
    level: int,
    indent_size: int,
) -> None:
    """Recursively serialize an element with proper indentation."""
    indent = " " * (level * indent_size)
    tag = _local_tag(elem.tag)
    attrs = _format_attributes(elem, tag)

    children = list(elem)
    has_cdata = elem.text and CDATA_MARKER in elem.text
    has_text = elem.text and elem.text.strip() and not has_cdata

    if not children and not has_text and not has_cdata:
        if elem.text is None or not elem.text.strip():
            lines.append(f"{indent}<{tag}{attrs} />")
        else:
            lines.append(f"{indent}<{tag}{attrs}>{_escape(elem.text)}</{tag}>")
        return

    if has_cdata:
        cdata_content = elem.text.replace(CDATA_MARKER, "")
        if not cdata_content or cdata_content == "":
            lines.append(f"{indent}<{tag}{attrs}><![CDATA[]]></{tag}>")
        elif "\n" not in cdata_content.strip():
            lines.append(f"{indent}<{tag}{attrs}><![CDATA[{cdata_content}]]></{tag}>")
        else:
            lines.append(f"{indent}<{tag}{attrs}><![CDATA[{cdata_content}]]></{tag}>")
        return

    if not children and has_text:
        lines.append(f"{indent}<{tag}{attrs}>{_escape(elem.text.strip())}</{tag}>")
        return

    lines.append(f"{indent}<{tag}{attrs}>")

    if has_text:
        lines.append(f"{' ' * ((level + 1) * indent_size)}{_escape(elem.text.strip())}")

    for child in children:
        _serialize_element(child, lines, level + 1, indent_size)

    lines.append(f"{indent}</{tag}>")


_NS_MAP = {
    "http://www.w3.org/XML/1998/namespace": "xml",
    "http://www.w3.org/2001/XMLSchema-instance": "xsi",
}


def _format_attributes(elem: ET.Element, tag: str) -> str:
    """Format attributes in the canonical order for this tag."""
    if not elem.attrib:
        return ""

    order = XML_ATTRIBUTE_ORDER.get(tag)
    if order:
        sorted_attrs: list[tuple[str, str]] = []
        for key in order:
            if key in elem.attrib:
                sorted_attrs.append((key, elem.attrib[key]))
        for key, val in elem.attrib.items():
            if key not in order:
                sorted_attrs.append((key, val))
    else:
        sorted_attrs = list(elem.attrib.items())

    parts = [f' {_attr_name(k)}="{_escape_attr(v)}"' for k, v in sorted_attrs]
    return "".join(parts)


def _attr_name(key: str) -> str:
    """Convert Clark notation {ns}local back to prefix:local."""
    if key.startswith("{"):
        ns_end = key.index("}")
        ns = key[1:ns_end]
        local = key[ns_end + 1:]
        prefix = _NS_MAP.get(ns)
        if prefix:
            return f"{prefix}:{local}"
        return local
    return key


def _local_tag(tag: str) -> str:
    """Strip namespace from tag if present."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _escape(text: str) -> str:
    """XML-escape text content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _escape_attr(text: str) -> str:
    """XML-escape attribute value."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
