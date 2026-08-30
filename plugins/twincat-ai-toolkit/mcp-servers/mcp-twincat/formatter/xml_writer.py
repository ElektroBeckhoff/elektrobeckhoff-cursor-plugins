"""XML Writer with CDATA preservation (re-exports twincat_core.xml.serializer)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

from twincat_core.xml.serializer import (
    CDATA_MARKER,
    XML_ATTRIBUTE_ORDER,
    XML_INDENT_SIZE_DEFAULT,
    _escape,
    _format_attributes,
    _local_tag,
    _serialize_element,
    serialize_twincat_xml,
)

__all__ = [
    "CDATA_MARKER",
    "XML_INDENT_SIZE_DEFAULT",
    "XML_ATTRIBUTE_ORDER",
    "serialize_twincat_xml",
]
