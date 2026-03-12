# Logging Patterns

## Edge-Detected State Logging

Never log every cycle. Use memory variables to detect transitions and log only on change.

### Connection State Changes

```iecst
VAR_INST
    _bConnectedMem : BOOL;
END_VAR
```

```iecst
IF _bConnected <> _bConnectedMem THEN
    _bConnectedMem := _bConnected;

    IF _bConnected THEN
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Info,
                sPath := _sPath,
                sFmt  := 'Connected: %s:%s',
                sArg1 := _stParam.sHostName,
                sArg2 := UINT_TO_STRING(_stParam.nHostPort));

        _nConnectionCount := _nConnectionCount + 1;
    ELSE
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Warning,
                sPath := _sPath,
                sFmt  := 'Disconnected',
                sArg1 := '',
                sArg2 := '');
    END_IF
END_IF
```

### Error State Changes

```iecst
VAR_INST
    _bClientErrorMem : BOOL;
END_VAR
```

```iecst
_bClientError := _fbClient.bError;

IF _bClientError <> _bClientErrorMem THEN
    _bClientErrorMem := _bClientError;

    IF _bClientError THEN
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Error,
                sPath := _sPath,
                sFmt  := 'fbClient.Error: %s',
                sArg1 := DWORD_TO_HEXSTR(HRESULT_TO_DWORD(hrErrorCode), 8, 0),
                sArg2 := '');
    ELSE
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Info,
                sPath := _sPath,
                sFmt  := 'fbClient.Error=Released',
                sArg1 := '',
                sArg2 := '');
    END_IF
END_IF
```

### MQTT Connection State (Enum Change)

```iecst
IF eConnectionState <> _fbCommunicator.eConnectionState THEN
    IF _fbCommunicator.eConnectionState <> ETcIotMqttClientState.MQTT_ERR_SUCCESS THEN
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Error,
                sPath := _sPath,
                sFmt  := 'fbCommunicator.eConnectionState: %s',
                sArg1 := F_IotETcIotMqttClientState_TO_String(_fbCommunicator.eConnectionState),
                sArg2 := '');
    ELSE
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Info,
                sPath := _sPath,
                sFmt  := 'fbCommunicator.eConnectionState: %s',
                sArg1 := F_IotETcIotMqttClientState_TO_String(_fbCommunicator.eConnectionState),
                sArg2 := '');
    END_IF

    eConnectionState := _fbCommunicator.eConnectionState;
END_IF
```

## HTTP Request/Response Logging

### Before Sending Request (Debug)

```iecst
F_IoT_Utilities_MessageLog(
        eMode := Param_MyLib.cnMessageLog,
        eMask := E_IoT_Utilities_MessageLog.Debug,
        sPath := _sPath,
        sFmt  := 'fbRequest.SendRequest: %s Size: %s',
        sArg1 := CONCAT(sHostName, sUri),
        sArg2 := TO_STRING(nSize));
```

### Success Response (Debug)

```iecst
IF _fbRequest.nStatusCode >= 200 AND _fbRequest.nStatusCode <= 207 THEN
    F_IoT_Utilities_MessageLog(
            eMode := Param_MyLib.cnMessageLog,
            eMask := E_IoT_Utilities_MessageLog.Debug,
            sPath := _sPath,
            sFmt  := 'fbRequest.nStatusCode: %s %s',
            sArg1 := F_HttpStatusCodeToString(_fbRequest.nStatusCode),
            sArg2 := sContent);
```

### Unexpected Status Code (Error)

```iecst
ELSE
    F_IoT_Utilities_MessageLog(
            eMode := Param_MyLib.cnMessageLog,
            eMask := E_IoT_Utilities_MessageLog.Error,
            sPath := _sPath,
            sFmt  := 'fbRequest.nStatusCode: %s %s',
            sArg1 := F_HttpStatusCodeToString(_fbRequest.nStatusCode),
            sArg2 := sContent);
END_IF
```

### Request Error (Error)

```iecst
IF _fbRequest.bError THEN
    F_IoT_Utilities_MessageLog(
            eMode := Param_MyLib.cnMessageLog,
            eMask := E_IoT_Utilities_MessageLog.Error,
            sPath := _sPath,
            sFmt  := 'fbRequest.Error: %s',
            sArg1 := F_HttpRequestErrorToString(_fbRequest.eErrorId),
            sArg2 := '');
END_IF
```

