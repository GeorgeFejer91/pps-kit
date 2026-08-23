from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / "For-AI/engineering/validation" / "scripts"


def _load_script(name: str):
    path = SCRIPT_DIR / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    assert rows
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_wired_loopback_evidence(path: Path, *, healthy: bool = True) -> None:
    frames = 128 if healthy else 0
    data = np.zeros((frames, 4), dtype=np.float32)
    if healthy:
        data[:, 3] = 0.01
    sf.write(path, data, 44100, subtype="FLOAT")
    payload = {
        "schema": "pps-wired-loopback-evidence.v1",
        "mode": "wired_loopback_output4_tactile_proxy",
        "started": True,
        "path": str(path),
        "sample_rate": 44100,
        "channels": 4,
        "frames": frames,
        "frames_seen": frames,
        "duration_s": frames / 44100,
        "input_channel_1based": 4,
        "peak_by_channel": [0.0, 0.0, 0.0, 0.01 if healthy else 0.0],
        "dropped_buffer_count": 0,
        "interrupted": not healthy,
    }
    path.with_name(path.stem + ".output_evidence.json").write_text(json.dumps(payload), encoding="utf-8")


def test_study5_ui_mouse_prefers_packaged_runner_when_both_flags_are_set(tmp_path: Path, monkeypatch):
    ui = _load_script("run_study5_end_to_end_ui_mouse_validation.py")
    calls: list[tuple[str, bool, bool]] = []

    def fake_packaged(args):
        calls.append(("packaged", bool(args.packaged_standalone_app), bool(args.standalone_launcher)))
        return 0

    def fake_standalone(args):
        calls.append(("standalone", bool(args.packaged_standalone_app), bool(args.standalone_launcher)))
        return 0

    monkeypatch.setattr(ui, "_run_packaged_standalone_app_validation", fake_packaged)
    monkeypatch.setattr(ui, "_run_standalone_launcher_validation", fake_standalone)

    assert ui.main(["--output-dir", str(tmp_path), "--standalone-launcher", "--packaged-standalone-app"]) == 0
    assert calls == [("packaged", True, True)]


def test_dummy_pulse_stimulus_has_coded_three_channel_shape(tmp_path: Path):
    make = _load_script("make_dummy_pulse_stimulus.py")

    stimulus, rows, manifest = make.build_dummy_pulse_stimulus(sample_rate=1000, intervals_ms=[300, 800], amplitude=0.2)
    paths = make.write_dummy_pulse_files(tmp_path, stimulus=stimulus, planned_rows=rows, manifest=manifest)

    assert stimulus.shape[1] == 3
    assert len({row["pulse_index"] for row in rows}) == 3
    assert len(rows) == 9
    assert rows[0]["expected_sample_index"] == 1000
    assert rows[3]["expected_sample_index"] == 1300
    assert paths["wav"].exists()
    assert not np.allclose(stimulus[:, 0], stimulus[:, 1])
    assert not np.allclose(stimulus[:, 1], stimulus[:, 2])


def test_dummy_pulse_stimulus_supports_channel_specific_amplitudes(tmp_path: Path):
    make = _load_script("make_dummy_pulse_stimulus.py")

    channel_amplitudes = make.parse_channel_amplitudes(
        "1:0.01,2:0.02,3:0.03",
        default_amplitude=0.2,
        channel_count=3,
    )
    stimulus, rows, manifest = make.build_dummy_pulse_stimulus(
        sample_rate=1000,
        intervals_ms=[300],
        amplitude=0.2,
        channel_amplitudes=channel_amplitudes,
    )
    make.write_dummy_pulse_files(tmp_path, stimulus=stimulus, planned_rows=rows, manifest=manifest)

    assert np.max(np.abs(stimulus), axis=0).tolist() == pytest.approx([0.01, 0.02, 0.03])
    assert manifest["channel_amplitudes"] == {"1": 0.01, "2": 0.02, "3": 0.03}
    assert [row["amplitude"] for row in rows[:3]] == [0.01, 0.02, 0.03]
    assert make.channel_amplitude_for(manifest, 0) == pytest.approx(0.01)


def test_dummy_pulse_comparison_recovers_latency_and_identity(tmp_path: Path):
    make = _load_script("make_dummy_pulse_stimulus.py")
    compare = _load_script("compare_dummy_pulse_recordings.py")
    sample_rate = 1000
    stimulus, rows, manifest = make.build_dummy_pulse_stimulus(sample_rate=sample_rate, intervals_ms=[300, 800], amplitude=0.2)
    make.write_dummy_pulse_files(tmp_path, stimulus=stimulus, planned_rows=rows, manifest=manifest)

    delays = [10, 11, 12]
    capture = np.zeros((stimulus.shape[0] + 64, 3), dtype=np.float32)
    for channel, delay in enumerate(delays):
        capture[delay : delay + stimulus.shape[0], channel] = stimulus[:, channel]
    sf.write(tmp_path / "direct_loopback_capture.wav", capture, sample_rate)

    report = compare.compare_run(tmp_path)

    assert report["passed"]
    direct = report["captures"][0]
    assert direct["capture"] == "direct_loopback"
    assert [row["best_identity_source_channel"] for row in direct["channel_summaries"]] == [0, 1, 2]
    assert direct["skew_summary"]["left_right_median_abs_skew_ms"] == 1.0
    assert direct["skew_summary"]["tactile_audio_median_abs_skew_ms"] <= 2.0


def test_woojer_mechanical_onset_comparison_recovers_known_sensor_delay(tmp_path: Path):
    make = _load_script("make_dummy_pulse_stimulus.py")
    woojer = _load_script("compare_woojer_mechanical_onset.py")
    sample_rate = 1000
    sensor_delay_samples = 25
    stimulus, rows, manifest = make.build_dummy_pulse_stimulus(
        sample_rate=sample_rate,
        intervals_ms=[300, 800],
        amplitude=0.2,
    )
    make.write_dummy_pulse_files(tmp_path, stimulus=stimulus, planned_rows=rows, manifest=manifest)

    recording = np.zeros((stimulus.shape[0] + 128, 4), dtype=np.float32)
    recording[:, 2] = np.pad(stimulus[:, 2], (10, 128 - 10))[: recording.shape[0]]
    recording[:, 3] = np.pad(stimulus[:, 2] * 0.25, (10 + sensor_delay_samples, 128 - 10 - sensor_delay_samples))[
        : recording.shape[0]
    ]
    sf.write(tmp_path / "woojer_sensor_recording.wav", recording, sample_rate)

    report = woojer.compare_mechanical_onset(
        planned_pulses_csv=tmp_path / "planned_pulses.csv",
        electrical_recording=tmp_path / "woojer_sensor_recording.wav",
        sensor_recording=tmp_path / "woojer_sensor_recording.wav",
        output_dir=tmp_path / "woojer_report",
        electrical_channel_1based=3,
        sensor_channel_1based=4,
        min_sensor_peak=0.001,
    )

    assert report["passed"]
    assert report["electrical_detected_count"] == 3
    assert report["sensor_detected_count"] == 3
    assert report["electrical_minus_planned_ms"]["mean_ms"] == pytest.approx(10.0)
    assert report["mechanical_minus_electrical_ms"]["mean_ms"] == pytest.approx(25.0)
    assert report["mechanical_minus_electrical_ms"]["sd_ms"] == pytest.approx(0.0)
    assert (tmp_path / "woojer_report" / "woojer_mechanical_onset_report.json").exists()


def test_dummy_pulse_comparison_flags_wrong_channel_identity(tmp_path: Path):
    make = _load_script("make_dummy_pulse_stimulus.py")
    compare = _load_script("compare_dummy_pulse_recordings.py")
    sample_rate = 1000
    stimulus, rows, manifest = make.build_dummy_pulse_stimulus(sample_rate=sample_rate, intervals_ms=[300, 800], amplitude=0.2)
    make.write_dummy_pulse_files(tmp_path, stimulus=stimulus, planned_rows=rows, manifest=manifest)

    capture = np.zeros((stimulus.shape[0] + 64, 3), dtype=np.float32)
    capture[10 : 10 + stimulus.shape[0], 0] = stimulus[:, 1]
    capture[10 : 10 + stimulus.shape[0], 1] = stimulus[:, 0]
    capture[10 : 10 + stimulus.shape[0], 2] = stimulus[:, 2]
    sf.write(tmp_path / "direct_loopback_capture.wav", capture, sample_rate)

    report = compare.compare_run(tmp_path)

    assert not report["passed"]
    identities = [row["best_identity_source_channel"] for row in report["captures"][0]["channel_summaries"]]
    assert identities[:2] == [1, 0]


def test_dummy_pulse_comparison_uses_planned_windows_not_early_artifacts(tmp_path: Path):
    make = _load_script("make_dummy_pulse_stimulus.py")
    compare = _load_script("compare_dummy_pulse_recordings.py")
    sample_rate = 1000
    stimulus, rows, manifest = make.build_dummy_pulse_stimulus(sample_rate=sample_rate, intervals_ms=[300, 800], amplitude=0.2)
    make.write_dummy_pulse_files(tmp_path, stimulus=stimulus, planned_rows=rows, manifest=manifest)

    delay = 10
    capture = np.zeros((stimulus.shape[0] + 64, 3), dtype=np.float32)
    capture[delay : delay + stimulus.shape[0], :] = stimulus
    early = np.zeros_like(capture)
    early[100 : 100 + 40, 0] = 0.2
    capture[:, 0] += early[:, 0]
    sf.write(tmp_path / "direct_loopback_capture.wav", capture, sample_rate)

    report = compare.compare_run(tmp_path)
    left = report["captures"][0]["channel_summaries"][0]

    assert report["passed"]
    assert left["median_latency_ms"] == pytest.approx(10.0)
    assert left["p95_abs_residual_ms"] == pytest.approx(0.0)


def test_actual_block_loopback_comparison_recovers_channel_skew(tmp_path: Path):
    compare = _load_script("compare_actual_block_loopback.py")
    sample_rate = 1000
    source = np.zeros((220, 3), dtype=np.float32)
    source[20:80, 0] = np.sin(np.linspace(0, np.pi * 4, 60)).astype(np.float32) * 0.2
    source[20:80, 1] = np.sin(np.linspace(0, np.pi * 4, 60)).astype(np.float32) * 0.2
    source[40:60, 2] = 0.2
    source[120:180, 0] = source[20:80, 0]
    source[120:180, 1] = source[20:80, 1]
    source[140:160, 2] = 0.2
    capture = np.zeros((source.shape[0] + 32, 3), dtype=np.float32)
    delays = [10, 11, 12]
    for channel, delay in enumerate(delays):
        capture[delay : delay + source.shape[0], channel] = source[:, channel]
    source_wav = tmp_path / "source_block.wav"
    capture_wav = tmp_path / "capture.wav"
    sf.write(source_wav, source, sample_rate)
    sf.write(capture_wav, capture, sample_rate)
    block_csv = tmp_path / "block.csv"
    _write_csv(
        block_csv,
        [
            {
                "Trial_Number": 1,
                "Trial_UID": "T001",
                "Trial_Type": "Audio-Tactile",
                "Trial_Start_Sample": 0,
                "Trial_End_Sample": 100,
            },
            {
                "Trial_Number": 2,
                "Trial_UID": "T002",
                "Trial_Type": "Audio-Tactile",
                "Trial_Start_Sample": 100,
                "Trial_End_Sample": 200,
            },
        ],
    )

    report = compare.compare_loopback(
        source_wav=source_wav,
        capture_wav=capture_wav,
        block_csv=block_csv,
        output_dir=tmp_path / "report",
        min_capture_peak=0.001,
    )

    assert report["passed"]
    assert report["interchannel_skew_ms"]["right_minus_left"]["mean_ms"] == pytest.approx(1.0)
    assert report["interchannel_skew_ms"]["tactile_minus_audio_mean"]["mean_ms"] == pytest.approx(1.5)
    assert (tmp_path / "report" / "actual_block_loopback_report.json").exists()


def test_lsl_marker_probe_normalizes_rich_v2_and_compact_samples():
    probe = _load_script("lsl_marker_probe.py")

    rich = probe.parse_marker_sample(
        [
            "2.0",
            "event-1",
            "tactile_onset",
            "1005",
            "trial:01:001:T001:tactile_onset",
            "S001",
            "P001",
            "1",
            "T001",
            "44100",
            "dac_time_sample_exact",
            '{"trial_uid":"T001"}',
        ]
    )
    compact = probe.parse_marker_sample(
        [
            "dummy_pulse",
            "run_pulse_001",
            '{"block_number":2,"participant_id":"P001","sample_index":1000}',
        ]
    )

    assert rich["event_type"] == "tactile_onset"
    assert rich["event_code"] == "1005"
    assert rich["trigger_key"].startswith("trial:")
    assert rich["timestamp_quality"] == "dac_time_sample_exact"
    assert compact["event_type"] == "dummy_pulse"
    assert compact["block_index"] == 2
    assert compact["participant_id"] == "P001"
    assert compact["sample_index"] == 1000


