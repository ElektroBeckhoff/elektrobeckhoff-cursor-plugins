---
name: twincat3-autodocs
description: >-
  Generate Markdown API docs via twincat_autodocs. Input = solution folder;
  output optional (auto repo root → docs/). No XAE. /twincat3-cmd-autodocs.
---

# Autodocs (Markdown API docs)

AutoDocs uses `twincat_core.xml` and `twincat_core.syntax` / AST semantic representations to parse POUs, DUTs, GVLs, and Interfaces without XML loss or parallel regex parsers.

## Scope (ONLY this)

1. Set `input` = solution folder (`<repo-root>/<LibName>/`) per rule `twincat3-mcp-autodocs`.
2. Omit `output` unless user needs a custom root — default auto-detects repo root.
3. Call **`twincat_autodocs(input=...)` once**.
4. Report `success`, `errors`, `repo_root`, `files_created`.

Do **not** in the same run: open XAE, format, validate, comment, migrate, edit source.

## Quick Start

```
Task Progress:
- [ ] Step 1: input = <repo-root>/<LibName>/ (solution folder)
- [ ] Step 2: twincat_autodocs(input=...) — output omitted unless override needed
- [ ] Step 3: Verify success, errors == 0, repo_root + output (/docs)
- [ ] Step 4: Report docs/toc.md, README TOC block, autodocs.log
```

## Step 1: Paths

Resolve from the user's workspace (rule `twincat3-mcp-autodocs` — AI path resolution):

- Repo root alone is **not** valid `input` — use `<repo-root>/<LibName>/` (`.sln` folder).
- Omit `output` — auto-detects repo root; docs → `<repo-root>/docs/`.

| Parameter | Required | Value |
|-----------|----------|-------|
| `input` | **Yes** | Solution folder: `<repo-root>/<LibName>/` (contains `.sln`) |
| `output` | No | Default: auto `<repo-root>/`. Override only when explicit. |

**Auto-detection** (when `output` omitted):

1. Walk up from `input` for `README.md` or `.git`.
2. Else use parent of `input` (standard solution-folder layout).

Docs always land in `<repo-root>/docs/` — never pass `docs/` as `output`.

**Folders only** — single files not supported.

## Step 2: Execute

**Default (preferred):**

```
twincat_autodocs(
  input="C:/path/to/<repo-root>/<LibName>"
)
```

**Explicit override:**

```
twincat_autodocs(
  input="C:/path/to/<repo-root>/<LibName>",
  output="C:/path/to/<repo-root>"
)
```

CLI:

```bash
python -m autodocs --input "C:/path/to/<repo-root>/<LibName>"
# optional: --output "C:/path/to/<repo-root>"
```

## Step 3: Result

```json
{
  "success": true,
  "repo_root": "C:/path/to/<repo-root>",
  "output": "C:/path/to/<repo-root>/docs",
  "files_created": ["<repo-root>/docs/<LibName>/POUs/FB_MyBlock.md"],
  "skipped_hidden": 0,
  "errors": 0
}
```

| Field | Meaning |
|-------|---------|
| `repo_root` | Resolved project/repo root |
| `output` | Docs directory (`<repo_root>/docs`) |
| `errors` | Must be `0` for success |

## Forbidden

| Do not | Why |
|--------|-----|
| `output=.../docs` | Double nesting |
| `input=<repo-root>` | Scans `samples/`; wrong scope |
| `input=<repo-root>/samples` | Never document samples |
| `input=.../POUs` only | Incomplete cross-refs |
| `input=single file` | Not supported |
| Format/validate in same step | Separate workflows |
| Guess paths on MCP failure | Read `log` instead |

## References

- Rule: `twincat3-mcp-autodocs`
- Command: `/twincat3-cmd-autodocs`
