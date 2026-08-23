"""Electrical loopback latency validation for PPS audio-tactile runs.

This module validates the synchronized Komplete ASIO route used by rendered
PPS stimuli. It measures the electrical output-to-input timing for the left
audio, right audio, and tactile-drive channels. It does not measure the
mechanical onset latency of a Woojer transducer.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf


DEFAULT_DEVICE_QUERY = "Komplete"
DEFAULT_DEVICE_NAME = "Komplete Audio ASIO Driver"
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_CHANNELS = 3
DEFAULT_LATENCY_S = 0.010
DEFAULT_BLOCKSIZE = 256
DEFAULT_OUTPUT_DIR = Path("artifacts") / "latency_validation"
DEFAULT_BASELINE_DIR = Path("local_data") / "latency_baselines"
SAFE_HARDWARE_AMPLITUDE_DEFAULT = 0.05
SAFE_HARDWARE_AMPLITUDE_MAX = 0.10

CHANNEL_LABELS = ("left_audio", "right_audio", "tactile_drive", "aux_4")


@dataclass(frozen=True)
class ValidationThresholds:
    min_detection_rate: float = 0.95
    max_left_right_skew_ms: float = 1.0
    max_tactile_audio_skew_ms: float = 2.0
    max_p95_jitter_ms: float = 2.0
    max_residual_jitter_ms: float = 5.0
    max_drift_ms_per_min: float = 0.5
    min_peak: float = 0.015
    clipping_abs: float = 0.98
    max_baseline_median_shift_ms: float = 3.0
    max_baseline_skew_shift_ms: float = 1.0


@dataclass(frozen=True)
class PlannedPulse:
    pulse_index: int
    channel: int
    channel_label: str
    sample_index: int
    time_s: float


def channel_label(index: int) -> str:
    if 0 <= index < len(CHANNEL_LABELS):
        return CHANNEL_LABELS[index]
    return f"channel_{index + 1}"


def validation_specs() -> dict[str, Any]:
    return {
        "schema": "pps-latency-device-specs.v1",
        "scope": "electrical_loopback_only",
        "audio_interface": {
            "device": "Native Instruments Komplete Audio 6 MK2",
            "use_in_toolkit": "synchronized ASIO output/input route",
            "recorded_specs": {
                "audio_resolution": "up to 192 kHz / 24-bit",
                "analog_io": "4 analog inputs / 4 analog outputs",
                "digital_io": "stereo S/PDIF input/output",
                "host_connection": "USB-B, USB 2.0, bus powered",
            },
            "sources": [
                "https://www.bhphotovideo.com/c/product/1477750-REG/native_instruments_25898_komplete_audio_6_mk2.html/specs",
                "https://www.native-instruments.com/en/support/downloads/drivers-other-files/",
            ],
        },
        "tactile_target": {
            "device": "Woojer Strap 4",
            "experiment_route": "wired analog aux input from Komplete output 3",
            "recorded_specs": {
                "haptic_frequency_response": "1-250 Hz",
                "audio_frequency_response": "20 Hz-20 kHz",
                "audio_input": "Aux 3.5 mm TRRS, USB stereo audio, Bluetooth A2DP",
                "bluetooth": "Bluetooth 5.0 audio plus BLE app control/update",
            },
            "sources": [
                "https://www.woojer.com/products/strap-4",
                "https://www.woojer.com/pages/strap-4-manual",
            ],
        },
        "limitations": [
            "Electrical loopback validates signal timing at the audio interface outputs and inputs.",
            "It does not validate Woojer mechanical vibration onset without an external vibration sensor.",
            "Bluetooth routes are excluded because they add avoidable, device-dependent latency.",
        ],
    }


def wiring_plan() -> dict[str, Any]:
    return {
        "schema": "pps-latency-wiring-plan.v1",
        "calibration_loopback_state": [
            "Turn output volume down before patching.",
            "Turn phantom power off.",
            "Set Komplete inputs 1/2 to line input mode rather than instrument/Hi-Z.",
            "Set input gain low, then raise only enough to avoid low-signal warnings.",
            "Patch physical output 1 to physical input 1 with a 1/4-inch TRS line cable.",
            "Patch physical output 2 to physical input 2 with a 1/4-inch TRS line cable.",
            "Patch physical output 3 to physical input 3 with a 1/4-inch TRS line cable.",
            "Optionally patch output 4 to input 4 for padded/future 4-channel tests.",
            "Disconnect or mute headphones and Woojer during calibration bursts.",
        ],
        "experiment_state": [
            "Remove the direct loopback patches.",
            "Route output 1/2 to headphones or a headphone amplifier.",
            "Route output 3 to the Woojer Strap 4 analog aux input.",
            "Use wired analog input for tactile timing work; do not use Bluetooth.",
            "Use splitters or a distribution amplifier only for later continuous participant-run loopback.",
        ],
        "software_channel_mapping": {
            "physical_output_1": "software output selector 0, left audio",
            "physical_output_2": "software output selector 1, right audio",
            "physical_output_3": "software output selector 2, tactile drive",
            "physical_input_1": "software input selector 0",
            "physical_input_2": "software input selector 1",
            "physical_input_3": "software input selector 2",
        },
    }


def make_calibration_stimulus(
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    pulse_count: int = 30,
    pre_roll_s: float = 1.0,
    post_roll_s: float = 1.0,
    pulse_interval_s: float = 0.5,
    pulse_duration_s: float = 0.010,
    amplitude: float = SAFE_HARDWARE_AMPLITUDE_DEFAULT,
) -> tuple[np.ndarray, list[PlannedPulse]]:
    """Return a deterministic multichannel pulse train and planned events."""

    if channels < 1:
        raise ValueError("channels must be at least 1")
    if pulse_count < 1:
        raise ValueError("pulse_count must be at least 1")
    if not (0.0 < amplitude <= 0.95):
        raise ValueError("amplitude must be in the range (0, 0.95]")

    pulse_samples = max(2, int(round(pulse_duration_s * sample_rate)))
    half = max(1, pulse_samples // 2)
    pulse = np.empty(pulse_samples, dtype=np.float32)
    pulse[:half] = float(amplitude)
    pulse[half:] = -float(amplitude)

    first_sample = int(round(pre_roll_s * sample_rate))
    interval_samples = max(pulse_samples + 1, int(round(pulse_interval_s * sample_rate)))
    last_start = first_sample + (pulse_count - 1) * interval_samples
    frames = last_start + pulse_samples + int(round(post_roll_s * sample_rate))
    data = np.zeros((frames, channels), dtype=np.float32)
    events: list[PlannedPulse] = []

    for pulse_index in range(1, pulse_count + 1):
        start = first_sample + (pulse_index - 1) * interval_samples
        for channel in range(channels):
            data[start : start + pulse_samples, channel] += pulse
            events.append(
                PlannedPulse(
                    pulse_index=pulse_index,
                    channel=channel,
                    channel_label=channel_label(channel),
                    sample_index=start,
                    time_s=start / float(sample_rate),
                )
            )
    return data, events


def _channel_threshold(signal: np.ndarray, *, min_peak: float) -> tuple[float, float, bool]:
    abs_signal = np.abs(signal.astype(np.float64, copy=False))
    peak = float(np.max(abs_signal)) if abs_signal.size else 0.0
    if not math.isfinite(peak):
        peak = 0.0
    median = float(np.median(abs_signal)) if abs_signal.size else 0.0
    mad = float(np.median(np.abs(abs_signal - median))) if abs_signal.size else 0.0
    adaptive = median + 8.0 * max(mad, 1e-9)
    if peak > 0:
        adaptive = min(max(adaptive, min_peak), peak * 0.50)
    threshold = max(min_peak, adaptive)
    return threshold, peak, peak < min_peak


def detect_loopback_events(
    samples: np.ndarray,
    planned_events: Iterable[PlannedPulse],
    *,
    sample_rate: int,
    thresholds: ValidationThresholds | None = None,
    search_pre_s: float = 0.005,
    search_post_s: float = 0.250,
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Detect planned loopback pulses in a captured multichannel signal."""

    thresholds = thresholds or ValidationThresholds()
    samples = _as_2d_float(samples)
    planned = list(planned_events)
    channel_profiles: dict[int, dict[str, Any]] = {}
    rows: list[dict[str, Any]] = []
    pre = int(round(search_pre_s * sample_rate))
    post = int(round(search_post_s * sample_rate))

    for channel in sorted({event.channel for event in planned}):
        if channel >= samples.shape[1]:
            channel_profiles[channel] = {
                "channel": channel,
                "channel_label": channel_label(channel),
                "threshold": "",
                "peak": 0.0,
                "low_signal": True,
                "clipped": False,
                "error": "capture has fewer channels than planned",
            }
            continue
        signal = samples[:, channel]
        threshold, peak, low_signal = _channel_threshold(signal, min_peak=thresholds.min_peak)
        channel_profiles[channel] = {
            "channel": channel,
            "channel_label": channel_label(channel),
            "threshold": threshold,
            "peak": peak,
            "low_signal": low_signal,
            "clipped": bool(peak >= thresholds.clipping_abs),
            "error": "",
        }

    for event in planned:
        profile = channel_profiles.get(event.channel, {})
        row = {
            "pulse_index": event.pulse_index,
            "channel": event.channel,
            "channel_label": event.channel_label,
            "expected_sample": event.sample_index,
            "expected_time_s": f"{event.time_s:.9f}",
            "detected": False,
            "detected_sample": "",
            "detected_time_s": "",
            "latency_samples": "",
            "latency_ms": "",
            "threshold": profile.get("threshold", ""),
            "peak": profile.get("peak", ""),
            "error": profile.get("error", ""),
        }
        if event.channel >= samples.shape[1] or profile.get("error"):
            rows.append(row)
            continue
        threshold = float(profile["threshold"])
        start = max(0, int(event.sample_index) - pre)
        stop = min(samples.shape[0], int(event.sample_index) + post)
        segment = np.abs(samples[start:stop, event.channel])
        hits = np.flatnonzero(segment >= threshold)
        if hits.size:
            detected_sample = int(start + hits[0])
            latency_samples = detected_sample - int(event.sample_index)
            row.update(
                {
                    "detected": True,
                    "detected_sample": detected_sample,
                    "detected_time_s": f"{detected_sample / float(sample_rate):.9f}",
                    "latency_samples": latency_samples,
                    "latency_ms": f"{latency_samples / float(sample_rate) * 1000.0:.6f}",
                }
            )
        rows.append(row)
    return rows, channel_profiles


