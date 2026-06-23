"""Provisional Woojer tactile-drive latency compensation policy."""

from __future__ import annotations

import math
import os
from typing import Any


DEFAULT_WOOJER_AUDIO_PATH_COMPENSATION_MS = 23.0
DEFAULT_NOMINAL_TACTILE_ONSET_MS = 100.0
WOOJER_COMPENSATION_ENV_VAR = "PPS_WOOJER_TACTILE_COMPENSATION_MS"
WOOJER_COMPENSATION_STATUS = "provisional_woojer_audio_path_not_mechanical_onset"


def configured_woojer_compensation_ms(value: Any | None = None) -> float:
    """Return the non-negative Woojer drive advance in milliseconds."""
    raw = os.environ.get(WOOJER_COMPENSATION_ENV_VAR, "") if value is None else value
    if raw in (None, ""):
        return DEFAULT_WOOJER_AUDIO_PATH_COMPENSATION_MS
    try:
        parsed = float(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_WOOJER_AUDIO_PATH_COMPENSATION_MS
    if not math.isfinite(parsed):
        return DEFAULT_WOOJER_AUDIO_PATH_COMPENSATION_MS
    return max(0.0, parsed)


def tactile_drive_onset_s(nominal_tactile_onset_s: float, compensation_ms: float | None = None) -> float:
    """Return the compensated audio-drive onset for a nominal tactile event."""
    compensation = configured_woojer_compensation_ms(compensation_ms)
    try:
        nominal = float(nominal_tactile_onset_s)
    except (TypeError, ValueError):
        nominal = 0.0
    if not math.isfinite(nominal):
        nominal = 0.0
    return max(0.0, nominal - compensation / 1000.0)


def woojer_tactile_latency_policy(compensation_ms: float | None = None) -> dict[str, Any]:
    """Return manifest-ready metadata for the current provisional policy."""
    compensation = configured_woojer_compensation_ms(compensation_ms)
    example_drive_ms = max(0.0, DEFAULT_NOMINAL_TACTILE_ONSET_MS - compensation)
    return {
        "schema": "pps-woojer-tactile-latency-compensation.v1",
        "enabled": compensation > 0.0,
        "status": WOOJER_COMPENSATION_STATUS,
        "compensation_ms": compensation,
        "nominal_reference_tactile_onset_ms": DEFAULT_NOMINAL_TACTILE_ONSET_MS,
        "example_compensated_drive_onset_ms": example_drive_ms,
        "environment_override": WOOJER_COMPENSATION_ENV_VAR,
        "measurement_basis": "Woojer audio pass-through loopback, provisional; not mechanical vibration onset.",
        "timing_rule": "Prepared block WAVs advance tactile drive by compensation_ms while nominal tactile onset stays unchanged.",
    }
