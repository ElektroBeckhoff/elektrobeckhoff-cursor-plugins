# TwinCAT AI Toolkit

AI rules, skills and templates for **Beckhoff TwinCAT 3** projects in **IEC 61131-3 Structured Text**.

## Rules

Automatically applied coding rules (`rules/`).

| Rule | Description |
|------|-------------|
| `twincat3-core` | ST syntax, cyclic execution, type safety, memory model |
| `twincat3-naming` | Variable prefixes, type names, file naming, unit suffixes |
| `twincat3-oop` | EXTENDS, interfaces, abstract FBs, FB_init injection |
| `twincat3-formatting` | Indentation, alignment, line wrapping |
| `twincat3-comments` | I/O comments, block separators, FB header |
| `twincat3-versioning` | Version format, Global_Version GVL, changelog |
| `twincat3-modbus` | Modbus TCP/RTU architecture, step-pair pattern |
| `twincat3-mqtt` | MQTT connection, subscribe-on-connect, reconnection |
| `twincat3-http` | HTTP(S) FB structure, 3-level error evaluation |
| `twincat3-iot-patterns` | Tc3_IoT_BA, MQTT widgets |
| `twincat3-logging` | F_IoT_Utilities_MessageLog, edge-detected logging |
| `twincat3-plcproj` | File/folder registration, PlaceholderReference |
| `twincat3-xml-tcpou` | TcPOU XML structure, GUIDs, methods, properties |
| `twincat3-xml-tcdut` | TcDUT XML for STRUCT, ENUM, UNION |
| `twincat3-xml-tcgvl` | TcGVL XML for global variable lists |

## Skills

On-demand skills, loaded when the AI assistant needs them (`skills/`).

| Skill | Description |
|-------|-------------|
| `twincat3-attributes` | All `{attribute '...'}` pragmas |
| `twincat3-code-style` | Formatting and comment rules reference |
| `twincat3-json-strings` | JSON parsing/writing, dynamic strings (`__NEW`/`__DELETE`) |
| `twincat3-logging` | Logging with instance-path context |
| `twincat3-modbus` | Modbus TCP + RTU device integration |
| `twincat3-mqtt` | MQTT publish/subscribe, QoS, TLS |
| `twincat3-http` | HTTP(S) REST, auth, JSON body |
| `twincat3-new-library` | Create a new library from scratch |
| `twincat3-infosys-lookup` | Look up Beckhoff InfoSys documentation |

## Commands

Agent-executable commands for common tasks (`commands/`).

| Command | Description |
|---------|-------------|
| `twincat3-modbus-tcp-device` | Create Modbus TCP device integration |
| `twincat3-modbus-rtu-device` | Create Modbus RTU device integration |
| `twincat3-modbus-add-write` | Add write registers to existing Modbus FB |
| `twincat3-mqtt-function-block` | Create MQTT function block |
| `twincat3-http-rest-client` | Create HTTP REST client FB |
| `twincat3-json-parse` | Add JSON parsing to existing FB |
| `twincat3-json-build` | Add JSON payload building to existing FB |
| `twincat3-new-function-block` | Create a new function block |
| `twincat3-new-state-machine` | Add step-based state machine to FB |
| `twincat3-add-method` | Add method to existing FB |
| `twincat3-add-property` | Add property to existing FB |
| `twincat3-new-library` | Create new PLC library from scratch |
| `twincat3-new-struct` | Create new struct (TcDUT) |
| `twincat3-new-enum` | Create new enum (TcDUT) |
| `twincat3-new-gvl` | Create new global variable list (TcGVL) |
| `twincat3-register-plcproj` | Register files in .plcproj |
