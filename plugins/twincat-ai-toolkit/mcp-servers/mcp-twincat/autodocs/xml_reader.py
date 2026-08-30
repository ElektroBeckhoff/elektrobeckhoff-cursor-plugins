"""XML declaration extraction from TwinCAT source files."""
import re
import xml.etree.ElementTree as ET

from autodocs.constants import QUAL
from autodocs.text_utils import (
    _extract_block_comment_texts,
    clean_return_type,
    has_hide_attribute,
    localname,
    strip_tc_attributes,
)

def gather_main_declaration_text(root: ET.Element) -> str:
    """
    Get only the <Declaration> text that is directly under the <POU> element
    (ignore declarations inside <Method>, <Property>, ...).
    """
    pou = None
    for el in root.iter():
        if localname(el.tag) == "POU":
            pou = el
            break
    if pou is None:
        return ""

    chunks = []
    for child in list(pou):
        if localname(child.tag) == "Declaration" and child.text:
            chunks.append(child.text)
    return "\n".join(chunks).replace("\r\n", "\n").replace("\r", "\n")


def gather_itf_declaration_text(root: ET.Element) -> str:
    """
    Get only the <Declaration> text that is directly under the <Itf> element
    (ignore declarations inside <Method>, <Property>, ...).
    """
    itf = None
    for el in root.iter():
        if localname(el.tag) == "Itf":
            itf = el
            break
    if itf is None:
        return ""

    chunks = []
    for child in list(itf):
        if localname(child.tag) == "Declaration" and child.text:
            chunks.append(child.text)
    return "\n".join(chunks).replace("\r\n", "\n").replace("\r", "\n")


