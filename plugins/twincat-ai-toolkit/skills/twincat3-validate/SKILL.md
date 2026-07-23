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
- [ ] Step 1: Find .sln / .plcproj path (prefer .sln)
- [ ] Step 2: Open solution with twincat_open
- [ ] Step 3: Run twincat_check_all_objects (returns errors automatically)
- [ ] Step 4: Interpret results
- [ ] Step 5: Fix errors and re-check (loop)
```

## Step 1: Find Project Path

Search the workspace for `.sln` or `.plcproj` files (prefer `.sln` when both exist):

```
Glob: **/*.sln
Glob: **/*.plcproj
```

> **TIP:** Pass a `.sln`, `.plcproj`, or folder to `twincat_open`. Prefer `.sln` for reliable attach when multiple XAE windows are open.

## Step 2: Open Solution

```
twincat_open(path="<path to .plcproj, .sln, or project folder>")
```

Prefer a `.sln` path when available — it is the most reliable match when multiple XAE windows are open.

The `path` parameter accepts:
- A `.sln` → resolves via .tsproj/.xti XML to the PLC project (preferred for attach)
- A `.plcproj` → opens / attaches via nearby `.sln`
- A folder → scans for .sln or .plcproj automatically

If the solution contains multiple PLC projects, the tool returns an error with the list of all available projects and their paths. Pick one and pass the exact `.plcproj` path.

### Optional: force XAE shell version

Only when the user asks or a specific TwinCAT build is required:

```
twincat_open(path="<...>", xae_version="4024")   # or "4026" / "15.0" / "17.0"
```

Default (empty): attach to any running instance that already has this solution; if starting new, prefer an already-running shell version, else newest registered.

If the solution is already open in a **different** shell than requested, the tool attaches to the running instance (no second XAE) and reports that version in `xae_version`.

### Verify open response

| Field | Meaning |
|-------|---------|
| `success` | Must be `true` |
| `solution_path` | Loaded `.sln` |
| `created_new_instance` | `true` only if MCP started a new TcXaeShell process; `false` = attached to / reused a running instance |
| `xae_version` | `"4024"` or `"4026"` (empty if ProgID unknown) |
| `xae_prog_id` | e.g. `TcXaeShell.DTE.15.0` |

If the project was already open in XAE and `created_new_instance` is unexpectedly `true`, stop and investigate — do not continue as if the user's existing window was reused.

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
| `warning_count` | Number of warnings |
| `errors[]` | Compile errors with `file_name`, `line`, `description` |
| `warnings[]` | Compiler warnings with `file_name`, `line`, `description` |
| `infos[]` | Build messages (memory sizes, compile summary) |

### Interpreting Results

**0 errors** (`error_count: 0`) = project compiles successfully. Still read `warnings[]`.

**Errors present** = fix the source files and re-check. Each error entry contains:
- `file_name`: Path to the `.TcPOU` / `.TcDUT` / `.TcGVL` (from the Build pane)
- `line`: TwinCAT compiler line number (ST declaration/implementation as reported by XAE — **not** necessarily the XML line in the raw file)
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
4. Repeat until `error_count: 0`

## Session Handling

Do **not** call `twincat_close()` after validation. Leave the XAE session open — the next `twincat_open` finds the matching solution via ROT (even when several XAE windows are open). Starting XAE is slow (~10-30 s), so keeping it alive saves significant time.

Only use `twincat_close()` if XAE is completely unresponsive or the user explicitly asks to close it.

## When to Use twincat_reload

`twincat_reload` is **only** needed after the **`.plcproj`** file was changed (e.g. version bump, added/removed Compile entries, library references, `twincat_plcproj_sync`). Do **not** reload for anything else.

| Change | Reload needed? |
|--------|---------------|
| Edited `.TcPOU` / `.TcDUT` / `.TcGVL` / `.TcIO` content | **No** |
| Any change that does **not** modify `.plcproj` | **No** |
| `.plcproj` edited (manually, sync, version, references, file list) | **Yes** |

After a `.plcproj` change: `twincat_open` (if needed) → `twincat_reload` → `twincat_check_all_objects`.

## When to Use twincat_build Instead

| Scenario | Tool |
|----------|------|
| Library project (compile all objects) | `twincat_check_all_objects` |
| Application / boot project | `twincat_build` (incremental) |
| Clean full rebuild | `twincat_build(full_rebuild=true)` |
| Quick syntax check | `twincat_check_all_objects` |
