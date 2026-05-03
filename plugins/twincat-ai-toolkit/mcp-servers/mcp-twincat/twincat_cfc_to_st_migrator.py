#!/usr/bin/env python3
"""
TwinCAT 3 CFC (Continuous Function Chart) to Structured Text (ST) Migration Tool.

Reads .TcPOU files containing CFC implementations and converts them to
functionally equivalent ST code while preserving declarations, attributes,
IDs and project structure.

Usage:
    python twincat_cfc_to_st_migrator.py --input "path/to/File.TcPOU"
    python twincat_cfc_to_st_migrator.py --input "path/to/project" --recursive
    python twincat_cfc_to_st_migrator.py --input "File.TcPOU" --dry-run
    python twincat_cfc_to_st_migrator.py --input "File.TcPOU" --analyze-only
"""

from __future__ import annotations

import datetime
import logging
import re
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from twincat_migrator_base import (
    AssignNode,
    BoxNode,
    MigrationConfig,
    MigrationLogger,
    MigrationReport,
    NwlNetwork,
    OperandNode,
    SCRIPT_VERSION,
    SUPPORTED_EXTENSIONS,
    TcFile,
    _detect_impl_type,
    _get_v_str,
    _print_analysis,
    _print_dry_run,
    _regenerate_guids,
    _resolve_output_path,
    _strip_quotes,
    build_generated_header, calculate_accuracy,
    can_replace,
    collect_input_files,
    convert_networks_to_st,
    create_backup,
    load_config,
    load_file,
    parse_arguments,
    validate_generated_st,
    write_output_file,
)

# ---------------------------------------------------------------------------
# CFC data model
# ---------------------------------------------------------------------------

@dataclass
class PinInfo:
    pin_id: int = 0
    owner_id: int = 0
    pin_type: str = ""          # "input" | "output" | "inout"
    name: str = ""
    negated: bool = False
    set_reset: str = "None"     # "None" | "Set" | "Reset"
    index: int = 0


@dataclass
class CFCElement:
    element_id: int = 0
    element_type: str = ""      # "input" | "output" | "box" | "connection"
    var_name: str = ""
    kind_of_call: str = ""      # "Operator" | "FunctionBlock"
    box_type: str = ""
    instance_name: str = ""
    input_pins: List[PinInfo] = field(default_factory=list)
    output_pins: List[PinInfo] = field(default_factory=list)
    inout_pins: List[PinInfo] = field(default_factory=list)
    en_eno: bool = False
    texts: List[str] = field(default_factory=list)
    bounds: str = ""


@dataclass
class CFCConnection:
    source_pin_id: int = 0
    dest_pin_id: int = 0


@dataclass
class CFCGraph:
    elements: Dict[int, CFCElement] = field(default_factory=dict)
    pins: Dict[int, PinInfo] = field(default_factory=dict)
    connections: List[CFCConnection] = field(default_factory=list)
    edges: Dict[int, int] = field(default_factory=dict)
    reverse_edges: Dict[int, List[int]] = field(default_factory=dict)
    execution_order: List[CFCElement] = field(default_factory=list)


CFC_SOURCE_TYPE = "CFC"
CFC_TOOL_NAME = "twincat_cfc_to_st_migrator"


# ---------------------------------------------------------------------------
# CFC Parser
# ---------------------------------------------------------------------------

def parse_cfc_graph(tc: TcFile) -> Optional[CFCGraph]:
    """Parse CFC XmlArchive into a pin-ID-indexed graph."""
    pou = tc.xml_root.find("POU")
    if pou is None:
        return None
    impl = pou.find("Implementation")
    if impl is None:
        return None
    cfc = impl.find("CFC")
    if cfc is None:
        return None

    archive = cfc.find("XmlArchive")
    if archive is None:
        return None
    data = archive.find("Data")
    if data is None:
        return None

    cfc_obj = None
    for o in data.findall("o"):
        if o.get("t") == "CFCImplementationObject":
            cfc_obj = o
            break
    if cfc_obj is None:
        return None

    items_el = None
    for child in cfc_obj:
        if child.get("n") == "Items" and child.get("t") == "CFCItemList":
            items_el = child
            break
    if items_el is None:
        return None

    inner_list = None
    for l2 in items_el.findall("l2"):
        if l2.get("n") == "InnerList":
            inner_list = l2
            break
    if inner_list is None:
        return None

    graph = CFCGraph()
    _scan_elements(inner_list, graph, tc)
    _scan_connections(inner_list, graph)
    _assign_texts(graph)
    _extract_execution_order(inner_list, graph)
    return graph


