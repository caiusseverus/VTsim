"""Plot generation and metrics for simulation results.

Usage:
    records = await run_simulation(...)
    metrics = compute_metrics(records, scenario)
    save_plot(records, scenario, output_path, metrics)
    write_summary_csv([metrics, ...], Path("results/summary.csv"))
    write_records_csv(records, Path("results/my_scenario_records.csv"))
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd

matplotlib.use("Agg")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def compute_metrics(records: list[dict[str, Any]], scenario: dict[str, Any]) -> dict[str, Any]:
    """Compute summary metrics from simulation records.

    Metrics
    -------
    steady_state_error_c
        Mean absolute error |T_model - T_target| over the last 25% of the
        simulation.  Uses model_temperature as ground truth to avoid
        sensor-lag artefacts.
    max_overshoot_c
        Maximum (T_model - T_target) observed across the full simulation.
        Positive = room exceeded setpoint.
    settling_time_h
        Elapsed hours at which the room temperature first enters and stays
        within the thermostat deadband for at least 30 consecutive minutes.
        None if the temperature never settles.
    energy_kwh
        Integral of (power_fraction × heater_power_watts) over the full
        simulation duration, converted to kWh.
    switch_cycles
        Number of ON→OFF transitions observed in power_percent.  Proxy for
        relay or valve wear.
    smartpi_a_final, smartpi_b_final
        Final SmartPI learned coefficients (None for TPI runs).
    scenario_name
        Copied from scenario["name"] for CSV grouping.
    """
    if not records:
        return _empty_metrics(scenario)

    df = pd.DataFrame(records)
    df = df.sort_values("elapsed_s").reset_index(drop=True)

    model_name: str = scenario.get("name", "unknown")
    heater_watts = float(
        scenario.get("model", {}).get(
            "heater_power_watts_r2c2",
            scenario.get("model", {}).get("heater_power_watts", 0.0),
        )
    )
    deadband = float(
        scenario.get("thermostat", {}).get("smart_pi_deadband", 0.2)
    )
    dt_s = float(scenario.get("simulation", {}).get("step_seconds", 10.0))

    # Require numeric columns.
    df["model_temperature"] = pd.to_numeric(df["model_temperature"], errors="coerce")
    df["target_temperature"] = pd.to_numeric(df["target_temperature"], errors="coerce")
    df["power_percent"] = pd.to_numeric(df.get("power_percent"), errors="coerce")
    df["on_percent"] = pd.to_numeric(df.get("on_percent"), errors="coerce")

    # Error vs setpoint.
    df["error_c"] = df["model_temperature"] - df["target_temperature"]

    # ── Steady-state error ───────────────────────────────────────────────────
    # Start from settling_time if found (avoids hysteresis-mode startup
    # disruption); fall back to last 33% of the run.
    window_steps = max(1, int(30 * 60 / dt_s))
    in_band_pre = (df["error_c"].abs() <= deadband).to_numpy()
    settle_s: float | None = None
    for i in range(len(in_band_pre) - window_steps + 1):
        if in_band_pre[i : i + window_steps].all():
            settle_s = float(df["elapsed_s"].iloc[i])
            break
    if settle_s is not None:
        sse_tail = df[df["elapsed_s"] >= settle_s]
    else:
        sse_tail = df[df["elapsed_s"] >= df["elapsed_s"].max() * 0.67]
    steady_state_error_c = float(sse_tail["error_c"].abs().mean()) if not sse_tail.empty else float("nan")

    # ── Max overshoot ────────────────────────────────────────────────────────
    max_overshoot_c = float(df["error_c"].max())

    # ── Settling time ────────────────────────────────────────────────────────
    settling_time_h: float | None = (settle_s / 3600.0) if settle_s is not None else None

    # ── Energy ───────────────────────────────────────────────────────────────
    # power_percent is 0–100; divide by 100 to get fraction.
    # Each record covers record_every_seconds of sim time.
    record_every_s = float(scenario.get("simulation", {}).get("record_every_seconds", 60.0))
    pwr_col = df["power_percent"] if df["power_percent"].notna().any() else df["on_percent"]
    pwr_fraction = pwr_col.fillna(0.0) / 100.0
    energy_kwh = float((pwr_fraction * heater_watts * record_every_s).sum() / 3_600_000.0)

    # ── Switch cycles (ON→OFF transitions in power_percent) ─────────────────
    p = pwr_col.fillna(0.0)
    switch_cycles = int(((p.shift(1, fill_value=0) > 0) & (p == 0)).sum())

    # ── SmartPI coefficients ─────────────────────────────────────────────────
    last = df.iloc[-1]
    smartpi_a_final = _to_float(last.get("smartpi_a"))
    smartpi_b_final = _to_float(last.get("smartpi_b"))
    deadtime_heat_s = _to_float(last.get("deadtime_heat_s"))
    deadtime_cool_s = _to_float(last.get("deadtime_cool_s"))

    return {
        "scenario_name": model_name,
        "steady_state_error_c": round(steady_state_error_c, 4),
        "max_overshoot_c": round(max_overshoot_c, 4),
        "settling_time_h": round(settling_time_h, 2) if settling_time_h is not None else None,
        "energy_kwh": round(energy_kwh, 4),
        "switch_cycles": switch_cycles,
        "smartpi_a_final": smartpi_a_final,
        "smartpi_b_final": smartpi_b_final,
        "deadtime_heat_s": deadtime_heat_s,
        "deadtime_cool_s": deadtime_cool_s,
    }


def _empty_metrics(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_name": scenario.get("name", "unknown"),
        "steady_state_error_c": None,
        "max_overshoot_c": None,
        "settling_time_h": None,
        "energy_kwh": None,
        "switch_cycles": None,
        "smartpi_a_final": None,
        "smartpi_b_final": None,
        "deadtime_heat_s": None,
        "deadtime_cool_s": None,
    }


def _to_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------

def save_plot(
    records: list[dict[str, Any]],
    scenario: dict[str, Any],
    output_path: Path,
    metrics: dict[str, Any] | None = None,
) -> None:
    """Save a two-panel simulation result plot.

    Top panel: room temperature (model ground truth) and target temperature.
    Bottom panel: heater power percentage over time.

    Args:
        records:     Output from ``run_simulation()``.
        scenario:    Full scenario dict (used for title and annotations).
        output_path: Path to write the PNG.
        metrics:     Optional metrics dict to annotate the title.
    """
    if not records:
        return

    df = pd.DataFrame(records)
    df = df.sort_values("elapsed_h").reset_index(drop=True)
    df["model_temperature"] = pd.to_numeric(df["model_temperature"], errors="coerce")
    df["target_temperature"] = pd.to_numeric(df["target_temperature"], errors="coerce")
    df["power_percent"] = pd.to_numeric(df.get("power_percent"), errors="coerce")
    df["on_percent"] = pd.to_numeric(df.get("on_percent"), errors="coerce")
    df["smartpi_u_ff"] = pd.to_numeric(df.get("smartpi_u_ff"), errors="coerce")
    df["smartpi_u_pi"] = pd.to_numeric(df.get("smartpi_u_pi"), errors="coerce")

    # Use power_percent if present, otherwise on_percent.
    if df["power_percent"].notna().any():
        power_col = df["power_percent"]
    else:
        power_col = df["on_percent"].fillna(0.0)

    has_control = df["smartpi_u_ff"].notna().any() or df["smartpi_u_pi"].notna().any()
    n_panels = 3 if has_control else 2
    height_ratios = [3, 1, 1] if has_control else [3, 1]

    fig, axes = plt.subplots(
        n_panels, 1, figsize=(14, 8), sharex=True,
        gridspec_kw={"height_ratios": height_ratios},
    )
    ax_temp, ax_pwr = axes[0], axes[1]
    ax_ctrl = axes[2] if has_control else None

    # Temperature panel.
    ax_temp.plot(
        df["elapsed_h"], df["model_temperature"],
        label="Room temperature (model)", linewidth=1.5,
    )
    ax_temp.plot(
        df["elapsed_h"], df["target_temperature"],
        linestyle="--", label="Target temperature", linewidth=1.2, color="tab:orange",
    )
    ax_temp.set_ylabel("Temperature (°C)")
    ax_temp.legend(loc="upper right", fontsize=9)
    ax_temp.grid(alpha=0.25)

    # Power panel: planned duty cycle only (switch state removed — clutters plot).
    ax_pwr.fill_between(
        df["elapsed_h"], power_col.fillna(0.0),
        alpha=0.4, label="Duty cycle (VT planned, %)", color="tab:red",
    )
    ax_pwr.set_ylabel("Power (%)")
    ax_pwr.set_ylim(-2, 102)
    if ax_ctrl is None:
        ax_pwr.set_xlabel("Elapsed time (h)")
    ax_pwr.legend(loc="upper right", fontsize=8)
    ax_pwr.grid(alpha=0.25)

    # SmartPI control signals panel (u_ff and u_pi).
    if ax_ctrl is not None:
        if df["smartpi_u_ff"].notna().any():
            ax_ctrl.plot(
                df["elapsed_h"], df["smartpi_u_ff"],
                linewidth=1.0, label="u_ff", color="tab:green",
            )
        if df["smartpi_u_pi"].notna().any():
            ax_ctrl.plot(
                df["elapsed_h"], df["smartpi_u_pi"],
                linewidth=1.0, label="u_pi", color="tab:purple",
            )
        ax_ctrl.set_ylabel("Control signal")
        ax_ctrl.set_xlabel("Elapsed time (h)")
        ax_ctrl.legend(loc="upper right", fontsize=8)
        ax_ctrl.grid(alpha=0.25)

    # Title.
    title = scenario.get("name", "VT Simulation")
    if scenario.get("description"):
        title += f"\n{scenario['description']}"
    if metrics:
        sse = metrics.get("steady_state_error_c")
        overshoot = metrics.get("max_overshoot_c")
        settle = metrics.get("settling_time_h")
        parts = []
        if sse is not None:
            parts.append(f"SSE={sse:.3f}°C")
        if overshoot is not None:
            parts.append(f"overshoot={overshoot:+.3f}°C")
        if settle is not None:
            parts.append(f"settled@{settle:.1f}h")
        if parts:
            title += "   |   " + "   ".join(parts)

    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Summary CSV
# ---------------------------------------------------------------------------

def write_records_csv(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write per-scenario simulation records to a timestep-level CSV.

    Columns are the union of all keys across all records (preserving insertion
    order of the first record).  Missing values are written as empty strings.
    If records is empty, the file is not created.

    Args:
        records:     List of snapshot dicts from ``run_simulation()``.
        output_path: Destination path (parent dirs created automatically).
    """
    if not records:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Collect all keys across all records to handle non-uniform dicts
    seen = dict.fromkeys(records[0])  # preserve insertion order of first record
    for row in records[1:]:
        seen.update(dict.fromkeys(row))
    fieldnames = list(seen)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            writer.writerow({k: ("" if v is None else v) for k, v in row.items()})


