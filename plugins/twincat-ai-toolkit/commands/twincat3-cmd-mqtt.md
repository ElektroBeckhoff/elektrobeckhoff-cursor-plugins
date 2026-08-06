---
name: twincat3-cmd-mqtt
description: Create or extend an MQTT function block (client, queue, reconnect, topic routing, optional JSON).
---

# MQTT Function Block

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-mqtt/SKILL.md`
2. `skills/twincat3-mqtt/mqtt-patterns.md`
3. `rules/twincat3-mqtt.mdc`
4. `rules/twincat3-naming.mdc`
5. `rules/twincat3-xml.mdc`
6. `rules/twincat3-core.mdc`

If JSON payloads are involved, also Read:

7. `skills/twincat3-json-strings/SKILL.md`
8. `skills/twincat3-json-strings/dynamic-strings.md`
9. relevant of `json-parse-patterns.md` / `json-write-patterns.md`

## Do

1. Follow mqtt skill + patterns; enforce subscribe-on-connect and `__NEW`/`__DELETE` pairing.
2. Fresh GUIDs for new objects; preserve XML safety rules.
