# JSON Writing Patterns (Tc3_JsonXml)

## Variables

```iecst
VAR
    _fbJsonWriter  : FB_JsonSaxWriter;
    _pJsonPayload  : POINTER TO BYTE;
    _nPayloadSize  : UDINT;
END_VAR
```

## Basic Write Flow (flat object)

Build: `{"id": 1, "device": "CX-01", "enabled": true, "power": 42.5}`

```iecst
_fbJsonWriter.ResetDocument();
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKeyNumber('id', 1);
_fbJsonWriter.AddKeyString('device', 'CX-01');
_fbJsonWriter.AddKeyBool('enabled', TRUE);
_fbJsonWriter.AddKey('power');
_fbJsonWriter.AddReal(42.5);
_fbJsonWriter.EndObject();

_nPayloadSize := _fbJsonWriter.GetDocumentLength();

IF _nPayloadSize > 0 THEN
    _pJsonPayload := __NEW(BYTE, _nPayloadSize);

    IF _pJsonPayload <> 0 THEN
        _fbJsonWriter.CopyDocument(_pJsonPayload^, _nPayloadSize);
        // Use _pJsonPayload^ for MQTT publish or HTTP send
        __DELETE(_pJsonPayload);
    END_IF
END_IF
```

## Nested Objects

Build: `{"device": "CX-01", "data": {"power": 42.5, "energy": 1234.0}}`

```iecst
_fbJsonWriter.ResetDocument();
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKeyString('device', sCxName);

_fbJsonWriter.AddKey('data');
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKey('power');
_fbJsonWriter.AddReal(stData.fPower);
_fbJsonWriter.AddKey('energy');
_fbJsonWriter.AddReal(stData.fEnergy);
_fbJsonWriter.EndObject();

_fbJsonWriter.EndObject();
```

## Arrays

Build: `{"modes": ["auto", "manual", "off"]}`

```iecst
_fbJsonWriter.ResetDocument();
_fbJsonWriter.StartObject();

_fbJsonWriter.AddKey('modes');
_fbJsonWriter.StartArray();
_fbJsonWriter.AddString('auto');
_fbJsonWriter.AddString('manual');
_fbJsonWriter.AddString('off');
_fbJsonWriter.EndArray();

_fbJsonWriter.EndObject();
```

## Nested Array of Objects (from Tc3_MieleAtHome)

Build: `{"targetTemperature": [{"Zone": 1, "value": 22}]}`

```iecst
_fbJsonWriter.ResetDocument();
_fbJsonWriter.StartObject();

_fbJsonWriter.AddKey('targetTemperature');
_fbJsonWriter.StartArray();
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKey('Zone');
_fbJsonWriter.AddDint(_stCommand.nZone);
_fbJsonWriter.AddKey('value');
_fbJsonWriter.AddDint(_stCommand.nTargetTemp);
_fbJsonWriter.EndObject();
_fbJsonWriter.EndArray();

_fbJsonWriter.EndObject();
_sBody := _fbJsonWriter.GetDocument();
```

### Time Array [hours, minutes] (from Tc3_MieleAtHome)

Build: `{"startTime": [14, 30]}`

```iecst
_fbJsonWriter.StartObject();

_fbJsonWriter.AddKey('startTime');
_fbJsonWriter.StartArray();
_fbJsonWriter.AddDint(_stCommand.nStartTime / 60);
_fbJsonWriter.AddDint(_stCommand.nStartTime MOD 60);
_fbJsonWriter.EndArray();

_fbJsonWriter.EndObject();
_sBody := _fbJsonWriter.GetDocument();
```

### Optional Fields (from Tc3_MieleAtHome)

```iecst
_fbJsonWriter.StartObject();

_fbJsonWriter.AddKey('programId');
_fbJsonWriter.AddDint(_stCommand.nProgram);

IF _stCommand.nProgDur <> 0 THEN
    _fbJsonWriter.AddKey('duration');
    _fbJsonWriter.StartArray();
    _fbJsonWriter.AddDint(_stCommand.nProgDur / 60);
    _fbJsonWriter.AddDint(_stCommand.nProgDur MOD 60);
    _fbJsonWriter.EndArray();
END_IF

IF _stCommand.nProgTemp <> 0 THEN
    _fbJsonWriter.AddKey('temperature');
    _fbJsonWriter.AddDint(_stCommand.nProgTemp);
END_IF

_fbJsonWriter.EndObject();
_sBody := _fbJsonWriter.GetDocument();
```

