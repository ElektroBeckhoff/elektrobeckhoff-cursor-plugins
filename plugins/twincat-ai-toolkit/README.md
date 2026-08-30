# TwinCAT AI Toolkit

AI rules, skills, commands, agents, and MCP build/runtime tools for **Beckhoff TwinCAT 3** projects in **IEC 61131-3 Structured Text**.

## Architecture

| Layer | Role |
|-------|------|
| **Core Engine** (`twincat_core/`) | Single source of truth: lossless XML & surgical patching, ST Lexer/CST/AST parser, multi-level semantic resolver, project graph & workspace index, LSP server |
| **Rules** (`rules/`) | Lean principles; `alwaysApply` only for core + naming |
| **Examples** (`rules/examples/`) | Heavy ST/XML samples — Read when implementing |
| **Skills** (`skills/`) | Executable workflows; domain detail in `*-patterns.md` / `references/` |
| **Commands** (`commands/`) | Slash entry points (`/twincat3-cmd-*`) with ordered Read-first lists |
| **Agents** (`agents/`) | Specialized readonly subagents (review, audit, debug, …) |
| **MCP** (`mcp-servers/mcp-twincat/`) | TcXaeShell COM automation, offline InfoSys `.mshc`, and tools consuming `twincat_core` |
| **VS Code Extension** (`vscode-extension/`) | Thin client adapter for syntax highlighting and LSP client |

### Token / load design

Only `twincat3-core` and `twincat3-naming` use `alwaysApply: true`. Domain and style rules stay glob/on-demand and are **lean** (principles + tables + pointers). Heavy samples live under `rules/examples/` or skill `references/` / `*-patterns.md` — Read those when implementing, not on every rule load. Core points to InfoSys-aligned ownership (pagefault → `twincat3-pagefault-safety` / audit skill; attributes → attributes skill; error `VAR_OUTPUT` → new-library templates).

## Key workflows

### `/twincat3-cmd-new-version` — ship gate

Strict pipeline (skill `twincat3-new-version`):

```text
PlcProj sync → Comment (scoped) → Format → PF-Audit
  → (re-Format only if code changed) → Validate(4024)
  → Version (auto / reexport) → Changelog → Export both
  → Thematic local commits → Report
```

- Default XAE **4024**; export always `.library` + `.compiled-library` (async + poll).
- Version: classify → auto MAJOR/MINOR/BUILD/REVISION per `twincat3-versioning`; mode `reexport` = no bump.
- Never pushes.

### `/twincat3-cmd-release` vs new-version

| | `/twincat3-cmd-new-version` | `/twincat3-cmd-release` |
|--|----------------------------|-------------------------|
| **Version** | Auto from bump table (honor explicit override) | **User-stated only** — ask; never invent |
| **Gate steps** | Full: plcproj, comment, format, PF-audit, validate, changelog, export, commits | Core: apply version → validate → export both → changelog |
| **Use when** | Ready to ship a library change | You already chose the exact version / skip full gate |

### `/twincat3-cmd-comment` — one object

One `.TcPOU` or `.TcDUT` per run (FB/FUNCTION/PROGRAM, STRUCT, or ENUM). Density from `twincat3-comments` inline pseudocode; English `(* *)` only. Optional STweep on that object afterward. Not a whole-library rewrite.

### `/twincat3-cmd-online-test` vs `/twincat3-cmd-live-diagnostics`

| | Online test | Live diagnostics |
|--|-------------|------------------|
| **Command** | `/twincat3-cmd-online-test` | `/twincat3-cmd-live-diagnostics` |
| **When** | Bring-up E2E on Usermode Runtime | PLC already RUN / `ready_for_ads` |
| **Focus** | UmRT start → activate → runtime messages → ADS smoke | MCP ADS symbols / R/W / batch; pyads for timed deep debug |
| **Export shortcut** | If export needed: `.library` only | N/A (no ship export) |

Prefer 4026 for UmRT online-test; ship gate / release stay on 4024 unless the user asks for 4026.

## Rules

Coding rules applied automatically or on request (`rules/`).

