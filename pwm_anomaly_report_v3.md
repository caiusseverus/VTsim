# PWM Thermostat Controller – Heater Timing Anomaly Report

**File analysed:** `pwm_r2c2_records__3_.csv`  
**Total rows:** 4,320 (plus header = 4,321 CSV lines), one row per 60 s  
**Data structure:** Three 24-hour runs beginning at elapsed 10 s, 86,410 s, 172,810 s  
**PWM cycle time:** 900 s (15 minutes = 15 rows per cycle)

---

## How the PWM Timing Should Work

The controller computes a `power_percent` (0–100) and translates it into a duty cycle over the 15-minute cycle. The heater should be ON (`switch_state = 1`) for `power_percent / 100 × 900 s` and OFF for the remainder. At 50% power that is 450 s ON / 450 s OFF; at 100% it is on continuously. `model_effective_heater_power_w` should equal 1,000 W while the switch is closed and 0 W when it is open.

---

## Summary of Findings

There are two distinct bug classes:

1. **`model_effective_heater_power_w` reads `hvac_action`, not `switch_state`.** The power model always applies 1,000 W whenever `hvac_action = 'heating'` and 0 W otherwise, completely ignoring the PWM switch position. This means the thermal simulation is always wrong during partial-power operation.

2. **The PWM switch fails to fire for extended periods despite non-zero `power_percent`.** There are multiple multi-hour blocks where `switch_state` remains 0 even though the controller is commanding substantial power. Conversely, there are shorter blocks where the switch remains ON longer than the commanded duty cycle dictates. The net effect is that the heater delivers far more or far less energy than commanded, in addition to the model not tracking it correctly.

---

## Bug 1: model_effective_heater_power_w Ignores switch_state

### Mechanism

`model_effective_heater_power_w == (hvac_action == 'heating') × 1,000 W` in 4,317 of 4,320 rows (99.93%). By contrast, `model_effective_heater_power_w == switch_state × 1,000 W` holds in only 4,106 rows (95.06%), with **214 mismatches**.

### Effect

- During any heating cycle with `power_percent < 100`, the model treats the heater as continuously at 1,000 W for the entire heating period, not just during the ON phase of the duty cycle.
- When `switch_state = 0` but `hvac_action = 'heating'` (e.g. during the OFF portion of a PWM cycle), `model_effective_heater_power_w = 1,000 W`, causing temperature to rise when it should be stable or falling.
- When `switch_state = 1` but `hvac_action = 'idle'` (switch not yet reset after a heating period), `model_effective_heater_power_w = 0`, causing temperature to fall when the heater is physically on.

### Key Anomalous Rows (Type A: switch OFF but model shows 1,000 W)

**112 rows** where `switch_state = 0` yet `model_effective_heater_power_w = 1,000 W`. All have `hvac_action = 'heating'` and `power_percent = 0` (or ≤ 1). Temperature rises at these points (mean +0.020 °C/step). They are concentrated in the `saturated` and `hold` governance regimes and scattered throughout the dataset; the full line-by-line list is in the original report.

### Key Anomalous Rows (Type B: switch ON but model shows 0 W)

**102 rows** where `switch_state = 1` yet `model_effective_heater_power_w = 0`. Three of these are the very first record of each 24-hour run (CSV lines **2, 1,442, 2,882** — a one-step initialisation lag at the start of each run). The remaining 99 occur during `hvac_action = 'idle'` when the switch has not yet been reset to 0.

### Fix

In the code that computes `model_effective_heater_power_w`, replace any conditional based on `hvac_action` with `switch_state × rated_power_w`.

---

## Bug 2: PWM Switch Timing Failures

### Normal Operation (for reference)

In the well-behaved early period — cycles 0–18, CSV lines 2–286, elapsed 10–17,110 s — the switch fires correctly with zero error in every cycle. Each cycle contains exactly `round(power_percent / 100 × 15)` rows of `switch_state = 1`, confirming the PWM mechanism correctly translates duty cycle to row count. The ON pulse is always a single contiguous block, placed at the start of the cycle when `power_percent > 50%` and at the end when `power_percent < 50%`. Examples from this correct period:

| Cycle | Elapsed start (s) | CSV lines | power_percent | Expected ON rows | Actual switch pattern |
|---|---|---|---|---|---|
| 3 | 2,710 | 47–61 | 60% | 9 | `[1,1,1,1,1,1,1,1,1,0,0,0,0,0,0]` |
| 6 | 5,410 | 92–106 | 60% | 9 | `[0,0,0,0,0,0,1,1,1,1,1,1,1,1,1]` |
| 7 | 6,310 | 107–121 | 73% | 11 | `[1,1,1,1,1,1,1,1,1,1,1,0,0,0,0]` |
| 10 | 9,010 | 152–166 | 53% | 8 | `[0,0,0,0,0,0,0,1,1,1,1,1,1,1,1]` |
| 11 | 9,910 | 167–181 | 80% | 12 | `[1,1,1,1,1,1,1,1,1,1,1,1,0,0,0]` |
| 14 | 12,610 | 212–226 | 47% | 7 | `[0,0,0,0,0,0,0,0,1,1,1,1,1,1,1]` |
| 15 | 13,510 | 227–241 | 87% | 13 | `[1,1,1,1,1,1,1,1,1,1,1,1,1,0,0]` |
| 18 | 16,210 | 272–286 | 33% | 5 | `[0,0,0,0,0,0,0,0,0,0,1,1,1,1,1]` |