def _scan_elements(inner_list, graph: CFCGraph, tc: TcFile) -> None:
    """Phase 1: Scan all elements and their pins."""
    for item in inner_list:
        if item.tag != "o":
            continue
        t_attr = item.get("t", "")

        if t_attr == "CFCInputElement":
            elem = _parse_input_element(item)
            graph.elements[elem.element_id] = elem
            for pin in elem.output_pins:
                pin.owner_id = elem.element_id
                graph.pins[pin.pin_id] = pin

        elif t_attr == "CFCOutputElement":
            elem = _parse_output_element(item)
            graph.elements[elem.element_id] = elem
            for pin in elem.input_pins:
                pin.owner_id = elem.element_id
                graph.pins[pin.pin_id] = pin

        elif t_attr == "CFCBoxElement":
            elem = _parse_box_element(item)
            graph.elements[elem.element_id] = elem
            for pin in elem.input_pins + elem.output_pins + elem.inout_pins:
                pin.owner_id = elem.element_id
                graph.pins[pin.pin_id] = pin


def _parse_input_element(item) -> CFCElement:
    elem = CFCElement(element_type="input")
    elem.element_id = _parse_id(item)
    elem.bounds = _get_v_str(item, "Bounds")

    for child in item:
        n_attr = child.get("n", "")
        t_attr = child.get("t", "")
        if n_attr == "Output" and t_attr == "CFCOutputPin":
            pin = _parse_pin(child, "output", 0)
            elem.output_pins = [pin]
        elif n_attr == "Outputs" and t_attr == "CFCItemList":
            elem.output_pins = _parse_pin_list(child, "output")
        elif n_attr == "Text" and t_attr == "CFCText":
            elem.texts = [_get_v_str(child, "Text")]
        elif n_attr == "Texts" and t_attr == "CFCItemList":
            elem.texts = _parse_text_list(child)

    if elem.texts:
        for t in elem.texts:
            if t:
                elem.var_name = t
                break
    return elem


def _parse_output_element(item) -> CFCElement:
    elem = CFCElement(element_type="output")
    elem.element_id = _parse_id(item)
    elem.bounds = _get_v_str(item, "Bounds")

    for child in item:
        n_attr = child.get("n", "")
        t_attr = child.get("t", "")
        if n_attr == "Input" and t_attr == "CFCInputPinWithSetReset":
            pin = _parse_pin(child, "input", 0)
            sr = _get_v_str(child, "SetReset")
            if sr and sr != "None":
                pin.set_reset = sr
            elem.input_pins = [pin]
        elif n_attr == "Inputs":
            elem.input_pins = _parse_single_input_pin(child)
        elif n_attr == "Text" and t_attr == "CFCText":
            elem.texts = [_get_v_str(child, "Text")]
        elif n_attr == "Texts" and t_attr == "CFCItemList":
            elem.texts = _parse_text_list(child)

    if elem.texts:
        for t in elem.texts:
            if t:
                elem.var_name = t
                break
    return elem


def _parse_box_element(item) -> CFCElement:
    elem = CFCElement(element_type="box")
    elem.element_id = _parse_id(item)
    elem.bounds = _get_v_str(item, "Bounds")
    elem.kind_of_call = _get_v_str(item, "KindOfCall")
    elem.en_eno = _get_v_str(item, "EnEno").lower() == "true"

    for child in item:
        if child.get("n") == "Inputs" and child.get("t") == "CFCItemList":
            elem.input_pins, extra_inout = _parse_box_input_pins(child)
            elem.inout_pins.extend(extra_inout)
    for child in item:
        if child.get("n") == "Outputs" and child.get("t") == "CFCItemList":
            elem.output_pins = _parse_pin_list(child, "output")
    for child in item:
        if child.get("n") == "Texts" and child.get("t") == "CFCItemList":
            elem.texts = _parse_text_list(child)

    return elem


def _parse_box_input_pins(inputs_el) -> Tuple[List[PinInfo], List[PinInfo]]:
    """Parse input pins from a box, detecting InOut pins via cet attribute."""
    input_pins: List[PinInfo] = []
    inout_pins: List[PinInfo] = []

    for l2 in inputs_el.findall("l2"):
        if l2.get("n") != "InnerList":
            continue
        cet = l2.get("cet", "")
        idx = 0
        for pin_o in l2.findall("o"):
            t_attr = pin_o.get("t", "")
            if t_attr == "CFCInOutPin" or cet == "CFCInOutPin":
                pin = _parse_pin(pin_o, "inout", idx)
                inout_pins.append(pin)
            else:
                pin = _parse_pin(pin_o, "input", idx)
                input_pins.append(pin)
            idx += 1
        break
    return input_pins, inout_pins


