"""Build the segmented preload asset catalog used by the HTML dashboard.

The catalog mirrors the dashboard workflow so each preload profile acts like a
small local file cabinet:

- 01_profile: citation/profile metadata
- 02_looming_stimuli: prebaked auditory-only stimulus WAVs and source metadata
- 03_baseline_strategy: baseline/catch defaults
- 04_trial_designer: trial-row and SOA decisions
- 05_run_setup: participant/randomization defaults

Generated WAVs are auditory-only. Tactile channels are added later during
session preparation from the saved SOA/trial schedule.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from peripersonal_space_toolkit import render_backend
from peripersonal_space_toolkit.dashboard_app import _stimulus_trajectory_snapshot
from peripersonal_space_toolkit.design import (
    AudioFileSpec,
    NoiseDefinition,
    audio_file_summary,
    block_trial_rows,
    cartesian_to_spherical,
    design_from_dict,
    design_to_dict,
    expand_trial_strip_source_labels,
    save_design,
    trajectory_endpoints_xyz,
)
from peripersonal_space_toolkit.preload_inventory import INVENTORY_SCHEMA, sha256_file
from peripersonal_space_toolkit.profile_recreation import (
    build_profile_parameters_manifest,
    build_profile_recreation_status,
    profile_variant_labels,
    render_profile_recreation_status_markdown,
)
from peripersonal_space_toolkit.templates import StudyTemplate, load_templates


REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = REPO_ROOT / "study_templates"
PRELOAD_ROOT = REPO_ROOT / "assets" / "preloads"
RECREATION_STATUS_PATH = PRELOAD_ROOT / "profile_recreation_status.json"
RECREATION_STATUS_DOC = REPO_ROOT / "docs" / "PUBLISHED_STUDY_RECREATION_STATUS.md"
BUILD_ROOT = REPO_ROOT / "artifacts" / "preload_catalog_build"
BASE_URL = "https://georgefejer91.github.io/pps-kit/assets/preloads"
SEGMENTS = [
    ("01_profile", "Profile"),
    ("02_looming_stimuli", "Looming Stimuli Builder"),
    ("03_baseline_strategy", "Baseline Strategy"),
    ("04_trial_designer", "Trial Designer"),
    ("05_run_setup", "Run Setup"),
]
NOISE_TYPES = ("pink", "blue", "white", "brown", "violet")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build all preload profile folders and asset inventory.")
    parser.add_argument("--force", action="store_true", help="Regenerate WAVs even if the target files already exist.")
    parser.add_argument(
        "--force-template",
        action="append",
        default=[],
        help="Regenerate WAVs only for the named template id while still rebuilding the full catalog metadata.",
    )
    args = parser.parse_args()
    force_template_ids = set(args.force_template or [])
    PRELOAD_ROOT.mkdir(parents=True, exist_ok=True)
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)

    templates = load_templates(TEMPLATE_DIR)
    variant_labels = profile_variant_labels(templates)
    profiles = []
    profile_parameter_manifests = []
    for template in templates:
        profile, profile_parameters = build_profile_catalog(
            template,
            force=args.force or template.template_id in force_template_ids,
            variant_label=variant_labels.get(template.template_id, ""),
        )
        profiles.append(profile)
        profile_parameter_manifests.append(profile_parameters)

    recreation_status = build_profile_recreation_status(profile_parameter_manifests)
    write_json(RECREATION_STATUS_PATH, recreation_status)
    RECREATION_STATUS_DOC.parent.mkdir(parents=True, exist_ok=True)
    RECREATION_STATUS_DOC.write_text(render_profile_recreation_status_markdown(recreation_status), encoding="utf-8")

    inventory = {
        "schema": INVENTORY_SCHEMA,
        "base_url": BASE_URL,
        "inventory_policy": (
            "GitHub stores the manifest and owned/generated preload assets. The browser never uploads local "
            "stimulus files or participant/session artifacts; the local companion verifies, downloads, or bakes assets."
        ),
        "catalog_policy": (
            "Each profile folder mirrors the dashboard workflow segments so local storage stays aligned with the "
            "researcher decision surface."
        ),
        "default_policy": {
            "asset_mode": "bundled_local",
            "retrieval_strategy": "bundled_or_download_from_github_pages",
            "local_only": True,
        },
        "segments": [{"folder": folder, "label": label} for folder, label in SEGMENTS],
        "profiles": profiles,
    }
    write_json(PRELOAD_ROOT / "preload_inventory.json", inventory)
    print(f"Built {len(profiles)} preload catalogs under {PRELOAD_ROOT}")
    return 0


def build_profile_catalog(template: StudyTemplate, *, force: bool, variant_label: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    profile_dir = PRELOAD_ROOT / template.template_id
    for folder, _label in SEGMENTS:
        (profile_dir / folder).mkdir(parents=True, exist_ok=True)

    design = design_from_dict(design_to_dict(template.design))
    source_assets = build_stimulus_assets(template, design, profile_dir, force=force)
    write_segment_metadata(template, design, profile_dir, source_assets)
    profile_parameters = build_profile_parameters_manifest(
        template,
        source_assets=source_assets,
        profile_dir=profile_dir,
        variant_label=variant_label,
    )
    profile_parameters_path = profile_dir / "01_profile" / "profile_parameters_manifest.json"
    write_json(profile_parameters_path, profile_parameters)
    recreation_status = profile_parameters["recreation_status"]

    manifest = {
        "schema": "pps-preload-profile-assets.v1",
        "template_id": template.template_id,
        "title": template.title,
        "visible_variant_label": variant_label,
        "publication_status": profile_parameters.get("publication_status", "published"),
        "profile_type": profile_parameters.get("profile_type", ""),
        "asset_mode": "bundled_local",
        "retrieval_strategy": "bundled_or_download_from_github_pages",
        "local_only": True,
        "catalog_segments": catalog_segments(profile_dir),
        "profile_parameters_manifest": rel(profile_parameters_path),
        "recreation_status": recreation_status,
        "render_contract": {
            "stage": "auditory_looming_prebake",
            "engine": "python-sofa-reference",
            "include_tactile": False,
            "tactile_policy": "deferred_until_session_preparation",
        },
        "assets": source_assets,
        "notes": [
            "Prebaked WAVs are local auditory-only profile assets.",
            "Tactile timing is introduced later by session preparation from SOA/trial CSVs.",
            "The browser dashboard only orchestrates local companion verification and use of these files.",
        ],
    }
    write_json(profile_dir / "preload_manifest.json", manifest)

    profile_entry = {
        "template_id": template.template_id,
        "title": template.title,
        "visible_variant_label": variant_label,
        "variant_display": profile_parameters["variant_display"],
        "publication_status": profile_parameters.get("publication_status", "published"),
        "profile_type": profile_parameters.get("profile_type", ""),
        "asset_mode": "bundled_local",
        "retrieval_strategy": "bundled_or_download_from_github_pages",
        "profile_manifest": rel(profile_dir / "preload_manifest.json"),
        "profile_parameters_manifest": rel(profile_parameters_path),
        "recreation_status": recreation_status,
        "runner_readiness": recreation_status["runner_readiness"],
        "profile_checks_passed": recreation_status["profile_checks_passed"],
        "segment_0_to_4_profile_checks_passed": recreation_status["segment_0_to_4_profile_checks_passed"],
        "finished_profile": recreation_status["finished_profile"],
        "segment_6_launchable": recreation_status["segment_6_launchable"],
        "profile_completion_status": recreation_status["profile_completion_status"],
        "primary_recreation_category": recreation_status["primary_category"],
        "missing_parameter_count": recreation_status["missing_parameter_count"],
        "unsupported_structure_count": recreation_status["unsupported_structure_count"],
        "local_only": True,
        "source_recipe_count": len(source_assets),
        "catalog_segments": catalog_segments(profile_dir),
        "message": "Bundled local profile assets and segment metadata are present in the preload catalog.",
        "assets": source_assets,
    }
    return profile_entry, profile_parameters


def build_stimulus_assets(
    template: StudyTemplate,
    design: Any,
    profile_dir: Path,
    *,
    force: bool,
) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    stimulus_dir = profile_dir / "02_looming_stimuli"
    render_index = 1
    for noise in design.noises:
        for variant in source_direction_variants(template, design, noise):
            variant_design = variant["design"]
            variant_noise = variant["source"]
            target = stimulus_dir / f"looming_{safe_name(variant_noise.label)}.wav"
            if force or not target.exists():
                render_noise_source(template, variant_design, variant_noise, render_index, target)
            assets.append(
                asset_metadata(
                    template,
                    variant_design,
                    variant_noise,
                    target,
                    direction_label=variant.get("direction_label", ""),
                )
            )
            render_index += 1

    for asset in design.custom_looming_files:
        source = resolve_path(asset.path)
        target = stimulus_dir / f"looming_{safe_name(asset.label)}.wav"
        if source.exists() and (force or not target.exists()):
            if source.resolve() != target.resolve():
                shutil.copy2(source, target)
        assets.append(asset_metadata(template, design, asset, target))
    return assets


def render_noise_source(template: StudyTemplate, design: Any, noise: NoiseDefinition, index: int, target: Path) -> None:
    build_dir = BUILD_ROOT / template.template_id / f"{index:03d}_{safe_name(noise.label)[:36]}"
    build_dir.mkdir(parents=True, exist_ok=True)
    source_design = design_from_dict(design_to_dict(design))
    source_design.noises = [replace(noise, label=f"source_{index:03d}")]
    source_design.custom_looming_files = []
    source_design.prestimulus_files = []
    design_path = build_dir / "stimulus_design.json"
    save_design(source_design, design_path)
    result = render_backend.render_design_with_3dti(
        design_path,
        build_dir,
        seed=int(source_design.protocol.random_seed or 20250604) + index * 1009,
        engine="python-sofa-reference",
        include_tactile=False,
    )
    if not result.wav_paths:
        raise RuntimeError(f"No WAV produced for {template.template_id}: {noise.label}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(result.wav_paths[0], target)
    qc_target = target.with_suffix(".render_qc.csv")
    if result.qc_path.exists():
        shutil.copy2(result.qc_path, qc_target)


def asset_metadata(
    template: StudyTemplate,
    design: Any,
    source: NoiseDefinition | AudioFileSpec,
    path: Path,
    *,
    direction_label: str = "",
) -> dict[str, Any]:
    source_kind = "generated_noise" if isinstance(source, NoiseDefinition) else "imported_audio"
    tone_type = source.noise_type if isinstance(source, NoiseDefinition) else (source.tone_type or infer_tone_type(source.label))
    summary = audio_file_summary(path) if path.exists() else {}
    snapshot = _stimulus_trajectory_snapshot(
        design,
        label=source.label,
        source_kind=source_kind,
        noise_type=tone_type,
    )
    if getattr(source, "motion_mode", "looming") == "stationary":
        snapshot = stationary_snapshot(snapshot)
    rel_path = rel(path)
    metadata = {
        "label": source.label,
        "path": rel_path,
        "url": f"{BASE_URL}/{template.template_id}/02_looming_stimuli/{path.name}",
        "sha256": sha256_file(path) if path.exists() else "",
        "duration_s": round(float(summary.get("duration_s", 0.0)), 6),
        "sample_rate": int(summary.get("sample_rate", 0)),
        "channels": int(summary.get("channels", 0)),
        "source_kind": source_kind,
        "noise_type": tone_type,
        "tone_type": tone_type,
        "motion_mode": getattr(source, "motion_mode", "looming") or "looming",
        "direction_label": direction_label,
        "render_mode": "preserve",
        "include_tactile": False,
        "trajectory_snapshot": snapshot,
    }
    if isinstance(source, NoiseDefinition):
        source_profile = getattr(source, "source_profile", "")
        source_profile_parameters = dict(getattr(source, "source_profile_parameters", {}) or {})
        if source_profile:
            metadata["source_profile"] = source_profile
        if source_profile_parameters:
            metadata["source_profile_parameters"] = source_profile_parameters
    return metadata


def stationary_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Represent a fixed-source preload without reusing the moving endpoint."""

    stationary = dict(snapshot)
    start = dict(stationary.get("start") or {})
    stationary.update(
        {
            "end_distance_cm": stationary.get("start_distance_cm", 0.0),
            "end_rotation_deg": stationary.get("start_rotation_deg", 0.0),
            "movement_duration_s": 0.0,
            "path_length_m": 0.0,
            "path_direction": "stationary",
            "end": start,
        }
    )
    return stationary


