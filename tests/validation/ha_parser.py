"""Load HA recorder JSON exports into normalised DataFrames.

The HA history export is a JSON array of climate entity state snapshots.
Each snapshot has:
    - timestamp (ISO 8601)
    - attributes.current_temperature
    - attributes.power_percent / on_percent
    - attributes.specific_states.ext_current_temperature
    - attributes.specific_states.smart_pi.{a, b, deadtime_heat_s, ...}

Usage:
    df = load_ha_export(Path("ha_exports/my_export.json"))
    metrics = compute_settled_metrics(df)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def load_ha_export(path: Path) -> pd.DataFrame:
    """Load a HA recorder JSON export into a normalised DataFrame.

    Elapsed time is computed relative to the first record's timestamp.
    All SmartPI fields are extracted from the nested attributes structure.

    Returns a DataFrame with columns:
        elapsed_s, elapsed_h, timestamp, current_temperature, target_temperature,
        power_percent, on_percent, ext_temperature,
        smartpi_a, smartpi_b, deadtime_heat_s, deadtime_cool_s,
        cycles_since_reset, governance_regime, phase
    """
    with path.open(encoding="utf-8") as f:
        raw: list[dict[str, Any]] = json.load(f)

    rows = []
    for record in raw:
        attrs = record.get("attributes") or {}
        specific = attrs.get("specific_states") or {}
        smart_pi = specific.get("smart_pi") or {}
        if not isinstance(smart_pi, dict):
            smart_pi = {}

        rows.append({
            "timestamp": record.get("timestamp") or record.get("last_changed"),
            "current_temperature": attrs.get("current_temperature"),
            "target_temperature": attrs.get("temperature"),
            "power_percent": attrs.get("power_percent"),
            "on_percent": attrs.get("on_percent"),
            "ext_temperature": specific.get("ext_current_temperature"),
            "smartpi_a": smart_pi.get("a"),
            "smartpi_b": smart_pi.get("b"),
            "deadtime_heat_s": smart_pi.get("deadtime_heat_s"),
            "deadtime_cool_s": smart_pi.get("deadtime_cool_s"),
            "cycles_since_reset": smart_pi.get("cycles_since_reset"),
            "governance_regime": smart_pi.get("governance_regime"),
            "phase": smart_pi.get("phase"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Elapsed seconds from first record
    t0 = df["timestamp"].iloc[0]
    df["elapsed_s"] = (df["timestamp"] - t0).dt.total_seconds()
    df["elapsed_h"] = df["elapsed_s"] / 3600.0

    # Coerce numeric columns
    for col in ("current_temperature", "target_temperature", "power_percent",
                "on_percent", "ext_temperature", "smartpi_a", "smartpi_b",
                "deadtime_heat_s", "deadtime_cool_s"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def compute_settled_metrics(df: pd.DataFrame) -> dict[str, Any]:
    """Compute settled-state summary metrics from a timeseries DataFrame.

    Uses the last 20% of the run as the settled window.  Works for both
    HA export DataFrames (from load_ha_export) and VTsim records DataFrames
    (from the records CSV), as long as they share column names.

    Returns dict with keys:
        settled_a, settled_b (None if not available),
        steady_state_error_c, mean_power_percent,
        deadtime_heat_s, deadtime_cool_s (None if not available)
    """
    if df.empty:
        return {
            "settled_a": None, "settled_b": None,
            "steady_state_error_c": None, "mean_power_percent": None,
            "deadtime_heat_s": None, "deadtime_cool_s": None,
        }

    # 20% window is used consistently for both HA and VTsim sides of the
    # comparison.  analysis.compute_metrics uses 25% for its own SSE metric
    # (a different function for pytest assertions), so numbers will differ
    # slightly if compared directly.
    cutoff = df["elapsed_s"].max() * 0.80
    tail = df[df["elapsed_s"] >= cutoff]

    def _mean_or_none(series: pd.Series):
        clean = series.dropna()
        return float(clean.mean()) if not clean.empty else None

    # Temperature error: use current_temperature if model_temperature absent
    temp_col = "model_temperature" if "model_temperature" in df.columns else "current_temperature"
    error = (tail[temp_col] - tail["target_temperature"]).abs()
    sse = float(error.mean()) if not error.empty else None

    pwr_col = "power_percent"
    mean_pwr = _mean_or_none(tail[pwr_col]) if pwr_col in tail.columns else None

    return {
        "settled_a": _mean_or_none(tail["smartpi_a"]) if "smartpi_a" in tail.columns else None,
        "settled_b": _mean_or_none(tail["smartpi_b"]) if "smartpi_b" in tail.columns else None,
        "steady_state_error_c": round(sse, 4) if sse is not None else None,
        "mean_power_percent": round(mean_pwr, 2) if mean_pwr is not None else None,
        "deadtime_heat_s": _mean_or_none(tail["deadtime_heat_s"]) if "deadtime_heat_s" in tail.columns else None,
        "deadtime_cool_s": _mean_or_none(tail["deadtime_cool_s"]) if "deadtime_cool_s" in tail.columns else None,
    }
