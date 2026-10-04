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
from urllib.request import ProxyHandler, build_opener
import winreg

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


def origin_only(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.hostname}" if parsed.hostname else parsed.scheme or "unknown"


def cdp_targets(port: int) -> list[dict[str, str]]:
    try:
        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/json/list", timeout=2) as response:
            return [{"type": item.get("type", ""), "origin": origin_only(item.get("url", ""))}
                    for item in json.load(response)]
    except (OSError, ValueError):
        return []


def wait_for_webview(port: int, process: subprocess.Popen[bytes]) -> dict:
    endpoint = f"http://127.0.0.1:{port}/json/version"
    direct_http = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + 60
    last_error = "No WebView2 debugging endpoint yet"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Installed Runner exited before WebView2 connected: {process.returncode}")
        try:
            with direct_http.open(endpoint, timeout=2) as response:
                return json.load(response)
        except (OSError, ValueError) as error:
            last_error = str(error)
            time.sleep(0.25)
    raise TimeoutError(f"WebView2 debugging endpoint unavailable: {last_error}")


POLICY_KEY = r"SOFTWARE\Policies\Microsoft\Edge\WebView2\AdditionalBrowserArguments"


def set_debug_policy(executable: str, port: int) -> tuple[str, int] | None:
    """Scope the elevated-host CDP override to this executable and save its old value."""
    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, POLICY_KEY, 0,
                            winreg.KEY_QUERY_VALUE | winreg.KEY_SET_VALUE) as key:
        try:
            previous = winreg.QueryValueEx(key, executable)
        except FileNotFoundError:
            previous = None
        winreg.SetValueEx(key, executable, 0, winreg.REG_SZ, f"--remote-debugging-port={port}")
        return previous


def restore_debug_policy(executable: str, previous: tuple[str, int] | None) -> None:
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, POLICY_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if previous is None:
            winreg.DeleteValue(key, executable)
        else:
            winreg.SetValueEx(key, executable, 0, previous[1], previous[0])


def audit(binary: Path, output: Path, commit: str, elevated_policy: bool) -> None:
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
        "elevated_host_debug_policy": elevated_policy,
        "passed": False,
    }
    process = None
    browser = None
    page = None
    previous_policy = None
    policy_set = False
    try:
        port = local_debug_port()
        if elevated_policy:
            previous_policy = set_debug_policy(binary.name, port)
            policy_set = True
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
        report["cdp_targets"] = cdp_targets(port)
        with sync_playwright() as playwright:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=30_000)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and page is None:
                candidates = [candidate for context in browser.contexts for candidate in context.pages]
                report["playwright_page_origins"] = sorted({origin_only(item.url) for item in candidates})
                page = next((item for item in candidates if installed_app_url(item.url)
                             or item.locator("#participant-code").count() > 0), None)
                if page is None:
                    time.sleep(0.25)
            report["cdp_targets"] = cdp_targets(port)
            if page is None:
                report["playwright_page_details"] = []
                for candidate in [item for context in browser.contexts for item in context.pages]:
                    detail = {"reported_origin": origin_only(candidate.url)}
                    try:
                        detail["dom_origin"] = origin_only(candidate.evaluate("location.href"))
                        detail["title"] = candidate.title()
                        detail["has_participant_control"] = candidate.locator("#participant-code").count() > 0
                    except Exception as error:
                        detail["inspection_error"] = type(error).__name__
                    report["playwright_page_details"].append(detail)
            assert page is not None, "No installed Tauri page appeared in WebView2"
            assert installed_app_url(page.evaluate("location.href")), "Playwright attached to an unexpected origin"
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
            next_audio = page.locator("#prepare-current-audio-block")
            assert next_audio.is_visible() and next_audio.is_disabled()
            assert next_audio.inner_text().strip() == "Prepare next audio block"
            next_audio_geometry = next_audio.evaluate("""node => ({
                width: node.clientWidth, scrollWidth: node.scrollWidth,
                height: node.clientHeight, scrollHeight: node.scrollHeight
            })""")
            assert next_audio_geometry["scrollWidth"] <= next_audio_geometry["width"] + 1
            assert next_audio_geometry["scrollHeight"] <= next_audio_geometry["height"] + 1
            report["webview_launched"] = True
            report["next_audio_control_visible"] = True
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
        report["passed"] = False
        report["error"] = f"{type(error).__name__}: {error}"
        report["process_alive_on_failure"] = process is not None and process.poll() is None
        if process is not None:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=2):
                    report["debug_port_accepting_connections"] = True
            except OSError:
                report["debug_port_accepting_connections"] = False
        if page is not None:
            try:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception:
                pass
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        restore_error = None
        if policy_set:
            try:
                restore_debug_policy(binary.name, previous_policy)
            except OSError as error:
                report["passed"] = False
                report["policy_restore_error"] = f"{type(error).__name__}: {error}"
                restore_error = error
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if restore_error is not None:
            raise restore_error


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--elevated-policy", action="store_true",
                        help="Temporarily set an app-specific HKLM debug-port policy for elevated CI hosts")
    args = parser.parse_args()
    audit(args.binary.resolve(), args.output_dir, args.commit, args.elevated_policy)
    print(f"Installed Runner WebView passed: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
