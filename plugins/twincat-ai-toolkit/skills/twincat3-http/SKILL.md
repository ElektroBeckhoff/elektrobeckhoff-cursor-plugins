---
name: twincat3-http
description: HTTP(S) REST communication in TwinCAT3 using FB_IotHttpClient/FB_IotHttpRequest from Tc3_IotBase. Mandatory FB structure, Execute method, Send state machine, 3-level error evaluation, authentication, JSON body workflow. Use when implementing HTTP REST APIs, cloud connectivity, webhooks, or any HTTP(S) communication in TwinCAT3.
---

# HTTP(S) REST Communication (Tc3_IotBase)

> **Mandatory rules:** See `twincat3-http.mdc` for FB structure, Execute method, error evaluation, and JSON body rules.

## Quick Start

```
Task Progress:
- [ ] Step 1: Add Tc3_IotBase and Tc3_JsonXml library references
- [ ] Step 2: Create FB_[Lib]_Client with mandatory internal state
- [ ] Step 3: Create ST_[Lib]_HttpParam struct
- [ ] Step 4: Implement Execute method (init, client cycle, timeout recovery)
- [ ] Step 5: Implement Send methods (2-state CASE, flat ELSIF)
- [ ] Step 6: Create F_[Lib]_HttpRequestErrorToString function
- [ ] Step 7: Add properties (IsConnected, IsBusy, IsError, ErrorText)
- [ ] Step 8: Register all POUs/DUTs in .plcproj
```

## Required Libraries

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

## Core FBs

| FB | Purpose |
|----|---------|
| `FB_IotHttpClient` | HTTP connection (host, port, TLS) |
| `FB_IotHttpRequest` | Build and send request, read response |
| `FB_IotHttpHeaderFieldMap` | Custom headers (auth, content-type) |

## Step 2: Mandatory FB Structure

```iecst
VAR
    _bBusy      : BOOL;         // TRUE while any request is in flight
    _bConnected : BOOL;         // TRUE after successful response
    _bError     : BOOL;         // TRUE after any error
    _sError     : T_MaxString;  // Human-readable error text

    _fbClient  : FB_IotHttpClient;
    _fbRequest : FB_IotHttpRequest;
    _fbHeader  : FB_IotHttpHeaderFieldMap;

    _fbJson    : FB_JsonDynDomParser;
    _fbWrite   : FB_JsonSaxWriter;
    _jsonDoc   : SJsonValue;

    _bInitClient : BOOL := TRUE;
    _sUri        : T_MaxString;
    _sContent    : T_MaxString;

    {attribute 'TcEncoding':='UTF-8'}
    _pJsonPayload     : POINTER TO STRING;
    _nJsonPayloadSize : UDINT;

    _fbTonTimeout : TON;

    {attribute 'instance-path'}
    {attribute 'noinit'}
    _sPath : T_MaxString;
END_VAR
VAR_OUTPUT
    bConnected : BOOL;
    bBusy      : BOOL;
    bError     : BOOL;
END_VAR
```

## Step 4: Execute Method

See [http-patterns.md](http-patterns.md) Section 3 for the complete implementation.

Key rules:
- `_fbClient.Execute()` MUST be called every cycle (after init)
- ONE `TON` timer on `_bBusy` for timeout recovery
- If timeout fires, force-reset both `_bBusy` and `_fbRequest.bBusy` via MEMSET

## Step 5: Send Methods

See [http-patterns.md](http-patterns.md) Section 4 for complete GET and POST templates.

Key rules:
- 2-state CASE machine: State 0 = Build & Send, State 1 = Evaluate
- Flat ELSIF chain in State 1 (NOT deep nesting)
- 3-level error evaluation (client error, request error, bad status code)
- `VAR_INST` for `_nState` (each method has independent state)

## Step 6: Error Mapping Function

See [http-patterns.md](http-patterns.md) Section 6 for the complete `ETcIotHttpRequestError` mapping.

## Advanced Patterns

See [http-patterns.md](http-patterns.md) for:
- Complete Execute method implementation
- HTTP GET and POST templates with 3-level error evaluation
- `F_[Lib]_HttpRequestErrorToString` complete mapping
- Authentication patterns (API Key, Bearer Token)
- JSON body build/allocate/send/free workflow
- JSON response parsing with DOM validation
- Client configuration (TLS, KeepAlive, timeout)
- HTTP methods reference (GET, POST, PUT, DELETE)
- Compression modes
- Checklist for new HTTP libraries
