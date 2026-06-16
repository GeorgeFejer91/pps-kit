"""Qt-facing session package and runner controller.

This module is intentionally independent from Qt.  The desktop designer uses it
to prepare one reproducible run folder and to drive the same event/audio
primitives used by the legacy runner.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .design import StimulusDesign, experiment_schedule_rows, export_protocol_csv, save_design, validate_design
from .session_analysis import analyze_session_events, format_analysis_summary, write_analysis_csvs
from .session_events import SessionEventLogger
from .timing_events import TimingEventHub, TriggerDictionary
from .timing_schedule import BlockEventSchedule
from .topup import TopUpLedger, write_topup_draft_manifest
from .runtime_paths import repo_root, writable_root


REPO_ROOT = repo_root()
WRITABLE_ROOT = writable_root()
DEFAULT_RENDER_DIR = WRITABLE_ROOT / "artifacts" / "qt_runner_render"
DEFAULT_SESSION_ROOT = WRITABLE_ROOT / "local_data" / "sessions"
DEFAULT_PROJECT_REGISTRY_ROOT = WRITABLE_ROOT / "local_data" / "dashboard_projects" / "0_study_project_registry"
DEFAULT_DASHBOARD_STATE_ROOT = WRITABLE_ROOT / "local_data" / "dashboard_state"
DEFAULT_SESSION_BLOCK_CACHE_ROOT = WRITABLE_ROOT / "local_data" / "session_block_cache"
TRIAL_SEQUENCE_VARIANT_DIR = "2_trial_sequence_designs"
LEGACY_TRIAL_SEQUENCE_VARIANT_DIR = "3_trial_sequence__variant_bakes"
TRIAL_SEQUENCE_VARIANT_MANIFEST = "trial_sequence_variants_manifest.json"
BASELINE_TACTILE_TRIAL_DIR = "3_tactile_and_baseline_trials"
LEGACY_BASELINE_TACTILE_TRIAL_DIR = "4_baseline_tactile_trial_design__trial_bakes"
BASELINE_TACTILE_TRIAL_MANIFEST = "baseline_tactile_trial_files_manifest.json"
PREFERRED_AUDIO_ROUTE = "Komplete Audio ASIO Driver"
REQUESTED_LATENCY_S = 0.010
REQUESTED_BLOCKSIZE = 256
SESSION_METADATA_SCHEMA = "pps-runner-session-metadata.v1"
RUN_PACKAGE_SCHEMA = "pps-run-session.v1"
SEGMENT_RUN_SETUP_SCHEMA = "pps-experiment-run-setup.v1"
SEGMENT_BLOCK_PREVIEW_SCHEMA = "pps-block-csv-preview.v1"
LAST_EXPERIMENT_SCHEMA = "pps-last-experiment.v1"
PREPARED_SESSION_QUEUE_SCHEMA = "pps-prepared-session-queue.v1"
BLOCK_WAV_CACHE_SCHEMA = "pps-session-block-cache.v1"
BLOCK_WAV_CACHE_VERSION = "2026-06-14.v1"
RESPONSE_MARKER_GAIN = 0.05
LAUNCHABLE_ACTIVITY_EVENTS = {"run_setup_prepared", "session_prepared", "runner_launched"}


@dataclass(frozen=True)
class RenderedWav:
    path: Path
    label: str
    duration_s: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    sha256: str = ""


@dataclass(frozen=True)
class RunBlock:
    index: int
    label: str
    manifest_path: Path
    wav_path: Path
    trial_count: int
    duration_s: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunPackage:
    participant_id: str
    session_id: str
    created_at: str
    session_dir: Path
    design_path: Path
    protocol_path: Path
    manifest_path: Path
    render_manifest_path: Path | None
    blocks: list[RunBlock] = field(default_factory=list)
    execution_mode: str = "design_schedule_blocks"
    source_run_setup_manifest_path: Path | None = None
    instruction_profile: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunPreflight:
    participant_id: str
    valid_design: bool
    participant_ready: bool
    render_ready: bool
    schedule_ready: bool
    audio_route: str
    audio_ready: bool
    render_dir: Path
    rendered_wavs: list[RenderedWav] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.valid_design and self.participant_ready and self.render_ready and self.schedule_ready and self.audio_ready


@dataclass(frozen=True)
class SessionRunResult:
    completed: bool
    interrupted: bool
    session_dir: Path
    events_csv: Path
    events_xdf: Path
    analysis_outputs: dict[str, Path]
    summary_text: str
    warnings: list[str] = field(default_factory=list)
    lsl_status: dict[str, Any] = field(default_factory=dict)
    recording_paths: list[Path] = field(default_factory=list)
    lsl_markers_csv: Path | None = None
    lsl_markers_xdf: Path | None = None
    trigger_dictionary_path: Path | None = None
    session_metadata_path: Path | None = None
    capture_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SessionCaptureOptions:
    """Output choices for a runner session.

    The in-memory event stream always exists while a session is active. These
    flags control which durable copies are written and whether LSL outlets are
    created.
    """

    enable_lsl: bool = True
    write_events_csv: bool = True
    write_internal_xdf: bool = True
    write_analysis_csvs: bool = True
    write_lsl_marker_mirror: bool = True
    write_trigger_dictionary: bool = True
    start_backup_recording: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "enable_lsl": bool(self.enable_lsl),
            "write_events_csv": bool(self.write_events_csv),
            "write_internal_xdf": bool(self.write_internal_xdf),
            "write_analysis_csvs": bool(self.write_analysis_csvs),
            "write_lsl_marker_mirror": bool(self.write_lsl_marker_mirror),
            "write_trigger_dictionary": bool(self.write_trigger_dictionary),
            "start_backup_recording": bool(self.start_backup_recording),
        }


ProgressCallback = Callable[[dict[str, Any]], None]
EventCallback = Callable[[str], None]


def sanitize_participant_id(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", text).strip("_")
    return safe[:64]


def render_manifest_path(render_dir: Path = DEFAULT_RENDER_DIR) -> Path:
    return Path(render_dir) / "render_manifest.json"


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _path_exists(path: str | Path) -> bool:
    try:
        return os.path.exists(_filesystem_path(path))
    except OSError:
        return False


def _read_text_file(path: str | Path, *, encoding: str = "utf-8") -> str:
    with open(_filesystem_path(path), "r", encoding=encoding) as handle:
        return handle.read()


def _soundfile_path(path: str | Path) -> str:
    return _filesystem_path(path)


def rendered_wavs(render_dir: Path = DEFAULT_RENDER_DIR) -> list[RenderedWav]:
    render_dir = Path(render_dir)
    manifest = _load_json(render_manifest_path(render_dir))
    outputs = manifest.get("wav_outputs", []) if isinstance(manifest, dict) else []
    wavs: list[RenderedWav] = []
    seen_paths: set[Path] = set()
    for item in outputs:
        path = Path(str(item.get("path", "")))
        if not path.is_absolute():
            path = render_dir / path
        if _path_exists(path) and path not in seen_paths:
            wavs.append(_wav_info(path, sha256=str(item.get("sha256", ""))))
            seen_paths.add(path)
    for path in render_dir.glob("*.wav"):
        if path not in seen_paths:
            wavs.append(_wav_info(path))
            seen_paths.add(path)
    if wavs:
        return sorted(wavs, key=lambda item: item.label)
    return sorted((_wav_info(path) for path in render_dir.glob("*.wav")), key=lambda item: item.label)


def available_stimulus_wavs(design: StimulusDesign, render_dir: Path = DEFAULT_RENDER_DIR) -> list[RenderedWav]:
    wavs: list[RenderedWav] = []
    seen_paths: set[Path] = set()
    for noise in design.noises:
        path_text = getattr(noise, "prebaked_path", "")
        if not path_text:
            continue
        path = _resolve_asset_path(path_text)
        if not _path_exists(path):
            continue
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        wavs.append(_wav_info(path, label=noise.label))
        seen_paths.add(resolved)
    for asset in design.custom_looming_files:
        path = _resolve_asset_path(asset.path)
        if not _path_exists(path):
            continue
        resolved = path.resolve()
        if resolved in seen_paths:
            continue
        wavs.append(_wav_info(path, label=asset.label))
        seen_paths.add(resolved)
    for wav in rendered_wavs(render_dir):
        resolved = wav.path.resolve()
        if resolved in seen_paths:
            continue
        wavs.append(wav)
        seen_paths.add(resolved)
    return sorted(wavs, key=lambda item: item.label)


def preflight_run_package(
    design: StimulusDesign,
    participant_id: str,
    *,
    render_dir: Path = DEFAULT_RENDER_DIR,
    require_audio: bool = False,
) -> RunPreflight:
    messages: list[str] = []
    clean_participant = sanitize_participant_id(participant_id)
    design_warnings = validate_design(design)
    if design_warnings:
        messages.extend(f"Design: {warning}" for warning in design_warnings[:4])
    participant_ready = bool(clean_participant)
    if not participant_ready:
        messages.append("Participant ID is required.")

    wavs = available_stimulus_wavs(design, render_dir)
    render_ready = bool(wavs)
    if not render_ready:
        messages.append("Rendered looming WAVs are missing.")

    schedule_rows = experiment_schedule_rows(design)
    schedule_ready = bool(schedule_rows)
    if not schedule_ready:
        messages.append("No trial schedule rows are available.")

    audio_ready = True
    if require_audio:
        audio_ready = _preferred_audio_route_available()
        if not audio_ready:
            messages.append(f"Preferred audio route not detected: {PREFERRED_AUDIO_ROUTE}.")

    return RunPreflight(
        participant_id=clean_participant,
        valid_design=not design_warnings,
        participant_ready=participant_ready,
        render_ready=render_ready,
        schedule_ready=schedule_ready,
        audio_route=f"{PREFERRED_AUDIO_ROUTE}, 3 channels, latency {REQUESTED_LATENCY_S:.3f}, blocksize {REQUESTED_BLOCKSIZE}",
        audio_ready=audio_ready,
        render_dir=Path(render_dir),
        rendered_wavs=wavs,
        messages=messages,
    )


def prepare_run_package(
    design: StimulusDesign,
    participant_id: str,
    *,
    render_dir: Path = DEFAULT_RENDER_DIR,
    session_root: Path = DEFAULT_SESSION_ROOT,
    created_at: datetime | None = None,
) -> RunPackage:
    clean_participant = sanitize_participant_id(participant_id)
    if not clean_participant:
        raise ValueError("Participant ID is required.")
    wavs = available_stimulus_wavs(design, render_dir)
    if not wavs:
        raise FileNotFoundError(f"No rendered WAV files found in {render_dir}.")

    created_at = created_at or datetime.now()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    session_id = f"{clean_participant}_{timestamp}"
    session_dir = Path(session_root) / session_id
    block_dir = session_dir / "blocks"
    analysis_dir = session_dir / "analysis"
    block_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)

    design_path = session_dir / "design.json"
    protocol_path = session_dir / "protocol_schedule.csv"
    rows = _participant_rows(design, clean_participant)
    variant_lookup = _trial_sequence_variant_lookup(render_dir)
    _attach_sequence_variant_paths(rows, variant_lookup)
    trial_file_lookup = _trial_file_lookup(render_dir)
    _attach_trial_file_paths(rows, trial_file_lookup)
    if not rows:
        raise ValueError("The current design produced no participant schedule rows.")

    save_design(design, design_path)
    export_protocol_csv(design, protocol_path)

    wav_by_label = _wav_lookup(wavs)
    blocks: list[RunBlock] = []
    for block_index, (block_label, block_rows) in enumerate(_group_rows_by_block(rows), start=1):
        manifest_path = block_dir / f"Block_{block_index:02d}_{_slug(block_label)}.csv"
        wav_path = block_dir / f"Block_{block_index:02d}_{_slug(block_label)}_concatenated.wav"
        _write_block_manifest(manifest_path, block_rows, clean_participant)
        duration_s = _materialize_block_wav(wav_path, block_rows, wav_by_label)
        if duration_s <= 0:
            duration_s = wav_by_label["__default__"].duration_s
        blocks.append(
            RunBlock(
                index=block_index,
                label=block_label,
                manifest_path=manifest_path,
                wav_path=wav_path,
                trial_count=len(block_rows),
                duration_s=float(duration_s),
            )
        )

    manifest_path = session_dir / "session_manifest.json"
    render_manifest = render_manifest_path(render_dir)
    package = RunPackage(
        participant_id=clean_participant,
        session_id=session_id,
        created_at=created_at.isoformat(timespec="seconds"),
        session_dir=session_dir,
        design_path=design_path,
        protocol_path=protocol_path,
        manifest_path=manifest_path,
        render_manifest_path=render_manifest if _path_exists(render_manifest) else None,
        blocks=blocks,
        execution_mode="design_schedule_blocks",
        instruction_profile=_materialize_session_instruction_profile(
            design.study_profile_reference_parameters.get("dashboard_run_setup", {}).get("instruction_profile", {})
            if isinstance(design.study_profile_reference_parameters.get("dashboard_run_setup"), dict)
            else {},
            session_dir=session_dir,
            source_base_dir=REPO_ROOT,
        ),
    )
    _write_session_manifest(package, wavs)
    return package


def load_run_package(manifest_path: Path) -> RunPackage:
    """Rehydrate a prepared run package from its session manifest."""
    manifest_path = Path(manifest_path)
    data = _load_json(manifest_path)
    if data.get("schema") != RUN_PACKAGE_SCHEMA:
        raise ValueError(f"Unsupported run package manifest: {manifest_path}")
    session_dir = manifest_path.parent
    blocks = [
        RunBlock(
            index=int(item["index"]),
            label=str(item["label"]),
            manifest_path=Path(item["manifest_path"]),
            wav_path=Path(item["wav_path"]),
            trial_count=int(item["trial_count"]),
            duration_s=float(item["duration_s"]),
            metadata=dict(item.get("metadata", {}) or {}),
        )
        for item in data.get("blocks", [])
    ]
    return RunPackage(
        participant_id=str(data.get("participant_id", "")),
        session_id=str(data.get("session_id", session_dir.name)),
        created_at=str(data.get("created_at", "")),
        session_dir=session_dir,
        design_path=Path(str(data.get("design_path", session_dir / "design.json"))),
        protocol_path=Path(str(data.get("protocol_path", session_dir / "protocol_schedule.csv"))),
        manifest_path=manifest_path,
        render_manifest_path=Path(str(data["render_manifest_path"])) if data.get("render_manifest_path") else None,
        blocks=blocks,
        execution_mode=str(data.get("execution_mode") or "design_schedule_blocks"),
        source_run_setup_manifest_path=Path(str(data["source_run_setup_manifest_path"])) if data.get("source_run_setup_manifest_path") else None,
        instruction_profile=_normalize_instruction_profile(data.get("instruction_profile", {})),
    )


def find_latest_dashboard_run_setup(
    registry_root: Path = DEFAULT_PROJECT_REGISTRY_ROOT,
) -> Path | None:
    """Return the newest prepared Segment 6 manifest under the dashboard registry."""
    root = Path(registry_root)
    if not _path_exists(root):
        return None
    candidates: list[Path] = []
    for manifest_path in root.glob("*/6_experiment_run_setup/experiment_run_setup_manifest.json"):
        manifest = _load_json(manifest_path)
        if manifest.get("schema") != SEGMENT_RUN_SETUP_SCHEMA or not bool(manifest.get("prepared")):
            continue
        csv_path = _resolve_relative_path(manifest.get("csv_path", ""), manifest_path.parent)
        if _path_exists(csv_path):
            candidates.append(manifest_path)
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def record_experiment_activity(
    event_type: str,
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    **payload: Any,
) -> Path:
    """Append a local dashboard activity event and update the resume pointer."""
    root = Path(state_root)
    root.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now().isoformat(timespec="seconds")
    event = {
        "schema": LAST_EXPERIMENT_SCHEMA,
        "event_type": str(event_type or "activity"),
        "created_at": created_at,
        **_json_ready(payload),
    }
    log_path = root / "experiment_activity_log.jsonl"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")

    pointer_path = root / "last_experiment.v1.json"
    if event["event_type"] not in LAUNCHABLE_ACTIVITY_EVENTS:
        return pointer_path
    pointer = _load_json(pointer_path) if _path_exists(pointer_path) else {}
    pointer.update({key: value for key, value in event.items() if value not in (None, "")})
    pointer["schema"] = LAST_EXPERIMENT_SCHEMA
    pointer["updated_at"] = created_at
    pointer["last_event_type"] = event["event_type"]
    pointer_path.write_text(json.dumps(pointer, indent=2), encoding="utf-8")
    return pointer_path


def load_last_experiment_pointer(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> dict[str, Any]:
    pointer_path = Path(state_root) / "last_experiment.v1.json"
    data = _load_json(pointer_path)
    if data.get("schema") != LAST_EXPERIMENT_SCHEMA:
        return {}
    return data


def segment_run_setup_participants(run_setup_manifest_path: Path) -> list[str]:
    """List participant IDs available in a prepared Segment 6 order table."""
    manifest, order_rows, _csv_path = _load_segment_run_setup(run_setup_manifest_path)
    participants = sorted(
        {
            str(row.get("participant_id") or "").strip()
            for row in order_rows
            if str(row.get("participant_id") or "").strip()
        },
        key=_participant_sort_key,
    )
    if int(manifest.get("participant_count") or 0) and len(participants) != int(manifest.get("participant_count") or 0):
        return participants
    return participants


def _emit_prepare_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    message: str,
    *,
    phase: str = "",
    current: int = 0,
    total: int = 0,
    detail: str = "",
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        {
            "phase": phase or message,
            "message": message,
            "detail": detail,
            "current": int(current or 0),
            "total": int(total or 0),
            "timestamp_unix": time.time(),
        }
    )


def _prepared_session_queue_path(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> Path:
    return Path(state_root) / "prepared_session_queue.v1.json"


def _load_prepared_session_queue(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> dict[str, Any]:
    path = _prepared_session_queue_path(state_root)
    data = _load_json(path)
    if data.get("schema") != PREPARED_SESSION_QUEUE_SCHEMA:
        return {"schema": PREPARED_SESSION_QUEUE_SCHEMA, "entries": []}
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def _write_prepared_session_queue(state_root: Path, queue_data: dict[str, Any]) -> Path:
    path = _prepared_session_queue_path(state_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    queue_data["schema"] = PREPARED_SESSION_QUEUE_SCHEMA
    queue_data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    path.write_text(json.dumps(_json_ready(queue_data), indent=2, sort_keys=True), encoding="utf-8")
    return path


def _run_setup_queue_hash(run_setup_manifest_path: Path) -> str:
    path = Path(run_setup_manifest_path)
    return _sha256_file(path) if _path_exists(path) else ""


def record_prepared_session_queue(
    *,
    participant_id: str,
    run_setup_manifest_path: Path,
    session_manifest_path: Path | None = None,
    status: str,
    message: str = "",
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
) -> Path:
    queue_data = _load_prepared_session_queue(state_root)
    run_setup = Path(run_setup_manifest_path).resolve()
    participant = sanitize_participant_id(participant_id)
    now = datetime.now().isoformat(timespec="seconds")
    entries = [
        entry
        for entry in queue_data.get("entries", [])
        if not (
            str(entry.get("participant_id") or "") == participant
            and str(entry.get("run_setup_manifest_path") or "") == str(run_setup)
            and str(entry.get("status") or "") in {"preparing", "ready", "failed"}
        )
    ]
    entries.append(
        {
            "participant_id": participant,
            "run_setup_manifest_path": str(run_setup),
            "run_setup_sha256": _run_setup_queue_hash(run_setup),
            "session_manifest_path": "" if session_manifest_path is None else str(Path(session_manifest_path).resolve()),
            "status": str(status or "unknown"),
            "message": str(message or ""),
            "created_at": now,
            "updated_at": now,
        }
    )
    queue_data["entries"] = entries[-100:]
    return _write_prepared_session_queue(state_root, queue_data)


def claim_prepared_session(
    run_setup_manifest_path: Path,
    participant_id: str,
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
) -> Path | None:
    queue_data = _load_prepared_session_queue(state_root)
    run_setup = Path(run_setup_manifest_path).resolve()
    participant = sanitize_participant_id(participant_id)
    run_setup_hash = _run_setup_queue_hash(run_setup)
    changed = False
    for entry in queue_data.get("entries", []):
        if str(entry.get("status") or "") != "ready":
            continue
        if str(entry.get("participant_id") or "") != participant:
            continue
        if str(entry.get("run_setup_manifest_path") or "") != str(run_setup):
            continue
        if str(entry.get("run_setup_sha256") or "") != run_setup_hash:
            entry["status"] = "stale"
            entry["message"] = "Run setup changed after prewarm."
            entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            continue
        manifest_path = Path(str(entry.get("session_manifest_path") or ""))
        if not _path_exists(manifest_path):
            entry["status"] = "missing"
            entry["message"] = "Prepared session manifest is missing."
            entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            continue
        try:
            package = load_run_package(manifest_path)
        except Exception as exc:
            entry["status"] = "invalid"
            entry["message"] = str(exc)
            entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            continue
        if package.participant_id != participant or not package.blocks:
            entry["status"] = "invalid"
            entry["message"] = "Prepared session does not match participant or has no blocks."
            entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            continue
        entry["status"] = "claimed"
        entry["claimed_at"] = datetime.now().isoformat(timespec="seconds")
        entry["updated_at"] = entry["claimed_at"]
        _write_prepared_session_queue(state_root, queue_data)
        return manifest_path
    if changed:
        _write_prepared_session_queue(state_root, queue_data)
    return None


def prepared_session_asset_status(
    run_setup_manifest_path: Path,
    participant_id: str,
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    session_root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, Any]:
    """Return a read-only status for a participant's prepared local audio package."""
    run_setup = Path(run_setup_manifest_path).resolve()
    participant = sanitize_participant_id(participant_id)
    if not participant:
        return {
            "participant_id": "",
            "generated": False,
            "status": "not_generated",
            "session_manifest_path": "",
            "message": "Participant ID is required.",
            "source": "",
            **_participant_data_collection_status(run_setup, ""),
        }

    run_setup_hash = _run_setup_queue_hash(run_setup)
    fallback_message = ""
    data_status = _participant_data_collection_status(run_setup, participant, session_root=session_root)
    queue_data = _load_prepared_session_queue(state_root)
    for entry in reversed(list(queue_data.get("entries", []))):
        if str(entry.get("participant_id") or "") != participant:
            continue
        if str(entry.get("run_setup_manifest_path") or "") != str(run_setup):
            continue
        status = str(entry.get("status") or "").strip().lower()
        if str(entry.get("run_setup_sha256") or "") != run_setup_hash:
            fallback_message = "Prepared queue entry is stale."
            continue
        manifest_path = Path(str(entry.get("session_manifest_path") or ""))
        if status == "preparing":
            return {
                "participant_id": participant,
                "generated": False,
                "status": "preparing",
                "session_manifest_path": str(manifest_path) if manifest_path else "",
                "message": str(entry.get("message") or "Preparing audio assets."),
                "source": "prepared_session_queue",
                **data_status,
            }
        if status == "failed":
            fallback_message = str(entry.get("message") or "Previous generation failed.")
            continue
        if status in {"ready", "claimed"}:
            valid, message = _prepared_session_manifest_ready_for_run_setup(manifest_path, run_setup, participant)
            if valid:
                return {
                    "participant_id": participant,
                    "generated": True,
                    "status": "ready" if status == "ready" else "generated",
                    "session_manifest_path": str(manifest_path.resolve()),
                    "message": message,
                    "source": "prepared_session_queue",
                    **data_status,
                }
            fallback_message = message

    scanned = _scan_prepared_session_manifest(run_setup, participant, session_root=session_root)
    if scanned is not None:
        manifest_path, message = scanned
        return {
            "participant_id": participant,
            "generated": True,
            "status": "generated",
            "session_manifest_path": str(manifest_path.resolve()),
            "message": message,
            "source": "session_scan",
            **data_status,
        }

    return {
        "participant_id": participant,
        "generated": False,
        "status": "not_generated",
        "session_manifest_path": "",
        "message": fallback_message or "No prepared local audio package found.",
        "source": "",
        **data_status,
    }


