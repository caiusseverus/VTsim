from __future__ import annotations

import sys
import types
from types import SimpleNamespace

# Lightweight stubs so tests can import sim.virtual_entities without Home Assistant installed.
if "homeassistant" not in sys.modules:
    ha_pkg = types.ModuleType("homeassistant")
    ha_const = types.ModuleType("homeassistant.const")
    ha_const.ATTR_ENTITY_ID = "entity_id"
    ha_core = types.ModuleType("homeassistant.core")

    class _HA:  # pragma: no cover - type stub only
        pass

    class _ServiceCall:  # pragma: no cover - type stub only
        pass

    ha_core.HomeAssistant = _HA
    ha_core.ServiceCall = _ServiceCall

    sys.modules["homeassistant"] = ha_pkg
    sys.modules["homeassistant.const"] = ha_const
    sys.modules["homeassistant.core"] = ha_core

from sim.virtual_entities import inject_temperature, remove_temperature_entity


class _FakeStates:
    def __init__(self) -> None:
        self._store: dict[str, SimpleNamespace] = {}

    def async_set(self, entity_id: str, state: str, attrs: dict):
        self._store[entity_id] = SimpleNamespace(state=state, attributes=dict(attrs))

    def async_remove(self, entity_id: str):
        self._store.pop(entity_id, None)

    def get(self, entity_id: str):
        return self._store.get(entity_id)


class _FakeHass:
    def __init__(self) -> None:
        self.states = _FakeStates()


def test_inject_temperature_sets_sensor_state() -> None:
    hass = _FakeHass()

    inject_temperature(hass, "sensor.room_temp", 21.23456, friendly_name="Room Temp")

    state = hass.states.get("sensor.room_temp")
    assert state is not None
    assert state.state == "21.2346"
    assert state.attributes["friendly_name"] == "Room Temp"
    assert state.attributes["device_class"] == "temperature"


def test_temperature_sensor_removal_supports_external_and_flow_ids() -> None:
    hass = _FakeHass()

    inject_temperature(hass, "sensor.external_temp", 8.5)
    inject_temperature(hass, "sensor.flow_temp", 42.0)

    inject_temperature(hass, "sensor.external_temp", None)
    remove_temperature_entity(hass, "sensor.flow_temp")

    assert hass.states.get("sensor.external_temp") is None
    assert hass.states.get("sensor.flow_temp") is None
