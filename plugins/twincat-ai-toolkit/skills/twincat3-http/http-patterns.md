# HTTP(S) REST Communication in TwinCAT3

Complete reference for building HTTP(S) client FBs with `Tc3_IotBase`.
Based on the working implementation in **Tc3_Seven_io** (`FB_Seven_io_Client`).

---

## 1. Required Libraries

```xml
<PlaceholderReference Include="Tc3_IotBase">
  <DefaultResolution>Tc3_IotBase, * (Beckhoff Automation GmbH)</DefaultResolution>
  <Namespace>Tc3_IotBase</Namespace>
</PlaceholderReference>
<PlaceholderReference Include="Tc3_JsonXml">
  <DefaultResolution>Tc3_JsonXml, * (Beckhoff Automation GmbH)</DefaultResolution>
  <Namespace>Tc3_JsonXml</Namespace>
</PlaceholderReference>
```

---

## 2. Mandatory FB Structure

Every HTTP client FB **MUST** have these internal state variables:

```iecst
VAR
    // --- Mandatory internal state (ALWAYS present) ---
    _bBusy      : BOOL;       // TRUE while any request is in flight
    _bConnected : BOOL;       // TRUE after successful response, FALSE after client error
    _bError     : BOOL;       // TRUE after any error (client, request, or status code)
    _sError     : T_MaxString; // Human-readable error text

    // --- Beckhoff HTTP FBs ---
    _fbClient  : FB_IotHttpClient;
    _fbRequest : FB_IotHttpRequest;
    _fbHeader  : FB_IotHttpHeaderFieldMap;

    // --- JSON (if API uses JSON) ---
    _fbJson    : FB_JsonDynDomParser;
    _fbWrite   : FB_JsonSaxWriter;
    _jsonDoc   : SJsonValue;

    // --- Init & Config ---
    _bInitClient : BOOL := TRUE;
    _sUri        : T_MaxString;
    _sContent    : T_MaxString;

    // --- Dynamic JSON payload ---
    {attribute 'TcEncoding':='UTF-8'}
    _pJsonPayload     : POINTER TO STRING;
    _nJsonPayloadSize : UDINT;

    // --- Timeout recovery ---
    _fbTonTimeout : TON;

    // --- Instance path for logging ---
    {attribute 'instance-path'}
    {attribute 'noinit'}
    _sPath : T_MaxString;
END_VAR
```

### VAR_OUTPUT (expose to user)

```iecst
VAR_OUTPUT
    bConnected : BOOL;
    bBusy      : BOOL;
    bError     : BOOL;
END_VAR
```

### Properties (read-only access)

```iecst
PROPERTY IsConnected : BOOL   // GET: returns _bConnected
PROPERTY IsBusy      : BOOL   // GET: returns _bBusy
PROPERTY IsError     : BOOL   // GET: returns _bError
PROPERTY ErrorText   : T_MaxString // GET: returns _sError
```

---

## 3. Execute Method

Called every PLC cycle. Handles init, client execution, timeout, and connection status.

