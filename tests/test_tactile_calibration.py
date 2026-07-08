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
    CALIBRATION_MAX_FALSE_ALARMS,
    CONFIRMATION_LEVEL_INCREMENT_PERCENT,
    CONFIRMATION_REQUIRED_CLEAN_CATCHES,
    CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
    INTER_TRIAL_INTERVAL_MAX_MS,
    INTER_TRIAL_INTERVAL_MIN_MS,
    LATEST_CALIBRATION_SCHEMA,
    PROTOCOL_NAME,
    SEARCH_LEVELS_PERCENT,
    STAIRCASE_LOWER_BOUND_HITS,
    STAIRCASE_MIN_CATCH_TRIALS,
    STAIRCASE_STOP_REVERSALS,
    STAIRCASE_TARGET_DETECTION_RATE,
    TACTILE_OUTPUT_34_HARD_GUARD_PERCENT,
    TACTILE_OUTPUT_34_MAX_PERCENT,
    VALID_RESPONSE_END_MS,
    VALID_RESPONSE_START_MS,
)
from peripersonal_space_toolkit.tactile_calibration.stimulus import write_calibration_trial_wav
from peripersonal_space_toolkit.response_policy import TACTILE_RESPONSE_MAX_RT_S, TACTILE_RESPONSE_MIN_RT_S


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
    def __init__(
        self,
        *,
        detection_threshold: float | None,
        false_alarm: bool = False,
        confirmation_threshold: float | None = None,
        confirmation_misses: int = 0,
        confirmation_false_alarm_catches: set[int] | None = None,
    ):
        self.detection_threshold = detection_threshold
        self.false_alarm = false_alarm
        self.confirmation_threshold = detection_threshold if confirmation_threshold is None else confirmation_threshold
        self.confirmation_misses_remaining = int(confirmation_misses)
        self.confirmation_false_alarm_catches = set(confirmation_false_alarm_catches or set())
        self.confirmation_catch_count = 0
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
        elif phase == "confirmation" and is_catch:
            self.confirmation_catch_count += 1
            should_click = self.confirmation_catch_count in self.confirmation_false_alarm_catches
        elif phase == "staircase" and self.detection_threshold is not None:
            should_click = level >= self.detection_threshold
        elif phase == "confirmation" and self.confirmation_threshold is not None:
            if self.confirmation_misses_remaining > 0:
                self.confirmation_misses_remaining -= 1
                should_click = False
            else:
                should_click = level >= self.confirmation_threshold
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
        current_output_34_percent=0.4,
        rng_seed=123,
    )
    return runner.run()


def test_tactile_calibration_protocol_accepts_adaptive_staircase_threshold(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=0.1))

    report = result["report"]
    threshold = float(report["detection_threshold_output_34_percent"])
    final = float(report["final_output_34_percent"])
    assert report["accepted"] is True
    assert report["protocol"] == PROTOCOL_NAME
    assert report["threshold_method"] == "two_down_one_up_transformed_adaptive_staircase_with_catches"
    assert 0.075 <= threshold <= 0.1
    assert threshold <= final <= report["max_output_34_percent"] <= TACTILE_OUTPUT_34_HARD_GUARD_PERCENT
    assert report["recommended_output_34_percent"] == pytest.approx(report["final_output_34_percent"])
    assert report["max_output_34_percent"] == pytest.approx(TACTILE_OUTPUT_34_MAX_PERCENT)
    assert report["initial_software_ceiling_output_34_percent"] == pytest.approx(TACTILE_OUTPUT_34_MAX_PERCENT)
    assert report["final_software_ceiling_output_34_percent"] == pytest.approx(TACTILE_OUTPUT_34_MAX_PERCENT)
    assert report["hard_output_34_guard_percent"] == pytest.approx(TACTILE_OUTPUT_34_HARD_GUARD_PERCENT)
    assert report["dynamic_ceiling_expansion_count"] == 0
    assert report["search_levels_percent"] == pytest.approx(list(SEARCH_LEVELS_PERCENT))
    assert report["staircase_levels_percent"][-1] == pytest.approx(TACTILE_OUTPUT_34_MAX_PERCENT)
    assert report["adaptive_staircase"]["target_detection_rate"] == pytest.approx(STAIRCASE_TARGET_DETECTION_RATE)
    assert report["adaptive_staircase"]["valid_response_start_ms"] == pytest.approx(VALID_RESPONSE_START_MS)
    assert report["adaptive_staircase"]["valid_response_end_ms"] == pytest.approx(VALID_RESPONSE_END_MS)
    assert report["staircase_summary"]["reversals"] >= STAIRCASE_STOP_REVERSALS
    assert report["staircase_summary"]["catch_trials"] >= STAIRCASE_MIN_CATCH_TRIALS
    assert report["staircase_summary"]["false_alarms"] == 0
    assert report["confirmation_summary"]["passed"] is True
    assert report["confirmation_summary"]["consecutive_hits"] >= CONFIRMATION_REQUIRED_CONSECUTIVE_HITS
    assert report["confirmation_summary"]["clean_catches"] >= CONFIRMATION_REQUIRED_CLEAN_CATCHES
    assert report["confirmation_summary"]["false_alarms"] == 0
    assert report["timing"]["inter_trial_interval_min_ms"] == pytest.approx(INTER_TRIAL_INTERVAL_MIN_MS)
    assert report["timing"]["inter_trial_interval_max_ms"] == pytest.approx(INTER_TRIAL_INTERVAL_MAX_MS)
    assert report["timing"]["valid_response_start_ms"] == pytest.approx(TACTILE_RESPONSE_MIN_RT_S * 1000.0)
    assert report["timing"]["valid_response_end_ms"] == pytest.approx(TACTILE_RESPONSE_MAX_RT_S * 1000.0)
    assert any(trial["phase"] == "familiarization" for trial in result["trials"])
    assert any(trial["phase"] == "confirmation" for trial in result["trials"])
    assert any(trial["staircase_direction"] == "down" for trial in result["trials"])
    assert any(trial["staircase_direction"] == "up" for trial in result["trials"])
    jittered = [trial["inter_trial_interval_ms"] for trial in result["trials"] if trial["phase"] == "staircase"]
    assert jittered
    assert all(INTER_TRIAL_INTERVAL_MIN_MS <= float(value) <= INTER_TRIAL_INTERVAL_MAX_MS for value in jittered)


