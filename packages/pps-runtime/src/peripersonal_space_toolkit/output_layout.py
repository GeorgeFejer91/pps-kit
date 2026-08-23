"""Shared layout for runner output-environment metadata files."""

from __future__ import annotations

import os
from pathlib import Path


BRIDGE_MANIFEST_FILENAME = "dashboard_runner_bridge_manifest.v1.json"
OUTPUT_DIARY_FILENAME = "output_diary.v1.jsonl"
ACQUISITION_PROFILE_SNAPSHOT_DIRNAME = "Experiment_context_folder_DO_NOT_DELETE"
PROJECT_STATE_DIRNAME = "project_state"
PROFILE_SNAPSHOT_DIRNAME = "profile_snapshot"
SHARED_INSTRUCTIONS_DIRNAME = "shared_instructions"
PREPARED_BLOCKS_DIRNAME = "prepared_blocks"
RUNNER_LOGS_DIRNAME = "runner_logs"
VERBOSE_EVENTS_DIRNAME = "verbose_events"
VALIDATION_REPORTS_DIRNAME = "validation_reports"
DATA_ANALYTICS_DIRNAME = "Data_Analytics"
DATA_MIN_DIRNAME = "1.Data_min"
DATA_MAX_DIRNAME = "2.Data_max"
DATA_MIN_MASTER_FILENAME = "master_successful_participants.csv"
CONTEXT_CHILD_DIRNAMES = {
    PROJECT_STATE_DIRNAME,
    PROFILE_SNAPSHOT_DIRNAME,
    SHARED_INSTRUCTIONS_DIRNAME,
    PREPARED_BLOCKS_DIRNAME,
    RUNNER_LOGS_DIRNAME,
    VERBOSE_EVENTS_DIRNAME,
    VALIDATION_REPORTS_DIRNAME,
}
LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAME = "study_profile_snapshot"
LEGACY_PROTECTED_PROFILE_SNAPSHOT_DIRNAME = "study_profile_snapshot_DO_NOT_DELETE"
LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAMES = (
    LEGACY_PROTECTED_PROFILE_SNAPSHOT_DIRNAME,
    LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAME,
)


def output_metadata_dir(output_folder: Path | str) -> Path:
    """Return the protected experiment context folder for an output project."""
    return Path(output_folder).expanduser() / ACQUISITION_PROFILE_SNAPSHOT_DIRNAME


def legacy_output_metadata_dir(output_folder: Path | str) -> Path:
    return Path(output_folder).expanduser() / LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAME


def output_project_state_dir(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / PROJECT_STATE_DIRNAME


def output_profile_snapshot_dir(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / PROFILE_SNAPSHOT_DIRNAME


def output_shared_instructions_dir(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / SHARED_INSTRUCTIONS_DIRNAME


def output_prepared_blocks_dir(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / PREPARED_BLOCKS_DIRNAME


def output_runner_logs_dir(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / RUNNER_LOGS_DIRNAME


def output_verbose_events_dir(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / VERBOSE_EVENTS_DIRNAME


def output_validation_reports_dir(output_folder: Path | str) -> Path:
    return output_metadata_dir(output_folder) / VALIDATION_REPORTS_DIRNAME


def output_data_analytics_dir(output_folder: Path | str) -> Path:
    return Path(output_folder).expanduser() / DATA_ANALYTICS_DIRNAME


def output_data_min_dir(output_folder: Path | str) -> Path:
    return Path(output_folder).expanduser() / DATA_MIN_DIRNAME


def output_data_max_dir(output_folder: Path | str) -> Path:
    return Path(output_folder).expanduser() / DATA_MAX_DIRNAME


def output_data_min_master_csv(output_folder: Path | str) -> Path:
    return output_data_min_dir(output_folder) / DATA_MIN_MASTER_FILENAME


def safe_output_participant_id(value: str | None) -> str:
    text = str(value or "").strip()
    cleaned = []
    for char in text:
        if char.isalnum() or char in {"_", "-", "."}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    result = "".join(cleaned).strip("._-")
    return result or "participant"


def output_data_min_participant_csv(output_folder: Path | str, participant_id: str | None) -> Path:
    participant = safe_output_participant_id(participant_id)
    return output_data_min_dir(output_folder) / f"{participant}.csv"


def output_data_max_participant_dir(output_folder: Path | str, participant_id: str | None) -> Path:
    participant = safe_output_participant_id(participant_id)
    return output_data_max_dir(output_folder) / participant


def output_diary_path(output_folder: Path | str) -> Path:
    return output_project_state_dir(output_folder) / OUTPUT_DIARY_FILENAME


def bridge_manifest_path(output_folder: Path | str) -> Path:
    return output_project_state_dir(output_folder) / BRIDGE_MANIFEST_FILENAME


def _legacy_metadata_dirs(output_folder: Path | str) -> list[Path]:
    root = Path(output_folder).expanduser()
    return [root / name for name in LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAMES]


def metadata_file_candidates(
    output_folder: Path | str,
    filename: str,
    *,
    include_legacy: bool = True,
    include_root: bool = True,
) -> list[Path]:
    root = Path(output_folder).expanduser()
    candidates = [
        output_project_state_dir(root) / filename,
        output_metadata_dir(root) / filename,
    ]
    if include_legacy:
        for legacy_dir in _legacy_metadata_dirs(root):
            candidates.append(legacy_dir / filename)
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
        *LEGACY_ACQUISITION_PROFILE_SNAPSHOT_DIRNAMES,
    }


def output_root_for_metadata_path(path: Path | str) -> Path:
    target = Path(path).expanduser()
    parent = target.parent
    if parent.name in CONTEXT_CHILD_DIRNAMES and is_output_metadata_dir(parent.parent):
        return parent.parent.parent
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
