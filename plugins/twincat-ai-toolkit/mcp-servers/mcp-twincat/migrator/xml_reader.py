"""XML loading and helper utilities for TwinCAT migration."""
from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .types import ActionInfo, TcFile


def load_file(path: Path, encoding: str = "utf-8") -> Optional[TcFile]:
    tc = TcFile(path=path, encoding=encoding)
    tc.file_type = path.suffix.lower()

    for enc in [encoding, "utf-8-sig", "utf-8", "latin-1"]:
        try:
            raw = path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        tc.errors.append(f"Cannot decode file with any known encoding: {path}")
        return tc

    try:
        tc.xml_tree = ET.ElementTree(ET.fromstring(raw))
        tc.xml_root = tc.xml_tree.getroot()
    except ET.ParseError as exc:
        tc.errors.append(f"XML parse error: {exc}")
        return tc

    pou = tc.xml_root.find("POU")
    if pou is None:
        pou = tc.xml_root.find("GVL")
    if pou is None:
        pou = tc.xml_root.find("DUT")
    if pou is None:
        for child in tc.xml_root:
            pou = child
            break

    if pou is not None:
        tc.pou_name = pou.get("Name", "")
        tc.pou_id = pou.get("Id", "")
        tc.special_func = pou.get("SpecialFunc", "")

        decl = pou.find("Declaration")
        if decl is not None and decl.text:
            tc.declaration = decl.text.strip()
            tc.pou_type = _detect_pou_type(tc.declaration)

        impl = pou.find("Implementation")
        if impl is not None:
            tc.impl_type = _detect_impl_type(impl)

        for action_el in pou.findall("Action"):
            ai = ActionInfo(name=action_el.get("Name", ""), xml_element=action_el)
            action_impl = action_el.find("Implementation")
            if action_impl is not None:
                ai.impl_type = _detect_impl_type(action_impl)
            tc.actions.append(ai)

    return tc


def _detect_pou_type(declaration: str) -> str:
    if not declaration:
        return "UNKNOWN"
    keywords = ["PROGRAM", "FUNCTION_BLOCK", "FUNCTION", "METHOD", "ACTION",
                "PROPERTY", "INTERFACE", "STRUCT", "ENUM", "TYPE"]
    for line in declaration.strip().split("\n"):
        upper = line.strip().upper()
        if not upper or upper.startswith("//") or upper.startswith("{") or upper.startswith("(*"):
            continue
        for kw in keywords:
            if upper.startswith(kw):
                return kw
        break
    return "UNKNOWN"


def _detect_impl_type(impl_element) -> str:
    for tag in ["ST", "NWL", "CFC", "SFC", "IL", "LD"]:
        if impl_element.find(tag) is not None:
            return tag
    return "UNKNOWN"


def _get_v_str(element, name: str) -> str:
    for child in element:
        if child.tag == "v" and child.get("n") == name:
            raw = (child.text or "").strip()
            return _strip_quotes(raw)
    return ""


def _find_v(element, name: str):
    for child in element:
        if child.tag == "v" and child.get("n") == name:
            return child
    return None


def _find_child_by_name(element, name: str):
    for child in element:
        if child.get("n") == name:
            return child
    return None


def _strip_quotes(s: str) -> str:
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def _regenerate_guids(xml_text: str) -> str:
    from twincat_core.xml.guid_manager import regenerate_all_guids
    return regenerate_all_guids(xml_text)
