# TwinCAT AI Toolkit

AI rules, skills, commands, and build tools for **Beckhoff TwinCAT 3** projects in **IEC 61131-3 Structured Text**.

## Rules

Coding rules applied automatically or on request (`rules/`).

| Rule | Description | Always Apply | Globs |
|------|-------------|:------------:|-------|
| `twincat3-core` | Priority stack (safety > function > performance > style), ST syntax, memory safety, DRY | Yes | — |
| `twincat3-naming` | Variable prefixes, type names, file naming, unit suffixes | Yes | — |
| `twincat3-oop` | EXTENDS, interfaces, abstract FBs, FB_init injection | — | — |
| `twincat3-formatting` | Indentation, alignment, blank lines, control flow | — | `*.TcPOU`, `*.TcDUT`, `*.TcGVL` |
| `twincat3-comments` | Mandatory I/O comments, block separators, FB headers | — | `*.TcPOU`, `*.TcDUT`, `*.TcGVL` |
| `twincat3-versioning` | Version format, Global_Version GVL, changelog | — | — |
| `twincat3-modbus` | Modbus TCP/RTU architecture, step-pair pattern, error handling | — | `*.TcPOU`, `*.TcDUT` |
| `twincat3-mqtt` | MQTT connection, subscribe-on-connect, reconnection, QoS, TLS | — | `*.TcPOU` |
| `twincat3-http` | HTTP(S) FB structure, 3-level error evaluation, auth | — | `*.TcPOU` |
| `twincat3-iot-patterns` | Tc3_IoT_BA, MQTT widgets, ComClient, Views | — | `Tc3_IoT_*/**`, `Tc3_Iot_*/**` |
| `twincat3-logging` | F_IoT_Utilities_MessageLog, edge-detected logging | — | `*.TcPOU`, `*.TcGVL` |
| `twincat3-plcproj` | File/folder registration, PlaceholderReference | — | `*.plcproj` |
| `twincat3-xml` | TcPlcObject XML for TcPOU/TcDUT/TcGVL/TcIO — CDATA-only edits, GUIDs, line endings, encoding/BOM | — | `*.TcPOU`, `*.TcDUT`, `*.TcGVL`, `*.TcIO` |
| `twincat3-mcp-build` | MCP build tools, validation workflow, session management | — | — |
| `twincat3-migration-safety` | Unified safety rules for all FBD/CFC migration (preview-first, backup, TODOs) | — | — |
| `twincat3-fup-safety` | FBD-specific migration notes (extends migration-safety) | — | — |
| `twincat3-cfc-safety` | CFC-specific migration notes (extends migration-safety) | — | — |
| `twincat3-plcproj-safety` | Safety rules for PlcProject sync (verify-first, backup; XAE compile only if user asks) | — | — |
| `twincat3-mcp-infosys-mshc` | Offline InfoSys MSHC lookup — when and how to use the search/read tools | — | — |

## Skills

On-demand skills, loaded when the AI assistant needs them (`skills/`).

| Skill | Description |
|-------|-------------|
| `twincat3-attributes` | Complete reference for all `{attribute '...'}` pragmas |
| `twincat3-code-style` | Formatting and comment rules reference |
| `twincat3-json-strings` | JSON parsing/writing with Tc3_JsonXml, dynamic strings (`__NEW`/`__DELETE`) |
| `twincat3-logging` | Structured logging with F_IoT_Utilities_MessageLog |
| `twincat3-modbus` | Modbus TCP + RTU device integration patterns |
| `twincat3-mqtt` | MQTT publish/subscribe, QoS, TLS, Last Will |
| `twincat3-http` | HTTP(S) REST client, auth, JSON body workflow |
| `twincat3-new-library` | Create a new TwinCAT3 PLC library from scratch |
| `twincat3-infosys-lookup` | Look up Beckhoff InfoSys documentation via web search |
| `twincat3-changelog` | Create and update changelogs for library releases |
| `twincat3-git-commit` | Thematic Conventional Commits locally (never push) |
| `twincat3-release` | Full library release: version bump, validate, export, changelog |
| `twincat3-fup-migrate` | FBD/FUP-to-ST migration workflow (analyze, preview, migrate) |
| `twincat3-cfc-migrate` | CFC-to-ST migration workflow (analyze, preview, migrate) |
| `twincat3-migrate` | Unified FBD/CFC migration with auto-detection (analyze, preview, migrate) |
| `twincat3-plcproj-sync` | PlcProject verify/sync workflow (verify, dry-run, sync, GUID repair) |
| `twincat3-infosys-mshc` | Offline InfoSys MSHC lookup — search/read local .mshc docs (EN/DE) |

## Commands

Slash commands (`commands/`). Pattern: `twincat3-cmd-<topic>`. Each command lists **Read first** paths (skill + rules) before work. Scaffolding-only helpers were removed — use rules/`twincat3-xml` for new FB/DUT/GVL.

