"""Run and analyze Woojer audio pass-through loopback latency tests.

The measured target is the audio signal emitted from the Woojer output and
recorded by the Komplete input. This script does not measure Woojer mechanical
vibration onset.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


SCRIPT_DIR = Path(__file__).resolve().parent
WOOJER_ROOT = SCRIPT_DIR.parent
REPO_ROOT = WOOJER_ROOT.parent
SRC_DIR = REPO_ROOT / "packages" / "pps-runtime" / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

SCHEMA = "pps-woojer-audio-loopback-stress.v1"
DEFAULT_SAMPLE_RATE = 44100
DEFAULT_LATENCY_S = 0.010
DEFAULT_BLOCKSIZE = 256
DEFAULT_PULSE_COUNT = 120
DEFAULT_PULSE_INTERVAL_MS = 500.0
DEFAULT_PULSE_DURATION_MS = 10.0
DEFAULT_PRE_ROLL_S = 1.0
DEFAULT_POST_ROLL_S = 1.0
DEFAULT_DRIVE_OUTPUT_CHANNEL = 3
DEFAULT_RETURN_INPUT_CHANNEL = 3
DEFAULT_DEVICE_QUERY = "Komplete"
SAFE_HARDWARE_AMPLITUDE_DEFAULT = 0.03
SAFE_HARDWARE_AMPLITUDE_MAX = 0.10
DEFAULT_MIN_PEAK = 0.001
DEFAULT_CLIPPING_ABS = 0.98
DEFAULT_MIN_DETECTION_RATE = 0.95
DEFAULT_MAX_P95_RESIDUAL_MS = 2.0
DEFAULT_MAX_RESIDUAL_MS = 5.0
DEFAULT_MAX_DRIFT_MS_PER_MIN = 0.5


def _default_output_root() -> Path:
    return WOOJER_ROOT / "runs"


def _timestamped_run_dir(root: Path, mode: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path(root) / f"{mode}_{stamp}"


def _as_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _stats(values: list[float]) -> dict[str, Any]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {
            "count": 0,
            "mean_ms": math.nan,
            "sd_ms": math.nan,
            "median_ms": math.nan,
            "p95_ms": math.nan,
            "min_ms": math.nan,
            "max_ms": math.nan,
        }
    ordered = sorted(finite)
    p95_idx = min(len(ordered) - 1, int(math.ceil(0.95 * len(ordered))) - 1)
    return {
        "count": len(finite),
        "mean_ms": float(statistics.fmean(finite)),
        "sd_ms": float(statistics.stdev(finite)) if len(finite) > 1 else 0.0,
        "median_ms": float(statistics.median(finite)),
        "p95_ms": float(ordered[p95_idx]),
        "min_ms": float(min(finite)),
        "max_ms": float(max(finite)),
    }


def _drift_ms_per_min(times_s: list[float], latencies_ms: list[float]) -> float:
    pairs = [
        (float(t), float(v))
        for t, v in zip(times_s, latencies_ms)
        if math.isfinite(float(t)) and math.isfinite(float(v))
    ]
    if len(pairs) < 2:
        return 0.0
    t = np.asarray([item[0] for item in pairs], dtype=np.float64)
    y = np.asarray([item[1] for item in pairs], dtype=np.float64)
    if float(np.max(t) - np.min(t)) <= 0:
        return 0.0
    slope, _intercept = np.polyfit(t / 60.0, y, 1)
    return float(slope) if math.isfinite(float(slope)) else math.nan


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


def build_pulse_stimulus(
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    output_channels: int = 4,
    drive_output_channel_1based: int = DEFAULT_DRIVE_OUTPUT_CHANNEL,
    pulse_count: int = DEFAULT_PULSE_COUNT,
    pulse_interval_ms: float = DEFAULT_PULSE_INTERVAL_MS,
    pulse_duration_ms: float = DEFAULT_PULSE_DURATION_MS,
    pre_roll_s: float = DEFAULT_PRE_ROLL_S,
    post_roll_s: float = DEFAULT_POST_ROLL_S,
    amplitude: float = SAFE_HARDWARE_AMPLITUDE_DEFAULT,
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    """Build a safe single-output biphasic pulse train."""

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if output_channels < 1:
        raise ValueError("output_channels must be at least 1")
    if not (1 <= drive_output_channel_1based <= output_channels):
        raise ValueError("drive output channel must be within the output stream width")
    if pulse_count < 1:
        raise ValueError("pulse_count must be at least 1")
    if pulse_interval_ms <= 0 or pulse_duration_ms <= 0:
        raise ValueError("pulse interval and duration must be positive")
    if pre_roll_s < 0 or post_roll_s < 0:
        raise ValueError("pre_roll_s and post_roll_s must be non-negative")
    if not (0 < amplitude <= SAFE_HARDWARE_AMPLITUDE_MAX):
        raise ValueError(f"amplitude must be in (0, {SAFE_HARDWARE_AMPLITUDE_MAX}]")

    drive_idx = drive_output_channel_1based - 1
    pulse_samples = max(2, int(round(pulse_duration_ms / 1000.0 * sample_rate)))
    half = max(1, pulse_samples // 2)
    pulse = np.empty(pulse_samples, dtype=np.float32)
    pulse[:half] = float(amplitude)
    pulse[half:] = -float(amplitude)
    interval_samples = max(pulse_samples + 1, int(round(pulse_interval_ms / 1000.0 * sample_rate)))
    first_sample = int(round(pre_roll_s * sample_rate))
    last_start = first_sample + (pulse_count - 1) * interval_samples
    frames = last_start + pulse_samples + int(round(post_roll_s * sample_rate))
    stimulus = np.zeros((frames, output_channels), dtype=np.float32)
    planned: list[dict[str, Any]] = []
    for pulse_index in range(1, pulse_count + 1):
        sample_index = first_sample + (pulse_index - 1) * interval_samples
        stimulus[sample_index : sample_index + pulse_samples, drive_idx] += pulse
        planned.append(
            {
                "pulse_index": pulse_index,
                "expected_sample_index": sample_index,
                "expected_time_s": sample_index / float(sample_rate),
                "drive_output_channel_1based": drive_output_channel_1based,
                "pulse_duration_samples": pulse_samples,
                "pulse_duration_ms": pulse_duration_ms,
                "amplitude": amplitude,
            }
        )
    manifest = {
        "schema": "pps-woojer-audio-pulse-stimulus.v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sample_rate": sample_rate,
        "output_channels": output_channels,
        "drive_output_channel_1based": drive_output_channel_1based,
        "pulse_count": pulse_count,
        "pulse_interval_ms": pulse_interval_ms,
        "pulse_duration_ms": pulse_duration_ms,
        "pre_roll_s": pre_roll_s,
        "post_roll_s": post_roll_s,
        "amplitude": amplitude,
        "measurement_scope": "Woojer audio pass-through only; not mechanical vibration onset.",
    }
    return stimulus, planned, manifest


def _threshold(
    signal: np.ndarray,
    *,
    min_peak: float = DEFAULT_MIN_PEAK,
    clipping_abs: float = DEFAULT_CLIPPING_ABS,
) -> tuple[float, float, bool, bool]:
    abs_signal = np.abs(np.asarray(signal, dtype=np.float64))
    peak = float(np.max(abs_signal)) if abs_signal.size else 0.0
    median = float(np.median(abs_signal)) if abs_signal.size else 0.0
    mad = float(np.median(np.abs(abs_signal - median))) if abs_signal.size else 0.0
    adaptive = median + 8.0 * max(mad, 1e-12)
    if peak > 0:
        adaptive = min(max(adaptive, float(min_peak)), peak * 0.50)
    threshold = max(float(min_peak), adaptive)
    return threshold, peak, peak < float(min_peak), peak >= float(clipping_abs)


def analyze_return_capture(
    capture: np.ndarray,
    planned_pulses: list[dict[str, Any]],
    *,
    sample_rate: int,
    return_input_channel_1based: int = DEFAULT_RETURN_INPUT_CHANNEL,
    search_pre_ms: float = 10.0,
    search_post_ms: float = 250.0,
    min_peak: float = DEFAULT_MIN_PEAK,
    clipping_abs: float = DEFAULT_CLIPPING_ABS,
    min_detection_rate: float = DEFAULT_MIN_DETECTION_RATE,
    max_p95_residual_ms: float = DEFAULT_MAX_P95_RESIDUAL_MS,
    max_residual_ms: float = DEFAULT_MAX_RESIDUAL_MS,
    max_drift_ms_per_min: float = DEFAULT_MAX_DRIFT_MS_PER_MIN,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Analyze a captured return channel against planned pulse samples."""

    if return_input_channel_1based < 1:
        raise ValueError("return input channel must be 1-based and positive")
    samples = np.asarray(capture, dtype=np.float32)
    if samples.ndim == 1:
        samples = samples[:, None]
    channel_idx = return_input_channel_1based - 1
    if channel_idx >= samples.shape[1]:
        signal = np.zeros(samples.shape[0] if samples.ndim == 2 else 0, dtype=np.float32)
        channel_error = f"capture has {samples.shape[1]} channel(s); requested input {return_input_channel_1based}"
    else:
        signal = samples[:, channel_idx]
        channel_error = ""

    threshold, peak, low_signal, clipped = _threshold(signal, min_peak=min_peak, clipping_abs=clipping_abs)
    pre = int(round(search_pre_ms / 1000.0 * sample_rate))
    post = int(round(search_post_ms / 1000.0 * sample_rate))
    event_rows: list[dict[str, Any]] = []
    latencies_ms: list[float] = []
    expected_times_s: list[float] = []
    for row in planned_pulses:
        expected_sample = int(row["expected_sample_index"])
        pulse_index = int(row["pulse_index"])
        expected_time_s = float(row["expected_time_s"])
        event = {
            "pulse_index": pulse_index,
            "expected_sample_index": expected_sample,
            "expected_time_s": f"{expected_time_s:.9f}",
            "detected": False,
            "detected_sample_index": "",
            "detected_time_s": "",
            "latency_ms": "",
            "residual_ms": "",
            "peak": peak,
            "threshold": threshold,
            "error": channel_error,
        }
        if channel_error or low_signal:
            event_rows.append(event)
            continue
        start = max(0, expected_sample - pre)
        stop = min(signal.shape[0], expected_sample + post)
        window = np.abs(signal[start:stop])
        hits = np.flatnonzero(window >= threshold)
        if hits.size:
            detected_sample = int(start + int(hits[0]))
            latency_ms = (detected_sample - expected_sample) / float(sample_rate) * 1000.0
            latencies_ms.append(latency_ms)
            expected_times_s.append(expected_time_s)
            event.update(
                {
                    "detected": True,
                    "detected_sample_index": detected_sample,
                    "detected_time_s": f"{detected_sample / float(sample_rate):.9f}",
                    "latency_ms": f"{latency_ms:.6f}",
                }
            )
        event_rows.append(event)

    median_latency = float(statistics.median(latencies_ms)) if latencies_ms else math.nan
    residuals_ms: list[float] = []
    for event in event_rows:
        latency = _as_float(event.get("latency_ms"))
        if math.isfinite(latency) and math.isfinite(median_latency):
            residual = latency - median_latency
            residuals_ms.append(abs(residual))
            event["residual_ms"] = f"{residual:.6f}"

    expected_count = len(planned_pulses)
    detected_count = len(latencies_ms)
    detection_rate = detected_count / float(expected_count or 1)
    latency_stats = _stats(latencies_ms)
    residual_stats = _stats(residuals_ms)
    drift = _drift_ms_per_min(expected_times_s, latencies_ms)
    checks = [
        {
            "name": "return_channel_available",
            "passed": not bool(channel_error),
            "value": "" if not channel_error else channel_error,
            "threshold": "requested input channel exists",
        },
        {
            "name": "detection_rate",
            "passed": detection_rate >= min_detection_rate,
            "value": detection_rate,
            "threshold": min_detection_rate,
        },
        {"name": "low_signal", "passed": not low_signal, "value": peak, "threshold": f">= {min_peak}"},
        {"name": "clipping", "passed": not clipped, "value": peak, "threshold": f"< {clipping_abs}"},
        {
            "name": "p95_residual_ms",
            "passed": math.isfinite(_as_float(residual_stats["p95_ms"]))
            and float(residual_stats["p95_ms"]) <= max_p95_residual_ms,
            "value": residual_stats["p95_ms"],
            "threshold": max_p95_residual_ms,
        },
        {
            "name": "max_residual_ms",
            "passed": math.isfinite(_as_float(residual_stats["max_ms"]))
            and float(residual_stats["max_ms"]) <= max_residual_ms,
            "value": residual_stats["max_ms"],
            "threshold": max_residual_ms,
        },
        {
            "name": "drift_ms_per_min",
            "passed": math.isfinite(drift) and abs(drift) <= max_drift_ms_per_min,
            "value": drift,
            "threshold": max_drift_ms_per_min,
        },
    ]
    analysis = {
        "passed": all(bool(check["passed"]) for check in checks),
        "status": "pass" if all(bool(check["passed"]) for check in checks) else "review_required",
        "expected_count": expected_count,
        "detected_count": detected_count,
        "detection_rate": detection_rate,
        "return_input_channel_1based": return_input_channel_1based,
        "latency_ms": latency_stats,
        "residual_jitter_ms": residual_stats,
        "drift_ms_per_min": drift,
        "signal_qc": {
            "peak": peak,
            "threshold": threshold,
            "low_signal": low_signal,
            "clipped": clipped,
            "min_peak": min_peak,
            "clipping_abs": clipping_abs,
        },
        "criteria": {
            "min_detection_rate": min_detection_rate,
            "max_p95_residual_ms": max_p95_residual_ms,
            "max_residual_ms": max_residual_ms,
            "max_drift_ms_per_min": max_drift_ms_per_min,
        },
        "checks": checks,
        "latency_values_ms": latencies_ms,
    }
    return event_rows, analysis


