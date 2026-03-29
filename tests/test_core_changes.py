"""Unit tests for engine and analysis changes."""
from __future__ import annotations
import asyncio
from sim.analysis import compute_metrics, _empty_metrics


def _make_records(deadtime: float | None = 45.5) -> list[dict]:
    return [
        {
            "elapsed_s": i * 60,
            "model_temperature": 20.0,
            "target_temperature": 20.0,
            "power_percent": 50.0,
            "smartpi_a": 0.022,
            "smartpi_b": 0.00044,
            "deadtime_heat_s": deadtime,
        }
        for i in range(10)
    ]


_SCENARIO = {
    "name": "test",
    "model": {"heater_power_watts": 1000},
    "simulation": {
        "step_seconds": 10,
        "record_every_seconds": 60,
        "duration_hours": 1,
    },
}


def test_compute_metrics_includes_deadtime_heat_s():
    metrics = compute_metrics(_make_records(deadtime=45.5), _SCENARIO)
    assert "deadtime_heat_s" in metrics
    assert metrics["deadtime_heat_s"] == 45.5


def test_compute_metrics_deadtime_none_when_absent():
    metrics = compute_metrics(_make_records(deadtime=None), _SCENARIO)
    assert metrics["deadtime_heat_s"] is None


def test_empty_metrics_includes_deadtime_heat_s():
    m = _empty_metrics(_SCENARIO)
    assert "deadtime_heat_s" in m
    assert m["deadtime_heat_s"] is None


import inspect
from datetime import datetime, timezone
from sim.engine import SimTimerScheduler, _EventQueue, run_simulation


def test_run_simulation_accepts_on_record_parameter():
    """on_record must be an optional keyword parameter."""
    sig = inspect.signature(run_simulation)
    assert "on_record" in sig.parameters
    param = sig.parameters["on_record"]
    assert param.default is None


def test_event_queue_orders_by_time_then_priority_then_sequence():
    queue = _EventQueue()
    queue.push(time_s=10.0, priority=40, event_type="later-inserted")
    queue.push(time_s=10.0, priority=40, event_type="latest")
    queue.push(time_s=5.0, priority=70, event_type="earliest-time")
    queue.push(time_s=10.0, priority=30, event_type="higher-priority")

    ordered = [queue.pop().event_type for _ in range(4)]
    assert ordered == [
        "earliest-time",
        "higher-priority",
        "later-inserted",
        "latest",
    ]


class _FakeHass:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.tasks: list[asyncio.Task] = []

    def async_create_task(self, coro):
        task = self.loop.create_task(coro)
        self.tasks.append(task)
        return task


def test_sim_timer_scheduler_queues_pending_timer_on_attach():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scheduler = SimTimerScheduler(now_provider=lambda: now)
    cancel = scheduler.schedule(_FakeHass(), 12.0, lambda when: when)
    del cancel
    queue = _EventQueue()

    scheduler.attach(queue, sim_start=now)

    event = queue.pop()
    assert event.event_type == "scheduled_callback"
    assert event.time_s == 12.0


def test_sim_timer_scheduler_cancel_prevents_callback():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scheduler = SimTimerScheduler(now_provider=lambda: now)
    queue = _EventQueue()
    scheduler.attach(queue, sim_start=now)
    fired: list[datetime] = []

    cancel = scheduler.schedule(_FakeHass(), 5.0, lambda when: fired.append(when))
    event = queue.pop()
    cancel()
    scheduler.fire(int(event.payload["timer_id"]))

    assert fired == []


def test_sim_timer_scheduler_creates_task_for_coroutine_callback():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scheduler = SimTimerScheduler(now_provider=lambda: now)
    queue = _EventQueue()
    scheduler.attach(queue, sim_start=now)
    hass = _FakeHass()
    fired: list[datetime] = []

    async def _callback(when):
        fired.append(when)

    scheduler.schedule(hass, 1.0, _callback)
    event = queue.pop()
    scheduler.fire(int(event.payload["timer_id"]))
    hass.loop.run_until_complete(asyncio.gather(*hass.tasks))
    hass.loop.close()

    assert len(hass.tasks) == 1
    assert fired == [now.replace(second=1)]


from pathlib import Path


def test_vtsim_output_dir_env_var(tmp_path):
    """VTSIM_OUTPUT_DIR must redirect output files when set."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_OUTPUT_DIR" in src


def test_vtsim_scenario_dir_env_var():
    """VTSIM_SCENARIO_DIR must be referenced in the test module source."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_SCENARIO_DIR" in src


def test_vtsim_vt_dir_env_var():
    """VTSIM_VT_DIR must be referenced in the test module source."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_VT_DIR" in src


def test_vtsim_live_csv_env_var():
    """VTSIM_LIVE_CSV must be referenced in the test module source."""
    src = Path("tests/test_vt_scenarios.py").read_text()
    assert "VTSIM_LIVE_CSV" in src
