import textwrap
from webapp.backend.importer import parse_ha_state


HA_STATE_YAML = textwrap.dedent("""
    min_temp: 7
    max_temp: 35
    configuration:
      cycle_min: 10
      minimal_activation_delay_sec: 0
      minimal_deactivation_delay_sec: 0
    preset_temperatures:
      eco_temp: 17.5
      comfort_temp: 20.0
      frost_temp: 10.0
      boost_temp: 25.0
    vtherm_over_switch:
      function: smart_pi
    smart_pi:
      deadtime_heat_s: 45.5
      a: 0.022
      b: 0.00044
    unknown_future_field: some_value
""")


def test_parse_ha_state_returns_three_lists():
    result = parse_ha_state(HA_STATE_YAML)
    assert "mapped" in result
    assert "unrecognised" in result
    assert "missing" in result


def test_parse_ha_state_mapped_fields():
    result = parse_ha_state(HA_STATE_YAML)
    mapped = {k: v for k, v in result["mapped"]}
    assert mapped["cycle_min"] == 10
    assert mapped["proportional_function"] == "smart_pi"
    assert mapped["eco_temp"] == 17.5
    assert mapped["comfort_temp"] == 20.0
    assert mapped["min_temp"] == 7
    assert mapped["max_temp"] == 35


def test_parse_ha_state_informational_fields():
    result = parse_ha_state(HA_STATE_YAML)
    mapped = {k: v for k, v in result["mapped"]}
    assert mapped.get("deadtime_heat_s") == 45.5
    assert mapped.get("smartpi_a") == 0.022


def test_parse_ha_state_unrecognised_contains_unknown():
    result = parse_ha_state(HA_STATE_YAML)
    unrecognised_keys = [k for k, _ in result["unrecognised"]]
    assert "unknown_future_field" in unrecognised_keys


def test_parse_ha_state_missing_has_defaults():
    result = parse_ha_state(HA_STATE_YAML)
    missing_keys = [k for k, _ in result["missing"]]
    assert "tpi_coef_int" in missing_keys
