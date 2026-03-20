"""Unit tests for webapp.backend.models CRUD."""
import pytest
from pathlib import Path
from ruamel.yaml import YAML

import webapp.backend.config as _cfg


@pytest.fixture
def models_dir(tmp_path, monkeypatch):
    d = tmp_path / "models"
    d.mkdir()
    monkeypatch.setattr(_cfg, "MODELS_DIR", d)
    return d


def _write_model(models_dir: Path, slug: str, data: dict) -> None:
    _yaml = YAML()
    p = models_dir / f"{slug}.yaml"
    with p.open("w") as f:
        _yaml.dump(data, f)


def test_list_models_empty(models_dir):
    from webapp.backend.models import list_models
    assert list_models() == []


def test_list_models_returns_summaries(models_dir):
    from webapp.backend.models import list_models
    _write_model(models_dir, "room_a", {
        "name": "Room A", "description": "test",
        "model": {"model_type": "r2c2"}, "simulation": {"duration_hours": 24}
    })
    result = list_models()
    assert len(result) == 1
    assert result[0]["slug"] == "room_a"
    assert result[0]["model_type"] == "r2c2"
    assert result[0]["duration_hours"] == 24


def test_get_model_returns_full_data(models_dir):
    from webapp.backend.models import get_model
    _write_model(models_dir, "room_b", {"name": "Room B", "model": {"model_type": "simple"}, "simulation": {}})
    data = get_model("room_b")
    assert data["name"] == "Room B"


def test_get_model_not_found(models_dir):
    from webapp.backend.models import get_model
    with pytest.raises(FileNotFoundError):
        get_model("nonexistent")


def test_save_and_delete_model(models_dir):
    from webapp.backend.models import save_model, delete_model, get_model
    save_model("new_room", {"name": "New Room", "model": {}, "simulation": {}})
    assert get_model("new_room")["name"] == "New Room"
    delete_model("new_room")
    with pytest.raises(FileNotFoundError):
        get_model("new_room")


def test_clone_model(models_dir):
    from webapp.backend.models import clone_model, get_model
    _write_model(models_dir, "src", {"name": "Source", "model": {}, "simulation": {}})
    clone_model("src", "dst")
    assert get_model("dst")["name"] == "dst"


def test_template_files_excluded(models_dir):
    from webapp.backend.models import list_models
    _write_model(models_dir, "_template", {"name": "Template", "model": {}, "simulation": {}})
    assert list_models() == []
