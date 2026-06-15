from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "tools" / "make_download_manifest.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("make_download_manifest", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_download_manifest_hashes_payload(tmp_path: Path):
    module = _load_module()
    payload = tmp_path / "PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip"
    payload.write_bytes(b"offline-package")
    inventory = tmp_path / "pps_package_inventory.v1.json"
    inventory.write_text(
        """{
  "schema": "pps-installer-package-inventory.v1",
  "summary": {
    "item_count": 3,
    "required_item_count": 2,
    "missing_required_count": 0
  }
}
""",
        encoding="utf-8",
    )

    manifest = module.build_manifest(
        payload=payload,
        payload_url="https://zenodo.org/records/123/files/PPS-Toolkit-v0.1.0-offline-lab-windows-x64.zip",
        version="0.1.0",
        source_tag="v0.1.0",
        source_commit="abc123",
        zenodo_doi="10.5281/zenodo.123",
        package_inventory=inventory,
    )

    assert manifest["schema"] == "pps-download-manifest.v1"
    assert manifest["version"] == "0.1.0"
    assert manifest["source_tag"] == "v0.1.0"
    assert manifest["payloads"][0]["kind"] == "offline_lab_windows_x64"
    assert manifest["payloads"][0]["filename"] == payload.name
    assert manifest["payloads"][0]["size_bytes"] == len(b"offline-package")
    assert len(manifest["payloads"][0]["sha256"]) == 64
    assert manifest["payloads"][0]["package_inventory"]["filename"] == inventory.name
    assert manifest["payloads"][0]["package_inventory"]["schema"] == "pps-installer-package-inventory.v1"
    assert manifest["payloads"][0]["package_inventory"]["missing_required_count"] == 0
    assert len(manifest["payloads"][0]["package_inventory"]["sha256"]) == 64
    assert {entry["kind"] for entry in manifest["entrypoints"]} >= {"dashboard", "experiment_runner", "docs"}


def test_build_download_manifest_requires_payload(tmp_path: Path):
    module = _load_module()
    missing = tmp_path / "missing.zip"

    try:
        module.build_manifest(
            payload=missing,
            payload_url="https://zenodo.org/records/123/files/missing.zip",
            version="0.1.0",
            source_tag="v0.1.0",
            source_commit="abc123",
            zenodo_doi="10.5281/zenodo.123",
        )
    except FileNotFoundError:
        return
    raise AssertionError("build_manifest accepted a missing payload")

