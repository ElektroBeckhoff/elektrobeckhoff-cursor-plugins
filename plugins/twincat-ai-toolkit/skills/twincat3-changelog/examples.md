# Changelog Examples

Slim-first, user-facing. Commit links use the repo’s real `origin` base URL.

---

## Example 1: Patch fix (default slim)

```markdown
# Changelog — Tc3_IoT_BA 1.2.4.6

## Highlights

- **Scene color recall** — RGB scenes no longer fall back to HS+White. ([`a1b2c3d`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/a1b2c3d))
- **Scene feedback** — match requires the active color mode to equal the saved mode. ([`e4f5a6b`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/e4f5a6b))

## Fixed

**`FB_IoT_SceneRGBWBase.CallSceneValues`**
- Saved RGB scenes were recalled via HS+White → wrong output. ([`a1b2c3d`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/a1b2c3d))

**Scene feedback** (`FB_IoT_SceneRGBBase`, `FB_IoT_SceneRGBWBase`, …)
- Feedback counted a match without checking `eActiveColorMode`. ([`e4f5a6b`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/e4f5a6b))
```

---

## Example 2: Small feature (new I/O)

```markdown
# Changelog — Tc3_MyLib 1.0.9.7

## Highlights

- **Smart Optimization** — thermostat setpoints can follow a central offset within min/max. ([`b2c3d4e`](https://github.com/ElektroBeckhoff/Tc3_MyLib/commit/b2c3d4e))

## Added

**`FB_ThermostatControl`**
- `bSmartOptimization : BOOL`, `fHeatingOffset` / `fCoolingOffset : REAL` [°C]. ([`b2c3d4e`](https://github.com/ElektroBeckhoff/Tc3_MyLib/commit/b2c3d4e))

```iecst
fbThermostat[1].bSmartOptimization := TRUE;
fbThermostat[1].fHeatingOffset     := 2.0;
```
```

---

## Example 3: Breaking change + Migration

```markdown
# Changelog — Tc3_Easee 1.0.0.0

## Highlights

- **HTTP client hang fixed** — abandoned requests and expired tokens no longer lock the shared client. ([`c3d4e5f`](https://github.com/ElektroBeckhoff/Tc3_Easee/commit/c3d4e5f))
- **Slave Wallbox removed** — use `FB_Easee_MasterWallbox` for all chargers. ([`d4e5f6a`](https://github.com/ElektroBeckhoff/Tc3_Easee/commit/d4e5f6a))

## Changed

**`FB_Easee_SlaveWallbox` / `ST_Easee_Set_Slave`**

> [!CAUTION]
> **BREAKING CHANGE:** Slave Wallbox types are removed. Switch instances to `FB_Easee_MasterWallbox`.

## Fixed

**`FB_EaseeClient`**
- Shared request slot and token refresh no longer deadlock the charger FBs. ([`c3d4e5f`](https://github.com/ElektroBeckhoff/Tc3_Easee/commit/c3d4e5f))

## Migration

1. Replace `FB_Easee_SlaveWallbox` with `FB_Easee_MasterWallbox`
2. Remove `ST_Easee_Set_Slave` usages
3. Update library reference to 1.0.0.0
```

---

## Example 4: Several commits → one highlight (compare link)

```markdown
# Changelog — Tc3_EB_BA 1.5.5.0

## Highlights

- **Room facade brightness** — RoomControl uses blind facade NESW bits to pick weather kLux. ([compare](https://github.com/ElektroBeckhoff/Tc3_EB_BA/compare/1.5.4.0...1.5.5.0))
- **Milder Daylight PI defaults** — `fKp := 0.02`, `tTi := T#45S`. ([`8084d4a`](https://github.com/ElektroBeckhoff/Tc3_EB_BA/commit/8084d4a))

## Changed

**`I_EB_BA_RoomFeedbackCollector.AddBlindFeedback`**

> [!CAUTION]
> **BREAKING CHANGE:** `AddBlindFeedback` now requires `eFacade : E_EB_BA_Facade`.

## Migration

1. Pass the blind’s `eFacade` into `AddBlindFeedback` if you call it yourself
2. Review Daylight PI defaults if you relied on the previous values
```

---

## Example 5: Multi-commit theme with SHA list

```markdown
# Changelog — Tc3_EMS 1.0.1.3

## Highlights

- **Locked reason on charge points** — HMI can show why a point is locked (`eLockedReason`). ([`f1a2b3c`](https://github.com/ElektroBeckhoff/Tc3_EMS/commit/f1a2b3c))
- **Virtual-limit deadbands** — separate up/down deadbands; faster reaction above setpoint. ([`a9b8c7d`](https://github.com/ElektroBeckhoff/Tc3_EMS/commit/a9b8c7d), [`b8c7d6e`](https://github.com/ElektroBeckhoff/Tc3_EMS/commit/b8c7d6e))

## Changed

**`ST_EMS_ECabinet_Param`**

> [!CAUTION]
> **BREAKING CHANGE:** Deadband members renamed/split; unit is **[% of output range]**.

## Migration

1. Update deadband member names (`…_up` / `…_Down`)
2. Retune overrides if you set custom deadbands or PID defaults
```
