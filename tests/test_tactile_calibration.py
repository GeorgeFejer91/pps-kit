from __future__ import annotations

import json
from pathlib import Path
import wave

import numpy as np
import pytest

from peripersonal_space_toolkit.tactile_calibration.persistence import (
    latest_calibration_path,
    load_latest_calibration,
    save_calibration_attempt,
    sanitize_participant_id,
)
from peripersonal_space_toolkit.tactile_calibration.protocol import TactileCalibrationRunner
from peripersonal_space_toolkit.tactile_calibration.schema import (
    CALIBRATION_SCHEMA,
    INTER_TRIAL_INTERVAL_MAX_MS,
    INTER_TRIAL_INTERVAL_MIN_MS,
    LATEST_CALIBRATION_SCHEMA,
    PROTOCOL_NAME,
    SEARCH_LEVELS_PERCENT,
    STAIRCASE_LOWER_BOUND_HITS,
    STAIRCASE_MIN_CATCH_TRIALS,
    STAIRCASE_STOP_REVERSALS,
    STAIRCASE_TARGET_DETECTION_RATE,
    TACTILE_OUTPUT_34_MAX_PERCENT,
)
from peripersonal_space_toolkit.tactile_calibration.stimulus import write_calibration_trial_wav


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TACTILE_CUE = REPO_ROOT / "assets" / "tactile" / "default_tactile_cue.wav"


def test_calibration_persistence_latest_success_only(tmp_path: Path):
    report = {
        "schema": CALIBRATION_SCHEMA,
        "participant_id": "P001",
        "created_at": "2026-06-26T12:00:00",
        "protocol": PROTOCOL_NAME,
        "accepted": True,
        "status": "accepted",
        "final_output_34_percent": 35.0,
        "detection_threshold_output_34_percent": 35.0,
        "recommended_output_34_percent": 35.0,
        "staircase_summary": {
            "target_detection_rate": STAIRCASE_TARGET_DETECTION_RATE,
            "signal_trials": 20,
            "catch_trials": STAIRCASE_MIN_CATCH_TRIALS,
            "hits": 14,
            "misses": 6,
            "false_alarms": 0,
            "reversals": STAIRCASE_STOP_REVERSALS,
            "reversal_levels_percent": [50.0, 35.0, 25.0, 35.0, 25.0, 35.0],
            "reversal_levels_used_percent": [25.0, 35.0, 25.0, 35.0],
            "hit_rate": 0.7,
            "false_alarm_rate": 0.0,
        },
        "staircase_hit_rate": 0.7,
        "staircase_false_alarm_rate": 0.0,
    }
    paths = save_calibration_attempt(
        output_root=tmp_path,
        participant_id="P001",
        report=report,
        trials=[{"trial_index": 1, "phase": "search", "level_percent": 35.0, "valid_response": True}],
        timestamp="20260626_120000",
    )

    assert paths["report_path"].exists()
    assert paths["trials_csv_path"].exists()
    assert latest_calibration_path(tmp_path, "P001").exists()
    latest = load_latest_calibration(tmp_path, "P001")
    assert latest is not None
    assert latest["final_output_34_percent"] == pytest.approx(35.0)
    assert "P001_tactile-calibration" in latest["latest_path"]

    failed_report = {**report, "accepted": False, "status": "failed", "final_output_34_percent": ""}
    save_calibration_attempt(
        output_root=tmp_path,
        participant_id="P001",
        report=failed_report,
        trials=[],
        timestamp="20260626_121000",
    )

    still_latest = load_latest_calibration(tmp_path, "P001")
    assert still_latest is not None
    assert still_latest["final_output_34_percent"] == pytest.approx(35.0)
    assert sanitize_participant_id(" P 01 / test ") == "P_01_test"


def test_tactile_calibration_stimulus_uses_three_channel_tactile_route(tmp_path: Path):
    wav_path = tmp_path / "trial.wav"
    info = write_calibration_trial_wav(
        wav_path,
        level_percent=50.0,
        source_pulse_path=DEFAULT_TACTILE_CUE,
    )

    assert info.sample_rate_hz == 44_100
    assert info.channels == 3
    assert info.used_fallback_pulse is False
    assert info.pulse_scale_percent == pytest.approx(50.0)
    assert info.pulse_duration_ms == pytest.approx(100.0, abs=0.05)
    with wave.open(str(wav_path), "rb") as handle:
        assert handle.getframerate() == 44_100
        assert handle.getnchannels() == 3
        raw = handle.readframes(handle.getnframes())
    samples = np.frombuffer(raw, dtype="<i2").reshape((-1, 3))
    assert np.max(np.abs(samples[:, 0])) == 0
    assert np.max(np.abs(samples[:, 1])) == 0
    assert np.max(np.abs(samples[:, 2])) > 0
    pre_frames = int(round(44_100 * 0.5))
    pulse_frames = int(round(44_100 * 0.1))
    assert np.max(np.abs(samples[:pre_frames, 2])) == 0
    assert np.max(np.abs(samples[pre_frames : pre_frames + pulse_frames, 2])) > 0


