"""Lossless scanner and reader for TwinCAT XML documents."""
from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .safe_io import read_file_lossless
from .types import CdataKind, CdataSpan, TcXmlDocument, XmlEncodingInfo

# XML Tag and CDATA scanning regexes
_RE_XML_TOKEN = re.compile(
    r"(?P<cdata><!\[CDATA\[(?P<cdata_body>.*?)\]\]>)"
    r"|(?P<comment><!--.*?-->)"
    r"|(?P<close_tag></\s*(?P<close_name>[A-Za-z0-9_:]+)\s*>)"
    r"|(?P<open_tag><\s*(?P<open_name>[A-Za-z0-9_:]+)(?P<attrs>[^>]*)>)",
    re.DOTALL | re.IGNORECASE,
)

_RE_ATTR_NAME = re.compile(r'Name=(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)
_RE_ATTR_ID = re.compile(r'Id=(?:"(\{?[0-9a-fA-F\-]+\}?)"|\'(\{?[0-9a-fA-F\-]+\}?)\')', re.IGNORECASE)
_RE_ATTR_SPECIAL = re.compile(r'SpecialFunc=(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)
_RE_ATTR_PRODUCT_VERSION = re.compile(r'ProductVersion=(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)
_RE_ATTR_VERSION = re.compile(r'Version=(?:"([^"]*)"|\'([^\']*)\')', re.IGNORECASE)


def _strip_ns(tag: str) -> str:
    """Strip XML namespace prefix from tag name."""
    if ":" in tag:
        return tag.split(":", 1)[1]
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_attr(pattern: re.Pattern, attrs_str: str) -> Optional[str]:
    m = pattern.search(attrs_str)
    if m:
        return m.group(1) or m.group(2)
    return None


def _classify_cdata(
    tag_stack: List[Tuple[str, str, Optional[str]]],
) -> Tuple[CdataKind, str, str, Optional[str]]:
    """Determine the CdataKind, parent_tag, parent_name, and parent_id from current tag stack.

    Stack elements: (tag_name, name_attr, id_attr)
    """
    if not tag_stack:
        return CdataKind.UNKNOWN, "", "", None

    # Filter out wrapper tags like Implementation, ST, Declaration to find semantic parent
    semantic_parent = None
    for item in reversed(tag_stack):
        tag = item[0]
        if tag in ("POU", "DUT", "GVL", "Itf", "Method", "Action", "Property", "Get", "Set"):
            semantic_parent = item
            break

    tags_in_stack = [t[0] for t in tag_stack]
    is_decl = "Declaration" in tags_in_stack
    is_impl = "Implementation" in tags_in_stack or "ST" in tags_in_stack

    if semantic_parent is None:
        return CdataKind.UNKNOWN, tag_stack[-1][0], "", None

    p_tag, p_name, p_id = semantic_parent

    if p_tag == "POU":
        if is_decl:
            return CdataKind.POU_DECLARATION, p_tag, p_name, p_id
        if is_impl:
            return CdataKind.POU_IMPLEMENTATION, p_tag, p_name, p_id
    elif p_tag == "DUT":
        if is_decl:
            return CdataKind.DUT_DECLARATION, p_tag, p_name, p_id
    elif p_tag == "GVL":
        if is_decl:
            return CdataKind.GVL_DECLARATION, p_tag, p_name, p_id
    elif p_tag == "Itf":
        if is_decl:
            return CdataKind.ITF_DECLARATION, p_tag, p_name, p_id
    elif p_tag == "Method":
        if is_decl:
            return CdataKind.METHOD_DECLARATION, p_tag, p_name, p_id
        if is_impl:
            return CdataKind.METHOD_IMPLEMENTATION, p_tag, p_name, p_id
    elif p_tag == "Action":
        if is_impl:
            return CdataKind.ACTION_IMPLEMENTATION, p_tag, p_name, p_id
    elif p_tag == "Property":
        if is_decl:
            return CdataKind.PROPERTY_DECLARATION, p_tag, p_name, p_id
    elif p_tag == "Get":
        # Check if parent is Property
        prop_name = ""
        for item in reversed(tag_stack):
            if item[0] == "Property":
                prop_name = item[1]
                break
        eff_name = prop_name or p_name
        if is_decl:
            return CdataKind.PROPERTY_GET_DECLARATION, "Property", eff_name, p_id
        if is_impl:
            return CdataKind.PROPERTY_GET_IMPLEMENTATION, "Property", eff_name, p_id
    elif p_tag == "Set":
        prop_name = ""
        for item in reversed(tag_stack):
            if item[0] == "Property":
                prop_name = item[1]
                break
        eff_name = prop_name or p_name
        if is_decl:
            return CdataKind.PROPERTY_SET_DECLARATION, "Property", eff_name, p_id
        if is_impl:
            return CdataKind.PROPERTY_SET_IMPLEMENTATION, "Property", eff_name, p_id

    return CdataKind.UNKNOWN, p_tag, p_name, p_id


def scan_cdata_spans(raw_text: str) -> List[CdataSpan]:
    """Scan raw XML text and extract all CDATA spans with exact positions and semantic context."""
    spans: List[CdataSpan] = []
    tag_stack: List[Tuple[str, str, Optional[str]]] = []

    for m in _RE_XML_TOKEN.finditer(raw_text):
        if m.group("cdata") is not None:
            cdata_match = m.group("cdata")
            raw_start = m.start("cdata")
            raw_end = m.end("cdata")
            # <![CDATA[ has length 9, ]]> has length 3
            body_start = raw_start + 9
            body_end = raw_end - 3
            body_content = m.group("cdata_body")

            kind, parent_tag, parent_name, parent_id = _classify_cdata(tag_stack)

            # Build tag path tuple
            tag_path_parts = []
            for t_name, n_attr, _ in tag_stack:
                if n_attr:
                    tag_path_parts.append(f"{t_name}[{n_attr}]")
                else:
                    tag_path_parts.append(t_name)

            span = CdataSpan(
                kind=kind,
                parent_tag=parent_tag,
                parent_name=parent_name,
                parent_id=parent_id,
                tag_path=tuple(tag_path_parts),
                cdata_raw_start=raw_start,
                cdata_raw_end=raw_end,
                content_start=body_start,
                content_end=body_end,
                content=body_content,
            )
            spans.append(span)

        elif m.group("open_tag") is not None:
            tag_name = _strip_ns(m.group("open_name"))
            attrs_str = m.group("attrs") or ""
            is_self_closing = attrs_str.rstrip().endswith("/")

            name_attr = _extract_attr(_RE_ATTR_NAME, attrs_str) or ""
            id_attr = _extract_attr(_RE_ATTR_ID, attrs_str)

            if not is_self_closing:
                tag_stack.append((tag_name, name_attr, id_attr))

        elif m.group("close_tag") is not None:
            close_tag_name = _strip_ns(m.group("close_name"))
            # Pop stack up to matching open tag
            for i in range(len(tag_stack) - 1, -1, -1):
                if tag_stack[i][0].casefold() == close_tag_name.casefold():
                    tag_stack = tag_stack[:i]
                    break

    return spans


def read_tc_xml(
    text: str,
    file_path: Optional[Path] = None,
    encoding_info: Optional[XmlEncodingInfo] = None,
) -> TcXmlDocument:
    """Parse raw XML text into a lossless TcXmlDocument."""
    if encoding_info is None:
        encoding_info = XmlEncodingInfo(
            line_ending="\r\n" if "\r\n" in text else "\n",
        )

    spans = scan_cdata_spans(text)

    # Extract top-level object metadata
    root_type = ""
    root_name = ""
    root_id = None
    product_version = None
    version = None

    for m in re.finditer(r'<\s*([A-Za-z0-9_:]+)([^>]*)>', text):
        tag = _strip_ns(m.group(1))
        attrs = m.group(2)
        if tag == "TcPlcObject":
            product_version = _extract_attr(_RE_ATTR_PRODUCT_VERSION, attrs)
            version = _extract_attr(_RE_ATTR_VERSION, attrs)
        elif tag in ("POU", "DUT", "GVL", "Itf") and not root_type:
            root_type = tag
            root_name = _extract_attr(_RE_ATTR_NAME, attrs) or ""
            root_id = _extract_attr(_RE_ATTR_ID, attrs)

    if not root_name and file_path:
        root_name = file_path.stem

    return TcXmlDocument(
        raw_text=text,
        encoding_info=encoding_info,
        file_path=file_path,
        cdata_spans=spans,
        root_object_type=root_type,
        root_object_name=root_name,
        root_object_id=root_id,
        product_version=product_version,
        version=version,
    )


def read_tc_xml_file(path: Union[str, Path]) -> TcXmlDocument:
    """Read a TwinCAT XML file losslessly from disk."""
    p = Path(path).resolve()
    raw_text, enc_info = read_file_lossless(p)
    return read_tc_xml(raw_text, file_path=p, encoding_info=enc_info)
