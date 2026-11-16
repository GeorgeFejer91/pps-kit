from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections import Counter
from pathlib import Path

from peripersonal_space_toolkit.design import block_trial_rows
from peripersonal_space_toolkit.profile_recreation import (
    PROFILE_PARAMETERS_SCHEMA,
    PROFILE_RECREATION_STATUS_SCHEMA,
    STATUS_DEFAULTED,
    STATUS_INFERRED,
    STATUS_MISSING,
    STATUS_REPORTED,
    STATUS_UNSUPPORTED,
    _classify_gap,
)
from peripersonal_space_toolkit.templates import DEFAULT_STUDY_TEMPLATE_ID, load_templates


ROOT = Path(__file__).resolve().parents[3]
VALIDATION_SCRIPT_DIR = ROOT / "For-AI/engineering/validation" / "scripts"
STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID = "study5_dynaspace_lateral_45_pps"


def _load_validation_script(name: str):
    path = VALIDATION_SCRIPT_DIR / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_profile_recreation_manifests_cover_all_current_templates():
    root = ROOT
    templates = load_templates(root / "packages" / "pps-resources" / "study_templates")
    template_ids = {template.template_id for template in templates}
    status = json.loads((root / "packages" / "pps-resources" / "assets" / "preloads" / "profile_recreation_status.json").read_text(encoding="utf-8"))

    published = [template for template in templates if template.doi]
    assert len(published) == 201
    assert len({template.doi.lower() for template in published}) == 91
    assert all(template.reference_parameters.get("study_row_id") for template in published)
    assert status["schema"] == PROFILE_RECREATION_STATUS_SCHEMA
    assert status["profile_count"] == len(templates)
    assert {profile["template_id"] for profile in status["profiles"]} == template_ids

    categorized = set().union(*(set(values) for values in status["categories"].values()))
    assert categorized == template_ids
    assert status["categories"]["gui_recreatable"]
    assert status["categories"]["missing_publication_parameters"]
    assert {
        "amemiya_2017_ieee_foot_sole_vibration",
        "amemiya_2017_ieee_sound_localization",
        "amemiya_2019_foot_sole_exp1",
        "amemiya_2019_foot_sole_exp2",
        "bernasconi_2018_trunk_ieeg",
        "di_cosmo_2021_phase_coupling",
        "ferri_2015_artificial_looming_valence",
        "ferri_2015_ecological_looming_valence",
        "ferroni_2020_schizotypy_active",
        "ferroni_2020_schizotypy_observation",
        "galigani_2020_tool_observation",
        "hobeika_2019_social_collaboration",
        "hobeika_2019_social_competition",
        "holmes_2020_exp1",
        "holmes_2020_exp2_strong_target",
        "holmes_2020_exp2_weak_target",
        "holmes_2020_exp3",
        "holmes_2020_exp4",
        "kitagawa_2005_auditory_localization",
        "kitagawa_2005_rear_toj",
        "kitagawa_2005_tactile_distractor",
        "mul_2019_autism_pps",
        "murray_2005_audiotactile_alignment",
        "orioli_2019_newborn_audiotactile",
        "orioli_2019_newborn_auditory",
        "orioli_2019_newborn_pilot",
        "ronga_2021_adult_erp",
        "ronga_2021_newborn_erp",
        "schizophrenia_tool_use_2022",
        "sorrentino_2021_ageing_hand_pps",
        "taffou_2021_auditory_roughness",
        "teramoto_2013_beyond_head_exp1",
        "teramoto_2013_beyond_head_exp2",
        "teraoka_2024_front_pps",
        "teraoka_2024_rear_pps",
        "zampini_2005_audiotactile_toj_exp1",
        "zampini_2005_audiotactile_toj_exp2",
        "zampini_2005_audiotactile_toj_exp3",
    } <= set(status["categories"]["toolkit_structural_gap"])

    allowed_statuses = {
        STATUS_REPORTED,
        STATUS_INFERRED,
        STATUS_DEFAULTED,
        STATUS_MISSING,
        STATUS_UNSUPPORTED,
    }
    for template in templates:
        template_id = template.template_id
        manifest_path = root / "packages" / "pps-resources" / "assets" / "preloads" / template_id / "01_profile" / "profile_parameters_manifest.json"
        assert manifest_path.exists(), template_id
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["schema"] == PROFILE_PARAMETERS_SCHEMA
        assert manifest["template_id"] == template_id
        gate = manifest["segment_0_to_4_profile_checks"]
        assert gate["gate"] == "segments_0_to_4"
        assert {item["segment"] for item in gate["segments"]} == {"0", "1", "2", "3", "4"}
        assert {item["status"] for item in manifest["field_inventory"]} <= allowed_statuses
        assert bool(template.reference_parameters.get("planner_scope")) == any(
            item["status"] == STATUS_UNSUPPORTED
            and (
                "current Segment 2 row/box" in item.get("note", "")
                or "row-order preservation" in item.get("note", "")
            )
            for item in manifest["field_inventory"]
        )
        blocking_reasons = {
            item.get("reason", "")
            for key in ("missing_publication_parameters", "unsupported_toolkit_structures")
            for item in manifest.get(key, [])
        }
        assert "clinical group/session metadata" not in blocking_reasons
        assert "prosthesis-worn state" not in blocking_reasons
        assert "pre/post intervention phase order" not in blocking_reasons
        assert "wheelchair training condition" not in blocking_reasons
        assert "treadmill state" not in blocking_reasons
        assert "optic flow condition" not in blocking_reasons
        assert "emotional ratings" not in blocking_reasons
        assert "sound-specific emotional validation" not in blocking_reasons
        assert _classify_gap("exact randomization sequence") == [STATUS_DEFAULTED]
        assert _classify_gap("counterbalanced block order from random seed") == [STATUS_DEFAULTED]
        assert STATUS_MISSING in _classify_gap("exact trial count and ITI table")


