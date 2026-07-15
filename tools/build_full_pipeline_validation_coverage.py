#!/usr/bin/env python
"""Build the source-to-runner audiotactile PPS validation ledger.

This ledger mirrors the full validation chain requested for the toolkit:
original paper/PDF/source parameters -> parsimonious profile settings -> HTML
GUI/toolkit implementation -> WAV/session runner execution -> emulated
observed-vs-expected behavior. It is deliberately conservative: a downstream
gate only passes when the current tracked evidence proves that gate for the
specific literature record.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
EXPECTED_OUTCOME_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"
PROFILE_STATUS_PATH = REPO_ROOT / "assets" / "preloads" / "profile_recreation_status.json"
PAPER_AUDIT_PATH = REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit" / "metadata_audit.jsonl"
MANUAL_REVIEW_INDEX_PATH = (
    REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit" / "manual_review_index.csv"
)
OUTPUT_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_full_pipeline_validation.json"

SCHEMA = "pps-audiotactile-full-pipeline-validation.v1"
GENERATED_ON = "2026-07-15"
MOUSE_CLICK_STATUS = "mouse_click_simulated_participant_like_comparison_available"
FULL_PIPELINE_STATUS = "full_emulated_source_to_runner_pipeline_validated"
ADJACENT_STATUS = "adjacent_not_applicable"


PIPELINE_GATES = [
    {
        "id": "source_parameter_extraction",
        "label": "Original paper/PDF/source parameter extraction",
        "question": (
            "Have the minimum task parameters from the original paper/source been captured "
            "well enough to recreate the audiotactile task without private/randomization-only details?"
        ),
    },
    {
        "id": "expected_outcome_extraction",
        "label": "Expected outcome extraction",
        "question": "Has the expected paper outcome/effect direction been extracted for comparison?",
    },
    {
        "id": "parsimonious_profile_saved",
        "label": "Parsimonious profile settings saved",
        "question": "Are the minimum extracted task settings saved as a current toolkit profile?",
    },
    {
        "id": "toolkit_gui_implementation",
        "label": "Toolkit/HTML GUI implementation",
        "question": "Can the profile pass Segment 0-4 checks and materialize through the GUI/toolkit path?",
    },
    {
        "id": "wav_generation_and_runner_execution",
        "label": "WAV generation and experiment runner execution",
        "question": "Can the profile generate runnable WAV/session artifacts and run through the experiment runner?",
    },
    {
        "id": "observed_emulated_expected_match",
        "label": "Observed emulated outcome vs expected outcome",
        "question": "Do runner-produced mouse-click simulated analysis rows support the extracted expected direction?",
    },
]


def build_full_pipeline_validation() -> dict[str, Any]:
    coverage = _load_json(COVERAGE_PATH)
    expected = _load_json(EXPECTED_OUTCOME_PATH)
    profile_status = _load_json(PROFILE_STATUS_PATH)
    paper_audit = _load_paper_audit(PAPER_AUDIT_PATH)
    manual_reviews = _load_manual_review_index(MANUAL_REVIEW_INDEX_PATH)

    expected_by_id = {record["record_id"]: record for record in expected["records"]}
    profile_by_id = {profile["template_id"]: profile for profile in profile_status["profiles"]}
    records = [
        _build_record(record, expected_by_id[record["record_id"]], profile_by_id, paper_audit, manual_reviews)
        for record in coverage["literature_records"]
    ]
    return {
        "schema": SCHEMA,
        "generated_on": GENERATED_ON,
        "source_ledgers": {
            "literature_coverage": "assets/preloads/audiotactile_literature_coverage.json",
            "expected_outcome_coverage": "assets/preloads/audiotactile_expected_outcome_coverage.json",
            "profile_recreation_status": "assets/preloads/profile_recreation_status.json",
            "paper_metadata_audit": "For-AI/audiotactile-paper-metadata-audit/metadata_audit.jsonl",
            "manual_review_index": "For-AI/audiotactile-paper-metadata-audit/manual_review_index.csv",
        },
        "pipeline_definition": {
            "start": "original paper/PDF/source parameter extraction",
            "end": "observed mouse-click emulated PPS runner behavior compared with extracted expected outcome",
            "gates": PIPELINE_GATES,
        },
        "scope": {
            "minimum_parameter_policy": (
                "The source gate asks whether the minimum audiotactile task parameters needed for a "
                "parsimonious profile are captured: stimulus/source provenance, trajectory or fixed "
                "source geometry, tactile timing/site/channel/calibration when task-critical, SOA or "
                "distance-at-tactile table, baseline/catch strategy, ITI/jitter when task-critical, and "
                "trial repetition counts. Routine randomization and block order are toolkit-native unless "
                "the paper's timing policy makes them task-defining."
            ),
            "evidence_boundary": (
                "A full pass in this ledger means source-to-runner emulated software validation with "
                "deterministic participant-like mouse clicks. It is not collected participant evidence, "
                "not a physical loopback or tactile-onset measurement, and not a scientific replication claim."
            ),
        },
        "summary": _summary(records),
        "records": records,
    }


def _build_record(
    literature: dict[str, Any],
    expected: dict[str, Any],
    profile_by_id: dict[str, dict[str, Any]],
    paper_audit: dict[str, dict[str, Any]],
    manual_reviews: dict[str, dict[str, str]],
) -> dict[str, Any]:
    record_id = literature["record_id"]
    category = literature["coverage_category"]
    template_ids = list(literature.get("current_template_ids") or [])
    template_profiles = [profile_by_id.get(template_id, {}) for template_id in template_ids]
    adjacent = category == "adjacent_out_of_scope"
    profile_ready = bool(
        template_ids
        and all(profile.get("finished_profile") and profile.get("segment_6_launchable") for profile in template_profiles)
    )
    expected_ready = expected.get("expected_outcome_status") == "structured_expected_outcome_extracted"
    source_ready = bool(
        category == "covered_runnable_profile"
        and literature.get("can_recreate_audiotactile_components_now") is True
        and not literature.get("blocking_constraint_ids")
        and not literature.get("missing_publication_parameters")
    )
    mouse_click_evidence = expected.get("observed_mouse_click_participant_like_evidence") or {}
    mouse_click_ready = mouse_click_evidence.get("status") == MOUSE_CLICK_STATUS
    paper_record = paper_audit.get(record_id, {})
    gates = {
        "source_parameter_extraction": _source_gate(literature, paper_record, manual_reviews.get(record_id, {})),
        "expected_outcome_extraction": _expected_gate(expected, adjacent),
        "parsimonious_profile_saved": _profile_gate(literature, template_profiles, source_ready, adjacent),
        "toolkit_gui_implementation": _toolkit_gui_gate(literature, template_profiles, profile_ready, adjacent),
        "wav_generation_and_runner_execution": _runner_gate(expected, profile_ready, mouse_click_ready, adjacent),
        "observed_emulated_expected_match": _observed_gate(expected, mouse_click_evidence, mouse_click_ready, adjacent),
    }
    full_pass = bool(not adjacent and all(gate["passed"] for gate in gates.values()))
    return {
        "record_id": record_id,
        "citation_short": literature.get("citation_short", ""),
        "doi": literature.get("doi", ""),
        "coverage_category": category,
        "pipeline_status": _pipeline_status(literature, expected, full_pass, adjacent),
        "full_emulated_pipeline_validated": full_pass,
        "current_template_ids": template_ids,
        "audiotactile_task_family": literature.get("audiotactile_task_family", ""),
        "source_basis": list(literature.get("source_basis") or []),
        "paper_audit": _paper_audit_summary(paper_record, manual_reviews.get(record_id, {})),
        "blocking_constraint_ids": list(literature.get("blocking_constraint_ids") or []),
        "missing_publication_parameters": list(literature.get("missing_publication_parameters") or []),
        "known_parameter_validation_report": literature.get("known_parameter_validation_report", ""),
        "expected_outcome_status": expected.get("expected_outcome_status", ""),
        "expected_effect_direction": (expected.get("expected_outcome") or {}).get("expected_effect_direction", ""),
        "runnable_status": expected.get("runnable_status", ""),
        "observed_vs_expected_status": expected.get("observed_vs_expected_status", ""),
        "gates": gates,
        "next_required_action": _next_required_action(literature, expected, gates, full_pass, adjacent),
    }


def _source_gate(
    literature: dict[str, Any], paper_record: dict[str, Any], manual_review: dict[str, str]
) -> dict[str, Any]:
    category = literature["coverage_category"]
    if category == "adjacent_out_of_scope":
        return _gate(
            passed=True,
            status="not_applicable_adjacent_record",
            evidence="Record is not an in-scope audiotactile PPS task.",
        )
    blockers = list(literature.get("blocking_constraint_ids") or [])
    missing = list(literature.get("missing_publication_parameters") or [])
    passed = (
        category == "covered_runnable_profile"
        and literature.get("can_recreate_audiotactile_components_now") is True
        and not blockers
        and not missing
    )
    if passed:
        status = "minimum_source_parameters_captured"
        evidence = "Literature ledger marks the task as currently recreatable with no blocking constraints or missing publication parameters."
    else:
        status = "source_parameters_missing_or_unresolved"
        evidence = "Tracked source/PDF audit does not yet prove all minimum task parameters needed for a runnable profile."
    return _gate(
        passed=passed,
        status=status,
        evidence=evidence,
        blockers=blockers,
        missing_parameters=missing,
        paper_audit=_paper_audit_summary(paper_record, manual_review),
    )


def _expected_gate(expected: dict[str, Any], adjacent: bool) -> dict[str, Any]:
    if adjacent:
        return _gate(True, "not_applicable_adjacent_record", "No expected outcome required for adjacent records.")
    passed = expected.get("expected_outcome_status") == "structured_expected_outcome_extracted"
    return _gate(
        passed,
        "structured_expected_outcome_extracted" if passed else "expected_outcome_missing",
        "Structured expected effect direction is available." if passed else "Expected outcome extraction is incomplete.",
        expected_effect_direction=(expected.get("expected_outcome") or {}).get("expected_effect_direction", ""),
        source_basis=list((expected.get("expected_outcome") or {}).get("source_basis") or []),
    )


def _profile_gate(
    literature: dict[str, Any],
    template_profiles: list[dict[str, Any]],
    source_ready: bool,
    adjacent: bool,
) -> dict[str, Any]:
    if adjacent:
        return _gate(True, "not_applicable_adjacent_record", "No profile required for adjacent records.")
    template_ids = list(literature.get("current_template_ids") or [])
    finished = bool(template_ids and all(profile.get("finished_profile") for profile in template_profiles))
    passed = bool(source_ready and finished)
    if passed:
        status = "parsimonious_profile_complete"
        evidence = "All current template IDs are finished profiles and source parameters are complete."
    elif template_ids:
        status = "profile_scaffold_present_but_incomplete"
        evidence = "A template/profile scaffold exists, but minimum source parameters or launch readiness are incomplete."
    else:
        status = "profile_not_yet_created"
        evidence = "No current toolkit profile is linked to this literature record."
    return _gate(
        passed,
        status,
        evidence,
        template_ids=template_ids,
        profile_completion_statuses=[
            profile.get("profile_completion_status", "missing_profile_status") for profile in template_profiles
        ],
    )


def _toolkit_gui_gate(
    literature: dict[str, Any],
    template_profiles: list[dict[str, Any]],
    profile_ready: bool,
    adjacent: bool,
) -> dict[str, Any]:
    if adjacent:
        return _gate(True, "not_applicable_adjacent_record", "No GUI/toolkit implementation required for adjacent records.")
    passed = bool(profile_ready)
    if passed:
        status = "segment_0_to_6_gui_toolkit_path_ready"
        evidence = "Profile status reports Segment 0-4 checks, Segment 1-6 materialization, and Segment 6 launch readiness."
    elif literature.get("coverage_category") == "not_yet_templated_requires_toolkit_structure":
        status = "blocked_by_toolkit_structure_or_response_contract"
        evidence = "The current toolkit/GUI schema does not yet model every task-mechanics blocker for this record."
    else:
        status = "blocked_by_missing_profile_parameters"
        evidence = "Toolkit path cannot be validated until the source parameters/profile are complete."
    return _gate(
        passed,
        status,
        evidence,
        blocker_ids=list(literature.get("blocking_constraint_ids") or []),
        profile_readiness=[
            {
                "template_id": profile.get("template_id", ""),
                "runner_readiness": profile.get("runner_readiness", ""),
                "segment_0_to_4_profile_checks_passed": profile.get("segment_0_to_4_profile_checks_passed", False),
                "segment_1_to_6_materializable": profile.get("segment_1_to_6_materializable", False),
                "segment_6_launchable": profile.get("segment_6_launchable", False),
            }
            for profile in template_profiles
        ],
    )


def _runner_gate(
    expected: dict[str, Any],
    profile_ready: bool,
    mouse_click_ready: bool,
    adjacent: bool,
) -> dict[str, Any]:
    if adjacent:
        return _gate(True, "not_applicable_adjacent_record", "No runner execution required for adjacent records.")
    passed = bool(profile_ready and mouse_click_ready)
    evidence = expected.get("observed_mouse_click_participant_like_evidence") or {}
    return _gate(
        passed,
        "wav_runner_mouse_click_emulation_available" if passed else "runner_execution_not_available_for_record",
        (
            "Ready profile was materialized and evaluated through SessionRunnerController with deterministic mouse clicks."
            if passed
            else "No record-level mouse-click runner comparison exists because the profile is not fully runnable."
        ),
        source_report=evidence.get("source_report", ""),
        runnable_status=expected.get("runnable_status", ""),
    )


def _observed_gate(
    expected: dict[str, Any],
    mouse_click_evidence: dict[str, Any],
    mouse_click_ready: bool,
    adjacent: bool,
) -> dict[str, Any]:
    if adjacent:
        return _gate(True, "not_applicable_adjacent_record", "No observed comparison required for adjacent records.")
    passed = bool(mouse_click_ready)
    return _gate(
        passed,
        "emulated_observed_direction_matches_expected" if passed else "no_observed_emulated_comparison",
        (
            "Runner-produced analysis rows are recorded as matching the extracted expected direction in the mouse-click audit."
            if passed
            else "No observed emulated comparison exists for this record."
        ),
        observed_vs_expected_status=expected.get("observed_vs_expected_status", ""),
        source_report=mouse_click_evidence.get("source_report", ""),
        evidence_boundary=mouse_click_evidence.get("model_boundary", ""),
    )


def _pipeline_status(
    literature: dict[str, Any], expected: dict[str, Any], full_pass: bool, adjacent: bool
) -> str:
    if adjacent:
        return ADJACENT_STATUS
    if full_pass:
        return FULL_PIPELINE_STATUS
    category = literature["coverage_category"]
    if category == "covered_blocked_missing_publication_parameters":
        return "profile_present_but_source_parameters_missing"
    if category == "not_yet_templated_missing_publication_parameters":
        return "source_parameters_missing_before_profile_creation"
    if category == "not_yet_templated_requires_toolkit_structure":
        return "toolkit_structure_or_response_contract_missing"
    if expected.get("runnable_status") == "template_present_but_blocked":
        return "profile_present_but_blocked"
    return "pipeline_incomplete"


def _next_required_action(
    literature: dict[str, Any],
    expected: dict[str, Any],
    gates: dict[str, dict[str, Any]],
    full_pass: bool,
    adjacent: bool,
) -> str:
    if adjacent:
        return "No action unless this record is reclassified as an in-scope audiotactile PPS task."
    if full_pass:
        return (
            "Emulated source-to-runner pipeline is available; collect participant and physical timing/loopback "
            "evidence before making a scientific replication claim."
        )
    if literature.get("coverage_category") == "not_yet_templated_requires_toolkit_structure":
        action = "Implement or validate toolkit support for: " + ", ".join(literature["blocking_constraint_ids"])
        missing = literature.get("missing_publication_parameters") or []
        if missing:
            action += "; also extract/source missing paper parameters: " + "; ".join(missing)
        return action
    if not gates["source_parameter_extraction"]["passed"]:
        missing = literature.get("missing_publication_parameters") or []
        if missing:
            return "Extract or source the missing paper parameters: " + "; ".join(missing)
    if not literature.get("current_template_ids"):
        return "Create a parsimonious toolkit profile after source parameters and toolkit blockers are resolved."
    return expected.get("required_next_evidence") or "Resolve the first failed pipeline gate."


def _summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts = Counter(record["pipeline_status"] for record in records)
    gate_counts: dict[str, dict[str, int]] = {}
    for gate_id in [gate["id"] for gate in PIPELINE_GATES]:
        gate_counts[gate_id] = dict(
            sorted(Counter(record["gates"][gate_id]["status"] for record in records).items())
        )
    return {
        "literature_record_count": len(records),
        "in_scope_record_count": sum(record["pipeline_status"] != ADJACENT_STATUS for record in records),
        "adjacent_not_applicable_record_count": status_counts.get(ADJACENT_STATUS, 0),
        "full_emulated_pipeline_validated_record_count": status_counts.get(FULL_PIPELINE_STATUS, 0),
        "human_behavioral_observed_record_count": 0,
        "physical_loopback_observed_record_count": 0,
        "pipeline_status_counts": dict(sorted(status_counts.items())),
        "gate_status_counts": gate_counts,
        "primary_gap_counts": {
            "profile_present_but_source_parameters_missing": status_counts.get(
                "profile_present_but_source_parameters_missing", 0
            ),
            "source_parameters_missing_before_profile_creation": status_counts.get(
                "source_parameters_missing_before_profile_creation", 0
            ),
            "toolkit_structure_or_response_contract_missing": status_counts.get(
                "toolkit_structure_or_response_contract_missing", 0
            ),
        },
    }


def _paper_audit_summary(paper_record: dict[str, Any], manual_review: dict[str, str]) -> dict[str, Any]:
    if not paper_record and not manual_review:
        return {}
    return {
        "pdf_status": paper_record.get("pdf_status", ""),
        "supplement_status": paper_record.get("supplement_status", ""),
        "extraction_status": paper_record.get("extraction_status", ""),
        "metadata_confidence_label": paper_record.get("metadata_confidence_label", ""),
        "metadata_confidence_score": paper_record.get("metadata_confidence_score", 0),
        "automated_evidence_status": (paper_record.get("automated_evidence_mining") or {}).get("status", ""),
        "manual_review_status": manual_review.get("manual_review_status", "") or manual_review.get("review_status", ""),
        "manual_review_confidence_label": manual_review.get("confidence_label", ""),
        "manual_review_profile_recreation_assessment": manual_review.get("profile_recreation_assessment", ""),
    }


def _gate(passed: bool, status: str, evidence: str, **extra: Any) -> dict[str, Any]:
    payload = {"passed": bool(passed), "status": status, "evidence": evidence}
    payload.update(extra)
    return payload


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_paper_audit(path: Path) -> dict[str, dict[str, Any]]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return {record["record_id"]: record for record in records}


def _load_manual_review_index(path: Path) -> dict[str, dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["record_id"]: row for row in csv.DictReader(handle)}


def main() -> int:
    OUTPUT_PATH.write_text(
        json.dumps(build_full_pipeline_validation(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
