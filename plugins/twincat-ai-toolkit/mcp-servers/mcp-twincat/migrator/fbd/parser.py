"""NWL (FBD/FUP) XML parser."""
from __future__ import annotations

from typing import List, Union

from migrator.types import AssignNode, BoxNode, DemuxNode, NwlNetwork, OperandNode, TcFile
from migrator.xml_reader import _find_child_by_name, _find_v, _get_v_str, _strip_quotes


def parse_nwl_networks(tc: TcFile) -> None:
    pou = tc.xml_root.find("POU")
    if pou is None:
        return
    impl = pou.find("Implementation")
    if impl is None:
        return
    nwl = impl.find("NWL")
    if nwl is None:
        return

    tc.networks = _parse_network_list(nwl)

    for action in tc.actions:
        if action.impl_type == "NWL" and action.xml_element is not None:
            action_impl = action.xml_element.find("Implementation")
            if action_impl is not None:
                action_nwl = action_impl.find("NWL")
                if action_nwl is not None:
                    action.networks = _parse_network_list(action_nwl)


def _parse_network_list(nwl_element) -> List[NwlNetwork]:
    networks: List[NwlNetwork] = []
    archive = nwl_element.find("XmlArchive")
    if archive is None:
        return networks
    data = archive.find("Data")
    if data is None:
        return networks

    nwl_obj = None
    for o in data.findall("o"):
        if o.get("t") == "NWLImplementationObject":
            nwl_obj = o
            break
    if nwl_obj is None:
        for o in data.findall("o"):
            nwl_obj = o
            break
    if nwl_obj is None:
        return networks

    network_list = None
    for l2 in nwl_obj.findall("l2"):
        if l2.get("n") == "NetworkList":
            network_list = l2
            break
    if network_list is None:
        return networks

    for idx, net_o in enumerate(network_list.findall("o")):
        nw = NwlNetwork(index=idx)
        nw.comment = _get_v_str(net_o, "Comment")
        nw.title = _get_v_str(net_o, "Title")
        nw.label = _get_v_str(net_o, "Label")
        nw.out_commented = _get_v_str(net_o, "OutCommented").lower() == "true"
        nw.xml_id = _get_v_str(net_o, "Id")

        items_el = None
        for l2 in net_o.findall("l2"):
            if l2.get("n") == "NetworkItems":
                items_el = l2
                break
        if items_el is not None:
            cet = items_el.get("cet", "")
            for item_o in items_el.findall("o"):
                t_attr = item_o.get("t", "")
                if t_attr == "BoxTreeDemux":
                    nw.items.append(_parse_demux(item_o))
                elif cet == "BoxTreeAssign" or _has_rvalue(item_o):
                    nw.items.append(_parse_assign(item_o))
                else:
                    nw.items.append(_parse_box(item_o))
        networks.append(nw)

    return networks


def _has_rvalue(element) -> bool:
    for child in element:
        if child.get("n") == "RValue":
            return True
    return False


def _parse_box(element) -> BoxNode:
    box = BoxNode()
    box.box_type = _get_v_str(element, "BoxType")
    box.xml_id = _get_v_str(element, "Id")

    call_type_el = _find_v(element, "CallType")
    if call_type_el is not None:
        box.call_type = (call_type_el.text or "").strip()

    box.en = _get_v_str(element, "EN").lower() == "true"
    box.eno = _get_v_str(element, "ENO").lower() == "true"

    inst_el = _find_child_by_name(element, "Instance")
    if inst_el is not None:
        box.instance = _parse_operand(inst_el)

    box.output_items = _parse_output_items(element)
    box.input_items = _parse_input_items(element)
    box.input_flags = _parse_input_flags(element)

    ip = _find_child_by_name(element, "InputParam")
    if ip is not None:
        box.input_param_names = _parse_param_list_names(ip)
        box.input_param_types = _parse_param_list_types(ip)

    op = _find_child_by_name(element, "OutputParam")
    if op is not None:
        box.output_param_names = _parse_param_list_names(op)
        box.output_param_types = _parse_param_list_types(op)

    snippet_el = _find_child_by_name(element, "STSnippet")
    if snippet_el is not None:
        box.st_snippet = _parse_st_snippet(snippet_el)

    return box


def _parse_assign(element) -> AssignNode:
    assign = AssignNode()
    assign.xml_id = _get_v_str(element, "Id")
    assign.outputs = _parse_output_items(element)
    flags_el = _find_child_by_name(element, "Flags")
    if flags_el is not None:
        try:
            assign.flags = int(_get_v_str(flags_el, "Flags") or "0")
        except ValueError:
            assign.flags = 0

    rv = _find_child_by_name(element, "RValue")
    if rv is not None:
        t_attr = rv.get("t", "")
        if "BoxTreeDemux" in t_attr:
            assign.rvalue = _parse_demux(rv)
        elif "BoxTreeAssign" in t_attr:
            assign.rvalue = _parse_assign(rv)
        elif ("BoxTreeOperand" in t_attr
              or (rv.tag == "o"
                  and _find_child_by_name(rv, "Operand") is not None
                  and _find_v(rv, "BoxType") is None
                  and "BoxTreeAssign" not in t_attr)):
            assign.rvalue = _parse_operand(rv)
        else:
            assign.rvalue = _parse_box(rv)

    return assign