def test_new_assessment_preloads_preserve_trial_counts_and_launch_gates():
    root = ROOT / "packages" / "pps-resources" / "assets" / "preloads"
    status = json.loads((root / "profile_recreation_status.json").read_text(encoding="utf-8"))
    expected = {
        "maister_2015_shared_sensory_pps": (50, True),
        "bassolino_2010_mouse_right_hand": (36, False),
        "bassolino_2010_mouse_left_hand_no_mouse_first": (48, False),
        "bassolino_2010_mouse_left_hand_passive_first": (48, False),
        "amemiya_2017_ieee_foot_sole_vibration": (192, False),
        "amemiya_2017_ieee_sound_localization": (64, False),
        "bernasconi_2018_trunk_ieeg": (85, False),
        "hobeika_2018_anisotropy_left_handed": (240, False),
        "hobeika_2018_anisotropy_right_handed": (240, False),
        "hobeika_2019_social_audience": (480, False),
        "hobeika_2019_social_collaboration": (480, False),
        "hobeika_2019_social_competition": (480, False),
        "holmes_2019_osf_exp1": (160, False),
        "holmes_2019_osf_exp2": (160, False),
        "holmes_2019_osf_exp2_strong_target": (160, False),
        "holmes_2019_osf_exp3": (160, False),
        "holmes_2019_osf_exp4": (180, False),
        "holmes_2020_exp1": (160, False),
        "holmes_2020_exp2_strong_target": (160, False),
        "holmes_2020_exp2_weak_target": (160, False),
        "holmes_2020_exp3": (160, False),
        "holmes_2020_exp4": (180, False),
        "taffou_2021_auditory_roughness": (0, False),
        "teraoka_2024_front_pps": (54, False),
        "teraoka_2024_rear_pps": (54, False),
        "teneggi_2013_social_face_pps": (208, False),
        "ardizzi_ferri_2018_looming_flat": (300, False),
        "amemiya_2019_foot_sole_exp1": (180, False),
        "amemiya_2019_foot_sole_exp2": (120, False),
        "ferri_2015_artificial_looming_valence": (416, False),
        "ferri_2015_ecological_looming_valence": (0, False),
        "hobeika_2020_logarithmic": (576, False),
        "hobeika_2020_pseudo_linear": (576, False),
        "rahmani_2025_2s_pps": (245, True),
        "rahmani_2025_3s_pps": (245, True),
        "cardini_2018_pregnancy_trunk_pps": (65, True),
        "cardini_2019_pregnancy_trunk_pps": (65, True),
        "chiarella_2024_mindfulness_cheek_pps": (100, False),
        "di_cosmo_2021_phase_coupling": (0, False),
        "ferroni_2020_schizotypy_active": (52, False),
        "ferroni_2020_schizotypy_observation": (52, False),
        "galigani_2020_tool_observation": (360, False),
        "kitagawa_2005_auditory_localization": (0, False),
        "kitagawa_2005_rear_toj": (640, False),
        "kitagawa_2005_tactile_distractor": (0, False),
        "mul_2019_autism_pps": (65, False),
        "murray_2005_audiotactile_alignment": (2400, False),
        "orioli_2019_newborn_audiotactile": (0, False),
        "orioli_2019_newborn_auditory": (0, False),
        "orioli_2019_newborn_pilot": (0, False),
        "ronga_2021_adult_erp": (0, False),
        "ronga_2021_newborn_erp": (0, False),
        "schizophrenia_tool_use_2022": (52, False),
        "sorrentino_2021_ageing_hand_pps": (110, False),
        "teramoto_2013_beyond_head_exp1": (320, False),
        "teramoto_2013_beyond_head_exp2": (16, False),
        "zampini_2005_audiotactile_toj_exp1": (640, False),
        "zampini_2005_audiotactile_toj_exp2": (640, False),
        "zampini_2005_audiotactile_toj_exp3": (40, False),
    }
    for profile in status["profiles"]:
        template_id = profile["template_id"]
        if template_id not in expected:
            continue
        trial_count, launchable = expected.pop(template_id)
        trial_design = root / template_id / "04_trial_designer" / "trial_design.json"
        assert json.loads(trial_design.read_text(encoding="utf-8"))["preview_trial_count"] == trial_count
        assert profile["segment_6_launchable"] is launchable
    assert not expected


