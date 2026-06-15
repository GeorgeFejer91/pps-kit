"""Runtime path helpers for source and frozen Windows builds."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_PRELOAD_INVENTORY = Path("assets") / "preloads" / "preload_inventory.json"
_STUDY_TEMPLATES = Path("study_templates")


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        key = str(resolved).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(resolved)
    return unique


def _has_resource_root(path: Path) -> bool:
    return (path / _STUDY_TEMPLATES).is_dir() and (path / _PRELOAD_INVENTORY).is_file()


def _has_preload_inventory(path: Path) -> bool:
    return (path / _PRELOAD_INVENTORY).is_file()


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _frozen_executable_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def _development_workspace_from_exe(executable_dir: Path) -> Path:
    if executable_dir.parent.name.lower() == "dist":
        return executable_dir.parent.parent
    return executable_dir


def repo_root() -> Path:
    """Return the readable resource root that contains study templates and preloads."""
    candidates: list[Path] = []
    if os.environ.get("PPS_TOOLKIT_ROOT"):
        candidates.append(Path(os.environ["PPS_TOOLKIT_ROOT"]))
    candidates.append(Path.cwd())

    executable_dir = _frozen_executable_dir()
    if executable_dir is not None:
        candidates.extend(
            [
                executable_dir,
                executable_dir.parent,
                _development_workspace_from_exe(executable_dir),
            ]
        )
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass))

    candidates.append(_source_root())
    candidates = _dedupe(candidates)

    for candidate in candidates:
        if _has_resource_root(candidate):
            return candidate
    for candidate in candidates:
        if _has_preload_inventory(candidate):
            return candidate
    return _source_root()


def writable_root() -> Path:
    """Return the root for generated sessions, renders, and dashboard state.

    PyInstaller one-dir builds expose bundled assets under ``_internal``. That
    folder is a resource location, not a durable experiment-output home.
    """
    if os.environ.get("PPS_TOOLKIT_DATA_ROOT"):
        return Path(os.environ["PPS_TOOLKIT_DATA_ROOT"]).expanduser().resolve()
    if os.environ.get("PPS_TOOLKIT_ROOT"):
        return Path(os.environ["PPS_TOOLKIT_ROOT"]).expanduser().resolve()

    executable_dir = _frozen_executable_dir()
    if executable_dir is not None:
        return _development_workspace_from_exe(executable_dir).resolve()

    candidates = _dedupe([Path.cwd(), _source_root()])
    for candidate in candidates:
        if _has_resource_root(candidate):
            return candidate
    return _source_root()