| Rule | Description | Always Apply | Globs |
|------|-------------|:------------:|-------|
| `twincat3-core` | Priority stack (safety > function > performance > style), ST syntax, memory safety, DRY; ownership map to other rules/skills | Yes | — |
| `twincat3-naming` | Variable prefixes, type names, file naming, unit suffixes | Yes | — |
| `twincat3-oop` | EXTENDS, interfaces, abstract FBs, FB_init injection | — | — |
| `twincat3-formatting` | Indentation, alignment, blank lines, control flow | — | `*.TcPOU`, `*.TcDUT`, `*.TcGVL` |
| `twincat3-formatter-verification` | Verification rules for Formatter test fixtures (raw, golden, oneline 4-gate) | — | — |
| `twincat3-comments` | Mandatory I/O `(* *)`, selective VAR, prose phase blocks (inline pseudocode) | — | `*.TcPOU`, `*.TcDUT`, `*.TcGVL`, `*.TcIO` |
| `twincat3-versioning` | Version format, bump table, release vs new-version ownership; samples in `rules/examples/` | — | — |
| `twincat3-modbus` | Modbus TCP/RTU architecture, step-pair pattern, error handling | — | `*.TcPOU`, `*.TcDUT` |
| `twincat3-mqtt` | MQTT connection, subscribe-on-connect, reconnection, QoS, TLS | — | `*.TcPOU` |
| `twincat3-http` | HTTP(S) FB structure, 3-level error evaluation, auth | — | `*.TcPOU` |
| `twincat3-iot-patterns` | Tc3_IoT_BA, MQTT widgets, ComClient, Views | — | `Tc3_IoT_*/**`, `Tc3_Iot_*/**` |
| `twincat3-logging` | F_IoT_Utilities_MessageLog, edge-detected logging | — | `*.TcPOU`, `*.TcGVL` |
| `twincat3-plcproj` | File/folder registration, PlaceholderReference | — | `*.plcproj` |
| `twincat3-xml` | TcPlcObject XML — CDATA-only edits, GUIDs, line endings, encoding/BOM | — | `*.TcPOU`, `*.TcDUT`, `*.TcGVL`, `*.TcIO` |
| `twincat3-pagefault-safety` | InfoSys-backed page-fault / AV patterns (AND, POINTER/REF/IFACE, `__NEW`/`__DELETE`, MEMCPY, bounds) | — | — |
| `twincat3-mcp-build` | MCP build tools, validation, session, export scope, async export/format | — | — |
| `twincat3-mcp-runtime` | UmRT / activate / runtime messages / ADS readiness and server IDs | — | — |
| `twincat3-mcp-stweep` | STweep install/license gates; format file/folder vs project confirm | — | — |
| `twincat3-mcp-format` | Python ST formatter MCP tools (`twincat_format_*`); no XAE | — | — |
| `twincat3-mcp-syntax` | Fast headless ST syntax and semantic check awareness (`twincat_check_syntax`); no XAE | — | — |
| `twincat3-mcp-autodocs` | Autodocs path contract: solution folder → repo root; `twincat_autodocs` only | — | — |
| `twincat3-mcp-live-diagnostics` | Live ADS R/W via MCP; when to escalate to Python pyads | — | — |
| `twincat3-mcp-infosys-mshc` | Offline InfoSys MSHC lookup — when and how to search/read | — | — |
| `twincat3-migration-safety` | Unified FBD/CFC migration safety (preview-first, backup, TODOs) | — | — |
| `twincat3-fup-safety` | FBD-specific migration notes (extends migration-safety) | — | — |
| `twincat3-cfc-safety` | CFC-specific migration notes (extends migration-safety) | — | — |
| `twincat3-plcproj-safety` | PlcProject sync safety (verify-first, backup; XAE only if user asks) | — | — |

### Examples (`rules/examples/`)

| Example file | Companion rule |
|--------------|----------------|
| `twincat3-xml.md` | `twincat3-xml` |
| `twincat3-oop.md` | `twincat3-oop` |
| `twincat3-versioning.md` | `twincat3-versioning` |
| `twincat3-plcproj.md` | `twincat3-plcproj` |
| `twincat3-iot-patterns.md` | `twincat3-iot-patterns` |