def test_profile_recreation_status_distinguishes_ready_missing_and_structural_profiles():
    root = ROOT
    status = json.loads((root / "packages" / "pps-resources" / "assets" / "preloads" / "profile_recreation_status.json").read_text(encoding="utf-8"))
    profiles = {profile["template_id"]: profile for profile in status["profiles"]}

    study5 = profiles[DEFAULT_STUDY_TEMPLATE_ID]
    assert study5["primary_category"] == "gui_recreatable"
    assert study5["publication_status"] == "unpublished_lab_profile"
    assert study5["runner_readiness"] == "ready"
    assert study5["profile_checks_passed"] is True
    assert study5["segment_0_to_4_profile_checks_passed"] is True
    assert study5["missing_parameter_count"] == 0
    assert study5["unsupported_structure_count"] == 0
    assert len(status["categories"]["gui_recreatable"]) == 30
    assert profiles["canzoneri_2013_tool_use_reshaping"]["profile_checks_passed"] is True

    study5_lateral = profiles[STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID]
    assert study5_lateral["primary_category"] == "gui_recreatable"
    assert study5_lateral["publication_status"] == "unpublished_lab_profile"
    assert study5_lateral["runner_readiness"] == "ready"
    assert study5_lateral["profile_checks_passed"] is True
    assert study5_lateral["segment_0_to_4_profile_checks_passed"] is True
    assert study5_lateral["missing_parameter_count"] == 0
    assert study5_lateral["unsupported_structure_count"] == 0

    pfeiffer = profiles["pfeiffer_2018_lateral_perihead_left_to_right"]
    assert pfeiffer["primary_category"] == "gui_recreatable"
    assert pfeiffer["runner_readiness"] == "ready"
    assert pfeiffer["profile_checks_passed"] is True
    assert pfeiffer["segment_0_to_4_profile_checks_passed"] is True

    serino_trunk = profiles["serino_2015_peri_trunk_exp1"]
    assert serino_trunk["primary_category"] == "gui_recreatable"
    assert serino_trunk["profile_checks_passed"] is True
    assert serino_trunk["segment_0_to_4_profile_checks_passed"] is True

    dynaspace = profiles["roussel_2025_dynaspace_mobile_pps"]
    assert dynaspace["primary_category"] == "gui_recreatable"
    assert dynaspace["publication_status"] == "published"
    assert dynaspace["runner_readiness"] == "ready"
    assert dynaspace["profile_checks_passed"] is True
    assert dynaspace["segment_0_to_4_profile_checks_passed"] is True
    assert dynaspace["missing_parameter_count"] == 0
    assert dynaspace["unsupported_structure_count"] == 0

    canzoneri = profiles["canzoneri_2012_dynamic_sounds"]
    assert canzoneri["primary_category"] == "gui_recreatable"
    assert canzoneri["runner_readiness"] == "ready"
    assert canzoneri["profile_checks_passed"] is True
    assert canzoneri["segment_0_to_4_profile_checks_passed"] is True
    assert canzoneri["missing_parameter_count"] == 0
    assert canzoneri["unsupported_structure_count"] == 0

    canzoneri_amputation = profiles["canzoneri_2013_amputation_prosthesis"]
    assert canzoneri_amputation["primary_category"] == "gui_recreatable"
    assert canzoneri_amputation["runner_readiness"] == "ready"
    assert canzoneri_amputation["profile_checks_passed"] is True
    assert canzoneri_amputation["segment_0_to_4_profile_checks_passed"] is True
    assert canzoneri_amputation["missing_parameter_count"] == 0
    assert canzoneri_amputation["unsupported_structure_count"] == 0

    tonelli = profiles["tonelli_2019_echolocation"]
    assert tonelli["primary_category"] == "gui_recreatable"
    assert tonelli["runner_readiness"] == "ready"
    assert tonelli["profile_checks_passed"] is True
    assert tonelli["segment_0_to_4_profile_checks_passed"] is True
    assert tonelli["missing_parameter_count"] == 0
    assert tonelli["unsupported_structure_count"] == 0

    serino_2007 = profiles["serino_2007_blind_cane_users"]
    assert serino_2007["primary_category"] == "missing_publication_parameters"
    assert serino_2007["runner_readiness"] == "blocked_missing_parameters"
    assert serino_2007["profile_checks_passed"] is False
    assert serino_2007["segment_0_to_4_profile_checks_passed"] is False
    assert serino_2007["missing_parameter_count"] == 4
    assert serino_2007["unsupported_structure_count"] == 0

    serino_front_back = profiles["serino_2015_front_back_trunk_exp2"]
    assert serino_front_back["primary_category"] == "gui_recreatable"
    assert serino_front_back["runner_readiness"] == "ready"
    assert serino_front_back["profile_checks_passed"] is True
    assert serino_front_back["segment_0_to_4_profile_checks_passed"] is True
    assert serino_front_back["missing_parameter_count"] == 0
    assert serino_front_back["unsupported_structure_count"] == 0

    serino_toolless = profiles["serino_2015_toolless_sync_training"]
    assert serino_toolless["primary_category"] == "gui_recreatable"
    assert serino_toolless["runner_readiness"] == "ready"
    assert serino_toolless["profile_checks_passed"] is True
    assert serino_toolless["segment_0_to_4_profile_checks_passed"] is True
    assert serino_toolless["missing_parameter_count"] == 0
    assert serino_toolless["unsupported_structure_count"] == 0

    galli = profiles["galli_2015_wheelchair_full_body"]
    assert galli["primary_category"] == "gui_recreatable"
    assert galli["runner_readiness"] == "ready"
    assert galli["profile_checks_passed"] is True
    assert galli["segment_0_to_4_profile_checks_passed"] is True
    assert galli["missing_parameter_count"] == 0
    assert galli["unsupported_structure_count"] == 0

    serino_hand = profiles["serino_2015_peri_hand_exp3"]
    assert serino_hand["primary_category"] == "gui_recreatable"
    assert serino_hand["runner_readiness"] == "ready"
    assert serino_hand["profile_checks_passed"] is True
    assert serino_hand["segment_0_to_4_profile_checks_passed"] is True
    assert serino_hand["missing_parameter_count"] == 0
    assert serino_hand["unsupported_structure_count"] == 0

    tajadura_uncrossed = profiles["tajadura_jimenez_2009_uncrossed_visual_deprivation"]
    assert tajadura_uncrossed["primary_category"] == "gui_recreatable"
    assert tajadura_uncrossed["publication_status"] == "published"
    assert tajadura_uncrossed["runner_readiness"] == "ready"
    assert tajadura_uncrossed["profile_checks_passed"] is True
    assert tajadura_uncrossed["segment_0_to_4_profile_checks_passed"] is True
    assert tajadura_uncrossed["missing_parameter_count"] == 0
    assert tajadura_uncrossed["unsupported_structure_count"] == 0

    tajadura_crossed = profiles["tajadura_jimenez_2009_crossed_visual_deprivation"]
    assert tajadura_crossed["primary_category"] == "gui_recreatable"
    assert tajadura_crossed["publication_status"] == "published"
    assert tajadura_crossed["runner_readiness"] == "ready"
    assert tajadura_crossed["profile_checks_passed"] is True
    assert tajadura_crossed["segment_0_to_4_profile_checks_passed"] is True
    assert tajadura_crossed["missing_parameter_count"] == 0
    assert tajadura_crossed["unsupported_structure_count"] == 0

    for template_id in (
        "biggio_2017_no_racket",
        "biggio_2017_common_racket",
        "biggio_2017_personal_racket",
    ):
        biggio = profiles[template_id]
        assert biggio["primary_category"] == "gui_recreatable"
        assert biggio["publication_status"] == "published"
        assert biggio["runner_readiness"] == "ready"
        assert biggio["profile_checks_passed"] is True
        assert biggio["segment_0_to_4_profile_checks_passed"] is True
        assert biggio["missing_parameter_count"] == 0
        assert biggio["unsupported_structure_count"] == 0

    report = (root / "docs" / "PUBLISHED_STUDY_RECREATION_STATUS.md").read_text(encoding="utf-8")
    assert "## GUI-recreatable" in report
    assert "## Missing publication parameters" in report
    assert "## Toolkit structural gap" in report
    assert "Clinical populations, interventions, and non-audiotactile experimental context" in report
    assert "Ordinary trial randomization and block order" in report

    tex_report = (
        root
        / "For-AI"
        / "research"
        / "literature"
        / "docs"
        / "audit_report.tex"
    ).read_text(encoding="utf-8")
    assert "Published-paper profiles passing checks & 22" in tex_report
    assert "study5" in tex_report and "box" in tex_report and "breathing" in tex_report
    assert "No visible GUI progress indicator" in tex_report
    assert "Clinical populations, interventions, non-audiotactile stimuli" in tex_report


