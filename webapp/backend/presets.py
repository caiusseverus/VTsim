"""Preset CRUD — structured VTherm parameter sets backed by webapp/presets.json."""
from __future__ import annotations
import json
from typing import Any

from . import config as _cfg

# Groups that make up a preset's parameter sections.
_GROUPS = ("control", "temperatures")


def _load() -> dict[str, Any]:
    return json.loads(_cfg.PRESETS_FILE.read_text())


def _save(data: dict[str, Any]) -> None:
    tmp = _cfg.PRESETS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_cfg.PRESETS_FILE)


def list_presets() -> list[dict[str, Any]]:
    return _load()["presets"]


def get_preset(preset_id: str) -> dict[str, Any]:
    for p in _load()["presets"]:
        if p["id"] == preset_id:
            return p
    raise KeyError(f"Preset not found: {preset_id}")


def create_preset(preset_id: str, name: str, params: dict[str, Any]) -> None:
    data = _load()
    if any(p["id"] == preset_id for p in data["presets"]):
        raise ValueError(f"Preset '{preset_id}' already exists")
    entry: dict[str, Any] = {"id": preset_id, "name": name}
    for group in _GROUPS:
        if group in params:
            entry[group] = params[group]
    data["presets"].append(entry)
    _save(data)


def update_preset(preset_id: str, name: str, params: dict[str, Any]) -> None:
    data = _load()
    for p in data["presets"]:
        if p["id"] == preset_id:
            p["name"] = name
            for group in _GROUPS:
                if group in params:
                    p[group] = params[group]
            _save(data)
            return
    raise KeyError(f"Preset not found: {preset_id}")


def delete_preset(preset_id: str) -> None:
    data = _load()
    orig = len(data["presets"])
    data["presets"] = [p for p in data["presets"] if p["id"] != preset_id]
    if len(data["presets"]) == orig:
        raise KeyError(f"Preset not found: {preset_id}")
    _save(data)


def clone_preset(source_id: str, new_id: str, new_name: str) -> None:
    """Duplicate a preset under a new id and name."""
    data = _load()
    # find source in already-loaded data (raises KeyError if not found)
    source = next((p for p in data["presets"] if p["id"] == source_id), None)
    if source is None:
        raise KeyError(f"Preset not found: {source_id}")
    if any(p["id"] == new_id for p in data["presets"]):
        raise ValueError(f"Preset '{new_id}' already exists")
    entry = {**source, "id": new_id, "name": new_name}
    data["presets"].append(entry)
    _save(data)


def flatten_preset_params(preset: dict[str, Any]) -> dict[str, Any]:
    """Flatten grouped preset params into a single dict for use as thermostat config."""
    flat: dict[str, Any] = {}
    for group in _GROUPS:
        flat.update(preset.get(group) or {})
    return flat
