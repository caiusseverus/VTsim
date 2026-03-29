#!/usr/bin/env python3
"""Compare two VTsim/HA JSON exports.

Produces a PNG figure with:
  - Side-by-side configuration diff table
  - Gantt-style categorical timelines for SmartPI mode fields
  - Numeric overlays for on_percent, a, b, error

Usage:
    python tools/compare.py a.json b.json [--output comparison.png] [--show]

Both files may be HA history-exporter JSON or VTsim ha_export JSON.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt

matplotlib.use("Agg")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_export(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list) or not data:
        raise ValueError(f"{path}: expected a non-empty JSON array")
    return data


def _parse_ts(val: Any) -> float:
    """Parse ISO string or numeric timestamp to unix float."""
    if isinstance(val, (int, float)):
        return float(val)
    return datetime.fromisoformat(str(val).replace("Z", "+00:00")).timestamp()


def elapsed_hours(records: list[dict]) -> list[float]:
    t0 = _parse_ts(records[0]["timestamp"])
    return [(_parse_ts(r["timestamp"]) - t0) / 3600.0 for r in records]


def _smart_pi(record: dict) -> dict:
    return (
        record.get("attributes", {})
        .get("specific_states", {})
        .get("smart_pi", {})
    ) or {}


def get_series(records: list[dict], field: str, source: str = "smart_pi") -> list[Any]:
    """Extract a time-aligned value list (None where absent)."""
    out = []
    for r in records:
        attrs = r.get("attributes", {})
        if source == "smart_pi":
            val = _smart_pi(r).get(field)
        elif source == "attributes":
            val = attrs.get(field)
        elif source == "sim_ground_truth":
            val = (attrs.get("sim_ground_truth") or {}).get(field)
        else:
            val = r.get(field)
        out.append(val)
    return out


# ---------------------------------------------------------------------------
# Configuration comparison
# ---------------------------------------------------------------------------

# Each entry: (display_name, extractor_fn)
_CONFIG_FIELDS: list[tuple[str, Any]] = [
    ("entity_id",               lambda r, _: r.get("entity_id")),
    ("friendly_name",           lambda r, _: r.get("attributes", {}).get("friendly_name")),
    ("preset_mode",             lambda r, _: r.get("attributes", {}).get("preset_mode")),
    ("device_power_w",          lambda r, _: (r.get("attributes", {}).get("power_manager") or {}).get("device_power")),
    ("cycle_min",               lambda r, sp: sp.get("cycle_min")),
    ("near_band_deg",           lambda r, sp: sp.get("near_band_deg")),
    ("near_band_source",        lambda r, sp: sp.get("near_band_source")),
    ("tau_min",                 lambda r, sp: sp.get("tau_min")),
    ("safety_delay_min",        lambda r, _: (r.get("attributes", {}).get("safety_manager") or {}).get("safety_delay_min")),
    ("safety_min_on_pct",       lambda r, _: (r.get("attributes", {}).get("safety_manager") or {}).get("safety_min_on_percent")),
    ("safety_default_on_pct",   lambda r, _: (r.get("attributes", {}).get("safety_manager") or {}).get("safety_default_on_percent")),
    ("ab_confidence_state",     lambda r, sp: sp.get("ab_confidence_state")),
    ("calibration_state",       lambda r, sp: sp.get("calibration_state")),
]


def extract_config(records: list[dict]) -> dict[str, Any]:
    # Use first record for config; fall back to last for anything absent
    first, last = records[0], records[-1]
    result: dict[str, Any] = {}
    for name, fn in _CONFIG_FIELDS:
        val = fn(first, _smart_pi(first))
        if val is None:
            val = fn(last, _smart_pi(last))
        result[name] = val
    return result


def print_config_diff(
    label_a: str, cfg_a: dict,
    label_b: str, cfg_b: dict,
) -> list[tuple[str, Any, Any, bool]]:
    col = 30
    print(f"\n{'Field':<26}  {label_a[:col]:<{col}}  {label_b[:col]:<{col}}  Match")
    print("-" * (26 + col * 2 + 12))
    rows = []
    for name, _ in _CONFIG_FIELDS:
        va, vb = cfg_a.get(name), cfg_b.get(name)
        match = va == vb
        sym = "✓" if match else "✗"
        print(f"{name:<26}  {str(va)[:col]:<{col}}  {str(vb)[:col]:<{col}}  {sym}")
        rows.append((name, va, vb, match))
    print()
    return rows


# ---------------------------------------------------------------------------
# Categorical (Gantt) timeline
# ---------------------------------------------------------------------------

# SmartPI fields to show as mode timelines
MODE_FIELDS = [
    "governance_regime",
    "phase",
    "regulation_mode",
    "learn_last_reason",
    "i_mode",
    "ff_reason",
]

# 20-colour palette for categorical values
_PALETTE = [
    "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3",
    "#937860", "#DA8BC3", "#8C8C8C", "#CCB974", "#64B5CD",
    "#1F77B4", "#FF7F0E", "#2CA02C", "#D62728", "#9467BD",
    "#8C564B", "#E377C2", "#7F7F7F", "#BCBD22", "#17BECF",
]


def _color_map(values: list[str | None]) -> dict[str, str]:
    unique = sorted({str(v) for v in values if v is not None})
    return {v: _PALETTE[i % len(_PALETTE)] for i, v in enumerate(unique)}


def _draw_gantt(
    ax,
    elapsed: list[float],
    values: list[Any],
    y: float,
    bar_h: float,
    color_map: dict[str, str],
    total_h: float,
) -> None:
    n = len(elapsed)
    for i, (t, v) in enumerate(zip(elapsed, values)):
        if v is None:
            continue
        t_end = elapsed[i + 1] if i + 1 < n else t + total_h / max(n, 1)
        ax.barh(
            y, max(t_end - t, 1e-9), left=t, height=bar_h * 0.82,
            color=color_map.get(str(v), "#cccccc"), align="center",
        )


def plot_mode_timelines(
    axs,
    elapsed_a: list[float],
    elapsed_b: list[float],
    records_a: list[dict],
    records_b: list[dict],
    label_a: str,
    label_b: str,
) -> None:
    total_h = max(
        elapsed_a[-1] if elapsed_a else 1,
        elapsed_b[-1] if elapsed_b else 1,
    )

    for ax, field in zip(axs, MODE_FIELDS):
        vals_a = get_series(records_a, field)
        vals_b = get_series(records_b, field)
        cmap = _color_map(vals_a + vals_b)  # type: ignore[operator]

        _draw_gantt(ax, elapsed_a, vals_a, y=1.0, bar_h=0.8, color_map=cmap, total_h=total_h)
        _draw_gantt(ax, elapsed_b, vals_b, y=0.0, bar_h=0.8, color_map=cmap, total_h=total_h)

        ax.set_yticks([0, 1])
        ax.set_yticklabels(
            [_trim(label_b, 18), _trim(label_a, 18)], fontsize=7,
        )
        ax.set_ylim(-0.55, 1.55)
        ax.set_ylabel(field, fontsize=7.5, rotation=0, ha="right", va="center", labelpad=4)
        ax.set_xlim(0, total_h)
        ax.grid(axis="x", alpha=0.25)

        # Per-subplot legend for the values present in this field
        unique = sorted({str(v) for v in vals_a + vals_b if v is not None})
        patches = [mpatches.Patch(color=cmap[v], label=v) for v in unique]
        if patches:
            ax.legend(
                handles=patches, loc="upper right", fontsize=6,
                ncol=min(5, len(patches)), framealpha=0.7,
            )


# ---------------------------------------------------------------------------
# Numeric timeline
# ---------------------------------------------------------------------------

_NUMERIC_FIELDS = [
    ("on_percent",  "attributes",  "On percent (%)"),
    ("a",           "smart_pi",    "SmartPI  a"),
    ("b",           "smart_pi",    "SmartPI  b"),
    ("error",       "smart_pi",    "Error (°C)"),
]


def plot_numeric_timelines(
    axs,
    elapsed_a: list[float],
    elapsed_b: list[float],
    records_a: list[dict],
    records_b: list[dict],
    label_a: str,
    label_b: str,
) -> None:
    for ax, (field, source, ylabel) in zip(axs, _NUMERIC_FIELDS):
        for elapsed, records, label, ls in (
            (elapsed_a, records_a, label_a, "-"),
            (elapsed_b, records_b, label_b, "--"),
        ):
            pairs = [
                (t, float(v))
                for t, v in zip(elapsed, get_series(records, field, source))
                if v is not None
            ]
            if pairs:
                ts, vs = zip(*pairs)
                ax.plot(ts, vs, label=_trim(label, 22), linewidth=1.1, linestyle=ls)

        ax.set_ylabel(ylabel, fontsize=8)
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(alpha=0.25)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _trim(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def _label_from(records: list[dict], path: Path) -> str:
    eid = records[0].get("entity_id")
    return eid if eid else path.stem


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file_a", type=Path, metavar="A.json")
    ap.add_argument("file_b", type=Path, metavar="B.json")
    ap.add_argument("--output", "-o", type=Path, default=None,
                    help="Output PNG path (default: comparison_<A>_vs_<B>.png)")
    ap.add_argument("--show", action="store_true", help="Open the figure interactively after saving")
    args = ap.parse_args()

    records_a = load_export(args.file_a)
    records_b = load_export(args.file_b)

    label_a = _label_from(records_a, args.file_a)
    label_b = _label_from(records_b, args.file_b)

    elapsed_a = elapsed_hours(records_a)
    elapsed_b = elapsed_hours(records_b)

    cfg_a = extract_config(records_a)
    cfg_b = extract_config(records_b)
    diff_rows = print_config_diff(label_a, cfg_a, label_b, cfg_b)

    # ------------------------------------------------------------------
    # Figure layout
    # ------------------------------------------------------------------
    n_mode = len(MODE_FIELDS)
    n_num = len(_NUMERIC_FIELDS)
    height_ratios = [3] + [1] * n_mode + [1.8] * n_num
    fig_h = 3 + n_mode * 1.1 + n_num * 1.8

    fig, all_axs = plt.subplots(
        1 + n_mode + n_num, 1,
        figsize=(17, fig_h),
        gridspec_kw={"height_ratios": height_ratios},
    )

    # -- Config table -------------------------------------------------
    ax_tbl = all_axs[0]
    ax_tbl.axis("off")
    cell_text = [
        [r[0], _trim(str(r[1]), 35), _trim(str(r[2]), 35), "✓" if r[3] else "✗"]
        for r in diff_rows
    ]
    cell_colors = [
        ["#f0f0f0", "white", "white", "#c8f7c5" if r[3] else "#f7c5c5"]
        for r in diff_rows
    ]
    tbl = ax_tbl.table(
        cellText=cell_text,
        colLabels=["Field", _trim(label_a, 35), _trim(label_b, 35), ""],
        cellColours=cell_colors,
        cellLoc="left",
        loc="center",
        bbox=[0.0, 0.0, 1.0, 1.0],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7.5)
    ax_tbl.set_title("Configuration", fontsize=10, pad=4, loc="left")

    # -- Mode timelines -----------------------------------------------
    ax_modes = all_axs[1 : 1 + n_mode]
    plot_mode_timelines(ax_modes, elapsed_a, elapsed_b, records_a, records_b, label_a, label_b)
    ax_modes[0].set_title("SmartPI mode timelines", fontsize=10, pad=4, loc="left")
    ax_modes[-1].set_xlabel("Elapsed time (h)", fontsize=8)

    # -- Numeric overlays ---------------------------------------------
    ax_nums = all_axs[1 + n_mode :]
    plot_numeric_timelines(ax_nums, elapsed_a, elapsed_b, records_a, records_b, label_a, label_b)
    ax_nums[0].set_title("Key numeric signals", fontsize=10, pad=4, loc="left")
    ax_nums[-1].set_xlabel("Elapsed time (h)", fontsize=8)

    fig.suptitle(
        f"VTsim / HA comparison  ·  {args.file_a.name}  vs  {args.file_b.name}",
        fontsize=11, y=1.002,
    )
    fig.tight_layout()

    output: Path = args.output or Path(f"comparison_{args.file_a.stem}_vs_{args.file_b.stem}.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, bbox_inches="tight")
    print(f"Saved: {output}")

    if args.show:
        import matplotlib
        matplotlib.use("TkAgg")
        plt.show()


if __name__ == "__main__":
    main()
