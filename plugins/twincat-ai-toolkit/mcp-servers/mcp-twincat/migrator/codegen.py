"""ST code generation from FBD/NWL IR."""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Union

from .constants import (
    ARITHMETIC_OPS,
    COMPARISON_OPS,
    CONVERSION_FUNCS,
    FB_CALL_TYPES,
    IEC_FUNCTIONS,
    INFIX_OPERATORS,
)
from .types import (
    AssignNode,
    BoxNode,
    DemuxNode,
    MigrationConfig,
    NwlNetwork,
    OperandNode,
    StNetwork,
    TcFile,
)


def _clean_bool_expr(expr: str) -> str:
    """Remove redundant OR FALSE / AND TRUE from boolean expressions."""
    expr = re.sub(r'\s+OR\s+FALSE\b', '', expr)
    expr = re.sub(r'\bFALSE\s+OR\s+', '', expr)
    expr = re.sub(r'\s+AND\s+TRUE\b', '', expr)
    expr = re.sub(r'\bTRUE\s+AND\s+', '', expr)
    return expr.strip()


def _apply_input_flag(expr: str, flag: int, box: BoxNode, input_idx: int,
                      tc: TcFile, hoisted: List[str]) -> str:
    if not expr:
        return expr
    logic_flag = flag & 0x07
    if logic_flag == 0:
        return expr
    if logic_flag & 1:
        if " " in expr and not expr.startswith("("):
            return f"NOT ({expr})"
        return f"NOT {expr}"
    if logic_flag in (2, 4):
        edge_type = "R_TRIG" if logic_flag == 2 else "F_TRIG"
        suffix = "PosEdge" if logic_flag == 2 else "NegEdge"
        inst = box.instance.name if box.instance else f"Box{box.xml_id or input_idx}"
        clean = re.sub(r'[\[\].\s]', '_', inst)
        pname = (box.input_param_names[input_idx]
                 if input_idx < len(box.input_param_names) else f"In{input_idx}")
        edge_name = f"fb_{clean}_{pname}_{suffix}"
        hoisted.append(f"{edge_name}(CLK := {expr});")
        if (edge_name, edge_type) not in tc.edge_vars:
            tc.edge_vars.append((edge_name, edge_type))
        return f"{edge_name}.Q"
    return expr


def convert_networks_to_st(tc: TcFile, cfg: MigrationConfig) -> None:
    tc.st_networks = []
    tc.todos = []
    tc.edge_vars = []
    all_lines: List[str] = []

    for nw in tc.networks:
        stn = StNetwork(index=nw.index, out_commented=nw.out_commented)

        header_parts = []
        if nw.title:
            header_parts.append(f"Title: {nw.title}")
        if nw.comment:
            header_parts.append(nw.comment)

        nw_label = f"Network {nw.index + 1}"
        comment_text = ": ".join(header_parts) if header_parts else ""
        oc_suffix = " [OutCommented]" if nw.out_commented else ""
        if comment_text:
            stn.comment_header = f"(* FBD {nw_label}: {comment_text}{oc_suffix} *)"
        else:
            stn.comment_header = f"(* FBD {nw_label}{oc_suffix} *)"

        if nw.out_commented:
            commented_lines = _generate_network_code(nw, tc, cfg)
            wrapped = ["(* OutCommented network:"]
            for line in commented_lines:
                wrapped.append(f"   {line}")
            wrapped.append("*)")
            stn.lines = wrapped
        else:
            todos_before = len(tc.todos)
            generated = _generate_network_code(nw, tc, cfg)
            new_todos = tc.todos[todos_before:]
            if new_todos and cfg.mark_todo:
                reasons = []
                for t in new_todos:
                    clean = t.replace("// TODO [FBD Migration]: ", "").replace("// TODO: ", "")
                    reasons.append(clean)
                reason_str = "; ".join(reasons)
                wrapped = [f"(* TODO [FBD Migration]: Network {nw.index + 1} - migration incomplete"]
                wrapped.append(f"   Reason: {reason_str}")
                wrapped.append(f"   Best-effort ST:")
                for line in generated:
                    wrapped.append(f"   {line}")
                wrapped.append("*)")
                stn.lines = wrapped
            else:
                stn.lines = generated

        stn.todos = [t for t in tc.todos if t not in [x for s in tc.st_networks for x in s.todos]]
        tc.st_networks.append(stn)

    for stn in tc.st_networks:
        if stn.comment_header:
            all_lines.append(stn.comment_header)
        all_lines.extend(stn.lines)
        all_lines.append("")

    tc.generated_st = "\n".join(all_lines).rstrip() + "\n"

    for action in tc.actions:
        if action.networks:
            action_lines: List[str] = []
            for nw in action.networks:
                todos_before = len(tc.todos)
                code = _generate_network_code(nw, tc, cfg)
                new_todos = tc.todos[todos_before:]
                if new_todos and cfg.mark_todo:
                    reasons = []
                    for t in new_todos:
                        clean = t.replace("// TODO [FBD Migration]: ", "").replace("// TODO: ", "")
                        reasons.append(clean)
                    reason_str = "; ".join(reasons)
                    action_lines.append(f"(* TODO [FBD Migration]: Action '{action.name}' Network {nw.index + 1} - migration incomplete")
                    action_lines.append(f"   Reason: {reason_str}")
                    action_lines.append(f"   Best-effort ST:")
                    for line in code:
                        action_lines.append(f"   {line}")
                    action_lines.append("*)")
                else:
                    action_lines.extend(code)
                action_lines.append("")
            action.st_code = "\n".join(action_lines).rstrip() + "\n"


