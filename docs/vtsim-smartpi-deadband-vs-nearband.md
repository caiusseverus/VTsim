# VTsim SmartPI Deadband vs Near-Band Behavior

## Summary

Two different effects were present during investigation of SmartPI behavior in VTsim:

1. a VTsim-specific PWM fidelity bug caused by batched event ordering in the simulation engine,
2. a real SmartPI control characteristic where the effective regulation band is much wider than the configured `smart_pi_deadband`.

These two effects must be kept separate.

The first explains why earlier VTsim PWM behavior diverged from Home Assistant.
The second explains why, even after the VTsim engine fix, SmartPI still settles farther from the setpoint than expected from a configured deadband of `0.05 C`.

This document explains:

- what VTsim was doing wrong,
- what SmartPI is doing by design,
- why PWM and linear outputs settle differently,
- why Home Assistant does not show the old VTsim-only PWM pathology,
- and what conclusions can be drawn without modifying VTherm or the linked heating simulator.

## Scope

This document is about:

- VTsim SmartPI scenarios,
- `over_switch` / PWM behavior,
- linear radiator behavior,
- effective regulation around setpoint,
- differences between VTsim and real Home Assistant timing.

This document is not proposing changes to:

- the VTherm source tree,
- the linked heating simulator,
- SmartPI control policy.

## Main Conclusion

There are two distinct truths:

1. VTsim previously had an engine-ordering bug that exaggerated PWM restart churn. That behavior was sim-specific and does not reflect real Home Assistant timing.
2. The remaining steady-state offset is mostly not a VTsim bug. It comes from VTherm SmartPI using an adaptive near-band that is much wider than the configured deadband.

Therefore:

- "deadband is `0.05 C`, so settling should stay around `0.05 C`" is not true for the current SmartPI implementation,
- the configured deadband is only the inner no-action zone,
- the effective control region is usually the larger adaptive near-band,
- actuator type then determines whether the steady-state bias appears slightly high or slightly low.

## Part 1: The VTsim-Specific PWM Fidelity Bug

### Original problem

VTsim used to collapse several different Home Assistant event classes into one synthetic batch per simulation step:

1. publish new sensor values,
2. advance simulated time,
3. fire scheduled callbacks,
4. drain all pending HA work together.

In practice this meant:

- `temp_sensor` state changes,
- `async_track_time_interval` control callbacks,
- `async_call_later` PWM ON/OFF scheduler callbacks,
- and their downstream `start_cycle()` / cancel / restart effects

all competed inside one synthetic transaction.

### Why that was wrong

In real Home Assistant:

- timers progress over real time,
- a running scheduler phase continues naturally,
- sensor state changes do not automatically share an execution instant with unrelated timer callbacks,
- ordering is distributed across the event loop over real timestamps.

In old VTsim:

- sensor publication and timer progression were effectively merged,
- the scheduler was more likely to be restarted or re-evaluated at the wrong synthetic moment,
- PWM cycle continuity was not faithfully represented.

### Why this did not happen in real HA

Because Home Assistant does not batch "publish room temperature" and "fire all time-driven callbacks" into one synthetic sim tick.

That is the core reason the earlier VTsim-only PWM restart pathology was visible in VTsim but not in HA.

### Engine fix applied in VTsim

`tests/sim/engine.py` was changed so each simulation step now has two drains:

1. advance clock, publish sensor updates, drain,
2. fire HA time change, drain again.

That split removes the most problematic batching artifact:

- sensor-driven control no longer shares one undifferentiated transaction with timer-driven callbacks.

### Result

After that engine change:

- the earlier "PWM gets stuck because the sim keeps collapsing restarts and timer callbacks together" problem is no longer the main explanation,
- remaining settling behavior is mostly attributable to SmartPI itself.

## Part 2: Why SmartPI Still Does Not Settle Near `0.05 C`

### Deadband is not the effective regulation band

The configured `smart_pi_deadband` is only the inner deadband.

SmartPI then computes a larger adaptive near-band, and much of the regulation near setpoint happens inside that near-band rather than the configured deadband.

Relevant code path:

- `deadband_c` is set in `prop_algo_smartpi.py`
- `DeadbandManager.update()` decides `in_deadband` and `in_near_band`
- `DeadbandManager.update_near_band_auto()` computes the adaptive near-band

