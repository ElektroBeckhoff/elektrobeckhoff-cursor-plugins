#!/usr/bin/env python3
"""
Universal TwinCAT 3 FBD/FUP to Structured Text (ST) Migration Tool.

Reads .TcPOU files containing FBD (NWL) implementations and converts them
to functionally identical ST code while preserving declarations, comments,
attributes, IDs and project structure.

Usage:
    python twincat_fbd_to_st_migrator.py --input "path/to/File.TcPOU"
    python twincat_fbd_to_st_migrator.py --input "path/to/project" --recursive
    python twincat_fbd_to_st_migrator.py --input "File.TcPOU" --dry-run
    python twincat_fbd_to_st_migrator.py --input "File.TcPOU" --analyze-only
"""

from __future__ import annotations

import datetime
import logging
import re
import shutil
import sys
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# Re-export everything from base so that `import twincat_fbd_to_st_migrator as M`
# continues to expose all IR classes, codegen, helpers, CLI, etc.
from twincat_migrator_base import *  # noqa: F401,F403
from twincat_migrator_base import (
    # IR classes
    ActionInfo, AssignNode, BoxNode, DemuxNode, MigrationConfig,
    MigrationLogger, MigrationReport, NwlNetwork, OperandNode,
    StNetwork, TcFile,
    # Constants
    ARITHMETIC_OPS, COMPARISON_OPS, CONVERSION_FUNCS, FB_CALL_TYPES,
    IEC_FUNCTIONS, INFIX_OPERATORS, SCRIPT_VERSION, SUPPORTED_EXTENSIONS,
    # Public functions
    build_generated_header, calculate_accuracy,
    can_replace, collect_input_files, convert_networks_to_st,
    create_backup, load_config, load_file, parse_arguments,
    validate_generated_st, write_output_file,
    # Private XML helpers
    _detect_impl_type, _detect_pou_type, _find_child_by_name,
    _find_v, _get_v_str, _strip_quotes,
    # Private codegen
    _apply_input_flag, _check_type_mismatch,
    _clean_bool_expr, _collect_vars, _collect_vars_node,
    _final_checklist, _format_call_params,
    _gen_assign, _gen_bool_expression, _gen_expression,
    _gen_fb_call, _gen_fb_inline_expr, _gen_function_call_expr,
    _gen_iec_func, _gen_infix_op, _gen_operator_call, _gen_sel,
    _gen_top_level_box, _gen_unknown_box, _generate_network_code,
    _is_default_skip, _is_fully_wrapped, _is_return_assign,
    # Private pipeline helpers
    _print_analysis, _print_dry_run, _regenerate_guids,
    _resolve_output_path,
)

FBD_SOURCE_TYPE = "FBD/FUP"
FBD_TOOL_NAME = "twincat_fbd_to_st_migrator"


# ---------------------------------------------------------------------------
# NWL parser
# ---------------------------------------------------------------------------

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
    cet_hints = ["BoxTreeBox"]
    for child in element:
        if child.tag == "l2" and child.get("n") == "InputItems":
            return True
    return False


# ---------------------------------------------------------------------------
# XML writer — replace NWL with ST in the .TcPOU
# ---------------------------------------------------------------------------

def _replace_nwl_block(text: str, start_tag: str, st_code: str) -> str:
    """Replace an <Implementation><NWL>...</NWL></Implementation> block following *start_tag*.

    Uses explicit tag boundary search instead of greedy/non-greedy regex,
    which is robust against XML comments and nested elements inside <NWL>.
    """
    anchor = text.find(start_tag)
    if anchor < 0:
        return text

    search_from = anchor + len(start_tag)
    impl_open = text.find("<Implementation>", search_from)
    if impl_open < 0:
        return text

    nwl_open = text.find("<NWL>", impl_open)
    if nwl_open < 0:
        return text

    nwl_close = text.find("</NWL>", nwl_open)
    if nwl_close < 0:
        return text

    impl_close = text.find("</Implementation>", nwl_close)
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


