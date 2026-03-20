# tests/test_backend/test_scenarios.py
import pytest
import yaml
from pathlib import Path
from webapp.backend.scenarios import list_scenarios, get_scenario, save_scenario, delete_scenario


def test_list_scenarios_returns_list():
    items = list_scenarios()
    assert isinstance(items, list)
    assert len(items) > 0


def test_list_scenarios_contains_name_and_description():
    items = list_scenarios()
    for item in items:
        assert "name" in item
        assert "description" in item


def test_get_scenario_returns_dict(tmp_path):
    items = list_scenarios()
    first_name = items[0]["name"]
    data = get_scenario(first_name)
    assert isinstance(data, dict)
    assert "model" in data
    assert "thermostat" in data
    assert "simulation" in data


def test_get_scenario_raises_for_unknown():
    with pytest.raises(FileNotFoundError):
        get_scenario("this_scenario_does_not_exist")


def test_save_and_delete_scenario(tmp_path, monkeypatch):
    from webapp.backend import scenarios
    monkeypatch.setattr(scenarios, "SCENARIOS_DIR", tmp_path)

    scenario_data = {
        "name": "test_scenario",
        "description": "A test",
        "model": {"model_type": "simple", "control_mode": "pwm",
                  "heater_power_watts": 1000, "heat_loss_coefficient": 50,
                  "thermal_mass": 350000, "initial_temperature": 18.0,
                  "external_temperature_fixed": 5.0},
        "thermostat": {"proportional_function": "smart_pi", "cycle_min": 15,
                       "minimal_activation_delay": 20, "minimal_deactivation_delay": 20,
                       "eco_temp": 17.5, "comfort_temp": 20.0, "min_temp": 7.0, "max_temp": 24.0},
        "simulation": {"duration_hours": 24, "step_seconds": 10, "record_every_seconds": 60},
    }
    save_scenario("test_scenario", scenario_data)
    assert (tmp_path / "test_scenario.yaml").exists()

    loaded = get_scenario("test_scenario")
    assert loaded["name"] == "test_scenario"

    delete_scenario("test_scenario")
    assert not (tmp_path / "test_scenario.yaml").exists()


def test_scenario_names_exclude_template():
    names = [s["name"] for s in list_scenarios()]
    assert "_template" not in names
