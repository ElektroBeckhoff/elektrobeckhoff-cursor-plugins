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
| `symbol` | Only FB_/ST_/E_/I_/F_ types | `MQTT` |
| `title` | Title substring only | `SmtpV3` |

## Fulltext Search (BM25 via SQLite FTS5)

Finds pages containing ALL query words, ranked by relevance:

```
twincat_infosys_mshc_search(query="PID controller", mode="fulltext")
twincat_infosys_mshc_search(query="send email SMTP", mode="fulltext")
twincat_infosys_mshc_search(query="convert REAL to STRING", mode="fulltext")
```

**Prefix search:** `FB_Json*`, `FB_MB*`, `ST_Iot*`
**Phrase search:** `"input registers"`, `"exponential backoff"`

## Search Strategy (Unknown Types)

1. **Exact name known** → default auto mode
2. **Name unknown, concept known** → `mode="fulltext"` with keywords
3. **Partial name** → prefix search: `FB_Smtp*`
4. **Still 0 results** → fall back to `twincat3-infosys-lookup` skill (web)

## Language

| `language` | Docs | Headers |
|------------|------|---------|
| `"en"` (default) | English | Inputs, Outputs, Methods |
| `"de"` | German | Eingaenge, Ausgaenge, Methoden |

Type names are identical in both languages.

## Response Structure

| Field | Content |
|-------|---------|
| `syntax` | Full ST declaration (VAR_INPUT/VAR_OUTPUT) |
| `inputs` | `[{name, type, description}]` |
| `outputs` | `[{name, type, description}]` |
| `methods` | `[{name, description}]` |
| `requirements` | `{library, twincat_version}` |
| `description` | Short summary |
| `full_text` | Complete page text (all content types) |

## Read a Specific Page

Only needed when `auto_read` did not fire (multiple results, no exact match):

```
twincat_infosys_mshc_read(path="tcplclib_tc3_jsonxml/1033/4219231115.html")
```

The `path` comes from the search result.

## Prerequisites

TwinCAT 3 offline docs must be installed via **Help > Add and Remove Help Content** in TcXaeShell.

## Limitations

- ~55,000 pages from installed `.mshc` file
- Some types may not have their own page (e.g., `E_IotMqttQos`)
- Body indexed up to 16KB per page
- First search builds index (~13s), cached afterwards (~0.2s)
