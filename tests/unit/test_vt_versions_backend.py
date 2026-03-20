"""Unit tests for webapp.backend.vt_versions CRUD."""
import json
import pytest
import webapp.backend.config as _cfg


@pytest.fixture
def versions_file(tmp_path, monkeypatch):
    f = tmp_path / "vt_versions.json"
    f.write_text(json.dumps({"vt_versions": []}))
    monkeypatch.setattr(_cfg, "VT_VERSIONS_FILE", f)
    return f


def test_list_empty(versions_file):
    from webapp.backend.vt_versions import list_vt_versions
    assert list_vt_versions() == []


def test_register_and_list(versions_file, tmp_path):
    from webapp.backend.vt_versions import register_vt_version, list_vt_versions
    vt_dir = tmp_path / "vt"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()
    register_vt_version("v9.1", str(vt_dir))
    versions = list_vt_versions()
    assert len(versions) == 1
    assert versions[0]["name"] == "v9.1"
    assert versions[0]["path"] == str(vt_dir)


def test_register_invalid_path_raises(versions_file, tmp_path):
    from webapp.backend.vt_versions import register_vt_version
    with pytest.raises(ValueError, match="not a valid"):
        register_vt_version("bad", str(tmp_path / "nonexistent"))


def test_register_duplicate_name_raises(versions_file, tmp_path):
    from webapp.backend.vt_versions import register_vt_version
    vt_dir = tmp_path / "vt"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()
    register_vt_version("v1", str(vt_dir))
    with pytest.raises(ValueError, match="already registered"):
        register_vt_version("v1", str(vt_dir))


def test_remove_version(versions_file, tmp_path):
    from webapp.backend.vt_versions import register_vt_version, remove_vt_version, list_vt_versions
    vt_dir = tmp_path / "vt"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()
    register_vt_version("v1", str(vt_dir))
    remove_vt_version("v1")
    assert list_vt_versions() == []


def test_remove_nonexistent_raises(versions_file):
    from webapp.backend.vt_versions import remove_vt_version
    with pytest.raises(KeyError):
        remove_vt_version("ghost")


def test_get_vt_dir(versions_file, tmp_path):
    from webapp.backend.vt_versions import register_vt_version, get_vt_dir
    vt_dir = tmp_path / "vt"
    vt_dir.mkdir()
    (vt_dir / "__init__.py").touch()
    (vt_dir / "climate.py").touch()
    register_vt_version("v1", str(vt_dir))
    assert get_vt_dir("v1") == str(vt_dir)
