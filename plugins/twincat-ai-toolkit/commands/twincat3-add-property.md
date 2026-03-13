---
name: twincat3-add-property
description: Add a property to an existing function block as valid TcPOU property XML with 3 GUIDs (property, getter, setter).
---

# Add Property to FB

Add property [PROPERTY_NAME] to FB_[NAME].

Type: [TYPE]
Access: [GET / SET / both]
Purpose: [DESCRIPTION]

## Instructions

Look up the rules for naming, OOP, and XML formats. Read and follow them before generating code.

Generate property XML with 3 GUIDs (`[guid]::NewGuid()`).
