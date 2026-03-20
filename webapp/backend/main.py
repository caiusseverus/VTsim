# webapp/backend/main.py
"""FastAPI application — routes, SSE, and static frontend serving."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import FRONTEND_DIST, RESULTS_DIR
from . import models as md
from . import vt_versions as vv
from . import presets as pr
from . import schedules as sc
from . import importer as im
from . import runs as rn
from . import verify as ve

app = FastAPI(title="VTsim Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

@app.get("/api/models")
def list_models():
    return md.list_models()


@app.get("/api/models/{slug}")
def get_model(slug: str):
    try:
        return md.get_model(slug)
    except FileNotFoundError:
        raise HTTPException(404, f"Model not found: {slug}")


class ModelBody(BaseModel):
    data: dict[str, Any]


@app.post("/api/models/{slug}")
def create_model(slug: str, body: ModelBody):
    md.save_model(slug, body.data)
    return {"ok": True}


@app.put("/api/models/{slug}")
def update_model(slug: str, body: ModelBody):
    md.save_model(slug, body.data)
    return {"ok": True}


@app.delete("/api/models/{slug}")
def delete_model(slug: str):
    try:
        md.delete_model(slug)
    except FileNotFoundError:
        raise HTTPException(404)
    return {"ok": True}


class CloneBody(BaseModel):
    new_slug: str


@app.post("/api/models/{slug}/clone")
def clone_model(slug: str, body: CloneBody):
    if not body.new_slug.strip():
        raise HTTPException(400, "new_slug required")
    try:
        md.clone_model(slug, body.new_slug.strip())
    except FileNotFoundError:
        raise HTTPException(404)
    return {"ok": True}


# ---------------------------------------------------------------------------
# VT Versions
# ---------------------------------------------------------------------------

@app.get("/api/vt-versions")
def list_vt_versions():
    return vv.list_vt_versions()


@app.get("/api/vt-versions/{name}")
def get_vt_version(name: str):
    try:
        versions = vv.list_vt_versions()
        for v in versions:
            if v["name"] == name:
                return v
        raise KeyError
    except KeyError:
        raise HTTPException(404, f"VT version not found: {name}")


class RegisterVersionBody(BaseModel):
    name: str
    path: str


@app.post("/api/vt-versions")
def register_vt_version(body: RegisterVersionBody):
    try:
        vv.register_vt_version(body.name, body.path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.delete("/api/vt-versions/{name}")
def remove_vt_version(name: str):
    try:
        vv.remove_vt_version(name)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

@app.get("/api/presets")
def list_presets():
    return pr.list_presets()


@app.get("/api/presets/{preset_id}")
def get_preset(preset_id: str):
    try:
        return pr.get_preset(preset_id)
    except KeyError:
        raise HTTPException(404, f"Preset not found: {preset_id}")


class CreatePresetBody(BaseModel):
    id: str
    name: str
    control: dict[str, Any] = {}
    temperatures: dict[str, Any] = {}


class UpdatePresetBody(BaseModel):
    name: str
    control: dict[str, Any] = {}
    temperatures: dict[str, Any] = {}


@app.post("/api/presets")
def create_preset(body: CreatePresetBody):
    try:
        pr.create_preset(body.id, body.name, {"control": body.control, "temperatures": body.temperatures})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.put("/api/presets/{preset_id}")
def update_preset(preset_id: str, body: UpdatePresetBody):
    try:
        pr.update_preset(preset_id, body.name, {"control": body.control, "temperatures": body.temperatures})
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@app.delete("/api/presets/{preset_id}")
def delete_preset(preset_id: str):
    try:
        pr.delete_preset(preset_id)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


class ClonePresetBody(BaseModel):
    new_id: str
    new_name: str


@app.post("/api/presets/{preset_id}/clone")
def clone_preset_endpoint(preset_id: str, body: ClonePresetBody):
    if not body.new_id.strip():
        raise HTTPException(400, "new_id required")
    try:
        pr.clone_preset(preset_id, body.new_id.strip(), body.new_name.strip() or body.new_id.strip())
    except KeyError:
        raise HTTPException(404)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------

@app.get("/api/schedules")
def list_schedules():
    return sc.list_schedules()


@app.get("/api/schedules/{schedule_id}")
def get_schedule(schedule_id: str):
    try:
        return sc.get_schedule(schedule_id)
    except KeyError:
        raise HTTPException(404, f"Schedule not found: {schedule_id}")


class CreateScheduleBody(BaseModel):
    id: str
    name: str
    type: str
    interval_hours: float | None = None
    high_temp: float | None = None
    low_temp: float | None = None
    entries: list[dict[str, Any]] | None = None


class UpdateScheduleBody(BaseModel):
    name: str
    type: str
    interval_hours: float | None = None
    high_temp: float | None = None
    low_temp: float | None = None
    entries: list[dict[str, Any]] | None = None


@app.post("/api/schedules")
def create_schedule(body: CreateScheduleBody):
    try:
        sc.create_schedule(body.model_dump(exclude_none=True))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.put("/api/schedules/{schedule_id}")
def update_schedule(schedule_id: str, body: UpdateScheduleBody):
    try:
        sc.update_schedule(schedule_id, body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


@app.delete("/api/schedules/{schedule_id}")
def delete_schedule(schedule_id: str):
    try:
        sc.delete_schedule(schedule_id)
    except KeyError:
        raise HTTPException(404)
    return {"ok": True}


# ---------------------------------------------------------------------------
# HA State Importer
# ---------------------------------------------------------------------------

class HAStateBody(BaseModel):
    yaml_text: str


@app.post("/api/import/ha-state")
def import_ha_state(body: HAStateBody):
    return im.parse_ha_state(body.yaml_text)


# ---------------------------------------------------------------------------
# HA Log Verify
# ---------------------------------------------------------------------------

@app.post("/api/verify/parse")
async def verify_parse(file: UploadFile = File(...)):
    content = await file.read()
    try:
        records = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")
    if not isinstance(records, list):
        raise HTTPException(400, "Expected a JSON array of state records")
    try:
        return ve.parse_ha_log(records)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

class CreateRunBody(BaseModel):
    name: str
    model_names: list[str]
    version_names: list[str]
    preset_ids: list[str]
    schedule_id: str
    ha_history: list[dict[str, Any]] | None = None
    starting_conditions: dict[str, Any] | None = None


@app.post("/api/runs")
async def create_run(body: CreateRunBody, background_tasks: BackgroundTasks):
    try:
        run_id = rn.create_run(
            name=body.name,
            model_names=body.model_names,
            version_names=body.version_names,
            preset_ids=body.preset_ids,
            schedule_id=body.schedule_id,
            ha_history=body.ha_history,
            starting_conditions=body.starting_conditions,
        )
    except (KeyError, FileNotFoundError) as e:
        raise HTTPException(400, str(e))
    background_tasks.add_task(rn.execute_run, run_id)
    return {"run_id": run_id}


@app.get("/api/runs")
def list_runs():
    return rn.list_runs()


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        return rn.get_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404)


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    try:
        rn.delete_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404)
    return {"ok": True}


@app.get("/api/runs/{run_id}/stream")
async def stream_run(run_id: str):
    async def event_generator():
        last_idx = 0
        while True:
            events = rn.get_events(run_id)
            for event in events[last_idx:]:
                yield f"data: {json.dumps(event)}\n\n"
            last_idx = len(events)
            try:
                run = rn.get_run(run_id)
            except FileNotFoundError:
                break
            if run["status"] in ("complete", "partial_failure", "failed"):
                events = rn.get_events(run_id)
                for event in events[last_idx:]:
                    yield f"data: {json.dumps(event)}\n\n"
                break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/runs/{run_id}/ha-history")
def get_ha_history(run_id: str):
    p = RESULTS_DIR / run_id / "ha_history.json"
    if not p.exists():
        raise HTTPException(404, "No HA history for this run")
    return json.loads(p.read_text())


@app.get("/api/results/{run_id}/summary")
def results_summary(run_id: str):
    try:
        run = rn.get_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404)
    return run.get("cells", [])


@app.get("/api/results/{run_id}/{model}/{version_preset}/plot")
def result_plot(run_id: str, model: str, version_preset: str):
    p = RESULTS_DIR / run_id / model / version_preset / f"{model}.png"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


@app.get("/api/results/{run_id}/{model}/{version_preset}/records")
def result_records(run_id: str, model: str, version_preset: str):
    p = RESULTS_DIR / run_id / model / version_preset / f"{model}_records.csv"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename={model}_records.csv"})


if FRONTEND_DIST.exists():
    # Serve hashed Vite bundles from /assets/ directly (efficient, no fallback needed).
    _assets = FRONTEND_DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    # Catch-all: serve exact files (favicon etc.) or fall back to index.html so that
    # React Router client-side routes survive a browser refresh.
    @app.get("/{full_path:path}")
    async def _serve_spa(full_path: str):
        candidate = FRONTEND_DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        index = FRONTEND_DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        raise HTTPException(404)
