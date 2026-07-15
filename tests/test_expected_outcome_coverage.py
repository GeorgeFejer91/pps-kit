from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
OUTCOME_PATH = ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"
BUILDER_PATH = ROOT / "tools" / "build_expected_outcome_coverage.py"

STRUCTURED_EXPECTED_OUTCOME_IDS = {
    "ageing_2021",
    "amiel_2025_front_rear",
    "amemiya_2017_pseudowalking_footsole",
    "ardizzi_ferri_2018_interoceptive",
    "autism_2019",
    "avenanti_2012_motor_cortex",
    "bassolino_2010_mouse_use",
    "biggio_2017_racket_tool_use",
    "body_image_social_cognition_2024",
    "canzoneri_2013_amputation_prosthesis",
    "canzoneri_2013_tool_use_reshaping",
    "canzoneri_2012_dynamic_sounds",
    "cell_reports_medicine_2026_consciousness",
    "cimmino_2013_surgical_arm_elongation",
    "depersonalisation_2024",
    "disorders_consciousness_2019",
    "farne_ladavas_2002_auditory_pps_humans",
    "ferri_2015_artificial_valence",
    "ferri_2015_ecological_valence",
    "ferri_2015_jneurosci_itv",
    "ferroni_2020_tool_observation",
    "finisguerra_2015_moving_sounds_motor",
    "footsole_vibration_2019",
    "galli_2015_wheelchair",
    "hobeika_2018_anisotropy",
    "hobeika_2020_methods",
    "holmes_2020_four_experiments",
    "ieeg_trunk_2018",
    "interoception_exteroception_2025",
    "jazz_duet_2021",
    "kitagawa_2005_sound_complexity",
    "ladavas_2001_auditory_tactile_extinction",
    "lamia_2026_arm_movement",
    "lerner_2021_3d_boundary",
    "looming_duration_2025",
    "maister_2015_shared_sensory",
    "matsuda_2021_four_directions",
    "mindfulness_pps_2024",
    "newborn_boundaries_2019",
    "novel_two_phase_audio_tactile_2025",
    "noel_2015_bodily_self",
    "noel_2015_walking",
    "noel_2018_neural_adaptation",
    "pfeiffer_2018_vestibular",
    "pregnancy_2019",
    "ronga_2021_newborn_erp",
    "seeming_confines_2021",
    "serino_2011_professional_fencers",
    "serino_2011_rtms",
    "schizophrenia_tool_use_2022",
    "serino_2007_blind_cane_users",
    "serino_2009_tms",
    "serino_2018_mixed_reality_pps",
    "serino_2015_exps_4_to_6",
    "serino_2015_front_back_trunk_exp2",
    "serino_2015_peri_hand_exp3",
    "serino_2015_peri_trunk_exp1",
    "serino_2015_toolless_sync_training",
    "smartphone_rt_methods_2025",
    "social_coding_2019",
    "social_perception_2017",
    "spadone_2021_connectivity",
    "taffou_2014_cynophobic_rear_looming",
    "taffou_2021_auditory_roughness",
    "tajadura_jimenez_2009_visual_deprivation",
    "teneggi_2013_social_face",
    "teramoto_2013_beyond_head_audiotactile",
    "teramoto_2013_visual_deprivation",
    "teraoka_2024_front_rear",
    "tonelli_2019_echolocation",
}

RUNNABLE_STRUCTURED_IDS = {
    "canzoneri_2012_dynamic_sounds",
    "galli_2015_wheelchair",
    "lerner_2021_3d_boundary",
    "noel_2015_bodily_self",
    "serino_2015_front_back_trunk_exp2",
    "serino_2015_peri_hand_exp3",
    "serino_2015_peri_trunk_exp1",
    "pfeiffer_2018_vestibular",
    "matsuda_2021_four_directions",
    "lamia_2026_arm_movement",
    "smartphone_rt_methods_2025",
    "tonelli_2019_echolocation",
}


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_expected_outcome_coverage", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_expected_outcome_coverage_matches_literature_records_and_builder():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    outcome = json.loads(OUTCOME_PATH.read_text(encoding="utf-8"))
    builder = _load_builder()

    assert outcome == builder.build_expected_outcome_coverage(coverage)
    assert outcome["schema"] == builder.SCHEMA
    assert outcome["source_literature_coverage"] == "assets/preloads/audiotactile_literature_coverage.json"
    assert outcome["summary"]["literature_record_count"] == len(outcome["records"]) == len(
        coverage["literature_records"]
    ) == 74

    coverage_ids = {record["record_id"] for record in coverage["literature_records"]}
    outcome_ids = {record["record_id"] for record in outcome["records"]}
    assert outcome_ids == coverage_ids


