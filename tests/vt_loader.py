"""Helpers for forcing VTherm imports to come from the selected checkout."""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

_VT_PREFIX = "custom_components.versatile_thermostat"


def activate_vt_checkout(project_root: Path, vt_dir: str | None = None) -> str | None:
    """Make the requested VT checkout win future imports.

    Pytest starts with the repository root on ``sys.path``, and earlier test runs may
    also leave VT modules cached in ``sys.modules``. When the worker selects another
    checkout through ``VTSIM_VT_DIR``, we must both move that checkout ahead of the
    repo root *and* drop any cached VT modules so Python does not silently reuse the
    wrong code.
    """
    for path in (str(project_root / "tests"), str(project_root)):
        if path not in sys.path:
            sys.path.insert(0, path)

    selected_vt_dir = vt_dir or os.getenv("VTSIM_VT_DIR", "")
    vt_parent: str | None = None
    if selected_vt_dir:
        vt_parent = str(Path(selected_vt_dir).resolve().parents[1])
        while vt_parent in sys.path:
            sys.path.remove(vt_parent)
        sys.path.insert(0, vt_parent)

    stale_modules = [
        name for name in tuple(sys.modules)
        if name == "custom_components"
        or name == _VT_PREFIX
        or name.startswith("custom_components.") and name.split(".", 2)[1] == "versatile_thermostat"
    ]
    for name in stale_modules:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return vt_parent


def import_vt_module(module_name: str, project_root: Path, vt_dir: str | None = None):
    """Import a VT module after activating the selected checkout."""
    activate_vt_checkout(project_root, vt_dir=vt_dir)
    return importlib.import_module(module_name)