def _generate_network_code(nw: NwlNetwork, tc: TcFile, cfg: MigrationConfig) -> List[str]:
    lines: List[str] = []

    demux_source: Optional[OperandNode] = None
    for item in nw.items:
        if isinstance(item, DemuxNode) and item.input and not item.input.is_empty:
            demux_source = item.input

    for item in nw.items:
        if isinstance(item, DemuxNode):
            continue
        if isinstance(item, AssignNode):
            if (isinstance(item.rvalue, DemuxNode)
                    and (item.rvalue.input is None or item.rvalue.input.is_empty)):
                if demux_source:
                    item.rvalue = OperandNode(
                        name=demux_source.name,
                        type_str=demux_source.type_str,
                        xml_id=demux_source.xml_id,
                    )
                else:
                    targets = [o.name for o in item.outputs if not o.is_empty]
                    todo = (f"// TODO [FBD Migration]: BoxTreeDemux RValue for "
                            f"'{', '.join(targets)}' - no demux source found in network")
                    lines.append(todo)
                    tc.todos.append(todo)
                    continue
            lines.extend(_gen_assign(item, tc, cfg))
        elif isinstance(item, BoxNode):
            lines.extend(_gen_top_level_box(item, tc, cfg))
    return lines


def _is_return_assign(assign: AssignNode) -> bool:
    """BoxTreeAssign with output '???' and Flags=8 is a FBD RETURN element."""
    return (assign.outputs
            and all(o.name == "???" and o.flags == 8 for o in assign.outputs))


