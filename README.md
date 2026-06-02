# ElektroBeckhoff Cursor Plugins

Cursor plugin marketplace for **Beckhoff TwinCAT 3** PLC development and **PDF tools**.

## Available Plugins

| Plugin | Description |
|--------|-------------|
| [twincat-ai-toolkit](plugins/twincat-ai-toolkit/) | AI rules, skills and commands for IEC 61131-3 Structured Text — covers Modbus, MQTT, HTTP, JSON, state machines, XML generation, and more |
| [pdf-tools](plugins/pdf-tools/) | PDF parsing and conversion using opendataloader-pdf — convert PDFs to Markdown, JSON, HTML with AI-ready structure extraction |

## Installation

Add this repository as a Cursor plugin source:

```
ElektroBeckhoff/elektrobeckhoff-cursor-plugins
```

## Prerequisites

| Plugin | Requirement | Install |
|--------|-------------|---------|
| twincat-ai-toolkit | Windows + TwinCAT XAE (for build tools) | [Beckhoff](https://www.beckhoff.com/twincat) |
| twincat-ai-toolkit | Python 3.10+ (for MCP server) | [python.org](https://www.python.org) |
| pdf-tools | Python 3.10+ (for MCP server) | [python.org](https://www.python.org) |
| pdf-tools | Java 11+ (opendataloader-pdf runtime) | [Adoptium](https://adoptium.net) |
| pdf-tools | opendataloader-pdf | `pip install opendataloader-pdf` |

## License

MIT License — see [LICENSE](LICENSE) for details.

Copyright (c) 2024-2026 Elektro Beckhoff GmbH.
Usage and modification permitted with attribution. The copyright notice must be
retained in all copies and derivative works — you may not claim this as your own work.

## Built With

- [Cursor IDE](https://www.cursor.com) — AI-native code editor
- [Anthropic Claude](https://claude.ai) — AI assistant (Claude Sonnet / Opus)
