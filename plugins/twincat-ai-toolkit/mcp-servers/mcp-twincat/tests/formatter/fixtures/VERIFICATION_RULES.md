# TwinCAT 3 Formatter Fixtures & Canonical Verification Rules

This document defines the architecture, standard operating procedures, and 1:1 verification rules for the TwinCAT 3 IEC 61131-3 Structured Text (ST) Formatter test fixtures.

---

## 1. Fixture Architecture Overview

The test fixture directory contains three synchronized folder structures under `fixtures/`:

```
fixtures/
├── raw/       <-- Unformatted / input TwinCAT 3 files (.TcPOU, .TcDUT, .TcGVL, .TcIO)
├── golden/    <-- Canonical reference formatted files (100% byte-exact standard)
└── oneline/   <-- Maximally compressed 1-line stress tests (generated automatically)
```

Each folder contains identical relative file paths categorized under:
- `samples/`: Complex real-world and large-scale industrial control POU/DUT/GVL/IO files (>1000 lines, deep nesting, extensive methods/actions/properties).
- `syntax/`: Focused syntax tests covering every IEC 61131-3 and TwinCAT 3 language construct, edge case, pragma, and comment style.

---

## 2. The Golden Standard & 1:1 Byte-Exact Requirement

A golden file (`fixtures/golden/...`) is the **immutable ground truth** for formatting output.

### Invariants:
1. **UTF-8 Encoding**: No Byte Order Mark (BOM).
2. **LF Line Endings**: Normalized Unix line terminators (`\n`).
3. **No Trailing Newline after `</TcPlcObject>`**: Files terminate cleanly on the closing XML tag.
4. **100% Deterministic & Idempotent**: Formatting a golden file produces the exact same bytes (`format(golden) == golden`).
5. **Zero Information Loss**: Comments, pragmas, string literals, expressions, and logic are 100% preserved.

---

## 3. The 4 Verification Gates (`verify_4gate_fixpoint.py`)

Every file in the fixture suite must pass all 4 verification gates without exception:

| Gate | Name | Operation | Requirement |
|:---|:---|:---|:---|
| **Gate 1** | **Raw → Golden** | `format(raw)` | Must be 100% byte-identical to `golden`. |
| **Gate 2** | **Idempotence** | `format(golden)` | Must produce 0 changes (`format(golden) == golden`). |
| **Gate 3** | **Fixpoint Golden** | `format(collapse(golden))` | Collapsing golden to single lines and reformatting must reproduce `golden` byte-identically. |
| **Gate 4** | **Fixpoint Raw** | `format(collapse(raw))` | Collapsing raw to single lines and reformatting must reproduce `golden` byte-identically. |

### Running the Full Fixpoint Suite:
```bash
python tests/formatter/scripts/verify_4gate_fixpoint.py --all
```
**Exit Code 0** and `ALL GATES PASSED` is strictly required.

---

## 4. STweep Integration & Reference Generation

STweep (official TwinCAT 3 formatter extension in TcXaeShell) serves as the reference benchmark:

1. **Deploying to TwinCAT Solution**:
   - Files are synchronized into `solution/twincat3-solution/twincat3-solution/plc-project/` using `twincat_plcproj_sync`.
2. **Compiler Check in XAE**:
   - Every file must compile with **0 errors** via `twincat_check_all_objects` before being accepted into the test suite.
3. **STweep Formatting**:
   - STweep formats files inside Visual Studio / TcXaeShell via DTE automation (`twincat_format_code` / STweep ops).
4. **Python Formatter Superiority Rule**:
   - When the Python formatter applies stricter canonical standardization than STweep (e.g. UPPERCASE keyword normalization, consistent multiline array indentation, safe comparison operator alignment), the Python formatter output is the canonical golden standard.

---

## 5. Workflow: Adding or Updating Test Fixtures

When adding a new fixture or modifying existing ones, follow this mandatory workflow:

1. **Create/Edit the `raw` file**:
   - Place in `fixtures/raw/syntax/` or `fixtures/raw/samples/`.
   - Ensure syntactically valid TwinCAT 3 code.
2. **Verify TwinCAT 3 Syntax**:
   - Copy to the TwinCAT test solution and run `twincat_check_all_objects`.
   - Fix any compiler errors until `errors == 0`.
3. **Format and Generate `golden`**:
   - Format the `raw` file using the Python formatter (or sync from STweep) and write to `fixtures/golden/...`.
4. **Regenerate `oneline` Fixtures**:
   ```bash
   python tests/formatter/scripts/generate_oneline_stress_fixtures.py
   ```
5. **Verify Fixpoint & Pytest**:
   ```bash
   python tests/formatter/scripts/verify_4gate_fixpoint.py --all
   pytest tests/formatter/tests
   ```
   Both commands must pass 100% before committing changes.
