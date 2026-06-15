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
    prepared_session_asset_status,
    prepared_session_asset_statuses,
    record_experiment_activity,
    record_prepared_session_queue,
    segment_run_setup_participants,
    _timeline_tactile_events,
    _timeline_trial_segments,
)
from .timing_schedule import BlockEventSchedule
from .preload_inventory import load_preload_inventory
from .runtime_paths import repo_root


DEFAULT_FOCUS_PROFILE_DESIGN_PATH = DEFAULT_DASHBOARD_STATE_ROOT / "focus_profile_runner_design.json"
DEFAULT_FOCUS_LAYOUT_PROFILE = render_focus_layout_profile(1120, 720)
FOCUS_STYLE_SHEET = render_focus_style_sheet(DEFAULT_FOCUS_LAYOUT_PROFILE)
STUDY5_PROFILE_ID = "study5_box_breathing_pps"
DATA_COLLECTED_MARK = "[collected]"


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
        from PySide6.QtCore import QPoint, QTimer, Qt, Signal
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
        "QPoint": QPoint,
        "QProgressBar": QProgressBar,
        "QPushButton": QPushButton,
        "Signal": Signal,
        "QSizePolicy": QSizePolicy,
        "QSplitter": QSplitter,
        "QTabWidget": QTabWidget,
        "QTextEdit": QTextEdit,
        "QTimer": QTimer,
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


def _compact_run_block_label(block: Any) -> str:
    text = str(getattr(block, "label", "") or f"Block {getattr(block, 'index', '')}").strip()
    return text if len(text) <= 24 else f"{text[:21]}..."


