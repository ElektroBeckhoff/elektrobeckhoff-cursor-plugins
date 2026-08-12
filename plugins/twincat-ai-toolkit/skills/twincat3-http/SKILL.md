---
name: twincat3-http
description: HTTP(S) REST in TwinCAT3 (FB_IotHttpClient/Request). Execute, 2-state Send, 3-level errors, auth, JSON body. Use for REST/cloud/webhooks.
---

# HTTP(S) REST Communication (Tc3_IotBase)

**Read first**

1. `rules/twincat3-http.mdc` — mandatory rules
2. [http-patterns.md](http-patterns.md) — complete ST (FB structure, Execute, GET/POST, auth, JSON, checklist)
3. If JSON parse/build: skill `twincat3-json-strings`

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

## Core FBs

| FB | Purpose |
|----|---------|
| `FB_IotHttpClient` | Connection (host, port, TLS) |
| `FB_IotHttpRequest` | Build/send request, read response |
| `FB_IotHttpHeaderFieldMap` | Custom headers |

## Workflow notes

- All ST templates live in [http-patterns.md](http-patterns.md) — **Read** that file; do not paste duplicates here.
- Enforce: `_fbClient.Execute()` every cycle; 3-level flat ELSIF; `_jsonDoc <> 0`; `__DELETE` payload in State 0.
