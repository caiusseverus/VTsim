"""Tests for tools/scenario_from_export.py."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SAMPLE_EXPORT = (
    _PROJECT_ROOT
    / "tests/validation/ha_exports"
    / "history_climate.sim_simple_pwm_20260317_1700_20260317_1709.json"
)
_TOOL = _PROJECT_ROOT / "tools" / "scenario_from_export.py"


@pytest.fixture
def sample_export(tmp_path):
    """Minimal single-record HA export for unit tests."""
    data = [
        {
            "entity_id": "climate.test_room",
            "state": "heat",
            "timestamp": "2026-03-17T08:00:00+00:00",
            "last_changed": "2026-03-17T08:00:00+00:00",
            "attributes": {
                "current_temperature": 19.5,
                "temperature": 20.0,
                "specific_states": {
                    "ext_current_temperature": 7.6,
                    "smart_pi": {
                        "a": 0.022,
                        "b": 0.00044,
                        "cycle_min": 10,
                    },
                },
            },
        }
    ]
    p = tmp_path / "export.json"
    p.write_text(json.dumps(data))
    return p


@pytest.fixture
def export_with_setpoint_change(tmp_path):
    """Export with a mid-run setpoint change."""
    data = [
        {
            "entity_id": "climate.test_room",
            "state": "heat",
            "timestamp": "2026-03-17T08:00:00+00:00",
            "last_changed": "2026-03-17T08:00:00+00:00",
            "attributes": {
                "current_temperature": 19.5,
                "temperature": 20.0,
                "specific_states": {"ext_current_temperature": 5.0, "smart_pi": {}},
            },
        },
        {
            "entity_id": "climate.test_room",
            "state": "heat",
            "timestamp": "2026-03-17T10:00:00+00:00",
            "last_changed": "2026-03-17T10:00:00+00:00",
            "attributes": {
                "current_temperature": 20.1,
                "temperature": 17.5,  # setpoint change
                "specific_states": {"ext_current_temperature": 5.0, "smart_pi": {}},
            },
        },
        {
            "entity_id": "climate.test_room",
            "state": "heat",
            "timestamp": "2026-03-17T16:00:00+00:00",
            "last_changed": "2026-03-17T16:00:00+00:00",
            "attributes": {
                "current_temperature": 18.0,
                "temperature": 20.0,  # back to comfort
                "specific_states": {"ext_current_temperature": 5.0, "smart_pi": {}},
            },
        },
    ]
    p = tmp_path / "export_with_changes.json"
    p.write_text(json.dumps(data))
    return p


def _run_tool(export_path, output_path, name="test_scenario"):
    result = subprocess.run(
        [
            sys.executable, str(_TOOL),
            str(export_path),
            "--output", str(output_path),
            "--name", name,
        ],
        capture_output=True, text=True,
    )
    return result


def test_tool_creates_valid_yaml(sample_export, tmp_path):
    """Tool exits 0 and produces a parseable YAML file."""
    out = tmp_path / "scenario.yaml"
    result = _run_tool(sample_export, out)
    assert result.returncode == 0, f"Tool failed:\n{result.stderr}"
    assert out.exists()
    import yaml
    data = yaml.safe_load(out.read_text())
    assert isinstance(data, dict)
    assert "model" in data
    assert "thermostat" in data
    assert "sensor" in data
    assert "disturbances" in data
    assert "simulation" in data


def test_tool_extracts_initial_temperature(sample_export, tmp_path):
    """initial_temperature is set from first record's current_temperature."""
    out = tmp_path / "scenario.yaml"
    _run_tool(sample_export, out)
    import yaml
    data = yaml.safe_load(out.read_text())
    assert data["model"]["initial_temperature"] == pytest.approx(19.5)


def test_tool_extracts_external_temperature(sample_export, tmp_path):
    """external_temperature_fixed is set from first record's ext_current_temperature."""
    out = tmp_path / "scenario.yaml"
    _run_tool(sample_export, out)
    import yaml
    data = yaml.safe_load(out.read_text())
    assert data["model"]["external_temperature_fixed"] == pytest.approx(7.6)


def test_tool_extracts_smart_pi_algorithm(sample_export, tmp_path):
    """proportional_function is smart_pi when smart_pi attributes are present."""
    out = tmp_path / "scenario.yaml"
    _run_tool(sample_export, out)
    import yaml
    data = yaml.safe_load(out.read_text())
    assert data["thermostat"]["proportional_function"] == "smart_pi"


def test_tool_extracts_cycle_min(sample_export, tmp_path):
    """cycle_min is extracted from smart_pi.cycle_min."""
    out = tmp_path / "scenario.yaml"
    _run_tool(sample_export, out)
    import yaml
    data = yaml.safe_load(out.read_text())
    assert data["thermostat"]["cycle_min"] == 10


def test_tool_detects_setpoint_changes(export_with_setpoint_change, tmp_path):
    """Schedule entries are generated for each setpoint change."""
    out = tmp_path / "scenario.yaml"
    _run_tool(export_with_setpoint_change, out)
    import yaml
    data = yaml.safe_load(out.read_text())
    schedule = data["simulation"]["schedule"]
    temps = [e["target_temp"] for e in schedule]
    assert 20.0 in temps
    assert 17.5 in temps


def test_tool_sets_duration_from_window(export_with_setpoint_change, tmp_path):
    """duration_hours is set from export time window (8h window → 8.0h)."""
    out = tmp_path / "scenario.yaml"
    _run_tool(export_with_setpoint_change, out)
    import yaml
    data = yaml.safe_load(out.read_text())
    # 08:00 → 16:00 = 8 hours
    assert data["simulation"]["duration_hours"] == pytest.approx(8.0, abs=0.5)


def test_tool_preserves_template_comments(sample_export, tmp_path):
    """Output file contains comments from the template (not stripped by PyYAML)."""
    out = tmp_path / "scenario.yaml"
    _run_tool(sample_export, out)
    content = out.read_text()
    # Template has comments like "# W — nominal heater output at 100%"
    assert "heater_power_watts" in content
    assert "#" in content  # at least some comments preserved


def test_tool_on_real_sample():
    """Smoke test on the actual sample export."""
    if not _SAMPLE_EXPORT.exists():
        pytest.skip("sample export not present")
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir) / "scenario.yaml"
        result = _run_tool(_SAMPLE_EXPORT, out, name="test_from_real_sample")
        assert result.returncode == 0, f"Tool failed:\n{result.stderr}"
        assert out.exists()
