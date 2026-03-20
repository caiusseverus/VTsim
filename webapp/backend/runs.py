# webapp/backend/runs.py
"""Run lifecycle management and subprocess worker orchestration."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML as _YAML
from ruamel.yaml.scalarstring import DoubleQuotedScalarString as _DQStr

from . import config as _cfg

MAX_WORKERS = int(os.getenv("VTSIM_MAX_WORKERS", "4"))
_status_lock = threading.Lock()


def _run_path(run_id: str) -> Path:
    return _cfg.RUNS_DIR / f"{run_id}.json"


def create_run(
    name: str,
    model_names: list[str],
    version_names: list[str],
    preset_ids: list[str],
    schedule_id: str,
    ha_history: list[dict] | None = None,
    starting_conditions: dict | None = None,
) -> str:
    """Create a run record and return its ID. Does not start execution."""
    from .vt_versions import get_vt_dir
    from .presets import get_preset, flatten_preset_params
    from .schedules import get_schedule

    _cfg.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:12]

    get_schedule(schedule_id)  # validates schedule exists; raises KeyError if not found

    cells = []
    for model_name in model_names:
        for version_name in version_names:
            for preset_id in preset_ids:
                vt_dir = get_vt_dir(version_name)
                preset = get_preset(preset_id)
                thermostat_params = flatten_preset_params(preset)
                cells.append({
                    "model": model_name,
                    "vt_version": version_name,
                    "preset": preset_id,
                    "vt_dir": vt_dir,
                    "thermostat_params": thermostat_params,
                    "status": "pending",
                })

    record: dict[str, Any] = {
        "id": run_id,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "schedule_id": schedule_id,
        "cells": cells,
    }
    if starting_conditions:
        record["starting_conditions"] = starting_conditions
    target = _run_path(run_id)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2))
    tmp.replace(target)

    if ha_history:
        history_dir = _cfg.RESULTS_DIR / run_id
        history_dir.mkdir(parents=True, exist_ok=True)
        history_file = history_dir / "ha_history.json"
        history_file.write_text(json.dumps(ha_history))

    return run_id


def get_run(run_id: str) -> dict[str, Any]:
    path = _run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"Run not found: {run_id}")
    return json.loads(path.read_text())


def list_runs() -> list[dict[str, Any]]:
    if not _cfg.RUNS_DIR.exists():
        return []
    runs = []
    for p in sorted(_cfg.RUNS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            runs.append(json.loads(p.read_text()))
        except Exception:
            continue
    return runs


def delete_run(run_id: str) -> None:
    path = _run_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"Run not found: {run_id}")
    path.unlink()
    results = _cfg.RESULTS_DIR / run_id
    if results.exists():
        shutil.rmtree(results)


def _update_cell_status(run_id: str, model: str, version: str, preset: str,
                         status: str, metrics: dict | None = None, error: str | None = None) -> None:
    with _status_lock:
        run = get_run(run_id)
        for cell in run["cells"]:
            if cell["model"] == model and cell["vt_version"] == version and cell["preset"] == preset:
                cell["status"] = status
                if metrics:
                    cell["metrics"] = metrics
                if error:
                    cell["error"] = error
                break
        statuses = {c["status"] for c in run["cells"]}
        if statuses == {"complete"}:
            run["status"] = "complete"
        elif "running" in statuses or "pending" in statuses:
            run["status"] = "running"
        elif "complete" in statuses:
            run["status"] = "partial_failure"
        else:
            run["status"] = "failed"
        target = _run_path(run_id)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(run, indent=2))
        tmp.replace(target)


def build_worker_scenario_yaml(
    model_data: dict[str, Any],
    thermostat_params: dict[str, Any],
    dest_dir: Path,
    schedule_entries: list[dict[str, Any]],
    model_slug: str = "",
    starting_conditions: dict[str, Any] | None = None,
) -> Path:
    """Write a merged model YAML (with thermostat + schedule injected) to dest_dir.

    The test harness reads thermostat from scenario.get('thermostat', {}) and
    the schedule from scenario.get('simulation', {}).get('schedule', []).
    We inject both here so the worker subprocess sees a complete scenario.
    """
    merged = dict(model_data)
    merged["thermostat"] = thermostat_params

    sim = dict(merged.get("simulation") or {})
    sim["schedule"] = schedule_entries

    if starting_conditions:
        # Override model room temperature and external temperature
        model_section = dict(merged.get("model") or {})
        if starting_conditions.get("initial_temperature") is not None:
            model_section["initial_temperature"] = starting_conditions["initial_temperature"]
        if starting_conditions.get("ext_temperature") is not None:
            model_section["external_temperature_fixed"] = starting_conditions["ext_temperature"]
        merged["model"] = model_section

        # Override sim starting state.
        # Force-quote hvac_mode so PyYAML (YAML 1.1) doesn't misread "off" as False.
        if starting_conditions.get("hvac_mode"):
            sim["initial_hvac_mode"] = _DQStr(starting_conditions["hvac_mode"])
        # Only set preset if it's a named preset (not "none"/null)
        pm = starting_conditions.get("preset_mode")
        if pm and pm not in ("none", "None"):
            sim["initial_preset_mode"] = pm

    merged["simulation"] = sim

    slug = model_slug or model_data.get("name", "model")
    out_path = dest_dir / f"{slug}.yaml"
    _yaml_writer = _YAML()
    with out_path.open("w", encoding="utf-8") as f:
        _yaml_writer.dump(merged, f)
    return out_path


async def _run_worker(
    run_id: str,
    model_name: str,
    vt_dir: str,
    thermostat_params: dict[str, Any],
    version_name: str,
    preset_name: str,
    schedule_id: str,
    starting_conditions: dict[str, Any] | None = None,
) -> None:
    from .models import get_model
    from .schedules import get_schedule, resolve_schedule

    output_dir = _cfg.RESULTS_DIR / run_id / model_name / f"{version_name}_{preset_name}"
    output_dir.mkdir(parents=True, exist_ok=True)
    live_csv = output_dir / f"{model_name}_live.csv"

    with tempfile.TemporaryDirectory(prefix=f"vtsim_{run_id}_") as tmp:
        tmp_path = Path(tmp)
        model_data = get_model(model_name)
        duration_hours = float((model_data.get("simulation") or {}).get("duration_hours", 48))
        schedule = get_schedule(schedule_id)
        schedule_entries = resolve_schedule(schedule, duration_hours)
        build_worker_scenario_yaml(model_data, thermostat_params, tmp_path,
                                   schedule_entries=schedule_entries, model_slug=model_name,
                                   starting_conditions=starting_conditions)

        env = {**os.environ,
               "VTSIM_VT_DIR": vt_dir,
               "VTSIM_SCENARIO_DIR": str(tmp_path),
               "VTSIM_OUTPUT_DIR": str(output_dir),
               "VTSIM_LIVE_CSV": str(live_csv)}

        proc = await asyncio.create_subprocess_exec(
            "uv", "run", "--", "pytest", "-q", "-s",
            f"tests/test_vt_scenarios.py::test_vt_scenario[{model_name}]",
            cwd=str(_cfg.PROJECT_ROOT),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        _update_cell_status(run_id, model_name, version_name, preset_name, "running")
        store_event(run_id, {"type": "cell_started", "model": model_name,
                              "version": version_name, "preset": preset_name})

        tail_task = asyncio.create_task(
            _tail_live_csv(live_csv, run_id, model_name, version_name, preset_name)
        )

        stdout, _ = await proc.communicate()
        tail_task.cancel()

        if proc.returncode == 0:
            metrics_file = output_dir / "metrics.json"
            metrics = {}
            if metrics_file.exists():
                metrics = json.loads(metrics_file.read_text())
            _update_cell_status(run_id, model_name, version_name, preset_name,
                                 "complete", metrics=metrics)
            store_event(run_id, {
                "type": "cell_complete",
                "model": model_name, "version": version_name,
                "preset": preset_name, "metrics": metrics,
            })
        else:
            error_msg = (stdout or b"").decode(errors="replace")[-2000:]
            _update_cell_status(run_id, model_name, version_name, preset_name,
                                 "failed", error=error_msg)
            store_event(run_id, {
                "type": "cell_error",
                "model": model_name, "version": version_name,
                "preset": preset_name, "message": error_msg,
            })


async def _tail_live_csv(
    csv_path: Path,
    run_id: str,
    model: str,
    version: str,
    preset: str,
) -> None:
    import csv as _csv
    seen_rows = 0
    while True:
        await asyncio.sleep(2)
        if not csv_path.exists():
            continue
        with csv_path.open("r", newline="", encoding="utf-8") as f:
            reader = list(_csv.DictReader(f))
        new_rows = reader[seen_rows:]
        seen_rows += len(new_rows)
        for row in new_rows:
            event: dict = {
                "type": "temperature_point",
                "model": model, "version": version, "preset": preset,
            }
            for key, val in row.items():
                try:
                    event[key] = float(val)
                except (ValueError, TypeError):
                    pass
            if "elapsed_h" not in event:
                continue
            store_event(run_id, event)


async def execute_run(run_id: str) -> None:
    run = get_run(run_id)
    semaphore = asyncio.Semaphore(MAX_WORKERS)

    async def _bounded_worker(cell: dict) -> None:
        async with semaphore:
            await _run_worker(
                run_id=run_id,
                model_name=cell["model"],
                vt_dir=cell["vt_dir"],
                thermostat_params=cell["thermostat_params"],
                version_name=cell["vt_version"],
                preset_name=cell["preset"],
                schedule_id=run["schedule_id"],
                starting_conditions=run.get("starting_conditions"),
            )

    tasks = [asyncio.create_task(_bounded_worker(c)) for c in run["cells"]]
    await asyncio.gather(*tasks, return_exceptions=True)
    store_event(run_id, {"type": "run_complete", "run_id": run_id})


_event_store: dict[str, list[dict]] = {}
_event_store_lock = threading.Lock()


def store_event(run_id: str, event: dict) -> None:
    with _event_store_lock:
        _event_store.setdefault(run_id, []).append(event)


def get_events(run_id: str) -> list[dict]:
    with _event_store_lock:
        return list(_event_store.get(run_id, []))
