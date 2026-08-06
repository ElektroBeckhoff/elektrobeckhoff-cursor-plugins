---
name: twincat3-cmd-migrate
description: Auto-detect FBD/CFC and migrate TwinCAT .TcPOU implementations to Structured Text (preview-first).
---

# Migrate FBD/CFC â†’ ST

## Read first (in order)

Resolve this plugin root (folder that contains `skills/` and `rules/`). Then **Read**:

1. `skills/twincat3-migrate/SKILL.md`
2. `rules/twincat3-migration-safety.mdc`

If the user insists on **FBD/FUP-only**, also Read:

3. `skills/twincat3-fup-migrate/SKILL.md`
4. `rules/twincat3-fup-safety.mdc`

If the user insists on **CFC-only**, also Read:

3. `skills/twincat3-cfc-migrate/SKILL.md`
4. `rules/twincat3-cfc-safety.mdc`

## Do

Default path (mixed / unspecified): follow `twincat3-migrate`.

1. Analyze â†’ preview (`dry_run`) â†’ migrate â€” do not skip 1â€“2 unless user explicitly allows.
2. After migrate: search `TODO [FBD Migration]` / `TODO [CFC Migration]`.
3. Do **not** run XAE compile (`twincat_open` / `twincat_check_all_objects`) unless the user explicitly asks.
