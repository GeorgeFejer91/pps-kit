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

from .design import StimulusDesign, design_to_dict, experiment_schedule_rows, export_protocol_csv, validate_design
from .loudness import (
    loudness_manifest_payload,
    loudness_policy_for_design,
    loudness_protocol_warnings,
    normalize_loudness_policy,
)
from .output_layout import (
    output_data_max_participant_dir,
    output_data_analytics_dir,
    output_data_min_dir,
    output_data_min_master_csv,
    output_data_min_participant_csv,
    output_metadata_dir,
    output_prepared_blocks_dir,
    output_runner_logs_dir,
    output_shared_instructions_dir,
    output_verbose_events_dir,
)
from .analysis_catalog import refresh_analysis_browser_outputs
from .response_policy import TACTILE_RESPONSE_MAX_RT_S, TACTILE_RESPONSE_MIN_RT_S, TACTILE_RESPONSE_RULE_LABEL
from .session_analysis import analyze_session_events, format_analysis_summary, write_analysis_csvs
from .session_events import SessionEventLogger
from .runner_diary import append_diary_entry, ensure_output_diary, find_output_diary
from .labrecorder_capture import LabRecorderCapture, LabRecorderCaptureError, find_labrecorder_cli
from .tactile_threshold_adaptation import (
    AdaptiveTactileThresholdController,
    adaptive_threshold_initial_output_34_percent,
)
from .tactile_latency import tactile_drive_onset_s, woojer_tactile_latency_policy
from .timing_events import TimingEventHub, TriggerDictionary
from .timing_schedule import BlockEventSchedule
from .topup import HIT, MISSED_NEEDS_TOPUP, PENDING, TopUpLedger, write_topup_draft_manifest
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
SESSION_GROUP_MANIFEST_SCHEMA = "pps-run-session-group.v1"
PART_SPLIT_SCHEMA = "pps-runner-part-split.v1"
PART_COMPLETION_STATUS_SCHEMA = "pps-runner-part-completion.v1"
SEGMENT_RUN_SETUP_SCHEMA = "pps-experiment-run-setup.v1"
SEGMENT_BLOCK_PREVIEW_SCHEMA = "pps-block-csv-preview.v1"
LAST_EXPERIMENT_SCHEMA = "pps-last-experiment.v1"
PREPARED_SESSION_QUEUE_SCHEMA = "pps-prepared-session-queue.v1"
BLOCK_WAV_CACHE_SCHEMA = "pps-session-block-cache.v1"
BLOCK_WAV_CACHE_VERSION = "2026-06-29.source-file-content.v1"
RESPONSE_MARKER_GAIN = 0.05
EXTERNAL_LABRECORDER_FINAL_MARKER_SETTLE_S = 1.0
LAUNCHABLE_ACTIVITY_EVENTS = {"run_setup_prepared", "session_prepared", "runner_launched"}
PARTICIPANT_TRIAL_CSV_SUFFIX = "_trials.csv"
EXTERNAL_LABRECORDER_SCOPE_PART = "part"
EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP = "session_group_same_window"
PART1_TOPUP_REPEAT_BLOCK_INDEXES = (1, 2)
DATA_MIN_FIELDNAMES = [
    "participant_id",
    "session_id",
    "part_session_id",
    "part_number",
    "block_number",
    "block_label",
    "trial_number",
    "trial_number_global",
    "trial_uid",
    "condition",
    "phase",
    "noise_type",
    "trial_type",
    "soa_ms",
    "response_given",
    "hit_miss",
    "reaction_time_ms",
]


def _package_output_root(package: "RunPackage") -> Path:
    session_dir = Path(package.session_dir)
    if _package_is_split_part(package):
        return session_dir.parent.parent
    return session_dir.parent


def _package_context_leaf(package: "RunPackage") -> Path:
    if _package_is_split_part(package):
        return Path(package.session_group_id) / package.part_folder_name
    return Path(package.session_id)


def _package_runner_log_dir(package: "RunPackage") -> Path:
    return output_runner_logs_dir(_package_output_root(package)) / _package_context_leaf(package)


def _package_group_runner_log_dir(package: "RunPackage") -> Path:
    if _package_is_split_part(package):
        return output_runner_logs_dir(_package_output_root(package)) / package.session_group_id
    return _package_runner_log_dir(package)


def _package_prepared_blocks_dir(package: "RunPackage") -> Path:
    return output_prepared_blocks_dir(_package_output_root(package)) / _package_context_leaf(package) / "blocks"


def _package_verbose_events_dir(package: "RunPackage") -> Path:
    return output_verbose_events_dir(_package_output_root(package)) / _package_context_leaf(package)


def _package_analytics_dir(package: "RunPackage") -> Path:
    return output_data_analytics_dir(_package_output_root(package)) / _package_context_leaf(package)


def _participant_trials_csv_path(package: "RunPackage") -> Path:
    return Path(package.session_dir) / f"{package.session_id}{PARTICIPANT_TRIAL_CSV_SUFFIX}"


def _external_labrecorder_xdf_path(package: "RunPackage") -> Path:
    return Path(package.session_dir) / f"{package.session_id}_external_labrecorder.xdf"


def _external_labrecorder_group_xdf_path(package: "RunPackage") -> Path:
    if _package_is_split_part(package):
        return Path(package.session_dir).parent / f"{package.session_group_id}_external_labrecorder.xdf"
    return _external_labrecorder_xdf_path(package)


def _verbose_events_csv_path(package: "RunPackage") -> Path:
    return _package_verbose_events_dir(package) / "events.csv"


def _verbose_events_xdf_path(package: "RunPackage") -> Path:
    return _package_verbose_events_dir(package) / "events.xdf"


def _lsl_markers_csv_path(package: "RunPackage") -> Path:
    return _package_verbose_events_dir(package) / "lsl_markers.csv"


def _lsl_markers_xdf_path(package: "RunPackage") -> Path:
    return _package_verbose_events_dir(package) / "lsl_markers.xdf"


def _trigger_dictionary_path(package: "RunPackage") -> Path:
    return _package_verbose_events_dir(package) / "trigger_dictionary.json"


def _session_metadata_path(package: "RunPackage") -> Path:
    return _package_runner_log_dir(package) / "session_metadata.json"


def _loudness_manifest_path(package: "RunPackage") -> Path:
    return package.manifest_path.with_name("loudness_manifest.json")


def _package_is_split_part(package: "RunPackage") -> bool:
    return bool(
        str(getattr(package, "part_split_schema", "") or "").strip()
        and str(getattr(package, "session_group_id", "") or "").strip()
        and str(getattr(package, "part_folder_name", "") or "").strip()
    )


def _package_part_session_id(package: "RunPackage") -> str:
    return str(getattr(package, "part_session_id", "") or getattr(package, "session_id", ""))


def _package_part_number_value(package: "RunPackage") -> str:
    part_number = getattr(package, "part_number", None)
    if part_number in (None, ""):
        return ""
    return str(part_number)


def _package_part_identity(package: "RunPackage") -> dict[str, Any]:
    return {
        "session_group_id": str(package.session_group_id or ""),
        "part_session_id": _package_part_session_id(package) if _package_is_split_part(package) else "",
        "part_number": getattr(package, "part_number", None) if _package_is_split_part(package) else "",
    }


def _package_split_part_count(package: "RunPackage") -> int:
    if not _package_is_split_part(package):
        return 1
    return 1 + len([path for path in package.sibling_part_manifest_paths if str(path or "").strip()])


def _session_group_manifest_path(package: "RunPackage") -> Path:
    return output_runner_logs_dir(_package_output_root(package)) / package.session_group_id / "session_group_manifest.json"


def _part_completion_status_path(package: "RunPackage") -> Path:
    return _package_runner_log_dir(package) / "part_completion_status.json"


def _audio_evidence_path(package: "RunPackage", block: "RunBlock") -> Path:
    return Path(package.session_dir) / f"block_{int(block.index):02d}_audio_evidence.wav"


def _wired_loopback_path(package: "RunPackage", block: "RunBlock") -> Path:
    return Path(package.session_dir) / f"block_{int(block.index):02d}_wired_loopback_input4.wav"


def _data_max_context_leaf(package: "RunPackage") -> Path:
    if _package_is_split_part(package):
        return Path(package.session_group_id) / package.part_folder_name
    return Path(package.session_id)


def _data_max_session_leaf(package: "RunPackage") -> Path:
    return output_data_max_participant_dir(_package_output_root(package), package.participant_id) / "sessions" / _data_max_context_leaf(package)


def _data_max_group_session_dir(package: "RunPackage") -> Path:
    participant_root = output_data_max_participant_dir(_package_output_root(package), package.participant_id)
    if _package_is_split_part(package):
        return participant_root / "sessions" / package.session_group_id
    return participant_root / "sessions" / package.session_id


def _data_max_runner_logs_leaf(package: "RunPackage") -> Path:
    return output_data_max_participant_dir(_package_output_root(package), package.participant_id) / "runner_logs" / _data_max_context_leaf(package)


def _data_max_analysis_leaf(package: "RunPackage") -> Path:
    return output_data_max_participant_dir(_package_output_root(package), package.participant_id) / "analysis_outputs" / _data_max_context_leaf(package)


def _data_max_prepared_blocks_leaf(package: "RunPackage") -> Path:
    return output_data_max_participant_dir(_package_output_root(package), package.participant_id) / "prepared_blocks" / _data_max_context_leaf(package) / "blocks"


WIRED_LOOPBACK_OFF = "off"
WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY = "output4_tactile_proxy"
WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY = "output4-tactile-proxy"
WIRED_LOOPBACK_MODES = frozenset({WIRED_LOOPBACK_OFF, WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY})


def normalize_wired_loopback_mode(value: Any) -> str:
    text = str(value or WIRED_LOOPBACK_OFF).strip().lower().replace("-", "_")
    if text == WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY:
        return WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY
    return WIRED_LOOPBACK_OFF


def _normalize_external_labrecorder_scope(value: Any) -> str:
    text = str(value or EXTERNAL_LABRECORDER_SCOPE_PART).strip().lower().replace("-", "_")
    if text in {"session_group", "group", EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP}:
        return EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP
    return EXTERNAL_LABRECORDER_SCOPE_PART


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
    loudness_policy: dict[str, Any] = field(default_factory=dict)
    session_group_id: str = ""
    part_number: int | None = None
    part_session_id: str = ""
    part_folder_name: str = ""
    sibling_part_manifest_paths: list[Path] = field(default_factory=list)
    part_split_schema: str = ""


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
    topup_summary: dict[str, Any] = field(default_factory=dict)
    adaptive_tactile_threshold_summary: dict[str, Any] = field(default_factory=dict)
    operator_completion_message: str = ""


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
    wired_loopback_mode: str = WIRED_LOOPBACK_OFF
    start_external_labrecorder: bool = False
    external_labrecorder_scope: str = EXTERNAL_LABRECORDER_SCOPE_PART
    external_labrecorder_cli: str = ""
    external_labrecorder_stream_timeout_s: float = 10.0
    external_labrecorder_startup_s: float = 1.0
    external_labrecorder_stop_timeout_s: float = 8.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "enable_lsl": bool(self.enable_lsl),
            "write_events_csv": bool(self.write_events_csv),
            "write_internal_xdf": bool(self.write_internal_xdf),
            "write_analysis_csvs": bool(self.write_analysis_csvs),
            "write_lsl_marker_mirror": bool(self.write_lsl_marker_mirror),
            "write_trigger_dictionary": bool(self.write_trigger_dictionary),
            "start_backup_recording": bool(self.start_backup_recording),
            "wired_loopback_mode": normalize_wired_loopback_mode(self.wired_loopback_mode),
            "start_external_labrecorder": bool(self.start_external_labrecorder),
            "external_labrecorder_scope": _normalize_external_labrecorder_scope(self.external_labrecorder_scope),
            "external_labrecorder_cli": str(self.external_labrecorder_cli or ""),
            "external_labrecorder_stream_timeout_s": float(self.external_labrecorder_stream_timeout_s),
            "external_labrecorder_startup_s": float(self.external_labrecorder_startup_s),
            "external_labrecorder_stop_timeout_s": float(self.external_labrecorder_stop_timeout_s),
        }


PARTICIPANT_TRIAL_FIELDNAMES = [
    "recording_date",
    "recording_time",
    "recording_unix_time",
    "participant_id",
    "participant_age_years",
    "participant_gender",
    "participant_handedness",
    "session_id",
    "session_group_id",
    "part_session_id",
    "part_number",
    "condition",
    "block_number",
    "block_label",
    "trial_number",
    "trial_uid",
    "trial_type",
    "family",
    "respiratory_phase",
    "row_label",
    "stimulus_modality",
    "noise_type",
    "soa_ms",
    "tactile_present",
    "catch_trial",
    "audio_present",
    "stimulus_start_unix_time",
    "tactile_unix_time",
    "response_window_onset_unix_time",
    "response_unix_time",
    "rt_ms",
    "response_event_id",
    "response_given",
    "outcome",
    "correctness_rule",
    "is_topup",
    "topup_role",
    "source_trial_uid",
    "primary_analysis_included",
]


