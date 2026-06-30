from __future__ import annotations

import importlib
from pathlib import Path


def _resource_root(path: Path) -> None:
    (path / "assets" / "preloads").mkdir(parents=True)
    (path / "assets" / "preloads" / "preload_inventory.json").write_text("{}", encoding="utf-8")
    (path / "study_templates").mkdir()


def test_frozen_runner_uses_distribution_parent_for_writable_outputs(tmp_path, monkeypatch):
    from peripersonal_space_toolkit import runtime_paths

    repo = tmp_path / "repo"
    app_dir = repo / "dist" / "PPSExperimentRunner"
    internal = app_dir / "_internal"
    _resource_root(internal)
    app_dir.mkdir(parents=True, exist_ok=True)
    work = tmp_path / "work"
    work.mkdir()

    monkeypatch.chdir(work)
    monkeypatch.delenv("PPS_TOOLKIT_ROOT", raising=False)
    monkeypatch.delenv("PPS_TOOLKIT_DATA_ROOT", raising=False)
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(internal), raising=False)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(app_dir / "PPSExperimentRunner.exe"))

    assert runtime_paths.repo_root() == internal.resolve()
    assert runtime_paths.writable_root() == repo.resolve()


def test_frozen_runner_checks_internal_when_meipass_is_executable_dir(tmp_path, monkeypatch):
    from peripersonal_space_toolkit import runtime_paths

    repo = tmp_path / "repo"
    app_dir = repo / "dist" / "PPSExperimentRunner"
    internal = app_dir / "_internal"
    _resource_root(internal)
    app_dir.mkdir(parents=True, exist_ok=True)
    work = tmp_path / "work"
    work.mkdir()

    monkeypatch.chdir(work)
    monkeypatch.delenv("PPS_TOOLKIT_ROOT", raising=False)
    monkeypatch.delenv("PPS_TOOLKIT_DATA_ROOT", raising=False)
    monkeypatch.setattr(runtime_paths.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime_paths.sys, "_MEIPASS", str(app_dir), raising=False)
    monkeypatch.setattr(runtime_paths.sys, "executable", str(app_dir / "PPSExperimentRunner.exe"))

    assert runtime_paths.repo_root() == internal.resolve()
    assert runtime_paths.writable_root() == repo.resolve()


def test_writable_root_env_override_wins(tmp_path, monkeypatch):
    from peripersonal_space_toolkit import runtime_paths

    target = tmp_path / "lab-data"
    monkeypatch.setenv("PPS_TOOLKIT_DATA_ROOT", str(target))

    assert runtime_paths.writable_root() == target.resolve()


def test_render_backend_resolves_relative_assets_from_runtime_resource_root(tmp_path, monkeypatch):
    from peripersonal_space_toolkit import render_backend, runtime_paths

    resource_root = tmp_path / "bundle" / "_internal"
    _resource_root(resource_root)
    original_repo_root = runtime_paths.repo_root
    monkeypatch.setattr(runtime_paths, "repo_root", lambda: resource_root.resolve())
    try:
        reloaded = importlib.reload(render_backend)

        assert reloaded.repo_relative_path("assets/example.wav") == resource_root.resolve() / "assets" / "example.wav"
    finally:
        monkeypatch.setattr(runtime_paths, "repo_root", original_repo_root)
        importlib.reload(render_backend)