def test_expected_outcome_layer_is_conservative_about_behavioral_validation():
    outcome = json.loads(OUTCOME_PATH.read_text(encoding="utf-8"))
    records = {record["record_id"]: record for record in outcome["records"]}

    structured_ids = {
        record_id
        for record_id, record in records.items()
        if record["expected_outcome_status"] == "structured_expected_outcome_extracted"
    }
    assert structured_ids == STRUCTURED_EXPECTED_OUTCOME_IDS
    assert outcome["summary"] == {
        "literature_record_count": 74,
        "structured_expected_outcome_record_count": 70,
        "pending_expected_outcome_record_count": 0,
        "adjacent_or_out_of_scope_record_count": 4,
        "runnable_profile_parameter_record_count": 12,
        "observed_behavioral_comparison_record_count": 0,
        "synthetic_profile_contrast_comparison_record_count": 12,
        "parameter_run_evidence_only_record_count": 0,
        "not_runnable_no_observed_comparison_record_count": 58,
        "adjacent_not_applicable_record_count": 4,
        "pending_expected_outcome_blocker_counts": {},
        "observed_comparison_gap_counts": {
            "not_applicable_adjacent_out_of_scope": 4,
            "not_yet_templated_missing_publication_parameters": 22,
            "not_yet_templated_requires_toolkit_structure": 28,
            "ready_profile_synthetic_contrast_available_needs_mouse_click_simulated_participant_like_comparison": 12,
            "template_present_blocked_missing_publication_parameters": 8,
        },
    }

    for record_id in structured_ids:
        record = records[record_id]
        expected = record["expected_outcome"]
        assert expected["primary_expected_effect"]
        assert expected["expected_effect_direction"]
        assert expected["observable_metric"]
        assert expected["condition_contrast"]
        assert expected["source_basis"]

    for record_id in RUNNABLE_STRUCTURED_IDS:
        record = records[record_id]
        assert record["runnable_status"] == "runnable_profile_parameters_ready"
        assert record["observed_vs_expected_status"] == (
            "synthetic_profile_contrast_comparison_available_behavioral_effect_unobserved"
        )
        assert record["observed_comparison_gap"] == (
            "ready_profile_synthetic_contrast_available_needs_mouse_click_simulated_participant_like_comparison"
        )
        assert record["observed_profile_contrast_evidence"] == {
            "status": "deterministic_synthetic_profile_contrast_comparison_available",
            "source_report": (
                "artifacts/validation_runs/current_goal_ready_profile_expected_contrast_audit_20260715/"
                "ready_profile_expected_contrast_audit_report.json"
            ),
            "model_boundary": (
                "Deterministic synthetic RT comparisons over runner rows; not collected participant data, "
                "not mouse-click-simulated participant-like runner behavior, and not a scientific "
                "replication claim."
            ),
        }
        assert "deterministic synthetic comparison" in record["observed_evidence_boundary"]
        assert record["required_next_evidence"].startswith("Run a participant-like mouse-click simulation")

    nonrunnable_structured = structured_ids - RUNNABLE_STRUCTURED_IDS
    assert nonrunnable_structured
    for record_id in nonrunnable_structured:
        record = records[record_id]
        assert record["runnable_status"] != "runnable_profile_parameters_ready"
        assert record["observed_vs_expected_status"] == "not_runnable_no_observed_comparison"
        assert record["observed_comparison_gap"] in {
            "template_present_blocked_missing_publication_parameters",
            "template_present_blocked_toolkit_structure",
            "not_yet_templated_missing_publication_parameters",
            "not_yet_templated_requires_toolkit_structure",
        }

    assert all(
        record["observed_vs_expected_status"] != "observed_behavioral_comparison_available"
        for record in records.values()
    )
    assert "do not prove human behavioral PPS effects" in outcome["scope"]["evidence_boundary"]