def test_preload_trial_designs_distinguish_inspection_from_playback():
    root = ROOT
    templates = load_templates(root / "packages" / "pps-resources" / "study_templates")

    for template in templates:
        trial_design_path = (
            root
            / "packages"
            / "pps-resources"
            / "assets"
            / "preloads"
            / template.template_id
            / "04_trial_designer"
            / "trial_design.json"
        )
        trial_design = json.loads(trial_design_path.read_text(encoding="utf-8"))
        strips = trial_design.get("trial_strips") or []
        if template.reference_parameters.get("planner_scope"):
            assert not any(strip.get("elements") for strip in strips), template.template_id
            assert trial_design["preview_trial_count"] == 0, template.template_id
            assert not block_trial_rows(template.design), template.template_id
            continue
        assert strips, template.template_id
        for strip in strips:
            assert strip.get("elements"), (template.template_id, strip.get("label"))
            for element in strip["elements"]:
                if element.get("kind") in {"fixed_audio", "looming_stimulus"}:
                    assert element.get("source_labels"), (
                        template.template_id,
                        strip.get("label"),
                        element.get("label"),
                    )


def test_source_backed_previews_preserve_trial_families_and_phase_order():
    templates = {
        template.template_id: template
        for template in load_templates(ROOT / "packages/pps-resources/study_templates")
    }
    expected = {
        "ferri_2015_premotor_itv_behavior": Counter({"Audio-Tactile": 180, "Catch": 120}),
        "serino_2015_peri_hand_posture_exp5": Counter({"Audio-Tactile": 288, "Baseline": 96, "Catch": 48}),
        "teneggi_2013_cooperative_game_exp2": Counter({"Audio-Tactile": 160, "Catch": 48}),
    }
    for profile_id, counts in expected.items():
        rows = block_trial_rows(templates[profile_id].design)
        assert Counter(row["trial_type"] for row in rows) == counts
        preload = ROOT / "packages/pps-resources/assets/preloads" / profile_id
        trial_design = json.loads((preload / "04_trial_designer/trial_design.json").read_text(encoding="utf-8"))
        assert trial_design["preview_trial_count"] == len(rows)
        manifest = json.loads((preload / "01_profile/profile_parameters_manifest.json").read_text(encoding="utf-8"))
        assert not manifest["recreation_status"]["segment_6_launchable"]
    cooperative = block_trial_rows(templates["teneggi_2013_cooperative_game_exp2"].design)
    assert list(dict.fromkeys(row["block_label"] for row in cooperative)) == [
        "Before game 1", "Before game 2", "After game 1", "After game 2",
    ]
    assert Counter(row["block_label"] for row in cooperative) == {
        "Before game 1": 52, "Before game 2": 52, "After game 1": 52, "After game 2": 52,
    }


