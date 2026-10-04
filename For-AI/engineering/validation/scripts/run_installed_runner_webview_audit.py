"""Exercise the installed Windows Runner WebView against its real Rust bridge."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import time
from urllib.parse import urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


def local_debug_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def installed_app_url(url: str) -> bool:
    parsed = urlparse(url)
    return (parsed.scheme == "tauri" and parsed.hostname == "localhost") or (
        parsed.scheme in {"http", "https"} and parsed.hostname == "tauri.localhost"
    )


def wait_for_webview(port: int, process: subprocess.Popen[bytes]) -> dict:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    deadline = time.monotonic() + 60
    last_error = "No WebView2 debugging endpoint yet"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Installed Runner exited before WebView2 connected: {process.returncode}")
        try:
            with urlopen(endpoint, timeout=2) as response:
                return json.load(response)
        except (OSError, ValueError) as error:
            last_error = str(error)
            time.sleep(0.25)
    raise TimeoutError(f"WebView2 debugging endpoint unavailable: {last_error}")


def audit(binary: Path, output: Path, commit: str) -> None:
    assert os.name == "nt", "Installed WebView audit requires Windows"
    assert binary.is_file(), f"Installed executable missing: {binary}"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "pps-runner-installed-webview-audit.v1",
        "commit": commit,
        "installed_binary_sha256": sha256(binary),
        "platform": platform.platform(),
        "scope": "ci_installed_webview_and_native_snapshot",
        "physical_output_qualified": False,
        "participant_execution": False,
        "passed": False,
    }
    process = None
    browser = None
    page = None
    try:
        port = local_debug_port()
        environment = os.environ.copy()
        environment["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={port}"
        process = subprocess.Popen(
            [str(binary)],
            cwd=binary.parent,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        version = wait_for_webview(port, process)
        report["webview2_browser"] = version.get("Browser", "unknown")
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=30_000)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and page is None:
                page = next(
                    (candidate for context in browser.contexts for candidate in context.pages
                     if installed_app_url(candidate.url)),
                    None,
                )
                if page is None:
                    time.sleep(0.25)
            assert page is not None, "No installed Tauri page appeared in WebView2"
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.locator("#participant-code").wait_for(timeout=30_000)
            page.wait_for_function(
                "document.querySelector('#state-chip')?.textContent?.trim() !== 'Connecting'",
                timeout=30_000,
            )
            state = page.locator("#state-chip").inner_text().strip()
            assert state != "Native bridge unavailable", state
            assert page.evaluate("typeof window.__TAURI_INTERNALS__?.invoke") == "function"
            snapshot = page.evaluate("window.__TAURI_INTERNALS__.invoke('runner_snapshot')")
            assert snapshot["schema"] == "pps-runner-authority-snapshot.v1", snapshot.get("schema")
            assert snapshot["package_verified"] is False
            assert snapshot["safety"]["local_armed"] is False
            assert page.locator("#participant-response").is_disabled()
            assert page.locator("#package-badge").inner_text().strip() == "Unverified"
            report["webview_launched"] = True
            report["app_url"] = page.url
            report["native_snapshot_schema"] = snapshot["schema"]
            report["initial_run_phase"] = snapshot["run"]["phase"]
            report["visible_state"] = state
            report["tabs"] = []
            for tab in ("control", "logging", "remote"):
                button = page.locator(f'.tab-button[data-tab="{tab}"]')
                button.click()
                assert button.get_attribute("aria-selected") == "true"
                panel = page.locator(f'.tab-panel[data-panel="{tab}"]')
                assert panel.is_visible()
                assert panel.get_attribute("class") and "is-active" in panel.get_attribute("class").split()
                screenshot = f"{tab}.png"
                page.screenshot(path=str(output / screenshot), full_page=True)
                geometry = page.evaluate("""() => ({
                    width: document.documentElement.clientWidth,
                    scrollWidth: document.documentElement.scrollWidth,
                    height: document.documentElement.clientHeight,
                    scrollHeight: document.documentElement.scrollHeight
                })""")
                report["tabs"].append({"name": tab, "screenshot": screenshot, "geometry": geometry})
                assert geometry["scrollWidth"] <= geometry["width"] + 1, (tab, geometry)
            assert not errors, errors
            report["passed"] = True
            browser.close()
            browser = None
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        if page is not None:
            try:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception:
                pass
        raise
    finally:
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    audit(args.binary.resolve(), args.output_dir, args.commit)
    print(f"Installed Runner WebView passed: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