```iecst
METHOD Execute : BOOL

IF NOT _bValid THEN
    RETURN;
END_IF

// --- Init (once) ---
IF _bInitClient THEN
    _fbClient.sHostName                := _stParam.sHostName;
    _fbClient.nHostPort                := _stParam.nHostPort;
    _fbClient.bKeepAlive               := _stParam.bKeepAlive;
    _fbClient.tConnectionTimeout       := _stParam.tConnectionTimeout;
    _fbClient.stTLS.bNoServerCertCheck := _stParam.bNoServerCertCheck;
    _fbClient.stTLS.sCA                := _stParam.sCA;
    _fbClient.stTLS.sCert              := _stParam.sCert;
    _fbClient.stTLS.sKeyFile           := _stParam.sKeyFile;
    _fbClient.stTLS.sKeyPwd            := _stParam.sKeyPwd;
    _bInitClient                       := FALSE;

    _fbRequest.sContentType := 'application/json; charset=utf-8';

    _fbHeader.AddField('Accept', 'application/json', FALSE);
    _fbHeader.AddField('X-Api-Key', _stParam.sApiToken, FALSE);

    _fbClient.Disconnect();
    RETURN;
ELSE
    _fbClient.Execute();
END_IF

// --- Timeout recovery (single timer for all) ---
_fbTonTimeout(IN := _bBusy, PT := _stParam.tConnectionTimeout * 2);

IF _fbTonTimeout.Q THEN
    MEMSET(destAddr := ADR(_bBusy), fillByte := 0, n := SIZEOF(_bBusy));
    MEMSET(destAddr := ADR(_fbRequest.bBusy), fillByte := 0, n := SIZEOF(_fbRequest.bBusy));
    _bError := TRUE;
    _sError := 'Timeout: request stuck';
END_IF

// --- Update outputs ---
bConnected := _bConnected;
bBusy      := _bBusy;
bError     := _bError;
```

### Key rules:
- `_fbClient.Execute()` MUST be called every cycle (after init)
- ONE `TON` timer on `_bBusy` for timeout recovery (not two separate timers)
- If `_fbTonTimeout.Q` fires, force-reset both `_bBusy` and `_fbRequest.bBusy` via MEMSET

---

## 4. Send Method Template (State Machine)

Every HTTP method uses a 2-state `CASE` machine. The return value signals "method finished" (not "success").

### Rules:
- State 0: Build request + send
- State 1: Evaluate response with **flat ELSIF chain** (NOT deep nesting)
- `_bBusy`/`_nState` reset happens ONCE at the end of State 1
- `SendXyz := TRUE` only in State 1 when fully processed
- **ALWAYS** validate `_jsonDoc <> 0` after `GetJsonDomContent`
- Use `VAR_INST` for `_nState` so each method has its own state

### Complete Template: HTTP GET

```iecst
METHOD INTERNAL SendGetXyz : BOOL
VAR_INST
    _nState : UDINT;
END_VAR

CASE _nState OF
    0: // --- Build & Send ---
        IF NOT _bBusy THEN
            _bBusy  := TRUE;
            _bError := FALSE;
            _sError := '';
            _sUri   := '/api/xyz';

            IF _fbRequest.SendRequest(
                    sUri         := _sUri,
                    fbClient     := _fbClient,
                    eRequestType := ETcIotHttpRequestType.HTTP_GET,
                    pContent     := 0,
                    nContentSize := 0,
                    fbHeader     := _refHeader) THEN
                _nState := 1;
            END_IF
        END_IF

    1: // --- Evaluate Response (flat ELSIF) ---
        IF _fbClient.bError THEN
            // Level 1: Client error (no connection at all)
            _sError     := DWORD_TO_HEXSTR(DINT_TO_DWORD(_fbClient.hrErrorCode), 8, 0);
            _bError     := TRUE;
            _bConnected := FALSE;
            _bBusy      := FALSE;
            _nState     := 0;
            SendGetXyz  := TRUE;

        ELSIF NOT _fbRequest.bBusy THEN
            IF NOT _fbRequest.bError
               AND _fbRequest.nStatusCode >= 200
               AND _fbRequest.nStatusCode <= 207 THEN
                // --- Success: Parse JSON ---
                _jsonDoc := _fbRequest.GetJsonDomContent(_fbJson);

                IF _jsonDoc <> 0 THEN
                    // Navigate DOM here...
                END_IF

                _bError     := FALSE;
                _bConnected := TRUE;

            ELSIF _fbRequest.bError THEN
                // Level 2: Request error (TLS, connection, timeout, etc.)
                _sError     := F_[Lib]_HttpRequestErrorToString(_fbRequest.eErrorId);
                _bError     := TRUE;
                _bConnected := FALSE;

            ELSE
                // Level 3: Bad HTTP status code (server responded but rejected)
                _fbRequest.GetContent(ADR(_sContent), SIZEOF(_sContent), TRUE);
                _sError     := CONCAT('HTTP ', TO_STRING(_fbRequest.nStatusCode));
                _bError     := TRUE;
                _bConnected := TRUE;
            END_IF

            _bBusy     := FALSE;
            _nState    := 0;
            SendGetXyz := TRUE;
        END_IF

END_CASE
```

