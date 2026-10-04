"""Exercise the installed Windows Planner UI and its private native worker."""

from __future__ import annotations

import argparse
import base64
from contextlib import nullcontext
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import time

import soundfile as sf

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


def native_request(page, method: str, path: str, body: dict | None = None) -> dict:
    response = page.evaluate("""async ({method, path, body}) => {
      const reply = await window.__TAURI_INTERNALS__.invoke('planner_request', {
        request: {method, path, body: body === null ? '' : JSON.stringify(body)}
      });
      if (reply.error) throw new Error(reply.error);
      const bytes = Uint8Array.from(atob(reply.body_base64), char => char.charCodeAt(0));
      return {status: reply.status, data: JSON.parse(new TextDecoder().decode(bytes))};
    }""", {"method": method, "path": path, "body": body})
    assert response["status"] == 200, (path, response)
    return response["data"]


def wait_native_job(page, job_id: str) -> dict:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        status = native_request(page, "GET", f"/api/jobs/{job_id}")
        if status["status"] in {"succeeded", "failed", "cancelled"}:
            assert status["status"] == "succeeded", status
            return status["result"]
        time.sleep(0.25)
    raise TimeoutError(f"Installed Planner job did not finish: {job_id}")


def prove_native_media(page, *, full_profile: bool) -> dict:
    custom = native_request(page, "POST", "/api/templates/__custom__/load", {})
    if full_profile:
        design = custom["design"]
        protocol = design["protocol"]
        design["name"] = "CI installed Planner to Runner"
        protocol.update({
            "soa_values_ms": [10], "spatial_values_cm": [100.0],
            "include_baseline_trials": False, "baseline_strategy": "none",
            "baseline_trial_percentage": 0.0, "include_catch_trials": False,
            "blocks": 1, "participants": 1, "repetitions_per_condition": 1,
            "trial_strips": [{"strip_id": "ci-row", "label": "CI native loom row",
                              "elements": [{"element_id": "ci-loom", "kind": "looming_stimulus",
                                            "label": "Looming Stimulus",
                                            "source_labels": ["CI native loom"], "randomized": True}]}],
        })
        custom = native_request(page, "POST", "/api/design", {"design": design})
    controls = {
        "start_distance_cm": 95.0,
        "end_distance_cm": 15.0,
        "start_rotation_deg": 270.0,
        "end_rotation_deg": 45.0,
        "movement_duration_s": 0.18,
        "start_hold_s": 0.0,
        "end_hold_s": 0.0,
    }
    job = native_request(page, "POST", "/api/stimulus/bake", {
        "participant_id": "",
        "design": custom["design"],
        "trajectory_controls": controls,
        "bake_recipe": {"kind": "generated_noise", "noise_type": "blue", "label": "CI native loom", "gain": 0.7},
    })
    result = wait_native_job(page, job["job_id"])
    assert result["status"] == "rendered_3dti", result
    assert result["source_kind"] == "generated_noise"
    wav = Path(result["wav_path"])
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["render_engine"] == "native-3dti"
    samples, sample_rate = sf.read(wav, dtype="float32", always_2d=True)
    frames, channels = samples.shape
    assert channels in (2, 3) and sample_rate == 44_100 and frames > 0
    assert float(abs(samples[:, :2]).max()) > 0, "Installed 3DTI render produced silent audio"
    if channels == 3:
        assert float(abs(samples[:, 2]).max()) == 0, "Auditory ingredient contains tactile output"
    return {"status": result["status"], "wav_sha256": sha256(wav),
            "channels": channels, "sample_rate": sample_rate, "frames": frames,
            "manifest_sha256": sha256(Path(result["manifest_path"]))}