## GetDocument — Small JSON as STRING (from Tc3_MieleAtHome)

For small JSON payloads that fit in a STRING, use `GetDocument` instead of `__NEW` + `CopyDocument`:

```iecst
_fbJsonWriter.ResetDocument();
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKey('powerOn');
_fbJsonWriter.AddBool(TRUE);
_fbJsonWriter.EndObject();

_sBody := _fbJsonWriter.GetDocument();  // Returns STRING(255)
_fbJsonWriter.ResetDocument();
```

Use `GetDocument` when JSON is small (<255 chars). Use `CopyDocument` + `__NEW` for larger payloads.

## CopyDocument — Large JSON to Dynamic Buffer

```iecst
_fbJsonWriter.StartObject();
_fbJsonWriter.AddKey('userName');
_fbJsonWriter.AddString(sUsername);
_fbJsonWriter.AddKey('password');
_fbJsonWriter.AddString(sPassword);
_fbJsonWriter.EndObject();

_fbJsonWriter.CopyDocument(pDoc := sDataGet, nDoc := SIZEOF(sDataGet));
_fbJsonWriter.ResetDocument();
```

## DOM Manipulation — AddJsonMember / SetJson / CopyJson (from Tc3_IoT_BA)

These methods work on `FB_JsonDynDomParser` to modify an existing DOM tree (not `FB_JsonSaxWriter`).

### AddJsonMember — Add Serialized JSON Under a Key

```iecst
// 1. Build JSON fragment with SaxWriter
_fbClient._fbJsonWriter.ResetDocument();
_fbClient._fbJsonWriter.StartObject();
_fbClient._fbJsonWriter.AddKeyString('iot.DisplayName', sDisplayName);
_fbClient._fbJsonWriter.AddKeyBool('iot.LightOn', bLightOn);
_fbClient._fbJsonWriter.EndObject();

// 2. Copy to temp buffer
_nPayloadSize := _fbClient._fbJsonWriter.GetDocumentLength();
_pJsonPayload := __NEW(BYTE, _nPayloadSize);

IF _pJsonPayload <> 0 THEN
    _fbClient._fbJsonWriter.CopyDocument(_pJsonPayload^, _nPayloadSize);

    // 3. Insert into existing DOM under key
    _fbClient._fbJsonParser.AddJsonMember(_jsonPath, _sWidgetId, _pJsonPayload^);

    __DELETE(_pJsonPayload);
END_IF
```

### SetJson — Replace Value at Existing Path

```iecst
// Replace entire value at _jsonPath with new JSON
_fbClient._fbJsonWriter.CopyDocument(_pJsonPayload^, _nPayloadSize);
_fbClient._fbJsonParser.SetJson(_jsonPath, _pJsonPayload^);
```

### CopyJson — Serialize DOM Node to Buffer

```iecst
// Get size of a DOM subtree
_nPayloadSize := _fbClient._fbJsonParser.GetJsonLength(_jsonViewEntry);

IF _nPayloadSize <> 0 THEN
    _pJsonPayload := __NEW(BYTE, _nPayloadSize);

    IF _pJsonPayload <> 0 THEN
        // Serialize subtree to buffer
        _fbClient._fbJsonParser.CopyJson(_jsonViewEntry, _pJsonPayload^, _nPayloadSize);

        // Use as raw JSON in SaxWriter
        _fbClient._fbJsonWriterOnChange.AddKey(_sAccumViewPath);
        _fbClient._fbJsonWriterOnChange.AddRawObject(_pJsonPayload^);

        __DELETE(_pJsonPayload);
    END_IF
END_IF
```

## Embedding Pre-built JSON (AddRawObject)

```iecst
_fbJsonWriter.AddKey('values');
_fbJsonWriter.AddRawObject(_pSubPayload^);
```

## _CreateSendPayload / _DeleteSendPayload Reuse Pattern (from Tc3_IoT_BA)

Encapsulate `__NEW`/`__DELETE` in methods with a creation flag to prevent double-allocation:

