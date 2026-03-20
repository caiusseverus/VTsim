# VTsim

Headless simulation harness for testing the [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) Home Assistant custom integration against Python thermal models — no running HA instance required.

Simulations run at accelerated speed with a synthetic clock. Results are written as CSV/JSON and viewable via a built-in web UI.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js + npm _(web UI only)_

## Installation

```bash
git clone https://github.com/caiusseverus/VTsim.git
cd VTsim
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

## Running Simulations

```bash
# All scenarios
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_vt_scenarios.py -s

# Single scenario
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q "tests/test_vt_scenarios.py::test_vt_scenario[pwm_r2c2_standard]" -s
```

Results are written to `results/<scenario_name>.png` and `results/summary.csv`.

## Scenarios

| Scenario | Model | Algorithm | Duration | SSE limit |
|---|---|---|---|---|
| pwm_r2c2_standard | R2C2 standard room | SmartPI | 48h | 0.5°C |
| pwm_r2c2_high_inertia | R2C2 heavy stone | SmartPI | 72h | 1.0°C |
| pwm_r2c2_low_inertia | R2C2 light build | SmartPI | 24h | 0.5°C |
| pwm_r2c2_tpi | R2C2 standard room | TPI | 48h | 1.5°C |
| pwm_simple_tpi | R1C1 simple | TPI | 24h | 1.5°C |

## Web UI

Builds the React frontend and starts the FastAPI backend at `http://localhost:8000`:

```bash
./run.sh          # uses existing frontend build if present
./run.sh --build  # force rebuild of frontend
```

Run outputs are stored in `webapp/runs/` and accessible via the UI.
