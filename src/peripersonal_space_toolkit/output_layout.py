"""Shared layout for runner output-environment metadata files."""

from __future__ import annotations

import os
from pathlib import Path


BRIDGE_MANIFEST_FILENAME = "dashboard_runner_bridge_manifest.v1.json"
OUTPUT_DIARY_FILENAME = "output_diary.v1.jsonl"
ACQUISITION_PROFILE_SNAPSHOT_DIRNAME = "study_profile_snapshot_DO_NOT_DELETE"
LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAME = "study_profile_snapshot"


def output_metadata_dir(output_folder: Path | str) -> Path:
    """Return the folder that owns persistent environment metadata."""
    return Path(output_folder).expanduser() / ACQUISITION_PROFILE_SNAPSHOT_DIRNAME


def legacy_output_metadata_dir(output_folder: Path | str) -> Path:
    return Path(output_folder).expanduser() / LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAME


def output_diary_path(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / OUTPUT_DIARY_FILENAME


def bridge_manifest_path(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / BRIDGE_MANIFEST_FILENAME


def metadata_file_candidates(
    output_folder: Path | str,
    filename: str,
    *,
    include_legacy: bool = True,
    include_root: bool = True,
) -> list[Path]:
    root = Path(output_folder).expanduser()
    candidates = [output_metadata_dir(root) / filename]
    if include_legacy:
        candidates.append(legacy_output_metadata_dir(root) / filename)
    if include_root:
        candidates.append(root / filename)
    unique: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path)
        if key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def find_existing_metadata_file(output_folder: Path | str, filename: str) -> Path | None:
    for candidate in metadata_file_candidates(output_folder, filename):
        if os.path.isfile(_filesystem_path(candidate)):
            return candidate
    return None


def is_output_metadata_dir(path: Path | str) -> bool:
    return Path(path).name in {
        ACQUISITION_PROFILE_SNAPSHOT_DIRNAME,
        LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAME,
    }


def output_root_for_metadata_path(path: Path | str) -> Path:
    target = Path(path).expanduser()
    parent = target.parent
    if is_output_metadata_dir(parent):
        return parent.parent
    return parent


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    text = str(resolved)
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text
