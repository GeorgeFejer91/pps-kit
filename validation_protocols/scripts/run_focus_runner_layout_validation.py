"""Render and audit Focus Mode layout legibility across screen sizes."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit import focus_app  # noqa: E402
from peripersonal_space_toolkit.focus_layout import (  # noqa: E402
    focus_palette_contrast_report,
    render_focus_layout_profile,
)
from peripersonal_space_toolkit.session_runner import RUN_PACKAGE_SCHEMA, SessionCaptureOptions, load_run_package  # noqa: E402


SCHEMA = "pps-focus-runner-layout-validation.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "focus_runner_layout_current"
DEFAULT_SCENARIOS = [
    ("compact_1024x600", 1024, 600, "window"),
    ("taskbar_1280x720", 1280, 720, "window"),
    ("laptop_1366x768", 1366, 768, "window"),
    ("desktop_1920x1080", 1920, 1080, "window"),
    ("wide_2560x1440", 2560, 1440, "window"),
]
DEFAULT_LAYOUT_VARIANTS = ("default", "operator_wide", "processing_tall")
REQUIRED_TEXT_COMMON = {
    "PPS Experiment Runner",
    "Native Focus Mode",
    "Experiment Running",
    "Participant Response",
    "Experiment Control",
    "Output Summary",
    "Part -",
    "Next tactile: no block schedule",
    "CLICK",
    "Start Run",
    "Pause",
    "Stop",
    "Close",
}
REQUIRED_TEXT_DATA = {"Participant Setup", "Session"}
REQUIRED_TEXT_INSTRUCTIONS_FULL = "5 clip(s) preloaded"
REQUIRED_TEXT_INSTRUCTIONS_COMPACT = "5 clips"
REQUIRED_TEXT_OPERATOR_PANEL = "Data Logging / Experiment Settings"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate the Focus Mode runner layout across common screen sizes.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--offscreen", action="store_true", help="Use Qt offscreen rendering for background validation.")
    parser.add_argument(
        "--screen",
        action="append",
        default=[],
        help="Extra scenario as label:WIDTHxHEIGHT, for example lab_monitor:1920x1040.",
    )
    return parser


def _write_manifest(output_dir: Path) -> Path:
    session_dir = output_dir / "P001_focus_runner_layout"
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / "session_manifest.json"
    blocks = [
        {
            "index": index,
            "label": f"Condition {1 if index <= 6 else 2} Block {((index - 1) % 6) + 1:02d}",
            "manifest_path": str(session_dir / "blocks" / f"block_{index:02d}.csv"),
            "wav_path": str(session_dir / "blocks" / f"block_{index:02d}.wav"),
            "trial_count": 34,
            "duration_s": 272.0,
            "metadata": {
                "part_number": 1 if index <= 6 else 2,
                "phase": "pre" if index <= 6 else "post",
                "phase_label": "Condition 1" if index <= 6 else "Condition 2",
            },
        }
        for index in range(1, 13)
    ]
    payload = {
        "schema": RUN_PACKAGE_SCHEMA,
        "participant_id": "P001",
        "session_id": "P001_focus_runner_layout_validation",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "session_dir": str(session_dir),
        "design_path": str(session_dir / "design.json"),
        "protocol_path": str(session_dir / "protocol_schedule.csv"),
        "manifest_path": str(manifest_path),
        "render_manifest_path": "",
        "execution_mode": "focus_mode_layout_validation",
        "instruction_profile": {
            "schema": "pps-run-instructions.v1",
            "slots": [
                {
                    "slot": "before_experiment",
                    "label": "Before experiment",
                    "enabled": True,
                    "path": "instructions/general.wav",
                    "duration_s": 85.708,
                    "continue_mode": "button",
                    "button_label": "Continue",
                },
                {
                    "slot": "before_block",
                    "label": "Before each block",
                    "enabled": True,
                    "path": "instructions/pre_block.wav",
                    "duration_s": 8.418,
                    "continue_mode": "click",
                },
                {
                    "slot": "after_block",
                    "label": "After each block",
                    "enabled": True,
                    "path": "instructions/post_block.wav",
                    "duration_s": 8.829,
                    "continue_mode": "click",
                },
                {
                    "slot": "between_conditions",
                    "label": "Between conditions",
                    "enabled": True,
                    "path": "instructions/between_conditions.wav",
                    "duration_s": 10.109,
                    "continue_mode": "button",
                    "button_label": "Continue",
                },
                {
                    "slot": "after_experiment",
                    "label": "After experiment",
                    "enabled": True,
                    "path": "instructions/finish.wav",
                    "duration_s": 7.001,
                    "continue_mode": "button",
                    "button_label": "Finish",
                },
            ]
        },
        "blocks": blocks,
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _parse_screen(value: str) -> tuple[str, int, int, str]:
    label, _, geometry = value.partition(":")
    width_text, sep, height_text = geometry.lower().partition("x")
    if not label or sep != "x":
        raise argparse.ArgumentTypeError(f"Invalid screen scenario {value!r}; use label:WIDTHxHEIGHT.")
    try:
        width = int(width_text)
        height = int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid screen dimensions in {value!r}.") from exc
    return label, width, height, "window"


def _process_events(app: Any, seconds: float = 0.15) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def _collect_texts(widget: Any) -> set[str]:
    texts: set[str] = set()
    for child in widget.findChildren(object):
        text = ""
        if hasattr(child, "text"):
            try:
                text = child.text()
            except TypeError:
                text = ""
        elif hasattr(child, "currentText"):
            text = child.currentText()
        if text:
            texts.add(str(text))
    return texts


def _widget_rect(dialog: Any, widget: Any) -> dict[str, int]:
    top_left = widget.mapTo(dialog, widget.rect().topLeft())
    bottom_right = widget.mapTo(dialog, widget.rect().bottomRight())
    return {
        "x": int(top_left.x()),
        "y": int(top_left.y()),
        "right": int(bottom_right.x()),
        "bottom": int(bottom_right.y()),
        "width": int(widget.width()),
        "height": int(widget.height()),
    }


def _inspect_image(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    stddev = [float(value) for value in stat.stddev]
    return {
        "path": str(path),
        "width": image.width,
        "height": image.height,
        "min_stddev_rgb": min(stddev),
        "mean_rgb": [float(value) for value in stat.mean],
        "nonblank": min(stddev) > 2.0,
    }


def _text_from_widget(widget: Any) -> str:
    if hasattr(widget, "text"):
        try:
            return str(widget.text())
        except TypeError:
            return ""
    if hasattr(widget, "currentText"):
        try:
            return str(widget.currentText())
        except TypeError:
            return ""
    return ""


def _audit_text_widgets(window: Any) -> tuple[list[str], dict[str, dict[str, int]]]:
    failures: list[str] = []
    metrics: dict[str, dict[str, int]] = {}
    dialog = window.dialog
    for index, child in enumerate(dialog.findChildren(object)):
        if child is dialog or not hasattr(child, "isVisible") or not child.isVisible():
            continue
        text = _text_from_widget(child).strip()
        if not text:
            continue
        if not hasattr(child, "rect") or not hasattr(child, "mapTo"):
            continue
        rect = _widget_rect(dialog, child)
        key = f"{type(child).__name__}:{text[:48]}:{index}"
        metrics[key] = rect
        if rect["x"] < 0 or rect["y"] < 0 or rect["right"] > dialog.width() or rect["bottom"] > dialog.height():
            failures.append(f"Text widget {text!r} is clipped outside the dialog: {rect}")
        visible = child.visibleRegion().boundingRect()
        if visible.width() <= 0 or visible.height() <= 0:
            failures.append(f"Text widget {text!r} has no visible region.")
            continue
        try:
            font_height = int(child.fontMetrics().height())
        except Exception:
            font_height = 12
        if rect["height"] < max(11, int(font_height * 0.75)):
            failures.append(f"Text widget {text!r} is too short for its font: {rect['height']}px.")
        if rect["width"] < 18:
            failures.append(f"Text widget {text!r} is too narrow to be legible: {rect['width']}px.")
    return failures, metrics


def _audit_window(
    window: Any,
    q: dict[str, Any],
    screenshot_path: Path,
    label: str,
    *,
    show_mode: str,
    layout_variant: str,
) -> dict[str, Any]:
    profile = window.layout_profile
    failures: list[str] = []
    embedded_snapshot = window.layout_validation_snapshot()
    embedded_failures = list(window.layout_validation_failures())
    font_families = set(q["QFontDatabase"].families())
    font_family = focus_app._qt_font_family(q)
    if font_families and font_family not in font_families:
        failures.append(f"Selected Qt font {font_family!r} is not available to this platform.")
    texts = _collect_texts(window.dialog)
    required_text = set(REQUIRED_TEXT_COMMON)
    if profile.screen_class != "constrained":
        required_text.update({"Block Order", "Stimulus / Tactile / Click Timeline", "Progress"})
    if profile.right_stack_mode == "tabs":
        required_text.update(REQUIRED_TEXT_DATA)
        required_text.add(REQUIRED_TEXT_INSTRUCTIONS_COMPACT if profile.compact else REQUIRED_TEXT_INSTRUCTIONS_FULL)
    else:
        required_text.update(REQUIRED_TEXT_DATA)
        required_text.add(REQUIRED_TEXT_OPERATOR_PANEL)
        required_text.add(REQUIRED_TEXT_INSTRUCTIONS_COMPACT if profile.compact else REQUIRED_TEXT_INSTRUCTIONS_FULL)
    missing = sorted(required_text - texts)
    if missing:
        failures.append(f"Missing visible runner text: {missing}")

    required_shortcuts = {
        "start_or_continue": {"Space", "Return", "Enter"},
        "pause_resume": {"Ctrl+P"},
        "stop": {"Ctrl+Shift+S"},
        "close": {"Ctrl+W"},
        "select_part_1": {"Alt+1"},
        "select_part_2": {"Alt+2"},
        "select_topup_preview": {"Ctrl+T"},
    }
    shortcut_map = {
        str(name): {str(item) for item in values}
        for name, values in dict(embedded_snapshot.get("keyboard_shortcuts") or {}).items()
    }
    for name, expected in required_shortcuts.items():
        actual = shortcut_map.get(name, set())
        if not expected.issubset(actual):
            failures.append(f"Keyboard shortcut map for {name} is {sorted(actual)}, expected {sorted(expected)}.")

    if window.dialog.width() > profile.available_width or window.dialog.height() > profile.available_height:
        failures.append(
            f"Window {window.dialog.width()}x{window.dialog.height()} exceeds scenario "
            f"{profile.available_width}x{profile.available_height}."
        )

    critical_widgets = {
        "target_button": window.target_button,
        "start_button": window.start_button,
        "pause_button": window.pause_button,
        "stop_button": window.stop_button,
        "close_button": window.close_button,
        "output_summary": window.output_summary,
        "part_selector_widget": window.part_selector_widget,
        "block_plan_widget": window.block_plan_widget,
        "tactile_timeline_widget": window.tactile_timeline_widget,
        "response_panel": window.response_panel,
        "processing_panel": window.processing_panel,
        "output_panel": window.output_panel,
    }
    if profile.right_stack_mode == "tabs" and layout_variant == "settings_tab":
        critical_widgets["settings_panel"] = window.settings_panel
    elif profile.right_stack_mode == "tabs":
        critical_widgets["data_selection_panel"] = window.data_selection_panel
    else:
        critical_widgets["data_selection_panel"] = window.data_selection_panel
        critical_widgets["settings_panel"] = window.settings_panel
    instruction_widget = getattr(window, "instruction_plan_widget", None) or getattr(window, "instruction_legend_widget", None)
    if instruction_widget is not None and instruction_widget.isVisible():
        critical_widgets["instruction_widget"] = instruction_widget
    if window.topup_draft_widget.isVisible():
        critical_widgets["topup_draft_widget"] = window.topup_draft_widget
    widget_metrics: dict[str, dict[str, int]] = {}
    for name, widget in critical_widgets.items():
        rect = _widget_rect(window.dialog, widget)
        widget_metrics[name] = rect
        if rect["x"] < 0 or rect["y"] < 0 or rect["right"] > window.dialog.width() or rect["bottom"] > window.dialog.height():
            failures.append(f"{name} is clipped outside the dialog: {rect}")
        if widget.visibleRegion().isEmpty():
            failures.append(f"{name} has an empty visible region.")

    if widget_metrics["target_button"]["height"] < profile.target_min_height:
        failures.append(
            f"CLICK target height {widget_metrics['target_button']['height']} is below "
            f"{profile.target_min_height}px."
        )
    if widget_metrics["target_button"]["width"] != widget_metrics["target_button"]["height"]:
        failures.append(f"CLICK target is not square: {widget_metrics['target_button']}.")
    if widget_metrics["target_button"]["height"] != profile.target_min_height:
        failures.append(
            f"CLICK target size {widget_metrics['target_button']['width']}x{widget_metrics['target_button']['height']} "
            f"does not match fixed profile size {profile.target_min_height}px."
        )
    for name in ("start_button", "pause_button", "stop_button", "close_button"):
        if widget_metrics[name]["height"] < profile.button_min_height:
            failures.append(f"{name} height {widget_metrics[name]['height']} is below {profile.button_min_height}px.")
    if widget_metrics["output_summary"]["height"] < profile.output_min_height:
        failures.append("Output Summary is shorter than the profile minimum.")
    if widget_metrics["output_panel"]["y"] < widget_metrics["response_panel"]["bottom"]:
        failures.append("Output Summary is not positioned under the response/click panel.")
    workspace_rect = _widget_rect(window.dialog, window.workspace_splitter)
    if widget_metrics["processing_panel"]["width"] < workspace_rect["width"] - 8:
        failures.append("Experiment Control does not span the full lower workspace width.")
    if widget_metrics["processing_panel"]["height"] < profile.experiment_control_min_height:
        failures.append(
            "Experiment Control height "
            f"{widget_metrics['processing_panel']['height']} is below profile minimum "
            f"{profile.experiment_control_min_height}."
        )

    for segment_name in ("response_panel", "data_selection_panel", "settings_panel", "processing_panel", "output_panel"):
        if segment_name not in widget_metrics:
            continue
        min_segment_height = 60 if segment_name == "output_panel" and profile.screen_class == "constrained" else 80
        if widget_metrics[segment_name]["height"] < min_segment_height:
            failures.append(f"{segment_name} is too short to operate: {widget_metrics[segment_name]}")
        if widget_metrics[segment_name]["width"] < 220:
            failures.append(f"{segment_name} is too narrow to operate: {widget_metrics[segment_name]}")

    splitter_metrics = {}
    splitter_names = ["workspace_splitter", "run_splitter"]
    for name in splitter_names:
        splitter = getattr(window, name, None)
        if splitter is None:
            failures.append(f"Missing resizable splitter {name}.")
            continue
        splitter_metrics[name] = {
            "width": int(splitter.width()),
            "height": int(splitter.height()),
            "count": int(splitter.count()),
            "handle_width": int(splitter.handleWidth()),
        }
        if splitter.handleWidth() < 6:
            failures.append(f"{name} handle is too small to drag comfortably.")
    if profile.right_stack_mode == "tabs":
        tabs = getattr(window, "operator_tabs", None)
        if tabs is None:
            failures.append("Missing constrained-screen Data/Settings tabs.")
        else:
            splitter_metrics["operator_tabs"] = {
                "width": int(tabs.width()),
                "height": int(tabs.height()),
                "count": int(tabs.count()),
                "current_index": int(tabs.currentIndex()),
            }
            if tabs.count() < 1:
                failures.append("Constrained operator tab set does not expose the merged Data Logging / Experiment Settings panel.")

    text_failures, text_metrics = _audit_text_widgets(window)
    failures.extend(text_failures)
    for failure in embedded_failures:
        embedded_message = f"Embedded layout audit: {failure}"
        if embedded_message not in failures:
            failures.append(embedded_message)

    screenshot = _inspect_image(screenshot_path)
    if not screenshot["nonblank"]:
        failures.append(f"Screenshot appears blank for {label}.")
    device_pixel_ratio = float(window.dialog.devicePixelRatioF())
    expected_width = int(round(window.dialog.width() * device_pixel_ratio))
    expected_height = int(round(window.dialog.height() * device_pixel_ratio))
    width_matches = min(abs(screenshot["width"] - window.dialog.width()), abs(screenshot["width"] - expected_width)) <= 2
    height_matches = min(abs(screenshot["height"] - window.dialog.height()), abs(screenshot["height"] - expected_height)) <= 2
    if not width_matches or not height_matches:
        failures.append("Screenshot dimensions do not match the rendered dialog or its high-DPI scale.")

    return {
        "label": label,
        "show_mode": show_mode,
        "layout_variant": layout_variant,
        "passed": not failures,
        "failures": failures,
        "layout_profile": profile.as_dict(),
        "dialog": {
            "width": window.dialog.width(),
            "height": window.dialog.height(),
            "device_pixel_ratio": device_pixel_ratio,
        },
        "font": {
            "selected_family": font_family,
            "available_family_count": len(font_families),
            "availability_checked": bool(font_families),
        },
        "widgets": widget_metrics,
        "splitters": splitter_metrics,
        "embedded_layout_snapshot": embedded_snapshot,
        "text_widgets_checked": len(text_metrics),
        "screenshot": screenshot,
        "visible_text_count": len(texts),
    }


def _scenario_list(app: Any, requested: list[str]) -> list[tuple[str, int, int, str]]:
    scenarios: list[tuple[str, int, int, str]] = []
    screen = app.primaryScreen()
    if screen is not None:
        geometry = screen.availableGeometry()
        scenarios.append(("pc_available_screen_maximized", int(geometry.width()), int(geometry.height()), "maximized"))
        scenarios.append(("pc_available_screen_windowed", int(geometry.width()), int(geometry.height()), "window"))
    scenarios.extend(DEFAULT_SCENARIOS)
    scenarios.extend(_parse_screen(value) for value in requested)

    seen: set[tuple[int, int, str]] = set()
    unique: list[tuple[str, int, int, str]] = []
    for label, width, height, show_mode in scenarios:
        key = (width, height, show_mode)
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, width, height, show_mode))
    return unique


def _apply_layout_variant(window: Any, variant: str) -> None:
    width = max(1, int(window.dialog.width()))
    height = max(1, int(window.dialog.height()))
    workspace_height = max(1, int(window.workspace_splitter.height()))
    tabs = getattr(window, "operator_tabs", None)
    if variant == "settings_tab" and tabs is not None:
        tabs.setCurrentIndex(1)
        return
    if variant == "operator_wide":
        if window.run_splitter.count() >= 3:
            response_width = max(getattr(window.layout_profile, "response_panel_side", 280), int(width * 0.24))
            remaining_width = max(1, width - response_width)
            window.run_splitter.setSizes([response_width, int(remaining_width * 0.68), int(remaining_width * 0.32)])
        else:
            window.run_splitter.setSizes([max(280, int(width * 0.32)), max(420, int(width * 0.68))])
    elif variant == "processing_tall":
        window.workspace_splitter.setSizes([max(280, int(workspace_height * 0.48)), max(220, int(workspace_height * 0.52))])


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Focus Runner Layout Validation",
        "",
        f"- Created: `{report['created_at']}`",
        f"- Passed: `{report['passed']}`",
        f"- Offscreen: `{report['offscreen']}`",
        "",
        "## Scenarios",
    ]
    for scenario in report["scenarios"]:
        lines.append(
            f"- `{scenario['label']}`: `{scenario['dialog']['width']}x{scenario['dialog']['height']}` "
            f"inside `{scenario['layout_profile']['available_width']}x{scenario['layout_profile']['available_height']}`, "
            f"profile `{scenario['layout_profile']['screen_class']}`, "
            f"mode `{scenario['show_mode']}`, variant `{scenario['layout_variant']}`, passed `{scenario['passed']}`"
        )
        if scenario["failures"]:
            lines.extend(f"  - {failure}" for failure in scenario["failures"])
    lines.append("")
    lines.append("## Screenshots")
    for scenario in report["scenarios"]:
        lines.append(f"- `{scenario['label']}`: `{scenario['screenshot']['path']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    q = focus_app._require_qt()
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    app.setStyleSheet(focus_app._focus_style_sheet(q, focus_app.DEFAULT_FOCUS_LAYOUT_PROFILE))
    package = load_run_package(_write_manifest(output_dir))

    scenarios: list[dict[str, Any]] = []
    for label, width, height, show_mode in _scenario_list(app, args.screen):
        profile = render_focus_layout_profile(width, height)
        variants = ("default", "processing_tall") if profile.right_stack_mode == "tabs" else DEFAULT_LAYOUT_VARIANTS
        for variant in variants:
            window = focus_app.FocusModeWindow(
                q,
                package,
                capture_options=SessionCaptureOptions(
                    enable_lsl=False,
                    write_internal_xdf=True,
                    write_analysis_csvs=True,
                    start_backup_recording=False,
                ),
                enable_missed_trial_topup=True,
                layout_profile=profile,
            )
            window.dialog.resize(profile.window_width, profile.window_height)
            if show_mode == "maximized":
                window.dialog.showMaximized()
            else:
                window.dialog.show()
            _process_events(app, 0.2)
            _apply_layout_variant(window, variant)
            _process_events(app, 0.2)
            screenshot_label = f"{label}_{variant}"
            screenshot_path = output_dir / f"{screenshot_label}.png"
            window.grab_screenshot(screenshot_path)
            _process_events(app, 0.05)
            scenarios.append(
                _audit_window(
                    window,
                    q,
                    screenshot_path,
                    screenshot_label,
                    show_mode=show_mode,
                    layout_variant=variant,
                )
            )
            window.dialog.close()
            _process_events(app, 0.05)

    contrast_report = focus_palette_contrast_report()
    contrast_failures = [
        f"{name} contrast {value:.2f} is below 4.5"
        for name, value in contrast_report.items()
        if value < 4.5
    ]
    passed = all(item["passed"] for item in scenarios) and not contrast_failures
    report = {
        "schema": SCHEMA,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "passed": passed,
        "offscreen": bool(args.offscreen),
        "contrast": contrast_report,
        "contrast_failures": contrast_failures,
        "scenarios": scenarios,
    }
    report_path = output_dir / "focus_runner_layout_validation.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    _write_markdown(output_dir / "focus_runner_layout_validation.md", report)
    print(f"Wrote Focus runner layout validation report: {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