class _FakeAudioEngine:
    def __init__(self, fail_after: int | None = None):
        self.played_blocks: list[str] = []
        self.fail_after = fail_after

    def play_block(self, path: str) -> bool:
        self.played_blocks.append(path)
        if self.fail_after is not None and len(self.played_blocks) > self.fail_after:
            return False
        return True


class _ScriptedCollector:
    def __init__(self, *, detection_threshold: float | None, false_alarm: bool = False):
        self.detection_threshold = detection_threshold
        self.false_alarm = false_alarm
        self.current: dict[str, object] = {}

    def start_trial(self, **payload):
        self.current = dict(payload)

    def wait_for_response(self, *, until_perf: float):
        phase = str(self.current.get("phase") or "")
        level = float(self.current.get("level_percent") or 0.0)
        is_catch = bool(self.current.get("is_catch"))
        should_click = False
        if phase == "staircase" and is_catch:
            should_click = self.false_alarm
        elif phase == "staircase" and self.detection_threshold is not None:
            should_click = level >= self.detection_threshold
        if not should_click:
            return None
        onset = float(self.current.get("estimated_onset_perf") or 0.0)
        response_perf = onset + 0.25
        return {
            "response_perf": response_perf,
            "response_latency_ms": 250.0,
            "valid_response": True,
        }

    def finish_trial(self):
        self.current = {}


def _run_protocol(tmp_path: Path, collector: _ScriptedCollector) -> dict:
    runner = TactileCalibrationRunner(
        audio_engine=_FakeAudioEngine(),
        response_collector=collector,
        participant_id="P001",
        output_root=tmp_path,
        source_pulse_path=DEFAULT_TACTILE_CUE,
        current_output_34_percent=40.0,
        rng_seed=123,
    )
    return runner.run()


def test_tactile_calibration_protocol_accepts_adaptive_staircase_threshold(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=0.1))

    report = result["report"]
    assert report["accepted"] is True
    assert report["protocol"] == PROTOCOL_NAME
    assert report["threshold_method"] == "two_down_one_up_transformed_adaptive_staircase_with_catches"
    assert 0.075 <= float(report["final_output_34_percent"]) <= 0.1
    assert report["detection_threshold_output_34_percent"] == pytest.approx(report["final_output_34_percent"])
    assert report["recommended_output_34_percent"] == pytest.approx(report["final_output_34_percent"])
    assert report["max_output_34_percent"] == pytest.approx(TACTILE_OUTPUT_34_MAX_PERCENT)
    assert report["search_levels_percent"] == pytest.approx(list(SEARCH_LEVELS_PERCENT))
    assert report["adaptive_staircase"]["target_detection_rate"] == pytest.approx(STAIRCASE_TARGET_DETECTION_RATE)
    assert report["staircase_summary"]["reversals"] >= STAIRCASE_STOP_REVERSALS
    assert report["staircase_summary"]["catch_trials"] >= STAIRCASE_MIN_CATCH_TRIALS
    assert report["staircase_summary"]["false_alarms"] == 0
    assert report["timing"]["inter_trial_interval_min_ms"] == pytest.approx(INTER_TRIAL_INTERVAL_MIN_MS)
    assert report["timing"]["inter_trial_interval_max_ms"] == pytest.approx(INTER_TRIAL_INTERVAL_MAX_MS)
    assert any(trial["phase"] == "familiarization" for trial in result["trials"])
    assert any(trial["staircase_direction"] == "down" for trial in result["trials"])
    assert any(trial["staircase_direction"] == "up" for trial in result["trials"])
    jittered = [trial["inter_trial_interval_ms"] for trial in result["trials"] if trial["phase"] == "staircase"]
    assert jittered
    assert all(INTER_TRIAL_INTERVAL_MIN_MS <= float(value) <= INTER_TRIAL_INTERVAL_MAX_MS for value in jittered)


