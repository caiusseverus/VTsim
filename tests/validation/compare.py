#!/usr/bin/env python3
"""Compare VTsim simulation output against a real HA recorder export.

Usage:
    uv run python tests/validation/compare.py \\
        tests/validation/ha_exports/my_export.json \\
        my_scenario_name \\
        [--results-dir results] \\
        [--output-dir results/validation]

Outputs a multi-panel PNG to <output-dir>/<scenario>_vs_ha.png and prints
a metric comparison table to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Allow running as a script from the project root
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_PROJECT_ROOT), str(_PROJECT_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from validation.ha_parser import compute_settled_metrics, load_ha_export


def _load_fakha_records(records_csv: Path) -> pd.DataFrame:
    """Load VTsim per-scenario records CSV."""
    df = pd.read_csv(records_csv)
    if "elapsed_h" not in df.columns:
        raise ValueError(
            f"Records CSV is missing 'elapsed_h' column: {records_csv}\n"
            "Re-run the scenario to regenerate the records file."
        )
    for col in ("elapsed_s", "elapsed_h", "model_temperature", "target_temperature",
                "power_percent", "on_percent", "switch_state", "smartpi_a", "smartpi_b",
                "deadtime_heat_s", "deadtime_cool_s"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _render_comparison(
    ha_df: pd.DataFrame,
    sim_df: pd.DataFrame,
    scenario_name: str,
    ha_metrics: dict,
    sim_metrics: dict,
    output_path: Path,
) -> None:
    """Render a multi-panel comparison PNG."""
    has_a = ha_df["smartpi_a"].notna().any() or (
        "smartpi_a" in sim_df.columns and sim_df["smartpi_a"].notna().any()
    )
    has_b = ha_df["smartpi_b"].notna().any() or (
        "smartpi_b" in sim_df.columns and sim_df["smartpi_b"].notna().any()
    )
    n_panels = 2 + int(has_a) + int(has_b) + 1  # temp + power + a + b + table

    fig, axes = plt.subplots(n_panels, 1, figsize=(14, 3 * n_panels), sharex=False)
    ax_idx = 0

    # --- Panel 1: Temperature ---
    ax = axes[ax_idx]; ax_idx += 1
    temp_col_sim = "model_temperature" if "model_temperature" in sim_df.columns else "current_temperature"
    ax.plot(sim_df["elapsed_h"], sim_df[temp_col_sim],
            label="VTsim (model)", linewidth=1.5, color="tab:blue")
    ax.plot(ha_df["elapsed_h"], ha_df["current_temperature"],
            label="Real HA", linewidth=1.5, linestyle="--", color="tab:orange")
    if "target_temperature" in sim_df.columns:
        ax.plot(sim_df["elapsed_h"], sim_df["target_temperature"],
                linestyle=":", color="grey", linewidth=1.0, label="Setpoint")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title(f"Validation: {scenario_name}")
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)

    # --- Panel 2: Power percent ---
    # Smooth VTsim power_percent over one PWM cycle so hysteresis-mode 0/100 pulses
    # appear as a duty-cycle percentage, matching HA's representation.
    ax = axes[ax_idx]; ax_idx += 1
    dt_s = sim_df["elapsed_s"].diff().median() or 60.0
    cycle_s = 10 * 60  # default 10-minute PWM cycle
    window = max(1, int(round(cycle_s / dt_s)))
    sim_power_smooth = (
        sim_df["power_percent"].fillna(0)
        .rolling(window, center=True, min_periods=1)
        .mean()
    )
    ax.plot(sim_df["elapsed_h"], sim_power_smooth,
            label="VTsim power_percent", linewidth=1.2, color="tab:blue")
    ax.plot(ha_df["elapsed_h"], ha_df["power_percent"].fillna(0),
            label="Real HA power_percent", linewidth=1.2, linestyle="--", color="tab:orange")
    ax.set_ylabel("Power (%)")
    ax.set_ylim(-2, 102)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.25)

    # --- Panel 3: SmartPI a ---
    if has_a:
        ax = axes[ax_idx]; ax_idx += 1
        if "smartpi_a" in sim_df.columns:
            ax.plot(sim_df["elapsed_h"], sim_df["smartpi_a"],
                    label="VTsim a", linewidth=1.2, color="tab:blue")
        if ha_df["smartpi_a"].notna().any():
            ax.plot(ha_df["elapsed_h"], ha_df["smartpi_a"],
                    label="Real HA a", linewidth=1.2, linestyle="--", color="tab:orange")
        ax.set_ylabel("SmartPI a")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.25)

    # --- Panel 4: SmartPI b ---
    if has_b:
        ax = axes[ax_idx]; ax_idx += 1
        if "smartpi_b" in sim_df.columns:
            ax.plot(sim_df["elapsed_h"], sim_df["smartpi_b"],
                    label="VTsim b", linewidth=1.2, color="tab:blue")
        if ha_df["smartpi_b"].notna().any():
            ax.plot(ha_df["elapsed_h"], ha_df["smartpi_b"],
                    label="Real HA b", linewidth=1.2, linestyle="--", color="tab:orange")
        ax.set_ylabel("SmartPI b")
        ax.legend(fontsize=9)
        ax.grid(alpha=0.25)

    # --- Panel 5: Metric table ---
    ax = axes[ax_idx]
    ax.axis("off")
    rows = []
    for key, label in [
        ("settled_a", "Settled a"),
        ("settled_b", "Settled b"),
        ("steady_state_error_c", "SSE (°C)"),
        ("mean_power_percent", "Mean power (%)"),
        ("deadtime_heat_s", "Deadtime heat (s)"),
        ("deadtime_cool_s", "Deadtime cool (s)"),
    ]:
        sim_v = sim_metrics.get(key)
        ha_v = ha_metrics.get(key)
        rows.append([label,
                     f"{sim_v:.5g}" if sim_v is not None else "n/a",
                     f"{ha_v:.5g}" if ha_v is not None else "n/a"])

    table = ax.table(
        cellText=rows,
        colLabels=["Metric", "VTsim", "Real HA"],
        loc="center", cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.4)

    # x-axis label on the bottom time-series panel only (table panel has no x-axis)
    axes[ax_idx - 1].set_xlabel("Elapsed time (h)")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"Report written to: {output_path}")


def _print_metric_table(ha_metrics: dict, sim_metrics: dict) -> None:
    print(f"\n{'Metric':<30} {'VTsim':>12} {'Real HA':>12}")
    print("-" * 56)
    for key, label in [
        ("settled_a", "Settled a"),
        ("settled_b", "Settled b"),
        ("steady_state_error_c", "SSE (°C)"),
        ("mean_power_percent", "Mean power (%)"),
        ("deadtime_heat_s", "Deadtime heat (s)"),
        ("deadtime_cool_s", "Deadtime cool (s)"),
    ]:
        sim_v = sim_metrics.get(key)
        ha_v = ha_metrics.get(key)
        sim_s = f"{sim_v:.5g}" if sim_v is not None else "n/a"
        ha_s = f"{ha_v:.5g}" if ha_v is not None else "n/a"
        print(f"{label:<30} {sim_s:>12} {ha_s:>12}")
    print()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare VTsim vs real HA VTherm output")
    parser.add_argument("ha_export", type=Path, help="Path to HA recorder JSON export")
    parser.add_argument("scenario_name", help="VTsim scenario name (stem of records CSV)")
    parser.add_argument("--results-dir", type=Path, default=Path("results"),
                        help="Directory containing <scenario>_records.csv (default: results/)")
    parser.add_argument("--output-dir", type=Path, default=Path("results/validation"),
                        help="Output directory for PNG (default: results/validation/)")
    args = parser.parse_args(argv)

    print(f"Loading HA export: {args.ha_export}")
    ha_df = load_ha_export(args.ha_export)
    print(f"  {len(ha_df)} records, {ha_df['elapsed_h'].max():.2f}h window")

    if ha_df.empty:
        print("ERROR: HA export contains no records.", file=sys.stderr)
        return 1

    records_csv = args.results_dir / f"{args.scenario_name}_records.csv"
    if not records_csv.exists():
        print(f"ERROR: VTsim records not found: {records_csv}", file=sys.stderr)
        print("Run the scenario first:", file=sys.stderr)
        print(f"  uv run pytest -q 'tests/test_vt_scenarios.py::test_vt_scenario[{args.scenario_name}]' -s", file=sys.stderr)
        return 1

    print(f"Loading VTsim records: {records_csv}")
    sim_df = _load_fakha_records(records_csv)
    print(f"  {len(sim_df)} records, {sim_df['elapsed_h'].max():.2f}h window")

    ha_metrics = compute_settled_metrics(ha_df)
    sim_metrics = compute_settled_metrics(sim_df)
    _print_metric_table(ha_metrics, sim_metrics)

    output_path = args.output_dir / f"{args.scenario_name}_vs_ha.png"
    _render_comparison(ha_df, sim_df, args.scenario_name, ha_metrics, sim_metrics, output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
