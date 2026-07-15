from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
HOLMES_PATH = ROOT / "assets" / "preloads" / "audiotactile_holmes2020_consensus_screening.json"
OPENALEX_PATH = ROOT / "assets" / "preloads" / "audiotactile_openalex_broad_screening.json"
OPENALEX_CANDIDATE_SCREENING_PATH = (
    ROOT / "assets" / "preloads" / "audiotactile_openalex_candidate_screening.json"
)
OPENALEX_QUERY_VARIANT_SCREENING_PATH = (
    ROOT / "assets" / "preloads" / "audiotactile_openalex_query_variant_screening.json"
)
PUBMED_QUERY_VARIANT_SCREENING_PATH = (
    ROOT / "assets" / "preloads" / "audiotactile_pubmed_query_variant_screening.json"
)
WEB_SANITY_SCREENING_PATH = (
    ROOT / "assets" / "preloads" / "audiotactile_web_sanity_screening.json"
)
PUBMED_ABSTRACTS_PATH = ROOT / "artifacts" / "literature_audit" / "pubmed_missing_screen_abstracts.json"
SCREENING_PATH = ROOT / "assets" / "preloads" / "audiotactile_pubmed_screening.json"
STATUS_PATH = ROOT / "assets" / "preloads" / "profile_recreation_status.json"


def test_literature_coverage_ledger_matches_current_template_inventory():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))

    assert coverage["schema"] == "pps-audiotactile-literature-coverage.v1"
    assert coverage["coverage_summary"]["literature_record_count"] == len(coverage["literature_records"]) == 74
    assert coverage["coverage_summary"]["literature_record_category_counts"] == {
        "covered_runnable_profile": 12,
        "covered_blocked_missing_publication_parameters": 7,
        "covered_blocked_toolkit_structure": 1,
        "not_yet_templated_requires_toolkit_structure": 29,
        "not_yet_templated_missing_publication_parameters": 21,
        "candidate_needs_full_text_task_audit": 0,
        "adjacent_out_of_scope": 4,
    }
    assert coverage["coverage_summary"]["current_template_count"] == status["profile_count"] == 24
    assert coverage["coverage_summary"]["current_profile_check_pass_count"] == len(
        status["categories"]["gui_recreatable"]
    ) == 16
    assert coverage["coverage_summary"]["published_profile_check_pass_count"] == 14
    assert coverage["coverage_summary"]["local_unpublished_profile_check_pass_count"] == 2
    assert coverage["coverage_summary"]["current_templates_with_toolkit_structural_gaps"] == 1
    assert coverage["coverage_summary"]["pubmed_screened_records"] == 48
    assert coverage["coverage_summary"]["openalex_broad_candidate_like_hits"] == 103
    assert coverage["coverage_summary"]["openalex_broad_linked_candidate_like_hits"] == 47
    assert coverage["coverage_summary"]["openalex_broad_unlinked_candidate_like_hits"] == 56
    assert coverage["coverage_summary"]["openalex_query_variant_queries"] == 9
    assert coverage["coverage_summary"]["openalex_query_variant_unique_returned_records"] == 822
    assert coverage["coverage_summary"]["openalex_query_variant_screened_candidate_like_hits"] == 22
    assert coverage["coverage_summary"]["openalex_query_variant_promoted_records"] == 2
    assert coverage["coverage_summary"]["openalex_query_variant_linked_existing_records_or_sources"] == 8
    assert coverage["coverage_summary"]["openalex_query_variant_excluded_records"] == 12
    assert coverage["coverage_summary"]["pubmed_query_variant_queries"] == 8
    assert coverage["coverage_summary"]["pubmed_query_variant_unique_records"] == 70
    assert coverage["coverage_summary"]["pubmed_query_variant_supplemental_screened_records"] == 22
    assert coverage["coverage_summary"]["pubmed_query_variant_promoted_records"] == 3
    assert coverage["coverage_summary"]["pubmed_query_variant_linked_existing_records_or_sources"] == 6
    assert coverage["coverage_summary"]["pubmed_query_variant_excluded_records"] == 13
    assert coverage["coverage_summary"]["web_search_sanity_screened_records"] == 8
    assert coverage["coverage_summary"]["web_search_sanity_linked_existing_records"] == 5
    assert coverage["coverage_summary"]["web_search_sanity_updated_records"] == 1
    assert coverage["coverage_summary"]["web_search_sanity_adjacent_records"] == 1
    assert coverage["coverage_summary"]["web_search_sanity_excluded_review_records"] == 1
    assert any(
        source.get("screening_file") == "assets/preloads/audiotactile_pubmed_screening.json"
        for source in coverage["evidence_sources"]
    )
    assert any(
        source.get("consensus_screening_file")
        == "assets/preloads/audiotactile_holmes2020_consensus_screening.json"
        for source in coverage["evidence_sources"]
    )
    assert any(
        source.get("broad_screening_file") == "assets/preloads/audiotactile_openalex_broad_screening.json"
        for source in coverage["evidence_sources"]
    )
    assert any(
        source.get("candidate_screening_file")
        == "assets/preloads/audiotactile_openalex_candidate_screening.json"
        for source in coverage["evidence_sources"]
    )
    assert any(
        source.get("screening_file")
        == "assets/preloads/audiotactile_openalex_query_variant_screening.json"
        for source in coverage["evidence_sources"]
    )
    assert any(
        source.get("screening_file")
        == "assets/preloads/audiotactile_pubmed_query_variant_screening.json"
        for source in coverage["evidence_sources"]
    )
    assert any(
        source.get("screening_file")
        == "assets/preloads/audiotactile_web_sanity_screening.json"
        for source in coverage["evidence_sources"]
    )
    assert any(
        source.get("id") == "consensus_mcp_spot_check_2026_07_15"
        and source.get("kind") == "consensus_mcp_spot_check"
        and len(source.get("queries") or []) == 3
        for source in coverage["evidence_sources"]
    )

    status_ids = {profile["template_id"] for profile in status["profiles"]}
    coverage_ids = {entry["template_id"] for entry in coverage["current_template_coverage"]}
    assert coverage_ids == status_ids

    by_template = {entry["template_id"]: entry for entry in coverage["current_template_coverage"]}
    assert by_template["study5_dynaspace_lateral_45_pps"] == {
        "template_id": "study5_dynaspace_lateral_45_pps",
        "published": False,
        "current_recreation_category": "gui_recreatable",
        "primary_constraint_ids": [],
    }
    assert by_template["serino_2015_peri_hand_exp3"] == {
        "template_id": "serino_2015_peri_hand_exp3",
        "published": True,
        "current_recreation_category": "gui_recreatable",
        "primary_constraint_ids": [],
    }
    assert by_template["tonelli_2019_echolocation"] == {
        "template_id": "tonelli_2019_echolocation",
        "published": True,
        "current_recreation_category": "gui_recreatable",
        "primary_constraint_ids": [],
    }
    assert by_template["lerner_2021_3d_audio_tactile_boundary"] == {
        "template_id": "lerner_2021_3d_audio_tactile_boundary",
        "published": True,
        "current_recreation_category": "gui_recreatable",
        "primary_constraint_ids": [],
        "source_notes": (
            "GUI-recreatable with twelve published 3D source directions, dynamic moving "
            "pink-noise and flat stationary pink-noise source families, six "
            "arm-length-scaled tactile timepoints represented using a declared 70 cm "
            "reference arm length, and 144 preview trial rows; exact Unity/3D Tune-In "
            "rendering and per-subject body/head scaling remain recreation caveats."
        ),
    }

    published_ready = [
        entry
        for entry in coverage["current_template_coverage"]
        if entry["published"] and entry["current_recreation_category"] == "gui_recreatable"
    ]
    assert len(published_ready) == 14


