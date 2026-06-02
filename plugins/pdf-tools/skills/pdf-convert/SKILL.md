---
name: pdf-convert
description: >-
  Convert PDF files to Markdown, JSON, HTML, or text using opendataloader-pdf
  via MCP. Covers prerequisite checks, pdf_convert tool usage, parameter
  reference, output handling, and error troubleshooting. Use when converting
  PDFs, extracting text from PDFs, or preparing PDF content for RAG pipelines.
---

# PDF Conversion

## Quick Start

```
Task Progress:
- [ ] Step 1: Check prerequisites with pdf_status
- [ ] Step 2: Convert PDF with pdf_convert
- [ ] Step 3: Read output files
```

## Step 1: Check Prerequisites

```
pdf_status()
```

Verify `ready: true`. If not:
- **Java missing** -- Install JDK 11+ from https://adoptium.net
- **opendataloader-pdf missing** -- `pip install opendataloader-pdf`

## Step 2: Convert PDF

### Single file to Markdown

```
pdf_convert(input_path="C:/path/to/document.pdf")
```

### Multiple files

```
pdf_convert(input_path="file1.pdf, file2.pdf, folder/")
```

### Custom output directory and format

```
pdf_convert(
    input_path="document.pdf",
    output_dir="C:/output/",
    format="markdown,json"
)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_path` | string | (required) | PDF file or folder path. Comma-separated for multiple |
| `output_dir` | string | `<input>/output/` | Output directory |
| `format` | string | `"markdown"` | Output format(s): `markdown`, `json`, `html`, `text`, `tagged-pdf`. Comma-separated |
| `image_output` | string | `"off"` | `"off"`, `"embedded"` (Base64), `"external"` (files) |
| `use_struct_tree` | bool | `false` | Use native PDF structure tags when available |

## Step 3: Read Output

The response contains `output_dir` and `files[]`. Read the generated files:

```
Read: <output_dir>/<filename>.md
```

## Format Selection Guide

| Your Goal | Format | Why |
|-----------|--------|-----|
| LLM context / RAG chunks | `markdown` | Clean text with preserved headings, tables, lists |
| Element coordinates / citations | `json` | Bounding boxes for every element |
| Web display | `html` | Styled output |
| Plain text only | `text` | No formatting |
| Accessibility remediation | `tagged-pdf` | Screen-reader-ready output |

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Java not found` | JDK not installed or not in PATH | Install JDK 11+ from Adoptium |
| `opendataloader-pdf not installed` | Python package missing | `pip install opendataloader-pdf` |
| `Path not found` | Invalid input path | Check file path exists |
| `JVM process failed` | Corrupted PDF or insufficient memory | Try a different PDF, increase JVM heap |

## Performance Notes

- Each `convert()` call spawns a JVM process -- batch multiple files in one call
- Local mode: ~60 pages/sec on CPU (0.02s/page)
- No GPU required
- For scanned/complex PDFs, use the `pdf-hybrid` skill instead
