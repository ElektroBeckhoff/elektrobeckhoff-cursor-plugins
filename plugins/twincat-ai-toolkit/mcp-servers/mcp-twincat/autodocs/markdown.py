"""Markdown rendering, section markers, and TOC generation."""
import re
from pathlib import Path

from autodocs.constants import SECTION_ORDER

def _md_escape_cell(s: str) -> str:
    """
    Escape markdown table cell content (currently escapes vertical bars).
    """
    s = "" if s is None else str(s)
    return s.replace("|", r"\|")


def md_table(headers, rows):
    """
    Render a GitHub-compatible markdown table with fixed-width columns.
    - headers: list[str]
    - rows: list[list[str]]
    """
    headers = [_md_escape_cell(h).replace("\t", " ") for h in headers]
    rows = [[_md_escape_cell(c).replace("\t", " ") for c in row] for row in rows]

    widths = []
    for i in range(len(headers)):
        col_vals = [len(row[i]) for row in rows] if rows else []
        widths.append(max(len(headers[i]), max(col_vals) if col_vals else 0))

    header_line = (
        "| "
        + " | ".join(headers[i].ljust(widths[i]) for i in range(len(headers)))
        + " |"
    )
    separator = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    data_lines = [
        "| "
        + " | ".join(rows[r][i].ljust(widths[i]) for i in range(len(headers)))
        + " |"
        for r in range(len(rows))
    ]
    return "\n".join([header_line, separator] + data_lines)
def write_readme_and_toc(
    output_root: Path,
    docs_root: Path,
    created_files,
    timestamp: str,
    *,
    include_toc_timestamp: bool = False,
):
    """
    Create/update:
      - <output_root>/README.md -> TOC block contains only a link to docs/toc.md
      - <docs_root>/toc.md      -> TOC block contains a full index of all .md files under docs/

    Only the <!-- TOC --> ... <!-- END_TOC --> block is replaced or created in both files.
    Directory items in toc.md are clickable and shown in bold. File bullets show the stem (no .md suffix).
    """

    def _gen_marker() -> str:
        if include_toc_timestamp:
            return f"_Automatically generated on {timestamp}_"
        return "_Automatically generated_"

    def build_full_docs_toc_lines():
        if not docs_root.exists():
            return [
                "# Table of Contents",
                "",
                _gen_marker(),
                "",
                "*(docs folder not found)*",
            ]

        all_md = sorted(
            (p for p in docs_root.rglob("*.md") if p.name.lower() != "toc.md"),
            key=lambda p: p.as_posix().lower(),
        )

        if not all_md:
            return [
                "# Table of Contents",
                "",
                _gen_marker(),
                "",
                "*(No files in docs yet)*",
            ]

        lines = [
            "# Table of Contents",
            "",
            _gen_marker(),
            "",
        ]

        seen_dirs = set()
        for abs_path in all_md:
            rel = abs_path.relative_to(docs_root)
            parts = rel.parts
            # Emit clickable directory bullets (unique, hierarchical)
            for d in range(len(parts) - 1):
                dir_key = "/".join(parts[: d + 1])
                if dir_key not in seen_dirs:
                    indent = "  " * d
                    url = "/".join(parts[: d + 1])
                    lines.append(f"{indent}- [**{parts[d]}**](<{url}>)")
                    seen_dirs.add(dir_key)
            # File bullet with stem (no .md)
            indent = "  " * (len(parts) - 1)
            url = rel.as_posix()
            lines.append(f"{indent}- [{rel.stem}](<{url}>)")
        return lines

    def build_readme_toc_lines():
        return [
            "# Table of Contents",
            "",
            _gen_marker(),
            "",
            "[Table of Contents](<docs/toc.md>)",
        ]

    # docs/toc.md
    docs_toc_path = docs_root / "toc.md"
    toc_lines_full = build_full_docs_toc_lines()
    toc_md_full = "\n".join(toc_lines_full) + "\n"
    toc_block_full = make_marked_block("TOC", toc_md_full)

    if docs_toc_path.exists():
        existing = docs_toc_path.read_text(encoding="utf-8")
        updated, _, _ = replace_or_append_block(existing, "TOC", toc_block_full)
        docs_toc_path.write_text(updated, encoding="utf-8")
    else:
        docs_toc_path.parent.mkdir(parents=True, exist_ok=True)
        docs_toc_path.write_text(toc_block_full + "\n", encoding="utf-8")

    # README.md
    readme_path = output_root / "README.md"
    toc_lines_readme = build_readme_toc_lines()
    readme_toc_md = "\n".join(toc_lines_readme) + "\n"
    readme_toc_block = make_marked_block("TOC", readme_toc_md)

    if readme_path.exists():
        existing = readme_path.read_text(encoding="utf-8")
        updated, _, _ = replace_or_append_block(existing, "TOC", readme_toc_block)
        readme_path.write_text(updated, encoding="utf-8")
    else:
        readme_path.write_text(readme_toc_block + "\n", encoding="utf-8")


