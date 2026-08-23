"""Stimulus-design data model and SOFA/trajectory helpers."""

from __future__ import annotations

import csv
import itertools
import json
import math
import os
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .runtime_paths import resource_root


SUPPORTED_NOISE_TYPES = ("pink", "blue", "violet", "white", "brown")
CUSTOM_AUDIO_NOISE_TYPE = "custom_audio"
SUPPORTED_IMPORTED_AUDIO_RENDER_MODES = ("spatialize", "preserve")
SUPPORTED_STIMULUS_SNIPPET_PLACEMENTS = ("before", "after")
SUPPORTED_STIMULUS_MOTION_MODES = ("looming", "stationary")
SUPPORTED_TRIAL_STRIP_ELEMENT_TYPES = ("fixed_audio", "looming_stimulus", "jitter")
SUPPORTED_DIRECTIONS = ("approach", "recede", "left_to_right", "right_to_left", "custom")
SUPPORTED_COORDINATE_MODES = ("polar", "cartesian")
SUPPORTED_TRIAL_TYPES = ("Audio-Tactile", "Baseline", "Catch", "Auditory-Only")
DEFAULT_BLOCK_STIMULUS_TYPES = ("Audio-Tactile", "Baseline", "Catch")
SUPPORTED_BASELINE_STRATEGIES = (
    "none",
    "min_anchor",
    "max_anchor",
    "min_max",
    "tactile_only",
    "stationary_burst",
    "soa_zero",
    "sound_offset",
    "custom",
)


def _resolve_design_asset_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.exists() or path.is_absolute():
        return path
    packaged = resource_root() / path
    return packaged if packaged.exists() else path


SUPPORTED_BASELINE_CUSTOM_TRIAL_MODES = ("tactile_only", "audio_tactile")
SUPPORTED_TRIAL_RANDOMIZATION = ("balanced_shuffle", "no_immediate_repeats", "ordered")
SUPPORTED_BLOCK_ORDER_RANDOMIZATION = ("counterbalanced_rotation", "seeded_random_permutation", "fixed")
DEFAULT_SOFA_FILE = "assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa"
DEFAULT_TRAJECTORY_PLANE_HEIGHT_M = 0.0
DEFAULT_TRAJECTORY_PLANE_LABEL = "listener head/ear center plane"
PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE = "dynaspace_gaussian_burst_train"
PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS: dict[str, Any] = {
    "burst_count_mode": "duration_derived",
    "burst_duration_s": 0.030,
    "rise_fall_s": 0.010,
    "target_period_s": 0.095,
    "onset_s": 0.300,
    "active_window_source": "trajectory_movement_duration",
    "spacing_policy": "symmetric_fit",
    "standard_basis": (
        "DynaSpace/Hobeika-style Gaussian white-noise burst train: raw DynaSpace audit found "
        "33 peaks at about 95 ms IOI for its active window. PPS-kit derives burst count and "
        "equal symmetric spacing from the configured active window so future trajectories can "
        "change duration without truncating the final burst. Consensus evidence supports "
        "broadband transients for localization/salience while 3DTI/SOFA owns binaural spatial cues."
    ),
}
DISTANCE_CM_MIN = 1.0
DISTANCE_CM_MAX = 1000.0
ROTATION_DEG_MIN = -180.0
ROTATION_DEG_MAX = 180.0
DISPLAY_ROTATION_DEG_MIN = 0.0
DISPLAY_ROTATION_DEG_MAX = 360.0


def gold_standard_looming_source_parameters(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = dict(PPS_LOOMING_GOLD_STANDARD_SOURCE_PARAMETERS)
    if overrides:
        parameters.update(overrides)
    return parameters


def should_apply_gold_standard_looming_source_profile(noise: "NoiseDefinition") -> bool:
    """Return whether a generated source should inherit the toolkit looming source standard."""

    if str(noise.source_profile or "").strip():
        return False
    if str(noise.motion_mode or "looming").strip().lower() == "stationary":
        return False
    return str(noise.noise_type or "").strip().lower() in SUPPORTED_NOISE_TYPES


def apply_gold_standard_looming_source_profile(noise: "NoiseDefinition") -> "NoiseDefinition":
    source_profile = str(noise.source_profile or "").strip()
    if source_profile == "continuous_noise":
        noise.source_profile_parameters = {}
    elif source_profile == PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE:
        noise.source_profile_parameters = gold_standard_looming_source_parameters(noise.source_profile_parameters)
    elif should_apply_gold_standard_looming_source_profile(noise):
        noise.source_profile = PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
        noise.source_profile_parameters = gold_standard_looming_source_parameters(noise.source_profile_parameters)
    return noise


def normalize_generated_looming_source_profiles(design: "StimulusDesign") -> "StimulusDesign":
    for noise in design.noises:
        apply_gold_standard_looming_source_profile(noise)
    return design


@dataclass
class AudioFileSpec:
    label: str
    path: str
    target_duration_s: float = 4.0
    render_mode: str = "preserve"
    tone_type: str = ""
    gain: float = 1.0
    placement: str = "before"
    target_source_label: str = ""
    phase: str = ""
    gap_s: float = 0.0
    sequence_order: int = 0
    motion_mode: str = "looming"
    trajectory_snapshot: dict[str, Any] = field(default_factory=dict)
    display_color_hex: str = ""
    source_input_path: str = ""


@dataclass
class NoiseDefinition:
    label: str
    noise_type: str
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    gain: float = 1.0
    source_profile: str = ""
    source_profile_parameters: dict[str, Any] = field(default_factory=dict)
    prebaked_path: str = ""
    sequence_order: int = 0
    motion_mode: str = "looming"
    trajectory_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class BlockSpec:
    label: str
    stimulus_types: list[str] = field(default_factory=lambda: list(DEFAULT_BLOCK_STIMULUS_TYPES))


@dataclass
class TrialStripElementSpec:
    element_id: str = ""
    kind: str = "looming_stimulus"
    label: str = ""
    source_label: str = ""
    source_labels: list[str] = field(default_factory=list)
    jitter_values_ms: list[int] = field(default_factory=list)
    randomized: bool = False


@dataclass
class TrialStripSpec:
    strip_id: str = ""
    label: str = ""
    audio_tactile_percentage: float | None = None
    catch_percentage: float | None = None
    baseline_percentage: float | None = None
    soa_values_ms: list[int] = field(default_factory=list)
    spatial_values_cm: list[float] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    elements: list[TrialStripElementSpec] = field(default_factory=list)


@dataclass
class TrajectorySpec:
    start_radius_m: float = 1.1
    end_radius_m: float = 0.1
    path_direction: str = "approach"
    coordinate_mode: str = "polar"
    start_x_m: float | None = None
    start_y_m: float | None = None
    start_z_m: float | None = None
    end_x_m: float | None = None
    end_y_m: float | None = None
    end_z_m: float | None = None
    path_length_m: float = 1.0
    propagation_speed_mps: float = 1.0 / 3.0
    azimuth_start_deg: float = 0.0
    azimuth_end_deg: float = 0.0
    elevation_deg: float = 0.0
    padding_pre_s: float = 0.5
    padding_post_s: float = 0.5
    sample_rate: int = 44100
    use_inverse_square: bool = True

    @property
    def movement_duration_s(self) -> float:
        if self.propagation_speed_mps <= 0:
            return 0.0
        return self.path_length_m / self.propagation_speed_mps

    @property
    def total_duration_s(self) -> float:
        return self.padding_pre_s + self.movement_duration_s + self.padding_post_s


@dataclass
class ProtocolSpec:
    repetitions_per_condition: int = 1
    trial_pool_repetition_defaults: dict[str, float] = field(default_factory=dict)
    soa_values_ms: list[int] = field(default_factory=lambda: [300, 800, 1500, 2200, 2700])
    spatial_values_cm: list[float] = field(default_factory=lambda: [100.0, 83.3, 60.0, 36.7, 20.0])
    pair_spatial_values_with_soas: bool = True
    auditory_motion_directions: list[str] = field(default_factory=lambda: ["looming"])
    tactile_sites: list[str] = field(default_factory=lambda: ["hand"])
    include_catch_trials: bool = True
    catch_trial_percentage: float = 10.0
    catch_trials_exact: int | None = None
    catch_crosses_sequence_variants: bool = True
    include_auditory_only_trials: bool = False
    auditory_only_trial_percentage: float = 0.0
    auditory_only_trials_exact: int | None = None
    auditory_only_crosses_sequence_variants: bool = True
    include_baseline_trials: bool = True
    baseline_strategy: str = "tactile_only"
    baseline_trials_exact: int | None = None
    baseline_trial_percentage: float = 0.0
    baseline_soa_values_ms: list[int] = field(default_factory=list)
    baseline_custom_trial_mode: str = "tactile_only"
    baseline_crosses_sequence_variants: bool = True
    respiratory_phases: list[str] = field(default_factory=lambda: ["Inhale", "Exhale"])
    blocks: int = 6
    block_specs: list[BlockSpec] = field(default_factory=list)
    repeat_trial_pool_per_block: bool = False
    distribute_trial_pool_across_blocks: bool = False
    trial_strips: list[TrialStripSpec] = field(default_factory=list)
    trial_randomization_strategy: str = "no_immediate_repeats"
    block_order_randomization: str = "counterbalanced_rotation"
    max_consecutive_same_trial_type: int = 2
    participants: int = 50
    random_seed: int = 20250604
    participant_order_policy: dict[str, Any] = field(default_factory=dict)


@dataclass
class StimulusDesign:
    name: str = "Study 5 PPS white/pink design"
    study_profile_id: str = ""
    study_profile_title: str = ""
    study_profile_notes: str = ""
    study_profile_reference_parameters: dict[str, Any] = field(default_factory=dict)
    sofa_file: str = DEFAULT_SOFA_FILE
    noises: list[NoiseDefinition] = field(default_factory=list)
    custom_looming_files: list[AudioFileSpec] = field(default_factory=list)
    prestimulus_files: list[AudioFileSpec] = field(default_factory=list)
    trajectory: TrajectorySpec = field(default_factory=TrajectorySpec)
    protocol: ProtocolSpec = field(default_factory=ProtocolSpec)


def default_design() -> StimulusDesign:
    return normalize_generated_looming_source_profiles(
        StimulusDesign(
            sofa_file=DEFAULT_SOFA_FILE,
            noises=[
                NoiseDefinition("Pink frontal", "pink", 0.0),
                NoiseDefinition("White frontal", "white", 0.0),
            ],
        )
    )


def design_to_dict(design: StimulusDesign) -> dict[str, Any]:
    normalize_generated_looming_source_profiles(design)
    return asdict(design)


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_").lower()
    return text or "item"


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_list(values: Any) -> list[int]:
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        values = [values]
    parsed: list[int] = []
    for value in values:
        try:
            parsed.append(int(round(float(value))))
        except (TypeError, ValueError):
            continue
    return parsed


def _float_list(values: Any) -> list[float]:
    if values in (None, ""):
        return []
    if not isinstance(values, list):
        values = [values]
    parsed: list[float] = []
    for value in values:
        try:
            parsed.append(float(value))
        except (TypeError, ValueError):
            continue
    return parsed


def _audio_file_specs_from_dicts(items: list[Any], *, default_motion_mode: str = "looming") -> list[AudioFileSpec]:
    specs: list[AudioFileSpec] = []
    for item in items:
        if isinstance(item, str):
            specs.append(AudioFileSpec(label=Path(item).stem, path=item, motion_mode=default_motion_mode))
        else:
            data = dict(item)
            data.setdefault("motion_mode", default_motion_mode)
            display_color = str(data.get("display_color_hex") or "").strip()
            data["display_color_hex"] = display_color.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", display_color) else ""
            data["source_input_path"] = str(data.get("source_input_path") or "")
            specs.append(AudioFileSpec(**data))
    return specs


def _trial_strip_specs_from_dicts(
    items: list[Any],
    *,
    source_labels: set[str] | None = None,
) -> list[TrialStripSpec]:
    strips: list[TrialStripSpec] = []
    available = source_labels or set()
    for strip_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        elements = [
            TrialStripElementSpec(**element)
            for element in item.get("elements", [])
            if isinstance(element, dict)
        ]
        _normalize_trial_strip_element_sources(elements, available)
        strips.append(
            TrialStripSpec(
                strip_id=str(item.get("strip_id") or f"strip-{strip_index}"),
                label=str(item.get("label") or f"Row {strip_index}"),
                audio_tactile_percentage=_optional_float(item.get("audio_tactile_percentage")),
                catch_percentage=_optional_float(item.get("catch_percentage")),
                baseline_percentage=_optional_float(item.get("baseline_percentage")),
                soa_values_ms=_int_list(item.get("soa_values_ms")),
                spatial_values_cm=_float_list(item.get("spatial_values_cm")),
                metadata=dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {},
                elements=elements,
            )
        )
    return strips


def _normalize_trial_strip_element_sources(
    elements: list[TrialStripElementSpec],
    available_source_labels: set[str],
) -> None:
    for element in elements:
        if element.kind not in {"fixed_audio", "looming_stimulus"}:
            continue
        labels: list[str] = []
        source_label = str(element.source_label or "").strip()
        if source_label:
            labels.append(source_label)
        labels.extend(str(label or "").strip() for label in element.source_labels)
        fallback_label = str(element.label or "").strip()
        if not any(labels) and fallback_label in available_source_labels:
            labels.append(fallback_label)
        element.source_labels = list(dict.fromkeys(label for label in labels if label))
        element.source_label = element.source_labels[0] if element.source_labels else ""


def design_from_dict(data: dict[str, Any]) -> StimulusDesign:
    noises = [NoiseDefinition(**item) for item in data.get("noises", [])]
    custom_looming_files = _audio_file_specs_from_dicts(data.get("custom_looming_files", []), default_motion_mode="looming")
    prestimulus_files = _audio_file_specs_from_dicts(data.get("prestimulus_files", []), default_motion_mode="stationary")
    trajectory_data = dict(data.get("trajectory", {}))
    if "coordinate_mode" not in trajectory_data and any(
        key in trajectory_data
        for key in ("start_x_m", "start_y_m", "start_z_m", "end_x_m", "end_y_m", "end_z_m")
    ):
        trajectory_data["coordinate_mode"] = "cartesian"
    trajectory = TrajectorySpec(**trajectory_data)
    protocol_data = dict(data.get("protocol", {}))
    protocol_data["block_specs"] = [
        BlockSpec(**item) if isinstance(item, dict) else BlockSpec(str(item))
        for item in protocol_data.get("block_specs", [])
    ]
    trial_source_labels = {
        item.label
        for item in [*noises, *custom_looming_files, *prestimulus_files]
        if str(item.label or "").strip()
    }
    protocol_data["trial_strips"] = _trial_strip_specs_from_dicts(
        protocol_data.get("trial_strips", []),
        source_labels=trial_source_labels,
    )
    if "include_catch_trials" not in protocol_data:
        protocol_data["include_catch_trials"] = bool(
            float(protocol_data.get("catch_trial_percentage") or 0.0) > 0.0
            or protocol_data.get("catch_trials_exact") not in (None, 0, "")
        )
    if "include_auditory_only_trials" not in protocol_data:
        protocol_data["include_auditory_only_trials"] = bool(
            float(protocol_data.get("auditory_only_trial_percentage") or 0.0) > 0.0
            or protocol_data.get("auditory_only_trials_exact") not in (None, 0, "")
        )
    protocol = ProtocolSpec(**protocol_data)
    return normalize_generated_looming_source_profiles(
        StimulusDesign(
            name=data.get("name", "Study 5 PPS white/pink design"),
            study_profile_id=data.get("study_profile_id", ""),
            study_profile_title=data.get("study_profile_title", ""),
            study_profile_notes=data.get("study_profile_notes", ""),
            study_profile_reference_parameters=dict(data.get("study_profile_reference_parameters", {})),
            sofa_file=data.get("sofa_file") or DEFAULT_SOFA_FILE,
            noises=noises,
            custom_looming_files=custom_looming_files,
            prestimulus_files=prestimulus_files,
            trajectory=trajectory,
            protocol=protocol,
        )
    )


def expand_trial_strip_source_labels(
    design: StimulusDesign,
    available_source_labels: list[str],
) -> StimulusDesign:
    """Expand base source selections to concrete preloaded source variants."""

    available = [str(label or "").strip() for label in available_source_labels if str(label or "").strip()]
    if not available:
        return design
    for strip in design.protocol.trial_strips:
        for element in strip.elements:
            if element.kind != "looming_stimulus":
                continue
            labels = _audio_choice_labels(element)
            if not labels:
                continue
            expanded: list[str] = []
            for label in labels:
                matches = [
                    candidate
                    for candidate in available
                    if candidate == label or candidate.startswith(f"{label} - ")
                ]
                expanded.extend(matches or [label])
            element.source_labels = list(dict.fromkeys(expanded))
            element.source_label = element.source_labels[0] if element.source_labels else ""
    return design


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def load_design(path: Path) -> StimulusDesign:
    with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
        return design_from_dict(json.loads(handle.read()))


def save_design(design: StimulusDesign, path: Path) -> None:
    path = Path(path)
    os.makedirs(_filesystem_path(path.parent), exist_ok=True)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(design_to_dict(design), indent=2))