### Internal rules that matter

The current SmartPI implementation contains the following important constants:

- `DEFAULT_DEADBAND_C = 0.05`
- `DEADBAND_HYSTERESIS = 0.025`
- `DEFAULT_NEAR_BAND_DEG = 0.40`
- `NEAR_BAND_ABOVE_FACTOR = 0.40`
- `NEAR_BAND_HYSTERESIS_C = 0.05`

These constants mean:

- deadband entry is at `|error| < deadband`,
- deadband exit is wider than entry,
- near-band entry/exit is wider than deadband,
- heating uses asymmetric near-band thresholds above and below setpoint.

### Critical widening rule

The adaptive near-band is clamped to at least:

- `deadband + 0.1`

So with `smart_pi_deadband = 0.05`,

- the near-band can never be less than `0.15 C`,
- even before model-based widening is added.

This alone already makes the effective control region much wider than the configured deadband.

## Part 3: Quantified Example From PWM

From the PWM sample:

- `a = 0.06431`
- `b = 0.001849`
- `current_temp ~= 20.246`
- `ext_temp = 5.0`
- `cycle_min = 15`
- `deadtime_heat_s = 120`
- `deadtime_cool_s = 120`
- `deadband_c = 0.05`

### Derived terms

- `delta_T = 20.246 - 5.0 = 15.246`
- `s_cool = b * delta_T ~= 0.02819 C/min`
- `s_heat_net = a - s_cool ~= 0.03612 C/min`
- `alpha = s_cool / s_heat_net ~= 0.780`

Cycle horizon terms:

- `cycle_s = 15 * 60 = 900 s`
- `H_below = 120 + 450 = 570 s`
- `H_above = 120 + 450 = 570 s`

Convert net heating slope to per-second:

- `s_heat_s ~= 0.03612 / 60 ~= 0.000602 C/s`

### Near-band result

Below setpoint:

- `nb_below = deadband + s_heat_s * H_below`
- `nb_below ~= 0.05 + 0.000602 * 570 ~= 0.393`

Above setpoint:

- `nb_above = deadband + alpha * s_heat_s * H_above`
- `nb_above ~= 0.05 + 0.780 * 0.000602 * 570 ~= 0.317`

These match the logged values closely:

- `near_band_below_deg ~= 0.3935`
- `near_band_above_deg ~= 0.3174`

### What contributes how much

Below setpoint side:

- configured deadband baseline: `0.05`
- half-cycle term: about `0.271`
- deadtime term: about `0.072`
- total: about `0.393`

Above setpoint side:

- configured deadband baseline: `0.05`
- half-cycle term: about `0.212`
- deadtime term: about `0.056`
- total: about `0.318`

Interpretation:

- the dominant widening term is not the configured deadband,
- it is the combination of half-cycle horizon and deadtime,
- the learned thermal model then shapes the asymmetry.

## Part 4: Quantified Example From Linear Radiator

From the linear sample:

- `current_temperature ~= 19.921`
- `target_temperature = 20.0`
- signed error is about `+0.079 C` below setpoint
- `in_deadband = FALSE`
- `in_near_band = TRUE`
- `near_band_below_deg ~= 0.4009`
- `near_band_above_deg = 0.15`

### What that means

Deadband:

- entry threshold: `0.05`
- exit threshold: `0.05 + 0.025 = 0.075`

The error is `0.079`, so:

- it is outside deadband,
- but it is still well inside near-band because `0.079 < 0.4009`.

So the linear radiator is not "violating deadband."
It is operating exactly as "outside deadband, still inside near-band."

## Part 5: Why PWM Settles Slightly High and Linear Slightly Low

Once the effective regulation region is the near-band rather than the configured deadband, actuator physics matter.

### PWM / switch actuator

PWM can only apply heat in discrete pulses.

Near setpoint this means:

- the controller requests tiny nonzero `on_percent`,
- the scheduler converts that into short ON windows,
- tiny kick pulses can bias the average temperature upward.

This is especially visible when:

- `guard_kick` is active,
- `near_band` is active,
- `committed_on_percent` remains small but positive.