def write_ha_export_json(
    records: list[dict[str, Any]],
    climate_entity_id: str,
    output_path: Path,
    sim_start: datetime,
) -> None:
    """Write simulation records in HA history-exporter JSON format.

    Each record in the output array matches the structure produced by the HA
    history exporter, enabling direct field-by-field comparison with real HA
    data.  The complete VT attribute dict (as VT reports it to HA) is preserved
    under ``attributes``.  Sim physics ground truth (model temperature, sensor
    temperature, switch state, etc.) is added under ``attributes.sim_ground_truth``
    so it doesn't conflict with any real VT field.

    Args:
        records:            Output from ``run_simulation()``.
        climate_entity_id:  The VT climate entity ID used during simulation.
        output_path:        Destination path for the JSON file.
        sim_start:          UTC datetime when the simulation began (returned by
                            ``run_simulation()`` alongside the records list).
    """
    if not records:
        return

    # Keys that belong in sim_ground_truth rather than the HA-format attributes.
    # These are simulation-only fields not present in real HA data.
    _SIM_KEYS = {
        "elapsed_s", "elapsed_h", "sensor_temperature",
        "model_temperature", "model_ext_temperature",
        "model_effective_heater_power_w", "model_heating_rate_c_per_s",
        "model_heat_loss_rate_c_per_s", "model_net_heat_rate_c_per_s",
        "switch_state",
    }

    if sim_start.tzinfo is None:
        sim_start = sim_start.replace(tzinfo=timezone.utc)

    export: list[dict[str, Any]] = []
    for record in records:
        elapsed_s = float(record.get("elapsed_s", 0.0))
        ts: datetime = sim_start + timedelta(seconds=elapsed_s)
        ts_iso = ts.isoformat()

        # Start with the full VT attribute dict captured at this timestep.
        raw_attrs: dict[str, Any] = dict(record.get("_vt_raw_attributes") or {})

        # Collect sim ground truth: explicit keys + any model_* extras.
        sim_gt: dict[str, Any] = {
            k: record[k] for k in _SIM_KEYS if k in record
        }
        for k, v in record.items():
            if k.startswith("model_") and k not in sim_gt:
                sim_gt[k] = v

        raw_attrs["sim_ground_truth"] = sim_gt

        export.append({
            "entity_id": climate_entity_id,
            "last_changed": ts_iso,
            "last_updated": ts_iso,
            "state": record.get("_vt_entity_state") or record.get("hvac_mode") or "unknown",
            "timestamp": ts.timestamp(),
            "attributes": raw_attrs,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(export, f, indent=2, default=str)


def write_summary_csv(
    all_metrics: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Write one row per scenario to a CSV summary file.

    Args:
        all_metrics: List of dicts returned by ``compute_metrics()``.
        output_path: Destination path (parent dirs created automatically).
    """
    if not all_metrics:
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(all_metrics[0].keys())
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_metrics)
