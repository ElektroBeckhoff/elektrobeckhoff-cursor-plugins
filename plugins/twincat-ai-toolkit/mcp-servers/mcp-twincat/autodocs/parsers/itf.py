"""Parse .TcIO interface files into documentation sections."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from autodocs.declaration_parser import (
    extract_var_blocks_from_declaration,
    parse_declarations_from_block,
)
from autodocs.markdown import md_table
from autodocs.text_utils import (
    _source_link_line,
    extract_itf_extends,
    has_hide_attribute,
    localname,
)
from autodocs.type_index import format_type_md
from autodocs.xml_reader import (
    extract_itf_header_comment,
    gather_itf_declaration_text,
    gather_method_declarations,
    gather_property_declarations,
)

def parse_tcItf(
    file_path: Path,
    type_index: dict | None = None,
    out_file: Path | None = None,
    docs_root: Path | None = None,
):
    """
    Parse a .TcIO file (TwinCAT Interface) and return a structured result or
    None if the interface is hidden.

    Result shape:
      { "title": <itf_name>, "sections": { KEY: markdown, ... } }
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    itf_name = file_path.stem
    for el in root.iter():
        if localname(el.tag) == "Itf":
            itf_name = el.get("Name") or itf_name
            break

    def render_methods(root_el: ET.Element) -> str:
        """Render METHODS section for an interface (identical layout to POU methods)."""
        methods = gather_method_declarations(root_el, parent_tag="Itf")
        if not methods:
            return ""

        def _mk_anchor(name: str) -> str:
            a = name.lower()
            a = re.sub(r"[^\w\s\-]", "", a)
            a = re.sub(r"\s+", "-", a).strip("-")
            return a

        def _one_line(s: str, maxlen: int = 80) -> str:
            s = re.sub(r"\s+", " ", (s or "")).strip()
            return (s[: maxlen - 1] + "…") if (len(s) > maxlen) else s

        parts = ["## Methods\n", "\n### Overview\n"]

        summary_rows = []
        for m in methods:
            ret = m.get("return", "")
            anchor = _mk_anchor(m.get("name", ""))
            comment_one_line = _one_line(m.get("comment") or "")
            ret_md = format_type_md(ret, out_file, type_index, docs_root) if ret else ""
            summary_rows.append(
                (m["name"], ret_md, comment_one_line, f"[↗](#{anchor})")
            )
        parts.append(md_table(["Method", "Return", "Comment", "Details"], summary_rows) + "\n")

        for m in methods:
            parts.append(f"### {m['name']}\n")
            if m.get("return"):
                ret_md = format_type_md(m["return"], out_file, type_index, docs_root)
                parts.append(f"Return: {ret_md}\n")

            desc = (m.get("comment") or "").strip()
            if desc:
                parts.append("\n#### Description\n")
                parts.append(desc + "\n")

            m_sections = {"INPUT": [], "OUTPUT": [], "IN_OUT": []}
            if m.get("decl"):
                blocks = extract_var_blocks_from_declaration(m["decl"])
                for key in ("INPUT", "OUTPUT", "IN_OUT"):
                    merged = "\n".join(blocks[key]) if isinstance(blocks[key], list) else ""
                    m_sections[key] = parse_declarations_from_block(merged)

            sub = []
            if m_sections["INPUT"]:
                rows = [(f"`{n}`", format_type_md(t, out_file, type_index, docs_root), init, c) for (n, t, init, c) in m_sections["INPUT"]]
                sub.append("#### Inputs\n" + md_table(["Name", "Type", "Init", "Comment"], rows) + "\n")
            if m_sections["OUTPUT"]:
                rows = [(f"`{n}`", format_type_md(t, out_file, type_index, docs_root), init, c) for (n, t, init, c) in m_sections["OUTPUT"]]
                sub.append("#### Outputs\n" + md_table(["Name", "Type", "Init", "Comment"], rows) + "\n")
            if m_sections["IN_OUT"]:
                rows = [(f"`{n}`", format_type_md(t, out_file, type_index, docs_root), init, c) for (n, t, init, c) in m_sections["IN_OUT"]]
                sub.append("#### InOut\n" + md_table(["Name", "Type", "Init", "Comment"], rows) + "\n")

            parts.extend(sub if sub else ["_No interface variables for this method._\n"])

        return "".join(parts)

    def render_properties(root_el: ET.Element) -> str:
        """Render PROPERTIES section for an interface."""
        props = gather_property_declarations(root_el, parent_tag="Itf")
        if not props:
            return ""
        parts = ["## Properties\n\n### Overview\n"]

        def _acc(p) -> str:
            g, s = p.get("has_get"), p.get("has_set")
            if g and s:
                return "R/W"
            if g and not s:
                return "R"
            if s and not g:
                return "W"
            return "—"

        rows = []
        for p in props:
            ptype = p.get("type", "")
            ptype_md = format_type_md(ptype, out_file, type_index, docs_root) if ptype else ""
            rows.append((p["name"], ptype_md, _acc(p)))

        parts.append(md_table(["Name", "Type", "Access"], rows) + "\n")
        return "".join(parts)

    # --- Parse and render Interface ---

    main_decl = gather_itf_declaration_text(root)
    if main_decl and has_hide_attribute(main_decl):
        return None

    rendered = {}
    src = _source_link_line(file_path, out_file)
    itf_ext_base = extract_itf_extends(main_decl)
    if itf_ext_base:
        base_md = format_type_md(itf_ext_base, out_file, type_index, docs_root)
        rendered["SIGNATURE"] = f"# {itf_name} Extends {base_md}\n" + src
    else:
        rendered["SIGNATURE"] = f"# {itf_name}\n" + src

    itf_comment = extract_itf_header_comment(main_decl)
    if itf_comment:
        rendered["DESCRIPTION"] = f"## Description\n\n{itf_comment}\n"

    props_md = render_properties(root)
    if props_md.strip():
        rendered["PROPERTIES"] = props_md

    methods_md = render_methods(root)
    if methods_md.strip():
        rendered["METHODS"] = methods_md

    return {"title": itf_name, "sections": rendered}
