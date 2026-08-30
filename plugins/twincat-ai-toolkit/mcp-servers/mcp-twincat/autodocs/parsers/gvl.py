"""Parse .TcGVL files into documentation sections."""
import xml.etree.ElementTree as ET
from pathlib import Path

from autodocs.declaration_parser import parse_declarations_from_block
from autodocs.markdown import md_table
from autodocs.text_utils import _source_link_line, has_hide_attribute, localname
from autodocs.type_index import format_type_md
from autodocs.xml_reader import (
    extract_gvl_header_comment,
    extract_gvl_var_blocks,
    gather_gvl_declaration_text,
)

_GVL_BLOCK_HEADINGS = {
    "CONSTANT": "Constants",
    "VAR": "Variables",
    "PERSISTENT": "Persistent Variables",
    "RETAIN": "Retain Variables",
}


def parse_tcGvl(
    file_path: Path,
    type_index: dict | None = None,
    out_file: Path | None = None,
    docs_root: Path | None = None,
):
    """
    Parse a .TcGVL file and return a structured result or None if the GVL is hidden.

    Result shape:
      { "title": <gvl_name>, "sections": { KEY: markdown, ... } }
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    gvl_name = file_path.stem
    for el in root.iter():
        if localname(el.tag) == "GVL":
            gvl_name = el.get("Name") or gvl_name
            break

    src = _source_link_line(file_path, out_file)

    decl = gather_gvl_declaration_text(root)
    if not decl:
        return {
            "title": gvl_name,
            "sections": {
                "SIGNATURE": f"# {gvl_name}\n" + src,
                "GVL": "_No declaration found._\n",
            },
        }

    if has_hide_attribute(decl):
        return None

    signature_md = f"# {gvl_name}\n" + src

    header_comment = extract_gvl_header_comment(decl)
    description_md = ""
    if header_comment:
        description_md = f"## Description\n\n{header_comment}\n"

    var_blocks = extract_gvl_var_blocks(decl)

    parts: list[str] = []
    for key in ("CONSTANT", "VAR", "PERSISTENT", "RETAIN"):
        body = var_blocks.get(key, "")
        if not body:
            continue
        heading = _GVL_BLOCK_HEADINGS[key]
        fields = parse_declarations_from_block(body)
        if not fields:
            continue
        rows = [
            (
                f"`{name}`",
                format_type_md(vtype, out_file, type_index, docs_root),
                init,
                comment,
            )
            for (name, vtype, init, comment) in fields
        ]
        parts.append(f"### {heading}\n")
        parts.append(md_table(["Name", "Type", "Init", "Comment"], rows) + "\n")

    gvl_md = "".join(parts) if parts else "_No variables found._\n"

    sections: dict[str, str] = {
        "SIGNATURE": signature_md,
        "GVL": gvl_md,
    }
    if description_md:
        sections["DESCRIPTION"] = description_md
    return {"title": gvl_name, "sections": sections}
