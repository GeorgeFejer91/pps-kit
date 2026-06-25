"""Loudness policy helpers for calibrated/estimated Study 5 audio levels."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Mapping


LOUDNESS_POLICY_KEY = "loudness_policy"
LOUDNESS_POLICY_SCHEMA = "pps-loudness-policy.v1"
LOUDNESS_MANIFEST_SCHEMA = "pps-loudness-manifest.v1"
DEFAULT_START_SPL_DB = 55.0
DEFAULT_END_SPL_DB = 75.0
DEFAULT_INSTRUCTION_OFFSET_DB = -6.0
DEFAULT_ESTIMATED_FULL_SCALE_SPL_DB = 109.2
DEFAULT_CALIBRATION_WINDOW_S = 0.5
DEFAULT_AUDIO_PEAK_CEILING_DBFS = -1.0


DEFAULT_LOUDNESS_POLICY: dict[str, Any] = {
    "schema": LOUDNESS_POLICY_SCHEMA,
    "mode": "estimated_spl",
    "calibration_mode": "estimate_allowed",
    "calibration_status": "estimated_not_measured",
    "start_spl_db": DEFAULT_START_SPL_DB,
    "end_spl_db": DEFAULT_END_SPL_DB,
    "instruction_offset_db": DEFAULT_INSTRUCTION_OFFSET_DB,
    "movement_ramp_shape": "linear_db",
    "hold_level_policy": "constant_start_and_endpoint",
    "calibration_window": "final_500ms_active_movement_excluding_padding",
    "calibration_window_s": DEFAULT_CALIBRATION_WINDOW_S,
    "estimated_full_scale_spl_db": DEFAULT_ESTIMATED_FULL_SCALE_SPL_DB,
    "audio_peak_ceiling_dbfs": DEFAULT_AUDIO_PEAK_CEILING_DBFS,
    "renderer_role": "3DTI_spatialization_with_toolkit_loudness_control",
    "distance_gain_policy": "disable_direct_path_gain_for_calibrated_loudness",
    "hardware": {
        "audio_interface": "Native Instruments Komplete Audio 6 MK2",
        "headphones": "Sennheiser HD 560S",
        "headphone_knob": "maximum_clockwise",
        "route": "ASIO / Komplete Audio ASIO Driver",
        "runner_audio_volume_percent": 100,
        "windows_volume_policy": "not_part_of_asio_calibration",
    },
    "estimate_basis": {
        "headphone_sensitivity": "HD 560S manufacturer: 110 dB SPL at 1 kHz / 1 Vrms",
        "interface_output": "Komplete Audio 6 MK2 secondary estimate: 2 x 25 mW at 33 ohm",
        "warning": "SPL is estimated until measured with a headphone coupler/artificial ear.",
    },
}


def db_to_linear(db: float) -> float:
    """Convert a dB amplitude difference to a linear multiplier."""

    return 10.0 ** (float(db) / 20.0)


def linear_to_db(value: float) -> float:
    if value <= 0:
        return float("-inf")
    return 20.0 * math.log10(float(value))


def spl_to_rms_dbfs(policy: Mapping[str, Any], spl_db: float) -> float:
    """Estimate RMS dBFS required for a target SPL under the policy mapping."""

    full_scale = _float(policy.get("estimated_full_scale_spl_db"), DEFAULT_ESTIMATED_FULL_SCALE_SPL_DB)
    return float(spl_db) - full_scale


def rms_dbfs_to_estimated_spl(policy: Mapping[str, Any], rms_dbfs: float) -> float:
    full_scale = _float(policy.get("estimated_full_scale_spl_db"), DEFAULT_ESTIMATED_FULL_SCALE_SPL_DB)
    return float(rms_dbfs) + full_scale


def normalize_loudness_policy(
    value: Any | None,
    *,
    pre_hold_s: float | None = None,
    movement_duration_s: float | None = None,
    post_hold_s: float | None = None,
) -> dict[str, Any]:
    """Return a backward-compatible, manifest-ready loudness policy."""

    incoming = dict(value) if isinstance(value, Mapping) else {}
    policy = _deep_merge(DEFAULT_LOUDNESS_POLICY, incoming)
    policy["schema"] = LOUDNESS_POLICY_SCHEMA
    policy["mode"] = _choice(policy.get("mode"), {"estimated_spl", "measured_spl", "digital_dbfs"}, "estimated_spl")
    policy["calibration_mode"] = _choice(
        policy.get("calibration_mode"),
        {"estimate_allowed", "measured_required", "digital_only"},
        "estimate_allowed",
    )
    policy["calibration_status"] = _choice(
        policy.get("calibration_status"),
        {"estimated_not_measured", "measured", "digital_only"},
        "estimated_not_measured",
    )
    policy["start_spl_db"] = _float(policy.get("start_spl_db"), DEFAULT_START_SPL_DB)
    policy["end_spl_db"] = _float(policy.get("end_spl_db"), DEFAULT_END_SPL_DB)
    if policy["end_spl_db"] < policy["start_spl_db"]:
        policy["start_spl_db"], policy["end_spl_db"] = policy["end_spl_db"], policy["start_spl_db"]
    policy["instruction_offset_db"] = _float(policy.get("instruction_offset_db"), DEFAULT_INSTRUCTION_OFFSET_DB)
    policy["movement_ramp_shape"] = _choice(policy.get("movement_ramp_shape"), {"linear_db"}, "linear_db")
    policy["hold_level_policy"] = _choice(
        policy.get("hold_level_policy"),
        {"constant_start_and_endpoint"},
        "constant_start_and_endpoint",
    )
    policy["calibration_window"] = "final_500ms_active_movement_excluding_padding"
    policy["calibration_window_s"] = max(0.05, _float(policy.get("calibration_window_s"), DEFAULT_CALIBRATION_WINDOW_S))
    policy["estimated_full_scale_spl_db"] = _float(
        policy.get("estimated_full_scale_spl_db"),
        DEFAULT_ESTIMATED_FULL_SCALE_SPL_DB,
    )
    policy["audio_peak_ceiling_dbfs"] = min(0.0, _float(policy.get("audio_peak_ceiling_dbfs"), DEFAULT_AUDIO_PEAK_CEILING_DBFS))
    if pre_hold_s is not None:
        policy["pre_hold_s"] = max(0.0, float(pre_hold_s))
    else:
        policy["pre_hold_s"] = max(0.0, _float(policy.get("pre_hold_s"), 0.5))
    if movement_duration_s is not None:
        policy["movement_duration_s"] = max(0.0, float(movement_duration_s))
    else:
        policy["movement_duration_s"] = max(0.0, _float(policy.get("movement_duration_s"), 3.0))
    if post_hold_s is not None:
        policy["post_hold_s"] = max(0.0, float(post_hold_s))
    else:
        policy["post_hold_s"] = max(0.0, _float(policy.get("post_hold_s"), 0.5))
    policy["total_duration_s"] = policy["pre_hold_s"] + policy["movement_duration_s"] + policy["post_hold_s"]
    policy["start_target_rms_dbfs"] = spl_to_rms_dbfs(policy, policy["start_spl_db"])
    policy["end_target_rms_dbfs"] = spl_to_rms_dbfs(policy, policy["end_spl_db"])
    policy["instruction_target_spl_db"] = policy["end_spl_db"] + policy["instruction_offset_db"]
    policy["instruction_target_rms_dbfs"] = spl_to_rms_dbfs(policy, policy["instruction_target_spl_db"])
    return policy


def loudness_policy_for_design(design: Any) -> dict[str, Any]:
    params = getattr(design, "study_profile_reference_parameters", {}) or {}
    trajectory = getattr(design, "trajectory", None)
    return normalize_loudness_policy(
        params.get(LOUDNESS_POLICY_KEY) if isinstance(params, Mapping) else None,
        pre_hold_s=getattr(trajectory, "padding_pre_s", None),
        movement_duration_s=getattr(trajectory, "movement_duration_s", None),
        post_hold_s=getattr(trajectory, "padding_post_s", None),
    )


def envelope_db_for_time(policy: Mapping[str, Any], time_s: float) -> float:
    """Return the target SPL at time_s with constant holds and linear-dB motion."""

    start = _float(policy.get("start_spl_db"), DEFAULT_START_SPL_DB)
    end = _float(policy.get("end_spl_db"), DEFAULT_END_SPL_DB)
    pre = max(0.0, _float(policy.get("pre_hold_s"), 0.5))
    movement = max(0.0, _float(policy.get("movement_duration_s"), 3.0))
    if time_s <= pre or movement <= 0:
        return start
    if time_s >= pre + movement:
        return end
    progress = (float(time_s) - pre) / movement
    return start + (end - start) * max(0.0, min(1.0, progress))


def relative_loudness_envelope(policy: Mapping[str, Any], samples: int, sample_rate: int) -> list[float]:
    """Build an endpoint-relative amplitude envelope for a rendered source."""

    endpoint = _float(policy.get("end_spl_db"), DEFAULT_END_SPL_DB)
    if samples <= 0 or sample_rate <= 0:
        return []
    return [
        db_to_linear(envelope_db_for_time(policy, index / float(sample_rate)) - endpoint)
        for index in range(samples)
    ]


def calibration_window_samples(policy: Mapping[str, Any], sample_rate: int, total_samples: int) -> tuple[int, int]:
    """Return the final active-movement calibration window, excluding holds."""

    pre = max(0.0, _float(policy.get("pre_hold_s"), 0.5))
    movement = max(0.0, _float(policy.get("movement_duration_s"), 3.0))
    window_s = max(0.05, _float(policy.get("calibration_window_s"), DEFAULT_CALIBRATION_WINDOW_S))
    active_end = pre + movement
    start_s = max(pre, active_end - window_s)
    stop_s = active_end
    start = max(0, min(total_samples, int(round(start_s * sample_rate))))
    stop = max(start + 1, min(total_samples, int(round(stop_s * sample_rate))))
    return start, stop


def calibration_window_target_rms_dbfs(policy: Mapping[str, Any], sample_rate: int, total_samples: int) -> float:
    """Return the intended RMS dBFS for the active calibration window.

    The endpoint target remains the final sample/post-hold level. Because the
    final active 500 ms is still ramping, its intended RMS is slightly below the
    endpoint hold RMS. Using the ramp-window target preserves the 55->75 dB
    endpoint relationship while matching the actual calibration window across
    noise types.
    """

    start, stop = calibration_window_samples(policy, sample_rate, total_samples)
    if stop <= start or sample_rate <= 0:
        return spl_to_rms_dbfs(policy, _float(policy.get("end_spl_db"), DEFAULT_END_SPL_DB))
    powers = [
        db_to_linear(spl_to_rms_dbfs(policy, envelope_db_for_time(policy, index / float(sample_rate)))) ** 2
        for index in range(start, stop)
    ]
    if not powers:
        return spl_to_rms_dbfs(policy, _float(policy.get("end_spl_db"), DEFAULT_END_SPL_DB))
    return linear_to_db(math.sqrt(sum(powers) / len(powers)))


def hold_window_samples(
    policy: Mapping[str, Any],
    sample_rate: int,
    total_samples: int,
    *,
    which: str,
) -> tuple[int, int]:
    pre = max(0.0, _float(policy.get("pre_hold_s"), 0.5))
    movement = max(0.0, _float(policy.get("movement_duration_s"), 3.0))
    post = max(0.0, _float(policy.get("post_hold_s"), 0.5))
    if which == "pre":
        start_s, stop_s = 0.0, pre
    elif which == "post":
        start_s, stop_s = pre + movement, pre + movement + post
    else:
        raise ValueError(f"Unsupported hold window: {which}")
    start = max(0, min(total_samples, int(round(start_s * sample_rate))))
    stop = max(start, min(total_samples, int(round(stop_s * sample_rate))))
    return start, stop


def loudness_protocol_warnings(policy: Mapping[str, Any] | None) -> list[str]:
    """Return participant-run warnings implied by the loudness policy."""

    normalized = normalize_loudness_policy(policy)
    hardware = normalized.get("hardware", {}) if isinstance(normalized.get("hardware"), Mapping) else {}
    warnings: list[str] = []
    calibration_status = str(normalized.get("calibration_status") or "").strip().lower()
    if calibration_status != "measured":
        warnings.append("SPL is estimated, not measured; verify with a headphone coupler/artificial ear before publication-grade SPL claims.")
    route = str(hardware.get("route") or "").strip()
    route_lower = route.lower()
    if "asio" not in route_lower or "komplete" not in route_lower:
        warnings.append(f"Loudness protocol expects ASIO / Komplete output; policy route is '{route or 'unspecified'}'.")
    interface = str(hardware.get("audio_interface") or "").strip()
    if "komplete audio 6" not in interface.lower():
        warnings.append(f"Loudness protocol expects Komplete Audio 6 MK2; policy interface is '{interface or 'unspecified'}'.")
    headphones = str(hardware.get("headphones") or "").strip()
    if "hd 560s" not in headphones.lower():
        warnings.append(f"Loudness protocol expects Sennheiser HD 560S; policy headphones are '{headphones or 'unspecified'}'.")
    knob = str(hardware.get("headphone_knob") or "").strip().lower()
    if "max" not in knob and "clockwise" not in knob:
        warnings.append("Komplete headphone volume knob should be fully clockwise for this loudness profile.")
    try:
        runner_volume = float(hardware.get("runner_audio_volume_percent"))
    except (TypeError, ValueError):
        runner_volume = float("nan")
    if not math.isfinite(runner_volume) or abs(runner_volume - 100.0) > 0.01:
        warnings.append(
            "Runner audio volume should be 100% for this loudness profile; "
            f"policy records {hardware.get('runner_audio_volume_percent', 'unspecified')}%."
        )
    windows_policy = str(hardware.get("windows_volume_policy") or "").strip().lower()
    if "not_part_of_asio_calibration" not in windows_policy:
        warnings.append("Windows/system volume should not be treated as part of the ASIO calibration path.")
    return warnings


def loudness_manifest_payload(
    policy: Mapping[str, Any] | None,
    *,
    created_at: str | None = None,
    participant_id: str = "",
    session_id: str = "",
    source_context: str = "",
    renderer_manifest_path: str = "",
    run_setup_manifest_path: str = "",
    source_wavs: list[Any] | None = None,
    stimulus_audit_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standalone loudness manifest shared by Segment 6 and sessions."""

    normalized = normalize_loudness_policy(policy)
    hardware = normalized.get("hardware", {}) if isinstance(normalized.get("hardware"), Mapping) else {}
    active_end = float(normalized.get("pre_hold_s", 0.5)) + float(normalized.get("movement_duration_s", 3.0))
    active_start = max(
        float(normalized.get("pre_hold_s", 0.5)),
        active_end - float(normalized.get("calibration_window_s", DEFAULT_CALIBRATION_WINDOW_S)),
    )
    return _json_ready(
        {
            "schema": LOUDNESS_MANIFEST_SCHEMA,
            "created_at": created_at or datetime.now().isoformat(timespec="seconds"),
            "source_context": source_context,
            "participant_id": participant_id,
            "session_id": session_id,
            "policy": normalized,
            "targets": {
                "start_spl_db": normalized.get("start_spl_db"),
                "endpoint_spl_db": normalized.get("end_spl_db"),
                "instruction_spl_db": normalized.get("instruction_target_spl_db"),
                "instruction_offset_db": normalized.get("instruction_offset_db"),
                "start_target_rms_dbfs": normalized.get("start_target_rms_dbfs"),
                "endpoint_target_rms_dbfs": normalized.get("end_target_rms_dbfs"),
                "instruction_target_rms_dbfs": normalized.get("instruction_target_rms_dbfs"),
            },
            "calibration": {
                "mode": normalized.get("calibration_mode"),
                "status": normalized.get("calibration_status"),
                "window": normalized.get("calibration_window"),
                "window_s": normalized.get("calibration_window_s"),
                "active_movement_window_s": [active_start, active_end],
                "excluded_padding_s": {
                    "pre_hold_s": normalized.get("pre_hold_s"),
                    "post_hold_s": normalized.get("post_hold_s"),
                },
                "estimated_full_scale_spl_db": normalized.get("estimated_full_scale_spl_db"),
                "estimate_basis": normalized.get("estimate_basis", {}),
            },
            "hardware_protocol": {
                "audio_interface": hardware.get("audio_interface", ""),
                "headphones": hardware.get("headphones", ""),
                "headphone_knob": hardware.get("headphone_knob", ""),
                "audio_route": hardware.get("route", ""),
                "runner_audio_volume_percent": hardware.get("runner_audio_volume_percent", ""),
                "windows_volume_policy": hardware.get("windows_volume_policy", ""),
            },
            "renderer": {
                "ramp_shape": normalized.get("movement_ramp_shape"),
                "hold_level_policy": normalized.get("hold_level_policy"),
                "normalization_status": "hidden_peak_normalization_disabled_in_loudness_control_mode",
                "peak_ceiling_dbfs": normalized.get("audio_peak_ceiling_dbfs"),
                "spatialization": normalized.get("renderer_role"),
                "distance_attenuation_policy": normalized.get("distance_gain_policy"),
                "threedti_authority": "3DTI supplies binaural/spatial cues; toolkit loudness policy controls final headphone SPL estimate.",
            },
            "inputs": {
                "renderer_manifest_path": renderer_manifest_path,
                "run_setup_manifest_path": run_setup_manifest_path,
                "source_wavs": source_wavs or [],
            },
            "stimulus_audit_summary": dict(stimulus_audit_summary or {}),
            "warnings": loudness_protocol_warnings(normalized),
        }
    )


def _deep_merge(defaults: Mapping[str, Any], incoming: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    keys = set(defaults) | set(incoming)
    for key in keys:
        default_value = defaults.get(key)
        incoming_value = incoming.get(key)
        if isinstance(default_value, Mapping) and isinstance(incoming_value, Mapping):
            merged[key] = _deep_merge(default_value, incoming_value)
        elif key in incoming:
            merged[key] = incoming_value
        else:
            merged[key] = default_value
    return merged


def _float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(parsed):
        return float(default)
    return parsed


def _choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip().lower()
    return text if text in allowed else default


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if hasattr(value, "__fspath__"):
        return str(value)
    return value
