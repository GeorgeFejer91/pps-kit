"""Qt stimulus designer with an embedded 3D trajectory viewer."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import render_backend
from .app_assets import apply_qt_app_icon, set_windows_app_user_model_id
from .focus_launch import build_focus_runner_command, resolve_packaged_focus_runner
from .runtime_paths import designer_frontend_root, resource_root, writable_root
from .subprocess_utils import windows_no_console_kwargs
from .design import (
    DEFAULT_SOFA_FILE,
    DEFAULT_TRAJECTORY_PLANE_HEIGHT_M,
    DEFAULT_TRAJECTORY_PLANE_LABEL,
    DISPLAY_ROTATION_DEG_MAX,
    DISPLAY_ROTATION_DEG_MIN,
    DISTANCE_CM_MAX,
    DISTANCE_CM_MIN,
    PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
    ROTATION_DEG_MAX,
    ROTATION_DEG_MIN,
    AudioFileSpec,
    BlockSpec,
    NoiseDefinition,
    ProtocolSpec,
    SUPPORTED_TRIAL_TYPES,
    StimulusDesign,
    TrajectorySpec,
    cartesian_to_spherical,
    azimuth_to_display_rotation_deg,
    default_design,
    effective_block_specs,
    export_protocol_csv,
    export_trajectory_csv,
    block_trial_rows,
    gold_standard_looming_source_parameters,
    load_design,
    participant_block_orders,
    point_from_distance_rotation_height,
    protocol_summary,
    save_design,
    trajectory_endpoints_xyz,
    validate_design,
)
from .templates import (
    StudyTemplate,
    load_templates,
    study_template_bibtex,
    study_template_citation_label,
    study_template_csl_json,
)
from .session_runner import (
    DEFAULT_RENDER_DIR,
    DEFAULT_SESSION_ROOT,
    RunPackage,
    prepare_run_package,
    preflight_run_package,
    rendered_wavs,
)


RESOURCE_ROOT = resource_root()
WRITABLE_ROOT = writable_root()
REPO_ROOT = WRITABLE_ROOT
DEFAULT_DESIGN_PATH = WRITABLE_ROOT / "configs" / "stimulus_design.generated.json"
TEMPLATE_DIR = RESOURCE_ROOT / "study_templates"
DEFAULT_RUNNER_STIMULI_DIR = WRITABLE_ROOT / "artifacts" / "stimuli" / "10.Participant_Sequences"
DEFAULT_RUNNER_INSTRUCTIONS_DIR = RESOURCE_ROOT / "assets" / "breathing"
DEFAULT_RUNNER_SETTINGS_FILE = WRITABLE_ROOT / "local_data" / "experiment_settings.json"
DEFAULT_RUNNER_DEMOGRAPHICS_DIR = WRITABLE_ROOT / "local_data" / "demographics"
DEFAULT_RUNNER_RECORDINGS_DIR = WRITABLE_ROOT / "local_data" / "loopback_recordings"
TRIAL_PREVIEW_LIMIT = 300
LAYOUT_SETTINGS_ORG = "PPS Toolkit"
LAYOUT_SETTINGS_APP = "Qt Designer Modern v4"
SPLITTER_DEFAULT_SIZES: dict[str, tuple[int, ...]] = {
    "stimulus/main": (520, 740),
    "stimulus/left": (320, 380),
    "stimulus/right": (300, 590),
    "trial/main": (430, 670),
    "trial/left": (335, 170, 205),
    "trial/right": (180, 420, 220),
    "runner/main": (430, 670),
    "runner/right": (420, 260),
}
APP_STYLE_SHEET = """
QWidget {
    background: #f3f5f2;
    color: #1f2722;
    font-family: "Aptos", "Noto Sans", sans-serif;
    font-size: 10pt;
}
QLabel {
    background: transparent;
}
QWidget#fieldCell {
    background: transparent;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QTableWidget {
    background: #ffffff;
    border: 1px solid #cdd7d1;
    border-radius: 8px;
    padding: 6px 9px;
    selection-background-color: #d6ebff;
    selection-color: #14221d;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QTableWidget:focus {
    border-color: #2f8b7d;
}
QComboBox {
    min-height: 26px;
}
QComboBox::drop-down {
    border: 0;
    width: 26px;
}
QSpinBox, QDoubleSpinBox {
    min-height: 26px;
}
QTextEdit, QTableWidget {
    border-radius: 8px;
}
QTableWidget {
    gridline-color: #e7eee9;
    alternate-background-color: #f7faf8;
    selection-background-color: #dcefe9;
    selection-color: #18231f;
}
QHeaderView::section {
    background: #e8f0ec;
    color: #2f4038;
    border: 0;
    border-bottom: 1px solid #cddad3;
    padding: 7px 9px;
    font-weight: 600;
}
QTableCornerButton::section {
    background: #e8f0ec;
    border: 0;
    border-bottom: 1px solid #cddad3;
}
QGroupBox {
    background: #fbfcfb;
    border: 1px solid #d2ddd7;
    border-top: 3px solid #8aa89d;
    border-radius: 9px;
    margin-top: 0;
    padding: 30px 13px 13px 13px;
    font-weight: 500;
}
QGroupBox::title {
    subcontrol-origin: padding;
    subcontrol-position: top left;
    top: 9px;
    left: 14px;
    padding: 0;
    color: #26352e;
    font-size: 10.5pt;
    font-weight: 700;
}
QGroupBox#noisePanel {
    background: #f0fbf7;
    border-color: #6fc4ad;
}
QGroupBox#noisePanel::title {
    color: #176b57;
}
QGroupBox#audioPanel {
    background: #f7f3ff;
    border-color: #b9a1e9;
}
QGroupBox#audioPanel::title {
    color: #5d3f9a;
}
QGroupBox#trajectoryStartPanel {
    background: #f0f7ff;
    border-color: #8dbbe7;
}
QGroupBox#trajectoryStartPanel::title {
    color: #2a6299;
}
QGroupBox#trajectoryEndPanel {
    background: #fff6e9;
    border-color: #e7ae5e;
}
QGroupBox#trajectoryEndPanel::title {
    color: #8a551c;
}
QGroupBox#timingPanel {
    background: #f2faec;
    border-color: #9fcd75;
}
QGroupBox#timingPanel::title {
    color: #4f7c2d;
}
QGroupBox#viewerPanel {
    background: #f0f8fb;
    border-color: #82bfd5;
}
QGroupBox#viewerPanel::title {
    color: #2a657b;
}
QGroupBox#conditionsPanel {
    background: #fff8e7;
    border-color: #d9b24d;
}
QGroupBox#conditionsPanel::title {
    color: #7a5a11;
}
QGroupBox#familiesPanel {
    background: #fff1f3;
    border-color: #df98a2;
}
QGroupBox#familiesPanel::title {
    color: #8a3d48;
}
QGroupBox#blocksPanel {
    background: #f6f2ff;
    border-color: #ac98df;
}
QGroupBox#blocksPanel::title {
    color: #563d8e;
}
QGroupBox#summaryPanel {
    background: #effaf3;
    border-color: #80c496;
}
QGroupBox#summaryPanel::title {
    color: #28683a;
}
QGroupBox#trialPreviewPanel {
    background: #f0f7ff;
    border-color: #8bb8e3;
}
QGroupBox#trialPreviewPanel::title {
    color: #2e5f90;
}
QGroupBox#ordersPanel {
    background: #f7f3ff;
    border-color: #bba4e8;
}
QGroupBox#ordersPanel::title {
    color: #5a3e8a;
}
QGroupBox#preparePanel {
    background: #fff7e8;
    border-color: #e1b260;
}
QGroupBox#preparePanel::title {
    color: #7d5519;
}
QGroupBox#readinessPanel {
    background: #f0fbf7;
    border-color: #6fc4ad;
}
QGroupBox#readinessPanel::title {
    color: #176b57;
}
QGroupBox#reviewPanel {
    background: #f0f7ff;
    border-color: #8fb9e5;
}
QGroupBox#reviewPanel::title {
    color: #305f91;
}
QTabWidget::pane {
    border: 1px solid #d3ddd8;
    border-radius: 9px;
    top: -1px;
    background: #f8faf8;
}
QTabBar::tab {
    background: #e8efeb;
    border: 1px solid #d3ddd8;
    border-bottom: 0;
    padding: 9px 16px;
    margin-right: 3px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}
