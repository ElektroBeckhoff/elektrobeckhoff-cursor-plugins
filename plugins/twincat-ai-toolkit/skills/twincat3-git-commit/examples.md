# Thematic Commit Examples

Patterns from TwinCAT3 library history (e.g. Tc3_EB_BA). **Never push** after these commits.

---

## Example 1: Subsystem series (DALI alignment)

Working tree has EvgControl input renames plus five device families updated.

**Wrong — one mega-commit:**

```
refactor: rename EvgControl inputs and update all DALI devices
```

**Correct — thematic groups:**

1. `refactor: clarify EvgControl DALI inputs and gate queries by short addr`  
   → `_internal/dali/control/*` only

2. `refactor: align DALI on/off device FBs with renamed EvgControl inputs`  
   → on/off device POUs only

3. `refactor: align DALI dimmer device FBs with renamed EvgControl inputs`  
   → dimmer POUs only

4. Same pattern for color-temp, RGB/RGBW, plug — one commit each

---

## Example 2: Fix vs style noise

After a real fix, TwinCAT re-saved XML formatting on the same POU.

**Split:**

1. `fix: harden EvgControl offline gating and group-assign retry`  
   → behavior/logic hunks (or the POU if inseparable)

2. `style: normalize DALI EvgControl formatting after TwinCAT save`  
   → whitespace / attribute order only commits when clearly separable

If the IDE mixed both in one file and they cannot be split cleanly, prefer a single `fix:` commit and mention formatting in the body.

---

## Example 3: Release vs changelog

After a release workflow:

| Group | Files | Message |
|-------|-------|---------|
| release | `Global_Version.TcGVL`, `*.plcproj` ProjectVersion, `Versions/1.4.3.0/*.library` (+ compiled) | `release: bump Tc3_EB_BA to 1.4.3.0 and add library export` |
| docs | `Versions/1.4.3.0/changelog-1.4.3.0.md` | `docs: add changelog for version 1.4.3.0` |

Do **not** combine library binaries with the changelog markdown in one commit.
