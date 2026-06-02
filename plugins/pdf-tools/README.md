# PDF Tools

PDF parsing and conversion tools using **[opendataloader-pdf](https://github.com/opendataloader-project/opendataloader-pdf)** for AI-ready data extraction.

## Rules

Coding rules applied automatically or on request (`rules/`).

| Rule | Description | Always Apply |
|------|-------------|:------------:|
| `pdf-tools-mcp` | MCP PDF tools awareness — available tools, format selection, workflow | — |

## Skills

On-demand skills, loaded when the AI assistant needs them (`skills/`).

| Skill | Description |
|-------|-------------|
| `pdf-convert` | Standard PDF conversion — prerequisites, `pdf_convert` usage, format guide, troubleshooting |
| `pdf-hybrid` | Hybrid mode for complex PDFs — scanned docs, OCR, formulas, charts, backend setup |

## Commands

Agent-executable commands for common tasks (`commands/`).

| Command | Description |
|---------|-------------|
| `pdf-to-markdown` | Convert PDF files to Markdown |
| `pdf-to-json` | Convert PDF files to structured JSON with bounding boxes |

## MCP Server

PDF conversion via opendataloader-pdf (`mcp-servers/mcp-pdf/`).

| Tool | Description | Prerequisites |
|------|-------------|---------------|
| `pdf_status` | Check if opendataloader-pdf and Java 11+ are installed | None |
| `pdf_convert` | Convert PDF(s) to Markdown/JSON/HTML/text (local mode, ~60 pages/sec) | Java 11+, opendataloader-pdf |
| `pdf_convert_hybrid` | Convert complex PDFs with AI backend (hybrid mode, #1 benchmark accuracy) | Java 11+, opendataloader-pdf[hybrid], running backend |

### Requirements

- **Java 11+** — opendataloader-pdf spawns JVM processes ([download from Adoptium](https://adoptium.net))
- **Python 3.10+** — MCP server runtime

```
mcp>=1.27.0
opendataloader-pdf>=2.4.0
```

Install with:

```bash
pip install opendataloader-pdf
```

For hybrid mode (scanned PDFs, complex tables, formulas):

```bash
pip install "opendataloader-pdf[hybrid]"
```

### Output Formats

| Format | Use Case |
|--------|----------|
| `markdown` | LLM context, RAG chunks — clean text with headings, tables, lists |
| `json` | Element coordinates, source citations — bounding boxes for every element |
| `html` | Web display with styling |
| `text` | Plain text extraction |
| `tagged-pdf` | Accessibility remediation — screen-reader-ready output |

### Troubleshooting: MCP server fails to start

**Symptom:** MCP logs show `python: can't open file '...\mcp-servers\mcp-pdf\server.py'` with a path rooted under the user home directory instead of the plugin folder, or `toolCount: 0`.

**Root cause:** Cursor does **not** apply a `cwd` field from plugin `.mcp.json`. The MCP process always starts with the user home or project folder as working directory, so relative paths resolve to the wrong location.

**Fix (applied):** The `.mcp.json` uses a Python bootstrap (`python -c "..."`) that locates `server.py` in the plugin cache via `~/.cursor/plugins/cache/elektrobeckhoff-cursor-plugins/pdf-tools/*/...` using `glob` and `runpy.run_path`.

**Fallback:** Add the server manually to `~/.cursor/mcp.json` with an absolute path:

```json
{
  "mcpServers": {
    "mcp-pdf": {
      "command": "python",
      "args": ["C:/Users/<you>/.cursor/plugins/cache/elektrobeckhoff-cursor-plugins/pdf-tools/<hash>/mcp-servers/mcp-pdf/server.py"]
    }
  }
}
```

Replace `<you>` and `<hash>` with your username and the commit hash in `%USERPROFILE%\.cursor\plugins\cache\`.
