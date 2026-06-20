"""Stress the PySide Focus Mode click-target path without audio hardware."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit import focus_app  # noqa: E402
from peripersonal_space_toolkit.session_runner import RUN_PACKAGE_SCHEMA, SessionCaptureOptions, load_run_package  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exercise PySide Focus Mode clicks with a fake controller.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "artifacts" / "validation_runs" / "focus_mode_click_path_current")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--interval-ms", type=int, default=60)
    parser.add_argument("--offscreen", action="store_true", help="Use Qt offscreen mode for CI/headless smoke runs.")
    parser.add_argument("--fullscreen", action="store_true", help="Show the validation window full-screen.")
    parser.add_argument("--mouse-backend", choices=["qtest", "pynput", "win32", "pyautogui"], default="qtest")
    return parser


def _write_manifest(output_dir: Path) -> Path:
    session_dir = output_dir / "P001_focus_mode_click_stress"
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / "session_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": RUN_PACKAGE_SCHEMA,
                "participant_id": "P001",
                "session_id": "P001_focus_mode_click_stress",
                "created_at": "2026-06-13T12:00:00",
                "session_dir": str(session_dir),
                "design_path": str(session_dir / "design.json"),
                "protocol_path": str(session_dir / "protocol_schedule.csv"),
                "manifest_path": str(manifest_path),
                "render_manifest_path": "",
                "execution_mode": "focus_mode_ui_stress",
                "blocks": [],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


class FakeFocusController:
    def __init__(self, package: Any, *, capture_options: SessionCaptureOptions, run_duration_s: float = 1.5, **_kwargs: Any) -> None:
        self.package = package
        self.capture_options = capture_options
        self.run_duration_s = float(run_duration_s)
        self.clicks: list[dict[str, Any]] = []
        self._stop_requested = False
        self._paused = False

    def run(self, *, progress_callback=None, event_callback=None):
        start = time.perf_counter()
        if event_callback:
            event_callback("Fake Focus Mode stress playback started")
        while (time.perf_counter() - start) < self.run_duration_s and not self._stop_requested:
            if not self._paused and progress_callback:
                elapsed = time.perf_counter() - start
                progress_callback(
                    {
                        "block_index": 1,
                        "block_label": "Fake click-path block",
                        "elapsed_s": elapsed,
                        "duration_s": self.run_duration_s,
                        "session_id": self.package.session_id,
                    }
                )
            time.sleep(0.02)
        completed = not self._stop_requested
        return SimpleNamespace(
            completed=completed,
            interrupted=not completed,
            session_dir=self.package.session_dir,
            events_csv=self.package.session_dir / "events.csv",
            events_xdf=self.package.session_dir / "events.xdf",
            analysis_outputs={},
            summary_text=f"Fake Focus Mode UI stress logged {len(self.clicks)} click(s).",
            warnings=[] if completed else ["Fake controller was stopped."],
            lsl_status={},
            recording_paths=[],
            lsl_markers_csv=None,
            trigger_dictionary_path=None,
            capture_options=self.capture_options.as_dict(),
        )

    def log_click(self, *, in_target: bool = True) -> None:
        self.clicks.append({"index": len(self.clicks) + 1, "in_target": bool(in_target), "perf_counter": time.perf_counter()})

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def stop(self) -> None:
        self._stop_requested = True


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.offscreen:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    q = focus_app._require_qt()
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    from PySide6.QtTest import QTest

    manifest_path = _write_manifest(args.output_dir)
    package = load_run_package(manifest_path)
    controller_holder: dict[str, FakeFocusController] = {}
    mouse_clicks: list[dict[str, Any]] = []

    def _factory(package_obj: Any, *, capture_options: SessionCaptureOptions, **kwargs: Any) -> FakeFocusController:
        controller = FakeFocusController(package_obj, capture_options=capture_options, **kwargs)
        controller_holder["controller"] = controller
        return controller

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(enable_lsl=False, write_internal_xdf=False, start_backup_recording=False),
        controller_factory=_factory,
    )
    screenshot_path = args.output_dir / "focus_mode_click_path_window.png"

    def _mouse_click(widget: Any, label: str) -> None:
        if widget is None or not widget.isEnabled():
            return
        backend = args.mouse_backend
        if backend == "qtest" or args.offscreen:
            QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
            mouse_clicks.append({"label": label, "backend": "qtest", "timestamp_unix": time.time()})
            return
        try:
            window.dialog.raise_()
            window.dialog.activateWindow()
            focus_app._force_foreground_window(window.dialog)
            widget.setFocus(q["Qt"].FocusReason.MouseFocusReason)
            app.processEvents()
            time.sleep(0.05)
            x, y, source = focus_app._widget_screen_center(widget)
            if backend == "pynput":
                from pynput.mouse import Button, Controller

                mouse = Controller()
                mouse.position = (int(x), int(y))
                time.sleep(0.05)
                mouse.press(Button.left)
                time.sleep(0.03)
                mouse.release(Button.left)
            elif backend == "win32":
                import ctypes

                ctypes.windll.user32.SetCursorPos(int(x), int(y))
                time.sleep(0.05)
                ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                time.sleep(0.03)
                ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
            elif backend == "pyautogui":
                import pyautogui  # type: ignore

                pyautogui.FAILSAFE = False
                pyautogui.PAUSE = 0
                pyautogui.click(int(x), int(y))
            app.processEvents()
            time.sleep(0.03)
            app.processEvents()
            mouse_clicks.append({"label": label, "backend": backend, "coordinate_source": source, "x": x, "y": y, "timestamp_unix": time.time()})
        except Exception as exc:
            mouse_clicks.append({"label": label, "backend": backend, "error": str(exc), "timestamp_unix": time.time()})

    def _select_combo_data(combo: Any, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _submit_setup() -> None:
        window.participant_name_input.setText("Mock Participant")
        window.age_input.setText("30")
        _select_combo_data(window.handedness_combo, "right")
        _select_combo_data(window.gender_combo, "prefer_not_to_say")
        _mouse_click(window.setup_submit_button, "Submit setup")

    q["QTimer"].singleShot(250, _submit_setup)
    q["QTimer"].singleShot(450, lambda: _mouse_click(window.start_button, "Start Run"))
    for index in range(max(0, args.count)):
        q["QTimer"].singleShot(
            700 + index * max(1, args.interval_ms),
            lambda index=index: _mouse_click(window.target_button, f"CLICK target {index + 1}"),
        )
    close_after_ms = 2400 + max(0, args.count) * max(1, args.interval_ms)
    exit_code = window.exec(
        fullscreen=bool(args.fullscreen),
        auto_start=False,
        auto_close_ms=close_after_ms,
        screenshot_path=screenshot_path,
    )
    controller = controller_holder.get("controller")
    click_count = len(controller.clicks) if controller is not None else 0
    report = {
        "schema": "pps-focus-mode-click-path-stress.v1",
        "passed": click_count == args.count and window.result is not None,
        "exit_code": exit_code,
        "requested_click_count": args.count,
        "logged_click_count": click_count,
        "click_mode": "qt_mouse_clicks" if args.mouse_backend == "qtest" else "visible_os_mouse_clicks",
        "mouse_backend": args.mouse_backend,
        "mouse_clicks": mouse_clicks,
        "screenshot_path": str(screenshot_path),
        "session_manifest": str(manifest_path),
        "offscreen": bool(args.offscreen),
    }
    report_path = args.output_dir / "focus_mode_click_path_report.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote Focus Mode click-path report: {report_path}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
