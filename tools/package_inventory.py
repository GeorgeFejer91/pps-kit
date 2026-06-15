#!/usr/bin/env python
"""Build and validate the PPS offline installer package inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SCHEMA = "pps-installer-package-inventory.v1"
DEFAULT_DEFINITION_OUTPUT = REPO_ROOT / "windows" / "installer_package_inventory.v1.json"


INVENTORY_ITEMS: list[dict[str, Any]] = [
    {
        "path": "dist/PPSExperimentRunner/PPSExperimentRunner.exe",
        "kind": "generated_binary",
        "role": "active packaged native Experiment Runner",
        "required": True,
        "source": "built by windows/Build_Experiment_Runner_Exe.ps1",
    },
    {
        "path": "dist/PPSExperimentRunner",
        "kind": "generated_directory",
        "role": "PyInstaller onedir runner resources",
        "required": True,
        "source": "built by windows/Build_Experiment_Runner_Exe.ps1",
    },
    {
        "path": "dist/PPSExperimentRunner/_internal/PySide6/plugins/platforms/qwindows.dll",
        "kind": "qt_platform_plugin",
        "role": "required Qt Windows platform plugin for PPSExperimentRunner.exe startup",
        "required": True,
        "source": "collected from PySide6 by windows/PPSExperimentRunner.spec",
    },
    {
        "path": "windows/downloader",
        "kind": "installer_source",
        "role": "lightweight GitHub-hosted downloader source package",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/Build_PPS_Downloader.ps1",
        "kind": "installer_build_script",
        "role": "builds PPS-Toolkit-Downloader.exe",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/Build_PPS_Distribution.ps1",
        "kind": "installer_build_script",
        "role": "builds the offline lab ZIP and download manifest",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/Setup_Windows_App.ps1",
        "kind": "launcher_support",
        "role": "creates local venv for source installs",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/Launch_HTML_Dashboard.bat",
        "kind": "entrypoint",
        "role": "starts the local HTML dashboard",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/Start_Website_Companion.bat",
        "kind": "entrypoint",
        "role": "starts the companion backend for GitHub Pages dashboard use",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/Launch_Experiment_Runner.bat",
        "kind": "entrypoint",
        "role": "opens the packaged native Experiment Runner",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/Create_Desktop_Shortcut.ps1",
        "kind": "installer_support",
        "role": "creates local dashboard and runner shortcuts",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "tools/make_download_manifest.py",
        "kind": "installer_manifest_tool",
        "role": "writes pps_download_manifest.v1.json for downloader verification",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "tools/make_offline_lab_zip.py",
        "kind": "installer_archive_tool",
        "role": "creates the heavyweight offline lab ZIP",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "tools/package_inventory.py",
        "kind": "installer_inventory_tool",
        "role": "validates required files before packaging",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "tools/check_qt_runtime.py",
        "kind": "installer_preflight_tool",
        "role": "validates PySide6 import and packaged Qt platform plugin presence",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "windows/installer_package_inventory.v1.json",
        "kind": "installer_package_definition",
        "role": "repo-visible installer package inventory definition",
        "required": True,
        "source": "tracked/generated from tools/package_inventory.py",
    },
    {
        "path": "src/peripersonal_space_toolkit/dashboard",
        "kind": "dashboard_asset_tree",
        "role": "packaged local HTML dashboard",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "index.html",
        "kind": "hosted_dashboard_entry",
        "role": "GitHub Pages static dashboard entrypoint",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "src/peripersonal_space_toolkit/viewer",
        "kind": "trajectory_viewer_asset_tree",
        "role": "local trajectory viewer and Three.js assets",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "src/peripersonal_space_toolkit/assets",
        "kind": "app_identity_assets",
        "role": "icons and app identity resources",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "assets/preloads/preload_inventory.json",
        "kind": "preload_catalog",
        "role": "machine-readable preload asset inventory",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "assets/preloads/profile_recreation_status.json",
        "kind": "preload_readiness_ledger",
        "role": "finished-profile and runner-readiness ledger",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "assets/preloads",
        "kind": "preload_asset_tree",
        "role": "segment-mirrored preload catalogs and bundled auditory assets",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "assets/breathing",
        "kind": "audio_asset_tree",
        "role": "bundled Study 5 spoken instruction WAV assets",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "assets/tactile/default_tactile_cue.wav",
        "kind": "audio_asset",
        "role": "default tactile channel cue",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa",
        "kind": "hrir_asset",
        "role": "redistributable FABIAN/TU SOFA resource",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "study_templates",
        "kind": "study_template_tree",
        "role": "published-study and Study 5 preload templates",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "configs",
        "kind": "example_config_tree",
        "role": "example design and runner configs",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "data/sample",
        "kind": "sample_data_tree",
        "role": "deidentified sample analysis data",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "docs",
        "kind": "documentation_tree",
        "role": "user, hardware, validation, and release docs",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "README.md",
        "kind": "documentation",
        "role": "top-level quick start",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "LICENSE",
        "kind": "license",
        "role": "source license",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "THIRD_PARTY_LICENSES.md",
        "kind": "license",
        "role": "third-party license and attribution notes",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "CITATION.cff",
        "kind": "citation",
        "role": "citation metadata",
        "required": True,
        "source": "tracked",
    },
    {
        "path": "third_party/3dti_renderer/bin",
        "kind": "renderer_binary_tree",
        "role": "approved native 3DTI renderer binaries when available",
        "required": False,
        "source": "local/generated",
    },
    {
        "path": "third_party/3dti_AudioToolkit",
        "kind": "renderer_source_tree",
        "role": "pinned 3DTI source snapshot and attribution boundary",
        "required": False,
        "source": "tracked/pinned",
    },
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_stats(path: Path) -> tuple[int, int]:
    files = [item for item in path.rglob("*") if item.is_file()]
    return len(files), sum(item.stat().st_size for item in files)


def build_inventory(stage_root: Path | None = None) -> dict[str, Any]:
    root = stage_root.resolve() if stage_root else None
    items: list[dict[str, Any]] = []
    missing_required: list[str] = []
    optional_absent: list[str] = []

    for spec in INVENTORY_ITEMS:
        entry = dict(spec)
        if root is not None:
            target = root / spec["path"]
            exists = target.exists()
            entry["exists"] = exists
            if exists and target.is_file():
                entry["size_bytes"] = target.stat().st_size
                entry["sha256"] = sha256_file(target)
            elif exists and target.is_dir():
                file_count, total_size = directory_stats(target)
                entry["file_count"] = file_count
                entry["size_bytes"] = total_size
            elif spec.get("required"):
                missing_required.append(spec["path"])
            else:
                optional_absent.append(spec["path"])
        items.append(entry)

    required_count = sum(1 for item in INVENTORY_ITEMS if item.get("required"))
    optional_count = len(INVENTORY_ITEMS) - required_count
    inventory: dict[str, Any] = {
        "schema": INVENTORY_SCHEMA,
        "project": "peripersonal-space-toolkit",
        "purpose": "Defines and validates the files needed for the easy-download Windows offline lab package.",
        "stage_root": str(root) if root is not None else "",
        "created_utc": datetime.now(timezone.utc).isoformat() if root is not None else "",
        "summary": {
            "item_count": len(INVENTORY_ITEMS),
            "required_item_count": required_count,
            "optional_item_count": optional_count,
            "missing_required_count": len(missing_required),
            "optional_absent_count": len(optional_absent),
        },
        "missing_required": missing_required,
        "optional_absent": optional_absent,
        "items": items,
    }
    return inventory


def write_inventory(inventory: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-root", type=Path, default=None, help="Staged offline package root to validate.")
    parser.add_argument("--output", type=Path, default=DEFAULT_DEFINITION_OUTPUT)
    parser.add_argument("--strict", action="store_true", help="Fail if any required inventory item is missing.")
    args = parser.parse_args(argv)

    inventory = build_inventory(args.stage_root)
    write_inventory(inventory, args.output)
    print(f"Wrote {args.output}")
    missing = inventory["missing_required"]
    if missing:
        print("Missing required package items:")
        for path in missing:
            print(f"  {path}")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