def test_lsl_local_reconciliation_matches_rich_and_numeric_streams(tmp_path: Path):
    reconcile_mod = _load_script("reconcile_lsl_with_local_events.py")
    events_csv = tmp_path / "events.csv"
    rich_csv = tmp_path / "rich_probe.csv"
    numeric_csv = tmp_path / "numeric_probe.csv"
    lsl_markers_csv = tmp_path / "lsl_markers.csv"
    output_dir = tmp_path / "reconciliation"
    event_payloads = [
        {
            "event_code": 30,
            "trigger_key": "response:mouse_click",
            "session_id": "S001",
            "participant_id": "P001",
            "timestamp_quality": "software_log",
        },
        {
            "event_code": 31,
            "trigger_key": "response:marker_start",
            "session_id": "S001",
            "participant_id": "P001",
            "sample_index": 44100,
            "timestamp_quality": "dac_time_sample_exact",
        },
    ]
    _write_csv(
        events_csv,
        [
            {
                "event_id": "1",
                "event_type": "mouse_click",
                "unix_time": "100.0",
                "monotonic_time": "10.0",
                "payload_json": json.dumps(event_payloads[0]),
            },
            {
                "event_id": "2",
                "event_type": "response_marker_start",
                "unix_time": "100.008",
                "monotonic_time": "10.008",
                "payload_json": json.dumps(event_payloads[1]),
            },
            {
                "event_id": "3",
                "event_type": "trial_start",
                "unix_time": "101.0",
                "monotonic_time": "11.0",
                "payload_json": json.dumps({"planned": True, "event_code": 1000}),
            },
        ],
    )
    _write_csv(
        rich_csv,
        [
            {
                "arrival_lsl_clock": "10.001",
                "sample_lsl_timestamp": "10.000",
                "arrival_minus_sample_ms": "1.000",
                "marker_version": "2.0",
                "event_id": "1",
                "event_type": "mouse_click",
                "event_code": "30",
                "trigger_key": "response:mouse_click",
                "session_id": "S001",
                "participant_id": "P001",
                "block_index": "",
                "trial_uid": "",
                "sample_index": "",
                "timestamp_quality": "software_log",
                "payload_json": json.dumps(event_payloads[0]),
                "raw_sample_json": "[]",
            },
            {
                "arrival_lsl_clock": "10.003",
                "sample_lsl_timestamp": "10.008",
                "arrival_minus_sample_ms": "-5.000",
                "marker_version": "2.0",
                "event_id": "2",
                "event_type": "response_marker_start",
                "event_code": "31",
                "trigger_key": "response:marker_start",
                "session_id": "S001",
                "participant_id": "P001",
                "block_index": "",
                "trial_uid": "",
                "sample_index": "44100",
                "timestamp_quality": "dac_time_sample_exact",
                "payload_json": json.dumps(event_payloads[1]),
                "raw_sample_json": "[]",
            },
        ],
    )
    _write_csv(
        numeric_csv,
        [
            {
                "arrival_lsl_clock": "10.001",
                "sample_lsl_timestamp": "10.000",
                "arrival_minus_sample_ms": "1.000",
                "marker_version": "",
                "event_id": "",
                "event_type": "",
                "event_code": "30",
                "trigger_key": "",
                "session_id": "",
                "participant_id": "",
                "block_index": "",
                "trial_uid": "",
                "sample_index": "",
                "timestamp_quality": "",
                "payload_json": "",
                "raw_sample_json": '["30"]',
            },
            {
                "arrival_lsl_clock": "10.003",
                "sample_lsl_timestamp": "10.008",
                "arrival_minus_sample_ms": "-5.000",
                "marker_version": "",
                "event_id": "",
                "event_type": "",
                "event_code": "31",
                "trigger_key": "",
                "session_id": "",
                "participant_id": "",
                "block_index": "",
                "trial_uid": "",
                "sample_index": "",
                "timestamp_quality": "",
                "payload_json": "",
                "raw_sample_json": '["31"]',
            },
        ],
    )
    _write_csv(
        lsl_markers_csv,
        [
            {
                "event_id": "1",
                "event_type": "mouse_click",
                "event_code": "30",
                "trigger_key": "response:mouse_click",
                "lsl_timestamp": "10.000",
                "timestamp_quality": "software_log",
                "sample_index": "",
                "block_index": "",
                "trial_uid": "",
                "pushed_to_lsl": "True",
                "payload_json": json.dumps(event_payloads[0]),
            },
            {
                "event_id": "2",
                "event_type": "response_marker_start",
                "event_code": "31",
                "trigger_key": "response:marker_start",
                "lsl_timestamp": "10.008",
                "timestamp_quality": "dac_time_sample_exact",
                "sample_index": "44100",
                "block_index": "",
                "trial_uid": "",
                "pushed_to_lsl": "True",
                "payload_json": json.dumps(event_payloads[1]),
            },
        ],
    )

    report = reconcile_mod.reconcile(
        events_csv=events_csv,
        rich_lsl_probe_csv=rich_csv,
        numeric_lsl_probe_csv=numeric_csv,
        lsl_markers_csv=lsl_markers_csv,
        output_dir=output_dir,
    )

    assert report["passed"]
    assert report["rich"]["actual_local_event_count"] == 2
    assert report["rich"]["rich_lsl_sample_count"] == 2
    assert report["rich"]["field_mismatch_count"] == 0
    assert report["numeric"]["observed_code_counts"] == {"30": 1, "31": 1}
    assert (output_dir / "lsl_local_reconciliation_report.md").exists()
    assert (output_dir / "lsl_local_reconciliation_mismatches.csv").read_text(encoding="utf-8").count("\n") == 1


def test_response_timing_strategy_comparison_quantifies_lsl_arrival_delay(tmp_path: Path):
    compare_mod = _load_script("compare_response_timing_strategies.py")
    events_csv = tmp_path / "events.csv"
    rich_csv = tmp_path / "rich_probe.csv"
    output_dir = tmp_path / "strategy"
    _write_csv(
        events_csv,
        [
            {
                "event_id": "1",
                "event_type": "mouse_click",
                "unix_time": "100.0",
                "monotonic_time": "10.000",
                "payload_json": json.dumps({"click_index": 1}),
            },
            {
                "event_id": "2",
                "event_type": "response_marker_start",
                "unix_time": "100.008",
                "monotonic_time": "10.008",
                "payload_json": json.dumps({"mouse_event_id": 1, "click_index": 1, "planned_marker_delay_ms": "8.0"}),
            },
            {
                "event_id": "3",
                "event_type": "mouse_click",
                "unix_time": "101.0",
                "monotonic_time": "11.000",
                "payload_json": json.dumps({"click_index": 2}),
            },
            {
                "event_id": "4",
                "event_type": "response_marker_start",
                "unix_time": "101.008",
                "monotonic_time": "11.008",
                "payload_json": json.dumps({"mouse_event_id": 3, "click_index": 2, "planned_marker_delay_ms": "8.0"}),
            },
        ],
    )
    _write_csv(
        rich_csv,
        [
            {
                "arrival_lsl_clock": "10.0004",
                "sample_lsl_timestamp": "10.0001",
                "arrival_minus_sample_ms": "0.3",
                "marker_version": "2.0",
                "event_id": "1",
                "event_type": "mouse_click",
                "event_code": "30",
                "trigger_key": "control:mouse_click",
                "session_id": "S001",
                "participant_id": "P001",
                "block_index": "",
                "trial_uid": "",
                "sample_index": "",
                "timestamp_quality": "software_log",
                "payload_json": "{}",
                "raw_sample_json": "[]",
            },
            {
                "arrival_lsl_clock": "10.0030",
                "sample_lsl_timestamp": "10.0080",
                "arrival_minus_sample_ms": "-5.0",
                "marker_version": "2.0",
                "event_id": "2",
                "event_type": "response_marker_start",
                "event_code": "31",
                "trigger_key": "control:response_marker_start",
                "session_id": "S001",
                "participant_id": "P001",
                "block_index": "1",
                "trial_uid": "",
                "sample_index": "37",
                "timestamp_quality": "dac_time_sample_exact",
                "payload_json": "{}",
                "raw_sample_json": "[]",
            },
            {
                "arrival_lsl_clock": "11.0006",
                "sample_lsl_timestamp": "11.0002",
                "arrival_minus_sample_ms": "0.4",
                "marker_version": "2.0",
                "event_id": "3",
                "event_type": "mouse_click",
                "event_code": "30",
                "trigger_key": "control:mouse_click",
                "session_id": "S001",
                "participant_id": "P001",
                "block_index": "",
                "trial_uid": "",
                "sample_index": "",
                "timestamp_quality": "software_log",
                "payload_json": "{}",
                "raw_sample_json": "[]",
            },
            {
                "arrival_lsl_clock": "11.0032",
                "sample_lsl_timestamp": "11.0080",
                "arrival_minus_sample_ms": "-4.8",
                "marker_version": "2.0",
                "event_id": "4",
                "event_type": "response_marker_start",
                "event_code": "31",
                "trigger_key": "control:response_marker_start",
                "session_id": "S001",
                "participant_id": "P001",
                "block_index": "1",
                "trial_uid": "",
                "sample_index": "74",
                "timestamp_quality": "dac_time_sample_exact",
                "payload_json": "{}",
                "raw_sample_json": "[]",
            },
        ],
    )

    report = compare_mod.compare_strategies(
        events_csv=events_csv,
        rich_lsl_probe_csv=rich_csv,
        output_dir=output_dir,
    )

    assert report["passed"]
    assert report["paired_click_marker_count"] == 2
    assert report["metrics"]["local_marker_minus_mouse_ms"]["median_ms"] == pytest.approx(8.0)
    assert report["metrics"]["lsl_mouse_arrival_minus_local_mouse_ms"]["median_ms"] == pytest.approx(0.5)
    assert report["metrics"]["marker_lsl_arrival_minus_sample_ms"]["median_ms"] == pytest.approx(-4.9)
    assert (output_dir / "response_timing_strategy_pairs.csv").exists()


def test_mouse_response_timing_stress_links_clicks_and_markers(tmp_path: Path):
    stress = _load_script("run_mouse_response_timing_stress.py")

    report = stress.run_stress(
        output_dir=tmp_path,
        count=3,
        interval_s=0.001,
        start_delay_s=0.0,
        planned_marker_delay_ms=8.0,
        callback_lead_ms=5.805,
        sample_rate=44100,
        blocksize=256,
        marker_gain=0.08,
        enable_lsl=False,
        warmup_s=0.0,
        realtime=False,
        flush_each=True,
    )

    assert report["passed"]
    assert report["mouse_click_count"] == 3
    assert report["response_marker_start_count"] == 3
    assert report["response_timestamp_quality_counts"] == {"dac_time_sample_exact": 3}
    assert report["marker_minus_mouse_ms"]["median_ms"] == pytest.approx(8.0)
    timing_qc = (tmp_path / "timing_qc.csv").read_text(encoding="utf-8")
    assert "delay_clock" in timing_qc
    assert "monotonic" in timing_qc


def test_dummy_output_route_sweep_refuses_hot_hardware_amplitude(tmp_path: Path):
    sweep = _load_script("run_dummy_output_route_sweep.py")

    with pytest.raises(ValueError, match="Refusing hardware playback amplitude"):
        sweep.run_sweep(
            output_dir=tmp_path,
            device=None,
            device_query="Komplete",
            sample_rate=44100,
            intervals_ms=[300, 800],
            pre_roll_s=1.0,
            post_roll_s=1.0,
            amplitude=0.20,
            input_channels=6,
            output_channels=3,
            sweep_output_count=3,
            latency_s=0.010,
            blocksize=256,
            allow_non_asio=False,
            capture_tail_s=0.5,
            search_pre_ms=25.0,
            search_post_ms=200.0,
        )


def test_dummy_output_route_sweep_refuses_selector_count_above_open_outputs(tmp_path: Path):
    sweep = _load_script("run_dummy_output_route_sweep.py")

    with pytest.raises(ValueError, match="sweep_output_count cannot exceed output_channels"):
        sweep.run_sweep(
            output_dir=tmp_path,
            device=None,
            device_query="Komplete",
            sample_rate=44100,
            intervals_ms=[300, 800],
            pre_roll_s=1.0,
            post_roll_s=1.0,
            amplitude=0.05,
            input_channels=6,
            output_channels=3,
            sweep_output_count=4,
            latency_s=0.010,
            blocksize=256,
            allow_non_asio=False,
            capture_tail_s=0.5,
            search_pre_ms=25.0,
            search_post_ms=200.0,
        )


def test_dummy_signal_level_qc_flags_visible_but_not_baseline_channel(tmp_path: Path):
    make = _load_script("make_dummy_pulse_stimulus.py")
    levels = _load_script("analyze_dummy_signal_levels.py")
    sample_rate = 1000
    stimulus, rows, manifest = make.build_dummy_pulse_stimulus(
        sample_rate=sample_rate,
        intervals_ms=[300, 800],
        amplitude=0.05,
    )
    manifest["output_channels"] = 3
    make.write_dummy_pulse_files(tmp_path, stimulus=stimulus, planned_rows=rows, manifest=manifest)

    rng = np.random.default_rng(123)
    gains = [1.0, 0.01, 1.0]
    for output_channel, gain in enumerate(gains):
        capture = rng.normal(0.0, 1e-6, size=(stimulus.shape[0] + 128, 3)).astype(np.float32)
        capture[: stimulus.shape[0], output_channel] += stimulus[:, output_channel] * gain
        sf.write(tmp_path / f"output_{output_channel + 1}_capture.wav", capture, sample_rate)

    report = levels.analyze_run(tmp_path)

    assert report["all_visible_above_noise"]
    assert not report["all_accepted_for_latency_baseline"]
    assert report["channels"][0]["accepted_for_latency_baseline"]
    assert report["channels"][1]["visible_above_noise"]
    assert not report["channels"][1]["accepted_for_latency_baseline"]
    assert report["channels"][2]["accepted_for_latency_baseline"]