def test_replication_assessments_preserve_counts_and_declared_motion():
    templates = {
        template.template_id: template
        for template in load_templates(ROOT / "packages/pps-resources/study_templates")
    }
    for seconds, step in ((2, 250), (3, 375)):
        rows = block_trial_rows(templates[f"rahmani_2025_{seconds}s_pps"].design)
        assert len({row["block_index"] for row in rows}) == 3
        assert sum(row["trial_type"] == "Catch" for row in rows) == 21
        for family in ("Audio-Tactile", "Baseline"):
            targets = [row for row in rows if row["trial_type"] == family]
            assert Counter(row["soa_ms"] for row in targets) == {step * i: 16 for i in range(1, 8)}
            assert {row["tactile_waveform_shape"] for row in targets} == {"sawtooth"}
            assert {row["tactile_frequency_hz"] for row in targets} == {80}
            assert {row["tactile_duration_ms"] for row in targets} == {200}

    for year in (2018, 2019):
        rows = block_trial_rows(templates[f"cardini_{year}_pregnancy_trunk_pps"].design)
        assert sum(row["trial_type"] == "Catch" for row in rows) == 15
        assert Counter(row["soa_ms"] for row in rows if row["trial_type"] == "Audio-Tactile") == {
            300: 10, 800: 10, 1500: 10, 2200: 10, 2500: 10,
        }

    rows = block_trial_rows(templates["ardizzi_ferri_2018_looming_flat"].design)
    assert {row["motion_direction"] for row in rows if "flat" in row["noise_label"].lower()} == {"stationary"}
    assert {row["motion_direction"] for row in rows if "looming" in row["noise_label"].lower()} == {"looming"}


