"""3DTI-compatible design-rendering adapter.

The native 3DTI wrapper remains the renderer-of-record target. Until that
wrapper is packaged, the default `auto` path renders auditable WAVs with the
bundled Python SOFA/FABIAN reference engine from the same saved trajectory/SOA
configuration.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .design import (
    CUSTOM_AUDIO_NOISE_TYPE,
    DEFAULT_SOFA_FILE,
    PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS,
    PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
    StimulusDesign,
    gold_standard_looming_source_parameters,
    cartesian_to_spherical,
    design_from_dict,
    design_to_dict,
    protocol_factor_pairs,
    protocol_sound_sources,
    protocol_summary,
    trajectory_point_at_time,
    trajectory_points_with_holds,
)
from .loudness import (
    LOUDNESS_POLICY_KEY,
    calibration_window_target_rms_dbfs,
    calibration_window_samples,
    db_to_linear,
    linear_to_db,
    loudness_policy_for_design,
    normalize_loudness_policy,
    relative_loudness_envelope,
    rms_dbfs_to_estimated_spl,
)
from .runtime_paths import product_root, repo_root
from .subprocess_utils import windows_no_console_kwargs


REPO_ROOT = repo_root()
PRODUCT_ROOT = product_root()
THIRD_PARTY_3DTI_DIR = PRODUCT_ROOT / "third_party" / "3dti_AudioToolkit"
THREEDTI_REPOSITORY = "https://github.com/3DTune-In/3dti_AudioToolkit"
THREEDTI_COMMIT = "6bfee08705675308a8c348b4c3a4d582586d2f99"
THREEDTI_ARCHIVE_SHA256 = "a96038866bf9d86420c6f871e611b1888add245d2cc3307341fedcb41cef6b82"
DEFAULT_BACKEND_EXE = PRODUCT_ROOT / "third_party" / "3dti_renderer" / "bin" / "pps-3dti-renderer.exe"
DEFAULT_RENDER_SAMPLE_RATE = 44100
DEFAULT_RENDER_FRAME_MS = 20.0
DEFAULT_RENDER_HOP_MS = 5.0
DEFAULT_HEAD_DIAMETER_M = 0.18
DEFAULT_SOUND_SPEED_MPS = 343.0
THREEDTI_NEAR_FIELD_REFERENCE_DISTANCE_M = 1.95
THREEDTI_ANECHOIC_ATTENUATION_DB_PER_DISTANCE_DOUBLING = -6.0206
OUTPUT_AUDIO_PEAK_NORMALIZATION = 0.90
OUTPUT_LIMITER_PEAK = 0.99
RENDER_ENGINES = ("auto", "native-3dti", "python-sofa-reference")
STANDARD_HRTF_RESOURCE = {
    "id": "fabian_tu_berlin_hato_0",
    "label": "FABIAN neutral HRIR, HATO 0",
    "role": "fixed_standard_listener_hrir",
    "experimenter_visible": False,
    "license": "CC BY 4.0",
    "source_record": "TU Berlin / DepositOnce FABIAN neutral HRIR",
    "sofa_mirror": "https://sofacoustics.org/data/database/tu-berlin/FABIAN_HRIR_measured_HATO_0.sofa",
}


@dataclass
class RenderResult:
    status: str
    exit_code: int
    output_dir: Path
    config_path: Path
    manifest_path: Path
    qc_path: Path
    backend_executable: Path | None = None
    wav_paths: tuple[Path, ...] = ()
    tactile_events_path: Path | None = None


class RendererUnavailable(RuntimeError):
    pass


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repo_relative_path(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    if resolved.is_absolute():
        return resolved
    return REPO_ROOT / resolved


def resolve_backend_executable(path: Path | None = None) -> Path:
    if path is not None:
        return path
    env_path = os.environ.get("PPS_3DTI_RENDERER")
    if env_path:
        return Path(env_path)
    return DEFAULT_BACKEND_EXE


def app_to_3dti_coordinates(x_m: float, y_m: float, z_m: float) -> dict[str, float]:
    """Map PPS app coordinates into 3DTI's default Ambisonic axis convention."""
    return {
        "x_m": y_m,
        "y_m": -x_m,
        "z_m": z_m,
    }


def load_render_design(path: Path) -> StimulusDesign:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "template_id" in data and "design" in data:
        from .templates import template_from_dict

        return template_from_dict(data).design
    return design_from_dict(data)


def _noise_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in protocol_sound_sources(design):
        row = {
            "label": source["label"],
            "noise_type": source["noise_type"],
            "tone_type": source.get("tone_type", source["noise_type"]),
            "gain": source.get("gain", 1.0),
            "motion_mode": source.get("motion_mode", "looming"),
        }
        source_profile = source.get("source_profile", "")
        source_profile_parameters = source.get("source_profile_parameters", {})
        if source_profile:
            row["source_profile"] = source_profile
        if source_profile_parameters:
            row["source_profile_parameters"] = source_profile_parameters
        if source.get("source_path"):
            row["source_path"] = source.get("source_path", "")
        if source.get("prebaked_path"):
            row["prebaked_path"] = source.get("prebaked_path", "")
        if source["noise_type"] == CUSTOM_AUDIO_NOISE_TYPE:
            row.update(
                {
                    "source_kind": "imported_audio",
                    "path": source.get("source_path", ""),
                    "target_duration_s": source.get("target_duration_s", 0.0),
                    "source_render_mode": source.get("source_render_mode", "preserve"),
                }
            )
        rows.append(row)
    return rows


def _trajectory_profiled_noise_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    rows = _noise_rows(design)
    for row in rows:
        profile = str(row.get("source_profile", "")).strip()
        if (
            not profile
            and str(row.get("source_kind", "procedural_noise")) != "imported_audio"
            and str(row.get("motion_mode", "looming")).strip().lower() != "stationary"
        ):
            row["source_profile"] = PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
            row["source_profile_parameters"] = gold_standard_looming_source_parameters(
                row.get("source_profile_parameters") if isinstance(row.get("source_profile_parameters"), dict) else {}
            )
            profile = row["source_profile"]
        if profile.lower() != PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE:
            continue
        raw_parameters = dict(row.get("source_profile_parameters") or {})
        legacy_fixed_count = (
            "burst_count" in raw_parameters
            and "burst_count_mode" not in raw_parameters
            and "spacing_policy" not in raw_parameters
            and "active_window_s" not in raw_parameters
        )
        if legacy_fixed_count:
            row["source_profile_parameters"] = raw_parameters
            continue
        parameters = dict(PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS)
        if raw_parameters and "standard_basis" not in raw_parameters:
            parameters.pop("standard_basis", None)
        parameters.update(raw_parameters)
        if "active_window_s" in parameters:
            row["source_profile_parameters"] = parameters
            continue
        active_window_source = str(
            parameters.get(
                "active_window_source",
                PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS.get("active_window_source", "trajectory_movement_duration"),
            )
        )
        if active_window_source == "trajectory_movement_duration":
            parameters["active_window_s"] = float(design.trajectory.movement_duration_s)
            parameters["active_window_s_source"] = "trajectory.movement_duration_s"
        elif active_window_source == "trajectory_movement_window":
            onset_s = max(
                0.0,
                float(parameters.get("onset_s", PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS.get("onset_s", 0.0))),
            )
            movement_end_s = float(design.trajectory.padding_pre_s + design.trajectory.movement_duration_s)
            parameters["active_window_s"] = max(0.0, movement_end_s - onset_s)
            parameters["active_window_s_source"] = "trajectory.padding_pre_s + trajectory.movement_duration_s - onset_s"
        elif active_window_source == "trajectory_total_duration":
            parameters["active_window_s"] = float(design.trajectory.total_duration_s)
            parameters["active_window_s_source"] = "trajectory.total_duration_s"
        row["source_profile_parameters"] = parameters
    return rows


