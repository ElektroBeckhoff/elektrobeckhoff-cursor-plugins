# ElektroBeckhoff Cursor Plugins

Cursor plugin marketplace for **Beckhoff TwinCAT 3** PLC development and **PDF tools**.

The flagship plugin — **TwinCAT AI Toolkit** — brings IEC 61131-3 Structured Text into Cursor as a full stack: lean coding rules, on-demand skills, slash commands, specialized agents, and a Windows MCP server that drives TcXaeShell (validate, STweep format, library export, Usermode Runtime, ADS).

## Available Plugins

| Plugin | Description |
|--------|-------------|
| [twincat-ai-toolkit](plugins/twincat-ai-toolkit/) | TwinCAT 3 AI toolkit for Cursor — rules, skills, commands, agents, and MCP build/runtime automation for Structured Text libraries |
| [pdf-tools](plugins/pdf-tools/) | PDF parsing and conversion using opendataloader-pdf — Markdown, JSON, HTML with AI-ready structure extraction |

## TwinCAT AI Toolkit — what you get

Architecture: **rules** (always-on core + on-demand domains) · **skills** (workflows) · **commands** (`/twincat3-cmd-*`) · **agents** (review, audit, debug) · **MCP** (TcXaeShell + offline InfoSys).

| Capability | What it does |
|------------|--------------|
| **Ship gate** | `/twincat3-cmd-new-version` — plcproj sync → comment → STweep format → pagefault audit → validate (4024) → auto version → changelog → export `.library` + `.compiled-library` → thematic local commits |
| **Release core** | `/twincat3-cmd-release` — user-chosen version only; validate + export both artifacts + changelog (no auto-bump) |
| **Validate / build** | MCP `CheckAllObjects` / build against TwinCAT XAE |
| **STweep format** | Format ST via MCP (file/folder; project with confirm); async + cancel for large jobs |
| **UmRT online test** | `/twincat3-cmd-online-test` — Usermode Runtime E2E: activate, runtime messages, ADS smoke |
| **Live ADS diagnostics** | `/twincat3-cmd-live-diagnostics` — symbols / read / write / batch when the PLC is already online |
| **Pagefault audit** | InfoSys-aligned static audit (AND, pointers, `__NEW`/`__DELETE`, MEMCPY, bounds) |
| **Comment pass** | `/twincat3-cmd-comment` — one-object `(* *)` comments from density rules |
| **InfoSys offline** | Local `.mshc` search/read (EN/DE); web fallback only if empty |
| **FBD / CFC → ST** | Preview-first migration via MCP (`twincat_fup_migrate`, `twincat_cfc_migrate`, `twincat_migrate`) or CLI `python -m migrator fbd\|cfc\|auto` — see [toolkit README](plugins/twincat-ai-toolkit/README.md#direct-cli-fbdcfc-migration-no-xae) |
| **IoT patterns** | Modbus TCP/RTU, MQTT, HTTP(S), JSON/`__NEW`, structured logging |
| **Token-thin rules** | Lean alwaysApply core + naming; heavy samples in `rules/examples/` and skill `*-patterns.md` |

Full inventory, workflows, and MCP troubleshooting: [plugins/twincat-ai-toolkit/README.md](plugins/twincat-ai-toolkit/README.md).

## Installation

Add this repository as a Cursor plugin source:

```
ElektroBeckhoff/elektrobeckhoff-cursor-plugins
```

Then enable the plugins you need in Cursor’s plugin UI.

## Prerequisites

| Plugin | Requirement | Install |
|--------|-------------|---------|
| twincat-ai-toolkit | Windows + TwinCAT XAE (for build / format / UmRT MCP tools) | [Beckhoff](https://www.beckhoff.com/twincat) |
| twincat-ai-toolkit | Python 3.10+ (for MCP server) | [python.org](https://www.python.org) |
| pdf-tools | Python 3.10+ (for MCP server) | [python.org](https://www.python.org) |
| pdf-tools | Java 11+ (opendataloader-pdf runtime) | [Adoptium](https://adoptium.net) |
| pdf-tools | opendataloader-pdf | `pip install opendataloader-pdf` |

Rules, skills, commands, and agents that do not call XAE work without TwinCAT installed; MCP validate/format/export/runtime requires Windows + XAE.

## License

MIT License — see [LICENSE](LICENSE) for details.

Copyright (c) 2024-2026 Elektro Beckhoff GmbH.
Usage and modification permitted with attribution. The copyright notice must be
retained in all copies and derivative works — you may not claim this as your own work.

## Built With

- [Cursor IDE](https://www.cursor.com) — AI-native code editor
- [Anthropic Claude](https://claude.ai) — AI assistant (Claude Sonnet / Opus)
