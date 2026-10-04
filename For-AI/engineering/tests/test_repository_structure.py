from __future__ import annotations

import json
import subprocess
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[3]
MANIFEST_DIR = ROOT / "distributions" / "manifests"
CONTRACT_CATALOG_PATH = ROOT / "docs" / "contracts" / "catalog.v1.json"
ALLOWLIST_PATH = ROOT / "For-AI" / "engineering" / "migration" / "root-allowlist.v1.json"
FORBIDDEN_DISTRIBUTION_PARTS = {
    "For-AI",
    "artifacts",
    "local_data",
    "participant_data",
    "private_not_for_public",
    "generated_outputs",
    "unreviewed",
}


def _tracked_paths() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.replace("\\", "/") for line in completed.stdout.splitlines() if line]


def _manifests(version: str = "v1") -> dict[str, dict]:
    result = {}
    for path in MANIFEST_DIR.glob(f"*.{version}.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") == f"pps-component-manifest.{version}":
            result[data["component_id"]] = data
    return result


def test_every_tracked_root_path_is_classified():
    allowlist = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    allowed = set(allowlist["tracked_directories"]) | set(allowlist["tracked_files"])
    unclassified = sorted({path.split("/", 1)[0] for path in _tracked_paths()} - allowed)
    assert unclassified == []


def test_component_contract_and_dependency_versions_are_exact():
    manifests = _manifests()
    assert set(manifests) == {"shared", "designer", "runner", "full"}
    version = manifests["shared"]["version"]
    assert manifests["designer"]["dependencies"] == [{"component_id": "shared", "version": version}]
    assert manifests["runner"]["dependencies"] == [{"component_id": "shared", "version": version}]
    assert {dependency["component_id"] for dependency in manifests["full"]["dependencies"]} == {
        "shared", "designer", "runner"
    }
    assert manifests["full"]["composition"] == {"shared_copies": 1, "central_hub": False}


def test_v2_full_owns_both_apps_and_one_compatible_shared_tree():
    manifests = _manifests("v2")
    assert set(manifests) == {"shared", "planner", "runner", "full"}
    version = manifests["shared"]["version"]
    assert all(manifest["version"] == version and manifest["platform"] == "windows-x64"
               for manifest in manifests.values())
    assert manifests["planner"]["dependencies"] == [{"component_id": "shared", "version": version}]
    assert manifests["runner"]["dependencies"] == [{"component_id": "shared", "version": version}]
    assert manifests["full"]["dependencies"] == [
        {"component_id": component, "version": version}
        for component in ("shared", "planner", "runner")
    ]
    assert manifests["full"]["composition"] == {"shared_copies": 1, "central_hub": False}
    assert manifests["full"]["entrypoints"] == (
        manifests["planner"]["entrypoints"] + manifests["runner"]["entrypoints"]
    )


def test_json_contract_catalog_points_to_its_existing_owners():
    catalog = json.loads(CONTRACT_CATALOG_PATH.read_text(encoding="utf-8"))
    assert catalog["schema"] == "pps-json-contract-catalog.v1"
    contracts = catalog["contracts"]
    ids = [contract["id"] for contract in contracts]
    assert len(ids) == len(set(ids))
    tracked = set(_tracked_paths())
    for contract in contracts:
        assert contract["id"].startswith(("pps-", "pps.")) and ".v" in contract["id"]
        assert contract["boundary"].strip()
        owner = contract["owner"]
        assert owner in tracked
        assert contract["id"] in (ROOT / owner).read_text(encoding="utf-8")


def test_every_install_mapping_has_exactly_one_owner_and_is_public():
    for version in ("v1", "v2"):
        owners: dict[str, str] = {}
        for component_id, manifest in _manifests(version).items():
            exclusions = set(manifest["exclusions"])
            assert "For-AI/**" in exclusions
            for mapping in manifest["source_to_install"]:
                source = PurePosixPath(mapping["source"])
                assert not (set(source.parts) & FORBIDDEN_DISTRIBUTION_PARTS)
                assert "android" not in mapping["source"].lower()
                install = mapping["install"]
                assert install not in owners, f"{install} owned by {owners[install]} and {component_id}"
                owners[install] = component_id


def test_android_experiment_is_not_a_public_entrypoint_or_manifest_source():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "pps-android-lsl-command" not in pyproject
    assert "pps-android-lsl-monitor" not in pyproject
    manifest_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in MANIFEST_DIR.glob("*.v1.json")
        if "legacy" not in path.name
    ).lower()
    assert "android-companion" not in manifest_text
    assert "runner-companion" not in manifest_text
