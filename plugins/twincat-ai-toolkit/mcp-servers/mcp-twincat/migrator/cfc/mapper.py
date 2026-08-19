"""Map CFC graph to shared NWL IR (BoxNode / AssignNode)."""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple, Union

from migrator.cfc.types import CFCElement, CFCGraph
from migrator.types import AssignNode, BoxNode, NwlNetwork, OperandNode, TcFile


def _resolve_expression(pin_id: int, graph: CFCGraph) -> Union[BoxNode, OperandNode]:
    """Recursively resolve a destination pin to an expression tree."""
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
        result = OperandNode(name=source_elem.var_name or "(* empty *)")
        if source_pin.negated:
            result = BoxNode(box_type="NOT", call_type="Not",
                             input_items=[result], input_flags=[0])
        return result

    if source_elem.element_type == "sink_mark":
        label = source_elem.var_name
        source_input_pin = graph.mark_sources.get(label) if label else None
        if source_input_pin is not None:
            result = _resolve_expression(source_input_pin, graph)
        else:
            result = OperandNode(name=f"(* unresolved mark: {label} *)")
        if source_pin.negated:
            result = BoxNode(box_type="NOT", call_type="Not",
                             input_items=[result], input_flags=[0])
        return result

    if source_elem.element_type == "box":
        if source_elem.kind_of_call == "FunctionBlock":
            inst = source_elem.instance_name or source_elem.box_type
            out_name = source_pin.name
            if out_name:
                result = OperandNode(name=f"{inst}.{out_name}")
            else:
                result = OperandNode(name=inst)
            if source_pin.negated:
                result = BoxNode(box_type="NOT", call_type="Not",
                                 input_items=[result], input_flags=[0])
            return result

        result = _build_operator_tree(source_elem, graph)
        if source_pin.negated:
            result = BoxNode(box_type="NOT", call_type="Not",
                             input_items=[result], input_flags=[0])
        return result

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
    """Convert CFC graph into NwlNetwork items using execution order."""
    items: List[Union[BoxNode, AssignNode]] = []
    exec_map: Dict[int, Tuple[int, str]] = {}

    for order_idx, elem in enumerate(graph.execution_order):
        if elem.element_type == "box":
            if elem.kind_of_call == "FunctionBlock":
                node = _map_function_block(elem, graph, tc)
                desc = elem.instance_name or elem.box_type
                exec_map[len(items)] = (order_idx, desc)
                items.append(node)
            elif elem.kind_of_call == "Base" and elem.box_type == "SUPER^":
                node = BoxNode(box_type="SUPER^", call_type="Action",
                               xml_id=str(elem.element_id))
                exec_map[len(items)] = (order_idx, "SUPER^")
                items.append(node)
            elif elem.kind_of_call == "LocalAction":
                node = BoxNode(box_type=elem.box_type, call_type="Action",
                               xml_id=str(elem.element_id))
                exec_map[len(items)] = (order_idx, f"Action: {elem.box_type}")
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


def inject_exec_order_comments(tc: TcFile) -> None:
    """Strip FBD network headers and inject CFC exec-order comments."""
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
