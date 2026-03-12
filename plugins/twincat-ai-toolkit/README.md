# twincat3-ai-toolkit

AI-friendly coding rules, patterns, and agent skills for developing **Beckhoff TwinCAT 3** PLC projects in **IEC 61131-3 Structured Text**.

---

## Rules (`rules/`)

Cursor `.mdc` rules — copy to `.cursor/rules/` in your project.

| Rule | Description | Applied to |
|------|-------------|------------|
| `twincat3-core` | ST syntax, cyclic execution, type safety, memory model, error pattern | always |
| `twincat3-naming` | Variable prefixes, type names, file naming, unit suffixes | always |
| `twincat3-fb-design` | Constants inside FB, VAR_INPUT defaults, standard output pattern, execute-flag pattern | always |
| `twincat3-state-machine` | `CASE _nStep OF` pattern, reserved step numbers, Modbus read pairs, interval timer | always |
| `twincat3-formatting` | Indentation, alignment, line wrapping | `*.TcPOU`, `*.TcDUT`, `*.TcGVL` |
| `twincat3-comments` | I/O comments, block separators, FB header | `*.TcPOU`, `*.TcDUT`, `*.TcGVL` |
| `twincat3-modbus` | Unified Modbus TCP/RTU architecture, step-pair pattern, error handling | optional |
| `twincat3-mqtt` | MQTT connection, subscribe-on-connect, payload allocation, reconnection | `*.TcPOU` |
| `twincat3-http` | HTTP(S) FB structure, Execute method, 3-level error evaluation, auth | `*.TcPOU` |
| `twincat3-oop` | EXTENDS, interfaces, abstract FBs, FB_init injection | optional |
| `twincat3-iot-patterns` | Tc3_IoT_BA, MQTT widgets, FB_init | `**/Tc3_IoT_*/**` |
| `twincat3-logging` | F_IoT_Utilities_MessageLog, edge-detected logging | `*.TcPOU`, `*.TcGVL` |
| `twincat3-versioning` | Version format, Global_Version GVL, changelog | optional |
| `twincat3-plcproj` | Registering files/folders, library PlaceholderReference entries | `**/*.plcproj` |
| `twincat3-xml-tcpou` | TcPOU XML structure, GUIDs, methods, properties | `**/*.TcPOU` |
| `twincat3-xml-tcdut` | TcDUT XML for STRUCT, ENUM, UNION | `**/*.TcDUT` |
| `twincat3-xml-tcgvl` | TcGVL XML for global variable lists | `**/*.TcGVL` |

---

## Skills (`skills/`)

Agent skills — loaded on demand by the AI assistant.

| Skill | Description |
|-------|-------------|
| `twincat3-attributes` | All `{attribute '...'}` pragmas — hide, noinit, reflection, pack_mode, qualified_only, strict, … |
| `twincat3-code-style` | Formatting and comment rules reference |
| `twincat3-json-strings` | JSON parsing (FB_JsonDomParser, FB_JsonDynDomParser), writing (FB_JsonSaxWriter), dynamic `__NEW`/`__DELETE` |
| `twincat3-logging` | F_IoT_Utilities_MessageLog with instance-path context |
| `twincat3-modbus` | Modbus TCP (Tc2_ModbusSrv) and RTU (Tc3_ModbusRtuEB) device integration with protocol-specific patterns |
| `twincat3-mqtt` | MQTT communication (FB_IotMqttClient) — publish/subscribe, topic routing, reconnection, QoS, TLS |
| `twincat3-http` | HTTP(S) REST communication (FB_IotHttpRequest) — GET/POST, 3-level error eval, auth, JSON body |
| `twincat3-new-library` | New library from scratch — folder layout, GUIDs, .plcproj setup, minimum files |
| `twincat3-infosys-lookup` | Fetch Beckhoff InfoSys documentation for unknown types and FBs |

---

## Prompts (`prompts/`)

Ready-to-paste prompts for common TwinCAT 3 tasks.

| Prompt | Enthält |
|--------|---------|
| `modbus.md` | TCP device, RTU device, Write register |
| `iot-communication.md` | MQTT FB, HTTP REST FB, JSON parse, JSON build |
| `function-blocks.md` | Generic FB, State machine, Method, Property |
| `library-types.md` | New library, Struct, Enum, GVL, .plcproj registration |