def _parse_pin_list(container, pin_type: str) -> List[PinInfo]:
    pins = []
    for l2 in container.findall("l2"):
        if l2.get("n") == "InnerList":
            for idx, pin_o in enumerate(l2.findall("o")):
                pins.append(_parse_pin(pin_o, pin_type, idx))
            break
    return pins


def _parse_single_input_pin(container) -> List[PinInfo]:
    """Parse the single input pin of a CFCOutputElement (CFCInputPinWithSetReset)."""
    pins = []
    for child in container:
        if child.tag == "o":
            pin = _parse_pin(child, "input", 0)
            sr = _get_v_str(child, "SetReset")
            if sr and sr != "None":
                pin.set_reset = sr
            pins.append(pin)
            break
    if not pins:
        for l2 in container.findall("l2"):
            if l2.get("n") == "InnerList":
                for idx, pin_o in enumerate(l2.findall("o")):
                    pin = _parse_pin(pin_o, "input", idx)
                    sr = _get_v_str(pin_o, "SetReset")
                    if sr and sr != "None":
                        pin.set_reset = sr
                    pins.append(pin)
                break
    return pins


def _parse_pin(pin_o, pin_type: str, index: int) -> PinInfo:
    pin = PinInfo(pin_type=pin_type, index=index)
    pin.pin_id = _parse_id(pin_o)
    pin.negated = _get_v_str(pin_o, "Negated").lower() == "true"
    sr = _get_v_str(pin_o, "SetReset")
    if sr and sr != "None":
        pin.set_reset = sr
    return pin


def _parse_text_list(container) -> List[str]:
    texts = []
    for l2 in container.findall("l2"):
        if l2.get("n") == "InnerList":
            for text_o in l2.findall("o"):
                texts.append(_get_v_str(text_o, "Text"))
            break
    return texts


def _parse_id(element) -> int:
    raw = _get_v_str(element, "Id")
    if raw.endswith("L"):
        raw = raw[:-1]
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Phase 2: Connection scan
# ---------------------------------------------------------------------------

def _scan_connections(inner_list, graph: CFCGraph) -> None:
    for item in inner_list:
        if item.tag != "o":
            continue
        if item.get("t") != "CFCConnection":
            continue
        src_raw = _get_v_str(item, "SourcePinId")
        dst_raw = _get_v_str(item, "DestPinId")
        if src_raw.endswith("L"):
            src_raw = src_raw[:-1]
        if dst_raw.endswith("L"):
            dst_raw = dst_raw[:-1]
        try:
            src_id = int(src_raw)
            dst_id = int(dst_raw)
        except (ValueError, TypeError):
            continue

        conn = CFCConnection(source_pin_id=src_id, dest_pin_id=dst_id)
        graph.connections.append(conn)
        graph.edges[dst_id] = src_id
        graph.reverse_edges.setdefault(src_id, []).append(dst_id)


# ---------------------------------------------------------------------------
# Phase 3: Text assignment
# ---------------------------------------------------------------------------

def _assign_texts(graph: CFCGraph) -> None:
    """Assign pin names and box type/instance from CFCText lists."""
    for elem in graph.elements.values():
        if elem.element_type == "box":
            _assign_box_texts(elem)


def _assign_box_texts(elem: CFCElement) -> None:
    texts = elem.texts
    if not texts:
        return

    modifiable_idx = -1
    for i, t in enumerate(texts):
        if t and t not in ("",):
            pass

    if elem.kind_of_call == "Operator":
        for i, t in enumerate(texts):
            if t:
                elem.box_type = t
                break
        for t in reversed(texts):
            if t:
                elem.box_type = t
                break
        for i, t in enumerate(texts):
            if t:
                elem.box_type = t
                modifiable_idx = i
                break

        non_empty = [t for t in texts if t]
        if non_empty:
            elem.box_type = non_empty[-1]

    elif elem.kind_of_call == "FunctionBlock":
        non_empty = [t for t in texts if t]
        if len(non_empty) >= 2:
            elem.box_type = non_empty[-2]
            elem.instance_name = non_empty[-1]
        elif len(non_empty) == 1:
            elem.box_type = non_empty[0]
            elem.instance_name = non_empty[0]

        n_inputs = len(elem.input_pins) + len(elem.inout_pins)
        n_outputs = len(elem.output_pins)
        pin_names_count = n_inputs + n_outputs

        all_texts = texts[:]
        if len(all_texts) >= pin_names_count + 2:
            all_input_pins = sorted(
                elem.input_pins + elem.inout_pins, key=lambda p: p.index
            )
            idx = 0
            for pin in all_input_pins:
                if idx < len(all_texts):
                    pin.name = all_texts[idx]
                idx += 1
            for pin in elem.output_pins:
                if idx < len(all_texts):
                    pin.name = all_texts[idx]
                idx += 1

    else:
        non_empty = [t for t in texts if t]
        if non_empty:
            elem.box_type = non_empty[-1]