def extract_itf_header_comment(decl_text: str) -> str:
    """
    Extract a block comment `(* ... *)` immediately preceding the INTERFACE
    signature line.
    """
    import textwrap

    if not decl_text:
        return ""

    sig = re.search(
        r"^\s*INTERFACE\b.*$",
        decl_text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not sig:
        return ""

    before = decl_text[: sig.start()]
    before_stripped = strip_tc_attributes(before).rstrip()

    blocks = _extract_block_comment_texts(before_stripped)
    if blocks:
        comment = " ".join(b.strip() for b in blocks if b.strip())
        return textwrap.dedent(comment).strip()

    return ""


def extract_pou_header_comment(decl_text: str) -> str:
    """
    Extract a block comment `(* ... *)` immediately preceding the POU signature line.

    Extraction logic:
    - Locate the FUNCTION_BLOCK, FUNCTION, or PROGRAM signature line.
    - Search backward from that line for the nearest block comment.
    - If found, normalize indentation and return the comment text.
    - Inline single-line comments (`//`) are not extracted as header comments.

    Args:
        decl_text: The full declaration text from gather_main_declaration_text().

    Returns:
        The extracted comment text (normalized, multi-line preserved), or empty string.
    """
    import textwrap

    if not decl_text:
        return ""

    # Locate the POU signature line (FUNCTION_BLOCK, FUNCTION, or PROGRAM).
    pou_line = re.search(
        r"^\s*(FUNCTION_BLOCK|FUNCTION|PROGRAM)\b.*$",
        decl_text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not pou_line:
        return ""

    # Extract text BEFORE the POU line.
    before_pou = decl_text[: pou_line.start()]
    before_stripped = strip_tc_attributes(before_pou).rstrip()

    blocks = _extract_block_comment_texts(before_stripped)
    if blocks:
        comment = " ".join(b.strip() for b in blocks if b.strip())
        return textwrap.dedent(comment).strip()

    return ""

def gather_method_declarations(root: ET.Element, parent_tag: str = "POU"):
    """
    Parse all <Method> nodes below the container element (*parent_tag*) and
    extract a compact data model per method.

    Extraction logic:
    - METHOD line is located precisely, then:
      * Return type is read and cleaned (no comment leakage).
      * A human-readable description is assembled from the nearest comment around the signature:
        1) An inline block comment that starts on the METHOD line (may span multiple lines).
        2) An inline // comment on the METHOD line.
        3) A leading block (`(* ... *)`) or line (`// ...`) comment immediately AFTER the METHOD line,
           and BEFORE any VAR_* section.
      The description may be multiline; downstream renderers can compress or format it as needed.

    Notes:
    - Methods with `{attribute 'hide'}` in their Declaration are skipped.
    - The remaining declaration text (after the METHOD signature line) is preserved for later
      VAR_* interface parsing.

    Returns:
        List[Dict]: Each dict has keys:
            - "name":    Method name (str)
            - "return":  Clean return type or "" (str)
            - "decl":    Declaration text *after* the METHOD line (str)
            - "comment": Description text (possibly multiline) or "" (str)
    """
    import textwrap

    methods = []
    pou = None
    for el in root.iter():
        if localname(el.tag) == parent_tag:
            pou = el
            break
    if pou is None:
        return methods

    for child in list(pou):
        if localname(child.tag) != "Method":
            continue

        m_name = child.get("Name") or ""
        m_decl_raw = ""
        for sub in list(child):
            if localname(sub.tag) == "Declaration" and sub.text:
                m_decl_raw = sub.text.replace("\r\n", "\n").replace("\r", "\n")
                break

        # Respect hidden methods.
        if m_decl_raw and has_hide_attribute(m_decl_raw):
            continue

        # Locate the METHOD line with absolute positions to slice precisely.
        mline = re.search(r"^\s*METHOD\b.*$", m_decl_raw, flags=re.IGNORECASE | re.MULTILINE)
        method_line = mline.group(0) if mline else ""

        # Extract return type from the METHOD line.
        m_ret = ""
        if method_line:
            mr = re.search(
                rf"^\s*METHOD{QUAL}\s+\w+(?:\s*:\s*(?P<ret>[^\r\n]+))?",
                method_line,
                flags=re.IGNORECASE,
            )
            if mr and mr.group("ret"):
                m_ret = clean_return_type(mr.group("ret"))

        # Assemble description (look in a robust order around the signature).
        desc = ""
        if mline:
            start_idx = mline.start()
            line_text = method_line

            # 0) FIRST: Check for block comment(s) BEFORE the METHOD line (most common pattern)
            before_method = m_decl_raw[:start_idx]
            before_stripped = strip_tc_attributes(before_method).rstrip()
            blocks = _extract_block_comment_texts(before_stripped)
            if blocks:
                desc = " ".join(b.strip() for b in blocks if b.strip())
            else:
                # 1) Inline block comment that STARTS on the METHOD line — may span multiple lines.
                idx_inline_block = line_text.find("(*")
                if idx_inline_block != -1:
                    # If it closes on the same line, read inline; else, span into the following text.
                    end_same = line_text.find("*)", idx_inline_block + 2)
                    if end_same != -1:
                        desc = line_text[idx_inline_block + 2 : end_same]
                    else:
                        abs_start = start_idx + idx_inline_block + 2
                        end = m_decl_raw.find("*)", abs_start)
                        if end != -1:
                            desc = m_decl_raw[abs_start:end]
                else:
                    # 2) Inline single-line comment on the METHOD line.
                    m_line_comment = re.search(r"//\s*(?P<c>.*)$", line_text)
                    if m_line_comment and m_line_comment.group("c").strip():
                        desc = m_line_comment.group("c").strip()
                    else:
                        # 3) A leading block or line comment immediately AFTER the METHOD line.
                        rest_text = m_decl_raw[mline.end():]
                        rest_text_l = strip_tc_attributes(rest_text).lstrip()

                        # Prefer a block comment first.
                        m_lead_block = re.match(r"^\(\*(?P<c>.*?)\*\)", rest_text_l, flags=re.DOTALL)
                        if m_lead_block and m_lead_block.group("c").strip():
                            desc = m_lead_block.group("c").strip()
                        else:
                            # Or a single-line comment right at the beginning of the remainder.
                            m_lead_line = re.match(r"^//\s*(?P<c>.*)$", rest_text_l)
                            if m_lead_line and m_lead_line.group("c").strip():
                                desc = m_lead_line.group("c").strip()

        # Normalize indentation and whitespace of the description.
        desc = textwrap.dedent(desc).strip()

        # Keep declaration text AFTER the METHOD line for interface parsing.
        m_decl_vars = m_decl_raw
        if mline:
            m_decl_vars = m_decl_raw[mline.end():]

        methods.append({
            "name": m_name,
            "return": m_ret,
            "decl": m_decl_vars,
            "comment": desc,
        })

    return methods



def gather_property_declarations(root: ET.Element, parent_tag: str = "POU"):
    """
    Collect all <Property> nodes under the container element (*parent_tag*)
    and return:
    [
      { "name": <str>, "type": <str|''>, "has_get": bool, "has_set": bool },
      ...
    ]
    Properties with {attribute 'hide'} in their declaration are skipped.
    """
    props = []
    pou = None
    for el in root.iter():
        if localname(el.tag) == parent_tag:
            pou = el
            break
    if pou is None:
        return props

    for child in list(pou):
        if localname(child.tag) != "Property":
            continue

        p_name = child.get("Name") or ""

        p_decl_raw = ""
        for sub in list(child):
            if localname(sub.tag) == "Declaration" and sub.text:
                p_decl_raw = sub.text.replace("\r\n", "\n").replace("\r", "\n")
                break

        if p_decl_raw and has_hide_attribute(p_decl_raw):
            continue

        p_type = ""
        if p_decl_raw:
            for ln in p_decl_raw.splitlines():
                ln_no_attr = strip_tc_attributes(ln).strip()
                if re.match(r"^\s*PROPERTY\b", ln_no_attr, flags=re.IGNORECASE):
                    m = re.search(
                        rf"^\s*PROPERTY{QUAL}\s+\w+\s*:\s*(?P<type>[^;\r\n]+)",
                        ln_no_attr,
                        flags=re.IGNORECASE,
                    )
                    if m:
                        p_type = clean_return_type(m.group("type"))
                    break

        has_get = any(localname(sc.tag) == "Get" for sc in list(child))
        has_set = any(localname(sc.tag) == "Set" for sc in list(child))

        props.append(
            {"name": p_name, "type": p_type, "has_get": has_get, "has_set": has_set}
        )

    return props


def gather_dut_declaration_text(root: ET.Element) -> str:
    """
    Get ONLY the <Declaration> directly under <DUT> (ignore nested elements).
    Returns the raw declaration text or ''.
    """
    dut = None
    for el in root.iter():
        if localname(el.tag) == "DUT":
            dut = el
            break
    if dut is None:
        return ""
    for child in list(dut):
        if localname(child.tag) == "Declaration" and child.text:
            return child.text.replace("\r\n", "\n").replace("\r", "\n")
    return ""


def extract_dut_header_comment(decl_text: str) -> str:
    """
    Extract a block comment `(* ... *)` immediately preceding the TYPE signature line.

    Extraction logic:
    - Locate the TYPE signature line.
    - Search backward from that line for the nearest block comment.
    - If found, normalize indentation and return the comment text.

    Args:
        decl_text: The full declaration text from gather_dut_declaration_text().

    Returns:
        The extracted comment text (normalized, multi-line preserved), or empty string.
    """
    import textwrap

    if not decl_text:
        return ""

    # Locate the TYPE signature line.
    type_line = re.search(
        rf"^\s*TYPE{QUAL}\b.*$",
        decl_text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if not type_line:
        return ""

    # Extract text BEFORE the TYPE line.
    before_type = decl_text[: type_line.start()]
    before_stripped = strip_tc_attributes(before_type).rstrip()

    # Find all block comments `(* ... *)` right before the TYPE signature and
    # join their inner texts (handles consecutive blocks).
    blocks = _extract_block_comment_texts(before_stripped)
    if blocks:
        comment = " ".join(b.strip() for b in blocks if b.strip())
        return textwrap.dedent(comment).strip()

    return ""


# --------------------------------------------------------------------
# GVL helpers
# --------------------------------------------------------------------


def gather_gvl_declaration_text(root: ET.Element) -> str:
    """
    Get the <Declaration> text directly under a <GVL> element.
    Returns the raw declaration text or ''.
    """
    for el in root.iter():
        if localname(el.tag) == "GVL":
            for child in list(el):
                if localname(child.tag) == "Declaration" and child.text:
                    return child.text.replace("\r\n", "\n").replace("\r", "\n")
    return ""


def extract_gvl_header_comment(decl_text: str) -> str:
    """
    Extract a block comment ``(* ... *)`` that appears before the first
    ``VAR_GLOBAL`` keyword in a GVL declaration.
    """
    import textwrap

    if not decl_text:
        return ""
    vg = re.search(r"\bVAR_GLOBAL\b", decl_text, flags=re.IGNORECASE)
    if not vg:
        return ""
    before = strip_tc_attributes(decl_text[: vg.start()]).rstrip()
    blocks = _extract_block_comment_texts(before)
    if blocks:
        comment = " ".join(b.strip() for b in blocks if b.strip())
        return textwrap.dedent(comment).strip()
    return ""


def extract_gvl_var_blocks(decl_text: str) -> dict:
    """
    Parse all ``VAR_GLOBAL ... END_VAR`` regions from a GVL declaration and
    group the inner variable text by modifier category.

    Returns::

        {
            "CONSTANT":   "merged body ...",
            "VAR":        "merged body ...",
            "PERSISTENT": "merged body ...",
            "RETAIN":     "merged body ...",
        }
    """
    blocks: dict[str, list[str]] = {
        "CONSTANT": [],
        "VAR": [],
        "PERSISTENT": [],
        "RETAIN": [],
    }
    if not decl_text:
        return {k: "\n".join(v) for k, v in blocks.items()}

    pattern = (
        r"VAR_GLOBAL\b((?:\s+(?:CONSTANT|PERSISTENT|RETAIN))*)"
        r"[^\S\r\n]*(.*?)(?=END_VAR\b)"
    )
    for m in re.finditer(pattern, decl_text, flags=re.DOTALL | re.IGNORECASE):
        modifiers = m.group(1).upper().split()
        body = m.group(2).strip()
        if not body:
            continue
        if "CONSTANT" in modifiers:
            blocks["CONSTANT"].append(body)
        elif "PERSISTENT" in modifiers:
            blocks["PERSISTENT"].append(body)
        elif "RETAIN" in modifiers:
            blocks["RETAIN"].append(body)
        else:
            blocks["VAR"].append(body)

    return {k: "\n".join(v) for k, v in blocks.items()}
