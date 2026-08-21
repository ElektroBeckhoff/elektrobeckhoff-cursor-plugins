"""HTML parsing and structured content extraction for InfoSys MSHC pages."""

import html
from typing import Any, Dict, List

from infosys_mshc.constants import (
    RE_CODE_BLOCK,
    RE_DESCRIPTION_META,
    RE_DISPLAY_VERSION,
    RE_H2,
    RE_MULTI_NL,
    RE_MULTI_WS,
    RE_TABLE_CELL,
    RE_TABLE_ROW,
    RE_TAG,
    RE_TITLE,
    SECTION_ALIASES,
    TYPE_PREFIXES,
)


def strip_tags(text: str) -> str:
    """Strip HTML tags, unescape HTML entities, and normalize whitespace."""
    text = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    text = RE_TAG.sub("", text)
    text = html.unescape(text)
    text = RE_MULTI_WS.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = RE_MULTI_NL.sub("\n\n", text)
    return text.strip()


_strip_tags = strip_tags


def detect_type(title: str) -> str:
    """Detect IEC 61131-3 entity type from title prefix (e.g. FB_, ST_, E_)."""
    for prefix, type_name in TYPE_PREFIXES.items():
        if title.startswith(prefix):
            return type_name
    return "article"


_detect_type = detect_type


def extract_syntax(raw_html: str) -> str:
    """Extract IEC 61131-3 code/syntax declaration block from HTML."""
    blocks = RE_CODE_BLOCK.findall(raw_html)
    for block in blocks:
        text = strip_tags(block)
        if any(
            kw in text
            for kw in (
                "FUNCTION_BLOCK",
                "FUNCTION ",
                "VAR_INPUT",
                "VAR_OUTPUT",
                "TYPE ",
                "METHOD ",
                "PROPERTY ",
                "PROGRAM ",
                "END_VAR",
                "END_TYPE",
                "END_STRUCT",
            )
        ):
            return text
    return ""


_extract_syntax = extract_syntax


def split_sections(raw_html: str) -> Dict[str, str]:
    """Split HTML content by <h2> headings, normalizing section names via aliases."""
    headings = list(RE_H2.finditer(raw_html))
    if not headings:
        return {}
    sections: Dict[str, str] = {}
    for i, m in enumerate(headings):
        name = strip_tags(m.group(1)).strip().lower()
        key = SECTION_ALIASES.get(name, name)
        start = m.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(raw_html)
        sections[key] = raw_html[start:end]
    return sections


_split_sections = split_sections


def parse_param_table(section_html: str) -> List[Dict[str, str]]:
    """Extract parameter / variable definitions from an HTML table."""
    if not section_html:
        return []
    rows = RE_TABLE_ROW.findall(section_html)
    params: List[Dict[str, str]] = []
    for row in rows:
        cells = RE_TABLE_CELL.findall(row)
        if len(cells) < 2:
            continue
        name = strip_tags(cells[0]).strip()
        typ = strip_tags(cells[1]).strip()
        desc = strip_tags(cells[2]).strip() if len(cells) > 2 else ""
        if not name or name.lower() in ("name", "parameter"):
            continue
        params.append({"name": name, "type": typ, "description": desc})
    return params


_parse_param_table = parse_param_table


def extract_methods(section_html: str) -> List[Dict[str, str]]:
    """Extract method list from methods section HTML table or text lines."""
    if not section_html:
        return []
    rows = RE_TABLE_ROW.findall(section_html)
    methods: List[Dict[str, str]] = []
    for row in rows:
        cells = RE_TABLE_CELL.findall(row)
        if len(cells) < 1:
            continue
        name = strip_tags(cells[0]).strip()
        desc = strip_tags(cells[1]).strip() if len(cells) > 1 else ""
        if not name or name.lower() in ("name", "method name", "methodenname"):
            continue
        methods.append({"name": name, "description": desc})
    if methods:
        return methods
    text = strip_tags(section_html)
    fallback: List[Dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("name"):
            continue
        token = line.split("(")[0].split("-")[0].split(":")[0].strip()
        if token and len(token) < 80 and " " not in token:
            fallback.append({"name": token, "description": ""})
    return fallback


_extract_methods = extract_methods


def extract_requirements(section_html: str) -> Dict[str, str]:
    """Extract library name, TwinCAT version, and target requirements from table."""
    if not section_html:
        return {}
    rows = RE_TABLE_ROW.findall(section_html)
    reqs: Dict[str, str] = {}
    for row in rows:
        cells = RE_TABLE_CELL.findall(row)
        if len(cells) < 2:
            continue
        key = strip_tags(cells[0]).strip().lower()
        val = strip_tags(cells[1]).strip()
        if "plc lib" in key or "plc librar" in key or "tc3 plc lib" in key:
            reqs["library"] = val
        elif "twincat" in key and "version" in key:
            reqs["twincat_version"] = val
        elif "development" in key or "engineering" in key:
            reqs["development_environment"] = val
        elif "target" in key:
            reqs["target_platform"] = val
    return reqs


_extract_requirements = extract_requirements


def parse_page(raw_html: str, html_path: str) -> Dict[str, Any]:
    """Parse raw HTML page content into a structured dictionary."""
    parts = html_path.split("/")
    component = parts[0] if len(parts) > 1 else ""

    title_m = RE_TITLE.search(raw_html)
    title = html.unescape(title_m.group(1)).strip() if title_m else ""
    sym_type = detect_type(title)

    desc_m = RE_DESCRIPTION_META.search(raw_html)
    description = html.unescape(desc_m.group(1)).strip() if desc_m else ""

    version_m = RE_DISPLAY_VERSION.search(raw_html)
    display_version = (
        html.unescape(version_m.group(1)).strip() if version_m else ""
    )

    syntax = extract_syntax(raw_html)
    sections = split_sections(raw_html)

    inputs = parse_param_table(sections.get("inputs", ""))
    outputs = parse_param_table(sections.get("outputs", ""))
    parameters = parse_param_table(sections.get("parameter", ""))
    if not inputs and not outputs and parameters:
        inputs = parameters
        parameters = []

    methods = extract_methods(sections.get("methods", ""))
    if not methods:
        methods = extract_methods(
            sections.get("event-driven methods (callback methods)", "")
        )

    requirements = extract_requirements(sections.get("requirements", ""))
    if display_version and not requirements.get("library"):
        req_parts = display_version.split("(", 1)
        requirements["library"] = req_parts[0].strip()
        if len(req_parts) > 1:
            requirements["twincat_version"] = req_parts[1].rstrip(")")

    full_text = strip_tags(raw_html)

    result: Dict[str, Any] = {
        "title": title,
        "component": component,
        "type": sym_type,
        "path": html_path,
        "description": description,
        "syntax": syntax,
    }
    if inputs:
        result["inputs"] = inputs
    if outputs:
        result["outputs"] = outputs
    if parameters:
        result["parameters"] = parameters
    if methods:
        result["methods"] = methods
    if requirements:
        result["requirements"] = requirements
    result["full_text"] = full_text
    return result


_parse_page = parse_page
