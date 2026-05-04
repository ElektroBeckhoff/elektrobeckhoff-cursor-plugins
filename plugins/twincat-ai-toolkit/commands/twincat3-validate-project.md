---
name: twincat3-validate-project
description: Validate the TwinCAT3 PLC project by compiling all objects and reporting errors.
---

# Validate Project

Compile all objects in the TwinCAT PLC project and report any errors.

## Required Context

**Skills:** `twincat3-validate` (follow completely)

## Instructions

Find the `.plcproj` in the workspace, open the solution with `twincat_open` (explicit path), run `twincat_check_all_objects`, and report all errors with file paths and line numbers.

If errors are found, offer to fix them.
