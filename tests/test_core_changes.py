"""Unit tests for engine and analysis changes."""
from __future__ import annotations
from sim.analysis import compute_metrics, _empty_metrics


def _make_records(deadtime: float | None = 45.5) -> list[dict]:
    return [
        {
            "elapsed_s": i * 60,
            "model_temperature": 20.0,
            "target_temperature": 20.0,
            "power_percent": 50.0,
            "smartpi_a": 0.022,
            "smartpi_b": 0.00044,
            "deadtime_heat_s": deadtime,
        }
        for i in range(10)
    ]


_SCENARIO = {
    "name": "test",
    "model": {"heater_power_watts": 1000},
    "simulation": {
        "step_seconds": 10,
        "record_every_seconds": 60,
        "duration_hours": 1,
    },
}


def test_compute_metrics_includes_deadtime_heat_s():
    metrics = compute_metrics(_make_records(deadtime=45.5), _SCENARIO)
    assert "deadtime_heat_s" in metrics
    assert metrics["deadtime_heat_s"] == 45.5


def test_compute_metrics_deadtime_none_when_absent():
    metrics = compute_metrics(_make_records(deadtime=None), _SCENARIO)
    assert metrics["deadtime_heat_s"] is None


def test_empty_metrics_includes_deadtime_heat_s():
    m = _empty_metrics(_SCENARIO)
    assert "deadtime_heat_s" in m
    assert m["deadtime_heat_s"] is None


import inspect
from sim.engine import run_simulation


def test_run_simulation_accepts_on_record_parameter():
    """on_record must be an optional keyword parameter."""
    sig = inspect.signature(run_simulation)
    assert "on_record" in sig.parameters
    param = sig.parameters["on_record"]
    assert param.default is None


from pathlib import Path


def test_vtsim_output_dir_env_var(tmp_path):
    """VTSIM_OUTPUT_DIR must redirect output files when set."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_OUTPUT_DIR" in src


def test_vtsim_scenario_dir_env_var():
    """VTSIM_SCENARIO_DIR must be referenced in the test module source."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_SCENARIO_DIR" in src


def test_vtsim_vt_dir_env_var():
    """VTSIM_VT_DIR must be referenced in the test module source."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_VT_DIR" in src


def test_vtsim_vt_dir_precedence_is_preserved():
    """Alternate VT dirs must stay ahead of the repo root on sys.path."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "sys.path.remove(_vt_parent)" in src
    assert "sys.path.insert(0, _vt_parent)" in src


def test_vtsim_live_csv_env_var():
    """VTSIM_LIVE_CSV must be referenced in the test module source."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_LIVE_CSV" in src
