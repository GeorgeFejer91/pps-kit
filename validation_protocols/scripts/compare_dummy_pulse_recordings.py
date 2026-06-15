"""Compare dummy 3-channel pulse recordings against the generated source WAV."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from make_dummy_pulse_stimulus import CHANNEL_CODES, channel_template  # noqa: E402
from make_dummy_pulse_stimulus import channel_amplitude_for  # noqa: E402


MIN_DETECTION_RATE = 0.95
MIN_PEAK = 0.015
MAX_LEFT_RIGHT_SKEW_MS = 1.0
MAX_TACTILE_AUDIO_SKEW_MS = 2.0
MAX_P95_RESIDUAL_MS = 2.0
MAX_RESIDUAL_MS = 5.0
MIN_SHAPE_CORRELATION = 0.70
MIN_IDENTITY_MARGIN = 0.08
DEFAULT_SEARCH_PRE_MS = 50.0
DEFAULT_SEARCH_POST_MS = 200.0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _as_2d_float(samples: np.ndarray) -> np.ndarray:
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim == 1:
        return samples[:, None]
    return samples


def _channel_threshold(signal: np.ndarray) -> tuple[float, float, bool, bool]:
    abs_signal = np.abs(signal.astype(np.float64, copy=False))
    peak = float(np.max(abs_signal)) if abs_signal.size else 0.0
    median = float(np.median(abs_signal)) if abs_signal.size else 0.0
    mad = float(np.median(np.abs(abs_signal - median))) if abs_signal.size else 0.0
    adaptive = median + 8.0 * max(mad, 1e-9)
    if peak > 0:
        adaptive = min(max(adaptive, MIN_PEAK), peak * 0.50)
    threshold = max(MIN_PEAK, adaptive)
    return threshold, peak, peak < MIN_PEAK, peak >= 0.98


def _detect_runs(signal: np.ndarray, *, min_width_samples: int) -> tuple[list[int], dict[str, Any]]:
    threshold, peak, low_signal, clipped = _channel_threshold(signal)
    if low_signal:
        return [], {"threshold": threshold, "peak": peak, "low_signal": low_signal, "clipped": clipped}
    above = np.flatnonzero(np.abs(signal) >= threshold)
    if above.size == 0:
        return [], {"threshold": threshold, "peak": peak, "low_signal": low_signal, "clipped": clipped}
    starts = [int(above[0])]
    previous = int(above[0])
    for sample in above[1:]:
        sample = int(sample)
        if sample > previous + max(2, min_width_samples // 4):
            starts.append(sample)
        previous = sample
    return starts, {"threshold": threshold, "peak": peak, "low_signal": low_signal, "clipped": clipped}


def _select_candidate_start(
    starts: list[int],
    *,
    signal: np.ndarray,
    templates: dict[int, np.ndarray],
    expected: int,
    intended_channel: int,
    sample_rate: int,
    used_starts: set[int],
    search_pre_ms: float,
    search_post_ms: float,
) -> int | None:
    pre = int(round((search_pre_ms / 1000.0) * sample_rate))
    post = int(round((search_post_ms / 1000.0) * sample_rate))
    lower = expected - pre
    upper = expected + post
    candidates = [start for start in starts if lower <= start <= upper and start not in used_starts]
    if not candidates:
        return None

    intended_template = templates[intended_channel]

    def score(start: int) -> tuple[float, float]:
        segment = signal[start : start + len(intended_template)]
        corr = abs(_normalized_correlation(segment, intended_template))
        distance_ms = abs(start - expected) / float(sample_rate) * 1000.0
        return (corr, -distance_ms)

    return max(candidates, key=score)


def _normalized_correlation(segment: np.ndarray, template: np.ndarray) -> float:
    n = min(len(segment), len(template))
    if n <= 1:
        return 0.0
    a = np.asarray(segment[:n], dtype=np.float64)
    b = np.asarray(template[:n], dtype=np.float64)
    a = a - float(np.mean(a))
    b = b - float(np.mean(b))
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return math.nan
    return float(np.percentile(np.asarray(values, dtype=np.float64), percentile))


def _mean_sd(values: list[float]) -> tuple[float, float]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return math.nan, math.nan
    mean = float(statistics.fmean(finite))
    sd = float(statistics.stdev(finite)) if len(finite) > 1 else 0.0
    return mean, sd


def _planned_by_channel(planned_rows: list[dict[str, str]]) -> dict[int, list[dict[str, str]]]:
    by_channel: dict[int, list[dict[str, str]]] = {}
    for row in planned_rows:
        by_channel.setdefault(int(row["channel"]), []).append(row)
    for rows in by_channel.values():
        rows.sort(key=lambda row: int(row["pulse_index"]))
    return by_channel


def compare_capture(
    capture_path: Path,
    *,
    planned_rows: list[dict[str, str]],
    manifest: dict[str, Any],
    capture_name: str,
    search_pre_ms: float = DEFAULT_SEARCH_PRE_MS,
    search_post_ms: float = DEFAULT_SEARCH_POST_MS,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    samples, capture_rate = sf.read(capture_path, dtype="float32", always_2d=True)
    samples = _as_2d_float(samples)
    sample_rate = int(manifest["sample_rate"])
    if int(capture_rate) != sample_rate:
        raise ValueError(f"{capture_path} sample rate {capture_rate} does not match planned {sample_rate}")

    planned = _planned_by_channel(planned_rows)
    expected_count = len(next(iter(planned.values()))) if planned else 0
    templates = {
        code.channel: channel_template(code, sample_rate=sample_rate, amplitude=channel_amplitude_for(manifest, code.channel))
        for code in CHANNEL_CODES
    }
    min_width_samples = max(2, min(len(template) for template in templates.values()) // 2)
    detection_rows: list[dict[str, Any]] = []
    channel_summaries: list[dict[str, Any]] = []
    median_latencies_ms: dict[int, float] = {}
    identity_ok = True

    for input_channel in range(min(samples.shape[1], len(CHANNEL_CODES))):
        signal = samples[:, input_channel]
        candidate_starts, profile = _detect_runs(signal, min_width_samples=min_width_samples)
        intended_rows = planned.get(input_channel, [])
        expected_samples = [int(row["expected_sample_index"]) for row in intended_rows]
        used_starts: set[int] = set()
        paired_starts: list[int | None] = []
        for expected in expected_samples:
            detected = _select_candidate_start(
                candidate_starts,
                signal=signal,
                templates=templates,
                expected=expected,
                intended_channel=input_channel,
                sample_rate=sample_rate,
                used_starts=used_starts,
                search_pre_ms=search_pre_ms,
                search_post_ms=search_post_ms,
            )
            if detected is not None:
                used_starts.add(detected)
            paired_starts.append(detected)
        offset = paired_starts[0] - expected_samples[0] if paired_starts and paired_starts[0] is not None and expected_samples else 0
        latencies_ms: list[float] = []
        residuals_ms: list[float] = []
        intended_corrs: list[float] = []
        identity_votes: list[int] = []

        for idx, planned_row in enumerate(intended_rows):
            detected = paired_starts[idx] if idx < len(paired_starts) else None
            expected = int(planned_row["expected_sample_index"])
            if detected is None:
                detection_rows.append(
                    {
                        "capture": capture_name,
                        "input_channel": input_channel,
                        "pulse_index": int(planned_row["pulse_index"]),
                        "detected": False,
                        "expected_sample_index": expected,
                        "detected_sample_index": "",
                        "latency_ms": "",
                        "residual_ms": "",
                        "best_source_channel": "",
                        "best_shape_correlation": "",
                        "intended_shape_correlation": "",
                    }
                )
                continue
            source_scores: dict[int, float] = {}
            for source_channel, template in templates.items():
                segment = signal[detected : detected + len(template)]
                source_scores[source_channel] = abs(_normalized_correlation(segment, template))
            best_source = max(source_scores, key=source_scores.get)
            best_corr = source_scores[best_source]
            intended_corr = source_scores.get(input_channel, 0.0)
            latency_ms = (detected - expected) / float(sample_rate) * 1000.0
            residual_ms = (detected - (expected + offset)) / float(sample_rate) * 1000.0
            latencies_ms.append(latency_ms)
            residuals_ms.append(residual_ms)
            intended_corrs.append(intended_corr)
            identity_votes.append(best_source)
            detection_rows.append(
                {
                    "capture": capture_name,
                    "input_channel": input_channel,
                    "pulse_index": int(planned_row["pulse_index"]),
                    "detected": True,
                    "expected_sample_index": expected,
                    "detected_sample_index": detected,
                    "latency_ms": f"{latency_ms:.6f}",
                    "residual_ms": f"{residual_ms:.6f}",
                    "best_source_channel": best_source,
                    "best_shape_correlation": f"{best_corr:.6f}",
                    "intended_shape_correlation": f"{intended_corr:.6f}",
                }
            )

        detection_rate = len(latencies_ms) / float(len(intended_rows) or 1)
        vote_counts = {channel: identity_votes.count(channel) for channel in range(len(CHANNEL_CODES))}
        best_identity = max(vote_counts, key=vote_counts.get) if identity_votes else None
        sorted_corrs = sorted(intended_corrs, reverse=True)
        mean_latency, sd_latency = _mean_sd(latencies_ms)
        median_latency = float(np.median(latencies_ms)) if latencies_ms else math.nan
        median_latencies_ms[input_channel] = median_latency
        mean_residual, sd_residual = _mean_sd([abs(value) for value in residuals_ms])
        p95_residual = _percentile([abs(value) for value in residuals_ms], 95)
        max_residual = max([abs(value) for value in residuals_ms], default=math.nan)
        median_intended_corr = float(np.median(intended_corrs)) if intended_corrs else math.nan
        identity_margin = (
            float(sorted_corrs[0] - sorted_corrs[1])
            if len(sorted_corrs) >= 2
            else (float(sorted_corrs[0]) if sorted_corrs else math.nan)
        )
        channel_identity_ok = best_identity == input_channel and median_intended_corr >= MIN_SHAPE_CORRELATION
        identity_ok = identity_ok and channel_identity_ok
        channel_summaries.append(
            {
                "input_channel": input_channel,
                "expected_source_channel": input_channel,
                "best_identity_source_channel": best_identity,
                "identity_ok": channel_identity_ok,
                "detection_rate": detection_rate,
                "detected_count": len(latencies_ms),
                "planned_count": len(intended_rows),
                "mean_latency_ms": mean_latency,
                "sd_latency_ms": sd_latency,
                "median_latency_ms": median_latency,
                "mean_abs_residual_ms": mean_residual,
                "sd_abs_residual_ms": sd_residual,
                "p95_abs_residual_ms": p95_residual,
                "max_abs_residual_ms": max_residual,
                "median_intended_shape_correlation": median_intended_corr,
                "identity_margin": identity_margin,
                "low_signal": bool(profile["low_signal"]),
                "clipped": bool(profile["clipped"]),
                "peak": profile["peak"],
                "threshold": profile["threshold"],
            }
        )

    left_right_skew = abs(median_latencies_ms.get(0, math.nan) - median_latencies_ms.get(1, math.nan))
    all_channels_finite = all(math.isfinite(median_latencies_ms.get(channel, math.nan)) for channel in (0, 1, 2))
    audio_median = (
        float(np.median([median_latencies_ms[channel] for channel in (0, 1)]))
        if all_channels_finite
        else math.nan
    )
    tactile_audio_skew = abs(median_latencies_ms.get(2, math.nan) - audio_median) if all_channels_finite else math.nan
    tactile_left_skew = abs(median_latencies_ms.get(2, math.nan) - median_latencies_ms.get(0, math.nan))
    latencies_by_pulse: dict[int, dict[int, float]] = {}
    for row in detection_rows:
        if row.get("detected") and str(row.get("latency_ms", "")).strip():
            latencies_by_pulse.setdefault(int(row["pulse_index"]), {})[int(row["input_channel"])] = float(row["latency_ms"])
    left_right_pair_skews = [
        abs(channels[1] - channels[0])
        for channels in latencies_by_pulse.values()
        if 0 in channels and 1 in channels
    ]
    tactile_audio_pair_skews = [
        abs(channels[2] - ((channels[0] + channels[1]) / 2.0))
        for channels in latencies_by_pulse.values()
        if 0 in channels and 1 in channels and 2 in channels
    ]
    tactile_left_pair_skews = [
        abs(channels[2] - channels[0])
        for channels in latencies_by_pulse.values()
        if 0 in channels and 2 in channels
    ]
    tactile_right_pair_skews = [
        abs(channels[2] - channels[1])
        for channels in latencies_by_pulse.values()
        if 1 in channels and 2 in channels
    ]
    left_right_pair_mean, left_right_pair_sd = _mean_sd(left_right_pair_skews)
    tactile_audio_pair_mean, tactile_audio_pair_sd = _mean_sd(tactile_audio_pair_skews)
    tactile_left_pair_mean, tactile_left_pair_sd = _mean_sd(tactile_left_pair_skews)
    tactile_right_pair_mean, tactile_right_pair_sd = _mean_sd(tactile_right_pair_skews)
    checks = [
        {
            "name": "three_channel_capture_available",
            "passed": samples.shape[1] >= 3,
            "value": int(samples.shape[1]),
            "threshold": ">= 3",
        },
        {
            "name": "channel_identity",
            "passed": identity_ok,
            "value": [row["best_identity_source_channel"] for row in channel_summaries],
            "threshold": [0, 1, 2],
        },
        {
            "name": "left_right_skew_ms",
            "passed": math.isfinite(left_right_skew) and left_right_skew <= MAX_LEFT_RIGHT_SKEW_MS,
            "value": left_right_skew,
            "threshold": MAX_LEFT_RIGHT_SKEW_MS,
        },
        {
            "name": "tactile_audio_skew_ms",
            "passed": math.isfinite(tactile_audio_skew) and tactile_audio_skew <= MAX_TACTILE_AUDIO_SKEW_MS,
            "value": tactile_audio_skew,
            "threshold": MAX_TACTILE_AUDIO_SKEW_MS,
        },
    ]
    for summary in channel_summaries:
        channel = summary["input_channel"]
        checks.extend(
            [
                {
                    "name": f"channel_{channel + 1}_detection_rate",
                    "passed": summary["detection_rate"] >= MIN_DETECTION_RATE,
                    "value": summary["detection_rate"],
                    "threshold": MIN_DETECTION_RATE,
                },
                {
                    "name": f"channel_{channel + 1}_shape_correlation",
                    "passed": math.isfinite(summary["median_intended_shape_correlation"]) and summary["median_intended_shape_correlation"] >= MIN_SHAPE_CORRELATION,
                    "value": summary["median_intended_shape_correlation"],
                    "threshold": MIN_SHAPE_CORRELATION,
                },
                {
                    "name": f"channel_{channel + 1}_p95_residual_ms",
                    "passed": math.isfinite(summary["p95_abs_residual_ms"]) and summary["p95_abs_residual_ms"] <= MAX_P95_RESIDUAL_MS,
                    "value": summary["p95_abs_residual_ms"],
                    "threshold": MAX_P95_RESIDUAL_MS,
                },
                {
                    "name": f"channel_{channel + 1}_max_residual_ms",
                    "passed": math.isfinite(summary["max_abs_residual_ms"]) and summary["max_abs_residual_ms"] <= MAX_RESIDUAL_MS,
                    "value": summary["max_abs_residual_ms"],
                    "threshold": MAX_RESIDUAL_MS,
                },
                {
                    "name": f"channel_{channel + 1}_low_signal",
                    "passed": not summary["low_signal"],
                    "value": summary["low_signal"],
                    "threshold": False,
                },
                {
                    "name": f"channel_{channel + 1}_clipping",
                    "passed": not summary["clipped"],
                    "value": summary["clipped"],
                    "threshold": False,
                },
            ]
        )

    summary = {
        "capture": capture_name,
        "path": str(capture_path),
        "sample_rate": sample_rate,
        "frames": int(samples.shape[0]),
        "channels": int(samples.shape[1]),
        "channel_summaries": channel_summaries,
        "skew_summary": {
            "left_right_median_abs_skew_ms": left_right_skew,
            "left_right_paired_count": len(left_right_pair_skews),
            "left_right_mean_abs_skew_ms": left_right_pair_mean,
            "left_right_sd_abs_skew_ms": left_right_pair_sd,
            "tactile_audio_median_abs_skew_ms": tactile_audio_skew,
            "tactile_audio_paired_count": len(tactile_audio_pair_skews),
            "tactile_audio_mean_abs_skew_ms": tactile_audio_pair_mean,
            "tactile_audio_sd_abs_skew_ms": tactile_audio_pair_sd,
            "tactile_left_median_abs_skew_ms": tactile_left_skew,
            "tactile_left_paired_count": len(tactile_left_pair_skews),
            "tactile_left_mean_abs_skew_ms": tactile_left_pair_mean,
            "tactile_left_sd_abs_skew_ms": tactile_left_pair_sd,
            "tactile_right_paired_count": len(tactile_right_pair_skews),
            "tactile_right_mean_abs_skew_ms": tactile_right_pair_mean,
            "tactile_right_sd_abs_skew_ms": tactile_right_pair_sd,
        },
        "checks": checks,
        "passed": all(bool(check["passed"]) for check in checks),
        "limitations": [
            "Direct electrical channel-3 timing is not Woojer mechanical onset.",
            "WASAPI capture may include unknown start offset and may not represent ASIO multichannel playback.",
        ],
    }
    return detection_rows, summary


def _write_detection_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Dummy 3-Channel Pulse Validation Report",
        "",
        f"- Run dir: `{report['run_dir']}`",
        f"- Status: `{report['status']}`",
        f"- Passed: `{report['passed']}`",
        "",
        "## Capture Results",
        "",
    ]
    for capture in report["captures"]:
        lines.extend(
            [
                f"### {capture['capture']}",
                "",
                f"- Passed: `{capture['passed']}`",
                f"- Channels: {capture['channels']}",
                f"- Left/right skew ms: {capture['skew_summary']['left_right_median_abs_skew_ms']:.6f}",
                f"- Left/right paired skew mean +/- SD ms: {capture['skew_summary'].get('left_right_mean_abs_skew_ms', math.nan):.6f} +/- {capture['skew_summary'].get('left_right_sd_abs_skew_ms', math.nan):.6f}",
                f"- Tactile/audio skew ms: {capture['skew_summary']['tactile_audio_median_abs_skew_ms']:.6f}",
                f"- Tactile/audio paired skew mean +/- SD ms: {capture['skew_summary'].get('tactile_audio_mean_abs_skew_ms', math.nan):.6f} +/- {capture['skew_summary'].get('tactile_audio_sd_abs_skew_ms', math.nan):.6f}",
                f"- Tactile/left skew ms: {capture['skew_summary'].get('tactile_left_median_abs_skew_ms', math.nan):.6f}",
                "",
            ]
        )
        for channel in capture["channel_summaries"]:
            lines.append(
                "- Input channel {idx}: identity={identity}, detection={rate:.3f}, "
                "mean latency={mean:.6f} +/- {sd:.6f} ms, median latency={lat:.6f} ms, shape corr={corr:.3f}".format(
                    idx=int(channel["input_channel"]) + 1,
                    identity=channel["best_identity_source_channel"],
                    rate=float(channel["detection_rate"]),
                    mean=float(channel.get("mean_latency_ms", math.nan)),
                    sd=float(channel.get("sd_latency_ms", math.nan)),
                    lat=float(channel["median_latency_ms"]),
                    corr=float(channel["median_intended_shape_correlation"]),
                )
            )
        lines.append("")
    lines.extend(["## Limitations", ""])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_run(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    manifest_path = run_dir / "dummy_pulse_manifest.json"
    planned_path = run_dir / "planned_pulses.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing {manifest_path}")
    if not planned_path.exists():
        raise FileNotFoundError(f"Missing {planned_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    planned_rows = _read_csv(planned_path)

    capture_candidates = [
        ("direct_loopback", run_dir / "direct_loopback_capture.wav"),
        ("wasapi_loopback", run_dir / "wasapi_loopback_capture.wav"),
    ]
    all_detection_rows: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    for capture_name, capture_path in capture_candidates:
        if not capture_path.exists():
            continue
        rows, summary = compare_capture(capture_path, planned_rows=planned_rows, manifest=manifest, capture_name=capture_name)
        all_detection_rows.extend(rows)
        captures.append(summary)

    direct_captures = [capture for capture in captures if capture["capture"] == "direct_loopback"]
    passed = bool(direct_captures) and all(capture["passed"] for capture in direct_captures)
    report = {
        "schema": "pps-dummy-3ch-pulse-comparison.v1",
        "run_dir": str(run_dir),
        "status": "pass" if passed else "review_required",
        "passed": passed,
        "captures": captures,
        "limitations": [
            "This validates one 3-channel WAV splitting to electrical outputs; it is not a participant experiment.",
            "Woojer mechanical onset is not measured without an external sensor.",
            "LSL/event marker latency is separate from physical audio-interface latency.",
        ],
    }
    _write_detection_csv(run_dir / "dummy_pulse_detections.csv", all_detection_rows)
    (run_dir / "dummy_pulse_comparison_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown(run_dir / "dummy_pulse_comparison_report.md", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare dummy pulse recordings against the source stimulus.")
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare_run(args.run_dir)
    print(f"Wrote {Path(args.run_dir) / 'dummy_pulse_comparison_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
