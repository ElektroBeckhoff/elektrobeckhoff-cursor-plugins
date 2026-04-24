# TwinCAT AI Toolkit

AI rules, skills, commands, and build tools for **Beckhoff TwinCAT 3** projects in **IEC 61131-3 Structured Text**.

## Rules

Coding rules applied automatically or on request (`rules/`).

| Rule | Description | Always Apply | Globs |
|------|-------------|:------------:|-------|
| `twincat3-core` | ST syntax, cyclic execution, type safety, memory model | Yes | — |
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
| `twincat3-xml-tcpou` | TcPOU XML structure, CDATA, GUIDs, methods, properties | — | `*.TcPOU` |
| `twincat3-xml-tcdut` | TcDUT XML for STRUCT, ENUM, UNION | — | `*.TcDUT` |
| `twincat3-xml-tcgvl` | TcGVL XML for global variable lists | — | `*.TcGVL` |

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

## Commands

Agent-executable commands for common tasks (`commands/`).

| Command | Description |
|---------|-------------|
| `twincat3-new-function-block` | Create a new function block as valid TcPOU XML with GUID |
| `twincat3-new-state-machine` | Add step-based state machine to an existing FB |
| `twincat3-add-method` | Add method to an existing function block |
| `twincat3-add-property` | Add property to an existing function block (3 GUIDs) |
| `twincat3-new-library` | Create new PLC library with complete folder structure |
| `twincat3-new-struct` | Create a new struct as valid TcDUT XML |
| `twincat3-new-enum` | Create a new enum as valid TcDUT XML with attribute pragmas |
| `twincat3-new-gvl` | Create a new global variable list as valid TcGVL XML |
| `twincat3-modbus-tcp-device` | Create Modbus TCP device integration with state machine |
| `twincat3-modbus-rtu-device` | Create Modbus RTU device integration with FIFO buffer |
| `twincat3-modbus-add-write` | Add write functionality to existing Modbus device FB |
| `twincat3-mqtt-function-block` | Create MQTT FB with client, queue, reconnection, topic routing |
| `twincat3-http-rest-client` | Create HTTP REST client FB with error mapping and param struct |
| `twincat3-json-parse` | Add JSON parsing logic to existing FB with dynamic memory |
| `twincat3-json-build` | Add JSON payload building logic to existing FB |
| `twincat3-register-plcproj` | Register TcPOU, TcDUT, or TcGVL files in .plcproj |

## MCP Server

Build automation via TcXaeShell COM (`mcp-servers/mcp-twincat/`).

Connects to Beckhoff TcXaeShell (Visual Studio) via COM automation on a dedicated STA thread. Requires Windows with TwinCAT XAE installed.

| Tool | Description |
|------|-------------|
| `twincat_project_info` | Read .plcproj metadata (title, version, company) — no XAE needed |
| `twincat_status` | Check whether TcXaeShell is installed and running |
| `twincat_open` | Open a TwinCAT solution in XAE, locate PLC project |
| `twincat_reload` | Reload solution from disk (after .plcproj / .tsproj changes) |
| `twincat_check_all_objects` | Compile ALL objects — primary validation for libraries |
| `twincat_build` | Rebuild the TwinCAT solution |
| `twincat_get_errors` | Read structured build/check output (errors, warnings, infos) |
| `twincat_export_library` | Export .library and .compiled-library, install to local repo |
| `twincat_close` | Close solution and release COM resources |

### Requirements

```
mcp>=1.27.0
pywin32>=306
```
