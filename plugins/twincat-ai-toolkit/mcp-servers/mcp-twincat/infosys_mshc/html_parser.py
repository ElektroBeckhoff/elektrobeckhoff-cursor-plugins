"""HTML parsing and structured content extraction for InfoSys MSHC pages."""

import html
import re
from typing import Any, Dict, List, Optional, Tuple

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

RE_PREFIX_STRIP = re.compile(
    r'^(?:Interface|Schnittstelle|Function\s+Block|Funktionsbaustein|Function|Funktion|Struct|Struktur|Structure|Type|Datentyp|Enum|Aufz[äa]hlung|Method|Methode|Property|Eigenschaft)\s+',
    re.IGNORECASE,
)

RE_VALID_IEC_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

NOISE_PARAM_NAMES = {
    "name", "parameter", "bezeichnung", "eingang", "ausgang",
    "return parameter", "rückgabeparameter", "meaning", "bedeutung",
    "hinweis", "notice", "description", "beschreibung", "wert", "value",
    "typ", "type", "daten", "datentyp", "constant", "konstante",
}


def strip_tags(text: str) -> str:
    """Strip HTML tags, unescape HTML entities, and normalize whitespace."""
    text = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
    text = re.sub(r'</?(?:p|div|li|tr|td|th|h[1-6])[^>]*>', ' ', text, flags=re.IGNORECASE)
    text = RE_TAG.sub("", text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ").replace("\u00a0", " ").replace("\u200b", "").replace("\r", "")
    text = RE_MULTI_WS.sub(" ", text)
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)
    text = RE_MULTI_NL.sub("\n\n", text)
    return text.strip()


_strip_tags = strip_tags


def detect_type(
    title: str,
    description: str = "",
    syntax: str = "",
    full_text: str = "",
    return_type: Optional[str] = None,
    has_methods: bool = False,
) -> str:
    """Detect IEC 61131-3 entity type from title, syntax block, description, full_text, or return_type."""
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
    if t_lower.startswith("interface ") or t_lower.startswith("schnittstelle ") or t_lower.startswith("i_") or t_lower.startswith("itc"):
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
        if s_upper.startswith("FUNCTION_BLOCK ") or s_upper.startswith("FUNCTION BLOCK "):
            return "FUNCTION_BLOCK"
        if s_upper.startswith("FUNCTION ") or s_upper.startswith("FUNCTION:"):
            return "FUNCTION"
        if s_upper.startswith("TYPE "):
            return "TYPE"
        if s_upper.startswith("INTERFACE "):
            return "INTERFACE"

    if full_text:
        ft_upper = full_text[:3000].upper()
        if re.search(r'\bFUNCTION_BLOCK\s+', ft_upper):
            return "FUNCTION_BLOCK"
        if re.search(r'\bFUNCTION\s+[A-Za-z0-9_]+\s*:', ft_upper) or re.search(r'\bFUNCTION\s*:', ft_upper):
            return "FUNCTION"
        if re.search(r'\bINTERFACE\s+', ft_upper):
            return "INTERFACE"

    if description:
        d_lower = description.lower().strip()
        if d_lower.startswith("this method ") or d_lower.startswith("diese methode ") or " method " in d_lower:
            return "METHOD"
        if d_lower.startswith("this property ") or d_lower.startswith("diese eigenschaft ") or " property " in d_lower:
            return "PROPERTY"
        if d_lower.startswith("this function block ") or d_lower.startswith("dieser funktionsbaustein ") or " function block " in d_lower:
            return "FUNCTION_BLOCK"
        if (
            d_lower.startswith("this function ")
            or d_lower.startswith("diese funktion ")
            or d_lower.startswith("the function ")
            or d_lower.startswith("die funktion ")
            or " function " in d_lower
            or " funktion " in d_lower
        ):
            return "FUNCTION"

    if return_type and not has_methods:
        return "FUNCTION"

    if has_methods:
        return "FUNCTION_BLOCK"

    return "article"


_detect_type = detect_type


def extract_canonical_name_and_type(
    title: str,
    description: str = "",
    syntax: str = "",
    full_text: str = "",
    return_type: Optional[str] = None,
    has_methods: bool = False,
) -> Tuple[str, str]:
    """Extract stripped canonical IEC symbol name and symbol type."""
    detected = detect_type(
        title,
        description=description,
        syntax=syntax,
        full_text=full_text,
        return_type=return_type,
        has_methods=has_methods,
    )
    clean_title = RE_PREFIX_STRIP.sub("", title).strip()
    return clean_title or title, detected


