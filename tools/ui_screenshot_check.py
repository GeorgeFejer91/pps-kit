"""Capture and sanity-check PPS Qt designer screenshots."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.qt_designer_app import DEFAULT_DESIGN_PATH, QtStimulusDesigner


EXPECTED_TABS = ("Stimulus Design", "Trial Assembler", "Experiment Runner")
REQUIRED_LABELS = {
    "Starting Point",
    "End Point",
    "Trajectory Preview",
    "Preview mode",
    "3D orbit",
    "Height",
    "Noise Types And Orientations",
    "Custom Audio Preloads",
    "Start hold",
    "End hold",
    "Reset Layout",
    "Maximize Preview",
    "Restore",
}
REQUIRED_TRIAL_ASSEMBLER_LABELS = {
    "Conditions",
    "Trial Families",
    "Block Sequence",
    "Protocol Summary",
    "Trial Table Preview",
    "Participant Block Orders",
    "Add Block",
    "Remove Selected",
    "Export Schedule CSV",
    "Reset Layout",
}
REQUIRED_RUNNER_LABELS = {
    "Prepare",
    "Participant",
    "Stimuli",
    "Session output",
    "Readiness",
    "Audio route",
    "Review",
    "Render",
    "Stress Audio",
    "Start Focus Mode",
    "Reset Layout",
}
FORBIDDEN_LABELS = {
    "SOFA / HRIR Source",
    "SOFA file",
    "Snap To SOFA",
    "Runner Assets",
    "Run Workflow",
    "Participant sequence folder",
    "Instruction audio folder",
    "Loopback recordings folder",
    "Launch Runner",
}
REQUIRED_FOOTER_BUTTONS = {
    "Check",
    "Render Looming WAVs",
    "Export Trajectory",
    "Export Protocol",
    "Save Settings",
    "Load Settings",
    "Save As",
    "Load File",
}
REQUIRED_HEADER_LABELS = {
    "Name",
    "Study profile",
    "Load Profile",
    "Citation",
}
REQUIRED_TEXT_SNIPPETS = (
    "Selected preload paper:",
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Capture visual QA screenshots for the PPS designer UI.")
    parser.add_argument("--design", type=Path, default=DEFAULT_DESIGN_PATH, help="Design JSON to open.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "artifacts" / "ui_verification")
    parser.add_argument("--iterations", type=int, default=1, help="Repeat the tab screenshot loop.")
    parser.add_argument("--delay", type=float, default=0.75, help="Seconds to wait before each capture.")
    parser.add_argument("--geometry", default="1280x820", help="Qt geometry for the verification window.")
    return parser


def safe_name(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def process_events(app: Any, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.02)


def collect_widget_texts(widget: Any) -> list[str]:
    texts: list[str] = []
    for child in widget.findChildren(object):
        text = ""
        if hasattr(child, "text"):
            try:
                text = child.text()
            except TypeError:
                text = ""
        elif hasattr(child, "currentText"):
            text = child.currentText()
        elif hasattr(child, "title"):
            text = child.title()
        if text:
            texts.append(str(text))
    return texts


def inspect_image(path: Path) -> dict[str, Any]:
    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    channel_stddev = [float(value) for value in stat.stddev]
    return {
        "path": str(path),
        "width": image.width,
        "height": image.height,
        "mean_rgb": [float(value) for value in stat.mean],
        "stddev_rgb": channel_stddev,
        "min_stddev_rgb": min(channel_stddev),
        "nonblank": min(channel_stddev) > 2.0,
    }


def grab_widget(widget: Any, path: Path) -> dict[str, int]:
    pixmap = widget.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not pixmap.save(str(path)):
        raise RuntimeError(f"Could not save screenshot: {path}")
    return {"width": pixmap.width(), "height": pixmap.height()}


def wait_for_viewer(designer: QtStimulusDesigner, app: Any, timeout_s: float = 8.0) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ready": False,
        "path_length_m": "",
        "camera_max_polar_angle": "",
        "view_mode": "",
        "height_visible": "",
        "camera_locked_top_down": "",
    }
    deadline = time.monotonic() + timeout_s

    def receive(value: Any) -> None:
        if isinstance(value, str):
            try:
                result.update(json.loads(value))
            except json.JSONDecodeError:
                return
        elif isinstance(value, dict):
            result.update(value)

    script = """
    (() => {
      const state = window.__trajectoryViewerState;
      if (state) {
        return JSON.stringify(state);
      }
      const el = document.getElementById('viewer');
      return JSON.stringify({
        ready: !!el && el.dataset.viewerReady === 'true',
        view_mode: el ? (el.dataset.viewMode || '') : '',
        height_visible: el ? (el.dataset.heightVisible || '') : '',
        camera_locked_top_down: el ? (el.dataset.cameraLockedTopDown || '') : '',
        path_length_m: el ? (el.dataset.pathLengthM || '') : '',
        camera_max_polar_angle: el ? (el.dataset.cameraMaxPolarAngle || '') : ''
      });
    })();
    """
    while time.monotonic() < deadline:
        designer.web_view.page().runJavaScript(script, receive)
        process_events(app, 0.15)
        if result.get("ready"):
            return result
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.iterations < 1:
        raise SystemExit("--iterations must be at least 1")

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        raise SystemExit("PySide6 is required for UI screenshot checks. Install with: pip install -e .[gui]") from exc

    app = QApplication.instance() or QApplication(sys.argv[:1])
    designer = QtStimulusDesigner(args.design)
    width, height = (int(part) for part in args.geometry.lower().split("x", 1))
    designer.window.resize(width, height)
    designer.window.show()
    designer.window.raise_()
    process_events(app, args.delay)

    report: dict[str, Any] = {
        "design": str(args.design),
        "geometry": args.geometry,
        "tabs": [],
        "screenshots": [],
        "layout_actions": {},
        "checks": [],
        "viewer": {},
        "failures": [],
    }

    try:
        report["viewer"] = wait_for_viewer(designer, app)
        if not report["viewer"].get("ready"):
            report["failures"].append("Embedded 3D viewer did not report ready.")
        if report["viewer"].get("view_mode") != "2d":
            report["failures"].append("Designer did not default to 2D bird's-eye preview.")
        try:
            max_polar = float(report["viewer"].get("camera_max_polar_angle") or "nan")
            if max_polar > 1.571:
                report["failures"].append("Camera max polar angle allows below-ground orbit.")
        except ValueError:
            report["failures"].append("Camera max polar angle was not reported.")

        designer.preview_mode.setCurrentText("2D bird's-eye")
        process_events(app, args.delay)
        report["viewer_2d"] = wait_for_viewer(designer, app)
        if report["viewer_2d"].get("view_mode") != "2d":
            report["failures"].append("2D preview mode did not reach the embedded viewer.")
        if report["viewer_2d"].get("height_visible") not in {False, "false", "False"}:
            report["failures"].append("2D preview still reports visible height.")
        if report["viewer_2d"].get("camera_locked_top_down") not in {True, "true", "True"}:
            report["failures"].append("2D preview did not report locked bird's-eye camera.")
        designer.preview_mode.setCurrentText("3D orbit")
        process_events(app, args.delay)
        report["viewer_3d"] = wait_for_viewer(designer, app)
        if report["viewer_3d"].get("view_mode") != "3d":
            report["failures"].append("3D preview mode did not reach the embedded viewer.")
        if report["viewer_3d"].get("height_visible") not in {True, "true", "True"}:
            report["failures"].append("3D preview does not report visible height.")
        if report["viewer_3d"].get("camera_locked_top_down") not in {False, "false", "False"}:
            report["failures"].append("3D preview still reports locked bird's-eye camera.")

        tab_widget = designer.window.findChild(designer.qt["QTabWidget"])
        tab_labels = [tab_widget.tabText(idx) for idx in range(tab_widget.count())] if tab_widget else []
        report["tabs"] = tab_labels
        if tuple(tab_labels) != EXPECTED_TABS:
            report["failures"].append(f"Expected tabs {EXPECTED_TABS}, found {tuple(tab_labels)}")

        if tab_widget:
            tab_widget.setCurrentIndex(0)
            designer._restore_preview()
            process_events(app, args.delay)
            default_sizes = {
                "stimulus_main": designer.stimulus_main_splitter.sizes(),
                "stimulus_right": designer.stimulus_right_splitter.sizes(),
            }
            default_path = args.output_dir / "00_stimulus_default_layout.png"
            grab_widget(designer.window, default_path)
            default_image = inspect_image(default_path)
            designer._maximize_preview()
            process_events(app, args.delay)
            maximized_sizes = {
                "stimulus_main": designer.stimulus_main_splitter.sizes(),
                "stimulus_right": designer.stimulus_right_splitter.sizes(),
            }
            maximized_path = args.output_dir / "00_stimulus_maximized_preview.png"
            grab_widget(designer.window, maximized_path)
            maximized_image = inspect_image(maximized_path)
            designer._restore_preview()
            process_events(app, args.delay)
            restored_sizes = {
                "stimulus_main": designer.stimulus_main_splitter.sizes(),
                "stimulus_right": designer.stimulus_right_splitter.sizes(),
            }
            report["layout_actions"] = {
                "default_sizes": default_sizes,
                "maximized_sizes": maximized_sizes,
                "restored_sizes": restored_sizes,
                "default_screenshot": default_image,
                "maximized_screenshot": maximized_image,
            }
            if not default_image["nonblank"]:
                report["failures"].append("Default stimulus layout screenshot appears blank.")
            if not maximized_image["nonblank"]:
                report["failures"].append("Maximized preview screenshot appears blank.")
            if designer._preview_maximized:
                report["failures"].append("Preview remained maximized after Restore.")
            if not designer.stimulus_controls_pane.isVisible() or not designer.trajectory_controls_pane.isVisible():
                report["failures"].append("Restore did not make stimulus controls visible again.")
            if restored_sizes["stimulus_main"][0] < 100 or restored_sizes["stimulus_right"][0] < 100:
                report["failures"].append("Restore did not return the stimulus workspace to a balanced usable shape.")
            if maximized_sizes["stimulus_main"] == default_sizes["stimulus_main"]:
                report["failures"].append("Maximize Preview did not change the main stimulus splitter sizes.")

        for iteration in range(args.iterations):
            for tab_index, tab_label in enumerate(tab_labels):
                tab_widget.setCurrentIndex(tab_index)
                process_events(app, args.delay)
                shot_path = args.output_dir / f"{iteration + 1:02d}_{safe_name(tab_label)}.png"
                window_metrics = grab_widget(designer.window, shot_path)
                image_metrics = inspect_image(shot_path)
                texts = set(collect_widget_texts(designer.window))
                item = {
                    "iteration": iteration + 1,
                    "tab": tab_label,
                    "window": window_metrics,
                    "image": image_metrics,
                    "texts": sorted(texts),
                }
                report["screenshots"].append(item)

                if not image_metrics["nonblank"]:
                    report["failures"].append(f"{tab_label} screenshot appears blank or nearly blank.")
                if window_metrics["width"] < 1000 or window_metrics["height"] < 650:
                    report["failures"].append(f"{tab_label} window is smaller than the usability baseline.")

                if tab_label == "Stimulus Design":
                    missing = REQUIRED_LABELS - texts
                    if missing:
                        report["failures"].append(f"Stimulus Design is missing visible labels: {sorted(missing)}")
                elif tab_label == "Trial Assembler":
                    missing = REQUIRED_TRIAL_ASSEMBLER_LABELS - texts
                    if missing:
                        report["failures"].append(f"Trial Assembler is missing visible labels: {sorted(missing)}")
                elif tab_label == "Experiment Runner":
                    missing = REQUIRED_RUNNER_LABELS - texts
                    if missing:
                        report["failures"].append(f"Experiment Runner is missing visible labels: {sorted(missing)}")

                forbidden = FORBIDDEN_LABELS & texts
                if forbidden:
                    report["failures"].append(f"{tab_label} exposes forbidden labels: {sorted(forbidden)}")

                missing_header = REQUIRED_HEADER_LABELS - texts
                if missing_header:
                    report["failures"].append(f"{tab_label} is missing visible profile/header controls: {sorted(missing_header)}")
                for snippet in REQUIRED_TEXT_SNIPPETS:
                    if not any(snippet in text for text in texts):
                        report["failures"].append(f"{tab_label} is missing visible text snippet: {snippet}")

                missing_footer = REQUIRED_FOOTER_BUTTONS - texts
                if missing_footer:
                    report["failures"].append(f"{tab_label} is missing visible footer actions: {sorted(missing_footer)}")

        report["checks"].append("Captured all notebook tabs.")
        report["checks"].append("Checked screenshots, visible labels, hidden SOFA panel, WebGL readiness, trial assembler, and integrated runner.")
    finally:
        designer.window.close()
        process_events(app, 0.1)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "ui_screenshot_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {report_path}")
    for item in report["screenshots"]:
        print(f"  {item['tab']}: {item['image']['path']}")
    if report["failures"]:
        print("Failures:")
        for failure in report["failures"]:
            print(f"  - {failure}")
        return 1
    print("UI screenshot checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