def prepared_session_asset_statuses(
    run_setup_manifest_path: Path,
    participant_ids: Iterable[str],
    *,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    session_root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, dict[str, Any]]:
    """Return prepared-package status for multiple participants."""
    return {
        sanitize_participant_id(participant_id): prepared_session_asset_status(
            run_setup_manifest_path,
            participant_id,
            state_root=state_root,
            session_root=session_root,
        )
        for participant_id in participant_ids
        if sanitize_participant_id(participant_id)
    }


def _prepared_session_manifest_ready_for_run_setup(
    manifest_path: Path,
    run_setup_manifest_path: Path,
    participant_id: str,
) -> tuple[bool, str]:
    if not manifest_path or not _path_exists(manifest_path):
        return False, "Prepared session manifest is missing."
    try:
        package = load_run_package(manifest_path)
    except Exception as exc:
        return False, str(exc)
    if package.participant_id != participant_id:
        return False, "Prepared session participant does not match."
    source_path = package.source_run_setup_manifest_path
    if source_path is None or Path(source_path).resolve() != Path(run_setup_manifest_path).resolve():
        return False, "Prepared session belongs to a different run setup."
    if not package.blocks:
        return False, "Prepared session has no blocks."
    for block in package.blocks:
        wav_path = _session_package_path(package, block.wav_path)
        manifest = _session_package_path(package, block.manifest_path)
        if not _path_exists(wav_path):
            return False, f"Prepared block WAV is missing: {wav_path}"
        if not _path_exists(manifest):
            return False, f"Prepared block manifest is missing: {manifest}"
    return True, "Prepared local audio package is available."


def _scan_prepared_session_manifest(
    run_setup_manifest_path: Path,
    participant_id: str,
    *,
    session_root: Path = DEFAULT_SESSION_ROOT,
) -> tuple[Path, str] | None:
    root = Path(session_root)
    if not _path_exists(root):
        return None
    candidates = sorted(
        root.glob(f"{participant_id}_*/session_manifest.json"),
        key=lambda path: path.stat().st_mtime if _path_exists(path) else 0.0,
        reverse=True,
    )
    for manifest_path in candidates:
        valid, message = _prepared_session_manifest_ready_for_run_setup(manifest_path, run_setup_manifest_path, participant_id)
        if valid:
            return manifest_path, message
    return None


def _participant_data_collection_status(
    run_setup_manifest_path: Path,
    participant_id: str,
    *,
    session_root: Path = DEFAULT_SESSION_ROOT,
) -> dict[str, Any]:
    base = {
        "data_collected": False,
        "data_collection_status": "not_collected",
        "data_session_manifest_path": "",
        "data_session_dir": "",
        "data_collection_message": "No completed participant data found.",
    }
    participant = sanitize_participant_id(participant_id)
    if not participant:
        base["data_collection_message"] = "Participant ID is required."
        return base
    root = Path(session_root)
    if not _path_exists(root):
        return base
    candidates = sorted(
        root.glob(f"{participant}_*/session_manifest.json"),
        key=lambda path: path.stat().st_mtime if _path_exists(path) else 0.0,
        reverse=True,
    )
    for manifest_path in candidates:
        package = _load_matching_session_package(manifest_path, run_setup_manifest_path, participant)
        if package is None:
            continue
        collected, message = _session_package_has_completed_data(package)
        if collected:
            return {
                "data_collected": True,
                "data_collection_status": "collected",
                "data_session_manifest_path": str(package.manifest_path.resolve()),
                "data_session_dir": str(package.session_dir.resolve()),
                "data_collection_message": message,
            }
        if message:
            base["data_collection_status"] = "incomplete"
            base["data_collection_message"] = message
            base["data_session_manifest_path"] = str(package.manifest_path.resolve())
            base["data_session_dir"] = str(package.session_dir.resolve())
    return base


def _load_matching_session_package(
    manifest_path: Path,
    run_setup_manifest_path: Path,
    participant_id: str,
) -> RunPackage | None:
    if not manifest_path or not _path_exists(manifest_path):
        return None
    try:
        package = load_run_package(manifest_path)
    except Exception:
        return None
    if package.participant_id != participant_id:
        return None
    source_path = package.source_run_setup_manifest_path
    if source_path is None or Path(source_path).resolve() != Path(run_setup_manifest_path).resolve():
        return None
    if not package.blocks:
        return None
    return package


def _session_package_has_completed_data(package: RunPackage) -> tuple[bool, str]:
    events_csv = Path(package.session_dir) / "events.csv"
    if not _path_exists(events_csv):
        return False, ""
    try:
        with events_csv.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("event_type") or "").strip() != "session_end":
                    continue
                payload = _json_loads_dict(row.get("payload_json"))
                completed = payload.get("completed", row.get("completed"))
                interrupted = payload.get("interrupted", row.get("interrupted"))
                if _truthy(completed) and not _truthy(interrupted):
                    return True, "Completed participant data found."
                return False, "Participant data exists, but the session did not complete."
    except Exception as exc:
        return False, f"Participant data status could not be read: {exc}"
    return False, "Participant data exists, but no completed session_end marker was found."


