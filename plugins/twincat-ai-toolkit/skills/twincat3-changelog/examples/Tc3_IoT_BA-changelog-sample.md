# Changelog — Tc3_IoT_BA 1.2.5.0

Example of the slim-first format for [ElektroBeckhoff/Tc3_IoT_BA](https://github.com/ElektroBeckhoff/Tc3_IoT_BA).  
Commit links use real SHAs from that repo (`git remote get-url origin` → `https://github.com/ElektroBeckhoff/Tc3_IoT_BA`).

---

## Highlights

- **New widgets** — SubHeadline, TrafficLight, Stepper, and StatusLED for app layout and indicators. ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))
- **Safer OnChange on CX9020** — OnChange publish is disabled on CX9020 (like x86) to avoid Tc3_JsonXml DOM crashes. ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))
- **Type-safe controller ID** — device class/type use `E_IoT_ControllerType` instead of raw string checks. ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

## Added

**`FB_IoT_Widget_SubHeadline`**
- Display-only headline separator for structuring the app layout. ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

**`FB_IoT_Widget_TrafficLight`**
- Three-color traffic light with selectable operation modes. ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

**`FB_IoT_Widget_Stepper`**
- Step back/forward with one-cycle pulse outputs `bBack` / `bForward`. ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

**`FB_IoT_Widget_StatusLED`**
- Single-color LED with blink pattern (`stColor` or raw UDINT). ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

**`E_IoT_ControllerType`**
- Enum for controller identification (used by platform gating / diagnostics). ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

## Changed

**OnChange platform gating**
- OnChange stays off on **CX9020** and **x86**; full cyclic publish unchanged on all platforms. ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

| Platform | OnChange |
|---|---|
| x64 (C60xx, CX2xxx, CX5x40+) | enabled |
| ARM (CX8xxx, CX7xxx) | enabled |
| ARM – CX9020 | **disabled** |
| x86 (CX5120, CX5130) | disabled |

## Fixed

**`F_IoT_IdentifyControllerClass`**
- CX9020 is identified as `Embedded` (was unrecognized). ([`47146bd`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/47146bd))

---

# Changelog — Tc3_IoT_BA 1.2.4.6

Smaller patch example (same repo).

## Highlights

- **Scene color recall** — RGB scenes no longer fall back to HS+White. ([`d9aa79a`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/d9aa79a))
- **Scene feedback** — a match requires `eActiveColorMode` to equal the saved mode. ([`d9aa79a`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/d9aa79a))

## Fixed

**`FB_IoT_SceneRGBWBase.CallSceneValues`**
- Saved RGB scenes were recalled via HS+White → wrong color output. ([`d9aa79a`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/d9aa79a))

**Scene feedback** (`FB_IoT_SceneRGBBase`, `FB_IoT_SceneRGBColorTempBase`, `FB_IoT_SceneRGBWBase`, `FB_IoT_SceneRGBWColorTempBase`)
- Feedback could report a match when brightness matched but the color mode differed. ([`d9aa79a`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/d9aa79a))

---

# Changelog — Tc3_IoT_BA 1.2.5.1 *(draft / not released)*

Unreleased follow-up already on `main` — example of a one-commit patch note.

## Highlights

- **Stepper JSON keys** — `bBack` / `bForward` are published in `BuildWidget` so the app receives the pulse outputs. ([`7757f30`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/7757f30))

## Fixed

**`FB_IoT_Widget_Stepper`**
- Missing `bBack` / `bForward` keys in the widget JSON. ([`7757f30`](https://github.com/ElektroBeckhoff/Tc3_IoT_BA/commit/7757f30))
