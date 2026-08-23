"""Diagnose where coded dummy pulse output channels appear in a capture."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compare_dummy_pulse_recordings import (  # noqa: E402
    MIN_PEAK,
    MIN_SHAPE_CORRELATION,
    _normalized_correlation,
    _read_csv,
    _channel_threshold,
)
from make_dummy_pulse_stimulus import CHANNEL_CODES, channel_amplitude_for, channel_template  # noqa: E402


def _planned_reference_samples(planned_rows: list[dict[str, str]]) -> list[int]:
    rows = [row for row in planned_rows if int(row["channel"]) == 0]
    rows.sort(key=lambda row: int(row["pulse_index"]))
    if not rows:
        rows = sorted(planned_rows, key=lambda row: (int(row["pulse_index"]), int(row["channel"])))
    return [int(row["expected_sample_index"]) for row in rows]


def _median(values: list[float]) -> float:
    return float(np.median(np.asarray(values, dtype=np.float64))) if values else math.nan


def _detect_expected_starts(
    signal: np.ndarray,
    expected_samples: list[int],
    *,
    sample_rate: int,
    search_pre_ms: float,
    search_post_ms: float,
) -> tuple[list[int], dict[str, Any]]:
    threshold, peak, low_signal, clipped = _channel_threshold(signal)
    if low_signal:
        return [], {"threshold": threshold, "peak": peak, "low_signal": low_signal, "clipped": clipped}
    pre = int(round(search_pre_ms / 1000.0 * sample_rate))
    post = int(round(search_post_ms / 1000.0 * sample_rate))
    detected: list[int] = []
    abs_signal = np.abs(signal)
    for expected in expected_samples:
        start = max(0, int(expected) - pre)
        stop = min(len(signal), int(expected) + post)
        if stop <= start:
            continue
        hits = np.flatnonzero(abs_signal[start:stop] >= threshold)
        if hits.size:
            detected.append(start + int(hits[0]))
    return detected, {"threshold": threshold, "peak": peak, "low_signal": low_signal, "clipped": clipped}


def diagnose_run(
    run_dir: Path,
    *,
    capture_name: str = "direct_loopback_capture.wav",
    search_pre_ms: float = 25.0,
    search_post_ms: float = 200.0,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    manifest_path = run_dir / "dummy_pulse_manifest.json"
    planned_path = run_dir / "planned_pulses.csv"
    capture_path = run_dir / capture_name
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing {manifest_path}")
    if not planned_path.exists():
        raise FileNotFoundError(f"Missing {planned_path}")
    if not capture_path.exists():
        raise FileNotFoundError(f"Missing {capture_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    planned_rows = _read_csv(planned_path)
    samples, capture_rate = sf.read(capture_path, dtype="float32", always_2d=True)
    sample_rate = int(manifest["sample_rate"])
    if int(capture_rate) != sample_rate:
        raise ValueError(f"{capture_path} sample rate {capture_rate} does not match planned {sample_rate}")

    expected_samples = _planned_reference_samples(planned_rows)
    templates = {
        code.channel: channel_template(code, sample_rate=sample_rate, amplitude=channel_amplitude_for(manifest, code.channel))
        for code in CHANNEL_CODES
    }
    input_summaries: list[dict[str, Any]] = []

    for input_channel in range(samples.shape[1]):
        signal = samples[:, input_channel]
        detected_starts, profile = _detect_expected_starts(
            signal,
            expected_samples,
            sample_rate=sample_rate,
            search_pre_ms=search_pre_ms,
            search_post_ms=search_post_ms,
        )
        detected_starts = detected_starts[: len(expected_samples)]
        votes: list[int] = []
        best_corrs: list[float] = []
        per_source_corrs: dict[int, list[float]] = {code.channel: [] for code in CHANNEL_CODES}
        latencies_ms: list[float] = []
        for idx, detected in enumerate(detected_starts):
            source_scores: dict[int, float] = {}
            for source_channel, template in templates.items():
                segment = signal[detected : detected + len(template)]
                score = abs(_normalized_correlation(segment, template))
                source_scores[source_channel] = score
                per_source_corrs[source_channel].append(score)
            best_source = max(source_scores, key=source_scores.get)
            votes.append(best_source)
            best_corrs.append(source_scores[best_source])
            if idx < len(expected_samples):
                latencies_ms.append((detected - expected_samples[idx]) / float(sample_rate) * 1000.0)

        vote_counts = Counter(votes)
        best_source_channel = vote_counts.most_common(1)[0][0] if vote_counts else ""
        median_best_corr = _median(best_corrs)
        detected_count = len(detected_starts)
        input_summaries.append(
            {
                "input_channel": input_channel,
                "input_channel_1based": input_channel + 1,
                "detected_count": detected_count,
                "expected_count": len(expected_samples),
                "detection_rate": detected_count / float(len(expected_samples) or 1),
                "best_source_channel": best_source_channel,
                "best_source_channel_1based": (int(best_source_channel) + 1) if best_source_channel != "" else "",
                "best_source_vote_counts": dict(vote_counts),
                "median_best_shape_correlation": median_best_corr,
                "median_latency_ms": _median(latencies_ms),
                "peak": float(profile["peak"]),
                "threshold": float(profile["threshold"]),
                "low_signal": bool(profile["low_signal"]),
                "clipped": bool(profile["clipped"]),
                "per_source_median_correlation": {str(source): _median(scores) for source, scores in per_source_corrs.items()},
            }
        )

    source_to_inputs: dict[str, list[int]] = {}
    for source_channel in range(len(CHANNEL_CODES)):
        matches = [
            int(row["input_channel_1based"])
            for row in input_summaries
            if row["best_source_channel"] == source_channel
            and row["detection_rate"] >= 0.95
            and math.isfinite(float(row["median_best_shape_correlation"]))
            and float(row["median_best_shape_correlation"]) >= MIN_SHAPE_CORRELATION
            and float(row["peak"]) >= MIN_PEAK
        ]
        source_to_inputs[str(source_channel + 1)] = matches

    expected_identity = all(source_to_inputs.get(str(idx + 1)) == [idx + 1] for idx in range(len(CHANNEL_CODES)))
    conclusions: list[str] = []
    for source_channel in range(len(CHANNEL_CODES)):
        inputs = source_to_inputs.get(str(source_channel + 1), [])
        if inputs == [source_channel + 1]:
            conclusions.append(f"Output/source channel {source_channel + 1} appears on expected input {source_channel + 1}.")
        elif inputs:
            conclusions.append(f"Output/source channel {source_channel + 1} appears on input(s) {inputs}, not only expected input {source_channel + 1}.")
        else:
            conclusions.append(f"Output/source channel {source_channel + 1} was not detected above threshold on any recorded input.")

    report = {
        "schema": "pps-dummy-channel-route-diagnosis.v1",
        "run_dir": str(run_dir),
        "capture_path": str(capture_path),
        "sample_rate": sample_rate,
        "capture_channels": int(samples.shape[1]),
        "search_window_ms": {"pre": search_pre_ms, "post": search_post_ms},
        "source_to_detected_inputs_1based": source_to_inputs,
        "expected_identity_route_passed": expected_identity,
        "input_summaries": input_summaries,
        "conclusions": conclusions,
        "limitations": [
            "This maps electrical/captured input channels, not Woojer mechanical vibration onset.",
            "Low-signal inputs can indicate an unplugged cable, input gain issue, muted output, or a physical/driver selector mismatch.",
        ],
    }
    (run_dir / "dummy_channel_route_diagnosis.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_csv(run_dir / "dummy_channel_route_diagnosis.csv", input_summaries)
    _write_markdown(run_dir / "dummy_channel_route_diagnosis.md", report)
    return report


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    flat_rows = []
    for row in rows:
        flat = dict(row)
        flat["best_source_vote_counts"] = json.dumps(flat["best_source_vote_counts"], sort_keys=True)
        flat["per_source_median_correlation"] = json.dumps(flat["per_source_median_correlation"], sort_keys=True)
        flat_rows.append(flat)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(flat_rows[0].keys()))
        writer.writeheader()
        writer.writerows(flat_rows)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Dummy Channel Route Diagnosis",
        "",
        f"- Run dir: `{report['run_dir']}`",
        f"- Capture channels: {report['capture_channels']}",
        f"- Expected identity route passed: `{report['expected_identity_route_passed']}`",
        f"- Source to detected inputs (1-based): `{json.dumps(report['source_to_detected_inputs_1based'], sort_keys=True)}`",
        "",
        "## Conclusions",
        "",
    ]
    for conclusion in report["conclusions"]:
        lines.append(f"- {conclusion}")
    lines.extend(["", "## Inputs", ""])
    for row in report["input_summaries"]:
        lines.append(
            "- Input {input}: best source={source}, detected={detected}/{expected}, "
            "peak={peak:.6f}, median corr={corr:.3f}, median latency={lat:.6f} ms".format(
                input=row["input_channel_1based"],
                source=row["best_source_channel_1based"] or "none",
                detected=row["detected_count"],
                expected=row["expected_count"],
                peak=float(row["peak"]),
                corr=float(row["median_best_shape_correlation"]) if math.isfinite(float(row["median_best_shape_correlation"])) else math.nan,
                lat=float(row["median_latency_ms"]) if math.isfinite(float(row["median_latency_ms"])) else math.nan,
            )
        )
    lines.extend(["", "## Limitations", ""])
    for limitation in report["limitations"]:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose dummy pulse channel routing across recorded inputs.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--capture-name", default="direct_loopback_capture.wav")
    parser.add_argument("--search-pre-ms", type=float, default=25.0)
    parser.add_argument("--search-post-ms", type=float, default=200.0)
    args = parser.parse_args(argv)
    report = diagnose_run(args.run_dir, capture_name=args.capture_name, search_pre_ms=args.search_pre_ms, search_post_ms=args.search_post_ms)
    print(f"Wrote {Path(args.run_dir) / 'dummy_channel_route_diagnosis.json'}")
    return 0 if report["expected_identity_route_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
