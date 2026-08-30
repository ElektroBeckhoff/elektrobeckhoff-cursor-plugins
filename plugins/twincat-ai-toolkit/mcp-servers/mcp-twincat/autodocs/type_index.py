"""Cross-reference type index and Markdown type linking."""
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from autodocs.constants import QUAL
from autodocs.text_utils import clean_return_type, has_hide_attribute, localname
from autodocs.xml_reader import (
    gather_dut_declaration_text,
    gather_gvl_declaration_text,
    gather_itf_declaration_text,
    gather_main_declaration_text,
)

def extract_function_return_type(main_decl: str) -> str:
    """
    Extract the return type from a FUNCTION signature line like:
      FUNCTION [QUAL] MyFunc : USINT // comment
    Not applied to FUNCTION_BLOCK.
    Returns the cleaned return type or ''.
    """
    if not main_decl:
        return ""
    pattern = rf"^\s*FUNCTION{QUAL}\s+\w+(?:\s*:\s*(?P<ret>[^\r\n]+))?"
    m = re.search(pattern, main_decl, flags=re.IGNORECASE | re.MULTILINE)
    if not m or not m.group("ret"):
        return ""
    return clean_return_type(m.group("ret"))
def build_type_index(base_folder: Path) -> dict:
    """
    Scan all .TcPOU, .TcDUT, .TcGVL and .TcIO files under *base_folder* and
    build a mapping from **lowercase** type name to the relative .md path
    (relative to *base_folder*, with .md suffix).  Hidden types
    ({attribute 'hide'}) are excluded.

    The lowercase key enables case-insensitive matching at lookup time, which
    is required because TwinCAT identifiers are case-insensitive.
    """
    from twincat_core.xml.reader import read_tc_xml_file

    index: dict[str, Path] = {}

    for ext in ("*.TcPOU", "*.TcDUT", "*.TcGVL", "*.TcIO"):
        for fpath in base_folder.rglob(ext):
            try:
                doc = read_tc_xml_file(fpath)
                name = doc.root_object_name or fpath.stem
                decl_span = doc.get_declaration_span()
                decl = decl_span.content if decl_span else ""

                if decl and has_hide_attribute(decl):
                    continue

                rel = fpath.relative_to(base_folder)
                index[name.lower()] = rel.with_suffix(".md")
            except Exception:
                continue

    return index


def format_type_md(
    raw_type: str,
    current_md: Path,
    type_index: dict | None,
    docs_root: Path | None,
) -> str:
    """
    Format a type string for Markdown, inserting cross-reference links for
    every identifier that exists in *type_index*.

    Compound types are split so only the known part becomes a link::

        'BOOL'                          → '`BOOL`'
        'FB_IoT_ComClient'              → '[`FB_IoT_ComClient`](<rel_path>)'
        'REFERENCE TO FB_IoT_ComClient' → '`REFERENCE TO` [`FB_IoT_ComClient`](<rel_path>)'
        'ARRAY[1..n] OF ST_Something'   → '`ARRAY[1..n] OF` [`ST_Something`](<rel_path>)'
    """
    if not raw_type:
        return ""
    if not type_index or not docs_root or not current_md:
        return f"`{raw_type}`"

    matches: list[tuple[int, int, str]] = []
    for m in re.finditer(r"\b([A-Za-z_]\w+)\b", raw_type):
        name = m.group(1)
        if name.lower() in type_index:
            matches.append((m.start(), m.end(), name))

    if not matches:
        return f"`{raw_type}`"

    parts: list[str] = []
    last_end = 0
    for start, end, name in matches:
        prefix = raw_type[last_end:start]
        if prefix.strip():
            parts.append(f"`{prefix.strip()}`")

        target_md = docs_root / type_index[name.lower()]
        rel_path = Path(os.path.relpath(target_md, current_md.parent)).as_posix()
        parts.append(f"[`{name}`](<{rel_path}>)")

        last_end = end

    suffix = raw_type[last_end:].strip()
    if suffix:
        parts.append(f"`{suffix}`")

    return " ".join(parts)


# --------------------------------------------------------------------
# Main parsing for POU and DUT + Markdown rendering
# --------------------------------------------------------------------

