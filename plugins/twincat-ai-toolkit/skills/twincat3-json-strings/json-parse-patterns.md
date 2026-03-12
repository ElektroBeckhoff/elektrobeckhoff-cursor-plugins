# JSON Parsing Patterns (Tc3_JsonXml)

## Variables

```iecst
VAR
    _fbJson     : FB_JsonDynDomParser;
    _jsonDoc    : SJsonValue;
    _jsonVal    : SJsonValue;
    _jsonVal2   : SJsonValue;
    _jsonVal3   : SJsonValue;
    _pPayload   : POINTER TO BYTE;
    _nPayloadSize : UDINT;
END_VAR
```

> Parser comparison → see `SKILL.md`

## Basic Parse Flow

```iecst
_nPayloadSize := _fbMessage.nPayloadSize + 1;
_pPayload     := __NEW(BYTE, _nPayloadSize);

IF _pPayload <> 0 THEN
    IF _fbMessage.GetPayload(
            pPayload            := _pPayload,
            nPayloadSize        := _nPayloadSize,
            bSetNullTermination := TRUE) THEN
        _jsonDoc := _fbJson.ParseDocument(_pPayload^);

        IF _jsonDoc <> 0 THEN
            IF _fbJson.HasMember(_jsonDoc, 'to') THEN
                _jsonVal := _fbJson.FindMember(_jsonDoc, 'to');
                _fbJson.CopyString(_jsonVal, _sDeviceName, SIZEOF(_sDeviceName));
            END_IF

            IF _fbJson.HasMember(_jsonDoc, 'id') THEN
                _jsonVal    := _fbJson.FindMember(_jsonDoc, 'id');
                _nMessageId := _fbJson.GetUint64(_jsonVal);
            END_IF
        END_IF
    END_IF

    __DELETE(_pPayload);
END_IF
```

## GetJsonDomContent — Parse HTTP Response Directly (from Tc3_MieleAtHome)

Skip `GetContent` + manual `ParseDocument` — parse the response body in one call:

```iecst
VAR
    _fbJson    : FB_JsonDomParser;   // Static parser works here
    _fbRequest : FB_IotHttpRequest;
    _jsonDoc   : SJsonValue;
END_VAR

_jsonDoc := _fbRequest.GetJsonDomContent(_fbJson);

IF _jsonDoc <> 0 THEN
    // Navigate normally
    IF _fbJson.HasMember(_jsonDoc, 'accessToken') THEN
        _jsonVal := _fbJson.FindMember(_jsonDoc, 'accessToken');
        _fbJson.CopyString(_jsonVal, sAccessToken, SIZEOF(sAccessToken));
    END_IF
END_IF
```

## Nested Object Navigation

For JSON like: `{"result": {"output": true, "apower": 42.5, "aenergy": {"total": 1234.5}}}`

```iecst
IF _fbJson.HasMember(_jsonDoc, 'result') THEN
    _jsonVal := _fbJson.FindMember(_jsonDoc, 'result');

    _jsonVal2            := _fbJson.FindMember(_jsonVal, 'output');
    bSwitchState         := _fbJson.GetBool(_jsonVal2);

    _jsonVal2            := _fbJson.FindMember(_jsonVal, 'apower');
    stMeasurement.fPower := _fbJson.GetDouble(_jsonVal2);

    IF _fbJson.HasMember(_jsonVal, 'aenergy') THEN
        _jsonVal2             := _fbJson.FindMember(_jsonVal, 'aenergy');
        _jsonVal2             := _fbJson.FindMember(_jsonVal2, 'total');
        stMeasurement.fEnergy := _fbJson.GetDouble(_jsonVal2);
    END_IF
END_IF
```

## Deep Nesting (from Tc3_MieleAtHome)

Real-world API: `ident.deviceIdentLabel.fabNumber`, `ident.deviceIdentLabel.swids[]`

```iecst
IF fbJson.HasMember(_jsonIdent, 'deviceIdentLabel') THEN
    _jsonType := fbJson.FindMember(_jsonIdent, 'deviceIdentLabel');

    IF _jsonType <> 0 THEN
        IF fbJson.HasMember(_jsonType, 'fabNumber') THEN
            _jsonItem := fbJson.FindMember(_jsonType, 'fabNumber');
            fbJson.CopyString(_jsonItem, stDevice.stIdent.sFabNumber, SIZEOF(stDevice.stIdent.sFabNumber));
        END_IF

        // Nested array: deviceIdentLabel.swids[]
        IF fbJson.HasMember(_jsonType, 'swids') THEN
            _jsonItem   := fbJson.FindMember(_jsonType, 'swids');
            _nArraySize := fbJson.GetArraySize(_jsonItem);

            FOR _idx := 1 TO MIN(_nArraySize, cMaxSwids) DO
                _jsonValue := fbJson.GetArrayValueByIdx(_jsonItem, _idx - 1);
                fbJson.CopyString(
                    _jsonValue,
                    stDevice.stIdent.arrSwids[_idx],
                    SIZEOF(stDevice.stIdent.arrSwids[_idx]));
            END_FOR
        END_IF
    END_IF
END_IF
```

### value_raw Pattern

Miele API uses `{"type": {"value_raw": 2, "value_localized": "Oven"}}`:

```iecst
IF fbJson.HasMember(_jsonType, 'value_raw') THEN
    _jsonItem          := fbJson.FindMember(_jsonType, 'value_raw');
    stDevice.nDeviceType := TO_INT(fbJson.GetInt(_jsonItem));
END_IF
```