def test_expected_outcome_pending_blockers_are_actionable():
    outcome = json.loads(OUTCOME_PATH.read_text(encoding="utf-8"))
    records = {record["record_id"]: record for record in outcome["records"]}

    assert outcome["expected_outcome_extraction_sources"] == {
        "paper_audit_checklist": "For-AI/audiotactile-paper-metadata-audit/running_checklist.csv",
        "manual_review_index": "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv",
    }

    pending_records = [
        record
        for record in records.values()
        if record["expected_outcome_status"] == "pending_expected_outcome_extraction"
    ]
    blocker_total = sum(outcome["summary"]["pending_expected_outcome_blocker_counts"].values())
    assert blocker_total == len(pending_records) == 0

    structured = records["canzoneri_2012_dynamic_sounds"]
    assert structured["expected_outcome_extraction_blocker"] == "structured_expected_outcome_available"
    assert structured["expected_outcome_source_audit"]["manual_review_confidence_label"] == (
        "high_confidence_extraction"
    )

    mindfulness = records["mindfulness_pps_2024"]
    assert mindfulness["expected_outcome_status"] == "structured_expected_outcome_extracted"
    assert mindfulness["expected_outcome"]["expected_effect_direction"] == (
        "fam_reduces_pps_boundary_sharpness_without_extension_reduction"
    )

    front_rear = records["teraoka_2024_front_rear"]
    assert front_rear["expected_outcome_status"] == "structured_expected_outcome_extracted"
    assert front_rear["expected_outcome"]["expected_effect_direction"] == (
        "rear_space_audio_tactile_facilitation_exceeds_front_space"
    )

    amputation = records["canzoneri_2013_amputation_prosthesis"]
    assert amputation["expected_outcome"]["expected_effect_direction"] == (
        "prosthesis_extends_amputated_side_pps_after_stump_shift_without_prosthesis"
    )

    walking = records["noel_2015_walking"]
    assert walking["expected_outcome"]["expected_effect_direction"] == (
        "walking_expands_chest_pps_to_farther_looming_sound_distances"
    )

    holmes = records["holmes_2020_four_experiments"]
    assert holmes["expected_outcome"]["expected_effect_direction"] == (
        "small_near_sound_rt_benefit_without_robust_distance_gradient"
    )

    kitagawa = records["kitagawa_2005_sound_complexity"]
    assert kitagawa["expected_outcome"]["expected_effect_direction"] == (
        "near_rear_complex_sounds_increase_audio_tactile_interference"
    )

    interoception = records["interoception_exteroception_2025"]
    assert interoception["expected_outcome"]["expected_effect_direction"] == (
        "cardiac_interoception_competes_with_tactile_rt_and_facilitates_self_relevance_encoding"
    )

    looming_duration = records["looming_duration_2025"]
    assert looming_duration["expected_outcome"]["expected_effect_direction"] == (
        "both_2s_and_3s_looming_sounds_facilitate_late_tactile_rt_with_duration_specific_boundaries"
    )

    ladavas = records["ladavas_2001_auditory_tactile_extinction"]
    assert ladavas["expected_outcome"]["expected_effect_direction"] == (
        "near_ipsilesional_complex_sounds_increase_contralesional_head_tactile_extinction"
    )

    jazz = records["jazz_duet_2021"]
    assert jazz["expected_outcome"]["expected_effect_direction"] == (
        "uncooperative_jazz_interaction_slows_near_audio_tactile_rt"
    )

    amemiya = records["amemiya_2017_pseudowalking_footsole"]
    assert amemiya["expected_outcome"]["expected_effect_direction"] == (
        "footsole_pseudowalking_vibration_expands_forward_pps"
    )

    two_phase = records["novel_two_phase_audio_tactile_2025"]
    assert two_phase["expected_outcome"]["expected_effect_direction"] == (
        "conditional_nonself_associated_sounds_widen_and_rigidify_pps_if_cognitive_self_associations_modulate_pps"
    )


