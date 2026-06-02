---
name: pdf-hybrid
description: >-
  Convert complex PDFs (scanned, borderless tables, formulas, charts) using
  opendataloader-pdf hybrid mode via MCP. Covers hybrid server startup,
  OCR configuration, formula/picture enrichment, and when to use hybrid
  vs local mode. Use for scanned PDFs, complex tables, OCR, or when
  local mode accuracy is insufficient.
---

# PDF Hybrid Mode Conversion

## When to Use Hybrid Mode

| Document Type | Use Hybrid? |
|---------------|-------------|
| Standard digital PDF | No -- use `pdf_convert` (local mode) |
| Complex or borderless tables | **Yes** |
| Scanned / image-based PDF | **Yes** (with `force_ocr`) |
| Mathematical formulas | **Yes** (with `hybrid_mode="full"`) |
| Charts needing description | **Yes** (with `hybrid_mode="full"`) |
| Non-English scanned PDF | **Yes** (with `force_ocr` + `ocr_lang`) |

## Quick Start

```
Task Progress:
- [ ] Step 1: Check prerequisites with pdf_status
- [ ] Step 2: Ensure hybrid backend is running
- [ ] Step 3: Convert with pdf_convert_hybrid
- [ ] Step 4: Read output files
```

## Step 1: Check Prerequisites

```
pdf_status()
```

Additional requirement for hybrid: `pip install "opendataloader-pdf[hybrid]"`

## Step 2: Start Hybrid Backend

The user must start the backend server in a separate terminal **before** calling `pdf_convert_hybrid`:

```bash
opendataloader-pdf-hybrid --port 5002
```

### Backend with OCR (scanned PDFs)

```bash
opendataloader-pdf-hybrid --port 5002 --force-ocr
```

### Backend with formula enrichment

```bash
opendataloader-pdf-hybrid --enrich-formula
```

### Backend with picture/chart descriptions

```bash
opendataloader-pdf-hybrid --enrich-picture-description
```

## Step 3: Convert with Hybrid Mode

### Basic hybrid conversion

```
pdf_convert_hybrid(input_path="document.pdf")
```

### Scanned PDF with OCR

```
pdf_convert_hybrid(
    input_path="scanned.pdf",
    force_ocr=true,
    ocr_lang="en,de"
)
```

### Full enrichment (formulas + pictures)

```
pdf_convert_hybrid(
    input_path="scientific-paper.pdf",
    hybrid_mode="full",
    format="json"
)
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `input_path` | string | (required) | PDF file or folder. Comma-separated for multiple |
| `output_dir` | string | `<input>/output/` | Output directory |
| `format` | string | `"markdown"` | `markdown`, `json`, `html`, `text`. Comma-separated |
| `hybrid` | string | `"docling-fast"` | Hybrid backend name |
| `hybrid_mode` | string | `""` (auto) | `"full"` for formula/picture enrichment |
| `force_ocr` | bool | `false` | Force OCR for scanned PDFs |
| `ocr_lang` | string | `""` (auto) | OCR languages: `en`, `de`, `ko`, `ja`, `ch_sim`, `fr`, `ar` |
| `image_output` | string | `"off"` | `"off"`, `"embedded"`, `"external"` |
| `use_struct_tree` | bool | `false` | Use native PDF structure tags |

## OCR Language Codes

| Code | Language |
|------|----------|
| `en` | English |
| `de` | German |
| `ko` | Korean |
| `ja` | Japanese |
| `ch_sim` | Chinese (Simplified) |
| `ch_tra` | Chinese (Traditional) |
| `fr` | French |
| `ar` | Arabic |

## Accuracy Comparison

| Mode | Overall Score | Table Accuracy | Speed (s/page) |
|------|--------------|----------------|-----------------|
| Hybrid | **0.907** | **0.928** | 0.463 |
| Local (default) | 0.831 | 0.489 | 0.015 |

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `Connection refused` | Hybrid backend not running | Start with `opendataloader-pdf-hybrid --port 5002` |
| `hybrid extra not installed` | Missing hybrid dependencies | `pip install "opendataloader-pdf[hybrid]"` |
| `OCR language not available` | Unsupported language code | Check supported codes above |
