---
name: pdf-to-markdown
description: Convert PDF files to Markdown using opendataloader-pdf.
---

# Convert PDF to Markdown

Convert one or more PDF files to clean, structured Markdown.

## Required Context

**Skills:** `pdf-convert` (follow completely)

## Instructions

1. Search the workspace for `.pdf` files using Glob: `**/*.pdf`
2. If multiple PDFs found, ask which to convert
3. Run `pdf_status()` to verify prerequisites
4. Run `pdf_convert(input_path="<path>", format="markdown")`
5. Read the generated `.md` file(s) and present the content
