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
| **Fast syntax / diagnostics** | `/twincat3-cmd-check-syntax` — instantaneous headless AST & semantic checks (`twincat_check_syntax`), type compatibility, interface conformance, no XAE needed |
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

## Prerequisites & Dependencies

### Summary Matrix

| Plugin | Component | Requirement | Scope | Purpose |
|--------|-----------|-------------|:-----:|---------|
| **twincat-ai-toolkit** | **Python** | Python 3.10+ | Required | MCP server runtime & `twincat_core` Language Server (LSP) |
| | **Python Packages** | `mcp>=1.27.0`, `pywin32>=306`, `pyads>=3.4.0`, `pygls>=2.0.0` | Required | Core tooling dependencies (`requirements.txt`) |
| | **TwinCAT 3 XAE** | TwinCAT 3.1 (Build 4024.x or 4026.x) | Optional* | Project compilation, validation, library export, ADS, and UmRT |
| | **Beckhoff InfoSys** | Offline InfoSys (`.mshc` Help Library) | Optional | Offline type lookup, API docstrings, and hover signatures |
| | **STweep for TwinCAT** | STweep 3.x CLI / TcXaeShell plugin | Optional | XAE-integrated code formatting (`twincat_stweep_*`) |
| | **TwinCAT UmRT** | Usermode Runtime (TC170x / TC3.1 4026+) | Optional | Headless runtime system tests without real-time kernel |
| | **Node.js** | Node.js 18+ & NPM | Optional | Rebuilding the VS Code / Cursor extension from source |
| **pdf-tools** | **Python** | Python 3.10+ | Required | MCP server runtime |
| | **Python Packages** | `mcp>=1.27.0`, `opendataloader-pdf>=2.4.0` | Required | PDF extraction & conversion (`requirements.txt`) |
| | **Java Runtime** | Java 11+ (JRE or JDK) | Required | Underlying opendataloader-pdf JVM extraction engine |

*\* Note: All headless tools (`twincat_check_syntax`, Python ST formatter, FBD/CFC migrator, AutoDocs, and LSP diagnostics) are 100% cross-platform (Windows, Linux, macOS) and do **not** require TwinCAT XAE. XAE is only required for COM build/export automation and live PLC communication on Windows.*

### Installing Dependencies

#### 1. TwinCAT AI Toolkit MCP & Core
```bash
cd plugins/twincat-ai-toolkit/mcp-servers/mcp-twincat
pip install -r requirements.txt
```

#### 2. PDF Tools MCP
```bash
cd plugins/pdf-tools/mcp-servers/mcp-pdf
pip install -r requirements.txt
```
*(Ensure Java 11+ is installed from [Adoptium](https://adoptium.net) or your system package manager).*

#### 3. Beckhoff Offline InfoSys (.mshc)
The toolkit automatically detects offline Beckhoff documentation in `C:\ProgramData\Microsoft\HelpLibrary2\Catalogs\VisualStudio*`. If not present, the tools gracefully fall back to web search or built-in catalogs.
- **Installer**: Download `TC3-InfoSys.exe` from [Beckhoff InfoSystem Download](https://download.beckhoff.com/download/Software/TwinCAT/TwinCAT3/InfoSystem/)
- **In TcXaeShell**: `Help` > `Manage Help Settings` > `Install content from online` > add *Beckhoff Information System* > `Update`.

## License

MIT License — see [LICENSE](LICENSE) for details.

Copyright (c) 2024-2026 Elektro Beckhoff GmbH.
Usage and modification permitted with attribution. The copyright notice must be
retained in all copies and derivative works — you may not claim this as your own work.

## Built With

- [Cursor IDE](https://www.cursor.com) — AI-native code editor
- [Anthropic Claude](https://claude.ai) — AI assistant (Claude Sonnet / Opus)
