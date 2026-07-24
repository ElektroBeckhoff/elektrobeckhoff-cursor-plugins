---
name: twincat3-commit
description: Split working-tree changes into thematic Conventional Commits and commit locally. Never pushes.
---

# Thematic Commit

Create local, theme-based Conventional Commits for the current TwinCAT3 library repo.

## Required Context

**Skills:** `twincat3-git-commit` (follow completely)

## Instructions

1. Follow the `twincat3-git-commit` skill end-to-end.
2. Analyze `git status` / diffs, split by theme or file family, and commit each group sequentially.
3. Commit **locally only**.
4. **NEVER** run `git push`, force-push, or any remote update. The user always pushes manually.
5. After finishing, list the commits created and remind the user that nothing was pushed.
