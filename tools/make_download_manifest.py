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
    payload_kind: str = "offline_lab_windows_x64",
    platform: str = "windows-amd64",
) -> dict:
    payload = payload.resolve()
    if not payload.is_file():
        raise FileNotFoundError(f"Payload does not exist: {payload}")
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
                "path": "windows/Launch_HTML_Dashboard.bat",
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