def test_tactile_calibration_protocol_tracks_lower_thresholds(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=0.02))

    report = result["report"]
    assert report["accepted"] is True
    assert 0.015 <= float(report["final_output_34_percent"]) <= 0.02
    staircase_levels = [trial["level_percent"] for trial in result["trials"] if trial["phase"] == "staircase"]
    assert 0.015 in staircase_levels
    assert 0.02 in staircase_levels
    assert report["staircase_summary"]["reversals"] >= STAIRCASE_STOP_REVERSALS


def test_tactile_calibration_protocol_accepts_lower_bound_censored_threshold(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=SEARCH_LEVELS_PERCENT[0]))

    report = result["report"]
    assert report["accepted"] is True
    assert report["status"] == "accepted_lower_bound_censored"
    assert report["threshold_censoring"] == "lower_bound"
    assert report["final_output_34_percent"] == pytest.approx(SEARCH_LEVELS_PERCENT[0])
    assert report["adaptive_staircase"]["lower_bound_hits"] == STAIRCASE_LOWER_BOUND_HITS
    assert report["staircase_summary"]["threshold_censoring"] == "lower_bound"


def test_tactile_calibration_protocol_rejects_false_alarm_bias(tmp_path: Path):
    result = _run_protocol(
        tmp_path,
        _ScriptedCollector(detection_threshold=0.02, false_alarm=True),
    )

    report = result["report"]
    assert report["accepted"] is False
    assert report["status"] == "invalid_false_alarm"
    assert report["final_output_34_percent"] == ""
    assert report["staircase_summary"]["false_alarms"] == 1


def test_tactile_calibration_protocol_fails_without_any_detection(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=None))

    report = result["report"]
    assert report["accepted"] is False
    assert report["final_output_34_percent"] == ""
    assert report["status"] == "failed_no_detection_at_max"
    assert "did not report" in report["message"]


def test_latest_calibration_json_is_small_summary(tmp_path: Path):
    report = {
        "schema": CALIBRATION_SCHEMA,
        "participant_id": "P002",
        "created_at": "2026-06-26T12:00:00",
        "protocol": PROTOCOL_NAME,
        "accepted": True,
        "status": "accepted",
        "final_output_34_percent": 50.0,
        "detection_threshold_output_34_percent": 50.0,
        "recommended_output_34_percent": 50.0,
        "adaptive_staircase": {
            "target_detection_rate": STAIRCASE_TARGET_DETECTION_RATE,
            "stop_reversals": STAIRCASE_STOP_REVERSALS,
            "minimum_catch_trials": STAIRCASE_MIN_CATCH_TRIALS,
        },
        "staircase_summary": {
            "target_detection_rate": STAIRCASE_TARGET_DETECTION_RATE,
            "hits": 16,
            "misses": 6,
            "signal_trials": 22,
            "false_alarms": 0,
            "catch_trials": STAIRCASE_MIN_CATCH_TRIALS,
            "reversals": STAIRCASE_STOP_REVERSALS,
            "reversal_levels_percent": [70.0, 50.0, 35.0, 50.0, 35.0, 50.0],
            "reversal_levels_used_percent": [35.0, 50.0, 35.0, 50.0],
            "hit_rate": 16 / 22,
            "false_alarm_rate": 0.0,
        },
        "staircase_hit_rate": 16 / 22,
        "validation_hit_rate": 16 / 22,
        "validation_false_alarm_rate": 0.0,
        "extra_verbose": {"not": "copied"},
    }
    save_calibration_attempt(output_root=tmp_path, participant_id="P002", report=report, trials=[], timestamp="t")

    latest_payload = json.loads(latest_calibration_path(tmp_path, "P002").read_text(encoding="utf-8"))
    assert latest_payload["schema"] == LATEST_CALIBRATION_SCHEMA
    assert latest_payload["final_output_34_percent"] == 50.0
    assert latest_payload["recommended_output_34_percent"] == 50.0
    assert latest_payload["staircase_reversals"] == STAIRCASE_STOP_REVERSALS
    assert latest_payload["staircase_target_detection_rate"] == pytest.approx(STAIRCASE_TARGET_DETECTION_RATE)
    assert latest_payload["staircase_signal_trials"] == 22
    assert latest_payload["catch_trials"] == STAIRCASE_MIN_CATCH_TRIALS
    assert "extra_verbose" not in latest_payload
