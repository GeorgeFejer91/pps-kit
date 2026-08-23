#!/usr/bin/env python
"""Assemble one installable PPS component tree from its tracked manifest."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
INVENTORY_TOOL = Path(__file__).with_name("package_inventory.py")


def _inventory_module():
    spec = importlib.util.spec_from_file_location("pps_package_inventory", INVENTORY_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {INVENTORY_TOOL}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _filesystem_path(path: Path) -> Path:
    """Return a Windows extended-length path without changing logical paths."""

    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return Path(resolved)
    if resolved.startswith("\\\\"):
        return Path(f"\\\\?\\UNC\\{resolved[2:]}")
    return Path(f"\\\\?\\{resolved}")


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(_filesystem_path(source), _filesystem_path(destination), dirs_exist_ok=False)
    else:
        shutil.copy2(_filesystem_path(source), _filesystem_path(destination))


def assemble(component_id: str, output: Path) -> dict:
    module = _inventory_module()
    manifests = module.load_manifests()
    components = module.resolve_components(component_id, manifests)
    output = output.resolve()
    if output.exists():
        shutil.rmtree(_filesystem_path(output))
    output.mkdir(parents=True)

    destinations: set[str] = set()
    for manifest in components:
        for mapping in manifest.get("source_to_install", []):
            source_text = str(mapping["source"])
            if source_text == "For-AI" or source_text.startswith("For-AI/"):
                raise RuntimeError(f"Refusing internal source: {source_text}")
            destination_text = str(mapping["install"])
            if destination_text in destinations:
                raise RuntimeError(f"Duplicate install destination: {destination_text}")
            destinations.add(destination_text)
            source = ROOT / source_text
            if not source.exists():
                raise FileNotFoundError(f"Missing {manifest['component_id']} input: {source_text}")
            _copy(source, output / destination_text)

    inventory = module.build_inventory(output, component_id)
    if inventory["missing_required"]:
        raise RuntimeError(f"Incomplete component inventory: {inventory['missing_required']}")
    inventory_path = output / "pps_package_inventory.v1.json"
    module.write_inventory(inventory, inventory_path)
    for manifest in components:
        source = Path(manifest["_path"])
        _copy(source, output / "component-manifests" / source.name)
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--component", choices=("shared", "designer", "runner", "full"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    inventory = assemble(args.component, args.output)
    print(json.dumps(inventory["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
