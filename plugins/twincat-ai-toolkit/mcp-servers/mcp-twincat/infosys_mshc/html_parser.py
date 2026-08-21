"""HTML parsing and structured content extraction for InfoSys MSHC pages."""

import html
import re
from typing import Any, Dict, List, Tuple

from infosys_mshc.constants import (
    DEFAULT_MAX_FULL_TEXT_CHARS,
    DEFAULT_MAX_METHODS,
    DEFAULT_MAX_PARAMS,
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
    text = text.replace("\xa0", " ").replace("\u00a0", " ").replace("\u200b", "").replace("\r", "")
    text = RE_MULTI_WS.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = RE_MULTI_NL.sub("\n\n", text)
    return text.strip()


_strip_tags = strip_tags


def detect_type(title: str, description: str = "", syntax: str = "") -> str:
    """Detect IEC 61131-3 entity type from title, syntax block, or description."""
    if not title:
        return "article"

    for prefix, type_name in TYPE_PREFIXES.items():
        if title.startswith(prefix):
            return type_name

    t_lower = title.lower().strip()
    if t_lower.startswith("method ") or t_lower.startswith("methode ") or t_lower.startswith("m_"):
        return "METHOD"
    if t_lower.startswith("property ") or t_lower.startswith("eigenschaft ") or t_lower.startswith("p_"):
        return "PROPERTY"
    if t_lower.startswith("function block ") or t_lower.startswith("funktionsbaustein ") or t_lower.startswith("fb_"):
        return "FUNCTION_BLOCK"
    if t_lower.startswith("function ") or t_lower.startswith("funktion ") or t_lower.startswith("f_"):
        return "FUNCTION"
    if t_lower.startswith("interface ") or t_lower.startswith("schnittstelle ") or t_lower.startswith("i_"):
        return "INTERFACE"
    if t_lower.startswith("struct ") or t_lower.startswith("structure ") or t_lower.startswith("struktur ") or t_lower.startswith("st_"):
        return "STRUCT"
    if t_lower.startswith("enum ") or t_lower.startswith("enumeration ") or t_lower.startswith("aufzählung ") or t_lower.startswith("e_"):
        return "ENUM"
    if t_lower.startswith("type ") or t_lower.startswith("datentyp ") or t_lower.startswith("t_"):
        return "TYPE"

    if syntax:
        s_upper = syntax.strip().upper()
        if s_upper.startswith("METHOD "):
            return "METHOD"
        if s_upper.startswith("PROPERTY "):
            return "PROPERTY"
        if s_upper.startswith("FUNCTION_BLOCK "):
            return "FUNCTION_BLOCK"
        if s_upper.startswith("FUNCTION "):
            return "FUNCTION"
        if s_upper.startswith("TYPE "):
            return "TYPE"
        if s_upper.startswith("INTERFACE "):
            return "INTERFACE"

    if description:
        d_lower = description.lower().strip()
        if d_lower.startswith("this method ") or d_lower.startswith("diese methode "):
            return "METHOD"
        if d_lower.startswith("this property ") or d_lower.startswith("diese eigenschaft "):
            return "PROPERTY"
        if d_lower.startswith("this function block ") or d_lower.startswith("dieser funktionsbaustein "):
            return "FUNCTION_BLOCK"
        if d_lower.startswith("this function ") or d_lower.startswith("diese funktion "):
            return "FUNCTION"

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
        if not name or name.lower() in ("name", "parameter", "bezeichnung"):
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
        if not name or name.lower() in ("name", "method name", "methodenname", "bezeichnung"):
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
        elif "development" in key or "engineering" in key or "entwicklungsumgebung" in key:
            reqs["development_environment"] = val
        elif "target" in key or "zielplattform" in key:
            reqs["target_platform"] = val
    return reqs


_extract_requirements = extract_requirements


def extract_library_and_parent(
    title: str,
    display_version: str = "",
    component: str = "",
    requirements: Dict[str, str] = None,
) -> Tuple[str, str, str]:
    """Extract library, parent symbol, and qualified_name from metadata and title."""
    reqs = requirements or {}
    library = ""
    if reqs.get("library"):
        library = reqs["library"].strip()
    elif display_version:
        library = display_version.split("(", 1)[0].strip()
    elif component:
        comp_lower = component.lower()
        if "tc3_" in comp_lower:
            idx = comp_lower.find("tc3_")
            library = "Tc3_" + "".join(word.capitalize() for word in component[idx + 4:].split("_"))
        elif "tc2_" in comp_lower:
            idx = comp_lower.find("tc2_")
            library = "Tc2_" + "".join(word.capitalize() for word in component[idx + 4:].split("_"))
        else:
            library = component

    parent = ""
    if "." in title:
        parts = title.split(".", 1)
        parent = parts[0].strip()
    elif "::" in title:
        parts = title.split("::", 1)
        parent = parts[0].strip()

    if parent and library:
        qualified_name = f"{library}.{parent}.{title.split('.')[-1]}"
    elif parent:
        qualified_name = f"{parent}.{title.split('.')[-1]}"
    elif library and title:
        qualified_name = f"{library}.{title}"
    else:
        qualified_name = title

    return library, parent, qualified_name


def parse_page(
    raw_html: str,
    html_path: str,
    include_full_text: bool = True,
    max_full_text_chars: int = DEFAULT_MAX_FULL_TEXT_CHARS,
    max_methods: int = DEFAULT_MAX_METHODS,
    max_params: int = DEFAULT_MAX_PARAMS,
) -> Dict[str, Any]:
    """Parse raw HTML page content into a structured dictionary with token budget limits."""
    parts = html_path.split("/")
    component = parts[0] if len(parts) > 1 else ""

    title_m = RE_TITLE.search(raw_html)
    title = html.unescape(title_m.group(1)).strip() if title_m else ""

    desc_m = RE_DESCRIPTION_META.search(raw_html)
    description = html.unescape(desc_m.group(1)).strip() if desc_m else ""

    version_m = RE_DISPLAY_VERSION.search(raw_html)
    display_version = (
        html.unescape(version_m.group(1)).strip() if version_m else ""
    )

    syntax = extract_syntax(raw_html)
    sym_type = detect_type(title, description=description, syntax=syntax)
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

    library, parent, qualified_name = extract_library_and_parent(
        title, display_version, component, requirements
    )

    # Token & item limits
    truncated = False
    methods_total = len(methods)
    methods_shown = methods_total
    if methods_total > max_methods:
        methods = methods[:max_methods]
        methods_shown = len(methods)
        truncated = True

    params_total = len(inputs) + len(outputs) + len(parameters)
    params_shown = params_total
    if params_total > max_params:
        if len(inputs) > max_params:
            inputs = inputs[:max_params]
            outputs = []
            parameters = []
        elif len(inputs) + len(outputs) > max_params:
            outputs = outputs[:max_params - len(inputs)]
            parameters = []
        else:
            rem = max_params - (len(inputs) + len(outputs))
            parameters = parameters[:rem]
        params_shown = len(inputs) + len(outputs) + len(parameters)
        truncated = True

    full_text_raw = strip_tags(raw_html)
    total_full_text_chars = len(full_text_raw)

    if include_full_text:
        if total_full_text_chars > max_full_text_chars:
            full_text = full_text_raw[:max_full_text_chars] + "\n... [truncated]"
            truncated = True
        else:
            full_text = full_text_raw
        full_text_included = True
    else:
        full_text = ""
        full_text_included = False

    result: Dict[str, Any] = {
        "title": title,
        "component": component,
        "type": sym_type,
        "path": html_path,
        "library": library,
        "parent": parent,
        "qualified_name": qualified_name,
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
    result["truncated"] = truncated
    result["full_text_included"] = full_text_included
    result["total_full_text_chars"] = total_full_text_chars
    if methods_total > 0:
        result["methods_total"] = methods_total
        result["methods_shown"] = methods_shown
    if params_total > 0:
        result["params_total"] = params_total
        result["params_shown"] = params_shown

    return result


_parse_page = parse_page
