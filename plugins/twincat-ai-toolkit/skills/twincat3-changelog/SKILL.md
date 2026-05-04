---
name: twincat3-changelog
description: >-
  Create and update changelogs for TwinCAT3 PLC library releases. Covers file
  naming, folder structure, header format, section templates, breaking change
  warnings, and code examples. Use when creating a new version changelog,
  documenting bug fixes, new features, breaking changes, or any release notes
  for a TwinCAT3 library project.
---

# Changelog Writing Guide

Universal guide for all TwinCAT3 PLC library projects.

## File Location and Naming

```
Versions/
  X.X.X.X/
    changelog-X.X.X.X.md
```

- One file per release version
- Lowercase `changelog-` prefix
- Version directory must match the version number exactly

## Header Format

Two header styles depending on release scope:

### Major / Feature Release

```markdown
# Changelog — <LibraryName> X.X.X.X

---

## Highlights

**1. Feature Title**
Brief description of the feature and its impact.

**2. Second Feature**
Brief description.

---

## All Changes

### Added
- Description of added functionality

### Changed
- Description of changed behavior

### Fixed
- Description of bug fix

### Deprecated
- Description of deprecated feature and migration path
```

Replace `<LibraryName>` with the actual library name (e.g. `Tc3_IoT_BA`, `Tc3_IoT_Utilities`, `Tc3_Modbus_RTU`).

### Bug Fix / Maintenance Release

```markdown
## Version X.X.X.X – Short Title

- One-sentence summary of the release scope.

---

### Section Title

**`FB_Name`**
- Description of the change.

---

### Another Section

- More changes.
```

**Rules:**
- Major releases use `#` (single hash) with `Changelog — <LibraryName>`
- Bug fix releases use `##` (double hash) with `Version X.X.X.X – Title`
- Use `–` (en dash) between version and title, not `-` (hyphen)
- Use `---` separators between major sections

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

Place breaking changes at the top of the changelog, before other sections.

### Systematic Fix (pattern applied across multiple POUs)

```markdown
### Section Title – Systematic Correction

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

### For Major Releases (Added/Changed/Fixed/Deprecated)

| Category | Use for |
|----------|---------|
| Added | New FBs, DUTs, GVLs, Functions, inputs, outputs, methods |
| Changed | Modified behavior, renamed items, refactored logic |
| Fixed | Bug fixes, typo corrections |
| Deprecated | Features to be removed, with migration path |

### For Bug Fix Releases (by severity)

| Section | Use for |
|---------|---------|
| Critical Bug Fixes | Bugs causing wrong behavior, data loss, crashes |
| Systematic Corrections | Pattern-based fixes across multiple POUs |
| Functional Fixes | Behavioral improvements, duplicate removal |
| Comment and Typo Corrections | Documentation fixes, spelling |
| Dead Code Removed | Unused code cleanup |

## Completeness Checklist

Before finalizing a changelog:

- [ ] Every code change has a corresponding changelog entry
- [ ] File is in `Versions/X.X.X.X/changelog-X.X.X.X.md`
- [ ] Header uses correct format (major vs. bug fix)
- [ ] Breaking changes use `> [!CAUTION]` block
- [ ] All affected FBs/DUTs/Functions listed
- [ ] Code examples use `iecst` syntax highlighting
- [ ] Sections separated with `---`
- [ ] Written in English
- [ ] No implementation details — purpose and impact only

## Reference

For real changelog examples, see [examples.md](examples.md).