def test_validation_evidence_audit_uses_publication_facing_baseline_boundary(tmp_path: Path):
    audit_mod = _load_script("build_validation_evidence_audit.py")

    paths = {
        "audio_stress": tmp_path / "audio_stress.json",
        "dummy_comparison": tmp_path / "dummy_comparison.json",
        "dummy_route_sweep": tmp_path / "dummy_route_sweep.json",
        "dummy_signal_qc": tmp_path / "dummy_signal_qc.json",
        "safe_calibration": tmp_path / "safe_calibration.json",
        "lsl_reconciliation": tmp_path / "lsl_reconciliation.json",
        "response_strategy": tmp_path / "response_strategy.json",
        "mouse_response": tmp_path / "mouse_response.json",
        "session_runner_click_path": tmp_path / "session_runner_click_path.json",
        "visible_runner_os_click": tmp_path / "visible_runner_os_click.json",
        "actual_condition_one_block": tmp_path / "actual_condition_one_block.json",
        "recording_layer_alignment": tmp_path / "recording_layer_alignment.json",
        "pc_software_requirements": tmp_path / "pc_software_requirements.json",
        "labrecorder_xdf": tmp_path / "labrecorder_xdf.json",
        "report_pdf": tmp_path / "latency_reliability_validations.pdf",
    }

    payloads = {
        "audio_stress": {"recommendation": {"status": "spatial_ready"}},
        "dummy_comparison": {"captures": []},
        "dummy_route_sweep": {"expected_identity_route_passed": False},
        "dummy_signal_qc": {"all_accepted_for_latency_baseline": False},
        "safe_calibration": {"passed": False, "channel_summaries": []},
        "lsl_reconciliation": {
            "passed": True,
            "rich": {"compared_event_count": 2, "rich_lsl_sample_count": 2, "field_mismatch_count": 0},
            "numeric": {"numeric_lsl_sample_count": 2},
        },
        "response_strategy": {
            "passed": True,
            "metrics": {
                "lsl_mouse_sample_minus_local_mouse_ms": {"median_ms": 0.067},
                "lsl_mouse_arrival_minus_local_mouse_ms": {"median_ms": 0.339},
                "local_marker_minus_mouse_ms": {"median_ms": 8.0},
            },
        },
        "mouse_response": {"passed": True, "mouse_click_count": 2, "response_marker_start_count": 2},
        "session_runner_click_path": {
            "passed": True,
            "mouse_click_count": 2,
            "response_marker_start_count": 2,
            "marker_minus_mouse_ms": {"median_ms": 8.1, "max_ms": 8.3},
        },
        "visible_runner_os_click": {
            "passed": True,
            "armed": True,
            "requested_click_count": 2,
            "mouse_click_count": 2,
            "response_marker_start_count": 2,
            "in_target_mouse_click_count": 2,
            "during_playback_mouse_click_count": 2,
            "marker_minus_mouse_ms": {"median_ms": 8.2},
        },
        "actual_condition_one_block": {
            "passed": False,
            "evidence_level": "development_or_fixture",
            "trial_count": 5,
            "analysis_ready_trial_count": 5,
            "xdf": {"loaded": True, "sample_count": 43},
            "lsl_marker_count": 43,
            "suspicious_non_actual_sources": ["segment_fixture"],
        },
        "recording_layer_alignment": {
            "passed": True,
            "audio": {
                "physical_minus_digital_latency_ms": {"mean_ms": 33.46, "sd_ms": 0.01, "median_ms": 33.47, "p95_ms": 33.47, "min_ms": 33.45, "max_ms": 33.47},
                "interchannel_skew": {"right_minus_left_ms": -0.023, "tactile_minus_audio_mean_ms": 0.011},
                "digital_metadata": {"dropped_buffer_count": 0, "clipped_channels_1based": []},
            },
            "internal_lsl": {
                "event_count": 146,
                "marker_count": 146,
                "missing_marker_event_ids": [],
                "extra_marker_event_ids": [],
                "duplicate_event_ids": [],
                "lsl_timestamp_error_ms": {"p95_ms": 0.0},
            },
            "response_marker_loopback": {
                "expected_marker_count": 20,
                "detected_marker_count": 20,
                "abs_residual_ms": {"p95_ms": 0.0},
            },
            "external_lsl": {"checked": False},
        },
        "pc_software_requirements": {
            "summary": {
                "missing_runtime_packages": [],
                "missing_validation_packages": [],
                "missing_external_tools": [],
                "komplete_asio_registry_present": True,
                "komplete_asio_sounddevice_ready": True,
            }
        },
        "labrecorder_xdf": {
            "passed": True,
            "comparison": {
                "passed": True,
                "expected_marker_count": 2,
                "rich_xdf_sample_count": 2,
                "numeric_xdf_sample_count": 2,
                "missing_event_ids": [],
                "field_mismatches": [],
                "timestamp_delta_xdf_minus_local_marker_ms": {"mean_ms": -0.005},
            },
        },
    }
    for key, payload in payloads.items():
        paths[key].write_text(json.dumps(payload), encoding="utf-8")
    paths["report_pdf"].write_bytes(b"%PDF-1.4\n")

    audit = audit_mod.build_audit(paths)
    evidence_blob = json.dumps(audit, sort_keys=True).lower()

    assert audit["completion_gate"]["complete"] is False
    assert "One 3-channel WAV routes to the intended physical channel identities" in audit["completion_gate"]["reason"]
    assert "Publication-grade all-channel electrical latency/skew baseline" in audit["completion_gate"]["reason"]
    assert "channel 2" not in evidence_blob
    assert "tactile-left" not in evidence_blob
    assert "publication-selected all-channel route identity dataset" in evidence_blob
    assert "exploratory route/level setup captures are excluded" in evidence_blob
    assert "windows validation pc software dependencies" in evidence_blob
    assert "external labrecorder xdf preserves" in evidence_blob
    assert "visible tk runner os-click stress passed=true" in evidence_blob
    assert "one actual prepared experimental block" in evidence_blob
    assert "physical-minus-digital latency" in evidence_blob
    assert audit["status_counts"]["proven"] >= 5


def test_validation_evidence_audit_resolves_latest_visible_runner_click(tmp_path: Path):
    audit_mod = _load_script("build_validation_evidence_audit.py")
    run_root = tmp_path / "artifacts" / "validation_runs"
    older = run_root / "visible_runner_os_click_stress_20260101_000000"
    newer = run_root / "visible_runner_os_click_stress_20260101_000001"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "visible_runner_os_click_report.json").write_text(
        json.dumps({"passed": False, "requested_click_count": 1}),
        encoding="utf-8",
    )
    (newer / "visible_runner_os_click_report.json").write_text(
        json.dumps({"passed": True, "requested_click_count": 3}),
        encoding="utf-8",
    )

    paths = audit_mod.resolve_artifact_paths(tmp_path)

    assert paths["visible_runner_os_click"] == newer / "visible_runner_os_click_report.json"