# ---------------------------------------------------------------------------
# Phase 4: Execution order from InnerList serialization
# ---------------------------------------------------------------------------

def _extract_execution_order(inner_list, graph: CFCGraph) -> None:
    """Extract execution order from InnerList element serialization order.

    Only CFCBoxElement and CFCOutputElement have execution order.
    Their relative order in the InnerList IS the execution order.
    """
    for item in inner_list:
        if item.tag != "o":
            continue
        t_attr = item.get("t", "")
        if t_attr in ("CFCBoxElement", "CFCOutputElement"):
            eid = _parse_id(item)
            if eid in graph.elements:
                graph.execution_order.append(graph.elements[eid])


# ---------------------------------------------------------------------------
# IR Mapping: CFC elements -> BoxNode / AssignNode / OperandNode
# ---------------------------------------------------------------------------

def _resolve_expression(pin_id: int, graph: CFCGraph) -> Union[BoxNode, OperandNode]:
    """Recursively resolve a destination pin to an expression tree.

    For operator sources: builds nested BoxNode trees (inlined expressions).
    For FB sources: returns OperandNode referencing instance.param.
    For input sources: returns OperandNode with variable name.
    """
    source_pin_id = graph.edges.get(pin_id)
    if source_pin_id is None:
        return OperandNode(name="(* unconnected *)")

    source_pin = graph.pins.get(source_pin_id)
    if source_pin is None:
        return OperandNode(name="(* unknown pin *)")

    source_elem = graph.elements.get(source_pin.owner_id)
    if source_elem is None:
        return OperandNode(name="(* unknown element *)")

    if source_elem.element_type == "input":
        return OperandNode(name=source_elem.var_name or "(* empty *)")

    if source_elem.element_type == "box":
        if source_elem.kind_of_call == "FunctionBlock":
            inst = source_elem.instance_name or source_elem.box_type
            out_name = source_pin.name
            if out_name:
                return OperandNode(name=f"{inst}.{out_name}")
            return OperandNode(name=inst)

        return _build_operator_tree(source_elem, graph)

    return OperandNode(name="(* unresolved *)")


def _build_operator_tree(elem: CFCElement, graph: CFCGraph) -> BoxNode:
    """Recursively build a BoxNode expression tree for an operator."""
    box_type = elem.box_type
    call_type = "Operator"
    if box_type in ("AND", "And"):
        call_type, box_type = "And", "AND"
    elif box_type in ("OR", "Or"):
        call_type, box_type = "Or", "OR"
    elif box_type in ("XOR", "Xor"):
        call_type, box_type = "Xor", "XOR"
    elif box_type in ("NOT", "Not"):
        call_type, box_type = "Not", "NOT"

    input_items: List[Union[BoxNode, OperandNode]] = []
    input_flags: List[int] = []
    for pin in elem.input_pins:
        resolved = _resolve_expression(pin.pin_id, graph)
        input_items.append(resolved)
        input_flags.append(1 if pin.negated else 0)

    for pin in elem.inout_pins:
        resolved = _resolve_expression(pin.pin_id, graph)
        input_items.append(resolved)
        input_flags.append(0)

    return BoxNode(
        box_type=box_type,
        call_type=call_type,
        input_items=input_items,
        input_flags=input_flags,
        xml_id=str(elem.element_id),
    )


def map_cfc_to_ir(graph: CFCGraph, tc: TcFile) -> List[NwlNetwork]:
    """Convert CFC graph into NwlNetwork items using execution order.

    Operators are inlined into expression trees (not standalone statements).
    FBs are standalone call statements.
    Outputs are assignment statements with recursively resolved rvalues.

    Also builds tc.cfc_exec_order_map: item_index -> (order_idx, description).
    """
    items: List[Union[BoxNode, AssignNode]] = []
    exec_map: Dict[int, Tuple[int, str]] = {}

    for order_idx, elem in enumerate(graph.execution_order):
        if elem.element_type == "box":
            if elem.kind_of_call == "FunctionBlock":
                node = _map_function_block(elem, graph, tc)
                desc = elem.instance_name or elem.box_type
                exec_map[len(items)] = (order_idx, desc)
                items.append(node)

        elif elem.element_type == "output":
            node = _map_output_element(elem, graph, tc)
            if node is not None:
                desc = f"=> {elem.var_name}"
                exec_map[len(items)] = (order_idx, desc)
                items.append(node)

    tc.cfc_exec_order_map = exec_map
    nw = NwlNetwork(index=0, items=items)
    return [nw]