def audio_file_summary(path: Path) -> dict[str, Any]:
    try:
        import soundfile as sf
    except ImportError as exc:
        raise RuntimeError("Install soundfile to inspect audio durations.") from exc

    info = sf.info(str(path))
    return {
        "frames": int(info.frames),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "duration_s": float(info.frames / info.samplerate) if info.samplerate else 0.0,
        "format": info.format,
    }


def _uses_cartesian_coordinates(spec: TrajectorySpec) -> bool:
    fields = (spec.start_x_m, spec.start_y_m, spec.start_z_m, spec.end_x_m, spec.end_y_m, spec.end_z_m)
    return spec.coordinate_mode == "cartesian" or any(value is not None for value in fields)


def cartesian_to_spherical(x_m: float, y_m: float, z_m: float) -> dict[str, float]:
    radius_m = math.sqrt(x_m**2 + y_m**2 + z_m**2)
    horizontal_radius = math.sqrt(x_m**2 + y_m**2)
    azimuth_deg = math.degrees(math.atan2(x_m, y_m)) if horizontal_radius else 0.0
    elevation_deg = math.degrees(math.atan2(z_m, horizontal_radius)) if radius_m else 0.0
    return {
        "radius_m": radius_m,
        "azimuth_deg": azimuth_deg,
        "elevation_deg": elevation_deg,
    }


def spherical_to_cartesian(radius_m: float, azimuth_deg: float, elevation_deg: float) -> dict[str, float]:
    az = math.radians(azimuth_deg)
    el = math.radians(elevation_deg)
    horizontal_radius = radius_m * math.cos(el)
    return {
        "x_m": horizontal_radius * math.sin(az),
        "y_m": horizontal_radius * math.cos(az),
        "z_m": radius_m * math.sin(el),
    }


def normalize_azimuth_deg(rotation_deg: float) -> float:
    return ((rotation_deg + 180.0) % 360.0) - 180.0


def azimuth_to_display_rotation_deg(azimuth_deg: float) -> float:
    return azimuth_deg % 360.0


def horizontal_point_from_distance_rotation(distance_cm: float, rotation_deg: float) -> dict[str, float]:
    return point_from_distance_rotation_height(distance_cm, rotation_deg, 0.0)


def point_from_distance_rotation_height(
    distance_cm: float,
    rotation_deg: float,
    height_cm: float = 0.0,
) -> dict[str, float]:
    if not DISTANCE_CM_MIN <= distance_cm <= DISTANCE_CM_MAX:
        raise ValueError(f"Distance must be between {DISTANCE_CM_MIN:g} and {DISTANCE_CM_MAX:g} cm.")
    if not DISPLAY_ROTATION_DEG_MIN <= rotation_deg <= DISPLAY_ROTATION_DEG_MAX:
        raise ValueError(
            f"Rotation must be between {DISPLAY_ROTATION_DEG_MIN:g} and {DISPLAY_ROTATION_DEG_MAX:g} degrees."
        )
    if abs(height_cm) > distance_cm:
        raise ValueError("Height from the head plane cannot be larger than the distance from the listener.")
    radius_m = distance_cm / 100.0
    z_m = height_cm / 100.0
    horizontal_radius_m = math.sqrt(max(radius_m**2 - z_m**2, 0.0))
    az = math.radians(normalize_azimuth_deg(rotation_deg))
    return {
        "x_m": horizontal_radius_m * math.sin(az),
        "y_m": horizontal_radius_m * math.cos(az),
        "z_m": z_m,
    }


def apply_trajectory_snapshot_to_trajectory(spec: TrajectorySpec, snapshot: dict[str, Any]) -> bool:
    """Apply a source-level trajectory snapshot to a mutable trajectory spec."""

    if not isinstance(snapshot, dict) or not snapshot:
        return False

    def snapshot_float(key: str, fallback: float) -> float:
        try:
            value = snapshot.get(key, fallback)
            return float(fallback if value in (None, "") else value)
        except (TypeError, ValueError):
            return float(fallback)

    def snapshot_point(key: str) -> dict[str, float] | None:
        point = snapshot.get(key)
        if not isinstance(point, dict):
            return None
        try:
            return {
                "x_m": float(point["x_m"]),
                "y_m": float(point["y_m"]),
                "z_m": float(point.get("z_m", 0.0)),
            }
        except (KeyError, TypeError, ValueError):
            return None

    start = snapshot_point("start")
    end = snapshot_point("end")
    if start is None or end is None:
        start = point_from_distance_rotation_height(
            snapshot_float("start_distance_cm", spec.start_radius_m * 100.0),
            snapshot_float("start_rotation_deg", azimuth_to_display_rotation_deg(spec.azimuth_start_deg)),
            snapshot_float("start_height_cm", 0.0),
        )
        end = point_from_distance_rotation_height(
            snapshot_float("end_distance_cm", spec.end_radius_m * 100.0),
            snapshot_float("end_rotation_deg", azimuth_to_display_rotation_deg(spec.azimuth_end_deg)),
            snapshot_float("end_height_cm", 0.0),
        )

    start_spherical = cartesian_to_spherical(start["x_m"], start["y_m"], start["z_m"])
    end_spherical = cartesian_to_spherical(end["x_m"], end["y_m"], end["z_m"])
    path_length = snapshot_float(
        "path_length_m",
        math.dist((start["x_m"], start["y_m"], start["z_m"]), (end["x_m"], end["y_m"], end["z_m"])),
    )
    movement_duration_s = snapshot_float("movement_duration_s", spec.movement_duration_s)

    spec.coordinate_mode = str(snapshot.get("coordinate_mode") or "cartesian")
    spec.path_direction = str(snapshot.get("path_direction") or "custom")
    spec.start_x_m = start["x_m"]
    spec.start_y_m = start["y_m"]
    spec.start_z_m = start["z_m"]
    spec.end_x_m = end["x_m"]
    spec.end_y_m = end["y_m"]
    spec.end_z_m = end["z_m"]
    spec.start_radius_m = float(start_spherical["radius_m"])
    spec.end_radius_m = float(end_spherical["radius_m"])
    spec.azimuth_start_deg = float(start_spherical["azimuth_deg"])
    spec.azimuth_end_deg = float(end_spherical["azimuth_deg"])
    spec.elevation_deg = float(start_spherical["elevation_deg"])
    spec.path_length_m = max(0.0, float(path_length))
    spec.propagation_speed_mps = spec.path_length_m / movement_duration_s if movement_duration_s > 0 else 0.0
    spec.padding_pre_s = max(0.0, snapshot_float("start_hold_s", spec.padding_pre_s))
    spec.padding_post_s = max(0.0, snapshot_float("end_hold_s", spec.padding_post_s))
    return True


def trajectory_endpoints_xyz(spec: TrajectorySpec) -> tuple[dict[str, float], dict[str, float]]:
    if _uses_cartesian_coordinates(spec) and all(
        value is not None
        for value in (spec.start_x_m, spec.start_y_m, spec.start_z_m, spec.end_x_m, spec.end_y_m, spec.end_z_m)
    ):
        return (
            {"x_m": float(spec.start_x_m), "y_m": float(spec.start_y_m), "z_m": float(spec.start_z_m)},
            {"x_m": float(spec.end_x_m), "y_m": float(spec.end_y_m), "z_m": float(spec.end_z_m)},
        )

    az0, az1 = _default_azimuths_for_direction(spec)
    return (
        spherical_to_cartesian(spec.start_radius_m, az0, spec.elevation_deg),
        spherical_to_cartesian(spec.end_radius_m, az1, spec.elevation_deg),
    )


