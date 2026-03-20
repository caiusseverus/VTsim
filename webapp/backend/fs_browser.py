"""Backend filesystem browser — returns subdirectories for a given path."""
from __future__ import annotations

from pathlib import Path


def browse(path: str | None) -> dict:
    """Return subdirectories of path, or the home directory if path is empty."""
    p = Path(path).resolve() if path else Path.home()

    if not p.exists() or not p.is_dir():
        raise ValueError(f"Not a directory: {p}")

    try:
        dirs = sorted(d.name for d in p.iterdir() if d.is_dir())
    except PermissionError:
        dirs = []

    parent = str(p.parent) if str(p) != str(p.parent) else None

    return {"path": str(p), "dirs": dirs, "parent": parent}
