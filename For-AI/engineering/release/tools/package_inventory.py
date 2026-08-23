#!/usr/bin/env python
"""Resolve and validate PPS component inventories from tracked manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
MANIFEST_DIR = REPO_ROOT / "distributions" / "manifests"
COMPONENT_SCHEMA = "pps-component-manifest.v1"
INVENTORY_SCHEMA = "pps-resolved-component-inventory.v1"


def _filesystem_path(path: Path) -> Path:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return Path(resolved)
    if resolved.startswith("\\\\"):
        return Path(f"\\\\?\\UNC\\{resolved[2:]}")
    return Path(f"\\\\?\\{resolved}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifests(manifest_dir: Path = MANIFEST_DIR) -> dict[str, dict[str, Any]]:
    manifests: dict[str, dict[str, Any]] = {}
    for path in sorted(manifest_dir.glob("*.v1.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != COMPONENT_SCHEMA:
            continue
        component_id = str(data["component_id"])
        if component_id in manifests:
            raise ValueError(f"duplicate component manifest: {component_id}")
        data["_path"] = path
        manifests[component_id] = data
    return manifests


def resolve_components(component_id: str, manifests: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(current_id: str) -> None:
        if current_id in complete:
            return
        if current_id in visiting:
            raise ValueError(f"component dependency cycle at {current_id}")
        manifest = manifests.get(current_id)
        if manifest is None:
            raise ValueError(f"missing component manifest: {current_id}")
        visiting.add(current_id)
        for dependency in manifest.get("dependencies", []):
            dependency_id = str(dependency["component_id"])
            dependency_manifest = manifests.get(dependency_id)
            if dependency_manifest is None:
                raise ValueError(f"{current_id} requires missing component {dependency_id}")
            if str(dependency["version"]) != str(dependency_manifest["version"]):
                raise ValueError(
                    f"{current_id} requires {dependency_id} {dependency['version']}, "
                    f"found {dependency_manifest['version']}"
                )
            visit(dependency_id)
        visiting.remove(current_id)
        complete.add(current_id)
        resolved.append(manifest)

    visit(component_id)
    return resolved


def build_inventory(stage_root: Path | None = None, component_id: str = "full") -> dict[str, Any]:
    manifests = load_manifests()
    components = resolve_components(component_id, manifests)
    root = stage_root.resolve() if stage_root else None
    items: list[dict[str, Any]] = []
    missing_required: list[str] = []
    install_owners: dict[str, str] = {}

    for manifest in components:
        owner = str(manifest["component_id"])
        for mapping in manifest.get("source_to_install", []):
            source = str(mapping["source"])
            install = str(mapping["install"])
            if source == "For-AI" or source.startswith("For-AI/"):
                raise ValueError(f"internal source included by {owner}: {source}")
            previous_owner = install_owners.get(install)
            if previous_owner and previous_owner != owner:
                raise ValueError(f"install path {install} owned by both {previous_owner} and {owner}")
            install_owners[install] = owner
            entry: dict[str, Any] = {
                "component_id": owner,
                "source": source,
                "path": install,
                "kind": mapping["kind"],
                "required": True,
            }
            if root is not None:
                target = root / install
                entry["exists"] = target.exists()
                if not target.exists():
                    missing_required.append(install)
                elif target.is_file():
                    entry["size_bytes"] = target.stat().st_size
                    entry["sha256"] = sha256_file(target)
                else:
                    filesystem_target = _filesystem_path(target)
                    files = [path for path in filesystem_target.rglob("*") if path.is_file()]
                    entry["file_count"] = len(files)
                    entry["size_bytes"] = sum(path.stat().st_size for path in files)
            items.append(entry)

    component_hashes = {
        str(manifest["component_id"]): sha256_file(manifest["_path"])
        for manifest in components
    }
    return {
        "schema": INVENTORY_SCHEMA,
        "component_id": component_id,
        "version": str(manifests[component_id]["version"]),
        "stage_root": str(root) if root is not None else "",
        "created_utc": datetime.now(timezone.utc).isoformat() if root is not None else "",
        "resolved_components": [str(manifest["component_id"]) for manifest in components],
        "component_manifest_sha256": component_hashes,
        "summary": {
            "item_count": len(items),
            "required_item_count": len(items),
            "missing_required_count": len(missing_required),
        },
        "missing_required": missing_required,
        "items": items,
    }


def write_inventory(inventory: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("shared", "designer", "runner", "full"), default="full")
    parser.add_argument("--stage-root", type=Path, default=None, help="Installed product root to validate.")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist" / "pps-component-inventory.v1.json")
    parser.add_argument("--strict", action="store_true", help="Fail if a required installed path is missing.")
    args = parser.parse_args(argv)
    inventory = build_inventory(args.stage_root, args.component)
    write_inventory(inventory, args.output)
    print(f"Wrote {args.output}")
    if args.strict and inventory["missing_required"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