def test_literature_coverage_constraints_focus_on_task_execution():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    constraint_ids = {item["id"] for item in coverage["constraint_taxonomy"]}
    constraint_dimensions = {
        item["id"]: item["dimension"] for item in coverage["constraint_taxonomy"]
    }
    gap_groups = coverage["standardization_gap_groups"]
    gap_group_ids = {item["id"] for item in gap_groups}

    assert "static_near_far_trial_family" in constraint_ids
    assert "direction_coupled_tactile_only_baseline" in constraint_ids
    assert "audiovisual_or_trisensory_trial_family" in constraint_ids
    assert "cross_modal_extinction_response_mapping" in constraint_ids
    assert "multi_speaker_array_switching" in constraint_ids
    assert "two_speaker_intensity_crossfade_gain_law" not in constraint_ids
    assert "body_scaled_distance_units" in constraint_ids
    assert "voice_key_response_capture" in constraint_ids
    assert "external_event_trigger_sync_contract" in constraint_ids
    assert "tactile_waveform_frequency_profile" in constraint_ids
    assert "missing_core_soa_iti_baseline_repetition_parameters" in constraint_ids
    assert "exact_trial_timing_randomization_tables" not in constraint_ids
    multi_speaker_constraint = next(
        item for item in coverage["constraint_taxonomy"] if item["id"] == "multi_speaker_array_switching"
    )
    assert multi_speaker_constraint["toolkit_status"] == "partially_modeled"
    assert multi_speaker_constraint["example_records"] == ["serino_2015_exps_4_to_6"]
    assert {
        "trial_design_families",
        "audio_source_and_renderer",
        "spatial_coordinate_system",
        "tactile_and_response_mapping",
        "timing_and_repetition",
        "physiology_or_external_trigger_contract",
    } <= gap_group_ids
    for group in gap_groups:
        assert group["question"]
        assert set(group["example_constraint_ids"]) <= constraint_ids, group["id"]

    non_blocking_tokens = {
        "clinical_population",
        "intervention",
        "prosthesis_group",
        "social_context",
        "wheelchair_context",
        "walking_context",
        "walking_treadmill_wheelchair_or_vr_context",
        "prosthesis_or_patient_group",
        "tool_use_training_context",
        "social_or_manipulation_context",
        "emotional_or_self_relevance_condition",
        "non_audiotactile_extra_stimulus",
    }
    task_execution_dimensions = set(coverage["blocker_definition"]["blocking_dimensions"])
    assert task_execution_dimensions == {
        "trial_family_and_baseline_logic",
        "auditory_stimulus_type_asset_provenance_rendering_or_gain_law",
        "spatial_trajectory_coordinate_frame_or_apparatus_geometry",
        "tactile_site_channel_modality_duration_or_calibration",
        "response_capture_or_response_mapping",
        "timing_iti_soa_baseline_repetition",
    }
    assert set(coverage["blocker_definition"]["non_blocking_contexts"]) <= non_blocking_tokens
    assert coverage["blocker_definition"]["acceptance_gate_required_parameters"] == [
        "auditory stimulus type and source asset provenance",
        "tactile stimulus type, site, channel, duration, and calibration when task-relevant",
        "ITI or jitter policy when task-relevant",
        "SOA or distance-at-tactile table",
        "baseline strategy and baseline timing",
        "trial repetition count",
    ]
    assert not any(
        "randomization" in value.lower() or "block order" in value.lower()
        for value in coverage["blocker_definition"]["acceptance_gate_required_parameters"]
    )

    for entry in coverage["current_template_coverage"]:
        assert not (set(entry["primary_constraint_ids"]) & non_blocking_tokens)

    records = {record["record_id"]: record for record in coverage["literature_records"]}
    assert records["spiousas_2025_auditory_only"]["coverage_category"] == "adjacent_out_of_scope"
    assert records["ladavas_2001_auditory_tactile_extinction"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "cross_modal_extinction_response_mapping" in records["ladavas_2001_auditory_tactile_extinction"]["blocking_constraint_ids"]
    assert records["farne_ladavas_2002_auditory_pps_humans"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "cross_modal_extinction_response_mapping" in records["farne_ladavas_2002_auditory_pps_humans"]["blocking_constraint_ids"]
    assert records["rossi_sebastiano_2022_visuotactile"]["coverage_category"] == "adjacent_out_of_scope"
    assert records["teraoka_2024_front_rear"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["holmes_2020_four_experiments"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["tajadura_jimenez_2009_visual_deprivation"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["mindfulness_pps_2024"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["newborn_boundaries_2019"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["ronga_2021_newborn_erp"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["ferri_2015_jneurosci_itv"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["autism_2019"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["social_coding_2019"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["social_perception_2017"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["ferroni_2020_tool_observation"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["ageing_2021"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["seeming_confines_2021"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["jazz_duet_2021"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["schizophrenia_tool_use_2022"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["novel_two_phase_audio_tactile_2025"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["depersonalisation_2024"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["lower_limb_pps_2017"]["coverage_category"] == "adjacent_out_of_scope"
    assert records["lower_limb_pps_2017"]["blocking_constraint_ids"] == []
    assert records["cell_reports_medicine_2026_consciousness"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "static_near_far_trial_family" in records["cell_reports_medicine_2026_consciousness"]["blocking_constraint_ids"]
    assert records["serino_2018_mixed_reality_pps"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "audiovisual_or_trisensory_trial_family" in records["serino_2018_mixed_reality_pps"]["blocking_constraint_ids"]
    assert records["amemiya_2017_pseudowalking_footsole"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["serino_2011_professional_fencers"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["interoception_exteroception_2025"]["doi"] == "10.1073/pnas.2516229122"
    assert records["interoception_exteroception_2025"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["amiel_2025_front_rear"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["body_image_social_cognition_2024"]["coverage_category"] == "not_yet_templated_missing_publication_parameters"
    assert records["taffou_2021_auditory_roughness"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "rear_hemifield_trajectory_families" in records["taffou_2021_auditory_roughness"]["blocking_constraint_ids"]
    assert records["looming_duration_2025"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "tactile_waveform_frequency_profile" in records["looming_duration_2025"]["blocking_constraint_ids"]
    assert records["lamia_2026_arm_movement"]["can_recreate_audiotactile_components_now"] is True
    assert records["serino_2015_peri_trunk_exp1"]["coverage_category"] == "covered_runnable_profile"
    assert records["serino_2015_peri_trunk_exp1"]["can_recreate_audiotactile_components_now"] is True
    assert records["serino_2015_peri_trunk_exp1"]["blocking_constraint_ids"] == []
    assert records["smartphone_rt_methods_2025"]["coverage_category"] == "covered_runnable_profile"
    assert records["smartphone_rt_methods_2025"]["current_template_ids"] == [
        "roussel_2025_dynaspace_mobile_pps"
    ]
    assert records["smartphone_rt_methods_2025"]["can_recreate_audiotactile_components_now"] is True
    assert records["smartphone_rt_methods_2025"]["blocking_constraint_ids"] == []
    assert records["serino_2015_peri_hand_exp3"]["coverage_category"] == "covered_runnable_profile"
    assert records["serino_2015_peri_hand_exp3"]["can_recreate_audiotactile_components_now"] is True
    assert records["serino_2015_peri_hand_exp3"]["blocking_constraint_ids"] == []
    assert records["canzoneri_2012_dynamic_sounds"]["coverage_category"] == "covered_runnable_profile"
    assert records["canzoneri_2012_dynamic_sounds"]["can_recreate_audiotactile_components_now"] is True
    assert records["canzoneri_2012_dynamic_sounds"]["blocking_constraint_ids"] == []
    assert records["canzoneri_2012_dynamic_sounds"]["missing_publication_parameters"] == []
    assert records["tonelli_2019_echolocation"]["coverage_category"] == "covered_runnable_profile"
    assert records["tonelli_2019_echolocation"]["can_recreate_audiotactile_components_now"] is True
    assert records["tonelli_2019_echolocation"]["blocking_constraint_ids"] == []
    assert records["tonelli_2019_echolocation"]["missing_publication_parameters"] == []
    assert records["tonelli_2019_echolocation"]["recreation_caveats"]
    assert records["serino_2015_front_back_trunk_exp2"]["coverage_category"] == "covered_runnable_profile"
    assert records["serino_2015_front_back_trunk_exp2"]["can_recreate_audiotactile_components_now"] is True
    assert records["serino_2015_front_back_trunk_exp2"]["blocking_constraint_ids"] == []
    assert records["serino_2015_front_back_trunk_exp2"]["missing_publication_parameters"] == []
    assert records["serino_2015_front_back_trunk_exp2"]["recreation_caveats"]
    assert records["galli_2015_wheelchair"]["coverage_category"] == "covered_runnable_profile"
    assert records["galli_2015_wheelchair"]["can_recreate_audiotactile_components_now"] is True
    assert records["galli_2015_wheelchair"]["blocking_constraint_ids"] == []
    assert records["galli_2015_wheelchair"]["missing_publication_parameters"] == []
    assert records["lerner_2021_3d_boundary"]["coverage_category"] == "covered_runnable_profile"
    assert records["lerner_2021_3d_boundary"]["can_recreate_audiotactile_components_now"] is True
    assert records["lerner_2021_3d_boundary"]["blocking_constraint_ids"] == []
    assert records["lerner_2021_3d_boundary"]["missing_publication_parameters"] == []
    assert records["lerner_2021_3d_boundary"]["recreation_caveats"]
    assert records["teramoto_2013_beyond_head_audiotactile"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "body_part_anchored_coordinate_frames" in records["teramoto_2013_beyond_head_audiotactile"]["blocking_constraint_ids"]
    assert "tactile_discrimination_or_localization_response" in records["teramoto_2013_beyond_head_audiotactile"]["blocking_constraint_ids"]
    assert records["finisguerra_2015_moving_sounds_motor"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "voice_key_response_capture" in records["finisguerra_2015_moving_sounds_motor"]["blocking_constraint_ids"]
    assert records["biggio_2017_racket_tool_use"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "static_near_far_trial_family" in records["biggio_2017_racket_tool_use"]["blocking_constraint_ids"]
    assert records["bassolino_2010_mouse_use"]["doi"] == "10.1016/j.neuropsychologia.2009.11.009"
    assert records["teneggi_2013_social_face"]["doi"] == "10.1016/j.cub.2013.01.043"
    assert records["serino_2009_tms"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert "external_event_trigger_sync_contract" in records["serino_2009_tms"]["blocking_constraint_ids"]
    assert records["avenanti_2012_motor_cortex"]["coverage_category"] == "not_yet_templated_requires_toolkit_structure"
    assert records["avenanti_2012_motor_cortex"]["blocking_constraint_ids"] == ["external_event_trigger_sync_contract"]
    assert records["barumerli_2026_semantic_looming_auditory_only"]["coverage_category"] == "adjacent_out_of_scope"
    assert records["barumerli_2026_semantic_looming_auditory_only"]["doi"] == "10.1038/s41598-026-48067-4"

    for record in coverage["literature_records"]:
        assert set(record["blocking_constraint_ids"]) <= constraint_ids, record["record_id"]
        assert not (set(record["blocking_constraint_ids"]) & non_blocking_tokens), record["record_id"]
        for constraint_id in record["blocking_constraint_ids"]:
            assert constraint_dimensions[constraint_id] in task_execution_dimensions, record["record_id"]


def test_literature_coverage_record_schema_and_verdict_semantics():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    required_record_fields = {
        "record_id",
        "citation_short",
        "doi",
        "source_basis",
        "current_template_ids",
        "coverage_category",
        "audiotactile_task_family",
        "can_recreate_audiotactile_components_now",
        "blocking_constraint_ids",
        "missing_publication_parameters",
    }

    for record in coverage["literature_records"]:
        assert required_record_fields <= set(record), record["record_id"]
        assert record["record_id"]
        assert record["citation_short"]
        assert record["source_basis"], record["record_id"]
        assert isinstance(record["current_template_ids"], list), record["record_id"]
        assert record["audiotactile_task_family"], record["record_id"]
        assert isinstance(record["can_recreate_audiotactile_components_now"], bool), record["record_id"]
        assert isinstance(record["blocking_constraint_ids"], list), record["record_id"]
        assert isinstance(record["missing_publication_parameters"], list), record["record_id"]

        category = record["coverage_category"]
        if category == "covered_runnable_profile":
            assert record["can_recreate_audiotactile_components_now"] is True, record["record_id"]
            assert record["current_template_ids"], record["record_id"]
            assert not record["blocking_constraint_ids"], record["record_id"]
            assert not record["missing_publication_parameters"], record["record_id"]
        elif category in {
            "covered_blocked_missing_publication_parameters",
            "not_yet_templated_missing_publication_parameters",
        }:
            assert record["can_recreate_audiotactile_components_now"] is False, record["record_id"]
            assert record["missing_publication_parameters"], record["record_id"]
        elif category in {
            "covered_blocked_toolkit_structure",
            "not_yet_templated_requires_toolkit_structure",
        }:
            assert record["can_recreate_audiotactile_components_now"] is False, record["record_id"]
            assert record["blocking_constraint_ids"], record["record_id"]
        elif category == "adjacent_out_of_scope":
            assert record["can_recreate_audiotactile_components_now"] is False, record["record_id"]
            assert not record["current_template_ids"], record["record_id"]


def test_literature_coverage_has_no_uncategorized_records():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    allowed_categories = {
        "covered_runnable_profile",
        "covered_blocked_missing_publication_parameters",
        "covered_blocked_toolkit_structure",
        "not_yet_templated_requires_toolkit_structure",
        "not_yet_templated_missing_publication_parameters",
        "candidate_needs_full_text_task_audit",
        "adjacent_out_of_scope",
    }
    record_ids = [record["record_id"] for record in coverage["literature_records"]]

    assert len(record_ids) == len(set(record_ids))
    assert {record["coverage_category"] for record in coverage["literature_records"]} <= allowed_categories
    assert not [
        record for record in coverage["literature_records"]
        if record["coverage_category"] == "candidate_needs_full_text_task_audit"
    ]


def test_pubmed_screening_trail_covers_every_record_and_links_inclusions():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    screening = json.loads(SCREENING_PATH.read_text(encoding="utf-8"))
    literature_record_ids = {record["record_id"] for record in coverage["literature_records"]}
    allowed_decisions = {
        "excluded_adjacent_non_pps_audiotactile_task",
        "excluded_commentary_no_new_task",
        "excluded_duplicate_correction",
        "excluded_methods_reference_no_distinct_pps_task",
        "excluded_non_audiotactile_pps_task",
        "excluded_review_or_theory_no_pps_task",
        "included_candidate_requires_static_near_far_support",
        "included_candidate_requires_toolkit_structure",
        "included_candidate_task_needs_full_text_audit",
        "included_current_blocked_profile",
        "included_current_runnable_profile",
    }
    records = list(screening["records"])

    assert screening["schema"] == "pps-audiotactile-pubmed-screening.v1"
    assert screening["screened_count"] == len(records) == 48
    assert len({record["pmid"] for record in records}) == 48
    assert {record["decision"] for record in records} <= allowed_decisions

    for record in records:
        links = set(record["linked_literature_record_ids"])
        assert links <= literature_record_ids, record["pmid"]
        if record["decision"].startswith("included_"):
            assert links, record["pmid"]

    by_pmid = {record["pmid"]: record for record in records}
    assert by_pmid["41329741"]["doi"] == "10.1073/pnas.2516229122"

    excluded = [record for record in records if record["decision"].startswith("excluded_")]
    included = [record for record in records if record["decision"].startswith("included_")]
    assert len(excluded) == 8
    assert len(included) == 40


def test_pubmed_abstract_cache_uses_screened_doi_values():
    if not PUBMED_ABSTRACTS_PATH.exists():
        pytest.skip("Ignored PubMed abstract cache is not present in this checkout.")
    abstracts = json.loads(PUBMED_ABSTRACTS_PATH.read_text(encoding="utf-8"))
    screening = json.loads(SCREENING_PATH.read_text(encoding="utf-8"))
    screened_by_pmid = {record["pmid"]: record for record in screening["records"]}

    for record in abstracts:
        screened = screened_by_pmid.get(record["pmid"])
        if screened:
            assert record["doi"] == screened["doi"], record["pmid"]


def test_holmes_consensus_screening_links_relevant_experiment_families():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    holmes = json.loads(HOLMES_PATH.read_text(encoding="utf-8"))
    literature_record_ids = {record["record_id"] for record in coverage["literature_records"]}
    allowed_decisions = {
        "consensus_candidate_needs_full_text_audit",
        "consensus_candidate_requires_toolkit_structure",
        "consensus_current_blocked_profile",
        "consensus_current_runnable_profile",
        "consensus_excluded_reference_or_parser_artifact",
        "consensus_neurophysiology_context",
        "consensus_partly_templated_requires_toolkit_structure",
    }
    records = list(holmes["records"])

    assert holmes["schema"] == "pps-audiotactile-holmes2020-consensus-screening.v1"
    assert holmes["source"]["reported_article_count"] == 23
    assert holmes["source"]["reported_relevant_experiment_count"] == 46
    assert holmes["source"]["parsed_past_sheet_experiment_rows"] == 49
    assert holmes["source"]["screened_experiment_family_records"] == len(records) == 27
    assert holmes["source"]["excluded_parser_or_reference_artifact_rows"] == 3
    assert {record["decision"] for record in records} <= allowed_decisions

    for record in records:
        links = set(record["linked_literature_record_ids"])
        assert links <= literature_record_ids, record["source_label"]
        if record["decision"] != "consensus_excluded_reference_or_parser_artifact":
            assert links, record["source_label"]

    current_template_ids = {
        entry["template_id"] for entry in coverage["current_template_coverage"]
    }
    for record in records:
        template_links = set(record.get("current_template_ids", []))
        assert template_links <= current_template_ids, record["source_label"]


def test_openalex_broad_screening_records_retrieval_scope_and_promoted_candidates():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    openalex = json.loads(OPENALEX_PATH.read_text(encoding="utf-8"))
    literature_record_ids = {record["record_id"] for record in coverage["literature_records"]}
    promoted_ids = {
        record["record_id"] for record in openalex["new_or_promoted_candidate_records"]
    }

    assert openalex["schema"] == "pps-audiotactile-openalex-broad-screening.v1"
    assert openalex["retrieved_count"] == 755
    assert openalex["automated_candidate_like_count"] == 103
    assert openalex["linked_candidate_like_count"] == 47
    assert openalex["unlinked_candidate_like_count"] == 56
    assert (
        openalex["candidate_screening_file"]
        == "assets/preloads/audiotactile_openalex_candidate_screening.json"
    )
    assert promoted_ids <= literature_record_ids
    assert {
        "social_perception_2017",
        "lower_limb_pps_2017",
        "newborn_boundaries_2019",
        "ronga_2021_newborn_erp",
        "serino_2018_mixed_reality_pps",
        "amemiya_2017_pseudowalking_footsole",
        "serino_2011_professional_fencers",
        "ferri_2015_jneurosci_itv",
        "interoception_exteroception_2025",
        "taffou_2021_auditory_roughness",
        "novel_two_phase_audio_tactile_2025",
        "looming_duration_2025",
    } <= promoted_ids
    lower_limb = next(
        record for record in openalex["new_or_promoted_candidate_records"]
        if record["record_id"] == "lower_limb_pps_2017"
    )
    assert "false positive" in lower_limb["reason"]


def test_openalex_candidate_screening_has_no_unresolved_candidate_like_hits():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    openalex = json.loads(OPENALEX_PATH.read_text(encoding="utf-8"))
    screening = json.loads(OPENALEX_CANDIDATE_SCREENING_PATH.read_text(encoding="utf-8"))
    literature_record_ids = {record["record_id"] for record in coverage["literature_records"]}
    allowed_decisions = {
        "linked_to_coverage_ledger",
        "promoted_to_coverage_ledger",
        "duplicate_or_supporting_source_linked_to_coverage_record",
        "excluded_visual_tactile_or_non_auditory_pps",
        "excluded_non_pps_audiotactile_or_haptic",
        "excluded_review_theory_or_model",
        "excluded_auditory_only_no_tactile_pps",
        "grey_literature_or_source_not_counted",
        "grey_literature_relevant_audio_tactile_task_not_counted",
    }
    records = screening["records"]

    assert screening["schema"] == "pps-audiotactile-openalex-candidate-screening.v1"
    assert screening["candidate_like_count"] == len(records) == openalex["automated_candidate_like_count"] == 103
    assert screening["linked_or_promoted_count"] == openalex["linked_candidate_like_count"] == 47
    assert screening["unlinked_excluded_or_grey_count"] == openalex["unlinked_candidate_like_count"] == 56
    assert {record["screening_decision"] for record in records} <= allowed_decisions
    assert not [
        record for record in records
        if record["screening_decision"] == "excluded_unresolved_by_rule"
    ]

    linked_rows = [record for record in records if record["linked_literature_record_ids"]]
    assert len(linked_rows) == 47
    for record in linked_rows:
        assert set(record["linked_literature_record_ids"]) <= literature_record_ids, record["rank"]

    by_rank = {record["rank"]: record for record in records}
    assert by_rank[19]["linked_literature_record_ids"] == ["serino_2018_mixed_reality_pps"]
    assert by_rank[84]["linked_literature_record_ids"] == ["amemiya_2017_pseudowalking_footsole"]
    assert by_rank[298]["linked_literature_record_ids"] == ["serino_2011_professional_fencers"]


def test_openalex_query_variant_screening_promotes_early_auditory_tactile_extinction_records():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    screening = json.loads(OPENALEX_QUERY_VARIANT_SCREENING_PATH.read_text(encoding="utf-8"))
    literature_record_ids = {record["record_id"] for record in coverage["literature_records"]}
    allowed_decisions = {
        "linked_to_coverage_ledger",
        "promoted_to_coverage_ledger",
        "duplicate_or_supporting_source_linked_to_coverage_record",
        "excluded_review_visual_tactile_or_non_auditory_pps",
        "excluded_query_reference_hit_no_audiotactile_task_evidence",
        "excluded_visual_or_vr_feedback_no_audiotactile_task",
        "excluded_review_theory_or_model",
        "excluded_nonhuman_or_non_runner_target",
        "excluded_visual_tactile_or_non_auditory_pps",
    }

    assert screening["schema"] == "pps-audiotactile-openalex-query-variant-screening.v1"
    assert screening["query_count"] == coverage["coverage_summary"]["openalex_query_variant_queries"] == 9
    assert (
        screening["unique_returned_record_count"]
        == coverage["coverage_summary"]["openalex_query_variant_unique_returned_records"]
        == 822
    )
    assert (
        screening["candidate_like_screened_count"]
        == coverage["coverage_summary"]["openalex_query_variant_screened_candidate_like_hits"]
        == len(screening["records"])
        == 22
    )
    assert screening["promoted_to_coverage_count"] == coverage["coverage_summary"]["openalex_query_variant_promoted_records"] == 2
    assert screening["linked_or_duplicate_count"] == coverage["coverage_summary"]["openalex_query_variant_linked_existing_records_or_sources"] == 8
    assert screening["excluded_count"] == coverage["coverage_summary"]["openalex_query_variant_excluded_records"] == 12
    assert {record["screening_decision"] for record in screening["records"]} <= allowed_decisions

    for record in screening["records"]:
        assert set(record["linked_literature_record_ids"]) <= literature_record_ids, record["openalex_id"]

    promoted_links = {
        link
        for record in screening["records"]
        if record["screening_decision"] == "promoted_to_coverage_ledger"
        for link in record["linked_literature_record_ids"]
    }
    assert promoted_links == {
        "ladavas_2001_auditory_tactile_extinction",
        "farne_ladavas_2002_auditory_pps_humans",
    }


def test_pubmed_query_variant_screening_promotes_supplemental_task_records():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    screening = json.loads(PUBMED_QUERY_VARIANT_SCREENING_PATH.read_text(encoding="utf-8"))
    literature_record_ids = {record["record_id"] for record in coverage["literature_records"]}
    allowed_decisions = {
        "linked_to_coverage_ledger",
        "promoted_to_coverage_ledger",
        "excluded_non_pps_conditioning_or_drug_context",
        "excluded_review_visual_tactile_or_non_auditory_pps",
        "excluded_review_theory_or_model",
        "excluded_non_pps_audiotactile_or_haptic",
        "excluded_adjacent_warning_signal_application",
        "excluded_clinical_extinction_methods_no_distinct_pps_task",
        "excluded_auditory_only_or_reaching_feedback",
        "excluded_auditory_only_no_tactile_pps",
        "excluded_model_theory_or_non_pps_engineering",
    }

    assert screening["schema"] == "pps-audiotactile-pubmed-query-variant-screening.v1"
    assert screening["query_count"] == coverage["coverage_summary"]["pubmed_query_variant_queries"] == 8
    assert (
        screening["unique_record_count"]
        == coverage["coverage_summary"]["pubmed_query_variant_unique_records"]
        == 70
    )
    assert (
        screening["supplemental_screened_count"]
        == coverage["coverage_summary"]["pubmed_query_variant_supplemental_screened_records"]
        == len(screening["records"])
        == 22
    )
    assert screening["promoted_to_coverage_count"] == coverage["coverage_summary"]["pubmed_query_variant_promoted_records"] == 3
    assert screening["linked_existing_count"] == coverage["coverage_summary"]["pubmed_query_variant_linked_existing_records_or_sources"] == 6
    assert screening["excluded_count"] == coverage["coverage_summary"]["pubmed_query_variant_excluded_records"] == 13
    assert {record["screening_decision"] for record in screening["records"]} <= allowed_decisions

    for record in screening["records"]:
        assert set(record["linked_literature_record_ids"]) <= literature_record_ids, record["pmid"]

    promoted_links = {
        link
        for record in screening["records"]
        if record["screening_decision"] == "promoted_to_coverage_ledger"
        for link in record["linked_literature_record_ids"]
    }
    assert promoted_links == {
        "teramoto_2013_beyond_head_audiotactile",
        "finisguerra_2015_moving_sounds_motor",
        "biggio_2017_racket_tool_use",
    }


def test_web_sanity_screening_records_live_search_disambiguations():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    screening = json.loads(WEB_SANITY_SCREENING_PATH.read_text(encoding="utf-8"))
    literature_record_ids = {record["record_id"] for record in coverage["literature_records"]}
    allowed_decisions = {
        "linked_to_coverage_ledger",
        "updated_coverage_ledger_parameters",
        "excluded_adjacent_auditory_only_pps",
        "excluded_review_no_distinct_task_profile",
    }

    assert screening["schema"] == "pps-audiotactile-web-sanity-screening.v1"
    assert screening["screened_count"] == coverage["coverage_summary"]["web_search_sanity_screened_records"] == 8
    assert screening["linked_existing_count"] == coverage["coverage_summary"]["web_search_sanity_linked_existing_records"] == 5
    assert screening["updated_coverage_count"] == coverage["coverage_summary"]["web_search_sanity_updated_records"] == 1
    assert screening["adjacent_out_of_scope_count"] == coverage["coverage_summary"]["web_search_sanity_adjacent_records"] == 1
    assert screening["excluded_review_count"] == coverage["coverage_summary"]["web_search_sanity_excluded_review_records"] == 1
    assert {record["screening_decision"] for record in screening["records"]} <= allowed_decisions

    for record in screening["records"]:
        assert set(record["linked_literature_record_ids"]) <= literature_record_ids, record["title"]

    by_decision = {record["screening_decision"]: record for record in screening["records"]}
    assert by_decision["updated_coverage_ledger_parameters"]["linked_literature_record_ids"] == [
        "looming_duration_2025"
    ]
    assert by_decision["excluded_adjacent_auditory_only_pps"]["linked_literature_record_ids"] == [
        "barumerli_2026_semantic_looming_auditory_only"
    ]
    linked_ids = {
        link
        for record in screening["records"]
        if record["screening_decision"] == "linked_to_coverage_ledger"
        for link in record["linked_literature_record_ids"]
    }
    assert {
        "ieeg_trunk_2018",
        "cell_reports_medicine_2026_consciousness",
        "teraoka_2024_front_rear",
        "tonelli_2019_echolocation",
        "pfeiffer_2018_vestibular",
    } <= linked_ids