## Skills

On-demand skills (`skills/`). Domain patterns often live in sibling `*-patterns.md` or `references/`.

| Skill | Description |
|-------|-------------|
| `twincat3-attributes` | Complete reference for all `{attribute '...'}` pragmas |
| `twincat3-code-style` | Formatting + comment quick reference → `references/` |
| `twincat3-json-strings` | JSON with Tc3_JsonXml, dynamic strings (`__NEW`/`__DELETE`) |
| `twincat3-logging` | Structured logging with F_IoT_Utilities_MessageLog |
| `twincat3-modbus` | Modbus TCP + RTU device integration patterns |
| `twincat3-mqtt` | MQTT publish/subscribe, QoS, TLS, Last Will |
| `twincat3-http` | HTTP(S) REST client, auth, JSON body workflow |
| `twincat3-new-library` | Create a new TwinCAT3 PLC library from scratch |
| `twincat3-infosys-mshc` | Offline InfoSys MSHC lookup (preferred) |
| `twincat3-infosys-lookup` | Web InfoSys fallback after MSHC returns 0 hits |
| `twincat3-changelog` | Slim user-facing changelogs with GitHub commit links |
| `twincat3-git-commit` | Thematic Conventional Commits locally (never push) |
| `twincat3-release` | Release core: user-chosen version, validate, export both, changelog |
| `twincat3-new-version` | Ship gate orchestrator (see Key workflows) |
| `twincat3-comment` | One-object comment pass (`(* *)`): FB / STRUCT / ENUM |
| `twincat3-check-syntax` | Fast headless ST syntax & semantic validation (`twincat_check_syntax`) |
| `twincat3-validate` | MCP CheckAllObjects validation (open → check → fix cycle) |
| `twincat3-format` | Python ST formatter via MCP (default — no XAE) |
| `twincat3-stweep-format` | STweep Format code via MCP (XAE + STweep license) |
| `twincat3-pagefault-audit` | InfoSys-only page-fault / AV static audit |
| `twincat3-live-diagnostics` | Live ADS via MCP; Python pyads for timed deep debug |
| `twincat3-umrt-systemtest` | UmRT E2E: start, activate, runtime messages, ADS smoke |
| `twincat3-fup-migrate` | FBD/FUP → ST (analyze, preview, migrate) |
| `twincat3-cfc-migrate` | CFC → ST (analyze, preview, migrate) |
| `twincat3-migrate` | Unified FBD/CFC migration with auto-detection |
| `twincat3-plcproj-sync` | PlcProject verify/sync (verify, dry-run, sync, GUID repair) |
| `twincat3-autodocs` | Markdown API docs — solution folder → repo root (`twincat_autodocs` only) |

## Commands

Slash commands (`commands/`). Pattern: `twincat3-cmd-<topic>`. Each command lists **Read first** paths before work.