def source_direction_variants(template: StudyTemplate, design: Any, source: NoiseDefinition) -> list[dict[str, Any]]:
    """Return concrete trajectory variants for a procedural preload source.

    Many study templates store paper-level motion factors in
    ``protocol.auditory_motion_directions`` while the runnable design has a
    single trajectory. The preload catalog should not collapse those factors
    into one visual/source entry when the geometry can be represented directly.
    """

    spherical_variants = spherical_source_position_variants(template, design, source)
    if spherical_variants:
        return spherical_variants

    directions = normalized_direction_labels(getattr(design.protocol, "auditory_motion_directions", []))
    if not directions:
        return [source_variant(design, source, "", None)]

    variants: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, direction in enumerate(directions):
        transform = direction_transform(direction, base_is_first=index == 0)
        if transform is None:
            continue
        label = source.label if not variants else f"{source.label} - {direction_display_label(direction)}"
        variant = source_variant(design, source, direction, transform, label=label)
        key = trajectory_key(_stimulus_trajectory_snapshot(variant["design"], label=label, source_kind="generated_noise", noise_type=source.noise_type))
        if key in seen and direction not in {"left_to_right", "right_to_left", "front_to_back", "back_to_front"}:
            continue
        seen.add(key)
        variants.append(variant)

    return variants or [source_variant(design, source, "", None)]


