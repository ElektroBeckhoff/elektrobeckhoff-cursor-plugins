"""Virtual Structured Text projection and bidirectional XML synchronization."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from ..xml.reader import read_tc_xml, read_tc_xml_file
from ..xml.surgical_patcher import patch_cdata_spans
from ..xml.types import CdataKind, CdataSpan, TcXmlDocument
from .source_map import SectionMapping, SourceMap

RE_SECTION_MARKER = re.compile(
    r"^\s*//\s*===+\s*\[twincat-section:(?P<kind>[^:]+):(?P<name>[^:]*):(?P<idx>\d+)\]\s*===+\s*$",
    re.MULTILINE,
)


def _format_section_label(kind: CdataKind, name: str) -> str:
    """Format human-readable label for a CDATA block."""
    kind_labels = {
        CdataKind.POU_DECLARATION: f"Declaration: {name}",
        CdataKind.POU_IMPLEMENTATION: f"Implementation: {name}",
        CdataKind.METHOD_DECLARATION: f"Method Declaration: {name}",
        CdataKind.METHOD_IMPLEMENTATION: f"Method Implementation: {name}",
        CdataKind.ACTION_IMPLEMENTATION: f"Action: {name}",
        CdataKind.PROPERTY_DECLARATION: f"Property Declaration: {name}",
        CdataKind.PROPERTY_GET_DECLARATION: f"Property Get Declaration: {name}",
        CdataKind.PROPERTY_GET_IMPLEMENTATION: f"Property Get Implementation: {name}",
        CdataKind.PROPERTY_SET_DECLARATION: f"Property Set Declaration: {name}",
        CdataKind.PROPERTY_SET_IMPLEMENTATION: f"Property Set Implementation: {name}",
        CdataKind.DUT_DECLARATION: f"DUT: {name}",
        CdataKind.GVL_DECLARATION: f"GVL: {name}",
        CdataKind.ITF_DECLARATION: f"Interface: {name}",
    }
    return kind_labels.get(kind, f"Section: {name} ({kind.value})")


@dataclass
class VirtualStDocument:
    """A projected Virtual Structured Text view of a TwinCAT XML document."""
    xml_doc: TcXmlDocument
    virtual_st: str
    source_map: SourceMap

    @classmethod
    def from_xml_document(cls, doc: TcXmlDocument) -> "VirtualStDocument":
        """Project a TcXmlDocument into a single continuous Virtual ST document."""
        sections: list[SectionMapping] = []
        st_lines: list[str] = []
        current_virt_line = 1
        current_virt_offset = 0

        # Calculate XML line offsets for accurate mapping
        xml_lines = doc.raw_text.splitlines(keepends=True)

        def get_xml_line_num(char_offset: int) -> int:
            cnt = 0
            for idx, l in enumerate(xml_lines, start=1):
                cnt += len(l)
                if char_offset < cnt:
                    return idx
            return max(1, len(xml_lines))

        # Single CDATA document (e.g. DUT, GVL, or single ITF)
        if len(doc.cdata_spans) == 1:
            span = doc.cdata_spans[0]
            content = span.content
            xml_start_line = get_xml_line_num(span.content_start)
            xml_end_line = get_xml_line_num(span.content_end)
            num_content_lines = len(content.splitlines()) or 1

            sec_map = SectionMapping(
                section_index=0,
                kind=span.kind,
                label=_format_section_label(span.kind, doc.root_object_name),
                cdata_span=span,
                virt_start_line=1,
                virt_end_line=num_content_lines,
                virt_content_start_line=1,
                virt_content_end_line=num_content_lines,
                xml_content_start_line=xml_start_line,
                xml_content_end_line=xml_end_line,
                virt_char_offset=0,
                virt_char_length=len(content),
            )
            return cls(
                xml_doc=doc,
                virtual_st=content,
                source_map=SourceMap(sections=[sec_map]),
            )

        # Multi-section document (e.g. POU with Methods, Actions, Properties)
        for idx, span in enumerate(doc.cdata_spans):
            name = span.parent_name or doc.root_object_name
            label = _format_section_label(span.kind, name)

            marker = f"// === [twincat-section:{span.kind.value}:{name}:{idx}] ==="
            comment_header = f"{marker}\n// {label}"

            header_lines_count = len(comment_header.splitlines())
            xml_start_line = get_xml_line_num(span.content_start)
            xml_end_line = get_xml_line_num(span.content_end)

            content = span.content.rstrip("\r\n")
            content_lines = content.splitlines() if content else [""]
            num_content_lines = len(content_lines)

            sec_start_line = current_virt_line
            content_start_line = current_virt_line + header_lines_count
            sec_end_line = content_start_line + num_content_lines - 1

            section_text = f"{comment_header}\n{content}\n\n"

            sec_map = SectionMapping(
                section_index=idx,
                kind=span.kind,
                label=label,
                cdata_span=span,
                virt_start_line=sec_start_line,
                virt_end_line=sec_end_line,
                virt_content_start_line=content_start_line,
                virt_content_end_line=sec_end_line,
                xml_content_start_line=xml_start_line,
                xml_content_end_line=xml_end_line,
                virt_char_offset=current_virt_offset,
                virt_char_length=len(section_text),
            )
            sections.append(sec_map)

            st_lines.append(section_text)
            current_virt_line = sec_end_line + 2  # accounted for trailing newlines
            current_virt_offset += len(section_text)

        full_virtual_st = "".join(st_lines)
        return cls(
            xml_doc=doc,
            virtual_st=full_virtual_st,
            source_map=SourceMap(sections=sections),
        )

    @classmethod
    def from_file(cls, file_path: Path | str) -> "VirtualStDocument":
        """Load a TwinCAT XML file from disk and create VirtualStDocument."""
        p = Path(file_path).resolve()
        doc = read_tc_xml_file(p)
        return cls.from_xml_document(doc)

    def apply_virtual_st_changes(self, new_virtual_st: str) -> str:
        """Apply changes made in Virtual ST back into the raw XML document losslessly."""
        if len(self.xml_doc.cdata_spans) <= 1:
            # Single CDATA: full virtual ST is the CDATA content
            if not self.xml_doc.cdata_spans:
                return self.xml_doc.raw_text
            span = self.xml_doc.cdata_spans[0]
            clean_content = new_virtual_st.rstrip("\r\n") + "\n"
            return patch_cdata_spans(self.xml_doc, [(span, clean_content)])

        # Multi-section parsing by marker
        matches = list(RE_SECTION_MARKER.finditer(new_virtual_st))
        if not matches:
            # No section markers found: fallback to keeping original XML if untracked
            return self.xml_doc.raw_text

        patches: list[Tuple[CdataSpan, str]] = []

        for i, match in enumerate(matches):
            idx = int(match.group("idx"))
            if idx >= len(self.xml_doc.cdata_spans):
                continue
            span = self.xml_doc.cdata_spans[idx]

            # Content starts after section comment header
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(new_virtual_st)

            raw_section_block = new_virtual_st[start_pos:end_pos]
            lines = raw_section_block.splitlines(keepends=True)

            # Filter out synthetic leading comments (e.g. "// Declaration: FB_Motor")
            clean_lines = []
            skipped_header = False
            for l in lines:
                if not skipped_header and l.strip().startswith("//"):
                    skipped_header = True
                    continue
                clean_lines.append(l)

            section_content = "".join(clean_lines).strip("\r\n")
            if section_content:
                section_content += "\n"

            patches.append((span, section_content))

        return patch_cdata_spans(self.xml_doc, patches)


def project_to_virtual_st(xml_text: str, file_path: Optional[Path] = None) -> VirtualStDocument:
    """Project raw XML string into a VirtualStDocument."""
    doc = read_tc_xml(xml_text, file_path=file_path)
    return VirtualStDocument.from_xml_document(doc)


def sync_virtual_st_to_xml(xml_text: str, new_virtual_st: str, file_path: Optional[Path] = None) -> str:
    """Update original XML text with edited Virtual ST content."""
    doc = read_tc_xml(xml_text, file_path=file_path)
    vdoc = VirtualStDocument.from_xml_document(doc)
    return vdoc.apply_virtual_st_changes(new_virtual_st)
