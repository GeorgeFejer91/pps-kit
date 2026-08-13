"""Shared stored-profile and acquisition-folder memory helpers."""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .output_layout import (
    ACQUISITION_PROFILE_SNAPSHOT_DIRNAME,
    BRIDGE_MANIFEST_FILENAME,
    OUTPUT_DIARY_FILENAME,
    bridge_manifest_path,
    find_existing_metadata_file,
    output_diary_path,
    output_metadata_dir,
    output_profile_snapshot_dir,
    output_runner_logs_dir,
)
from .preload_inventory import load_preload_inventory
from .runtime_paths import repo_root, writable_root


WRITABLE_ROOT = writable_root()
DEFAULT_PROJECT_REGISTRY_ROOT = WRITABLE_ROOT / "local_data" / "dashboard_projects" / "0_study_project_registry"
DEFAULT_DASHBOARD_STATE_ROOT = WRITABLE_ROOT / "local_data" / "dashboard_state"
DEFAULT_OUTPUT_FOLDER = WRITABLE_ROOT / "local_data" / "sessions"
FOCUS_RUNNER_SETTINGS_SCHEMA = "pps-focus-runner-settings.v1"
PROFILE_CATALOG_SCHEMA = "pps-shared-profile-catalog.v1"
DASHBOARD_RUNNER_BRIDGE_SCHEMA = "pps-dashboard-runner-bridge-manifest.v1"
OUTPUT_DIARY_EVENT_SCHEMA = "pps-output-diary-event.v1"
FOCUS_RUNNER_SETTINGS_FILENAME = "focus_runner_settings.v1.json"
RUN_SETUP_MANIFEST_SCHEMA = "pps-experiment-run-setup.v1"
PROJECT_MANIFEST_SCHEMA = "pps-dashboard-project.v1"
CUSTOM_PROJECT_ID_SLUG_MAX_LENGTH = 21
_REDACTED_KEYS = {"participant_name", "real_name", "given_name", "family_name", "full_name"}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def existing_output_diary_path(output_folder: Path | str) -> Path | None:
    return find_existing_metadata_file(output_folder, OUTPUT_DIARY_FILENAME)


def existing_bridge_manifest_path(output_folder: Path | str) -> Path | None:
    return find_existing_metadata_file(output_folder, BRIDGE_MANIFEST_FILENAME)


def generate_custom_profile_id(
    display_name: str,
    registry_root: Path = DEFAULT_PROJECT_REGISTRY_ROOT,
    *,
    created_at: datetime | None = None,
    max_slug_length: int = CUSTOM_PROJECT_ID_SLUG_MAX_LENGTH,
) -> str:
    """Return a collision-safe custom profile folder id."""
    created = created_at or datetime.now()
    timestamp = created.strftime("%Y%m%d_%H%M%S")
    slug = project_slug(display_name, "custom_project", max_length=max_slug_length)
    base = f"custom_{slug}_{timestamp}"
    root = Path(registry_root)
    candidate = base
    suffix = 2
    while (root / candidate).exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def project_slug(value: str, default: str = "project", *, max_length: int | None = None) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    text = text or default
    if max_length is not None and max_length > 0 and len(text) > max_length:
        digest = hashlib.sha1(str(value or text).encode("utf-8")).hexdigest()[:6]
        if max_length <= len(digest):
            return digest[:max_length]
        prefix = text[: max_length - len(digest) - 1].rstrip("_")
        text = f"{prefix}_{digest}" if prefix else digest[:max_length]
    return text


