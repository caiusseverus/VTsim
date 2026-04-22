"""Parametrised VT native simulation tests.

Each YAML file in tests/scenarios/ becomes one test case.  The test:
  1. Creates a thermal model from the scenario's ``model:`` config.
  2. Seeds virtual HA sensor/switch entities (no heating_simulator integration).
  3. Patches the SmartPI monotonic clock to advance in lock-step with simulation.
  4. Loads only the Versatile Thermostat integration via MockConfigEntry.
  5. Runs the simulation loop (sim/engine.py).
  6. Computes metrics and saves a plot to results/<scenario_name>.png.
  7. Asserts steady-state error is within the scenario's declared limit.

Run:
    pytest -q tests/test_vt_scenarios.py -s
    pytest -q tests/test_vt_scenarios.py::test_vt_scenario[pwm_r2c2_standard] -s
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import csv as _csv_module
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.loader import DATA_CUSTOM_COMPONENTS
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Ensure project root is importable (custom_components.* and sim.*)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_PROJECT_ROOT), str(_PROJECT_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sim.analysis import compute_metrics, save_plot, write_ha_export_json, write_records_csv, write_summary_csv
from sim.engine import SimTimerScheduler, run_simulation
from sim.models import create_model
from sim.virtual_entities import (
    async_setup_virtual_number,
    async_setup_virtual_switch,
    inject_temperature,
    remove_temperature_entity,
)
from custom_components.versatile_thermostat.vtherm_api import VersatileThermostatAPI

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_vtsim_scenario_dir = os.getenv("VTSIM_SCENARIO_DIR", "")
_SCENARIO_DIR = Path(_vtsim_scenario_dir) if _vtsim_scenario_dir else Path(__file__).parent / "models"
_RESULTS_DIR = _PROJECT_ROOT / "results"

# Collect scenario files, excluding template (_template.yaml and other leading-underscore files).
SCENARIOS = [
    p.stem
    for p in sorted(_SCENARIO_DIR.glob("*.yaml"))
    if not p.stem.startswith("_")
]

_TEMP_SENSOR = "sensor.vt_sim_temperature"
_EXT_SENSOR = "sensor.vt_sim_ext_temperature"
_SWITCH_HEATER = "switch.vt_sim_heater"
_NUMBER_VALVE = "number.vt_sim_valve"

# ---------------------------------------------------------------------------
# SimClock — provides a controllable monotonic time source for SmartPI
# ---------------------------------------------------------------------------


@dataclass
class SimClock:
    now_s: float = field(default=0.0)
    anchor: Any = field(default=None)

    def monotonic(self) -> float:
        return self.now_s

    def utcnow(self):
        # Anchor must be set before dt_util.utcnow is monkeypatched.
        return self.anchor + timedelta(seconds=self.now_s)

    def time(self) -> float:
        return float(self.utcnow().timestamp())

    def advance(self, dt_s: float) -> None:
        self.now_s += max(0.0, dt_s)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_scenario(name: str) -> dict[str, Any]:
    path = _SCENARIO_DIR / f"{name}.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def _resolve_hass(hass_obj: Any) -> tuple[HomeAssistant, Any | None]:
    """Unwrap hass if the fixture returns an async generator rather than HA directly."""
    if hasattr(hass_obj, "states") and hasattr(hass_obj, "config_entries"):
        return hass_obj, None
    anext = getattr(hass_obj, "__anext__", None)
    if anext is None:
        raise TypeError(f"Unsupported hass fixture type: {type(hass_obj)!r}")
    _trace("await hass.__anext__()")
    resolved = await anext()
    return resolved, hass_obj


def _quiet_logs() -> None:
    for name in (
        "homeassistant",
        "custom_components",
        "pytest_homeassistant_custom_component",
        "asyncio",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)


def _trace_enabled() -> bool:
    """Enable stage tracing with VTSIM_TRACE=1."""
    return os.getenv("VTSIM_TRACE", "").strip() not in ("", "0", "false", "False")


def _trace(msg: str) -> None:
    if _trace_enabled():
        print(f"[vtsim] {msg}", flush=True)


def _prepare_custom_components(hass: HomeAssistant) -> None:
    """Symlink (or copy) custom_components/versatile_thermostat into HA's config dir."""
    _vt_dir = os.getenv("VTSIM_VT_DIR", "")
    src = Path(_vt_dir) if _vt_dir else _PROJECT_ROOT / "custom_components" / "versatile_thermostat"
    dst_root = Path(hass.config.config_dir) / "custom_components"
    dst_root.mkdir(parents=True, exist_ok=True)
    dst = dst_root / "versatile_thermostat"
    if not src.exists():
        pytest.fail(f"Missing integration source: {src}")
    if dst.exists() or dst.is_symlink():
        return
    try:
        os.symlink(src, dst, target_is_directory=True)
    except OSError:
        shutil.copytree(src, dst, dirs_exist_ok=True)