## FindMemberPath Shortcut

Navigate dotted paths in one call (available in `FB_JsonDynDomParser`):

```iecst
_jsonVal := _fbJson.FindMemberPath(_jsonDoc, 'result.aenergy.total');

IF _jsonVal <> 0 THEN
    stMeasurement.fEnergy := _fbJson.GetDouble(_jsonVal);
END_IF
```

## Object Iteration — MemberBegin/End/Next (from Tc3_MieleAtHome)

When keys are dynamic (e.g. device IDs as keys), iterate all members:

```iecst
_jsonIterator    := _fbJson.MemberBegin(_jsonDoc);
_jsonIteratorEnd := _fbJson.MemberEnd(_jsonDoc);
_idx             := 0;

WHILE _jsonIterator <> _jsonIteratorEnd DO
    IF _idx < cMaxDevices THEN
        _idx       := _idx + 1;
        _jsonValue := _fbJson.GetMemberValue(_jsonIterator);

        // Key = device ID string
        stDevices[_idx].sID := _fbJson.GetMemberName(_jsonIterator);

        // Value = device object — navigate its children
        SplitDevices(
            fbJson   := _fbJson,
            jsonDoc  := _jsonValue,
            stDevice := stDevices[_idx]);
    ELSE
        EXIT;
    END_IF

    _jsonIterator := _fbJson.NextMember(_jsonIterator);
END_WHILE
```

## Array Iteration — Iterator-Based

```iecst
_jsonVal := _fbJson.FindMember(_jsonDoc, 'results');

IF _jsonVal <> 0 THEN
    _jsonIterator    := _fbJson.ArrayBegin(_jsonVal);
    _jsonIteratorEnd := _fbJson.ArrayEnd(_jsonVal);

    WHILE _jsonIterator <> _jsonIteratorEnd DO
        _jsonVal2 := _fbJson.GetArrayValue(_jsonIterator);

        _jsonVal3 := _fbJson.FindMember(_jsonVal2, 'name');
        _fbJson.CopyString(_jsonVal3, _sName, SIZEOF(_sName));

        _jsonIterator := _fbJson.NextArray(_jsonIterator);
    END_WHILE
END_IF
```

## Array Access — Index-Based (from Tc3_MieleAtHome)

### GetArraySize + GetArrayValueByIdx

```iecst
_nArraySize := fbJson.GetArraySize(_jsonArray);

IF _nArraySize > 0 THEN
    FOR _idx := 1 TO MIN(_nArraySize, cMaxItems) DO
        _jsonValue := fbJson.GetArrayValueByIdx(_jsonArray, _idx - 1);  // 0-based!

        // Extract from each element
        SplitPrograms(fbJson, _jsonValue, stDevice.arrPrograms[_idx]);
    END_FOR
END_IF
```

### Fixed-Size Array (e.g. [hours, minutes])

```iecst
_nArraySize := fbJson.GetArraySize(_jsonType);

IF _nArraySize = 2 THEN
    _nMinutes := TO_INT(fbJson.GetInt(fbJson.GetArrayValueByIdx(_jsonType, 0))) * 60;
    _nMinutes := _nMinutes + TO_INT(fbJson.GetInt(fbJson.GetArrayValueByIdx(_jsonType, 1)));
    stDevice.nRemainingTime := _nMinutes;
END_IF
```

### Bounded Array (with overflow protection)

```iecst
_nArraySize := fbJson.GetArraySize(_jsonAction);

IF _nArraySize > 0 THEN
    FOR _idx := 1 TO MIN(_nArraySize, cMaxProcessActions) DO
        _jsonItem                        := fbJson.GetArrayValueByIdx(_jsonAction, _idx - 1);
        stDevice.arrProcessActions[_idx] := TO_INT(fbJson.GetInt(_jsonItem));
    END_FOR
END_IF
```

## Extraction Methods Reference

| Method | Returns | Use For |
|--------|---------|---------|
| `CopyString(val, dest, sizeof)` | `BOOL` | String values |
| `GetBool(val)` | `BOOL` | Boolean values |
| `GetInt(val)` | `DINT` | Signed integers |
| `GetUint(val)` | `UDINT` | Unsigned integers |
| `GetUint64(val)` | `ULINT` | Large unsigned (timestamps) |
| `GetDouble(val)` | `LREAL` | Floating point |
| `HasMember(parent, key)` | `BOOL` | Check if key exists |
| `FindMember(parent, key)` | `SJsonValue` | Get child by key |
| `FindMemberPath(root, path)` | `SJsonValue` | Get nested by dotted path |
| `GetArraySize(arr)` | `UDINT` | Array length |
| `GetArrayValueByIdx(arr, idx)` | `SJsonValue` | Element by 0-based index |
| `ArrayBegin(arr)` | `SJsonAIterator` | Start array iteration |
| `ArrayEnd(arr)` | `SJsonAIterator` | End sentinel |
| `NextArray(iter)` | `SJsonAIterator` | Advance iterator |
| `GetArrayValue(iter)` | `SJsonValue` | Get current element |
| `MemberBegin(obj)` | `SJsonMIterator` | Start object iteration |
| `MemberEnd(obj)` | `SJsonMIterator` | End sentinel |
| `NextMember(iter)` | `SJsonMIterator` | Advance iterator |
| `GetMemberName(iter)` | `STRING` | Current member key |
| `GetMemberValue(iter)` | `SJsonValue` | Current member value |
| `GetJsonDomContent(fbParser)` | `SJsonValue` | Parse HTTP response as DOM |
