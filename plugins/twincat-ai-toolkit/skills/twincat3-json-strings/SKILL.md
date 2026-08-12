---
name: twincat3-json-strings
description: JSON parsing with FB_JsonDomParser/FB_JsonDynDomParser, JSON writing with FB_JsonSaxWriter, DOM manipulation with AddJsonMember/SetJson/CopyJson, dynamic string allocation with __NEW/__DELETE, and string operations in TwinCAT3. Use when working with MQTT payloads, HTTP responses, REST APIs, JSON data, dynamic memory, string formatting, or any Tc3_JsonXml operations.
---

# JSON & Dynamic Strings in TwinCAT3

## Overview

TwinCAT3 uses the `Tc3_JsonXml` library for JSON. Three main FBs:

| FB | Purpose | Direction |
|----|---------|-----------|
| `FB_JsonDomParser` | Parse JSON into navigable DOM (static memory) | Receive/Read |
| `FB_JsonDynDomParser` | Parse JSON into navigable DOM (dynamic memory) | Receive/Read |
| `FB_JsonSaxWriter` | Build JSON string incrementally | Send/Write |

## FB_JsonDomParser vs FB_JsonDynDomParser

| | `FB_JsonDomParser` | `FB_JsonDynDomParser` |
|-|--------------------|-----------------------|
| Memory | Static, compile-time buffer | Dynamic, runtime allocation |
| Best for | HTTP responses (`GetJsonDomContent`), known-size JSON | MQTT payloads, variable-size JSON, persistent DOM trees |
| DOM mutation | `AddJsonMember`, `SetJson`, `CopyJson`, `SetFileTime` | Same API |
| Used in | Tc3_MieleAtHome, Tc3_Seven_io | Tc3_IoT_BA |

Both parsers share the same API — `FindMember`, `HasMember`, `GetArraySize`, `GetArrayValueByIdx`, `MemberBegin`/`MemberEnd` etc. work identically on both.

**Rule of thumb**: Use `FB_JsonDomParser` for HTTP response parsing. Use `FB_JsonDynDomParser` when building/modifying DOM trees or handling unknown payload sizes.

## JSON Parsing Workflow

```
1. Get JSON data     →  GetJsonDomContent(fbParser) or __NEW + GetPayload + ParseDocument
2. Navigate DOM      →  FindMember / HasMember / MemberBegin / GetArrayValueByIdx
3. Extract values    →  CopyString / GetDouble / GetInt / GetBool / GetUint64
4. Free if allocated →  __DELETE(pPayload)
```

ST for HTTP shortcut, MQTT `__NEW` parse, object/array/deep nesting →
[json-parse-patterns.md](json-parse-patterns.md).

## JSON Writing Workflow

```
1. Reset document    →  _fbJsonWriter.ResetDocument()
2. Build structure   →  StartObject / AddKey* / EndObject
3. Output:
   a. Small (<255)   →  sBody := _fbJsonWriter.GetDocument()
   b. Large           →  __NEW + CopyDocument + __DELETE
```

ST for GetDocument / CopyDocument, nested arrays, DOM mutation, `_CreateSendPayload` →
[json-write-patterns.md](json-write-patterns.md).

## Dynamic String Allocation

Always: `__NEW` → check `<> 0` → use → `__DELETE` in same scope.

ST for allocation, reuse, string ops → [dynamic-strings.md](dynamic-strings.md).

## Key Rules

1. **Always check `_pPayload <> 0`** after `__NEW` — allocation can fail
2. **Always `__DELETE`** in the same scope — no dangling pointers
3. **Always check `_jsonDoc <> 0`** after `ParseDocument` or `GetJsonDomContent`
4. **Always `HasMember` before `FindMember`** for optional fields
5. **`CopyString` needs target buffer size** via `SIZEOF()`
6. **`GetDocument` returns STRING(255)** — use `CopyDocument` for larger JSON
7. **`GetArrayValueByIdx` is 0-based** — use `_idx - 1` when indexing from 1
8. **Size validation**: Check `GetDocumentLength` matches expected size before `CopyDocument`

## Required Library

```xml
<PlaceholderReference Include="Tc3_JsonXml">
  <DefaultResolution>Tc3_JsonXml, * (Beckhoff Automation GmbH)</DefaultResolution>
  <Namespace>Tc3_JsonXml</Namespace>
</PlaceholderReference>
```
