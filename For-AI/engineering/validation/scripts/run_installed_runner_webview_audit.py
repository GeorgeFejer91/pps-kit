"""Exercise the installed Windows Runner WebView against its real Rust bridge."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import tempfile
import time
import struct
from urllib.parse import urlparse
from urllib.request import ProxyHandler, build_opener
import wave
import winreg

from playwright.sync_api import expect, sync_playwright
from pywinauto import Desktop


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


def synthetic_planner_profile(root: Path) -> Path:
    """Freeze two inventoried Segment 5/6 rows in the Planner's JSON contract."""
    root.mkdir(parents=True, exist_ok=True)
    target = root / "target.wav"
    catch = root / "catch.wav"
    with wave.open(str(target), "wb") as audio:
        audio.setparams((3, 2, 44_100, 0, "NONE", "not compressed"))
        audio.writeframes(bytes(4_000 * 3 * 2))
    with wave.open(str(catch), "wb") as audio:
        audio.setparams((2, 2, 44_100, 0, "NONE", "not compressed"))
        audio.writeframes(bytes(1_000 * 2 * 2))

    block = root / "block.csv"
    fields = ["block_trial_index", "family", "trial_file_path", "source_sha256",
              "looming_segment_onset_s", "tactile_onset_s", "soa_ms", "iti_ms",
              "tactile_waveform_shape", "tactile_frequency_hz", "tactile_duration_ms",
              "tactile_channel"]
    with block.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields)
        writer.writeheader()
        writer.writerow({"block_trial_index": 1, "family": "audio_tactile",
                         "trial_file_path": str(target), "source_sha256": sha256(target),
                         "soa_ms": 50, "iti_ms": 10, "tactile_waveform_shape": "square",
                         "tactile_frequency_hz": 100, "tactile_duration_ms": 10,
                         "tactile_channel": 3})
        writer.writerow({"block_trial_index": 2, "family": "catch",
                         "trial_file_path": str(catch), "source_sha256": sha256(catch),
                         "looming_segment_onset_s": 0, "soa_ms": 0, "iti_ms": 0})
    order = root / "order.csv"
    with order.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=["participant_id", "block_csv_path", "block_label"])
        writer.writeheader()
        writer.writerow({"participant_id": "CI_SYNTHETIC", "block_csv_path": str(block),
                         "block_label": "Synthetic profile block"})
    accepted = root / "accepted.json"
    accepted.write_text('{"accepted": true}', encoding="utf-8")
    setup = root / "setup.json"
    run_setup = {"schema": "pps-experiment-run-setup.v1", "prepared": True,
                 "source_segment5_manifest": str(accepted),
                 "source_segment5_manifest_sha256": sha256(accepted), "csv_path": str(order),
                 "total_block_runs": 1}
    setup.write_text(json.dumps(run_setup), encoding="utf-8")

    def rows(path: Path) -> list[dict[str, str]]:
        with path.open(newline="", encoding="utf-8") as source:
            return list(csv.DictReader(source))

    inventory = []
    for path in (setup, accepted, order, block, target, catch):
        item = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
        if path.suffix == ".wav":
            with wave.open(str(path), "rb") as audio:
                item["audio"] = {"frames": audio.getnframes(), "sample_rate": audio.getframerate(),
                                 "channels": audio.getnchannels(), "format": "WAV"}
        inventory.append(item)
    profile = root / "experiment.json"
    profile.write_text(json.dumps({
        "schema": "pps-experiment-profile.v1", "profile_id": "ci-synthetic",
        "display_name": "Installed synthetic profile", "source_revision": 1, "design": {},
        "run_setup_path": str(setup),
        "assembly": {"run_setup": run_setup, "block_order": rows(order),
                     "blocks": [{"source_csv_path": str(block), "label": "Synthetic profile block",
                                 "rows": rows(block)}]},
        "files": inventory,
    }, indent=2) + "\n", encoding="utf-8")
    return profile