def test_barumerli_segment2_expands_analog_motion_to_binaural_source_variants():
    root = ROOT
    trial_design = json.loads(
        (
            root
            / "packages"
            / "pps-resources"
            / "assets"
            / "preloads"
            / "barumerli_2026_arm_movement_exp1"
            / "04_trial_designer"
            / "trial_design.json"
        ).read_text(encoding="utf-8")
    )
    labels = trial_design["trial_strips"][0]["elements"][0]["source_labels"]

    assert labels == ["Pink moving sound", "Pink moving sound - receding"]


def test_protocol12_matrix_targets_ready_published_profiles_and_blocked_samples():
    matrix = _load_validation_script("run_profile_recreation_interface_matrix.py")
    status = json.loads((ROOT / "packages" / "pps-resources" / "assets" / "preloads" / "profile_recreation_status.json").read_text(encoding="utf-8"))

    ready_published = matrix._target_template_ids(status, profile_set="ready-published")
    ready_all = matrix._target_template_ids(status, profile_set="ready-all")
    blocked_samples = matrix._default_blocked_samples(status, exclude=set(ready_published))

    assert DEFAULT_STUDY_TEMPLATE_ID not in ready_published
    assert STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID not in ready_published
    assert DEFAULT_STUDY_TEMPLATE_ID in ready_all
    assert STUDY5_DYNASPACE_LATERAL_TEMPLATE_ID in ready_all
    assert len(ready_published) == 28
    assert "maister_2015_shared_sensory_pps" in ready_published
    assert "canzoneri_2013_tool_use_reshaping" in ready_published
    assert set(ready_published) < set(ready_all)
    assert len(blocked_samples) == 2

    profiles = {profile["template_id"]: profile for profile in status["profiles"]}
    assert any(profiles[item]["missing_parameter_count"] > 0 for item in blocked_samples)
    assert any(profiles[item]["unsupported_structure_count"] > 0 for item in blocked_samples)