| Command | Skill(s) | Description |
|---------|----------|-------------|
| `twincat3-cmd-new-version` | `twincat3-new-version` (+ atomic skills) | Full ship gate |
| `twincat3-cmd-release` | `twincat3-release` (+ changelog) | User-chosen version + validate + export both |
| `twincat3-cmd-comment` | `twincat3-comment` | One-object `(* *)` comment pass |
| `twincat3-cmd-format` | `twincat3-format` | Python ST formatter via MCP (default) |
| `twincat3-cmd-stweep-format` | `twincat3-stweep-format` | STweep Format code via MCP (XAE) |
| `twincat3-cmd-pagefault-audit` | `twincat3-pagefault-audit` | InfoSys-only page-fault / AV audit |
| `twincat3-cmd-check-syntax` | `twincat3-check-syntax` | Fast headless ST syntax & semantic check (no XAE) |
| `twincat3-cmd-online-test` | `twincat3-umrt-systemtest` | UmRT end-to-end online test |
| `twincat3-cmd-live-diagnostics` | `twincat3-live-diagnostics` | Live ADS diagnose (PLC already online) |
| `twincat3-cmd-validate` | `twincat3-validate` | MCP CheckAllObjects validation |
| `twincat3-cmd-migrate` | `twincat3-migrate` (+ fup/cfc) | FBD/CFC → ST (preview-first) |
| `twincat3-cmd-plcproj-sync` | `twincat3-plcproj-sync` | Verify/sync `.plcproj` vs disk |
| `twincat3-cmd-autodocs` | `twincat3-autodocs` | Autodocs only — solution folder → repo root |
| `twincat3-cmd-commit` | `twincat3-git-commit` | Thematic Conventional Commits (never push) |
| `twincat3-cmd-changelog` | `twincat3-changelog` | Write `Versions/<ver>/changelog-<ver>.md` |
| `twincat3-cmd-new-library` | `twincat3-new-library` | New PLC library scaffold |
| `twincat3-cmd-modbus` | `twincat3-modbus` | Modbus TCP/RTU device integration |
| `twincat3-cmd-mqtt` | `twincat3-mqtt` | MQTT FB (optional JSON) |
| `twincat3-cmd-http` | `twincat3-http` | HTTP(S) REST client FB |
| `twincat3-cmd-json` | `twincat3-json-strings` | JSON parse and/or build |
| `twincat3-cmd-logging` | `twincat3-logging` | Structured MessageLog logging |
| `twincat3-cmd-infosys` | `twincat3-infosys-mshc` (+ lookup) | Beckhoff type/docs lookup |
| `twincat3-cmd-attributes` | `twincat3-attributes` | Attribute pragma apply/explain |
| `twincat3-cmd-code-style` | `twincat3-code-style` | Formatting + comments standards |

## Agents

Specialized readonly subagents (`agents/`).

| Agent | Description |
|-------|-------------|
| `twincat-code-reviewer` | ST review vs naming, formatting, OOP, comments, core — severity ERROR / WARNING / INFO |
| `twincat-comment-auditor` | Report-only comment gap audit vs `twincat3-comments` (`(* *)` only) |
| `twincat-debugger` | Compiler / runtime / dependency diagnosis with MCP build tools |
| `twincat-pagefault-auditor` | InfoSys-only page-fault / AV auditor (checklist Check-IDs) |
| `twincat-migration-planner` | FBD/CFC migration assessment — analyze, dry-run, risk order |
| `twincat-architecture` | Library structure, FB hierarchies, interfaces, deps, versioning |
| `twincat-infosys-researcher` | InfoSys lookup — offline-first, web fallback |

Ship gate + comment: skills `twincat3-new-version` and `twincat3-comment` are the executable source of truth.

## MCP Server

Build/runtime automation via TcXaeShell COM (`mcp-servers/mcp-twincat/`). Requires Windows + TwinCAT XAE for XAE-backed tools. **57 tools** total.

### Server IDs and discovery

| Mode | Server ID | When |
|------|-----------|------|
| Team / marketplace | `plugin-twincat-ai-toolkit-mcp-twincat` | Installed plugin |
| Local (dev) | `user-mcp-twincat-local` | Repo `server.py` via `~/.cursor/mcp.json` key `mcp-twincat-local` |

- Discover schemas with **`GetMcpTools(server, …)`** — do not read tool JSON files as primary discovery.
- Use **one** server per turn (avoid DTE/ROT races).
- Details: rules `twincat3-mcp-build`, `twincat3-mcp-runtime`, `twincat3-mcp-stweep`, `twincat3-mcp-format`, `twincat3-mcp-syntax`, `twincat3-mcp-autodocs`, `twincat3-mcp-live-diagnostics`, `twincat3-mcp-infosys-mshc`.

### Tools by area

