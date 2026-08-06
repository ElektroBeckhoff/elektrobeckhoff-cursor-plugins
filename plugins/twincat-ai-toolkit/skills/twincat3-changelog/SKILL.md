---
name: twincat3-changelog
description: >-
  Create short user-facing TwinCAT3 library changelogs (slim-first). Covers
  Versions/ naming, Highlights with GitHub commit links, Added/Changed/Fixed,
  breaking changes, and Migration. Use for release notes, bug-fix notes, or
  updating changelog-*.md.
---

# Changelog Writing Guide

Audience: **library users** scanning “what changed for me?” in ~30 seconds.
Not for implementation internals (tickets, watchdogs, refactors, style noise).

**Default = slim.** Use the full template only for breaking / major API surface changes.

## File location

```
Versions/
  X.X.X.X/
    changelog-X.X.X.X.md
```

- One file per release; version folder name must match exactly
- Lowercase `changelog-` prefix

## Gather changes (git)

1. Version from `.plcproj` `<ProjectVersion>` or `Global_Version.TcGVL`
2. Previous baseline: last `Versions/<prev>/` folder and/or git tag
3. Collect commits + resolve **GitHub repo URL**:

```bash
git remote get-url origin
git log --oneline <prev>..HEAD
git log --format="%h %H %s" <prev>..HEAD
```

4. Normalize `origin` to an HTTPS GitHub base (no `.git` suffix):

| `origin` | Base URL |
|----------|----------|
| `https://github.com/Org/Repo.git` | `https://github.com/Org/Repo` |
| `git@github.com:Org/Repo.git` | `https://github.com/Org/Repo` |
| `https://github.com/Org/Repo` | unchanged |

5. Commit link for a SHA (prefer short 7+ hex in link text, full or short SHA in URL):

```
https://github.com/<Org>/<Repo>/commit/<sha>
```

Example: [`8084d4a`](https://github.com/ElektroBeckhoff/Tc3_EB_BA/commit/8084d4a)

Optional range for the whole release:

```
https://github.com/<Org>/<Repo>/compare/<prev-tag-or-sha>...<head-sha>
```

6. Rewrite commit subjects into **user-facing** Highlights (impact). Drop pure `style:` / formatting / ProductVersion noise.
7. Do **not** commit/push from this skill (use `/twincat3-cmd-commit` only if asked).

If `origin` is not GitHub (or missing), omit commit links and note that in the reply to the user — do not invent URLs.

---

## Default template (slim-first)

Use for almost every release (patches, fixes, small features):

```markdown
# Changelog — <LibraryName> X.X.X.X

## Highlights

- **Short impact title** — one sentence for the app developer. ([`abc1234`](https://github.com/<Org>/<Repo>/commit/abc1234))
- **Second impact** — … ([`def5678`](https://github.com/<Org>/<Repo>/commit/def5678))

## Fixed

**`FB_Example`**
- Before → after (user-visible). ([`abc1234`](https://github.com/<Org>/<Repo>/commit/abc1234))

## Added

**`FB_Example`**
- New `bEnable : BOOL` – … ([`def5678`](https://github.com/<Org>/<Repo>/commit/def5678))
```

### Slim rules

- **Highlights:** max **3–5** bullets; each 1–2 sentences; **end with a commit link** to the main commit for that change
- One highlight → one primary commit link (if many commits, link the most important or use compare URL once in Highlights intro)
- Sections: only `Added` / `Changed` / `Fixed` / `Deprecated` / `Migration` as needed — **omit empty**
- No `### Style` in user changelogs
- No `---` required between sections (optional)
- English; present tense; WHAT/WHY only
- Code samples only when the user must wire a new API

### Multiple commits → one theme

```markdown
- **Token refresh reliability** — expired tokens trigger a full login; client no longer hangs. ([compare](https://github.com/<Org>/<Repo>/compare/abc1234...def5678))
```

Or list 2–3 short SHAs after the sentence: ([`abc1234`](…/commit/abc1234), [`def5678`](…/commit/def5678))

---

## Full template (breaking / major only)

When public API breaks, renames span many types, or Migration is non-trivial:

```markdown
# Changelog — <LibraryName> X.X.X.X

## Highlights

- **Impact 1** — … ([`abc1234`](https://github.com/<Org>/<Repo>/commit/abc1234))
- **Impact 2** — … ([`def5678`](https://github.com/<Org>/<Repo>/commit/def5678))

## Changed

**`FB_Example` inputs**

> [!CAUTION]
> **BREAKING CHANGE:** What broke and what the user must update.

- `nOld` → `nNew` ([`abc1234`](https://github.com/<Org>/<Repo>/commit/abc1234))

## Fixed

**`FB_Example`**
- Before → after ([`def5678`](https://github.com/<Org>/<Repo>/commit/def5678))

## Migration

1. Concrete upgrade step
2. …
```

Keep full changelogs as short as possible: Highlights still scannable; detail only for API/Migration.

---

## Entry patterns

### Fix

```markdown
**`FB_Example`**
- Wrong color recall in RGB scenes → recalls the saved color mode. ([`abc1234`](https://github.com/<Org>/<Repo>/commit/abc1234))
```

### New API

```markdown
**`FB_Example`**
- New inputs: `bSmartOpt : BOOL`, `fOffset : REAL` [°C]. ([`abc1234`](https://github.com/<Org>/<Repo>/commit/abc1234))
```

### Breaking

```markdown
> [!CAUTION]
> **BREAKING CHANGE:** Description and required action.
```

Always add **Migration** when the user must rewire / rename / add a dependency.

---

## Do / don't

| Do | Don't |
|----|--------|
| User-visible behavior and public I/O | Internal helpers, tickets, watchdogs, step machines |
| Link commits in Highlights (and detail bullets) | Paste full `git log` |
| Max 3–5 Highlights | Essay-length Highlights |
| Migration only if action needed | Empty Migration / Style sections |
| Real `origin`-based GitHub URLs | Guessed org/repo names |

## Checklist

- [ ] `Versions/X.X.X.X/changelog-X.X.X.X.md`
- [ ] Slim by default; full only if breaking/major
- [ ] Highlights ≤ 5, each with GitHub commit (or compare) link when `origin` is GitHub
- [ ] Links use `https://github.com/<Org>/<Repo>/commit/<sha>` from this repo’s `origin`
- [ ] Breaking → `> [!CAUTION]` + Migration
- [ ] English; no implementation noise
- [ ] No push; commit only via `/twincat3-cmd-commit` if requested

## Reference

Examples: [examples.md](examples.md)
