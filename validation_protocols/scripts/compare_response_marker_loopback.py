"""Compare logged response markers against a tactile-channel loopback recording.

This internal checker is for the physical backup layer of the response strategy.
It reads response_marker_start events from events.csv, detects pulse starts in a
recorded tactile channel, fits the median sample offset, and reports recovery
rate plus residual jitter. The fitted offset is hardware/recording latency; the
residuals are the timing-reconstruction quality after accounting for that
latency.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


SCHEMA = "pps-response-marker-loopback-comparison.v1"
MIN_DETECTION_RATE = 0.95
MAX_P95_RESIDUAL_MS = 2.0
MAX_ABS_RESIDUAL_MS = 5.0
DIGITAL_EVIDENCE_MIN_SEARCH_POST_MS = 300.0


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"response_marker_loopback_comparison_{stamp}"


def _read_events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            payload = {}
            try:
                payload = json.loads(row.get("payload_json") or "{}")
            except json.JSONDecodeError:
                payload = {}
            rows.append({**row, "payload": payload})
    return rows


def _as_int(value: Any, *, default: int | None = None) -> int | None:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, *, default: float = math.nan) -> float:
    try:
        if value in (None, ""):
            return default
        result = float(str(value))
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _block_number_from_name(path: Path) -> int | None:
    match = re.search(r"(?:Block|block)[_\-\s]*(\d+)", path.name)
    if not match:
        return None
    return int(match.group(1))


def _response_markers(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers = []
    for row in events:
        if row.get("event_type") != "response_marker_start":
            continue
        payload = dict(row.get("payload") or {})
        sample_index = _as_int(payload.get("sample_index"), default=None)
        if sample_index is None:
            continue
        markers.append(
            {
                "event_id": _as_int(row.get("event_id"), default=0) or 0,
                "mouse_event_id": _as_int(payload.get("mouse_event_id"), default=0) or 0,
                "block_number": _as_int(payload.get("block_number"), default=None),
                "block_label": payload.get("block_label", ""),
                "sample_index": sample_index,
                "marker_gain": payload.get("marker_gain", ""),
                "timestamp_quality": payload.get("timestamp_quality", ""),
            }
        )
    markers.sort(key=lambda item: (item["block_number"] or 0, item["sample_index"], item["event_id"]))
    return markers


def _channel_threshold(signal: np.ndarray, *, min_peak: float) -> tuple[float, float, bool]:
    abs_signal = np.abs(np.asarray(signal, dtype=np.float64))
    peak = float(np.max(abs_signal)) if abs_signal.size else 0.0
    median = float(np.median(abs_signal)) if abs_signal.size else 0.0
    mad = float(np.median(np.abs(abs_signal - median))) if abs_signal.size else 0.0
    adaptive = median + 8.0 * max(mad, 1e-9)
    if peak > 0:
        adaptive = min(max(adaptive, min_peak), peak * 0.50)
    threshold = max(min_peak, adaptive)
    return threshold, peak, peak < min_peak


def _detect_starts(signal: np.ndarray, *, sample_rate: int, min_peak: float, min_gap_ms: float) -> tuple[list[int], dict[str, Any]]:
    threshold, peak, low_signal = _channel_threshold(signal, min_peak=min_peak)
    if low_signal:
        return [], {"threshold": threshold, "peak": peak, "low_signal": True}
    above = np.flatnonzero(np.abs(signal) >= threshold)
    if above.size == 0:
        return [], {"threshold": threshold, "peak": peak, "low_signal": True}
    min_gap = max(1, int(round((min_gap_ms / 1000.0) * sample_rate)))
    starts = [int(above[0])]
    previous = int(above[0])
    for sample in above[1:]:
        sample = int(sample)
        if sample > previous + min_gap:
            starts.append(sample)
        previous = sample
    return starts, {"threshold": threshold, "peak": peak, "low_signal": False}


def _pair_markers(
    markers: list[dict[str, Any]],
    starts: list[int],
    *,
    sample_rate: int,
    search_pre_ms: float,
    search_post_ms: float,
) -> list[dict[str, Any]]:
    used: set[int] = set()
    offset_estimate: float | None = None
    rows: list[dict[str, Any]] = []
    pre = int(round((search_pre_ms / 1000.0) * sample_rate))
    post = int(round((search_post_ms / 1000.0) * sample_rate))
    for marker in markers:
        expected = int(marker["sample_index"])
        candidates = [start for start in starts if start not in used and expected - pre <= start <= expected + post]
        detected = None
        if candidates:
            target = expected + offset_estimate if offset_estimate is not None else expected
            detected = min(candidates, key=lambda start: abs(start - target))
            used.add(detected)
            current_offset = detected - expected
            if offset_estimate is None:
                offset_estimate = float(current_offset)
            else:
                previous_offsets = [
                    int(row["detected_sample_index"]) - int(row["expected_sample_index"])
                    for row in rows
                    if row.get("detected")
                ]
                previous_offsets.append(current_offset)
                offset_estimate = float(statistics.median(previous_offsets))
        rows.append(
            {
                "event_id": marker["event_id"],
                "mouse_event_id": marker["mouse_event_id"],
                "block_number": marker["block_number"] or "",
                "block_label": marker["block_label"],
                "expected_sample_index": expected,
                "detected": detected is not None,
                "detected_sample_index": "" if detected is None else detected,
                "raw_offset_ms": "" if detected is None else (detected - expected) / float(sample_rate) * 1000.0,
                "residual_ms": "",
                "timestamp_quality": marker.get("timestamp_quality", ""),
                "marker_gain": marker.get("marker_gain", ""),
            }
        )
    detected_offsets = [
        int(row["detected_sample_index"]) - int(row["expected_sample_index"])
        for row in rows
        if row.get("detected")
    ]
    median_offset = statistics.median(detected_offsets) if detected_offsets else math.nan
    for row in rows:
        if not row.get("detected") or not math.isfinite(float(median_offset)):
            continue
        residual = (int(row["detected_sample_index"]) - int(row["expected_sample_index"]) - median_offset) / float(sample_rate) * 1000.0
        row["residual_ms"] = residual
    return rows


def _stats(values: list[float]) -> dict[str, float | int | None]:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return {"count": 0, "mean_ms": None, "sd_ms": None, "median_ms": None, "p95_ms": None, "max_ms": None, "min_ms": None}
    p95_index = min(len(finite) - 1, int(round(0.95 * (len(finite) - 1))))
    return {
        "count": len(finite),
        "mean_ms": statistics.fmean(finite),
        "sd_ms": statistics.stdev(finite) if len(finite) > 1 else 0.0,
        "median_ms": statistics.median(finite),
        "p95_ms": finite[p95_index],
        "max_ms": max(finite),
        "min_ms": min(finite),
    }


def compare_recording(
    recording_path: Path,
    markers: list[dict[str, Any]],
    *,
    tactile_channel_1based: int,
    search_pre_ms: float,
    search_post_ms: float,
    min_peak: float,
    min_gap_ms: float,
) -> dict[str, Any]:
    samples, sample_rate = sf.read(recording_path, dtype="float32", always_2d=True)
    if tactile_channel_1based < 1 or tactile_channel_1based > samples.shape[1]:
        return {
            "recording": str(recording_path),
            "status": "skipped",
            "reason": f"recording has {samples.shape[1]} channel(s); requested tactile channel {tactile_channel_1based}",
        }
    signal = samples[:, tactile_channel_1based - 1]
    starts, profile = _detect_starts(signal, sample_rate=int(sample_rate), min_peak=min_peak, min_gap_ms=min_gap_ms)
    block_number = _block_number_from_name(recording_path)
    scoped = [marker for marker in markers if marker.get("block_number") == block_number] if block_number is not None else list(markers)
    if block_number is not None and not scoped:
        scoped = list(markers) if len({marker.get("block_number") for marker in markers}) <= 1 else []
    pairs = _pair_markers(scoped, starts, sample_rate=int(sample_rate), search_pre_ms=search_pre_ms, search_post_ms=search_post_ms)
    detected = [row for row in pairs if row.get("detected")]
    detection_rate = len(detected) / float(len(scoped) or 1)
    offsets_ms = [_as_float(row.get("raw_offset_ms")) for row in detected]
    residuals_ms = [abs(_as_float(row.get("residual_ms"))) for row in detected]
    residual_stats = _stats(residuals_ms)
    offset_stats = _stats(offsets_ms)
    p95_residual = residual_stats["p95_ms"] if residual_stats["p95_ms"] is not None else math.inf
    max_residual = residual_stats["max_ms"] if residual_stats["max_ms"] is not None else math.inf
    passed = bool(scoped) and detection_rate >= MIN_DETECTION_RATE and float(p95_residual) <= MAX_P95_RESIDUAL_MS and float(max_residual) <= MAX_ABS_RESIDUAL_MS
    return {
        "recording": str(recording_path),
        "status": "pass" if passed else "review_required",
        "passed": passed,
        "block_number": block_number if block_number is not None else "",
        "sample_rate": int(sample_rate),
        "tactile_channel_1based": tactile_channel_1based,
        "expected_marker_count": len(scoped),
        "detected_marker_count": len(detected),
        "detected_pulse_count": len(starts),
        "detection_rate": detection_rate,
        "offset_ms": offset_stats,
        "abs_residual_ms": residual_stats,
        "threshold_profile": profile,
        "search_window_ms": {
            "pre": float(search_pre_ms),
            "post": float(search_post_ms),
        },
        "pairs": pairs,
    }


def _is_digital_audio_evidence(path: Path) -> bool:
    return "audio_evidence" in path.name.lower()


def _write_pairs_csv(path: Path, blocks: list[dict[str, Any]]) -> None:
    fieldnames = [
        "recording",
        "event_id",
        "mouse_event_id",
        "block_number",
        "expected_sample_index",
        "detected",
        "detected_sample_index",
        "raw_offset_ms",
        "residual_ms",
        "timestamp_quality",
        "marker_gain",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for block in blocks:
            for row in block.get("pairs", []):
                writer.writerow({**{key: row.get(key, "") for key in fieldnames}, "recording": block.get("recording", "")})


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Response Marker Loopback Comparison",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Expected markers: `{report['expected_marker_count']}`",
        f"- Detected markers: `{report['detected_marker_count']}`",
        f"- Detection rate: `{report['detection_rate']}`",
        f"- Offset ms: `{json.dumps(report['offset_ms'], sort_keys=True)}`",
        f"- Absolute residual ms: `{json.dumps(report['abs_residual_ms'], sort_keys=True)}`",
        "",
        "The fitted offset estimates recording/hardware latency. Residuals estimate how reliably response markers can be recovered after accounting for that latency.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_loopback(
    *,
    events_csv: Path,
    recordings: list[Path],
    output_dir: Path,
    tactile_channel_1based: int = 3,
    search_pre_ms: float = 10.0,
    search_post_ms: float = 150.0,
    min_peak: float = 0.005,
    min_gap_ms: float = 5.0,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    events = _read_events(events_csv)
    markers = _response_markers(events)
    blocks: list[dict[str, Any]] = []
    for recording in recordings:
        recording_search_post_ms = float(search_post_ms)
        recording_role = "physical_loopback"
        if _is_digital_audio_evidence(recording):
            recording_search_post_ms = max(recording_search_post_ms, DIGITAL_EVIDENCE_MIN_SEARCH_POST_MS)
            recording_role = "digital_audio_evidence"
        block = compare_recording(
            recording,
            markers,
            tactile_channel_1based=tactile_channel_1based,
            search_pre_ms=search_pre_ms,
            search_post_ms=recording_search_post_ms,
            min_peak=min_peak,
            min_gap_ms=min_gap_ms,
        )
        block["recording_role"] = recording_role
        blocks.append(block)
    comparable = [block for block in blocks if block.get("status") != "skipped"]
    expected = sum(int(block.get("expected_marker_count", 0) or 0) for block in comparable)
    detected = sum(int(block.get("detected_marker_count", 0) or 0) for block in comparable)
    residuals = [
        abs(_as_float(row.get("residual_ms")))
        for block in comparable
        for row in block.get("pairs", [])
        if row.get("detected")
    ]
    offsets = [
        _as_float(row.get("raw_offset_ms"))
        for block in comparable
        for row in block.get("pairs", [])
        if row.get("detected")
    ]
    detection_rate = detected / float(expected or 1)
    residual_stats = _stats(residuals)
    offset_stats = _stats(offsets)
    passed = bool(comparable) and all(bool(block.get("passed")) for block in comparable) and detection_rate >= MIN_DETECTION_RATE
    report = {
        "schema": SCHEMA,
        "events_csv": str(events_csv),
        "recordings": [str(path) for path in recordings],
        "passed": passed,
        "status": "pass" if passed else "review_required",
        "expected_marker_count": expected,
        "detected_marker_count": detected,
        "detection_rate": detection_rate,
        "offset_ms": offset_stats,
        "abs_residual_ms": residual_stats,
        "criteria": {
            "min_detection_rate": MIN_DETECTION_RATE,
            "max_p95_abs_residual_ms": MAX_P95_RESIDUAL_MS,
            "max_abs_residual_ms": MAX_ABS_RESIDUAL_MS,
        },
        "blocks": blocks,
        "limitations": [
            "This compares electrical/tactile-channel loopback pulses against logged response_marker_start sample indices.",
            "It estimates recording/hardware offset and residual jitter; it does not measure Woojer mechanical vibration onset.",
            "A physical recording is required before this can prove physical response-marker recovery.",
            "Digital audio-evidence WAVs can include recorder pre-roll, so their pairing window is widened automatically.",
        ],
    }
    (output_dir / "response_marker_loopback_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_pairs_csv(output_dir / "response_marker_loopback_pairs.csv", blocks)
    _write_markdown(output_dir / "response_marker_loopback_report.md", report)
    return report


def _recordings_from_session(session_dir: Path) -> list[Path]:
    recordings = list(dict.fromkeys([*sorted(session_dir.glob("*.wav")), *sorted((session_dir / "recordings").glob("*.wav"))]))
    physical = [
        path
        for path in recordings
        if ("physical" in path.name.lower() or "loopback" in path.name.lower()) and "audio_evidence" not in path.name.lower()
    ]
    return physical or recordings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare response_marker_start events against tactile-channel loopback pulses.")
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--events-csv", type=Path)
    parser.add_argument("--recording", type=Path, action="append", dest="recordings")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--tactile-channel", type=int, default=3, help="1-based tactile/response-marker channel in the recording.")
    parser.add_argument("--search-pre-ms", type=float, default=10.0)
    parser.add_argument("--search-post-ms", type=float, default=150.0)
    parser.add_argument("--min-peak", type=float, default=0.005)
    args = parser.parse_args(argv)

    if args.events_csv is None:
        if args.session_dir is None:
            parser.error("--events-csv or --session-dir is required")
        args.events_csv = args.session_dir / "events.csv"
    recordings = args.recordings
    if not recordings:
        if args.session_dir is None:
            parser.error("--recording or --session-dir is required")
        recordings = _recordings_from_session(args.session_dir)
    if not recordings:
        parser.error("No recordings found")
    output_dir = args.output_dir or _default_output_dir()
    report = compare_loopback(
        events_csv=args.events_csv,
        recordings=recordings,
        output_dir=output_dir,
        tactile_channel_1based=args.tactile_channel,
        search_pre_ms=args.search_pre_ms,
        search_post_ms=args.search_post_ms,
        min_peak=args.min_peak,
    )
    print(f"Wrote response marker loopback report: {output_dir / 'response_marker_loopback_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
