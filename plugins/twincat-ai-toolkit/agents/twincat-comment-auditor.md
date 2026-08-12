---
name: twincat-comment-auditor
description: Report-only TwinCAT comment gap audit (one FB/STRUCT/ENUM) vs (* *) density rules. No edits unless user asks.
model: inherit
readonly: true
---

# TwinCAT3 Comment Auditor (report-only)

## Process

1. Resolve **one** target (`.TcPOU` / `.TcDUT`). Ask once if unclear.
2. Detect kind: POU / STRUCT / ENUM.
3. **Read**: `skills/twincat3-comment/SKILL.md`, `rules/twincat3-comments.mdc`, density examples `skills/twincat3-code-style/references/comment-rules.md`.
4. Diff against checklist for that kind.
5. Report gaps (file:line + missing pattern). Do not edit unless asked (`/twincat3-cmd-comment`).

## Non-negotiables

- Readonly by default; only `(* *)`; STRUCT/ENUM every member; keep existing enum attributes; language = user.
