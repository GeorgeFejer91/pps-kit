from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from peripersonal_space_toolkit import latency_validation as lv


def _shifted_capture(stimulus: np.ndarray, delays: list[int]) -> np.ndarray:
    frames = stimulus.shape[0] + max(delays) + 128
    capture = np.zeros((frames, stimulus.shape[1]), dtype=np.float32)
    for channel, delay in enumerate(delays):
        capture[delay : delay + stimulus.shape[0], channel] = stimulus[:, channel]
    return capture


def test_calibration_stimulus_has_expected_channels_and_events():
    stimulus, events = lv.make_calibration_stimulus(
        sample_rate=1000,
        channels=3,
        pulse_count=4,
        pre_roll_s=0.1,
        pulse_interval_s=0.2,
        pulse_duration_s=0.01,
    )

    assert stimulus.ndim == 2
    assert stimulus.shape[1] == 3
    assert len(events) == 12
    assert {event.channel_label for event in events} == {"left_audio", "right_audio", "tactile_drive"}
    assert events[0].sample_index == 100
    assert np.max(np.abs(stimulus)) > 0


def test_synthetic_loopback_passes_with_small_channel_skew():
    sample_rate = 44100
    stimulus, events = lv.make_calibration_stimulus(sample_rate=sample_rate, channels=3, pulse_count=10)
    capture = _shifted_capture(stimulus, [100, 110, 120])

    rows, profiles = lv.detect_loopback_events(capture, events, sample_rate=sample_rate)
    summary = lv.summarize_latency_validation(rows, profiles)

    assert summary["passed"]
    medians = {row["channel_label"]: row["median_latency_ms"] for row in summary["channel_summaries"]}
    assert abs(medians["left_audio"] - (100 / sample_rate * 1000.0)) < 0.001
    assert summary["skew_summary"]["left_right_median_abs_skew_ms"] < 1.0
    assert summary["skew_summary"]["tactile_audio_median_abs_skew_ms"] < 2.0


def test_low_signal_loopback_fails_validation():
    sample_rate = 44100
    stimulus, events = lv.make_calibration_stimulus(sample_rate=sample_rate, channels=3, pulse_count=5)
    capture = _shifted_capture(stimulus * 0.01, [100, 100, 100])

    rows, profiles = lv.detect_loopback_events(capture, events, sample_rate=sample_rate)
    summary = lv.summarize_latency_validation(rows, profiles)

    assert not summary["passed"]
    assert any(check["name"].endswith("_low_signal") and not check["passed"] for check in summary["checks"])


def test_baseline_shift_failure_is_reported():
    sample_rate = 44100
    stimulus, events = lv.make_calibration_stimulus(sample_rate=sample_rate, channels=3, pulse_count=8)
    baseline_capture = _shifted_capture(stimulus, [100, 100, 100])
    rows, profiles = lv.detect_loopback_events(baseline_capture, events, sample_rate=sample_rate)
    baseline_summary = lv.summarize_latency_validation(rows, profiles)

    shifted_capture = _shifted_capture(stimulus, [400, 400, 400])
    rows, profiles = lv.detect_loopback_events(shifted_capture, events, sample_rate=sample_rate)
    shifted_summary = lv.summarize_latency_validation(rows, profiles, baseline_summary=baseline_summary)

    assert not shifted_summary["passed"]
    assert shifted_summary["baseline_comparison"]["status"] == "compared"
    assert any("baseline_median_shift" in check["name"] and not check["passed"] for check in shifted_summary["checks"])


def test_specs_command_writes_snapshot(tmp_path: Path):
    exit_code = lv.main(["specs", "--output-dir", str(tmp_path)])

    assert exit_code == 0
    run_dirs = list(tmp_path.iterdir())
    assert len(run_dirs) == 1
    assert (run_dirs[0] / "device_specs.json").exists()
    assert (run_dirs[0] / "wiring_plan.json").exists()
    route = json.loads((run_dirs[0] / "route_snapshot.json").read_text(encoding="utf-8"))
    assert route["schema"] == "pps-latency-route-snapshot.v1"


def test_session_validation_compares_tactile_timing(tmp_path: Path):
    session_dir = tmp_path / "session"
    recording_dir = session_dir / "recordings"
    recording_dir.mkdir(parents=True)
    events_path = session_dir / "events.csv"
    planned_times = [1.0, 2.0, 3.0]
    with events_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["event_id", "event_type", "unix_time", "monotonic_time", "payload_json"])
        writer.writeheader()
        for idx, relative_time in enumerate(planned_times, start=1):
            writer.writerow(
                {
                    "event_id": idx,
                    "event_type": "tactile_onset",
                    "unix_time": relative_time,
                    "monotonic_time": relative_time,
                    "payload_json": json.dumps(
                        {
                            "planned": True,
                            "block_number": 1,
                            "relative_time_s": relative_time,
                        }
                    ),
                }
            )

    sample_rate = 1000
    samples = np.zeros((4500, 3), dtype=np.float32)
    for relative_time in planned_times:
        start = int((relative_time + 0.25) * sample_rate)
        samples[start : start + 10, 2] = 0.2
    sf.write(recording_dir / "Block_01_loopback.wav", samples, sample_rate)

    report = lv.validate_session_dir(session_dir, output_dir=session_dir / "analysis")

    assert report["passed"]
    assert report["blocks"][0]["matched_count"] == 3
    assert (session_dir / "analysis" / "session_latency_validation_report.json").exists()
