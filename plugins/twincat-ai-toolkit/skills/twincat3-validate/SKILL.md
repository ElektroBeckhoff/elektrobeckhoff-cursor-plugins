---
name: twincat3-validate
description: >-
  Validate a TwinCAT3 PLC project using MCP build automation. Covers opening
  the solution, running CheckAllObjects, reading errors, interpreting results,
  and the fix-recheck cycle. Use after editing .TcPOU / .TcDUT / .TcGVL files,
  when asked to compile, validate, or check for errors.
---

# Validate TwinCAT3 Project

## Quick Start

```
Task Progress:
- [ ] Step 1: Find .plcproj path in workspace
- [ ] Step 2: Open solution with twincat_open
- [ ] Step 3: Run twincat_check_all_objects (returns errors automatically)
- [ ] Step 4: Interpret results
- [ ] Step 5: Fix errors and re-check (loop)
```

## Step 1: Find .plcproj Path

Search the workspace for `.plcproj` files. Exclude `Samples_/`, `Versions/`, `_Libraries/`:

```
Glob: **/*.plcproj
```

Pick the **library project** `.plcproj` (not samples). Example:
```
Tc3_MyLib/Tc3_MyLib/Tc3_MyLib/Tc3_MyLib.plcproj
```

> **CRITICAL:** Always pass the explicit `plcproj_path` to `twincat_open`. Never rely on auto-detect — it searches from the plugin cache and may find wrong projects.

## Step 2: Open Solution

```
twincat_open(plcproj_path="<full path to .plcproj>")
```

The tool automatically:
- Finds the `.sln` file near the `.plcproj`
- Reads the PLC project name from `.plcproj` XML
- Attaches to a running XAE if the correct solution is already open
- Starts a separate XAE instance if a different solution is open (user's work stays untouched)

**Verify response:** `success: true` and `plc_project_name` matches expected name.

## Step 3: Run CheckAllObjects

```
twincat_check_all_objects()
```

This is the **primary validation tool for library projects**. It compiles ALL objects in the PLC project — not just those referenced from MAIN. A normal `twincat_build` would miss errors in unreferenced POUs.

`CheckAllObjects` re-reads files from disk. No `twincat_reload` needed after editing `.TcPOU` / `.TcDUT` / `.TcGVL` content.

**No separate `twincat_get_output_log()` call needed** — the response already includes all errors, warnings, and infos.

## Step 4: Interpret Results

The response contains:

| Field | Content |
|-------|---------|
| `success` | `true` if 0 errors |
| `error_count` | Number of **errors** only |
| `errors[]` | Compile errors with `file_name`, `line`, `description` |
| `warnings[]` | Compiler warnings with `file_name`, `line`, `description` |
| `infos[]` | Build messages (memory sizes, compile summary) |

### Interpreting Results

**0 errors** = project compiles successfully. Warnings are informational.

**Errors present** = fix the source files and re-check. Each error entry contains:
- `file_name`: Full path to the `.TcPOU` / `.TcDUT` / `.TcGVL` file
- `line`: Line number within the ST code section (not the XML line)
- `description`: Error message from the TwinCAT compiler

### Common Error Patterns

| Error | Cause | Fix |
|-------|-------|-----|
| `Unknown type: 'X'` | Undeclared type in VAR block | Check spelling, add missing DUT/reference |
| `Cannot convert type 'X' to type 'Y'` | Type mismatch | Add explicit conversion: `TO_INT()`, `TO_REAL()` |
| `Variable 'X' not found` | Undeclared variable | Add to VAR block or check scope |
| `'X' is not a member of 'Y'` | Wrong property/method name | Check FB interface |

## Step 5: Fix and Re-check

For each error:
1. Read the file at the reported path
2. Fix the ST code at the reported line
3. After fixing all errors: re-run `twincat_check_all_objects`
4. Repeat until `count: 0`

## Session Handling

Do **not** call `twincat_close()` after validation. Leave the XAE session open — it will be reused by subsequent `twincat_open` calls automatically. Starting XAE is slow (~10-30 s), so keeping it alive saves significant time.

Only use `twincat_close()` if XAE is completely unresponsive or the user explicitly asks to close it.

## When to Use twincat_reload

`twincat_reload` is only needed after **structural** changes:

| Change | Reload needed? |
|--------|---------------|
| Edited code in `.TcPOU` / `.TcDUT` / `.TcGVL` | No |
| Added/removed files in `.plcproj` | **Yes** |
| Changed version in `.plcproj` | **Yes** |
| Modified `.tsproj` configuration | **Yes** |
| Added library reference in `.plcproj` | **Yes** |

After `twincat_reload`, re-run `twincat_check_all_objects` to validate.

## When to Use twincat_build Instead

| Scenario | Tool |
|----------|------|
| Library project (compile all objects) | `twincat_check_all_objects` |
| Application project (build executable) | `twincat_build` |
| Quick syntax check | `twincat_check_all_objects` |
| Full rebuild with boot project | `twincat_build` |