def _install_control_debug_instrumentation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instrument SmartPI control entrypoints from the harness only.

    This keeps VTsim observational: no edits to the tested VTherm source tree.
    Stats are attached to each thermostat instance and injected into
    ``attributes.specific_states.control_debug`` by a wrapped
    ``update_custom_attributes()`` call.
    """
    from custom_components.versatile_thermostat.base_thermostat import BaseThermostat
    from custom_components.versatile_thermostat.prop_handler_smartpi import SmartPIHandler

    def _ensure_debug_state(thermostat: Any) -> dict[str, Any]:
        stats = getattr(thermostat, "_vtsim_control_debug_stats", None)
        if not isinstance(stats, dict):
            stats = {
                "total_calls": 0,
                "calls_by_source": {},
                "last_source": None,
                "last_iso": None,
                "same_timestamp_calls": 0,
                "max_same_timestamp_calls": 0,
                "last_force": False,
            }
            setattr(thermostat, "_vtsim_control_debug_stats", stats)
        if not hasattr(thermostat, "_vtsim_pending_control_debug_source"):
            setattr(thermostat, "_vtsim_pending_control_debug_source", None)
        if not hasattr(thermostat, "_vtsim_active_control_debug_source"):
            setattr(thermostat, "_vtsim_active_control_debug_source", None)
        return stats

    def _set_source(thermostat: Any, source: str) -> None:
        _ensure_debug_state(thermostat)
        setattr(thermostat, "_vtsim_pending_control_debug_source", source)

    def _consume_source(thermostat: Any, fallback: str) -> str:
        _ensure_debug_state(thermostat)
        source = getattr(thermostat, "_vtsim_pending_control_debug_source", None) or fallback
        setattr(thermostat, "_vtsim_pending_control_debug_source", None)
        return str(source)

    def _record_entry(thermostat: Any, source: str, *, force: bool = False) -> None:
        stats = _ensure_debug_state(thermostat)
        now_iso = thermostat.now.isoformat()

        stats["total_calls"] = int(stats.get("total_calls", 0)) + 1
        by_source = stats.get("calls_by_source")
        if not isinstance(by_source, dict):
            by_source = {}
            stats["calls_by_source"] = by_source
        by_source[source] = int(by_source.get(source, 0)) + 1

        if stats.get("last_iso") == now_iso:
            same_ts_calls = int(stats.get("same_timestamp_calls", 0)) + 1
        else:
            same_ts_calls = 1

        stats["same_timestamp_calls"] = same_ts_calls
        stats["max_same_timestamp_calls"] = max(
            int(stats.get("max_same_timestamp_calls", 0)),
            same_ts_calls,
        )
        stats["last_iso"] = now_iso
        stats["last_source"] = source
        stats["last_force"] = bool(force)

    orig_update_custom_attributes = BaseThermostat.update_custom_attributes

    def _wrapped_update_custom_attributes(self: Any) -> None:
        orig_update_custom_attributes(self)
        stats = _ensure_debug_state(self)
        specific = self._attr_extra_state_attributes.get("specific_states")
        if isinstance(specific, dict):
            specific["control_debug"] = {
                "total_calls": stats["total_calls"],
                "calls_by_source": dict(stats["calls_by_source"]),
                "last_source": stats["last_source"],
                "last_iso": stats["last_iso"],
                "same_timestamp_calls": stats["same_timestamp_calls"],
                "max_same_timestamp_calls": stats["max_same_timestamp_calls"],
                "last_force": stats["last_force"],
            }
            cycle_debug = getattr(self, "_vtsim_cycle_debug", None)
            if isinstance(cycle_debug, dict):
                specific["cycle_debug"] = dict(cycle_debug)

    monkeypatch.setattr(BaseThermostat, "update_custom_attributes", _wrapped_update_custom_attributes)

    orig_async_control_heating = BaseThermostat.async_control_heating

    async def _wrapped_async_control_heating(self: Any, timestamp=None, force=False):
        if timestamp and getattr(self, "_vtsim_pending_control_debug_source", None) is None:
            _set_source(self, "cycle_timer")
        return await orig_async_control_heating(self, timestamp=timestamp, force=force)

    monkeypatch.setattr(BaseThermostat, "async_control_heating", _wrapped_async_control_heating)

    orig_temp_changed = BaseThermostat._async_temperature_changed

    async def _wrapped_temp_changed(self: Any, event):
        _set_source(self, "temp_sensor")
        return await orig_temp_changed(self, event)

    monkeypatch.setattr(BaseThermostat, "_async_temperature_changed", _wrapped_temp_changed)

    orig_ext_temp_changed = BaseThermostat._async_ext_temperature_changed

    async def _wrapped_ext_temp_changed(self: Any, event):
        _set_source(self, "ext_temp_sensor")
        return await orig_ext_temp_changed(self, event)

    monkeypatch.setattr(BaseThermostat, "_async_ext_temperature_changed", _wrapped_ext_temp_changed)

    orig_control_heating = SmartPIHandler.control_heating

    async def _wrapped_control_heating(self: Any, timestamp=None, force=False):
        thermostat = self._thermostat
        source = _consume_source(thermostat, "direct")
        setattr(thermostat, "_vtsim_active_control_debug_source", source)
        _record_entry(thermostat, source, force=force)
        try:
            return await orig_control_heating(self, timestamp=timestamp, force=force)
        finally:
            setattr(thermostat, "_vtsim_active_control_debug_source", None)

    monkeypatch.setattr(SmartPIHandler, "control_heating", _wrapped_control_heating)

    orig_silent_heartbeat = SmartPIHandler._async_control_heating_silently

    async def _wrapped_silent_heartbeat(self: Any):
        _set_source(self._thermostat, "smartpi_heartbeat")
        return await orig_silent_heartbeat(self)

    monkeypatch.setattr(SmartPIHandler, "_async_control_heating_silently", _wrapped_silent_heartbeat)


def _install_cycle_debug_instrumentation(
    monkeypatch: pytest.MonkeyPatch,
    clock: SimClock,
) -> None:
    """Instrument scheduler cycle phase from the harness only."""
    try:
        from custom_components.versatile_thermostat.cycle_scheduler import (
            CycleScheduler,
            calculate_cycle_times,
        )
    except ModuleNotFoundError:
        return

    def _ensure_cycle_debug(thermostat: Any) -> dict[str, Any]:
        debug = getattr(thermostat, "_vtsim_cycle_debug", None)
        if not isinstance(debug, dict):
            debug = {
                "cycle_start_iso": None,
                "cycle_duration_sec": None,
                "cycle_elapsed_sec": None,
                "last_on_time_sec": None,
                "last_off_time_sec": None,
                "last_realized_on_percent": None,
                "last_tick_is_initial": None,
                "last_tick_current_t": None,
                "last_tick_next_global_tick": None,
                "is_within_pwm_on_window": None,
                "last_cycle_restart_reason": None,
                "restart_count": 0,
                "restart_count_by_source": {},
                "last_restart_source": None,
                "suppressed_restart_count": 0,
                "suppressed_restart_count_by_source": {},
                "last_suppressed_restart_source": None,
            }
            setattr(thermostat, "_vtsim_cycle_debug", debug)
        return debug

    def _update_cycle_phase(scheduler: Any, *, is_initial: bool) -> None:
        thermostat = scheduler._thermostat
        debug = _ensure_cycle_debug(thermostat)
        current_t = 0.0 if is_initial else max(0.0, clock.time() - float(scheduler._cycle_start_time or 0.0))
        debug["cycle_elapsed_sec"] = current_t
        debug["last_tick_is_initial"] = bool(is_initial)
        debug["last_tick_current_t"] = current_t
        if scheduler._cycle_duration_sec:
            debug["cycle_duration_sec"] = float(scheduler._cycle_duration_sec)
        on_time = scheduler._current_on_time_sec
        debug["is_within_pwm_on_window"] = bool(on_time and current_t < float(on_time))

    orig_start_cycle_switch = CycleScheduler._start_cycle_switch

    async def _wrapped_start_cycle_switch(self: Any, hvac_mode: Any, on_time_sec: float, off_time_sec: float, on_percent: float):
        thermostat = self._thermostat
        debug = _ensure_cycle_debug(thermostat)
        restart_source = (
            getattr(thermostat, "_vtsim_active_control_debug_source", None)
            or getattr(thermostat, "_vtsim_pending_control_debug_source", None)
            or "direct"
        )
        by_source = debug.get("restart_count_by_source")
        if not isinstance(by_source, dict):
            by_source = {}
            debug["restart_count_by_source"] = by_source
        debug["restart_count"] = int(debug.get("restart_count", 0)) + 1
        by_source[restart_source] = int(by_source.get(restart_source, 0)) + 1
        debug["last_restart_source"] = str(restart_source)
        debug["cycle_start_iso"] = clock.utcnow().isoformat()
        debug["cycle_duration_sec"] = float(self._cycle_duration_sec)
        debug["cycle_elapsed_sec"] = 0.0
        debug["last_on_time_sec"] = float(on_time_sec)
        debug["last_off_time_sec"] = float(off_time_sec)
        debug["last_realized_on_percent"] = float(on_percent)
        if hvac_mode is not None:
            debug["last_hvac_mode"] = str(hvac_mode)
        if hvac_mode is not None and str(hvac_mode).lower().endswith("off"):
            debug["last_cycle_restart_reason"] = "hvac_off"
        elif on_time_sec <= 0:
            debug["last_cycle_restart_reason"] = "zero_on_time"
        elif on_time_sec >= self._cycle_duration_sec:
            debug["last_cycle_restart_reason"] = "full_on_cycle"
        else:
            debug["last_cycle_restart_reason"] = "pwm_cycle"
        return await orig_start_cycle_switch(self, hvac_mode, on_time_sec, off_time_sec, on_percent)

    monkeypatch.setattr(CycleScheduler, "_start_cycle_switch", _wrapped_start_cycle_switch)

    orig_tick = CycleScheduler._tick

    async def _wrapped_tick(self: Any, _now=None, _is_initial: bool = False):
        _update_cycle_phase(self, is_initial=_is_initial)
        result = await orig_tick(self, _now=_now, _is_initial=_is_initial)
        debug = _ensure_cycle_debug(self._thermostat)
        next_tick = None
        if getattr(self, "_tick_unsub", None) is not None and self._cycle_start_time:
            elapsed = max(0.0, clock.time() - float(self._cycle_start_time))
            next_tick = max(0.0, float(self._cycle_duration_sec) - elapsed)
        debug["last_tick_next_global_tick"] = next_tick
        _update_cycle_phase(self, is_initial=False)
        return result

    monkeypatch.setattr(CycleScheduler, "_tick", _wrapped_tick)

    orig_on_master_cycle_end = CycleScheduler._on_master_cycle_end

    async def _wrapped_on_master_cycle_end(self: Any, _now):
        _ensure_cycle_debug(self._thermostat)["last_cycle_restart_reason"] = "master_cycle_end"
        return await orig_on_master_cycle_end(self, _now)

    monkeypatch.setattr(CycleScheduler, "_on_master_cycle_end", _wrapped_on_master_cycle_end)


# ---------------------------------------------------------------------------
# VT config entry construction
# ---------------------------------------------------------------------------

# All required VT config fields with sensible simulation defaults.
# The scenario's thermostat: section overrides any of these.
_VT_DEFAULTS: dict[str, Any] = {
    "thermostat_type": "thermostat_over_switch",
    "proportional_function": "smart_pi",
    "tpi_coef_int": 0.3,
    "tpi_coef_ext": 0.01,
    "tpi_threshold_low": 0.0,
    "tpi_threshold_high": 1.0,
    "use_smart_pi_central_config": False,
    "smart_pi_deadband": 0.05,
    "smart_pi_hysteresis_on": 0.30,
    "smart_pi_hysteresis_off": 0.50,
    "smart_pi_use_setpoint_filter": True,
    "smart_pi_debug": True,
    "smart_pi_aggregation_mode": "weighted_median",
    "cycle_min": 15,
    "minimal_activation_delay": 0,
    "minimal_deactivation_delay": 0,
    "heater_keep_alive": 0,
    "inverse_switch_command": False,
    "ac_mode": False,
    "step_temperature": 0.1,
    "min_temp": 7.0,
    "max_temp": 25.0,
    "temp_min": 7.0,
    "temp_max": 25.0,
    "target_temp": 20.0,
    "frost_temp": 10.0,
    "eco_temp": 17.5,
    "comfort_temp": 20.0,
    "boost_temp": 25.0,
    "frost_away_temp": 10.0,
    "eco_away_temp": 17.0,
    "comfort_away_temp": 18.0,
    "boost_away_temp": 22.0,
    "use_window_feature": False,
    "use_motion_feature": False,
    "use_presence_feature": False,
    "use_power_feature": False,
    "use_central_boiler_feature": False,
    "use_auto_start_stop_feature": False,
    "window_sensor_entity_id": "",
    "motion_sensor_entity_id": "",
    "presence_sensor_entity_id": "",
    "power_sensor_entity_id": "",
    "max_power_sensor_entity_id": "",
    "auto_regulation_mode": "auto_regulation_none",
    "auto_regulation_dtemp": 0.0,
    "auto_regulation_periode_min": 0,  # 0 = no filter; valve recalculate must run every temp change
    "auto_regulation_use_device_temp": False,
    "safety_delay_min": 60,
    "safety_min_on_percent": 0.5,
    "safety_default_on_percent": 0.1,
    "lock_users": True,
    "lock_automations": True,
    "lock_code": False,
    "opening_degree_entity_ids": [],
    "closing_degree_entity_ids": [],
    "offset_calibration_entity_ids": [],
    "sync_entity_ids": [],
    "auto_tpi_mode": False,
    "auto_tpi_learning_type": "discovery",
    "auto_tpi_enable_advanced_settings": False,
    "heater_heating_time": 3600,
    "heater_cooling_time": 3600,
    "auto_tpi_calculation_method": "average",
    "auto_tpi_ema_alpha": 0.2,
    "auto_tpi_avg_initial_weight": 0.7,
    "auto_tpi_aggressiveness": 1.0,
    "auto_tpi_ema_decay_rate": 0.99,
    "use_heating_failure_detection_feature": False,
    "use_heating_failure_detection_central_config": False,
    "heating_failure_threshold": 0.1,
    "cooling_failure_threshold": 0.1,
    "heating_failure_detection_delay": 60,
    "temperature_change_tolerance": 0.1,
    "failure_detection_enable_template": "",
    "use_central_mode": False,
    "used_by_controls_central_boiler": False,
    "central_boiler_activation_service": "",
    "central_boiler_deactivation_service": "",
    "central_boiler_activation_delay_sec": 0,
    "auto_start_stop_level": "auto_start_stop_none",
}


def _build_vt_config(
    scenario_thermostat: dict[str, Any],
    temp_sensor_id: str,
    ext_sensor_id: str,
    heater_id: str,
    scenario_name: str,
    control_mode: str = "pwm",
) -> dict[str, Any]:
    """Merge scenario thermostat settings over defaults and inject entity IDs."""
    config = dict(_VT_DEFAULTS)
    # Derive thermostat_type from control_mode unless scenario explicitly sets it.
    if control_mode == "linear" and "thermostat_type" not in scenario_thermostat:
        config["thermostat_type"] = "thermostat_over_valve"
    config.update(scenario_thermostat)
    config["name"] = scenario_name
    config["temperature_sensor_entity_id"] = temp_sensor_id
    config["external_temperature_sensor_entity_id"] = ext_sensor_id
    config["heater_entity_id"] = heater_id
    config["underlying_entity_ids"] = [heater_id]
    return config


async def _setup_vt(hass: HomeAssistant, config_data: dict[str, Any]) -> MockConfigEntry:
    """Create and load the VT config entry; fail fast on setup error."""
    entry_kwargs: dict[str, Any] = {
        "domain": "versatile_thermostat",
        "title": config_data.get("name", "VT Simulation"),
        "data": config_data,
        "unique_id": "vtsim-scenario",
        "version": 2,
    }
    if "minor_version" in inspect.signature(MockConfigEntry).parameters:
        entry_kwargs["minor_version"] = 3

    entry = MockConfigEntry(**entry_kwargs)
    _trace("vt: add_to_hass")
    entry.add_to_hass(hass)

    timeout_s = float(os.getenv("VTSIM_SETUP_TIMEOUT_S", "60"))
    _trace(f"vt: async_setup start timeout={timeout_s}s")
    ok = await asyncio.wait_for(
        hass.config_entries.async_setup(entry.entry_id),
        timeout=timeout_s,
    )
    _trace(f"vt: async_setup returned ok={ok}")
    _trace("vt: async_block_till_done start")
    await asyncio.wait_for(hass.async_block_till_done(), timeout=60.0)
    _trace("vt: async_block_till_done done")

    current = hass.config_entries.async_get_entry(entry.entry_id)
    if not ok or (current and current.state is ConfigEntryState.MIGRATION_ERROR):
        pytest.fail(
            "VT config entry failed to load. "
            "Check HA/VT version compatibility and required config fields."
        )
    return entry


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario_name", SCENARIOS)
async def test_vt_scenario(
    hass: HomeAssistant,
    scenario_name: str,
    monkeypatch: pytest.MonkeyPatch,
    metrics_accumulator: list,
) -> None:
    _quiet_logs()
    _trace(f"begin scenario={scenario_name}")
    _trace(f"hass param type={type(hass)!r}")
    hass, hass_gen = await _resolve_hass(hass)
    _trace("resolved hass fixture")
    _trace(f"running loop={type(asyncio.get_running_loop()).__name__}")
    _trace(f"loop policy={type(asyncio.get_event_loop_policy()).__name__}")
    scenario = _load_scenario(scenario_name)
    sim_cfg: dict[str, Any] = scenario.get("simulation", {})
    model_cfg: dict[str, Any] = scenario.get("model", {})
    vt_cfg: dict[str, Any] = scenario.get("thermostat", {})

    control_mode = str(model_cfg.get("control_mode", "pwm")).lower()
    heater_id = _NUMBER_VALVE if control_mode == "linear" else _SWITCH_HEATER

    # ------------------------------------------------------------------
    # 1. Thermal model
    # ------------------------------------------------------------------
    _trace("create model")
    model = create_model(model_cfg)

    # ------------------------------------------------------------------
    # 2. Seed virtual sensor states BEFORE VT setup.
    #    VT reads these in async_added_to_hass; they must already exist.
    # ------------------------------------------------------------------
    _trace("seed sensors")
    inject_temperature(hass, _TEMP_SENSOR, model.temperature)
    inject_temperature(hass, _EXT_SENSOR, model.external_temperature,
                       friendly_name="External Temperature")

    # ------------------------------------------------------------------
    # 3. Register virtual heater entity
    # ------------------------------------------------------------------
    _trace(f"setup virtual heater control_mode={control_mode}")
    if control_mode == "linear":
        await async_setup_virtual_number(hass, heater_id)
    else:
        await async_setup_virtual_switch(hass, heater_id)

    # ------------------------------------------------------------------
    # 4. Prepare HA custom-component discovery
    # ------------------------------------------------------------------
    _trace("prepare custom_components discovery")
    _prepare_custom_components(hass)
    hass.data.pop(DATA_CUSTOM_COMPONENTS, None)
    _install_control_debug_instrumentation(monkeypatch)

    # Reset VT API singleton so stale hass from a prior test is not reused.
    VersatileThermostatAPI._hass = None

    # ------------------------------------------------------------------
    # 5. Patch SmartPI monotonic clock BEFORE VT creates its SmartPI instance
    # ------------------------------------------------------------------
    _trace("patch SmartPI monotonic clock")
    clock = SimClock(anchor=dt_util.utcnow().replace(microsecond=0))
    timer_scheduler = SimTimerScheduler(now_provider=clock.utcnow)
    monkeypatch.setattr(
        "custom_components.versatile_thermostat.prop_algo_smartpi.time.monotonic",
        clock.monotonic,
    )
    _install_cycle_debug_instrumentation(monkeypatch, clock)

    # ------------------------------------------------------------------
    # 5b. Patch CycleScheduler to use simulated time.
    #
    # CycleScheduler uses two real-wall-clock mechanisms that break in fast
    # simulation:
    #   1. time.time() for _cycle_start_time and current_t — in fast simulation
    #      current_t is always ~0 ms, so compute_target_state sees the switch
    #      permanently at the start of its cycle.
    #   2. async_call_later (loop.call_at with real monotonic) — the ON/OFF tick
    #      and cycle-end repeat callbacks never fire because real seconds never
    #      accumulate during a fast simulated run.
    #
    # Fix: route time.time() through the SimClock so cycle position arithmetic
    # is correct, and replace async_call_later with a version that fires on
    # EVENT_TIME_CHANGED (which VTsim already drives via async_fire_time_changed).
    # ------------------------------------------------------------------
    import time as _time_mod
    monkeypatch.setattr(_time_mod, "time", clock.time)

    def _sim_async_track_time_interval(hass_obj, action, interval):
        return timer_scheduler.schedule_interval(hass_obj, action, interval)

    def _sim_async_call_later(hass_obj, delay, action):
        return timer_scheduler.schedule(hass_obj, delay, action)

    import homeassistant.helpers.event as ha_event
    monkeypatch.setattr(ha_event, "async_track_time_interval", _sim_async_track_time_interval)

    # cycle_scheduler was added in a later VT version — skip patching on older builds
    try:
        import custom_components.versatile_thermostat.cycle_scheduler  # noqa: F401
        monkeypatch.setattr(
            "custom_components.versatile_thermostat.cycle_scheduler.async_call_later",
            _sim_async_call_later,
        )
    except ModuleNotFoundError:
        pass

    for module_name in (
        "custom_components.versatile_thermostat.thermostat_switch",
        "custom_components.versatile_thermostat.thermostat_valve",
        "custom_components.versatile_thermostat.thermostat_climate",
        "custom_components.versatile_thermostat.prop_handler_smartpi",
        "custom_components.versatile_thermostat.keep_alive",
        "custom_components.versatile_thermostat.feature_central_boiler_manager",
    ):
        try:
            module = __import__(module_name, fromlist=["async_track_time_interval"])
            monkeypatch.setattr(module, "async_track_time_interval", _sim_async_track_time_interval)
        except ModuleNotFoundError:
            continue

    # ------------------------------------------------------------------
    # 5c. Limit VT platform forwarding to what the simulation actually needs.
    #     Forwarding all platforms can hang under some HA test/plugin combos.
    # ------------------------------------------------------------------
    # climate must come before number — VT's number entities self-register into
    # the VTherm API after the climate entity is created.  Without number, all
    # preset temperatures fall back to min_temp and VT never commands any heat.
    _trace("limit VT PLATFORMS to climate + number")
    import custom_components.versatile_thermostat as vt_mod
    monkeypatch.setattr(vt_mod, "PLATFORMS", ["climate", "number"])

    # ------------------------------------------------------------------
    # 6. Load VT integration
    # ------------------------------------------------------------------
    _trace("setup VT config entry")
    vt_config = _build_vt_config(vt_cfg, _TEMP_SENSOR, _EXT_SENSOR, heater_id, scenario_name, control_mode=control_mode)
    entry = await _setup_vt(hass, vt_config)
    _trace("VT setup complete")

    # ------------------------------------------------------------------
    # 6b. Re-register virtual heater services.
    #     VT's dependency loading causes HA to load the switch/number
    #     component, which replaces our custom service handlers with
    #     entity-service routing.  Since our virtual entities are not in
    #     the entity registry, those routed calls do nothing.
    #     Re-registering AFTER VT setup restores our handlers.
    # ------------------------------------------------------------------
    _trace("re-register virtual heater services")
    if control_mode == "linear":
        await async_setup_virtual_number(hass, heater_id)
    else:
        await async_setup_virtual_switch(hass, heater_id)

    # ------------------------------------------------------------------
    # 7. Discover the climate entity VT registered
    # ------------------------------------------------------------------
    _trace("discover climate entity")
    climate_entity = next(
        (s.entity_id for s in hass.states.async_all("climate")),
        None,
    )
    if climate_entity is None:
        await hass.config_entries.async_unload(entry.entry_id)
        pytest.fail("VT did not register a climate entity after setup.")

    # ------------------------------------------------------------------
    # 8. Run simulation + analysis
    # ------------------------------------------------------------------
    try:
        # ------------------------------------------------------------------
        # 8a. Patch time + scheduling for accelerated simulation.
        #     Do this after VT setup so HA initialization runs on real time.
        # ------------------------------------------------------------------
        monkeypatch.setattr(time, "time", clock.time)
        monkeypatch.setattr(dt_util, "utcnow", clock.utcnow)

        def _async_track_time_interval_sim(hass_obj, action, interval):
            return timer_scheduler.schedule_interval(hass_obj, action, interval)

        def _async_call_later_sim(hass_obj, delay, action):
            return timer_scheduler.schedule(hass_obj, delay, action)

        monkeypatch.setattr(ha_event, "async_track_time_interval", _async_track_time_interval_sim)
        monkeypatch.setattr(ha_event, "async_call_later", _async_call_later_sim)

        # cycle_scheduler was added in a later VT version — skip patching on older builds
        try:
            import custom_components.versatile_thermostat.cycle_scheduler as vt_cycle
            monkeypatch.setattr(vt_cycle, "async_call_later", _async_call_later_sim)
        except ModuleNotFoundError:
            pass

        for module_name in (
            "custom_components.versatile_thermostat.thermostat_switch",
            "custom_components.versatile_thermostat.thermostat_valve",
            "custom_components.versatile_thermostat.thermostat_climate",
            "custom_components.versatile_thermostat.prop_handler_smartpi",
            "custom_components.versatile_thermostat.keep_alive",
            "custom_components.versatile_thermostat.feature_central_boiler_manager",
        ):
            try:
                module = __import__(module_name, fromlist=["async_track_time_interval"])
                monkeypatch.setattr(module, "async_track_time_interval", _async_track_time_interval_sim)
            except ModuleNotFoundError:
                continue

        # Set up live CSV streaming for web backend.
        _live_csv_path_str = os.getenv("VTSIM_LIVE_CSV", "")
        _on_record = None
        if _live_csv_path_str:
            _live_csv_path = Path(_live_csv_path_str)
            _live_csv_path.parent.mkdir(parents=True, exist_ok=True)
            _live_csv_headers_written = [False]

            def _on_record(record: dict) -> None:
                with _live_csv_path.open("a", newline="", encoding="utf-8") as _f:
                    _w = _csv_module.DictWriter(_f, fieldnames=list(record.keys()))
                    if not _live_csv_headers_written[0]:
                        _w.writeheader()
                        _live_csv_headers_written[0] = True
                    _w.writerow({k: ("" if v is None else v) for k, v in record.items()})

        _trace("run simulation")
        records, sim_start = await run_simulation(
            hass,
            model=model,
            control_mode=control_mode,
            heater_entity_id=heater_id,
            temp_sensor_id=_TEMP_SENSOR,
            ext_sensor_id=_EXT_SENSOR,
            climate_entity_id=climate_entity,
            scenario=scenario,
            advance_clock=clock.advance,
            on_record=_on_record,
            timer_scheduler=timer_scheduler,
        )
        _trace(f"simulation done records={len(records)}")

        metrics = compute_metrics(records, scenario)
        metrics["scenario_name"] = scenario_name
        metrics_accumulator.append(metrics)

        _output_dir_override = os.getenv("VTSIM_OUTPUT_DIR", "")
        _output_dir = Path(_output_dir_override) if _output_dir_override else _RESULTS_DIR
        _output_dir.mkdir(parents=True, exist_ok=True)
        output_path = _output_dir / f"{scenario_name}.png"
        save_plot(records, scenario, output_path, metrics)
        records_csv_path = _output_dir / f"{scenario_name}_records.csv"
        write_records_csv(records, records_csv_path)
        ha_export_path = _output_dir / f"{scenario_name}_ha_export.json"
        write_ha_export_json(records, climate_entity, ha_export_path, sim_start)
        # Write per-run metrics JSON for web backend consumption.
        if _output_dir_override:
            metrics_path = _output_dir / "metrics.json"
            metrics_path.write_text(json.dumps(metrics, default=str))

        print(
            f"\n  [{scenario_name}]  "
            f"SSE={metrics['steady_state_error_c']}°C  "
            f"overshoot={metrics['max_overshoot_c']:+.3f}°C  "
            f"settle={metrics['settling_time_h']}h  "
            f"energy={metrics['energy_kwh']:.3f} kWh  "
            f"cycles={metrics['switch_cycles']}"
        )

        # ------------------------------------------------------------------
        # 9. Assertions
        # ------------------------------------------------------------------
        assert records, "Simulation produced no records."
        assert output_path.exists(), f"Plot not written: {output_path}"

        max_err = sim_cfg.get("max_acceptable_steady_state_error_c")
        sse = metrics.get("steady_state_error_c")
        if max_err is not None and sse is not None:
            assert sse <= float(max_err), (
                f"Steady-state error {sse:.3f}°C exceeds limit {float(max_err)}°C"
            )

        max_energy = sim_cfg.get("max_acceptable_energy_kwh")
        if max_energy is not None and metrics.get("energy_kwh") is not None:
            assert float(metrics["energy_kwh"]) <= float(max_energy), (
                f"Energy {metrics['energy_kwh']:.3f} kWh exceeds limit {float(max_energy):.3f} kWh"
            )

        max_overshoot = sim_cfg.get("max_acceptable_overshoot_c")
        if max_overshoot is not None and metrics.get("max_overshoot_c") is not None:
            assert float(metrics["max_overshoot_c"]) <= float(max_overshoot), (
                f"Overshoot {metrics['max_overshoot_c']:+.3f}°C exceeds limit {float(max_overshoot):+.3f}°C"
            )

        max_cycles = sim_cfg.get("max_acceptable_switch_cycles")
        if max_cycles is not None and metrics.get("switch_cycles") is not None:
            assert int(metrics["switch_cycles"]) <= int(max_cycles), (
                f"Switch cycles {metrics['switch_cycles']} exceeds limit {int(max_cycles)}"
            )

        max_settle = sim_cfg.get("max_acceptable_settling_time_h")
        if max_settle is not None:
            st = metrics.get("settling_time_h")
            assert st is not None, "Settling time is None but a limit was provided."
            assert float(st) <= float(max_settle), (
                f"Settling time {float(st):.2f}h exceeds limit {float(max_settle):.2f}h"
            )

    finally:
        await hass.config_entries.async_unload(entry.entry_id)
        remove_temperature_entity(hass, _TEMP_SENSOR)
        remove_temperature_entity(hass, _EXT_SENSOR)
        await asyncio.wait_for(hass.async_block_till_done(), timeout=30.0)
        # Clear VT API singleton so the next test starts clean.
        VersatileThermostatAPI._hass = None
        if hass_gen is not None:
            await hass_gen.aclose()
