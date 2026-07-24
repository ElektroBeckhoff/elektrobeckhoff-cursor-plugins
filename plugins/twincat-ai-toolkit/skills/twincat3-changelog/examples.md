# Changelog Examples

Real-world examples from TwinCAT3 library projects, ordered by complexity.

---

## Example 1: Minimal Bug Fix

A single-issue fix — no breaking changes, no new API.

```markdown
## Version 1.1.0.4 – ForceUpdate for view metadata

In `FB_View`, after adding the view metadata, the `ForceUpdate` flag in the JSON
document is now automatically set to `TRUE` if it is not already set. This ensures
that the app receives an update after a metadata change.
```

---

## Example 2: New Feature with Code Example

New feature affecting multiple FBs with new inputs that users need to wire.

```markdown
## Version 1.0.9.7 – Smart Optimization Feature for Thermostat Control

- **New Feature:** Smart Optimization for Thermostat Control System
  - Enables dynamic adjustment of setpoints based on central control
  - Heating: Setpoint can be increased by configurable offset
  - Cooling: Setpoint can be decreased by configurable offset
  - Min/Max limits are respected when applying offsets

**`FB_ThermostatControl`**
- New inputs added:
  - `bSmartOptimization : BOOL` – Enables/disables Smart Optimization
  - `fHeatingOffset : REAL` – Offset for heating [°C]
  - `fCoolingOffset : REAL` – Offset for cooling [°C]

‍```iecst
// example
fbThermostat[1].bSmartOptimization := TRUE;
fbThermostat[1].fHeatingOffset     := 2.0;
fbThermostat[1].fCoolingOffset     := 1.5;
‍```

**Data structures extended:**
- `ST_Thermostat_Data`: Smart Optimization parameters added
- `ST_ThermostatStatus`: Smart Optimization status added
```

---

## Example 3: Breaking Change with Migration

Changes that require user action — removed/renamed APIs, new dependencies.

```markdown
## Version 1.1.0.0 – Message Logging Migration

### Breaking Change

> [!CAUTION]
> **Migration Required:** This version migrates from internal message logging
> to the external `Tc3_IoT_Utilities` library.
>
> - **New Dependency:** Now requires `Tc3_IoT_Utilities` library
> - **Action Required:** Add library reference to your project before updating

### Message Log Level Changes

**Breaking Change in `Param_MyLib`:**

- **New:** `cnMessageLog : BYTE := 2;`

The message logging now uses numeric values instead of enum:

‍```
0 = None, 1 = Critical, 2 = Error (default), 3 = Warning, 4 = Info, 5 = Debug
‍```
```

---

## Example 4: Major Feature Release (EB_BA-style)

Primary template: Highlights → All Changes (Added/Changed/Fixed/Style) → Migration.

```markdown
# Changelog — Tc3_MyLib 1.4.3.0

---

## Highlights

**1. Persistent Restore with Client Age Guard**
All persistent state is gated by a global restore-checked flag so actuators wait
before writing retain values on cold start.

**2. LightAutomatic → LightDaylightAutomatic Rename**
Daylight-based light automation types are renamed for clarity.

---

## All Changes

### Added

**Persistent Restore Infrastructure**
- Global restore-checked flag and latch-based restore on room/facade control FBs

**Status DUTs**
- New status structs for daylight automation and threshold learning

### Changed

**LightAutomatic → LightDaylightAutomatic Rename**

> [!CAUTION]
> **BREAKING CHANGE:** All `LightAutomatic`-related types are renamed to include
> "Daylight". Instance declarations and config struct references must be updated.

- `FB_MyLib_LightAutomatic` → `FB_MyLib_LightDaylightAutomatic`
- Matching DUTs and interfaces renamed the same way

### Fixed

**BlindThermoAutomatic Temperature Activation**
- Re-arm temperature timers after Neutral exit; avoid false activation after reboot

### Style

- Normalized ProductVersion headers after TwinCAT save (no API impact)

---

## Migration

1. Rename all `LightAutomatic` instance and type references to `LightDaylightAutomatic`
2. Wire the new restore-checked / enable-persistent-restore inputs where rooms use retain data
3. Rebuild and verify light automation and persistent restore on a cold start
```

---

## Example 5: Systematic Bug Fix Collection

Audit/cleanup release with categorized fixes across the codebase.

```markdown
## Version 1.2.0.2 – Systematic Bug Fixes and Code Cleanup

- Comprehensive code analysis followed by correction of 8 critical bugs,
  systematic persistent saving fixes, and over 30 comment corrections.

---

### Critical Bug Fixes

**`FB_General`**
- `sMode3` was incorrectly read from `aModes2` instead of `aModes3` (copy-paste error).

**`FB_Widget_Blind`**
- Added `_bTrigSavePersistent := TRUE` in the `bAngleDown_Ads` block.

---

### Persistent Saving – Systematic Correction

Systematic audit of all Standard Control FBs with `VAR PERSISTENT`.
Only `FB_HeatingCooling(Ex)` correctly triggered disk writes on PLC-side changes.

**`FB_SwitchPers` / `FB_SwitchPers_General`**
- Added `bSavePersistent` trigger in the `IF bSwitch <> _bSwitchPers` block.

**Blind FBs** (`FB_RolBldActr`, `FB_SunBldActr`, `FB_Window`)
- Added `bSavePersistent` trigger on `_R_TRIG_SaveShadowPos.Q`.

---

### Functional Fixes

**`FB_ComClient` (WriteAdsSym)**
- Fixed FIND comparison typo `.sMode_Strenght` → `.sMode_Strength`.

---

### Comment and Typo Corrections

**Widget comments** – Copy-paste comments in BuildWidget corrected:
- `FB_Widget_BarChart` → `(* JSON Widget BARCHART *)`
- `FB_Widget_Blind` → `(* JSON Widget BLIND *)`

**DUT corrections:**
- `ST_Input_BOOL` → `'Boolean Value'` instead of `'Boolen Value'`

---

### Dead Code Removed

- `FB_RolBldActr` → Removed `IF FALSE THEN` block
- `FB_SunBldActr` → Removed identical `IF FALSE THEN` block
```