def _stimulus_assembly_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    fallback_order = 1
    for noise in design.noises:
        if not noise.label.strip():
            continue
        rows.append(
            {
                "component_kind": "generated_noise",
                "label": noise.label,
                "noise_type": noise.noise_type,
                "gain": noise.gain,
                "prebaked_path": noise.prebaked_path,
                "sequence_order": noise.sequence_order or fallback_order,
                "motion_mode": noise.motion_mode,
            }
        )
        fallback_order += 1
    for asset in design.custom_looming_files:
        if not asset.label.strip() and not asset.path.strip():
            continue
        rows.append(
            {
                "component_kind": "custom_audio",
                "label": asset.label,
                "path": asset.path,
                "target_duration_s": asset.target_duration_s,
                "tone_type": asset.tone_type,
                "gain": asset.gain,
                "sequence_order": asset.sequence_order or fallback_order,
                "motion_mode": asset.motion_mode,
                "source_render_mode": asset.render_mode,
            }
        )
        fallback_order += 1
    for asset in design.prestimulus_files:
        if not asset.label.strip() and not asset.path.strip():
            continue
        rows.append(
            {
                "component_kind": "instruction_snippet",
                "label": asset.label,
                "path": asset.path,
                "target_duration_s": asset.target_duration_s,
                "gain": asset.gain,
                "sequence_order": asset.sequence_order or fallback_order,
                "motion_mode": asset.motion_mode,
                "placement": asset.placement,
                "target_source_label": asset.target_source_label,
                "phase": asset.phase,
                "gap_s": asset.gap_s,
                "source_render_mode": asset.render_mode,
            }
        )
        fallback_order += 1
    return sorted(rows, key=lambda item: (int(item.get("sequence_order", 0) or 0), str(item.get("label", ""))))


def _stimulus_snippet_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    return [
        row
        for row in _stimulus_assembly_rows(design)
        if row.get("component_kind") == "instruction_snippet"
    ]


def _source_motion_mode(config: dict[str, Any], source: dict[str, Any]) -> str:
    label = str(source.get("label", ""))
    for component in config["source"].get("stimulus_assembly", {}).get("components", []):
        if component.get("label") == label and component.get("component_kind") in {"generated_noise", "custom_audio"}:
            return "stationary" if component.get("motion_mode") == "stationary" else "looming"
    return "looming"


def _listener_head_diameter_m(design: StimulusDesign) -> float:
    value = design.study_profile_reference_parameters.get("head_diameter_m", DEFAULT_HEAD_DIAMETER_M)
    try:
        head_diameter = float(value)
    except (TypeError, ValueError):
        head_diameter = DEFAULT_HEAD_DIAMETER_M
    return head_diameter if head_diameter > 0 else DEFAULT_HEAD_DIAMETER_M


def _head_model_source(design: StimulusDesign) -> str:
    if "head_diameter_m" in design.study_profile_reference_parameters:
        profile = design.study_profile_id or design.study_profile_title or "study_profile"
        return f"{profile}.reference_parameters.head_diameter_m"
    return "toolkit_default_head_diameter_m"


def _tactile_events(design: StimulusDesign) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for soa_ms, spatial_cm in protocol_factor_pairs(design.protocol):
        source_at_tactile = trajectory_point_at_time(design.trajectory, soa_ms / 1000.0)
        events.append(
            {
                "trial_type": "Audio-Tactile",
                "soa_ms": soa_ms,
                "tactile_onset_s": soa_ms / 1000.0,
                "planned_spatial_value_cm": spatial_cm,
                "source_radius_at_tactile_cm": source_at_tactile["radius_m"] * 100.0,
                "source_x_at_tactile_m": source_at_tactile["x_m"],
                "source_y_at_tactile_m": source_at_tactile["y_m"],
                "source_z_at_tactile_m": source_at_tactile["z_m"],
                "trajectory_phase_at_tactile": source_at_tactile["phase"],
            }
        )
    return events


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return slug or "stimulus"


def _expected_wav_paths(config: dict[str, Any], output_dir: Path) -> list[Path]:
    return [output_dir / f"looming_{_slug(noise['label'])}.wav" for noise in config["source"]["noises"]]


def _generate_noise(noise_type: str, samples: int, sample_rate: int, seed: int) -> "Any":
    import numpy as np

    rng = np.random.default_rng(seed)
    white = rng.standard_normal(samples)
    noise = noise_type.lower()
    if noise == "white":
        result = white
    elif noise == "pink":
        spectrum = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(samples, 1.0 / sample_rate)
        freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
        result = np.fft.irfft(spectrum / np.sqrt(freqs), n=samples)
    elif noise == "blue":
        spectrum = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(samples, 1.0 / sample_rate)
        freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
        result = np.fft.irfft(spectrum * np.sqrt(freqs), n=samples)
    elif noise == "violet":
        spectrum = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(samples, 1.0 / sample_rate)
        freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
        result = np.fft.irfft(spectrum * freqs, n=samples)
    elif noise == "brown":
        result = np.cumsum(white)
    else:
        raise ValueError(f"Unsupported noise type: {noise_type}")
    peak = float(np.max(np.abs(result))) if samples else 0.0
    return result / peak if peak > 0 else result


