"""Bidirectional source mapping between Virtual ST lines/offsets and XML CDATA spans."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from ..syntax.span import Position, SourceSpan
from ..xml.types import CdataKind, CdataSpan


@dataclass(slots=True)
class SectionMapping:
    """Mapping between a single virtual ST section and its underlying XML CDATA span."""
    section_index: int
    kind: CdataKind
    label: str
    cdata_span: CdataSpan
    # 1-based line ranges in virtual ST
    virt_start_line: int
    virt_end_line: int
    virt_content_start_line: int  # Line where actual CDATA content begins (after header)
    virt_content_end_line: int    # Line where actual CDATA content ends
    # 1-based line ranges in physical XML document
    xml_content_start_line: int
    xml_content_end_line: int
    # Character offsets
    virt_char_offset: int
    virt_char_length: int

    def contains_virtual_line(self, line: int) -> bool:
        return self.virt_start_line <= line <= self.virt_end_line

    def contains_xml_line(self, line: int) -> bool:
        return self.xml_content_start_line <= line <= self.xml_content_end_line


@dataclass(slots=True)
class SourceMap:
    """Bidirectional position and offset translator between Virtual ST and Raw XML."""
    sections: list[SectionMapping] = field(default_factory=list)

    def find_section_by_virtual_line(self, line: int) -> Optional[SectionMapping]:
        for sec in self.sections:
            if sec.contains_virtual_line(line):
                return sec
        return None

    def find_section_by_xml_line(self, line: int) -> Optional[SectionMapping]:
        for sec in self.sections:
            if sec.contains_xml_line(line):
                return sec
        return None

    def virtual_to_xml_position(self, virt_line: int, virt_col: int) -> tuple[int, int]:
        """Convert a 1-based virtual ST position (line, col) to 1-based physical XML position."""
        sec = self.find_section_by_virtual_line(virt_line)
        if not sec:
            # Fallback 1:1 if outside mapped sections
            return virt_line, virt_col

        # If cursor is in synthetic header lines, map to the XML start line of CDATA
        if virt_line < sec.virt_content_start_line:
            return sec.xml_content_start_line, 1

        line_offset = virt_line - sec.virt_content_start_line
        xml_line = sec.xml_content_start_line + line_offset
        return xml_line, virt_col

    def xml_to_virtual_position(self, xml_line: int, xml_col: int) -> tuple[int, int]:
        """Convert a 1-based physical XML position (line, col) to 1-based virtual ST position."""
        sec = self.find_section_by_xml_line(xml_line)
        if not sec:
            return xml_line, xml_col

        line_offset = xml_line - sec.xml_content_start_line
        virt_line = sec.virt_content_start_line + line_offset
        return virt_line, xml_col

    def map_virtual_to_xml(self, virt_line: int, virt_col: int) -> tuple[int, int]:
        """Alias for virtual_to_xml_position."""
        return self.virtual_to_xml_position(virt_line, virt_col)

    def map_xml_to_virtual(self, xml_line: int, xml_col: int) -> tuple[int, int]:
        """Alias for xml_to_virtual_position."""
        return self.xml_to_virtual_position(xml_line, xml_col)