| Area | Tools (summary) | Notes |
|------|-----------------|-------|
| **Session / build** | `twincat_status`, `twincat_open`, `twincat_reload`, `twincat_check_all_objects`, `twincat_build`, `twincat_get_output_log`, `twincat_close` | Primary validate = CheckAllObjects |
| **Extension ops** | `twincat_extension_status`, `twincat_extension_install`, `twincat_extension_build` | VSIX bundle check & installation |
| **Export (async)** | `twincat_export_library`, `twincat_export_progress`, `twincat_export_check_artifacts` | Default `wait=false`; after `-32001` poll then disk-check before re-export |
| **STweep format (XAE)** | `twincat_stweep_status`, `twincat_stweep_format`, `twincat_stweep_format_progress`, `twincat_stweep_format_cancel` | Requires `twincat_open`; default `wait=false`; poll progress; dismiss reload dialogs via `twincat_dismiss_safe_dialogs` |
| **Python format (no XAE)** | `twincat_format`, `twincat_format_progress`, `twincat_format_validate`, `twincat_format_config` | File-based; default formatter; also `python -m formatter` CLI |
| **Target / activate** | `twincat_get_target`, `twincat_set_target`, `twincat_activate`, `twincat_start`, `twincat_task_*`, `twincat_io_*` | See `twincat3-mcp-runtime` |
| **UmRT / PLC / messages** | `twincat_umrt_*`, `twincat_runtime_state`, `twincat_set_runtime_mode`, `twincat_plc_*`, `twincat_runtime_messages`, `twincat_verify_library_on_target`, `twincat_umrt_e2e` | Online-test path |
| **ADS** | `twincat_ads_symbols`, `twincat_ads_read`, `twincat_ads_read_list`, `twincat_ads_write`, `twincat_ads_write_list` | Live-diagnostics path; writes need `confirm` |
| **No XAE (Syntax / Docs / Project)** | `twincat_check_syntax`, `twincat_workspace_symbols`, `twincat_symbol_lookup`, `twincat_plcproj_info`, `twincat_plcproj_verify`, `twincat_plcproj_sync`, `twincat_fup_migrate`, `twincat_cfc_migrate`, `twincat_migrate`, `twincat_autodocs`, `twincat_infosys_mshc_search`, `twincat_infosys_mshc_read` | Fast AST checks / Disk / offline docs |

**Export scope:** ship gate / release → both `.library` + `.compiled-library`. Online-test (if export needed) → `.library` only (`compiled_library=false`).

### Direct CLI (FBD/CFC migration, no XAE)

From `mcp-servers/mcp-twincat/` (same Python env as the MCP server):

```bash
cd plugins/twincat-ai-toolkit/mcp-servers/mcp-twincat

# FBD/FUP (NWL) → ST
python -m migrator fbd --input "POUs/MyFb.TcPOU" --dry-run
python -m migrator fbd --input "POUs/MyFb.TcPOU" --swap

# CFC → ST
python -m migrator cfc --input "POUs/MyFb.TcPOU" --analyze-only

# Auto-detect NWL vs CFC per file
python -m migrator auto --input "POUs/" --recursive --dry-run
python -m migrator auto --input "POUs/MyFb.TcPOU" --force
```

Common flags: `--dry-run`, `--analyze-only`, `--swap`, `--force`, `--recursive`, `--no-backup`, `--strict`.

MCP equivalents (same backend): `twincat_fup_migrate`, `twincat_cfc_migrate`, `twincat_migrate`. Full flag reference: skills `twincat3-fup-migrate`, `twincat3-cfc-migrate`, `twincat3-migrate` → `cli-reference.md`.

Migrates `.TcPOU` with NWL/CFC implementation only — not `.TcIO` (interfaces are declaration-only; code lives in implementing FBs).

### Direct CLI (Python formatter, no XAE)

From `mcp-servers/mcp-twincat/`:

```bash
cd plugins/twincat-ai-toolkit/mcp-servers/mcp-twincat
python -m formatter POUs/ --recursive
python -m formatter FB_MyBlock.TcPOU --dry-run
```

MCP equivalents: `twincat_format`, `twincat_format_validate`, `twincat_format_config`. Command: `/twincat3-cmd-format`. Skill: `twincat3-format`.

STweep (XAE): `/twincat3-cmd-stweep-format` → `twincat_stweep_format`, etc.

### Direct CLI (autodocs, no XAE)

Generate Markdown API docs from TwinCAT source (`.TcPOU`, `.TcDUT`, `.TcGVL`, `.TcIO`):

