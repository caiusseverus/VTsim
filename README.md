# VTsim

Headless simulation harness for testing the [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat) Home Assistant custom integration against Python thermal models — no running HA instance required.

Simulations run at accelerated speed with a synthetic clock. Results are written as CSV/JSON and viewable via a built-in web UI.

## Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js + npm _(web UI only)_
- [versatile_thermostat](https://github.com/jmcollin78/versatile_thermostat) — cloned separately
- [heating_simulator](https://github.com/jmcollin78/heating_simulator) — cloned separately

## Installation

```bash
git clone https://github.com/caiusseverus/VTsim.git
cd VTsim
UV_CACHE_DIR=/tmp/uv-cache uv sync
```

## Configuration

VTsim needs the paths to the two dependency repos. The easiest way is via the web UI — start with `./run.sh` and set both paths on the Versions page.

For CLI pytest, set environment variables instead:

```bash
export VTSIM_VT_DIR=/path/to/versatile_thermostat/custom_components/versatile_thermostat
export VTSIM_HEATING_SIM_DIR=/path/to/heating_simulator/custom_components/heating_simulator
```

Or symlink them into the repo root:

```bash
ln -s /path/to/versatile_thermostat/custom_components/versatile_thermostat custom_components/versatile_thermostat
ln -s /path/to/heating_simulator/custom_components/heating_simulator custom_components/heating_simulator
```

## Running Simulations

```bash
# All scenarios
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q tests/test_vt_scenarios.py -s

# Single scenario
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q "tests/test_vt_scenarios.py::test_vt_scenario[pwm_r2c2]" -s
```

Results are written to `results/<scenario_name>.png` and `results/summary.csv` (pytest runs only; web UI runs go to `webapp/runs/`).

## Scenarios

Scenarios are defined by YAML files in `tests/models/`. Each file specifies the thermal model, control algorithm, simulation duration, and VT configuration. See `tests/models/_template.yaml` for the full schema.

To run a specific scenario by filename stem:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest -q "tests/test_vt_scenarios.py::test_vt_scenario[pwm_r2c2]" -s
```

## Web UI

Builds the React frontend and starts the FastAPI backend at `http://localhost:8000`:

```bash
./run.sh          # uses existing frontend build if present
./run.sh --build  # force rebuild of frontend
```

Run outputs are stored in `webapp/runs/` and accessible via the UI. The UI includes pages for managing thermal models, presets, schedules, VT versions, and run results, with live monitoring during active runs and a comparison view across multiple runs.
