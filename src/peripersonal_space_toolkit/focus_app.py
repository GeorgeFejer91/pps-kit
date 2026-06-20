"""Native participant Focus Mode launcher for prepared PPS sessions."""

from __future__ import annotations

import argparse
import csv
from html import escape
import json
import math
import os
import queue
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from .app_assets import apply_qt_app_icon, set_windows_app_user_model_id
from .audio_routing import (
    NI_KOMPLETE_AUDIO_DRIVER_INSTALL_GUIDE_URL,
    NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL,
    AudioRuntimeReadiness,
    assess_audio_runtime_readiness,
    komplete_audio_asio_reconnect_steps,
    komplete_audio_asio_install_steps,
)
from .analysis_review import (
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
    fit_row_for_scope,
    load_analysis_review_data,
    observed_points_for_scope,
    prediction_points_for_scope,
    prediction_series_for_scope,
    raw_points_for_scope,
    scope_comparison_row,
    scopes_for_part_mode,
)
from .focus_layout import (
    FocusLayoutProfile,
    render_focus_layout_profile,
    render_focus_style_sheet,
)
from .output_layout import output_root_for_metadata_path
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
from .session_runner import (
    DEFAULT_DASHBOARD_STATE_ROOT,
    DEFAULT_PROJECT_REGISTRY_ROOT,
    DEFAULT_RENDER_DIR,
    DEFAULT_SESSION_ROOT,
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


DEFAULT_FOCUS_PROFILE_DESIGN_PATH = DEFAULT_DASHBOARD_STATE_ROOT / "focus_profile_runner_design.json"
DEFAULT_FOCUS_LAYOUT_PROFILE = render_focus_layout_profile(1120, 720)
FOCUS_STYLE_SHEET = render_focus_style_sheet(DEFAULT_FOCUS_LAYOUT_PROFILE)
STUDY5_PROFILE_ID = "study5_box_breathing_pps"
DATA_COLLECTED_MARK = "[collected]"
TIMELINE_LABEL_WIDTH = 58
TIMELINE_RIGHT_MARGIN = 12
TIMELINE_ROW_NAMES = ("Resp", "Type", "SOA", "Tactile", "Clicks")
TIMELINE_MINIMUM_VISIBLE_HEIGHT = 84
TIMELINE_SEGMENT_LABEL_SKIP_WIDTH = 22
TIMELINE_REPEATED_LABEL_SKIP_WIDTH = 58
SINGLE_INSTANCE_MUTEX_NAME = "Local\\PPSExperimentRunnerSingleInstance"
SINGLE_INSTANCE_EXIT_CODE = 4


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
    root.mkdir(parents=True, exist_ok=True)
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
    if not parent.is_dir():
        raise ValueError("Choose an existing output folder before initiating a new data collection environment.")
    slug = slugify_identifier(session_name, fallback="")
    if not slug:
        raise ValueError("Enter a session name before initiating a new data collection environment.")
    stamp = time.strftime("%Y%m%d_%H%M%S")
    root = parent / f"{slug}_{stamp}"
    suffix = 2
    while root.exists():
        root = parent / f"{slug}_{stamp}_{suffix}"
        suffix += 1
    root.mkdir(parents=True, exist_ok=False)
    diary = ensure_output_diary(root, session_name)
    return root, diary, slug


def _capture_options_payload(capture_options: SessionCaptureOptions | dict[str, Any] | None) -> dict[str, Any]:
    if capture_options is None:
        return SessionCaptureOptions().as_dict()
    if isinstance(capture_options, SessionCaptureOptions):
        return capture_options.as_dict()
    return dict(capture_options)


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
    if not parent.is_dir():
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
    parser.add_argument("--no-lsl", action="store_true", help="Do not create live LSL marker outlets for this run.")
    parser.add_argument("--no-internal-xdf", action="store_true", help="Do not write the local events.xdf mirror.")
    parser.add_argument("--no-analysis-csv", action="store_true", help="Do not write immediate analysis CSV outputs.")
    parser.add_argument("--no-backup-recording", action="store_true", help="Do not write the optional fail-safe local recording WAV.")
    parser.add_argument("--external-labrecorder", action="store_true", help="Start runner-owned LabRecorder RCS capture after LSL outlets are online and before playback.")
    parser.add_argument("--labrecorder-cli", type=Path, default=None, help="Optional explicit path to LabRecorderCLI.exe used to find the LabRecorder bundle.")
    parser.add_argument("--labrecorder-stream-timeout-s", type=float, default=10.0, help="Seconds to wait for runner LSL streams before starting LabRecorder.")
    parser.add_argument("--labrecorder-startup-s", type=float, default=1.0, help="Seconds to wait after LabRecorder starts before playback may continue.")
    parser.add_argument("--labrecorder-stop-timeout-s", type=float, default=8.0, help="Seconds to wait for LabRecorder to close the XDF at session end.")
    parser.add_argument(
        "--wired-loopback",
        choices=[WIRED_LOOPBACK_OFF, WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY],
        default=WIRED_LOOPBACK_OFF,
        help="Record an optional wired analog loopback route, for example output4-tactile-proxy.",
    )
    parser.add_argument("--enable-missed-trial-topup", action="store_true", help="Prepare and request approval for one final missed-trial top-up block.")
    parser.add_argument("--validation-screenshot", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--validation-auto-close-ms", type=int, default=None, help=argparse.SUPPRESS)
    return parser


def _require_qt() -> dict[str, Any]:
    try:
        from PySide6.QtCore import QPoint, QTimer, Qt, QUrl, Signal
        from PySide6.QtGui import QBrush, QColor, QCursor, QDesktopServices, QFont, QFontDatabase, QFontMetrics, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
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
            QSplitter,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
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
        "QPoint": QPoint,
        "QProgressBar": QProgressBar,
        "QPushButton": QPushButton,
        "QScrollArea": QScrollArea,
        "QShortcut": QShortcut,
        "Signal": Signal,
        "QSizePolicy": QSizePolicy,
        "QSplitter": QSplitter,
        "QTabWidget": QTabWidget,
        "QTableWidget": QTableWidget,
        "QTableWidgetItem": QTableWidgetItem,
        "QTextEdit": QTextEdit,
        "QTimer": QTimer,
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
        def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            schedule_clamp = getattr(owner, "_schedule_experiment_control_splitter_clamp", None)
            if callable(schedule_clamp):
                schedule_clamp()

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


def _create_analysis_curve_plot_widget(q: dict[str, Any]) -> Any:
    class AnalysisCurvePlotWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            self.observed: list[dict[str, float | str]] = []
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
            show_observed: bool = True,
            show_uncertainty: bool = True,
            show_raw_points: bool = False,
            show_boundary: bool = True,
            show_low_n_markers: bool = True,
        ) -> None:
            self.observed = list(observed)
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
                visible_observed = self.observed if self.show_observed else []
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

                def _model_color(model: str) -> Any:
                    if model == MODEL_SIGMOID:
                        return q["QColor"]("#246b55")
                    if model == MODEL_LINEAR:
                        return q["QColor"]("#4b5fa8")
                    if model == MODEL_LOGARITHMIC_DECAY:
                        return q["QColor"]("#a4631b")
                    return q["QColor"]("#246b55")

                def _model_pen(model: str, *, width_px: int = 3) -> Any:
                    pen = q["QPen"](_model_color(model))
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
                    if len(spread_points) >= 2:
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
                    painter.setPen(_model_pen(model))
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
                            painter.setPen(_model_pen(model, width_px=2))
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
                            painter.setPen(_model_pen(model, width_px=2))
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
                if visible_observed:
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

                if len(visible_observed) >= 2:
                    mean_pen = q["QPen"](q["QColor"]("#8c2f2f"))
                    mean_pen.setWidth(2)
                    painter.setPen(mean_pen)
                    mean_path = q["QPainterPath"]()
                    first = visible_observed[0]
                    mean_path.moveTo(_x(float(first["x"])), _y(float(first["y"])))
                    for point in visible_observed[1:]:
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

                point_pen = q["QPen"](q["QColor"]("#8c2f2f"))
                point_pen.setWidth(2)
                painter.setPen(point_pen)
                painter.setBrush(q["QBrush"](q["QColor"]("#f4e2b8")))
                for point in visible_observed:
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
                        painter.setBrush(q["QBrush"](q["QColor"]("#f4e2b8")))

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

    def __init__(self, q: dict[str, Any], parent: Any, data: Any) -> None:
        self.q = q
        self.data = data
        self.current_part_mode = data.default_part_mode
        self.current_view = VIEW_DATA_BEHAVIOR
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
            "Exploratory data-behavior signals compare this recording with common PPS visualization patterns; they are not scientific conclusions or participant-readiness certification."
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

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
        root.addLayout(view_row)

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
        root.addLayout(controls)

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
            box.stateChanged.connect(lambda _state=0: self._refresh())
            self.plot_toggles[key] = box
            toggle_layout.addWidget(box, index // 4, index % 4)
        root.addWidget(toggle_panel)

        body = q["QSplitter"](q["Qt"].Orientation.Vertical)
        body.setChildrenCollapsible(False)
        body.setHandleWidth(8)
        body.setMinimumHeight(0)
        body.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        root.addWidget(body, 1)

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

        plot_panel, plot_layout = _panel(q, "Model Visualization")
        self.plot_widget = _create_analysis_curve_plot_widget(q)
        self.plot_widget.setObjectName("analysisCurvePlot")
        plot_layout.addWidget(self.plot_widget)
        body.addWidget(plot_panel)

        detail_panel, detail_layout = _panel(q, "Selected Fit Details")
        self.detail_text = q["QTextEdit"]()
        self.detail_text.setObjectName("analysisDetailsText")
        self.detail_text.setReadOnly(True)
        self.detail_text.setMinimumHeight(64)
        self.detail_text.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        detail_layout.addWidget(self.detail_text)
        body.addWidget(detail_panel)
        body.setSizes([104, 252, 88])

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

        self.scope_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        self.model_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        self.metric_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        self.source_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        self.grouping_combo.currentIndexChanged.connect(lambda _index: self._refresh())
        self._reload_scopes_for_part_mode()
        self._populate_overview_table()

    def _set_view(self, view: str) -> None:
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
                            "SOA",
                            f"{segment.soa_ms} ms" if segment.soa_ms else "SOA",
                            row_y_by_name["SOA"] - row_height // 2,
                            _soa_color(segment.soa_ms),
                        )
                    ):
                        segment_width = max(2, x2 - x1)
                        painter.setPen(q["QPen"](q["QColor"]("#bcc7bd")))
                        painter.setBrush(q["QBrush"](q["QColor"](color)))
                        painter.drawRoundedRect(x1, y, segment_width, row_height, 4, 4)
                        _draw_fitted_text(row_name, x1, y, segment_width, row_height, text, "#202621", optional=True)

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
        start_external_labrecorder=bool(args.external_labrecorder),
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
    return bool(package.blocks)


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
    output_root = Path(session_root) if session_root is not None else active_output_folder(
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
    output_root = Path(session_root) if session_root is not None else active_output_folder(
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


def _package_output_root(package: Any) -> Path:
    try:
        session_dir = Path(getattr(package, "session_dir")).resolve()
    except Exception:
        return current_runner_session_root()
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
        project = controller._ensure_project_context(controller.design)
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
    output_root = Path(session_root) if session_root is not None else active_output_folder(
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
    if not events_csv.is_file():
        return counts
    with events_csv.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            event_type = str(row.get("event_type") or "")
            if event_type:
                counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _install_validation_auto_clicker(q: dict[str, Any], window: "FocusModeWindow") -> list[dict[str, Any]]:
    from PySide6.QtTest import QTest

    clicks: list[dict[str, Any]] = []
    start_gate_state: dict[str, Any] = {}

    def _click(widget: Any, label: str) -> None:
        if widget is None or not widget.isEnabled():
            return
        QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
        clicks.append({"label": label, "timestamp_unix": time.time()})

    def _click_start_when_ready() -> None:
        if window.result is not None:
            return
        if window.start_button.isEnabled() and _validation_start_gate_ready(clicks, start_gate_state, source="auto_clicker"):
            _click(window.start_button, "Start Run")
            return
        q["QTimer"].singleShot(100, _click_start_when_ready)

    def _poll() -> None:
        if window.result is not None:
            q["QTimer"].singleShot(250, window.dialog.accept)
            return
        request = window.pending_instruction_request
        if request is not None:
            context = dict(request.get("context") or {})
            mode = str(context.get("mode") or "click")
            label = str(context.get("instruction_label") or "instruction")
            if mode == "button":
                _click(window.instruction_button, f"instruction button: {label}")
            else:
                _click(window.target_button, f"instruction target: {label}")
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
    backend_requested = os.environ.get("PPS_FOCUS_VALIDATION_MOUSE_BACKEND", "win32").strip().lower() or "win32"
    records: list[dict[str, Any]] = []
    scheduled_events: set[str] = set()
    scheduled_response_keys: set[str] = set()
    completed_events: set[str] = set()
    pending: list[dict[str, Any]] = []
    start_clicked = {"value": False}
    start_gate_state: dict[str, Any] = {}
    miss_keys: set[str] | None = None
    instruction_attempts: dict[int, tuple[int, float]] = {}

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
        controller = window.controller
        logger = getattr(controller, "logger", None) if controller is not None else None
        events = getattr(logger, "events", []) if logger is not None else []
        return sum(1 for event in events if getattr(event, "event_type", "") == "mouse_click")

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
        backend = _press_primary_key(f"instruction: {label}")
        records.append(
            {
                "label": f"instruction_continue:{label}",
                "mode": mode,
                "backend": backend,
                "timestamp_unix": time.time(),
            }
        )

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
            backend = _click_widget(window.target_button, f"tactile response {item['trial_uid']}", preferred_backend=backend_requested)
            completed_events.add(schedule_key)
            pending.remove(item)
            records.append(
                {
                    **item,
                    "label": "tactile_response_click",
                    "backend": backend,
                    "actual_delay_ms": (time.perf_counter() - float(item["tactile_monotonic_time"])) * 1000.0,
                    "timestamp_unix": time.time(),
                }
            )

    def _poll() -> None:
        if window.result is not None:
            q["QTimer"].singleShot(1000, window.dialog.accept)
            return
        _submit_mock_setup_if_needed()
        if (
            not start_clicked["value"]
            and window.start_button.isEnabled()
            and _validation_start_gate_ready(records, start_gate_state, source="participant_emulator")
        ):
            backend = _press_primary_key("Start Run")
            start_clicked["value"] = True
            records.append({"label": "Start Run", "backend": backend, "timestamp_unix": time.time()})
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
    manifest_outputs: dict[str, Any] = {}
    try:
        manifest_payload = json.loads(Path(session_manifest).read_text(encoding="utf-8"))
        if isinstance(manifest_payload.get("outputs"), dict):
            manifest_outputs = dict(manifest_payload.get("outputs") or {})
    except Exception:
        manifest_outputs = {}
    events_csv = Path(str(manifest_outputs.get("verbose_events_csv") or manifest_outputs.get("events_csv") or package.session_dir / "events.csv"))
    payload = {
        "schema": "pps-focus-mode-packaged-validation.v1",
        "session_manifest": str(session_manifest),
        "session_dir": str(package.session_dir),
        "events_csv": str(events_csv),
        "exit_code": int(exit_code),
        "completed": bool(window.result is not None and getattr(window.result, "completed", False)),
        "event_counts": _validation_event_counts(events_csv),
        "validation_mouse_clicks": validation_clicks,
        "validation_topup_approvals": list(getattr(window, "validation_topup_approval_records", [])),
        "planned_tactile_cue_count": int(getattr(window, "planned_tactile_cue_count", 0)),
        "cursor_recenter_records": list(getattr(window, "recenter_records", [])),
        "cursor_recenter_count": len(getattr(window, "recenter_records", [])),
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class FocusModeWindow:
    """Dashboard-styled native participant runner window."""

    def __init__(
        self,
        q: dict[str, Any],
        package: Any,
        *,
        capture_options: SessionCaptureOptions | None = None,
        enable_missed_trial_topup: bool = False,
        controller_factory: Callable[..., Any] | None = None,
        layout_profile: FocusLayoutProfile | None = None,
    ) -> None:
        self.q = q
        self.package = package
        self.output_root = _package_output_root(package)
        self.capture_options = capture_options or SessionCaptureOptions()
        self.enable_missed_trial_topup = bool(enable_missed_trial_topup)
        self.controller_factory = controller_factory
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.controller: SessionRunnerController | None = None
        self._owned_audio_engine: Any | None = None
        self.thread: threading.Thread | None = None
        self.result: Any | None = None
        self.exit_code = 1
        self.demographics_submitted = False
        self.pending_instruction_request: dict[str, Any] | None = None
        self._pre_run_controls: list[Any] = []
        self._prewarm_thread: threading.Thread | None = None
        self._prewarm_started = False
        self._participant_combo_updating = False
        self._run_active = False
        self._run_paused = False
        self._timeline_perf_anchor: float | None = None
        self.timeline_state = TactileTimelineState()
        self.timeline_preview_state = TactileTimelineState()
        self.selected_display_block_index: int | None = None
        self.preview_display_block_index: int | None = None
        self.selected_part_key: str | None = None
        self.recenter_records: list[dict[str, Any]] = []
        self._last_recenter_backend_warning = ""
        self.validation_topup_approval_records: list[dict[str, Any]] = []
        self.planned_tactile_cue_count = 0
        self.analysis_review_dialog: AnalysisReviewDialog | None = None
        self.primary_action_shortcuts: list[Any] = []
        self.operator_action_shortcuts: dict[str, list[Any]] = {}
        self.all_block_plan_items: list[dict[str, Any]] = []
        self.block_plan_items: list[dict[str, Any]] = []
        self.instruction_plan_items: list[dict[str, Any]] = []
        self.topup_draft_items: list[dict[str, Any]] = []
        self.part_buttons: dict[str, Any] = {}
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
        self._build()

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

        self.workspace_splitter = q["QSplitter"](q["Qt"].Orientation.Vertical)
        self.workspace_splitter.setChildrenCollapsible(False)
        self.workspace_splitter.setHandleWidth(max(7, profile.root_spacing))
        self.workspace_splitter.splitterMoved.connect(
            lambda _pos, _index: self._clamp_workspace_splitter_for_experiment_control()
        )
        root.addWidget(self.workspace_splitter, 1)

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
        response_layout.addWidget(self.instruction_button)

        self.start_button = q["QPushButton"]("Start Run")
        self.start_button.setObjectName("primaryButton")
        self.start_button.setEnabled(False)
        self.pause_button = q["QPushButton"]("Pause")
        self.stop_button = q["QPushButton"]("Stop")
        self.stop_button.setObjectName("dangerButton")
        self.close_button = q["QPushButton"]("Close")
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.stop_button.clicked.connect(self._stop)
        self.close_button.clicked.connect(self._close)
        controls = q["QGridLayout"]()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(6)
        controls.setVerticalSpacing(6)
        controls.addWidget(self.start_button, 0, 0)
        controls.addWidget(self.pause_button, 0, 1)
        controls.addWidget(self.stop_button, 1, 0)
        controls.addWidget(self.close_button, 1, 1)
        controls.setColumnStretch(0, 1)
        controls.setColumnStretch(1, 1)
        response_layout.addLayout(controls)
        self._install_primary_action_shortcuts()
        response_cell_layout.addWidget(response_panel, 0, q["Qt"].AlignmentFlag.AlignTop | q["Qt"].AlignmentFlag.AlignHCenter)

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
        response_cell_layout.addWidget(output_panel)
        response_stack_height = profile.response_panel_side + output_panel_min_height + max(6, profile.root_spacing)
        response_cell.setMinimumHeight(response_stack_height)
        response_cell_layout.addStretch(1)
        self.run_splitter.addWidget(response_cell)

        self.operator_splitter = None
        self.operator_tabs = None
        if profile.right_stack_mode == "tabs":
            self.operator_tabs = q["QTabWidget"]()
            self.operator_tabs.setDocumentMode(True)
            self.operator_tabs.setMinimumWidth(300)
            try:
                self.operator_tabs.tabBar().setMovable(True)
            except Exception:
                pass
            self.run_splitter.addWidget(self.operator_tabs)

        def _add_operator_panel(title_text: str, panel: Any) -> None:
            if self.operator_tabs is not None:
                self.operator_tabs.addTab(panel, title_text)
            else:
                self.run_splitter.addWidget(panel)

        settings_title = "Data Logging / Experiment Settings"
        data_panel_title = "" if profile.right_stack_mode == "tabs" else settings_title
        data_panel, data_layout = _panel(q, data_panel_title, profile=profile)
        self.data_selection_panel = data_panel
        self.settings_panel = data_panel
        data_panel.setMinimumWidth(380 if profile.compact else 460)
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
        self.participant_code_combo = q["QComboBox"]()
        self.participant_code_combo.setObjectName("runnerParticipantCombo")
        self.participant_code_combo.setEditable(False)
        self.participant_code_combo.setToolTip("Select a prepared participant profile from the run setup.")
        self._populate_participant_code_combo(self.package.participant_id)
        self.participant_code_combo.currentIndexChanged.connect(self._participant_selection_changed)
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

        _add_setup_field(0, "Participant", self.participant_code_combo)
        _add_setup_field(1, "Name", self.participant_name_input)
        _add_setup_field(2, "Age", self.age_input)
        _add_setup_field(3, "Handedness", self.handedness_combo)
        _add_setup_field(4, "Gender", self.gender_combo)
        setup_fields.setColumnStretch(1, 1)
        data_logging_layout.addLayout(setup_fields)
        data_logging_layout.addWidget(self.include_name_lsl_checkbox)
        self.setup_submit_button = q["QPushButton"]("Submit setup")
        self.setup_submit_button.setObjectName("participantSetupSubmitButton")
        self.setup_submit_button.setToolTip("Submit participant setup and create the session LSL marker streams.")
        self.setup_submit_button.setMinimumHeight(profile.button_min_height)
        self.setup_submit_button.clicked.connect(self._submit_participant_setup)
        data_logging_layout.addWidget(self.setup_submit_button)
        self._pre_run_controls.extend(
            [
                self.participant_code_combo,
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
        self.external_labrecorder_checkbox.setChecked(bool(self.capture_options.start_external_labrecorder))
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
        _add_operator_panel(settings_title, data_panel)

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

        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.run_splitter.setStretchFactor(0, 0)
        if profile.right_stack_mode == "tabs":
            self.run_splitter.setStretchFactor(1, 1)
        else:
            self.run_splitter.setStretchFactor(1, 2)

        response_column_width = profile.response_panel_side + max(12, profile.root_spacing)
        if profile.right_stack_mode == "tabs":
            self.run_splitter.setSizes([response_column_width, max(420, profile.window_width - response_column_width)])
        else:
            remaining_width = max(620, profile.window_width - response_column_width)
            self.run_splitter.setSizes([response_column_width, remaining_width])
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

    def _timeline_display_state(self) -> TactileTimelineState:
        if self.preview_display_block_index is not None:
            return self.timeline_preview_state
        return self.timeline_state

    def _available_part_keys(self) -> list[str]:
        return _package_part_keys(self.package)

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
        self.selected_part_key = key
        self._refresh_run_plan(select_default=preview_first)

    def _refresh_part_controls(self) -> None:
        available = set(self._available_part_keys())
        selected = self._ensure_selected_part_key()
        for part_key, button in getattr(self, "part_buttons", {}).items():
            enabled = part_key in available
            button.setEnabled(enabled)
            button.setChecked(enabled and part_key == selected)
            if enabled:
                button.setToolTip(f"Show {_part_button_label(part_key)} block order and top-up draft.")
            else:
                button.setToolTip(f"{_part_button_label(part_key)} is not present in this Segment 6 setup.")

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

    def _populate_participant_code_combo(self, preferred: str = "") -> None:
        if not hasattr(self, "participant_code_combo"):
            return
        participants = _package_participant_ids(self.package)
        statuses = _package_participant_statuses(self.package, participants)
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
            package = prepare_segment_run_package(
                run_setup_path,
                selected,
                session_root=self.output_root,
                progress_callback=_progress,
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

        self.package = package
        self.output_root = _package_output_root(package)
        self._clear_participant_details()
        self._refresh_loaded_package_display()
        self._populate_participant_code_combo(self.package.participant_id)
        self.event_label.setText(f"Participant {self.package.participant_id} ready")
        _append_output_diary_event(
            "participant_switched",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"previous_participant_id": current, "selected_participant_id": self.package.participant_id},
            create=True,
        )

    def _clear_participant_details(self) -> None:
        self.demographics_submitted = False
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
            start_external_labrecorder=bool(self.external_labrecorder_checkbox.isChecked()),
            external_labrecorder_cli=str(self.capture_options.external_labrecorder_cli or ""),
            external_labrecorder_stream_timeout_s=float(self.capture_options.external_labrecorder_stream_timeout_s),
            external_labrecorder_startup_s=float(self.capture_options.external_labrecorder_startup_s),
            external_labrecorder_stop_timeout_s=float(self.capture_options.external_labrecorder_stop_timeout_s),
        )

    def _runner_metadata(self) -> dict[str, Any]:
        return {
            "participant_code": self._selected_participant_code() or self.package.participant_id,
            "participant_name": self.participant_name_input.text().strip(),
            "include_name_in_lsl": bool(self.include_name_lsl_checkbox.isChecked()),
            "age_years": self.age_input.text().strip(),
            "handedness": self.handedness_combo.currentData() or "",
            "gender": self.gender_combo.currentData() or "",
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
        self._stop()
        if not (self.thread is not None and self.thread.is_alive()):
            self._release_prepared_controller()

    def _submit_participant_setup(self) -> bool:
        if self.demographics_submitted and self.controller is not None:
            return True
        failures = self._participant_setup_failures()
        if failures:
            self.event_label.setText(f"Complete participant setup: {', '.join(failures)}.")
            return False
        self.capture_options = self._runtime_capture_options()
        self.enable_missed_trial_topup = bool(self.topup_checkbox.isChecked())
        self._refresh_run_plan()
        runner_metadata = self._runner_metadata()
        try:
            if self.controller_factory is not None:
                self.controller = self.controller_factory(
                    self.package,
                    capture_options=self.capture_options,
                    enable_topup=self.enable_missed_trial_topup,
                    runner_metadata=runner_metadata,
                    topup_approval_callback=self._request_topup_approval if self.enable_missed_trial_topup else None,
                    instruction_continue_callback=self._request_instruction_continue,
                )
            else:
                self.controller = SessionRunnerController(
                    self.package,
                    audio_engine=None,
                    capture_options=self.capture_options,
                    enable_topup=self.enable_missed_trial_topup,
                    runner_metadata=runner_metadata,
                    topup_approval_callback=self._request_topup_approval if self.enable_missed_trial_topup else None,
                    instruction_continue_callback=self._request_instruction_continue,
                )
        except Exception as exc:
            self.controller = None
            self.event_label.setText(f"Participant setup could not prepare LSL: {exc}")
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
            return False
        self.demographics_submitted = True
        self._freeze_pre_run_controls()
        self.start_button.setEnabled(True)
        self.run_state_chip.setText("LSL Ready" if bool(self.capture_options.enable_lsl) else "Ready")
        lsl_message = str(getattr(lsl_status, "message", "") or "")
        self.event_label.setText(lsl_message or "Participant setup submitted")
        _append_output_diary_event(
            "participant_setup_submitted",
            package=self.package,
            participant_id=str(runner_metadata.get("participant_code") or self.package.participant_id),
            capture_options=self.capture_options.as_dict(),
            payload={
                "lsl_enabled": bool(getattr(lsl_status, "enabled", False)) if lsl_status is not None else bool(self.capture_options.enable_lsl),
                "lsl_message": lsl_message,
                "topup_enabled": self.enable_missed_trial_topup,
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
        return {
            "start_or_continue": ["Space", "Return", "Enter"],
            "pause_resume": ["Ctrl+P"],
            "stop": ["Ctrl+Shift+S"],
            "close": ["Ctrl+W"],
            "select_part_1": ["Alt+1"],
            "select_part_2": ["Alt+2"],
            "select_topup_preview": ["Ctrl+T"],
        }

    def _install_operator_action_shortcuts(self) -> None:
        q = self.q

        def _add(name: str, sequence: str, callback: Callable[[], None]) -> None:
            shortcut = q["QShortcut"](q["QKeySequence"](sequence), self.dialog)
            shortcut.setContext(q["Qt"].ShortcutContext.WindowShortcut)
            shortcut.activated.connect(callback)
            self.operator_action_shortcuts.setdefault(name, []).append(shortcut)

        for sequence in self.keyboard_shortcut_map()["pause_resume"]:
            _add("pause_resume", sequence, self._handle_pause_resume_shortcut)
        for sequence in self.keyboard_shortcut_map()["stop"]:
            _add("stop", sequence, self._handle_stop_shortcut)
        for sequence in self.keyboard_shortcut_map()["close"]:
            _add("close", sequence, self._handle_close_shortcut)
        for sequence in self.keyboard_shortcut_map()["select_part_1"]:
            _add("select_part_1", sequence, lambda key="1": self._handle_part_shortcut(key))
        for sequence in self.keyboard_shortcut_map()["select_part_2"]:
            _add("select_part_2", sequence, lambda key="2": self._handle_part_shortcut(key))
        for sequence in self.keyboard_shortcut_map()["select_topup_preview"]:
            _add("select_topup_preview", sequence, self._handle_topup_preview_shortcut)

    def _handle_pause_resume_shortcut(self) -> None:
        if self.pause_button.isEnabled():
            self._toggle_pause()

    def _handle_stop_shortcut(self) -> None:
        if self.stop_button.isEnabled():
            self._stop()

    def _handle_close_shortcut(self) -> None:
        if self.close_button.isEnabled():
            self._close()

    def _handle_part_shortcut(self, part_key: str) -> None:
        button = getattr(self, "part_buttons", {}).get(str(part_key))
        if button is not None and button.isEnabled():
            self._select_part_key(str(part_key), preview_first=True)

    def _handle_topup_preview_shortcut(self) -> None:
        if self._topup_slots_enabled_for_plan():
            self._select_current_part_topup_slot()

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
            "output_panel": self.output_panel,
            "output_summary": self.output_summary,
            "processing_panel": self.processing_panel,
            "part_selector_widget": self.part_selector_widget,
            "block_plan_widget": self.block_plan_widget,
            "tactile_timeline_widget": self.tactile_timeline_widget,
            "start_button": self.start_button,
            "pause_button": self.pause_button,
            "stop_button": self.stop_button,
            "close_button": self.close_button,
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
        timeline_debug = {}
        timeline_snapshot = getattr(self.tactile_timeline_widget, "timeline_debug_snapshot", None)
        if callable(timeline_snapshot):
            timeline_debug = dict(timeline_snapshot())
        experiment_control_debug = self._experiment_control_layout_debug()
        return {
            "dialog": {"width": int(self.dialog.width()), "height": int(self.dialog.height())},
            "layout_profile": self.layout_profile.as_dict(),
            "widgets": {name: self._dialog_relative_rect(widget) for name, widget in widgets.items() if widget is not None},
            "splitters": splitter_metrics,
            "timeline_debug": timeline_debug,
            "experiment_control_debug": experiment_control_debug,
            "keyboard_shortcuts": self.keyboard_shortcut_map(),
            "adaptive_mechanisms": {
                "right_stack_mode": self.layout_profile.right_stack_mode,
                "operator_tabs": self.operator_tabs is not None,
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
        failures: list[str] = []
        if dialog["width"] > profile.available_width or dialog["height"] > profile.available_height:
            failures.append(
                f"window {dialog['width']}x{dialog['height']} exceeds available "
                f"{profile.available_width}x{profile.available_height}"
            )
        for name, rect in widgets.items():
            if rect["x"] < 0 or rect["y"] < 0 or rect["right"] > dialog["width"] or rect["bottom"] > dialog["height"]:
                failures.append(f"{name} is clipped outside the dialog: {rect}")
        target = widgets.get("target_button", {})
        if target and (target.get("width") != profile.target_min_height or target.get("height") != profile.target_min_height):
            failures.append(f"target_button does not match fixed {profile.target_min_height}px square: {target}")
        processing = widgets.get("processing_panel", {})
        if processing and processing.get("height", 0) < profile.experiment_control_min_height:
            failures.append(
                "processing_panel is shorter than the profile minimum "
                f"{profile.experiment_control_min_height}px: {processing}"
            )
        experiment_control_debug = snapshot.get("experiment_control_debug") or {}
        content_min_height = int(experiment_control_debug.get("content_min_height") or 0)
        if processing and content_min_height and processing.get("height", 0) < content_min_height:
            failures.append(
                "processing_panel is shorter than the content-safe minimum "
                f"{content_min_height}px: {processing}"
            )
        clipped_lower = list(experiment_control_debug.get("clipped_widgets") or [])
        if clipped_lower:
            failures.append(f"lower Experiment Control widgets are clipped: {clipped_lower}")
        too_short_lower = list(experiment_control_debug.get("too_short_widgets") or [])
        if too_short_lower:
            failures.append(f"lower Experiment Control widgets are shorter than measured content: {too_short_lower}")
        overlap_pairs = list(experiment_control_debug.get("overlap_pairs") or [])
        if overlap_pairs:
            failures.append(f"lower Experiment Control widgets overlap: {overlap_pairs}")
        hidden_required = list(experiment_control_debug.get("hidden_required_widgets") or [])
        if hidden_required:
            failures.append(f"required lower Experiment Control widgets are hidden: {hidden_required}")
        if processing:
            workspace_width = int(getattr(self.workspace_splitter, "width", lambda: 0)())
            if workspace_width and processing.get("width", 0) < workspace_width - 8:
                failures.append(f"processing_panel does not span the lower workspace width: {processing}")
        timeline_debug = snapshot.get("timeline_debug") or {}
        row_names = list(timeline_debug.get("row_names") or [])
        if row_names != list(TIMELINE_ROW_NAMES):
            failures.append(f"timeline rows are {row_names}, expected {list(TIMELINE_ROW_NAMES)}")
        label_fit = dict(timeline_debug.get("label_fit") or {})
        if int(label_fit.get("overlap_count") or 0) > 0:
            failures.append(f"timeline labels overlap in {label_fit.get('overlap_count')} measured rect(s)")
        response = widgets.get("response_panel", {})
        output = widgets.get("output_panel", {})
        if response and output and output.get("y", 0) < response.get("bottom", 0):
            failures.append("output_panel is not positioned under response_panel")
        data_column = widgets.get("data_logging_column", {})
        settings_column = widgets.get("experiment_settings_column", {})
        if data_column and settings_column:
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

    def _keyboard_focus_is_pre_run_input(self) -> bool:
        focus = self.q["QApplication"].focusWidget()
        if focus is None:
            return False
        input_types = (
            self.q["QLineEdit"],
            self.q["QTextEdit"],
            self.q["QComboBox"],
            self.q["QCheckBox"],
        )
        return isinstance(focus, input_types)

    def _handle_primary_action_shortcut(self) -> None:
        if self.pending_instruction_request is not None:
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
        self.target_button.setEnabled(True)
        self.event_label.setText(f"Instruction continuation logged ({source})")
        self._set_primary_action_shortcuts_enabled(False)
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
            payload={"message": message},
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
            payload={"topup_enabled": self.enable_missed_trial_topup},
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
        self._set_primary_action_shortcuts_enabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        self.target_button.setEnabled(True)
        self._run_active = True
        self._run_paused = False
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

    def _request_topup_approval(self, summary: dict[str, Any]) -> bool:
        request = {"summary": dict(summary), "approved": False, "event": threading.Event()}
        self.messages.put(("topup_approval", request))
        request["event"].wait()
        return bool(request["approved"])

    def _request_instruction_continue(self, context: dict[str, Any]) -> bool:
        request = {"context": dict(context), "approved": False, "event": threading.Event()}
        self.messages.put(("instruction_continue", request))
        request["event"].wait()
        return bool(request["approved"])

    def _click(self) -> None:
        if self.pending_instruction_request is not None:
            self._approve_pending_instruction_continue(source="click target")
            return
        if self.controller is None:
            self.event_label.setText("Start the run before logging responses.")
            return
        self.controller.log_click(in_target=True)
        if self.timeline_state.active:
            self.timeline_state.record_click(self.timeline_state.elapsed_s)
            self._update_tactile_timeline_display()
        self.event_label.setText("Participant click logged")
        _append_output_diary_event(
            "target_clicked",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={
                "during_playback": self._run_active,
                "elapsed_s": self.timeline_state.elapsed_s if self.timeline_state.active else "",
            },
            create=True,
        )

    def _continue_instruction_button(self) -> None:
        self._approve_pending_instruction_continue(source="button")

    def _toggle_pause(self) -> None:
        if self.controller is None:
            return
        if self.pause_button.text() == "Pause":
            self.controller.pause()
            self.pause_button.setText("Resume")
            self._run_paused = True
            self.run_state_chip.setText("Paused")
            self.progress_label.setText("Paused")
            event_type = "pause_clicked"
        else:
            self.controller.resume()
            self.pause_button.setText("Pause")
            self._run_paused = False
            self.run_state_chip.setText("Running")
            event_type = "resume_clicked"
        _append_output_diary_event(
            event_type,
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
            self.next_tactile_label.setText(
                f"Next tactile: Trial {next_cue.trial_number} in {countdown:.1f}s{soa}{row}"
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
        mode = "recorded_intent" if offscreen else self._move_os_cursor_to_global_center(x, y)
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
        if self._last_recenter_backend_warning:
            record["backend_warning"] = self._last_recenter_backend_warning
        self.recenter_records.append(record)

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
        while not self.messages.empty():
            kind, payload = self.messages.get_nowait()
            if kind == "progress":
                if dict(payload).get("ui_event") == "block_schedule":
                    self._handle_block_schedule(dict(payload))
                    continue
                if dict(payload).get("ui_event") == "topup_draft":
                    self._handle_topup_draft(dict(payload))
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
            elif kind == "done":
                self._handle_done(payload)
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

    def _handle_instruction_continue(self, payload: dict[str, Any]) -> None:
        context = dict(payload.get("context") or {})
        self.pending_instruction_request = payload
        mode = str(context.get("mode") or "click")
        label = str(context.get("instruction_label") or "instruction")
        self.target_button.setEnabled(True)
        if mode == "button":
            self.instruction_button.setText(str(context.get("button_label") or "Continue"))
            self.instruction_button.setVisible(True)
            self.event_label.setText(f"Click the target, press Space/Enter, or use Continue after {label}.")
        else:
            self.instruction_button.setVisible(False)
            self.event_label.setText(f"Click the target or press Space/Enter to continue after {label}.")
        self._set_primary_action_shortcuts_enabled(True)

    def _handle_topup_approval(self, payload: dict[str, Any]) -> None:
        q = self.q
        summary = dict(payload.get("summary") or {})
        _append_output_diary_event(
            "topup_approval_requested",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"summary": summary},
            create=True,
        )
        missed = int(summary.get("missed_trial_count") or 0)
        topup_trials = int(summary.get("topup_trial_count") or 0)
        fillers = int(summary.get("filler_trial_count") or 0)
        part = str(summary.get("part_number") or "").strip()
        part_text = f" for Part {part}" if part else ""
        message = (
            f"{missed} tactile trial(s) need top-up{part_text}.\n"
            f"The prepared top-up block has {topup_trials} trial(s), including {fillers} row-structure filler trial(s).\n\n"
            "Play the top-up block now?"
        )
        if _env_flag("PPS_FOCUS_VALIDATION_AUTO_APPROVE_TOPUP"):
            self.validation_topup_approval_records.append(
                {
                    "summary": summary,
                    "approved": True,
                    "mode": "validation_auto_approve",
                    "timestamp_unix": time.time(),
                }
            )
            payload["approved"] = True
            _append_output_diary_event(
                "topup_approval_resolved",
                package=self.package,
                capture_options=self.capture_options.as_dict(),
                payload={"summary": summary, "approved": True, "mode": "validation_auto_approve"},
                create=True,
            )
            payload["event"].set()
            return
        answer = q["QMessageBox"].question(
            self.dialog,
            "Play Top-up Block?",
            message,
            q["QMessageBox"].StandardButton.Yes | q["QMessageBox"].StandardButton.No,
            q["QMessageBox"].StandardButton.No,
        )
        payload["approved"] = answer == q["QMessageBox"].StandardButton.Yes
        self.validation_topup_approval_records.append(
            {
                "summary": summary,
                "approved": bool(payload["approved"]),
                "mode": "operator_dialog",
                "timestamp_unix": time.time(),
            }
        )
        _append_output_diary_event(
            "topup_approval_resolved",
            package=self.package,
            capture_options=self.capture_options.as_dict(),
            payload={"summary": summary, "approved": bool(payload["approved"]), "mode": "operator_dialog"},
            create=True,
        )
        payload["event"].set()

    def _handle_done(self, result: Any) -> None:
        self.result = result
        self.exit_code = 0 if result.completed else 2
        self._run_active = False
        self._run_paused = False
        self.timeline_state.active = False
        if self.active_display_block_index is not None:
            self.completed_display_block_indices.add(int(self.active_display_block_index))
        self.active_display_block_index = None
        if hasattr(self, "block_plan_widget"):
            self.block_plan_widget.update()
        self.target_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self._set_primary_action_shortcuts_enabled(False)
        self.progress.setValue(1000 if result.completed else self.progress.value())
        self.run_state_chip.setText("Complete" if result.completed else "Interrupted")
        self.progress_label.setText("Complete" if result.completed else "Interrupted")
        lines = [str(result.summary_text or "").strip()]
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
                "warnings": list(getattr(result, "warnings", []) or []),
            },
            create=True,
        )
        self._maybe_open_analysis_review(result)
        self._shutdown_owned_audio_engine()
        self.timer.stop()

    def _maybe_open_analysis_review(self, result: Any) -> None:
        if not bool(getattr(result, "completed", False)):
            return
        if _env_flag("PPS_FOCUS_DISABLE_ANALYSIS_POPUP"):
            return
        capture_options = dict(getattr(result, "capture_options", {}) or {})
        if not bool(capture_options.get("write_analysis_csvs", True)):
            return
        try:
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
        path.parent.mkdir(parents=True, exist_ok=True)
        self.dialog.grab().save(str(path))

    def exec(
        self,
        *,
        fullscreen: bool = True,
        auto_start: bool = True,
        auto_close_ms: int | None = None,
        screenshot_path: Path | None = None,
    ) -> int:
        if auto_start:
            self.q["QTimer"].singleShot(350, self.start)
        if screenshot_path is not None:
            self.q["QTimer"].singleShot(250, lambda: self.grab_screenshot(screenshot_path))
        if auto_close_ms is not None:
            self.q["QTimer"].singleShot(int(auto_close_ms), self.dialog.accept)
        if not _env_flag("PPS_FOCUS_DISABLE_PREWARM"):
            self.q["QTimer"].singleShot(700, self.start_next_participant_prewarm)
        if fullscreen and hasattr(self.dialog, "showMaximized"):
            self.dialog.showMaximized()
        elif fullscreen and hasattr(self.dialog, "showFullScreen"):
            self.dialog.showFullScreen()
        else:
            self.dialog.show()
        self.dialog.exec()
        return int(self.exit_code)


def run_focus_window(
    session_manifest: Path,
    *,
    capture_options: SessionCaptureOptions | None = None,
    enable_missed_trial_topup: bool = False,
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
    enable_missed_trial_topup: bool = False,
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
    initial_participant = str(
        participant_id
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

    selected_action: dict[str, Any] = {"open_environment": False}
    setup_mode: dict[str, bool] = {"enabled": False}
    initializing: dict[str, bool] = {"busy": False}
    gate_shortcuts: dict[str, Any] = {}
    messages: queue.Queue[tuple[str, Any]] = queue.Queue()

    layout = q["QVBoxLayout"](dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(14)
    panel, panel_layout = _panel(q, "Experiment Environment")
    heading = q["QLabel"](
        "Resume an existing data collection environment, or pick a folder and start a fresh timestamped environment."
    )
    heading.setObjectName("mutedLabel")
    heading.setWordWrap(True)
    panel_layout.addWidget(heading)
    step_label = q["QLabel"]("Step 1: Choose 1 Resume or 2 Pick Output Folder / Start New Session.")
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
        or "Current decision: press 1 to resume a ready environment, or press 2 to pick an output folder."
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
    resume_button = q["QPushButton"]("1 Resume Experiment")
    resume_button.setObjectName("resumeExperimentButton")
    resume_button.setProperty("class", "primary")
    resume_button.setProperty("decisionTone", "resume")
    choose_folder_button = q["QPushButton"]("2 Pick Output Folder / Start New Session")
    choose_folder_button.setObjectName("chooseOutputFolderButton")
    choose_folder_button.setProperty("decisionTone", "folder")
    initiate_button = q["QPushButton"]("Initiate New Data Collection Environment")
    initiate_button.setObjectName("initiateEnvironmentButton")
    initiate_button.setEnabled(False)
    close_button = q["QPushButton"]("Close")
    buttons.addWidget(resume_button)
    buttons.addWidget(choose_folder_button)
    buttons.addWidget(initiate_button)
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
        return (not initializing["busy"]) and (not setup_mode["enabled"])

    def _update_decision_shortcuts() -> None:
        resume_shortcut = gate_shortcuts.get("resume")
        choose_shortcut = gate_shortcuts.get("choose")
        if resume_shortcut is not None:
            resume_shortcut.setEnabled(_decision_shortcuts_enabled() and _resume_ready())
        if choose_shortcut is not None:
            choose_shortcut.setEnabled(_decision_shortcuts_enabled())

    def _refresh_gate_attention() -> None:
        errors = _validation_errors()
        if setup_mode["enabled"]:
            if errors:
                step_label.setText("Step 2: Fill the highlighted required fields.")
                _set_attention(step_label, "current")
            else:
                step_label.setText("Step 3: Create the data collection environment.")
                _set_attention(step_label, "complete")
            _set_widget_gate_state(output_folder_input, "complete" if _selected_parent().is_dir() else "needed")
            _set_widget_gate_state(profile_combo, "complete" if _selected_profile() else "needed")
            _set_widget_gate_state(session_name_input, "complete" if _session_slug() else "needed")
            _set_attention(resume_button, "locked")
            _set_attention(choose_folder_button, "complete")
            _set_attention(initiate_button, "go" if not errors else "locked")
            _set_attention(message, "complete" if not errors else "current")
        else:
            step_label.setText("Step 1: Choose 1 Resume or 2 Pick Output Folder / Start New Session.")
            _set_attention(step_label, "current")
            _set_widget_gate_state(output_folder_input, "locked")
            _set_widget_gate_state(profile_combo, "locked")
            _set_widget_gate_state(session_name_input, "locked")
            if _resume_ready():
                _set_attention(resume_button, "current")
                _set_attention(
                    choose_folder_button,
                    "available" if active_environment.get("kind") == "existing_environment" else "current",
                )
            else:
                _set_attention(resume_button, "locked")
                _set_attention(choose_folder_button, "current")
            _set_attention(initiate_button, "locked")
            _set_attention(message, "current")
        _update_decision_shortcuts()

    def _set_environment_busy(busy: bool) -> None:
        initializing["busy"] = busy
        resume_button.setEnabled((not busy) and _resume_ready())
        choose_folder_button.setEnabled(not busy)
        initiate_button.setEnabled((not busy) and _can_initiate())
        close_button.setEnabled(not busy)
        output_folder_input.setEnabled(not busy)
        profile_combo.setEnabled((not busy) and setup_mode["enabled"])
        session_name_input.setEnabled(not busy)
        copy_button.setEnabled(not busy)
        progress.setVisible(busy)
        if busy:
            progress.setRange(0, 0)
        else:
            progress.setRange(0, 1000)
            progress.setValue(0)
        _refresh_gate_attention()

    def _validation_errors() -> list[str]:
        if not setup_mode["enabled"]:
            return []
        parent = _selected_parent()
        if not output_folder_input.text().strip():
            return ["Choose an output parent folder."]
        if not parent.is_dir():
            return ["Output folder must be an existing folder."]
        if not _selected_profile():
            return ["Choose an experiment profile."]
        if not _session_slug():
            return ["Enter a Windows-safe session name."]
        return []

    def _can_initiate() -> bool:
        return setup_mode["enabled"] and not _validation_errors()

    def _refresh_initiate_state() -> None:
        errors = _validation_errors()
        initiate_button.setEnabled((not initializing["busy"]) and setup_mode["enabled"] and not errors)
        if setup_mode["enabled"]:
            if errors:
                message.setText(errors[0])
            else:
                preview = _selected_parent() / f"{_session_slug()}_<timestamp>"
                message.setText(f"Ready to create {preview}.")
        output_folder_input.setToolTip(output_folder_input.text().strip())
        _refresh_gate_attention()

    def _unlock_for_new_environment(parent: Path) -> None:
        setup_mode["enabled"] = True
        active_environment.update(
            {
                "root": Path(parent).expanduser(),
                "profile_id": "",
                "participant_id": "P001",
                "session_name": "",
                "runner_diary_path": None,
                "kind": "new_parent",
            }
        )
        output_folder_input.setReadOnly(False)
        output_folder_input.setText(str(parent))
        profile_combo.setEnabled(True)
        profile_combo.setCurrentIndex(0)
        session_name_input.setReadOnly(False)
        session_name_input.setText("")
        resume_button.setEnabled(False)
        message.setText("New output parent selected. Experiment Profile and Session Name are now required.")
        _refresh_initiate_state()

    def _lock_for_existing_environment(context: dict[str, Any]) -> None:
        setup_mode["enabled"] = False
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
        initiate_button.setEnabled(False)
        markers = ", ".join(context.get("markers") or ["environment marker"])
        message.setText(f"Existing experiment environment found ({markers}). Press 1 or click Resume Experiment.")
        _refresh_gate_attention()

    def _select_output_folder(folder: Path) -> None:
        context = _classify_launcher_output_folder(
            folder,
            fallback_profile_id=initial_profile,
            fallback_session_name=initial_session_name,
            fallback_participant_id=initial_participant,
        )
        if context.get("kind") == "existing_environment":
            _lock_for_existing_environment(context)
        else:
            _unlock_for_new_environment(Path(context.get("root") or folder))

    def _copy_output_path() -> None:
        try:
            app.clipboard().setText(output_folder_input.text())
            message.setText("Output folder path copied.")
        except Exception as exc:
            message.setText(f"Could not copy path: {exc}")

    def _choose_parent_folder() -> None:
        current_root = Path(str(active_environment.get("root") or initial_output_root)).expanduser()
        start_folder = current_root if current_root.is_dir() else DEFAULT_SESSION_ROOT
        parent = q["QFileDialog"].getExistingDirectory(
            dialog,
            "Choose Output Folder",
            str(start_folder),
        )
        if parent:
            _select_output_folder(Path(parent))

    def _resume_environment() -> None:
        if not _resume_ready():
            message.setText("No remembered experiment environment is ready. Choose a new output folder first.")
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
            "resume_experiment_clicked",
            session_root=output_root,
            experiment_name=session_name,
            profile_id=profile_id,
            participant_id=participant,
            capture_options=_capture_options_for_launcher(),
            create=True,
        )
        selected_action["open_environment"] = True
        dialog.accept()

    def _start_environment_initialization() -> None:
        errors = _validation_errors()
        if errors:
            message.setText(errors[0])
            return
        parent = _selected_parent()
        profile_id = _selected_profile()
        session_name = _session_name()
        _set_environment_busy(True)
        message.setText("Creating data collection environment...")

        def _progress_callback(payload: dict[str, Any]) -> None:
            messages.put(("progress", dict(payload)))

        def _worker() -> None:
            try:
                result = initiate_data_collection_environment(
                    parent_folder=parent,
                    profile_id=profile_id,
                    session_name=session_name,
                    participant_id="P001",
                    capture_options=capture_options,
                    progress_callback=_progress_callback,
                )
            except Exception as exc:
                messages.put(("error", str(exc)))
            else:
                messages.put(("done", result))

        threading.Thread(target=_worker, name="pps-environment-init", daemon=True).start()

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
                _refresh_initiate_state()
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
                selected_action["open_environment"] = True
                message.setText("Environment ready.")
                dialog.accept()

    def _focus_is_editing_gate_text() -> bool:
        focus = app.focusWidget()
        return bool(
            focus in (output_folder_input, session_name_input)
            and focus.isEnabled()
            and hasattr(focus, "isReadOnly")
            and not focus.isReadOnly()
        )

    def _resume_shortcut_activated() -> None:
        if _focus_is_editing_gate_text() or not _decision_shortcuts_enabled() or not resume_button.isEnabled():
            return
        resume_button.click()

    def _choose_shortcut_activated() -> None:
        if _focus_is_editing_gate_text() or not _decision_shortcuts_enabled() or not choose_folder_button.isEnabled():
            return
        choose_folder_button.click()

    timer = q["QTimer"](dialog)
    timer.timeout.connect(_drain_environment_messages)
    timer.start(100)

    output_folder_input.textChanged.connect(lambda _text: _refresh_initiate_state())
    profile_combo.currentIndexChanged.connect(lambda _index: _refresh_initiate_state())
    session_name_input.textChanged.connect(lambda _text: _refresh_initiate_state())
    copy_button.clicked.connect(_copy_output_path)
    choose_folder_button.clicked.connect(_choose_parent_folder)
    resume_button.clicked.connect(_resume_environment)
    initiate_button.clicked.connect(_start_environment_initialization)
    close_button.clicked.connect(dialog.reject)
    gate_shortcuts["resume"] = q["QShortcut"](q["QKeySequence"]("1"), dialog)
    gate_shortcuts["resume"].setContext(q["Qt"].ShortcutContext.ApplicationShortcut)
    gate_shortcuts["resume"].activated.connect(_resume_shortcut_activated)
    gate_shortcuts["choose"] = q["QShortcut"](q["QKeySequence"]("2"), dialog)
    gate_shortcuts["choose"].setContext(q["Qt"].ShortcutContext.ApplicationShortcut)
    gate_shortcuts["choose"].activated.connect(_choose_shortcut_activated)
    resume_button.setEnabled(_resume_ready())
    _refresh_gate_attention()

    def _validation_auto_environment() -> None:
        target_profile = os.environ.get("PPS_FOCUS_VALIDATION_PROFILE", STUDY5_PROFILE_ID).strip() or STUDY5_PROFILE_ID
        parent = DEFAULT_SESSION_ROOT
        parent.mkdir(parents=True, exist_ok=True)
        _unlock_for_new_environment(parent)
        index = profile_combo.findData(target_profile)
        if index >= 0:
            profile_combo.setCurrentIndex(index)
        session_name_input.setText("Study 5 validation")
        q["QTimer"].singleShot(250, lambda: initiate_button.click() if initiate_button.isEnabled() else None)

    if _env_flag("PPS_FOCUS_VALIDATION_LAUNCHER_AUTO_CLICK"):
        q["QTimer"].singleShot(200, _validation_auto_environment)

    accepted = dialog.exec() == q["QDialog"].DialogCode.Accepted
    if not accepted or not selected_action.get("open_environment"):
        return 1
    return _run_environment_operations_window(
        capture_options=capture_options,
        enable_missed_trial_topup=enable_missed_trial_topup,
        participant_id=str(active_environment.get("participant_id") or initial_participant or "P001"),
    )


def _run_environment_operations_window(
    *,
    capture_options: SessionCaptureOptions | None = None,
    enable_missed_trial_topup: bool = False,
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
    initial_participant = str(
        participant_id
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
        show_driver_button = bool(readiness is not None and not readiness.publication_ready)
    except Exception as exc:
        launcher_message = initial_message or f"Audio preflight could not run: {exc}"
        show_driver_button = not bool(initial_message)
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
            driver_button.setVisible(not readiness.publication_ready)
            return readiness
        except Exception as exc:
            readiness_state["readiness"] = None
            message.setText(f"Audio preflight could not run: {exc}")
            driver_button.setVisible(True)
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
                driver_button.setVisible(True)
            else:
                message.setText(refreshed.message())
                driver_button.setVisible(not refreshed.publication_ready)
        else:
            _refresh_launcher_audio_preflight()

    driver_button.clicked.connect(_open_audio_dependency_dialog)
    if show_driver_button and not initial_message:
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
        return capture_options.as_dict() if capture_options is not None else SessionCaptureOptions().as_dict()

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
        if profile_combo.isEnabled():
            QTest.mouseClick(profile_combo, q["Qt"].MouseButton.LeftButton)
            validation_launcher_clicks.append(
                {
                    "label": "click Study/profile selector",
                    "timestamp_unix": time.time(),
                    "selected_profile": str(profile_combo.currentData() or ""),
                }
            )
        else:
            validation_launcher_clicks.append(
                {
                    "label": "click Study/profile selector",
                    "timestamp_unix": time.time(),
                    "selected_profile": str(profile_combo.currentData() or ""),
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
    single_instance = _acquire_runner_single_instance()
    if not single_instance.acquired:
        _show_runner_single_instance_notice(single_instance.message)
        return SINGLE_INSTANCE_EXIT_CODE
    try:
        if args.launcher:
            return run_launcher_window(
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                participant_id=args.participant_id,
            )
        if args.session_manifest is not None:
            return run_focus_window(
                args.session_manifest,
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                manual_start=args.manual_start,
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
                    participant_id=args.participant_id,
                    initial_message=str(exc),
                )
            return run_focus_window(
                manifest,
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                manual_start=args.manual_start,
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
                    participant_id=args.participant_id,
                    initial_message=str(exc),
                )
            return run_focus_window(
                manifest,
                capture_options=options,
                enable_missed_trial_topup=args.enable_missed_trial_topup,
                manual_start=args.manual_start,
                auto_close_ms=args.validation_auto_close_ms,
                screenshot_path=args.validation_screenshot,
            )
        return run_launcher_window(
            capture_options=options,
            enable_missed_trial_topup=args.enable_missed_trial_topup,
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
