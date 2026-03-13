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

## Instructions

Look up all relevant rules and skills for MQTT, naming, formatting, comments, JSON, and XML formats. Read and follow them completely before generating code.

Generate all required files: device FB with MQTT client + message queue, subscribe-on-connect, reconnection, receive with dynamic payload allocation, publish, topic routing, data struct, .plcproj registration. Generate GUIDs with `[guid]::NewGuid()`.
