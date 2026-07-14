#!/usr/bin/env python
"""Build the audiotactile expected-outcome coverage ledger.

This ledger is deliberately conservative. It records which literature records
have a structured expected behavioral/scientific outcome extracted, and whether
the current toolkit has any observed evidence that can be compared with that
outcome. Software mock runs can validate schedules, WAV generation, markers, and
analysis plumbing; they do not validate human PPS effects.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
OUTPUT_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"

SCHEMA = "pps-audiotactile-expected-outcome-coverage.v1"


EXPECTED_OUTCOMES: dict[str, dict[str, Any]] = {
    "noel_2015_bodily_self": {
        "outcome_family": "body-location-dependent_pps_boundary_shift",
        "primary_expected_effect": (
            "Synchronous full-body-illusion stroking shifts PPS toward the virtual body: "
            "front-space PPS expands toward the avatar and back-space PPS shrinks relative "
            "to asynchronous stroking."
        ),
        "expected_effect_direction": "synchronous_front_expansion_and_back_reduction",
        "observable_metric": "tactile RT facilitation as a function of looming-sound distance/SOA",
        "condition_contrast": "synchronous versus asynchronous visuo-tactile stroking, front versus back space",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/noel_2015_bodily_self.json",
            "Consensus MCP 2026-07-15 query: audiotactile peripersonal space auditory tactile integration boundary looming",
        ],
    },
    "serino_2015_peri_trunk_exp1": {
        "outcome_family": "distance_dependent_audio_tactile_facilitation",
        "primary_expected_effect": (
            "Task-irrelevant moving sounds closer to the trunk facilitate tactile responses "
            "more than far sounds, yielding an estimated peri-trunk PPS boundary from the "
            "RT-by-distance function."
        ),
        "expected_effect_direction": "near_or_approaching_trunk_sounds_speed_tactile_rt",
        "observable_metric": "baseline-corrected tactile RT/facilitation across D1-D6 distances",
        "condition_contrast": "near versus far trunk-centered auditory distances and looming/receding motion",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_peri_trunk_exp1.json",
            "assets/preloads/audiotactile_holmes2020_consensus_screening.json",
        ],
    },
    "pfeiffer_2018_vestibular": {
        "outcome_family": "vestibular_modulation_of_perihead_pps",
        "primary_expected_effect": (
            "Vestibular stimulation speeds tactile detection, and congruent audio-vestibular "
            "motion expands peri-head PPS farther from the body relative to no rotation or "
            "incongruent motion."
        ),
        "expected_effect_direction": "congruent_audio_vestibular_motion_expands_pps",
        "observable_metric": "maximal auditory distance/SOA at which tactile RT facilitation is present",
        "condition_contrast": "congruent versus incongruent vestibular/auditory motion and no-rotation baselines",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#pfeiffer_2018_vestibular",
            "Consensus MCP 2026-07-15 query: audiotactile peripersonal space auditory tactile integration boundary looming",
        ],
    },
    "matsuda_2021_four_directions": {
        "outcome_family": "directional_peritrunk_pps_for_approaching_sounds",
        "primary_expected_effect": (
            "Peri-trunk PPS representations are observed for approaching sounds in front, "
            "rear, left, and right directions; receding sounds are not expected to produce "
            "the same direction-general PPS facilitation pattern."
        ),
        "expected_effect_direction": "approaching_sounds_show_pps_facilitation_across_four_directions",
        "observable_metric": "tactile RT/facilitation by T1-T5 SOA and body-relative direction",
        "condition_contrast": "approaching versus receding sounds across front/rear/left/right blocks",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/matsuda_2021_four_directions.json",
            "Consensus MCP 2026-07-15 query: audio tactile peripersonal space looming sound tactile reaction time",
        ],
    },
    "lamia_2026_arm_movement": {
        "outcome_family": "arm_movement_reduction_of_audio_tactile_facilitation",
        "primary_expected_effect": (
            "Looming sounds enhance tactile reactivity near the hand and trunk when still, "
            "but arm movement execution reduces or eliminates the distance-dependent "
            "audio-tactile facilitation irrespective of the stimulated body part."
        ),
        "expected_effect_direction": "movement_blunts_looming_distance_facilitation",
        "observable_metric": "baseline-corrected tactile RT/facilitation across tactile delays and movement state",
        "condition_contrast": "motor versus static blocks, hand versus trunk tactile site, looming versus receding sounds",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/lamia_2026_arm_movement.json",
            "Consensus MCP 2026-07-15 query: audio tactile peripersonal space looming sound tactile reaction time",
        ],
    },
    "smartphone_rt_methods_2025": {
        "outcome_family": "mobile_looming_versus_static_tactile_rt_facilitation",
        "primary_expected_effect": (
            "On validated Android devices, looming sounds reduce tactile RTs by about "
            "20-25 ms compared with static sounds in the smartphone PPS task."
        ),
        "expected_effect_direction": "looming_faster_than_static",
        "observable_metric": "tactile RT difference between looming and fixed/static auditory conditions",
        "condition_contrast": "looming headphone sound versus fixed/static comparator sound",
        "source_basis": [
            "assets/preloads/audiotactile_literature_coverage.json#smartphone_rt_methods_2025",
            "Consensus MCP 2026-07-15 query: audio tactile peripersonal space looming sound tactile reaction time",
        ],
    },
}


def main() -> int:
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    ledger = build_expected_outcome_coverage(coverage)
    OUTPUT_PATH.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


def build_expected_outcome_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    records = [build_record(record) for record in coverage.get("literature_records", [])]
    expected_counts = Counter(record["expected_outcome_status"] for record in records)
    observed_counts = Counter(record["observed_vs_expected_status"] for record in records)
    runnable_records = [record for record in records if record["runnable_status"] == "runnable_profile_parameters_ready"]
    return {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "source_literature_coverage": "assets/preloads/audiotactile_literature_coverage.json",
        "scope": {
            "goal": (
                "Track whether each known audiotactile PPS literature record has a structured "
                "expected outcome and whether the current toolkit has observed evidence that can "
                "be compared against it."
            ),
            "evidence_boundary": (
                "Protocol 12, static preview parity, one-block fake-audio runner stress, and "
                "synthetic loopback prove software scheduling, WAV generation, event/marker, and "
                "artifact contracts. They do not prove human behavioral PPS effects. Observed "
                "scientific outcomes require either collected participant data or an explicit "
                "synthetic-participant model whose assumptions are documented separately."
            ),
        },
        "summary": {
            "literature_record_count": len(records),
            "structured_expected_outcome_record_count": expected_counts["structured_expected_outcome_extracted"],
            "pending_expected_outcome_record_count": expected_counts["pending_expected_outcome_extraction"],
            "adjacent_or_out_of_scope_record_count": expected_counts["adjacent_out_of_scope"],
            "runnable_profile_parameter_record_count": len(runnable_records),
            "observed_behavioral_comparison_record_count": observed_counts["observed_behavioral_comparison_available"],
            "parameter_run_evidence_only_record_count": observed_counts[
                "parameter_run_evidence_only_behavioral_effect_unobserved"
            ],
            "not_runnable_no_observed_comparison_record_count": observed_counts["not_runnable_no_observed_comparison"],
            "adjacent_not_applicable_record_count": observed_counts["adjacent_not_applicable"],
        },
        "current_observed_evidence": {
            "profile_materialization": (
                "artifacts/validation_runs/current_goal_profile_recreation_ready_all_20260714/"
                "profile_recreation_interface_matrix_report.json"
            ),
            "static_dashboard_parity": (
                "artifacts/validation_runs/current_goal_static_dashboard_parity_all_20260714_after_static_baseline_fix/"
                "static_dashboard_preview_parity_audit_report.json"
            ),
            "runner_mock": (
                "artifacts/validation_runs/current_goal_one_block_runner_20260714_duration500ms/"
                "one_block_trial_runner_report.json"
            ),
            "click_path_mock": (
                "artifacts/validation_runs/current_goal_session_click_path_20260714/"
                "session_runner_click_path_report.json"
            ),
            "synthetic_response_marker_loopback": (
                "artifacts/validation_runs/current_goal_mock_response_marker_loopback_20260714/comparison/"
                "response_marker_loopback_report.json"
            ),
        },
        "records": records,
    }


def build_record(record: dict[str, Any]) -> dict[str, Any]:
    record_id = str(record.get("record_id") or "")
    coverage_category = str(record.get("coverage_category") or "")
    template_ids = [str(value) for value in record.get("current_template_ids") or []]
    expected = EXPECTED_OUTCOMES.get(record_id)
    adjacent = coverage_category == "adjacent_out_of_scope"

    if adjacent:
        expected_status = "adjacent_out_of_scope"
    elif expected:
        expected_status = "structured_expected_outcome_extracted"
    else:
        expected_status = "pending_expected_outcome_extraction"

    runnable_status = _runnable_status(record, coverage_category, template_ids, adjacent)
    observed_status = _observed_status(expected_status, runnable_status)

    return {
        "record_id": record_id,
        "citation_short": str(record.get("citation_short") or ""),
        "doi": str(record.get("doi") or ""),
        "coverage_category": coverage_category,
        "current_template_ids": template_ids,
        "runnable_status": runnable_status,
        "expected_outcome_status": expected_status,
        "expected_outcome": expected or {},
        "observed_vs_expected_status": observed_status,
        "observed_evidence_boundary": _observed_boundary(observed_status),
        "required_next_evidence": _required_next_evidence(expected_status, runnable_status),
    }


def _runnable_status(
    record: dict[str, Any],
    coverage_category: str,
    template_ids: list[str],
    adjacent: bool,
) -> str:
    if adjacent:
        return "adjacent_not_applicable"
    if record.get("can_recreate_audiotactile_components_now") is True and template_ids:
        return "runnable_profile_parameters_ready"
    if template_ids:
        return "template_present_but_blocked"
    return "not_yet_templated"


def _observed_status(expected_status: str, runnable_status: str) -> str:
    if expected_status == "adjacent_out_of_scope":
        return "adjacent_not_applicable"
    if runnable_status != "runnable_profile_parameters_ready":
        return "not_runnable_no_observed_comparison"
    return "parameter_run_evidence_only_behavioral_effect_unobserved"


def _observed_boundary(observed_status: str) -> str:
    if observed_status == "parameter_run_evidence_only_behavioral_effect_unobserved":
        return (
            "Current evidence can show that the profile can load/materialize/run as software, "
            "but no profile-specific participant or synthetic behavioral data have been "
            "compared with the paper's expected PPS effect."
        )
    if observed_status == "not_runnable_no_observed_comparison":
        return "The study is not yet runnable as a finished toolkit profile, so no observed comparison exists."
    return "The record is adjacent or out of scope for audiotactile PPS outcome comparison."


def _required_next_evidence(expected_status: str, runnable_status: str) -> str:
    if expected_status == "adjacent_out_of_scope":
        return "No outcome comparison required unless the record is reclassified as in scope."
    if expected_status == "pending_expected_outcome_extraction":
        return (
            "Extract a short structured expected outcome from the paper's Results/figures/tables "
            "and link it to an observable analysis metric."
        )
    if runnable_status != "runnable_profile_parameters_ready":
        return "Resolve profile blockers before attempting observed-vs-expected evaluation."
    return (
        "Run a profile-specific observed dataset: either collected participant data or an explicit "
        "synthetic participant model, then compare the analysis output with the structured expected effect."
    )


if __name__ == "__main__":
    raise SystemExit(main())
