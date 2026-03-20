"""Heating simulator path configuration backed by webapp/heating_sim.json."""
from __future__ import annotations

import json
from pathlib import Path

from . import config as _cfg


def _load() -> dict:
    return json.loads(_cfg.HEATING_SIM_FILE.read_text())


def _save(data: dict) -> None:
    tmp = _cfg.HEATING_SIM_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_cfg.HEATING_SIM_FILE)


def get_path() -> str:
    return _load().get("path", "")


def set_path(path: str) -> None:
    _validate(path)
    _save({"path": path})


def _validate(path_str: str) -> None:
    p = Path(path_str)
    if not p.is_dir() or not (p / "thermal_model.py").exists():
        raise ValueError(
            f"'{path_str}' is not a valid heating_simulator directory "
            "(must contain thermal_model.py)"
        )


def get_dir() -> str:
    """Return the configured heating sim dir, or raise ValueError if not set."""
    path = get_path()
    if not path:
        raise ValueError("Heating simulator directory not configured")
    return path
