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

**Templates + filled examples:** [examples.md](examples.md) — **Read** before writing.

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

5. Commit link: `https://github.com/<Org>/<Repo>/commit/<sha>`  
   Example shape: `[`8084d4a`](https://github.com/<Org>/<Repo>/commit/8084d4a)` — use the repo’s real `origin` URL.  
   Optional release range: `…/compare/<prev>...<head>`.
6. Rewrite commit subjects into **user-facing** Highlights (impact). Drop pure `style:` / formatting / ProductVersion noise.
7. Do **not** commit/push from this skill (use `/twincat3-cmd-commit` only if asked).

If `origin` is not GitHub (or missing), omit commit links and note that in the reply — do not invent URLs.

## Slim rules

- **Highlights:** max **3–5** bullets; each 1–2 sentences; **end with a commit link** to the main commit for that change
- One highlight → one primary commit link (if many commits, link the most important or use compare URL once in Highlights intro)
- Sections: only `Added` / `Changed` / `Fixed` / `Deprecated` / `Migration` as needed — **omit empty**
- No `### Style` in user changelogs
- English; present tense; WHAT/WHY only
- Code samples only when the user must wire a new API
- Breaking → `> [!CAUTION]` with **BREAKING CHANGE:** + **Migration** steps

Blank templates and filled samples → [examples.md](examples.md).

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