def test_validation_evidence_audit_resolves_latest_route_sweep(tmp_path: Path):
    audit_mod = _load_script("build_validation_evidence_audit.py")
    run_root = tmp_path / "artifacts" / "validation_runs"
    older = run_root / "final_functional_route_sweep_20260101_000000"
    newer = run_root / "final_functional_route_sweep_20260101_000001"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    (older / "dummy_output_route_sweep_report.json").write_text(
        json.dumps({"expected_identity_route_passed": False, "amplitude": 0.05, "outputs": []}),
        encoding="utf-8",
    )
    (newer / "dummy_output_route_sweep_report.json").write_text(
        json.dumps(
            {
                "expected_identity_route_passed": False,
                "amplitude": 0.05,
                "outputs": [
                    {"output_channel_1based": 1, "expected_input_1based": 1, "detected_inputs_1based": [1], "identity_ok": True},
                    {"output_channel_1based": 2, "expected_input_1based": 2, "detected_inputs_1based": [], "identity_ok": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    (newer / "dummy_signal_level_qc.json").write_text(
        json.dumps(
            {
                "all_visible_above_noise": True,
                "all_accepted_for_latency_baseline": False,
                "channels": [
                    {
                        "output_channel_1based": 1,
                        "expected_input_channel_1based": 1,
                        "median_pulse_peak": 0.4,
                        "visible_above_noise": True,
                        "accepted_for_latency_baseline": True,
                        "clipped": False,
                    },
                    {
                        "output_channel_1based": 2,
                        "expected_input_channel_1based": 2,
                        "median_pulse_peak": 0.006,
                        "visible_above_noise": True,
                        "accepted_for_latency_baseline": False,
                        "clipped": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    paths = audit_mod.resolve_artifact_paths(tmp_path)

    assert paths["dummy_route_sweep"] == newer / "dummy_output_route_sweep_report.json"
    assert paths["dummy_signal_qc"] == newer / "dummy_signal_level_qc.json"


def test_pc_software_requirements_audit_records_dependency_sections():
    audit_mod = _load_script("audit_pc_software_requirements.py")

    audit = audit_mod.build_audit()
    package_names = {row["package"] for row in audit["python_packages"]}
    tool_names = {row["name"] for row in audit["external_tools"]}
    driver_names = {row["name"] for row in audit["windows_drivers"]}

    assert audit["schema"] == "pps-pc-software-requirements-audit.v1"
    assert "sounddevice" in package_names
    assert "pylsl" in package_names
    assert "pyxdf" in package_names
    assert "LabRecorder" in tool_names
    assert any("Komplete Audio 6" in name for name in driver_names)
    assert "komplete_asio_sounddevice_ready" in audit["summary"]


def test_labrecorder_xdf_comparison_matches_rich_and_numeric_samples():
    labrec = _load_script("run_labrecorder_lsl_xdf_stress.py")
    marker_rows = [
        {
            "event_id": "1",
            "event_type": "session_start",
            "event_code": "1",
            "trigger_key": "control:session_start",
            "block_index": "",
            "trial_uid": "",
            "sample_index": "",
            "timestamp_quality": "software_log",
            "lsl_timestamp": "10.000000000",
            "pushed_to_lsl": "True",
            "payload_json": json.dumps({"session_id": "S", "participant_id": "P"}),
        },
        {
            "event_id": "2",
            "event_type": "test_marker",
            "event_code": "50",
            "trigger_key": "control:test_marker",
            "block_index": "1",
            "trial_uid": "T001",
            "sample_index": "44100",
            "timestamp_quality": "software_log",
            "lsl_timestamp": "10.050000000",
            "pushed_to_lsl": "True",
            "payload_json": json.dumps({"session_id": "S", "participant_id": "P"}),
        },
    ]
    rich_rows = [
        {**marker_rows[0], "session_id": "S", "participant_id": "P", "sample_lsl_timestamp": "10.000000000"},
        {**marker_rows[1], "session_id": "S", "participant_id": "P", "sample_lsl_timestamp": "10.050000000"},
    ]
    numeric_rows = [
        {"event_code": "1", "sample_lsl_timestamp": "10.000000000"},
        {"event_code": "50", "sample_lsl_timestamp": "10.050000000"},
    ]

    report = labrec.compare_xdf_to_local(rich_rows=rich_rows, numeric_rows=numeric_rows, marker_rows=marker_rows)

    assert report["passed"]
    assert report["expected_marker_count"] == 2
    assert report["rich_xdf_sample_count"] == 2
    assert report["numeric_xdf_sample_count"] == 2
    assert report["field_mismatches"] == []
    assert report["timestamp_delta_xdf_minus_local_marker_ms"]["max_ms"] == pytest.approx(0.0)


def test_session_runner_click_path_stress_uses_controller_log_click(tmp_path: Path):
    stress = _load_script("run_session_runner_click_path_stress.py")

    report = stress.run_stress(
        output_dir=tmp_path,
        count=3,
        interval_s=0.001,
        start_delay_s=0.0,
        planned_marker_delay_ms=8.0,
        sample_rate=44100,
        block_hold_s=0.1,
    )

    assert report["passed"]
    assert report["mouse_click_count"] == 3
    assert report["response_marker_start_count"] == 3
    assert report["linked_pair_count"] == 3
    assert report["response_timestamp_quality_counts"] == {"dac_time_sample_exact": 3}
    assert report["marker_minus_mouse_ms"]["median_ms"] == pytest.approx(8.0, abs=0.75)
    assert (tmp_path / "session_runner_click_pairs.csv").exists()


def test_one_block_trial_runner_realtime_stress_writes_analysis_ready_outputs(tmp_path: Path):
    pytest.importorskip("pyxdf")
    stress = _load_script("run_one_block_trial_runner_realtime_stress.py")

    report = stress.run_stress(
        output_dir=tmp_path,
        participant_id="P001",
        trial_count=2,
        sample_rate=44100,
        trial_duration_s=0.45,
        blocksize=256,
        enable_lsl=False,
        response_marker_delay_ms=8.0,
    )

    assert report["passed"]
    assert report["event_type_counts"]["trial_end"] == 2
    assert report["event_type_counts"]["mouse_click"] == 2
    assert report["analysis_ready_trial_count"] == 2
    assert report["analysis_ready_hit_count"] == 2
    assert report["xdf"]["loaded"]
    assert Path(report["analysis_ready_trials_csv"]).exists()
    assert (tmp_path / "analysis_ready_trials.csv").exists()


def test_protocol11_artifact_auditor_accepts_one_block_runner_outputs(tmp_path: Path):
    pytest.importorskip("pyxdf")
    stress = _load_script("run_one_block_trial_runner_realtime_stress.py")
    validator = _load_script("validate_protocol11_emulated_runner_artifacts.py")

    stress_report = stress.run_stress(
        output_dir=tmp_path / "runner",
        participant_id="P001",
        trial_count=2,
        sample_rate=44100,
        trial_duration_s=0.45,
        blocksize=256,
        enable_lsl=False,
        response_marker_delay_ms=8.0,
    )
    analysis_rows = list(csv.DictReader(Path(stress_report["analysis_ready_trials_csv"]).open(encoding="utf-8")))
    plan_path = tmp_path / "protocol11_response_plan.json"
    plan_path.write_text(
        json.dumps(
            {
                "schema": "pps-protocol11-response-plan.v1",
                "expected_capture_options": stress_report["capture_options"],
                "trials": [
                    {
                        "trial_uid": row["trial_uid"],
                        "action": "hit",
                        "planned_rt_ms": row["rt_ms"],
                        "rt_tolerance_ms": 1.0,
                    }
                    for row in analysis_rows
                ],
            }
        ),
        encoding="utf-8",
    )

    audit = validator.validate_artifacts(
        Path(stress_report["session_dir"]),
        response_plan_path=plan_path,
        output_dir=tmp_path / "protocol11_audit",
    )

    assert audit["passed"]
    assert audit["sections"]["stimulus_assembly"]["passed"]
    assert audit["sections"]["timing_event_schedule"]["passed"]
    assert audit["sections"]["response_marker_path"]["passed"]
    assert audit["response_plan_audit"]["planned_count"] == 2
    assert (tmp_path / "protocol11_audit" / "protocol11_emulated_runner_artifact_audit.json").exists()


def test_protocol11_controlled_response_matrix_exercises_boundary_pairing(tmp_path: Path):
    matrix = _load_script("run_protocol11_controlled_response_matrix.py")

    report = matrix.run_matrix(
        output_dir=tmp_path,
        participant_id="P011",
        sample_rate=44100,
        blocksize=512,
        enable_lsl=False,
        response_marker_delay_ms=8.0,
    )

    assert report["passed"]
    assert report["checks"]["early_99ms_rejected"]
    assert report["checks"]["boundary_100ms_accepted"]
    assert report["checks"]["next_trial_start_click_accepted_previous"]
    assert report["checks"]["max_1300ms_accepted"]
    assert report["checks"]["late_1301ms_rejected"]
    assert report["artifact_audit_passed"]
    assert Path(report["response_plan_json"]).exists()
    assert Path(report["artifact_audit_json"]).exists()


def test_protocol11_capture_options_matrix_respects_output_toggles(tmp_path: Path):
    matrix = _load_script("run_protocol11_capture_options_matrix.py")

    report = matrix.run_matrix(
        output_dir=tmp_path,
        participant_id="P011",
        sample_rate=44100,
        trial_count=2,
        trial_duration_s=0.25,
    )

    assert report["passed"]
    variants = {variant["name"]: variant for variant in report["variants"]}
    assert set(variants) == {
        "standard_all_local",
        "events_only_no_recording",
        "xdf_without_events_csv",
        "analysis_without_xdf_or_lsl",
        "marker_mirror_only",
    }
    standard = variants["standard_all_local"]
    assert standard["file_inventory"]["events_csv"]["exists"]
    assert standard["file_inventory"]["events_xdf"]["exists"]
    assert standard["file_inventory"]["lsl_markers_xdf"]["exists"]
    assert standard["file_inventory"]["trigger_dictionary_json"]["exists"]
    assert standard["file_inventory"]["analysis_csv_count"] > 0
    assert standard["recording_paths"]

    events_only = variants["events_only_no_recording"]
    assert events_only["file_inventory"]["events_csv"]["exists"]
    assert not events_only["file_inventory"]["events_xdf"]["exists"]
    assert not events_only["file_inventory"]["lsl_markers_csv"]["exists"]
    assert events_only["file_inventory"]["analysis_csv_count"] == 0
    assert events_only["checks"]["recording_disabled_logged"]

    xdf_only = variants["xdf_without_events_csv"]
    assert not xdf_only["file_inventory"]["events_csv"]["exists"]
    assert xdf_only["file_inventory"]["events_xdf"]["exists"]

    marker_only = variants["marker_mirror_only"]
    assert not marker_only["file_inventory"]["events_csv"]["exists"]
    assert marker_only["file_inventory"]["lsl_markers_csv"]["exists"]
    assert marker_only["file_inventory"]["lsl_markers_xdf"]["exists"]
    assert marker_only["file_inventory"]["trigger_dictionary_json"]["exists"]
    assert marker_only["file_inventory"]["analysis_csv_count"] == 0
    assert (tmp_path / "protocol11_capture_options_matrix_variants.csv").exists()


def test_protocol11_study5_readiness_auditor_checks_xdf_audio_and_scope(tmp_path: Path):
    pytest.importorskip("pyxdf")
    from PIL import Image

    src_root = REPO_ROOT / "packages" / "pps-runtime" / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    from peripersonal_space_toolkit.session_events import SessionEventLogger
    from peripersonal_space_toolkit.timing_events import TimingEventHub

    auditor = _load_script("audit_protocol11_study5_readiness.py")

    artifact_dir = tmp_path / "real_asio_fixture"
    session_dir = artifact_dir / "session_one_block"
    blocks_dir = session_dir / "blocks"
    analysis_dir = session_dir / "analysis"
    blocks_dir.mkdir(parents=True)
    analysis_dir.mkdir()

    participant_id = "PVAL001"
    session_id = "PVAL001_study5_fixture"
    block_label = "Study 5 realtime fixture block"
    sample_rate = 1000
    block_rows = [
        {
            "Trial_Number": 1,
            "Trial_UID": "T001",
            "Trial_Type": "Audio-Tactile",
            "Family": "audio_tactile",
            "SOA_ms": 200,
            "Trial_Start_S": "0.000000000",
            "Looming_Onset_S": "0.200000000",
            "Tactile_Onset_S": "0.400000000",
            "Response_Window_Onset_S": "0.200000000",
            "Trial_End_S": "1.000000000",
            "Trial_Duration_S": "1.000000000",
            "Sample_Rate_Hz": sample_rate,
            "Channels": 3,
            "Trial_Start_Sample": 0,
            "Looming_Onset_Sample": 200,
            "Tactile_Onset_Sample": 400,
            "Response_Window_Onset_Sample": 200,
            "Trial_End_Sample": 1000,
        },
        {
            "Trial_Number": 2,
            "Trial_UID": "T002",
            "Trial_Type": "Baseline",
            "Family": "baseline",
            "SOA_ms": "",
            "Trial_Start_S": "1.000000000",
            "Looming_Onset_S": "",
            "Tactile_Onset_S": "0.300000000",
            "Response_Window_Onset_S": "0.300000000",
            "Trial_End_S": "2.000000000",
            "Trial_Duration_S": "1.000000000",
            "Sample_Rate_Hz": sample_rate,
            "Channels": 3,
            "Trial_Start_Sample": 1000,
            "Looming_Onset_Sample": "",
            "Tactile_Onset_Sample": 1300,
            "Response_Window_Onset_Sample": 1300,
            "Trial_End_Sample": 2000,
        },
        {
            "Trial_Number": 3,
            "Trial_UID": "T003",
            "Trial_Type": "Catch",
            "Family": "catch",
            "SOA_ms": "",
            "Trial_Start_S": "2.000000000",
            "Looming_Onset_S": "0.200000000",
            "Tactile_Onset_S": "",
            "Response_Window_Onset_S": "0.200000000",
            "Trial_End_S": "3.000000000",
            "Trial_Duration_S": "1.000000000",
            "Sample_Rate_Hz": sample_rate,
            "Channels": 3,
            "Trial_Start_Sample": 2000,
            "Looming_Onset_Sample": 2200,
            "Tactile_Onset_Sample": "",
            "Response_Window_Onset_Sample": 2200,
            "Trial_End_Sample": 3000,
        },
    ]
    block_csv = blocks_dir / "Block_01_from_study5_fixture.csv"
    _write_csv(block_csv, block_rows)

    block_audio = np.zeros((3000, 3), dtype=np.float32)
    block_audio[200:230, 0:2] = 0.25
    block_audio[400:430, 2] = 0.5
    block_audio[1300:1330, 2] = 0.5
    block_audio[2200:2230, 0:2] = 0.25
    block_wav = blocks_dir / "Block_01_from_study5_fixture.wav"
    sf.write(block_wav, block_audio, sample_rate)

    evidence_audio = np.zeros((3000, 4), dtype=np.float32)
    evidence_audio[:, :3] = block_audio
    evidence_audio[570:590, 2] = 0.45
    evidence_audio[1470:1490, 2] = 0.45
    evidence_wav = session_dir / "fixture_audio_evidence.wav"
    sf.write(evidence_wav, evidence_audio, sample_rate)
    evidence_sidecar = {
        "schema": "pps-digital-output-evidence.v1",
        "mode": "digital_output_evidence_wav",
        "device_name": "Komplete Audio ASIO Driver",
        "hostapi": "ASIO",
        "runtime_output_channels": 4,
        "tactile_output_channel_1based": 3,
        "sample_rate": sample_rate,
        "sample_rate_hz": sample_rate,
        "channels": 4,
        "frames": 3000,
        "duration_s": 3.0,
        "peak_by_channel": [0.25, 0.25, 0.5, 0.0],
        "clipped_channels_1based": [],
        "dropped_buffer_count": 0,
        "interrupted": False,
        "path": str(evidence_wav),
    }
    (session_dir / "fixture_audio_evidence.output_evidence.json").write_text(json.dumps(evidence_sidecar), encoding="utf-8")

    manifest = {
        "schema": "pps-runner-session-manifest.v1",
        "session_id": session_id,
        "participant_id": participant_id,
        "session_dir": str(session_dir),
        "validation_context": {"profile_id": "study5_box_breathing_pps"},
        "outputs": {"analysis_dir": str(analysis_dir)},
        "blocks": [
            {
                "label": block_label,
                "wav_path": str(block_wav),
                "manifest_path": str(block_csv),
                "trial_count": 3,
                "duration_s": 3.0,
                "metadata": {"sample_rate_hz": sample_rate, "channels": 3, "source_block_label": "Study 5 fixture"},
            }
        ],
    }
    (session_dir / "session_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    metadata = {
        "schema": "pps-runner-session-metadata.v1",
        "session_id": session_id,
        "participant": {"participant_id": participant_id},
        "experiment": {
            "template_id": "study5_box_breathing_pps",
            "parts_per_participant": 2,
            "instruction_profile": {"slots": [{"source": "original_study5"}]},
            "run_setup_snapshot": {"blocks_per_part": 6},
        },
    }
    (session_dir / "session_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    (session_dir / "analysis_summary.txt").write_text("fixture analysis summary\n", encoding="utf-8")
    (session_dir / "design.json").write_text("{}", encoding="utf-8")
    (session_dir / "protocol_schedule.csv").write_text("block,trial\n1,1\n", encoding="utf-8")

    logger = SessionEventLogger(participant_id)
    hub = TimingEventHub(logger, enable_lsl=False, session_id=session_id, participant_id=participant_id)

    capture_options = {
        "enable_lsl": True,
        "start_backup_recording": True,
        "write_analysis_csvs": True,
        "write_events_csv": True,
        "write_internal_xdf": True,
        "write_lsl_marker_mirror": True,
        "write_trigger_dictionary": True,
    }

    def log_event(event_type: str, seconds: float, **payload):
        payload.setdefault("lsl_timestamp", seconds)
        return hub.log(event_type, unix_time=1000.0 + seconds, monotonic_time=500.0 + seconds, **payload)

    log_event("session_start", 0.0, capture_options=capture_options)
    log_event("block_start", 0.1, block_number=1, block_label=block_label)
    log_event("block_schedule_loaded", 0.11, block_index=1, block_number=1, block_label=block_label)
    log_event("recording_start", 0.12, block_number=1, block_label=block_label)
    log_event(
        "audio_sample_zero",
        0.13,
        block_index=1,
        block_number=1,
        block_label=block_label,
        sample_index=0,
        sample_rate=sample_rate,
        timestamp_quality="dac_time_sample_exact",
        timestamp_anchor="audio_sample_zero",
    )

    mouse_marker_pairs = []
    for row in block_rows:
        trial_number = int(row["Trial_Number"])
        trial_uid = str(row["Trial_UID"])
        start_sample = int(row["Trial_Start_Sample"])
        start_s = start_sample / sample_rate
        common = {
            "block_index": 1,
            "block_number": 1,
            "block_label": block_label,
            "trial_number": trial_number,
            "trial_uid": trial_uid,
            "sample_rate": sample_rate,
            "timestamp_quality": "dac_time_sample_exact",
            "timestamp_anchor": "audio_sample_zero",
        }
        log_event(
            "trial_start",
            1.0 + start_s,
            **common,
            sample_index=start_sample,
            planned_sample_index=start_sample,
            trigger_key=f"trial:01:{trial_number:03d}:{trial_uid}:trial_start",
        )
        if row["Looming_Onset_Sample"] != "":
            sample = int(row["Looming_Onset_Sample"])
            log_event(
                "looming_onset",
                1.0 + sample / sample_rate,
                **common,
                sample_index=sample,
                planned_sample_index=sample,
                trigger_key=f"trial:01:{trial_number:03d}:{trial_uid}:looming_onset",
            )
        if row["Tactile_Onset_Sample"] != "":
            sample = int(row["Tactile_Onset_Sample"])
            log_event(
                "tactile_onset",
                1.0 + sample / sample_rate,
                **common,
                sample_index=sample,
                planned_sample_index=sample,
                trigger_key=f"trial:01:{trial_number:03d}:{trial_uid}:tactile_onset",
            )
            mouse = log_event("mouse_click", 1.0 + sample / sample_rate + 0.15, block_number=1, block_label=block_label, trial_uid=trial_uid)
            marker = log_event(
                "response_marker_start",
                1.0 + sample / sample_rate + 0.17,
                block_number=1,
                block_label=block_label,
                mouse_event_id=mouse.event_id,
                sample_index=sample + 170,
                sample_rate=sample_rate,
                timestamp_quality="dac_time_sample_exact",
                timestamp_anchor="audio_sample_zero",
            )
            mouse_marker_pairs.append((mouse.event_id, marker.event_id, trial_uid))
        response_sample = int(row["Response_Window_Onset_Sample"])
        log_event(
            "response_window_onset",
            1.0 + response_sample / sample_rate,
            **common,
            sample_index=response_sample,
            planned_sample_index=response_sample,
            trigger_key=f"trial:01:{trial_number:03d}:{trial_uid}:response_window_onset",
        )
        end_sample = int(row["Trial_End_Sample"])
        log_event(
            "trial_end",
            1.0 + end_sample / sample_rate,
            **common,
            sample_index=end_sample,
            planned_sample_index=end_sample,
            trigger_key=f"trial:01:{trial_number:03d}:{trial_uid}:trial_end",
        )

    log_event("recording_end", 4.2, block_number=1, block_label=block_label)
    log_event("block_end", 4.3, block_number=1, block_label=block_label, completed=True)
    log_event("session_end", 4.4, completed=True, interrupted=False)

    logger.write_csv(session_dir / "events.csv")
    logger.write_xdf(session_dir / "events.xdf")
    hub.write_lsl_markers_csv(session_dir / "lsl_markers.csv")
    hub.write_lsl_markers_xdf(session_dir / "lsl_markers.xdf")
    hub.write_trigger_dictionary(session_dir / "trigger_dictionary.json")

    analysis_rows = [
        {
            "trial_uid": trial_uid,
            "hit": "True",
            "rt_ms": "150.0",
            "primary_analysis_included": "True",
            "trial_type": "Audio-Tactile",
            "click_event_id": str(mouse_id),
        }
        for mouse_id, _marker_id, trial_uid in mouse_marker_pairs
    ]
    for suffix in ("responses", "analysis_ready_trials", "final_trial_outcomes"):
        _write_csv(analysis_dir / f"{session_id}_{suffix}.csv", analysis_rows)
    _write_csv(analysis_dir / f"{session_id}_summary.csv", [{"participant_id": participant_id, "n": 2, "hits": 2, "hit_rate": 1.0}])
    _write_csv(analysis_dir / f"{session_id}_pps_curve_points.csv", [{"soa_ms": 200, "n": 1, "mean_rt_ms": 150.0}])
    _write_csv(analysis_dir / f"{session_id}_model_fits.csv", [{"model": "linear", "n_points": 1, "aic": 0.0}])
    _write_csv(analysis_dir / f"{session_id}_model_fit_comparison.csv", [{"best_model": "linear", "best_aic": 0.0}])
    _write_csv(
        analysis_dir / "data_behavior_by_scope.csv",
        [
            {
                "scope": "Session",
                "aggregation_mode": "",
                "signal": "Expected pattern",
                "feature": "Response distribution",
                "message": "The final response yield is sufficient for exploratory review.",
                "evidence": "hit_rate=1.000",
            }
        ],
    )
    (analysis_dir / "exploratory_quality_summary.json").write_text(
        json.dumps(
            {
                "schema": "pps-exploratory-data-behavior.v1",
                "interpretation_note": "Exploratory data-behavior signals are not scientific conclusions.",
                "signal_labels": [
                    "Expected pattern",
                    "Mixed / ambiguous",
                    "Unusual pattern",
                    "Insufficient evidence",
                    "Technical caveat",
                ],
                "signal_counts": {"Expected pattern": 1},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (analysis_dir / f"{session_id}_sigmoid_fits.csv").write_text("empty\n", encoding="utf-8")
    _write_csv(
        analysis_dir / f"{session_id}_timing_qc.csv",
        [
            {
                "mouse_event_id": mouse_id,
                "response_marker_event_id": marker_id,
                "marker_minus_mouse_ms": 20.0,
                "block_number": 1,
                "block_label": block_label,
            }
            for mouse_id, marker_id, _trial_uid in mouse_marker_pairs
        ],
    )

    focus_report = {
        "schema": "pps-focus-mode-packaged-validation.v1",
        "completed": True,
        "exit_code": 0,
        "session_dir": str(session_dir),
        "session_manifest": str(session_dir / "session_manifest.json"),
        "validation_audio_realtime": True,
        "planned_tactile_cue_count": 2,
        "cursor_recenter_count": 2,
        "validation_mouse_clicks": [
            {
                "label": "participant_emulator_plan",
                "standard_tactile_cue_count": 2,
                "planned_miss_count": 0,
            },
            *[
                {
                    "action": "standard_click",
                    "trial_uid": trial_uid,
                    "actual_delay_ms": 150.0,
                    "backend": "pyautogui",
                    "label": "tactile_response_click",
                }
                for _mouse_id, _marker_id, trial_uid in mouse_marker_pairs
            ],
        ],
    }
    (artifact_dir / "focus_validation_report.json").write_text(json.dumps(focus_report), encoding="utf-8")
    (artifact_dir / "packaged_runner_process_launch.json").write_text(
        json.dumps(
            {
                "schema": "pps-packaged-real-asio-process-launch.v1",
                "pid": 123,
                "exe": "dist/PPSExperimentRunner/PPSExperimentRunner.exe",
                "session_manifest": str(session_dir / "session_manifest.json"),
                "mouse_backend": "pyautogui",
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "preparation_report.json").write_text(json.dumps({"schema": "pps-real-asio-ui-validation-prep.v1", "session_dir": str(session_dir)}), encoding="utf-8")

    image = Image.new("RGB", (12, 12), color=(8, 12, 18))
    image.putpixel((6, 6), (220, 240, 255))
    image.save(artifact_dir / "focus_screenshot.png")
    image.save(artifact_dir / "live_desktop_after_first_cues.png")

    report = auditor.audit_readiness(artifact_dir, output_dir=tmp_path / "readiness_audit")

    assert report["passed"]
    assert not report["full_study5_realtime_ready"]
    assert report["sections"]["lsl_xdf_trigger_logging"]["passed"]
    assert report["sections"]["local_recorder_audio_evidence"]["passed"]
    assert report["sections"]["analysis_outputs"]["passed"]
    assert report["scope"] == "one_block_study5_real_asio_rehearsal"
    assert (tmp_path / "readiness_audit" / "lsl_xdf_audio_reconciliation_report.json").exists()
    assert (tmp_path / "readiness_audit" / "response_marker_audio_evidence_validation" / "response_marker_loopback_report.json").exists()

    strict = auditor.audit_readiness(
        artifact_dir,
        output_dir=tmp_path / "readiness_audit_strict",
        require_full_study5=True,
        require_realtime=True,
    )

    assert not strict["passed"]
    assert strict["scope_summary"]["validation_audio_realtime"]
    assert any(item["name"] == "artifact_is_full_study5_when_required" and not item["passed"] for item in strict["criteria"])
    assert (tmp_path / "readiness_audit" / "protocol11_study5_readiness_audit.json").exists()


def test_study5_readiness_auditor_selection_audit_is_topup_and_extra_click_aware():
    auditor = _load_script("audit_protocol11_study5_readiness.py")

    planned = {
        "standard_click_count": 2,
        "topup_click_count": 2,
        "all_click_count": 4,
        "deliberate_miss_count": 1,
        "plan_declared_tactile_count": 3,
        "plan_declared_miss_count": 1,
    }
    analysis_ready_rows = [
        {"trial_uid": "T001", "hit": "True", "final_outcome_source": "original", "click_event_id": "101"},
        {"trial_uid": "T002", "hit": "True", "final_outcome_source": "original", "click_event_id": "102"},
        {
            "trial_uid": "T003",
            "hit": "True",
            "final_outcome_source": "topup_rescue",
            "click_event_id": "201",
            "topup_click_event_id": "201",
        },
    ]
    response_rows = [
        {"trial_uid": "T001", "hit": "True", "is_topup": "false", "click_event_id": "101"},
        {"trial_uid": "T002", "hit": "True", "is_topup": "false", "click_event_id": "102"},
        {"trial_uid": "T003", "hit": "False", "is_topup": "false", "click_event_id": ""},
        {"trial_uid": "TU001", "hit": "True", "is_topup": "true", "topup_role": "rescue", "click_event_id": "201"},
        {"trial_uid": "TU002", "hit": "True", "is_topup": "true", "topup_role": "filler", "click_event_id": "202"},
    ]

    audit = auditor._analysis_selection_audit(
        planned=planned,
        analysis_ready_rows=analysis_ready_rows,
        response_rows=response_rows,
        mouse_event_ids={"101", "102", "201", "202", "301"},
        scheduled_tactile_count=5,
    )

    assert audit["response_hits_match_all_planned_clicks"]
    assert audit["rows_match_declared_standard_tactile_count"]
    assert audit["original_hits_match_standard_plan"]
    assert audit["topup_rescues_match_miss_plan"]
    assert audit["final_hits_cover_standard_pool"]
    assert audit["selected_click_ids_are_unique_and_logged"]
    assert audit["extra_logged_mouse_click_count"] == 1
    assert audit["extra_logged_mouse_event_ids"] == ["301"]


def test_study5_readiness_auditor_rt_tolerance_is_backend_aware():
    auditor = _load_script("audit_protocol11_study5_readiness.py")

    focus_report = {
        "validation_mouse_clicks": [
            {"label": "participant_emulator_plan", "standard_tactile_cue_count": 20, "planned_miss_count": 0},
            *[
                {
                    "label": "tactile_response_click",
                    "action": "standard_click",
                    "trial_uid": f"T{i:03d}",
                    "planned_delay_ms": 250.0,
                    "actual_delay_ms": 250.0,
                    "backend": "pyautogui",
                }
                for i in range(19)
            ],
            {
                "label": "tactile_response_click",
                "action": "standard_click",
                "trial_uid": "T019",
                "planned_delay_ms": 250.0,
                "actual_delay_ms": 250.0,
                "backend": "pyautogui",
            },
        ],
    }
    rows = [{"trial_uid": f"T{i:03d}", "hit": "True", "rt_ms": "250.0"} for i in range(19)]
    rows.append({"trial_uid": "T019", "hit": "True", "rt_ms": "355.0"})

    os_audit = auditor._analysis_rt_audit(focus_report, rows, 25.0, 35.0, 125.0)
    assert os_audit["within_tolerance"]
    assert os_audit["os_distribution_within_tolerance"]
    assert not os_audit["strict_max_within_tolerance"]

    qtest_report = json.loads(json.dumps(focus_report))
    for record in qtest_report["validation_mouse_clicks"]:
        if record.get("action") == "standard_click":
            record["backend"] = "qtest"
    qtest_audit = auditor._analysis_rt_audit(qtest_report, rows, 25.0, 35.0, 125.0)
    assert not qtest_audit["within_tolerance"]


def test_response_marker_loopback_pairs_against_dominant_offset_when_first_candidate_is_wrong():
    comparator = _load_script("compare_response_marker_loopback.py")
    markers = [
        {"event_id": 1, "mouse_event_id": 11, "block_number": 1, "block_label": "Block 1", "sample_index": 1000},
        {"event_id": 2, "mouse_event_id": 12, "block_number": 1, "block_label": "Block 1", "sample_index": 2000},
        {"event_id": 3, "mouse_event_id": 13, "block_number": 1, "block_label": "Block 1", "sample_index": 3000},
    ]
    starts = [995, 1314, 2314, 3314]

    pairs = comparator._pair_markers(
        markers,
        starts,
        sample_rate=1000,
        search_pre_ms=10.0,
        search_post_ms=600.0,
    )

    assert [row["detected_sample_index"] for row in pairs] == [1314, 2314, 3314]
    assert [row["raw_offset_ms"] for row in pairs] == [314.0, 314.0, 314.0]


def test_full_realtime_harness_strict_mode_uses_hardware_standard_capture(tmp_path: Path, monkeypatch):
    harness = _load_script("run_full_realtime_participant_emulation.py")
    monkeypatch.delenv("PPS_FOCUS_VALIDATION_EXTERNAL_CLICK_PYTHON", raising=False)
    runner = tmp_path / "PPSExperimentRunner.exe"
    labrecorder_cli = tmp_path / "LabRecorderCLI.exe"
    labrecorder_cli.write_text("cli", encoding="utf-8")
    screenshot = tmp_path / "focus_screenshot.png"

    strict_args = harness.build_arg_parser().parse_args(
        [
            "--runner",
            str(runner),
            "--audio-mode",
            "hardware",
            "--audio-device-index",
            "28",
            "--strict-study5-readiness",
            "--participant-id",
            "P001",
            "--wired-loopback",
            "output4-tactile-proxy",
            "--external-labrecorder",
            "--labrecorder-cli",
            str(labrecorder_cli),
            "--labrecorder-stream-timeout-s",
            "14",
            "--labrecorder-startup-s",
            "1.5",
            "--labrecorder-stop-timeout-s",
            "11",
            "--companion-advertise-ip",
            "10.0.2.2",
            "--validation-windowed",
        ]
    )
    strict_command = harness._build_runner_command(strict_args, runner=runner, screenshot_path=screenshot)
    strict_env = harness._configure_validation_env(strict_args, output_dir=tmp_path, focus_report_path=tmp_path / "focus_validation_report.json")

    assert "--no-lsl" not in strict_command
    assert "--no-internal-xdf" not in strict_command
    assert "--no-backup-recording" not in strict_command
    assert "--validation-screenshot" in strict_command
    assert "--wired-loopback" in strict_command
    assert "output4-tactile-proxy" in strict_command
    assert "--external-labrecorder" in strict_command
    assert "--no-external-labrecorder" not in strict_command
    assert "--labrecorder-cli" in strict_command
    assert str(labrecorder_cli) in strict_command
    assert strict_command[strict_command.index("--companion-advertise-ip") + 1] == "10.0.2.2"
    assert "--validation-windowed" in strict_command
    assert strict_command[strict_command.index("--labrecorder-stream-timeout-s") + 1] == "14.0"
    assert strict_command[strict_command.index("--labrecorder-startup-s") + 1] == "1.5"
    assert strict_command[strict_command.index("--labrecorder-stop-timeout-s") + 1] == "11.0"
    assert harness._standard_capture_requested(strict_args)
    assert "PPS_FOCUS_VALIDATION_REALTIME_AUDIO" not in strict_env
    assert strict_env["PPS_FOCUS_VALIDATION_PARTICIPANT_EMULATOR"] == "1"
    assert strict_env["PPS_FOCUS_VALIDATION_PARTICIPANT_ID"] == "P001"
    assert strict_env["PPS_AUDIO_DEVICE_INDEX"] == "28"
    assert strict_env["PPS_PROTOCOL11_VALIDATION_LANE"] == "full-stack"
    assert strict_env["PPS_PROTOCOL11_WIRED_LOOPBACK"] == "output4-tactile-proxy"
    assert strict_env["PPS_FOCUS_VALIDATION_COMPANION_PAIRING_REPORT"] == str(tmp_path / "companion_pairing_report.json")
    assert strict_env["PPS_FOCUS_VALIDATION_EXTERNAL_CLICK_PYTHON"] == sys.executable

    legacy_args = harness.build_arg_parser().parse_args(["--runner", str(runner)])
    legacy_command = harness._build_runner_command(legacy_args, runner=runner, screenshot_path=screenshot)
    legacy_env = harness._configure_validation_env(legacy_args, output_dir=tmp_path, focus_report_path=tmp_path / "focus_validation_report.json")

    assert "--no-lsl" in legacy_command
    assert "--no-internal-xdf" in legacy_command
    assert "--no-backup-recording" in legacy_command
    assert "--no-external-labrecorder" in legacy_command
    assert "--wired-loopback" not in legacy_command
    assert legacy_env["PPS_PROTOCOL11_VALIDATION_LANE"] == "software-only"
    assert legacy_env["PPS_FOCUS_VALIDATION_EXTERNAL_CLICK_PYTHON"] == sys.executable

    qtest_env = harness._configure_validation_env(
        harness.build_arg_parser().parse_args(["--runner", str(runner), "--mouse-backend", "qtest"]),
        output_dir=tmp_path,
        focus_report_path=tmp_path / "focus_validation_report.json",
    )
    assert "PPS_FOCUS_VALIDATION_EXTERNAL_CLICK_PYTHON" not in qtest_env

    passive_args = harness.build_arg_parser().parse_args(
        [
            "--runner",
            str(runner),
            "--mouse-backend",
            "none",
            "--validation-windowed",
            "--timeout-s",
            "2",
            "--launch-via-environment-gate",
        ]
    )
    passive_env = harness._configure_validation_env(
        passive_args,
        output_dir=tmp_path,
        focus_report_path=tmp_path / "focus_validation_report.json",
    )
    assert passive_env["PPS_FOCUS_VALIDATION_MOUSE_BACKEND"] == "none"
    assert passive_env["PPS_FOCUS_VALIDATION_AUTO_CLOSE_MS"] == "2000"
    assert passive_env["PPS_FOCUS_VALIDATION_DISABLE_MOUSE_CAPTURE"] == "1"
    assert passive_env["PPS_FOCUS_VALIDATION_DISABLE_CURSOR_RECENTER"] == "1"
    assert passive_env["PPS_FOCUS_VALIDATION_ENABLE_SYNTHETIC_CLICK_SHORTCUT"] == "1"
    assert passive_env["PPS_FOCUS_VALIDATION_DISPLAY"] == "left"
    assert passive_env["PPS_FOCUS_VALIDATION_RUNNER_WIDTH"] == "820"
    assert "PPS_FOCUS_VALIDATION_PARTICIPANT_EMULATOR" not in passive_env
    assert "PPS_FOCUS_VALIDATION_EXTERNAL_CLICK_PYTHON" not in passive_env
    assert "PPS_FOCUS_VALIDATION_LAUNCHER_AUTO_CLICK" not in passive_env

    source_args = harness.build_arg_parser().parse_args(
        [
            "--runner-mode",
            "source",
            "--audio-mode",
            "hardware",
            "--standard-capture",
        ]
    )
    source_command = harness._build_runner_command(source_args, runner=runner, screenshot_path=screenshot)
    source_env = harness._configure_validation_env(source_args, output_dir=tmp_path, focus_report_path=tmp_path / "focus_validation_report.json")

    assert source_command[0] == sys.executable
    assert source_command[1].replace("\\", "/").endswith(
        "apps/runner/launchers/focus_runner_entry.py"
    )
    assert "--no-lsl" not in source_command
    assert source_env["SD_ENABLE_ASIO"] == "1"
    assert str(REPO_ROOT / "packages" / "pps-runtime" / "src") in source_env["PYTHONPATH"]
    assert source_env["PPS_PROTOCOL11_VALIDATION_LANE"] == "full-stack"

    with pytest.raises(ValueError, match="requires --audio-mode hardware"):
        harness.main(["--runner", str(runner), "--strict-study5-readiness"])
    with pytest.raises(ValueError, match="Full-stack validation requires --audio-mode hardware"):
        harness.main(["--runner", str(runner), "--validation-lane", "full-stack"])
    with pytest.raises(ValueError, match="requires an OS mouse backend"):
        harness.main(["--runner", str(runner), "--validation-lane", "full-stack", "--audio-mode", "hardware", "--mouse-backend", "qtest"])
    with pytest.raises(ValueError, match="cannot disable LSL, internal XDF, or local audio-evidence"):
        harness.main(["--runner", str(runner), "--validation-lane", "full-stack", "--audio-mode", "hardware", "--no-backup-recording"])
    with pytest.raises(ValueError, match="Software-only validation requires --audio-mode validation-realtime"):
        harness.main(["--runner", str(runner), "--validation-lane", "software-only", "--audio-mode", "hardware"])
    with pytest.raises(ValueError, match="External LabRecorder validation requires live LSL outlets"):
        harness.main(["--runner", str(runner), "--external-labrecorder", "--no-lsl"])


def test_full_realtime_harness_resolves_manifest_topup_and_analysis_outputs(tmp_path: Path):
    harness = _load_script("run_full_realtime_participant_emulation.py")
    session_dir = tmp_path / "P001_20260102_030405"
    session_dir.mkdir()
    runner_log_dir = tmp_path / "Experiment_context_folder_DO_NOT_DELETE" / "runner_logs" / session_dir.name
    topup_dir = runner_log_dir / "topup"
    topup_dir.mkdir(parents=True)
    analysis_dir = tmp_path / "Data_Analytics" / session_dir.name
    analysis_dir.mkdir(parents=True)
    events_csv = tmp_path / "Experiment_context_folder_DO_NOT_DELETE" / "verbose_events" / session_dir.name / "events.csv"
    events_csv.parent.mkdir(parents=True)

    _write_csv(events_csv, [{"event_type": "block_end"} for _ in range(12)])
    _write_csv(topup_dir / "topup_block_part1_manifest.csv", [{"Trial_UID": "TU001", "Topup_Role": "rescue"}])
    (topup_dir / "topup_ledger.json").write_text(json.dumps({"summary": {"rescue": 1}}), encoding="utf-8")
    _write_csv(
        analysis_dir / f"{session_dir.name}_final_trial_outcomes.csv",
        [{"trial_uid": "T004", "hit": "True", "final_outcome_source": "topup_rescue"}],
    )
    manifest_path = runner_log_dir / "session_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "blocks": [{"duration_s": 1.0} for _ in range(12)],
                "outputs": {
                    "analysis_dir": str(analysis_dir),
                    "topup_ledger_json": str(topup_dir / "topup_ledger.json"),
                    "topup_block_manifest_csv": str(topup_dir / "topup_block_part1_manifest.csv"),
                },
            }
        ),
        encoding="utf-8",
    )
    focus_report = tmp_path / "focus_validation_report.json"
    focus_report.write_text(
        json.dumps(
            {
                "completed": True,
                "session_dir": str(session_dir),
                "session_manifest": str(manifest_path),
                "events_csv": str(events_csv),
                "planned_tactile_cue_count": 4,
                "cursor_recenter_count": 4,
                "validation_audio_realtime": True,
                "validation_topup_approvals": [{"approved": True}],
                "validation_mouse_clicks": [
                    {"label": "participant_emulator_plan", "standard_tactile_cue_count": 4, "planned_miss_count": 1},
                    {"label": "tactile_response_plan", "action": "deliberate_miss", "trial_uid": "T004"},
                    {"label": "tactile_response_click", "action": "standard_click", "trial_uid": "T001", "actual_delay_ms": 200},
                    {"label": "tactile_response_click", "action": "standard_click", "trial_uid": "T002", "actual_delay_ms": 300},
                    {"label": "tactile_response_click", "action": "standard_click", "trial_uid": "T003", "actual_delay_ms": 400},
                    {"label": "tactile_response_click", "action": "topup_click", "trial_uid": "T004", "actual_delay_ms": 250},
                ],
            }
        ),
        encoding="utf-8",
    )

    evaluation, failures = harness._evaluate_focus_report(
        focus_report,
        process_wall_s=20.0,
        exit_code=0,
        audio_mode="validation-realtime",
        runner_mode="packaged",
        validation_lane=harness.VALIDATION_LANE_SOFTWARE_ONLY,
    )

    assert failures == []
    assert evaluation["topup_rescue_row_count"] == 1
    assert evaluation["final_topup_rescued_hit_count"] == 1
    assert evaluation["analysis_dir"] == str(analysis_dir)
    assert evaluation["topup_dir"] == str(topup_dir)


def test_desktop_full_mock_rehearsal_delegates_to_full_stack_harness(tmp_path: Path, monkeypatch):
    rehearsal = _load_script("run_desktop_full_mock_rehearsal.py")
    parent = tmp_path / "Desktop"
    parent.mkdir()
    runner = tmp_path / "PPSExperimentRunner.exe"
    runner.write_text("exe", encoding="utf-8")
    environment_root = parent / "mock_20260620"
    captured: dict[str, object] = {}

    def fake_create_environment(args):
        environment_root.mkdir(parents=True)
        return {"environment_root": str(environment_root), "participant_id": args.participant_id}

    def fake_emulator_main(argv):
        captured["argv"] = list(argv)
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        session_dir = environment_root / "P050_20260620_121400"
        session_dir.mkdir(parents=True)
        manifest = session_dir / "session_manifest.json"
        manifest.write_text(json.dumps({"outputs": {}}), encoding="utf-8")
        (output_dir / "focus_validation_report.json").write_text(
            json.dumps(
                {
                    "session_dir": str(session_dir),
                    "session_manifest": str(manifest),
                    "events_csv": str(output_dir / "events.csv"),
                    "completed": True,
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "full_realtime_participant_emulation_report.json").write_text(
            json.dumps({"passed": True}),
            encoding="utf-8",
        )
        return 0

    monkeypatch.setattr(rehearsal, "_create_rehearsal_environment", fake_create_environment)
    monkeypatch.setattr(rehearsal.emulator, "main", fake_emulator_main)
    monkeypatch.setattr(rehearsal, "output_validation_reports_dir", lambda root: Path(root) / "v")
    args = rehearsal.build_arg_parser().parse_args(
        [
            "--desktop-output-parent",
            str(parent),
            "--runner",
            str(runner),
            "--skip-audio-preflight",
        ]
    )

    report = rehearsal.run_rehearsal(args)

    argv = captured["argv"]
    assert report["passed"]
    assert report["environment_root"] == str(environment_root.resolve())
    assert "--wired-loopback" in argv
    assert argv[argv.index("--wired-loopback") + 1] == "output4-tactile-proxy"
    assert "--strict-study5-readiness" in argv
    assert argv[argv.index("--participant-id") + 1] == "P050"
    assert Path(report["validation_dir"]).parent.name == "v"


def test_desktop_full_mock_rehearsal_uses_runner_owned_labrecorder(tmp_path: Path, monkeypatch):
    rehearsal = _load_script("run_desktop_full_mock_rehearsal.py")
    parent = tmp_path / "Desktop"
    parent.mkdir()
    runner = tmp_path / "PPSExperimentRunner.exe"
    runner.write_text("exe", encoding="utf-8")
    labrecorder_cli = tmp_path / "LabRecorderCLI.exe"
    labrecorder_cli.write_text("cli", encoding="utf-8")
    environment_root = parent / "mock_20260620"
    captured: dict[str, object] = {}

    def fake_create_environment(args):
        environment_root.mkdir(parents=True)
        return {"environment_root": str(environment_root), "participant_id": args.participant_id}

    def fake_emulator_main(argv):
        captured["argv"] = list(argv)
        output_dir = Path(argv[argv.index("--output-dir") + 1])
        session_dir = environment_root / "P050_20260620_121400"
        session_dir.mkdir(parents=True)
        _write_wired_loopback_evidence(session_dir / "block_01_wired_loopback_input4.wav", healthy=True)
        context_dir = environment_root / "Experiment_context_folder_DO_NOT_DELETE"
        verbose_dir = context_dir / "verbose_events" / session_dir.name
        runner_log_dir = context_dir / "runner_logs" / session_dir.name
        verbose_dir.mkdir(parents=True)
        runner_log_dir.mkdir(parents=True)
        _write_csv(
            verbose_dir / "events.csv",
            [
                {
                    "event_id": "1",
                    "event_type": "block_start",
                    "payload_json": json.dumps({"block_number": 1}),
                },
                {
                    "event_id": "2",
                    "event_type": "wired_loopback_start",
                    "payload_json": json.dumps(
                        {
                            "block_number": 1,
                            "started": True,
                            "path": str(session_dir / "block_01_wired_loopback_input4.wav"),
                            "message": "",
                        }
                    ),
                },
            ],
        )
        lsl_markers_csv = verbose_dir / "lsl_markers.csv"
        marker_rows = [
            {
                "event_id": "1",
                "event_type": "session_start",
                "event_code": "1",
                "trigger_key": "control:session_start",
                "session_id": session_dir.name,
                "participant_id": "P050",
                "block_index": "",
                "trial_uid": "",
                "sample_index": "",
                "timestamp_quality": "software_log",
                "payload_json": "{}",
                "lsl_timestamp": "10.000000000",
                "pushed_to_lsl": "True",
            },
            {
                "event_id": "2",
                "event_type": "block_start",
                "event_code": "10",
                "trigger_key": "control:block_start",
                "session_id": session_dir.name,
                "participant_id": "P050",
                "block_index": "1",
                "trial_uid": "",
                "sample_index": "",
                "timestamp_quality": "software_log",
                "payload_json": "{}",
                "lsl_timestamp": "10.100000000",
                "pushed_to_lsl": "True",
            },
        ]
        _write_csv(lsl_markers_csv, marker_rows)
        manifest = session_dir / "session_manifest.json"
        manifest.write_text(json.dumps({"outputs": {"lsl_markers_csv": str(lsl_markers_csv)}}), encoding="utf-8")
        xdf_path = session_dir / f"{session_dir.name}_external_labrecorder.xdf"
        xdf_path.write_bytes(b"xdf")
        stdout_path = runner_log_dir / "external_labrecorder_stdout.txt"
        stderr_path = runner_log_dir / "external_labrecorder_stderr.txt"
        stdout_path.write_text("stopped\n", encoding="utf-8")
        stderr_path.write_text("", encoding="utf-8")
        runner_report = runner_log_dir / "external_labrecorder_capture_report.json"
        runner_report.write_text(
            json.dumps(
                {
                    "start": {"command": [str(labrecorder_cli), str(xdf_path)], "labrecorder_cli": str(labrecorder_cli)},
                    "stop": {
                        "returncode": 0,
                        "stdout_path": str(stdout_path),
                        "stderr_path": str(stderr_path),
                        "xdf_path": str(xdf_path),
                    },
                }
            ),
            encoding="utf-8",
        )
        (output_dir / "focus_validation_report.json").write_text(
            json.dumps(
                {
                    "session_dir": str(session_dir),
                    "session_manifest": str(manifest),
                    "events_csv": str(verbose_dir / "events.csv"),
                    "completed": True,
                    "analysis_outputs": {
                        "external_labrecorder_xdf": str(xdf_path),
                        "external_labrecorder_report": str(runner_report),
                        "external_labrecorder_stdout": str(stdout_path),
                        "external_labrecorder_stderr": str(stderr_path),
                    },
                }
            ),
            encoding="utf-8",
        )
        criteria = [
            ("lsl_xdf_trigger_logging", "events_xdf_loadable_and_complete"),
            ("lsl_xdf_trigger_logging", "lsl_marker_xdf_dual_streams_complete"),
            ("lsl_xdf_trigger_logging", "events_and_lsl_marker_csvs_match"),
            ("local_recorder_audio_evidence", "audio_evidence_files_cover_played_blocks"),
            ("local_recorder_audio_evidence", "lsl_xdf_audio_reconciliation_passed"),
            ("analysis_outputs", "emulated_rt_values_match_plan_tolerance"),
        ]
        (output_dir / "full_realtime_participant_emulation_report.json").write_text(
            json.dumps(
                {
                    "passed": True,
                    "validation_lane": "full-stack",
                    "strict_study5_readiness_requested": True,
                    "evaluation": {"event_counts": {"block_start": 1, "mouse_click": 1, "response_marker_start": 1}},
                    "readiness_audit": {
                        "passed": True,
                        "output_dir": str(output_dir / "protocol11_study5_readiness_audit"),
                        "expected_event_counts": {"block_start": 1},
                        "event_counts": {"block_start": 1, "mouse_click": 1, "response_marker_start": 1},
                        "audio_evidence": {"record_count": 1},
                        "sections": {"response_marker_path": {"passed": True}},
                        "criteria": [
                            {"section": section, "name": name, "passed": True}
                            for section, name in criteria
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        return 0

    rich_rows = [
        {
            "event_id": "1",
            "event_type": "session_start",
            "event_code": "1",
            "trigger_key": "control:session_start",
            "session_id": "P050_20260620_121400",
            "participant_id": "P050",
            "block_index": "",
            "trial_uid": "",
            "sample_index": "",
            "timestamp_quality": "software_log",
            "payload_json": "{}",
            "sample_lsl_timestamp": "10.000000000",
        },
        {
            "event_id": "2",
            "event_type": "block_start",
            "event_code": "10",
            "trigger_key": "control:block_start",
            "session_id": "P050_20260620_121400",
            "participant_id": "P050",
            "block_index": "1",
            "trial_uid": "",
            "sample_index": "",
            "timestamp_quality": "software_log",
            "payload_json": "{}",
            "sample_lsl_timestamp": "10.100000000",
        },
    ]
    numeric_rows = [
        {"event_code": "1", "sample_lsl_timestamp": "10.000000000"},
        {"event_code": "10", "sample_lsl_timestamp": "10.100000000"},
    ]
    monkeypatch.setattr(rehearsal, "_find_labrecorder_cli", lambda _explicit=None: labrecorder_cli)
    monkeypatch.setattr(rehearsal, "_create_rehearsal_environment", fake_create_environment)
    monkeypatch.setattr(rehearsal.emulator, "main", fake_emulator_main)
    monkeypatch.setattr(rehearsal, "_load_xdf_streams", lambda _path: (rich_rows, numeric_rows, {}))
    monkeypatch.setattr(rehearsal, "output_validation_reports_dir", lambda root: Path(root) / "v")
    args = rehearsal.build_arg_parser().parse_args(
        [
            "--desktop-output-parent",
            str(parent),
            "--runner",
            str(runner),
            "--skip-audio-preflight",
            "--external-labrecorder",
            "--labrecorder-cli",
            str(labrecorder_cli),
        ]
    )

    report = rehearsal.run_rehearsal(args)

    argv = captured["argv"]
    assert report["passed"]
    assert "--external-labrecorder" in argv
    assert "--labrecorder-cli" in argv
    assert str(labrecorder_cli) in argv
    assert report["external_labrecorder"]["checked"]
    assert report["external_labrecorder"]["passed"]
    assert report["cross_stream_reconciliation"]["passed"]
    validation_dir = Path(report["validation_dir"])
    assert (validation_dir / "external_labrecorder_reconciliation" / "external_labrecorder_reconciliation_report.json").is_file()
    assert (validation_dir / "cross_stream_reconciliation" / "cross_stream_reconciliation_report.json").is_file()


def test_desktop_full_mock_rehearsal_rejects_empty_wired_loopback_sidecars(tmp_path: Path):
    rehearsal = _load_script("run_desktop_full_mock_rehearsal.py")
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    wired_wav = session_dir / "block_01_wired_loopback_input4.wav"
    _write_wired_loopback_evidence(wired_wav, healthy=False)
    events_csv = tmp_path / "events.csv"
    _write_csv(
        events_csv,
        [
            {
                "event_id": "1",
                "event_type": "block_start",
                "payload_json": json.dumps({"block_number": 1}),
            },
            {
                "event_id": "2",
                "event_type": "wired_loopback_start",
                "payload_json": json.dumps(
                    {
                        "block_number": 1,
                        "started": False,
                        "path": str(wired_wav),
                        "message": "persistent_output_stream_not_duplex_for_wired_loopback",
                    }
                ),
            },
        ],
    )
    lsl_markers_csv = tmp_path / "lsl_markers.csv"
    _write_csv(lsl_markers_csv, [{"event_id": "1", "event_type": "block_start", "payload_json": "{}"}])
    manifest = session_dir / "session_manifest.json"
    manifest.write_text(json.dumps({"outputs": {"lsl_markers_csv": str(lsl_markers_csv)}}), encoding="utf-8")
    (validation_dir / "focus_validation_report.json").write_text(
        json.dumps({"session_dir": str(session_dir), "session_manifest": str(manifest), "events_csv": str(events_csv)}),
        encoding="utf-8",
    )
    readiness = {
        "passed": True,
        "expected_event_counts": {"block_start": 1},
        "event_counts": {"block_start": 1},
        "audio_evidence": {"record_count": 1},
        "sections": {"response_marker_path": {"passed": True}},
        "criteria": [
            {"section": "lsl_xdf_trigger_logging", "name": "events_xdf_loadable_and_complete", "passed": True},
            {"section": "lsl_xdf_trigger_logging", "name": "lsl_marker_xdf_dual_streams_complete", "passed": True},
            {"section": "lsl_xdf_trigger_logging", "name": "events_and_lsl_marker_csvs_match", "passed": True},
            {"section": "local_recorder_audio_evidence", "name": "audio_evidence_files_cover_played_blocks", "passed": True},
            {"section": "local_recorder_audio_evidence", "name": "lsl_xdf_audio_reconciliation_passed", "passed": True},
            {"section": "analysis_outputs", "name": "emulated_rt_values_match_plan_tolerance", "passed": True},
        ],
    }

    report = rehearsal.cross_stream_reconciliation_report(
        validation_dir=validation_dir,
        harness_report={
            "passed": True,
            "validation_lane": "full-stack",
            "strict_study5_readiness_requested": True,
            "readiness_audit": readiness,
        },
        focus_report={},
        external_report={"checked": False, "passed": True},
        wired_loopback_requested=True,
    )

    assert not report["passed"]
    assert not report["criteria"]["wired_loopback_started_for_played_blocks"]
    assert not report["criteria"]["wired_loopback_sidecars_nonempty_clean"]
    assert not report["criteria"]["wired_loopback_input_signal_present"]
    assert report["wired_loopback_events"]["failures"][0]["message"] == "persistent_output_stream_not_duplex_for_wired_loopback"


def test_desktop_full_mock_rehearsal_preflight_enables_asio(monkeypatch):
    rehearsal = _load_script("run_desktop_full_mock_rehearsal.py")

    class FakeSoundDevice:
        @staticmethod
        def query_hostapis():
            return [{"name": "ASIO"}]

        @staticmethod
        def query_devices():
            return [
                {
                    "name": "Komplete Audio ASIO Driver",
                    "hostapi": 0,
                    "max_input_channels": 6,
                    "max_output_channels": 6,
                }
            ]

    monkeypatch.delenv("SD_ENABLE_ASIO", raising=False)
    monkeypatch.setitem(sys.modules, "sounddevice", FakeSoundDevice)

    report = rehearsal._audio_route_preflight()

    assert report["komplete_asio_4x4_ready"]
    assert report["candidates"][0]["hostapi"] == "ASIO"
    assert os.environ["SD_ENABLE_ASIO"] == "1"


def test_desktop_full_mock_rehearsal_reconciles_external_labrecorder_xdf(tmp_path: Path, monkeypatch):
    rehearsal = _load_script("run_desktop_full_mock_rehearsal.py")
    validation_dir = tmp_path / "validation"
    validation_dir.mkdir()
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    lsl_markers_csv = tmp_path / "lsl_markers.csv"
    marker_rows = [
        {
            "event_id": "1",
            "event_type": "session_start",
            "event_code": "1",
            "trigger_key": "control:session_start",
            "session_id": "S",
            "participant_id": "P050",
            "block_index": "",
            "trial_uid": "",
            "sample_index": "",
            "timestamp_quality": "software_log",
            "payload_json": "{}",
            "lsl_timestamp": "10.000000000",
            "pushed_to_lsl": "True",
        },
        {
            "event_id": "2",
            "event_type": "block_start",
            "event_code": "10",
            "trigger_key": "control:block_start",
            "session_id": "S",
            "participant_id": "P050",
            "block_index": "1",
            "trial_uid": "",
            "sample_index": "",
            "timestamp_quality": "software_log",
            "payload_json": "{}",
            "lsl_timestamp": "10.100000000",
            "pushed_to_lsl": "True",
        },
    ]
    _write_csv(lsl_markers_csv, marker_rows)
    manifest = session_dir / "session_manifest.json"
    manifest.write_text(json.dumps({"outputs": {"lsl_markers_csv": str(lsl_markers_csv)}}), encoding="utf-8")
    (validation_dir / "focus_validation_report.json").write_text(
        json.dumps({"session_dir": str(session_dir), "session_manifest": str(manifest), "events_csv": str(tmp_path / "events.csv")}),
        encoding="utf-8",
    )
    rich_rows = [
        {**marker_rows[0], "sample_lsl_timestamp": "10.000000000"},
        {**marker_rows[1], "sample_lsl_timestamp": "10.100000000"},
    ]
    numeric_rows = [
        {"event_code": "1", "sample_lsl_timestamp": "10.000000000"},
        {"event_code": "10", "sample_lsl_timestamp": "10.100000000"},
    ]
    xdf_path = validation_dir / "session_external_labrecorder.xdf"
    xdf_path.write_bytes(b"xdf")
    monkeypatch.setattr(rehearsal, "_load_xdf_streams", lambda _path: (rich_rows, numeric_rows, {}))

    report = rehearsal.reconcile_external_labrecorder_xdf(
        validation_dir=validation_dir,
        xdf_path=xdf_path,
        labrecorder_cli=tmp_path / "LabRecorderCLI.exe",
        labrecorder_command=["LabRecorderCLI.exe", str(xdf_path)],
        labrecorder_returncode=0,
        stdout_path=tmp_path / "stdout.txt",
        stderr_path=tmp_path / "stderr.txt",
    )

    assert report["passed"]
    assert report["comparison"]["rich_xdf_sample_count"] == 2
    assert report["block_indices_observed"] == ["1"]
    assert (validation_dir / "external_labrecorder_reconciliation" / "external_labrecorder_rich_xdf_samples.csv").is_file()


def test_readiness_audit_accepts_declared_output4_tactile_mirror():
    auditor = _load_script("audit_protocol11_study5_readiness.py")

    silent_output4 = {
        "scan": {"max_abs_by_channel": [0.2, 0.1, 0.3, 0.0]},
        "sidecar": {"duplicate_tactile_output_channel_1based": ""},
    }
    mirrored_output4 = {
        "scan": {"max_abs_by_channel": [0.2, 0.1, 0.3, 0.3]},
        "sidecar": {"duplicate_tactile_output_channel_1based": 4},
    }
    unexpected_output4_signal = {
        "scan": {"max_abs_by_channel": [0.2, 0.1, 0.3, 0.3]},
        "sidecar": {"duplicate_tactile_output_channel_1based": ""},
    }

    assert auditor._audio_signal_shape_ok(silent_output4)
    assert auditor._audio_signal_shape_ok(mirrored_output4)
    assert not auditor._audio_signal_shape_ok(unexpected_output4_signal)


def test_one_block_actual_condition_progress_csv_accepts_variable_payloads(tmp_path: Path):
    harness = _load_script("run_one_block_actual_condition_validation.py")
    progress_csv = tmp_path / "runner_progress_samples.csv"

    harness._write_progress_csv(
        progress_csv,
        [
            {"monotonic_time": 1.0, "block_index": 1, "block_label": "Block 01"},
            {"monotonic_time": 2.0, "elapsed_s": 0.25, "duration_s": 1.0, "session_id": "P001_test"},
        ],
    )

    rows = list(csv.DictReader(progress_csv.open(newline="", encoding="utf-8")))
    assert len(rows) == 2
    assert "elapsed_s" in rows[0]
    assert rows[1]["session_id"] == "P001_test"


def test_topup_missed_trial_stress_rescues_intentional_misses(tmp_path: Path):
    stress = _load_script("run_topup_missed_trial_stress.py")

    report = stress.run_stress(
        output_dir=tmp_path,
        participant_id="P001",
        scenarios=["row_imbalanced_misses"],
        block_count=1,
        trials_per_block=4,
        sample_rate=44100,
        # Keep adjacent response windows from overlapping so clicks intended
        # for later trials cannot rescue deliberate earlier misses.
        trial_duration_s=1.25,
        blocksize=256,
        enable_lsl=False,
        response_marker_delay_ms=8.0,
    )

    assert report["passed"]
    scenario = report["scenario_reports"][0]
    assert scenario["topup_played_after_standard"]
    assert scenario["expected_missed_count"] == 2
    assert scenario["topup_rescue_count"] == 2
    assert scenario["topup_filler_count"] >= 1
    assert scenario["final_rescued_count"] == 2
    assert scenario["checks"]["rescue_manifest_matches_misses"]
    assert Path(scenario["ledger_csv"]).exists()
    assert Path(scenario["topup_manifest_csv"]).exists()
    assert Path(scenario["final_trial_outcomes_csv"]).exists()


def _write_one_block_actual_condition_fixture(tmp_path: Path, *, suspicious: bool = False) -> Path:
    session_dir = tmp_path / "P001_20260612_180000"
    block_dir = session_dir / "blocks"
    analysis_dir = session_dir / "analysis"
    recordings_dir = session_dir / "recordings"
    block_dir.mkdir(parents=True)
    analysis_dir.mkdir()
    recordings_dir.mkdir()

    sample_rate = 1000
    wav = np.zeros((1500, 3), dtype=np.float32)
    wav[100:120, 0] = 0.01
    wav[150:170, 2] = 0.01
    block_wav = block_dir / "Block_01_from_study5.csv.wav"
    sf.write(block_wav, wav, sample_rate)
    sf.write(recordings_dir / "Block_01_loopback.wav", wav, sample_rate)

    block_csv = block_dir / "Block_01_from_study5.csv"
    noise_type = "validation_rect_pulse" if suspicious else "looming_noise"
    source_label = "Validation pulse | SOA 50 ms" if suspicious else "Study 5 looming source | SOA 50 ms"
    _write_csv(
        block_csv,
        [
            {
                "Trial_UID": "P001_B01_T001",
                "Trial_Number": 1,
                "Trial_Type": "Audio-Tactile",
                "SOA_ms": 50,
                "Noise_Type": noise_type,
                "Respiratory_Phase": "Inhale",
                "Sequence_Labels": source_label,
            },
            {
                "Trial_UID": "P001_B01_T002",
                "Trial_Number": 2,
                "Trial_Type": "Audio-Tactile",
                "SOA_ms": 150,
                "Noise_Type": noise_type,
                "Respiratory_Phase": "Exhale",
                "Sequence_Labels": source_label,
            },
            {
                "Trial_UID": "P001_B01_T003",
                "Trial_Number": 3,
                "Trial_Type": "Catch",
                "SOA_ms": 0,
                "Noise_Type": noise_type,
                "Respiratory_Phase": "Inhale",
                "Sequence_Labels": source_label,
            },
        ],
    )

    source_manifest = (
        tmp_path / "segment_fixture" / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
        if suspicious
        else tmp_path / "dashboard_project" / "6_experiment_run_setup" / "experiment_run_setup_manifest.json"
    )
    source_manifest.parent.mkdir(parents=True)
    source_manifest.write_text(json.dumps({"schema": "pps-experiment-run-setup.v1"}), encoding="utf-8")

    manifest = {
        "schema": "pps-run-session.v1",
        "participant_id": "P001",
        "session_id": "P001_20260612_180000",
        "execution_mode": "participant_block_wavs",
        "source_run_setup_manifest_path": str(source_manifest),
        "blocks": [
            {
                "index": 1,
                "label": "Study 5 Block 01",
                "manifest_path": str(block_csv),
                "wav_path": str(block_wav),
                "trial_count": 3,
                "duration_s": 1.5,
                "metadata": {
                    "execution_mode": "participant_block_wavs",
                    "source_block_csv_path": str(block_csv),
                    "sample_rate_hz": sample_rate,
                    "channels": 3,
                },
            }
        ],
        "outputs": {
            "events_csv": str(session_dir / "events.csv"),
            "events_xdf": str(session_dir / "events.xdf"),
            "lsl_markers_csv": str(session_dir / "lsl_markers.csv"),
            "trigger_dictionary_json": str(session_dir / "trigger_dictionary.json"),
            "analysis_dir": str(analysis_dir),
        },
    }
    (session_dir / "session_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (session_dir / "trigger_dictionary.json").write_text(json.dumps({"trial:01": 1000}), encoding="utf-8")

    events = []
    event_id = 1

    def add(event_type: str, mono: float, payload: dict[str, object] | None = None) -> int:
        nonlocal event_id
        payload = dict(payload or {})
        events.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "unix_time": 1000.0 + mono,
                "monotonic_time": mono,
                "payload_json": json.dumps(payload),
            }
        )
        event_id += 1
        return event_id - 1

    add("session_start", 0.000)
    add("block_start", 0.001)
    add("recording_start", 0.002)
    for trial_index, onset in enumerate([0.100, 0.600], start=1):
        base = {
            "timestamp_quality": "dac_time_sample_exact",
            "trial_number": trial_index,
            "trial_uid": f"P001_B01_T{trial_index:03d}",
            "sample_index": int(onset * sample_rate),
        }
        add("trial_start", onset, base)
        add("looming_onset", onset + 0.050, base)
        add("tactile_onset", onset + 0.100, base)
        add("response_window_onset", onset + 0.100, base)
        mouse_id = add("mouse_click", onset + 0.300, {"in_target": True, "during_playback": True})
        add("response_marker_start", onset + 0.308, {**base, "mouse_event_id": mouse_id})
        add("trial_end", onset + 0.400, base)
    catch_base = {
        "timestamp_quality": "dac_time_sample_exact",
        "trial_number": 3,
        "trial_uid": "P001_B01_T003",
        "sample_index": 1100,
    }
    add("trial_start", 1.100, catch_base)
    add("looming_onset", 1.150, catch_base)
    add("response_window_onset", 1.150, catch_base)
    add("trial_end", 1.400, catch_base)
    add("recording_end", 1.100)
    add("block_end", 1.101)
    add("session_end", 1.102)
    _write_csv(session_dir / "events.csv", events)
    _write_csv(session_dir / "lsl_markers.csv", [{"event_id": row["event_id"], "event_type": row["event_type"]} for row in events])
    _write_csv(
        analysis_dir / "P001_20260612_180000_analysis_ready_trials.csv",
        [
            {"trial_number": 1, "hit": True, "rt_ms": 200.0, "soa_ms": 50},
            {"trial_number": 2, "hit": True, "rt_ms": 200.0, "soa_ms": 150},
        ],
    )
    _write_csv(
        analysis_dir / "P001_20260612_180000_timing_qc.csv",
        [
            {"mouse_event_id": 9, "response_marker_event_id": 10, "marker_minus_mouse_ms": 8.0},
            {"mouse_event_id": 16, "response_marker_event_id": 17, "marker_minus_mouse_ms": 8.0},
        ],
    )
    return session_dir


def test_actual_condition_one_block_validator_accepts_real_looking_session(tmp_path: Path):
    validator = _load_script("validate_one_block_actual_condition_run.py")
    session_dir = _write_one_block_actual_condition_fixture(tmp_path)

    report = validator.validate_session(session_dir, require_xdf=False)

    assert report["passed"]
    assert report["evidence_level"] == "actual_experimental_condition_one_block"
    assert report["trial_count"] == 3
    assert report["analysis_ready_trial_count"] == 2
    assert report["expected_event_type_counts"]["looming_onset"] == 3
    assert report["expected_event_type_counts"]["tactile_onset"] == 2
    assert report["event_type_counts"]["tactile_onset"] == 2
    assert (session_dir / "analysis" / "actual_condition_validation" / "one_block_actual_condition_validation.json").exists()


def test_actual_condition_one_block_validator_rejects_dummy_fixture_sources(tmp_path: Path):
    validator = _load_script("validate_one_block_actual_condition_run.py")
    session_dir = _write_one_block_actual_condition_fixture(tmp_path, suspicious=True)

    report = validator.validate_session(session_dir, require_xdf=False)

    actual_source = next(row for row in report["criteria"] if row["key"] == "actual_experiment_sources")
    assert not report["passed"]
    assert not actual_source["passed"]
    assert report["suspicious_non_actual_sources"]


def test_response_marker_loopback_comparison_recovers_physical_marker_trace(tmp_path: Path):
    compare = _load_script("compare_response_marker_loopback.py")
    sample_rate = 1000
    offset_samples = 33
    marker_samples = [100, 250, 410, 590, 760]
    events_csv = tmp_path / "events.csv"
    recording = tmp_path / "Block_01_loopback.wav"

    rows = []
    event_id = 1
    for index, sample in enumerate(marker_samples, start=1):
        rows.append(
            {
                "event_id": event_id,
                "event_type": "response_marker_start",
                "unix_time": f"{index:.9f}",
                "monotonic_time": f"{index:.9f}",
                "payload_json": json.dumps(
                    {
                        "sample_index": sample,
                        "mouse_event_id": event_id - 1,
                        "block_number": 1,
                        "timestamp_quality": "dac_time_sample_exact",
                        "marker_gain": 0.05,
                    }
                ),
            }
        )
        event_id += 1
    _write_csv(events_csv, rows)

    capture = np.zeros((1000, 3), dtype=np.float32)
    for sample in marker_samples:
        start = sample + offset_samples
        capture[start : start + 20, 2] = 0.05
    sf.write(recording, capture, sample_rate)

    report = compare.compare_loopback(
        events_csv=events_csv,
        recordings=[recording],
        output_dir=tmp_path / "comparison",
        tactile_channel_1based=3,
        search_pre_ms=5.0,
        search_post_ms=80.0,
        min_peak=0.005,
    )

    assert report["passed"]
    assert report["expected_marker_count"] == 5
    assert report["detected_marker_count"] == 5
    assert report["offset_ms"]["median_ms"] == pytest.approx(33.0)
    assert report["abs_residual_ms"]["max_ms"] == pytest.approx(0.0)
    assert (tmp_path / "comparison" / "response_marker_loopback_pairs.csv").exists()


def test_response_marker_loopback_auto_widens_for_digital_audio_evidence_preroll(tmp_path: Path):
    compare = _load_script("compare_response_marker_loopback.py")
    sample_rate = 44100
    offset_samples = 7000
    marker_samples = [10000, 24000, 38000]
    events_csv = tmp_path / "events.csv"
    recording = tmp_path / "Block_01_audio_evidence.wav"

    rows = []
    for event_id, sample in enumerate(marker_samples, start=1):
        rows.append(
            {
                "event_id": event_id,
                "event_type": "response_marker_start",
                "unix_time": f"{event_id:.9f}",
                "monotonic_time": f"{event_id:.9f}",
                "payload_json": json.dumps(
                    {
                        "sample_index": sample,
                        "mouse_event_id": event_id - 1,
                        "block_number": 1,
                        "timestamp_quality": "dac_time_sample_exact",
                        "marker_gain": 0.05,
                    }
                ),
            }
        )
    _write_csv(events_csv, rows)

    capture = np.zeros((52000, 3), dtype=np.float32)
    for sample in marker_samples:
        start = sample + offset_samples
        capture[start : start + 64, 2] = 0.05
    sf.write(recording, capture, sample_rate)

    report = compare.compare_loopback(
        events_csv=events_csv,
        recordings=[recording],
        output_dir=tmp_path / "digital_comparison",
        tactile_channel_1based=3,
        search_pre_ms=10.0,
        search_post_ms=150.0,
        min_peak=0.005,
    )

    assert report["passed"]
    assert report["detected_marker_count"] == 3
    assert report["offset_ms"]["median_ms"] == pytest.approx(offset_samples / sample_rate * 1000.0)
    assert report["blocks"][0]["recording_role"] == "digital_audio_evidence"
    assert report["blocks"][0]["search_window_ms"]["post"] >= 300.0


def test_recording_layer_alignment_compares_digital_physical_and_lsl(tmp_path: Path):
    compare = _load_script("compare_recording_layers.py")
    sample_rate = 1000
    digital = np.zeros((800, 3), dtype=np.float32)
    digital[100:130, 0] = 0.1
    digital[140:170, 1] = 0.1
    digital[300:305, 2] = 0.08
    physical = np.zeros((850, 3), dtype=np.float32)
    physical[20 : 20 + digital.shape[0], :] = digital
    digital_wav = tmp_path / "Block_01_audio_evidence.wav"
    physical_wav = tmp_path / "Block_01_physical_loopback.wav"
    sf.write(digital_wav, digital, sample_rate)
    sf.write(physical_wav, physical, sample_rate)
    (tmp_path / "Block_01_audio_evidence.output_evidence.json").write_text(
        json.dumps(
            {
                "mode": "digital_output_evidence_wav",
                "sample_rate": sample_rate,
                "channels": 3,
                "frames": int(digital.shape[0]),
                "dropped_buffer_count": 0,
                "clipped_channels_1based": [],
            }
        ),
        encoding="utf-8",
    )
    events = [
        {
            "event_id": 1,
            "event_type": "audio_sample_zero",
            "unix_time": 1.0,
            "monotonic_time": 1.0,
            "payload_json": json.dumps({"block_index": 1, "sample_index": 0, "sample_rate": sample_rate}),
        },
        {
            "event_id": 2,
            "event_type": "tactile_onset",
            "unix_time": 1.3,
            "monotonic_time": 1.3,
            "payload_json": json.dumps({"block_index": 1, "sample_index": 300, "sample_rate": sample_rate, "trial_uid": "T001"}),
        },
        {
            "event_id": 3,
            "event_type": "response_marker_start",
            "unix_time": 1.3,
            "monotonic_time": 1.3,
            "payload_json": json.dumps({"block_index": 1, "sample_index": 300, "sample_rate": sample_rate, "mouse_event_id": 4}),
        },
    ]
    markers = [
        {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "event_code": 20 + int(row["event_id"]),
            "trigger_key": f"control:{row['event_type']}",
            "lsl_timestamp": 1000.0 + (0.3 if row["event_id"] in {2, 3} else 0.0),
            "timestamp_quality": "dac_time_sample_exact",
            "sample_index": 300 if row["event_id"] in {2, 3} else 0,
            "block_index": 1,
            "trial_uid": "T001" if row["event_id"] in {2, 3} else "",
            "pushed_to_lsl": True,
            "payload_json": row["payload_json"],
        }
        for row in events
    ]
    events_csv = tmp_path / "events.csv"
    lsl_csv = tmp_path / "lsl_markers.csv"
    _write_csv(events_csv, events)
    _write_csv(lsl_csv, markers)

    report = compare.compare_layers(
        physical_wav=physical_wav,
        digital_wav=digital_wav,
        events_csv=events_csv,
        lsl_markers_csv=lsl_csv,
        output_dir=tmp_path / "comparison",
    )

    assert report["passed"]
    assert report["audio"]["physical_minus_digital_latency_ms"]["mean_ms"] == pytest.approx(20.0)
    assert report["audio"]["interchannel_skew"]["right_minus_left_ms"] == pytest.approx(0.0)
    assert report["internal_lsl"]["missing_marker_event_ids"] == []
    assert report["internal_lsl"]["lsl_timestamp_error_ms"]["p95_ms"] == pytest.approx(0.0)


def test_study5_baseline_no_looming_metrics_require_instruction_audio():
    audit = _load_script("audit_study5_baseline_propagation.py")
    sample_rate = 1000
    data = np.zeros((8000, 3), dtype=np.float32)
    tone = np.sin(np.linspace(0, np.pi * 16, 4000, endpoint=False)).astype(np.float32) * 0.02
    data[:4000, 0] = tone
    data[:4000, 1] = tone
    data[4800:4900, 2] = 0.05

    ok = audit.baseline_no_looming_metrics(data, sample_rate, looming_offset_s=4.0)
    assert ok["passed"]
    assert ok["pre_instruction_audio_peak"] > 0.01
    assert ok["looming_interval_audio_peak"] == pytest.approx(0.0)
    assert ok["tactile_peak"] == pytest.approx(0.05)

    missing_instruction = data.copy()
    missing_instruction[:4000, :2] = 0.0
    assert not audit.baseline_no_looming_metrics(missing_instruction, sample_rate, looming_offset_s=4.0)["passed"]

    leaking_looming = data.copy()
    leaking_looming[4200:4300, 0] = 0.02
    assert not audit.baseline_no_looming_metrics(leaking_looming, sample_rate, looming_offset_s=4.0)["passed"]


def test_study5_prepared_block_audit_flags_baseline_silent():
    audit = _load_script("audit_study5_baseline_propagation.py")
    families = ["baseline"] * 10 + ["audio_tactile"] * 20 + ["catch"] * 4
    rows = []
    for index, family in enumerate(families, start=1):
        phase = "Inhale" if index % 2 else "Exhale"
        if family == "baseline":
            stem = "baseline_no_looming_inhale4000ms_white_soa300ms_ch3.wav"
        elif family == "audio_tactile":
            stem = "inhale4000ms_whitefrontal4000ms_soa300ms_ch3.wav"
        else:
            stem = "catch_inhale4000ms_whitefrontal4000ms_audio.wav"
        if index == 1:
            stem = "baseline_silent_inhale4000ms_white_soa300ms_ch3.wav"
        rows.append(
            {
                "Trial_Number": index,
                "Family": family,
                "Respiratory_Phase": phase,
                "Row_Label": f"{phase} trial type",
                "Source_File_Name": stem,
                "Trial_File_Path": f"C:/tmp/{stem}",
            }
        )

    report = audit._audit_block_rows(rows, label="Block_01", expect_block_counts=True)

    assert not report["passed"]
    assert report["checks"]["trial_count"]
    assert report["checks"]["family_counts"]
    assert report["checks"]["phase_alternation"]
    assert not report["checks"]["no_stale_baseline_silent"]