def _gen_assign(assign: AssignNode, tc: TcFile, cfg: MigrationConfig) -> List[str]:
    lines: List[str] = []
    if assign.rvalue is None:
        return lines

    if _is_return_assign(assign):
        hoisted: List[str] = []
        cond = _gen_expression(assign.rvalue, tc, cfg, hoisted)
        cond = _clean_bool_expr(cond)
        lines.extend(hoisted)
        if cond and cond.upper() not in ("TRUE", "1"):
            lines.append(f"IF {cond} THEN")
            lines.append("    RETURN;")
            lines.append("END_IF")
        else:
            lines.append("RETURN;")
        return lines

    if isinstance(assign.rvalue, DemuxNode):
        if assign.rvalue.input and not assign.rvalue.input.is_empty:
            targets = [o for o in assign.outputs if not o.is_empty]
            for target in targets:
                lines.append(f"{target.name} := {assign.rvalue.input.name};")
        else:
            targets = [o.name for o in assign.outputs if not o.is_empty]
            todo = (f"// TODO [FBD Migration]: Unresolved BoxTreeDemux for "
                    f"'{', '.join(targets)}' - empty demux input")
            lines.append(todo)
            tc.todos.append(todo)
        return lines

    if isinstance(assign.rvalue, AssignNode):
        inner_lines = _gen_assign(assign.rvalue, tc, cfg)
        lines.extend(inner_lines)
        inner_targets = [o for o in assign.rvalue.outputs if not o.is_empty]
        outer_targets = [o for o in assign.outputs if not o.is_empty]
        if inner_targets and outer_targets:
            for ot in outer_targets:
                lines.append(f"{ot.name} := {inner_targets[0].name};")
        elif outer_targets:
            for ot in outer_targets:
                todo = (f"// TODO [FBD Migration]: Chained assignment for '{ot.name}' "
                        f"- inner assign has no resolvable output")
                lines.append(todo)
                tc.todos.append(todo)
        return lines

    if isinstance(assign.rvalue, BoxNode) and assign.rvalue.call_type in FB_CALL_TYPES:
        hoisted: List[str] = []
        box = assign.rvalue
        assign_targets = [o for o in assign.outputs if not o.is_empty]
        fb_out_names = box.output_param_names
        fb_out_types = box.output_param_types
        null_idx = next((i for i, o in enumerate(box.output_items) if o.is_null), 0)
        assign_out_param = fb_out_names[null_idx] if null_idx < len(fb_out_names) else (
            fb_out_names[0] if fb_out_names else "")
        negated = bool(assign.flags & 1)

        inst_name = (box.box_type if box.call_type in ("Function", "Program", "Method")
                     else (box.instance.name if box.instance else ""))

        param_targets: Dict[str, List[Tuple[str, str, bool]]] = {}

        for i, out_op in enumerate(box.output_items):
            if not out_op.is_empty and i < len(fb_out_names) and fb_out_names[i]:
                param_targets.setdefault(fb_out_names[i], []).append(
                    (out_op.name, out_op.type_str, False))

        if assign_out_param:
            for out_op in assign_targets:
                param_targets.setdefault(assign_out_param, []).append(
                    (out_op.name, out_op.type_str, negated))

        inline_outs: List[Tuple[str, str, str]] = []
        post_call_lines: List[str] = []

        for pname, targets in param_targets.items():
            p_idx = next((j for j, n in enumerate(fb_out_names) if n == pname), -1)
            p_type = fb_out_types[p_idx] if 0 <= p_idx < len(fb_out_types) else ""

            if len(targets) == 1 and not targets[0][2]:
                target, t_type, _ = targets[0]
                if p_type and t_type and _check_type_mismatch(p_type, t_type):
                    inline_outs.append((pname,
                        f"{target} (* TYPE MISMATCH: {p_type} -> {t_type} *)", ""))
                else:
                    inline_outs.append((pname, target, t_type))
            else:
                for target, t_type, is_neg in targets:
                    neg_prefix = "NOT " if is_neg else ""
                    if p_type and t_type and _check_type_mismatch(p_type, t_type):
                        post_call_lines.append(
                            f"{target} := {neg_prefix}{inst_name}.{pname}; "
                            f"(* TYPE MISMATCH: {p_type} -> {t_type} *)")
                    else:
                        post_call_lines.append(
                            f"{target} := {neg_prefix}{inst_name}.{pname};")

        fb_lines = _gen_fb_call(box, tc, cfg, hoisted, inline_outs,
                                skip_output_items=True)
        lines.extend(hoisted)
        lines.extend(fb_lines)
        if post_call_lines:
            lines.append("")
            lines.append(f"(* {inst_name} output mappings *)")
            lines.extend(post_call_lines)
        return lines

    hoisted: List[str] = []
    rvalue_expr = _gen_expression(assign.rvalue, tc, cfg, hoisted)
    rvalue_expr = _clean_bool_expr(rvalue_expr)
    if assign.flags & 1 and rvalue_expr:
        if " " in rvalue_expr and not rvalue_expr.startswith("("):
            rvalue_expr = f"NOT ({rvalue_expr})"
        else:
            rvalue_expr = f"NOT {rvalue_expr}"
    lines.extend(hoisted)
    targets = [o for o in assign.outputs if not o.is_empty]
    if not rvalue_expr or rvalue_expr.strip() == "":
        for target in targets:
            todo = (f"// TODO [FBD Migration]: Empty RValue for '{target.name}'"
                    f" - verify assignment source in original FBD")
            lines.append(todo)
            tc.todos.append(todo)
    else:
        for target in targets:
            lines.append(f"{target.name} := {rvalue_expr};")
    return lines


