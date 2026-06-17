"""Append-only runner output project diary helpers."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


RUNNER_DIARY_SCHEMA = "pps-runner-output-diary.v1"
RUNNER_SETTINGS_SCHEMA = "pps-focus-runner-settings.v1"
DIARY_FILENAME_MARKER = "LOG-DIARY_DO_NOT_DELETE"
DIARY_SUFFIX = f"_{DIARY_FILENAME_MARKER}.txt"
RUNNER_SETTINGS_FILENAME = "focus_runner_settings.v1.json"


@dataclass(frozen=True)
class OutputProjectResolution:
    root: Path
    diary_path: Path
    created: bool
    reused_existing_diary: bool


def slugify_identifier(value: str | None, *, fallback: str = "pps_experiment", max_length: int = 72) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    if not text:
        text = fallback
    return text[:max_length].strip("_") or fallback


def diary_filename(identifier: str | None) -> str:
    return f"{slugify_identifier(identifier)}{DIARY_SUFFIX}"


def is_diary_file(path: Path) -> bool:
    path = Path(path)
    return path.is_file() and path.name.endswith(DIARY_SUFFIX)


def find_output_diary(folder: Path) -> Path | None:
    root = Path(folder).expanduser()
    if not root.is_dir():
        return None
    candidates = [path for path in root.glob(f"*{DIARY_SUFFIX}") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def ensure_output_diary(project_root: Path, experiment_identifier: str | None = None) -> Path:
    root = Path(project_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    existing = find_output_diary(root)
    if existing is not None:
        return existing
    diary_path = root / diary_filename(experiment_identifier)
    append_diary_entry(
        diary_path,
        "diary_created",
        experiment_name=str(experiment_identifier or ""),
        payload={"project_root": str(root)},
    )
    return diary_path


def resolve_or_create_output_project(
    selected_folder: Path,
    *,
    experiment_identifier: str | None = None,
    timestamp: str | None = None,
) -> OutputProjectResolution:
    selected = Path(selected_folder).expanduser().resolve()
    selected.mkdir(parents=True, exist_ok=True)
    existing = find_output_diary(selected)
    if existing is not None:
        append_diary_entry(
            existing,
            "output_project_reused",
            experiment_name=str(experiment_identifier or ""),
            payload={"selected_folder": str(selected)},
        )
        return OutputProjectResolution(root=selected, diary_path=existing, created=False, reused_existing_diary=True)

    stamp = str(timestamp or time.strftime("%Y%m%d_%H%M%S"))
    slug = slugify_identifier(experiment_identifier)
    project_root = selected / f"{slug}_{stamp}"
    suffix = 2
    while project_root.exists():
        project_root = selected / f"{slug}_{stamp}_{suffix}"
        suffix += 1
    project_root.mkdir(parents=True, exist_ok=True)
    diary_path = project_root / diary_filename(slug)
    append_diary_entry(
        diary_path,
        "output_project_created",
        experiment_name=str(experiment_identifier or slug),
        payload={"selected_folder": str(selected), "project_root": str(project_root)},
    )
    return OutputProjectResolution(root=project_root, diary_path=diary_path, created=True, reused_existing_diary=False)


def append_diary_entry(
    diary_path: Path,
    event_type: str,
    *,
    session_id: str = "",
    participant_id: str = "",
    experiment_name: str = "",
    profile_id: str = "",
    run_setup_manifest_path: str | Path = "",
    session_manifest_path: str | Path = "",
    capture_options: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Path:
    path = Path(diary_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    entry = {
        "schema": RUNNER_DIARY_SCHEMA,
        "event_type": str(event_type or "activity"),
        "created_at": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "unix_time": now,
        "session_id": str(session_id or ""),
        "participant_id": str(participant_id or ""),
        "experiment_name": str(experiment_name or ""),
        "profile_id": str(profile_id or ""),
        "run_setup_manifest_path": "" if not run_setup_manifest_path else str(run_setup_manifest_path),
        "session_manifest_path": "" if not session_manifest_path else str(session_manifest_path),
        "capture_options": _json_ready(capture_options or {}),
        "payload": _json_ready(payload or {}),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def read_diary_entries(diary_path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    path = Path(diary_path)
    if not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    try:
        lines: Iterable[str] = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict) and item.get("schema") == RUNNER_DIARY_SCHEMA:
            entries.append(item)
    if limit is not None and limit >= 0:
        return entries[-limit:]
    return entries


def latest_diary_context(diary_path: Path) -> dict[str, Any]:
    entries = read_diary_entries(diary_path)
    context: dict[str, Any] = {}
    for entry in entries:
        for key in (
            "session_id",
            "participant_id",
            "experiment_name",
            "profile_id",
            "run_setup_manifest_path",
            "session_manifest_path",
            "capture_options",
        ):
            value = entry.get(key)
            if value not in (None, "", {}):
                context[key] = value
    return context


def runner_settings_path(state_root: Path) -> Path:
    return Path(state_root).expanduser() / RUNNER_SETTINGS_FILENAME


def load_runner_settings(state_root: Path) -> dict[str, Any]:
    path = runner_settings_path(state_root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": RUNNER_SETTINGS_SCHEMA}
    if not isinstance(data, dict) or data.get("schema") != RUNNER_SETTINGS_SCHEMA:
        return {"schema": RUNNER_SETTINGS_SCHEMA}
    return data


def update_runner_settings(state_root: Path, **updates: Any) -> dict[str, Any]:
    data = load_runner_settings(state_root)
    data.update({key: _json_ready(value) for key, value in updates.items() if value is not None})
    data["schema"] = RUNNER_SETTINGS_SCHEMA
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path = runner_settings_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return data


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