def load_baseline_report(path: Path) -> dict[str, Any]:
    path = Path(path)
    report_path = path if path.is_file() else path / "woojer_audio_loopback_report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"Baseline report not found: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def compare_with_baseline(
    analysis: dict[str, Any],
    baseline_report: dict[str, Any] | None,
    *,
    max_added_latency_ms: float | None = None,
) -> dict[str, Any]:
    if baseline_report is None:
        return {
            "status": "missing_baseline",
            "passed": True,
            "message": "No direct-baseline run was supplied; Woojer-added latency was not computed.",
        }
    baseline_analysis = baseline_report.get("analysis", {})
    baseline_median = _as_float(baseline_analysis.get("latency_ms", {}).get("median_ms"))
    current_values = [_as_float(value) for value in analysis.get("latency_values_ms", [])]
    current_values = [value for value in current_values if math.isfinite(value)]
    if not math.isfinite(baseline_median) or not current_values:
        return {
            "status": "unavailable",
            "passed": False,
            "message": "Baseline or current latency values are missing.",
        }
    added_values = [value - baseline_median for value in current_values]
    added_stats = _stats(added_values)
    checks: list[dict[str, Any]] = []
    if max_added_latency_ms is not None:
        checks.append(
            {
                "name": "p95_added_latency_ms",
                "passed": math.isfinite(_as_float(added_stats["p95_ms"]))
                and float(added_stats["p95_ms"]) <= float(max_added_latency_ms),
                "value": added_stats["p95_ms"],
                "threshold": max_added_latency_ms,
            }
        )
    return {
        "status": "compared",
        "passed": all(bool(check["passed"]) for check in checks) if checks else True,
        "baseline_run": baseline_report.get("run_dir") or baseline_report.get("run_id", ""),
        "baseline_mode": baseline_report.get("mode", ""),
        "baseline_median_latency_ms": baseline_median,
        "current_median_latency_ms": analysis.get("latency_ms", {}).get("median_ms"),
        "added_latency_ms": added_stats,
        "checks": checks,
    }


