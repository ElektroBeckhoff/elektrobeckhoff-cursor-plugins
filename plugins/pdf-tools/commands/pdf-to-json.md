---
name: pdf-to-json
description: Convert PDF files to structured JSON with bounding boxes using opendataloader-pdf.
---

# Convert PDF to JSON

Convert one or more PDF files to structured JSON with element types, bounding boxes, and semantic metadata.

## Required Context

**Skills:** `pdf-convert` (follow completely)

## Instructions

1. Search the workspace for `.pdf` files using Glob: `**/*.pdf`
2. If multiple PDFs found, ask which to convert
3. Run `pdf_status()` to verify prerequisites
4. Run `pdf_convert(input_path="<path>", format="json")`
5. Read the generated `.json` file(s) and summarize the extracted structure