### Complete Template: HTTP POST with JSON Body

```iecst
METHOD INTERNAL SendPostXyz : BOOL
VAR_IN_OUT
    stData : ST_[Lib]_SomeData;
END_VAR
VAR_INST
    _nState : UDINT;
END_VAR

CASE _nState OF
    0: // --- Build JSON & Send ---
        IF NOT _bBusy THEN
            _bBusy  := TRUE;
            _bError := FALSE;
            _sError := '';
            _sUri   := '/api/xyz';

            _fbWrite.ResetDocument();
            _fbWrite.StartObject();
            _fbWrite.AddKeyString('to', stData.sRecipient);
            _fbWrite.AddKeyString('text', stData.sMessage);
            _fbWrite.EndObject();
            _nJsonPayloadSize := _fbWrite.GetDocumentLength();

            IF _nJsonPayloadSize > 0 THEN
                _pJsonPayload := __NEW(BYTE, _nJsonPayloadSize);

                IF _pJsonPayload <> 0 THEN
                    _fbWrite.CopyDocument(_pJsonPayload^, _nJsonPayloadSize);

                    IF _fbRequest.SendRequest(
                            sUri         := _sUri,
                            fbClient     := _fbClient,
                            eRequestType := ETcIotHttpRequestType.HTTP_POST,
                            pContent     := _pJsonPayload,
                            nContentSize := _nJsonPayloadSize - 1,
                            fbHeader     := _refHeader) THEN
                        _nState := 1;
                    END_IF
                END_IF

                __DELETE(_pJsonPayload);
            END_IF
        END_IF

    1: // --- Evaluate Response (flat ELSIF) ---
        IF _fbClient.bError THEN
            _sError      := DWORD_TO_HEXSTR(DINT_TO_DWORD(_fbClient.hrErrorCode), 8, 0);
            _bError      := TRUE;
            _bConnected  := FALSE;
            _bBusy       := FALSE;
            _nState      := 0;
            SendPostXyz  := TRUE;

        ELSIF NOT _fbRequest.bBusy THEN
            IF NOT _fbRequest.bError
               AND _fbRequest.nStatusCode >= 200
               AND _fbRequest.nStatusCode <= 207 THEN
                _jsonDoc := _fbRequest.GetJsonDomContent(_fbJson);

                IF _jsonDoc <> 0 THEN
                    // Parse response fields...
                END_IF

                _bError     := FALSE;
                _bConnected := TRUE;

            ELSIF _fbRequest.bError THEN
                _sError     := F_[Lib]_HttpRequestErrorToString(_fbRequest.eErrorId);
                _bError     := TRUE;
                _bConnected := FALSE;

            ELSE
                _fbRequest.GetContent(ADR(_sContent), SIZEOF(_sContent), TRUE);
                _sError     := CONCAT('HTTP ', TO_STRING(_fbRequest.nStatusCode));
                _bError     := TRUE;
                _bConnected := TRUE;
            END_IF

            _bBusy      := FALSE;
            _nState     := 0;
            SendPostXyz := TRUE;
        END_IF

END_CASE
```

---

## 5. Error Evaluation (3 Levels)

Every response MUST be evaluated at three levels. The ELSIF chain in State 1 handles this:

| Level | Condition | Meaning | `_bConnected` | `_bError` |
|-------|-----------|---------|---------------|-----------|
| 1 | `_fbClient.bError` | No connection (DNS, network, TLS handshake) | `FALSE` | `TRUE` |
| 2 | `_fbRequest.bError` | Request failed (timeout, parse error, etc.) | `FALSE` | `TRUE` |
| 3 | `nStatusCode < 200 OR > 207` | Server responded but rejected (4xx, 5xx) | `TRUE` | `TRUE` |
| OK | `nStatusCode >= 200 AND <= 207` | Success | `TRUE` | `FALSE` |