def spherical_source_position_variants(
    template: StudyTemplate,
    design: Any,
    source: NoiseDefinition,
) -> list[dict[str, Any]]:
    positions = template.reference_parameters.get("virtual_sound_source_positions")
    if not isinstance(positions, list) or not positions:
        return []

    variants: list[dict[str, Any]] = []
    for index, position in enumerate(positions, start=1):
        if not isinstance(position, dict):
            continue
        direction_label = str(position.get("label") or f"direction_{index:02d}")
        label = source.label if not variants else f"{source.label} - {direction_display_label(direction_label)}"
        variant_design = design_from_dict(design_to_dict(design))
        apply_spherical_source_position(variant_design.trajectory, position)
        variant_source = replace(source, label=label)
        variant_design.noises = [variant_source]
        variant_design.custom_looming_files = []
        variant_design.prestimulus_files = []
        variants.append({"design": variant_design, "source": variant_source, "direction_label": direction_label})
    return variants


def apply_spherical_source_position(trajectory: Any, position: dict[str, Any]) -> None:
    start_x = float(position["x_left_right_m"])
    start_y = float(position["z_behind_front_m"])
    start_z = float(position["y_down_top_m"])
    start_radius = math.sqrt(start_x**2 + start_y**2 + start_z**2)
    if start_radius <= 0:
        return
    end_radius = max(float(position.get("end_radius_m", trajectory.end_radius_m)), 0.01)
    scale = end_radius / start_radius
    trajectory.coordinate_mode = "cartesian"
    trajectory.path_direction = "custom"
    trajectory.start_x_m = start_x
    trajectory.start_y_m = start_y
    trajectory.start_z_m = start_z
    trajectory.end_x_m = start_x * scale
    trajectory.end_y_m = start_y * scale
    trajectory.end_z_m = start_z * scale
    trajectory.start_radius_m = start_radius
    trajectory.end_radius_m = end_radius
    trajectory.path_length_m = math.dist(
        (trajectory.start_x_m, trajectory.start_y_m, trajectory.start_z_m),
        (trajectory.end_x_m, trajectory.end_y_m, trajectory.end_z_m),
    )
    movement_duration = float(position.get("movement_duration_s", 0.0) or 0.0)
    velocity = float(position.get("velocity_mps", 0.0) or 0.0)
    if movement_duration > 0:
        trajectory.propagation_speed_mps = trajectory.path_length_m / movement_duration
    elif velocity > 0:
        trajectory.propagation_speed_mps = velocity
    refresh_radius_from_xyz(trajectory)