def _gen_top_level_box(box: BoxNode, tc: TcFile, cfg: MigrationConfig) -> List[str]:
    if box.call_type in FB_CALL_TYPES:
        hoisted: List[str] = []
        lines = _gen_fb_call(box, tc, cfg, hoisted)
        result = list(hoisted) + lines
        return result

    if box.call_type == "Action":
        return [f"{box.box_type}();"]

    if box.box_type == "EXECUTE" and box.st_snippet:
        hoisted: List[str] = []
        en_expr = ""
        if box.input_items:
            en_expr = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            en_expr = _clean_bool_expr(en_expr)
        lines = list(hoisted)
        if en_expr and en_expr.upper() not in ("TRUE", "1"):
            lines.append(f"IF {en_expr} THEN")
            for s in box.st_snippet:
                lines.append(f"    {s}")
            lines.append("END_IF")
        else:
            lines.extend(box.st_snippet)
        return lines

    if box.box_type == "RET" or box.box_type == "RETURN":
        return ["RETURN;"]

    if box.box_type == "JMP":
        label = ""
        if box.output_items:
            for o in box.output_items:
                if not o.is_empty:
                    label = o.name
                    break
        if label:
            todo = f"// TODO [FBD Migration]: JMP {label} - convert jump to IF/ELSE structure"
            tc.todos.append(todo)
            return [todo]
        todo = "// TODO [FBD Migration]: JMP - no label found"
        tc.todos.append(todo)
        return [todo]

    if not box.input_items and box.call_type in ("", "None") and not box.instance:
        return [f"{box.box_type}();"]

    hoisted: List[str] = []
    expr = _gen_expression(box, tc, cfg, hoisted)
    expr = _clean_bool_expr(expr)
    result = list(hoisted)
    outputs = [o for o in box.output_items if not o.is_empty]
    if outputs:
        for o in outputs:
            result.append(f"{o.name} := {expr};")
    elif expr:
        result.append(f"{expr};")
    return result


def _check_type_mismatch(param_type: str, target_type: str) -> bool:
    if not param_type or not target_type:
        return False
    return param_type.upper().strip() != target_type.upper().strip()


