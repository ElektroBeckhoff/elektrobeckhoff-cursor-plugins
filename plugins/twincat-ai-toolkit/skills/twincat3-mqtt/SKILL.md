---
name: twincat3-mqtt
description: MQTT in TwinCAT3 (FB_IotMqttClient). Publish/subscribe, queues, topic routing, reconnect, QoS, TLS, LWT. Use for broker messaging or IoT MQTT FBs.
---

# MQTT Communication (Tc3_IotBase)

**Read first**

1. `rules/twincat3-mqtt.mdc` — mandatory rules
2. [mqtt-patterns.md](mqtt-patterns.md) — all ST samples (template, subscribe/receive/publish, TLS, LWT, wildcards)
3. If JSON payloads: skill `twincat3-json-strings`

## Quick Start

```
Task Progress:
- [ ] Step 1: Add Tc3_IotBase library reference
- [ ] Step 2: Declare MQTT client, message queue, and message FBs
- [ ] Step 3: Configure connection (host, port, client ID, credentials)
- [ ] Step 4: Implement subscribe-on-connect with reconnection handling
- [ ] Step 5: Implement message receive with dynamic payload allocation
- [ ] Step 6: Implement publish (string or dynamic JSON)
- [ ] Step 7: Add topic routing for incoming messages
```

## Core FBs

| FB | Purpose |
|----|---------|
| `FB_IotMqttClient` | Connect, publish, subscribe |
| `FB_IotMqttMessageQueue` | Incoming message queue |
| `FB_IotMqttMessage` | Single message (topic + payload) |

## Workflow notes

- Steps 2–7 ST: **Read** [mqtt-patterns.md](mqtt-patterns.md) (do not duplicate here).
- Enforce: Execute every cycle; subscribe only when Connected; reset `_bSubscribed` on disconnect; pair `__NEW`/`__DELETE`.