def validate_design(design: StimulusDesign) -> list[str]:
    warnings: list[str] = []
    if not design.noises and not design.custom_looming_files:
        warnings.append("At least one procedural noise definition or custom looming audio source is required.")
    for noise in design.noises:
        if noise.noise_type.lower() not in SUPPORTED_NOISE_TYPES:
            warnings.append(f"Unsupported noise type for {noise.label}: {noise.noise_type}")
        if not -180.0 <= noise.azimuth_deg <= 180.0:
            warnings.append(f"Azimuth for {noise.label} should be between -180 and 180 degrees.")
        if not -90.0 <= noise.elevation_deg <= 90.0:
            warnings.append(f"Elevation for {noise.label} should be between -90 and 90 degrees.")
        if noise.gain <= 0:
            warnings.append(f"Gain for {noise.label} must be positive.")
        if noise.sequence_order < 0:
            warnings.append(f"{noise.label} sequence order cannot be negative.")
        if noise.motion_mode not in SUPPORTED_STIMULUS_MOTION_MODES:
            warnings.append(f"{noise.label} stimulus motion mode is unsupported: {noise.motion_mode}")

    for label, files in [
        ("custom looming", design.custom_looming_files),
        ("prestimulus", design.prestimulus_files),
    ]:
        for asset in files:
            if not asset.label.strip():
                warnings.append(f"A {label} file is missing a label.")
            if not asset.path.strip():
                warnings.append(f"{asset.label or label.title()} is missing a file path.")
            elif not _resolve_design_asset_path(asset.path).exists():
                warnings.append(f"{asset.label} file was not found: {asset.path}")
            if asset.target_duration_s <= 0:
                warnings.append(f"{asset.label} target duration must be positive.")
            if asset.render_mode not in SUPPORTED_IMPORTED_AUDIO_RENDER_MODES:
                warnings.append(f"{asset.label} imported audio render mode is unsupported: {asset.render_mode}")
            if asset.gain <= 0:
                warnings.append(f"{asset.label} gain must be positive.")
            if asset.placement not in SUPPORTED_STIMULUS_SNIPPET_PLACEMENTS:
                warnings.append(f"{asset.label} stimulus snippet placement is unsupported: {asset.placement}")
            if asset.gap_s < 0:
                warnings.append(f"{asset.label} stimulus snippet gap cannot be negative.")
            if asset.sequence_order < 0:
                warnings.append(f"{asset.label} sequence order cannot be negative.")
            if asset.motion_mode not in SUPPORTED_STIMULUS_MOTION_MODES:
                warnings.append(f"{asset.label} stimulus motion mode is unsupported: {asset.motion_mode}")

    t = design.trajectory
    if t.path_direction not in SUPPORTED_DIRECTIONS:
        warnings.append(f"Unsupported path direction: {t.path_direction}")
    if t.coordinate_mode not in SUPPORTED_COORDINATE_MODES:
        warnings.append(f"Unsupported coordinate mode: {t.coordinate_mode}")
    if _uses_cartesian_coordinates(t):
        start = (t.start_x_m, t.start_y_m, t.start_z_m)
        end = (t.end_x_m, t.end_y_m, t.end_z_m)
        if any(value is None for value in (*start, *end)):
            warnings.append("Cartesian trajectories require start and end X/Y/Z coordinates.")
        elif math.dist(start, end) <= 0:
            warnings.append("Start and end coordinates must not be identical.")
    if not _uses_cartesian_coordinates(t) and (t.start_radius_m <= 0 or t.end_radius_m <= 0):
        warnings.append("Start and end radius must be positive.")
    if t.path_length_m <= 0:
        warnings.append("Path length must be positive.")
    if t.propagation_speed_mps <= 0:
        warnings.append("Propagation speed must be positive.")
    radial_delta = abs(t.start_radius_m - t.end_radius_m)
    if not _uses_cartesian_coordinates(t) and t.path_direction in {"approach", "recede"} and abs(t.path_length_m - radial_delta) > 0.05:
        warnings.append("Radial path length differs from the start/end radius difference.")

    p = design.protocol
    if p.repetitions_per_condition < 1:
        warnings.append("Repetitions per condition must be at least 1.")
    for key, value in (p.trial_pool_repetition_defaults or {}).items():
        try:
            parsed_value = float(value)
        except (TypeError, ValueError):
            warnings.append(f"Trial-pool repetition default for {key} must be numeric.")
            continue
        if parsed_value < 0:
            warnings.append(f"Trial-pool repetition default for {key} cannot be negative.")
        if abs((parsed_value * 2) - round(parsed_value * 2)) > 1e-7:
            warnings.append(f"Trial-pool repetition default for {key} must use 0.5 increments.")
    if not p.soa_values_ms:
        warnings.append("At least one SOA value is required.")
    if any(soa < 0 for soa in p.soa_values_ms):
        warnings.append("SOA values must be non-negative.")
    using_trial_strips = has_trial_strips(p)
    if not using_trial_strips and not p.spatial_values_cm:
        warnings.append("At least one spatial value is required.")
    if p.spatial_values_cm and any(value <= 0 for value in p.spatial_values_cm):
        warnings.append("Spatial values must be positive.")
    if not using_trial_strips and p.pair_spatial_values_with_soas and len(p.soa_values_ms) != len(p.spatial_values_cm):
        warnings.append("Paired SOA/spatial mode expects the same number of SOAs and spatial values.")
    if not p.auditory_motion_directions:
        warnings.append("At least one auditory motion direction is required.")
    if not p.tactile_sites:
        warnings.append("At least one tactile body site is required.")
    if not 0 <= p.catch_trial_percentage < 100:
        warnings.append("Catch-trial percentage must be between 0 and 99.9.")
    if p.catch_trials_exact is not None and p.catch_trials_exact < 0:
        warnings.append("Exact catch-trial count cannot be negative.")
    if not 0 <= p.auditory_only_trial_percentage < 100:
        warnings.append("Auditory-only trial percentage must be between 0 and 99.9.")
    if p.auditory_only_trials_exact is not None and p.auditory_only_trials_exact < 0:
        warnings.append("Exact auditory-only trial count cannot be negative.")
    if p.baseline_trials_exact is not None and p.baseline_trials_exact < 0:
        warnings.append("Exact baseline-trial count cannot be negative.")
    if p.baseline_strategy not in SUPPORTED_BASELINE_STRATEGIES:
        warnings.append(f"Unsupported baseline strategy: {p.baseline_strategy}")
    if p.baseline_custom_trial_mode not in SUPPORTED_BASELINE_CUSTOM_TRIAL_MODES:
        warnings.append(f"Unsupported custom baseline mode: {p.baseline_custom_trial_mode}")
    if not 0 <= p.baseline_trial_percentage < 100:
        warnings.append("Baseline-trial percentage must be between 0 and 99.9.")
    if p.include_baseline_trials and p.baseline_strategy == "custom" and not p.baseline_soa_values_ms:
        warnings.append("Custom baseline strategy requires at least one baseline timing value.")
    if any(soa < -10000 for soa in p.baseline_soa_values_ms):
        warnings.append("Baseline SOA values look implausibly early.")
    if not using_trial_strips and not p.respiratory_phases:
        warnings.append("At least one respiratory phase is required.")
    if p.blocks < 1:
        warnings.append("Block count must be at least 1.")
    if p.trial_randomization_strategy not in SUPPORTED_TRIAL_RANDOMIZATION:
        warnings.append(f"Unsupported trial randomization strategy: {p.trial_randomization_strategy}")
    if p.block_order_randomization not in SUPPORTED_BLOCK_ORDER_RANDOMIZATION:
        warnings.append(f"Unsupported block order randomization strategy: {p.block_order_randomization}")
    if p.max_consecutive_same_trial_type < 1:
        warnings.append("Maximum consecutive same trial type must be at least 1.")
    source_labels = {str(source["label"]) for source in protocol_sound_sources(design)}
    fixed_audio_labels = {asset.label for asset in design.prestimulus_files if asset.label.strip()}
    for strip_index, strip in enumerate(p.trial_strips, start=1):
        strip_label = strip.label.strip() or f"Row {strip_index}"
        if any(soa < 0 for soa in strip.soa_values_ms):
            warnings.append(f"{strip_label} SOA overrides must be non-negative.")
        if any(value <= 0 for value in strip.spatial_values_cm):
            warnings.append(f"{strip_label} spatial overrides must be positive.")
        if p.pair_spatial_values_with_soas and strip.soa_values_ms and strip.spatial_values_cm and len(strip.soa_values_ms) != len(strip.spatial_values_cm):
            warnings.append(f"{strip_label} paired SOA/spatial overrides should have the same length.")
        if _strip_has_explicit_mix(strip):
            for label, raw_value in (
                ("audio-tactile", strip.audio_tactile_percentage),
                ("catch", strip.catch_percentage),
                ("baseline", strip.baseline_percentage),
            ):
                if raw_value is not None and not 0 <= raw_value <= 100:
                    warnings.append(f"{strip_label} {label} percentage must be between 0 and 100.")
            mix = _strip_mix_values(strip, p)
            if mix["audio_tactile"] <= 0:
                warnings.append(f"{strip_label} must keep audio-tactile percentage above 0% for row-based trial mixing.")
            total_mix = mix["audio_tactile"] + mix["catch"] + mix["baseline"]
            if not 99.5 <= total_mix <= 100.5:
                warnings.append(f"{strip_label} row percentages should sum to 100%.")
            if mix["baseline"] > 0 and _baseline_strategy(p) == "none":
                warnings.append(f"{strip_label} baseline percentage requires an active baseline strategy.")
        if not strip.elements:
            warnings.append(f"{strip_label} must contain at least one filmstrip element.")
            continue
        for element in strip.elements:
            if element.kind not in SUPPORTED_TRIAL_STRIP_ELEMENT_TYPES:
                warnings.append(f"{strip_label} contains unsupported filmstrip element type: {element.kind}")
            if element.kind == "fixed_audio":
                labels = _audio_choice_labels(element)
                if not labels:
                    warnings.append(f"{strip_label} audio box requires at least one selected clip or stimulus.")
                unknown_fixed = [
                    label
                    for label in labels
                    if label not in fixed_audio_labels and label not in source_labels
                ]
                if unknown_fixed:
                    warnings.append(f"{strip_label} references unknown audio/stimulus source(s): {', '.join(unknown_fixed)}")
            if element.kind == "looming_stimulus":
                labels = _audio_choice_labels(element)
                if not labels:
                    warnings.append(f"{strip_label} looming stimulus box requires at least one selected stimulus source.")
                unknown_sources = [
                    label
                    for label in labels
                    if label and label not in source_labels
                ]
                if unknown_sources:
                    warnings.append(f"{strip_label} references unknown stimulus source(s): {', '.join(unknown_sources)}")
            if element.kind == "jitter" and not _jitter_values_ms(element):
                warnings.append(f"{strip_label} jitter event requires at least one non-negative timing value.")
    block_specs = effective_block_specs(p)
    if not block_specs:
        warnings.append("At least one block must be defined.")
    for block in block_specs:
        if not block.label.strip():
            warnings.append("A block is missing a label.")
        if not block.stimulus_types:
            warnings.append(f"{block.label or 'Block'} must include at least one stimulus type.")
        for stimulus_type in block.stimulus_types:
            if stimulus_type not in SUPPORTED_TRIAL_TYPES:
                warnings.append(f"Unsupported stimulus type in {block.label}: {stimulus_type}")
    row_catch_required = any(_strip_has_explicit_mix(strip) and _strip_mix_values(strip, p)["catch"] > 0 for strip in p.trial_strips)
    row_baseline_required = any(_strip_has_explicit_mix(strip) and _strip_mix_values(strip, p)["baseline"] > 0 for strip in p.trial_strips)
    row_legacy_baseline_required = (
        p.include_baseline_trials
        and _baseline_strategy(p) != "none"
        and any(strip.elements and not _strip_has_explicit_mix(strip) for strip in p.trial_strips)
    )
    protocol_legacy_baseline_required = (
        p.include_baseline_trials
        and _baseline_strategy(p) != "none"
        and not using_trial_strips
    )
    required_types = {"Audio-Tactile"}
    if p.catch_trials_exact is not None and p.catch_trials_exact > 0:
        required_types.add("Catch")
    elif p.catch_trial_percentage > 0 or row_catch_required:
        required_types.add("Catch")
    if p.auditory_only_trials_exact is not None and p.auditory_only_trials_exact > 0:
        required_types.add("Auditory-Only")
    elif p.include_auditory_only_trials and p.auditory_only_trial_percentage >= 0:
        required_types.add("Auditory-Only")
    if row_baseline_required or row_legacy_baseline_required or protocol_legacy_baseline_required:
        required_types.add("Baseline")
    available_types = {stimulus_type for block in block_specs for stimulus_type in block.stimulus_types}
    missing_types = sorted(required_types - available_types)
    if missing_types:
        warnings.append(f"No block accepts required stimulus type(s): {', '.join(missing_types)}")
    if p.participants < 1:
        warnings.append("Participant count must be at least 1.")
    return warnings