def _raised_cosine_edge(length: int, edge: int) -> "Any":
    import numpy as np

    envelope = np.ones(length, dtype=float)
    if length <= 0 or edge <= 0:
        return envelope
    edge = min(edge, max(1, length // 2))
    phase = np.linspace(0.0, np.pi, edge, endpoint=False)
    attack = 0.5 - 0.5 * np.cos(phase)
    envelope[:edge] = attack
    envelope[-edge:] = attack[::-1]
    return envelope


def _profile_float(params: dict[str, Any], defaults: dict[str, Any], key: str, fallback: float) -> float:
    value = params.get(key, defaults.get(key, fallback))
    if value is None:
        value = fallback
    return float(value)


def _dynaspace_burst_onsets(
    *,
    samples: int,
    sample_rate: int,
    parameters: dict[str, Any] | None = None,
) -> tuple[list[float], dict[str, Any]]:
    params = parameters if isinstance(parameters, dict) else {}
    defaults = PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS
    burst_duration_s = max(0.001, _profile_float(params, defaults, "burst_duration_s", 0.030))
    rise_fall_s = max(0.0, _profile_float(params, defaults, "rise_fall_s", 0.010))
    requested_onset_s = max(0.0, _profile_float(params, defaults, "onset_s", 0.300))
    if "target_period_s" in params:
        target_period_s = max(0.001, float(params["target_period_s"]))
    elif "inter_burst_interval_s" in params:
        inter_burst_interval_s = max(0.0, float(params["inter_burst_interval_s"]))
        target_period_s = burst_duration_s + inter_burst_interval_s
    elif "target_period_s" in defaults:
        target_period_s = max(0.001, _profile_float(params, defaults, "target_period_s", 0.095))
    else:
        inter_burst_interval_s = max(0.0, _profile_float(params, defaults, "inter_burst_interval_s", 0.065))
        target_period_s = burst_duration_s + inter_burst_interval_s
    total_duration_s = samples / float(sample_rate)
    burst_fit_duration_s = min(burst_duration_s, total_duration_s) if total_duration_s > 0 else 0.0
    latest_audible_onset_s = max(0.0, total_duration_s - burst_fit_duration_s)
    onset_s = min(requested_onset_s, latest_audible_onset_s)
    end_margin_s = max(0.0, _profile_float(params, defaults, "end_margin_s", 0.0))
    active_window_value = params.get("active_window_s", defaults.get("active_window_s"))
    if active_window_value is None:
        active_window_s = max(0.0, total_duration_s - onset_s - end_margin_s)
    else:
        active_window_s = max(0.0, float(active_window_value))
        active_window_s = min(active_window_s, max(0.0, total_duration_s - onset_s))

    legacy_fixed_period = (
        "burst_count" in params
        and "burst_count_mode" not in params
        and "spacing_policy" not in params
        and "active_window_s" not in params
    )
    burst_count_mode = (
        str(params.get("burst_count_mode", defaults.get("burst_count_mode", "duration_derived"))).strip().lower()
    )
    if "burst_count" in params and "burst_count_mode" not in params:
        burst_count_mode = "fixed"
    spacing_policy = (
        str(params.get("spacing_policy", defaults.get("spacing_policy", "symmetric_fit"))).strip().lower()
    )
    if legacy_fixed_period:
        spacing_policy = "fixed_period_truncate"

    if spacing_policy == "fixed_period_truncate":
        burst_count = max(1, int(params.get("burst_count", defaults.get("burst_count", 1))))
        onsets = [onset_s + index * target_period_s for index in range(burst_count)]
        onsets = [value for value in onsets if value < total_duration_s]
        resolved = {
            "burst_count": len(onsets),
            "burst_duration_s": burst_duration_s,
            "rise_fall_s": rise_fall_s,
            "target_period_s": target_period_s,
            "actual_period_s": target_period_s if len(onsets) > 1 else 0.0,
            "onset_s": onset_s,
            "active_window_s": active_window_s,
            "spacing_policy": spacing_policy,
            "burst_count_mode": burst_count_mode,
        }
        if requested_onset_s != onset_s:
            resolved["requested_onset_s"] = requested_onset_s
            resolved["onset_fit_policy"] = "clamped_to_available_duration"
        return onsets, resolved

    span_s = max(0.0, active_window_s - burst_duration_s)
    if burst_count_mode in {"fixed", "explicit"} and "burst_count" in params:
        burst_count = max(1, int(params["burst_count"]))
    else:
        periods = int(math.floor((span_s / target_period_s) + 0.5)) if target_period_s > 0 and span_s > 0 else 0
        burst_count = max(1, periods + 1)

    allow_overlap = bool(params.get("allow_burst_overlap", defaults.get("allow_burst_overlap", False)))
    if not allow_overlap and burst_count > 1 and span_s > 0:
        minimum_period_s = max(
            burst_duration_s,
            float(params.get("minimum_period_s", defaults.get("minimum_period_s", burst_duration_s))),
        )
        max_without_overlap = max(1, int(math.floor(span_s / minimum_period_s)) + 1)
        burst_count = min(burst_count, max_without_overlap)

    if burst_count <= 1:
        onsets = [onset_s + (span_s * 0.5)]
        actual_period_s = 0.0
    else:
        actual_period_s = span_s / float(burst_count - 1)
        onsets = [onset_s + index * actual_period_s for index in range(burst_count)]

    onsets = [value for value in onsets if value < total_duration_s]
    resolved = {
        "burst_count": len(onsets),
        "burst_duration_s": burst_duration_s,
        "rise_fall_s": rise_fall_s,
        "target_period_s": target_period_s,
        "actual_period_s": actual_period_s,
        "onset_s": onset_s,
        "active_window_s": active_window_s,
        "spacing_policy": spacing_policy,
        "burst_count_mode": burst_count_mode,
    }
    if requested_onset_s != onset_s:
        resolved["requested_onset_s"] = requested_onset_s
        resolved["onset_fit_policy"] = "clamped_to_available_duration"
    return onsets, resolved


def _generate_dynaspace_burst_train(
    noise_type: str,
    samples: int,
    sample_rate: int,
    seed: int,
    parameters: dict[str, Any] | None = None,
) -> "Any":
    import numpy as np

    params = parameters if isinstance(parameters, dict) else {}
    burst_onsets_s, resolved = _dynaspace_burst_onsets(samples=samples, sample_rate=sample_rate, parameters=params)
    burst_duration_s = float(resolved["burst_duration_s"])
    rise_fall_s = float(resolved["rise_fall_s"])
    source = np.zeros(samples, dtype=float)
    burst_samples = max(1, int(round(burst_duration_s * sample_rate)))
    edge_samples = int(round(rise_fall_s * sample_rate))
    envelope = _raised_cosine_edge(burst_samples, edge_samples)

    for index, burst_onset_s in enumerate(burst_onsets_s):
        start = int(round(burst_onset_s * sample_rate))
        stop = min(samples, start + burst_samples)
        if stop <= start:
            continue
        burst = _generate_noise(noise_type, stop - start, sample_rate, seed + index * 37)
        source[start:stop] += burst * envelope[: stop - start]

    peak = float(np.max(np.abs(source))) if samples else 0.0
    return source / peak if peak > 0 else source


def _generate_procedural_source(source: dict[str, Any], samples: int, sample_rate: int, seed: int) -> "Any":
    profile = str(source.get("source_profile") or "").strip().lower()
    if profile in {"", "continuous_noise", "procedural_noise"}:
        return _generate_noise(source["noise_type"], samples, sample_rate, seed)
    if profile == PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE:
        return _generate_dynaspace_burst_train(
            source["noise_type"],
            samples,
            sample_rate,
            seed,
            source.get("source_profile_parameters"),
        )
    raise ValueError(f"Unsupported source profile: {source.get('source_profile')}")


def _loudness_control_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("renderer", {}).get("level_model", {}).get("toolkit_loudness_control_enabled"))


def _rms_dbfs(data: "Any") -> float:
    import numpy as np

    if data is None or not len(data):
        return float("-inf")
    rms = float(np.sqrt(np.mean(np.asarray(data, dtype=float) ** 2)))
    return linear_to_db(rms)


def _apply_loudness_envelope(data: "Any", policy: dict[str, Any], sample_rate: int) -> "Any":
    import numpy as np

    envelope = np.asarray(relative_loudness_envelope(policy, len(data), sample_rate), dtype=float)
    if data.ndim == 1:
        return data * envelope
    return data * envelope[:, None]


def _stereo_rms_dbfs(stereo: "Any", start: int, stop: int) -> float:
    window = stereo[start:stop, :]
    if not len(window):
        return float("-inf")
    return _rms_dbfs(window)


def _apply_calibrated_loudness_target(
    stereo: "Any",
    policy: dict[str, Any],
    sample_rate: int,
    total_samples: int,
) -> tuple["Any", dict[str, Any]]:
    import numpy as np

    start, stop = calibration_window_samples(policy, sample_rate, total_samples)
    final_window = stereo[start:stop, :]
    measured_rms = float(np.sqrt(np.mean(final_window * final_window))) if len(final_window) else 0.0
    target_rms_dbfs = calibration_window_target_rms_dbfs(policy, sample_rate, total_samples)
    target_rms = db_to_linear(target_rms_dbfs)
    if measured_rms <= 0:
        raise RuntimeError("Cannot apply calibrated loudness target: active calibration window is silent.")
    gain = target_rms / measured_rms
    scaled = stereo * gain
    audio_peak = float(np.max(np.abs(scaled))) if scaled.size else 0.0
    audio_peak_dbfs = linear_to_db(audio_peak)
    ceiling_dbfs = float(policy.get("audio_peak_ceiling_dbfs", -1.0))
    if audio_peak_dbfs > ceiling_dbfs:
        raise RuntimeError(
            "Calibrated loudness render would exceed the audio peak ceiling "
            f"({audio_peak_dbfs:.3f} dBFS > {ceiling_dbfs:.3f} dBFS)."
        )
    pre_start = 0
    pre_stop = max(0, min(total_samples, int(round(float(policy.get("pre_hold_s", 0.5)) * sample_rate))))
    post_start = max(0, min(total_samples, int(round((float(policy.get("pre_hold_s", 0.5)) + float(policy.get("movement_duration_s", 3.0))) * sample_rate))))
    post_stop = max(post_start, min(total_samples, int(round(float(policy.get("total_duration_s", total_samples / sample_rate)) * sample_rate))))
    final_rms_dbfs = _stereo_rms_dbfs(scaled, start, stop)
    metadata = {
        "loudness_control": "toolkit_estimated_spl",
        "loudness_ramp_shape": str(policy.get("movement_ramp_shape", "linear_db")),
        "loudness_start_spl_db": f"{float(policy['start_spl_db']):.3f}",
        "loudness_end_spl_db": f"{float(policy['end_spl_db']):.3f}",
        "loudness_target_start_rms_dbfs": f"{float(policy['start_target_rms_dbfs']):.3f}",
        "loudness_target_end_rms_dbfs": f"{float(policy['end_target_rms_dbfs']):.3f}",
        "loudness_calibration_window_role": "final_active_movement_excluding_trajectory_padding",
        "loudness_calibration_window_target_rms_dbfs": f"{target_rms_dbfs:.3f}",
        "loudness_final_window_start_s": f"{start / sample_rate:.6f}",
        "loudness_final_window_stop_s": f"{stop / sample_rate:.6f}",
        "loudness_pre_hold_rms_dbfs": f"{_stereo_rms_dbfs(scaled, pre_start, pre_stop):.3f}",
        "loudness_final_window_rms_dbfs": f"{final_rms_dbfs:.3f}",
        "loudness_post_hold_rms_dbfs": f"{_stereo_rms_dbfs(scaled, post_start, post_stop):.3f}",
        "loudness_final_window_estimated_spl_db": f"{rms_dbfs_to_estimated_spl(policy, final_rms_dbfs):.3f}",
        "loudness_applied_gain_db": f"{linear_to_db(gain):.3f}",
        "loudness_audio_peak_dbfs": f"{audio_peak_dbfs:.3f}",
        "loudness_peak_ceiling_dbfs": f"{ceiling_dbfs:.3f}",
        "loudness_peak_status": "within_ceiling",
    }
    return scaled, metadata


def _has_imported_audio_sources(config: dict[str, Any]) -> bool:
    return any(source.get("source_kind") == "imported_audio" for source in config["source"]["noises"])


def _read_imported_audio_source(source: dict[str, Any], sample_rate: int, total_samples: int) -> tuple["Any", int, int]:
    import numpy as np
    import soundfile as sf
    from scipy import signal

    path = repo_relative_path(str(source.get("path", "")))
    data, source_rate = sf.read(str(path), dtype="float32", always_2d=True)
    source_channels = int(data.shape[1])
    if source_rate != sample_rate:
        divisor = math.gcd(int(source_rate), int(sample_rate))
        data = signal.resample_poly(data, sample_rate // divisor, source_rate // divisor, axis=0)
    if len(data) > total_samples:
        data = data[:total_samples, :]
    elif len(data) < total_samples:
        padding = np.zeros((total_samples - len(data), data.shape[1]), dtype=data.dtype)
        data = np.concatenate([data, padding], axis=0)
    return data, int(source_rate), source_channels


def _render_imported_audio_source(
    source: dict[str, Any],
    *,
    config: dict[str, Any],
    tactile: "Any | None",
    output_dir: Path,
    sample_rate: int,
    total_samples: int,
) -> tuple[Path, dict[str, Any]]:
    import numpy as np
    import soundfile as sf

    data, source_rate, source_channels = _read_imported_audio_source(source, sample_rate, total_samples)
    if data.shape[1] == 1:
        stereo = np.column_stack([data[:, 0], data[:, 0]])
    elif data.shape[1] == 2:
        stereo = data[:, :2]
    else:
        stereo = data[:, :2]
    gain = float(source.get("gain", 1.0) or 1.0)
    loudness_metadata: dict[str, Any] = {}
    if _loudness_control_enabled(config):
        policy = config["loudness_policy"]
        stereo = _apply_loudness_envelope(stereo * gain, policy, sample_rate)
        stereo, loudness_metadata = _apply_calibrated_loudness_target(stereo, policy, sample_rate, total_samples)
        gain = 1.0
    include_tactile = bool(config["tactile"].get("enabled", True))
    if include_tactile:
        tactile_channel = data[:, 2] if data.shape[1] > 2 else tactile
        if tactile_channel is None:
            tactile_channel = np.zeros(total_samples, dtype=stereo.dtype)
        rendered = np.column_stack([stereo * gain, tactile_channel])
    else:
        rendered = stereo * gain
    peak = float(np.max(np.abs(rendered))) if rendered.size else 0.0
    if peak > OUTPUT_LIMITER_PEAK and not _loudness_control_enabled(config):
        rendered = rendered / peak * OUTPUT_LIMITER_PEAK
        peak = float(np.max(np.abs(rendered)))
    audio_peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    wav_path = output_dir / f"looming_{_slug(source['label'])}.wav"
    sf.write(wav_path, rendered, sample_rate, subtype="PCM_16")
    peak_for_qc = audio_peak if _loudness_control_enabled(config) else peak
    peak_dbfs = "-inf" if peak_for_qc <= 0 else f"{20.0 * math.log10(peak_for_qc):.3f}"
    return wav_path, {
        "status": "rendered_imported_audio",
        "noise_label": source["label"],
        "noise_type": source["noise_type"],
        "source_kind": "imported_audio",
        "source_render_mode": source.get("source_render_mode", "preserve"),
        "source_path": str(repo_relative_path(str(source.get("path", "")))),
        "source_sample_rate": source_rate,
        "source_channels": source_channels,
        "duration_s": f"{total_samples / sample_rate:.6f}",
        "sample_rate": sample_rate,
        "channels": 3 if include_tactile else 2,
        "tactile_events": len(config["tactile"]["events"]),
        "tactile_channel": 2 if include_tactile else "",
        "peak_dbfs": peak_dbfs,
        "clipping": str(peak_for_qc >= 1.0).lower(),
        "hrir_positions_used": "",
        "first_half_left_rms": "",
        "first_half_right_rms": "",
        "second_half_left_rms": "",
        "second_half_right_rms": "",
        **loudness_metadata,
        "wav_sha256": sha256_file(wav_path) or "",
        "message": (
            "Imported local audio source rendered as binaural left/right"
            + (
                " plus tactile. Mono files are duplicated to both ears; stereo files receive the toolkit tactile channel; files with 3+ channels preserve channel 3 as tactile."
                if include_tactile
                else " only. Tactile assembly is deferred until the run/session preparation stage."
            )
        ),
    }


def _imported_audio_mono_source(source: dict[str, Any], sample_rate: int, total_samples: int) -> tuple["Any", int, int]:
    import numpy as np

    data, source_rate, source_channels = _read_imported_audio_source(source, sample_rate, total_samples)
    if data.shape[1] == 1:
        dry = data[:, 0]
    else:
        dry = np.mean(data[:, :2], axis=1)
    return dry, source_rate, source_channels


def _load_sofa_hrirs(sofa_file: str) -> dict[str, Any]:
    import numpy as np

    path = repo_relative_path(sofa_file)
    try:
        from netCDF4 import Dataset

        with Dataset(path, "r") as sofa:
            positions = np.asarray(sofa.variables["SourcePosition"][:], dtype=float)
            hrirs = np.asarray(sofa.variables["Data.IR"][:], dtype=float)
            sample_rate = int(round(float(np.asarray(sofa.variables["Data.SamplingRate"][:]).ravel()[0])))
    except Exception:
        import sofar

        sofa = sofar.read_sofa(str(path))
        positions = np.asarray(sofa.SourcePosition, dtype=float)
        hrirs = np.asarray(sofa.Data_IR, dtype=float)
        sample_rate = int(round(float(sofa.Data_SamplingRate)))
    if positions.shape[0] == 3 and positions.ndim == 2:
        positions = positions.T
    return {
        "positions": positions,
        "hrirs": hrirs,
        "sample_rate": sample_rate,
    }


def _nearest_hrir_index(positions: "Any", app_azimuth_deg: float, elevation_deg: float) -> int:
    import numpy as np

    sofa_azimuth = (-app_azimuth_deg) % 360.0
    azimuth_delta = ((positions[:, 0] - sofa_azimuth + 180.0) % 360.0) - 180.0
    elevation_delta = positions[:, 1] - elevation_deg
    distance = azimuth_delta**2 + elevation_delta**2
    return int(np.argmin(distance))


def _sample_from_config(config: dict[str, Any], time_s: float) -> dict[str, float]:
    samples = config["trajectory"]["samples"]
    if not samples:
        return {"x_m": 0.0, "y_m": 1.0, "z_m": 0.0, "radius_m": 1.0}
    target = min(samples, key=lambda item: abs(float(item["time_s"]) - time_s))
    return {
        "x_m": float(target["x_m"]),
        "y_m": float(target["y_m"]),
        "z_m": float(target["z_m"]),
        "radius_m": float(target["radius_m"]),
    }


def _tactile_waveform(config: dict[str, Any], sample_rate: int) -> "Any":
    import numpy as np

    spec = config["tactile"]["waveform"]
    duration_s = float(spec["duration_s"])
    samples = max(1, int(round(duration_s * sample_rate)))
    t = np.arange(samples, dtype=float) / sample_rate
    attack_samples = max(1, min(samples, int(round(0.02 * sample_rate))))
    waveform = np.empty(samples, dtype=float)
    waveform[:attack_samples] = np.sin(2 * np.pi * float(spec["attack_frequency_hz"]) * t[:attack_samples])
    waveform[attack_samples:] = np.sin(2 * np.pi * float(spec["decay_frequency_hz"]) * t[attack_samples:])
    envelope = np.hanning(max(4, samples * 2))[:samples]
    if len(envelope) != samples:
        envelope = np.ones(samples, dtype=float)
    waveform *= envelope
    peak = float(np.max(np.abs(waveform)))
    if peak > 0:
        waveform = waveform / peak * float(spec.get("peak_normalization", 0.95))
    return waveform


def _add_tactile_channel(config: dict[str, Any], sample_rate: int, samples: int) -> "Any":
    import numpy as np

    channel = np.zeros(samples, dtype=float)
    cue = _tactile_waveform(config, sample_rate)
    for event in config["tactile"]["events"]:
        onset = int(round(float(event["tactile_onset_s"]) * sample_rate))
        if onset >= samples:
            continue
        end = min(samples, onset + len(cue))
        if end > onset:
            channel[onset:end] += cue[: end - onset]
    peak = float(np.max(np.abs(channel))) if samples else 0.0
    if peak > 1.0:
        channel /= peak
    return channel


def _spatialize_moving_source(
    dry: "Any",
    source: dict[str, Any],
    *,
    config: dict[str, Any],
    sofa: dict[str, Any],
    sample_rate: int,
    total_samples: int,
    frame_samples: int,
    hop_samples: int,
    window: "Any",
) -> tuple["Any", set[int]]:
    import numpy as np
    from scipy import signal

    hrir_len = int(sofa["hrirs"].shape[-1])
    stereo = np.zeros((total_samples + hrir_len + frame_samples, 2), dtype=float)
    used_hrir_indices: set[int] = set()
    stationary_point = _sample_from_config(config, 0.0) if _source_motion_mode(config, source) == "stationary" else None

    for start in range(0, total_samples, hop_samples):
        stop = min(total_samples, start + frame_samples)
        valid = stop - start
        if valid <= 0:
            continue
        frame = np.zeros(frame_samples, dtype=float)
        frame[:valid] = dry[start:stop]
        center_time = (start + valid / 2.0) / sample_rate
        point = stationary_point or _sample_from_config(config, center_time)
        spherical = cartesian_to_spherical(point["x_m"], point["y_m"], point["z_m"])
        hrir_index = _nearest_hrir_index(
            sofa["positions"],
            spherical["azimuth_deg"],
            spherical["elevation_deg"],
        )
        used_hrir_indices.add(hrir_index)
        radius = max(float(point["radius_m"]), 0.05)
        distance_gain = 1.0 / radius if config["source"].get("gain_law") else 1.0
        frame *= window * float(source.get("gain", 1.0)) * distance_gain
        left = signal.fftconvolve(frame, sofa["hrirs"][hrir_index, 0, :], mode="full")
        right = signal.fftconvolve(frame, sofa["hrirs"][hrir_index, 1, :], mode="full")
        end = start + len(left)
        stereo[start:end, 0] += left
        stereo[start:end, 1] += right

    stereo = stereo[:total_samples, :]
    audio_peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
    if audio_peak > 0 and not _loudness_control_enabled(config):
        stereo = stereo / audio_peak * OUTPUT_AUDIO_PEAK_NORMALIZATION
    return stereo, used_hrir_indices


def build_render_config(
    design: StimulusDesign,
    *,
    seed: int,
    output_dir: Path,
    samples_per_second: float = 200.0,
    sample_rate: int = DEFAULT_RENDER_SAMPLE_RATE,
    include_tactile: bool = True,
) -> dict[str, Any]:
    trajectory_samples = trajectory_points_with_holds(design.trajectory, samples_per_second=samples_per_second)
    sofa_file = design.sofa_file or DEFAULT_SOFA_FILE
    sofa_path = repo_relative_path(sofa_file)
    head_diameter_m = _listener_head_diameter_m(design)
    head_radius_m = head_diameter_m / 2.0
    sources = _trajectory_profiled_noise_rows(design)
    imported_source_count = sum(1 for source in sources if source.get("source_kind") == "imported_audio")
    tactile_events = _tactile_events(design) if include_tactile else []
    reference_parameters = design.study_profile_reference_parameters if isinstance(design.study_profile_reference_parameters, dict) else {}
    raw_loudness_policy = reference_parameters.get(LOUDNESS_POLICY_KEY)
    loudness_control_enabled = isinstance(raw_loudness_policy, dict)
    loudness_policy = loudness_policy_for_design(design)
    output_peak_normalization = None if loudness_control_enabled else OUTPUT_AUDIO_PEAK_NORMALIZATION
    return {
        "schema": "pps-3dti-render-config.v1",
        "loudness_policy": loudness_policy,
        "renderer": {
            "backend": "3DTI AudioToolkit",
            "repository": THREEDTI_REPOSITORY,
            "commit": THREEDTI_COMMIT,
            "source_snapshot_path": str(THIRD_PARTY_3DTI_DIR.as_posix()),
            "source_archive_sha256": THREEDTI_ARCHIVE_SHA256,
            "frame_ms": DEFAULT_RENDER_FRAME_MS,
            "hop_ms": DEFAULT_RENDER_HOP_MS,
            "spatialization_mode": "HighQuality",
            "acoustic_model": {
                "hrir_lookup": "SOFA/FABIAN direction lookup on the measured HRTF sphere",
                "distance_model": "3DTI direct-path distance attenuation plus near-field ILD/shadow filtering",
                "customized_itd": True,
                "propagation_delay": True,
                "sound_speed_mps": DEFAULT_SOUND_SPEED_MPS,
                "near_field_reference_distance_m": THREEDTI_NEAR_FIELD_REFERENCE_DISTANCE_M,
                "anechoic_attenuation_db_per_distance_doubling": (
                    THREEDTI_ANECHOIC_ATTENUATION_DB_PER_DISTANCE_DOUBLING
                ),
                "distance_attenuation_smoothing": True,
                "reverb_enabled": False,
            },
            "level_model": {
                "toolkit_loudness_control_enabled": loudness_control_enabled,
                "noise_gain_unit": (
                    "linear_source_precalibration_multiplier"
                    if loudness_control_enabled
                    else "linear_amplitude_multiplier"
                ),
                "noise_gain_default": 1.0,
                "absolute_spl_estimated": loudness_control_enabled
                and loudness_policy.get("mode") == "estimated_spl",
                "absolute_spl_calibrated": loudness_control_enabled
                and loudness_policy.get("calibration_status") == "measured",
                "loudness_policy": loudness_policy,
                "output_audio_peak_normalization": output_peak_normalization,
                "output_audio_peak_normalization_dbfs": (
                    None if output_peak_normalization is None else 20.0 * math.log10(output_peak_normalization)
                ),
                "output_limiter_peak": OUTPUT_LIMITER_PEAK,
                "output_limiter_peak_dbfs": 20.0 * math.log10(OUTPUT_LIMITER_PEAK),
                "note": (
                    "In loudness-control mode, the toolkit applies a constant-hold linear-dB envelope and "
                    "matches the final active-movement calibration window RMS to the intended ramp-window target; "
                    "hidden audio peak normalization is disabled. Legacy designs without a loudness policy retain "
                    "peak normalization."
                ),
            },
        },
        "coordinate_convention": {
            "app": "X right positive, Y front positive, Z up positive",
            "3dti_default": "X front positive, Y left positive, Z up positive",
            "adapter_mapping": {
                "3dti_x_m": "app_y_m",
                "3dti_y_m": "-app_x_m",
                "3dti_z_m": "app_z_m",
            },
            "adapter_responsibility": "Map app coordinates into 3DTI source/listener coordinates before calling SetSourceTransform.",
        },
        "listener": {
            "stationary": True,
            "x_m": 0.0,
            "y_m": 0.0,
            "z_m": 0.0,
            "head_diameter_m": head_diameter_m,
            "head_radius_m": head_radius_m,
            "head_model_source": _head_model_source(design),
        },
        "source": {
            "type": "mixed_procedural_and_imported" if imported_source_count and len(sources) > imported_source_count else ("imported_audio" if imported_source_count else "generated_noise"),
            "seed": seed,
            "sample_rate": sample_rate,
            "noises": sources,
            "imported_audio_count": imported_source_count,
            "stimulus_assembly": {
                "components": _stimulus_assembly_rows(design),
                "snippets": _stimulus_snippet_rows(design),
                "integration": "recorded_for_session_assembly",
            },
            "gain_law": False if loudness_control_enabled else "3DTI_free_field_direct_path",
            "distance_gain_policy": (
                loudness_policy.get("distance_gain_policy")
                if loudness_control_enabled
                else "3DTI_free_field_direct_path"
            ),
            "sofa_file": sofa_file,
            "sofa_file_sha256": sha256_file(sofa_path),
            "hrtf_resource": {
                **STANDARD_HRTF_RESOURCE,
                "sofa_file": sofa_file,
                "sofa_file_sha256": sha256_file(sofa_path),
            },
        },
        "study_profile": {
            "id": design.study_profile_id,
            "title": design.study_profile_title,
            "notes": design.study_profile_notes,
            "reference_parameters": design.study_profile_reference_parameters,
        },
        "tactile": {
            "enabled": bool(include_tactile),
            "stage": "experiment_render" if include_tactile else "deferred_until_session_preparation",
            "soa_reference": "stimulus_window_onset_s",
            "output_layout": "multichannel_binaural_plus_tactile" if include_tactile else "binaural_auditory_only",
            "channels": {
                "0": "binaural_left",
                "1": "binaural_right",
                **({"2": "vibrotactile"} if include_tactile else {}),
            },
            "legacy_two_channel_layout": {
                "supported_for_study5_replication_only": True,
                "channels": {
                    "0": "vibrotactile",
                    "1": "mono_or_single_ear_looming",
                },
            },
            "waveform": {
                "type": "two_component_vibrotactile_sinusoid",
                "duration_s": 0.1,
                "attack_frequency_hz": 200,
                "decay_frequency_hz": 50,
                "attack_db": 4,
                "decay_db": -22,
                "peak_normalization": 0.95,
            },
            "events": tactile_events,
        },
        "protocol": {
            "summary": protocol_summary(design),
            "soa_values_ms": design.protocol.soa_values_ms,
            "spatial_values_cm": design.protocol.spatial_values_cm,
            "pair_spatial_values_with_soas": design.protocol.pair_spatial_values_with_soas,
            "tactile_sites": design.protocol.tactile_sites,
            "respiratory_phases": design.protocol.respiratory_phases,
            "trial_randomization_strategy": design.protocol.trial_randomization_strategy,
            "block_order_randomization": design.protocol.block_order_randomization,
            "random_seed": design.protocol.random_seed,
        },
        "trajectory": {
            "mode": "linear_cartesian_with_endpoint_holds",
            "start_hold_s": design.trajectory.padding_pre_s,
            "movement_duration_s": design.trajectory.movement_duration_s,
            "end_hold_s": design.trajectory.padding_post_s,
            "total_duration_s": design.trajectory.total_duration_s,
            "samples_per_second": samples_per_second,
            "samples": trajectory_samples,
        },
        "outputs": {
            "output_dir": str(output_dir),
            "expected_wav_pattern": "looming_{noise_label}.wav",
            "manifest": "render_manifest.json",
            "qc_csv": "render_qc.csv",
            "tactile_events_csv": "render_tactile_events.csv",
        },
        "design": design_to_dict(design),
    }


def write_render_qc(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "status",
        "noise_label",
        "noise_type",
        "source_profile",
        "source_profile_parameters",
        "source_kind",
        "source_render_mode",
        "source_path",
        "source_sample_rate",
        "source_channels",
        "duration_s",
        "sample_rate",
        "channels",
        "tactile_events",
        "tactile_channel",
        "peak_dbfs",
        "clipping",
        "hrir_positions_used",
        "first_half_left_rms",
        "first_half_right_rms",
        "second_half_left_rms",
        "second_half_right_rms",
        "loudness_control",
        "loudness_ramp_shape",
        "loudness_start_spl_db",
        "loudness_end_spl_db",
        "loudness_target_start_rms_dbfs",
        "loudness_target_end_rms_dbfs",
        "loudness_calibration_window_role",
        "loudness_calibration_window_target_rms_dbfs",
        "loudness_final_window_start_s",
        "loudness_final_window_stop_s",
        "loudness_pre_hold_rms_dbfs",
        "loudness_final_window_rms_dbfs",
        "loudness_post_hold_rms_dbfs",
        "loudness_final_window_estimated_spl_db",
        "loudness_applied_gain_db",
        "loudness_audio_peak_dbfs",
        "loudness_peak_ceiling_dbfs",
        "loudness_peak_status",
        "wav_sha256",
        "message",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_tactile_events_qc(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = int(config["source"]["sample_rate"])
    waveform = config["tactile"]["waveform"]
    cue_duration_s = float(waveform["duration_s"])
    cue_samples = int(round(cue_duration_s * sample_rate))
    fieldnames = [
        "trial_type",
        "soa_ms",
        "tactile_onset_s",
        "tactile_onset_sample",
        "tactile_duration_s",
        "tactile_duration_samples",
        "tactile_channel",
        "planned_spatial_value_cm",
        "source_radius_at_tactile_cm",
        "source_x_at_tactile_m",
        "source_y_at_tactile_m",
        "source_z_at_tactile_m",
        "trajectory_phase_at_tactile",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for event in config["tactile"]["events"]:
            writer.writerow(
                {
                    "trial_type": event["trial_type"],
                    "soa_ms": event["soa_ms"],
                    "tactile_onset_s": f"{float(event['tactile_onset_s']):.6f}",
                    "tactile_onset_sample": int(round(float(event["tactile_onset_s"]) * sample_rate)),
                    "tactile_duration_s": f"{cue_duration_s:.6f}",
                    "tactile_duration_samples": cue_samples,
                    "tactile_channel": "2",
                    "planned_spatial_value_cm": event["planned_spatial_value_cm"],
                    "source_radius_at_tactile_cm": f"{float(event['source_radius_at_tactile_cm']):.6f}",
                    "source_x_at_tactile_m": f"{float(event['source_x_at_tactile_m']):.9f}",
                    "source_y_at_tactile_m": f"{float(event['source_y_at_tactile_m']):.9f}",
                    "source_z_at_tactile_m": f"{float(event['source_z_at_tactile_m']):.9f}",
                    "trajectory_phase_at_tactile": event["trajectory_phase_at_tactile"],
                }
            )


def write_trajectory_qc(path: Path, config: dict[str, Any]) -> None:
    samples = config["trajectory"]["samples"]
    if not samples:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(samples[0]))
        writer.writeheader()
        writer.writerows(samples)


def render_with_python_sofa_reference(config: dict[str, Any], output_dir: Path, qc_path: Path) -> list[Path]:
    import numpy as np
    import soundfile as sf

    sample_rate = int(config["source"]["sample_rate"])
    spatialized_sources = [
        source
        for source in config["source"]["noises"]
        if source.get("source_kind") != "imported_audio" or source.get("source_render_mode") == "spatialize"
    ]
    sofa = _load_sofa_hrirs(config["source"]["sofa_file"]) if spatialized_sources else None
    if sofa is not None and sofa["sample_rate"] != sample_rate:
        raise RuntimeError(
            f"SOFA sample rate {sofa['sample_rate']} Hz does not match render sample rate {sample_rate} Hz."
        )
    total_duration = float(config["trajectory"]["total_duration_s"])
    total_samples = max(1, int(round(total_duration * sample_rate)))
    frame_samples = max(16, int(round(float(config["renderer"]["frame_ms"]) / 1000.0 * sample_rate)))
    hop_samples = max(1, int(round(float(config["renderer"]["hop_ms"]) / 1000.0 * sample_rate)))
    window = np.sqrt(np.hanning(frame_samples))
    if not np.any(window):
        window = np.ones(frame_samples, dtype=float)
    include_tactile = bool(config["tactile"].get("enabled", True))
    tactile = _add_tactile_channel(config, sample_rate, total_samples) if include_tactile else None
    rows: list[dict[str, Any]] = []
    wav_paths: list[Path] = []

    for noise_index, noise in enumerate(config["source"]["noises"]):
        source_kind = noise.get("source_kind", "procedural_noise")
        source_render_mode = noise.get("source_render_mode", "preserve")
        imported_metadata: dict[str, Any] = {}
        if source_kind == "imported_audio" and source_render_mode != "spatialize":
            wav_path, row = _render_imported_audio_source(
                noise,
                config=config,
                tactile=tactile,
                output_dir=output_dir,
                sample_rate=sample_rate,
                total_samples=total_samples,
            )
            wav_paths.append(wav_path)
            rows.append(row)
            continue
        if source_kind == "imported_audio":
            dry, source_rate, source_channels = _imported_audio_mono_source(noise, sample_rate, total_samples)
            imported_metadata = {
                "source_render_mode": "spatialize",
                "source_path": str(repo_relative_path(str(noise.get("path", "")))),
                "source_sample_rate": source_rate,
                "source_channels": source_channels,
            }
        else:
            dry_seed = int(config["source"]["seed"]) + noise_index * 1009
            dry = _generate_procedural_source(noise, total_samples, sample_rate, dry_seed)
        loudness_metadata: dict[str, Any] = {}
        if _loudness_control_enabled(config):
            dry = _apply_loudness_envelope(dry, config["loudness_policy"], sample_rate)
        stereo, used_hrir_indices = _spatialize_moving_source(
            dry,
            noise,
            config=config,
            sofa=sofa,
            sample_rate=sample_rate,
            total_samples=total_samples,
            frame_samples=frame_samples,
            hop_samples=hop_samples,
            window=window,
        )
        if _loudness_control_enabled(config):
            stereo, loudness_metadata = _apply_calibrated_loudness_target(
                stereo,
                config["loudness_policy"],
                sample_rate,
                total_samples,
            )
        rendered = np.column_stack([stereo, tactile]) if include_tactile and tactile is not None else stereo
        first_half = stereo[: total_samples // 2, :]
        second_half = stereo[total_samples // 2 :, :]
        first_rms = np.sqrt(np.mean(first_half * first_half, axis=0)) if len(first_half) else np.zeros(2)
        second_rms = np.sqrt(np.mean(second_half * second_half, axis=0)) if len(second_half) else np.zeros(2)
        peak = float(np.max(np.abs(rendered))) if rendered.size else 0.0
        if peak > OUTPUT_LIMITER_PEAK and not _loudness_control_enabled(config):
            rendered = rendered / peak * OUTPUT_LIMITER_PEAK
            peak = float(np.max(np.abs(rendered)))
        peak_for_qc = float(np.max(np.abs(stereo))) if _loudness_control_enabled(config) and stereo.size else peak
        wav_path = output_dir / f"looming_{_slug(noise['label'])}.wav"
        sf.write(wav_path, rendered, sample_rate, subtype="PCM_16")
        wav_paths.append(wav_path)
        peak_dbfs = "-inf" if peak_for_qc <= 0 else f"{20.0 * math.log10(peak_for_qc):.3f}"
        rows.append(
            {
                "status": "rendered_reference",
                "noise_label": noise["label"],
                "noise_type": noise["noise_type"],
                "source_profile": noise.get("source_profile", ""),
                "source_profile_parameters": json.dumps(noise.get("source_profile_parameters", {}), sort_keys=True),
                "source_kind": source_kind,
                **imported_metadata,
                "duration_s": f"{total_samples / sample_rate:.6f}",
                "sample_rate": sample_rate,
                "channels": 3 if include_tactile else 2,
                "tactile_events": len(config["tactile"]["events"]),
                "tactile_channel": 2 if include_tactile else "",
                "peak_dbfs": peak_dbfs,
                "clipping": str(peak_for_qc >= 1.0).lower(),
                "hrir_positions_used": len(used_hrir_indices),
                "first_half_left_rms": f"{float(first_rms[0]):.9f}",
                "first_half_right_rms": f"{float(first_rms[1]):.9f}",
                "second_half_left_rms": f"{float(second_rms[0]):.9f}",
                "second_half_right_rms": f"{float(second_rms[1]):.9f}",
                **loudness_metadata,
                "wav_sha256": sha256_file(wav_path) or "",
                "message": (
                    "Rendered with the Python SOFA/FABIAN reference engine from the same "
                    f"3DTI-compatible config; HRIR positions used: {len(used_hrir_indices)}."
                    + ("" if include_tactile else " Tactile channel generation was deferred for this auditory-only bake.")
                ),
            }
        )

    write_render_qc(qc_path, rows)
    return wav_paths


def write_manifest(
    path: Path,
    *,
    status: str,
    config: dict[str, Any],
    backend_executable: Path,
    message: str,
    render_engine: str = "native-3dti",
    wav_paths: list[Path] | tuple[Path, ...] | None = None,
    tactile_events_path: Path | None = None,
) -> None:
    manifest = {
        "schema": "pps-3dti-render-manifest.v1",
        "status": status,
        "message": message,
        "backend_executable": str(backend_executable),
        "backend_executable_sha256": sha256_file(backend_executable),
        "render_engine": render_engine,
        "renderer": config["renderer"],
        "listener": config["listener"],
        "coordinate_convention": config["coordinate_convention"],
        "duration_s": config["trajectory"]["total_duration_s"],
        "trajectory_samples": len(config["trajectory"]["samples"]),
        "source": config["source"],
        "loudness_policy": config.get("loudness_policy", normalize_loudness_policy(None)),
        "tactile_events": {
            "enabled": bool(config["tactile"].get("enabled", True)),
            "stage": config["tactile"].get("stage", ""),
            "count": len(config["tactile"]["events"]),
            "path": str(tactile_events_path) if tactile_events_path else None,
            "sha256": sha256_file(tactile_events_path) if tactile_events_path else None,
        },
        "source_snapshot_present": THIRD_PARTY_3DTI_DIR.exists(),
        "sofa_file": config["source"]["sofa_file"],
        "sofa_file_sha256": config["source"]["sofa_file_sha256"],
        "hrtf_resource": config["source"]["hrtf_resource"],
        "study_profile": config.get("study_profile", {}),
        "wav_outputs": [
            {
                "path": str(path),
                "sha256": sha256_file(path),
            }
            for path in (wav_paths or [])
        ],
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def postprocess_native_manifest(
    path: Path,
    *,
    config: dict[str, Any],
    backend_executable: Path,
    wav_paths: list[Path],
    tactile_events_path: Path,
) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        manifest = {}
    manifest.update(
        {
            "schema": "pps-render-manifest.v1",
            "status": "rendered_3dti",
            "render_engine": "native-3dti",
            "backend_executable": str(backend_executable),
            "backend_executable_sha256": sha256_file(backend_executable),
            "renderer": config["renderer"],
            "loudness_policy": config.get("loudness_policy", normalize_loudness_policy(None)),
            "source": {
                "sample_rate": config["source"]["sample_rate"],
                "sofa_file": config["source"]["sofa_file"],
                "sofa_file_sha256": config["source"]["sofa_file_sha256"],
                "hrtf_resource": config["source"].get("hrtf_resource", {}),
            },
            "listener": config["listener"],
            "study_profile": config.get("study_profile", {}),
            "tactile_events": {
                "enabled": bool(config["tactile"].get("enabled", True)),
                "stage": config["tactile"].get("stage", ""),
                "path": str(tactile_events_path),
                "sha256": sha256_file(tactile_events_path),
                "count": len(config["tactile"]["events"]),
            },
            "wav_outputs": [
                {
                    "path": str(path),
                    "sha256": sha256_file(path),
                }
                for path in wav_paths
            ],
        }
    )
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def render_design_with_3dti(
    design_path: Path,
    output_dir: Path,
    *,
    seed: int,
    backend_executable: Path | None = None,
    dry_run: bool = False,
    engine: str = "auto",
    include_tactile: bool = True,
) -> RenderResult:
    if engine not in RENDER_ENGINES:
        raise ValueError(f"Unsupported render engine: {engine}")
    design = load_render_design(design_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    backend = resolve_backend_executable(backend_executable)
    config = build_render_config(design, seed=seed, output_dir=output_dir, include_tactile=include_tactile)
    config_path = output_dir / "render_config.3dti.json"
    manifest_path = output_dir / "render_manifest.json"
    qc_path = output_dir / "render_qc.csv"
    trajectory_path = output_dir / "render_trajectory_samples.csv"
    tactile_events_path = output_dir / "render_tactile_events.csv"

    config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    write_trajectory_qc(trajectory_path, config)
    write_tactile_events_qc(tactile_events_path, config)
    uses_imported_audio = _has_imported_audio_sources(config)

    if dry_run:
        write_manifest(
            manifest_path,
            status="config_written",
            config=config,
            backend_executable=backend,
            message="Render config written; backend was not invoked.",
            render_engine=engine,
            tactile_events_path=tactile_events_path,
        )
        write_render_qc(qc_path, [])
        return RenderResult(
            "config_written",
            0,
            output_dir,
            config_path,
            manifest_path,
            qc_path,
            backend,
            tactile_events_path=tactile_events_path,
        )

    if engine == "python-sofa-reference":
        wav_paths = render_with_python_sofa_reference(config, output_dir, qc_path)
        message = (
            "Rendered with the Python SOFA/FABIAN reference engine from the same saved "
            "3DTI-compatible trajectory config."
        )
        if not include_tactile:
            message += " Tactile cue generation was deferred for this auditory-only stimulus bake."
        write_manifest(
            manifest_path,
            status="rendered_reference",
            config=config,
            backend_executable=backend,
            message=message,
            render_engine="python-sofa-reference",
            wav_paths=wav_paths,
            tactile_events_path=tactile_events_path,
        )
        return RenderResult(
            "rendered_reference",
            0,
            output_dir,
            config_path,
            manifest_path,
            qc_path,
            backend,
            tuple(wav_paths),
            tactile_events_path,
        )

    if uses_imported_audio:
        if engine == "native-3dti":
            raise RuntimeError("Imported audio sources require the python-sofa-reference render path.")
        wav_paths = render_with_python_sofa_reference(config, output_dir, qc_path)
        message = (
            "Rendered with the Python reference engine because this design includes local imported audio sources. "
            "Imported files are read from the research PC by the local backend, not uploaded online."
        )
        write_manifest(
            manifest_path,
            status="rendered_reference",
            config=config,
            backend_executable=backend,
            message=message,
            render_engine="python-sofa-reference",
            wav_paths=wav_paths,
            tactile_events_path=tactile_events_path,
        )
        return RenderResult(
            "rendered_reference",
            0,
            output_dir,
            config_path,
            manifest_path,
            qc_path,
            backend,
            tuple(wav_paths),
            tactile_events_path,
        )

    if not backend.exists():
        if engine in {"auto", "python-sofa-reference"}:
            wav_paths = render_with_python_sofa_reference(config, output_dir, qc_path)
            message = (
                "Native 3DTI renderer backend was not found, so WAVs were rendered with the "
                "Python SOFA/FABIAN reference engine from the same saved trajectory/SOA config."
            )
            write_manifest(
                manifest_path,
                status="rendered_reference",
                config=config,
                backend_executable=backend,
                message=message,
                render_engine="python-sofa-reference",
                wav_paths=wav_paths,
                tactile_events_path=tactile_events_path,
            )
            return RenderResult(
                "rendered_reference",
                0,
                output_dir,
                config_path,
                manifest_path,
                qc_path,
                backend,
                tuple(wav_paths),
                tactile_events_path,
            )
        message = (
            "3DTI renderer backend is not built. Run For-AI/engineering/build/windows/Fetch_3DTI_Backend.ps1 "
            "and For-AI/engineering/build/windows/Build_3DTI_Renderer.ps1, or set PPS_3DTI_RENDERER."
        )
        write_manifest(
            manifest_path,
            status="backend_missing",
            config=config,
            backend_executable=backend,
            message=message,
            render_engine="native-3dti",
            tactile_events_path=tactile_events_path,
        )
        write_render_qc(
            qc_path,
            [
                {
                    "status": "backend_missing",
                    "noise_label": noise["label"],
                    "noise_type": noise["noise_type"],
                    "source_kind": noise.get("source_kind", "procedural_noise"),
                    "duration_s": config["trajectory"]["total_duration_s"],
                    "sample_rate": config["source"]["sample_rate"],
                    "peak_dbfs": "",
                    "clipping": "",
                    "wav_sha256": "",
                    "message": message,
                }
                for noise in config["source"]["noises"]
            ],
        )
        return RenderResult(
            "backend_missing",
            2,
            output_dir,
            config_path,
            manifest_path,
            qc_path,
            backend,
            tactile_events_path=tactile_events_path,
        )

    command = [
        str(backend),
        "--config",
        str(config_path),
        "--output-dir",
        str(output_dir),
        "--manifest",
        str(manifest_path),
        "--qc",
        str(qc_path),
    ]
    completed = subprocess.run(
        command,
        # Paths serialized in the scientific config remain resource-relative
        # (for example ``assets/...``). Launch the native adapter from that
        # canonical root so source and frozen builds resolve identical bytes.
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        **windows_no_console_kwargs(),
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "3DTI renderer failed.").strip()
        write_manifest(
            manifest_path,
            status="backend_failed",
            config=config,
            backend_executable=backend,
            message=message,
            render_engine="native-3dti",
            tactile_events_path=tactile_events_path,
        )
        return RenderResult(
            "backend_failed",
            completed.returncode,
            output_dir,
            config_path,
            manifest_path,
            qc_path,
            backend,
            tactile_events_path=tactile_events_path,
        )

    wav_paths = [path for path in _expected_wav_paths(config, output_dir) if path.exists()]
    postprocess_native_manifest(
        manifest_path,
        config=config,
        backend_executable=backend,
        wav_paths=wav_paths,
        tactile_events_path=tactile_events_path,
    )
    return RenderResult(
        "rendered_3dti",
        0,
        output_dir,
        config_path,
        manifest_path,
        qc_path,
        backend,
        tuple(wav_paths),
        tactile_events_path=tactile_events_path,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a saved PPS design through the pinned 3DTI backend.")
    parser.add_argument("--design", type=Path, required=True, help="Saved StimulusDesign JSON or study profile JSON.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory for WAV, manifest, and QC outputs.")
    parser.add_argument("--seed", type=int, default=20250604, help="Deterministic dry-noise seed.")
    parser.add_argument("--backend", type=Path, help="Path to pps-3dti-renderer.exe. Defaults to PPS_3DTI_RENDERER or third_party path.")
    parser.add_argument(
        "--engine",
        choices=RENDER_ENGINES,
        default="auto",
        help="Render engine. auto uses native 3DTI when available, otherwise the Python SOFA/FABIAN reference renderer.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only write the 3DTI render config and QC scaffolding.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = render_design_with_3dti(
        args.design,
        args.output_dir,
        seed=args.seed,
        backend_executable=args.backend,
        dry_run=args.dry_run,
        engine=args.engine,
    )
    print(f"3DTI render status: {result.status}")
    print(f"  config: {result.config_path}")
    print(f"  manifest: {result.manifest_path}")
    print(f"  qc: {result.qc_path}")
    if result.tactile_events_path:
        print(f"  tactile events: {result.tactile_events_path}")
    for wav_path in result.wav_paths:
        print(f"  wav: {wav_path}")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