def extract_syntax(raw_html: str) -> str:
    """Extract IEC 61131-3 code/syntax declaration block from HTML."""
    blocks = RE_CODE_BLOCK.findall(raw_html)
    for block in blocks:
        text = strip_tags(block)
        if any(
            kw in text
            for kw in (
                "FUNCTION_BLOCK",
                "FUNCTION BLOCK",
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


def extract_return_type(syntax: str, full_text: str = "", sym_type: str = "") -> Optional[str]:
    """Extract return type for Functions, Methods, and Properties from declaration syntax or text."""
    text_to_search = (syntax + "\n" + full_text[:2000]).replace("VAR_INPUT", " VAR_INPUT ").replace("VAR_OUTPUT", " VAR_OUTPUT ")

    # 1. Standard ST FUNCTION declaration e.g. "FUNCTION MEMCPY : UDINT" or "MEMCPY FUNCTION : UDINT"
    m = re.search(r'FUNCTION\s+\w+\s*:\s*([A-Za-z0-9_]+(?:\s*\([^)]*\))?)', text_to_search, re.IGNORECASE)
    if m:
        ret = m.group(1).strip()
        return ret.split("(")[0].strip()

    m2 = re.search(r'(\w+)\s+FUNCTION\s*:\s*([A-Za-z0-9_]+(?:\s*\([^)]*\))?)', text_to_search, re.IGNORECASE)
    if m2:
        ret = m2.group(2).strip()
        return ret.split("(")[0].strip()

    # 2. METHOD or PROPERTY declaration e.g. "METHOD M_GetVal : INT"
    m_meth = re.search(r'(?:METHOD|PROPERTY)\s+\w+\s*:\s*([A-Za-z0-9_]+(?:\s*\([^)]*\))?)', text_to_search, re.IGNORECASE)
    if m_meth:
        ret = m_meth.group(1).strip()
        return ret.split("(")[0].strip()

    return None


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
    """Extract parameter / variable definitions from an HTML table, filtering out non-identifier noise."""
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

        if not name:
            continue

        name_lower = name.lower()
        if name_lower in NOISE_PARAM_NAMES:
            continue
        if name.startswith(("0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ">", "<", "=", "+", "-", "*", "/", "#")):
            continue
        if " " in name and not name.startswith("_"):
            continue

        if len(cells) == 2 and not desc:
            clean_t = typ.strip()
            if (len(clean_t.split()) > 2 and not clean_t.upper().startswith(("POINTER TO", "REFERENCE TO", "ARRAY [", "ARRAY["))) or clean_t.endswith((".", ";", ":")):
                continue
            if clean_t.lower() in ("description", "beschreibung", "meaning", "bedeutung", "hinweis", "notice", "wert", "value"):
                continue

        params.append({"name": name, "type": typ, "description": desc})
    return params


_parse_param_table = parse_param_table


def extract_properties(section_html: str) -> List[Dict[str, str]]:
    """Extract property list from properties section HTML table."""
    if not section_html:
        return []
    rows = RE_TABLE_ROW.findall(section_html)
    properties: List[Dict[str, str]] = []
    for row in rows:
        cells = RE_TABLE_CELL.findall(row)
        if len(cells) < 1:
            continue
        name = strip_tags(cells[0]).strip()
        if not name or name.lower() in ("name", "property", "eigenschaft", "bezeichnung"):
            continue

        typ = strip_tags(cells[1]).strip() if len(cells) > 1 else "BOOL"
        desc = strip_tags(cells[2]).strip() if len(cells) > 2 else ""
        access = "Get/Set"
        if len(cells) > 3:
            access = strip_tags(cells[3]).strip()

        properties.append({
            "name": name,
            "type": typ,
            "description": desc,
            "access": access,
        })
    return properties


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

    properties = extract_properties(sections.get("properties", ""))

    full_text_raw = strip_tags(raw_html)
    return_type = extract_return_type(syntax, full_text_raw)
    has_methods = bool(methods)

    canonical_name, sym_type = extract_canonical_name_and_type(
        title,
        description=description,
        syntax=syntax,
        full_text=full_text_raw,
        return_type=return_type,
        has_methods=has_methods,
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
        "canonical_name": canonical_name,
        "component": component,
        "type": sym_type,
        "sym_type": sym_type,
        "path": html_path,
        "library": library,
        "parent": parent,
        "qualified_name": qualified_name,
        "description": description,
        "syntax": syntax,
    }
    if return_type:
        result["return_type"] = return_type
    if inputs:
        result["inputs"] = inputs
    if outputs:
        result["outputs"] = outputs
    if parameters:
        result["parameters"] = parameters
    if methods:
        result["methods"] = methods
    if properties:
        result["properties"] = properties
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