def write_st_to_xml(tc: TcFile, regenerate_ids: bool = False) -> Optional[str]:
    if tc.xml_root is None:
        return None

    raw_text = tc.path.read_text(encoding=tc.encoding)

    if "<POU " not in raw_text and "<POU>" not in raw_text:
        return None
    if "<NWL>" not in raw_text:
        return None

    pou_tag_match = re.search(r'<POU\s[^>]*>', raw_text)
    if not pou_tag_match:
        return None
    pou_tag = pou_tag_match.group(0)

    result = _replace_nwl_block(raw_text, pou_tag, tc.generated_st)
    if result == raw_text:
        return None

    if tc.edge_vars:
        unique_vars = list(dict.fromkeys(tc.edge_vars))
        decl_lines = "\n".join(f"    {name} : {etype};" for name, etype in unique_vars)
        edge_block = (
            "\nVAR\n"
            "    // Auto-generated edge detection instances [FBD Migration]\n"
            f"{decl_lines}\n"
            "END_VAR"
        )
        cdata_open = result.find("<Declaration><![CDATA[")
        if cdata_open >= 0:
            cdata_start = cdata_open + len("<Declaration><![CDATA[")
            cdata_close = result.find("]]></Declaration>", cdata_start)
            if cdata_close >= 0:
                old_decl = result[cdata_start:cdata_close]
                new_decl = old_decl.rstrip() + "\n" + edge_block + "\n"
                result = result[:cdata_start] + new_decl + result[cdata_close:]

    for action in tc.actions:
        if action.st_code and action.name:
            action_tag = f'<Action Name="{action.name}"'
            result = _replace_nwl_block(result, action_tag, action.st_code)

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

    if tc.impl_type != "NWL":
        if tc.impl_type in ("CFC", "SFC", "IL"):
            mlog.log(f"  SKIP: {tc.impl_type} migration not supported")
            tc.warnings.append(f"{tc.impl_type} migration not supported")
        else:
            mlog.log(f"  SKIP: Implementation is {tc.impl_type}, not FBD/NWL")
        return True

    parse_nwl_networks(tc)
    mlog.log(f"  Networks parsed: {len(tc.networks)}")
    for nw in tc.networks:
        mlog.log(f"    Network {nw.index + 1}: {len(nw.items)} items"
                 + (", OutCommented" if nw.out_commented else ""))

    action_nwl_count = sum(1 for a in tc.actions if a.networks)
    if action_nwl_count:
        mlog.log(f"  Actions with NWL: {action_nwl_count}")

    if cfg.analyze_only:
        mlog.log(f"  ANALYZE-ONLY: No ST generation")
        _print_analysis(tc)
        report.add(tc, None, None, False)
        return True

    convert_networks_to_st(tc, cfg)

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

    acc = calculate_accuracy(tc)
    tm_count = tc.generated_st.count("TYPE MISMATCH:")
    header = build_generated_header(FBD_SOURCE_TYPE, tc.path.name, FBD_TOOL_NAME, SCRIPT_VERSION, acc, tm_count)
    tc.generated_st = header + tc.generated_st

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
    xml_content = write_st_to_xml(tc, regenerate_ids=new_file)
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
            backup_path = tc.path.parent / f"{tc.path.stem}_backup_{ts}{tc.path.suffix}"
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
            batch_name = f"{input_p.name}_backup_{ts_batch}"
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
            bkp_name = f"{input_p.name}_backup_{ts_batch}"
            bkp_dir = input_p.parent / bkp_name
            bkp_dir.mkdir(parents=True, exist_ok=True)
            cfg.backup_dir = str(bkp_dir)
    else:
        base_path = input_p.parent if input_p.is_file() else input_p

    mlog = MigrationLogger(cfg.log_enabled, base_path, prefix)
    report = MigrationReport(cfg.report_enabled, base_path, prefix)

    mlog.log(f"TwinCAT FBD-to-ST Migrator v{SCRIPT_VERSION}")
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