class ParticipantTrialCsvWriter:
    """Append one analysis-friendly row when each trial reaches its end marker."""

    def __init__(
        self,
        path: Path,
        *,
        package: RunPackage,
        participant_metadata: dict[str, Any] | None = None,
        min_rt_s: float = TACTILE_RESPONSE_MIN_RT_S,
        max_rt_s: float = TACTILE_RESPONSE_MAX_RT_S,
    ):
        self.path = Path(path)
        self.package = package
        self.participant_metadata = dict(participant_metadata or {})
        self.min_rt_s = max(0.0, float(min_rt_s))
        self.max_rt_s = max(self.min_rt_s, float(max_rt_s))
        self._trial_states: dict[tuple[str, str], dict[str, Any]] = {}
        self._clicks: list[dict[str, Any]] = []
        self._written_keys: set[tuple[str, str]] = set()
        self._used_click_ids: set[Any] = set()
        self._lock = threading.RLock()
        self._write_header()

    def observe_event(self, event: Any) -> None:
        row = _flat_event_row(event)
        event_type = str(row.get("event_type") or "")
        if not event_type:
            return
        with self._lock:
            if event_type == "mouse_click":
                self._clicks.append(row)
                return
            if event_type in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "stimulus_window_onset", "trial_end"}:
                key = self._trial_key(row)
                state = self._trial_states.setdefault(key, {"events": {}, "base": dict(row)})
                state["events"][event_type] = dict(row)
                state["base"].update({key: value for key, value in row.items() if value not in (None, "")})
                if event_type == "trial_end":
                    self._append_resolved_trial(key, state)

    def rewrite_from_events(self, events: Iterable[Any]) -> Path:
        with self._lock:
            self._trial_states = {}
            self._clicks = []
            self._written_keys = set()
            self._used_click_ids = set()
            self._write_header()
            for event in sorted(
                (_flat_event_row(item) for item in events),
                key=lambda row: (_as_float(row.get("unix_time"), default=0.0), _as_int(row.get("event_id"), default=0)),
            ):
                event_type = str(event.get("event_type") or "")
                if event_type == "mouse_click":
                    self._clicks.append(event)
                    continue
                if event_type in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "stimulus_window_onset", "trial_end"}:
                    key = self._trial_key(event)
                    state = self._trial_states.setdefault(key, {"events": {}, "base": dict(event)})
                    state["events"][event_type] = dict(event)
                    state["base"].update({name: value for name, value in event.items() if value not in (None, "")})
            states = sorted(
                self._trial_states.items(),
                key=lambda item: (
                    _as_float(item[1].get("events", {}).get("trial_start", {}).get("unix_time"), default=0.0),
                    _as_float(item[1].get("events", {}).get("trial_end", {}).get("unix_time"), default=0.0),
                    item[0],
                ),
            )
            for key, state in states:
                if "trial_end" in state.get("events", {}):
                    self._append_resolved_trial(key, state)
            return self.path

    def _write_header(self) -> None:
        _mkdir(self.path.parent)
        with open(_filesystem_path(self.path), "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PARTICIPANT_TRIAL_FIELDNAMES)
            writer.writeheader()

    def _trial_key(self, row: dict[str, Any]) -> tuple[str, str]:
        block = str(_row_value(row, "block_number", "block_index", "Block_Number", default="")).strip()
        trial_uid = str(_row_value(row, "trial_uid", "Trial_UID", default="")).strip()
        if not trial_uid:
            trial_uid = str(_row_value(row, "trial_number", "trial_index", "Trial_Number", default="")).strip()
        return (block, trial_uid)

    def _append_resolved_trial(self, key: tuple[str, str], state: dict[str, Any]) -> None:
        if key in self._written_keys:
            return
        row = self._resolved_trial_row(state)
        with open(_filesystem_path(self.path), "a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=PARTICIPANT_TRIAL_FIELDNAMES)
            writer.writerow(row)
        self._written_keys.add(key)
        response_event_id = row.get("response_event_id", "")
        if response_event_id not in (None, ""):
            self._used_click_ids.add(response_event_id)

    def _resolved_trial_row(self, state: dict[str, Any]) -> dict[str, Any]:
        events = dict(state.get("events", {}) or {})
        base = dict(state.get("base", {}) or {})
        trial_start = events.get("trial_start", {})
        looming_onset = events.get("looming_onset", {})
        tactile_onset = events.get("tactile_onset", {})
        response_onset = events.get("response_window_onset", {})
        trial_end = events.get("trial_end", base)
        trial_type = str(_row_value(base, "trial_type", "Trial_Type", default="")).strip()
        family = str(_row_value(base, "family", "Family", default="")).strip()
        modality = _trial_stimulus_modality(trial_type, family, bool(tactile_onset))
        tactile_present = _trial_has_tactile(trial_type, family, bool(tactile_onset))
        catch_trial = _trial_is_catch(trial_type, family)
        audio_present = _trial_has_audio(trial_type, family, bool(looming_onset))
        trial_start_unix = _as_float(trial_start.get("unix_time", base.get("unix_time")), default=0.0)
        stimulus_start_unix = _as_float(
            looming_onset.get("unix_time", tactile_onset.get("unix_time", response_onset.get("unix_time", trial_start_unix))),
            default=trial_start_unix,
        )
        tactile_unix = _as_float(tactile_onset.get("unix_time"), default=0.0)
        response_window_unix = _as_float(response_onset.get("unix_time"), default=stimulus_start_unix)
        trial_end_unix = _as_float(trial_end.get("unix_time"), default=response_window_unix)
        click, valid_response, response_given = self._select_response(
            block_number=str(_row_value(base, "block_number", "block_index", "Block_Number", default="")).strip(),
            trial_start_unix=trial_start_unix,
            response_window_unix=response_window_unix,
            tactile_unix=tactile_unix,
            trial_end_unix=trial_end_unix,
            tactile_present=tactile_present,
            catch_trial=catch_trial,
        )
        click_unix = _as_float(click.get("unix_time"), default=0.0) if click else 0.0
        rt_ms = ""
        if valid_response and tactile_present and tactile_unix > 0.0 and click_unix > 0.0:
            rt_ms = f"{(click_unix - tactile_unix) * 1000.0:.3f}"
        if tactile_present:
            outcome = "Hit" if valid_response else "Miss"
            correctness_rule = f"response within {TACTILE_RESPONSE_RULE_LABEL}"
        elif catch_trial:
            outcome = "Miss" if response_given else "Hit"
            correctness_rule = "withhold response during catch/audio-only trial"
        else:
            outcome = "Hit" if not response_given else "Miss"
            correctness_rule = "withhold response when no tactile target is present"
        recorded_at = datetime.fromtimestamp(_as_float(trial_end.get("unix_time"), default=time.time()))
        return {
            "recording_date": recorded_at.strftime("%Y-%m-%d"),
            "recording_time": recorded_at.strftime("%H:%M:%S.%f")[:-3],
            "recording_unix_time": f"{_as_float(trial_end.get('unix_time'), default=time.time()):.9f}",
            "participant_id": self.package.participant_id,
            "participant_age_years": self.participant_metadata.get("age_years", ""),
            "participant_gender": self.participant_metadata.get("gender", ""),
            "participant_handedness": self.participant_metadata.get("handedness", ""),
            "session_id": self.package.session_id,
            "session_group_id": str(getattr(self.package, "session_group_id", "") or ""),
            "part_session_id": _package_part_session_id(self.package) if _package_is_split_part(self.package) else "",
            "part_number": _row_value(base, "part_number", "Part_Number", default=""),
            "condition": _row_value(base, "condition", "Condition", default=""),
            "block_number": _row_value(base, "block_number", "block_index", "Block_Number", default=""),
            "block_label": _row_value(base, "block_label", "Block_Label", default=""),
            "trial_number": _row_value(base, "trial_number", "trial_index", "Trial_Number", default=""),
            "trial_uid": _row_value(base, "trial_uid", "Trial_UID", default=""),
            "trial_type": trial_type,
            "family": family,
            "respiratory_phase": _row_value(base, "respiratory_phase", "Respiratory_Phase", "row_label", "Row_Label", "Row", default=""),
            "row_label": _row_value(base, "row_label", "Row_Label", "Row", default=""),
            "stimulus_modality": modality,
            "noise_type": _row_value(base, "noise_type", "Noise_Type", "noise_label", "Noise_Label", default=""),
            "soa_ms": _row_value(base, "soa_ms", "SOA_ms", default=""),
            "tactile_present": str(tactile_present).lower(),
            "catch_trial": str(catch_trial).lower(),
            "audio_present": str(audio_present).lower(),
            "stimulus_start_unix_time": "" if stimulus_start_unix <= 0.0 else f"{stimulus_start_unix:.9f}",
            "tactile_unix_time": "" if tactile_unix <= 0.0 else f"{tactile_unix:.9f}",
            "response_window_onset_unix_time": "" if response_window_unix <= 0.0 else f"{response_window_unix:.9f}",
            "response_unix_time": "" if click_unix <= 0.0 else f"{click_unix:.9f}",
            "rt_ms": rt_ms,
            "response_event_id": "" if not click else click.get("event_id", ""),
            "response_given": str(response_given).lower(),
            "outcome": outcome,
            "correctness_rule": correctness_rule,
            "is_topup": str(_truthy(_row_value(base, "is_topup", "Is_Topup", "block_is_topup_block", default=False))).lower(),
            "topup_role": _row_value(base, "topup_role", "Topup_Role", default=""),
            "source_trial_uid": _row_value(base, "source_trial_uid", "Source_Trial_UID", "Original_Trial_UID", default=""),
            "primary_analysis_included": str(_truthy(_row_value(base, "primary_analysis_included", "Primary_Analysis_Included", default=True))).lower(),
        }

    def _select_response(
        self,
        *,
        block_number: str,
        trial_start_unix: float,
        response_window_unix: float,
        tactile_unix: float,
        trial_end_unix: float,
        tactile_present: bool,
        catch_trial: bool,
    ) -> tuple[dict[str, Any], bool, bool]:
        start = response_window_unix if response_window_unix > 0.0 else trial_start_unix
        end = trial_end_unix if trial_end_unix > start else start + self.max_rt_s
        if tactile_present and tactile_unix > 0.0:
            start = min(start, tactile_unix) if start > 0.0 else tactile_unix
            end = max(end, tactile_unix + self.max_rt_s)
        candidates = [
            click
            for click in self._clicks
            if click.get("event_id") not in self._used_click_ids
            and _truthy(click.get("in_target", True))
            and _truthy(click.get("during_playback", True))
            and str(_row_value(click, "block_number", "block_index", default="")).strip() == block_number
            and start <= _as_float(click.get("unix_time"), default=0.0) <= end
        ]
        candidates.sort(key=lambda item: (_as_float(item.get("unix_time"), default=0.0), _as_int(item.get("event_id"), default=0)))
        if not candidates:
            return {}, False, False
        if tactile_present:
            tactile_start = tactile_unix if tactile_unix > 0.0 else start
            valid_start = tactile_start + self.min_rt_s
            valid_end = tactile_start + self.max_rt_s
            for click in candidates:
                click_time = _as_float(click.get("unix_time"), default=0.0)
                if valid_start <= click_time <= valid_end:
                    return click, True, True
            return candidates[0], False, True
        if catch_trial:
            return candidates[0], False, True
        return candidates[0], False, True


def _normalize_data_min_phase(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if "inhale" in lowered:
        return "Inhale"
    if "exhale" in lowered:
        return "Exhale"
    return text


def _normalize_data_min_bool(value: Any) -> str:
    return "true" if _truthy(value) else "false"


def _normalize_data_min_outcome(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if "miss" in lowered:
        return "Miss"
    if "hit" in lowered:
        return "Hit"
    return text


def _is_data_min_filler_or_debug(row: dict[str, Any]) -> bool:
    role = str(_row_value(row, "topup_role", "Topup_Role", default="")).strip().lower()
    trial_type = str(_row_value(row, "trial_type", "Trial_Type", default="")).strip().lower()
    family = str(_row_value(row, "family", "Family", default="")).strip().lower()
    if role in {"filler", "debug"}:
        return True
    if trial_type in {"filler", "debug"} or family in {"filler", "debug"}:
        return True
    return False


def _data_min_row_from_rich(row: dict[str, Any], *, trial_number_global: int) -> dict[str, Any]:
    return {
        "participant_id": _row_value(row, "participant_id", "Participant_ID", default=""),
        "session_id": _row_value(row, "session_id", "Session_ID", default=""),
        "part_session_id": _row_value(row, "part_session_id", "Part_Session_ID", default=""),
        "part_number": _row_value(row, "part_number", "Part_Number", default=""),
        "block_number": _row_value(row, "block_number", "block_index", "Block_Number", default=""),
        "block_label": _row_value(row, "block_label", "Block_Label", default=""),
        "trial_number": _row_value(row, "trial_number", "trial_index", "Trial_Number", default=""),
        "trial_number_global": str(trial_number_global),
        "trial_uid": _row_value(row, "trial_uid", "Trial_UID", default=""),
        "condition": _row_value(row, "condition", "Condition", default=""),
        "phase": _normalize_data_min_phase(_row_value(row, "respiratory_phase", "phase", "Row_Label", default="")),
        "noise_type": _row_value(row, "noise_type", "Noise_Type", "noise_label", default=""),
        "trial_type": _row_value(row, "trial_type", "Trial_Type", default=""),
        "soa_ms": _row_value(row, "soa_ms", "SOA_ms", default=""),
        "response_given": _normalize_data_min_bool(_row_value(row, "response_given", "Response_Given", default=False)),
        "hit_miss": _normalize_data_min_outcome(_row_value(row, "outcome", "hit_miss", "Hit_Miss", default="")),
        "reaction_time_ms": _row_value(row, "rt_ms", "RT_ms", "reaction_time_ms", default=""),
    }


def _data_min_rows_from_participant_trials(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    global_index = 1
    for path in paths:
        for row in _read_csv_rows(path):
            if _is_data_min_filler_or_debug(row):
                continue
            rows.append(_data_min_row_from_rich(row, trial_number_global=global_index))
            global_index += 1
    return rows


def _write_data_min_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=DATA_MIN_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in DATA_MIN_FIELDNAMES})
    return path


def _data_min_csv_header(path: Path) -> list[str]:
    try:
        with open(_filesystem_path(path), newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            return next(reader, [])
    except Exception:
        return []


def _is_data_min_participant_csv(path: Path, output_root: Path) -> bool:
    master_name = output_data_min_master_csv(output_root).name
    return path.name != master_name and path.suffix.lower() == ".csv" and _data_min_csv_header(path) == DATA_MIN_FIELDNAMES


def _data_min_participant_csvs(output_root: Path) -> list[Path]:
    data_min = output_data_min_dir(output_root)
    return [path for path in sorted(data_min.glob("*.csv"), key=lambda item: item.name.lower()) if _is_data_min_participant_csv(path, output_root)]


def _prune_data_min_dir(output_root: Path) -> None:
    data_min = output_data_min_dir(output_root)
    if not _path_exists(data_min):
        return
    master_name = output_data_min_master_csv(output_root).name
    try:
        children = list(Path(data_min).iterdir())
    except Exception:
        return
    for child in children:
        if child.name == master_name:
            continue
        if child.is_file() and _is_data_min_participant_csv(child, output_root):
            continue
        try:
            if child.is_dir():
                shutil.rmtree(_filesystem_path(child))
            else:
                child.unlink()
        except Exception:
            continue


def _refresh_data_min_master_csv(output_root: Path) -> Path:
    participant_csvs = _data_min_participant_csvs(output_root)
    master = output_data_min_master_csv(output_root)
    _mkdir(master.parent)
    with open(_filesystem_path(master), "w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=DATA_MIN_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for participant_csv in participant_csvs:
            for row in _read_csv_rows(participant_csv):
                writer.writerow({field: row.get(field, "") for field in DATA_MIN_FIELDNAMES})
    return master


def _package_group_completed(package: "RunPackage") -> bool:
    if not _package_is_split_part(package):
        return True
    manifest = _load_json(_session_group_manifest_path(package))
    parts = [part for part in manifest.get("parts", []) if isinstance(part, dict)] if isinstance(manifest, dict) else []
    if not parts:
        return False
    return all(bool(part.get("completed")) for part in parts)


def _participant_trial_paths_for_completed_package(package: "RunPackage") -> list[Path]:
    if not _package_is_split_part(package):
        return [_participant_trials_csv_path(package)] if _path_is_file(_participant_trials_csv_path(package)) else []
    if not _package_group_completed(package):
        return []
    manifest = _load_json(_session_group_manifest_path(package))
    paths: list[Path] = []
    for part in sorted(manifest.get("parts", []), key=lambda item: _as_int(item.get("part_number"), default=0)):
        try:
            part_package = load_run_package(Path(str(part.get("session_manifest_path") or "")))
        except Exception:
            continue
        trials = _participant_trials_csv_path(part_package)
        if _path_is_file(trials):
            paths.append(trials)
    return paths


def write_data_min_publication_outputs(package: "RunPackage") -> dict[str, Path]:
    paths = _participant_trial_paths_for_completed_package(package)
    if not paths:
        return {}
    output_root = _package_output_root(package)
    participant_csv = output_data_min_participant_csv(output_root, package.participant_id)
    rows = _data_min_rows_from_participant_trials(paths)
    _write_data_min_csv(participant_csv, rows)
    _prune_data_min_dir(output_root)
    master_csv = _refresh_data_min_master_csv(output_root)
    return {
        "data_min_participant_csv": participant_csv,
        "data_min_master_successful_participants_csv": master_csv,
    }


def _copy_existing_path(source: Path, destination: Path) -> Path | None:
    if not source or not _path_exists(source):
        return None
    try:
        if _path_is_file(source):
            _mkdir(destination.parent)
            shutil.copy2(_filesystem_path(source), _filesystem_path(destination))
            return destination
        _mkdir(destination)
        shutil.copytree(_filesystem_path(source), _filesystem_path(destination), dirs_exist_ok=True)
        return destination
    except Exception:
        return None


def _copy_directory_contents(source: Path, destination: Path) -> None:
    if not source or not _path_exists(source):
        return
    _mkdir(destination)
    try:
        for child in sorted(Path(source).iterdir(), key=lambda item: item.name):
            _copy_existing_path(child, destination / child.name)
    except Exception:
        return


def mirror_data_max_outputs(package: "RunPackage", *, analysis_outputs: dict[str, Path] | None = None) -> dict[str, Path]:
    participant_root = output_data_max_participant_dir(_package_output_root(package), package.participant_id)
    participant_label = participant_root.name
    demographics_dir = participant_root / f"{participant_label}_demographics"
    calibration_dir = participant_root / f"{participant_label}_tactile-calibration"
    session_leaf = _data_max_session_leaf(package)
    runner_logs_leaf = _data_max_runner_logs_leaf(package)
    analysis_leaf = _data_max_analysis_leaf(package)
    prepared_leaf = _data_max_prepared_blocks_leaf(package)
    outputs: dict[str, Path] = {"data_max_participant_dir": participant_root, "data_max_session_dir": session_leaf}

    for directory in (
        demographics_dir,
        calibration_dir,
        participant_root / "sessions",
        participant_root / "prepared_blocks",
        participant_root / "analysis_outputs",
        participant_root / "runner_logs",
    ):
        _mkdir(directory)

    _copy_directory_contents(Path(package.session_dir), session_leaf)
    session_sources = [
        package.manifest_path,
        package.design_path,
        package.protocol_path,
        _loudness_manifest_path(package),
        _session_metadata_path(package),
        _verbose_events_csv_path(package),
        _verbose_events_xdf_path(package),
        _lsl_markers_csv_path(package),
        _lsl_markers_xdf_path(package),
        _trigger_dictionary_path(package),
    ]
    if _package_is_split_part(package):
        session_sources.append(_part_completion_status_path(package))
    for source in session_sources:
        copied = _copy_existing_path(Path(source), session_leaf / Path(source).name) if source else None
        if copied is not None:
            outputs[f"data_max_{Path(source).stem}"] = copied

    if _package_is_split_part(package):
        group_manifest = _session_group_manifest_path(package)
        copied = _copy_existing_path(group_manifest, _data_max_group_session_dir(package) / group_manifest.name)
        if copied is not None:
            outputs["data_max_session_group_manifest"] = copied

    _copy_directory_contents(_package_runner_log_dir(package), runner_logs_leaf)
    _copy_directory_contents(_package_analytics_dir(package), analysis_leaf)
    _copy_directory_contents(_package_prepared_blocks_dir(package), prepared_leaf)
    if analysis_outputs:
        for key, source in analysis_outputs.items():
            source_path = Path(source)
            if not _path_exists(source_path):
                continue
            if source_path.parent == _package_analytics_dir(package):
                copied = _copy_existing_path(source_path, analysis_leaf / source_path.name)
            else:
                copied = _copy_existing_path(source_path, session_leaf / source_path.name)
            if copied is not None:
                outputs[f"data_max_{key}"] = copied

    output_root = _package_output_root(package)
    raw_participant_id = str(package.participant_id or "").strip()
    calibration_sources = [
        output_root / raw_participant_id / f"{raw_participant_id}_tactile-calibration",
        output_root / participant_label / f"{participant_label}_tactile-calibration",
    ]
    seen_calibration_sources: set[Path] = set()
    for source in calibration_sources:
        source = Path(source)
        if source in seen_calibration_sources:
            continue
        seen_calibration_sources.add(source)
        if _path_exists(source):
            _copy_directory_contents(source, calibration_dir)
            outputs["data_max_tactile_calibration_dir"] = calibration_dir
            break

    metadata = _load_json(_session_metadata_path(package))
    participant_metadata = metadata.get("participant", {}) if isinstance(metadata, dict) else {}
    if isinstance(participant_metadata, dict) and participant_metadata:
        payload = {
            "schema": "pps-private-participant-demographics.v1",
            "participant_id": package.participant_id,
            "session_id": package.session_id,
            "session_group_id": package.session_group_id,
            "part_session_id": package.part_session_id,
            "part_number": package.part_number,
            "participant": participant_metadata,
        }
        _write_json_file(demographics_dir / "participant_metadata.private.json", payload)
        _write_json_file(demographics_dir / "setup_submission.private.json", payload)
        outputs["data_max_demographics_dir"] = demographics_dir
    return outputs


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


def _path_is_file(path: str | Path) -> bool:
    try:
        return os.path.isfile(_filesystem_path(path))
    except OSError:
        return False


def _mkdir(path: str | Path) -> None:
    os.makedirs(_filesystem_path(path), exist_ok=True)


def _read_text_file(path: str | Path, *, encoding: str = "utf-8") -> str:
    with open(_filesystem_path(path), "r", encoding=encoding) as handle:
        return handle.read()


def _write_text_file(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    target = Path(path)
    _mkdir(target.parent)
    with open(_filesystem_path(target), "w", encoding=encoding) as handle:
        handle.write(text)


def _write_json_file(path: str | Path, payload: Any) -> None:
    _write_text_file(path, json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n")


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
    loudness_warnings = loudness_protocol_warnings(loudness_policy_for_design(design))
    messages.extend(f"Loudness: {warning}" for warning in loudness_warnings)

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
    session_root = Path(session_root)
    session_dir = session_root / session_id
    run_package_dir = output_runner_logs_dir(session_root) / session_id
    block_dir = output_prepared_blocks_dir(session_root) / session_id / "blocks"
    _mkdir(block_dir)
    _mkdir(run_package_dir)
    _mkdir(session_dir)

    design_path = run_package_dir / "design.json"
    protocol_path = run_package_dir / "protocol_schedule.csv"
    rows = _participant_rows(design, clean_participant)
    variant_lookup = _trial_sequence_variant_lookup(render_dir)
    _attach_sequence_variant_paths(rows, variant_lookup)
    trial_file_lookup = _trial_file_lookup(render_dir)
    _attach_trial_file_paths(rows, trial_file_lookup)
    if not rows:
        raise ValueError("The current design produced no participant schedule rows.")

    _write_json_file(design_path, design_to_dict(design))
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

    manifest_path = run_package_dir / "session_manifest.json"
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
        loudness_policy=normalize_loudness_policy(
            design.study_profile_reference_parameters.get("loudness_policy")
            if isinstance(design.study_profile_reference_parameters, dict)
            else None
        ),
    )
    _write_session_manifest(package, wavs)
    _append_package_diary_event(
        package,
        "session_package_prepared",
        payload={
            "execution_mode": package.execution_mode,
            "block_count": len(package.blocks),
            "session_dir": str(package.session_dir),
        },
    )
    return package


def load_run_package(manifest_path: Path) -> RunPackage:
    """Rehydrate a prepared run package from its session manifest."""
    manifest_path = Path(manifest_path)
    data = _load_json(manifest_path)
    if data.get("schema") != RUN_PACKAGE_SCHEMA:
        raise ValueError(f"Unsupported run package manifest: {manifest_path}")
    session_dir = Path(str(data.get("session_dir") or manifest_path.parent))
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
        loudness_policy=normalize_loudness_policy(data.get("loudness_policy")),
        session_group_id=str(data.get("session_group_id") or ""),
        part_number=_as_int(data.get("part_number"), default=0) or None,
        part_session_id=str(data.get("part_session_id") or data.get("session_id") or ""),
        part_folder_name=str(data.get("part_folder_name") or ""),
        sibling_part_manifest_paths=[Path(str(item)) for item in data.get("sibling_part_manifest_paths", []) if str(item or "").strip()],
        part_split_schema=str(data.get("part_split_schema") or ""),
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
    _mkdir(root)
    created_at = datetime.now().isoformat(timespec="seconds")
    event = {
        "schema": LAST_EXPERIMENT_SCHEMA,
        "event_type": str(event_type or "activity"),
        "created_at": created_at,
        **_json_ready(payload),
    }
    log_path = root / "experiment_activity_log.jsonl"
    with open(_filesystem_path(log_path), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    _append_activity_diary_event(event)

    pointer_path = root / "last_experiment.v1.json"
    if event["event_type"] not in LAUNCHABLE_ACTIVITY_EVENTS:
        return pointer_path
    pointer = _load_json(pointer_path) if _path_exists(pointer_path) else {}
    pointer.update({key: value for key, value in event.items() if value not in (None, "")})
    pointer["schema"] = LAST_EXPERIMENT_SCHEMA
    pointer["updated_at"] = created_at
    pointer["last_event_type"] = event["event_type"]
    _write_text_file(pointer_path, json.dumps(pointer, indent=2), encoding="utf-8")
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
    queue_data["schema"] = PREPARED_SESSION_QUEUE_SCHEMA
    queue_data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_text_file(path, json.dumps(_json_ready(queue_data), indent=2, sort_keys=True), encoding="utf-8")
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
    session_root: Path | None = None,
) -> Path | None:
    queue_data = _load_prepared_session_queue(state_root)
    run_setup = Path(run_setup_manifest_path).resolve()
    participant = sanitize_participant_id(participant_id)
    run_setup_hash = _run_setup_queue_hash(run_setup)
    session_root_path = Path(session_root).resolve() if session_root is not None else None
    changed = False
    for entry in queue_data.get("entries", []):
        if str(entry.get("status") or "") not in {"ready", "claimed"}:
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
        if session_root_path is not None and not _path_is_within(manifest_path, session_root_path):
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
        current, message = prepared_session_manifest_current_status(
            manifest_path,
            run_setup_manifest_path=run_setup,
            participant_id=participant,
        )
        if not current:
            entry["status"] = "stale"
            entry["message"] = message
            entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
            changed = True
            continue
        selected_manifest_path = _next_runnable_manifest_for_package(package)
        if selected_manifest_path != manifest_path:
            valid, message = _prepared_session_manifest_ready_for_run_setup(
                selected_manifest_path,
                run_setup,
                participant,
            )
            if not valid:
                entry["status"] = "invalid"
                entry["message"] = message
                entry["updated_at"] = datetime.now().isoformat(timespec="seconds")
                changed = True
                continue
        entry["status"] = "claimed"
        entry["claimed_manifest_path"] = str(selected_manifest_path.resolve())
        entry["claimed_at"] = datetime.now().isoformat(timespec="seconds")
        entry["updated_at"] = entry["claimed_at"]
        _write_prepared_session_queue(state_root, queue_data)
        return selected_manifest_path.resolve()
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
    session_root_path = Path(session_root).resolve()
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
            if manifest_path and not _path_is_within(manifest_path, session_root_path):
                fallback_message = "Prepared queue entry belongs to a different output folder."
                continue
            valid, message = _prepared_session_manifest_ready_for_run_setup(manifest_path, run_setup, participant)
            if valid and not _path_is_within(manifest_path, Path(session_root)):
                valid = False
                message = "Prepared session belongs to a different output folder."
            if valid:
                selected_manifest_path = manifest_path
                try:
                    selected_manifest_path = _next_runnable_manifest_for_package(load_run_package(manifest_path))
                except Exception:
                    selected_manifest_path = manifest_path
                return {
                    "participant_id": participant,
                    "generated": True,
                    "status": "ready" if status == "ready" else "generated",
                    "session_manifest_path": str(selected_manifest_path.resolve()),
                    "message": message,
                    "source": "prepared_session_queue",
                    **data_status,
                }
            fallback_message = message

    scanned, scanned_message = _scan_prepared_session_manifest(run_setup, participant, session_root=session_root)
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
    if scanned_message:
        fallback_message = fallback_message or scanned_message

    return {
        "participant_id": participant,
        "generated": False,
        "status": "not_generated",
        "session_manifest_path": "",
        "message": fallback_message or "No prepared local audio package found.",
        "source": "",
        **data_status,
    }


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


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
    return prepared_session_manifest_current_status(
        manifest_path,
        run_setup_manifest_path=run_setup_manifest_path,
        participant_id=participant_id,
    )


def prepared_session_manifest_current_status(
    manifest_path: Path,
    *,
    run_setup_manifest_path: Path | None = None,
    participant_id: str | None = None,
) -> tuple[bool, str]:
    if not manifest_path or not _path_exists(manifest_path):
        return False, "Prepared session manifest is missing."
    try:
        package = load_run_package(manifest_path)
    except Exception as exc:
        return False, str(exc)
    if participant_id is not None and package.participant_id != participant_id:
        return False, "Prepared session participant does not match."
    source_path = package.source_run_setup_manifest_path
    requested_run_setup = Path(run_setup_manifest_path) if run_setup_manifest_path is not None else source_path
    if run_setup_manifest_path is not None:
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
    return _prepared_session_sources_current(package, requested_run_setup)


def _prepared_session_sources_current(package: RunPackage, run_setup_manifest_path: Path | None) -> tuple[bool, str]:
    if package.execution_mode != "participant_block_wavs":
        return True, "Prepared local audio package is available."
    if run_setup_manifest_path is None or not _path_exists(run_setup_manifest_path):
        return False, "Prepared session source run setup is missing."

    manifest = _load_json(package.manifest_path)
    recorded_run_hash = str(manifest.get("source_run_setup_sha256") or "").strip()
    current_run_hash = _sha256_file(run_setup_manifest_path)
    if not recorded_run_hash:
        return False, "Prepared session was created before source-hash tracking; regenerate audio assets."
    if recorded_run_hash != current_run_hash:
        return False, "Prepared session is stale because the Segment 6 run setup changed."

    for block in package.blocks:
        metadata = dict(block.metadata or {})
        if bool(metadata.get("is_topup_block")):
            continue
        source_text = str(metadata.get("source_block_csv_path") or "").strip()
        recorded_source_hash = str(metadata.get("source_block_csv_sha256") or "").strip()
        if not source_text or not recorded_source_hash:
            return False, f"Prepared block {block.index} lacks source CSV provenance; regenerate audio assets."
        source_csv = _resolve_relative_path(source_text, Path(run_setup_manifest_path).parent)
        if not _path_exists(source_csv):
            return False, f"Prepared block source CSV is missing: {source_csv}"
        if _sha256_file(source_csv) != recorded_source_hash:
            return False, f"Prepared block {block.index} is stale because the source CSV changed: {source_csv}"
        try:
            source_rows = _read_csv_rows(source_csv)
        except Exception as exc:
            return False, f"Prepared block source CSV cannot be read: {exc}"
        if len(source_rows) != int(block.trial_count):
            return False, (
                f"Prepared block {block.index} trial count is stale: "
                f"{block.trial_count} prepared vs {len(source_rows)} source rows."
            )
        prepared_csv = _session_package_path(package, block.manifest_path)
        try:
            prepared_rows = _read_csv_rows(prepared_csv)
        except Exception as exc:
            return False, f"Prepared block manifest cannot be read: {exc}"
        if len(prepared_rows) != int(block.trial_count):
            return False, (
                f"Prepared block {block.index} manifest row count is stale: "
                f"{block.trial_count} expected vs {len(prepared_rows)} prepared rows."
            )
        ordered_source_rows = sorted(source_rows, key=lambda row: _as_int(row.get("block_trial_index"), default=0))
        for source_row, prepared_row in zip(ordered_source_rows, prepared_rows):
            trial_path = _resolve_relative_path(
                _row_value(source_row, "Trial_File_Path", "trial_file_path", default=""),
                source_csv.parent,
            )
            if not _path_exists(trial_path):
                return False, f"Prepared block {block.index} source trial WAV is missing: {trial_path}"
            current_hash = _sha256_file(trial_path)
            declared_hash = str(_row_value(source_row, "Source_SHA256", "source_sha256", default="")).strip()
            prepared_hash = str(_row_value(prepared_row, "Source_SHA256", "source_sha256", default="")).strip()
            if declared_hash and declared_hash != current_hash:
                return False, f"Prepared block {block.index} is stale because a source trial WAV changed: {trial_path}"
            if prepared_hash and prepared_hash != current_hash:
                return False, f"Prepared block {block.index} is stale because a source trial WAV changed: {trial_path}"
    return True, "Prepared local audio package is available."


def _iter_prepared_session_manifest_candidates(
    run_setup_manifest_path: Path,
    participant_id: str,
    *,
    session_root: Path = DEFAULT_SESSION_ROOT,
) -> list[Path]:
    root = Path(session_root)
    if not _path_exists(root):
        return []
    participant = sanitize_participant_id(participant_id)
    patterns = [
        output_runner_logs_dir(root).glob(f"{participant}_*/session_manifest.json"),
        output_runner_logs_dir(root).glob(f"{participant}_*/part_*/session_manifest.json"),
        root.glob(f"{participant}_*/session_manifest.json"),
        root.glob(f"{participant}_*/part_*/session_manifest.json"),
    ]
    candidates: set[Path] = set()
    for pattern in patterns:
        candidates.update(path.resolve() for path in pattern if _path_exists(path))
    return sorted(
        candidates,
        key=lambda path: path.stat().st_mtime if _path_exists(path) else 0.0,
        reverse=True,
    )


def _scan_prepared_session_manifest(
    run_setup_manifest_path: Path,
    participant_id: str,
    *,
    session_root: Path = DEFAULT_SESSION_ROOT,
) -> tuple[tuple[Path, str] | None, str]:
    candidates = _iter_prepared_session_manifest_candidates(
        run_setup_manifest_path,
        participant_id,
        session_root=session_root,
    )
    last_message = ""
    for manifest_path in candidates:
        valid, message = _prepared_session_manifest_ready_for_run_setup(manifest_path, run_setup_manifest_path, participant_id)
        if valid:
            try:
                package = load_run_package(manifest_path)
                selected = _next_runnable_manifest_for_package(package)
                return (selected, message), ""
            except Exception:
                return (manifest_path, message), ""
        if message:
            last_message = message
    return None, last_message


def _split_group_packages(package: RunPackage) -> list[RunPackage]:
    if not _package_is_split_part(package):
        return [package]
    packages: dict[Path, RunPackage] = {package.manifest_path.resolve(): package}
    for manifest_path in package.sibling_part_manifest_paths:
        if not manifest_path or not _path_exists(manifest_path):
            continue
        try:
            sibling = load_run_package(manifest_path)
        except Exception:
            continue
        if sibling.participant_id != package.participant_id:
            continue
        if sibling.session_group_id and package.session_group_id and sibling.session_group_id != package.session_group_id:
            continue
        packages[sibling.manifest_path.resolve()] = sibling
    return sorted(packages.values(), key=lambda item: int(item.part_number or 0))


def _next_runnable_package_for_group(packages: list[RunPackage]) -> RunPackage | None:
    ordered = sorted(packages, key=lambda item: int(item.part_number or 0))
    if not ordered:
        return None
    for package in ordered:
        completed, _message = _session_package_has_completed_data(package)
        if not completed:
            return package
    return ordered[-1]


def _next_runnable_manifest_for_package(package: RunPackage) -> Path:
    if not _package_is_split_part(package):
        return package.manifest_path
    selected = _next_runnable_package_for_group(_split_group_packages(package))
    return selected.manifest_path if selected is not None else package.manifest_path


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        target = Path(path).resolve()
        base = Path(root).resolve()
    except Exception:
        return False
    return target == base or base in target.parents


def _split_part_status_label(part_number: int, *, completed: bool, message: str) -> str:
    if completed:
        suffix = "complete" if int(part_number or 0) == 1 else "collected"
    elif str(message or "").strip():
        suffix = "incomplete"
    else:
        suffix = "ready"
    return f"Part {int(part_number or 0) or '?'} {suffix}"


def _split_group_data_collection_status(packages: list[RunPackage], base: dict[str, Any]) -> dict[str, Any]:
    ordered = sorted(packages, key=lambda item: int(item.part_number or 0))
    if not ordered:
        return base
    part_statuses: list[dict[str, Any]] = []
    first_unfinished: RunPackage | None = None
    first_unfinished_message = ""
    for package in ordered:
        completed, message = _session_package_has_completed_data(package)
        part_number = int(package.part_number or 0)
        if first_unfinished is None and not completed:
            first_unfinished = package
            first_unfinished_message = message
        part_statuses.append(
            {
                "part_number": part_number,
                "part_session_id": package.part_session_id,
                "part_folder_name": package.part_folder_name,
                "session_manifest_path": str(package.manifest_path.resolve()),
                "session_dir": str(package.session_dir.resolve()),
                "completed": bool(completed),
                "status": "complete" if completed else ("incomplete" if message else "ready"),
                "message": message,
                "label": _split_part_status_label(part_number, completed=completed, message=message),
            }
        )
    inventory = ", ".join(str(item.get("label") or "") for item in part_statuses if item.get("label"))
    all_completed = all(bool(item.get("completed")) for item in part_statuses)
    selected = ordered[-1] if all_completed else (first_unfinished or ordered[0])
    selected_part = int(selected.part_number or 0)
    payload = {
        **base,
        "data_session_manifest_path": str(selected.manifest_path.resolve()),
        "data_session_dir": str(selected.session_dir.resolve()),
        "session_group_id": selected.session_group_id,
        "session_group_manifest_path": str(_session_group_manifest_path(selected)),
        "next_part_number": selected_part if not all_completed else "",
        "next_part_manifest_path": "" if all_completed else str(selected.manifest_path.resolve()),
        "next_part_session_dir": "" if all_completed else str(selected.session_dir.resolve()),
        "part_statuses": part_statuses,
        "part_inventory": inventory,
        "data_collection_message": inventory or base["data_collection_message"],
    }
    if all_completed:
        payload.update(
            {
                "data_collected": True,
                "data_collection_status": "collected",
                "data_collection_message": inventory or "Completed participant data found.",
            }
        )
    elif first_unfinished_message:
        payload.update(
            {
                "data_collection_status": "incomplete",
                "data_collection_message": inventory or first_unfinished_message,
            }
        )
    elif selected_part <= 1:
        payload.update(
            {
                "data_collection_status": "not_collected",
                "data_collection_message": inventory or "No completed participant data found.",
            }
        )
    else:
        payload.update(
            {
                "data_collection_status": f"part_{selected_part}_ready",
                "data_collection_message": inventory or f"Part {selected_part} is ready.",
            }
        )
    return payload


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
        "session_group_id": "",
        "session_group_manifest_path": "",
        "next_part_number": "",
        "next_part_manifest_path": "",
        "next_part_session_dir": "",
        "part_statuses": [],
        "part_inventory": "",
    }
    participant = sanitize_participant_id(participant_id)
    if not participant:
        base["data_collection_message"] = "Participant ID is required."
        return base
    candidates = _iter_prepared_session_manifest_candidates(
        run_setup_manifest_path,
        participant,
        session_root=session_root,
    )
    seen_split_groups: set[str] = set()
    for manifest_path in candidates:
        package = _load_matching_session_package(manifest_path, run_setup_manifest_path, participant)
        if package is None:
            continue
        if _package_is_split_part(package):
            group_key = package.session_group_id or str(package.session_dir.parent.resolve())
            if group_key in seen_split_groups:
                continue
            seen_split_groups.add(group_key)
            group_packages = [
                item
                for item in _split_group_packages(package)
                if _load_matching_session_package(item.manifest_path, run_setup_manifest_path, participant) is not None
            ]
            return _split_group_data_collection_status(group_packages, base)
        collected, message = _session_package_has_completed_data(package)
        if collected:
            return {
                **base,
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
    if _package_is_split_part(package):
        status = _load_json_if_exists(_part_completion_status_path(package))
        if status.get("schema") == PART_COMPLETION_STATUS_SCHEMA:
            completed = _truthy(status.get("completed"))
            interrupted = _truthy(status.get("interrupted"))
            if completed and not interrupted:
                return True, "Completed participant data found."
            return False, "Participant data exists, but the part did not complete."
    events_csv = _verbose_events_csv_path(package)
    if not _path_exists(events_csv):
        legacy_events_csv = Path(package.session_dir) / "events.csv"
        events_csv = legacy_events_csv if _path_exists(legacy_events_csv) else events_csv
    if not _path_exists(events_csv):
        return False, ""
    try:
        with open(_filesystem_path(events_csv), newline="", encoding="utf-8-sig") as handle:
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
        declared_hash = str(_row_value(row, "source_sha256", "Source_SHA256", default="")).strip()
        actual_hash = _sha256_file(trial_path) if _path_exists(trial_path) else ""
        row_payload.append(
            {
                "trial_file_path": str(trial_path.resolve()) if trial_path else "",
                "source_sha256": actual_hash,
                "declared_source_sha256": declared_hash,
                "block_trial_index": str(_row_value(row, "block_trial_index", "Block_Trial_Index", default="")),
                "family": str(_row_value(row, "family", "Family", default="")),
                "soa_ms": str(_row_value(row, "soa_ms", "SOA_ms", default="")),
            }
        )
    payload = {
        "schema": BLOCK_WAV_CACHE_SCHEMA,
        "version": BLOCK_WAV_CACHE_VERSION,
        "tactile_latency_compensation": woojer_tactile_latency_policy(),
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
    _mkdir(target.parent)
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
                "tactile_drive_onset_s": row.get("Tactile_Drive_Onset_S", ""),
                "tactile_latency_compensation_requested_ms": row.get("Tactile_Latency_Compensation_Requested_ms", ""),
                "tactile_latency_compensation_applied_ms": row.get("Tactile_Latency_Compensation_Applied_ms", ""),
                "tactile_latency_compensation_status": row.get("Tactile_Latency_Compensation_Status", ""),
                "tactile_latency_compensation_applied": row.get("Tactile_Latency_Compensation_Applied", ""),
                "tactile_latency_compensation_note": row.get("Tactile_Latency_Compensation_Note", ""),
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
    _mkdir(manifest_path.parent)
    payload = {
        "schema": BLOCK_WAV_CACHE_SCHEMA,
        "version": BLOCK_WAV_CACHE_VERSION,
        "cache_key": cache_key,
        "tactile_latency_compensation": woojer_tactile_latency_policy(),
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
    _write_json_file(manifest_path, payload)


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
    ordered_rows = sorted(source_rows, key=lambda row: _as_int(row.get("block_trial_index"), default=0))
    for row, cached in zip(ordered_rows, trials):
        if not isinstance(cached, dict):
            return None
        trial_path = _resolve_relative_path(_row_value(row, "trial_file_path", "Trial_File_Path", default=""), source_csv.parent)
        if not _path_exists(trial_path):
            return None
        current_hash = _sha256_file(trial_path)
        declared_hash = str(_row_value(row, "source_sha256", "Source_SHA256", default="")).strip()
        cached_hash = str(cached.get("source_sha256") or "").strip()
        if declared_hash and declared_hash != current_hash:
            return None
        if cached_hash != current_hash:
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
        tactile_compensation = {
            "requested_compensation_ms": _as_float(cached.get("tactile_latency_compensation_requested_ms"), default=0.0),
            "applied_compensation_ms": _as_float(cached.get("tactile_latency_compensation_applied_ms"), default=0.0),
            "drive_onset_s": _as_float(cached.get("tactile_drive_onset_s"), default=tactile_onset_s),
            "status": str(cached.get("tactile_latency_compensation_status") or ""),
            "applied": _truthy(cached.get("tactile_latency_compensation_applied")),
            "note": str(cached.get("tactile_latency_compensation_note") or ""),
        }
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
                tactile_drive_onset_s=float(tactile_compensation.get("drive_onset_s") or tactile_onset_s),
                tactile_compensation=tactile_compensation,
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
    split_parts: bool | None = None,
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
    if split_parts is None:
        split_parts = _as_int(run_setup.get("parts_per_participant"), default=1) > 1
    if split_parts:
        packages = _prepare_split_segment_run_packages(
            run_setup_manifest_path,
            run_setup,
            order_csv_path,
            participant_rows,
            clean_participant,
            design=design,
            session_root=session_root,
            created_at=created_at,
            progress_callback=progress_callback,
            block_cache_root=block_cache_root,
            use_block_cache=use_block_cache,
        )
        return _select_next_runnable_part_package(packages)
    created_at = created_at or datetime.now()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    session_id = f"{clean_participant}_{timestamp}"
    session_root = Path(session_root)
    session_dir = session_root / session_id
    run_package_dir = output_runner_logs_dir(session_root) / session_id
    block_dir = output_prepared_blocks_dir(session_root) / session_id / "blocks"
    _mkdir(block_dir)
    _mkdir(run_package_dir)
    _mkdir(session_dir)
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
    loudness_policy = normalize_loudness_policy(run_setup.get("loudness_policy"))

    design_path = run_package_dir / "design.json"
    if design is None:
        _write_text_file(design_path, "{}\n")
    else:
        _write_json_file(design_path, design_to_dict(design))

    protocol_path = run_package_dir / "protocol_schedule.csv"
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
                _mkdir(cache_wav_path.parent)
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

    manifest_path = run_package_dir / "session_manifest.json"
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
        loudness_policy=loudness_policy,
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
    _append_package_diary_event(
        package,
        "session_package_prepared",
        payload={
            "execution_mode": package.execution_mode,
            "block_count": len(package.blocks),
            "session_dir": str(package.session_dir),
            "source_run_setup_manifest_path": str(run_setup_manifest_path),
        },
    )
    _emit_prepare_progress(
        progress_callback,
        "Opening Focus Mode",
        phase="opening_focus_mode",
        current=total_blocks,
        total=total_blocks,
        detail=str(manifest_path),
    )
    return package


def _prepare_split_segment_run_packages(
    run_setup_manifest_path: Path,
    run_setup: dict[str, Any],
    order_csv_path: Path,
    participant_rows: list[dict[str, str]],
    clean_participant: str,
    *,
    design: StimulusDesign | None,
    session_root: Path,
    created_at: datetime | None,
    progress_callback: Callable[[dict[str, Any]], None] | None,
    block_cache_root: Path,
    use_block_cache: bool,
) -> list[RunPackage]:
    created_at = created_at or datetime.now()
    timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    session_group_id = f"{clean_participant}_{timestamp}"
    session_root = Path(session_root)
    group_session_dir = session_root / session_group_id
    group_runner_log_dir = output_runner_logs_dir(session_root) / session_group_id
    _mkdir(group_session_dir)
    _mkdir(group_runner_log_dir)

    rows_with_global: list[tuple[int, dict[str, str]]] = list(enumerate(participant_rows, start=1))
    part_numbers = sorted(
        {
            _segment_part_number(str(row.get("phase") or "single").strip().lower() or "single")
            for _global_index, row in rows_with_global
        }
    )
    if len(part_numbers) < 2:
        raise ValueError("Split session preparation requires at least two Segment 6 parts.")
    part_count = len(part_numbers)
    total_blocks = len(participant_rows)
    packages: list[RunPackage] = []
    package_wavs: dict[str, list[RenderedWav]] = {}

    _emit_prepare_progress(
        progress_callback,
        "Preparing split Segment 6 setup",
        phase="segment6_split",
        current=0,
        total=total_blocks,
        detail=f"{session_group_id}: {part_count} parts",
    )

    for part_number in part_numbers:
        part_label = f"part_{part_number:02d}"
        part_rows = [
            (global_index, row)
            for global_index, row in rows_with_global
            if _segment_part_number(str(row.get("phase") or "single").strip().lower() or "single") == part_number
        ]
        if not part_rows:
            continue
        part_session_id = f"{session_group_id}_{part_label}"
        session_dir = group_session_dir / part_label
        run_package_dir = group_runner_log_dir / part_label
        block_dir = output_prepared_blocks_dir(session_root) / session_group_id / part_label / "blocks"
        _mkdir(block_dir)
        _mkdir(run_package_dir)
        _mkdir(session_dir)

        instruction_profile = _materialize_session_instruction_profile(
            run_setup.get("instruction_profile", {}),
            session_dir=session_dir,
            source_base_dir=run_setup_manifest_path.parent,
            output_root=session_root,
        )
        loudness_policy = normalize_loudness_policy(run_setup.get("loudness_policy"))

        design_path = run_package_dir / "design.json"
        if design is None:
            _write_text_file(design_path, "{}\n")
        else:
            _write_json_file(design_path, design_to_dict(design))

        protocol_path = run_package_dir / "protocol_schedule.csv"
        _write_segment_protocol_schedule(protocol_path, [row for _global_index, row in part_rows], clean_participant, order_csv_path)

        blocks: list[RunBlock] = []
        source_wavs: list[RenderedWav] = []
        seen_wavs: set[Path] = set()
        for part_block_number, (global_block_index, order_row) in enumerate(part_rows, start=1):
            source_csv = _resolve_relative_path(order_row.get("block_csv_path", ""), order_csv_path.parent)
            if not _path_exists(source_csv):
                raise FileNotFoundError(f"Segment 6 references a missing Segment 5 block CSV: {source_csv}")
            master_rows = _read_csv_rows(source_csv)
            if not master_rows:
                raise ValueError(f"Segment 5 block CSV has no trial rows: {source_csv}")

            phase = str(order_row.get("phase") or "single").strip().lower() or "single"
            participant_position = _as_int(order_row.get("participant_block_position"), default=global_block_index)
            source_block_index = _as_int(order_row.get("source_block_index"), default=participant_position)
            label = str(order_row.get("block_label") or f"Block {part_block_number:02d}").strip()
            base_stem = f"Block_{part_block_number:02d}_from_{Path(source_csv).stem}"
            block_csv_path = block_dir / f"{base_stem}.csv"
            block_wav_path = block_dir / f"{base_stem}.wav"

            _emit_prepare_progress(
                progress_callback,
                f"Loading WAV files for Part {part_number} block {part_block_number}/{len(part_rows)}",
                phase="loading_wavs",
                current=global_block_index - 1,
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
                duration_s, sample_rate, channels, trial_rows, wav_infos = _segment_trial_rows_from_cache(
                    master_rows,
                    cache_manifest,
                    participant_id=clean_participant,
                    session_id=part_session_id,
                    part_number=part_number,
                    phase=phase,
                    phase_label=str(order_row.get("phase_label") or phase.title()),
                    output_block_index=part_block_number,
                    participant_block_position=participant_position,
                    source_block_index=source_block_index,
                    source_block_label=label,
                    source_block_csv_path=source_csv,
                )
            else:
                _emit_prepare_progress(
                    progress_callback,
                    f"Assembling Part {part_number} block {part_block_number}/{len(part_rows)}",
                    phase="assembling_block",
                    current=global_block_index,
                    total=total_blocks,
                    detail=str(block_wav_path),
                )
                materialize_target = block_wav_path
                cache_wav_path = Path()
                cache_manifest_path = Path()
                if use_block_cache and cache_key:
                    cache_wav_path, cache_manifest_path = _segment_block_cache_paths(cache_key, block_cache_root)
                    _mkdir(cache_wav_path.parent)
                    if _path_exists(cache_wav_path):
                        Path(_filesystem_path(cache_wav_path)).unlink()
                    materialize_target = cache_wav_path
                duration_s, sample_rate, channels, trial_rows, wav_infos = _materialize_segment_block_wav(
                    materialize_target,
                    master_rows,
                    participant_id=clean_participant,
                    session_id=part_session_id,
                    part_number=part_number,
                    phase=phase,
                    phase_label=str(order_row.get("phase_label") or phase.title()),
                    output_block_index=part_block_number,
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
            for row in trial_rows:
                row["Session_Group_ID"] = session_group_id
                row["Part_Session_ID"] = part_session_id
                row["Global_Block_Index"] = global_block_index
                row["Part_Block_Number"] = part_block_number
                row["Block_Number"] = part_block_number
                row["Block_Label"] = f"Block {part_block_number:02d}"
            _write_segment_block_csv(block_csv_path, trial_rows)
            for wav in wav_infos:
                resolved = wav.path.resolve()
                if resolved not in seen_wavs:
                    source_wavs.append(wav)
                    seen_wavs.add(resolved)
            blocks.append(
                RunBlock(
                    index=part_block_number,
                    label=label,
                    manifest_path=block_csv_path,
                    wav_path=block_wav_path,
                    trial_count=len(trial_rows),
                    duration_s=duration_s,
                    metadata={
                        "execution_mode": "participant_block_wavs",
                        "phase": phase,
                        "phase_label": str(order_row.get("phase_label") or phase.title()),
                        "session_group_id": session_group_id,
                        "part_session_id": part_session_id,
                        "part_number": part_number,
                        "part_block_number": part_block_number,
                        "global_block_index": global_block_index,
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

        package = RunPackage(
            participant_id=clean_participant,
            session_id=part_session_id,
            created_at=created_at.isoformat(timespec="seconds"),
            session_dir=session_dir,
            design_path=design_path,
            protocol_path=protocol_path,
            manifest_path=run_package_dir / "session_manifest.json",
            render_manifest_path=None,
            blocks=blocks,
            execution_mode="participant_block_wavs",
            source_run_setup_manifest_path=run_setup_manifest_path,
            instruction_profile=instruction_profile,
            loudness_policy=loudness_policy,
            session_group_id=session_group_id,
            part_number=part_number,
            part_session_id=part_session_id,
            part_folder_name=part_label,
            sibling_part_manifest_paths=[],
            part_split_schema=PART_SPLIT_SCHEMA,
        )
        packages.append(package)
        package_wavs[part_session_id] = source_wavs

    if len(packages) < 2:
        raise ValueError("Split session preparation did not produce both part packages.")

    for package in packages:
        siblings = [other.manifest_path for other in packages if other.part_number != package.part_number]
        package = RunPackage(
            **{
                **package.__dict__,
                "sibling_part_manifest_paths": siblings,
            }
        )
        package_index = next(index for index, item in enumerate(packages) if item.part_number == package.part_number)
        packages[package_index] = package
        _write_session_manifest(package, package_wavs.get(package.part_session_id, []))
        _append_package_diary_event(
            package,
            "session_part_package_prepared",
            payload={
                "execution_mode": package.execution_mode,
                "block_count": len(package.blocks),
                "session_dir": str(package.session_dir),
                "source_run_setup_manifest_path": str(run_setup_manifest_path),
                "session_group_id": session_group_id,
                "part_number": package.part_number,
                "part_session_id": package.part_session_id,
            },
        )

    _write_session_group_manifest(packages, run_setup=run_setup, run_setup_manifest_path=run_setup_manifest_path)
    _emit_prepare_progress(
        progress_callback,
        "Opening Focus Mode",
        phase="opening_focus_mode",
        current=total_blocks,
        total=total_blocks,
        detail=str(_select_next_runnable_part_package(packages).manifest_path),
    )
    return packages


def _select_next_runnable_part_package(packages: list[RunPackage]) -> RunPackage:
    ordered = sorted(packages, key=lambda package: int(package.part_number or 0))
    for package in ordered:
        completed, _message = _session_package_has_completed_data(package)
        if not completed:
            return package
    return ordered[-1]


def _write_session_group_manifest(
    packages: list[RunPackage],
    *,
    run_setup: dict[str, Any],
    run_setup_manifest_path: Path,
) -> Path:
    if not packages:
        raise ValueError("Cannot write a session group manifest without packages.")
    first = packages[0]
    group_path = _session_group_manifest_path(first)
    part_entries = []
    for package in sorted(packages, key=lambda item: int(item.part_number or 0)):
        completed, message = _session_package_has_completed_data(package)
        part_entries.append(
            {
                "part_number": package.part_number,
                "part_session_id": package.part_session_id,
                "part_folder_name": package.part_folder_name,
                "session_manifest_path": str(package.manifest_path),
                "session_dir": str(package.session_dir),
                "block_count": len(package.blocks),
                "completed": completed,
                "completion_message": message,
                "part_completion_status_path": str(_part_completion_status_path(package)),
            }
        )
    payload = {
        "schema": SESSION_GROUP_MANIFEST_SCHEMA,
        "part_split_schema": PART_SPLIT_SCHEMA,
        "session_group_id": first.session_group_id,
        "participant_id": first.participant_id,
        "created_at": first.created_at,
        "source_run_setup_manifest_path": str(run_setup_manifest_path),
        "source_run_setup_sha256": _sha256_file(run_setup_manifest_path) if _path_is_file(run_setup_manifest_path) else "",
        "experiment_structure": str(run_setup.get("experiment_structure") or ""),
        "parts_per_participant": len(packages),
        "parts": part_entries,
    }
    _write_json_file(group_path, payload)
    return group_path


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
        lsl_stream_session_id: str | None = None,
        shared_lsl_outlet: Any | None = None,
        external_labrecorder_state: dict[str, Any] | None = None,
        external_labrecorder_stop_on_run_end: bool = True,
        external_labrecorder_finalize_path: Path | str | None = None,
    ):
        self.package = package
        self.audio_engine = audio_engine
        self.capture_options = _coerce_capture_options(capture_options, enable_lsl=enable_lsl)
        if lsl_stream_session_id is None and self.capture_options.external_labrecorder_scope == EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP:
            lsl_stream_session_id = package.session_group_id if _package_is_split_part(package) else package.session_id
        self._lsl_stream_session_id = str(lsl_stream_session_id or package.session_id)
        self.block_schedules = _block_event_schedules(package)
        self.trigger_dictionary = TriggerDictionary.from_schedules(self.block_schedules.values())
        self.logger = SessionEventLogger(package.participant_id)
        self._runner_log_dir = _package_runner_log_dir(package)
        self._verbose_events_dir = _package_verbose_events_dir(package)
        self._analytics_dir = _package_analytics_dir(package)
        self._topup_dir = self._runner_log_dir / "topup"
        self._runner_metadata_input = dict(runner_metadata or {})
        self._tactile_response_ledger = TopUpLedger(
            self._topup_dir,
            participant_id=package.participant_id,
            session_id=package.session_id,
        )
        self.topup_ledger = self._tactile_response_ledger if enable_topup else None
        self._adaptive_tactile_threshold = AdaptiveTactileThresholdController(
            initial_output_34_percent=adaptive_threshold_initial_output_34_percent(self._runner_metadata_input)
        )
        self._runner_metadata_input["adaptive_tactile_threshold"] = self._adaptive_tactile_threshold.policy_payload()
        self._part_identity = {
            key: value
            for key, value in _package_part_identity(package).items()
            if value not in (None, "")
        }
        self._session_metadata_path = _session_metadata_path(package)
        self._session_metadata = _build_runner_session_metadata(
            package,
            runner_metadata=self._runner_metadata_input,
            capture_options=self.capture_options,
            topup_enabled=enable_topup,
        )
        self._participant_trials_csv_path = _participant_trials_csv_path(package)
        self._participant_trial_writer = ParticipantTrialCsvWriter(
            self._participant_trials_csv_path,
            package=package,
            participant_metadata=dict(self._session_metadata.get("participant") or {}),
        )
        self._lsl_session_metadata = _redact_session_metadata_for_lsl(self._session_metadata)
        self._topup_approval_callback = topup_approval_callback
        self._instruction_continue_callback = instruction_continue_callback
        self.events = TimingEventHub(
            self.logger,
            enable_lsl=self.capture_options.enable_lsl,
            session_id=package.session_id,
            participant_id=package.participant_id,
            lsl_stream_session_id=self._lsl_stream_session_id,
            lsl_outlet=shared_lsl_outlet,
            trigger_dictionary=self.trigger_dictionary,
            event_callback=self._handle_logged_event,
            stream_metadata=self._lsl_session_metadata,
            default_payload=self._part_identity,
        )
        self._stop_requested = False
        self._analysis_outputs: dict[str, Path] = {}
        self._summary_text = ""
        self._recording_paths: list[Path] = []
        self._events_csv_path = _verbose_events_csv_path(package)
        self._events_xdf_path = _verbose_events_xdf_path(package)
        self._lsl_markers_csv_path = _lsl_markers_csv_path(package)
        self._lsl_markers_xdf_path = _lsl_markers_xdf_path(package)
        self._trigger_dictionary_path = _trigger_dictionary_path(package)
        self._external_labrecorder_xdf_path = _external_labrecorder_xdf_path(package)
        external_labrecorder_log_dir = (
            _package_group_runner_log_dir(package)
            if self.capture_options.external_labrecorder_scope == EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP
            else self._runner_log_dir
        )
        self._external_labrecorder_stdout_path = external_labrecorder_log_dir / "external_labrecorder_stdout.txt"
        self._external_labrecorder_stderr_path = external_labrecorder_log_dir / "external_labrecorder_stderr.txt"
        self._external_labrecorder_report_path = external_labrecorder_log_dir / "external_labrecorder_capture_report.json"
        self._external_labrecorder_capture: LabRecorderCapture | None = None
        self._external_labrecorder_outputs: dict[str, Path] = {}
        self._external_labrecorder_status: dict[str, Any] = {"enabled": bool(self.capture_options.start_external_labrecorder)}
        self._external_labrecorder_stop_on_run_end = bool(external_labrecorder_stop_on_run_end)
        self._external_labrecorder_finalize_path = Path(external_labrecorder_finalize_path) if external_labrecorder_finalize_path else None
        self._external_labrecorder_continuity_state = dict(external_labrecorder_state or {})
        if external_labrecorder_state:
            self._adopt_external_labrecorder_state(dict(external_labrecorder_state))
        self._external_labrecorder_stop_lock = threading.Lock()
        self._last_completed = False
        self._last_interrupted = False
        self._accepting_responses = False
        self._active_block: RunBlock | None = None
        self._run_warnings: list[str] = []
        self._instruction_continue_event: threading.Event | None = None
        self._instruction_continue_source = ""
        self._instruction_wait_context: dict[str, Any] = {}
        self._progress_callback: ProgressCallback | None = None
        self._topup_draft_signature = ""
        self._topup_outcome = "disabled" if self.topup_ledger is None else ""
        self._topup_summary: dict[str, Any] = {}
        self._operator_completion_message = ""
        self._configure_audio_engine_capture_options(self.audio_engine)

    def _adopt_external_labrecorder_state(self, state: dict[str, Any]) -> None:
        capture = state.get("capture")
        if capture is None:
            return
        self._external_labrecorder_capture = capture
        self._external_labrecorder_status = dict(state.get("status") or {})
        self._external_labrecorder_status.setdefault("enabled", True)
        self._external_labrecorder_status.setdefault("started", True)
        self._external_labrecorder_status["continued_from_previous_part"] = True
        self._external_labrecorder_xdf_path = Path(state.get("xdf_path") or self._external_labrecorder_xdf_path)
        self._external_labrecorder_stdout_path = Path(state.get("stdout_path") or self._external_labrecorder_stdout_path)
        self._external_labrecorder_stderr_path = Path(state.get("stderr_path") or self._external_labrecorder_stderr_path)
        self._external_labrecorder_report_path = Path(state.get("report_path") or self._external_labrecorder_report_path)
        self._external_labrecorder_outputs["external_labrecorder_xdf"] = self._external_labrecorder_xdf_path
        self._external_labrecorder_outputs["external_labrecorder_stdout"] = self._external_labrecorder_stdout_path
        self._external_labrecorder_outputs["external_labrecorder_stderr"] = self._external_labrecorder_stderr_path
        self._external_labrecorder_outputs["external_labrecorder_report"] = self._external_labrecorder_report_path
        if self._external_labrecorder_finalize_path is None and state.get("finalize_path"):
            self._external_labrecorder_finalize_path = Path(state["finalize_path"])

    def handoff_external_labrecorder_to_next_part(self) -> dict[str, Any] | None:
        capture = self._external_labrecorder_capture
        if capture is None or self._external_labrecorder_status.get("stop"):
            return None
        lsl_outlet = getattr(self.events, "lsl", None)
        if lsl_outlet is None:
            return None
        state = {
            "schema": "pps-runner-continuous-labrecorder-handoff.v1",
            "capture": capture,
            "status": dict(self._external_labrecorder_status),
            "xdf_path": self._external_labrecorder_xdf_path,
            "stdout_path": self._external_labrecorder_stdout_path,
            "stderr_path": self._external_labrecorder_stderr_path,
            "report_path": self._external_labrecorder_report_path,
            "lsl_outlet": lsl_outlet,
            "lsl_stream_session_id": self._lsl_stream_session_id,
            "session_group_id": self.package.session_group_id,
            "source_part_session_id": self.package.part_session_id,
            "finalize_path": _external_labrecorder_group_xdf_path(self.package),
        }
        self._external_labrecorder_capture = None
        return state

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
        try:
            external_labrecorder_start = self._start_external_labrecorder_capture()
            self.events.log(
                "session_start",
                session_dir=str(self.package.session_dir),
                session_metadata_path=str(session_metadata_path),
                session_metadata_sha256=_sha256_file(session_metadata_path) if _path_exists(session_metadata_path) else "",
                session_metadata=self._lsl_session_metadata,
                lsl_enabled=self.events.lsl_status.enabled,
                lsl_message=self.events.lsl_status.message,
                lsl_stream_session_id=self._lsl_stream_session_id,
                capture_options=self.capture_options.as_dict(),
                topup_enabled=self.topup_ledger is not None,
                external_labrecorder=external_labrecorder_start,
            )
            if _package_is_split_part(self.package):
                self.events.log(
                    "part_session_start",
                    session_dir=str(self.package.session_dir),
                    session_group_manifest_path=str(_session_group_manifest_path(self.package)),
                    part_completion_status_path=str(_part_completion_status_path(self.package)),
                    part_folder_name=self.package.part_folder_name,
                    sibling_part_manifest_paths=[str(path) for path in self.package.sibling_part_manifest_paths],
                )
            if bool(external_labrecorder_start.get("started")):
                self.events.log(
                    "external_labrecorder_start",
                    xdf_path=str(self._external_labrecorder_xdf_path),
                    labrecorder_cli=str(external_labrecorder_start.get("labrecorder_cli") or ""),
                    pid=external_labrecorder_start.get("pid"),
                    command=external_labrecorder_start.get("command") or [],
                    lsl_stream_session_id=self._lsl_stream_session_id,
                    continued_from_previous_part=bool(external_labrecorder_start.get("continued_from_previous_part")),
                )
                if event_callback is not None:
                    event_callback("external_labrecorder_started")
            if event_callback is not None:
                event_callback("session_start")
            _append_package_diary_event(
                self.package,
                "session_start",
                capture_options=self.capture_options,
                payload={
                    "session_dir": str(self.package.session_dir),
                    "session_metadata_path": str(session_metadata_path),
                    "lsl_enabled": self.events.lsl_status.enabled,
                    "lsl_message": self.events.lsl_status.message,
                    "lsl_stream_session_id": self._lsl_stream_session_id,
                    "topup_enabled": self.topup_ledger is not None,
                    "external_labrecorder": external_labrecorder_start,
                },
            )
            if engine is None:
                engine = self._create_audio_engine()
                self.audio_engine = engine
            standard_blocks = [block for block in self.package.blocks if not _truthy(block.metadata.get("is_topup_block"))]
            display_by_block, topup_display_by_part, display_block_count = _run_playback_numbering(
                standard_blocks,
                include_topup_slots=self.topup_ledger is not None,
            )
            play_start_instruction = not (
                _package_is_split_part(self.package)
                and _as_int(self.package.part_number, default=1) > 1
            )
            if play_start_instruction:
                if not self._play_instruction_slot(
                    engine,
                    "before_experiment",
                    event_callback=event_callback,
                    needs_continue=bool(standard_blocks),
                    context={"next_action": "start_experiment", "part_folder_name": self.package.part_folder_name},
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
                recording_path = _audio_evidence_path(self.package, block)
                recording_started = self._start_backup_recording(engine, recording_path, block)
                wired_loopback_path = _wired_loopback_path(self.package, block)
                wired_loopback_started = self._start_wired_loopback_recording(engine, wired_loopback_path, block)

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
                interrupted_block = not ok or self._stop_requested
                self._stop_backup_recording(engine, recording_path, block, interrupted=interrupted_block, started=recording_started)
                self._stop_wired_loopback_recording(
                    engine,
                    wired_loopback_path,
                    block,
                    interrupted=interrupted_block,
                    started=wired_loopback_started,
                )
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
                final_instruction_slot = (
                    "between_conditions"
                    if _package_is_split_part(self.package)
                    and _as_int(self.package.part_number, default=1) < _package_split_part_count(self.package)
                    else "after_experiment"
                )
                if not self._play_instruction_slot(
                    engine,
                    final_instruction_slot,
                    event_callback=event_callback,
                    needs_continue=False,
                    context={
                        "next_action": "finish_part" if final_instruction_slot == "between_conditions" else "finish_experiment",
                        "part_folder_name": self.package.part_folder_name,
                        "sibling_part_manifest_paths": [str(path) for path in self.package.sibling_part_manifest_paths],
                    },
                ):
                    interrupted = True
            completed = not interrupted
            if _package_is_split_part(self.package):
                self.events.log(
                    "part_session_end",
                    completed=completed,
                    interrupted=interrupted,
                    part_completion_status_path=str(_part_completion_status_path(self.package)),
                    next_part_manifest_path=str(self.package.sibling_part_manifest_paths[0]) if self.package.sibling_part_manifest_paths else "",
                )
            self.events.log("session_end", completed=completed, interrupted=interrupted)
        except Exception as exc:
            interrupted = True
            self.events.log("session_error", message=str(exc))
            if _package_is_split_part(self.package):
                self.events.log(
                    "part_session_end",
                    completed=False,
                    interrupted=True,
                    error=str(exc),
                    part_completion_status_path=str(_part_completion_status_path(self.package)),
                )
            _append_package_diary_event(
                self.package,
                "session_error",
                capture_options=self.capture_options,
                payload={"message": str(exc)},
            )
            self._emit(event_callback, f"Run error: {exc}")
        finally:
            self._progress_callback = None
            self._last_completed = bool(completed)
            self._last_interrupted = bool(interrupted)
            if self._external_labrecorder_stop_on_run_end:
                self._stop_external_labrecorder_capture()
            else:
                self._write_deferred_external_labrecorder_report(completed=completed, interrupted=interrupted)
            self._write_outputs()
            self._operator_completion_message = self._build_operator_completion_message(completed=completed, interrupted=interrupted)
            self._write_part_completion_status(completed=completed, interrupted=interrupted)
            self._refresh_analysis_browser_outputs(completed=completed, interrupted=interrupted)
            self._mirror_data_max_outputs()
            self._refresh_data_min_outputs(completed=completed, interrupted=interrupted)
            if owns_engine and self.audio_engine is not None and hasattr(self.audio_engine, "shutdown"):
                self.audio_engine.shutdown()

        self._operator_completion_message = self._build_operator_completion_message(completed=completed, interrupted=interrupted)
        result = SessionRunResult(
            completed=completed,
            interrupted=interrupted,
            session_dir=self.package.session_dir,
            events_csv=self._events_csv_path,
            events_xdf=self._events_xdf_path,
            analysis_outputs=self._analysis_outputs,
            summary_text=self._summary_text,
            warnings=list(self._run_warnings) if completed else ["Session was interrupted before all blocks completed.", *self._run_warnings],
            lsl_status=dict(self.events.lsl_status.__dict__),
            recording_paths=list(self._recording_paths),
            lsl_markers_csv=self._lsl_markers_csv_path,
            lsl_markers_xdf=self._lsl_markers_xdf_path,
            trigger_dictionary_path=self._trigger_dictionary_path,
            session_metadata_path=self._session_metadata_path,
            capture_options=self.capture_options.as_dict(),
            topup_summary=dict(self._topup_summary),
            adaptive_tactile_threshold_summary=self._adaptive_tactile_threshold.summary(),
            operator_completion_message=self._operator_completion_message,
        )
        _append_package_diary_event(
            self.package,
            "session_completed" if completed else "session_interrupted",
            capture_options=self.capture_options,
            payload={
                "completed": completed,
                "interrupted": interrupted,
                "events_csv": str(result.events_csv),
                "events_xdf": str(result.events_xdf),
                "lsl_markers_csv": str(result.lsl_markers_csv or ""),
                "lsl_markers_xdf": str(result.lsl_markers_xdf or ""),
                "trigger_dictionary_path": str(result.trigger_dictionary_path or ""),
                "session_metadata_path": str(result.session_metadata_path or ""),
                "recording_paths": [str(path) for path in result.recording_paths],
                "analysis_outputs": {key: str(value) for key, value in result.analysis_outputs.items()},
                "topup_summary": dict(result.topup_summary),
                "adaptive_tactile_threshold_summary": dict(result.adaptive_tactile_threshold_summary),
                "operator_completion_message": result.operator_completion_message,
                "warnings": list(result.warnings),
            },
        )
        try:
            from .profile_memory import append_output_diary_event, update_runner_settings

            event_type = "run_completed" if result.completed and not result.interrupted else "run_interrupted"
            append_output_diary_event(
                event_type,
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                participant_id=self.package.participant_id,
                session_id=self.package.session_id,
                session_dir=str(self.package.session_dir),
                session_manifest_path=str(self.package.manifest_path),
                run_setup_manifest_path=str(self.package.source_run_setup_manifest_path or ""),
                completed=result.completed,
                interrupted=result.interrupted,
                capture_options=result.capture_options,
            )
            append_output_diary_event(
                "participant_collection_summary",
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                participant_id=self.package.participant_id,
                session_id=self.package.session_id,
                data_collected=bool(result.completed and not result.interrupted),
                session_dir=str(self.package.session_dir),
                topup_summary=dict(result.topup_summary),
                adaptive_tactile_threshold_summary=dict(result.adaptive_tactile_threshold_summary),
                operator_completion_message=result.operator_completion_message,
            )
            update_runner_settings(
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                participant_id=self.package.participant_id,
                capture_options=result.capture_options,
                run_setup_manifest_path=str(self.package.source_run_setup_manifest_path or ""),
                session_manifest_path=self.package.manifest_path,
            )
        except Exception:
            pass
        return result

    def _mirror_data_max_outputs(self) -> None:
        try:
            outputs = mirror_data_max_outputs(self.package, analysis_outputs=self._analysis_outputs)
        except Exception as exc:  # noqa: BLE001 - backup organization must not hide run completion.
            self._run_warnings.append(f"2.Data_max mirror failed: {exc}")
            return
        self._analysis_outputs.update(outputs)

    def _refresh_data_min_outputs(self, *, completed: bool, interrupted: bool) -> None:
        if not completed or interrupted:
            return
        try:
            outputs = write_data_min_publication_outputs(self.package)
        except Exception as exc:  # noqa: BLE001 - public export must not hide run completion.
            self._run_warnings.append(f"1.Data_min export failed: {exc}")
            return
        self._analysis_outputs.update(outputs)

    def _write_external_labrecorder_report(self, payload: dict[str, Any]) -> None:
        _write_json_file(self._external_labrecorder_report_path, payload)
        self._external_labrecorder_outputs["external_labrecorder_report"] = self._external_labrecorder_report_path

    def _external_labrecorder_report_payload(self, *, start: dict[str, Any], stop: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": "pps-runner-owned-labrecorder-capture.v1",
            "session_id": self.package.session_id,
            "session_group_id": self.package.session_group_id,
            "part_session_id": self.package.part_session_id,
            "part_number": self.package.part_number,
            "participant_id": self.package.participant_id,
            "lsl_stream_session_id": self._lsl_stream_session_id,
            "external_labrecorder_scope": self.capture_options.external_labrecorder_scope,
            "start": start,
            "stop": stop,
        }

    def _write_deferred_external_labrecorder_report(self, *, completed: bool, interrupted: bool) -> None:
        capture = self._external_labrecorder_capture
        if capture is None or not self._external_labrecorder_status.get("started") or self._external_labrecorder_status.get("stop"):
            return
        start = {
            **{key: value for key, value in self._external_labrecorder_status.items() if key != "stop"},
            "deferred_stop_after_part": True,
            "part_completed": bool(completed),
            "part_interrupted": bool(interrupted),
            "continuity_note": "LabRecorder is intentionally left running so the next split part can share one uninterrupted XDF in the same runner window.",
        }
        self._external_labrecorder_outputs["external_labrecorder_xdf"] = self._external_labrecorder_xdf_path
        self._external_labrecorder_outputs["external_labrecorder_stdout"] = self._external_labrecorder_stdout_path
        self._external_labrecorder_outputs["external_labrecorder_stderr"] = self._external_labrecorder_stderr_path
        self._write_external_labrecorder_report(self._external_labrecorder_report_payload(start=start, stop={"deferred": True}))

    def _start_external_labrecorder_capture(self) -> dict[str, Any]:
        if self._external_labrecorder_capture is not None and self._external_labrecorder_status.get("started"):
            continued = {
                **{key: value for key, value in self._external_labrecorder_status.items() if key != "stop"},
                "enabled": True,
                "started": True,
                "continued_from_previous_part": True,
                "xdf_path": str(self._external_labrecorder_xdf_path),
                "lsl_stream_session_id": self._lsl_stream_session_id,
            }
            self._write_external_labrecorder_report(
                self._external_labrecorder_report_payload(start=continued, stop={"continued": True})
            )
            _append_package_diary_event(
                self.package,
                "external_labrecorder_continued",
                capture_options=self.capture_options,
                payload=continued,
            )
            return continued
        if not self.capture_options.start_external_labrecorder:
            self._external_labrecorder_status = {"enabled": False, "started": False}
            return dict(self._external_labrecorder_status)
        if not self.capture_options.enable_lsl or not self.events.lsl_status.enabled:
            raise RuntimeError(f"External LabRecorder capture requires active LSL outlets: {self.events.lsl_status.message}")
        try:
            cli = find_labrecorder_cli(self.capture_options.external_labrecorder_cli or None)
            capture = LabRecorderCapture(
                labrecorder_cli=cli,
                xdf_path=self._external_labrecorder_xdf_path,
                session_id=self._lsl_stream_session_id,
                stdout_path=self._external_labrecorder_stdout_path,
                stderr_path=self._external_labrecorder_stderr_path,
            )
            started = capture.start(
                stream_timeout_s=self.capture_options.external_labrecorder_stream_timeout_s,
                startup_s=self.capture_options.external_labrecorder_startup_s,
            )
        except (FileNotFoundError, LabRecorderCaptureError) as exc:
            raise RuntimeError(f"External LabRecorder capture could not start: {exc}") from exc
        self._external_labrecorder_capture = capture
        self._external_labrecorder_status = dict(started)
        self._external_labrecorder_outputs["external_labrecorder_xdf"] = self._external_labrecorder_xdf_path
        self._external_labrecorder_outputs["external_labrecorder_stdout"] = self._external_labrecorder_stdout_path
        self._external_labrecorder_outputs["external_labrecorder_stderr"] = self._external_labrecorder_stderr_path
        self._write_external_labrecorder_report(self._external_labrecorder_report_payload(start=started, stop={}))
        _append_package_diary_event(
            self.package,
            "external_labrecorder_started",
            capture_options=self.capture_options,
            payload=started,
        )
        return dict(started)

    def _stop_external_labrecorder_capture(self, *, runner_exit: bool = False, timeout_s: float | None = None) -> None:
        with self._external_labrecorder_stop_lock:
            capture = self._external_labrecorder_capture
            if capture is None:
                return
            if self._external_labrecorder_status.get("stop"):
                return
            try:
                self.events.log(
                    "external_labrecorder_stop_requested",
                    xdf_path=str(self._external_labrecorder_xdf_path),
                    pid=self._external_labrecorder_status.get("pid"),
                    runner_exit=bool(runner_exit),
                )
            except Exception:
                pass
            final_marker_settle_s = 0.0 if runner_exit else max(0.0, float(EXTERNAL_LABRECORDER_FINAL_MARKER_SETTLE_S))
            if final_marker_settle_s:
                try:
                    self.events.flush_callback_events(timeout_s=min(0.5, final_marker_settle_s))
                except Exception:
                    pass
                time.sleep(final_marker_settle_s)
            stop_timeout_s = (
                max(0.25, float(timeout_s))
                if timeout_s is not None
                else self.capture_options.external_labrecorder_stop_timeout_s
            )
            if runner_exit and hasattr(capture, "close_for_runner_exit"):
                stopped = capture.close_for_runner_exit(timeout_s=stop_timeout_s)
            else:
                stopped = capture.stop(timeout_s=stop_timeout_s)
            stopped["final_marker_settle_s"] = final_marker_settle_s
            stopped["runner_exit"] = bool(runner_exit)
            self._finalize_external_labrecorder_xdf(stopped)
            if _path_exists(self._external_labrecorder_xdf_path):
                if self._external_labrecorder_xdf_path not in self._recording_paths:
                    self._recording_paths.append(self._external_labrecorder_xdf_path)
                self._external_labrecorder_outputs["external_labrecorder_xdf"] = self._external_labrecorder_xdf_path
            for key, path in (
                ("external_labrecorder_stdout", self._external_labrecorder_stdout_path),
                ("external_labrecorder_stderr", self._external_labrecorder_stderr_path),
            ):
                if _path_exists(path):
                    self._external_labrecorder_outputs[key] = path
            self._external_labrecorder_status["stop"] = stopped
            self._write_external_labrecorder_report(
                self._external_labrecorder_report_payload(
                    start={key: value for key, value in self._external_labrecorder_status.items() if key != "stop"},
                    stop=stopped,
                )
            )
            if int(stopped.get("returncode") or 0) != 0:
                self._run_warnings.append(f"External LabRecorder exited with code {stopped.get('returncode')}.")
            _append_package_diary_event(
                self.package,
                "external_labrecorder_stopped",
                capture_options=self.capture_options,
                payload=stopped,
            )

    def _finalize_external_labrecorder_xdf(self, stopped: dict[str, Any]) -> None:
        final_path = self._external_labrecorder_finalize_path
        if final_path is None:
            return
        final_path = Path(final_path)
        source_path = self._external_labrecorder_xdf_path
        if source_path.resolve() == final_path.resolve():
            return
        if not _path_exists(source_path):
            stopped["finalize_error"] = f"source XDF did not exist: {source_path}"
            return
        try:
            _mkdir(final_path.parent)
            os.replace(_filesystem_path(source_path), _filesystem_path(final_path))
        except Exception as exc:
            stopped["finalize_error"] = str(exc)
            self._run_warnings.append(f"External LabRecorder XDF could not be moved to continuous group path: {exc}")
            return
        stopped["source_xdf_path_before_finalize"] = str(source_path)
        stopped["finalized_xdf_path"] = str(final_path)
        stopped["xdf_path"] = str(final_path)
        self._external_labrecorder_xdf_path = final_path
        self._external_labrecorder_outputs["external_labrecorder_xdf"] = final_path

    def close_external_labrecorder_for_runner_exit(self, *, timeout_s: float = 2.0) -> None:
        self._stop_requested = True
        if self._instruction_continue_event is not None:
            self.continue_instruction(source="runner_exit")
        engine = self.audio_engine
        if engine is not None:
            stop = getattr(engine, "stop", None)
            if callable(stop):
                try:
                    stop()
                except Exception:
                    pass
        had_open_capture = self._external_labrecorder_capture is not None and not self._external_labrecorder_status.get("stop")
        self._stop_external_labrecorder_capture(runner_exit=True, timeout_s=timeout_s)
        if had_open_capture and (self._last_completed or self._last_interrupted):
            self._write_outputs()
            self._write_part_completion_status(completed=self._last_completed, interrupted=self._last_interrupted)

    def _write_session_metadata(self) -> Path:
        self._session_metadata = _build_runner_session_metadata(
            self.package,
            runner_metadata=self._runner_metadata_input,
            capture_options=self.capture_options,
            topup_enabled=self.topup_ledger is not None,
            run_started_at=datetime.now().isoformat(timespec="seconds"),
            lsl_status=dict(self.events.lsl_status.__dict__),
        )
        self._session_metadata.setdefault("timing", {}).setdefault("lsl_stream", {})["source_session_id"] = self._lsl_stream_session_id
        self._session_metadata.setdefault("capture_policy", {})["external_labrecorder_scope"] = self.capture_options.external_labrecorder_scope
        _mkdir(self.package.session_dir)
        _write_json_file(self._session_metadata_path, self._session_metadata)
        return self._session_metadata_path

    def _handle_logged_event(self, event: Any) -> None:
        self._participant_trial_writer.observe_event(event)
        self._tactile_response_ledger.observe_event(event)
        self._apply_adaptive_tactile_threshold(progress_callback=self._progress_callback)
        if self.topup_ledger is None:
            return
        self._emit_topup_draft(self._progress_callback, expire=False)

    def _expire_tactile_response_windows(
        self,
        *,
        progress_callback: ProgressCallback | None = None,
        now_unix: float | None = None,
    ) -> None:
        self._tactile_response_ledger.expire_due(float(now_unix if now_unix is not None else time.time()))
        self._apply_adaptive_tactile_threshold(progress_callback=progress_callback)

    def _apply_adaptive_tactile_threshold(self, *, progress_callback: ProgressCallback | None = None) -> None:
        self._adaptive_tactile_threshold.update_counts_from_entries(self._tactile_response_ledger.entries)
        adjustments = self._adaptive_tactile_threshold.observe_missed_entries(
            self._tactile_response_ledger.missed_entries(include_topup=True)
        )
        if not adjustments:
            return
        for adjustment in adjustments:
            new_percent = float(adjustment.get("new_output_34_percent") or 0.0)
            engine = self.audio_engine
            if engine is not None:
                try:
                    setattr(engine, "tactile_volume", new_percent / 100.0)
                except Exception as exc:
                    self._run_warnings.append(f"Adaptive tactile threshold could not be applied to audio engine: {exc}")
            summary = self._adaptive_tactile_threshold.summary()
            message = (
                f"Tactile threshold nudged to Output 3/4 {new_percent:g}% "
                f"after {adjustment.get('triggering_miss_count')} tactile misses."
            )
            payload = {
                **adjustment,
                "message": message,
                "adaptive_tactile_threshold": summary,
            }
            self.events.log("tactile_threshold_adapted", **payload)
            if progress_callback is not None:
                try:
                    progress_callback({"ui_event": "tactile_threshold_adapted", **payload})
                except Exception:
                    pass

    def _persist_topup_state(self, *, part_number: int | str | None = None) -> None:
        if self.topup_ledger is None:
            return
        outputs = self.topup_ledger.write_outputs()
        draft_path = write_topup_draft_manifest(self._topup_dir, self.topup_ledger, part_number=part_number)
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
        if expire:
            self._expire_tactile_response_windows(
                progress_callback=progress_callback,
                now_unix=float(now_unix if now_unix is not None else time.time()),
            )
        if self.topup_ledger is None or progress_callback is None:
            return
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

    def _topup_summary_payload(self, *, outcome: str, part_number: int | str | None = None, phase_label: str = "") -> dict[str, Any]:
        summary = dict(self.topup_ledger.summary()) if self.topup_ledger is not None else {}
        if self.topup_ledger is not None and part_number is not None:
            selected_part = _part_suffix(part_number)
            entries = [
                entry
                for entry in self.topup_ledger.entries
                if _part_suffix(getattr(entry, "part_number", "")) == selected_part
            ]
            summary.update(
                {
                    "tracked_tactile_trials": len(entries),
                    "pending": sum(1 for entry in entries if entry.status == PENDING),
                    "hit": sum(1 for entry in entries if entry.status == HIT),
                    "missed_needs_topup": sum(1 for entry in entries if entry.status == MISSED_NEEDS_TOPUP and not entry.is_topup),
                    "topup_attempts": sum(1 for entry in entries if entry.is_topup),
                    "parts": [selected_part] if selected_part else [],
                }
            )
        payload = {
            "ui_event": "topup_completion",
            "topup_enabled": self.topup_ledger is not None,
            "topup_outcome": str(outcome or ""),
            "part_number": "" if part_number is None else _part_suffix(part_number),
            "phase_label": phase_label,
            "tracked_tactile_trials": int(summary.get("tracked_tactile_trials") or 0),
            "hit_count": int(summary.get("hit") or 0),
            "missed_needs_topup_count": int(summary.get("missed_needs_topup") or 0),
            "topup_attempt_count": int(summary.get("topup_attempts") or 0),
        }
        payload["operator_completion_message"] = self._build_operator_completion_message(
            completed=True,
            interrupted=False,
            topup_payload=payload,
        )
        return payload

    def _record_topup_outcome(
        self,
        outcome: str,
        *,
        part_number: int | str | None = None,
        phase_label: str = "",
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        payload = self._topup_summary_payload(outcome=outcome, part_number=part_number, phase_label=phase_label)
        self._topup_outcome = str(outcome or "")
        self._topup_summary = dict(payload)
        if progress_callback is not None:
            try:
                progress_callback(dict(payload))
            except Exception:
                pass
        return payload

    def _build_operator_completion_message(
        self,
        *,
        completed: bool,
        interrupted: bool,
        topup_payload: dict[str, Any] | None = None,
    ) -> str:
        part_number = _part_suffix(getattr(self.package, "part_number", ""))
        part_number_int = _as_int(part_number, default=0)
        split_part_count = _package_split_part_count(self.package)
        final_split_part = bool(_package_is_split_part(self.package) and part_number_int >= split_part_count)
        part_label = "Participant" if final_split_part else (f"Part {part_number}" if part_number else "Participant")
        if interrupted or not completed:
            return f"{part_label} interrupted before data collection completed."
        payload = dict(topup_payload or self._topup_summary or {})
        outcome = str(payload.get("topup_outcome") or self._topup_outcome or ("disabled" if self.topup_ledger is None else "")).strip()
        subject = f"{part_label} data collected" if part_label.startswith("Part ") else "Participant data collected"
        if outcome == "not_needed":
            suffix = " No top-up needed."
        elif outcome == "played":
            suffix = " Top-up completed."
        elif outcome == "skipped":
            suffix = " Top-up skipped."
        elif outcome == "failed_to_materialize":
            suffix = " Top-up could not be created; standard data was saved."
        elif outcome == "disabled":
            suffix = " Top-up disabled."
        else:
            suffix = ""
        if _package_is_split_part(self.package) and part_number_int and part_number_int < split_part_count:
            suffix = f"{suffix} Part 02 is ready."
        return f"{subject}.{suffix}".strip()

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
        force_part_transition_wait = bool(needs_continue and str((context or {}).get("next_action") or "").strip() == "next_condition")
        if (not slot or not bool(slot.get("enabled"))) and not force_part_transition_wait:
            return not self._stop_requested
        context = dict(context or {})
        slot_payload = dict(slot or {})
        if force_part_transition_wait:
            slot_payload["continue_mode"] = "button"
            slot_payload["button_label"] = _part_transition_button_label(context) or "Start Part 2"
        label = str(slot_payload.get("label") or slot_name.replace("_", " ").title())
        path_text = str(slot_payload.get("path") or "").strip()
        path = Path(path_text) if path_text else Path()
        payload = {
            "instruction_slot": slot_name,
            "instruction_label": label,
            "instruction_path": path_text,
            "instruction_continue_mode": str(slot_payload.get("continue_mode") or "click"),
            "button_label": str(slot_payload.get("button_label") or "Continue"),
            **context,
        }
        if not path_text or not _path_exists(path):
            self.events.log("instruction_missing", **payload)
            if str(path).strip():
                self._run_warnings.append(f"Instruction audio is missing for {label}: {path}")
            if force_part_transition_wait:
                return self._await_instruction_continuation(slot_payload, payload, event_callback=event_callback)
            return not self._stop_requested
        self._emit(event_callback, f"Instruction: {label}")
        self.events.log(
            "instruction_start",
            duration_s=float(slot_payload.get("duration_s") or 0.0),
            sha256=str(slot_payload.get("sha256") or ""),
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

        playback_path = _soundfile_path(path)
        try:
            returned = engine.play_instruction(playback_path, _done)
        except TypeError:
            returned = engine.play_instruction(playback_path)
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
        button_label = str(payload.get("button_label") or slot.get("button_label") or "Continue")
        self._instruction_wait_context = {**payload, "mode": mode, "button_label": button_label}
        self.events.log("instruction_continue_wait", **self._instruction_wait_context)
        self._emit(
            event_callback,
            (
                f"Click the response target to continue after {payload.get('instruction_label')}"
                if mode == "click"
                else button_label
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
            self._record_topup_outcome("disabled", part_number=part_number, phase_label=phase_label, progress_callback=progress_callback)
            return True
        self.events.flush_callback_events()
        self.topup_ledger.finalize_open_trials(part_number=part_number)
        self._apply_adaptive_tactile_threshold(progress_callback=progress_callback)
        self._persist_topup_state(part_number=part_number)
        misses = self.topup_ledger.missed_entries(include_topup=False, part_number=part_number)
        repeat_blocks = _part1_topup_repeat_blocks(self.package, part_number=part_number)
        if not misses and not repeat_blocks:
            payload = self._record_topup_outcome(
                "not_needed",
                part_number=part_number,
                phase_label=phase_label,
                progress_callback=progress_callback,
            )
            self.events.log(
                "topup_not_needed",
                missed_trial_count=0,
                part_number="" if part_number is None else _part_suffix(part_number),
                phase_label=phase_label,
                tracked_tactile_trials=payload["tracked_tactile_trials"],
                hit_count=payload["hit_count"],
                operator_completion_message=payload["operator_completion_message"],
            )
            self._persist_topup_state(part_number=part_number)
            return True
        try:
            block, manifest_outputs = self._materialize_topup_block(
                misses,
                part_number=part_number,
                phase_label=phase_label,
                display_block_index=display_block_index,
                display_block_count=display_block_count,
                repeat_blocks=repeat_blocks,
            )
        except Exception as exc:
            self.events.log("topup_block_materialize_failed", missed_trial_count=len(misses), part_number="" if part_number is None else _part_suffix(part_number), phase_label=phase_label, message=str(exc))
            self._run_warnings.append(f"Top-up block could not be materialized: {exc}")
            self._record_topup_outcome(
                "failed_to_materialize",
                part_number=part_number,
                phase_label=phase_label,
                progress_callback=progress_callback,
            )
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
            "repeat_trial_count": int(block.metadata.get("repeat_trial_count", 0) or 0),
            "topup_source_mode": str(block.metadata.get("topup_source_mode") or ""),
            "repeat_block_indexes": block.metadata.get("repeat_block_indexes") or [],
            "part_number": "" if part_number is None else _part_suffix(part_number),
            "phase_label": phase_label,
            "manifest_path": str(block.manifest_path),
            "wav_path": str(block.wav_path),
        }
        self.events.log("topup_block_ready", **summary)
        _append_package_diary_event(
            self.package,
            "topup_block_ready",
            capture_options=self.capture_options,
            payload=summary,
        )
        approved = True
        if self._topup_approval_callback is not None:
            try:
                approved = bool(self._topup_approval_callback(dict(summary)))
            except Exception as exc:
                self.events.log("topup_block_approval_failed", message=str(exc), **summary)
                _append_package_diary_event(
                    self.package,
                    "topup_block_approval_failed",
                    capture_options=self.capture_options,
                    payload={"message": str(exc), **summary},
                )
                self._run_warnings.append(f"Top-up approval failed: {exc}")
        if not approved:
            self.events.log("topup_block_skipped", reason="operator_not_approved", **summary)
            _append_package_diary_event(
                self.package,
                "topup_block_skipped",
                capture_options=self.capture_options,
                payload={"reason": "operator_not_approved", **summary},
            )
            self._persist_topup_state(part_number=part_number)
            self._record_topup_outcome("skipped", part_number=part_number, phase_label=phase_label, progress_callback=progress_callback)
            return True

        self.events.log("topup_block_approved", **summary)
        _append_package_diary_event(
            self.package,
            "topup_block_approved",
            capture_options=self.capture_options,
            payload=summary,
        )
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
        recording_path = _audio_evidence_path(self.package, block)
        recording_started = self._start_backup_recording(engine, recording_path, block)
        wired_loopback_path = _wired_loopback_path(self.package, block)
        wired_loopback_started = self._start_wired_loopback_recording(engine, wired_loopback_path, block)

        def _progress(elapsed_s: float, current_block: RunBlock = block) -> None:
            self._expire_tactile_response_windows(
                progress_callback=progress_callback,
                now_unix=block_start_unix + float(elapsed_s or 0.0),
            )
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
        interrupted_block = not ok or self._stop_requested
        self._stop_backup_recording(engine, recording_path, block, interrupted=interrupted_block, started=recording_started)
        self._stop_wired_loopback_recording(
            engine,
            wired_loopback_path,
            block,
            interrupted=interrupted_block,
            started=wired_loopback_started,
        )
        self._accepting_responses = False
        self.events.log("block_end", block_number=block.index, block_label=block.label, completed=ok, is_topup=True)
        self.topup_ledger.finalize_open_trials(part_number=part_number)
        self._apply_adaptive_tactile_threshold(progress_callback=progress_callback)
        self._persist_topup_state(part_number=part_number)
        if not ok:
            self._run_warnings.append("Top-up block was interrupted before completion.")
            return False
        self._record_topup_outcome("played", part_number=part_number, phase_label=phase_label, progress_callback=progress_callback)
        return not self._stop_requested

    def stop(self) -> None:
        self._stop_requested = True
        if self.audio_engine is not None and hasattr(self.audio_engine, "stop"):
            self.audio_engine.stop()
        self.events.log("operator_stop")
        _append_package_diary_event(self.package, "operator_stop", capture_options=self.capture_options)

    def pause(self) -> None:
        if self.audio_engine is not None and hasattr(self.audio_engine, "pause"):
            self.audio_engine.pause()
        self.events.log("operator_pause")
        _append_package_diary_event(self.package, "operator_pause", capture_options=self.capture_options)

    def resume(self) -> None:
        if self.audio_engine is not None and hasattr(self.audio_engine, "resume"):
            self.audio_engine.resume()
        self.events.log("operator_resume")
        _append_package_diary_event(self.package, "operator_resume", capture_options=self.capture_options)

    def awaiting_instruction_continue(self) -> dict[str, Any]:
        return dict(self._instruction_wait_context)

    def continue_instruction(self, *, source: str = "operator") -> None:
        if self._instruction_continue_event is None:
            return
        self._instruction_continue_source = str(source or "operator")
        self._instruction_continue_event.set()
        _append_package_diary_event(
            self.package,
            "instruction_continue",
            capture_options=self.capture_options,
            payload={"source": self._instruction_continue_source, "context": dict(self._instruction_wait_context)},
        )

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
        _append_package_diary_event(
            self.package,
            "mouse_click",
            capture_options=self.capture_options,
            payload={
                "event_id": event.event_id,
                "in_target": in_target,
                "during_playback": during_playback,
                **block_payload,
            },
        )

    def _materialize_topup_block(
        self,
        misses: list[Any],
        *,
        part_number: int | str | None = None,
        phase_label: str = "",
        display_block_index: int | None = None,
        display_block_count: int | None = None,
        repeat_blocks: list[RunBlock] | None = None,
    ) -> tuple[RunBlock, dict[str, Path]]:
        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise RuntimeError("Install numpy and soundfile to prepare a top-up block.") from exc

        repeat_blocks = list(repeat_blocks or [])
        repeat_mode = bool(repeat_blocks)
        emitted: list[tuple[str, Any | None, dict[str, Any], Path, RunBlock]] = []
        if repeat_mode:
            row_order: list[str] = []
            for source_block in repeat_blocks:
                source_rows = _read_csv_rows(source_block.manifest_path)
                if not source_rows:
                    raise ValueError(f"Top-up repeat source block has no rows: {source_block.manifest_path}")
                for source_row in source_rows:
                    row = dict(source_row)
                    label = _topup_row_label(row) or "row"
                    if label not in row_order:
                        row_order.append(label)
                    emitted.append(("repeat", None, row, source_block.manifest_path.parent, source_block))
        else:
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
        multi_part = _package_is_split_part(self.package) or len(_package_part_numbers(self.package)) > 1
        repeat_indexes = _repeat_block_indexes(repeat_blocks)
        repeat_label = ", ".join(f"{index:02d}" for index in repeat_indexes)
        repeat_stem = "_".join(f"{index:02d}" for index in repeat_indexes)
        if repeat_mode:
            block_label = (
                f"Part {part_label} top-up repeat blocks {repeat_label}"
                if multi_part and part_label
                else f"Top-up repeat blocks {repeat_label}"
            )
            block_stem = f"Block_{block_index:02d}_{'part' + part_label + '_' if multi_part and part_label else ''}topup_repeat_blocks_{repeat_stem}"
        else:
            block_label = f"Part {part_label} top-up missed tactile trials" if multi_part and part_label else "Top-up missed tactile trials"
            block_stem = f"Block_{block_index:02d}_{'part' + part_label + '_' if multi_part and part_label else ''}topup_missed_trials"
        wav_path = _package_prepared_blocks_dir(self.package) / f"{block_stem}.wav"
        manifest_stem = f"topup_block_part{part_label}_manifest" if multi_part and part_label else "topup_block_manifest"
        csv_path = self._topup_dir / f"{manifest_stem}.csv"
        json_path = self._topup_dir / f"{manifest_stem}.json"

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
            looming_onset_s = _segment_looming_onset_s(source_row)
            tactile_onset_s = _segment_tactile_onset_s(source_row, looming_onset_s)
            family = _segment_family(source_row)
            data, tactile_compensation = _apply_tactile_drive_compensation(
                data,
                sample_rate=sample_rate,
                family=family,
                tactile_onset_s=tactile_onset_s,
            )
            target_channels = max(target_channels, int(data.shape[1]))
            clips.append(data)
            duration_frames = int(data.shape[0])
            trial_start_sample = frame_cursor
            trial_end_sample = frame_cursor + duration_frames
            duration_s = float(duration_frames / sample_rate) if sample_rate else 0.0
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
                tactile_drive_onset_s=float(tactile_compensation.get("drive_onset_s") or tactile_onset_s),
                tactile_compensation=tactile_compensation,
            )
            row["Session_Group_ID"] = self.package.session_group_id
            row["Part_Session_ID"] = _package_part_session_id(self.package) if _package_is_split_part(self.package) else ""
            row["Global_Block_Index"] = _row_value(source_row, "Global_Block_Index", default=block_index)
            row["Part_Block_Number"] = block_index
            row["Trial_UID"] = f"{self.package.participant_id}_topup_B{block_index:02d}_T{trial_index:03d}_{role}"
            row["Block_Label"] = block_label
            row["Is_Topup"] = "true"
            row["Topup_Role"] = role
            row["Primary_Analysis_Included"] = "true" if role in {"rescue", "repeat"} else "false"
            row["Source_Trial_UID"] = source_uid
            row["Original_Trial_UID"] = source_uid
            row["Topup_Source_Ledger_ID"] = "" if entry is None else getattr(entry, "ledger_id", "")
            row["Topup_Source_Block_Number"] = _row_value(source_row, "Block_Number", "block_number", default=getattr(entry, "block_number", ""))
            row["Topup_Source_Trial_Number"] = _row_value(source_row, "Trial_Number", "trial_number", default=getattr(entry, "trial_number", ""))
            row["Topup_Attempt_Number"] = 2 if role in {"rescue", "repeat"} else 1
            row["Topup_Rescue_Analysis_Role"] = (
                "primary_rescue" if role == "rescue" else ("block_repeat" if role == "repeat" else "row_structure_filler")
            )
            if role == "repeat":
                row["Topup_Repeat_Source_Block_Index"] = _as_int(
                    source_block.metadata.get("part_block_number", source_block.index),
                    default=source_block.index,
                )
                row["Topup_Repeat_Source_Block_Label"] = source_block.label
                row["Topup_Repeat_Source_Block_Manifest"] = str(source_block.manifest_path)
            trial_rows.append(row)
            frame_cursor = trial_end_sample

        padded = []
        for data in clips:
            if data.shape[1] < target_channels:
                pad = np.zeros((data.shape[0], target_channels - data.shape[1]), dtype=data.dtype)
                data = np.concatenate([data, pad], axis=1)
            padded.append(data)
        block_audio = np.concatenate(padded, axis=0)
        _mkdir(wav_path.parent)
        sf.write(_soundfile_path(wav_path), block_audio, sample_rate, subtype="PCM_16")
        _write_csv_rows(csv_path, trial_rows)
        _write_text_file(
            json_path,
            json.dumps(
                {
                    "schema": "pps-topup-block-manifest.v1",
                    "participant_id": self.package.participant_id,
                    "session_id": self.package.session_id,
                    "session_group_id": self.package.session_group_id,
                    "part_session_id": _package_part_session_id(self.package) if _package_is_split_part(self.package) else "",
                    "part_number": "" if part_number is None else part_label,
                    "phase_label": phase_label,
                    "block_index": block_index,
                    "display_block_index": display_index,
                    "play_order_index": display_index,
                    "display_block_count": display_count,
                    "block_label": block_label,
                    "row_order": row_order,
                    "topup_source_mode": "repeat_blocks" if repeat_mode else "missed_trials",
                    "repeat_block_indexes": repeat_indexes,
                    "repeat_block_manifest_paths": [str(block.manifest_path) for block in repeat_blocks],
                    "missed_trial_count": len(misses),
                    "rescue_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "rescue"),
                    "filler_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "filler"),
                    "repeat_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "repeat"),
                    "csv_path": str(csv_path),
                    "wav_path": str(wav_path),
                    "rows": _json_ready(trial_rows),
                },
                indent=2,
            ),
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
                "session_group_id": self.package.session_group_id,
                "part_session_id": _package_part_session_id(self.package) if _package_is_split_part(self.package) else "",
                "display_block_index": display_index,
                "play_order_index": display_index,
                "display_block_count": display_count,
                "part_number": _as_int(_row_value(trial_rows[0], "Part_Number", default=1), default=1) if trial_rows else 1,
                "sample_rate_hz": sample_rate,
                "channels": target_channels,
                "topup_source_mode": "repeat_blocks" if repeat_mode else "missed_trials",
                "repeat_block_indexes": repeat_indexes,
                "repeat_block_manifest_paths": [str(block.manifest_path) for block in repeat_blocks],
                "rescue_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "rescue"),
                "filler_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "filler"),
                "repeat_trial_count": sum(1 for row in trial_rows if row.get("Topup_Role") == "repeat"),
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
        self._configure_audio_engine_capture_options(engine)
        if CLICK_SOUND and not engine.load_click_sound(CLICK_SOUND):
            raise RuntimeError(
                "Audio output stream could not be opened for the tactile response-marker path. "
                "Check the selected ASIO device and restart the runner."
            )
        return engine

    def _configure_audio_engine_capture_options(self, engine: Any | None) -> None:
        if engine is None or not hasattr(engine, "set_wired_loopback_mode"):
            return
        try:
            engine.set_wired_loopback_mode(self.capture_options.wired_loopback_mode)
        except Exception as exc:
            self._run_warnings.append(f"Wired loopback mode could not be applied: {exc}")

    def _write_outputs(self) -> None:
        self.events.flush_callback_events()
        topup_outputs: dict[str, Path] = {}
        self._tactile_response_ledger.finalize_open_trials()
        self._apply_adaptive_tactile_threshold()
        adaptive_outputs = self._adaptive_tactile_threshold.write_outputs(self._runner_log_dir)
        if self.topup_ledger is not None:
            topup_outputs = self.topup_ledger.write_outputs()
            topup_outputs["topup_block_manifest_draft"] = write_topup_draft_manifest(self._topup_dir, self.topup_ledger)
            topup_manifest_csv = self._topup_dir / "topup_block_manifest.csv"
            topup_manifest_json = self._topup_dir / "topup_block_manifest.json"
            if topup_manifest_csv.exists():
                topup_outputs["topup_block_manifest"] = topup_manifest_csv
            if topup_manifest_json.exists():
                topup_outputs["topup_block_manifest_json"] = topup_manifest_json
            for part_csv in sorted(self._topup_dir.glob("topup_block_part*_manifest.csv")):
                match = re.search(r"part([^_]+)_manifest", part_csv.stem)
                key = f"topup_block_manifest_part{match.group(1)}" if match else part_csv.stem
                topup_outputs[key] = part_csv
            for part_json in sorted(self._topup_dir.glob("topup_block_part*_manifest.json")):
                match = re.search(r"part([^_]+)_manifest", part_json.stem)
                key = f"topup_block_manifest_json_part{match.group(1)}" if match else part_json.stem
                topup_outputs[key] = part_json
            topup_block_dir = _package_prepared_blocks_dir(self.package)
            for topup_wav in sorted(topup_block_dir.glob("*topup*.wav")):
                match = re.search(r"_part([^_]+)_topup", topup_wav.stem)
                if match:
                    topup_outputs[f"topup_block_wav_part{match.group(1)}"] = topup_wav
                elif "topup_block_wav" not in topup_outputs:
                    topup_outputs["topup_block_wav"] = topup_wav
                else:
                    topup_outputs[topup_wav.stem] = topup_wav
        self._participant_trial_writer.rewrite_from_events(self.logger.events)
        events_csv = self._events_csv_path
        events_xdf = self._events_xdf_path
        lsl_markers_csv = self._lsl_markers_csv_path
        lsl_markers_xdf = self._lsl_markers_xdf_path
        trigger_dictionary_path = self._trigger_dictionary_path
        if self.capture_options.write_events_csv:
            self.logger.write_csv(events_csv)
        if self.capture_options.write_internal_xdf:
            self.logger.write_xdf(
                events_xdf,
                metadata={
                    "participant_id": self.package.participant_id,
                    "session_id": self.package.session_id,
                    "session_group_id": self.package.session_group_id,
                    "part_session_id": self.package.part_session_id,
                    "part_number": self.package.part_number,
                    "lsl_stream_session_id": self._lsl_stream_session_id,
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
        self._analysis_outputs["participant_trials"] = self._participant_trials_csv_path
        if self.capture_options.write_analysis_csvs:
            self._analysis_outputs.update(write_analysis_csvs(analysis, self._analytics_dir, self.package.session_id))
            self._analysis_outputs["timing_qc"] = _write_timing_qc_csv(self.logger.events, self._analytics_dir / f"{self.package.session_id}_timing_qc.csv")
        self._analysis_outputs.update(adaptive_outputs)
        self._analysis_outputs.update(topup_outputs)
        if self.capture_options.write_lsl_marker_mirror:
            self._analysis_outputs["lsl_markers"] = lsl_markers_csv
            self._analysis_outputs["lsl_markers_xdf"] = lsl_markers_xdf
        if self.capture_options.write_trigger_dictionary:
            self._analysis_outputs["trigger_dictionary"] = trigger_dictionary_path
        if _path_exists(self._session_metadata_path):
            self._analysis_outputs["session_metadata"] = self._session_metadata_path
        self._analysis_outputs.update(self._external_labrecorder_outputs)
        self._summary_text = format_analysis_summary(analysis)
        _mkdir(self._analytics_dir)
        _write_text_file(self._analytics_dir / "analysis_summary.txt", self._summary_text + "\n", encoding="utf-8")

    def _refresh_analysis_browser_outputs(self, *, completed: bool, interrupted: bool) -> None:
        if interrupted or not completed or not self.capture_options.write_analysis_csvs:
            return
        try:
            catalog = refresh_analysis_browser_outputs(
                _package_output_root(self.package),
                preferred_participant_id=self.package.participant_id,
            )
        except Exception as exc:  # noqa: BLE001 - derived analysis must not block run completion.
            self._run_warnings.append(f"Analysis browser catalog refresh failed: {exc}")
            return
        self._analysis_outputs["analysis_catalog"] = catalog.path
        for warning in catalog.warnings:
            self._run_warnings.append(warning)

    def _write_part_completion_status(self, *, completed: bool, interrupted: bool) -> None:
        if not _package_is_split_part(self.package):
            return
        status_path = _part_completion_status_path(self.package)
        payload = {
            "schema": PART_COMPLETION_STATUS_SCHEMA,
            "session_group_id": self.package.session_group_id,
            "part_session_id": self.package.part_session_id,
            "session_id": self.package.session_id,
            "participant_id": self.package.participant_id,
            "part_number": self.package.part_number,
            "part_folder_name": self.package.part_folder_name,
            "completed": bool(completed),
            "interrupted": bool(interrupted),
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "session_manifest_path": str(self.package.manifest_path),
            "session_dir": str(self.package.session_dir),
            "events_csv": str(self._events_csv_path),
            "lsl_markers_csv": str(self._lsl_markers_csv_path),
            "lsl_stream_session_id": self._lsl_stream_session_id,
            "trigger_dictionary_json": str(self._trigger_dictionary_path),
            "session_metadata_json": str(self._session_metadata_path),
            "participant_trials_csv": str(self._participant_trials_csv_path),
            "external_labrecorder_scope": self.capture_options.external_labrecorder_scope,
            "external_labrecorder_xdf": str(self._external_labrecorder_xdf_path),
            "external_labrecorder_group_xdf": str(_external_labrecorder_group_xdf_path(self.package)),
            "external_labrecorder_report": str(self._external_labrecorder_report_path),
            "topup_enabled": self.topup_ledger is not None,
            "topup_outcome": str(self._topup_summary.get("topup_outcome") or self._topup_outcome or ("disabled" if self.topup_ledger is None else "")),
            "tracked_tactile_trials": int(self._topup_summary.get("tracked_tactile_trials") or 0),
            "hit_count": int(self._topup_summary.get("hit_count") or 0),
            "missed_needs_topup_count": int(self._topup_summary.get("missed_needs_topup_count") or 0),
            "topup_attempt_count": int(self._topup_summary.get("topup_attempt_count") or 0),
            "adaptive_tactile_threshold_summary": self._adaptive_tactile_threshold.summary(),
            "operator_completion_message": self._operator_completion_message
            or self._build_operator_completion_message(completed=completed, interrupted=interrupted),
            "analysis_outputs": {key: str(value) for key, value in self._analysis_outputs.items()},
        }
        _write_json_file(status_path, payload)
        packages = [self.package]
        for sibling in self.package.sibling_part_manifest_paths:
            try:
                packages.append(load_run_package(Path(sibling)))
            except Exception:
                continue
        try:
            run_setup = _load_json(self.package.source_run_setup_manifest_path) if self.package.source_run_setup_manifest_path else {}
            _write_session_group_manifest(
                packages,
                run_setup=run_setup,
                run_setup_manifest_path=self.package.source_run_setup_manifest_path or Path(),
            )
        except Exception:
            return

    def _play_block_with_schedule(
        self,
        engine: Any,
        block: RunBlock,
        *,
        progress_callback: Callable[[float], None],
        block_event_schedule: BlockEventSchedule | None,
    ) -> bool:
        playback_path = _soundfile_path(block.wav_path)
        try:
            return bool(
                engine.play_block(
                    playback_path,
                    progress_callback=progress_callback,
                    audio_event_callback=self.events.enqueue_callback_event,
                    block_event_schedule=block_event_schedule,
                )
            )
        except TypeError:
            return bool(
                engine.play_block(
                    playback_path,
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
            _mkdir(path.parent)
            started = bool(engine.start_recording(_filesystem_path(path)))
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
            engine.stop_recording(_filesystem_path(path), interrupted=interrupted)
            self.events.log("recording_end", block_number=block.index, block_label=block.label, path=str(path), interrupted=interrupted)
        except Exception as exc:
            self.events.log("recording_stop_failed", block_number=block.index, block_label=block.label, path=str(path), message=str(exc))

    def _start_wired_loopback_recording(self, engine: Any, path: Path, block: RunBlock) -> bool:
        if self.capture_options.wired_loopback_mode != WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY:
            return False
        if not hasattr(engine, "start_wired_loopback_recording"):
            self.events.log(
                "wired_loopback_unavailable",
                block_number=block.index,
                block_label=block.label,
                mode=self.capture_options.wired_loopback_mode,
                reason="audio engine has no wired loopback recording API",
            )
            return False
        try:
            _mkdir(path.parent)
            sample_rate = _as_int(
                block.metadata.get("sample_rate_hz", block.metadata.get("sample_rate")),
                default=0,
            )
            if sample_rate <= 0:
                try:
                    import soundfile as sf

                    sample_rate = int(sf.info(_soundfile_path(block.wav_path)).samplerate)
                except Exception:
                    sample_rate = 0
            started = bool(
                engine.start_wired_loopback_recording(
                    _filesystem_path(path),
                    mode=self.capture_options.wired_loopback_mode,
                    sample_rate=sample_rate or None,
                )
            )
        except Exception as exc:
            self.events.log(
                "wired_loopback_start_failed",
                block_number=block.index,
                block_label=block.label,
                path=str(path),
                mode=self.capture_options.wired_loopback_mode,
                message=str(exc),
            )
            return False
        self.events.log(
            "wired_loopback_start",
            block_number=block.index,
            block_label=block.label,
            path=str(path),
            started=started,
            mode=self.capture_options.wired_loopback_mode,
            source_output_channel_1based=4,
            input_channel_1based=4,
            scope="duplicate_tactile_proxy_not_woojer_mechanical_onset",
            message=str(getattr(engine, "_wired_loopback_last_error", "") or ""),
        )
        if started:
            self._recording_paths.append(path)
        return started

    def _stop_wired_loopback_recording(self, engine: Any, path: Path, block: RunBlock, *, interrupted: bool, started: bool) -> None:
        if not started or not hasattr(engine, "stop_wired_loopback_recording"):
            return
        try:
            engine.stop_wired_loopback_recording(_filesystem_path(path), interrupted=interrupted)
            self.events.log(
                "wired_loopback_end",
                block_number=block.index,
                block_label=block.label,
                path=str(path),
                interrupted=interrupted,
                mode=self.capture_options.wired_loopback_mode,
            )
        except Exception as exc:
            self.events.log(
                "wired_loopback_stop_failed",
                block_number=block.index,
                block_label=block.label,
                path=str(path),
                message=str(exc),
            )

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


def _flat_event_row(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        row = dict(event)
    elif hasattr(event, "as_flat_dict"):
        row = dict(event.as_flat_dict())
    else:
        row = {
            "event_id": getattr(event, "event_id", ""),
            "event_type": getattr(event, "event_type", ""),
            "unix_time": getattr(event, "unix_time", ""),
            "monotonic_time": getattr(event, "monotonic_time", ""),
        }
        payload = getattr(event, "payload", {}) or {}
        if isinstance(payload, dict):
            row.update(payload)
    payload_json = row.get("payload_json")
    if payload_json and isinstance(payload_json, str):
        try:
            payload = json.loads(payload_json)
        except Exception:
            payload = {}
        if isinstance(payload, dict):
            for key, value in payload.items():
                row.setdefault(key, value)
    return row


def _trial_is_catch(trial_type: str, family: str) -> bool:
    text = f"{trial_type} {family}".strip().lower()
    return "catch" in text or "audio_only" in text or "audio-only" in text


def _trial_has_tactile(trial_type: str, family: str, tactile_event_seen: bool) -> bool:
    if tactile_event_seen:
        return True
    text = f"{trial_type} {family}".strip().lower()
    if _trial_is_catch(trial_type, family):
        return False
    return "tactile" in text or "baseline" in text


def _trial_has_audio(trial_type: str, family: str, looming_event_seen: bool) -> bool:
    if looming_event_seen:
        return True
    text = f"{trial_type} {family}".strip().lower()
    if "baseline" in text and "audio" not in text:
        return False
    return "audio" in text or "catch" in text


def _trial_stimulus_modality(trial_type: str, family: str, tactile_event_seen: bool) -> str:
    tactile = _trial_has_tactile(trial_type, family, tactile_event_seen)
    audio = _trial_has_audio(trial_type, family, False)
    if tactile and audio:
        return "audiotactile"
    if tactile:
        return "tactile"
    if audio:
        return "audio"
    return ""


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
        kwargs: dict[str, Any] = {}
        bool_fields = {
            "enable_lsl",
            "write_events_csv",
            "write_internal_xdf",
            "write_analysis_csvs",
            "write_lsl_marker_mirror",
            "write_trigger_dictionary",
            "start_backup_recording",
            "start_external_labrecorder",
        }
        float_fields = {
            "external_labrecorder_stream_timeout_s",
            "external_labrecorder_startup_s",
            "external_labrecorder_stop_timeout_s",
        }
        for key in allowed:
            if key not in value:
                continue
            if key == "wired_loopback_mode":
                kwargs[key] = normalize_wired_loopback_mode(value[key])
            elif key == "external_labrecorder_scope":
                kwargs[key] = _normalize_external_labrecorder_scope(value[key])
            elif key == "external_labrecorder_cli":
                kwargs[key] = str(value[key] or "")
            elif key in float_fields:
                try:
                    kwargs[key] = max(0.0, float(value[key]))
                except (TypeError, ValueError):
                    kwargs[key] = getattr(SessionCaptureOptions(), key)
            elif key in bool_fields:
                kwargs[key] = bool(value[key])
            else:
                kwargs[key] = value[key]
        options = SessionCaptureOptions(**kwargs)
    else:
        raise TypeError(f"Unsupported capture options type: {type(value)!r}")
    if enable_lsl is not None:
        options = SessionCaptureOptions(**{**options.as_dict(), "enable_lsl": bool(enable_lsl)})
    else:
        normalized_mode = normalize_wired_loopback_mode(options.wired_loopback_mode)
        normalized_scope = _normalize_external_labrecorder_scope(options.external_labrecorder_scope)
        if normalized_mode != options.wired_loopback_mode or normalized_scope != options.external_labrecorder_scope:
            options = SessionCaptureOptions(
                **{
                    **options.as_dict(),
                    "wired_loopback_mode": normalized_mode,
                    "external_labrecorder_scope": normalized_scope,
                }
            )
    if not (options.write_events_csv or options.write_internal_xdf or options.write_analysis_csvs or options.write_lsl_marker_mirror):
        raise ValueError("At least one durable runner output must be enabled.")
    if options.start_external_labrecorder and not options.enable_lsl:
        raise ValueError("Runner-owned LabRecorder capture requires live LSL outlets.")
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
        "session_group_id": package.session_group_id,
        "part_session_id": _package_part_session_id(package),
        "part_number": package.part_number,
        "part_folder_name": package.part_folder_name,
        "part_split_schema": package.part_split_schema,
        "sibling_part_manifest_paths": [str(path) for path in package.sibling_part_manifest_paths],
        "created_at": package.created_at,
        "run_started_at": run_started_at,
        "participant": participant,
        "experiment": _experiment_metadata_from_package(package),
        "capture_policy": {
            **capture_options.as_dict(),
            "topup_missed_trials_by_part": bool(topup_enabled),
            "lsl_event_protocol_standard": True,
            "local_audio_evidence_wav_label": "Fail-safe local audio evidence WAV",
            "playback_output_levels": _json_ready(raw.get("playback_output_levels") or {}),
            "tactile_calibration": _json_ready(raw.get("tactile_calibration") or {}),
            "adaptive_tactile_threshold": _json_ready(raw.get("adaptive_tactile_threshold") or {}),
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
        "session_group_id": package.session_group_id,
        "part_session_id": _package_part_session_id(package),
        "part_number": package.part_number,
        "part_split_schema": package.part_split_schema,
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
        "session_group_manifest": _session_group_manifest_path(package) if _package_is_split_part(package) else None,
        "part_completion_status": _part_completion_status_path(package) if _package_is_split_part(package) else None,
        "participant_trials_csv": _participant_trials_csv_path(package),
        "verbose_events_csv": _verbose_events_csv_path(package),
        "verbose_events_xdf": _verbose_events_xdf_path(package),
        "lsl_markers_csv": _lsl_markers_csv_path(package),
        "lsl_markers_xdf": _lsl_markers_xdf_path(package),
        "trigger_dictionary_json": _trigger_dictionary_path(package),
    }
    result = {
        key: {
            "path": "" if path is None else str(path),
            "sha256": "" if path is None or not _path_exists(path) else _sha256_file(Path(path)),
        }
        for key, path in paths.items()
    }
    result["directories"] = {
        "participant_data_dir": str(package.session_dir),
        "experiment_context_dir": str(output_metadata_dir(_package_output_root(package))),
        "runner_logs_dir": str(_package_runner_log_dir(package)),
        "verbose_events_dir": str(_package_verbose_events_dir(package)),
        "data_analytics_dir": str(_package_analytics_dir(package)),
        "prepared_blocks_dir": str(_package_prepared_blocks_dir(package)),
    }
    return result


def _append_package_diary_event(
    package: RunPackage,
    event_type: str,
    *,
    capture_options: dict[str, Any] | SessionCaptureOptions | None = None,
    payload: dict[str, Any] | None = None,
) -> Path | None:
    try:
        experiment = _experiment_metadata_from_package(package)
        experiment_name = str(experiment.get("experiment_name") or experiment.get("project_label") or "PPS experiment")
        profile_id = str(experiment.get("template_id") or "")
        diary_path = ensure_output_diary(Path(package.session_dir).parent, experiment_name)
        options = capture_options.as_dict() if isinstance(capture_options, SessionCaptureOptions) else dict(capture_options or {})
        return append_diary_entry(
            diary_path,
            event_type,
            session_id=package.session_id,
            participant_id=package.participant_id,
            experiment_name=experiment_name,
            profile_id=profile_id,
            run_setup_manifest_path="" if package.source_run_setup_manifest_path is None else str(package.source_run_setup_manifest_path),
            session_manifest_path=str(package.manifest_path),
            capture_options=options,
            payload=payload or {},
        )
    except Exception:
        return None


def _append_activity_diary_event(event: dict[str, Any]) -> Path | None:
    session_manifest_text = str(event.get("session_manifest_path") or event.get("session_manifest") or "").strip()
    session_dir_text = str(event.get("session_dir") or "").strip()
    package: RunPackage | None = None
    if session_manifest_text:
        try:
            package = load_run_package(Path(session_manifest_text))
        except Exception:
            package = None
    if package is not None:
        return _append_package_diary_event(package, str(event.get("event_type") or "activity"), payload=event)
    if not session_dir_text:
        return None
    try:
        session_dir = Path(session_dir_text).expanduser().resolve()
        root = session_dir.parent
        diary_path = find_output_diary(root) or ensure_output_diary(root, str(event.get("experiment_name") or "PPS experiment"))
        return append_diary_entry(
            diary_path,
            str(event.get("event_type") or "activity"),
            participant_id=str(event.get("participant_id") or ""),
            experiment_name=str(event.get("experiment_name") or ""),
            profile_id=str(event.get("template_id") or event.get("profile_id") or ""),
            run_setup_manifest_path=str(event.get("run_setup_manifest_path") or ""),
            session_manifest_path=session_manifest_text,
            payload=event,
        )
    except Exception:
        return None


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


def _timeline_noise_type_label(payload: dict[str, Any]) -> str:
    return _timeline_payload_label(payload, "Noise_Type", "noise_type")


def _part_transition_button_label(payload: dict[str, Any]) -> str:
    if str(payload.get("next_action") or "").strip() != "next_condition":
        return ""
    part = _timeline_payload_label(payload, "next_part_number", "part_number", "block_part_number", "Part_Number")
    if not part:
        return "Start Part 2"
    try:
        return f"Start Part {int(float(part))}"
    except ValueError:
        return f"Start Part {part}"


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
                "noise_type": _timeline_noise_type_label(payload),
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
                "noise_type": _timeline_noise_type_label(payload),
                "soa_ms": str(payload.get("soa_ms") or payload.get("SOA_ms") or "").strip(),
                "family": str(payload.get("family") or payload.get("Family") or ""),
                "trial_type": trial_type,
            }
        )
    return segments


def _part1_topup_repeat_blocks(
    package: RunPackage,
    *,
    part_number: int | str | None,
) -> list[RunBlock]:
    """Return the part-local blocks that should be replayed by the Part 1 top-up."""
    if _part_suffix(part_number) != "1":
        return []
    if not _package_is_split_part(package) or _package_split_part_count(package) < 2:
        return []
    wanted = {int(index) for index in PART1_TOPUP_REPEAT_BLOCK_INDEXES}
    matches: dict[int, RunBlock] = {}
    for block in package.blocks:
        if _truthy(block.metadata.get("is_topup_block")):
            continue
        if _block_part_key(block) != "1":
            continue
        part_block_index = _as_int(block.metadata.get("part_block_number", block.index), default=block.index)
        if part_block_index in wanted:
            matches[int(part_block_index)] = block
    if set(matches) != wanted:
        return []
    return [matches[index] for index in PART1_TOPUP_REPEAT_BLOCK_INDEXES]


def _repeat_block_indexes(blocks: list[RunBlock]) -> list[int]:
    return [
        _as_int(block.metadata.get("part_block_number", block.index), default=block.index)
        for block in blocks
    ]


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
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
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
    _write_json_file(manifest_path, manifest)


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


def _materialize_session_instruction_profile(
    value: Any,
    *,
    session_dir: Path,
    source_base_dir: Path,
    output_root: Path | None = None,
) -> dict[str, Any]:
    profile = _normalize_instruction_profile(value)
    slots: list[dict[str, Any]] = []
    instruction_dir = output_shared_instructions_dir(Path(output_root) if output_root is not None else Path(session_dir).parent)
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
        _mkdir(instruction_dir)
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


def _tactile_drive_onset_for_trial(family: str, tactile_onset_s: float) -> tuple[float, float]:
    policy = woojer_tactile_latency_policy()
    requested_ms = float(policy.get("compensation_ms") or 0.0)
    if family not in {"audio_tactile", "baseline"} or requested_ms <= 0.0:
        return max(0.0, float(tactile_onset_s)), 0.0
    drive_onset_s = tactile_drive_onset_s(float(tactile_onset_s), requested_ms)
    requested_samples_ms = max(0.0, (float(tactile_onset_s) - drive_onset_s) * 1000.0)
    return round(drive_onset_s, 9), requested_samples_ms


def _apply_tactile_drive_compensation(
    data: Any,
    *,
    sample_rate: int,
    family: str,
    tactile_onset_s: float,
) -> tuple[Any, dict[str, Any]]:
    import numpy as np

    drive_onset_s, requested_ms = _tactile_drive_onset_for_trial(family, tactile_onset_s)
    policy = woojer_tactile_latency_policy()
    result = {
        "requested_compensation_ms": requested_ms,
        "applied_compensation_ms": 0.0,
        "drive_onset_s": max(0.0, float(tactile_onset_s)),
        "status": policy.get("status", ""),
        "applied": False,
        "note": "",
    }
    if family not in {"audio_tactile", "baseline"}:
        result["note"] = "no_tactile_trial"
        return data, result
    if requested_ms <= 0.0:
        result["note"] = "compensation_disabled"
        return data, result
    if sample_rate <= 0 or getattr(data, "ndim", 0) != 2 or int(data.shape[1]) < 3:
        result["note"] = "no_tactile_channel_available"
        return data, result

    nominal_sample = max(0, int(round(float(tactile_onset_s) * sample_rate)))
    drive_sample = max(0, int(round(drive_onset_s * sample_rate)))
    if drive_sample >= nominal_sample:
        result["note"] = "no_advance_after_clamp"
        return data, result
    if nominal_sample >= int(data.shape[0]):
        result["note"] = "nominal_onset_outside_trial_audio"
        return data, result

    source = np.asarray(data)
    adjusted = np.array(source, copy=True)
    tactile = np.array(source[:, 2], copy=True)
    active = np.flatnonzero(np.abs(tactile) > 1.0e-7)
    if active.size == 0:
        result["note"] = "empty_tactile_channel"
        return data, result
    if int(active[-1]) < nominal_sample:
        result["note"] = "tactile_signal_before_nominal_onset"
        return data, result

    shift = nominal_sample - drive_sample
    shifted = np.zeros_like(tactile)
    shifted[: max(0, len(tactile) - shift)] = tactile[shift:]
    adjusted[:, 2] = shifted
    applied_ms = shift / float(sample_rate) * 1000.0
    result.update(
        {
            "applied_compensation_ms": applied_ms,
            "drive_onset_s": drive_sample / float(sample_rate),
            "applied": True,
            "note": "tactile_channel_shifted_earlier",
        }
    )
    return adjusted, result


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
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
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
        looming_onset_s = _segment_looming_onset_s(row)
        tactile_onset_s = _segment_tactile_onset_s(row, looming_onset_s)
        family = _segment_family(row)
        data, tactile_compensation = _apply_tactile_drive_compensation(
            data,
            sample_rate=sample_rate,
            family=family,
            tactile_onset_s=tactile_onset_s,
        )
        target_channels = max(target_channels, int(data.shape[1]))
        clips.append(data)
        wav_infos.append(_wav_info(trial_path, sha256=actual_hash, label=trial_path.stem))
        duration_frames = int(data.shape[0])
        trial_start_sample = frame_cursor
        trial_end_sample = frame_cursor + duration_frames
        duration_s = float(duration_frames / sample_rate) if sample_rate else 0.0
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
                tactile_drive_onset_s=float(tactile_compensation.get("drive_onset_s") or tactile_onset_s),
                tactile_compensation=tactile_compensation,
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
    _mkdir(output_path.parent)
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
    tactile_drive_onset_s: float,
    tactile_compensation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trial_start_s = trial_start_sample / float(sample_rate)
    trial_end_s = trial_end_sample / float(sample_rate)
    response_window_onset_s = looming_onset_s if family in {"audio_tactile", "catch"} else tactile_onset_s
    tactile_compensation = dict(tactile_compensation or {})
    has_tactile = family in {"audio_tactile", "baseline"}
    drive_onset_s = max(0.0, float(tactile_drive_onset_s))
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
        "Tactile_Drive_Onset_S": f"{drive_onset_s:.9f}" if has_tactile else "",
        "Tactile_Drive_Onset_Sample": int(round((trial_start_s + drive_onset_s) * sample_rate)) if has_tactile else "",
        "Tactile_Latency_Compensation_Requested_ms": (
            f"{float(tactile_compensation.get('requested_compensation_ms') or 0.0):.3f}" if has_tactile else ""
        ),
        "Tactile_Latency_Compensation_Applied_ms": (
            f"{float(tactile_compensation.get('applied_compensation_ms') or 0.0):.3f}" if has_tactile else ""
        ),
        "Tactile_Latency_Compensation_Status": str(tactile_compensation.get("status") or "") if has_tactile else "",
        "Tactile_Latency_Compensation_Applied": bool(tactile_compensation.get("applied")) if has_tactile else "",
        "Tactile_Latency_Compensation_Note": str(tactile_compensation.get("note") or "") if has_tactile else "",
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
        "Session_Group_ID",
        "Part_Session_ID",
        "Part_Number",
        "Phase",
        "Phase_Label",
        "Block_Number",
        "Block_Label",
        "Global_Block_Index",
        "Part_Block_Number",
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
        "Tactile_Drive_Onset_S",
        "Tactile_Drive_Onset_Sample",
        "Tactile_Latency_Compensation_Requested_ms",
        "Tactile_Latency_Compensation_Applied_ms",
        "Tactile_Latency_Compensation_Status",
        "Tactile_Latency_Compensation_Applied",
        "Tactile_Latency_Compensation_Note",
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
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
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
    _mkdir(path.parent)
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
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as f:
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
    _mkdir(path.parent)
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
    loudness_policy = normalize_loudness_policy(package.loudness_policy)
    tactile_latency_policy = woojer_tactile_latency_policy()
    loudness_manifest_path = _loudness_manifest_path(package)
    source_wavs = [_json_ready(asdict(wav)) for wav in wavs]
    loudness_manifest = loudness_manifest_payload(
        loudness_policy,
        created_at=package.created_at,
        participant_id=package.participant_id,
        session_id=package.session_id,
        source_context="runner_session_package",
        renderer_manifest_path=str(package.render_manifest_path) if package.render_manifest_path else "",
        run_setup_manifest_path=str(package.source_run_setup_manifest_path) if package.source_run_setup_manifest_path else "",
        source_wavs=source_wavs,
        stimulus_audit_summary={
            "source_wav_count": len(source_wavs),
            "prepared_block_count": len(package.blocks),
            "execution_mode": package.execution_mode,
        },
    )
    manifest = {
        "schema": RUN_PACKAGE_SCHEMA,
        "participant_id": package.participant_id,
        "session_id": package.session_id,
        "session_group_id": package.session_group_id,
        "part_number": "" if package.part_number is None else package.part_number,
        "part_session_id": _package_part_session_id(package),
        "part_folder_name": package.part_folder_name,
        "sibling_part_manifest_paths": [str(path) for path in package.sibling_part_manifest_paths],
        "part_split_schema": package.part_split_schema,
        "created_at": package.created_at,
        "session_dir": str(package.session_dir),
        "context_dir": str(output_metadata_dir(_package_output_root(package))),
        "session_group_manifest_path": str(_session_group_manifest_path(package)) if _package_is_split_part(package) else "",
        "part_completion_status_path": str(_part_completion_status_path(package)) if _package_is_split_part(package) else "",
        "data_analytics_dir": str(_package_analytics_dir(package)),
        "execution_mode": package.execution_mode,
        "source_run_setup_manifest_path": str(package.source_run_setup_manifest_path) if package.source_run_setup_manifest_path else "",
        "source_run_setup_sha256": (
            _sha256_file(package.source_run_setup_manifest_path)
            if package.source_run_setup_manifest_path and _path_exists(package.source_run_setup_manifest_path)
            else ""
        ),
        "audio_route": {
            "preferred_device": PREFERRED_AUDIO_ROUTE,
            "channels": 3,
            "latency_s": REQUESTED_LATENCY_S,
            "blocksize": REQUESTED_BLOCKSIZE,
            "loudness_control": {
                "policy_schema": loudness_policy.get("schema", ""),
                "calibration_status": loudness_policy.get("calibration_status", ""),
                "hardware": loudness_policy.get("hardware", {}),
                "start_spl_db": loudness_policy.get("start_spl_db", ""),
                "end_spl_db": loudness_policy.get("end_spl_db", ""),
                "instruction_offset_db": loudness_policy.get("instruction_offset_db", ""),
                "estimated_full_scale_spl_db": loudness_policy.get("estimated_full_scale_spl_db", ""),
                "loudness_manifest_path": str(loudness_manifest_path),
                "warning": "Estimated SPL until verified with a headphone coupler/artificial ear.",
            },
        },
        "timing": {
            "primary_response_source": "mouse_click event log plus optional LSL marker stream",
            "stimulus_anchor": "audio_sample_zero emitted by audio callback",
            "backup_trace": "optional local digital output evidence WAV; output 4 mirrors tactile on canonical 4-channel routes; input-4 wired loopback recording is opt-in and not Woojer mechanical onset",
            "tactile_latency_compensation": _json_ready(tactile_latency_policy),
            "response_marker": {
                "channel": "tactile output",
                "gain": RESPONSE_MARKER_GAIN,
                "purpose": "sub-threshold physical QC marker, not primary RT source",
            },
            "lsl_stream": {
                "name": "PPSMarkersV2",
                "type": "Markers",
                "required": True,
                "policy": "create once before the first instruction/block, keep online until participant session end, and never destroy/recreate per block",
            },
        },
        "design_path": str(package.design_path),
        "protocol_path": str(package.protocol_path),
        "render_manifest_path": str(package.render_manifest_path) if package.render_manifest_path else "",
        "instruction_profile": _json_ready(package.instruction_profile),
        "loudness_policy": _json_ready(loudness_policy),
        "source_wavs": source_wavs,
        "blocks": [_json_ready(asdict(block)) for block in package.blocks],
        "outputs": {
            "participant_trials_csv": str(_participant_trials_csv_path(package)),
            "participant_audio_evidence_wav_pattern": str(package.session_dir / "block_XX_audio_evidence.wav"),
            "participant_wired_loopback_input4_wav_pattern": str(package.session_dir / "block_XX_wired_loopback_input4.wav"),
            "external_labrecorder_xdf": str(_external_labrecorder_xdf_path(package)),
            "external_labrecorder_group_xdf": str(_external_labrecorder_group_xdf_path(package)) if _package_is_split_part(package) else "",
            "external_labrecorder_report": str(_package_runner_log_dir(package) / "external_labrecorder_capture_report.json"),
            "external_labrecorder_group_report": str(_package_group_runner_log_dir(package) / "external_labrecorder_capture_report.json") if _package_is_split_part(package) else "",
            "verbose_events_csv": str(_verbose_events_csv_path(package)),
            "verbose_events_xdf": str(_verbose_events_xdf_path(package)),
            "lsl_markers_csv": str(_lsl_markers_csv_path(package)),
            "lsl_markers_xdf": str(_lsl_markers_xdf_path(package)),
            "trigger_dictionary_json": str(_trigger_dictionary_path(package)),
            "session_metadata_json": str(_session_metadata_path(package)),
            "loudness_manifest_json": str(loudness_manifest_path),
            "analysis_dir": str(_package_analytics_dir(package)),
            "prepared_blocks_dir": str(_package_prepared_blocks_dir(package)),
            "part_completion_status_json": str(_part_completion_status_path(package)) if _package_is_split_part(package) else "",
            "session_group_manifest_json": str(_session_group_manifest_path(package)) if _package_is_split_part(package) else "",
        },
    }
    _write_json_file(loudness_manifest_path, loudness_manifest)
    _write_json_file(package.manifest_path, manifest)


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

    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as f:
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
