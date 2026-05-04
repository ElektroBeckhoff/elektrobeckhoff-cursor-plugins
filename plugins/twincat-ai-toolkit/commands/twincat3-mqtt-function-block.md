---
name: twincat3-mqtt-function-block
description: Create an MQTT function block with client, message queue, subscribe-on-connect, reconnection, receive with dynamic payload allocation, publish, and topic routing.
---

# New MQTT Function Block

Create an MQTT function block for: [NAME / DEVICE]

Broker: [IP:PORT]
Subscribe topics: [TOPIC1, TOPIC2, ...]
Publish topics: [TOPIC1, TOPIC2, ...]
Payload format: [JSON / Plain String]

## Required Context

**Rules:** `twincat3-mqtt`, `twincat3-naming`, `twincat3-xml-tcpou`, `twincat3-comments`, `twincat3-formatting`
**Skills:** `twincat3-mqtt` (SKILL.md + mqtt-patterns.md), `twincat3-json-strings` (if JSON payload)

## Deliverables

1. Device FB with MQTT client + message queue
2. Subscribe-on-connect with reconnection handling
3. Receive with dynamic payload allocation (`__NEW`/`__DELETE`)
4. Publish method(s)
5. Topic routing
6. Data struct for parsed payloads
7. Register all files in `.plcproj`, generate GUIDs with `[guid]::NewGuid()`
