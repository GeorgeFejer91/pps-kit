from __future__ import annotations

import importlib.util
import hashlib
import json
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


def test_full_v2_catalog_matches_tauri_resource_map():
    module = _load_module()
    inventory = module.build_inventory(component_id="full", manifest_version="v2")
    assert inventory["schema"] == "pps-resolved-component-inventory.v2"
    assert inventory["resolved_components"] == ["shared", "planner", "runner", "full"]
    assert inventory["resolved_components"].count("shared") == 1
    expected = {
        (REPO_ROOT / item["source"]).resolve().relative_to(REPO_ROOT).as_posix(): item["path"].rstrip("/")
        for item in inventory["items"]
        if item["path"] != "pps-experiment-planner.exe"
    }
    config_dir = REPO_ROOT / "apps" / "designer" / "src-tauri"
    config = json.loads((config_dir / "tauri.full-validation.conf.json").read_text(encoding="utf-8"))
    actual = {
        (config_dir / source).resolve().relative_to(REPO_ROOT).as_posix(): destination.rstrip("/")
        for source, destination in config["bundle"]["resources"].items()
    }
    assert actual == expected
    planner = next(item for item in inventory["items"] if item["path"] == "pps-experiment-planner.exe")
    assert planner["binary_patch"] == "tauri-nsis"


def test_tauri_nsis_patch_accepts_only_the_single_bundle_marker(tmp_path: Path):
    module = _load_module()
    source = tmp_path / "planner.exe"
    source.write_bytes(b"prefix" + module.TAURI_BUNDLE_TOKEN + b"suffix")
    expected = b"prefix" + module.TAURI_NSIS_TOKEN + b"suffix"
    assert module.sha256_tauri_nsis_binary(source) == hashlib.sha256(expected).hexdigest()
    source.write_bytes(module.TAURI_BUNDLE_TOKEN * 2)
    try:
        module.sha256_tauri_nsis_binary(source)
    except ValueError as error:
        assert "exactly one" in str(error)
    else:
        raise AssertionError("duplicate bundle markers must fail inventory verification")


def test_v2_inventory_rejects_other_planner_executable_changes(tmp_path: Path, monkeypatch):
    module = _load_module()
    source = tmp_path / "target/release/pps-experiment-planner.exe"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"before" + module.TAURI_BUNDLE_TOKEN + b"after")
    installed_root = tmp_path / "installed"
    installed_root.mkdir()
    installed = installed_root / source.name
    installed.write_bytes(b"before" + module.TAURI_NSIS_TOKEN + b"after")
    manifest_path = tmp_path / "planner.v2.json"
    manifest_path.write_text("{}", encoding="utf-8")
    manifest = {
        "component_id": "planner",
        "version": "0.1.0",
        "_path": manifest_path,
        "source_to_install": [{
            "source": source.relative_to(tmp_path).as_posix(),
            "install": source.name,
            "kind": "generated_file",
            "binary_patch": "tauri-nsis",
        }],
    }
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(module, "load_manifests", lambda manifest_version: {"planner": manifest})
    good = module.build_inventory(installed_root, "planner", "v2")
    assert good["mismatched"] == []
    assert good["items"][0]["expected_install_sha256"] == good["items"][0]["sha256"]
    installed.write_bytes(installed.read_bytes() + b"changed")
    bad = module.build_inventory(installed_root, "planner", "v2")
    assert bad["mismatched"] == [source.name]
