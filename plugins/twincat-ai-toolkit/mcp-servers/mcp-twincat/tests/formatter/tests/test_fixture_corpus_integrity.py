"""Comprehensive raw corpus formatter integrity test.

Tests ALL files under ``fixtures/raw/`` with syntax token integrity,
XML well-formedness, and idempotency checks.
1. Syntax integrity check (ST structure before/after must match)
2. XML well-formedness (parseable before/after)
3. Idempotency (format twice = same result)
4. No data loss (all identifiers, keywords, values preserved)

The syntax check validates that formatting NEVER introduces or removes:
- Keywords (IF, THEN, END_IF, VAR, etc.)
- Identifiers (variable names, FB names)
- Operators (:=, =>, etc.)
- Semicolons
- String literals
- Numeric values
"""
import sys
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter

_MCP_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_MCP_ROOT))

from formatter.config import load_config
from formatter.file_processor import process_file
from formatter.st_formatter import format_st_code
from formatter.st_alignment import align_declarations, align_assignments, align_fb_call_params
from formatter.st_line_wrapper import wrap_long_lines
from formatter.utils import safe_read_file, compute_sha256

TC3_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
CONFIG = load_config()

# Patterns for syntax token extraction
_RE_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_RE_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.DOTALL)
_RE_LINE_COMMENT = re.compile(r"//[^\n]*")
_RE_STRING = re.compile(r"'[^'\r\n]*'|\"[^\"\r\n]*\"")
_RE_PRAGMA = re.compile(r"\{[^}\r\n]*\}")
_RE_IDENTIFIER = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_RE_NUMBER = re.compile(r"\b\d[\d_]*(?:\.[\d_]+)?(?:[eE][+-]?\d+)?\b|16#[0-9A-Fa-f_]+|2#[01_]+|8#[0-7_]+")
_RE_ASSIGN = re.compile(r":=|=>")
_RE_SEMICOLON = re.compile(r";")


def extract_syntax_tokens(cdata: str) -> dict[str, Counter]:
    """Extract syntax-relevant tokens from ST code for comparison.

    Returns counters for identifiers, keywords, numbers, operators, etc.
    This is a LIGHTWEIGHT syntax check - not a full parser, but catches
    any formatting bug that adds/removes/modifies actual code tokens.
    """
    # Strip comments, strings, pragmas (these can have formatting changes)
    code = _RE_BLOCK_COMMENT.sub(" ", cdata)
    code = _RE_LINE_COMMENT.sub(" ", code)
    # Preserve string values for comparison
    strings = _RE_STRING.findall(cdata)
    code = _RE_STRING.sub(" ", code)
    pragmas = _RE_PRAGMA.findall(cdata)
    code = _RE_PRAGMA.sub(" ", code)

    identifiers = _RE_IDENTIFIER.findall(code)
    numbers = _RE_NUMBER.findall(code)
    assigns = _RE_ASSIGN.findall(code)
    semicolons = _RE_SEMICOLON.findall(code)

    return {
        "identifiers": Counter(w.upper() for w in identifiers),
        "numbers": Counter(numbers),
        "assigns": Counter(assigns),
        "semicolons": Counter(semicolons),
        "strings": Counter(strings),
        "pragmas": Counter(pragmas),
    }


def compare_tokens(before: dict[str, Counter], after: dict[str, Counter]) -> list[str]:
    """Compare token sets, return list of differences."""
    errors = []
    for category in before:
        b = before[category]
        a = after[category]
        added = a - b
        removed = b - a
        if added:
            top = list(added.most_common(3))
            errors.append(f"  ADDED {category}: {top}")
        if removed:
            top = list(removed.most_common(3))
            errors.append(f"  REMOVED {category}: {top}")
    return errors


def check_xml_wellformed(text: str) -> str | None:
    """Check if the formatted text is valid XML. Returns error or None."""
    try:
        ET.fromstring(text)
        return None
    except ET.ParseError as e:
        return str(e)