def build_report(
    *,
    mode: str,
    run_dir: Path,
    settings: dict[str, Any],
    analysis: dict[str, Any],
    route: dict[str, Any] | None = None,
    recording: dict[str, Any] | None = None,
    baseline_report: dict[str, Any] | None = None,
    max_added_latency_ms: float | None = None,
) -> dict[str, Any]:
    baseline_comparison = compare_with_baseline(
        analysis,
        baseline_report if mode == "woojer-loop" else None,
        max_added_latency_ms=max_added_latency_ms,
    )
    if mode == "direct-baseline":
        baseline_comparison = {
            "status": "not_applicable",
            "passed": True,
            "message": "Direct baseline run; no Woojer-added latency is computed.",
        }
    passed = bool(analysis.get("passed")) and bool(baseline_comparison.get("passed", True))
    report = {
        "schema": SCHEMA,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_id": Path(run_dir).name,
        "run_dir": str(run_dir),
        "mode": mode,
        "measurement_scope": "woojer_audio_pass_through_only",
        "passed": passed,
        "status": "pass" if passed else "review_required",
        "settings": settings,
        "route": route or {},
        "recording": recording or {},
        "analysis": analysis,
        "baseline_comparison": baseline_comparison,
        "limitations": [
            "This measures Woojer audio pass-through only, not mechanical vibration onset.",
            "A direct baseline is needed to estimate Woojer-added audio delay.",
            "Bluetooth Woojer routes are excluded from timing-sensitive use.",
            "The first implementation is measure-first unless max_added_latency_ms is supplied.",
        ],
    }
    return report


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_run_artifacts(
    run_dir: Path,
    *,
    stimulus: np.ndarray,
    capture: np.ndarray,
    sample_rate: int,
    planned_pulses: list[dict[str, Any]],
    stimulus_manifest: dict[str, Any],
    event_rows: list[dict[str, Any]],
    report: dict[str, Any],
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    sf.write(run_dir / "stimulus.wav", stimulus, sample_rate, subtype="PCM_24")
    sf.write(run_dir / "capture.wav", capture, sample_rate, subtype="PCM_24")
    _write_csv(run_dir / "planned_pulses.csv", planned_pulses)
    (run_dir / "stimulus_manifest.json").write_text(json.dumps(_json_ready(stimulus_manifest), indent=2), encoding="utf-8")
    _write_csv(run_dir / "woojer_audio_loopback_events.csv", event_rows)
    (run_dir / "woojer_audio_loopback_report.json").write_text(json.dumps(_json_ready(report), indent=2), encoding="utf-8")
    _write_markdown(run_dir / "woojer_audio_loopback_report.md", report)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    analysis = report["analysis"]
    baseline = report["baseline_comparison"]
    added = baseline.get("added_latency_ms", {})
    lines = [
        "# Woojer Audio Loopback Report",
        "",
        f"- Mode: `{report['mode']}`",
        f"- Passed: `{report['passed']}`",
        f"- Status: `{report['status']}`",
        f"- Run dir: `{report['run_dir']}`",
        f"- Detection: `{analysis['detected_count']}/{analysis['expected_count']}`",
        f"- Median latency ms: `{analysis['latency_ms']['median_ms']}`",
        f"- P95 latency ms: `{analysis['latency_ms']['p95_ms']}`",
        f"- P95 residual jitter ms: `{analysis['residual_jitter_ms']['p95_ms']}`",
        f"- Drift ms/min: `{analysis['drift_ms_per_min']}`",
        f"- Baseline comparison: `{baseline.get('status')}`",
    ]
    if added:
        lines.append(f"- Woojer-added median latency ms: `{added.get('median_ms')}`")
        lines.append(f"- Woojer-added p95 latency ms: `{added.get('p95_ms')}`")
    lines.extend(["", "## Checks", ""])
    for check in analysis.get("checks", []):
        lines.append(f"- `{check['name']}`: `{check['passed']}` value=`{check['value']}` threshold=`{check['threshold']}`")
    for check in baseline.get("checks", []):
        lines.append(f"- `{check['name']}`: `{check['passed']}` value=`{check['value']}` threshold=`{check['threshold']}`")
    lines.extend(["", "## Limitations", ""])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _tex_escape(value: Any) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def append_tex_log(report: dict[str, Any], *, tex_log: Path = WOOJER_ROOT / "woojer_latency_stress_log.tex") -> None:
    tex_log = Path(tex_log)
    text = tex_log.read_text(encoding="utf-8")
    marker = "% AUTO_LOG_ENTRIES_END"
    if marker not in text:
        raise ValueError(f"Could not find {marker} in {tex_log}")
    analysis = report["analysis"]
    baseline = report["baseline_comparison"]
    added = baseline.get("added_latency_ms", {})
    added_median = added.get("median_ms", "--") if added else "--"
    row = (
        f"{_tex_escape(report['created_at'])} & "
        f"\\texttt{{{_tex_escape(report['mode'])}}} & "
        f"\\texttt{{{_tex_escape(report['run_id'])}}} & "
        f"{analysis['detected_count']}/{analysis['expected_count']} & "
        f"{_format_ms(analysis['latency_ms'].get('median_ms'))} & "
        f"{_format_ms(added_median)} & "
        f"\\texttt{{{_tex_escape(report['status'])}}} \\\\\n"
    )
    text = text.replace(marker, row + marker)
    tex_log.write_text(text, encoding="utf-8")


def _format_ms(value: Any) -> str:
    number = _as_float(value)
    if not math.isfinite(number):
        return "--"
    return f"{number:.3f}"


def capture_live_asio(
    stimulus: np.ndarray,
    *,
    sample_rate: int,
    input_channels: int,
    output_channels: int,
    device: int | None = None,
    device_query: str = DEFAULT_DEVICE_QUERY,
    latency_s: float = DEFAULT_LATENCY_S,
    blocksize: int = DEFAULT_BLOCKSIZE,
    allow_non_asio: bool = False,
    capture_tail_s: float = 0.5,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Play the stimulus and record the Komplete inputs in one full-duplex stream."""

    from peripersonal_space_toolkit import latency_validation as lv

    sd = lv._load_sounddevice()
    device_idx, device_info, hostapi = lv._select_device(
        sd,
        device=device,
        device_query=device_query,
        require_asio=not allow_non_asio,
    )
    max_inputs = int(device_info.get("max_input_channels", 0))
    max_outputs = int(device_info.get("max_output_channels", 0))
    if input_channels > max_inputs:
        raise RuntimeError(f"selected device exposes {max_inputs} input channels, requested {input_channels}")
    if output_channels > max_outputs:
        raise RuntimeError(f"selected device exposes {max_outputs} output channels, requested {output_channels}")
    input_selectors = list(range(input_channels))
    output_selectors = list(range(output_channels))
    extra_settings = None
    if hostapi.lower() == "asio":
        extra_settings = (lv._asio_settings(sd, input_selectors), lv._asio_settings(sd, output_selectors))

    total_frames = stimulus.shape[0] + int(round(capture_tail_s * sample_rate))
    state: dict[str, Any] = {"pos": 0, "callbacks": 0, "statuses": [], "input_chunks": []}

    def callback(indata, outdata, frames, time_info, status):
        if status:
            state["statuses"].append(str(status))
        state["callbacks"] += 1
        start = int(state["pos"])
        stop = start + frames
        outdata.fill(0)
        if start < stimulus.shape[0]:
            n = min(frames, stimulus.shape[0] - start)
            outdata[:n, : stimulus.shape[1]] = stimulus[start : start + n, :]
        state["input_chunks"].append(np.array(indata[:, :input_channels], dtype=np.float32, copy=True))
        state["pos"] = stop
        if stop >= total_frames:
            raise sd.CallbackStop

    stream = sd.Stream(
        samplerate=sample_rate,
        blocksize=blocksize,
        dtype="float32",
        device=(device_idx, device_idx),
        channels=(input_channels, output_channels),
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

    capture = (
        np.concatenate(state["input_chunks"], axis=0)[:total_frames]
        if state["input_chunks"]
        else np.zeros((0, input_channels), dtype=np.float32)
    )
    route = lv.build_route_snapshot(
        device_name=str(device_info.get("name", "")),
        hostapi=hostapi,
        sample_rate=sample_rate,
        channels=output_channels,
        latency_s=latency_s,
        blocksize=blocksize,
        input_selectors=input_selectors,
        output_selectors=output_selectors,
        local_device_info=lv._jsonable_device_info(device_info, device_idx=device_idx, hostapi=hostapi),
    )
    route["input_channels"] = input_channels
    route["output_channels"] = output_channels
    status = {
        "route": route,
        "actual_latency": lv._latency_string(actual_latency),
        "cpu_load": f"{cpu_load:.6f}",
        "callback_count": state["callbacks"],
        "status_count": len(state["statuses"]),
        "status_messages": " | ".join(sorted(set(state["statuses"]))),
        "active_after_deadline": active_after_deadline,
        "elapsed_ms": (time.perf_counter() - start_time) * 1000.0,
    }
    return capture, status


def _resolve_output_channels(requested: int, drive_output_channel_1based: int) -> int:
    if requested > 0:
        return max(requested, drive_output_channel_1based)
    return max(4, drive_output_channel_1based)


def run_once(args: argparse.Namespace, *, repeat_index: int = 1) -> dict[str, Any]:
    output_root = Path(args.output_root)
    if args.repeats == 1:
        run_dir = Path(args.output_dir) if args.output_dir else _timestamped_run_dir(output_root, args.mode)
    else:
        base_dir = Path(args.output_dir) if args.output_dir else _timestamped_run_dir(output_root, args.mode)
        run_dir = base_dir / f"repeat_{repeat_index:02d}"
    output_channels = _resolve_output_channels(args.output_channels, args.drive_output_channel)
    input_channels = max(args.input_channels, args.return_input_channel)
    stimulus, planned, manifest = build_pulse_stimulus(
        sample_rate=args.sample_rate,
        output_channels=output_channels,
        drive_output_channel_1based=args.drive_output_channel,
        pulse_count=args.pulse_count,
        pulse_interval_ms=args.pulse_interval_ms,
        pulse_duration_ms=args.pulse_duration_ms,
        pre_roll_s=args.pre_roll_s,
        post_roll_s=args.post_roll_s,
        amplitude=args.amplitude,
    )
    capture, io_status = capture_live_asio(
        stimulus,
        sample_rate=args.sample_rate,
        input_channels=input_channels,
        output_channels=output_channels,
        device=args.device,
        device_query=args.device_query,
        latency_s=args.latency,
        blocksize=args.blocksize,
        allow_non_asio=args.allow_non_asio,
        capture_tail_s=args.capture_tail_s,
    )
    events, analysis = analyze_return_capture(
        capture,
        planned,
        sample_rate=args.sample_rate,
        return_input_channel_1based=args.return_input_channel,
        search_pre_ms=args.search_pre_ms,
        search_post_ms=args.search_post_ms,
        min_peak=args.min_peak,
    )
    settings = vars(args).copy()
    settings["repeat_index"] = repeat_index
    baseline_report = load_baseline_report(args.baseline_run) if args.baseline_run else None
    report = build_report(
        mode=args.mode,
        run_dir=run_dir,
        settings=settings,
        route=io_status.get("route", {}),
        recording=io_status,
        analysis=analysis,
        baseline_report=baseline_report,
        max_added_latency_ms=args.max_added_latency_ms,
    )
    write_run_artifacts(
        run_dir,
        stimulus=stimulus,
        capture=capture,
        sample_rate=args.sample_rate,
        planned_pulses=planned,
        stimulus_manifest=manifest,
        event_rows=events,
        report=report,
    )
    if args.append_tex_log:
        append_tex_log(report, tex_log=args.tex_log)
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Woojer audio pass-through loopback latency stress tests.")
    parser.add_argument("--mode", choices=["direct-baseline", "woojer-loop"], required=True)
    parser.add_argument("--baseline-run", type=Path, help="Direct-baseline run folder or report JSON for Woojer-added latency.")
    parser.add_argument("--output-root", type=Path, default=_default_output_root())
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    parser.add_argument("--device", type=int)
    parser.add_argument("--device-query", default=DEFAULT_DEVICE_QUERY)
    parser.add_argument("--allow-non-asio", action="store_true")
    parser.add_argument("--latency", type=float, default=DEFAULT_LATENCY_S)
    parser.add_argument("--blocksize", type=int, default=DEFAULT_BLOCKSIZE)
    parser.add_argument("--output-channels", type=int, default=0, help="0 means prefer a 4-channel stream when possible.")
    parser.add_argument("--input-channels", type=int, default=0, help="0 means enough channels to include the return input.")
    parser.add_argument("--drive-output-channel", type=int, default=DEFAULT_DRIVE_OUTPUT_CHANNEL)
    parser.add_argument("--return-input-channel", type=int, default=DEFAULT_RETURN_INPUT_CHANNEL)
    parser.add_argument("--pulse-count", type=int, default=DEFAULT_PULSE_COUNT)
    parser.add_argument("--pulse-interval-ms", type=float, default=DEFAULT_PULSE_INTERVAL_MS)
    parser.add_argument("--pulse-duration-ms", type=float, default=DEFAULT_PULSE_DURATION_MS)
    parser.add_argument("--pre-roll-s", type=float, default=DEFAULT_PRE_ROLL_S)
    parser.add_argument("--post-roll-s", type=float, default=DEFAULT_POST_ROLL_S)
    parser.add_argument("--amplitude", type=float, default=SAFE_HARDWARE_AMPLITUDE_DEFAULT)
    parser.add_argument("--capture-tail-s", type=float, default=0.5)
    parser.add_argument("--search-pre-ms", type=float, default=10.0)
    parser.add_argument("--search-post-ms", type=float, default=250.0)
    parser.add_argument("--min-peak", type=float, default=DEFAULT_MIN_PEAK)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-added-latency-ms", type=float)
    parser.add_argument("--append-tex-log", action="store_true")
    parser.add_argument("--tex-log", type=Path, default=WOOJER_ROOT / "woojer_latency_stress_log.tex")
    return parser


def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault("SD_ENABLE_ASIO", "1")
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.amplitude <= 0:
        parser.error("--amplitude must be positive")
    if args.amplitude > SAFE_HARDWARE_AMPLITUDE_MAX:
        parser.error(f"refusing amplitude above {SAFE_HARDWARE_AMPLITUDE_MAX}")
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    if args.repeats > 1 and args.output_dir is None:
        args.output_dir = _timestamped_run_dir(Path(args.output_root), args.mode)
    reports = []
    for repeat_index in range(1, args.repeats + 1):
        report = run_once(args, repeat_index=repeat_index)
        reports.append(report)
        print(f"Wrote {Path(report['run_dir']) / 'woojer_audio_loopback_report.json'}")
    return 0 if all(report["passed"] for report in reports) else 1


if __name__ == "__main__":
    raise SystemExit(main())