### Error text sources per level

```iecst
// Level 1: Client error -> hex HRESULT
_sError := DWORD_TO_HEXSTR(DINT_TO_DWORD(_fbClient.hrErrorCode), 8, 0);

// Level 2: Request error -> human-readable via ETcIotHttpRequestError mapping
_sError := F_[Lib]_HttpRequestErrorToString(_fbRequest.eErrorId);

// Level 3: Bad status code -> response body
_fbRequest.GetContent(ADR(_sContent), SIZEOF(_sContent), TRUE);
_sError := CONCAT('HTTP ', TO_STRING(_fbRequest.nStatusCode));
```

---

## 6. ETcIotHttpRequestError to String Function

Every library that uses HTTP MUST include this error mapping function.
Replace `[Lib]` with your library prefix (e.g. `Seven_io`, `Influx`).

```iecst
{attribute 'hide'}
FUNCTION F_[Lib]_HttpRequestErrorToString : T_MaxString
VAR_INPUT
    eErrorId : ETcIotHttpRequestError;
END_VAR

CASE eErrorId OF
    ETcIotHttpRequestError.HTTP_REQ_ERR_BUSY:                    F_[Lib]_HttpRequestErrorToString := 'Request busy (BUSY)';
    ETcIotHttpRequestError.HTTP_REQ_ERR_SUCCESS:                 F_[Lib]_HttpRequestErrorToString := 'Success';
    ETcIotHttpRequestError.HTTP_REQ_ERR_NOMEM:                   F_[Lib]_HttpRequestErrorToString := 'Out of memory';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_PROTOCOL:         F_[Lib]_HttpRequestErrorToString := 'Protocol creation failed';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_INVAL:              F_[Lib]_HttpRequestErrorToString := 'Invalid connection';
    ETcIotHttpRequestError.HTTP_REQ_ERR_NO_CONN:                 F_[Lib]_HttpRequestErrorToString := 'No connection';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_REFUSED:            F_[Lib]_HttpRequestErrorToString := 'Connection refused';
    ETcIotHttpRequestError.HTTP_REQ_ERR_NOT_FOUND:               F_[Lib]_HttpRequestErrorToString := 'Resource not found';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_LOST:               F_[Lib]_HttpRequestErrorToString := 'Connection lost';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS:                     F_[Lib]_HttpRequestErrorToString := 'TLS error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_NOT_SUPPORTED:           F_[Lib]_HttpRequestErrorToString := 'Not supported';
    ETcIotHttpRequestError.HTTP_REQ_ERR_AUTH:                     F_[Lib]_HttpRequestErrorToString := 'Authentication failed';
    ETcIotHttpRequestError.HTTP_REQ_ERR_ACL_DENIED:              F_[Lib]_HttpRequestErrorToString := 'Access denied (ACL)';
    ETcIotHttpRequestError.HTTP_REQ_ERR_UNKNOWN:                 F_[Lib]_HttpRequestErrorToString := 'Unknown error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_ERRNO:                   F_[Lib]_HttpRequestErrorToString := 'System error (errno)';
    ETcIotHttpRequestError.HTTP_REQ_ERR_EAI:                     F_[Lib]_HttpRequestErrorToString := 'Address resolution error (EAI)';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PROXY:                   F_[Lib]_HttpRequestErrorToString := 'Proxy error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CA_NOTFOUND:         F_[Lib]_HttpRequestErrorToString := 'TLS CA certificate not found';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CERT_NOTFOUND:       F_[Lib]_HttpRequestErrorToString := 'TLS certificate not found';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_KEY_NOTFOUND:        F_[Lib]_HttpRequestErrorToString := 'TLS key not found';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CA_INVALID:          F_[Lib]_HttpRequestErrorToString := 'TLS CA certificate invalid';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CERT_INVALID:        F_[Lib]_HttpRequestErrorToString := 'TLS certificate invalid';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_KEY_INVALID:         F_[Lib]_HttpRequestErrorToString := 'TLS key invalid';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_VERIFY_FAIL:         F_[Lib]_HttpRequestErrorToString := 'TLS certificate verification failed';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_SETUP:               F_[Lib]_HttpRequestErrorToString := 'TLS setup failed';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_HANDSHAKE_FAIL:      F_[Lib]_HttpRequestErrorToString := 'TLS handshake failed';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CIPHER_INVALID:      F_[Lib]_HttpRequestErrorToString := 'TLS cipher invalid';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_VERSION_INVALID:     F_[Lib]_HttpRequestErrorToString := 'TLS version not supported';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_PSK_INVALID:         F_[Lib]_HttpRequestErrorToString := 'TLS PSK invalid';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CRL_NOTFOUND:        F_[Lib]_HttpRequestErrorToString := 'TLS CRL not found';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CRL_INVALID:         F_[Lib]_HttpRequestErrorToString := 'TLS CRL invalid';
    ETcIotHttpRequestError.HTTP_REQ_ERR_FINALIZE_DISCONNECT:     F_[Lib]_HttpRequestErrorToString := 'Disconnect finalization failed';
    ETcIotHttpRequestError.HTTP_REQ_ERR_BIND:                    F_[Lib]_HttpRequestErrorToString := 'Bind error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_BIND_ADDR_INUSE:         F_[Lib]_HttpRequestErrorToString := 'Address already in use';
    ETcIotHttpRequestError.HTTP_REQ_ERR_BIND_ADDR_INVAL:         F_[Lib]_HttpRequestErrorToString := 'Invalid address';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE:                  F_[Lib]_HttpRequestErrorToString := 'Request creation failed';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CREATE_TYPE:             F_[Lib]_HttpRequestErrorToString := 'Invalid request type';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN:                    F_[Lib]_HttpRequestErrorToString := 'Connection error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_TIMEDOUT:           F_[Lib]_HttpRequestErrorToString := 'Connection timed out';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CONN_HOSTUNREACH:        F_[Lib]_HttpRequestErrorToString := 'Host unreachable';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CERT_EXPIRED:        F_[Lib]_HttpRequestErrorToString := 'TLS certificate expired';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TLS_CN_MISMATCH:         F_[Lib]_HttpRequestErrorToString := 'TLS CN mismatch';
    ETcIotHttpRequestError.HTTP_REQ_ERR_INV_PARAM:               F_[Lib]_HttpRequestErrorToString := 'Invalid parameter';
    ETcIotHttpRequestError.HTTP_REQ_ERR_FIFO_FULL:               F_[Lib]_HttpRequestErrorToString := 'FIFO full';
    ETcIotHttpRequestError.HTTP_REQ_ERR_TCP_SEND:                F_[Lib]_HttpRequestErrorToString := 'TCP send error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_CANCELLED:               F_[Lib]_HttpRequestErrorToString := 'Request cancelled';
    ETcIotHttpRequestError.HTTP_REQ_ERR_RESPONSE_TIMEDOUT:       F_[Lib]_HttpRequestErrorToString := 'Response timed out';
    ETcIotHttpRequestError.HTTP_REQ_ERR_INV_HDR_SIZE:            F_[Lib]_HttpRequestErrorToString := 'Invalid header size';
    ETcIotHttpRequestError.HTTP_REQ_ERR_INV_ENCODING:            F_[Lib]_HttpRequestErrorToString := 'Invalid encoding';
    ETcIotHttpRequestError.HTTP_REQ_ERR_INV_CONTENT_SIZE:        F_[Lib]_HttpRequestErrorToString := 'Invalid content size';
    ETcIotHttpRequestError.HTTP_REQ_ERR_INV_CHUNK_SIZE:          F_[Lib]_HttpRequestErrorToString := 'Invalid chunk size';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_HDR:               F_[Lib]_HttpRequestErrorToString := 'Header parse error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_HDR_FIELD:         F_[Lib]_HttpRequestErrorToString := 'Header field parse error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_HDR_FIELD_NAME:    F_[Lib]_HttpRequestErrorToString := 'Invalid header field name';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_HDR_FIELD_VAL:     F_[Lib]_HttpRequestErrorToString := 'Invalid header field value';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_STATUS_LINE:       F_[Lib]_HttpRequestErrorToString := 'Status line parse error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_CHUNK:             F_[Lib]_HttpRequestErrorToString := 'Chunk parse error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_CHUNK_SIZE:        F_[Lib]_HttpRequestErrorToString := 'Chunk size error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_CHUNK_EXT_NAME:    F_[Lib]_HttpRequestErrorToString := 'Chunk extension name error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_CHUNK_EXT_VAL:     F_[Lib]_HttpRequestErrorToString := 'Chunk extension value error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_CHUNK_DATA:        F_[Lib]_HttpRequestErrorToString := 'Chunk data error';
    ETcIotHttpRequestError.HTTP_REQ_ERR_PARSE_CHUNK_TRAILER:     F_[Lib]_HttpRequestErrorToString := 'Chunk trailer error';
ELSE
    F_[Lib]_HttpRequestErrorToString := 'Unknown error code';
END_CASE
```

