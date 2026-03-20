# tests/test_backend/test_versions.py
import json
import pytest
from pathlib import Path
from webapp.backend.versions import (
    list_versions, register_version, remove_version,
    add_config, update_config, remove_config, get_vt_dir,
)


@pytest.fixture
def versions_file(tmp_path, monkeypatch):
    """Redirect versions.json to a temp file."""
    from webapp.backend import config
    vf = tmp_path / "versions.json"
    vf.write_text('{"versions": []}')
    monkeypatch.setattr(config, "VERSIONS_FILE", vf)
    return vf


def test_list_versions_empty(versions_file):
    assert list_versions() == []


def test_register_version(tmp_path, versions_file):
    vt_dir = tmp_path / "versatile_thermostat"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()

    register_version("v9.1.0", str(vt_dir))
    versions = list_versions()
    assert len(versions) == 1
    assert versions[0]["name"] == "v9.1.0"
    assert versions[0]["configs"] == []


def test_register_version_invalid_path(tmp_path, versions_file):
    with pytest.raises(ValueError, match="not a valid"):
        register_version("bad", str(tmp_path / "nonexistent"))


def test_add_and_remove_config(tmp_path, versions_file):
    vt_dir = tmp_path / "vt"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()
    register_version("v9", str(vt_dir))

    add_config("v9", "cycle_10", {"cycle_min": 10})
    versions = list_versions()
    configs = versions[0]["configs"]
    assert len(configs) == 1
    assert configs[0]["name"] == "cycle_10"
    assert configs[0]["overrides"]["cycle_min"] == 10

    remove_config("v9", "cycle_10")
    assert list_versions()[0]["configs"] == []


def test_remove_version(tmp_path, versions_file):
    vt_dir = tmp_path / "vt"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()
    register_version("v9", str(vt_dir))
    remove_version("v9")
    assert list_versions() == []


def test_get_vt_dir(tmp_path, versions_file):
    vt_dir = tmp_path / "vt"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()
    register_version("v9", str(vt_dir))
    assert get_vt_dir("v9") == str(vt_dir)