From cycle 19 onward (CSV line 287, elapsed 17,110 s), the timing begins to break down. Of the 288 total 15-minute cycles in the dataset, only 94 have zero (or negligible) timing error. The remaining **178 cycles have errors exceeding one full row (60 s)**.

### Anomaly Type 1: Switch Stuck OFF During Commanded Heating

There are **21 blocks** (≥ 5 consecutive rows = ≥ 5 min) where `switch_state` is continuously 0 despite `power_percent > 10`. These range from 22 minutes to **12 hours**. During all of these, `hvac_action` is `idle` and `model_effective_heater_power_w = 0` — the control system has concluded no heat is needed despite `power_percent` climbing.

**Complete list:**

| Start CSV | End CSV | Start elapsed (s) | End elapsed (s) | Duration | Mean power% | Max power% | Run |
|---|---|---|---|---|---|---|---|
| 288 | 309 | 17,170 | 18,430 | 22 min | 12% | 22% | 1 |
| 321 | 349 | 19,150 | 20,830 | 29 min | 41% | 76% | 1 |
| 363 | 393 | 21,670 | 23,470 | 31 min | 49% | 87% | 1 |
| 539 | 573 | 32,230 | 34,270 | 35 min | 47% | 91% | 1 |
| 590 | 625 | 35,290 | 37,390 | 36 min | 52% | 96% | 1 |
| 642 | 676 | 38,410 | 40,450 | 35 min | 50% | 94% | 1 |
| **2162** | **2881** | **129,610** | **172,750** | **12.0 hours** | **35%** | **86%** | **1** |
| 2956 | 2979 | 177,250 | 178,630 | 24 min | 48% | 92% | 2 |
| 2993 | 3015 | 179,470 | 180,790 | 23 min | 49% | 91% | 2 |
| 3041 | 3064 | 182,350 | 183,730 | 24 min | 45% | 89% | 2 |
| 3082 | 3104 | 184,810 | 186,130 | 23 min | 48% | 91% | 2 |
| 3144 | 3168 | 188,530 | 189,970 | 25 min | 43% | 90% | 2 |
| 3187 | 3209 | 191,110 | 192,430 | 23 min | 48% | 91% | 2 |
| 3363 | 3388 | 201,670 | 203,170 | 26 min | 42% | 91% | 2 |
| 3409 | 3432 | 204,430 | 205,810 | 24 min | 45% | 90% | 2 |
| 3452 | 3474 | 207,010 | 208,330 | 23 min | 49% | 92% | 2 |
| 3509 | 3531 | 210,430 | 211,750 | 23 min | 49% | 92% | 2 |
| **3588** | **3969** | **215,170** | **238,030** | **6.4 hours** | **25%** | **86%** | **3** |
| **3979** | **4130** | **238,630** | **247,690** | **2.5 hours** | **51%** | **86%** | **3** |
| **4140** | **4279** | **248,290** | **256,630** | **2.3 hours** | **49%** | **86%** | **3** |
| 4292 | 4321 | 257,410 | 259,150 | 30 min | 15% | 27% | 3 |

**The 12-hour stuck-off block (CSV 2162–2881)** is the most severe instance. It spans the final 43,200 s of run 1. During this period:
- `hvac_action` is `idle` for all 720 rows.
- `power_percent` starts at 0%, then climbs continuously from ~10% (CSV 2462) to 86% (CSV 2872) — the controller recognises the room is cold and escalates the requested duty cycle, but the switch never fires.
- `model_temperature` falls from 20.1 °C to 17.1 °C, a drop of 3 °C over 12 hours.
- Because Bug 1 means the model only registers heat when `hvac_action = 'heating'`, it fails to detect the heater is truly off, and the controller cannot escape the `idle` state.

The **three run-3 stuck-off blocks** (CSV 3588–3969, 3979–4130, 4140–4279) together total approximately 11 hours of heater lock-out. Each follows the same pattern: `power_percent` rises to 86% while the switch remains closed-off.

### Anomaly Type 2: Switch Stuck ON Longer Than Commanded

There are **20 blocks** (≥ 5 rows) where `switch_state = 1` throughout despite `mean_power_percent < 90%`. These represent the heater ON pulse overshooting its allotted time within the 15-minute cycle — the switch turned on but the off-trigger fired late or not at all as `power_percent` dropped during the heating event.

**Complete list:**

