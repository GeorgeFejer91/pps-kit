#!/usr/bin/env python
"""Create the PPS lightweight-downloader release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "pps_download_manifest.v1.json"
MANIFEST_SCHEMA = "pps-download-manifest.v1"
NI_DRIVER_PAGE_URL = "https://www.native-instruments.com/en/support/downloads/drivers-other-files/"
FLEXASIO_URL = "https://github.com/dechamps/FlexASIO/releases/download/flexasio-1.10b/FlexASIO-1.10b.exe"
FLEXASIO_SHA256 = "fe496bcc08d6c421c6244c8a60ac7b538560bda138000fd1a54ab8ebce031209"
FLEXASIO_SIZE_BYTES = 13749698


def project_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
    except Exception:
        return ""
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    *,
    payload: Path,
    payload_url: str,
    version: str,
    source_tag: str,
    source_commit: str,
    zenodo_doi: str,
    package_inventory: Path | None = None,
    payload_kind: str = "offline_lab_windows_x64",
    platform: str = "windows-amd64",
) -> dict:
    payload = payload.resolve()
    if not payload.is_file():
        raise FileNotFoundError(f"Payload does not exist: {payload}")
    inventory_payload: dict | None = None
    if package_inventory is not None:
        package_inventory = package_inventory.resolve()
        if not package_inventory.is_file():
            raise FileNotFoundError(f"Package inventory does not exist: {package_inventory}")
        inventory_data = json.loads(package_inventory.read_text(encoding="utf-8"))
        summary = inventory_data.get("summary", {})
        inventory_payload = {
            "schema": inventory_data.get("schema", ""),
            "filename": package_inventory.name,
            "path_in_payload": package_inventory.name,
            "sha256": sha256_file(package_inventory),
            "item_count": summary.get("item_count", 0),
            "required_item_count": summary.get("required_item_count", 0),
            "missing_required_count": summary.get("missing_required_count", 0),
        }
    return {
        "schema": MANIFEST_SCHEMA,
        "project": "peripersonal-space-toolkit",
        "version": version,
        "source_tag": source_tag,
        "source_commit": source_commit,
        "zenodo_doi": zenodo_doi,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "payloads": [
            {
                "kind": payload_kind,
                "label": "PPS Toolkit offline lab package (Windows x64)",
                "filename": payload.name,
                "url": payload_url,
                "size_bytes": payload.stat().st_size,
                "sha256": sha256_file(payload),
                "platform": platform,
                "package_inventory": inventory_payload,
                "contains": [
                    "PPSExperimentRunner.exe",
                    "local HTML dashboard and companion launchers",
                    "redistributable PPS assets",
                    "FABIAN SOFA HRTF resource",
                    "3DTI renderer binaries when built",
                    "documentation and license manifests",
                ],
            }
        ],
        "entrypoints": [
            {
                "kind": "dashboard",
                "label": "PPS Toolkit Dashboard",
                "path": "dist/PPSDashboardLauncher/PPSDashboardLauncher.exe",
                "shortcut": True,
            },
            {
                "kind": "experiment_runner",
                "label": "PPS Experiment Runner",
                "path": "windows/Launch_Experiment_Runner.bat",
                "shortcut": True,
            },
            {
                "kind": "docs",
                "label": "PPS Toolkit Windows Guide",
                "path": "docs/WINDOWS_APP.md",
                "shortcut": False,
            },
        ],
        "external_dependencies": [
            {
                "kind": "native_instruments_komplete_audio_asio",
                "label": "Native Instruments Komplete Audio ASIO Driver",
                "required_for": "validated synchronized 3-channel PPS playback",
                "provider": "Native Instruments",
                "provider_page_url": NI_DRIVER_PAGE_URL,
                "license_policy": (
                    "Provider proprietary driver. PPS Toolkit may point to the official provider source, "
                    "but must not mirror or redistribute the installer unless written redistribution permission is recorded."
                ),
                "redistribution_permitted": False,
                "auto_download": False,
                "install_instructions": [
                    "Open the provider page.",
                    "Download Komplete Audio 6 MK2 Driver 5.22.0 - Windows 10 or the current provider-listed successor.",
                    "Disconnect the interface, run setup.exe from the downloaded ZIP, reconnect the interface, and restart PPSExperimentRunner.exe.",
                ],
                "notes": "This is the publication-grade route for one hardware-clocked left/right/tactile output stream.",
            },
            {
                "kind": "flexasio_optional_fallback",
                "label": "FlexASIO optional diagnostic fallback",
                "required_for": "diagnostic fallback only; not publication timing validation",
                "provider": "Etienne Dechamps",
                "provider_page_url": "https://github.com/dechamps/FlexASIO/releases",
                "download_url": FLEXASIO_URL,
                "filename": "FlexASIO-1.10b.exe",
                "size_bytes": FLEXASIO_SIZE_BYTES,
                "sha256": FLEXASIO_SHA256,
                "license_policy": (
                    "FlexASIO source is MIT-licensed; ASIO trademark and SDK terms remain governed by Steinberg. "
                    "The installer is cached from the publisher GitHub release with SHA256 verification."
                ),
                "redistribution_permitted": True,
                "auto_download": True,
                "install_instructions": [
                    "Run the cached FlexASIO installer only for diagnostic fallback when no native vendor ASIO driver is available.",
                    "Revalidate route identity, latency, and interchannel skew before using any fallback in a study.",
                ],
                "notes": "FlexASIO wraps Windows audio APIs through PortAudio and does not replace the native Komplete Audio ASIO route.",
            },
        ],
        "uninstall": {
            "kind": "remove_folder",
            "instructions": "Remove the installed version folder under %LOCALAPPDATA%\\PPS Toolkit\\versions and delete the PPS Toolkit shortcuts.",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload", type=Path, required=True, help="Heavyweight offline lab package ZIP.")
    parser.add_argument("--payload-url", required=True, help="Final Zenodo download URL for the payload.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output pps_download_manifest.v1.json path.")
    parser.add_argument("--version", default=project_version(), help="Release version.")
    parser.add_argument("--source-tag", default="", help="Git release tag. Defaults to v<version>.")
    parser.add_argument("--source-commit", default="", help="Git source commit. Defaults to current HEAD when available.")
    parser.add_argument("--zenodo-doi", default="", help="Versioned Zenodo DOI or concept DOI.")
    parser.add_argument("--package-inventory", type=Path, default=None, help="Generated package inventory included in the payload.")
    parser.add_argument("--payload-kind", default="offline_lab_windows_x64")
    parser.add_argument("--platform", default="windows-amd64")
    args = parser.parse_args(argv)

    source_tag = args.source_tag or f"v{args.version}"
    source_commit = args.source_commit or git_commit()
    manifest = build_manifest(
        payload=args.payload,
        payload_url=args.payload_url,
        version=args.version,
        source_tag=source_tag,
        source_commit=source_commit,
        zenodo_doi=args.zenodo_doi,
        package_inventory=args.package_inventory,
        payload_kind=args.payload_kind,
        platform=args.platform,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Payload SHA256: {manifest['payloads'][0]['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

