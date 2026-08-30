---
name: twincat3-cmd-autodocs
description: >-
  Autodocs only: twincat_autodocs(input=solution folder). Output optional —
  auto repo root → docs/. No XAE, no format/validate.
---

# Autodocs

## Read first (in order)

1. `rules/twincat3-mcp-autodocs.mdc`
2. `skills/twincat3-autodocs/SKILL.md`

## Do (exactly this)

1. **`input`** = solution folder `<repo-root>/<LibName>/` (contains `<LibName>.sln`).
2. **`output`** — **omit by default** (auto-detects `<repo-root>` → writes `<repo-root>/docs/`).
   Pass `output` only when the user explicitly requests a different project root.
3. **One call:**

   ```
   twincat_autodocs(input="<repo-root>/<LibName>")
   ```

4. **Verify:** `success`, `errors == 0`, `repo_root`, `output` ends with `/docs`.
5. **Report:** `files_created` count, `skipped_hidden`, `docs/toc.md`, `docs/autodocs.log`.

## Do not (separate steps only)

- XAE / format / validate / comment / migrate / source edits
- `output=<repo-root>/docs`
- `input=<repo-root>` or `input=samples`

## Example (placeholder paths)

```
twincat_autodocs(
  input="C:/path/to/<repo-root>/<LibName>"
)
```

CLI:

```bash
python -m autodocs --input "C:/path/to/<repo-root>/<LibName>"
```
