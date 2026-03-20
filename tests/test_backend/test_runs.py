# tests/test_backend/test_runs.py
import json
import pytest
from pathlib import Path
from webapp.backend.runs import (
    create_run, get_run, list_runs, delete_run,
    build_worker_scenario_yaml, _merge_vt_config,
)


@pytest.fixture
def runs_dir(tmp_path, monkeypatch):
    from webapp.backend import config
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    return tmp_path


def test_create_run_returns_id(runs_dir):
    run_id = create_run(
        name="test_run",
        scenario_names=["pwm_simple"],
        version_configs=[{"version": "v9", "config": "default", "vt_dir": "/tmp/vt",
                          "overrides": {}}],
    )
    assert isinstance(run_id, str)
    assert len(run_id) > 0


def test_get_run_returns_metadata(runs_dir):
    run_id = create_run(
        name="r1",
        scenario_names=["s1"],
        version_configs=[{"version": "v1", "config": "c1", "vt_dir": "/t", "overrides": {}}],
    )
    run = get_run(run_id)
    assert run["id"] == run_id
    assert run["name"] == "r1"
    assert run["status"] in ("pending", "running", "complete", "partial_failure")


def test_list_runs_returns_all(runs_dir):
    create_run("r1", ["s1"], [{"version": "v1", "config": "c1", "vt_dir": "/t", "overrides": {}}])
    create_run("r2", ["s2"], [{"version": "v1", "config": "c1", "vt_dir": "/t", "overrides": {}}])
    runs = list_runs()
    assert len(runs) >= 2


def test_delete_run(runs_dir):
    run_id = create_run("r1", ["s1"],
                        [{"version": "v1", "config": "c1", "vt_dir": "/t", "overrides": {}}])
    delete_run(run_id)
    with pytest.raises(FileNotFoundError):
        get_run(run_id)


def test_merge_vt_config_applies_overrides():
    base = {"cycle_min": 15, "eco_temp": 17.5}
    scenario_thermostat = {"cycle_min": 10}
    overrides = {"eco_temp": 18.0}
    merged = _merge_vt_config(base, scenario_thermostat, overrides)
    assert merged["cycle_min"] == 10  # scenario wins over base
    assert merged["eco_temp"] == 18.0  # override wins over scenario


def test_build_worker_scenario_yaml(tmp_path):
    scenario_data = {
        "name": "pwm_simple",
        "thermostat": {"cycle_min": 15},
        "model": {},
        "simulation": {},
    }
    overrides = {"cycle_min": 10}
    yaml_path = build_worker_scenario_yaml(
        scenario_data=scenario_data,
        overrides=overrides,
        dest_dir=tmp_path,
    )
    assert yaml_path.exists()
    from ruamel.yaml import YAML
    _yaml = YAML()
    loaded = _yaml.load(yaml_path.read_text())
    assert loaded["thermostat"]["cycle_min"] == 10
