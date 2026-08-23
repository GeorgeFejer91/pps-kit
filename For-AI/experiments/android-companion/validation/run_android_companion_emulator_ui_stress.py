"""Drive the Android runner companion through emulator UI stress scenarios.

This validation script intentionally uses visible Android UI labels plus ADB
tap/text input. It proves what an operator can do through the app surface and
also records whether the current source tree has the optional native Android
LSL runner/controller hooks needed for later live network validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import socket
import subprocess
import sys
import time
import wave
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.runner_companion import (  # noqa: E402
    HEALTH_SCHEMA,
    SNAPSHOT_SCHEMA,
    RunnerCompanionConfig,
    RunnerCompanionService,
    build_pairing_uri,
)


APP_ID = "io.ppskit.runnercompanion"
TOKEN = "android-validation-token"
SCHEMA = "pps-android-companion-emulator-ui-stress.v1"
EMULATOR_VIEWPORT_POLICY = "fixed_avd_viewport_no_resize_no_reposition"
FORBIDDEN_EMULATOR_VIEWPORT_COMMANDS = [
    "wm size",
    "wm density",
    "settings put system user_rotation",
    "settings put system accelerometer_rotation",
    "cmd window",
    "MoveWindow",
    "SetWindowPos",
    "Set_Companion_Emulation_Layout",
]


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return REPO_ROOT / "artifacts" / "validation_runs" / f"android_companion_emulator_ui_stress_{stamp}"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_tiny_wav(path: Path, *, duration_s: float, sample_rate: int = 44_100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(duration_s * sample_rate))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        frames = bytearray()
        for index in range(frame_count):
            # Quiet but non-silent tone so Android audio playback reports duration.
            value = int(0.12 * 32767 * math.sin(2.0 * math.pi * 440.0 * index / sample_rate))
            frames.extend(int(value).to_bytes(2, byteorder="little", signed=True))
        wav.writeframes(bytes(frames))


@dataclass
class MobileValidationAsset:
    package_id: str
    asset_id: str
    path: Path
    duration_s: float


class ValidationBridge:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.sequence = 1
        self.setup_payloads: list[dict[str, Any]] = []
        self.started_parts: list[int] = []
        self.paused = 0
        self.resumed = 0
        self.continued = 0
        self.mobile_event_uploads: list[dict[str, Any]] = []
        self.mobile_complete_uploads: list[dict[str, Any]] = []
        self._setup_submitted = False
        self._part = 0
        self._running = False
        self._paused = False
        self._part1_continue_seen = False
        self.assets = self._prepare_assets(output_dir / "server_assets")

    def _prepare_assets(self, asset_dir: Path) -> dict[str, MobileValidationAsset]:
        part1 = asset_dir / "validation_part1_block.wav"
        part2 = asset_dir / "validation_part2_block.wav"
        _write_tiny_wav(part1, duration_s=12.0)
        _write_tiny_wav(part2, duration_s=12.0)
        return {
            "pkg-part1": MobileValidationAsset("pkg-part1", "asset-part1-block", part1, 12.0),
            "pkg-part2": MobileValidationAsset("pkg-part2", "asset-part2-block", part2, 12.0),
        }

    def health(self) -> dict[str, Any]:
        return {"schema": HEALTH_SCHEMA, "status": "ok", "session_id": "android-ui-stress"}

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": SNAPSHOT_SCHEMA,
            "sequence": self.sequence,
            "server_unix_ms": int(time.time() * 1000),
            "server_perf_counter_s": time.perf_counter(),
            "connection_state": "online",
            "allowed_commands": self._allowed_commands(),
            "participant": {"participant_id": "PVAL"},
            "setup": {"submitted": self._setup_submitted},
            "part_status": {"available_parts": ["1", "2"], "active_part": str(self._part or "")},
            "run_status": {
                "running": self._running,
                "paused": self._paused,
                "state_label": "Paused" if self._paused else ("Running" if self._running else "Ready"),
            },
            "run_plan": [{"part_number": 1}, {"part_number": 2}],
            "active_block": {
                "duration_s": 12.0,
                "elapsed_s": 2.0 if self._running else 0.0,
                "last_anchor_server_perf_counter_s": time.perf_counter(),
                "running": self._running,
                "paused": self._paused,
                "instruction_waiting": self._running and not self._paused,
            },
            "timeline": {
                "trial_rows": [
                    {"trial_number": 1, "start_s": 0.0, "end_s": 4.0, "display_label": "V1", "soa_ms": "100"},
                    {"trial_number": 2, "start_s": 4.0, "end_s": 8.0, "display_label": "V2", "soa_ms": "300"},
                ],
                "tactile_cues": [
                    {"trial_number": 1, "tactile_time_s": 0.25, "soa_ms": "100"},
                    {"trial_number": 2, "tactile_time_s": 4.25, "soa_ms": "300"},
                ],
                "clicks": [],
                "counts": {"clicks": 0},
            },
            "topup": {"draft_count": 0},
            "instruction_gate": {
                "waiting": self._running and not self._paused,
                "button_label": "Continue",
            },
        }

    def _allowed_commands(self) -> list[str]:
        if not self._setup_submitted:
            return ["setup"]
        if self._paused:
            return ["resume"]
        if self._running:
            return ["pause", "continue_instruction"]
        if self._part == 0:
            return ["start_part_1"]
        if self._part == 1 and self._part1_continue_seen:
            return ["start_part_2"]
        if self._part == 2:
            return ["start_part_2"]
        return ["continue_instruction"]

    def submit_setup(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.setup_payloads.append(dict(payload))
        self._setup_submitted = True
        self.sequence += 1
        return self.snapshot()

    def continue_instruction(self) -> dict[str, Any]:
        self.continued += 1
        if self._part == 1:
            self._running = False
            self._paused = False
            self._part1_continue_seen = True
        elif self._part == 2:
            self._running = False
            self._paused = False
        self.sequence += 1
        return self.snapshot()

    def start_part(self, part_number: int) -> dict[str, Any]:
        self.started_parts.append(int(part_number))
        self._part = int(part_number)
        self._running = True
        self._paused = False
        self.sequence += 1
        return self.snapshot()

    def pause(self) -> dict[str, Any]:
        self.paused += 1
        self._paused = True
        self.sequence += 1
        return self.snapshot()

    def resume(self) -> dict[str, Any]:
        self.resumed += 1
        self._paused = False
        self._running = True
        self.sequence += 1
        return self.snapshot()

    def mobile_packages(self) -> dict[str, Any]:
        return {
            "schema": "pps-mobile-run-package-list.v2",
            "active_package_id": "pkg-part1",
            "packages": [
                self._package_summary("pkg-part1", "Validation Part 01", 1),
                self._package_summary("pkg-part2", "Validation Part 02", 2),
            ],
        }

    def _package_summary(self, package_id: str, title: str, part_number: int) -> dict[str, Any]:
        asset = self.assets[package_id]
        return {
            "package_id": package_id,
            "participant_id": "PVAL",
            "session_id": f"android-ui-stress-part-{part_number:02d}",
            "title": title,
            "block_count": 1,
            "trial_count": 1,
            "asset_count": 1,
            "total_asset_bytes": asset.path.stat().st_size,
            "mobile_runnable": True,
            "phone_owned_session": False,
            "warnings": [],
        }

    def mobile_package_manifest(self, package_id: str) -> dict[str, Any]:
        if package_id not in self.assets:
            raise KeyError(package_id)
        part_number = 1 if package_id.endswith("part1") else 2
        asset = self.assets[package_id]
        size = asset.path.stat().st_size
        return {
            "schema": "pps-mobile-run-package.v2",
            "package_id": package_id,
            "participant_id": "PVAL",
            "session_id": f"android-ui-stress-part-{part_number:02d}",
            "session_group_id": "android-ui-stress-group",
            "part_session_id": f"android-ui-stress-part-{part_number:02d}",
            "part_number": str(part_number),
            "title": f"Validation Part {part_number:02d}",
            "phone_owned_session": False,
            "mobile_runnable": True,
            "warnings": [],
            "assets": [
                {
                    "asset_id": asset.asset_id,
                    "filename": asset.path.name,
                    "media_type": "audio/wav",
                    "role": "block_audio",
                    "size_bytes": size,
                    "sha256": _sha256(asset.path),
                    "available": True,
                }
            ],
            "blocks": [
                {
                    "block_id": f"block-part-{part_number:02d}",
                    "index": 1,
                    "label": f"Part {part_number:02d} validation block",
                    "duration_s": asset.duration_s,
                    "trial_count": 1,
                    "audio_asset_id": asset.asset_id,
                    "trials": [
                        {
                            "trial_number": 1,
                            "trial_uid": f"P{part_number:02d}-T001",
                            "trial_type": "audio_tactile",
                            "family": "main",
                            "soa_ms": "100",
                            "row_label": "validation_trial",
                            "noise_type": "validation",
                            "start_s": 0.0,
                            "end_s": asset.duration_s,
                            "duration_s": asset.duration_s,
                            "tactile_onset_s": 1.5,
                            "response_window_onset_s": 1.5,
                        }
                    ],
                    "tactile_cues": [
                        {
                            "cue_id": 1,
                            "trial_number": 1,
                            "trial_uid": f"P{part_number:02d}-T001",
                            "time_s": 1.5,
                            "trial_relative_time_s": 1.5,
                            "soa_ms": "100",
                            "row_label": "validation_trial",
                            "noise_type": "validation",
                        }
                    ],
                }
            ],
            "building_blocks": [],
            "reconstruction": {
                "schema": "pps-mobile-reconstruction-contract.v1",
                "authority": "validation_fixture",
                "fallback_execution_strategy": "prepared_block_wav_replay",
                "preferred_lightweight_strategy": "pcm_wav_assembler",
                "source_run_setup_sha256": "validation",
                "schedule_hash": f"validation-part-{part_number}",
                "building_block_count": 0,
                "block_count": 1,
                "trial_count": 1,
            },
            "lsl": {
                "schema": "pps-android-lsl-contract.v1",
                "runtime_authority": "android_phone",
                "privacy_default": "metadata_payload",
                "stream_names": {
                    "rich_markers": "PPSMarkersV2",
                    "numeric_triggers": "PPSTriggerCodes",
                    "command_signals": "PPSCommandSignalsV1",
                    "command_acks": "PPSCommandAcksV1",
                },
                "native_android_lsl_required": True,
                "current_android_source_behavior": "local_lsl_marker_mirror",
                "supported_commands": [
                    "start_experiment",
                    "pause",
                    "resume",
                    "continue_instruction",
                    "stop_after_block",
                    "request_snapshot",
                    "operator_note",
                ],
            },
        }

    def mobile_package_asset_path(self, package_id: str, asset_id: str) -> tuple[str, str]:
        asset = self.assets[package_id]
        if asset.asset_id != asset_id:
            raise KeyError(asset_id)
        return str(asset.path), "audio/wav"

    def mobile_run_events(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {"run_id": run_id, "payload": dict(payload), "received_unix_s": time.time()}
        self.mobile_event_uploads.append(record)
        _write_json(self.output_dir / "server_uploads" / f"{run_id}_events_{len(self.mobile_event_uploads):03d}.json", record)
        return {
            "schema": "pps-mobile-run-events.v1",
            "status": "accepted",
            "run_id": run_id,
            "event_count": len(payload.get("events") or []),
        }

    def mobile_run_complete(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {"run_id": run_id, "payload": dict(payload), "received_unix_s": time.time()}
        self.mobile_complete_uploads.append(record)
        _write_json(self.output_dir / "server_uploads" / f"{run_id}_complete_{len(self.mobile_complete_uploads):03d}.json", record)
        return {
            "schema": "pps-mobile-run-complete.v1",
            "status": "accepted",
            "run_id": run_id,
            "event_count": len(payload.get("events") or []),
        }


class AndroidDevice:
    def __init__(self, *, adb: str, serial: str, output_dir: Path, timeout_s: float = 20.0) -> None:
        self.adb = adb
        self.serial = serial
        self.output_dir = output_dir
        self.timeout_s = timeout_s
        self.dump_index = 0

    def adb_cmd(self, *args: str, timeout_s: float | None = None, check: bool = True, text: bool = True) -> subprocess.CompletedProcess:
        command = [self.adb, "-s", self.serial, *args]
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=text,
            capture_output=True,
            timeout=timeout_s or self.timeout_s,
            check=check,
        )

    def shell(self, command: str, *, timeout_s: float | None = None, check: bool = True) -> subprocess.CompletedProcess:
        return self.adb_cmd("shell", command, timeout_s=timeout_s, check=check)

    def wait_booted(self, timeout_s: float = 180.0) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.adb_cmd("get-state", check=False).stdout.strip()
            boot = self.shell("getprop sys.boot_completed", check=False).stdout.strip()
            if state == "device" and boot == "1":
                return
            time.sleep(2.0)
        raise RuntimeError(f"Android device {self.serial} did not finish booting.")

    def clear_app(self) -> None:
        self.shell(f"pm clear {APP_ID}", check=False)

    def launch_pairing(self, uri: str) -> None:
        escaped = uri.replace("'", "'\\''")
        self.shell(f"am start -a android.intent.action.VIEW -d '{escaped}'", timeout_s=10.0)
        time.sleep(1.0)

    def screenshot(self, name: str) -> Path:
        path = self.output_dir / "screenshots" / f"{name}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        result = self.adb_cmd("exec-out", "screencap", "-p", text=False, timeout_s=10.0)
        path.write_bytes(result.stdout)
        return path

    def dump_ui(self, label: str = "ui") -> tuple[Path, ET.Element]:
        self.dump_index += 1
        local = self.output_dir / "ui_dumps" / f"{self.dump_index:03d}_{label}.xml"
        local.parent.mkdir(parents=True, exist_ok=True)
        self.shell("uiautomator dump /sdcard/pps_window.xml", timeout_s=10.0)
        raw = self.adb_cmd("exec-out", "cat", "/sdcard/pps_window.xml", timeout_s=10.0).stdout
        local.write_text(raw, encoding="utf-8", errors="replace")
        return local, ET.fromstring(raw)

    def nodes(self, label: str = "ui") -> list[dict[str, Any]]:
        _, root = self.dump_ui(label)
        return [dict(node.attrib) for node in root.iter("node")]

    def visible_texts(self, label: str = "ui") -> list[str]:
        texts: list[str] = []
        for node in self.nodes(label):
            text = (node.get("text") or node.get("content-desc") or "").strip()
            if text:
                texts.append(text)
        return texts

    def wait_for_text(self, needle: str, *, timeout_s: float = 20.0, contains: bool = True) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        last_texts: list[str] = []
        while time.monotonic() < deadline:
            nodes = self.nodes("wait")
            last_texts = [(node.get("text") or node.get("content-desc") or "").strip() for node in nodes]
            for node in nodes:
                text = (node.get("text") or node.get("content-desc") or "").strip()
                if (contains and needle in text) or (not contains and needle == text):
                    return node
            time.sleep(0.5)
        raise RuntimeError(f"Timed out waiting for text {needle!r}. Last visible texts: {last_texts[:30]}")

    def tap_text(self, needle: str, *, timeout_s: float = 20.0, contains: bool = True) -> dict[str, Any]:
        node = self.wait_for_text(needle, timeout_s=timeout_s, contains=contains)
        x, y = _center_from_bounds(node["bounds"])
        self.shell(f"input tap {x} {y}", timeout_s=5.0)
        time.sleep(0.45)
        return {"text": needle, "x": x, "y": y, "node": node}

    def tap_text_scrolling(self, needle: str, *, attempts: int = 6, contains: bool = True) -> dict[str, Any]:
        last_error = ""
        for _ in range(max(1, attempts)):
            try:
                return self.tap_text(needle, timeout_s=2.0, contains=contains)
            except Exception as exc:  # noqa: BLE001 - retained in validation report on final failure.
                last_error = str(exc)
                self.shell("input swipe 1500 780 1500 260 350", check=False)
                time.sleep(0.4)
        raise RuntimeError(last_error or f"Could not find {needle!r} after scrolling.")

    def scroll_to_top(self, *, swipes: int = 5) -> None:
        for _ in range(max(1, swipes)):
            self.shell("input swipe 1500 260 1500 790 250", check=False)
            time.sleep(0.15)

    def enter_text(self, field_label: str, value: str) -> None:
        self.tap_text(field_label, timeout_s=10.0)
        time.sleep(0.2)
        escaped = value.replace(" ", "%s").replace("&", "\\&")
        self.shell(f"input text {escaped}", timeout_s=5.0)
        time.sleep(0.2)
        self.shell("input keyevent KEYCODE_BACK", check=False)
        time.sleep(0.3)

    def tap_center_repeated(self, *, count: int, interval_s: float) -> list[dict[str, Any]]:
        taps: list[dict[str, Any]] = []
        for index in range(count):
            node = self.wait_for_text("Tap Response", timeout_s=5.0)
            x, y = _center_from_bounds(node["bounds"])
            self.shell(f"input tap {x} {y}", timeout_s=5.0)
            taps.append({"index": index + 1, "x": x, "y": y, "unix_s": time.time()})
            time.sleep(interval_s)
        return taps


def _center_from_bounds(bounds: str) -> tuple[int, int]:
    # Android bounds are formatted as [left,top][right,bottom].
    cleaned = bounds.replace("][", ",").replace("[", "").replace("]", "")
    left, top, right, bottom = [int(part) for part in cleaned.split(",")]
    return int((left + right) / 2), int((top + bottom) / 2)


def run_pc_control_ui(device: AndroidDevice, pairing_uri: str, bridge: ValidationBridge, output_dir: Path) -> dict[str, Any]:
    evidence: dict[str, Any] = {"name": "pc_runner_control_ui", "steps": []}
    device.clear_app()
    device.launch_pairing(pairing_uri)
    evidence["steps"].append({"action": "launch_pairing", "texts": device.visible_texts("pc_launch")})
    device.screenshot("pc_01_mode_selection")
    device.wait_for_text("Experiment Mode", timeout_s=20.0)
    evidence["steps"].append({"action": "tap_pc_runner_control", **device.tap_text("PC Runner Control")})
    device.wait_for_text("Participant Setup", timeout_s=20.0)
    device.screenshot("pc_02_runner_control_setup")
    device.enter_text("Name", "Validation User")
    device.enter_text("Age", "31")
    evidence["steps"].append({"action": "submit_setup", **device.tap_text_scrolling("Submit")})
    device.wait_for_text("Start Part 01", timeout_s=20.0)
    evidence["steps"].append({"action": "start_part_1", **device.tap_text("Start Part 01")})
    device.wait_for_text("Pause", timeout_s=20.0)
    evidence["steps"].append({"action": "pause_1", **device.tap_text("Pause")})
    device.wait_for_text("Resume", timeout_s=20.0)
    evidence["steps"].append({"action": "resume_1", **device.tap_text("Resume")})
    device.wait_for_text("Continue", timeout_s=20.0)
    evidence["steps"].append({"action": "continue_part_1", **device.tap_text("Continue")})
    device.wait_for_text("Start Part 02", timeout_s=20.0)
    evidence["steps"].append({"action": "start_part_2", **device.tap_text("Start Part 02")})
    device.wait_for_text("Pause", timeout_s=20.0)
    evidence["steps"].append({"action": "pause_2", **device.tap_text("Pause")})
    device.wait_for_text("Resume", timeout_s=20.0)
    evidence["steps"].append({"action": "resume_2", **device.tap_text("Resume")})
    device.screenshot("pc_03_after_command_stress")
    evidence["bridge_state"] = {
        "setup_payloads": bridge.setup_payloads,
        "started_parts": bridge.started_parts,
        "paused": bridge.paused,
        "resumed": bridge.resumed,
        "continued": bridge.continued,
    }
    evidence["passed"] = (
        len(bridge.setup_payloads) == 1
        and bridge.started_parts[:2] == [1, 2]
        and bridge.paused >= 2
        and bridge.resumed >= 2
        and bridge.continued >= 1
    )
    _write_json(output_dir / "pc_runner_control_ui_report.json", evidence)
    return evidence


def run_phone_runtime_ui(device: AndroidDevice, pairing_uri: str, bridge: ValidationBridge, output_dir: Path) -> dict[str, Any]:
    evidence: dict[str, Any] = {"name": "phone_runtime_ui", "steps": []}
    device.clear_app()
    device.launch_pairing(pairing_uri)
    device.wait_for_text("Experiment Mode", timeout_s=20.0)
    device.screenshot("phone_01_mode_selection")
    evidence["steps"].append({"action": "tap_run_experiment_on_phone", **device.tap_text("Run Experiment On Phone")})
    device.wait_for_text("Phone Participant Metadata", timeout_s=20.0)
    device.screenshot("phone_02_package_list")
    evidence["steps"].append({"action": "sync_all", **device.tap_text_scrolling("Sync All")})
    time.sleep(2.0)
    device.scroll_to_top()
    device.wait_for_text("Full experiment synced", timeout_s=30.0)
    device.screenshot("phone_03_synced")
    evidence["steps"].append({"action": "start_full_experiment", **device.tap_text_scrolling("Start Full Experiment")})
    device.scroll_to_top()
    device.wait_for_text("Running", timeout_s=10.0)
    device.tap_text_scrolling("Tap Response", attempts=8)
    device.wait_for_text("Tap Response", timeout_s=10.0)
    evidence["tap_stress"] = device.tap_center_repeated(count=16, interval_s=0.35)
    device.scroll_to_top()
    device.wait_for_text("Uploaded 2 part artifacts", timeout_s=60.0)
    device.screenshot("phone_04_full_experiment_complete")
    complete_payloads = [record["payload"] for record in bridge.mobile_complete_uploads]
    all_payloads = [record["payload"] for record in bridge.mobile_event_uploads] + complete_payloads
    complete_summaries = [payload.get("summary", {}) for payload in complete_payloads]
    event_types = []
    tap_count = 0
    valid_tap_count = 0
    for payload in all_payloads:
        event_types.extend([event.get("type") for event in payload.get("events", []) if isinstance(event, dict)])
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        if isinstance(summary, dict):
            tap_count = max(tap_count, int(summary.get("tap_count") or 0))
            valid_tap_count = max(valid_tap_count, int(summary.get("valid_tap_count") or 0))
    evidence["server_state"] = {
        "event_upload_count": len(bridge.mobile_event_uploads),
        "complete_upload_count": len(bridge.mobile_complete_uploads),
        "complete_summaries": complete_summaries,
        "max_tap_count": tap_count,
        "max_valid_tap_count": valid_tap_count,
        "event_types": event_types,
    }
    evidence["passed"] = (
        len(bridge.mobile_complete_uploads) == 2
        and any(event == "run_complete" for event in event_types)
        and any(event == "tap" for event in event_types)
        and tap_count >= 1
    )
    _write_json(output_dir / "phone_runtime_ui_report.json", evidence)
    return evidence


def run_lsl_roundtrip(output_dir: Path, *, count: int) -> dict[str, Any]:
    lsl_dir = output_dir / "lsl_command_ack_roundtrip"
    command = [
        sys.executable,
        str(REPO_ROOT / "For-AI/engineering/validation" / "scripts" / "run_lsl_command_ack_roundtrip.py"),
        "--output-dir",
        str(lsl_dir),
        "--count",
        str(count),
    ]
    started = time.time()
    result = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, timeout=60.0)
    report_path = lsl_dir / "lsl_command_ack_roundtrip_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    return {
        "name": "host_lsl_command_ack_roundtrip",
        "passed": result.returncode == 0 and bool(report.get("passed")),
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "elapsed_s": time.time() - started,
        "report_path": str(report_path),
        "report": report,
    }


def android_emulator_viewport_policy_assessment() -> dict[str, Any]:
    source_text = Path(__file__).read_text(encoding="utf-8", errors="ignore")
    forbidden_found = [
        command
        for command in FORBIDDEN_EMULATOR_VIEWPORT_COMMANDS
        if source_text.count(command) > 1
    ]
    return {
        "name": "android_emulator_fixed_viewport_policy",
        "passed": not forbidden_found,
        "expected_to_pass": True,
        "policy": EMULATOR_VIEWPORT_POLICY,
        "forbidden_commands_found": forbidden_found,
        "reason": (
            "Android UI stress validation uses the AVD's configured viewport, "
            "ADB taps, uiautomator dumps, and screencap output only. It must not "
            "resize, widen, rotate, repeatedly reposition, or otherwise fight the "
            "emulator window to make the UI pass."
        ),
    }


def android_lsl_capability_assessment() -> dict[str, Any]:
    project_root = (
        REPO_ROOT
        / "For-AI"
        / "experiments"
        / "android-companion"
        / "runner-companion"
    )
    app_root = project_root / "app"
    android_sources = list((app_root / "src" / "main").rglob("*.kt"))
    source_by_name = {path.name: path.read_text(encoding="utf-8", errors="ignore") for path in android_sources}
    source_text = "\n".join(source_by_name.values())
    native_markers = ["liblsl", "StreamInlet", "StreamOutlet", "PhoneNativeLslBridge", "PhoneLslControllerTransport"]
    found_markers = [marker for marker in native_markers if marker in source_text]
    native_bridge = source_by_name.get("PhoneNativeLslBridge.kt", "")
    controller_commands = source_by_name.get("PhoneControllerCommands.kt", "")
    main_activity = source_by_name.get("MainActivity.kt", "")
    lsl_protocol = source_by_name.get("PhoneLslProtocol.kt", "")
    build_gradle = (project_root / "build.gradle.kts").read_text(encoding="utf-8", errors="ignore")
    app_build_gradle = (app_root / "build.gradle.kts").read_text(encoding="utf-8", errors="ignore")
    aar_path = app_root / "libs" / "liblsl-Android.aar"
    runner_marker_outlets = all(
        token in native_bridge
        for token in [
            "openMarkerTransport",
            "PHONE_LSL_RICH_MARKER_STREAM_NAME",
            "PHONE_LSL_NUMERIC_TRIGGER_STREAM_NAME",
            "pushMarker",
            "ReflectivePhoneLslMarkerTransport",
        ]
    )
    runner_command_receiver = all(
        token in native_bridge + main_activity
        for token in [
            "openCommandTransport",
            "pullCommandSample",
            "sendAck",
            "pollNativeCommands",
            "recordNativeCommandAckLocked",
            "PPSCommandSignalsV1",
            "PPSCommandAcksV1",
        ]
    )
    controller_command_sender = all(
        token in native_bridge + controller_commands
        for token in [
            "openControllerTransport",
            "sendCommand",
            "pullAckSample",
            "writePhoneControllerCommandOutbox",
            "native_lsl_controller_with_local_outbox",
        ]
    )
    token_gated_commands = all(
        token in lsl_protocol + main_activity + controller_commands
        for token in [
            "token_required",
            "expectedCommandToken",
            "phoneCommandAckForSample",
            "optString(\"token\")",
        ]
    )
    optional_aar_hook = 'file("libs/liblsl-Android.aar")' in app_build_gradle and "implementation(files(optionalLiblslAndroidAar))" in app_build_gradle
    source_supported = runner_marker_outlets and runner_command_receiver and controller_command_sender and token_gated_commands and optional_aar_hook
    live_state = (
        "source_supported_aar_present_requires_live_network_validation"
        if source_supported and aar_path.is_file()
        else "source_supported_default_build_local_mirror_only"
        if source_supported
        else "source_missing_native_lsl_hooks"
    )
    return {
        "name": "android_native_lsl_capability",
        "passed": source_supported,
        "expected_to_pass": True,
        "native_lsl_symbols_found": found_markers,
        "liblsl_aar_present": aar_path.is_file(),
        "optional_aar_gradle_hook_present": optional_aar_hook,
        "runner_marker_outlets_supported_by_source": runner_marker_outlets,
        "runner_command_receiver_supported_by_source": runner_command_receiver,
        "controller_command_sender_supported_by_source": controller_command_sender,
        "token_gated_command_ack_supported_by_source": token_gated_commands,
        "runner_to_android_lsl_control_supported_by_source": runner_command_receiver,
        "second_android_app_lsl_control_supported_by_source": controller_command_sender,
        "live_native_lsl_control_available_in_this_build": source_supported and aar_path.is_file(),
        "live_validation_state": live_state,
        "native_lsl_runtime_requires_local_aar": True,
        "build_gradle_seen": "com.android.application" in build_gradle or "com.android.application" in app_build_gradle,
        "reason": (
            "The Android source now contains optional native liblsl marker, command receiver, "
            "ack, and controller-sender hooks. Default builds remain local-mirror/outbox only "
            "unless For-AI/experiments/android-companion/runner-companion/app/libs/liblsl-Android.aar is supplied, and live "
            "network/XDF validation is still required before treating Android LSL as proven."
        ),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stress the Android companion through emulator UI labels and ADB taps.")
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-pc-control", action="store_true")
    parser.add_argument("--skip-phone-runtime", action="store_true")
    parser.add_argument("--skip-lsl-roundtrip", action="store_true")
    parser.add_argument("--lsl-count", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    port = _free_port()
    bridge = ValidationBridge(output_dir)
    service = RunnerCompanionService(
        bridge,
        config=RunnerCompanionConfig(host="127.0.0.1", port=port, advertise_ip="10.0.2.2"),
        token=TOKEN,
    )
    device = AndroidDevice(adb=args.adb, serial=args.serial, output_dir=output_dir)

    results: list[dict[str, Any]] = [
        android_emulator_viewport_policy_assessment(),
        android_lsl_capability_assessment(),
    ]
    started = time.time()
    service_started = False
    fatal_error: dict[str, str] | None = None
    try:
        service.start()
        service_started = True
        device.wait_booted()
        pc_pairing_uri = build_pairing_uri(host="10.0.2.2", port=port, session_id="android-ui-stress", token=TOKEN)
        phone_pairing_uri = pc_pairing_uri
        if not args.skip_pc_control:
            results.append(run_pc_control_ui(device, pc_pairing_uri, bridge, output_dir))
        if not args.skip_phone_runtime:
            results.append(run_phone_runtime_ui(device, phone_pairing_uri, bridge, output_dir))
        if not args.skip_lsl_roundtrip:
            results.append(run_lsl_roundtrip(output_dir, count=max(1, int(args.lsl_count))))
    except Exception as exc:  # noqa: BLE001 - validation artifacts must capture early device/setup failures.
        fatal_error = {"type": type(exc).__name__, "message": str(exc)}
        results.append(
            {
                "name": "android_emulator_ui_stress_exception",
                "passed": False,
                "error_type": fatal_error["type"],
                "message": fatal_error["message"],
            }
        )
    finally:
        if service_started:
            service.stop()

    passed = all(bool(item.get("passed")) or item.get("expected_to_pass") is False for item in results)
    strict_passed = all(bool(item.get("passed")) for item in results)
    report = {
        "schema": SCHEMA,
        "passed": passed,
        "strict_passed": strict_passed,
        "started_unix_s": started,
        "elapsed_s": time.time() - started,
        "adb_serial": args.serial,
        "companion_port": port,
        "artifact_dir": str(output_dir),
        "results": results,
        "fatal_error": fatal_error,
        "interpretation": {
            "pc_runner_control_http_ui": "pass" if any(r.get("name") == "pc_runner_control_ui" and r.get("passed") for r in results) else "fail_or_skipped",
            "phone_local_full_experiment_ui": "pass" if any(r.get("name") == "phone_runtime_ui" and r.get("passed") for r in results) else "fail_or_skipped",
            "host_lsl_command_ack": "pass" if any(r.get("name") == "host_lsl_command_ack_roundtrip" and r.get("passed") for r in results) else "fail_or_skipped",
            "android_live_lsl_control": next(
                (
                    str(r.get("live_validation_state"))
                    for r in results
                    if r.get("name") == "android_native_lsl_capability"
                ),
                "not_assessed",
            ),
        },
    }
    _write_json(output_dir / "android_companion_emulator_ui_stress_report.json", report)
    print(json.dumps({"passed": report["passed"], "strict_passed": report["strict_passed"], "artifact_dir": str(output_dir)}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
