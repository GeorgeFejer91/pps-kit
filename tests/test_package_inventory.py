from __future__ import annotations

import importlib.util
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "package_inventory.py"
TRACKED_INVENTORY_PATH = REPO_ROOT / "windows" / "installer_package_inventory.v1.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("package_inventory", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tracked_installer_inventory_matches_tool_definition():
    module = _load_module()
    expected = module.build_inventory()
    tracked = json.loads(TRACKED_INVENTORY_PATH.read_text(encoding="utf-8"))

    assert tracked["schema"] == module.INVENTORY_SCHEMA
    assert tracked["summary"] == expected["summary"]
    assert [item["path"] for item in tracked["items"]] == [item["path"] for item in expected["items"]]
    assert all("exists" not in item for item in tracked["items"])
    required_paths = {item["path"] for item in tracked["items"] if item["required"]}
    assert "dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll" in required_paths


def test_package_inventory_reports_missing_required_items(tmp_path: Path):
    module = _load_module()
    inventory = module.build_inventory(tmp_path)

    assert inventory["summary"]["missing_required_count"] > 0
    assert "dist/PPSExperimentRunner/PPSExperimentRunner.exe" in inventory["missing_required"]
