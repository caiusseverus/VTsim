#!/usr/bin/env python3
"""Generate a VTsim scenario YAML from a HA climate entity history export.

Usage:
    uv run python tools/scenario_from_export.py <ha_export.json> \\
        [--output tests/scenarios/my_scenario.yaml] \\
        [--name my_scenario_name]

Reads a HA recorder JSON export of a climate entity and extracts:
  - initial_temperature (current_temperature at first record)
  - comfort_temp and schedule (from setpoint changes across history)
  - external_temperature_fixed (ext_current_temperature at first record)
  - proportional_function (smart_pi if smart_pi attributes present)
  - cycle_min (from smart_pi.cycle_min)
  - duration_hours (from export time window)

Physics, sensor, and disturbance params are left at template defaults
with # VERIFY comments. Auto-filled fields are annotated # from export.

Uses ruamel.yaml (round-trip mode) to preserve template comments.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ruamel.yaml import YAML

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_TEMPLATE = _PROJECT_ROOT / "tests" / "scenarios" / "_template.yaml"


def _load_export(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or len(data) == 0:
        print(f"ERROR: {path} is empty or not a JSON array.", file=sys.stderr)
        sys.exit(1)
    return data


def _extract_fields(records: list[dict]) -> dict:
    """Extract all VTherm fields from the export. Returns a flat dict of findings."""
    first = records[0]
    last  = records[-1]
    attrs_first = first.get("attributes", {})
    specific    = attrs_first.get("specific_states") or {}
    if isinstance(specific, str):
        specific = {}
    smart_pi    = specific.get("smart_pi") or {}
    if not isinstance(smart_pi, dict):
        smart_pi = {}

    findings: dict = {}

    # Initial temperature
    t0 = attrs_first.get("current_temperature")
    if t0 is not None:
        findings["initial_temperature"] = float(t0)
    else:
        print("WARNING: current_temperature not found in first record; using template default.",
              file=sys.stderr)

    # External temperature
    ext = specific.get("ext_current_temperature")
    if ext is not None:
        findings["external_temperature_fixed"] = float(ext)
    else:
        print("WARNING: ext_current_temperature not found; using template default.", file=sys.stderr)

    # Algorithm
    if smart_pi:
        findings["proportional_function"] = "smart_pi"
    else:
        findings["proportional_function"] = "tpi"
        print("WARNING: smart_pi not found in export; defaulting to tpi.", file=sys.stderr)

    # Cycle min
    if "cycle_min" in smart_pi:
        findings["cycle_min"] = int(smart_pi["cycle_min"])

    # Comfort temp (setpoint at first record)
    t_set = attrs_first.get("temperature")
    if t_set is not None:
        findings["comfort_temp"] = float(t_set)

    # Duration from timestamps
    try:
        import pandas as pd
        ts_first = pd.to_datetime(first["timestamp"], format="ISO8601", utc=True)
        ts_last  = pd.to_datetime(last["timestamp"],  format="ISO8601", utc=True)
        duration_h = (ts_last - ts_first).total_seconds() / 3600.0
        # Round up to nearest 0.5 h, minimum 0.5 h
        duration_h = max(0.5, round(duration_h * 2) / 2)
        findings["duration_hours"] = duration_h
    except Exception as e:
        print(f"WARNING: could not compute duration from timestamps: {e}", file=sys.stderr)

    # Schedule: detect setpoint changes
    schedule = []
    prev_temp = attrs_first.get("temperature")
    try:
        import pandas as pd
        ts0 = pd.to_datetime(first["timestamp"], format="ISO8601", utc=True)
        if prev_temp is not None:
            schedule.append({"at_hour": 0.0, "target_temp": float(prev_temp)})
        for rec in records[1:]:
            attrs = rec.get("attributes", {})
            t_sp = attrs.get("temperature")
            if t_sp is not None and t_sp != prev_temp:
                ts = pd.to_datetime(rec["timestamp"], format="ISO8601", utc=True)
                elapsed_h = round((ts - ts0).total_seconds() / 3600.0, 3)
                schedule.append({"at_hour": elapsed_h, "target_temp": float(t_sp)})
                prev_temp = t_sp
        if schedule:
            findings["schedule"] = schedule
    except Exception as e:
        print(f"WARNING: could not build schedule: {e}", file=sys.stderr)

    return findings


def _apply_findings(doc, findings: dict, name: str) -> None:
    """Apply extracted findings to the ruamel.yaml round-trip document."""

    def _set(node, key, value, comment: str = "from export"):
        """Set a value and append a comment marker."""
        node[key] = value
        # ruamel.yaml comment API: yaml_add_eol_comment(comment, key)
        node.yaml_add_eol_comment(comment, key)

    # Name
    doc["name"] = name
    doc["description"] = "Generated from HA export — verify physics params before running"

    model = doc["model"]
    thermostat = doc["thermostat"]
    simulation = doc["simulation"]

    if "initial_temperature" in findings:
        _set(model, "initial_temperature", findings["initial_temperature"])
    if "external_temperature_fixed" in findings:
        _set(model, "external_temperature_fixed", findings["external_temperature_fixed"])

    if "proportional_function" in findings:
        _set(thermostat, "proportional_function", findings["proportional_function"])
    if "cycle_min" in findings:
        _set(thermostat, "cycle_min", findings["cycle_min"])
    if "comfort_temp" in findings:
        _set(thermostat, "comfort_temp", findings["comfort_temp"])

    if "duration_hours" in findings:
        _set(simulation, "duration_hours", findings["duration_hours"])

    if "schedule" in findings:
        from ruamel.yaml.comments import CommentedSeq, CommentedMap
        sched = CommentedSeq()
        for entry in findings["schedule"]:
            m = CommentedMap()
            m["at_hour"]     = entry["at_hour"]
            m["target_temp"] = entry["target_temp"]
            sched.append(m)
        simulation["schedule"] = sched
        simulation.yaml_add_eol_comment("from export", "schedule")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate a VTsim scenario YAML from a HA climate entity history export"
    )
    parser.add_argument("ha_export", type=Path, help="Path to HA recorder JSON export")
    parser.add_argument(
        "--output", "-o", type=Path,
        default=Path("tests/scenarios/scenario_from_export.yaml"),
        help="Output YAML path (default: tests/scenarios/scenario_from_export.yaml)",
    )
    parser.add_argument(
        "--name", "-n", default=None,
        help="Scenario name (default: output filename stem)",
    )
    args = parser.parse_args(argv)

    name = args.name or args.output.stem

    print(f"Loading export: {args.ha_export}")
    records = _load_export(args.ha_export)
    print(f"  {len(records)} records")

    findings = _extract_fields(records)
    print(f"  Extracted: {list(findings.keys())}")

    if not _TEMPLATE.exists():
        print(f"ERROR: template not found: {_TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    yaml = YAML()
    yaml.preserve_quotes = True
    with _TEMPLATE.open(encoding="utf-8") as f:
        doc = yaml.load(f)

    _apply_findings(doc, findings, name)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f)

    print(f"Written: {args.output}")
    print("NOTE: Physics params (heater_power_watts, thermal_mass, etc.) must be verified")
    print("      against your HA heating_simulator config — they are left at template defaults.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
