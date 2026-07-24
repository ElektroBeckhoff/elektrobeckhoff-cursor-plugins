---
name: twincat3-changelog
description: >-
  Create and update changelogs for TwinCAT3 PLC library releases. Covers file
  naming, folder structure, header format, Highlights/All Changes/Migration
  sections, breaking change warnings, and git-log sourcing. Use when creating
  a new version changelog, documenting bug fixes, new features, breaking
  changes, or any release notes for a TwinCAT3 library project.
---

# Changelog Writing Guide

Universal guide for TwinCAT3 PLC library projects. Audience: **library users**
(what is new, changed, fixed — not implementation internals).

Gold-standard layout: Tc3_EB_BA `Versions/*/changelog-*.md`.

## File Location and Naming

```
Versions/
  X.X.X.X/
    changelog-X.X.X.X.md
```

- One file per release version
- Lowercase `changelog-` prefix
- Version directory must match the version number exactly

## Gather Changes (from git)

Before writing, collect user-facing changes since the previous release:

1. Read current version from `.plcproj` `<ProjectVersion>` or `Global_Version.TcGVL`
2. Find previous version folder under `Versions/` (or previous tag if present)
3. Run (adjust range as needed):

```
git log --oneline <prev-version-commit-or-tag>..HEAD
git log --stat <prev-version-commit-or-tag>..HEAD
```

If no clear baseline, diff PLC sources against the previous `Versions/<prev>/` release commit or ask the user for the range.

4. Rewrite commit subjects into **user-facing** entries (WHAT/WHY). Drop pure `style:` / formatting noise unless it affects the public API surface.
5. Do **not** auto-commit or push the changelog from this skill (use `/twincat3-commit` only if the user asks).

## Header Format

### Primary template (feature / major / user-relevant patch)

Prefer this for any release that library consumers should read:

```markdown
# Changelog — <LibraryName> X.X.X.X

---

## Highlights

**1. Feature Title**
Brief description of the feature and its impact for the application developer.

**2. Second Feature**
Brief description.

---

## All Changes

### Added

**Theme or type name**
- User-facing description

### Changed

**Theme or rename**

> [!CAUTION]
> **BREAKING CHANGE:** What changed and what the user must update.

- Details

### Fixed

**`FB_Example` or theme**
- Problem → corrected behavior

### Style

- Formatting / naming cleanup that is worth noting (optional; omit if empty)

---

## Migration

1. Concrete step for upgrading projects
2. Further steps as needed
```

Replace `<LibraryName>` with the actual library name (e.g. `Tc3_EB_BA`, `Tc3_IoT_Utilities`).

Use `---` between major sections. Em dash `—` in the H1 title.

### Slim bug-fix template (tiny internal patches only)

When the release is a single small fix and Highlights would be empty noise:

```markdown
## Version X.X.X.X – Short Title

- One-sentence summary of the release scope.

---

### Fixed

**`FB_Name`**
- Description of the change.
```

If the patch is still **user-relevant**, prefer the primary template (same sections as feature releases).

**Rules:**
- Primary releases use `#` with `Changelog — <LibraryName>`
- Slim bug-fix releases use `##` with `Version X.X.X.X – Title`
- Use `–` (en dash) between version and title in slim headers, not `-` (hyphen)

## Language and Style

- **English only**
- Professional, concise, technical tone
- Focus on WHAT changed and WHY — no implementation details
- Present tense for descriptions ("Adds", "Fixes", "Removes")

## Section Templates

### Bug Fix Entry

```markdown
**`FB_Example`**
- Fixed description of the problem. Previous behavior → corrected behavior.
```

### New Feature Entry

```markdown
**`FB_Example`**
- New inputs added:
  - `bNewInput : BOOL` – Description
  - `fNewValue : REAL` – Description [unit]
```

### Feature with Code Example

Only include code examples when they help understanding (new API, migration):

````markdown
**`FB_Example`**
- New method `DoSomething` for specific purpose.

```iecst
// example
fbExample.DoSomething(
    bEnable := TRUE,
    fValue  := 42.0);
```
````

Use `iecst` syntax highlighting for all code blocks.

### Breaking Change

```markdown
> [!CAUTION]
> **BREAKING CHANGE:** Description of what changed and what action is required.
```

Place under the relevant `### Changed` theme (or at the top of All Changes if it spans the release). Always pair with **Migration** steps when user action is required.

### Systematic Fix (pattern applied across multiple POUs)

```markdown
### Fixed

**Section Title – Systematic Correction**

Brief explanation of the root cause and scope of the fix.

**`FB_Name_1`**
- Specific change in this FB.

**`FB_Name_2` / `FB_Name_3`**
- Shared change description when identical.

**Group Name** (`FB_A`, `FB_B`, `FB_C`)
- Shared change description for a family of FBs.
```

## Formatting Rules

### Bullet Points
- `-` for main points
- `  -` (2 spaces) for sub-points
- `    -` (4 spaces) for sub-sub-points

### Emphasis
- **Bold** for important terms, parameter names, section labels
- `` `code` `` for FB names, variables, methods, types, file names
- *Italics* sparingly for emphasis

### POU Names
- Always in code format: `` `FB_Example` ``
- Bold + code for section headers: `**`FB_Example`**`
- Group related POUs: `**`FB_A` / `FB_B`**`

## Categorizing Changes

| Category | Use for |
|----------|---------|
| Added | New FBs, DUTs, GVLs, Functions, inputs, outputs, methods |
| Changed | Modified behavior, renamed items, refactored public API |
| Fixed | Bug fixes affecting runtime behavior |
| Style | Naming/format cleanup worth noting for consumers (optional) |
| Deprecated | Features to be removed, with migration path |
| Migration | Step-by-step upgrade actions (own `## Migration` section) |

Omit empty sections.

## Completeness Checklist

Before finalizing a changelog:

- [ ] Every **user-facing** code change has a corresponding entry
- [ ] File is in `Versions/X.X.X.X/changelog-X.X.X.X.md`
- [ ] Header uses primary template (or slim bug-fix when appropriate)
- [ ] Breaking changes use `> [!CAUTION]` with **BREAKING CHANGE:**
- [ ] Migration steps present when breaking or rename-required
- [ ] All affected FBs/DUTs/Functions listed where relevant
- [ ] Code examples use `iecst` syntax highlighting
- [ ] Sections separated with `---`
- [ ] Written in English
- [ ] No implementation details — purpose and impact only
- [ ] Not pushed; commit only via `/twincat3-commit` if the user requests it

## Reference

For real changelog examples, see [examples.md](examples.md).