def run_full_test():
    """Run comprehensive test on all Tc3_EB_BA files."""
    if not TC3_DIR.exists():
        print(f"ERROR: {TC3_DIR} not found")
        return False

    all_files = sorted(
        f for f in TC3_DIR.rglob("*")
        if f.suffix.lower() in (".tcpou", ".tcdut", ".tcgvl", ".tcio")
    )
    print(f"Testing {len(all_files)} files from raw fixture corpus")
    print("=" * 70)

    stats = {
        "total": len(all_files),
        "passed": 0,
        "syntax_error": 0,
        "xml_error": 0,
        "idempotency_error": 0,
        "format_error": 0,
        "unchanged": 0,
        "formatted": 0,
    }
    errors: list[tuple[str, str]] = []

    for i, filepath in enumerate(all_files):
        name = filepath.relative_to(TC3_DIR)

        # Read original
        try:
            raw_bytes, encoding = safe_read_file(str(filepath))
            original_text = raw_bytes.decode(encoding)
        except Exception as e:
            errors.append((str(name), f"Read error: {e}"))
            stats["format_error"] += 1
            continue

        # Extract CDATA blocks from original
        original_cdatas = _RE_CDATA.findall(original_text)
        original_tokens = {}
        for idx, cdata in enumerate(original_cdatas):
            if cdata.strip():
                original_tokens[idx] = extract_syntax_tokens(cdata)

        # Check original XML is well-formed
        xml_err = check_xml_wellformed(original_text)
        if xml_err:
            errors.append((str(name), f"Original XML invalid: {xml_err}"))
            stats["xml_error"] += 1
            continue

        # Format the file (in-memory via dry_run)
        result = process_file(str(filepath), CONFIG, dry_run=True, sort_xml=False, validate=False)

        if not result.success:
            errors.append((str(name), f"Format failed: {result.errors}"))
            stats["format_error"] += 1
            continue

        if not result.changed:
            stats["unchanged"] += 1
            stats["passed"] += 1
            continue

        stats["formatted"] += 1

        # Get formatted text by re-reading + formatting (non-dry for content)
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp()) / filepath.name
        shutil.copy2(str(filepath), str(tmp))
        process_file(str(tmp), CONFIG, dry_run=False, sort_xml=False, validate=False)
        fmt_bytes, fmt_enc = safe_read_file(str(tmp))
        formatted_text = fmt_bytes.decode(fmt_enc)

        # Check 1: XML well-formedness after format
        xml_err = check_xml_wellformed(formatted_text)
        if xml_err:
            errors.append((str(name), f"Formatted XML invalid: {xml_err}"))
            stats["xml_error"] += 1
            shutil.rmtree(tmp.parent, ignore_errors=True)
            continue

        # Check 2: Syntax token integrity
        formatted_cdatas = _RE_CDATA.findall(formatted_text)
        syntax_ok = True
        for idx, cdata in enumerate(formatted_cdatas):
            if not cdata.strip():
                continue
            if idx in original_tokens:
                after_tokens = extract_syntax_tokens(cdata)
                diffs = compare_tokens(original_tokens[idx], after_tokens)
                if diffs:
                    errors.append((str(name), f"Syntax tokens changed in CDATA[{idx}]:\n" + "\n".join(diffs)))
                    stats["syntax_error"] += 1
                    syntax_ok = False
                    break

        if not syntax_ok:
            shutil.rmtree(tmp.parent, ignore_errors=True)
            continue

        # Check 3: Idempotency (format again, must be unchanged)
        result2 = process_file(str(tmp), CONFIG, dry_run=True, sort_xml=False, validate=False)
        if result2.changed:
            errors.append((str(name), "NOT IDEMPOTENT: formatting twice produces different output"))
            stats["idempotency_error"] += 1
            shutil.rmtree(tmp.parent, ignore_errors=True)
            continue

        stats["passed"] += 1
        shutil.rmtree(tmp.parent, ignore_errors=True)

        # Progress
        if (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(all_files)} processed")

    # Report
    print(f"\n{'=' * 70}")
    print(f"RESULTS: {stats['total']} files tested")
    print(f"{'=' * 70}")
    print(f"  Passed:             {stats['passed']}")
    print(f"  Unchanged:          {stats['unchanged']}")
    print(f"  Formatted+OK:       {stats['formatted'] - stats['syntax_error'] - stats['xml_error'] - stats['idempotency_error']}")
    print(f"  Syntax errors:      {stats['syntax_error']}")
    print(f"  XML errors:         {stats['xml_error']}")
    print(f"  Idempotency errors: {stats['idempotency_error']}")
    print(f"  Format errors:      {stats['format_error']}")

    if errors:
        print(f"\n{'─' * 70}")
        print(f"ERRORS ({len(errors)}):")
        print(f"{'─' * 70}")
        for name, err in errors[:20]:
            print(f"\n  {name}:")
            for line in err.split("\n"):
                print(f"    {line}")
            if len(errors) > 20:
                print(f"\n  ... +{len(errors) - 20} more errors")

    print(f"\n{'=' * 70}")
    if errors:
        print("STATUS: FAILED")
    else:
        print("STATUS: ALL PASSED")
    print(f"{'=' * 70}")

    return len(errors) == 0


if __name__ == "__main__":
    success = run_full_test()
    sys.exit(0 if success else 1)
