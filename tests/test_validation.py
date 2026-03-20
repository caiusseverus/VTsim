import csv
import subprocess
import tempfile
from pathlib import Path
import sys

import pytest

from validation.ha_parser import load_ha_export, compute_settled_metrics

# conftest.py adds tests/ to sys.path only inside a session-scoped fixture,
# which fires too late for module-level imports.  This block ensures the path
# is set before the import below, both under pytest and direct script execution.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_PROJECT_ROOT), str(_PROJECT_ROOT / "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from sim.analysis import write_records_csv


def test_write_records_csv_creates_file_with_expected_columns():
    records = [
        {"elapsed_s": 0.0, "elapsed_h": 0.0, "model_temperature": 18.0,
         "target_temperature": 20.0, "power_percent": 100.0, "smartpi_a": None, "smartpi_b": None},
        {"elapsed_s": 60.0, "elapsed_h": 1/60, "model_temperature": 18.5,
         "target_temperature": 20.0, "power_percent": 80.0, "smartpi_a": 0.02, "smartpi_b": 0.0004},
    ]
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_records.csv"
        write_records_csv(records, path)
        assert path.exists()
        with path.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["smartpi_a"] == ""  # None serialised as empty string
        assert "elapsed_s" in rows[0]
        assert "model_temperature" in rows[0]
        assert float(rows[1]["smartpi_a"]) == pytest.approx(0.02)


def test_write_records_csv_empty_is_noop():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "empty.csv"
        write_records_csv([], path)
        assert not path.exists()


def test_load_ha_export_returns_dataframe():
    sample = Path(_PROJECT_ROOT) / "tests/validation/ha_exports" / \
        "history_climate.sim_simple_pwm_20260317_1700_20260317_1709.json"
    if not sample.exists():
        pytest.skip("sample export not present")
    df = load_ha_export(sample)
    assert not df.empty
    assert "elapsed_s" in df.columns
    assert "current_temperature" in df.columns
    assert "power_percent" in df.columns
    assert "smartpi_a" in df.columns
    assert "smartpi_b" in df.columns
    assert df["elapsed_s"].iloc[0] == pytest.approx(0.0)
    assert df["elapsed_s"].iloc[-1] > 0


def test_load_ha_export_extracts_nested_fields():
    sample = Path(_PROJECT_ROOT) / "tests/validation/ha_exports" / \
        "history_climate.sim_simple_pwm_20260317_1700_20260317_1709.json"
    if not sample.exists():
        pytest.skip("sample export not present")
    df = load_ha_export(sample)
    # The sample export has SmartPI a ≈ 0.022134 and b ≈ 0.000439
    assert df["smartpi_a"].notna().any()
    assert df["smartpi_b"].notna().any()
    assert df["smartpi_a"].dropna().iloc[0] == pytest.approx(0.022134, abs=1e-4)


def test_compute_settled_metrics_last_20_percent():
    import pandas as pd
    import numpy as np
    n = 100
    df = pd.DataFrame({
        "elapsed_s": np.linspace(0, 3600, n),
        "current_temperature": np.linspace(18.0, 20.0, n),
        "target_temperature": [20.0] * n,
        "power_percent": [50.0] * n,
        "smartpi_a": [0.02] * 50 + [0.022] * 50,
        "smartpi_b": [0.0004] * 50 + [0.00044] * 50,
    })
    metrics = compute_settled_metrics(df)
    assert metrics["settled_a"] == pytest.approx(0.022, abs=1e-4)
    assert metrics["settled_b"] == pytest.approx(0.00044, abs=1e-6)
    assert "steady_state_error_c" in metrics
    assert "mean_power_percent" in metrics


def test_compare_script_runs_on_sample_data(tmp_path):
    """Smoke test: compare.py exits 0 and writes a PNG."""
    sample_export = Path(_PROJECT_ROOT) / "tests/validation/ha_exports" / \
        "history_climate.sim_simple_pwm_20260317_1700_20260317_1709.json"
    records_csv = Path(_PROJECT_ROOT) / "results" / "validation_sim_simple_pwm_records.csv"
    if not sample_export.exists():
        pytest.skip("sample export not present")
    if not records_csv.exists():
        pytest.skip("validation_sim_simple_pwm_records.csv not present — run pytest test_vt_scenarios first")
    out_dir = tmp_path / "validation"
    result = subprocess.run(
        [
            sys.executable, str(Path(_PROJECT_ROOT) / "tests/validation/compare.py"),
            str(sample_export),
            "validation_sim_simple_pwm",
            "--results-dir", str(Path(_PROJECT_ROOT) / "results"),
            "--output-dir", str(out_dir),
        ],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"compare.py failed:\n{result.stderr}"
    expected_png = out_dir / "validation_sim_simple_pwm_vs_ha.png"
    assert expected_png.exists(), f"Expected PNG not written: {expected_png}"