| Command | Skill(s) | Description |
|---------|----------|-------------|
| `twincat3-cmd-commit` | `twincat3-git-commit` | Thematic Conventional Commits locally (never push) |
| `twincat3-cmd-changelog` | `twincat3-changelog` | Write `Versions/<ver>/changelog-<ver>.md` |
| `twincat3-cmd-release` | `twincat3-release` (+ changelog) | Version bump, validate, export, changelog |
| `twincat3-cmd-validate` | `twincat3-validate` | MCP CheckAllObjects validation |
| `twincat3-cmd-migrate` | `twincat3-migrate` (+ fup/cfc if needed) | FBD/CFC → ST (preview-first) |
| `twincat3-cmd-plcproj-sync` | `twincat3-plcproj-sync` | Verify/sync `.plcproj` vs disk |
| `twincat3-cmd-new-library` | `twincat3-new-library` | New PLC library scaffold |
| `twincat3-cmd-modbus` | `twincat3-modbus` | Modbus TCP/RTU device integration |
| `twincat3-cmd-mqtt` | `twincat3-mqtt` | MQTT FB (optional JSON) |
| `twincat3-cmd-http` | `twincat3-http` | HTTP(S) REST client FB |
| `twincat3-cmd-json` | `twincat3-json-strings` | JSON parse and/or build |
| `twincat3-cmd-logging` | `twincat3-logging` | Structured MessageLog logging |
| `twincat3-cmd-infosys` | `twincat3-infosys-mshc` (+ lookup fallback) | Beckhoff type/docs lookup |
| `twincat3-cmd-attributes` | `twincat3-attributes` | Attribute pragma apply/explain |
| `twincat3-cmd-code-style` | `twincat3-code-style` | Formatting + comments standards |

## Agents

Specialized readonly subagents that can be delegated to or invoked via `/agent-name` (`agents/`).

| Agent | Description |
|-------|-------------|
| `twincat-code-reviewer` | ST code review against naming, formatting, OOP, comments, and core rules. Reports findings by severity (ERROR / WARNING / INFO). |
| `twincat-debugger` | Systematic diagnosis of compiler errors, runtime bugs, and missing dependencies using MCP build tools. |
| `twincat-migration-planner` | FBD/FUP and CFC migration assessment — analyze scope, dry-run preview, risk classification, recommended migration order. |
| `twincat-architecture` | Library architecture analysis — project structure, FB hierarchies, interface design, dependency management, versioning. |
| `twincat-infosys-researcher` | Beckhoff InfoSys documentation lookup — type signatures, methods, library requirements, attributes (offline-first, web fallback). |

## MCP Server

Build automation via TcXaeShell COM (`mcp-servers/mcp-twincat/`).

Connects to Beckhoff TcXaeShell (Visual Studio) via COM automation on a dedicated STA thread. Requires Windows with TwinCAT XAE installed.

| Tool | Description |
|------|-------------|
| `twincat_plcproj_info` | Read .plcproj metadata (title, version, company) — no XAE needed |
| `twincat_status` | XAE install/running, instances (busy/dialogs), MCP session, SilentMode |
| `twincat_open` | Open / attach solution (ROT multi-instance; optional `xae_version`) |
| `twincat_reload` | Reload solution from disk — only after `.plcproj` was changed |
| `twincat_check_all_objects` | Compile ALL objects — primary validation for libraries |
| `twincat_build` | Incremental build (`full_rebuild=true` for clean rebuild) |
| `twincat_get_output_log` | Re-read build pane (usually unnecessary after check/build) |
| `twincat_export_library` | Export .library / .compiled-library (requires prior `twincat_open`) |
| `twincat_close` | Release MCP session (quit only if MCP started XAE; else detach) |
| `twincat_fup_migrate` | Convert FBD/FUP .TcPOU to Structured Text — no XAE needed |
| `twincat_cfc_migrate` | Convert CFC .TcPOU to Structured Text — no XAE needed |
| `twincat_migrate` | Auto-detect FBD/CFC and convert to ST in one pass — no XAE needed |
| `twincat_plcproj_verify` | Verify .plcproj matches disk (read-only) — no XAE needed |
| `twincat_plcproj_sync` | Sync .plcproj from disk with backup/force/dry-run — no XAE needed |
| `twincat_infosys_mshc_search` | Search local offline InfoSys .mshc for types, attributes, articles (EN/DE) — no XAE needed |
| `twincat_infosys_mshc_read` | Read a page with structured extraction (syntax, I/O, methods) — no XAE needed |

### Requirements

```
mcp>=1.27.0
pywin32>=306
```

### Troubleshooting: MCP server fails to start

**Symptom:** MCP logs show `python: can't open file '...\mcp-servers\mcp-twincat\server.py'` with a path rooted under the user home directory instead of the plugin folder, or `toolCount: 0`.

**Root cause:** Cursor does **not** apply a `cwd` field from plugin `.mcp.json` ([confirmed bug](https://github.com/anthropics/claude-code/issues/17565), [Cursor forum](https://forum.cursor.com/t/inconsistent-working-directory-for-plugin-hook-commands/153236)). The MCP process always starts with the user home or project folder as working directory, so relative paths to `server.py` resolve to the wrong location.

**Fix (applied):** The `.mcp.json` uses a Python bootstrap (`python -c "..."`) that locates `server.py` in the plugin cache via `~/.cursor/plugins/cache/elektrobeckhoff-cursor-plugins/twincat-ai-toolkit/*/...` using `glob` and `runpy.run_path`. This is fully self-contained and does not rely on any Cursor environment variables (`cwd`, `CURSOR_PLUGIN_ROOT`) that are not available for MCP server processes.

**Fallback:** Add the server manually to `~/.cursor/mcp.json` with an absolute path:

```json
{
  "mcpServers": {
    "mcp-twincat": {
      "command": "python",
      "args": ["C:/Users/<you>/.cursor/plugins/cache/elektrobeckhoff-cursor-plugins/twincat-ai-toolkit/<hash>/mcp-servers/mcp-twincat/server.py"]
    }
  }
}
```

Replace `<you>` and `<hash>` with your username and the commit hash in `%USERPROFILE%\.cursor\plugins\cache\`.