def _map_function_block(elem: CFCElement, graph: CFCGraph, tc: TcFile) -> BoxNode:
    """Map a CFC FunctionBlock box to a BoxNode (standalone call)."""
    inst_name = elem.instance_name or elem.box_type

    all_input_pins = sorted(
        elem.input_pins + elem.inout_pins, key=lambda p: p.index
    )
    input_items: List[Union[BoxNode, OperandNode]] = []
    input_param_names: List[str] = []
    input_flags: List[int] = []
    for pin in all_input_pins:
        resolved = _resolve_expression(pin.pin_id, graph)
        input_items.append(resolved)
        input_param_names.append(pin.name or "")
        input_flags.append(1 if pin.negated else 0)

    output_items: List[OperandNode] = []
    output_param_names: List[str] = []
    for pin in elem.output_pins:
        output_items.append(OperandNode(is_null=True))
        output_param_names.append(pin.name or "")

    return BoxNode(
        box_type=elem.box_type,
        call_type="FunctionBlock",
        instance=OperandNode(name=inst_name, is_instance=True),
        input_items=input_items,
        input_param_names=input_param_names,
        input_flags=input_flags,
        output_items=output_items,
        output_param_names=output_param_names,
        xml_id=str(elem.element_id),
    )


def _map_output_element(elem: CFCElement, graph: CFCGraph, tc: TcFile) -> Optional[AssignNode]:
    """Map a CFCOutputElement to an AssignNode with recursively resolved rvalue."""
    if not elem.var_name:
        return None
    target = OperandNode(name=elem.var_name, is_lvalue=True)

    if not elem.input_pins:
        tc.warnings.append(f"Output '{elem.var_name}' has no input pin")
        return AssignNode(outputs=[target], rvalue=OperandNode(name="(* no source *)"))

    pin = elem.input_pins[0]
    rvalue = _resolve_expression(pin.pin_id, graph)

    flags = 0
    if pin.negated:
        flags = 1

    return AssignNode(outputs=[target], rvalue=rvalue, flags=flags)


# ---------------------------------------------------------------------------
# Post-processing: inject CFC execution order comments
# ---------------------------------------------------------------------------

def _inject_exec_order_comments(tc: TcFile) -> None:
    """Strip FBD network headers, inject exec-order comments.

    Removes the ``(* FBD Network N *)`` header that the shared codegen emits
    (CFC always has exactly one network, so the header is noise).  Optionally
    replaces it with ``(* CFC Network N: <comment> *)``.  Then inserts
    ``(* CFC Exec Order: N — desc *)`` comments between statement blocks
    using tc.cfc_exec_order_map.
    """
    exec_map = getattr(tc, "cfc_exec_order_map", None)
    if not tc.generated_st:
        return

    lines = tc.generated_st.split("\n")
    cleaned: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("(* FBD Network ") and stripped.endswith("*)"):
            if tc.networks and tc.networks[0].comment:
                nw_num = stripped.split("Network ")[1].split(":")[0].split(" ")[0].rstrip("*)")
                cleaned.append(f"(* CFC Network {nw_num}: {tc.networks[0].comment} *)")
            continue
        cleaned.append(line)

    if not exec_map:
        tc.generated_st = "\n".join(cleaned)
        return

    result: List[str] = []
    item_idx = 0
    comment_placed = False
    for line in cleaned:
        stripped = line.strip()
        if not comment_placed and stripped and not stripped.startswith("(*"):
            if item_idx in exec_map:
                order_idx, desc = exec_map[item_idx]
                if item_idx > 0:
                    result.append("")
                result.append(f"(* CFC Exec Order: {order_idx} — {desc} *)")
            comment_placed = True

        result.append(line)

        if stripped.endswith(";"):
            item_idx += 1
            comment_placed = False

    tc.generated_st = "\n".join(result)


# ---------------------------------------------------------------------------
# XML writer — replace CFC with ST in the .TcPOU
# ---------------------------------------------------------------------------

