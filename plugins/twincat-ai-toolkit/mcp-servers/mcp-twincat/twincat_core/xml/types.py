"""Core data types for lossless TwinCAT XML handling."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Sequence, Tuple


class CdataKind(str, Enum):
    """Categorization of CDATA blocks in TwinCAT files."""
    POU_DECLARATION = "pou_declaration"
    POU_IMPLEMENTATION = "pou_implementation"
    METHOD_DECLARATION = "method_declaration"
    METHOD_IMPLEMENTATION = "method_implementation"
    PROPERTY_DECLARATION = "property_declaration"
    PROPERTY_GET_DECLARATION = "property_get_declaration"
    PROPERTY_GET_IMPLEMENTATION = "property_get_implementation"
    PROPERTY_SET_DECLARATION = "property_set_declaration"
    PROPERTY_SET_IMPLEMENTATION = "property_set_implementation"
    ACTION_IMPLEMENTATION = "action_implementation"
    DUT_DECLARATION = "dut_declaration"
    GVL_DECLARATION = "gvl_declaration"
    ITF_DECLARATION = "itf_declaration"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CdataSpan:
    """Exact character boundary and context for a CDATA block in raw XML."""
    kind: CdataKind
    parent_tag: str
    parent_name: str = ""
    parent_id: Optional[str] = None
    tag_path: Tuple[str, ...] = ()
    cdata_raw_start: int = 0
    cdata_raw_end: int = 0
    content_start: int = 0
    content_end: int = 0
    content: str = ""

    @property
    def raw_length(self) -> int:
        """Length of full <![CDATA[...]]> tag."""
        return self.cdata_raw_end - self.cdata_raw_start

    @property
    def content_length(self) -> int:
        """Length of inner content."""
        return self.content_end - self.content_start

    @property
    def is_declaration(self) -> bool:
        """Whether this CDATA span contains a declaration block."""
        return self.kind in (
            CdataKind.POU_DECLARATION,
            CdataKind.DUT_DECLARATION,
            CdataKind.GVL_DECLARATION,
            CdataKind.ITF_DECLARATION,
            CdataKind.METHOD_DECLARATION,
            CdataKind.PROPERTY_DECLARATION,
            CdataKind.PROPERTY_GET_DECLARATION,
            CdataKind.PROPERTY_SET_DECLARATION,
        )

    @property
    def is_implementation(self) -> bool:
        """Whether this CDATA span contains an implementation body."""
        return self.kind in (
            CdataKind.POU_IMPLEMENTATION,
            CdataKind.METHOD_IMPLEMENTATION,
            CdataKind.ACTION_IMPLEMENTATION,
            CdataKind.PROPERTY_GET_IMPLEMENTATION,
            CdataKind.PROPERTY_SET_IMPLEMENTATION,
        )


@dataclass
class XmlEncodingInfo:
    """Metadata describing file encoding and format characteristics."""
    encoding: str = "utf-8"
    has_bom: bool = False
    line_ending: str = "\r\n"
    xml_declaration: str = '<?xml version="1.0" encoding="utf-8"?>'


@dataclass
class TcXmlDocument:
    """Lossless representation of a TwinCAT XML file."""
    raw_text: str
    encoding_info: XmlEncodingInfo = field(default_factory=XmlEncodingInfo)
    file_path: Optional[Path] = None
    cdata_spans: list[CdataSpan] = field(default_factory=list)
    root_object_type: str = ""
    root_object_name: str = ""
    root_object_id: Optional[str] = None
    product_version: Optional[str] = None
    version: Optional[str] = None

    def get_declaration_span(self) -> Optional[CdataSpan]:
        """Return the primary declaration CDATA span for the root object."""
        for span in self.cdata_spans:
            if span.kind in (
                CdataKind.POU_DECLARATION,
                CdataKind.DUT_DECLARATION,
                CdataKind.GVL_DECLARATION,
                CdataKind.ITF_DECLARATION,
            ):
                return span
        return None

    def get_implementation_span(self) -> Optional[CdataSpan]:
        """Return the primary body implementation CDATA span for a POU."""
        for span in self.cdata_spans:
            if span.kind == CdataKind.POU_IMPLEMENTATION:
                return span
        return None

    def get_method_spans(self, name: Optional[str] = None) -> list[CdataSpan]:
        """Return all CDATA spans belonging to methods (optionally filtered by method name)."""
        res: list[CdataSpan] = []
        for span in self.cdata_spans:
            if span.kind in (CdataKind.METHOD_DECLARATION, CdataKind.METHOD_IMPLEMENTATION):
                if name is None or span.parent_name.casefold() == name.casefold():
                    res.append(span)
        return res

    def get_action_spans(self, name: Optional[str] = None) -> list[CdataSpan]:
        """Return all CDATA spans belonging to actions (optionally filtered by action name)."""
        res: list[CdataSpan] = []
        for span in self.cdata_spans:
            if span.kind == CdataKind.ACTION_IMPLEMENTATION:
                if name is None or span.parent_name.casefold() == name.casefold():
                    res.append(span)
        return res

    def get_property_spans(self, name: Optional[str] = None) -> list[CdataSpan]:
        """Return all CDATA spans belonging to properties (optionally filtered by property name)."""
        res: list[CdataSpan] = []
        for span in self.cdata_spans:
            if span.kind in (
                CdataKind.PROPERTY_DECLARATION,
                CdataKind.PROPERTY_GET_DECLARATION,
                CdataKind.PROPERTY_GET_IMPLEMENTATION,
                CdataKind.PROPERTY_SET_DECLARATION,
                CdataKind.PROPERTY_SET_IMPLEMENTATION,
            ):
                if name is None or span.parent_name.casefold() == name.casefold():
                    res.append(span)
        return res