def summarize_latency_validation(
    detection_rows: list[dict[str, Any]],
    channel_profiles: dict[int, dict[str, Any]],
    *,
    thresholds: ValidationThresholds | None = None,
    baseline_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or ValidationThresholds()
    channel_summaries: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    for channel in sorted(channel_profiles):
        profile = channel_profiles[channel]
        rows = [row for row in detection_rows if int(row["channel"]) == channel]
        detected = [row for row in rows if row["detected"]]
        latencies = np.array([float(row["latency_ms"]) for row in detected], dtype=np.float64)
        times = np.array([float(row["expected_time_s"]) for row in detected], dtype=np.float64)
        planned_count = len(rows)
        detected_count = len(detected)
        detection_rate = detected_count / planned_count if planned_count else 0.0
        median_latency = _nan_float(np.median(latencies)) if latencies.size else math.nan
        mean_latency, sd_latency = _mean_sd(latencies)
        residuals = np.abs(latencies - median_latency) if latencies.size else np.array([], dtype=np.float64)
        mean_residual, sd_residual = _mean_sd(residuals)
        p95_jitter = _nan_float(np.percentile(residuals, 95)) if residuals.size else math.nan
        max_jitter = _nan_float(np.max(residuals)) if residuals.size else math.nan
        drift = _drift_ms_per_min(times, latencies)
        summary = {
            "channel": channel,
            "channel_label": profile.get("channel_label", channel_label(channel)),
            "planned_count": planned_count,
            "detected_count": detected_count,
            "detection_rate": detection_rate,
            "mean_latency_ms": mean_latency,
            "sd_latency_ms": sd_latency,
            "median_latency_ms": median_latency,
            "mean_abs_residual_jitter_ms": mean_residual,
            "sd_abs_residual_jitter_ms": sd_residual,
            "p95_residual_jitter_ms": p95_jitter,
            "max_residual_jitter_ms": max_jitter,
            "drift_ms_per_min": drift,
            "peak": profile.get("peak", 0.0),
            "threshold": profile.get("threshold", ""),
            "low_signal": bool(profile.get("low_signal", False)),
            "clipped": bool(profile.get("clipped", False)),
            "error": profile.get("error", ""),
        }
        channel_summaries.append(summary)
        checks.extend(_channel_checks(summary, thresholds))

    skew = _skew_summary(detection_rows)
    checks.append(
        {
            "name": "left_right_median_skew",
            "passed": _lte_or_missing(skew.get("left_right_median_abs_skew_ms"), thresholds.max_left_right_skew_ms),
            "value": skew.get("left_right_median_abs_skew_ms"),
            "threshold": thresholds.max_left_right_skew_ms,
        }
    )
    checks.append(
        {
            "name": "tactile_audio_median_skew",
            "passed": _lte_or_missing(skew.get("tactile_audio_median_abs_skew_ms"), thresholds.max_tactile_audio_skew_ms),
            "value": skew.get("tactile_audio_median_abs_skew_ms"),
            "threshold": thresholds.max_tactile_audio_skew_ms,
        }
    )

    baseline_comparison = _baseline_comparison(channel_summaries, skew, baseline_summary, thresholds)
    checks.extend(baseline_comparison.get("checks", []))
    passed = all(bool(check.get("passed")) for check in checks)
    return {
        "schema": "pps-latency-summary.v1",
        "passed": passed,
        "status": "pass" if passed else "fail",
        "channel_summaries": channel_summaries,
        "skew_summary": skew,
        "baseline_comparison": baseline_comparison,
        "checks": checks,
    }


def route_key(route_snapshot: dict[str, Any]) -> str:
    parts = [
        str(route_snapshot.get("device_name", "")),
        str(route_snapshot.get("hostapi", "")),
        str(route_snapshot.get("sample_rate", "")),
        str(route_snapshot.get("channels", "")),
        str(route_snapshot.get("latency_s", "")),
        str(route_snapshot.get("blocksize", "")),
        "-".join(str(x) for x in route_snapshot.get("output_selectors", [])),
        "-".join(str(x) for x in route_snapshot.get("input_selectors", [])),
    ]
    return _slug("_".join(parts))


def build_route_snapshot(
    *,
    device_name: str = DEFAULT_DEVICE_NAME,
    hostapi: str = "ASIO",
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = DEFAULT_CHANNELS,
    latency_s: float = DEFAULT_LATENCY_S,
    blocksize: int = DEFAULT_BLOCKSIZE,
    input_selectors: list[int] | None = None,
    output_selectors: list[int] | None = None,
    local_device_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "pps-latency-route-snapshot.v1",
        "device_name": device_name,
        "hostapi": hostapi,
        "sample_rate": sample_rate,
        "channels": channels,
        "latency_s": latency_s,
        "blocksize": blocksize,
        "input_selectors": list(input_selectors if input_selectors is not None else range(channels)),
        "output_selectors": list(output_selectors if output_selectors is not None else range(channels)),
        "local_device_info": local_device_info or {},
    }


def _load_sounddevice():
    os.environ.setdefault("SD_ENABLE_ASIO", "1")
    import sounddevice as sd  # type: ignore

    return sd


def _hostapi_name(sd: Any, device_info: dict[str, Any]) -> str:
    try:
        return str(sd.query_hostapis(int(device_info.get("hostapi", 0))).get("name", ""))
    except Exception:
        return ""


def _select_device(sd: Any, *, device: int | None, device_query: str, require_asio: bool) -> tuple[int, dict[str, Any], str]:
    devices = sd.query_devices()
    candidates: list[tuple[int, dict[str, Any], str]] = []
    for idx, raw in enumerate(devices):
        dev = dict(raw)
        name = str(dev.get("name", ""))
        hostapi = _hostapi_name(sd, dev)
        if device is not None and idx != device:
            continue
        if device is None and device_query.lower() not in name.lower():
            continue
        if int(dev.get("max_output_channels", 0)) < DEFAULT_CHANNELS:
            continue
        if int(dev.get("max_input_channels", 0)) < DEFAULT_CHANNELS:
            continue
        if require_asio and hostapi.lower() != "asio":
            continue
        candidates.append((idx, dev, hostapi))
    if not candidates:
        raise RuntimeError("No matching full-duplex 3-channel audio device found.")
    candidates.sort(key=lambda item: (0 if "komplete" in item[1].get("name", "").lower() else 1, item[0]))
    return candidates[0]


def _asio_settings(sd: Any, selectors: list[int]):
    if hasattr(sd, "AsioSettings"):
        return sd.AsioSettings(channel_selectors=selectors)
    return None


def capture_live_loopback(
    stimulus: np.ndarray,
    *,
    sample_rate: int,
    channels: int,
    device: int | None = None,
    device_query: str = DEFAULT_DEVICE_QUERY,
    latency_s: float = DEFAULT_LATENCY_S,
    blocksize: int = DEFAULT_BLOCKSIZE,
    allow_non_asio: bool = False,
    capture_tail_s: float = 0.5,
) -> tuple[np.ndarray, dict[str, Any]]:
    sd = _load_sounddevice()
    device_idx, device_info, hostapi = _select_device(
        sd,
        device=device,
        device_query=device_query,
        require_asio=not allow_non_asio,
    )
    input_selectors = list(range(channels))
    output_selectors = list(range(channels))
    extra_settings = None
    if hostapi.lower() == "asio":
        extra_settings = (_asio_settings(sd, input_selectors), _asio_settings(sd, output_selectors))

    total_frames = stimulus.shape[0] + int(round(capture_tail_s * sample_rate))
    state = {"pos": 0, "callbacks": 0, "statuses": [], "input_chunks": []}

    def callback(indata, outdata, frames, time_info, status):
        if status:
            state["statuses"].append(str(status))
        state["callbacks"] += 1
        start = int(state["pos"])
        stop = start + frames
        outdata.fill(0)
        if start < stimulus.shape[0]:
            n = min(frames, stimulus.shape[0] - start)
            outdata[:n, :channels] = stimulus[start : start + n, :channels]
        state["input_chunks"].append(np.array(indata[:, :channels], dtype=np.float32, copy=True))
        state["pos"] = stop
        if stop >= total_frames:
            raise sd.CallbackStop

    stream = sd.Stream(
        samplerate=sample_rate,
        blocksize=blocksize,
        dtype="float32",
        device=(device_idx, device_idx),
        channels=(channels, channels),
        latency=(latency_s, latency_s),
        extra_settings=extra_settings,
        callback=callback,
    )
    start_time = time.perf_counter()
    stream.start()
    deadline = start_time + (total_frames / float(sample_rate)) + 5.0
    while stream.active and time.perf_counter() < deadline:
        time.sleep(0.005)
    active_after_deadline = bool(stream.active)
    actual_latency = getattr(stream, "latency", "")
    cpu_load = float(getattr(stream, "cpu_load", 0.0))
    stream.stop()
    stream.close()

    if not state["input_chunks"]:
        capture = np.zeros((0, channels), dtype=np.float32)
    else:
        capture = np.concatenate(state["input_chunks"], axis=0)[:total_frames]

    route = build_route_snapshot(
        device_name=str(device_info.get("name", "")),
        hostapi=hostapi,
        sample_rate=sample_rate,
        channels=channels,
        latency_s=latency_s,
        blocksize=blocksize,
        input_selectors=input_selectors,
        output_selectors=output_selectors,
        local_device_info=_jsonable_device_info(device_info, device_idx=device_idx, hostapi=hostapi),
    )
    meta = {
        "route": route,
        "actual_latency": _latency_string(actual_latency),
        "cpu_load": f"{cpu_load:.6f}",
        "callback_count": state["callbacks"],
        "status_count": len(state["statuses"]),
        "status_messages": " | ".join(sorted(set(state["statuses"]))),
        "active_after_deadline": active_after_deadline,
        "elapsed_ms": (time.perf_counter() - start_time) * 1000.0,
    }
    return capture, meta


def validate_calibration_capture(
    capture: np.ndarray,
    planned_events: list[PlannedPulse],
    *,
    sample_rate: int,
    route_snapshot: dict[str, Any],
    thresholds: ValidationThresholds | None = None,
    baseline_summary: dict[str, Any] | None = None,
    io_status: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    thresholds = thresholds or ValidationThresholds()
    rows, profiles = detect_loopback_events(capture, planned_events, sample_rate=sample_rate, thresholds=thresholds)
    summary = summarize_latency_validation(rows, profiles, thresholds=thresholds, baseline_summary=baseline_summary)
    status_checks = []
    io_status = dict(io_status or {})
    status_checks.append(
        {
            "name": "callback_status_flags",
            "passed": int(io_status.get("status_count", 0) or 0) == 0,
            "value": io_status.get("status_messages", ""),
            "threshold": "no callback status flags",
        }
    )
    if io_status.get("active_after_deadline"):
        status_checks.append(
            {
                "name": "stream_completed_before_deadline",
                "passed": False,
                "value": True,
                "threshold": False,
            }
        )
    summary["checks"] = status_checks + list(summary["checks"])
    summary["passed"] = all(bool(check.get("passed")) for check in summary["checks"])
    summary["status"] = "pass" if summary["passed"] else "fail"
    summary["route_snapshot"] = route_snapshot
    summary["io_status"] = io_status
    return rows, summary


def validate_session_dir(
    session_dir: Path,
    *,
    output_dir: Path,
    thresholds: ValidationThresholds | None = None,
) -> dict[str, Any]:
    thresholds = thresholds or ValidationThresholds()
    events = _load_session_events(session_dir / "events.csv")
    recordings = sorted((session_dir / "recordings").glob("*.wav"))
    blocks: list[dict[str, Any]] = []
    for recording in recordings:
        samples, sample_rate = _read_wav(recording)
        if samples.shape[1] < 3:
            blocks.append(
                {
                    "recording": str(recording),
                    "status": "skipped",
                    "reason": "recording has fewer than 3 channels; tactile drive channel is not available",
                }
            )
            continue
        block_number = _block_number_from_name(recording.name)
        planned = [
            event
            for event in events
            if event.get("event_type") == "tactile_onset"
            and _payload_bool(event, "planned")
            and _payload_int(event, "block_number") == block_number
        ]
        planned_times = sorted(_payload_float(event, "relative_time_s") for event in planned)
        planned_times = [value for value in planned_times if math.isfinite(value)]
        detected_times = _detect_runs(samples[:, 2], sample_rate, min_peak=thresholds.min_peak)
        block_summary = _compare_session_tactile_timing(planned_times, detected_times, thresholds=thresholds)
        block_summary.update(
            {
                "recording": str(recording),
                "block_number": block_number,
                "planned_tactile_count": len(planned_times),
                "detected_tactile_count": len(detected_times),
            }
        )
        blocks.append(block_summary)
    comparable_blocks = [block for block in blocks if block.get("status") != "skipped"]
    passed = bool(comparable_blocks) and all(block.get("passed") for block in comparable_blocks)
    report = {
        "schema": "pps-session-latency-validation.v1",
        "session_dir": str(session_dir),
        "scope": "intra-block tactile timing from physical loopback recordings",
        "passed": passed,
        "status": "pass" if passed else "review_required",
        "blocks": blocks,
        "limitations": [
            "Block recordings are aligned by the first detected tactile-drive event.",
            "This session validator checks intra-block timing residuals, not absolute roundtrip latency.",
            "Use pps-latency-validate calibrate for absolute electrical loopback validation.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "session_latency_validation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate PPS electrical loopback latency.")
    sub = parser.add_subparsers(dest="command", required=True)

    specs = sub.add_parser("specs", help="Write vendor specs, wiring plan, and local route snapshot.")
    specs.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    specs.add_argument("--device", type=int, help="Specific sounddevice device index.")
    specs.add_argument("--device-query", default=DEFAULT_DEVICE_QUERY)
    specs.add_argument("--allow-non-asio", action="store_true")

    cal = sub.add_parser("calibrate", help="Run active electrical loopback calibration.")
    cal.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    cal.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    cal.add_argument("--device", type=int, help="Specific sounddevice device index.")
    cal.add_argument("--device-query", default=DEFAULT_DEVICE_QUERY)
    cal.add_argument("--allow-non-asio", action="store_true")
    cal.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    cal.add_argument("--channels", type=int, default=DEFAULT_CHANNELS)
    cal.add_argument("--latency", type=float, default=DEFAULT_LATENCY_S)
    cal.add_argument("--blocksize", type=int, default=DEFAULT_BLOCKSIZE)
    cal.add_argument("--pulse-count", type=int, default=30)
    cal.add_argument("--pulse-interval-s", type=float, default=0.5)
    cal.add_argument("--pulse-duration-s", type=float, default=0.010)
    cal.add_argument("--amplitude", type=float, default=SAFE_HARDWARE_AMPLITUDE_DEFAULT)
    cal.add_argument("--establish-baseline", action="store_true")

    session = sub.add_parser("validate-session", help="Validate available loopback recordings for a session.")
    session.add_argument("--session-dir", type=Path, required=True)
    session.add_argument("--output-dir", type=Path)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.command == "specs":
        run_dir = _timestamped_output_dir(args.output_dir)
        payload = _specs_payload(args)
        _write_json(run_dir / "device_specs.json", payload["device_specs"])
        _write_json(run_dir / "wiring_plan.json", payload["wiring_plan"])
        _write_json(run_dir / "route_snapshot.json", payload["route_snapshot"])
        print(f"Wrote latency validation specs to {run_dir}")
        return 0
    if args.command == "calibrate":
        return _run_calibrate(args)
    if args.command == "validate-session":
        output_dir = args.output_dir or (Path(args.session_dir) / "analysis")
        report = validate_session_dir(Path(args.session_dir), output_dir=output_dir)
        print(f"Wrote {Path(output_dir) / 'session_latency_validation_report.json'}")
        return 0 if report["passed"] else 1
    raise SystemExit(f"Unknown command: {args.command}")


def _run_calibrate(args: argparse.Namespace) -> int:
    if args.amplitude <= 0:
        print("--amplitude must be positive.", file=sys.stderr)
        return 2
    if args.amplitude > SAFE_HARDWARE_AMPLITUDE_MAX:
        print(
            f"Refusing hardware playback amplitude {args.amplitude}; "
            f"latency validation caps direct-loopback playback at {SAFE_HARDWARE_AMPLITUDE_MAX}. "
            "Use lower input gain or a safer hardware patch instead of raising the digital test level.",
            file=sys.stderr,
        )
        return 2
    run_dir = _timestamped_output_dir(args.output_dir)
    thresholds = ValidationThresholds()
    stimulus, planned_events = make_calibration_stimulus(
        sample_rate=args.sample_rate,
        channels=args.channels,
        pulse_count=args.pulse_count,
        pulse_interval_s=args.pulse_interval_s,
        pulse_duration_s=args.pulse_duration_s,
        amplitude=args.amplitude,
    )
    sf.write(run_dir / "calibration_stimulus.wav", stimulus, args.sample_rate)
    _write_pulses_csv(run_dir / "planned_pulses.csv", planned_events)

    capture, io_status = capture_live_loopback(
        stimulus,
        sample_rate=args.sample_rate,
        channels=args.channels,
        device=args.device,
        device_query=args.device_query,
        latency_s=args.latency,
        blocksize=args.blocksize,
        allow_non_asio=args.allow_non_asio,
    )
    sf.write(run_dir / "loopback_capture.wav", capture, args.sample_rate)
    route_snapshot = dict(io_status["route"])
    key = route_key(route_snapshot)
    baseline_path = args.baseline_dir / f"{key}.json"
    baseline = _load_json(baseline_path) if baseline_path.exists() and not args.establish_baseline else None
    rows, summary = validate_calibration_capture(
        capture,
        planned_events,
        sample_rate=args.sample_rate,
        route_snapshot=route_snapshot,
        thresholds=thresholds,
        baseline_summary=baseline.get("summary") if isinstance(baseline, dict) else None,
        io_status=io_status,
    )
    _write_detection_csv(run_dir / "latency_events.csv", rows)
    _write_summary_csv(run_dir / "latency_summary.csv", summary)
    _write_json(run_dir / "device_specs.json", validation_specs())
    _write_json(run_dir / "wiring_plan.json", wiring_plan())
    _write_json(run_dir / "route_snapshot.json", route_snapshot)
    _write_json(run_dir / "latency_validation_report.json", summary)
    if args.establish_baseline:
        args.baseline_dir.mkdir(parents=True, exist_ok=True)
        _write_json(
            baseline_path,
            {
                "schema": "pps-latency-baseline.v1",
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "route_key": key,
                "route_snapshot": route_snapshot,
                "summary": summary,
            },
        )
        print(f"Wrote baseline {baseline_path}")
    print(f"Wrote latency validation report to {run_dir}")
    print(f"Status: {summary['status']}")
    return 0 if summary["passed"] else 1


def _specs_payload(args: argparse.Namespace) -> dict[str, Any]:
    route = build_route_snapshot()
    try:
        sd = _load_sounddevice()
        device_idx, device_info, hostapi = _select_device(
            sd,
            device=args.device,
            device_query=args.device_query,
            require_asio=not args.allow_non_asio,
        )
        route = build_route_snapshot(
            device_name=str(device_info.get("name", DEFAULT_DEVICE_NAME)),
            hostapi=hostapi,
            local_device_info=_jsonable_device_info(device_info, device_idx=device_idx, hostapi=hostapi),
        )
    except Exception as exc:
        route["local_device_info"] = {"status": "unavailable", "message": str(exc)}
    return {
        "device_specs": validation_specs(),
        "wiring_plan": wiring_plan(),
        "route_snapshot": route,
    }


def _timestamped_output_dir(root: Path) -> Path:
    path = Path(root) / datetime.now().strftime("%Y%m%d_%H%M%S")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2), encoding="utf-8")
    return path


def _write_pulses_csv(path: Path, pulses: list[PlannedPulse]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(pulses[0]).keys()) if pulses else ["pulse_index"])
        writer.writeheader()
        for pulse in pulses:
            writer.writerow(asdict(pulse))
    return path


def _write_detection_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    fieldnames = [
        "pulse_index",
        "channel",
        "channel_label",
        "expected_sample",
        "expected_time_s",
        "detected",
        "detected_sample",
        "detected_time_s",
        "latency_samples",
        "latency_ms",
        "threshold",
        "peak",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _write_summary_csv(path: Path, summary: dict[str, Any]) -> Path:
    rows = summary.get("channel_summaries", [])
    fieldnames = [
        "channel",
        "channel_label",
        "planned_count",
        "detected_count",
        "detection_rate",
        "median_latency_ms",
        "p95_residual_jitter_ms",
        "max_residual_jitter_ms",
        "drift_ms_per_min",
        "peak",
        "threshold",
        "low_signal",
        "clipped",
        "error",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})
    return path


def _as_2d_float(samples: np.ndarray) -> np.ndarray:
    arr = np.asarray(samples, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2:
        raise ValueError("samples must be a one- or two-dimensional audio array")
    return arr


def _nan_float(value: Any) -> float:
    try:
        result = float(value)
    except Exception:
        return math.nan
    return result if math.isfinite(result) else math.nan


def _mean_sd(values: Any) -> tuple[float, float]:
    arr = np.asarray(list(values), dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return math.nan, math.nan
    mean = _nan_float(np.mean(arr))
    sd = _nan_float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
    return mean, sd


def _drift_ms_per_min(times_s: np.ndarray, latencies_ms: np.ndarray) -> float:
    if times_s.size < 2 or latencies_ms.size < 2:
        return 0.0
    if float(np.max(times_s) - np.min(times_s)) <= 0:
        return 0.0
    slope, _intercept = np.polyfit(times_s / 60.0, latencies_ms, 1)
    return _nan_float(slope)


def _channel_checks(summary: dict[str, Any], thresholds: ValidationThresholds) -> list[dict[str, Any]]:
    label = summary.get("channel_label", f"channel_{summary.get('channel')}")
    return [
        {
            "name": f"{label}_detection_rate",
            "passed": float(summary.get("detection_rate", 0.0)) >= thresholds.min_detection_rate,
            "value": summary.get("detection_rate"),
            "threshold": thresholds.min_detection_rate,
        },
        {
            "name": f"{label}_low_signal",
            "passed": not bool(summary.get("low_signal", False)),
            "value": summary.get("peak"),
            "threshold": thresholds.min_peak,
        },
        {
            "name": f"{label}_clipping",
            "passed": not bool(summary.get("clipped", False)),
            "value": summary.get("peak"),
            "threshold": f"< {thresholds.clipping_abs}",
        },
        {
            "name": f"{label}_p95_jitter",
            "passed": _lte_or_missing(summary.get("p95_residual_jitter_ms"), thresholds.max_p95_jitter_ms),
            "value": summary.get("p95_residual_jitter_ms"),
            "threshold": thresholds.max_p95_jitter_ms,
        },
        {
            "name": f"{label}_max_jitter",
            "passed": _lte_or_missing(summary.get("max_residual_jitter_ms"), thresholds.max_residual_jitter_ms),
            "value": summary.get("max_residual_jitter_ms"),
            "threshold": thresholds.max_residual_jitter_ms,
        },
        {
            "name": f"{label}_drift",
            "passed": abs(float(summary.get("drift_ms_per_min", 0.0))) <= thresholds.max_drift_ms_per_min,
            "value": summary.get("drift_ms_per_min"),
            "threshold": thresholds.max_drift_ms_per_min,
        },
    ]


def _skew_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_pulse: dict[int, dict[int, float]] = {}
    for row in rows:
        if not row.get("detected"):
            continue
        by_pulse.setdefault(int(row["pulse_index"]), {})[int(row["channel"])] = float(row["latency_ms"])
    lr: list[float] = []
    tactile: list[float] = []
    for channels in by_pulse.values():
        if 0 in channels and 1 in channels:
            lr.append(abs(channels[1] - channels[0]))
        if 0 in channels and 1 in channels and 2 in channels:
            tactile.append(abs(channels[2] - ((channels[0] + channels[1]) / 2.0)))
    lr_mean, lr_sd = _mean_sd(lr)
    tactile_mean, tactile_sd = _mean_sd(tactile)
    return {
        "left_right_pairs": len(lr),
        "left_right_mean_abs_skew_ms": lr_mean,
        "left_right_sd_abs_skew_ms": lr_sd,
        "left_right_median_abs_skew_ms": _nan_float(np.median(lr)) if lr else math.nan,
        "tactile_audio_pairs": len(tactile),
        "tactile_audio_mean_abs_skew_ms": tactile_mean,
        "tactile_audio_sd_abs_skew_ms": tactile_sd,
        "tactile_audio_median_abs_skew_ms": _nan_float(np.median(tactile)) if tactile else math.nan,
    }


def _baseline_comparison(
    channel_summaries: list[dict[str, Any]],
    skew: dict[str, Any],
    baseline_summary: dict[str, Any] | None,
    thresholds: ValidationThresholds,
) -> dict[str, Any]:
    if not baseline_summary:
        return {"status": "no_baseline", "checks": []}
    baseline_channels = {int(row["channel"]): row for row in baseline_summary.get("channel_summaries", [])}
    checks: list[dict[str, Any]] = []
    deltas: list[dict[str, Any]] = []
    for row in channel_summaries:
        channel = int(row["channel"])
        baseline = baseline_channels.get(channel)
        if not baseline:
            continue
        try:
            delta = float(row["median_latency_ms"]) - float(baseline["median_latency_ms"])
        except (TypeError, ValueError):
            continue
        deltas.append({"channel": channel, "median_latency_shift_ms": delta})
        checks.append(
            {
                "name": f"{row['channel_label']}_baseline_median_shift",
                "passed": abs(delta) <= thresholds.max_baseline_median_shift_ms,
                "value": delta,
                "threshold": thresholds.max_baseline_median_shift_ms,
            }
        )
    baseline_skew = baseline_summary.get("skew_summary", {})
    for key in ("left_right_median_abs_skew_ms", "tactile_audio_median_abs_skew_ms"):
        if key in baseline_skew and key in skew and math.isfinite(float(skew[key])) and math.isfinite(float(baseline_skew[key])):
            delta = float(skew[key]) - float(baseline_skew[key])
            checks.append(
                {
                    "name": f"{key}_baseline_shift",
                    "passed": abs(delta) <= thresholds.max_baseline_skew_shift_ms,
                    "value": delta,
                    "threshold": thresholds.max_baseline_skew_shift_ms,
                }
            )
    return {"status": "compared", "median_latency_deltas": deltas, "checks": checks}


def _lte_or_missing(value: Any, threshold: float) -> bool:
    try:
        number = float(value)
    except Exception:
        return False
    return math.isfinite(number) and number <= threshold


def _detect_runs(signal: np.ndarray, sample_rate: int, *, min_peak: float) -> list[float]:
    threshold, peak, low_signal = _channel_threshold(signal, min_peak=min_peak)
    if low_signal or peak <= 0:
        return []
    above = np.abs(signal) >= threshold
    starts = []
    min_gap = int(round(0.050 * sample_rate))
    previous = -min_gap
    for idx in np.flatnonzero(above):
        idx = int(idx)
        if idx - previous >= min_gap:
            starts.append(idx / float(sample_rate))
        previous = idx
    return starts


def _compare_session_tactile_timing(
    planned_times: list[float],
    detected_times: list[float],
    *,
    thresholds: ValidationThresholds,
) -> dict[str, Any]:
    if not planned_times or not detected_times:
        return {"status": "no_match", "passed": False, "detection_rate": 0.0, "p95_residual_ms": ""}
    n = min(len(planned_times), len(detected_times))
    offset = detected_times[0] - planned_times[0]
    residuals = [(detected_times[i] - (planned_times[i] + offset)) * 1000.0 for i in range(n)]
    abs_residuals = np.abs(np.array(residuals, dtype=np.float64))
    detection_rate = n / len(planned_times)
    p95 = _nan_float(np.percentile(abs_residuals, 95)) if abs_residuals.size else math.nan
    passed = detection_rate >= thresholds.min_detection_rate and p95 <= thresholds.max_residual_jitter_ms
    return {
        "status": "compared",
        "passed": passed,
        "aligned_offset_s": offset,
        "matched_count": n,
        "detection_rate": detection_rate,
        "median_abs_residual_ms": _nan_float(np.median(abs_residuals)) if abs_residuals.size else math.nan,
        "p95_abs_residual_ms": p95,
    }


def _load_session_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                payload = json.loads(row.get("payload_json", "") or "{}")
            except json.JSONDecodeError:
                payload = {}
            row["payload"] = payload
            rows.append(row)
    return rows


def _payload_bool(event: dict[str, Any], key: str) -> bool:
    value = event.get("payload", {}).get(key)
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"true", "1", "yes"}


def _payload_int(event: dict[str, Any], key: str) -> int:
    try:
        return int(float(str(event.get("payload", {}).get(key, ""))))
    except ValueError:
        return 0


def _payload_float(event: dict[str, Any], key: str) -> float:
    try:
        return float(str(event.get("payload", {}).get(key, "")))
    except ValueError:
        return math.nan


def _block_number_from_name(name: str) -> int:
    match = re.search(r"Block[_ -]*(\d+)", name, flags=re.IGNORECASE)
    if not match:
        return 0
    return int(match.group(1))


def _read_wav(path: Path) -> tuple[np.ndarray, int]:
    data, sample_rate = sf.read(str(path), dtype="float32", always_2d=True)
    return data, int(sample_rate)


def _jsonable_device_info(device_info: dict[str, Any], *, device_idx: int, hostapi: str) -> dict[str, Any]:
    output = {key: _json_ready(value) for key, value in dict(device_info).items()}
    output["device_index"] = device_idx
    output["hostapi_name"] = hostapi
    return output


def _latency_string(value: Any) -> str:
    if isinstance(value, tuple):
        return "/".join(f"{float(item):.6f}" for item in value)
    try:
        return f"{float(value):.6f}"
    except Exception:
        return str(value)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
    return slug or "default"


if __name__ == "__main__":
    raise SystemExit(main())
