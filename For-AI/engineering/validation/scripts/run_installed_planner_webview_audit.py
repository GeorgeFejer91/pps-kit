"""Exercise the installed Windows Planner UI and its private native worker."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

from playwright.sync_api import expect, sync_playwright

from run_installed_runner_webview_audit import (
    cdp_targets,
    installed_app_url,
    local_debug_port,
    origin_only,
    restore_debug_policy,
    set_debug_policy,
    sha256,
    wait_for_webview,
)


SEGMENTS = ("study", "stimulus", "trials", "baseline", "block", "schedule", "run")


def audit(binary: Path, output: Path, commit: str, elevated_policy: bool) -> None:
    assert os.name == "nt", "Installed Planner audit requires Windows"
    assert binary.is_file(), f"Installed Planner executable is missing: {binary}"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "pps-planner-installed-webview-audit.v1",
        "commit": commit,
        "installed_binary_sha256": sha256(binary),
        "platform": platform.platform(),
        "scope": "installed_local_webview_private_worker_custom_study_and_segment_geometry",
        "passed": False,
        "segments": [],
    }
    previous_policy = None
    policy_set = False
    process = None
    try:
        with tempfile.TemporaryDirectory(prefix="pps-planner-installed-audit-") as state_dir:
            port = local_debug_port()
            if elevated_policy:
                previous_policy = set_debug_policy(binary.name, port)
                policy_set = True
            environment = os.environ.copy()
            environment["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"--remote-debugging-port={port}"
            environment["PPS_TOOLKIT_DATA_ROOT"] = state_dir
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
                try:
                    page = None
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline and page is None:
                        candidates = [candidate for context in browser.contexts for candidate in context.pages]
                        page = next((candidate for candidate in candidates if installed_app_url(candidate.url)
                                     or candidate.locator("#study-segment").count() > 0), None)
                        if page is None:
                            time.sleep(0.25)
                    assert page is not None, "Installed Planner WebView did not appear"
                    page.set_default_timeout(30_000)
                    assert installed_app_url(page.evaluate("location.href"))
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    expect(page.locator("#study-segment")).to_be_visible()
                    expect(page.locator("#connection-status")).to_have_text("connected", timeout=60_000)
                    assert page.evaluate("window.PPSDesignerApp?.isHosted()") is False
                    assert page.locator("#companion-panel .layout-title").inner_text() == "Bundled Planner"
                    page.locator("#start-new-custom-design").click()
                    expect(page.locator("#customize-modal")).to_be_visible()
                    page.locator("#customize-study-name").fill("CI installed Planner study")
                    page.locator("#customize-submit").click()
                    expect(page.locator("#customize-modal")).to_be_hidden(timeout=60_000)
                    assert page.evaluate("window.PPSDesignerApp.getState().design.name") == "CI installed Planner study"
                    report["custom_study_created_through_ui"] = True
                    for segment in SEGMENTS:
                        panel = page.locator(f"#{segment}-segment")
                        panel.scroll_into_view_if_needed()
                        geometry = page.evaluate("""() => ({
                          width: document.documentElement.clientWidth,
                          scrollWidth: document.documentElement.scrollWidth,
                          height: document.documentElement.clientHeight
                        })""")
                        assert geometry["width"] >= 980
                        assert geometry["scrollWidth"] <= geometry["width"] + 1, (segment, geometry)
                        filename = f"segment-{segment}.png"
                        page.screenshot(path=str(output / filename))
                        report["segments"].append({"name": segment, "screenshot": filename, "geometry": geometry})
                    assert not errors, errors
                    report["app_url"] = page.evaluate("location.href")
                    report["passed"] = True
                finally:
                    browser.close()
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        if policy_set:
            restore_debug_policy(binary.name, previous_policy)
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--elevated-policy", action="store_true")
    args = parser.parse_args()
    audit(args.binary.resolve(), args.output_dir, args.commit, args.elevated_policy)
    print(f"Installed Planner WebView passed: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
