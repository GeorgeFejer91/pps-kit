"""Compare Woojer mechanical sensor onset against electrical channel-3 drive.

This is an internal validation helper. It assumes an external contact
microphone, accelerometer, or vibration sensor is recorded in sync with the
electrical channel-3 drive. It does not play audio.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


SCHEMA = "pps-woojer-mechanical-onset-comparison.v1"
MIN_DETECTION_RATE = 0.95


def _default_output_dir() -> Path:
    return Path("artifacts") / "validation_runs" / f"woojer_mechanical_onset_{time.strftime('%Y%m%d_%H%M%S')}"


def _as_float(value: Any) -> float:
    try:
        result = float(str(value))
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
            "max_ms": math.nan,
            "min_ms": math.nan,
        }
    ordered = sorted(finite)
    p95_idx = min(len(ordered) - 1, int(math.ceil(0.95 * len(ordered))) - 1)
    return {
        "count": len(finite),
        "mean_ms": float(statistics.fmean(finite)),
        "sd_ms": float(statistics.stdev(finite)) if len(finite) > 1 else 0.0,
        "median_ms": float(statistics.median(finite)),
        "p95_ms": float(ordered[p95_idx]),
        "max_ms": float(max(finite)),
        "min_ms": float(min(finite)),
    }


def _read_signal(path: Path, *, channel_1based: int) -> tuple[np.ndarray, int]:
    if channel_1based < 1:
        raise ValueError("channel numbers are 1-based and must be positive")
    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    channel = channel_1based - 1
    if channel >= data.shape[1]:
        raise ValueError(f"{path} has {data.shape[1]} channel(s); requested channel {channel_1based}")
    return np.asarray(data[:, channel], dtype=np.float64), int(sample_rate)


def _read_planned_samples(path: Path, *, electrical_channel_1based: int) -> list[dict[str, int]]:
    rows: list[dict[str, int]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            channel_number = int(row.get("channel_number") or int(row.get("channel", "0")) + 1)
            if channel_number != electrical_channel_1based:
                continue
            rows.append(
                {
                    "pulse_index": int(row.get("pulse_index", len(rows) + 1)),
                    "expected_sample_index": int(row.get("expected_sample_index") or row.get("nominal_sample_index")),
                }
            )
    rows.sort(key=lambda row: row["pulse_index"])
    return rows


def _threshold(signal: np.ndarray, *, min_peak: float, multiplier: float) -> tuple[float, float, bool]:
    abs_signal = np.abs(np.asarray(signal, dtype=np.float64))
    peak = float(np.max(abs_signal)) if abs_signal.size else 0.0
    median = float(np.median(abs_signal)) if abs_signal.size else 0.0
    mad = float(np.median(np.abs(abs_signal - median))) if abs_signal.size else 0.0
    adaptive = median + float(multiplier) * max(mad, 1e-12)
    if peak > 0:
        adaptive = min(max(adaptive, float(min_peak)), peak * 0.50)
    threshold = max(float(min_peak), adaptive)
    return threshold, peak, peak < min_peak


def _detect_first(
    signal: np.ndarray,
    *,
    expected_sample: int,
    sample_rate: int,
    search_pre_ms: float,
    search_post_ms: float,
    threshold: float,
    min_peak: float,
) -> dict[str, Any]:
    pre = int(round(float(search_pre_ms) / 1000.0 * sample_rate))
    post = int(round(float(search_post_ms) / 1000.0 * sample_rate))
    start = max(0, int(expected_sample) - pre)
    stop = min(signal.shape[0], int(expected_sample) + post)
    window = signal[start:stop]
    peak = float(np.max(np.abs(window))) if window.size else 0.0
    if peak < min_peak or not window.size:
        return {
            "detected": False,
            "sample_index": None,
            "peak": peak,
            "threshold": threshold,
            "low_signal": True,
        }
    above = np.flatnonzero(np.abs(window) >= threshold)
    if above.size == 0:
        return {
            "detected": False,
            "sample_index": None,
            "peak": peak,
            "threshold": threshold,
            "low_signal": False,
        }
    return {
        "detected": True,
        "sample_index": int(start + int(above[0])),
        "peak": peak,
        "threshold": threshold,
        "low_signal": False,
    }


def _write_pairs_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Woojer Mechanical Onset Comparison",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Expected pulses: `{report['expected_count']}`",
        f"- Electrical detections: `{report['electrical_detected_count']}`",
        f"- Sensor detections: `{report['sensor_detected_count']}`",
        f"- Sensor/electrical detection rate: `{report['sensor_detection_rate']}`",
        f"- Mechanical minus electrical ms: `{json.dumps(report['mechanical_minus_electrical_ms'], sort_keys=True)}`",
        f"- Electrical minus planned ms: `{json.dumps(report['electrical_minus_planned_ms'], sort_keys=True)}`",
        "",
        "## Interpretation",
        "",
        "Mechanical-minus-electrical is the estimated vibration sensor onset delay after the electrical channel-3 drive is detected.",
        "Negative values can indicate electrical crosstalk into the sensor channel or poor sensor mounting.",
        "",
        "## Limitations",
        "",
    ]
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_mechanical_onset(
    *,
    planned_pulses_csv: Path,
    electrical_recording: Path,
    sensor_recording: Path,
    output_dir: Path,
    electrical_channel_1based: int = 3,
    sensor_channel_1based: int = 4,
    electrical_search_pre_ms: float = 10.0,
    electrical_search_post_ms: float = 150.0,
    sensor_search_pre_ms: float = 2.0,
    sensor_search_post_ms: float = 250.0,
    min_electrical_peak: float = 0.005,
    min_sensor_peak: float = 0.0005,
    threshold_multiplier: float = 8.0,
    max_mechanical_latency_ms: float = 150.0,
    max_negative_latency_ms: float = 1.0,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    planned = _read_planned_samples(planned_pulses_csv, electrical_channel_1based=electrical_channel_1based)
    electrical, electrical_rate = _read_signal(electrical_recording, channel_1based=electrical_channel_1based)
    sensor, sensor_rate = _read_signal(sensor_recording, channel_1based=sensor_channel_1based)
    if electrical_rate != sensor_rate:
        raise ValueError(f"sample rate mismatch: electrical={electrical_rate}, sensor={sensor_rate}")
    sample_rate = electrical_rate

    electrical_threshold, electrical_peak, electrical_low = _threshold(
        electrical,
        min_peak=min_electrical_peak,
        multiplier=threshold_multiplier,
    )
    sensor_threshold, sensor_peak, sensor_low = _threshold(
        sensor,
        min_peak=min_sensor_peak,
        multiplier=threshold_multiplier,
    )

    pairs: list[dict[str, Any]] = []
    for row in planned:
        pulse_index = row["pulse_index"]
        planned_sample = row["expected_sample_index"]
        electrical_detection = _detect_first(
            electrical,
            expected_sample=planned_sample,
            sample_rate=sample_rate,
            search_pre_ms=electrical_search_pre_ms,
            search_post_ms=electrical_search_post_ms,
            threshold=electrical_threshold,
            min_peak=min_electrical_peak,
        )
        electrical_sample = electrical_detection["sample_index"]
        sensor_detection = {
            "detected": False,
            "sample_index": None,
            "peak": math.nan,
            "threshold": sensor_threshold,
            "low_signal": sensor_low,
        }
        if electrical_sample is not None:
            sensor_detection = _detect_first(
                sensor,
                expected_sample=int(electrical_sample),
                sample_rate=sample_rate,
                search_pre_ms=sensor_search_pre_ms,
                search_post_ms=sensor_search_post_ms,
                threshold=sensor_threshold,
                min_peak=min_sensor_peak,
            )
        sensor_sample = sensor_detection["sample_index"]
        electrical_minus_planned_ms = (
            (int(electrical_sample) - planned_sample) / float(sample_rate) * 1000.0
            if electrical_sample is not None
            else math.nan
        )
        mechanical_minus_electrical_ms = (
            (int(sensor_sample) - int(electrical_sample)) / float(sample_rate) * 1000.0
            if electrical_sample is not None and sensor_sample is not None
            else math.nan
        )
        pairs.append(
            {
                "pulse_index": pulse_index,
                "planned_sample_index": planned_sample,
                "electrical_detected": bool(electrical_detection["detected"]),
                "electrical_sample_index": "" if electrical_sample is None else int(electrical_sample),
                "sensor_detected": bool(sensor_detection["detected"]),
                "sensor_sample_index": "" if sensor_sample is None else int(sensor_sample),
                "electrical_minus_planned_ms": electrical_minus_planned_ms,
                "mechanical_minus_electrical_ms": mechanical_minus_electrical_ms,
                "electrical_peak": electrical_detection["peak"],
                "sensor_peak": sensor_detection["peak"],
                "electrical_threshold": electrical_threshold,
                "sensor_threshold": sensor_threshold,
            }
        )

    expected_count = len(planned)
    electrical_detected = sum(1 for row in pairs if row["electrical_detected"])
    sensor_detected = sum(1 for row in pairs if row["sensor_detected"])
    electrical_rate_detected = electrical_detected / float(expected_count or 1)
    sensor_rate_detected = sensor_detected / float(expected_count or 1)
    electrical_minus_planned = [_as_float(row["electrical_minus_planned_ms"]) for row in pairs if row["electrical_detected"]]
    mechanical_minus_electrical = [
        _as_float(row["mechanical_minus_electrical_ms"])
        for row in pairs
        if row["electrical_detected"] and row["sensor_detected"]
    ]
    mechanical_stats = _stats(mechanical_minus_electrical)
    electrical_stats = _stats(electrical_minus_planned)
    passed = (
        expected_count > 0
        and electrical_rate_detected >= MIN_DETECTION_RATE
        and sensor_rate_detected >= MIN_DETECTION_RATE
        and not electrical_low
        and not sensor_low
        and math.isfinite(mechanical_stats["min_ms"])
        and mechanical_stats["min_ms"] >= -float(max_negative_latency_ms)
        and mechanical_stats["p95_ms"] <= float(max_mechanical_latency_ms)
    )
    report = {
        "schema": SCHEMA,
        "planned_pulses_csv": str(planned_pulses_csv),
        "electrical_recording": str(electrical_recording),
        "sensor_recording": str(sensor_recording),
        "electrical_channel_1based": electrical_channel_1based,
        "sensor_channel_1based": sensor_channel_1based,
        "sample_rate": sample_rate,
        "passed": passed,
        "status": "pass" if passed else "review_required",
        "expected_count": expected_count,
        "electrical_detected_count": electrical_detected,
        "sensor_detected_count": sensor_detected,
        "electrical_detection_rate": electrical_rate_detected,
        "sensor_detection_rate": sensor_rate_detected,
        "electrical_minus_planned_ms": electrical_stats,
        "mechanical_minus_electrical_ms": mechanical_stats,
        "signal_qc": {
            "electrical_peak": electrical_peak,
            "electrical_threshold": electrical_threshold,
            "electrical_low_signal": electrical_low,
            "sensor_peak": sensor_peak,
            "sensor_threshold": sensor_threshold,
            "sensor_low_signal": sensor_low,
        },
        "criteria": {
            "min_detection_rate": MIN_DETECTION_RATE,
            "max_mechanical_latency_ms": max_mechanical_latency_ms,
            "max_negative_latency_ms": max_negative_latency_ms,
        },
        "pairs": pairs,
        "limitations": [
            "This requires a real external vibration/contact sensor mechanically coupled to the Woojer.",
            "It estimates mechanical sensor onset relative to electrical channel-3 drive, not subjective tactile perception.",
            "Sensor mounting, sensor driver latency, and electrical crosstalk can affect onset estimates and must be documented.",
        ],
    }
    (output_dir / "woojer_mechanical_onset_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_pairs_csv(output_dir / "woojer_mechanical_onset_pairs.csv", pairs)
    _write_markdown(output_dir / "woojer_mechanical_onset_report.md", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare Woojer vibration sensor onset against electrical channel-3 drive.")
    parser.add_argument("--run-dir", type=Path, help="Dummy-pulse run directory containing planned_pulses.csv and direct_loopback_capture.wav.")
    parser.add_argument("--planned-pulses-csv", type=Path)
    parser.add_argument("--recording", type=Path, help="Single synchronized WAV containing both electrical and sensor channels.")
    parser.add_argument("--electrical-recording", type=Path)
    parser.add_argument("--sensor-recording", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--electrical-channel", type=int, default=3)
    parser.add_argument("--sensor-channel", type=int, default=4)
    parser.add_argument("--electrical-search-pre-ms", type=float, default=10.0)
    parser.add_argument("--electrical-search-post-ms", type=float, default=150.0)
    parser.add_argument("--sensor-search-pre-ms", type=float, default=2.0)
    parser.add_argument("--sensor-search-post-ms", type=float, default=250.0)
    parser.add_argument("--min-electrical-peak", type=float, default=0.005)
    parser.add_argument("--min-sensor-peak", type=float, default=0.0005)
    parser.add_argument("--threshold-multiplier", type=float, default=8.0)
    parser.add_argument("--max-mechanical-latency-ms", type=float, default=150.0)
    parser.add_argument("--max-negative-latency-ms", type=float, default=1.0)
    args = parser.parse_args(argv)

    planned = args.planned_pulses_csv
    if planned is None:
        if args.run_dir is None:
            parser.error("--planned-pulses-csv or --run-dir is required")
        planned = args.run_dir / "planned_pulses.csv"

    electrical_recording = args.electrical_recording or args.recording
    sensor_recording = args.sensor_recording or args.recording
    if electrical_recording is None:
        if args.run_dir is None:
            parser.error("--recording, --electrical-recording, or --run-dir is required")
        electrical_recording = args.run_dir / "direct_loopback_capture.wav"
    if sensor_recording is None:
        parser.error("--recording or --sensor-recording is required for the external sensor channel")

    output_dir = args.output_dir or _default_output_dir()
    report = compare_mechanical_onset(
        planned_pulses_csv=planned,
        electrical_recording=electrical_recording,
        sensor_recording=sensor_recording,
        output_dir=output_dir,
        electrical_channel_1based=args.electrical_channel,
        sensor_channel_1based=args.sensor_channel,
        electrical_search_pre_ms=args.electrical_search_pre_ms,
        electrical_search_post_ms=args.electrical_search_post_ms,
        sensor_search_pre_ms=args.sensor_search_pre_ms,
        sensor_search_post_ms=args.sensor_search_post_ms,
        min_electrical_peak=args.min_electrical_peak,
        min_sensor_peak=args.min_sensor_peak,
        threshold_multiplier=args.threshold_multiplier,
        max_mechanical_latency_ms=args.max_mechanical_latency_ms,
        max_negative_latency_ms=args.max_negative_latency_ms,
    )
    print(f"Wrote Woojer mechanical onset report: {output_dir / 'woojer_mechanical_onset_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