def _replace_cfc_block(text: str, start_tag: str, st_code: str) -> str:
    """Replace <Implementation><CFC>...</CFC></Implementation> with ST."""
    anchor = text.find(start_tag)
    if anchor < 0:
        return text

    search_from = anchor + len(start_tag)
    impl_open = text.find("<Implementation>", search_from)
    if impl_open < 0:
        return text

    cfc_open = text.find("<CFC>", impl_open)
    if cfc_open < 0:
        return text

    cfc_close = text.find("</CFC>", cfc_open)
    if cfc_close < 0:
        return text

    impl_close = text.find("</Implementation>", cfc_close)
    if impl_close < 0:
        return text
    impl_close_end = impl_close + len("</Implementation>")

    indent = "      "
    new_impl = (
        "<Implementation>\n"
        f"{indent}<ST><![CDATA[{st_code}]]></ST>\n"
        "    </Implementation>"
    )
    return text[:impl_open] + new_impl + text[impl_close_end:]


def write_cfc_st_to_xml(tc: TcFile, regenerate_ids: bool = False) -> Optional[str]:
    if tc.xml_root is None:
        return None

    raw_text = tc.path.read_text(encoding=tc.encoding)

    if "<POU " not in raw_text and "<POU>" not in raw_text:
        return None
    if "<CFC>" not in raw_text:
        return None

    pou_tag_match = re.search(r'<POU\s[^>]*>', raw_text)
    if not pou_tag_match:
        return None
    pou_tag = pou_tag_match.group(0)

    result = _replace_cfc_block(raw_text, pou_tag, tc.generated_st)
    if result == raw_text:
        return None

    if regenerate_ids:
        result = _regenerate_guids(result)

    return result


# ---------------------------------------------------------------------------
# Main processing pipeline
# ---------------------------------------------------------------------------