def prove_native_profile(page, profile_path: Path) -> dict:
    stages = (
        ("trial_sequence_batch", "2_trial_sequence_designs", {}),
        ("audiotactile_trial_batch", "3_tactile_and_baseline_trials", {}),
        ("trial_repetition_pool", "4_trial_repetition_pool", {"default_repetitions": 1}),
        ("block_csv_preview", "5_block_csv_preview", {"block_count": 1}),
    )
    results = []
    for kind, label, options in stages:
        design = native_request(page, "GET", "/api/state")["design"]
        job = native_request(page, "POST", "/api/stimulus/bake", {
            "participant_id": "", "design": design,
            "bake_recipe": {"kind": kind, "label": label, **options},
        })
        result = wait_native_job(page, job["job_id"])
        results.append({"stage": kind, "manifest_sha256": sha256(Path(result["manifest_path"]))})
    accepted = native_request(page, "POST", "/api/block-csv/accept", {})
    assert accepted["block_csv_preview"]["accepted"] is True
    prepared = native_request(page, "POST", "/api/run-sequence/prepare", {
        "design": accepted["design"], "run_setup": {"experiment_structure": "single"},
    })
    assert prepared["project_segments"]["6_experiment_run_setup"]["status"] == "ready"
    state = prepared
    for step in ("stimulus", "trials", "baseline", "block", "schedule"):
        revision = state["custom_workflow"]["review_revision"]
        state = native_request(page, "POST", "/api/design", {
            "workflow_action": {"type": "save_and_continue", "step_id": step,
                                "expected_revision": revision},
        })
        assert state["workflow_action_result"]["advanced"] is True, (step, state)
    assert state["custom_workflow"]["edit_step"] == "run"
    reply = page.evaluate("""async revision => {
      const response = await window.__TAURI_INTERNALS__.invoke('planner_request', {
        request: {method: 'POST', path: '/api/profiles/export-json',
                  body: JSON.stringify({expected_revision: revision})}
      });
      if (response.error) throw new Error(response.error);
      return response;
    }""", state["custom_workflow"]["review_revision"])
    assert reply["status"] == 200, reply
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_bytes(base64.b64decode(reply["body_base64"], validate=True))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["schema"] == "pps-experiment-profile.v1"
    assert profile["assembly"]["blocks"] and profile["files"]
    for item in profile["files"]:
        path = Path(item["path"])
        assert path.is_file() and path.stat().st_size == item["bytes"]
        assert sha256(path) == item["sha256"]
    trial_audio = [Path(item["path"]) for item in profile["files"]
                   if item["path"].lower().endswith(".wav")
                   and sf.info(item["path"]).channels >= 3
                   and sf.info(item["path"]).subtype == "PCM_16"]
    assert trial_audio, "Exported Planner profile has no multichannel trial WAV"
    return {"profile_sha256": sha256(profile_path), "profile_schema": profile["schema"],
            "source_files_verified": len(profile["files"]), "multichannel_pcm16_wavs": len(trial_audio),
            "block_count": len(profile["assembly"]["blocks"]), "stages": results}


def audit(binary: Path, output: Path, commit: str, elevated_policy: bool,
          persistent_data_root: Path | None = None, export_profile_path: Path | None = None) -> None:
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
        if export_profile_path is not None:
            assert persistent_data_root is not None, "The exported profile needs persistent source media"
        if persistent_data_root is not None:
            persistent_data_root.mkdir(parents=True, exist_ok=False)
        state_context = (nullcontext(str(persistent_data_root)) if persistent_data_root is not None
                         else tempfile.TemporaryDirectory(prefix="pps-planner-installed-audit-"))
        with state_context as state_dir:
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
                    report["native_3dti_media"] = prove_native_media(
                        page, full_profile=export_profile_path is not None)
                    if export_profile_path is not None:
                        report["native_profile"] = prove_native_profile(page, export_profile_path)
                    assert not errors, errors
                    report["app_url"] = page.evaluate("location.href")
                    report["passed"] = True
                finally:
                    browser.close()
    finally:
        if process is not None and process.poll() is None:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                           check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    parser.add_argument("--persistent-data-root", type=Path)
    parser.add_argument("--export-profile-path", type=Path)
    args = parser.parse_args()
    audit(args.binary.resolve(), args.output_dir, args.commit, args.elevated_policy,
          args.persistent_data_root, args.export_profile_path)
    print(f"Installed Planner WebView passed: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
