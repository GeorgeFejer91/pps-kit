from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "For-AI" / "engineering" / "release" / "tools" / "package_inventory.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("package_inventory", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_inventory_resolves_shared_once_and_both_apps():
    inventory = _load_module().build_inventory(component_id="full")

    assert inventory["schema"] == "pps-resolved-component-inventory.v1"
    assert inventory["resolved_components"] == ["shared", "designer", "runner", "full"]
    assert inventory["resolved_components"].count("shared") == 1
    paths = {item["path"] for item in inventory["items"]}
    assert "apps/PPSDesigner" in paths
    assert "apps/PPSExperimentRunner" in paths
    assert "shared/assets" in paths
    assert all(not item["source"].startswith("For-AI/") for item in inventory["items"])


def test_standalone_inventories_do_not_include_the_other_application():
    module = _load_module()
    designer = module.build_inventory(component_id="designer")
    runner = module.build_inventory(component_id="runner")

    designer_paths = {item["path"] for item in designer["items"]}
    runner_paths = {item["path"] for item in runner["items"]}
    assert "apps/PPSDesigner" in designer_paths
    assert "apps/PPSExperimentRunner" not in designer_paths
    assert "apps/PPSExperimentRunner" in runner_paths
    assert "apps/PPSDesigner" not in runner_paths


def test_package_inventory_reports_missing_required_items(tmp_path: Path):
    (tmp_path / "apps" / "PPSExperimentRunner").mkdir(parents=True)
    inventory = _load_module().build_inventory(tmp_path, component_id="full")

    assert inventory["summary"]["missing_required_count"] > 0
    assert "apps/PPSExperimentRunner" not in inventory["missing_required"]
    assert "apps/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll" in inventory["missing_required"]
    assert "shared/third_party/3dti_renderer/bin/pps-3dti-renderer.exe" in inventory["missing_required"]
    assert inventory["stage_root"] == "."


def test_inventory_rejects_a_changed_redistributable(tmp_path: Path):
    runtime = tmp_path / "support" / "windows-prerequisites" / "vc2013_redist.x64.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"unexpected binary")

    with pytest.raises(ValueError, match="Unexpected SHA256 for support/windows-prerequisites/vc2013_redist.x64.exe"):
        _load_module().build_inventory(tmp_path, component_id="designer")
