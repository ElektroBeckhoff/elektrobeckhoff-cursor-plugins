# Zero-change behavior (local verification)

## Format (`python -m formatter`)

| Scenario | Tool behavior | Git / workflow |
|----------|---------------|----------------|
| All files already formatted | Hash compare → **no disk write**; `N unchanged` in summary; exit **0** | `git diff --cached --quiet` → **no commit** |
| No formattable files in tree | Message `no formattable files found`; exit **0** | **no commit** |
| Some files need formatting | Only changed files written; exit **0** | Commit only `${LIB_INPUT}/` |

Implementation: `formatter/file_processor.py` — write only when `original_hash != new_hash`.

---

## AutoDocs (`python -m autodocs`)

| Scenario | Tool behavior | Git / workflow |
|----------|---------------|----------------|
| Steady state (docs exist, sources unchanged) | Re-processes all files; `.md` output byte-identical. Default: `docs/autodocs.log` is NOT written; TOC has no changing timestamp. | **No diff** on `docs/toc.md` + `README.md` |
| Every successful run (optional enabled) | If `--write-log` (or MCP `write_log=true`) is set, `docs/autodocs.log` is rewritten. If `--toc-timestamp` (or MCP `toc_timestamp=true`) is set, TOC timestamp changes. | Commit happens only for the enabled files |
| First run (no docs yet) | Creates all `.md` + toc + log | Large commit |

Test command (Tc3_EB_BA, second run after docs committed):

```text
git diff --name-only docs README.md
→ (expected: empty, no commit)
```

---

## Implications for CI

- **Format workflow**: safe to run on every push — idempotent, silent when nothing to fix.
- **Autodocs workflow**: with defaults (`write_log=false`, `toc_timestamp=false`) it is idempotent: no commit if docs content doesn't change.
