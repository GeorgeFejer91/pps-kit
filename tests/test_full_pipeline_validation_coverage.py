from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINE_PATH = ROOT / "assets" / "preloads" / "audiotactile_full_pipeline_validation.json"
BUILDER_PATH = ROOT / "tools" / "build_full_pipeline_validation_coverage.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_full_pipeline_validation_coverage", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_full_pipeline_validation_ledger_matches_builder():
    builder = _load_builder()
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))

    assert pipeline == builder.build_full_pipeline_validation()
    assert pipeline["schema"] == builder.SCHEMA
    assert pipeline["pipeline_definition"]["start"] == "original paper/PDF/source parameter extraction"
    assert pipeline["pipeline_definition"]["end"] == (
        "observed mouse-click emulated PPS runner behavior compared with extracted expected outcome"
    )
    assert [gate["id"] for gate in pipeline["pipeline_definition"]["gates"]] == [
        "source_parameter_extraction",
        "expected_outcome_extraction",
        "parsimonious_profile_saved",
        "toolkit_gui_implementation",
        "wav_generation_and_runner_execution",
        "observed_emulated_expected_match",
    ]


def test_full_pipeline_validation_summary_is_conservative():
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    summary = pipeline["summary"]

    assert summary["literature_record_count"] == 74
    assert summary["in_scope_record_count"] == 70
    assert summary["adjacent_not_applicable_record_count"] == 4
    assert summary["full_emulated_pipeline_validated_record_count"] == 12
    assert summary["human_behavioral_observed_record_count"] == 0
    assert summary["physical_loopback_observed_record_count"] == 0
    assert summary["pipeline_status_counts"] == {
        "adjacent_not_applicable": 4,
        "full_emulated_source_to_runner_pipeline_validated": 12,
        "profile_present_but_source_parameters_missing": 8,
        "source_parameters_missing_before_profile_creation": 28,
        "toolkit_structure_or_response_contract_missing": 22,
    }
    assert summary["primary_gap_counts"] == {
        "profile_present_but_source_parameters_missing": 8,
        "source_parameters_missing_before_profile_creation": 28,
        "toolkit_structure_or_response_contract_missing": 22,
    }
    assert summary["gate_status_counts"]["source_parameter_extraction"] == {
        "minimum_source_parameters_captured": 12,
        "not_applicable_adjacent_record": 4,
        "source_parameters_missing_or_unresolved": 58,
    }
    assert summary["gate_status_counts"]["observed_emulated_expected_match"] == {
        "emulated_observed_direction_matches_expected": 12,
        "no_observed_emulated_comparison": 58,
        "not_applicable_adjacent_record": 4,
    }
    assert summary["gate_status_counts"]["toolkit_gui_implementation"] == {
        "blocked_by_missing_profile_parameters": 36,
        "blocked_by_toolkit_structure_or_response_contract": 22,
        "not_applicable_adjacent_record": 4,
        "segment_0_to_6_gui_toolkit_path_ready": 12,
    }
    assert "not collected participant evidence" in pipeline["scope"]["evidence_boundary"]


def test_full_pipeline_validated_records_pass_every_required_gate():
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    records = {record["record_id"]: record for record in pipeline["records"]}
    full_records = [
        record for record in records.values() if record["full_emulated_pipeline_validated"]
    ]

    assert len(full_records) == pipeline["summary"]["full_emulated_pipeline_validated_record_count"] == 12
    for record in full_records:
        assert record["pipeline_status"] == "full_emulated_source_to_runner_pipeline_validated"
        assert all(gate["passed"] for gate in record["gates"].values()), record["record_id"]
        assert record["gates"]["source_parameter_extraction"]["status"] == "minimum_source_parameters_captured"
        assert record["gates"]["parsimonious_profile_saved"]["status"] == "parsimonious_profile_complete"
        assert record["gates"]["toolkit_gui_implementation"]["status"] == "segment_0_to_6_gui_toolkit_path_ready"
        assert record["gates"]["wav_generation_and_runner_execution"]["status"] == (
            "wav_runner_mouse_click_emulation_available"
        )
        assert record["gates"]["observed_emulated_expected_match"]["status"] == (
            "emulated_observed_direction_matches_expected"
        )
        assert record["gates"]["observed_emulated_expected_match"]["source_report"].endswith(
            "ready_profile_mouse_click_expected_outcome_audit_report.json"
        )

    canzoneri = records["canzoneri_2012_dynamic_sounds"]
    assert canzoneri["full_emulated_pipeline_validated"]
    assert canzoneri["current_template_ids"] == ["canzoneri_2012_dynamic_sounds"]


def test_full_pipeline_blocks_at_the_first_unproven_layer():
    pipeline = json.loads(PIPELINE_PATH.read_text(encoding="utf-8"))
    records = {record["record_id"]: record for record in pipeline["records"]}

    taffou = records["taffou_2014_cynophobic_rear_looming"]
    assert taffou["pipeline_status"] == "profile_present_but_source_parameters_missing"
    assert not taffou["gates"]["source_parameter_extraction"]["passed"]
    assert taffou["gates"]["parsimonious_profile_saved"]["status"] == (
        "profile_scaffold_present_but_incomplete"
    )
    assert "exact dog/sheep source audio" in taffou["next_required_action"]

    newborn = records["newborn_boundaries_2019"]
    assert newborn["pipeline_status"] == "source_parameters_missing_before_profile_creation"
    assert newborn["gates"]["source_parameter_extraction"]["status"] == (
        "source_parameters_missing_or_unresolved"
    )
    assert newborn["gates"]["parsimonious_profile_saved"]["status"] == "profile_not_yet_created"
    assert newborn["blocking_constraint_ids"] == ["missing_core_soa_iti_baseline_repetition_parameters"]

    kitagawa = records["kitagawa_2005_sound_complexity"]
    assert kitagawa["pipeline_status"] == "toolkit_structure_or_response_contract_missing"
    assert kitagawa["gates"]["toolkit_gui_implementation"]["status"] == (
        "blocked_by_toolkit_structure_or_response_contract"
    )
    assert kitagawa["blocking_constraint_ids"] == ["tactile_discrimination_or_localization_response"]

    spiousas = records["spiousas_2025_auditory_only"]
    assert spiousas["pipeline_status"] == "adjacent_not_applicable"
    assert not spiousas["full_emulated_pipeline_validated"]
    assert all(gate["status"] == "not_applicable_adjacent_record" for gate in spiousas["gates"].values())