def _gen_fb_call(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                 hoisted: List[str],
                 extra_outputs: Optional[List[Tuple[str, str, str]]] = None,
                 skip_output_items: bool = False) -> List[str]:
    if box.call_type in ("Function", "Program", "Method"):
        inst_name = box.box_type
    elif box.instance and box.instance.name:
        inst_name = box.instance.name
    else:
        todo = f"// TODO: FB call without instance for {box.box_type}"
        tc.todos.append(todo)
        return [todo]
    param_names = box.input_param_names
    input_items = box.input_items

    mappings: List[Tuple[str, str, str]] = []
    for i, inp in enumerate(input_items):
        pname = param_names[i] if i < len(param_names) and param_names[i] else ""

        expr = _gen_expression(inp, tc, cfg, hoisted)
        expr = _clean_bool_expr(expr)
        flag = box.input_flags[i] if i < len(box.input_flags) else 0
        expr = _apply_input_flag(expr, flag, box, i, tc, hoisted)
        if not expr:
            continue
        if _is_default_skip(expr, pname, inp):
            continue
        mappings.append((pname, ":=", expr))

    out_names = box.output_param_names
    out_types = box.output_param_types
    if not skip_output_items:
        out_items = box.output_items
        for i, out_op in enumerate(out_items):
            if not out_op.is_empty and i < len(out_names) and out_names[i]:
                p_type = out_types[i] if i < len(out_types) else ""
                t_type = out_op.type_str
                if _check_type_mismatch(p_type, t_type):
                    mappings.append((out_names[i], "=>",
                                     f"{out_op.name} (* TYPE MISMATCH: {p_type} -> {t_type} *)"))
                else:
                    mappings.append((out_names[i], "=>", out_op.name))

    if extra_outputs:
        for pname, target, t_type in extra_outputs:
            p_idx = next((j for j, n in enumerate(out_names) if n == pname), -1)
            p_type = out_types[p_idx] if 0 <= p_idx < len(out_types) else ""
            if p_type and t_type and _check_type_mismatch(p_type, t_type):
                mappings.append((pname, "=>",
                                 f"{target} (* TYPE MISMATCH: {p_type} -> {t_type} *)"))
            else:
                mappings.append((pname, "=>", target))

    if not mappings:
        return [f"{inst_name}();"]

    indent = "    "
    lines = [f"{inst_name}("]
    for i, (pname, op, val) in enumerate(mappings):
        if pname:
            param_str = f"{indent}{pname} {op} {val}"
        else:
            param_str = f"{indent}{val}"
        if i < len(mappings) - 1:
            lines.append(f"{param_str},")
        else:
            lines.append(f"{param_str});")
    return lines


def _gen_function_call_expr(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                            hoisted: List[str]) -> str:
    func_name = box.box_type
    param_names = box.input_param_names
    indent = "        "

    mappings: List[Tuple[str, str]] = []
    for i, inp in enumerate(box.input_items):
        pname = param_names[i] if i < len(param_names) and param_names[i] else ""
        expr = _gen_expression(inp, tc, cfg, hoisted)
        expr = _clean_bool_expr(expr)
        flag = box.input_flags[i] if i < len(box.input_flags) else 0
        expr = _apply_input_flag(expr, flag, box, i, tc, hoisted)
        if not expr:
            continue
        if _is_default_skip(expr, pname, inp):
            continue
        mappings.append((pname, expr))

    if not mappings:
        return f"{func_name}()"

    named = [(n, v) for n, v in mappings if n]
    positional = [v for n, v in mappings if not n]

    if not named:
        return f"{func_name}({', '.join(positional)})"

    parts: List[str] = []
    for v in positional:
        parts.append(f"{indent}{v}")
    for n, v in named:
        parts.append(f"{indent}{n} := {v}")

    inner = ",\n".join(parts)
    return f"{func_name}(\n{inner})"


def _is_default_skip(expr: str, pname: str, inp) -> bool:
    if isinstance(inp, OperandNode) and inp.is_empty:
        return True
    if not expr or expr == "":
        return True
    return False


