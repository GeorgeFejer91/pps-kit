"""Realtime one-block trial-runner validation with simulated tactile responses.

This internal harness builds a tiny Segment 5/6-style run setup, materializes
one participant block, runs it through SessionRunnerController with a realtime
fake audio engine, and injects deterministic jittered mouse clicks after each
tactile onset. It validates the runner data products, not physical hardware.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-one-block-trial-runner-realtime-stress.v1"


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"one_block_trial_runner_realtime_{stamp}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _read_events(path: Path) -> list[dict[str, Any]]:
    rows = []
    for row in _read_csv(path):
        try:
            payload = json.loads(row.get("payload_json", "") or "{}")
        except json.JSONDecodeError:
            payload = {}
        rows.append({**row, "payload": payload})
    return rows


def _add_pulse(data: np.ndarray, channel: int, onset_s: float, *, sample_rate: int, amplitude: float = 0.02) -> None:
    start = max(0, min(data.shape[0], int(round(onset_s * sample_rate))))
    width = max(1, int(round(0.020 * sample_rate)))
    stop = max(start, min(data.shape[0], start + width))
    data[start:stop, channel] = amplitude


def _build_segment_fixture(
    output_dir: Path,
    *,
    participant_id: str,
    trial_count: int,
    sample_rate: int,
    trial_duration_s: float,
) -> Path:
    project_root = output_dir / "segment_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)

    soa_values = [0, 50, 100, 150, 200]
    block_rows: list[dict[str, Any]] = []
    looming_onset_s = 0.100
    for index in range(1, trial_count + 1):
        soa_ms = soa_values[(index - 1) % len(soa_values)]
        tactile_onset_s = looming_onset_s + (soa_ms / 1000.0)
        frames = int(round(trial_duration_s * sample_rate))
        data = np.zeros((frames, 3), dtype=np.float32)
        _add_pulse(data, 0, looming_onset_s, sample_rate=sample_rate, amplitude=0.018)
        _add_pulse(data, 1, looming_onset_s + 0.002, sample_rate=sample_rate, amplitude=0.016)
        _add_pulse(data, 2, tactile_onset_s, sample_rate=sample_rate, amplitude=0.014)
        wav_path = stim_root / f"trial_{index:02d}_soa{soa_ms:03d}_3ch.wav"
        sf.write(wav_path, data, sample_rate)
        block_rows.append(
            {
                "block_trial_index": index,
                "family": "audio_tactile",
                "row_label": "Inhale" if index % 2 else "Exhale",
                "noise_type": "validation_rect_pulse",
                "soa_ms": soa_ms,
                "sequence_labels": f"Validation pulse | SOA {soa_ms} ms",
                "sequence_variant_key": f"validation_pulse_soa{soa_ms:03d}",
                "source_file_name": wav_path.name,
                "trial_file_path": str(wav_path),
                "source_sha256": _sha256(wav_path),
                "duration_ms": int(round(trial_duration_s * 1000.0)),
                "duration_s": f"{trial_duration_s:.9f}",
                "looming_segment_onset_s": f"{looming_onset_s:.9f}",
                "tactile_onset_s": f"{tactile_onset_s:.9f}",
                "channels": 3,
                "tactile_channel": 3,
            }
        )

    block_csv = block_root / "block_01_final.csv"
    block_fieldnames = [
        "block_trial_index",
        "family",
        "row_label",
        "noise_type",
        "soa_ms",
        "sequence_labels",
        "sequence_variant_key",
        "source_file_name",
        "trial_file_path",
        "source_sha256",
        "duration_ms",
        "duration_s",
        "looming_segment_onset_s",
        "tactile_onset_s",
        "channels",
        "tactile_channel",
    ]
    _write_csv(block_csv, block_rows, block_fieldnames)

    block_manifest = block_root / "block_csv_preview_manifest.json"
    block_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-block-csv-preview.v1",
                "accepted": True,
                "blocks": [
                    {
                        "block_index": 1,
                        "csv_path": str(block_csv),
                        "csv_file_name": block_csv.name,
                        "trial_count": len(block_rows),
                    }
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    order_csv = run_root / "experiment_block_order.csv"
    order_rows = [
        {
            "participant_id": participant_id,
            "participant_index": 1,
            "experiment_structure": "single",
            "phase": "single",
            "phase_label": "Single",
            "phase_index": 1,
            "participant_block_position": 1,
            "source_block_index": 1,
            "block_label": "Validation Block 01",
            "block_csv_file": block_csv.name,
            "block_csv_path": str(block_csv),
            "trial_count": len(block_rows),
            "duration_ms": int(round(trial_count * trial_duration_s * 1000.0)),
            "sequence_seed": 20260612,
        }
    ]
    _write_csv(
        order_csv,
        order_rows,
        [
            "participant_id",
            "participant_index",
            "experiment_structure",
            "phase",
            "phase_label",
            "phase_index",
            "participant_block_position",
            "source_block_index",
            "block_label",
            "block_csv_file",
            "block_csv_path",
            "trial_count",
            "duration_ms",
            "sequence_seed",
        ],
    )

    run_manifest = run_root / "experiment_run_setup_manifest.json"
    run_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-experiment-run-setup.v1",
                "status": "prepared",
                "prepared": True,
                "csv_path": str(order_csv),
                "experiment_structure": "single",
                "participant_count": 1,
                "parts_per_participant": 1,
                "blocks_per_part": 1,
                "total_block_runs": 1,
                "seed": 20260612,
                "source_segment5_manifest": str(block_manifest),
                "source_segment5_manifest_sha256": _sha256(block_manifest),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_manifest


class RealtimeFakeAudioEngine:
    """Realtime callback-shaped audio engine that does not touch hardware."""

    def __init__(self, *, sample_rate: int, blocksize: int, response_marker_delay_ms: float):
        self.sample_rate = int(sample_rate)
        self.blocksize = int(blocksize)
        self.response_marker_delay_ms = float(response_marker_delay_ms)
        self.playback_started = threading.Event()
        self.finish_requested = threading.Event()
        self.trigger_records: list[dict[str, Any]] = []
        self.recording_paths: list[str] = []
        self._audio_event_callback = None
        self._play_start_perf = 0.0
        self._last_block_path: Path | None = None
        self._recording_active = False
        self._recording_output_path: Path | None = None

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self._last_block_path = Path(path)
        info = sf.info(path)
        frames_total = int(info.frames)
        self.sample_rate = int(info.samplerate)
        self._audio_event_callback = audio_event_callback
        self._play_start_perf = time.perf_counter()
        if block_event_schedule is not None:
            block_event_schedule.reset()
        self.playback_started.set()

        cursor = 0
        while cursor < frames_total and not self.finish_requested.is_set():
            frames = min(self.blocksize, frames_total - cursor)
            now = time.perf_counter()
            if audio_event_callback is not None and block_event_schedule is not None:
                event_frames = frames + 1 if cursor + frames >= frames_total else frames
                for event in block_event_schedule.consume_buffer(cursor, event_frames):
                    offset = int(event.sample_index) - cursor
                    payload = dict(event.payload)
                    payload.update(
                        {
                            "event_type": event.event_type,
                            "sample_index": event.sample_index,
                            "buffer_start_sample": cursor,
                            "sample_offset_in_buffer": offset,
                            "sample_rate": self.sample_rate,
                            "trigger_key": event.trigger_key,
                            "callback_perf_counter": now,
                            "stream_current_time": now,
                            "stream_output_buffer_dac_time": now,
                        }
                    )
                    audio_event_callback(payload)
            if progress_callback is not None:
                progress_callback(cursor / self.sample_rate)
            cursor += frames
            target = self._play_start_perf + (cursor / self.sample_rate)
            sleep_s = target - time.perf_counter()
            if sleep_s > 0:
                time.sleep(min(sleep_s, 0.020))
        if progress_callback is not None:
            progress_callback(min(cursor, frames_total) / self.sample_rate)
        return not self.finish_requested.is_set()

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        now = time.perf_counter()
        elapsed_samples = max(0, int(round((now - self._play_start_perf) * self.sample_rate)))
        offset = max(0, int(round((self.response_marker_delay_ms / 1000.0) * self.sample_rate)))
        payload = {
            "event_type": "response_marker_start",
            "sample_index": elapsed_samples + offset,
            "buffer_start_sample": elapsed_samples,
            "sample_offset_in_buffer": offset,
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

    def start_recording(self, output_path: str) -> bool:
        self._recording_active = True
        self._recording_output_path = Path(output_path)
        self.recording_paths.append(output_path)
        return True

    def is_recording(self) -> bool:
        return self._recording_active

    def stop_recording(self, output_path: str | None = None, interrupted: bool = False) -> None:
        self._recording_active = False
        target = Path(output_path) if output_path else self._recording_output_path
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._last_block_path and self._last_block_path.exists():
            shutil.copyfile(self._last_block_path, target)
        else:
            sf.write(target, np.zeros((1, 3), dtype=np.float32), self.sample_rate)

    def stop(self) -> None:
        self.finish_requested.set()

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def shutdown(self) -> None:
        self.stop()


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean_ms": None, "sd_ms": None, "median_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None}
    ordered = sorted(float(value) for value in values)
    p95_index = min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)
    return {
        "count": len(ordered),
        "mean_ms": statistics.fmean(ordered),
        "sd_ms": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
        "min_ms": min(ordered),
        "max_ms": max(ordered),
    }


def _event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _verify_xdf(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size <= 0:
        return {"exists": path.exists(), "loaded": False, "sample_count": 0, "message": "events.xdf missing or empty"}
    try:
        import pyxdf  # type: ignore

        streams, _header = pyxdf.load_xdf(str(path))
    except Exception as exc:
        return {"exists": True, "loaded": False, "sample_count": 0, "message": str(exc)}
    sample_count = 0
    for stream in streams:
        timestamps = stream.get("time_stamps", [])
        sample_count += len(timestamps)
    return {"exists": True, "loaded": True, "sample_count": sample_count, "message": "loaded with pyxdf"}


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# One-Block Trial Runner Realtime Stress",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Session dir: `{report.get('session_dir')}`",
        f"- Trials requested: `{report.get('trial_count')}`",
        f"- Analysis-ready rows: `{report.get('analysis_ready_trial_count')}`",
        f"- Hits: `{report.get('analysis_ready_hit_count')}`",
        f"- RT ms: `{json.dumps(report.get('rt_ms'), sort_keys=True)}`",
        f"- Mouse to response-marker ms: `{json.dumps(report.get('marker_minus_mouse_ms'), sort_keys=True)}`",
        f"- Event counts: `{json.dumps(report.get('event_type_counts'), sort_keys=True)}`",
        f"- XDF: `{json.dumps(report.get('xdf'), sort_keys=True)}`",
        "",
        "This validates the runner software/output contract with a realtime fake audio engine. It does not play through the Komplete Audio 6, measure electrical loopback, or measure Woojer mechanical onset.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_stress(
    *,
    output_dir: Path,
    participant_id: str,
    trial_count: int,
    sample_rate: int,
    trial_duration_s: float,
    blocksize: int,
    enable_lsl: bool,
    response_marker_delay_ms: float,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_segment_fixture(
        output_dir,
        participant_id=participant_id,
        trial_count=trial_count,
        sample_rate=sample_rate,
        trial_duration_s=trial_duration_s,
    )
    package = prepare_segment_run_package(
        run_manifest,
        participant_id,
        session_root=output_dir / "sessions",
        created_at=datetime.now(),
    )
    engine = RealtimeFakeAudioEngine(
        sample_rate=sample_rate,
        blocksize=blocksize,
        response_marker_delay_ms=response_marker_delay_ms,
    )
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options=SessionCaptureOptions(enable_lsl=enable_lsl),
    )
    result_holder: dict[str, Any] = {}

    def _run_controller() -> None:
        result_holder["result"] = controller.run()

    thread = threading.Thread(target=_run_controller, name="pps-one-block-realtime-controller", daemon=True)
    thread.start()
    if not engine.playback_started.wait(timeout=5.0):
        raise RuntimeError("Controller did not start playback in time.")

    click_plan_delays_ms = [180.0, 225.0, 260.0, 205.0, 240.0, 190.0, 275.0]
    scheduled: dict[str, dict[str, Any]] = {}
    clicked: set[str] = set()
    click_rows: list[dict[str, Any]] = []
    deadline = time.perf_counter() + max(5.0, trial_count * trial_duration_s + 5.0)
    while thread.is_alive() and time.perf_counter() < deadline:
        now = time.perf_counter()
        for event in controller.logger.events:
            if event.event_type != "tactile_onset":
                continue
            payload = dict(event.payload or {})
            trial_uid = str(payload.get("trial_uid") or payload.get("Trial_UID") or event.event_id)
            if trial_uid not in scheduled:
                delay_ms = click_plan_delays_ms[len(scheduled) % len(click_plan_delays_ms)]
                scheduled[trial_uid] = {
                    "trial_uid": trial_uid,
                    "tactile_event_id": event.event_id,
                    "tactile_monotonic_time": event.monotonic_time,
                    "planned_click_delay_ms": delay_ms,
                    "due_perf_counter": event.monotonic_time + (delay_ms / 1000.0),
                }
        for trial_uid, plan in list(scheduled.items()):
            if trial_uid in clicked or now < float(plan["due_perf_counter"]):
                continue
            controller.log_click(x=320 + len(clicked), y=240, in_target=True)
            clicked.add(trial_uid)
            click_rows.append(
                {
                    **plan,
                    "actual_click_perf_counter": f"{time.perf_counter():.9f}",
                }
            )
        time.sleep(0.002)
    thread.join(timeout=5.0)
    if thread.is_alive():
        engine.stop()
        thread.join(timeout=2.0)
        raise RuntimeError("Controller did not finish the realtime one-block run.")

    result = result_holder["result"]
    controller.events.flush_callback_events()

    events = _read_events(result.events_csv)
    event_ids = [row.get("event_id", "") for row in events]
    duplicate_event_ids = sorted({event_id for event_id in event_ids if event_ids.count(event_id) > 1})
    analysis_ready_path = result.analysis_outputs.get("analysis_ready_trials", package.session_dir / "analysis" / f"{package.session_id}_analysis_ready_trials.csv")
    analysis_rows = _read_csv(analysis_ready_path)
    timing_qc_path = result.analysis_outputs.get("timing_qc", package.session_dir / "analysis" / f"{package.session_id}_timing_qc.csv")
    timing_rows = _read_csv(timing_qc_path)
    rt_values = [float(row["rt_ms"]) for row in analysis_rows if str(row.get("rt_ms") or "").strip()]
    marker_delta_values = [float(row["marker_minus_mouse_ms"]) for row in timing_rows if str(row.get("marker_minus_mouse_ms") or "").strip()]
    lsl_rows = _read_csv(result.lsl_markers_csv or package.session_dir / "lsl_markers.csv")
    xdf_status = _verify_xdf(result.events_xdf)
    copied_analysis_ready = output_dir / "analysis_ready_trials.csv"
    if analysis_ready_path.exists():
        shutil.copyfile(analysis_ready_path, copied_analysis_ready)
    _write_csv(
        output_dir / "simulated_click_plan.csv",
        click_rows,
        [
            "trial_uid",
            "tactile_event_id",
            "tactile_monotonic_time",
            "planned_click_delay_ms",
            "due_perf_counter",
            "actual_click_perf_counter",
        ],
    )

    timestamp_qualities: dict[str, int] = {}
    for row in lsl_rows:
        quality = str(row.get("timestamp_quality") or "")
        timestamp_qualities[quality] = timestamp_qualities.get(quality, 0) + 1

    event_counts = _event_type_counts(events)
    passed = bool(
        result.completed
        and event_counts.get("tactile_onset", 0) == trial_count
        and event_counts.get("mouse_click", 0) == trial_count
        and event_counts.get("response_marker_start", 0) == trial_count
        and len(analysis_rows) == trial_count
        and sum(1 for row in analysis_rows if str(row.get("hit")).lower() in {"true", "1", "yes"}) == trial_count
        and not duplicate_event_ids
        and result.events_csv.exists()
        and result.events_xdf.exists()
        and xdf_status.get("exists")
        and xdf_status.get("sample_count", 0) >= len(events)
        and analysis_ready_path.exists()
        and (result.lsl_markers_csv is None or result.lsl_markers_csv.exists())
        and (result.trigger_dictionary_path is None or result.trigger_dictionary_path.exists())
        and timestamp_qualities.get("dac_time_sample_exact", 0) >= trial_count
    )

    report = {
        "schema": SCHEMA,
        "passed": passed,
        "completed": bool(result.completed),
        "interrupted": bool(result.interrupted),
        "participant_id": participant_id,
        "trial_count": trial_count,
        "session_dir": str(package.session_dir),
        "run_setup_manifest": str(run_manifest),
        "block_wav": str(package.blocks[0].wav_path),
        "block_csv": str(package.blocks[0].manifest_path),
        "events_csv": str(result.events_csv),
        "events_xdf": str(result.events_xdf),
        "analysis_ready_trials_csv": str(analysis_ready_path),
        "analysis_ready_trials_copy": str(copied_analysis_ready),
        "timing_qc_csv": str(timing_qc_path),
        "lsl_markers_csv": str(result.lsl_markers_csv or ""),
        "trigger_dictionary_json": str(result.trigger_dictionary_path or ""),
        "event_type_counts": event_counts,
        "duplicate_event_ids": duplicate_event_ids,
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_ready_hit_count": sum(1 for row in analysis_rows if str(row.get("hit")).lower() in {"true", "1", "yes"}),
        "rt_ms": _summary(rt_values),
        "marker_minus_mouse_ms": _summary(marker_delta_values),
        "lsl_marker_count": len(lsl_rows),
        "lsl_timestamp_quality_counts": timestamp_qualities,
        "xdf": xdf_status,
        "capture_options": result.capture_options,
        "simulated_backup_recording_paths": [str(path) for path in result.recording_paths],
        "limitations": [
            "This is a realtime software runner validation with a fake audio engine.",
            "It does not touch hardware, direct electrical loopback, or Woojer mechanical vibration.",
            "The backup recording file is a simulated copy of the block WAV, not a physical capture.",
        ],
    }
    (output_dir / "one_block_trial_runner_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown_report(report, output_dir / "one_block_trial_runner_report.md")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one realtime block through the trial runner with simulated jittered clicks.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--participant-id", default="P001")
    parser.add_argument("--trial-count", type=int, default=5)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--trial-duration-s", type=float, default=0.750)
    parser.add_argument("--blocksize", type=int, default=256)
    parser.add_argument("--response-marker-delay-ms", type=float, default=8.0)
    parser.add_argument("--no-lsl", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    report = run_stress(
        output_dir=output_dir,
        participant_id=args.participant_id,
        trial_count=args.trial_count,
        sample_rate=args.sample_rate,
        trial_duration_s=args.trial_duration_s,
        blocksize=args.blocksize,
        enable_lsl=not args.no_lsl,
        response_marker_delay_ms=args.response_marker_delay_ms,
    )
    print(f"Wrote one-block trial-runner report: {output_dir / 'one_block_trial_runner_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
