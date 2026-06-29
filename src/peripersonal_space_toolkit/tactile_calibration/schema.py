"""Stable constants and schema fields for tactile calibration artifacts."""

from __future__ import annotations

CALIBRATION_SCHEMA = "pps-tactile-calibration.v2"
LATEST_CALIBRATION_SCHEMA = "pps-tactile-calibration-latest.v2"
PROTOCOL_NAME = "two_down_one_up_detection_threshold.v2"

DEFAULT_SAMPLE_RATE_HZ = 44_100
DEFAULT_CHANNEL_COUNT = 3
DEFAULT_PULSE_DURATION_MS = 100.0
DEFAULT_PRE_SILENCE_MS = 500.0
DEFAULT_POST_SILENCE_MS = 1_500.0
VALID_RESPONSE_START_MS = 100.0
VALID_RESPONSE_END_MS = 1_500.0

TACTILE_OUTPUT_34_MAX_PERCENT = 0.5
SEARCH_LEVELS_PERCENT = (0.01, 0.015, 0.02, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5)
FAMILIARIZATION_TRIAL_COUNT = 1
FAMILIARIZATION_MIN_LEVEL_PERCENT = TACTILE_OUTPUT_34_MAX_PERCENT
STAIRCASE_DOWN_AFTER_HITS = 2
STAIRCASE_UP_AFTER_MISSES = 1
STAIRCASE_TARGET_DETECTION_RATE = 0.7071067811865476
STAIRCASE_STOP_REVERSALS = 6
STAIRCASE_REVERSALS_TO_AVERAGE = 4
STAIRCASE_LOWER_BOUND_HITS = 4
STAIRCASE_MIN_CATCH_TRIALS = 3
STAIRCASE_CATCH_INTERVAL_SIGNALS = 4
STAIRCASE_MAX_FALSE_ALARMS = 0
INTER_TRIAL_INTERVAL_MIN_MS = 1_800.0
INTER_TRIAL_INTERVAL_MAX_MS = 2_600.0
MAX_CALIBRATION_EVENTS = 60

REPORT_FILENAME = "tactile_calibration_report.json"
TRIALS_FILENAME = "tactile_calibration_trials.csv"
LATEST_FILENAME = "latest_tactile_calibration.json"

TRIAL_FIELDNAMES = [
    "trial_index",
    "phase",
    "level_percent",
    "candidate_level_percent",
    "staircase_index",
    "staircase_direction",
    "reversal_index",
    "consecutive_hits",
    "consecutive_misses",
    "step_index",
    "is_catch",
    "pulse_present",
    "inter_trial_interval_ms",
    "estimated_onset_perf",
    "valid_start_perf",
    "valid_end_perf",
    "response_perf",
    "response_latency_ms",
    "valid_response",
    "response_present",
    "trial_outcome",
    "response_x",
    "response_y",
    "response_in_target",
    "response_source",
    "recenter_mode",
    "recenter_x",
    "recenter_y",
    "recenter_coordinate_source",
]