def effective_block_specs(protocol: ProtocolSpec) -> list[BlockSpec]:
    if protocol.block_specs:
        return [
            BlockSpec(
                label=block.label,
                stimulus_types=[trial_type for trial_type in block.stimulus_types if trial_type],
            )
            for block in protocol.block_specs
        ]
    stimulus_types = list(DEFAULT_BLOCK_STIMULUS_TYPES)
    if protocol.include_auditory_only_trials and "Auditory-Only" not in stimulus_types:
        stimulus_types.append("Auditory-Only")
    return [
        BlockSpec(label=f"Block {idx + 1}", stimulus_types=list(stimulus_types))
        for idx in range(max(1, protocol.blocks))
    ]


def protocol_factor_pairs(protocol: ProtocolSpec) -> list[tuple[int, float]]:
    if protocol.pair_spatial_values_with_soas:
        return list(zip(protocol.soa_values_ms, protocol.spatial_values_cm))
    return [
        (soa, spatial)
        for soa in protocol.soa_values_ms
        for spatial in protocol.spatial_values_cm
    ]


def _baseline_strategy(protocol: ProtocolSpec) -> str:
    strategy = str(protocol.baseline_strategy or "").strip().lower()
    if not protocol.include_baseline_trials:
        return "none"
    if strategy in SUPPORTED_BASELINE_STRATEGIES:
        return strategy
    return "tactile_only"


def _sound_offset_ms(trajectory: TrajectorySpec | None) -> int:
    if trajectory is None:
        return 0
    return int(round(max(0.0, trajectory.total_duration_s) * 1000.0))


def baseline_timing_values_ms(protocol: ProtocolSpec, trajectory: TrajectorySpec | None = None) -> list[int]:
    strategy = _baseline_strategy(protocol)
    if strategy == "none":
        return []
    if strategy == "min_anchor":
        if not protocol.soa_values_ms:
            return []
        return [protocol.soa_values_ms[0]]
    if strategy == "max_anchor":
        if not protocol.soa_values_ms:
            return []
        return [protocol.soa_values_ms[-1]]
    if strategy == "min_max":
        if not protocol.soa_values_ms:
            return []
        return list(dict.fromkeys([protocol.soa_values_ms[0], protocol.soa_values_ms[-1]]))
    if strategy == "soa_zero":
        return [0]
    if strategy == "sound_offset":
        return [_sound_offset_ms(trajectory)]
    if protocol.baseline_soa_values_ms:
        return list(protocol.baseline_soa_values_ms)
    if strategy == "custom":
        return []
    return [soa for soa, _spatial in protocol_factor_pairs(protocol)]


def baseline_factor_pairs(protocol: ProtocolSpec, trajectory: TrajectorySpec | None = None) -> list[tuple[int, float]]:
    timing_values = baseline_timing_values_ms(protocol, trajectory)
    if not timing_values:
        return []
    spatial = protocol.spatial_values_cm[0] if protocol.spatial_values_cm else 0.0
    return [(soa, spatial) for soa in timing_values]


def baseline_target_count(protocol: ProtocolSpec, reference_trial_count: int, candidate_count: int) -> int:
    if not protocol.include_baseline_trials or _baseline_strategy(protocol) == "none":
        return 0
    if candidate_count <= 0:
        return 0
    if protocol.baseline_trials_exact is not None:
        return int(protocol.baseline_trials_exact)
    percentage = float(protocol.baseline_trial_percentage or 0.0)
    if percentage <= 0:
        return candidate_count
    if reference_trial_count <= 0:
        return candidate_count
    return max(1, int(math.ceil(reference_trial_count * percentage / (100.0 - percentage))))


def _select_baseline_rows(candidates: list[dict[str, Any]], target_count: int) -> list[dict[str, Any]]:
    if not candidates or target_count <= 0:
        return []
    selected: list[dict[str, Any]] = []
    for index in range(target_count):
        row = dict(candidates[index % len(candidates)])
        row["baseline_sample_index"] = index + 1
        row["trial_unit_key"] = _slug(f"{row.get('trial_unit_key', 'baseline')}_{index + 1}")
        selected.append(row)
    return selected


def _bounded_percentage(value: float | None, fallback: float = 0.0) -> float:
    try:
        numeric = float(fallback if value is None else value)
    except (TypeError, ValueError):
        numeric = float(fallback)
    return max(0.0, min(100.0, numeric))


def _strip_has_explicit_mix(strip: TrialStripSpec) -> bool:
    return any(
        value is not None
        for value in (
            strip.audio_tactile_percentage,
            strip.catch_percentage,
            strip.baseline_percentage,
        )
    )


def _strip_mix_values(strip: TrialStripSpec, protocol: ProtocolSpec) -> dict[str, float]:
    catch = _bounded_percentage(strip.catch_percentage, protocol.catch_trial_percentage)
    baseline_fallback = protocol.baseline_trial_percentage if _baseline_strategy(protocol) != "none" else 0.0
    baseline = _bounded_percentage(strip.baseline_percentage, baseline_fallback)
    if strip.audio_tactile_percentage is None:
        audio_tactile = max(0.0, 100.0 - catch - baseline)
    else:
        audio_tactile = _bounded_percentage(strip.audio_tactile_percentage, 100.0)
    return {
        "audio_tactile": audio_tactile,
        "catch": catch,
        "baseline": baseline,
    }


def _strip_mix_metadata(strip: TrialStripSpec, protocol: ProtocolSpec) -> dict[str, float]:
    mix = _strip_mix_values(strip, protocol)
    return {
        "row_audio_tactile_percent": mix["audio_tactile"],
        "row_catch_percent": mix["catch"],
        "row_baseline_percent": mix["baseline"],
    }


_STRIP_METADATA_RESERVED_KEYS = {
    "trial_type",
    "repetition",
    "tactile_site",
    "motion_direction",
    "phase",
    "soa_ms",
    "spatial_value_cm",
    "noise_label",
    "noise_type",
    "azimuth_deg",
    "elevation_deg",
    "trial_strip_id",
    "trial_strip_label",
    "trial_strip_index",
    "trial_type_id",
    "trial_type_label",
    "trial_type_index",
    "sequence_variant_index",
    "tactile_enabled",
    "trial_unit_key",
}


def _strip_metadata(strip: TrialStripSpec) -> dict[str, Any]:
    if not isinstance(strip.metadata, dict):
        return {}
    return {
        str(key): value
        for key, value in strip.metadata.items()
        if str(key).strip() and str(key) not in _STRIP_METADATA_RESERVED_KEYS
    }


def _strip_soa_values(strip: TrialStripSpec, protocol: ProtocolSpec) -> list[int]:
    return list(strip.soa_values_ms or protocol.soa_values_ms)


def _strip_spatial_value_for_soa(strip: TrialStripSpec, protocol: ProtocolSpec, soa_index: int) -> float:
    spatial_values = list(strip.spatial_values_cm or protocol.spatial_values_cm)
    if not spatial_values:
        return 0.0
    if protocol.pair_spatial_values_with_soas:
        return spatial_values[min(soa_index, len(spatial_values) - 1)]
    return spatial_values[0]


def _row_extra_count(reference_count: int, extra_percentage: float, audio_tactile_percentage: float) -> int:
    if reference_count <= 0 or extra_percentage <= 0:
        return 0
    return int(math.ceil(reference_count * extra_percentage / max(0.1, audio_tactile_percentage)))


def has_trial_strips(protocol: ProtocolSpec) -> bool:
    return any(strip.elements for strip in protocol.trial_strips)


def _strip_looming_events(strip: TrialStripSpec) -> list[TrialStripElementSpec]:
    return [element for element in strip.elements if element.kind == "looming_stimulus"]


def _source_by_label(design: StimulusDesign) -> dict[str, dict[str, Any]]:
    return {str(source["label"]): source for source in protocol_sound_sources(design)}


def _fixed_audio_by_label(design: StimulusDesign) -> dict[str, AudioFileSpec]:
    return {asset.label: asset for asset in design.prestimulus_files if asset.label.strip()}


def _strip_sources(design: StimulusDesign, slot: TrialStripElementSpec | None) -> list[dict[str, Any]]:
    sources = _source_by_label(design)
    if not slot:
        return []
    labels = [label for label in slot.source_labels if label]
    if not labels:
        return list(sources.values())
    return [sources[label] for label in labels if label in sources]


def _audio_choice_labels(element: TrialStripElementSpec) -> list[str]:
    labels = [str(label).strip() for label in element.source_labels if str(label).strip()]
    if not labels and str(element.source_label or "").strip():
        labels = [str(element.source_label).strip()]
    return list(dict.fromkeys(labels))


def _normalized_motion_direction_labels(protocol: ProtocolSpec) -> list[str]:
    labels: list[str] = []
    for value in protocol.auditory_motion_directions or []:
        label = re.sub(r"[\s-]+", "_", str(value or "").strip().lower())
        if label:
            labels.append(label)
    return list(dict.fromkeys(labels))


def _motion_direction_display_label(direction: str) -> str:
    return str(direction or "").replace("_", " ").strip()


def _directional_source_choices(
    design: StimulusDesign,
    label: str,
    source: dict[str, Any],
    selected_labels: list[str],
) -> list[dict[str, Any]]:
    directions = _normalized_motion_direction_labels(design.protocol)
    if len(directions) <= 1 or len(selected_labels) != 1:
        return []
    choices: list[dict[str, Any]] = []
    for index, direction in enumerate(directions):
        variant_source = dict(source)
        variant_label = str(label) if index == 0 else f"{label} - {_motion_direction_display_label(direction)}"
        variant_source["label"] = variant_label
        variant_source["motion_direction"] = direction
        choices.append(
            {
                "kind": "looming_stimulus",
                "label": variant_label,
                "source": variant_source,
            }
        )
    return choices


def _strip_element_choices(design: StimulusDesign, element: TrialStripElementSpec) -> list[dict[str, Any]]:
    fixed = _fixed_audio_by_label(design)
    sources = _source_by_label(design)
    if element.kind == "jitter":
        values = _jitter_values_ms(element)
        return [
            {
                "kind": "jitter",
                "label": element.label or "Jitter",
                "jitter_ms": value,
            }
            for value in values
        ]
    if element.kind == "looming_stimulus":
        labels = _audio_choice_labels(element) or list(sources)
    else:
        labels = _audio_choice_labels(element)
    choices: list[dict[str, Any]] = []
    for label in labels:
        if label in fixed:
            asset = fixed[label]
            choices.append(
                {
                    "kind": "fixed_audio",
                    "label": asset.label,
                    "path": asset.path,
                    "gain": asset.gain,
                }
            )
        elif label in sources:
            source = sources[label]
            directional_choices = _directional_source_choices(design, label, source, labels)
            if directional_choices:
                choices.extend(directional_choices)
                continue
            choices.append(
                {
                    "kind": "looming_stimulus",
                    "label": str(source.get("label", label)),
                    "source": source,
                }
            )
    return choices


def _strip_variant_choices(design: StimulusDesign, strip: TrialStripSpec) -> list[tuple[dict[str, Any], ...]]:
    factors: list[list[dict[str, Any]]] = []
    for element in strip.elements:
        choices = _strip_element_choices(design, element)
        if not choices:
            return []
        factors.append(choices)
    if not factors:
        return []
    return [tuple(variant) for variant in itertools.product(*factors)]


