"""Parse HA Developer Tools entity state YAML into VTsim thermostat config."""
from __future__ import annotations
from typing import Any

import yaml

_MAPPINGS: list[tuple[tuple[str, ...], str, bool]] = [
    (("configuration", "cycle_min"),                    "cycle_min",                    False),
    (("configuration", "minimal_activation_delay_sec"), "minimal_activation_delay",     False),
    (("configuration", "minimal_deactivation_delay_sec"), "minimal_deactivation_delay", False),
    (("vtherm_over_switch", "function"),                "proportional_function",         False),
    (("preset_temperatures", "eco_temp"),               "eco_temp",                     False),
    (("preset_temperatures", "comfort_temp"),           "comfort_temp",                 False),
    (("preset_temperatures", "frost_temp"),             "frost_temp",                   False),
    (("preset_temperatures", "boost_temp"),             "boost_temp",                   False),
    (("min_temp",),                                     "min_temp",                     False),
    (("max_temp",),                                     "max_temp",                     False),
    (("smart_pi", "deadtime_heat_s"),                   "deadtime_heat_s",              True),
    (("smart_pi", "a"),                                 "smartpi_a",                    True),
    (("smart_pi", "b"),                                 "smartpi_b",                    True),
]

# HA state keys that are runtime/internal state or HA-only — not VTsim config params.
# These are silently dropped from the "unrecognised" list.
_HA_INTERNAL_KEYS: frozenset[str] = frozenset({
    # Runtime state
    "hvac_mode", "hvac_modes", "hvac_action",
    "current_temperature", "temperature", "ema_temp",
    "target_temp_step", "preset_mode", "preset_modes",
    "is_ready", "on_percent", "power_percent",
    # Detailed internal state blobs
    "specific_states", "current_state", "requested_state",
    # HA feature flags — not relevant to simulation
    "is_presence_configured", "is_power_configured", "is_motion_configured",
    "is_window_configured", "is_window_auto_configured",
    "is_safety_configured", "is_lock_configured",
    "is_heating_failure_detection_configured", "is_over_switch",
    # HA-only managers / metadata
    "power_manager", "safety_manager", "lock_manager",
    "timed_preset_manager", "friendly_name", "supported_features",
})

_IMPORTABLE_VT_KEYS = {
    "cycle_min", "minimal_activation_delay", "minimal_deactivation_delay",
    "proportional_function", "tpi_coef_int", "tpi_coef_ext",
    "smart_pi_deadband", "smart_pi_hysteresis_on", "smart_pi_hysteresis_off",
    "eco_temp", "comfort_temp", "frost_temp", "boost_temp",
    "min_temp", "max_temp",
}

_VT_DEFAULTS_SUBSET = {
    "cycle_min": 15,
    "minimal_activation_delay": 20,
    "minimal_deactivation_delay": 20,
    "proportional_function": "smart_pi",
    "tpi_coef_int": 0.3,
    "tpi_coef_ext": 0.01,
    "smart_pi_deadband": 0.05,
    "smart_pi_hysteresis_on": 0.30,
    "smart_pi_hysteresis_off": 0.50,
    "eco_temp": 17.5,
    "comfort_temp": 20.0,
    "frost_temp": 10.0,
    "boost_temp": 25.0,
    "min_temp": 7.0,
    "max_temp": 25.0,
}


def _get_nested(data: dict, path: tuple[str, ...]) -> Any:
    """Navigate nested dict by tuple path; return None if any key missing."""
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
        if cur is None:
            return None
    return cur


def parse_ha_state(yaml_text: str) -> dict[str, Any]:
    """Parse HA entity state YAML and categorize fields.

    Returns:
        dict with keys:
        - "mapped": list of (vtsim_key, value) tuples for recognized fields
        - "unrecognised": list of (key, value) tuples for unknown top-level keys
        - "missing": list of (key, default_value) tuples for expected keys not in YAML
    """
    data = yaml.safe_load(yaml_text) or {}

    mapped: list[tuple[str, Any]] = []
    mapped_vtsim_keys: set[str] = set()

    for ha_path, vtsim_key, _info in _MAPPINGS:
        val = _get_nested(data, ha_path)
        if val is not None:
            mapped.append((vtsim_key, val))
            mapped_vtsim_keys.add(vtsim_key)

    # Identify unrecognised top-level keys — skip known internal/HA-only keys and private keys
    known_top_level = {path[0] for path, _, _ in _MAPPINGS}
    unrecognised: list[tuple[str, Any]] = [
        (k, v) for k, v in data.items()
        if k not in known_top_level
        and k not in _HA_INTERNAL_KEYS
        and not k.startswith("_")
    ]

    # Identify missing importable keys and their defaults
    missing: list[tuple[str, Any]] = [
        (k, _VT_DEFAULTS_SUBSET.get(k))
        for k in sorted(_IMPORTABLE_VT_KEYS)
        if k not in mapped_vtsim_keys
    ]

    return {"mapped": mapped, "unrecognised": unrecognised, "missing": missing}