def _gen_expression(node: Union[BoxNode, OperandNode, AssignNode, None], tc: TcFile,
                    cfg: MigrationConfig, hoisted: List[str]) -> str:
    if node is None:
        return ""

    if isinstance(node, OperandNode):
        if node.is_empty:
            return ""
        return node.name

    if isinstance(node, AssignNode):
        assign_lines = _gen_assign(node, tc, cfg)
        hoisted.extend(assign_lines)
        targets = [o for o in node.outputs if not o.is_empty]
        if targets:
            return targets[0].name
        return ""

    if isinstance(node, BoxNode) and node.box_type == "EXECUTE" and node.st_snippet:
        hoisted.extend(node.st_snippet)
        return ""

    box = node

    if box.call_type in INFIX_OPERATORS:
        return _gen_bool_expression(box, tc, cfg, hoisted)

    if box.call_type == "Not" or box.box_type == "NOT":
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            if " " in inner and not inner.startswith("("):
                return f"NOT ({inner})"
            return f"NOT {inner}"
        return "NOT ???"

    op_str = COMPARISON_OPS.get(box.box_type)
    if op_str:
        expr = _gen_infix_op(box, op_str, tc, cfg, hoisted)
        return f"({expr})" if expr else expr

    op_str = ARITHMETIC_OPS.get(box.box_type)
    if op_str:
        return _gen_infix_op(box, op_str, tc, cfg, hoisted)

    if box.box_type.upper() in CONVERSION_FUNCS or box.box_type.upper().startswith("TO_"):
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            return f"{box.box_type}({inner})"
        return f"{box.box_type}()"

    if box.box_type == "SEL":
        return _gen_sel(box, tc, cfg, hoisted)

    if box.box_type.upper() in IEC_FUNCTIONS:
        return _gen_iec_func(box, tc, cfg, hoisted)

    if box.box_type in ("MOVE", "ASSIGN"):
        if box.input_items:
            return _gen_expression(box.input_items[0], tc, cfg, hoisted)
        return ""

    if box.box_type == "JMP":
        label = ""
        if box.input_items:
            label = _gen_expression(box.input_items[0], tc, cfg, hoisted)
        if not label and box.output_items:
            for o in box.output_items:
                if not o.is_empty:
                    label = o.name
                    break
        if label:
            return f"(* TODO [FBD Migration]: JMP {label} - verify jump target *)"
        return "(* TODO [FBD Migration]: JMP - no label found *)"

    if box.box_type == "RET" or box.box_type == "RETURN":
        return "RETURN"

    if box.call_type in FB_CALL_TYPES:
        return _gen_fb_inline_expr(box, tc, cfg, hoisted)

    if box.call_type == "Action":
        return box.box_type

    if box.call_type == "Operator":
        return _gen_operator_call(box, tc, cfg, hoisted)

    if box.call_type == "Conversion":
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            return f"{box.box_type}({inner})"
        return f"{box.box_type}()"

    if box.box_type and box.input_items:
        return _gen_unknown_box(box, tc, cfg, hoisted)

    if box.box_type and not box.input_items and box.call_type in ("", "None"):
        return f"{box.box_type}()"

    if box.box_type:
        todo = f"(* TODO: Unknown box type '{box.box_type}' call_type='{box.call_type}' *)"
        tc.todos.append(todo)
        if cfg.mark_todo:
            return todo
        return f"{box.box_type}()"

    return ""


def _is_fully_wrapped(expr: str) -> bool:
    """Return True only if the outermost parens span the entire expression."""
    if not expr.startswith("("):
        return False
    depth = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth == 0:
            return i == len(expr) - 1
    return False


def _gen_bool_expression(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                         hoisted: List[str]) -> str:
    op_word = INFIX_OPERATORS.get(box.call_type, "AND")
    parts: List[str] = []
    for i, inp in enumerate(box.input_items):
        expr = _gen_expression(inp, tc, cfg, hoisted)
        if not expr:
            continue
        flag = box.input_flags[i] if i < len(box.input_flags) else 0
        expr = _apply_input_flag(expr, flag, box, i, tc, hoisted)
        parts.append(expr)

    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]

    needs_parens = any(" OR " in p or " AND " in p or " XOR " in p for p in parts)
    if needs_parens:
        wrapped = []
        for p in parts:
            if (" OR " in p or " AND " in p or " XOR " in p) and not _is_fully_wrapped(p):
                wrapped.append(f"({p})")
            else:
                wrapped.append(p)
        parts = wrapped

    return f" {op_word} ".join(parts)