def _run_plan_items(package: Any, *, include_topup_slots: bool) -> list[dict[str, Any]]:
    standard_blocks = [block for block in getattr(package, "blocks", []) if not _is_topup_block(block)]
    items: list[dict[str, Any]] = []
    display_index = 0
    for index, block in enumerate(standard_blocks):
        part_key = _block_part_key(block)
        display_index += 1
        items.append(
            {
                "kind": "standard",
                "part_key": part_key,
                "number": display_index,
                "label": _compact_run_block_label(block),
                "block_index": int(getattr(block, "index", display_index) or display_index),
                "trial_count": int(getattr(block, "trial_count", 0) or 0),
                "duration_s": float(getattr(block, "duration_s", 0.0) or 0.0),
            }
        )
        next_block = standard_blocks[index + 1] if index + 1 < len(standard_blocks) else None
        if include_topup_slots and (next_block is None or _block_part_key(next_block) != part_key):
            display_index += 1
            items.append(
                {
                    "kind": "topup",
                    "part_key": part_key,
                    "number": display_index,
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
        entries = ", ".join(f"{item['number']} {item['label']}" for item in part_items)
        lines.append(f"{_part_display_label(part_key)}: {entries}")
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


def _create_tactile_timeline_widget(
    q: dict[str, Any],
    state: TactileTimelineState,
    profile: FocusLayoutProfile | None = None,
    state_provider: Callable[[], TactileTimelineState] | None = None,
) -> Any:
    class TactileTimelineWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            self.setMinimumHeight(84 if profile is not None and profile.screen_class == "constrained" else 116)

        def paintEvent(self, _event: Any) -> None:  # noqa: N802 - Qt API
            painter = q["QPainter"](self)
            try:
                painter.setRenderHint(q["QPainter"].RenderHint.Antialiasing, True)
                width = max(1, int(self.width()))
                height = max(1, int(self.height()))
                label_width = 58
                right_margin = 12
                compact_rows = height < 108
                top_margin = 6 if compact_rows else 10
                usable = max(1, width - label_width - right_margin)
                timeline_state = state_provider() if state_provider is not None else state
                duration = max(0.001, float(timeline_state.duration_s or 0.0))
                row_offsets = (3, 22, 41, 60) if compact_rows else (5, 31, 58, 86)
                rows = [(label, top_margin + offset) for label, offset in zip(("Clip", "Trial", "Tactile", "Clicks"), row_offsets)]

                painter.fillRect(self.rect(), q["QColor"]("#f8f9f6"))
                label_pen = q["QPen"](q["QColor"]("#647067"))
                painter.setPen(label_pen)
                for label, row_y in rows:
                    painter.drawText(4, row_y - 8, label_width - 8, 18, int(q["Qt"].AlignmentFlag.AlignRight), label)
                    guide_pen = q["QPen"](q["QColor"]("#d9dfd6"))
                    guide_pen.setWidth(1)
                    painter.setPen(guide_pen)
                    painter.drawLine(label_width, row_y, width - right_margin, row_y)
                    painter.setPen(label_pen)

                if not timeline_state.cues and not timeline_state.trial_segments:
                    painter.setPen(q["QPen"](q["QColor"]("#647067")))
                    painter.drawText(self.rect(), q["Qt"].AlignmentFlag.AlignCenter, "No experiment schedule loaded")
                    return

                def _x(time_s: float) -> int:
                    return label_width + int(max(0.0, min(1.0, float(time_s) / duration)) * usable)

                def _short(text: str, limit: int = 18) -> str:
                    clean = " ".join(str(text or "").replace("|", " ").split())
                    return clean if len(clean) <= limit else f"{clean[: max(1, limit - 3)]}..."

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
                    return palette[fallback_index % len(palette)]

                row_height = 16 if compact_rows else 18
                for index, segment in enumerate(timeline_state.trial_segments):
                    x1 = _x(segment.start_s)
                    x2 = max(x1 + 2, _x(segment.end_s))
                    clip_color = _color_for(segment.clip_label, index)
                    trial_color = _color_for(segment.trial_label, index + 2)
                    for row_index, (text, y, color) in enumerate(
                        (
                            (segment.clip_label or segment.family or "Clip", rows[0][1] - row_height // 2, clip_color),
                            (segment.trial_label or segment.family or "Trial", rows[1][1] - row_height // 2, trial_color),
                        )
                    ):
                        painter.setPen(q["QPen"](q["QColor"]("#bcc7bd")))
                        painter.setBrush(q["QBrush"](q["QColor"](color)))
                        painter.drawRoundedRect(x1, y, max(2, x2 - x1), row_height, 4, 4)
                        if x2 - x1 >= 34:
                            painter.setPen(q["QPen"](q["QColor"]("#202621")))
                            painter.drawText(x1 + 3, y + 1, max(1, x2 - x1 - 6), row_height - 2, int(q["Qt"].AlignmentFlag.AlignVCenter), _short(text, 16 if row_index else 20))

                for cue in timeline_state.cues:
                    status = timeline_state.cue_status(cue)
                    color = {
                        "passed": "#647067",
                        "recentered": "#246b55",
                        "next": "#8c2f2f",
                        "upcoming": "#d9dfd6",
                    }.get(status, "#d9dfd6")
                    x = _x(cue.time_s)
                    line_y = rows[2][1]
                    radius = 5 if status == "next" else 4
                    marker_pen = q["QPen"](q["QColor"]("#202621" if status == "next" else "#bcc7bd"))
                    marker_pen.setWidth(1)
                    painter.setPen(marker_pen)
                    painter.setBrush(q["QBrush"](q["QColor"](color)))
                    painter.drawEllipse(x - radius, line_y - radius, radius * 2, radius * 2)

                click_pen = q["QPen"](q["QColor"]("#1d5d99"))
                click_pen.setWidth(2)
                painter.setPen(click_pen)
                painter.setBrush(q["QBrush"](q["QColor"]("#dce7f4")))
                click_y = rows[3][1]
                for marker in timeline_state.click_markers:
                    x = _x(marker.time_s)
                    painter.drawRect(x - 4, click_y - 4, 8, 8)

                cursor_x = _x(timeline_state.elapsed_s)
                cursor_pen = q["QPen"](q["QColor"]("#b91c1c"))
                cursor_pen.setWidth(3)
                painter.setPen(cursor_pen)
                painter.drawLine(cursor_x, 4, cursor_x, min(height - 4, rows[-1][1] + 14))
            finally:
                painter.end()

    return TactileTimelineWidget()


def _create_block_plan_widget(q: dict[str, Any], owner: Any) -> Any:
    class BlockPlanWidget(q["QWidget"]):
        def __init__(self) -> None:
            super().__init__()
            profile = getattr(owner, "layout_profile", None)
            self._compact = bool(profile is not None and profile.screen_class == "constrained")
            self.setMinimumHeight(36 if self._compact else 58)
            self.setCursor(q["Qt"].CursorShape.PointingHandCursor)
            self.setMouseTracking(True)

        def _column_count(self, width: int, count: int) -> int:
            margin = 8
            gap = 5
            min_width = 36 if self._compact else 42
            available = max(min_width, int(width) - (2 * margin))
            return max(1, min(max(1, count), int((available + gap) / (min_width + gap))))

        def refresh_layout_height(self) -> None:
            items = list(getattr(owner, "block_plan_items", []) or [])
            if not items:
                target_height = 36 if self._compact else 58
            else:
                margin = 8
                gap = 5
                box_height = 28 if self._compact else 32
                columns = self._column_count(max(1, int(self.width())), len(items))
                rows = max(1, int(math.ceil(len(items) / columns)))
                target_height = (2 * margin) + (rows * box_height) + ((rows - 1) * gap)
                target_height = max(36 if self._compact else 58, target_height)
            if int(self.minimumHeight()) != int(target_height):
                self.setMinimumHeight(int(target_height))
                self.updateGeometry()

        def resizeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            super().resizeEvent(event)
            self.refresh_layout_height()

        def _layout_items(self) -> list[dict[str, Any]]:
            items = list(getattr(owner, "block_plan_items", []) or [])
            if not items:
                return []
            width = max(1, int(self.width()))
            margin = 8
            gap = 5
            count = len(items)
            columns = self._column_count(width, count)
            rows = max(1, int(math.ceil(count / columns)))
            box_height = 28 if self._compact else 32
            available_width = max(1, width - (2 * margin) - (gap * (columns - 1)))
            box_width = max(32 if self._compact else 38, int(available_width / columns))
            layout_items: list[dict[str, Any]] = []
            for index, item in enumerate(items):
                row = int(index / columns)
                column = index % columns
                x = margin + column * (box_width + gap)
                y = margin + row * (box_height + gap)
                if y + box_height > max(self.height(), self.minimumHeight()) - 2:
                    box_height = max(20, int((max(self.height(), self.minimumHeight()) - (2 * margin) - (gap * (rows - 1))) / rows))
                    y = margin + row * (box_height + gap)
                entry = dict(item)
                entry.update({"x": x, "y": y, "width": box_width, "height": box_height})
                layout_items.append(entry)
            return layout_items

        def item_center(self, number: int) -> Any:
            for item in self._layout_items():
                if int(item.get("number") or 0) == int(number):
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
                label = str(item.get("label") or "")
                self.setToolTip(f"Block {item.get('number')}: {label}" if label else f"Block {item.get('number')}")
            super().mouseMoveEvent(event)

        def mousePressEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
            if event.button() == q["Qt"].MouseButton.LeftButton:
                try:
                    point = event.position().toPoint()
                except AttributeError:
                    point = event.pos()
                item = self._item_at(point)
                if item is not None:
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
                    number = int(item.get("number") or 0)
                    x = int(item["x"])
                    y = int(item["y"])
                    box_width = int(item["width"])
                    box_height = int(item["height"])
                    kind = str(item.get("kind") or "")
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
                    label = "TU" if kind == "topup" else f"{number}"
                    if box_width >= 68:
                        label = f"{number} TU" if kind == "topup" else f"Block {number}"
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
    options.sort(key=lambda item: (0 if item[0] == STUDY5_PROFILE_ID else 1, item[1].lower()))
    return options


def profile_participant_ids(profile_id: str) -> list[str]:
    """Return the numbered participant IDs declared by a finished profile."""
    profile = str(profile_id or "").strip()
    if not profile:
        return ["P001"]
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
    return (
        DEFAULT_PROJECT_REGISTRY_ROOT
        / f"profile_{profile}"
        / "6_experiment_run_setup"
        / "experiment_run_setup_manifest.json"
    )


def profile_participant_asset_statuses(profile_id: str) -> dict[str, dict[str, Any]]:
    participants = profile_participant_ids(profile_id)
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
    return prepared_session_asset_statuses(run_setup, participants, state_root=DEFAULT_DASHBOARD_STATE_ROOT)


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


def _package_participant_statuses(package: Any, participants: list[str]) -> dict[str, dict[str, Any]]:
    statuses: dict[str, dict[str, Any]] = {}
    run_setup = getattr(package, "source_run_setup_manifest_path", None)
    if run_setup and participants:
        run_setup_path = Path(run_setup)
        if run_setup_path.is_file():
            try:
                statuses = prepared_session_asset_statuses(
                    run_setup_path,
                    participants,
                    state_root=DEFAULT_DASHBOARD_STATE_ROOT,
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
            session_root=DEFAULT_SESSION_ROOT,
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
                session_root=DEFAULT_SESSION_ROOT,
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
        self._participant_combo_updating = False
        self._run_active = False
        self._run_paused = False
        self._timeline_perf_anchor: float | None = None
        self.timeline_state = TactileTimelineState()
        self.timeline_preview_state = TactileTimelineState()
        self.selected_display_block_index: int | None = None
        self.preview_display_block_index: int | None = None
        self.recenter_records: list[dict[str, Any]] = []
        self._last_recenter_backend_warning = ""
        self.validation_topup_approval_records: list[dict[str, Any]] = []
        self.planned_tactile_cue_count = 0
        self.block_plan_items: list[dict[str, Any]] = []
        self.active_display_block_index: int | None = None
        self.completed_display_block_indices: set[int] = set()
        self.recenter_controller = TactileRecenterController(self.timeline_state, self._move_cursor_to_target)

        self.dialog = q["QDialog"]()
        _enable_standard_window_controls(q, self.dialog)
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
        root.addWidget(self.workspace_splitter, 1)

        self.run_splitter = q["QSplitter"](q["Qt"].Orientation.Horizontal)
        self.run_splitter.setChildrenCollapsible(False)
        self.run_splitter.setHandleWidth(max(7, profile.root_spacing))
        self.workspace_splitter.addWidget(self.run_splitter)

        response_cell = q["QWidget"]()
        response_cell_layout = q["QVBoxLayout"](response_cell)
        response_cell_layout.setContentsMargins(0, 0, 0, 0)
        response_cell_layout.setSpacing(0)
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
        response_cell_layout.addWidget(response_panel, 0, q["Qt"].AlignmentFlag.AlignTop | q["Qt"].AlignmentFlag.AlignHCenter)
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

        data_panel_title = "" if profile.right_stack_mode == "tabs" else "Data Selection"
        data_panel, data_layout = _panel(q, data_panel_title, profile=profile)
        self.data_selection_panel = data_panel
        data_panel.setMinimumWidth(320 if profile.compact else 360)
        data_panel_min_height = 178 if profile.screen_class == "constrained" else max(250, profile.response_panel_side)
        data_panel.setMinimumHeight(data_panel_min_height)
        data_layout.addWidget(_subtitle(q, "Participant Setup"))
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

        def _add_setup_field(row: int, column: int, label: str, widget: Any, *, column_span: int = 1) -> None:
            key = q["QLabel"](label)
            key.setObjectName("metricLabel")
            key.setMinimumHeight(max(16, profile.input_min_height - 8))
            if hasattr(widget, "setMinimumHeight"):
                widget.setMinimumHeight(profile.input_min_height)
            setup_fields.addWidget(key, row, column)
            setup_fields.addWidget(widget, row, column + 1, 1, column_span)

        _add_setup_field(0, 0, "Participant", self.participant_code_combo)
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
                self.participant_code_combo,
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

        self.session_participant_value = _add_session_metric(0, 0, "Participant", self.package.participant_id)
        self.session_blocks_value = _add_session_metric(0, 2, "Blocks", str(len(self.package.blocks)))
        instruction_summary = _instruction_profile_summary(self.package)
        if profile.compact:
            instruction_summary = instruction_summary.replace(" clip(s) preloaded", " clips")
        self.session_duration_value = _add_session_metric(1, 0, "Duration", _format_duration(_package_duration(self.package)))
        self.session_instruction_value = _add_session_metric(1, 2, "Instruction clips", instruction_summary)
        self.session_value = _add_session_metric(2, 0, "Session", self.package.session_id, column_span=3)
        self.session_value.setToolTip(f"Session: {self.package.session_id}\nFolder: {self.package.session_dir}")
        self.folder_value = None
        if not profile.compact:
            self.folder_value = _add_session_metric(3, 0, "Folder", _short_folder_label(self.package.session_dir), column_span=3)
            self.folder_value.setToolTip(str(self.package.session_dir))
            run_plan_row = 4
        else:
            run_plan_row = 3
        self.run_plan_value = _add_session_metric(run_plan_row, 0, "Run plan", "", column_span=3)
        session_grid.setColumnStretch(1, 1)
        session_grid.setColumnStretch(3, 1)
        data_layout.addLayout(session_grid)
        data_layout.addStretch(1)
        _add_operator_panel("Data Selection", data_panel)

        settings_panel_title = "" if profile.right_stack_mode == "tabs" else "Settings"
        settings_panel, settings_layout = _panel(q, settings_panel_title, profile=profile)
        self.settings_panel = settings_panel
        settings_panel.setMinimumWidth(240 if profile.compact else 270)
        settings_panel_min_height = 128 if profile.screen_class == "constrained" else max(180, profile.response_panel_side)
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
        self.topup_checkbox.stateChanged.connect(lambda _state: self._refresh_run_plan())
        settings_layout.addWidget(self.backup_recording_checkbox)
        settings_layout.addWidget(self.topup_checkbox)
        settings_layout.addStretch(1)
        self._pre_run_controls.extend([self.backup_recording_checkbox, self.topup_checkbox])
        _add_operator_panel("Settings", settings_panel)

        self.processing_splitter = q["QSplitter"](q["Qt"].Orientation.Horizontal)
        self.processing_splitter.setChildrenCollapsible(False)
        self.processing_splitter.setHandleWidth(max(7, profile.root_spacing))

        processing_panel, progress_layout = _panel(q, "Experiment Control", profile=profile)
        self.processing_panel = processing_panel
        processing_panel.setMinimumHeight(170 if profile.screen_class == "constrained" else 190)
        processing_panel.setMinimumWidth(360 if profile.compact else 420)
        progress_layout.setSpacing(profile.panel_spacing)
        if profile.screen_class != "constrained":
            progress_layout.addWidget(_subtitle(q, "Block Order"))
        self.block_plan_widget = _create_block_plan_widget(q, self)
        progress_layout.addWidget(self.block_plan_widget)
        self.block_preview_label = q["QLabel"]("Block preview: live schedule")
        self.block_preview_label.setObjectName("mutedLabel")
        self.block_preview_label.setWordWrap(True)
        progress_layout.addWidget(self.block_preview_label)
        if profile.screen_class != "constrained":
            progress_layout.addWidget(_subtitle(q, "Stimulus / Tactile / Click Timeline"))
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
        self.tactile_timeline_widget = _create_tactile_timeline_widget(
            q,
            self.timeline_state,
            profile,
            state_provider=self._timeline_display_state,
        )
        progress_layout.addWidget(self.tactile_timeline_widget)
        self.recenter_status_label = q["QLabel"]("Cursor recenter: waiting")
        self.recenter_status_label.setObjectName("mutedLabel")
        self.recenter_status_label.setWordWrap(True)
        progress_layout.addWidget(self.recenter_status_label)
        if profile.screen_class == "constrained":
            self.recenter_status_label.setVisible(False)
        else:
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
        if profile.screen_class == "constrained":
            self.progress_label.setVisible(False)
            self.progress.setVisible(False)
            self.event_label.setVisible(False)
            self.prewarm_label.setVisible(False)
        progress_layout.addStretch(1)
        self.processing_splitter.addWidget(processing_panel)

        output_panel, output_layout = _panel(q, "Output Summary", profile=profile)
        self.output_panel = output_panel
        output_panel.setMinimumHeight(170 if profile.screen_class == "constrained" else 190)
        output_panel.setMinimumWidth(260 if profile.compact else 320)
        output_layout.setSpacing(profile.panel_spacing)
        self.output_summary = q["QTextEdit"]()
        self.output_summary.setReadOnly(True)
        self.output_summary.setMinimumHeight(profile.output_min_height)
        self.output_summary.setSizePolicy(q["QSizePolicy"].Policy.Expanding, q["QSizePolicy"].Policy.Expanding)
        self.output_summary.setPlainText("Session outputs will appear here after the run.")
        output_layout.addWidget(self.output_summary)
        self.processing_splitter.addWidget(output_panel)
        self.workspace_splitter.addWidget(self.processing_splitter)

        self.workspace_splitter.setStretchFactor(0, 1)
        self.workspace_splitter.setStretchFactor(1, 1)
        self.run_splitter.setStretchFactor(0, 0)
        if profile.right_stack_mode == "tabs":
            self.run_splitter.setStretchFactor(1, 1)
        else:
            self.run_splitter.setStretchFactor(1, 2)
            self.run_splitter.setStretchFactor(2, 1)
        self.processing_splitter.setStretchFactor(0, 2)
        self.processing_splitter.setStretchFactor(1, 1)

        response_column_width = profile.response_panel_side + max(8, profile.root_spacing)
        if profile.right_stack_mode == "tabs":
            self.run_splitter.setSizes([response_column_width, max(420, profile.window_width - response_column_width)])
        else:
            remaining_width = max(620, profile.window_width - response_column_width)
            self.run_splitter.setSizes(
                [
                    response_column_width,
                    max(360, int(remaining_width * 0.58)),
                    max(260, int(remaining_width * 0.42)),
                ]
            )
        top_height = max(profile.response_panel_side, int(profile.window_height * (0.54 if profile.right_stack_mode != "tabs" else 0.48)))
        lower_height = max(180 if profile.screen_class == "constrained" else 210, profile.window_height - top_height)
        self.workspace_splitter.setSizes([top_height, lower_height])
        self.processing_splitter.setSizes([max(440, int(profile.window_width * 0.58)), max(320, int(profile.window_width * 0.42))])

        self.timer = q["QTimer"](self.dialog)
        self.timer.timeout.connect(self._drain)
        self.timer.start(100)
        self.dialog.finished.connect(lambda _code: self._stop())
        self._refresh_run_plan()

    def _timeline_display_state(self) -> TactileTimelineState:
        if self.preview_display_block_index is not None:
            return self.timeline_preview_state
        return self.timeline_state

    def _run_plan_item_by_number(self, display_number: int) -> dict[str, Any] | None:
        target = int(display_number or 0)
        for item in list(getattr(self, "block_plan_items", []) or []):
            if int(item.get("number") or 0) == target:
                return dict(item)
        return None

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
        if hasattr(self, "block_preview_label"):
            if selected:
                self.block_preview_label.setText(f"Block preview: live Block {selected}")
            else:
                self.block_preview_label.setText("Block preview: live schedule")
        if hasattr(self, "block_plan_widget"):
            self.block_plan_widget.update()
        if hasattr(self, "tactile_timeline_widget"):
            self.tactile_timeline_widget.update()

    def _select_block_plan_item(self, display_number: int) -> None:
        number = int(display_number or 0)
        if number <= 0:
            return
        item = self._run_plan_item_by_number(number)
        if item is None:
            return
        self.selected_display_block_index = number
        if self.active_display_block_index == number:
            self._clear_block_preview(selected=number)
            return

        kind = str(item.get("kind") or "")
        if kind == "topup":
            self.preview_display_block_index = number
            self.timeline_preview_state.clear()
            part_label = _part_display_label(str(item.get("part_key") or ""))
            self.block_preview_label.setText(
                f"Block preview: Block {number} top-up | {part_label} missed tactile trials"
            )
            self.block_plan_widget.update()
            self.tactile_timeline_widget.update()
            return

        block = self._block_for_plan_item(item)
        if block is None:
            self.preview_display_block_index = number
            self.timeline_preview_state.clear()
            self.block_preview_label.setText(f"Block preview: Block {number} schedule unavailable")
            self.block_plan_widget.update()
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
            tactile_events=tactile_events,
            trial_segments=trial_segments,
        )
        self.preview_display_block_index = number
        self.block_preview_label.setText(
            f"Block preview: Block {number} | {len(trial_segments)} trials | {len(tactile_events)} tactile cues"
        )
        self.block_plan_widget.update()
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
                session_root=DEFAULT_SESSION_ROOT,
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
        self._clear_participant_details()
        self._refresh_loaded_package_display()
        self._populate_participant_code_combo(self.package.participant_id)
        self.event_label.setText(f"Participant {self.package.participant_id} ready")

    def _clear_participant_details(self) -> None:
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
        self._refresh_run_plan()
        self._update_tactile_timeline_display()

    def _topup_slots_enabled_for_plan(self) -> bool:
        if hasattr(self, "topup_checkbox"):
            try:
                return bool(self.topup_checkbox.isChecked())
            except Exception:
                pass
        return bool(self.enable_missed_trial_topup)

    def _refresh_run_plan(self) -> None:
        include_topup_slots = self._topup_slots_enabled_for_plan()
        standard_count = sum(1 for block in self.package.blocks if not _is_topup_block(block))
        topup_slots = sum(1 for item in _run_plan_items(self.package, include_topup_slots=include_topup_slots) if item["kind"] == "topup")
        total_count = _run_plan_total(self.package, include_topup_slots=include_topup_slots)
        plan_text = _run_plan_text(self.package, include_topup_slots=include_topup_slots)
        if hasattr(self, "run_plan_value"):
            self.run_plan_value.setText(plan_text)
            self.run_plan_value.setToolTip(plan_text)
        self.block_plan_items = _run_plan_items(self.package, include_topup_slots=include_topup_slots)
        if hasattr(self, "block_plan_widget"):
            refresh_height = getattr(self.block_plan_widget, "refresh_layout_height", None)
            if callable(refresh_height):
                refresh_height()
            self.block_plan_widget.update()
        if hasattr(self, "session_blocks_value"):
            if topup_slots:
                self.session_blocks_value.setText(f"{total_count} ({standard_count} standard + {topup_slots} top-up)")
            else:
                self.session_blocks_value.setText(str(standard_count))
        if hasattr(self, "block_chip") and not self._run_active:
            self.block_chip.setText(f"Block -/{total_count}")
        if self.selected_display_block_index is not None:
            valid_numbers = {int(item.get("number") or 0) for item in self.block_plan_items}
            if self.selected_display_block_index not in valid_numbers:
                self._clear_block_preview()

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
        self._refresh_run_plan()
        self._clear_block_preview()
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
        if self.timeline_state.active:
            self.timeline_state.record_click(self.timeline_state.elapsed_s)
            self._update_tactile_timeline_display()
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
            trial_segments=list(payload.get("trial_segments") or []),
        )
        self.planned_tactile_cue_count += len(self.timeline_state.cues)
        anchor = _float_or_none(payload.get("block_schedule_perf_counter"))
        self._timeline_perf_anchor = anchor if anchor is not None else time.perf_counter()
        part_text = str(payload.get("part_number") or "").strip()
        self.part_chip.setText(_part_display_label(part_text) if part_text else "Part -")
        display_index = _payload_display_block_index(payload)
        display_count = _payload_display_block_count(
            payload,
            _run_plan_total(self.package, include_topup_slots=self._topup_slots_enabled_for_plan()),
        )
        if self.active_display_block_index is not None and self.active_display_block_index != display_index:
            self.completed_display_block_indices.add(int(self.active_display_block_index))
        self.active_display_block_index = int(display_index) if display_index else None
        if self.active_display_block_index is not None:
            self._clear_block_preview(selected=self.active_display_block_index)
        if hasattr(self, "block_plan_widget"):
            self.block_plan_widget.update()
        if bool(payload.get("is_topup")):
            self.block_chip.setText(
                f"Block {display_index}/{display_count} (Top-up)" if display_index else f"Block -/{display_count} (Top-up)"
            )
        else:
            self.block_chip.setText(f"Block {display_index}/{display_count}" if display_index else f"Block -/{display_count}")
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
            self.tactile_count_label.setText(f"0 / 0 cues | {self.timeline_state.click_count()} clicks")
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
        self.tactile_count_label.setText(
            f"{self.timeline_state.passed_count()} / {total} cues | {self.timeline_state.click_count()} clicks"
        )
        if not preserve_recenter_message:
            self.recenter_status_label.setText(
                f"Cursor recenter: {self.timeline_state.recentered_count()} / {total} cues"
            )
        self.tactile_timeline_widget.update()

    def _move_cursor_to_target(self, cue: TactileTimelineCue) -> None:
        center = self.target_button.mapToGlobal(self.target_button.rect().center())
        offscreen = self._offscreen_platform()
        mode = "recorded_intent" if offscreen else self._move_os_cursor_to_global_center(int(center.x()), int(center.y()))
        record = {
            "cue_id": cue.cue_id,
            "trial_number": cue.trial_number,
            "trial_uid": cue.trial_uid,
            "time_s": cue.time_s,
            "elapsed_s": self.timeline_state.elapsed_s,
            "mode": mode,
            "x": int(center.x()),
            "y": int(center.y()),
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
                display_index = _payload_display_block_index(dict(payload))
                display_count = _payload_display_block_count(
                    dict(payload),
                    _run_plan_total(self.package, include_topup_slots=self._topup_slots_enabled_for_plan()),
                )
                block_kind = "top-up block" if bool(payload.get("is_topup")) else "Block"
                self.progress_label.setText(
                    f"{block_kind.title()} {display_index}: {payload.get('block_label')}  "
                    f"{elapsed:.1f}/{duration:.1f}s"
                )
                part_number = str(payload.get("part_number") or "").strip()
                if part_number:
                    self.part_chip.setText(_part_display_label(part_number))
                if bool(payload.get("is_topup")):
                    self.block_chip.setText(
                        f"Block {display_index}/{display_count} (Top-up)" if display_index else f"Block -/{display_count} (Top-up)"
                    )
                else:
                    self.block_chip.setText(f"Block {display_index}/{display_count}" if display_index else f"Block -/{display_count}")
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
        if self.active_display_block_index is not None:
            self.completed_display_block_indices.add(int(self.active_display_block_index))
        self.active_display_block_index = None
        if hasattr(self, "block_plan_widget"):
            self.block_plan_widget.update()
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
    _enable_standard_window_controls(q, dialog)
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

    profile_options = finished_profile_options()
    profile_combo = _combo(q, profile_options, current=STUDY5_PROFILE_ID)
    profile_combo.setEnabled(bool(profile_options))
    panel_layout.addWidget(_field_row(q, "Study/profile preset", profile_combo))

    participant_combo = q["QComboBox"]()
    participant_combo.setObjectName("participantCombo")
    panel_layout.addWidget(_field_row(q, "Participant", participant_combo))

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

    def _current_profile() -> str:
        return str(profile_combo.currentData() or "")

    def _refresh_participant_options(preferred: str = "") -> None:
        nonlocal participant_statuses
        profile = _current_profile()
        participants = profile_participant_ids(profile)
        statuses = profile_participant_asset_statuses(profile) if profile else {}
        participant_statuses = statuses
        current = default_profile_participant(
            participants,
            statuses,
            preferred=preferred or str(participant_combo.currentData() or "") or participant_id or "P001",
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

    _refresh_participant_options(participant_id or "P001")

    def _set_busy(busy: bool) -> None:
        latest_button.setEnabled(not busy)
        profile_button.setEnabled((not busy) and bool(profile_options))
        generate_button.setEnabled((not busy) and bool(profile_options))
        range_button.setEnabled((not busy) and bool(profile_options))
        choose_button.setEnabled(not busy)
        close_button.setEnabled(not busy)
        profile_combo.setEnabled((not busy) and bool(profile_options))
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
                dialog.accept()
            elif kind == "generated":
                _refresh_participant_options(_selected_participant())
                prepared = int(payload.get("prepared_count") or 0) if isinstance(payload, dict) else 0
                reused = int(payload.get("reused_count") or 0) if isinstance(payload, dict) else 0
                message.setText(f"Audio assets ready: {prepared} generated, {reused} already available")
                detail_message.setText("")
                _set_busy(False)
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
                _selected_participant(),
                progress_callback=progress_callback,
            ),
        )

    def _open_profile() -> None:
        _start_preparation(
            "Loading selected profile",
            lambda progress_callback: prepare_profile_focus_session(
                str(profile_combo.currentData() or ""),
                _selected_participant(),
                progress_callback=progress_callback,
            ),
        )

    def _generate_selected() -> None:
        participant = _selected_participant()
        if not participant:
            message.setText("Choose a participant before generating assets.")
            return
        _start_preparation(
            f"Generating audio assets for {participant}",
            lambda progress_callback: prepare_profile_audio_assets(
                _current_profile(),
                [participant],
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
        _start_preparation(
            f"Generating audio assets for {len(participants)} participant(s)",
            lambda progress_callback: prepare_profile_audio_assets(
                _current_profile(),
                participants,
                progress_callback=progress_callback,
            ),
            success_kind="generated",
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
    generate_button.clicked.connect(_generate_selected)
    range_button.clicked.connect(_generate_range)
    profile_combo.currentIndexChanged.connect(lambda _index: _refresh_participant_options())
    choose_button.clicked.connect(_choose_manifest)
    cancel_button.clicked.connect(lambda: (preparation_cancel.set(), cancel_button.setEnabled(False), message.setText("Cancelling loading...")))
    close_button.clicked.connect(dialog.reject)
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
