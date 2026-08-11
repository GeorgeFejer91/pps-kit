"""Validate 3D trajectory preview navigation with browser mouse actions."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit import dashboard_app  # noqa: E402
from peripersonal_space_toolkit.design import default_design, save_design  # noqa: E402


SCHEMA = "pps-trajectory-viewer-navigation-validation.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "trajectory_viewer_navigation"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate dashboard trajectory preview 3D navigation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--browser-headed", action="store_true")
    parser.add_argument("--timeout-s", type=float, default=60.0)
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
        "# Trajectory Viewer Navigation Validation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Dashboard URL: `{report.get('dashboard_url')}`",
        f"- Browser clicks: `{len(report.get('browser_clicks', []))}`",
        f"- Screenshots: `{len(report.get('screenshots', []))}`",
        "",
        "This validation drives the visible HTML dashboard and embedded Three.js viewer with browser mouse/keyboard events.",
    ]
    if report.get("failures"):
        lines.extend(["", "## Failures"])
        lines.extend(f"- {failure}" for failure in report["failures"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


@dataclass
class DashboardServer:
    url: str
    server: Any
    thread: threading.Thread

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=5.0)


def _start_dashboard_server(*, output_dir: Path, host: str, port: int) -> DashboardServer:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("uvicorn is required for trajectory viewer validation.") from exc

    work_dir = output_dir / "w"
    work_dir.mkdir(parents=True, exist_ok=True)
    design_path = work_dir / "stimulus_design.generated.json"
    save_design(default_design(), design_path)
    controller = dashboard_app.DashboardController(
        design_path=design_path,
        render_dir=work_dir / "rendered",
        session_root=work_dir / "sessions",
        import_dir=work_dir / "imports",
        preview_dir=work_dir / "previews",
        project_registry_root=work_dir / "projects",
    )
    app = dashboard_app.create_app(controller)
    actual_port = int(port or _free_port(host))
    config = uvicorn.Config(app, host=host, port=actual_port, log_level="warning", access_log=False)
    server = uvicorn.Server(config)

    def _run() -> None:
        server.run()

    thread = threading.Thread(target=_run, name="pps-trajectory-viewer-navigation-validation", daemon=True)
    thread.start()
    url = f"http://{host}:{actual_port}"
    deadline = time.time() + 20.0
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1.0) as response:
                if response.status == 200:
                    return DashboardServer(url=url, server=server, thread=thread)
        except Exception as exc:  # pragma: no cover - timing dependent
            last_error = exc
            time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=5.0)
    raise RuntimeError(f"Dashboard server did not become ready: {last_error}")


def _screenshot_summary(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image, ImageStat
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Pillow is required for screenshot validation.") from exc

    image = Image.open(path).convert("RGB")
    stat = ImageStat.Stat(image)
    stddev = [float(value) for value in stat.stddev]
    return {
        "path": path,
        "width": image.width,
        "height": image.height,
        "stddev": stddev,
        "nonblank": max(stddev) > 2.0,
    }


def _viewer_state(page: Any) -> dict[str, Any]:
    state = page.eval_on_selector(
        "#trajectory-frame",
        """frame => {
          const win = frame.contentWindow;
          const state = win && win.__trajectoryViewerState;
          return state ? JSON.parse(JSON.stringify(state)) : {};
        }""",
    )
    return state if isinstance(state, dict) else {}


def _wait_for_state(page: Any, predicate: Any, label: str, timeout_s: float) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last_state: dict[str, Any] = {}
    while time.time() < deadline:
        last_state = _viewer_state(page)
        if predicate(last_state):
            return last_state
        time.sleep(0.05)
    raise AssertionError(f"Timed out waiting for {label}; last state: {last_state}")


def _click(page: Any, selector: str, label: str, clicks: list[dict[str, Any]]) -> None:
    page.locator(selector).click()
    clicks.append({"selector": selector, "label": label})


def _run_browser_validation(*, server: DashboardServer, output_dir: Path, browser_headed: bool, timeout_s: float) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("Python Playwright is required for trajectory viewer validation.") from exc

    screenshots: list[dict[str, Any]] = []
    clicks: list[dict[str, Any]] = []
    states: dict[str, Any] = {}
    failures: list[str] = []
    dashboard_url = f"{server.url}/dashboard/index.html?page=toolkit&v=20260616-trajectory-nav"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not browser_headed)
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.goto(dashboard_url, wait_until="networkidle")
        page.wait_for_selector("#trajectory-frame")
        _wait_for_state(page, lambda state: state.get("ready") and state.get("view_mode") == "2d", "2D viewer ready", timeout_s)

        _click(page, "#preview-mode-3d", "switch preview to 3D", clicks)
        states["initial_3d"] = _wait_for_state(
            page,
            lambda state: state.get("view_mode") == "3d" and state.get("three_d_pan_enabled") is True,
            "3D viewer ready with pan enabled",
            timeout_s,
        )
        if states["initial_3d"].get("three_d_roll_locked") is not True:
            failures.append("3D viewer did not report roll-locked camera up state.")

        for preset in ("front", "back", "left", "right", "top", "iso"):
            _click(page, f'[data-view-preset="{preset}"]', f"snap {preset} view", clicks)
            states[f"preset_{preset}"] = _wait_for_state(
                page,
                lambda state, preset=preset: state.get("three_d_view_preset") == preset,
                f"{preset} preset state",
                timeout_s,
            )

        before_zoom = float(states["preset_iso"].get("three_d_camera_distance_m") or 0.0)
        _click(page, "#zoom-in-camera", "click 3D zoom in", clicks)
        states["zoom_in"] = _wait_for_state(
            page,
            lambda state: 0 < float(state.get("three_d_camera_distance_m") or 999) < before_zoom,
            "3D zoom-in distance change",
            timeout_s,
        )

        frame = page.frame_locator("#trajectory-frame")
        canvas = frame.locator("canvas")
        # Segment 1 is a taller merged workspace now. Keep the embedded canvas
        # inside the viewport before dispatching page-level mouse coordinates;
        # Playwright does not auto-scroll for raw page.mouse gestures.
        canvas.scroll_into_view_if_needed()
        canvas_box = canvas.bounding_box()
        if not canvas_box:
            raise AssertionError("Could not locate trajectory viewer canvas.")
        before_pan = states["zoom_in"]
        start_x = canvas_box["x"] + canvas_box["width"] * 0.55
        start_y = canvas_box["y"] + canvas_box["height"] * 0.55
        page.keyboard.down("Shift")
        page.mouse.move(start_x, start_y)
        page.mouse.down()
        page.mouse.move(start_x + 130, start_y + 70, steps=10)
        page.mouse.up()
        page.keyboard.up("Shift")
        states["pan"] = _wait_for_state(
            page,
            lambda state: (
                state.get("three_d_target_x_m") != before_pan.get("three_d_target_x_m")
                or state.get("three_d_target_y_m") != before_pan.get("three_d_target_y_m")
                or state.get("three_d_target_z_m") != before_pan.get("three_d_target_z_m")
            ),
            "3D Shift-drag pan target change",
            timeout_s,
        )

        screenshot_path = output_dir / "trajectory_preview_3d_navigation_desktop.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        screenshots.append(_screenshot_summary(screenshot_path))

        page.set_viewport_size({"width": 980, "height": 760})
        page.wait_for_timeout(300)
        narrow_path = output_dir / "trajectory_preview_3d_navigation_narrow.png"
        page.screenshot(path=str(narrow_path), full_page=True)
        screenshots.append(_screenshot_summary(narrow_path))
        browser.close()

    for screenshot in screenshots:
        if not screenshot.get("nonblank"):
            failures.append(f"Screenshot appears blank: {screenshot.get('path')}")

    return {
        "schema": SCHEMA,
        "dashboard_url": dashboard_url,
        "browser_clicks": clicks,
        "states": states,
        "screenshots": screenshots,
        "failures": failures,
        "passed": not failures,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    server = _start_dashboard_server(output_dir=output_dir, host=args.host, port=args.port)
    try:
        report = _run_browser_validation(
            server=server,
            output_dir=output_dir,
            browser_headed=bool(args.browser_headed),
            timeout_s=float(args.timeout_s),
        )
    finally:
        server.stop()
    _write_json(output_dir / "trajectory_viewer_navigation_validation.json", report)
    _write_markdown(output_dir / "trajectory_viewer_navigation_validation.md", report)
    print(f"Wrote trajectory viewer navigation validation report: {output_dir / 'trajectory_viewer_navigation_validation.json'}")
    if report.get("failures"):
        for failure in report["failures"]:
            print(f"FAIL: {failure}")
        return 1
    print("Trajectory viewer navigation validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
