"""Model YAML CRUD — thermal model + simulation params only (no thermostat, no schedule)."""
from __future__ import annotations
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from . import config

_yaml = YAML()
_yaml.preserve_quotes = True


def list_models() -> list[dict[str, Any]]:
    """Return summary list of all non-template models."""
    result = []
    for path in sorted(config.MODELS_DIR.glob("*.yaml")):
        if path.stem.startswith("_"):
            continue
        try:
            with path.open("r", encoding="utf-8") as f:
                data = _yaml.load(f)
            result.append({
                "slug": path.stem,
                "name": data.get("name", path.stem),
                "description": data.get("description", ""),
                "model_type": (data.get("model") or {}).get("model_type", ""),
                "control_mode": (data.get("model") or {}).get("control_mode", "pwm"),
                "duration_hours": (data.get("simulation") or {}).get("duration_hours", 0),
            })
        except Exception:
            continue
    return result


def get_model(slug: str) -> dict[str, Any]:
    """Load and return a model by slug."""
    path = config.MODELS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Model not found: {slug}")
    with path.open("r", encoding="utf-8") as f:
        return dict(_yaml.load(f))


def save_model(slug: str, data: dict[str, Any]) -> None:
    """Write a model dict to YAML. Creates or overwrites."""
    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = config.MODELS_DIR / f"{slug}.yaml"
    with path.open("w", encoding="utf-8") as f:
        _yaml.dump(data, f)


def delete_model(slug: str) -> None:
    path = config.MODELS_DIR / f"{slug}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Model not found: {slug}")
    path.unlink()


def clone_model(source_slug: str, new_slug: str) -> None:
    data = get_model(source_slug)
    data["name"] = new_slug
    save_model(new_slug, data)