---

## 7. Authentication Patterns

### API Key Header (e.g. seven.io)

```iecst
_fbHeader.AddField(
    sField       := 'X-Api-Key',
    sValue       := _stParam.sApiToken,
    bAppendValue := FALSE);
_fbHeader.AddField(
    sField       := 'Accept',
    sValue       := 'application/json',
    bAppendValue := FALSE);
```

### Bearer Token (e.g. InfluxDB V2)

```iecst
_fbHeader.AddField(
    sField       := 'Authorization',
    sValue       := CONCAT('Token ', _stParam.sToken),
    bAppendValue := FALSE);
_fbHeader.AddField(
    sField       := 'Content-Type',
    sValue       := 'text/plain; charset=utf-8',
    bAppendValue := FALSE);
```

---

## 8. JSON Body: Build, Allocate, Send, Free

Always in State 0 of the Send method. Pattern:

```iecst
_fbWrite.ResetDocument();
_fbWrite.StartObject();
_fbWrite.AddKeyString('to', sRecipient);
_fbWrite.AddKeyString('text', sMessage);
_fbWrite.AddKeyNumber('count', nCount);
_fbWrite.EndObject();
_nJsonPayloadSize := _fbWrite.GetDocumentLength();

IF _nJsonPayloadSize > 0 THEN
    _pJsonPayload := __NEW(BYTE, _nJsonPayloadSize);

    IF _pJsonPayload <> 0 THEN
        _fbWrite.CopyDocument(_pJsonPayload^, _nJsonPayloadSize);

        IF _fbRequest.SendRequest(
                sUri         := _sUri,
                fbClient     := _fbClient,
                eRequestType := ETcIotHttpRequestType.HTTP_POST,
                pContent     := _pJsonPayload,
                nContentSize := _nJsonPayloadSize - 1,
                fbHeader     := _refHeader) THEN
            _nState := 1;
        END_IF
    END_IF

    __DELETE(_pJsonPayload);
END_IF
```

