"""HA-format JSON comparison logic for the web backend.

Accepts records in either HA history-exporter format or VTsim ha_export format
(they share the same schema).  Returns structured data the frontend renders with
Plotly — no matplotlib dependency here.
"""
from __future__ import annotations

import json
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import RESULTS_DIR

_TEMP_DIR = Path(tempfile.gettempdir()) / "vtsim_ha_compare"
_TEMP_DIR.mkdir(exist_ok=True)

MODE_FIELDS = [
    "governance_regime",
    "phase",
    "regulation_mode",
    "learn_last_reason",
    "i_mode",
    "ff_reason",
]

NUMERIC_FIELDS: list[tuple[str, str]] = [
    ("on_percent", "attributes"),
    ("a",          "smart_pi"),
    ("b",          "smart_pi"),
    ("error",      "smart_pi"),
]

# Fields extracted for the config diff table.
# Tuple: (field_name, extractor).  All fields are always extracted and
# returned; the frontend decides which subset to display.
_CONFIG_FIELDS: list[tuple[str, Any]] = [
    # ── Identity ────────────────────────────────────────────────────────────
    ("entity_id",                lambda r, sp: r.get("entity_id")),
    ("friendly_name",            lambda r, sp: (r.get("attributes") or {}).get("friendly_name")),
    ("preset_mode",              lambda r, sp: (r.get("attributes") or {}).get("preset_mode")),
    # ── Thermostat core ─────────────────────────────────────────────────────
    ("device_power_w",           lambda r, sp: ((r.get("attributes") or {}).get("power_manager") or {}).get("device_power")),
    ("cycle_min",                lambda r, sp: sp.get("cycle_min")),
    ("near_band_deg",            lambda r, sp: sp.get("near_band_deg")),
    ("near_band_source",         lambda r, sp: sp.get("near_band_source")),
    ("tau_min",                  lambda r, sp: sp.get("tau_min")),
    ("sat_persistent_cycles",    lambda r, sp: sp.get("sat_persistent_cycles")),
    # ── Safety ──────────────────────────────────────────────────────────────
    ("safety_delay_min",         lambda r, sp: ((r.get("attributes") or {}).get("safety_manager") or {}).get("safety_delay_min")),
    ("safety_min_on_pct",        lambda r, sp: ((r.get("attributes") or {}).get("safety_manager") or {}).get("safety_min_on_percent")),
    ("safety_default_on_pct",    lambda r, sp: ((r.get("attributes") or {}).get("safety_manager") or {}).get("safety_default_on_percent")),
    # ── Feedforward ─────────────────────────────────────────────────────────
    ("ff_scale_unreliable_max",  lambda r, sp: sp.get("ff_scale_unreliable_max")),
    ("ff_warmup_ok_count",       lambda r, sp: sp.get("ff_warmup_ok_count")),
    ("ff_taper_alpha",           lambda r, sp: sp.get("ff_taper_alpha")),
    # ── Twin / SmartPI extras ───────────────────────────────────────────────
    ("twin_control_enabled",     lambda r, sp: sp.get("twin_control_enabled")),
    ("twin_sp_filter_active",    lambda r, sp: sp.get("twin_sp_filter_active")),
    # ── Gain factors ────────────────────────────────────────────────────────
    ("ki_near_factor",           lambda r, sp: sp.get("ki_near_factor")),
    ("kp_near_factor",           lambda r, sp: sp.get("kp_near_factor")),
    ("kp_source",                lambda r, sp: sp.get("kp_source")),
    # ── Emergent / diagnostic (disabled by default in UI) ───────────────────
    ("ab_confidence_state",      lambda r, sp: sp.get("ab_confidence_state")),
    ("calibration_state",        lambda r, sp: sp.get("calibration_state")),
    ("diag_ab_mode_effective",   lambda r, sp: sp.get("diag_ab_mode_effective")),
    ("tau_reliable",             lambda r, sp: sp.get("tau_reliable")),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _smart_pi(record: dict) -> dict:
    return (
        (record.get("attributes") or {})
        .get("specific_states", {})
        .get("smart_pi", {})
    ) or {}


def _parse_ts(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    return datetime.fromisoformat(str(val).replace("Z", "+00:00")).timestamp()


def _elapsed_hours(records: list[dict]) -> list[float]:
    t0 = _parse_ts(records[0]["timestamp"])
    return [(_parse_ts(r["timestamp"]) - t0) / 3600.0 for r in records]


def _get_series(records: list[dict], field: str, source: str) -> list[Any]:
    out = []
    for r in records:
        attrs = r.get("attributes") or {}
        if source == "smart_pi":
            val = _smart_pi(r).get(field)
        elif source == "attributes":
            val = attrs.get(field)
        elif source == "sim_ground_truth":
            val = (attrs.get("sim_ground_truth") or {}).get(field)
        else:
            val = None
        out.append(val)
    return out


def _extract_config(records: list[dict]) -> dict[str, Any]:
    first, last = records[0], records[-1]
    result: dict[str, Any] = {}
    for name, fn in _CONFIG_FIELDS:
        val = fn(first, _smart_pi(first))
        if val is None:
            val = fn(last, _smart_pi(last))
        result[name] = val
    return result


# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------

def save_upload(raw_bytes: bytes) -> str:
    """Save uploaded JSON bytes to a temp file; return an opaque file_id."""
    file_id = uuid.uuid4().hex
    (_TEMP_DIR / f"{file_id}.json").write_bytes(raw_bytes)
    return file_id


def load_upload(file_id: str) -> list[dict]:
    path = _TEMP_DIR / f"{file_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Upload token expired or unknown: {file_id}")
    return json.loads(path.read_bytes())


def load_run_cell(run_id: str, model: str, cell: str) -> list[dict]:
    """Load the ha_export.json for a completed run cell."""
    ha_path = RESULTS_DIR / run_id / model / cell / f"{model}_ha_export.json"
    if not ha_path.exists():
        raise FileNotFoundError(f"ha_export.json not found: {ha_path}")
    return json.loads(ha_path.read_bytes())


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def list_available_cells() -> list[dict[str, str]]:
    """Return all (run_id, model, cell) triples that have an ha_export.json."""
    cells: list[dict[str, str]] = []
    if not RESULTS_DIR.exists():
        return cells
    for run_dir in sorted(RESULTS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not run_dir.is_dir():
            continue
        for model_dir in sorted(run_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            model = model_dir.name
            for cell_dir in sorted(model_dir.iterdir()):
                if not cell_dir.is_dir():
                    continue
                if (cell_dir / f"{model}_ha_export.json").exists():
                    cells.append({
                        "run_id": run_dir.name,
                        "model": model,
                        "cell": cell_dir.name,   # "{vt_version}_{preset}"
                        "label": f"{run_dir.name[:8]} / {model} / {cell_dir.name}",
                    })
    return cells


# ---------------------------------------------------------------------------
# Core comparison
# ---------------------------------------------------------------------------

def compare(records_a: list[dict], records_b: list[dict]) -> dict[str, Any]:
    """Return structured comparison data for frontend rendering."""
    label_a = records_a[0].get("entity_id") or "A"
    label_b = records_b[0].get("entity_id") or "B"

    elapsed_a = _elapsed_hours(records_a)
    elapsed_b = _elapsed_hours(records_b)

    cfg_a = _extract_config(records_a)
    cfg_b = _extract_config(records_b)

    config_diff = [
        {
            "field": name,
            "a": cfg_a.get(name),
            "b": cfg_b.get(name),
            "match": cfg_a.get(name) == cfg_b.get(name),
        }
        for name, _ in _CONFIG_FIELDS
    ]

    series: dict[str, Any] = {}

    for field in MODE_FIELDS:
        vals_a = [str(v) if v is not None else None for v in _get_series(records_a, field, "smart_pi")]
        vals_b = [str(v) if v is not None else None for v in _get_series(records_b, field, "smart_pi")]
        series[field] = {
            "type": "categorical",
            "a": {"times_h": elapsed_a, "values": vals_a},
            "b": {"times_h": elapsed_b, "values": vals_b},
        }

    for field, source in NUMERIC_FIELDS:
        series[field] = {
            "type": "numeric",
            "a": {"times_h": elapsed_a, "values": _get_series(records_a, field, source)},
            "b": {"times_h": elapsed_b, "values": _get_series(records_b, field, source)},
        }

    return {
        "label_a": label_a,
        "label_b": label_b,
        "config_diff": config_diff,
        "series": series,
        "mode_fields": MODE_FIELDS,
        "numeric_fields": [f for f, _ in NUMERIC_FIELDS],
    }