def source_variant(
    design: Any,
    source: NoiseDefinition,
    direction_label: str,
    transform: str | None,
    *,
    label: str | None = None,
) -> dict[str, Any]:
    variant_design = design_from_dict(design_to_dict(design))
    if transform == "identity":
        pass
    elif transform == "reverse":
        reverse_trajectory(variant_design.trajectory)
    elif transform == "rotate_180":
        rotate_trajectory(variant_design.trajectory, 180.0)
    elif transform == "mirror_left_right":
        mirror_trajectory_left_right(variant_design.trajectory)
    variant_source = replace(source, label=label or source.label)
    variant_design.noises = [variant_source]
    variant_design.custom_looming_files = []
    variant_design.prestimulus_files = []
    return {"design": variant_design, "source": variant_source, "direction_label": direction_label}


def normalized_direction_labels(values: list[Any]) -> list[str]:
    labels: list[str] = []
    for value in values:
        text = " ".join(str(value or "").strip().lower().replace("-", "_").split())
        if text:
            labels.append(text.replace(" ", "_"))
    return labels


def direction_transform(direction: str, *, base_is_first: bool) -> str | None:
    if direction in {"looming", "approaching", "approach", "in", "inward"}:
        return "identity"
    if direction in {"receding", "recede", "out", "outward"}:
        return "reverse"
    if direction == "left_to_right":
        return "identity" if base_is_first else "reverse"
    if direction == "right_to_left":
        return "reverse"
    if direction == "front_to_back":
        return "identity" if base_is_first else "reverse"
    if direction == "back_to_front":
        return "reverse"
    if direction in {"front_looming", "front"}:
        return "identity"
    if direction in {"back_looming", "rear_looming", "back", "rear"}:
        return "rotate_180"
    if direction in {"rear_left_looming", "rear_left", "left_rear"}:
        return "identity"
    if direction in {"rear_right_looming", "rear_right", "right_rear"}:
        return "mirror_left_right"
    return None


