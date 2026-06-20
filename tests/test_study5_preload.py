from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from peripersonal_space_toolkit import dashboard_app
from peripersonal_space_toolkit.dashboard_app import DashboardController
from peripersonal_space_toolkit.design import block_trial_rows, default_design, save_design, validate_design
from peripersonal_space_toolkit.preload_inventory import load_preload_inventory, profile_asset_status
from peripersonal_space_toolkit.templates import DEFAULT_STUDY_TEMPLATE_ID, load_templates

PINK_WHITE_STUDY5_TEMPLATE_ID = "study5_box_breathing_pps_pink_white"


def _study5_template():
    root = Path(__file__).resolve().parents[1]
    templates = load_templates(root / "study_templates")
    return next(template for template in templates if template.template_id == DEFAULT_STUDY_TEMPLATE_ID)


def _study5_pink_white_template():
    root = Path(__file__).resolve().parents[1]
    templates = load_templates(root / "study_templates")
    return next(template for template in templates if template.template_id == PINK_WHITE_STUDY5_TEMPLATE_ID)


def test_study5_is_first_default_preload():
    root = Path(__file__).resolve().parents[1]
    templates = load_templates(root / "study_templates")

    assert templates[0].template_id == DEFAULT_STUDY_TEMPLATE_ID


def test_dashboard_starts_from_study5_when_no_deliberate_profile_is_saved(tmp_path: Path):
    missing_design_path = tmp_path / "missing.json"
    fresh = DashboardController(
        design_path=missing_design_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert fresh["selected_template"] == DEFAULT_STUDY_TEMPLATE_ID
    assert fresh["design"]["prestimulus_files"][0]["label"] == "Inhale instruction"
    assert fresh["design"]["noises"][0]["label"] == "Pink frontal"
    assert fresh["design"]["custom_looming_files"] == []
    assert fresh["design"]["protocol"]["trial_strips"][0]["label"] == "Inhale trial type"
    assert fresh["preload_inventory"]["status"] == "ready"
    assert fresh["preflight"]["render_ready"] is True

    scratch_design = default_design()
    scratch_design.name = "Manual scratch design"
    scratch_design.study_profile_reference_parameters = {"dashboard_mode": "custom"}
    scratch_path = tmp_path / "custom_scratch.json"
    save_design(scratch_design, scratch_path)
    from_scratch = DashboardController(
        design_path=scratch_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert from_scratch["selected_template"] == DEFAULT_STUDY_TEMPLATE_ID


def test_dashboard_preserves_deliberate_saved_profile(tmp_path: Path):
    saved_design = _study5_template().design
    saved_design.name = "Edited Study 5 working copy"
    saved_path = tmp_path / "saved_profile.json"
    save_design(saved_design, saved_path)

    state = DashboardController(
        design_path=saved_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert state["selected_template"] == DEFAULT_STUDY_TEMPLATE_ID
    assert state["design"]["name"] == "Edited Study 5 working copy"


def test_dashboard_replaces_saved_non_default_profile_with_study5_for_startup(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    saved_design = next(
        template.design
        for template in load_templates(root / "study_templates")
        if template.template_id != DEFAULT_STUDY_TEMPLATE_ID
    )
    saved_path = tmp_path / "saved_other_profile.json"
    save_design(saved_design, saved_path)

    state = DashboardController(
        design_path=saved_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert state["selected_template"] == DEFAULT_STUDY_TEMPLATE_ID
    assert state["design"]["study_profile_id"] == DEFAULT_STUDY_TEMPLATE_ID
    assert state["design"]["name"] == _study5_template().design.name


def test_dashboard_migrates_legacy_study5_row_labels_on_saved_profile_load(tmp_path: Path):
    saved_design = _study5_template().design
    saved_design.protocol.trial_strips[0].label = "Inhale row"
    saved_design.protocol.trial_strips[1].label = "Exhale row"
    saved_design.protocol.include_baseline_trials = False
    saved_design.protocol.baseline_strategy = "none"
    saved_design.protocol.baseline_custom_trial_mode = "audio_tactile"
    saved_design.protocol.baseline_soa_values_ms = [0]
    saved_design.study_profile_notes = "Legacy Study 5 config with filmstrip trial rows."
    saved_path = tmp_path / "legacy_study5.json"
    save_design(saved_design, saved_path)

    state = DashboardController(
        design_path=saved_path,
        render_dir=tmp_path / "render",
        session_root=tmp_path / "sessions",
        import_dir=tmp_path / "imports",
    ).snapshot()

    assert [strip["label"] for strip in state["design"]["protocol"]["trial_strips"]] == [
        "Inhale trial type",
        "Exhale trial type",
    ]
    assert "within-block trial type rows" in state["design"]["study_profile_notes"]
    assert "filmstrip trial rows" not in state["design"]["study_profile_notes"]
    assert state["design"]["protocol"]["include_catch_trials"] is True
    assert state["design"]["protocol"]["include_baseline_trials"] is True
    assert state["design"]["protocol"]["baseline_strategy"] == "tactile_only"
    assert state["design"]["protocol"]["baseline_custom_trial_mode"] == "tactile_only"
    assert state["design"]["protocol"]["baseline_soa_values_ms"] == []
    assert state["design"]["protocol"]["trial_pool_repetition_defaults"] == {
        "default": 3.0,
        "audio_tactile": 3.0,
        "baseline": 1.5,
        "catch": 3.0,
    }


def test_unpublished_study5_template_preloads_breathing_assets_and_filmstrip():
    root = Path(__file__).resolve().parents[1]
    study5 = _study5_template()
    design = study5.design

    assert study5.doi == ""
    assert study5.verification_status == "verified"
    assert design.study_profile_title == "Study 5 PPS box-breathing profile"
    assert design.name == "Study 5 PPS box-breathing design"
    assert design.study_profile_reference_parameters["custom_clips_preloaded"] is True
    assert dashboard_app._run_setup_settings(design)["experiment_structure"] == "pre_post"
    assert design.protocol.include_catch_trials is True
    assert design.protocol.catch_trial_percentage == pytest.approx(0.0)
    assert design.protocol.include_baseline_trials is True
    assert design.protocol.baseline_strategy == "tactile_only"
    assert design.protocol.baseline_custom_trial_mode == "tactile_only"
    assert design.protocol.baseline_soa_values_ms == []
    assert design.protocol.trial_pool_repetition_defaults == {
        "default": 3.0,
        "audio_tactile": 3.0,
        "baseline": 1.5,
        "catch": 3.0,
    }
    custom_clip_assets = design.study_profile_reference_parameters["custom_clip_assets"]
    assert [clip["label"] for clip in custom_clip_assets[:2]] == ["Inhale instruction", "Exhale instruction"]
    assert [clip["variant"] for clip in custom_clip_assets[:2]] == ["original_study5", "original_study5"]
    assert {clip["variant"] for clip in custom_clip_assets} == {"original_study5"}
    assert all(clip["duration_s"] == pytest.approx(4.0) for clip in custom_clip_assets)
    assert [clip.label for clip in design.prestimulus_files][:2] == ["Inhale instruction", "Exhale instruction"]
    assert all("assets/breathing/original_study5/" in clip.path.replace("\\", "/") for clip in design.prestimulus_files)
    assert len(design.prestimulus_files) == 2
    assert [clip.phase for clip in design.prestimulus_files[:2]] == ["Inhale", "Exhale"]
    assert all(clip.motion_mode == "stationary" for clip in design.prestimulus_files)
    assert all(clip.target_duration_s == pytest.approx(4.0) for clip in design.prestimulus_files)

    instruction_profile = dashboard_app._run_setup_settings(design)["instruction_profile"]
    instruction_slots = {slot["slot"]: slot for slot in instruction_profile["slots"]}
    template_profile = design.study_profile_reference_parameters["dashboard_run_setup"]["instruction_profile"]
    preload_run_defaults = json.loads(
        (root / "assets" / "preloads" / "study5_box_breathing_pps" / "05_run_setup" / "run_defaults.json").read_text(
            encoding="utf-8"
        )
    )
    assert preload_run_defaults["instruction_profile"] == template_profile
    expected_instruction_defaults = {
        "before_experiment": ("General instructions", "General_Instructions.wav", 85.708, "click"),
        "before_each_block": ("Pre-block instruction", "Pre-Block_Instruction.wav", 8.418, "delay"),
        "after_each_block": ("Post-block instruction", "Post-Block_Instruction.wav", 8.829, "click"),
        "between_conditions": ("Condition transition", "InterimMessage.wav", 10.109, "button"),
        "after_experiment": ("Finish message", "FinishMessage.wav", 7.001, "delay"),
    }
    assert set(instruction_slots) == set(expected_instruction_defaults)
    for slot_name, (label, filename, duration_s, continue_mode) in expected_instruction_defaults.items():
        slot = instruction_slots[slot_name]
        assert slot["enabled"] is True
        assert slot["required"] is False
        assert slot["label"] == label
        assert slot["path"].replace("\\", "/").endswith(f"assets/breathing/original_study5/{filename}")
        assert slot["duration_s"] == pytest.approx(duration_s, abs=0.001)
        assert slot["sample_rate"] == 44100
        assert slot["channels"] in {1, 2}
        assert slot["sha256"]
        assert slot["continue_mode"] == continue_mode
        assert slot["source"] == "original_study5"
    assert [asset.label for asset in design.noises] == [
        "Pink frontal",
        "Blue frontal",
        "White frontal",
        "Brown frontal",
    ]
    assert design.custom_looming_files == []

    for clip in design.prestimulus_files:
        path = root / clip.path
        assert path.exists()
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == 44100
            assert wav.getnframes() == 176400
            assert wav.getnframes() / wav.getframerate() == pytest.approx(4.0)

    for asset in design.noises:
        path = root / asset.prebaked_path
        assert path.exists()
        assert asset.motion_mode == "looming"
        with wave.open(str(path), "rb") as wav:
            assert wav.getframerate() == 44100
            assert wav.getnchannels() == 2
            assert wav.getnframes() == 176400
            assert wav.getnframes() / wav.getframerate() == pytest.approx(4.0)

    inventory = load_preload_inventory(root)
    asset_status = profile_asset_status(DEFAULT_STUDY_TEMPLATE_ID, inventory=inventory, repo_root=root)
    assert asset_status["status"] == "ready"
    assert asset_status["asset_count"] == 4
    assert all(asset["sha256_ok"] is True for asset in asset_status["assets"])

    strips = design.protocol.trial_strips
    assert [strip.label for strip in strips] == ["Inhale trial type", "Exhale trial type"]
    assert [strip.elements[0].source_label for strip in strips] == ["Inhale instruction", "Exhale instruction"]
    for strip in strips:
        assert strip.audio_tactile_percentage == pytest.approx(100.0)
        assert strip.catch_percentage == pytest.approx(0.0)
        assert strip.baseline_percentage == pytest.approx(0.0)
        assert strip.elements[0].kind == "fixed_audio"
        assert strip.elements[0].randomized is False
        assert strip.elements[1].kind == "looming_stimulus"
        assert strip.elements[1].randomized is True
        assert strip.elements[1].source_labels == [asset.label for asset in design.noises]

    assert validate_design(design) == []
    rows = block_trial_rows(design)
    noncatch = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    assert len(noncatch) == design.protocol.blocks * 2 * len(design.noises) * len(design.protocol.soa_values_ms)
    assert {row["trial_type_label"] for row in rows} == {"Inhale trial type", "Exhale trial type"}
    assert {row["trial_strip_label"] for row in rows} == {"Inhale trial type", "Exhale trial type"}
    assert all("instruction | " in row["sequence_labels"] for row in rows)


def test_study5_pink_white_profile_keeps_study5_defaults_with_two_sources():
    root = Path(__file__).resolve().parents[1]
    template = _study5_pink_white_template()
    design = template.design

    assert template.title == "Study 5 PPS box-breathing pink/white profile"
    assert template.verification_status == "verified"
    assert design.study_profile_reference_parameters["publication_status"] == "unpublished_lab_profile"
    assert design.study_profile_reference_parameters["variant_source_profile_id"] == DEFAULT_STUDY_TEMPLATE_ID
    assert design.study_profile_reference_parameters["noise_source_policy"].startswith("Pink frontal and White frontal only")
    assert design.name == "Study 5 PPS box-breathing pink/white design"
    assert [asset.label for asset in design.noises] == ["Pink frontal", "White frontal"]
    assert [asset.noise_type for asset in design.noises] == ["pink", "white"]
    assert all(PINK_WHITE_STUDY5_TEMPLATE_ID in asset.prebaked_path for asset in design.noises)
    assert design.protocol.trial_pool_repetition_defaults == {
        "default": 3.0,
        "audio_tactile": 3.0,
        "baseline": 1.5,
        "catch": 3.0,
    }
    assert dashboard_app._run_setup_settings(design)["experiment_structure"] == "pre_post"

    strips = design.protocol.trial_strips
    assert [strip.label for strip in strips] == ["Inhale trial type", "Exhale trial type"]
    for strip in strips:
        looming = next(element for element in strip.elements if element.kind == "looming_stimulus")
        assert looming.source_labels == ["Pink frontal", "White frontal"]

    inventory = load_preload_inventory(root)
    asset_status = profile_asset_status(PINK_WHITE_STUDY5_TEMPLATE_ID, inventory=inventory, repo_root=root)
    assert asset_status["status"] == "ready"
    assert asset_status["asset_count"] == 2
    assert all(asset["sha256_ok"] is True for asset in asset_status["assets"])

    trial_design = json.loads(
        (
            root
            / "assets"
            / "preloads"
            / PINK_WHITE_STUDY5_TEMPLATE_ID
            / "04_trial_designer"
            / "trial_design.json"
        ).read_text(encoding="utf-8")
    )
    assert trial_design["preview_trial_count"] == 120
    assert validate_design(design) == []
    rows = block_trial_rows(design)
    noncatch = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    assert len(noncatch) == design.protocol.blocks * 2 * len(design.noises) * len(design.protocol.soa_values_ms)
