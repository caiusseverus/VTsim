# tests/test_backend/test_config.py
from pathlib import Path
from webapp.backend.config import PROJECT_ROOT, SCENARIOS_DIR, RESULTS_DIR, RUNS_DIR, VERSIONS_FILE, FRONTEND_DIST


def test_project_root_is_fakeha_dir():
    assert (PROJECT_ROOT / "tests" / "scenarios").is_dir()


def test_scenarios_dir_points_to_yaml_dir():
    assert SCENARIOS_DIR.is_dir()
    assert any(SCENARIOS_DIR.glob("*.yaml"))


def test_results_dir_is_under_project_root():
    assert RESULTS_DIR == PROJECT_ROOT / "results"


def test_runs_dir_is_under_webapp():
    assert RUNS_DIR == PROJECT_ROOT / "webapp" / "runs"


def test_versions_file_exists():
    assert VERSIONS_FILE.exists()


def test_frontend_dist_is_under_webapp():
    assert FRONTEND_DIST == PROJECT_ROOT / "webapp" / "frontend" / "dist"