**Important**: `nContentSize := _nJsonPayloadSize - 1` (exclude null terminator).
`__DELETE` is outside the `SendRequest` IF — memory is freed same cycle regardless of send success.

---

## 9. JSON Response Parsing

**ALWAYS** validate `_jsonDoc <> 0` before accessing DOM:

```iecst
_jsonDoc := _fbRequest.GetJsonDomContent(_fbJson);

IF _jsonDoc <> 0 THEN
    // Simple member access
    IF (_jsonVal := _fbJson.FindMember(_jsonDoc, 'balance')) <> 0 THEN
        _fBalance := _fbJson.GetDouble(_jsonVal);
    END_IF

    // Array iteration
    IF _fbJson.HasMember(_jsonDoc, 'messages') THEN
        _jsonMessages    := _fbJson.FindMember(_jsonDoc, 'messages');
        _jsonIterator    := _fbJson.ArrayBegin(_jsonMessages);
        _jsonIteratorEnd := _fbJson.ArrayEnd(_jsonMessages);
        _idx             := 1;

        WHILE _jsonIterator <> _jsonIteratorEnd AND (_idx <= cMaxEntries) DO
            _jsonArrayValue := _fbJson.GetArrayValue(_jsonIterator);

            IF (_jsonVal := _fbJson.FindMember(_jsonArrayValue, 'id')) <> 0 THEN
                arrResult[_idx].nId := _fbJson.GetInt(_jsonVal);
            END_IF

            IF (_jsonVal := _fbJson.FindMember(_jsonArrayValue, 'name')) <> 0 THEN
                _fbJson.CopyString(_jsonVal, arrResult[_idx].sName, SIZEOF(arrResult[_idx].sName));
            END_IF

            _jsonIterator := _fbJson.NextArray(_jsonIterator);
            _idx          := _idx + 1;
        END_WHILE
    END_IF
END_IF
```

