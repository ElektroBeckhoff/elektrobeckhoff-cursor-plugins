---
name: twincat3-format
description: >-
  Format TwinCAT3 Structured Text files using the Python-based formatter (MCP).
  File-based — no XAE/COM required. Covers single file, folder, project, scoped
  regions, and member filtering. Use when asked to format code, run /twincat3-cmd-format,
  or as part of the new-version pipeline.
---

# Format code (Python Formatter via MCP)

The Python formatter operates natively on `twincat_core.xml` (surgical CDATA patching) and `twincat_core.syntax` (lossless tokens and CST). It guarantees idempotency and zero XML restructuring when formatting targeted ST code.

## Quick Start

```
Task Progress:
- [ ] Step 1: Determine scope (file / folder / project / region)
- [ ] Step 2: twincat_format with appropriate parameters
- [ ] Step 3: For large projects: poll twincat_format_progress
- [ ] Step 4: Check result (formatted / unchanged / errors)
- [ ] Step 5: On errors → investigate, fix source, re-run
```

## Step 1: Determine scope

| User intent | Tool call |
|-------------|-----------|
| Format one file | `twincat_format(path="<file>")` |
| Format a folder | `twincat_format(path="<folder>")` |
| Format whole project | `twincat_format(project="<path-to.sln>")` |
| Only declaration | `twincat_format(path="<file>", region="declaration")` |
| Only implementation | `twincat_format(path="<file>", region="implementation")` |
| Only methods | `twincat_format(path="<file>", member_filter="all_methods")` |
| Only actions | `twincat_format(path="<file>", member_filter="all_actions")` |
| Only properties | `twincat_format(path="<file>", member_filter="all_properties")` |
| One specific method | `twincat_format(path="<file>", member="M_Init")` |
| Preview only | Add `dry_run=true` to any call above |
| Validate only | `twincat_format_validate(path="<path>")` |

Default behavior formats **everything** (ST code + XML structure + sorting).

## Step 2: Execute format

```
twincat_format(
  path="POUs/_internal/",     # or project="MyLib.sln"
  recursive=true,             # default
  dry_run=false,              # default
  validate=true,              # default
  format_xml=true,            # default
  sort_elements=false         # default — preserves original order; true = alphabetical sort
)
```

**Scoped formatting** disables XML reformatting automatically (only touches targeted ST regions):
```
twincat_format(path="FB_MyBlock.TcPOU", region="declaration")
```

## Step 3: Poll progress (large projects)

For projects with >50 files, poll progress:
```
twincat_format_progress()
→ { "status": "running", "files_done": 45, "files_total": 200 }
```

Repeat until `status` is `done` or `error`.

## Step 4: Interpret result

```json
{
  "success": true,
  "total": 200,
  "formatted": 15,
  "unchanged": 183,
  "errors": 2,
  "dry_run": false,
  "results": [...]
}
```

| Field | Action |
|-------|--------|
| `formatted > 0` | Files changed on disk — success |
| `unchanged` | Already correctly formatted (idempotent) |
| `errors > 0` | Investigate `results[]` entries with `success=false` |
| `dry_run=true` | Nothing written — preview only |

## Step 5: Error handling

Common error reasons:
- **XML parse error** — malformed XML in source file; fix manually
- **Syntax integrity failed** — formatter would alter token structure; file skipped (safe)
- **Encoding error** — unsupported file encoding

On syntax integrity failures: the formatter **never** writes the file. The source is safe.

## Configuration

Show active configuration (defaults + project `.stformat.json`):
```
twincat_format_config(project_path="<project_root>")
```

Key settings (in `.stformat.json` at project root):
```json
{
  "lineLength": { "wrap_at": 228 },
  "alignment": { "declarations": true, "assignments": true, "fb_call_params": true },
  "calls": { "max_params_single_line": 4, "multiline_indent": 8 },
  "keywords": { "uppercase": true },
  "xml": { "sort_methods": true, "sort_actions": true, "sort_properties": true },
  "safety": { "backup": true, "syntax_check": true }
}
```

Full defaults: `formatter/defaults.json`.

## Disable regions

The formatter respects disable markers within CDATA blocks:

```
(* Code that gets formatted *)
{formatting.disable}
(* This block is never touched *)
{formatting.enable}
(* Formatting resumes here *)
```

Also compatible with STweep markers:
```
{STweep.Disable}
(* Protected region *)
{STweep.Enable}
```

Both attribute-style `{...}` and comment-style `(*...*)`  are supported. Case-insensitive.

## CFC / FBD files

Files with CFC or FBD implementation are handled safely:
- **Formatted:** Declaration (top), ST Methods, ST Properties, ST Actions
- **Never touched:** CFC/FBD Implementation XML

## Validation only

Run XML validation without formatting:
```
twincat_format_validate(path="<path>", recursive=true)
```

Checks:
- Name attribute matches declaration in CDATA
- GUID format and uniqueness
- Required elements present (Declaration, Implementation)
- SpecialFunc values valid
- FolderPath consistency

## Compared to STweep (XAE COM)

| Feature | Python formatter (`twincat_format_*`) | STweep (`twincat_stweep_format_*`) |
|---------|---------------------------------------|-----------------------------------|
| Requires XAE | No | Yes |
| Requires STweep license | No | Yes |
| Format speed | Fast (parallel, file-based) | Slow (sequential, COM per file) |
| XML sorting | Opt-in (`sort_elements=true`) | No |
| XML validation | Yes | No |
| Scoped formatting | Yes (region/member) | No (file/folder only) |
| Dry-run | Yes | No |
| CFC/FBD safe | Yes | Yes |
| Config | `.stformat.json` | STweep settings in XAE |
| Disable regions | `{formatting.disable}` + `{STweep.Disable}` | `{STweep.Disable}` only |

## Related

- Rule: `twincat3-mcp-format` (tool reference)
- Rule: `twincat3-formatting` (style principles)
- Skill: `twincat3-code-style` (quick decision table + references)
- Skill: `twincat3-stweep-format` (STweep via XAE — explicit STweep requests only)
- Command: `/twincat3-cmd-format`
- Skill: `twincat3-new-version` (uses this formatter in Step 3)
- Config reference: `formatter/defaults.json`