def process_file(path: Path, cfg: MigrationConfig, mlog: MigrationLogger,
                 report: MigrationReport) -> bool:
    mlog.log(f"Processing: {path}")

    tc = load_file(path, cfg.encoding)
    if tc is None:
        mlog.log(f"  ERROR: Cannot load file")
        return False

    if tc.errors:
        for e in tc.errors:
            mlog.log(f"  ERROR: {e}")
        report.add(tc, None, None, False)
        return False

    mlog.log(f"  File type: {tc.file_type}")
    mlog.log(f"  POU: {tc.pou_name} ({tc.pou_type})")
    mlog.log(f"  Implementation: {tc.impl_type}")

    if tc.file_type in (".tcgvl", ".tcdut"):
        mlog.log(f"  SKIP: {tc.file_type} has no implementation to migrate")
        return True

    if tc.impl_type != "CFC":
        if tc.impl_type in ("NWL", "SFC", "IL"):
            mlog.log(f"  SKIP: {tc.impl_type} - use FBD migrator for NWL")
            tc.warnings.append(f"{tc.impl_type} not a CFC implementation")
        else:
            mlog.log(f"  SKIP: Implementation is {tc.impl_type}, not CFC")
        return True

    graph = parse_cfc_graph(tc)
    if graph is None:
        mlog.log(f"  ERROR: Failed to parse CFC graph")
        tc.errors.append("CFC graph parsing failed")
        report.add(tc, None, None, False)
        return False

    mlog.log(f"  CFC elements: {len(graph.elements)} "
             f"(boxes: {sum(1 for e in graph.elements.values() if e.element_type == 'box')}, "
             f"inputs: {sum(1 for e in graph.elements.values() if e.element_type == 'input')}, "
             f"outputs: {sum(1 for e in graph.elements.values() if e.element_type == 'output')})")
    mlog.log(f"  Connections: {len(graph.connections)}")
    mlog.log(f"  Execution order: {len(graph.execution_order)} elements")

    if cfg.analyze_only:
        mlog.log(f"  ANALYZE-ONLY: No ST generation")
        _print_cfc_analysis(tc, graph)
        report.add(tc, None, None, False)
        return True

    tc.networks = map_cfc_to_ir(graph, tc)
    mlog.log(f"  IR networks: {len(tc.networks)}, items: {sum(len(nw.items) for nw in tc.networks)}")

    convert_networks_to_st(tc, cfg)

    _inject_exec_order_comments(tc)

    acc = calculate_accuracy(tc)
    tm_count = tc.generated_st.count("TYPE MISMATCH:")
    header = build_generated_header(CFC_SOURCE_TYPE, tc.path.name, CFC_TOOL_NAME, SCRIPT_VERSION, acc, tm_count)
    tc.generated_st = header + tc.generated_st

    mlog.log(f"  ST generated: {len(tc.generated_st.splitlines())} lines")
    if tc.todos:
        mlog.log(f"  TODOs: {len(tc.todos)}")
        for t in tc.todos:
            mlog.log(f"    {t}")

    valid = validate_generated_st(tc, cfg)
    if tc.warnings:
        for w in tc.warnings:
            mlog.log(f"  WARNING: {w}")
    if tc.errors:
        for e in tc.errors:
            mlog.log(f"  ERROR: {e}")

    if not valid and cfg.strict:
        mlog.log(f"  ABORTED: Validation failed in strict mode")
        report.add(tc, None, None, False)
        return False

    if cfg.dry_run:
        acc = calculate_accuracy(tc)
        mlog.log(f"  DRY-RUN: No files changed (Accuracy: {acc:.2f} %)")
        _print_dry_run(tc, cfg)
        report.add(tc, None, None, False)
        return True

    use_swap = cfg.swap and not cfg.force and not cfg.output_path
    new_file = not cfg.force
    xml_content = write_cfc_st_to_xml(tc, regenerate_ids=new_file)
    if xml_content is None:
        mlog.log(f"  ERROR: Failed to generate output XML")
        tc.errors.append("XML generation failed")
        report.add(tc, None, None, False)
        return False

    backup_path: Optional[Path] = None

    if cfg.force:
        output_path = tc.path
        if cfg.backup:
            bkp_dir = Path(cfg.backup_dir) if cfg.backup_dir else None
            inp_root = Path(cfg.input_path) if cfg.backup_dir else None
            backup_path = create_backup(tc.path, bkp_dir, inp_root)
            if backup_path is None:
                mlog.log(f"  ERROR: Backup failed, will not force-overwrite")
                tc.errors.append("Backup creation failed")
                report.add(tc, None, None, False)
                return False
            mlog.log(f"  Backup: {backup_path}")
        elif cfg.strict:
            mlog.log(f"  ERROR: Strict mode requires backup for --force")
            tc.errors.append("Strict mode: cannot force-overwrite without backup")
            report.add(tc, None, None, False)
            return False
        else:
            mlog.log(f"  WARNING: Force-overwriting without backup!")

        replaceable, reason = can_replace(tc, cfg, backup_path)
        if not replaceable:
            mlog.log(f"  BLOCKED: {reason}")
            report.add(tc, backup_path, None, False)
            return False

        ok = write_output_file(xml_content, tc.path, tc.encoding)
        if ok:
            mlog.log(f"  FORCE-OVERWRITTEN: {tc.path}")
        else:
            mlog.log(f"  ERROR: Force-overwrite failed")
        report.add(tc, backup_path, tc.path, ok)
        return ok

    if use_swap:
        if cfg.batch_dir:
            input_root = Path(cfg.input_path)
            try:
                rel = tc.path.relative_to(input_root)
            except ValueError:
                rel = Path(tc.path.name)
            backup_path = Path(cfg.batch_dir) / rel
            backup_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
            backup_path = tc.path.parent / f"{tc.path.stem}_cfc_backup_{ts}{tc.path.suffix}"
        try:
            shutil.copy2(str(tc.path), str(backup_path))
        except Exception as exc:
            mlog.log(f"  ERROR: Cannot copy to backup: {exc}")
            tc.errors.append(f"Swap backup failed: {exc}")
            report.add(tc, None, None, False)
            return False
        mlog.log(f"  BACKUP: {backup_path}")

        ok = write_output_file(xml_content, tc.path, tc.encoding)
        if ok:
            mlog.log(f"  OUTPUT: {tc.path} (original path)")
        else:
            mlog.log(f"  ERROR: Write failed, restoring original from backup")
            try:
                shutil.copy2(str(backup_path), str(tc.path))
            except Exception:
                mlog.log(f"  CRITICAL: Restore failed! Backup at {backup_path}")
        report.add(tc, backup_path, tc.path if ok else None, False)
        return ok

    if cfg.batch_dir:
        input_root = Path(cfg.input_path)
        try:
            rel = tc.path.relative_to(input_root)
        except ValueError:
            rel = Path(tc.path.name)
        output_path = Path(cfg.batch_dir) / rel
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path = _resolve_output_path(tc.path, cfg)
    ok = write_output_file(xml_content, output_path, tc.encoding)
    if ok:
        mlog.log(f"  OUTPUT: {output_path}")
    else:
        mlog.log(f"  ERROR: Write failed: {output_path}")
    report.add(tc, None, output_path, False)
    return ok


