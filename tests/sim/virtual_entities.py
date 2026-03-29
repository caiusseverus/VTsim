"""Virtual HA entities for the VT native simulation suite.

Registers minimal HA state and service handlers so Versatile Thermostat can
run in a bare hass fixture without the heating_simulator integration.

Supported control modes
-----------------------
pwm / switch
    VT calls switch.turn_on / switch.turn_off.
    Use async_setup_virtual_switch() + read_switch_power().

linear / valve
    VT calls number.set_value with a 0–100 percentage.
    Use async_setup_virtual_number() + read_number_power().

Temperature sensors are plain HA state entries — inject them with
inject_temperature() before VT setup and after each thermal model step.

Usage pattern
-------------
    # 1. Seed initial sensor states BEFORE setting up VT.
    inject_temperature(hass, TEMP_SENSOR_ID, model.temperature)
    inject_temperature(hass, EXT_SENSOR_ID, model.external_temperature,
                       friendly_name="External Temperature")

    # 2. Register virtual heater entity.
    await async_setup_virtual_switch(hass, SWITCH_ID)  # PWM mode
    # OR
    await async_setup_virtual_number(hass, NUMBER_ID)   # linear mode

    # 3. After each simulation step, read heater power.
    power = read_switch_power(hass, SWITCH_ID)
    # OR
    power = read_number_power(hass, NUMBER_ID)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall


# ---------------------------------------------------------------------------
# Attribute templates
# ---------------------------------------------------------------------------

_TEMP_ATTRS: dict[str, Any] = {
    "unit_of_measurement": "°C",
    "device_class": "temperature",
    "state_class": "measurement",
}

_SWITCH_ATTRS: dict[str, Any] = {
    "friendly_name": "VT Sim Heater Switch",
}

_NUMBER_ATTRS: dict[str, Any] = {
    "min": 0,
    "max": 100,
    "step": 1,
    "unit_of_measurement": "%",
    "friendly_name": "VT Sim Valve Position",
}

_VIRTUAL_SWITCH_DEBUG_KEY = "vtsim_virtual_switch_debug"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_entity_ids(call: ServiceCall) -> list[str]:
    """Return entity IDs from a service call, handling both data and target styles."""
    # Older-style: entity_id in service_data
    ids: Any = call.data.get(ATTR_ENTITY_ID)

    # Newer-style: entity_id in target (HA >= 2021.x)
    if ids is None and hasattr(call, "target") and call.target:
        ids = call.target.get(ATTR_ENTITY_ID)

    if ids is None:
        return []
    return [ids] if isinstance(ids, str) else list(ids)


def _ensure_switch_debug(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    store = hass.data.setdefault(_VIRTUAL_SWITCH_DEBUG_KEY, {})
    debug = store.get(entity_id)
    if not isinstance(debug, dict):
        debug = {
            "last_command": None,
            "last_command_iso": None,
            "last_state": None,
            "command_count": 0,
            "turn_on_count": 0,
            "turn_off_count": 0,
        }
        store[entity_id] = debug
    return debug


def _record_switch_command(
    hass: HomeAssistant,
    entity_id: str,
    *,
    command: str,
    resulting_state: str,
) -> None:
    debug = _ensure_switch_debug(hass, entity_id)
    now = datetime.now().astimezone()
    debug["last_command"] = command
    debug["last_command_iso"] = now.isoformat()
    debug["last_state"] = resulting_state
    debug["command_count"] = int(debug.get("command_count", 0)) + 1
    if command == "turn_on":
        debug["turn_on_count"] = int(debug.get("turn_on_count", 0)) + 1
    elif command == "turn_off":
        debug["turn_off_count"] = int(debug.get("turn_off_count", 0)) + 1


# ---------------------------------------------------------------------------
# Setup functions
# ---------------------------------------------------------------------------

async def async_setup_virtual_switch(
    hass: HomeAssistant,
    entity_id: str,
    initial_state: str = "off",
) -> None:
    """Register a virtual switch entity with turn_on / turn_off service handlers.

    Safe to call if switch services are already registered — the handlers are
    written to update any entity_id passed to them, so multiple virtual switches
    can share one registration call.

    Args:
        hass:          The HomeAssistant instance.
        entity_id:     Entity ID to seed (e.g. ``"switch.vt_sim_heater"``).
        initial_state: Initial switch state, ``"on"`` or ``"off"``.
    """
    hass.states.async_set(entity_id, initial_state, _SWITCH_ATTRS)
    _ensure_switch_debug(hass, entity_id)["last_state"] = initial_state

    async def _turn_on(call: ServiceCall) -> None:
        for eid in _extract_entity_ids(call):
            hass.states.async_set(eid, "on", _SWITCH_ATTRS)
            _record_switch_command(hass, eid, command="turn_on", resulting_state="on")

    async def _turn_off(call: ServiceCall) -> None:
        for eid in _extract_entity_ids(call):
            hass.states.async_set(eid, "off", _SWITCH_ATTRS)
            _record_switch_command(hass, eid, command="turn_off", resulting_state="off")

    hass.services.async_register("switch", "turn_on", _turn_on)
    hass.services.async_register("switch", "turn_off", _turn_off)


async def async_setup_virtual_number(
    hass: HomeAssistant,
    entity_id: str,
    initial_value: float = 0.0,
) -> None:
    """Register a virtual number entity with a set_value service handler.

    Used for linear / valve control mode where VT writes a 0–100 percentage.

    Args:
        hass:          The HomeAssistant instance.
        entity_id:     Entity ID to seed (e.g. ``"number.vt_sim_valve"``).
        initial_value: Initial value (0–100).
    """
    hass.states.async_set(entity_id, str(float(initial_value)), _NUMBER_ATTRS)

    async def _set_value(call: ServiceCall) -> None:
        value = float(call.data.get("value", 0.0))
        for eid in _extract_entity_ids(call):
            hass.states.async_set(eid, str(value), _NUMBER_ATTRS)

    hass.services.async_register("number", "set_value", _set_value)


# ---------------------------------------------------------------------------
# Temperature injection
# ---------------------------------------------------------------------------

def inject_temperature(
    hass: HomeAssistant,
    entity_id: str,
    temp: float,
    *,
    friendly_name: str | None = None,
) -> None:
    """Write a temperature value into HA state.

    Does NOT await — the state change event is queued and will be processed
    on the next ``async_block_till_done()`` call (which follows immediately
    after ``async_fire_time_changed`` in the engine loop).

    Args:
        hass:          The HomeAssistant instance.
        entity_id:     Sensor entity ID to update.
        temp:          Temperature in °C.
        friendly_name: Optional override for the friendly_name attribute.
    """
    attrs = dict(_TEMP_ATTRS)
    if friendly_name is not None:
        attrs["friendly_name"] = friendly_name
    hass.states.async_set(entity_id, f"{temp:.4f}", attrs)


# ---------------------------------------------------------------------------
# Power / state readers
# ---------------------------------------------------------------------------

def read_switch_power(hass: HomeAssistant, entity_id: str) -> float:
    """Return 1.0 if the virtual switch is on, 0.0 if off or missing."""
    state = hass.states.get(entity_id)
    if state is None:
        return 0.0
    return 1.0 if state.state == "on" else 0.0


def read_number_power(
    hass: HomeAssistant,
    entity_id: str,
    max_value: float = 100.0,
) -> float:
    """Return valve position as a power fraction in [0.0, 1.0].

    Args:
        hass:       The HomeAssistant instance.
        entity_id:  Number entity ID to read.
        max_value:  The value that corresponds to 100% power (default 100).
    """
    state = hass.states.get(entity_id)
    if state is None:
        return 0.0
    if max_value <= 0:
        return 0.0
    try:
        return max(0.0, min(1.0, float(state.state) / max_value))
    except (ValueError, TypeError):
        return 0.0


def read_switch_debug(hass: HomeAssistant, entity_id: str) -> dict[str, Any]:
    """Return harness-only debug info for a virtual switch."""
    debug = hass.data.get(_VIRTUAL_SWITCH_DEBUG_KEY, {}).get(entity_id, {})
    return dict(debug) if isinstance(debug, dict) else {}