def direction_display_label(direction: str) -> str:
    return direction.replace("_", " ")


def reverse_trajectory(trajectory: Any) -> None:
    trajectory.start_radius_m, trajectory.end_radius_m = trajectory.end_radius_m, trajectory.start_radius_m
    trajectory.azimuth_start_deg, trajectory.azimuth_end_deg = trajectory.azimuth_end_deg, trajectory.azimuth_start_deg
    trajectory.start_x_m, trajectory.end_x_m = trajectory.end_x_m, trajectory.start_x_m
    trajectory.start_y_m, trajectory.end_y_m = trajectory.end_y_m, trajectory.start_y_m
    trajectory.start_z_m, trajectory.end_z_m = trajectory.end_z_m, trajectory.start_z_m
    direction_map = {
        "approach": "recede",
        "recede": "approach",
        "left_to_right": "right_to_left",
        "right_to_left": "left_to_right",
    }
    trajectory.path_direction = direction_map.get(trajectory.path_direction, "custom")


def rotate_trajectory(trajectory: Any, degrees: float) -> None:
    if trajectory.start_x_m is not None and trajectory.start_y_m is not None:
        trajectory.start_x_m, trajectory.start_y_m = rotate_xy(trajectory.start_x_m, trajectory.start_y_m, degrees)
    if trajectory.end_x_m is not None and trajectory.end_y_m is not None:
        trajectory.end_x_m, trajectory.end_y_m = rotate_xy(trajectory.end_x_m, trajectory.end_y_m, degrees)
    trajectory.azimuth_start_deg = normalize_signed_degrees(float(trajectory.azimuth_start_deg) + degrees)
    trajectory.azimuth_end_deg = normalize_signed_degrees(float(trajectory.azimuth_end_deg) + degrees)
    trajectory.path_direction = "custom"
    refresh_radius_from_xyz(trajectory)


