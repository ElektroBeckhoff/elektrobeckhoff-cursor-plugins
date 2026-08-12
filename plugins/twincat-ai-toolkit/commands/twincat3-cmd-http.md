---
name: twincat3-cmd-http
description: Create or extend an HTTP(S) REST client FB (Execute, state machine, 3-level errors, optional JSON).
---

# HTTP REST Client

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `rules/twincat3-http.mdc`
2. `skills/twincat3-http/SKILL.md`
3. `skills/twincat3-http/http-patterns.md`
4. `rules/twincat3-naming.mdc`
5. `rules/twincat3-xml.mdc` (+ `rules/examples/twincat3-xml.md` if scaffolding)
6. `rules/twincat3-core.mdc`

If JSON body/response parsing is needed, also Read:

7. `skills/twincat3-json-strings/SKILL.md`
8. `skills/twincat3-json-strings/dynamic-strings.md`
9. relevant of `json-parse-patterns.md` / `json-write-patterns.md`

## Do

1. Follow http skill + patterns (Execute method, Send state machine, 3-level error evaluation).
2. Fresh GUIDs; memory-safe JSON allocation on all paths.