def _json_loads_dict(value: Any) -> dict[str, Any]:
    try:
        payload = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _session_package_path(package: RunPackage, value: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else Path(package.session_dir) / path


def next_segment_participant(run_setup_manifest_path: Path, participant_id: str) -> str | None:
    participants = segment_run_setup_participants(run_setup_manifest_path)
    current = sanitize_participant_id(participant_id)
    if current not in participants:
        return participants[0] if participants else None
    index = participants.index(current) + 1
    return participants[index] if index < len(participants) else None


def _block_cache_root(block_cache_root: Path = DEFAULT_SESSION_BLOCK_CACHE_ROOT) -> Path:
    return Path(block_cache_root)


def _segment_block_cache_key(
    *,
    source_csv: Path,
    source_rows: list[dict[str, str]],
    source_run_setup_manifest_path: Path,
) -> str:
    ordered_rows = sorted(source_rows, key=lambda row: _as_int(row.get("block_trial_index"), default=0))
    row_payload: list[dict[str, str]] = []
    for row in ordered_rows:
        trial_path = _resolve_relative_path(_row_value(row, "trial_file_path", "Trial_File_Path", default=""), source_csv.parent)
        expected_hash = str(_row_value(row, "source_sha256", "Source_SHA256", default="")).strip()
        actual_hash = expected_hash or (_sha256_file(trial_path) if _path_exists(trial_path) else "")
        row_payload.append(
            {
                "trial_file_path": str(trial_path.resolve()) if trial_path else "",
                "source_sha256": actual_hash,
                "block_trial_index": str(_row_value(row, "block_trial_index", "Block_Trial_Index", default="")),
                "family": str(_row_value(row, "family", "Family", default="")),
                "soa_ms": str(_row_value(row, "soa_ms", "SOA_ms", default="")),
            }
        )
    payload = {
        "schema": BLOCK_WAV_CACHE_SCHEMA,
        "version": BLOCK_WAV_CACHE_VERSION,
        "source_csv_path": str(Path(source_csv).resolve()),
        "source_csv_sha256": _sha256_file(source_csv),
        "source_run_setup_sha256": _sha256_file(source_run_setup_manifest_path)
        if _path_exists(source_run_setup_manifest_path)
        else "",
        "rows": row_payload,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _segment_block_cache_paths(cache_key: str, block_cache_root: Path = DEFAULT_SESSION_BLOCK_CACHE_ROOT) -> tuple[Path, Path]:
    root = _block_cache_root(block_cache_root) / cache_key[:2] / cache_key
    return root / "block.wav", root / "block_cache_manifest.json"


def _link_or_copy_cached_block(source: Path, target: Path) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    if _path_exists(target):
        Path(_filesystem_path(target)).unlink()
    try:
        os.link(_filesystem_path(source), _filesystem_path(target))
        return "hardlink"
    except OSError:
        shutil.copy2(_filesystem_path(source), _filesystem_path(target))
        return "copy"


def _cache_manifest_trial_payload(trial_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for row in trial_rows:
        start_sample = _as_int(row.get("Trial_Start_Sample"), default=0)
        end_sample = _as_int(row.get("Trial_End_Sample"), default=start_sample)
        trials.append(
            {
                "trial_file_path": row.get("Trial_File_Path", ""),
                "source_sha256": row.get("Source_SHA256", ""),
                "sample_rate": _as_int(row.get("Sample_Rate_Hz"), default=0),
                "channels": _as_int(row.get("Channels"), default=0),
                "duration_frames": max(0, end_sample - start_sample),
            }
        )
    return trials


def _write_block_cache_manifest(
    manifest_path: Path,
    *,
    cache_key: str,
    source_csv: Path,
    source_run_setup_manifest_path: Path,
    block_wav_path: Path,
    duration_s: float,
    sample_rate: int,
    channels: int,
    trial_rows: list[dict[str, Any]],
) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": BLOCK_WAV_CACHE_SCHEMA,
        "version": BLOCK_WAV_CACHE_VERSION,
        "cache_key": cache_key,
        "source_csv_path": str(Path(source_csv).resolve()),
        "source_csv_sha256": _sha256_file(source_csv),
        "source_run_setup_manifest_path": str(Path(source_run_setup_manifest_path).resolve()),
        "source_run_setup_sha256": _sha256_file(source_run_setup_manifest_path)
        if _path_exists(source_run_setup_manifest_path)
        else "",
        "block_wav_path": str(block_wav_path),
        "duration_s": float(duration_s),
        "sample_rate": int(sample_rate),
        "channels": int(channels),
        "trials": _cache_manifest_trial_payload(trial_rows),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    manifest_path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True), encoding="utf-8")


def _read_valid_block_cache(
    *,
    cache_key: str,
    source_csv: Path,
    source_rows: list[dict[str, str]],
    source_run_setup_manifest_path: Path,
    block_cache_root: Path = DEFAULT_SESSION_BLOCK_CACHE_ROOT,
) -> tuple[Path, dict[str, Any]] | None:
    wav_path, manifest_path = _segment_block_cache_paths(cache_key, block_cache_root)
    if not (_path_exists(wav_path) and _path_exists(manifest_path)):
        return None
    manifest = _load_json(manifest_path)
    if manifest.get("schema") != BLOCK_WAV_CACHE_SCHEMA or manifest.get("cache_key") != cache_key:
        return None
    if manifest.get("version") != BLOCK_WAV_CACHE_VERSION:
        return None
    if str(manifest.get("source_csv_sha256") or "") != _sha256_file(source_csv):
        return None
    expected_run_hash = _sha256_file(source_run_setup_manifest_path) if _path_exists(source_run_setup_manifest_path) else ""
    if str(manifest.get("source_run_setup_sha256") or "") != expected_run_hash:
        return None
    trials = manifest.get("trials", [])
    if not isinstance(trials, list) or len(trials) != len(source_rows):
        return None
    return wav_path, manifest


def _segment_trial_rows_from_cache(
    source_rows: list[dict[str, str]],
    cache_manifest: dict[str, Any],
    *,
    participant_id: str,
    session_id: str,
    part_number: int,
    phase: str,
    phase_label: str,
    output_block_index: int,
    participant_block_position: int,
    source_block_index: int,
    source_block_label: str,
    source_block_csv_path: Path,
) -> tuple[float, int, int, list[dict[str, Any]], list[RenderedWav]]:
    ordered_rows = sorted(source_rows, key=lambda row: _as_int(row.get("block_trial_index"), default=0))
    cache_trials = list(cache_manifest.get("trials", []))
    source_block_hash = str(cache_manifest.get("source_csv_sha256") or _sha256_file(source_block_csv_path))
    sample_rate = _as_int(cache_manifest.get("sample_rate"), default=0)
    channels = _as_int(cache_manifest.get("channels"), default=3)
    frame_cursor = 0
    trial_rows: list[dict[str, Any]] = []
    wav_infos: list[RenderedWav] = []
    for trial_index, row in enumerate(ordered_rows, start=1):
        cached = dict(cache_trials[trial_index - 1])
        trial_path = Path(str(cached.get("trial_file_path") or ""))
        trial_hash = str(cached.get("source_sha256") or "")
        trial_rate = _as_int(cached.get("sample_rate"), default=sample_rate)
        trial_channels = _as_int(cached.get("channels"), default=channels)
        duration_frames = _as_int(cached.get("duration_frames"), default=0)
        duration_s = float(duration_frames / trial_rate) if trial_rate else 0.0
        trial_start_sample = frame_cursor
        trial_end_sample = frame_cursor + duration_frames
        looming_onset_s = _segment_looming_onset_s(row)
        tactile_onset_s = _segment_tactile_onset_s(row, looming_onset_s)
        family = _segment_family(row)
        trial_rows.append(
            _segment_session_trial_row(
                row,
                participant_id=participant_id,
                session_id=session_id,
                part_number=part_number,
                phase=phase,
                phase_label=phase_label,
                output_block_index=output_block_index,
                participant_block_position=participant_block_position,
                source_block_index=source_block_index,
                source_block_label=source_block_label,
                source_block_csv_path=source_block_csv_path,
                source_block_csv_sha256=source_block_hash,
                trial_index=trial_index,
                family=family,
                trial_file_path=trial_path,
                trial_file_sha256=trial_hash,
                sample_rate=trial_rate,
                source_channels=trial_channels,
                trial_start_sample=trial_start_sample,
                trial_end_sample=trial_end_sample,
                duration_s=duration_s,
                looming_onset_s=looming_onset_s,
                tactile_onset_s=tactile_onset_s,
            )
        )
        wav_infos.append(_wav_info(trial_path, sha256=trial_hash, label=trial_path.stem))
        frame_cursor = trial_end_sample
    duration_s = float(frame_cursor / sample_rate) if sample_rate else float(cache_manifest.get("duration_s") or 0.0)
    return duration_s, sample_rate, channels, trial_rows, wav_infos


def prepare_segment_run_package(
    run_setup_manifest_path: Path,
    participant_id: str,
    *,
    design: StimulusDesign | None = None,
    session_root: Path = DEFAULT_SESSION_ROOT,
    created_at: datetime | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    block_cache_root: Path = DEFAULT_SESSION_BLOCK_CACHE_ROOT,
    use_block_cache: bool = True,
) -> RunPackage:
    """Prepare one participant session from Segment 5 master blocks and Segment 6 order CSV.

    This is the dashboard-compatible path: Segment 5 defines reusable block CSVs,
    Segment 6 defines participant order, and this function materializes exactly
    one participant's ordered block WAVs.
    """
    clean_participant = sanitize_participant_id(participant_id)
    if not clean_participant:
        raise ValueError("Participant ID is required.")

    run_setup_manifest_path = Path(run_setup_manifest_path)
    _emit_prepare_progress(progress_callback, "Checking Segment artifacts", phase="checking", current=0, total=0)
    run_setup, order_rows, order_csv_path = _load_segment_run_setup(run_setup_manifest_path)
    participant_rows = [
        dict(row)
        for row in order_rows
        if str(row.get("participant_id") or "").strip() == clean_participant
    ]
    if not participant_rows:
        available = ", ".join(segment_run_setup_participants(run_setup_manifest_path)) or "none"
        raise ValueError(f"Participant {clean_participant} is not present in Segment 6 block order. Available: {available}.")

    participant_rows.sort(
        key=lambda row: (
            _as_int(row.get("phase_index"), default=1),
            _as_int(row.get("participant_block_position"), default=1),
        )
    )
    created_at = created_at or datetime.now()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    session_id = f"{clean_participant}_{timestamp}"
    session_dir = Path(session_root) / session_id
    block_dir = session_dir / "blocks"
    analysis_dir = session_dir / "analysis"
    block_dir.mkdir(parents=True, exist_ok=True)
    analysis_dir.mkdir(parents=True, exist_ok=True)
    _emit_prepare_progress(
        progress_callback,
        "Preparing Segment 6 setup",
        phase="segment6",
        current=0,
        total=len(participant_rows),
        detail=str(run_setup_manifest_path),
    )
    instruction_profile = _materialize_session_instruction_profile(
        run_setup.get("instruction_profile", {}),
        session_dir=session_dir,
        source_base_dir=run_setup_manifest_path.parent,
    )

    design_path = session_dir / "design.json"
    if design is None:
        design_path.write_text("{}\n", encoding="utf-8")
    else:
        save_design(design, design_path)

    protocol_path = session_dir / "protocol_schedule.csv"
    _write_segment_protocol_schedule(protocol_path, participant_rows, clean_participant, order_csv_path)

    blocks: list[RunBlock] = []
    source_wavs: list[RenderedWav] = []
    seen_wavs: set[Path] = set()
    total_blocks = len(participant_rows)
    for output_index, order_row in enumerate(participant_rows, start=1):
        source_csv = _resolve_relative_path(order_row.get("block_csv_path", ""), order_csv_path.parent)
        if not _path_exists(source_csv):
            raise FileNotFoundError(f"Segment 6 references a missing Segment 5 block CSV: {source_csv}")
        master_rows = _read_csv_rows(source_csv)
        if not master_rows:
            raise ValueError(f"Segment 5 block CSV has no trial rows: {source_csv}")

        phase = str(order_row.get("phase") or "single").strip().lower() or "single"
        part_number = _segment_part_number(phase)
        participant_position = _as_int(order_row.get("participant_block_position"), default=output_index)
        source_block_index = _as_int(order_row.get("source_block_index"), default=participant_position)
        label = str(order_row.get("block_label") or f"Block {participant_position:02d}").strip()
        base_stem = f"Block_{output_index:02d}_from_{Path(source_csv).stem}"
        block_csv_path = block_dir / f"{base_stem}.csv"
        block_wav_path = block_dir / f"{base_stem}.wav"

        _emit_prepare_progress(
            progress_callback,
            f"Loading WAV files for block {output_index}/{total_blocks}",
            phase="loading_wavs",
            current=output_index - 1,
            total=total_blocks,
            detail=str(source_csv),
        )
        cache_key = ""
        cache_status = "disabled"
        cache_link_mode = ""
        cached: tuple[Path, dict[str, Any]] | None = None
        if use_block_cache:
            cache_key = _segment_block_cache_key(
                source_csv=source_csv,
                source_rows=master_rows,
                source_run_setup_manifest_path=run_setup_manifest_path,
            )
            cached = _read_valid_block_cache(
                cache_key=cache_key,
                source_csv=source_csv,
                source_rows=master_rows,
                source_run_setup_manifest_path=run_setup_manifest_path,
                block_cache_root=block_cache_root,
            )
        if cached is not None:
            cached_wav_path, cache_manifest = cached
            cache_link_mode = _link_or_copy_cached_block(cached_wav_path, block_wav_path)
            cache_status = "hit"
            _emit_prepare_progress(
                progress_callback,
                f"Loading cached block {output_index}/{total_blocks}",
                phase="block_cache_hit",
                current=output_index,
                total=total_blocks,
                detail=str(block_wav_path),
            )
            duration_s, sample_rate, channels, trial_rows, wav_infos = _segment_trial_rows_from_cache(
                master_rows,
                cache_manifest,
                participant_id=clean_participant,
                session_id=session_id,
                part_number=part_number,
                phase=phase,
                phase_label=str(order_row.get("phase_label") or phase.title()),
                output_block_index=output_index,
                participant_block_position=participant_position,
                source_block_index=source_block_index,
                source_block_label=label,
                source_block_csv_path=source_csv,
            )
        else:
            _emit_prepare_progress(
                progress_callback,
                f"Assembling block {output_index}/{total_blocks}",
                phase="assembling_block",
                current=output_index,
                total=total_blocks,
                detail=str(block_wav_path),
            )
            materialize_target = block_wav_path
            cache_wav_path = Path()
            cache_manifest_path = Path()
            if use_block_cache and cache_key:
                cache_wav_path, cache_manifest_path = _segment_block_cache_paths(cache_key, block_cache_root)
                cache_wav_path.parent.mkdir(parents=True, exist_ok=True)
                if _path_exists(cache_wav_path):
                    Path(_filesystem_path(cache_wav_path)).unlink()
                materialize_target = cache_wav_path
            duration_s, sample_rate, channels, trial_rows, wav_infos = _materialize_segment_block_wav(
                materialize_target,
                master_rows,
                participant_id=clean_participant,
                session_id=session_id,
                part_number=part_number,
                phase=phase,
                phase_label=str(order_row.get("phase_label") or phase.title()),
                output_block_index=output_index,
                participant_block_position=participant_position,
                source_block_index=source_block_index,
                source_block_label=label,
                source_block_csv_path=source_csv,
            )
            if use_block_cache and cache_key and cache_wav_path:
                _write_block_cache_manifest(
                    cache_manifest_path,
                    cache_key=cache_key,
                    source_csv=source_csv,
                    source_run_setup_manifest_path=run_setup_manifest_path,
                    block_wav_path=cache_wav_path,
                    duration_s=duration_s,
                    sample_rate=sample_rate,
                    channels=channels,
                    trial_rows=trial_rows,
                )
                cache_link_mode = _link_or_copy_cached_block(cache_wav_path, block_wav_path)
                cache_status = "miss_stored"
            else:
                cache_status = "disabled"
        _write_segment_block_csv(block_csv_path, trial_rows)
        for wav in wav_infos:
            resolved = wav.path.resolve()
            if resolved not in seen_wavs:
                source_wavs.append(wav)
                seen_wavs.add(resolved)
        blocks.append(
            RunBlock(
                index=output_index,
                label=label,
                manifest_path=block_csv_path,
                wav_path=block_wav_path,
                trial_count=len(trial_rows),
                duration_s=duration_s,
                metadata={
                    "execution_mode": "participant_block_wavs",
                    "phase": phase,
                    "phase_label": str(order_row.get("phase_label") or phase.title()),
                    "part_number": part_number,
                    "participant_block_position": participant_position,
                    "source_block_index": source_block_index,
                    "source_block_label": label,
                    "source_block_csv_path": str(source_csv),
                    "source_block_csv_sha256": _sha256_file(source_csv),
                    "sample_rate_hz": sample_rate,
                    "channels": channels,
                    "block_cache_key": cache_key,
                    "block_cache_status": cache_status,
                    "block_cache_link_mode": cache_link_mode,
                },
            )
        )

    manifest_path = session_dir / "session_manifest.json"
    package = RunPackage(
        participant_id=clean_participant,
        session_id=session_id,
        created_at=created_at.isoformat(timespec="seconds"),
        session_dir=session_dir,
        design_path=design_path,
        protocol_path=protocol_path,
        manifest_path=manifest_path,
        render_manifest_path=None,
        blocks=blocks,
        execution_mode="participant_block_wavs",
        source_run_setup_manifest_path=run_setup_manifest_path,
        instruction_profile=instruction_profile,
    )
    _emit_prepare_progress(
        progress_callback,
        "Writing session manifest",
        phase="writing_manifest",
        current=total_blocks,
        total=total_blocks,
        detail=str(manifest_path),
    )
    _write_session_manifest(package, source_wavs)
    _emit_prepare_progress(
        progress_callback,
        "Opening Focus Mode",
        phase="opening_focus_mode",
        current=total_blocks,
        total=total_blocks,
        detail=str(manifest_path),
    )
    return package


def prepare_all_segment_run_packages(
    run_setup_manifest_path: Path,
    *,
    design: StimulusDesign | None = None,
    session_root: Path = DEFAULT_SESSION_ROOT,
    created_at: datetime | None = None,
) -> list[RunPackage]:
    """Prepare every participant listed in a Segment 6 order manifest."""
    run_setup_manifest_path = Path(run_setup_manifest_path)
    participants = segment_run_setup_participants(run_setup_manifest_path)
    timestamp = created_at or datetime.now()
    return [
        prepare_segment_run_package(
            run_setup_manifest_path,
            participant,
            design=design,
            session_root=session_root,
            created_at=timestamp,
        )
        for participant in participants
    ]


class SessionRunnerController:
    """Runs a prepared package and writes recoverable session outputs."""

    def __init__(
        self,
        package: RunPackage,
        *,
        audio_engine: Any | None = None,
        capture_options: SessionCaptureOptions | dict[str, Any] | None = None,
        enable_lsl: bool | None = None,
        enable_topup: bool = False,
        runner_metadata: dict[str, Any] | None = None,
        topup_approval_callback: Callable[[dict[str, Any]], bool] | None = None,
        instruction_continue_callback: Callable[[dict[str, Any]], bool] | None = None,
    ):
        self.package = package
        self.audio_engine = audio_engine
        self.capture_options = _coerce_capture_options(capture_options, enable_lsl=enable_lsl)
        self.block_schedules = _block_event_schedules(package)
        self.trigger_dictionary = TriggerDictionary.from_schedules(self.block_schedules.values())
        self.logger = SessionEventLogger(package.participant_id)
        self.topup_ledger = (
            TopUpLedger(
                package.session_dir,
                participant_id=package.participant_id,
                session_id=package.session_id,
            )
            if enable_topup
            else None
        )
        self._runner_metadata_input = dict(runner_metadata or {})
        self._session_metadata_path = package.session_dir / "session_metadata.json"
        self._session_metadata = _build_runner_session_metadata(
            package,
            runner_metadata=self._runner_metadata_input,
            capture_options=self.capture_options,
            topup_enabled=enable_topup,
        )
        self._lsl_session_metadata = _redact_session_metadata_for_lsl(self._session_metadata)
        self._topup_approval_callback = topup_approval_callback
        self._instruction_continue_callback = instruction_continue_callback
        self.events = TimingEventHub(
            self.logger,
            enable_lsl=self.capture_options.enable_lsl,
            session_id=package.session_id,
            participant_id=package.participant_id,
            trigger_dictionary=self.trigger_dictionary,
            event_callback=self._handle_logged_event,
            stream_metadata=self._lsl_session_metadata,
        )
        self._stop_requested = False
        self._analysis_outputs: dict[str, Path] = {}
        self._summary_text = ""
        self._recording_paths: list[Path] = []
        self._accepting_responses = False
        self._active_block: RunBlock | None = None
        self._run_warnings: list[str] = []
        self._instruction_continue_event: threading.Event | None = None
        self._instruction_continue_source = ""
        self._instruction_wait_context: dict[str, Any] = {}
        self._progress_callback: ProgressCallback | None = None
        self._topup_draft_signature = ""

    def run(
        self,
        *,
        progress_callback: ProgressCallback | None = None,
        event_callback: EventCallback | None = None,
    ) -> SessionRunResult:
        completed = False
        interrupted = False
        owns_engine = self.audio_engine is None
        engine = self.audio_engine
        self._progress_callback = progress_callback
        session_metadata_path = self._write_session_metadata()
        self._lsl_session_metadata = _redact_session_metadata_for_lsl(self._session_metadata)
        self.events.log(
            "session_start",
            session_dir=str(self.package.session_dir),
            session_metadata_path=str(session_metadata_path),
            session_metadata_sha256=_sha256_file(session_metadata_path) if _path_exists(session_metadata_path) else "",
            session_metadata=self._lsl_session_metadata,
            lsl_enabled=self.events.lsl_status.enabled,
            lsl_message=self.events.lsl_status.message,
            capture_options=self.capture_options.as_dict(),
            topup_enabled=self.topup_ledger is not None,
        )
        try:
            if engine is None:
                engine = self._create_audio_engine()
                self.audio_engine = engine
            standard_blocks = [block for block in self.package.blocks if not _truthy(block.metadata.get("is_topup_block"))]
            display_by_block, topup_display_by_part, display_block_count = _run_playback_numbering(
                standard_blocks,
                include_topup_slots=self.topup_ledger is not None,
            )
            if not self._play_instruction_slot(
                engine,
                "before_experiment",
                event_callback=event_callback,
                needs_continue=bool(standard_blocks),
                context={"next_action": "start_experiment"},
            ):
                interrupted = True
            for block_index, block in enumerate(standard_blocks):
                if self._stop_requested:
                    interrupted = True
                    break
                if interrupted:
                    break
                if not self._play_instruction_slot(
                    engine,
                    "before_each_block",
                    event_callback=event_callback,
                    needs_continue=True,
                    context={
                        "next_action": "start_block",
                        "block_number": block.index,
                        "block_label": block.label,
                        **_event_metadata(block.metadata),
                    },
                ):
                    interrupted = True
                    break
                self._emit(event_callback, f"Block {block.index}: {block.label}")
                block_start_unix = time.time()
                block_start_monotonic = time.perf_counter()
                self.events.log(
                    "block_start",
                    unix_time=block_start_unix,
                    monotonic_time=block_start_monotonic,
                    block_number=block.index,
                    block_label=block.label,
                    block_path=str(block.wav_path),
                    trial_count=block.trial_count,
                    **_event_metadata(block.metadata),
                )
                schedule = self.block_schedules.get(block.index)
                if schedule is not None:
                    self.events.log(
                        "block_schedule_loaded",
                        block_number=block.index,
                        block_index=block.index,
                        block_label=block.label,
                        block_path=str(block.wav_path),
                        manifest_path=str(block.manifest_path),
                        scheduled_event_count=len(schedule),
                    )
                recording_path = self.package.session_dir / f"Block_{block.index:02d}_{_slug(block.label)}_audio_evidence.wav"
                recording_started = self._start_backup_recording(engine, recording_path, block)

                def _progress(elapsed_s: float, current_block: RunBlock = block) -> None:
                    self._emit_topup_draft(progress_callback, expire=True, now_unix=block_start_unix + float(elapsed_s or 0.0))
                    if progress_callback:
                        display_index = display_by_block.get(current_block.index, current_block.index)
                        progress_callback(
                            {
                                "block_index": current_block.index,
                                "display_block_index": display_index,
                                "play_order_index": display_index,
                                "block_label": current_block.label,
                                "elapsed_s": float(elapsed_s),
                                "duration_s": current_block.duration_s,
                                "session_id": self.package.session_id,
                                "part_number": _block_part_number(current_block),
                                "phase": str(current_block.metadata.get("phase") or ""),
                                "phase_label": str(current_block.metadata.get("phase_label") or current_block.metadata.get("phase") or ""),
                                "block_count": display_block_count,
                                "display_block_count": display_block_count,
                                "standard_block_index": current_block.index,
                                "standard_block_count": len(standard_blocks),
                                "is_topup": False,
                            }
                        )

                _emit_block_schedule_progress(
                    progress_callback,
                    block,
                    schedule,
                    total_blocks=display_block_count,
                    is_topup=False,
                    display_block_index=display_by_block.get(block.index, block.index),
                    display_block_count=display_block_count,
                )
                self._active_block = block
                self._accepting_responses = True
                try:
                    ok = bool(
                        self._play_block_with_schedule(
                            engine,
                            block,
                            progress_callback=_progress,
                            block_event_schedule=schedule,
                        )
                    )
                finally:
                    self._active_block = None
                self.events.flush_callback_events()
                if not self._has_logged_event("audio_sample_zero", block.index):
                    self.events.log(
                        "timing_anchor_fallback",
                        block_number=block.index,
                        block_index=block.index,
                        block_label=block.label,
                        reason="audio_sample_zero was not emitted by the audio engine",
                        timestamp_quality="block_anchor_fallback",
                    )
                    before_count = len(self.logger.events)
                    self.logger.extend_planned_block_events(
                        block.manifest_path,
                        block_start_unix=block_start_unix,
                        block_start_monotonic=block_start_monotonic,
                        participant_id=self.package.participant_id,
                        part_number=_as_int(block.metadata.get("part_number"), default=1),
                        block_number=block.index,
                        trial_duration_s=_trial_duration_s(block),
                        stimulus_segment_onset_s=0.0,
                    )
                    for fallback_event in self.logger.events[before_count:]:
                        self._handle_logged_event(fallback_event)
                self._stop_backup_recording(engine, recording_path, block, interrupted=(not ok or self._stop_requested), started=recording_started)
                self._accepting_responses = False
                self.events.log("block_end", block_number=block.index, block_label=block.label, completed=ok)
                self._persist_topup_state()
                if not ok or self._stop_requested:
                    interrupted = True
                    break
                next_block = standard_blocks[block_index + 1] if block_index + 1 < len(standard_blocks) else None
                same_condition = next_block is not None and _block_condition_key(next_block) == _block_condition_key(block)
                if not self._play_instruction_slot(
                    engine,
                    "after_each_block",
                    event_callback=event_callback,
                    needs_continue=bool(next_block and same_condition),
                    context={
                        "next_action": "next_block" if next_block else "after_experiment",
                        "block_number": block.index,
                        "block_label": block.label,
                        "next_block_number": next_block.index if next_block else "",
                        "next_block_label": next_block.label if next_block else "",
                        **_event_metadata(block.metadata),
                    },
                ):
                    interrupted = True
                    break
                part_boundary = next_block is None or _block_part_key(next_block) != _block_part_key(block)
                if part_boundary:
                    topup_ok = self._maybe_run_topup_block(
                        engine,
                        progress_callback=progress_callback,
                        event_callback=event_callback,
                        part_number=_block_part_number(block),
                        phase_label=str(block.metadata.get("phase_label") or block.metadata.get("phase") or ""),
                        display_block_index=topup_display_by_part.get(_block_part_key(block)),
                        display_block_count=display_block_count,
                    )
                    if not topup_ok:
                        interrupted = True
                        break
                if next_block is not None and not same_condition:
                    if not self._play_instruction_slot(
                        engine,
                        "between_conditions",
                        event_callback=event_callback,
                        needs_continue=True,
                        context={
                            "next_action": "next_condition",
                            "block_number": block.index,
                            "block_label": block.label,
                            "next_block_number": next_block.index,
                            "next_block_label": next_block.label,
                            "next_phase": next_block.metadata.get("phase_label", next_block.metadata.get("phase", "")),
                            **_event_metadata(next_block.metadata),
                        },
                    ):
                        interrupted = True
                        break
            if not interrupted and not self._stop_requested:
                if not self._play_instruction_slot(
                    engine,
                    "after_experiment",
                    event_callback=event_callback,
                    needs_continue=False,
                    context={"next_action": "finish_experiment"},
                ):
                    interrupted = True
            completed = not interrupted
            self.events.log("session_end", completed=completed, interrupted=interrupted)
        except Exception as exc:
            interrupted = True
            self.events.log("session_error", message=str(exc))
            self._emit(event_callback, f"Run error: {exc}")
        finally:
            self._progress_callback = None
            self._write_outputs()
            if owns_engine and self.audio_engine is not None and hasattr(self.audio_engine, "shutdown"):
                self.audio_engine.shutdown()

        return SessionRunResult(
            completed=completed,
            interrupted=interrupted,
            session_dir=self.package.session_dir,
            events_csv=self.package.session_dir / "events.csv",
            events_xdf=self.package.session_dir / "events.xdf",
            analysis_outputs=self._analysis_outputs,
            summary_text=self._summary_text,
            warnings=list(self._run_warnings) if completed else ["Session was interrupted before all blocks completed.", *self._run_warnings],
            lsl_status=dict(self.events.lsl_status.__dict__),
            recording_paths=list(self._recording_paths),
            lsl_markers_csv=self.package.session_dir / "lsl_markers.csv",
            lsl_markers_xdf=self.package.session_dir / "lsl_markers.xdf",
            trigger_dictionary_path=self.package.session_dir / "trigger_dictionary.json",
            session_metadata_path=self._session_metadata_path,
            capture_options=self.capture_options.as_dict(),
        )

    def _write_session_metadata(self) -> Path:
        self._session_metadata = _build_runner_session_metadata(
            self.package,
            runner_metadata=self._runner_metadata_input,
            capture_options=self.capture_options,
            topup_enabled=self.topup_ledger is not None,
            run_started_at=datetime.now().isoformat(timespec="seconds"),
            lsl_status=dict(self.events.lsl_status.__dict__),
        )
        self.package.session_dir.mkdir(parents=True, exist_ok=True)
        self._session_metadata_path.write_text(json.dumps(_json_ready(self._session_metadata), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return self._session_metadata_path

    def _handle_logged_event(self, event: Any) -> None:
        if self.topup_ledger is None:
            return
        self.topup_ledger.observe_event(event)
        self._emit_topup_draft(self._progress_callback, expire=False)

    def _persist_topup_state(self, *, part_number: int | str | None = None) -> None:
        if self.topup_ledger is None:
            return
        outputs = self.topup_ledger.write_outputs()
        draft_path = write_topup_draft_manifest(self.package.session_dir, self.topup_ledger, part_number=part_number)
        self._analysis_outputs.update(outputs)
        key = "topup_block_manifest_draft" if part_number is None else f"topup_block_manifest_part{_part_suffix(part_number)}_draft"
        self._analysis_outputs[key] = draft_path

    def _emit_topup_draft(
        self,
        progress_callback: ProgressCallback | None,
        *,
        expire: bool,
        part_number: int | str | None = None,
        now_unix: float | None = None,
    ) -> None:
        if self.topup_ledger is None or progress_callback is None:
            return
        if expire:
            self.topup_ledger.expire_due(float(now_unix if now_unix is not None else time.time()))
        payload = self._topup_draft_payload(part_number=part_number)
        signature = json.dumps(
            {
                "summary": payload.get("summary", {}),
                "missed": [
                    (
                        item.get("part_number", ""),
                        item.get("block_number", ""),
                        item.get("trial_number", ""),
                        item.get("trial_uid", ""),
                        item.get("status", ""),
                    )
                    for item in payload.get("missed_trials", [])
                ],
            },
            sort_keys=True,
        )
        if signature == self._topup_draft_signature:
            return
        self._topup_draft_signature = signature
        try:
            progress_callback(payload)
        except Exception:
            return

    def _topup_draft_payload(self, *, part_number: int | str | None = None) -> dict[str, Any]:
        if self.topup_ledger is None:
            return {
                "ui_event": "topup_draft",
                "topup_enabled": False,
                "part_number": "" if part_number is None else _part_suffix(part_number),
                "summary": {},
                "missed_trials": [],
            }
        entries = self.topup_ledger.missed_entries(include_topup=False)
        if part_number is not None:
            selected_part = _part_suffix(part_number)
            entries = [entry for entry in entries if _part_suffix(getattr(entry, "part_number", "")) == selected_part]
        missed_trials = [
            {
                "ledger_id": getattr(entry, "ledger_id", ""),
                "status": getattr(entry, "status", ""),
                "part_number": _part_suffix(getattr(entry, "part_number", "")),
                "phase_label": getattr(entry, "phase_label", ""),
                "block_number": getattr(entry, "block_number", ""),
                "block_label": getattr(entry, "block_label", ""),
                "trial_number": getattr(entry, "trial_number", ""),
                "trial_uid": getattr(entry, "trial_uid", ""),
                "trial_type": getattr(entry, "trial_type", ""),
                "family": getattr(entry, "family", ""),
                "row_label": getattr(entry, "row_label", ""),
                "respiratory_phase": getattr(entry, "respiratory_phase", ""),
                "soa_ms": getattr(entry, "soa_ms", ""),
                "noise_type": getattr(entry, "noise_type", ""),
                "sequence_labels": getattr(entry, "sequence_labels", ""),
                "miss_reason": getattr(entry, "miss_reason", ""),
            }
            for entry in entries
        ]
        summary = self.topup_ledger.summary()
        return {
            "ui_event": "topup_draft",
            "topup_enabled": True,
            "part_number": "" if part_number is None else _part_suffix(part_number),
            "summary": summary,
            "missed_trial_count": len(missed_trials),
            "missed_trials": missed_trials,
        }

    def _instruction_slot(self, slot_name: str) -> dict[str, Any] | None:
        profile = _normalize_instruction_profile(self.package.instruction_profile)
        for slot in profile.get("slots", []):
            if str(slot.get("slot") or "") == slot_name:
                return dict(slot)
        return None

    def _play_instruction_slot(
        self,
        engine: Any,
        slot_name: str,
        *,
        event_callback: EventCallback | None,
        needs_continue: bool,
        context: dict[str, Any] | None = None,
    ) -> bool:
        slot = self._instruction_slot(slot_name)
        if not slot or not bool(slot.get("enabled")):
            return not self._stop_requested
        context = dict(context or {})
        label = str(slot.get("label") or slot_name.replace("_", " ").title())
        path = Path(str(slot.get("path") or ""))
        payload = {
            "instruction_slot": slot_name,
            "instruction_label": label,
            "instruction_path": str(path),
            "instruction_continue_mode": str(slot.get("continue_mode") or "click"),
            **context,
        }
        if not _path_exists(path):
            self.events.log("instruction_missing", **payload)
            self._run_warnings.append(f"Instruction audio is missing for {label}: {path}")
            return not self._stop_requested
        self._emit(event_callback, f"Instruction: {label}")
        self.events.log(
            "instruction_start",
            duration_s=float(slot.get("duration_s") or 0.0),
            sha256=str(slot.get("sha256") or ""),
            **payload,
        )
        ok = self._play_instruction_audio(engine, path)
        self.events.log("instruction_end", completed=ok, **payload)
        if not ok or self._stop_requested:
            self.events.log("instruction_error", stopped=self._stop_requested, **payload)
            if self._stop_requested:
                return False
            self._run_warnings.append(f"Optional instruction audio could not be played for {label}; continuing without it.")
            return True
        if needs_continue:
            return self._await_instruction_continuation(slot, payload, event_callback=event_callback)
        return True

    def _play_instruction_audio(self, engine: Any, path: Path) -> bool:
        if not hasattr(engine, "play_instruction"):
            self.events.log("instruction_error", instruction_path=str(path), message="audio engine has no play_instruction API")
            return False
        finished = threading.Event()
        result = {"ok": False}

        def _done(success: bool = True) -> None:
            result["ok"] = bool(success)
            finished.set()

        try:
            returned = engine.play_instruction(str(path), _done)
        except TypeError:
            returned = engine.play_instruction(str(path))
            if isinstance(returned, bool):
                result["ok"] = bool(returned)
                finished.set()
        except Exception as exc:
            self.events.log("instruction_error", instruction_path=str(path), message=str(exc))
            return False
        if isinstance(returned, bool) and not finished.is_set():
            result["ok"] = bool(returned)
            finished.set()
        while not finished.wait(0.05):
            if self._stop_requested:
                if hasattr(engine, "stop"):
                    engine.stop()
                return False
        return bool(result["ok"])

    def _await_instruction_continuation(
        self,
        slot: dict[str, Any],
        payload: dict[str, Any],
        *,
        event_callback: EventCallback | None,
    ) -> bool:
        mode = str(slot.get("continue_mode") or "click").strip().lower()
        if mode not in {"click", "delay", "button"}:
            mode = "click"
        if mode == "delay":
            delay_s = max(0.0, float(slot.get("delay_s") or 0.0))
            self.events.log("instruction_continue_wait", mode=mode, delay_s=delay_s, **payload)
            self._emit(event_callback, f"Continuing in {delay_s:.1f}s")
            deadline = time.perf_counter() + delay_s
            while time.perf_counter() < deadline:
                if self._stop_requested:
                    return False
                time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))
            self.events.log("instruction_continue", mode=mode, source="timer", delay_s=delay_s, **payload)
            return not self._stop_requested

        self._instruction_continue_event = threading.Event()
        self._instruction_continue_source = ""
        self._instruction_wait_context = {**payload, "mode": mode, "button_label": str(slot.get("button_label") or "Continue")}
        self.events.log("instruction_continue_wait", **self._instruction_wait_context)
        self._emit(
            event_callback,
            (
                f"Click the response target to continue after {payload.get('instruction_label')}"
                if mode == "click"
                else str(slot.get("button_label") or "Continue")
            ),
        )
        try:
            if self._instruction_continue_callback is not None:
                try:
                    if bool(self._instruction_continue_callback(dict(self._instruction_wait_context))):
                        self.continue_instruction(source="callback")
                except Exception as exc:
                    self.events.log("instruction_error", message=str(exc), **payload)
                    return False
            while not self._instruction_continue_event.wait(0.05):
                if self._stop_requested:
                    return False
            self.events.log("instruction_continue", source=self._instruction_continue_source or mode, **payload)
            return not self._stop_requested
        finally:
            self._instruction_continue_event = None
            self._instruction_continue_source = ""
            self._instruction_wait_context = {}

    def _maybe_run_topup_block(
        self,
        engine: Any,
        *,
        progress_callback: ProgressCallback | None,
        event_callback: EventCallback | None,
        part_number: int | str | None = None,
        phase_label: str = "",
        display_block_index: int | None = None,
        display_block_count: int | None = None,
    ) -> bool:
        if self.topup_ledger is None:
            return True
        self.events.flush_callback_events()
        self.topup_ledger.finalize_open_trials(part_number=part_number)
        self._persist_topup_state(part_number=part_number)
        misses = self.topup_ledger.missed_entries(include_topup=False, part_number=part_number)
        if not misses:
            self.events.log("topup_not_needed", missed_trial_count=0, part_number="" if part_number is None else _part_suffix(part_number), phase_label=phase_label)
            self._persist_topup_state(part_number=part_number)
            return True
        try:
            block, manifest_outputs = self._materialize_topup_block(
                misses,
                part_number=part_number,
                phase_label=phase_label,
                display_block_index=display_block_index,
                display_block_count=display_block_count,
            )
        except Exception as exc:
            self.events.log("topup_block_materialize_failed", missed_trial_count=len(misses), part_number="" if part_number is None else _part_suffix(part_number), phase_label=phase_label, message=str(exc))
            self._run_warnings.append(f"Top-up block could not be materialized: {exc}")
            self._persist_topup_state(part_number=part_number)
            return True

        self._analysis_outputs.update(manifest_outputs)
        self.block_schedules[block.index] = BlockEventSchedule.from_block_manifest(
            block.manifest_path,
            block_index=block.index,
            block_label=block.label,
            block_wav_path=block.wav_path,
            participant_id=self.package.participant_id,
            session_id=self.package.session_id,
            part_number=block.metadata.get("part_number", ""),
            sample_rate=_as_int(block.metadata.get("sample_rate_hz"), default=0),
            block_metadata=block.metadata,
        )
        summary = {
            "missed_trial_count": len(misses),
            "topup_trial_count": block.trial_count,
            "rescue_trial_count": int(block.metadata.get("rescue_trial_count", 0) or 0),
            "filler_trial_count": int(block.metadata.get("filler_trial_count", 0) or 0),
            "part_number": "" if part_number is None else _part_suffix(part_number),
            "phase_label": phase_label,
            "manifest_path": str(block.manifest_path),
            "wav_path": str(block.wav_path),
        }
        self.events.log("topup_block_ready", **summary)
        approved = False
        if self._topup_approval_callback is not None:
            try:
                approved = bool(self._topup_approval_callback(dict(summary)))
            except Exception as exc:
                self.events.log("topup_block_approval_failed", message=str(exc), **summary)
                self._run_warnings.append(f"Top-up approval failed: {exc}")
        else:
            self._run_warnings.append("Top-up block was prepared but not played because operator approval was not configured.")
        if not approved:
            self.events.log("topup_block_skipped", reason="operator_not_approved", **summary)
            self._persist_topup_state(part_number=part_number)
            return True

        self.events.log("topup_block_approved", **summary)
        self._emit(event_callback, f"Top-up block: {block.label}")
        block_start_unix = time.time()
        block_start_monotonic = time.perf_counter()
        self.events.log(
            "block_start",
            unix_time=block_start_unix,
            monotonic_time=block_start_monotonic,
            block_number=block.index,
            block_label=block.label,
            block_path=str(block.wav_path),
            trial_count=block.trial_count,
            **_event_metadata(block.metadata),
        )
        schedule = self.block_schedules.get(block.index)
        if schedule is not None:
            self.events.log(
                "block_schedule_loaded",
                block_number=block.index,
                block_index=block.index,
                block_label=block.label,
                block_path=str(block.wav_path),
                manifest_path=str(block.manifest_path),
                scheduled_event_count=len(schedule),
            )
        recording_path = self.package.session_dir / f"Block_{block.index:02d}_{_slug(block.label)}_audio_evidence.wav"
        recording_started = self._start_backup_recording(engine, recording_path, block)

        def _progress(elapsed_s: float, current_block: RunBlock = block) -> None:
            if progress_callback:
                current_display_index = _as_int(
                    current_block.metadata.get("display_block_index", current_block.metadata.get("play_order_index")),
                    default=current_block.index,
                )
                current_display_count = _as_int(
                    current_block.metadata.get("display_block_count"),
                    default=len(self.package.blocks),
                )
                progress_callback(
                    {
                        "block_index": current_block.index,
                        "display_block_index": current_display_index,
                        "play_order_index": current_display_index,
                        "block_label": current_block.label,
                        "elapsed_s": float(elapsed_s),
                        "duration_s": current_block.duration_s,
                        "session_id": self.package.session_id,
                        "part_number": _block_part_number(current_block),
                        "phase": str(current_block.metadata.get("phase") or ""),
                        "phase_label": str(current_block.metadata.get("phase_label") or current_block.metadata.get("phase") or ""),
                        "block_count": current_display_count,
                        "display_block_count": current_display_count,
                        "standard_block_index": "",
                        "standard_block_count": sum(1 for item in self.package.blocks if not _truthy(item.metadata.get("is_topup_block"))),
                        "is_topup": True,
                    }
                )

        _emit_block_schedule_progress(
            progress_callback,
            block,
            schedule,
            total_blocks=_as_int(block.metadata.get("display_block_count"), default=len(self.package.blocks)),
            is_topup=True,
            display_block_index=_as_int(block.metadata.get("display_block_index"), default=block.index),
            display_block_count=_as_int(block.metadata.get("display_block_count"), default=len(self.package.blocks)),
        )
        self._active_block = block
        self._accepting_responses = True
        try:
            ok = bool(
                self._play_block_with_schedule(
                    engine,
                    block,
                    progress_callback=_progress,
                    block_event_schedule=schedule,
                )
            )
        finally:
            self._active_block = None
        self.events.flush_callback_events()
        if not self._has_logged_event("audio_sample_zero", block.index):
            self.events.log(
                "timing_anchor_fallback",
                block_number=block.index,
                block_index=block.index,
                block_label=block.label,
                reason="audio_sample_zero was not emitted by the audio engine",
                timestamp_quality="block_anchor_fallback",
            )
            before_count = len(self.logger.events)
            self.logger.extend_planned_block_events(
                block.manifest_path,
                block_start_unix=block_start_unix,
                block_start_monotonic=block_start_monotonic,
                participant_id=self.package.participant_id,
                part_number=_as_int(block.metadata.get("part_number"), default=1),
                block_number=block.index,
                trial_duration_s=_trial_duration_s(block),
                stimulus_segment_onset_s=0.0,
            )
            for fallback_event in self.logger.events[before_count:]:
                self._handle_logged_event(fallback_event)
        self._stop_backup_recording(engine, recording_path, block, interrupted=(not ok or self._stop_requested), started=recording_started)
        self._accepting_responses = False
        self.events.log("block_end", block_number=block.index, block_label=block.label, completed=ok, is_topup=True)
        self.topup_ledger.finalize_open_trials(part_number=part_number)
        self._persist_topup_state(part_number=part_number)
        if not ok:
            self._run_warnings.append("Top-up block was interrupted before completion.")
            return False
        return not self._stop_requested

    def stop(self) -> None:
        self._stop_requested = True
        if self.audio_engine is not None and hasattr(self.audio_engine, "stop"):
            self.audio_engine.stop()
        self.events.log("operator_stop")

    def pause(self) -> None:
        if self.audio_engine is not None and hasattr(self.audio_engine, "pause"):
            self.audio_engine.pause()
        self.events.log("operator_pause")

    def resume(self) -> None:
        if self.audio_engine is not None and hasattr(self.audio_engine, "resume"):
            self.audio_engine.resume()
        self.events.log("operator_resume")

    def awaiting_instruction_continue(self) -> dict[str, Any]:
        return dict(self._instruction_wait_context)

    def continue_instruction(self, *, source: str = "operator") -> None:
        if self._instruction_continue_event is None:
            return
        self._instruction_continue_source = str(source or "operator")
        self._instruction_continue_event.set()

    def log_click(self, *, x: int | None = None, y: int | None = None, in_target: bool = True) -> None:
        if self._instruction_continue_event is not None:
            self.continue_instruction(source="target_click")
            return
        during_playback = self._accepting_responses
        active_block = self._active_block
        block_payload = {
            "block_number": active_block.index if active_block else "",
            "block_label": active_block.label if active_block else "",
            "part_number": _block_part_number(active_block) if active_block else "",
            "phase": active_block.metadata.get("phase", "") if active_block else "",
            "phase_label": active_block.metadata.get("phase_label", "") if active_block else "",
            "is_topup": bool(active_block.metadata.get("is_topup") or active_block.metadata.get("is_topup_block")) if active_block else False,
        }
        event = self.events.log(
            "mouse_click",
            x=x if x is not None else "",
            y=y if y is not None else "",
            in_target=in_target,
            during_playback=during_playback,
            **block_payload,
            push_lsl=False,
        )
        if during_playback and self.audio_engine is not None and hasattr(self.audio_engine, "trigger_click"):
            self.audio_engine.trigger_click(
                metadata={
                    "mouse_event_id": event.event_id,
                    "mouse_event_unix_time": event.unix_time,
                    "mouse_event_monotonic_time": event.monotonic_time,
                    "block_number": block_payload["block_number"],
                    "block_label": block_payload["block_label"],
                    "part_number": block_payload["part_number"],
                    "phase": block_payload["phase"],
                    "phase_label": block_payload["phase_label"],
                    "is_topup": block_payload["is_topup"],
                },
                marker_gain=RESPONSE_MARKER_GAIN,
            )
        self.events.push_deferred_event_marker(event)

    def _materialize_topup_block(
        self,
        misses: list[Any],
        *,
        part_number: int | str | None = None,
        phase_label: str = "",
        display_block_index: int | None = None,
        display_block_count: int | None = None,
    ) -> tuple[RunBlock, dict[str, Path]]:
        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("Install numpy and soundfile to prepare a top-up block.") from exc

        source_by_uid, row_order, rows_by_label = _topup_source_index(self.package, part_number=part_number)
        if not row_order:
            row_order = sorted({str(getattr(entry, "row_label", "") or "row") for entry in misses})
        missed_uids = {str(getattr(entry, "trial_uid", "") or "") for entry in misses}
        hit_entries = self.topup_ledger.hit_entries(include_topup=False, part_number=part_number) if self.topup_ledger is not None else []
        hit_filler_by_label: dict[str, list[tuple[dict[str, Any], Path, RunBlock]]] = {}
        for entry in hit_entries:
            source = source_by_uid.get(str(entry.trial_uid))
            if source is None:
                continue
            label = _topup_row_label(source[0]) or str(entry.row_label or "")
            hit_filler_by_label.setdefault(label, []).append(source)

        miss_queues: dict[str, list[tuple[Any, dict[str, Any], Path, RunBlock]]] = {}
        for entry in misses:
            source = source_by_uid.get(str(entry.trial_uid))
            if source is None:
                source = (_topup_entry_source_row(entry), self.package.session_dir, self.package.blocks[-1] if self.package.blocks else _empty_topup_source_block())
            label = _topup_row_label(source[0]) or str(getattr(entry, "row_label", "") or "row")
            if label not in row_order:
                row_order.append(label)
            miss_queues.setdefault(label, []).append((entry, source[0], source[1], source[2]))

        filler_index_by_label: dict[str, int] = {}

        def _filler_for(label: str) -> tuple[dict[str, Any], Path, RunBlock] | None:
            candidates = hit_filler_by_label.get(label) or [
                item for item in rows_by_label.get(label, []) if str(item[0].get("Trial_UID") or "") not in missed_uids
            ] or rows_by_label.get(label, [])
            if not candidates:
                return None
            index = filler_index_by_label.get(label, 0)
            filler_index_by_label[label] = index + 1
            return candidates[index % len(candidates)]

        emitted: list[tuple[str, Any | None, dict[str, Any], Path, RunBlock]] = []
        while any(queue for queue in miss_queues.values()):
            for label in row_order:
                queue = miss_queues.get(label, [])
                if queue:
                    entry, row, base_dir, source_block = queue.pop(0)
                    emitted.append(("rescue", entry, row, base_dir, source_block))
                elif any(queue for queue in miss_queues.values()):
                    filler = _filler_for(label)
                    if filler is not None:
                        row, base_dir, source_block = filler
                        emitted.append(("filler", None, row, base_dir, source_block))
        if not emitted:
            raise ValueError("No missed tactile rows were available for top-up block generation.")

        block_index = max((block.index for block in self.package.blocks), default=0) + 1
        display_index = _as_int(display_block_index, default=block_index)
        display_count = _as_int(display_block_count, default=display_index)
        part_label = _part_suffix(part_number)
        multi_part = len(_package_part_numbers(self.package)) > 1
        block_label = f"Part {part_label} top-up missed tactile trials" if multi_part and part_label else "Top-up missed tactile trials"
        block_stem = f"Block_{block_index:02d}_{'part' + part_label + '_' if multi_part and part_label else ''}topup_missed_trials"
        wav_path = self.package.session_dir / "blocks" / f"{block_stem}.wav"
        manifest_stem = f"topup_block_part{part_label}_manifest" if multi_part and part_label else "topup_block_manifest"
        csv_path = self.package.session_dir / f"{manifest_stem}.csv"
        json_path = self.package.session_dir / f"{manifest_stem}.json"

        clips: list[Any] = []
        sample_rate = 0
        target_channels = 3
        frame_cursor = 0
        trial_rows: list[dict[str, Any]] = []
        for trial_index, (role, entry, source_row, source_base_dir, source_block) in enumerate(emitted, start=1):
            trial_path = _resolve_relative_path(_row_value(source_row, "Trial_File_Path", "trial_file_path", default=""), source_base_dir)
            if not _path_exists(trial_path):
                raise FileNotFoundError(f"Top-up source trial WAV is missing: {trial_path}")
            expected_hash = str(_row_value(source_row, "Source_SHA256", "source_sha256", default="")).strip()
            actual_hash = _sha256_file(trial_path)
            if expected_hash and expected_hash != actual_hash:
                raise ValueError(f"Top-up trial WAV hash mismatch for {trial_path.name}.")
            data, rate = sf.read(_soundfile_path(trial_path), dtype="float32", always_2d=True)
            if sample_rate and int(rate) != sample_rate:
                raise ValueError("Top-up block source rows contain mixed sample rates.")
            sample_rate = int(rate)
            target_channels = max(target_channels, int(data.shape[1]))
            clips.append(data)
            duration_frames = int(data.shape[0])
            trial_start_sample = frame_cursor
            trial_end_sample = frame_cursor + duration_frames
            duration_s = float(duration_frames / sample_rate) if sample_rate else 0.0
            looming_onset_s = _segment_looming_onset_s(source_row)
            tactile_onset_s = _segment_tactile_onset_s(source_row, looming_onset_s)
            family = _segment_family(source_row)
            source_uid = str(_row_value(source_row, "Trial_UID", "trial_uid", default=getattr(entry, "trial_uid", ""))).strip()
            source_block_csv = _resolve_relative_path(
                _row_value(source_row, "Source_Block_CSV_Path", "source_block_csv_path", default=str(source_block.manifest_path)),
                source_base_dir,
            )
            source_block_hash = str(_row_value(source_row, "Source_Block_CSV_SHA256", default="")).strip()
            if not source_block_hash and _path_exists(source_block_csv):
                source_block_hash = _sha256_file(source_block_csv)
            row = _segment_session_trial_row(
                source_row,
                participant_id=self.package.participant_id,
                session_id=self.package.session_id,
                part_number=_as_int(_row_value(source_row, "Part_Number", default=source_block.metadata.get("part_number", 1)), default=1),
                phase=str(_row_value(source_row, "Phase", default="topup") or "topup"),
                phase_label=str(_row_value(source_row, "Phase_Label", default="Top-up") or "Top-up"),
                output_block_index=block_index,
                participant_block_position=block_index,
                source_block_index=_as_int(_row_value(source_row, "Source_Block_Index", default=source_block.index), default=source_block.index),
                source_block_label=str(_row_value(source_row, "Source_Block_Label", default=source_block.label) or source_block.label),
                source_block_csv_path=source_block_csv,
                source_block_csv_sha256=source_block_hash,
                trial_index=trial_index,
                family=family,
                trial_file_path=trial_path,
                trial_file_sha256=actual_hash,
                sample_rate=sample_rate,
                source_channels=int(data.shape[1]),
                trial_start_sample=trial_start_sample,
                trial_end_sample=trial_end_sample,
                duration_s=duration_s,
                looming_onset_s=looming_onset_s,
                tactile_onset_s=tactile_onset_s,
            )
            row["Trial_UID"] = f"{self.package.participant_id}_topup_B{block_index:02d}_T{trial_index:03d}_{role}"
            row["Block_Label"] = block_label
            row["Is_Topup"] = "true"
            row["Topup_Role"] = role
            row["Primary_Analysis_Included"] = "true" if role == "rescue" else "false"
            row["Source_Trial_UID"] = source_uid
            row["Original_Trial_UID"] = source_uid
            row["Topup_Source_Ledger_ID"] = "" if entry is None else getattr(entry, "ledger_id", "")
            row["Topup_Source_Block_Number"] = _row_value(source_row, "Block_Number", "block_number", default=getattr(entry, "block_number", ""))
            row["Topup_Source_Trial_Number"] = _row_value(source_row, "Trial_Number", "trial_number", default=getattr(entry, "trial_number", ""))
            row["Topup_Attempt_Number"] = 2 if role == "rescue" else 1
            row["Topup_Rescue_Analysis_Role"] = "primary_rescue" if role == "rescue" else "row_structure_filler"
            trial_rows.append(row)
            frame_cursor = trial_end_sample

        padded = []
        for data in clips:
            if data.shape[1] < target_channels:
                pad = np.zeros((data.shape[0], target_channels - data.shape[1]), dtype=data.dtype)
                data = np.concatenate([data, pad], axis=1)
            padded.append(data)
        block_audio = np.concatenate(padded, axis=0)
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(_soundfile_path(wav_path), block_audio, sample_rate, subtype="PCM_16")
        _write_csv_rows(csv_path, trial_rows)
        json_path.write_text(
            json.dumps(
                {
                    "schema": "pps-topup-block-manifest.v1",
                    "participant_id": self.package.participant_id,
                    "session_id": self.package.session_id,
                    "part_number": "" if part_number is None else part_label,
                    "phase_label": phase_label,
                    "block_index": block_index,
                    "display_block_index": display_index,
                    "play_order_index": display_index,
                    "display_block_count": display_count,
                    "block_label": block_label,
                    "row_order": row_order,
                    "missed_trial_count": len(misses),
                    "rescue_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "rescue"),
                    "filler_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "filler"),
                    "csv_path": str(csv_path),
                    "wav_path": str(wav_path),
                    "rows": _json_ready(trial_rows),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        block = RunBlock(
            index=block_index,
            label=block_label,
            manifest_path=csv_path,
            wav_path=wav_path,
            trial_count=len(trial_rows),
            duration_s=float(block_audio.shape[0] / sample_rate) if sample_rate else 0.0,
            metadata={
                "execution_mode": "topup_block_wavs",
                "is_topup_block": True,
                "display_block_index": display_index,
                "play_order_index": display_index,
                "display_block_count": display_count,
                "part_number": _as_int(_row_value(trial_rows[0], "Part_Number", default=1), default=1) if trial_rows else 1,
                "sample_rate_hz": sample_rate,
                "channels": target_channels,
                "rescue_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "rescue"),
                "filler_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "filler"),
                "topup_manifest_json": str(json_path),
                "topup_part_number": "" if part_number is None else part_label,
                "topup_phase_label": phase_label,
            },
        )
        self.package.blocks.append(block)
        _append_topup_block_to_session_manifest(self.package.manifest_path, block, ledger=self.topup_ledger)
        outputs = {"topup_block_manifest": csv_path, "topup_block_manifest_json": json_path}
        if multi_part and part_label:
            outputs[f"topup_block_manifest_part{part_label}"] = csv_path
            outputs[f"topup_block_manifest_json_part{part_label}"] = json_path
            outputs[f"topup_block_wav_part{part_label}"] = wav_path
        else:
            outputs["topup_block_wav"] = wav_path
        return block, outputs

    def _create_audio_engine(self) -> Any:
        from .runner import CLICK_SOUND, AudioEngine, find_output_device
        from .audio_routing import audio_runtime_preflight_message

        device_idx, _device_name, _is_preferred = find_output_device()
        if device_idx is None:
            raise RuntimeError("No usable audio output device was found.\n" + audio_runtime_preflight_message())
        engine = AudioEngine(device_idx)
        if CLICK_SOUND and not engine.load_click_sound(CLICK_SOUND):
            raise RuntimeError(
                "Audio output stream could not be opened for the tactile response-marker path. "
                "Check the selected ASIO device and restart the runner."
            )
        return engine

    def _write_outputs(self) -> None:
        self.events.flush_callback_events()
        topup_outputs: dict[str, Path] = {}
        if self.topup_ledger is not None:
            self.topup_ledger.finalize_open_trials()
            topup_outputs = self.topup_ledger.write_outputs()
            topup_outputs["topup_block_manifest_draft"] = write_topup_draft_manifest(self.package.session_dir, self.topup_ledger)
            topup_manifest_csv = self.package.session_dir / "topup_block_manifest.csv"
            topup_manifest_json = self.package.session_dir / "topup_block_manifest.json"
            if topup_manifest_csv.exists():
                topup_outputs["topup_block_manifest"] = topup_manifest_csv
            if topup_manifest_json.exists():
                topup_outputs["topup_block_manifest_json"] = topup_manifest_json
            for part_csv in sorted(self.package.session_dir.glob("topup_block_part*_manifest.csv")):
                match = re.search(r"part([^_]+)_manifest", part_csv.stem)
                key = f"topup_block_manifest_part{match.group(1)}" if match else part_csv.stem
                topup_outputs[key] = part_csv
            for part_json in sorted(self.package.session_dir.glob("topup_block_part*_manifest.json")):
                match = re.search(r"part([^_]+)_manifest", part_json.stem)
                key = f"topup_block_manifest_json_part{match.group(1)}" if match else part_json.stem
                topup_outputs[key] = part_json
            topup_block_dir = self.package.session_dir / "blocks"
            for topup_wav in sorted(topup_block_dir.glob("*topup_missed_trials.wav")):
                match = re.search(r"_part([^_]+)_topup", topup_wav.stem)
                if match:
                    topup_outputs[f"topup_block_wav_part{match.group(1)}"] = topup_wav
                elif "topup_block_wav" not in topup_outputs:
                    topup_outputs["topup_block_wav"] = topup_wav
                else:
                    topup_outputs[topup_wav.stem] = topup_wav
        events_csv = self.package.session_dir / "events.csv"
        events_xdf = self.package.session_dir / "events.xdf"
        lsl_markers_csv = self.package.session_dir / "lsl_markers.csv"
        lsl_markers_xdf = self.package.session_dir / "lsl_markers.xdf"
        trigger_dictionary_path = self.package.session_dir / "trigger_dictionary.json"
        if self.capture_options.write_events_csv:
            self.logger.write_csv(events_csv)
        if self.capture_options.write_internal_xdf:
            self.logger.write_xdf(
                events_xdf,
                metadata={
                    "participant_id": self.package.participant_id,
                    "session_id": self.package.session_id,
                    "session_manifest": str(self.package.manifest_path),
                    "session_metadata": str(self._session_metadata_path),
                    "lsl_status": dict(self.events.lsl_status.__dict__),
                    "capture_options": self.capture_options.as_dict(),
                },
            )
        if self.capture_options.write_lsl_marker_mirror:
            self.events.write_lsl_markers_csv(lsl_markers_csv)
            self.events.write_lsl_markers_xdf(lsl_markers_xdf)
        if self.capture_options.write_trigger_dictionary:
            self.events.write_trigger_dictionary(trigger_dictionary_path)
        analysis = analyze_session_events(self.logger.events)
        self._analysis_outputs = {}
        if self.capture_options.write_analysis_csvs:
            self._analysis_outputs = write_analysis_csvs(analysis, self.package.session_dir / "analysis", self.package.session_id)
            self._analysis_outputs["timing_qc"] = _write_timing_qc_csv(self.logger.events, self.package.session_dir / "analysis" / f"{self.package.session_id}_timing_qc.csv")
        self._analysis_outputs.update(topup_outputs)
        if self.capture_options.write_lsl_marker_mirror:
            self._analysis_outputs["lsl_markers"] = lsl_markers_csv
            self._analysis_outputs["lsl_markers_xdf"] = lsl_markers_xdf
        if self.capture_options.write_trigger_dictionary:
            self._analysis_outputs["trigger_dictionary"] = trigger_dictionary_path
        if _path_exists(self._session_metadata_path):
            self._analysis_outputs["session_metadata"] = self._session_metadata_path
        self._summary_text = format_analysis_summary(analysis)
        (self.package.session_dir / "analysis_summary.txt").write_text(self._summary_text + "\n", encoding="utf-8")

    def _play_block_with_schedule(
        self,
        engine: Any,
        block: RunBlock,
        *,
        progress_callback: Callable[[float], None],
        block_event_schedule: BlockEventSchedule | None,
    ) -> bool:
        try:
            return bool(
                engine.play_block(
                    str(block.wav_path),
                    progress_callback=progress_callback,
                    audio_event_callback=self.events.enqueue_callback_event,
                    block_event_schedule=block_event_schedule,
                )
            )
        except TypeError:
            return bool(
                engine.play_block(
                    str(block.wav_path),
                    progress_callback=progress_callback,
                    audio_event_callback=self.events.enqueue_callback_event,
                )
            )

    def _has_logged_event(self, event_type: str, block_number: int) -> bool:
        return any(
            event.event_type == event_type and _as_int(event.payload.get("block_number", event.payload.get("block_index")), default=-1) == block_number
            for event in self.logger.events
        )

    def _start_backup_recording(self, engine: Any, path: Path, block: RunBlock) -> bool:
        if not self.capture_options.start_backup_recording:
            self.events.log("recording_disabled", block_number=block.index, block_label=block.label)
            return False
        if not hasattr(engine, "start_recording"):
            self.events.log("recording_unavailable", block_number=block.index, block_label=block.label, reason="audio engine has no recording API")
            return False
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            started = bool(engine.start_recording(str(path)))
        except Exception as exc:
            self.events.log("recording_start_failed", block_number=block.index, block_label=block.label, path=str(path), message=str(exc))
            return False
        self.events.log(
            "recording_start",
            block_number=block.index,
            block_label=block.label,
            path=str(path),
            started=started,
            mode="digital_output_evidence_wav",
        )
        if started:
            self._recording_paths.append(path)
        return started

    def _stop_backup_recording(self, engine: Any, path: Path, block: RunBlock, *, interrupted: bool, started: bool) -> None:
        if not started or not hasattr(engine, "stop_recording"):
            return
        try:
            engine.stop_recording(str(path), interrupted=interrupted)
            self.events.log("recording_end", block_number=block.index, block_label=block.label, path=str(path), interrupted=interrupted)
        except Exception as exc:
            self.events.log("recording_stop_failed", block_number=block.index, block_label=block.label, path=str(path), message=str(exc))

    @staticmethod
    def _emit(callback: EventCallback | None, message: str) -> None:
        if callback:
            callback(message)


def _preferred_audio_route_available() -> bool:
    try:
        import sounddevice as sd

        for device in sd.query_devices():
            name = str(device.get("name", "")).lower()
            hostapi = sd.query_hostapis(int(device.get("hostapi", 0))).get("name", "").lower()
            if "komplete" in name and "asio" in hostapi and int(device.get("max_output_channels", 0)) >= 3:
                return True
    except Exception:
        return False
    return False


def _event_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {
        f"block_{key}": value
        for key, value in metadata.items()
        if isinstance(key, str) and key and isinstance(value, (str, int, float, bool))
    }


def _block_condition_key(block: RunBlock) -> tuple[int, str]:
    return (
        _as_int(block.metadata.get("phase_index"), default=_as_int(block.metadata.get("part_number"), default=1)),
        str(block.metadata.get("phase") or block.metadata.get("phase_label") or "").strip().lower(),
    )


def _block_part_number(block: RunBlock) -> int:
    return _as_int(block.metadata.get("part_number"), default=1)


def _block_part_key(block: RunBlock) -> str:
    return _part_suffix(_block_part_number(block))


def _part_suffix(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return _slug(text)


def _package_part_numbers(package: RunPackage) -> set[str]:
    return {_block_part_key(block) for block in package.blocks if not _truthy(block.metadata.get("is_topup_block"))}


def _run_playback_numbering(
    standard_blocks: list[RunBlock],
    *,
    include_topup_slots: bool,
) -> tuple[dict[int, int], dict[str, int], int]:
    """Return UI play-order numbers for standard blocks and part-end top-up slots."""
    display_by_block: dict[int, int] = {}
    topup_by_part: dict[str, int] = {}
    display_index = 0
    for index, block in enumerate(standard_blocks):
        display_index += 1
        display_by_block[block.index] = display_index
        next_block = standard_blocks[index + 1] if index + 1 < len(standard_blocks) else None
        if include_topup_slots and (next_block is None or _block_part_key(next_block) != _block_part_key(block)):
            display_index += 1
            topup_by_part[_block_part_key(block)] = display_index
    return display_by_block, topup_by_part, display_index


def _coerce_capture_options(
    value: SessionCaptureOptions | dict[str, Any] | None,
    *,
    enable_lsl: bool | None = None,
) -> SessionCaptureOptions:
    if value is None:
        options = SessionCaptureOptions()
    elif isinstance(value, SessionCaptureOptions):
        options = value
    elif isinstance(value, dict):
        allowed = SessionCaptureOptions().__dataclass_fields__.keys()
        options = SessionCaptureOptions(**{key: bool(value[key]) for key in allowed if key in value})
    else:
        raise TypeError(f"Unsupported capture options type: {type(value)!r}")
    if enable_lsl is not None:
        options = SessionCaptureOptions(**{**options.as_dict(), "enable_lsl": bool(enable_lsl)})
    if not (options.write_events_csv or options.write_internal_xdf or options.write_analysis_csvs or options.write_lsl_marker_mirror):
        raise ValueError("At least one durable runner output must be enabled.")
    return options


def _build_runner_session_metadata(
    package: RunPackage,
    *,
    runner_metadata: dict[str, Any] | None,
    capture_options: SessionCaptureOptions,
    topup_enabled: bool,
    run_started_at: str = "",
    lsl_status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = dict(runner_metadata or {})
    participant_code = str(raw.get("participant_code") or package.participant_id or "").strip()
    participant_name = str(raw.get("participant_name") or "").strip()
    include_name = _truthy(raw.get("include_name_in_lsl", False))
    pseudonym = str(raw.get("participant_pseudonym") or "").strip() or _participant_pseudonym(package.session_id, participant_code)
    lsl_identity = participant_name if include_name and participant_name else pseudonym
    participant = {
        "participant_id": package.participant_id,
        "participant_code": participant_code,
        "name": participant_name,
        "include_name_in_lsl": include_name,
        "participant_pseudonym": pseudonym,
        "lsl_identity": lsl_identity,
        "age_years": str(raw.get("age_years") or "").strip(),
        "handedness": _normal_choice(raw.get("handedness"), {"right", "left", "ambidextrous", "prefer_not_to_say"}),
        "gender": _normal_choice(raw.get("gender"), {"male", "female", "other", "prefer_not_to_say"}),
    }
    return {
        "schema": SESSION_METADATA_SCHEMA,
        "session_id": package.session_id,
        "created_at": package.created_at,
        "run_started_at": run_started_at,
        "participant": participant,
        "experiment": _experiment_metadata_from_package(package),
        "capture_policy": {
            **capture_options.as_dict(),
            "topup_missed_trials_by_part": bool(topup_enabled),
            "lsl_event_protocol_standard": True,
            "local_audio_evidence_wav_label": "Fail-safe local audio evidence WAV",
        },
        "lsl_status_at_start": dict(lsl_status or {}),
        "session_paths": _session_metadata_paths(package),
    }


def _redact_session_metadata_for_lsl(metadata: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(_json_ready(metadata)))
    participant = dict(redacted.get("participant") or {})
    include_name = _truthy(participant.get("include_name_in_lsl", False))
    if not include_name:
        participant["name"] = ""
        participant["name_redacted_for_lsl"] = True
        participant["lsl_identity"] = participant.get("participant_pseudonym", "")
    else:
        participant["name_redacted_for_lsl"] = False
    redacted["participant"] = participant
    return redacted


def _participant_pseudonym(session_id: str, participant_code: str) -> str:
    seed = f"{participant_code}|{session_id}".encode("utf-8", errors="ignore")
    return f"PPS-{hashlib.sha256(seed).hexdigest()[:10].upper()}"


def _normal_choice(value: Any, allowed: set[str]) -> str:
    text = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return text if text in allowed else ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _experiment_metadata_from_package(package: RunPackage) -> dict[str, Any]:
    design_data = _load_json_if_exists(package.design_path)
    run_setup_data = _load_json_if_exists(package.source_run_setup_manifest_path) if package.source_run_setup_manifest_path else {}
    project_data: dict[str, Any] = {}
    if package.source_run_setup_manifest_path:
        project_manifest = package.source_run_setup_manifest_path.parent.parent / "project_manifest.json"
        project_data = _load_json_if_exists(project_manifest)
    experiment_name = (
        str(run_setup_data.get("experiment_name") or "").strip()
        or str(project_data.get("project_label") or "").strip()
        or str(design_data.get("study_profile_id") or "").strip()
        or str(design_data.get("name") or "").strip()
    )
    experiment_number = str(run_setup_data.get("experiment_number") or run_setup_data.get("experiment_nr") or "").strip()
    return {
        "experiment_name": experiment_name,
        "experiment_number": experiment_number,
        "project_id": str(project_data.get("project_id") or "").strip(),
        "project_label": str(project_data.get("project_label") or "").strip(),
        "template_id": str(design_data.get("study_profile_id") or project_data.get("source_template_id") or "").strip(),
        "execution_mode": package.execution_mode,
        "experiment_structure": str(run_setup_data.get("experiment_structure") or "").strip(),
        "participant_count": run_setup_data.get("participant_count", ""),
        "parts_per_participant": run_setup_data.get("parts_per_participant", ""),
        "instruction_profile": _json_ready(package.instruction_profile),
        "design_snapshot": _json_ready(design_data),
        "run_setup_snapshot": _json_ready(run_setup_data),
    }


def _session_metadata_paths(package: RunPackage) -> dict[str, Any]:
    paths = {
        "session_manifest": package.manifest_path,
        "design": package.design_path,
        "protocol": package.protocol_path,
        "source_run_setup_manifest": package.source_run_setup_manifest_path,
        "render_manifest": package.render_manifest_path,
    }
    return {
        key: {
            "path": "" if path is None else str(path),
            "sha256": "" if path is None or not _path_exists(path) else _sha256_file(Path(path)),
        }
        for key, path in paths.items()
    }


def _load_json_if_exists(path: Path | None) -> dict[str, Any]:
    if path is None or not _path_exists(path):
        return {}
    try:
        return _load_json(Path(path))
    except Exception:
        return {}


def _block_event_schedules(package: RunPackage) -> dict[int, BlockEventSchedule]:
    schedules: dict[int, BlockEventSchedule] = {}
    for block in package.blocks:
        sample_rate = _as_int(block.metadata.get("sample_rate_hz"), default=0)
        if sample_rate <= 0:
            try:
                import soundfile as sf

                info = sf.info(_soundfile_path(block.wav_path))
                sample_rate = int(info.samplerate)
            except Exception:
                sample_rate = 0
        schedules[block.index] = BlockEventSchedule.from_block_manifest(
            block.manifest_path,
            block_index=block.index,
            block_label=block.label,
            block_wav_path=block.wav_path,
            participant_id=package.participant_id,
            session_id=package.session_id,
            part_number=block.metadata.get("part_number", ""),
            sample_rate=sample_rate,
            block_metadata=block.metadata,
        )
    return schedules


def _emit_block_schedule_progress(
    progress_callback: ProgressCallback | None,
    block: RunBlock,
    schedule: BlockEventSchedule | None,
    *,
    total_blocks: int,
    is_topup: bool,
    display_block_index: int | None = None,
    display_block_count: int | None = None,
) -> None:
    if progress_callback is None:
        return
    display_index = _as_int(display_block_index, default=block.index)
    display_count = _as_int(display_block_count, default=max(0, int(total_blocks or 0)))
    progress_callback(
        {
            "ui_event": "block_schedule",
            "part_number": _block_part_number(block),
            "phase": str(block.metadata.get("phase") or ""),
            "phase_label": str(block.metadata.get("phase_label") or block.metadata.get("phase") or ""),
            "block_index": block.index,
            "display_block_index": display_index,
            "play_order_index": display_index,
            "block_label": block.label,
            "block_count": display_count,
            "display_block_count": display_count,
            "standard_block_index": "" if is_topup else block.index,
            "standard_block_count": "",
            "duration_s": block.duration_s,
            "is_topup": bool(is_topup),
            "block_schedule_perf_counter": time.perf_counter(),
            "block_schedule_unix_time": time.time(),
            "tactile_events": _timeline_tactile_events(schedule),
            "trial_segments": _timeline_trial_segments(schedule),
        }
    )


def _timeline_relative_time(event: Any, payload: dict[str, Any]) -> float:
    relative_time = _as_float(payload.get("relative_time_s"), default=math.nan)
    if math.isfinite(relative_time):
        return relative_time
    sample_rate = _as_float(payload.get("sample_rate", payload.get("Sample_Rate_Hz")), default=0.0)
    return float(event.sample_index) / sample_rate if sample_rate > 0 else math.nan


def _timeline_payload_label(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            text = str(value).strip()
            if text:
                return text
    return ""


def _timeline_trial_type_label(payload: dict[str, Any]) -> str:
    family = str(payload.get("family") or payload.get("Family") or "").strip()
    trial_type = _timeline_payload_label(payload, "Trial_Type", "trial_type")
    topup_role = _timeline_payload_label(payload, "topup_role", "Topup_Role")
    if _truthy(payload.get("is_topup", payload.get("Is_Topup", False))):
        role = topup_role.replace("_", " ").strip().title()
        return f"Top-up {role}".strip() if role else "Top-up"
    key = (trial_type or family).strip().lower().replace("-", "_").replace(" ", "_")
    labels = {
        "audio_tactile": "Audio-tactile",
        "audiotactile": "Audio-tactile",
        "baseline": "Baseline",
        "catch": "Catch",
        "catch_trial": "Catch",
        "audio_only": "Catch",
    }
    return labels.get(key, trial_type or family or "Trial")


def _timeline_tactile_events(schedule: BlockEventSchedule | None) -> list[dict[str, Any]]:
    if schedule is None:
        return []
    tactile_events: list[dict[str, Any]] = []
    for event in getattr(schedule, "events", []):
        if event.event_type != "tactile_onset":
            continue
        payload = dict(event.payload)
        relative_time = _timeline_relative_time(event, payload)
        if not math.isfinite(relative_time) or relative_time < 0:
            continue
        family = str(payload.get("family") or payload.get("Family") or "").strip()
        trial_type_label = _timeline_trial_type_label(payload)
        row_label = _timeline_payload_label(
            payload,
            "Respiratory_Phase",
            "respiratory_phase",
            "row_label",
            "Row_Label",
            "Trial_Type_Label",
            "trial_type_label",
            "Trial_Strip_Label",
            "trial_strip_label",
            "Row",
        )
        tactile_events.append(
            {
                "trial_number": _as_int(payload.get("trial_number", payload.get("Trial_Number")), default=len(tactile_events) + 1),
                "trial_uid": str(payload.get("trial_uid") or payload.get("Trial_UID") or ""),
                "time_s": relative_time,
                "sample_index": int(event.sample_index),
                "soa_ms": str(payload.get("soa_ms") or payload.get("SOA_ms") or ""),
                "family": family,
                "row_label": row_label,
                "trial_label": trial_type_label,
                "clip_label": _timeline_payload_label(
                    payload,
                    "Fixed_Audio_Labels",
                    "fixed_audio_labels",
                    "Sequence_Labels",
                    "sequence_labels",
                    "Sequence_Source_Labels",
                    "sequence_source_labels",
                    "Sequence_Variant_Label",
                    "sequence_variant_label",
                    "Noise_Label",
                    "noise_label",
                    "Trial_Type",
                    "trial_type",
                ),
            }
        )
    return sorted(
        tactile_events,
        key=lambda item: (
            _as_float(item.get("time_s"), default=0.0),
            _as_int(item.get("trial_number"), default=0),
            str(item.get("trial_uid") or ""),
        ),
    )


def _timeline_trial_segments(schedule: BlockEventSchedule | None) -> list[dict[str, Any]]:
    if schedule is None:
        return []
    starts: dict[str, dict[str, Any]] = {}
    ends: dict[str, float] = {}
    fallback_order: list[str] = []
    for event in getattr(schedule, "events", []):
        if event.event_type not in {"trial_start", "trial_end"}:
            continue
        payload = dict(event.payload)
        trial_uid = str(payload.get("trial_uid") or payload.get("Trial_UID") or "").strip()
        if not trial_uid:
            trial_uid = f"trial_{_as_int(payload.get('trial_number', payload.get('Trial_Number')), default=len(fallback_order) + 1):03d}"
        relative_time = _timeline_relative_time(event, payload)
        if not math.isfinite(relative_time) or relative_time < 0:
            continue
        if event.event_type == "trial_start":
            if trial_uid not in fallback_order:
                fallback_order.append(trial_uid)
            starts[trial_uid] = {"payload": payload, "start_s": relative_time, "sample_index": int(event.sample_index)}
        else:
            ends[trial_uid] = relative_time
    segments: list[dict[str, Any]] = []
    sorted_uids = sorted(fallback_order, key=lambda uid: starts.get(uid, {}).get("start_s", 0.0))
    for index, trial_uid in enumerate(sorted_uids):
        start = starts.get(trial_uid)
        if not start:
            continue
        payload = dict(start["payload"])
        start_s = float(start["start_s"])
        end_s = ends.get(trial_uid)
        if end_s is None or end_s <= start_s:
            next_uid = sorted_uids[index + 1] if index + 1 < len(sorted_uids) else ""
            next_start = starts.get(next_uid, {}).get("start_s")
            end_s = float(next_start) if next_start not in (None, "") else start_s + 8.0
        trial_type = _timeline_trial_type_label(payload)
        respiratory_label = _timeline_payload_label(
            payload,
            "Respiratory_Phase",
            "respiratory_phase",
            "Trial_Type_Label",
            "trial_type_label",
            "Trial_Strip_Label",
            "trial_strip_label",
            "Row_Label",
            "row_label",
            "Row",
        )
        clip_label = _timeline_payload_label(
            payload,
            "Fixed_Audio_Labels",
            "fixed_audio_labels",
            "Sequence_Labels",
            "sequence_labels",
            "Sequence_Source_Labels",
            "sequence_source_labels",
            "Sequence_Variant_Label",
            "sequence_variant_label",
            "Noise_Label",
            "noise_label",
            "Noise_Type",
            "noise_type",
        )
        segments.append(
            {
                "trial_number": _as_int(payload.get("trial_number", payload.get("Trial_Number")), default=index + 1),
                "trial_uid": trial_uid,
                "start_s": start_s,
                "end_s": float(end_s),
                "start_sample_index": int(start.get("sample_index", 0)),
                "clip_label": respiratory_label or clip_label or "Trial",
                "trial_label": trial_type or "Trial",
                "soa_ms": str(payload.get("soa_ms") or payload.get("SOA_ms") or "").strip(),
                "family": str(payload.get("family") or payload.get("Family") or ""),
                "trial_type": trial_type,
            }
        )
    return segments


def _topup_source_index(
    package: RunPackage,
    *,
    part_number: int | str | None = None,
) -> tuple[
    dict[str, tuple[dict[str, Any], Path, RunBlock]],
    list[str],
    dict[str, list[tuple[dict[str, Any], Path, RunBlock]]],
]:
    by_uid: dict[str, tuple[dict[str, Any], Path, RunBlock]] = {}
    row_order: list[str] = []
    rows_by_label: dict[str, list[tuple[dict[str, Any], Path, RunBlock]]] = {}
    for block in package.blocks:
        if bool(block.metadata.get("is_topup_block")):
            continue
        if part_number is not None and _block_part_key(block) != _part_suffix(part_number):
            continue
        try:
            rows = _read_csv_rows(block.manifest_path)
        except Exception:
            rows = []
        for row in rows:
            uid = str(row.get("Trial_UID") or row.get("trial_uid") or "").strip()
            source = (dict(row), block.manifest_path.parent, block)
            if uid:
                by_uid[uid] = source
            if not _topup_row_has_tactile(row):
                continue
            label = _topup_row_label(row)
            if label and label not in row_order:
                row_order.append(label)
            rows_by_label.setdefault(label, []).append(source)
    return by_uid, row_order, rows_by_label


def _topup_row_has_tactile(row: dict[str, Any]) -> bool:
    family = str(_row_value(row, "Family", "family", default="")).strip().lower().replace("-", "_").replace(" ", "_")
    trial_type = str(_row_value(row, "Trial_Type", "trial_type", default="")).strip().lower()
    if family in {"audio_tactile", "baseline"}:
        return True
    if trial_type in {"audio-tactile", "baseline"}:
        return True
    return _row_value(row, "Tactile_Onset_Sample", "tactile_onset_sample", default="") not in (None, "")


def _topup_row_label(row: dict[str, Any]) -> str:
    return str(_row_value(row, "Row_Label", "row_label", "Row", "respiratory_phase", "Respiratory_Phase", default="")).strip()


def _topup_entry_source_row(entry: Any) -> dict[str, Any]:
    return {
        "Participant_ID": getattr(entry, "participant_id", ""),
        "Session_ID": getattr(entry, "session_id", ""),
        "Part_Number": getattr(entry, "part_number", ""),
        "Phase": getattr(entry, "phase", ""),
        "Phase_Label": getattr(entry, "phase_label", ""),
        "Block_Number": getattr(entry, "block_number", ""),
        "Block_Label": getattr(entry, "block_label", ""),
        "Trial_Number": getattr(entry, "trial_number", ""),
        "Trial_UID": getattr(entry, "trial_uid", ""),
        "Trial_Type": getattr(entry, "trial_type", ""),
        "Family": getattr(entry, "family", ""),
        "SOA_ms": getattr(entry, "soa_ms", ""),
        "Row": getattr(entry, "row_label", ""),
        "Row_Label": getattr(entry, "row_label", ""),
        "Respiratory_Phase": getattr(entry, "respiratory_phase", ""),
        "Noise_Type": getattr(entry, "noise_type", ""),
        "Sequence_Labels": getattr(entry, "sequence_labels", ""),
        "Trial_File_Path": getattr(entry, "trial_file_path", ""),
        "Source_SHA256": getattr(entry, "source_sha256", ""),
        "Source_Block_Index": getattr(entry, "source_block_index", ""),
        "Source_Block_Label": getattr(entry, "source_block_label", ""),
        "Source_Block_CSV_Path": getattr(entry, "manifest_path", ""),
        "Segment5_Block_Trial_Index": getattr(entry, "segment5_block_trial_index", ""),
    }


def _empty_topup_source_block() -> RunBlock:
    return RunBlock(index=0, label="", manifest_path=Path("."), wav_path=Path("."), trial_count=0, duration_s=0.0)


def _write_csv_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _append_topup_block_to_session_manifest(manifest_path: Path, block: RunBlock, *, ledger: TopUpLedger | None) -> None:
    manifest = _load_json(manifest_path)
    if not manifest:
        return
    blocks = list(manifest.get("blocks", []) or [])
    blocks = [item for item in blocks if int(item.get("index", -1)) != block.index]
    blocks.append(_json_ready(asdict(block)))
    manifest["blocks"] = blocks
    outputs = dict(manifest.get("outputs", {}) or {})
    outputs["topup_ledger_csv"] = str(ledger.csv_path) if ledger is not None else ""
    outputs["topup_ledger_json"] = str(ledger.json_path) if ledger is not None else ""
    outputs["topup_block_manifest_csv"] = str(block.manifest_path)
    outputs["topup_block_manifest_json"] = str(block.metadata.get("topup_manifest_json", ""))
    manifest["outputs"] = outputs
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _load_segment_run_setup(run_setup_manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, str]], Path]:
    manifest_path = Path(run_setup_manifest_path)
    manifest = _load_json(manifest_path)
    if manifest.get("schema") != SEGMENT_RUN_SETUP_SCHEMA:
        raise ValueError(f"Unsupported Segment 6 manifest: {manifest_path}")
    if not bool(manifest.get("prepared")):
        raise ValueError("Segment 6 run setup is not prepared.")
    csv_path = _resolve_relative_path(manifest.get("csv_path", ""), manifest_path.parent)
    if not _path_exists(csv_path):
        raise FileNotFoundError(f"Segment 6 block-order CSV is missing: {csv_path}")
    rows = _read_csv_rows(csv_path)
    if not rows:
        raise ValueError("Segment 6 block-order CSV contains no rows.")
    expected = _as_int(manifest.get("total_block_runs"), default=len(rows))
    if expected != len(rows):
        raise ValueError("Segment 6 block-order CSV row count does not match its manifest.")
    source_manifest = _resolve_relative_path(manifest.get("source_segment5_manifest", ""), manifest_path.parent)
    recorded_hash = str(manifest.get("source_segment5_manifest_sha256") or "").strip()
    if recorded_hash and _path_exists(source_manifest) and _sha256_file(source_manifest) != recorded_hash:
        raise ValueError("Segment 6 is stale because the accepted Segment 5 manifest changed.")
    return manifest, rows, csv_path


def _resolve_relative_path(value: Any, base_dir: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path(base_dir)
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return Path(base_dir) / path


def _normalize_instruction_profile(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"schema": "pps-run-instructions.v1", "slots": []}
    slots: list[dict[str, Any]] = []
    raw_slots = value.get("slots", [])
    if isinstance(raw_slots, dict):
        raw_slots = list(raw_slots.values())
    if not isinstance(raw_slots, list):
        raw_slots = []
    for item in raw_slots:
        if not isinstance(item, dict):
            continue
        slot = str(item.get("slot") or "").strip()
        if not slot:
            continue
        mode = str(item.get("continue_mode") or "click").strip().lower()
        if mode not in {"click", "delay", "button"}:
            mode = "click"
        try:
            delay_s = max(0.0, float(item.get("delay_s") or 0.0))
        except (TypeError, ValueError):
            delay_s = 0.0
        slots.append(
            {
                "slot": slot,
                "label": str(item.get("label") or slot.replace("_", " ").title()).strip(),
                "enabled": bool(item.get("enabled", False)),
                "required": False,
                "path": str(item.get("path") or "").strip(),
                "duration_s": float(item.get("duration_s") or 0.0),
                "sample_rate": int(item.get("sample_rate") or 0),
                "channels": int(item.get("channels") or 0),
                "sha256": str(item.get("sha256") or "").strip(),
                "continue_mode": mode,
                "delay_s": delay_s,
                "button_label": str(item.get("button_label") or "Continue").strip() or "Continue",
                "source": str(item.get("source") or "").strip(),
            }
        )
    return {
        "schema": str(value.get("schema") or "pps-run-instructions.v1"),
        "slots": slots,
    }


def _materialize_session_instruction_profile(value: Any, *, session_dir: Path, source_base_dir: Path) -> dict[str, Any]:
    profile = _normalize_instruction_profile(value)
    slots: list[dict[str, Any]] = []
    instruction_dir = Path(session_dir) / "instructions"
    for item in profile.get("slots", []):
        slot = dict(item)
        if not bool(slot.get("enabled")):
            slots.append(slot)
            continue
        path_text = str(slot.get("path") or "").strip()
        if not path_text:
            slot["path"] = ""
            slots.append(slot)
            continue
        source = _resolve_relative_path(path_text, source_base_dir)
        if path_text and not _path_exists(source):
            repo_relative = REPO_ROOT / path_text
            if _path_exists(repo_relative):
                source = repo_relative
        if not _path_exists(source) or Path(source).is_dir():
            slots.append(slot)
            continue
        instruction_dir.mkdir(parents=True, exist_ok=True)
        suffix = source.suffix or ".wav"
        target = instruction_dir / f"{_slug(str(slot.get('slot') or source.stem))}{suffix}"
        if _path_exists(target) and _sha256_file(target) != _sha256_file(source):
            target = instruction_dir / f"{_slug(str(slot.get('slot') or source.stem))}_{_sha256_file(source)[:8]}{suffix}"
        if not _path_exists(target):
            shutil.copy2(_filesystem_path(source), _filesystem_path(target))
        info = _wav_info(target, label=str(slot.get("label") or target.stem))
        slot.update(
            {
                "path": str(target),
                "duration_s": float(info.duration_s),
                "sample_rate": int(info.sample_rate),
                "channels": int(info.channels),
                "sha256": _sha256_file(target),
            }
        )
        slots.append(slot)
    return {"schema": profile.get("schema", "pps-run-instructions.v1"), "slots": slots}


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _participant_sort_key(value: str) -> tuple[int, str]:
    match = re.fullmatch(r"P(\d+)", str(value or "").strip(), flags=re.IGNORECASE)
    if match:
        return (int(match.group(1)), str(value))
    return (10**9, str(value))


def _segment_part_number(phase: str) -> int:
    return 2 if str(phase or "").strip().lower() == "post" else 1


def _segment_trial_type(family: str) -> str:
    return {
        "audio_tactile": "Audio-Tactile",
        "baseline": "Baseline",
        "catch": "Catch",
    }.get(str(family or "").strip().lower(), "Trial")


def _segment_family(row: dict[str, Any]) -> str:
    family = str(row.get("family") or row.get("Family") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if family in {"audio_tactile", "baseline", "catch"}:
        return family
    trial_type = str(row.get("Trial_Type") or "").strip().lower()
    if "baseline" in trial_type:
        return "baseline"
    if "catch" in trial_type:
        return "catch"
    return "audio_tactile"


def _row_value(row: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def _segment_looming_onset_s(row: dict[str, Any]) -> float:
    explicit = _row_value(row, "looming_segment_onset_s", "Looming_Onset_S", default="")
    if explicit != "":
        return max(0.0, _as_float(explicit, default=0.0))
    name = str(_row_value(row, "source_file_name", "Source_File_Name", "trial_file_path", "Trial_File_Path", default=""))
    cleaned = Path(name).stem.lower()
    if cleaned.startswith("baseline_"):
        cleaned = re.sub(r"^baseline_[a-z]+_", "", cleaned)
    if cleaned.startswith("catch_"):
        cleaned = cleaned[len("catch_"):]
    tokens = cleaned.split("_")
    total_ms = 0
    for token in tokens:
        if token.startswith(("soa", "tac", "total", "ch3")):
            break
        match = re.search(r"(\d{2,6})ms$", token)
        if match:
            total_ms += int(match.group(1))
            continue
        if "loom" in token or "frontal" in token or "pink" in token or "blue" in token or "white" in token or "brown" in token:
            break
    return round(total_ms / 1000.0, 6) if total_ms else 0.0


def _segment_tactile_onset_s(row: dict[str, Any], looming_onset_s: float) -> float:
    explicit = _row_value(row, "tactile_onset_s", "Tactile_Onset_S", default="")
    if explicit != "":
        return max(0.0, _as_float(explicit, default=looming_onset_s))
    family = _segment_family(row)
    if family == "catch":
        return 0.0
    soa_ms = _as_float(_row_value(row, "soa_ms", "SOA_ms", default=0), default=0.0)
    return round(max(0.0, looming_onset_s + soa_ms / 1000.0), 6)


def _write_segment_protocol_schedule(path: Path, rows: list[dict[str, str]], participant_id: str, source_csv_path: Path) -> None:
    fieldnames = [
        "participant_id",
        "phase",
        "phase_label",
        "phase_index",
        "participant_block_position",
        "source_block_index",
        "block_label",
        "block_csv_file",
        "block_csv_path",
        "trial_count",
        "duration_ms",
        "source_segment6_csv_path",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "participant_id": participant_id,
                    "phase": row.get("phase", ""),
                    "phase_label": row.get("phase_label", ""),
                    "phase_index": row.get("phase_index", ""),
                    "participant_block_position": row.get("participant_block_position", ""),
                    "source_block_index": row.get("source_block_index", ""),
                    "block_label": row.get("block_label", ""),
                    "block_csv_file": row.get("block_csv_file", ""),
                    "block_csv_path": row.get("block_csv_path", ""),
                    "trial_count": row.get("trial_count", ""),
                    "duration_ms": row.get("duration_ms", ""),
                    "source_segment6_csv_path": str(source_csv_path),
                }
            )


def _materialize_segment_block_wav(
    output_path: Path,
    source_rows: list[dict[str, str]],
    *,
    participant_id: str,
    session_id: str,
    part_number: int,
    phase: str,
    phase_label: str,
    output_block_index: int,
    participant_block_position: int,
    source_block_index: int,
    source_block_label: str,
    source_block_csv_path: Path,
) -> tuple[float, int, int, list[dict[str, Any]], list[RenderedWav]]:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Install numpy and soundfile to prepare participant block WAVs.") from exc

    clips: list[Any] = []
    sample_rate = 0
    target_channels = 3
    trial_rows: list[dict[str, Any]] = []
    wav_infos: list[RenderedWav] = []
    frame_cursor = 0
    source_block_hash = _sha256_file(source_block_csv_path)
    ordered_rows = sorted(source_rows, key=lambda row: _as_int(row.get("block_trial_index"), default=len(trial_rows) + 1))
    for trial_index, row in enumerate(ordered_rows, start=1):
        trial_path = _resolve_relative_path(_row_value(row, "trial_file_path", "Trial_File_Path", default=""), source_block_csv_path.parent)
        if not _path_exists(trial_path):
            raise FileNotFoundError(f"Segment 5 trial row references a missing WAV: {trial_path}")
        expected_hash = str(_row_value(row, "source_sha256", "Source_SHA256", default="")).strip()
        actual_hash = _sha256_file(trial_path)
        if expected_hash and expected_hash != actual_hash:
            raise ValueError(f"Trial WAV hash mismatch for {trial_path.name}. Re-bake upstream segments before running.")
        data, rate = sf.read(_soundfile_path(trial_path), dtype="float32", always_2d=True)
        if sample_rate and int(rate) != sample_rate:
            raise ValueError(f"Segment 5 block contains mixed sample rates: {source_block_csv_path.name}")
        sample_rate = int(rate)
        target_channels = max(target_channels, int(data.shape[1]))
        clips.append(data)
        wav_infos.append(_wav_info(trial_path, sha256=actual_hash, label=trial_path.stem))
        duration_frames = int(data.shape[0])
        trial_start_sample = frame_cursor
        trial_end_sample = frame_cursor + duration_frames
        duration_s = float(duration_frames / sample_rate) if sample_rate else 0.0
        looming_onset_s = _segment_looming_onset_s(row)
        tactile_onset_s = _segment_tactile_onset_s(row, looming_onset_s)
        family = _segment_family(row)
        trial_rows.append(
            _segment_session_trial_row(
                row,
                participant_id=participant_id,
                session_id=session_id,
                part_number=part_number,
                phase=phase,
                phase_label=phase_label,
                output_block_index=output_block_index,
                participant_block_position=participant_block_position,
                source_block_index=source_block_index,
                source_block_label=source_block_label,
                source_block_csv_path=source_block_csv_path,
                source_block_csv_sha256=source_block_hash,
                trial_index=trial_index,
                family=family,
                trial_file_path=trial_path,
                trial_file_sha256=actual_hash,
                sample_rate=sample_rate,
                source_channels=int(data.shape[1]),
                trial_start_sample=trial_start_sample,
                trial_end_sample=trial_end_sample,
                duration_s=duration_s,
                looming_onset_s=looming_onset_s,
                tactile_onset_s=tactile_onset_s,
            )
        )
        frame_cursor = trial_end_sample
    if not clips or not sample_rate:
        raise ValueError(f"Segment 5 block contains no usable audio rows: {source_block_csv_path}")

    padded = []
    for data in clips:
        if data.shape[1] < target_channels:
            pad = np.zeros((data.shape[0], target_channels - data.shape[1]), dtype=data.dtype)
            data = np.concatenate([data, pad], axis=1)
        padded.append(data)
    block = np.concatenate(padded, axis=0)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(_soundfile_path(output_path), block, sample_rate, subtype="PCM_16")
    return float(block.shape[0] / sample_rate), sample_rate, target_channels, trial_rows, wav_infos


def _segment_session_trial_row(
    source: dict[str, str],
    *,
    participant_id: str,
    session_id: str,
    part_number: int,
    phase: str,
    phase_label: str,
    output_block_index: int,
    participant_block_position: int,
    source_block_index: int,
    source_block_label: str,
    source_block_csv_path: Path,
    source_block_csv_sha256: str,
    trial_index: int,
    family: str,
    trial_file_path: Path,
    trial_file_sha256: str,
    sample_rate: int,
    source_channels: int,
    trial_start_sample: int,
    trial_end_sample: int,
    duration_s: float,
    looming_onset_s: float,
    tactile_onset_s: float,
) -> dict[str, Any]:
    trial_start_s = trial_start_sample / float(sample_rate)
    trial_end_s = trial_end_sample / float(sample_rate)
    response_window_onset_s = looming_onset_s if family in {"audio_tactile", "catch"} else tactile_onset_s
    soa_ms = _row_value(source, "soa_ms", "SOA_ms", default="")
    row_label = str(_row_value(source, "row_label", "Row_Label", "Row", default="")).strip()
    trial_uid = f"{participant_id}_{phase}_B{output_block_index:02d}_T{trial_index:03d}_{_row_value(source, 'trial_pool_index', default=trial_index)}"
    return {
        "Participant_ID": participant_id,
        "Session_ID": session_id,
        "Part_Number": part_number,
        "Phase": phase,
        "Phase_Label": phase_label,
        "Block_Number": output_block_index,
        "Block_Label": f"Block {output_block_index:02d}",
        "Participant_Block_Position": participant_block_position,
        "Source_Block_Index": source_block_index,
        "Source_Block_Label": source_block_label,
        "Source_Block_CSV_Path": str(source_block_csv_path),
        "Source_Block_CSV_SHA256": source_block_csv_sha256,
        "Trial_Number": trial_index,
        "Trial_UID": trial_uid,
        "Trial_Type": _segment_trial_type(family),
        "Family": family,
        "SOA_ms": soa_ms,
        "Row": row_label,
        "Row_Label": row_label,
        "Respiratory_Phase": row_label,
        "Noise_Type": _row_value(source, "noise_type", "Noise_Type", default=""),
        "Baseline_Mode": _row_value(source, "baseline_mode", "Baseline_Mode", default=""),
        "Sequence_Labels": _row_value(source, "sequence_labels", "Sequence_Labels", default=""),
        "Sequence_Variant_Key": _row_value(source, "sequence_variant_key", "Sequence_Variant_Key", default=""),
        "Source_File_Name": _row_value(source, "source_file_name", "Source_File_Name", default=trial_file_path.name),
        "Trial_File_Path": str(trial_file_path),
        "Source_SHA256": trial_file_sha256,
        "Duration_ms": int(round(duration_s * 1000.0)),
        "Trial_Duration_S": f"{duration_s:.9f}",
        "Sample_Rate_Hz": sample_rate,
        "Channels": source_channels,
        "Tactile_Channel": _row_value(source, "tactile_channel", "Tactile_Channel", default=""),
        "Trial_Start_S": f"{trial_start_s:.9f}",
        "Trial_Start_Sample": trial_start_sample,
        "Looming_Onset_S": f"{looming_onset_s:.9f}" if family in {"audio_tactile", "catch"} else "",
        "Looming_Onset_Sample": int(round((trial_start_s + looming_onset_s) * sample_rate)) if family in {"audio_tactile", "catch"} else "",
        "Tactile_Onset_S": f"{tactile_onset_s:.9f}" if family in {"audio_tactile", "baseline"} else "",
        "Tactile_Onset_Sample": int(round((trial_start_s + tactile_onset_s) * sample_rate)) if family in {"audio_tactile", "baseline"} else "",
        "Response_Window_Onset_S": f"{response_window_onset_s:.9f}",
        "Response_Window_Onset_Sample": int(round((trial_start_s + response_window_onset_s) * sample_rate)),
        "Trial_End_S": f"{trial_end_s:.9f}",
        "Trial_End_Sample": trial_end_sample,
        "Segment5_Block_Trial_Index": _row_value(source, "block_trial_index", default=trial_index),
        "Segment4_Trial_Pool_Index": _row_value(source, "trial_pool_index", default=""),
        "Configured_Repetitions": _row_value(source, "configured_repetitions", default=""),
        "Repetition_Index": _row_value(source, "repetition_index", default=""),
        "Fractional_Extra": _row_value(source, "fractional_extra", default=""),
    }


def _write_segment_block_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "Participant_ID",
        "Session_ID",
        "Part_Number",
        "Phase",
        "Phase_Label",
        "Block_Number",
        "Block_Label",
        "Participant_Block_Position",
        "Source_Block_Index",
        "Source_Block_Label",
        "Source_Block_CSV_Path",
        "Source_Block_CSV_SHA256",
        "Trial_Number",
        "Trial_UID",
        "Trial_Type",
        "Family",
        "SOA_ms",
        "Row",
        "Row_Label",
        "Respiratory_Phase",
        "Noise_Type",
        "Baseline_Mode",
        "Sequence_Labels",
        "Sequence_Variant_Key",
        "Source_File_Name",
        "Trial_File_Path",
        "Source_SHA256",
        "Duration_ms",
        "Trial_Duration_S",
        "Sample_Rate_Hz",
        "Channels",
        "Tactile_Channel",
        "Trial_Start_S",
        "Trial_Start_Sample",
        "Looming_Onset_S",
        "Looming_Onset_Sample",
        "Tactile_Onset_S",
        "Tactile_Onset_Sample",
        "Response_Window_Onset_S",
        "Response_Window_Onset_Sample",
        "Trial_End_S",
        "Trial_End_Sample",
        "Segment5_Block_Trial_Index",
        "Segment4_Trial_Pool_Index",
        "Configured_Repetitions",
        "Repetition_Index",
        "Fractional_Extra",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(_filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _participant_rows(design: StimulusDesign, participant_id: str) -> list[dict[str, Any]]:
    rows = experiment_schedule_rows(design)
    exact = [dict(row) for row in rows if str(row.get("participant_id", "")) == participant_id]
    if exact:
        return exact
    first_id = str(rows[0].get("participant_id", "")) if rows else ""
    fallback = [dict(row) for row in rows if str(row.get("participant_id", "")) == first_id]
    for row in fallback:
        row["participant_id"] = participant_id
        row["participant_index"] = ""
    return fallback


def _trial_sequence_variant_lookup(render_dir: Path) -> dict[tuple[int, str], str]:
    manifest_path = Path(render_dir) / TRIAL_SEQUENCE_VARIANT_DIR / TRIAL_SEQUENCE_VARIANT_MANIFEST
    if not _path_exists(manifest_path):
        manifest_path = Path(render_dir) / LEGACY_TRIAL_SEQUENCE_VARIANT_DIR / TRIAL_SEQUENCE_VARIANT_MANIFEST
    try:
        data = json.loads(_read_text_file(manifest_path, encoding="utf-8"))
    except Exception:
        return {}
    lookup: dict[tuple[int, str], str] = {}
    for item in data.get("variants", []):
        try:
            row_index = int(item.get("row_index") or 0)
        except (TypeError, ValueError):
            continue
        keys = {
            str(item.get("variant_key") or "").strip(),
            str(item.get("sequence_variant_key") or "").strip(),
        }
        path = str(item.get("file_path") or "").strip()
        if row_index and path:
            for key in keys:
                if key:
                    lookup[(row_index, key)] = path
    return lookup


def _attach_sequence_variant_paths(rows: list[dict[str, Any]], lookup: dict[tuple[int, str], str]) -> None:
    if not lookup:
        return
    for row in rows:
        if str(row.get("trial_type") or "") == "Baseline":
            continue
        key = (int(row.get("trial_strip_index") or 0), str(row.get("sequence_variant_key") or ""))
        path = lookup.get(key)
        if path:
            row["sequence_variant_path"] = path


def _trial_file_lookup(render_dir: Path) -> dict[tuple[str, int, str, int], str]:
    manifest_path = Path(render_dir) / BASELINE_TACTILE_TRIAL_DIR / BASELINE_TACTILE_TRIAL_MANIFEST
    if not _path_exists(manifest_path):
        manifest_path = Path(render_dir) / LEGACY_BASELINE_TACTILE_TRIAL_DIR / BASELINE_TACTILE_TRIAL_MANIFEST
    try:
        data = json.loads(_read_text_file(manifest_path, encoding="utf-8"))
    except Exception:
        return {}
    lookup: dict[tuple[str, int, str, int], str] = {}
    for item in data.get("files", []):
        try:
            row_index = int(item.get("row_index") or 0)
            soa_ms = int(item.get("soa_ms") or 0)
        except (TypeError, ValueError):
            continue
        family = str(item.get("family") or "").strip()
        variant_keys = {
            str(item.get("variant_key") or "").strip(),
            str(item.get("sequence_variant_key") or "").strip(),
        }
        path = str(item.get("file_path") or "").strip()
        if family and row_index and path:
            for variant_key in variant_keys:
                if variant_key:
                    lookup[(family, row_index, variant_key, soa_ms)] = path
    return lookup


def _attach_trial_file_paths(rows: list[dict[str, Any]], lookup: dict[tuple[str, int, str, int], str]) -> None:
    if not lookup:
        return
    for row in rows:
        trial_type = str(row.get("trial_type") or "")
        if trial_type == "Audio-Tactile":
            family = "audio_tactile"
        elif trial_type == "Baseline":
            family = "baseline"
        elif trial_type == "Catch":
            family = "catch"
        else:
            continue
        try:
            key = (
                family,
                int(row.get("trial_strip_index") or 0),
                str(row.get("sequence_variant_key") or ""),
                int(row.get("soa_ms") or 0),
            )
        except (TypeError, ValueError):
            continue
        path = lookup.get(key)
        if not path and family == "catch":
            path = lookup.get((family, key[1], key[2], 0))
        if path:
            row["trial_file_path"] = path


def _group_rows_by_block(rows: Iterable[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for row in rows:
        position = _as_int(row.get("participant_block_position"), default=_as_int(row.get("block_index"), default=1))
        label = str(row.get("block_label", f"Block {position}"))
        grouped.setdefault((position, label), []).append(row)
    return [(key[1], grouped[key]) for key in sorted(grouped)]


def _write_block_manifest(path: Path, rows: list[dict[str, Any]], participant_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "Participant_ID",
        "Part_Number",
        "Block_Number",
        "Block_Label",
        "Trial_Number",
        "Trial_Type",
        "SOA_ms",
        "Noise_Label",
        "Noise_Type",
        "Respiratory_Phase",
        "Tactile_Site",
        "Motion_Direction",
        "Spatial_Value_cm",
        "Azimuth_deg",
        "Elevation_deg",
        "Trial_Strip_ID",
        "Trial_Strip_Label",
        "Trial_Strip_Index",
        "Trial_Type_ID",
        "Trial_Type_Label",
        "Trial_Type_Index",
        "Row_Audio_Tactile_Percent",
        "Row_Catch_Percent",
        "Row_Baseline_Percent",
        "Tactile_Enabled",
        "Sequence_Labels",
        "Fixed_Audio_Labels",
        "Fixed_Audio_Paths",
        "Sequence_Source_Labels",
        "Sequence_Variant_Label",
        "Sequence_Variant_Key",
        "Sequence_Variant_Path",
        "Trial_File_Path",
        "Jitter_Labels",
        "Jitter_Values_Ms",
        "Jitter_Total_Ms",
        "Baseline_Strategy",
        "Baseline_Sample_Index",
        "Trial_Unit_Key",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for index, row in enumerate(rows, start=1):
            writer.writerow(
                {
                    "Participant_ID": participant_id,
                    "Part_Number": 1,
                    "Block_Number": row.get("participant_block_position", row.get("block_index", "")),
                    "Block_Label": row.get("block_label", ""),
                    "Trial_Number": index,
                    "Trial_Type": row.get("trial_type", ""),
                    "SOA_ms": row.get("soa_ms", ""),
                    "Noise_Label": row.get("noise_label", ""),
                    "Noise_Type": row.get("noise_type", ""),
                    "Respiratory_Phase": row.get("phase", ""),
                    "Tactile_Site": row.get("tactile_site", ""),
                    "Motion_Direction": row.get("motion_direction", ""),
                    "Spatial_Value_cm": row.get("spatial_value_cm", ""),
                    "Azimuth_deg": row.get("azimuth_deg", ""),
                    "Elevation_deg": row.get("elevation_deg", ""),
                    "Trial_Strip_ID": row.get("trial_strip_id", ""),
                    "Trial_Strip_Label": row.get("trial_strip_label", ""),
                    "Trial_Strip_Index": row.get("trial_strip_index", ""),
                    "Trial_Type_ID": row.get("trial_type_id", row.get("trial_strip_id", "")),
                    "Trial_Type_Label": row.get("trial_type_label", row.get("trial_strip_label", "")),
                    "Trial_Type_Index": row.get("trial_type_index", row.get("trial_strip_index", "")),
                    "Row_Audio_Tactile_Percent": row.get("row_audio_tactile_percent", ""),
                    "Row_Catch_Percent": row.get("row_catch_percent", ""),
                    "Row_Baseline_Percent": row.get("row_baseline_percent", ""),
                    "Tactile_Enabled": row.get("tactile_enabled", ""),
                    "Sequence_Labels": row.get("sequence_labels", ""),
                    "Fixed_Audio_Labels": row.get("fixed_audio_labels", ""),
                    "Fixed_Audio_Paths": row.get("fixed_audio_paths", ""),
                    "Sequence_Source_Labels": row.get("sequence_source_labels", ""),
                    "Sequence_Variant_Label": row.get("sequence_variant_label", ""),
                    "Sequence_Variant_Key": row.get("sequence_variant_key", ""),
                    "Sequence_Variant_Path": row.get("sequence_variant_path", ""),
                    "Trial_File_Path": row.get("trial_file_path", ""),
                    "Jitter_Labels": row.get("jitter_labels", ""),
                    "Jitter_Values_Ms": row.get("jitter_values_ms", ""),
                    "Jitter_Total_Ms": row.get("jitter_total_ms", ""),
                    "Baseline_Strategy": row.get("baseline_strategy", ""),
                    "Baseline_Sample_Index": row.get("baseline_sample_index", ""),
                    "Trial_Unit_Key": row.get("trial_unit_key", ""),
                }
            )


def _materialize_block_wav(path: Path, rows: list[dict[str, Any]], wav_by_label: dict[str, RenderedWav]) -> float:
    try:
        import numpy as np
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Install numpy and soundfile to prepare runnable session blocks.") from exc

    clips = []
    sample_rate = 0
    channels = 0
    default_wav = wav_by_label["__default__"]
    for row in rows:
        wav = _select_wav_for_row(row, wav_by_label, default_wav)
        data, sr = sf.read(_soundfile_path(wav.path), dtype="float32", always_2d=True)
        if sample_rate and sr != sample_rate:
            raise ValueError(f"Rendered WAV sample-rate mismatch: {wav.path}")
        sample_rate = int(sr)
        channels = max(channels, int(data.shape[1]))
        clips.append(data)
    if not clips:
        return 0.0
    padded = []
    for data in clips:
        if data.shape[1] < channels:
            pad = np.zeros((data.shape[0], channels - data.shape[1]), dtype=data.dtype)
            data = np.concatenate([data, pad], axis=1)
        padded.append(data)
    block = np.concatenate(padded, axis=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(_soundfile_path(path), block, sample_rate)
    return float(block.shape[0] / sample_rate) if sample_rate else 0.0


def _select_wav_for_row(row: dict[str, Any], wav_by_label: dict[str, RenderedWav], default_wav: RenderedWav) -> RenderedWav:
    trial_file_path = str(row.get("trial_file_path") or "").strip()
    if trial_file_path:
        path = _resolve_asset_path(trial_file_path)
        if _path_exists(path):
            return _wav_info(path, label=str(row.get("trial_unit_key") or path.stem))
    variant_path = str(row.get("sequence_variant_path") or "").strip()
    if variant_path:
        path = _resolve_asset_path(variant_path)
        if _path_exists(path):
            return _wav_info(path, label=str(row.get("sequence_variant_label") or path.stem))
    candidates = [
        str(row.get("noise_label", "")),
        str(row.get("noise_type", "")),
        _slug(str(row.get("noise_label", ""))),
        _slug(str(row.get("noise_type", ""))),
    ]
    for candidate in candidates:
        key = candidate.strip().lower()
        if key and key in wav_by_label:
            return wav_by_label[key]
    return default_wav


def _wav_lookup(wavs: list[RenderedWav]) -> dict[str, RenderedWav]:
    lookup: dict[str, RenderedWav] = {"__default__": wavs[0]}
    for wav in wavs:
        for key in {wav.label, wav.path.stem, wav.path.name, wav.path.stem.replace("looming_", "")}:
            if key:
                lookup.setdefault(key.strip().lower(), wav)
                lookup.setdefault(_slug(key).lower(), wav)
    return lookup


def _resolve_asset_path(value: str | Path) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _wav_info(path: Path, *, sha256: str = "", label: str = "") -> RenderedWav:
    try:
        import soundfile as sf

        info = sf.info(_soundfile_path(path))
        duration_s = float(info.frames / info.samplerate) if info.samplerate else 0.0
        sample_rate = int(info.samplerate)
        channels = int(info.channels)
    except Exception:
        duration_s = 0.0
        sample_rate = 0
        channels = 0
    wav_label = label.strip() or path.stem.replace("looming_", "").replace("_", " ")
    return RenderedWav(path=path, label=wav_label, duration_s=duration_s, sample_rate=sample_rate, channels=channels, sha256=sha256)


def _write_session_manifest(package: RunPackage, wavs: list[RenderedWav]) -> None:
    manifest = {
        "schema": RUN_PACKAGE_SCHEMA,
        "participant_id": package.participant_id,
        "session_id": package.session_id,
        "created_at": package.created_at,
        "execution_mode": package.execution_mode,
        "source_run_setup_manifest_path": str(package.source_run_setup_manifest_path) if package.source_run_setup_manifest_path else "",
        "audio_route": {
            "preferred_device": PREFERRED_AUDIO_ROUTE,
            "channels": 3,
            "latency_s": REQUESTED_LATENCY_S,
            "blocksize": REQUESTED_BLOCKSIZE,
        },
        "timing": {
            "primary_response_source": "mouse_click event log plus optional LSL marker stream",
            "stimulus_anchor": "audio_sample_zero emitted by audio callback",
            "backup_trace": "optional local digital output evidence WAV; physical loopback is validation-only",
            "response_marker": {
                "channel": "tactile output",
                "gain": RESPONSE_MARKER_GAIN,
                "purpose": "sub-threshold physical QC marker, not primary RT source",
            },
            "lsl_stream": {
                "name": "PPSMarkersV2",
                "type": "Markers",
                "required": True,
                "policy": "standard runner event/metadata protocol; live outlet is always attempted and local mirrors are always written",
            },
        },
        "design_path": str(package.design_path),
        "protocol_path": str(package.protocol_path),
        "render_manifest_path": str(package.render_manifest_path) if package.render_manifest_path else "",
        "instruction_profile": _json_ready(package.instruction_profile),
        "source_wavs": [_json_ready(asdict(wav)) for wav in wavs],
        "blocks": [_json_ready(asdict(block)) for block in package.blocks],
        "outputs": {
            "events_csv": str(package.session_dir / "events.csv"),
            "events_xdf": str(package.session_dir / "events.xdf"),
            "lsl_markers_csv": str(package.session_dir / "lsl_markers.csv"),
            "lsl_markers_xdf": str(package.session_dir / "lsl_markers.xdf"),
            "trigger_dictionary_json": str(package.session_dir / "trigger_dictionary.json"),
            "session_metadata_json": str(package.session_dir / "session_metadata.json"),
            "analysis_dir": str(package.session_dir / "analysis"),
        },
    }
    package.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_timing_qc_csv(events: Iterable[Any], path: Path) -> Path:
    rows = []
    mouse_by_id: dict[int, Any] = {}
    markers = []
    for event in events:
        if getattr(event, "event_type", "") == "mouse_click":
            mouse_by_id[int(event.event_id)] = event
        elif getattr(event, "event_type", "") == "response_marker_start":
            markers.append(event)

    for marker in markers:
        payload = dict(getattr(marker, "payload", {}) or {})
        mouse_event_id = _as_int(payload.get("mouse_event_id"), default=0)
        mouse = mouse_by_id.get(mouse_event_id)
        delta_ms = ""
        if mouse is not None:
            delta_ms = (float(marker.monotonic_time) - float(mouse.monotonic_time)) * 1000.0
        rows.append(
            {
                "mouse_event_id": mouse_event_id or "",
                "response_marker_event_id": marker.event_id,
                "mouse_unix_time": "" if mouse is None else f"{mouse.unix_time:.9f}",
                "response_marker_unix_time": f"{marker.unix_time:.9f}",
                "mouse_monotonic_time": "" if mouse is None else f"{mouse.monotonic_time:.9f}",
                "response_marker_monotonic_time": f"{marker.monotonic_time:.9f}",
                "marker_minus_mouse_ms": "" if delta_ms == "" else f"{delta_ms:.3f}",
                "delay_clock": "monotonic",
                "marker_channel": payload.get("marker_channel", ""),
                "marker_gain": payload.get("marker_gain", ""),
                "block_number": payload.get("block_number", ""),
                "block_label": payload.get("block_label", ""),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "mouse_event_id",
                "response_marker_event_id",
                "mouse_unix_time",
                "response_marker_unix_time",
                "mouse_monotonic_time",
                "response_marker_monotonic_time",
                "marker_minus_mouse_ms",
                "delay_clock",
                "marker_channel",
                "marker_gain",
                "block_number",
                "block_label",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(_read_text_file(path, encoding="utf-8"))
    except Exception:
        return {}


def _trial_duration_s(block: RunBlock) -> float:
    return max(0.001, block.duration_s / max(1, block.trial_count))


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return slug or "Block"


def _as_int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value
