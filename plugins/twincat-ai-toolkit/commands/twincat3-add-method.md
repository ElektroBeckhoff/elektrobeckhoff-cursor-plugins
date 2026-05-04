---
name: twincat3-add-method
description: Add a method to an existing function block as valid TcPOU method XML with its own GUID.
---

# Add Method to FB

Add method [METHOD_NAME] to FB_[NAME].

Purpose: [DESCRIPTION]
Parameters: [LIST]
Return type: [TYPE]

## Required Context

**Rules:** `twincat3-naming`, `twincat3-xml-tcpou`, `twincat3-comments`

## Instructions

Generate method XML with its own GUID (`[guid]::NewGuid()`). Method is placed inside the POU element, after `</Implementation>`.
