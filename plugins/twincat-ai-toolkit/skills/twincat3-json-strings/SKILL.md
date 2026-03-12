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

### Parse HTTP Response (shortcut)

```iecst
_jsonDoc := _fbRequest.GetJsonDomContent(_fbJson);  // One call, no __NEW needed
```

### Parse MQTT Payload (manual)

```iecst
_pPayload := __NEW(BYTE, _fbMessage.nPayloadSize + 1);
IF _pPayload <> 0 THEN
    _fbMessage.GetPayload(_pPayload, _fbMessage.nPayloadSize + 1, TRUE);
    _jsonDoc := _fbJson.ParseDocument(_pPayload^);
    // ... navigate ...
    __DELETE(_pPayload);
END_IF
```

See [json-parse-patterns.md](json-parse-patterns.md) for object iteration, index-based array access, deep nesting, and complete examples.

## JSON Writing Workflow

```
1. Reset document    →  _fbJsonWriter.ResetDocument()
2. Build structure   →  StartObject / AddKey* / EndObject
3. Output:
   a. Small (<255)   →  sBody := _fbJsonWriter.GetDocument()
   b. Large           →  __NEW + CopyDocument + __DELETE
```

### Small JSON (GetDocument shortcut)

```iecst
_fbJsonWriter.ResetDocument();
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKey('powerOn');
_fbJsonWriter.AddBool(TRUE);
_fbJsonWriter.EndObject();

_sBody := _fbJsonWriter.GetDocument();  // Returns STRING(255)
_fbJsonWriter.ResetDocument();
```

### Large JSON (CopyDocument)

```iecst
_nPayloadSize := _fbJsonWriter.GetDocumentLength();
_pJsonPayload := __NEW(BYTE, _nPayloadSize);

IF _pJsonPayload <> 0 THEN
    _fbJsonWriter.CopyDocument(_pJsonPayload^, _nPayloadSize);
    // Publish or send...
    __DELETE(_pJsonPayload);
END_IF
```

See [json-write-patterns.md](json-write-patterns.md) for nested arrays, DOM manipulation (AddJsonMember/SetJson/CopyJson), and the _CreateSendPayload reuse pattern.

## Dynamic String Allocation

```iecst
_nPayloadSize := _fbMessage.nPayloadSize + 1;
_pPayload     := __NEW(BYTE, _nPayloadSize);

IF _pPayload <> 0 THEN
    // Use the buffer...
    __DELETE(_pPayload);  // ALWAYS free in same scope
END_IF
```

See [dynamic-strings.md](dynamic-strings.md) for allocation patterns, reuse strategies, and string operations.

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
