from __future__ import annotations

import importlib.util
from pathlib import Path


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
    inventory = _load_module().build_inventory(tmp_path, component_id="runner")

    assert inventory["summary"]["missing_required_count"] > 0
    assert "apps/PPSExperimentRunner" in inventory["missing_required"]