def make_marked_block(section_key: str, inner_md: str) -> str:
    """
    Wrap a section's markdown with HTML comment markers so it can be replaced later:
      <!-- KEY -->
      <!-- WARNING: DO NOT EDIT CONTENT BETWEEN SECTION MARKERS - AUTO-GENERATED -->
      ... inner_md ...
      <!-- END_KEY -->
    """
    warning = "<!-- WARNING: DO NOT EDIT CONTENT BETWEEN SECTION MARKERS - AUTO-GENERATED -->"
    return f"<!-- {section_key} -->\n{warning}\n{inner_md.rstrip()}\n<!-- END_{section_key} -->"


def replace_or_append_block(
    existing_text: str, section_key: str, new_block: str
) -> (str, bool, bool):
    """
    Replace the marked block <!-- KEY --> ... <!-- END_KEY --> if present.
    If not present, append the block at the end.

    Returns:
      (updated_text, replaced, appended)
    """
    pattern = rf"<!--\s*{section_key}\s*-->.*?<!--\s*END_{section_key}\s*-->"
    if re.search(pattern, existing_text, flags=re.DOTALL | re.IGNORECASE):
        updated = re.sub(
            pattern, new_block, existing_text, flags=re.DOTALL | re.IGNORECASE
        )
        return updated, True, False
    else:
        sep = "" if existing_text.endswith("\n") else "\n"
        updated = existing_text + f"{sep}\n\n{new_block}\n"
        return updated, False, True


def _reorder_sections(text: str) -> str:
    """
    Reorder marked sections in *text* to match SECTION_ORDER.

    User-added content between sections is kept with the **preceding** block
    so it travels along when that block moves.  Content before the first
    block (preamble) and after the last block (epilogue) stays in place.
    """
    _BLOCK_RE = re.compile(
        r"(<!--\s*(\w+)\s*-->.*?<!--\s*END_\2\s*-->)",
        flags=re.DOTALL | re.IGNORECASE,
    )
    matches = list(_BLOCK_RE.finditer(text))
    if len(matches) < 2:
        return text

    order_map = {k: i for i, k in enumerate(SECTION_ORDER)}

    preamble = text[: matches[0].start()]
    epilogue = text[matches[-1].end() :]

    # Each entry: (section_key, block_text, trailing_gap)
    entries = []
    for idx, m in enumerate(matches):
        key = m.group(2).upper()
        block_text = m.group(1)
        gap_start = m.end()
        gap_end = matches[idx + 1].start() if idx + 1 < len(matches) else m.end()
        gap = text[gap_start:gap_end]
        entries.append((key, block_text, gap))

    current_keys = [e[0] for e in entries]
    sorted_keys = sorted(current_keys, key=lambda k: order_map.get(k, 999))
    if current_keys == sorted_keys:
        return text

    keyed = {e[0]: e for e in entries}
    parts = [preamble]
    for i, key in enumerate(sorted_keys):
        _, block_text, gap = keyed[key]
        parts.append(block_text)
        if i < len(sorted_keys) - 1:
            parts.append(gap if gap.strip() else "\n\n")
    parts.append(epilogue)
    return "".join(parts)


def write_or_update_markdown(
    out_file: Path, title: str, sections: dict
) -> (bool, list, list):
    """
    Create or update a .md file:

    - If the file does not exist:
        * Write a header '# <title>' (only if no SIGNATURE section is present)
        * Write all non-empty sections, each wrapped in markers.

    - If the file exists:
        * For each provided section, replace the existing marked block or append it.

    Returns:
      (created_new: bool, replaced_keys: list[str], appended_keys: list[str])
    """
    blocks = {k: v for k, v in sections.items() if v and v.strip()}

    if not out_file.exists():
        parts = []
        if "SIGNATURE" not in blocks:
            parts.append(f"# {title}\n")
        for key in SECTION_ORDER:
            if key in blocks:
                parts.append(make_marked_block(key, blocks[key]))
                parts.append("")
        out_file.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return True, list(blocks.keys()), []

    text = out_file.read_text(encoding="utf-8")

    # If SIGNATURE is provided, remove the top '# <title>' header (it will be rendered in the section)
    if "SIGNATURE" in blocks:
        text = re.sub(rf"^\s*#\s+{re.escape(title)}\s*\n+", "", text, count=1)

    replaced, appended = [], []
    for key in SECTION_ORDER:
        if key not in blocks:
            continue
        new_block = make_marked_block(key, blocks[key])
        text, was_replaced, was_appended = replace_or_append_block(text, key, new_block)
        if was_replaced:
            replaced.append(key)
        if was_appended:
            appended.append(key)

    text = _reorder_sections(text)
    out_file.write_text(text, encoding="utf-8")
    return False, replaced, appended


# --------------------------------------------------------------------
# VAR_* block extraction and parsing
# --------------------------------------------------------------------


