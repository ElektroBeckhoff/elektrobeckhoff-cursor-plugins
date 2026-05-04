---
name: twincat3-http-rest-client
description: Create an HTTP REST client FB with execute and send methods, error mapping, param struct, GVL, properties, and data structs.
---

# New HTTP REST Client

Create an HTTP REST client for: [NAME / API]

Host: [HOSTNAME:PORT]
Endpoints:
  [GET/POST] [/api/endpoint] = [DESCRIPTION]
  [GET/POST] [/api/endpoint] = [DESCRIPTION]
Auth: [API-Key / Bearer Token / None]

## Required Context

**Rules:** `twincat3-http`, `twincat3-naming`, `twincat3-xml-tcpou`, `twincat3-xml-tcdut`, `twincat3-comments`, `twincat3-formatting`
**Skills:** `twincat3-http` (SKILL.md + http-patterns.md), `twincat3-json-strings` (for JSON parsing/writing)

## Deliverables

1. `FB_[Lib]_Client.TcPOU` -- client FB with Execute + Send methods
2. `F_[Lib]_HttpRequestErrorToString.TcPOU` -- error mapping function
3. `ST_[Lib]_HttpParam.TcDUT` -- param struct
4. Data structs for response parsing
5. Properties: IsConnected, IsBusy, IsError, ErrorText
6. Register all files in `.plcproj`, generate GUIDs with `[guid]::NewGuid()`
