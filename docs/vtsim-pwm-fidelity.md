# VTsim PWM Fidelity Problem

## Summary

VTsim currently does not reproduce Home Assistant PWM behavior faithfully when Versatile Thermostat (`VTherm`) is running in `smart_pi` / `over_switch` mode.

The main observed mismatch is:

- In VTsim, room-temperature sensor updates repeatedly restart the PWM cycle.
- In real Home Assistant operation, a running PWM cycle continues much more naturally and is not continually reset by ordinary sensor updates.

This produces a behavioral difference near setpoint and deadband:

- VTsim spends too much time at the start of new PWM cycles.
- The switch turns on more often than expected near zero error.
- Deadband entry and dwell differ from the HA-based simulation and from real HA behavior.

This document describes:

1. the problem,
2. the evidence,
3. the most likely root cause,
4. two implementation options,
5. the recommended fix path.

This document is intended to be sufficient to implement the fix without any additional conversation context.

## Scope

This problem applies to:

- VTsim fast simulation
- `smart_pi` / PWM control
- `over_switch` thermostats

It is specifically about fidelity between:

- VTsim's synthetic step-based event loop
- Home Assistant's real event/timer behavior

It is not primarily a bug in SmartPI deadband logic.

## Observed Symptoms

Near target temperature, VTsim showed:

- large numbers of `temp_sensor`-triggered `control_heating()` calls,
- large numbers of PWM cycle restarts attributed to the same source,
- repeated cycle starts with `cycle_elapsed_sec == 0`,
- switch `on` behavior near zero error that did not match expected settling behavior.

This manifested as a difference in whether VTherm entered or remained in deadband compared with the HA-based simulation.

## Evidence

Harness instrumentation was added in VTsim to measure:

- control entry source counts,
- same-timestamp control calls,
- scheduler cycle start metadata,
- virtual switch command history,
- cycle restart counts by source,
- optional suppression counts for temp-sensor-triggered restarts.

### Control-path evidence

Example late-run control counts showed:

- `temp_sensor` control calls dominating all other sources,
- `smartpi_heartbeat` a distant second,
- `cycle_timer` relatively small,
- `same_timestamp_calls` never indicating exact duplicate same-time re-entry.

This ruled out "same timestamp duplicate control entry" as the primary issue.

### Scheduler evidence

Before suppression, restart counters were effectively dominated by `temp_sensor`.

Representative pattern:

- `control_debug_calls_temp_sensor` approximately equal to `cycle_debug_restart_count_temp_sensor`
- `cycle_debug_cycle_elapsed_sec` repeatedly `0.0`
- `cycle_debug_last_restart_source == temp_sensor`
- `cycle_debug_last_cycle_restart_reason` repeatedly `pwm_cycle` or `zero_on_time`

This means ordinary room-temperature updates were repeatedly restarting the PWM cycle.

### A/B comparison evidence

A harness-only experimental mode was added to suppress non-forced `temp_sensor`-triggered cycle restarts while a cycle is already running.

When comparing baseline vs suppressed behavior in the deadband-adjacent region `abs(smartpi_error) <= 0.06`:

- `deadband_true_share` improved from about `0.846` to about `0.916`
- `mean_abs_error` improved from about `0.0342` to about `0.0300`
- `mean_switch_state` dropped from about `0.769` to about `0.297`
- `max_restart_temp_sensor` dropped from about `3192` to about `65`

This is strong evidence that temp-sensor-driven restart churn is the dominant sim-side fidelity problem.

## Root Cause

### High-level cause

VTsim compresses several Home Assistant behaviors into a single synthetic sim step:

1. advance thermal model,
2. inject new sensor state,
3. advance simulated clock,
4. fire Home Assistant time-change events,
5. drain all pending work immediately.

This batching gives room-temperature updates too much authority over scheduler lifecycle.

### Why this differs from real Home Assistant

In real Home Assistant:

- sensor state changes happen over real time,
- `async_call_later` timers continue independently,
- a running PWM cycle progresses continuously,
- scheduled ON/OFF transitions occur at their intended times,
- control recalculation and cycle progression are interleaved over time rather than collapsed into one synthetic transaction.

In VTsim:

- a room sensor update can trigger `control_heating()`,
- that control pass can cancel/replace the current scheduler cycle immediately,
- the scheduler is frequently returned to the start of a new cycle,
- the PWM ON window is therefore overrepresented.

### What this means semantically

VTsim is currently modeling this behavior:

- "new room temperature implies immediate scheduler restart"

