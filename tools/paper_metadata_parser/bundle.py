from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .parser import ARTIFACT_DIR, AUDIT_DIR


BUNDLE_DIRNAME = "resume_bundles"
INVENTORY_FILENAME = "local_artifact_inventory.json"
MAX_HASH_BYTES = 1024 * 1024 * 1024
INCLUDED_TOP_LEVEL = {"publication_pdfs", "supplements", "extracted", "acquisition_status.json"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            if total > MAX_HASH_BYTES:
                raise ValueError(f"Refusing to hash unexpectedly large file: {path}")
            digest.update(chunk)
    return digest.hexdigest()


def artifact_category(relative_path: Path) -> str:
    parts = relative_path.parts
    if not parts:
        return "unknown"
    if parts[0] == "publication_pdfs":
        return "publication_pdf"
    if parts[0] == "supplements":
        return "supplement"
    if parts[0] == "extracted":
        return "extracted_text_or_parser_output"
    if parts[0] == "tooling":
        return "local_tooling"
    return parts[0]


def record_id_for_artifact(relative_path: Path) -> str:
    parts = relative_path.parts
    if not parts:
        return ""
    if parts[0] == "publication_pdfs":
        return Path(parts[-1]).stem
    if parts[0] == "supplements" and len(parts) > 1:
        return parts[1]
    if parts[0] == "extracted":
        if len(parts) > 2 and parts[1] in {"fallback", "supplements"}:
            return parts[2]
        if len(parts) > 2 and parts[1] == "opendataloader":
            return Path(parts[2]).stem
    return ""


def iter_artifacts(artifact_root: Path) -> list[Path]:
    if not artifact_root.exists():
        return []
    files: list[Path] = []
    for path in sorted(artifact_root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(artifact_root)
        if relative.parts and relative.parts[0] == BUNDLE_DIRNAME:
            continue
        if relative.parts and relative.parts[0] not in INCLUDED_TOP_LEVEL:
            continue
        files.append(path)
    return files


def build_inventory(repo_root: Path, *, create_zip: bool = True) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    artifact_root = repo_root / ARTIFACT_DIR
    audit_dir = repo_root / AUDIT_DIR
    bundle_dir = artifact_root / BUNDLE_DIRNAME
    files = iter_artifacts(artifact_root)
    generated_at = datetime.now(timezone.utc).isoformat()

    entries: list[dict[str, Any]] = []
    total_bytes = 0
    for path in files:
        relative_artifact = path.relative_to(artifact_root)
        relative_repo = path.relative_to(repo_root)
        size = path.stat().st_size
        total_bytes += size
        entries.append(
            {
                "relative_path": relative_repo.as_posix(),
                "artifact_relative_path": relative_artifact.as_posix(),
                "category": artifact_category(relative_artifact),
                "record_id": record_id_for_artifact(relative_artifact),
                "size_bytes": size,
                "sha256": sha256_file(path),
            }
        )

    bundle_payload: dict[str, Any] = {
        "created": False,
        "relative_path": "",
        "size_bytes": 0,
        "sha256": "",
    }
    if create_zip and files:
        bundle_dir.mkdir(parents=True, exist_ok=True)
        bundle_path = bundle_dir / "paper_metadata_audit_artifacts_latest.zip"
        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in files:
                archive.write(path, path.relative_to(artifact_root).as_posix())
        bundle_payload = {
            "created": True,
            "relative_path": bundle_path.relative_to(repo_root).as_posix(),
            "size_bytes": bundle_path.stat().st_size,
            "sha256": sha256_file(bundle_path),
        }

    category_counts = Counter(entry["category"] for entry in entries)
    inventory = {
        "schema": "pps-paper-metadata-local-artifact-inventory.v1",
        "generated_at": generated_at,
        "artifact_root": ARTIFACT_DIR.as_posix(),
        "copyright_boundary": (
            "This tracked inventory stores relative paths, sizes, and hashes only. "
            "The PDFs, supplements, extracted text, and local ZIP bundle remain ignored local artifacts and must not be committed to the public repository."
        ),
        "restore_note": (
            "To resume on the same machine, keep artifacts/paper_metadata_audit/ in place. "
            "To move work privately, transfer the ignored ZIP bundle named below outside the public Git repo, extract it into artifacts/paper_metadata_audit/, then run python -m tools.paper_metadata_parser --refresh."
        ),
        "artifact_file_count": len(entries),
        "artifact_total_bytes": total_bytes,
        "category_counts": dict(sorted(category_counts.items())),
        "local_bundle": bundle_payload,
        "files": entries,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / INVENTORY_FILENAME).write_text(
        json.dumps(inventory, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return inventory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a GitHub-safe inventory and ignored local ZIP backup for paper metadata audit artifacts."
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--no-zip",
        action="store_true",
        help="Only write the tracked inventory; do not create/update the ignored local ZIP bundle.",
    )
    args = parser.parse_args(argv)
    inventory = build_inventory(args.repo_root, create_zip=not args.no_zip)
    print(
        json.dumps(
            {
                "artifact_file_count": inventory["artifact_file_count"],
                "artifact_total_bytes": inventory["artifact_total_bytes"],
                "category_counts": inventory["category_counts"],
                "local_bundle": inventory["local_bundle"],
            },
            indent=2,
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
