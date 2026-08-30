"""Parse .TcDUT files into documentation sections."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from autodocs.constants import QUAL
from autodocs.declaration_parser import (
    extract_struct_like_body,
    parse_declarations_from_block,
    parse_enum_members,
)
from autodocs.markdown import md_table
from autodocs.text_utils import (
    _source_link_line,
    clean_return_type,
    has_hide_attribute,
    localname,
    strip_tc_attributes,
)
from autodocs.type_index import format_type_md
from autodocs.xml_reader import extract_dut_header_comment, gather_dut_declaration_text

def parse_tcDut(
    file_path: Path,
    type_index: dict | None = None,
    out_file: Path | None = None,
    docs_root: Path | None = None,
):
    """
    Parse a .TcDUT file and return a structured result or None if the DUT is hidden.

    Result shape:
      { "title": <type_name>, "sections": { KEY: markdown, ... } }
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    type_name = file_path.stem
    for el in root.iter():
        if localname(el.tag) == "DUT":
            type_name = el.get("Name") or type_name
            break

    src = _source_link_line(file_path, out_file)

    decl = gather_dut_declaration_text(root)
    if not decl:
        return {
            "title": type_name,
            "sections": {
                "SIGNATURE": f"# {type_name}\n" + src,
                "DUT": "_No declaration found._\n",
            },
        }

    if has_hide_attribute(decl):
        return None

    decl_no_attr = strip_tc_attributes(decl)

    def _find_struct_union_extends(text: str) -> str:
        m = re.search(
            rf"^\s*TYPE{QUAL}\s+\w+\s+EXTENDS\s+(?P<base>[A-Za-z_][\w\.]*)\s*:\s*(STRUCT|UNION)\b",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        return m.group("base").strip() if m else ""

    base_for_signature = _find_struct_union_extends(decl_no_attr)
    if base_for_signature:
        base_sig_md = format_type_md(base_for_signature, out_file, type_index, docs_root)
        signature_md = f"# {type_name} Extends {base_sig_md}\n" + src
    else:
        signature_md = f"# {type_name}\n" + src

    # Extract DUT header comment (block comment before TYPE)
    dut_comment = extract_dut_header_comment(decl)
    description_md = ""
    if dut_comment:
        description_md = f"## Description\n\n{dut_comment}\n"

    # Slice from the TYPE line onward so that header comments
    # (e.g. "(* Union overlay ... *)") cannot confuse keyword detection.
    type_line_m = re.search(
        rf"^\s*TYPE{QUAL}\b", decl_no_attr, flags=re.IGNORECASE | re.MULTILINE
    )
    decl_body = decl_no_attr[type_line_m.start():] if type_line_m else decl_no_attr

    # Try ENUM
    # Pattern 1: TYPE Name : [BaseType]? ( body ) [BaseType]? [:= Default]? ;
    enum_m = re.search(
        rf"^\s*TYPE{QUAL}\s+\w+\s*:\s*(?:\w+\s*)?\(\s*(?P<body>.*?)\)\s*(?P<base>\w+)?(?:\s*:=\s*\w+)?\s*;",
        decl_body,
        flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    if not enum_m:
        # Pattern 2: TYPE Name : BaseType ( body ) [:= Default]? ;
        enum_m = re.search(
            rf"^\s*TYPE{QUAL}\s+\w+\s*:\s*(?P<base>\w+)\s*\(\s*(?P<body>.*?)\)\s*(?::=\s*\w+)?\s*;",
            decl_body,
            flags=re.IGNORECASE | re.DOTALL | re.MULTILINE,
        )

    # Guard: if the regex matched but the body does not parse as enum members,
    # this is a false positive (e.g. STRING(size) / WSTRING(size) aliases).
    if enum_m:
        body = enum_m.group("body") or ""
        items = parse_enum_members(body)
        if not items:
            enum_m = None

    if enum_m:
        base = (enum_m.group("base") or "").strip()
        body = enum_m.group("body") or ""
        items = parse_enum_members(body)
        rows = [(f"`{n}`", f"`{v}`" if v else "", c) for (n, v, c) in items]

        parts = ["## Enum\n"]
        if base:
            base_md = format_type_md(base, out_file, type_index, docs_root)
            parts.append(f"Enum type: {base_md}\n\n")
        parts.append(md_table(["Name", "Value", "Comment"], rows) + "\n")

        sections = {
            "SIGNATURE": signature_md,
            "DUT": "".join(parts),
        }
        if description_md:
            sections["DESCRIPTION"] = description_md
        return {"title": type_name, "sections": sections}

    # Try STRUCT
    if re.search(r"\bSTRUCT\b", decl_body, flags=re.IGNORECASE):
        base_struct = _find_struct_union_extends(decl_body)
        body = extract_struct_like_body(decl_body, "STRUCT")
        fields = parse_declarations_from_block(body)
        rows = [(f"`{n}`", format_type_md(t, out_file, type_index, docs_root), init, c) for (n, t, init, c) in fields]

        parts = ["## Struct\n"]
        if base_struct:
            ext_md = format_type_md(base_struct, out_file, type_index, docs_root)
            parts.append(f"Extends {ext_md}\n\n")
        if rows:
            parts.append(md_table(["Name", "Type", "Init", "Comment"], rows) + "\n")
        else:
            parts.append("_No fields found in STRUCT._\n")

        sections = {
            "SIGNATURE": signature_md,
            "DUT": "".join(parts),
        }
        if description_md:
            sections["DESCRIPTION"] = description_md
        return {"title": type_name, "sections": sections}

    # Try UNION
    if re.search(r"\bUNION\b", decl_body, flags=re.IGNORECASE):
        base_union = _find_struct_union_extends(decl_body)
        body = extract_struct_like_body(decl_body, "UNION")
        fields = parse_declarations_from_block(body)
        rows = [(f"`{n}`", format_type_md(t, out_file, type_index, docs_root), init, c) for (n, t, init, c) in fields]

        parts = ["## Union\n"]
        if base_union:
            ext_md = format_type_md(base_union, out_file, type_index, docs_root)
            parts.append(f"Extends {ext_md}\n\n")
        if rows:
            parts.append(md_table(["Name", "Type", "Init", "Comment"], rows) + "\n")
        else:
            parts.append("_No fields found in UNION._\n")

        sections = {
            "SIGNATURE": signature_md,
            "DUT": "".join(parts),
        }
        if description_md:
            sections["DESCRIPTION"] = description_md
        return {"title": type_name, "sections": sections}

    # Try alias
    alias_m = re.search(
        rf"^\s*TYPE{QUAL}\s+\w+\s*:\s*(?P<alias>[^;]+)\s*;?",
        decl_body,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    if alias_m:
        alias = clean_return_type(alias_m.group("alias"))
        alias_md = format_type_md(alias, out_file, type_index, docs_root)
        md = f"## Alias\nAlias of {alias_md}\n"
        sections = {
            "SIGNATURE": signature_md,
            "DUT": md,
        }
        if description_md:
            sections["DESCRIPTION"] = description_md
        return {"title": type_name, "sections": sections}

    # Fallback
    sections = {
        "SIGNATURE": signature_md,
        "DUT": "_Unsupported DUT format._\n",
    }
    if description_md:
        sections["DESCRIPTION"] = description_md
    return {"title": type_name, "sections": sections}