def _variant_slug(variant: tuple[dict[str, Any], ...]) -> str:
    parts: list[str] = []
    for choice in variant:
        if choice.get("kind") == "jitter":
            parts.append(f"jitter_{choice.get('jitter_ms', 0)}ms")
        else:
            parts.append(str(choice.get("label") or "audio"))
    return _slug("_".join(parts) or "variant")


def _variant_metadata(strip: TrialStripSpec, variant: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    sequence_labels: list[str] = []
    fixed_labels: list[str] = []
    fixed_paths: list[str] = []
    source_labels: list[str] = []
    jitter_labels: list[str] = []
    jitter_values: list[int] = []
    primary_source: dict[str, Any] | None = None
    for choice in variant:
        kind = choice.get("kind")
        if kind == "jitter":
            value = int(choice.get("jitter_ms") or 0)
            label = str(choice.get("label") or "Jitter")
            sequence_labels.append(f"{label} ({value} ms)")
            jitter_labels.append(label)
            jitter_values.append(value)
        elif kind == "fixed_audio":
            label = str(choice.get("label") or "Fixed audio")
            sequence_labels.append(label)
            fixed_labels.append(label)
            fixed_paths.append(str(choice.get("path") or ""))
        else:
            source = dict(choice.get("source") or {})
            label = str(choice.get("label") or source.get("label") or "Looming stimulus")
            sequence_labels.append(label)
            source_labels.append(label)
            if primary_source is None:
                primary_source = source
    variant_label = " + ".join(sequence_labels) if sequence_labels else (strip.label or "Trial sequence")
    return {
        "sequence_labels": " | ".join(sequence_labels),
        "fixed_audio_labels": "; ".join(fixed_labels),
        "fixed_audio_paths": "; ".join(fixed_paths),
        "jitter_labels": "; ".join(jitter_labels),
        "jitter_values_ms": "; ".join(str(value) for value in jitter_values),
        "jitter_total_ms": sum(jitter_values) if jitter_values else "",
        "sequence_source_labels": "; ".join(source_labels),
        "sequence_variant_label": variant_label,
        "sequence_variant_key": _variant_slug(variant),
        "sequence_variant_path": "",
        "primary_source": primary_source or {},
    }


def _strip_fixed_audio(strip: TrialStripSpec, design: StimulusDesign) -> list[AudioFileSpec]:
    fixed = _fixed_audio_by_label(design)
    clips: list[AudioFileSpec] = []
    for element in strip.elements:
        if element.kind != "fixed_audio":
            continue
        for label in _audio_choice_labels(element):
            clip = fixed.get(label)
            if clip:
                clips.append(clip)
    return clips


def _jitter_values_ms(element: TrialStripElementSpec) -> list[int]:
    values: list[int] = []
    for value in element.jitter_values_ms:
        try:
            timing = int(value)
        except (TypeError, ValueError):
            continue
        if timing >= 0:
            values.append(timing)
    return values


def _strip_jitter_events(strip: TrialStripSpec) -> list[TrialStripElementSpec]:
    return [element for element in strip.elements if element.kind == "jitter"]


def _strip_jitter_assignment(strip: TrialStripSpec, sequence_index: int) -> tuple[int, ...]:
    values: list[int] = []
    for element in _strip_jitter_events(strip):
        event_values = _jitter_values_ms(element) or [0]
        values.append(event_values[sequence_index % len(event_values)])
    return tuple(values)


def _strip_source_assignment(
    design: StimulusDesign,
    strip: TrialStripSpec,
    primary_source_label: str,
    sequence_index: int,
) -> tuple[str, ...]:
    labels: list[str] = []
    for event_index, element in enumerate(_strip_looming_events(strip)):
        if event_index == 0:
            labels.append(primary_source_label or element.label or "Looming Stimulus")
            continue
        source_choices = [
            str(source.get("label", ""))
            for source in _strip_sources(design, element)
            if str(source.get("label", "")).strip()
        ]
        labels.append(source_choices[sequence_index % len(source_choices)] if source_choices else primary_source_label)
    return tuple(labels)


def _jitter_metadata(strip: TrialStripSpec, jitter_values: tuple[int, ...]) -> dict[str, Any]:
    events = _strip_jitter_events(strip)
    if not events:
        return {
            "jitter_labels": "",
            "jitter_values_ms": "",
            "jitter_total_ms": "",
        }
    labels: list[str] = []
    values: list[int] = []
    for index, element in enumerate(events):
        labels.append(element.label or "Jitter")
        values.append(int(jitter_values[index]) if index < len(jitter_values) else 0)
    return {
        "jitter_labels": "; ".join(labels),
        "jitter_values_ms": "; ".join(str(value) for value in values),
        "jitter_total_ms": sum(values),
    }


def _strip_sequence_labels(
    strip: TrialStripSpec,
    source_label: str,
    jitter_values: tuple[int, ...] = (),
    source_labels: tuple[str, ...] = (),
) -> list[str]:
    labels: list[str] = []
    jitter_index = 0
    source_index = 0
    for element in strip.elements:
        if element.kind == "fixed_audio":
            labels.append(element.label or element.source_label or "Fixed audio")
        elif element.kind == "looming_stimulus":
            label = source_labels[source_index] if source_index < len(source_labels) else source_label
            labels.append(label or element.label or "Looming Stimulus")
            source_index += 1
        elif element.kind == "jitter":
            timing = int(jitter_values[jitter_index]) if jitter_index < len(jitter_values) else 0
            labels.append(f"{element.label or 'Jitter'} ({timing} ms)")
            jitter_index += 1
    return labels


def _spatial_value_for_soa(protocol: ProtocolSpec, soa_index: int) -> float:
    if not protocol.spatial_values_cm:
        return 0.0
    if protocol.pair_spatial_values_with_soas:
        return protocol.spatial_values_cm[min(soa_index, len(protocol.spatial_values_cm) - 1)]
    return protocol.spatial_values_cm[0]


def _filmstrip_condition_rows_for_strip(
    design: StimulusDesign,
    strip: TrialStripSpec,
    strip_index: int,
) -> list[dict[str, Any]]:
    protocol = design.protocol
    variants = _strip_variant_choices(design, strip)
    strip_id = strip.strip_id or f"strip-{strip_index}"
    strip_label = strip.label or f"Row {strip_index}"
    trial_type_label = strip_label
    row_mix = _strip_mix_metadata(strip, protocol)
    row_metadata = _strip_metadata(strip)
    soa_values = _strip_soa_values(strip, protocol)
    rows: list[dict[str, Any]] = []
    tactile_sites = protocol.tactile_sites or ["hand"]

    for repetition in range(1, protocol.repetitions_per_condition + 1):
        for tactile_site in tactile_sites:
            for soa_index, soa_ms in enumerate(soa_values):
                spatial_cm = _strip_spatial_value_for_soa(strip, protocol, soa_index)
                for variant_index, variant in enumerate(variants, start=1):
                    metadata = _variant_metadata(strip, variant)
                    source = metadata.pop("primary_source", {})
                    source_label = str(source.get("label") or metadata.get("sequence_variant_label") or "")
                    motion_direction = str(source.get("motion_direction") or ("looming" if source else ""))
                    variant_key = str(metadata.get("sequence_variant_key") or f"variant_{variant_index}")
                    unit_key = f"{strip_id}_{variant_key}_{soa_ms}_{repetition}"
                    rows.append(
                        {
                            "trial_type": "Audio-Tactile",
                            "repetition": repetition,
                            "tactile_site": tactile_site,
                            "motion_direction": motion_direction,
                            "phase": strip_label,
                            "soa_ms": soa_ms,
                            "spatial_value_cm": spatial_cm,
                            "noise_label": source_label,
                            "noise_type": source.get("noise_type", ""),
                            "azimuth_deg": source.get("azimuth_deg", ""),
                            "elevation_deg": source.get("elevation_deg", ""),
                            "trial_strip_id": strip_id,
                            "trial_strip_label": strip_label,
                            "trial_strip_index": strip_index,
                            "trial_type_id": strip_id,
                            "trial_type_label": trial_type_label,
                            "trial_type_index": strip_index,
                            "sequence_variant_index": variant_index,
                            **row_mix,
                            "tactile_enabled": True,
                            **metadata,
                            **row_metadata,
                            "trial_unit_key": _slug(unit_key),
                        }
                    )
    return rows


def _filmstrip_baseline_rows_for_strip(
    design: StimulusDesign,
    strip: TrialStripSpec,
    strip_index: int,
) -> list[dict[str, Any]]:
    protocol = design.protocol
    baseline_pairs = baseline_factor_pairs(protocol, design.trajectory)
    if not baseline_pairs:
        return []
    variants = _strip_variant_choices(design, strip)
    if not protocol.baseline_crosses_sequence_variants:
        variants = variants[:1]
    strip_id = strip.strip_id or f"strip-{strip_index}"
    strip_label = strip.label or f"Event {strip_index}"
    trial_type_label = strip_label
    row_mix = _strip_mix_metadata(strip, protocol)
    row_metadata = _strip_metadata(strip)
    rows: list[dict[str, Any]] = []
    tactile_sites = protocol.tactile_sites or ["hand"]

    for repetition in range(1, protocol.repetitions_per_condition + 1):
        for tactile_site in tactile_sites:
            for soa_ms, spatial_cm in baseline_pairs:
                for variant_index, variant in enumerate(variants, start=1):
                    metadata = _variant_metadata(strip, variant)
                    source = dict(metadata.pop("primary_source", {}) or {})
                    motion_direction = str(source.get("motion_direction") or "")
                    sequence_labels = [
                        label
                        for label in str(metadata.get("sequence_labels") or "").split(" | ")
                        if label
                    ]
                    if "Baseline tactile" not in sequence_labels:
                        sequence_labels.append("Baseline tactile")
                    metadata["sequence_labels"] = " | ".join(sequence_labels)
                    metadata["sequence_source_labels"] = ""
                    variant_key = str(metadata.get("sequence_variant_key") or f"variant_{variant_index}")
                    unit_key = f"{strip_id}_baseline_{variant_key}_{soa_ms}_{repetition}"
                    rows.append(
                        {
                            "trial_type": "Baseline",
                            "repetition": repetition,
                            "tactile_site": tactile_site,
                            "motion_direction": motion_direction,
                            "phase": strip_label,
                            "soa_ms": soa_ms,
                            "spatial_value_cm": spatial_cm,
                            "noise_label": "",
                            "noise_type": "",
                            "azimuth_deg": "",
                            "elevation_deg": "",
                            "trial_strip_id": strip_id,
                            "trial_strip_label": strip_label,
                            "trial_strip_index": strip_index,
                            "trial_type_id": strip_id,
                            "trial_type_label": trial_type_label,
                            "trial_type_index": strip_index,
                            "sequence_variant_index": variant_index,
                            **row_mix,
                            "tactile_enabled": True,
                            **metadata,
                            **row_metadata,
                            "trial_unit_key": _slug(unit_key),
                            "baseline_strategy": _baseline_strategy(protocol),
                        }
                    )
    return rows


def _filmstrip_catch_rows(rows: list[dict[str, Any]], protocol: ProtocolSpec, catch_count: int) -> list[dict[str, Any]]:
    if not rows or catch_count <= 0:
        return []
    template_rows = rows if protocol.catch_crosses_sequence_variants else rows[:1]
    catches: list[dict[str, Any]] = []
    for index in range(catch_count):
        template = dict(template_rows[index % len(template_rows)])
        template["trial_type"] = "Catch"
        template["repetition"] = ""
        template["tactile_enabled"] = False
        template["expected_response"] = "withhold"
        template["target_role"] = "catch_no_target"
        template["response_rule"] = template.get("response_rule") or "withhold_response_to_audio_only_catch"
        template["trial_unit_key"] = _slug(f"{template.get('trial_unit_key', 'catch')}_catch_{index + 1}")
        catches.append(template)
    return catches


def _filmstrip_auditory_only_rows(
    rows: list[dict[str, Any]],
    protocol: ProtocolSpec,
    auditory_only_count: int,
) -> list[dict[str, Any]]:
    if not rows or auditory_only_count <= 0:
        return []
    template_rows = rows if protocol.auditory_only_crosses_sequence_variants else rows[:1]
    auditory_rows: list[dict[str, Any]] = []
    for index in range(auditory_only_count):
        template = dict(template_rows[index % len(template_rows)])
        template["trial_type"] = "Auditory-Only"
        template["repetition"] = ""
        template["tactile_enabled"] = False
        template["expected_response"] = template.get("expected_response") or "respond"
        template["target_role"] = template.get("target_role") or "auditory_target"
        template["response_rule"] = template.get("response_rule") or "respond_to_auditory_target"
        template["trial_unit_key"] = _slug(f"{template.get('trial_unit_key', 'auditory')}_auditory_only_{index + 1}")
        auditory_rows.append(template)
    return auditory_rows


def _with_filmstrip_catches(
    rows: list[dict[str, Any]],
    protocol: ProtocolSpec,
    strip: TrialStripSpec | None = None,
) -> list[dict[str, Any]]:
    if strip is not None and _strip_has_explicit_mix(strip):
        mix = _strip_mix_values(strip, protocol)
        catch_count = _row_extra_count(len(rows), mix["catch"], mix["audio_tactile"])
    elif protocol.catch_trials_exact is not None:
        catch_count = protocol.catch_trials_exact
    elif protocol.catch_trial_percentage > 0:
        catch_count = int(math.ceil(len(rows) * protocol.catch_trial_percentage / (100.0 - protocol.catch_trial_percentage)))
    else:
        catch_count = 0
    if not rows or catch_count <= 0:
        return rows
    return [*rows, *_filmstrip_catch_rows(rows, protocol, catch_count)]


def _with_filmstrip_auditory_only(
    rows: list[dict[str, Any]],
    protocol: ProtocolSpec,
) -> list[dict[str, Any]]:
    if not protocol.include_auditory_only_trials:
        return rows
    if protocol.auditory_only_trials_exact is not None:
        auditory_only_count = protocol.auditory_only_trials_exact
    elif protocol.auditory_only_trial_percentage > 0:
        auditory_only_count = int(math.ceil(len(rows) * protocol.auditory_only_trial_percentage / (100.0 - protocol.auditory_only_trial_percentage)))
    else:
        auditory_only_count = len(rows)
    if not rows or auditory_only_count <= 0:
        return rows
    return [*rows, *_filmstrip_auditory_only_rows(rows, protocol, auditory_only_count)]


def _row_baseline_target_count(
    strip: TrialStripSpec,
    protocol: ProtocolSpec,
    reference_trial_count: int,
    candidate_count: int,
) -> int:
    if not protocol.include_baseline_trials or _baseline_strategy(protocol) == "none":
        return 0
    if candidate_count <= 0:
        return 0
    if not _strip_has_explicit_mix(strip):
        return baseline_target_count(protocol, reference_trial_count, candidate_count)
    mix = _strip_mix_values(strip, protocol)
    return _row_extra_count(reference_trial_count, mix["baseline"], mix["audio_tactile"])


def _filmstrip_rows_for_stimulus_types(
    design: StimulusDesign,
    stimulus_types: set[str],
) -> list[dict[str, Any]]:
    protocol = design.protocol
    strips = [strip for strip in protocol.trial_strips if strip.elements]
    rows_by_strip: list[tuple[int, list[dict[str, Any]]]] = []
    baseline_candidates: list[dict[str, Any]] = []
    exact_catch_candidates: list[dict[str, Any]] = []
    exact_auditory_only_candidates: list[dict[str, Any]] = []
    legacy_baseline_audio_count = 0
    for strip_index, strip in enumerate(strips, start=1):
        audio_rows = (
            _filmstrip_condition_rows_for_strip(design, strip, strip_index)
            if any(trial_type in stimulus_types for trial_type in ("Audio-Tactile", "Catch", "Auditory-Only"))
            else []
        )
        rows = list(audio_rows) if "Audio-Tactile" in stimulus_types else []
        if "Auditory-Only" in stimulus_types and protocol.include_auditory_only_trials:
            if protocol.auditory_only_trials_exact is None:
                rows.extend(
                    row
                    for row in _with_filmstrip_auditory_only(audio_rows, protocol)
                    if row.get("trial_type") == "Auditory-Only"
                )
            else:
                exact_auditory_only_candidates.extend(audio_rows)
        if "Catch" in stimulus_types:
            if _strip_has_explicit_mix(strip) or protocol.catch_trials_exact is None:
                rows.extend(
                    row
                    for row in _with_filmstrip_catches(audio_rows, protocol, strip)
                    if row.get("trial_type") == "Catch"
                )
            else:
                exact_catch_candidates.extend(audio_rows)
        if "Baseline" in stimulus_types:
            strip_baseline_candidates = _filmstrip_baseline_rows_for_strip(design, strip, strip_index)
            if _strip_has_explicit_mix(strip):
                rows.extend(
                    _select_baseline_rows(
                        strip_baseline_candidates,
                        _row_baseline_target_count(
                            strip,
                            protocol,
                            len(audio_rows),
                            len(strip_baseline_candidates),
                        ),
                    )
                )
            else:
                baseline_candidates.extend(strip_baseline_candidates)
                legacy_baseline_audio_count += len(audio_rows)
        rows_by_strip.append((strip_index, rows))
    selected_baselines = _select_baseline_rows(
        baseline_candidates,
        baseline_target_count(protocol, legacy_baseline_audio_count, len(baseline_candidates)),
    )
    exact_catches = _filmstrip_catch_rows(
        exact_catch_candidates,
        protocol,
        int(protocol.catch_trials_exact or 0) if protocol.catch_trials_exact is not None else 0,
    )
    exact_auditory_only = _filmstrip_auditory_only_rows(
        exact_auditory_only_candidates,
        protocol,
        int(protocol.auditory_only_trials_exact or 0) if protocol.auditory_only_trials_exact is not None else 0,
    )
    catches_by_strip: dict[int, list[dict[str, Any]]] = {}
    for row in exact_catches:
        catches_by_strip.setdefault(int(row.get("trial_strip_index") or 0), []).append(row)
    auditory_only_by_strip: dict[int, list[dict[str, Any]]] = {}
    for row in exact_auditory_only:
        auditory_only_by_strip.setdefault(int(row.get("trial_strip_index") or 0), []).append(row)
    baselines_by_strip: dict[int, list[dict[str, Any]]] = {}
    for row in selected_baselines:
        baselines_by_strip.setdefault(int(row.get("trial_strip_index") or 0), []).append(row)
    combined: list[dict[str, Any]] = []
    for strip_index, rows in rows_by_strip:
        combined.extend(rows)
        combined.extend(catches_by_strip.get(strip_index, []))
        combined.extend(auditory_only_by_strip.get(strip_index, []))
        combined.extend(baselines_by_strip.get(strip_index, []))
    return combined


def _filmstrip_distributed_block_trial_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    protocol = design.protocol
    blocks = effective_block_specs(protocol)
    available_types = {
        trial_type
        for block in blocks
        for trial_type in block.stimulus_types
        if trial_type in set(SUPPORTED_TRIAL_TYPES)
    }
    pool_rows = _filmstrip_rows_for_stimulus_types(design, available_types)
    block_rows: dict[str, list[dict[str, Any]]] = {block.label: [] for block in blocks}
    rows_by_type: dict[str, list[dict[str, Any]]] = {trial_type: [] for trial_type in SUPPORTED_TRIAL_TYPES}
    for row in pool_rows:
        rows_by_type.setdefault(str(row.get("trial_type") or ""), []).append(row)

    for trial_type, rows in rows_by_type.items():
        if not rows:
            continue
        eligible_blocks = [block for block in blocks if trial_type in block.stimulus_types]
        if not eligible_blocks:
            continue
        shuffled = list(rows)
        random.Random(protocol.random_seed + sum(ord(ch) for ch in trial_type)).shuffle(shuffled)
        for idx, row in enumerate(shuffled):
            min_count = min(len(block_rows[block.label]) for block in eligible_blocks)
            candidates = [
                block
                for block in eligible_blocks
                if len(block_rows[block.label]) == min_count
            ]
            block = candidates[idx % len(candidates)]
            block_rows[block.label].append(dict(row))

    scheduled: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks, start=1):
        randomized = _randomize_rows(
            block_rows.get(block.label, []),
            protocol,
            seed=protocol.random_seed + block_index * 1009,
        )
        for block_trial_index, row in enumerate(randomized, start=1):
            scheduled.append(
                {
                    "block_index": block_index,
                    "block_label": block.label,
                    "block_trial_index": block_trial_index,
                    **row,
                }
            )
    return scheduled


