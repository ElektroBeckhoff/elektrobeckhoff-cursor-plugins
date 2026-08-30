"""TwinCAT Lossless XML & Document Engine."""
from .guid_manager import (
    extract_all_guids,
    find_duplicate_guids,
    generate_guid,
    is_fake_ai_guid,
    is_valid_guid,
    normalize_guid,
    regenerate_all_guids,
)
from .reader import (
    read_tc_xml,
    read_tc_xml_file,
    scan_cdata_spans,
)
from .safe_io import (
    WriteSummary,
    detect_encoding_info,
    encode_document,
    read_file_lossless,
    save_document_lossless,
    write_file_safe,
)
from .serializer import (
    CDATA_MARKER,
    XML_ATTRIBUTE_ORDER,
    serialize_twincat_xml,
)
from .surgical_patcher import (
    patch_action,
    patch_by_filter,
    patch_cdata_span,
    patch_cdata_spans,
    patch_declaration,
    patch_implementation,
    patch_method,
)
from .types import (
    CdataKind,
    CdataSpan,
    TcXmlDocument,
    XmlEncodingInfo,
)

__all__ = [
    "CdataKind",
    "CdataSpan",
    "TcXmlDocument",
    "XmlEncodingInfo",
    "WriteSummary",
    "CDATA_MARKER",
    "XML_ATTRIBUTE_ORDER",
    "read_tc_xml",
    "read_tc_xml_file",
    "scan_cdata_spans",
    "patch_cdata_span",
    "patch_cdata_spans",
    "patch_by_filter",
    "patch_declaration",
    "patch_implementation",
    "patch_method",
    "patch_action",
    "serialize_twincat_xml",
    "is_valid_guid",
    "is_fake_ai_guid",
    "normalize_guid",
    "generate_guid",
    "extract_all_guids",
    "find_duplicate_guids",
    "detect_encoding_info",
    "encode_document",
    "read_file_lossless",
    "write_file_safe",
    "save_document_lossless",
]