def _print_cfc_analysis(tc: TcFile, graph: CFCGraph):
    print(f"\n{'=' * 60}")
    print(f"CFC ANALYSIS: {tc.path.name}")
    print(f"{'=' * 60}")
    print(f"  POU Name:       {tc.pou_name}")
    print(f"  POU Type:       {tc.pou_type}")
    print(f"  Implementation: {tc.impl_type}")

    boxes = [e for e in graph.elements.values() if e.element_type == "box"]
    inputs = [e for e in graph.elements.values() if e.element_type == "input"]
    outputs = [e for e in graph.elements.values() if e.element_type == "output"]

    print(f"  Elements:       {len(graph.elements)} total")
    print(f"    Boxes:        {len(boxes)}")
    print(f"    Inputs:       {len(inputs)}")
    print(f"    Outputs:      {len(outputs)}")
    print(f"  Connections:    {len(graph.connections)}")
    print(f"  Exec order:     {len(graph.execution_order)} elements")

    for elem in boxes:
        kind = elem.kind_of_call
        if kind == "FunctionBlock":
            print(f"    FB: {elem.box_type} inst={elem.instance_name}")
        else:
            print(f"    Op: {elem.box_type}")

    for elem in outputs:
        print(f"    Out: {elem.var_name}")
    print()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    cfg = parse_arguments(argv)
    logging.basicConfig(level=getattr(logging, cfg.log_level, logging.INFO),
                        format="%(levelname)s: %(message)s")
    cfg = load_config(cfg)

    input_p = Path(cfg.input_path)
    prefix = input_p.stem.lower() if input_p.is_file() else input_p.name.lower()
    ts_batch = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")

    if input_p.is_dir() and not cfg.dry_run and not cfg.analyze_only:
        use_swap = cfg.swap and not cfg.force and not cfg.output_path
        if cfg.output_path and not cfg.force:
            bd = Path(cfg.output_path)
            bd.mkdir(parents=True, exist_ok=True)
            cfg.batch_dir = str(bd)
            base_path = bd
        elif use_swap:
            batch_name = f"{input_p.name}_cfc_backup_{ts_batch}"
            bd = input_p.parent / batch_name
            bd.mkdir(parents=True, exist_ok=True)
            cfg.batch_dir = str(bd)
            base_path = bd
        elif not cfg.force:
            batch_name = f"{input_p.name}_st_generated_{ts_batch}"
            bd = input_p.parent / batch_name
            bd.mkdir(parents=True, exist_ok=True)
            cfg.batch_dir = str(bd)
            base_path = bd
        else:
            base_path = input_p

        if cfg.force and cfg.backup:
            bkp_name = f"{input_p.name}_cfc_backup_{ts_batch}"
            bkp_dir = input_p.parent / bkp_name
            bkp_dir.mkdir(parents=True, exist_ok=True)
            cfg.backup_dir = str(bkp_dir)
    else:
        base_path = input_p.parent if input_p.is_file() else input_p

    mlog = MigrationLogger(cfg.log_enabled, base_path, prefix)
    report = MigrationReport(cfg.report_enabled, base_path, prefix)

    mlog.log(f"TwinCAT CFC-to-ST Migrator v{SCRIPT_VERSION}")
    mlog.log(f"Input: {cfg.input_path}")
    mlog.log(f"Mode: {'dry-run' if cfg.dry_run else 'analyze-only' if cfg.analyze_only else 'migrate'}")
    mlog.log(f"Force: {cfg.force}, Swap: {cfg.swap}, Backup: {cfg.backup}, Strict: {cfg.strict}")

    files = collect_input_files(cfg)
    if not files:
        mlog.log("No supported files found.")
        print("No supported files found.")
        mlog.save()
        return 1

    mlog.log(f"Files to process: {len(files)}")

    success_count = 0
    fail_count = 0

    for f in files:
        try:
            result = process_file(f, cfg, mlog, report)
            if result:
                success_count += 1
            else:
                fail_count += 1
        except Exception as exc:
            mlog.log(f"EXCEPTION processing {f}: {exc}")
            mlog.log(traceback.format_exc())
            fail_count += 1

    acc_values = [r["accuracy"] for r in report.file_reports if r.get("accuracy") is not None]
    overall_acc = round(sum(acc_values) / len(acc_values), 2) if acc_values else 100.0

    mlog.log(f"Done. Success: {success_count}, Failed: {fail_count}, Accuracy: {overall_acc:.2f} %")
    print(f"\nMigration complete. Success: {success_count}, Failed: {fail_count}, Accuracy: {overall_acc:.2f} %")

    mlog.save()
    report.save()

    if mlog.enabled and mlog.entries:
        print(f"Log: {mlog.log_path}")
    if report.enabled and report.file_reports:
        print(f"Report: {report.report_path}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
