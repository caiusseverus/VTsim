"""VT version registry backed by webapp/vt_versions.json."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from . import config as _cfg


def _load() -> dict[str, Any]:
    return json.loads(_cfg.VT_VERSIONS_FILE.read_text())


def _save(data: dict[str, Any]) -> None:
    tmp = _cfg.VT_VERSIONS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_cfg.VT_VERSIONS_FILE)


def list_vt_versions() -> list[dict[str, Any]]:
    return _load()["vt_versions"]


def _validate_path(path_str: str) -> None:
    p = Path(path_str)
    if not p.is_dir() or not (p / "__init__.py").exists() or not (p / "climate.py").exists():
        raise ValueError(
            f"'{path_str}' is not a valid versatile_thermostat directory "
            "(must contain __init__.py and climate.py)"
        )


def register_vt_version(name: str, path: str) -> None:
    _validate_path(path)
    data = _load()
    if any(v["name"] == name for v in data["vt_versions"]):
        raise ValueError(f"Version '{name}' already registered")
    data["vt_versions"].append({"name": name, "path": path})
    _save(data)


def remove_vt_version(name: str) -> None:
    data = _load()
    orig = len(data["vt_versions"])
    data["vt_versions"] = [v for v in data["vt_versions"] if v["name"] != name]
    if len(data["vt_versions"]) == orig:
        raise KeyError(f"VT version not found: {name}")
    _save(data)


def get_vt_dir(name: str) -> str:
    data = _load()
    for v in data["vt_versions"]:
        if v["name"] == name:
            return v["path"]
    raise KeyError(f"VT version not found: {name}")
