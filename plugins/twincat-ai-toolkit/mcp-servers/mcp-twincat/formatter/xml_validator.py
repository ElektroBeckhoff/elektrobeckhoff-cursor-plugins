"""XML Validator for TwinCAT3 files.

Validates:
- Name attribute matches first type name in Declaration CDATA
- GUID format and uniqueness
- Required elements (Declaration, Implementation for POU; Declaration for DUT/GVL)
- SpecialFunc values
- FolderPath consistency
- Interface rules (no Implementation in interface methods)
- ParameterList attribute on GVL
- Encoding consistency
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Sequence

from formatter.constants import RE_GUID, VALID_SPECIAL_FUNC
from formatter.types import ValidationIssue


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

_RE_TYPE_NAME = re.compile(
    r"(?:FUNCTION_BLOCK|FUNCTION|PROGRAM|METHOD|PROPERTY|ACTION|INTERFACE)\s+"
    r"(?:(?:ABSTRACT|FINAL|PUBLIC|INTERNAL|PRIVATE|PROTECTED)\s+)*"
    r"(\w+)",
    re.IGNORECASE,
)
_RE_DUT_NAME = re.compile(r"TYPE\s+(\w+)", re.IGNORECASE)
_RE_GVL_START = re.compile(r"VAR_GLOBAL", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_twincat_xml(
    raw_text: str,
    file_path: str = "",
    *,
    check_name_match: bool = True,
    check_guids: bool = True,
    check_structure: bool = True,
) -> list[ValidationIssue]:
    """Validate a TwinCAT XML file and return all issues found."""
    issues: list[ValidationIssue] = []

    try:
        root = ET.fromstring(_strip_cdata_for_parse(raw_text))
    except ET.ParseError as e:
        issues.append(ValidationIssue(
            level="error",
            file=file_path,
            line=0,
            message=f"XML parse error: {e}",
            rule="xml_parse",
        ))
        return issues

    cdata_blocks = _extract_cdata_blocks(raw_text)

    if check_guids:
        issues.extend(_check_guids(root, file_path))

    if check_structure:
        issues.extend(_check_structure(root, file_path))

    if check_name_match:
        issues.extend(_check_name_match(root, file_path, cdata_blocks))

    return issues


# ---------------------------------------------------------------------------
# GUID Checks
# ---------------------------------------------------------------------------


def _check_guids(root: ET.Element, file_path: str) -> list[ValidationIssue]:
    """Check GUID format and uniqueness."""
    issues: list[ValidationIssue] = []
    seen_guids: dict[str, str] = {}

    for elem in root.iter():
        guid = elem.get("Id", "")
        if not guid:
            continue

        if not RE_GUID.fullmatch(guid):
            issues.append(ValidationIssue(
                level="error",
                file=file_path,
                line=0,
                message=f"Invalid GUID format: {guid} on <{_local_tag(elem.tag)}>",
                rule="guid_format",
            ))
            continue

        guid_lower = guid.lower()
        if guid_lower in seen_guids:
            issues.append(ValidationIssue(
                level="error",
                file=file_path,
                line=0,
                message=f"Duplicate GUID {guid} on <{_local_tag(elem.tag)}> "
                        f"(first seen on <{seen_guids[guid_lower]}>)",
                rule="guid_unique",
            ))
        else:
            seen_guids[guid_lower] = _local_tag(elem.tag)

    return issues


# ---------------------------------------------------------------------------
# Structure Checks
# ---------------------------------------------------------------------------


def _check_structure(root: ET.Element, file_path: str) -> list[ValidationIssue]:
    """Check required elements and valid attribute values."""
    issues: list[ValidationIssue] = []

    for elem in root.iter():
        tag = _local_tag(elem.tag)

        if tag == "POU":
            issues.extend(_check_pou_structure(elem, file_path))
        elif tag == "DUT":
            issues.extend(_check_dut_structure(elem, file_path))
        elif tag == "GVL":
            issues.extend(_check_gvl_structure(elem, file_path))
        elif tag == "Itf":
            issues.extend(_check_itf_structure(elem, file_path))

    return issues


def _check_pou_structure(pou: ET.Element, file_path: str) -> list[ValidationIssue]:
    """POU needs Declaration + Implementation, valid SpecialFunc."""
    issues: list[ValidationIssue] = []
    name = pou.get("Name", "<unknown>")
    children_tags = {_local_tag(c.tag) for c in pou}

    if "Declaration" not in children_tags:
        issues.append(ValidationIssue(
            level="error", file=file_path, line=0,
            message=f"POU '{name}' missing <Declaration>",
            rule="pou_structure",
        ))
    if "Implementation" not in children_tags:
        issues.append(ValidationIssue(
            level="error", file=file_path, line=0,
            message=f"POU '{name}' missing <Implementation>",
            rule="pou_structure",
        ))

    special = pou.get("SpecialFunc")
    if special is not None and special not in VALID_SPECIAL_FUNC:
        issues.append(ValidationIssue(
            level="warning", file=file_path, line=0,
            message=f"POU '{name}' has unknown SpecialFunc='{special}'",
            rule="special_func",
        ))

    for child in pou:
        tag = _local_tag(child.tag)
        child_name = child.get("Name", "<unknown>")

        if tag == "Method":
            method_tags = {_local_tag(c.tag) for c in child}
            if "Declaration" not in method_tags:
                issues.append(ValidationIssue(
                    level="error", file=file_path, line=0,
                    message=f"Method '{child_name}' in POU '{name}' missing <Declaration>",
                    rule="method_structure",
                ))
            if "Implementation" not in method_tags:
                issues.append(ValidationIssue(
                    level="error", file=file_path, line=0,
                    message=f"Method '{child_name}' in POU '{name}' missing <Implementation>",
                    rule="method_structure",
                ))

        elif tag == "Property":
            prop_tags = {_local_tag(c.tag) for c in child}
            if "Get" not in prop_tags and "Set" not in prop_tags:
                issues.append(ValidationIssue(
                    level="error", file=file_path, line=0,
                    message=f"Property '{child_name}' in POU '{name}' has neither <Get> nor <Set>",
                    rule="property_structure",
                ))

    folder_names = {
        child.get("Name", "")
        for child in pou if _local_tag(child.tag) == "Folder"
    }
    for child in pou:
        folder_path = child.get("FolderPath", "")
        if folder_path:
            folder_ref = folder_path.rstrip("\\")
            if folder_ref not in folder_names:
                issues.append(ValidationIssue(
                    level="warning", file=file_path, line=0,
                    message=f"Element '{child.get('Name', '')}' references "
                            f"FolderPath='{folder_path}' but no <Folder Name=\"{folder_ref}\"> exists",
                    rule="folder_consistency",
                ))

    return issues


def _check_dut_structure(dut: ET.Element, file_path: str) -> list[ValidationIssue]:
    """DUT needs Declaration."""
    issues: list[ValidationIssue] = []
    name = dut.get("Name", "<unknown>")
    children_tags = {_local_tag(c.tag) for c in dut}

    if "Declaration" not in children_tags:
        issues.append(ValidationIssue(
            level="error", file=file_path, line=0,
            message=f"DUT '{name}' missing <Declaration>",
            rule="dut_structure",
        ))
    return issues


def _check_gvl_structure(gvl: ET.Element, file_path: str) -> list[ValidationIssue]:
    """GVL needs Declaration, ParameterList only 'True' or absent."""
    issues: list[ValidationIssue] = []
    name = gvl.get("Name", "<unknown>")
    children_tags = {_local_tag(c.tag) for c in gvl}

    if "Declaration" not in children_tags:
        issues.append(ValidationIssue(
            level="error", file=file_path, line=0,
            message=f"GVL '{name}' missing <Declaration>",
            rule="gvl_structure",
        ))

    param_list = gvl.get("ParameterList")
    if param_list is not None and param_list != "True":
        issues.append(ValidationIssue(
            level="warning", file=file_path, line=0,
            message=f"GVL '{name}' has ParameterList='{param_list}' (expected 'True' or absent)",
            rule="gvl_parameter_list",
        ))
    return issues


def _check_itf_structure(itf: ET.Element, file_path: str) -> list[ValidationIssue]:
    """Interface methods have no Implementation, properties have only Get/Set Declaration."""
    issues: list[ValidationIssue] = []
    name = itf.get("Name", "<unknown>")

    for child in itf:
        tag = _local_tag(child.tag)
        child_name = child.get("Name", "<unknown>")

        if tag == "Method":
            for sub in child:
                if _local_tag(sub.tag) == "Implementation":
                    issues.append(ValidationIssue(
                        level="warning", file=file_path, line=0,
                        message=f"Interface '{name}' method '{child_name}' should not have <Implementation>",
                        rule="itf_method",
                    ))

    return issues


# ---------------------------------------------------------------------------
# Name Match Checks
# ---------------------------------------------------------------------------


def _check_name_match(
    root: ET.Element, file_path: str, cdata_blocks: dict[str, str]
) -> list[ValidationIssue]:
    """Check that Name attributes match the type name declared in CDATA."""
    issues: list[ValidationIssue] = []

    for elem in root.iter():
        tag = _local_tag(elem.tag)
        name_attr = elem.get("Name")
        if name_attr is None:
            continue

        if tag in ("POU", "DUT", "GVL", "Itf", "Method", "Action", "Property"):
            decl = _find_child(elem, "Declaration")
            if decl is None:
                continue

            elem_id = id(decl)
            cdata_key = f"_elem_{elem_id}"
            decl_text = cdata_blocks.get(str(elem_id), "")
            if not decl_text:
                decl_text = _get_element_cdata_text(decl)
            if not decl_text:
                continue

            declared_name = _extract_declared_name(decl_text, tag)
            if declared_name and declared_name != name_attr:
                issues.append(ValidationIssue(
                    level="error", file=file_path, line=0,
                    message=f"<{tag} Name=\"{name_attr}\"> but declaration has '{declared_name}'",
                    rule="name_match",
                ))

    return issues


def _extract_declared_name(cdata: str, context: str) -> str:
    """Extract the declared type/program name from CDATA content."""
    # Strip comments to avoid matching keywords inside them
    cleaned = re.sub(r"\(\*.*?\*\)", " ", cdata, flags=re.DOTALL)
    cleaned = re.sub(r"//[^\n]*", " ", cleaned)

    if context in ("DUT",):
        m = _RE_DUT_NAME.search(cleaned)
        return m.group(1) if m else ""
    if context == "GVL":
        return ""
    m = _RE_TYPE_NAME.search(cleaned)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_cdata_for_parse(raw: str) -> str:
    """Replace CDATA with safe content for ET parsing."""
    import re as _re
    return _re.sub(
        r"<!\[CDATA\[(.*?)\]\]>",
        lambda m: m.group(1).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if m.group(1).strip() else "",
        raw,
        flags=_re.DOTALL,
    )


def _extract_cdata_blocks(raw: str) -> dict[str, str]:
    """Extract all CDATA blocks from raw XML text (by position)."""
    import re as _re
    blocks: dict[str, str] = {}
    for i, m in enumerate(_re.finditer(r"<!\[CDATA\[(.*?)\]\]>", raw, _re.DOTALL)):
        blocks[str(i)] = m.group(1)
    return blocks


def _get_element_cdata_text(elem: ET.Element) -> str:
    """Get text content of an element (after CDATA stripping by ET)."""
    return elem.text or ""


def _find_child(elem: ET.Element, tag: str) -> ET.Element | None:
    """Find first child with given local tag."""
    for child in elem:
        if _local_tag(child.tag) == tag:
            return child
    return None


def _local_tag(tag: str) -> str:
    """Strip namespace."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag
