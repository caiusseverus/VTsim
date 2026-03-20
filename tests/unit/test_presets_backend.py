"""Unit tests for webapp.backend.presets CRUD."""
import json
import pytest
import webapp.backend.config as _cfg


@pytest.fixture
def presets_file(tmp_path, monkeypatch):
    f = tmp_path / "presets.json"
    f.write_text(json.dumps({"presets": []}))
    monkeypatch.setattr(_cfg, "PRESETS_FILE", f)
    return f


def test_list_empty(presets_file):
    from webapp.backend.presets import list_presets
    assert list_presets() == []


def test_create_and_list(presets_file):
    from webapp.backend.presets import create_preset, list_presets
    create_preset("sp1", "SmartPI Default", {
        "control": {"proportional_function": "smart_pi", "cycle_min": 15},
        "temperatures": {"eco_temp": 17.5, "comfort_temp": 20.0}
    })
    presets = list_presets()
    assert len(presets) == 1
    assert presets[0]["id"] == "sp1"
    assert presets[0]["name"] == "SmartPI Default"


def test_get_preset(presets_file):
    from webapp.backend.presets import create_preset, get_preset
    create_preset("p1", "Test", {"control": {}, "temperatures": {}})
    p = get_preset("p1")
    assert p["name"] == "Test"


def test_get_preset_not_found(presets_file):
    from webapp.backend.presets import get_preset
    with pytest.raises(KeyError):
        get_preset("ghost")


def test_update_preset(presets_file):
    from webapp.backend.presets import create_preset, update_preset, get_preset
    create_preset("p1", "Old Name", {"control": {}, "temperatures": {}})
    update_preset("p1", "New Name", {"control": {"cycle_min": 10}, "temperatures": {}})
    assert get_preset("p1")["name"] == "New Name"
    assert get_preset("p1")["control"]["cycle_min"] == 10


def test_delete_preset(presets_file):
    from webapp.backend.presets import create_preset, delete_preset, list_presets
    create_preset("p1", "Test", {"control": {}, "temperatures": {}})
    delete_preset("p1")
    assert list_presets() == []


def test_flatten_preset(presets_file):
    from webapp.backend.presets import flatten_preset_params
    preset = {
        "control": {"proportional_function": "smart_pi", "cycle_min": 15},
        "temperatures": {"eco_temp": 17.5, "comfort_temp": 20.0},
    }
    flat = flatten_preset_params(preset)
    assert flat["proportional_function"] == "smart_pi"
    assert flat["eco_temp"] == 17.5
    assert flat["cycle_min"] == 15


def test_duplicate_id_raises(presets_file):
    from webapp.backend.presets import create_preset
    create_preset("p1", "Test", {})
    with pytest.raises(ValueError, match="already exists"):
        create_preset("p1", "Test2", {})


def test_clone_preset(presets_file):
    from webapp.backend.presets import create_preset, clone_preset, list_presets
    create_preset("orig", "Original", {"control": {"cycle_min": 10}, "temperatures": {"eco_temp": 17.5}})
    clone_preset("orig", "copy", "Copy")
    presets = list_presets()
    assert len(presets) == 2
    copy = next(p for p in presets if p["id"] == "copy")
    assert copy["name"] == "Copy"
    assert copy["control"]["cycle_min"] == 10
    assert copy["temperatures"]["eco_temp"] == 17.5

def test_clone_preset_not_found(presets_file):
    from webapp.backend.presets import clone_preset
    with pytest.raises(KeyError):
        clone_preset("nope", "new", "New")

def test_clone_preset_duplicate_id(presets_file):
    from webapp.backend.presets import create_preset, clone_preset
    create_preset("p1", "P1", {"control": {}, "temperatures": {}})
    create_preset("p2", "P2", {"control": {}, "temperatures": {}})
    with pytest.raises(ValueError):
        clone_preset("p1", "p2", "Conflict")
