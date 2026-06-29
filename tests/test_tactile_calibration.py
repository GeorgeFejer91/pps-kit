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
    CONFIRMATION_CATCH_TRIALS,
    CONFIRMATION_SIGNAL_TRIALS,
    INTER_TRIAL_INTERVAL_MAX_MS,
    INTER_TRIAL_INTERVAL_MIN_MS,
    LATEST_CALIBRATION_SCHEMA,
    PROTOCOL_NAME,
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
        "validation_hit_rate": 1.0,
        "validation_false_alarm_rate": 0.0,
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
    def __init__(self, *, search_detect_at: float | None, confirmation_pass_at: float | None, false_alarm: bool = False):
        self.search_detect_at = search_detect_at
        self.confirmation_pass_at = confirmation_pass_at
        self.false_alarm = false_alarm
        self.current: dict[str, object] = {}

    def start_trial(self, **payload):
        self.current = dict(payload)

    def wait_for_response(self, *, until_perf: float):
        phase = str(self.current.get("phase") or "")
        level = float(self.current.get("level_percent") or 0.0)
        is_catch = bool(self.current.get("is_catch"))
        should_click = False
        if phase == "search" and self.search_detect_at is not None:
            should_click = level >= self.search_detect_at
        elif phase == "confirmation" and is_catch:
            should_click = self.false_alarm
        elif phase == "confirmation" and self.confirmation_pass_at is not None:
            should_click = level >= self.confirmation_pass_at
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


def test_tactile_calibration_protocol_accepts_lowest_confirmed_threshold(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(search_detect_at=25.0, confirmation_pass_at=25.0))

    report = result["report"]
    assert report["accepted"] is True
    assert report["protocol"] == PROTOCOL_NAME
    assert report["final_output_34_percent"] == pytest.approx(25.0)
    assert report["detection_threshold_output_34_percent"] == pytest.approx(25.0)
    assert report["recommended_output_34_percent"] == pytest.approx(25.0)
    assert report["confirmation_summary"]["hits"] == CONFIRMATION_SIGNAL_TRIALS
    assert report["confirmation_summary"]["false_alarms"] == 0
    assert report["timing"]["inter_trial_interval_min_ms"] == pytest.approx(INTER_TRIAL_INTERVAL_MIN_MS)
    assert report["timing"]["inter_trial_interval_max_ms"] == pytest.approx(INTER_TRIAL_INTERVAL_MAX_MS)
    assert any(trial["phase"] == "familiarization" for trial in result["trials"])
    jittered = [trial["inter_trial_interval_ms"] for trial in result["trials"] if trial["phase"] == "confirmation"]
    assert jittered
    assert all(INTER_TRIAL_INTERVAL_MIN_MS <= float(value) <= INTER_TRIAL_INTERVAL_MAX_MS for value in jittered)


def test_tactile_calibration_protocol_escalates_after_failed_confirmation(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(search_detect_at=12.0, confirmation_pass_at=18.0))

    report = result["report"]
    assert report["accepted"] is True
    assert report["final_output_34_percent"] == pytest.approx(18.0)
    confirmation_levels = [trial["level_percent"] for trial in result["trials"] if trial["phase"] == "confirmation"]
    assert 12.0 in confirmation_levels
    assert 18.0 in confirmation_levels
    assert report["candidate_summaries"][0]["hits"] == 0
    assert report["candidate_summaries"][1]["hits"] == CONFIRMATION_SIGNAL_TRIALS


def test_tactile_calibration_protocol_rejects_false_alarm_bias(tmp_path: Path):
    result = _run_protocol(
        tmp_path,
        _ScriptedCollector(search_detect_at=18.0, confirmation_pass_at=18.0, false_alarm=True),
    )

    report = result["report"]
    assert report["accepted"] is False
    assert report["status"] == "invalid_false_alarm"
    assert report["final_output_34_percent"] == ""
    assert report["confirmation_summary"]["false_alarms"] == CONFIRMATION_CATCH_TRIALS


def test_tactile_calibration_protocol_fails_without_any_search_detection(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(search_detect_at=None, confirmation_pass_at=None))

    report = result["report"]
    assert report["accepted"] is False
    assert report["final_output_34_percent"] == ""
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
        "confirmation_summary": {
            "hits": CONFIRMATION_SIGNAL_TRIALS,
            "signal_trials": CONFIRMATION_SIGNAL_TRIALS,
            "false_alarms": 0,
            "catch_trials": CONFIRMATION_CATCH_TRIALS,
        },
        "validation_hit_rate": 1.0,
        "validation_false_alarm_rate": 0.0,
        "extra_verbose": {"not": "copied"},
    }
    save_calibration_attempt(output_root=tmp_path, participant_id="P002", report=report, trials=[], timestamp="t")

    latest_payload = json.loads(latest_calibration_path(tmp_path, "P002").read_text(encoding="utf-8"))
    assert latest_payload["schema"] == LATEST_CALIBRATION_SCHEMA
    assert latest_payload["final_output_34_percent"] == 50.0
    assert latest_payload["recommended_output_34_percent"] == 50.0
    assert latest_payload["confirmation_hits"] == CONFIRMATION_SIGNAL_TRIALS
    assert "extra_verbose" not in latest_payload
