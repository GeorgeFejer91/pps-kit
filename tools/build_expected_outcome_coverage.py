#!/usr/bin/env python
"""Build the audiotactile expected-outcome coverage ledger.

This ledger is deliberately conservative. It records which literature records
have a structured expected behavioral/scientific outcome extracted, and whether
the current toolkit has any observed evidence that can be compared with that
outcome. Software mock runs can validate schedules, WAV generation, markers, and
analysis plumbing; they do not validate human PPS effects.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
OUTPUT_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"
PAPER_AUDIT_CHECKLIST_PATH = (
    REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit" / "running_checklist.csv"
)
MANUAL_REVIEW_INDEX_PATH = (
    REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit" / "manual_review_index.csv"
)

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
    "biggio_2017_racket_tool_use": {
        "outcome_family": "tool_condition_modulation_of_static_audio_tactile_pps",
        "primary_expected_effect": (
            "Racket-related conditions are expected to modulate the static near/far "
            "audio-tactile interaction around the stimulated wrist, shifting the "
            "near-versus-far tactile-response benefit relative to the no-racket condition."
        ),
        "expected_effect_direction": "racket_context_changes_near_far_audio_tactile_facilitation",
        "observable_metric": "tactile response performance by near/far sound position and racket condition",
        "condition_contrast": "no-racket versus common-racket versus personal-racket blocked sessions",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/biggio_2017_racket_tool_use.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#biggio_2017_racket_tool_use",
        ],
    },
    "canzoneri_2012_dynamic_sounds": {
        "outcome_family": "dynamic_looming_audio_tactile_pps_boundary",
        "primary_expected_effect": (
            "Dynamic approaching sounds are expected to facilitate tactile responses "
            "as they enter near body space, producing a distance/SOA-dependent PPS "
            "function that is weaker or differently shaped for receding sounds."
        ),
        "expected_effect_direction": "approaching_near_body_sounds_speed_tactile_rt",
        "observable_metric": "tactile RT/facilitation curve and sigmoid-derived boundary by T1-T5 timing",
        "condition_contrast": "approaching/IN versus receding/OUT pink-noise trajectories plus tactile-only baselines",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/canzoneri_2012_dynamic_sounds.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#canzoneri_2012_dynamic_sounds",
        ],
    },
    "cell_reports_medicine_2026_consciousness": {
        "outcome_family": "passive_near_far_audio_tactile_eeg_consciousness_index",
        "primary_expected_effect": (
            "Static near/far audio-tactile stimulation is expected to produce EEG "
            "multisensory-integration signatures that vary with conscious state, "
            "with near-space audio-tactile responses serving as the PPS-sensitive endpoint."
        ),
        "expected_effect_direction": "near_far_audio_tactile_eeg_integration_tracks_conscious_state",
        "observable_metric": "EEG multisensory response or classifier feature for ATNear/ATFar versus unisensory rows",
        "condition_contrast": "healthy wake/sleep or DoC state groups crossed with near/far audio-tactile conditions",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/cell_reports_medicine_2026_consciousness.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#cell_reports_medicine_2026_consciousness",
        ],
    },
    "disorders_consciousness_2019": {
        "outcome_family": "passive_near_far_audio_tactile_eeg_doc_encoding",
        "primary_expected_effect": (
            "Passive arm-centered near/far audio-tactile stimulation is expected to "
            "show multisensory EEG encoding of PPS that is preserved or graded by "
            "disorder-of-consciousness status rather than appearing as a behavioral RT effect."
        ),
        "expected_effect_direction": "near_far_audio_tactile_eeg_encoding_differs_by_consciousness_state",
        "observable_metric": "EEG response to ATNear/ATFar relative to tactile-only and auditory-only controls",
        "condition_contrast": "DoC/patient status and healthy controls crossed with tactile, auditory-near/far, and AT-near/far rows",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/disorders_consciousness_2019.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#disorders_consciousness_2019",
        ],
    },
    "farne_ladavas_2002_auditory_pps_humans": {
        "outcome_family": "static_perihead_audio_tactile_extinction_modulation",
        "primary_expected_effect": (
            "Static sounds close to the body are expected to modulate tactile "
            "extinction/detection more strongly than far sounds, establishing a "
            "near-space auditory-tactile interaction without a looming trajectory."
        ),
        "expected_effect_direction": "near_sounds_modulate_tactile_extinction_more_than_far_sounds",
        "observable_metric": "tactile report/extinction rate by speaker distance and front/back position",
        "condition_contrast": "near versus far and front/back static auditory positions with tactile-only/no-stimulation rows",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/farne_ladavas_2002_auditory_pps_humans.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#farne_ladavas_2002_auditory_pps_humans",
        ],
    },
    "finisguerra_2015_moving_sounds_motor": {
        "outcome_family": "moving_sound_modulation_of_hand_motor_excitability",
        "primary_expected_effect": (
            "Moving sounds within the hand-centered PPS are expected to modulate "
            "hand motor-cortex excitability, with MEP amplitude varying by sound "
            "position and motion direction rather than by tactile RT."
        ),
        "expected_effect_direction": "near_hand_moving_sounds_modulate_mep_excitability",
        "observable_metric": "TMS-evoked MEP amplitude by sampled sound position and IN/OUT direction",
        "condition_contrast": "approaching versus receding moving sounds, sampled positions, and pre/post no-noise baselines",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/finisguerra_2015_moving_sounds_motor.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#finisguerra_2015_moving_sounds_motor",
        ],
    },
    "ieeg_trunk_2018": {
        "outcome_family": "intracranial_trunk_pps_multisensory_neural_map",
        "primary_expected_effect": (
            "Passive trunk-centered audio-tactile trials are expected to reveal "
            "distance-sensitive multisensory neural responses in intracranial "
            "recordings, strongest for PPS-relevant front-approach timings."
        ),
        "expected_effect_direction": "near_trunk_audio_tactile_trials_show_stronger_neural_integration",
        "observable_metric": "iEEG multisensory response to AT trials relative to A-only and T-only rows by tactile timing",
        "condition_contrast": "A, T, and AT randomized trials across trunk-centered tactile timings/distances",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/ieeg_trunk_2018.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#ieeg_trunk_2018",
        ],
    },
    "ronga_2021_newborn_erp": {
        "outcome_family": "newborn_near_far_audio_tactile_erp_spatial_tuning",
        "primary_expected_effect": (
            "Near hand-centered audio-tactile stimulation is expected to evoke a "
            "different ERP multisensory response than far stimulation, showing "
            "spatial tuning of audio-tactile PPS responses in newborns and adults."
        ),
        "expected_effect_direction": "near_audio_tactile_erp_response_differs_from_far",
        "observable_metric": "ERP amplitude/latency response for near/far audio-tactile versus unisensory controls",
        "condition_contrast": "near versus far speaker positions and audio-tactile versus unisensory condition rows",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/ronga_2021_newborn_erp.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#ronga_2021_newborn_erp",
        ],
    },
    "serino_2007_blind_cane_users": {
        "outcome_family": "cane_use_static_near_far_pps_extension",
        "primary_expected_effect": (
            "Cane/tool-use conditions are expected to extend or reshape the "
            "near/far audio-tactile interaction, so far sounds aligned with cane "
            "use show stronger tactile-detection benefit than in baseline/handle conditions."
        ),
        "expected_effect_direction": "cane_use_extends_audio_tactile_facilitation_toward_far_space",
        "observable_metric": "tactile target detection/RT by near/far sound position and cane/handle/training condition",
        "condition_contrast": "cane versus handle/tool-use conditions, blind versus sighted groups, near versus far sounds",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2007_blind_cane_users.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#serino_2007_blind_cane_users",
        ],
    },
    "serino_2015_front_back_trunk_exp2": {
        "outcome_family": "front_back_trunk_audio_tactile_pps_boundary",
        "primary_expected_effect": (
            "Dynamic sounds moving through front and back trunk space are expected "
            "to facilitate tactile responses most when the sound is close to the "
            "corresponding trunk tactile anchor, yielding front/back PPS functions."
        ),
        "expected_effect_direction": "near_trunk_front_back_sounds_speed_corresponding_tactile_rt",
        "observable_metric": "tactile RT/facilitation by front/back trajectory distance and tactile site",
        "condition_contrast": "front-to-back versus back-to-front 16-speaker motion and sternum/back tactile anchors",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_front_back_trunk_exp2.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#serino_2015_front_back_trunk_exp2",
        ],
    },
    "serino_2015_peri_hand_exp3": {
        "outcome_family": "lateralized_perihand_audio_tactile_pps_boundary",
        "primary_expected_effect": (
            "Hand-centered moving sounds are expected to facilitate tactile "
            "responses most near the stimulated hand, producing a peri-hand PPS "
            "function across the reported D1-D5 distance table."
        ),
        "expected_effect_direction": "near_hand_sounds_speed_hand_tactile_rt",
        "observable_metric": "hand tactile RT/facilitation by D1-D5 distance and looming/receding direction",
        "condition_contrast": "lateralized two-speaker moving sounds, tactile-only D1/D5 baselines, and sound-only catches",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_peri_hand_exp3.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#serino_2015_peri_hand_exp3",
        ],
    },
    "serino_2015_exps_4_to_6": {
        "outcome_family": "body_part_centered_pps_remapping_across_hand_trunk_face",
        "primary_expected_effect": (
            "Experiments 4-6 are expected to show that audio-tactile facilitation "
            "follows the currently relevant body-part anchor and sound-location "
            "congruency, rather than a single fixed trunk-centered boundary."
        ),
        "expected_effect_direction": "audio_tactile_facilitation_tracks_body_part_anchor_and_congruency",
        "observable_metric": "tactile RT/facilitation by hand/trunk/face tactile site, distance, posture, and sound-location congruency",
        "condition_contrast": "Exp. 4 hand versus trunk, Exp. 5 hand near versus far from trunk, Exp. 6 face/trunk congruent versus incongruent locations",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/serino_2015_exps_4_to_6.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#serino_2015_exps_4_to_6",
        ],
    },
    "taffou_2021_auditory_roughness": {
        "outcome_family": "affective_roughness_expansion_of_audio_tactile_pps",
        "primary_expected_effect": (
            "Rough looming sounds are expected to expand or strengthen PPS-related "
            "tactile facilitation relative to non-rough looming sounds, shifting "
            "the response benefit farther into rear-left space."
        ),
        "expected_effect_direction": "rough_sounds_expand_distance_range_of_tactile_facilitation",
        "observable_metric": "tactile RT/facilitation by Tbefore/T1-T5/Tafter timing and rough versus non-rough sound type",
        "condition_contrast": "rough versus non-rough rear-left binaural looming sounds plus silent baseline timings",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/taffou_2021_auditory_roughness.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#taffou_2021_auditory_roughness",
        ],
    },
    "tajadura_jimenez_2009_visual_deprivation": {
        "outcome_family": "static_left_right_audio_tactile_spatial_congruency",
        "primary_expected_effect": (
            "Static left/right audio-tactile trials are expected to show "
            "spatial-congruency and posture-dependent multisensory facilitation, "
            "with visual-deprivation history affecting how external space is coded."
        ),
        "expected_effect_direction": "spatially_congruent_audio_tactile_trials_show_posture_dependent_facilitation",
        "observable_metric": "response speed/accuracy or redundancy-gain metric by side congruency and crossed/uncrossed posture",
        "condition_contrast": "auditory-only, tactile-only, and congruent audio-tactile rows in crossed versus uncrossed posture blocks",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/tajadura_jimenez_2009_visual_deprivation.json",
            "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv#tajadura_jimenez_2009_visual_deprivation",
        ],
    },
    "tonelli_2019_echolocation": {
        "outcome_family": "echolocation_training_modulation_of_lateral_head_pps",
        "primary_expected_effect": (
            "Echolocation training is expected to reshape lateral head/neck PPS, "
            "changing the distance-dependent tactile facilitation curve from pre "
            "to post training relative to control conditions."
        ),
        "expected_effect_direction": "echolocation_training_changes_lateral_head_pps_boundary",
        "observable_metric": "neck tactile RT/facilitation by seven speaker-defined distances before and after training",
        "condition_contrast": "pre versus post echolocation training, lateral seven-speaker looming trajectory, baselines, and catches",
        "source_basis": [
            "For-AI/audiotactile-paper-metadata-audit/manual_reviews/tonelli_2019_echolocation.json",
            "For-AI/audiotactile-paper-metadata-audit/pps_visualization_inventory.csv#tonelli_2019_echolocation",
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
    paper_audit_index = _load_csv_index(PAPER_AUDIT_CHECKLIST_PATH, key="record_id")
    manual_review_index = _load_csv_index(MANUAL_REVIEW_INDEX_PATH, key="record_id")
    records = [
        build_record(
            record,
            paper_audit_index.get(str(record.get("record_id") or ""), {}),
            manual_review_index.get(str(record.get("record_id") or ""), {}),
        )
        for record in coverage.get("literature_records", [])
    ]
    expected_counts = Counter(record["expected_outcome_status"] for record in records)
    observed_counts = Counter(record["observed_vs_expected_status"] for record in records)
    blocker_counts = Counter(
        record["expected_outcome_extraction_blocker"]
        for record in records
        if record["expected_outcome_status"] == "pending_expected_outcome_extraction"
    )
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
            "pending_expected_outcome_blocker_counts": dict(sorted(blocker_counts.items())),
        },
        "expected_outcome_extraction_sources": {
            "paper_audit_checklist": "For-AI/audiotactile-paper-metadata-audit/running_checklist.csv",
            "manual_review_index": "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv",
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


def build_record(
    record: dict[str, Any],
    paper_audit_row: dict[str, str] | None = None,
    manual_review_row: dict[str, str] | None = None,
) -> dict[str, Any]:
    record_id = str(record.get("record_id") or "")
    coverage_category = str(record.get("coverage_category") or "")
    template_ids = [str(value) for value in record.get("current_template_ids") or []]
    expected = EXPECTED_OUTCOMES.get(record_id)
    adjacent = coverage_category == "adjacent_out_of_scope"
    paper_audit = paper_audit_row or {}
    manual_review = manual_review_row or {}

    if adjacent:
        expected_status = "adjacent_out_of_scope"
    elif expected:
        expected_status = "structured_expected_outcome_extracted"
    else:
        expected_status = "pending_expected_outcome_extraction"

    runnable_status = _runnable_status(record, coverage_category, template_ids, adjacent)
    observed_status = _observed_status(expected_status, runnable_status)
    extraction_blocker = _expected_outcome_extraction_blocker(expected_status, paper_audit, manual_review)

    return {
        "record_id": record_id,
        "citation_short": str(record.get("citation_short") or ""),
        "doi": str(record.get("doi") or ""),
        "coverage_category": coverage_category,
        "current_template_ids": template_ids,
        "runnable_status": runnable_status,
        "expected_outcome_status": expected_status,
        "expected_outcome": expected or {},
        "expected_outcome_extraction_blocker": extraction_blocker,
        "expected_outcome_source_audit": _expected_outcome_source_audit(paper_audit, manual_review),
        "observed_vs_expected_status": observed_status,
        "observed_evidence_boundary": _observed_boundary(observed_status),
        "required_next_evidence": _required_next_evidence(expected_status, runnable_status),
    }


def _load_csv_index(path: Path, key: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return {
            str(row.get(key) or ""): {str(k): str(v or "") for k, v in row.items()}
            for row in rows
            if row.get(key)
        }


def _expected_outcome_extraction_blocker(
    expected_status: str,
    paper_audit: dict[str, str],
    manual_review: dict[str, str],
) -> str:
    if expected_status == "structured_expected_outcome_extracted":
        return "structured_expected_outcome_available"
    if expected_status == "adjacent_out_of_scope":
        return "adjacent_out_of_scope"

    manual_status = manual_review.get("manual_review_status", "")
    manual_confidence = manual_review.get("confidence_label", "")
    if manual_status:
        if manual_confidence == "partial_extraction" or "supplement_blocked" in manual_status:
            return "manual_review_partial_or_supplement_blocked"
        return "manual_review_needs_results_direction_structuring"

    pdf_status = paper_audit.get("pdf_status", "")
    extraction_status = paper_audit.get("extraction_status", "")
    metadata_confidence = paper_audit.get("metadata_confidence_label", "")
    visualization_status = paper_audit.get("pps_visualization_audit_status", "")

    if visualization_status == "source_mined":
        return "source_mined_needs_results_visual_review"
    if pdf_status == "needs_user_download":
        return "needs_user_pdf_download"
    if pdf_status in {"paywalled", "open_access_unavailable"}:
        return "main_pdf_unavailable_or_paywalled"
    if extraction_status == "pending_pdf":
        return "pending_pdf_extraction"
    if metadata_confidence in {"pending_source", "source_unavailable"}:
        return "source_unavailable_or_pending"
    return "expected_outcome_not_yet_reviewed"


def _expected_outcome_source_audit(
    paper_audit: dict[str, str],
    manual_review: dict[str, str],
) -> dict[str, str]:
    fields = {
        "paper_audit_pdf_status": paper_audit.get("pdf_status", ""),
        "paper_audit_supplement_status": paper_audit.get("supplement_status", ""),
        "paper_audit_extraction_status": paper_audit.get("extraction_status", ""),
        "paper_audit_metadata_confidence_label": paper_audit.get("metadata_confidence_label", ""),
        "paper_audit_visualization_status": paper_audit.get("pps_visualization_audit_status", ""),
        "paper_audit_visualization_candidate_count": paper_audit.get("pps_visualization_candidate_count", ""),
        "manual_review_status": manual_review.get("manual_review_status", ""),
        "manual_review_confidence_label": manual_review.get("confidence_label", ""),
        "manual_review_profile_recreation_assessment": manual_review.get("profile_recreation_assessment", ""),
    }
    return {key: value for key, value in fields.items() if value}


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
    if runnable_status == "not_yet_templated":
        return (
            "Create a profile template or add the missing toolkit structure before attempting "
            "observed-vs-expected evaluation."
        )
    if runnable_status != "runnable_profile_parameters_ready":
        return "Resolve profile blockers before attempting observed-vs-expected evaluation."
    return (
        "Run a profile-specific observed dataset: either collected participant data or an explicit "
        "synthetic participant model, then compare the analysis output with the structured expected effect."
    )


if __name__ == "__main__":
    raise SystemExit(main())
