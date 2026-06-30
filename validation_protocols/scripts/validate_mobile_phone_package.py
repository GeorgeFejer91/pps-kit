"""Validate Android phone-owned PPS mobile run package manifests."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.mobile_phone_runtime import (  # noqa: E402
    MOBILE_PACKAGE_SCHEMA,
    validate_mobile_package_manifest,
)


def load_mobile_manifest(path: Path) -> dict[str, Any]:
    if path.is_dir():
        for candidate in ("manifest.json", "run_package_manifest.json", "mobile_package_manifest.json"):
            manifest_path = path / candidate
            if manifest_path.is_file():
                return _read_json(manifest_path)
        raise FileNotFoundError(f"{path} does not contain a mobile run package manifest JSON")
    if path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="pps-mobile-package-") as temp_dir:
            temp_root = Path(temp_dir)
            with zipfile.ZipFile(path) as archive:
                manifest_members = [
                    name
                    for name in archive.namelist()
                    if name.endswith("manifest.json")
                    or name.endswith("run_package_manifest.json")
                    or name.endswith("mobile_package_manifest.json")
                ]
                if not manifest_members:
                    raise FileNotFoundError(f"{path} does not contain a mobile run package manifest JSON")
                manifest_name = sorted(manifest_members)[0]
                archive.extract(manifest_name, temp_root)
                return _read_json(temp_root / manifest_name)
    return _read_json(path)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def _write_report(result: dict[str, Any], output_dir: Path, source_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_json = output_dir / "mobile_phone_package_validation.json"
    report_md = output_dir / "mobile_phone_package_validation.md"
    report_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Mobile Phone Package Validation",
        "",
        f"- Source: `{source_path}`",
        f"- Result: `{'PASS' if result.get('ok') else 'FAIL'}`",
        f"- Package: `{result.get('summary', {}).get('package_id', '')}`",
        f"- Blocks: `{result.get('summary', {}).get('block_count', 0)}`",
        f"- Building blocks: `{result.get('summary', {}).get('building_block_count', 0)}`",
        "",
    ]
    if result.get("failures"):
        lines.extend(["## Failures", *[f"- {item}" for item in result["failures"]], ""])
    if result.get("warnings"):
        lines.extend(["## Warnings", *[f"- {item}" for item in result["warnings"]], ""])
    report_md.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path, help="Mobile manifest JSON, package folder, or exported ZIP.")
    parser.add_argument("--allow-legacy-schema", action="store_true", help=f"Do not require {MOBILE_PACKAGE_SCHEMA}.")
    parser.add_argument("--require-phone-owned-session", action="store_true")
    parser.add_argument("--require-building-blocks", action="store_true")
    parser.add_argument("--require-lightweight-scheduled-blocks", action="store_true")
    parser.add_argument("--allow-missing-assets", action="store_true")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for JSON/Markdown validation reports.")
    args = parser.parse_args(argv)

    result = validate_mobile_package_manifest(
        load_mobile_manifest(args.manifest),
        require_v2=not args.allow_legacy_schema,
        require_phone_owned_session=args.require_phone_owned_session,
        require_building_blocks=args.require_building_blocks,
        require_lightweight_scheduled_blocks=args.require_lightweight_scheduled_blocks,
        require_available_assets=not args.allow_missing_assets,
    ).to_json()
    if args.output_dir:
        _write_report(result, args.output_dir, args.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
