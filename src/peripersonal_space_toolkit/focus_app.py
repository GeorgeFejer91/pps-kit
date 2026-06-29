"""Native participant Focus Mode launcher for prepared PPS sessions."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from html import escape
import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, TimeoutError as FutureTimeoutError
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

from .app_assets import apply_qt_app_icon, set_windows_app_user_model_id
from .analysis_catalog import (
    DATASET_KIND_POOL,
    load_analysis_dataset,
    refresh_analysis_catalog,
    selected_dataset_id_for_participant,
)
from .audio_routing import (
    NI_KOMPLETE_AUDIO_DRIVER_INSTALL_GUIDE_URL,
    NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL,
    AudioRuntimeReadiness,
    assess_audio_runtime_readiness,
    komplete_audio_asio_reconnect_steps,
    komplete_audio_asio_install_steps,
)
from .analysis_review import (
    CONDITION_LENS_TWO_BY_TWO,
    MODEL_EVIDENCE_INSUFFICIENT,
    MODEL_EVIDENCE_MIXED,
    MODEL_EVIDENCE_STRONG,
    MODEL_BEST,
    MODEL_COMPARE_ALL,
    MODEL_LABELS,
    MODEL_LINEAR,
    MODEL_LOGARITHMIC_DECAY,
    MODEL_ORDER,
    MODEL_SIGMOID,
    PART_AGGREGATION_LABELS,
    PARTS_POOLED,
    PARTS_SEPARATE,
    GROUPING_LABELS,
    GROUPING_ORDER,
    METRIC_FACILITATION,
    METRIC_LABELS,
    METRIC_MEAN_RT,
    METRIC_ORDER,
    SOURCE_FINAL,
    SOURCE_LABELS,
    SOURCE_ORDER,
    VIEW_DATA_BEHAVIOR,
    VIEW_LABELS,
    VIEW_MODEL_FITS,
    VIEW_ORDER,
    available_models_for_scope,
    artifact_rows_for_review,
    behavior_signal_counts,
    behavior_signals_for_scope,
    best_model_for_scope,
    condition_lens_button_rows,
    condition_lens_baseline_status,
    condition_lens_metric_label,
    condition_lens_observed_series,
    condition_lens_prediction_series,
    fit_row_for_scope,
    default_condition_lens,
    default_condition_model,
    load_analysis_review_data,
    model_button_rows,
    observed_points_for_scope,
    prediction_points_for_scope,
    prediction_series_for_scope,
    raw_points_for_scope,
    recording_quality_status,
    scope_comparison_row,
    scopes_for_part_mode,
)
from .focus_layout import (
    FocusLayoutProfile,
    render_focus_layout_profile,
    render_focus_style_sheet,
)
from .output_layout import _filesystem_path as _output_filesystem_path
from .output_layout import (
    output_data_analytics_dir,
    output_project_state_dir,
    output_root_for_metadata_path,
    output_runner_logs_dir,
    output_verbose_events_dir,
)
from .focus_timeline import TactileRecenterController, TactileTimelineCue, TactileTimelineState
from .runner_diary import (
    RUNNER_SETTINGS_SCHEMA,
    append_diary_entry,
    ensure_output_diary,
    find_output_diary,
    latest_diary_context,
    load_runner_settings as _load_runner_settings,
    resolve_or_create_output_project,
    runner_settings_path as _runner_settings_path,
    slugify_identifier,
    update_runner_settings as _update_runner_settings,
)
from .runner_companion import (
    DEFAULT_COMPANION_HOST,
    DEFAULT_COMPANION_PORT,
    HEALTH_SCHEMA,
    SNAPSHOT_SCHEMA,
    CompanionCommandError,
    RunnerCompanionConfig,
    RunnerCompanionService,
    build_pairing_uri,
    choose_lan_ipv4,
    generate_companion_token,
    pairing_qr_png_bytes,
)
from .mobile_phone_runtime import (
    MobileRuntimePackageError,
    build_mobile_package_list,
    build_mobile_package_manifest,
    mobile_asset_path,
    mobile_package_id,
    write_mobile_runtime_events,
)
from .session_runner import (
    DEFAULT_DASHBOARD_STATE_ROOT,
    DEFAULT_PROJECT_REGISTRY_ROOT,
    DEFAULT_RENDER_DIR,
    DEFAULT_SESSION_ROOT,
    EXTERNAL_LABRECORDER_SCOPE_PART,
    EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP,
    SessionCaptureOptions,
    SessionRunnerController,
    WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
    WIRED_LOOPBACK_OFF,
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    claim_prepared_session,
    find_latest_dashboard_run_setup,
    load_last_experiment_pointer,
    load_run_package,
    next_segment_participant,
    prepare_segment_run_package,
    prepared_session_manifest_current_status,
    prepared_session_asset_status,
    prepared_session_asset_statuses,
    record_experiment_activity,
    record_prepared_session_queue,
    segment_run_setup_participants,
    normalize_wired_loopback_mode,
    _timeline_tactile_events,
    _timeline_trial_segments,
)
from .timing_schedule import BlockEventSchedule
from .preload_inventory import load_preload_inventory
from .profile_memory import (
    BRIDGE_MANIFEST_FILENAME,
    OUTPUT_DIARY_FILENAME,
    append_output_diary_event,
    active_output_folder,
    bridge_manifest_path,
    build_profile_catalog,
    existing_bridge_manifest_path,
    existing_output_diary_path,
    load_runner_settings as load_profile_runner_settings,
    output_diary_path,
    prepare_acquisition_folder,
    profile_participant_ids_from_entry,
    resolve_profile_entry,
    update_runner_settings as update_profile_runner_settings,
)
from .runtime_paths import repo_root
from .tactile_calibration import (
    CALIBRATION_SCHEMA,
    CONFIRMATION_REQUIRED_CLEAN_CATCHES,
    CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
    PROTOCOL_NAME as TACTILE_CALIBRATION_PROTOCOL_NAME,
    TACTILE_OUTPUT_34_MAX_PERCENT,
    TactileCalibrationRunner,
    VALID_RESPONSE_END_MS,
    VALID_RESPONSE_START_MS,
    load_latest_calibration,
    save_calibration_attempt,
)


DEFAULT_FOCUS_PROFILE_DESIGN_PATH = DEFAULT_DASHBOARD_STATE_ROOT / "focus_profile_runner_design.json"
DEFAULT_FOCUS_LAYOUT_PROFILE = render_focus_layout_profile(1120, 720)
FOCUS_STYLE_SHEET = render_focus_style_sheet(DEFAULT_FOCUS_LAYOUT_PROFILE)
STUDY5_PROFILE_ID = "study5_box_breathing_pps"
DATA_COLLECTED_MARK = "[collected]"
PARTICIPANT_LEDGER_FILENAME = "participant_ledger.v1.json"
PARTICIPANT_LEDGER_SCHEMA = "pps-focus-participant-ledger.v1"
TIMELINE_LABEL_WIDTH = 58
TIMELINE_RIGHT_MARGIN = 12
TIMELINE_ROW_NAMES = ("Resp", "Type", "Noise", "SOA", "Tactile", "Clicks")
TIMELINE_MINIMUM_VISIBLE_HEIGHT = 84
TIMELINE_SEGMENT_LABEL_SKIP_WIDTH = 22
TIMELINE_REPEATED_LABEL_SKIP_WIDTH = 58
SINGLE_INSTANCE_MUTEX_NAME = "Local\\PPSExperimentRunnerSingleInstance"
SINGLE_INSTANCE_EXIT_CODE = 4
OUTPUT_12_VOLUME_PERCENT_KEY = "output_1_2_volume_percent"
OUTPUT_34_VOLUME_PERCENT_KEY = "output_3_4_volume_percent"
OUTPUT_CHANNEL_VOLUME_SETTINGS_KEY = "output_channel_volumes"
OUTPUT_CHANNEL_VOLUME_SCHEMA = "pps-output-channel-volumes.v1"
OUTPUT_TEST_AUDIO_PATH = (
    repo_root()
    / "assets"
    / "preloads"
    / STUDY5_PROFILE_ID
    / "02_looming_stimuli"
    / "looming_Pink_frontal.wav"
)
OUTPUT_TEST_TACTILE_PATH = repo_root() / "assets" / "tactile" / "runner_output_test_tactile.wav"
TACTILE_CALIBRATION_SOURCE_PULSE_PATH = repo_root() / "assets" / "tactile" / "default_tactile_cue.wav"


def _timeline_segment_value(segment: Any, key: str) -> Any:
    if isinstance(segment, dict):
        return segment.get(key, "")
    return getattr(segment, key, "")


def _timeline_segment_is_catch(segment: Any) -> bool:
    labels = (
        _timeline_segment_value(segment, "family"),
        _timeline_segment_value(segment, "trial_label"),
        _timeline_segment_value(segment, "trial_type"),
    )
    for label in labels:
        text = str(label or "").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {"catch", "catch_trial", "audio_only"}:
            return True
    return False


def _timeline_soa_display_label(segment: Any) -> str:
    if _timeline_segment_is_catch(segment):
        return "N/A"
    value = str(_timeline_segment_value(segment, "soa_ms") or _timeline_segment_value(segment, "SOA_ms") or "").strip()
    if not value:
        return "SOA"
    if value.lower().replace(".", "").replace("/", "") in {"na", "none"}:
        return "N/A"
    return f"{value} ms"


def _timeline_row_label_optional(row_name: str) -> bool:
    return str(row_name or "").strip() not in {"Type", "Noise"}


def _timeline_widget_minimum_height(profile: FocusLayoutProfile | None) -> int:
    if profile is not None and profile.screen_class == "constrained":
        return TIMELINE_MINIMUM_VISIBLE_HEIGHT
    if profile is not None and profile.compact:
        return TIMELINE_MINIMUM_VISIBLE_HEIGHT
    return max(TIMELINE_MINIMUM_VISIBLE_HEIGHT, 96)
SINGLE_INSTANCE_MESSAGE = (
    "PPS Experiment Runner is already open.\n\n"
    "Close the existing Experiment Runner window before starting another one."
)


class _RunnerSingleInstance:
    def __init__(
        self,
        *,
        acquired: bool,
        handle: Any | None = None,
        kernel32: Any | None = None,
        message: str = SINGLE_INSTANCE_MESSAGE,
    ) -> None:
        self.acquired = bool(acquired)
        self._handle = handle
        self._kernel32 = kernel32
        self.message = message

    def release(self) -> None:
        if self._handle is None or self._kernel32 is None:
            return
        try:
            self._kernel32.ReleaseMutex(self._handle)
        except Exception:
            pass
        try:
            self._kernel32.CloseHandle(self._handle)
        except Exception:
            pass
        self._handle = None


def _acquire_runner_single_instance() -> _RunnerSingleInstance:
    """Acquire the process-wide runner guard for the current Windows session."""
    if sys.platform != "win32":
        return _RunnerSingleInstance(acquired=True)
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.ReleaseMutex.argtypes = (wintypes.HANDLE,)
        kernel32.ReleaseMutex.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, True, SINGLE_INSTANCE_MUTEX_NAME)
        error_code = ctypes.get_last_error()
        if not handle:
            return _RunnerSingleInstance(
                acquired=False,
                message=(
                    "PPS Experiment Runner could not verify that no other runner is open.\n\n"
                    f"Windows error {error_code}. Close any existing runner and try again."
                ),
            )
        if error_code == 183:
            kernel32.CloseHandle(handle)
            return _RunnerSingleInstance(acquired=False)
        return _RunnerSingleInstance(acquired=True, handle=handle, kernel32=kernel32)
    except Exception as exc:
        return _RunnerSingleInstance(
            acquired=False,
            message=(
                "PPS Experiment Runner could not verify that no other runner is open.\n\n"
                f"{exc}"
            ),
        )


def _show_runner_single_instance_notice(message: str = SINGLE_INSTANCE_MESSAGE) -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            flags = 0x00000040 | 0x00010000 | 0x00040000
            ctypes.windll.user32.MessageBoxW(None, message, "PPS Experiment Runner", flags)
            return
        except Exception:
            pass
    print(message, file=sys.stderr)


def runner_settings_path(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> Path:
    return _runner_settings_path(state_root)


def load_runner_settings(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> dict[str, Any]:
    return _load_runner_settings(state_root)


def update_runner_settings(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT, **updates: Any) -> dict[str, Any]:
    return _update_runner_settings(state_root, **updates)


def current_runner_session_root(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> Path:
    settings = load_runner_settings(state_root)
    raw = str(settings.get("current_output_project_root") or settings.get("session_root") or "").strip()
    if raw:
        return Path(raw).expanduser()
    diary_raw = str(settings.get("diary_path") or "").strip()
    if diary_raw:
        diary_path = Path(diary_raw).expanduser()
        if diary_path.is_file():
            return output_root_for_metadata_path(diary_path)
    return DEFAULT_SESSION_ROOT


def current_runner_diary_path(state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT) -> Path | None:
    settings = load_runner_settings(state_root)
    raw = str(settings.get("diary_path") or "").strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_file():
            return path
    return find_output_diary(current_runner_session_root(state_root))


def set_runner_session_root(
    session_root: Path,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    *,
    diary_path: Path | None = None,
    experiment_name: str = "",
    profile_id: str = "",
    participant_id: str = "",
    capture_options: dict[str, Any] | None = None,
) -> Path:
    root = Path(session_root).expanduser().resolve()
    os.makedirs(_output_filesystem_path(root), exist_ok=True)
    diary = diary_path or find_output_diary(root)
    update_runner_settings(
        state_root,
        session_root=str(root),
        current_output_project_root=str(root),
        diary_path="" if diary is None else str(Path(diary).resolve()),
        last_experiment_name=experiment_name,
        last_profile_id=profile_id,
        last_participant_id=participant_id,
        last_capture_options=capture_options or {},
    )
    return root


def remember_runner_context(
    *,
    session_root: Path | None = None,
    diary_path: Path | None = None,
    experiment_name: str = "",
    profile_id: str = "",
    participant_id: str = "",
    capture_options: dict[str, Any] | None = None,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
) -> dict[str, Any]:
    root = Path(session_root).expanduser().resolve() if session_root is not None else current_runner_session_root(state_root).resolve()
    diary = diary_path or find_output_diary(root)
    return update_runner_settings(
        state_root,
        session_root=str(root),
        current_output_project_root=str(root),
        diary_path="" if diary is None else str(Path(diary).resolve()),
        last_experiment_name=experiment_name,
        last_profile_id=profile_id,
        last_participant_id=participant_id,
        last_capture_options=capture_options or {},
    )


def create_runner_output_project(
    parent_dir: Path,
    state_root: Path = DEFAULT_DASHBOARD_STATE_ROOT,
    *,
    experiment_identifier: str = "PPS experiment",
    profile_id: str = "",
    participant_id: str = "",
    capture_options: dict[str, Any] | None = None,
) -> Path:
    resolution = resolve_or_create_output_project(
        parent_dir,
        experiment_identifier=experiment_identifier,
        timestamp=time.strftime("%Y%m%d_%H%M%S"),
    )
    set_runner_session_root(
        resolution.root,
        state_root=state_root,
        diary_path=resolution.diary_path,
        experiment_name=experiment_identifier,
        profile_id=profile_id,
        participant_id=participant_id,
        capture_options=capture_options,
    )
    return resolution.root


def create_timestamped_output_environment(parent_dir: Path, session_name: str) -> tuple[Path, Path, str]:
    parent = Path(parent_dir).expanduser().resolve()
    if not os.path.isdir(_output_filesystem_path(parent)):
        raise ValueError("Choose an existing output folder before initiating a new data collection environment.")
    slug = slugify_identifier(session_name, fallback="")
    if not slug:
        raise ValueError("Enter a session name before initiating a new data collection environment.")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    root = parent / f"{slug}_{stamp}"
    suffix = 2
    while os.path.exists(_output_filesystem_path(root)):
        root = parent / f"{slug}_{stamp}_{suffix}"
        suffix += 1
    os.makedirs(_output_filesystem_path(root), exist_ok=False)
    diary = ensure_output_diary(root, session_name)
    return root, diary, slug


def _capture_options_payload(capture_options: SessionCaptureOptions | dict[str, Any] | None) -> dict[str, Any]:
    if capture_options is None:
        return _default_focus_capture_options().as_dict()
    if isinstance(capture_options, SessionCaptureOptions):
        return capture_options.as_dict()
    return dict(capture_options)


def _default_focus_capture_options() -> SessionCaptureOptions:
    return SessionCaptureOptions(
        wired_loopback_mode=WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
        start_external_labrecorder=True,
    )


OUTPUT_VOLUME_SLIDER_SCALE = 1000
OUTPUT_VOLUME_PERCENT_DECIMALS = 3
OUTPUT_VOLUME_PERCENT_STEP = 0.001

def _coerce_volume_percent(value: Any, *, default: float = 100.0, maximum: float = 100.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if not math.isfinite(number):
        number = float(default)
    maximum_value = max(0.0, float(maximum))
    return round(max(0.0, min(maximum_value, number)), OUTPUT_VOLUME_PERCENT_DECIMALS)


def _coerce_tactile_output_percent(value: Any, *, default: float = TACTILE_OUTPUT_34_MAX_PERCENT) -> float:
    return _coerce_volume_percent(value, default=default, maximum=TACTILE_OUTPUT_34_MAX_PERCENT)


def _volume_percent_to_slider_value(value: Any, *, maximum: float = 100.0) -> int:
    return int(round(_coerce_volume_percent(value, maximum=maximum) * OUTPUT_VOLUME_SLIDER_SCALE))


def _slider_value_to_volume_percent(value: Any, *, maximum: float = 100.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(maximum) * OUTPUT_VOLUME_SLIDER_SCALE
    if not math.isfinite(number):
        number = float(maximum) * OUTPUT_VOLUME_SLIDER_SCALE
    return _coerce_volume_percent(number / OUTPUT_VOLUME_SLIDER_SCALE, maximum=maximum)


def _output_volume_gain(percent: Any, *, maximum: float = 100.0) -> float:
    return _coerce_volume_percent(percent, maximum=maximum) / 100.0


def _output_channel_volume_payload(output_12_percent: Any, output_34_percent: Any) -> dict[str, Any]:
    output_12 = _coerce_volume_percent(output_12_percent)
    output_34 = _coerce_tactile_output_percent(output_34_percent)
    return {
        "schema": OUTPUT_CHANNEL_VOLUME_SCHEMA,
        "output_1_2_percent": output_12,
        "output_3_4_percent": output_34,
        "output_1_2_linear_gain": _output_volume_gain(output_12),
        "output_3_4_linear_gain": _output_volume_gain(output_34, maximum=TACTILE_OUTPUT_34_MAX_PERCENT),
        "output_3_4_max_percent": TACTILE_OUTPUT_34_MAX_PERCENT,
    }


def _load_output_channel_volume_percentages(state_root: Path | None = None) -> tuple[float, float]:
    settings = load_runner_settings(DEFAULT_DASHBOARD_STATE_ROOT if state_root is None else state_root)
    grouped = settings.get(OUTPUT_CHANNEL_VOLUME_SETTINGS_KEY)
    grouped = grouped if isinstance(grouped, dict) else {}
    output_12 = grouped.get(
        "output_1_2_percent",
        settings.get(OUTPUT_12_VOLUME_PERCENT_KEY, settings.get("audio_volume_percent", 100)),
    )
    output_34 = grouped.get(
        "output_3_4_percent",
        settings.get(OUTPUT_34_VOLUME_PERCENT_KEY, settings.get("tactile_volume_percent", 100)),
    )
    return _coerce_volume_percent(output_12), _coerce_tactile_output_percent(output_34)


def _persist_output_channel_volumes(
    output_12_percent: Any,
    output_34_percent: Any,
    *,
    state_root: Path | None = None,
) -> dict[str, Any]:
    output_12 = _coerce_volume_percent(output_12_percent)
    output_34 = _coerce_tactile_output_percent(output_34_percent)
    return update_runner_settings(
        DEFAULT_DASHBOARD_STATE_ROOT if state_root is None else state_root,
        **{
            OUTPUT_12_VOLUME_PERCENT_KEY: output_12,
            OUTPUT_34_VOLUME_PERCENT_KEY: output_34,
            OUTPUT_CHANNEL_VOLUME_SETTINGS_KEY: _output_channel_volume_payload(output_12, output_34),
        },
    )


def initiate_data_collection_environment(
    *,
    parent_folder: Path,
    profile_id: str,
    session_name: str,
    participant_id: str = "P001",
    capture_options: SessionCaptureOptions | dict[str, Any] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Create a folder-local data collection environment and preload one participant."""
    parent = Path(parent_folder).expanduser()
    if not os.path.isdir(_output_filesystem_path(parent)):
        raise ValueError("Choose an existing output folder before initiating a new data collection environment.")
    profile = str(profile_id or "").strip()
    if not profile:
        raise ValueError("Choose an experiment profile before initiating a new data collection environment.")
    label = str(session_name or "").strip()
    session_slug = slugify_identifier(label, fallback="")
    if not session_slug:
        raise ValueError("Enter a session name before initiating a new data collection environment.")
    participant = str(participant_id or "").strip() or "P001"
    capture_payload = _capture_options_payload(capture_options)

    _emit_launcher_progress(
        progress_callback,
        "Loading selected profile",
        phase="profile_inventory",
        detail=profile,
        current=0,
        total=4,
    )
    _controller, _design, run_setup_manifest_path = _materialize_profile_run_setup(
        profile,
        progress_callback=progress_callback,
    )
    entry = resolve_profile_entry(
        profile,
        registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        session_root=active_output_folder(state_root=DEFAULT_DASHBOARD_STATE_ROOT, fallback=DEFAULT_SESSION_ROOT),
        inventory=load_preload_inventory(repo_root()),
    )
    source_project_dir = Path(str(entry.get("project_dir") or "")).expanduser()
    if not source_project_dir.is_dir():
        source_project_dir = Path(run_setup_manifest_path).resolve().parents[1]

    _emit_launcher_progress(
        progress_callback,
        "Creating output environment",
        phase="environment_folder",
        detail=str(parent),
        current=1,
        total=4,
    )
    environment_root, diary_path, session_slug = create_timestamped_output_environment(parent, label)
    set_runner_session_root(
        environment_root,
        diary_path=diary_path,
        experiment_name=label,
        profile_id=profile,
        participant_id=participant,
        capture_options=capture_payload,
    )
    update_runner_settings(
        DEFAULT_DASHBOARD_STATE_ROOT,
        active_session_name=label,
        active_output_parent_folder=str(parent.resolve()),
        active_environment_created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    _emit_launcher_progress(
        progress_callback,
        "Copying profile snapshot",
        phase="profile_snapshot",
        detail=str(source_project_dir),
        current=2,
        total=4,
    )
    bridge = prepare_acquisition_folder(
        profile_entry=entry,
        source_project_dir=source_project_dir,
        output_folder=environment_root,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        participant_id=participant,
        capture_options=capture_payload,
    )
    append_diary_entry(
        diary_path,
        "data_collection_environment_initiated",
        participant_id=participant,
        experiment_name=label,
        profile_id=profile,
        run_setup_manifest_path=str(bridge.get("run_setup_manifest_path") or ""),
        capture_options=capture_payload,
        payload={
            "parent_folder": str(parent.resolve()),
            "environment_root": str(environment_root),
            "bridge_manifest_path": str(bridge.get("bridge_manifest_path") or ""),
            "session_name": label,
            "session_slug": session_slug,
        },
    )
    append_output_diary_event(
        "data_collection_environment_initiated",
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        output_folder=environment_root,
        profile_id=profile,
        profile_kind=str(entry.get("kind") or ""),
        dashboard_project_id=str(entry.get("dashboard_project_id") or ""),
        participant_id=participant,
        bridge_manifest_path=str(bridge.get("bridge_manifest_path") or ""),
        session_name=label,
    )

    _emit_launcher_progress(
        progress_callback,
        "Preparing first participant",
        phase="participant_package",
        detail=participant,
        current=3,
        total=4,
    )
    prepared = prepare_profile_audio_assets(
        profile,
        [participant],
        session_root=environment_root,
        progress_callback=progress_callback,
    )
    _emit_launcher_progress(
        progress_callback,
        "Data collection environment ready",
        phase="environment_ready",
        detail=str(environment_root),
        current=4,
        total=4,
    )
    return {
        "environment_root": str(environment_root),
        "diary_path": str(diary_path),
        "bridge": bridge,
        "prepared_participants": prepared,
        "profile_id": profile,
        "session_name": label,
        "participant_id": participant,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run native PPS Focus Mode from a prepared session manifest.")
    parser.add_argument("--session-manifest", type=Path, help="Path to local_data/sessions/.../session_manifest.json.")
    parser.add_argument("--last-experiment", action="store_true", help="Bypass the gate and open the last launchable dashboard experiment.")
    parser.add_argument("--latest-dashboard-setup", action="store_true", help="Bypass the gate, prepare, and open the newest prepared dashboard Segment 6 setup.")
    parser.add_argument("--launcher", action="store_true", help="Open the resume/data-collection environment gate explicitly. This is also the no-argument default.")
    parser.add_argument("--profile", default="", help="Load a finished study/profile preload directly in the runner, for example study5_box_breathing_pps.")
    parser.add_argument("--participant-id", default="", help="Participant ID to materialize when using --latest-dashboard-setup.")
    parser.add_argument("--manual-start", action="store_true", help="Open the runner window but wait for Start Run before playback.")
    parser.add_argument("--no-companion", action="store_true", help="Do not start the LAN phone companion service.")
    parser.add_argument("--companion-host", default=DEFAULT_COMPANION_HOST, help="Host interface for the phone companion service.")
    parser.add_argument("--companion-port", type=int, default=DEFAULT_COMPANION_PORT, help="LAN port for the phone companion service.")
    parser.add_argument("--companion-advertise-ip", default="", help="Explicit IP address to put in the phone companion QR code.")
    parser.add_argument("--no-lsl", action="store_true", help="Do not create live LSL marker outlets for this run.")
    parser.add_argument("--no-internal-xdf", action="store_true", help="Do not write the local events.xdf mirror.")
    parser.add_argument("--no-analysis-csv", action="store_true", help="Do not write immediate analysis CSV outputs.")
    parser.add_argument("--no-backup-recording", action="store_true", help="Do not write the optional fail-safe local recording WAV.")
    labrecorder_group = parser.add_mutually_exclusive_group()
    labrecorder_group.add_argument(
        "--external-labrecorder",
        dest="external_labrecorder",
        action="store_true",
        default=True,
        help="Start runner-owned LabRecorder RCS capture after LSL outlets are online and before playback.",
    )
    labrecorder_group.add_argument(
        "--no-external-labrecorder",
        dest="external_labrecorder",
        action="store_false",
        help="Open Focus Mode with full-session LabRecorder XDF unchecked.",
    )
    parser.add_argument("--labrecorder-cli", type=Path, default=None, help="Optional explicit path to LabRecorderCLI.exe used to find the LabRecorder bundle.")
    parser.add_argument("--labrecorder-stream-timeout-s", type=float, default=10.0, help="Seconds to wait for runner LSL streams before starting LabRecorder.")
    parser.add_argument("--labrecorder-startup-s", type=float, default=1.0, help="Seconds to wait after LabRecorder starts before playback may continue.")
    parser.add_argument("--labrecorder-stop-timeout-s", type=float, default=8.0, help="Seconds to wait for LabRecorder to close the XDF at session end.")
    parser.add_argument(
        "--wired-loopback",
        choices=[WIRED_LOOPBACK_OFF, WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY],
        default=WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
        help="Record a wired analog loopback route, or pass off to open the checkbox unchecked.",
    )
    topup_group = parser.add_mutually_exclusive_group()
    topup_group.add_argument(
        "--enable-missed-trial-topup",
        dest="enable_missed_trial_topup",
        action="store_true",
        default=True,
        help="Prepare and play one final missed-trial top-up block without an additional prompt.",
    )
    topup_group.add_argument(
        "--no-missed-trial-topup",
        dest="enable_missed_trial_topup",
        action="store_false",
        help="Open Focus Mode with missed-trial top-up unchecked.",
    )
    parser.add_argument("--validation-screenshot", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--validation-auto-close-ms", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--validation-windowed", action="store_true", help=argparse.SUPPRESS)
    return parser


def _require_qt() -> dict[str, Any]:
    try:
        from PySide6.QtCore import QEvent, QLocale, QPoint, QSize, QTimer, Qt, QUrl, Signal
        from PySide6.QtGui import QBrush, QColor, QCursor, QDesktopServices, QFont, QFontDatabase, QFontMetrics, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDoubleSpinBox,
            QFileDialog,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QLabel,
            QHeaderView,
            QLineEdit,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QScrollArea,
            QSizePolicy,
            QSlider,
            QSplitter,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
            QToolButton,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise RuntimeError("Install the GUI extra to run native Focus Mode: pip install -e .[gui]") from exc
    return {
        "QApplication": QApplication,
        "QCheckBox": QCheckBox,
        "QBrush": QBrush,
        "QColor": QColor,
        "QComboBox": QComboBox,
        "QCursor": QCursor,
        "QDesktopServices": QDesktopServices,
        "QDialog": QDialog,
        "QDoubleSpinBox": QDoubleSpinBox,
        "QEvent": QEvent,
        "QLocale": QLocale,
        "QFileDialog": QFileDialog,
        "QFrame": QFrame,
        "QFont": QFont,
        "QGridLayout": QGridLayout,
        "QHBoxLayout": QHBoxLayout,
        "QHeaderView": QHeaderView,
        "QFontDatabase": QFontDatabase,
        "QFontMetrics": QFontMetrics,
        "QIcon": QIcon,
        "QKeySequence": QKeySequence,
        "QLabel": QLabel,
        "QLineEdit": QLineEdit,
        "QMessageBox": QMessageBox,
        "QPainter": QPainter,
        "QPainterPath": QPainterPath,
        "QPen": QPen,
        "QPixmap": QPixmap,
        "QPoint": QPoint,
        "QSize": QSize,
        "QProgressBar": QProgressBar,
        "QPushButton": QPushButton,
        "QScrollArea": QScrollArea,
        "QShortcut": QShortcut,
        "Signal": Signal,
        "QSizePolicy": QSizePolicy,
        "QSlider": QSlider,
        "QSplitter": QSplitter,
        "QTabWidget": QTabWidget,
        "QTableWidget": QTableWidget,
        "QTableWidgetItem": QTableWidgetItem,
        "QTextEdit": QTextEdit,
        "QTimer": QTimer,
        "QToolButton": QToolButton,
        "QUrl": QUrl,
        "QVBoxLayout": QVBoxLayout,
        "QWidget": QWidget,
        "Qt": Qt,
    }


def _standard_window_flags(q: dict[str, Any]) -> Any:
    window_type = q["Qt"].WindowType
    return (
        window_type.Window
        | window_type.WindowTitleHint
        | window_type.WindowSystemMenuHint
        | window_type.WindowMinimizeButtonHint
        | window_type.WindowMaximizeButtonHint
        | window_type.WindowCloseButtonHint
    )


def _enable_standard_window_controls(q: dict[str, Any], dialog: Any) -> None:
    dialog.setWindowFlags(_standard_window_flags(q))
    if hasattr(dialog, "setSizeGripEnabled"):
        dialog.setSizeGripEnabled(True)


def _screen_bounded_dialog_size(
    q: dict[str, Any],
    *,
    width: int,
    height: int,
    min_width: int,
    min_height: int,
) -> tuple[int, int, int, int]:
    app = q["QApplication"].instance()
    screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return width, height, min_width, min_height
    geometry = screen.availableGeometry()
    max_width = max(min_width, int(geometry.width()) - 48)
    max_height = max(min_height, int(geometry.height()) - 64)
    return (
        min(width, max_width),
        min(height, max_height),
        min(min_width, max_width),
        min(min_height, max_height),
    )


def _center_dialog_on_primary_screen(q: dict[str, Any], dialog: Any) -> None:
    app = q["QApplication"].instance()
    screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return
    geometry = screen.availableGeometry()
    x = int(geometry.left() + max(0, (geometry.width() - dialog.width()) / 2))
    y = int(geometry.top() + max(0, (geometry.height() - dialog.height()) / 2))
    dialog.move(x, y)


def _widget_screen_center(widget: Any) -> tuple[int, int, str]:
    try:
        center = widget.mapToGlobal(widget.rect().center())
        x = int(center.x())
        y = int(center.y())
        if x or y:
            ratio = 1.0
            try:
                screen = widget.screen()
                ratio = float(screen.devicePixelRatio()) if screen is not None else 1.0
            except Exception:
                ratio = 1.0
            if ratio > 1.01:
                return int(round(x * ratio)), int(round(y * ratio)), f"qt_map_to_global_dpr_{ratio:g}"
            return x, y, "qt_map_to_global"
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(widget.winId())
            rect = wintypes.RECT()
            if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width = int(rect.right - rect.left)
                height = int(rect.bottom - rect.top)
                if width > 0 and height > 0:
                    return int(rect.left + width / 2), int(rect.top + height / 2), "win32_get_window_rect"
        except Exception:
            pass
    return 0, 0, "unresolved"


def _widget_win32_client_center(widget: Any) -> tuple[int, int, int]:
    if sys.platform != "win32":
        return 0, 0, 0
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())
        rect = wintypes.RECT()
        if hwnd and ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(rect)):
            width = max(0, int(rect.right - rect.left))
            height = max(0, int(rect.bottom - rect.top))
            return hwnd, int(width / 2), int(height / 2)
    except Exception:
        pass
    return 0, 0, 0


def _send_validation_external_mouse_click(
    *,
    x: int,
    y: int,
    backend: str,
    python_path: str | None = None,
    hwnd: int | None = None,
    client_x: int | None = None,
    client_y: int | None = None,
    window_message_only: bool = False,
    timeout_s: float = 2.0,
) -> dict[str, Any]:
    """Send a validation click from a helper Python process."""
    import subprocess

    resolved_backend = str(backend or "").strip().lower()
    helper_python = str(python_path or os.environ.get("PPS_FOCUS_VALIDATION_EXTERNAL_CLICK_PYTHON") or "").strip()
    if not helper_python:
        return {"ok": False, "backend": resolved_backend, "error": "external_click_python_not_configured"}
    if resolved_backend not in {"pynput", "win32", "pyautogui"}:
        return {"ok": False, "backend": resolved_backend, "error": f"unsupported_backend:{resolved_backend}"}
    helper_code = r'''
import ctypes
import json
import sys
import time


def _set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _send_win32_click(x, y):
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(x), int(y))
    time.sleep(0.05)

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", ctypes.c_ulong), ("union", INPUTUNION)]

    extra = ctypes.c_ulong(0)

    def _send(flags):
        item = INPUT(0, INPUTUNION(mi=MOUSEINPUT(0, 0, 0, flags, 0, ctypes.pointer(extra))))
        sent = user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(item))
        if int(sent) != 1:
            raise OSError("SendInput failed")

    _send(0x0002)
    time.sleep(0.03)
    _send(0x0004)


def _send_win32_message_click(hwnd, client_x, client_y):
    user32 = ctypes.windll.user32
    lparam = (int(client_y) << 16) | (int(client_x) & 0xFFFF)
    user32.PostMessageW(int(hwnd), 0x0200, 0, lparam)
    time.sleep(0.02)
    user32.PostMessageW(int(hwnd), 0x0201, 0x0001, lparam)
    time.sleep(0.03)
    user32.PostMessageW(int(hwnd), 0x0202, 0, lparam)


backend = sys.argv[1].strip().lower()
x = int(round(float(sys.argv[2])))
y = int(round(float(sys.argv[3])))
hwnd = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].strip() else 0
client_x = int(round(float(sys.argv[5]))) if len(sys.argv) > 5 and sys.argv[5].strip() else 0
client_y = int(round(float(sys.argv[6]))) if len(sys.argv) > 6 and sys.argv[6].strip() else 0
message_only = sys.argv[7].strip().lower() in {"1", "true", "yes"} if len(sys.argv) > 7 else False
result = {"ok": False, "backend": backend, "x": x, "y": y, "hwnd": hwnd or ""}
try:
    _set_dpi_aware()
    raw_ok = False
    raw_error = ""
    if message_only:
        raw_error = "raw_input_skipped_for_window_message_only"
    elif backend == "pynput":
        try:
            from pynput.mouse import Button, Controller

            mouse = Controller()
            mouse.position = (x, y)
            time.sleep(0.05)
            mouse.press(Button.left)
            time.sleep(0.03)
            mouse.release(Button.left)
            raw_ok = True
        except Exception as exc:
            raw_error = str(exc)
    elif backend == "win32":
        try:
            _send_win32_click(x, y)
            raw_ok = True
        except Exception as exc:
            raw_error = str(exc)
    elif backend == "pyautogui":
        try:
            import pyautogui

            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0
            pyautogui.click(x, y)
            raw_ok = True
        except Exception as exc:
            raw_error = str(exc)
    else:
        raise ValueError(f"unsupported backend: {backend}")
    message_ok = False
    message_error = ""
    if message_only and hwnd and client_x >= 0 and client_y >= 0:
        try:
            _send_win32_message_click(hwnd, client_x, client_y)
            message_ok = True
        except Exception as exc:
            message_error = str(exc)
    result["raw_input_sent"] = raw_ok
    result["window_message_sent"] = message_ok
    if raw_error:
        result["raw_input_error"] = raw_error
    if message_error:
        result["window_message_error"] = message_error
    result["ok"] = bool(raw_ok or message_ok)
except Exception as exc:
    result["error"] = str(exc)
print(json.dumps(result, sort_keys=True))
raise SystemExit(0 if result["ok"] else 2)
'''
    startupinfo = None
    creationflags = 0
    if sys.platform == "win32":
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        except Exception:
            startupinfo = None
            creationflags = 0
    try:
        completed = subprocess.run(
            [
                helper_python,
                "-c",
                helper_code,
                resolved_backend,
                str(int(x)),
                str(int(y)),
                str(int(hwnd or 0)),
                str(int(client_x or 0)),
                str(int(client_y or 0)),
                "1" if window_message_only else "0",
            ],
            capture_output=True,
            text=True,
            timeout=max(0.5, float(timeout_s)),
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
    except Exception as exc:
        return {"ok": False, "backend": resolved_backend, "python": helper_python, "x": int(x), "y": int(y), "error": str(exc)}
    stdout = (completed.stdout or "").strip()
    payload: dict[str, Any] = {}
    if stdout:
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except Exception:
            payload = {"stdout": stdout}
    payload.setdefault("backend", resolved_backend)
    payload.setdefault("x", int(x))
    payload.setdefault("y", int(y))
    payload["python"] = helper_python
    payload["returncode"] = int(completed.returncode)
    if completed.stderr:
        payload["stderr"] = completed.stderr.strip()
    payload["ok"] = bool(payload.get("ok")) and completed.returncode == 0
    return payload


def _force_foreground_window(widget: Any) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        hwnd = int(widget.winId())
        if not hwnd:
            return
        user32 = ctypes.windll.user32
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        swp_flags = 0x0001 | 0x0002 | 0x0040  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, swp_flags)  # HWND_TOPMOST
        user32.BringWindowToTop(hwnd)
        user32.SetActiveWindow(hwnd)
        user32.SetForegroundWindow(hwnd)
        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, swp_flags)  # HWND_NOTOPMOST
    except Exception:
        pass


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def _float_or_none(value: Any) -> float | None:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _package_duration(package: Any) -> float:
    return sum(float(block.duration_s) for block in package.blocks)


def _format_file_size(num_bytes: float) -> str:
    value = max(0.0, float(num_bytes or 0.0))
    if value >= 1024**3:
        return f"{value / 1024**3:.1f} GB"
    if value >= 1024**2:
        return f"{value / 1024**2:.1f} MB"
    if value >= 1024:
        return f"{value / 1024:.1f} KB"
    return f"{int(round(value))} B"


def _estimated_backup_recording_size(package: Any) -> str:
    total_bytes = 0.0
    for block in getattr(package, "blocks", []) or []:
        metadata = _block_metadata(block)
        duration_s = max(0.0, float(getattr(block, "duration_s", 0.0) or 0.0))
        sample_rate_value = _float_or_none(metadata.get("sample_rate_hz") or metadata.get("sample_rate"))
        channel_value = _float_or_none(metadata.get("channels"))
        sample_rate = int(sample_rate_value) if sample_rate_value is not None and sample_rate_value > 0 else 48_000
        channels = int(channel_value) if channel_value is not None and channel_value > 0 else 3
        total_bytes += duration_s * max(1, sample_rate) * max(1, channels) * 4
        total_bytes += 44
    return _format_file_size(total_bytes)


def _backup_recording_checkbox_text(package: Any) -> str:
    return (
        "Save additional fail-safe local recording\n"
        f"(LSL logging remains standard; estimated extra file: ~{_estimated_backup_recording_size(package)})"
    )


def _wired_loopback_checkbox_text() -> str:
    return (
        "Record wired loopback from Input 4\n"
        "(Output 4 always mirrors tactile; patch Output 4 to Input 4)"
    )


def _external_labrecorder_checkbox_text() -> str:
    return (
        "Record full-session LabRecorder XDF\n"
        "(Runner starts LabRecorder after LSL appears and before playback)"
    )


def _audio_dependency_dialog_html(readiness: AudioRuntimeReadiness) -> str:
    detail_items = "".join(f"<li>{escape(item)}</li>" for item in readiness.details)
    unvalidated_items = "".join(f"<li>{escape(item)}</li>" for item in readiness.unvalidated_output_devices)
    steps = komplete_audio_asio_reconnect_steps() if readiness.komplete_asio_driver_registered else komplete_audio_asio_install_steps()
    step_items = "".join(f"<li>{escape(step)}</li>" for step in steps)
    sounddevice = escape(readiness.sounddevice_version or "not detected")
    hostapi_state = "visible" if readiness.asio_hostapi_present else "not visible"
    if readiness.komplete_asio_driver_registered:
        heading = "Komplete Audio 6 MK2 interface not detected"
        intro = (
            "PPS found the installed native <b>Komplete Audio ASIO Driver</b>, but the Komplete interface is not "
            "connected or ready yet."
        )
        driver_state = "installed/registered"
        status_text = "Driver installed; Komplete Audio 6 MK2 is not exposing a 3+ channel output."
    else:
        heading = "Komplete Audio ASIO driver required"
        intro = (
            "PPS needs the native <b>Komplete Audio ASIO Driver</b> so left, right, "
            "and tactile output share one synchronized multichannel device."
        )
        driver_state = "not registered"
        status_text = "Komplete Audio ASIO driver is missing or no 3+ channel output is visible."
    unvalidated_html = (
        "<p><b>Detected 3+ output alternatives for pretesting only:</b></p>"
        f"<ul>{unvalidated_items}</ul>"
        if unvalidated_items
        else ""
    )
    return (
        f"<h2>{heading}</h2>"
        f"<p>{intro}</p>"
        f"<p><b>Status:</b> {escape(status_text)}</p>"
        f"<p><b>Komplete ASIO driver:</b> {driver_state}<br>"
        f"<b>sounddevice:</b> {sounddevice}<br><b>ASIO host API:</b> {hostapi_state}</p>"
        f"<ul>{detail_items}</ul>"
        f"{unvalidated_html}"
        "<p><b>What to do next:</b></p>"
        f"<ol>{step_items}</ol>"
        "<p>"
        f"Driver page: <a href=\"{NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL}\">{NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL}</a><br>"
        f"Install guide: <a href=\"{NI_KOMPLETE_AUDIO_DRIVER_INSTALL_GUIDE_URL}\">{NI_KOMPLETE_AUDIO_DRIVER_INSTALL_GUIDE_URL}</a>"
        "</p>"
        "<p>After the installer finishes and the interface is reconnected, click "
        "<b>Retry Audio Detection</b>. PPS will automatically select "
        "<b>Komplete Audio ASIO Driver</b> when it appears.</p>"
    )


def _audio_device_index_from_label(label: str) -> int | None:
    text = str(label or "").strip()
    if not text.startswith("[") or "]" not in text:
        return None
    try:
        return int(text[1 : text.index("]")])
    except Exception:
        return None


def _audio_output_count_from_label(label: str) -> int:
    text = str(label or "")
    marker = "outputs 1-"
    if marker in text:
        tail = text.split(marker, 1)[1].lstrip()
        digits = ""
        for char in tail:
            if char.isdigit():
                digits += char
            elif digits:
                break
        if digits:
            return int(digits)
    out_marker = " out"
    if out_marker in text:
        prefix = text.split(out_marker, 1)[0].rstrip()
        trailing_digits: list[str] = []
        for char in reversed(prefix):
            if char.isdigit():
                trailing_digits.append(char)
            elif trailing_digits:
                break
        digits = "".join(reversed(trailing_digits))
        if digits:
            return int(digits)
    return 0


def _audio_device_name_from_label(label: str) -> str:
    text = str(label or "").strip()
    if text.startswith("[") and "]" in text:
        text = text[text.index("]") + 1 :].strip()
    for marker in (
        " (Windows ",
        " (ASIO",
        " (WASAPI",
        " (WDM-KS",
        " (MME",
        " (DirectSound",
        " (Core Audio",
        " (ALSA",
        " (JACK",
        " (OSS",
        " (PulseAudio",
    ):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
            break
    return text or "Selected audio device"


def _audio_device_display_name_from_label(label: str) -> str:
    name = _audio_device_name_from_label(label)
    if len(name) > 44:
        name = f"{name[:41]}..."
    return name.strip() or "Selected audio device"


def _manual_audio_channel_option_label(device_label: str, output_index: int) -> str:
    return f"{_audio_device_display_name_from_label(device_label)} - Output {output_index}"


def _manual_audio_channel_options(device_labels: tuple[str, ...]) -> list[tuple[int, int, str, str]]:
    options: list[tuple[int, int, str, str]] = []
    for device_label in device_labels:
        device_index = _audio_device_index_from_label(device_label)
        output_count = _audio_output_count_from_label(device_label)
        if device_index is None or output_count <= 0:
            continue
        for output_index in range(1, output_count + 1):
            option_label = _manual_audio_channel_option_label(device_label, output_index)
            options.append((int(device_index), int(output_index), str(device_label), option_label))
    return options


def _manual_channel_summary(channels: tuple[int, int, int]) -> str:
    return f"left=Output {channels[0]}, right=Output {channels[1]}, tactile=Output {channels[2]}"


def _unvalidated_audio_route_message(label: str, channels: tuple[int, int, int]) -> str:
    return (
        "User-selected system audio route accepted: "
        f"{label}. PPS will use {_manual_channel_summary(channels)}. "
        "This setup is not calibrated for PPS timing; run independent channel and latency tests before using it for "
        "time-sensitive data collection."
    )


def _clear_dialog_audio_selection_if_validated_route_ready(readiness: AudioRuntimeReadiness) -> None:
    if readiness.publication_ready and os.environ.get("PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG") == "1":
        os.environ.pop("PPS_AUDIO_DEVICE_INDEX", None)
        os.environ.pop("PPS_AUDIO_OUTPUT_CHANNELS", None)
        os.environ.pop("PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG", None)


def _confirm_unvalidated_audio_route(
    q: dict[str, Any],
    *,
    parent: Any,
    label: str,
    channels: tuple[int, int, int],
) -> bool:
    message_box = q["QMessageBox"](parent)
    message_box.setObjectName("unvalidatedAudioRouteConfirmDialog")
    _enable_standard_window_controls(q, message_box)
    message_box.setWindowTitle("Continue Without Komplete Interface")
    message_box.setIcon(q["QMessageBox"].Icon.Warning)
    message_box.setText("Continue without the Komplete Audio interface?")
    message_box.setInformativeText(
        _unvalidated_audio_route_message(label, channels)
        + " Do not treat this route as calibrated participant timing evidence until channel identity and latency "
        "have been tested independently."
    )
    continue_button = message_box.addButton("Continue Without Komplete Interface", q["QMessageBox"].ButtonRole.AcceptRole)
    cancel_button = message_box.addButton("Cancel", q["QMessageBox"].ButtonRole.RejectRole)
    message_box.setDefaultButton(cancel_button)
    message_box.exec()
    return message_box.clickedButton() == continue_button


def _show_audio_dependency_dialog(
    q: dict[str, Any],
    *,
    parent: Any | None = None,
    readiness: AudioRuntimeReadiness | None = None,
) -> bool:
    """Show a repair dialog and return True once native Komplete ASIO is ready."""
    current: dict[str, Any] = {
        "readiness": readiness or assess_audio_runtime_readiness(),
        "accepted_unvalidated": False,
        "unvalidated_label": "",
    }
    if current["readiness"].publication_ready:
        return True

    dialog = q["QDialog"](parent)
    dialog.setObjectName("audioDependencyDialog")
    _enable_standard_window_controls(q, dialog)
    dialog.setWindowTitle("Audio Driver Required")
    dialog_width, dialog_height, min_width, min_height = _screen_bounded_dialog_size(
        q,
        width=860,
        height=680,
        min_width=680,
        min_height=500,
    )
    dialog.resize(dialog_width, dialog_height)
    dialog.setMinimumSize(min_width, min_height)
    dialog.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))
    _prepare_validation_window_placement(q, dialog)

    layout = q["QVBoxLayout"](dialog)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(6)

    instructions = q["QLabel"]()
    instructions.setObjectName("audioDependencyInstructions")
    instructions.setWordWrap(True)
    instructions.setMinimumWidth(0)
    instructions.setOpenExternalLinks(True)
    instructions.setTextInteractionFlags(q["Qt"].TextInteractionFlag.TextBrowserInteraction)
    instructions.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Preferred)
    instructions_host = q["QWidget"]()
    instructions_host.setMinimumWidth(0)
    instructions_layout = q["QVBoxLayout"](instructions_host)
    instructions_layout.setContentsMargins(0, 0, 8, 0)
    instructions_layout.setSpacing(0)
    instructions_layout.addWidget(instructions)
    instructions_layout.addStretch(1)
    instructions_scroll = q["QScrollArea"]()
    instructions_scroll.setObjectName("audioDependencyInstructionsScroll")
    instructions_scroll.setWidgetResizable(True)
    instructions_scroll.setFrameShape(q["QFrame"].Shape.NoFrame)
    instructions_scroll.setFixedHeight(max(80, min(100, int(dialog_height * 0.15))))
    instructions_scroll.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Fixed)
    instructions_scroll.setWidget(instructions_host)
    layout.addWidget(instructions_scroll)

    status = q["QLabel"]("")
    status.setObjectName("audioDependencyStatus")
    status.setWordWrap(True)
    status.setMinimumWidth(0)
    status.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Maximum)
    status.setMaximumHeight(64)
    status.setAlignment(q["Qt"].AlignmentFlag.AlignTop | q["Qt"].AlignmentFlag.AlignLeft)
    layout.addWidget(status)

    unvalidated_label = q["QLabel"](
        "<b>Unvalidated pretest route</b><br>"
        "Choose left, right, and tactile device-channel entries.<br>"
        "You may reuse a channel. Timing is unvalidated.<br>"
        "Verify channel identity and latency before time-sensitive use."
    )
    unvalidated_label.setObjectName("unvalidatedAudioRouteWarning")
    unvalidated_label.setWordWrap(True)
    unvalidated_label.setMinimumWidth(0)
    unvalidated_label.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Maximum)
    unvalidated_label.setMaximumHeight(76)
    unvalidated_label.setAlignment(q["Qt"].AlignmentFlag.AlignTop | q["Qt"].AlignmentFlag.AlignLeft)
    layout.addWidget(unvalidated_label)

    channel_controls_host = q["QWidget"]()
    channel_controls_host.setObjectName("unvalidatedAudioChannelControls")
    channel_controls_host.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Fixed)
    channel_controls = q["QGridLayout"]()
    channel_controls.setContentsMargins(0, 0, 0, 0)
    channel_controls.setHorizontalSpacing(8)
    channel_controls.setVerticalSpacing(4)
    left_channel_combo = q["QComboBox"]()
    left_channel_combo.setObjectName("unvalidatedLeftChannelCombo")
    right_channel_combo = q["QComboBox"]()
    right_channel_combo.setObjectName("unvalidatedRightChannelCombo")
    tactile_channel_combo = q["QComboBox"]()
    tactile_channel_combo.setObjectName("unvalidatedTactileChannelCombo")
    manual_channel_widgets: list[Any] = []
    for column, (label, combo) in enumerate(
        (
            ("Left (default 1)", left_channel_combo),
            ("Right (default 2)", right_channel_combo),
            ("Tactile (default 3)", tactile_channel_combo),
        )
    ):
        label_widget = q["QLabel"](label)
        manual_channel_widgets.append(label_widget)
        manual_channel_widgets.append(combo)
        combo.setMinimumContentsLength(8)
        combo.setFixedWidth(170)
        combo.setSizeAdjustPolicy(q["QComboBox"].SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        channel_controls.addWidget(label_widget, 0, column)
        channel_controls.addWidget(combo, 1, column)
        channel_controls.setColumnStretch(column, 0)
    channel_controls.setColumnStretch(3, 1)
    use_unvalidated = q["QPushButton"]("Accept Pretest Settings")
    use_unvalidated.setObjectName("useUnvalidatedAudioRouteButton")
    use_unvalidated.setToolTip(
        "Continue without the Komplete interface for pretesting only; this route is not calibrated PPS timing hardware."
    )
    use_unvalidated.setMinimumWidth(180)
    use_unvalidated.setMaximumWidth(230)
    use_unvalidated.setSizePolicy(q["QSizePolicy"].Policy.Fixed, q["QSizePolicy"].Policy.Fixed)
    channel_controls.addWidget(use_unvalidated, 2, 0, 1, 3, q["Qt"].AlignmentFlag.AlignLeft)
    channel_controls_host.setLayout(channel_controls)
    layout.addWidget(channel_controls_host)

    buttons = q["QHBoxLayout"]()
    open_driver = q["QPushButton"]("Open Native Instruments Driver Page")
    open_driver.setObjectName("openKompleteDriverPageButton")
    open_guide = q["QPushButton"]("Open Install Guide")
    open_guide.setObjectName("openKompleteInstallGuideButton")
    retry = q["QPushButton"]("Retry Audio Detection")
    retry.setObjectName("retryAudioDetectionButton")
    close = q["QPushButton"]("Close")
    close.setObjectName("closeAudioDependencyDialogButton")
    buttons.addWidget(open_driver)
    buttons.addWidget(open_guide)
    buttons.addStretch(1)
    buttons.addWidget(retry)
    buttons.addWidget(close)
    layout.addLayout(buttons)

    def _render() -> None:
        ready = current["readiness"]
        _clear_dialog_audio_selection_if_validated_route_ready(ready)
        instructions.setText(_audio_dependency_dialog_html(ready))
        current["channel_options"] = _manual_audio_channel_options(tuple(ready.unvalidated_output_devices))
        show_unvalidated = bool(current["channel_options"]) and not ready.publication_ready
        unvalidated_label.setVisible(show_unvalidated)
        channel_controls_host.setVisible(show_unvalidated)
        for widget in manual_channel_widgets:
            widget.setVisible(show_unvalidated)
        use_unvalidated.setVisible(show_unvalidated)
        use_unvalidated.setEnabled(show_unvalidated)
        _refresh_manual_channel_dropdowns()
        if ready.publication_ready:
            status.setText("Komplete Audio ASIO Driver detected. PPS will use it automatically.")
        else:
            status.setText("Waiting for Komplete Audio ASIO Driver. Reconnect the interface, then retry detection.")

    def _refresh_manual_channel_dropdowns() -> None:
        options = list(current.get("channel_options", []))
        previous = [
            left_channel_combo.currentData(),
            right_channel_combo.currentData(),
            tactile_channel_combo.currentData(),
        ]
        first_device = int(options[0][0]) if options else None
        for combo_index, combo in enumerate((left_channel_combo, right_channel_combo, tactile_channel_combo)):
            combo.blockSignals(True)
            combo.clear()
            for option in options:
                combo.addItem(option[3], option)
            target = previous[combo_index] if previous[combo_index] in options else None
            if target is None and first_device is not None:
                default_output = combo_index + 1
                target = next(
                    (option for option in options if option[0] == first_device and option[1] == default_output),
                    options[0] if options else None,
                )
            if target is not None:
                item_index = combo.findData(target)
                combo.setCurrentIndex(item_index if item_index >= 0 else 0)
            selected = combo.currentData()
            if isinstance(selected, tuple) and len(selected) >= 3:
                combo.setToolTip(_manual_audio_channel_option_label(str(selected[2]), int(selected[1])))
            else:
                combo.setToolTip(str(combo.currentText() or ""))
            combo.blockSignals(False)

    def _retry() -> None:
        current["readiness"] = assess_audio_runtime_readiness()
        _render()
        if current["readiness"].publication_ready:
            dialog.accept()

    def _use_unvalidated() -> None:
        selections = [
            left_channel_combo.currentData(),
            right_channel_combo.currentData(),
            tactile_channel_combo.currentData(),
        ]
        if not all(isinstance(selection, tuple) and len(selection) >= 3 for selection in selections):
            status.setText("Choose left, right, and tactile device channels before continuing.")
            return
        device_indices = {int(selection[0]) for selection in selections}
        if len(device_indices) != 1:
            status.setText("Choose three channels from the same audio device; PPS opens one output stream per run.")
            return
        device_index = int(selections[0][0])
        label = _audio_device_display_name_from_label(str(selections[0][2]))
        channels = (
            int(selections[0][1]),
            int(selections[1][1]),
            int(selections[2][1]),
        )
        if not _confirm_unvalidated_audio_route(q, parent=dialog, label=label, channels=channels):
            status.setText("System audio pretest route was not selected.")
            return
        os.environ["PPS_AUDIO_DEVICE_INDEX"] = str(int(device_index))
        os.environ["PPS_AUDIO_OUTPUT_CHANNELS"] = ",".join(str(channel) for channel in channels)
        os.environ["PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG"] = "1"
        current["accepted_unvalidated"] = True
        current["unvalidated_label"] = label
        status.setText(_unvalidated_audio_route_message(label, channels))
        dialog.accept()

    open_driver.clicked.connect(lambda: q["QDesktopServices"].openUrl(q["QUrl"](NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL)))
    open_guide.clicked.connect(lambda: q["QDesktopServices"].openUrl(q["QUrl"](NI_KOMPLETE_AUDIO_DRIVER_INSTALL_GUIDE_URL)))
    retry.clicked.connect(_retry)
    use_unvalidated.clicked.connect(_use_unvalidated)
    close.clicked.connect(dialog.reject)
    _render()
    _center_dialog_on_primary_screen(q, dialog)
    accepted = dialog.exec() == q["QDialog"].DialogCode.Accepted
    return accepted and (current["readiness"].publication_ready or bool(current["accepted_unvalidated"]))


def _block_metadata(block: Any) -> dict[str, Any]:
    metadata = getattr(block, "metadata", {}) or {}
    return metadata if isinstance(metadata, dict) else {}


def _metadata_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _is_topup_block(block: Any) -> bool:
    return _metadata_truthy(_block_metadata(block).get("is_topup_block"))


def _block_part_key(block: Any) -> str:
    metadata = _block_metadata(block)
    value = metadata.get("part_number", metadata.get("topup_part_number", metadata.get("phase_index", "")))
    text = str(value or "").strip()
    if not text:
        return "1"
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def _part_display_label(part_key: str) -> str:
    text = str(part_key or "").strip()
    try:
        return f"Part {int(float(text)):02d}"
    except ValueError:
        return f"Part {text}" if text else "Part --"


def _part_button_label(part_key: str) -> str:
    text = str(part_key or "").strip()
    try:
        return f"Part {int(float(text))}"
    except ValueError:
        return f"Part {text}" if text else "Part"


def _part_key_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def _part_sort_key(value: Any) -> tuple[int, str]:
    text = _part_key_text(value)
    try:
        return (int(float(text)), text)
    except ValueError:
        return (999, text)


def _compact_run_block_label(block: Any) -> str:
    text = str(getattr(block, "label", "") or f"Block {getattr(block, 'index', '')}").strip()
    return text if len(text) <= 24 else f"{text[:21]}..."


def _package_part_keys(package: Any) -> list[str]:
    keys: list[str] = []
    for block in getattr(package, "blocks", []) or []:
        if _is_topup_block(block):
            continue
        part_key = _block_part_key(block)
        if part_key not in keys:
            keys.append(part_key)
    return keys or ["1"]


def _run_plan_items(package: Any, *, include_topup_slots: bool) -> list[dict[str, Any]]:
    standard_blocks = [block for block in getattr(package, "blocks", []) if not _is_topup_block(block)]
    items: list[dict[str, Any]] = []
    display_index = 0
    part_block_counts: dict[str, int] = {}
    for index, block in enumerate(standard_blocks):
        part_key = _block_part_key(block)
        display_index += 1
        part_block_counts[part_key] = int(part_block_counts.get(part_key, 0)) + 1
        part_block_number = part_block_counts[part_key]
        items.append(
            {
                "kind": "standard",
                "part_key": part_key,
                "number": display_index,
                "part_block_number": part_block_number,
                "display_label": f"Block {part_block_number}",
                "label": _compact_run_block_label(block),
                "block_index": int(getattr(block, "index", display_index) or display_index),
                "trial_count": int(getattr(block, "trial_count", 0) or 0),
                "duration_s": float(getattr(block, "duration_s", 0.0) or 0.0),
            }
        )
        next_block = standard_blocks[index + 1] if index + 1 < len(standard_blocks) else None
        if include_topup_slots and (next_block is None or _block_part_key(next_block) != part_key):
            display_index += 1
            part_block_counts[part_key] = int(part_block_counts.get(part_key, 0)) + 1
            part_block_number = part_block_counts[part_key]
            items.append(
                {
                    "kind": "topup",
                    "part_key": part_key,
                    "number": display_index,
                    "part_block_number": part_block_number,
                    "display_label": f"Block {part_block_number} top-up",
                    "label": "Top-up if needed",
                }
            )
    return items


def _run_plan_total(package: Any, *, include_topup_slots: bool) -> int:
    return len(_run_plan_items(package, include_topup_slots=include_topup_slots))


def _run_plan_text(package: Any, *, include_topup_slots: bool) -> str:
    items = _run_plan_items(package, include_topup_slots=include_topup_slots)
    if not items:
        return "No blocks prepared"
    lines: list[str] = []
    part_order: list[str] = []
    for item in items:
        part_key = str(item["part_key"])
        if part_key not in part_order:
            part_order.append(part_key)
    for part_key in part_order:
        part_items = [item for item in items if item["part_key"] == part_key]
        entries = ", ".join(f"{item.get('part_block_number', item['number'])} {item['label']}" for item in part_items)
        lines.append(f"{_part_display_label(part_key)}: {entries}")
    return "\n".join(lines)


def _run_plan_compact_text(package: Any, *, include_topup_slots: bool) -> str:
    items = _run_plan_items(package, include_topup_slots=include_topup_slots)
    if not items:
        return "No blocks prepared"
    lines: list[str] = []
    part_order: list[str] = []
    for item in items:
        part_key = str(item["part_key"])
        if part_key not in part_order:
            part_order.append(part_key)
    for part_key in part_order:
        part_items = [item for item in items if item["part_key"] == part_key]
        standard_count = sum(1 for item in part_items if item.get("kind") == "standard")
        topup_count = sum(1 for item in part_items if item.get("kind") == "topup")
        parts = [f"{standard_count} block{'s' if standard_count != 1 else ''}"]
        if topup_count:
            parts.append("top-up if needed")
        lines.append(f"{_part_display_label(part_key)}: {' + '.join(parts)}")
    return "\n".join(lines)


def _payload_display_block_index(payload: dict[str, Any]) -> int:
    for key in ("display_block_index", "play_order_index", "block_play_order_index", "block_index"):
        try:
            value = int(float(str(payload.get(key)).strip()))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def _payload_display_block_count(payload: dict[str, Any], fallback: int) -> int:
    for key in ("display_block_count", "block_count"):
        try:
            value = int(float(str(payload.get(key)).strip()))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return max(0, int(fallback or 0))


def _short_folder_label(path: Path) -> str:
    parts = path.parts
    if len(parts) >= 3:
        return str(Path(*parts[-3:]))
    return str(path)


def _instruction_profile_summary(package: Any) -> str:
    profile = getattr(package, "instruction_profile", {}) or {}
    slots = profile.get("slots", []) if isinstance(profile, dict) else []
    enabled = [slot for slot in slots if isinstance(slot, dict) and slot.get("enabled") and slot.get("path")]
    return f"{len(enabled)} clip(s) preloaded" if enabled else "No preloaded clips"


INSTRUCTION_SLOT_ALIASES = {
    "before_block": "before_each_block",
    "pre_block": "before_each_block",
    "after_block": "after_each_block",
    "post_block": "after_each_block",
    "interim": "between_conditions",
}

INSTRUCTION_SLOT_STYLES = {
    "before_experiment": {"label": "General", "color": "#5b6ee1"},
    "before_each_block": {"label": "Pre-block", "color": "#2f7d57"},
    "after_each_block": {"label": "Post-block", "color": "#b7791f"},
    "between_conditions": {"label": "Interim", "color": "#1f7a8c"},
    "after_experiment": {"label": "Finish", "color": "#9f3a60"},
}

INSTRUCTION_SLOT_ORDER = (
    "before_experiment",
    "before_each_block",
    "after_each_block",
    "between_conditions",
    "after_experiment",
)


def _canonical_instruction_slot(slot: Any) -> str:
    text = str(slot or "").strip()
    return INSTRUCTION_SLOT_ALIASES.get(text, text)


def _instruction_slot_display(slot: str, fallback: str = "") -> str:
    canonical = _canonical_instruction_slot(slot)
    style = INSTRUCTION_SLOT_STYLES.get(canonical, {})
    return str(style.get("label") or fallback or canonical.replace("_", " ").title())


def _instruction_slot_color(slot: str) -> str:
    canonical = _canonical_instruction_slot(slot)
    style = INSTRUCTION_SLOT_STYLES.get(canonical, {})
    return str(style.get("color") or "#647067")


def _instruction_slots(package: Any) -> list[dict[str, Any]]:
    profile = getattr(package, "instruction_profile", {}) or {}
    raw_slots = profile.get("slots", []) if isinstance(profile, dict) else []
    if isinstance(raw_slots, dict):
        raw_slots = list(raw_slots.values())
    slots: list[dict[str, Any]] = []
    for item in raw_slots if isinstance(raw_slots, list) else []:
        if not isinstance(item, dict):
            continue
        slot = _canonical_instruction_slot(item.get("slot"))
        if not slot:
            continue
        payload = dict(item)
        payload["slot"] = slot
        payload["display_label"] = _instruction_slot_display(slot, str(item.get("label") or ""))
        payload["color"] = _instruction_slot_color(slot)
        slots.append(payload)
    order = {slot: index for index, slot in enumerate(INSTRUCTION_SLOT_ORDER)}
    return sorted(slots, key=lambda item: (order.get(str(item.get("slot") or ""), 99), str(item.get("display_label") or "")))


def _enabled_instruction_slots(package: Any) -> list[dict[str, Any]]:
    return [
        slot
        for slot in _instruction_slots(package)
        if bool(slot.get("enabled")) and str(slot.get("path") or "").strip()
    ]


def _trial_type_color(label: Any, family: Any = "") -> str:
    text = f"{label} {family}".strip().lower().replace("-", "_").replace(" ", "_")
    if "audio_tactile" in text or "audiotactile" in text:
        return "#dcefeb"
    if "baseline" in text:
        return "#f4e2b8"
    if "catch" in text:
        return "#e4e7eb"
    if "top_up" in text or "topup" in text:
        return "#f0dddd"
    return "#e3ead8"


def _topup_draft_item_label(item: dict[str, Any], *, compact: bool = False) -> str:
    block = str(item.get("block_number") or "").strip()
    trial = str(item.get("trial_number") or "").strip()
    row = str(item.get("respiratory_phase") or item.get("row_label") or "").strip()
    trial_type = str(item.get("trial_type") or item.get("family") or "Trial").strip()
    soa = str(item.get("soa_ms") or "").strip()
    prefix = " ".join(part for part in (f"B{block}" if block else "", f"T{trial}" if trial else "") if part)
    if compact:
        return " | ".join(part for part in (prefix, row, trial_type) if part)
    soa_text = f"SOA {soa}" if soa else ""
    return " | ".join(part for part in (prefix, row, trial_type, soa_text) if part)


def _chip(q: dict[str, Any], text: str, *, tone: str = "neutral") -> Any:
    label = q["QLabel"](text)
    label.setObjectName("chip")
    label.setProperty("tone", tone)
    label.setWordWrap(True)
    return label


def _panel(q: dict[str, Any], title: str, *, profile: FocusLayoutProfile | None = None) -> tuple[Any, Any]:
    frame = q["QFrame"]()
    frame.setObjectName("panel")
    layout = q["QVBoxLayout"](frame)
    margin = profile.panel_margin if profile is not None else DEFAULT_FOCUS_LAYOUT_PROFILE.panel_margin
    spacing = profile.panel_spacing if profile is not None else DEFAULT_FOCUS_LAYOUT_PROFILE.panel_spacing
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)
    if title:
        heading = q["QLabel"](title)
        heading.setObjectName("sectionTitle")
        input_min_height = profile.input_min_height if profile is not None else DEFAULT_FOCUS_LAYOUT_PROFILE.input_min_height
        heading.setMinimumHeight(max(16, input_min_height - 8))
        layout.addWidget(heading)
    return frame, layout


def _create_focus_mode_dialog(q: dict[str, Any], owner: Any) -> Any:
    class FocusModeDialog(q["QDialog"]):
        def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802 - Qt API
            try:
                mouse_press = q["QEvent"].Type.MouseButtonPress
            except AttributeError:
                mouse_press = q["QEvent"].MouseButtonPress
            if event.type() == mouse_press:
                handler = getattr(owner, "_handle_response_mouse_press", None)
                if callable(handler):
                    handler(watched, event)
            return False

        def _restore_locked_geometry(self) -> None:
            if not bool(getattr(owner, "_experiment_window_locked", False)):
                return
            restore = getattr(owner, "_restore_locked_experiment_window_geometry", None)
            if callable(restore):
                restore()

        def moveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().moveEvent(event)
            self._restore_locked_geometry()

        def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            schedule_clamp = getattr(owner, "_schedule_experiment_control_splitter_clamp", None)
            if callable(schedule_clamp):
                schedule_clamp()
            self._restore_locked_geometry()

    return FocusModeDialog()


def _subtitle(q: dict[str, Any], text: str) -> Any:
    label = q["QLabel"](text)
    label.setObjectName("sectionSubtitle")
    return label


def _metric_row(q: dict[str, Any], label: str, value: str) -> Any:
    row = q["QWidget"]()
    layout = q["QHBoxLayout"](row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    key = q["QLabel"](label)
    key.setObjectName("metricLabel")
    val = q["QLabel"](value)
    val.setObjectName("metricValue")
    val.setWordWrap(True)
    layout.addWidget(key)
    layout.addWidget(val, 1)
    return row


def _field_row(q: dict[str, Any], label: str, widget: Any) -> Any:
    row = q["QWidget"]()
    layout = q["QHBoxLayout"](row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    key = q["QLabel"](label)
    key.setObjectName("metricLabel")
    layout.addWidget(key)
    layout.addWidget(widget, 1)
    return row


def _output_volume_slider_row(
    q: dict[str, Any],
    *,
    label: str,
    value: float,
    object_name: str,
    tooltip: str,
    on_change: Callable[[float], None],
    maximum_percent: float = 100.0,
) -> tuple[Any, Any, Any]:
    max_percent = max(0.0, float(maximum_percent))

    class VolumePercentSpinBox(q["QDoubleSpinBox"]):
        def __init__(self) -> None:
            super().__init__()
            self.lineEdit().installEventFilter(self)

        def valueFromText(self, text: str) -> float:  # noqa: N802 - Qt override
            clean = str(text or "").replace("%", "").strip().replace(",", ".")
            try:
                value = float(clean)
            except ValueError:
                return float(self.value())
            return _coerce_volume_percent(value, maximum=max_percent) if math.isfinite(value) else float(self.value())

        def textFromValue(self, value: float) -> str:  # noqa: N802 - Qt override
            return f"{_coerce_volume_percent(value, maximum=max_percent):.{OUTPUT_VOLUME_PERCENT_DECIMALS}f}"

        def _commit_text_value(self) -> None:
            text = self.lineEdit().text().replace("%", "").strip().replace(",", ".")
            try:
                value = float(text)
            except ValueError:
                self.interpretText()
                return
            if math.isfinite(value):
                self.setValue(_coerce_volume_percent(value, maximum=max_percent))
            else:
                self.interpretText()

        def eventFilter(self, watched: Any, event: Any) -> bool:  # noqa: N802 - Qt override
            if (
                watched is self.lineEdit()
                and event.type() == q["QEvent"].Type.KeyPress
                and event.key() in (q["Qt"].Key.Key_Return, q["Qt"].Key.Key_Enter)
            ):
                self._commit_text_value()
                event.accept()
                return True
            return super().eventFilter(watched, event)

        def keyPressEvent(self, event: Any) -> None:  # noqa: N802 - Qt override
            if event.key() in (q["Qt"].Key.Key_Return, q["Qt"].Key.Key_Enter):
                self._commit_text_value()
                event.accept()
                return
            super().keyPressEvent(event)

    row = q["QWidget"]()
    layout = q["QHBoxLayout"](row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    key = q["QLabel"](label)
    key.setObjectName("metricLabel")
    slider = q["QSlider"](q["Qt"].Orientation.Horizontal)
    slider.setObjectName(object_name)
    slider.setRange(0, int(round(max_percent * OUTPUT_VOLUME_SLIDER_SCALE)))
    slider.setSingleStep(1)
    slider.setPageStep(10)
    slider.setTickInterval(100)
    slider.setToolTip(tooltip)
    slider.setValue(_volume_percent_to_slider_value(value, maximum=max_percent))
    slider.setMinimumWidth(120)
    percent = VolumePercentSpinBox()
    percent.setObjectName(object_name.replace("Slider", "PercentBox"))
    percent.setRange(0.0, max_percent)
    percent.setDecimals(OUTPUT_VOLUME_PERCENT_DECIMALS)
    percent.setSingleStep(OUTPUT_VOLUME_PERCENT_STEP)
    percent.setSuffix("%")
    percent.setLocale(q["QLocale"].c())
    percent.setKeyboardTracking(False)
    percent.setValue(_coerce_volume_percent(value, maximum=max_percent))
    percent.setMinimumWidth(78)
    percent.setMaximumWidth(96)
    percent.setToolTip(tooltip)
    layout.addWidget(key)
    layout.addWidget(slider, 1)
    layout.addWidget(percent)

    def _slider_changed(changed: int) -> None:
        percent_value = _slider_value_to_volume_percent(changed, maximum=max_percent)
        previous = percent.blockSignals(True)
        percent.setValue(percent_value)
        percent.blockSignals(previous)
        on_change(percent_value)

    def _percent_changed(changed: float) -> None:
        percent_value = _coerce_volume_percent(changed, maximum=max_percent)
        slider_value = _volume_percent_to_slider_value(percent_value, maximum=max_percent)
        previous = slider.blockSignals(True)
        slider.setValue(slider_value)
        slider.blockSignals(previous)
        on_change(percent_value)

    slider.valueChanged.connect(_slider_changed)
    percent.valueChanged.connect(_percent_changed)
    return row, slider, percent


def _format_tactile_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(number):
        return ""
    return f"{number:.3f}%"


def _create_tactile_calibration_timeline_widget(q: dict[str, Any]) -> Any:
    class TactileCalibrationTimelineWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            self.events: list[dict[str, Any]] = []
            self.max_events = 60
            self.setMinimumHeight(74)
            self.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Fixed)

        def set_events(self, events: list[dict[str, Any]], *, max_events: int) -> None:
            self.events = [dict(event) for event in events]
            self.max_events = max(1, int(max_events or 1))
            self.update()

        def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().paintEvent(event)
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                rect = self.rect()
                painter.fillRect(rect, q["QColor"]("#f7fafc"))
                left = 12
                right = max(left + 1, rect.width() - 12)
                mid_y = rect.height() // 2
                painter.setPen(q["QPen"](q["QColor"]("#b7c3d0"), 2))
                painter.drawLine(left, mid_y, right, mid_y)
                for event_record in self.events:
                    try:
                        index = int(event_record.get("trial_index") or 0)
                    except Exception:
                        index = 0
                    if index <= 0:
                        continue
                    frac = min(1.0, max(0.0, (index - 1) / max(1, self.max_events - 1)))
                    x = int(round(left + frac * (right - left)))
                    is_catch = bool(event_record.get("is_catch"))
                    outcome = str(event_record.get("trial_outcome") or "").strip().lower()
                    current = bool(event_record.get("current"))
                    if "false_alarm" in outcome:
                        color = "#b42318"
                    elif outcome in {"hit", "correct_reject"}:
                        color = "#16794c"
                    elif outcome in {"miss", "catch_response_out_of_window"}:
                        color = "#d47c00"
                    elif is_catch:
                        color = "#64748b"
                    else:
                        color = "#2563eb"
                    radius = 6 if current else 4
                    painter.setBrush(q["QBrush"](q["QColor"](color)))
                    painter.setPen(q["QPen"](q["QColor"]("#ffffff"), 1))
                    painter.drawEllipse(q["QPoint"](x, mid_y), radius, radius)
                painter.setPen(q["QPen"](q["QColor"]("#475569"), 1))
                painter.drawText(12, rect.height() - 8, f"0 / {self.max_events} event cap")
            finally:
                painter.end()

    return TactileCalibrationTimelineWidget()


def _create_tactile_calibration_monitor_dialog(q: dict[str, Any], owner: Any, participant: str) -> Any:
    class TactileCalibrationMonitorDialog(q["QDialog"]):
        def __init__(self) -> None:
            super().__init__(owner.dialog)
            self.setWindowTitle(f"Tactile Calibration Monitor - {participant}")
            self.setModal(False)
            self.setObjectName("tactileCalibrationMonitor")
            self.events: list[dict[str, Any]] = []
            self.current_row_by_trial: dict[int, int] = {}
            self._accepted_assay = False
            self.resize(760, 620)

            root = q["QVBoxLayout"](self)
            root.setContentsMargins(14, 14, 14, 14)
            root.setSpacing(10)

            self.status_label = q["QLabel"]("Preparing tactile threshold assay")
            self.status_label.setObjectName("sectionTitle")
            self.status_label.setWordWrap(True)
            root.addWidget(self.status_label)

            self.target_panel = q["QFrame"]()
            self.target_panel.setObjectName("tactileCalibrationTargetPanel")
            target_layout = q["QVBoxLayout"](self.target_panel)
            target_layout.setContentsMargins(8, 8, 8, 8)
            target_layout.setSpacing(8)
            target_layout.addWidget(_subtitle(q, "Participant Response Target"))
            self.target_button = _create_response_target_button(q, DEFAULT_FOCUS_LAYOUT_PROFILE)
            self.target_button.setObjectName("tactileCalibrationTargetButton")
            self.target_button.setEnabled(True)
            self.target_button.clicked.connect(lambda _checked=False: owner._record_tactile_calibration_target_click("calibration_monitor_target"))
            target_layout.addWidget(self.target_button, 0, q["Qt"].AlignmentFlag.AlignHCenter)
            self.warning_label = q["QLabel"]("")
            self.warning_label.setObjectName("tactileCalibrationWarning")
            self.warning_label.setWordWrap(True)
            self.warning_label.setStyleSheet("color: #991b1b; font-weight: 700;")
            self.warning_label.setVisible(False)
            target_layout.addWidget(self.warning_label)
            root.addWidget(self.target_panel)

            metrics = q["QFrame"]()
            metrics_layout = q["QGridLayout"](metrics)
            metrics_layout.setContentsMargins(0, 0, 0, 0)
            metrics_layout.setHorizontalSpacing(12)
            metrics_layout.setVerticalSpacing(6)
            self.intensity_label = q["QLabel"]("Intensity: --")
            self.window_label = q["QLabel"]("Response window: --")
            self.reversal_label = q["QLabel"]("Reversals: 0")
            self.response_label = q["QLabel"]("Last response: --")
            self.confirmation_hits_label = q["QLabel"](
                f"Final hits: 0/{CONFIRMATION_REQUIRED_CONSECUTIVE_HITS}"
            )
            self.confirmation_catches_label = q["QLabel"](
                f"Clean catches: 0/{CONFIRMATION_REQUIRED_CLEAN_CATCHES}"
            )
            for label in (
                self.intensity_label,
                self.window_label,
                self.reversal_label,
                self.response_label,
                self.confirmation_hits_label,
                self.confirmation_catches_label,
            ):
                label.setObjectName("metricValue")
                label.setWordWrap(True)
            self.intensity_bar = q["QProgressBar"]()
            self.intensity_bar.setRange(0, int(round(TACTILE_OUTPUT_34_MAX_PERCENT * OUTPUT_VOLUME_SLIDER_SCALE)))
            self.intensity_bar.setTextVisible(True)
            self.intensity_bar.setValue(0)
            metrics_layout.addWidget(self.intensity_label, 0, 0)
            metrics_layout.addWidget(self.window_label, 0, 1)
            metrics_layout.addWidget(self.reversal_label, 1, 0)
            metrics_layout.addWidget(self.response_label, 1, 1)
            metrics_layout.addWidget(self.confirmation_hits_label, 2, 0)
            metrics_layout.addWidget(self.confirmation_catches_label, 2, 1)
            metrics_layout.addWidget(self.intensity_bar, 3, 0, 1, 2)
            root.addWidget(metrics)

            self.timeline = _create_tactile_calibration_timeline_widget(q)
            root.addWidget(self.timeline)

            self.table = q["QTableWidget"](0, 6)
            self.table.setObjectName("tactileCalibrationTrialTable")
            self.table.setHorizontalHeaderLabels(["#", "Phase", "Level", "Pulse", "Response", "Outcome"])
            self.table.setEditTriggers(q["QTableWidget"].EditTrigger.NoEditTriggers)
            self.table.verticalHeader().setVisible(False)
            self.table.horizontalHeader().setSectionResizeMode(q["QHeaderView"].ResizeMode.Stretch)
            root.addWidget(self.table, 1)

            buttons = q["QHBoxLayout"]()
            buttons.addStretch(1)
            self.abort_button = q["QPushButton"]("Abort")
            self.abort_button.setObjectName("dangerButton")
            self.abort_button.clicked.connect(lambda _checked=False: owner._abort_tactile_calibration())
            self.close_button = q["QPushButton"]("Close")
            self.close_button.setEnabled(False)
            self.close_button.clicked.connect(self._close_or_continue)
            buttons.addWidget(self.abort_button)
            buttons.addWidget(self.close_button)
            root.addLayout(buttons)

        def _close_or_continue(self) -> None:
            if self._accepted_assay:
                owner._return_from_successful_tactile_calibration()
            else:
                self.accept()

        def _set_catch_warning(self, active: bool, text: str = "") -> None:
            if active:
                self.target_panel.setStyleSheet(
                    "QFrame#tactileCalibrationTargetPanel { "
                    "border: 2px solid #b3261e; border-radius: 6px; background: #fff1f2; }"
                )
                self.warning_label.setText(text or "Only press when you feel the tactile pulse.")
                self.warning_label.setVisible(True)
            else:
                self.target_panel.setStyleSheet("")
                self.warning_label.setText("")
                self.warning_label.setVisible(False)

        def update_confirmation(self, payload: dict[str, Any]) -> None:
            def _count(key: str) -> int:
                try:
                    return max(0, int(payload.get(key) or 0))
                except Exception:
                    return 0

            hits = _count("confirmation_consecutive_hits")
            catches = _count("confirmation_clean_catches")
            self.confirmation_hits_label.setText(
                f"Final hits: {hits}/{CONFIRMATION_REQUIRED_CONSECUTIVE_HITS}"
            )
            self.confirmation_catches_label.setText(
                f"Clean catches: {catches}/{CONFIRMATION_REQUIRED_CLEAN_CATCHES}"
            )
            warning = str(payload.get("warning") or "").strip()
            if warning:
                self._set_catch_warning(True, warning)

        def update_progress(self, payload: dict[str, Any]) -> None:
            trial_index = int(payload.get("trial_index") or 0)
            level = payload.get("level_percent", "")
            is_catch = bool(payload.get("is_catch"))
            message = str(payload.get("message") or "Tactile calibration running")
            self._set_catch_warning(False)
            self.status_label.setText(message)
            self.intensity_label.setText(f"Intensity: {_format_tactile_percent(level)} Output 3/4")
            try:
                self.intensity_bar.setValue(int(round(float(level) * OUTPUT_VOLUME_SLIDER_SCALE)))
            except Exception:
                self.intensity_bar.setValue(0)
            self.intensity_bar.setFormat(_format_tactile_percent(level))
            self.window_label.setText(
                f"Response window: {VALID_RESPONSE_START_MS:.0f}-{VALID_RESPONSE_END_MS:.0f} ms after pulse onset"
            )
            reversal = payload.get("reversal_index", "")
            self.reversal_label.setText(f"Reversals: {reversal if str(reversal) else 0}")
            if str(payload.get("phase") or "") == "confirmation":
                self.update_confirmation(payload)
            if trial_index:
                event_record = {
                    "trial_index": trial_index,
                    "phase": str(payload.get("phase") or ""),
                    "level_percent": level,
                    "is_catch": is_catch,
                    "current": True,
                }
                for event_item in self.events:
                    event_item["current"] = False
                self.events.append(event_record)
                row = self.table.rowCount()
                self.current_row_by_trial[trial_index] = row
                self.table.insertRow(row)
                values = [
                    trial_index,
                    str(payload.get("phase") or ""),
                    _format_tactile_percent(level),
                    "Catch" if is_catch else "Pulse",
                    "Waiting",
                    "",
                ]
                for column, value in enumerate(values):
                    self.table.setItem(row, column, q["QTableWidgetItem"](str(value)))
                self.table.scrollToBottom()
            self.timeline.set_events(self.events, max_events=int(payload.get("max_calibration_events") or 60))

        def record_response(self, payload: dict[str, Any]) -> None:
            trial_index = int(payload.get("trial_index") or 0)
            valid = bool(payload.get("valid_response"))
            latency = payload.get("response_latency_ms", "")
            try:
                latency_text = f"{float(latency):.0f} ms"
            except Exception:
                latency_text = "out of window"
            source = str(payload.get("response_source") or payload.get("source") or "mouse")
            self.response_label.setText(
                f"Last response: {'valid' if valid else 'ignored'} {latency_text} ({source})"
            )
            row = self.current_row_by_trial.get(trial_index)
            if row is not None:
                self.table.setItem(row, 4, q["QTableWidgetItem"]("valid " + latency_text if valid else "ignored"))

        def finish_trial(self, trial: dict[str, Any]) -> None:
            trial_index = int(trial.get("trial_index") or 0)
            outcome = str(trial.get("trial_outcome") or "")
            if str(trial.get("phase") or "") == "confirmation":
                self.update_confirmation(trial)
            warning = str(trial.get("warning") or "").strip()
            if warning or outcome == "false_alarm":
                self._set_catch_warning(True, warning or "Only press when you feel the tactile pulse.")
            row = self.current_row_by_trial.get(trial_index)
            if row is not None:
                self.table.setItem(row, 5, q["QTableWidgetItem"](outcome))
                if not bool(trial.get("response_present")):
                    self.table.setItem(row, 4, q["QTableWidgetItem"]("none"))
            for event_item in self.events:
                if int(event_item.get("trial_index") or 0) == trial_index:
                    event_item.update({"current": False, "trial_outcome": outcome})
            self.timeline.set_events(self.events, max_events=int(getattr(self.timeline, "max_events", 60)))

        def finish_assay(self, report: dict[str, Any]) -> None:
            accepted = bool(report.get("accepted"))
            self._accepted_assay = accepted
            final_value = report.get("recommended_output_34_percent", report.get("final_output_34_percent", ""))
            final_text = _format_tactile_percent(final_value)
            summary = dict(report.get("staircase_summary") or {})
            confirmation = dict(report.get("confirmation_summary") or {})
            reversals = summary.get("reversals", "")
            if accepted:
                self._set_catch_warning(False)
                self.status_label.setText(
                    f"Calibration yielded a value of {final_text} Output 3/4.\n"
                    "This value has been saved as part of the data log and implemented as the preset for this participant.\n"
                    "You may now continue with the experiment."
                )
                if final_text:
                    self.intensity_label.setText(f"Accepted threshold: {final_text} Output 3/4")
                    self.intensity_bar.setFormat(final_text)
                    try:
                        self.intensity_bar.setValue(int(round(float(final_value) * OUTPUT_VOLUME_SLIDER_SCALE)))
                    except Exception:
                        pass
            else:
                self.status_label.setText(str(report.get("message") or "Calibration failed"))
            if str(reversals):
                self.reversal_label.setText(f"Reversals: {reversals}")
            if confirmation:
                self.update_confirmation(
                    {
                        "confirmation_consecutive_hits": confirmation.get("consecutive_hits", ""),
                        "confirmation_clean_catches": confirmation.get("clean_catches", ""),
                    }
                )
            self.abort_button.setEnabled(False)
            self.close_button.setText("Continue" if accepted else "Close")
            self.close_button.setEnabled(True)

    return TactileCalibrationMonitorDialog()


def _create_analysis_curve_plot_widget(q: dict[str, Any]) -> Any:
    class AnalysisCurvePlotWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            self.observed: list[dict[str, float | str]] = []
            self.observed_series: list[dict[str, Any]] = []
            self.predicted: list[dict[str, float]] = []
            self.predicted_series: list[dict[str, Any]] = []
            self.raw_points: list[dict[str, float | str]] = []
            self.model_label = ""
            self.metric_label = ""
            self.empty_text = "No analysis curve selected"
            self.boundary_x: float | None = None
            self.boundary_label = ""
            self.show_observed = True
            self.show_uncertainty = True
            self.show_raw_points = False
            self.show_boundary = True
            self.show_low_n_markers = True
            self.setMinimumHeight(178)
            self.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)

        def set_series(
            self,
            *,
            observed: list[dict[str, float | str]],
            predicted: list[dict[str, float]],
            model_label: str,
            metric_label: str,
            empty_text: str,
            predicted_series: list[dict[str, Any]] | None = None,
            boundary_x: float | None = None,
            boundary_label: str = "",
            raw_points: list[dict[str, float | str]] | None = None,
            observed_series: list[dict[str, Any]] | None = None,
            show_observed: bool = True,
            show_uncertainty: bool = True,
            show_raw_points: bool = False,
            show_boundary: bool = True,
            show_low_n_markers: bool = True,
        ) -> None:
            self.observed = list(observed)
            if observed_series is None:
                self.observed_series = [{"label": "Observed mean", "points": list(observed), "color": "#8c2f2f"}] if observed else []
            else:
                self.observed_series = list(observed_series)
            self.predicted = list(predicted)
            if predicted_series is None:
                self.predicted_series = [{"model": "", "label": "Model fit", "points": list(predicted)}] if predicted else []
            else:
                self.predicted_series = list(predicted_series)
            self.raw_points = list(raw_points or [])
            self.model_label = str(model_label or "")
            self.metric_label = str(metric_label or "")
            self.empty_text = str(empty_text or "No analysis curve selected")
            self.boundary_x = boundary_x if boundary_x is not None and math.isfinite(float(boundary_x)) else None
            self.boundary_label = str(boundary_label or "")
            self.show_observed = bool(show_observed)
            self.show_uncertainty = bool(show_uncertainty)
            self.show_raw_points = bool(show_raw_points)
            self.show_boundary = bool(show_boundary)
            self.show_low_n_markers = bool(show_low_n_markers)
            self.update()

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                painter.fillRect(self.rect(), q["QColor"]("#f8f9f6"))
                width = max(1, int(self.width()))
                height = max(1, int(self.height()))
                left = 128
                right = 22
                compact_legend = len(self.predicted_series) > 1 and width < 840
                top = 76 if compact_legend else 28
                bottom = 42
                plot_width = max(1, width - left - right)
                plot_height = max(1, height - top - bottom)
                visible_observed_series = self.observed_series if self.show_observed else []
                visible_observed = [point for series in visible_observed_series for point in list(series.get("points") or [])]
                all_points = [(float(item["x"]), float(item["y"])) for item in visible_observed]
                if self.show_raw_points:
                    all_points.extend((float(item["x"]), float(item["y"])) for item in self.raw_points)
                for item in visible_observed:
                    low = _analysis_float(item.get("y_low"))
                    high = _analysis_float(item.get("y_high"))
                    if self.show_uncertainty and low is not None and high is not None:
                        all_points.append((float(item["x"]), low))
                        all_points.append((float(item["x"]), high))
                for series in self.predicted_series:
                    all_points.extend((float(item["x"]), float(item["y"])) for item in list(series.get("points") or []))
                if not all_points:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, self.empty_text)
                    return
                x_values = [point[0] for point in all_points]
                y_values = [point[1] for point in all_points]
                if self.show_boundary and self.boundary_x is not None:
                    x_values.append(float(self.boundary_x))
                x_min = min(x_values)
                x_max = max(x_values)
                y_min = min(y_values)
                y_max = max(y_values)
                if x_min == x_max:
                    x_min -= 1.0
                    x_max += 1.0
                if y_min == y_max:
                    y_min -= 1.0
                    y_max += 1.0
                y_pad = max(1.0, (y_max - y_min) * 0.12)
                y_min -= y_pad
                y_max += y_pad

                def _x(value: float) -> float:
                    return left + (value - x_min) / (x_max - x_min) * plot_width

                def _y(value: float) -> float:
                    return top + (y_max - value) / (y_max - y_min) * plot_height

                def _model_color(model: str, color: str = "") -> Any:
                    if color:
                        return q["QColor"](color)
                    if model == MODEL_SIGMOID:
                        return q["QColor"]("#246b55")
                    if model == MODEL_LINEAR:
                        return q["QColor"]("#4b5fa8")
                    if model == MODEL_LOGARITHMIC_DECAY:
                        return q["QColor"]("#a4631b")
                    return q["QColor"]("#246b55")

                def _model_pen(model: str, *, width_px: int = 3, color: str = "") -> Any:
                    pen = q["QPen"](_model_color(model, color))
                    pen.setWidth(width_px)
                    if model == MODEL_LINEAR:
                        pen.setStyle(q["Qt"].PenStyle.DashLine)
                    elif model == MODEL_LOGARITHMIC_DECAY:
                        pen.setStyle(q["Qt"].PenStyle.DotLine)
                    return pen

                grid_pen = q["QPen"](q["QColor"]("#d9dfd6"))
                grid_pen.setWidth(1)
                painter.setPen(grid_pen)
                for index in range(5):
                    y = top + int(plot_height * index / 4)
                    painter.drawLine(left, y, width - right, y)
                axis_pen = q["QPen"](q["QColor"]("#647067"))
                axis_pen.setWidth(2)
                painter.setPen(axis_pen)
                painter.drawLine(left, top, left, top + plot_height)
                painter.drawLine(left, top + plot_height, width - right, top + plot_height)

                if self.show_boundary and self.boundary_x is not None and x_min <= self.boundary_x <= x_max:
                    boundary_pen = q["QPen"](q["QColor"]("#6a5d2f"))
                    boundary_pen.setWidth(2)
                    boundary_pen.setStyle(q["Qt"].PenStyle.DashLine)
                    painter.setPen(boundary_pen)
                    boundary_px = int(round(_x(float(self.boundary_x))))
                    painter.drawLine(boundary_px, top, boundary_px, top + plot_height)
                    painter.setPen(q["QPen"](q["QColor"]("#6a5d2f")))
                    label = self.boundary_label or f"Boundary {_fmt_analysis_value(self.boundary_x)} ms"
                    if compact_legend:
                        label = f"Boundary {_fmt_analysis_value(self.boundary_x)} ms"
                        label_x = left
                        label_y = 50
                        label_width = 190
                    else:
                        label_y = top + 4
                        label_width = min(150, max(92, width - boundary_px - right - 4))
                        if label_width < 100:
                            label_width = 128
                            label_x = int(max(left + 4, boundary_px - label_width - 6))
                        else:
                            label_x = int(boundary_px + 6)
                    painter.drawText(label_x, label_y, label_width, 18, int(q["Qt"].AlignmentFlag.AlignLeft), label)

                spread_points = [
                    (float(point["x"]), float(point["y_low"]), float(point["y_high"]))
                    for point in visible_observed
                    if _analysis_float(point.get("y_low")) is not None and _analysis_float(point.get("y_high")) is not None
                ]
                if self.show_uncertainty and spread_points:
                    range_color = q["QColor"]("#d7b46a")
                    range_color.setAlpha(34)
                    range_pen_color = q["QColor"]("#9a7629")
                    range_pen_color.setAlpha(82)
                    if len(visible_observed_series) <= 1 and len(spread_points) >= 2:
                        path = q["QPainterPath"]()
                        first = spread_points[0]
                        path.moveTo(_x(first[0]), _y(max(first[1], first[2])))
                        for x_value, low, high in spread_points[1:]:
                            path.lineTo(_x(x_value), _y(max(low, high)))
                        for x_value, low, high in reversed(spread_points):
                            path.lineTo(_x(x_value), _y(min(low, high)))
                        path.closeSubpath()
                        painter.fillPath(path, q["QBrush"](range_color))
                    painter.setPen(q["QPen"](range_pen_color))
                    painter.setBrush(q["QBrush"](range_color))
                    for x_value, low, high in spread_points:
                        y_top = int(round(_y(max(low, high))))
                        y_bottom = int(round(_y(min(low, high))))
                        height_px = max(8, y_bottom - y_top)
                        painter.drawRoundedRect(int(round(_x(x_value))) - 8, y_top, 16, height_px, 7, 7)
                    label = str(visible_observed[0].get("spread_label") or "").strip()
                    if label:
                        painter.setPen(q["QPen"](q["QColor"]("#647067")))
                        painter.drawText(
                            left,
                            top + plot_height + 22,
                            plot_width,
                            16,
                            int(q["Qt"].AlignmentFlag.AlignRight),
                            f"Observed mean range: +/- {label}",
                        )

                for series in self.predicted_series:
                    points = list(series.get("points") or [])
                    if not points:
                        continue
                    model = str(series.get("model") or "")
                    painter.setPen(_model_pen(model, color=str(series.get("color") or "")))
                    path = q["QPainterPath"]()
                    first = points[0]
                    path.moveTo(_x(float(first["x"])), _y(float(first["y"])))
                    for point in points[1:]:
                        path.lineTo(_x(float(point["x"])), _y(float(point["y"])))
                    painter.drawPath(path)

                if len(self.predicted_series) > 1:
                    if compact_legend:
                        legend_x = max(left + 190, width - right - 322)
                        legend_y = 32
                        for index, series in enumerate(self.predicted_series):
                            model = str(series.get("model") or "")
                            label = str(series.get("label") or MODEL_LABELS.get(model, model))
                            if model == MODEL_LOGARITHMIC_DECAY:
                                label = "Log decay"
                            item_x = legend_x + (index % 2) * 154
                            item_y = legend_y + (index // 2) * 18
                            painter.setPen(_model_pen(model, width_px=2, color=str(series.get("color") or "")))
                            painter.drawLine(
                                int(round(item_x)),
                                int(round(item_y + 7)),
                                int(round(item_x + 24)),
                                int(round(item_y + 7)),
                            )
                            painter.setPen(q["QPen"](q["QColor"]("#202621")))
                            painter.drawText(
                                int(round(item_x + 30)),
                                int(round(item_y)),
                                142,
                                16,
                                int(q["Qt"].AlignmentFlag.AlignLeft),
                                label,
                            )
                    else:
                        legend_x = max(left + 12, width - right - 430)
                        legend_y = top + 4
                        for series in self.predicted_series:
                            model = str(series.get("model") or "")
                            label = str(series.get("label") or MODEL_LABELS.get(model, model))
                            painter.setPen(_model_pen(model, width_px=2, color=str(series.get("color") or "")))
                            painter.drawLine(
                                int(round(legend_x)),
                                int(round(legend_y + 7)),
                                int(round(legend_x + 24)),
                                int(round(legend_y + 7)),
                            )
                            painter.setPen(q["QPen"](q["QColor"]("#202621")))
                            painter.drawText(
                                int(round(legend_x + 30)),
                                int(round(legend_y)),
                                120,
                                16,
                                int(q["Qt"].AlignmentFlag.AlignLeft),
                                label,
                            )
                            legend_x += 138
                if visible_observed and len(visible_observed_series) <= 1:
                    if compact_legend and len(self.predicted_series) > 1:
                        legend_y = 50
                        legend_x = max(left + 190, width - right - 322) + 154
                    else:
                        legend_y = top + 24 if len(self.predicted_series) > 1 else top + 4
                        legend_x = max(left + 12, width - right - 182)
                    mean_pen = q["QPen"](q["QColor"]("#8c2f2f"))
                    mean_pen.setWidth(2)
                    painter.setPen(mean_pen)
                    painter.drawLine(
                        int(round(legend_x)),
                        int(round(legend_y + 7)),
                        int(round(legend_x + 24)),
                        int(round(legend_y + 7)),
                    )
                    painter.setPen(q["QPen"](q["QColor"]("#202621")))
                    painter.drawText(
                        int(round(legend_x + 30)),
                        int(round(legend_y)),
                        132,
                        16,
                        int(q["Qt"].AlignmentFlag.AlignLeft),
                        "Observed mean",
                    )

                for series in visible_observed_series:
                    points = list(series.get("points") or [])
                    if len(points) < 2:
                        continue
                    mean_pen = q["QPen"](q["QColor"](str(series.get("color") or "#8c2f2f")))
                    mean_pen.setWidth(2)
                    painter.setPen(mean_pen)
                    mean_path = q["QPainterPath"]()
                    first = points[0]
                    mean_path.moveTo(_x(float(first["x"])), _y(float(first["y"])))
                    for point in points[1:]:
                        mean_path.lineTo(_x(float(point["x"])), _y(float(point["y"])))
                    painter.drawPath(mean_path)

                if self.show_raw_points and self.raw_points:
                    raw_pen = q["QPen"](q["QColor"]("#4f5b52"))
                    raw_pen.setWidth(1)
                    raw_fill = q["QColor"]("#4f5b52")
                    raw_fill.setAlpha(52)
                    painter.setPen(raw_pen)
                    painter.setBrush(q["QBrush"](raw_fill))
                    for point in self.raw_points:
                        x = int(round(_x(float(point["x"]))))
                        y = int(round(_y(float(point["y"]))))
                        painter.drawEllipse(x - 3, y - 3, 6, 6)

                for series in visible_observed_series:
                    point_color = q["QColor"](str(series.get("color") or "#8c2f2f"))
                    point_pen = q["QPen"](point_color)
                    point_pen.setWidth(2)
                    fill_color = q["QColor"](point_color)
                    fill_color.setAlpha(46)
                    painter.setPen(point_pen)
                    painter.setBrush(q["QBrush"](fill_color))
                    for point in list(series.get("points") or []):
                        x = int(round(_x(float(point["x"]))))
                        y = int(round(_y(float(point["y"]))))
                        painter.drawEllipse(x - 5, y - 5, 10, 10)
                        if self.show_low_n_markers and str(point.get("low_n") or "").strip():
                            low_n_pen = q["QPen"](q["QColor"]("#a4631b"))
                            low_n_pen.setWidth(2)
                            painter.setPen(low_n_pen)
                            painter.setBrush(q["Qt"].BrushStyle.NoBrush)
                            painter.drawEllipse(x - 8, y - 8, 16, 16)
                            painter.setPen(point_pen)
                            painter.setBrush(q["QBrush"](fill_color))

                painter.setPen(q["QPen"](q["QColor"]("#202621")))
                painter.drawText(8, 6, width - 16, 18, int(q["Qt"].AlignmentFlag.AlignVCenter), self.model_label or "Model fit")
                painter.setPen(q["QPen"](q["QColor"]("#647067")))
                painter.drawText(left, height - 28, plot_width, 18, q["Qt"].AlignmentFlag.AlignCenter, "SOA (ms)")
                painter.drawText(8, top + 18, left - 18, 18, int(q["Qt"].AlignmentFlag.AlignRight), self.metric_label or "RT")
                painter.drawText(8, top + plot_height - 10, left - 18, 18, int(q["Qt"].AlignmentFlag.AlignRight), _fmt_analysis_value(y_min))
                painter.drawText(8, top - 8, left - 18, 18, int(q["Qt"].AlignmentFlag.AlignRight), _fmt_analysis_value(y_max))
                painter.drawText(left - 12, top + plot_height + 4, 70, 18, int(q["Qt"].AlignmentFlag.AlignLeft), _fmt_analysis_value(x_min))
                painter.drawText(width - right - 70, top + plot_height + 4, 70, 18, int(q["Qt"].AlignmentFlag.AlignRight), _fmt_analysis_value(x_max))
            finally:
                painter.end()

    return AnalysisCurvePlotWidget()


class AnalysisReviewDialog:
    """Read-only post-run model-fit review dialog."""

    def __init__(
        self,
        q: dict[str, Any],
        parent: Any,
        data: Any,
        *,
        dataset_entries: list[dict[str, Any]] | None = None,
        selected_dataset_id: str = "",
    ) -> None:
        self.q = q
        self.data = data
        self.dataset_entries = list(dataset_entries or [])
        self.current_dataset_id = str(selected_dataset_id or getattr(data, "dataset_id", "") or "")
        self._dataset_combo_updating = False
        self.current_part_mode = data.default_part_mode
        self.current_view = VIEW_DATA_BEHAVIOR
        self.current_condition_lens = default_condition_lens(data)
        self.current_quick_model = default_condition_model(data)
        self.quick_mode = True
        self.condition_lens_buttons: dict[str, Any] = {}
        self.quick_model_buttons: dict[str, Any] = {}
        self.part_mode_buttons: dict[str, Any] = {}
        self.view_buttons: dict[str, Any] = {}
        self.plot_toggles: dict[str, Any] = {}
        self.dialog = q["QDialog"](parent)
        _enable_standard_window_controls(q, self.dialog)
        self.dialog.setWindowTitle("PPS Instant Analysis")
        self.dialog.setModal(False)
        minimum_width, minimum_height, initial_width, initial_height = self._screen_sized_bounds()
        self.dialog.setMinimumSize(minimum_width, minimum_height)
        self.dialog.resize(initial_width, initial_height)
        self.dialog.setStyleSheet(self._analysis_style_sheet())
        self._build()
        self._refresh()

    def show(self) -> None:
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def _screen_sized_bounds(self) -> tuple[int, int, int, int]:
        width = 1280
        height = 900
        try:
            screen = self.q["QApplication"].primaryScreen()
            geometry = screen.availableGeometry() if screen is not None else None
            if geometry is not None:
                width = int(geometry.width())
                height = int(geometry.height())
        except Exception:
            pass
        minimum_width = min(720, max(620, width - 80))
        minimum_height = min(500, max(460, height - 120))
        initial_width = min(980, max(minimum_width, width - 120))
        initial_height = min(700, max(minimum_height, height - 120))
        return minimum_width, minimum_height, initial_width, initial_height

    def _analysis_style_sheet(self) -> str:
        return (
            _focus_style_sheet(self.q, DEFAULT_FOCUS_LAYOUT_PROFILE)
            + """
QDialog {
    background: #f4f5f1;
}
QScrollArea#analysisScrollArea,
QWidget#analysisContent {
    background: #f4f5f1;
}
QFrame#analysisSegmentedControl {
    background: #ffffff;
    border: 1px solid #bcc7bd;
    border-radius: 6px;
}
QFrame#analysisTogglePanel {
    background: #ffffff;
    border: 1px solid #d9dfd6;
    border-radius: 6px;
}
QPushButton#analysisSegmentButton {
    border: 0;
    border-radius: 0;
    background: transparent;
    padding: 6px 10px;
    min-height: 30px;
    font-weight: 700;
}
QPushButton#analysisSegmentButton:hover {
    background: #f3f6f2;
}
QPushButton#analysisSegmentButton:checked {
    background: #246b55;
    color: #ffffff;
    font-weight: 800;
}
QPushButton#analysisSegmentButton:disabled {
    color: #9ba59d;
    background: #eef0eb;
}
QCheckBox#analysisPlotToggle {
    color: #202621;
    padding: 3px 6px;
    font-weight: 650;
}
QCheckBox#analysisPlotToggle:disabled {
    color: #9ba59d;
}
QLabel#analysisQualityReason,
QLabel#analysisTriageHint {
    color: #4f5b52;
    font-weight: 650;
}
QLabel#analysisQualityBadge {
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 900;
}
QPushButton#analysisConditionLensButton,
QPushButton#analysisModelButton,
QPushButton#analysisMoreButton {
    border: 1px solid #bcc7bd;
    border-radius: 6px;
    background: #ffffff;
    color: #202621;
    padding: 7px 12px;
    min-height: 30px;
    font-weight: 800;
}
QPushButton#analysisConditionLensButton:checked,
QPushButton#analysisModelButton:checked {
    background: #202621;
    color: #ffffff;
    border-color: #202621;
}
QWidget#analysisMoreContainer {
    background: #f4f5f1;
}
QTableWidget#analysisOverviewTable {
    background: #ffffff;
    border: 1px solid #d9dfd6;
    border-radius: 6px;
    gridline-color: #d9dfd6;
    selection-background-color: #e9f4ef;
    selection-color: #202621;
}
QHeaderView::section {
    background: #f8f9f6;
    color: #37433b;
    border: 0;
    border-right: 1px solid #d9dfd6;
    border-bottom: 1px solid #d9dfd6;
    padding: 5px 6px;
    font-weight: 800;
}
QTextEdit#analysisDetailsText {
    background: #ffffff;
    border-radius: 6px;
}
"""
        )

    def _build(self) -> None:
        q = self.q
        outer = q["QVBoxLayout"](self.dialog)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll_area = q["QScrollArea"]()
        self.scroll_area.setObjectName("analysisScrollArea")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(q["Qt"].ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(q["QFrame"].Shape.NoFrame)
        self.scroll_area.setMinimumHeight(0)
        self.scroll_area.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        content = q["QWidget"]()
        content.setObjectName("analysisContent")
        root = q["QVBoxLayout"](content)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area, 1)

        header = q["QLabel"]("Instant PPS Analysis")
        header.setObjectName("appTitle")
        root.addWidget(header)

        subtitle = q["QLabel"](
            "Plot-first triage for this participant run. The quality grade is a strict data-exclusion gate; model and condition colors are exploratory cues."
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        dataset_row = q["QHBoxLayout"]()
        dataset_row.setContentsMargins(0, 0, 0, 0)
        dataset_row.setSpacing(8)
        dataset_row.addWidget(q["QLabel"]("Dataset"))
        self.dataset_combo = q["QComboBox"]()
        self.dataset_combo.setObjectName("analysisDatasetCombo")
        self.dataset_combo.setMinimumWidth(260)
        self._populate_dataset_combo()
        self.dataset_combo.currentIndexChanged.connect(self._dataset_selection_changed)
        dataset_row.addWidget(self.dataset_combo, 1)
        root.addLayout(dataset_row)

        quality_row = q["QHBoxLayout"]()
        quality_row.setContentsMargins(0, 0, 0, 0)
        quality_row.setSpacing(8)
        self.quality_badge = q["QLabel"]("Participant Run Quality: UNKNOWN")
        self.quality_badge.setObjectName("analysisQualityBadge")
        self.quality_reason = q["QLabel"]("")
        self.quality_reason.setObjectName("analysisQualityReason")
        self.quality_reason.setWordWrap(True)
        quality_row.addWidget(self.quality_badge, 0)
        quality_row.addWidget(self.quality_reason, 1)
        root.addLayout(quality_row)

        plot_panel, plot_layout = _panel(q, "PPS Response Curves")
        self.plot_widget = _create_analysis_curve_plot_widget(q)
        self.plot_widget.setObjectName("analysisCurvePlot")
        self.plot_widget.setMinimumHeight(260)
        plot_layout.addWidget(self.plot_widget)
        root.addWidget(plot_panel, 1)

        condition_row = q["QHBoxLayout"]()
        condition_row.setContentsMargins(0, 0, 0, 0)
        condition_row.setSpacing(8)
        condition_row.addWidget(q["QLabel"]("Conditions"))
        for payload in condition_lens_button_rows(self.data):
            lens = str(payload.get("lens") or "")
            button = q["QPushButton"](str(payload.get("label") or lens))
            button.setObjectName("analysisConditionLensButton")
            button.setCheckable(True)
            button.setChecked(lens == self.current_condition_lens)
            button.setToolTip(self._condition_button_tooltip(payload))
            button.clicked.connect(lambda _checked=False, selected_lens=lens: self._set_condition_lens(selected_lens))
            self.condition_lens_buttons[lens] = button
            condition_row.addWidget(button)
        condition_row.addStretch(1)
        root.addLayout(condition_row)

        model_row = q["QHBoxLayout"]()
        model_row.setContentsMargins(0, 0, 0, 0)
        model_row.setSpacing(8)
        model_row.addWidget(q["QLabel"]("Model"))
        for payload in model_button_rows(self.data):
            model = str(payload.get("model") or "")
            button = q["QPushButton"](str(payload.get("label") or model))
            button.setObjectName("analysisModelButton")
            button.setCheckable(True)
            button.setChecked(model == self.current_quick_model)
            button.setToolTip(self._model_button_tooltip(payload))
            button.clicked.connect(lambda _checked=False, selected_model=model: self._set_quick_model(selected_model))
            self.quick_model_buttons[model] = button
            model_row.addWidget(button)
        model_row.addStretch(1)
        root.addLayout(model_row)

        self.triage_hint = q["QLabel"]("")
        self.triage_hint.setObjectName("analysisTriageHint")
        self.triage_hint.setWordWrap(True)
        root.addWidget(self.triage_hint)

        self.more_button = q["QPushButton"]("More")
        self.more_button.setObjectName("analysisMoreButton")
        self.more_button.setCheckable(True)
        self.more_button.toggled.connect(self._set_more_visible)
        root.addWidget(self.more_button, 0)

        self.more_container = q["QWidget"]()
        self.more_container.setObjectName("analysisMoreContainer")
        self.more_container.setVisible(False)
        more_root = q["QVBoxLayout"](self.more_container)
        more_root.setContentsMargins(0, 0, 0, 0)
        more_root.setSpacing(8)
        root.addWidget(self.more_container, 0)

        view_row = q["QHBoxLayout"]()
        view_row.setContentsMargins(0, 0, 0, 0)
        view_row.setSpacing(8)
        view_row.addWidget(q["QLabel"]("View"))
        self.view_frame = q["QFrame"]()
        self.view_frame.setObjectName("analysisSegmentedControl")
        view_layout = q["QGridLayout"](self.view_frame)
        view_layout.setContentsMargins(0, 0, 0, 0)
        view_layout.setSpacing(0)
        for index, view in enumerate(VIEW_ORDER):
            button = q["QPushButton"](VIEW_LABELS.get(view, view))
            button.setObjectName("analysisSegmentButton")
            button.setCheckable(True)
            button.setChecked(view == self.current_view)
            button.clicked.connect(lambda _checked=False, selected_view=view: self._set_view(selected_view))
            self.view_buttons[view] = button
            view_layout.addWidget(button, index // 3, index % 3)
        view_row.addWidget(self.view_frame, 1)
        more_root.addLayout(view_row)

        controls = q["QGridLayout"]()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        self.part_mode_frame = q["QFrame"]()
        self.part_mode_frame.setObjectName("analysisSegmentedControl")
        part_mode_layout = q["QHBoxLayout"](self.part_mode_frame)
        part_mode_layout.setContentsMargins(0, 0, 0, 0)
        part_mode_layout.setSpacing(0)
        available_part_modes = set(self.data.part_modes)
        for mode in (PARTS_SEPARATE, PARTS_POOLED):
            button = q["QPushButton"](PART_AGGREGATION_LABELS.get(mode, mode))
            button.setObjectName("analysisSegmentButton")
            button.setCheckable(True)
            button.setEnabled(mode in available_part_modes)
            button.setChecked(mode == self.current_part_mode)
            button.clicked.connect(lambda _checked=False, selected_mode=mode: self._set_part_mode(selected_mode))
            self.part_mode_buttons[mode] = button
            part_mode_layout.addWidget(button)
        self.scope_combo = q["QComboBox"]()
        self.scope_combo.setObjectName("analysisScopeCombo")
        self.model_combo = q["QComboBox"]()
        self.model_combo.setObjectName("analysisModelCombo")
        for model in MODEL_ORDER:
            self.model_combo.addItem(MODEL_LABELS.get(model, model), model)
        self.metric_combo = q["QComboBox"]()
        self.metric_combo.setObjectName("analysisMetricCombo")
        for metric in METRIC_ORDER:
            self.metric_combo.addItem(METRIC_LABELS.get(metric, metric), metric)
        self.source_combo = q["QComboBox"]()
        self.source_combo.setObjectName("analysisSourceCombo")
        for source in SOURCE_ORDER:
            self.source_combo.addItem(SOURCE_LABELS.get(source, source), source)
        self.grouping_combo = q["QComboBox"]()
        self.grouping_combo.setObjectName("analysisGroupingCombo")
        for grouping in GROUPING_ORDER:
            self.grouping_combo.addItem(GROUPING_LABELS.get(grouping, grouping), grouping)
        controls.addWidget(q["QLabel"]("Parts"), 0, 0)
        controls.addWidget(self.part_mode_frame, 0, 1)
        controls.addWidget(q["QLabel"]("Condition"), 0, 2)
        controls.addWidget(self.scope_combo, 0, 3)
        controls.addWidget(q["QLabel"]("Model"), 1, 0)
        controls.addWidget(self.model_combo, 1, 1)
        controls.addWidget(q["QLabel"]("Metric"), 1, 2)
        controls.addWidget(self.metric_combo, 1, 3)
        controls.addWidget(q["QLabel"]("Source"), 2, 0)
        controls.addWidget(self.source_combo, 2, 1)
        controls.addWidget(q["QLabel"]("Grouping"), 2, 2)
        controls.addWidget(self.grouping_combo, 2, 3)
        controls.setColumnStretch(3, 1)
        more_root.addLayout(controls)

        toggle_panel = q["QFrame"]()
        toggle_panel.setObjectName("analysisTogglePanel")
        toggle_layout = q["QGridLayout"](toggle_panel)
        toggle_layout.setContentsMargins(6, 4, 6, 4)
        toggle_layout.setSpacing(3)
        for index, (key, label, checked) in enumerate((
            ("observed_means", "Observed means", True),
            ("uncertainty_band", "Uncertainty band", True),
            ("raw_trial_points", "Raw trial points", False),
            ("rejected_extra_clicks", "Rejected / extra clicks", False),
            ("topup_rescues", "Top-up rescues", False),
            ("pps_boundary", "PPS boundary", True),
            ("all_model_fits", "All model fits", False),
            ("low_n_markers", "Low-N markers", True),
        )):
            box = q["QCheckBox"](label)
            box.setObjectName("analysisPlotToggle")
            box.setChecked(checked)
            box.stateChanged.connect(lambda _state=0: self._refresh_detail_mode())
            self.plot_toggles[key] = box
            toggle_layout.addWidget(box, index // 4, index % 4)
        more_root.addWidget(toggle_panel)

        body = q["QSplitter"](q["Qt"].Orientation.Vertical)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(8)
        body.setMinimumHeight(0)
        body.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        more_root.addWidget(body, 1)

        overview_panel, overview_layout = _panel(q, "Best Model Overview")
        self.overview_table = q["QTableWidget"](0, 7)
        self.overview_table.setObjectName("analysisOverviewTable")
        self.overview_table.setHorizontalHeaderLabels(["Scope", "Best", "AIC", "R2", "RMSE", "Metric", "N"])
        self.overview_table.setEditTriggers(q["QTableWidget"].EditTrigger.NoEditTriggers)
        self.overview_table.setWordWrap(False)
        self.overview_table.setMinimumHeight(82)
        self.overview_table.setMaximumHeight(112)
        self.overview_table.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Minimum)
        self.overview_table.setHorizontalScrollBarPolicy(q["Qt"].ScrollBarPolicy.ScrollBarAlwaysOff)
        self.overview_table.setVerticalScrollBarPolicy(q["Qt"].ScrollBarPolicy.ScrollBarAsNeeded)
        self.overview_table.cellClicked.connect(self._select_scope_from_table)
        try:
            header = self.overview_table.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, q["QHeaderView"].ResizeMode.Stretch)
            for column in range(1, 7):
                header.setSectionResizeMode(column, q["QHeaderView"].ResizeMode.Fixed)
            vertical_header = self.overview_table.verticalHeader()
            vertical_header.setVisible(False)
            vertical_header.setDefaultSectionSize(30)
        except Exception:
            pass
        overview_layout.addWidget(self.overview_table)
        body.addWidget(overview_panel)

        detail_panel, detail_layout = _panel(q, "Selected Fit Details")
        self.detail_text = q["QTextEdit"]()
        self.detail_text.setObjectName("analysisDetailsText")
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(64)
        self.detail_text.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        detail_layout.addWidget(self.detail_text)
        body.addWidget(detail_panel)
        body.setSizes([112, 180])

        buttons = q["QHBoxLayout"]()
        buttons.setContentsMargins(12, 8, 12, 12)
        buttons.addStretch(1)
        self.open_folder_button = q["QPushButton"]("Open Analysis Folder")
        self.open_folder_button.clicked.connect(self._open_analysis_folder)
        close_button = q["QPushButton"]("Close")
        close_button.clicked.connect(self.dialog.close)
        buttons.addWidget(self.open_folder_button)
        buttons.addWidget(close_button)
        outer.addLayout(buttons)

        self.scope_combo.currentIndexChanged.connect(lambda _index: self._refresh_detail_mode())
        self.model_combo.currentIndexChanged.connect(lambda _index: self._refresh_detail_mode())
        self.metric_combo.currentIndexChanged.connect(lambda _index: self._refresh_detail_mode())
        self.source_combo.currentIndexChanged.connect(lambda _index: self._refresh_detail_mode())
        self.grouping_combo.currentIndexChanged.connect(lambda _index: self._refresh_detail_mode())
        self._reload_scopes_for_part_mode()
        self._populate_overview_table()
        self._refresh_quick_button_styles()

    def _populate_dataset_combo(self) -> None:
        if not hasattr(self, "dataset_combo"):
            return
        entries = self.dataset_entries or [
            {
                "dataset_id": self.current_dataset_id or getattr(self.data, "dataset_id", "") or "current",
                "dataset_label": getattr(self.data, "dataset_label", "") or "Current participant",
                "dataset_kind": getattr(self.data, "dataset_kind", "") or "participant",
            }
        ]
        self._dataset_combo_updating = True
        try:
            self.dataset_combo.blockSignals(True)
            self.dataset_combo.clear()
            for entry in entries:
                dataset_id = str(entry.get("dataset_id") or "")
                self.dataset_combo.addItem(self._dataset_entry_label(entry), dataset_id)
            current = self.current_dataset_id or str(getattr(self.data, "dataset_id", "") or "")
            index = self.dataset_combo.findData(current)
            self.dataset_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.dataset_combo.blockSignals(False)
            self._dataset_combo_updating = False

    def _dataset_entry_label(self, entry: dict[str, Any]) -> str:
        label = str(entry.get("dataset_label") or "").strip() or "Dataset"
        quality = str(entry.get("quality_status") or "").strip().upper()
        if str(entry.get("dataset_kind") or "") == DATASET_KIND_POOL:
            return label
        return f"{label} ({quality})" if quality else label

    def _dataset_selection_changed(self, _index: int) -> None:
        if self._dataset_combo_updating:
            return
        dataset_id = str(self.dataset_combo.currentData() or "").strip()
        if not dataset_id or dataset_id == self.current_dataset_id:
            return
        entry = next((item for item in self.dataset_entries if str(item.get("dataset_id") or "") == dataset_id), None)
        if entry is None:
            return
        try:
            data = load_analysis_dataset(entry)
        except Exception as exc:  # noqa: BLE001 - keep the existing dataset visible on load failure.
            self.triage_hint.setText(f"Could not load selected analysis dataset: {exc}")
            return
        if not data.has_analysis_tables:
            self.triage_hint.setText("Selected analysis dataset has no plotted analysis tables.")
            return
        self.data = data
        self.current_dataset_id = dataset_id
        self.current_part_mode = data.default_part_mode
        self.current_condition_lens = default_condition_lens(data)
        self.current_quick_model = default_condition_model(data)
        self.quick_mode = True
        self._reload_scopes_for_part_mode()
        self._populate_overview_table()
        self._refresh_quick_button_styles()
        self._refresh()

    def _condition_button_tooltip(self, payload: dict[str, Any]) -> str:
        cues = []
        if payload.get("curve_separation_winner"):
            cues.append("largest visual curve separation")
        if payload.get("boundary_shift_winner"):
            cues.append("largest valid sigmoid boundary shift")
        return "Exploratory condition lens" + (": " + ", ".join(cues) if cues else "")

    def _model_button_tooltip(self, payload: dict[str, Any]) -> str:
        tier = str(payload.get("evidence_tier") or MODEL_EVIDENCE_INSUFFICIENT)
        wins = payload.get("subcondition_wins", 0)
        overall = "overall winner" if payload.get("overall_winner") else "not overall winner"
        return f"AICc support: {tier}; {overall}; subcondition wins: {wins}"

    def _set_condition_lens(self, lens: str) -> None:
        self.quick_mode = True
        self.current_condition_lens = str(lens or CONDITION_LENS_TWO_BY_TWO)
        self._refresh_quick_button_styles()
        self._refresh()

    def _set_quick_model(self, model: str) -> None:
        self.quick_mode = True
        self.current_quick_model = str(model or MODEL_SIGMOID)
        self._refresh_quick_button_styles()
        self._refresh()

    def _set_more_visible(self, visible: bool) -> None:
        self.more_container.setVisible(bool(visible))
        self.more_button.setText("Less" if visible else "More")
        if visible:
            self.detail_text.setPlainText(self._quick_detail_text())

    def _refresh_detail_mode(self) -> None:
        self.quick_mode = False
        self._refresh()

    def _refresh_quick_button_styles(self) -> None:
        condition_payloads = {str(row.get("lens") or ""): row for row in condition_lens_button_rows(self.data)}
        for lens, button in self.condition_lens_buttons.items():
            payload = condition_payloads.get(lens, {})
            label = str(payload.get("label") or lens)
            if button.text() != label:
                button.setText(label)
            button.setToolTip(self._condition_button_tooltip(payload))
            if button.isChecked() != (lens == self.current_condition_lens):
                button.setChecked(lens == self.current_condition_lens)
            stripe = "#246b55" if payload.get("curve_separation_winner") else "#4b5fa8" if payload.get("boundary_shift_winner") else "#bcc7bd"
            self._style_triage_button(button, selected=lens == self.current_condition_lens, stripe=stripe)
        model_payloads = {str(row.get("model") or ""): row for row in model_button_rows(self.data)}
        for model, button in self.quick_model_buttons.items():
            payload = model_payloads.get(model, {})
            label = str(payload.get("label") or MODEL_LABELS.get(model, model))
            if button.text() != label:
                button.setText(label)
            button.setToolTip(self._model_button_tooltip(payload))
            if button.isChecked() != (model == self.current_quick_model):
                button.setChecked(model == self.current_quick_model)
            self._style_triage_button(button, selected=model == self.current_quick_model, stripe=self._evidence_color(str(payload.get("evidence_tier") or "")))

    def _style_triage_button(self, button: Any, *, selected: bool, stripe: str) -> None:
        if selected:
            button.setStyleSheet(f"border: 1px solid #202621; border-left: 7px solid {stripe}; background: #202621; color: #ffffff;")
        else:
            button.setStyleSheet(f"border: 1px solid #bcc7bd; border-left: 7px solid {stripe}; background: #ffffff; color: #202621;")

    def _evidence_color(self, tier: str) -> str:
        if tier == MODEL_EVIDENCE_STRONG:
            return "#246b55"
        if tier == MODEL_EVIDENCE_MIXED:
            return "#a4631b"
        return "#9ba59d"

    def _refresh_quality_badge(self) -> None:
        status, reason = recording_quality_status(self.data)
        label = str(getattr(self.data, "quality_label", "") or "Participant Run Quality")
        self.quality_badge.setText(f"{label}: {status}")
        if status == "PASS":
            self.quality_badge.setStyleSheet("background: #dceee5; color: #174f3e; border: 1px solid #8dc3aa;")
        elif status == "FAIL":
            self.quality_badge.setStyleSheet("background: #f4dddd; color: #7b2323; border: 1px solid #d39a9a;")
        else:
            self.quality_badge.setStyleSheet("background: #ecefeb; color: #4f5b52; border: 1px solid #bcc7bd;")
        self.quality_reason.setText(reason)

    def _refresh_quick(self) -> None:
        self._refresh_quality_badge()
        observed_series = condition_lens_observed_series(self.data, self.current_condition_lens)
        if not observed_series and scopes_for_part_mode(self.data, self.current_part_mode):
            self.quick_mode = False
            self._refresh()
            return
        predicted_series = condition_lens_prediction_series(self.data, self.current_condition_lens, self.current_quick_model)
        lens_payload = next((row for row in condition_lens_button_rows(self.data) if row.get("lens") == self.current_condition_lens), {})
        model_payload = next((row for row in model_button_rows(self.data) if row.get("model") == self.current_quick_model), {})
        lens_label = str(lens_payload.get("label") or self.current_condition_lens)
        model_label = str(model_payload.get("label") or MODEL_LABELS.get(self.current_quick_model, self.current_quick_model))
        tier = str(model_payload.get("evidence_tier") or MODEL_EVIDENCE_INSUFFICIENT)
        baseline_status = condition_lens_baseline_status(self.data, self.current_condition_lens)
        self.triage_hint.setText(
            f"{lens_label}: {len(observed_series)} curve(s). {model_label} AICc support: {tier}. "
            f"{baseline_status}. Button colors point to promising visual separation or model support, not confirmatory statistics."
        )
        self.plot_widget.set_series(
            observed=[],
            observed_series=observed_series,
            predicted=[],
            predicted_series=predicted_series,
            model_label=f"{lens_label} | {model_label}",
            metric_label=condition_lens_metric_label(self.data, self.current_condition_lens),
            empty_text="No condition-lens curve points were available for this participant.",
            show_observed=True,
            show_uncertainty=True,
            show_raw_points=False,
            show_boundary=False,
            show_low_n_markers=True,
        )
        self.detail_text.setPlainText(self._quick_detail_text())

    def _quick_detail_text(self) -> str:
        status, reason = recording_quality_status(self.data)
        quality_label = str(getattr(self.data, "quality_label", "") or "Participant Run Quality")
        lines = [f"{quality_label}: {status}", reason]
        if str(getattr(self.data, "dataset_kind", "") or "") == DATASET_KIND_POOL:
            lines.append(
                f"Pool inclusion: {getattr(self.data, 'pool_included_count', 0)} PASS participant(s), "
                f"{getattr(self.data, 'pool_excluded_count', 0)} excluded."
            )
        lines.append(f"Condition lens: {self.current_condition_lens}")
        lines.append(f"Model display: {MODEL_LABELS.get(self.current_quick_model, self.current_quick_model)}")
        summary = self.data.condition_lens_triage_summary
        if summary:
            lines.append("")
            lines.append(str(summary.get("interpretation_note") or ""))
            wins = summary.get("model_wins_by_subcondition", {})
            if isinstance(wins, dict) and wins:
                lines.append("Model wins by subcondition: " + ", ".join(f"{key} {value}" for key, value in sorted(wins.items())))
        failures = self.data.recording_quality_gate.get("failures", [])
        if isinstance(failures, list) and failures:
            lines.append("")
            lines.append("Serious exclusion criteria")
            lines.extend(f"- {row.get('message', '')} ({row.get('evidence', '')})" for row in failures[:8] if isinstance(row, dict))
        return "\n".join(line for line in lines if line is not None)

    def _set_view(self, view: str) -> None:
        self.quick_mode = False
        if view == self.current_view or view not in VIEW_ORDER:
            for button_view, button in self.view_buttons.items():
                button.setChecked(button_view == self.current_view)
            return
        self.current_view = view
        for button_view, button in self.view_buttons.items():
            button.setChecked(button_view == view)
        if view == VIEW_MODEL_FITS:
            self.model_combo.setEnabled(True)
        self._refresh()

    def _set_part_mode(self, mode: str) -> None:
        self.quick_mode = False
        if mode == self.current_part_mode or mode not in self.data.part_modes:
            for button_mode, button in self.part_mode_buttons.items():
                button.setChecked(button_mode == self.current_part_mode)
            return
        self.current_part_mode = mode
        for button_mode, button in self.part_mode_buttons.items():
            button.setChecked(button_mode == mode)
        self._reload_scopes_for_part_mode()
        self._populate_overview_table()
        self._refresh()

    def _toggle_checked(self, key: str, default: bool = False) -> bool:
        widget = self.plot_toggles.get(key)
        if widget is None:
            return default
        try:
            return bool(widget.isChecked())
        except Exception:
            return default

    def _reload_scopes_for_part_mode(self) -> None:
        current = str(self.scope_combo.currentData() or self.scope_combo.currentText() or "")
        scopes = scopes_for_part_mode(self.data, self.current_part_mode)
        try:
            self.scope_combo.blockSignals(True)
        except Exception:
            pass
        self.scope_combo.clear()
        for scope in scopes:
            self.scope_combo.addItem(scope, scope)
        if current:
            index = self.scope_combo.findText(current)
            if index >= 0:
                self.scope_combo.setCurrentIndex(index)
        try:
            self.scope_combo.blockSignals(False)
        except Exception:
            pass

    def _populate_overview_table(self) -> None:
        q = self.q
        scopes = scopes_for_part_mode(self.data, self.current_part_mode)
        self.overview_table.setRowCount(len(scopes))
        for row_index, scope in enumerate(scopes):
            row = scope_comparison_row(self.data, scope, self.current_part_mode)
            best_model = str(row.get("best_model") or "").strip()
            best_fit = fit_row_for_scope(self.data, scope, best_model or MODEL_BEST, self.current_part_mode) or {}
            values = [
                scope,
                MODEL_LABELS.get(best_model, best_model),
                _fmt_analysis_value(row.get("best_aic") or best_fit.get("aic")),
                _fmt_analysis_value(row.get("best_r2") or best_fit.get("r2")),
                _fmt_analysis_value(row.get("best_rmse") or best_fit.get("rmse")),
                _metric_display(row.get("fit_metric") or best_fit.get("fit_metric")),
                str(row.get("n_points") or best_fit.get("n_points") or ""),
            ]
            for column, value in enumerate(values):
                item = q["QTableWidgetItem"](str(value))
                item.setToolTip(str(value))
                self.overview_table.setItem(row_index, column, item)
        for column, width in enumerate((220, 112, 62, 62, 70, 118, 34)):
            self.overview_table.setColumnWidth(column, width)

    def _select_scope_from_table(self, row: int, _column: int) -> None:
        item = self.overview_table.item(row, 0)
        if item is None:
            return
        index = self.scope_combo.findText(item.text())
        if index >= 0:
            self.scope_combo.setCurrentIndex(index)

    def _open_analysis_folder(self) -> None:
        if self.data.session_dir is None:
            return
        analysis_dir = self.data.session_dir / "analysis"
        target = analysis_dir if analysis_dir.is_dir() else self.data.session_dir
        self.q["QDesktopServices"].openUrl(self.q["QUrl"].fromLocalFile(str(target)))

    def _refresh(self) -> None:
        if self.quick_mode:
            self._refresh_quick_button_styles()
            self._refresh_quick()
            return
        scopes = scopes_for_part_mode(self.data, self.current_part_mode)
        if not scopes:
            self.scope_combo.setEnabled(False)
            self.model_combo.setEnabled(False)
            self.plot_widget.set_series(
                observed=[],
                predicted=[],
                model_label="No model fits",
                metric_label="",
                empty_text="No analyzable SOA curves were written for this session.",
            )
            self.detail_text.setPlainText(self._empty_detail_text())
            return
        self.scope_combo.setEnabled(True)
        self.model_combo.setEnabled(True)
        scope = str(self.scope_combo.currentData() or self.scope_combo.currentText() or scopes[0])
        requested_model = str(self.model_combo.currentData() or MODEL_BEST)
        metric = str(self.metric_combo.currentData() or METRIC_FACILITATION)
        source_mode = str(self.source_combo.currentData() or SOURCE_FINAL)
        grouping = str(self.grouping_combo.currentData() or "")
        if self._toggle_checked("all_model_fits") and metric in {METRIC_FACILITATION, METRIC_MEAN_RT}:
            requested_model = MODEL_COMPARE_ALL
        resolved_model = best_model_for_scope(self.data, scope, self.current_part_mode) if requested_model == MODEL_BEST else requested_model
        fit = None if requested_model == MODEL_COMPARE_ALL else fit_row_for_scope(self.data, scope, requested_model, self.current_part_mode)
        observed = observed_points_for_scope(self.data, scope, self.current_part_mode, metric=metric, source_mode=source_mode)
        model_metric_available = metric in {METRIC_FACILITATION, METRIC_MEAN_RT}
        predicted_series = (
            prediction_series_for_scope(self.data, scope, requested_model, part_mode=self.current_part_mode)
            if model_metric_available
            else []
        )
        predicted = list(predicted_series[0].get("points") or []) if len(predicted_series) == 1 else []
        available = available_models_for_scope(self.data, scope, self.current_part_mode)
        model_label = MODEL_LABELS.get(resolved_model, resolved_model or "Model")
        if requested_model == MODEL_BEST and resolved_model:
            model_label = f"Best model: {model_label}"
        elif requested_model == MODEL_COMPARE_ALL:
            model_label = MODEL_LABELS.get(MODEL_COMPARE_ALL, "Compare all three")
        empty = f"{MODEL_LABELS.get(requested_model, requested_model)} was not fit for {scope}."
        sigmoid_fit = fit_row_for_scope(self.data, scope, MODEL_SIGMOID, self.current_part_mode)
        boundary_x = None
        if requested_model == MODEL_COMPARE_ALL and sigmoid_fit is not None:
            boundary_x = _analysis_float(sigmoid_fit.get("pps_boundary_soa_ms"))
        elif resolved_model == MODEL_SIGMOID:
            boundary_x = _analysis_float((fit or {}).get("pps_boundary_soa_ms"))
        if not model_metric_available:
            boundary_x = None
            model_label = METRIC_LABELS.get(metric, metric)
        raw_points = (
            raw_points_for_scope(self.data, scope, self.current_part_mode, source_mode=source_mode)
            if self._toggle_checked("raw_trial_points") or self._toggle_checked("rejected_extra_clicks") or self._toggle_checked("topup_rescues")
            else []
        )
        if self._toggle_checked("topup_rescues"):
            raw_points.extend(raw_points_for_scope(self.data, scope, self.current_part_mode, source_mode="topup_rescues"))
        self.plot_widget.set_series(
            observed=observed,
            predicted=predicted,
            predicted_series=predicted_series,
            model_label=f"{scope} | {model_label}",
            metric_label=_metric_display(metric),
            empty_text=empty if observed else "No curve points were available for this condition.",
            boundary_x=boundary_x,
            boundary_label=f"PPS boundary {_fmt_analysis_value(boundary_x)} ms" if boundary_x is not None else "",
            raw_points=raw_points,
            show_observed=self._toggle_checked("observed_means", True),
            show_uncertainty=self._toggle_checked("uncertainty_band", True),
            show_raw_points=bool(raw_points),
            show_boundary=self._toggle_checked("pps_boundary", True),
            show_low_n_markers=self._toggle_checked("low_n_markers", True),
        )
        self.detail_text.setPlainText(
            self._detail_text(scope, requested_model, resolved_model, fit, observed, available, metric, source_mode, grouping)
        )

    def _detail_text(
        self,
        scope: str,
        requested_model: str,
        resolved_model: str,
        fit: dict[str, Any] | None,
        observed: list[dict[str, float | str]],
        available: list[str],
        metric: str,
        source_mode: str,
        grouping: str,
    ) -> str:
        lines = [f"View: {VIEW_LABELS.get(self.current_view, self.current_view)}"]
        lines.append(f"Scope: {scope}")
        lines.append(f"Part summary: {PART_AGGREGATION_LABELS.get(self.current_part_mode, self.current_part_mode)}")
        lines.append(f"Metric: {METRIC_LABELS.get(metric, _metric_display(metric))}")
        lines.append(f"Source: {SOURCE_LABELS.get(source_mode, source_mode)}")
        if grouping:
            lines.append(f"Grouping lens: {GROUPING_LABELS.get(grouping, grouping)}")
        if self.current_view == VIEW_DATA_BEHAVIOR:
            lines.append("")
            lines.append("Exploratory data-behavior signals")
            signals = behavior_signals_for_scope(self.data, scope, self.current_part_mode)
            if signals:
                for row in signals[:10]:
                    lines.append(
                        f"- {row.get('signal', '')}: {row.get('feature', '')} - {row.get('message', '')} ({row.get('evidence', '')})"
                    )
            else:
                lines.append("- Insufficient evidence: No behavior-signal artifact was available for this session.")
            counts = behavior_signal_counts(self.data)
            if counts:
                ordered = [f"{label} {counts[label]}" for label in sorted(counts) if counts.get(label)]
                lines.append("Signal mix: " + ", ".join(ordered))
            note = str(self.data.exploratory_quality_summary.get("interpretation_note") or "").strip()
            if note:
                lines.append("")
                lines.append(note)
        elif self.current_view == "responses":
            lines.extend(self._response_detail_lines(scope, source_mode))
        elif self.current_view == "timing_evidence":
            lines.extend(self._timing_detail_lines())
        elif self.current_view == "topup":
            lines.extend(self._topup_detail_lines())
        elif self.current_view == "artifacts":
            lines.extend(self._artifact_detail_lines())
        comparison = scope_comparison_row(self.data, scope, self.current_part_mode)
        best = str(comparison.get("best_model") or "").strip()
        if best and self.current_view in {VIEW_DATA_BEHAVIOR, VIEW_MODEL_FITS}:
            lines.append(f"Best model by AIC: {MODEL_LABELS.get(best, best)}")
            lines.append(f"Best AIC: {_fmt_analysis_value(comparison.get('best_aic'))}")
            lines.append(f"Best R2: {_fmt_analysis_value(comparison.get('best_r2'))}")
        lines.append(f"Observed point count: {len(observed)}")
        spread_labels = sorted({str(point.get("spread_label") or "").strip() for point in observed if str(point.get("spread_label") or "").strip()})
        if spread_labels:
            lines.append(f"Displayed range: +/- {'/'.join(spread_labels)} around each SOA mean")
        if available and self.current_view in {VIEW_DATA_BEHAVIOR, VIEW_MODEL_FITS}:
            lines.append("Available displays: " + ", ".join(MODEL_LABELS.get(model, model) for model in available))
        if requested_model == MODEL_COMPARE_ALL and self.current_view in {VIEW_DATA_BEHAVIOR, VIEW_MODEL_FITS}:
            displayed = [model for model in (MODEL_SIGMOID, MODEL_LINEAR, MODEL_LOGARITHMIC_DECAY) if model in available]
            if displayed:
                lines.append("Displayed models: " + ", ".join(MODEL_LABELS.get(model, model) for model in displayed))
        elif requested_model == MODEL_BEST and resolved_model and self.current_view in {VIEW_DATA_BEHAVIOR, VIEW_MODEL_FITS}:
            lines.append(f"Displayed model: {MODEL_LABELS.get(resolved_model, resolved_model)}")
        elif requested_model != MODEL_BEST and self.current_view in {VIEW_DATA_BEHAVIOR, VIEW_MODEL_FITS}:
            lines.append(f"Displayed model: {MODEL_LABELS.get(requested_model, requested_model)}")
        if requested_model == MODEL_COMPARE_ALL and self.current_view in {VIEW_DATA_BEHAVIOR, VIEW_MODEL_FITS}:
            sigmoid_fit = fit_row_for_scope(self.data, scope, MODEL_SIGMOID, self.current_part_mode)
            if sigmoid_fit is not None and sigmoid_fit.get("pps_boundary_soa_ms") not in (None, ""):
                lines.append(f"Sigmoid PPS boundary: {_fmt_analysis_value(sigmoid_fit.get('pps_boundary_soa_ms'))} ms")
        elif fit is None and self.current_view == VIEW_MODEL_FITS:
            lines.append("")
            lines.append("This model was not fit for the selected condition, usually because there were too few usable SOA points.")
        elif fit is not None and self.current_view == VIEW_MODEL_FITS:
            lines.append("")
            lines.append("Fit parameters")
            for key in (
                "lower",
                "upper",
                "pps_boundary_soa_ms",
                "slope",
                "intercept",
                "log_slope",
                "r2",
                "rmse",
                "rss",
                "aic",
                "n_points",
                "fit_metric",
            ):
                if key in fit and fit.get(key) not in (None, ""):
                    lines.append(f"- {key}: {_fmt_analysis_value(fit.get(key))}")
        if self.data.summary_text:
            lines.append("")
            lines.append("Session summary")
            lines.extend(str(self.data.summary_text).splitlines()[:8])
        if self.data.warnings:
            lines.append("")
            lines.append("Warnings")
            lines.extend(f"- {warning}" for warning in self.data.warnings[:6])
        return "\n".join(lines)

    def _response_detail_lines(self, scope: str, source_mode: str) -> list[str]:
        final_rows = self.data.final_outcome_rows or self.data.response_rows
        scoped = []
        for row in final_rows:
            part = _analysis_int(row.get("part_number"))
            part_label = "All parts" if self.current_part_mode == PARTS_POOLED and part is not None else (f"Part {part}" if part is not None else "")
            condition = str(row.get("condition") or "").strip()
            if condition.lower().startswith("part ") and condition[5:].strip().isdigit():
                condition = ""
            row_scope = " / ".join(part for part in (part_label, condition, str(row.get("respiratory_phase") or "").strip(), str(row.get("noise_type") or "").strip()) if part)
            if row_scope == scope:
                scoped.append(row)
        hits = sum(1 for row in scoped if _analysis_truthy(row.get("hit")))
        rescues = sum(1 for row in scoped if _analysis_truthy(row.get("rescued_in_topup")))
        return [
            "",
            "Response behavior",
            f"- Source lens: {SOURCE_LABELS.get(source_mode, source_mode)}",
            f"- Scoped tactile rows: {len(scoped)}",
            f"- Selected hits: {hits}",
            f"- Top-up rescues in scope: {rescues}",
        ]

    def _timing_detail_lines(self) -> list[str]:
        delays = [_analysis_float(row.get("marker_minus_mouse_ms")) for row in self.data.timing_qc_rows]
        delays = [value for value in delays if value is not None]
        qualities: dict[str, int] = {}
        for row in self.data.event_rows:
            quality = str(row.get("timestamp_quality") or "").strip()
            if quality:
                qualities[quality] = qualities.get(quality, 0) + 1
        lines = ["", "Timing evidence"]
        lines.append(f"- Timing QC rows: {len(self.data.timing_qc_rows)}")
        if delays:
            mean = sum(delays) / len(delays)
            lines.append(f"- Marker-minus-mouse delay mean: {_fmt_analysis_value(mean)} ms")
            lines.append(f"- Marker-minus-mouse delay range: {_fmt_analysis_value(min(delays))} to {_fmt_analysis_value(max(delays))} ms")
        if qualities:
            lines.append("- Timestamp qualities: " + ", ".join(f"{key} {value}" for key, value in sorted(qualities.items())))
        return lines

    def _topup_detail_lines(self) -> list[str]:
        final_rows = self.data.final_outcome_rows or self.data.response_rows
        rescues = [row for row in final_rows if _analysis_truthy(row.get("rescued_in_topup"))]
        fillers = [row for row in self.data.response_rows if str(row.get("topup_role") or "").strip().lower() == "filler"]
        unresolved = [row for row in final_rows if not _analysis_truthy(row.get("hit"))]
        return [
            "",
            "Top-up behavior",
            f"- Rescued final outcomes: {len(rescues)}",
            f"- Filler rows excluded from primary analysis: {len(fillers)}",
            f"- Final misses still present: {len(unresolved)}",
        ]

    def _artifact_detail_lines(self) -> list[str]:
        rows = artifact_rows_for_review(self.data)
        lines = ["", "Artifact evidence"]
        if not rows:
            return lines + ["- No artifact path inventory was available."]
        lines.extend(f"- {row['artifact']}: {row['available']} ({row['path']})" for row in rows[:12])
        return lines

    def _empty_detail_text(self) -> str:
        lines = ["No model-fit tables were available for review."]
        if self.data.summary_text:
            lines.append("")
            lines.append(self.data.summary_text)
        if self.data.warnings:
            lines.append("")
            lines.extend(f"- {warning}" for warning in self.data.warnings[:6])
        return "\n".join(lines)


def _fmt_analysis_value(value: Any) -> str:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return "" if value in (None, "") else str(value)
    if not math.isfinite(parsed):
        return "n/a"
    if abs(parsed) >= 100:
        return f"{parsed:.1f}"
    if abs(parsed) >= 10:
        return f"{parsed:.2f}"
    return f"{parsed:.3f}"


def _analysis_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _analysis_int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _analysis_truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _metric_display(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered == "facilitation_ms":
        return "Facilitation (ms)"
    if lowered == "mean_rt_ms":
        return "Mean RT (ms)"
    return text.replace("_", " ")


def _create_tactile_timeline_widget(
    q: dict[str, Any],
    state: TactileTimelineState,
    profile: FocusLayoutProfile | None = None,
    state_provider: Callable[[], TactileTimelineState] | None = None,
) -> Any:
    class TactileTimelineWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            self._row_names = tuple(TIMELINE_ROW_NAMES)
            self._label_fit_stats = {
                "drawn": 0,
                "shrunk": 0,
                "elided": 0,
                "skipped": 0,
                "skipped_repeated": 0,
                "overlap_count": 0,
            }
            self.setMinimumHeight(_timeline_widget_minimum_height(profile))

        def timeline_debug_snapshot(self) -> dict[str, Any]:
            return {
                "row_count": len(self._row_names),
                "row_names": list(self._row_names),
                "label_fit": dict(self._label_fit_stats),
                "minimum_height": int(self.minimumHeight()),
            }

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            fit_stats = {
                "drawn": 0,
                "shrunk": 0,
                "elided": 0,
                "skipped": 0,
                "skipped_repeated": 0,
                "overlap_count": 0,
            }
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                width = max(1, int(self.width()))
                height = max(1, int(self.height()))
                label_width = TIMELINE_LABEL_WIDTH
                right_margin = TIMELINE_RIGHT_MARGIN
                compact_rows = height < 96
                very_compact_rows = height < 84
                usable = max(1, width - label_width - right_margin)
                timeline_state = state_provider() if state_provider is not None else state
                duration = max(0.001, float(timeline_state.duration_s or 0.0))
                top_y = 5 if very_compact_rows else (8 if compact_rows else 14)
                bottom_y = max(top_y + 1, height - (5 if very_compact_rows else (8 if compact_rows else 12)))
                if len(self._row_names) == 1:
                    row_y_values = [int((top_y + bottom_y) / 2)]
                else:
                    row_gap = (bottom_y - top_y) / max(1, len(self._row_names) - 1)
                    row_y_values = [int(round(top_y + index * row_gap)) for index in range(len(self._row_names))]
                rows = list(zip(self._row_names, row_y_values))
                row_y_by_name = {label: row_y for label, row_y in rows}

                painter.fillRect(self.rect(), q["QColor"]("#f8f9f6"))
                label_pen = q["QPen"](q["QColor"]("#647067"))
                painter.setPen(label_pen)
                for label, row_y in rows:
                    label_height = 8 if height < 55 else (10 if very_compact_rows else (14 if compact_rows else 18))
                    painter.drawText(
                        4,
                        max(0, row_y - label_height // 2),
                        label_width - 8,
                        label_height,
                        int(q["Qt"].AlignmentFlag.AlignRight | q["Qt"].AlignmentFlag.AlignVCenter),
                        label,
                    )
                    guide_pen = q["QPen"](q["QColor"]("#d9dfd6"))
                    guide_pen.setWidth(1)
                    painter.setPen(guide_pen)
                    painter.drawLine(label_width, row_y, width - right_margin, row_y)
                    painter.setPen(label_pen)

                if not timeline_state.cues and not timeline_state.trial_segments and not timeline_state.click_markers:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, "No experiment schedule loaded")
                    return

                def _x(time_s: float) -> int:
                    return label_width + int(max(0.0, min(1.0, float(time_s) / duration)) * usable)

                def _clean_label(text: str) -> str:
                    clean = " ".join(str(text or "").replace("|", " ").split())
                    return clean

                palette = ["#dcefeb", "#f4e2b8", "#e7dff0", "#dce7f4", "#f0dddd", "#e3ead8"]

                def _color_for(label: str, fallback_index: int) -> str:
                    text = str(label or "").strip().lower()
                    if "inhale" in text:
                        return "#dce7f4"
                    if "exhale" in text:
                        return "#e7dff0"
                    if "baseline" in text:
                        return "#e3ead8"
                    if "catch" in text:
                        return "#f4e2b8"
                    if "audio" in text and "tactile" in text:
                        return "#dcefeb"
                    return palette[fallback_index % len(palette)]

                def _soa_color(value: str) -> str:
                    try:
                        soa = float(str(value).strip())
                    except (TypeError, ValueError):
                        return "#f1f5f9"
                    if soa <= 0:
                        return "#e4e7eb"
                    if soa <= 300:
                        return "#dce7f4"
                    if soa <= 800:
                        return "#dcefeb"
                    if soa <= 1500:
                        return "#f4e2b8"
                    if soa <= 2200:
                        return "#eadcf0"
                    return "#f0dddd"

                def _noise_label(value: str) -> str:
                    text = str(value or "").strip()
                    if not text:
                        return "Noise"
                    return text.replace("_", " ").title()

                def _noise_color(value: str, fallback_index: int) -> str:
                    text = str(value or "").strip().lower()
                    colors = {
                        "pink": "#f5d5e0",
                        "white": "#e5e7eb",
                        "blue": "#dbeafe",
                        "brown": "#e8dcc9",
                        "violet": "#e9d5ff",
                        "custom_audio": "#dbe8dc",
                    }
                    return colors.get(text, palette[(fallback_index + 3) % len(palette)])

                row_height = 6 if height < 55 else (8 if very_compact_rows else (12 if compact_rows else 16))
                last_text_by_row: dict[str, str] = {}
                drawn_rects_by_row: dict[str, tuple[int, int, int, int]] = {}
                text_alignment = int(q["Qt"].AlignmentFlag.AlignLeft | q["Qt"].AlignmentFlag.AlignVCenter)
                text_elide_enum = getattr(q["Qt"], "TextElideMode", None)
                text_elide_mode = getattr(text_elide_enum, "ElideRight", None) if text_elide_enum is not None else None
                if text_elide_mode is None:
                    text_elide_mode = q["Qt"].ElideRight

                def _advance(metrics: Any, text: str) -> int:
                    try:
                        return int(metrics.horizontalAdvance(text))
                    except AttributeError:
                        return int(metrics.width(text))

                def _draw_fitted_text(
                    row_name: str,
                    x: int,
                    y: int,
                    box_width: int,
                    box_height: int,
                    text: str,
                    color: str,
                    *,
                    optional: bool = True,
                ) -> None:
                    clean = _clean_label(text)
                    text_width = max(0, int(box_width) - 6)
                    if not clean or text_width <= 0:
                        fit_stats["skipped"] += 1
                        return
                    if optional and box_width < TIMELINE_SEGMENT_LABEL_SKIP_WIDTH:
                        fit_stats["skipped"] += 1
                        return
                    if optional and clean == last_text_by_row.get(row_name) and box_width < TIMELINE_REPEATED_LABEL_SKIP_WIDTH:
                        fit_stats["skipped"] += 1
                        fit_stats["skipped_repeated"] += 1
                        return

                    original_font = q["QFont"](painter.font())
                    base_font = q["QFont"](original_font)
                    base_point = float(base_font.pointSizeF())
                    if base_point <= 0:
                        base_point = float(profile.chip_font_pt if profile is not None else 9.0)
                        base_font.setPointSizeF(base_point)
                    min_point = max(5.8 if very_compact_rows else 6.4, base_point - (2.2 if compact_rows else 1.8))
                    fitted_font = q["QFont"](base_font)
                    metrics = q["QFontMetrics"](fitted_font)
                    fitted_text = clean
                    fit_kind = "drawn"
                    if _advance(metrics, clean) > text_width:
                        point = base_point - 0.4
                        while point >= min_point:
                            trial_font = q["QFont"](base_font)
                            trial_font.setPointSizeF(point)
                            trial_metrics = q["QFontMetrics"](trial_font)
                            if _advance(trial_metrics, clean) <= text_width:
                                fitted_font = trial_font
                                metrics = trial_metrics
                                fit_kind = "shrunk"
                                break
                            point -= 0.4
                        else:
                            fitted_font = q["QFont"](base_font)
                            fitted_font.setPointSizeF(min_point)
                            metrics = q["QFontMetrics"](fitted_font)
                            fitted_text = str(metrics.elidedText(clean, text_elide_mode, text_width))
                            if not fitted_text.strip():
                                fit_stats["skipped"] += 1
                                return
                            fit_kind = "elided"

                    previous = drawn_rects_by_row.get(row_name)
                    if previous is not None and x < previous[2]:
                        fit_stats["overlap_count"] += 1
                    drawn_rects_by_row[row_name] = (x, y, x + max(1, box_width), y + max(1, box_height))
                    last_text_by_row[row_name] = clean
                    painter.setFont(fitted_font)
                    painter.setPen(q["QPen"](q["QColor"](color)))
                    painter.drawText(x + 3, y + 1, max(1, text_width), max(1, box_height - 2), text_alignment, fitted_text)
                    painter.setFont(original_font)
                    fit_stats["drawn"] += 1
                    if fit_kind in ("shrunk", "elided"):
                        fit_stats[fit_kind] += 1

                for index, segment in enumerate(timeline_state.trial_segments):
                    x1 = _x(segment.start_s)
                    x2 = max(x1 + 2, _x(segment.end_s))
                    clip_color = _color_for(segment.clip_label, index)
                    trial_color = _color_for(segment.trial_label, index + 2)
                    for row_name, text, y, color in (
                        (
                            "Resp",
                            segment.clip_label or "Resp",
                            row_y_by_name["Resp"] - row_height // 2,
                            clip_color,
                        ),
                        (
                            "Type",
                            segment.trial_label or segment.family or "Type",
                            row_y_by_name["Type"] - row_height // 2,
                            trial_color,
                        ),
                        (
                            "Noise",
                            _noise_label(segment.noise_type),
                            row_y_by_name["Noise"] - row_height // 2,
                            _noise_color(segment.noise_type, index),
                        ),
                        (
                            "SOA",
                            _timeline_soa_display_label(segment),
                            row_y_by_name["SOA"] - row_height // 2,
                            _soa_color(segment.soa_ms),
                        )
                    ):
                        segment_width = max(2, x2 - x1)
                        painter.setPen(q["QPen"](q["QColor"]("#bcc7bd")))
                        painter.setBrush(q["QBrush"](q["QColor"](color)))
                        painter.drawRoundedRect(x1, y, segment_width, row_height, 4, 4)
                        _draw_fitted_text(
                            row_name,
                            x1,
                            y,
                            segment_width,
                            row_height,
                            text,
                            "#202621",
                            optional=_timeline_row_label_optional(row_name),
                        )

                tactile_y = row_y_by_name["Tactile"]
                for cue in timeline_state.cues:
                    status = timeline_state.cue_status(cue)
                    color = {
                        "passed": "#647067",
                        "recentered": "#246b55",
                        "next": "#8c2f2f",
                        "upcoming": "#d9dfd6",
                    }.get(status, "#d9dfd6")
                    x = _x(cue.time_s)
                    radius = 5 if status == "next" else 4
                    marker_pen = q["QPen"](q["QColor"]("#202621" if status == "next" else "#bcc7bd"))
                    marker_pen.setWidth(1)
                    painter.setPen(marker_pen)
                    painter.setBrush(q["QBrush"](q["QColor"](color)))
                    painter.drawEllipse(x - radius, tactile_y - radius, radius * 2, radius * 2)

                click_y = row_y_by_name["Clicks"]
                for marker in timeline_state.click_markers:
                    x = _x(marker.time_s)
                    response_click = str(getattr(marker, "response_status", "") or "") == "tactile_response"
                    pen_color = "#065f46" if response_click else "#9a3412"
                    fill_color = "#10b981" if response_click else "#f97316"
                    click_pen = q["QPen"](q["QColor"](pen_color))
                    click_pen.setWidth(2)
                    painter.setPen(click_pen)
                    painter.setBrush(q["QBrush"](q["QColor"](fill_color)))
                    click_radius = 4 if not very_compact_rows else 3
                    painter.drawEllipse(x - click_radius, click_y - click_radius, click_radius * 2, click_radius * 2)
                    overlay_radius = 3 if not very_compact_rows else 2
                    painter.drawEllipse(x - overlay_radius, tactile_y - overlay_radius, overlay_radius * 2, overlay_radius * 2)

                cursor_x = _x(timeline_state.elapsed_s)
                cursor_pen = q["QPen"](q["QColor"]("#b91c1c"))
                cursor_pen.setWidth(3)
                painter.setPen(cursor_pen)
                painter.drawLine(cursor_x, 4, cursor_x, min(height - 4, rows[-1][1] + (10 if very_compact_rows else 14)))
            finally:
                self._label_fit_stats = fit_stats
                painter.end()

    return TactileTimelineWidget()


def _create_block_plan_widget(q: dict[str, Any], owner: Any) -> Any:
    class BlockPlanWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            profile = getattr(owner, "layout_profile", None)
            self._compact = bool(profile is not None and profile.screen_class == "constrained")
            self.setMinimumHeight(36 if self._compact else 62)
            self.setCursor(q["Qt"].CursorShape.PointingHandCursor)
            self.setMouseTracking(True)

        def _instruction_slots_for_block_item(self, item: dict[str, Any]) -> list[dict[str, Any]]:
            handler = getattr(owner, "_instruction_slots_for_item", None)
            if not callable(handler):
                return []
            return [dict(slot) for slot in list(handler(item) or [])]

        def _visual_groups(self) -> list[list[dict[str, Any]]]:
            groups: list[list[dict[str, Any]]] = []
            for item in list(getattr(owner, "block_plan_items", []) or []):
                plan_item = dict(item)
                group: list[dict[str, Any]] = []
                if str(plan_item.get("kind") or "") == "standard":
                    slots = self._instruction_slots_for_block_item(plan_item)
                    before_slots = [
                        slot
                        for slot in slots
                        if str(slot.get("slot") or "") in {"before_experiment", "before_each_block"}
                    ]
                    after_slots = [
                        slot
                        for slot in slots
                        if str(slot.get("slot") or "") not in {"before_experiment", "before_each_block"}
                    ]
                    for slot in before_slots:
                        group.append(
                            {
                                "entry_kind": "instruction",
                                "placement": "before",
                                "block_number": int(plan_item.get("number") or 0),
                                **dict(slot),
                            }
                        )
                group.append({"entry_kind": "block", **plan_item})
                if str(plan_item.get("kind") or "") == "standard":
                    for slot in after_slots:
                        group.append(
                            {
                                "entry_kind": "instruction",
                                "placement": "after",
                                "block_number": int(plan_item.get("number") or 0),
                                **dict(slot),
                            }
                        )
                groups.append(group)
            return groups

        def _entry_size(self, entry: dict[str, Any]) -> tuple[int, int]:
            if str(entry.get("entry_kind") or "") == "instruction":
                return (10 if self._compact else 13, 16 if self._compact else 20)
            return (48 if self._compact else 68, 28 if self._compact else 32)

        def _layout_items_for_width(self, width: int) -> tuple[list[dict[str, Any]], int]:
            groups = self._visual_groups()
            if not groups:
                return [], 36 if self._compact else 58
            margin = 8
            gap = 4 if self._compact else 5
            row_height = 28 if self._compact else 32
            right_edge = max(margin + 1, int(width) - margin)
            available = max(1, right_edge - margin)
            x = margin
            y = margin
            layout_items: list[dict[str, Any]] = []

            def _wrap_row() -> None:
                nonlocal x, y
                x = margin
                y += row_height + gap

            for group in groups:
                group_width = sum(self._entry_size(entry)[0] for entry in group) + gap * max(0, len(group) - 1)
                if x > margin and group_width <= available and x + group_width > right_edge:
                    _wrap_row()
                for entry in group:
                    entry_width, entry_height = self._entry_size(entry)
                    if x > margin and x + entry_width > right_edge:
                        _wrap_row()
                    item_y = y + max(0, int((row_height - entry_height) / 2))
                    layout_entry = dict(entry)
                    layout_entry.update({"x": x, "y": item_y, "width": entry_width, "height": entry_height})
                    layout_items.append(layout_entry)
                    x += entry_width + gap
            target_height = max(36 if self._compact else 58, y + row_height + margin)
            return layout_items, target_height

        def refresh_layout_height(self) -> None:
            _items, target_height = self._layout_items_for_width(max(1, int(self.width())))
            if int(self.minimumHeight()) != int(target_height):
                self.setMinimumHeight(int(target_height))
                self.updateGeometry()
            owner_refresh = getattr(owner, "_refresh_experiment_control_minimum_height", None)
            if callable(owner_refresh):
                owner_refresh()

        def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            self.refresh_layout_height()

        def _layout_items(self) -> list[dict[str, Any]]:
            items, _target_height = self._layout_items_for_width(max(1, int(self.width())))
            return items

        def item_center(self, number: int) -> Any:
            for item in self._layout_items():
                if str(item.get("entry_kind") or "") == "block" and int(item.get("number") or 0) == int(number):
                    return q["QPoint"](
                        int(item["x"]) + int(item["width"]) // 2,
                        int(item["y"]) + int(item["height"]) // 2,
                    )
            return q["QPoint"](0, 0)

        def _item_at(self, point: Any) -> dict[str, Any] | None:
            px = int(point.x())
            py = int(point.y())
            for item in self._layout_items():
                x = int(item["x"])
                y = int(item["y"])
                width = int(item["width"])
                height = int(item["height"])
                if x <= px <= x + width and y <= py <= y + height:
                    return item
            return None

        def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            try:
                point = event.position().toPoint()
            except AttributeError:
                point = event.pos()
            item = self._item_at(point)
            if item is not None:
                if str(item.get("entry_kind") or "") == "instruction":
                    label = str(item.get("display_label") or item.get("label") or "Instruction")
                    mode = str(item.get("continue_mode") or "").replace("_", " ")
                    duration = float(item.get("duration_s") or 0.0)
                    self.setToolTip(f"{label} | {duration:.1f}s | {mode}".strip(" |"))
                else:
                    label = str(item.get("label") or "")
                    display = str(item.get("display_label") or f"Block {item.get('part_block_number') or item.get('number')}")
                    part = _part_button_label(str(item.get("part_key") or ""))
                    detail = f"{part} {display}"
                    if label and label != display:
                        detail = f"{detail}: {label}"
                    self.setToolTip(detail)
            super().mouseMoveEvent(event)

        def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            if event.button() == q["Qt"].MouseButton.LeftButton:
                try:
                    point = event.position().toPoint()
                except AttributeError:
                    point = event.pos()
                item = self._item_at(point)
                if item is not None and str(item.get("entry_kind") or "") == "block":
                    handler = getattr(owner, "_select_block_plan_item", None)
                    if callable(handler):
                        handler(int(item.get("number") or 0))
                    event.accept()
                    return
            super().mousePressEvent(event)

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                width = max(1, int(self.width()))
                height = max(1, int(self.height()))
                items = list(getattr(owner, "block_plan_items", []) or [])
                painter.fillRect(self.rect(), q["QColor"]("#f8f9f6"))
                if not items:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, "No blocks prepared")
                    return

                active = getattr(owner, "active_display_block_index", None)
                selected = getattr(owner, "selected_display_block_index", None)
                completed = set(getattr(owner, "completed_display_block_indices", set()) or set())
                next_index = None
                if active is None:
                    for item in items:
                        number = int(item.get("number") or 0)
                        if number and number not in completed:
                            next_index = number
                            break

                for item in self._layout_items():
                    x = int(item["x"])
                    y = int(item["y"])
                    box_width = int(item["width"])
                    box_height = int(item["height"])
                    if str(item.get("entry_kind") or "") == "instruction":
                        color = str(item.get("color") or _instruction_slot_color(str(item.get("slot") or "")))
                        painter.setPen(q["QPen"](q["QColor"]("#7d8b80")))
                        painter.setBrush(q["QBrush"](q["QColor"](color)))
                        painter.drawRoundedRect(x, y, box_width, box_height, 4, 4)
                        continue
                    number = int(item.get("number") or 0)
                    kind = str(item.get("kind") or "")
                    display_number = int(item.get("part_block_number") or number)
                    if number == active:
                        fill = "#246b55"
                        border = "#1d5846"
                        text = "#ffffff"
                    elif number in completed:
                        fill = "#dcefeb"
                        border = "#9fd0bd"
                        text = "#17634f"
                    elif number == next_index:
                        fill = "#f4e2b8"
                        border = "#d6a94d"
                        text = "#202621"
                    elif kind == "topup":
                        fill = "#f0dddd"
                        border = "#e3aca7"
                        text = "#8c2f2f"
                    else:
                        fill = "#ffffff"
                        border = "#bcc7bd"
                        text = "#202621"
                    painter.setPen(q["QPen"](q["QColor"](border)))
                    painter.setBrush(q["QBrush"](q["QColor"](fill)))
                    painter.drawRoundedRect(x, y, box_width, box_height, 5, 5)
                    painter.setPen(q["QPen"](q["QColor"](text)))
                    label = "TU" if kind == "topup" else f"{display_number}"
                    if box_width >= 68:
                        label = f"{display_number} TU" if kind == "topup" else f"Block {display_number}"
                    painter.drawText(x + 3, y + 2, box_width - 6, box_height - 4, q["Qt"].AlignmentFlag.AlignCenter, label)
                    if number == selected:
                        selected_pen = q["QPen"](q["QColor"]("#1d5d99"))
                        selected_pen.setWidth(3)
                        painter.setPen(selected_pen)
                        painter.setBrush(q["Qt"].BrushStyle.NoBrush)
                        painter.drawRoundedRect(x + 2, y + 2, box_width - 4, box_height - 4, 5, 5)
                    if number == active:
                        bar_pen = q["QPen"](q["QColor"]("#b91c1c"))
                        bar_pen.setWidth(4)
                        painter.setPen(bar_pen)
                        bar_x = x + max(4, box_width // 2)
                        painter.drawLine(bar_x, y + 4, bar_x, y + box_height - 4)
            finally:
                painter.end()

    return BlockPlanWidget()


def _create_instruction_legend_widget(q: dict[str, Any], owner: Any) -> Any:
    class InstructionLegendWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            profile = getattr(owner, "layout_profile", None)
            self._compact = bool(profile is not None and profile.compact)
            self.setMinimumHeight(34 if self._compact else 44)
            self.setMouseTracking(True)

        def _items(self) -> list[dict[str, Any]]:
            return [dict(item) for item in _enabled_instruction_slots(getattr(owner, "package", None))]

        def _layout_items_for_width(self, width: int) -> tuple[list[dict[str, Any]], int]:
            raw_items = self._items()
            if not raw_items:
                return [], 30 if self._compact else 36
            margin = 4
            gap = 8
            row_gap = 5
            swatch = 10 if self._compact else 12
            row_height = 18 if self._compact else 20
            right_edge = max(margin + 1, int(width) - margin)
            x = margin
            y = margin
            layout_items: list[dict[str, Any]] = []
            metrics = self.fontMetrics()
            for item in raw_items:
                label = str(item.get("display_label") or item.get("label") or "Instruction")
                try:
                    text_width = int(metrics.horizontalAdvance(label))
                except AttributeError:
                    text_width = int(metrics.width(label))
                entry_width = min(max(swatch + 6 + text_width, 70 if self._compact else 82), 150)
                if x > margin and x + entry_width > right_edge:
                    x = margin
                    y += row_height + row_gap
                entry = dict(item)
                entry.update({"x": x, "y": y, "width": entry_width, "height": row_height, "swatch": swatch})
                layout_items.append(entry)
                x += entry_width + gap
            target_height = max(34 if self._compact else 44, y + row_height + margin)
            return layout_items, target_height

        def refresh_layout_height(self) -> None:
            _items, target = self._layout_items_for_width(max(1, int(self.width())))
            if int(self.minimumHeight()) != int(target):
                self.setMinimumHeight(int(target))
                self.updateGeometry()

        def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            self.refresh_layout_height()

        def _layout_items(self) -> list[dict[str, Any]]:
            items, _target = self._layout_items_for_width(max(1, int(self.width())))
            return items

        def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            try:
                point = event.position().toPoint()
            except AttributeError:
                point = event.pos()
            px = int(point.x())
            py = int(point.y())
            for item in self._layout_items():
                x = int(item["x"])
                y = int(item["y"])
                width = int(item["width"])
                height = int(item["height"])
                if x <= px <= x + width and y <= py <= y + height:
                    label = str(item.get("label") or item.get("display_label") or "Instruction")
                    mode = str(item.get("continue_mode") or "").replace("_", " ")
                    duration = float(item.get("duration_s") or 0.0)
                    self.setToolTip(f"{label} | {duration:.1f}s | {mode}".strip(" |"))
                    break
            super().mouseMoveEvent(event)

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                painter.fillRect(self.rect(), q["QColor"]("#f8f9f6"))
                items = self._layout_items()
                if not items:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, "No instruction clips")
                    return
                for item in items:
                    x = int(item["x"])
                    y = int(item["y"])
                    height = int(item["height"])
                    swatch = int(item["swatch"])
                    color = str(item.get("color") or _instruction_slot_color(str(item.get("slot") or "")))
                    painter.setPen(q["QPen"](q["QColor"]("#7d8b80")))
                    painter.setBrush(q["QBrush"](q["QColor"](color)))
                    painter.drawRoundedRect(x, y + max(0, (height - swatch) // 2), swatch, swatch, 3, 3)
                    painter.setPen(q["QPen"](q["QColor"]("#202621")))
                    text = str(item.get("display_label") or item.get("label") or "Instruction")
                    painter.drawText(
                        x + swatch + 5,
                        y,
                        max(1, int(item["width"]) - swatch - 5),
                        height,
                        int(q["Qt"].AlignmentFlag.AlignVCenter),
                        text,
                    )
            finally:
                painter.end()

    return InstructionLegendWidget()


def _create_topup_draft_widget(q: dict[str, Any], owner: Any) -> Any:
    class TopupDraftWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            profile = getattr(owner, "layout_profile", None)
            self._compact = bool(profile is not None and profile.screen_class == "constrained")
            self.setMinimumHeight(34 if self._compact else 42)
            self.setCursor(q["Qt"].CursorShape.PointingHandCursor)

        def refresh_layout_height(self) -> None:
            items = list(getattr(owner, "_visible_topup_draft_items", lambda: [])() or [])
            margin = 8
            gap = 5
            box_height = 18 if self._compact else 22
            if not items:
                target_height = 34 if self._compact else 42
            else:
                columns = max(1, min(len(items), int(max(1, self.width() - 16) / (132 if self._compact else 170))))
                rows = int(math.ceil(len(items) / columns))
                target_height = (2 * margin) + rows * box_height + max(0, rows - 1) * gap
                target_height = max(34 if self._compact else 42, target_height)
            if int(self.minimumHeight()) != int(target_height):
                self.setMinimumHeight(int(target_height))
                self.updateGeometry()

        def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            self.refresh_layout_height()

        def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            if event.button() == q["Qt"].MouseButton.LeftButton:
                handler = getattr(owner, "_select_current_part_topup_slot", None)
                if callable(handler):
                    handler()
                    event.accept()
                    return
            super().mousePressEvent(event)

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                painter.fillRect(self.rect(), q["QColor"]("#f8f9f6"))
                items = list(getattr(owner, "_visible_topup_draft_items", lambda: [])() or [])
                part_label = _part_button_label(str(getattr(owner, "selected_part_key", "") or "1"))
                enabled = bool(getattr(owner, "_topup_slots_enabled_for_plan", lambda: False)())
                if not enabled:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, "Top-up block disabled")
                    return
                if not items:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, f"{part_label} top-up draft: no missed tactile trials yet")
                    return
                margin = 8
                gap = 5
                box_height = 18 if self._compact else 22
                columns = max(1, min(len(items), int(max(1, self.width() - 16) / (132 if self._compact else 170))))
                available = max(1, int(self.width()) - (2 * margin) - gap * (columns - 1))
                box_width = max(120 if self._compact else 150, int(available / columns))
                for index, item in enumerate(items):
                    row = int(index / columns)
                    column = index % columns
                    x = margin + column * (box_width + gap)
                    y = margin + row * (box_height + gap)
                    color = _trial_type_color(item.get("trial_type", ""), item.get("family", ""))
                    painter.setPen(q["QPen"](q["QColor"]("#bcc7bd")))
                    painter.setBrush(q["QBrush"](q["QColor"](color)))
                    painter.drawRoundedRect(x, y, box_width, box_height, 5, 5)
                    label = _topup_draft_item_label(item, compact=self._compact)
                    try:
                        elide_mode = q["Qt"].TextElideMode.ElideRight
                    except AttributeError:
                        elide_mode = q["Qt"].ElideRight
                    label = str(painter.fontMetrics().elidedText(label, elide_mode, max(1, box_width - 8)))
                    painter.setPen(q["QPen"](q["QColor"]("#202621")))
                    painter.drawText(x + 4, y + 1, box_width - 8, box_height - 2, int(q["Qt"].AlignmentFlag.AlignVCenter), label)
            finally:
                painter.end()

    return TopupDraftWidget()


def _create_response_target_button(q: dict[str, Any], profile: FocusLayoutProfile) -> Any:
    class BullseyeTargetButton(q["QWidget"]):
        clicked = q["Signal"]()

        def __init__(self) -> None:
            super().__init__()
            self._pressed = False
            self.last_click_global_pos: tuple[int, int] | None = None
            self.setObjectName("targetButton")
            self.setAccessibleName("CLICK response target")
            self.setToolTip("Participant response target")
            self.setFixedSize(profile.target_min_height, profile.target_min_height)
            self.setSizePolicy(q["QSizePolicy"].Policy.Fixed, q["QSizePolicy"].Policy.Fixed)
            self.setCursor(q["Qt"].CursorShape.PointingHandCursor)
            self.setMouseTracking(True)

        def text(self) -> str:
            return "CLICK"

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                rect = self.rect().adjusted(1, 1, -2, -2)
                enabled = bool(self.isEnabled())
                pressed = enabled and self._pressed
                hovered = enabled and bool(self.underMouse())
                background = "#e9f4ef" if pressed else ("#ffffff" if hovered else "#f8f9f6")
                border = "#246b55" if (pressed or hovered) else "#bcc7bd"
                if not enabled:
                    background = "#eef0eb"
                    border = "#d7ded5"

                border_pen = q["QPen"](q["QColor"](border))
                border_pen.setWidth(2)
                painter.setPen(border_pen)
                painter.setBrush(q["QBrush"](q["QColor"](background)))
                painter.drawRoundedRect(rect, 6, 6)

                side = max(1, min(rect.width(), rect.height()))
                center = rect.center()
                cx = int(center.x())
                cy = int(center.y())
                outer = max(24, int(side * 0.34))
                middle = max(14, int(side * 0.22))
                inner = max(6, int(side * 0.09))
                ring_color = "#8c2f2f" if enabled else "#9ba59d"
                accent_color = "#246b55" if enabled else "#9ba59d"
                fill_color = "#ffffff" if enabled else "#f4f5f1"

                painter.setBrush(q["QBrush"](q["QColor"](fill_color)))
                ring_pen = q["QPen"](q["QColor"](ring_color))
                ring_pen.setWidth(3)
                painter.setPen(ring_pen)
                painter.drawEllipse(cx - outer, cy - outer, outer * 2, outer * 2)

                accent_pen = q["QPen"](q["QColor"](accent_color))
                accent_pen.setWidth(3)
                painter.setPen(accent_pen)
                painter.drawEllipse(cx - middle, cy - middle, middle * 2, middle * 2)

                painter.setPen(q["QPen"](q["QColor"](ring_color)))
                painter.setBrush(q["QBrush"](q["QColor"](ring_color)))
                painter.drawEllipse(cx - inner, cy - inner, inner * 2, inner * 2)
            finally:
                painter.end()

        def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            if self.isEnabled() and event.button() == q["Qt"].MouseButton.LeftButton:
                self._pressed = True
                self.update()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            was_pressed = self._pressed
            self._pressed = False
            self.update()
            if self.isEnabled() and was_pressed and event.button() == q["Qt"].MouseButton.LeftButton:
                try:
                    point = event.position().toPoint()
                except AttributeError:
                    point = event.pos()
                if self.rect().contains(point):
                    try:
                        global_point = event.globalPosition().toPoint()
                    except AttributeError:
                        global_point = event.globalPos()
                    self.last_click_global_pos = (int(global_point.x()), int(global_point.y()))
                    self.clicked.emit()
                event.accept()
                return
            super().mouseReleaseEvent(event)

    return BullseyeTargetButton()


def _combo(q: dict[str, Any], values: list[tuple[str, str]], *, current: str = "") -> Any:
    combo = q["QComboBox"]()
    for value, label in values:
        combo.addItem(label, value)
    if current:
        index = combo.findData(current)
        if index >= 0:
            combo.setCurrentIndex(index)
    return combo


def _set_combo_data(combo: Any, value: str) -> bool:
    index = combo.findData(str(value or ""))
    if index < 0:
        return False
    combo.setCurrentIndex(index)
    return True


def _qt_font_family(q: dict[str, Any]) -> str:
    try:
        families = set(q["QFontDatabase"].families())
    except Exception:
        families = set()
    for family in ("Calibri", "Aptos", "Microsoft Sans Serif", "Tahoma", "Verdana"):
        if family in families:
            return family
    try:
        app = q["QApplication"].instance()
        application_family = str(app.font().family()) if app is not None else ""
    except Exception:
        application_family = ""
    if application_family in families:
        return application_family
    if families:
        return sorted(families)[0]
    return "Calibri"


def _focus_style_sheet(q: dict[str, Any], profile: FocusLayoutProfile) -> str:
    return render_focus_style_sheet(profile, font_family=_qt_font_family(q))


def _screen_fit_size(
    q: dict[str, Any],
    *,
    target_width: int,
    target_height: int,
    min_width: int,
    min_height: int,
) -> tuple[int, int, int, int]:
    profile = _focus_layout_profile(
        q,
        target_width=target_width,
        target_height=target_height,
        min_width=min_width,
        min_height=min_height,
    )
    return profile.window_width, profile.window_height, profile.min_width, profile.min_height


def _focus_layout_profile(
    q: dict[str, Any],
    *,
    target_width: int = 3840,
    target_height: int = 900,
    min_width: int = 820,
    min_height: int = 520,
) -> FocusLayoutProfile:
    app = q["QApplication"].instance()
    screen = app.primaryScreen() if app is not None else None
    if screen is None:
        return render_focus_layout_profile(
            target_width,
            target_height,
            target_width=target_width,
            target_height=target_height,
            min_width=min_width,
            min_height=min_height,
        )
    geometry = screen.availableGeometry()
    return render_focus_layout_profile(
        int(geometry.width()),
        int(geometry.height()),
        target_width=target_width,
        target_height=target_height,
        min_width=min_width,
        min_height=min_height,
    )


def _capture_options_from_args(args: argparse.Namespace) -> SessionCaptureOptions:
    return SessionCaptureOptions(
        enable_lsl=not args.no_lsl,
        write_internal_xdf=not args.no_internal_xdf,
        write_analysis_csvs=not args.no_analysis_csv,
        start_backup_recording=not args.no_backup_recording,
        wired_loopback_mode=normalize_wired_loopback_mode(args.wired_loopback),
        start_external_labrecorder=bool(args.external_labrecorder and not args.no_lsl),
        external_labrecorder_cli=str(args.labrecorder_cli or ""),
        external_labrecorder_stream_timeout_s=float(args.labrecorder_stream_timeout_s),
        external_labrecorder_startup_s=float(args.labrecorder_startup_s),
        external_labrecorder_stop_timeout_s=float(args.labrecorder_stop_timeout_s),
    )


def _is_launchable_session_manifest(path: Path) -> bool:
    try:
        package = load_run_package(path)
    except Exception:
        return False
    if not package.blocks:
        return False
    if package.source_run_setup_manifest_path is None:
        return True
    current, _message = prepared_session_manifest_current_status(path)
    return current


def _path_is_inside_root(path: Path, root: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (OSError, ValueError):
        return False


def prepare_latest_focus_session(
    participant_id: str | None = None,
    *,
    session_root: Path | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    """Materialize a session package from the newest prepared Segment 6 setup."""
    validation_output_root = os.environ.get("PPS_FOCUS_VALIDATION_OUTPUT_ROOT", "").strip()
    if session_root is not None:
        output_root = Path(session_root)
    elif validation_output_root:
        output_root = Path(validation_output_root).expanduser()
    else:
        output_root = active_output_folder(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            fallback=DEFAULT_SESSION_ROOT,
        )
    run_setup = find_latest_dashboard_run_setup()
    if run_setup is None:
        raise FileNotFoundError("No prepared Segment 6 dashboard setup was found.")
    participant = (participant_id or "").strip()
    if not participant:
        participants = segment_run_setup_participants(run_setup)
        if not participants:
            raise ValueError(f"Prepared setup has no participants: {run_setup}")
        participant = participants[0]
    claimed = claim_prepared_session(
        run_setup,
        participant,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        session_root=output_root,
    )
    if claimed is not None:
        return claimed
    package = prepare_segment_run_package(
        run_setup,
        participant,
        session_root=output_root,
        progress_callback=progress_callback,
    )
    record_experiment_activity(
        "session_prepared",
        run_setup_manifest_path=str(run_setup),
        session_manifest_path=str(package.manifest_path),
        session_dir=str(package.session_dir),
        participant_id=participant,
    )
    update_profile_runner_settings(
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        output_folder=output_root,
        participant_id=participant,
        run_setup_manifest_path=run_setup,
        session_manifest_path=package.manifest_path,
    )
    return package.manifest_path


def prepare_last_or_latest_focus_session(
    participant_id: str | None = None,
    *,
    session_root: Path | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    """Open the last launchable session, falling back to the newest prepared setup."""
    validation_output_root = os.environ.get("PPS_FOCUS_VALIDATION_OUTPUT_ROOT", "").strip()
    if session_root is not None:
        output_root = Path(session_root)
    elif validation_output_root:
        output_root = Path(validation_output_root).expanduser()
    else:
        output_root = active_output_folder(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            fallback=DEFAULT_SESSION_ROOT,
        )
    pointer = load_last_experiment_pointer()
    session_text = str(pointer.get("session_manifest_path") or "").strip()
    session_manifest = Path(session_text) if session_text else Path()
    if (
        session_text
        and _path_is_inside_root(session_manifest, output_root)
        and _is_launchable_session_manifest(session_manifest)
    ):
        return session_manifest
    run_setup_text = str(pointer.get("run_setup_manifest_path") or "").strip()
    run_setup = Path(run_setup_text) if run_setup_text else Path()
    if run_setup_text and run_setup.exists():
        participant = (participant_id or str(pointer.get("participant_id") or "")).strip()
        if not participant:
            participants = segment_run_setup_participants(run_setup)
            participant = participants[0] if participants else ""
        if participant:
            claimed = claim_prepared_session(
                run_setup,
                participant,
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                session_root=output_root,
            )
            if claimed is not None:
                return claimed
            package = prepare_segment_run_package(
                run_setup,
                participant,
                session_root=output_root,
                progress_callback=progress_callback,
            )
            record_experiment_activity(
                "session_prepared",
                run_setup_manifest_path=str(run_setup),
                session_manifest_path=str(package.manifest_path),
                session_dir=str(package.session_dir),
                participant_id=participant,
            )
            update_profile_runner_settings(
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                output_folder=output_root,
                participant_id=participant,
                run_setup_manifest_path=run_setup,
                session_manifest_path=package.manifest_path,
            )
            return package.manifest_path
    return prepare_latest_focus_session(
        participant_id or str(pointer.get("participant_id") or ""),
        session_root=output_root,
        progress_callback=progress_callback,
    )


def _focus_dashboard_controller() -> Any:
    from . import dashboard_app

    output_root = active_output_folder(state_root=DEFAULT_DASHBOARD_STATE_ROOT, fallback=DEFAULT_SESSION_ROOT)
    return dashboard_app.DashboardController(
        design_path=DEFAULT_FOCUS_PROFILE_DESIGN_PATH,
        render_dir=DEFAULT_RENDER_DIR,
        session_root=output_root,
        import_dir=dashboard_app.DEFAULT_IMPORT_DIR,
        preview_dir=dashboard_app.DEFAULT_PREVIEW_DIR,
        project_registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
    )


def finished_profile_options() -> list[tuple[str, str]]:
    """Return Segment 6-launchable bundled and local profiles for the launcher."""
    catalog = build_profile_catalog(
        registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        session_root=active_output_folder(state_root=DEFAULT_DASHBOARD_STATE_ROOT, fallback=DEFAULT_SESSION_ROOT),
        inventory=load_preload_inventory(repo_root()),
        include_unlaunchable_bundled=False,
    )
    options: list[tuple[str, str]] = []
    for profile in catalog.get("entries", []):
        if not bool(profile.get("segment_6_ready")):
            continue
        profile_id = str(profile.get("profile_id") or "").strip()
        if not profile_id:
            continue
        label = str(profile.get("display_name") or profile_id).strip()
        kind_label = "local" if profile.get("kind") == "custom" else "bundled"
        options.append((profile_id, f"{label} ({kind_label})"))
    options.sort(key=lambda item: (0 if item[0] == STUDY5_PROFILE_ID else 1, item[1].lower()))
    return options


def _environment_bridge_manifest(output_root: Path | None = None) -> dict[str, Any]:
    root = Path(output_root) if output_root is not None else active_output_folder(
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        fallback=DEFAULT_SESSION_ROOT,
    )
    path = existing_bridge_manifest_path(root) or bridge_manifest_path(root)
    return _read_json_dict(path)


def _bridge_matches_profile(bridge: dict[str, Any], profile_id: str) -> bool:
    profile = str(profile_id or "").strip()
    bridge_profile = str(bridge.get("profile_id") or "").strip()
    return bool(bridge and (not profile or not bridge_profile or bridge_profile == profile))


def _environment_run_setup_manifest_path(profile_id: str, output_root: Path | None = None) -> Path:
    bridge = _environment_bridge_manifest(output_root)
    if not _bridge_matches_profile(bridge, profile_id):
        return Path()
    path = Path(str(bridge.get("run_setup_manifest_path") or ""))
    return path if path.is_file() else Path()


def _environment_participant_ids(profile_id: str, output_root: Path | None = None) -> list[str]:
    bridge = _environment_bridge_manifest(output_root)
    if not _bridge_matches_profile(bridge, profile_id):
        return []
    participants = [str(item or "").strip() for item in bridge.get("participant_ids", []) if str(item or "").strip()]
    if participants:
        return participants
    count = int(bridge.get("participant_count") or 0)
    return [f"P{index:03d}" for index in range(1, count + 1)] if count > 0 else []


def _environment_design_and_run_setup(profile_id: str, output_root: Path | None = None) -> tuple[Any, Path] | None:
    root = Path(output_root) if output_root is not None else active_output_folder(
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        fallback=DEFAULT_SESSION_ROOT,
    )
    run_setup = _environment_run_setup_manifest_path(profile_id, root)
    if not run_setup.is_file():
        return None
    bridge = _environment_bridge_manifest(root)
    snapshot_dir = Path(str(bridge.get("acquisition_profile_snapshot_dir") or ""))
    design_path = snapshot_dir / "0_profile" / "active_design.json"
    if not design_path.is_file():
        return None
    from . import dashboard_app

    design = dashboard_app._normalize_dashboard_design(dashboard_app.load_design(design_path))
    return design, run_setup


def profile_participant_ids(profile_id: str) -> list[str]:
    """Return participant IDs declared by a bundled or custom profile."""
    profile = str(profile_id or "").strip()
    if not profile:
        return ["P001"]
    bridged = _environment_participant_ids(profile)
    if bridged:
        return bridged
    try:
        entry = resolve_profile_entry(
            profile,
            registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            session_root=active_output_folder(state_root=DEFAULT_DASHBOARD_STATE_ROOT, fallback=DEFAULT_SESSION_ROOT),
            inventory=load_preload_inventory(repo_root()),
        )
        return profile_participant_ids_from_entry(entry)
    except Exception:
        count = 1
        defaults_path = repo_root() / "assets" / "preloads" / profile / "05_run_setup" / "run_defaults.json"
        try:
            data = json.loads(defaults_path.read_text(encoding="utf-8"))
            count = max(1, int(data.get("participants") or data.get("participant_count") or 1))
        except Exception:
            count = 1
        return [f"P{index:03d}" for index in range(1, count + 1)]


def parse_participant_range(text: str, *, max_participant: int | None = None) -> list[str]:
    """Parse explicit participant ranges such as 1-10, P001-P010, or 1,3-5."""
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Enter a participant number or range first.")
    normalized = raw.replace(";", ",")
    participant_numbers: list[int] = []
    seen: set[int] = set()
    for part in [item.strip() for item in normalized.split(",") if item.strip()]:
        if "-" in part:
            start_text, end_text = [item.strip() for item in part.split("-", 1)]
            start = _parse_participant_number(start_text)
            end = _parse_participant_number(end_text)
            if start <= 0 or end <= 0:
                raise ValueError("Participant numbers must be positive.")
            if end < start:
                raise ValueError("Participant ranges must run from low to high.")
            numbers = range(start, end + 1)
        else:
            number = _parse_participant_number(part)
            if number <= 0:
                raise ValueError("Participant numbers must be positive.")
            numbers = range(number, number + 1)
        for number in numbers:
            if max_participant is not None and number > max_participant:
                raise ValueError(f"Participant P{number:03d} is outside the configured 1-{max_participant} range.")
            if number not in seen:
                participant_numbers.append(number)
                seen.add(number)
    if not participant_numbers:
        raise ValueError("Enter at least one participant number.")
    return [f"P{number:03d}" for number in participant_numbers]


def profile_run_setup_manifest_path(profile_id: str) -> Path:
    profile = str(profile_id or "").strip()
    if not profile:
        return Path()
    bridged = _environment_run_setup_manifest_path(profile)
    if bridged.is_file():
        return bridged
    try:
        entry = resolve_profile_entry(
            profile,
            registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            session_root=active_output_folder(state_root=DEFAULT_DASHBOARD_STATE_ROOT, fallback=DEFAULT_SESSION_ROOT),
            inventory=load_preload_inventory(repo_root()),
        )
        run_setup = str(entry.get("run_setup_manifest_path") or "").strip()
        if run_setup:
            return Path(run_setup)
    except Exception:
        pass
    return (
        DEFAULT_PROJECT_REGISTRY_ROOT
        / f"profile_{profile}"
        / "6_experiment_run_setup"
        / "experiment_run_setup_manifest.json"
    )


def profile_participant_asset_statuses(profile_id: str, *, session_root: Path | None = None) -> dict[str, dict[str, Any]]:
    output_root = Path(session_root) if session_root is not None else current_runner_session_root()
    participants = _environment_participant_ids(profile_id, output_root) or profile_participant_ids(profile_id)
    run_setup = _environment_run_setup_manifest_path(profile_id, output_root)
    if not run_setup.is_file():
        run_setup = profile_run_setup_manifest_path(profile_id)
    if not run_setup.is_file():
        return {
            participant: {
                "participant_id": participant,
                "generated": False,
                "status": "not_generated",
                "session_manifest_path": "",
                "message": "Run setup has not been materialized yet.",
                "source": "",
                "data_collected": False,
                "data_collection_status": "not_collected",
                "data_session_manifest_path": "",
                "data_session_dir": "",
                "data_collection_message": "No completed participant data found.",
            }
            for participant in participants
        }
    return prepared_session_asset_statuses(
        run_setup,
        participants,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        session_root=output_root,
    )


def profile_participant_dropdown_label(participant: str, status: dict[str, Any]) -> str:
    state = str(status.get("status") or "not_generated")
    if state == "ready":
        asset_suffix = "generated, ready"
    elif bool(status.get("generated")):
        asset_suffix = "generated"
    elif state == "preparing":
        asset_suffix = "generating"
    elif state == "failed":
        asset_suffix = "failed"
    else:
        asset_suffix = "not generated"
    inventory = str(status.get("part_inventory") or "").strip()
    if inventory:
        data_suffix = inventory
    else:
        data_suffix = f"{DATA_COLLECTED_MARK} data collected" if status.get("data_collected") else "data not collected"
    return f"{participant} - {asset_suffix} - {data_suffix}"


def default_profile_participant(
    participants: list[str],
    statuses: dict[str, dict[str, Any]],
    *,
    preferred: str = "",
) -> str:
    available = [str(participant or "").strip() for participant in participants if str(participant or "").strip()]
    if not available:
        return ""
    preferred = str(preferred or "").strip()
    if preferred in available and _status_is_generated_without_data(statuses.get(preferred, {})):
        return preferred
    for participant in available:
        if _status_is_generated_without_data(statuses.get(participant, {})):
            return participant
    return preferred if preferred in available else available[0]


def _status_is_generated_without_data(status: dict[str, Any]) -> bool:
    return bool(status.get("generated")) and not bool(status.get("data_collected"))


def _package_participant_ids(package: Any) -> list[str]:
    participants: list[str] = []
    run_setup = getattr(package, "source_run_setup_manifest_path", None)
    if run_setup:
        try:
            participants = segment_run_setup_participants(Path(run_setup))
        except Exception:
            participants = []
    current = str(getattr(package, "participant_id", "") or "").strip()
    if current and current not in participants:
        participants.insert(0, current)
    return [participant for participant in participants if str(participant or "").strip()]


def _package_is_split_part(package: Any) -> bool:
    return bool(str(getattr(package, "part_split_schema", "") or "").strip()) and bool(
        str(getattr(package, "session_group_id", "") or "").strip()
    )


def _package_output_root(package: Any) -> Path:
    try:
        session_dir = Path(getattr(package, "session_dir")).resolve()
    except Exception:
        return current_runner_session_root()
    if _package_is_split_part(package):
        return session_dir.parent.parent
    return session_dir.parent


def _package_experiment_context(package: Any) -> dict[str, str]:
    design_data = _read_json_dict(getattr(package, "design_path", None))
    run_setup_data = _read_json_dict(getattr(package, "source_run_setup_manifest_path", None))
    experiment_name = (
        str(run_setup_data.get("experiment_name") or "").strip()
        or str(design_data.get("study_profile_title") or "").strip()
        or str(design_data.get("name") or "").strip()
        or str(design_data.get("study_profile_id") or "").strip()
        or "PPS experiment"
    )
    return {
        "experiment_name": experiment_name,
        "profile_id": str(design_data.get("study_profile_id") or "").strip(),
    }


def _focus_filesystem_path(path: Any) -> str:
    resolved = Path(path).expanduser().resolve()
    text = str(resolved)
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _focus_path_is_file(path: Any) -> bool:
    try:
        return os.path.isfile(_focus_filesystem_path(path))
    except Exception:
        return False


def _read_json_dict(path: Any) -> dict[str, Any]:
    if path in (None, ""):
        return {}
    try:
        with open(_focus_filesystem_path(path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def participant_ledger_path(output_root: Path | str) -> Path:
    return output_project_state_dir(output_root) / PARTICIPANT_LEDGER_FILENAME


def load_participant_ledger(output_root: Path | str) -> dict[str, Any]:
    path = participant_ledger_path(output_root)
    try:
        with open(_output_filesystem_path(path), "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"schema": PARTICIPANT_LEDGER_SCHEMA, "participants": {}}
    if not isinstance(data, dict):
        return {"schema": PARTICIPANT_LEDGER_SCHEMA, "participants": {}}
    participants = data.get("participants")
    if not isinstance(participants, dict):
        participants = {}
    return {
        **data,
        "schema": PARTICIPANT_LEDGER_SCHEMA,
        "participants": participants,
    }


def save_participant_ledger(output_root: Path | str, ledger: dict[str, Any]) -> Path:
    path = participant_ledger_path(output_root)
    data = dict(ledger or {})
    participants = data.get("participants")
    if not isinstance(participants, dict):
        participants = {}
    data["schema"] = PARTICIPANT_LEDGER_SCHEMA
    data["participants"] = participants
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    os.makedirs(_output_filesystem_path(path.parent), exist_ok=True)
    with open(_output_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    return path


def participant_ledger_entry(output_root: Path | str, participant_id: str) -> dict[str, Any]:
    participant = str(participant_id or "").strip()
    if not participant:
        return {}
    entry = load_participant_ledger(output_root).get("participants", {}).get(participant)
    return dict(entry) if isinstance(entry, dict) else {}


def _read_latest_output_diary_context(path: Any) -> dict[str, Any]:
    if path in (None, ""):
        return {}
    diary_path = Path(path)
    if not _focus_path_is_file(diary_path):
        return {}
    try:
        with open(_focus_filesystem_path(diary_path), "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except Exception:
        return {}
    context: dict[str, Any] = {}
    for line in lines:
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if not isinstance(entry, dict):
            continue
        for key in (
            "profile_id",
            "profile_kind",
            "dashboard_project_id",
            "participant_id",
            "bridge_manifest_path",
            "acquisition_profile_snapshot_dir",
            "active_output_folder",
            "output_folder",
            "session_name",
            "experiment_name",
            "display_name",
        ):
            value = entry.get(key)
            if value not in (None, "", {}):
                context[key] = value
    return context


def _classify_launcher_output_folder(
    folder: Path,
    *,
    fallback_profile_id: str = "",
    fallback_session_name: str = "",
    fallback_participant_id: str = "",
) -> dict[str, Any]:
    root = Path(folder).expanduser()
    try:
        resolved_root = root.resolve()
    except Exception:
        resolved_root = root
    runner_diary_path = find_output_diary(resolved_root) if resolved_root.is_dir() else None
    existing_output_diary = existing_output_diary_path(resolved_root) if resolved_root.is_dir() else None
    output_diary_file = existing_output_diary or output_diary_path(resolved_root)
    existing_bridge = existing_bridge_manifest_path(resolved_root) if resolved_root.is_dir() else None
    bridge_path = existing_bridge or bridge_manifest_path(resolved_root)
    output_diary_context = _read_latest_output_diary_context(existing_output_diary)
    bridge_exists = existing_bridge is not None or _focus_path_is_file(bridge_path)
    if not bridge_exists:
        bridged_text = str(output_diary_context.get("bridge_manifest_path") or "").strip()
        bridged_path = Path(bridged_text).expanduser() if bridged_text else None
        if bridged_path is not None and _focus_path_is_file(bridged_path):
            bridge_path = bridged_path
            bridge_exists = True
    bridge = _read_json_dict(bridge_path)
    diary_context = latest_diary_context(runner_diary_path) if runner_diary_path is not None else {}
    has_environment_marker = bool(
        runner_diary_path is not None
        or existing_output_diary is not None
        or bridge_exists
    )
    if not has_environment_marker:
        return {
            "kind": "new_parent",
            "root": resolved_root,
            "profile_id": "",
            "session_name": "",
            "participant_id": fallback_participant_id or "P001",
            "runner_diary_path": None,
            "output_diary_path": output_diary_file if _focus_path_is_file(output_diary_file) else None,
            "bridge_manifest_path": None,
            "bridge": {},
            "markers": [],
        }
    profile_id = str(
        bridge.get("profile_id")
        or diary_context.get("profile_id")
        or output_diary_context.get("profile_id")
        or fallback_profile_id
        or ""
    ).strip()
    session_name = str(
        bridge.get("display_name")
        or diary_context.get("experiment_name")
        or output_diary_context.get("session_name")
        or output_diary_context.get("experiment_name")
        or output_diary_context.get("display_name")
        or fallback_session_name
        or resolved_root.name
    ).strip()
    participant = str(
        bridge.get("participant_id")
        or diary_context.get("participant_id")
        or output_diary_context.get("participant_id")
        or fallback_participant_id
        or "P001"
    ).strip()
    markers: list[str] = []
    if runner_diary_path is not None:
        markers.append("runner diary")
    if existing_output_diary is not None:
        markers.append("output diary")
    if bridge_exists:
        markers.append("dashboard bridge")
    return {
        "kind": "existing_environment",
        "root": resolved_root,
        "profile_id": profile_id,
        "session_name": session_name,
        "participant_id": participant or "P001",
        "runner_diary_path": runner_diary_path,
        "output_diary_path": existing_output_diary,
        "bridge_manifest_path": bridge_path if bridge_exists else None,
        "bridge": bridge,
        "markers": markers,
    }


def _refresh_qt_dynamic_property(widget: Any, name: str, value: Any) -> None:
    if widget is None:
        return
    try:
        if widget.property(name) == value:
            return
        widget.setProperty(name, value)
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)
        widget.update()
    except Exception:
        return


def _append_output_diary_event(
    event_type: str,
    *,
    package: Any | None = None,
    session_root: Path | None = None,
    experiment_name: str = "",
    profile_id: str = "",
    participant_id: str = "",
    capture_options: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    create: bool = False,
) -> Path | None:
    root = _package_output_root(package) if package is not None else Path(session_root or current_runner_session_root()).expanduser().resolve()
    context = _package_experiment_context(package) if package is not None else {}
    experiment = experiment_name or context.get("experiment_name", "") or profile_id or "PPS experiment"
    profile = profile_id or context.get("profile_id", "")
    participant = participant_id or str(getattr(package, "participant_id", "") or "").strip()
    diary = ensure_output_diary(root, experiment) if create else find_output_diary(root)
    if diary is None:
        return None
    path = append_diary_entry(
        diary,
        event_type,
        session_id=str(getattr(package, "session_id", "") or ""),
        participant_id=participant,
        experiment_name=experiment,
        profile_id=profile,
        run_setup_manifest_path=str(getattr(package, "source_run_setup_manifest_path", "") or ""),
        session_manifest_path=str(getattr(package, "manifest_path", "") or ""),
        capture_options=capture_options,
        payload=payload,
    )
    remember_runner_context(
        session_root=root,
        diary_path=path,
        experiment_name=experiment,
        profile_id=profile,
        participant_id=participant,
        capture_options=capture_options,
    )
    return path


def _package_participant_statuses(package: Any, participants: list[str]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    run_setup = getattr(package, "source_run_setup_manifest_path", None)
    output_root = _package_output_root(package)
    if run_setup and participants:
        run_setup_path = Path(run_setup)
        if run_setup_path.is_file():
            try:
                statuses = prepared_session_asset_statuses(
                    run_setup_path,
                    participants,
                    state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                    session_root=output_root,
                )
            except Exception:
                statuses = {}
    current = str(getattr(package, "participant_id", "") or "").strip()
    if current:
        current_status = statuses.get(current, {})
        statuses[current] = {
            **current_status,
            "participant_id": current,
            "generated": True,
            "status": "ready",
            "session_manifest_path": str(getattr(package, "manifest_path", "") or ""),
            "message": "Current runner participant package is loaded.",
            "data_collected": bool(current_status.get("data_collected")),
            "data_collection_status": current_status.get("data_collection_status", "not_collected"),
            "data_session_manifest_path": current_status.get("data_session_manifest_path", ""),
            "data_session_dir": current_status.get("data_session_dir", ""),
            "data_collection_message": current_status.get("data_collection_message", ""),
        }
    return statuses


def prepare_profile_audio_assets(
    profile_id: str,
    participant_ids: list[str],
    *,
    session_root: Path | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Explicitly prepare local audio/session packages without opening Focus Mode."""
    profile = str(profile_id or "").strip()
    if not profile:
        raise ValueError("Choose a study/profile preset before generating assets.")
    participants = [participant for participant in participant_ids if participant]
    if not participants:
        raise ValueError("Choose at least one participant before generating assets.")

    _emit_launcher_progress(
        progress_callback,
        "Loading profile inventory",
        phase="profile_inventory",
        detail=profile,
        current=0,
        total=len(participants),
    )
    output_root = Path(session_root) if session_root is not None else active_output_folder(
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        fallback=DEFAULT_SESSION_ROOT,
    )
    environment = _environment_design_and_run_setup(profile, output_root)
    if environment is not None:
        design, run_setup_manifest_path = environment
        controller = SimpleNamespace(design_path=Path(run_setup_manifest_path).resolve().parents[1] / "0_profile" / "active_design.json")
    else:
        controller, design, run_setup_manifest_path = _materialize_profile_run_setup(
            profile,
            progress_callback=progress_callback,
        )
    results: list[dict[str, Any]] = []
    prepared_count = 0
    reused_count = 0
    for index, participant in enumerate(participants, start=1):
        status = prepared_session_asset_status(
            run_setup_manifest_path,
            participant,
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            session_root=output_root,
        )
        if status.get("status") == "preparing":
            reused_count += 1
            results.append({**status, "participant_id": participant, "status": "already_preparing"})
            _emit_launcher_progress(
                progress_callback,
                f"{participant}: generation already running",
                phase="asset_preparing",
                detail=str(status.get("message") or ""),
                current=index,
                total=len(participants),
            )
            continue
        existing_session_manifest = str(status.get("session_manifest_path") or "").strip()
        if status.get("generated") and existing_session_manifest:
            record_prepared_session_queue(
                participant_id=participant,
                run_setup_manifest_path=run_setup_manifest_path,
                session_manifest_path=Path(existing_session_manifest),
                status="ready",
                message="Prepared package reused by Experiment Runner launcher.",
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            )
            reused_count += 1
            results.append({**status, "participant_id": participant, "status": "already_ready"})
            _emit_launcher_progress(
                progress_callback,
                f"{participant}: assets already generated",
                phase="asset_ready",
                detail=str(status.get("session_manifest_path") or ""),
                current=index,
                total=len(participants),
            )
            continue

        record_prepared_session_queue(
            participant_id=participant,
            run_setup_manifest_path=run_setup_manifest_path,
            status="preparing",
            message="Preparing from Experiment Runner launcher.",
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        )

        def _participant_progress(payload: dict[str, Any], *, participant_id: str = participant, participant_index: int = index) -> None:
            _emit_launcher_progress(
                progress_callback,
                str(payload.get("message") or f"Generating {participant_id}"),
                phase=str(payload.get("phase") or "generating_assets"),
                detail=f"{participant_id}: {payload.get('detail') or ''}".strip(),
                current=participant_index - 1,
                total=len(participants),
            )

        try:
            package = prepare_segment_run_package(
                run_setup_manifest_path,
                participant,
                design=design,
                session_root=output_root,
                progress_callback=_participant_progress,
            )
        except Exception as exc:
            record_prepared_session_queue(
                participant_id=participant,
                run_setup_manifest_path=run_setup_manifest_path,
                status="failed",
                message=str(exc),
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            )
            raise

        record_prepared_session_queue(
            participant_id=participant,
            run_setup_manifest_path=run_setup_manifest_path,
            session_manifest_path=package.manifest_path,
            status="ready",
            message="Prepared by Experiment Runner launcher.",
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        )
        record_experiment_activity(
            "session_prepared",
            template_id=profile,
            run_setup_manifest_path=str(run_setup_manifest_path),
            session_manifest_path=str(package.manifest_path),
            session_dir=str(package.session_dir),
            participant_id=participant,
        )
        update_profile_runner_settings(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            output_folder=output_root,
            profile_id=profile,
            participant_id=participant,
            run_setup_manifest_path=run_setup_manifest_path,
            session_manifest_path=package.manifest_path,
        )
        prepared_count += 1
        results.append(
            {
                "participant_id": participant,
                "status": "generated",
                "session_manifest_path": str(package.manifest_path),
                "session_dir": str(package.session_dir),
                "block_count": len(package.blocks),
            }
        )
        _emit_launcher_progress(
            progress_callback,
            f"{participant}: assets generated",
            phase="asset_generated",
            detail=str(package.manifest_path),
            current=index,
            total=len(participants),
        )

    _emit_launcher_progress(
        progress_callback,
        "Audio assets ready",
        phase="assets_ready",
        detail=f"{prepared_count} generated, {reused_count} already available",
        current=len(participants),
        total=len(participants),
    )
    return {
        "profile_id": profile,
        "participant_count": len(participants),
        "prepared_count": prepared_count,
        "reused_count": reused_count,
        "run_setup_manifest_path": str(run_setup_manifest_path),
        "results": results,
        "design_path": str(controller.design_path),
    }


def _materialize_profile_run_setup(
    profile_id: str,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[Any, Any, Path]:
    from . import dashboard_app

    entry = resolve_profile_entry(
        profile_id,
        registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        session_root=active_output_folder(state_root=DEFAULT_DASHBOARD_STATE_ROOT, fallback=DEFAULT_SESSION_ROOT),
        inventory=load_preload_inventory(repo_root()),
    )
    if entry.get("kind") == "custom":
        run_setup_manifest_path = Path(str(entry.get("run_setup_manifest_path") or ""))
        if not run_setup_manifest_path.is_file() or not bool(entry.get("segment_6_ready")):
            reasons = entry.get("missing_or_stale_asset_reasons") or ["Segment 6 is not ready."]
            raise ValueError(f"Local study profile '{profile_id}' cannot be launched: {str(reasons[0])}")
        design_path = Path(str(entry.get("project_dir") or "")) / "0_profile" / "active_design.json"
        if not design_path.is_file():
            raise FileNotFoundError(f"Stored profile design is missing: {design_path}")
        design = dashboard_app._normalize_dashboard_design(dashboard_app.load_design(design_path))
        return SimpleNamespace(design_path=design_path), design, run_setup_manifest_path

    controller = _focus_dashboard_controller()
    inventory_profiles = controller.preload_inventory_payload().get("profiles", [])
    status = next((item for item in inventory_profiles if item.get("template_id") == profile_id), None)
    if status is None:
        raise ValueError(f"Unknown study/profile preset: {profile_id}")
    if not (status.get("finished_profile") and status.get("segment_6_launchable")):
        reason = str(status.get("profile_completion_status") or status.get("runner_readiness") or "unfinished_preload")
        raise ValueError(
            f"Study/profile preset '{profile_id}' is not a finished Segment 6 launchable profile yet ({reason})."
        )

    controller.load_template(profile_id, snapshot=False)
    with controller._lock:
        project = controller._ensure_project_context(controller.design, clear_stale_profile_outputs=True)
        design = dashboard_app._copy_design(controller.design)
    controller._ensure_profile_run_artifacts(project, design, progress_callback=progress_callback)
    with controller._lock:
        project = controller._ensure_project_context(controller.design)
        design = dashboard_app._copy_design(controller.design)
    run_setup_manifest_path = dashboard_app._run_setup_manifest_path(project.project_dir)
    if not run_setup_manifest_path.is_file():
        raise RuntimeError(f"Study/profile preset '{profile_id}' did not produce a Segment 6 run setup.")
    return controller, design, run_setup_manifest_path


def _parse_participant_number(value: str) -> int:
    text = str(value or "").strip()
    if text.upper().startswith("P"):
        text = text[1:]
    if not text.isdigit():
        raise ValueError(f"Invalid participant number: {value!r}")
    return int(text)


def _emit_launcher_progress(
    progress_callback: Callable[[dict[str, Any]], None] | None,
    message: str,
    *,
    phase: str,
    detail: str = "",
    current: int = 0,
    total: int = 0,
) -> None:
    if progress_callback is None:
        return
    progress_callback(
        {
            "phase": phase,
            "message": message,
            "detail": detail,
            "current": int(current or 0),
            "total": int(total or 0),
            "timestamp_unix": time.time(),
        }
    )


def prepare_profile_focus_session(
    profile_id: str,
    participant_id: str | None = None,
    *,
    session_root: Path | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    """Materialize a participant session directly from a bundled or custom profile."""
    profile = str(profile_id or "").strip()
    if not profile:
        raise ValueError("Choose a study/profile preset before opening Focus Mode.")
    participant = str(participant_id or "").strip() or "P001"
    if progress_callback is not None:
        progress_callback(
            {
                "phase": "profile_inventory",
                "message": "Loading profile inventory",
                "detail": profile,
                "current": 0,
                "total": 0,
                "timestamp_unix": time.time(),
            }
        )
    validation_output_root = os.environ.get("PPS_FOCUS_VALIDATION_OUTPUT_ROOT", "").strip()
    if session_root is not None:
        output_root = Path(session_root)
    elif validation_output_root:
        output_root = Path(validation_output_root).expanduser()
    else:
        output_root = active_output_folder(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            fallback=DEFAULT_SESSION_ROOT,
        )
    environment = _environment_design_and_run_setup(profile, output_root)
    if environment is not None:
        design, run_setup_manifest_path = environment
    else:
        _controller, design, run_setup_manifest_path = _materialize_profile_run_setup(
            profile,
            progress_callback=progress_callback,
        )
    claimed = claim_prepared_session(
        run_setup_manifest_path,
        participant,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        session_root=output_root,
    )
    if claimed is not None:
        package = load_run_package(claimed)
    else:
        status = prepared_session_asset_status(
            run_setup_manifest_path,
            participant,
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            session_root=output_root,
        )
        existing_manifest = str(status.get("session_manifest_path") or "").strip()
        if bool(status.get("generated")) and existing_manifest:
            package = load_run_package(Path(existing_manifest))
        else:
            package = prepare_segment_run_package(
                run_setup_manifest_path,
                participant,
                design=design,
                session_root=output_root,
                progress_callback=progress_callback,
            )
            record_prepared_session_queue(
                participant_id=participant,
                run_setup_manifest_path=run_setup_manifest_path,
                session_manifest_path=package.manifest_path,
                status="ready",
                message="Prepared by Experiment Runner launcher.",
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            )
    record_experiment_activity(
        "session_prepared",
        template_id=profile,
        run_setup_manifest_path=str(run_setup_manifest_path),
        session_manifest_path=str(package.manifest_path),
        session_dir=str(package.session_dir),
        participant_id=participant,
    )
    entry = resolve_profile_entry(
        profile,
        registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        session_root=output_root,
        inventory=load_preload_inventory(repo_root()),
    )
    update_profile_runner_settings(
        state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        output_folder=output_root,
        profile_id=profile,
        profile_kind=str(entry.get("kind") or ""),
        dashboard_project_id=str(entry.get("dashboard_project_id") or ""),
        participant_id=participant,
        run_setup_manifest_path=run_setup_manifest_path,
        session_manifest_path=package.manifest_path,
    )
    return Path(package.manifest_path)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str) -> int | None:
    value = os.environ.get(name, "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _validation_no_mouse_mode() -> bool:
    return (
        _env_flag("PPS_FOCUS_VALIDATION_DISABLE_MOUSE_CAPTURE")
        or _env_flag("PPS_FOCUS_VALIDATION_DISABLE_CURSOR_RECENTER")
        or _env_flag("PPS_FOCUS_VALIDATION_NO_MOUSE")
    )


def _validation_window_rect_from_env() -> tuple[int, int, int, int] | None:
    value = os.environ.get("PPS_FOCUS_VALIDATION_WINDOW_RECT", "").strip()
    if not value:
        return None
    parts = [part.strip() for part in value.replace(";", ",").split(",")]
    if len(parts) != 4:
        return None
    try:
        x, y, width, height = (int(float(part)) for part in parts)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return x, y, width, height


def _validation_window_rect_for_display(q: dict[str, Any]) -> tuple[int, int, int, int] | None:
    explicit = _validation_window_rect_from_env()
    if explicit is not None:
        return explicit
    display = os.environ.get("PPS_FOCUS_VALIDATION_DISPLAY", "").strip().lower()
    if not display:
        return None
    app = q["QApplication"].instance()
    if app is None or not hasattr(app, "screens"):
        return None
    try:
        screens = list(app.screens())
    except Exception:
        screens = []
    if not screens:
        return None

    def _screen_area(screen: Any) -> Any:
        try:
            return screen.availableGeometry()
        except Exception:
            return screen.geometry()

    def _screen_name(screen: Any) -> str:
        try:
            return str(screen.name()).strip().lower()
        except Exception:
            return ""

    selected = None
    if display == "primary":
        try:
            selected = app.primaryScreen()
        except Exception:
            selected = None
    elif display in {"left", "display2", "2"}:
        if display in {"display2", "2"}:
            selected = next(
                (screen for screen in screens if _screen_name(screen).endswith("display2")),
                None,
            )
        if selected is None:
            selected = min(screens, key=lambda screen: int(_screen_area(screen).x()))
    elif display == "right":
        selected = max(screens, key=lambda screen: int(_screen_area(screen).x()))
    else:
        selected = next((screen for screen in screens if _screen_name(screen) == display), None)
    if selected is None:
        return None

    area = _screen_area(selected)
    x = int(area.x())
    y = int(area.y())
    area_width = max(1, int(area.width()))
    area_height = max(1, int(area.height()))
    requested_width = _env_int("PPS_FOCUS_VALIDATION_RUNNER_WIDTH") or 820
    width = max(560, min(int(requested_width), int(area_width * 0.48), area_width))
    height = area_height
    return x, y, width, height


def _apply_window_rect(dialog: Any, rect: tuple[int, int, int, int] | None) -> None:
    if rect is None:
        return
    x, y, width, height = rect
    try:
        dialog.setGeometry(int(x), int(y), int(width), int(height))
    except Exception:
        pass
    try:
        dialog.move(int(x), int(y))
        dialog.resize(int(width), int(height))
    except Exception:
        pass


def _prepare_validation_window_placement(
    q: dict[str, Any],
    dialog: Any,
    rect: tuple[int, int, int, int] | None = None,
) -> tuple[int, int, int, int] | None:
    resolved = rect if rect is not None else _validation_window_rect_for_display(q)
    if resolved is None:
        return None
    _apply_window_rect(dialog, resolved)
    try:
        for delay_ms in (0, 200, 500, 1000, 2000):
            q["QTimer"].singleShot(
                delay_ms,
                lambda resolved=resolved: _apply_window_rect(dialog, resolved),
            )
    except Exception:
        pass
    return resolved


def _path_is_within(path: str | Path, root: str | Path) -> bool:
    try:
        target = Path(path).resolve()
        base = Path(root).resolve()
    except Exception:
        return False
    return target == base or base in target.parents


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) else default


def _validation_start_gate_ready(records: list[dict[str, Any]], state: dict[str, Any], *, source: str) -> bool:
    ready_file = os.environ.get("PPS_FOCUS_VALIDATION_START_READY_FILE", "").strip()
    if not ready_file or bool(state.get("released")):
        return True
    now = time.perf_counter()
    if not state.get("started_monotonic"):
        state["started_monotonic"] = now
        records.append(
            {
                "label": "start_gate_waiting",
                "source": source,
                "ready_file": ready_file,
                "timestamp_unix": time.time(),
            }
        )
    if Path(ready_file).expanduser().is_file():
        state["released"] = True
        records.append(
            {
                "label": "start_gate_released",
                "source": source,
                "ready_file": ready_file,
                "wait_s": max(0.0, now - float(state.get("started_monotonic") or now)),
                "timestamp_unix": time.time(),
            }
        )
        return True
    timeout_s = max(0.0, _env_float("PPS_FOCUS_VALIDATION_START_READY_TIMEOUT_S", 60.0))
    elapsed_s = now - float(state.get("started_monotonic") or now)
    if elapsed_s >= timeout_s:
        state["released"] = True
        records.append(
            {
                "label": "start_gate_timeout_released",
                "source": source,
                "ready_file": ready_file,
                "wait_s": elapsed_s,
                "timeout_s": timeout_s,
                "timestamp_unix": time.time(),
            }
        )
        return True
    return False


class _ValidationFastAudioEngine:
    """Validation-only fake engine that emits normal scheduled audio callbacks."""

    def __init__(self, *, chunk_frames: int = 441_000, realtime: bool = False) -> None:
        self.chunk_frames = int(chunk_frames)
        self.realtime = bool(realtime)
        self.played_blocks: list[str] = []
        self.played_block_durations_s: list[float] = []
        self.played_instructions: list[str] = []
        self.played_instruction_durations_s: list[float] = []
        self._stop_requested = threading.Event()
        self._audio_event_callback: Callable[[dict[str, Any]], None] | None = None
        self._play_start_perf = 0.0
        self.sample_rate = 44_100

    def play_instruction(self, path: str, done: Callable[[bool], None] | None = None) -> bool:
        import soundfile as sf

        self.played_instructions.append(path)
        duration_s = 0.0
        try:
            info = sf.info(str(path))
            duration_s = float(info.frames) / float(info.samplerate) if int(info.samplerate) > 0 else 0.0
        except Exception:
            duration_s = 0.0
        self.played_instruction_durations_s.append(duration_s)
        if self.realtime and duration_s > 0:
            deadline = time.perf_counter() + duration_s
            while not self._stop_requested.is_set():
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                time.sleep(min(remaining, 0.050))
        if done is not None:
            done(not self._stop_requested.is_set())
        return not self._stop_requested.is_set()

    def play_block(
        self,
        path: str,
        progress_callback: Callable[[float], None] | None = None,
        audio_event_callback: Callable[[dict[str, Any]], None] | None = None,
        block_event_schedule: Any = None,
    ) -> bool:
        import soundfile as sf

        self.played_blocks.append(path)
        info = sf.info(str(path))
        frames_total = int(info.frames)
        self.sample_rate = int(info.samplerate)
        duration_s = float(frames_total) / float(self.sample_rate) if self.sample_rate > 0 else 0.0
        self.played_block_durations_s.append(duration_s)
        self._audio_event_callback = audio_event_callback
        self._play_start_perf = time.perf_counter()
        if block_event_schedule is not None:
            block_event_schedule.reset()
            if progress_callback is not None and self.sample_rate > 0 and not self.realtime:
                lead_times = sorted(
                    {
                        max(0.0, (float(event.sample_index) / float(self.sample_rate)) - 0.5)
                        for event in getattr(block_event_schedule, "events", [])
                        if getattr(event, "event_type", "") == "tactile_onset"
                    }
                )
                for lead_time in lead_times:
                    progress_callback(lead_time)
                    # Let the Qt drain timer process each synthetic cue before the next block replaces the timeline.
                    time.sleep(0.005)
                time.sleep(0.150)
        cursor = 0
        while cursor < frames_total and not self._stop_requested.is_set():
            frames = min(self.chunk_frames, frames_total - cursor)
            now = time.perf_counter()
            buffer_dac_perf = self._play_start_perf + (cursor / self.sample_rate if self.sample_rate > 0 else 0.0)
            if audio_event_callback is not None and block_event_schedule is not None:
                event_frames = frames + 1 if cursor + frames >= frames_total else frames
                for event in block_event_schedule.consume_buffer(cursor, event_frames):
                    offset = int(event.sample_index) - cursor
                    payload = dict(event.payload)
                    payload.update(
                        {
                            "event_type": event.event_type,
                            "sample_index": event.sample_index,
                            "buffer_start_sample": cursor,
                            "sample_offset_in_buffer": offset,
                            "sample_rate": self.sample_rate,
                            "trigger_key": event.trigger_key,
                            "callback_perf_counter": now,
                            "stream_current_time": now,
                            "stream_output_buffer_dac_time": buffer_dac_perf,
                        }
                    )
                    audio_event_callback(payload)
            cursor += frames
            if progress_callback is not None:
                progress_callback(min(cursor, frames_total) / self.sample_rate)
            if self.realtime and self.sample_rate > 0:
                target = self._play_start_perf + (cursor / self.sample_rate)
                while not self._stop_requested.is_set():
                    sleep_s = target - time.perf_counter()
                    if sleep_s <= 0:
                        break
                    time.sleep(min(sleep_s, 0.025))
        return not self._stop_requested.is_set()

    def trigger_click(self, metadata: dict[str, Any] | None = None, marker_gain: float | None = None) -> None:
        now = time.perf_counter()
        elapsed_sample = max(0, int(round((now - self._play_start_perf) * self.sample_rate))) if self._play_start_perf else 0
        payload = {
            "event_type": "response_marker_start",
            "sample_index": elapsed_sample,
            "buffer_start_sample": elapsed_sample,
            "sample_offset_in_buffer": 0,
            "sample_rate": self.sample_rate,
            "callback_perf_counter": now,
            "stream_current_time": now,
            "stream_output_buffer_dac_time": now,
            "marker_channel": 2,
            "marker_gain": marker_gain,
            **dict(metadata or {}),
        }
        if self._audio_event_callback is not None:
            self._audio_event_callback(payload)

    def stop(self) -> None:
        self._stop_requested.set()

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def shutdown(self) -> None:
        self.stop()


def _validation_event_counts(events_csv: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not os.path.isfile(_output_filesystem_path(events_csv)):
        return counts
    with open(_output_filesystem_path(events_csv), newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            event_type = str(row.get("event_type") or "")
            if event_type:
                counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _validation_scoped_event_counts(events_csv: Path) -> dict[str, Any]:
    scopes: dict[str, Any] = {
        "standard": {},
        "topup": {},
        "standard_trial_families": {},
        "topup_trial_families": {},
    }
    if not os.path.isfile(_output_filesystem_path(events_csv)):
        return scopes
    with open(_output_filesystem_path(events_csv), newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            event_type = str(row.get("event_type") or "")
            if not event_type:
                continue
            try:
                payload = json.loads(str(row.get("payload_json") or "{}"))
            except Exception:
                payload = {}
            is_topup = _truthy(
                payload.get("is_topup")
                or payload.get("Is_Topup")
                or payload.get("block_is_topup_block")
                or payload.get("block_is_topup")
            )
            scope_key = "topup" if is_topup else "standard"
            scope_counts = scopes[scope_key]
            scope_counts[event_type] = int(scope_counts.get(event_type, 0)) + 1
            if event_type == "trial_start":
                family = str(payload.get("family") or payload.get("Family") or "").strip() or "unknown"
                family_key = "topup_trial_families" if is_topup else "standard_trial_families"
                family_counts = scopes[family_key]
                family_counts[family] = int(family_counts.get(family, 0)) + 1
    return scopes


def _validation_merge_event_counts(items: Iterable[dict[str, Any]]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for counts in items:
        if not isinstance(counts, dict):
            continue
        for key, value in counts.items():
            try:
                merged[str(key)] = merged.get(str(key), 0) + int(value)
            except (TypeError, ValueError):
                continue
    return merged


def _validation_merge_scoped_event_counts(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "standard": {},
        "topup": {},
        "standard_trial_families": {},
        "topup_trial_families": {},
    }
    for scopes in items:
        if not isinstance(scopes, dict):
            continue
        for scope_key, counts in scopes.items():
            if not isinstance(counts, dict):
                continue
            target = merged.setdefault(str(scope_key), {})
            for event_type, value in counts.items():
                try:
                    target[str(event_type)] = int(target.get(str(event_type), 0)) + int(value)
                except (TypeError, ValueError):
                    continue
    return merged


def _validation_resolve_path(value: Any, base: Path | None = None, fallback: Path | None = None) -> Path | None:
    text = str(value or "").strip()
    if text:
        path = Path(text)
        if not path.is_absolute() and base is not None:
            path = base / path
        return path
    return fallback


def _validation_context_leaf(manifest: dict[str, Any]) -> Path:
    session_group_id = str(manifest.get("session_group_id") or "").strip()
    part_folder_name = str(manifest.get("part_folder_name") or "").strip()
    if session_group_id and part_folder_name:
        return Path(session_group_id) / part_folder_name
    session_id = str(manifest.get("session_id") or manifest.get("part_session_id") or "").strip()
    return Path(session_id or "session")


def _validation_manifest_output_root(session_dir: Path, manifest: dict[str, Any]) -> Path:
    output_root = str(manifest.get("output_root") or "").strip()
    if output_root:
        return Path(output_root)
    if str(manifest.get("session_group_id") or "").strip():
        return session_dir.parent.parent
    return session_dir.parent


def _validation_part_status_path(
    manifest: dict[str, Any],
    outputs: dict[str, Any],
    manifest_base: Path,
    *,
    output_root: Path,
    context_leaf: Path,
    group_entry: dict[str, Any] | None = None,
) -> Path:
    fallback = output_runner_logs_dir(output_root) / context_leaf / "part_completion_status.json"
    value = (
        outputs.get("part_completion_status_json")
        or manifest.get("part_completion_status_path")
        or ((group_entry or {}).get("part_completion_status_path") if group_entry else "")
    )
    return _validation_resolve_path(value, manifest_base, fallback) or fallback


def _validation_topup_dir_from_outputs(outputs: dict[str, Any], fallback: Path) -> Path:
    for key, value in outputs.items():
        if not str(key).startswith("topup_") or not str(value or "").strip():
            continue
        candidate = Path(str(value))
        if candidate.suffix:
            return candidate.parent
        return candidate
    return fallback


def _validation_part_report(
    manifest_path: Path,
    *,
    group_entry: dict[str, Any] | None = None,
    fallback_package: Any | None = None,
    completed_override: bool | None = None,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest_base = manifest_path.parent
    manifest = _read_json_dict(manifest_path)
    outputs = dict(manifest.get("outputs") or {})
    if fallback_package is not None and not manifest:
        try:
            manifest = {
                "participant_id": getattr(fallback_package, "participant_id", ""),
                "session_id": getattr(fallback_package, "session_id", ""),
                "session_group_id": getattr(fallback_package, "session_group_id", ""),
                "part_session_id": getattr(fallback_package, "part_session_id", ""),
                "part_number": getattr(fallback_package, "part_number", ""),
                "part_folder_name": getattr(fallback_package, "part_folder_name", ""),
                "session_dir": str(getattr(fallback_package, "session_dir", "")),
            }
        except Exception:
            manifest = {}
    session_dir = _validation_resolve_path(
        manifest.get("session_dir") or ((group_entry or {}).get("session_dir") if group_entry else ""),
        manifest_base,
        Path(getattr(fallback_package, "session_dir", manifest_base)) if fallback_package is not None else manifest_base,
    ) or manifest_base
    output_root = _validation_manifest_output_root(session_dir, manifest)
    context_leaf = _validation_context_leaf(manifest)
    status_path = _validation_part_status_path(
        manifest,
        outputs,
        manifest_base,
        output_root=output_root,
        context_leaf=context_leaf,
        group_entry=group_entry,
    )
    status = _read_json_dict(status_path)
    status_outputs = dict(status.get("analysis_outputs") or {})
    merged_outputs = {**outputs, **status_outputs}
    events_csv = _validation_resolve_path(
        status.get("events_csv") or outputs.get("verbose_events_csv") or outputs.get("events_csv"),
        manifest_base,
        output_verbose_events_dir(output_root) / context_leaf / "events.csv",
    )
    analysis_dir = _validation_resolve_path(
        outputs.get("analysis_dir") or manifest.get("data_analytics_dir"),
        manifest_base,
        output_data_analytics_dir(output_root) / context_leaf,
    )
    topup_dir = _validation_topup_dir_from_outputs(merged_outputs, output_runner_logs_dir(output_root) / context_leaf / "topup")
    completed = bool(status.get("completed") or (group_entry or {}).get("completed"))
    if completed_override is not None:
        completed = bool(completed_override)
    block_count = len(manifest.get("blocks") or [])
    part_session_id = str(
        manifest.get("part_session_id")
        or status.get("part_session_id")
        or (group_entry or {}).get("part_session_id")
        or manifest.get("session_id")
        or ""
    )
    report = {
        "session_manifest": str(manifest_path),
        "session_dir": str(session_dir),
        "events_csv": str(events_csv or ""),
        "analysis_dir": str(analysis_dir or ""),
        "topup_dir": str(topup_dir),
        "part_completion_status": str(status_path),
        "completed": completed,
        "block_count": int(block_count),
        "participant_id": str(manifest.get("participant_id") or status.get("participant_id") or ""),
        "session_id": str(manifest.get("session_id") or status.get("session_id") or ""),
        "session_group_id": str(manifest.get("session_group_id") or status.get("session_group_id") or ""),
        "part_session_id": part_session_id,
        "part_number": manifest.get("part_number", status.get("part_number", (group_entry or {}).get("part_number") if group_entry else "")),
        "part_folder_name": str(
            manifest.get("part_folder_name")
            or status.get("part_folder_name")
            or ((group_entry or {}).get("part_folder_name") if group_entry else "")
            or ""
        ),
        "outputs": {str(key): str(value) for key, value in merged_outputs.items()},
    }
    if events_csv is not None:
        report["event_counts"] = _validation_event_counts(events_csv)
        report["scoped_event_counts"] = _validation_scoped_event_counts(events_csv)
    else:
        report["event_counts"] = {}
        report["scoped_event_counts"] = _validation_scoped_event_counts(Path(""))
    return report


def _validation_split_part_reports(
    session_manifest: Path,
    package: Any,
    *,
    completed_override: bool | None = None,
) -> tuple[list[dict[str, Any]], Path | None, dict[str, Any]]:
    active_manifest = Path(session_manifest)
    manifest_payload = _read_json_dict(active_manifest)
    outputs = dict(manifest_payload.get("outputs") or {})
    group_manifest_path = _validation_resolve_path(
        outputs.get("session_group_manifest_json") or manifest_payload.get("session_group_manifest_path"),
        active_manifest.parent,
        None,
    )
    if group_manifest_path is None and _package_is_split_part(package):
        try:
            group_manifest_path = output_runner_logs_dir(_package_output_root(package)) / str(package.session_group_id) / "session_group_manifest.json"
        except Exception:
            group_manifest_path = None
    group_payload = _read_json_dict(group_manifest_path) if group_manifest_path is not None else {}
    entries = group_payload.get("parts") if isinstance(group_payload.get("parts"), list) else []
    part_reports: list[dict[str, Any]] = []
    active_key = str(active_manifest.resolve()).lower() if _focus_path_is_file(active_manifest) else str(active_manifest).lower()
    if entries:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            part_manifest = _validation_resolve_path(entry.get("session_manifest_path"), group_manifest_path.parent if group_manifest_path else active_manifest.parent)
            if part_manifest is None:
                continue
            entry_key = str(part_manifest.resolve()).lower() if _focus_path_is_file(part_manifest) else str(part_manifest).lower()
            part_reports.append(
                _validation_part_report(
                    part_manifest,
                    group_entry=entry,
                    fallback_package=package if entry_key == active_key else None,
                    completed_override=completed_override if entry_key == active_key else None,
                )
            )
    else:
        manifests: list[Path] = [active_manifest]
        for item in list(getattr(package, "sibling_part_manifest_paths", []) or []):
            candidate = Path(item)
            if str(candidate) and all(str(candidate) != str(existing) for existing in manifests):
                manifests.append(candidate)
        for manifest_path in manifests:
            entry_key = str(manifest_path.resolve()).lower() if _focus_path_is_file(manifest_path) else str(manifest_path).lower()
            part_reports.append(
                _validation_part_report(
                    manifest_path,
                    fallback_package=package if entry_key == active_key else None,
                    completed_override=completed_override if entry_key == active_key else None,
                )
            )
    part_reports.sort(key=lambda item: _validation_int(item.get("part_number"), default=9999))
    return part_reports, group_manifest_path, group_payload


def _validation_capture_part_snapshot(window: "FocusModeWindow", *, label: str) -> dict[str, Any]:
    package = window.package
    manifest_path = Path(getattr(package, "manifest_path", ""))
    completed = bool(window.result is not None and getattr(window.result, "completed", False))
    report = _validation_part_report(manifest_path, fallback_package=package, completed_override=completed)
    snapshot = {
        "label": label,
        "timestamp_unix": time.time(),
        "session_manifest": str(manifest_path),
        "session_dir": str(getattr(package, "session_dir", "")),
        "session_id": str(getattr(package, "session_id", "")),
        "session_group_id": str(getattr(package, "session_group_id", "")),
        "part_session_id": str(getattr(package, "part_session_id", "") or getattr(package, "session_id", "")),
        "part_number": getattr(package, "part_number", ""),
        "part_folder_name": str(getattr(package, "part_folder_name", "")),
        "completed": completed,
        "event_counts": dict(report.get("event_counts") or {}),
        "scoped_event_counts": dict(report.get("scoped_event_counts") or {}),
        "planned_tactile_cue_count": int(getattr(window, "planned_tactile_cue_count", 0) or 0),
        "cursor_recenter_count": len(getattr(window, "recenter_records", []) or []),
        "cursor_recenter_records": list(getattr(window, "recenter_records", []) or []),
        "validation_topup_approvals": list(getattr(window, "validation_topup_approval_records", []) or []),
    }
    snapshots = list(getattr(window, "validation_part_snapshots", []) or [])
    key = str(snapshot["part_session_id"] or snapshot["session_manifest"])
    retained = [
        item
        for item in snapshots
        if str(item.get("part_session_id") or item.get("session_manifest") or "") != key
    ]
    retained.append(snapshot)
    window.validation_part_snapshots = retained
    return snapshot


def _install_validation_auto_clicker(q: dict[str, Any], window: "FocusModeWindow") -> list[dict[str, Any]]:
    from PySide6.QtTest import QTest

    clicks: list[dict[str, Any]] = []
    start_gate_state: dict[str, Any] = {}
    instruction_attempts: dict[int, tuple[int, float]] = {}

    def _click(widget: Any, label: str) -> None:
        if widget is None or not widget.isEnabled():
            return
        QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
        clicks.append({"label": label, "timestamp_unix": time.time()})

    def _select_combo_data(combo: Any, value: str) -> None:
        try:
            index = combo.findData(value)
            if int(index) >= 0:
                combo.setCurrentIndex(index)
        except Exception:
            pass

    def _submit_mock_setup_if_needed() -> None:
        if bool(getattr(window, "demographics_submitted", False)):
            return
        try:
            if not str(window.participant_name_input.text() or "").strip():
                window.participant_name_input.setText("Mock Participant")
            if not str(window.age_input.text() or "").strip():
                window.age_input.setText("30")
            _select_combo_data(window.handedness_combo, "right")
            _select_combo_data(window.gender_combo, "prefer_not_to_say")
            _click(getattr(window, "setup_submit_button", None), "Submit setup")
        except Exception as exc:
            clicks.append({"label": "participant_setup_submit_failed", "message": str(exc), "timestamp_unix": time.time()})

    loaded_manifest_state = {"path": str(getattr(window.package, "manifest_path", ""))}

    def _reset_if_loaded_package_changed() -> None:
        current = str(getattr(window.package, "manifest_path", ""))
        if current == loaded_manifest_state["path"]:
            return
        loaded_manifest_state["path"] = current
        start_gate_state.clear()
        instruction_attempts.clear()

    def _click_start_when_ready() -> None:
        if window.result is not None:
            return
        _reset_if_loaded_package_changed()
        _submit_mock_setup_if_needed()
        if window.start_button.isEnabled() and _validation_start_gate_ready(clicks, start_gate_state, source="auto_clicker"):
            _click(window.start_button, str(window.start_button.text() or "Start Run"))
            q["QTimer"].singleShot(250, _click_start_when_ready)
            return
        q["QTimer"].singleShot(100, _click_start_when_ready)

    def _part2_start_gate_pending() -> bool:
        check = getattr(window, "_part2_start_gate_pending", None)
        if callable(check):
            try:
                return bool(check())
            except Exception:
                return False
        return False

    def _click_instruction_once(widget: Any, label: str, request_id: int) -> None:
        attempt_count, last_attempt = instruction_attempts.get(request_id, (0, 0.0))
        now = time.perf_counter()
        if attempt_count >= 5 or (attempt_count > 0 and now - last_attempt < 0.25):
            return
        instruction_attempts[request_id] = (attempt_count + 1, now)
        _click(widget, label)

    def _poll() -> None:
        if window.result is not None:
            _validation_capture_part_snapshot(window, label="before_accept")
            q["QTimer"].singleShot(250, window.dialog.accept)
            return
        _reset_if_loaded_package_changed()
        request = window.pending_instruction_request
        if request is not None:
            request_id = id(request)
            context = dict(request.get("context") or {})
            mode = str(context.get("mode") or "click")
            label = str(context.get("instruction_label") or "instruction")
            if _part2_start_gate_pending():
                _click_instruction_once(getattr(window, "start_part2_button", None), "Start Part 02", request_id)
            elif mode == "button":
                _click_instruction_once(window.instruction_button, f"instruction button: {label}", request_id)
            else:
                _click_instruction_once(window.target_button, f"instruction target: {label}", request_id)
        q["QTimer"].singleShot(50, _poll)

    q["QTimer"].singleShot(500, _click_start_when_ready)
    q["QTimer"].singleShot(650, _poll)
    return clicks


def _install_validation_participant_emulator(q: dict[str, Any], window: "FocusModeWindow") -> list[dict[str, Any]]:
    from PySide6.QtTest import QTest

    rng = __import__("random").Random(int(_env_float("PPS_FOCUS_VALIDATION_PARTICIPANT_SEED", 20260615)))
    miss_rate = max(0.0, min(1.0, _env_float("PPS_FOCUS_VALIDATION_PARTICIPANT_MISS_RATE", 0.06)))
    min_misses = max(0, int(_env_float("PPS_FOCUS_VALIDATION_PARTICIPANT_MIN_MISSES", 6)))
    delay_min_ms = max(100.0, _env_float("PPS_FOCUS_VALIDATION_PARTICIPANT_DELAY_MIN_MS", 150.0))
    delay_max_ms = max(delay_min_ms, _env_float("PPS_FOCUS_VALIDATION_PARTICIPANT_DELAY_MAX_MS", 850.0))
    topup_delay_min_ms = max(100.0, _env_float("PPS_FOCUS_VALIDATION_TOPUP_DELAY_MIN_MS", 140.0))
    topup_delay_max_ms = max(topup_delay_min_ms, _env_float("PPS_FOCUS_VALIDATION_TOPUP_DELAY_MAX_MS", 500.0))
    trial_end_margin_ms = max(0.0, _env_float("PPS_FOCUS_VALIDATION_TRIAL_END_MARGIN_MS", 650.0))
    backend_requested = os.environ.get("PPS_FOCUS_VALIDATION_MOUSE_BACKEND", "win32").strip().lower() or "win32"
    responses_only = _env_flag("PPS_FOCUS_VALIDATION_PARTICIPANT_RESPONSES_ONLY")
    records: list[dict[str, Any]] = []
    scheduled_events: set[str] = set()
    scheduled_response_keys: set[str] = set()
    completed_events: set[str] = set()
    pending: list[dict[str, Any]] = []
    start_gate_state: dict[str, Any] = {}
    part2_gate_state: dict[str, Any] = {}
    miss_keys: set[str] | None = None
    instruction_attempts: dict[int, tuple[int, float]] = {}
    loaded_manifest_state = {"path": str(getattr(window.package, "manifest_path", ""))}

    def _ensure_miss_plan() -> set[str]:
        nonlocal miss_keys
        if miss_keys is not None:
            return miss_keys
        if window.controller is None:
            return set()
        standard_records: list[tuple[str, str]] = []
        schedules = getattr(window.controller, "block_schedules", {}) or {}
        for block in getattr(window.package, "blocks", []):
            if bool(getattr(block, "metadata", {}).get("is_topup_block")):
                continue
            part = str(getattr(block, "metadata", {}).get("part_number") or getattr(block, "metadata", {}).get("phase_index") or "")
            schedule = schedules.get(block.index)
            if schedule is None:
                continue
            for schedule_event in getattr(schedule, "events", []):
                if getattr(schedule_event, "event_type", "") != "tactile_onset":
                    continue
                payload = dict(getattr(schedule_event, "payload", {}) or {})
                standard_records.append(
                    (_validation_event_key(block.index, payload, int(getattr(schedule_event, "sample_index", 0))), part)
                )
        standard_keys = [key for key, _part in standard_records]
        miss_count = min(len(standard_keys), max(min_misses, int(round(len(standard_keys) * miss_rate)))) if standard_keys else 0
        selected: set[str] = set()
        by_part: dict[str, list[str]] = {}
        for key, part in standard_records:
            by_part.setdefault(part or "single", []).append(key)
        for part_keys in by_part.values():
            if len(selected) >= miss_count:
                break
            selected.add(rng.choice(part_keys))
        remaining = [key for key in standard_keys if key not in selected]
        if miss_count > len(selected) and remaining:
            selected.update(rng.sample(remaining, min(len(remaining), miss_count - len(selected))))
        miss_keys = selected
        records.append(
            {
                "label": "participant_emulator_plan",
                "backend_requested": backend_requested,
                "standard_tactile_cue_count": len(standard_keys),
                "planned_miss_count": len(miss_keys),
                "part_count": len(by_part),
                "miss_rate": miss_rate,
                "delay_min_ms": delay_min_ms,
                "delay_max_ms": delay_max_ms,
                "trial_end_margin_ms": trial_end_margin_ms,
                "timestamp_unix": time.time(),
            }
        )
        return miss_keys

    def _target_center() -> tuple[int, int]:
        x, y, _source = _widget_screen_center(window.target_button)
        return x, y

    def _select_combo_data(combo: Any, value: str) -> None:
        try:
            index = combo.findData(value)
            if int(index) >= 0:
                combo.setCurrentIndex(index)
        except Exception:
            pass

    def _submit_mock_setup_if_needed() -> None:
        if responses_only:
            return
        if bool(getattr(window, "demographics_submitted", False)):
            return
        try:
            if not str(window.participant_name_input.text() or "").strip():
                window.participant_name_input.setText("Mock Participant")
            if not str(window.age_input.text() or "").strip():
                window.age_input.setText("30")
            _select_combo_data(window.handedness_combo, "right")
            _select_combo_data(window.gender_combo, "prefer_not_to_say")
            submit = getattr(window, "setup_submit_button", None)
            if submit is not None and submit.isEnabled():
                backend = _click_widget(submit, "Submit setup", preferred_backend="qtest")
                records.append({"label": "Submit setup", "backend": backend, "timestamp_unix": time.time()})
        except Exception as exc:
            records.append({"label": "participant_setup_submit_failed", "message": str(exc), "timestamp_unix": time.time()})

    def _reset_for_loaded_package() -> None:
        nonlocal miss_keys
        miss_keys = None
        scheduled_events.clear()
        scheduled_response_keys.clear()
        completed_events.clear()
        pending.clear()
        start_gate_state.clear()
        part2_gate_state.clear()
        instruction_attempts.clear()

    def _reset_if_loaded_package_changed() -> None:
        current = str(getattr(window.package, "manifest_path", ""))
        if current == loaded_manifest_state["path"]:
            return
        loaded_manifest_state["path"] = current
        _reset_for_loaded_package()

    def _activate_widget_for_os_click(widget: Any) -> None:
        try:
            window.dialog.raise_()
            window.dialog.activateWindow()
            _force_foreground_window(window.dialog)
            widget.setFocus(q["Qt"].FocusReason.MouseFocusReason)
            q["QApplication"].processEvents()
            time.sleep(0.02)
        except Exception:
            pass

    def _press_primary_key(label: str) -> str:
        try:
            window.dialog.raise_()
            window.dialog.activateWindow()
            _force_foreground_window(window.dialog)
            window.dialog.setFocus(q["Qt"].FocusReason.ShortcutFocusReason)
            q["QApplication"].processEvents()
            time.sleep(0.02)
        except Exception:
            pass
        if backend_requested == "pyautogui":
            try:
                import pyautogui  # type: ignore

                pyautogui.FAILSAFE = False
                pyautogui.PAUSE = 0
                pyautogui.press("space")
                return "pyautogui_space"
            except Exception as exc:
                records.append({"label": "pyautogui_keyboard_unavailable", "source": label, "message": str(exc), "timestamp_unix": time.time()})
        if backend_requested == "win32" and not window._offscreen_platform():
            try:
                import ctypes

                ctypes.windll.user32.keybd_event(0x20, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x20, 0, 0x0002, 0)
                return "win32_space"
            except Exception as exc:
                records.append({"label": "win32_keyboard_unavailable", "source": label, "message": str(exc), "timestamp_unix": time.time()})
        QTest.keyClick(window.dialog, q["Qt"].Key.Key_Space)
        return "qtest_space"

    def _logged_mouse_click_count() -> int:
        return len(_mouse_click_events())

    def _mouse_click_events() -> list[Any]:
        controller = window.controller
        logger = getattr(controller, "logger", None) if controller is not None else None
        events = getattr(logger, "events", []) if logger is not None else []
        return [event for event in events if getattr(event, "event_type", "") == "mouse_click"]

    def _latest_mouse_click_event() -> Any | None:
        events = _mouse_click_events()
        return events[-1] if events else None

    def _matched_tactile_event(item: dict[str, Any]) -> Any | None:
        controller = window.controller
        logger = getattr(controller, "logger", None) if controller is not None else None
        events = getattr(logger, "events", []) if logger is not None else []
        trial_uid = str(item.get("trial_uid") or "").strip()
        block_index = _validation_int(item.get("block_index"), default=0)
        for event in reversed(events):
            if getattr(event, "event_type", "") != "tactile_onset":
                continue
            payload = dict(getattr(event, "payload", {}) or {})
            event_trial_uid = str(payload.get("trial_uid") or payload.get("Trial_UID") or "").strip()
            event_block_index = _validation_int(payload.get("block_index") or payload.get("block_number"), default=0)
            if trial_uid and event_trial_uid != trial_uid:
                continue
            if block_index > 0 and event_block_index > 0 and event_block_index != block_index:
                continue
            return event
        return None

    def _bounded_validation_delay_ms(delay_ms: float, *, tactile_relative_s: Any = None, trial_end_relative_s: Any = None) -> tuple[float, float | None]:
        try:
            tactile_s = float(tactile_relative_s)
            trial_end_s = float(trial_end_relative_s)
        except (TypeError, ValueError):
            return float(delay_ms), None
        if not (math.isfinite(tactile_s) and math.isfinite(trial_end_s) and trial_end_s > tactile_s):
            return float(delay_ms), None
        max_delay_ms = max(100.0, (trial_end_s - tactile_s) * 1000.0 - trial_end_margin_ms)
        return min(float(delay_ms), max_delay_ms), max_delay_ms

    def _pump_click_events() -> None:
        try:
            q["QApplication"].processEvents()
            time.sleep(0.035)
            q["QApplication"].processEvents()
        except Exception:
            pass

    def _send_win32_click(widget: Any) -> str:
        if window._offscreen_platform():
            return "win32_skipped_offscreen"
        import ctypes

        x, y = _target_center() if widget is window.target_button else _widget_screen_center(widget)[:2]
        ctypes.windll.user32.SetCursorPos(int(x), int(y))
        time.sleep(0.035)
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.025)
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
        _pump_click_events()
        return "win32"

    def _try_external_click_process(
        widget: Any,
        label: str,
        preferred_backend: str,
        *,
        verify_target_click: bool,
        before_click_count: int,
    ) -> tuple[bool, str]:
        external_python = str(os.environ.get("PPS_FOCUS_VALIDATION_EXTERNAL_CLICK_PYTHON") or "").strip()
        if not external_python or preferred_backend not in {"pynput", "win32", "pyautogui"} or window._offscreen_platform():
            return False, preferred_backend
        x, y, coordinate_source = _widget_screen_center(widget)
        hwnd, client_x, client_y = _widget_win32_client_center(widget)

        def _attempt(*, window_message_only: bool) -> dict[str, Any]:
            result = _send_validation_external_mouse_click(
                x=int(x),
                y=int(y),
                backend=preferred_backend,
                python_path=external_python,
                hwnd=hwnd,
                client_x=client_x,
                client_y=client_y,
                window_message_only=window_message_only,
            )
            records.append(
                {
                    "label": "external_mouse_click_process",
                    "source_label": label,
                    "backend": preferred_backend,
                    "backend_transport": "external_python_process",
                    "coordinate_source": coordinate_source,
                    "x": int(x),
                    "y": int(y),
                    "hwnd": hwnd or "",
                    "client_x": client_x,
                    "client_y": client_y,
                    "window_message_only": bool(window_message_only),
                    "ok": bool(result.get("ok")),
                    "returncode": result.get("returncode"),
                    "raw_input_sent": bool(result.get("raw_input_sent")),
                    "window_message_sent": bool(result.get("window_message_sent")),
                    "error": str(result.get("error") or result.get("stderr") or result.get("raw_input_error") or ""),
                    "timestamp_unix": time.time(),
                }
            )
            _pump_click_events()
            return result

        result = _attempt(window_message_only=False)
        _pump_click_events()
        if not verify_target_click or _logged_mouse_click_count() > before_click_count:
            return bool(result.get("ok")), preferred_backend
        if hwnd:
            fallback = _attempt(window_message_only=True)
            _pump_click_events()
            if _logged_mouse_click_count() > before_click_count:
                return bool(fallback.get("ok")), f"{preferred_backend}+win32_message_fallback"
        return bool(result.get("ok")), preferred_backend

    def _click_widget(widget: Any, label: str, *, preferred_backend: str = "qtest") -> str:
        if widget is None or not widget.isEnabled():
            return "skipped_disabled"
        verify_target_click = (
            widget is window.target_button
            and window.controller is not None
            and window.pending_instruction_request is None
        )
        before_clicks = _logged_mouse_click_count() if verify_target_click else -1
        backend_used = preferred_backend
        if preferred_backend == "qtest" or window._offscreen_platform():
            QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
            _pump_click_events()
            return "qtest_control"
        _activate_widget_for_os_click(widget)
        external_attempted, external_backend = _try_external_click_process(
            widget,
            label,
            preferred_backend,
            verify_target_click=verify_target_click,
            before_click_count=before_clicks,
        )
        if external_attempted:
            if not verify_target_click or _logged_mouse_click_count() > before_clicks:
                return external_backend
            records.append(
                {
                    "label": "external_mouse_click_not_observed",
                    "source_label": label,
                    "backend": external_backend,
                    "before_mouse_click_count": before_clicks,
                    "after_mouse_click_count": _logged_mouse_click_count(),
                    "timestamp_unix": time.time(),
                }
            )
        if preferred_backend == "pyautogui":
            try:
                import pyautogui  # type: ignore

                pyautogui.FAILSAFE = False
                pyautogui.PAUSE = 0
                x, y, _source = _widget_screen_center(widget)
                pyautogui.click(int(x), int(y))
                _pump_click_events()
                return "pyautogui"
            except Exception as exc:
                records.append({"label": "pyautogui_backend_unavailable", "message": str(exc), "timestamp_unix": time.time()})
                backend_used = "pynput"
        if backend_used == "pynput":
            try:
                from pynput.mouse import Button, Controller

                mouse = Controller()
                x, y, _source = _widget_screen_center(widget)
                mouse.position = (int(x), int(y))
                time.sleep(0.035)
                mouse.press(Button.left)
                time.sleep(0.025)
                mouse.release(Button.left)
                _pump_click_events()
                if verify_target_click and _logged_mouse_click_count() <= before_clicks:
                    try:
                        fallback = _send_win32_click(widget)
                        if _logged_mouse_click_count() > before_clicks:
                            return f"pynput+{fallback}_recovery"
                    except Exception as fallback_exc:
                        records.append({"label": "win32_recovery_unavailable", "message": str(fallback_exc), "timestamp_unix": time.time()})
                    QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
                    _pump_click_events()
                    return "pynput+qtest_recovery"
                return "pynput"
            except Exception as exc:
                records.append({"label": "pynput_backend_unavailable", "message": str(exc), "timestamp_unix": time.time()})
                backend_used = "win32"
        if backend_used == "win32" and not window._offscreen_platform():
            try:
                backend = _send_win32_click(widget)
                if verify_target_click and _logged_mouse_click_count() <= before_clicks:
                    QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
                    _pump_click_events()
                    return f"{backend}+qtest_recovery"
                return backend
            except Exception as exc:
                records.append({"label": "win32_backend_unavailable", "message": str(exc), "timestamp_unix": time.time()})
        QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
        _pump_click_events()
        return "qtest"

    def _continue_instruction_if_needed() -> None:
        if responses_only:
            return
        request = window.pending_instruction_request
        if request is None:
            return
        request_id = id(request)
        attempt_count, last_attempt = instruction_attempts.get(request_id, (0, 0.0))
        now = time.perf_counter()
        if attempt_count >= 5 or (attempt_count > 0 and now - last_attempt < 0.5):
            return
        instruction_attempts[request_id] = (attempt_count + 1, now)
        context = dict(request.get("context") or {})
        mode = str(context.get("mode") or "click")
        label = str(context.get("instruction_label") or "instruction")
        part2_pending = False
        check_part2 = getattr(window, "_part2_start_gate_pending", None)
        if callable(check_part2):
            try:
                part2_pending = bool(check_part2())
            except Exception:
                part2_pending = False
        if part2_pending:
            _click_part2_start_gate(source="instruction")
            return
        backend = _press_primary_key(f"instruction: {label}")
        records.append(
            {
                "label": f"instruction_continue:{label}",
                "mode": mode,
                "backend": backend,
                "timestamp_unix": time.time(),
            }
        )

    def _part2_start_gate_ready() -> bool:
        check_part2 = getattr(window, "_part2_start_gate_pending", None)
        if callable(check_part2):
            try:
                if bool(check_part2()):
                    return True
            except Exception:
                pass
        for widget in (getattr(window, "start_part2_button", None), getattr(window, "start_button", None)):
            try:
                label = str(widget.text() or "")
            except Exception:
                label = ""
            if widget is not None and widget.isEnabled() and label.strip() in {"Start Part 02", "Start Part 2"}:
                return True
        return False

    def _click_part2_start_gate(*, source: str) -> bool:
        if responses_only:
            return False
        if not _part2_start_gate_ready():
            return False
        now = time.perf_counter()
        last_attempt = float(part2_gate_state.get("last_attempt_monotonic") or 0.0)
        if now - last_attempt < 0.5:
            return False
        part2_gate_state["last_attempt_monotonic"] = now
        for widget in (getattr(window, "start_part2_button", None), getattr(window, "start_button", None)):
            if widget is None or not widget.isEnabled():
                continue
            backend = _click_widget(widget, "Start Part 02", preferred_backend="qtest")
            records.append(
                {
                    "label": "Start Part 02",
                    "mode": "part_transition",
                    "source": source,
                    "backend": backend,
                    "timestamp_unix": time.time(),
                }
            )
            return True
        return False

    def _schedule_tactile_events() -> None:
        controller = window.controller
        if controller is None:
            return
        active_miss_keys = _ensure_miss_plan()
        for event in controller.logger.events:
            event_key = f"event:{event.event_id}"
            if event.event_type != "tactile_onset" or event_key in scheduled_events:
                continue
            payload = dict(event.payload or {})
            is_topup = _truthy(payload.get("is_topup") or payload.get("Is_Topup") or payload.get("block_is_topup_block"))
            block_index = _validation_int(payload.get("block_index") or payload.get("block_number"), default=0)
            sample_index = _validation_int(payload.get("sample_index") or payload.get("planned_sample_index"), default=0)
            key = _validation_event_key(block_index, payload, sample_index)
            if key in scheduled_response_keys:
                scheduled_events.add(event_key)
                continue
            should_miss = (not is_topup) and key in active_miss_keys
            if is_topup:
                delay_ms = rng.uniform(topup_delay_min_ms, topup_delay_max_ms)
                action = "topup_click"
            elif should_miss:
                delay_ms = 0.0
                action = "deliberate_miss"
            else:
                delay_ms = rng.uniform(delay_min_ms, delay_max_ms)
                action = "standard_click"
            uncapped_delay_ms = float(delay_ms)
            delay_cap_ms = None
            if not should_miss:
                delay_ms, delay_cap_ms = _bounded_validation_delay_ms(
                    delay_ms,
                    tactile_relative_s=payload.get("relative_time_s") or payload.get("tactile_onset_s") or payload.get("Tactile_Onset_S"),
                    trial_end_relative_s=payload.get("trial_end_s") or payload.get("Trial_End_S"),
                )
            scheduled_events.add(event_key)
            scheduled_response_keys.add(key)
            item = {
                "event_id": event.event_id,
                "schedule_key": event_key,
                "trial_uid": str(payload.get("trial_uid") or payload.get("Trial_UID") or ""),
                "source_trial_uid": str(payload.get("source_trial_uid") or payload.get("Source_Trial_UID") or ""),
                "block_index": block_index,
                "is_topup": is_topup,
                "topup_role": str(payload.get("topup_role") or payload.get("Topup_Role") or ""),
                "action": action,
                "tactile_monotonic_time": float(event.monotonic_time),
                "due_monotonic_time": float(event.monotonic_time) + delay_ms / 1000.0,
                "planned_delay_ms": delay_ms,
                "uncapped_delay_ms": uncapped_delay_ms,
                "delay_cap_ms": delay_cap_ms,
            }
            if should_miss:
                completed_events.add(event_key)
                records.append({**item, "label": "tactile_response_plan", "timestamp_unix": time.time()})
            else:
                pending.append(item)

    def _timeline_block_is_topup(block_index: int) -> bool:
        controller = window.controller
        active_block = getattr(controller, "_active_block", None) if controller is not None else None
        metadata = dict(getattr(active_block, "metadata", {}) or {}) if active_block is not None else {}
        active_index = _validation_int(getattr(active_block, "index", ""), default=-1) if active_block is not None else -1
        if active_index == int(block_index):
            return _truthy(metadata.get("is_topup") or metadata.get("is_topup_block"))
        item = window._run_plan_item_by_number(getattr(window, "active_display_block_index", None) or 0)
        return bool(item is not None and str(item.get("kind") or "") == "topup")

    def _schedule_timeline_cues() -> None:
        controller = window.controller
        timeline = getattr(window, "timeline_state", None)
        anchor = getattr(window, "_timeline_perf_anchor", None)
        if controller is None or timeline is None or not bool(getattr(timeline, "active", False)):
            return
        if anchor is None:
            return
        block_index = _validation_int(getattr(timeline, "block_index", ""), default=0)
        if block_index <= 0:
            return
        active_miss_keys = _ensure_miss_plan()
        is_topup = _timeline_block_is_topup(block_index)
        for cue in list(getattr(timeline, "cues", []) or []):
            sample_index = getattr(cue, "sample_index", None)
            payload = {"trial_uid": getattr(cue, "trial_uid", ""), "trial_number": getattr(cue, "trial_number", "")}
            key = _validation_event_key(
                block_index,
                payload,
                _validation_int(sample_index, default=int(getattr(cue, "cue_id", 0) or 0)),
            )
            event_key = f"timeline:{block_index}:{getattr(cue, 'cue_id', '')}:{getattr(cue, 'trial_uid', '')}"
            if event_key in scheduled_events or key in scheduled_response_keys:
                scheduled_events.add(event_key)
                continue
            should_miss = (not is_topup) and key in active_miss_keys
            if is_topup:
                delay_ms = rng.uniform(topup_delay_min_ms, topup_delay_max_ms)
                action = "topup_click"
            elif should_miss:
                delay_ms = 0.0
                action = "deliberate_miss"
            else:
                delay_ms = rng.uniform(delay_min_ms, delay_max_ms)
                action = "standard_click"
            uncapped_delay_ms = float(delay_ms)
            delay_cap_ms = None
            if not should_miss:
                segment = timeline.segment_at(float(getattr(cue, "time_s", 0.0) or 0.0))
                trial_end_s = getattr(segment, "end_s", None) if segment is not None else getattr(timeline, "duration_s", None)
                delay_ms, delay_cap_ms = _bounded_validation_delay_ms(
                    delay_ms,
                    tactile_relative_s=getattr(cue, "time_s", None),
                    trial_end_relative_s=trial_end_s,
                )
            scheduled_events.add(event_key)
            scheduled_response_keys.add(key)
            tactile_monotonic = float(anchor) + float(getattr(cue, "time_s", 0.0) or 0.0)
            item = {
                "event_id": event_key,
                "schedule_key": event_key,
                "trial_uid": str(getattr(cue, "trial_uid", "") or ""),
                "source_trial_uid": "",
                "block_index": block_index,
                "is_topup": is_topup,
                "topup_role": "timeline",
                "action": action,
                "tactile_monotonic_time": tactile_monotonic,
                "due_monotonic_time": tactile_monotonic + delay_ms / 1000.0,
                "planned_delay_ms": delay_ms,
                "uncapped_delay_ms": uncapped_delay_ms,
                "delay_cap_ms": delay_cap_ms,
                "schedule_source": "timeline",
            }
            if should_miss:
                completed_events.add(event_key)
                records.append({**item, "label": "tactile_response_plan", "timestamp_unix": time.time()})
            else:
                pending.append(item)

    def _fire_due_responses() -> None:
        now = time.perf_counter()
        for item in list(pending):
            schedule_key = str(item.get("schedule_key") or item.get("event_id"))
            if schedule_key in completed_events or now < float(item["due_monotonic_time"]):
                continue
            before_click_count = _logged_mouse_click_count()
            backend = _click_widget(window.target_button, f"tactile response {item['trial_uid']}", preferred_backend=backend_requested)
            mouse_event = _latest_mouse_click_event() if _logged_mouse_click_count() > before_click_count else None
            mouse_monotonic = getattr(mouse_event, "monotonic_time", None) if mouse_event is not None else None
            tactile_event = _matched_tactile_event(item)
            tactile_monotonic = getattr(tactile_event, "monotonic_time", None) if tactile_event is not None else item["tactile_monotonic_time"]
            try:
                actual_delay_ms = (float(mouse_monotonic) - float(tactile_monotonic)) * 1000.0
            except (TypeError, ValueError):
                actual_delay_ms = (time.perf_counter() - float(item["tactile_monotonic_time"])) * 1000.0
            completed_events.add(schedule_key)
            pending.remove(item)
            records.append(
                {
                    **item,
                    "label": "tactile_response_click",
                    "backend": backend,
                    "actual_delay_ms": actual_delay_ms,
                    "mouse_event_id": getattr(mouse_event, "event_id", "") if mouse_event is not None else "",
                    "tactile_event_id": getattr(tactile_event, "event_id", "") if tactile_event is not None else "",
                    "actual_tactile_monotonic_time": float(tactile_monotonic) if tactile_monotonic is not None else "",
                    "timestamp_unix": time.time(),
                }
            )

    def _poll() -> None:
        _reset_if_loaded_package_changed()
        if _click_part2_start_gate(source="result_boundary"):
            q["QTimer"].singleShot(20, _poll)
            return
        if window.result is not None:
            _validation_capture_part_snapshot(window, label="before_accept")
            q["QTimer"].singleShot(1000, window.dialog.accept)
            return
        _submit_mock_setup_if_needed()
        part2_clicked = _click_part2_start_gate(source="poll")
        if (
            not responses_only and
            not part2_clicked and
            window.start_button.isEnabled()
            and _validation_start_gate_ready(records, start_gate_state, source="participant_emulator")
        ):
            start_label = str(window.start_button.text() or "Start Run")
            backend = _press_primary_key(start_label)
            records.append({"label": start_label, "backend": backend, "timestamp_unix": time.time()})
        _continue_instruction_if_needed()
        _schedule_timeline_cues()
        _schedule_tactile_events()
        _fire_due_responses()
        q["QTimer"].singleShot(20, _poll)

    q["QTimer"].singleShot(500, _poll)
    return records


def _validation_event_key(block_index: int, payload: dict[str, Any], sample_index: int) -> str:
    trial_uid = str(payload.get("trial_uid") or payload.get("Trial_UID") or "").strip()
    if trial_uid:
        return f"{block_index}:{trial_uid}"
    trial_number = str(payload.get("trial_number") or payload.get("Trial_Number") or "").strip()
    return f"{block_index}:{trial_number}:{sample_index}"


def _validation_int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none", "off"}


def _write_validation_focus_report(
    path: Path,
    *,
    session_manifest: Path,
    package: Any,
    exit_code: int,
    window: "FocusModeWindow",
    validation_clicks: list[dict[str, Any]],
    engine: _ValidationFastAudioEngine | None,
) -> None:
    active_completed = bool(window.result is not None and getattr(window.result, "completed", False))
    _validation_capture_part_snapshot(window, label="final_report")
    parts, group_manifest_path, group_payload = _validation_split_part_reports(
        Path(session_manifest),
        package,
        completed_override=active_completed,
    )
    snapshots = list(getattr(window, "validation_part_snapshots", []) or [])
    snapshots_by_part_session = {
        str(item.get("part_session_id") or ""): item
        for item in snapshots
        if str(item.get("part_session_id") or "").strip()
    }
    snapshots_by_manifest = {
        str(item.get("session_manifest") or ""): item
        for item in snapshots
        if str(item.get("session_manifest") or "").strip()
    }
    for part in parts:
        snapshot = snapshots_by_part_session.get(str(part.get("part_session_id") or "")) or snapshots_by_manifest.get(
            str(part.get("session_manifest") or "")
        )
        if snapshot:
            part["validation_snapshot"] = snapshot
            part["planned_tactile_cue_count"] = int(snapshot.get("planned_tactile_cue_count") or 0)
            part["cursor_recenter_count"] = int(snapshot.get("cursor_recenter_count") or 0)
            part["cursor_recenter_records"] = list(snapshot.get("cursor_recenter_records") or [])
            part["validation_topup_approvals"] = list(snapshot.get("validation_topup_approvals") or [])
    if not parts:
        parts = [_validation_part_report(Path(session_manifest), fallback_package=package, completed_override=active_completed)]
    aggregate_event_counts = _validation_merge_event_counts([dict(part.get("event_counts") or {}) for part in parts])
    aggregate_scoped_counts = _validation_merge_scoped_event_counts([dict(part.get("scoped_event_counts") or {}) for part in parts])
    standard_event_counts = dict(aggregate_scoped_counts.get("standard") or {})
    standard_block_end_count = int(standard_event_counts.get("block_end") or aggregate_event_counts.get("block_end") or 0)
    standard_trial_start_count = int(standard_event_counts.get("trial_start") or aggregate_event_counts.get("trial_start") or 0)
    standard_trial_end_count = int(standard_event_counts.get("trial_end") or aggregate_event_counts.get("trial_end") or 0)
    expected_part_count = _validation_int(group_payload.get("parts_per_participant"), default=len(parts))
    if expected_part_count <= 0:
        expected_part_count = len(parts)
    completed_part_count = sum(1 for part in parts if bool(part.get("completed")))
    split_run = bool(group_manifest_path is not None or _package_is_split_part(package) or expected_part_count > 1 or len(parts) > 1)
    all_parts_completed = bool(parts) and completed_part_count >= expected_part_count and all(bool(part.get("completed")) for part in parts)
    active_manifest = str(Path(session_manifest))
    active_part = next((part for part in parts if str(part.get("session_manifest") or "") == active_manifest), parts[-1])
    cursor_recenter_records: list[dict[str, Any]] = []
    validation_topup_approvals: list[dict[str, Any]] = []
    planned_tactile_cue_count = 0
    for snapshot in snapshots:
        planned_tactile_cue_count += int(snapshot.get("planned_tactile_cue_count") or 0)
        cursor_recenter_records.extend(list(snapshot.get("cursor_recenter_records") or []))
        validation_topup_approvals.extend(list(snapshot.get("validation_topup_approvals") or []))
    if not snapshots:
        planned_tactile_cue_count = int(getattr(window, "planned_tactile_cue_count", 0) or 0)
        cursor_recenter_records = list(getattr(window, "recenter_records", []) or [])
        validation_topup_approvals = list(getattr(window, "validation_topup_approval_records", []) or [])
    events_csvs = [str(part.get("events_csv") or "") for part in parts if str(part.get("events_csv") or "").strip()]
    analysis_dirs = [str(part.get("analysis_dir") or "") for part in parts if str(part.get("analysis_dir") or "").strip()]
    topup_dirs = [str(part.get("topup_dir") or "") for part in parts if str(part.get("topup_dir") or "").strip()]
    payload = {
        "schema": "pps-focus-mode-packaged-validation.v1",
        "session_manifest": str(session_manifest),
        "session_dir": str(package.session_dir),
        "session_group_manifest": str(group_manifest_path or ""),
        "session_group_id": str(group_payload.get("session_group_id") or getattr(package, "session_group_id", "") or ""),
        "events_csv": str(active_part.get("events_csv") or ""),
        "events_csvs": events_csvs,
        "analysis_dir": str(active_part.get("analysis_dir") or ""),
        "analysis_dirs": analysis_dirs,
        "topup_dir": str(active_part.get("topup_dir") or ""),
        "topup_dirs": topup_dirs,
        "exit_code": int(exit_code),
        "completed": bool(all_parts_completed if split_run else active_completed),
        "expected_part_count": int(expected_part_count),
        "completed_part_count": int(completed_part_count),
        "all_parts_completed": bool(all_parts_completed),
        "parts": parts,
        "event_counts": aggregate_event_counts,
        "scoped_event_counts": aggregate_scoped_counts,
        "aggregate_event_counts": aggregate_event_counts,
        "aggregate_scoped_event_counts": aggregate_scoped_counts,
        "block_count": standard_block_end_count,
        "block_end_count": standard_block_end_count,
        "trial_start_count": standard_trial_start_count,
        "trial_end_count": standard_trial_end_count,
        "total_block_end_count": int(aggregate_event_counts.get("block_end", 0)),
        "total_trial_start_count": int(aggregate_event_counts.get("trial_start", 0)),
        "total_trial_end_count": int(aggregate_event_counts.get("trial_end", 0)),
        "validation_mouse_clicks": validation_clicks,
        "validation_topup_approvals": validation_topup_approvals,
        "validation_part_snapshots": snapshots,
        "planned_tactile_cue_count": int(planned_tactile_cue_count),
        "cursor_recenter_records": cursor_recenter_records,
        "cursor_recenter_count": len(cursor_recenter_records),
        "played_block_count": len(engine.played_blocks) if engine is not None else None,
        "played_block_duration_s": sum(getattr(engine, "played_block_durations_s", [])) if engine is not None else None,
        "played_block_durations_s": list(getattr(engine, "played_block_durations_s", [])) if engine is not None else [],
        "played_instruction_count": len(engine.played_instructions) if engine is not None else None,
        "played_instruction_duration_s": sum(getattr(engine, "played_instruction_durations_s", [])) if engine is not None else None,
        "validation_audio_realtime": bool(getattr(engine, "realtime", False)) if engine is not None else False,
    }
    if window.result is not None:
        analysis_outputs = dict(getattr(window.result, "analysis_outputs", {}) or {})
        payload["analysis_outputs"] = {str(key): str(value) for key, value in analysis_outputs.items()}
        payload["external_labrecorder_xdf"] = str(analysis_outputs.get("external_labrecorder_xdf") or "")
        payload["external_labrecorder_report"] = str(analysis_outputs.get("external_labrecorder_report") or "")
        payload["external_labrecorder_stdout"] = str(analysis_outputs.get("external_labrecorder_stdout") or "")
        payload["external_labrecorder_stderr"] = str(analysis_outputs.get("external_labrecorder_stderr") or "")
    os.makedirs(_output_filesystem_path(path.parent), exist_ok=True)
    with open(_output_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_validation_launcher_report(
    path: Path,
    *,
    selected_manifest: Path | None,
    exit_code: int,
    profile_count: int,
    selected_profile: str,
    validation_clicks: list[dict[str, Any]],
) -> None:
    payload = {
        "schema": "pps-standalone-launcher-packaged-validation.v1",
        "selected_manifest": str(selected_manifest or ""),
        "exit_code": int(exit_code),
        "profile_count": int(profile_count),
        "selected_profile": selected_profile,
        "validation_mouse_clicks": validation_clicks,
    }
    os.makedirs(_output_filesystem_path(path.parent), exist_ok=True)
    with open(_output_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")


class _FocusCompanionBridge:
    """Marshals companion API calls onto the Focus Mode Qt/UI thread."""

    def __init__(self, window: "FocusModeWindow") -> None:
        self.window = window

    def _call(self, callback: Callable[[], dict[str, Any]], *, timeout_s: float = 5.0) -> dict[str, Any]:
        if threading.get_ident() == getattr(self.window, "_ui_thread_id", None):
            return callback()
        future: Future[dict[str, Any]] = Future()
        self.window._companion_command_queue.put((future, callback))
        try:
            return future.result(timeout=max(0.1, float(timeout_s)))
        except FutureTimeoutError as exc:
            raise CompanionCommandError(
                "Focus Mode did not answer the companion request in time.",
                status_code=503,
                reason="ui_timeout",
            ) from exc

    def health(self) -> dict[str, Any]:
        return self._call(self.window._companion_health, timeout_s=2.0)

    def snapshot(self) -> dict[str, Any]:
        return self._call(self.window._companion_snapshot, timeout_s=2.0)

    def submit_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(lambda: self.window._companion_submit_setup(payload), timeout_s=10.0)

    def continue_instruction(self) -> dict[str, Any]:
        return self._call(self.window._companion_continue_instruction, timeout_s=5.0)

    def start_part(self, part_number: int) -> dict[str, Any]:
        return self._call(lambda: self.window._companion_start_part(part_number), timeout_s=5.0)

    def pause(self) -> dict[str, Any]:
        return self._call(lambda: self.window._companion_set_paused(True), timeout_s=5.0)

    def resume(self) -> dict[str, Any]:
        return self._call(lambda: self.window._companion_set_paused(False), timeout_s=5.0)

    def mobile_packages(self) -> dict[str, Any]:
        return self._call(self.window._companion_mobile_packages, timeout_s=10.0)

    def mobile_package_manifest(self, package_id: str) -> dict[str, Any]:
        return self._call(lambda: self.window._companion_mobile_package_manifest(package_id), timeout_s=30.0)

    def mobile_package_asset_path(self, package_id: str, asset_id: str) -> tuple[str, str]:
        payload = self._call(
            lambda: self.window._companion_mobile_package_asset_path(package_id, asset_id),
            timeout_s=5.0,
        )
        return str(payload.get("path") or ""), str(payload.get("media_type") or "application/octet-stream")

    def mobile_run_events(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(lambda: self.window._companion_mobile_run_events(run_id, payload), timeout_s=10.0)

    def mobile_run_complete(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(lambda: self.window._companion_mobile_run_complete(run_id, payload), timeout_s=10.0)


def _windows_wifi_direct_status() -> dict[str, Any]:
    status = {
        "available": False,
        "adapter_detected": False,
        "hosted_network_supported": False,
        "wireless_display_supported": False,
        "message": "Wi-Fi Direct status was not checked.",
    }
    try:
        completed = subprocess.run(
            ["netsh", "wlan", "show", "drivers"],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception as exc:  # noqa: BLE001 - status-only diagnostic
        status["message"] = f"Wi-Fi Direct check unavailable: {exc}"
        return status
    output = str(completed.stdout or completed.stderr or "")
    lower = output.lower()
    status["wireless_display_supported"] = "wireless display supported" in lower and "yes" in lower
    status["hosted_network_supported"] = "hosted network supported" in lower and "yes" in lower
    try:
        adapters = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance -ClassName Win32_NetworkAdapter | "
                "Where-Object { $_.Name -match 'Wi-Fi Direct' } | "
                "Select-Object -ExpandProperty Name",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
        status["adapter_detected"] = bool(str(adapters.stdout or "").strip())
    except Exception:
        status["adapter_detected"] = False
    status["available"] = bool(status["adapter_detected"] or status["wireless_display_supported"])
    if status["available"]:
        status["message"] = (
            "Wi-Fi Direct-capable Windows adapter detected. Use this fallback after the phone and PC are "
            "joined to the same direct link; same-Wi-Fi LAN remains the primary transfer path."
        )
    else:
        status["message"] = "No usable Windows Wi-Fi Direct adapter was detected. Use same-Wi-Fi LAN or the manual URI."
    if "hosted network supported" in lower and not status["hosted_network_supported"]:
        status["message"] += " Legacy hosted-network commands are not supported by this driver."
    return status


class _PhoneTransferBridge:
    """Companion bridge for phone-owned experiment transfer without PC playback."""

    def __init__(
        self,
        *,
        packages: list[Any],
        transfer_id: str,
        profile_id: str,
        participant_id: str,
        port: int,
    ) -> None:
        self.packages = list(packages)
        self.transfer_id = str(transfer_id or "")
        self.profile_id = str(profile_id or "")
        self.participant_id = str(participant_id or "")
        self.port = int(port)
        self.sequence = 0

    def health(self) -> dict[str, Any]:
        package_list = build_mobile_package_list(self.packages, phone_owned_session=True)
        package_rows = list(package_list.get("packages") or [])
        return {
            "schema": HEALTH_SCHEMA,
            "service": "pps-phone-transfer",
            "status": "ok",
            "session_id": self.transfer_id,
            "participant_id": self.participant_id,
            "profile_id": self.profile_id,
            "port": self.port,
            "transfer_mode": "phone_export",
            "mobile_runtime": {
                "enabled": True,
                "phone_owned_session": True,
                "package_count": len(package_rows),
                "active_package_id": str(package_list.get("active_package_id") or ""),
                "mobile_runnable": bool(package_rows) and all(bool(item.get("mobile_runnable")) for item in package_rows),
            },
        }

    def snapshot(self) -> dict[str, Any]:
        self.sequence += 1
        return {
            "schema": SNAPSHOT_SCHEMA,
            "sequence": self.sequence,
            "server_unix_ms": int(time.time() * 1000),
            "server_perf_counter_s": time.perf_counter(),
            "connection_state": "phone_export_ready",
            "allowed_commands": [],
            "participant": {
                "participant_id": self.participant_id,
                "session_id": self.transfer_id,
                "selected_participant_id": self.participant_id,
            },
            "setup": {
                "submitted": True,
                "ready": True,
                "participant_name_present": False,
                "name_sharing_opt_in": False,
                "age": "",
                "handedness": "",
                "gender": "",
            },
            "part_status": {"available_parts": [], "selected_part": "", "current_package_part": "", "pending_start_part": ""},
            "run_status": {
                "running": False,
                "paused": False,
                "complete": False,
                "state_label": "Phone export ready",
                "event_label": "Phone owns the run session.",
            },
            "active_block": {"active": False, "running": False, "paused": False, "instruction_waiting": False},
            "timeline": {"trial_rows": [], "tactile_cues": [], "clicks": [], "counts": {}},
            "topup": {"draft_count": 0},
            "instruction_gate": {"waiting": False, "part2_start_gate": False, "instruction_label": "", "button_label": ""},
        }

    def _phone_export_only(self) -> dict[str, Any]:
        raise CompanionCommandError(
            "This QR serves phone-owned experiment packages only.",
            status_code=409,
            reason="phone_export_only",
        )

    def submit_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._phone_export_only()

    def continue_instruction(self) -> dict[str, Any]:
        return self._phone_export_only()

    def start_part(self, part_number: int) -> dict[str, Any]:
        return self._phone_export_only()

    def pause(self) -> dict[str, Any]:
        return self._phone_export_only()

    def resume(self) -> dict[str, Any]:
        return self._phone_export_only()

    def mobile_packages(self) -> dict[str, Any]:
        return build_mobile_package_list(self.packages, phone_owned_session=True)

    def mobile_package_manifest(self, package_id: str) -> dict[str, Any]:
        package = self._package_for_id(package_id)
        if package is None:
            raise CompanionCommandError(status_code=404, reason="mobile_package_not_found")
        return build_mobile_package_manifest(package, phone_owned_session=True)

    def mobile_package_asset_path(self, package_id: str, asset_id: str) -> tuple[str, str]:
        package = self._package_for_id(package_id)
        if package is None:
            raise CompanionCommandError(status_code=404, reason="mobile_package_not_found")
        try:
            path = mobile_asset_path(package, package_id, asset_id)
        except MobileRuntimePackageError as exc:
            raise CompanionCommandError(str(exc), status_code=404, reason="mobile_asset_not_found") from exc
        return str(path), "audio/wav"

    def mobile_run_events(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": "pps-mobile-run-events.v1",
            "status": "accepted_phone_owned_no_pc_copy",
            "run_id": str(run_id or ""),
            "event_count": len(list((payload or {}).get("events") or [])),
        }

    def mobile_run_complete(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": "pps-mobile-run-complete.v1",
            "status": "accepted_phone_owned_no_pc_copy",
            "run_id": str(run_id or ""),
            "event_count": len(list((payload or {}).get("events") or [])),
        }

    def _package_for_id(self, package_id: str) -> Any | None:
        clean = str(package_id or "").strip()
        for package in self.packages:
            if mobile_package_id(package) == clean:
                return package
        return None


class _FocusTactileCalibrationCollector:
    """Thread-safe target-click collector for tactile calibration trials."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._trial: dict[str, Any] | None = None
        self._first_response: dict[str, Any] | None = None
        self._valid_response: dict[str, Any] | None = None

    def start_trial(
        self,
        *,
        trial_index: int,
        phase: str,
        level_percent: float,
        is_catch: bool,
        estimated_onset_perf: float,
        valid_start_perf: float,
        valid_end_perf: float,
    ) -> None:
        with self._condition:
            self._trial = {
                "trial_index": int(trial_index),
                "phase": str(phase),
                "level_percent": float(level_percent),
                "is_catch": bool(is_catch),
                "estimated_onset_perf": float(estimated_onset_perf),
                "valid_start_perf": float(valid_start_perf),
                "valid_end_perf": float(valid_end_perf),
            }
            self._first_response = None
            self._valid_response = None
            self._condition.notify_all()

    def record_click(
        self,
        *,
        in_target: bool = True,
        x: int | None = None,
        y: int | None = None,
        source: str = "",
    ) -> dict[str, Any] | None:
        now = time.perf_counter()
        with self._condition:
            trial = dict(self._trial or {})
            if not trial:
                return None
            valid = float(trial["valid_start_perf"]) <= now <= float(trial["valid_end_perf"])
            response = {
                "trial_index": int(trial.get("trial_index") or 0),
                "response_perf": now,
                "response_latency_ms": (now - float(trial["estimated_onset_perf"])) * 1000.0,
                "valid_response": bool(valid),
                "response_x": "" if x is None else int(x),
                "response_y": "" if y is None else int(y),
                "response_in_target": bool(in_target),
                "response_source": str(source or ""),
            }
            if self._first_response is None:
                self._first_response = dict(response)
            if valid and self._valid_response is None:
                self._valid_response = dict(response)
                self._condition.notify_all()
            return response

    def wait_for_response(self, *, until_perf: float) -> dict[str, Any] | None:
        with self._condition:
            while self._valid_response is None:
                remaining = float(until_perf) - time.perf_counter()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=min(0.1, remaining))
            if self._valid_response is not None:
                return dict(self._valid_response)
            return None if self._first_response is None else dict(self._first_response)

    def finish_trial(self) -> None:
        with self._condition:
            self._trial = None
            self._first_response = None
            self._valid_response = None
            self._condition.notify_all()


class FocusModeWindow:
    """Dashboard-styled native participant runner window."""

    def __init__(
        self,
        q: dict[str, Any],
        package: Any,
        *,
        capture_options: SessionCaptureOptions | None = None,
        enable_missed_trial_topup: bool = True,
        controller_factory: Callable[..., Any] | None = None,
        layout_profile: FocusLayoutProfile | None = None,
        companion_enabled: bool = True,
        companion_host: str = DEFAULT_COMPANION_HOST,
        companion_port: int = DEFAULT_COMPANION_PORT,
        companion_advertise_ip: str = "",
    ) -> None:
        self.q = q
        self.package = package
        self.output_root = _package_output_root(package)
        self.capture_options = capture_options or _default_focus_capture_options()
        self.enable_missed_trial_topup = bool(enable_missed_trial_topup)
        self.output_12_volume_percent, self.output_34_volume_percent = _load_output_channel_volume_percentages()
        self.controller_factory = controller_factory
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._ui_thread_id = threading.get_ident()
        self._companion_command_queue: queue.Queue[tuple[Future[dict[str, Any]], Callable[[], dict[str, Any]]]] = queue.Queue()
        self._companion_sequence = 0
        self._companion_snapshot_signature = ""
        self.companion_enabled = bool(companion_enabled)
        self.companion_config = RunnerCompanionConfig(
            host=str(companion_host or DEFAULT_COMPANION_HOST),
            port=int(companion_port or DEFAULT_COMPANION_PORT),
            advertise_ip=str(companion_advertise_ip or choose_lan_ipv4() or ""),
        )
        self.companion_token = generate_companion_token()
        self.companion_service: RunnerCompanionService | None = None
        self.companion_pairing_uri = build_pairing_uri(
            host=self.companion_config.advertised_host,
            port=self.companion_config.port,
            session_id=str(getattr(package, "session_id", "") or ""),
            token=self.companion_token,
        )
        self._validation_companion_pairing_report = os.environ.get(
            "PPS_FOCUS_VALIDATION_COMPANION_PAIRING_REPORT", ""
        ).strip()
        self.companion_qr_png: bytes = b""
        self.companion_tab_index = -1
        self.companion_status_message = "Phone companion is disabled." if not self.companion_enabled else "Phone companion starting."
        if self.companion_enabled:
            try:
                self.companion_qr_png = pairing_qr_png_bytes(self.companion_pairing_uri)
            except Exception as exc:
                self.companion_status_message = f"Phone companion QR unavailable: {exc}"
        self.controller: SessionRunnerController | None = None
        self._continuous_external_labrecorder_state: dict[str, Any] | None = None
        self._owned_audio_engine: Any | None = None
        self.thread: threading.Thread | None = None
        self.result: Any | None = None
        self.exit_code = 1
        self.demographics_submitted = False
        self.pending_instruction_request: dict[str, Any] | None = None
        self.pending_topup_approval_request: dict[str, Any] | None = None
        self._pre_run_controls: list[Any] = []
        self.mode_tabs: Any | None = None
        self.data_logging_tab_index = 0
        self.experiment_control_tab_index = 1
        self._prewarm_thread: threading.Thread | None = None
        self._prewarm_started = False
        self._participant_combo_updating = False
        self.participant_statuses: dict[str, dict[str, Any]] = {}
        self._run_active = False
        self._run_paused = False
        self._experiment_control_ready = False
        self._output_test_active = False
        self._tactile_calibration_active = False
        self._tactile_calibration_worker: threading.Thread | None = None
        self._tactile_calibration_cancel_event: threading.Event | None = None
        self._tactile_calibration_started_global_listener = False
        self._tactile_calibration_collector = _FocusTactileCalibrationCollector()
        self.tactile_calibration_monitor_dialog: Any | None = None
        self._latest_tactile_calibration: dict[str, Any] = {}
        self._timeline_perf_anchor: float | None = None
        self.timeline_state = TactileTimelineState()
        self.timeline_preview_state = TactileTimelineState()
        self.selected_display_block_index: int | None = None
        self.preview_display_block_index: int | None = None
        self.selected_part_key: str | None = None
        self.recenter_records: list[dict[str, Any]] = []
        self._last_recenter_backend_warning = ""
        self.validation_topup_approval_records: list[dict[str, Any]] = []
        self.validation_part_snapshots: list[dict[str, Any]] = []
        self.planned_tactile_cue_count = 0
        self.analysis_review_dialog: AnalysisReviewDialog | None = None
        self.primary_action_shortcuts: list[Any] = []
        self.operator_action_shortcuts: dict[str, list[Any]] = {}
        self._experiment_window_locked = False
        self._experiment_window_lock_restoring = False
        self._experiment_window_locked_geometry: Any | None = None
        self._experiment_window_locked_window_state: Any | None = None
        self._experiment_window_previous_minimum_size: Any | None = None
        self._experiment_window_previous_maximum_size: Any | None = None
        self.all_block_plan_items: list[dict[str, Any]] = []
        self.block_plan_items: list[dict[str, Any]] = []
        self.instruction_plan_items: list[dict[str, Any]] = []
        self.topup_draft_items: list[dict[str, Any]] = []
        self._last_topup_completion: dict[str, Any] = {}
        self.part_buttons: dict[str, Any] = {}
        self.start_part2_button: Any | None = None
        self.active_display_block_index: int | None = None
        self.completed_display_block_indices: set[int] = set()
        self.recenter_controller = TactileRecenterController(self.timeline_state, self._move_cursor_to_target)

        self._workspace_splitter_clamping = False
        self._workspace_splitter_clamp_pending = False
        self.dialog = _create_focus_mode_dialog(q, self)
        _enable_standard_window_controls(q, self.dialog)
        self.dialog.setWindowTitle(f"PPS Experiment Runner - {package.participant_id}")
        self.dialog.setModal(True)
        self.layout_profile = layout_profile or _focus_layout_profile(q)
        self.dialog.resize(self.layout_profile.window_width, self.layout_profile.window_height)
        self.dialog.setMinimumSize(self.layout_profile.min_width, self.layout_profile.min_height)
        self.dialog.setStyleSheet(_focus_style_sheet(q, self.layout_profile))
        _append_output_diary_event(
            "focus_window_opened",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"topup_enabled": self.enable_missed_trial_topup},
            create=True,
        )
        self._response_click_filter_installed = False
        self._global_response_click_listener: Any | None = None
        self._global_response_click_listener_error = ""
        self._global_response_click_listener_lock = threading.Lock()
        self._target_global_bounds_lock = threading.Lock()
        self._target_global_bounds: tuple[int, int, int, int] | None = None
        self._response_click_record_lock = threading.Lock()
        self._last_response_click_signature: tuple[
            tuple[int | None, int | None, bool],
            float,
        ] | None = None
        self._build()
        self._install_response_click_filter()

    def _build(self) -> None:
        q = self.q
        profile = self.layout_profile
        root = q["QVBoxLayout"](self.dialog)
        root.setContentsMargins(profile.root_margin, profile.root_margin, profile.root_margin, profile.root_margin)
        root.setSpacing(profile.root_spacing)

        topbar = q["QFrame"]()
        topbar.setObjectName("topbar")
        topbar_layout = q["QHBoxLayout"](topbar)
        topbar_layout.setContentsMargins(profile.panel_margin, 8, profile.panel_margin, 8)
        topbar_layout.setSpacing(profile.grid_spacing)

        brand = q["QVBoxLayout"]()
        title = q["QLabel"]("PPS Experiment Runner")
        title.setObjectName("appTitle")
        subtitle = q["QLabel"]("Native Focus Mode")
        subtitle.setObjectName("mutedLabel")
        brand.addWidget(title)

        self.run_state_chip = _chip(q, "Ready", tone="ok")
        self.part_chip = _chip(q, "Part -", tone="neutral")
        initial_block_count = _run_plan_total(self.package, include_topup_slots=self.enable_missed_trial_topup)
        self.block_chip = _chip(q, f"Block -/{initial_block_count}", tone="neutral")
        participant_label = (
            f"ID {self.package.participant_id}" if profile.compact else f"Participant {self.package.participant_id}"
        )
        self.participant_chip = _chip(q, participant_label, tone="neutral")
        self.participant_chip.setToolTip(f"Participant {self.package.participant_id}")

        chip_row = q["QWidget"]()
        chip_row_layout = q["QHBoxLayout"](chip_row)
        chip_row_layout.setContentsMargins(0, 0, 0, 0)
        chip_row_layout.setSpacing(6)
        chip_row_layout.addWidget(subtitle)
        chip_row_layout.addWidget(self.participant_chip)
        chip_row_layout.addWidget(self.part_chip)
        chip_row_layout.addWidget(self.block_chip)
        chip_row_layout.addWidget(self.run_state_chip)
        chip_row_layout.addStretch(1)
        brand.addWidget(chip_row)
        topbar_layout.addLayout(brand, 1)
        root.addWidget(topbar)

        self.mode_tabs = q["QTabWidget"]()
        self.mode_tabs.setObjectName("focusModeTabs")
        self.mode_tabs.setDocumentMode(True)
        root.addWidget(self.mode_tabs, 1)

        self.experiment_control_tab = q["QWidget"]()
        self.experiment_control_tab.setObjectName("experimentControlTab")
        experiment_control_tab_layout = q["QVBoxLayout"](self.experiment_control_tab)
        experiment_control_tab_layout.setContentsMargins(0, 0, 0, 0)
        experiment_control_tab_layout.setSpacing(0)

        self.workspace_splitter = q["QSplitter"](q["Qt"].Orientation.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(max(7, profile.root_spacing))
        self.workspace_splitter.splitterMoved.connect(
            lambda _pos, _index: self._clamp_workspace_splitter_for_experiment_control()
        )
        experiment_control_tab_layout.addWidget(self.workspace_splitter, 1)

        self.run_splitter = q["QSplitter"](q["Qt"].Orientation.Horizontal)
        self.run_splitter.setChildrenCollapsible(False)
        self.run_splitter.setHandleWidth(max(7, profile.root_spacing))
        self.workspace_splitter.addWidget(self.run_splitter)

        response_cell = q["QWidget"]()
        response_cell_layout = q["QVBoxLayout"](response_cell)
        response_cell_layout.setContentsMargins(0, 0, 0, 0)
        response_cell_layout.setSpacing(max(6, profile.root_spacing))
        response_cell.setMinimumWidth(profile.response_panel_side)
        response_cell.setMinimumHeight(profile.response_panel_side)
        response_cell.setSizePolicy(q["QSizePolicy"].Policy.Minimum, q["QSizePolicy"].Policy.Expanding)
        self.response_cell = response_cell

        response_panel, response_layout = _panel(q, "Experiment Running", profile=profile)
        self.response_panel = response_panel
        response_panel.setFixedSize(profile.response_panel_side, profile.response_panel_side)
        response_panel.setSizePolicy(q["QSizePolicy"].Policy.Fixed, q["QSizePolicy"].Policy.Fixed)
        compact_response_margin = max(8, profile.panel_margin - 2)
        response_layout.setContentsMargins(
            compact_response_margin,
            compact_response_margin,
            compact_response_margin,
            compact_response_margin,
        )
        response_layout.setSpacing(max(5, profile.panel_spacing - 1))
        response_layout.addWidget(_subtitle(q, "Participant Response"))
        self.target_button = _create_response_target_button(q, profile)
        self.target_button.setEnabled(False)
        self.target_button.clicked.connect(self._click)
        response_layout.addWidget(self.target_button, 0, q["Qt"].AlignmentFlag.AlignHCenter)
        response_layout.addStretch(1)
        self.instruction_button = q["QPushButton"]("Continue")
        self.instruction_button.setObjectName("primaryButton")
        self.instruction_button.setVisible(False)
        self.instruction_button.clicked.connect(self._continue_instruction_button)

        self.start_button = q["QPushButton"]("Start Run")
        self.start_button.setObjectName("startButton")
        self.start_button.setEnabled(False)
        self.pause_button = q["QPushButton"]("Pause")
        self.resume_button = q["QPushButton"]("Resume")
        self.stop_button = q["QPushButton"]("Stop", self.dialog)
        self.stop_button.setObjectName("dangerButton")
        self.stop_button.setVisible(False)
        self.close_button = q["QPushButton"]("Close", self.dialog)
        self.close_button.setVisible(False)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        for button in (self.start_button, self.pause_button, self.resume_button, self.stop_button, self.close_button):
            button.setAutoDefault(False)
            button.setDefault(False)
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self._pause)
        self.resume_button.clicked.connect(self._resume)
        self.stop_button.clicked.connect(self._stop)
        self.close_button.clicked.connect(self._close)
        self._install_primary_action_shortcuts()
        response_cell_layout.addWidget(response_panel, 0, q["Qt"].AlignmentFlag.AlignTop | q["Qt"].AlignmentFlag.AlignHCenter)

        output_levels_panel, output_levels_layout = _panel(q, "Output Levels", profile=profile)
        self.output_levels_panel = output_levels_panel
        output_levels_panel.setMinimumWidth(profile.response_panel_side)
        output_levels_panel.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Fixed)
        output_levels_heading_height = max(16, profile.input_min_height - 8)
        output_test_button_min_height = profile.button_min_height + 4
        output_test_spacing = max(10, profile.panel_spacing)
        output_test_stack_min_height = (output_test_button_min_height * 2) + output_test_spacing
        output_levels_panel_min_height = max(
            150,
            output_levels_heading_height
            + (profile.input_min_height * 2)
            + output_test_stack_min_height
            + (profile.panel_margin * 2)
            + (profile.panel_spacing * 3),
        )
        output_levels_panel.setMinimumHeight(output_levels_panel_min_height)
        output_levels_panel.setMaximumHeight(output_levels_panel_min_height)
        (
            output_12_row,
            self.output_12_volume_slider,
            self.output_12_volume_percent_box,
        ) = _output_volume_slider_row(
            q,
            label="Output 1/2",
            value=self.output_12_volume_percent,
            object_name="output12VolumeSlider",
            tooltip="Linear gain for the Komplete output 1/2 auditory headphone pair.",
            on_change=lambda value: self._set_output_volume("output_1_2", value),
        )
        (
            output_34_row,
            self.output_34_volume_slider,
            self.output_34_volume_percent_box,
        ) = _output_volume_slider_row(
            q,
            label="Output 3/4",
            value=self.output_34_volume_percent,
            object_name="output34VolumeSlider",
            tooltip="Linear gain for tactile output 3 and its output 4 mirror. Capped at 0.5% for participant comfort.",
            on_change=lambda value: self._set_output_volume("output_3_4", value),
            maximum_percent=TACTILE_OUTPUT_34_MAX_PERCENT,
        )
        output_levels_layout.addWidget(output_12_row)
        output_levels_layout.addWidget(output_34_row)
        output_test_controls = q["QGridLayout"]()
        output_test_controls.setContentsMargins(0, 0, 0, 0)
        output_test_controls.setHorizontalSpacing(6)
        output_test_controls.setVerticalSpacing(output_test_spacing)
        self.test_audio_button = q["QPushButton"]("Test Audio")
        self.test_audio_button.setObjectName("testAudioOutputButton")
        self.test_audio_button.setMinimumHeight(output_test_button_min_height)
        self.test_audio_button.setToolTip("Play one Study 5 pink frontal looming burst-train stimulus through Komplete outputs 1/2 using the current Output 1/2 level.")
        self.test_audio_button.clicked.connect(lambda _checked=False: self._run_output_test("audio"))
        self.test_tactile_button = q["QPushButton"]("Test Tactile")
        self.test_tactile_button.setObjectName("testTactileOutputButton")
        self.test_tactile_button.setMinimumHeight(output_test_button_min_height)
        self.test_tactile_button.setToolTip("Play four standardized tactile pulses one second apart through output 3, mirrored to output 4, using the capped current Output 3/4 level.")
        self.test_tactile_button.clicked.connect(lambda _checked=False: self._run_output_test("tactile"))
        self.tactile_calibration_button = q["QPushButton"]("Tactile Threshold")
        self.tactile_calibration_button.setObjectName("tactileCalibrationButton")
        self.tactile_calibration_button.setMinimumHeight(output_test_button_min_height)
        self.tactile_calibration_button.setToolTip(
            "Run the participant-specific 2-down/1-up tactile threshold staircase. Verbally instruct the participant to press the mouse whenever a tactile pulse is felt."
        )
        self.tactile_calibration_button.clicked.connect(lambda _checked=False: self._run_tactile_calibration())
        output_test_controls.setColumnStretch(0, 1)
        output_test_controls.setColumnStretch(1, 1)
        output_test_controls.setRowMinimumHeight(0, output_test_button_min_height)
        output_test_controls.setRowMinimumHeight(1, output_test_button_min_height)
        output_test_controls.addWidget(self.test_audio_button, 0, 0)
        output_test_controls.addWidget(self.test_tactile_button, 0, 1)
        output_test_controls.addWidget(self.tactile_calibration_button, 1, 0, 1, 2)
        output_levels_layout.addLayout(output_test_controls)
        self._pre_run_controls.append(self.tactile_calibration_button)

        output_panel, output_layout = _panel(q, "Output Summary", profile=profile)
        self.output_panel = output_panel
        output_title_min_height = max(16, profile.input_min_height - 8)
        output_panel_min_height = (
            profile.output_min_height
            + output_title_min_height
            + profile.panel_spacing
            + (profile.panel_margin * 2)
        )
        output_panel_max_height = max(profile.output_max_height + (profile.panel_margin * 2), output_panel_min_height)
        output_panel.setMinimumHeight(output_panel_min_height)
        output_panel.setMaximumHeight(output_panel_max_height)
        output_panel.setMinimumWidth(profile.response_panel_side)
        output_layout.setSpacing(profile.panel_spacing)
        self.output_summary = q["QTextEdit"]()
        self.output_summary.setReadOnly(True)
        self.output_summary.setMinimumHeight(profile.output_min_height)
        self.output_summary.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        self.output_summary.setPlainText("Session outputs will appear here after the run.")
        output_layout.addWidget(self.output_summary)
        show_output_summary_panel = profile.screen_class not in {"constrained", "compact"}
        output_panel.setVisible(show_output_summary_panel)
        output_stack_cell = q["QWidget"]()
        output_stack_cell.setObjectName("outputStackCell")
        output_stack_layout = q["QVBoxLayout"](output_stack_cell)
        output_stack_layout.setContentsMargins(0, 0, 0, 0)
        output_stack_layout.setSpacing(max(6, profile.root_spacing))
        output_stack_cell.setMinimumWidth(300 if profile.compact else 360)
        output_stack_cell.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        output_stack_layout.addWidget(output_levels_panel)
        output_stack_layout.addWidget(output_panel)
        output_stack_layout.addStretch(1)
        self.output_stack_cell = output_stack_cell
        output_stack_parts = [output_levels_panel_min_height]
        if show_output_summary_panel:
            output_stack_parts.append(output_panel_min_height)
        output_stack_height = sum(output_stack_parts) + (max(6, profile.root_spacing) * max(0, len(output_stack_parts) - 1))
        response_stack_height = max(profile.response_panel_side, output_stack_height)
        self.response_stack_height = response_stack_height
        response_cell.setMinimumHeight(profile.response_panel_side)
        response_cell_layout.addStretch(1)
        self.run_splitter.addWidget(response_cell)
        self.run_splitter.addWidget(output_stack_cell)

        self.operator_splitter = None
        self.operator_tabs = None
        settings_title = "Data Logging / Experiment Settings"
        data_panel, data_layout = _panel(q, settings_title, profile=profile)
        self.data_selection_panel = data_panel
        self.settings_panel = data_panel
        data_panel.setMinimumWidth(380 if profile.compact else 460)
        data_panel.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        data_panel_min_height = 248 if profile.screen_class == "constrained" else max(290, profile.response_panel_side)
        data_panel.setMinimumHeight(data_panel_min_height)
        data_two_column = profile.screen_class != "constrained" or profile.available_width >= 1000
        self.data_settings_columns_mode = "two_column" if data_two_column else "stacked"
        self.data_columns_widget = q["QWidget"]()
        self.data_columns_widget.setObjectName("dataSettingsColumns")
        data_columns_layout = (q["QHBoxLayout"] if data_two_column else q["QVBoxLayout"])(self.data_columns_widget)
        data_columns_layout.setContentsMargins(0, 0, 0, 0)
        data_columns_layout.setSpacing(max(10, profile.grid_spacing + 4))
        self.data_logging_column = q["QWidget"]()
        self.data_logging_column.setObjectName("dataLoggingColumn")
        self.experiment_settings_column = q["QWidget"]()
        self.experiment_settings_column.setObjectName("experimentSettingsColumn")
        data_logging_layout = q["QVBoxLayout"](self.data_logging_column)
        data_logging_layout.setContentsMargins(0, 0, 0, 0)
        data_logging_layout.setSpacing(profile.panel_spacing)
        experiment_settings_layout = q["QVBoxLayout"](self.experiment_settings_column)
        experiment_settings_layout.setContentsMargins(0, 0, 0, 0)
        experiment_settings_layout.setSpacing(profile.panel_spacing)
        if data_two_column:
            self.data_logging_column.setMinimumWidth(280 if profile.compact else 330)
            self.experiment_settings_column.setMinimumWidth(280 if profile.compact else 330)
        data_columns_layout.addWidget(self.data_logging_column, 1)
        data_columns_layout.addWidget(self.experiment_settings_column, 1)
        data_layout.addWidget(self.data_columns_widget)

        data_logging_layout.addWidget(_subtitle(q, "Participant Setup"))
        self.participant_selector_widget = q["QWidget"]()
        self.participant_selector_widget.setObjectName("runnerParticipantStepper")
        participant_selector_layout = q["QHBoxLayout"](self.participant_selector_widget)
        participant_selector_layout.setContentsMargins(0, 0, 0, 0)
        participant_selector_layout.setSpacing(6)
        self.participant_code_combo = q["QComboBox"]()
        self.participant_code_combo.setObjectName("runnerParticipantCombo")
        self.participant_code_combo.setEditable(False)
        self.participant_code_combo.setToolTip("Select a prepared participant profile from the run setup.")
        participant_selector_layout.addWidget(self.participant_code_combo, 1)
        participant_arrow_column = q["QWidget"]()
        participant_arrow_layout = q["QVBoxLayout"](participant_arrow_column)
        participant_arrow_layout.setContentsMargins(0, 0, 0, 0)
        participant_arrow_layout.setSpacing(2)
        self.participant_increment_button = q["QToolButton"]()
        self.participant_increment_button.setObjectName("participantIncrementButton")
        self.participant_increment_button.setArrowType(q["Qt"].ArrowType.UpArrow)
        self.participant_increment_button.setToolTip("Next participant")
        self.participant_decrement_button = q["QToolButton"]()
        self.participant_decrement_button.setObjectName("participantDecrementButton")
        self.participant_decrement_button.setArrowType(q["Qt"].ArrowType.DownArrow)
        self.participant_decrement_button.setToolTip("Previous participant")
        for button in (self.participant_increment_button, self.participant_decrement_button):
            button.setAutoRaise(True)
            button.setMinimumWidth(max(24, profile.input_min_height - 6))
            button.setMinimumHeight(max(14, profile.input_min_height // 2 - 2))
        participant_arrow_layout.addWidget(self.participant_increment_button)
        participant_arrow_layout.addWidget(self.participant_decrement_button)
        participant_selector_layout.addWidget(participant_arrow_column)
        self._populate_participant_code_combo(self.package.participant_id)
        self.participant_code_combo.currentIndexChanged.connect(self._participant_selection_changed)
        self.participant_increment_button.clicked.connect(lambda _checked=False: self._step_participant_selection(1))
        self.participant_decrement_button.clicked.connect(lambda _checked=False: self._step_participant_selection(-1))
        self.participant_name_input = q["QLineEdit"]("")
        self.participant_name_input.setPlaceholderText("Participant name")
        self.include_name_lsl_checkbox = q["QCheckBox"]("Include name in LSL/session markers (opt-in)")
        self.include_name_lsl_checkbox.setObjectName("nameSharingCheckbox")
        self.include_name_lsl_checkbox.setToolTip("Opt in only when the participant's real name may be stored in local session metadata and LSL markers.")
        self.include_name_lsl_checkbox.setMinimumHeight(max(profile.button_min_height + 8, profile.input_min_height + 12))
        self.include_name_lsl_checkbox.setChecked(False)
        self.age_input = q["QLineEdit"]("")
        self.age_input.setPlaceholderText("Age")
        self.handedness_combo = _combo(
            q,
            [
                ("", "Select handedness"),
                ("right", "Right"),
                ("left", "Left"),
                ("ambidextrous", "Ambidextrous"),
                ("prefer_not_to_say", "Prefer not to say"),
            ],
        )
        self.gender_combo = _combo(
            q,
            [
                ("", "Select gender"),
                ("male", "Male"),
                ("female", "Female"),
                ("other", "Other"),
                ("prefer_not_to_say", "Prefer not to say"),
            ],
        )
        setup_fields = q["QGridLayout"]()
        setup_fields.setContentsMargins(0, 0, 0, 0)
        setup_fields.setHorizontalSpacing(8)
        setup_fields.setVerticalSpacing(6)

        def _add_setup_field(row: int, label: str, widget: Any) -> None:
            key = q["QLabel"](label)
            key.setObjectName("metricLabel")
            key.setMinimumHeight(max(16, profile.input_min_height - 8))
            if hasattr(widget, "setMinimumHeight"):
                widget.setMinimumHeight(profile.input_min_height)
            setup_fields.addWidget(key, row, 0)
            setup_fields.addWidget(widget, row, 1)

        _add_setup_field(0, "Participant", self.participant_selector_widget)
        _add_setup_field(1, "Name", self.participant_name_input)
        _add_setup_field(2, "Age", self.age_input)
        _add_setup_field(3, "Handedness", self.handedness_combo)
        _add_setup_field(4, "Gender", self.gender_combo)
        setup_fields.setColumnStretch(1, 1)
        data_logging_layout.addLayout(setup_fields)
        self.participant_status_summary_label = q["QLabel"]("")
        self.participant_status_summary_label.setObjectName("participantLedgerSummary")
        self.participant_status_summary_label.setWordWrap(True)
        self.participant_status_summary_label.setMinimumHeight(max(18, profile.input_min_height - 4))
        data_logging_layout.addWidget(self.participant_status_summary_label)
        data_logging_layout.addWidget(self.include_name_lsl_checkbox)
        self.setup_submit_button = q["QPushButton"]("Submit setup")
        self.setup_submit_button.setObjectName("participantSetupSubmitButton")
        self.setup_submit_button.setToolTip("Submit participant setup and create the session LSL marker streams.")
        self.setup_submit_button.setMinimumHeight(profile.button_min_height)
        self.setup_submit_button.clicked.connect(self._submit_participant_setup)
        data_logging_layout.addWidget(self.setup_submit_button)
        self.setup_status_label = q["QLabel"]("Submit setup to unlock start controls.")
        self.setup_status_label.setObjectName("mutedLabel")
        self.setup_status_label.setWordWrap(True)
        data_logging_layout.addWidget(self.setup_status_label)

        self._pre_run_controls.extend(
            [
                self.participant_code_combo,
                self.participant_selector_widget,
                self.participant_increment_button,
                self.participant_decrement_button,
                self.participant_name_input,
                self.include_name_lsl_checkbox,
                self.age_input,
                self.handedness_combo,
                self.gender_combo,
                self.setup_submit_button,
            ]
        )

        data_logging_layout.addWidget(_subtitle(q, "Data Logging"))
        self.backup_recording_checkbox = q["QCheckBox"](_backup_recording_checkbox_text(self.package))
        self.backup_recording_checkbox.setObjectName("failSafeRecordingCheckbox")
        self.backup_recording_checkbox.setToolTip(
            "LSL/event logging remains standard. This adds per-block fail-safe local recording WAVs on this computer."
        )
        self.backup_recording_checkbox.setMinimumHeight(max(profile.button_min_height + 18, profile.input_min_height + 22))
        self.backup_recording_checkbox.setChecked(bool(self.capture_options.start_backup_recording))
        data_logging_layout.addWidget(self.backup_recording_checkbox)
        self.wired_loopback_checkbox = q["QCheckBox"](_wired_loopback_checkbox_text())
        self.wired_loopback_checkbox.setObjectName("wiredLoopbackCheckbox")
        self.wired_loopback_checkbox.setToolTip(
            "Output 4 already mirrors tactile output 3 on 4-channel routes. "
            "This records input 4 as an analog duplicate proxy, not Woojer mechanical vibration onset."
        )
        self.wired_loopback_checkbox.setMinimumHeight(max(profile.button_min_height + 18, profile.input_min_height + 22))
        self.wired_loopback_checkbox.setChecked(
            normalize_wired_loopback_mode(self.capture_options.wired_loopback_mode)
            == WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY
        )
        data_logging_layout.addWidget(self.wired_loopback_checkbox)
        self.external_labrecorder_checkbox = q["QCheckBox"](_external_labrecorder_checkbox_text())
        self.external_labrecorder_checkbox.setObjectName("externalLabRecorderCheckbox")
        self.external_labrecorder_checkbox.setToolTip(
            "Starts LabRecorder through its remote-control socket as a child process owned by the runner. "
            "Playback waits until PPSMarkersV2 and PPSTriggerCodes are discoverable and LabRecorder is running."
        )
        self.external_labrecorder_checkbox.setMinimumHeight(max(profile.button_min_height + 18, profile.input_min_height + 22))
        self.external_labrecorder_checkbox.setChecked(
            bool(self.capture_options.enable_lsl and self.capture_options.start_external_labrecorder)
        )
        self.external_labrecorder_checkbox.setEnabled(bool(self.capture_options.enable_lsl))
        data_logging_layout.addWidget(self.external_labrecorder_checkbox)
        self._pre_run_controls.append(self.external_labrecorder_checkbox)
        data_logging_layout.addStretch(1)

        experiment_settings_layout.addWidget(_subtitle(q, "Session"))
        session_grid = q["QGridLayout"]()
        session_grid.setContentsMargins(0, 0, 0, 0)
        session_grid.setHorizontalSpacing(10)
        session_grid.setVerticalSpacing(4)

        def _add_session_metric(row: int, label: str, value: str) -> Any:
            key = q["QLabel"](label)
            key.setObjectName("metricLabel")
            key.setMinimumHeight(max(16, profile.input_min_height - 8))
            val = q["QLabel"](value)
            val.setObjectName("metricValue")
            val.setWordWrap(True)
            val.setMinimumHeight(max(16, profile.input_min_height - 8))
            session_grid.addWidget(key, row, 0)
            session_grid.addWidget(val, row, 1)
            return val

        self.session_participant_value = _add_session_metric(0, "Participant", self.package.participant_id)
        self.session_blocks_value = _add_session_metric(1, "Blocks", str(len(self.package.blocks)))
        instruction_summary = _instruction_profile_summary(self.package)
        if profile.compact:
            instruction_summary = instruction_summary.replace(" clip(s) preloaded", " clips")
        self.session_duration_value = _add_session_metric(2, "Duration", _format_duration(_package_duration(self.package)))
        self.session_instruction_value = _add_session_metric(3, "Instruction clips", instruction_summary)
        self.session_value = _add_session_metric(4, "Session", self.package.session_id)
        self.session_value.setToolTip(f"Session: {self.package.session_id}\nFolder: {self.package.session_dir}")
        self.folder_value = None
        if not profile.compact:
            self.folder_value = _add_session_metric(5, "Folder", _short_folder_label(self.package.session_dir))
            self.folder_value.setToolTip(str(self.package.session_dir))
            run_plan_row = 6
        else:
            run_plan_row = 5
        self.run_plan_value = _add_session_metric(run_plan_row, "Run plan", "")
        session_grid.setColumnStretch(1, 1)
        experiment_settings_layout.addLayout(session_grid)
        experiment_settings_layout.addWidget(_subtitle(q, "Experiment Settings"))
        self.topup_checkbox = q["QCheckBox"]("Top up missed tactile trials at part end")
        self.topup_checkbox.setToolTip("Top up missed tactile trials at end of each part")
        self.topup_checkbox.setMinimumHeight(profile.input_min_height)
        self.topup_checkbox.setChecked(bool(self.enable_missed_trial_topup))
        self.topup_checkbox.stateChanged.connect(lambda _state: self._refresh_run_plan(select_default=True))
        experiment_settings_layout.addWidget(self.topup_checkbox)
        experiment_settings_layout.addWidget(_subtitle(q, "Instruction Map"))
        self.instruction_legend_widget = _create_instruction_legend_widget(q, self)
        experiment_settings_layout.addWidget(self.instruction_legend_widget)
        experiment_settings_layout.addStretch(1)
        self._pre_run_controls.extend([self.backup_recording_checkbox, self.wired_loopback_checkbox, self.topup_checkbox])
        data_layout.addStretch(1)
        self.data_logging_tab_index = self.mode_tabs.addTab(data_panel, "Data Logging")

        companion_panel, companion_layout = _panel(q, "Companion Android App (Experimental)", profile=profile)
        self.companion_panel = companion_panel
        companion_layout.setSpacing(max(10, profile.panel_spacing))
        self.companion_status_label = q["QLabel"](self.companion_status_message)
        self.companion_status_label.setObjectName("mutedLabel")
        self.companion_status_label.setWordWrap(True)
        companion_layout.addWidget(self.companion_status_label)
        self.companion_qr_label = q["QLabel"]("")
        self.companion_qr_label.setObjectName("companionQrCode")
        self.companion_qr_label.setFixedSize(320, 320)
        self.companion_qr_label.setAlignment(q["Qt"].AlignmentFlag.AlignCenter)
        companion_layout.addWidget(self.companion_qr_label, 0, q["Qt"].AlignmentFlag.AlignHCenter)
        self.companion_endpoint_label = q["QLabel"]("")
        self.companion_endpoint_label.setObjectName("metricValue")
        self.companion_endpoint_label.setWordWrap(True)
        companion_layout.addWidget(self.companion_endpoint_label)
        self.companion_uri_field = q["QLineEdit"]("")
        self.companion_uri_field.setObjectName("companionPairingUriField")
        self.companion_uri_field.setReadOnly(True)
        self.companion_uri_field.setToolTip("Pairing URI encoded in the QR code.")
        companion_layout.addWidget(self.companion_uri_field)
        companion_layout.addStretch(1)
        self.companion_tab_index = self.mode_tabs.addTab(companion_panel, "Companion Android App (Experimental)")
        self._refresh_companion_panel()

        self.processing_splitter = None

        processing_panel, progress_layout = _panel(q, "Experiment Control", profile=profile)
        self.processing_panel = processing_panel
        processing_panel_min_height = max(
            profile.experiment_control_min_height,
            profile.experiment_control_content_min_height,
        )
        processing_panel.setMinimumHeight(processing_panel_min_height)
        processing_panel.setMinimumWidth(360 if profile.compact else 420)
        processing_panel.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Minimum)
        progress_layout.setSpacing(profile.panel_spacing)
        show_lower_detail_text = profile.screen_class == "spacious" and profile.available_height >= 1300
        show_lower_headings = (not profile.compact) and profile.available_height >= 1100
        self.run_controls_widget = q["QWidget"]()
        self.run_controls_widget.setObjectName("experimentRunControls")
        run_controls_layout = q["QHBoxLayout"](self.run_controls_widget)
        run_controls_layout.setContentsMargins(0, 0, 0, 0)
        run_controls_layout.setSpacing(6)
        run_controls_layout.addWidget(self.start_button)
        run_controls_layout.addWidget(self.pause_button)
        run_controls_layout.addWidget(self.resume_button)
        run_controls_layout.addWidget(self.instruction_button)
        run_controls_layout.addStretch(1)
        progress_layout.addWidget(self.run_controls_widget)
        if show_lower_headings:
            progress_layout.addWidget(_subtitle(q, "Block Order"))
        self.part_selector_widget = q["QWidget"]()
        part_selector_layout = q["QHBoxLayout"](self.part_selector_widget)
        part_selector_layout.setContentsMargins(0, 0, 0, 0)
        part_selector_layout.setSpacing(6)
        part_selector_layout.addWidget(_subtitle(q, "Part"))
        for part_key in ("1", "2"):
            button = q["QPushButton"](_part_button_label(part_key))
            button.setObjectName(f"part{part_key}Button")
            button.setCheckable(True)
            button.setMinimumHeight(profile.button_min_height)
            button.clicked.connect(lambda _checked=False, key=part_key: self._select_part_key(key, preview_first=True))
            self.part_buttons[part_key] = button
            part_selector_layout.addWidget(button)
        self.start_part2_button = q["QPushButton"]("Start Part 02")
        self.start_part2_button.setObjectName("startPart2Button")
        self.start_part2_button.setMinimumHeight(profile.button_min_height)
        self.start_part2_button.setEnabled(False)
        self.start_part2_button.setToolTip("Part 02 can be started only after Part 01 has finished and the runner is waiting at the part boundary.")
        self.start_part2_button.clicked.connect(self._start_part2_button_clicked)
        part_selector_layout.addWidget(self.start_part2_button)
        part_selector_layout.addStretch(1)
        progress_layout.addWidget(self.part_selector_widget)
        self.block_plan_widget = _create_block_plan_widget(q, self)
        progress_layout.addWidget(self.block_plan_widget)
        self.block_preview_label = q["QLabel"]("Block preview: live schedule")
        self.block_preview_label.setObjectName("mutedLabel")
        self.block_preview_label.setWordWrap(False)
        progress_layout.addWidget(self.block_preview_label)
        if not show_lower_detail_text:
            self.block_preview_label.setVisible(False)
        self.topup_draft_widget = _create_topup_draft_widget(q, self)
        progress_layout.addWidget(self.topup_draft_widget)
        if show_lower_headings:
            progress_layout.addWidget(_subtitle(q, "Stimulus / Tactile / Click Timeline"))
        timeline_status = q["QWidget"]()
        self.timeline_status_widget = timeline_status
        timeline_status.setMinimumHeight(max(profile.button_min_height, profile.input_min_height + 4))
        timeline_status_layout = q["QHBoxLayout"](timeline_status)
        timeline_status_layout.setContentsMargins(0, 0, 0, 0)
        timeline_status_layout.setSpacing(8)
        self.next_tactile_label = q["QLabel"]("Next tactile: no block schedule")
        self.next_tactile_label.setObjectName("metricValue")
        self.next_tactile_label.setWordWrap(False)
        self.tactile_count_label = q["QLabel"]("0 / 0 cues")
        self.tactile_count_label.setObjectName("mutedLabel")
        self.tactile_count_label.setWordWrap(False)
        timeline_status_layout.addWidget(self.next_tactile_label, 1)
        timeline_status_layout.addWidget(self.tactile_count_label)
        progress_layout.addWidget(timeline_status)
        self.tactile_timeline_widget = _create_tactile_timeline_widget(
            q,
            self.timeline_state,
            profile,
            state_provider=self._timeline_display_state,
        )
        progress_layout.addWidget(self.tactile_timeline_widget)
        self.recenter_status_label = q["QLabel"]("Cursor recenter: waiting")
        self.recenter_status_label.setObjectName("mutedLabel")
        self.recenter_status_label.setWordWrap(False)
        progress_layout.addWidget(self.recenter_status_label)
        if not show_lower_detail_text:
            self.recenter_status_label.setVisible(False)
        if show_lower_detail_text:
            progress_layout.addWidget(_subtitle(q, "Progress"))
        self.progress_label = q["QLabel"]("Waiting to start")
        self.progress_label.setObjectName("metricValue")
        self.progress_label.setWordWrap(False)
        progress_layout.addWidget(self.progress_label)
        if not show_lower_detail_text:
            self.progress_label.setVisible(False)
        self.progress = q["QProgressBar"]()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress_track_widget = q["QWidget"]()
        self.progress_track_widget.setMinimumHeight(profile.progress_min_height + 5)
        progress_track_layout = q["QHBoxLayout"](self.progress_track_widget)
        progress_track_layout.setContentsMargins(TIMELINE_LABEL_WIDTH, 0, TIMELINE_RIGHT_MARGIN, 0)
        progress_track_layout.setSpacing(0)
        progress_track_layout.addWidget(self.progress)
        progress_layout.addWidget(self.progress_track_widget)
        if profile.screen_class == "constrained":
            self.progress_label.setVisible(False)
            self.progress_track_widget.setVisible(False)
        self.event_label = q["QLabel"]("Event stream idle")
        self.event_label.setObjectName("mutedLabel")
        self.event_label.setWordWrap(False)
        progress_layout.addWidget(self.event_label)
        self.prewarm_label = q["QLabel"]("Next participant: idle")
        self.prewarm_label.setObjectName("mutedLabel")
        self.prewarm_label.setWordWrap(False)
        progress_layout.addWidget(self.prewarm_label)
        if not show_lower_detail_text:
            self.event_label.setVisible(False)
            self.prewarm_label.setVisible(False)
        if profile.screen_class == "constrained":
            self.progress_track_widget.setVisible(False)
        progress_layout.addStretch(1)
        self.workspace_splitter.addWidget(processing_panel)
        self.experiment_control_tab_index = self.mode_tabs.addTab(self.experiment_control_tab, "Experiment Control")
        self.mode_tabs.setTabEnabled(self.experiment_control_tab_index, True)
        self.mode_tabs.setCurrentIndex(self.data_logging_tab_index)

        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.run_splitter.setStretchFactor(0, 0)
        if self.run_splitter.count() > 1:
            self.run_splitter.setStretchFactor(1, 1)

        response_column_width = profile.response_panel_side + max(12, profile.root_spacing)
        if self.run_splitter.count() > 1:
            remaining_width = max(360, profile.window_width - response_column_width)
            self.run_splitter.setSizes([response_column_width, remaining_width])
        else:
            self.run_splitter.setSizes([max(response_column_width, profile.window_width - (profile.root_margin * 2))])
        top_height = response_stack_height
        self._refresh_experiment_control_minimum_height()
        self.workspace_splitter.setSizes([top_height, profile.experiment_control_initial_height])
        self._clamp_workspace_splitter_for_experiment_control()

        self.timer = q["QTimer"](self.dialog)
        self.timer.timeout.connect(self._drain)
        self.timer.start(100)
        self.dialog.finished.connect(self._handle_dialog_finished)
        self._refresh_run_plan(select_default=True)
        self._install_operator_action_shortcuts()
        self._apply_participant_ledger_to_fields(self.package.participant_id)
        self._apply_latest_tactile_calibration(self.package.participant_id, show_message=False)
        self._refresh_participant_ledger_summary()
        self._set_experiment_control_tab_ready(False)

    def _set_experiment_control_tab_ready(self, ready: bool, *, switch: bool = False) -> None:
        tabs = getattr(self, "mode_tabs", None)
        if tabs is None:
            return
        index = int(getattr(self, "experiment_control_tab_index", 1))
        if 0 <= index < tabs.count():
            tabs.setTabEnabled(index, True)
            self._experiment_control_ready = bool(ready)
            self._set_output_level_controls_enabled(bool(ready))
            if getattr(self, "part_buttons", None):
                self._refresh_part_controls()
            if ready and switch:
                tabs.setCurrentIndex(index)

    def _set_setup_status_message(self, message: str) -> None:
        label = getattr(self, "setup_status_label", None)
        if label is not None:
            label.setText(str(message or ""))

    def _tactile_calibration_allowed(self) -> bool:
        thread_alive = bool(self.thread is not None and self.thread.is_alive())
        setup_state_safe = (
            (not self.demographics_submitted and self.controller is None)
            or (self.demographics_submitted and self.controller is not None)
        )
        return bool(
            getattr(self, "tactile_calibration_button", None) is not None
            and setup_state_safe
            and not self._run_active
            and not thread_alive
            and not self._output_test_active
            and not self._tactile_calibration_active
            and bool(str(getattr(self.package, "participant_id", "") or "").strip())
        )

    def _set_tactile_calibration_button_enabled(self) -> None:
        button = getattr(self, "tactile_calibration_button", None)
        if button is not None:
            button.setEnabled(self._tactile_calibration_allowed())

    def _current_tactile_calibration_metadata(self) -> dict[str, Any]:
        selected = self._selected_participant_code() or str(getattr(self.package, "participant_id", "") or "")
        current = dict(self._latest_tactile_calibration or {})
        if str(current.get("participant_id") or "") != str(selected):
            loaded = load_latest_calibration(self.output_root, selected)
            current = dict(loaded or {})
        if not current:
            return {}
        keys = {
            "schema",
            "participant_id",
            "accepted",
            "status",
            "created_at",
            "protocol",
            "threshold_method",
            "threshold_definition",
            "final_output_34_percent",
            "detection_threshold_output_34_percent",
            "recommended_output_34_percent",
            "confirmation_level_output_34_percent",
            "staircase_target_detection_rate",
            "staircase_reversals",
            "staircase_reversal_levels_percent",
            "staircase_reversal_levels_used_percent",
            "staircase_signal_trials",
            "staircase_hits",
            "staircase_misses",
            "staircase_hit_rate",
            "staircase_false_alarm_rate",
            "staircase_catch_trials",
            "staircase_catch_false_alarms",
            "confirmation_hits",
            "confirmation_misses",
            "confirmation_consecutive_hits",
            "confirmation_clean_catches",
            "confirmation_catch_trials",
            "confirmation_catch_false_alarms",
            "confirmation_required_consecutive_hits",
            "confirmation_required_clean_catches",
            "confirmation_signal_trials",
            "catch_false_alarms",
            "catch_trials",
            "confirmation_hit_rate",
            "confirmation_false_alarm_rate",
            "validation_hit_rate",
            "validation_false_alarm_rate",
            "trial_count",
            "timing",
            "adaptive_staircase",
            "staircase_criteria",
            "confirmation_criteria",
            "report_path",
            "trials_csv_path",
            "latest_path",
        }
        payload = {key: current.get(key, "") for key in keys if key in current}
        for percent_key in (
            "final_output_34_percent",
            "detection_threshold_output_34_percent",
            "recommended_output_34_percent",
            "confirmation_level_output_34_percent",
        ):
            if percent_key in payload:
                try:
                    payload[percent_key] = _coerce_tactile_output_percent(float(payload.get(percent_key)))
                except (TypeError, ValueError):
                    payload[percent_key] = payload.get(percent_key, "")
        if payload:
            payload["max_output_34_percent"] = TACTILE_OUTPUT_34_MAX_PERCENT
        return payload

    def _apply_latest_tactile_calibration(self, participant_id: str | None = None, *, show_message: bool = True) -> bool:
        participant = str(participant_id or self._selected_participant_code() or self.package.participant_id or "").strip()
        latest = load_latest_calibration(self.output_root, participant)
        if latest is None:
            self._latest_tactile_calibration = {}
            return False
        raw_percent = float(latest.get("recommended_output_34_percent", latest["final_output_34_percent"]))
        percent = _coerce_tactile_output_percent(raw_percent)
        self._latest_tactile_calibration = dict(latest)
        if percent != raw_percent:
            self._latest_tactile_calibration["legacy_recommended_output_34_percent_before_cap"] = raw_percent
            for percent_key in (
                "final_output_34_percent",
                "detection_threshold_output_34_percent",
                "recommended_output_34_percent",
                "confirmation_level_output_34_percent",
            ):
                if percent_key in self._latest_tactile_calibration:
                    self._latest_tactile_calibration[percent_key] = percent
            self._latest_tactile_calibration["max_output_34_percent"] = TACTILE_OUTPUT_34_MAX_PERCENT
        self._set_output_volume("output_3_4", percent)
        if show_message and hasattr(self, "event_label"):
            if percent != raw_percent:
                self.event_label.setText(
                    f"{participant}: loaded tactile threshold {raw_percent:g}%, clamped to {percent:g}%"
                )
            else:
                self.event_label.setText(f"{participant}: loaded tactile threshold {percent:g}%")
        return True

    def _refresh_companion_panel(self) -> None:
        status_label = getattr(self, "companion_status_label", None)
        if status_label is not None:
            status_label.setText(str(self.companion_status_message or ""))
        endpoint_label = getattr(self, "companion_endpoint_label", None)
        if endpoint_label is not None:
            if self.companion_enabled:
                endpoint_label.setText(
                    f"http://{self.companion_config.advertised_host}:{self.companion_config.port}"
                )
                endpoint_label.setToolTip(self.companion_pairing_uri)
            else:
                endpoint_label.setText("Disabled for this run.")
                endpoint_label.setToolTip("")
        uri_field = getattr(self, "companion_uri_field", None)
        if uri_field is not None:
            uri_field.setText(self.companion_pairing_uri if self.companion_enabled else "")
        self._refresh_companion_qr_label(getattr(self, "companion_qr_label", None), size=320)

    def _refresh_companion_qr_label(self, qr_label: Any | None, *, size: int | None = None) -> None:
        if qr_label is None:
            return
        if not self.companion_enabled:
            qr_label.setText("Off")
            qr_label.setPixmap(self.q["QPixmap"]())
            return
        if not self.companion_qr_png:
            qr_label.setText("QR unavailable")
            qr_label.setPixmap(self.q["QPixmap"]())
            return
        pixmap = self.q["QPixmap"]()
        if pixmap.loadFromData(self.companion_qr_png):
            qr_label.setText("")
            target_size = qr_label.size()
            if size is not None:
                target_size = self.q["QSize"](int(size), int(size))
            qr_label.setPixmap(
                pixmap.scaled(
                    target_size,
                    self.q["Qt"].AspectRatioMode.KeepAspectRatio,
                    self.q["Qt"].TransformationMode.SmoothTransformation,
                )
            )
        else:
            qr_label.setText("QR unavailable")
            qr_label.setPixmap(self.q["QPixmap"]())

    def _refresh_companion_pairing_payload(self) -> None:
        self.companion_pairing_uri = build_pairing_uri(
            host=self.companion_config.advertised_host,
            port=self.companion_config.port,
            session_id=str(getattr(self.package, "session_id", "") or ""),
            token=self.companion_token,
        )
        if self.companion_enabled:
            try:
                self.companion_qr_png = pairing_qr_png_bytes(self.companion_pairing_uri)
                if not str(self.companion_status_message or "").strip():
                    self.companion_status_message = "Phone companion ready."
            except Exception as exc:
                self.companion_qr_png = b""
                self.companion_status_message = f"Phone companion QR unavailable: {exc}"
        self._write_validation_companion_pairing_report(service_started=self.companion_service is not None)
        self._refresh_companion_panel()

    def _write_validation_companion_pairing_report(self, *, service_started: bool) -> None:
        path_text = str(getattr(self, "_validation_companion_pairing_report", "") or "").strip()
        if not path_text:
            return
        path = Path(path_text).expanduser()
        payload = {
            "schema": "pps-focus-mode-validation-companion-pairing.v1",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "companion_enabled": bool(self.companion_enabled),
            "service_started": bool(service_started),
            "status_message": str(self.companion_status_message or ""),
            "endpoint": f"http://{self.companion_config.advertised_host}:{self.companion_config.port}",
            "pairing_uri": str(self.companion_pairing_uri or ""),
            "session_id": str(getattr(self.package, "session_id", "") or ""),
            "session_group_id": str(getattr(self.package, "session_group_id", "") or ""),
            "part_session_id": str(getattr(self.package, "part_session_id", "") or ""),
            "participant_id": str(getattr(self.package, "participant_id", "") or ""),
            "token_header": "X-PPS-Companion-Token",
            "validation_only": True,
        }
        os.makedirs(_output_filesystem_path(path.parent), exist_ok=True)
        with open(_output_filesystem_path(path), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    def _start_companion_service(self) -> None:
        if not self.companion_enabled:
            self.companion_status_message = "Phone companion is disabled."
            self._refresh_companion_panel()
            return
        if self.companion_service is not None:
            return
        self._refresh_companion_pairing_payload()
        bridge = _FocusCompanionBridge(self)
        try:
            self.companion_service = RunnerCompanionService(
                bridge,
                token=self.companion_token,
                config=self.companion_config,
            )
            self.companion_service.start()
            self.companion_status_message = "Scan to pair a trusted phone on this LAN."
        except Exception as exc:
            self.companion_service = None
            self.companion_status_message = f"Phone companion could not start: {exc}"
        self._write_validation_companion_pairing_report(service_started=self.companion_service is not None)
        self._refresh_companion_panel()

    def _stop_companion_service(self) -> None:
        service = self.companion_service
        self.companion_service = None
        if service is None:
            return
        try:
            service.stop()
        finally:
            self.companion_status_message = "Phone companion stopped."
            self._refresh_companion_panel()

    def _drain_companion_commands(self) -> None:
        while not self._companion_command_queue.empty():
            future, callback = self._companion_command_queue.get_nowait()
            if future.cancelled():
                continue
            try:
                future.set_result(callback())
            except Exception as exc:  # noqa: BLE001 - propagate API failures to the HTTP thread.
                future.set_exception(exc)

    def _companion_health(self) -> dict[str, Any]:
        return {
            "schema": HEALTH_SCHEMA,
            "service": "pps-runner-companion",
            "status": "ok" if self.companion_enabled else "disabled",
            "snapshot_schema": SNAPSHOT_SCHEMA,
            "session_id": str(getattr(self.package, "session_id", "") or ""),
            "participant_id": str(getattr(self.package, "participant_id", "") or ""),
            "port": int(self.companion_config.port),
            "token_header": "X-PPS-Companion-Token",
            "mobile_runtime": self._companion_mobile_runtime_payload(),
        }

    def _companion_mobile_runtime_payload(self) -> dict[str, Any]:
        try:
            package_list = build_mobile_package_list(self._companion_mobile_available_packages())
        except Exception as exc:  # noqa: BLE001 - surfaced as a phone capability warning.
            return {
                "enabled": False,
                "package_count": 0,
                "active_package_id": "",
                "mobile_runnable": False,
                "warnings": [str(exc)],
            }
        packages = list(package_list.get("packages") or [])
        active = dict(packages[0]) if packages else {}
        return {
            "enabled": True,
            "package_count": len(packages),
            "active_package_id": str(package_list.get("active_package_id") or ""),
            "mobile_runnable": bool(active.get("mobile_runnable")),
            "warnings": list(active.get("warnings") or []),
            "runtime_limitations": list(active.get("runtime_limitations") or []),
        }

    def _companion_mobile_packages(self) -> dict[str, Any]:
        return build_mobile_package_list(self._companion_mobile_available_packages())

    def _companion_mobile_package_manifest(self, package_id: str) -> dict[str, Any]:
        package = self._companion_mobile_package_for_id(package_id)
        if package is None:
            raise CompanionCommandError(status_code=404, reason="mobile_package_not_found")
        return build_mobile_package_manifest(package)

    def _companion_mobile_package_asset_path(self, package_id: str, asset_id: str) -> dict[str, Any]:
        package = self._companion_mobile_package_for_id(package_id)
        if package is None:
            raise CompanionCommandError(status_code=404, reason="mobile_package_not_found")
        try:
            path = mobile_asset_path(package, package_id, asset_id)
        except MobileRuntimePackageError as exc:
            raise CompanionCommandError(str(exc), status_code=404, reason="mobile_asset_not_found") from exc
        return {"path": str(path), "media_type": "audio/wav"}

    def _companion_mobile_run_events(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        package = self._companion_mobile_package_for_id(str(payload.get("package_id") or ""))
        if package is None:
            raise CompanionCommandError(status_code=404, reason="mobile_package_not_found")
        try:
            result = write_mobile_runtime_events(
                package,
                output_root=_package_output_root(package),
                run_id=run_id,
                payload=dict(payload or {}),
                complete=False,
            )
        except MobileRuntimePackageError as exc:
            raise CompanionCommandError(str(exc), status_code=409, reason="mobile_runtime_upload_rejected") from exc
        _append_output_diary_event(
            "mobile_phone_runtime_events_uploaded",
            package=package,
            payload={
                "run_id": result.get("run_id", ""),
                "package_id": result.get("package_id", ""),
                "event_count": result.get("event_count", 0),
                "artifact_path": result.get("artifact_path", ""),
            },
        )
        return result

    def _companion_mobile_run_complete(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        package = self._companion_mobile_package_for_id(str(payload.get("package_id") or ""))
        if package is None:
            raise CompanionCommandError(status_code=404, reason="mobile_package_not_found")
        try:
            result = write_mobile_runtime_events(
                package,
                output_root=_package_output_root(package),
                run_id=run_id,
                payload=dict(payload or {}),
                complete=True,
            )
        except MobileRuntimePackageError as exc:
            raise CompanionCommandError(str(exc), status_code=409, reason="mobile_runtime_upload_rejected") from exc
        _append_output_diary_event(
            "mobile_phone_runtime_completed",
            package=package,
            payload={
                "run_id": result.get("run_id", ""),
                "package_id": result.get("package_id", ""),
                "event_count": result.get("event_count", 0),
                "artifact_path": result.get("artifact_path", ""),
            },
        )
        return result

    def _companion_mobile_available_packages(self) -> list[Any]:
        packages: list[Any] = [self.package]
        seen = {mobile_package_id(self.package)}
        for raw_path in list(getattr(self.package, "sibling_part_manifest_paths", []) or []):
            try:
                sibling = load_run_package(Path(raw_path))
            except Exception:
                continue
            package_id = mobile_package_id(sibling)
            if package_id in seen:
                continue
            seen.add(package_id)
            packages.append(sibling)
        return packages

    def _companion_mobile_package_for_id(self, package_id: str) -> Any | None:
        clean = str(package_id or "").strip()
        for package in self._companion_mobile_available_packages():
            if mobile_package_id(package) == clean:
                return package
        return None

    def _companion_select_combo_data(self, combo: Any, value: str) -> bool:
        clean = str(value or "").strip()
        index = combo.findData(clean)
        if index < 0:
            for candidate in range(combo.count()):
                if str(combo.itemText(candidate) or "").strip().lower() == clean.lower():
                    index = candidate
                    break
        if index < 0:
            return False
        combo.setCurrentIndex(index)
        return True

    def _companion_allowed_commands(self) -> list[str]:
        allowed: list[str] = []
        if bool(self.result is not None and bool(getattr(self.result, "completed", False))):
            return allowed
        thread_alive = bool(self.thread is not None and self.thread.is_alive())
        setup_allowed = bool(not self._run_active and not thread_alive)
        if setup_allowed:
            allowed.append("setup")
        if self.pending_instruction_request is not None and not self._part2_start_gate_pending():
            allowed.append("continue_instruction")
        if self.demographics_submitted and self.controller is not None and not thread_alive:
            start_key = self._start_button_part_key()
            if start_key == "1" and not self._part2_start_gate_pending():
                allowed.append("start_part_1")
            if start_key == "2" or self._part2_start_gate_pending():
                allowed.append("start_part_2")
        pause_button = getattr(self, "pause_button", None)
        resume_button = getattr(self, "resume_button", None)
        if self.controller is not None and self._run_active:
            if bool(self._run_paused):
                if resume_button is not None and resume_button.isEnabled():
                    allowed.append("resume")
            elif pause_button is not None and pause_button.isEnabled():
                allowed.append("pause")
        return allowed

    def _companion_setup_payload(self) -> dict[str, Any]:
        failures = self._participant_setup_failures() if not self.demographics_submitted else []
        return {
            "submitted": bool(self.demographics_submitted),
            "ready": bool(self.demographics_submitted and self.controller is not None),
            "required_missing": failures,
            "participant_code": self._selected_participant_code() or str(getattr(self.package, "participant_id", "") or ""),
            "participant_name": str(self.participant_name_input.text() or ""),
            "participant_name_present": bool(str(self.participant_name_input.text() or "").strip()),
            "name_sharing_opt_in": bool(self.include_name_lsl_checkbox.isChecked()),
            "age": str(self.age_input.text() or ""),
            "handedness": str(self.handedness_combo.currentData() or ""),
            "gender": str(self.gender_combo.currentData() or ""),
        }

    def _companion_run_plan_payload(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        active = self.active_display_block_index
        completed = set(getattr(self, "completed_display_block_indices", set()) or set())
        for item in list(getattr(self, "all_block_plan_items", []) or []):
            row = dict(item)
            try:
                number = int(row.get("number") or 0)
            except (TypeError, ValueError):
                number = 0
            if active is not None and number == int(active):
                status = "active"
            elif number in completed:
                status = "complete"
            else:
                status = "pending"
            row["status"] = status
            rows.append(row)
        return rows

    def _companion_active_block_payload(self, *, server_perf_counter_s: float) -> dict[str, Any]:
        state = self.timeline_state
        elapsed = max(0.0, float(state.elapsed_s or 0.0))
        duration = max(0.0, float(state.duration_s or 0.0))
        if duration > 0:
            elapsed = min(elapsed, duration)
        anchor = self._timeline_perf_anchor
        if anchor is None:
            anchor = server_perf_counter_s - elapsed
        return {
            "active": bool(state.active),
            "part_number": str(state.part_number or ""),
            "phase_label": str(state.phase_label or ""),
            "block_index": str(state.block_index or ""),
            "block_label": str(state.block_label or ""),
            "display_block_index": self.active_display_block_index,
            "duration_s": duration,
            "elapsed_s": elapsed,
            "last_anchor_server_perf_counter_s": float(anchor),
            "running": bool(self._run_active and state.active),
            "paused": bool(self._run_paused),
            "instruction_waiting": bool(self.pending_instruction_request is not None),
        }

    def _companion_timeline_payload(self) -> dict[str, Any]:
        state = self.timeline_state
        trial_rows = [
            {
                "trial_number": segment.trial_number,
                "trial_uid": segment.trial_uid,
                "start_s": segment.start_s,
                "end_s": segment.end_s,
                "clip_label": segment.clip_label,
                "trial_label": segment.trial_label,
                "noise_type": segment.noise_type,
                "soa_ms": segment.soa_ms,
                "family": segment.family,
            }
            for segment in state.trial_segments
        ]
        instruction_rows = [
            {
                "slot": segment.slot,
                "label": segment.label,
                "start_s": segment.start_s,
                "end_s": segment.end_s,
                "color": segment.color,
            }
            for segment in state.instruction_segments
        ]
        cues = [
            {
                "cue_id": cue.cue_id,
                "trial_number": cue.trial_number,
                "trial_uid": cue.trial_uid,
                "time_s": cue.time_s,
                "sample_index": cue.sample_index,
                "soa_ms": cue.soa_ms,
                "family": cue.family,
                "row_label": cue.row_label,
                "clip_label": cue.clip_label,
                "trial_label": cue.trial_label,
                "noise_type": cue.noise_type,
                "recentered": cue.recentered,
                "status": state.cue_status(cue),
            }
            for cue in state.cues
        ]
        clicks = [
            {
                "click_id": marker.click_id,
                "time_s": marker.time_s,
                "trial_uid": marker.trial_uid,
                "response_status": marker.response_status,
                "cue_id": marker.cue_id,
                "cue_trial_uid": marker.cue_trial_uid,
                "rt_s": marker.rt_s,
            }
            for marker in state.click_markers
        ]
        return {
            "trial_rows": trial_rows,
            "instruction_rows": instruction_rows,
            "tactile_cues": cues,
            "clicks": clicks,
            "counts": {
                "tactile_total": len(state.cues),
                "tactile_passed": state.passed_count(),
                "clicks": state.click_count(),
                "recentered": state.recentered_count(),
                "planned_tactile_cues": int(getattr(self, "planned_tactile_cue_count", 0) or 0),
            },
        }

    def _companion_instruction_gate_payload(self) -> dict[str, Any]:
        request = self.pending_instruction_request
        if request is None:
            return {"waiting": False}
        context = dict(request.get("context") or {})
        return {
            "waiting": True,
            "request_id": id(request),
            "part2_start_gate": bool(self._part2_start_gate_pending()),
            "instruction_label": str(context.get("instruction_label") or "instruction"),
            "button_label": str(context.get("button_label") or "Continue"),
            "next_action": str(context.get("next_action") or ""),
            "context": context,
        }

    def _companion_snapshot(self) -> dict[str, Any]:
        self._tick_tactile_clock()
        server_perf = time.perf_counter()
        state_payload = {
            "connection_state": "online",
            "allowed_commands": self._companion_allowed_commands(),
            "participant": {
                "participant_id": str(getattr(self.package, "participant_id", "") or ""),
                "selected_participant_id": self._selected_participant_code(),
                "session_id": str(getattr(self.package, "session_id", "") or ""),
                "session_group_id": str(getattr(self.package, "session_group_id", "") or ""),
                "part_session_id": str(getattr(self.package, "part_session_id", "") or ""),
            },
            "setup": self._companion_setup_payload(),
            "part_status": {
                "available_parts": self._available_part_keys(),
                "selected_part": self._ensure_selected_part_key(),
                "current_package_part": self._current_package_part_key(),
                "pending_start_part": self._pending_start_part_key(),
            },
            "run_status": {
                "state_label": str(self.run_state_chip.text() if hasattr(self, "run_state_chip") else ""),
                "progress_label": str(self.progress_label.text() if hasattr(self, "progress_label") else ""),
                "event_label": str(self.event_label.text() if hasattr(self, "event_label") else ""),
                "running": bool(self._run_active),
                "paused": bool(self._run_paused),
                "thread_alive": bool(self.thread is not None and self.thread.is_alive()),
                "complete": bool(self.result is not None and bool(getattr(self.result, "completed", False))),
            },
            "run_plan": self._companion_run_plan_payload(),
            "active_block": self._companion_active_block_payload(server_perf_counter_s=server_perf),
            "timeline": self._companion_timeline_payload(),
            "topup": {
                "enabled": bool(self._topup_slots_enabled_for_plan()),
                "draft_count": len(self._visible_topup_draft_items()),
            },
            "instruction_gate": self._companion_instruction_gate_payload(),
            "mobile_runtime": self._companion_mobile_runtime_payload(),
        }
        signature = json.dumps(state_payload, sort_keys=True, default=str)
        if signature != self._companion_snapshot_signature:
            self._companion_sequence += 1
            self._companion_snapshot_signature = signature
        return {
            "schema": SNAPSHOT_SCHEMA,
            "sequence": int(self._companion_sequence),
            "server_unix_ms": int(time.time() * 1000),
            "server_perf_counter_s": server_perf,
            **state_payload,
        }

    def _companion_submit_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._run_active or (self.thread is not None and self.thread.is_alive()):
            raise CompanionCommandError(reason="setup_locked_while_running")
        participant_code = str(payload.get("participant_code") or payload.get("participant_id") or "").strip()
        selected = self._selected_participant_code() or str(getattr(self.package, "participant_id", "") or "")
        if participant_code and participant_code != selected:
            raise CompanionCommandError(reason="participant_switching_is_laptop_only")
        name = str(payload.get("participant_name") or payload.get("name") or "").strip()
        age = str(payload.get("age") or payload.get("age_years") or "").strip()
        handedness = str(payload.get("handedness") or "").strip()
        gender = str(payload.get("gender") or "").strip()
        share_name = bool(
            payload.get("name_sharing_opt_in")
            if "name_sharing_opt_in" in payload
            else payload.get("include_name_in_lsl", payload.get("share_participant_name", False))
        )
        self.participant_name_input.setText(name)
        self.age_input.setText(age)
        self.include_name_lsl_checkbox.setChecked(share_name)
        if handedness and not self._companion_select_combo_data(self.handedness_combo, handedness):
            raise CompanionCommandError(reason="invalid_handedness")
        if gender and not self._companion_select_combo_data(self.gender_combo, gender):
            raise CompanionCommandError(reason="invalid_gender")
        if not self._submit_participant_setup():
            raise CompanionCommandError(reason="setup_incomplete")
        return self._companion_snapshot()

    def _companion_continue_instruction(self) -> dict[str, Any]:
        if self.pending_instruction_request is None:
            raise CompanionCommandError(reason="no_instruction_gate")
        if self._part2_start_gate_pending():
            raise CompanionCommandError(reason="use_start_part_2")
        if not self._approve_pending_instruction_continue(source="phone companion"):
            raise CompanionCommandError(reason="continue_instruction_failed")
        return self._companion_snapshot()

    def _companion_start_part(self, part_number: int) -> dict[str, Any]:
        part = int(part_number)
        thread_alive = bool(self.thread is not None and self.thread.is_alive())
        if part == 2 and self._part2_start_gate_pending():
            self._start_part2_gate(source="phone companion")
            return self._companion_snapshot()
        if thread_alive or self._run_active:
            raise CompanionCommandError(reason="run_already_active")
        if not self.demographics_submitted or self.controller is None:
            raise CompanionCommandError(reason="setup_required")
        target_key = str(part)
        if target_key not in self._available_part_keys() and target_key != self._start_button_part_key():
            raise CompanionCommandError(reason="part_not_available")
        if target_key != self._start_button_part_key():
            self._select_part_key(target_key, preview_first=True)
        if target_key != self._start_button_part_key():
            raise CompanionCommandError(reason=f"start_part_{part}_not_available")
        if not self.start_button.isEnabled() and not self._part2_start_gate_pending():
            raise CompanionCommandError(reason=f"start_part_{part}_not_allowed")
        self.start()
        return self._companion_snapshot()

    def _companion_set_paused(self, paused: bool) -> dict[str, Any]:
        desired = bool(paused)
        pause_button = getattr(self, "pause_button", None)
        resume_button = getattr(self, "resume_button", None)
        if self.controller is None or not self._run_active:
            raise CompanionCommandError(reason="pause_not_allowed")
        if bool(self._run_paused) == desired:
            return self._companion_snapshot()
        active_button = pause_button if desired else resume_button
        if active_button is None or not active_button.isEnabled():
            raise CompanionCommandError(reason="pause_not_allowed")
        if desired:
            self._pause()
        else:
            self._resume()
        if bool(self._run_paused) != desired:
            raise CompanionCommandError(reason="pause_state_not_changed")
        return self._companion_snapshot()

    def _install_response_click_filter(self) -> None:
        app = self.q["QApplication"].instance()
        if app is None or self._response_click_filter_installed:
            return
        app.installEventFilter(self.dialog)
        self._response_click_filter_installed = True

    def _remove_response_click_filter(self) -> None:
        app = self.q["QApplication"].instance()
        if app is None or not self._response_click_filter_installed:
            return
        try:
            app.removeEventFilter(self.dialog)
        except Exception:
            pass
        self._response_click_filter_installed = False

    def _refresh_target_global_bounds(self) -> None:
        bounds: tuple[int, int, int, int] | None = None
        try:
            top_left = self.target_button.mapToGlobal(self.q["QPoint"](0, 0))
            left = int(top_left.x())
            top = int(top_left.y())
            width = max(0, int(self.target_button.width()))
            height = max(0, int(self.target_button.height()))
            if width > 0 and height > 0:
                bounds = (left, top, left + width, top + height)
        except Exception:
            bounds = None
        with self._target_global_bounds_lock:
            self._target_global_bounds = bounds

    def _cached_target_contains_global_xy(self, x: int | None, y: int | None) -> bool:
        if x is None or y is None:
            return False
        with self._target_global_bounds_lock:
            bounds = self._target_global_bounds
        if bounds is None:
            return False
        left, top, right, bottom = bounds
        try:
            return left <= int(x) <= right and top <= int(y) <= bottom
        except Exception:
            return False

    def _is_left_mouse_button(self, button: Any) -> bool:
        name = str(getattr(button, "name", "") or "").strip().lower()
        if name == "left":
            return True
        text = str(button or "").strip().lower()
        return text in {"left", "button.left", "mousebutton.left"} or text.endswith(".left")

    def _start_global_response_click_listener(self) -> bool:
        if self._offscreen_platform():
            return False
        if _env_flag("PPS_FOCUS_VALIDATION_DISABLE_MOUSE_CAPTURE"):
            self._global_response_click_listener_error = "disabled_by_validation"
            _append_output_diary_event(
                "global_response_click_listener_disabled",
                package=self.package,
                capture_options=self.capture_options.as_dict(),
                payload={"reason": "PPS_FOCUS_VALIDATION_DISABLE_MOUSE_CAPTURE"},
                create=True,
            )
            return False
        with self._global_response_click_listener_lock:
            if self._global_response_click_listener is not None:
                return True
            try:
                from pynput import mouse  # type: ignore
            except Exception as exc:
                self._global_response_click_listener_error = str(exc)
                _append_output_diary_event(
                    "global_response_click_listener_unavailable",
                    package=self.package,
                    capture_options=self.capture_options.as_dict(),
                    payload={"backend": "pynput", "message": str(exc)},
                    create=True,
                )
                return False

            def _on_click(x: Any, y: Any, button: Any, pressed: bool) -> None:
                if not pressed or not self._is_left_mouse_button(button):
                    return
                self._handle_global_response_mouse_click(x, y)

            try:
                listener = mouse.Listener(on_click=_on_click)
                listener.start()
            except Exception as exc:
                self._global_response_click_listener_error = str(exc)
                _append_output_diary_event(
                    "global_response_click_listener_unavailable",
                    package=self.package,
                    capture_options=self.capture_options.as_dict(),
                    payload={"backend": "pynput", "message": str(exc)},
                    create=True,
                )
                return False
            self._global_response_click_listener = listener
            self._global_response_click_listener_error = ""
            _append_output_diary_event(
                "global_response_click_listener_started",
                package=self.package,
                capture_options=self.capture_options.as_dict(),
                payload={"backend": "pynput"},
                create=True,
            )
            return True

    def _stop_global_response_click_listener(self) -> None:
        with self._global_response_click_listener_lock:
            listener = self._global_response_click_listener
            self._global_response_click_listener = None
        if listener is None:
            return
        try:
            listener.stop()
        except Exception:
            pass
        try:
            listener_ident = getattr(listener, "ident", None)
            if listener_ident is None or listener_ident != threading.current_thread().ident:
                listener.join(timeout=0.2)
        except Exception:
            pass

    def _start_tactile_calibration_response_listener(self) -> None:
        with self._global_response_click_listener_lock:
            already_running = self._global_response_click_listener is not None
        started = self._start_global_response_click_listener()
        self._tactile_calibration_started_global_listener = bool(started and not already_running)

    def _stop_tactile_calibration_response_listener(self) -> None:
        if self._tactile_calibration_started_global_listener:
            self._stop_global_response_click_listener()
        self._tactile_calibration_started_global_listener = False

    def _object_is_target_button(self, watched: Any) -> bool:
        current = watched
        while current is not None:
            if current is self.target_button:
                return True
            parent = getattr(current, "parent", None)
            current = parent() if callable(parent) else None
        return False

    def _mouse_event_global_xy(self, event: Any) -> tuple[int | None, int | None]:
        try:
            point = event.globalPosition().toPoint()
        except AttributeError:
            try:
                point = event.globalPos()
            except Exception:
                return None, None
        try:
            return int(point.x()), int(point.y())
        except Exception:
            return None, None

    def _target_contains_global_xy(self, x: int | None, y: int | None) -> bool:
        if x is None or y is None:
            return False
        self._refresh_target_global_bounds()
        return self._cached_target_contains_global_xy(x, y)

    def _tactile_calibration_target_widget(self) -> Any | None:
        monitor = getattr(self, "tactile_calibration_monitor_dialog", None)
        target = getattr(monitor, "target_button", None) if monitor is not None else None
        if target is not None and target.isVisible():
            return target
        return getattr(self, "target_button", None)

    def _tactile_calibration_target_center(self) -> tuple[int | None, int | None, str]:
        target = self._tactile_calibration_target_widget()
        if target is None:
            return None, None, "unavailable"
        return _widget_screen_center(target)

    def _tactile_calibration_contains_global_xy(self, x: int | None, y: int | None) -> bool:
        if x is None or y is None:
            return False
        target = self._tactile_calibration_target_widget()
        if target is None:
            return False
        try:
            point = target.mapFromGlobal(self.q["QPoint"](int(x), int(y)))
            return bool(target.rect().contains(point))
        except Exception:
            return self._target_contains_global_xy(x, y)

    def _target_last_click_global_xy(self) -> tuple[int | None, int | None]:
        value = getattr(self.target_button, "last_click_global_pos", None)
        if isinstance(value, tuple) and len(value) == 2:
            try:
                return int(value[0]), int(value[1])
            except Exception:
                pass
        return None, None

    def _handle_response_mouse_press(self, watched: Any, event: Any) -> None:
        if (
            not self._run_active
            or self.controller is None
            or self.pending_instruction_request is not None
            or self._object_is_target_button(watched)
        ):
            return
        try:
            if event.button() != self.q["Qt"].MouseButton.LeftButton:
                return
        except Exception:
            return
        x, y = self._mouse_event_global_xy(event)
        in_target = self._target_contains_global_xy(x, y)
        if in_target:
            return
        self._log_response_click(
            x=x,
            y=y,
            in_target=False,
            diary_event_type="response_window_clicked",
            source="qt_event_filter",
        )

    def _log_response_click(
        self,
        *,
        x: int | None = None,
        y: int | None = None,
        in_target: bool,
        diary_event_type: str,
        source: str,
    ) -> None:
        if self.controller is None:
            self.event_label.setText("Start the run before logging responses.")
            return
        payload = self._record_response_click_event(
            x=x,
            y=y,
            in_target=in_target,
            diary_event_type=diary_event_type,
            source=source,
        )
        if payload is not None:
            self._apply_response_click_to_ui(payload)

    def _normalize_response_click_xy(self, x: Any, y: Any) -> tuple[int | None, int | None]:
        try:
            clean_x = int(x)
        except Exception:
            clean_x = None
        try:
            clean_y = int(y)
        except Exception:
            clean_y = None
        return clean_x, clean_y

    def _current_response_elapsed_s(self) -> float | str:
        if not self.timeline_state.active:
            return ""
        elapsed = float(self.timeline_state.elapsed_s or 0.0)
        anchor = self._timeline_perf_anchor
        if anchor is not None and self._run_active:
            elapsed = max(elapsed, time.perf_counter() - float(anchor))
        duration = float(self.timeline_state.duration_s or 0.0)
        if duration > 0:
            elapsed = min(elapsed, duration)
        return max(0.0, elapsed)

    def _is_duplicate_response_click(
        self,
        signature: tuple[int | None, int | None, bool],
        now: float,
    ) -> bool:
        last_signature = self._last_response_click_signature
        if last_signature is None:
            return False
        previous, previous_time = last_signature
        if now - previous_time >= 0.05:
            return False
        if previous[2] != signature[2]:
            return False
        previous_x, previous_y, _previous_target = previous
        x, y, _target = signature
        if previous_x is None or previous_y is None or x is None or y is None:
            return previous_x == x and previous_y == y
        return abs(previous_x - x) <= 2 and abs(previous_y - y) <= 2

    def _record_response_click_event(
        self,
        *,
        x: int | None = None,
        y: int | None = None,
        in_target: bool,
        diary_event_type: str,
        source: str,
    ) -> dict[str, Any] | None:
        clean_x, clean_y = self._normalize_response_click_xy(x, y)
        target_hit = bool(in_target)
        now = time.perf_counter()
        signature = (clean_x, clean_y, target_hit)
        with self._response_click_record_lock:
            if self.controller is None:
                return None
            if self._is_duplicate_response_click(signature, now):
                return None
            self._last_response_click_signature = (signature, now)
            elapsed_s = self._current_response_elapsed_s()
            during_playback = bool(self._run_active)
            self.controller.log_click(x=clean_x, y=clean_y, in_target=target_hit)
        return {
            "in_target": target_hit,
            "x": "" if clean_x is None else clean_x,
            "y": "" if clean_y is None else clean_y,
            "during_playback": during_playback,
            "elapsed_s": elapsed_s,
            "diary_event_type": diary_event_type,
            "source": str(source or ""),
        }

    def _apply_response_click_to_ui(self, payload: dict[str, Any]) -> None:
        in_target = bool(payload.get("in_target"))
        elapsed_s = payload.get("elapsed_s", "")
        if self.timeline_state.active:
            try:
                click_elapsed = float(elapsed_s)
            except (TypeError, ValueError):
                click_elapsed = self.timeline_state.elapsed_s
            self.timeline_state.record_click(click_elapsed)
            self._update_tactile_timeline_display()
        self.event_label.setText("Participant click logged" if in_target else "Participant click logged outside target")
        diary_event_type = str(payload.get("diary_event_type") or "response_clicked")
        _append_output_diary_event(
            diary_event_type,
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={
                "in_target": in_target,
                "x": payload.get("x", ""),
                "y": payload.get("y", ""),
                "during_playback": bool(payload.get("during_playback")),
                "elapsed_s": elapsed_s,
                "source": str(payload.get("source") or ""),
            },
            create=True,
        )

    def _handle_global_response_mouse_click(self, x: Any, y: Any) -> None:
        if self._tactile_calibration_active:
            clean_x, clean_y = self._normalize_response_click_xy(x, y)
            in_target = self._tactile_calibration_contains_global_xy(clean_x, clean_y)
            payload = self._tactile_calibration_collector.record_click(
                in_target=in_target,
                x=clean_x,
                y=clean_y,
                source="global_mouse_listener",
            )
            if payload:
                self.messages.put(
                    (
                        "tactile_calibration_click",
                        payload,
                    )
                )
            return
        if not self._run_active or self.controller is None or self.pending_instruction_request is not None:
            return
        clean_x, clean_y = self._normalize_response_click_xy(x, y)
        in_target = self._cached_target_contains_global_xy(clean_x, clean_y)
        payload = self._record_response_click_event(
            x=clean_x,
            y=clean_y,
            in_target=in_target,
            diary_event_type="target_clicked" if in_target else "response_global_clicked",
            source="global_mouse_listener",
        )
        if payload is not None:
            self.messages.put(("response_click", payload))

    def _timeline_display_state(self) -> TactileTimelineState:
        if self.preview_display_block_index is not None:
            return self.timeline_preview_state
        return self.timeline_state

    def _available_part_keys(self) -> list[str]:
        if _package_is_split_part(self.package):
            keys = list(self._split_part_manifest_map())
            if keys:
                return sorted(keys, key=_part_sort_key)
        return _package_part_keys(self.package)

    def _current_package_part_key(self) -> str:
        part_key = _part_key_text(getattr(self.package, "part_number", ""))
        if part_key:
            return part_key
        keys = _package_part_keys(self.package)
        return keys[0] if keys else ""

    def _split_part_manifest_map(self) -> dict[str, Path]:
        manifests: dict[str, Path] = {}
        current_key = self._current_package_part_key()
        current_manifest = Path(getattr(self.package, "manifest_path", ""))
        if current_key and str(current_manifest):
            manifests[current_key] = current_manifest
        for manifest_path in list(getattr(self.package, "sibling_part_manifest_paths", []) or []):
            path = Path(manifest_path)
            if not path.exists():
                continue
            try:
                sibling = load_run_package(path)
            except Exception:
                continue
            key = _part_key_text(getattr(sibling, "part_number", ""))
            if key:
                manifests[key] = sibling.manifest_path
        return manifests

    def _ensure_selected_part_key(self) -> str:
        available = self._available_part_keys()
        current = str(self.selected_part_key or "").strip()
        if current in available:
            return current
        self.selected_part_key = available[0] if available else "1"
        return str(self.selected_part_key)

    def _select_part_key(self, part_key: str, *, preview_first: bool = False) -> None:
        key = str(part_key or "").strip()
        if key not in self._available_part_keys():
            return
        if _package_is_split_part(self.package) and key != self._current_package_part_key():
            self._load_split_part_key(key)
            return
        self.selected_part_key = key
        self._refresh_run_plan(select_default=preview_first)

    def _refresh_part_controls(self) -> None:
        available = set(self._available_part_keys())
        selected = self._ensure_selected_part_key()
        for part_key, button in getattr(self, "part_buttons", {}).items():
            enabled = part_key in available and bool(getattr(self, "_experiment_control_ready", False))
            button.setEnabled(enabled)
            button.setChecked(enabled and part_key == selected)
            if enabled:
                button.setToolTip(f"Show {_part_button_label(part_key)} block order and top-up draft.")
            else:
                button.setToolTip(f"{_part_button_label(part_key)} is not present in this Segment 6 setup.")
        self._refresh_start_part2_button()
        self._refresh_start_button_label()

    def _load_split_part_key(self, part_key: str) -> None:
        if self.thread is not None and self.thread.is_alive():
            if hasattr(self, "event_label"):
                self.event_label.setText("Stop or finish the current part before switching parts.")
            return
        manifest_path = self._split_part_manifest_map().get(str(part_key))
        if manifest_path is None:
            if hasattr(self, "event_label"):
                self.event_label.setText(f"{_part_display_label(part_key)} is not prepared for this participant.")
            return
        try:
            package = load_run_package(manifest_path)
        except Exception as exc:
            if hasattr(self, "event_label"):
                self.event_label.setText(f"Could not load {_part_display_label(part_key)}: {exc}")
            return
        restore_submitted_setup = bool(self.demographics_submitted and self.controller is not None)
        self._prepare_continuous_external_labrecorder_handoff(package)
        self.selected_part_key = str(part_key)
        self._replace_loaded_package(package, message=f"{_part_display_label(part_key)} ready. Submit setup, then start.")
        if restore_submitted_setup:
            if self._submit_participant_setup():
                self.event_label.setText(f"{_part_display_label(part_key)} ready. Press {self.start_button.text()} when ready.")

    def _prepare_continuous_external_labrecorder_handoff(self, next_package: Any) -> None:
        controller = self.controller
        if controller is None:
            return
        if not (_package_is_split_part(self.package) and _package_is_split_part(next_package)):
            return
        if str(getattr(self.package, "session_group_id", "")) != str(getattr(next_package, "session_group_id", "")):
            return
        handoff = getattr(controller, "handoff_external_labrecorder_to_next_part", None)
        if not callable(handoff):
            return
        state = handoff()
        if not state:
            return
        self._continuous_external_labrecorder_state = dict(state)
        _append_output_diary_event(
            "external_labrecorder_handoff_prepared",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={
                "next_part_session_id": str(getattr(next_package, "part_session_id", "") or getattr(next_package, "session_id", "")),
                "session_group_id": str(getattr(next_package, "session_group_id", "")),
                "xdf_path": str(state.get("xdf_path") or ""),
                "finalize_path": str(state.get("finalize_path") or ""),
                "lsl_stream_session_id": str(state.get("lsl_stream_session_id") or ""),
            },
            create=True,
        )

    def _start_button_part_key(self) -> str:
        if self._part2_start_gate_pending():
            return "2"
        return self._ensure_selected_part_key()

    def _refresh_start_button_label(self) -> None:
        button = getattr(self, "start_button", None)
        if button is None:
            return
        part_key = self._start_button_part_key()
        if part_key:
            label = f"Start {_part_display_label(part_key)}"
            button.setText(label)
            button.setToolTip(f"Start playback for {_part_display_label(part_key)}.")
        else:
            button.setText("Start Run")
            button.setToolTip("Start playback for the selected run package.")

    def _pending_start_part_key(self) -> str:
        request = self.pending_instruction_request
        if request is None:
            return ""
        context = dict(request.get("context") or {})
        if str(context.get("next_action") or "").strip() != "next_condition":
            return ""
        for key in ("next_part_number", "part_number", "block_part_number", "Part_Number"):
            value = context.get(key)
            if value not in (None, ""):
                return _part_key_text(value)
        return "2" if "2" in self._available_part_keys() else ""

    def _refresh_start_part2_button(self) -> None:
        button = getattr(self, "start_part2_button", None)
        if button is None:
            return
        if _package_is_split_part(self.package):
            button.setVisible(False)
            button.setEnabled(False)
            return
        has_part2 = "2" in self._available_part_keys()
        button.setVisible(has_part2)
        pending_part = self._pending_start_part_key()
        enabled = bool(has_part2 and pending_part == "2")
        button.setEnabled(enabled)
        button.setText("Start Part 02")
        if enabled:
            button.setToolTip("Part 01 is complete. Click to continue acquisition into Part 02.")
        elif has_part2:
            button.setToolTip("Part 02 can be started only after Part 01 has finished and the runner is waiting at the part boundary.")
        else:
            button.setToolTip("This run setup has no Part 02.")

    def _part2_start_gate_pending(self) -> bool:
        return self._pending_start_part_key() == "2"

    def _start_part2_button_clicked(self) -> None:
        self._start_part2_gate(source="start part 2 button")

    def _start_part2_gate(self, *, source: str) -> None:
        if not self._part2_start_gate_pending():
            if hasattr(self, "event_label"):
                self.event_label.setText("Start Part 02 becomes available after Part 01 is complete.")
            self._refresh_start_part2_button()
            self._refresh_start_button_label()
            return
        self.selected_part_key = "2"
        self._refresh_run_plan()
        self._approve_pending_instruction_continue(source=source)
        self._refresh_start_part2_button()
        self._refresh_start_button_label()

    def _next_split_part_manifest(self) -> Path | None:
        if not _package_is_split_part(self.package):
            return None
        current_part = _part_key_text(getattr(self.package, "part_number", ""))
        try:
            current_number = int(current_part or "0")
        except ValueError:
            current_number = 0
        candidates: list[tuple[int, Path]] = []

        def _add_candidate(manifest_path: Any, *, part_number_hint: Any = None, base: Path | None = None) -> None:
            path = Path(manifest_path)
            if not path.is_absolute() and base is not None:
                path = base / path
            if not _focus_path_is_file(path):
                return
            try:
                next_package = load_run_package(path)
            except Exception:
                next_package = None
            try:
                part_number = int(_part_key_text(part_number_hint) or _part_key_text(getattr(next_package, "part_number", "")) or "0")
            except (TypeError, ValueError):
                part_number = 0
            if part_number > current_number:
                candidates.append((part_number, Path(getattr(next_package, "manifest_path", path))))

        for manifest_path in list(getattr(self.package, "sibling_part_manifest_paths", []) or []):
            _add_candidate(manifest_path)
        if not candidates:
            active_manifest = Path(getattr(self.package, "manifest_path", ""))
            manifest_payload = _read_json_dict(active_manifest)
            outputs = dict(manifest_payload.get("outputs") or {})
            group_manifest_path = _validation_resolve_path(
                outputs.get("session_group_manifest_json") or manifest_payload.get("session_group_manifest_path"),
                active_manifest.parent if str(active_manifest) else None,
                None,
            )
            group_payload = _read_json_dict(group_manifest_path) if group_manifest_path is not None else {}
            for entry in group_payload.get("parts") if isinstance(group_payload.get("parts"), list) else []:
                if not isinstance(entry, dict):
                    continue
                _add_candidate(
                    entry.get("session_manifest_path"),
                    part_number_hint=entry.get("part_number"),
                    base=group_manifest_path.parent if group_manifest_path is not None else None,
                )
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0])[0][1]

    def _auto_load_next_split_part_after_completion(self, *, completion_message: str = "") -> bool:
        manifest_path = self._next_split_part_manifest()
        if manifest_path is None:
            return False
        restore_submitted_setup = bool(self.demographics_submitted and self.controller is not None)
        previous_output_summary = ""
        if hasattr(self, "output_summary"):
            previous_output_summary = str(self.output_summary.toPlainText() or "").strip()
        try:
            package = load_run_package(manifest_path)
        except Exception as exc:
            if hasattr(self, "event_label"):
                self.event_label.setText(f"Part 01 complete; could not load Part 02 automatically: {exc}")
            return False
        next_part_key = _part_key_text(getattr(package, "part_number", "")) or "2"
        self._prepare_continuous_external_labrecorder_handoff(package)
        self.selected_part_key = next_part_key
        next_label = _part_display_label(next_part_key)
        prefix = str(completion_message or "Part 01 complete.").strip()
        self._replace_loaded_package(package, message=f"{prefix} {next_label} loaded. Submit setup to start.")
        if restore_submitted_setup and self._submit_participant_setup():
            if hasattr(self, "event_label"):
                self.event_label.setText(f"{prefix} {next_label} loaded. Press {self.start_button.text()} when ready.")
            self._set_setup_status_message(f"Setup submitted for {next_label}. Experiment Control is ready.")
        if previous_output_summary and hasattr(self, "output_summary"):
            handoff_status = f"{next_label} loaded for same-window continuation."
            self.output_summary.setPlainText(f"{previous_output_summary}\n\n{handoff_status}")
        return True

    def _visible_plan_items(self) -> list[dict[str, Any]]:
        selected = self._ensure_selected_part_key()
        return [dict(item) for item in self.all_block_plan_items if str(item.get("part_key") or "") == selected]

    def _run_plan_item_by_number(self, display_number: int) -> dict[str, Any] | None:
        target = int(display_number or 0)
        for item in list(getattr(self, "all_block_plan_items", []) or []) or list(getattr(self, "block_plan_items", []) or []):
            if int(item.get("number") or 0) == target:
                return dict(item)
        return None

    def _topup_item_for_part(self, part_key: str | None = None) -> dict[str, Any] | None:
        key = str(part_key or self._ensure_selected_part_key() or "").strip()
        for item in list(getattr(self, "all_block_plan_items", []) or []):
            if str(item.get("part_key") or "") == key and str(item.get("kind") or "") == "topup":
                return dict(item)
        return None

    def _select_current_part_topup_slot(self) -> None:
        item = self._topup_item_for_part()
        if item is not None:
            self._select_block_plan_item(int(item.get("number") or 0))

    def _visible_topup_draft_items(self) -> list[dict[str, Any]]:
        selected = self._ensure_selected_part_key()
        return [
            dict(item)
            for item in list(getattr(self, "topup_draft_items", []) or [])
            if str(item.get("part_number") or "1").strip() == selected
        ]

    def _topup_draft_should_show(self) -> bool:
        enabled = bool(self._topup_slots_enabled_for_plan())
        if not enabled:
            return False
        if self.layout_profile.compact or self.layout_profile.available_height <= 900:
            return False
        selected_item = self._run_plan_item_by_number(self.selected_display_block_index or 0)
        if selected_item is not None and str(selected_item.get("kind") or "") == "topup":
            return True
        return bool(self._visible_topup_draft_items())

    def _refresh_topup_draft_widget(self) -> None:
        if not hasattr(self, "topup_draft_widget"):
            return
        self.topup_draft_widget.setVisible(self._topup_draft_should_show())
        refresh_height = getattr(self.topup_draft_widget, "refresh_layout_height", None)
        if callable(refresh_height):
            refresh_height()
        self.topup_draft_widget.update()
        self._refresh_experiment_control_minimum_height()

    def _experiment_control_visible_widgets(self) -> list[tuple[str, Any]]:
        candidates = [
            ("run_controls_widget", getattr(self, "run_controls_widget", None)),
            ("part_selector_widget", getattr(self, "part_selector_widget", None)),
            ("block_plan_widget", getattr(self, "block_plan_widget", None)),
            ("block_preview_label", getattr(self, "block_preview_label", None)),
            ("topup_draft_widget", getattr(self, "topup_draft_widget", None)),
            ("timeline_status_widget", getattr(self, "timeline_status_widget", None)),
            ("tactile_timeline_widget", getattr(self, "tactile_timeline_widget", None)),
            ("recenter_status_label", getattr(self, "recenter_status_label", None)),
            ("progress_label", getattr(self, "progress_label", None)),
            ("progress_track_widget", getattr(self, "progress_track_widget", None)),
            ("event_label", getattr(self, "event_label", None)),
            ("prewarm_label", getattr(self, "prewarm_label", None)),
        ]
        visible: list[tuple[str, Any]] = []
        for name, widget in candidates:
            if widget is None:
                continue
            try:
                if widget.isHidden():
                    continue
            except Exception:
                continue
            visible.append((name, widget))
        return visible

    def _experiment_control_visible_layout_widgets(self) -> list[Any]:
        layout = self.processing_panel.layout() if hasattr(self, "processing_panel") else None
        if layout is None:
            return []
        widgets: list[Any] = []
        for index in range(int(layout.count())):
            item = layout.itemAt(index)
            widget = item.widget() if item is not None else None
            if widget is None:
                continue
            try:
                if widget.isHidden():
                    continue
            except Exception:
                continue
            widgets.append(widget)
        return widgets

    def _widget_required_height(self, widget: Any, available_width: int) -> int:
        heights = [0]
        for getter_name in ("minimumHeight",):
            try:
                heights.append(max(0, int(getattr(widget, getter_name)())))
            except Exception:
                pass
        for getter_name in ("minimumSizeHint", "sizeHint"):
            try:
                hint = getattr(widget, getter_name)()
                heights.append(max(0, int(hint.height())))
            except Exception:
                pass
        width = max(1, int(available_width or 1))
        try:
            current_width = int(widget.width())
            if current_width > 1:
                width = min(width, current_width)
        except Exception:
            pass
        try:
            if bool(widget.hasHeightForWidth()):
                heights.append(max(0, int(widget.heightForWidth(width))))
        except Exception:
            pass
        return max(heights)

    def _experiment_control_layout_margins_and_spacing(self) -> tuple[int, int, int]:
        layout = self.processing_panel.layout() if hasattr(self, "processing_panel") else None
        margin_total = 0
        horizontal_margins = 0
        spacing = max(0, int(getattr(layout, "spacing", lambda: 0)())) if layout is not None else 0
        if layout is not None:
            margins = layout.contentsMargins()
            margin_total = int(margins.top()) + int(margins.bottom())
            horizontal_margins = int(margins.left()) + int(margins.right())
        return margin_total, horizontal_margins, spacing

    def _experiment_control_content_minimum_height(self) -> int:
        profile_min = int(getattr(self.layout_profile, "experiment_control_content_min_height", 0) or 0)
        if not hasattr(self, "processing_panel"):
            return profile_min
        margin_total, horizontal_margins, spacing = self._experiment_control_layout_margins_and_spacing()
        panel_width = int(getattr(self.processing_panel, "width", lambda: 0)() or 0)
        fallback_width = max(360, int(getattr(self.layout_profile, "window_width", 0) or 0))
        available_width = max(1, (panel_width or fallback_width) - horizontal_margins)
        visible_heights = [self._widget_required_height(widget, available_width) for widget in self._experiment_control_visible_layout_widgets()]
        if not visible_heights:
            return profile_min
        core_total = margin_total + sum(visible_heights) + spacing * max(0, len(visible_heights) - 1)
        return max(profile_min, int(core_total))

    def _clamp_workspace_splitter_for_experiment_control(self) -> None:
        if self._workspace_splitter_clamping:
            return
        if not hasattr(self, "workspace_splitter") or not hasattr(self, "processing_panel"):
            return
        target = max(
            int(getattr(self.processing_panel, "minimumHeight", lambda: 0)() or 0),
            int(getattr(self, "experiment_control_content_min_height", 0) or 0),
            self._experiment_control_content_minimum_height(),
        )
        sizes = list(self.workspace_splitter.sizes())
        if len(sizes) < 2:
            return
        total = int(getattr(self.workspace_splitter, "height", lambda: 0)() or 0)
        if total <= 0:
            total = sum(int(size) for size in sizes)
        if total <= 0:
            return
        bottom = int(sizes[-1])
        if bottom >= target:
            return
        self._workspace_splitter_clamping = True
        try:
            top = max(0, total - target)
            self.workspace_splitter.setSizes([top, target])
        finally:
            self._workspace_splitter_clamping = False

    def _schedule_experiment_control_splitter_clamp(self) -> None:
        if self._workspace_splitter_clamp_pending:
            return
        if not hasattr(self, "dialog"):
            return
        self._workspace_splitter_clamp_pending = True

        def _run() -> None:
            self._workspace_splitter_clamp_pending = False
            self._refresh_experiment_control_minimum_height()
            self._clamp_workspace_splitter_for_experiment_control()

        self.q["QTimer"].singleShot(0, _run)

    def _experiment_control_layout_debug(self) -> dict[str, Any]:
        content_min = self._experiment_control_content_minimum_height()
        panel_height = int(getattr(self.processing_panel, "height", lambda: 0)() or 0) if hasattr(self, "processing_panel") else 0
        visible_widgets = self._experiment_control_visible_widgets()
        visible_names = {name for name, _widget in visible_widgets}
        required_names = self._required_experiment_control_widget_names()
        panel_rect = {
            "width": int(getattr(self.processing_panel, "width", lambda: 0)() or 0) if hasattr(self, "processing_panel") else 0,
            "height": panel_height,
        }
        widgets: dict[str, dict[str, int]] = {}
        clipped: list[str] = []
        too_short: list[str] = []
        overlap_pairs: list[str] = []
        for name, widget in visible_widgets:
            try:
                top_left = widget.mapTo(self.processing_panel, widget.rect().topLeft())
                width = int(widget.width())
                height = int(widget.height())
                x = int(top_left.x())
                y = int(top_left.y())
                rect = {
                    "x": x,
                    "y": y,
                    "right": x + width,
                    "bottom": y + height,
                    "width": width,
                    "height": height,
                }
            except Exception:
                continue
            required_height = self._widget_required_height(widget, max(1, rect["width"]))
            rect["required_height"] = int(required_height)
            widgets[name] = rect
            if rect["x"] < 0 or rect["y"] < 0 or rect["right"] > panel_rect["width"] or rect["bottom"] > panel_height:
                clipped.append(name)
            if rect["height"] < required_height:
                too_short.append(name)
        names = list(widgets)
        for left_index, left_name in enumerate(names):
            left = widgets[left_name]
            for right_name in names[left_index + 1 :]:
                right = widgets[right_name]
                horizontal_overlap = left["x"] < right["right"] and right["x"] < left["right"]
                vertical_overlap = left["y"] < right["bottom"] and right["y"] < left["bottom"]
                if horizontal_overlap and vertical_overlap:
                    overlap_pairs.append(f"{left_name}:{right_name}")
        timeline_debug = {}
        if hasattr(self, "tactile_timeline_widget"):
            timeline_snapshot = getattr(self.tactile_timeline_widget, "timeline_debug_snapshot", None)
            if callable(timeline_snapshot):
                timeline_debug = dict(timeline_snapshot())
        return {
            "content_min_height": int(content_min),
            "profile_content_min_height": int(self.layout_profile.experiment_control_content_min_height),
            "profile_min_height": int(self.layout_profile.experiment_control_min_height),
            "panel_minimum_height": int(self.processing_panel.minimumHeight()) if hasattr(self, "processing_panel") else 0,
            "actual_height": int(panel_height),
            "visible_child_count": len(visible_widgets),
            "widgets": widgets,
            "clipped_widgets": clipped,
            "too_short_widgets": too_short,
            "overlap_pairs": overlap_pairs,
            "overlap_count": len(overlap_pairs),
            "hidden_required_widgets": sorted(required_names - visible_names),
            "timeline_label_fit": dict(timeline_debug.get("label_fit") or {}),
        }

    def _required_experiment_control_widget_names(self) -> set[str]:
        names = {
            "part_selector_widget",
            "block_plan_widget",
            "timeline_status_widget",
            "tactile_timeline_widget",
        }
        if hasattr(self, "topup_draft_widget") and self._topup_draft_should_show():
            names.add("topup_draft_widget")
        return names

    def _refresh_experiment_control_minimum_height(self) -> None:
        if not hasattr(self, "processing_panel"):
            return
        content_min = self._experiment_control_content_minimum_height()
        target = max(
            int(getattr(self.layout_profile, "experiment_control_min_height", 0) or 0),
            int(getattr(self.layout_profile, "experiment_control_content_min_height", 0) or 0),
            content_min,
        )
        self.experiment_control_content_min_height = content_min
        if int(self.processing_panel.minimumHeight()) != int(target):
            self.processing_panel.setMinimumHeight(int(target))
            self.processing_panel.updateGeometry()
        self._clamp_workspace_splitter_for_experiment_control()

    def _refresh_timeline_min_height(self) -> None:
        if not hasattr(self, "tactile_timeline_widget"):
            return
        target = _timeline_widget_minimum_height(self.layout_profile)
        if int(self.tactile_timeline_widget.minimumHeight()) != int(target):
            self.tactile_timeline_widget.setMinimumHeight(int(target))
            self.tactile_timeline_widget.updateGeometry()
        self._refresh_experiment_control_minimum_height()

    def _standard_plan_items(self) -> list[dict[str, Any]]:
        return [dict(item) for item in list(getattr(self, "all_block_plan_items", []) or []) if str(item.get("kind") or "") == "standard"]

    def _instruction_slots_for_item(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        if str(item.get("kind") or "") != "standard":
            return []
        enabled_slots = _enabled_instruction_slots(self.package)
        by_slot = {str(slot.get("slot") or ""): dict(slot) for slot in enabled_slots}
        standard_items = self._standard_plan_items()
        numbers = [int(entry.get("number") or 0) for entry in standard_items]
        item_number = int(item.get("number") or 0)
        index = numbers.index(item_number) if item_number in numbers else -1
        next_item = standard_items[index + 1] if 0 <= index < len(standard_items) - 1 else None
        relevant: list[str] = []
        if index == 0:
            relevant.append("before_experiment")
        relevant.append("before_each_block")
        relevant.append("after_each_block")
        if next_item is not None and str(next_item.get("part_key") or "") != str(item.get("part_key") or ""):
            relevant.append("between_conditions")
        if index == len(standard_items) - 1:
            relevant.append("after_experiment")
        return [by_slot[slot] for slot in relevant if slot in by_slot]

    def _timeline_instruction_segments_for_item(self, item: dict[str, Any], *, duration_s: float) -> list[dict[str, Any]]:
        slots = self._instruction_slots_for_item(item)
        if not slots:
            return []
        duration = max(0.001, float(duration_s or 0.001))
        leading_slots = [slot for slot in slots if str(slot.get("slot") or "") in {"before_experiment", "before_each_block"}]
        trailing_slots = [slot for slot in slots if str(slot.get("slot") or "") not in {"before_experiment", "before_each_block"}]
        width = min(duration * 0.08, max(0.4, duration / max(8.0, len(slots) * 3.0)))
        gap = min(duration * 0.015, 0.25)
        segments: list[dict[str, Any]] = []
        cursor = 0.0
        for slot in leading_slots:
            start = cursor
            end = min(duration, start + width)
            segments.append(
                {
                    "slot": slot.get("slot", ""),
                    "label": slot.get("display_label") or slot.get("label") or "Instruction",
                    "start_s": start,
                    "end_s": end,
                    "color": slot.get("color") or _instruction_slot_color(str(slot.get("slot") or "")),
                }
            )
            cursor = end + gap
        cursor = max(0.0, duration - (len(trailing_slots) * width + max(0, len(trailing_slots) - 1) * gap))
        for slot in trailing_slots:
            start = cursor
            end = min(duration, start + width)
            segments.append(
                {
                    "slot": slot.get("slot", ""),
                    "label": slot.get("display_label") or slot.get("label") or "Instruction",
                    "start_s": start,
                    "end_s": end,
                    "color": slot.get("color") or _instruction_slot_color(str(slot.get("slot") or "")),
                }
            )
            cursor = end + gap
        return segments

    def _set_instruction_plan_for_item(self, item: dict[str, Any] | None) -> None:
        self.instruction_plan_items = self._instruction_slots_for_item(item or {}) if item else _enabled_instruction_slots(self.package)
        if hasattr(self, "instruction_legend_widget"):
            refresh_height = getattr(self.instruction_legend_widget, "refresh_layout_height", None)
            if callable(refresh_height):
                refresh_height()
            self.instruction_legend_widget.update()
        if hasattr(self, "block_plan_widget"):
            refresh_height = getattr(self.block_plan_widget, "refresh_layout_height", None)
            if callable(refresh_height):
                refresh_height()
            self.block_plan_widget.update()

    def _select_default_block_preview(self) -> None:
        if self._run_active:
            return
        for item in self.block_plan_items:
            if str(item.get("kind") or "") == "standard":
                self._select_block_plan_item(int(item.get("number") or 0))
                return
        if self.block_plan_items:
            self._select_block_plan_item(int(self.block_plan_items[0].get("number") or 0))

    def _block_for_plan_item(self, item: dict[str, Any]) -> Any | None:
        block_index = item.get("block_index")
        if block_index in (None, ""):
            return None
        try:
            target_index = int(block_index)
        except (TypeError, ValueError):
            return None
        for block in getattr(self.package, "blocks", []) or []:
            try:
                if int(getattr(block, "index", -1)) == target_index:
                    return block
            except (TypeError, ValueError):
                continue
        return None

    def _block_preview_schedule(self, block: Any) -> BlockEventSchedule:
        metadata = _block_metadata(block)
        sample_rate_value = _float_or_none(metadata.get("sample_rate_hz"))
        sample_rate = int(sample_rate_value) if sample_rate_value is not None and sample_rate_value > 0 else 0
        trial_count = max(1, int(getattr(block, "trial_count", 0) or 0))
        trial_duration_s = max(0.001, float(getattr(block, "duration_s", 0.0) or 0.0) / trial_count)
        return BlockEventSchedule.from_block_manifest(
            getattr(block, "manifest_path", ""),
            block_index=int(getattr(block, "index", 0) or 0),
            block_label=str(getattr(block, "label", "") or ""),
            block_wav_path=getattr(block, "wav_path", ""),
            participant_id=str(getattr(self.package, "participant_id", "") or ""),
            session_id=str(getattr(self.package, "session_id", "") or ""),
            part_number=_block_part_key(block),
            sample_rate=sample_rate,
            block_metadata=metadata,
            trial_duration_s=trial_duration_s,
        )

    def _clear_block_preview(self, *, selected: int | None = None) -> None:
        self.preview_display_block_index = None
        self.timeline_preview_state.clear()
        self.selected_display_block_index = selected
        self._set_instruction_plan_for_item(self._run_plan_item_by_number(selected or 0) if selected else None)
        if hasattr(self, "block_preview_label"):
            if selected:
                item = self._run_plan_item_by_number(selected)
                display = item.get("display_label") if item else f"Block {selected}"
                self.block_preview_label.setText(f"Block preview: live {display}")
            else:
                self.block_preview_label.setText("Block preview: live schedule")
        if hasattr(self, "block_plan_widget"):
            self.block_plan_widget.update()
        if hasattr(self, "tactile_timeline_widget"):
            self.tactile_timeline_widget.update()
        self._refresh_topup_draft_widget()

    def _select_block_plan_item(self, display_number: int) -> None:
        number = int(display_number or 0)
        if number <= 0:
            return
        item = self._run_plan_item_by_number(number)
        if item is None:
            return
        self.selected_part_key = str(item.get("part_key") or self._ensure_selected_part_key())
        self._refresh_part_controls()
        self.selected_display_block_index = number
        if self.active_display_block_index == number:
            self._clear_block_preview(selected=number)
            self._refresh_topup_draft_widget()
            return

        kind = str(item.get("kind") or "")
        if kind == "topup":
            self.preview_display_block_index = number
            self.timeline_preview_state.clear()
            self._set_instruction_plan_for_item(item)
            part_label = _part_display_label(str(item.get("part_key") or ""))
            draft_count = len(self._visible_topup_draft_items())
            draft_text = f" | {draft_count} missed trial(s) in draft" if draft_count else " | waiting for missed trials"
            self.block_preview_label.setText(
                f"Block preview: {item.get('display_label', 'Top-up')} | {part_label} missed tactile trials{draft_text}"
            )
            self.block_plan_widget.update()
            self._refresh_topup_draft_widget()
            self.tactile_timeline_widget.update()
            return

        block = self._block_for_plan_item(item)
        if block is None:
            self.preview_display_block_index = number
            self.timeline_preview_state.clear()
            self._set_instruction_plan_for_item(item)
            self.block_preview_label.setText(f"Block preview: Block {number} schedule unavailable")
            self.block_plan_widget.update()
            self._refresh_topup_draft_widget()
            self.tactile_timeline_widget.update()
            return

        try:
            schedule = self._block_preview_schedule(block)
            tactile_events = _timeline_tactile_events(schedule)
            trial_segments = _timeline_trial_segments(schedule)
        except Exception as exc:
            self.preview_display_block_index = number
            self.timeline_preview_state.clear()
            self.block_preview_label.setText(f"Block preview: Block {number} unavailable ({exc})")
            self.block_plan_widget.update()
            self._refresh_topup_draft_widget()
            self.tactile_timeline_widget.update()
            return

        duration_s = float(getattr(block, "duration_s", 0.0) or 0.0)
        if duration_s <= 0 and trial_segments:
            duration_s = max(float(segment.get("end_s") or 0.0) for segment in trial_segments)
        self.timeline_preview_state.load_block(
            part_number=_block_part_key(block),
            phase_label=str(_block_metadata(block).get("phase_label") or _block_metadata(block).get("phase") or ""),
            block_index=getattr(block, "index", ""),
            block_label=str(getattr(block, "label", "") or f"Block {number}"),
            duration_s=max(0.001, duration_s),
            instruction_segments=self._timeline_instruction_segments_for_item(item, duration_s=max(0.001, duration_s)),
            tactile_events=tactile_events,
            trial_segments=trial_segments,
        )
        self.preview_display_block_index = number
        self._set_instruction_plan_for_item(item)
        self.block_preview_label.setText(
            f"Block preview: {item.get('display_label', f'Block {number}')} | {len(trial_segments)} trials | {len(tactile_events)} tactile cues"
        )
        self.block_plan_widget.update()
        self._refresh_topup_draft_widget()
        self.tactile_timeline_widget.update()

    def _step_participant_selection(self, delta: int) -> None:
        if not hasattr(self, "participant_code_combo"):
            return
        combo = self.participant_code_combo
        count = combo.count()
        if count <= 0:
            return
        current_index = combo.currentIndex()
        next_index = max(0, min(count - 1, current_index + int(delta or 0)))
        if next_index != current_index:
            combo.setCurrentIndex(next_index)
        self._refresh_participant_step_buttons()

    def _refresh_participant_step_buttons(self) -> None:
        if not hasattr(self, "participant_code_combo"):
            return
        count = self.participant_code_combo.count()
        index = self.participant_code_combo.currentIndex()
        can_change = (
            count > 1
            and not self.demographics_submitted
            and not self._run_active
            and self.controller is None
            and not (self.thread is not None and self.thread.is_alive())
        )
        if hasattr(self, "participant_decrement_button"):
            self.participant_decrement_button.setEnabled(can_change and index > 0)
        if hasattr(self, "participant_increment_button"):
            self.participant_increment_button.setEnabled(can_change and 0 <= index < count - 1)
        self._set_tactile_calibration_button_enabled()

    def _participant_ledger_entry_for(self, participant_id: str) -> dict[str, Any]:
        entry = participant_ledger_entry(self.output_root, participant_id)
        if not entry:
            return {}
        current_run_setup = str(getattr(self.package, "source_run_setup_manifest_path", "") or "")
        entry_run_setup = str(entry.get("run_setup_manifest_path") or "")
        if current_run_setup and entry_run_setup:
            try:
                if Path(current_run_setup).resolve() != Path(entry_run_setup).resolve():
                    return {}
            except Exception:
                if current_run_setup != entry_run_setup:
                    return {}
        return entry

    def _apply_participant_ledger_to_fields(self, participant_id: str | None = None) -> bool:
        if not hasattr(self, "participant_name_input"):
            return False
        participant = str(participant_id or self._selected_participant_code() or self.package.participant_id or "").strip()
        entry = self._participant_ledger_entry_for(participant)
        if not entry:
            return False
        self.participant_name_input.setText(str(entry.get("participant_name") or ""))
        self.age_input.setText(str(entry.get("age_years") or ""))
        _set_combo_data(self.handedness_combo, str(entry.get("handedness") or ""))
        _set_combo_data(self.gender_combo, str(entry.get("gender") or ""))
        self.include_name_lsl_checkbox.setChecked(bool(entry.get("include_name_in_lsl", False)))
        return True

    def _save_participant_ledger_entry(self, runner_metadata: dict[str, Any]) -> Path:
        participant = str(runner_metadata.get("participant_code") or self.package.participant_id or "").strip()
        if not participant:
            raise ValueError("Participant code is required for the setup ledger.")
        ledger = load_participant_ledger(self.output_root)
        participants = dict(ledger.get("participants") or {})
        now = datetime.now().isoformat(timespec="seconds")
        participants[participant] = {
            "participant_id": participant,
            "participant_name": str(runner_metadata.get("participant_name") or ""),
            "age_years": str(runner_metadata.get("age_years") or ""),
            "handedness": str(runner_metadata.get("handedness") or ""),
            "gender": str(runner_metadata.get("gender") or ""),
            "include_name_in_lsl": bool(runner_metadata.get("include_name_in_lsl")),
            "tactile_calibration": _json_ready(runner_metadata.get("tactile_calibration") or {}),
            "submitted_at": now,
            "updated_at": now,
            "session_id": str(getattr(self.package, "session_id", "") or ""),
            "session_manifest_path": str(getattr(self.package, "manifest_path", "") or ""),
            "run_setup_manifest_path": str(getattr(self.package, "source_run_setup_manifest_path", "") or ""),
        }
        ledger["participants"] = participants
        return save_participant_ledger(self.output_root, ledger)

    def _participant_data_summary(self, status: dict[str, Any]) -> str:
        inventory = str(status.get("part_inventory") or "").strip()
        if inventory:
            return inventory
        collection_state = str(status.get("data_collection_status") or "").strip()
        if bool(status.get("data_collected")) or collection_state == "collected":
            return "data collected"
        if collection_state == "incomplete":
            return "incomplete data exists"
        return "data not collected"

    def _refresh_participant_ledger_summary(self) -> None:
        if not hasattr(self, "participant_status_summary_label"):
            return
        participants = _package_participant_ids(self.package)
        statuses = self.participant_statuses or _package_participant_statuses(self.package, participants)
        selected = self._selected_participant_code() or str(getattr(self.package, "participant_id", "") or "").strip()
        status = statuses.get(selected, {})
        setup_text = "setup saved" if self._participant_ledger_entry_for(selected) else "setup not saved"
        calibration = load_latest_calibration(self.output_root, selected)
        if calibration:
            percent = _coerce_tactile_output_percent(
                calibration.get("recommended_output_34_percent", calibration["final_output_34_percent"])
            )
            calibration_text = f"tactile threshold {percent:g}%"
        else:
            calibration_text = "tactile threshold not calibrated"
        data_text = self._participant_data_summary(status)
        collected_others = [
            participant
            for participant in participants
            if participant != selected and bool(statuses.get(participant, {}).get("data_collected"))
        ]
        if collected_others:
            preview = ", ".join(collected_others[:4])
            if len(collected_others) > 4:
                preview = f"{preview}, +{len(collected_others) - 4}"
            other_text = f"Other completed: {preview}."
        else:
            other_text = "No other completed data."
        self.participant_status_summary_label.setText(f"{selected}: {setup_text}; {calibration_text}; {data_text}. {other_text}")

    def _populate_participant_code_combo(self, preferred: str = "") -> None:
        if not hasattr(self, "participant_code_combo"):
            return
        participants = _package_participant_ids(self.package)
        statuses = _package_participant_statuses(self.package, participants)
        self.participant_statuses = statuses
        current = str(preferred or getattr(self.package, "participant_id", "") or "").strip()
        self._participant_combo_updating = True
        try:
            self.participant_code_combo.blockSignals(True)
            self.participant_code_combo.clear()
            for participant in participants:
                clean_participant = str(participant or "").strip()
                if not clean_participant:
                    continue
                status = statuses.get(clean_participant, {})
                item_index = self.participant_code_combo.count()
                self.participant_code_combo.addItem(
                    profile_participant_dropdown_label(clean_participant, status),
                    clean_participant,
                )
                tooltip = str(
                    status.get("data_collection_message")
                    or status.get("message")
                    or "Participant profile from this run setup."
                )
                self.participant_code_combo.setItemData(
                    item_index,
                    tooltip,
                    self.q["Qt"].ItemDataRole.ToolTipRole,
                )
                if status.get("data_collected"):
                    self.participant_code_combo.setItemData(
                        item_index,
                        self.q["QBrush"](self.q["QColor"]("#15803d")),
                        self.q["Qt"].ItemDataRole.ForegroundRole,
                    )
            index = self.participant_code_combo.findData(current)
            self.participant_code_combo.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.participant_code_combo.blockSignals(False)
            self._participant_combo_updating = False
        self._refresh_participant_step_buttons()
        self._refresh_participant_ledger_summary()

    def _selected_participant_code(self) -> str:
        if hasattr(self, "participant_code_combo"):
            selected = str(self.participant_code_combo.currentData() or "").strip()
            if selected:
                return selected
        return str(getattr(self.package, "participant_id", "") or "").strip()

    def _participant_selection_changed(self, _index: int) -> None:
        if self._participant_combo_updating:
            return
        selected = self._selected_participant_code()
        current = str(getattr(self.package, "participant_id", "") or "").strip()
        if not selected or selected == current:
            self._refresh_participant_step_buttons()
            self._refresh_participant_ledger_summary()
            return
        if self._run_active or self.controller is not None or (self.thread is not None and self.thread.is_alive()):
            if hasattr(self, "event_label"):
                self.event_label.setText("Participant can be changed before starting a run.")
            self._populate_participant_code_combo(current)
            return
        self._switch_participant_package(selected)

    def _switch_participant_package(self, participant_id: str) -> None:
        selected = str(participant_id or "").strip()
        current = str(getattr(self.package, "participant_id", "") or "").strip()
        run_setup = getattr(self.package, "source_run_setup_manifest_path", None)
        if not selected or selected == current:
            self._populate_participant_code_combo(current)
            return
        if not run_setup:
            self.event_label.setText("Participant switching needs a Segment 6 run setup source.")
            self._populate_participant_code_combo(current)
            return
        run_setup_path = Path(run_setup)
        if not run_setup_path.exists():
            self.event_label.setText(f"Participant switching unavailable: setup missing at {run_setup_path}")
            self._populate_participant_code_combo(current)
            return

        app = self.q["QApplication"].instance()

        def _set_progress(message: str) -> None:
            if hasattr(self, "event_label"):
                self.event_label.setText(message)
            if app is not None:
                app.processEvents()

        def _progress(payload: dict[str, Any]) -> None:
            message = str(payload.get("message") or "Preparing participant package")
            _set_progress(f"{selected}: {message}")

        _set_progress(f"Loading participant {selected}")
        try:
            self.q["QApplication"].setOverrideCursor(self.q["QCursor"](self.q["Qt"].CursorShape.WaitCursor))
            manifest_path = claim_prepared_session(
                run_setup_path,
                selected,
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                session_root=self.output_root,
            )
            if manifest_path is None:
                status = prepared_session_asset_status(
                    run_setup_path,
                    selected,
                    state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                    session_root=self.output_root,
                )
                existing_manifest = str(status.get("session_manifest_path") or "").strip()
                if bool(status.get("generated")) and existing_manifest:
                    manifest_path = Path(existing_manifest)
            if manifest_path is not None:
                package = load_run_package(manifest_path)
            else:
                package = prepare_segment_run_package(
                    run_setup_path,
                    selected,
                    session_root=self.output_root,
                    progress_callback=_progress,
                )
                record_prepared_session_queue(
                    participant_id=selected,
                    run_setup_manifest_path=run_setup_path,
                    session_manifest_path=package.manifest_path,
                    status="ready",
                    message="Prepared by Experiment Runner participant switch.",
                    state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                )
        except Exception as exc:
            self.event_label.setText(f"Could not load participant {selected}: {exc}")
            self._populate_participant_code_combo(current)
            return
        finally:
            try:
                self.q["QApplication"].restoreOverrideCursor()
            except Exception:
                pass

        self._replace_loaded_package(package, message=f"Participant {package.participant_id} ready")
        _append_output_diary_event(
            "participant_switched",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"previous_participant_id": current, "selected_participant_id": self.package.participant_id},
            create=True,
        )

    def _replace_loaded_package(self, package: Any, *, message: str = "") -> None:
        self.package = package
        self.output_root = _package_output_root(package)
        self.result = None
        self.exit_code = 1
        self.pending_instruction_request = None
        self.pending_topup_approval_request = None
        self.thread = None
        self.messages = queue.Queue()
        self._clear_participant_details()
        self._refresh_loaded_package_display()
        self._populate_participant_code_combo(self.package.participant_id)
        self._apply_participant_ledger_to_fields(self.package.participant_id)
        self._refresh_companion_pairing_payload()
        if hasattr(self, "mode_tabs"):
            self._set_experiment_control_tab_ready(False)
            self.mode_tabs.setCurrentIndex(self.data_logging_tab_index)
        if hasattr(self, "timer") and not self.timer.isActive():
            self.timer.start(100)
        if message and hasattr(self, "event_label"):
            self.event_label.setText(message)
        self._apply_latest_tactile_calibration(self.package.participant_id, show_message=False)
        self._refresh_participant_ledger_summary()
        self._set_tactile_calibration_button_enabled()
        _append_output_diary_event(
            "runner_part_package_loaded",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"message": message},
            create=True,
        )

    def _clear_participant_details(self) -> None:
        self.demographics_submitted = False
        self._set_experiment_control_tab_ready(False)
        self.start_button.setEnabled(False)
        self._release_prepared_controller()
        if hasattr(self, "participant_name_input"):
            self.participant_name_input.clear()
        if hasattr(self, "age_input"):
            self.age_input.clear()
        if hasattr(self, "include_name_lsl_checkbox"):
            self.include_name_lsl_checkbox.setChecked(False)
        for combo_name in ("handedness_combo", "gender_combo"):
            combo = getattr(self, combo_name, None)
            if combo is not None:
                combo.setCurrentIndex(0)
        if hasattr(self, "setup_submit_button"):
            self.setup_submit_button.setEnabled(True)
            self._set_setup_status_message("Submit setup to unlock start controls.")

    def _refresh_loaded_package_display(self) -> None:
        profile = self.layout_profile
        participant_label = (
            f"ID {self.package.participant_id}" if profile.compact else f"Participant {self.package.participant_id}"
        )
        self.dialog.setWindowTitle(f"PPS Experiment Runner - {self.package.participant_id}")
        self.participant_chip.setText(participant_label)
        self.participant_chip.setToolTip(f"Participant {self.package.participant_id}")
        self.part_chip.setText("Part -")
        self.run_state_chip.setText("Ready")
        self.timeline_state.clear()
        self._timeline_perf_anchor = None
        self.planned_tactile_cue_count = 0
        self.topup_draft_items = []
        self._last_topup_completion = {}
        self.active_display_block_index = None
        self._clear_block_preview()
        self.completed_display_block_indices.clear()
        self.recenter_records.clear()
        self.progress.setValue(0)
        self.progress_label.setText("Waiting to start")
        self.prewarm_label.setText("Next participant: idle")
        self._prewarm_started = False
        self._prewarm_thread = None
        self.output_summary.setPlainText("Session outputs will appear here after the run.")
        self.session_participant_value.setText(self.package.participant_id)
        self.session_duration_value.setText(_format_duration(_package_duration(self.package)))
        instruction_summary = _instruction_profile_summary(self.package)
        if profile.compact:
            instruction_summary = instruction_summary.replace(" clip(s) preloaded", " clips")
        self.session_instruction_value.setText(instruction_summary)
        self.session_value.setText(self.package.session_id)
        self.session_value.setToolTip(f"Session: {self.package.session_id}\nFolder: {self.package.session_dir}")
        if self.folder_value is not None:
            self.folder_value.setText(_short_folder_label(self.package.session_dir))
            self.folder_value.setToolTip(str(self.package.session_dir))
        if hasattr(self, "backup_recording_checkbox"):
            self.backup_recording_checkbox.setText(_backup_recording_checkbox_text(self.package))
        if hasattr(self, "wired_loopback_checkbox"):
            self.wired_loopback_checkbox.setText(_wired_loopback_checkbox_text())
        self._refresh_run_plan(select_default=True)
        self._update_tactile_timeline_display()
        self._apply_participant_ledger_to_fields(self.package.participant_id)
        self._refresh_participant_ledger_summary()

    def _topup_slots_enabled_for_plan(self) -> bool:
        if hasattr(self, "topup_checkbox"):
            try:
                return bool(self.topup_checkbox.isChecked())
            except Exception:
                pass
        return bool(self.enable_missed_trial_topup)

    def _refresh_run_plan(self, *, select_default: bool = False) -> None:
        include_topup_slots = self._topup_slots_enabled_for_plan()
        standard_count = sum(1 for block in self.package.blocks if not _is_topup_block(block))
        topup_slots = sum(1 for item in _run_plan_items(self.package, include_topup_slots=include_topup_slots) if item["kind"] == "topup")
        total_count = _run_plan_total(self.package, include_topup_slots=include_topup_slots)
        plan_text = _run_plan_text(self.package, include_topup_slots=include_topup_slots)
        if hasattr(self, "run_plan_value"):
            display_plan = _run_plan_compact_text(self.package, include_topup_slots=include_topup_slots) if self.layout_profile.compact else plan_text
            self.run_plan_value.setText(display_plan)
            self.run_plan_value.setToolTip(plan_text)
        self.all_block_plan_items = _run_plan_items(self.package, include_topup_slots=include_topup_slots)
        self._refresh_part_controls()
        self.block_plan_items = self._visible_plan_items()
        if hasattr(self, "block_plan_widget"):
            refresh_height = getattr(self.block_plan_widget, "refresh_layout_height", None)
            if callable(refresh_height):
                refresh_height()
            self.block_plan_widget.update()
        self._refresh_timeline_min_height()
        if hasattr(self, "topup_draft_widget"):
            self._refresh_topup_draft_widget()
        if hasattr(self, "session_blocks_value"):
            if topup_slots:
                self.session_blocks_value.setText(f"{total_count} ({standard_count} standard + {topup_slots} top-up)")
            else:
                self.session_blocks_value.setText(str(standard_count))
        if hasattr(self, "block_chip") and not self._run_active:
            self.block_chip.setText(f"Block -/{len(self.block_plan_items) or total_count}")
        if self.selected_display_block_index is not None:
            valid_numbers = {int(item.get("number") or 0) for item in self.block_plan_items}
            if self.selected_display_block_index not in valid_numbers:
                self._clear_block_preview()
                select_default = True
        if select_default:
            self._select_default_block_preview()
        if not self.block_plan_items:
            self._set_instruction_plan_for_item(None)
        self._refresh_experiment_control_minimum_height()

    def _runtime_capture_options(self) -> SessionCaptureOptions:
        start_external_labrecorder = bool(
            self.capture_options.enable_lsl and self.external_labrecorder_checkbox.isChecked()
        )
        external_scope = EXTERNAL_LABRECORDER_SCOPE_PART
        if start_external_labrecorder and (
            self._continuous_external_labrecorder_state is not None
            or (_package_is_split_part(self.package) and self._next_split_part_manifest() is not None)
        ):
            external_scope = EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP
        return SessionCaptureOptions(
            enable_lsl=bool(self.capture_options.enable_lsl),
            write_events_csv=True,
            write_internal_xdf=bool(self.capture_options.write_internal_xdf),
            write_analysis_csvs=bool(self.capture_options.write_analysis_csvs),
            write_lsl_marker_mirror=True,
            write_trigger_dictionary=True,
            start_backup_recording=bool(self.backup_recording_checkbox.isChecked()),
            wired_loopback_mode=(
                WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY
                if bool(self.wired_loopback_checkbox.isChecked())
                else WIRED_LOOPBACK_OFF
            ),
            start_external_labrecorder=start_external_labrecorder,
            external_labrecorder_scope=external_scope,
            external_labrecorder_cli=str(self.capture_options.external_labrecorder_cli or ""),
            external_labrecorder_stream_timeout_s=float(self.capture_options.external_labrecorder_stream_timeout_s),
            external_labrecorder_startup_s=float(self.capture_options.external_labrecorder_startup_s),
            external_labrecorder_stop_timeout_s=float(self.capture_options.external_labrecorder_stop_timeout_s),
        )

    def _output_channel_volume_payload(self) -> dict[str, Any]:
        return _output_channel_volume_payload(
            self.output_12_volume_percent,
            self.output_34_volume_percent,
        )

    def _apply_output_volumes_to_engine(self, engine: Any | None) -> None:
        if engine is None:
            return
        audio_gain = _output_volume_gain(self.output_12_volume_percent)
        tactile_gain = _output_volume_gain(self.output_34_volume_percent, maximum=TACTILE_OUTPUT_34_MAX_PERCENT)
        setter = getattr(engine, "set_main_volume", None)
        if callable(setter):
            try:
                setter(audio_gain)
            except Exception:
                setattr(engine, "audio_volume", audio_gain)
        else:
            setattr(engine, "audio_volume", audio_gain)
        setattr(engine, "tactile_volume", tactile_gain)

    def _set_output_volume(self, target: str, value: float, *, persist: bool = True) -> None:
        percent = _coerce_tactile_output_percent(value) if target == "output_3_4" else _coerce_volume_percent(value)
        if target == "output_1_2":
            self.output_12_volume_percent = percent
            if hasattr(self, "output_12_volume_slider"):
                previous = self.output_12_volume_slider.blockSignals(True)
                self.output_12_volume_slider.setValue(_volume_percent_to_slider_value(percent))
                self.output_12_volume_slider.blockSignals(previous)
            if hasattr(self, "output_12_volume_percent_box"):
                previous = self.output_12_volume_percent_box.blockSignals(True)
                self.output_12_volume_percent_box.setValue(percent)
                self.output_12_volume_percent_box.blockSignals(previous)
        elif target == "output_3_4":
            self.output_34_volume_percent = percent
            if hasattr(self, "output_34_volume_slider"):
                previous = self.output_34_volume_slider.blockSignals(True)
                self.output_34_volume_slider.setValue(
                    _volume_percent_to_slider_value(percent, maximum=TACTILE_OUTPUT_34_MAX_PERCENT)
                )
                self.output_34_volume_slider.blockSignals(previous)
            if hasattr(self, "output_34_volume_percent_box"):
                previous = self.output_34_volume_percent_box.blockSignals(True)
                self.output_34_volume_percent_box.setValue(percent)
                self.output_34_volume_percent_box.blockSignals(previous)
        self._apply_output_volumes_to_engine(self._owned_audio_engine)
        controller_engine = getattr(self.controller, "audio_engine", None) if self.controller is not None else None
        if controller_engine is not self._owned_audio_engine:
            self._apply_output_volumes_to_engine(controller_engine)
        if persist:
            _persist_output_channel_volumes(
                self.output_12_volume_percent,
                self.output_34_volume_percent,
            )

    def _set_output_test_buttons_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled) and not self._run_active and not self._output_test_active and not self._tactile_calibration_active
        for button_name in ("test_audio_button", "test_tactile_button"):
            button = getattr(self, button_name, None)
            if button is not None:
                button.setEnabled(enabled)
        self._set_tactile_calibration_button_enabled()

    def _set_output_level_controls_enabled(self, enabled: bool) -> None:
        for control_name in (
            "output_12_volume_slider",
            "output_12_volume_percent_box",
            "output_34_volume_slider",
            "output_34_volume_percent_box",
        ):
            control = getattr(self, control_name, None)
            if control is not None:
                control.setEnabled(bool(enabled))
        self._set_output_test_buttons_enabled(bool(enabled))

    def _window_geometry_payload(self, geometry: Any | None = None) -> dict[str, int]:
        rect = geometry if geometry is not None else self.dialog.geometry()
        return {
            "x": int(rect.x()),
            "y": int(rect.y()),
            "width": int(rect.width()),
            "height": int(rect.height()),
        }

    def _experiment_window_lock_snapshot(self) -> dict[str, Any]:
        locked_geometry = self._experiment_window_locked_geometry
        payload: dict[str, Any] = {
            "active": bool(self._experiment_window_locked),
            "current_geometry": self._window_geometry_payload(),
        }
        if locked_geometry is not None:
            payload["locked_geometry"] = self._window_geometry_payload(locked_geometry)
        if self._experiment_window_locked_window_state is not None:
            payload["locked_window_state"] = str(self._experiment_window_locked_window_state)
        return payload

    def _lock_experiment_window_geometry(self) -> None:
        if self._experiment_window_locked:
            self._restore_locked_experiment_window_geometry()
            return
        self._experiment_window_locked_geometry = self.dialog.geometry()
        self._experiment_window_locked_window_state = self.dialog.windowState()
        self._experiment_window_previous_minimum_size = self.dialog.minimumSize()
        self._experiment_window_previous_maximum_size = self.dialog.maximumSize()
        self._experiment_window_locked = True
        if hasattr(self.dialog, "setSizeGripEnabled"):
            self.dialog.setSizeGripEnabled(False)
        self.dialog.setFixedSize(self._experiment_window_locked_geometry.size())
        self._restore_locked_experiment_window_geometry()
        _append_output_diary_event(
            "focus_window_geometry_locked",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload=self._experiment_window_lock_snapshot(),
            create=True,
        )

    def _restore_locked_experiment_window_geometry(self) -> None:
        if not self._experiment_window_locked or self._experiment_window_lock_restoring:
            return
        locked_geometry = self._experiment_window_locked_geometry
        if locked_geometry is None:
            return
        self._experiment_window_lock_restoring = True
        try:
            locked_state = self._experiment_window_locked_window_state
            if locked_state is not None and self.dialog.windowState() != locked_state:
                self.dialog.setWindowState(locked_state)
            if self.dialog.geometry() != locked_geometry:
                self.dialog.setGeometry(locked_geometry)
        finally:
            self._experiment_window_lock_restoring = False

    def _unlock_experiment_window_geometry(self) -> None:
        if not self._experiment_window_locked and self._experiment_window_previous_minimum_size is None:
            return
        self._experiment_window_locked = False
        self._experiment_window_lock_restoring = False
        previous_maximum = self._experiment_window_previous_maximum_size
        previous_minimum = self._experiment_window_previous_minimum_size
        if previous_maximum is not None:
            self.dialog.setMaximumSize(previous_maximum)
        if previous_minimum is not None:
            self.dialog.setMinimumSize(previous_minimum)
        if hasattr(self.dialog, "setSizeGripEnabled"):
            self.dialog.setSizeGripEnabled(True)
        self._experiment_window_locked_geometry = None
        self._experiment_window_locked_window_state = None
        self._experiment_window_previous_minimum_size = None
        self._experiment_window_previous_maximum_size = None

    def _output_test_engine(self) -> Any | None:
        controller_engine = getattr(self.controller, "audio_engine", None) if self.controller is not None else None
        engine = controller_engine or self._owned_audio_engine
        if engine is None:
            engine = self._create_real_audio_engine_on_ui_thread()
            self._owned_audio_engine = engine
        self._apply_output_volumes_to_engine(engine)
        return engine

    def _run_output_test(self, target: str) -> bool:
        target = str(target or "").strip().lower()
        if self._run_active or (self.thread is not None and self.thread.is_alive()):
            self.event_label.setText("Output tests are available before playback starts or after it ends.")
            return False
        if self._output_test_active:
            self.event_label.setText("Output test already playing.")
            return False
        if target == "audio":
            path = OUTPUT_TEST_AUDIO_PATH
            label = "Test Audio"
        elif target == "tactile":
            path = OUTPUT_TEST_TACTILE_PATH
            label = "Test Tactile"
        else:
            return False
        if not path.exists():
            self.event_label.setText(f"{label} asset missing: {path}")
            return False
        try:
            engine = self._output_test_engine()
        except Exception as exc:
            self.event_label.setText(f"{label} could not initialize audio: {exc}")
            return False
        if engine is None:
            self.event_label.setText(f"{label} could not initialize audio.")
            return False

        self._output_test_active = True
        self._set_output_test_buttons_enabled(False)
        self.event_label.setText(f"{label} playing")
        _append_output_diary_event(
            "output_test_started",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={
                "target": target,
                "asset_path": str(path),
                "playback_output_levels": self._output_channel_volume_payload(),
            },
            create=True,
        )

        def _finish(success: bool, message: str = "") -> None:
            self.messages.put(
                (
                    "output_test_done",
                    {
                        "target": target,
                        "label": label,
                        "success": bool(success),
                        "message": message,
                        "asset_path": str(path),
                    },
                )
            )

        if target == "audio":
            play_instruction = getattr(engine, "play_instruction", None)
            if not callable(play_instruction):
                _finish(False, "audio engine has no instruction playback API")
                return False
            try:
                returned = play_instruction(str(path), lambda success=True: _finish(bool(success)))
                if returned is False:
                    _finish(False, "audio engine rejected instruction playback")
                    return False
            except Exception as exc:
                _finish(False, str(exc))
                return False
            return True

        play_block = getattr(engine, "play_block", None)
        if not callable(play_block):
            _finish(False, "audio engine has no block playback API")
            return False

        def _play_tactile() -> None:
            try:
                _finish(bool(play_block(str(path))))
            except Exception as exc:
                _finish(False, str(exc))

        threading.Thread(target=_play_tactile, name="pps-output-tactile-test", daemon=True).start()
        return True

    def _handle_output_test_done(self, payload: dict[str, Any]) -> None:
        self._output_test_active = False
        self._set_output_test_buttons_enabled(True)
        label = str(payload.get("label") or "Output test")
        success = bool(payload.get("success"))
        message = str(payload.get("message") or "").strip()
        if success:
            self.event_label.setText(f"{label} complete")
        else:
            self.event_label.setText(f"{label} failed: {message or 'playback did not complete'}")
        _append_output_diary_event(
            "output_test_finished",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={
                "target": str(payload.get("target") or ""),
                "asset_path": str(payload.get("asset_path") or ""),
                "success": success,
                "message": message,
                "playback_output_levels": self._output_channel_volume_payload(),
            },
            create=True,
        )

    def _tactile_calibration_package_context(self) -> dict[str, Any]:
        return {
            "run_setup_manifest_path": str(getattr(self.package, "source_run_setup_manifest_path", "") or ""),
            "session_id": str(getattr(self.package, "session_id", "") or ""),
            "session_group_id": str(getattr(self.package, "session_group_id", "") or ""),
            "part_session_id": str(getattr(self.package, "part_session_id", "") or ""),
            "part_number": str(getattr(self.package, "part_number", "") or ""),
        }

    def _open_tactile_calibration_monitor(self, participant: str) -> None:
        existing = getattr(self, "tactile_calibration_monitor_dialog", None)
        if existing is not None:
            try:
                existing.close()
            except Exception:
                pass
        monitor = _create_tactile_calibration_monitor_dialog(self.q, self, participant)
        self.tactile_calibration_monitor_dialog = monitor
        def _clear_monitor_reference(_code: int, monitor_ref: Any = monitor) -> None:
            if getattr(self, "tactile_calibration_monitor_dialog", None) is monitor_ref:
                self.tactile_calibration_monitor_dialog = None

        try:
            monitor.finished.connect(_clear_monitor_reference)
        except Exception:
            pass
        monitor.show()
        try:
            monitor.raise_()
            monitor.activateWindow()
        except Exception:
            pass

    def _abort_tactile_calibration(self) -> None:
        if self._tactile_calibration_cancel_event is not None:
            self._tactile_calibration_cancel_event.set()
        self.event_label.setText("Tactile threshold assay abort requested.")
        monitor = getattr(self, "tactile_calibration_monitor_dialog", None)
        if monitor is not None:
            try:
                monitor.status_label.setText("Abort requested; waiting for the current trial to finish.")
                monitor.abort_button.setEnabled(False)
            except Exception:
                pass

    def _request_tactile_calibration_recenter_from_worker(self, payload: dict[str, Any]) -> dict[str, Any]:
        if threading.get_ident() == self._ui_thread_id:
            return self._move_cursor_to_tactile_calibration_target(payload)
        future: Future[dict[str, Any]] = Future()
        self.messages.put(("tactile_calibration_recenter", {"context": dict(payload), "future": future}))
        try:
            return dict(future.result(timeout=1.0))
        except Exception as exc:
            return {"mode": "recenter_timeout", "error": str(exc), **dict(payload)}

    def _return_from_successful_tactile_calibration(self) -> None:
        monitor = getattr(self, "tactile_calibration_monitor_dialog", None)
        if monitor is not None:
            try:
                monitor.accept()
            except Exception:
                try:
                    monitor.close()
                except Exception:
                    pass
            if getattr(self, "tactile_calibration_monitor_dialog", None) is monitor:
                self.tactile_calibration_monitor_dialog = None
        try:
            self.mode_tabs.setCurrentIndex(self.experiment_control_tab_index)
        except Exception:
            pass
        try:
            self.dialog.raise_()
            self.dialog.activateWindow()
        except Exception:
            pass
        focus_target = self.start_button if self.start_button.isEnabled() else self.tactile_calibration_button
        try:
            focus_target.setFocus()
        except Exception:
            pass

    def _run_tactile_calibration(self) -> bool:
        if not self._tactile_calibration_allowed():
            thread_alive = bool(self.thread is not None and self.thread.is_alive())
            if self._output_test_active:
                self.event_label.setText("Wait for the current output test before running the tactile threshold assay.")
            elif self._tactile_calibration_active:
                self.event_label.setText("Tactile threshold assay is already running.")
            elif self._run_active or thread_alive:
                self.event_label.setText("Tactile threshold assay is available before experiment playback starts.")
            else:
                self.event_label.setText("Select or submit a participant before running the tactile threshold assay.")
            return False
        try:
            engine = self._output_test_engine()
        except Exception as exc:
            self.event_label.setText(f"Tactile threshold assay could not initialize audio: {exc}")
            return False
        if engine is None:
            self.event_label.setText("Tactile threshold assay could not initialize audio.")
            return False
        participant = self._selected_participant_code() or self.package.participant_id
        cancel_event = threading.Event()
        self._tactile_calibration_cancel_event = cancel_event
        self._tactile_calibration_active = True
        self._set_output_test_buttons_enabled(False)
        self.target_button.setEnabled(True)
        self._refresh_target_global_bounds()
        self._open_tactile_calibration_monitor(participant)
        self._start_tactile_calibration_response_listener()
        self.event_label.setText(
            "Adaptive tactile threshold assay running: instruct participant to press the mouse when a tactile pulse is felt."
        )
        playback_before = self._output_channel_volume_payload()
        output_12_percent = self.output_12_volume_percent
        _append_output_diary_event(
            "tactile_calibration_started",
            package=self.package,
            participant_id=participant,
            capture_options=self.capture_options.as_dict(),
            payload={
                "protocol": TACTILE_CALIBRATION_PROTOCOL_NAME,
                "playback_output_levels_before": playback_before,
            },
            create=True,
        )

        def _progress(payload: dict[str, Any]) -> None:
            self.messages.put(("tactile_calibration_progress", dict(payload)))

        def _failure_report(message: str) -> dict[str, Any]:
            now = datetime.now().isoformat(timespec="seconds")
            return {
                "schema": CALIBRATION_SCHEMA,
                "participant_id": participant,
                "created_at": now,
                "completed_at": now,
                "protocol": TACTILE_CALIBRATION_PROTOCOL_NAME,
                "accepted": False,
                "status": "failed",
                "message": message,
                "final_output_34_percent": "",
                "detection_threshold_output_34_percent": "",
                "recommended_output_34_percent": "",
                "staircase_hit_rate": "",
                "staircase_false_alarm_rate": "",
                "staircase_summary": {},
                "adaptive_staircase": {},
                "validation_hit_rate": "",
                "validation_false_alarm_rate": "",
                "output_root": str(self.output_root),
                "playback_output_levels_before": playback_before,
                **self._tactile_calibration_package_context(),
            }

        def _worker() -> None:
            runner: TactileCalibrationRunner | None = None
            try:
                runner = TactileCalibrationRunner(
                    audio_engine=engine,
                    response_collector=self._tactile_calibration_collector,
                    participant_id=participant,
                    output_root=self.output_root,
                    source_pulse_path=TACTILE_CALIBRATION_SOURCE_PULSE_PATH,
                    current_output_34_percent=self.output_34_volume_percent,
                    playback_output_levels_before=playback_before,
                    package_context=self._tactile_calibration_package_context(),
                    progress_callback=_progress,
                    recenter_callback=self._request_tactile_calibration_recenter_from_worker,
                    cancel_event=cancel_event,
                )
                result = runner.run()
                report = dict(result.get("report") or {})
                trials = [dict(trial) for trial in list(result.get("trials") or [])]
            except Exception as exc:
                report = _failure_report(str(exc))
                trials = [] if runner is None else [dict(trial) for trial in runner.trials]
            if bool(report.get("accepted")):
                try:
                    final_percent = float(
                        report.get("recommended_output_34_percent", report.get("final_output_34_percent"))
                    )
                except (TypeError, ValueError):
                    final_percent = self.output_34_volume_percent
                report["playback_output_levels_after"] = _output_channel_volume_payload(output_12_percent, final_percent)
            else:
                report["playback_output_levels_after"] = playback_before
            try:
                paths = save_calibration_attempt(
                    output_root=self.output_root,
                    participant_id=participant,
                    report=report,
                    trials=trials,
                )
                path_payload = {key: str(value) for key, value in paths.items()}
            except Exception as exc:
                report["accepted"] = False
                report["status"] = "failed"
                report["message"] = f"{report.get('message') or 'Threshold assay failed'}; could not save artifacts: {exc}"
                path_payload = {}
            self.messages.put(
                (
                    "tactile_calibration_done",
                    {
                        "participant_id": participant,
                        "report": report,
                        "trials": trials,
                        "paths": path_payload,
                    },
                )
            )

        self._tactile_calibration_worker = threading.Thread(target=_worker, name="pps-tactile-calibration", daemon=True)
        self._tactile_calibration_worker.start()
        return True

    def _handle_tactile_calibration_progress(self, payload: dict[str, Any]) -> None:
        message = str(payload.get("message") or "Adaptive tactile threshold assay running")
        self.event_label.setText(message)
        monitor = getattr(self, "tactile_calibration_monitor_dialog", None)
        if str(payload.get("ui_event") or "") == "confirmation_update":
            if "next_level_percent" in payload:
                try:
                    self._set_output_volume("output_3_4", float(payload.get("next_level_percent")), persist=False)
                except Exception:
                    pass
            if monitor is not None:
                try:
                    monitor.update_confirmation(payload)
                except Exception:
                    pass
            return
        if str(payload.get("ui_event") or "") == "trial_complete":
            if monitor is not None:
                try:
                    monitor.finish_trial(payload)
                except Exception:
                    pass
            return
        if "level_percent" in payload:
            try:
                self._set_output_volume("output_3_4", float(payload.get("level_percent")), persist=False)
            except Exception:
                pass
        if monitor is not None:
            try:
                monitor.update_progress(payload)
            except Exception:
                pass

    def _handle_tactile_calibration_done(self, payload: dict[str, Any]) -> None:
        self._tactile_calibration_active = False
        self._tactile_calibration_cancel_event = None
        self._stop_tactile_calibration_response_listener()
        self._tactile_calibration_collector.finish_trial()
        self.target_button.setEnabled(False)
        self._set_output_level_controls_enabled(bool(self.demographics_submitted))
        participant = str(payload.get("participant_id") or self.package.participant_id)
        report = dict(payload.get("report") or {})
        paths = dict(payload.get("paths") or {})
        accepted = bool(report.get("accepted"))
        if accepted:
            try:
                final_percent = float(report.get("recommended_output_34_percent", report.get("final_output_34_percent")))
            except (TypeError, ValueError):
                final_percent = self.output_34_volume_percent
            self._set_output_volume("output_3_4", final_percent)
            latest = load_latest_calibration(self.output_root, participant)
            self._latest_tactile_calibration = dict(latest or {})
            ready_text = "Ready to start the experiment." if self.start_button.isEnabled() else "Submit setup to start the experiment."
            self.event_label.setText(
                f"{participant}: tactile calibration successful at {final_percent:g}% Output 3/4. {ready_text}"
            )
        else:
            message = str(report.get("message") or "threshold assay did not pass")
            self.event_label.setText(f"{participant}: tactile threshold failed - {message}")
            playback_before = dict(report.get("playback_output_levels_before") or {})
            if "output_3_4_percent" in playback_before:
                self._set_output_volume("output_3_4", playback_before.get("output_3_4_percent"))
        monitor = getattr(self, "tactile_calibration_monitor_dialog", None)
        if monitor is not None:
            try:
                monitor.finish_assay(report)
            except Exception:
                pass
        self._refresh_participant_ledger_summary()
        _append_output_diary_event(
            "tactile_calibration_finished",
            package=self.package,
            participant_id=participant,
            capture_options=self.capture_options.as_dict(),
            payload={
                "accepted": accepted,
                "status": str(report.get("status") or ""),
                "message": str(report.get("message") or ""),
                "final_output_34_percent": report.get("final_output_34_percent", ""),
                "detection_threshold_output_34_percent": report.get("detection_threshold_output_34_percent", ""),
                "recommended_output_34_percent": report.get("recommended_output_34_percent", ""),
                "staircase_summary": _json_ready(report.get("staircase_summary") or {}),
                "adaptive_staircase": _json_ready(report.get("adaptive_staircase") or {}),
                "confirmation_summary": _json_ready(report.get("confirmation_summary") or {}),
                "timing": _json_ready(report.get("timing") or {}),
                "report_path": str(paths.get("report_path") or report.get("report_path") or ""),
                "trials_csv_path": str(paths.get("trials_csv_path") or report.get("trials_csv_path") or ""),
                "latest_path": str(paths.get("latest_path") or ""),
            },
            create=True,
        )

    def _runner_metadata(self) -> dict[str, Any]:
        return {
            "participant_code": self._selected_participant_code() or self.package.participant_id,
            "participant_name": self.participant_name_input.text().strip(),
            "include_name_in_lsl": bool(self.include_name_lsl_checkbox.isChecked()),
            "age_years": self.age_input.text().strip(),
            "handedness": self.handedness_combo.currentData() or "",
            "gender": self.gender_combo.currentData() or "",
            "playback_output_levels": self._output_channel_volume_payload(),
            "tactile_calibration": self._current_tactile_calibration_metadata(),
        }

    def start_next_participant_prewarm(self) -> None:
        if self._prewarm_started:
            return
        self._prewarm_started = True
        run_setup = getattr(self.package, "source_run_setup_manifest_path", None)
        if not run_setup:
            self.prewarm_label.setText("Next participant: no Segment 6 setup")
            return
        run_setup_path = Path(run_setup)
        if not run_setup_path.exists():
            self.prewarm_label.setText("Next participant: setup missing")
            return
        try:
            next_participant = next_segment_participant(run_setup_path, self.package.participant_id)
        except Exception as exc:
            self.prewarm_label.setText(f"Next participant: unavailable ({exc})")
            return
        if not next_participant:
            self.prewarm_label.setText("Next participant: none")
            return
        self.prewarm_label.setText(f"Next {next_participant}: preparing")
        record_prepared_session_queue(
            participant_id=next_participant,
            run_setup_manifest_path=run_setup_path,
            status="preparing",
            message="Preparing in Focus Mode background worker.",
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
        )

        def _progress(payload: dict[str, Any]) -> None:
            self.messages.put(
                (
                    "prewarm_progress",
                    {
                        "participant_id": next_participant,
                        "message": str(payload.get("message") or "Preparing"),
                    },
                )
            )

        def _run() -> None:
            try:
                package = prepare_segment_run_package(
                    run_setup_path,
                    next_participant,
                    session_root=self.output_root,
                    progress_callback=_progress,
                )
            except Exception as exc:
                record_prepared_session_queue(
                    participant_id=next_participant,
                    run_setup_manifest_path=run_setup_path,
                    status="failed",
                    message=str(exc),
                    state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                )
                _append_output_diary_event(
                    "next_participant_prewarm_failed",
                    package=self.package,
                    participant_id=next_participant,
                    capture_options=self.capture_options.as_dict(),
                    payload={"message": str(exc), "run_setup_manifest_path": str(run_setup_path)},
                    create=True,
                )
                self.messages.put(("prewarm", {"participant_id": next_participant, "status": "failed", "message": str(exc)}))
            else:
                record_prepared_session_queue(
                    participant_id=next_participant,
                    run_setup_manifest_path=run_setup_path,
                    session_manifest_path=package.manifest_path,
                    status="ready",
                    message="Prepared by Focus Mode one-step-ahead queue.",
                    state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                )
                _append_output_diary_event(
                    "next_participant_prewarmed",
                    package=package,
                    capture_options=self.capture_options.as_dict(),
                    payload={"source": "focus_mode_background_worker"},
                    create=True,
                )
                self.messages.put(
                    (
                        "prewarm",
                        {
                            "participant_id": next_participant,
                            "status": "ready",
                            "message": str(package.manifest_path),
                        },
                    )
                )

        self._prewarm_thread = threading.Thread(target=_run, name="pps-next-participant-prewarm", daemon=True)
        self._prewarm_thread.start()

    def _freeze_pre_run_controls(self) -> None:
        for control in self._pre_run_controls:
            try:
                control.setEnabled(False)
            except Exception:
                pass

    def _participant_setup_failures(self) -> list[str]:
        failures: list[str] = []
        if not str(self.participant_name_input.text() or "").strip():
            failures.append("name")
        age_text = str(self.age_input.text() or "").strip()
        if not age_text:
            failures.append("age")
        else:
            try:
                age_value = float(age_text)
            except ValueError:
                failures.append("valid age")
            else:
                if age_value <= 0 or age_value > 120:
                    failures.append("valid age")
        if not str(self.handedness_combo.currentData() or "").strip():
            failures.append("handedness")
        if not str(self.gender_combo.currentData() or "").strip():
            failures.append("gender")
        return failures

    def _controller_lsl_status(self) -> Any:
        events = getattr(self.controller, "events", None)
        return getattr(events, "lsl_status", None)

    def _release_prepared_controller(self) -> None:
        controller = self.controller
        if controller is None:
            return
        events = getattr(controller, "events", None)
        close = getattr(events, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                pass
        self.controller = None

    def _handle_dialog_finished(self, _code: int) -> None:
        cancel_event = getattr(self, "_tactile_calibration_cancel_event", None)
        if cancel_event is not None:
            cancel_event.set()
        monitor = getattr(self, "tactile_calibration_monitor_dialog", None)
        if monitor is not None:
            try:
                monitor.close()
            except Exception:
                pass
            self.tactile_calibration_monitor_dialog = None
        self._stop_tactile_calibration_response_listener()
        self._stop_companion_service()
        self._remove_response_click_filter()
        self._stop_global_response_click_listener()
        self._stop()
        self._release_pending_operator_requests(source="runner_window_closed")
        self._close_external_labrecorder_for_runner_exit()
        if not (self.thread is not None and self.thread.is_alive()):
            self._release_prepared_controller()

    def _submit_participant_setup(self) -> bool:
        if self.demographics_submitted and self.controller is not None:
            self._set_setup_status_message("Setup submitted. Experiment Control is ready.")
            self._set_experiment_control_tab_ready(True, switch=True)
            return True
        failures = self._participant_setup_failures()
        if failures:
            self.event_label.setText(f"Complete participant setup: {', '.join(failures)}.")
            self._set_setup_status_message(f"Complete participant setup: {', '.join(failures)}.")
            return False
        self.capture_options = self._runtime_capture_options()
        self.enable_missed_trial_topup = bool(self.topup_checkbox.isChecked())
        self._refresh_run_plan()
        runner_metadata = self._runner_metadata()
        continuous_state = dict(self._continuous_external_labrecorder_state or {})
        lsl_stream_session_id = str(continuous_state.get("lsl_stream_session_id") or "")
        if not lsl_stream_session_id and self.capture_options.external_labrecorder_scope == EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP:
            lsl_stream_session_id = str(getattr(self.package, "session_group_id", "") or getattr(self.package, "session_id", ""))
        stop_external_labrecorder_on_run_end = True
        if (
            self.capture_options.external_labrecorder_scope == EXTERNAL_LABRECORDER_SCOPE_SESSION_GROUP
            and _package_is_split_part(self.package)
            and self._next_split_part_manifest() is not None
            and not continuous_state
        ):
            stop_external_labrecorder_on_run_end = False
        external_finalize_path = continuous_state.get("finalize_path") if continuous_state else None
        try:
            if self.controller_factory is not None:
                self.controller = self.controller_factory(
                    self.package,
                    capture_options=self.capture_options,
                    enable_topup=self.enable_missed_trial_topup,
                    runner_metadata=runner_metadata,
                    topup_approval_callback=self._auto_approve_topup_playback if self.enable_missed_trial_topup else None,
                    instruction_continue_callback=self._request_instruction_continue,
                )
            else:
                self.controller = SessionRunnerController(
                    self.package,
                    audio_engine=None,
                    capture_options=self.capture_options,
                    enable_topup=self.enable_missed_trial_topup,
                    runner_metadata=runner_metadata,
                    topup_approval_callback=self._auto_approve_topup_playback if self.enable_missed_trial_topup else None,
                    instruction_continue_callback=self._request_instruction_continue,
                    lsl_stream_session_id=lsl_stream_session_id or None,
                    shared_lsl_outlet=continuous_state.get("lsl_outlet") if continuous_state else None,
                    external_labrecorder_state=continuous_state or None,
                    external_labrecorder_stop_on_run_end=stop_external_labrecorder_on_run_end,
                    external_labrecorder_finalize_path=external_finalize_path,
                )
                if continuous_state:
                    self._continuous_external_labrecorder_state = None
        except Exception as exc:
            self.controller = None
            self.event_label.setText(f"Participant setup could not prepare LSL: {exc}")
            self._set_setup_status_message(f"Participant setup could not prepare LSL: {exc}")
            return False
        lsl_status = self._controller_lsl_status()
        if (
            bool(self.capture_options.enable_lsl)
            and hasattr(lsl_status, "enabled")
            and not bool(getattr(lsl_status, "enabled", False))
        ):
            message = str(getattr(lsl_status, "message", "LSL streams were not created.") or "LSL streams were not created.")
            self._release_prepared_controller()
            self.event_label.setText(f"Participant setup could not prepare LSL: {message}")
            self._set_setup_status_message(f"Participant setup could not prepare LSL: {message}")
            return False
        self.demographics_submitted = True
        self._apply_output_volumes_to_engine(getattr(self.controller, "audio_engine", None))
        self._freeze_pre_run_controls()
        self._set_tactile_calibration_button_enabled()
        self._refresh_part_controls()
        ledger_path_text = ""
        ledger_error = ""
        try:
            ledger_path_text = str(self._save_participant_ledger_entry(runner_metadata))
        except Exception as exc:
            ledger_error = str(exc)
        self._refresh_participant_step_buttons()
        self._refresh_participant_ledger_summary()
        self.start_button.setEnabled(True)
        self._refresh_start_button_label()
        self._set_experiment_control_tab_ready(True, switch=True)
        self.run_state_chip.setText("LSL Ready" if bool(self.capture_options.enable_lsl) else "Ready")
        lsl_message = str(getattr(lsl_status, "message", "") or "")
        event_message = lsl_message or "Participant setup submitted"
        if ledger_error:
            event_message = f"{event_message}; participant ledger not saved: {ledger_error}"
        self.event_label.setText(event_message)
        self._set_setup_status_message("Setup submitted. Experiment Control is ready.")
        _append_output_diary_event(
            "participant_setup_submitted",
            package=self.package,
            participant_id=str(runner_metadata.get("participant_code") or self.package.participant_id),
            capture_options=self.capture_options.as_dict(),
            payload={
                "lsl_enabled": bool(getattr(lsl_status, "enabled", False)) if lsl_status is not None else bool(self.capture_options.enable_lsl),
                "lsl_message": lsl_message,
                "topup_enabled": self.enable_missed_trial_topup,
                "playback_output_levels": self._output_channel_volume_payload(),
                "participant_ledger_path": ledger_path_text,
                "participant_ledger_saved": bool(ledger_path_text) and not ledger_error,
                "participant_ledger_error": ledger_error,
                "participant_metadata_fields": sorted(key for key, value in runner_metadata.items() if str(value or "").strip()),
            },
            create=True,
        )
        return True

    def _install_primary_action_shortcuts(self) -> None:
        q = self.q
        for sequence in ("Space", "Return", "Enter"):
            shortcut = q["QShortcut"](q["QKeySequence"](sequence), self.dialog)
            shortcut.setContext(q["Qt"].ShortcutContext.WindowShortcut)
            shortcut.activated.connect(self._handle_primary_action_shortcut)
            self.primary_action_shortcuts.append(shortcut)
        self._set_primary_action_shortcuts_enabled(True)

    def _set_primary_action_shortcuts_enabled(self, enabled: bool) -> None:
        for shortcut in getattr(self, "primary_action_shortcuts", []):
            try:
                shortcut.setEnabled(bool(enabled))
            except Exception:
                pass

    def keyboard_shortcut_map(self) -> dict[str, list[str]]:
        shortcuts = {
            "start_or_continue": ["Space", "Return", "Enter"],
            "pause_resume": ["Ctrl+P"],
            "close": ["Ctrl+W"],
            "select_part_1": ["Alt+1"],
            "select_part_2": ["Alt+2"],
            "select_topup_preview": ["Ctrl+T"],
        }
        if _env_flag("PPS_FOCUS_VALIDATION_ENABLE_SYNTHETIC_CLICK_SHORTCUT"):
            shortcuts["validation_synthetic_click"] = ["Ctrl+Alt+Shift+F12"]
        return shortcuts

    def _install_operator_action_shortcuts(self) -> None:
        q = self.q

        def _add(name: str, sequence: str, callback: Callable[[], None]) -> None:
            shortcut = q["QShortcut"](q["QKeySequence"](sequence), self.dialog)
            shortcut.setContext(q["Qt"].ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self.operator_action_shortcuts.setdefault(name, []).append(shortcut)

        for sequence in self.keyboard_shortcut_map()["pause_resume"]:
            _add("pause_resume", sequence, self._handle_pause_resume_shortcut)
        for sequence in self.keyboard_shortcut_map()["close"]:
            _add("close", sequence, self._handle_close_shortcut)
        for sequence in self.keyboard_shortcut_map()["select_part_1"]:
            _add("select_part_1", sequence, lambda key="1": self._handle_part_shortcut(key))
        for sequence in self.keyboard_shortcut_map()["select_part_2"]:
            _add("select_part_2", sequence, lambda key="2": self._handle_part_shortcut(key))
        for sequence in self.keyboard_shortcut_map()["select_topup_preview"]:
            _add("select_topup_preview", sequence, self._handle_topup_preview_shortcut)
        for sequence in self.keyboard_shortcut_map().get("validation_synthetic_click", []):
            _add("validation_synthetic_click", sequence, self._handle_validation_synthetic_click_shortcut)

    def _handle_pause_resume_shortcut(self) -> None:
        if self.pause_button.isEnabled():
            self._pause()
        elif self.resume_button.isEnabled():
            self._resume()

    def _handle_stop_shortcut(self) -> None:
        if self.stop_button.isEnabled():
            self._stop()

    def _handle_close_shortcut(self) -> None:
        self._close()

    def _handle_part_shortcut(self, part_key: str) -> None:
        button = getattr(self, "part_buttons", {}).get(str(part_key))
        if button is not None and button.isEnabled():
            self._select_part_key(str(part_key), preview_first=True)

    def _handle_topup_preview_shortcut(self) -> None:
        if self._topup_slots_enabled_for_plan():
            self._select_current_part_topup_slot()

    def _handle_validation_synthetic_click_shortcut(self) -> None:
        if not _env_flag("PPS_FOCUS_VALIDATION_ENABLE_SYNTHETIC_CLICK_SHORTCUT"):
            return
        if self.controller is None or not self._run_active or self.pending_instruction_request is not None:
            return
        self._refresh_target_global_bounds()
        bounds = self._target_global_bounds
        if bounds is None:
            x = y = None
        else:
            left, top, right, bottom = bounds
            x = int(round((left + right) / 2))
            y = int(round((top + bottom) / 2))
        self._log_response_click(
            x=x,
            y=y,
            in_target=True,
            diary_event_type="validation_synthetic_target_clicked",
            source="validation_hotkey_ctrl_alt_shift_f12",
        )

    def _dialog_relative_rect(self, widget: Any) -> dict[str, int]:
        top_left = widget.mapTo(self.dialog, widget.rect().topLeft())
        bottom_right = widget.mapTo(self.dialog, widget.rect().bottomRight())
        return {
            "x": int(top_left.x()),
            "y": int(top_left.y()),
            "right": int(bottom_right.x()),
            "bottom": int(bottom_right.y()),
            "width": int(widget.width()),
            "height": int(widget.height()),
        }

    def layout_validation_snapshot(self) -> dict[str, Any]:
        widgets = {
            "target_button": self.target_button,
            "response_panel": self.response_panel,
            "output_stack_cell": self.output_stack_cell,
            "output_levels_panel": self.output_levels_panel,
            "output_panel": self.output_panel,
            "output_summary": self.output_summary,
            "processing_panel": self.processing_panel,
            "part_selector_widget": self.part_selector_widget,
            "block_plan_widget": self.block_plan_widget,
            "tactile_timeline_widget": self.tactile_timeline_widget,
            "run_controls_widget": self.run_controls_widget,
            "start_button": self.start_button,
            "pause_button": self.pause_button,
            "resume_button": self.resume_button,
            "stop_button": self.stop_button,
        }
        if getattr(self, "data_selection_panel", None) is not None:
            widgets["data_selection_panel"] = self.data_selection_panel
        if getattr(self, "settings_panel", None) is not None:
            widgets["settings_panel"] = self.settings_panel
        if getattr(self, "data_columns_widget", None) is not None:
            widgets["data_settings_columns"] = self.data_columns_widget
        if getattr(self, "data_logging_column", None) is not None:
            widgets["data_logging_column"] = self.data_logging_column
        if getattr(self, "experiment_settings_column", None) is not None:
            widgets["experiment_settings_column"] = self.experiment_settings_column
        splitter_metrics = {}
        for name in ("workspace_splitter", "run_splitter"):
            splitter = getattr(self, name, None)
            if splitter is not None:
                splitter_metrics[name] = {
                    "width": int(splitter.width()),
                    "height": int(splitter.height()),
                    "count": int(splitter.count()),
                    "handle_width": int(splitter.handleWidth()),
                }
        if self.operator_tabs is not None:
            splitter_metrics["operator_tabs"] = {
                "width": int(self.operator_tabs.width()),
                "height": int(self.operator_tabs.height()),
                "count": int(self.operator_tabs.count()),
                "current_index": int(self.operator_tabs.currentIndex()),
            }
        if self.mode_tabs is not None:
            splitter_metrics["mode_tabs"] = {
                "width": int(self.mode_tabs.width()),
                "height": int(self.mode_tabs.height()),
                "count": int(self.mode_tabs.count()),
                "current_index": int(self.mode_tabs.currentIndex()),
                "data_logging_index": int(self.data_logging_tab_index),
                "experiment_control_index": int(self.experiment_control_tab_index),
                "experiment_control_enabled": bool(self.mode_tabs.isTabEnabled(self.experiment_control_tab_index)),
            }
        timeline_debug = {}
        timeline_snapshot = getattr(self.tactile_timeline_widget, "timeline_debug_snapshot", None)
        if callable(timeline_snapshot):
            timeline_debug = dict(timeline_snapshot())
        experiment_control_debug = self._experiment_control_layout_debug()
        visible_widgets = {
            name: bool(getattr(widget, "isVisibleTo", lambda _parent: True)(self.dialog))
            for name, widget in widgets.items()
            if widget is not None
        }
        return {
            "dialog": {"width": int(self.dialog.width()), "height": int(self.dialog.height())},
            "layout_profile": self.layout_profile.as_dict(),
            "widgets": {name: self._dialog_relative_rect(widget) for name, widget in widgets.items() if widget is not None},
            "widget_visibility": visible_widgets,
            "splitters": splitter_metrics,
            "timeline_debug": timeline_debug,
            "experiment_control_debug": experiment_control_debug,
            "experiment_window_lock": self._experiment_window_lock_snapshot(),
            "keyboard_shortcuts": self.keyboard_shortcut_map(),
            "adaptive_mechanisms": {
                "right_stack_mode": self.layout_profile.right_stack_mode,
                "operator_tabs": self.operator_tabs is not None,
                "mode_tabs": self.mode_tabs is not None,
                "resizable_workspace_splitter": self.workspace_splitter is not None,
                "resizable_run_splitter": self.run_splitter is not None,
                "data_settings_columns": getattr(self, "data_settings_columns_mode", ""),
                "lower_detail_text": bool(
                    self.layout_profile.screen_class == "spacious" and self.layout_profile.available_height >= 1300
                ),
                "lower_headings": bool((not self.layout_profile.compact) and self.layout_profile.available_height >= 1100),
            },
        }

    def layout_validation_failures(self) -> list[str]:
        snapshot = self.layout_validation_snapshot()
        profile = self.layout_profile
        dialog = snapshot["dialog"]
        widgets = snapshot["widgets"]
        widget_visibility = dict(snapshot.get("widget_visibility") or {})
        failures: list[str] = []
        if dialog["width"] > profile.available_width or dialog["height"] > profile.available_height:
            failures.append(
                f"window {dialog['width']}x{dialog['height']} exceeds available "
                f"{profile.available_width}x{profile.available_height}"
            )
        experiment_control_debug = snapshot.get("experiment_control_debug") or {}
        for name, rect in widgets.items():
            if not bool(widget_visibility.get(name, True)):
                continue
            overflow_left = max(0, -int(rect.get("x", 0)))
            overflow_top = max(0, -int(rect.get("y", 0)))
            overflow_right = max(0, int(rect.get("right", 0)) - int(dialog["width"]))
            overflow_bottom = max(0, int(rect.get("bottom", 0)) - int(dialog["height"]))
            lower_panel_chrome_only = (
                name == "processing_panel"
                and overflow_left == 0
                and overflow_top == 0
                and overflow_right == 0
                and 0 < overflow_bottom <= max(1, int(profile.root_margin))
                and not list(experiment_control_debug.get("clipped_widgets") or [])
                and not list(experiment_control_debug.get("too_short_widgets") or [])
                and not list(experiment_control_debug.get("overlap_pairs") or [])
            )
            if (overflow_left or overflow_top or overflow_right or overflow_bottom) and not lower_panel_chrome_only:
                failures.append(f"{name} is clipped outside the dialog: {rect}")
        target = widgets.get("target_button", {})
        target_visible = bool(widget_visibility.get("target_button", True))
        if target and target_visible and (target.get("width") != profile.target_min_height or target.get("height") != profile.target_min_height):
            failures.append(f"target_button does not match fixed {profile.target_min_height}px square: {target}")
        processing = widgets.get("processing_panel", {})
        processing_visible = bool(widget_visibility.get("processing_panel", True))
        if processing and processing_visible and processing.get("height", 0) < profile.experiment_control_min_height:
            failures.append(
                "processing_panel is shorter than the profile minimum "
                f"{profile.experiment_control_min_height}px: {processing}"
            )
        content_min_height = int(experiment_control_debug.get("content_min_height") or 0)
        if processing and processing_visible and content_min_height and processing.get("height", 0) < content_min_height:
            failures.append(
                "processing_panel is shorter than the content-safe minimum "
                f"{content_min_height}px: {processing}"
            )
        clipped_lower = list(experiment_control_debug.get("clipped_widgets") or [])
        if processing_visible and clipped_lower:
            failures.append(f"lower Experiment Control widgets are clipped: {clipped_lower}")
        too_short_lower = list(experiment_control_debug.get("too_short_widgets") or [])
        if processing_visible and too_short_lower:
            failures.append(f"lower Experiment Control widgets are shorter than measured content: {too_short_lower}")
        overlap_pairs = list(experiment_control_debug.get("overlap_pairs") or [])
        if processing_visible and overlap_pairs:
            failures.append(f"lower Experiment Control widgets overlap: {overlap_pairs}")
        hidden_required = list(experiment_control_debug.get("hidden_required_widgets") or [])
        if processing_visible and hidden_required:
            failures.append(f"required lower Experiment Control widgets are hidden: {hidden_required}")
        if processing and processing_visible:
            workspace_width = int(getattr(self.workspace_splitter, "width", lambda: 0)())
            if workspace_width and processing.get("width", 0) < workspace_width - 8:
                failures.append(f"processing_panel does not span the lower workspace width: {processing}")
        timeline_debug = snapshot.get("timeline_debug") or {}
        row_names = list(timeline_debug.get("row_names") or [])
        timeline_visible = bool(widget_visibility.get("tactile_timeline_widget", True))
        if timeline_visible and row_names != list(TIMELINE_ROW_NAMES):
            failures.append(f"timeline rows are {row_names}, expected {list(TIMELINE_ROW_NAMES)}")
        label_fit = dict(timeline_debug.get("label_fit") or {})
        if timeline_visible and int(label_fit.get("overlap_count") or 0) > 0:
            failures.append(f"timeline labels overlap in {label_fit.get('overlap_count')} measured rect(s)")
        response = widgets.get("response_panel", {})
        output_levels = widgets.get("output_levels_panel", {})
        output = widgets.get("output_panel", {})
        response_visible = bool(widget_visibility.get("response_panel", True))
        if response_visible and response and output_levels:
            output_separated = (
                output_levels.get("y", 0) >= response.get("bottom", 0)
                or output_levels.get("x", 0) >= response.get("right", 0)
            )
            if not output_separated:
                failures.append("output_levels_panel is not separated from response_panel")
        output_panel_visible = bool(getattr(getattr(self, "output_panel", None), "isVisible", lambda: False)())
        if response_visible and output_panel_visible and output_levels and output and output.get("y", 0) < output_levels.get("bottom", 0):
            failures.append("output_panel is not positioned under output_levels_panel")
        data_column = widgets.get("data_logging_column", {})
        settings_column = widgets.get("experiment_settings_column", {})
        data_visible = bool(widget_visibility.get("data_logging_column", True))
        if data_visible and data_column and settings_column:
            if getattr(self, "data_settings_columns_mode", "") == "stacked":
                if settings_column.get("y", 0) < data_column.get("bottom", 0):
                    failures.append("experiment_settings_column should stack below data_logging_column in stacked mode")
            else:
                same_row = abs(settings_column.get("y", 0) - data_column.get("y", 0)) <= 8
                right_of_data = settings_column.get("x", 0) >= data_column.get("right", 0)
                if not (same_row and right_of_data):
                    failures.append(
                        "Data Logging and Experiment Settings columns are not side-by-side "
                        f"for {profile.screen_class} layout: data={data_column}, settings={settings_column}"
                    )
            for name, rect in (("data_logging_column", data_column), ("experiment_settings_column", settings_column)):
                if rect.get("width", 0) < 220:
                    failures.append(f"{name} is too narrow for operator controls: {rect}")
        required_shortcut_names = set(self.keyboard_shortcut_map())
        installed_shortcut_names = {"start_or_continue"} | {
            name for name, shortcuts in self.operator_action_shortcuts.items() if shortcuts
        }
        missing_shortcuts = sorted(required_shortcut_names - installed_shortcut_names)
        if missing_shortcuts:
            failures.append(f"missing installed keyboard shortcuts: {missing_shortcuts}")
        return failures

    def _focused_output_volume_percent_box(self) -> Any | None:
        focus = self.q["QApplication"].focusWidget()
        if focus is None:
            return None
        for name in ("output_12_volume_percent_box", "output_34_volume_percent_box"):
            box = getattr(self, name, None)
            if box is not None and (focus is box or box.isAncestorOf(focus)):
                return box
        return None

    def _commit_focused_output_volume_percent_box(self) -> bool:
        box = self._focused_output_volume_percent_box()
        if box is None:
            return False
        commit = getattr(box, "_commit_text_value", None)
        if callable(commit):
            commit()
        else:
            box.interpretText()
        return True

    def _keyboard_focus_is_pre_run_input(self) -> bool:
        focus = self.q["QApplication"].focusWidget()
        if focus is None:
            return False
        input_types = (
            self.q["QLineEdit"],
            self.q["QTextEdit"],
            self.q["QComboBox"],
            self.q["QCheckBox"],
            self.q["QDoubleSpinBox"],
            self.q["QSlider"],
        )
        return isinstance(focus, input_types)

    def _handle_primary_action_shortcut(self) -> None:
        if self._commit_focused_output_volume_percent_box():
            return
        if self.pending_instruction_request is not None:
            if self._part2_start_gate_pending():
                self._start_part2_gate(source="keyboard")
                return
            self._approve_pending_instruction_continue(source="keyboard")
            return
        if self.start_button.isEnabled() and not self._keyboard_focus_is_pre_run_input():
            self.start()

    def _approve_pending_instruction_continue(self, *, source: str) -> bool:
        if self.pending_instruction_request is None:
            return False
        context = dict(self.pending_instruction_request.get("context") or {})
        self.pending_instruction_request["approved"] = True
        self.pending_instruction_request["event"].set()
        self.pending_instruction_request = None
        self.instruction_button.setVisible(False)
        self.instruction_button.setText("Continue")
        self.target_button.setEnabled(True)
        self.event_label.setText(f"Instruction continuation logged ({source})")
        self._set_primary_action_shortcuts_enabled(False)
        if self._run_active:
            self.start_button.setEnabled(False)
        self._refresh_start_part2_button()
        self._refresh_start_button_label()
        _append_output_diary_event(
            "instruction_continue",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"source": source, "context": context},
            create=True,
        )
        return True

    def _create_real_audio_engine_on_ui_thread(self) -> Any:
        from .audio_routing import audio_runtime_preflight_message
        from .runner import CLICK_SOUND, AudioEngine, find_output_device

        device_idx, _device_name, _is_preferred = find_output_device()
        if device_idx is None:
            raise RuntimeError("No usable audio output device was found.\n" + audio_runtime_preflight_message())
        engine = AudioEngine(device_idx)
        if hasattr(engine, "set_wired_loopback_mode"):
            engine.set_wired_loopback_mode(self.capture_options.wired_loopback_mode)
        self._apply_output_volumes_to_engine(engine)
        try:
            if CLICK_SOUND and not engine.load_click_sound(CLICK_SOUND):
                raise RuntimeError(
                    "The tactile response-marker output stream could not be opened. "
                    "Check the selected Komplete ASIO device and restart Focus Mode."
                )
            return engine
        except Exception:
            if hasattr(engine, "shutdown"):
                engine.shutdown()
            raise

    def _shutdown_owned_audio_engine(self) -> None:
        engine = self._owned_audio_engine
        self._owned_audio_engine = None
        if engine is not None and hasattr(engine, "shutdown"):
            try:
                engine.shutdown()
            except Exception:
                pass

    def _handle_startup_failure(self, message: str) -> None:
        _append_output_diary_event(
            "audio_initialization_failed",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"message": message, "playback_output_levels": self._output_channel_volume_payload()},
            create=True,
        )
        result = SimpleNamespace(
            completed=False,
            interrupted=True,
            summary_text="Run could not start.",
            session_dir=self.package.session_dir,
            events_csv=self.package.session_dir / "events.csv",
            events_xdf=self.package.session_dir / "events.xdf",
            lsl_markers_csv=None,
            lsl_markers_xdf=None,
            trigger_dictionary_path=None,
            session_metadata_path=None,
            recording_paths=[],
            warnings=[message],
            capture_options=self.capture_options.as_dict(),
        )
        self.event_label.setText(message)
        self._handle_done(result)

    def start(self) -> None:
        if self._part2_start_gate_pending():
            self._start_part2_gate(source="start button")
            return
        if self.thread is not None and self.thread.is_alive():
            return
        if not self.demographics_submitted or self.controller is None:
            self.start_button.setEnabled(False)
            self.event_label.setText("Submit participant setup before starting playback.")
            return
        self.capture_options = self.controller.capture_options
        self.enable_missed_trial_topup = bool(self.enable_missed_trial_topup)
        self._refresh_run_plan()
        self._clear_block_preview()
        self.topup_draft_items = []
        self._refresh_topup_draft_widget()
        _append_output_diary_event(
            "start_run_clicked",
            package=self.package,
            participant_id=self.package.participant_id,
            capture_options=self.capture_options.as_dict(),
            payload={
                "topup_enabled": self.enable_missed_trial_topup,
                "playback_output_levels": self._output_channel_volume_payload(),
            },
            create=True,
        )
        if self.controller_factory is None and getattr(self.controller, "audio_engine", None) is None:
            try:
                self._shutdown_owned_audio_engine()
                self._owned_audio_engine = self._create_real_audio_engine_on_ui_thread()
                self.controller.audio_engine = self._owned_audio_engine
            except Exception as exc:
                self._handle_startup_failure(f"Audio initialization failed: {exc}")
                return
        self.start_button.setEnabled(False)
        self._set_output_test_buttons_enabled(False)
        self._refresh_start_part2_button()
        self._refresh_start_button_label()
        self._set_primary_action_shortcuts_enabled(False)
        self._run_active = True
        self._run_paused = False
        self._refresh_pause_resume_buttons()
        self.stop_button.setEnabled(False)
        self.target_button.setEnabled(True)
        self._last_response_click_signature = None
        self._lock_experiment_window_geometry()
        self._refresh_target_global_bounds()
        self._start_global_response_click_listener()
        self.run_state_chip.setText("Running")
        self.progress_label.setText("Starting playback")
        self.event_label.setText("Session event stream active")

        def _run() -> None:
            assert self.controller is not None
            result = self.controller.run(
                progress_callback=lambda payload: self.messages.put(("progress", payload)),
                event_callback=lambda message: self.messages.put(("event", message)),
            )
            self.messages.put(("done", result))

        self.thread = threading.Thread(target=_run, daemon=True)
        self.thread.start()

    def _auto_approve_topup_playback(self, summary: dict[str, Any]) -> bool:
        summary = dict(summary)
        record = {
            "summary": summary,
            "approved": True,
            "mode": "setup_checkbox_auto_play",
            "timestamp_unix": time.time(),
        }
        self.validation_topup_approval_records.append(record)
        _append_output_diary_event(
            "topup_approval_resolved",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"summary": summary, "approved": True, "mode": "setup_checkbox_auto_play"},
            create=True,
        )
        return True

    def _request_topup_approval(self, summary: dict[str, Any]) -> bool:
        return self._auto_approve_topup_playback(summary)

    def _request_instruction_continue(self, context: dict[str, Any]) -> bool:
        request = {"context": dict(context), "approved": False, "event": threading.Event()}
        self.pending_instruction_request = request
        self.messages.put(("instruction_continue", request))
        request["event"].wait()
        if self.pending_instruction_request is request:
            self.pending_instruction_request = None
        return bool(request["approved"])

    def _release_pending_operator_requests(self, *, source: str) -> None:
        released: list[str] = []
        for name, attr in (
            ("instruction_continue", "pending_instruction_request"),
            ("topup_approval", "pending_topup_approval_request"),
        ):
            request = getattr(self, attr, None)
            if not request:
                continue
            request["approved"] = False
            event = request.get("event")
            if hasattr(event, "set"):
                event.set()
            setattr(self, attr, None)
            released.append(name)
        if not released:
            return
        target_button = getattr(self, "target_button", None)
        if target_button is not None:
            target_button.setEnabled(False)
        instruction_button = getattr(self, "instruction_button", None)
        if instruction_button is not None:
            instruction_button.setVisible(False)
        self._set_primary_action_shortcuts_enabled(False)
        self._refresh_start_part2_button()
        _append_output_diary_event(
            "pending_operator_request_released",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"source": source, "released": released},
            create=True,
        )

    def _close_external_labrecorder_for_runner_exit(self) -> None:
        controller = self.controller
        close = getattr(controller, "close_external_labrecorder_for_runner_exit", None)
        try:
            timeout_s = min(2.0, max(0.25, float(self.capture_options.external_labrecorder_stop_timeout_s)))
        except Exception:
            timeout_s = 2.0
        if callable(close):
            try:
                close(timeout_s=timeout_s)
            except Exception as exc:
                _append_output_diary_event(
                    "external_labrecorder_runner_exit_close_failed",
                    package=self.package,
                    capture_options=self.capture_options.as_dict(),
                    payload={"error": str(exc)},
                    create=True,
                )
        self._close_pending_continuous_external_labrecorder_state(timeout_s=timeout_s)

    def _close_pending_continuous_external_labrecorder_state(self, *, timeout_s: float) -> None:
        state = self._continuous_external_labrecorder_state
        if not state:
            return
        capture = state.get("capture")
        if capture is None:
            self._continuous_external_labrecorder_state = None
            return
        try:
            close_for_exit = getattr(capture, "close_for_runner_exit", None)
            if callable(close_for_exit):
                stopped = close_for_exit(timeout_s=timeout_s)
            else:
                stopped = capture.stop(timeout_s=timeout_s)
        except Exception as exc:
            _append_output_diary_event(
                "external_labrecorder_pending_handoff_close_failed",
                package=self.package,
                capture_options=self.capture_options.as_dict(),
                payload={"error": str(exc), "xdf_path": str(state.get("xdf_path") or "")},
                create=True,
            )
            return
        stopped = dict(stopped or {})
        stopped["runner_exit"] = True
        stopped["pending_handoff_cancelled"] = True
        report_path = Path(state.get("report_path") or "")
        if str(report_path):
            try:
                os.makedirs(_output_filesystem_path(report_path.parent), exist_ok=True)
                with open(_output_filesystem_path(report_path), "w", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "schema": "pps-runner-owned-labrecorder-capture.v1",
                                "session_group_id": str(state.get("session_group_id") or ""),
                                "source_part_session_id": str(state.get("source_part_session_id") or ""),
                                "lsl_stream_session_id": str(state.get("lsl_stream_session_id") or ""),
                                "start": {key: value for key, value in dict(state.get("status") or {}).items() if key != "stop"},
                                "stop": stopped,
                            },
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n"
                    )
            except Exception:
                pass
        _append_output_diary_event(
            "external_labrecorder_pending_handoff_closed",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={
                "xdf_path": str(state.get("xdf_path") or stopped.get("xdf_path") or ""),
                "finalize_path": str(state.get("finalize_path") or ""),
                "returncode": stopped.get("returncode"),
            },
            create=True,
        )
        self._continuous_external_labrecorder_state = None

    def _click(self) -> None:
        if self._tactile_calibration_active:
            self._record_tactile_calibration_target_click("focus_target")
            return
        if self.pending_instruction_request is not None:
            if self._part2_start_gate_pending():
                self.event_label.setText("Use Start Part 02 to continue to Part 02.")
                return
            self._approve_pending_instruction_continue(source="click target")
            return
        if self.controller is None:
            self.event_label.setText("Start the run before logging responses.")
            return
        x, y = self._target_last_click_global_xy()
        self._log_response_click(x=x, y=y, in_target=True, diary_event_type="target_clicked", source="qt_response_target")

    def _record_tactile_calibration_target_click(self, source: str) -> None:
        if not self._tactile_calibration_active:
            return
        x, y, _coordinate_source = self._tactile_calibration_target_center()
        payload = self._tactile_calibration_collector.record_click(
            in_target=True,
            x=x,
            y=y,
            source=source,
        )
        if payload:
            self.messages.put(("tactile_calibration_click", payload))
            self.event_label.setText(
                "Tactile threshold response recorded."
                if bool(payload.get("valid_response"))
                else "Tactile threshold click outside the response window."
            )

    def _continue_instruction_button(self) -> None:
        if self._part2_start_gate_pending():
            self.event_label.setText("Use Start Part 02 to continue to Part 02.")
            return
        self._approve_pending_instruction_continue(source="button")

    def _refresh_pause_resume_buttons(self) -> None:
        pause_enabled = bool(self.controller is not None and self._run_active and not self._run_paused)
        resume_enabled = bool(self.controller is not None and self._run_active and self._run_paused)
        self.pause_button.setEnabled(pause_enabled)
        self.resume_button.setEnabled(resume_enabled)

    def _pause(self) -> None:
        if self.controller is None or not self._run_active or self._run_paused:
            self._refresh_pause_resume_buttons()
            return
        self.controller.pause()
        self._run_paused = True
        self._refresh_pause_resume_buttons()
        self.run_state_chip.setText("Paused")
        self.progress_label.setText("Paused")
        _append_output_diary_event(
            "pause_clicked",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            create=True,
        )

    def _resume(self) -> None:
        if self.controller is None or not self._run_active or not self._run_paused:
            self._refresh_pause_resume_buttons()
            return
        self.controller.resume()
        self._run_paused = False
        self._refresh_pause_resume_buttons()
        self.run_state_chip.setText("Running")
        _append_output_diary_event(
            "resume_clicked",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            create=True,
        )

    def _stop(self) -> None:
        _append_output_diary_event(
            "stop_clicked",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"thread_alive": bool(self.thread and self.thread.is_alive())},
            create=True,
        )
        self._run_active = False
        self._refresh_pause_resume_buttons()
        self._stop_global_response_click_listener()
        stop = getattr(self.controller, "stop", None)
        if callable(stop):
            stop()
        if hasattr(self, "progress_label"):
            self.progress_label.setText("Stopping" if self.thread and self.thread.is_alive() else self.progress_label.text())

    def _close(self) -> None:
        _append_output_diary_event(
            "close_clicked",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            create=True,
        )
        self._stop()
        self.dialog.accept()

    def _handle_block_schedule(self, payload: dict[str, Any]) -> None:
        display_index = _payload_display_block_index(payload)
        plan_item = self._run_plan_item_by_number(display_index)
        if plan_item is not None:
            self.selected_part_key = str(plan_item.get("part_key") or self.selected_part_key or "")
            self._refresh_run_plan()
        duration_s = payload.get("duration_s", 0.0)
        duration_float = _float_or_none(duration_s)
        duration_float = float(duration_float) if duration_float is not None else 0.0
        self.timeline_state.load_block(
            part_number=payload.get("part_number", ""),
            phase_label=payload.get("phase_label", payload.get("phase", "")),
            block_index=payload.get("block_index", ""),
            block_label=payload.get("block_label", ""),
            duration_s=duration_float,
            instruction_segments=self._timeline_instruction_segments_for_item(plan_item or {}, duration_s=max(0.001, duration_float)),
            tactile_events=list(payload.get("tactile_events") or []),
            trial_segments=list(payload.get("trial_segments") or []),
        )
        self.planned_tactile_cue_count += len(self.timeline_state.cues)
        self._timeline_perf_anchor = None
        part_text = str(payload.get("part_number") or "").strip()
        self.part_chip.setText(_part_display_label(part_text) if part_text else "Part -")
        display_count = _payload_display_block_count(
            payload,
            _run_plan_total(self.package, include_topup_slots=self._topup_slots_enabled_for_plan()),
        )
        if self.active_display_block_index is not None and self.active_display_block_index != display_index:
            self.completed_display_block_indices.add(int(self.active_display_block_index))
        self.active_display_block_index = int(display_index) if display_index else None
        if self.active_display_block_index is not None:
            self._clear_block_preview(selected=self.active_display_block_index)
            self._set_instruction_plan_for_item(plan_item)
        if hasattr(self, "block_plan_widget"):
            self.block_plan_widget.update()
        if plan_item is not None:
            display_index_label = int(plan_item.get("part_block_number") or display_index)
            display_count = len([item for item in self.all_block_plan_items if str(item.get("part_key") or "") == str(plan_item.get("part_key") or "")]) or display_count
        else:
            display_index_label = display_index
        if bool(payload.get("is_topup")):
            self.block_chip.setText(
                f"Block {display_index_label}/{display_count} (Top-up)" if display_index else f"Block -/{display_count} (Top-up)"
            )
        else:
            self.block_chip.setText(f"Block {display_index_label}/{display_count}" if display_index else f"Block -/{display_count}")
        self.recenter_status_label.setText("Cursor recenter: waiting for next tactile cue")
        self._sync_progress_bar_to_red_line()
        self._update_tactile_timeline_display()

    def _sync_progress_bar_to_red_line(self) -> None:
        if not hasattr(self, "progress"):
            return
        duration = float(self.timeline_state.duration_s or 0.0)
        if duration <= 0:
            self.progress.setValue(0)
            return
        elapsed = max(0.0, min(duration, float(self.timeline_state.elapsed_s or 0.0)))
        self.progress.setValue(int(max(0.0, min(1.0, elapsed / duration)) * 1000))

    def _update_tactile_progress(self, elapsed_s: float, *, anchor_to_now: bool = False) -> None:
        duration = float(self.timeline_state.duration_s or 0.0)
        elapsed = max(0.0, float(elapsed_s or 0.0))
        if duration > 0:
            elapsed = min(elapsed, duration)
        if anchor_to_now:
            self._timeline_perf_anchor = time.perf_counter() - elapsed
        moved = self.recenter_controller.tick(
            elapsed,
            active=self._run_active and self.timeline_state.active,
            paused=self._run_paused,
            instruction_waiting=self.pending_instruction_request is not None,
        )
        if moved:
            last = moved[-1]
            self.recenter_status_label.setText(
                f"Cursor recenter: Trial {last.trial_number} at {last.time_s:.1f}s"
            )
        self._sync_progress_bar_to_red_line()
        self._update_tactile_timeline_display(preserve_recenter_message=bool(moved))

    def _update_tactile_timeline_display(self, *, preserve_recenter_message: bool = False) -> None:
        total = len(self.timeline_state.cues)
        if total <= 0:
            text = "Next tactile: no cues in this block" if self.timeline_state.active else "Next tactile: no block schedule"
            self.next_tactile_label.setText(text)
            self.next_tactile_label.setToolTip(text)
            self.tactile_count_label.setText(f"0 / 0 cues | {self.timeline_state.click_count()} clicks")
            self.tactile_count_label.setToolTip(self.tactile_count_label.text())
            if not preserve_recenter_message:
                self.recenter_status_label.setText("Cursor recenter: waiting")
            self.tactile_timeline_widget.update()
            return
        next_cue = self.timeline_state.next_cue()
        if next_cue is None:
            self.next_tactile_label.setText("Next tactile: complete")
        else:
            countdown = max(0.0, next_cue.time_s - self.timeline_state.elapsed_s)
            soa = f" | SOA {next_cue.soa_ms} ms" if str(next_cue.soa_ms).strip() else ""
            row = f" | {next_cue.row_label}" if str(next_cue.row_label).strip() else ""
            noise = f" | {next_cue.noise_type}" if str(next_cue.noise_type).strip() else ""
            self.next_tactile_label.setText(
                f"Next tactile: Trial {next_cue.trial_number} in {countdown:.1f}s{soa}{row}{noise}"
            )
        self.next_tactile_label.setToolTip(self.next_tactile_label.text())
        self.tactile_count_label.setText(
            f"{self.timeline_state.passed_count()} / {total} cues | {self.timeline_state.click_count()} clicks"
        )
        self.tactile_count_label.setToolTip(self.tactile_count_label.text())
        if not preserve_recenter_message:
            self.recenter_status_label.setText(
                f"Cursor recenter: {self.timeline_state.recentered_count()} / {total} cues"
            )
        self.tactile_timeline_widget.update()

    def _move_cursor_to_target(self, cue: TactileTimelineCue) -> None:
        x, y, coordinate_source = _widget_screen_center(self.target_button)
        offscreen = self._offscreen_platform()
        no_mouse_mode = _validation_no_mouse_mode()
        self._last_recenter_backend_warning = ""
        if offscreen or no_mouse_mode:
            mode = "recorded_intent"
            if no_mouse_mode and not offscreen:
                self._last_recenter_backend_warning = "cursor recenter disabled by validation no-mouse mode"
        else:
            mode = self._move_os_cursor_to_global_center(x, y)
        record = {
            "cue_id": cue.cue_id,
            "trial_number": cue.trial_number,
            "trial_uid": cue.trial_uid,
            "time_s": cue.time_s,
            "elapsed_s": self.timeline_state.elapsed_s,
            "mode": mode,
            "coordinate_source": coordinate_source,
            "x": x,
            "y": y,
        }
        if no_mouse_mode:
            record["cursor_move_suppressed"] = True
        if self._last_recenter_backend_warning:
            record["backend_warning"] = self._last_recenter_backend_warning
        self.recenter_records.append(record)

    def _move_cursor_to_tactile_calibration_target(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        x, y, coordinate_source = self._tactile_calibration_target_center()
        offscreen = self._offscreen_platform()
        no_mouse_mode = _validation_no_mouse_mode()
        self._last_recenter_backend_warning = ""
        if x is None or y is None:
            mode = "target_unavailable"
        elif offscreen or no_mouse_mode:
            mode = "recorded_intent"
            if no_mouse_mode and not offscreen:
                self._last_recenter_backend_warning = "cursor recenter disabled by validation no-mouse mode"
        else:
            mode = self._move_os_cursor_to_global_center(int(x), int(y))
        record = {
            "source": "tactile_calibration",
            "mode": mode,
            "coordinate_source": coordinate_source,
            "x": "" if x is None else int(x),
            "y": "" if y is None else int(y),
            **dict(context or {}),
        }
        if no_mouse_mode:
            record["cursor_move_suppressed"] = True
        if self._last_recenter_backend_warning:
            record["backend_warning"] = self._last_recenter_backend_warning
        self.recenter_records.append(record)
        return record

    def _move_os_cursor_to_global_center(self, x: int, y: int) -> str:
        self._last_recenter_backend_warning = ""
        try:
            import pyautogui  # type: ignore

            pyautogui.FAILSAFE = False
            pyautogui.PAUSE = 0
            pyautogui.moveTo(int(x), int(y), duration=0)
            return "pyautogui"
        except Exception as exc:
            self._last_recenter_backend_warning = f"pyautogui unavailable: {exc}"
        try:
            self.q["QCursor"].setPos(int(x), int(y))
            return "qt_cursor_fallback"
        except Exception as exc:
            detail = f"Qt cursor fallback failed: {exc}"
            self._last_recenter_backend_warning = (
                f"{self._last_recenter_backend_warning}; {detail}"
                if self._last_recenter_backend_warning
                else detail
            )
            return "cursor_move_failed"

    def _offscreen_platform(self) -> bool:
        env_platform = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
        if env_platform in {"offscreen", "minimal"}:
            return True
        app = self.q["QApplication"].instance()
        try:
            platform = str(app.platformName()).lower() if app is not None else ""
        except Exception:
            platform = ""
        return platform in {"offscreen", "minimal"}

    def _tick_tactile_clock(self) -> None:
        if self._timeline_perf_anchor is None or not self._run_active or self._run_paused or not self.timeline_state.active:
            return
        elapsed = max(0.0, time.perf_counter() - self._timeline_perf_anchor)
        if self.timeline_state.duration_s > 0:
            elapsed = min(elapsed, self.timeline_state.duration_s)
        if elapsed < self.timeline_state.elapsed_s:
            elapsed = self.timeline_state.elapsed_s
        self._update_tactile_progress(elapsed)

    def _activate_response_target_window(self) -> None:
        if self._offscreen_platform():
            return
        try:
            self.dialog.raise_()
            self.dialog.activateWindow()
            _force_foreground_window(self.dialog)
            self.target_button.setFocus(self.q["Qt"].FocusReason.MouseFocusReason)
            self.q["QApplication"].processEvents()
        except Exception:
            pass

    def _drain(self) -> None:
        self._drain_companion_commands()
        while not self.messages.empty():
            kind, payload = self.messages.get_nowait()
            if kind == "progress":
                if dict(payload).get("ui_event") == "block_schedule":
                    self._handle_block_schedule(dict(payload))
                    continue
                if dict(payload).get("ui_event") == "topup_draft":
                    self._handle_topup_draft(dict(payload))
                    continue
                if dict(payload).get("ui_event") == "topup_completion":
                    self._handle_topup_completion(dict(payload))
                    continue
                duration = float(payload.get("duration_s") or 0.0)
                elapsed = float(payload.get("elapsed_s") or 0.0)
                display_index = _payload_display_block_index(dict(payload))
                display_count = _payload_display_block_count(
                    dict(payload),
                    _run_plan_total(self.package, include_topup_slots=self._topup_slots_enabled_for_plan()),
                )
                block_kind = "top-up block" if bool(payload.get("is_topup")) else "Block"
                plan_item = self._run_plan_item_by_number(display_index)
                display_index_label = int(plan_item.get("part_block_number") or display_index) if plan_item is not None else display_index
                if plan_item is not None:
                    display_count = len([item for item in self.all_block_plan_items if str(item.get("part_key") or "") == str(plan_item.get("part_key") or "")]) or display_count
                self.progress_label.setText(
                    f"{block_kind.title()} {display_index_label}: {payload.get('block_label')}  "
                    f"{elapsed:.1f}/{duration:.1f}s"
                )
                part_number = str(payload.get("part_number") or "").strip()
                if part_number:
                    self.part_chip.setText(_part_display_label(part_number))
                if bool(payload.get("is_topup")):
                    self.block_chip.setText(
                        f"Block {display_index_label}/{display_count} (Top-up)" if display_index else f"Block -/{display_count} (Top-up)"
                    )
                else:
                    self.block_chip.setText(f"Block {display_index_label}/{display_count}" if display_index else f"Block -/{display_count}")
                self._update_tactile_progress(elapsed, anchor_to_now=True)
            elif kind == "event":
                self.event_label.setText(str(payload))
                if str(payload) in {"external_labrecorder_started", "session_start"}:
                    self._activate_response_target_window()
            elif kind == "response_click":
                self._apply_response_click_to_ui(dict(payload))
            elif kind == "tactile_calibration_click":
                response_payload = dict(payload)
                self.event_label.setText(
                    "Tactile threshold response recorded."
                    if bool(response_payload.get("valid_response"))
                    else "Tactile threshold click outside the response window."
                )
                monitor = getattr(self, "tactile_calibration_monitor_dialog", None)
                if monitor is not None:
                    try:
                        monitor.record_response(response_payload)
                    except Exception:
                        pass
            elif kind == "tactile_calibration_recenter":
                recenter_payload = dict(payload)
                future = recenter_payload.get("future")
                try:
                    result = self._move_cursor_to_tactile_calibration_target(
                        dict(recenter_payload.get("context") or {})
                    )
                except Exception as exc:
                    result = {"mode": "failed", "error": str(exc)}
                if hasattr(future, "set_result"):
                    future.set_result(result)
            elif kind == "prewarm_progress":
                self.prewarm_label.setText(f"Next {payload.get('participant_id')}: {payload.get('message')}")
            elif kind == "prewarm":
                participant = str(payload.get("participant_id") or "")
                status = str(payload.get("status") or "")
                if status == "ready":
                    self.prewarm_label.setText(f"Next {participant}: ready")
                elif status == "failed":
                    self.prewarm_label.setText(f"Next {participant}: failed")
                else:
                    self.prewarm_label.setText(f"Next {participant}: {status}")
            elif kind == "topup_approval":
                self._handle_topup_approval(payload)
            elif kind == "instruction_continue":
                self._handle_instruction_continue(payload)
            elif kind == "output_test_done":
                self._handle_output_test_done(payload)
            elif kind == "tactile_calibration_progress":
                self._handle_tactile_calibration_progress(dict(payload))
            elif kind == "tactile_calibration_done":
                self._handle_tactile_calibration_done(dict(payload))
            elif kind == "done":
                self._handle_done(payload)
        self._refresh_target_global_bounds()
        self._tick_tactile_clock()
        self._refresh_experiment_control_minimum_height()

    def _handle_topup_draft(self, payload: dict[str, Any]) -> None:
        self.topup_draft_items = [dict(item) for item in list(payload.get("missed_trials") or []) if isinstance(item, dict)]
        self._refresh_topup_draft_widget()
        if self.selected_display_block_index is not None:
            item = self._run_plan_item_by_number(self.selected_display_block_index)
            if item is not None and str(item.get("kind") or "") == "topup":
                draft_count = len(self._visible_topup_draft_items())
                part_label = _part_display_label(str(item.get("part_key") or ""))
                draft_text = f" | {draft_count} missed trial(s) in draft" if draft_count else " | waiting for missed trials"
                self.block_preview_label.setText(
                    f"Block preview: {item.get('display_label', 'Top-up')} | {part_label} missed tactile trials{draft_text}"
                )
                self._refresh_experiment_control_minimum_height()

    def _handle_topup_completion(self, payload: dict[str, Any]) -> None:
        self._last_topup_completion = dict(payload)
        message = str(payload.get("operator_completion_message") or "").strip()
        outcome = str(payload.get("topup_outcome") or "").strip()
        if not message:
            if outcome == "not_needed":
                part_number = str(payload.get("part_number") or "").strip()
                message = (
                    f"Part {part_number} data collected. No top-up needed. Part 02 will load automatically."
                    if part_number == "1"
                    else "Participant data collected. No top-up needed."
                )
            elif outcome == "played":
                message = "Top-up completed."
            elif outcome == "disabled":
                message = "Data collected. Top-up disabled."
        if message:
            self.event_label.setText(message)
            self.progress_label.setText(message)
        if outcome == "not_needed":
            self.run_state_chip.setText("No Top-Up Needed")
        elif outcome in {"played", "disabled", "skipped"}:
            self.run_state_chip.setText("Top-Up Done" if outcome == "played" else "Complete")
        _append_output_diary_event(
            "topup_completion_visible",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload=dict(payload),
            create=True,
        )

    def _handle_instruction_continue(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        if hasattr(event, "is_set") and event.is_set():
            return
        context = dict(payload.get("context") or {})
        self.pending_instruction_request = payload
        mode = str(context.get("mode") or "click")
        label = str(context.get("instruction_label") or "instruction")
        if self._part2_start_gate_pending():
            self.target_button.setEnabled(False)
            self.instruction_button.setVisible(False)
            self.instruction_button.setText("Continue")
            self.selected_part_key = "2"
            self.start_button.setEnabled(True)
            self.event_label.setText("Part 01 complete. Press Start Part 02 when ready.")
            self._set_primary_action_shortcuts_enabled(True)
            self._refresh_start_part2_button()
            self._refresh_start_button_label()
            return
        self.target_button.setEnabled(True)
        if mode == "button":
            self.instruction_button.setText(str(context.get("button_label") or "Continue"))
            self.instruction_button.setVisible(True)
            self.event_label.setText(f"Click the target, press Space/Enter, or use Continue after {label}.")
        else:
            self.instruction_button.setVisible(False)
            self.event_label.setText(f"Click the target or press Space/Enter to continue after {label}.")
        self._set_primary_action_shortcuts_enabled(True)
        self._refresh_start_part2_button()
        self._refresh_start_button_label()

    def _handle_topup_approval(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        if hasattr(event, "is_set") and event.is_set():
            return
        self.pending_topup_approval_request = payload
        summary = dict(payload.get("summary") or {})
        payload["approved"] = self._auto_approve_topup_playback(summary)
        if hasattr(event, "set"):
            event.set()
        if self.pending_topup_approval_request is payload:
            self.pending_topup_approval_request = None

    def _handle_done(self, result: Any) -> None:
        self.result = result
        self.exit_code = 0 if result.completed else 2
        self._run_active = False
        self._run_paused = False
        self._stop_global_response_click_listener()
        self._unlock_experiment_window_geometry()
        self.timeline_state.active = False
        if self.active_display_block_index is not None:
            self.completed_display_block_indices.add(int(self.active_display_block_index))
        self.active_display_block_index = None
        if hasattr(self, "block_plan_widget"):
            self.block_plan_widget.update()
        self.target_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._set_output_test_buttons_enabled(True)
        self._refresh_start_part2_button()
        self._set_primary_action_shortcuts_enabled(False)
        self.progress.setValue(1000 if result.completed else self.progress.value())
        self.run_state_chip.setText("Complete" if result.completed else "Interrupted")
        self.progress_label.setText("Complete" if result.completed else "Interrupted")
        operator_message = str(getattr(result, "operator_completion_message", "") or "").strip()
        if operator_message:
            self.event_label.setText(operator_message)
            self.progress_label.setText(operator_message)
        if _package_is_split_part(self.package) and bool(result.completed):
            next_manifest = self._next_split_part_manifest()
            if next_manifest is not None and not operator_message:
                current_part = _part_key_text(getattr(self.package, "part_number", "")) or "?"
                self.event_label.setText(f"{_part_display_label(current_part)} complete; Part 02 ready.")
        lines = [str(result.summary_text or "").strip()]
        if operator_message:
            lines.append(f"Operator status: {operator_message}")
        topup_summary = dict(getattr(result, "topup_summary", {}) or {})
        if topup_summary:
            lines.append(
                "Top-up: "
                f"{topup_summary.get('topup_outcome', 'unknown')} "
                f"({topup_summary.get('hit_count', 0)} hits, "
                f"{topup_summary.get('missed_needs_topup_count', 0)} misses, "
                f"{topup_summary.get('topup_attempt_count', 0)} attempts)"
            )
        lines.append(f"Session folder: {result.session_dir}")
        lines.append(f"Events CSV: {result.events_csv}")
        if result.capture_options.get("write_internal_xdf", True):
            lines.append(f"Events XDF: {result.events_xdf}")
        if result.lsl_markers_csv is not None:
            lines.append(f"LSL marker mirror: {result.lsl_markers_csv}")
        if result.trigger_dictionary_path is not None:
            lines.append(f"Trigger dictionary: {result.trigger_dictionary_path}")
        if getattr(result, "session_metadata_path", None) is not None:
            lines.append(f"Session metadata: {result.session_metadata_path}")
        if result.recording_paths:
            lines.append("Recordings:")
            lines.extend(f"  {path}" for path in result.recording_paths)
        if result.warnings:
            lines.append("Warnings:")
            lines.extend(f"  {warning}" for warning in result.warnings)
        self.output_summary.setPlainText("\n".join(line for line in lines if line))
        _append_output_diary_event(
            "output_summary_written",
            package=self.package,
            capture_options=dict(getattr(result, "capture_options", {}) or {}),
            payload={
                "completed": bool(getattr(result, "completed", False)),
                "interrupted": bool(getattr(result, "interrupted", False)),
                "session_dir": str(getattr(result, "session_dir", "")),
                "events_csv": str(getattr(result, "events_csv", "")),
                "events_xdf": str(getattr(result, "events_xdf", "")),
                "lsl_markers_csv": str(getattr(result, "lsl_markers_csv", "") or ""),
                "lsl_markers_xdf": str(getattr(result, "lsl_markers_xdf", "") or ""),
                "trigger_dictionary_path": str(getattr(result, "trigger_dictionary_path", "") or ""),
                "session_metadata_path": str(getattr(result, "session_metadata_path", "") or ""),
                "recording_paths": [str(path) for path in list(getattr(result, "recording_paths", []) or [])],
                "topup_summary": dict(topup_summary),
                "operator_completion_message": operator_message,
                "warnings": list(getattr(result, "warnings", []) or []),
            },
            create=True,
        )
        if _env_flag("PPS_FOCUS_VALIDATION_REPORT") or _env_flag("PPS_FOCUS_VALIDATION_AUTO_CLICK"):
            try:
                _validation_capture_part_snapshot(self, label="part_complete")
            except Exception:
                pass
        self._maybe_open_analysis_review(result)
        self._shutdown_owned_audio_engine()
        if self.companion_service is None:
            self.timer.stop()
        if _package_is_split_part(self.package) and bool(result.completed):
            self._auto_load_next_split_part_after_completion(completion_message=operator_message)

    def _maybe_open_analysis_review(self, result: Any) -> None:
        if not bool(getattr(result, "completed", False)):
            return
        if _env_flag("PPS_FOCUS_DISABLE_ANALYSIS_POPUP"):
            return
        capture_options = dict(getattr(result, "capture_options", {}) or {})
        if not bool(capture_options.get("write_analysis_csvs", True)):
            return
        try:
            catalog = refresh_analysis_catalog(self.output_root)
            entries = catalog.selectable_entries
            selected_dataset_id = selected_dataset_id_for_participant(
                catalog,
                str(getattr(self.package, "participant_id", "") or getattr(result, "participant_id", "") or ""),
            )
            if entries and selected_dataset_id:
                selected_entry = next((entry for entry in entries if str(entry.get("dataset_id") or "") == selected_dataset_id), entries[0])
                data = load_analysis_dataset(selected_entry)
                if not data.has_analysis_tables:
                    return
                self.analysis_review_dialog = AnalysisReviewDialog(
                    self.q,
                    self.dialog,
                    data,
                    dataset_entries=entries,
                    selected_dataset_id=selected_dataset_id,
                )
                self.analysis_review_dialog.show()
                return
            if _package_is_split_part(self.package):
                return
            outputs = dict(getattr(result, "analysis_outputs", {}) or {})
            events_csv = getattr(result, "events_csv", None)
            if events_csv not in (None, ""):
                outputs.setdefault("events_csv", events_csv)
            data = load_analysis_review_data(
                outputs,
                session_dir=getattr(result, "session_dir", None),
                summary_text=str(getattr(result, "summary_text", "") or ""),
            )
            if not data.has_analysis_tables:
                return
            self.analysis_review_dialog = AnalysisReviewDialog(self.q, self.dialog, data)
            self.analysis_review_dialog.show()
        except Exception as exc:  # noqa: BLE001 - analysis review must never break run completion.
            current = self.output_summary.toPlainText().strip()
            suffix = f"Analysis viewer unavailable: {exc}"
            self.output_summary.setPlainText(f"{current}\n{suffix}" if current else suffix)

    def grab_screenshot(self, path: Path) -> None:
        os.makedirs(_output_filesystem_path(path.parent), exist_ok=True)
        self.dialog.grab().save(_output_filesystem_path(path))

    def _apply_validation_window_rect(self, rect: tuple[int, int, int, int] | None) -> None:
        _apply_window_rect(self.dialog, rect)

    def exec(
        self,
        *,
        fullscreen: bool = True,
        auto_start: bool = True,
        auto_close_ms: int | None = None,
        screenshot_path: Path | None = None,
    ) -> int:
        self._start_companion_service()
        if auto_start:
            self.q["QTimer"].singleShot(350, self.start)
        if screenshot_path is not None:
            self.q["QTimer"].singleShot(250, lambda: self.grab_screenshot(screenshot_path))
        if auto_close_ms is not None:
            self.q["QTimer"].singleShot(int(auto_close_ms), self.dialog.accept)
        if not _env_flag("PPS_FOCUS_DISABLE_PREWARM"):
            self.q["QTimer"].singleShot(700, self.start_next_participant_prewarm)
        validation_rect = None if fullscreen else _validation_window_rect_for_display(self.q)
        _prepare_validation_window_placement(self.q, self.dialog, validation_rect)
        if fullscreen and hasattr(self.dialog, "showMaximized"):
            self.dialog.showMaximized()
        elif fullscreen and hasattr(self.dialog, "showFullScreen"):
            self.dialog.showFullScreen()
        else:
            self.dialog.show()
        if validation_rect is not None:
            self._apply_validation_window_rect(validation_rect)
        self.dialog.exec()
        return int(self.exit_code)


def run_focus_window(
    session_manifest: Path,
    *,
    capture_options: SessionCaptureOptions | None = None,
    enable_missed_trial_topup: bool = True,
    companion_enabled: bool = True,
    companion_host: str = DEFAULT_COMPANION_HOST,
    companion_port: int = DEFAULT_COMPANION_PORT,
    companion_advertise_ip: str = "",
    manual_start: bool = False,
    fullscreen: bool = True,
    auto_close_ms: int | None = None,
    screenshot_path: Path | None = None,
) -> int:
    q = _require_qt()
    package = load_run_package(session_manifest)
    set_windows_app_user_model_id("PPS.Toolkit.FocusMode")
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    app.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))
    validation_engine: _ValidationFastAudioEngine | None = None
    controller_factory: Callable[..., Any] | None = None
    validation_audio_requested = _env_flag("PPS_FOCUS_VALIDATION_REALTIME_AUDIO") or _env_flag("PPS_FOCUS_VALIDATION_FAST_AUDIO")
    if not validation_audio_requested:
        readiness = assess_audio_runtime_readiness()
        _clear_dialog_audio_selection_if_validated_route_ready(readiness)
        if not readiness.publication_ready and not _show_audio_dependency_dialog(q, readiness=readiness):
            return 2
    if _env_flag("PPS_FOCUS_VALIDATION_REALTIME_AUDIO"):
        validation_engine = _ValidationFastAudioEngine(
            chunk_frames=max(64, _env_int("PPS_FOCUS_VALIDATION_AUDIO_CHUNK_FRAMES") or 4096),
            realtime=True,
        )
    elif _env_flag("PPS_FOCUS_VALIDATION_FAST_AUDIO"):
        validation_engine = _ValidationFastAudioEngine()
    if validation_engine is not None:

        def _factory(package_obj: Any, *, capture_options: SessionCaptureOptions, **kwargs: Any) -> SessionRunnerController:
            return SessionRunnerController(
                package_obj,
                audio_engine=validation_engine,
                capture_options=capture_options,
                enable_topup=bool(kwargs.get("enable_topup")),
                runner_metadata=kwargs.get("runner_metadata"),
                topup_approval_callback=kwargs.get("topup_approval_callback"),
                instruction_continue_callback=kwargs.get("instruction_continue_callback"),
            )

        controller_factory = _factory
    window = FocusModeWindow(
        q,
        package,
        capture_options=capture_options,
        enable_missed_trial_topup=enable_missed_trial_topup,
        controller_factory=controller_factory,
        companion_enabled=companion_enabled,
        companion_host=companion_host,
        companion_port=companion_port,
        companion_advertise_ip=companion_advertise_ip,
    )
    apply_qt_app_icon(q, app=app, window=window.dialog)
    validation_clicks: list[dict[str, Any]] = []
    if _env_flag("PPS_FOCUS_VALIDATION_PARTICIPANT_EMULATOR"):
        validation_clicks = _install_validation_participant_emulator(q, window)
        if auto_close_ms is None:
            auto_close_ms = _env_int("PPS_FOCUS_VALIDATION_AUTO_CLOSE_MS")
    elif _env_flag("PPS_FOCUS_VALIDATION_AUTO_CLICK"):
        validation_clicks = _install_validation_auto_clicker(q, window)
        if auto_close_ms is None:
            auto_close_ms = _env_int("PPS_FOCUS_VALIDATION_AUTO_CLOSE_MS")
    exit_code = window.exec(
        fullscreen=fullscreen,
        auto_start=not manual_start,
        auto_close_ms=auto_close_ms,
        screenshot_path=screenshot_path,
    )
    report_path = os.environ.get("PPS_FOCUS_VALIDATION_REPORT", "").strip()
    if report_path:
        _write_validation_focus_report(
            Path(report_path),
            session_manifest=session_manifest,
            package=package,
            exit_code=exit_code,
            window=window,
            validation_clicks=validation_clicks,
            engine=validation_engine,
        )
    return exit_code


def run_launcher_window(
    *,
    capture_options: SessionCaptureOptions | None = None,
    enable_missed_trial_topup: bool = True,
    companion_enabled: bool = True,
    companion_host: str = DEFAULT_COMPANION_HOST,
    companion_port: int = DEFAULT_COMPANION_PORT,
    companion_advertise_ip: str = "",
    participant_id: str = "",
    initial_message: str = "",
) -> int:
    q = _require_qt()
    set_windows_app_user_model_id("PPS.Toolkit.FocusMode")
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    app.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))

    runner_settings = load_profile_runner_settings(state_root=DEFAULT_DASHBOARD_STATE_ROOT, default_output_folder=DEFAULT_SESSION_ROOT)
    diary_settings = load_runner_settings()
    initial_diary = current_runner_diary_path()
    diary_context = latest_diary_context(initial_diary) if initial_diary is not None else {}
    initial_profile = str(
        runner_settings.get("active_profile_id")
        or diary_settings.get("last_profile_id")
        or diary_context.get("profile_id")
        or STUDY5_PROFILE_ID
    ).strip()
    validation_participant = os.environ.get("PPS_FOCUS_VALIDATION_PARTICIPANT_ID", "").strip()
    initial_participant = str(
        validation_participant
        or participant_id
        or runner_settings.get("participant_id")
        or diary_settings.get("last_participant_id")
        or diary_context.get("participant_id")
        or "P001"
    ).strip()
    initial_output_root = Path(str(runner_settings.get("active_output_folder") or current_runner_session_root())).expanduser()
    initial_session_name = str(
        diary_settings.get("active_session_name")
        or diary_settings.get("last_experiment_name")
        or diary_context.get("experiment_name")
        or initial_output_root.name
        or "PPS experiment"
    ).strip()
    active_environment: dict[str, Any] = {
        "root": initial_output_root,
        "profile_id": initial_profile,
        "participant_id": initial_participant,
        "session_name": initial_session_name,
        "runner_diary_path": initial_diary,
        "kind": "remembered",
    }

    profile_options = finished_profile_options()
    profile_values = {profile_id for profile_id, _label in profile_options}
    if initial_profile and initial_profile not in profile_values:
        profile_options.insert(0, (initial_profile, initial_profile))
        profile_values.add(initial_profile)
    editable_profile_options = [("", "Choose experiment profile..."), *profile_options]

    dialog = q["QDialog"]()
    _enable_standard_window_controls(q, dialog)
    dialog.setWindowTitle("PPS Experiment Runner")
    dialog.resize(880, 520)
    dialog.setMinimumSize(760, 480)
    dialog.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))
    apply_qt_app_icon(q, app=app, window=dialog)
    _prepare_validation_window_placement(q, dialog)

    selected_action: dict[str, Any] = {"open_environment": False, "phone_transfer": False}
    initializing: dict[str, bool] = {"busy": False}
    gate_shortcuts: dict[str, Any] = {}
    messages: queue.Queue[tuple[str, Any]] = queue.Queue()

    layout = q["QVBoxLayout"](dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(14)
    panel, panel_layout = _panel(q, "Experiment Environment")
    heading = q["QLabel"]("Choose how to open a PPS data collection session.")
    heading.setObjectName("mutedLabel")
    heading.setWordWrap(True)
    panel_layout.addWidget(heading)
    step_label = q["QLabel"](
        "Choose 1 Resume Last Session, 2 Resume Custom Session, 3 Start New Session, or 4 Send To Phone."
    )
    step_label.setObjectName("gateStepLabel")
    step_label.setWordWrap(True)
    panel_layout.addWidget(step_label)

    output_folder_input = q["QLineEdit"](str(initial_output_root))
    output_folder_input.setObjectName("outputFolderField")
    output_folder_input.setReadOnly(True)
    output_folder_input.setToolTip(str(initial_output_root))
    copy_button = q["QPushButton"]("Copy Path")
    copy_button.setObjectName("copyOutputFolderButton")
    output_widget = q["QWidget"]()
    output_layout = q["QHBoxLayout"](output_widget)
    output_layout.setContentsMargins(0, 0, 0, 0)
    output_layout.setSpacing(8)
    output_layout.addWidget(output_folder_input, 1)
    output_layout.addWidget(copy_button)
    panel_layout.addWidget(_field_row(q, "Output Folder", output_widget))

    profile_combo = _combo(q, editable_profile_options, current=initial_profile)
    profile_combo.setObjectName("environmentProfileCombo")
    profile_combo.setEnabled(False)
    panel_layout.addWidget(_field_row(q, "Experiment Profile", profile_combo))

    session_name_input = q["QLineEdit"](initial_session_name)
    session_name_input.setObjectName("sessionNameField")
    session_name_input.setReadOnly(True)
    session_name_input.setPlaceholderText("My Experiment")
    panel_layout.addWidget(_field_row(q, "Session Name", session_name_input))

    message = q["QLabel"](
        initial_message
        or "Current decision: resume from memory, choose a session folder to scan, or start a new session."
    )
    message.setObjectName("gateStatusLabel")
    message.setWordWrap(True)
    panel_layout.addWidget(message)
    progress = q["QProgressBar"]()
    progress.setRange(0, 1000)
    progress.setValue(0)
    progress.setVisible(False)
    panel_layout.addWidget(progress)

    buttons = q["QHBoxLayout"]()
    resume_button = q["QPushButton"]("1 Resume Last Session")
    resume_button.setObjectName("resumeLastSessionButton")
    resume_button.setProperty("class", "primary")
    resume_button.setProperty("decisionTone", "resume")
    resume_custom_button = q["QPushButton"]("2 Resume Custom Session")
    resume_custom_button.setObjectName("resumeCustomSessionButton")
    resume_custom_button.setProperty("decisionTone", "custom")
    start_new_button = q["QPushButton"]("3 Start New Session")
    start_new_button.setObjectName("startNewSessionButton")
    start_new_button.setProperty("decisionTone", "start")
    phone_button = q["QPushButton"]("4 Send To Phone")
    phone_button.setObjectName("sendToPhoneButton")
    phone_button.setProperty("decisionTone", "phone")
    close_button = q["QPushButton"]("Close")
    buttons.addWidget(resume_button)
    buttons.addWidget(resume_custom_button)
    buttons.addWidget(start_new_button)
    buttons.addWidget(phone_button)
    buttons.addStretch(1)
    buttons.addWidget(close_button)
    panel_layout.addLayout(buttons)
    layout.addWidget(panel)
    layout.addStretch(1)

    def _capture_options_for_launcher() -> dict[str, Any]:
        return _capture_options_payload(capture_options)

    def _selected_parent() -> Path:
        return Path(output_folder_input.text().strip()).expanduser()

    def _selected_profile() -> str:
        return str(profile_combo.currentData() or "").strip()

    def _session_name() -> str:
        return str(session_name_input.text() or "").strip()

    def _session_slug() -> str:
        return slugify_identifier(_session_name(), fallback="")

    def _resume_ready() -> bool:
        root = Path(active_environment.get("root") or "")
        return root.expanduser().is_dir() and bool(str(active_environment.get("profile_id") or "").strip())

    def _set_widget_gate_state(widget: Any, state: str) -> None:
        _refresh_qt_dynamic_property(widget, "gateState", state)

    def _set_attention(widget: Any, state: str) -> None:
        _refresh_qt_dynamic_property(widget, "attention", state)

    def _set_profile_combo_current(profile_id: str) -> None:
        profile = str(profile_id or "").strip()
        was_blocked = profile_combo.blockSignals(True)
        try:
            if not profile:
                profile_combo.setCurrentIndex(0)
                return
            index = profile_combo.findData(profile)
            if index < 0:
                profile_combo.addItem(profile, profile)
                index = profile_combo.findData(profile)
            if index >= 0:
                profile_combo.setCurrentIndex(index)
        finally:
            profile_combo.blockSignals(was_blocked)

    def _decision_shortcuts_enabled() -> bool:
        return not initializing["busy"]

    def _update_decision_shortcuts() -> None:
        resume_shortcut = gate_shortcuts.get("resume")
        custom_shortcut = gate_shortcuts.get("custom")
        start_shortcut = gate_shortcuts.get("start")
        phone_shortcut = gate_shortcuts.get("phone")
        if resume_shortcut is not None:
            resume_shortcut.setEnabled(_decision_shortcuts_enabled() and _resume_ready())
        if custom_shortcut is not None:
            custom_shortcut.setEnabled(_decision_shortcuts_enabled())
        if start_shortcut is not None:
            start_shortcut.setEnabled(_decision_shortcuts_enabled())
        if phone_shortcut is not None:
            phone_shortcut.setEnabled(_decision_shortcuts_enabled())

    def _refresh_gate_attention() -> None:
        step_label.setText(
            "Choose 1 Resume Last Session, 2 Resume Custom Session, 3 Start New Session, or 4 Send To Phone."
        )
        _set_attention(step_label, "current")
        _set_widget_gate_state(output_folder_input, "locked")
        _set_widget_gate_state(profile_combo, "locked")
        _set_widget_gate_state(session_name_input, "locked")
        _set_attention(resume_button, "current" if _resume_ready() else "locked")
        _set_attention(resume_custom_button, "available")
        _set_attention(start_new_button, "available")
        _set_attention(phone_button, "available")
        _set_attention(message, "current")
        _update_decision_shortcuts()

    def _set_environment_busy(busy: bool) -> None:
        initializing["busy"] = busy
        resume_button.setEnabled((not busy) and _resume_ready())
        resume_custom_button.setEnabled(not busy)
        start_new_button.setEnabled(not busy)
        phone_button.setEnabled(not busy)
        close_button.setEnabled(not busy)
        output_folder_input.setEnabled(not busy)
        profile_combo.setEnabled(False)
        session_name_input.setEnabled(not busy)
        copy_button.setEnabled(not busy)
        progress.setVisible(busy)
        if busy:
            progress.setRange(0, 0)
        else:
            progress.setRange(0, 1000)
            progress.setValue(0)
        _refresh_gate_attention()

    def _lock_for_existing_environment(context: dict[str, Any]) -> None:
        root = Path(context.get("root") or initial_output_root).expanduser()
        profile_id = str(context.get("profile_id") or initial_profile or "").strip()
        participant = str(context.get("participant_id") or initial_participant or "P001").strip()
        session_name = str(context.get("session_name") or root.name or initial_session_name).strip()
        active_environment.update(
            {
                "root": root,
                "profile_id": profile_id,
                "participant_id": participant or "P001",
                "session_name": session_name,
                "runner_diary_path": context.get("runner_diary_path"),
                "kind": "existing_environment",
            }
        )
        output_folder_input.setReadOnly(True)
        output_folder_input.setText(str(root))
        output_folder_input.setToolTip(str(root))
        _set_profile_combo_current(profile_id)
        profile_combo.setEnabled(False)
        session_name_input.setReadOnly(True)
        session_name_input.setText(session_name)
        resume_button.setEnabled(_resume_ready())
        markers = ", ".join(context.get("markers") or ["environment marker"])
        message.setText(f"Existing session environment found ({markers}).")
        _refresh_gate_attention()

    def _classify_custom_session_folder(folder: Path) -> dict[str, Any]:
        context = _classify_launcher_output_folder(
            folder,
            fallback_profile_id="",
            fallback_session_name="",
            fallback_participant_id=initial_participant,
        )
        if context.get("kind") != "existing_environment":
            raise ValueError("No PPS session metadata was found in that folder. Use Start New Session for empty folders.")
        if not str(context.get("profile_id") or "").strip():
            raise ValueError("That folder has PPS metadata but no experiment profile. Choose a complete PPS session folder.")
        return context

    def _copy_output_path() -> None:
        try:
            app.clipboard().setText(output_folder_input.text())
            message.setText("Output folder path copied.")
        except Exception as exc:
            message.setText(f"Could not copy path: {exc}")

    def _choose_custom_session_folder() -> None:
        current_root = Path(str(active_environment.get("root") or initial_output_root)).expanduser()
        start_folder = current_root if current_root.is_dir() else DEFAULT_SESSION_ROOT
        folder = q["QFileDialog"].getExistingDirectory(
            dialog,
            "Choose Session Folder",
            str(start_folder),
        )
        if not folder:
            return
        try:
            context = _classify_custom_session_folder(Path(folder))
        except Exception as exc:
            message.setText(str(exc))
            _refresh_gate_attention()
            return
        _lock_for_existing_environment(context)
        _resume_environment(event_type="resume_custom_session_clicked")

    def _resume_environment(*, event_type: str = "resume_last_session_clicked") -> None:
        if not _resume_ready():
            message.setText("No remembered session is ready. Use Resume Custom Session or Start New Session.")
            return
        output_root = Path(active_environment.get("root") or initial_output_root).expanduser().resolve()
        profile_id = str(active_environment.get("profile_id") or initial_profile or "").strip()
        participant = str(active_environment.get("participant_id") or initial_participant or "P001").strip()
        session_name = str(active_environment.get("session_name") or initial_session_name or output_root.name).strip()
        diary_path = active_environment.get("runner_diary_path") or find_output_diary(output_root)
        remember_runner_context(
            session_root=output_root,
            diary_path=diary_path,
            experiment_name=session_name,
            profile_id=profile_id,
            participant_id=participant,
            capture_options=_capture_options_for_launcher(),
        )
        update_profile_runner_settings(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            output_folder=output_root,
            profile_id=profile_id,
            participant_id=participant,
            capture_options=_capture_options_for_launcher(),
        )
        _append_output_diary_event(
            event_type,
            session_root=output_root,
            experiment_name=session_name,
            profile_id=profile_id,
            participant_id=participant,
            capture_options=_capture_options_for_launcher(),
            create=True,
        )
        selected_action["open_environment"] = True
        dialog.accept()

    def _start_environment_initialization(parent: Path, profile_id: str, session_name: str) -> None:
        parent = Path(parent).expanduser()
        profile = str(profile_id or "").strip()
        label = str(session_name or "").strip()
        if not parent.is_dir():
            message.setText("Choose an existing output parent folder.")
            return
        if not profile:
            message.setText("Choose an experiment profile.")
            return
        if not slugify_identifier(label, fallback=""):
            message.setText("Enter a Windows-safe session name.")
            return
        _set_environment_busy(True)
        message.setText("Creating new session environment...")

        def _progress_callback(payload: dict[str, Any]) -> None:
            messages.put(("progress", dict(payload)))

        def _worker() -> None:
            try:
                result = initiate_data_collection_environment(
                    parent_folder=parent,
                    profile_id=profile,
                    session_name=label,
                    participant_id="P001",
                    capture_options=capture_options,
                    progress_callback=_progress_callback,
                )
            except Exception as exc:
                messages.put(("error", str(exc)))
            else:
                messages.put(("done", result))

        threading.Thread(target=_worker, name="pps-environment-init", daemon=True).start()

    def _new_session_default_parent() -> Path:
        current_root = Path(str(active_environment.get("root") or initial_output_root)).expanduser()
        if current_root.is_dir() and current_root.name:
            return current_root.parent if current_root.parent.is_dir() else current_root
        return DEFAULT_SESSION_ROOT

    def _open_start_new_session_dialog() -> dict[str, Any] | None:
        setup_dialog = q["QDialog"](dialog)
        setup_dialog.setObjectName("startNewSessionDialog")
        setup_dialog.setWindowTitle("Start New Session")
        setup_dialog.resize(640, 260)
        setup_dialog.setMinimumSize(560, 240)
        setup_dialog.setStyleSheet(dialog.styleSheet())
        _prepare_validation_window_placement(q, setup_dialog)
        setup_layout = q["QVBoxLayout"](setup_dialog)
        setup_layout.setContentsMargins(16, 16, 16, 16)
        setup_layout.setSpacing(12)

        intro = q["QLabel"]("Define the local parent folder, experiment profile, and session name.")
        intro.setObjectName("mutedLabel")
        intro.setWordWrap(True)
        setup_layout.addWidget(intro)

        parent_input = q["QLineEdit"](str(_new_session_default_parent()))
        parent_input.setObjectName("newSessionParentField")
        parent_input.setReadOnly(True)
        parent_button = q["QPushButton"]("Choose Parent Folder")
        parent_button.setObjectName("newSessionParentButton")
        parent_widget = q["QWidget"]()
        parent_layout = q["QHBoxLayout"](parent_widget)
        parent_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.setSpacing(8)
        parent_layout.addWidget(parent_input, 1)
        parent_layout.addWidget(parent_button)
        setup_layout.addWidget(_field_row(q, "Parent Folder", parent_widget))

        new_profile_combo = _combo(q, editable_profile_options, current=initial_profile)
        new_profile_combo.setObjectName("newSessionProfileCombo")
        setup_layout.addWidget(_field_row(q, "Experiment Profile", new_profile_combo))

        new_session_name = q["QLineEdit"]("")
        new_session_name.setObjectName("newSessionNameField")
        new_session_name.setPlaceholderText("My Experiment")
        setup_layout.addWidget(_field_row(q, "Session Name", new_session_name))

        status = q["QLabel"]("")
        status.setObjectName("newSessionStatusLabel")
        status.setWordWrap(True)
        setup_layout.addWidget(status)

        action_row = q["QHBoxLayout"]()
        create_button = q["QPushButton"]("Start Session")
        create_button.setObjectName("createNewSessionButton")
        create_button.setProperty("class", "primary")
        cancel_button = q["QPushButton"]("Cancel")
        action_row.addStretch(1)
        action_row.addWidget(create_button)
        action_row.addWidget(cancel_button)
        setup_layout.addLayout(action_row)

        result: dict[str, Any] = {}

        def _new_session_errors() -> list[str]:
            parent = Path(parent_input.text().strip()).expanduser()
            if not parent_input.text().strip():
                return ["Choose an output parent folder."]
            if not parent.is_dir():
                return ["Parent folder must already exist."]
            if not str(new_profile_combo.currentData() or "").strip():
                return ["Choose an experiment profile."]
            if not slugify_identifier(new_session_name.text().strip(), fallback=""):
                return ["Enter a Windows-safe session name."]
            return []

        def _refresh_new_session_state() -> None:
            errors = _new_session_errors()
            create_button.setEnabled(not errors)
            if errors:
                status.setText(errors[0])
            else:
                preview = Path(parent_input.text().strip()).expanduser() / f"{slugify_identifier(new_session_name.text(), fallback='session')}_<timestamp>"
                status.setText(f"Ready to create {preview}.")

        def _choose_new_parent() -> None:
            current = Path(parent_input.text().strip()).expanduser()
            folder = q["QFileDialog"].getExistingDirectory(
                setup_dialog,
                "Choose Parent Folder",
                str(current if current.is_dir() else DEFAULT_SESSION_ROOT),
            )
            if folder:
                parent_input.setText(str(Path(folder)))
                _refresh_new_session_state()

        def _accept_new_session() -> None:
            errors = _new_session_errors()
            if errors:
                status.setText(errors[0])
                return
            result.update(
                {
                    "parent": Path(parent_input.text().strip()).expanduser(),
                    "profile_id": str(new_profile_combo.currentData() or "").strip(),
                    "session_name": new_session_name.text().strip(),
                }
            )
            setup_dialog.accept()

        parent_button.clicked.connect(_choose_new_parent)
        parent_input.textChanged.connect(lambda _text: _refresh_new_session_state())
        new_profile_combo.currentIndexChanged.connect(lambda _index: _refresh_new_session_state())
        new_session_name.textChanged.connect(lambda _text: _refresh_new_session_state())
        new_session_name.returnPressed.connect(_accept_new_session)
        create_button.clicked.connect(_accept_new_session)
        cancel_button.clicked.connect(setup_dialog.reject)
        _refresh_new_session_state()

        if setup_dialog.exec() != q["QDialog"].DialogCode.Accepted:
            return None
        return result

    def _start_new_session() -> None:
        result = _open_start_new_session_dialog()
        if not result:
            return
        _start_environment_initialization(
            Path(result["parent"]),
            str(result["profile_id"]),
            str(result["session_name"]),
        )

    def _send_to_phone() -> None:
        selected_action["phone_transfer"] = True
        selected_action["open_environment"] = False
        dialog.accept()

    def _drain_environment_messages() -> None:
        while not messages.empty():
            kind, payload = messages.get_nowait()
            if kind == "progress":
                total = int(payload.get("total") or 0)
                current = int(payload.get("current") or 0)
                if total > 0:
                    progress.setRange(0, 1000)
                    progress.setValue(int(max(0.0, min(1.0, current / total)) * 1000))
                else:
                    progress.setRange(0, 0)
                progress_message = str(payload.get("message") or "Preparing environment")
                detail = str(payload.get("detail") or "").strip()
                message.setText(f"{progress_message}: {detail}" if detail else progress_message)
            elif kind == "error":
                message.setText(str(payload))
                _set_environment_busy(False)
            elif kind == "done":
                root_text = str(payload.get("environment_root") or "").strip()
                if root_text:
                    active_environment.update(
                        {
                            "root": Path(root_text),
                            "profile_id": str(payload.get("profile_id") or _selected_profile() or "").strip(),
                            "participant_id": str(payload.get("participant_id") or "P001").strip(),
                            "session_name": str(payload.get("session_name") or _session_name() or "").strip(),
                            "runner_diary_path": Path(str(payload.get("diary_path"))) if payload.get("diary_path") else None,
                            "kind": "existing_environment",
                        }
                    )
                    _lock_for_existing_environment(active_environment)
                selected_action["open_environment"] = True
                message.setText("Environment ready.")
                dialog.accept()

    def _focus_is_editing_gate_text() -> bool:
        return False

    def _resume_shortcut_activated() -> None:
        if _focus_is_editing_gate_text() or not _decision_shortcuts_enabled() or not resume_button.isEnabled():
            return
        resume_button.click()

    def _custom_shortcut_activated() -> None:
        if _focus_is_editing_gate_text() or not _decision_shortcuts_enabled() or not resume_custom_button.isEnabled():
            return
        resume_custom_button.click()

    def _start_shortcut_activated() -> None:
        if _focus_is_editing_gate_text() or not _decision_shortcuts_enabled() or not start_new_button.isEnabled():
            return
        start_new_button.click()

    def _phone_shortcut_activated() -> None:
        if _focus_is_editing_gate_text() or not _decision_shortcuts_enabled() or not phone_button.isEnabled():
            return
        phone_button.click()

    timer = q["QTimer"](dialog)
    timer.timeout.connect(_drain_environment_messages)
    timer.start(100)

    copy_button.clicked.connect(_copy_output_path)
    resume_custom_button.clicked.connect(_choose_custom_session_folder)
    resume_button.clicked.connect(lambda _checked=False: _resume_environment(event_type="resume_last_session_clicked"))
    start_new_button.clicked.connect(_start_new_session)
    phone_button.clicked.connect(_send_to_phone)
    close_button.clicked.connect(dialog.reject)
    gate_shortcuts["resume"] = q["QShortcut"](q["QKeySequence"]("1"), dialog)
    gate_shortcuts["resume"].setContext(q["Qt"].ShortcutContext.ApplicationShortcut)
    gate_shortcuts["resume"].activated.connect(_resume_shortcut_activated)
    gate_shortcuts["custom"] = q["QShortcut"](q["QKeySequence"]("2"), dialog)
    gate_shortcuts["custom"].setContext(q["Qt"].ShortcutContext.ApplicationShortcut)
    gate_shortcuts["custom"].activated.connect(_custom_shortcut_activated)
    gate_shortcuts["start"] = q["QShortcut"](q["QKeySequence"]("3"), dialog)
    gate_shortcuts["start"].setContext(q["Qt"].ShortcutContext.ApplicationShortcut)
    gate_shortcuts["start"].activated.connect(_start_shortcut_activated)
    gate_shortcuts["phone"] = q["QShortcut"](q["QKeySequence"]("4"), dialog)
    gate_shortcuts["phone"].setContext(q["Qt"].ShortcutContext.ApplicationShortcut)
    gate_shortcuts["phone"].activated.connect(_phone_shortcut_activated)
    resume_button.setEnabled(_resume_ready())
    _refresh_gate_attention()

    def _validation_auto_environment() -> None:
        target_profile = os.environ.get("PPS_FOCUS_VALIDATION_PROFILE", STUDY5_PROFILE_ID).strip() or STUDY5_PROFILE_ID
        parent = Path(os.environ.get("PPS_FOCUS_VALIDATION_OUTPUT_ROOT", "") or DEFAULT_SESSION_ROOT).expanduser()
        os.makedirs(_output_filesystem_path(parent), exist_ok=True)
        _start_environment_initialization(parent, target_profile, "Study 5 validation")

    if _env_flag("PPS_FOCUS_VALIDATION_LAUNCHER_AUTO_CLICK"):
        q["QTimer"].singleShot(200, _validation_auto_environment)

    accepted = dialog.exec() == q["QDialog"].DialogCode.Accepted
    if accepted and selected_action.get("phone_transfer"):
        return _run_phone_transfer_window(
            capture_options=capture_options,
            companion_enabled=companion_enabled,
            companion_host=companion_host,
            companion_port=companion_port,
            companion_advertise_ip=companion_advertise_ip,
            participant_id=str(active_environment.get("participant_id") or initial_participant or "P001"),
        )
    if not accepted or not selected_action.get("open_environment"):
        return 1
    return _run_environment_operations_window(
        capture_options=capture_options,
        enable_missed_trial_topup=enable_missed_trial_topup,
        companion_enabled=companion_enabled,
        companion_host=companion_host,
        companion_port=companion_port,
        companion_advertise_ip=companion_advertise_ip,
        participant_id=str(active_environment.get("participant_id") or initial_participant or "P001"),
    )


def _phone_transfer_packages_for_manifest(manifest_path: Path) -> list[Any]:
    package = load_run_package(Path(manifest_path))
    packages: list[Any] = [package]
    seen = {mobile_package_id(package)}
    for raw_path in list(getattr(package, "sibling_part_manifest_paths", []) or []):
        try:
            sibling = load_run_package(Path(raw_path))
        except Exception:
            continue
        package_id = mobile_package_id(sibling)
        if package_id in seen:
            continue
        seen.add(package_id)
        packages.append(sibling)
    return packages


def _run_phone_transfer_window(
    *,
    capture_options: SessionCaptureOptions | None = None,
    companion_enabled: bool = True,
    companion_host: str = DEFAULT_COMPANION_HOST,
    companion_port: int = DEFAULT_COMPANION_PORT,
    companion_advertise_ip: str = "",
    participant_id: str = "",
    initial_message: str = "",
) -> int:
    q = _require_qt()
    set_windows_app_user_model_id("PPS.Toolkit.FocusMode")
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    app.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))

    dialog = q["QDialog"]()
    _enable_standard_window_controls(q, dialog)
    dialog.setWindowTitle("PPS Experiment Runner - Send To Phone")
    dialog.resize(920, 720)
    dialog.setMinimumSize(760, 620)
    dialog.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))
    apply_qt_app_icon(q, app=app, window=dialog)
    _prepare_validation_window_placement(q, dialog)

    runner_settings = load_profile_runner_settings(state_root=DEFAULT_DASHBOARD_STATE_ROOT, default_output_folder=DEFAULT_SESSION_ROOT)
    initial_settings = load_runner_settings()
    initial_diary = current_runner_diary_path()
    initial_diary_context = latest_diary_context(initial_diary) if initial_diary is not None else {}
    initial_profile = str(
        runner_settings.get("active_profile_id")
        or initial_settings.get("last_profile_id")
        or initial_diary_context.get("profile_id")
        or STUDY5_PROFILE_ID
    ).strip()
    initial_participant = str(
        participant_id
        or runner_settings.get("participant_id")
        or initial_settings.get("last_participant_id")
        or initial_diary_context.get("participant_id")
        or "P001"
    ).strip()
    output_root_state: dict[str, Path] = {
        "path": Path(runner_settings.get("active_output_folder") or current_runner_session_root()).expanduser()
    }
    service_state: dict[str, Any] = {
        "service": None,
        "packages": [],
        "pairing_uri": "",
        "qr_png": b"",
        "transfer_id": "",
    }
    preparation_messages: queue.Queue[tuple[str, Any]] = queue.Queue()
    preparation_cancel = threading.Event()
    preparation_thread: dict[str, threading.Thread | None] = {"thread": None}

    layout = q["QVBoxLayout"](dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(12)
    panel, panel_layout = _panel(q, "Send Experiment To Phone")
    heading = q["QLabel"](
        "Prepare the selected profile for a phone-owned run. The PC only serves the study package; "
        "the Android app stores the experiment session locally."
    )
    heading.setObjectName("mutedLabel")
    heading.setWordWrap(True)
    panel_layout.addWidget(heading)

    profile_options = finished_profile_options()
    available_profiles = {profile_id for profile_id, _label in profile_options}
    profile_combo = _combo(q, profile_options, current=initial_profile if initial_profile in available_profiles else STUDY5_PROFILE_ID)
    profile_combo.setObjectName("phoneTransferProfileCombo")
    if profile_combo.currentIndex() < 0 and profile_options:
        profile_combo.setCurrentIndex(0)
    panel_layout.addWidget(_field_row(q, "Experiment Profile", profile_combo))

    participant_combo = q["QComboBox"]()
    participant_combo.setObjectName("phoneTransferParticipantCombo")
    panel_layout.addWidget(_field_row(q, "Phone Schedule", participant_combo))

    output_folder_input = q["QLineEdit"](str(output_root_state["path"]))
    output_folder_input.setObjectName("phoneTransferOutputFolderField")
    output_folder_input.setReadOnly(True)
    output_folder_input.setToolTip("Used only as a staging/cache location for prepared phone assets.")
    panel_layout.addWidget(_field_row(q, "Asset Staging Folder", output_folder_input))

    transport_combo = q["QComboBox"]()
    transport_combo.setObjectName("phoneTransferTransportCombo")
    transport_combo.addItem("Same Wi-Fi LAN", "lan")
    transport_combo.addItem("Wi-Fi Direct fallback", "wifi_direct")
    panel_layout.addWidget(_field_row(q, "Bridge", transport_combo))

    wifi_status = _windows_wifi_direct_status()
    wifi_label = q["QLabel"](str(wifi_status.get("message") or ""))
    wifi_label.setObjectName("mutedLabel")
    wifi_label.setWordWrap(True)
    panel_layout.addWidget(wifi_label)

    message = q["QLabel"](initial_message or "Choose a profile and schedule, then prepare the phone package.")
    message.setObjectName("mutedLabel")
    message.setWordWrap(True)
    panel_layout.addWidget(message)
    progress = q["QProgressBar"]()
    progress.setRange(0, 1000)
    progress.setValue(0)
    progress.setVisible(False)
    panel_layout.addWidget(progress)

    package_label = q["QLabel"]("No phone package prepared yet.")
    package_label.setObjectName("metricValue")
    package_label.setWordWrap(True)
    panel_layout.addWidget(package_label)

    qr_label = q["QLabel"]("")
    qr_label.setObjectName("companionQrCode")
    qr_label.setFixedSize(320, 320)
    qr_label.setAlignment(q["Qt"].AlignmentFlag.AlignCenter)
    panel_layout.addWidget(qr_label, 0, q["Qt"].AlignmentFlag.AlignHCenter)
    endpoint_label = q["QLabel"]("")
    endpoint_label.setObjectName("metricValue")
    endpoint_label.setWordWrap(True)
    panel_layout.addWidget(endpoint_label)
    uri_field = q["QLineEdit"]("")
    uri_field.setObjectName("phoneTransferPairingUriField")
    uri_field.setReadOnly(True)
    panel_layout.addWidget(uri_field)

    buttons = q["QHBoxLayout"]()
    prepare_button = q["QPushButton"]("Prepare And Show QR")
    prepare_button.setObjectName("phoneTransferPrepareButton")
    prepare_button.setProperty("class", "primary")
    stop_button = q["QPushButton"]("Stop Bridge")
    stop_button.setObjectName("phoneTransferStopButton")
    stop_button.setEnabled(False)
    close_button = q["QPushButton"]("Close")
    buttons.addWidget(prepare_button)
    buttons.addWidget(stop_button)
    buttons.addStretch(1)
    buttons.addWidget(close_button)
    panel_layout.addLayout(buttons)
    layout.addWidget(panel)

    def _current_profile() -> str:
        return str(profile_combo.currentData() or "").strip()

    def _selected_participant() -> str:
        return str(participant_combo.currentData() or "").strip()

    def _refresh_participant_options(preferred: str = "") -> None:
        profile = _current_profile()
        participants = profile_participant_ids(profile) if profile else []
        current = preferred or _selected_participant() or initial_participant or "P001"
        participant_combo.blockSignals(True)
        participant_combo.clear()
        for participant in participants:
            participant_combo.addItem(participant, participant)
        index = participant_combo.findData(current)
        participant_combo.setCurrentIndex(index if index >= 0 else (0 if participants else -1))
        participant_combo.blockSignals(False)
        prepare_button.setEnabled(bool(profile and participants and companion_enabled))

    def _set_busy(busy: bool) -> None:
        profile_combo.setEnabled(not busy)
        participant_combo.setEnabled(not busy)
        transport_combo.setEnabled(not busy)
        prepare_button.setEnabled((not busy) and companion_enabled and bool(_current_profile()) and bool(_selected_participant()))
        close_button.setEnabled(not busy)
        stop_button.setEnabled((not busy) and service_state.get("service") is not None)
        progress.setVisible(busy)
        progress.setRange(0, 0 if busy else 1000)
        if not busy:
            progress.setValue(0)

    def _refresh_qr() -> None:
        uri = str(service_state.get("pairing_uri") or "")
        uri_field.setText(uri)
        endpoint_label.setText("")
        if uri:
            endpoint_label.setText(f"Bridge ready at http://{config.advertised_host}:{config.port}")
        pixmap = q["QPixmap"]()
        qr_png = service_state.get("qr_png") or b""
        if qr_png and pixmap.loadFromData(qr_png):
            qr_label.setText("")
            qr_label.setPixmap(
                pixmap.scaled(
                    q["QSize"](320, 320),
                    q["Qt"].AspectRatioMode.KeepAspectRatio,
                    q["Qt"].TransformationMode.SmoothTransformation,
                )
            )
        else:
            qr_label.setPixmap(q["QPixmap"]())
            qr_label.setText("QR appears after preparation")

    def _stop_service() -> None:
        service = service_state.get("service")
        service_state["service"] = None
        if service is not None:
            try:
                service.stop()
            except Exception:
                pass
        stop_button.setEnabled(False)
        if service is not None:
            message.setText("Phone bridge stopped.")

    config = RunnerCompanionConfig(
        host=str(companion_host or DEFAULT_COMPANION_HOST),
        port=int(companion_port or DEFAULT_COMPANION_PORT),
        advertise_ip=str(companion_advertise_ip or choose_lan_ipv4() or ""),
    )

    def _start_service(packages: list[Any]) -> None:
        _stop_service()
        token = generate_companion_token()
        profile = _current_profile()
        participant = _selected_participant()
        transfer_id = slugify_identifier(
            f"{profile}-{participant}-phone-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            fallback=f"phone-{int(time.time())}",
        )
        transport = str(transport_combo.currentData() or "lan")
        pairing_uri = build_pairing_uri(
            host=config.advertised_host,
            port=config.port,
            session_id=transfer_id,
            token=token,
            mode="phone_export",
            transfer_id=transfer_id,
            transport=transport,
        )
        bridge = _PhoneTransferBridge(
            packages=packages,
            transfer_id=transfer_id,
            profile_id=profile,
            participant_id=participant,
            port=config.port,
        )
        service = RunnerCompanionService(bridge, token=token, config=config)
        service.start()
        service_state.update(
            {
                "service": service,
                "packages": packages,
                "pairing_uri": pairing_uri,
                "qr_png": pairing_qr_png_bytes(pairing_uri),
                "transfer_id": transfer_id,
            }
        )
        total_bytes = sum(
            int(asset.get("size_bytes") or 0)
            for package in packages
            for asset in build_mobile_package_manifest(package, phone_owned_session=True).get("assets", [])
        )
        package_label.setText(
            f"{len(packages)} phone package(s) ready, {total_bytes / (1024 * 1024):.1f} MiB assets. "
            "Scan with the Android companion and choose Run Experiment On Phone."
        )
        if transport == "wifi_direct":
            message.setText("Wi-Fi Direct fallback selected. Join the phone and PC to the same direct link, then scan this QR.")
        else:
            message.setText("Same-Wi-Fi bridge ready. Scan this QR from the Android companion.")
        stop_button.setEnabled(True)
        _refresh_qr()

    def _progress_callback(payload: dict[str, Any]) -> None:
        if preparation_cancel.is_set():
            raise RuntimeError("Preparation cancelled.")
        preparation_messages.put(("progress", dict(payload)))

    def _start_preparation() -> None:
        active = preparation_thread.get("thread")
        if active is not None and active.is_alive():
            return
        if not companion_enabled:
            message.setText("Phone companion bridge is disabled for this launch.")
            return
        profile = _current_profile()
        participant = _selected_participant()
        if not profile or not participant:
            message.setText("Choose a profile and phone schedule first.")
            return
        preparation_cancel.clear()
        _set_busy(True)
        message.setText("Preparing phone package...")

        def _worker() -> None:
            try:
                manifest = prepare_profile_focus_session(
                    profile,
                    participant,
                    session_root=output_root_state["path"],
                    progress_callback=_progress_callback,
                )
                packages = _phone_transfer_packages_for_manifest(Path(manifest))
            except Exception as exc:
                preparation_messages.put(("error", str(exc)))
            else:
                preparation_messages.put(("done", packages))

        worker = threading.Thread(target=_worker, name="pps-phone-transfer-prep", daemon=True)
        preparation_thread["thread"] = worker
        worker.start()

    def _drain_messages() -> None:
        while not preparation_messages.empty():
            kind, payload = preparation_messages.get_nowait()
            if kind == "progress":
                total = int(payload.get("total") or 0)
                current = int(payload.get("current") or 0)
                if total > 0:
                    progress.setRange(0, 1000)
                    progress.setValue(int(max(0.0, min(1.0, current / total)) * 1000))
                else:
                    progress.setRange(0, 0)
                detail = str(payload.get("detail") or payload.get("phase") or "").strip()
                message.setText(f"{payload.get('message') or 'Preparing phone package'}: {detail}" if detail else str(payload.get("message") or "Preparing phone package"))
            elif kind == "error":
                message.setText(str(payload))
                _set_busy(False)
            elif kind == "done":
                try:
                    _start_service(list(payload or []))
                except Exception as exc:
                    message.setText(f"Phone bridge could not start: {exc}")
                _set_busy(False)

    profile_combo.currentIndexChanged.connect(lambda _index: _refresh_participant_options())
    prepare_button.clicked.connect(_start_preparation)
    stop_button.clicked.connect(_stop_service)
    close_button.clicked.connect(dialog.accept)
    timer = q["QTimer"](dialog)
    timer.timeout.connect(_drain_messages)
    timer.start(100)
    _refresh_participant_options(initial_participant)
    _refresh_qr()
    accepted = dialog.exec() == q["QDialog"].DialogCode.Accepted
    _stop_service()
    return 0 if accepted else 1


def _run_environment_operations_window(
    *,
    capture_options: SessionCaptureOptions | None = None,
    enable_missed_trial_topup: bool = True,
    companion_enabled: bool = True,
    companion_host: str = DEFAULT_COMPANION_HOST,
    companion_port: int = DEFAULT_COMPANION_PORT,
    companion_advertise_ip: str = "",
    participant_id: str = "",
    initial_message: str = "",
) -> int:
    q = _require_qt()
    set_windows_app_user_model_id("PPS.Toolkit.FocusMode")
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    app.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))

    dialog = q["QDialog"]()
    _enable_standard_window_controls(q, dialog)
    dialog.setWindowTitle("PPS Experiment Runner")
    dialog.resize(900, 620)
    dialog.setMinimumSize(760, 520)
    dialog.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))
    apply_qt_app_icon(q, app=app, window=dialog)
    _prepare_validation_window_placement(q, dialog)

    selected_manifest: dict[str, Path | None] = {"path": None}
    runner_settings = load_profile_runner_settings(state_root=DEFAULT_DASHBOARD_STATE_ROOT, default_output_folder=DEFAULT_SESSION_ROOT)
    initial_settings = load_runner_settings()
    initial_diary = current_runner_diary_path()
    initial_diary_context = latest_diary_context(initial_diary) if initial_diary is not None else {}
    initial_profile = str(
        runner_settings.get("active_profile_id")
        or initial_settings.get("last_profile_id")
        or initial_diary_context.get("profile_id")
        or STUDY5_PROFILE_ID
    ).strip()
    validation_participant = os.environ.get("PPS_FOCUS_VALIDATION_PARTICIPANT_ID", "").strip()
    initial_participant = str(
        validation_participant
        or participant_id
        or runner_settings.get("participant_id")
        or initial_settings.get("last_participant_id")
        or initial_diary_context.get("participant_id")
        or "P001"
    ).strip()
    output_root_state: dict[str, Path] = {"path": Path(runner_settings.get("active_output_folder") or DEFAULT_SESSION_ROOT)}
    layout = q["QVBoxLayout"](dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(14)
    panel, panel_layout = _panel(q, "Prepare Participants And Run")
    heading = q["QLabel"]("Generate participant files for the active data collection environment, then open Focus Mode for the selected participant.")
    heading.setObjectName("mutedLabel")
    heading.setWordWrap(True)
    panel_layout.addWidget(heading)

    output_folder_input = q["QLineEdit"](str(output_root_state["path"]))
    output_folder_input.setReadOnly(True)
    output_folder_input.setObjectName("outputFolderField")
    output_folder_input.setToolTip("Participant session folders, bridge manifest, and output diary are written here.")
    choose_output_button = q["QPushButton"]("Choose Output Folder")
    choose_output_button.setObjectName("chooseOutputFolderButton")
    choose_output_button.setVisible(False)
    output_folder_widget = q["QWidget"]()
    output_folder_layout = q["QHBoxLayout"](output_folder_widget)
    output_folder_layout.setContentsMargins(0, 0, 0, 0)
    output_folder_layout.setSpacing(8)
    output_folder_layout.addWidget(output_folder_input, 1)
    output_folder_layout.addWidget(choose_output_button)
    panel_layout.addWidget(_field_row(q, "Output Folder", output_folder_widget))

    profile_options = finished_profile_options()
    available_profiles = {profile_id for profile_id, _label in profile_options}
    profile_combo = _combo(q, profile_options, current=initial_profile if initial_profile in available_profiles else STUDY5_PROFILE_ID)
    if profile_combo.currentIndex() < 0 and profile_options:
        profile_combo.setCurrentIndex(0)
    profile_combo.setEnabled(False)
    panel_layout.addWidget(_field_row(q, "Experiment Profile", profile_combo))

    participant_combo = q["QComboBox"]()
    participant_combo.setObjectName("participantCombo")
    panel_layout.addWidget(_field_row(q, "Participant", participant_combo))

    if initial_diary is not None:
        remember_runner_context(
            session_root=output_root_state["path"],
            diary_path=initial_diary,
            experiment_name=str(initial_diary_context.get("experiment_name") or ""),
            profile_id=str(initial_diary_context.get("profile_id") or initial_profile),
            participant_id=str(initial_diary_context.get("participant_id") or initial_participant),
            capture_options=dict(initial_diary_context.get("capture_options") or {}),
        )
    validation_launcher_auto = _env_flag("PPS_FOCUS_VALIDATION_LAUNCHER_AUTO_CLICK")

    asset_controls = q["QHBoxLayout"]()
    generate_button = q["QPushButton"]("Generate Audio Assets")
    range_input = q["QLineEdit"]()
    range_input.setPlaceholderText("1-10")
    range_button = q["QPushButton"]("Generate Range")
    asset_controls.addWidget(generate_button)
    asset_controls.addWidget(q["QLabel"]("Range"))
    asset_controls.addWidget(range_input, 1)
    asset_controls.addWidget(range_button)
    panel_layout.addLayout(asset_controls)

    readiness_state: dict[str, AudioRuntimeReadiness | None] = {"readiness": None}
    show_driver_button = False
    try:
        readiness_state["readiness"] = None if initial_message else assess_audio_runtime_readiness()
        readiness = readiness_state["readiness"]
        if readiness is not None:
            _clear_dialog_audio_selection_if_validated_route_ready(readiness)
        launcher_message = initial_message or (readiness.message() if readiness is not None else "")
        show_driver_button = bool(readiness is not None and not readiness.publication_ready and not validation_launcher_auto)
    except Exception as exc:
        launcher_message = initial_message or f"Audio preflight could not run: {exc}"
        show_driver_button = bool((not initial_message) and not validation_launcher_auto)
    message = q["QLabel"](launcher_message or "Ready")
    message.setObjectName("mutedLabel")
    message.setWordWrap(True)
    panel_layout.addWidget(message)
    driver_button = q["QPushButton"]("Audio Driver Instructions")
    driver_button.setObjectName("secondaryButton")
    driver_button.setToolTip("Show Komplete Audio ASIO install steps and retry audio detection.")
    driver_button.setVisible(show_driver_button)
    panel_layout.addWidget(driver_button)
    progress = q["QProgressBar"]()
    progress.setRange(0, 1000)
    progress.setValue(0)
    progress.setVisible(False)
    panel_layout.addWidget(progress)
    detail_message = q["QLabel"]("")
    detail_message.setObjectName("mutedLabel")
    detail_message.setWordWrap(True)
    detail_message.setVisible(False)
    panel_layout.addWidget(detail_message)

    buttons = q["QHBoxLayout"]()
    latest_button = q["QPushButton"]("Resume Last Experiment")
    latest_button.setObjectName("primaryButton")
    profile_button = q["QPushButton"]("Run Selected Profile")
    profile_button.setEnabled(bool(profile_options))
    choose_button = q["QPushButton"]("Choose Session Manifest")
    cancel_button = q["QPushButton"]("Cancel Loading")
    cancel_button.setVisible(False)
    close_button = q["QPushButton"]("Close")
    buttons.addWidget(latest_button)
    buttons.addWidget(profile_button)
    buttons.addWidget(choose_button)
    buttons.addWidget(cancel_button)
    buttons.addStretch(1)
    buttons.addWidget(close_button)
    panel_layout.addLayout(buttons)
    layout.addWidget(panel)
    layout.addStretch(1)
    preparation_messages: queue.Queue[tuple[str, Any]] = queue.Queue()
    preparation_cancel = threading.Event()
    preparation_thread: dict[str, threading.Thread | None] = {"thread": None}
    participant_statuses: dict[str, dict[str, Any]] = {}

    def _refresh_launcher_audio_preflight() -> AudioRuntimeReadiness | None:
        try:
            readiness_state["readiness"] = assess_audio_runtime_readiness()
            readiness = readiness_state["readiness"]
            _clear_dialog_audio_selection_if_validated_route_ready(readiness)
            message.setText(readiness.message())
            driver_button.setVisible(not readiness.publication_ready and not validation_launcher_auto)
            return readiness
        except Exception as exc:
            readiness_state["readiness"] = None
            message.setText(f"Audio preflight could not run: {exc}")
            driver_button.setVisible(not validation_launcher_auto)
            return None

    def _open_audio_dependency_dialog() -> None:
        readiness = readiness_state["readiness"] or assess_audio_runtime_readiness()
        if _show_audio_dependency_dialog(q, parent=dialog, readiness=readiness):
            refreshed = assess_audio_runtime_readiness()
            readiness_state["readiness"] = refreshed
            selected_device_index = os.environ.get("PPS_AUDIO_DEVICE_INDEX", "").strip()
            if os.environ.get("PPS_AUDIO_UNVALIDATED_ROUTE_FROM_DIALOG") == "1" and selected_device_index:
                channel_text = os.environ.get("PPS_AUDIO_OUTPUT_CHANNELS", "1,2,3")
                message.setText(
                    "User-selected system audio route accepted. PPS will use the selected output device with "
                    f"left/right/tactile outputs {channel_text}; run independent channel and latency tests before "
                    "time-sensitive use."
                )
                driver_button.setVisible(not validation_launcher_auto)
            else:
                message.setText(refreshed.message())
                driver_button.setVisible(not refreshed.publication_ready and not validation_launcher_auto)
        else:
            _refresh_launcher_audio_preflight()

    driver_button.clicked.connect(_open_audio_dependency_dialog)
    if show_driver_button and not initial_message and not validation_launcher_auto:
        q["QTimer"].singleShot(100, _open_audio_dependency_dialog)

    def _current_profile() -> str:
        return str(profile_combo.currentData() or "")

    def _current_output_root() -> Path:
        return Path(output_root_state["path"])

    def _set_output_root(path: Path) -> None:
        output_root_state["path"] = Path(path)
        output_folder_input.setText(str(output_root_state["path"]))
        output_folder_input.setToolTip(str(output_root_state["path"]))

    def _current_profile_kind() -> str:
        try:
            entry = resolve_profile_entry(
                _current_profile(),
                registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
                state_root=DEFAULT_DASHBOARD_STATE_ROOT,
                session_root=active_output_folder(state_root=DEFAULT_DASHBOARD_STATE_ROOT, fallback=DEFAULT_SESSION_ROOT),
                inventory=load_preload_inventory(repo_root()),
            )
            return str(entry.get("kind") or "")
        except Exception:
            return ""

    def _refresh_participant_options(preferred: str = "") -> None:
        nonlocal participant_statuses
        profile = _current_profile()
        participants = profile_participant_ids(profile)
        statuses = profile_participant_asset_statuses(profile, session_root=_current_output_root()) if profile else {}
        participant_statuses = statuses
        current = default_profile_participant(
            participants,
            statuses,
            preferred=preferred or str(participant_combo.currentData() or "") or initial_participant or "P001",
        )
        participant_combo.blockSignals(True)
        participant_combo.clear()
        for participant in participants:
            status = statuses.get(participant, {})
            item_index = participant_combo.count()
            participant_combo.addItem(profile_participant_dropdown_label(participant, status), participant)
            if status.get("data_collected"):
                participant_combo.setItemData(
                    item_index,
                    q["QBrush"](q["QColor"]("#15803d")),
                    q["Qt"].ItemDataRole.ForegroundRole,
                )
                participant_combo.setItemData(
                    item_index,
                    str(status.get("data_collection_message") or "Participant data collected."),
                    q["Qt"].ItemDataRole.ToolTipRole,
                )
        index = participant_combo.findData(current)
        participant_combo.setCurrentIndex(index if index >= 0 else 0)
        participant_combo.blockSignals(False)
        enabled = bool(profile_options and participants)
        participant_combo.setEnabled(enabled)
        generate_button.setEnabled(enabled)
        range_button.setEnabled(enabled)

    def _selected_participant() -> str:
        return str(participant_combo.currentData() or "").strip()

    _refresh_participant_options(initial_participant or "P001")

    def _current_profile_label() -> str:
        try:
            label = str(profile_combo.currentText() or "").strip()
        except Exception:
            label = ""
        return label or _current_profile() or "PPS experiment"

    def _launcher_capture_options() -> dict[str, Any]:
        return capture_options.as_dict() if capture_options is not None else _default_focus_capture_options().as_dict()

    def _log_launcher_event(event_type: str, *, payload: dict[str, Any] | None = None, create: bool = False) -> None:
        _append_output_diary_event(
            event_type,
            session_root=_current_output_root(),
            experiment_name=_current_profile_label(),
            profile_id=_current_profile(),
            participant_id=_selected_participant(),
            capture_options=_launcher_capture_options(),
            payload=payload,
            create=create,
        )

    _log_launcher_event(
        "launcher_opened",
        payload={"restored_diary_path": "" if initial_diary is None else str(initial_diary)},
        create=False,
    )

    def _set_busy(busy: bool) -> None:
        latest_button.setEnabled(not busy)
        profile_button.setEnabled((not busy) and bool(profile_options))
        generate_button.setEnabled((not busy) and bool(profile_options))
        range_button.setEnabled((not busy) and bool(profile_options))
        choose_button.setEnabled(not busy)
        choose_output_button.setEnabled(not busy)
        close_button.setEnabled(not busy)
        profile_combo.setEnabled(False)
        participant_combo.setEnabled(not busy)
        range_input.setEnabled(not busy)
        progress.setVisible(busy)
        detail_message.setVisible(busy)
        cancel_button.setVisible(busy)
        cancel_button.setEnabled(busy)
        if not busy:
            progress.setRange(0, 1000)
            progress.setValue(0)

    def _progress_callback(payload: dict[str, Any]) -> None:
        if preparation_cancel.is_set():
            raise RuntimeError("Preparation cancelled.")
        preparation_messages.put(("progress", dict(payload)))

    def _start_preparation(
        label: str,
        prepare: Callable[[Callable[[dict[str, Any]], None]], Any],
        *,
        success_kind: str = "done",
    ) -> None:
        active = preparation_thread.get("thread")
        if active is not None and active.is_alive():
            return
        preparation_cancel.clear()
        message.setText(label)
        detail_message.setText("")
        progress.setRange(0, 0)
        _set_busy(True)

        def _worker() -> None:
            try:
                result = prepare(_progress_callback)
            except Exception as exc:
                preparation_messages.put(("error", str(exc)))
            else:
                preparation_messages.put((success_kind, result))

        worker = threading.Thread(target=_worker, name="pps-runner-launcher-prep", daemon=True)
        preparation_thread["thread"] = worker
        worker.start()

    def _drain_preparation_messages() -> None:
        while not preparation_messages.empty():
            kind, payload = preparation_messages.get_nowait()
            if kind == "progress":
                total = int(payload.get("total") or 0)
                current = int(payload.get("current") or 0)
                if total > 0:
                    progress.setRange(0, 1000)
                    progress.setValue(int(max(0.0, min(1.0, current / total)) * 1000))
                else:
                    progress.setRange(0, 0)
                message.setText(str(payload.get("message") or "Preparing experiment"))
                detail_message.setText(str(payload.get("detail") or payload.get("phase") or ""))
            elif kind == "done":
                if preparation_cancel.is_set():
                    message.setText("Loading cancelled.")
                    detail_message.setText("")
                    _set_busy(False)
                    continue
                selected_manifest["path"] = Path(payload)
                message.setText("Opening Focus Mode")
                _log_launcher_event(
                    "launcher_opening_focus_mode",
                    payload={"session_manifest_path": str(selected_manifest["path"])},
                    create=True,
                )
                dialog.accept()
            elif kind == "generated":
                _refresh_participant_options(_selected_participant())
                prepared = int(payload.get("prepared_count") or 0) if isinstance(payload, dict) else 0
                reused = int(payload.get("reused_count") or 0) if isinstance(payload, dict) else 0
                message.setText(f"Audio assets ready: {prepared} generated, {reused} already available")
                _log_launcher_event(
                    "audio_assets_generation_finished",
                    payload=dict(payload) if isinstance(payload, dict) else {},
                    create=True,
                )
                detail_message.setText("")
                _set_busy(False)
            elif kind == "error":
                message.setText(str(payload))
                _log_launcher_event(
                    "launcher_preparation_failed",
                    payload={"message": str(payload)},
                    create=True,
                )
                detail_message.setText("")
                _set_busy(False)

    preparation_timer = q["QTimer"](dialog)
    preparation_timer.timeout.connect(_drain_preparation_messages)
    preparation_timer.start(100)

    def _open_latest() -> None:
        _log_launcher_event("resume_last_clicked", create=True)
        _start_preparation(
            "Loading last experiment",
            lambda progress_callback: prepare_last_or_latest_focus_session(
                _selected_participant(),
                session_root=_current_output_root(),
                progress_callback=progress_callback,
            ),
        )

    def _open_profile() -> None:
        _log_launcher_event("run_selected_profile_clicked", create=True)
        _start_preparation(
            "Loading selected profile",
            lambda progress_callback: prepare_profile_focus_session(
                str(profile_combo.currentData() or ""),
                _selected_participant(),
                session_root=_current_output_root(),
                progress_callback=progress_callback,
            ),
        )

    def _generate_selected() -> None:
        participant = _selected_participant()
        if not participant:
            message.setText("Choose a participant before generating assets.")
            return
        _log_launcher_event(
            "generate_audio_assets_clicked",
            payload={"participant_ids": [participant]},
            create=True,
        )
        _start_preparation(
            f"Generating audio assets for {participant}",
            lambda progress_callback: prepare_profile_audio_assets(
                _current_profile(),
                [participant],
                session_root=_current_output_root(),
                progress_callback=progress_callback,
            ),
            success_kind="generated",
        )

    def _generate_range() -> None:
        try:
            participants = parse_participant_range(
                range_input.text().strip(),
                max_participant=len(profile_participant_ids(_current_profile())),
            )
        except ValueError as exc:
            message.setText(str(exc))
            return
        preferred = participants[0] if participants else _selected_participant()
        if preferred:
            index = participant_combo.findData(preferred)
            if index >= 0:
                participant_combo.setCurrentIndex(index)
        _log_launcher_event(
            "generate_audio_asset_range_clicked",
            payload={"participant_ids": participants, "range_text": range_input.text().strip()},
            create=True,
        )
        _start_preparation(
            f"Generating audio assets for {len(participants)} participant(s)",
            lambda progress_callback: prepare_profile_audio_assets(
                _current_profile(),
                participants,
                session_root=_current_output_root(),
                progress_callback=progress_callback,
            ),
            success_kind="generated",
        )

    def _choose_output_folder() -> None:
        parent = q["QFileDialog"].getExistingDirectory(
            dialog,
            "Choose Runner Output Folder",
            str(_current_output_root().parent if _current_output_root() else DEFAULT_SESSION_ROOT.parent),
        )
        if not parent:
            return
        try:
            project_root = create_runner_output_project(
                Path(parent),
                experiment_identifier=_current_profile_label(),
                profile_id=_current_profile(),
                participant_id=_selected_participant(),
                capture_options=_launcher_capture_options(),
            )
        except Exception as exc:
            message.setText(f"Could not create output project: {exc}")
            return
        update_profile_runner_settings(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            output_folder=project_root,
            profile_id=_current_profile(),
            profile_kind=_current_profile_kind(),
            participant_id=_selected_participant(),
        )
        append_output_diary_event(
            "output_folder_selected",
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            output_folder=project_root,
            profile_id=_current_profile(),
            profile_kind=_current_profile_kind(),
            participant_id=_selected_participant(),
        )
        _set_output_root(project_root)
        message.setText(f"Runner output project set to {project_root}")
        _refresh_participant_options(_selected_participant())
        _log_launcher_event(
            "output_folder_selected",
            payload={"selected_folder": str(parent), "output_project_root": str(project_root)},
            create=False,
        )

    def _choose_manifest() -> None:
        filename, _selected_filter = q["QFileDialog"].getOpenFileName(
            dialog,
            "Choose Session Manifest",
            str(_current_output_root()),
            "PPS session_manifest.json (session_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if filename:
            _log_launcher_event(
                "choose_session_manifest_clicked",
                payload={"session_manifest_path": filename},
                create=False,
            )
            selected_manifest["path"] = Path(filename)
            dialog.accept()

    latest_button.clicked.connect(_open_latest)
    profile_button.clicked.connect(_open_profile)
    generate_button.clicked.connect(_generate_selected)
    range_button.clicked.connect(_generate_range)

    def _profile_changed(_index: int) -> None:
        update_profile_runner_settings(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            output_folder=_current_output_root(),
            profile_id=_current_profile(),
            profile_kind=_current_profile_kind(),
            participant_id=_selected_participant(),
        )
        append_output_diary_event(
            "profile_selected",
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            profile_id=_current_profile(),
            profile_kind=_current_profile_kind(),
            participant_id=_selected_participant(),
        )
        _refresh_participant_options()

    profile_combo.currentIndexChanged.connect(_profile_changed)
    participant_combo.currentIndexChanged.connect(
        lambda _index: update_profile_runner_settings(
            state_root=DEFAULT_DASHBOARD_STATE_ROOT,
            output_folder=_current_output_root(),
            profile_id=_current_profile(),
            profile_kind=_current_profile_kind(),
            participant_id=_selected_participant(),
        )
    )
    choose_output_button.clicked.connect(_choose_output_folder)
    choose_button.clicked.connect(_choose_manifest)
    cancel_button.clicked.connect(lambda: (preparation_cancel.set(), cancel_button.setEnabled(False), message.setText("Cancelling loading...")))
    close_button.clicked.connect(lambda: (_log_launcher_event("launcher_close_clicked", create=False), dialog.reject()))
    validation_launcher_clicks: list[dict[str, Any]] = []

    def _validation_click_launcher_profile() -> None:
        from PySide6.QtTest import QTest

        target = os.environ.get("PPS_FOCUS_VALIDATION_PROFILE", STUDY5_PROFILE_ID).strip()
        if target:
            index = profile_combo.findData(target)
            if index >= 0:
                profile_combo.setCurrentIndex(index)
        requested_participant = initial_participant or "P001"
        participant_index = participant_combo.findData(requested_participant)
        if participant_index >= 0:
            participant_combo.setCurrentIndex(participant_index)
        if profile_combo.isEnabled():
            QTest.mouseClick(profile_combo, q["Qt"].MouseButton.LeftButton)
            validation_launcher_clicks.append(
                {
                    "label": "click Study/profile selector",
                    "timestamp_unix": time.time(),
                    "selected_profile": str(profile_combo.currentData() or ""),
                    "selected_participant": _selected_participant(),
                }
            )
        else:
            validation_launcher_clicks.append(
                {
                    "label": "click Study/profile selector",
                    "timestamp_unix": time.time(),
                    "selected_profile": str(profile_combo.currentData() or ""),
                    "selected_participant": _selected_participant(),
                    "mode": "locked_environment_profile",
                }
            )
        q["QTimer"].singleShot(150, _validation_click_launcher_run_button)

    def _validation_click_launcher_run_button() -> None:
        from PySide6.QtTest import QTest

        if profile_button.isEnabled():
            QTest.mouseClick(profile_button, q["Qt"].MouseButton.LeftButton)
            validation_launcher_clicks.append(
                {
                    "label": "click Run Selected Profile",
                    "timestamp_unix": time.time(),
                    "selected_profile": str(profile_combo.currentData() or ""),
                    "selected_participant": _selected_participant(),
                }
            )

    if _env_flag("PPS_FOCUS_VALIDATION_LAUNCHER_AUTO_CLICK"):
        q["QTimer"].singleShot(400, _validation_click_launcher_profile)

    accepted = dialog.exec() == q["QDialog"].DialogCode.Accepted
    if not accepted or selected_manifest["path"] is None:
        launcher_report_path = os.environ.get("PPS_FOCUS_VALIDATION_LAUNCHER_REPORT", "").strip()
        if launcher_report_path:
            _write_validation_launcher_report(
                Path(launcher_report_path),
                selected_manifest=selected_manifest["path"],
                exit_code=1,
                profile_count=len(profile_options),
                selected_profile=str(profile_combo.currentData() or ""),
                validation_clicks=validation_launcher_clicks,
            )
        return 1
    exit_code = run_focus_window(
        selected_manifest["path"],
        capture_options=capture_options,
        enable_missed_trial_topup=enable_missed_trial_topup,
        companion_enabled=companion_enabled,
        companion_host=companion_host,
        companion_port=companion_port,
        companion_advertise_ip=companion_advertise_ip,
        manual_start=True,
        fullscreen=True,
    )
    launcher_report_path = os.environ.get("PPS_FOCUS_VALIDATION_LAUNCHER_REPORT", "").strip()
    if launcher_report_path:
        _write_validation_launcher_report(
            Path(launcher_report_path),
            selected_manifest=selected_manifest["path"],
            exit_code=exit_code,
            profile_count=len(profile_options),
            selected_profile=str(profile_combo.currentData() or ""),
            validation_clicks=validation_launcher_clicks,
        )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    options = _capture_options_from_args(args)
    companion_kwargs = {
        "companion_enabled": not bool(args.no_companion),
        "companion_host": args.companion_host,
        "companion_port": int(args.companion_port),
        "companion_advertise_ip": args.companion_advertise_ip,
    }
    single_instance = _acquire_runner_single_instance()
    if not single_instance.acquired:
        _show_runner_single_instance_notice(single_instance.message)
        return SINGLE_INSTANCE_EXIT_CODE
    try:
        if args.launcher:
            return run_launcher_window(
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                **companion_kwargs,
                participant_id=args.participant_id,
            )
        if args.session_manifest is not None:
            return run_focus_window(
                args.session_manifest,
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                **companion_kwargs,
                manual_start=args.manual_start,
                fullscreen=not bool(args.validation_windowed),
                auto_close_ms=args.validation_auto_close_ms,
                screenshot_path=args.validation_screenshot,
            )
        if args.profile:
            try:
                manifest = prepare_profile_focus_session(args.profile, args.participant_id)
            except Exception as exc:
                return run_launcher_window(
                    capture_options=options,
                    enable_missed_trial_topup=args.enable_missed_trial_topup,
                    **companion_kwargs,
                    participant_id=args.participant_id,
                    initial_message=str(exc),
                )
            return run_focus_window(
                manifest,
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                **companion_kwargs,
                manual_start=args.manual_start,
                fullscreen=not bool(args.validation_windowed),
                auto_close_ms=args.validation_auto_close_ms,
                screenshot_path=args.validation_screenshot,
            )
        if args.latest_dashboard_setup or args.last_experiment:
            try:
                manifest = prepare_last_or_latest_focus_session(args.participant_id)
            except Exception as exc:
                return run_launcher_window(
                    capture_options=options,
                    enable_missed_trial_topup=args.enable_missed_trial_topup,
                    **companion_kwargs,
                    participant_id=args.participant_id,
                    initial_message=str(exc),
                )
            return run_focus_window(
                manifest,
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                **companion_kwargs,
                manual_start=args.manual_start,
                auto_close_ms=args.validation_auto_close_ms,
                screenshot_path=args.validation_screenshot,
            )
        return run_launcher_window(
            capture_options=options,
            enable_missed_trial_topup=args.enable_missed_trial_topup,
            **companion_kwargs,
            participant_id=args.participant_id,
        )
    finally:
        single_instance.release()


def direct_module_launch_retirement_message() -> str:
    return (
        "Direct Python module launch of Focus Mode is retired. "
        "The only active operator experiment runner is the packaged "
        "dist\\PPSExperimentRunner\\PPSExperimentRunner.exe. "
        "Build it with windows\\Build_Experiment_Runner_Exe.ps1, then run the exe "
        "or windows\\Launch_Experiment_Runner.bat."
    )


if __name__ == "__main__":
    print(direct_module_launch_retirement_message(), file=sys.stderr)
    raise SystemExit(2)