| Start CSV | End CSV | Start elapsed (s) | End elapsed (s) | Duration | Mean power% | Min power% | Run |
|---|---|---|---|---|---|---|---|
| 310 | 320 | 18,490 | 19,090 | 11 min | 31% | 5% | 1 |
| 350 | 362 | 20,890 | 21,610 | 13 min | 41% | 4% | 1 |
| 394 | 407 | 23,530 | 24,310 | 14 min | 49% | 9% | 1 |
| 574 | 589 | 34,330 | 35,230 | 16 min | 44% | 3% | 1 |
| 626 | 641 | 37,450 | 38,350 | 16 min | 50% | 4% | 1 |
| 677 | 692 | 40,510 | 41,410 | 16 min | 45% | 3% | 1 |
| **1442** | **1494** | **86,410** | **89,530** | **53 min** | **87%** | **8%** | **2 start** |
| 2980 | 2992 | 178,690 | 179,410 | 13 min | 45% | 3% | 2 |
| 3016 | 3029 | 180,850 | 181,630 | 14 min | 41% | 1% | 2 |
| 3065 | 3077 | 183,790 | 184,510 | 13 min | 49% | 15% | 2 |
| 3105 | 3117 | 186,190 | 186,910 | 13 min | 49% | 15% | 2 |
| 3169 | 3182 | 190,030 | 190,810 | 14 min | 46% | 1% | 2 |
| 3210 | 3222 | 192,490 | 193,210 | 13 min | 48% | 15% | 2 |
| 3389 | 3403 | 203,230 | 204,070 | 15 min | 42% | 1% | 2 |
| 3433 | 3446 | 205,870 | 206,650 | 14 min | 46% | 1% | 2 |
| 3475 | 3489 | 208,390 | 209,230 | 15 min | 40% | 2% | 2 |
| 3532 | 3544 | 211,810 | 212,530 | 13 min | 46% | 5% | 2 |
| 3970 | 3978 | 238,090 | 238,570 | 9 min | 43% | 5% | 3 |
| 4131 | 4139 | 247,750 | 248,230 | 9 min | 46% | 17% | 3 |
| 4280 | 4288 | 256,690 | 257,170 | 9 min | 42% | 4% | 3 |

In all stuck-ON blocks, `power_percent` trends downward within the block — the switch turned on when `power_percent` was higher and has not been turned off as the controller reduced the commanded duty cycle. The **53-minute stuck-ON block at CSV 1442–1494** (start of run 2) is the most prominent, where the switch remains on from `power_percent = 100%` all the way down to 8%.

Note that stuck-OFF and stuck-ON blocks appear in alternating pairs throughout the data. Each stuck-ON block immediately follows a stuck-OFF block. This is a consequence of the same underlying fault: the PWM ON pulse fires late (after the stuck-OFF gap), then runs long (the stuck-ON overshoot), and the excess carry-over into the next window displaces the expected firing in the cycle after that.

---

## Temperature Consequences

Because `model_effective_heater_power_w` follows `hvac_action` rather than `switch_state`, the simulated temperature is driven by the wrong signal throughout. In practice:

- During a stuck-OFF block where `hvac_action = 'idle'`: temperature falls continuously. The model correctly shows no heat input, but only accidentally — the *reason* is wrong (model believes action is idle; the actual fault is the switch is broken).
- During the catastrophic 12-hour stuck-off: `model_temperature` falls 3 °C while `power_percent` reaches 86%. The controller escalates heat demand; the switch never responds; the model does not register the failure because it evaluates power from `hvac_action`, not `switch_state`.
- During a stuck-ON block: temperature rises faster than `power_percent` justifies, because the switch delivers more energy than the commanded duty cycle.

---

## Debugging Priorities

1. **Fix `model_effective_heater_power_w` computation (Bug 1):** Replace `if hvac_action == 'heating': power = 1000` with `power = switch_state * rated_power_w`. This immediately corrects the simulation tracking and is a prerequisite for diagnosing Bug 2, because the current model masks the switch failure.

2. **Investigate why `hvac_action` locks to `idle` for hours despite `power_percent` rising (Bug 2, stuck-OFF).** The smoking gun is CSV lines 2162–2881: `power_percent` reaches 86%, the room cools 3 °C, but `hvac_action` never transitions to `heating` and the switch never fires. Look for a condition blocking the `idle → heating` transition that is gated on `model_effective_heater_power_w` or another model-derived signal — fixing Bug 1 may break this deadlock directly.

3. **Investigate the PWM OFF-trigger when `power_percent` decreases mid-cycle (Bug 2, stuck-ON).** The switch stays on when `power_percent` drops during a heating event. Verify the logic that determines when to open the switch responds to real-time changes in `power_percent`, not just the value sampled at the start of the 15-minute cycle.

4. **Verify the 15-minute PWM timer is free-running.** The clean early period confirms the timer and duty-cycle calculation are correct in isolation. The failures all occur after the controller begins adjusting `power_percent` dynamically. Confirm the PWM timer is not being reset or re-evaluated when the controller updates `power_percent` mid-cycle, which could cause the pulse to misfire on every update.