def test_tactile_calibration_expands_software_ceiling_above_initial_max(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=0.82))

    report = result["report"]
    assert report["accepted"] is True
    assert float(report["final_output_34_percent"]) >= 0.82
    assert report["initial_software_ceiling_output_34_percent"] == pytest.approx(TACTILE_OUTPUT_34_MAX_PERCENT)
    assert report["final_software_ceiling_output_34_percent"] > TACTILE_OUTPUT_34_MAX_PERCENT
    assert report["max_output_34_percent"] == pytest.approx(report["final_software_ceiling_output_34_percent"])
    assert report["hard_output_34_guard_percent"] == pytest.approx(TACTILE_OUTPUT_34_HARD_GUARD_PERCENT)
    assert report["dynamic_ceiling_expansion_count"] == len(report["dynamic_ceiling_expansions"])
    assert report["dynamic_ceiling_expansion_count"] > 0
    assert max(report["staircase_levels_percent"]) > TACTILE_OUTPUT_34_MAX_PERCENT
    assert max(trial["level_percent"] for trial in result["trials"]) > TACTILE_OUTPUT_34_MAX_PERCENT


def test_tactile_calibration_protocol_tracks_lower_thresholds(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=0.02))

    report = result["report"]
    assert report["accepted"] is True
    assert 0.015 <= float(report["detection_threshold_output_34_percent"]) <= 0.02
    assert float(report["final_output_34_percent"]) >= float(report["detection_threshold_output_34_percent"])
    staircase_levels = [trial["level_percent"] for trial in result["trials"] if trial["phase"] == "staircase"]
    assert 0.015 in staircase_levels
    assert 0.02 in staircase_levels
    assert report["staircase_summary"]["reversals"] >= STAIRCASE_STOP_REVERSALS


def test_tactile_calibration_protocol_accepts_lower_bound_censored_threshold(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=SEARCH_LEVELS_PERCENT[0]))

    report = result["report"]
    assert report["accepted"] is True
    assert report["status"] == "accepted"
    assert report["threshold_censoring"] == "lower_bound"
    assert report["detection_threshold_output_34_percent"] == pytest.approx(SEARCH_LEVELS_PERCENT[0])
    assert report["final_output_34_percent"] == pytest.approx(SEARCH_LEVELS_PERCENT[0])
    assert report["adaptive_staircase"]["lower_bound_hits"] == STAIRCASE_LOWER_BOUND_HITS
    assert report["staircase_summary"]["threshold_censoring"] == "lower_bound"
    assert report["confirmation_summary"]["consecutive_hits"] >= CONFIRMATION_REQUIRED_CONSECUTIVE_HITS
    assert report["confirmation_summary"]["clean_catches"] >= CONFIRMATION_REQUIRED_CLEAN_CATCHES