def _filmstrip_block_trial_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    protocol = design.protocol
    if protocol.distribute_trial_pool_across_blocks and not protocol.repeat_trial_pool_per_block:
        return _filmstrip_distributed_block_trial_rows(design)
    scheduled: list[dict[str, Any]] = []
    strips = [strip for strip in protocol.trial_strips if strip.elements]
    for block_index, block in enumerate(effective_block_specs(protocol), start=1):
        if not any(trial_type in block.stimulus_types for trial_type in SUPPORTED_TRIAL_TYPES):
            continue
        strip_payloads: list[tuple[int, list[dict[str, Any]]]] = []
        baseline_candidates: list[dict[str, Any]] = []
        exact_catch_candidates: list[dict[str, Any]] = []
        exact_auditory_only_candidates: list[dict[str, Any]] = []
        legacy_baseline_audio_count = 0
        for strip_index, strip in enumerate(strips, start=1):
            audio_rows = (
                _filmstrip_condition_rows_for_strip(design, strip, strip_index)
                if any(trial_type in block.stimulus_types for trial_type in ("Audio-Tactile", "Catch", "Auditory-Only"))
                else []
            )
            rows = list(audio_rows) if "Audio-Tactile" in block.stimulus_types else []
            if "Auditory-Only" in block.stimulus_types and protocol.include_auditory_only_trials:
                if protocol.auditory_only_trials_exact is None:
                    rows.extend(
                        row
                        for row in _with_filmstrip_auditory_only(audio_rows, protocol)
                        if row.get("trial_type") == "Auditory-Only"
                    )
                else:
                    exact_auditory_only_candidates.extend(audio_rows)
            if "Catch" in block.stimulus_types:
                if _strip_has_explicit_mix(strip) or protocol.catch_trials_exact is None:
                    rows.extend(
                        row
                        for row in _with_filmstrip_catches(audio_rows, protocol, strip)
                        if row.get("trial_type") == "Catch"
                    )
                else:
                    exact_catch_candidates.extend(audio_rows)
            if "Baseline" in block.stimulus_types:
                strip_baseline_candidates = _filmstrip_baseline_rows_for_strip(design, strip, strip_index)
                if _strip_has_explicit_mix(strip):
                    rows.extend(
                        _select_baseline_rows(
                            strip_baseline_candidates,
                            _row_baseline_target_count(
                                strip,
                                protocol,
                                len(audio_rows),
                                len(strip_baseline_candidates),
                            ),
                        )
                    )
                else:
                    baseline_candidates.extend(strip_baseline_candidates)
                    legacy_baseline_audio_count += len(audio_rows)
            strip_payloads.append((strip_index, rows))
        selected_baselines = _select_baseline_rows(
            baseline_candidates,
            baseline_target_count(protocol, legacy_baseline_audio_count, len(baseline_candidates)),
        )
        exact_catches = _filmstrip_catch_rows(
            exact_catch_candidates,
            protocol,
            int(protocol.catch_trials_exact or 0) if protocol.catch_trials_exact is not None else 0,
        )
        exact_auditory_only = _filmstrip_auditory_only_rows(
            exact_auditory_only_candidates,
            protocol,
            int(protocol.auditory_only_trials_exact or 0) if protocol.auditory_only_trials_exact is not None else 0,
        )
        catches_by_strip: dict[int, list[dict[str, Any]]] = {}
        for row in exact_catches:
            catches_by_strip.setdefault(int(row.get("trial_strip_index") or 0), []).append(row)
        auditory_only_by_strip: dict[int, list[dict[str, Any]]] = {}
        for row in exact_auditory_only:
            auditory_only_by_strip.setdefault(int(row.get("trial_strip_index") or 0), []).append(row)
        baselines_by_strip: dict[int, list[dict[str, Any]]] = {}
        for row in selected_baselines:
            baselines_by_strip.setdefault(int(row.get("trial_strip_index") or 0), []).append(row)
        strip_queues: list[list[dict[str, Any]]] = []
        for strip_index, rows in strip_payloads:
            rows = list(rows)
            rows.extend(catches_by_strip.get(strip_index, []))
            rows.extend(auditory_only_by_strip.get(strip_index, []))
            rows.extend(baselines_by_strip.get(strip_index, []))
            if not rows:
                continue
            randomized = _randomize_rows(
                rows,
                protocol,
                seed=protocol.random_seed + block_index * 1009 + strip_index * 917,
            )
            strip_queues.append(randomized)
        block_trial_index = 1
        while any(strip_queues):
            for queue in strip_queues:
                if not queue:
                    continue
                row = queue.pop(0)
                scheduled.append(
                    {
                        "block_index": block_index,
                        "block_label": block.label,
                        "block_trial_index": block_trial_index,
                        **row,
                    }
                )
                block_trial_index += 1
    return scheduled


