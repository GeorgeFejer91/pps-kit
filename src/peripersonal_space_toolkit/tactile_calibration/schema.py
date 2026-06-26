"""Stable constants and schema fields for tactile calibration artifacts."""

from __future__ import annotations

CALIBRATION_SCHEMA = "pps-tactile-calibration.v1"
LATEST_CALIBRATION_SCHEMA = "pps-tactile-calibration-latest.v1"
PROTOCOL_NAME = "quick_reliable_working_level.v1"

DEFAULT_SAMPLE_RATE_HZ = 44_100
DEFAULT_CHANNEL_COUNT = 3
DEFAULT_PULSE_DURATION_MS = 100.0
DEFAULT_PRE_SILENCE_MS = 500.0
DEFAULT_POST_SILENCE_MS = 1_500.0
VALID_RESPONSE_START_MS = 100.0
VALID_RESPONSE_END_MS = 1_500.0

SEARCH_LEVELS_PERCENT = (5.0, 8.0, 12.0, 18.0, 25.0, 35.0, 50.0, 70.0, 90.0, 100.0)
PRACTICE_TRIAL_COUNT = 2
PRACTICE_MIN_LEVEL_PERCENT = 70.0
VALIDATION_SIGNAL_TRIALS = 6
VALIDATION_CATCH_TRIALS = 2
VALIDATION_MIN_HITS = 5
VALIDATION_MAX_FALSE_ALARMS = 1

REPORT_FILENAME = "tactile_calibration_report.json"
TRIALS_FILENAME = "tactile_calibration_trials.csv"
LATEST_FILENAME = "latest_tactile_calibration.json"

TRIAL_FIELDNAMES = [
    "trial_index",
    "phase",
    "level_percent",
    "is_catch",
    "estimated_onset_perf",
    "valid_start_perf",
    "valid_end_perf",
    "response_perf",
    "response_latency_ms",
    "valid_response",
    "trial_outcome",
]
