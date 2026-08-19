"""One-shot script: migrate raw fixtures -> format -> write golden files.

Run from the mcp-twincat directory:
    python tests/_generate_golden.py
"""
import os
import sys
import shutil
import tempfile

_server_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, _server_dir)
for _sub in ("migrator", "formatter"):
    sys.path.insert(0, os.path.join(_server_dir, _sub))

from pathlib import Path
from migrator.fbd import main as fup_main
from migrator.cfc import main as cfc_main
from formatter.config import load_config
from formatter.file_processor import process_batch

RAW_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
GOLDEN_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "golden"


def _migrate_file(src: Path, dst: Path) -> bool:
    """Run the appropriate migrator on *src*, write output to *dst*."""
    name_lower = src.name.lower()
    if name_lower.startswith("cfc_"):
        main_fn = cfc_main
    elif name_lower.startswith("fbd_"):
        main_fn = fup_main
    else:
        print(f"  SKIP (unknown prefix): {src.name}")
        return False

    argv = [
        "--input", str(src),
        "--output", str(dst),
        "--no-log",
        "--no-report",
        "--no-backup",
    ]
    code = main_fn(argv)
    return code == 0


def _format_file(path: Path) -> bool:
    """Run the ST formatter on a single file.

    Disables syntax_check so the migrator's output (which may have
    an extra or missing semicolon) can still be formatted cleanly.
    The golden file IS the reference, so integrity vs. pre-format
    state is irrelevant here.
    """
    cfg = load_config(project_root=str(path.parent))
    cfg.safety.syntax_check = False
    batch = process_batch(
        [str(path)], cfg,
        dry_run=False,
        validate=True,
        format_st=True,
        format_xml=True,
        sort_xml=False,
        scope=None,
    )
    return batch.errors == 0


def main():
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    raw_files = sorted(RAW_DIR.glob("*.TcPOU"))
    if not raw_files:
        print("No raw fixtures found in", RAW_DIR)
        return

    ok = 0
    fail = 0
    for src in raw_files:
        dst = GOLDEN_DIR / src.name
        print(f"[migrate] {src.name} ... ", end="", flush=True)

        if not _migrate_file(src, dst):
            print("MIGRATION FAILED")
            fail += 1
            continue
        print("OK", flush=True)

        print(f"[format]  {src.name} ... ", end="", flush=True)
        if not _format_file(dst):
            print("FORMAT FAILED")
            fail += 1
            continue
        print("OK", flush=True)
        ok += 1

    print(f"\nDone: {ok} golden files created, {fail} failures.")


if __name__ == "__main__":
    main()