But HA behaves much closer to:

- "new room temperature updates demand; existing scheduled PWM state generally continues unless there is a real reason to interrupt it"

That semantic mismatch is the underlying problem.

## Current Relevant Code Locations

The issue is in the VTsim harness/event model, not in the symlinked VT source tree.

Relevant files:

- `tests/sim/engine.py`
- `tests/test_vt_scenarios.py`
- `tests/sim/virtual_entities.py`

Relevant concepts:

- synthetic simulation step ordering in `run_simulation()`
- monkeypatched `async_call_later`
- harness instrumentation wrapped around `BaseThermostat`, `SmartPIHandler`, and `CycleScheduler`
- virtual switch service handlers for `turn_on` / `turn_off`

Symlinked VTherm code should not be modified to solve this fidelity issue by default.

## Problem Statement

VTsim needs to behave like Home Assistant by default for PWM cycle continuity.

Specifically:

- ordinary room-temperature sensor updates must not continuously reset an in-flight PWM cycle,
- scheduled ON/OFF timing must remain authoritative once a cycle is running,
- demand recalculation and cycle replacement must be separated.

## Solution Option 1: Preserve Running PWM Cycles

### Description

This option keeps the existing VTsim step model but changes scheduler behavior so that ordinary `temp_sensor`-triggered control passes do not restart an already-running cycle.

This should become the VTsim default behavior if the goal is HA fidelity.

### Intended semantics

While a cycle is already running:

- allow demand recalculation,
- update stored cycle parameters for future use,
- do not tear down and recreate the active cycle on ordinary `temp_sensor` control passes.

Still allow immediate restart when appropriate:

- forced restarts,
- cycle-end restarts,
- scheduler-driven cadence,
- optionally heartbeat-driven paths if needed,
- optionally explicit external-force paths if required by VT semantics.

### Recommended default rule

When `CycleScheduler.start_cycle()` is called:

- if source is `temp_sensor`,
- and `is_cycle_running` is `True`,
- and `force` is `False`,
- and `_from_cycle_end` is `False`,
- then do not restart the cycle.

Instead:

- recompute and store:
  - `_current_hvac_mode`
  - `_current_on_time_sec`
  - `_current_off_time_sec`
  - `_current_on_percent`
  - thermostat `_on_time_sec`
  - thermostat `_off_time_sec`
- leave the active scheduler timing and current cycle phase intact.

### Why this works

This preserves the core HA-like invariant:

- a running cycle keeps progressing,
- temperature updates influence future demand,
- but do not repeatedly re-arm the current PWM phase.

### Existing experimental implementation

An experimental harness-only implementation already exists in `tests/test_vt_scenarios.py` behind the environment variable:

- `VTSIM_SUPPRESS_TEMP_SENSOR_RESTARTS=1`

That implementation wraps `CycleScheduler.start_cycle()` and suppresses temp-sensor-driven non-forced restarts while a cycle is running.

### Changes required to make this the default

1. Remove the environment-variable gate.
2. Keep the suppression logic active by default.
3. Optionally add an opt-out flag if legacy behavior must remain available.

### Advantages

- low risk,
- narrow behavioral change,
- strong evidence already supports improved fidelity,
- easy to validate against HA runs,
- does not require changing tested VTherm source.

### Risks

- this is a behavioral policy in the harness, not a general event-kernel rewrite,
- if HA actually does restart cycles from ordinary sensor updates in some future VT version, VTsim could diverge,
- the policy depends on the assumption that cycle continuity is the correct HA semantic.

### When this option is sufficient

Use this option if:

- the primary goal is accurate HA-like PWM behavior now,
- the simulator must remain stable and maintainable,
- the observed mismatch is specifically temp-sensor restart churn.

## Solution Option 2: Rewrite VTsim Event Semantics

### Description

This option changes the simulation engine so synthetic steps no longer collapse all HA event types into one atomic batch that allows immediate scheduler replacement from sensor updates.

This is architecturally cleaner and potentially more faithful in the long term.

### Goal

Make VTsim event ordering and timer behavior look more like Home Assistant:

- scheduled callbacks advance independently,
- sensor updates are processed as events,
- PWM cycle timing progresses continuously,
- recalculation does not automatically imply cycle replacement.

### What would need to change

#### 1. Separate event classes inside a step

The engine should distinguish:

- plant/physics advancement,
- sensor publication,
- scheduler timer callbacks,
- control recalculation,
- actuation/switch commands.

These should not all be treated as one undifferentiated "tick".

