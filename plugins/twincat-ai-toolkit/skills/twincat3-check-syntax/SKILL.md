---
name: twincat3-check-syntax
description: >-
  Fast headless TwinCAT3 Structured Text syntax and semantic validation using
  twincat_check_syntax (MCP). No XAE/COM required. Checks declarations, statements,
  expressions, and semantic type compatibility in milliseconds. Use after editing
  PLC files, before committing, or when asked to check syntax.
---

# Fast TwinCAT3 Syntax & Semantic Check (MCP)

The `twincat_check_syntax` tool provides millisecond-speed, headless validation for IEC 61131-3 Structured Text files using `twincat_core`. It runs cross-platform without needing Visual Studio or a running TwinCAT runtime.

## Quick Start

```
Task Progress:
- [ ] Step 1: Identify target file, folder, or project
- [ ] Step 2: Run twincat_check_syntax
- [ ] Step 3: Inspect error_count, warning_count, and diagnostics[]
- [ ] Step 4: Fix any detected issues and re-verify
```

## When to use `twincat_check_syntax` vs `twincat_check_all_objects`

| Criterion | `twincat_check_syntax` (Fast-Path) | `twincat_check_all_objects` (Full-Path) |
|-----------|-----------------------------------|------------------------------------------|
| **Speed** | 10–50 ms | 10–30 s |
| **Prerequisites** | None (pure Python / cross-platform) | Windows + Visual Studio / TcXaeShell |
| **Ideal for** | Post-edit checks, pre-commit loops, headless CI | Final ship gate, official library exports |

## Step 1: Choose scope and parameters

| Scope | Tool Call |
|-------|-----------|
| Auto-detect current project | `twincat_check_syntax()` |
| Single file | `twincat_check_syntax(path="POUs/FB_Motor.TcPOU")` |
| Directory (recursive) | `twincat_check_syntax(path="POUs/", recursive=true)` |
| Solution / PLC Project | `twincat_check_syntax(path="MySolution.sln")` |
| Errors only (ignore warnings) | `twincat_check_syntax(include_warnings=false)` |

## Step 2: Interpreting Diagnostics

The response contains a structured JSON payload:

```json
{
  "success": true,
  "total_files": 5,
  "error_count": 0,
  "warning_count": 1,
  "diagnostics": [
    {
      "file": "FB_Motor.TcPOU",
      "path": "c:/repo/POUs/FB_Motor.TcPOU",
      "line": 42,
      "column": 5,
      "severity": "warning",
      "code": "TC-SEM-007",
      "message": "Implicit conversion from 'DINT' to 'INT': possible loss of data"
    }
  ]
}
```

- If `error_count > 0`, `success` is `false`. Investigate and resolve all errors.
- If `warning_count > 0`, review narrowing conversions (`TC-SEM-007`) to ensure intentional type casting.

## Step 3: Diagnostic Codes Quick Reference

- **`TC-DECL-001`**: `FUNCTION` lacks explicit return type.
- **`TC-DECL-002`**: `PROPERTY` lacks data type.
- **`TC-DECL-003`**: `CONSTANT` missing initial value.
- **`TC-DECL-004`**: `VAR_IN_OUT` cannot have initial value.
- **`TC-DECL-005`**: `VAR_TEMP` cannot be `RETAIN` or `PERSISTENT`.
- **`TC-DECL-007`**: Invalid array bounds (`ARRAY[10..2]`).
- **`TC-STMT-001` / `002`**: `EXIT` or `CONTINUE` outside a loop.
- **`TC-STMT-004`**: Jump to undefined label (`JMP`).
- **`TC-EXPR-002`**: Invalid assignment target.
- **`TC-SEM-001`**: Unknown data type.
- **`TC-SEM-002`**: Duplicate variable or method name.
- **`TC-SEM-003`**: Missing interface method or property implementation.
- **`TC-SEM-004`**: Cyclic inheritance.
- **`TC-SEM-005`**: Instantiating an `ABSTRACT FUNCTION_BLOCK`.
- **`TC-SEM-006`**: Type mismatch error in assignment or condition.
- **`TC-SEM-007`**: Implicit narrowing / precision loss warning.
