"""Cross-platform native shell for the PPS Experiment Designer."""

from __future__ import annotations

import argparse
import atexit
import base64
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from .dashboard_app import DashboardController, create_app


APP_TITLE = "PPS Experiment Designer"
DEFAULT_PORT = 8766
STATE_ROOT = Path(os.environ.get("PPS_DESIGNER_STATE_ROOT", Path.home() / ".pps-toolkit"))
WINDOW_STATE = STATE_ROOT / "designer-window.json"
INSTANCE_STATE = STATE_ROOT / "designer-instance.json"
INSTANCE_LOCK = STATE_ROOT / "designer-instance.lock"


def _free_port(preferred: int = DEFAULT_PORT) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as handle:
            try:
                handle.bind(("127.0.0.1", port))
            except OSError:
                continue
            return int(handle.getsockname()[1])
    raise RuntimeError("No local port is available for PPS Designer.")


def _read_window_state() -> dict[str, int]:
    try:
        value = json.loads(WINDOW_STATE.read_text(encoding="utf-8"))
        return {
            "width": int(value.get("width", 1480)), "height": int(value.get("height", 900)),
            "x": int(value.get("x", 80)), "y": int(value.get("y", 60)),
        }
    except (OSError, ValueError, TypeError):
        return {"width": 1480, "height": 900, "x": 80, "y": 60}


def _acquire_instance_lock() -> object | None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    handle = INSTANCE_LOCK.open("a+b")
    handle.seek(0)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ImportError):
        handle.close()
        return None
    return handle


def _write_instance(url: str) -> None:
    STATE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary = INSTANCE_STATE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"pid": os.getpid(), "url": url}) + "\n", encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(INSTANCE_STATE)


def _start_server(port: int, token: str) -> object:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("Install the designer extra: pip install -e '.[designer]'") from exc
    app = create_app(
        DashboardController(),
        companion_token=token,
        require_mutation_token=True,
    )
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="pps-designer-backend", daemon=True)
    thread.start()
    health = f"http://127.0.0.1:{port}/api/health"
    for _ in range(100):
        try:
            with urllib.request.urlopen(health, timeout=0.25) as response:
                if response.status == 200:
                    return server
        except OSError:
            time.sleep(0.05)
    server.should_exit = True
    raise RuntimeError("The PPS Designer local service did not become ready.")


class ShellApi:
    def __init__(self) -> None:
        self.window: object | None = None

    def open_external(self, url: str) -> bool:
        parsed = urllib.parse.urlparse(str(url))
        if parsed.scheme not in {"http", "https", "mailto"}:
            return False
        return bool(webbrowser.open(url))

    def save_profile_bundle(self, content_base64: str, suggested_name: str) -> bool:
        if self.window is None:
            return False
        import webview

        name = Path(str(suggested_name)).name
        if not name.endswith(".pps-profile"):
            name += ".pps-profile"
        selected = self.window.create_file_dialog(webview.SAVE_DIALOG, save_filename=name)
        if not selected:
            return False
        destination = Path(selected if isinstance(selected, str) else selected[0])
        destination.write_bytes(base64.b64decode(content_base64, validate=True))
        return True


def _open_native(url: str) -> int:
    try:
        import webview
    except ImportError as exc:
        raise RuntimeError("pywebview is unavailable. Install the designer extra or use --browser.") from exc
    dimensions = _read_window_state()
    shell_api = ShellApi()
    window = webview.create_window(
        APP_TITLE,
        url,
        width=max(980, dimensions["width"]),
        height=max(640, dimensions["height"]),
        min_size=(980, 640),
        x=dimensions["x"],
        y=dimensions["y"],
        confirm_close=False,
        text_select=True,
        js_api=shell_api,
    )
    shell_api.window = window

    def remember() -> None:
        try:
            STATE_ROOT.mkdir(parents=True, exist_ok=True)
            WINDOW_STATE.write_text(
                json.dumps({"width": int(window.width), "height": int(window.height), "x": int(window.x), "y": int(window.y)}) + "\n",
                encoding="utf-8",
            )
        except (OSError, TypeError, ValueError):
            pass

    window.events.closed += remember
    window.events.loaded += lambda: window.evaluate_js("""
      document.addEventListener('click', (event) => {
        const link = event.target.closest('a[href]');
        if (!link) return;
        const target = new URL(link.href, location.href);
        if (target.origin !== location.origin) {
          event.preventDefault();
          window.pywebview.api.open_external(target.href);
        }
      }, true);
    """)
    gui = "edgechromium" if sys.platform == "win32" else "gtk" if sys.platform.startswith("linux") else None
    if hasattr(webview, "settings"):
        webview.settings["ALLOW_DOWNLOADS"] = False
        webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
    webview.start(gui=gui, private_mode=False, storage_path=str(STATE_ROOT / "webview"))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Open PPS Experiment Designer in a native desktop window.")
    parser.add_argument("--browser", action="store_true", help="Use the system browser as an explicit fallback.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    instance_lock = _acquire_instance_lock()
    if instance_lock is None:
        print("PPS Experiment Designer is already running.")
        return 0
    port = _free_port(args.port)
    token = secrets.token_urlsafe(32)
    server = _start_server(port, token)
    bootstrap = f"http://127.0.0.1:{port}/api/bootstrap?{urllib.parse.urlencode({'token': token})}"
    _write_instance(f"http://127.0.0.1:{port}/dashboard/compiled/index.html?desktop=1")

    def stop() -> None:
        server.should_exit = True
        try:
            INSTANCE_STATE.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            instance_lock.close()
        except OSError:
            pass

    atexit.register(stop)
    if args.browser:
        webbrowser.open(bootstrap)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return 0
    try:
        return _open_native(bootstrap)
    except RuntimeError as exc:
        print(f"{exc}\nRun 'pps-designer --browser' for the explicit browser fallback.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
