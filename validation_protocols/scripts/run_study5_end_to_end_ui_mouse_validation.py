"""Mouse-click UI validation for launching and running the Study 5 profile.

This is an internal UI-behavior validation. It deliberately drives the HTML
dashboard with browser click events and the native Focus Mode runner with Qt
mouse clicks. It avoids dashboard API shortcuts while still replacing hardware
audio playback with a fast callback-compatible fake audio engine, so the script
can run safely on development machines without Komplete ASIO/Woojer hardware.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit import dashboard_app, focus_app  # noqa: E402
from peripersonal_space_toolkit.design import default_design, save_design  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    load_run_package,
)


SCHEMA = "pps-study5-end-to-end-ui-mouse-validation.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "s5_ui_mouse"
STUDY5_TEMPLATE_ID = "study5_box_breathing_pps"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Study 5 dashboard-to-Focus-Mode UI by mouse clicks.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    parser.add_argument("--browser-headed", action="store_true", help="Show the browser instead of using headless Chromium.")
    parser.add_argument("--qt-headed", action="store_true", help="Show the Focus Mode window instead of using Qt offscreen mode.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--focus-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--standalone-launcher", action="store_true", help="Validate the standalone runner profile selector by Qt mouse clicks.")
    parser.add_argument("--packaged-standalone-app", action="store_true", help="Validate the packaged standalone runner exe with OS mouse clicks.")
    parser.add_argument("--packaged-visible-os-clicks", action="store_true", help="Use visible Win32 OS mouse clicks for packaged validation instead of offscreen Qt mouse events.")
    parser.add_argument("--packaged-runner", type=Path, default=REPO_ROOT / "dist" / "PPSExperimentRunner" / "PPSExperimentRunner.exe")
    parser.add_argument("--session-manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--manual-start", action="store_true", help=argparse.SUPPRESS)
    return parser


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Study 5 End-to-End UI Mouse Validation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Dashboard URL: `{report.get('dashboard_url')}`",
        f"- Selected template: `{report.get('selected_template')}`",
        f"- Session manifest: `{report.get('session_manifest')}`",
        f"- Run setup manifest: `{report.get('run_setup_manifest')}`",
        f"- Focus exit code: `{report.get('focus_mode', {}).get('exit_code')}`",
        f"- Focus blocks completed: `{report.get('focus_mode', {}).get('block_end_count')}` / `{report.get('focus_mode', {}).get('block_count')}`",
        f"- Segment 6 external runner process: `{report.get('segment6_external_runner_process')}`",
        f"- Browser clicks: `{len(report.get('browser_clicks', []))}`",
        f"- Focus mouse clicks: `{len(report.get('focus_mode', {}).get('mouse_clicks', []))}`",
        "",
        "This validation uses browser/Qt mouse-click events. It does not use dashboard backend API calls to drive the workflow. Segment 6 launches a separate Focus Mode validation runner process through the normal runner command path. Hardware audio is replaced by a fast fake audio engine, so this proves UI behavior and runner software completion, not physical latency or electrical loopback.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


@dataclass
class DashboardServer:
    controller: dashboard_app.DashboardController
    url: str
    server: Any
    thread: threading.Thread
    runner_cmd_path: Path
    child_report_path: Path
    previous_runner_exe: str | None

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5.0)
        if self.previous_runner_exe is None:
            os.environ.pop("PPS_FOCUS_RUNNER_EXE", None)
        else:
            os.environ["PPS_FOCUS_RUNNER_EXE"] = self.previous_runner_exe


def _write_validation_runner_cmd(path: Path, *, output_dir: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    qt_prefix = "set QT_QPA_PLATFORM=offscreen\r\n"
    command = (
        "@echo off\r\n"
        f"{qt_prefix}"
        f"\"{sys.executable}\" \"{script}\" --focus-child --output-dir \"{output_dir}\" %*\r\n"
    )
    path.write_text(command, encoding="ascii")


def _start_dashboard_server(*, output_dir: Path, host: str, port: int, participant_id: str) -> DashboardServer:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("uvicorn is required for the dashboard UI validation.") from exc

    work_dir = output_dir / "w"
    work_dir.mkdir(parents=True, exist_ok=True)
    runner_cmd = output_dir / "focus_validation_runner.cmd"
    child_report = output_dir / "focus_child_report.json"
    if child_report.exists():
        child_report.unlink()
    _write_validation_runner_cmd(runner_cmd, output_dir=output_dir)
    previous_runner_exe = os.environ.get("PPS_FOCUS_RUNNER_EXE")
    os.environ["PPS_FOCUS_RUNNER_EXE"] = str(runner_cmd)

    design_path = work_dir / "stimulus_design.generated.json"
    if not design_path.exists():
        save_design(default_design(), design_path)

    controller = dashboard_app.DashboardController(
        design_path=design_path,
        render_dir=work_dir / "rendered",
        session_root=work_dir / "sessions",
        import_dir=work_dir / "imports",
        preview_dir=work_dir / "previews",
        project_registry_root=work_dir / "projects",
    )
    controller.participant_id = participant_id
    app = dashboard_app.create_app(controller)
    actual_port = int(port or _free_port(host))
    config = uvicorn.Config(app, host=host, port=actual_port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    def _run() -> None:
        server.run()

    thread = threading.Thread(target=_run, name="pps-study5-dashboard-ui-validation", daemon=True)
    thread.start()
    url = f"http://{host}:{actual_port}"
    deadline = time.time() + 20.0
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1.0) as response:
                if response.status == 200:
                    return DashboardServer(
                        controller=controller,
                        url=url,
                        server=server,
                        thread=thread,
                        runner_cmd_path=runner_cmd,
                        child_report_path=child_report,
                        previous_runner_exe=previous_runner_exe,
                    )
        except Exception as exc:  # pragma: no cover - timing dependent
            last_error = exc
            time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=5.0)
    raise RuntimeError(f"Dashboard server did not become ready: {last_error}")


def _read_json_if_ready(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _click_locator(page: Any, selector: str, label: str, clicks: list[dict[str, Any]], *, timeout_ms: int = 30_000) -> None:
    locator = page.locator(selector).first
    locator.scroll_into_view_if_needed(timeout=timeout_ms)
    locator.click(timeout=timeout_ms)
    clicks.append({"label": label, "selector": selector, "timestamp": datetime.now().isoformat(timespec="milliseconds")})


def _launch_study5_from_dashboard(
    *,
    server: DashboardServer,
    output_dir: Path,
    browser_headed: bool,
    timeout_s: float,
) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Python Playwright is required for the dashboard UI validation.") from exc

    browser_clicks: list[dict[str, Any]] = []
    screenshot_path = output_dir / "dashboard_segment6_launch.png"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not browser_headed)
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.goto(f"{server.url}/dashboard/index.html", wait_until="networkidle", timeout=60_000)
        page.locator("#template-select").wait_for(timeout=30_000)

        _click_locator(page, "#template-select", "click study/profile preload selector", browser_clicks)
        selected_template = page.locator("#template-select").input_value(timeout=30_000)
        if selected_template != STUDY5_TEMPLATE_ID:
            raise RuntimeError(
                f"Expected Study 5 to be the selected preload after clicking the selector; found {selected_template!r}."
            )

        _click_locator(page, '[data-step-link="run"]', "click Segment 6 navigation", browser_clicks)
        page.locator("#prepare-experiment").scroll_into_view_if_needed(timeout=30_000)
        button = page.locator("#prepare-experiment")
        button.wait_for(state="visible", timeout=30_000)
        if not button.is_enabled(timeout=30_000):
            raise RuntimeError("Segment 6 runner launch button is disabled for the Study 5 profile.")
        _click_locator(page, "#prepare-experiment", "click Segment 6 Save Design and Start Experiment Runner", browser_clicks, timeout_ms=int(timeout_s * 1000))

        child_report: dict[str, Any] | None = None
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            package = server.controller.current_run_package
            child_report = _read_json_if_ready(server.child_report_path)
            if package is not None and Path(package.manifest_path).is_file() and child_report is not None:
                break
            time.sleep(0.25)
        package = server.controller.current_run_package
        if package is None:
            raise RuntimeError("Segment 6 click did not prepare a Study 5 session package.")
        if child_report is None:
            raise RuntimeError("Segment 6 did not launch and complete the external Focus Mode validation runner process.")
        page.screenshot(path=str(screenshot_path), full_page=True)
        browser.close()

    state = server.controller.snapshot()
    launch = state.get("experiment_runner_launch_result", {})
    run_setup_manifest = package.source_run_setup_manifest_path
    return {
        "browser_clicks": browser_clicks,
        "dashboard_screenshot": str(screenshot_path),
        "selected_template": state.get("selected_template", ""),
        "run_setup_manifest": str(run_setup_manifest or launch.get("run_setup_manifest") or ""),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "block_count": len(package.blocks),
        "instruction_clip_count": sum(1 for slot in package.instruction_profile.get("slots", []) if slot.get("enabled") and slot.get("path")),
        "segment6_external_runner_process": True,
        "external_focus_child_report": str(server.child_report_path),
        "validation_runner_command_path": str(server.runner_cmd_path),
        "launch_result": launch,
        "focus_mode": child_report.get("focus_mode", {}),
    }


class FastUiAudioEngine:
    """Fast fake engine that emits callback-shaped scheduled events."""

    def __init__(self, *, chunk_frames: int = 441_000) -> None:
        self.chunk_frames = int(chunk_frames)
        self.played_blocks: list[str] = []
        self.played_instructions: list[str] = []
        self._stop_requested = threading.Event()
        self._audio_event_callback = None
        self._play_start_perf = 0.0
        self.sample_rate = 44_100

    def play_instruction(self, path: str, done=None) -> bool:
        self.played_instructions.append(path)
        if done is not None:
            done(True)
        return True

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        import soundfile as sf

        self.played_blocks.append(path)
        info = sf.info(path)
        frames_total = int(info.frames)
        self.sample_rate = int(info.samplerate)
        self._audio_event_callback = audio_event_callback
        self._play_start_perf = time.perf_counter()
        if block_event_schedule is not None:
            block_event_schedule.reset()
            if progress_callback is not None and self.sample_rate > 0:
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
                            "stream_output_buffer_dac_time": now,
                        }
                    )
                    audio_event_callback(payload)
            cursor += frames
            if progress_callback is not None:
                progress_callback(min(cursor, frames_total) / self.sample_rate)
        return not self._stop_requested.is_set()

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        now = time.perf_counter()
        payload = {
            "event_type": "response_marker_start",
            "sample_index": 0,
            "buffer_start_sample": 0,
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


def _event_counts(events_csv: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not events_csv.exists():
        return counts
    with events_csv.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            event_type = str(row.get("event_type") or "")
            counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _run_focus_mode_by_mouse(
    *,
    session_manifest: Path,
    output_dir: Path,
    qt_headed: bool,
    timeout_s: float,
) -> dict[str, Any]:
    if not qt_headed:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtTest import QTest

    q = focus_app._require_qt()
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    package = load_run_package(session_manifest)
    engine = FastUiAudioEngine()
    controller_holder: dict[str, SessionRunnerController] = {}

    def _factory(package_obj: Any, *, capture_options: SessionCaptureOptions, **kwargs: Any) -> SessionRunnerController:
        controller = SessionRunnerController(
            package_obj,
            audio_engine=engine,
            capture_options=capture_options,
            enable_topup=False,
            runner_metadata=kwargs.get("runner_metadata"),
            instruction_continue_callback=kwargs.get("instruction_continue_callback"),
        )
        controller_holder["controller"] = controller
        return controller

    window = focus_app.FocusModeWindow(
        q,
        package,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_internal_xdf=False,
            write_analysis_csvs=True,
            start_backup_recording=False,
        ),
        enable_missed_trial_topup=False,
        controller_factory=_factory,
    )
    mouse_clicks: list[dict[str, Any]] = []

    def _click(widget: Any, label: str) -> None:
        if widget is None or not widget.isEnabled():
            return
        QTest.mouseClick(widget, q["Qt"].MouseButton.LeftButton)
        mouse_clicks.append({"label": label, "timestamp": datetime.now().isoformat(timespec="milliseconds")})

    def _poll_instruction_requests() -> None:
        if window.result is not None:
            window.grab_screenshot(output_dir / "focus_mode_complete.png")
            window.dialog.accept()
            return
        request = window.pending_instruction_request
        if request is not None:
            context = dict(request.get("context") or {})
            mode = str(context.get("mode") or "click")
            if mode == "button":
                _click(window.instruction_button, f"instruction button: {context.get('instruction_label', '')}")
            else:
                _click(window.target_button, f"instruction target: {context.get('instruction_label', '')}")
        q["QTimer"].singleShot(50, _poll_instruction_requests)

    q["QTimer"].singleShot(300, lambda: _click(window.start_button, "Start Run"))
    q["QTimer"].singleShot(450, _poll_instruction_requests)
    exit_code = window.exec(
        fullscreen=bool(qt_headed),
        auto_start=False,
        auto_close_ms=int(timeout_s * 1000),
        screenshot_path=output_dir / "focus_mode_start.png",
    )
    app.processEvents()

    counts = _event_counts(package.session_dir / "events.csv")
    return {
        "exit_code": exit_code,
        "block_count": len(package.blocks),
        "block_start_count": counts.get("block_start", 0),
        "block_end_count": counts.get("block_end", 0),
        "instruction_start_count": counts.get("instruction_start", 0),
        "instruction_continue_count": counts.get("instruction_continue", 0),
        "session_end_count": counts.get("session_end", 0),
        "event_counts": counts,
        "mouse_clicks": mouse_clicks,
        "planned_tactile_cue_count": int(getattr(window, "planned_tactile_cue_count", 0)),
        "cursor_recenter_count": len(getattr(window, "recenter_records", [])),
        "cursor_recenter_records": list(getattr(window, "recenter_records", [])),
        "played_block_count": len(engine.played_blocks),
        "played_instruction_count": len(engine.played_instructions),
        "events_csv": str(package.session_dir / "events.csv"),
        "analysis_summary": str(package.session_dir / "analysis_summary.txt"),
        "session_metadata": str(package.session_dir / "session_metadata.json"),
        "start_screenshot": str(output_dir / "focus_mode_start.png"),
        "complete_screenshot": str(output_dir / "focus_mode_complete.png"),
        "completed": bool(window.result is not None and getattr(window.result, "completed", False)),
    }


def _evaluate_report(report: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if report.get("selected_template") != STUDY5_TEMPLATE_ID:
        failures.append("Study 5 was not the selected dashboard preload.")
    if not Path(str(report.get("session_manifest") or "")).is_file():
        failures.append("Segment 6 did not produce a session manifest.")
    if not Path(str(report.get("run_setup_manifest") or "")).is_file():
        failures.append("Segment 6 did not produce a run setup manifest.")
    if int(report.get("instruction_clip_count") or 0) != 5:
        failures.append("Study 5 did not preload all five original run-level instruction clips.")
    if int(report.get("block_count") or 0) <= 0:
        failures.append("Study 5 session package contains no participant blocks.")
    if not report.get("segment6_external_runner_process"):
        failures.append("Segment 6 did not launch an external Focus Mode runner process.")
    if not Path(str(report.get("external_focus_child_report") or "")).is_file():
        failures.append("External Focus Mode runner process did not write a child validation report.")
    focus = dict(report.get("focus_mode") or {})
    if not focus.get("completed"):
        failures.append("Focus Mode did not report a completed run.")
    if int(focus.get("block_end_count") or 0) != int(focus.get("block_count") or -1):
        failures.append("Focus Mode did not finish every participant block.")
    if int(focus.get("played_instruction_count") or 0) < 5:
        failures.append("Focus Mode did not attempt the preloaded Study 5 instruction clips.")
    if not any(click.get("label") == "Start Run" for click in focus.get("mouse_clicks", [])):
        failures.append("Focus Mode was not started through a mouse click.")
    planned_cues = int(focus.get("planned_tactile_cue_count") or 0)
    recentered_cues = int(focus.get("cursor_recenter_count") or 0)
    if planned_cues <= 0:
        failures.append("Focus Mode did not expose planned tactile cues for the live timeline.")
    elif recentered_cues != planned_cues:
        failures.append(f"Focus Mode recentered {recentered_cues}/{planned_cues} planned tactile cue(s).")
    if not any("Segment 6" in click.get("label", "") for click in report.get("browser_clicks", [])):
        failures.append("Dashboard Segment 6 launch button was not clicked.")
    return not failures, failures


def _run_focus_child(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.session_manifest is None:
        raise RuntimeError("Focus child mode requires --session-manifest.")
    focus_result = _run_focus_mode_by_mouse(
        session_manifest=args.session_manifest,
        output_dir=output_dir,
        qt_headed=bool(args.qt_headed),
        timeout_s=float(args.timeout_s),
    )
    child_report = {
        "schema": f"{SCHEMA}.focus-child",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "session_manifest": str(args.session_manifest),
        "focus_mode": focus_result,
        "passed": bool(focus_result.get("completed")),
        "failures": [] if focus_result.get("completed") else ["Focus Mode did not complete."],
    }
    _write_json(output_dir / "focus_child_report.json", child_report)
    return 0 if child_report["passed"] else 1


def _write_standalone_markdown(path: Path, report: dict[str, Any]) -> None:
    focus = dict(report.get("focus_mode") or {})
    lines = [
        "# Standalone Runner Profile Click Validation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Selected profile: `{report.get('selected_profile')}`",
        f"- Session manifest: `{report.get('session_manifest')}`",
        f"- Focus exit code: `{focus.get('exit_code')}`",
        f"- Focus blocks completed: `{focus.get('block_end_count')}` / `{focus.get('block_count')}`",
        f"- Launcher mouse clicks: `{len(report.get('launcher_mouse_clicks', []))}`",
        f"- Focus mouse clicks: `{len(focus.get('mouse_clicks', []))}`",
        "",
        "This validation opens the standalone Experiment Runner launcher, uses Qt mouse-click events on the finished-profile selector and Run Selected Profile button, then drives Focus Mode with Qt mouse-click events through the Study 5 session. Hardware audio is replaced by a fast fake audio engine.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_standalone_launcher_validation(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    if not args.qt_headed:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtTest import QTest

    q = focus_app._require_qt()
    app = q["QApplication"].instance() or q["QApplication"](sys.argv[:1])
    focus_app.DEFAULT_FOCUS_PROFILE_DESIGN_PATH = output_dir / "focus_profile_runner_design.json"
    focus_app.DEFAULT_PROJECT_REGISTRY_ROOT = output_dir / "projects"
    focus_app.DEFAULT_SESSION_ROOT = output_dir / "sessions"
    focus_app.DEFAULT_RENDER_DIR = output_dir / "rendered"

    launcher_clicks: list[dict[str, Any]] = []
    selected_manifest: dict[str, str] = {}
    focus_holder: dict[str, Any] = {}
    original_run_focus_window = focus_app.run_focus_window

    def _record_click(label: str) -> None:
        launcher_clicks.append({"label": label, "timestamp": datetime.now().isoformat(timespec="milliseconds")})

    def _click_launcher() -> None:
        for widget in app.topLevelWidgets():
            if getattr(widget, "windowTitle", lambda: "")() != "PPS Experiment Runner":
                continue
            combo = next(
                (item for item in widget.findChildren(q["QComboBox"]) if item.findData(STUDY5_TEMPLATE_ID) >= 0),
                None,
            )
            button = next(
                (item for item in widget.findChildren(q["QPushButton"]) if item.text() == "Run Selected Profile"),
                None,
            )
            if combo is not None:
                index = combo.findData(STUDY5_TEMPLATE_ID)
                if index >= 0:
                    combo.setCurrentIndex(index)
                QTest.mouseClick(combo, q["Qt"].MouseButton.LeftButton)
                _record_click("click Study/profile preset selector")
            if button is not None and button.isEnabled():
                QTest.mouseClick(button, q["Qt"].MouseButton.LeftButton)
                _record_click("click Run Selected Profile")
                return
        q["QTimer"].singleShot(100, _click_launcher)

    def _validation_focus_window(session_manifest: Path, **_kwargs: Any) -> int:
        selected_manifest["path"] = str(session_manifest)
        focus_result = _run_focus_mode_by_mouse(
            session_manifest=Path(session_manifest),
            output_dir=output_dir,
            qt_headed=bool(args.qt_headed),
            timeout_s=float(args.timeout_s),
        )
        focus_holder["focus_mode"] = focus_result
        return int(focus_result.get("exit_code") or 0)

    try:
        focus_app.run_focus_window = _validation_focus_window
        q["QTimer"].singleShot(300, _click_launcher)
        exit_code = focus_app.run_launcher_window(
            capture_options=SessionCaptureOptions(
                enable_lsl=False,
                write_internal_xdf=False,
                write_analysis_csvs=True,
                start_backup_recording=False,
            ),
            enable_missed_trial_topup=False,
            participant_id=args.participant_id,
        )
    finally:
        focus_app.run_focus_window = original_run_focus_window

    focus_result = dict(focus_holder.get("focus_mode") or {})
    report = {
        "schema": f"{SCHEMA}.standalone-launcher",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "selected_profile": STUDY5_TEMPLATE_ID,
        "session_manifest": selected_manifest.get("path", ""),
        "launcher_exit_code": exit_code,
        "launcher_mouse_clicks": launcher_clicks,
        "focus_mode": focus_result,
    }
    failures: list[str] = []
    if not any(click.get("label") == "click Study/profile preset selector" for click in launcher_clicks):
        failures.append("Standalone runner profile selector was not clicked.")
    if not any(click.get("label") == "click Run Selected Profile" for click in launcher_clicks):
        failures.append("Standalone runner Run Selected Profile button was not clicked.")
    if not Path(str(report.get("session_manifest") or "")).is_file():
        failures.append("Standalone runner did not prepare a Study 5 session manifest.")
    if not focus_result.get("completed"):
        failures.append("Focus Mode did not complete after standalone runner profile launch.")
    if int(focus_result.get("block_end_count") or 0) != int(focus_result.get("block_count") or -1):
        failures.append("Focus Mode did not finish every block after standalone runner profile launch.")
    if int(focus_result.get("played_instruction_count") or 0) < 5:
        failures.append("Standalone runner Study 5 launch did not play the original instruction profile.")
    planned_cues = int(focus_result.get("planned_tactile_cue_count") or 0)
    recentered_cues = int(focus_result.get("cursor_recenter_count") or 0)
    if planned_cues <= 0:
        failures.append("Standalone runner Focus Mode did not expose planned tactile cues.")
    elif recentered_cues != planned_cues:
        failures.append(f"Standalone runner Focus Mode recentered {recentered_cues}/{planned_cues} planned tactile cue(s).")
    report["passed"] = not failures
    report["failures"] = failures
    _write_json(output_dir / "standalone_runner_profile_click_validation.json", report)
    _write_standalone_markdown(output_dir / "standalone_runner_profile_click_validation.md", report)
    print(f"Wrote standalone runner profile click validation report: {output_dir / 'standalone_runner_profile_click_validation.json'}")
    return 0 if report["passed"] else 1


def _wait_for_windows_window(pid: int, title_fragment: str, *, timeout_s: float) -> int:
    import win32gui
    import win32process

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        matches: list[int] = []

        def _visit(hwnd: int, _extra: object) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            _thread_id, window_pid = win32process.GetWindowThreadProcessId(hwnd)
            if int(window_pid) != int(pid):
                return
            title = win32gui.GetWindowText(hwnd)
            if title_fragment in title:
                matches.append(hwnd)

        win32gui.EnumWindows(_visit, None)
        if matches:
            return matches[0]
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for window {title_fragment!r} from pid {pid}.")


def _client_size(hwnd: int) -> tuple[int, int]:
    import win32gui

    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    return max(1, int(right - left)), max(1, int(bottom - top))


def _raise_windows_window(hwnd: int) -> None:
    import win32con
    import win32gui

    flags = win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE if win32gui.IsIconic(hwnd) else win32con.SW_SHOW)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, flags)
        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, flags)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.15)


def _click_client_fraction(
    hwnd: int,
    x_fraction: float,
    y_fraction: float,
    label: str,
    clicks: list[dict[str, Any]],
) -> None:
    import win32api
    import win32con
    import win32gui

    width, height = _client_size(hwnd)
    client_x = int(round(width * float(x_fraction)))
    client_y = int(round(height * float(y_fraction)))
    screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_x, client_y))
    _raise_windows_window(hwnd)
    win32api.SetCursorPos((screen_x, screen_y))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, screen_x, screen_y, 0, 0)
    time.sleep(0.04)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, screen_x, screen_y, 0, 0)
    clicks.append(
        {
            "label": label,
            "client_fraction": [float(x_fraction), float(y_fraction)],
            "client_point": [client_x, client_y],
            "screen_point": [screen_x, screen_y],
            "timestamp": datetime.now().isoformat(timespec="milliseconds"),
        }
    )


def _save_window_screenshot(hwnd: int, path: Path) -> str:
    import win32gui
    from PIL import ImageGrab

    _raise_windows_window(hwnd)
    rect = win32gui.GetWindowRect(hwnd)
    image = ImageGrab.grab(bbox=rect)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return str(path)


def _write_packaged_standalone_markdown(path: Path, report: dict[str, Any]) -> None:
    focus = dict(report.get("focus_mode") or {})
    launcher = dict(report.get("launcher") or {})
    counts = dict(focus.get("event_counts") or {})
    click_mode = report.get("click_mode") or "unknown"
    selected_profile = launcher.get("selected_profile") or report.get("selected_profile") or ""
    lines = [
        "# Packaged Standalone Runner Mouse Validation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Click mode: `{click_mode}`",
        f"- Runner exe: `{report.get('packaged_runner')}`",
        f"- Process exit code: `{report.get('process_exit_code')}`",
        f"- Selected profile: `{selected_profile}`",
        f"- Session manifest: `{focus.get('session_manifest') or launcher.get('selected_manifest')}`",
        f"- Completed: `{focus.get('completed')}`",
        f"- Blocks completed: `{counts.get('block_end', 0)}`",
        f"- Trial starts/ends: `{counts.get('trial_start', 0)}` / `{counts.get('trial_end', 0)}`",
        f"- Launcher mouse clicks: `{len(report.get('launcher_os_mouse_clicks', []) or launcher.get('validation_mouse_clicks', []))}`",
        f"- Focus validation mouse clicks: `{len(focus.get('validation_mouse_clicks', []))}`",
        "",
        "This validation launches the packaged standalone PPSExperimentRunner.exe, clicks the study/profile selector and Run Selected Profile, and completes Study 5 inside packaged Focus Mode with validation-only mouse events plus a fast fake audio engine.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _enable_process_dpi_awareness() -> None:
    """Keep Win32 click/screenshot coordinates on the same pixel grid."""

    if os.name != "nt":
        return
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    except Exception:
        pass


def _run_packaged_standalone_app_background_validation(args: argparse.Namespace) -> int:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = args.packaged_runner.resolve()
    if not runner.is_file():
        raise FileNotFoundError(f"Packaged runner exe was not found: {runner}")

    focus_report_path = output_dir / "packaged_focus_validation_report.json"
    launcher_report_path = output_dir / "packaged_launcher_validation_report.json"
    for path in (focus_report_path, launcher_report_path):
        if path.exists():
            path.unlink()

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PPS_FOCUS_VALIDATION_FAST_AUDIO"] = "1"
    env["PPS_FOCUS_VALIDATION_AUTO_CLICK"] = "1"
    env["PPS_FOCUS_VALIDATION_LAUNCHER_AUTO_CLICK"] = "1"
    env["PPS_FOCUS_VALIDATION_PROFILE"] = STUDY5_TEMPLATE_ID
    env["PPS_FOCUS_VALIDATION_AUTO_CLOSE_MS"] = str(int(float(args.timeout_s) * 1000))
    env["PPS_FOCUS_VALIDATION_REPORT"] = str(focus_report_path)
    env["PPS_FOCUS_VALIDATION_LAUNCHER_REPORT"] = str(launcher_report_path)

    process = subprocess.Popen(
        [
            str(runner),
            "--launcher",
            "--no-lsl",
            "--no-internal-xdf",
            "--no-backup-recording",
            "--participant-id",
            args.participant_id,
        ],
        cwd=str(REPO_ROOT),
        env=env,
    )
    failures: list[str] = []
    try:
        exit_code = process.wait(timeout=float(args.timeout_s) + 20.0)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            exit_code = process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            exit_code = process.wait(timeout=5.0)
        failures.append("Packaged runner process did not exit after the background validation timeout.")

    launcher_result: dict[str, Any] = {}
    focus_result: dict[str, Any] = {}
    if launcher_report_path.is_file():
        launcher_result = json.loads(launcher_report_path.read_text(encoding="utf-8"))
    else:
        failures.append("Packaged standalone launcher did not write a validation report.")
    if focus_report_path.is_file():
        focus_result = json.loads(focus_report_path.read_text(encoding="utf-8"))
    else:
        failures.append("Packaged Focus Mode did not write a validation report.")

    counts = dict(focus_result.get("event_counts") or {})
    launcher_clicks = list(launcher_result.get("validation_mouse_clicks") or [])
    focus_clicks = list(focus_result.get("validation_mouse_clicks") or [])
    if exit_code != 0:
        failures.append(f"Packaged runner exited with code {exit_code}.")
    if int(launcher_result.get("profile_count") or 0) <= 0:
        failures.append("Packaged standalone launcher did not expose any finished profiles.")
    if launcher_result.get("selected_profile") != STUDY5_TEMPLATE_ID:
        failures.append("Packaged standalone launcher did not select the Study 5 profile.")
    if not any(click.get("label") == "click Study/profile preset selector" for click in launcher_clicks):
        failures.append("Packaged standalone launcher profile selector was not clicked by a validation mouse event.")
    if not any(click.get("label") == "click Run Selected Profile" for click in launcher_clicks):
        failures.append("Packaged standalone launcher Run Selected Profile was not clicked by a validation mouse event.")
    if not focus_result.get("completed"):
        failures.append("Packaged Focus Mode did not complete Study 5.")
    if int(counts.get("block_end") or 0) != 12:
        failures.append("Packaged Focus Mode did not complete all 12 Study 5 blocks.")
    if int(counts.get("trial_start") or 0) != 408 or int(counts.get("trial_end") or 0) != 408:
        failures.append("Packaged Focus Mode did not emit all 408 Study 5 trial starts/ends.")
    if int(focus_result.get("played_instruction_count") or 0) < 5:
        failures.append("Packaged Focus Mode did not attempt all five original Study 5 instruction clips.")
    if not any(click.get("label") == "Start Run" for click in focus_clicks):
        failures.append("Packaged Focus Mode Start Run was not activated by a validation mouse click.")
    planned_cues = int(focus_result.get("planned_tactile_cue_count") or 0)
    recentered_cues = int(focus_result.get("cursor_recenter_count") or 0)
    if planned_cues <= 0:
        failures.append("Packaged Focus Mode did not expose planned tactile cues.")
    elif recentered_cues != planned_cues:
        failures.append(f"Packaged Focus Mode recentered {recentered_cues}/{planned_cues} planned tactile cue(s).")

    report = {
        "schema": f"{SCHEMA}.packaged-standalone-app",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "click_mode": "offscreen_qt_mouse_events",
        "packaged_runner": str(runner),
        "process_exit_code": exit_code,
        "launcher_report": str(launcher_report_path),
        "focus_report": str(focus_report_path),
        "launcher": launcher_result,
        "focus_mode": focus_result,
        "passed": not failures,
        "failures": failures,
    }
    _write_json(output_dir / "packaged_standalone_runner_background_mouse_validation.json", report)
    _write_packaged_standalone_markdown(output_dir / "packaged_standalone_runner_background_mouse_validation.md", report)
    print(f"Wrote packaged standalone runner background mouse validation report: {output_dir / 'packaged_standalone_runner_background_mouse_validation.json'}")
    return 0 if report["passed"] else 1


def _run_packaged_standalone_app_validation(args: argparse.Namespace) -> int:
    if not bool(getattr(args, "packaged_visible_os_clicks", False)):
        return _run_packaged_standalone_app_background_validation(args)

    _enable_process_dpi_awareness()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = args.packaged_runner.resolve()
    if not runner.is_file():
        raise FileNotFoundError(f"Packaged runner exe was not found: {runner}")

    focus_report_path = output_dir / "packaged_focus_validation_report.json"
    if focus_report_path.exists():
        focus_report_path.unlink()
    launcher_clicks: list[dict[str, Any]] = []
    screenshots: dict[str, str] = {}
    env = os.environ.copy()
    env["PPS_FOCUS_VALIDATION_FAST_AUDIO"] = "1"
    env["PPS_FOCUS_VALIDATION_AUTO_CLICK"] = "1"
    env["PPS_FOCUS_VALIDATION_AUTO_CLOSE_MS"] = str(int(float(args.timeout_s) * 1000))
    env["PPS_FOCUS_VALIDATION_REPORT"] = str(focus_report_path)

    process = subprocess.Popen(
        [
            str(runner),
            "--launcher",
            "--no-lsl",
            "--no-internal-xdf",
            "--no-backup-recording",
            "--participant-id",
            args.participant_id,
        ],
        cwd=str(REPO_ROOT),
        env=env,
    )
    exit_code: int | None = None
    focus_result: dict[str, Any] = {}
    failures: list[str] = []
    try:
        launcher_hwnd = _wait_for_windows_window(process.pid, "PPS Experiment Runner", timeout_s=30.0)
        screenshots["launcher_before_click"] = _save_window_screenshot(
            launcher_hwnd, output_dir / "packaged_launcher_before_click.png"
        )
        _click_client_fraction(
            launcher_hwnd,
            0.70,
            0.16,
            "click Study/profile preset selector",
            launcher_clicks,
        )
        time.sleep(0.25)
        screenshots["launcher_after_profile_click"] = _save_window_screenshot(
            launcher_hwnd, output_dir / "packaged_launcher_after_profile_click.png"
        )
        _click_client_fraction(
            launcher_hwnd,
            0.70,
            0.22,
            "click selected Study 5 profile option",
            launcher_clicks,
        )
        time.sleep(0.25)
        screenshots["launcher_after_profile_option_click"] = _save_window_screenshot(
            launcher_hwnd, output_dir / "packaged_launcher_after_profile_option_click.png"
        )
        _click_client_fraction(
            launcher_hwnd,
            0.32,
            0.46,
            "click Run Selected Profile",
            launcher_clicks,
        )
        time.sleep(0.50)
        screenshots["launcher_after_run_profile_click"] = _save_window_screenshot(
            launcher_hwnd, output_dir / "packaged_launcher_after_run_profile_click.png"
        )

        deadline = time.time() + float(args.timeout_s)
        while time.time() < deadline:
            if focus_report_path.is_file():
                break
            if process.poll() is not None:
                break
            time.sleep(0.25)
        if not focus_report_path.is_file() and process.poll() is None:
            screenshots["launcher_after_timeout"] = _save_window_screenshot(
                launcher_hwnd, output_dir / "packaged_launcher_after_timeout.png"
            )
        try:
            exit_code = process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                exit_code = process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                exit_code = process.wait(timeout=5.0)
            failures.append("Packaged runner process did not exit after the validation timeout.")
    finally:
        if process.poll() is None:
            process.terminate()

    if focus_report_path.is_file():
        focus_result = json.loads(focus_report_path.read_text(encoding="utf-8"))
    else:
        failures.append("Packaged Focus Mode did not write a validation report.")

    counts = dict(focus_result.get("event_counts") or {})
    if exit_code != 0:
        failures.append(f"Packaged runner exited with code {exit_code}.")
    if not any(click.get("label") == "click Study/profile preset selector" for click in launcher_clicks):
        failures.append("Standalone launcher profile selector was not clicked with an OS mouse event.")
    if not any(click.get("label") == "click Run Selected Profile" for click in launcher_clicks):
        failures.append("Standalone launcher Run Selected Profile was not clicked with an OS mouse event.")
    if not focus_result.get("completed"):
        failures.append("Packaged Focus Mode did not complete Study 5.")
    if int(counts.get("block_end") or 0) != 12:
        failures.append("Packaged Focus Mode did not complete all 12 Study 5 blocks.")
    if int(counts.get("trial_start") or 0) != 408 or int(counts.get("trial_end") or 0) != 408:
        failures.append("Packaged Focus Mode did not emit all 408 Study 5 trial starts/ends.")
    if int(focus_result.get("played_instruction_count") or 0) < 5:
        failures.append("Packaged Focus Mode did not attempt all five original Study 5 instruction clips.")
    if not any(click.get("label") == "Start Run" for click in focus_result.get("validation_mouse_clicks", [])):
        failures.append("Packaged Focus Mode Start Run was not activated by a validation mouse click.")
    planned_cues = int(focus_result.get("planned_tactile_cue_count") or 0)
    recentered_cues = int(focus_result.get("cursor_recenter_count") or 0)
    if planned_cues <= 0:
        failures.append("Packaged Focus Mode did not expose planned tactile cues.")
    elif recentered_cues != planned_cues:
        failures.append(f"Packaged Focus Mode recentered {recentered_cues}/{planned_cues} planned tactile cue(s).")

    report = {
        "schema": f"{SCHEMA}.packaged-standalone-app",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "click_mode": "visible_win32_os_mouse_events",
        "selected_profile": STUDY5_TEMPLATE_ID,
        "packaged_runner": str(runner),
        "process_exit_code": exit_code,
        "launcher_os_mouse_clicks": launcher_clicks,
        "screenshots": screenshots,
        "focus_report": str(focus_report_path),
        "focus_mode": focus_result,
        "passed": not failures,
        "failures": failures,
    }
    _write_json(output_dir / "packaged_standalone_runner_os_mouse_validation.json", report)
    _write_packaged_standalone_markdown(output_dir / "packaged_standalone_runner_os_mouse_validation.md", report)
    print(f"Wrote packaged standalone runner OS mouse validation report: {output_dir / 'packaged_standalone_runner_os_mouse_validation.json'}")
    return 0 if report["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.focus_child:
        return _run_focus_child(args)
    if args.standalone_launcher:
        return _run_standalone_launcher_validation(args)
    if args.packaged_standalone_app:
        return _run_packaged_standalone_app_validation(args)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    server: DashboardServer | None = None
    try:
        server = _start_dashboard_server(
            output_dir=output_dir,
            host=args.host,
            port=args.port,
            participant_id=args.participant_id,
        )
        dashboard_result = _launch_study5_from_dashboard(
            server=server,
            output_dir=output_dir,
            browser_headed=bool(args.browser_headed),
            timeout_s=float(args.timeout_s),
        )
        report = {
            "schema": SCHEMA,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "dashboard_url": server.url,
            "browser_headed": bool(args.browser_headed),
            "qt_headed": bool(args.qt_headed),
            **dashboard_result,
            "notes": [
                "Workflow driving uses browser and Qt mouse-click events.",
                "Segment 6 launches a separate Focus Mode validation runner process through the normal runner command path; that child process imports the real Focus Mode window and drives it with Qt mouse clicks against the actual Segment 6 session manifest.",
                "The audio engine is a fast callback-compatible fake; this is UI behavior evidence, not hardware/latency evidence.",
            ],
        }
        passed, failures = _evaluate_report(report)
        report["passed"] = passed
        report["failures"] = failures
        _write_json(output_dir / "study5_end_to_end_ui_mouse_validation.json", report)
        _write_markdown(output_dir / "study5_end_to_end_ui_mouse_validation.md", report)
        print(f"Wrote Study 5 UI mouse validation report: {output_dir / 'study5_end_to_end_ui_mouse_validation.json'}")
        return 0 if passed else 1
    finally:
        if server is not None:
            server.stop()


if __name__ == "__main__":
    raise SystemExit(main())
