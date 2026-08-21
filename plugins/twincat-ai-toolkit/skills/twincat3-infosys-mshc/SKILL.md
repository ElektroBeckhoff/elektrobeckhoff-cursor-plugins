---
name: twincat3-infosys-mshc
description: Look up Beckhoff TwinCAT3 types, attributes, and documentation from the local offline InfoSys (.mshc) via MCP. Preferred over web-based lookup. Supports exact name search, BM25 fulltext, prefix, and phrase queries. Use when you need signatures, parameters, methods, or requirements of Tc2_*/Tc3_* library types.
---

# Offline InfoSys MSHC Lookup

## Tools

| Tool | Purpose |
|------|---------|
| `twincat_infosys_mshc_search` | Search by name, keywords, prefix, or phrase |
| `twincat_infosys_mshc_read` | Read a specific page by path |

## Quick Lookup (Most Common Case)

```
twincat_infosys_mshc_search(query="FB_IotMqttClient")
```

`auto_read=true` (default) returns full structured page on exact match. **One call is enough.**

## Search Modes

| Mode | Use case | Example |
|------|----------|---------|
| `auto` (default) | Known name or partial name | `FB_IotMqttClient`, `JsonDom` |
| `fulltext` | Find by description/keywords | `read Modbus input registers` |
| `symbol` | Only IEC types (FB, ST, E, I, F, M, P) | `MQTT`, `AddJsonMember` |
| `title` | Title substring only | `SmtpV3` |

## Filters & Output Format

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `library` | `str` | `""` | Filter results by library name (e.g. `library="Tc3_JsonXml"`) |
| `parent` | `str` | `""` | Filter by parent FB/Struct (e.g. `parent="FB_JsonDomParser"`) |
| `format` | `str` | `"markdown"` | `"markdown"` (default, token-efficient table layout) or `"json"` (raw structured dict) |
| `include_full_text` | `bool` | `false` | When reading, `false` returns concise IEC structure (<500 tokens). Set `true` for full body text. |

## Fulltext Search (BM25 via SQLite FTS5)

Finds pages containing ALL query words, ranked by relevance:

```
twincat_infosys_mshc_search(query="PID controller", mode="fulltext")
twincat_infosys_mshc_search(query="send email SMTP", mode="fulltext")
twincat_infosys_mshc_search(query="convert REAL to STRING", mode="fulltext")
twincat_infosys_mshc_search(query="AddJsonMember", parent="FB_JsonDomParser", format="markdown")
```

**Prefix search:** `FB_Json*`, `FB_MB*`, `ST_Iot*`
**Phrase search:** `"input registers"`, `"exponential backoff"`

## Search Strategy (Unknown Types)

1. **Exact name known** → default auto mode (`auto_read=true` is default)
2. **Method/Property disambiguation** → pass `parent="FB_..."` or `library="Tc3_..."`
3. **Name unknown, concept known** → `mode="fulltext"` with keywords
4. **Partial name** → prefix search: `FB_Smtp*`
5. **Markdown output** → pass `format="markdown"` for compact prompt injection
6. **Still 0 results** → fall back to `twincat3-infosys-lookup` skill (web)

## Language

| `language` | Docs | Headers |
|------------|------|---------|
| `"en"` (default) | English | Inputs, Outputs, Methods |
| `"de"` | German | Eingaenge, Ausgaenge, Methoden |

Type names are identical in both languages.

## Response Structure

| Field | Content |
|-------|---------|
| `title` | Page / Symbol title |
| `type` | `FUNCTION_BLOCK`, `STRUCT`, `ENUM`, `INTERFACE`, `FUNCTION`, `METHOD`, `PROPERTY`, `TYPE`, `article` |
| `library` | Explicit library name (e.g. `Tc3_JsonXml`, `Tc3_IotBase`) |
| `parent` | Parent POU/Struct for methods and properties (e.g. `FB_JsonDomParser`) |
| `qualified_name` | Fully qualified identifier (e.g. `Tc3_JsonXml.FB_JsonDomParser.AddJsonMember`) |
| `syntax` | Full ST declaration (`VAR_INPUT`/`VAR_OUTPUT`, `METHOD`, `PROPERTY`) |
| `inputs` | `[{name, type, description}]` |
| `outputs` | `[{name, type, description}]` |
| `methods` | `[{name, description}]` |
| `requirements` | `{library, twincat_version, development_environment, target_platform}` |
| `description` | Short summary |
| `full_text` | Complete page text (empty by default to save tokens; populated if `include_full_text=true`) |
| `truncated` | Boolean flag indicating whether arrays or text were trimmed to fit token budgets |
| `methods_total` / `methods_shown` | Method list truncation metrics |
| `params_total` / `params_shown` | Parameter list truncation metrics |

## Read a Specific Page

Only needed when `auto_read` did not fire (multiple results, no exact match):

```
twincat_infosys_mshc_read(path="tcplclib_tc3_jsonxml/1033/4219231115.html")
twincat_infosys_mshc_read(path="tcplclib_tc3_jsonxml/1033/4219231115.html", format="markdown")
```

The `path` comes from the search result.

## Prerequisites

TwinCAT 3 offline docs must be installed via **Help > Add and Remove Help Content** in TcXaeShell.

## Performance & Architecture

- ~55,000 pages from installed `.mshc` file
- Persistent ZipFile handle caching across MCP requests: **< 10ms read latency**
- SQLite FTS5 Schema v2 with BM25 full-text indexing (~1-3ms query latency)
- First search builds index (~13s), cached in `%TEMP%/twincat-mcp-infosys-mshc` (~0.2s startup)
- Automatic cache invalidation on `.mshc` file modification or schema update