def runner_settings_path(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> Path:
    return Path(state_root) / FOCUS_RUNNER_SETTINGS_FILENAME


def load_runner_settings(
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    default_output_folder: Path = DEFAULT_OUTPUT_FOLDER,
) -> dict[str, Any]:
    path = runner_settings_path(state_root)
    data = _read_json(path)
    if data.get("schema") != FOCUS_RUNNER_SETTINGS_SCHEMA:
        data = _settings_from_legacy_pointer(state_root=state_root)
    output_folder = Path(
        str(
            data.get("active_output_folder")
            or data.get("current_output_project_root")
            or data.get("session_root")
            or default_output_folder
        )
    ).expanduser()
    output_diary = Path(str(data.get("output_diary_path") or output_diary_path(output_folder)))
    diary_path = Path(str(data.get("diary_path") or output_diary))
    bridge_path = Path(str(data.get("bridge_manifest_path") or bridge_manifest_path(output_folder)))
    normalized = dict(data)
    normalized.update(
        {
        "schema": FOCUS_RUNNER_SETTINGS_SCHEMA,
        "active_output_folder": str(output_folder),
        "current_output_project_root": str(data.get("current_output_project_root") or output_folder),
        "session_root": str(data.get("session_root") or output_folder),
        "diary_path": str(diary_path),
        "output_diary_path": str(output_diary),
        "bridge_manifest_path": str(bridge_path),
        "active_profile_id": str(data.get("active_profile_id") or data.get("template_id") or ""),
        "active_profile_kind": str(data.get("active_profile_kind") or ""),
        "dashboard_project_id": str(data.get("dashboard_project_id") or ""),
        "participant_id": str(data.get("participant_id") or ""),
        "capture_options": dict(data.get("capture_options") or {}) if isinstance(data.get("capture_options"), dict) else {},
        "updated_at": str(data.get("updated_at") or ""),
        "last_session_manifest_path": str(data.get("last_session_manifest_path") or data.get("session_manifest_path") or ""),
        "last_run_setup_manifest_path": str(data.get("last_run_setup_manifest_path") or data.get("run_setup_manifest_path") or ""),
        }
    )
    return normalized


def save_runner_settings(
    settings: dict[str, Any],
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
) -> Path:
    root = Path(state_root)
    root.mkdir(parents=True, exist_ok=True)
    data = load_runner_settings(state_root=state_root)
    data.update(_json_ready(settings))
    output_folder = Path(str(data.get("active_output_folder") or DEFAULT_OUTPUT_FOLDER)).expanduser()
    data["schema"] = FOCUS_RUNNER_SETTINGS_SCHEMA
    data["active_output_folder"] = str(output_folder)
    data["current_output_project_root"] = str(data.get("current_output_project_root") or output_folder)
    data["session_root"] = str(data.get("session_root") or output_folder)
    data["output_diary_path"] = str(data.get("output_diary_path") or output_diary_path(output_folder))
    data["diary_path"] = str(data.get("diary_path") or data["output_diary_path"])
    data["bridge_manifest_path"] = str(data.get("bridge_manifest_path") or bridge_manifest_path(output_folder))
    data["updated_at"] = now_iso()
    path = runner_settings_path(state_root)
    _write_json_file(path, data)
    return path


def update_runner_settings(
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    output_folder: Path | None = None,
    profile_id: str | None = None,
    profile_kind: str | None = None,
    dashboard_project_id: str | None = None,
    participant_id: str | None = None,
    capture_options: dict[str, Any] | None = None,
    run_setup_manifest_path: Path | str | None = None,
    session_manifest_path: Path | str | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    current = load_runner_settings(state_root=state_root)
    if output_folder is not None:
        output = Path(output_folder).expanduser()
        updates["active_output_folder"] = str(output)
        updates["current_output_project_root"] = str(output)
        updates["session_root"] = str(output)
        updates["output_diary_path"] = str(output_diary_path(output))
        current_diary_text = str(current.get("diary_path") or "").strip()
        current_diary = Path(current_diary_text).expanduser() if current_diary_text else None
        if current_diary is None or current_diary.name == OUTPUT_DIARY_FILENAME or current_diary.parent != output:
            updates["diary_path"] = str(_find_runner_log_diary(output) or output_diary_path(output))
        updates["bridge_manifest_path"] = str(bridge_manifest_path(output))
    if profile_id is not None:
        updates["active_profile_id"] = str(profile_id)
    if profile_kind is not None:
        updates["active_profile_kind"] = str(profile_kind)
    if dashboard_project_id is not None:
        updates["dashboard_project_id"] = str(dashboard_project_id)
    if participant_id is not None:
        updates["participant_id"] = str(participant_id)
    if capture_options is not None:
        updates["capture_options"] = dict(capture_options)
    if run_setup_manifest_path is not None:
        updates["last_run_setup_manifest_path"] = str(run_setup_manifest_path)
    if session_manifest_path is not None:
        updates["last_session_manifest_path"] = str(session_manifest_path)
    save_runner_settings(updates, state_root=state_root)
    return load_runner_settings(state_root=state_root)


def active_output_folder(
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    fallback: Path = DEFAULT_OUTPUT_FOLDER,
) -> Path:
    settings = load_runner_settings(state_root=state_root, default_output_folder=fallback)
    return Path(str(settings.get("active_output_folder") or fallback)).expanduser()


def append_output_diary_event(
    event_type: str,
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    output_folder: Path | None = None,
    **payload: Any,
) -> Path:
    settings = load_runner_settings(state_root=state_root)
    root = Path(output_folder or settings["active_output_folder"]).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    diary_path = Path(settings.get("output_diary_path") or output_diary_path(root))
    if output_folder is not None:
        diary_path = output_diary_path(root)
    os.makedirs(_filesystem_path(diary_path.parent), exist_ok=True)
    event = {
        "schema": OUTPUT_DIARY_EVENT_SCHEMA,
        "event_type": str(event_type or "activity"),
        "created_at": now_iso(),
        **_redact_participant_names(_json_ready(payload)),
    }
    with open(_filesystem_path(diary_path), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return diary_path


def build_profile_catalog(
    *,
    registry_root: Path = DEFAULT_PROJECT_REGISTRY_ROOT,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    session_root: Path | None = None,
    inventory: dict[str, Any] | None = None,
    include_unlaunchable_bundled: bool = True,
) -> dict[str, Any]:
    registry = Path(registry_root)
    output_root = Path(session_root or active_output_folder(state_root=state_root))
    inv = inventory if isinstance(inventory, dict) else load_preload_inventory(repo_root())
    entries: list[dict[str, Any]] = []
    entries.extend(
        _bundled_profile_entries(
            inv,
            registry_root=registry,
            session_root=output_root,
            state_root=state_root,
            include_unlaunchable=include_unlaunchable_bundled,
        )
    )
    entries.extend(_custom_profile_entries(registry, session_root=output_root, state_root=state_root))
    return {
        "schema": PROFILE_CATALOG_SCHEMA,
        "created_at": now_iso(),
        "registry_root": str(registry),
        "active_output_folder": str(output_root),
        "entries": entries,
    }


def resolve_profile_entry(
    profile_id: str,
    *,
    kind: str = "",
    registry_root: Path = DEFAULT_PROJECT_REGISTRY_ROOT,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    session_root: Path | None = None,
    inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target = str(profile_id or "").strip()
    target_kind = str(kind or "").strip().lower()
    if not target:
        raise ValueError("Choose a study/profile before continuing.")
    catalog = build_profile_catalog(
        registry_root=registry_root,
        state_root=state_root,
        session_root=session_root,
        inventory=inventory,
    )
    for entry in catalog["entries"]:
        if entry.get("profile_id") != target:
            continue
        if target_kind and entry.get("kind") != target_kind:
            continue
        return entry
    raise KeyError(target)


def profile_participant_ids_from_entry(entry: dict[str, Any]) -> list[str]:
    participants = [str(item or "").strip() for item in entry.get("participant_ids", []) if str(item or "").strip()]
    if participants:
        return participants
    count = max(1, int(entry.get("participant_count") or 1))
    return [f"P{index:03d}" for index in range(1, count + 1)]


def prepare_acquisition_folder(
    *,
    profile_entry: dict[str, Any],
    source_project_dir: Path,
    output_folder: Path,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    participant_id: str = "",
    capture_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = Path(output_folder).expanduser().resolve()
    os.makedirs(_filesystem_path(output), exist_ok=True)
    profile_id = str(profile_entry.get("profile_id") or "").strip()
    if not profile_id:
        raise ValueError("Profile id is required before preparing an acquisition folder.")
    source = Path(source_project_dir).resolve()
    if not os.path.isdir(_filesystem_path(source)):
        raise FileNotFoundError(f"Stored profile project folder is missing: {source}")
    snapshot_root = output_profile_snapshot_dir(output)
    snapshot_dir = (snapshot_root / profile_id).resolve()
    if output != snapshot_dir and output not in snapshot_dir.parents:
        raise ValueError("Acquisition profile snapshot path escapes the output folder.")
    if _path_exists(snapshot_dir):
        remove_project_tree(snapshot_dir)
    os.makedirs(_filesystem_path(snapshot_root), exist_ok=True)
    copy_project_tree(source, snapshot_dir)
    rebase_project_copy_paths(snapshot_dir, old_root=source, new_root=snapshot_dir)
    refresh_project_dependency_hashes(snapshot_dir)
    bridge = write_bridge_manifest(
        output_folder=output,
        profile_entry={**profile_entry, "acquisition_profile_snapshot_dir": str(snapshot_dir)},
        source_project_dir=snapshot_dir,
        state_root=state_root,
        participant_id=participant_id,
        capture_options=capture_options,
    )
    update_runner_settings(
        state_root=state_root,
        output_folder=output,
        profile_id=profile_id,
        profile_kind=str(profile_entry.get("kind") or ""),
        dashboard_project_id=str(profile_entry.get("dashboard_project_id") or ""),
        participant_id=participant_id or None,
        capture_options=capture_options,
        run_setup_manifest_path=bridge.get("run_setup_manifest_path") or None,
    )
    append_output_diary_event(
        "acquisition_folder_exported",
        state_root=state_root,
        output_folder=output,
        profile_id=profile_id,
        profile_kind=str(profile_entry.get("kind") or ""),
        dashboard_project_id=str(profile_entry.get("dashboard_project_id") or ""),
        participant_id=participant_id,
        bridge_manifest_path=bridge.get("bridge_manifest_path", ""),
        acquisition_profile_snapshot_dir=str(snapshot_dir),
    )
    return bridge


def copy_project_tree(
    source: Path,
    target: Path,
    *,
    ignore_patterns: Iterable[str] = (),
) -> None:
    """Copy a stored profile project tree without tripping Windows path limits."""
    source_root = Path(source).expanduser().resolve()
    target_root = Path(target).expanduser().resolve()
    if not os.path.isdir(_filesystem_path(source_root)):
        raise FileNotFoundError(f"Stored profile project folder is missing: {source_root}")
    if _path_exists(target_root):
        raise FileExistsError(f"Profile project folder already exists: {target_root}")

    patterns = tuple(str(pattern) for pattern in ignore_patterns if str(pattern))
    source_text = _filesystem_path(source_root)
    for root_text, dir_names, file_names in os.walk(source_text):
        dir_names[:] = [name for name in dir_names if not _matches_ignore(name, patterns)]
        rel_text = os.path.relpath(root_text, source_text)
        destination_dir = target_root if rel_text == "." else target_root / rel_text
        os.makedirs(_filesystem_path(destination_dir), exist_ok=True)
        for file_name in file_names:
            if _matches_ignore(file_name, patterns):
                continue
            source_file = os.path.join(root_text, file_name)
            target_file = destination_dir / file_name
            os.makedirs(_filesystem_path(target_file.parent), exist_ok=True)
            shutil.copy2(source_file, _filesystem_path(target_file))


def remove_project_tree(path: Path) -> None:
    target = Path(path).expanduser().resolve()
    if _path_exists(target):
        shutil.rmtree(_filesystem_path(target))


def refresh_project_dependency_hashes(project_dir: Path) -> None:
    """Refresh manifest-to-manifest hashes after copying and rebasing a profile."""
    root = Path(project_dir)
    segment0_manifest = root / "0_profile" / "project_manifest.json"
    segment1_manifest = root / "1_core_audio_ingredients" / "stimulus_ingredients_manifest.json"
    segment2_manifest = root / "2_trial_sequence_designs" / "trial_sequence_variants_manifest.json"
    segment3_manifest = root / "3_tactile_and_baseline_trials" / "baseline_tactile_trial_files_manifest.json"
    segment4_manifest = root / "4_trial_repetition_pool" / "trial_repetition_pool_manifest.json"
    segment5_manifest = root / "5_block_csv_preview" / "block_csv_preview_manifest.json"
    segment6_manifest = root / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    updates = (
        (segment1_manifest, "", segment0_manifest),
        (segment2_manifest, "", segment1_manifest),
        (segment3_manifest, "trial_sequence_manifest_sha256", segment2_manifest),
        (segment4_manifest, "source_segment3_manifest_sha256", segment3_manifest),
        (segment5_manifest, "source_segment4_manifest_sha256", segment4_manifest),
        (segment6_manifest, "source_segment5_manifest_sha256", segment5_manifest),
    )
    for manifest_path, field_name, source_path in updates:
        if not _path_exists(manifest_path) or not _path_exists(source_path):
            continue
        payload = _read_json(manifest_path)
        if not payload:
            continue
        digest = _sha256_file(source_path)
        if not digest:
            continue
        changed = False
        if field_name and payload.get(field_name) != digest:
            payload[field_name] = digest
            changed = True
        lineage = payload.get("segment_lineage")
        if isinstance(lineage, dict) and lineage.get("upstream_manifest_sha256") != digest:
            lineage["upstream_manifest_sha256"] = digest
            changed = True
        if changed:
            _write_json_file(manifest_path, payload)


def rebase_project_copy_paths(project_dir: Path, *, old_root: Path, new_root: Path) -> None:
    """Rewrite copied project manifests/CSVs from the source root to the copy root."""
    root = Path(project_dir)
    old_path = Path(old_root).resolve()
    new_path = Path(new_root).resolve()
    for json_path in _walk_project_files(root, ".json"):
        data = _read_json(json_path)
        if not data:
            continue
        _write_json_file(json_path, _replace_path_strings(data, old_path=old_path, new_path=new_path))
    replacements = _path_replacements(old_path, new_path)
    for csv_path in _walk_project_files(root, ".csv"):
        try:
            with open(_filesystem_path(csv_path), "r", encoding="utf-8") as handle:
                text = handle.read()
        except Exception:
            continue
        updated = text
        for old_text, new_text in replacements:
            updated = updated.replace(old_text, new_text)
        if updated != text:
            with open(_filesystem_path(csv_path), "w", encoding="utf-8") as handle:
                handle.write(updated)


def write_bridge_manifest(
    *,
    output_folder: Path,
    profile_entry: dict[str, Any],
    source_project_dir: Path,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    participant_id: str = "",
    capture_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output = Path(output_folder).expanduser().resolve()
    os.makedirs(_filesystem_path(output), exist_ok=True)
    project_dir = Path(source_project_dir).resolve()
    segment_manifests = _segment_manifest_paths(project_dir)
    run_setup_text = str(segment_manifests.get("6_experiment_run_setup") or "")
    run_setup_path = Path(run_setup_text) if run_setup_text else None
    run_setup = _read_json(run_setup_path) if run_setup_path is not None else {}
    participants = _participants_from_run_setup(run_setup_path) if run_setup_path is not None and _path_exists(run_setup_path) else []
    manifest = {
        "schema": DASHBOARD_RUNNER_BRIDGE_SCHEMA,
        "created_at": now_iso(),
        "local_only": True,
        "active_output_folder": str(output),
        "environment_metadata_dir": str(output_metadata_dir(output)),
        "project_state_dir": str(output_diary_path(output).parent),
        "profile_snapshot_dir": str(output_profile_snapshot_dir(output)),
        "runner_logs_dir": str(output_runner_logs_dir(output)),
        "output_diary_path": str(output_diary_path(output)),
        "profile_id": str(profile_entry.get("profile_id") or ""),
        "display_name": str(profile_entry.get("display_name") or ""),
        "kind": str(profile_entry.get("kind") or ""),
        "dashboard_project_id": str(profile_entry.get("dashboard_project_id") or ""),
        "source_template_id": str(profile_entry.get("source_template_id") or ""),
        "source_profile_id": str(profile_entry.get("source_profile_id") or ""),
        "participant_id": str(participant_id or ""),
        "participant_ids": participants,
        "participant_count": len(participants) or int(profile_entry.get("participant_count") or 0),
        "segment_6_ready": bool(run_setup.get("prepared")) and bool(run_setup_path is not None and _path_exists(run_setup_path)),
        "asset_roots": list(profile_entry.get("asset_roots") or []),
        "stored_project_dir": str(profile_entry.get("project_dir") or ""),
        "acquisition_profile_snapshot_dir": str(project_dir),
        "segment_manifests": {
            segment: {
                "path": str(path),
                "sha256": _sha256_file(Path(path)) if path else "",
                "exists": bool(path and _path_exists(Path(path))),
            }
            for segment, path in segment_manifests.items()
        },
        "run_setup_manifest_path": str(run_setup_path) if run_setup_path is not None else "",
        "run_setup_manifest_sha256": _sha256_file(run_setup_path) if run_setup_path is not None and _path_exists(run_setup_path) else "",
        "capture_options": dict(capture_options or {}),
        "runner_settings_path": str(runner_settings_path(state_root)),
    }
    bridge_path = bridge_manifest_path(output)
    os.makedirs(_filesystem_path(bridge_path.parent), exist_ok=True)
    with open(_filesystem_path(bridge_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(manifest), indent=2, sort_keys=True) + "\n")
    manifest["bridge_manifest_path"] = str(bridge_path)
    return manifest


def _settings_from_legacy_pointer(*, state_root: Path) -> dict[str, Any]:
    pointer = _read_json(Path(state_root) / "last_experiment.v1.json")
    if not pointer:
        return {}
    return {
        "active_profile_id": str(pointer.get("template_id") or ""),
        "participant_id": str(pointer.get("participant_id") or ""),
        "last_session_manifest_path": str(pointer.get("session_manifest_path") or ""),
        "last_run_setup_manifest_path": str(pointer.get("run_setup_manifest_path") or ""),
    }


def _bundled_profile_entries(
    inventory: dict[str, Any],
    *,
    registry_root: Path,
    session_root: Path,
    state_root: Path,
    include_unlaunchable: bool,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for profile in inventory.get("profiles", []):
        profile_id = str(profile.get("template_id") or "").strip()
        if not profile_id:
            continue
        finished = bool(profile.get("finished_profile")) or (
            str(profile.get("runner_readiness") or "") == "ready"
            and bool(profile.get("profile_checks_passed"))
            and bool(profile.get("segment_0_to_4_profile_checks_passed"))
        )
        launchable = bool(profile.get("segment_6_launchable")) or finished
        if not include_unlaunchable and not (finished and launchable):
            continue
        project_dir = registry_root / f"profile_{project_slug(profile_id, 'profile')}"
        run_setup_path = project_dir / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
        participant_ids = _participants_from_run_setup(run_setup_path) if _path_exists(run_setup_path) else _participants_from_preload_defaults(profile_id)
        statuses = _participant_statuses(run_setup_path, participant_ids, session_root=session_root, state_root=state_root)
        asset_roots = [str(repo_root() / "assets" / "preloads" / profile_id)]
        if project_dir.exists():
            asset_roots.append(str(project_dir))
        missing_reasons = []
        if not launchable:
            missing_reasons.append(str(profile.get("profile_completion_status") or profile.get("runner_readiness") or "unfinished_preload"))
        if _path_exists(run_setup_path) and not _run_setup_ready(run_setup_path):
            missing_reasons.append("Segment 6 run setup manifest is missing, stale, or incomplete.")
        entries.append(
            {
                "profile_id": profile_id,
                "display_name": str(profile.get("variant_display") or profile.get("visible_variant_label") or profile_id),
                "kind": "bundled",
                "dashboard_project_id": f"profile_{project_slug(profile_id, 'profile')}",
                "project_dir": str(project_dir) if project_dir.exists() else "",
                "asset_roots": asset_roots,
                "segment_manifests": _segment_manifest_paths(project_dir),
                "run_setup_manifest_path": str(run_setup_path) if _path_exists(run_setup_path) else "",
                "segment_6_ready": bool(launchable and (not _path_exists(run_setup_path) or _run_setup_ready(run_setup_path))),
                "participant_count": len(participant_ids),
                "participant_ids": participant_ids,
                "participants": [_participant_entry(participant, statuses.get(participant, {})) for participant in participant_ids],
                "source_template_id": profile_id,
                "source_profile_id": "",
                "created_at": "",
                "missing_or_stale_asset_reasons": [reason for reason in missing_reasons if reason],
            }
        )
    entries.sort(key=lambda item: (0 if item["profile_id"] == "study5_box_breathing_pps" else 1, item["display_name"].lower()))
    return entries


def _custom_profile_entries(registry_root: Path, *, session_root: Path, state_root: Path) -> list[dict[str, Any]]:
    root = Path(registry_root)
    if not root.exists():
        return []
    entries: list[dict[str, Any]] = []
    for child in root.iterdir():
        if not child.is_dir() or not child.name.startswith("custom_"):
            continue
        active_design_path = child / "0_profile" / "active_design.json"
        if not _path_exists(active_design_path):
            continue
        design = _read_json(active_design_path)
        reference = design.get("study_profile_reference_parameters")
        reference = reference if isinstance(reference, dict) else {}
        project_metadata = reference.get("dashboard_project")
        project_metadata = project_metadata if isinstance(project_metadata, dict) else {}
        if str(reference.get("dashboard_mode") or "").strip().lower() != "custom":
            continue
        if str(reference.get("profile_status") or "legacy").strip().lower() == "draft":
            continue
        project_manifest = _read_json(child / "0_profile" / "project_manifest.json")
        display_name = str(
            project_manifest.get("project_label")
            or project_metadata.get("project_label")
            or design.get("name")
            or child.name
        )
        run_setup_path = child / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
        participant_ids = _participants_from_run_setup(run_setup_path) if _path_exists(run_setup_path) else []
        if not participant_ids:
            protocol = design.get("protocol") if isinstance(design.get("protocol"), dict) else {}
            preview_count = max(1, min(100, int(protocol.get("participants") or 1)))
            participant_ids = [f"P{index:03d}" for index in range(1, preview_count + 1)]
        statuses = _participant_statuses(run_setup_path, participant_ids, session_root=session_root, state_root=state_root)
        legacy_run_ready = _run_setup_ready(run_setup_path)
        segment_paths = _segment_manifest_paths(child)
        profile_ready = all(segment in segment_paths for segment in (
            "0_profile", "1_core_audio_ingredients", "2_trial_sequence_designs",
            "3_tactile_and_baseline_trials", "4_trial_repetition_pool", "5_block_csv_preview",
        ))
        missing = []
        if not profile_ready:
            missing.append("The saved profile is missing one or more accepted Segment 0-5 artifacts.")
        entries.append(
            {
                "profile_id": child.name,
                "display_name": display_name,
                "kind": "custom",
                "dashboard_project_id": child.name,
                "project_dir": str(child),
                "asset_roots": [str(child)],
                "segment_manifests": segment_paths,
                "run_setup_manifest_path": str(run_setup_path) if _path_exists(run_setup_path) else "",
                "profile_ready": profile_ready,
                "segment_6_ready": profile_ready or legacy_run_ready,
                "runner_materialization_required": profile_ready and not legacy_run_ready,
                "participant_count": len(participant_ids),
                "participant_ids": participant_ids,
                "participants": [_participant_entry(participant, statuses.get(participant, {})) for participant in participant_ids],
                "source_template_id": str(project_manifest.get("source_template_id") or project_metadata.get("source_template_id") or ""),
                "source_profile_id": str(project_manifest.get("source_profile_id") or project_metadata.get("source_profile_id") or ""),
                "created_at": str(project_manifest.get("created_at") or project_metadata.get("created_at") or ""),
                "missing_or_stale_asset_reasons": missing,
            }
        )
    return sorted(entries, key=lambda item: (item.get("created_at", ""), item.get("profile_id", "")), reverse=True)


def _participant_statuses(
    run_setup_path: Path,
    participant_ids: Iterable[str],
    *,
    session_root: Path,
    state_root: Path,
) -> dict[str, dict[str, Any]]:
    participants = [str(participant or "").strip() for participant in participant_ids if str(participant or "").strip()]
    if not participants or not _path_exists(run_setup_path):
        return {}
    try:
        from .session_runner import prepared_session_asset_statuses

        return prepared_session_asset_statuses(
            Path(run_setup_path),
            participants,
            state_root=state_root,
            session_root=session_root,
        )
    except Exception:
        return {}


def _participant_entry(participant_id: str, status: dict[str, Any]) -> dict[str, Any]:
    return {
        "participant_id": participant_id,
        "generated": bool(status.get("generated")),
        "status": str(status.get("status") or "not_generated"),
        "session_manifest_path": str(status.get("session_manifest_path") or ""),
        "data_collected": bool(status.get("data_collected")),
        "data_collection_status": str(status.get("data_collection_status") or "not_collected"),
        "data_session_manifest_path": str(status.get("data_session_manifest_path") or ""),
        "data_session_dir": str(status.get("data_session_dir") or ""),
        "data_collection_message": str(status.get("data_collection_message") or "No completed participant data found."),
    }


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).expanduser().resolve()
    text = str(resolved)
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _path_exists(path: str | Path) -> bool:
    try:
        return os.path.exists(_filesystem_path(path))
    except OSError:
        return False


def _matches_ignore(name: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(name, pattern) for pattern in patterns)


def _walk_project_files(root: Path, suffix: str) -> Iterable[Path]:
    root_text = _filesystem_path(root)
    target_suffix = str(suffix or "").lower()
    for current_root, _dir_names, file_names in os.walk(root_text):
        for file_name in file_names:
            if target_suffix and not file_name.lower().endswith(target_suffix):
                continue
            yield Path(os.path.join(current_root, file_name))


def _find_runner_log_diary(folder: Path) -> Path | None:
    root = Path(folder)
    try:
        matches = [
            path
            for path in _walk_project_files(root, "LOG-DIARY_DO_NOT_DELETE.txt")
            if os.path.isfile(_filesystem_path(path))
        ]
    except Exception:
        return None
    if not matches:
        return None
    return max(matches, key=lambda path: os.path.getmtime(_filesystem_path(path)))


def _replace_path_strings(value: Any, *, old_path: Path, new_path: Path) -> Any:
    if isinstance(value, dict):
        return {str(key): _replace_path_strings(item, old_path=old_path, new_path=new_path) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_path_strings(item, old_path=old_path, new_path=new_path) for item in value]
    if isinstance(value, str):
        updated = value
        for old_text, new_text in _path_replacements(old_path, new_path):
            updated = updated.replace(old_text, new_text)
        return updated
    return value


def _path_replacements(old_path: Path, new_path: Path) -> list[tuple[str, str]]:
    old_raw = str(old_path)
    new_raw = str(new_path)
    pairs = [
        (old_raw, new_raw),
        (old_path.as_posix(), new_path.as_posix()),
        (old_raw.replace("\\", "\\\\"), new_raw.replace("\\", "\\\\")),
    ]
    unique: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for pair in pairs:
        if pair[0] and pair not in seen:
            unique.append(pair)
            seen.add(pair)
    return unique


def _segment_manifest_paths(project_dir: Path) -> dict[str, str]:
    root = Path(project_dir)
    paths = {
        "0_profile": root / "0_profile" / "project_manifest.json",
        "1_core_audio_ingredients": root / "1_core_audio_ingredients" / "stimulus_ingredients_manifest.json",
        "2_trial_sequence_designs": root / "2_trial_sequence_designs" / "trial_sequence_variants_manifest.json",
        "3_tactile_and_baseline_trials": root / "3_tactile_and_baseline_trials" / "baseline_tactile_trial_files_manifest.json",
        "4_trial_repetition_pool": root / "4_trial_repetition_pool" / "trial_repetition_pool_manifest.json",
        "5_block_csv_preview": root / "5_block_csv_preview" / "block_csv_preview_manifest.json",
        "6_experiment_run_setup": root / "6_experiment_run_setup" / "experiment_run_setup_manifest.json",
    }
    return {segment: str(path) for segment, path in paths.items() if _path_exists(path)}


def _run_setup_ready(run_setup_path: Path) -> bool:
    path = Path(run_setup_path)
    manifest = _read_json(path)
    if manifest.get("schema") != RUN_SETUP_MANIFEST_SCHEMA or not bool(manifest.get("prepared")):
        return False
    csv_path = _resolve_manifest_path(manifest.get("csv_path", ""), path.parent)
    return bool(csv_path and _path_exists(csv_path))


def _participants_from_run_setup(run_setup_path: Path) -> list[str]:
    path = Path(run_setup_path)
    manifest = _read_json(path)
    csv_path = _resolve_manifest_path(manifest.get("csv_path", ""), path.parent)
    participants: set[str] = set()
    if csv_path and _path_exists(csv_path):
        try:
            with open(_filesystem_path(csv_path), newline="", encoding="utf-8-sig") as handle:
                for row in csv.DictReader(handle):
                    participant = str(row.get("participant_id") or "").strip()
                    if participant:
                        participants.add(participant)
        except Exception:
            pass
    if participants:
        return sorted(participants, key=_participant_sort_key)
    count = int(manifest.get("participant_count") or 0)
    return [f"P{index:03d}" for index in range(1, count + 1)] if count > 0 else []


def _participants_from_preload_defaults(profile_id: str) -> list[str]:
    defaults = repo_root() / "assets" / "preloads" / profile_id / "05_run_setup" / "run_defaults.json"
    count = 1
    try:
        data = json.loads(defaults.read_text(encoding="utf-8"))
        count = max(1, int(data.get("participants") or data.get("participant_count") or 1))
    except Exception:
        count = 1
    return [f"P{index:03d}" for index in range(1, count + 1)]


def _participant_sort_key(value: str) -> tuple[int, str]:
    text = str(value or "").strip()
    match = re.fullmatch(r"P?(\d+)", text, flags=re.IGNORECASE)
    if match:
        return (int(match.group(1)), text)
    return (10**9, text)


def _resolve_manifest_path(value: Any, base_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_absolute() else Path(base_dir) / path


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return {}


def _write_json_file(path: Path, payload: dict[str, Any]) -> None:
    target = Path(path)
    os.makedirs(_filesystem_path(target.parent), exist_ok=True)
    with open(_filesystem_path(target), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n")


def _sha256_file(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with open(_filesystem_path(path), "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except Exception:
        return ""


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _redact_participant_names(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in _REDACTED_KEYS:
                continue
            redacted[str(key)] = _redact_participant_names(item)
        return redacted
    if isinstance(value, list):
        return [_redact_participant_names(item) for item in value]
    return value