---

## 10. Client Configuration

Typically stored in a param struct and applied during init:

```iecst
_fbClient.sHostName                := _stParam.sHostName;
_fbClient.nHostPort                := _stParam.nHostPort;
_fbClient.bKeepAlive               := _stParam.bKeepAlive;
_fbClient.tConnectionTimeout       := _stParam.tConnectionTimeout;
_fbClient.stTLS.bNoServerCertCheck := _stParam.bNoServerCertCheck;
_fbClient.stTLS.sCA                := _stParam.sCA;
_fbClient.stTLS.sCert              := _stParam.sCert;
_fbClient.stTLS.sKeyFile           := _stParam.sKeyFile;
_fbClient.stTLS.sKeyPwd            := _stParam.sKeyPwd;
```

---

## 11. HTTP Methods Reference

| Method | Enum | Typical Use |
|--------|------|-------------|
| GET | `ETcIotHttpRequestType.HTTP_GET` | Read data, status queries |
| POST | `ETcIotHttpRequestType.HTTP_POST` | Send data, create resources |
| PUT | `ETcIotHttpRequestType.HTTP_PUT` | Update resources |
| DELETE | `ETcIotHttpRequestType.HTTP_DELETE` | Remove resources |

---

## 12. Compression

```iecst
_fbRequest.eCompressionMode := E_IotHttpCompressionMode.Gzip;
_fbRequest.eCompressionMode := E_IotHttpCompressionMode.NoCompression;  // Default
```

---

## 13. Checklist for New HTTP Library

When creating a new TwinCAT library that communicates via HTTP(S):

- [ ] `FB_[Lib]_Client` with `_bBusy`, `_bConnected`, `_bError`, `_sError`
- [ ] `Execute` method: init, `_fbClient.Execute()`, timeout recovery, output update
- [ ] `F_[Lib]_HttpRequestErrorToString` function (copy from Section 6, replace `[Lib]`)
- [ ] `ST_[Lib]_HttpParam` struct with host, port, token, TLS, timeout, log level
- [ ] `Param_[Lib]` GVL with constants (max entries, etc.)
- [ ] Each Send method: 2-state CASE, flat ELSIF in State 1, 3-level error eval
- [ ] `_jsonDoc <> 0` check after every `GetJsonDomContent`
- [ ] `__DELETE(_pJsonPayload)` in State 0 after SendRequest (not in State 1)
- [ ] Properties: `IsConnected`, `IsBusy`, `IsError`, `ErrorText`, `Balance` etc.
- [ ] Consumer FBs (e.g. `FB_[Lib]_SMS`) hold `REFERENCE TO FB_[Lib]_Client`