def protocol_trial_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    protocol = design.protocol
    factor_pairs = protocol_factor_pairs(protocol)
    repetitions = range(1, protocol.repetitions_per_condition + 1)
    sound_sources = protocol_sound_sources(design)

    for repetition in repetitions:
        for tactile_site in protocol.tactile_sites:
            for motion_direction in protocol.auditory_motion_directions:
                for phase in protocol.respiratory_phases:
                    for soa_ms, spatial_cm in factor_pairs:
                        for source in sound_sources:
                            rows.append(
                                {
                                    "trial_type": "Audio-Tactile",
                                    "repetition": repetition,
                                    "tactile_site": tactile_site,
                                    "motion_direction": motion_direction,
                                    "phase": phase,
                                    "soa_ms": soa_ms,
                                    "spatial_value_cm": spatial_cm,
                                    "noise_label": source["label"],
                                    "noise_type": source["noise_type"],
                                    "azimuth_deg": source["azimuth_deg"],
                                    "elevation_deg": source["elevation_deg"],
                                }
                            )

    audio_tactile_count = len(rows)
    if protocol.include_auditory_only_trials:
        if protocol.auditory_only_trials_exact is not None:
            auditory_only_count = int(protocol.auditory_only_trials_exact)
        elif protocol.auditory_only_trial_percentage > 0:
            auditory_only_count = int(
                math.ceil(audio_tactile_count * protocol.auditory_only_trial_percentage / (100.0 - protocol.auditory_only_trial_percentage))
            )
        else:
            auditory_only_count = audio_tactile_count
        noises = sound_sources or [_sound_source_from_noise(NoiseDefinition("Auditory target", "white"))]
        phases = protocol.respiratory_phases or ["Any"]
        pairs = factor_pairs or [(0, 0.0)]
        motion_directions = protocol.auditory_motion_directions or ["looming"]
        for i in range(max(0, auditory_only_count)):
            soa_ms, spatial_cm = pairs[i % len(pairs)]
            noise = noises[i % len(noises)]
            rows.append(
                {
                    "trial_type": "Auditory-Only",
                    "repetition": "",
                    "tactile_site": "",
                    "motion_direction": motion_directions[i % len(motion_directions)],
                    "phase": phases[i % len(phases)],
                    "soa_ms": soa_ms,
                    "spatial_value_cm": spatial_cm,
                    "noise_label": noise["label"],
                    "noise_type": noise["noise_type"],
                    "azimuth_deg": noise["azimuth_deg"],
                    "elevation_deg": noise["elevation_deg"],
                    "tactile_enabled": False,
                    "expected_response": "respond",
                    "target_role": "auditory_target",
                    "response_rule": "respond_to_auditory_target",
                }
            )

    if protocol.include_baseline_trials:
        baseline_pairs = baseline_factor_pairs(protocol, design.trajectory)
        baseline_candidates: list[dict[str, Any]] = []
        for repetition in repetitions:
            for tactile_site in protocol.tactile_sites:
                for phase in protocol.respiratory_phases:
                    for soa_ms, spatial_cm in baseline_pairs:
                        baseline_candidates.append(
                            {
                                "trial_type": "Baseline",
                                "repetition": repetition,
                                "tactile_site": tactile_site,
                                "motion_direction": "",
                                "phase": phase,
                                "soa_ms": soa_ms,
                                "spatial_value_cm": spatial_cm,
                                "noise_label": "",
                                "noise_type": "",
                                "azimuth_deg": "",
                                "elevation_deg": "",
                                "baseline_strategy": _baseline_strategy(protocol),
                            }
                        )
        rows.extend(_select_baseline_rows(
            baseline_candidates,
            baseline_target_count(protocol, len(rows), len(baseline_candidates)),
        ))

    noncatch_count = len(rows)
    if protocol.catch_trials_exact is not None:
        catch_count = protocol.catch_trials_exact
    elif protocol.catch_trial_percentage > 0:
        catch_count = int(math.ceil(noncatch_count * protocol.catch_trial_percentage / (100.0 - protocol.catch_trial_percentage)))
    else:
        catch_count = 0

    noises = sound_sources or [_sound_source_from_noise(NoiseDefinition("Catch", "white"))]
    phases = protocol.respiratory_phases or ["Any"]
    pairs = factor_pairs or [(0, 0.0)]
    tactile_sites = protocol.tactile_sites or ["body"]
    motion_directions = protocol.auditory_motion_directions or ["looming"]
    for i in range(catch_count):
        soa_ms, spatial_cm = pairs[i % len(pairs)]
        noise = noises[i % len(noises)]
        rows.append(
            {
                "trial_type": "Catch",
                "repetition": "",
                "tactile_site": tactile_sites[i % len(tactile_sites)],
                "motion_direction": motion_directions[i % len(motion_directions)],
                "phase": phases[i % len(phases)],
                "soa_ms": soa_ms,
                "spatial_value_cm": spatial_cm,
                "noise_label": noise["label"],
                "noise_type": noise["noise_type"],
                "azimuth_deg": noise["azimuth_deg"],
                "elevation_deg": noise["elevation_deg"],
            }
        )
    return rows


def protocol_sound_sources(design: StimulusDesign) -> list[dict[str, Any]]:
    sources = [_sound_source_from_noise(noise) for noise in design.noises]
    sources.extend(
        {
            "label": asset.label,
            "noise_type": CUSTOM_AUDIO_NOISE_TYPE,
            "tone_type": asset.tone_type,
            "azimuth_deg": "",
            "elevation_deg": "",
            "gain": asset.gain,
            "source_path": asset.path,
            "target_duration_s": asset.target_duration_s,
            "source_render_mode": asset.render_mode,
            "stimulus_placement": asset.placement,
            "target_source_label": asset.target_source_label,
            "phase": asset.phase,
            "gap_s": asset.gap_s,
            "trajectory_snapshot": dict(asset.trajectory_snapshot),
        }
        for asset in design.custom_looming_files
        if asset.label.strip() or asset.path.strip()
    )
    return sources


def _sound_source_from_noise(noise: NoiseDefinition) -> dict[str, Any]:
    source_profile = str(noise.source_profile or "").strip()
    source_profile_parameters = dict(noise.source_profile_parameters)
    if should_apply_gold_standard_looming_source_profile(noise):
        source_profile = PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
        source_profile_parameters = gold_standard_looming_source_parameters(source_profile_parameters)
    elif source_profile == PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE:
        source_profile_parameters = gold_standard_looming_source_parameters(source_profile_parameters)
    elif source_profile == "continuous_noise":
        source_profile_parameters = {}
    return {
        "label": noise.label,
        "noise_type": noise.noise_type,
        "tone_type": noise.noise_type,
        "azimuth_deg": noise.azimuth_deg,
        "elevation_deg": noise.elevation_deg,
        "gain": noise.gain,
        "source_profile": source_profile,
        "source_profile_parameters": source_profile_parameters,
        "source_path": noise.prebaked_path,
        "prebaked_path": noise.prebaked_path,
        "source_kind": "procedural_noise",
        "motion_mode": noise.motion_mode,
        "trajectory_snapshot": dict(noise.trajectory_snapshot),
    }


def _condition_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("trial_type"),
        row.get("tactile_site"),
        row.get("motion_direction"),
        row.get("phase"),
        row.get("soa_ms"),
        row.get("spatial_value_cm"),
        row.get("noise_label"),
    )


def _violates_trial_type_run(candidate: dict[str, Any], ordered: list[dict[str, Any]], max_run: int) -> bool:
    if max_run <= 0 or len(ordered) < max_run:
        return False
    trial_type = candidate.get("trial_type")
    return all(row.get("trial_type") == trial_type for row in ordered[-max_run:])


def _randomize_rows(rows: list[dict[str, Any]], protocol: ProtocolSpec, seed: int) -> list[dict[str, Any]]:
    if protocol.trial_randomization_strategy == "ordered":
        return list(rows)

    rng = random.Random(seed)
    remaining = list(rows)
    rng.shuffle(remaining)
    if protocol.trial_randomization_strategy == "balanced_shuffle":
        return remaining

    ordered: list[dict[str, Any]] = []
    while remaining:
        previous_key = _condition_key(ordered[-1]) if ordered else None
        choice_index = None
        for idx, row in enumerate(remaining):
            if _violates_trial_type_run(row, ordered, protocol.max_consecutive_same_trial_type):
                continue
            if previous_key is not None and _condition_key(row) == previous_key:
                continue
            choice_index = idx
            break
        if choice_index is None:
            for idx, row in enumerate(remaining):
                if not _violates_trial_type_run(row, ordered, protocol.max_consecutive_same_trial_type):
                    choice_index = idx
                    break
        if choice_index is None:
            choice_index = 0
        ordered.append(remaining.pop(choice_index))
    return ordered


def block_trial_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    protocol = design.protocol
    if has_trial_strips(protocol):
        return _filmstrip_block_trial_rows(design)

    blocks = effective_block_specs(protocol)
    block_rows: dict[str, list[dict[str, Any]]] = {block.label: [] for block in blocks}
    rows_by_type: dict[str, list[dict[str, Any]]] = {trial_type: [] for trial_type in SUPPORTED_TRIAL_TYPES}
    for row in protocol_trial_rows(design):
        rows_by_type.setdefault(str(row["trial_type"]), []).append(row)

    if protocol.repeat_trial_pool_per_block:
        for block in blocks:
            for trial_type, rows in rows_by_type.items():
                if trial_type not in block.stimulus_types:
                    continue
                block_rows[block.label].extend(dict(row) for row in rows)
    else:
        for trial_type, rows in rows_by_type.items():
            if not rows:
                continue
            eligible_blocks = [block for block in blocks if trial_type in block.stimulus_types]
            if not eligible_blocks:
                continue
            shuffled = list(rows)
            random.Random(protocol.random_seed + sum(ord(ch) for ch in trial_type)).shuffle(shuffled)
            for idx, row in enumerate(shuffled):
                min_count = min(len(block_rows[block.label]) for block in eligible_blocks)
                candidates = [
                    block
                    for block in eligible_blocks
                    if len(block_rows[block.label]) == min_count
                ]
                block = candidates[idx % len(candidates)]
                block_rows[block.label].append(dict(row))

    scheduled: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks, start=1):
        randomized = _randomize_rows(
            block_rows[block.label],
            protocol,
            seed=protocol.random_seed + block_index * 1009,
        )
        for trial_index, row in enumerate(randomized, start=1):
            scheduled.append(
                {
                    "block_index": block_index,
                    "block_label": block.label,
                    "block_trial_index": trial_index,
                    **row,
                }
            )
    return scheduled


def participant_block_orders(design: StimulusDesign) -> dict[str, list[str]]:
    from .participant_orders import participant_order

    protocol = design.protocol
    labels = [block.label for block in effective_block_specs(protocol)]
    if not labels:
        return {}

    orders: dict[str, list[str]] = {}
    for participant_index in range(1, protocol.participants + 1):
        generated = participant_order(
            labels,
            participant_index=participant_index,
            policy=protocol.participant_order_policy,
            legacy_algorithm=protocol.block_order_randomization,
            legacy_seed=protocol.random_seed,
        )
        orders[f"P{participant_index:03d}"] = list(generated.block_order)
    return orders


def experiment_schedule_rows(design: StimulusDesign) -> list[dict[str, Any]]:
    block_rows = block_trial_rows(design)
    rows_by_block: dict[str, list[dict[str, Any]]] = {}
    for row in block_rows:
        rows_by_block.setdefault(str(row["block_label"]), []).append(row)

    scheduled: list[dict[str, Any]] = []
    for participant_id, order in participant_block_orders(design).items():
        participant_index = int(participant_id[1:])
        for block_position, block_label in enumerate(order, start=1):
            for row in rows_by_block.get(block_label, []):
                scheduled.append(
                    {
                        "participant_id": participant_id,
                        "participant_index": participant_index,
                        "participant_block_position": block_position,
                        **row,
                    }
                )
    return scheduled


