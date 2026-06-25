"""Preload-profile asset inventory helpers.

The inventory is public/static, but asset verification and retrieval happen
through the local companion backend.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

from .runtime_paths import repo_root


REPO_ROOT = repo_root()
INVENTORY_RELATIVE_PATH = Path("assets") / "preloads" / "preload_inventory.json"
INVENTORY_SCHEMA = "pps-preload-asset-inventory.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_preload_inventory(repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    path = Path(repo_root) / INVENTORY_RELATIVE_PATH
    if not path.exists():
        return {
            "schema": INVENTORY_SCHEMA,
            "profiles": [],
            "default_policy": {
                "asset_mode": "not_indexed",
                "retrieval_strategy": "generate_on_local_companion",
            },
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("schema", INVENTORY_SCHEMA)
    data.setdefault("profiles", [])
    return data


def preload_inventory_payload(template_ids: list[str], *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    inventory = load_preload_inventory(repo_root)
    return {
        "schema": inventory.get("schema", INVENTORY_SCHEMA),
        "inventory_path": str(INVENTORY_RELATIVE_PATH.as_posix()),
        "base_url": inventory.get("base_url", ""),
        "segments": list(inventory.get("segments", [])),
        "default_policy": inventory.get("default_policy", {}),
        "profiles": [
            profile_asset_status(template_id, inventory=inventory, repo_root=repo_root)
            for template_id in template_ids
        ],
    }


def profile_asset_status(
    template_id: str,
    *,
    inventory: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    inventory = inventory or load_preload_inventory(repo_root)
    entry = _profile_entry(template_id, inventory)
    if entry is None:
        return _default_status(template_id, inventory)

    assets = [_asset_status(asset, inventory=inventory, repo_root=repo_root) for asset in entry.get("assets", [])]
    missing = [asset for asset in assets if not asset["exists"]]
    hash_mismatch = [asset for asset in assets if asset["exists"] and asset.get("sha256_ok") is False]
    if not assets:
        status = "recipe_only"
    elif not missing and not hash_mismatch:
        status = "ready"
    elif missing:
        status = "missing"
    else:
        status = "hash_mismatch"

    runner_readiness = entry.get(
        "runner_readiness",
        (entry.get("recreation_status") or {}).get("runner_readiness", ""),
    )
    profile_checks_passed = bool(
        entry.get("profile_checks_passed", (entry.get("recreation_status") or {}).get("profile_checks_passed", False))
    )
    segment_gate_passed = bool(
        entry.get(
            "segment_0_to_4_profile_checks_passed",
            (entry.get("recreation_status") or {}).get("segment_0_to_4_profile_checks_passed", False),
        )
    )
    finished_profile = runner_readiness == "ready" and profile_checks_passed and segment_gate_passed

    return {
        "template_id": template_id,
        "status": status,
        "ready": status == "ready",
        "asset_mode": entry.get("asset_mode", "recipe_only"),
        "retrieval_strategy": entry.get("retrieval_strategy", "generate_on_local_companion"),
        "profile_manifest": entry.get("profile_manifest", ""),
        "profile_parameters_manifest": entry.get("profile_parameters_manifest", ""),
        "visible_variant_label": entry.get("visible_variant_label", ""),
        "variant_display": entry.get("variant_display", entry.get("title", "")),
        "recreation_status": dict(entry.get("recreation_status") or {}),
        "runner_readiness": runner_readiness,
        "profile_checks_passed": profile_checks_passed,
        "segment_0_to_4_profile_checks_passed": segment_gate_passed,
        "finished_profile": finished_profile,
        "segment_6_launchable": finished_profile,
        "profile_completion_status": "finished_segment_6_launchable" if finished_profile else "unfinished_preload",
        "primary_recreation_category": entry.get(
            "primary_recreation_category",
            (entry.get("recreation_status") or {}).get("primary_category", ""),
        ),
        "missing_parameter_count": int(
            entry.get("missing_parameter_count")
            or (entry.get("recreation_status") or {}).get("missing_parameter_count")
            or 0
        ),
        "unsupported_structure_count": int(
            entry.get("unsupported_structure_count")
            or (entry.get("recreation_status") or {}).get("unsupported_structure_count")
            or 0
        ),
        "local_only": bool(entry.get("local_only", True)),
        "asset_count": len(assets),
        "ready_asset_count": sum(1 for asset in assets if asset["exists"] and asset.get("sha256_ok") is not False),
        "assets": assets,
        "catalog_segments": list(entry.get("catalog_segments", [])),
        "message": _status_message(status, entry, assets),
    }


def ensure_preload_assets(
    template_id: str,
    *,
    inventory: dict[str, Any] | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    inventory = inventory or load_preload_inventory(repo_root)
    entry = _profile_entry(template_id, inventory)
    if entry is None:
        return _default_status(template_id, inventory)

    base_url = str(inventory.get("base_url", "")).rstrip("/")
    for asset in entry.get("assets", []):
        rel_path = str(asset.get("path") or asset.get("local_path") or "").strip()
        if not rel_path:
            continue
        local_path = Path(repo_root) / rel_path
        if local_path.exists():
            continue
        remote_url = str(asset.get("url") or "").strip()
        if not remote_url and base_url:
            remote_url = f"{base_url}/{_url_path(rel_path)}"
        if not remote_url:
            continue
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(remote_url, timeout=30) as response:
            local_path.write_bytes(response.read())

    return profile_asset_status(template_id, inventory=inventory, repo_root=repo_root)


def _profile_entry(template_id: str, inventory: dict[str, Any]) -> dict[str, Any] | None:
    for entry in inventory.get("profiles", []):
        if entry.get("template_id") == template_id:
            return dict(entry)
    return None


def _asset_status(asset: dict[str, Any], *, inventory: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    rel_path = str(asset.get("path") or asset.get("local_path") or "").strip()
    local_path = Path(repo_root) / rel_path
    exists = bool(rel_path and local_path.exists())
    expected_sha = str(asset.get("sha256") or "").strip()
    actual_sha = sha256_file(local_path) if exists else ""
    base_url = str(inventory.get("base_url", "")).rstrip("/")
    remote_url = str(asset.get("url") or "").strip()
    if not remote_url and base_url and rel_path:
        remote_url = f"{base_url}/{_url_path(rel_path)}"
    return {
        "label": str(asset.get("label") or Path(rel_path).stem),
        "path": rel_path,
        "url": remote_url,
        "exists": exists,
        "sha256": actual_sha,
        "expected_sha256": expected_sha,
        "sha256_ok": (actual_sha == expected_sha) if exists and expected_sha else None,
        "duration_s": asset.get("duration_s"),
        "sample_rate": asset.get("sample_rate"),
        "channels": asset.get("channels"),
        "source_kind": asset.get("source_kind", ""),
        "noise_type": asset.get("noise_type", ""),
        "tone_type": asset.get("tone_type", asset.get("noise_type", "")),
        "motion_mode": asset.get("motion_mode", ""),
        "render_mode": asset.get("render_mode", ""),
        "include_tactile": asset.get("include_tactile"),
        "trajectory_snapshot": asset.get("trajectory_snapshot", {}),
    }


def _default_status(template_id: str, inventory: dict[str, Any]) -> dict[str, Any]:
    policy = dict(inventory.get("default_policy", {}))
    return {
        "template_id": template_id,
        "status": "not_indexed",
        "ready": False,
        "asset_mode": policy.get("asset_mode", "not_indexed"),
        "retrieval_strategy": policy.get("retrieval_strategy", "generate_on_local_companion"),
        "profile_manifest": "",
        "profile_parameters_manifest": "",
        "visible_variant_label": "",
        "variant_display": template_id,
        "recreation_status": {},
        "runner_readiness": "",
        "profile_checks_passed": False,
        "segment_0_to_4_profile_checks_passed": False,
        "finished_profile": False,
        "segment_6_launchable": False,
        "profile_completion_status": "unfinished_preload",
        "primary_recreation_category": "",
        "missing_parameter_count": 0,
        "unsupported_structure_count": 0,
        "local_only": True,
        "asset_count": 0,
        "ready_asset_count": 0,
        "assets": [],
        "catalog_segments": [],
        "message": "No preload asset entry exists yet; use the local companion to bake this profile on demand.",
    }


def _status_message(status: str, entry: dict[str, Any], assets: list[dict[str, Any]]) -> str:
    if status == "ready":
        return "Bundled local preload assets are present and verified."
    if status == "recipe_only":
        return str(
            entry.get("message")
            or "This profile is indexed, but its looming assets are generated by the local companion on demand."
        )
    if status == "missing":
        missing = ", ".join(asset["label"] for asset in assets if not asset["exists"])
        return f"Preload assets are indexed but missing locally: {missing}."
    if status == "hash_mismatch":
        return "One or more preload assets exist locally but do not match the inventory hash."
    return "Preload asset status is unknown."


def _url_path(path: str) -> str:
    return path.replace("\\", "/")
