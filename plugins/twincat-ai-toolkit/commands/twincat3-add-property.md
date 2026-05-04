---
name: twincat3-add-property
description: Add a property to an existing function block as valid TcPOU property XML with 3 GUIDs (property, getter, setter).
---

# Add Property to FB

Add property [PROPERTY_NAME] to FB_[NAME].

Type: [TYPE]
Access: [GET / SET / both]
Purpose: [DESCRIPTION]

## Required Context

**Rules:** `twincat3-naming`, `twincat3-oop`, `twincat3-xml-tcpou`

## Instructions

Generate property XML with 3 GUIDs (`[guid]::NewGuid()`) -- one for property, one for Get, one for Set. Property names use PascalCase without prefix.
