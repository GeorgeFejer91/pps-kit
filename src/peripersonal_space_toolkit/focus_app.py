"""Native participant Focus Mode launcher for prepared PPS sessions."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .app_assets import apply_qt_app_icon, set_windows_app_user_model_id
from .focus_layout import (
    FocusLayoutProfile,
    render_focus_layout_profile,
    render_focus_style_sheet,
)
from .focus_timeline import TactileRecenterController, TactileTimelineCue, TactileTimelineState
from .session_runner import (
    DEFAULT_DASHBOARD_STATE_ROOT,
    DEFAULT_PROJECT_REGISTRY_ROOT,
    DEFAULT_RENDER_DIR,
    DEFAULT_SESSION_ROOT,
    SessionCaptureOptions,
    SessionRunnerController,
    claim_prepared_session,
    find_latest_dashboard_run_setup,
    load_last_experiment_pointer,
    load_run_package,
    next_segment_participant,
    prepare_segment_run_package,
    record_experiment_activity,
    record_prepared_session_queue,
    segment_run_setup_participants,
)
from .preload_inventory import load_preload_inventory
from .runtime_paths import repo_root


DEFAULT_FOCUS_PROFILE_DESIGN_PATH = DEFAULT_DASHBOARD_STATE_ROOT / "focus_profile_runner_design.json"
DEFAULT_FOCUS_LAYOUT_PROFILE = render_focus_layout_profile(1120, 720)
FOCUS_STYLE_SHEET = render_focus_style_sheet(DEFAULT_FOCUS_LAYOUT_PROFILE)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run native PPS Focus Mode from a prepared session manifest.")
    parser.add_argument("--session-manifest", type=Path, help="Path to local_data/sessions/.../session_manifest.json.")
    parser.add_argument("--last-experiment", action="store_true", help="Open the last launchable dashboard experiment.")
    parser.add_argument("--latest-dashboard-setup", action="store_true", help="Prepare and open the newest prepared dashboard Segment 6 setup.")
    parser.add_argument("--launcher", action="store_true", help="Open the profile/session launcher instead of auto-resuming.")
    parser.add_argument("--profile", default="", help="Load a finished study/profile preload directly in the runner, for example study5_box_breathing_pps.")
    parser.add_argument("--participant-id", default="", help="Participant ID to materialize when using --latest-dashboard-setup.")
    parser.add_argument("--manual-start", action="store_true", help="Open the runner window but wait for Start Run before playback.")
    parser.add_argument("--no-lsl", action="store_true", help="Do not create live LSL marker outlets for this run.")
    parser.add_argument("--no-internal-xdf", action="store_true", help="Do not write the local events.xdf mirror.")
    parser.add_argument("--no-analysis-csv", action="store_true", help="Do not write immediate analysis CSV outputs.")
    parser.add_argument("--no-backup-recording", action="store_true", help="Do not write the local full-audio evidence WAV.")
    parser.add_argument("--enable-missed-trial-topup", action="store_true", help="Prepare and request approval for one final missed-trial top-up block.")
    parser.add_argument("--validation-screenshot", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--validation-auto-close-ms", type=int, default=None, help=argparse.SUPPRESS)
    return parser


def _require_qt() -> dict[str, Any]:
    try:
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtGui import QBrush, QColor, QCursor, QFontDatabase, QIcon, QPainter, QPen
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
            QLineEdit,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QSizePolicy,
            QSplitter,
            QTabWidget,
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
        "QDialog": QDialog,
        "QFileDialog": QFileDialog,
        "QFrame": QFrame,
        "QGridLayout": QGridLayout,
        "QHBoxLayout": QHBoxLayout,
        "QFontDatabase": QFontDatabase,
        "QIcon": QIcon,
        "QLabel": QLabel,
        "QLineEdit": QLineEdit,
        "QMessageBox": QMessageBox,
        "QPainter": QPainter,
        "QPen": QPen,
        "QProgressBar": QProgressBar,
        "QPushButton": QPushButton,
        "QSizePolicy": QSizePolicy,
        "QSplitter": QSplitter,
        "QTabWidget": QTabWidget,
        "QTextEdit": QTextEdit,
        "QTimer": QTimer,
        "QVBoxLayout": QVBoxLayout,
        "QWidget": QWidget,
        "Qt": Qt,
    }


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
        layout.addWidget(heading)
    return frame, layout


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


def _create_tactile_timeline_widget(q: dict[str, Any], state: TactileTimelineState) -> Any:
    class TactileTimelineWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            self.setMinimumHeight(40)

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                width = max(1, int(self.width()))
                height = max(1, int(self.height()))
                margin = 12
                line_y = max(18, height // 2)
                usable = max(1, width - (2 * margin))
                duration = max(0.001, float(state.duration_s or 0.0))

                base_pen = q["QPen"](q["QColor"]("#bcc7bd"))
                base_pen.setWidth(2)
                painter.setPen(base_pen)
                painter.drawLine(margin, line_y, width - margin, line_y)

                if not state.cues:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, "No tactile cues loaded")
                    return

                for cue in state.cues:
                    status = state.cue_status(cue)
                    color = {
                        "passed": "#647067",
                        "recentered": "#246b55",
                        "next": "#8c2f2f",
                        "upcoming": "#d9dfd6",
                    }.get(status, "#d9dfd6")
                    x = margin + int(max(0.0, min(1.0, cue.time_s / duration)) * usable)
                    radius = 5 if status == "next" else 4
                    marker_pen = q["QPen"](q["QColor"]("#202621" if status == "next" else "#bcc7bd"))
                    marker_pen.setWidth(1)
                    painter.setPen(marker_pen)
                    painter.setBrush(q["QBrush"](q["QColor"](color)))
                    painter.drawEllipse(x - radius, line_y - radius, radius * 2, radius * 2)

                cursor_x = margin + int(max(0.0, min(1.0, state.elapsed_s / duration)) * usable)
                cursor_pen = q["QPen"](q["QColor"]("#246b55"))
                cursor_pen.setWidth(2)
                painter.setPen(cursor_pen)
                painter.drawLine(cursor_x, max(4, line_y - 18), cursor_x, min(height - 4, line_y + 18))
            finally:
                painter.end()

    return TactileTimelineWidget()


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
    target_width: int = 1120,
    target_height: int = 720,
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
    )


def _is_launchable_session_manifest(path: Path) -> bool:
    try:
        package = load_run_package(path)
    except Exception:
        return False
    return bool(package.blocks)


def prepare_latest_focus_session(
    participant_id: str | None = None,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    """Materialize a session package from the newest prepared Segment 6 setup."""
    run_setup = find_latest_dashboard_run_setup()
    if run_setup is None:
        raise FileNotFoundError("No prepared Segment 6 dashboard setup was found.")
    participant = (participant_id or "").strip()
    if not participant:
        participants = segment_run_setup_participants(run_setup)
        if not participants:
            raise ValueError(f"Prepared setup has no participants: {run_setup}")
        participant = participants[0]
    claimed = claim_prepared_session(run_setup, participant, state_root=DEFAULT_DASHBOARD_STATE_ROOT)
    if claimed is not None:
        return claimed
    package = prepare_segment_run_package(
        run_setup,
        participant,
        session_root=DEFAULT_SESSION_ROOT,
        progress_callback=progress_callback,
    )
    record_experiment_activity(
        "session_prepared",
        run_setup_manifest_path=str(run_setup),
        session_manifest_path=str(package.manifest_path),
        session_dir=str(package.session_dir),
        participant_id=participant,
    )
    return package.manifest_path


def prepare_last_or_latest_focus_session(
    participant_id: str | None = None,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    """Open the last launchable session, falling back to the newest prepared setup."""
    pointer = load_last_experiment_pointer()
    session_text = str(pointer.get("session_manifest_path") or "").strip()
    session_manifest = Path(session_text) if session_text else Path()
    if session_text and _is_launchable_session_manifest(session_manifest):
        return session_manifest
    run_setup_text = str(pointer.get("run_setup_manifest_path") or "").strip()
    run_setup = Path(run_setup_text) if run_setup_text else Path()
    if run_setup_text and run_setup.exists():
        participant = (participant_id or str(pointer.get("participant_id") or "")).strip()
        if not participant:
            participants = segment_run_setup_participants(run_setup)
            participant = participants[0] if participants else ""
        if participant:
            claimed = claim_prepared_session(run_setup, participant, state_root=DEFAULT_DASHBOARD_STATE_ROOT)
            if claimed is not None:
                return claimed
            package = prepare_segment_run_package(
                run_setup,
                participant,
                session_root=DEFAULT_SESSION_ROOT,
                progress_callback=progress_callback,
            )
            record_experiment_activity(
                "session_prepared",
                run_setup_manifest_path=str(run_setup),
                session_manifest_path=str(package.manifest_path),
                session_dir=str(package.session_dir),
                participant_id=participant,
            )
            return package.manifest_path
    return prepare_latest_focus_session(
        participant_id or str(pointer.get("participant_id") or ""),
        progress_callback=progress_callback,
    )


def _focus_dashboard_controller() -> Any:
    from . import dashboard_app

    return dashboard_app.DashboardController(
        design_path=DEFAULT_FOCUS_PROFILE_DESIGN_PATH,
        render_dir=DEFAULT_RENDER_DIR,
        session_root=DEFAULT_SESSION_ROOT,
        import_dir=dashboard_app.DEFAULT_IMPORT_DIR,
        preview_dir=dashboard_app.DEFAULT_PREVIEW_DIR,
        project_registry_root=DEFAULT_PROJECT_REGISTRY_ROOT,
    )


def finished_profile_options() -> list[tuple[str, str]]:
    """Return Segment 6-launchable study/profile presets for the runner launcher."""
    inventory = load_preload_inventory(repo_root())
    profiles = inventory.get("profiles", [])
    options: list[tuple[str, str]] = []
    for profile in profiles:
        finished = bool(profile.get("finished_profile")) or (
            str(profile.get("runner_readiness") or "") == "ready"
            and bool(profile.get("profile_checks_passed"))
            and bool(profile.get("segment_0_to_4_profile_checks_passed"))
        )
        launchable = bool(profile.get("segment_6_launchable")) or finished
        if not (finished and launchable):
            continue
        template_id = str(profile.get("template_id") or "").strip()
        if not template_id:
            continue
        label = str(profile.get("variant_display") or profile.get("visible_variant_label") or template_id).strip()
        options.append((template_id, label or template_id))
    options.sort(key=lambda item: (0 if item[0] == "study5_box_breathing_pps" else 1, item[1].lower()))
    return options


def prepare_profile_focus_session(
    profile_id: str,
    participant_id: str | None = None,
    *,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    """Materialize a participant session directly from a finished preload profile."""
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
    controller = _focus_dashboard_controller()
    inventory_profiles = controller.preload_inventory_payload().get("profiles", [])
    status = next((item for item in inventory_profiles if item.get("template_id") == profile), None)
    if status is None:
        raise ValueError(f"Unknown study/profile preset: {profile}")
    if not (status.get("finished_profile") and status.get("segment_6_launchable")):
        reason = str(status.get("profile_completion_status") or status.get("runner_readiness") or "unfinished_preload")
        raise ValueError(
            f"Study/profile preset '{profile}' is not a finished Segment 6 launchable profile yet ({reason})."
        )

    controller.load_template(profile, snapshot=False)
    controller.prepare_session(
        {"participant_id": participant},
        progress_callback=progress_callback,
        snapshot=False,
    )
    package = controller.current_run_package
    if package is None or not Path(package.manifest_path).is_file():
        raise RuntimeError(f"Study/profile preset '{profile}' did not produce a session manifest.")
    record_experiment_activity(
        "session_prepared",
        template_id=profile,
        run_setup_manifest_path=str(package.source_run_setup_manifest_path or ""),
        session_manifest_path=str(package.manifest_path),
        session_dir=str(package.session_dir),
        participant_id=participant,
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


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) else default


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

    def _click(widget: Any, label: str) -> None:
        if widget is None or not widget.isEnabled():
            return
        QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
        clicks.append({"label": label, "timestamp_unix": time.time()})

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

    q["QTimer"].singleShot(500, lambda: _click(window.start_button, "Start Run"))
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
    scheduled_events: set[int] = set()
    completed_events: set[int] = set()
    pending: list[dict[str, Any]] = []
    start_clicked = {"value": False}
    miss_keys: set[str] | None = None

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
        center = window.target_button.mapToGlobal(window.target_button.rect().center())
        return int(center.x()), int(center.y())

    def _click_widget(widget: Any, label: str, *, preferred_backend: str = "qtest") -> str:
        if widget is None or not widget.isEnabled():
            return "skipped_disabled"
        backend_used = preferred_backend
        if widget is not window.target_button or label.startswith("instruction:"):
            QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
            return "qtest_control"
        if preferred_backend == "pyautogui":
            try:
                import pyautogui  # type: ignore

                pyautogui.FAILSAFE = False
                center = widget.mapToGlobal(widget.rect().center())
                pyautogui.click(int(center.x()), int(center.y()))
                return "pyautogui"
            except Exception as exc:
                records.append({"label": "pyautogui_backend_unavailable", "message": str(exc), "timestamp_unix": time.time()})
                backend_used = "pynput"
        if backend_used == "pynput":
            try:
                from pynput.mouse import Button, Controller

                mouse = Controller()
                center = widget.mapToGlobal(widget.rect().center())
                mouse.position = (int(center.x()), int(center.y()))
                mouse.press(Button.left)
                mouse.release(Button.left)
                return "pynput"
            except Exception as exc:
                records.append({"label": "pynput_backend_unavailable", "message": str(exc), "timestamp_unix": time.time()})
                backend_used = "win32"
        if backend_used == "win32" and not window._offscreen_platform():
            try:
                import ctypes

                x, y = _target_center() if widget is window.target_button else (
                    int(widget.mapToGlobal(widget.rect().center()).x()),
                    int(widget.mapToGlobal(widget.rect().center()).y()),
                )
                ctypes.windll.user32.SetCursorPos(int(x), int(y))
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                return "win32"
            except Exception as exc:
                records.append({"label": "win32_backend_unavailable", "message": str(exc), "timestamp_unix": time.time()})
        QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
        return "qtest"

    def _continue_instruction_if_needed() -> None:
        request = window.pending_instruction_request
        if request is None:
            return
        context = dict(request.get("context") or {})
        mode = str(context.get("mode") or "click")
        label = str(context.get("instruction_label") or "instruction")
        widget = window.instruction_button if mode == "button" else window.target_button
        backend = _click_widget(widget, f"instruction: {label}", preferred_backend=backend_requested)
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
            if event.event_type != "tactile_onset" or event.event_id in scheduled_events:
                continue
            payload = dict(event.payload or {})
            is_topup = _truthy(payload.get("is_topup") or payload.get("Is_Topup") or payload.get("block_is_topup_block"))
            block_index = _validation_int(payload.get("block_index") or payload.get("block_number"), default=0)
            sample_index = _validation_int(payload.get("sample_index") or payload.get("planned_sample_index"), default=0)
            key = _validation_event_key(block_index, payload, sample_index)
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
            scheduled_events.add(event.event_id)
            item = {
                "event_id": event.event_id,
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
                completed_events.add(event.event_id)
                records.append({**item, "label": "tactile_response_plan", "timestamp_unix": time.time()})
            else:
                pending.append(item)

    def _fire_due_responses() -> None:
        now = time.perf_counter()
        for item in list(pending):
            if item["event_id"] in completed_events or now < float(item["due_monotonic_time"]):
                continue
            backend = _click_widget(window.target_button, f"tactile response {item['trial_uid']}", preferred_backend=backend_requested)
            completed_events.add(int(item["event_id"]))
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
        if not start_clicked["value"] and window.start_button.isEnabled():
            backend = _click_widget(window.start_button, "Start Run", preferred_backend=backend_requested)
            start_clicked["value"] = True
            records.append({"label": "Start Run", "backend": backend, "timestamp_unix": time.time()})
        _continue_instruction_if_needed()
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
    events_csv = package.session_dir / "events.csv"
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
        self.capture_options = capture_options or SessionCaptureOptions()
        self.enable_missed_trial_topup = bool(enable_missed_trial_topup)
        self.controller_factory = controller_factory
        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.controller: SessionRunnerController | None = None
        self.thread: threading.Thread | None = None
        self.result: Any | None = None
        self.exit_code = 1
        self.pending_instruction_request: dict[str, Any] | None = None
        self._pre_run_controls: list[Any] = []
        self._prewarm_thread: threading.Thread | None = None
        self._prewarm_started = False
        self._run_active = False
        self._run_paused = False
        self._timeline_perf_anchor: float | None = None
        self.timeline_state = TactileTimelineState()
        self.recenter_records: list[dict[str, Any]] = []
        self.validation_topup_approval_records: list[dict[str, Any]] = []
        self.planned_tactile_cue_count = 0
        self.recenter_controller = TactileRecenterController(self.timeline_state, self._move_cursor_to_target)

        self.dialog = q["QDialog"]()
        self.dialog.setWindowTitle(f"PPS Experiment Runner - {package.participant_id}")
        self.dialog.setModal(True)
        self.layout_profile = layout_profile or _focus_layout_profile(q)
        self.dialog.resize(self.layout_profile.window_width, self.layout_profile.window_height)
        self.dialog.setMinimumSize(self.layout_profile.min_width, self.layout_profile.min_height)
        self.dialog.setStyleSheet(_focus_style_sheet(q, self.layout_profile))
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
        self.block_chip = _chip(q, f"Block -/{len(self.package.blocks)}", tone="neutral")
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
        root.addWidget(self.workspace_splitter, 1)

        self.run_splitter = q["QSplitter"](q["Qt"].Orientation.Horizontal)
        self.run_splitter.setChildrenCollapsible(False)
        self.run_splitter.setHandleWidth(max(7, profile.root_spacing))
        self.workspace_splitter.addWidget(self.run_splitter)

        response_panel, response_layout = _panel(q, "Experiment Running", profile=profile)
        self.response_panel = response_panel
        response_panel.setMinimumWidth(360 if profile.screen_class == "constrained" else 430)
        response_layout.addWidget(_subtitle(q, "Participant Response"))
        self.target_button = q["QPushButton"]("CLICK")
        self.target_button.setObjectName("targetButton")
        self.target_button.setMinimumHeight(profile.target_min_height)
        self.target_button.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        self.target_button.setEnabled(False)
        self.target_button.clicked.connect(self._click)
        response_layout.addWidget(self.target_button, 1)
        self.instruction_button = q["QPushButton"]("Continue")
        self.instruction_button.setObjectName("primaryButton")
        self.instruction_button.setVisible(False)
        self.instruction_button.clicked.connect(self._continue_instruction_button)
        response_layout.addWidget(self.instruction_button)

        controls = q["QHBoxLayout"]()
        self.start_button = q["QPushButton"]("Start Run")
        self.start_button.setObjectName("primaryButton")
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
        controls.addWidget(self.start_button)
        controls.addWidget(self.pause_button)
        controls.addWidget(self.stop_button)
        controls.addStretch(1)
        controls.addWidget(self.close_button)
        response_layout.addLayout(controls)
        self.run_splitter.addWidget(response_panel)

        self.operator_splitter = None
        self.operator_tabs = None
        if profile.right_stack_mode == "tabs":
            self.operator_tabs = q["QTabWidget"]()
            self.operator_tabs.setDocumentMode(True)
            self.operator_tabs.setMinimumWidth(300)
            self.run_splitter.addWidget(self.operator_tabs)
        else:
            self.operator_splitter = q["QSplitter"](q["Qt"].Orientation.Vertical)
            self.operator_splitter.setChildrenCollapsible(False)
            self.operator_splitter.setHandleWidth(max(7, profile.root_spacing))
            self.operator_splitter.setMinimumWidth(300 if profile.screen_class == "constrained" else 360)
            self.run_splitter.addWidget(self.operator_splitter)

        def _add_operator_panel(title_text: str, panel: Any) -> None:
            if self.operator_tabs is not None:
                self.operator_tabs.addTab(panel, title_text)
            else:
                self.operator_splitter.addWidget(panel)

        data_panel_title = "" if profile.right_stack_mode == "tabs" else "Data Selection"
        data_panel, data_layout = _panel(q, data_panel_title, profile=profile)
        self.data_selection_panel = data_panel
        data_panel_min_height = 178 if profile.screen_class == "constrained" else (260 if profile.compact else 238)
        data_panel.setMinimumHeight(data_panel_min_height)
        data_layout.addWidget(_subtitle(q, "Participant Setup"))
        self.participant_code_input = q["QLineEdit"](self.package.participant_id)
        self.participant_code_input.setPlaceholderText("Participant code")
        self.participant_name_input = q["QLineEdit"]("")
        self.participant_name_input.setPlaceholderText("Participant name")
        self.include_name_lsl_checkbox = q["QCheckBox"]("Include name in LSL/session markers")
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

        def _add_setup_field(row: int, column: int, label: str, widget: Any, *, column_span: int = 1) -> None:
            key = q["QLabel"](label)
            key.setObjectName("metricLabel")
            key.setMinimumHeight(max(16, profile.input_min_height - 8))
            if hasattr(widget, "setMinimumHeight"):
                widget.setMinimumHeight(profile.input_min_height)
            setup_fields.addWidget(key, row, column)
            setup_fields.addWidget(widget, row, column + 1, 1, column_span)

        _add_setup_field(0, 0, "Code", self.participant_code_input)
        _add_setup_field(0, 2, "Age", self.age_input)
        _add_setup_field(1, 0, "Name", self.participant_name_input, column_span=3)
        _add_setup_field(2, 0, "Handedness", self.handedness_combo)
        _add_setup_field(2, 2, "Gender", self.gender_combo)
        setup_fields.setColumnStretch(1, 1)
        setup_fields.setColumnStretch(3, 1)
        data_layout.addLayout(setup_fields)
        data_layout.addWidget(self.include_name_lsl_checkbox)
        self._pre_run_controls.extend(
            [
                self.participant_code_input,
                self.participant_name_input,
                self.include_name_lsl_checkbox,
                self.age_input,
                self.handedness_combo,
                self.gender_combo,
            ]
        )

        data_layout.addWidget(_subtitle(q, "Session"))
        session_grid = q["QGridLayout"]()
        session_grid.setContentsMargins(0, 0, 0, 0)
        session_grid.setHorizontalSpacing(10)
        session_grid.setVerticalSpacing(4)

        def _add_session_metric(row: int, column: int, label: str, value: str, *, column_span: int = 1) -> Any:
            key = q["QLabel"](label)
            key.setObjectName("metricLabel")
            key.setMinimumHeight(max(16, profile.input_min_height - 8))
            val = q["QLabel"](value)
            val.setObjectName("metricValue")
            val.setWordWrap(True)
            val.setMinimumHeight(max(16, profile.input_min_height - 8))
            session_grid.addWidget(key, row, column)
            session_grid.addWidget(val, row, column + 1, 1, column_span)
            return val

        _add_session_metric(0, 0, "Participant", self.package.participant_id)
        _add_session_metric(0, 2, "Blocks", str(len(self.package.blocks)))
        instruction_summary = _instruction_profile_summary(self.package)
        if profile.compact:
            instruction_summary = instruction_summary.replace(" clip(s) preloaded", " clips")
        _add_session_metric(1, 0, "Duration", _format_duration(_package_duration(self.package)))
        _add_session_metric(1, 2, "Instruction clips", instruction_summary)
        session_value = _add_session_metric(2, 0, "Session", self.package.session_id, column_span=3)
        session_value.setToolTip(f"Session: {self.package.session_id}\nFolder: {self.package.session_dir}")
        if not profile.compact:
            folder_value = _add_session_metric(3, 0, "Folder", _short_folder_label(self.package.session_dir), column_span=3)
            folder_value.setToolTip(str(self.package.session_dir))
        session_grid.setColumnStretch(1, 1)
        session_grid.setColumnStretch(3, 1)
        data_layout.addLayout(session_grid)
        data_layout.addStretch(1)
        _add_operator_panel("Data Selection", data_panel)

        settings_panel_title = "" if profile.right_stack_mode == "tabs" else "Settings"
        settings_panel, settings_layout = _panel(q, settings_panel_title, profile=profile)
        self.settings_panel = settings_panel
        settings_panel_min_height = 128 if profile.screen_class == "constrained" else (190 if profile.compact else 184)
        settings_panel.setMinimumHeight(settings_panel_min_height)
        settings_layout.addWidget(_subtitle(q, "Recording"))
        chip_grid = q["QGridLayout"]()
        chip_grid.setContentsMargins(0, 0, 0, 0)
        chip_grid.setHorizontalSpacing(6)
        chip_grid.setVerticalSpacing(6)
        recording_chips = [("events.csv on", True)]
        recording_chips.extend(
            [
                (label if enabled else f"{label} off", bool(enabled))
                for label, enabled in (
                    ("LSL/event protocol", self.capture_options.enable_lsl),
                    ("local marker mirror", self.capture_options.write_lsl_marker_mirror),
                    ("trigger dictionary", self.capture_options.write_trigger_dictionary),
                    ("events.xdf", self.capture_options.write_internal_xdf),
                    ("analysis CSVs", self.capture_options.write_analysis_csvs),
                )
            ]
        )
        columns = max(1, int(profile.recording_chip_columns))
        for index, (label, enabled) in enumerate(recording_chips):
            chip = _chip(q, label, tone="ok" if enabled else "off")
            chip_grid.addWidget(chip, index // columns, index % columns)
        settings_layout.addLayout(chip_grid)
        self.backup_recording_checkbox = q["QCheckBox"]("Backup WAV (Belts and Suspenders)")
        self.backup_recording_checkbox.setToolTip("Belts and Suspenders: save local full-audio backup WAV")
        self.backup_recording_checkbox.setChecked(bool(self.capture_options.start_backup_recording))
        self.topup_checkbox = q["QCheckBox"]("Top up missed tactile trials at part end")
        self.topup_checkbox.setToolTip("Top up missed tactile trials at end of each part")
        self.topup_checkbox.setChecked(bool(self.enable_missed_trial_topup))
        settings_layout.addWidget(self.backup_recording_checkbox)
        settings_layout.addWidget(self.topup_checkbox)
        settings_layout.addStretch(1)
        self._pre_run_controls.extend([self.backup_recording_checkbox, self.topup_checkbox])
        _add_operator_panel("Settings", settings_panel)

        processing_panel, processing_layout = _panel(q, "Data Processing", profile=profile)
        self.processing_panel = processing_panel
        processing_panel.setMinimumHeight(210 if profile.screen_class == "constrained" else 220)
        self.processing_splitter = q["QSplitter"](q["Qt"].Orientation.Horizontal)
        self.processing_splitter.setChildrenCollapsible(False)
        self.processing_splitter.setHandleWidth(max(7, profile.root_spacing))

        progress_widget = q["QWidget"]()
        progress_layout = q["QVBoxLayout"](progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(profile.panel_spacing)
        progress_layout.addWidget(_subtitle(q, "Live Tactile Timeline"))
        timeline_status = q["QWidget"]()
        timeline_status_layout = q["QHBoxLayout"](timeline_status)
        timeline_status_layout.setContentsMargins(0, 0, 0, 0)
        timeline_status_layout.setSpacing(8)
        self.next_tactile_label = q["QLabel"]("Next tactile: no block schedule")
        self.next_tactile_label.setObjectName("metricValue")
        self.next_tactile_label.setWordWrap(True)
        self.tactile_count_label = q["QLabel"]("0 / 0 cues")
        self.tactile_count_label.setObjectName("mutedLabel")
        timeline_status_layout.addWidget(self.next_tactile_label, 1)
        timeline_status_layout.addWidget(self.tactile_count_label)
        progress_layout.addWidget(timeline_status)
        self.tactile_timeline_widget = _create_tactile_timeline_widget(q, self.timeline_state)
        progress_layout.addWidget(self.tactile_timeline_widget)
        self.recenter_status_label = q["QLabel"]("Cursor recenter: waiting")
        self.recenter_status_label.setObjectName("mutedLabel")
        self.recenter_status_label.setWordWrap(True)
        progress_layout.addWidget(self.recenter_status_label)
        progress_layout.addWidget(_subtitle(q, "Progress"))
        self.progress_label = q["QLabel"]("Waiting to start")
        self.progress_label.setObjectName("metricValue")
        self.progress_label.setWordWrap(True)
        progress_layout.addWidget(self.progress_label)
        self.progress = q["QProgressBar"]()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        progress_layout.addWidget(self.progress)
        self.event_label = q["QLabel"]("Event stream idle")
        self.event_label.setObjectName("mutedLabel")
        self.event_label.setWordWrap(True)
        progress_layout.addWidget(self.event_label)
        self.prewarm_label = q["QLabel"]("Next participant: idle")
        self.prewarm_label.setObjectName("mutedLabel")
        self.prewarm_label.setWordWrap(True)
        progress_layout.addWidget(self.prewarm_label)
        progress_layout.addStretch(1)
        self.processing_splitter.addWidget(progress_widget)

        output_widget = q["QWidget"]()
        output_layout = q["QVBoxLayout"](output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(profile.panel_spacing)
        output_layout.addWidget(_subtitle(q, "Output Summary"))
        self.output_summary = q["QTextEdit"]()
        self.output_summary.setReadOnly(True)
        self.output_summary.setMinimumHeight(profile.output_min_height)
        self.output_summary.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        self.output_summary.setPlainText("Session outputs will appear here after the run.")
        output_layout.addWidget(self.output_summary)
        self.processing_splitter.addWidget(output_widget)
        processing_layout.addWidget(self.processing_splitter, 1)
        self.workspace_splitter.addWidget(processing_panel)

        self.run_splitter.setSizes([max(520, int(profile.window_width * 0.62)), max(340, int(profile.window_width * 0.38))])
        if self.operator_splitter is not None:
            self.operator_splitter.setSizes([max(210, int(profile.window_height * 0.45)), max(150, int(profile.window_height * 0.28))])
        self.workspace_splitter.setSizes([max(300, int(profile.window_height * 0.58)), max(210, int(profile.window_height * 0.34))])
        self.processing_splitter.setSizes([max(260, int(profile.window_width * 0.28)), max(520, int(profile.window_width * 0.72))])

        self.timer = q["QTimer"](self.dialog)
        self.timer.timeout.connect(self._drain)
        self.timer.start(100)
        self.dialog.finished.connect(lambda _code: self._stop())

    def _runtime_capture_options(self) -> SessionCaptureOptions:
        return SessionCaptureOptions(
            enable_lsl=bool(self.capture_options.enable_lsl),
            write_events_csv=True,
            write_internal_xdf=bool(self.capture_options.write_internal_xdf),
            write_analysis_csvs=bool(self.capture_options.write_analysis_csvs),
            write_lsl_marker_mirror=True,
            write_trigger_dictionary=True,
            start_backup_recording=bool(self.backup_recording_checkbox.isChecked()),
        )

    def _runner_metadata(self) -> dict[str, Any]:
        return {
            "participant_code": self.participant_code_input.text().strip() or self.package.participant_id,
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
                    session_root=DEFAULT_SESSION_ROOT,
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

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return
        self.capture_options = self._runtime_capture_options()
        self.enable_missed_trial_topup = bool(self.topup_checkbox.isChecked())
        runner_metadata = self._runner_metadata()
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
                capture_options=self.capture_options,
                enable_topup=self.enable_missed_trial_topup,
                runner_metadata=runner_metadata,
                topup_approval_callback=self._request_topup_approval if self.enable_missed_trial_topup else None,
                instruction_continue_callback=self._request_instruction_continue,
            )
        self.start_button.setEnabled(False)
        self._freeze_pre_run_controls()
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
            context = dict(self.pending_instruction_request.get("context") or {})
            if context.get("mode") == "click":
                self.pending_instruction_request["approved"] = True
                self.pending_instruction_request["event"].set()
                self.pending_instruction_request = None
                self.instruction_button.setVisible(False)
                self.target_button.setEnabled(True)
                self.event_label.setText("Instruction continuation logged")
                return
        if self.controller is None:
            self.event_label.setText("Start the run before logging responses.")
            return
        self.controller.log_click(in_target=True)
        self.event_label.setText("Participant click logged")

    def _continue_instruction_button(self) -> None:
        if self.pending_instruction_request is None:
            return
        self.pending_instruction_request["approved"] = True
        self.pending_instruction_request["event"].set()
        self.pending_instruction_request = None
        self.instruction_button.setVisible(False)
        self.target_button.setEnabled(True)
        self.event_label.setText("Instruction continuation logged")

    def _toggle_pause(self) -> None:
        if self.controller is None:
            return
        if self.pause_button.text() == "Pause":
            self.controller.pause()
            self.pause_button.setText("Resume")
            self._run_paused = True
            self.run_state_chip.setText("Paused")
            self.progress_label.setText("Paused")
        else:
            self.controller.resume()
            self.pause_button.setText("Pause")
            self._run_paused = False
            self.run_state_chip.setText("Running")

    def _stop(self) -> None:
        self._run_active = False
        if self.controller is not None:
            self.controller.stop()
        if hasattr(self, "progress_label"):
            self.progress_label.setText("Stopping" if self.thread and self.thread.is_alive() else self.progress_label.text())

    def _close(self) -> None:
        self._stop()
        self.dialog.accept()

    def _handle_block_schedule(self, payload: dict[str, Any]) -> None:
        self.timeline_state.load_block(
            part_number=payload.get("part_number", ""),
            phase_label=payload.get("phase_label", payload.get("phase", "")),
            block_index=payload.get("block_index", ""),
            block_label=payload.get("block_label", ""),
            duration_s=payload.get("duration_s", 0.0),
            tactile_events=list(payload.get("tactile_events") or []),
        )
        self.planned_tactile_cue_count += len(self.timeline_state.cues)
        anchor = _float_or_none(payload.get("block_schedule_perf_counter"))
        self._timeline_perf_anchor = anchor if anchor is not None else time.perf_counter()
        part_text = str(payload.get("part_number") or "").strip()
        self.part_chip.setText(f"Part {part_text}" if part_text else "Part -")
        block_index = str(payload.get("block_index") or "").strip()
        block_count = int(payload.get("block_count") or len(self.package.blocks) or 0)
        if bool(payload.get("is_topup")):
            self.block_chip.setText(f"Top-up {block_index}" if block_index else "Top-up")
        else:
            self.block_chip.setText(f"Block {block_index}/{block_count}" if block_index else f"Block -/{block_count}")
        self.recenter_status_label.setText("Cursor recenter: waiting for next tactile cue")
        self._update_tactile_timeline_display()

    def _update_tactile_progress(self, elapsed_s: float) -> None:
        moved = self.recenter_controller.tick(
            elapsed_s,
            active=self._run_active and self.timeline_state.active,
            paused=self._run_paused,
            instruction_waiting=self.pending_instruction_request is not None,
        )
        if moved:
            last = moved[-1]
            self.recenter_status_label.setText(
                f"Cursor recenter: Trial {last.trial_number} at {last.time_s:.1f}s"
            )
        self._update_tactile_timeline_display(preserve_recenter_message=bool(moved))

    def _update_tactile_timeline_display(self, *, preserve_recenter_message: bool = False) -> None:
        total = len(self.timeline_state.cues)
        if total <= 0:
            text = "Next tactile: no cues in this block" if self.timeline_state.active else "Next tactile: no block schedule"
            self.next_tactile_label.setText(text)
            self.tactile_count_label.setText("0 / 0 cues")
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
        self.tactile_count_label.setText(f"{self.timeline_state.passed_count()} / {total} cues")
        if not preserve_recenter_message:
            self.recenter_status_label.setText(
                f"Cursor recenter: {self.timeline_state.recentered_count()} / {total} cues"
            )
        self.tactile_timeline_widget.update()

    def _move_cursor_to_target(self, cue: TactileTimelineCue) -> None:
        center = self.target_button.mapToGlobal(self.target_button.rect().center())
        offscreen = self._offscreen_platform()
        self.recenter_records.append(
            {
                "cue_id": cue.cue_id,
                "trial_number": cue.trial_number,
                "trial_uid": cue.trial_uid,
                "time_s": cue.time_s,
                "elapsed_s": self.timeline_state.elapsed_s,
                "mode": "recorded_intent" if offscreen else "os_cursor",
                "x": int(center.x()),
                "y": int(center.y()),
            }
        )
        if not offscreen:
            self.q["QCursor"].setPos(center)

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
        if self._timeline_perf_anchor is None or not self._run_active or not self.timeline_state.active:
            return
        elapsed = max(0.0, time.perf_counter() - self._timeline_perf_anchor)
        if self.timeline_state.duration_s > 0:
            elapsed = min(elapsed, self.timeline_state.duration_s)
        if elapsed < self.timeline_state.elapsed_s:
            elapsed = self.timeline_state.elapsed_s
        self._update_tactile_progress(elapsed)

    def _drain(self) -> None:
        while not self.messages.empty():
            kind, payload = self.messages.get_nowait()
            if kind == "progress":
                if dict(payload).get("ui_event") == "block_schedule":
                    self._handle_block_schedule(dict(payload))
                    continue
                duration = float(payload.get("duration_s") or 0.0)
                elapsed = float(payload.get("elapsed_s") or 0.0)
                value = int(max(0.0, min(1.0, elapsed / duration)) * 1000) if duration > 0 else 0
                self.progress.setValue(value)
                self.progress_label.setText(
                    f"Block {payload.get('block_index')}: {payload.get('block_label')}  "
                    f"{elapsed:.1f}/{duration:.1f}s"
                )
                part_number = str(payload.get("part_number") or "").strip()
                if part_number:
                    self.part_chip.setText(f"Part {part_number}")
                block_count = int(payload.get("block_count") or len(self.package.blocks) or 0)
                if bool(payload.get("is_topup")):
                    self.block_chip.setText(f"Top-up {payload.get('block_index')}")
                else:
                    self.block_chip.setText(f"Block {payload.get('block_index')}/{block_count}")
                self._update_tactile_progress(elapsed)
            elif kind == "event":
                self.event_label.setText(str(payload))
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

    def _handle_instruction_continue(self, payload: dict[str, Any]) -> None:
        context = dict(payload.get("context") or {})
        self.pending_instruction_request = payload
        mode = str(context.get("mode") or "click")
        label = str(context.get("instruction_label") or "instruction")
        if mode == "button":
            self.target_button.setEnabled(False)
            self.instruction_button.setText(str(context.get("button_label") or "Continue"))
            self.instruction_button.setVisible(True)
            self.event_label.setText(f"Use the runner button to continue after {label}.")
        else:
            self.target_button.setEnabled(True)
            self.instruction_button.setVisible(False)
            self.event_label.setText(f"Click the target to continue after {label}.")

    def _handle_topup_approval(self, payload: dict[str, Any]) -> None:
        q = self.q
        summary = dict(payload.get("summary") or {})
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
        payload["event"].set()

    def _handle_done(self, result: Any) -> None:
        self.result = result
        self.exit_code = 0 if result.completed else 2
        self._run_active = False
        self._run_paused = False
        self.timeline_state.active = False
        self.target_button.setEnabled(False)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.start_button.setEnabled(False)
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
        self.timer.stop()

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

    dialog = q["QDialog"]()
    dialog.setWindowTitle("PPS Experiment Runner")
    dialog.resize(900, 620)
    dialog.setMinimumSize(760, 520)
    dialog.setStyleSheet(_focus_style_sheet(q, DEFAULT_FOCUS_LAYOUT_PROFILE))
    apply_qt_app_icon(q, app=app, window=dialog)

    selected_manifest: dict[str, Path | None] = {"path": None}
    layout = q["QVBoxLayout"](dialog)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(14)
    panel, panel_layout = _panel(q, "Open Experiment Runner")
    heading = q["QLabel"]("Resume the last dashboard experiment, choose a prepared participant session, or run a finished study/profile preset.")
    heading.setObjectName("mutedLabel")
    heading.setWordWrap(True)
    panel_layout.addWidget(heading)
    participant = q["QLineEdit"](participant_id or "P001")
    participant.setPlaceholderText("Participant ID")
    panel_layout.addWidget(participant)
    message = q["QLabel"](initial_message or "Ready")
    message.setObjectName("mutedLabel")
    message.setWordWrap(True)
    panel_layout.addWidget(message)
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

    profile_options = finished_profile_options()
    profile_combo = _combo(q, profile_options, current="study5_box_breathing_pps")
    profile_combo.setEnabled(bool(profile_options))
    panel_layout.addWidget(_field_row(q, "Study/profile preset", profile_combo))

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

    def _set_busy(busy: bool) -> None:
        latest_button.setEnabled(not busy)
        profile_button.setEnabled((not busy) and bool(profile_options))
        choose_button.setEnabled(not busy)
        close_button.setEnabled(not busy)
        profile_combo.setEnabled((not busy) and bool(profile_options))
        participant.setEnabled(not busy)
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

    def _start_preparation(label: str, prepare: Callable[[Callable[[dict[str, Any]], None]], Path]) -> None:
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
                manifest_path = prepare(_progress_callback)
            except Exception as exc:
                preparation_messages.put(("error", str(exc)))
            else:
                preparation_messages.put(("done", manifest_path))

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
                dialog.accept()
            elif kind == "error":
                message.setText(str(payload))
                detail_message.setText("")
                _set_busy(False)

    preparation_timer = q["QTimer"](dialog)
    preparation_timer.timeout.connect(_drain_preparation_messages)
    preparation_timer.start(100)

    def _open_latest() -> None:
        _start_preparation(
            "Loading last experiment",
            lambda progress_callback: prepare_last_or_latest_focus_session(
                participant.text().strip(),
                progress_callback=progress_callback,
            ),
        )

    def _open_profile() -> None:
        _start_preparation(
            "Loading selected profile",
            lambda progress_callback: prepare_profile_focus_session(
                str(profile_combo.currentData() or ""),
                participant.text().strip(),
                progress_callback=progress_callback,
            ),
        )

    def _choose_manifest() -> None:
        filename, _selected_filter = q["QFileDialog"].getOpenFileName(
            dialog,
            "Choose Session Manifest",
            str(DEFAULT_SESSION_ROOT),
            "PPS session_manifest.json (session_manifest.json);;JSON files (*.json);;All files (*)",
        )
        if filename:
            selected_manifest["path"] = Path(filename)
            dialog.accept()

    latest_button.clicked.connect(_open_latest)
    profile_button.clicked.connect(_open_profile)
    choose_button.clicked.connect(_choose_manifest)
    cancel_button.clicked.connect(lambda: (preparation_cancel.set(), cancel_button.setEnabled(False), message.setText("Cancelling loading...")))
    close_button.clicked.connect(dialog.reject)
    validation_launcher_clicks: list[dict[str, Any]] = []

    def _validation_click_launcher_profile() -> None:
        from PySide6.QtTest import QTest

        target = os.environ.get("PPS_FOCUS_VALIDATION_PROFILE", "study5_box_breathing_pps").strip()
        if target:
            index = profile_combo.findData(target)
            if index >= 0:
                profile_combo.setCurrentIndex(index)
        if profile_combo.isEnabled():
            QTest.mouseClick(profile_combo, q["Qt"].MouseButton.LeftButton)
            validation_launcher_clicks.append(
                {
                    "label": "click Study/profile preset selector",
                    "timestamp_unix": time.time(),
                    "selected_profile": str(profile_combo.currentData() or ""),
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
        manual_start=True,
        auto_close_ms=args.validation_auto_close_ms,
        screenshot_path=args.validation_screenshot,
    )


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