def choose_path_in_native_dialog(process_id: int, path: Path, *, folder: bool = False) -> None:
    """Exercise the app-owned Windows chooser; the WebView never supplies a path."""
    dialog = Desktop(backend="uia").window(process=process_id, class_name="#32770")
    dialog.wait("visible", timeout=30)
    if folder:
        folder_name = dialog.child_window(auto_id="1152", control_type="Edit")
        folder_name.wait("visible", timeout=10)
        folder_name.set_edit_text(str(path))
        dialog.child_window(auto_id="1", control_type="Button").click()
        dialog.wait_not("visible", timeout=15)
    else:
        file_name = dialog.child_window(auto_id="1148", control_type="ComboBox").child_window(
            control_type="Edit"
        )
        file_name.wait("visible", timeout=10)
        file_name.set_edit_text(str(path))
        dialog.child_window(auto_id="1", control_type="Button").click()


def audit(binary: Path, output: Path, commit: str, elevated_policy: bool,
          planner_profile: Path | None = None) -> None:
    assert os.name == "nt", "Installed WebView audit requires Windows"
    assert binary.is_file(), f"Installed executable missing: {binary}"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": "pps-runner-installed-webview-audit.v1",
        "commit": commit,
        "installed_binary_sha256": sha256(binary),
        "platform": platform.platform(),
        "scope": "ci_installed_webview_native_profile_media_package_schedule_and_pcm",
        "physical_output_qualified": False,
        "participant_execution": False,
        "elevated_host_debug_policy": elevated_policy,
        "passed": False,
        "profile_origin": "installed_planner" if planner_profile is not None else "synthetic_fixture",
    }
    process = None
    browser = None
    page = None
    previous_policy = None
    policy_set = False
    fixture = None
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
            page.evaluate("""() => {
                window.installedAuditToasts = [];
                new MutationObserver(() => {
                    const message = document.querySelector('#toast')?.textContent?.trim();
                    if (message && window.installedAuditToasts.at(-1) !== message) {
                        window.installedAuditToasts.push(message);
                    }
                }).observe(document.querySelector('#toast'), {childList: true, characterData: true, subtree: true});
            }""")
            expect(page.locator("#state-chip")).not_to_have_text("Connecting", timeout=30_000)
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
            fixture = tempfile.TemporaryDirectory(prefix="pps-installed-audit-")
            fixture_root = Path(fixture.name)
            participant_id = "CI_PLANNER" if planner_profile is not None else "CI_SYNTHETIC"
            page.locator("#participant-code").fill(participant_id)
            page.locator("#participant-age").fill("30")
            page.locator("#participant-handedness").select_option("right")
            page.locator("#participant-gender").select_option("prefer_not_to_say")
            page.locator("#setup-form button[type=submit]").click()
            expect(page.locator("#prepare-experiment-profile")).to_be_enabled(timeout=10_000)
            setup_snapshot = page.evaluate("window.__TAURI_INTERNALS__.invoke('runner_snapshot')")
            assert setup_snapshot["setup"]["submitted"] is True
            expect(page.locator("#setup-badge")).to_have_text("Submitted")
            report["participant_setup_submitted"] = True

            profile_path = planner_profile or synthetic_planner_profile(fixture_root / "profile")
            assert profile_path.is_file(), f"Planner profile is missing: {profile_path}"
            output_parent = fixture_root / "generated"
            output_parent.mkdir()
            expect(page.locator("#prepare-experiment-profile")).to_be_enabled(timeout=10_000)
            page.locator("#prepare-experiment-profile").click()
            choose_path_in_native_dialog(process.pid, profile_path)
            choose_path_in_native_dialog(process.pid, output_parent, folder=True)
            expect(page.locator("#prepare-experiment-profile")).to_be_enabled(timeout=60_000)
            generated = list(output_parent.glob(f"{participant_id}_*"))
            report["fixture_generated_locations"] = [
                str(path.relative_to(fixture_root)) for path in fixture_root.rglob(f"{participant_id}_*")
            ]
            report["profile_session_id"] = page.evaluate(
                "window.__TAURI_INTERNALS__.invoke('runner_snapshot')"
            )["identity"]["session_id"]
            assert len(generated) == 1 and generated[0].is_dir(), (
                generated, page.evaluate("window.installedAuditToasts || []"),
            )
            expect(page.locator("#package-badge")).to_have_text("Verified", timeout=10_000)
            generated_manifest = generated[0] / "session_manifest.json"
            generated_wav = generated[0] / "blocks" / "Block_01.wav"
            generated_csv = generated[0] / "blocks" / "Block_01.csv"
            assert all(path.is_file() for path in (generated_manifest, generated_wav, generated_csv))
            manifest = json.loads(generated_manifest.read_text(encoding="utf-8"))
            assert manifest["schema"] == "pps-run-session.v1"
            assert manifest["participant_id"] == participant_id
            assert len(manifest["blocks"]) == 1
            with generated_csv.open(newline="", encoding="utf-8") as source:
                generated_rows = list(csv.DictReader(source))
            if planner_profile is None:
                assert manifest["blocks"][0]["trial_count"] == 2
                assert [row["Family"] for row in generated_rows] == ["audio_tactile", "catch"]
                assert generated_rows[0]["Tactile_Waveform_Generated"] == "true"
            else:
                source_profile = json.loads(profile_path.read_text(encoding="utf-8"))
                assert source_profile["schema"] == "pps-experiment-profile.v1"
                assert manifest["blocks"][0]["trial_count"] == len(source_profile["assembly"]["blocks"][0]["rows"])
                assert len(generated_rows) == manifest["blocks"][0]["trial_count"]
                assert any(row["Family"] == "audio_tactile" for row in generated_rows)
            with wave.open(str(generated_wav), "rb") as audio:
                assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (3, 2, 44_100)
                frames = audio.getnframes()
                assert frames > 0
                pcm = audio.readframes(frames)
            samples = struct.unpack(f"<{len(pcm) // 2}h", pcm)
            if planner_profile is None:
                assert frames == 5_441
                assert all(samples[index] == 0 for index in range(0, len(samples), 3))
                assert all(samples[index] == 0 for index in range(1, len(samples), 3))
                assert any(samples[index] != 0 for index in range(2, 4_000 * 3, 3))
                assert all(samples[index] == 0 for index in range(4_441 * 3, len(samples)))
            else:
                assert any(sample != 0 for sample in samples), "Planner media became silent in the Runner package"
            profile_snapshot = page.evaluate("window.__TAURI_INTERNALS__.invoke('runner_snapshot')")
            assert profile_snapshot["package_verified"] is True
            assert profile_snapshot["identity"]["session_id"] == generated[0].name
            assert profile_snapshot["safety"]["local_armed"] is False
            report["planner_profile_sha256"] = sha256(profile_path)
            report["generated_manifest_sha256"] = sha256(generated_manifest)
            report["generated_wav_sha256"] = sha256(generated_wav)
            report["generated_csv_sha256"] = sha256(generated_csv)
            report["generated_wav_frames"] = frames
            report["planner_profile_package_generated"] = True

            expect(page.locator("#inspect-prepared-execution")).to_be_enabled(timeout=10_000)
            page.locator("#inspect-prepared-execution").click()
            expect(page.locator("#execution-inspection-status")).to_have_text(
                "Compiled · inspection only", timeout=30_000,
            )
            report["profile_rust_schedule_compiled"] = True
            expect(page.locator("#prepare-current-audio-block")).to_be_enabled(timeout=10_000)
            page.locator("#prepare-current-audio-block").click()
            expect(page.locator("#prepared-audio-status")).to_have_text(
                "Prepared · output not reserved", timeout=30_000,
            )
            expect(page.locator("#native-output-prepare")).to_be_disabled()
            report["profile_native_pcm_prepared"] = True
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
            try:
                dialog = Desktop(backend="uia").window(process=process.pid, class_name="#32770")
                if dialog.exists(timeout=1):
                    report["native_dialog_on_failure"] = [
                        {"name": control.element_info.name, "id": control.element_info.automation_id,
                         "type": control.element_info.control_type}
                        for control in dialog.descendants()[:80]
                    ]
            except Exception:
                pass
        if page is not None:
            try:
                report["ui_messages_on_failure"] = page.evaluate("window.installedAuditToasts || []")
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
        if fixture is not None:
            fixture.cleanup()
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
    parser.add_argument("--profile-path", type=Path,
                        help="Use the JSON and source media exported by the installed Planner")
    parser.add_argument("--elevated-policy", action="store_true",
                        help="Temporarily set an app-specific HKLM debug-port policy for elevated CI hosts")
    args = parser.parse_args()
    audit(args.binary.resolve(), args.output_dir, args.commit, args.elevated_policy,
          args.profile_path.resolve() if args.profile_path else None)
    print(f"Installed Runner WebView passed: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
