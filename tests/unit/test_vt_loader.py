from __future__ import annotations

import sys
from pathlib import Path

from vt_loader import activate_vt_checkout, import_vt_module


def _make_vt_checkout(base: Path, marker: str) -> Path:
    vt_dir = base / marker / "custom_components" / "versatile_thermostat"
    vt_dir.mkdir(parents=True)
    (vt_dir.parent / "__init__.py").write_text("")
    (vt_dir / "__init__.py").write_text(f'MARKER = "{marker}"\n')
    (vt_dir / "vtherm_api.py").write_text(
        f'class VersatileThermostatAPI:\n    marker = "{marker}"\n'
    )
    (vt_dir / "climate.py").write_text("")
    return vt_dir


def test_activate_vt_checkout_moves_selected_checkout_to_front(tmp_path):
    project_root = tmp_path / "repo"
    (project_root / "tests").mkdir(parents=True)
    local_vt_dir = _make_vt_checkout(project_root, "local")
    alt_vt_dir = _make_vt_checkout(tmp_path, "alt")

    sys.path.insert(0, str(project_root))
    import_vt_module("custom_components.versatile_thermostat", project_root, vt_dir=str(local_vt_dir))

    vt_parent = activate_vt_checkout(project_root, vt_dir=str(alt_vt_dir))

    assert vt_parent == str(alt_vt_dir.resolve().parents[1])
    assert sys.path[0] == vt_parent


def test_import_vt_module_reloads_from_new_checkout(tmp_path):
    project_root = tmp_path / "repo"
    (project_root / "tests").mkdir(parents=True)
    local_vt_dir = _make_vt_checkout(project_root, "local")
    alt_vt_dir = _make_vt_checkout(tmp_path, "alt")

    local_mod = import_vt_module(
        "custom_components.versatile_thermostat.vtherm_api",
        project_root,
        vt_dir=str(local_vt_dir),
    )
    assert local_mod.VersatileThermostatAPI.marker == "local"

    alt_mod = import_vt_module(
        "custom_components.versatile_thermostat.vtherm_api",
        project_root,
        vt_dir=str(alt_vt_dir),
    )
    assert alt_mod.VersatileThermostatAPI.marker == "alt"
