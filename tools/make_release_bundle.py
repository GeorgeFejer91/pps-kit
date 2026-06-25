#!/usr/bin/env python
"""Create a reviewed source-and-assets release bundle."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tomllib
import zipfile
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPO_ROOT / "tools" / "release_audit.py"
DEFAULT_DIST_DIR = REPO_ROOT / "dist"


def _load_release_audit():
    spec = importlib.util.spec_from_file_location("release_audit", AUDIT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {AUDIT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _project_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bundle_name(version: str) -> str:
    return f"peripersonal-space-toolkit-{version}-bundle.zip"


def create_bundle(output_path: Path | None = None, *, force: bool = False) -> Path:
    release_audit = _load_release_audit()
    problems = release_audit.run_audit()
    if problems:
        joined = "\n  - ".join(problems)
        raise RuntimeError(f"Release audit failed:\n  - {joined}")

    version = _project_version()
    if output_path is None:
        output_path = DEFAULT_DIST_DIR / _bundle_name(version)
    output_path = output_path.resolve()
    if output_path.exists() and not force:
        raise FileExistsError(f"{output_path} already exists; pass --force to replace it")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    files = sorted(release_audit.iter_public_files(REPO_ROOT), key=lambda p: p.relative_to(REPO_ROOT).as_posix())
    manifest_files = []
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in files:
            rel = path.relative_to(REPO_ROOT).as_posix()
            bundle.write(path, rel)
            stat = path.stat()
            manifest_files.append(
                {
                    "path": rel,
                    "bytes": stat.st_size,
                    "sha256": _sha256_file(path),
                }
            )

        manifest = {
            "schema": "pps-release-bundle-manifest.v1",
            "project": "peripersonal-space-toolkit",
            "version": version,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "file_count": len(manifest_files),
            "files": manifest_files,
        }
        bundle.writestr(
            "bundle_manifest.json",
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        )

    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Destination zip path. Defaults to dist/<project-version>-bundle.zip.")
    parser.add_argument("--force", action="store_true", help="Replace an existing bundle at the output path.")
    args = parser.parse_args(argv)

    try:
        bundle_path = create_bundle(args.output, force=args.force)
    except Exception as exc:
        print(f"Bundle creation failed: {exc}")
        return 1

    digest = _sha256_file(bundle_path)
    print(f"Created {bundle_path}")
    print(f"SHA256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
