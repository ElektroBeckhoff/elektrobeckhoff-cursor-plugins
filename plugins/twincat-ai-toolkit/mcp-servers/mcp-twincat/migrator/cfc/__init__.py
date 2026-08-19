"""TwinCAT CFC to ST migration."""
from __future__ import annotations

from migrator.cfc.mapper import (
    inject_exec_order_comments,
    map_cfc_to_ir,
    _map_function_block,
    _map_output_element,
    _resolve_expression,
)
from migrator.cfc.parser import parse_cfc_graph
from migrator.cfc.pipeline import CFC_SOURCE_TYPE, CFC_TOOL_NAME, main, process_file
from migrator.cfc.types import CFCConnection, CFCElement, CFCGraph, PinInfo
from migrator.cfc.xml_patch import write_cfc_st_to_xml

__all__ = [
    "CFC_SOURCE_TYPE",
    "CFC_TOOL_NAME",
    "main",
    "process_file",
    "parse_cfc_graph",
    "map_cfc_to_ir",
    "inject_exec_order_comments",
    "write_cfc_st_to_xml",
    "CFCConnection",
    "CFCElement",
    "CFCGraph",
    "PinInfo",
    "_resolve_expression",
    "_map_function_block",
    "_map_output_element",
]
