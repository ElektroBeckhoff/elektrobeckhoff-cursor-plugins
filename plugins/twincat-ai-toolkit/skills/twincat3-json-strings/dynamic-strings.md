# Dynamic Strings & Memory Patterns

## __NEW / __DELETE Basics

TwinCAT3 normally uses compile-time allocation. Dynamic memory is the exception, used primarily for JSON payloads that can vary in size.

### Allocate

```iecst
_nPayloadSize := _fbMessage.nPayloadSize + 1;  // +1 for null terminator
_pPayload     := __NEW(BYTE, _nPayloadSize);
```

### Null Check (mandatory)

```iecst
IF _pPayload <> 0 THEN
    // Safe to use
ELSE
    // Allocation failed - handle error
    hrErrorCode := E_HRESULTAdsErr.NOMEMORY;
END_IF
```

### Free (always in same scope)

```iecst
__DELETE(_pPayload);
```

### Complete Pattern

```iecst
_pPayload := __NEW(BYTE, _nPayloadSize);

IF _pPayload <> 0 THEN
    // ... use buffer ...
    __DELETE(_pPayload);
END_IF
```

## Reuse Pattern (FB_IoT_ComClient)

For FBs that build payloads across multiple cycles:

```iecst
// In VAR section
VAR
    _pSendPayload        : POINTER TO BYTE;
    _nSendPayloadSize    : UDINT;
    _bSendPayloadCreated : BOOL;
END_VAR

// Create method
METHOD _CreateSendPayload : BOOL
    IF NOT _bSendPayloadCreated THEN
        _nSendPayloadSize := _fbJsonWriter.GetDocumentLength();

        IF _nSendPayloadSize > 0 THEN
            _pSendPayload := __NEW(BYTE, _nSendPayloadSize);

            IF _pSendPayload <> 0 THEN
                _bSendPayloadCreated := TRUE;
                _CreateSendPayload   := TRUE;
            END_IF
        END_IF
    END_IF

// Delete method
METHOD _DeleteSendPayload
    IF _bSendPayloadCreated THEN
        __DELETE(_pSendPayload);
        _bSendPayloadCreated := FALSE;
        _nSendPayloadSize    := 0;
    END_IF
```

## POINTER TO STRING vs POINTER TO BYTE

```iecst
// For raw byte buffers (JSON, binary)
_pPayload : POINTER TO BYTE;
_pPayload := __NEW(BYTE, nSize);

// For string operations
_pString : POINTER TO STRING;
// Usually NOT dynamically allocated - use fixed STRING variables instead
```

## String Types

| Type | Size | Use |
|------|------|-----|
| `STRING` | 80 chars default | General purpose |
| `STRING(255)` | 255 chars | Longer strings |
| `T_MaxString` | 255 chars | Standard Beckhoff alias |
| `T_IoT_PathString` | Custom | IoT widget paths |
| `T_IoT_NameString` | Custom | Display names |
| `T_IoT_EventString` | Custom | Event JSON strings |
| `T_IoT_TelemetryString` | Custom | Telemetry JSON strings |

## String Operations

### Concatenation

```iecst
sResult := CONCAT(sPrefix, sSuffix);
sResult := CONCAT(CONCAT(sPart1, '/'), sPart2);  // Nested for 3+ parts
```

### Format Strings (FB_FormatString)

```iecst
_fbFormat(
    sFormat := 'Device %s: Power = %d W',
    arg1    := F_STRING(sDeviceName),
    arg2    := F_DINT(nPower),
    sOut    => sLogMessage,
    bError  =>);
```

### Library-specific Format Helpers

Pattern: `F_[Lib]FormatString_[N]` where N = number of arguments

```iecst
// Shelly RPC topic
sTopic := F_ShellyFormatString_2(
    sFmt  := '%s/rpc',
    sArg1 := sShellyPrefix);

// EasyMqtt message topic
sTopic := F_EasyMqttFormatString_3(
    sFmt  := '%s/EasyMqtt/%s/%s',
    sArg1 := sMainTopic,
    sArg2 := sDeviceName,
    sArg3 := sSubTopic);
```

### String Search and Split

```iecst
// Find substring position
nPos := FIND2(sHaystack, sNeedle);  // 0 = not found

// String length
nLen := LEN2(sInput);

// Split by separator
FindAndSplit(
    pSrcString  := ADR(sInput),
    pLeftString := ADR(sLeft),
    pRightString := ADR(sRight),
    nSeparator  := 16#2C);  // comma = 0x2C

// Split by character
FindAndSplitChar(
    sInput     := sInput,
    cSeparator := ',',
    sLeft      => sLeft,
    sRight     => sRight);
```

### UTF-8 Conversion

```iecst
sUtf8 := F_Iot_Convert_String_To_UTF8(sInput := sAnsiString);
```

### MEMCPY / MEMSET

```iecst
// Copy raw bytes
MEMCPY(
    destAddr := ADR(stDest),
    srcAddr  := ADR(stSource),
    n        := SIZEOF(stSource));

// Clear buffer
MEMSET(
    destAddr := ADR(_arrBuffer),
    fillByte := 0,
    n        := SIZEOF(_arrBuffer));
```

## Common Pitfalls

1. **Forgetting `__DELETE`** -> memory leak (PLC has limited heap)
2. **Using `__DELETE` on already-freed pointer** -> access violation
3. **Not checking `<> 0` after `__NEW`** -> null pointer dereference
4. **Buffer too small for `CopyString`** -> truncated data (use `SIZEOF`)
5. **Missing null terminator** -> always allocate `nPayloadSize + 1`
6. **String overflow** -> `STRING(80)` can't hold more than 80 chars, use `T_MaxString` or larger
