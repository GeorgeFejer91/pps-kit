"""Stress the SessionRunnerController click-to-response-marker path.

This is an internal validation harness. It does not send OS mouse clicks and it
does not touch hardware. Instead, it runs the real session controller with a
deterministic fake audio engine, injects clicks through the controller's public
log_click() path during active playback, and verifies that each click produces a
linked callback-derived response_marker_start event.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.design import ProtocolSpec, default_design  # noqa: E402
from peripersonal_space_toolkit.session_runner import SessionRunnerController, prepare_run_package  # noqa: E402


SCHEMA = "pps-session-runner-click-path-stress.v1"


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"session_runner_click_path_stress_{stamp}"


def _compact_design() -> Any:
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol = ProtocolSpec(
        repetitions_per_condition=1,
        soa_values_ms=[300],
        spatial_values_cm=[100.0],
        pair_spatial_values_with_soas=True,
        auditory_motion_directions=["looming"],
        tactile_sites=["hand"],
        include_catch_trials=False,
        catch_trial_percentage=0.0,
        include_baseline_trials=False,
        respiratory_phases=["Inhale"],
        blocks=1,
        participants=1,
        random_seed=20260612,
    )
    return design


def _prepare_render_dir(output_dir: Path, *, sample_rate: int) -> Path:
    render_dir = output_dir / "rendered_input"
    render_dir.mkdir(parents=True, exist_ok=True)
    wav_path = render_dir / "looming_validation_click_path.wav"
    frames = max(1, int(round(sample_rate * 0.050)))
    data = np.zeros((frames, 3), dtype=np.float32)
    sf.write(wav_path, data, sample_rate)
    (render_dir / "render_manifest.json").write_text(
        json.dumps(
            {
                "schema": "pps-render-manifest.v1",
                "status": "rendered_reference",
                "wav_outputs": [{"path": str(wav_path), "sha256": "validation-click-path"}],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return render_dir


class DeterministicClickAudioEngine:
    """Fake audio engine that emits callback-shaped response marker events."""

    def __init__(self, *, sample_rate: int, planned_marker_delay_ms: float, block_hold_s: float):
        self.sample_rate = int(sample_rate)
        self.planned_marker_delay_ms = float(planned_marker_delay_ms)
        self.block_hold_s = float(block_hold_s)
        self.playback_started = threading.Event()
        self.finish_requested = threading.Event()
        self.played: list[str] = []
        self.trigger_records: list[dict[str, Any]] = []
        self._audio_event_callback = None
        self._play_start_perf = 0.0

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self.played.append(path)
        self._audio_event_callback = audio_event_callback
        self._play_start_perf = time.perf_counter()
        if audio_event_callback and block_event_schedule is not None:
            block_event_schedule.reset()
            for event in block_event_schedule.consume_buffer(0, self.sample_rate * 60):
                payload = dict(event.payload)
                now = time.perf_counter()
                payload.update(
                    {
                        "event_type": event.event_type,
                        "sample_index": event.sample_index,
                        "buffer_start_sample": 0,
                        "sample_offset_in_buffer": event.sample_index,
                        "sample_rate": self.sample_rate,
                        "trigger_key": event.trigger_key,
                        "callback_perf_counter": now,
                        "stream_current_time": now,
                        "stream_output_buffer_dac_time": now,
                    }
                )
                audio_event_callback(payload)
        elif audio_event_callback:
            now = time.perf_counter()
            audio_event_callback(
                {
                    "event_type": "audio_sample_zero",
                    "sample_index": 0,
                    "buffer_start_sample": 0,
                    "sample_offset_in_buffer": 0,
                    "sample_rate": self.sample_rate,
                    "callback_perf_counter": now,
                    "stream_current_time": now,
                    "stream_output_buffer_dac_time": now,
                }
            )
        self.playback_started.set()
        deadline = time.perf_counter() + max(0.1, self.block_hold_s)
        while time.perf_counter() < deadline and not self.finish_requested.is_set():
            if progress_callback:
                progress_callback(time.perf_counter() - self._play_start_perf)
            time.sleep(0.005)
        if progress_callback:
            progress_callback(time.perf_counter() - self._play_start_perf)
        return True

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        now = time.perf_counter()
        delay_s = max(0.0, self.planned_marker_delay_ms / 1000.0)
        sample_offset = int(round(delay_s * self.sample_rate))
        elapsed_samples = int(round((now - self._play_start_perf) * self.sample_rate))
        payload = {
            "event_type": "response_marker_start",
            "sample_index": elapsed_samples + sample_offset,
            "buffer_start_sample": elapsed_samples,
            "sample_offset_in_buffer": sample_offset,
            "sample_rate": self.sample_rate,
            "callback_perf_counter": now,
            "stream_current_time": now,
            "stream_output_buffer_dac_time": now,
            "marker_channel": 2,
            "marker_gain": marker_gain,
            **dict(metadata or {}),
        }
        self.trigger_records.append(payload)
        if self._audio_event_callback is not None:
            self._audio_event_callback(payload)

    def shutdown(self) -> None:
        self.finish_requested.set()


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean_ms": None, "sd_ms": None, "median_ms": None, "p95_ms": None, "max_ms": None, "min_ms": None}
    ordered = sorted(float(value) for value in values)
    p95_index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
    return {
        "count": len(ordered),
        "mean_ms": statistics.fmean(ordered),
        "sd_ms": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
        "max_ms": max(ordered),
        "min_ms": min(ordered),
    }


def _write_pairs_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "mouse_event_id",
        "response_marker_event_id",
        "click_index",
        "mouse_monotonic_time",
        "response_marker_monotonic_time",
        "marker_minus_mouse_ms",
        "timestamp_quality",
        "marker_channel",
        "marker_gain",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Session Runner Click Path Stress",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Requested clicks: `{report['requested_click_count']}`",
        f"- Mouse clicks logged: `{report['mouse_click_count']}`",
        f"- Response markers logged: `{report['response_marker_start_count']}`",
        f"- Linked pairs: `{report['linked_pair_count']}`",
        f"- Marker-minus-mouse: `{json.dumps(report['marker_minus_mouse_ms'], sort_keys=True)}`",
        f"- Timestamp qualities: `{json.dumps(report['response_timestamp_quality_counts'], sort_keys=True)}`",
        "",
        "This validates the session-runner click path with a deterministic fake audio engine. It is not an OS-level GUI click test and it is not a physical loopback recording.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_stress(
    *,
    output_dir: Path,
    count: int,
    interval_s: float,
    start_delay_s: float,
    planned_marker_delay_ms: float,
    sample_rate: int,
    block_hold_s: float | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    render_dir = _prepare_render_dir(output_dir, sample_rate=sample_rate)
    package = prepare_run_package(
        _compact_design(),
        "P001",
        render_dir=render_dir,
        session_root=output_dir / "sessions",
        created_at=datetime.now(),
    )
    hold_s = block_hold_s if block_hold_s is not None else max(0.5, start_delay_s + max(0, count - 1) * interval_s + 0.2)
    engine = DeterministicClickAudioEngine(
        sample_rate=sample_rate,
        planned_marker_delay_ms=planned_marker_delay_ms,
        block_hold_s=hold_s,
    )
    controller = SessionRunnerController(package, audio_engine=engine)
    result_holder: dict[str, Any] = {}

    def _run_controller() -> None:
        result_holder["result"] = controller.run()

    thread = threading.Thread(target=_run_controller, name="pps-session-click-path-controller", daemon=True)
    thread.start()
    if not engine.playback_started.wait(timeout=5.0):
        raise RuntimeError("Session controller did not enter playback in time.")
    time.sleep(max(0.0, start_delay_s))
    for index in range(1, max(0, count) + 1):
        controller.log_click(x=100 + index, y=200 + index, in_target=True)
        if index < count:
            time.sleep(max(0.0, interval_s))
    engine.finish_requested.set()
    thread.join(timeout=5.0)
    if thread.is_alive():
        raise RuntimeError("Session controller did not finish after click stress.")

    result = result_holder["result"]
    controller.events.flush_callback_events()
    events = list(controller.logger.events)
    mouse_events = [event for event in events if event.event_type == "mouse_click"]
    markers = [event for event in events if event.event_type == "response_marker_start"]
    mouse_by_id = {int(event.event_id): event for event in mouse_events}
    pairs: list[dict[str, Any]] = []
    missing_mouse_ids: list[int] = []
    duplicate_mouse_ids: list[int] = []
    seen_mouse_ids: set[int] = set()
    delays: list[float] = []
    qualities: dict[str, int] = {}

    for marker in markers:
        payload = dict(marker.payload or {})
        mouse_event_id = int(payload.get("mouse_event_id") or 0)
        mouse = mouse_by_id.get(mouse_event_id)
        if mouse_event_id in seen_mouse_ids:
            duplicate_mouse_ids.append(mouse_event_id)
        seen_mouse_ids.add(mouse_event_id)
        quality = str(payload.get("timestamp_quality") or "")
        qualities[quality] = qualities.get(quality, 0) + 1
        if mouse is None:
            missing_mouse_ids.append(mouse_event_id)
            continue
        delta_ms = (float(marker.monotonic_time) - float(mouse.monotonic_time)) * 1000.0
        delays.append(delta_ms)
        pairs.append(
            {
                "mouse_event_id": mouse_event_id,
                "response_marker_event_id": marker.event_id,
                "click_index": "",
                "mouse_monotonic_time": f"{mouse.monotonic_time:.9f}",
                "response_marker_monotonic_time": f"{marker.monotonic_time:.9f}",
                "marker_minus_mouse_ms": f"{delta_ms:.6f}",
                "timestamp_quality": quality,
                "marker_channel": payload.get("marker_channel", ""),
                "marker_gain": payload.get("marker_gain", ""),
            }
        )

    missing_markers_for_mouse_ids = sorted(set(mouse_by_id) - seen_mouse_ids)
    timing = _summary(delays)
    median_delay = timing.get("median_ms")
    timing_ok = median_delay is not None and abs(float(median_delay) - planned_marker_delay_ms) <= 2.0
    passed = bool(
        result.completed
        and len(mouse_events) == count
        and len(markers) == count
        and len(pairs) == count
        and not missing_mouse_ids
        and not missing_markers_for_mouse_ids
        and not duplicate_mouse_ids
        and qualities.get("dac_time_sample_exact", 0) == count
        and timing_ok
    )

    _write_pairs_csv(output_dir / "session_runner_click_pairs.csv", pairs)
    report = {
        "schema": SCHEMA,
        "passed": passed,
        "requested_click_count": count,
        "mouse_click_count": len(mouse_events),
        "response_marker_start_count": len(markers),
        "linked_pair_count": len(pairs),
        "missing_mouse_ids_for_markers": missing_mouse_ids,
        "missing_response_marker_for_mouse_event_ids": missing_markers_for_mouse_ids,
        "duplicate_response_markers_for_mouse_event_ids": duplicate_mouse_ids,
        "response_timestamp_quality_counts": qualities,
        "marker_minus_mouse_ms": timing,
        "planned_marker_delay_ms": planned_marker_delay_ms,
        "timing_tolerance_ms": 2.0,
        "session_completed": bool(result.completed),
        "session_dir": str(result.session_dir),
        "events_csv": str(result.events_csv),
        "timing_qc_csv": str(result.analysis_outputs.get("timing_qc", "")),
        "lsl_markers_csv": str(result.lsl_markers_csv or ""),
        "trigger_dictionary_json": str(result.trigger_dictionary_path or ""),
        "triggered_audio_markers": len(engine.trigger_records),
        "limitations": [
            "This validates the SessionRunnerController click path with a deterministic fake audio engine.",
            "It does not send OS mouse clicks into the visible GUI.",
            "It does not measure physical tactile-channel marker recovery or Woojer mechanical onset.",
        ],
    }
    (output_dir / "session_runner_click_path_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown_report(report, output_dir / "session_runner_click_path_report.md")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a session-runner click path stress validation.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--interval-s", type=float, default=0.02)
    parser.add_argument("--start-delay-s", type=float, default=0.05)
    parser.add_argument("--planned-marker-delay-ms", type=float, default=8.0)
    parser.add_argument("--sample-rate", type=int, default=44100)
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    report = run_stress(
        output_dir=output_dir,
        count=args.count,
        interval_s=args.interval_s,
        start_delay_s=args.start_delay_s,
        planned_marker_delay_ms=args.planned_marker_delay_ms,
        sample_rate=args.sample_rate,
    )
    print(f"Wrote session runner click path report: {output_dir / 'session_runner_click_path_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