```bash
cd plugins/twincat-ai-toolkit/mcp-servers/mcp-twincat
python -m autodocs --input "C:/Project/<LibName>"
# optional override: --output "C:/Project"
```

Writes `<repo-root>/docs/` (mirrored `.md` files), updates `README.md` TOC block and `docs/toc.md`.

**Library repo contract:** `input` = `<repo-root>/<LibName>/` (solution folder). `output` optional — default auto-detects `<repo-root>` (README/.git walk). Docs always in `<repo-root>/docs/`. See rule `twincat3-mcp-autodocs`.

MCP: `twincat_autodocs(input="<repo-root>/<LibName>")` — `output` optional. Command: `/twincat3-cmd-autodocs`. Skill: `twincat3-autodocs`.

### Direct CLI (InfoSys MSHC offline docs, no XAE)

Search and read Beckhoff offline documentation (.mshc):

```bash
cd plugins/twincat-ai-toolkit/mcp-servers/mcp-twincat
python -m infosys_mshc --search "FB_JsonDomParser"
python -m infosys_mshc --search "AddJsonMember" --parent "FB_JsonDomParser" --format markdown
python -m infosys_mshc --read "tcplclib_tc3_jsonxml/1033/4219231115.html" --format markdown
```

MCP equivalents: `twincat_infosys_mshc_search`, `twincat_infosys_mshc_read`. Command: `/twincat3-cmd-infosys`. Skill: `twincat3-infosys-mshc`.

### Fast Syntax & Semantic Checking (no XAE)

Headless, instantaneous syntax and semantic validation across files and folders directly via `twincat_core`:

- **MCP tool:** `twincat_check_syntax(path="POUs/MyFb.TcPOU", recursive=True, include_warnings=True)`
- **Command:** `/twincat3-cmd-check-syntax`
- **Skill:** `twincat3-check-syntax`
- **Diagnostic codes:** `TC-DECL-*` (declarations), `TC-STMT-*` (control flow), `TC-EXPR-*` (expressions), `TC-SEM-*` (types, inheritance, duplicates, interface conformance).

### Requirements

```
mcp>=1.27.0
pywin32>=306
```

### Troubleshooting: MCP server fails to start

**Symptom:** MCP logs show `python: can't open file '...\mcp-servers\mcp-twincat\server.py'` with a path rooted under the user home directory instead of the plugin folder, or `toolCount: 0`.

**Root cause:** Cursor does **not** apply a `cwd` field from plugin `.mcp.json` ([confirmed bug](https://github.com/anthropics/claude-code/issues/17565), [Cursor forum](https://forum.cursor.com/t/inconsistent-working-directory-for-plugin-hook-commands/153236)). The MCP process always starts with the user home or project folder as working directory, so relative paths to `server.py` resolve to the wrong location.

**Fix (applied):** The `.mcp.json` uses a Python bootstrap (`python -c "..."`) that locates `server.py` in the plugin cache via `~/.cursor/plugins/cache/elektrobeckhoff-cursor-plugins/twincat-ai-toolkit/*/...` using `glob` and `runpy.run_path`. This is fully self-contained and does not rely on Cursor environment variables (`cwd`, `CURSOR_PLUGIN_ROOT`) that are not available for MCP server processes.

**Fallback (local / Ultra):** Add a **dev** server to `~/.cursor/mcp.json` with an absolute path to the **repo** `server.py`. Use key `mcp-twincat-local` so Cursor exposes it as `user-mcp-twincat-local` (distinct from the plugin server `plugin-twincat-ai-toolkit-mcp-twincat`). Use **one** server per turn.

```json
{
  "mcpServers": {
    "mcp-twincat-local": {
      "command": "python",
      "args": ["C:/Users/<you>/Documents/GitHub/ElektroBeckhoff/elektrobeckhoff-cursor-plugins/plugins/twincat-ai-toolkit/mcp-servers/mcp-twincat/server.py"]
    }
  }
}
```

Replace the path with your clone. Discover tools via `GetMcpTools` — do not read tool JSON files.
