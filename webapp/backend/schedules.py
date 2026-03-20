"""Schedule CRUD — reusable setpoint schedule presets backed by webapp/schedules.json."""
from __future__ import annotations
import json
import re
from typing import Any

from . import config as _cfg

_ID_RE = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$')


def _load() -> dict[str, Any]:
    try:
        return json.loads(_cfg.SCHEDULES_FILE.read_text())
    except FileNotFoundError:
        return {"schedules": []}


def _save(data: dict[str, Any]) -> None:
    tmp = _cfg.SCHEDULES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(_cfg.SCHEDULES_FILE)


def _validate_id(id_val: str) -> None:
    if not _ID_RE.match(id_val) or len(id_val) > 60:
        raise ValueError(f"Invalid id '{id_val}': must match [a-z0-9]([a-z0-9-]*[a-z0-9])?, max 60 chars")


def list_schedules() -> list[dict[str, Any]]:
    return _load()["schedules"]


def get_schedule(schedule_id: str) -> dict[str, Any]:
    for s in _load()["schedules"]:
        if s["id"] == schedule_id:
            return s
    raise KeyError(f"Schedule not found: {schedule_id}")


def create_schedule(data: dict[str, Any]) -> None:
    """Create a schedule from a flat data dict (includes id, name, type, and type-specific fields)."""
    _validate_id(data.get("id", ""))
    db = _load()
    if any(s["id"] == data["id"] for s in db["schedules"]):
        raise ValueError(f"Schedule '{data['id']}' already exists")
    db["schedules"].append(data)
    _save(db)


def update_schedule(schedule_id: str, data: dict[str, Any]) -> None:
    """Update a schedule's fields (id not changed). data excludes id."""
    db = _load()
    for s in db["schedules"]:
        if s["id"] == schedule_id:
            for k, v in data.items():
                s[k] = v
            _save(db)
            return
    raise KeyError(f"Schedule not found: {schedule_id}")


def delete_schedule(schedule_id: str) -> None:
    db = _load()
    orig = len(db["schedules"])
    db["schedules"] = [s for s in db["schedules"] if s["id"] != schedule_id]
    if len(db["schedules"]) == orig:
        raise KeyError(f"Schedule not found: {schedule_id}")
    _save(db)


def resolve_schedule(schedule: dict[str, Any], duration_hours: float) -> list[dict[str, Any]]:
    """Expand a schedule dict into a concrete list of {at_hour, target_temp} entries."""
    if schedule["type"] == "explicit":
        return sorted(
            [{"at_hour": float(e["at_hour"]), "target_temp": float(e["target_temp"])}
             for e in schedule["entries"]],
            key=lambda e: e["at_hour"],
        )
    # pattern
    interval = float(schedule["interval_hours"])
    high = float(schedule["high_temp"])
    low = float(schedule["low_temp"])
    entries = []
    t = 0.0
    i = 0
    while t < duration_hours:
        entries.append({"at_hour": t, "target_temp": high if i % 2 == 0 else low})
        t += interval
        i += 1
    return entries
