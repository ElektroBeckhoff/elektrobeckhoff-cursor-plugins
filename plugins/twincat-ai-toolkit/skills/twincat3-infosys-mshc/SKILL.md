---
name: twincat3-infosys-mshc
description: Look up Beckhoff TwinCAT3 types, attributes, and documentation from the local offline InfoSys archive (.mshc) using the twincat_infosys_mshc_search and twincat_infosys_mshc_read MCP tools. Use when the user asks about a Beckhoff library type, attribute pragma, or documentation page, or when you need the exact signature, parameters, methods, or requirements of Tc2_*/Tc3_* library types. Preferred over web-based lookup because it works offline and returns structured data.
---

# TwinCAT3 Offline InfoSys MSHC Lookup

Look up exact signatures, parameters, methods, and requirements for Beckhoff library types directly from the locally installed offline documentation (.mshc archive).

## When to Use

- User asks "what are the inputs of FB_IotMqttClient?"
- You need the exact VAR_INPUT/VAR_OUTPUT of a Beckhoff library FB
- You're unsure about parameter types, defaults, or string lengths
- You need to know which library to reference (Tc3_IotBase, Tc2_System, etc.)
- User asks about a TwinCAT attribute pragma (e.g., `pack_mode`, `strict`, `TcRpcEnable`)
- User references a Beckhoff type you don't have in your training data
- **Preferred over the web-based `twincat3-infosys-lookup` skill** because it works without internet

## Prerequisites

TwinCAT 3 offline documentation must be installed via **Help > Add and Remove Help Content** in TcXaeShell. The default `.mshc` file location:

```
C:\ProgramData\Microsoft\HelpLibrary2\Catalogs\VisualStudio15\ContentStore\EN-US\BKINFOSYS3_VS_100_EN-US.9.mshc
```

## Lookup Workflow

### Step 1: Search

```
twincat_infosys_mshc_search(query="FB_JsonDomParser")
twincat_infosys_mshc_search(query="FB_JsonDomParser", language="de")
```

The `auto_read` parameter (default: `true`) automatically reads the full page when a score-100 match is found. **In most cases, a single search call is all you need.**

#### Language Parameter

| `language` | Documentation | Description language |
|------------|---------------|---------------------|
| `"en"` (default) | English (EN-US, `/1033/`) | English |
| `"de"` | German (DE-DE, `/1031/`) | German |

Both languages contain the same types and pages. Type names (FB_, ST_, E_) are identical; descriptions and section headers differ.

#### Search Modes

| Mode | Description | Speed |
|------|-------------|-------|
| `auto` (default) | exact title > prefix > substring > fulltext fallback | Fast for title matches |
| `title` | title-only matching | Fast |
| `symbol` | title-only, filtered to FB_/ST_/E_/I_/F_ types | Fast |
| `fulltext` | searches inside HTML page content | ~1-2s (reads all pages) |

#### Search Tips

- **For EN docs**: use English titles: `Attribute 'hide'`; **for DE docs**: `Attribut 'hide'`
- **For attributes**: search by the attribute name directly: `pack_mode`, `strict`, `TcRpcEnable`, `noinit`
- **For FBs/STRUCTs/ENUMs**: use the exact type name: `FB_IotMqttClient`, `ST_IotMqttWill`, `E_CouplerErrType`
- **For methods inside an FB**: first search and read the FB, then look at the `methods` list
- **Fulltext mode**: use when searching for concepts or terms inside page content: `twincat_infosys_mshc_search(query="exponential backoff", mode="fulltext")`

### Step 2: Read (only if auto_read did not fire)

If the search returned multiple results and you need a specific one, or if `auto_read` was disabled:

```
twincat_infosys_mshc_read(path="tcplclib_tc3_jsonxml/1033/4219231115.html")
```

The `path` comes from the search result's `path` field.

### Step 3: Use the Structured Data

The read response contains:

| Field | Content |
|-------|---------|
| `title` | Page title (e.g., "FB_JsonDomParser") |
| `type` | Detected type: FUNCTION_BLOCK, STRUCT, ENUM, FUNCTION, INTERFACE, TYPE, article |
| `syntax` | Full ST declaration with VAR_INPUT/VAR_OUTPUT |
| `description` | Short description from meta tag |
| `inputs` | List of `{name, type, description}` dicts |
| `outputs` | List of `{name, type, description}` dicts |
| `methods` | List of `{name, description}` dicts |
| `requirements` | `{twincat_version, library, development_environment}` |
| `full_text` | **Complete page text** (stripped HTML) — always present, even for articles, attribute pages, guides |

### Step 4: Format for the User

Present the result as a clean ST declaration block:

```iecst
// From offline InfoSys: FB_JsonDomParser
// Library: Tc3_JsonXml | TwinCAT 3.1, Build 4022
FUNCTION_BLOCK FB_JsonDomParser
VAR_OUTPUT
    initStatus : HRESULT;
END_VAR
// Methods: AddArrayMember, AddBoolMember, ParseDocument, SetJson, ...
// (110 methods total)
```

## Duplicate Results

The same page ID can appear in multiple components (e.g., `FB_JsonDomParser` exists in `tcplclib_tc3_jsonxml`, `tf6701_tc3_iot_communication_mqtt`, and `tf6760_tc3_iot_https_rest`). The score-100 match is the primary component. Lower-scored duplicates are the same content.

## Limitations

- Only pages present in the installed `.mshc` file are searchable (~55,000 pages)
- Some types (like `E_IotMqttQos`) may not have their own page in the offline docs
- Fulltext search reads up to 16KB per page — very long pages may not be fully indexed
- The `.mshc` file version depends on the installed TwinCAT documentation version

## Comparison with twincat3-infosys-lookup (web-based)

| Feature | twincat3-infosys-mshc (this) | twincat3-infosys-lookup (web) |
|---------|------------------------------|-------------------------------|
| Internet required | No | Yes |
| Structured output | Yes (parsed JSON) | No (raw HTML) |
| Speed | ~0.02-0.2s title / ~1-2s fulltext | Depends on network |
| Coverage | Installed offline docs | Full online InfoSys |
| Auto-read | Yes (score-100 match) | Manual fetch required |

**Always prefer this offline tool.** Fall back to web-based lookup only when a type is missing from the offline docs.