def test_tactile_calibration_protocol_rejects_false_alarm_bias(tmp_path: Path):
    result = _run_protocol(
        tmp_path,
        _ScriptedCollector(detection_threshold=0.02, false_alarm=True),
    )

    report = result["report"]
    assert report["accepted"] is False
    assert report["status"] == "invalid_false_alarm"
    assert report["final_output_34_percent"] == ""
    assert report["staircase_summary"]["false_alarms"] == CALIBRATION_MAX_FALSE_ALARMS


def test_tactile_calibration_confirmation_miss_raises_level_without_repeating_staircase(tmp_path: Path):
    result = _run_protocol(
        tmp_path,
        _ScriptedCollector(
            detection_threshold=SEARCH_LEVELS_PERCENT[0],
            confirmation_threshold=SEARCH_LEVELS_PERCENT[0],
            confirmation_misses=1,
        ),
    )

    report = result["report"]
    assert report["accepted"] is True
    assert report["detection_threshold_output_34_percent"] == pytest.approx(SEARCH_LEVELS_PERCENT[0])
    assert report["final_output_34_percent"] == pytest.approx(
        SEARCH_LEVELS_PERCENT[0] + CONFIRMATION_LEVEL_INCREMENT_PERCENT
    )
    assert report["confirmation_summary"]["misses"] == 1
    assert report["confirmation_summary"]["consecutive_hits"] >= CONFIRMATION_REQUIRED_CONSECUTIVE_HITS
    confirmation_misses = [
        trial for trial in result["trials"] if trial["phase"] == "confirmation" and trial["trial_outcome"] == "miss"
    ]
    assert len(confirmation_misses) == 1
    assert confirmation_misses[0]["confirmation_consecutive_hits"] == 0


def test_tactile_calibration_confirmation_false_alarm_warns_resets_and_keeps_intensity(tmp_path: Path):
    result = _run_protocol(
        tmp_path,
        _ScriptedCollector(
            detection_threshold=SEARCH_LEVELS_PERCENT[0],
            confirmation_false_alarm_catches={2},
        ),
    )

    report = result["report"]
    assert report["accepted"] is True
    assert report["final_output_34_percent"] == pytest.approx(report["detection_threshold_output_34_percent"])
    assert report["confirmation_summary"]["false_alarms"] == 1
    assert report["confirmation_summary"]["clean_catches"] >= CONFIRMATION_REQUIRED_CLEAN_CATCHES
    false_alarm_trials = [
        trial for trial in result["trials"] if trial["phase"] == "confirmation" and trial["trial_outcome"] == "false_alarm"
    ]
    assert len(false_alarm_trials) == 1
    assert false_alarm_trials[0]["warning"] == "Only press when you feel the tactile pulse."
    assert false_alarm_trials[0]["confirmation_clean_catches"] == 0
    assert false_alarm_trials[0]["level_percent"] == pytest.approx(report["detection_threshold_output_34_percent"])


def test_tactile_calibration_confirmation_fails_on_third_cumulative_false_alarm(tmp_path: Path):
    result = _run_protocol(
        tmp_path,
        _ScriptedCollector(
            detection_threshold=SEARCH_LEVELS_PERCENT[0],
            confirmation_false_alarm_catches={1, 2, 3},
        ),
    )

    report = result["report"]
    assert report["accepted"] is False
    assert report["status"] == "invalid_false_alarm"
    assert report["final_output_34_percent"] == ""
    assert report["staircase_summary"]["false_alarms"] == 0
    assert report["confirmation_summary"]["false_alarms"] == CALIBRATION_MAX_FALSE_ALARMS


def test_tactile_calibration_protocol_fails_without_any_detection(tmp_path: Path):
    result = _run_protocol(tmp_path, _ScriptedCollector(detection_threshold=None))

    report = result["report"]
    assert report["accepted"] is False
    assert report["final_output_34_percent"] == ""
    assert report["status"] == "failed_no_detection_at_hard_guard"
    assert "hard safety guard" in report["message"]
    assert report["final_software_ceiling_output_34_percent"] == pytest.approx(TACTILE_OUTPUT_34_HARD_GUARD_PERCENT)


