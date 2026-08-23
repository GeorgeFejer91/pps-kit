"""Runtime path helpers for the modular source tree and frozen applications."""

from __future__ import annotations

import os
import sys
from pathlib import Path


_PRELOAD_INVENTORY = Path("assets") / "preloads" / "preload_inventory.json"
_STUDY_TEMPLATES = Path("study_templates")
_SOURCE_RESOURCE_DIR = Path("packages") / "pps-resources"
_DESIGNER_FRONTEND_DIR = Path("apps") / "designer" / "frontend"


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


def _module_ancestors() -> list[Path]:
    module_path = Path(__file__).resolve()
    return list(module_path.parents)


def _looks_like_product_root(path: Path) -> bool:
    return (
        (path / "pyproject.toml").is_file()
        and (path / "packages" / "pps-runtime").is_dir()
    ) or _has_resource_root(path)


def _resource_root_for(path: Path) -> Path | None:
    source_resources = path / _SOURCE_RESOURCE_DIR
    if _has_resource_root(source_resources):
        return source_resources
    if _has_resource_root(path) or _has_preload_inventory(path):
        return path
    return None


def _frozen_executable_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def _development_workspace_from_exe(executable_dir: Path) -> Path:
    if executable_dir.parent.name.lower() == "dist":
        return executable_dir.parent.parent
    return executable_dir


def product_root() -> Path:
    """Return the source repository or installed PPS product root."""
    candidates: list[Path] = []
    if os.environ.get("PPS_TOOLKIT_ROOT"):
        candidates.append(Path(os.environ["PPS_TOOLKIT_ROOT"]))
    candidates.append(Path.cwd())

    executable_dir = _frozen_executable_dir()
    if executable_dir is not None:
        meipass = getattr(sys, "_MEIPASS", "")
        frozen_resource_candidates = [Path(meipass)] if meipass else []
        frozen_resource_candidates.append(executable_dir / "_internal")
        candidates.extend(
            frozen_resource_candidates
            + [
                executable_dir,
                executable_dir.parent,
                _development_workspace_from_exe(executable_dir),
            ]
        )

    candidates.extend(_module_ancestors())
    candidates = _dedupe(candidates)

    for candidate in candidates:
        if _looks_like_product_root(candidate):
            return candidate
    return _module_ancestors()[2]


def resource_root() -> Path:
    """Return the directory containing ``assets`` and ``study_templates``."""
    candidates: list[Path] = []
    if os.environ.get("PPS_TOOLKIT_ROOT"):
        candidates.append(Path(os.environ["PPS_TOOLKIT_ROOT"]))

    executable_dir = _frozen_executable_dir()
    if executable_dir is not None:
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass))
        candidates.extend([executable_dir / "_internal", executable_dir, executable_dir.parent])

    candidates.extend([Path.cwd(), product_root(), *_module_ancestors()])
    for candidate in _dedupe(candidates):
        resolved = _resource_root_for(candidate)
        if resolved is not None:
            return resolved
    return product_root() / _SOURCE_RESOURCE_DIR


def designer_frontend_root() -> Path:
    """Return the canonical Designer frontend for source or frozen execution."""
    candidates: list[Path] = []
    if os.environ.get("PPS_TOOLKIT_ROOT"):
        candidates.append(Path(os.environ["PPS_TOOLKIT_ROOT"]))
    executable_dir = _frozen_executable_dir()
    if executable_dir is not None:
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            candidates.append(Path(meipass))
        candidates.extend([executable_dir / "_internal", executable_dir, executable_dir.parent])
    candidates.extend([Path.cwd(), product_root(), *_module_ancestors()])
    for candidate in _dedupe(candidates):
        frontend = candidate / _DESIGNER_FRONTEND_DIR
        if (frontend / "compiled" / "index.html").is_file():
            return frontend
        legacy = candidate / "dashboard"
        if (legacy / "compiled" / "index.html").is_file():
            return legacy
    return product_root() / _DESIGNER_FRONTEND_DIR


def app_asset_path(name: str) -> Path:
    """Return one approved application identity or illustration asset."""
    return resource_root() / "assets" / "app" / name


def repo_root() -> Path:
    """Compatibility alias for the historical resource-root contract."""
    return resource_root()


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

    candidates = _dedupe([Path.cwd(), product_root()])
    for candidate in candidates:
        if _looks_like_product_root(candidate) or _has_resource_root(candidate):
            return candidate
    return product_root()
