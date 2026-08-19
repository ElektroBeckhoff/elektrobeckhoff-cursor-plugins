"""CFC XML parser."""
from __future__ import annotations

from typing import List, Optional, Tuple

from migrator.cfc.types import CFCConnection, CFCElement, CFCGraph, PinInfo
from migrator.types import TcFile
from migrator.xml_reader import _get_v_str


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

        elif t_attr == "CFCSourceConnectionMark":
            elem = _parse_source_mark(item)
            graph.elements[elem.element_id] = elem
            for pin in elem.input_pins:
                pin.owner_id = elem.element_id
                graph.pins[pin.pin_id] = pin
            if elem.var_name and elem.input_pins:
                graph.mark_sources[elem.var_name] = elem.input_pins[0].pin_id

        elif t_attr == "CFCSinkConnectionMark":
            elem = _parse_sink_mark(item)
            graph.elements[elem.element_id] = elem
            for pin in elem.output_pins:
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


def _parse_source_mark(item) -> CFCElement:
    """Parse a CFCSourceConnectionMark (receives a signal, names it)."""
    elem = CFCElement(element_type="source_mark")
    elem.element_id = _parse_id(item)
    elem.bounds = _get_v_str(item, "Bounds")

    for child in item:
        n_attr = child.get("n", "")
        t_attr = child.get("t", "")
        if n_attr == "Input" and t_attr in ("CFCInputPin", "CFCInputPinWithSetReset"):
            pin = _parse_pin(child, "input", 0)
            elem.input_pins = [pin]
        elif n_attr == "Text" and t_attr == "CFCText":
            elem.texts = [_get_v_str(child, "Text")]

    if elem.texts:
        for t in elem.texts:
            if t:
                elem.var_name = t
                break
    return elem


def _parse_sink_mark(item) -> CFCElement:
    """Parse a CFCSinkConnectionMark (provides a named signal to consumers)."""
    elem = CFCElement(element_type="sink_mark")
    elem.element_id = _parse_id(item)
    elem.bounds = _get_v_str(item, "Bounds")

    for child in item:
        n_attr = child.get("n", "")
        t_attr = child.get("t", "")
        if n_attr == "Output" and t_attr == "CFCOutputPin":
            pin = _parse_pin(child, "output", 0)
            elem.output_pins = [pin]
        elif n_attr == "Text" and t_attr == "CFCText":
            elem.texts = [_get_v_str(child, "Text")]

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
        n_attr = child.get("n", "")
        t_attr = child.get("t", "")
        if n_attr == "Inputs" and t_attr == "CFCItemList":
            elem.input_pins, extra_inout = _parse_box_input_pins(child)
            elem.inout_pins.extend(extra_inout)
        elif n_attr == "Input" and t_attr in ("CFCInputPin", "CFCInputPinWithSetReset"):
            if not elem.input_pins:
                elem.input_pins = [_parse_pin(child, "input", 0)]
    for child in item:
        n_attr = child.get("n", "")
        t_attr = child.get("t", "")
        if n_attr == "Outputs" and t_attr == "CFCItemList":
            elem.output_pins = _parse_pin_list(child, "output")
        elif n_attr == "Output" and t_attr == "CFCOutputPin":
            if not elem.output_pins:
                elem.output_pins = [_parse_pin(child, "output", 0)]
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


def _assign_texts(graph: CFCGraph) -> None:
    """Assign pin names and box type/instance from CFCText lists."""
    for elem in graph.elements.values():
        if elem.element_type == "box":
            _assign_box_texts(elem)


def _assign_box_texts(elem: CFCElement) -> None:
    texts = elem.texts
    if not texts:
        return

    if elem.kind_of_call == "Operator":
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


def _extract_execution_order(inner_list, graph: CFCGraph) -> None:
    """Extract execution order from InnerList element serialization order."""
    for item in inner_list:
        if item.tag != "o":
            continue
        t_attr = item.get("t", "")
        if t_attr in ("CFCBoxElement", "CFCOutputElement"):
            eid = _parse_id(item)
            if eid in graph.elements:
                graph.execution_order.append(graph.elements[eid])