```iecst
VAR
    _pSendPayload        : POINTER TO BYTE;
    _bSendPayloadCreated : BOOL;
END_VAR

METHOD _CreateSendPayload : BOOL
VAR_INPUT
    nSize : UDINT;
END_VAR

IF NOT _bSendPayloadCreated THEN
    _pSendPayload := __NEW(BYTE, nSize);

    IF _pSendPayload <> 0 THEN
        _CreateSendPayload   := TRUE;
        _bSendPayloadCreated := TRUE;
    END_IF
END_IF

METHOD _DeleteSendPayload : BOOL

IF _bSendPayloadCreated THEN
    __DELETE(_pSendPayload);
    _bSendPayloadCreated := FALSE;
    _DeleteSendPayload   := TRUE;
END_IF
```

### Usage in State Machine

```iecst
CASE _nState OF
    0: // Prepare
        _jsonDoc          := _fbJsonParser.GetDocumentRoot();
        _nSendPayloadSize := _fbJsonParser.GetDocumentLength();

        IF _nSendPayloadSize > 0
           AND_THEN THIS^._CreateSendPayload(nSize := _nSendPayloadSize) THEN
            _nState := 1;
        END_IF

    1: // Copy and validate
        _nSendPayloadSizeCheck := _fbJsonParser.GetDocumentLength();

        IF _nSendPayloadSizeCheck = _nSendPayloadSize THEN
            _fbJsonParser.CopyDocument(_pSendPayload^, _nSendPayloadSize);
            _nState := 2;
        ELSE
            // Size changed during build — discard and retry
            _nInvalidCount := _nInvalidCount + 1;
            THIS^._DeleteSendPayload();
            _nState := 0;
        END_IF

    2: // Publish
        _fbMqttClient.Publish(
            sTopic       := sTopic,
            pPayload     := _pSendPayload,
            nPayloadSize := _nSendPayloadSize,
            eQoS         := TcIotMqttQos.AtLeastOnceDelivery);
        _nState := 3;

    3: // Cleanup
        THIS^._DeleteSendPayload();
        _nState := 0;

END_CASE
```

## Size Validation Pattern

```iecst
_nSizeCheck := _fbJsonParser.GetDocumentLength();

IF _nSizeCheck = _nExpectedSize THEN
    _nActualSize := _fbJsonParser.CopyDocument(_pPayload^, _nExpectedSize);
ELSE
    _nInvalidCount := _nInvalidCount + 1;
    THIS^._DeleteSendPayload();
    _nState := 0;
END_IF
```

## AddKey Methods Reference

| Method | Value Type | Example |
|--------|-----------|---------|
| `AddKeyString(key, value)` | STRING | `AddKeyString('name', 'CX-01')` |
| `AddKeyNumber(key, value)` | DINT | `AddKeyNumber('id', 42)` |
| `AddKeyBool(key, value)` | BOOL | `AddKeyBool('on', TRUE)` |
| `AddKeyNull(key)` | null | `AddKeyNull('error')` |
| `AddKeyFileTime(key, value)` | FILETIME | `AddKeyFileTime('ts', nTime)` |
| `AddKey(key)` + `AddReal(v)` | LREAL | Separate calls for floats |
| `AddKey(key)` + `AddDint(v)` | DINT | Separate calls for DINT |
| `AddKey(key)` + `AddUlint(v)` | ULINT | Separate calls for ULINT |
| `AddKey(key)` + `AddBool(v)` | BOOL | Separate calls for BOOL |
| `AddKey(key)` + `AddRawObject(s)` | Raw JSON | Embed pre-built JSON |
| `AddString(value)` | STRING | Array elements (no key) |
| `GetDocument()` | STRING(255) | Small JSON shortcut |
| `CopyDocument(pDoc, nSize)` | to buffer | Large JSON |

## DOM Manipulation Reference (FB_JsonDynDomParser)

| Method | Purpose |
|--------|---------|
| `AddJsonMember(parent, key, json)` | Add serialized JSON under a new key |
| `SetJson(node, json)` | Replace node value with serialized JSON |
| `CopyJson(node, pDest, nSize)` | Serialize DOM node to buffer |
| `GetJsonLength(node)` | Get serialized size of a DOM node |
| `GetDocumentRoot()` | Get root `SJsonValue` handle |
| `GetDocumentLength()` | Get total document size |
| `SetFileTime(node, value)` | Set FILETIME value on node |