def mirror_trajectory_left_right(trajectory: Any) -> None:
    if trajectory.start_x_m is not None:
        trajectory.start_x_m = -float(trajectory.start_x_m)
    if trajectory.end_x_m is not None:
        trajectory.end_x_m = -float(trajectory.end_x_m)
    trajectory.azimuth_start_deg = normalize_signed_degrees(-float(trajectory.azimuth_start_deg))
    trajectory.azimuth_end_deg = normalize_signed_degrees(-float(trajectory.azimuth_end_deg))
    trajectory.path_direction = "custom"
    refresh_radius_from_xyz(trajectory)


def rotate_xy(x_m: float, y_m: float, degrees: float) -> tuple[float, float]:
    angle = math.radians(degrees)
    cos_v = math.cos(angle)
    sin_v = math.sin(angle)
    return (float(x_m) * cos_v - float(y_m) * sin_v, float(x_m) * sin_v + float(y_m) * cos_v)


def normalize_signed_degrees(value: float) -> float:
    return ((float(value) + 180.0) % 360.0) - 180.0


def refresh_radius_from_xyz(trajectory: Any) -> None:
    start, end = trajectory_endpoints_xyz(trajectory)
    start_spherical = cartesian_to_spherical(start["x_m"], start["y_m"], start["z_m"])
    end_spherical = cartesian_to_spherical(end["x_m"], end["y_m"], end["z_m"])
    trajectory.start_radius_m = float(start_spherical["radius_m"])
    trajectory.end_radius_m = float(end_spherical["radius_m"])


