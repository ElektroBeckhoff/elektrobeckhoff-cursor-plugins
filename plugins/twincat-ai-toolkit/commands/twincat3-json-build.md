---
name: twincat3-json-build
description: Create JSON payload building logic in an existing FB for MQTT publish or HTTP POST body.
---

# Build JSON (Publish / HTTP Body)

Create JSON payload in FB_[NAME] for [MQTT Publish / HTTP POST].

Fields:
  [fieldname] : [TYPE] = [DESCRIPTION]
  [fieldname] : [TYPE] = [DESCRIPTION]

## Required Context

**Rules:** `twincat3-naming`
**Skills:** `twincat3-json-strings` (SKILL.md + json-write-patterns.md)

## Instructions

Use `FB_JsonSaxWriter` for building. Use `GetDocument()` for small payloads (<255 chars), `CopyDocument` with `__NEW`/`__DELETE` for larger payloads.
