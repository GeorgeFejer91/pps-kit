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
    "biggio_2017_racket_tool_use",
    "canzoneri_2012_dynamic_sounds",
    "cell_reports_medicine_2026_consciousness",
    "disorders_consciousness_2019",
    "farne_ladavas_2002_auditory_pps_humans",
    "finisguerra_2015_moving_sounds_motor",
    "ieeg_trunk_2018",
    "lamia_2026_arm_movement",
    "matsuda_2021_four_directions",
    "noel_2015_bodily_self",
    "pfeiffer_2018_vestibular",
    "ronga_2021_newborn_erp",
    "serino_2007_blind_cane_users",
    "serino_2015_exps_4_to_6",
    "serino_2015_front_back_trunk_exp2",
    "serino_2015_peri_hand_exp3",
    "serino_2015_peri_trunk_exp1",
    "smartphone_rt_methods_2025",
    "taffou_2021_auditory_roughness",
    "tajadura_jimenez_2009_visual_deprivation",
    "tonelli_2019_echolocation",
}

RUNNABLE_STRUCTURED_IDS = {
    "noel_2015_bodily_self",
    "serino_2015_peri_trunk_exp1",
    "pfeiffer_2018_vestibular",
    "matsuda_2021_four_directions",
    "lamia_2026_arm_movement",
    "smartphone_rt_methods_2025",
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
        "structured_expected_outcome_record_count": 21,
        "pending_expected_outcome_record_count": 49,
        "adjacent_or_out_of_scope_record_count": 4,
        "runnable_profile_parameter_record_count": 6,
        "observed_behavioral_comparison_record_count": 0,
        "parameter_run_evidence_only_record_count": 6,
        "not_runnable_no_observed_comparison_record_count": 64,
        "adjacent_not_applicable_record_count": 4,
        "pending_expected_outcome_blocker_counts": {
            "main_pdf_unavailable_or_paywalled": 24,
            "manual_review_needs_results_direction_structuring": 1,
            "manual_review_partial_or_supplement_blocked": 1,
            "needs_user_pdf_download": 9,
            "source_mined_needs_results_visual_review": 14,
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
        assert record["observed_vs_expected_status"] == "parameter_run_evidence_only_behavioral_effect_unobserved"

    nonrunnable_structured = structured_ids - RUNNABLE_STRUCTURED_IDS
    assert nonrunnable_structured
    for record_id in nonrunnable_structured:
        record = records[record_id]
        assert record["runnable_status"] != "runnable_profile_parameters_ready"
        assert record["observed_vs_expected_status"] == "not_runnable_no_observed_comparison"

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
    assert blocker_total == len(pending_records) == 49

    assert (
        records["mindfulness_pps_2024"]["expected_outcome_extraction_blocker"]
        == "manual_review_needs_results_direction_structuring"
    )
    assert records["depersonalisation_2024"]["expected_outcome_extraction_blocker"] == (
        "manual_review_partial_or_supplement_blocked"
    )
    assert records["ferri_2015_jneurosci_itv"]["expected_outcome_extraction_blocker"] == (
        "source_mined_needs_results_visual_review"
    )
    assert records["ladavas_2001_auditory_tactile_extinction"]["expected_outcome_extraction_blocker"] == (
        "main_pdf_unavailable_or_paywalled"
    )
    assert records["canzoneri_2013_tool_use_reshaping"]["expected_outcome_extraction_blocker"] == (
        "needs_user_pdf_download"
    )

    structured = records["canzoneri_2012_dynamic_sounds"]
    assert structured["expected_outcome_extraction_blocker"] == "structured_expected_outcome_available"
    assert structured["expected_outcome_source_audit"]["manual_review_confidence_label"] == (
        "high_confidence_extraction"
    )


def test_expected_outcome_blocked_and_adjacent_records_do_not_claim_observed_comparison():
    outcome = json.loads(OUTCOME_PATH.read_text(encoding="utf-8"))
    records = {record["record_id"]: record for record in outcome["records"]}

    for record_id in [
        "canzoneri_2013_tool_use_reshaping",
        "canzoneri_2013_amputation_prosthesis",
        "ferri_2015_artificial_valence",
        "hobeika_2020_methods",
    ]:
        record = records[record_id]
        assert record["runnable_status"] != "runnable_profile_parameters_ready"
        assert record["observed_vs_expected_status"] == "not_runnable_no_observed_comparison"
        assert record["required_next_evidence"].startswith("Extract a short structured expected outcome")

    for record_id in [
        "canzoneri_2012_dynamic_sounds",
        "tonelli_2019_echolocation",
        "serino_2015_front_back_trunk_exp2",
    ]:
        record = records[record_id]
        assert record["runnable_status"] == "template_present_but_blocked"
        assert record["expected_outcome_status"] == "structured_expected_outcome_extracted"
        assert record["required_next_evidence"].startswith("Resolve profile blockers")

    for record_id in [
        "farne_ladavas_2002_auditory_pps_humans",
        "taffou_2021_auditory_roughness",
        "cell_reports_medicine_2026_consciousness",
    ]:
        record = records[record_id]
        assert record["runnable_status"] == "not_yet_templated"
        assert record["expected_outcome_status"] == "structured_expected_outcome_extracted"
        assert record["required_next_evidence"].startswith("Create a profile template")

    adjacent = records["barumerli_2026_semantic_looming_auditory_only"]
    assert adjacent["expected_outcome_status"] == "adjacent_out_of_scope"
    assert adjacent["observed_vs_expected_status"] == "adjacent_not_applicable"
    assert adjacent["required_next_evidence"] == "No outcome comparison required unless the record is reclassified as in scope."


def test_expected_outcome_current_observed_evidence_is_software_only():
    outcome = json.loads(OUTCOME_PATH.read_text(encoding="utf-8"))
    evidence = outcome["current_observed_evidence"]

    assert set(evidence) == {
        "profile_materialization",
        "static_dashboard_parity",
        "runner_mock",
        "click_path_mock",
        "synthetic_response_marker_loopback",
    }
    assert evidence["profile_materialization"].endswith("profile_recreation_interface_matrix_report.json")
    assert evidence["runner_mock"].endswith("one_block_trial_runner_report.json")
    assert evidence["synthetic_response_marker_loopback"].endswith("response_marker_loopback_report.json")
    assert all(value.startswith("artifacts/validation_runs/") for value in evidence.values())