### Invalid Input Data (Warning)

```iecst
IF pData = 0 OR nSize = 0 THEN
    F_IoT_Utilities_MessageLog(
            eMode := Param_MyLib.cnMessageLog,
            eMask := E_IoT_Utilities_MessageLog.Warning,
            sPath := _sPath,
            sFmt  := 'fbRequest.SendRequest: %s Size: %s',
            sArg1 := CONCAT(sHostName, sUri),
            sArg2 := TO_STRING(nSize));

    _bError := TRUE;
    RETURN;
END_IF
```

## Modbus Device Logging

### Register Read Error

```iecst
F_IoT_Utilities_MessageLog(
        eMode := Param_MyLib.cnMessageLog,
        eMask := E_IoT_Utilities_MessageLog.Error,
        sPath := _sPath,
        sFmt  := 'FB_MBReadInputRegs.Error: %s',
        sArg1 := BOOL_TO_STRING(_fbReadRegs.bError),
        sArg2 := '');
```

### Connection Retry

```iecst
F_IoT_Utilities_MessageLog(
        eMode := Param_MyLib.cnMessageLog,
        eMask := E_IoT_Utilities_MessageLog.Warning,
        sPath := _sPath,
        sFmt  := 'Retry %s/%s: %s',
        sArg1 := UINT_TO_STRING(nRetryCount),
        sArg2 := UINT_TO_STRING(cMaxRetries));
```

## Persistent Data Logging

```iecst
IF NOT _fbWritePersistentData.BUSY THEN
    IF NOT _fbWritePersistentData.ERR THEN
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Debug,
                sPath := THIS^._sPath,
                sFmt  := 'fbWritePersistentData.AmsNetId:%s Port: %s',
                sArg1 := sAmsNetId,
                sArg2 := UINT_TO_STRING(nPort));
    ELSE
        F_IoT_Utilities_MessageLog(
                eMode := Param_MyLib.cnMessageLog,
                eMask := E_IoT_Utilities_MessageLog.Error,
                sPath := THIS^._sPath,
                sFmt  := 'fbWritePersistentData.Error= %s',
                sArg1 := DWORD_TO_HEXSTR(UDINT_TO_DWORD(_fbWritePersistentData.ERRID), 8, 0),
                sArg2 := '');
    END_IF
END_IF
```

## Direct ADSLOGSTR with FormatString Helpers

For one-off logging outside the `F_IoT_Utilities_MessageLog` pattern (e.g. telemetry logging):

```iecst
ADSLOGSTR(
        msgCtrlMask := ADSLOG_MSGTYPE_HINT,
        msgFmtStr   := F_IoT_Utilities_FormatString_6(
                sFormat := 'Telemetry: AdsPath: (%s) Widget: (%s %s) (Value: %s Field: %s Datatype: %s)',
                arg1    := sAdsPath,
                arg2    := sViewPath,
                arg3    := sDisplayName,
                arg4    := sValue,
                arg5    := TO_STRING(eField),
                arg6    := TO_STRING(eDatatype)),
        strArg := '');
```

## Level Selection Guide

| Situation | Level | Example |
|-----------|-------|---------|
| System unusable, data loss | `Critical` | Memory allocation failed |
| Operation failed, needs attention | `Error` | HTTP 500, MQTT disconnect with error, Modbus read failure |
| Unexpected but recoverable | `Warning` | Invalid input data (pData=0), retry, buffer overflow truncation |
| Normal lifecycle events | `Info` | Connected, Disconnected, Error released, State changes |
| Operational details | `Debug` | Every send/receive, status codes, payload sizes, timing data |

## Formatting Conventions

- Use `%s` placeholders only (the underlying `FB_FormatString` is used with `F_STRING`)
- Always provide both `sArg1` and `sArg2` (use `''` for unused args)
- Use explicit type conversions: `UINT_TO_STRING()`, `TO_STRING()`, `UDINT_TO_STRING()`
- Use `DWORD_TO_HEXSTR(code, 8, 0)` for HRESULT/error codes
- Use `CONCAT()` to build compound args when format slots are limited
- Keep format strings descriptive: `'fbRequest.nStatusCode: %s %s'` not `'Status: %s %s'`
