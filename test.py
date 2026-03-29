import csv

BASELINE = "results/unblocked.csv"
SUPPRESSED = "results/blocked.csv"

def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def to_bool(v):
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true", "1"}:
        return True
    if s in {"false", "0"}:
        return False
    return None

def load_rows(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            err = to_float(row.get("smartpi_error"))
            if err is None or abs(err) > 0.06:
                continue
            rows.append(row)
    return rows

def mean(vals):
    vals = [v for v in vals if v is not None]
    return (sum(vals) / len(vals)) if vals else None

def maxv(vals):
    vals = [v for v in vals if v is not None]
    return max(vals) if vals else None
def summarize(rows):
    out = {}
    out["rows_near_zero_error"] = len(rows)
    out["deadband_true_rows"] = sum(1 for r in rows if to_bool(r.get("smartpi_in_deadband")) is True)
    out["deadband_true_share"] = (
        out["deadband_true_rows"] / len(rows) if rows else None
    )
    out["mean_abs_error"] = mean(abs(to_float(r.get("smartpi_error"))) for r in rows)
    out["mean_switch_state"] = mean(to_float(r.get("switch_state")) for r in rows)
    out["mean_cycle_elapsed_sec"] = mean(to_float(r.get("cycle_debug_cycle_elapsed_sec")) for r in rows)
    out["max_restart_temp_sensor"] = maxv(to_float(r.get("cycle_debug_restart_count_temp_sensor")) for r in rows)
    out["max_suppressed_restart_temp_sensor"] = maxv(
        to_float(r.get("cycle_debug_suppressed_restart_count_temp_sensor")) for r in rows
    )
    out["mean_on_percent"] = mean(to_float(r.get("on_percent")) for r in rows)
    out["heating_rows"] = sum(1 for r in rows if str(r.get("hvac_action", "")).strip().lower() == "heating")
    out["idle_rows"] = sum(1 for r in rows if str(r.get("hvac_action", "")).strip().lower() == "idle")
    return out
base = summarize(load_rows(BASELINE))
supp = summarize(load_rows(SUPPRESSED))

keys = [
    "rows_near_zero_error",
    "deadband_true_rows",
    "deadband_true_share",
    "mean_abs_error",
    "mean_switch_state",
    "mean_cycle_elapsed_sec",
    "max_restart_temp_sensor",
    "max_suppressed_restart_temp_sensor",
    "mean_on_percent",
    "heating_rows",
    "idle_rows",
]

print(f"{'metric':35} {'baseline':>14} {'suppressed':>14} {'delta':>14}")
for k in keys:
    b = base.get(k)
    s = supp.get(k)
    d = (s - b) if isinstance(b, (int, float)) and isinstance(s, (int, float)) else None
    print(f"{k:35} {str(b):>14} {str(s):>14} {str(d):>14}")