def _gen_infix_op(box: BoxNode, op: str, tc: TcFile, cfg: MigrationConfig,
                  hoisted: List[str]) -> str:
    exprs = []
    for inp in box.input_items:
        e = _gen_expression(inp, tc, cfg, hoisted)
        if e:
            exprs.append(e)
    if len(exprs) == 2:
        return f"{exprs[0]} {op} {exprs[1]}"
    if len(exprs) == 1:
        return exprs[0]
    return f" {op} ".join(exprs)


def _gen_sel(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
             hoisted: List[str]) -> str:
    exprs = [_gen_expression(inp, tc, cfg, hoisted) for inp in box.input_items]
    while len(exprs) < 3:
        exprs.append("???")
    if exprs[1].upper() == "FALSE" and exprs[2].upper() == "TRUE":
        return exprs[0]
    if exprs[1].upper() == "TRUE" and exprs[2].upper() == "FALSE":
        if " " in exprs[0] and not exprs[0].startswith("("):
            return f"NOT ({exprs[0]})"
        return f"NOT {exprs[0]}"
    return f"SEL({exprs[0]}, {exprs[1]}, {exprs[2]})"


def _gen_iec_func(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                  hoisted: List[str]) -> str:
    exprs = []
    for inp in box.input_items:
        e = _gen_expression(inp, tc, cfg, hoisted)
        if e:
            exprs.append(e)
    args = ", ".join(exprs)
    return f"{box.box_type}({args})"


def _gen_fb_inline_expr(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                        hoisted: List[str]) -> str:
    """Hoist nested FB call or inline function call, return expression reference."""
    if box.call_type in ("Function", "Program", "Method"):
        return _gen_function_call_expr(box, tc, cfg, hoisted)
    if not box.instance or not box.instance.name:
        todo = f"(* TODO [FBD Migration]: FB call without instance: {box.box_type} *)"
        tc.todos.append(todo)
        return todo

    inst = box.instance.name
    fb_lines = _gen_fb_call(box, tc, cfg, hoisted)
    hoisted.extend(fb_lines)

    out_names = box.output_param_names
    if out_names and out_names[0]:
        return f"{inst}.{out_names[0]}"
    return inst


def _gen_operator_call(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                       hoisted: List[str]) -> str:
    op_str = COMPARISON_OPS.get(box.box_type)
    if op_str:
        expr = _gen_infix_op(box, op_str, tc, cfg, hoisted)
        return f"({expr})" if expr else expr
    op_str = ARITHMETIC_OPS.get(box.box_type)
    if op_str:
        return _gen_infix_op(box, op_str, tc, cfg, hoisted)

    if box.box_type.upper() in CONVERSION_FUNCS:
        if box.input_items:
            inner = _gen_expression(box.input_items[0], tc, cfg, hoisted)
            return f"{box.box_type}({inner})"

    if box.box_type.upper() in IEC_FUNCTIONS:
        return _gen_iec_func(box, tc, cfg, hoisted)

    if box.input_items:
        exprs = []
        for inp in box.input_items:
            e = _gen_expression(inp, tc, cfg, hoisted)
            if e:
                exprs.append(e)
        args = ", ".join(exprs)
        return f"{box.box_type}({args})"
    return f"{box.box_type}()"


def _gen_unknown_box(box: BoxNode, tc: TcFile, cfg: MigrationConfig,
                     hoisted: List[str]) -> str:
    if box.instance:
        inst = box.instance.name
        param_names = box.input_param_names
        parts = []
        for i, inp in enumerate(box.input_items):
            expr = _gen_expression(inp, tc, cfg, hoisted)
            if not expr:
                continue
            if i < len(param_names) and param_names[i]:
                parts.append(f"{param_names[i]} := {expr}")
            else:
                parts.append(expr)
        if parts:
            args = ", ".join(parts)
            return f"(* {inst}({args}) *)"
        return f"(* {inst}() *)"

    exprs = []
    for inp in box.input_items:
        e = _gen_expression(inp, tc, cfg, hoisted)
        if e:
            exprs.append(e)
    args = ", ".join(exprs)
    todo = f"(* TODO: {box.box_type}({args}) *)"
    tc.todos.append(todo)
    return todo