def test_latest_calibration_json_is_small_summary(tmp_path: Path):
    report = {
        "schema": CALIBRATION_SCHEMA,
        "participant_id": "P002",
        "created_at": "2026-06-26T12:00:00",
        "protocol": PROTOCOL_NAME,
        "accepted": True,
        "status": "accepted",
        "final_output_34_percent": 0.82,
        "detection_threshold_output_34_percent": 0.81,
        "recommended_output_34_percent": 0.82,
        "confirmation_level_output_34_percent": 0.82,
        "max_output_34_percent": 0.82,
        "initial_software_ceiling_output_34_percent": 0.7,
        "final_software_ceiling_output_34_percent": 0.82,
        "hard_output_34_guard_percent": 1.0,
        "dynamic_ceiling_expansions": [
            {
                "index": 1,
                "old_software_ceiling_output_34_percent": 0.7,
                "new_software_ceiling_output_34_percent": 0.82,
                "hard_output_34_guard_percent": 1.0,
            }
        ],
        "dynamic_ceiling_expansion_count": 1,
        "adaptive_staircase": {
            "target_detection_rate": STAIRCASE_TARGET_DETECTION_RATE,
            "stop_reversals": STAIRCASE_STOP_REVERSALS,
            "minimum_catch_trials": STAIRCASE_MIN_CATCH_TRIALS,
        },
        "confirmation_criteria": {
            "required_consecutive_hits": CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
            "required_clean_catches": CONFIRMATION_REQUIRED_CLEAN_CATCHES,
            "level_increment_percent": CONFIRMATION_LEVEL_INCREMENT_PERCENT,
            "max_false_alarms": CALIBRATION_MAX_FALSE_ALARMS,
        },
        "confirmation_summary": {
            "hits": 10,
            "misses": 1,
            "signal_trials": 11,
            "false_alarms": 0,
            "catch_trials": CONFIRMATION_REQUIRED_CLEAN_CATCHES,
            "clean_catches": CONFIRMATION_REQUIRED_CLEAN_CATCHES,
            "consecutive_hits": CONFIRMATION_REQUIRED_CONSECUTIVE_HITS,
            "hit_rate": 10 / 11,
            "false_alarm_rate": 0.0,
            "confirmed_output_34_percent": 50.01,
            "passed": True,
        },
        "staircase_summary": {
            "target_detection_rate": STAIRCASE_TARGET_DETECTION_RATE,
            "hits": 16,
            "misses": 6,
            "signal_trials": 22,
            "false_alarms": 0,
            "catch_trials": STAIRCASE_MIN_CATCH_TRIALS,
            "reversals": STAIRCASE_STOP_REVERSALS,
            "reversal_levels_percent": [0.7, 0.5, 0.35, 0.5, 0.35, 0.5],
            "reversal_levels_used_percent": [0.35, 0.5, 0.35, 0.5],
            "hit_rate": 16 / 22,
            "false_alarm_rate": 0.0,
        },
        "staircase_hit_rate": 16 / 22,
        "confirmation_hit_rate": 10 / 11,
        "confirmation_false_alarm_rate": 0.0,
        "validation_hit_rate": 16 / 22,
        "validation_false_alarm_rate": 0.0,
        "extra_verbose": {"not": "copied"},
    }
    save_calibration_attempt(output_root=tmp_path, participant_id="P002", report=report, trials=[], timestamp="t")

    latest_payload = json.loads(latest_calibration_path(tmp_path, "P002").read_text(encoding="utf-8"))
    assert latest_payload["schema"] == LATEST_CALIBRATION_SCHEMA
    assert latest_payload["final_output_34_percent"] == 0.82
    assert latest_payload["recommended_output_34_percent"] == 0.82
    assert latest_payload["detection_threshold_output_34_percent"] == 0.81
    assert latest_payload["max_output_34_percent"] == 0.82
    assert latest_payload["initial_software_ceiling_output_34_percent"] == 0.7
    assert latest_payload["final_software_ceiling_output_34_percent"] == 0.82
    assert latest_payload["hard_output_34_guard_percent"] == 1.0
    assert latest_payload["dynamic_ceiling_expansion_count"] == 1
    assert latest_payload["dynamic_ceiling_expansions"][0]["new_software_ceiling_output_34_percent"] == 0.82
    assert latest_payload["staircase_reversals"] == STAIRCASE_STOP_REVERSALS
    assert latest_payload["staircase_target_detection_rate"] == pytest.approx(STAIRCASE_TARGET_DETECTION_RATE)
    assert latest_payload["staircase_signal_trials"] == 22
    assert latest_payload["staircase_catch_trials"] == STAIRCASE_MIN_CATCH_TRIALS
    assert latest_payload["confirmation_consecutive_hits"] == CONFIRMATION_REQUIRED_CONSECUTIVE_HITS
    assert latest_payload["confirmation_clean_catches"] == CONFIRMATION_REQUIRED_CLEAN_CATCHES
    assert latest_payload["confirmation_required_clean_catches"] == CONFIRMATION_REQUIRED_CLEAN_CATCHES
    assert latest_payload["catch_trials"] == CONFIRMATION_REQUIRED_CLEAN_CATCHES
    assert "extra_verbose" not in latest_payload