### Linear actuator

Linear output is continuous rather than pulsed.

Near setpoint this means:

- the actuator can hold a small steady output,
- no pulse quantization is needed,
- the room can sit slightly below target while balancing heat loss continuously.

So with the same near-band logic:

- PWM tends to show a small positive bias more easily,
- linear can show a small negative bias more easily.

This is an actuator consequence layered on top of the same SmartPI near-band policy.

## Part 6: Why This Still Appears In VTsim But Not In HA

This question has two different answers depending on which behavior is meant.

### A. The old PWM restart pathology

That was a VTsim-specific engine artifact.

It appeared in VTsim because:

- the engine used to batch sensor events and timer callbacks together,
- scheduler continuity was distorted by the synthetic event model.

It did not appear in HA because:

- Home Assistant schedules those actions over real time,
- timers and sensor events are not collapsed into one synthetic step.

### B. The remaining settling offset around target

That is not primarily a VTsim bug.

It remains visible in VTsim because:

- VTsim is now exercising VTherm SmartPI behavior more faithfully than before,
- SmartPI itself uses a wider adaptive near-band than the configured deadband.

If HA appears not to show it as strongly, likely reasons are:

1. HA observation is often done through rounded display values such as `19.9`, `20.0`, `20.1`, `20.2`.
2. Real-world sensor timing and noise may soften or blur the effect.
3. Real-world plant dynamics may differ from the simulation model.
4. The operator may be visually interpreting the configured deadband as the effective band, when SmartPI is actually regulating against a wider adaptive near-band.

So the correct comparison is:

- old VTsim-only PWM restart churn: sim bug,
- present near-band-driven offset: mostly VTherm SmartPI behavior.

## Part 7: Controls That Widen the Effective Band

The following inputs materially widen the effective near-band:

### User-configurable knobs

- `smart_pi_deadband`
  - base inner deadband only
- `cycle_min`
  - longer cycle increases the half-cycle horizon term
- anything that influences learned `a` and `b`
  - building model and observed temperatures
- anything that influences learned deadtimes
  - plant response and switching history

### Internal SmartPI constants

- `DEADBAND_HYSTERESIS = 0.025`
- `NEAR_BAND_HYSTERESIS_C = 0.05`
- `NEAR_BAND_ABOVE_FACTOR = 0.40`
- minimum adaptive near-band floor of `deadband + 0.1`

### Dominant drivers in the investigated runs

In the examples above, the biggest contributors were:

1. half-cycle horizon from `cycle_min = 15`,
2. deadtime values,
3. model-derived net slope,
4. only then the configured deadband.

## Part 8: Practical Interpretation

With the current VTherm SmartPI implementation:

- the configured deadband should not be interpreted as the final settling band,
- the effective regulation band is the adaptive near-band,
- actuator type changes how that wider band is realized physically.

Therefore:

- a room sitting at about `+0.2 C` in PWM near target is not necessarily evidence of a VTsim bug,
- a linear actuator sitting at about `-0.08 C` is not necessarily evidence of a different control algorithm,
- both can be consistent with the same SmartPI near-band logic.

## Final Conclusion

The investigation shows:

1. VTsim previously had a real PWM fidelity bug caused by batched engine ordering.
2. That bug explains earlier VTsim-only restart pathologies and does not reflect Home Assistant real-time behavior.
3. After fixing the engine ordering, the remaining setpoint-adjacent bias is mostly explained by VTherm SmartPI itself.
4. SmartPI's configured deadband is only the inner comfort zone.
5. The effective regulation band is often much wider because SmartPI computes an adaptive near-band from:
   - deadband,
   - cycle duration,
   - deadtime,
   - learned thermal slopes,
   - and internal near-band hysteresis rules.

For the investigated runs, the effective band was roughly:

- PWM: about `+0.317 C / +0.393 C` near-band limits above/below setpoint,
- linear: about `+0.15 C / +0.401 C` near-band limits above/below setpoint.

That is several times wider than the configured deadband of `0.05 C`.

So the correct framing is:

- the old discrepancy with HA was partly a VTsim engine problem,
- the remaining discrepancy with intuitive "0.05 C deadband" expectations is a SmartPI near-band policy effect.