def test_expected_outcome_blocked_and_adjacent_records_do_not_claim_observed_comparison():
    outcome = json.loads(OUTCOME_PATH.read_text(encoding="utf-8"))
    records = {record["record_id"]: record for record in outcome["records"]}

    for record_id in [
        "taffou_2014_cynophobic_rear_looming",
        "noel_2015_walking",
        "hobeika_2020_methods",
        "amemiya_2017_pseudowalking_footsole",
    ]:
        record = records[record_id]
        assert record["runnable_status"] != "runnable_profile_parameters_ready"
        assert record["observed_vs_expected_status"] == "not_runnable_no_observed_comparison"
        if record["expected_outcome_status"] == "pending_expected_outcome_extraction":
            assert record["required_next_evidence"].startswith("Extract a short structured expected outcome")

    for record_id in [
        "canzoneri_2013_tool_use_reshaping",
    ]:
        record = records[record_id]
        assert record["runnable_status"] == "template_present_but_blocked"
        assert record["expected_outcome_status"] == "structured_expected_outcome_extracted"
        assert record["observed_comparison_gap"] in {
            "template_present_blocked_missing_publication_parameters",
            "template_present_blocked_toolkit_structure",
        }
        assert record["required_next_evidence"].startswith("Resolve profile blockers")

    for record_id in [
        "farne_ladavas_2002_auditory_pps_humans",
        "taffou_2021_auditory_roughness",
        "cell_reports_medicine_2026_consciousness",
    ]:
        record = records[record_id]
        assert record["runnable_status"] == "not_yet_templated"
        assert record["expected_outcome_status"] == "structured_expected_outcome_extracted"
        assert record["observed_comparison_gap"] in {
            "not_yet_templated_missing_publication_parameters",
            "not_yet_templated_requires_toolkit_structure",
        }
        assert record["required_next_evidence"].startswith("Create a profile template")

    adjacent = records["barumerli_2026_semantic_looming_auditory_only"]
    assert adjacent["expected_outcome_status"] == "adjacent_out_of_scope"
    assert adjacent["observed_vs_expected_status"] == "adjacent_not_applicable"
    assert adjacent["observed_comparison_gap"] == "not_applicable_adjacent_out_of_scope"
    assert adjacent["required_next_evidence"] == (
        "No outcome comparison required unless the record is reclassified as in scope."
    )


def test_expected_outcome_current_observed_evidence_is_software_only():
    outcome = json.loads(OUTCOME_PATH.read_text(encoding="utf-8"))
    evidence = outcome["current_observed_evidence"]

    assert set(evidence) == {
        "profile_materialization",
        "static_dashboard_parity",
        "runner_mock",
        "ready_profile_runner_smoke",
        "ready_profile_response_marker_loopback",
        "ready_profile_expected_contrast_audit",
        "click_path_mock",
        "synthetic_response_marker_loopback",
        "synthetic_expected_outcome_smoke",
    }
    assert evidence["profile_materialization"].endswith("profile_recreation_interface_matrix_report.json")
    assert evidence["runner_mock"].endswith("one_block_trial_runner_report.json")
    assert evidence["ready_profile_runner_smoke"].endswith("ready_profile_runner_smoke_report.json")
    assert evidence["ready_profile_response_marker_loopback"].endswith(
        "ready_profile_response_marker_loopback_report.json"
    )
    assert evidence["ready_profile_expected_contrast_audit"].endswith(
        "ready_profile_expected_contrast_audit_report.json"
    )
    assert evidence["synthetic_response_marker_loopback"].endswith("response_marker_loopback_report.json")
    assert evidence["synthetic_expected_outcome_smoke"].endswith("synthetic_expected_outcome_smoke_report.json")
    assert all(value.startswith("artifacts/validation_runs/") for value in evidence.values())
