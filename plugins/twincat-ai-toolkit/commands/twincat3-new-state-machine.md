---
name: twincat3-new-state-machine
description: Add a step-based state machine to an existing FB using CASE _nStep OF with standard steps (idle, operations, success, error, delay).
---

# New Step-Based State Machine

Add a step-based state machine to FB_[NAME].

Purpose: [DESCRIPTION]
Steps: [LIST OF OPERATIONS]

## Required Context

**Rules:** `twincat3-core`, `twincat3-naming`, `twincat3-formatting`

## Instructions

Use `CASE _nStep OF` with standard steps (idle=0, operations=1+, success=90, error=100, delay=200).
