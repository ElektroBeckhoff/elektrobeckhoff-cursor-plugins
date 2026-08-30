"""Comprehensive verification of syntax fixtures against STweep (TcXaeShell) and Python Formatter."""
from __future__ import annotations

import filecmp
import os
import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_MCP_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_MCP_ROOT))
for _sub in ("automation_interface", "plcproj"):
    _p = str(_MCP_ROOT / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from formatter.file_processor import process_file
from formatter.config import load_config
from twincat_plcproj_ops import sync_plcproj, PlcProjConfig
from twincat_automation_interface import TcAutomationInterface

WORKSPACE_ROOT = _MCP_ROOT.parents[3]
SOLUTION_SLN = _MCP_ROOT.parents[1] / "solution" / "twincat3-solution" / "twincat3-solution.sln"
PLC_PROJ_DIR = _MCP_ROOT.parents[1] / "solution" / "twincat3-solution" / "twincat3-solution" / "plc-project"
PLCPROJ_FILE = PLC_PROJ_DIR / "plc-project.plcproj"

RAW_SYNTAX_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures" / "raw" / "syntax"
GOLDEN_SYNTAX_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures" / "golden" / "syntax"
RAW_SAMPLES_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures" / "raw" / "samples"
GOLDEN_SAMPLES_DIR = _MCP_ROOT / "tests" / "formatter" / "fixtures" / "golden" / "samples"


def deploy_fresh_raw_files() -> list[tuple[Path, Path, Path]]:
    """Copy all raw files to plc-project, returning list of (raw_path, plc_path, golden_path)."""
    mapping = []
    GOLDEN_SYNTAX_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    
    for raw_dir, golden_dir in [(RAW_SYNTAX_DIR, GOLDEN_SYNTAX_DIR), (RAW_SAMPLES_DIR, GOLDEN_SAMPLES_DIR)]:
        if not raw_dir.is_dir():
            continue
        for raw_file in sorted(raw_dir.glob("*.*")):
            ext = raw_file.suffix.lower()
            if ext not in (".tcpou", ".tcdut", ".tcgvl", ".tcio"):
                continue
            
            if ext == ".tcpou":
                sub = "POUs"
            elif ext == ".tcdut":
                sub = "DUTs"
            elif ext == ".tcgvl":
                sub = "GVLs"
            elif ext == ".tcio":
                sub = "ITFs"
            else:
                sub = ""
                
            target_dir = PLC_PROJ_DIR / sub if sub else PLC_PROJ_DIR
            target_dir.mkdir(parents=True, exist_ok=True)
            plc_file = target_dir / raw_file.name
            golden_file = golden_dir / raw_file.name
            
            shutil.copy2(raw_file, plc_file)
            mapping.append((raw_file, plc_file, golden_file))
        
    sync_res = sync_plcproj(PlcProjConfig(input_path=str(PLCPROJ_FILE), force=True, backup=False))
    print(f"Deployed {len(mapping)} files to plc-project. Sync: {sync_res.success} ({sync_res.compile_count} items)")
    return mapping


def run_stweep_format_all(mapping: list[tuple[Path, Path, Path]]) -> None:
    """Trigger STweep format via automation bridge and poll until complete."""
    bridge = TcAutomationInterface()
    res_open = bridge.open_solution(str(SOLUTION_SLN), proj_name="plc_project")
    print(f"Bridge open solution: {res_open.success}")
    time.sleep(2)
    
    print("Running STweep format on plc-project...")
    res = bridge.format_code(path=str(PLCPROJ_FILE), confirm=True, wait=False, timeout_s=300)
    print(f"Format job initiated: {res.message}")
    
    while True:
        prog = bridge.get_format_progress()
        print(f"  Progress: {prog.files_done}/{prog.files_total} ({prog.percent}%) - {prog.message}")
        if not prog.running:
            break
        time.sleep(2)
        
    final_res = prog.result
    if final_res:
        failed_items = final_res.get("failed", [])
        print(f"STweep format finished: success={final_res.get('success')}, formatted={len(final_res.get('formatted', []))}, unchanged={len(final_res.get('unchanged', []))}, failed={len(failed_items)}")
        if failed_items:
            print(f"Retrying {len(failed_items)} failed files individually...")
            for fail in failed_items:
                fpath = fail.get("path")
                print(f"  Retrying: {fpath}")
                time.sleep(1)
                r = bridge.format_code(path=fpath, confirm=True, wait=True, timeout_s=30)
                print(f"    -> {r.success}: {r.message}")


def main():
    mapping = deploy_fresh_raw_files()
    run_stweep_format_all(mapping)
    
    print("\n" + "="*80)
    print("STEP 1: Check STweep Output & Synchronize / Verify Golden")
    print("="*80)
    
    stweep_ok = 0
    golden_synced = 0
    
    for raw_path, plc_path, golden_path in mapping:
        stweep_content = plc_path.read_text(encoding="utf-8-sig")
        
        if not golden_path.exists() or "--sync-golden" in sys.argv:
            golden_path.write_text(stweep_content, encoding="utf-8")
            print(f"[SYNCED GOLDEN] {golden_path.name}")
            golden_synced += 1
            stweep_ok += 1
        else:
            golden_content = golden_path.read_text(encoding="utf-8-sig")
            if stweep_content == golden_content:
                stweep_ok += 1
            else:
                print(f"[STWEEP DIFF] {raw_path.name} differs from Golden!")
                from formatter.diff_reporter import generate_diff
                print(generate_diff(raw_path.name, golden_content, stweep_content))
                
    print(f"STweep vs Golden: {stweep_ok} identical")
    
    print("\n" + "="*80)
    print("STEP 2: Format Raw with Python Formatter & Compare to Golden / STweep")
    print("="*80)
    
    formatter_pass = 0
    formatter_fail = 0
    
    cfg = load_config()
    for raw_path, plc_path, golden_path in mapping:
        fmt_res = process_file(raw_path, cfg, dry_run=True)
        if not fmt_res.success:
            print(f"[FAIL] Formatter failed on {raw_path.name}: {fmt_res.errors}")
            formatter_fail += 1
            continue
            
        golden_content = golden_path.read_text(encoding="utf-8-sig")
        
        temp_dir = _MCP_ROOT / "tests" / "formatter" / "_tmp_test"
        temp_dir.mkdir(exist_ok=True)
        temp_file = temp_dir / raw_path.name
        shutil.copy2(raw_path, temp_file)
        
        fmt_write_res = process_file(temp_file, cfg, dry_run=False)
        py_formatted = temp_file.read_text(encoding="utf-8-sig")
        temp_file.unlink()
        
        if py_formatted == golden_content:
            print(f"[MATCH 100%] {raw_path.name} == STweep / Golden")
            formatter_pass += 1
        else:
            print(f"[MISMATCH] {raw_path.name} != Golden")
            from formatter.diff_reporter import generate_diff
            print(generate_diff(raw_path.name, golden_content, py_formatted))
            formatter_fail += 1
            
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass
        
    print("\n" + "="*80)
    print(f"FINAL RESULT: {formatter_pass}/{len(mapping)} PASS, {formatter_fail} FAIL")
    print("="*80)


if __name__ == "__main__":
    main()
