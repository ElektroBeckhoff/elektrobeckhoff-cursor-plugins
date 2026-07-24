---
name: twincat3-git-commit
description: >-
  Create thematic Conventional Commit groups for TwinCAT3 PLC library repos.
  Analyzes git status/diff, splits changes by theme or file family, and commits
  locally. Never pushes. Use when the user asks to commit, split commits, or
  run /twincat3-commit.
---

# TwinCAT3 Thematic Git Commits

Create **local** Conventional Commits grouped by change theme / coherent file set.
Gold-standard style: Tc3_EB_BA history (`feat:`, `fix:`, `refactor:`, …).

## Hard Rules

- **NEVER** run `git push`, `git push -u`, force-push, or any remote update
- **NEVER** create GitHub releases or use `gh` from this skill
- Push is **always** the user's responsibility
- Do **not** commit secrets (`.env`, credentials, private keys)
- English commit messages only
- One theme / one coherent file group per commit — never mix unrelated subsystems

## Prerequisites

1. Run `git --version`. If git is missing, stop and tell the user to install Git for Windows.
2. Confirm the working directory is a git repo (`git rev-parse --is-inside-work-tree`).

## Workflow

### 1. Gather state (parallel)

```
git status
git diff
git diff --cached
git log -15 --oneline
```

Match the repo's existing message style from `git log`.

### 2. Split into thematic groups

Group unstaged + untracked (+ already staged if mixed) by:

| Heuristic | Example |
|-----------|---------|
| Same folder / FB family | `POUs/.../dali/`, `devices/blind/` |
| Same change type | all `fix` vs all `refactor` vs all `feat` |
| Release artifacts alone | `Global_Version.TcGVL`, `.plcproj` `ProjectVersion`, `Versions/<ver>/*.(compiled-)library` |
| Changelog alone | `Versions/<ver>/changelog-<ver>.md` → `docs:` |
| TwinCAT noise alone | ProductVersion / property rename / pure formatting after XAE save → `style:` |

**Do not** put release binaries, changelog, and feature POU edits in one commit.

Preferred order when multiple groups exist:

1. Feature / fix / refactor source groups (logical dependency order)
2. `style:` formatting-only
3. `docs:` changelog
4. `release:` version bump + library export

### 3. Commit each group sequentially

For each group:

1. Stage only that group's files: `git add -- <paths>`
2. Commit with a Conventional Commit message
3. Proceed to the next group

#### Commit message format

```
type: short subject naming the FB or subsystem

Optional body: what changed and why (behavior/scope), not a file list.
```

**Types:** `feat`, `fix`, `refactor`, `style`, `docs`, `release`, `chore`

- Subject: imperative, concise; name the component (`EvgControl`, `FB_EB_BA_View`, library name for release)
- No `(scope)` parentheses required unless the repo already uses them
- Body: 1–3 sentences when the subject alone is unclear

#### PowerShell commit (Windows)

```powershell
git commit -m @"
fix: harden EvgControl offline gating and group-assign retry

Skip DALI traffic for empty/invalid addresses and invalidate PhysicalMinimum on failed re-query.
"@
```

#### Bash / Git Bash

```bash
git commit -m "$(cat <<'EOF'
fix: harden EvgControl offline gating and group-assign retry

Skip DALI traffic for empty/invalid addresses and invalidate PhysicalMinimum on failed re-query.
EOF
)"
```

### 4. Verify

```
git status
git log -N --oneline   # N = number of commits just created
```

Summarize for the user: commit hashes, subjects, and that **nothing was pushed**.

## Empty / blocked cases

- No changes → do not create an empty commit; tell the user
- Only secrets / junk → warn and skip
- Pre-commit hook failure → fix the issue and create a **new** commit (do not `--amend` unless the user's commit rules allow it)

## Out of scope

- Pushing, tagging, GitHub Releases
- Rewriting published history
- Changelog authoring (use `twincat3-changelog` / `/twincat3-write-changelog`)

## Reference

Grouping examples: [examples.md](examples.md)
