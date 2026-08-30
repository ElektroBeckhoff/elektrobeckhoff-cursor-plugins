"""Parse .TcPOU files into documentation sections."""
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
    extract_pou_extends,
    has_hide_attribute,
    localname,
)
from autodocs.type_index import extract_function_return_type, format_type_md
from autodocs.xml_reader import (
    extract_pou_header_comment,
    gather_main_declaration_text,
    gather_method_declarations,
    gather_property_declarations,
)

def parse_tcPou(
    file_path: Path,
    type_index: dict | None = None,
    out_file: Path | None = None,
    docs_root: Path | None = None,
):
    """
    Parse a .TcPOU file and return a structured result or None if the POU is hidden.

    Result shape:
      { "title": <pou_name>, "sections": { KEY: markdown, ... } }
    """
    tree = ET.parse(file_path)
    root = tree.getroot()

    pou_name = file_path.stem
    for el in root.iter():
        if localname(el.tag) == "POU":
            pou_name = el.get("Name") or pou_name
            break

    def collect_sections_from_text(decl_text: str):
        """
        Parse top-level VAR_* interface from the POU's main declaration.
        Returns a dict with keys 'INPUT', 'OUTPUT', 'IN_OUT' mapped to lists of tuples (name, type, init, comment).
        """
        sections = {"INPUT": [], "OUTPUT": [], "IN_OUT": []}
        if not decl_text:
            return sections
        blocks = extract_var_blocks_from_declaration(decl_text)
        for key in ("INPUT", "OUTPUT", "IN_OUT"):
            merged = "\n".join(blocks[key])
            sections[key] = parse_declarations_from_block(merged)
        return sections

    def render_main_sections(sections_dict: dict) -> dict:
        """
        Render POU main interface sections (Inputs/Outputs/InOut) as markdown tables.
        Returns a dict keyed by section key containing markdown strings.
        """
        out = {}
        mapping = [
            ("INPUT", "## Inputs"),
            ("OUTPUT", "## Outputs"),
            ("IN_OUT", "## InOut"),
        ]
        for key, title in mapping:
            rows = [
                (f"`{n}`", format_type_md(t, out_file, type_index, docs_root), init, c)
                for (n, t, init, c) in sections_dict[key]
            ]
            if rows:
                out[key] = (
                    f"{title}\n"
                    + md_table(["Name", "Type", "Init", "Comment"], rows)
                    + "\n"
                )
        return out

    def render_methods(root_el: ET.Element) -> str:
        """
        Render the METHODS section:
        - A concise "Overview" table (Method | Return | Comment | Details),
        where the comment is collapsed into a single informative line.
        - Detailed per-method blocks, each with:
            * Title (### {MethodName})
            * Optional Return line
            * Optional Description section with the full multi-line description
            * Interface tables for Inputs / Outputs / InOut (if present)
        """
        methods = gather_method_declarations(root_el)
        if not methods:
            return ""

        def _mk_anchor(name: str) -> str:
            """Build a GitHub-like anchor for in-page links from a heading."""
            a = name.lower()
            a = re.sub(r"[^\w\s\-]", "", a)
            a = re.sub(r"\s+", "-", a).strip("-")
            return a

        def _one_line(s: str, maxlen: int = 80) -> str:
            """Compress a multi-line description into a single, readable line."""
            s = re.sub(r"\s+", " ", (s or "")).strip()
            return (s[: maxlen - 1] + "…") if (len(s) > maxlen) else s

        parts = ["## Methods\n", "\n### Overview\n"]

        # Build the overview table.
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

        # Render detailed method blocks.
        for m in methods:
            parts.append(f"### {m['name']}\n")
            if m.get("return"):
                ret_md = format_type_md(m["return"], out_file, type_index, docs_root)
                parts.append(f"Return: {ret_md}\n")

            # Render Description only if available.
            desc = (m.get("comment") or "").strip()
            if desc:
                parts.append("\n#### Description\n")
                parts.append(desc + "\n")

            # Extract interface variables from the method declaration.
            m_sections = {"INPUT": [], "OUTPUT": [], "IN_OUT": []}
            if m.get("decl"):
                blocks = extract_var_blocks_from_declaration(m["decl"])
                for key in ("INPUT", "OUTPUT", "IN_OUT"):
                    merged = "\n".join(blocks[key]) if isinstance(blocks[key], list) else ""
                    m_sections[key] = parse_declarations_from_block(merged)

            # Render interface tables where applicable.
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
        """
        Render the PROPERTIES section:
        - A compact overview table (Name | Type | Access), where Access is derived as:
        R/W (both getters and setters), R (getter only), W (setter only), or — (neither).
        """
        props = gather_property_declarations(root_el)
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

    # --- Parse and render POU ---

    main_decl = gather_main_declaration_text(root)
    if main_decl and has_hide_attribute(main_decl):
        return None

    rendered = {}
    src = _source_link_line(file_path, out_file)
    pou_ext_base = extract_pou_extends(main_decl)
    if pou_ext_base:
        base_md = format_type_md(pou_ext_base, out_file, type_index, docs_root)
        rendered["SIGNATURE"] = f"# {pou_name} Extends {base_md}\n" + src
    else:
        rendered["SIGNATURE"] = f"# {pou_name}\n" + src

    # Extract POU header comment (block comment before FUNCTION_BLOCK/FUNCTION/PROGRAM)
    pou_comment = extract_pou_header_comment(main_decl)
    if pou_comment:
        rendered["DESCRIPTION"] = f"## Description\n\n{pou_comment}\n"

    pou_return = extract_function_return_type(main_decl)
    if pou_return:
        ret_md = format_type_md(pou_return, out_file, type_index, docs_root)
        rendered["RETURN"] = f"Return: {ret_md}\n"

    main_sections = collect_sections_from_text(main_decl)
    rendered.update(render_main_sections(main_sections))

    methods_md = render_methods(root)
    if methods_md.strip():
        rendered["METHODS"] = methods_md

    props_md = render_properties(root)
    if props_md.strip():
        rendered["PROPERTIES"] = props_md

    return {"title": pou_name, "sections": rendered}
