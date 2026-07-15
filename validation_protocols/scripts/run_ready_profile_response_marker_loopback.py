"""Recover ready-profile response markers from synthetic loopback WAVs.

This validation wrapper consumes the ready-profile runner smoke report, builds
one loopback-shaped WAV per played profile block from the logged
response_marker_start sample indices, and feeds those WAVs through the shared
response-marker loopback comparator.

The resulting report proves that each ready profile's runner event log can be
converted into a loopback evidence trace and decoded by the existing recovery
tooling. It is intentionally synthetic: it does not measure physical output,
audio-interface latency, Woojer vibration, participant behavior, or published
PPS effects.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compare_response_marker_loopback  # noqa: E402


SCHEMA = "pps-ready-profile-response-marker-loopback.v1"
DEFAULT_SMOKE_REPORT = (
    REPO_ROOT
    / "artifacts"
    / "validation_runs"
    / "current_goal_ready_profile_runner_smoke_20260715"
    / "ready_profile_runner_smoke_report.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "artifacts"
    / "validation_runs"
    / "current_goal_ready_profile_response_marker_loopback_20260715"
)
EVIDENCE_BOUNDARY = (
    "Synthetic per-ready-profile response-marker loopback built from runner "
    "events. It proves response-marker event logs can be recovered from "
    "loopback-shaped WAV traces by the comparator; it does not prove physical "
    "loopback, hardware latency, Woojer mechanical onset, participant "
    "behavior, or published PPS effects."
)


def run_validation(
    *,
    smoke_report: Path = DEFAULT_SMOKE_REPORT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    templates: list[str] | None = None,
    tactile_channel_1based: int = 3,
    pulse_amplitude: float = 0.02,
    pulse_width_ms: float = 12.0,
    search_pre_ms: float = 10.0,
    search_post_ms: float = 150.0,
    min_peak: float = 0.005,
) -> dict[str, Any]:
    smoke_report = Path(smoke_report).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    smoke = _read_json(smoke_report)
    profile_filter = set(templates or [])
    source_profiles = [
        profile
        for profile in smoke.get("profiles", [])
        if not profile_filter or str(profile.get("template_id") or "") in profile_filter
    ]
    profile_results = [
        _validate_profile(
            profile,
            output_dir=output_dir / "profiles" / _safe_name(str(profile.get("template_id") or "profile")),
            tactile_channel_1based=tactile_channel_1based,
            pulse_amplitude=pulse_amplitude,
            pulse_width_ms=pulse_width_ms,
            search_pre_ms=search_pre_ms,
            search_post_ms=search_post_ms,
            min_peak=min_peak,
        )
        for profile in source_profiles
    ]
    summary = _summary(profile_results)
    criteria = {
        "source_smoke_report_exists": smoke_report.is_file(),
        "source_smoke_report_passed": bool(smoke.get("passed")),
        "profiles_selected": bool(source_profiles),
        "all_selected_profiles_passed": bool(profile_results) and all(profile.get("passed") for profile in profile_results),
        "all_expected_markers_recovered": summary["total_expected_markers"] > 0
        and summary["total_expected_markers"] == summary["total_detected_markers"],
    }
    passed = all(criteria.values())
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "passed": passed,
        "criteria": criteria,
        "summary": summary,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "source_smoke_report": {
            "path": str(smoke_report),
            "schema": smoke.get("schema", ""),
            "passed": bool(smoke.get("passed")),
            "summary": smoke.get("summary", {}),
        },
        "templates": [str(profile.get("template_id") or "") for profile in source_profiles],
        "profiles": profile_results,
        "report_json": str(output_dir / "ready_profile_response_marker_loopback_report.json"),
        "report_md": str(output_dir / "ready_profile_response_marker_loopback_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _validate_profile(
    profile: dict[str, Any],
    *,
    output_dir: Path,
    tactile_channel_1based: int,
    pulse_amplitude: float,
    pulse_width_ms: float,
    search_pre_ms: float,
    search_post_ms: float,
    min_peak: float,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    template_id = str(profile.get("template_id") or "")
    events_csv = Path(str((profile.get("outputs") or {}).get("events_csv") or ""))
    rows = _read_events(events_csv) if events_csv.is_file() else []
    markers = _response_markers(rows)
    recordings = _write_synthetic_recordings(
        markers,
        output_dir=output_dir / "synthetic_recordings",
        tactile_channel_1based=tactile_channel_1based,
        pulse_amplitude=pulse_amplitude,
        pulse_width_ms=pulse_width_ms,
    )
    comparison = {}
    comparison_dir = output_dir / "comparison"
    if recordings and events_csv.is_file():
        comparison = compare_response_marker_loopback.compare_loopback(
            events_csv=events_csv,
            recordings=recordings,
            output_dir=comparison_dir,
            tactile_channel_1based=tactile_channel_1based,
            search_pre_ms=search_pre_ms,
            search_post_ms=search_post_ms,
            min_peak=min_peak,
        )
    expected_markers = len(markers)
    detected_markers = int(comparison.get("detected_marker_count") or 0)
    criteria = {
        "source_profile_passed_runner_smoke": bool(profile.get("passed")),
        "events_csv_exists": events_csv.is_file(),
        "response_markers_present": expected_markers > 0,
        "synthetic_recordings_written": bool(recordings) and all(path.is_file() for path in recordings),
        "comparator_report_written": (comparison_dir / "response_marker_loopback_report.json").is_file(),
        "comparator_passed": bool(comparison.get("passed")),
        "all_expected_markers_recovered": expected_markers > 0 and detected_markers == expected_markers,
    }
    return {
        "template_id": template_id,
        "passed": all(criteria.values()),
        "criteria": criteria,
        "events_csv": str(events_csv),
        "runner_smoke_event_counts": profile.get("event_counts", {}),
        "expected_marker_count": expected_markers,
        "detected_marker_count": detected_markers,
        "detection_rate": float(comparison.get("detection_rate") or 0.0),
        "offset_ms": comparison.get("offset_ms", {}),
        "abs_residual_ms": comparison.get("abs_residual_ms", {}),
        "synthetic_recordings": [str(path) for path in recordings],
        "comparison_report": str(comparison_dir / "response_marker_loopback_report.json"),
        "comparison_pairs_csv": str(comparison_dir / "response_marker_loopback_pairs.csv"),
        "comparison_blocks": [
            {
                "recording": block.get("recording", ""),
                "block_number": block.get("block_number", ""),
                "expected_marker_count": block.get("expected_marker_count", 0),
                "detected_marker_count": block.get("detected_marker_count", 0),
                "detection_rate": block.get("detection_rate", 0.0),
                "passed": bool(block.get("passed")),
            }
            for block in comparison.get("blocks", [])
        ],
    }


def _write_synthetic_recordings(
    markers: list[dict[str, Any]],
    *,
    output_dir: Path,
    tactile_channel_1based: int,
    pulse_amplitude: float,
    pulse_width_ms: float,
) -> list[Path]:
    if not markers:
        return []
    output_dir.mkdir(parents=True, exist_ok=True)
    grouped: dict[int | None, list[dict[str, Any]]] = defaultdict(list)
    for marker in markers:
        grouped[marker.get("block_number")].append(marker)
    recordings: list[Path] = []
    for block_number, block_markers in sorted(grouped.items(), key=lambda item: (-1 if item[0] is None else item[0])):
        sample_rate = _dominant_sample_rate(block_markers)
        pulse_width_samples = max(1, int(round((pulse_width_ms / 1000.0) * sample_rate)))
        pad_samples = max(pulse_width_samples + int(round(0.25 * sample_rate)), int(round(0.5 * sample_rate)))
        last_sample = max(int(marker["sample_index"]) for marker in block_markers)
        frames = max(last_sample + pad_samples, sample_rate)
        channels = max(3, int(tactile_channel_1based))
        samples = np.zeros((frames, channels), dtype=np.float32)
        channel_index = int(tactile_channel_1based) - 1
        for marker in block_markers:
            start = max(0, int(marker["sample_index"]))
            end = min(frames, start + pulse_width_samples)
            samples[start:end, channel_index] = float(pulse_amplitude)
        name = _recording_name(block_number)
        path = output_dir / name
        sf.write(path, samples, sample_rate)
        recordings.append(path)
    return recordings


def _recording_name(block_number: int | None) -> str:
    if block_number is None:
        return "all_blocks_response_marker_loopback.wav"
    return f"Block_{block_number:02d}_response_marker_loopback.wav"


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


def _response_markers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("event_type") or "") != "response_marker_start":
            continue
        payload = dict(row.get("payload") or {})
        sample_index = _as_int(payload.get("sample_index"))
        if sample_index is None:
            continue
        markers.append(
            {
                "event_id": _as_int(row.get("event_id")) or 0,
                "mouse_event_id": _as_int(payload.get("mouse_event_id")) or 0,
                "block_number": _as_int(payload.get("block_number")),
                "block_label": str(payload.get("block_label") or ""),
                "sample_index": sample_index,
                "sample_rate": _as_int(payload.get("sample_rate")) or 44100,
                "marker_gain": payload.get("marker_gain", ""),
                "timestamp_quality": payload.get("timestamp_quality", ""),
            }
        )
    markers.sort(key=lambda item: (item["block_number"] or 0, item["sample_index"], item["event_id"]))
    return markers


def _dominant_sample_rate(markers: list[dict[str, Any]]) -> int:
    sample_rates = [int(marker.get("sample_rate") or 44100) for marker in markers]
    [(sample_rate, _count)] = Counter(sample_rates).most_common(1)
    return int(sample_rate)


def _summary(profile_results: list[dict[str, Any]]) -> dict[str, Any]:
    rates = [float(profile.get("detection_rate") or 0.0) for profile in profile_results]
    return {
        "profile_count": len(profile_results),
        "passed_profile_count": sum(1 for profile in profile_results if profile.get("passed")),
        "failed_profile_count": sum(1 for profile in profile_results if not profile.get("passed")),
        "total_expected_markers": sum(int(profile.get("expected_marker_count") or 0) for profile in profile_results),
        "total_detected_markers": sum(int(profile.get("detected_marker_count") or 0) for profile in profile_results),
        "total_synthetic_recordings": sum(len(profile.get("synthetic_recordings") or []) for profile in profile_results),
        "min_detection_rate": min(rates) if rates else 0.0,
        "median_detection_rate": statistics.median(rates) if rates else 0.0,
    }


def _as_int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        result = float(str(value))
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return int(result)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Ready Profile Response Marker Loopback",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Profiles: `{report['summary']['passed_profile_count']}/{report['summary']['profile_count']}`",
        f"- Expected markers: `{report['summary']['total_expected_markers']}`",
        f"- Detected markers: `{report['summary']['total_detected_markers']}`",
        f"- Synthetic recordings: `{report['summary']['total_synthetic_recordings']}`",
        "",
        EVIDENCE_BOUNDARY,
        "",
        "## Profiles",
        "",
    ]
    for profile in report["profiles"]:
        lines.append(
            f"- `{profile['template_id']}`: passed=`{profile['passed']}`, "
            f"markers=`{profile['detected_marker_count']}/{profile['expected_marker_count']}`, "
            f"detection_rate=`{profile['detection_rate']}`"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_") or "profile"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build synthetic per-ready-profile response-marker loopback WAVs and compare them."
    )
    parser.add_argument("--smoke-report", type=Path, default=DEFAULT_SMOKE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--template", action="append", default=[])
    parser.add_argument("--tactile-channel", type=int, default=3)
    parser.add_argument("--pulse-amplitude", type=float, default=0.02)
    parser.add_argument("--pulse-width-ms", type=float, default=12.0)
    parser.add_argument("--search-pre-ms", type=float, default=10.0)
    parser.add_argument("--search-post-ms", type=float, default=150.0)
    parser.add_argument("--min-peak", type=float, default=0.005)
    args = parser.parse_args(argv)

    report = run_validation(
        smoke_report=args.smoke_report,
        output_dir=args.output_dir,
        templates=args.template or None,
        tactile_channel_1based=args.tactile_channel,
        pulse_amplitude=args.pulse_amplitude,
        pulse_width_ms=args.pulse_width_ms,
        search_pre_ms=args.search_pre_ms,
        search_post_ms=args.search_post_ms,
        min_peak=args.min_peak,
    )
    print(f"Wrote ready profile response-marker loopback report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
