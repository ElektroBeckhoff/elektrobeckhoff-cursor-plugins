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

## Step 1: Find Project Path

Search the workspace for `.plcproj` or `.sln` files:

```
Glob: **/*.plcproj
Glob: **/*.sln
```

> **TIP:** You can pass a `.plcproj`, `.sln`, or a folder to `twincat_open`. The tool resolves everything automatically via XML parsing.

## Step 2: Open Solution

```
twincat_open(path="<path to .plcproj, .sln, or project folder>")
```

The `path` parameter accepts:
- A `.plcproj` → opens directly
- A `.sln` → resolves via .tsproj/.xti XML to the PLC project
- A folder → scans for .sln or .plcproj automatically

If the solution contains multiple PLC projects, the tool returns an error with the list of all available projects and their paths. Pick one and pass the exact `.plcproj` path.

**Verify response:** `success: true`.

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
