---
name: twincat3-stweep-format
description: >-
  Format TwinCAT Structured Text via STweep in TcXaeShell (MCP). Covers
  twincat_open session attach, install/license wizard check, and
  twincat_format_code for file/folder (project only with confirm). Use when
  asked to Format code, run STweep, or /twincat3-cmd-format.
---

# Format ST with STweep (MCP)

## Quick Start

```
Task Progress:
- [ ] Step 1: Resolve .sln / path; twincat_open
- [ ] Step 2: twincat_stweep_status — installed + commands_loaded (no UI)
- [ ] Step 3: twincat_format_code (file/folder; project needs confirm=true)
- [ ] Step 4: Many files → wait=false + poll twincat_format_progress
- [ ] Step 5: To abort → twincat_format_cancel (stops between files)
- [ ] Step 6: Verify disk — require `disk_changed` or accept `files_unchanged` only after git/hash check
- [ ] Step 7: On unlicensed fail-fast → stop; else report files_formatted / unchanged / failed
```

## Step 1: Open the same XAE session

```
twincat_open(path="<sln preferred | plcproj | folder>", xae_version="")
```

Format uses the **same** MCP bridge session as build/check — not “whatever window is focused”. Use `xae_version="4024"` / `"4026"` when multiple shells are open.

## Step 2: Install check (no license window)

```
twincat_stweep_status()
```

| Field | Required |
|-------|----------|
| `installed` | true |
| `commands_loaded` | true |
| `ready` | true |

Default status does **not** open the License wizard. License is verified when formatting: first Formatcode failure with a license error → abort remaining files (`method=unlicensed`).

Optional: `probe_license=true` only if the user wants wizard days/status (visible UI flash). **Never** print activation keys.

## Step 3: Format

**File or small folder (blocking OK):**

```
twincat_format_code(path="<file.TcPOU|folder>")
```

**Many files / whole project (prefer async + poll):**

```
twincat_format_code(path="<folder|project>", confirm=true?, wait=false, timeout_seconds=1800)
# then poll until running=false:
twincat_format_progress()
```

| Progress field | Meaning |
|----------------|---------|
| `running` | job still active |
| `phase` | `starting` / `formatting` / `done` / `error` |
| `files_done` / `files_total` / `percent` | MCP file-count progress |
| `current_file` | path being formatted |
| `result` | final format payload when finished |

STweep may show its own XAE progress UI; MCP does not drive that dialog — it tracks per-file Formatcode. Poll **`twincat_format_progress`** (not `twincat_stweep_status`) while a job runs — status goes through STA and can queue behind format.

Supported: `.TcPOU`, `.TcGVL`, `.TcDUT`, `.TcIO`.

**Whole project (explicit confirm only):**

```
twincat_format_code(path="", confirm=true, wait=false, timeout_seconds=1800)
# or path="<....plcproj>" / project root folder, confirm=true
```

**How it differs from the XAE UI**

| UI (right-click folder in Solution Explorer) | MCP today |
|-----------------------------------------------|-----------|
| One `PlcFolder` / `SPSOrdner.Formatcode` on the selected folder | Walks `.TcPOU`/`.TcGVL`/`.TcDUT`/`.TcIO`, `OpenFile` + editor Formatcode per file, then closes the tab |
| No flood of editor tabs | Was leaving tabs open — now closes after each file |

Reason: `UIHierarchyItem.Select` is broken on TcXaeShell
(`UIHierarchyItemMarshaler.Select` not found), so automation cannot select
the SE folder the way the UI does. Command names still exist:
`PlcFolder.Formatcode` (EN/4024) / `SPSOrdner.Formatcode` (DE/4026).

**Cancel:** `twincat_format_cancel()` while a job runs → stops after the
current file (`phase=canceled`). Prefer `wait=false` so the agent can cancel.

**Settle/save + disk verify:** After Formatcode, MCP holds the Document ref and
saves on first dirty (+~150 ms), then compares a **content fingerprint**.
Saving too late often misses the buffer (ActiveDocument goes away) — that must
not look like a successful format.

Do **not** use STweep.CLI.

## Step 4: Interpret result

| Field | Meaning |
|-------|---------|
| `success` | no hard failures; may still have `files_unchanged` |
| `disk_changed` | at least one file’s on-disk bytes changed |
| `async_started` | background job started (`wait=false`) |
| `files_formatted` | disk actually changed |
| `files_unchanged` / `unchanged[]` | Formatcode ran; never dirty (already OK or silent no-op) |
| `files_failed` / `failed[]` | errors — includes dirty/Save but disk unchanged |
| `license_ok` / `installed` | echoed preflight |

**Agent check:** After format, if `disk_changed=false` (or only `files_unchanged`),
verify with `git diff` / file hash. Do not assume column alignment applied.
On dirty-save failure text: retry once or stop and format in XAE.

## Related

- Rule: `twincat3-mcp-stweep`
- Command: `/twincat3-cmd-format`
- Session/open details: skill `twincat3-validate` (open semantics)
