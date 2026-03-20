"""Central path constants for the VTsim web backend."""
from pathlib import Path

# Resolves to VTsim/ regardless of working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

MODELS_DIR = PROJECT_ROOT / "tests" / "models"
RESULTS_DIR = PROJECT_ROOT / "results"
RUNS_DIR = PROJECT_ROOT / "webapp" / "runs"
VT_VERSIONS_FILE = PROJECT_ROOT / "webapp" / "vt_versions.json"
HEATING_SIM_FILE = PROJECT_ROOT / "webapp" / "heating_sim.json"
PRESETS_FILE = PROJECT_ROOT / "webapp" / "presets.json"
SCHEDULES_FILE = PROJECT_ROOT / "webapp" / "schedules.json"
FRONTEND_DIST = PROJECT_ROOT / "webapp" / "frontend" / "dist"
