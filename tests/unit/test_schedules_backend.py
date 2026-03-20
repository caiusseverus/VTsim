"""Unit tests for webapp.backend.schedules CRUD."""
import json
import pytest
import webapp.backend.config as _cfg


@pytest.fixture
def schedules_file(tmp_path, monkeypatch):
    f = tmp_path / "schedules.json"
    f.write_text(json.dumps({"schedules": []}))
    monkeypatch.setattr(_cfg, "SCHEDULES_FILE", f)
    return f


_PATTERN = {
    "id": "12h-alt",
    "name": "12h alternation",
    "type": "pattern",
    "interval_hours": 12,
    "high_temp": 20.0,
    "low_temp": 17.5,
}
_EXPLICIT = {
    "id": "custom",
    "name": "Custom",
    "type": "explicit",
    "entries": [
        {"at_hour": 0, "target_temp": 17.5},
        {"at_hour": 6, "target_temp": 20.0},
    ],
}


def test_list_empty(schedules_file):
    from webapp.backend.schedules import list_schedules
    assert list_schedules() == []


def test_create_pattern_and_list(schedules_file):
    from webapp.backend.schedules import create_schedule, list_schedules
    create_schedule(dict(_PATTERN))
    result = list_schedules()
    assert len(result) == 1
    assert result[0]["id"] == "12h-alt"
    assert result[0]["type"] == "pattern"
    assert result[0]["interval_hours"] == 12


def test_create_explicit_and_list(schedules_file):
    from webapp.backend.schedules import create_schedule, list_schedules
    create_schedule(dict(_EXPLICIT))
    result = list_schedules()
    assert len(result) == 1
    assert result[0]["type"] == "explicit"
    assert len(result[0]["entries"]) == 2


def test_get_schedule(schedules_file):
    from webapp.backend.schedules import create_schedule, get_schedule
    create_schedule(dict(_PATTERN))
    s = get_schedule("12h-alt")
    assert s["name"] == "12h alternation"


def test_get_not_found(schedules_file):
    from webapp.backend.schedules import get_schedule
    with pytest.raises(KeyError):
        get_schedule("ghost")


def test_update_schedule(schedules_file):
    from webapp.backend.schedules import create_schedule, update_schedule, get_schedule
    create_schedule(dict(_PATTERN))
    update_schedule("12h-alt", {"name": "Updated", "type": "pattern",
                                "interval_hours": 6, "high_temp": 21.0, "low_temp": 18.0})
    s = get_schedule("12h-alt")
    assert s["name"] == "Updated"
    assert s["interval_hours"] == 6


def test_update_not_found(schedules_file):
    from webapp.backend.schedules import update_schedule
    with pytest.raises(KeyError):
        update_schedule("ghost", {"name": "x", "type": "pattern",
                                  "interval_hours": 12, "high_temp": 20, "low_temp": 17})


def test_delete_schedule(schedules_file):
    from webapp.backend.schedules import create_schedule, delete_schedule, list_schedules
    create_schedule(dict(_PATTERN))
    delete_schedule("12h-alt")
    assert list_schedules() == []


def test_delete_not_found(schedules_file):
    from webapp.backend.schedules import delete_schedule
    with pytest.raises(KeyError):
        delete_schedule("ghost")


def test_duplicate_id_raises(schedules_file):
    from webapp.backend.schedules import create_schedule
    create_schedule(dict(_PATTERN))
    with pytest.raises(ValueError, match="already exists"):
        create_schedule(dict(_PATTERN))


def test_invalid_id_raises(schedules_file):
    from webapp.backend.schedules import create_schedule
    bad = dict(_PATTERN)
    bad["id"] = "-bad-id"
    with pytest.raises(ValueError, match="Invalid id"):
        create_schedule(bad)


def test_id_no_leading_trailing_hyphens(schedules_file):
    from webapp.backend.schedules import create_schedule
    for bad_id in ["-abc", "abc-", "--abc", "abc--"]:
        data = dict(_PATTERN)
        data["id"] = bad_id
        with pytest.raises(ValueError, match="Invalid id"):
            create_schedule(data)


def test_resolve_schedule_pattern(schedules_file):
    from webapp.backend.schedules import resolve_schedule
    schedule = {"type": "pattern", "interval_hours": 12, "high_temp": 20.0, "low_temp": 17.5}
    entries = resolve_schedule(schedule, 48.0)
    assert entries[0] == {"at_hour": 0.0, "target_temp": 20.0}
    assert entries[1] == {"at_hour": 12.0, "target_temp": 17.5}
    assert entries[2] == {"at_hour": 24.0, "target_temp": 20.0}
    assert entries[3] == {"at_hour": 36.0, "target_temp": 17.5}
    assert len(entries) == 4


def test_resolve_schedule_explicit(schedules_file):
    from webapp.backend.schedules import resolve_schedule
    schedule = {"type": "explicit", "entries": [
        {"at_hour": 6, "target_temp": 20.0},
        {"at_hour": 0, "target_temp": 17.5},
    ]}
    entries = resolve_schedule(schedule, 48.0)
    # Should be sorted by at_hour
    assert entries[0]["at_hour"] == 0
    assert entries[1]["at_hour"] == 6
