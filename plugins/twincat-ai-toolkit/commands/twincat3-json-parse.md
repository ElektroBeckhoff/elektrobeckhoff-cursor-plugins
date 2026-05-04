---
name: twincat3-json-parse
description: Add JSON parsing logic to an existing FB for MQTT payloads or HTTP responses with data struct and dynamic memory allocation.
---

# Parse JSON (MQTT Payload / HTTP Response)

Add JSON parsing to FB_[NAME] for [MQTT Payload / HTTP Response].

Fields:
  [fieldname] : [TYPE] = [DESCRIPTION]
  [fieldname] : [TYPE] = [DESCRIPTION]

## Required Context

**Rules:** `twincat3-naming`
**Skills:** `twincat3-json-strings` (SKILL.md + json-parse-patterns.md)

## Instructions

Create data struct and parse logic with dynamic memory allocation. Always check `_jsonDoc <> 0` after `ParseDocument`/`GetJsonDomContent`. Always `__DELETE` in the same scope as `__NEW`.
