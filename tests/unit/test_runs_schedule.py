"""Tests for schedule_id integration in runs.py create_run."""
import pytest


def test_create_run_stores_schedule_id(tmp_path, monkeypatch):
    import webapp.backend.config as _cfg
    import json

    # Set up temp dirs
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(_cfg, "RUNS_DIR", runs_dir)

    # Set up a model
    from ruamel.yaml import YAML
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(_cfg, "MODELS_DIR", models_dir)
    yaml = YAML()
    model_yaml = models_dir / "test-model.yaml"
    with model_yaml.open("w") as f:
        yaml.dump({"name": "Test Model", "model": {"model_type": "simple"},
                   "simulation": {"duration_hours": 48, "step_seconds": 10,
                                  "record_every_seconds": 60, "initial_hvac_mode": "heat",
                                  "initial_preset_mode": "eco"}}, f)

    # Set up a preset
    presets_file = tmp_path / "presets.json"
    presets_file.write_text(json.dumps({"presets": [{
        "id": "test-preset", "name": "Test",
        "control": {}, "temperatures": {"eco_temp": 17.5, "comfort_temp": 20.0}
    }]}))
    monkeypatch.setattr(_cfg, "PRESETS_FILE", presets_file)

    # Set up a schedule
    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text(json.dumps({"schedules": [{
        "id": "test-sched", "name": "Test", "type": "pattern",
        "interval_hours": 12, "high_temp": 20.0, "low_temp": 17.5
    }]}))
    monkeypatch.setattr(_cfg, "SCHEDULES_FILE", schedules_file)

    # Set up vt_versions
    vt_versions_file = tmp_path / "vt_versions.json"
    vt_versions_file.write_text(json.dumps({"vt_versions": [{"name": "test-v", "path": "/some/path"}]}))
    monkeypatch.setattr(_cfg, "VT_VERSIONS_FILE", vt_versions_file)

    from webapp.backend.runs import create_run
    run_id = create_run(
        name="test run",
        model_names=["test-model"],
        version_names=["test-v"],
        preset_ids=["test-preset"],
        schedule_id="test-sched",
    )

    run_file = runs_dir / f"{run_id}.json"
    run = json.loads(run_file.read_text())
    assert run["schedule_id"] == "test-sched"
    # schedule_id is at top level, not per-cell
    assert "schedule_id" not in run["cells"][0]


def test_create_run_invalid_schedule_raises(tmp_path, monkeypatch):
    import webapp.backend.config as _cfg
    import json

    runs_dir = tmp_path / "runs"
    monkeypatch.setattr(_cfg, "RUNS_DIR", runs_dir)

    from ruamel.yaml import YAML
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    monkeypatch.setattr(_cfg, "MODELS_DIR", models_dir)
    yaml = YAML()
    model_yaml = models_dir / "test-model.yaml"
    with model_yaml.open("w") as f:
        yaml.dump({"name": "Test", "model": {"model_type": "simple"},
                   "simulation": {"duration_hours": 48}}, f)

    presets_file = tmp_path / "presets.json"
    presets_file.write_text(json.dumps({"presets": [{
        "id": "p1", "name": "P", "control": {}, "temperatures": {}
    }]}))
    monkeypatch.setattr(_cfg, "PRESETS_FILE", presets_file)

    schedules_file = tmp_path / "schedules.json"
    schedules_file.write_text(json.dumps({"schedules": []}))
    monkeypatch.setattr(_cfg, "SCHEDULES_FILE", schedules_file)

    vt_versions_file = tmp_path / "vt_versions.json"
    vt_versions_file.write_text(json.dumps({"vt_versions": [{"name": "v1", "path": "/x"}]}))
    monkeypatch.setattr(_cfg, "VT_VERSIONS_FILE", vt_versions_file)

    from webapp.backend.runs import create_run
    with pytest.raises(KeyError):
        create_run(name="r", model_names=["test-model"], version_names=["v1"],
                   preset_ids=["p1"], schedule_id="no-such-schedule")
