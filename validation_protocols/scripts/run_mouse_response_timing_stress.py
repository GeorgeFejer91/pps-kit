"""Internal stress harness for mouse-click to response-marker timing.

This script does not change the experiment runner. It exercises the existing
SessionEventLogger and TimingEventHub from the outside with deterministic
mouse_click events and callback-shaped response_marker_start payloads.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from peripersonal_space_toolkit.session_events import SessionEvent, SessionEventLogger  # noqa: E402
from peripersonal_space_toolkit.timing_events import TimingEventHub  # noqa: E402


SCHEMA = "pps-mouse-response-timing-stress.v1"


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"mouse_response_timing_stress_{stamp}"


def _sleep_until(target_perf: float) -> None:
    while True:
        remaining = target_perf - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.005))


def _float(value: Any) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _stats(values: list[float]) -> dict[str, Any]:
    values = [float(value) for value in values if math.isfinite(float(value))]
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)
    return {
        "count": len(values),
        "min_ms": min(values),
        "mean_ms": statistics.fmean(values),
        "sd_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median_ms": statistics.median(values),
        "p95_ms": ordered[p95_index],
        "max_ms": max(values),
    }


def _event_payload(event: SessionEvent) -> dict[str, Any]:
    return dict(getattr(event, "payload", {}) or {})


def _write_timing_qc_csv(events: list[SessionEvent], path: Path) -> Path:
    mouse_by_id = {int(event.event_id): event for event in events if event.event_type == "mouse_click"}
    rows: list[dict[str, Any]] = []
    for marker in events:
        if marker.event_type != "response_marker_start":
            continue
        payload = _event_payload(marker)
        mouse_id = int(_float(payload.get("mouse_event_id"))) if math.isfinite(_float(payload.get("mouse_event_id"))) else 0
        mouse = mouse_by_id.get(mouse_id)
        delta_ms = ""
        if mouse is not None:
            delta_ms = (float(marker.monotonic_time) - float(mouse.monotonic_time)) * 1000.0
        rows.append(
            {
                "mouse_event_id": mouse_id or "",
                "response_marker_event_id": marker.event_id,
                "click_index": payload.get("click_index", ""),
                "mouse_unix_time": "" if mouse is None else f"{mouse.unix_time:.9f}",
                "response_marker_unix_time": f"{marker.unix_time:.9f}",
                "mouse_monotonic_time": "" if mouse is None else f"{mouse.monotonic_time:.9f}",
                "response_marker_monotonic_time": f"{marker.monotonic_time:.9f}",
                "marker_minus_mouse_ms": "" if delta_ms == "" else f"{delta_ms:.3f}",
                "delay_clock": "monotonic",
                "planned_marker_delay_ms": payload.get("planned_marker_delay_ms", ""),
                "marker_channel": payload.get("marker_channel", ""),
                "marker_gain": payload.get("marker_gain", ""),
                "timestamp_quality": payload.get("timestamp_quality", ""),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "mouse_event_id",
            "response_marker_event_id",
            "click_index",
            "mouse_unix_time",
            "response_marker_unix_time",
            "mouse_monotonic_time",
            "response_marker_monotonic_time",
            "marker_minus_mouse_ms",
            "delay_clock",
            "planned_marker_delay_ms",
            "marker_channel",
            "marker_gain",
            "timestamp_quality",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _analyse_events(events: list[SessionEvent], *, expected_count: int, planned_delay_ms: float) -> dict[str, Any]:
    mouse_events = [event for event in events if event.event_type == "mouse_click"]
    response_markers = [event for event in events if event.event_type == "response_marker_start"]
    mouse_by_id = {int(event.event_id): event for event in mouse_events}
    marker_by_mouse: dict[int, list[SessionEvent]] = {}
    for marker in response_markers:
        payload = _event_payload(marker)
        mouse_id = int(_float(payload.get("mouse_event_id"))) if math.isfinite(_float(payload.get("mouse_event_id"))) else 0
        marker_by_mouse.setdefault(mouse_id, []).append(marker)

    linked_deltas_ms: list[float] = []
    schedule_errors_ms: list[float] = []
    callback_leads_ms: list[float] = []
    missing_links: list[int] = []
    duplicate_links: list[int] = []
    for mouse in mouse_events:
        markers = marker_by_mouse.get(int(mouse.event_id), [])
        if not markers:
            missing_links.append(int(mouse.event_id))
            continue
        if len(markers) > 1:
            duplicate_links.append(int(mouse.event_id))
        marker = markers[0]
        delta_ms = (float(marker.monotonic_time) - float(mouse.monotonic_time)) * 1000.0
        linked_deltas_ms.append(delta_ms)
        schedule_errors_ms.append(delta_ms - planned_delay_ms)
        marker_payload = _event_payload(marker)
        callback_perf = _float(marker_payload.get("callback_perf_counter"))
        if math.isfinite(callback_perf):
            callback_leads_ms.append((float(marker.monotonic_time) - callback_perf) * 1000.0)

    event_ids = [int(event.event_id) for event in events]
    duplicate_event_ids = sorted({event_id for event_id in event_ids if event_ids.count(event_id) > 1})
    quality_counts = Counter(
        str(_event_payload(event).get("timestamp_quality", ""))
        for event in response_markers
        if _event_payload(event).get("timestamp_quality", "")
    )
    event_type_counts = Counter(event.event_type for event in events)
    pass_checks = {
        "all_mouse_clicks_logged": len(mouse_events) == expected_count,
        "all_response_markers_logged": len(response_markers) == expected_count,
        "all_clicks_linked_once": not missing_links and not duplicate_links,
        "no_duplicate_event_ids": not duplicate_event_ids,
        "all_response_markers_dac_timed": quality_counts.get("dac_time_sample_exact", 0) == expected_count,
        "marker_delay_error_within_1_ms": max([abs(value) for value in schedule_errors_ms], default=0.0) <= 1.0,
    }
    return {
        "event_count": len(events),
        "event_type_counts": dict(event_type_counts),
        "mouse_click_count": len(mouse_events),
        "response_marker_start_count": len(response_markers),
        "duplicate_event_ids": duplicate_event_ids,
        "missing_response_marker_for_mouse_event_ids": missing_links,
        "duplicate_response_markers_for_mouse_event_ids": duplicate_links,
        "response_timestamp_quality_counts": dict(quality_counts),
        "marker_minus_mouse_ms": _stats(linked_deltas_ms),
        "marker_delay_error_ms": _stats(schedule_errors_ms),
        "callback_to_marker_lead_ms": _stats(callback_leads_ms),
        "pass_checks": pass_checks,
        "passed": all(pass_checks.values()),
    }


def run_stress(
    *,
    output_dir: Path,
    count: int,
    interval_s: float,
    start_delay_s: float,
    planned_marker_delay_ms: float,
    callback_lead_ms: float,
    sample_rate: int,
    blocksize: int,
    marker_gain: float,
    enable_lsl: bool,
    warmup_s: float,
    realtime: bool,
    flush_each: bool,
) -> dict[str, Any]:
    if count < 0:
        raise ValueError("count must be non-negative")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if blocksize <= 0:
        raise ValueError("blocksize must be positive")

    output_dir.mkdir(parents=True, exist_ok=True)
    logger = SessionEventLogger(participant_id="VALIDATION_MOUSE")
    hub = TimingEventHub(
        logger,
        enable_lsl=enable_lsl,
        session_id=f"mouse_response_stress_{time.strftime('%Y%m%d_%H%M%S')}",
        participant_id="VALIDATION_MOUSE",
    )
    manifest = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "purpose": "Internal software timing stress for mouse_click to response_marker_start linkage.",
        "count": count,
        "interval_s": interval_s,
        "start_delay_s": start_delay_s,
        "planned_marker_delay_ms": planned_marker_delay_ms,
        "callback_lead_ms": callback_lead_ms,
        "sample_rate": sample_rate,
        "blocksize": blocksize,
        "marker_gain": marker_gain,
        "enable_lsl": enable_lsl,
        "lsl_status": dict(hub.lsl_status.__dict__),
        "measurement_boundary": "software timing/logging harness; no physical loopback or Woojer mechanical onset measured",
    }
    (output_dir / "mouse_response_timing_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    if realtime and warmup_s > 0:
        time.sleep(warmup_s)

    hub.log("session_start", validation_schema=SCHEMA, output_dir=str(output_dir))
    hub.log("block_start", block_index=1, block_number=1, block_label="mouse_response_timing_stress")

    start_perf = time.perf_counter() + max(0.0, start_delay_s)
    base_audio_sample = 0
    for index in range(1, count + 1):
        scheduled_perf = start_perf + (index - 1) * max(0.0, interval_s)
        if realtime:
            _sleep_until(scheduled_perf)
        dispatch_perf = time.perf_counter()
        dispatch_unix = time.time()
        mouse_event = hub.log(
            "mouse_click",
            unix_time=dispatch_unix,
            monotonic_time=dispatch_perf,
            click_index=index,
            scheduled_perf_counter=f"{scheduled_perf:.9f}",
            dispatch_perf_counter=f"{dispatch_perf:.9f}",
            dispatch_jitter_ms=f"{(dispatch_perf - scheduled_perf) * 1000.0:.6f}",
            in_target=True,
            during_playback=True,
            emulated=True,
            validation_schema=SCHEMA,
        )

        marker_time_perf = dispatch_perf + planned_marker_delay_ms / 1000.0
        callback_perf = marker_time_perf - max(0.0, callback_lead_ms) / 1000.0
        if realtime:
            _sleep_until(callback_perf)
        sample_offset = (index * 37) % blocksize
        buffer_start_sample = base_audio_sample + ((index - 1) * blocksize)
        sample_index = buffer_start_sample + sample_offset
        stream_output_buffer_dac_time = marker_time_perf - (sample_offset / float(sample_rate))
        hub.enqueue_callback_event(
            {
                "event_type": "response_marker_start",
                "mouse_event_id": mouse_event.event_id,
                "click_index": index,
                "marker_channel": 3,
                "marker_gain": marker_gain,
                "sample_rate": sample_rate,
                "buffer_start_sample": buffer_start_sample,
                "sample_offset_in_buffer": sample_offset,
                "sample_index": sample_index,
                "stream_current_time": callback_perf,
                "stream_output_buffer_dac_time": stream_output_buffer_dac_time,
                "callback_perf_counter": callback_perf,
                "planned_marker_delay_ms": f"{planned_marker_delay_ms:.6f}",
                "callback_lead_ms": f"{callback_lead_ms:.6f}",
                "block_index": 1,
                "block_number": 1,
                "block_label": "mouse_response_timing_stress",
                "validation_schema": SCHEMA,
                "simulated_callback_payload": True,
            }
        )
        if flush_each:
            hub.flush_callback_events(timeout_s=0.5)

    hub.flush_callback_events(timeout_s=5.0)
    hub.log("block_end", block_index=1, block_number=1, block_label="mouse_response_timing_stress")
    hub.log("session_end", validation_schema=SCHEMA)
    hub.flush_callback_events(timeout_s=2.0)

    events = logger.events
    events_csv = logger.write_csv(output_dir / "events.csv")
    events_xdf = logger.write_xdf(
        output_dir / "events.xdf",
        metadata={
            "participant_id": "VALIDATION_MOUSE",
            "session_id": logger.session_id,
            "validation_schema": SCHEMA,
            "lsl_status": dict(hub.lsl_status.__dict__),
        },
    )
    lsl_markers_csv = hub.write_lsl_markers_csv(output_dir / "lsl_markers.csv")
    trigger_dictionary = hub.write_trigger_dictionary(output_dir / "trigger_dictionary.json")
    timing_qc_csv = _write_timing_qc_csv(events, output_dir / "timing_qc.csv")
    analysis = _analyse_events(events, expected_count=count, planned_delay_ms=planned_marker_delay_ms)
    analysis.update(
        {
            "schema": SCHEMA,
            "output_dir": str(output_dir),
            "events_csv": str(events_csv),
            "events_xdf": str(events_xdf),
            "lsl_markers_csv": str(lsl_markers_csv),
            "trigger_dictionary_json": str(trigger_dictionary),
            "timing_qc_csv": str(timing_qc_csv),
            "lsl_status": dict(hub.lsl_status.__dict__),
            "limitations": [
                "This run validates software logging, callback timestamp conversion, and optional LSL fan-out only.",
                "It does not prove physical audio-interface latency, WASAPI capture behavior, or Woojer mechanical onset.",
                "A real active runner session is still needed to validate OS click injection into the GUI during playback.",
            ],
        }
    )
    (output_dir / "mouse_response_timing_report.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    _write_markdown_report(analysis, output_dir / "mouse_response_timing_report.md")
    hub.close()
    return analysis


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    checks = report.get("pass_checks") or {}
    lines = [
        "# Mouse Response Timing Stress",
        "",
        f"- Output dir: `{report.get('output_dir')}`",
        f"- Passed: `{report.get('passed')}`",
        f"- Mouse clicks: {report.get('mouse_click_count')}",
        f"- Response markers: {report.get('response_marker_start_count')}",
        f"- Timestamp qualities: `{json.dumps(report.get('response_timestamp_quality_counts'), sort_keys=True)}`",
        f"- Marker minus mouse: `{json.dumps(report.get('marker_minus_mouse_ms'), sort_keys=True)}`",
        f"- Marker delay error: `{json.dumps(report.get('marker_delay_error_ms'), sort_keys=True)}`",
        f"- Callback-to-marker lead: `{json.dumps(report.get('callback_to_marker_lead_ms'), sort_keys=True)}`",
        "",
        "## Checks",
        "",
    ]
    for name, passed in sorted(checks.items()):
        lines.append(f"- `{name}`: {passed}")
    lines.extend(["", "## Limitations", ""])
    for limitation in report.get("limitations") or []:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run internal mouse/response-marker timing stress.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--interval-s", type=float, default=0.05)
    parser.add_argument("--start-delay-s", type=float, default=1.0)
    parser.add_argument("--planned-marker-delay-ms", type=float, default=8.0)
    parser.add_argument("--callback-lead-ms", type=float, default=5.805)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--blocksize", type=int, default=256)
    parser.add_argument("--marker-gain", type=float, default=0.08)
    parser.add_argument("--enable-lsl", action="store_true")
    parser.add_argument("--warmup-s", type=float, default=2.0)
    parser.add_argument("--no-realtime", action="store_true", help="Run as fast as possible for unit/debug checks.")
    parser.add_argument("--no-flush-each", action="store_true", help="Flush callback queue only after all clicks.")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    report = run_stress(
        output_dir=output_dir,
        count=args.count,
        interval_s=args.interval_s,
        start_delay_s=args.start_delay_s,
        planned_marker_delay_ms=args.planned_marker_delay_ms,
        callback_lead_ms=args.callback_lead_ms,
        sample_rate=args.sample_rate,
        blocksize=args.blocksize,
        marker_gain=args.marker_gain,
        enable_lsl=args.enable_lsl,
        warmup_s=args.warmup_s,
        realtime=not args.no_realtime,
        flush_each=not args.no_flush_each,
    )
    print(f"Wrote mouse response timing report: {output_dir / 'mouse_response_timing_report.json'}")
    print(f"Passed: {report.get('passed')}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