#### 2. Preserve scheduler phase across sensor events

The scheduler should maintain cycle phase independently of room sensor updates.

A new sensor value may update demand, but should not implicitly return the scheduler to `t=0`.

#### 3. Process scheduled callbacks according to simulated time, not step-side batching

`async_call_later` callbacks should fire based on an event queue or equivalent simulated-time ordering that more closely mirrors HA scheduling.

This may require:

- sub-step event processing,
- priority ordering between scheduled timers and state-change handling,
- explicit simulated-time event queue handling rather than "inject everything, then drain everything".

#### 4. Distinguish "new command target" from "replace active cycle"

The engine should support:

- recompute target power now,
- apply to the current cycle only when semantics demand it,
- otherwise use it at the next valid boundary.

### Possible implementation directions

#### Direction A: event queue in the engine

Refactor `tests/sim/engine.py` so each top-level time step may contain multiple internal simulated events ordered by timestamp:

- pending timer callback,
- sensor state change,
- scheduler transition,
- next record boundary.

#### Direction B: two-phase control application

Keep coarse stepping but split the control side into:

- phase 1: update control demand from sensors,
- phase 2: let scheduler adopt updated demand only at approved boundaries.

This is closer to Option 1 but built into engine semantics rather than enforced as a scheduler policy gate.

### Advantages

- more principled,
- more generically HA-like,
- less likely to require special-case rules if more fidelity issues appear later.

### Risks

- much larger implementation surface,
- easier to introduce subtle ordering bugs,
- harder to validate,
- harder to keep compatible across different VT versions,
- more work than needed to solve the currently demonstrated mismatch.

### When this option is appropriate

Use this option if:

- VTsim is intended to become a high-fidelity HA event simulator generally,
- multiple timing/fidelity issues beyond PWM restart churn need to be solved,
- the team is willing to validate a larger refactor carefully.

## Recommended Path

### Recommended immediate fix

Adopt Option 1 as the new VTsim default:

- preserve running PWM cycles across ordinary `temp_sensor` recalculations,
- allow only appropriate restart sources to replace an in-flight cycle.

Reason:

- this directly fixes the observed mismatch,
- it has strong empirical support from A/B testing,
- it is much lower risk than rewriting the simulation event kernel.

### Recommended follow-up

Treat Option 2 as a future architectural improvement, not a prerequisite for fixing the current fidelity bug.

If Option 2 is pursued later, it should be validated against:

- the current Option 1 behavior,
- HA-based simulation traces,
- real HA scenarios where possible.

## Concrete Acceptance Criteria

After implementing the default fix, VTsim should show all of the following in deadband-adjacent windows:

1. `temp_sensor` no longer dominates cycle restarts.
2. `cycle_debug_restart_count_temp_sensor` stays low relative to `control_debug_calls_temp_sensor`.
3. deadband share near setpoint is materially closer to HA-based sim.
4. switch activity near zero error is materially lower than the old VTsim baseline.
5. active PWM cycles are not repeatedly reset to `cycle_elapsed_sec == 0` by ordinary sensor updates.

## Suggested Validation Queries

Compare baseline and fixed runs in the region:

- `abs(smartpi_error) <= 0.06`

Key metrics:

- `smartpi_in_deadband`
- `mean_abs_error`
- `mean_switch_state`
- `cycle_debug_restart_count_temp_sensor`
- `control_debug_calls_temp_sensor`
- `switch_cycles`

Interpretation:

- more deadband rows,
- lower switch activity near zero error,
- dramatically fewer temp-sensor cycle restarts

all indicate improved HA fidelity.

## Implementation Notes

### Default behavior target

VTsim should default to HA-like cycle continuity.

If any compatibility toggle is retained, it should be an opt-out for legacy behavior, not an opt-in for the fix.

### Version-compatibility requirement

Because VTsim tests against multiple versions of `versatile_thermostat` via a symlinked source tree:

- changes should remain in the VTsim harness where possible,
- monkeypatching should be preferred over editing VT source,
- patches should fail gracefully when a target class or method does not exist in older VT versions.

## Short Conclusion

The fidelity problem is caused by VTsim collapsing sensor updates and scheduler lifecycle into the same synthetic step, allowing room-temperature events to repeatedly restart PWM cycles.

The practical fix is to make VTsim preserve a running PWM cycle by default and stop treating ordinary `temp_sensor` updates as immediate cycle-restart events.

That fix already has strong evidence supporting it and should be adopted as the default VTsim behavior.
