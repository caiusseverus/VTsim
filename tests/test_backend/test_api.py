# tests/test_backend/test_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from webapp.backend.main import app


@pytest.mark.asyncio
async def test_list_scenarios():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/scenarios")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.asyncio
async def test_get_scenario():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        scenarios = (await client.get("/api/scenarios")).json()
        name = scenarios[0]["name"]
        r = await client.get(f"/api/scenarios/{name}")
    assert r.status_code == 200
    assert "model" in r.json()


@pytest.mark.asyncio
async def test_get_unknown_scenario_returns_404():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/scenarios/does_not_exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_versions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/versions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_import_ha_state():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/import/ha-state", json={"yaml_text": "min_temp: 7\nmax_temp: 35\n"})
    assert r.status_code == 200
    body = r.json()
    assert "mapped" in body
    assert "unrecognised" in body
    assert "missing" in body


@pytest.mark.asyncio
async def test_list_runs():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/runs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