def _fixed_audio_duration_s(design: StimulusDesign, label: str) -> float:
    for asset in design.prestimulus_files:
        if asset.label == label:
            return max(0.0, float(asset.target_duration_s or 0.0))
    return 0.0


def _source_duration_s(design: StimulusDesign, label: str) -> float:
    for asset in design.custom_looming_files:
        if asset.label == label:
            return max(0.0, float(asset.target_duration_s or 0.0))
    return max(0.0, float(design.trajectory.total_duration_s or 0.0))


def _row_estimated_duration_s(design: StimulusDesign, row: dict[str, Any]) -> float:
    fixed_labels = [
        label.strip()
        for label in str(row.get("fixed_audio_labels", "")).split(";")
        if label.strip()
    ]
    fixed_duration = sum(_fixed_audio_duration_s(design, label) for label in fixed_labels)
    sound_window = _source_duration_s(design, str(row.get("noise_label") or ""))
    if row.get("trial_type") == "Baseline":
        sound_window = max(sound_window, max(0, int(row.get("soa_ms") or 0)) / 1000.0)
    return max(0.1, fixed_duration + sound_window)


def protocol_summary(design: StimulusDesign) -> dict[str, Any]:
    rows = block_trial_rows(design)
    audio_tactile = sum(1 for row in rows if row["trial_type"] == "Audio-Tactile")
    baseline = sum(1 for row in rows if row["trial_type"] == "Baseline")
    catch = sum(1 for row in rows if row["trial_type"] == "Catch")
    auditory_only = sum(1 for row in rows if row["trial_type"] == "Auditory-Only")
    total = len(rows)
    blocks = max(1, len(effective_block_specs(design.protocol)))
    block_counts: dict[str, int] = {}
    for row in rows:
        block_counts[str(row["block_label"])] = block_counts.get(str(row["block_label"]), 0) + 1
    estimated_participant_s = sum(_row_estimated_duration_s(design, row) for row in rows)
    baseline_denominator = max(1, audio_tactile + baseline)
    return {
        "audio_tactile_trials": audio_tactile,
        "baseline_trials": baseline,
        "catch_trials": catch,
        "auditory_only_trials": auditory_only,
        "total_trials": total,
        "blocks": blocks,
        "trials_per_block": max(block_counts.values(), default=int(math.ceil(total / blocks))),
        "min_trials_per_block": min(block_counts.values(), default=0),
        "max_trials_per_block": max(block_counts.values(), default=0),
        "participants": design.protocol.participants,
        "total_participant_trials": total * design.protocol.participants,
        "baseline_actual_percent": round(100.0 * baseline / baseline_denominator, 1),
        "estimated_participant_minutes": round(estimated_participant_s / 60.0, 1),
        "estimated_all_participants_hours": round(
            estimated_participant_s * max(1, design.protocol.participants) / 3600.0,
            1,
        ),
    }


def export_protocol_csv(design: StimulusDesign, path: Path) -> None:
    os.makedirs(_filesystem_path(path.parent), exist_ok=True)
    rows = experiment_schedule_rows(design)
    fieldnames = [
        "participant_id",
        "participant_index",
        "participant_block_position",
        "block_index",
        "block_label",
        "block_trial_index",
        "trial_type",
        "repetition",
        "tactile_site",
        "motion_direction",
        "phase",
        "soa_ms",
        "spatial_value_cm",
        "noise_label",
        "noise_type",
        "azimuth_deg",
        "elevation_deg",
        "trial_strip_id",
        "trial_strip_label",
        "trial_strip_index",
        "trial_type_id",
        "trial_type_label",
        "trial_type_index",
        "row_audio_tactile_percent",
        "row_catch_percent",
        "row_baseline_percent",
        "tactile_enabled",
        "fixed_audio_labels",
        "fixed_audio_paths",
        "sequence_source_labels",
        "sequence_variant_label",
        "sequence_variant_key",
        "sequence_variant_path",
        "sequence_variant_index",
        "jitter_labels",
        "jitter_values_ms",
        "jitter_total_ms",
        "sequence_labels",
        "baseline_strategy",
        "baseline_sample_index",
        "trial_unit_key",
    ]
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _default_azimuths_for_direction(spec: TrajectorySpec) -> tuple[float, float]:
    if spec.path_direction == "left_to_right" and spec.azimuth_start_deg == spec.azimuth_end_deg:
        return -45.0, 45.0
    if spec.path_direction == "right_to_left" and spec.azimuth_start_deg == spec.azimuth_end_deg:
        return 45.0, -45.0
    return spec.azimuth_start_deg, spec.azimuth_end_deg


def _trajectory_xyz_at_fraction(spec: TrajectorySpec, u: float) -> dict[str, float]:
    u = max(0.0, min(1.0, u))
    if _uses_cartesian_coordinates(spec):
        start, end = trajectory_endpoints_xyz(spec)
        return {
            "x_m": start["x_m"] + (end["x_m"] - start["x_m"]) * u,
            "y_m": start["y_m"] + (end["y_m"] - start["y_m"]) * u,
            "z_m": start["z_m"] + (end["z_m"] - start["z_m"]) * u,
        }

    az0, az1 = _default_azimuths_for_direction(spec)
    radius_m = spec.start_radius_m + (spec.end_radius_m - spec.start_radius_m) * u
    azimuth_deg = az0 + (az1 - az0) * u
    return spherical_to_cartesian(radius_m, azimuth_deg, spec.elevation_deg)


def trajectory_point_at_time(spec: TrajectorySpec, time_s: float) -> dict[str, float]:
    movement_duration = max(spec.movement_duration_s, 0.0)
    start_hold_s = max(spec.padding_pre_s, 0.0)
    end_hold_s = max(spec.padding_post_s, 0.0)
    total_duration = start_hold_s + movement_duration + end_hold_s
    clamped_time = max(0.0, min(time_s, total_duration))
    if clamped_time < start_hold_s or movement_duration <= 0:
        phase = "start_hold"
        u = 0.0
    elif clamped_time <= start_hold_s + movement_duration:
        phase = "movement"
        u = (clamped_time - start_hold_s) / movement_duration
    else:
        phase = "end_hold"
        u = 1.0

    xyz = _trajectory_xyz_at_fraction(spec, u)
    spherical = cartesian_to_spherical(xyz["x_m"], xyz["y_m"], xyz["z_m"])
    return {
        "time_s": clamped_time,
        "phase": phase,
        "u": u,
        "radius_m": spherical["radius_m"],
        "azimuth_deg": spherical["azimuth_deg"],
        "elevation_deg": spherical["elevation_deg"],
        "x_m": xyz["x_m"],
        "y_m": xyz["y_m"],
        "z_m": xyz["z_m"],
    }


def trajectory_points_with_holds(spec: TrajectorySpec, samples_per_second: float = 100.0) -> list[dict[str, float]]:
    if samples_per_second <= 0:
        raise ValueError("samples_per_second must be positive.")
    total_duration = max(spec.total_duration_s, 0.0)
    sample_count = max(2, int(round(total_duration * samples_per_second)) + 1)
    if sample_count == 2:
        return [trajectory_point_at_time(spec, 0.0), trajectory_point_at_time(spec, total_duration)]
    return [
        trajectory_point_at_time(spec, total_duration * i / (sample_count - 1))
        for i in range(sample_count)
    ]


def trajectory_points(spec: TrajectorySpec, samples: int = 121) -> list[dict[str, float]]:
    samples = max(2, samples)
    duration = max(spec.movement_duration_s, 0.0)
    if _uses_cartesian_coordinates(spec):
        rows: list[dict[str, float]] = []
        for i in range(samples):
            u = i / (samples - 1)
            time_s = duration * u
            xyz = _trajectory_xyz_at_fraction(spec, u)
            x_m = xyz["x_m"]
            y_m = xyz["y_m"]
            z_m = xyz["z_m"]
            spherical = cartesian_to_spherical(x_m, y_m, z_m)
            rows.append(
                {
                    "time_s": time_s,
                    "radius_m": spherical["radius_m"],
                    "azimuth_deg": spherical["azimuth_deg"],
                    "elevation_deg": spherical["elevation_deg"],
                    "x_m": x_m,
                    "y_m": y_m,
                    "z_m": z_m,
                }
            )
        return rows

    rows: list[dict[str, float]] = []
    for i in range(samples):
        u = i / (samples - 1)
        time_s = duration * u
        xyz = _trajectory_xyz_at_fraction(spec, u)
        spherical = cartesian_to_spherical(xyz["x_m"], xyz["y_m"], xyz["z_m"])
        rows.append(
            {
                "time_s": time_s,
                "radius_m": spherical["radius_m"],
                "azimuth_deg": spherical["azimuth_deg"],
                "elevation_deg": spherical["elevation_deg"],
                "x_m": xyz["x_m"],
                "y_m": xyz["y_m"],
                "z_m": xyz["z_m"],
            }
        )
    return rows


def export_trajectory_csv(design: StimulusDesign, path: Path, samples: int = 121) -> None:
    os.makedirs(_filesystem_path(path.parent), exist_ok=True)
    rows = trajectory_points(design.trajectory, samples=samples)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sofa_summary(path: Path) -> dict[str, Any]:
    try:
        import sofar
    except ImportError as exc:
        raise RuntimeError("Install the sofar package to inspect SOFA files.") from exc

    hrtf = sofar.read_sofa(str(path))
    positions = np.asarray(hrtf.Source.Position.get_values(), dtype=float)
    if positions.ndim != 2 or positions.shape[1] < 2:
        raise RuntimeError("SOFA source positions must have at least azimuth and elevation columns.")

    sample_rate = None
    try:
        sample_rate = float(np.asarray(hrtf.Data.SamplingRate.get_values()).reshape(-1)[0])
    except Exception:
        sample_rate = None

    distances = positions[:, 2] if positions.shape[1] >= 3 else np.full(len(positions), np.nan)
    return {
        "conventions": getattr(hrtf, "GLOBAL_SOFAConventions", ""),
        "version": getattr(hrtf, "GLOBAL_SOFAConventionsVersion", ""),
        "positions": int(len(positions)),
        "azimuth_min": float(np.nanmin(positions[:, 0])),
        "azimuth_max": float(np.nanmax(positions[:, 0])),
        "elevation_min": float(np.nanmin(positions[:, 1])),
        "elevation_max": float(np.nanmax(positions[:, 1])),
        "distance_min": float(np.nanmin(distances)) if not np.all(np.isnan(distances)) else None,
        "distance_max": float(np.nanmax(distances)) if not np.all(np.isnan(distances)) else None,
        "sample_rate": sample_rate,
    }


def nearest_sofa_position(path: Path, azimuth_deg: float, elevation_deg: float = 0.0) -> dict[str, float]:
    try:
        import sofar
    except ImportError as exc:
        raise RuntimeError("Install the sofar package to inspect SOFA files.") from exc

    hrtf = sofar.read_sofa(str(path))
    positions = np.asarray(hrtf.Source.Position.get_values(), dtype=float)
    if positions.ndim != 2 or positions.shape[1] < 2:
        raise RuntimeError("SOFA source positions must have at least azimuth and elevation columns.")

    azimuth_delta = ((positions[:, 0] - azimuth_deg + 180.0) % 360.0) - 180.0
    elevation_delta = positions[:, 1] - elevation_deg
    score = np.sqrt(azimuth_delta**2 + elevation_delta**2)
    idx = int(np.argmin(score))
    row = positions[idx]
    return {
        "index": float(idx),
        "azimuth_deg": float(row[0]),
        "elevation_deg": float(row[1]),
        "distance_m": float(row[2]) if row.shape[0] >= 3 else float("nan"),
        "angular_error_deg": float(score[idx]),
    }


def snap_noises_to_sofa(design: StimulusDesign) -> StimulusDesign:
    if not design.sofa_file:
        raise RuntimeError("No SOFA file selected.")
    sofa_path = Path(design.sofa_file)
    snapped = design_from_dict(design_to_dict(design))
    for noise in snapped.noises:
        nearest = nearest_sofa_position(sofa_path, noise.azimuth_deg, noise.elevation_deg)
        noise.azimuth_deg = nearest["azimuth_deg"]
        noise.elevation_deg = nearest["elevation_deg"]
    return snapped