def _parse_demux(element) -> DemuxNode:
    demux = DemuxNode()
    demux.xml_id = _get_v_str(element, "Id")
    input_el = _find_child_by_name(element, "Input")
    if input_el is not None and input_el.tag == "o":
        demux.input = _parse_operand(input_el)
    return demux


def _parse_operand(element) -> OperandNode:
    op = OperandNode()

    inner = _find_child_by_name(element, "Operand")
    if inner is not None:
        target = inner
    else:
        target = element

    raw = _get_v_str(target, "Operand")
    op.name = _strip_quotes(raw)
    op.type_str = _get_v_str(target, "Type")
    op.is_lvalue = _get_v_str(target, "LValue").lower() == "true"
    op.is_instance = _get_v_str(target, "IsInstance").lower() == "true"
    op.xml_id = _get_v_str(target, "Id")
    op.comment = _get_v_str(target, "Comment")
    for src in (target, element):
        flags_el = _find_child_by_name(src, "Flags")
        if flags_el is not None:
            try:
                op.flags = int(_get_v_str(flags_el, "Flags") or "0")
            except ValueError:
                op.flags = 0
            break

    if not op.name:
        raw2 = _get_v_str(element, "Operand")
        if raw2:
            op.name = _strip_quotes(raw2)
        op.type_str = op.type_str or _get_v_str(element, "Type")
        op.is_lvalue = op.is_lvalue or _get_v_str(element, "LValue").lower() == "true"
        op.is_instance = op.is_instance or _get_v_str(element, "IsInstance").lower() == "true"
        op.xml_id = op.xml_id or _get_v_str(element, "Id")

    return op


def _parse_output_items(element) -> List[OperandNode]:
    results = []
    oi = _find_child_by_name(element, "OutputItems")
    if oi is None:
        return results

    inner_l2 = None
    for l2 in oi.findall("l2"):
        if l2.get("n") == "OutputItems":
            inner_l2 = l2
            break
    if inner_l2 is None:
        inner_l2 = oi

    for child in inner_l2:
        if child.tag == "n":
            results.append(OperandNode(is_null=True))
        elif child.tag == "o":
            results.append(_parse_operand(child))
    return results


def _is_assign_element(element) -> bool:
    t = element.get("t", "")
    if "BoxTreeAssign" in t:
        return True
    if _has_rvalue(element) and _find_child_by_name(element, "OutputItems") is not None:
        if not _is_box_element(element):
            return True
    return False


def _parse_input_items(element) -> List[Union[BoxNode, OperandNode, AssignNode]]:
    results = []
    for l2 in element.findall("l2"):
        if l2.get("n") == "InputItems":
            for child in l2:
                if child.tag == "n":
                    results.append(OperandNode())
                elif child.tag == "o":
                    if _is_assign_element(child):
                        results.append(_parse_assign(child))
                    elif _is_box_element(child):
                        results.append(_parse_box(child))
                    else:
                        results.append(_parse_operand(child))
            break
    return results


def _parse_input_flags(element) -> List[int]:
    flags = []
    for l2 in element.findall("l2"):
        if l2.get("n") == "InputFlags":
            for child in l2:
                if child.tag == "o":
                    val = _get_v_str(child, "Flags")
                    try:
                        flags.append(int(val))
                    except (ValueError, TypeError):
                        flags.append(0)
                elif child.tag == "n":
                    flags.append(0)
            break
    return flags


def _parse_param_list_names(element) -> List[str]:
    names = []
    for l2 in element.findall("l2"):
        if l2.get("n") == "Names":
            for v in l2.findall("v"):
                names.append((v.text or "").strip())
            break
    return names


def _parse_param_list_types(element) -> List[str]:
    types = []
    for l2 in element.findall("l2"):
        if l2.get("n") == "Types":
            for v in l2.findall("v"):
                types.append((v.text or "").strip())
            break
    return types


def _parse_st_snippet(element) -> List[str]:
    """Extract ST code lines from an STSnippet element (Execute box)."""
    lines = []
    for inner in element.iter("o"):
        if inner.get("t") == "STImplementationObject":
            for doc in inner.iter("o"):
                if doc.get("t") == "TextDocument":
                    for text_line in doc.iter("o"):
                        text_v = _get_v_str(text_line, "Text")
                        if text_v:
                            lines.append(text_v)
            break
    return lines


def _is_box_element(element) -> bool:
    for child in element:
        if child.tag == "v" and child.get("n") == "BoxType":
            return True
    t = element.get("t", "")
    if "BoxTreeBox" in t:
        return True
    for child in element:
        if child.tag == "l2" and child.get("n") == "InputItems":
            return True
    return False
