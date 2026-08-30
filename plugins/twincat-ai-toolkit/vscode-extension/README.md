# TwinCAT 3 Structured Text & Tooling

[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](https://github.com/ElektroBeckhoff/elektrobeckhoff-cursor-plugins)
[![Language](https://img.shields.io/badge/language-IEC%2061131--3%20ST-orange.svg)](https://www.beckhoff.com)
[![Platform](https://img.shields.io/badge/platform-VS%20Code%20%7C%20Cursor-green.svg)](#)

A high-performance extension for **Beckhoff TwinCAT 3** and **IEC 61131-3 Structured Text (ST)** development in VS Code and Cursor. Powered by the native `twincat_core` Language Server and formatting engine.

---

## Key Features

### 1. Accurate TwinCAT 3 Syntax Highlighting
Full TextMate grammar support tailored specifically for TwinCAT 3 and modern IEC 61131-3 Structured Text:
- **IEC 61131-3 Core**: Standard keywords (`IF`, `THEN`, `CASE`, `FOR`, `WHILE`, `VAR`, `VAR_INPUT`, etc.).
- **TwinCAT 3 Extensions**: Attribute pragmas (`{attribute '...'}`), dynamic memory management (`__NEW`, `__DELETE`, `__ISVALIDREF`), and OOP constructs (`THIS`, `SUPER^`, `EXTENDS`, `IMPLEMENTS`, `ABSTRACT`, `FINAL`).
- **Beckhoff Types & Literals**: Typed constants (`TIME#100ms`, `T#1s`, `DT#...`, `16#FF`, `2#1010`), memory addressing (`%I*`, `%QX0.0`), and standard Beckhoff types (`T_MaxString`, `HRESULT`, `ANY`).

### 2. Built-in TwinCAT Language Server (LSP)
Directly backed by `twincat_core.lsp`:
- **Live Syntax & Semantic Diagnostics**: Instant error detection and squiggly underlines for syntax mistakes, duplicate identifiers, interface conformance, and type mismatches.
- **Rich Hover & Parameter Documentation**: Comprehensive tooltips for POUs, methods, structs, enums, variables, and comments with InfoSys documentation.
- **Go to Definition & Implementation**: Fast navigation to symbols across files within the solution.
- **IntelliSense Auto-Completion**: Member access (`.`, `^`) and scope completions.
- **Workspace & Project Awareness**: Indexing of `.plcproj` project trees, libraries, and global variable lists (GVLs).

### 3. Canonical TwinCAT Code Formatting
- Clean and consistent code formatting respecting Beckhoff and IEC 61131-3 conventions.
- Auto-indentation and keyword normalization.

---

## Commands & Shortcuts

| Command | Title | Description |
| :--- | :--- | :--- |
| `twincat.restartServer` | **TwinCAT: Restart Language Server** | Restarts the background Python Language Server. |

---

## Configuration Options

Customize extension behavior in your `settings.json`:

```json
{
  // Path to the Python executable running the twincat_core LSP
  "twincat.server.pythonPath": "python",

  // Additional directory paths for twincat_core module lookup
  "twincat.server.extraPaths": [],

  // Trace communication between editor and Language Server (off | messages | verbose)
  "twincat.server.trace.server": "off",

  // Enable/disable document formatting via twincat_core
  "twincat.format.enable": true
}
```

---

## Supported File Extensions

| Extension | Object Type | Description |
| :--- | :--- | :--- |
| `.TcPOU` | Program / Function Block / Function | TwinCAT 3 Program Organization Unit |
| `.TcDUT` | Struct / Enum / Alias / Union | TwinCAT 3 Data Unit Type |
| `.TcGVL` | Global Variable List | TwinCAT 3 GVL & Parameter Lists |
| `.TcIO`  | Interface | TwinCAT 3 Object-Oriented Interface |
| `.TcTTO` | Task / DUT configuration | TwinCAT 3 Target Type Object |
| `.st` / `.iecst` | Pure Structured Text | Raw IEC 61131-3 source files |

---

## Requirements & Setup

1. **Python 3.10+** (used to run the embedded `twincat_core` Language Server).
2. **VS Code 1.85.0+** or **Cursor IDE**.

---

## Author & License

- **Author**: [ElektroBeckhoff](https://github.com/ElektroBeckhoff)
- **Repository**: [elektrobeckhoff-cursor-plugins](https://github.com/ElektroBeckhoff/elektrobeckhoff-cursor-plugins)
- **License**: MIT
