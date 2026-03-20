"""Core simulation loop for the VT native simulation suite.

Expected call sequence in the test:
    1. model = create_model(scenario["model"])
    2. inject_temperature(hass, TEMP_ID, model.temperature)
    3. inject_temperature(hass, EXT_ID, model.external_temperature)
    4. await async_setup_virtual_switch(hass, HEATER_ID)   # or virtual_number
    5. monkeypatch SmartPI monotonic clock
    6. await setup_vt_integration(hass, scenario)
    7. records = await run_simulation(hass, model=model, ...)

The loop ordering eliminates a one-step control lag:

    for each step:
        1. apply disturbances          set ext_temp / occupancy / weather on model
        2. model.step(dt_s)           physics forward using *previous* heater command
        3. sensor_temp = pipeline(...)  degrade model.temperature (lag/noise/rate-limit)
        4. inject_temperature(...)     queue degraded room temp into HA
        5. advance_clock(dt_s)         advance SmartPI monotonic
        6. async_fire_time_changed()   drain queue + fire VT timers
        7. async_block_till_done()     VT sees updated temp, fires ON/OFF transitions
        8. prev_power = read_power()   read new heater command for next step

VT's async_call_later callbacks (ON→OFF mid-cycle) fire naturally at step 3–4
when async_fire_time_changed advances past their scheduled time.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time as _time_module
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

# Capture the real monotonic clock before any test harness patches it.
# Used for wall-clock timeout checks inside the simulation loop.
_REAL_MONOTONIC = _time_module.monotonic

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .virtual_entities import inject_temperature, read_number_power, read_switch_power

import sys as _sys
from pathlib import Path as _Path

# Allow importing disturbances directly from the heating_simulator source.
# Resolution order matches models.py: VTSIM_HEATING_SIM_DIR env var first,
# then the custom_components symlink fallback for CLI pytest.
_hs_env = os.environ.get("VTSIM_HEATING_SIM_DIR")
_HS_ROOT = _Path(_hs_env) if _hs_env else _Path(__file__).resolve().parents[2] / "custom_components" / "heating_simulator"
if str(_HS_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_HS_ROOT))

from disturbances import ExternalTempProfile, OccupancyProfile, WeatherProfile  # noqa: E402
from .sensor_pipeline import SensorPipeline  # noqa: E402

_LOG = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def _capture_snapshot(
    hass: HomeAssistant,
    climate_entity_id: str,
    model: Any,
    elapsed_s: float,
    sensor_temperature: float | None = None,
) -> dict[str, Any]:
    """Build a record from current HA climate state + thermal model state."""
    state = hass.states.get(climate_entity_id)
    if state is None:
        return {"elapsed_s": elapsed_s, "elapsed_h": elapsed_s / 3600.0}

    attrs = state.attributes

    # target_temperature lives under "temperature" in the HA climate standard,
    # but VT also nests it in current_state for some configurations.
    target_temp = attrs.get("temperature")
    if target_temp is None:
        cs = attrs.get("current_state") or {}
        if isinstance(cs, dict):
            target_temp = cs.get("target_temperature")

    specific = attrs.get("specific_states") or {}
    smart_pi = specific.get("smart_pi", {}) if isinstance(specific, dict) else {}
    if not isinstance(smart_pi, dict):
        smart_pi = {}

    return {
        "elapsed_s": elapsed_s,
        "elapsed_h": elapsed_s / 3600.0,
        # Physics ground truth
        "model_temperature": model.temperature,
        "sensor_temperature": sensor_temperature,   # degraded — what VTherm saw
        "model_ext_temperature": model.external_temperature,
        # VT view of the world
        "current_temperature": attrs.get("current_temperature"),
        "target_temperature": target_temp,
        "hvac_action": attrs.get("hvac_action"),
        "hvac_mode": attrs.get("hvac_mode"),
        "preset_mode": attrs.get("preset_mode"),
        "on_percent": attrs.get("on_percent"),
        "power_percent": attrs.get("power_percent"),
        # SmartPI internals
        "smartpi_a": smart_pi.get("a"),
        "smartpi_b": smart_pi.get("b"),
        "smartpi_learn_ok_count_a": smart_pi.get("learn_ok_count_a"),
        "smartpi_learn_ok_count_b": smart_pi.get("learn_ok_count_b"),
        "smartpi_learn_last_reason": smart_pi.get("learn_last_reason"),
        "smartpi_governance_regime": smart_pi.get("governance_regime"),
        "smartpi_phase": smart_pi.get("phase"),
        "deadtime_heat_s": smart_pi.get("deadtime_heat_s"),
        # Model direct physical quantities
        **{
            "model_effective_heater_power_w": getattr(model, "effective_heater_power", None),
            "model_heating_rate_c_per_s":     getattr(model, "heating_rate", None),
            "model_heat_loss_rate_c_per_s":   getattr(model, "heat_loss_rate", None),
            "model_net_heat_rate_c_per_s":    getattr(model, "net_heat_rate", None),
        },
        # Model-type specific quantities (radiator_temperature, fabric_temperature, etc.)
        **{
            f"model_{k}": v
            for k, v in (getattr(model, "extra_state", None) or {}).items()
        },
    }


def _build_disturbances(
    cfg: dict[str, Any],
) -> tuple[ExternalTempProfile, OccupancyProfile, WeatherProfile]:
    """Build disturbance objects from the scenario ``disturbances:`` config section."""
    ep_cfg  = cfg.get("ext_temp_profile", {}) or {}
    occ_cfg = cfg.get("occupancy", {}) or {}
    wx_cfg  = cfg.get("weather", {}) or {}

    ext_profile = ExternalTempProfile(
        enabled        = bool(ep_cfg.get("enabled", False)),
        base_temp      = float(ep_cfg.get("base", 5.0)),
        temp_amplitude = float(ep_cfg.get("amplitude", 3.0)),
        min_hour       = float(ep_cfg.get("min_hour", 5.5)),
        max_hour       = float(ep_cfg.get("max_hour", 14.5)),
    )

    occupancy = OccupancyProfile(
        enabled                = bool(occ_cfg.get("enabled", False)),
        max_occupants          = int(occ_cfg.get("max_occupants", 2)),
        cooking_power_watts    = float(occ_cfg.get("cooking_power_w", 0.0)),
        cooking_duration_s     = float(occ_cfg.get("cooking_duration_s", 1200.0)),
        cooking_events_per_day = float(occ_cfg.get("cooking_events_per_day", 2.0)),
        seed                   = int(occ_cfg.get("seed", 42)),
    )

    weather = WeatherProfile(
        wind_speed_m_s          = float(wx_cfg.get("wind_speed_m_s", 0.0)),
        wind_coefficient        = float(wx_cfg.get("wind_coefficient", 0.0)),
        rain_intensity_fraction = float(wx_cfg.get("rain_intensity", 0.0)),
        rain_moisture_factor    = float(wx_cfg.get("rain_moisture_factor", 0.0)),
    )

    return ext_profile, occupancy, weather


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

def _fmt_f(val: Any, width: int, decimals: int) -> str:
    try:
        return f"{float(val):{width}.{decimals}f}"
    except (TypeError, ValueError):
        return "n/a".rjust(width)


def _fmt_i(val: Any, width: int) -> str:
    try:
        return f"{int(val):{width}d}"
    except (TypeError, ValueError):
        return "n/a".rjust(width)


def _print_progress(
    step: int,
    total_steps: int,
    elapsed_s: float,
    snap: dict[str, Any],
) -> None:
    h = int(elapsed_s // 3600)
    m = int((elapsed_s % 3600) // 60)
    reason = str(snap.get("smartpi_learn_last_reason") or "")[:40].ljust(40)
    phase = str(snap.get("smartpi_phase") or "n/a")[:10].ljust(10)
    print(
        f"\rstep {step:5d}/{total_steps:<5d} "
        f"t={h:03d}h{m:02d}m "
        f"T={_fmt_f(snap.get('model_temperature'), 7, 3)}C "
        f"tgt={_fmt_f(snap.get('target_temperature'), 6, 2)}C "
        f"pwr={_fmt_f(snap.get('power_percent'), 5, 1)}% "
        f"a={_fmt_f(snap.get('smartpi_a'), 8, 5)} "
        f"b={_fmt_f(snap.get('smartpi_b'), 8, 5)} "
        f"ok_a={_fmt_i(snap.get('smartpi_learn_ok_count_a'), 4)} "
        f"ok_b={_fmt_i(snap.get('smartpi_learn_ok_count_b'), 4)} "
        f"phase={phase} "
        f"reason={reason}",
        end="",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_simulation(
    hass: HomeAssistant,
    *,
    model: Any,
    control_mode: str,
    heater_entity_id: str,
    temp_sensor_id: str,
    ext_sensor_id: str,
    climate_entity_id: str,
    scenario: dict[str, Any],
    advance_clock: Callable[[float], None],
    wall_clock_timeout_s: float = 600.0,
    on_record: "Callable[[dict[str, Any]], None] | None" = None,
) -> list[dict[str, Any]]:
    """Run the simulation loop and return a list of timestamped snapshot records.

    This function must be called after the VT integration is set up and the
    SmartPI monotonic clock is monkeypatched.

    Args:
        hass:              The HomeAssistant test instance.
        model:             Thermal model from ``sim.models.create_model()``.
        control_mode:      ``"pwm"`` (switch entity) or ``"linear"`` (number entity).
        heater_entity_id:  The switch or number entity VT writes to.
        temp_sensor_id:    Room temperature sensor entity ID.
        ext_sensor_id:     External temperature sensor entity ID.
        climate_entity_id: The VT climate entity to read state from.
        scenario:          Full scenario dict; reads ``scenario["simulation"]``.
        advance_clock:     Called each step with ``dt_s`` to advance the SimClock.

    Returns:
        List of snapshot dicts, one per ``record_every_seconds`` of simulated time.
    """
    sim_cfg: dict[str, Any] = scenario.get("simulation", {})

    # Build sensor pipeline and disturbance objects from scenario config.
    pipeline = SensorPipeline(scenario.get("sensor", {}), model.temperature)
    ext_profile, occupancy, weather = _build_disturbances(
        scenario.get("disturbances", {}) or {}
    )
    # Initial pre-loop sensor reading (dt_s=0 → lag stage returns initial_temp unchanged).
    sensor_temp: float = pipeline.step(model.temperature, dt_s=0.0, sim_time_s=0.0)

    dt_s = float(sim_cfg.get("step_seconds", 10.0))
    if dt_s <= 0:
        dt_s = 10.0

    duration_h = float(sim_cfg.get("duration_hours", 48.0))
    total_s = duration_h * 3600.0
    total_steps = int(total_s / dt_s)
    if total_steps <= 0:
        raise ValueError(
            f"Simulation produces zero steps (duration_hours={duration_h}, "
            f"step_seconds={dt_s})"
        )

    record_every_s = float(sim_cfg.get("record_every_seconds", 60.0))
    record_every_steps = max(1, int(record_every_s / dt_s))

    # Build sorted setpoint schedule: (trigger_elapsed_s, target_temp)
    schedule: list[tuple[float, float]] = sorted(
        (float(item["at_hour"]) * 3600.0, float(item["target_temp"]))
        for item in (sim_cfg.get("schedule") or [])
        if isinstance(item, dict) and "at_hour" in item and "target_temp" in item
    )
    sched_idx = 0

    # -----------------------------------------------------------------------
    # Initial thermostat state
    # -----------------------------------------------------------------------
    initial_hvac_mode = str(sim_cfg.get("initial_hvac_mode", "heat"))
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": climate_entity_id, "hvac_mode": initial_hvac_mode},
        blocking=True,
    )

    initial_preset = sim_cfg.get("initial_preset_mode")
    if initial_preset is not None:
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {"entity_id": climate_entity_id, "preset_mode": str(initial_preset)},
            blocking=True,
        )

    initial_temperature = sim_cfg.get("initial_temperature")
    if initial_temperature is not None:
        await hass.services.async_call(
            "climate",
            "set_temperature",
            {"entity_id": climate_entity_id, "temperature": float(initial_temperature)},
            blocking=True,
        )

    # VT may create long-lived background tasks; waiting for them can block forever.
    await asyncio.wait_for(hass.async_block_till_done(), timeout=60.0)

    # -----------------------------------------------------------------------
    # Simulation clock
    # -----------------------------------------------------------------------
    # Anchor at HA's notion of "now" (may be patched by the harness).
    sim_start = dt_util.utcnow().astimezone(timezone.utc).replace(second=0, microsecond=0)

    # Fire an initial tick to let VT process startup state before the loop.
    async_fire_time_changed(hass, sim_start)
    await asyncio.wait_for(hass.async_block_till_done(), timeout=60.0)

    # -----------------------------------------------------------------------
    # Power reader (selected once, called each step)
    # -----------------------------------------------------------------------
    if control_mode == "linear":
        def _read_power() -> float:
            return read_number_power(hass, heater_entity_id)
    else:
        def _read_power() -> float:
            return read_switch_power(hass, heater_entity_id)

    prev_power: float = _read_power()

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------
    records: list[dict[str, Any]] = []
    show_progress = os.getenv("VTSIM_PROGRESS", "").strip() not in ("", "0", "false", "False")
    last_progress_minute: int = -1
    wall_start = _REAL_MONOTONIC()
    _TIMEOUT_CHECK_INTERVAL = 1000  # check wall clock every N steps

    for step in range(total_steps):
        if step > 0 and step % _TIMEOUT_CHECK_INTERVAL == 0:
            elapsed_wall = _REAL_MONOTONIC() - wall_start
            if elapsed_wall > wall_clock_timeout_s:
                raise TimeoutError(
                    f"Simulation wall-clock timeout after {elapsed_wall:.0f}s "
                    f"at simulated step {step}/{total_steps} "
                    f"({step * dt_s / 3600:.1f}h of {duration_h}h)"
                )
        elapsed_s_start = step * dt_s
        elapsed_s_end = elapsed_s_start + dt_s

        # Apply any setpoint changes due at the start of this step.
        while sched_idx < len(schedule) and elapsed_s_start >= schedule[sched_idx][0]:
            target_temp = schedule[sched_idx][1]
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": climate_entity_id, "temperature": target_temp},
                blocking=True,
            )
            await asyncio.wait_for(hass.async_block_till_done(), timeout=30.0)
            sched_idx += 1

        # Apply disturbances to model attributes BEFORE stepping the physics.
        # This matches the coordinator tick order in heating_simulator/__init__.py
        # (disturbances set on model, then model.step() consumes them).
        if ext_profile.enabled:
            model.set_external_temperature(ext_profile.temperature_at(elapsed_s_start))
        model.internal_gain_watts = occupancy.gain_at(elapsed_s_start)
        model.weather_k_multiplier = weather.multiplier

        # Physics: advance thermal model by dt_s using the previously read
        # heater command.  The model now represents state at elapsed_s_end.
        model.set_power_fraction(prev_power)
        model.step(dt_s)

        # Apply the sensor pipeline — VTherm sees the degraded temperature,
        # not the raw physics ground truth.
        sensor_temp = pipeline.step(model.temperature, dt_s, elapsed_s_end)

        # Inject new temperatures — these are queued as HA state changes and
        # will be processed inside the async_block_till_done below.
        inject_temperature(hass, temp_sensor_id, sensor_temp)
        inject_temperature(
            hass, ext_sensor_id, model.external_temperature,
            friendly_name="External Temperature",
        )

        # Advance simulated monotonic/wall-clock so callbacks observe the new "now".
        advance_clock(dt_s)

        # Advance HA simulation time. This fires:
        #   • async_track_time_interval callbacks (VT main control, every cycle_min)
        #   • async_call_later callbacks (CycleScheduler ON→OFF transitions)
        #   • state_changed event for the injected temperature above
        current_time = sim_start + timedelta(seconds=elapsed_s_end)
        async_fire_time_changed(hass, current_time)
        await asyncio.wait_for(hass.async_block_till_done(), timeout=30.0)

        # Read heater command for the NEXT physics step.
        prev_power = _read_power()

        # Record snapshot.
        if step % record_every_steps == 0:
            snap = _capture_snapshot(
                hass, climate_entity_id, model, elapsed_s_end,
                sensor_temperature=sensor_temp,
            )
            # Record the actual switch/valve state just commanded, so the plot
            # shows what the thermal model will receive next step — not just VT's
            # planned duty cycle (power_percent), which stays constant for the
            # whole 15-min cycle even while the switch is in its OFF portion.
            snap["switch_state"] = prev_power
            records.append(snap)
            if on_record is not None:
                on_record(snap)

            if show_progress:
                elapsed_minute = int(elapsed_s_end // 60)
                if elapsed_minute != last_progress_minute:
                    last_progress_minute = elapsed_minute
                    _print_progress(step + 1, total_steps, elapsed_s_end, snap)

    if show_progress:
        print()  # end the progress line
    return records