def write_segment_metadata(template: StudyTemplate, design: Any, profile_dir: Path, source_assets: list[dict[str, Any]]) -> None:
    metadata_design = design_from_dict(design_to_dict(design))
    expand_trial_strip_source_labels(
        metadata_design,
        [str(asset.get("label") or "") for asset in source_assets],
    )
    design_payload = design_to_dict(metadata_design)
    profile = {
        "schema": "pps-preload-profile-segment.v1",
        "template_id": template.template_id,
        "title": template.title,
        "citation": template.citation,
        "doi": template.doi,
        "source_url": template.source_url,
        "verification_status": template.verification_status,
        "notes": template.notes,
        "reference_parameters": template.reference_parameters,
        "provenance": template.provenance,
    }
    write_json(profile_dir / "01_profile" / "profile_metadata.json", profile)

    trajectories: dict[str, dict[str, Any]] = {}
    for asset in source_assets:
        snapshot = asset.get("trajectory_snapshot", {})
        key = trajectory_key(snapshot)
        item = trajectories.setdefault(
            key,
            {
                "trajectory_snapshot": snapshot,
                "source_labels": [],
                "tone_types": [],
                "asset_paths": [],
            },
        )
        item["source_labels"].append(asset["label"])
        if asset["tone_type"] not in item["tone_types"]:
            item["tone_types"].append(asset["tone_type"])
        item["asset_paths"].append(asset["path"])
    write_json(
        profile_dir / "02_looming_stimuli" / "stimulus_sources.json",
        {
            "schema": "pps-preload-stimulus-sources.v1",
            "template_id": template.template_id,
            "assets": source_assets,
        },
    )
    write_json(
        profile_dir / "02_looming_stimuli" / "trajectory_inventory.json",
        {
            "schema": "pps-preload-trajectory-inventory.v1",
            "template_id": template.template_id,
            "trajectories": list(trajectories.values()),
        },
    )

    protocol = design.protocol
    write_json(
        profile_dir / "03_baseline_strategy" / "baseline_strategy.json",
        {
            "schema": "pps-preload-baseline-segment.v1",
            "template_id": template.template_id,
            "baseline_strategy": protocol.baseline_strategy,
            "include_baseline_trials": protocol.include_baseline_trials,
            "baseline_trial_percentage": protocol.baseline_trial_percentage,
            "baseline_soa_values_ms": protocol.baseline_soa_values_ms,
            "catch_trial_percentage": protocol.catch_trial_percentage,
            "catch_trials_exact": protocol.catch_trials_exact,
        },
    )
    write_json(
        profile_dir / "04_trial_designer" / "trial_design.json",
        {
            "schema": "pps-preload-trial-designer-segment.v1",
            "template_id": template.template_id,
            "repetitions_per_condition": protocol.repetitions_per_condition,
            "soa_values_ms": protocol.soa_values_ms,
            "spatial_values_cm": protocol.spatial_values_cm,
            "custom_clip_assets": template.reference_parameters.get("custom_clip_assets", []),
            "trial_strips": design_payload["protocol"].get("trial_strips", []),
            "prestimulus_files": design_payload.get("prestimulus_files", []),
            "preview_trial_count": len(block_trial_rows(metadata_design)),
        },
    )
    run_setup_defaults = {
        "schema": "pps-preload-run-setup-segment.v1",
        "template_id": template.template_id,
        "blocks": protocol.blocks,
        "participants": protocol.participants,
        "random_seed": protocol.random_seed,
        "trial_randomization_strategy": protocol.trial_randomization_strategy,
        "block_order_randomization": protocol.block_order_randomization,
    }
    dashboard_run_setup = template.reference_parameters.get("dashboard_run_setup")
    if isinstance(dashboard_run_setup, dict):
        if "experiment_structure" in dashboard_run_setup:
            run_setup_defaults["experiment_structure"] = dashboard_run_setup["experiment_structure"]
        if "seed" in dashboard_run_setup:
            run_setup_defaults["seed"] = dashboard_run_setup["seed"]
        if "instruction_profile" in dashboard_run_setup:
            run_setup_defaults["instruction_profile"] = dashboard_run_setup["instruction_profile"]
    write_json(
        profile_dir / "05_run_setup" / "run_defaults.json",
        run_setup_defaults,
    )


def catalog_segments(profile_dir: Path) -> list[dict[str, str]]:
    return [
        {
            "folder": folder,
            "label": label,
            "path": rel(profile_dir / folder),
        }
        for folder, label in SEGMENTS
    ]


def trajectory_key(snapshot: dict[str, Any]) -> str:
    fields = (
        "start_distance_cm",
        "end_distance_cm",
        "start_rotation_deg",
        "end_rotation_deg",
        "movement_duration_s",
        "start_hold_s",
        "end_hold_s",
    )
    return "|".join(str(round(float(snapshot.get(field, 0.0)), 4)) for field in fields)


def infer_tone_type(label: str) -> str:
    text = str(label or "").lower()
    for noise_type in NOISE_TYPES:
        if noise_type in text:
            return noise_type
    return "custom_audio"


def resolve_path(path: str | Path) -> Path:
    target = Path(path).expanduser()
    if target.is_absolute():
        return target
    return REPO_ROOT / target


def rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(REPO_ROOT).as_posix())


def safe_name(value: str) -> str:
    import re

    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("._")
    return (safe or "stimulus")[:80].strip("._") or "stimulus"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