def test_protocol12_matrix_metadata_only_report_accepts_ready_and_blocked(tmp_path: Path):
    matrix = _load_validation_script("run_profile_recreation_interface_matrix.py")

    report = matrix.run_matrix(
        output_dir=tmp_path,
        templates=["pfeiffer_2018_lateral_perihead_left_to_right"],
        blocked_templates=["taffou_2014_cynophobic_rear_looming"],
        metadata_only=True,
    )

    assert report["schema"] == matrix.SCHEMA
    assert report["passed"]
    assert report["ready_profile_count"] == 1
    assert report["blocked_profile_sample_count"] == 1
    assert report["profile_results"][0]["gate_passed"]
    assert report["profile_results"][0]["materialization"]["status"] == "skipped"
    assert report["blocked_results"][0]["blocked"]
    assert (tmp_path / "profile_recreation_interface_matrix_report.json").exists()
    assert (tmp_path / "profile_recreation_interface_matrix_report.md").exists()


def test_protocol12_matrix_materializes_session_packages_under_each_profile_root(tmp_path: Path):
    matrix = _load_validation_script("run_profile_recreation_interface_matrix.py")

    report = matrix.run_matrix(
        output_dir=tmp_path,
        templates=["roussel_2025_dynaspace_mobile_pps", "matsuda_2021_four_directions"],
        skip_blocked_samples=True,
    )

    assert report["schema"] == matrix.SCHEMA
    assert report["passed"]
    local_criteria = [
        criterion
        for criterion in report["criteria"]
        if criterion["name"].endswith(":participant_package_profile_local")
    ]
    assert len(local_criteria) == 2
    assert all(criterion["passed"] for criterion in local_criteria)

    for result in report["profile_results"]:
        materialization = result["materialization"]
        expected_root = Path(materialization["expected_session_root"]).resolve()
        session_dir = Path(materialization["session_dir"]).resolve()
        session_manifest = Path(materialization["session_manifest_path"]).resolve()

        assert result["template_id"] in str(expected_root)
        assert session_dir == expected_root or expected_root in session_dir.parents
        assert session_manifest == expected_root or expected_root in session_manifest.parents
        assert os.path.isfile(matrix._filesystem_path(session_manifest))
