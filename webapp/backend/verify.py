"""Parse HA recorder JSON exports into VTsim run configuration."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any


def _parse_ts(record: dict) -> datetime:
    ts = record.get("timestamp") or record.get("last_changed") or ""
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def _mean_or_none(values: list) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def parse_ha_log(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Parse a HA recorder JSON export into a VTsim VerifyParseResult.

    Args:
        records: list of HA state snapshots from Developer Tools → Download data.

    Returns:
        VerifyParseResult dict.
    """
    if not records:
        raise ValueError("Empty records list")

    records = sorted(records, key=_parse_ts)
    t0 = _parse_ts(records[0])
    t_last = _parse_ts(records[-1])
    duration_hours = (t_last - t0).total_seconds() / 3600.0

    entity_id = records[0].get("entity_id", "")

    # --- Starting conditions (first record) ---
    first_attrs = records[0].get("attributes") or {}
    first_specific = first_attrs.get("specific_states") or {}
    starting_conditions: dict[str, Any] = {
        "hvac_mode": records[0].get("state", "heat"),
        "preset_mode": first_attrs.get("preset_mode", "none"),
        "initial_temperature": first_attrs.get("current_temperature"),
        "ext_temperature": first_specific.get("ext_current_temperature"),
    }

    # --- VT config from first record attributes ---
    config = first_attrs.get("configuration") or {}
    over_switch = first_attrs.get("vtherm_over_switch") or {}
    preset_temps_src = first_attrs.get("preset_temperatures") or {}

    control: dict[str, Any] = {}
    if config.get("cycle_min") is not None:
        control["cycle_min"] = config["cycle_min"]
    if config.get("minimal_activation_delay_sec") is not None:
        control["minimal_activation_delay"] = config["minimal_activation_delay_sec"]
    if config.get("minimal_deactivation_delay_sec") is not None:
        control["minimal_deactivation_delay"] = config["minimal_deactivation_delay_sec"]
    if over_switch.get("function") is not None:
        control["proportional_function"] = over_switch["function"]

    temperatures: dict[str, float] = {}
    for key in ("eco_temp", "comfort_temp", "frost_temp", "boost_temp"):
        val = preset_temps_src.get(key)
        if val is not None:
            temperatures[key] = float(val)
    for key in ("min_temp", "max_temp"):
        val = first_attrs.get(key)
        if val is not None:
            temperatures[key] = float(val)

    preset = {"control": control, "temperatures": temperatures}

    # --- SmartPI seed: mean of a, b, deadtime_heat_s from settled tail (last 20%) ---
    cutoff_s = duration_hours * 3600 * 0.80
    settled_a, settled_b, settled_dt = [], [], []
    for rec in records:
        elapsed = (_parse_ts(rec) - t0).total_seconds()
        if elapsed < cutoff_s:
            continue
        sp = ((rec.get("attributes") or {}).get("specific_states") or {}).get("smart_pi") or {}
        if not isinstance(sp, dict):
            continue
        if sp.get("a") is not None:
            settled_a.append(sp["a"])
        if sp.get("b") is not None:
            settled_b.append(sp["b"])
        if sp.get("deadtime_heat_s") is not None:
            settled_dt.append(sp["deadtime_heat_s"])

    smartpi_seed: dict[str, Any] | None = None
    if settled_a or settled_b or settled_dt:
        smartpi_seed = {
            "a": _mean_or_none(settled_a),
            "b": _mean_or_none(settled_b),
            "deadtime_heat_s": _mean_or_none(settled_dt),
        }

    # --- Schedule: one entry per target_temp change ---
    schedule: list[dict[str, Any]] = []
    _sentinel = object()
    prev_target: Any = _sentinel
    for rec in records:
        target = (rec.get("attributes") or {}).get("temperature")
        if target is not None and target != prev_target:
            elapsed_h = (_parse_ts(rec) - t0).total_seconds() / 3600.0
            schedule.append({"at_hour": round(elapsed_h, 4), "target_temp": float(target)})
            prev_target = target

    # --- History: one HaHistoryPoint per record ---
    history: list[dict[str, Any]] = []
    for rec in records:
        attrs = rec.get("attributes") or {}
        elapsed_h = (_parse_ts(rec) - t0).total_seconds() / 3600.0
        on_pct = (attrs.get("on_percent")
                  if attrs.get("on_percent") is not None
                  else attrs.get("power_percent"))
        history.append({
            "elapsed_h": round(elapsed_h, 6),
            "temperature": attrs.get("current_temperature"),
            "target": attrs.get("temperature"),
            "on_percent": on_pct,
        })

    return {
        "entity_id": entity_id,
        "preset": preset,
        "starting_conditions": starting_conditions,
        "smartpi_seed": smartpi_seed,
        "duration_hours": round(duration_hours, 3),
        "heater_power_watts": None,
        "schedule": schedule,
        "history": history,
    }