QTabBar::tab:selected {
    background: #fbfcfb;
    color: #0f6f60;
    font-weight: 600;
}
QTabBar::tab:hover {
    background: #f1f6f3;
}
QPushButton {
    background: #ffffff;
    border: 1px solid #c8d4ce;
    border-radius: 8px;
    padding: 8px 13px;
    color: #1e2c25;
}
QPushButton:hover {
    background: #edf6f2;
    border-color: #7bb2a3;
}
QPushButton:pressed {
    background: #dceee8;
}
QPushButton:disabled {
    background: #eef2f0;
    color: #8a9992;
    border-color: #d8e0dc;
}
QPushButton#primaryButton {
    background: #126e60;
    color: #ffffff;
    border-color: #126e60;
    font-weight: 600;
}
QPushButton#primaryButton:hover {
    background: #0d5a4f;
}
QPushButton#primaryButton:disabled {
    background: #b9c9c3;
    color: #f3f7f5;
    border-color: #b9c9c3;
}
QPushButton#subtleButton {
    background: transparent;
    border-color: transparent;
    color: #4e625a;
}
QPushButton#citationButton {
    background: #f3edff;
    border-color: #a98bdc;
    color: #4b2f78;
    font-weight: 600;
}
QPushButton#citationButton:hover {
    background: #eee5ff;
    border-color: #9f82d4;
}
QFrame#profileCard {
    background: #fffaf0;
    border: 1px solid #dcc48d;
    border-left: 5px solid #b47b16;
    border-radius: 9px;
}
QFrame#topBar, QFrame#footerBar {
    background: #ffffff;
    border: 1px solid #d3ddd8;
    border-radius: 9px;
}
QLabel#profileSummary {
    background: transparent;
    color: #4f4431;
    padding: 7px 8px;
}
QLabel#statusPill {
    background: #eaf5f1;
    color: #245548;
    border: 1px solid #cce3dc;
    border-radius: 10px;
    padding: 5px 10px;
}
QSplitter::handle {
    background: #d7e1dc;
}
QSplitter::handle:horizontal {
    width: 7px;
    margin: 1px 2px;
}
QSplitter::handle:vertical {
    height: 7px;
    margin: 2px 1px;
}
QSplitter::handle:hover {
    background: #8fb9ad;
}
QScrollBar:vertical {
    background: transparent;
    width: 12px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #b8c7c0;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover {
    background: #8fa89f;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background: transparent;
    height: 12px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #b8c7c0;
    border-radius: 5px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover {
    background: #8fa89f;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}
QMenu {
    background: #ffffff;
    border: 1px solid #cbd7d1;
    border-radius: 8px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 24px 7px 12px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: #edf6f2;
    color: #123a31;
}
"""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch the PPS stimulus designer.")
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN_PATH, help="Design JSON to open or create.")
    return parser


def _require_qt():
    try:
        from PySide6.QtCore import QSettings, QTimer, QUrl, Qt
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import (
            QAbstractItemView,
            QAbstractSpinBox,
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDoubleSpinBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMenu,
            QMessageBox,
            QProgressBar,
            QPushButton,
            QSpinBox,
            QSplitter,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError as exc:
        raise RuntimeError("Install the GUI dependencies with: pip install -e .[gui]") from exc

    return {
        "QApplication": QApplication,
        "QAbstractItemView": QAbstractItemView,
        "QAbstractSpinBox": QAbstractSpinBox,
        "QCheckBox": QCheckBox,
        "QComboBox": QComboBox,
        "QDialog": QDialog,
        "QDoubleSpinBox": QDoubleSpinBox,
        "QFileDialog": QFileDialog,
        "QFormLayout": QFormLayout,
        "QFrame": QFrame,
        "QGridLayout": QGridLayout,
        "QGroupBox": QGroupBox,
        "QHBoxLayout": QHBoxLayout,
        "QHeaderView": QHeaderView,
        "QIcon": QIcon,
        "QLabel": QLabel,
        "QLineEdit": QLineEdit,
        "QMainWindow": QMainWindow,
        "QMenu": QMenu,
        "QMessageBox": QMessageBox,
        "QProgressBar": QProgressBar,
        "QPushButton": QPushButton,
        "QSettings": QSettings,
        "QTimer": QTimer,
        "QSpinBox": QSpinBox,
        "QSplitter": QSplitter,
        "QTabWidget": QTabWidget,
        "QTableWidget": QTableWidget,
        "QTableWidgetItem": QTableWidgetItem,
        "QTextEdit": QTextEdit,
        "QUrl": QUrl,
        "Qt": Qt,
        "QVBoxLayout": QVBoxLayout,
        "QWebEngineView": QWebEngineView,
        "QWidget": QWidget,
    }


def _as_cm_and_rotation(point: dict[str, float]) -> tuple[float, float]:
    spherical = cartesian_to_spherical(point["x_m"], point["y_m"], point["z_m"])
    return spherical["radius_m"] * 100.0, azimuth_to_display_rotation_deg(spherical["azimuth_deg"])


def _height_cm(point: dict[str, float]) -> float:
    return point["z_m"] * 100.0


def trajectory_viewer_payload(
    design: StimulusDesign,
    display_radius_m: float | None = None,
    preview_mode: str = "2d",
) -> dict[str, Any]:
    start, end = trajectory_endpoints_xyz(design.trajectory)
    normalized_mode = "2d" if str(preview_mode).lower().startswith("2") else "3d"
    if normalized_mode == "2d":
        start = {**start, "z_m": 0.0}
        end = {**end, "z_m": 0.0}
    radius = display_radius_m or max(
        0.1,
        design.trajectory.start_radius_m,
        design.trajectory.end_radius_m,
        math.sqrt(start["x_m"] ** 2 + start["y_m"] ** 2 + start["z_m"] ** 2),
        math.sqrt(end["x_m"] ** 2 + end["y_m"] ** 2 + end["z_m"] ** 2),
    )
    return {
        "radius_m": radius,
        "path_length_m": design.trajectory.path_length_m,
        "movement_duration_s": design.trajectory.movement_duration_s,
        "speed_mps": design.trajectory.propagation_speed_mps,
        "preview_mode": normalized_mode,
        "height_visible": normalized_mode == "3d",
        "trajectory_plane": {
            "height_m": DEFAULT_TRAJECTORY_PLANE_HEIGHT_M,
            "label": DEFAULT_TRAJECTORY_PLANE_LABEL,
            "locked_in_2d": normalized_mode == "2d",
        },
        "start": start,
        "end": end,
        "labels": {
            "start": "Starting Point",
            "end": "End Point",
            "distance_unit": "cm",
            "rotation_unit": "deg",
        },
        "study_profile": {
            "id": design.study_profile_id,
            "title": design.study_profile_title,
        },
    }


def create_design_from_endpoint_controls(
    base_design: StimulusDesign,
    *,
    start_distance_cm: float,
    start_rotation_deg: float,
    end_distance_cm: float,
    end_rotation_deg: float,
    movement_duration_s: float,
    lead_padding_s: float,
    tail_padding_s: float,
    start_height_cm: float = DEFAULT_TRAJECTORY_PLANE_HEIGHT_M * 100.0,
    end_height_cm: float = DEFAULT_TRAJECTORY_PLANE_HEIGHT_M * 100.0,
) -> StimulusDesign:
    start = point_from_distance_rotation_height(start_distance_cm, start_rotation_deg, start_height_cm)
    end = point_from_distance_rotation_height(end_distance_cm, end_rotation_deg, end_height_cm)
    path_length = math.dist(
        (start["x_m"], start["y_m"], start["z_m"]),
        (end["x_m"], end["y_m"], end["z_m"]),
    )
    if path_length <= 0:
        raise ValueError("Starting Point and End Point cannot be identical.")
    if movement_duration_s <= 0:
        raise ValueError("Movement duration must be positive.")

    start_spherical = cartesian_to_spherical(start["x_m"], start["y_m"], start["z_m"])
    end_spherical = cartesian_to_spherical(end["x_m"], end["y_m"], end["z_m"])
    trajectory = TrajectorySpec(
        start_radius_m=start_spherical["radius_m"],
        end_radius_m=end_spherical["radius_m"],
        path_direction="custom",
        coordinate_mode="cartesian",
        start_x_m=start["x_m"],
        start_y_m=start["y_m"],
        start_z_m=start["z_m"],
        end_x_m=end["x_m"],
        end_y_m=end["y_m"],
        end_z_m=end["z_m"],
        path_length_m=path_length,
        propagation_speed_mps=path_length / movement_duration_s,
        azimuth_start_deg=start_spherical["azimuth_deg"],
        azimuth_end_deg=end_spherical["azimuth_deg"],
        elevation_deg=0.0,
        padding_pre_s=lead_padding_s,
        padding_post_s=tail_padding_s,
    )
    return StimulusDesign(
        name=base_design.name,
        study_profile_id=base_design.study_profile_id,
        study_profile_title=base_design.study_profile_title,
        study_profile_notes=base_design.study_profile_notes,
        study_profile_reference_parameters=dict(base_design.study_profile_reference_parameters),
        sofa_file=base_design.sofa_file or DEFAULT_SOFA_FILE,
        noises=list(base_design.noises),
        custom_looming_files=list(base_design.custom_looming_files),
        prestimulus_files=list(base_design.prestimulus_files),
        trajectory=trajectory,
        protocol=base_design.protocol,
    )


def trial_assembler_preview_rows(design: StimulusDesign, limit: int = TRIAL_PREVIEW_LIMIT) -> list[dict[str, Any]]:
    rows = block_trial_rows(design)
    preview: list[dict[str, Any]] = []
    for row in rows[: max(0, limit)]:
        preview.append(
            {
                "block": row.get("block_label", ""),
                "trial": row.get("block_trial_index", ""),
                "type": row.get("trial_type", ""),
                "phase": row.get("phase", ""),
                "soa_ms": row.get("soa_ms", ""),
                "space_cm": row.get("spatial_value_cm", ""),
                "tactile_site": row.get("tactile_site", ""),
                "noise": row.get("noise_label", ""),
            }
        )
    return preview


def participant_order_preview_rows(design: StimulusDesign, limit: int = 60) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for participant_id, order in list(participant_block_orders(design).items())[: max(0, limit)]:
        rows.append(
            {
                "participant": participant_id,
                "block_order": " -> ".join(order),
            }
        )
    return rows


def runner_asset_status(stimuli_dir: Path) -> dict[str, Any]:
    stimuli_dir = Path(stimuli_dir)
    participant_dirs = []
    block_wavs = []
    if stimuli_dir.exists():
        participant_dirs = [
            path
            for path in stimuli_dir.iterdir()
            if path.is_dir() and path.name.upper().startswith("P") and path.name[1:].isdigit()
        ]
        for participant_dir in participant_dirs:
            block_wavs.extend(participant_dir.rglob("*_concatenated.wav"))
    return {
        "stimuli_dir": str(stimuli_dir),
        "exists": stimuli_dir.exists(),
        "participants": len(participant_dirs),
        "block_wavs": len(block_wavs),
        "ready": stimuli_dir.exists() and bool(participant_dirs) and bool(block_wavs),
    }


def runner_launch_command(
    *,
    stimuli_dir: Path = DEFAULT_RUNNER_STIMULI_DIR,
    instructions_dir: Path = DEFAULT_RUNNER_INSTRUCTIONS_DIR,
    background_music: Path | None = None,
    settings_file: Path = DEFAULT_RUNNER_SETTINGS_FILE,
    demographics_dir: Path = DEFAULT_RUNNER_DEMOGRAPHICS_DIR,
    recordings_dir: Path = DEFAULT_RUNNER_RECORDINGS_DIR,
    list_devices: bool = False,
    python_executable: str | None = None,
) -> list[str]:
    if list_devices:
        return [
            python_executable or sys.executable,
            "-m",
            "peripersonal_space_toolkit.audio_device_stress",
            "--dry-run",
            "--device-query",
            "Komplete",
        ]
    _ = (stimuli_dir, instructions_dir, background_music, settings_file, demographics_dir, recordings_dir)
    runner_exe = resolve_packaged_focus_runner()
    if runner_exe is None:
        raise FileNotFoundError(
            "The active experiment runner is the packaged PPSExperimentRunner.exe. "
            "Build it with windows\\Build_Experiment_Runner_Exe.ps1 before launching a participant run."
        )
    return [str(runner_exe), "--launcher"]


class QtStimulusDesigner:
    def __init__(self, design_path: Path = DEFAULT_DESIGN_PATH):
        self.qt = _require_qt()
        app = self.qt["QApplication"].instance()
        if app is not None:
            app.setStyle("Fusion")
        QMainWindow = self.qt["QMainWindow"]
        self.window = QMainWindow()
        self.window.setWindowTitle("Peripersonal Space Toolkit - Stimulus Designer")
        self.window.resize(1280, 820)
        self.window.setMinimumSize(1080, 700)
        self.window.setStyleSheet(APP_STYLE_SHEET)
        self.app_icon = apply_qt_app_icon(self.qt, app=app, window=self.window)

        self.design_path = design_path
        self.design = load_design(design_path) if design_path.exists() else default_design()
        self.templates: list[StudyTemplate] = load_templates(TEMPLATE_DIR)
        self.block_specs: list[BlockSpec] = effective_block_specs(self.design.protocol)
        self._loading_block_table = False
        self.runner_render_dir = DEFAULT_RENDER_DIR
        self.current_run_package: RunPackage | None = None
        self.layout_settings = self.qt["QSettings"](LAYOUT_SETTINGS_ORG, LAYOUT_SETTINGS_APP)
        self._splitters: dict[str, Any] = {}
        self._applying_splitter_state = False
        self._preview_maximized = False

        self._build_ui()
        self._load_design(self.design)
        self.qt["QTimer"].singleShot(0, lambda: self._on_tab_changed(self.tab_widget.currentIndex()))

    def _apply_splitter_states_for_scope(self, scope: str) -> None:
        for key in SPLITTER_DEFAULT_SIZES:
            if not key.startswith(f"{scope}/"):
                continue
            self._apply_splitter_state(key)

    def _on_tab_changed(self, index: int) -> None:
        if not hasattr(self, "tab_widget"):
            return
        label = self.tab_widget.tabText(index).lower()
        if "stimulus" in label:
            scope = "stimulus"
        elif "trial" in label:
            scope = "trial"
        elif "runner" in label:
            scope = "runner"
        else:
            return
        self.qt["QTimer"].singleShot(0, lambda scope=scope: self._apply_splitter_states_for_scope(scope))

    def _make_spin(self, minimum: float, maximum: float, step: float, suffix: str = "", decimals: int = 1):
        spin = self.qt["QDoubleSpinBox"]()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
        spin.setDecimals(decimals)
        spin.setSuffix(suffix)
        spin.setButtonSymbols(self.qt["QAbstractSpinBox"].ButtonSymbols.NoButtons)
        spin.setFixedHeight(34)
        spin.valueChanged.connect(self._on_design_changed)
        return spin

    def _make_int_spin(self, minimum: int, maximum: int) -> Any:
        spin = self.qt["QSpinBox"]()
        spin.setRange(minimum, maximum)
        spin.setButtonSymbols(self.qt["QAbstractSpinBox"].ButtonSymbols.NoButtons)
        spin.setFixedHeight(34)
        return spin

    def _make_button(self, text: str, callback: Any | None = None, *, primary: bool = False, subtle: bool = False):
        button = self.qt["QPushButton"](text)
        if primary:
            button.setObjectName("primaryButton")
        elif subtle:
            button.setObjectName("subtleButton")
        if callback is not None:
            button.clicked.connect(callback)
        return button

    def _make_menu_button(self, text: str, actions: list[tuple[str, Any]]):
        button = self._make_button(text)
        menu = self.qt["QMenu"](button)
        for label, callback in actions:
            action = menu.addAction(label)
            action.triggered.connect(callback)
        button.setMenu(menu)
        return button

    def _style_table(self, table: Any, *, stretch_last: bool = True) -> None:
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setDefaultAlignment(self.qt["Qt"].AlignmentFlag.AlignLeft | self.qt["Qt"].AlignmentFlag.AlignVCenter)
        header.setSectionResizeMode(self.qt["QHeaderView"].ResizeMode.ResizeToContents)
        if stretch_last and table.columnCount() > 0:
            header.setSectionResizeMode(table.columnCount() - 1, self.qt["QHeaderView"].ResizeMode.Stretch)

    def _new_pane(self) -> tuple[Any, Any]:
        pane = self.qt["QWidget"]()
        layout = self.qt["QVBoxLayout"](pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        return pane, layout

    def _add_toolbar(self, layout: Any, actions: list[tuple[str, Any]], *, stretch_first: bool = True) -> Any:
        q = self.qt
        toolbar = q["QHBoxLayout"]()
        toolbar.setSpacing(6)
        if stretch_first:
            toolbar.addStretch(1)
        for label, callback in actions:
            toolbar.addWidget(self._make_button(label, callback))
        layout.addLayout(toolbar)
        return toolbar

    def _register_splitter(self, key: str, splitter: Any, *, children_collapsible: bool = False) -> Any:
        splitter.setObjectName(f"splitter_{key.replace('/', '_')}")
        splitter.setChildrenCollapsible(children_collapsible)
        self._splitters[key] = splitter
        splitter.splitterMoved.connect(lambda *_args, saved_key=key: self._save_splitter_state(saved_key))
        self._apply_splitter_state(key)
        return splitter

    def _apply_splitter_state(self, key: str) -> None:
        splitter = self._splitters.get(key)
        if splitter is None:
            return
        self._applying_splitter_state = True
        try:
            stored = self.layout_settings.value(f"splitters/{key}")
            restored = bool(stored) and splitter.restoreState(stored)
            if not restored:
                splitter.setSizes(list(SPLITTER_DEFAULT_SIZES[key]))
        finally:
            self._applying_splitter_state = False

    def _save_splitter_state(self, key: str) -> None:
        if self._applying_splitter_state:
            return
        splitter = self._splitters.get(key)
        if splitter is not None:
            self.layout_settings.setValue(f"splitters/{key}", splitter.saveState())

    def _reset_layout(self, scope: str = "all") -> None:
        prefixes = tuple(SPLITTER_DEFAULT_SIZES) if scope == "all" else tuple(
            key for key in SPLITTER_DEFAULT_SIZES if key.startswith(f"{scope}/")
        )
        if scope in {"all", "stimulus"}:
            self._restore_preview()
        self._applying_splitter_state = True
        try:
            for key in prefixes:
                self.layout_settings.remove(f"splitters/{key}")
                splitter = self._splitters.get(key)
                if splitter is not None:
                    splitter.setSizes(list(SPLITTER_DEFAULT_SIZES[key]))
        finally:
            self._applying_splitter_state = False
        self.status_label.setText("Layout reset.")

    def _maximize_preview(self) -> None:
        if not hasattr(self, "stimulus_controls_pane"):
            return
        self._preview_maximized = True
        self.stimulus_controls_pane.setVisible(False)
        self.trajectory_controls_pane.setVisible(False)
        self._applying_splitter_state = True
        try:
            self.stimulus_main_splitter.setSizes([1, 1000])
            self.stimulus_right_splitter.setSizes([1, 1000])
        finally:
            self._applying_splitter_state = False
        self._update_preview_action_state()

    def _restore_preview(self) -> None:
        if not hasattr(self, "stimulus_controls_pane"):
            return
        self._preview_maximized = False
        self.stimulus_controls_pane.setVisible(True)
        self.trajectory_controls_pane.setVisible(True)
        self._apply_splitter_state("stimulus/main")
        self._apply_splitter_state("stimulus/right")
        self._update_preview_action_state()

    def _update_preview_action_state(self) -> None:
        if hasattr(self, "maximize_preview_button"):
            self.maximize_preview_button.setEnabled(not self._preview_maximized)
        if hasattr(self, "restore_preview_button"):
            self.restore_preview_button.setEnabled(self._preview_maximized)

    def _build_ui(self) -> None:
        q = self.qt
        central = q["QWidget"]()
        root = q["QVBoxLayout"](central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        header = q["QHBoxLayout"]()
        self.name_edit = q["QLineEdit"]()
        self.name_edit.setMinimumWidth(220)
        self.template_combo = q["QComboBox"]()
        self.template_combo.setMinimumWidth(520)
        self.template_combo.setMinimumContentsLength(48)
        self.template_combo.setSizeAdjustPolicy(q["QComboBox"].SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.template_combo.addItems([study_template_citation_label(item) for item in self.templates])
        self.template_combo.currentIndexChanged.connect(lambda _idx: self._update_profile_summary())
        load_template = q["QPushButton"]("Load Profile")
        load_template.clicked.connect(self._load_template)
        self.citation_button = self._make_menu_button(
            "Citation",
            [
                ("Show Citation", self._show_profile_citation),
                ("Save BibTeX", self._save_profile_bibtex),
                ("Save CSL JSON", self._save_profile_csl_json),
            ],
        )
        self.citation_button.setObjectName("citationButton")
        header.addWidget(q["QLabel"]("Name"))
        header.addWidget(self.name_edit, 2)
        header.addWidget(q["QLabel"]("Study profile"))
        header.addWidget(self.template_combo, 3)
        header.addWidget(load_template)
        header.addWidget(self.citation_button)
        root.addLayout(header)
        profile_card = q["QFrame"]()
        profile_card.setObjectName("profileCard")
        profile_card_layout = q["QVBoxLayout"](profile_card)
        profile_card_layout.setContentsMargins(6, 4, 6, 4)
        self.profile_summary_label = q["QLabel"]("")
        self.profile_summary_label.setObjectName("profileSummary")
        self.profile_summary_label.setWordWrap(True)
        profile_card_layout.addWidget(self.profile_summary_label)
        root.addWidget(profile_card)

        tabs = q["QTabWidget"]()
        root.addWidget(tabs, 1)
        stimulus_tab = q["QWidget"]()
        trial_tab = q["QWidget"]()
        runner_tab = q["QWidget"]()
        tabs.addTab(stimulus_tab, "Stimulus Design")
        tabs.addTab(trial_tab, "Trial Assembler")
        tabs.addTab(runner_tab, "Experiment Runner")
        self.tab_widget = tabs
        tabs.currentChanged.connect(self._on_tab_changed)

        stimulus_layout = q["QVBoxLayout"](stimulus_tab)
        stimulus_layout.setContentsMargins(0, 0, 0, 0)
        stimulus_toolbar = q["QHBoxLayout"]()
        stimulus_toolbar.addStretch(1)
        stimulus_toolbar.addWidget(self._make_button("Reset Layout", lambda: self._reset_layout("stimulus")))
        self.maximize_preview_button = self._make_button("Maximize Preview", self._maximize_preview)
        self.restore_preview_button = self._make_button("Restore", self._restore_preview)
        stimulus_toolbar.addWidget(self.maximize_preview_button)
        stimulus_toolbar.addWidget(self.restore_preview_button)
        stimulus_layout.addLayout(stimulus_toolbar)

        splitter = q["QSplitter"](q["Qt"].Horizontal)
        self.stimulus_main_splitter = splitter
        stimulus_layout.addWidget(splitter, 1)

        self.stimulus_controls_pane, controls_layout = self._new_pane()
        left_splitter = q["QSplitter"](q["Qt"].Vertical)
        controls_layout.addWidget(left_splitter, 1)
        noise_pane, noise_layout = self._new_pane()
        audio_pane, audio_layout = self._new_pane()
        self._build_noise_panel(noise_layout)
        self._build_audio_panel(audio_layout)
        left_splitter.addWidget(noise_pane)
        left_splitter.addWidget(audio_pane)
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 1)

        right = q["QWidget"]()
        right_layout = q["QVBoxLayout"](right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_splitter = q["QSplitter"](q["Qt"].Vertical)
        self.stimulus_right_splitter = right_splitter
        right_layout.addWidget(right_splitter, 1)
        self.trajectory_controls_pane, trajectory_controls_layout = self._new_pane()
        self.trajectory_controls_pane.setMinimumHeight(300)
        viewer_pane, viewer_layout = self._new_pane()
        self._build_path_controls_panel(trajectory_controls_layout)
        self._build_trajectory_viewer_panel(viewer_layout)
        right_splitter.addWidget(self.trajectory_controls_pane)
        right_splitter.addWidget(viewer_pane)
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 2)

        splitter.addWidget(self.stimulus_controls_pane)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        self._register_splitter("stimulus/left", left_splitter)
        self._register_splitter("stimulus/right", right_splitter)
        self._register_splitter("stimulus/main", splitter)
        self._update_preview_action_state()

        self._build_trial_tab(trial_tab)
        self._build_runner_tab(runner_tab)

        footer = q["QHBoxLayout"]()
        self.status_label = q["QLabel"]("Ready.")
        footer.addWidget(self.status_label, 1)
        for text, callback in [
            ("Check", self._check_design),
            ("Render Looming WAVs", self._render_looming_wavs),
            ("Export Trajectory", self._export_trajectory),
            ("Export Protocol", self._export_protocol),
            ("Save Settings", self._save_settings),
            ("Load Settings", self._load_settings),
            ("Save As", self._save_as),
            ("Load File", self._load_file),
        ]:
            button = q["QPushButton"](text)
            button.clicked.connect(callback)
            footer.addWidget(button)
        root.addLayout(footer)

        self.window.setCentralWidget(central)

    def _build_noise_panel(self, layout: Any) -> None:
        q = self.qt
        group = q["QGroupBox"]("Noise Types And Orientations")
        group.setObjectName("noisePanel")
        box = q["QVBoxLayout"](group)
        self.noise_table = q["QTableWidget"](0, 5)
        self.noise_table.setHorizontalHeaderLabels(["Label", "Type", "Azimuth", "Elevation", "Gain"])
        self.noise_table.setSelectionBehavior(q["QAbstractItemView"].SelectionBehavior.SelectRows)
        self.noise_table.itemSelectionChanged.connect(self._noise_selected)
        box.addWidget(self.noise_table)

        form = q["QGridLayout"]()
        self.noise_label = q["QLineEdit"]()
        self.noise_type = q["QComboBox"]()
        self.noise_type.addItems(["pink", "blue", "white", "brown"])
        self.noise_azimuth = self._make_spin(ROTATION_DEG_MIN, ROTATION_DEG_MAX, 1, " deg", 1)
        self.noise_elevation = self._make_spin(0, 0, 1, " deg", 1)
        self.noise_gain = self._make_spin(0.1, 2.0, 0.1, "", 2)
        self.noise_gain.setValue(1.0)
        for col, label in enumerate(["Label", "Type", "Azimuth", "Elevation", "Gain"]):
            form.addWidget(q["QLabel"](label), 0, col)
        for col, widget in enumerate([self.noise_label, self.noise_type, self.noise_azimuth, self.noise_elevation, self.noise_gain]):
            form.addWidget(widget, 1, col)
        box.addLayout(form)
        buttons = q["QHBoxLayout"]()
        add_update = q["QPushButton"]("Add / Update")
        add_update.clicked.connect(self._add_or_update_noise)
        remove = q["QPushButton"]("Remove")
        remove.clicked.connect(self._remove_noise)
        buttons.addWidget(add_update)
        buttons.addWidget(remove)
        buttons.addStretch(1)
        box.addLayout(buttons)
        layout.addWidget(group)

    def _build_audio_panel(self, layout: Any) -> None:
        q = self.qt
        group = q["QGroupBox"]("Custom Audio Preloads")
        group.setObjectName("audioPanel")
        group.setMinimumHeight(300)
        box = q["QVBoxLayout"](group)
        self.audio_table = q["QTableWidget"](0, 4)
        self.audio_table.setMaximumHeight(105)
        self.audio_table.setHorizontalHeaderLabels(["Type", "Label", "Target s", "File"])
        self.audio_table.setSelectionBehavior(q["QAbstractItemView"].SelectionBehavior.SelectRows)
        self.audio_table.itemSelectionChanged.connect(self._audio_selected)
        box.addWidget(self.audio_table)

        form = q["QGridLayout"]()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(9)
        self.audio_type = q["QComboBox"]()
        self.audio_type.addItems(["Looming", "Prestimulus"])
        self.audio_label = q["QLineEdit"]()
        self.audio_duration = self._make_spin(0.1, 60.0, 0.1, "", 1)
        self.audio_path = q["QLineEdit"]()
        browse = q["QPushButton"]("Browse")
        browse.clicked.connect(self._browse_audio)
        for col, label in enumerate(["Type", "Label", "Target s"]):
            form.addWidget(q["QLabel"](label), 0, col)
        form.addWidget(self.audio_type, 1, 0)
        form.addWidget(self.audio_label, 1, 1)
        form.addWidget(self.audio_duration, 1, 2)
        form.addWidget(q["QLabel"]("File"), 2, 0)
        form.addWidget(self.audio_path, 3, 0, 1, 2)
        form.addWidget(browse, 3, 2)
        box.addLayout(form)
        buttons = q["QHBoxLayout"]()
        add_update = q["QPushButton"]("Add / Update")
        add_update.clicked.connect(self._add_or_update_audio)
        remove = q["QPushButton"]("Remove")
        remove.clicked.connect(self._remove_audio)
        validate = q["QPushButton"]("Validate File")
        validate.clicked.connect(self._validate_audio)
        for button in (add_update, remove, validate):
            buttons.addWidget(button)
        buttons.addStretch(1)
        box.addLayout(buttons)
        layout.addWidget(group, 1)

    def _build_endpoint_panel(self, title: str):
        q = self.qt
        group = q["QGroupBox"](title)
        group.setObjectName("trajectoryStartPanel" if title == "Starting Point" else "trajectoryEndPanel")
        group.setMinimumHeight(130)
        group.setMaximumHeight(150)
        grid = q["QGridLayout"](group)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        distance = self._make_spin(DISTANCE_CM_MIN, DISTANCE_CM_MAX, 0.1, " cm", 3)
        rotation = self._make_spin(DISPLAY_ROTATION_DEG_MIN, DISPLAY_ROTATION_DEG_MAX, 0.1, " deg", 3)
        height_label = q["QLabel"]("Height")
        height_label.setToolTip("Height from head plane")
        height = self._make_spin(-DISTANCE_CM_MAX, DISTANCE_CM_MAX, 0.1, " cm", 3)
        height.setToolTip("Height from head plane")
        height.setValue(0.0)
        distance_label = q["QLabel"]("Distance")
        distance_label.setToolTip("Distance from listener")
        rotation_label = q["QLabel"]("Rotation")
        rotation_label.setToolTip("Rotation around listener")
        for col, label in enumerate([distance_label, rotation_label]):
            grid.addWidget(label, 0, col)
        grid.addWidget(height_label, 0, 2)
        for col, widget in enumerate([distance, rotation, height]):
            grid.addWidget(widget, 1, col)
            grid.setColumnStretch(col, 1)
        return group, distance, rotation, height, height_label

    def _build_path_panel(self, layout: Any) -> None:
        self._build_path_controls_panel(layout)
        self._build_trajectory_viewer_panel(layout)

    def _build_path_controls_panel(self, layout: Any) -> None:
        q = self.qt
        endpoint_row = q["QHBoxLayout"]()
        start_group, self.start_distance, self.start_rotation, self.start_height, self.start_height_label = self._build_endpoint_panel("Starting Point")
        end_group, self.end_distance, self.end_rotation, self.end_height, self.end_height_label = self._build_endpoint_panel("End Point")
        endpoint_row.addWidget(start_group)
        endpoint_row.addWidget(end_group)
        layout.addLayout(endpoint_row)

        timing = q["QGroupBox"]("Movement Timing")
        timing.setObjectName("timingPanel")
        timing.setMinimumHeight(145)
        timing.setMaximumHeight(170)
        timing_grid = q["QGridLayout"](timing)
        timing_grid.setHorizontalSpacing(12)
        timing_grid.setVerticalSpacing(9)
        self.movement_duration = self._make_spin(0.1, 30.0, 0.1, " s", 2)
        self.lead_padding = self._make_spin(0.0, 30.0, 0.1, " s", 2)
        self.tail_padding = self._make_spin(0.0, 30.0, 0.1, " s", 2)
        self.path_summary = q["QLabel"]("")
        timing_grid.addWidget(q["QLabel"]("Movement duration"), 0, 0)
        timing_grid.addWidget(self.movement_duration, 0, 1)
        timing_grid.addWidget(q["QLabel"]("Start hold"), 0, 2)
        timing_grid.addWidget(self.lead_padding, 0, 3)
        timing_grid.addWidget(q["QLabel"]("End hold"), 1, 0)
        timing_grid.addWidget(self.tail_padding, 1, 1)
        timing_grid.addWidget(q["QLabel"]("Derived path"), 1, 2)
        timing_grid.addWidget(self.path_summary, 1, 3)
        timing_grid.setColumnStretch(1, 1)
        timing_grid.setColumnStretch(3, 1)
        layout.addWidget(timing)

    def _build_trajectory_viewer_panel(self, layout: Any) -> None:
        q = self.qt
        viewer_group = q["QGroupBox"]("Trajectory Preview")
        viewer_group.setObjectName("viewerPanel")
        viewer_group.setMinimumHeight(280)
        viewer_layout = q["QVBoxLayout"](viewer_group)
        viewer_controls = q["QHBoxLayout"]()
        self.preview_mode = q["QComboBox"]()
        self.preview_mode.addItem("2D bird's-eye", "2d")
        self.preview_mode.addItem("3D orbit", "3d")
        self.preview_mode.currentIndexChanged.connect(self._on_preview_mode_changed)
        viewer_controls.addWidget(q["QLabel"]("Preview mode"))
        viewer_controls.addWidget(self.preview_mode)
        viewer_controls.addStretch(1)
        viewer_layout.addLayout(viewer_controls)
        self.web_view = q["QWebEngineView"]()
        self.web_view.setMinimumHeight(170)
        viewer_layout.addWidget(self.web_view, 1)
        reset_camera = q["QPushButton"]("Reset Camera")
        reset_camera.setMaximumWidth(140)
        reset_camera.clicked.connect(lambda: self.web_view.page().runJavaScript("window.resetTrajectoryCamera && window.resetTrajectoryCamera();"))
        camera_row = q["QHBoxLayout"]()
        camera_row.addStretch(1)
        camera_row.addWidget(reset_camera)
        viewer_layout.addLayout(camera_row)
        layout.addWidget(viewer_group, 1)

        viewer_path = designer_frontend_root() / "viewer" / "index.html"
        self.web_view.loadFinished.connect(lambda _ok: self._update_viewer())
        self.web_view.load(q["QUrl"].fromLocalFile(str(viewer_path)))
        self._set_height_controls_enabled(False)

    def _build_trial_tab(self, tab: Any) -> None:
        q = self.qt
        layout = q["QVBoxLayout"](tab)
        layout.setContentsMargins(0, 0, 0, 0)
        self._add_toolbar(layout, [("Reset Layout", lambda: self._reset_layout("trial"))])
        splitter = q["QSplitter"](q["Qt"].Horizontal)
        layout.addWidget(splitter, 1)

        left_splitter = q["QSplitter"](q["Qt"].Vertical)
        right_splitter = q["QSplitter"](q["Qt"].Vertical)
        condition_pane, condition_layout = self._new_pane()
        family_pane, family_layout = self._new_pane()
        block_pane, block_layout = self._new_pane()
        summary_pane, summary_layout = self._new_pane()
        preview_pane, preview_layout = self._new_pane()
        order_pane, order_layout = self._new_pane()

        self._build_trial_condition_panel(condition_layout)
        self._build_trial_family_panel(family_layout)
        self._build_block_assembler_panel(block_layout)
        self._build_protocol_summary_panel(summary_layout)
        self._build_trial_table_preview_panel(preview_layout)
        self._build_participant_order_panel(order_layout)

        for pane in (condition_pane, family_pane, block_pane):
            left_splitter.addWidget(pane)
        for pane in (summary_pane, preview_pane, order_pane):
            right_splitter.addWidget(pane)
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 1)
        left_splitter.setStretchFactor(2, 2)
        right_splitter.setStretchFactor(0, 1)
        right_splitter.setStretchFactor(1, 3)
        right_splitter.setStretchFactor(2, 1)

        left = q["QWidget"]()
        left_layout = q["QVBoxLayout"](left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(left_splitter, 1)
        right = q["QWidget"]()
        right_layout = q["QVBoxLayout"](right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(right_splitter, 1)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        self._register_splitter("trial/left", left_splitter)
        self._register_splitter("trial/right", right_splitter)
        self._register_splitter("trial/main", splitter)
        self._connect_protocol_widgets()

    def _build_trial_condition_panel(self, layout: Any) -> None:
        q = self.qt
        group = q["QGroupBox"]("Conditions")
        group.setObjectName("conditionsPanel")
        group.setMinimumHeight(320)
        controls = q["QGridLayout"](group)
        controls.setAlignment(q["Qt"].AlignmentFlag.AlignTop)
        controls.setHorizontalSpacing(12)
        controls.setVerticalSpacing(8)
        self.repetitions = self._make_int_spin(1, 999)
        self.soa_values = q["QLineEdit"]()
        self.spatial_values = q["QLineEdit"]()
        self.pair_spatial = q["QCheckBox"]("Pair SOA and spatial values")
        self.pair_spatial.setText("SOA/space")
        self.pair_spatial.setToolTip("Pair SOA and spatial values")
        self.motion_directions = q["QLineEdit"]()
        self.tactile_sites = q["QLineEdit"]()
        self.respiratory_phases = q["QLineEdit"]()
        self.participants = self._make_int_spin(1, 9999)

        label_help = {
            "Reps": "Repetitions per condition",
            "SOAs": "Stimulus onset asynchronies in milliseconds",
            "Space cm": "Spatial values at tactile onset in centimetres",
            "Motion": "Auditory motion labels",
            "Tactile": "Tactile sites",
        }
        self.spatial_values.setToolTip("Spatial values at tactile onset in centimetres")
        self.soa_values.setMinimumWidth(120)
        self.spatial_values.setMinimumWidth(105)
        self.respiratory_phases.setMinimumWidth(115)

        def field_cell(label_text: str, widget: Any) -> Any:
            cell = q["QWidget"]()
            cell.setObjectName("fieldCell")
            cell.setFixedHeight(66)
            cell_layout = q["QVBoxLayout"](cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(3)
            label = q["QLabel"](label_text)
            if label_text in label_help:
                label.setToolTip(label_help[label_text])
            cell_layout.addWidget(label)
            cell_layout.addWidget(widget)
            return cell

        cells = [
            ("Reps", self.repetitions),
            ("Participants", self.participants),
            ("SOAs", self.soa_values),
            ("Pairing", self.pair_spatial),
            ("Space cm", self.spatial_values),
            ("Motion", self.motion_directions),
            ("Tactile", self.tactile_sites),
            ("Respiration", self.respiratory_phases),
        ]
        for idx, (label, widget) in enumerate(cells):
            controls.addWidget(field_cell(label, widget), idx // 4, idx % 4)
        for col in range(4):
            controls.setColumnStretch(col, 1)
        layout.addWidget(group)

    def _build_trial_family_panel(self, layout: Any) -> None:
        q = self.qt
        group = q["QGroupBox"]("Trial Families")
        group.setObjectName("familiesPanel")
        controls = q["QGridLayout"](group)
        self.include_baseline = q["QCheckBox"]("Tactile-only baseline")
        self.catch_percentage = self._make_spin(0, 99.9, 1, " %", 1)
        self.catch_exact = q["QLineEdit"]()
        self.baseline_soas = q["QLineEdit"]()
        self.trial_randomization = q["QComboBox"]()
        self.trial_randomization.addItems(["balanced_shuffle", "no_immediate_repeats", "ordered"])
        self.block_randomization = q["QComboBox"]()
        self.block_randomization.addItems(["counterbalanced_rotation", "seeded_random_permutation", "fixed"])
        self.max_same_type = self._make_int_spin(1, 99)
        self.random_seed = self._make_int_spin(0, 2_147_483_647)

        controls.addWidget(self.include_baseline, 0, 0, 1, 2)
        controls.addWidget(q["QLabel"]("Baseline SOAs (ms)"), 1, 0)
        controls.addWidget(self.baseline_soas, 1, 1)
        controls.addWidget(q["QLabel"]("Catch trials"), 2, 0)
        catch_row = q["QHBoxLayout"]()
        catch_row.addWidget(self.catch_percentage)
        catch_row.addWidget(q["QLabel"]("or exact"))
        catch_row.addWidget(self.catch_exact)
        controls.addLayout(catch_row, 2, 1)
        automation = q["QLabel"](
            "Ordering is generated reproducibly: no immediate repeats within blocks and counterbalanced participant block order."
        )
        automation.setWordWrap(True)
        controls.addWidget(automation, 3, 0, 1, 2)
        layout.addWidget(group)

    def _build_block_assembler_panel(self, layout: Any) -> None:
        q = self.qt
        group = q["QGroupBox"]("Block Sequence")
        group.setObjectName("blocksPanel")
        box = q["QVBoxLayout"](group)
        self.block_table = q["QTableWidget"](0, 4)
        self.block_table.setHorizontalHeaderLabels(["Block", "Audio-Tactile", "Baseline", "Catch"])
        self.block_table.setSelectionBehavior(q["QAbstractItemView"].SelectionBehavior.SelectRows)
        self.block_table.itemChanged.connect(self._block_table_changed)
        box.addWidget(self.block_table, 1)
        buttons = q["QHBoxLayout"]()
        add_block = q["QPushButton"]("Add Block")
        add_block.clicked.connect(self._add_block)
        remove_block = q["QPushButton"]("Remove Selected")
        remove_block.clicked.connect(self._remove_block)
        buttons.addWidget(add_block)
        buttons.addWidget(remove_block)
        buttons.addStretch(1)
        box.addLayout(buttons)
        layout.addWidget(group, 1)

    def _build_trial_preview_panel(self, layout: Any) -> None:
        self._build_protocol_summary_panel(layout)
        self._build_trial_table_preview_panel(layout)
        self._build_participant_order_panel(layout)

    def _build_protocol_summary_panel(self, layout: Any) -> None:
        q = self.qt
        summary_group = q["QGroupBox"]("Protocol Summary")
        summary_group.setObjectName("summaryPanel")
        summary_layout = q["QVBoxLayout"](summary_group)
        self.protocol_summary = q["QTextEdit"]()
        self.protocol_summary.setReadOnly(True)
        summary_layout.addWidget(self.protocol_summary)
        layout.addWidget(summary_group)

    def _build_trial_table_preview_panel(self, layout: Any) -> None:
        q = self.qt
        preview_group = q["QGroupBox"]("Trial Table Preview")
        preview_group.setObjectName("trialPreviewPanel")
        preview_layout = q["QVBoxLayout"](preview_group)
        self.trial_preview_table = q["QTableWidget"](0, 8)
        self.trial_preview_table.setHorizontalHeaderLabels(
            ["Block", "Trial", "Type", "Phase", "SOA", "Space", "Tactile Site", "Noise"]
        )
        self.trial_preview_table.setEditTriggers(q["QAbstractItemView"].EditTrigger.NoEditTriggers)
        preview_layout.addWidget(self.trial_preview_table, 1)
        layout.addWidget(preview_group, 2)

    def _build_participant_order_panel(self, layout: Any) -> None:
        q = self.qt
        order_group = q["QGroupBox"]("Participant Block Orders")
        order_group.setObjectName("ordersPanel")
        order_layout = q["QVBoxLayout"](order_group)
        self.participant_order_table = q["QTableWidget"](0, 2)
        self.participant_order_table.setHorizontalHeaderLabels(["Participant", "Block order"])
        self.participant_order_table.setEditTriggers(q["QAbstractItemView"].EditTrigger.NoEditTriggers)
        order_layout.addWidget(self.participant_order_table)
        order_buttons = q["QHBoxLayout"]()
        refresh = q["QPushButton"]("Refresh")
        refresh.clicked.connect(self._on_design_changed)
        export = q["QPushButton"]("Export Schedule CSV")
        export.clicked.connect(self._export_protocol)
        order_buttons.addWidget(refresh)
        order_buttons.addWidget(export)
        order_buttons.addStretch(1)
        order_layout.addLayout(order_buttons)
        layout.addWidget(order_group)

    def _connect_protocol_widgets(self) -> None:
        widgets = [
            self.repetitions,
            self.soa_values,
            self.spatial_values,
            self.pair_spatial,
            self.include_baseline,
            self.catch_percentage,
            self.catch_exact,
            self.baseline_soas,
            self.motion_directions,
            self.tactile_sites,
            self.respiratory_phases,
            self.participants,
        ]

        for widget in [
            self.trial_randomization,
            self.block_randomization,
            self.max_same_type,
            self.random_seed,
        ]:
            widget.setVisible(False)
            widgets.append(widget)

        for widget in widgets:
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._on_design_changed)
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self._on_design_changed)
            if hasattr(widget, "currentTextChanged"):
                widget.currentTextChanged.connect(self._on_design_changed)
            if hasattr(widget, "stateChanged"):
                widget.stateChanged.connect(self._on_design_changed)

    def _build_runner_tab(self, tab: Any) -> None:
        q = self.qt
        layout = q["QVBoxLayout"](tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._add_toolbar(layout, [("Reset Layout", lambda: self._reset_layout("runner"))])

        setup = q["QGroupBox"]("Prepare")
        setup.setObjectName("preparePanel")
        setup_grid = q["QGridLayout"](setup)
        self.runner_participant_id = q["QLineEdit"]("P001")
        self.runner_participant_id.textChanged.connect(self._refresh_runner_status)
        self.runner_render_dir_label = q["QLabel"](str(self.runner_render_dir))
        self.runner_render_dir_label.setWordWrap(True)
        self.runner_session_output_label = q["QLabel"](str(DEFAULT_SESSION_ROOT))
        self.runner_session_output_label.setWordWrap(True)
        setup_grid.addWidget(q["QLabel"]("Participant"), 0, 0)
        setup_grid.addWidget(self.runner_participant_id, 0, 1)
        setup_grid.addWidget(q["QLabel"]("Stimuli"), 1, 0)
        setup_grid.addWidget(self.runner_render_dir_label, 1, 1)
        setup_grid.addWidget(q["QLabel"]("Session output"), 2, 0)
        setup_grid.addWidget(self.runner_session_output_label, 2, 1)

        readiness = q["QGroupBox"]("Readiness")
        readiness.setObjectName("readinessPanel")
        readiness_layout = q["QVBoxLayout"](readiness)
        readiness_layout.addWidget(q["QLabel"]("Audio route"))
        self.runner_audio_route_label = q["QLabel"]("")
        self.runner_audio_route_label.setWordWrap(True)
        readiness_layout.addWidget(self.runner_audio_route_label)
        self.runner_status = q["QTextEdit"]()
        self.runner_status.setReadOnly(True)
        self.runner_status.setMinimumHeight(190)
        readiness_layout.addWidget(self.runner_status, 1)

        review = q["QGroupBox"]("Review")
        review.setObjectName("reviewPanel")
        review_layout = q["QVBoxLayout"](review)
        self.runner_review = q["QTextEdit"]()
        self.runner_review.setReadOnly(True)
        self.runner_review.setMinimumHeight(160)
        review_layout.addWidget(self.runner_review)

        splitter = q["QSplitter"](q["Qt"].Horizontal)
        right_splitter = q["QSplitter"](q["Qt"].Vertical)
        setup_pane, setup_layout = self._new_pane()
        setup_layout.addWidget(setup)
        setup_layout.addStretch(1)
        readiness_pane, readiness_pane_layout = self._new_pane()
        readiness_pane_layout.addWidget(readiness)
        review_pane, review_pane_layout = self._new_pane()
        review_pane_layout.addWidget(review)
        right_splitter.addWidget(readiness_pane)
        right_splitter.addWidget(review_pane)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 1)
        splitter.addWidget(setup_pane)
        splitter.addWidget(right_splitter)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)
        self._register_splitter("runner/right", right_splitter)
        self._register_splitter("runner/main", splitter)

        actions = q["QHBoxLayout"]()
        self.runner_render_button = q["QPushButton"]("Render")
        self.runner_render_button.clicked.connect(self._render_looming_wavs_for_runner)
        self.runner_prepare_button = q["QPushButton"]("Prepare")
        self.runner_prepare_button.clicked.connect(self._prepare_runner_artifacts)
        self.runner_stress_audio_button = q["QPushButton"]("Stress Audio")
        self.runner_stress_audio_button.clicked.connect(self._stress_audio_route)
        self.runner_start_button = q["QPushButton"]("Start Focus Mode")
        self.runner_start_button.setObjectName("primaryButton")
        self.runner_start_button.clicked.connect(self._start_focus_mode)
        for button in (
            self.runner_render_button,
            self.runner_prepare_button,
            self.runner_stress_audio_button,
            self.runner_start_button,
        ):
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addLayout(actions)

    def _browse_directory_into(self, widget: Any, title: str) -> None:
        path = self.qt["QFileDialog"].getExistingDirectory(self.window, title, widget.text() or str(REPO_ROOT))
        if path:
            widget.setText(path)

    def _browse_file_into(self, widget: Any, title: str) -> None:
        path, _ = self.qt["QFileDialog"].getOpenFileName(self.window, title, widget.text() or str(REPO_ROOT), "All files (*.*)")
        if path:
            widget.setText(path)

    def _runner_paths(self) -> dict[str, Path | None]:
        def _text(name: str, default: Path | str) -> str:
            widget = getattr(self, name, None)
            if widget is not None and hasattr(widget, "text"):
                return widget.text().strip() or str(default)
            return str(default)

        background = _text("runner_background_music", "")
        return {
            "stimuli_dir": Path(_text("runner_stimuli_dir", DEFAULT_RUNNER_STIMULI_DIR)),
            "instructions_dir": Path(_text("runner_instructions_dir", DEFAULT_RUNNER_INSTRUCTIONS_DIR)),
            "background_music": Path(background) if background else None,
            "settings_file": Path(_text("runner_settings_file", DEFAULT_RUNNER_SETTINGS_FILE)),
            "demographics_dir": Path(_text("runner_demographics_dir", DEFAULT_RUNNER_DEMOGRAPHICS_DIR)),
            "recordings_dir": Path(_text("runner_recordings_dir", DEFAULT_RUNNER_RECORDINGS_DIR)),
        }

    def _runner_command(self, *, list_devices: bool = False) -> list[str]:
        paths = self._runner_paths()
        return runner_launch_command(
            stimuli_dir=paths["stimuli_dir"],  # type: ignore[arg-type]
            instructions_dir=paths["instructions_dir"],  # type: ignore[arg-type]
            background_music=paths["background_music"],
            settings_file=paths["settings_file"],  # type: ignore[arg-type]
            demographics_dir=paths["demographics_dir"],  # type: ignore[arg-type]
            recordings_dir=paths["recordings_dir"],  # type: ignore[arg-type]
            list_devices=list_devices,
        )

    def _refresh_runner_status(self) -> None:
        if not hasattr(self, "runner_status"):
            return
        participant_id = self.runner_participant_id.text().strip() if hasattr(self, "runner_participant_id") else "P001"
        try:
            design = self._build_design_from_fields()
            summary = protocol_summary(design)
            preflight = preflight_run_package(design, participant_id, render_dir=self.runner_render_dir, require_audio=True)
            protocol_lines = [f"{key}: {value}" for key, value in summary.items()]
        except Exception as exc:
            self.runner_status.setPlainText(f"Design status: {exc}")
            if hasattr(self, "runner_start_button"):
                self.runner_start_button.setEnabled(False)
            return
        if hasattr(self, "runner_audio_route_label"):
            self.runner_audio_route_label.setText(preflight.audio_route)
        if hasattr(self, "runner_render_dir_label"):
            self.runner_render_dir_label.setText(str(self.runner_render_dir))
        if hasattr(self, "runner_session_output_label"):
            session_text = str(self.current_run_package.session_dir) if self.current_run_package else str(DEFAULT_SESSION_ROOT)
            self.runner_session_output_label.setText(session_text)
        checklist = [
            ("Participant", preflight.participant_ready),
            ("Design", preflight.valid_design),
            ("Stimuli", preflight.render_ready),
            ("Schedule", preflight.schedule_ready),
            ("Audio route", preflight.audio_ready),
        ]
        wav_lines = [
            f"- {wav.label}: {wav.duration_s:.2f}s, {wav.channels} ch, {wav.sample_rate} Hz"
            for wav in preflight.rendered_wavs[:6]
        ]
        if len(preflight.rendered_wavs) > 6:
            wav_lines.append(f"- {len(preflight.rendered_wavs) - 6} more")
        lines = [
            "Readiness",
            *[f"{label}: {'ready' if ready else 'required'}" for label, ready in checklist],
            "",
            "Current protocol",
            *protocol_lines,
            "",
            "Rendered stimuli",
            *(wav_lines or ["Render required"]),
        ]
        if self.current_run_package:
            lines.extend(["", "Prepared session", str(self.current_run_package.manifest_path)])
        if preflight.messages:
            lines.extend(["", "Warnings", *preflight.messages])
        self.runner_status.setPlainText("\n".join(lines))
        if hasattr(self, "runner_start_button"):
            self.runner_start_button.setEnabled(preflight.ready and bool(self.current_run_package))
        if hasattr(self, "runner_prepare_button"):
            self.runner_prepare_button.setEnabled(preflight.participant_ready and preflight.valid_design and preflight.render_ready)

    def _check_runner_assets(self) -> None:
        self._refresh_runner_status()
        wavs = rendered_wavs(self.runner_render_dir)
        if wavs:
            self.qt["QMessageBox"].information(self.window, "Stimuli", f"{len(wavs)} rendered WAV file(s) are available.")
        else:
            self.qt["QMessageBox"].warning(self.window, "Stimuli", "Render required before preparing a session.")

    def _prepare_runner_artifacts(self) -> None:
        try:
            design = self._build_design_from_fields()
            package = prepare_run_package(
                design,
                self.runner_participant_id.text(),
                render_dir=self.runner_render_dir,
                session_root=DEFAULT_SESSION_ROOT,
            )
        except Exception as exc:
            self.qt["QMessageBox"].warning(self.window, "Prepare", str(exc))
            self._refresh_runner_status()
            return
        self.current_run_package = package
        self.status_label.setText(f"Prepared session {package.session_id}")
        self._append_runner_review(
            "\n".join(
                [
                    f"Prepared session: {package.session_id}",
                    f"Session output: {package.session_dir}",
                    f"Blocks: {len(package.blocks)}",
                    f"Manifest: {package.manifest_path}",
                ]
            )
        )
        self._refresh_runner_status()

    def _list_audio_devices(self) -> None:
        self._stress_audio_route()

    def _stress_audio_route(self) -> None:
        command = [
            sys.executable,
            "-m",
            "peripersonal_space_toolkit.audio_device_stress",
            "--device-query",
            "Komplete",
            "--mode",
            "callback",
            "--iterations",
            "1",
            "--duration-s",
            "2",
            "--latency",
            "0.010",
            "--blocksize",
            "256",
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                timeout=45,
                check=False,
                **windows_no_console_kwargs(),
            )
            output = (completed.stdout + "\n" + completed.stderr).strip()
            self._append_runner_review(output or "Audio stress command returned no output.")
        except Exception as exc:
            self.qt["QMessageBox"].warning(self.window, "Stress Audio", str(exc))

    def _launch_experiment_runner(self) -> None:
        self._start_focus_mode()

    def _start_focus_mode(self) -> None:
        try:
            preflight = preflight_run_package(
                self._build_design_from_fields(),
                self.runner_participant_id.text(),
                render_dir=self.runner_render_dir,
                require_audio=True,
            )
        except Exception as exc:
            self.qt["QMessageBox"].warning(self.window, "Start Focus Mode", str(exc))
            return
        if self.current_run_package is None or not preflight.ready:
            message = "Prepare a session and resolve all readiness items before Focus Mode."
            if preflight.messages:
                message += "\n\n" + "\n".join(preflight.messages)
            self.qt["QMessageBox"].warning(self.window, "Start Focus Mode", message)
            self._refresh_runner_status()
            return
        try:
            launch_command = build_focus_runner_command(self.current_run_package.manifest_path, manual_start=True)
            subprocess.Popen(launch_command.command, cwd=REPO_ROOT, **windows_no_console_kwargs())
            self._append_runner_review(f"Opened active experiment runner: {launch_command.runner_binary}")
        except Exception as exc:
            self.qt["QMessageBox"].warning(self.window, "Start Focus Mode", str(exc))

    def _append_runner_review(self, text: str) -> None:
        if hasattr(self, "runner_review"):
            current = self.runner_review.toPlainText().strip()
            self.runner_review.setPlainText((current + "\n\n" + text).strip() if current else text)
        if hasattr(self, "runner_status"):
            self._refresh_runner_status()

    def _render_looming_wavs_for_runner(self, checked: bool = False) -> None:
        _ = checked
        self._render_looming_wavs(output_dir=self.runner_render_dir, prompt_for_output=False)

    def _set_table_values(self, table: Any, rows: list[list[str]]) -> None:
        table.setRowCount(len(rows))
        QTableWidgetItem = self.qt["QTableWidgetItem"]
        for row_idx, row_values in enumerate(rows):
            for col_idx, value in enumerate(row_values):
                table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

    def _set_preview_table_values(self, table: Any, rows: list[dict[str, Any]], columns: list[str]) -> None:
        table.setRowCount(len(rows))
        QTableWidgetItem = self.qt["QTableWidgetItem"]
        for row_idx, row in enumerate(rows):
            for col_idx, key in enumerate(columns):
                table.setItem(row_idx, col_idx, QTableWidgetItem(str(row.get(key, ""))))
        table.resizeColumnsToContents()

    def _checkable_item(self, checked: bool):
        item = self.qt["QTableWidgetItem"]("")
        item.setFlags(item.flags() | self.qt["Qt"].ItemFlag.ItemIsUserCheckable)
        item.setCheckState(self.qt["Qt"].CheckState.Checked if checked else self.qt["Qt"].CheckState.Unchecked)
        return item

    def _refresh_block_table(self) -> None:
        if not hasattr(self, "block_table"):
            return
        self._loading_block_table = True
        try:
            self.block_table.setRowCount(len(self.block_specs))
            QTableWidgetItem = self.qt["QTableWidgetItem"]
            for row_idx, block in enumerate(self.block_specs):
                self.block_table.setItem(row_idx, 0, QTableWidgetItem(block.label))
                for col_idx, trial_type in enumerate(SUPPORTED_TRIAL_TYPES, start=1):
                    self.block_table.setItem(row_idx, col_idx, self._checkable_item(trial_type in block.stimulus_types))
            self.block_table.resizeColumnsToContents()
        finally:
            self._loading_block_table = False

    def _block_table_changed(self, item: Any) -> None:
        if self._loading_block_table or item is None:
            return
        rows: list[BlockSpec] = []
        for row_idx in range(self.block_table.rowCount()):
            label_item = self.block_table.item(row_idx, 0)
            label = label_item.text().strip() if label_item else f"Block {row_idx + 1}"
            stimulus_types = []
            for col_idx, trial_type in enumerate(SUPPORTED_TRIAL_TYPES, start=1):
                check_item = self.block_table.item(row_idx, col_idx)
                if check_item and check_item.checkState() == self.qt["Qt"].CheckState.Checked:
                    stimulus_types.append(trial_type)
            rows.append(BlockSpec(label=label or f"Block {row_idx + 1}", stimulus_types=stimulus_types))
        self.block_specs = rows or [BlockSpec("Block 1", list(SUPPORTED_TRIAL_TYPES))]
        self._on_design_changed()

    def _add_block(self) -> None:
        self.block_specs.append(BlockSpec(f"Block {len(self.block_specs) + 1}", list(SUPPORTED_TRIAL_TYPES)))
        self._refresh_block_table()
        self._on_design_changed()

    def _remove_block(self) -> None:
        row = self._selected_row(self.block_table)
        if row is None or not (0 <= row < len(self.block_specs)):
            return
        del self.block_specs[row]
        if not self.block_specs:
            self.block_specs = [BlockSpec("Block 1", list(SUPPORTED_TRIAL_TYPES))]
        self._refresh_block_table()
        self._on_design_changed()

    def _load_design(self, design: StimulusDesign) -> None:
        self.design = design
        self.name_edit.setText(design.name)
        template_idx = self._template_index_for_id(design.study_profile_id)
        if template_idx is not None and self.template_combo.currentIndex() != template_idx:
            blocked = self.template_combo.blockSignals(True)
            try:
                self.template_combo.setCurrentIndex(template_idx)
            finally:
                self.template_combo.blockSignals(blocked)
        start, end = trajectory_endpoints_xyz(design.trajectory)
        start_distance_cm, start_rotation = _as_cm_and_rotation(start)
        end_distance_cm, end_rotation = _as_cm_and_rotation(end)
        self.start_distance.setValue(max(DISTANCE_CM_MIN, min(DISTANCE_CM_MAX, start_distance_cm)))
        self.start_rotation.setValue(max(DISPLAY_ROTATION_DEG_MIN, min(DISPLAY_ROTATION_DEG_MAX, start_rotation)))
        self.end_distance.setValue(max(DISTANCE_CM_MIN, min(DISTANCE_CM_MAX, end_distance_cm)))
        self.end_rotation.setValue(max(DISPLAY_ROTATION_DEG_MIN, min(DISPLAY_ROTATION_DEG_MAX, end_rotation)))
        self.start_height.setValue(max(-DISTANCE_CM_MAX, min(DISTANCE_CM_MAX, _height_cm(start))))
        self.end_height.setValue(max(-DISTANCE_CM_MAX, min(DISTANCE_CM_MAX, _height_cm(end))))
        has_height = abs(start["z_m"]) > 1e-9 or abs(end["z_m"]) > 1e-9
        self.preview_mode.setCurrentText("3D orbit" if has_height else "2D bird's-eye")
        self._set_height_controls_enabled(has_height)
        self.movement_duration.setValue(max(0.1, design.trajectory.movement_duration_s))
        self.lead_padding.setValue(design.trajectory.padding_pre_s)
        self.tail_padding.setValue(design.trajectory.padding_post_s)

        self._refresh_noise_table()
        self._refresh_audio_table()
        self._load_protocol(design.protocol)
        self._update_profile_summary()
        self._on_design_changed()

    def _load_protocol(self, protocol: ProtocolSpec) -> None:
        self.repetitions.setValue(protocol.repetitions_per_condition)
        self.soa_values.setText(", ".join(str(value) for value in protocol.soa_values_ms))
        self.spatial_values.setText(", ".join(f"{value:g}" for value in protocol.spatial_values_cm))
        self.pair_spatial.setChecked(protocol.pair_spatial_values_with_soas)
        self.include_baseline.setChecked(protocol.include_baseline_trials)
        self.catch_percentage.setValue(protocol.catch_trial_percentage)
        self.catch_exact.setText("" if protocol.catch_trials_exact is None else str(protocol.catch_trials_exact))
        self.baseline_soas.setText(", ".join(str(value) for value in protocol.baseline_soa_values_ms))
        self.motion_directions.setText(", ".join(protocol.auditory_motion_directions))
        self.tactile_sites.setText(", ".join(protocol.tactile_sites))
        self.respiratory_phases.setText(", ".join(protocol.respiratory_phases))
        for line_edit in (
            self.soa_values,
            self.spatial_values,
            self.catch_exact,
            self.baseline_soas,
            self.motion_directions,
            self.tactile_sites,
            self.respiratory_phases,
        ):
            line_edit.setCursorPosition(0)
        self.trial_randomization.setCurrentText(protocol.trial_randomization_strategy)
        self.block_randomization.setCurrentText(protocol.block_order_randomization)
        self.max_same_type.setValue(protocol.max_consecutive_same_trial_type)
        self.participants.setValue(protocol.participants)
        self.random_seed.setValue(protocol.random_seed)
        self.block_specs = effective_block_specs(protocol)
        self._refresh_block_table()

    def _refresh_noise_table(self) -> None:
        self._set_table_values(
            self.noise_table,
            [[noise.label, noise.noise_type, f"{noise.azimuth_deg:g}", f"{noise.elevation_deg:g}", f"{noise.gain:g}"] for noise in self.design.noises],
        )

    def _refresh_audio_table(self) -> None:
        rows = []
        for asset in self.design.custom_looming_files:
            rows.append(["Looming", asset.label, f"{asset.target_duration_s:g}", asset.path])
        for asset in self.design.prestimulus_files:
            rows.append(["Prestimulus", asset.label, f"{asset.target_duration_s:g}", asset.path])
        self._set_table_values(self.audio_table, rows)

    def _parse_int_list(self, value: str, label: str) -> list[int]:
        try:
            return [int(part.strip()) for part in value.split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError(f"{label} must be a comma-separated list of integers.") from exc

    def _parse_float_list(self, value: str, label: str) -> list[float]:
        try:
            return [float(part.strip()) for part in value.split(",") if part.strip()]
        except ValueError as exc:
            raise ValueError(f"{label} must be a comma-separated list of numbers.") from exc

    def _parse_string_list(self, value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    def _parse_optional_int(self, value: str) -> int | None:
        value = value.strip()
        return int(value) if value else None

    def _build_protocol_from_fields(self) -> ProtocolSpec:
        return ProtocolSpec(
            repetitions_per_condition=self.repetitions.value(),
            soa_values_ms=self._parse_int_list(self.soa_values.text(), "SOAs"),
            spatial_values_cm=self._parse_float_list(self.spatial_values.text(), "Spatial values"),
            pair_spatial_values_with_soas=self.pair_spatial.isChecked(),
            auditory_motion_directions=self._parse_string_list(self.motion_directions.text()),
            tactile_sites=self._parse_string_list(self.tactile_sites.text()),
            catch_trial_percentage=self.catch_percentage.value(),
            catch_trials_exact=self._parse_optional_int(self.catch_exact.text()),
            include_baseline_trials=self.include_baseline.isChecked(),
            baseline_soa_values_ms=self._parse_int_list(self.baseline_soas.text(), "Baseline SOAs"),
            respiratory_phases=self._parse_string_list(self.respiratory_phases.text()),
            blocks=len(self.block_specs),
            block_specs=list(self.block_specs),
            trial_randomization_strategy=self.trial_randomization.currentText(),
            block_order_randomization=self.block_randomization.currentText(),
            max_consecutive_same_trial_type=self.max_same_type.value(),
            participants=self.participants.value(),
            random_seed=self.random_seed.value(),
        )

    def _preview_mode_id(self) -> str:
        if not hasattr(self, "preview_mode"):
            return "2d"
        return self.preview_mode.currentData() or "2d"

    def _set_height_controls_enabled(self, enabled: bool) -> None:
        for widget_name in ("start_height", "end_height", "start_height_label", "end_height_label"):
            if hasattr(self, widget_name):
                widget = getattr(self, widget_name)
                widget.setVisible(enabled)
                widget.setEnabled(enabled)

    def _on_preview_mode_changed(self) -> None:
        enabled = self._preview_mode_id() == "3d"
        self._set_height_controls_enabled(enabled)
        self._on_design_changed()

    def _build_design_from_fields(self) -> StimulusDesign:
        base = StimulusDesign(
            name=self.name_edit.text().strip() or "Untitled PPS stimulus design",
            study_profile_id=self.design.study_profile_id,
            study_profile_title=self.design.study_profile_title,
            study_profile_notes=self.design.study_profile_notes,
            study_profile_reference_parameters=dict(self.design.study_profile_reference_parameters),
            sofa_file=DEFAULT_SOFA_FILE,
            noises=list(self.design.noises),
            custom_looming_files=list(self.design.custom_looming_files),
            prestimulus_files=list(self.design.prestimulus_files),
            protocol=self._build_protocol_from_fields(),
        )
        return create_design_from_endpoint_controls(
            base,
            start_distance_cm=self.start_distance.value(),
            start_rotation_deg=self.start_rotation.value(),
            end_distance_cm=self.end_distance.value(),
            end_rotation_deg=self.end_rotation.value(),
            movement_duration_s=self.movement_duration.value(),
            lead_padding_s=self.lead_padding.value(),
            tail_padding_s=self.tail_padding.value(),
            start_height_cm=self.start_height.value() if self._preview_mode_id() == "3d" else 0.0,
            end_height_cm=self.end_height.value() if self._preview_mode_id() == "3d" else 0.0,
        )

    def _on_design_changed(self) -> None:
        try:
            self.design = self._build_design_from_fields()
        except Exception:
            return
        if hasattr(self, "current_run_package"):
            self.current_run_package = None
        self._update_path_summary()
        self._update_viewer()
        self._update_protocol_summary()

    def _update_path_summary(self) -> None:
        text = (
            f"{self.design.trajectory.path_length_m:.2f} m; "
            f"{self.design.trajectory.propagation_speed_mps:.2f} m/s; "
            f"{self.design.trajectory.total_duration_s:.2f} s total"
        )
        self.path_summary.setText(text)

    def _update_viewer(self) -> None:
        if not hasattr(self, "web_view"):
            return
        preview_mode = self._preview_mode_id()
        payload = json.dumps(trajectory_viewer_payload(self.design, preview_mode=preview_mode))
        self.web_view.page().runJavaScript(f"window.updateTrajectory && window.updateTrajectory({payload});")

    def _update_protocol_summary(self) -> None:
        if not hasattr(self, "protocol_summary"):
            return
        try:
            design = self._build_design_from_fields()
            summary = protocol_summary(design)
        except Exception:
            return
        self.protocol_summary.setPlainText("\n".join(f"{key}: {value}" for key, value in summary.items()))
        if hasattr(self, "trial_preview_table"):
            self._set_preview_table_values(
                self.trial_preview_table,
                trial_assembler_preview_rows(design),
                ["block", "trial", "type", "phase", "soa_ms", "space_cm", "tactile_site", "noise"],
            )
        if hasattr(self, "participant_order_table"):
            self._set_preview_table_values(
                self.participant_order_table,
                participant_order_preview_rows(design),
                ["participant", "block_order"],
            )
        if hasattr(self, "runner_status"):
            self._refresh_runner_status()

    def _template_index_for_id(self, template_id: str) -> int | None:
        if not template_id:
            return None
        for idx, template in enumerate(self.templates):
            if template.template_id == template_id:
                return idx
        return None

    def _selected_template(self) -> StudyTemplate | None:
        if not hasattr(self, "template_combo"):
            return None
        idx = self.template_combo.currentIndex()
        if 0 <= idx < len(self.templates):
            return self.templates[idx]
        return None

    def _loaded_template(self) -> StudyTemplate | None:
        idx = self._template_index_for_id(self.design.study_profile_id)
        return self.templates[idx] if idx is not None else None

    def _profile_parameter_suffix(self, params: dict[str, Any]) -> str:
        details = []
        if "trajectory_plane_height_m" in params:
            details.append(f"plane {float(params['trajectory_plane_height_m']) * 100:g} cm")
        if {"start_x_m", "stop_x_m", "front_offset_y_m"}.issubset(params):
            details.append(
                f"x {float(params['start_x_m']) * 100:g} to {float(params['stop_x_m']) * 100:g} cm, "
                f"front offset {float(params['front_offset_y_m']) * 100:g} cm"
            )
        if "speed_mps" in params:
            details.append(f"speed {float(params['speed_mps']) * 100:g} cm/s")
        if "noise_type" in params:
            details.append(f"{params['noise_type']} noise")
        return "; ".join(details)

    def _update_profile_summary(self) -> None:
        if not hasattr(self, "profile_summary_label"):
            return
        selected = self._selected_template()
        loaded = self._loaded_template()
        lines = []
        if selected is not None:
            lines.append(f"Selected preload paper: {study_template_citation_label(selected)}")
        if loaded is not None:
            details = self._profile_parameter_suffix(self.design.study_profile_reference_parameters)
            suffix = f" Parameters: {details}." if details else ""
            lines.append(f"Current settings loaded from: {loaded.citation}{suffix}")
            if loaded.doi:
                lines.append(f"DOI: {loaded.doi}")
            elif loaded.source_url:
                lines.append(f"Source: {loaded.source_url}")
        else:
            lines.append("Current settings: Custom design")
        if hasattr(self, "citation_button"):
            self.citation_button.setEnabled(selected is not None)
        self.profile_summary_label.setText("\n".join(lines))

    def _show_profile_citation(self) -> None:
        template = self._selected_template()
        if template is None:
            self.qt["QMessageBox"].warning(self.window, "Citation", "Select a study profile first.")
            return
        message = self.qt["QMessageBox"](self.window)
        message.setWindowTitle("Study Profile Citation")
        message.setText(study_template_citation_label(template))
        detail_lines = [
            template.citation,
            "",
            f"Verification status: {template.verification_status}",
        ]
        if template.doi:
            detail_lines.append(f"DOI: {template.doi}")
        if template.source_url:
            detail_lines.append(f"Source: {template.source_url}")
        message.setInformativeText("\n".join(detail_lines))
        message.setDetailedText(study_template_bibtex(template))
        message.exec()

    def _save_profile_citation_file(self, *, suffix: str, file_filter: str, content: str) -> None:
        template = self._selected_template()
        if template is None:
            self.qt["QMessageBox"].warning(self.window, "Citation", "Select a study profile first.")
            return
        default_dir = REPO_ROOT / "artifacts" / "citations"
        default_path = default_dir / f"{template.template_id}.{suffix}"
        path, _ = self.qt["QFileDialog"].getSaveFileName(self.window, "Save citation", str(default_path), file_filter)
        if not path:
            return
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        self.status_label.setText(f"Saved citation {output_path}")

    def _save_profile_bibtex(self) -> None:
        template = self._selected_template()
        if template is not None:
            self._save_profile_citation_file(
                suffix="bib",
                file_filter="BibTeX files (*.bib);;All files (*.*)",
                content=study_template_bibtex(template),
            )

    def _save_profile_csl_json(self) -> None:
        template = self._selected_template()
        if template is not None:
            self._save_profile_citation_file(
                suffix="json",
                file_filter="CSL JSON files (*.json);;All files (*.*)",
                content=study_template_csl_json(template),
            )

    def _selected_row(self, table: Any) -> int | None:
        selected = table.selectionModel().selectedRows()
        return selected[0].row() if selected else None

    def _noise_selected(self) -> None:
        row = self._selected_row(self.noise_table)
        if row is None or row >= len(self.design.noises):
            return
        noise = self.design.noises[row]
        self.noise_label.setText(noise.label)
        self.noise_type.setCurrentText(noise.noise_type)
        self.noise_azimuth.setValue(noise.azimuth_deg)
        self.noise_elevation.setValue(0.0)
        self.noise_gain.setValue(noise.gain)

    def _add_or_update_noise(self) -> None:
        row = self._selected_row(self.noise_table)
        existing = self.design.noises[row] if row is not None and row < len(self.design.noises) else None
        source_profile = existing.source_profile if existing and existing.source_profile else PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
        source_profile_parameters = (
            dict(existing.source_profile_parameters)
            if existing and existing.source_profile_parameters
            else gold_standard_looming_source_parameters()
        )
        noise = NoiseDefinition(
            label=self.noise_label.text().strip() or self.noise_type.currentText().title(),
            noise_type=self.noise_type.currentText(),
            azimuth_deg=self.noise_azimuth.value(),
            elevation_deg=0.0,
            gain=self.noise_gain.value(),
            source_profile=source_profile,
            source_profile_parameters=source_profile_parameters,
        )
        if row is None:
            self.design.noises.append(noise)
        else:
            self.design.noises[row] = noise
        self._refresh_noise_table()
        self._on_design_changed()

    def _remove_noise(self) -> None:
        row = self._selected_row(self.noise_table)
        if row is not None and 0 <= row < len(self.design.noises):
            del self.design.noises[row]
            self._refresh_noise_table()
            self._on_design_changed()

    def _audio_selected(self) -> None:
        row = self._selected_row(self.audio_table)
        if row is None:
            return
        looming_count = len(self.design.custom_looming_files)
        if row < looming_count:
            asset = self.design.custom_looming_files[row]
            self.audio_type.setCurrentText("Looming")
        else:
            asset = self.design.prestimulus_files[row - looming_count]
            self.audio_type.setCurrentText("Prestimulus")
        self.audio_label.setText(asset.label)
        self.audio_duration.setValue(asset.target_duration_s)
        self.audio_path.setText(asset.path)

    def _browse_audio(self) -> None:
        path, _ = self.qt["QFileDialog"].getOpenFileName(self.window, "Select audio file", str(REPO_ROOT), "Audio files (*.wav *.mp3);;All files (*.*)")
        if path:
            self.audio_path.setText(path)

    def _add_or_update_audio(self) -> None:
        asset = AudioFileSpec(
            label=self.audio_label.text().strip() or Path(self.audio_path.text()).stem,
            path=self.audio_path.text().strip(),
            target_duration_s=self.audio_duration.value(),
        )
        row = self._selected_row(self.audio_table)
        kind = self.audio_type.currentText()
        if row is None:
            if kind == "Looming":
                self.design.custom_looming_files.append(asset)
            else:
                self.design.prestimulus_files.append(asset)
        else:
            looming_count = len(self.design.custom_looming_files)
            if row < looming_count:
                if kind == "Looming":
                    self.design.custom_looming_files[row] = asset
                else:
                    del self.design.custom_looming_files[row]
                    self.design.prestimulus_files.append(asset)
            else:
                idx = row - looming_count
                if kind == "Prestimulus":
                    self.design.prestimulus_files[idx] = asset
                else:
                    del self.design.prestimulus_files[idx]
                    self.design.custom_looming_files.append(asset)
        self._refresh_audio_table()
        self._on_design_changed()

    def _remove_audio(self) -> None:
        row = self._selected_row(self.audio_table)
        if row is None:
            return
        looming_count = len(self.design.custom_looming_files)
        if row < looming_count:
            del self.design.custom_looming_files[row]
        else:
            del self.design.prestimulus_files[row - looming_count]
        self._refresh_audio_table()
        self._on_design_changed()

    def _validate_audio(self) -> None:
        path = Path(self.audio_path.text())
        if not path.exists():
            self.qt["QMessageBox"].warning(self.window, "Audio file", f"File not found:\n{path}")
            return
        self.qt["QMessageBox"].information(self.window, "Audio file", "File exists.")

    def _load_template(self) -> None:
        idx = self.template_combo.currentIndex()
        if 0 <= idx < len(self.templates):
            self._load_design(self.templates[idx].design)
            self.status_label.setText(f"Loaded study profile: {self.templates[idx].title}")

    def _check_design(self) -> None:
        try:
            design = self._build_design_from_fields()
        except Exception as exc:
            self.qt["QMessageBox"].warning(self.window, "Invalid design", str(exc))
            return
        warnings = validate_design(design)
        if warnings:
            self.qt["QMessageBox"].warning(self.window, "Design check", "\n".join(warnings))
        else:
            self.qt["QMessageBox"].information(self.window, "Design check", "Design check passed.")

    def _save_settings(self) -> None:
        save_design(self._build_design_from_fields(), self.design_path)
        self.status_label.setText(f"Saved {self.design_path}")

    def _load_settings(self) -> None:
        if self.design_path.exists():
            self._load_design(load_design(self.design_path))
            self.status_label.setText(f"Loaded {self.design_path}")

    def _save_as(self) -> None:
        path, _ = self.qt["QFileDialog"].getSaveFileName(self.window, "Save design", str(self.design_path), "JSON files (*.json);;All files (*.*)")
        if path:
            self.design_path = Path(path)
            self._save_settings()

    def _load_file(self) -> None:
        path, _ = self.qt["QFileDialog"].getOpenFileName(self.window, "Load design", str(REPO_ROOT), "JSON files (*.json);;All files (*.*)")
        if path:
            self.design_path = Path(path)
            self._load_design(load_design(self.design_path))

    def _render_looming_wavs(self, checked: bool = False, *, output_dir: Path | None = None, prompt_for_output: bool = True) -> None:
        _ = checked
        if prompt_for_output:
            selected = self.qt["QFileDialog"].getExistingDirectory(
                self.window,
                "Select render output directory",
                str(REPO_ROOT / "artifacts" / "rendered_looming"),
            )
            if not selected:
                return
            output_path = Path(selected)
        else:
            output_path = Path(output_dir or self.runner_render_dir)
        design_path = output_path / "stimulus_design.for_render.json"
        try:
            save_design(self._build_design_from_fields(), design_path)
            result = render_backend.render_design_with_3dti(
                design_path,
                output_path,
                seed=self.random_seed.value() if hasattr(self, "random_seed") else 20250604,
            )
        except Exception as exc:
            self.qt["QMessageBox"].warning(self.window, "Render looming WAVs", str(exc))
            return

        self.status_label.setText(f"3DTI render status: {result.status}")
        self.runner_render_dir = output_path
        self.current_run_package = None
        if hasattr(self, "runner_render_dir_label"):
            self.runner_render_dir_label.setText(str(output_path))
        if result.status == "backend_missing":
            self.qt["QMessageBox"].warning(
                self.window,
                "3DTI backend missing",
                (
                    "The render config, trajectory samples, manifest, and QC CSV were written, "
                    "but no WAVs were synthesized because the 3DTI renderer backend is not built.\n\n"
                    f"Manifest:\n{result.manifest_path}"
                ),
            )
        elif result.status in {"rendered_3dti", "rendered_reference"}:
            title = "Render complete" if result.status == "rendered_3dti" else "Reference render complete"
            detail = (
                "Native 3DTI render completed."
                if result.status == "rendered_3dti"
                else "Native 3DTI was not available, so the Python SOFA/FABIAN reference renderer produced the WAVs."
            )
            self.qt["QMessageBox"].information(
                self.window,
                title,
                (
                    f"{detail}\n\n"
                    f"WAV files: {len(result.wav_paths)}\n"
                    f"Manifest:\n{result.manifest_path}\n"
                    f"QC:\n{result.qc_path}\n"
                    f"Tactile events:\n{result.tactile_events_path}"
                ),
            )
        else:
            self.qt["QMessageBox"].information(
                self.window,
                "Render status",
                f"3DTI render status: {result.status}\n\nManifest:\n{result.manifest_path}",
            )
        if hasattr(self, "runner_status"):
            self._refresh_runner_status()

    def _export_trajectory(self) -> None:
        path, _ = self.qt["QFileDialog"].getSaveFileName(self.window, "Export trajectory CSV", str(REPO_ROOT / "artifacts" / "stimulus_trajectory.csv"), "CSV files (*.csv);;All files (*.*)")
        if path:
            export_trajectory_csv(self._build_design_from_fields(), Path(path))
            self.status_label.setText(f"Exported {path}")

    def _export_protocol(self) -> None:
        path, _ = self.qt["QFileDialog"].getSaveFileName(self.window, "Export protocol CSV", str(REPO_ROOT / "artifacts" / "stimulus_protocol.csv"), "CSV files (*.csv);;All files (*.*)")
        if path:
            export_protocol_csv(self._build_design_from_fields(), Path(path))
            self.status_label.setText(f"Exported {path}")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    set_windows_app_user_model_id()
    qt = _require_qt()
    QApplication = qt["QApplication"]
    app = QApplication.instance() or QApplication(sys.argv[:1])
    designer = QtStimulusDesigner(args.design)
    designer.window.show()
    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
