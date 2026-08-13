#!/usr/bin/env python3
"""Build the compact paper-facing PPS emulation review matrices.

The compact matrix deliberately reports evidence state at the thirteen-contract
level. Exact serializer fields and profile values remain in the current-input
matrices and are linked from the normalized evidence ledger.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit"
DEFAULT_OUTPUT_DIR = AUDIT_DIR / "publication-parameter-matrix"
CONTRACT_PATH = AUDIT_DIR / "parsimonious_emulation_contract.v1.json"
METADATA_AUDIT_PATH = AUDIT_DIR / "metadata_audit.jsonl"
MANUAL_REVIEW_DIR = AUDIT_DIR / "manual_reviews"
CURRENT_INPUT_SCHEMA_PATH = REPO_ROOT / "tools" / "current_toolkit_input_schema.json"
SOURCE_REVIEW_PATH = AUDIT_DIR / "parsimonious_source_reviews.v1.json"
STRUCTURE_REVIEW_PATH = AUDIT_DIR / "study_structure_reviews.v1.json"
STRUCTURE_CONTRACT_KEY = "study_structure_schedule"
MEASUREMENT_REVIEW_PATH = AUDIT_DIR / "measurement_acquisition_reviews.v1.json"
MEASUREMENT_CONTRACT_KEY = "measurement_acquisition_outcome"


EXPECTED_CONTRACT_KEYS = (
    "auditory_stimulus",
    "trajectory_kinematics",
    "trial_sequence",
    "task_response",
    "jitter_iti_policy",
    "soa_schedule",
    "tactile_target",
    "baseline_trial_contract",
    "catch_trial_contract",
    "repetition_allocation",
    "block_order_contract",
    STRUCTURE_CONTRACT_KEY,
    MEASUREMENT_CONTRACT_KEY,
)
EXPECTED_COMPLETION_RULES = {
    "auditory_stimulus": "dependency_review",
    "trajectory_kinematics": "trajectory_dependency",
    "trial_sequence": "all_required",
    "task_response": "response_dependency",
    "jitter_iti_policy": "all_required",
    "soa_schedule": "soa_dependency",
    "tactile_target": "all_required",
    "baseline_trial_contract": "control_family_dependency",
    "catch_trial_contract": "control_family_dependency",
    "repetition_allocation": "all_required",
    "block_order_contract": "all_required",
    STRUCTURE_CONTRACT_KEY: "study_structure_dependency",
    MEASUREMENT_CONTRACT_KEY: "measurement_acquisition_dependency",
}
EXPECTED_FUTURE_TOOLKIT_PATHS = {
    STRUCTURE_CONTRACT_KEY: (
        "pps-study-plan.v1::sample_and_assignment",
        "pps-study-plan.v1::factors[]",
        "pps-study-plan.v1::schedule.events[]",
        "pps-study-plan.v1::schedule.events[].protocol_binding",
        "pps-study-plan.v1::assignment_and_order_policy",
    ),
    MEASUREMENT_CONTRACT_KEY: (
        "pps-study-plan.v1::schedule.events[].measurement_binding",
        "pps-acquisition-plan.v1::acquisitions[]",
    ),
}
RESOLVED_EVIDENCE_STATUSES = {
    "reported_complete",
    "derived_complete",
    "explicitly_absent",
    "not_applicable",
}
EMULATION_COVERAGE_STATUSES = {
    "reported_complete",
    "derived_complete",
    "explicitly_absent",
}
SOURCE_VALUE_REQUIRED_STATUSES = {
    "reported_complete",
    "derived_complete",
    "approximation_required",
    "partial",
    "conflicting_evidence",
    "low_confidence",
    "explicitly_absent",
}
REVIEW_QUEUE_EXCLUDED_STATUSES = {
    "reported_complete",
    "explicitly_absent",
    "not_applicable",
}

STATUS_LEGEND = {
    "reported_complete": (
        "An experiment-scoped final-contract review found the required scientific components "
        "reported. This does not independently certify Toolkit implementation fidelity."
    ),
    "derived_complete": (
        "An experiment-scoped final-contract review found the contract reconstructible using "
        "a recorded formula or reviewed protocol lineage."
    ),
    "approximation_required": (
        "The paper constrains the method but a private asset, calibration, exact renderer field, "
        "or other implementation-defining component needs an explicit substitute."
    ),
    "partial": (
        "Useful contract evidence is present, but final required components have not all been "
        "reviewed or remain unresolved. Coarse 25-field audit parents never promote beyond this state."
    ),
    "conflicting_evidence": "Tracked sources or reported quantities conflict and require resolution.",
    "low_confidence": "Only automated or explicitly low-confidence candidate evidence is available.",
    "explicitly_absent": (
        "The publication explicitly reports that this conditional control family or feature was absent."
    ),
    "not_reported": (
        "The required value was not found after the tracked review attempts; protocol lineage or an "
        "explicit approximation is needed."
    ),
    "source_unavailable": "No inspectable source evidence currently supports a contract-level decision.",
    "not_assessed": "The publication/study has no exact joined audit evidence for this contract.",
    "not_applicable": "The reviewed evidence marks the contract as not applicable to this study.",
    "composite_requires_split": (
        "Evidence exists only for a combined multi-experiment record and must not be copied to an "
        "individual experiment row before disaggregation."
    ),
    "mixed_across_studies": "The publication's registered study rows have different statuses.",
}

STATUS_ACTIONS = {
    "reported_complete": "verify_current_toolkit_mapping_or_approve_adapter",
    "derived_complete": "verify_derivation_and_current_toolkit_mapping",
    "approximation_required": "choose_and_document_approved_substitute",
    "partial": "extract_missing_required_components",
    "conflicting_evidence": "resolve_source_or_arithmetic_conflict",
    "low_confidence": "verify_candidate_against_primary_source",
    "explicitly_absent": "confirm_absence_is_experiment_scoped",
    "not_reported": "check_protocol_lineage_or_choose_documented_approximation",
    "source_unavailable": "acquire_or_open_source",
    "not_assessed": "create_publication_audit",
    "not_applicable": "no_action_unless_scope_changes",
    "composite_requires_split": "disaggregate_record_by_experiment",
    "mixed_across_studies": "review_each_registered_study_row",
}

STATUS_PRIORITY = {
    "composite_requires_split": 100,
    "conflicting_evidence": 98,
    "partial": 90,
    "not_reported": 85,
    "source_unavailable": 75,
    "not_assessed": 70,
    "low_confidence": 65,
    "approximation_required": 55,
    "derived_complete": 35,
    "reported_complete": 20,
    "explicitly_absent": 10,
    "not_applicable": 0,
}

LEGACY_SOURCE_STATUSES = {
    "available_reported",
    "available_with_derivation",
    "available_caveated",
    "missing_after_review",
}
SOURCE_COMPONENT_STATUSES = {
    "reported",
    "derived",
    "approximation_required",
    "not_reported",
    "source_unavailable",
    "explicitly_absent",
    "not_applicable",
    "conflicting_evidence",
    "low_confidence",
}
SATISFIED_COMPONENT_STATUSES = {
    "reported",
    "derived",
    "explicitly_absent",
    "not_applicable",
}

SOURCE_KEYS_BY_CONTRACT = {
    "auditory_stimulus": ["auditory_stimulus", "stimulus_contract"],
    "trajectory_kinematics": [
        "trajectory_kinematics",
        "trajectory_geometry",
        "looming_duration_kinematics",
    ],
    "trial_sequence": ["trial_sequence"],
    "task_response": ["task_response", "trial_sequence_response"],
    "jitter_iti_policy": ["jitter_iti_policy"],
    "soa_schedule": ["soa_schedule"],
    "tactile_target": ["tactile_target"],
    "baseline_trial_contract": ["baseline_trial_contract", "baseline_contract"],
    "catch_trial_contract": ["catch_trial_contract", "catch_contract"],
    "repetition_allocation": ["repetition_allocation"],
    "block_order_contract": ["block_order_contract", "block_allocation"],
}

STRUCTURE_ENTRY_STATUSES = {
    "reported_complete",
    "derived_complete",
    "partial",
    "conflicting_evidence",
}
MEASUREMENT_ENTRY_STATUSES = {
    *STRUCTURE_ENTRY_STATUSES,
    "not_applicable",
}
STRUCTURE_COMPONENT_STATUSES = {
    "reported",
    "derived",
    "partial",
    "conflicting_evidence",
    "not_reported",
    "not_assessed",
    "not_applicable",
}
STRUCTURE_ENUM_FIELDS = {
    "design_family": "study_design_family",
    "assignment_scope": "study_assignment_scope",
    "pps_occurrence_pattern": "pps_occurrence_pattern",
}
FACTOR_ENUM_FIELDS = {
    "role": "study_factor_role",
    "scope": "study_factor_scope",
    "assignment_method": "study_assignment_method",
}
EVENT_ENUM_FIELDS = {
    "event_kind": "study_schedule_event_kind",
    "execution_mode": "study_schedule_execution_mode",
    "relation": "study_schedule_relation",
}
MEASUREMENT_ENUM_FIELDS = {
    "outcome_family": "measurement_outcome_family",
    "binding_mode": "measurement_binding_mode",
    "clock_sync_method": "measurement_clock_sync_method",
}


def _normalize_source_status(status: str, value: str = "") -> str:
    if status in STATUS_LEGEND and status != "mixed_across_studies":
        return status
    if status == "available_reported":
        return "reported_complete"
    if status == "available_with_derivation":
        return "derived_complete"
    if status == "available_caveated":
        text = value.lower()
        if any(token in text for token in ("conflict", "disagree", "inconsisten")):
            return "conflicting_evidence"
        return "approximation_required"
    if status == "missing_after_review":
        return "not_reported"
    raise RuntimeError(f"Unknown source-review status: {status}")


def _source_override_for_contract(
    study_row_id: str,
    contract: dict[str, Any],
    source_reviews: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any] | None:
    key = contract["column_key"]
    direct = source_reviews.get((study_row_id, key))
    if direct:
        result = dict(direct)
        result["status"] = _normalize_source_status(
            str(result.get("status") or ""), str(result.get("value") or "")
        )
        result["source_review_keys"] = key
        return result

    candidate_keys = SOURCE_KEYS_BY_CONTRACT.get(key, [])

    if key == "trajectory_kinematics":
        parts = [
            (legacy_key, source_reviews[(study_row_id, legacy_key)])
            for legacy_key in ("trajectory_geometry", "looming_duration_kinematics")
            if (study_row_id, legacy_key) in source_reviews
        ]
        if not parts:
            return None
        statuses = [
            _normalize_source_status(str(review.get("status") or ""), str(review.get("value") or ""))
            for _, review in parts
        ]
        if all(item == "not_applicable" for item in statuses) and len(parts) == 2:
            status = "not_applicable"
        elif "conflicting_evidence" in statuses:
            status = "conflicting_evidence"
        elif "low_confidence" in statuses:
            status = "low_confidence"
        elif len(parts) < 2 or any(
            item in {"partial", "not_reported", "source_unavailable", "not_assessed"}
            for item in statuses
        ):
            status = "partial"
        elif "approximation_required" in statuses:
            status = "approximation_required"
        elif "derived_complete" in statuses:
            status = "derived_complete"
        else:
            status = "reported_complete"
        return {
            "status": status,
            "value": " | ".join(
                f"{_title(legacy_key)}: {review.get('value', '')}" for legacy_key, review in parts
            ),
            "page_or_section": _unique_text(
                review.get("page_or_section", "") for _, review in parts
            ),
            "evidence_note": _unique_text(
                review.get("evidence_note", "") for _, review in parts
            ),
            "derivation_note": _unique_text(
                review.get("derivation_note", "") for _, review in parts
            ),
            "component_reviews": _merge_component_reviews(
                review.get("component_reviews", {}) for _, review in parts
            ),
            "source_review_keys": " | ".join(legacy_key for legacy_key, _ in parts),
        }

    for legacy_key in candidate_keys:
        review = source_reviews.get((study_row_id, legacy_key))
        if review:
            result = dict(review)
            result["status"] = _normalize_source_status(
                str(result.get("status") or ""), str(result.get("value") or "")
            )
            result["source_review_keys"] = legacy_key
            return result

    # The prior compact source review bundled sequence and response. Preserve
    # its experiment-scoped prose for both projections; the final-component
    # resolver below prevents either projection from being overpromoted.
    if key == "trial_sequence":
        legacy = source_reviews.get((study_row_id, "trial_sequence_response"))
        if legacy:
            normalized = _normalize_source_status(
                str(legacy.get("status") or ""), str(legacy.get("value") or "")
            )
            return {
                **legacy,
                "status": normalized,
                "source_review_keys": "trial_sequence_response (legacy projection)",
            }
    return None


def _merge_component_reviews(
    review_groups: Iterable[Any],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw_group in review_groups:
        if not isinstance(raw_group, dict):
            continue
        for component_key, raw_review in raw_group.items():
            review = dict(raw_review or {})
            prior = merged.get(component_key)
            if prior is None or prior == review:
                merged[component_key] = review
                continue
            merged[component_key] = {
                "status": "conflicting_evidence",
                "value": _unique_text(
                    (prior.get("value", ""), review.get("value", ""))
                ),
                "evidence_note": _unique_text(
                    (
                        prior.get("evidence_note", ""),
                        review.get("evidence_note", ""),
                        "Different legacy source-review components were merged.",
                    )
                ),
            }
    return merged


def _contract_component_keys(contract: dict[str, Any]) -> list[str]:
    return [
        *contract["required_components"],
        *contract.get("conditional_components", []),
    ]


def _project_component_reviews(
    contract: dict[str, Any], source_override: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    raw_reviews = source_override.get("component_reviews", {})
    if not isinstance(raw_reviews, dict):
        return {}
    return {
        key: dict(raw_reviews[key])
        for key in _contract_component_keys(contract)
        if key in raw_reviews
    }


def _finalize_source_override(
    contract: dict[str, Any], source_override: dict[str, Any]
) -> dict[str, Any]:
    result = dict(source_override)
    top_status = str(result.get("status") or "")
    value = str(result.get("value") or "")
    component_reviews = _project_component_reviews(contract, result)
    result["component_reviews"] = component_reviews

    # An explicit passive/no-response policy satisfies the response-mode
    # branch; it is not an absent task/response contract.
    if contract["column_key"] == "task_response" and top_status == "explicitly_absent":
        if re.search(r"\b(?:passive|task[- ]?free|no[- ]response)\b", value, re.I):
            top_status = "reported_complete"
        else:
            top_status = "partial"
    elif (
        top_status == "explicitly_absent"
        and contract["completion_rule"] != "control_family_dependency"
    ):
        top_status = "partial"

    # Legacy contract prose remains useful evidence, but only atomic final
    # components can certify one of the resolved states.
    if not component_reviews:
        if top_status in RESOLVED_EVIDENCE_STATUSES:
            top_status = "partial"
        result["status"] = top_status
        return result

    required_keys = list(contract["required_components"])
    required_reviews = {
        key: component_reviews[key]
        for key in required_keys
        if key in component_reviews
    }
    required_statuses = [
        str(required_reviews[key].get("status") or "") for key in required_reviews
    ]
    reviewed_statuses = [
        str(review.get("status") or "") for review in component_reviews.values()
    ]
    missing_required = [key for key in required_keys if key not in required_reviews]
    unsatisfied_required = [
        key
        for key, review in required_reviews.items()
        if str(review.get("status") or "") not in SATISFIED_COMPONENT_STATUSES
    ]

    if top_status == "conflicting_evidence" or "conflicting_evidence" in reviewed_statuses:
        final_status = "conflicting_evidence"
    elif top_status == "approximation_required" or "approximation_required" in reviewed_statuses:
        final_status = "approximation_required"
    elif missing_required or unsatisfied_required:
        satisfied_count = sum(
            status in SATISFIED_COMPONENT_STATUSES for status in required_statuses
        )
        if satisfied_count:
            final_status = "partial"
        elif required_statuses and all(status == "not_reported" for status in required_statuses):
            final_status = "not_reported"
        elif required_statuses and all(
            status == "source_unavailable" for status in required_statuses
        ):
            final_status = "source_unavailable"
        elif required_statuses and all(status == "low_confidence" for status in required_statuses):
            final_status = "low_confidence"
        else:
            final_status = "partial"
    elif top_status in {
        "partial",
        "not_reported",
        "source_unavailable",
        "not_assessed",
        "low_confidence",
    }:
        # Structured components may clarify why a prior review was partial,
        # but they do not silently overrule an unresolved contract decision.
        final_status = top_status
    else:
        family_review = component_reviews.get("family_or_explicit_none", {})
        family_status = str(family_review.get("status") or "")
        if (
            contract["completion_rule"] == "control_family_dependency"
            and (top_status == "explicitly_absent" or family_status == "explicitly_absent")
        ):
            final_status = "explicitly_absent"
        elif all(status == "not_applicable" for status in required_statuses):
            final_status = "not_applicable"
        elif top_status == "not_applicable":
            final_status = "partial"
        elif top_status == "derived_complete" or "derived" in required_statuses:
            final_status = "derived_complete"
        else:
            final_status = "reported_complete"

    result["status"] = final_status
    return result


def _source_missing_components(
    contract: dict[str, Any],
    status: str,
    source_override: dict[str, Any],
) -> list[str]:
    if "missing_required_components" in source_override:
        raw_missing = source_override["missing_required_components"]
        return (
            [str(value) for value in raw_missing]
            if isinstance(raw_missing, list)
            else [str(raw_missing)]
        )
    if status in RESOLVED_EVIDENCE_STATUSES:
        return []
    component_reviews = source_override.get("component_reviews", {})
    if isinstance(component_reviews, dict) and component_reviews:
        missing: list[str] = []
        for component_key in contract["required_components"]:
            review = component_reviews.get(component_key)
            component_status = str((review or {}).get("status") or "")
            if component_status not in SATISFIED_COMPONENT_STATUSES:
                missing.append(component_key)
        for component_key in _contract_component_keys(contract):
            review = component_reviews.get(component_key)
            component_status = str((review or {}).get("status") or "")
            if component_status in {
                "approximation_required",
                "conflicting_evidence",
                "low_confidence",
            } and component_key not in missing:
                missing.append(component_key)
        if missing:
            return missing
    if status in {"partial", "approximation_required"}:
        return list(
            contract.get("partial_missing_components")
            or contract["required_components"]
        )
    return list(contract["required_components"])


def _validate_source_override(
    study_row_id: str,
    contract: dict[str, Any],
    source_override: dict[str, Any],
) -> None:
    key = contract["column_key"]
    status = str(source_override.get("status") or "")
    value = str(source_override.get("value") or "").strip()
    if status not in STATUS_LEGEND or status == "mixed_across_studies":
        raise RuntimeError(
            f"Unknown normalized source-review status {status} on {study_row_id}/{key}"
        )
    if status in SOURCE_VALUE_REQUIRED_STATUSES and not value:
        raise RuntimeError(
            f"Source-review status {status} requires a value: {study_row_id}/{key}"
        )
    if status == "derived_complete" and not str(
        source_override.get("derivation_note") or ""
    ).strip():
        raise RuntimeError(
            f"Derived source-review status requires a derivation note: {study_row_id}/{key}"
        )
    if (
        status == "explicitly_absent"
        and contract["completion_rule"] != "control_family_dependency"
    ):
        raise RuntimeError(
            "Explicit absence is only a resolved final-contract state for a conditional "
            f"control family: {study_row_id}/{key}"
        )


def _validate_source_component_reviews(
    study_row_id: str,
    source_key: str,
    review: dict[str, Any],
    contracts: list[dict[str, Any]],
) -> None:
    raw_components = review.get("component_reviews")
    if raw_components is None:
        return
    if not isinstance(raw_components, dict):
        raise RuntimeError(
            f"component_reviews must be an object: {study_row_id}/{source_key}"
        )

    target_contracts = [
        contract
        for contract in contracts
        if source_key in SOURCE_KEYS_BY_CONTRACT.get(contract["column_key"], [])
        or (
            source_key == "trial_sequence_response"
            and contract["column_key"] == "trial_sequence"
        )
    ]
    allowed_components = {
        component_key
        for contract in target_contracts
        for component_key in _contract_component_keys(contract)
    }
    unknown = sorted(set(raw_components) - allowed_components)
    if unknown:
        raise RuntimeError(
            f"Unknown final component(s) on {study_row_id}/{source_key}: "
            + ", ".join(unknown)
        )

    for component_key, component_review in raw_components.items():
        if not isinstance(component_review, dict):
            raise RuntimeError(
                f"Component review must be an object: "
                f"{study_row_id}/{source_key}/{component_key}"
            )
        status = str(component_review.get("status") or "")
        if status not in SOURCE_COMPONENT_STATUSES:
            raise RuntimeError(
                f"Unknown component status {status}: "
                f"{study_row_id}/{source_key}/{component_key}"
            )
        value = component_review.get("value")
        if status in {
            "reported",
            "derived",
            "approximation_required",
            "explicitly_absent",
            "conflicting_evidence",
            "low_confidence",
        } and value in (None, "", [], {}):
            raise RuntimeError(
                f"Component status {status} requires a value: "
                f"{study_row_id}/{source_key}/{component_key}"
            )
        if status == "explicitly_absent" and component_key != "family_or_explicit_none":
            raise RuntimeError(
                "explicitly_absent is only valid for family_or_explicit_none: "
                f"{study_row_id}/{source_key}/{component_key}"
            )


def _json_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _require_identifier(value: Any, *, context: str) -> str:
    identifier = str(value or "").strip()
    if not identifier:
        raise RuntimeError(f"Blank identifier: {context}")
    return identifier


def _validate_enum_value(
    container: dict[str, Any],
    field: str,
    vocabulary_name: str,
    controlled_vocabularies: dict[str, dict[str, str]],
    *,
    context: str,
    required: bool,
) -> str:
    value = str(container.get(field) or "").strip()
    if not value:
        if required:
            raise RuntimeError(f"Missing {field}: {context}")
        return ""
    vocabulary = controlled_vocabularies.get(vocabulary_name)
    if not isinstance(vocabulary, dict):
        raise RuntimeError(f"Missing controlled vocabulary: {vocabulary_name}")
    if value not in vocabulary:
        raise RuntimeError(
            f"Unknown {field} {value!r} on {context}; expected {vocabulary_name}"
        )
    return value


def _validate_optional_count(container: dict[str, Any], field: str, *, context: str) -> None:
    value = container.get(field)
    if value in (None, ""):
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{field} must be a non-negative integer: {context}")
    if value < 0 or int(value) != value:
        raise RuntimeError(f"{field} must be a non-negative integer: {context}")


def _normalize_id_list(value: Any, *, context: str) -> list[str]:
    if value in (None, "", []):
        return []
    raw_values = value if isinstance(value, list) else [value]
    identifiers = [
        _require_identifier(item, context=f"{context}[{index}]")
        for index, item in enumerate(raw_values)
    ]
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError(f"Duplicate identifier reference: {context}")
    return identifiers


def _normalize_factor_level_bindings(
    value: Any,
    *,
    context: str,
) -> dict[str, str]:
    if value in (None, "", [], {}):
        return {}
    if isinstance(value, dict):
        bindings = {
            _require_identifier(factor_id, context=f"{context}/factor_id"):
            _require_identifier(level_id, context=f"{context}/{factor_id}")
            for factor_id, level_id in value.items()
        }
    elif isinstance(value, list):
        bindings = {}
        for index, raw_binding in enumerate(value):
            if not isinstance(raw_binding, dict):
                raise RuntimeError(f"Factor binding must be an object: {context}[{index}]")
            factor_id = _require_identifier(
                raw_binding.get("factor_id"), context=f"{context}[{index}]/factor_id"
            )
            level_id = _require_identifier(
                raw_binding.get("level_id"), context=f"{context}[{index}]/level_id"
            )
            if factor_id in bindings:
                raise RuntimeError(f"Duplicate factor binding: {context}/{factor_id}")
            bindings[factor_id] = level_id
    else:
        raise RuntimeError(f"factor_level_bindings must be an object or list: {context}")
    return bindings


def _structure_value_summary(entry: dict[str, Any]) -> str:
    explicit = _json_text(entry.get("value"))
    if explicit:
        return explicit
    normalized = entry.get("normalized_structure") or {}
    parts = [
        f"{_title(field)}: {_json_text(normalized.get(field))}"
        for field in STRUCTURE_ENUM_FIELDS
        if _json_text(normalized.get(field))
    ]
    if parts:
        return " | ".join(parts)
    component_reviews = entry.get("component_reviews") or {}
    component_values = [
        f"{_title(component)}: {_json_text(review.get('value'))}"
        for component, review in component_reviews.items()
        if isinstance(review, dict) and _json_text(review.get("value"))
    ]
    if component_values:
        return " | ".join(component_values)
    component_statuses = [
        f"{component}={str(review.get('status') or '').strip()}"
        for component, review in component_reviews.items()
        if isinstance(review, dict) and str(review.get("status") or "").strip()
    ]
    return "Component review states: " + ", ".join(component_statuses)


def _structure_source_override(entry: dict[str, Any]) -> dict[str, Any]:
    component_reviews = entry.get("component_reviews") or {}
    component_derivations = _unique_text(
        review.get("derivation_note", "")
        for review in component_reviews.values()
        if isinstance(review, dict)
    )
    return {
        "status": str(entry.get("status") or ""),
        "value": _structure_value_summary(entry),
        "page_or_section": str(entry.get("page_or_section") or ""),
        "evidence_note": str(entry.get("evidence_note") or ""),
        "derivation_note": _unique_text(
            (entry.get("derivation_note", ""), component_derivations)
        ),
        "component_reviews": component_reviews,
        "source_review_keys": "study_structure_reviews.v1",
    }


def _load_structure_reviews(
    *,
    valid_study_row_ids: set[str],
    contract: dict[str, Any],
    controlled_vocabularies: dict[str, dict[str, str]],
) -> tuple[str, dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    if not STRUCTURE_REVIEW_PATH.exists():
        return "", {}, {}
    document = json.loads(STRUCTURE_REVIEW_PATH.read_text(encoding="utf-8"))
    if document.get("schema") != "pps-study-structure-reviews.v1":
        raise RuntimeError("Unexpected study-structure review schema")
    document_review_date = str(document.get("review_date") or "").strip()
    raw_entries = document.get("entries", [])
    if not isinstance(raw_entries, list):
        raise RuntimeError("Study-structure review entries must be a list")

    required_components = set(contract["required_components"])
    allowed_components = set(_contract_component_keys(contract))
    entries: dict[str, dict[str, Any]] = {}
    overrides: dict[tuple[str, str], dict[str, Any]] = {}
    for entry_index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            raise RuntimeError(f"Study-structure entry must be an object: entries[{entry_index}]")
        study_row_id = _require_identifier(
            entry.get("study_row_id"), context=f"entries[{entry_index}]/study_row_id"
        )
        if study_row_id in entries:
            raise RuntimeError(f"Duplicate study-structure review row: {study_row_id}")
        if study_row_id not in valid_study_row_ids:
            raise RuntimeError(f"Unknown study-structure review row: {study_row_id}")
        status = str(entry.get("status") or "").strip()
        if status not in STRUCTURE_ENTRY_STATUSES:
            raise RuntimeError(
                f"Unknown study-structure entry status {status}: {study_row_id}"
            )
        for provenance_field in ("source_type", "source_file", "page_or_section"):
            if not str(entry.get(provenance_field) or "").strip():
                raise RuntimeError(
                    f"Study-structure review lacks {provenance_field}: {study_row_id}"
                )
        if not str(entry.get("review_date") or document_review_date).strip():
            raise RuntimeError(f"Study-structure review lacks review_date: {study_row_id}")

        component_reviews = entry.get("component_reviews")
        if not isinstance(component_reviews, dict):
            raise RuntimeError(f"component_reviews must be an object: {study_row_id}")
        unknown_components = sorted(set(component_reviews) - allowed_components)
        if unknown_components:
            raise RuntimeError(
                f"Unknown study-structure component(s) on {study_row_id}: "
                + ", ".join(unknown_components)
            )
        missing_component_reviews = sorted(required_components - set(component_reviews))
        if missing_component_reviews:
            raise RuntimeError(
                f"Missing required study-structure component review(s) on {study_row_id}: "
                + ", ".join(missing_component_reviews)
            )
        for component_key, component_review in component_reviews.items():
            if not isinstance(component_review, dict):
                raise RuntimeError(
                    f"Component review must be an object: {study_row_id}/{component_key}"
                )
            component_status = str(component_review.get("status") or "").strip()
            if component_status not in STRUCTURE_COMPONENT_STATUSES:
                raise RuntimeError(
                    f"Unknown study-structure component status {component_status}: "
                    f"{study_row_id}/{component_key}"
                )
            if component_status in {
                "reported",
                "derived",
                "partial",
                "conflicting_evidence",
            } and component_review.get("value") in (None, "", [], {}):
                raise RuntimeError(
                    f"Component status {component_status} requires a value: "
                    f"{study_row_id}/{component_key}"
                )
            if component_status == "derived" and not str(
                component_review.get("derivation_note")
                or entry.get("derivation_note")
                or ""
            ).strip():
                raise RuntimeError(
                    f"Derived component requires a derivation note: "
                    f"{study_row_id}/{component_key}"
                )

        normalized = entry.get("normalized_structure") or {}
        if not isinstance(normalized, dict):
            raise RuntimeError(f"normalized_structure must be an object: {study_row_id}")
        sample_and_assignment = normalized.get("sample_and_assignment")
        if sample_and_assignment not in (None, ""):
            if not isinstance(sample_and_assignment, dict):
                raise RuntimeError(
                    f"normalized_structure.sample_and_assignment must be an object: {study_row_id}"
                )
            for count_field in (
                "planned_n",
                "analyzed_n",
                "planned_sample_n",
                "analyzed_sample_n",
                "cohort_or_arm_count",
                "arm_count",
                "cohort_count",
            ):
                _validate_optional_count(
                    sample_and_assignment,
                    count_field,
                    context=f"{study_row_id}/normalized_structure/sample_and_assignment",
                )
            per_arm = _first_present(
                sample_and_assignment,
                (
                    "per_arm_n",
                    "per_arm_sample",
                    "arm_sample_sizes",
                    "cohort_sample_sizes",
                ),
            )
            if per_arm not in (None, "", {}):
                if not isinstance(per_arm, dict):
                    raise RuntimeError(
                        f"Per-arm sample values must be an object: {study_row_id}"
                    )
                for arm_id, arm_sample in per_arm.items():
                    _require_identifier(
                        arm_id,
                        context=f"{study_row_id}/sample_and_assignment/per_arm_n",
                    )
                    if isinstance(arm_sample, dict):
                        for count_field in ("planned_n", "analyzed_n"):
                            _validate_optional_count(
                                arm_sample,
                                count_field,
                                context=f"{study_row_id}/sample_and_assignment/{arm_id}",
                            )
                    else:
                        _validate_optional_count(
                            {"n": arm_sample},
                            "n",
                            context=f"{study_row_id}/sample_and_assignment/{arm_id}",
                        )
        complete = status in {"reported_complete", "derived_complete"}
        for field, vocabulary_name in STRUCTURE_ENUM_FIELDS.items():
            _validate_enum_value(
                normalized,
                field,
                vocabulary_name,
                controlled_vocabularies,
                context=f"{study_row_id}/normalized_structure",
                required=complete,
            )

        factors = entry.get("factors", [])
        if not isinstance(factors, list):
            raise RuntimeError(f"factors must be a list: {study_row_id}")
        factor_levels: dict[str, set[str]] = {}
        for factor_index, factor in enumerate(factors):
            context = f"{study_row_id}/factors[{factor_index}]"
            if not isinstance(factor, dict):
                raise RuntimeError(f"Factor must be an object: {context}")
            factor_id = _require_identifier(factor.get("factor_id"), context=f"{context}/factor_id")
            if factor_id in factor_levels:
                raise RuntimeError(f"Duplicate factor_id {factor_id}: {study_row_id}")
            for field, vocabulary_name in FACTOR_ENUM_FIELDS.items():
                _validate_enum_value(
                    factor,
                    field,
                    vocabulary_name,
                    controlled_vocabularies,
                    context=context,
                    required=True,
                )
            levels = factor.get("levels", [])
            if not isinstance(levels, list):
                raise RuntimeError(f"levels must be a list: {context}")
            level_ids: set[str] = set()
            for level_index, level in enumerate(levels):
                level_context = f"{context}/levels[{level_index}]"
                if not isinstance(level, dict):
                    raise RuntimeError(f"Factor level must be an object: {level_context}")
                level_id = _require_identifier(
                    level.get("level_id"), context=f"{level_context}/level_id"
                )
                if level_id in level_ids:
                    raise RuntimeError(
                        f"Duplicate level_id {level_id}: {study_row_id}/{factor_id}"
                    )
                level_ids.add(level_id)
                _validate_optional_count(level, "planned_n", context=level_context)
                _validate_optional_count(level, "analyzed_n", context=level_context)
            factor_levels[factor_id] = level_ids

        events = entry.get("events", [])
        if not isinstance(events, list):
            raise RuntimeError(f"events must be a list: {study_row_id}")
        event_ids: set[str] = set()
        occurrence_ids: set[str] = set()
        for event_index, event in enumerate(events):
            context = f"{study_row_id}/events[{event_index}]"
            if not isinstance(event, dict):
                raise RuntimeError(f"Event must be an object: {context}")
            event_id = _require_identifier(event.get("event_id"), context=f"{context}/event_id")
            if event_id in event_ids:
                raise RuntimeError(f"Duplicate event_id {event_id}: {study_row_id}")
            event_ids.add(event_id)
            for field, vocabulary_name in EVENT_ENUM_FIELDS.items():
                _validate_enum_value(
                    event,
                    field,
                    vocabulary_name,
                    controlled_vocabularies,
                    context=context,
                    required=True,
                )
            _validate_optional_count(event, "order_index", context=context)
            _validate_optional_count(event, "repeat_count", context=context)
            duration_s = event.get("duration_s")
            if duration_s not in (None, "") and (
                isinstance(duration_s, bool)
                or not isinstance(duration_s, (int, float))
                or duration_s < 0
            ):
                raise RuntimeError(f"duration_s must be non-negative: {context}")
            occurrence_id = str(event.get("pps_occurrence_id") or "").strip()
            if occurrence_id:
                if occurrence_id in occurrence_ids:
                    raise RuntimeError(
                        f"Duplicate pps_occurrence_id {occurrence_id}: {study_row_id}"
                    )
                occurrence_ids.add(occurrence_id)
            if event.get("parameter_overrides") not in (None, "", {}) and not isinstance(
                event.get("parameter_overrides"), dict
            ):
                raise RuntimeError(f"parameter_overrides must be an object: {context}")

        for event_index, event in enumerate(events):
            context = f"{study_row_id}/events[{event_index}]"
            event_id = str(event["event_id"]).strip()
            relative_to = str(event.get("relative_to_event_id") or "").strip()
            if relative_to:
                if relative_to not in event_ids:
                    raise RuntimeError(
                        f"Unknown relative_to_event_id {relative_to}: {context}"
                    )
                if relative_to == event_id:
                    raise RuntimeError(f"Event cannot reference itself: {context}")
            for reference_field in ("predecessor_event_ids", "concurrent_event_ids"):
                for reference_id in _normalize_id_list(
                    event.get(reference_field), context=f"{context}/{reference_field}"
                ):
                    if reference_id not in event_ids:
                        raise RuntimeError(
                            f"Unknown {reference_field} reference {reference_id}: {context}"
                        )
                    if reference_id == event_id:
                        raise RuntimeError(f"Event cannot reference itself: {context}")
            bindings = _normalize_factor_level_bindings(
                event.get("factor_level_bindings"),
                context=f"{context}/factor_level_bindings",
            )
            for factor_id, level_id in bindings.items():
                if factor_id not in factor_levels:
                    raise RuntimeError(
                        f"Unknown factor binding {factor_id}: {context}"
                    )
                if level_id not in factor_levels[factor_id]:
                    raise RuntimeError(
                        f"Unknown factor level binding {factor_id}/{level_id}: {context}"
                    )

        override = _structure_source_override(entry)
        finalized = _finalize_source_override(contract, override)
        _validate_source_override(study_row_id, contract, finalized)
        entries[study_row_id] = entry
        overrides[(study_row_id, STRUCTURE_CONTRACT_KEY)] = finalized
    return document_review_date, entries, overrides


def _measurement_value_summary(entry: dict[str, Any]) -> str:
    explicit = _json_text(entry.get("value"))
    if explicit:
        return explicit
    acquisitions = entry.get("acquisitions") or []
    parts = []
    for acquisition in acquisitions:
        acquisition_id = str(acquisition.get("acquisition_id") or "").strip()
        family = str(acquisition.get("outcome_family") or "").strip()
        measure = _json_text(acquisition.get("primary_measure"))
        binding = str(acquisition.get("binding_mode") or "").strip()
        details = ", ".join(value for value in (family, measure, binding) if value)
        if details:
            parts.append(f"{acquisition_id}: {details}")
    if parts:
        return " | ".join(parts)
    component_reviews = entry.get("component_reviews") or {}
    component_values = [
        f"{_title(component)}: {_json_text(review.get('value'))}"
        for component, review in component_reviews.items()
        if isinstance(review, dict) and _json_text(review.get("value"))
    ]
    if component_values:
        return " | ".join(component_values)
    component_statuses = [
        f"{component}={str(review.get('status') or '').strip()}"
        for component, review in component_reviews.items()
        if isinstance(review, dict) and str(review.get("status") or "").strip()
    ]
    return "Component review states: " + ", ".join(component_statuses)


def _measurement_source_override(entry: dict[str, Any]) -> dict[str, Any]:
    component_reviews = entry.get("component_reviews") or {}
    component_derivations = _unique_text(
        review.get("derivation_note", "")
        for review in component_reviews.values()
        if isinstance(review, dict)
    )
    return {
        "status": str(entry.get("status") or ""),
        "value": _measurement_value_summary(entry),
        "page_or_section": str(entry.get("page_or_section") or ""),
        "evidence_note": str(entry.get("evidence_note") or ""),
        "derivation_note": _unique_text(
            (entry.get("derivation_note", ""), component_derivations)
        ),
        "component_reviews": component_reviews,
        "source_review_keys": "measurement_acquisition_reviews.v1",
    }


def _load_measurement_reviews(
    *,
    valid_study_row_ids: set[str],
    contract: dict[str, Any],
    controlled_vocabularies: dict[str, dict[str, str]],
) -> tuple[str, dict[str, dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    if not MEASUREMENT_REVIEW_PATH.exists():
        return "", {}, {}
    document = json.loads(MEASUREMENT_REVIEW_PATH.read_text(encoding="utf-8"))
    if document.get("schema") != "pps-measurement-acquisition-reviews.v1":
        raise RuntimeError("Unexpected measurement-acquisition review schema")
    document_review_date = str(document.get("review_date") or "").strip()
    raw_entries = document.get("entries", [])
    if not isinstance(raw_entries, list):
        raise RuntimeError("Measurement-acquisition review entries must be a list")

    required_components = set(contract["required_components"])
    allowed_components = set(_contract_component_keys(contract))
    entries: dict[str, dict[str, Any]] = {}
    overrides: dict[tuple[str, str], dict[str, Any]] = {}
    forbidden_analysis_fields = {
        "analysis",
        "analysis_model",
        "statistical_model",
        "model_fitting",
        "inferential_model",
    }
    for entry_index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            raise RuntimeError(
                f"Measurement-acquisition entry must be an object: entries[{entry_index}]"
            )
        study_row_id = _require_identifier(
            entry.get("study_row_id"), context=f"entries[{entry_index}]/study_row_id"
        )
        if study_row_id in entries:
            raise RuntimeError(f"Duplicate measurement-acquisition review row: {study_row_id}")
        if study_row_id not in valid_study_row_ids:
            raise RuntimeError(f"Unknown measurement-acquisition review row: {study_row_id}")
        status = str(entry.get("status") or "").strip()
        if status not in MEASUREMENT_ENTRY_STATUSES:
            raise RuntimeError(
                f"Unknown measurement-acquisition entry status {status}: {study_row_id}"
            )
        for provenance_field in ("source_type", "source_file", "page_or_section"):
            if not str(entry.get(provenance_field) or "").strip():
                raise RuntimeError(
                    f"Measurement-acquisition review lacks {provenance_field}: {study_row_id}"
                )
        if not str(entry.get("review_date") or document_review_date).strip():
            raise RuntimeError(
                f"Measurement-acquisition review lacks review_date: {study_row_id}"
            )

        component_reviews = entry.get("component_reviews")
        if not isinstance(component_reviews, dict):
            raise RuntimeError(f"component_reviews must be an object: {study_row_id}")
        unknown_components = sorted(set(component_reviews) - allowed_components)
        if unknown_components:
            raise RuntimeError(
                f"Unknown measurement-acquisition component(s) on {study_row_id}: "
                + ", ".join(unknown_components)
            )
        missing_components = sorted(required_components - set(component_reviews))
        if missing_components:
            raise RuntimeError(
                f"Missing required measurement-acquisition component review(s) on {study_row_id}: "
                + ", ".join(missing_components)
            )
        for component_key, component_review in component_reviews.items():
            if not isinstance(component_review, dict):
                raise RuntimeError(
                    f"Component review must be an object: {study_row_id}/{component_key}"
                )
            component_status = str(component_review.get("status") or "").strip()
            if component_status not in STRUCTURE_COMPONENT_STATUSES:
                raise RuntimeError(
                    f"Unknown measurement-acquisition component status {component_status}: "
                    f"{study_row_id}/{component_key}"
                )
            if component_status in {
                "reported",
                "derived",
                "partial",
                "conflicting_evidence",
            } and component_review.get("value") in (None, "", [], {}):
                raise RuntimeError(
                    f"Component status {component_status} requires a value: "
                    f"{study_row_id}/{component_key}"
                )
            if component_status == "derived" and not str(
                component_review.get("derivation_note")
                or entry.get("derivation_note")
                or ""
            ).strip():
                raise RuntimeError(
                    f"Derived component requires a derivation note: "
                    f"{study_row_id}/{component_key}"
                )

        acquisitions = entry.get("acquisitions", [])
        if not isinstance(acquisitions, list):
            raise RuntimeError(f"acquisitions must be a list: {study_row_id}")
        if status == "not_applicable":
            non_na_required = sorted(
                component_key
                for component_key in required_components
                if str(component_reviews[component_key].get("status") or "")
                != "not_applicable"
            )
            if non_na_required:
                raise RuntimeError(
                    f"A not_applicable measurement review requires all required components "
                    f"to be not_applicable on {study_row_id}: "
                    + ", ".join(non_na_required)
                )
            if acquisitions:
                raise RuntimeError(
                    f"A not_applicable measurement review cannot contain acquisitions: {study_row_id}"
                )
        if status in {"reported_complete", "derived_complete"} and not acquisitions:
            raise RuntimeError(
                f"Complete measurement-acquisition review needs an acquisition row: {study_row_id}"
            )
        acquisition_ids: set[str] = set()
        for acquisition_index, acquisition in enumerate(acquisitions):
            context = f"{study_row_id}/acquisitions[{acquisition_index}]"
            if not isinstance(acquisition, dict):
                raise RuntimeError(f"Acquisition must be an object: {context}")
            forbidden = sorted(set(acquisition) & forbidden_analysis_fields)
            if forbidden:
                raise RuntimeError(
                    f"Analysis/model fields are outside the acquisition contract on {context}: "
                    + ", ".join(forbidden)
                )
            acquisition_id = _require_identifier(
                acquisition.get("acquisition_id"), context=f"{context}/acquisition_id"
            )
            if acquisition_id in acquisition_ids:
                raise RuntimeError(
                    f"Duplicate acquisition_id {acquisition_id}: {study_row_id}"
                )
            acquisition_ids.add(acquisition_id)
            for field, vocabulary_name in MEASUREMENT_ENUM_FIELDS.items():
                _validate_enum_value(
                    acquisition,
                    field,
                    vocabulary_name,
                    controlled_vocabularies,
                    context=context,
                    required=True,
                )
            if status in {"reported_complete", "derived_complete"}:
                for field in (
                    "modality_or_signal",
                    "primary_measure",
                    "event_trigger",
                    "acquisition_window",
                    "primary_outcome_definition",
                ):
                    if not _json_text(acquisition.get(field)):
                        raise RuntimeError(f"Missing {field}: {context}")
            binding_mode = str(acquisition.get("binding_mode") or "")
            outcome_family = str(acquisition.get("outcome_family") or "")
            if binding_mode == "native_response_log" and outcome_family not in {
                "behavioral_response",
                "multimodal",
            }:
                raise RuntimeError(
                    f"native_response_log requires a behavioral outcome family: {context}"
                )
            for reference_field in (
                "applies_to_event_ids",
                "applies_to_pps_occurrence_ids",
            ):
                _normalize_id_list(
                    acquisition.get(reference_field),
                    context=f"{context}/{reference_field}",
                )

        override = _measurement_source_override(entry)
        finalized = _finalize_source_override(contract, override)
        _validate_source_override(study_row_id, contract, finalized)
        entries[study_row_id] = entry
        overrides[(study_row_id, MEASUREMENT_CONTRACT_KEY)] = finalized
    return document_review_date, entries, overrides


def _first_present(container: dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        value = container.get(key)
        if value not in (None, "", [], {}):
            return value
    return ""


def _sample_assignment_value(entry: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    component_review = (entry.get("component_reviews") or {}).get(
        "sample_and_assignment", {}
    )
    raw_value = (
        component_review.get("value") if isinstance(component_review, dict) else ""
    )
    if isinstance(raw_value, dict):
        return _json_text(raw_value), raw_value
    normalized = entry.get("normalized_structure") or {}
    normalized_sample = normalized.get("sample_and_assignment")
    if isinstance(normalized_sample, dict):
        return _json_text(raw_value) or _json_text(normalized_sample), normalized_sample
    return _json_text(raw_value), {}


def _compiled_event_links(
    events: list[dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    predecessors: dict[str, set[str]] = {
        str(event.get("event_id") or "").strip(): set() for event in events
    }
    concurrent: dict[str, set[str]] = {
        str(event.get("event_id") or "").strip(): set() for event in events
    }
    for event in events:
        event_id = str(event.get("event_id") or "").strip()
        predecessors[event_id].update(
            _normalize_id_list(
                event.get("predecessor_event_ids"),
                context=f"{event_id}/predecessor_event_ids",
            )
        )
        concurrent[event_id].update(
            _normalize_id_list(
                event.get("concurrent_event_ids"),
                context=f"{event_id}/concurrent_event_ids",
            )
        )
        relation = str(event.get("relation") or "").strip()
        relative_to = str(event.get("relative_to_event_id") or "").strip()
        if not relative_to:
            continue
        if relation == "after":
            predecessors[event_id].add(relative_to)
        elif relation == "before":
            predecessors[relative_to].add(event_id)
        elif relation == "concurrent":
            concurrent[event_id].add(relative_to)
            concurrent[relative_to].add(event_id)
    return predecessors, concurrent


def _build_structure_tables(
    *,
    study_index: list[dict[str, str]],
    entries: dict[str, dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    contract: dict[str, Any],
    document_review_date: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    evidence_by_study = {
        row["study_row_id"]: row
        for row in evidence_rows
        if row["contract_key"] == STRUCTURE_CONTRACT_KEY
    }
    structure_rows: list[dict[str, Any]] = []
    factor_level_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    future_paths = " | ".join(contract.get("future_toolkit_paths", []))
    legacy_paths = " | ".join(contract.get("legacy_untyped_metadata_paths", []))
    compiler_outputs = " | ".join(contract.get("compiler_derived_outputs", []))

    for study in study_index:
        study_row_id = study["study_row_id"]
        entry = entries.get(study_row_id, {})
        evidence = evidence_by_study[study_row_id]
        normalized = entry.get("normalized_structure") or {}
        component_reviews = entry.get("component_reviews") or {}
        factors = entry.get("factors") or []
        events = entry.get("events") or []
        sample_summary, sample = _sample_assignment_value(entry)
        visit_ids = {
            str(event.get("visit_id") or "").strip()
            for event in events
            if str(event.get("visit_id") or "").strip()
        }
        session_ids = {
            str(event.get("session_id") or "").strip()
            for event in events
            if str(event.get("session_id") or "").strip()
        }
        occurrence_ids = {
            str(event.get("pps_occurrence_id") or "").strip()
            for event in events
            if str(event.get("pps_occurrence_id") or "").strip()
        }
        assignment_methods = _unique_text(
            factor.get("assignment_method", "") for factor in factors
        )
        structure_rows.append(
            {
                "study_row_id": study_row_id,
                "network_node_id": study["network_node_id"],
                "record_id": study.get("record_id", ""),
                "study_label": study["study_label"],
                "experiment_letter": study.get("experiment_letter", ""),
                "structure_review_status": evidence["evidence_status"],
                "source_type": str(entry.get("source_type") or ""),
                "review_date": str(
                    (entry.get("review_date") or document_review_date)
                    if entry
                    else ""
                ),
                "source_file": evidence["source_file"],
                "page_or_section": evidence["page_or_section"],
                "evidence_note": evidence["evidence_note"],
                "derivation_note": evidence["derivation_note"],
                "sample_and_assignment_status": str(
                    (component_reviews.get("sample_and_assignment") or {}).get(
                        "status", ""
                    )
                ),
                "sample_and_assignment_summary": sample_summary,
                "population_summary": _json_text(
                    sample.get("population_summary")
                ),
                "inclusion_criteria": _json_text(
                    sample.get("inclusion_criteria")
                ),
                "exclusion_criteria": _json_text(
                    sample.get("exclusion_criteria")
                ),
                "planned_sample_n": _first_present(
                    sample, ("planned_n", "planned_sample_n", "planned_sample_size")
                ),
                "analyzed_sample_n": _first_present(
                    sample, ("analyzed_n", "analyzed_sample_n", "analyzed_sample_size")
                ),
                "cohort_or_arm_count": _first_present(
                    sample, ("cohort_or_arm_count", "arm_count", "cohort_count")
                ),
                "per_arm_sample_json": json.dumps(
                    _first_present(
                        sample,
                        (
                            "per_arm_n",
                            "per_arm_sample",
                            "arm_sample_sizes",
                            "cohort_sample_sizes",
                        ),
                    )
                    or {},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "assignment_summary": _first_present(
                    sample, ("assignment_summary", "allocation_summary", "allocation_rule")
                ),
                "assignment_or_order_methods": assignment_methods,
                "design_topology_status": str(
                    (component_reviews.get("design_topology") or {}).get(
                        "status", ""
                    )
                ),
                "design_topology_summary": _json_text(
                    (component_reviews.get("design_topology") or {}).get("value")
                ),
                "pps_occasion_schedule_status": str(
                    (component_reviews.get("pps_occasion_schedule") or {}).get(
                        "status", ""
                    )
                ),
                "pps_occasion_schedule_summary": _json_text(
                    (component_reviews.get("pps_occasion_schedule") or {}).get(
                        "value"
                    )
                ),
                "factor_scope_map_status": str(
                    (component_reviews.get("factor_scope_map") or {}).get(
                        "status", ""
                    )
                ),
                "factor_scope_map_summary": _json_text(
                    (component_reviews.get("factor_scope_map") or {}).get("value")
                ),
                "protocol_binding_status": str(
                    (component_reviews.get("protocol_binding") or {}).get(
                        "status", ""
                    )
                ),
                "protocol_binding_summary": _json_text(
                    (component_reviews.get("protocol_binding") or {}).get("value")
                ),
                "order_assignment_spacing_status": str(
                    (component_reviews.get("order_assignment_spacing") or {}).get(
                        "status", ""
                    )
                ),
                "order_assignment_spacing_summary": _json_text(
                    (component_reviews.get("order_assignment_spacing") or {}).get(
                        "value"
                    )
                ),
                "intervention_schedule_status": str(
                    (component_reviews.get("intervention_schedule") or {}).get(
                        "status", ""
                    )
                ),
                "intervention_schedule_summary": _json_text(
                    (component_reviews.get("intervention_schedule") or {}).get(
                        "value"
                    )
                ),
                "design_family": str(normalized.get("design_family") or ""),
                "assignment_scope": str(normalized.get("assignment_scope") or ""),
                "pps_occurrence_pattern": str(
                    normalized.get("pps_occurrence_pattern") or ""
                ),
                "compiled_factor_count": len(factors),
                "compiled_factor_level_count": sum(
                    len(factor.get("levels") or []) for factor in factors
                ),
                "compiled_event_count": len(events),
                "compiled_pps_measurement_event_count": sum(
                    event.get("event_kind") == "pps_measurement" for event in events
                ),
                "compiled_distinct_visit_id_count": len(visit_ids),
                "compiled_distinct_session_id_count": len(session_ids),
                "compiled_distinct_pps_occurrence_id_count": len(occurrence_ids),
                "normalized_structure_json": json.dumps(
                    normalized,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "component_status_json": json.dumps(
                    {
                        key: review.get("status", "")
                        for key, review in component_reviews.items()
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "component_value_json": json.dumps(
                    {
                        key: review.get("value", "")
                        for key, review in component_reviews.items()
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "current_toolkit_support": contract["current_toolkit_support"],
                "current_toolkit_paths": "",
                "future_toolkit_paths": future_paths,
                "legacy_untyped_metadata_paths": legacy_paths,
                "compiler_derived_outputs": compiler_outputs,
            }
        )

        provenance = {
            "source_type": str(entry.get("source_type") or ""),
            "source_file": evidence["source_file"],
            "page_or_section": evidence["page_or_section"],
            "evidence_note": evidence["evidence_note"],
        }
        identity = {
            "study_row_id": study_row_id,
            "network_node_id": study["network_node_id"],
            "record_id": study.get("record_id", ""),
            "study_label": study["study_label"],
        }
        for factor in factors:
            levels = factor.get("levels") or [{}]
            for level in levels:
                factor_level_rows.append(
                    {
                        **identity,
                        "factor_id": str(factor.get("factor_id") or ""),
                        "factor_label": str(factor.get("label") or ""),
                        "factor_role": str(factor.get("role") or ""),
                        "factor_scope": str(factor.get("scope") or ""),
                        "assignment_method": str(
                            factor.get("assignment_method") or ""
                        ),
                        "allocation_rule": _json_text(
                            factor.get("allocation_rule")
                        ),
                        "level_id": str(level.get("level_id") or ""),
                        "level_label": str(level.get("label") or ""),
                        "planned_n": level.get("planned_n", ""),
                        "analyzed_n": level.get("analyzed_n", ""),
                        "level_record_status": (
                            "declared_level"
                            if level.get("level_id")
                            else "factor_without_discrete_levels"
                        ),
                        **provenance,
                        "current_toolkit_support": contract["current_toolkit_support"],
                        "future_toolkit_path": "pps-study-plan.v1::factors[]",
                    }
                )

        predecessors, concurrent = _compiled_event_links(events)
        for event in events:
            event_id = str(event.get("event_id") or "")
            bindings = _normalize_factor_level_bindings(
                event.get("factor_level_bindings"),
                context=f"{study_row_id}/{event_id}/factor_level_bindings",
            )
            event_rows.append(
                {
                    **identity,
                    "event_id": event_id,
                    "event_label": str(event.get("label") or ""),
                    "order_index": event.get("order_index", ""),
                    "event_kind": str(event.get("event_kind") or ""),
                    "execution_mode": str(event.get("execution_mode") or ""),
                    "relation": str(event.get("relation") or ""),
                    "relative_to_event_id": str(
                        event.get("relative_to_event_id") or ""
                    ),
                    "compiled_predecessor_event_ids": " | ".join(
                        sorted(predecessors[event_id])
                    ),
                    "compiled_concurrent_event_ids": " | ".join(
                        sorted(concurrent[event_id])
                    ),
                    "visit_id": str(event.get("visit_id") or ""),
                    "session_id": str(event.get("session_id") or ""),
                    "pps_occurrence_id": str(
                        event.get("pps_occurrence_id") or ""
                    ),
                    "timepoint_label": str(event.get("timepoint_label") or ""),
                    "repeat_count": event.get("repeat_count", ""),
                    "duration_s": event.get("duration_s", ""),
                    "duration_text": str(event.get("duration_text") or ""),
                    "spacing_notes": str(event.get("spacing_notes") or ""),
                    "factor_level_bindings_json": json.dumps(
                        bindings,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "profile_or_protocol_ref": _json_text(
                        event.get("profile_or_protocol_ref")
                    ),
                    "parameter_overrides_json": json.dumps(
                        event.get("parameter_overrides") or {},
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    **provenance,
                    "current_toolkit_support": contract["current_toolkit_support"],
                    "future_toolkit_path": "pps-study-plan.v1::schedule.events[]",
                }
            )
    return structure_rows, factor_level_rows, event_rows


def _build_measurement_acquisition_table(
    *,
    study_index: list[dict[str, str]],
    entries: dict[str, dict[str, Any]],
    structure_entries: dict[str, dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence_by_study = {
        row["study_row_id"]: row
        for row in evidence_rows
        if row["contract_key"] == MEASUREMENT_CONTRACT_KEY
    }
    study_by_id = {row["study_row_id"]: row for row in study_index}
    rows: list[dict[str, Any]] = []
    for study_row_id, entry in entries.items():
        study = study_by_id[study_row_id]
        evidence = evidence_by_study[study_row_id]
        structure_events = (structure_entries.get(study_row_id) or {}).get("events", [])
        valid_event_ids = {
            str(event.get("event_id") or "").strip() for event in structure_events
        }
        valid_occurrence_ids = {
            str(event.get("pps_occurrence_id") or "").strip()
            for event in structure_events
            if str(event.get("pps_occurrence_id") or "").strip()
        }
        for acquisition in entry.get("acquisitions", []):
            acquisition_id = str(acquisition.get("acquisition_id") or "")
            applies_to_event_ids = _normalize_id_list(
                acquisition.get("applies_to_event_ids"),
                context=f"{study_row_id}/{acquisition_id}/applies_to_event_ids",
            )
            applies_to_occurrence_ids = _normalize_id_list(
                acquisition.get("applies_to_pps_occurrence_ids"),
                context=(
                    f"{study_row_id}/{acquisition_id}/applies_to_pps_occurrence_ids"
                ),
            )
            unknown_events = sorted(set(applies_to_event_ids) - valid_event_ids)
            if unknown_events:
                raise RuntimeError(
                    f"Unknown acquisition schedule event reference(s) on "
                    f"{study_row_id}/{acquisition_id}: {', '.join(unknown_events)}"
                )
            unknown_occurrences = sorted(
                set(applies_to_occurrence_ids) - valid_occurrence_ids
            )
            if unknown_occurrences:
                raise RuntimeError(
                    f"Unknown acquisition PPS occurrence reference(s) on "
                    f"{study_row_id}/{acquisition_id}: {', '.join(unknown_occurrences)}"
                )
            rows.append(
                {
                    "study_row_id": study_row_id,
                    "network_node_id": study["network_node_id"],
                    "record_id": study.get("record_id", ""),
                    "study_label": study["study_label"],
                    "acquisition_id": acquisition_id,
                    "acquisition_label": str(acquisition.get("label") or ""),
                    "outcome_family": str(
                        acquisition.get("outcome_family") or ""
                    ),
                    "modality_or_signal": _json_text(
                        acquisition.get("modality_or_signal")
                    ),
                    "primary_measure": _json_text(
                        acquisition.get("primary_measure")
                    ),
                    "binding_mode": str(acquisition.get("binding_mode") or ""),
                    "device_or_system": _json_text(
                        acquisition.get("device_or_system")
                    ),
                    "channels_or_sites_json": json.dumps(
                        acquisition.get("channels_or_sites") or [],
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "event_trigger": _json_text(
                        acquisition.get("event_trigger")
                    ),
                    "clock_sync_method": str(
                        acquisition.get("clock_sync_method") or ""
                    ),
                    "acquisition_window": _json_text(
                        acquisition.get("acquisition_window")
                    ),
                    "primary_outcome_definition": _json_text(
                        acquisition.get("primary_outcome_definition")
                    ),
                    "calibration_or_online_processing": _json_text(
                        acquisition.get("calibration_or_online_processing")
                    ),
                    "applies_to_event_ids": " | ".join(applies_to_event_ids),
                    "applies_to_pps_occurrence_ids": " | ".join(
                        applies_to_occurrence_ids
                    ),
                    "profile_or_protocol_ref": _json_text(
                        acquisition.get("profile_or_protocol_ref")
                    ),
                    "source_type": str(entry.get("source_type") or ""),
                    "review_date": str(entry.get("review_date") or ""),
                    "source_file": evidence["source_file"],
                    "page_or_section": evidence["page_or_section"],
                    "evidence_note": evidence["evidence_note"],
                    "derivation_note": evidence["derivation_note"],
                    "current_toolkit_support": contract["current_toolkit_support"],
                    "current_toolkit_paths": "",
                    "runtime_or_untyped_inputs": " | ".join(
                        contract.get("runtime_or_untyped_inputs", [])
                    ),
                    "future_toolkit_paths": " | ".join(
                        contract.get("future_toolkit_paths", [])
                    ),
                    "analysis_model_scope": "excluded_from_acquisition_contract",
                }
            )
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_manual_reviews() -> list[dict[str, Any]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(MANUAL_REVIEW_DIR.glob("*.json"))
    ]


def _flatten_fields(review: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    flattened: dict[str, dict[str, Any]] = {}
    for segment_key, fields in (review or {}).get("segment_field_audit", {}).items():
        for field_key, field in fields.items():
            flattened[field_key] = {"segment_key": segment_key, **(field or {})}
    return flattened


def _unique_text(values: Iterable[Any]) -> str:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return " | ".join(result)


def _title(key: str) -> str:
    return key.replace("_", " ").capitalize()


def _doi_source_pointer(doi: Any) -> str:
    value = str(doi or "").strip()
    if not value:
        return ""
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value, flags=re.I)
    return f"https://doi.org/{value}" if value else ""


def _field_class(field: dict[str, Any] | None) -> str:
    if not field:
        return "source_unavailable"
    status = str(field.get("status") or "source_unavailable")
    value = field.get("value")
    has_value = value not in (None, "", [], {})
    if status in {"reported", "reported_with_toolkit_distribution"}:
        return "reported" if has_value else "missing"
    if status in {"derived", "protocol_lineage_derived"}:
        return "derived" if has_value else "missing"
    if status == "reported_with_caveat":
        return "caveated" if has_value else "missing"
    if status == "source_inconsistency_caveat":
        return "conflict" if has_value else "missing"
    if status == "inferred_low_confidence":
        return "low_confidence" if has_value else "source_unavailable"
    if status == "reported_absent":
        return "explicit_absent"
    if status == "not_reported_after_review":
        return "missing"
    if status == "not_applicable":
        return "not_applicable"
    return "source_unavailable"


def _looks_explicitly_absent(value: Any, *, family: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    patterns = {
        "baseline_contract": (
            r"^no (?:separate |explicit )?baseline",
            r"^none$",
            r"without (?:a )?baseline",
        ),
        "catch_contract": (
            r"^no (?:separate )?(?:catch|auditory-only|control) trials?",
            r"^none$",
            r"without (?:catch|auditory-only) trials?",
        ),
        "baseline_trial_contract": (
            r"^no (?:separate |explicit )?baseline",
            r"^none$",
            r"without (?:a )?baseline",
        ),
        "catch_trial_contract": (
            r"^no (?:separate )?(?:catch|auditory-only|control) trials?",
            r"^none$",
            r"without (?:catch|auditory-only) trials?",
        ),
    }
    return any(re.search(pattern, text) for pattern in patterns.get(family, ()))


def _evaluate_contract(
    contract: dict[str, Any],
    fields: dict[str, dict[str, Any]],
    *,
    has_audit: bool,
    composite: bool,
) -> tuple[str, list[str], dict[str, str]]:
    all_parent_fields = [
        *contract["required_parent_fields"],
        *contract.get("conditional_parent_fields", []),
    ]
    component_classes = {
        key: _field_class(fields.get(key)) for key in all_parent_fields
    }
    final_components = list(contract["required_components"])
    if composite:
        return "composite_requires_split", final_components, component_classes
    if not all_parent_fields:
        return "not_assessed", final_components, component_classes
    if not has_audit:
        return "not_assessed", final_components, component_classes

    required_parents = list(contract["required_parent_fields"])
    rule = contract["completion_rule"]
    if rule == "control_family_dependency":
        anchor_key = contract["anchor_parent_field"]
        anchor_field = fields.get(anchor_key)
        anchor_class = component_classes[anchor_key]
        if _looks_explicitly_absent(
            (anchor_field or {}).get("value"), family=contract["column_key"]
        ):
            return "explicitly_absent", [], component_classes
        if anchor_class == "explicit_absent":
            return "explicitly_absent", [], component_classes
        if anchor_class == "not_applicable":
            return "not_applicable", [], component_classes

    required_classes = [component_classes[key] for key in required_parents]
    reported_or_derived = [
        value for value in required_classes if value in {"reported", "derived", "caveated"}
    ]
    # The legacy 25 fields are deliberately only coarse parents. Even a fully
    # populated parent set cannot prove final contract completeness; only an
    # experiment-scoped final-contract review may do that.
    if "conflict" in required_classes:
        return "conflicting_evidence", final_components, component_classes
    if reported_or_derived:
        return (
            "partial",
            list(contract.get("partial_missing_components") or final_components),
            component_classes,
        )
    if "low_confidence" in required_classes:
        return "low_confidence", final_components, component_classes
    if required_classes and all(value == "not_applicable" for value in required_classes):
        return "not_applicable", [], component_classes
    if "source_unavailable" in required_classes:
        return "source_unavailable", final_components, component_classes
    if "missing" in required_classes or "explicit_absent" in required_classes:
        return "not_reported", final_components, component_classes
    return "not_assessed", final_components, component_classes


def _field_value_summary(contract: dict[str, Any], fields: dict[str, dict[str, Any]]) -> str:
    keys = [
        *contract["required_parent_fields"],
        *contract.get("conditional_parent_fields", []),
    ]
    return " | ".join(
        f"{_title(key)}: {fields[key]['value']}"
        for key in keys
        if key in fields and fields[key].get("value") not in (None, "", [], {})
    )


def _toolkit_evidence(
    study_row_id: str,
    current_paths: list[str],
    values_by_study_path: dict[tuple[str, str], list[dict[str, str]]],
) -> tuple[str, str, str]:
    if not current_paths:
        return "not_in_current_design_or_run_plan_schema", "", ""
    matched = [
        row
        for current_path in current_paths
        for row in values_by_study_path.get((study_row_id, current_path), [])
    ]
    if not matched:
        return "no_profile", "", ""
    statuses = {row["categorical_status"] for row in matched}
    if statuses & {"required_field_missing", "invalid_serialized_shape"}:
        encoding_status = "invalid_or_required_input_missing"
    elif statuses & {"serialized_explicit", "partially_serialized_with_defaults"}:
        encoding_status = "encoded_explicit_or_partial"
    else:
        encoding_status = "defaults_or_repeatable_entities_absent"

    value_parts: list[str] = []
    profile_files: list[str] = []
    for row in matched:
        profile_files.append(row.get("profile_source_file", ""))
        try:
            values = json.loads(row.get("explicit_values_json") or "[]")
        except json.JSONDecodeError:
            values = []
        if values:
            value_parts.append(
                f"{row['profile_id']}::{row['current_toolkit_input_path']}="
                f"{json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}"
            )
    return encoding_status, " | ".join(value_parts), _unique_text(profile_files)


def build(output_dir: Path) -> dict[str, Any]:
    contract_document = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract_document.get("schema") != "pps-parsimonious-emulation-contract.v1":
        raise RuntimeError("Unexpected parsimonious emulation contract schema")
    controlled_vocabularies = contract_document.get("controlled_vocabularies", {})
    if not isinstance(controlled_vocabularies, dict):
        raise RuntimeError("controlled_vocabularies must be an object")
    for vocabulary_name, vocabulary in controlled_vocabularies.items():
        if not isinstance(vocabulary, dict) or not vocabulary:
            raise RuntimeError(
                f"Controlled vocabulary {vocabulary_name} must be a non-empty object"
            )
        blank_terms = [
            str(term)
            for term, description in vocabulary.items()
            if not str(term).strip() or not str(description).strip()
        ]
        if blank_terms:
            raise RuntimeError(
                f"Controlled vocabulary {vocabulary_name} has blank term/description entries"
            )
    contracts = contract_document["contracts"]
    contract_keys = [contract["column_key"] for contract in contracts]
    if tuple(contract_keys) != EXPECTED_CONTRACT_KEYS:
        raise RuntimeError(
            "The parsimonious contract must contain the thirteen canonical columns in order: "
            + ", ".join(EXPECTED_CONTRACT_KEYS)
        )
    for contract in contracts:
        key = contract["column_key"]
        if contract.get("completion_rule") != EXPECTED_COMPLETION_RULES[key]:
            raise RuntimeError(
                f"Unexpected completion rule for {key}: {contract.get('completion_rule')}"
            )
        if not str(contract.get("current_toolkit_support") or "").strip():
            raise RuntimeError(f"current_toolkit_support must be nonblank for {key}")
        vocabulary_names = contract.get("normalization_vocabularies", [])
        if not isinstance(vocabulary_names, list):
            raise RuntimeError(f"normalization_vocabularies must be a list for {key}")
        unknown_vocabularies = sorted(
            set(vocabulary_names) - set(controlled_vocabularies)
        )
        if unknown_vocabularies:
            raise RuntimeError(
                f"Unknown normalization vocabulary for {key}: "
                + ", ".join(unknown_vocabularies)
            )
        expected_future_paths = EXPECTED_FUTURE_TOOLKIT_PATHS.get(key, ())
        actual_future_paths = tuple(contract.get("future_toolkit_paths", []))
        if actual_future_paths != expected_future_paths:
            raise RuntimeError(
                f"Unexpected future Toolkit destination path(s) for {key}: "
                + ", ".join(actual_future_paths)
            )
        if expected_future_paths and contract.get("current_toolkit_paths"):
            raise RuntimeError(
                f"Future study/acquisition plan contract cannot claim current design paths: {key}"
            )

    current_schema = json.loads(CURRENT_INPUT_SCHEMA_PATH.read_text(encoding="utf-8"))
    current_paths = {item["serialized_path"] for item in current_schema["inputs"]}
    for contract in contracts:
        unknown = sorted(set(contract["current_toolkit_paths"]) - current_paths)
        if unknown:
            raise RuntimeError(
                f"Unknown current Toolkit path(s) for {contract['column_key']}: {', '.join(unknown)}"
            )

    study_index = _read_csv(output_dir / "study_instance_index.csv")
    current_values = _read_csv(output_dir / "current_toolkit_input_values.csv")
    audits = _read_jsonl(METADATA_AUDIT_PATH)
    manuals = _load_manual_reviews()
    source_review_document = json.loads(SOURCE_REVIEW_PATH.read_text(encoding="utf-8"))
    if source_review_document.get("schema") != "pps-parsimonious-source-reviews.v1":
        raise RuntimeError("Unexpected parsimonious source-review schema")
    source_review_date = str(source_review_document.get("review_date") or "").strip()
    source_reviews: dict[tuple[str, str], dict[str, Any]] = {}
    source_review_entries: dict[str, dict[str, Any]] = {}
    allowed_source_keys = {
        source_key
        for source_keys in SOURCE_KEYS_BY_CONTRACT.values()
        for source_key in source_keys
    } | {"trajectory_geometry", "looming_duration_kinematics", "trial_sequence_response"}
    valid_study_row_ids = {row["study_row_id"] for row in study_index}
    for entry in source_review_document.get("entries", []):
        study_row_id = str(entry.get("study_row_id") or "")
        if not study_row_id or study_row_id in source_review_entries:
            raise RuntimeError(f"Duplicate or blank source-review study row: {study_row_id}")
        if study_row_id not in valid_study_row_ids:
            raise RuntimeError(f"Unknown source-review study row: {study_row_id}")
        if not str(entry.get("source_file") or "").strip():
            raise RuntimeError(f"Source-review entry lacks source_file: {study_row_id}")
        entry_contracts = entry.get("contracts", {})
        if not isinstance(entry_contracts, dict):
            raise RuntimeError(f"Source-review contracts must be an object: {study_row_id}")
        source_review_entries[study_row_id] = entry
        for contract_key, review in entry_contracts.items():
            if not isinstance(review, dict):
                raise RuntimeError(
                    f"Source review must be an object: {study_row_id}/{contract_key}"
                )
            if contract_key not in allowed_source_keys:
                raise RuntimeError(
                    f"Unknown compact contract {contract_key} on source-review row {study_row_id}"
                )
            raw_status = str(review.get("status") or "")
            if (
                raw_status not in STATUS_LEGEND
                and raw_status not in LEGACY_SOURCE_STATUSES
            ) or raw_status == "mixed_across_studies":
                raise RuntimeError(
                    f"Unknown source-review status {raw_status} on {study_row_id}/{contract_key}"
                )
            if not str(review.get("page_or_section") or "").strip():
                raise RuntimeError(
                    f"Source review lacks page_or_section: {study_row_id}/{contract_key}"
                )
            _validate_source_component_reviews(
                study_row_id, contract_key, review, contracts
            )
            source_reviews[(study_row_id, contract_key)] = review
    structure_contract = next(
        contract
        for contract in contracts
        if contract["column_key"] == STRUCTURE_CONTRACT_KEY
    )
    (
        structure_review_date,
        structure_review_entries,
        structure_review_overrides,
    ) = _load_structure_reviews(
        valid_study_row_ids=valid_study_row_ids,
        contract=structure_contract,
        controlled_vocabularies=controlled_vocabularies,
    )
    source_reviews.update(structure_review_overrides)
    measurement_contract = next(
        contract
        for contract in contracts
        if contract["column_key"] == MEASUREMENT_CONTRACT_KEY
    )
    (
        measurement_review_date,
        measurement_review_entries,
        measurement_review_overrides,
    ) = _load_measurement_reviews(
        valid_study_row_ids=valid_study_row_ids,
        contract=measurement_contract,
        controlled_vocabularies=controlled_vocabularies,
    )
    source_reviews.update(measurement_review_overrides)
    for study in study_index:
        if (
            study.get("experiment_disaggregation_status")
            == "experiment_specific_source_review_available"
        ):
            missing_contracts = [
                contract["column_key"]
                for contract in contracts
                if (study["study_row_id"], contract["column_key"])
                not in source_reviews
            ]
            if missing_contracts:
                raise RuntimeError(
                    "experiment_specific_source_review_available requires a dedicated "
                    f"source review for every compact contract on {study['study_row_id']}: "
                    + ", ".join(missing_contracts)
                )
    audit_by_id = {row["record_id"]: row for row in audits}
    manual_by_id = {row["record_id"]: row for row in manuals}
    values_by_study_path: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in current_values:
        values_by_study_path[(row["study_row_id"], row["current_toolkit_input_path"])].append(row)

    status_rows: list[dict[str, Any]] = []
    value_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    review_queue_rows: list[dict[str, Any]] = []

    for study in study_index:
        record_id = study.get("record_id", "")
        audit = audit_by_id.get(record_id)
        manual = manual_by_id.get(record_id)
        effective = manual or audit
        fields = _flatten_fields(effective)
        composite = study.get("parameter_evidence_scope") == "composite_requires_split"
        row_statuses: dict[str, str] = {}
        row_values: dict[str, str] = {}

        for contract in contracts:
            key = contract["column_key"]
            status, missing_required, component_classes = _evaluate_contract(
                contract,
                fields,
                has_audit=effective is not None,
                composite=composite,
            )
            record_value = _field_value_summary(contract, fields)
            source_override = _source_override_for_contract(
                study["study_row_id"], contract, source_reviews
            )
            if source_override:
                source_override = _finalize_source_override(contract, source_override)
                _validate_source_override(study["study_row_id"], contract, source_override)
                status = str(source_override["status"])
                paper_value = str(source_override.get("value") or "")
                missing_required = _source_missing_components(
                    contract, status, source_override
                )
            else:
                paper_value = "" if composite else record_value
            display_value = (
                f"COMPOSITE RECORD - DISAGGREGATE: {record_value}"
                if composite and record_value and not source_override
                else paper_value
            )
            all_parent_fields = [
                *contract["required_parent_fields"],
                *contract.get("conditional_parent_fields", []),
            ]
            if key == STRUCTURE_CONTRACT_KEY:
                source_entry = structure_review_entries.get(
                    study["study_row_id"], {}
                )
                effective_source_review_date = structure_review_date
            elif key == MEASUREMENT_CONTRACT_KEY:
                source_entry = measurement_review_entries.get(
                    study["study_row_id"], {}
                )
                effective_source_review_date = measurement_review_date
            else:
                source_entry = source_review_entries.get(study["study_row_id"], {})
                effective_source_review_date = source_review_date
            source_files = (
                str(source_entry.get("source_file") or "")
                if source_override
                else _unique_text(
                    fields.get(parent, {}).get("source_file", "") for parent in all_parent_fields
                )
            )
            if (
                paper_value
                and status in SOURCE_VALUE_REQUIRED_STATUSES
                and not source_files
            ):
                source_files = _doi_source_pointer(study.get("doi"))
                if not source_files:
                    raise RuntimeError(
                        "Evidence-bearing paper value lacks a source pointer: "
                        f"{study['study_row_id']}/{key}"
                    )
            pages = (
                str(source_override.get("page_or_section") or "")
                if source_override
                else _unique_text(
                    fields.get(parent, {}).get("page_or_section", "") for parent in all_parent_fields
                )
            )
            evidence_notes = (
                str(source_override.get("evidence_note") or "")
                if source_override
                else _unique_text(
                    fields.get(parent, {}).get("evidence_note", "") for parent in all_parent_fields
                )
            )
            derivation_notes = (
                str(source_override.get("derivation_note") or "")
                if source_override
                else _unique_text(
                    fields.get(parent, {}).get("evidence_note", "")
                    for parent in all_parent_fields
                    if _field_class(fields.get(parent)) == "derived"
                )
            )
            toolkit_status, toolkit_values, profile_sources = _toolkit_evidence(
                study["study_row_id"],
                contract["current_toolkit_paths"],
                values_by_study_path,
            )
            row_statuses[key] = status
            row_values[key] = display_value
            final_component_reviews = (
                source_override.get("component_reviews", {})
                if source_override
                else {}
            )

            evidence_row = {
                "study_row_id": study["study_row_id"],
                "network_node_id": study["network_node_id"],
                "record_id": record_id,
                "study_label": study["study_label"],
                "experiment_letter": study.get("experiment_letter", ""),
                "parameter_evidence_scope": study.get("parameter_evidence_scope", ""),
                "contract_key": key,
                "segment": contract["segment"],
                "contract_label": contract["label"],
                "evidence_status": status,
                "paper_value": paper_value,
                "composite_record_value": record_value if composite and not source_override else "",
                "experiment_scoped_source_override": "yes" if source_override else "no",
                "source_review_keys": (
                    str(source_override.get("source_review_keys") or "")
                    if source_override
                    else ""
                ),
                "component_status_json": json.dumps(
                    {
                        component: review.get("status", "")
                        for component, review in final_component_reviews.items()
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "component_value_json": json.dumps(
                    {
                        component: review.get("value", "")
                        for component, review in final_component_reviews.items()
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "component_evidence_note_json": json.dumps(
                    {
                        component: review.get("evidence_note", "")
                        for component, review in final_component_reviews.items()
                        if review.get("evidence_note")
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "coarse_parent_status_json": json.dumps(
                    component_classes,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "coarse_parent_value_json": json.dumps(
                    {
                        parent: fields.get(parent, {}).get("value", "")
                        for parent in all_parent_fields
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "missing_required_components": " | ".join(missing_required),
                "source_layer": (
                    str(source_entry.get("source_type") or "experiment_scoped_source_review")
                    if source_override
                    else "manual_review" if manual else "metadata_audit" if audit else "not_assessed"
                ),
                "review_date": (
                    str(source_entry.get("review_date") or effective_source_review_date)
                    if source_override
                    else str(manual.get("review_date") or "") if manual else ""
                ),
                "source_file": source_files,
                "page_or_section": pages,
                "evidence_note": evidence_notes,
                "derivation_note": derivation_notes,
                "toolkit_encoding_status": toolkit_status,
                "toolkit_value_summary": toolkit_values,
                "profile_source_files": profile_sources,
                "current_toolkit_support": contract["current_toolkit_support"],
                "current_toolkit_paths": " | ".join(contract["current_toolkit_paths"]),
                "future_toolkit_paths": " | ".join(
                    contract.get("future_toolkit_paths", [])
                ),
                "legacy_untyped_metadata_paths": " | ".join(
                    contract.get("legacy_untyped_metadata_paths", [])
                ),
                "compiler_derived_outputs": " | ".join(
                    contract.get("compiler_derived_outputs", [])
                ),
                "runtime_or_untyped_inputs": " | ".join(
                    contract.get("runtime_or_untyped_inputs", [])
                ),
                "review_action": STATUS_ACTIONS[status],
            }
            evidence_rows.append(evidence_row)
            if status not in REVIEW_QUEUE_EXCLUDED_STATUSES:
                review_queue_rows.append(
                    {
                        "priority_score": STATUS_PRIORITY[status]
                        + (12 if study.get("toolkit_status") == "supported_incomplete" else 0),
                        "study_row_id": study["study_row_id"],
                        "record_id": record_id,
                        "study_label": study["study_label"],
                        "contract_key": key,
                        "contract_label": contract["label"],
                        "evidence_status": status,
                        "paper_value": paper_value,
                        "missing_required_components": " | ".join(missing_required),
                        "source_file": source_files,
                        "page_or_section": pages,
                        "toolkit_encoding_status": toolkit_status,
                        "review_action": STATUS_ACTIONS[status],
                        "reviewer_decision": "",
                        "reviewer_note": "",
                        "review_date": "",
                    }
                )

        counts = Counter(row_statuses.values())
        resolved_count = sum(
            counts[status] for status in EMULATION_COVERAGE_STATUSES
        )
        identity = {
            "study_row_id": study["study_row_id"],
            "network_node_id": study["network_node_id"],
            "record_id": record_id,
            "study_label": study["study_label"],
            "title": study["title"],
            "year": study["year"],
            "doi": study["doi"],
            "experiment_letter": study.get("experiment_letter", ""),
            "experiment_label": study.get("experiment_label", ""),
            "profile_id": study.get("profile_id", ""),
            "parameter_evidence_scope": study.get("parameter_evidence_scope", ""),
            "evidence_stage": study.get("evidence_stage", ""),
            "toolkit_status": study.get("toolkit_status", ""),
        }
        status_rows.append(
            {
                **identity,
                "contract_count": len(contracts),
                "available_or_resolved_count": resolved_count,
                "caveated_count": counts["approximation_required"],
                "partial_count": counts["partial"],
                "missing_or_unreviewed_count": sum(
                    counts[status]
                    for status in {
                        "not_reported",
                        "source_unavailable",
                        "not_assessed",
                        "low_confidence",
                    }
                ),
                "composite_requires_split_count": counts["composite_requires_split"],
                "contract_coverage_pct": round(
                    100 * resolved_count / len(contracts),
                    1,
                ),
                "resolved_contracts": f"{resolved_count}/{len(contracts)}",
                **row_statuses,
            }
        )
        value_rows.append({**identity, **row_values})

    study_order = {row["study_row_id"]: index for index, row in enumerate(study_index)}
    if len(study_order) != len(study_index):
        raise RuntimeError("study_instance_index.csv contains duplicate study_row_id values")
    status_rows.sort(key=lambda row: study_order[row["study_row_id"]])
    value_rows_by_id = {row["study_row_id"]: row for row in value_rows}
    value_rows = [value_rows_by_id[row["study_row_id"]] for row in status_rows]
    evidence_rows.sort(key=lambda row: (row["study_row_id"], contract_keys.index(row["contract_key"])))
    review_queue_rows.sort(
        key=lambda row: (-int(row["priority_score"]), row["study_row_id"], contract_keys.index(row["contract_key"]))
    )

    rows_by_node: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in status_rows:
        rows_by_node[row["network_node_id"]].append(row)
    publication_rows: list[dict[str, Any]] = []
    for node_id, rows in rows_by_node.items():
        first = rows[0]
        aggregate: dict[str, Any] = {
            "network_node_id": node_id,
            "title": first["title"],
            "year": first["year"],
            "doi": first["doi"],
            "toolkit_status": first["toolkit_status"],
            "study_instance_count": len(rows),
            "study_row_ids": " | ".join(row["study_row_id"] for row in rows),
        }
        for key in contract_keys:
            statuses = sorted({row[key] for row in rows})
            aggregate[key] = statuses[0] if len(statuses) == 1 else "mixed_across_studies"
        publication_rows.append(aggregate)
    prominence_by_node = {
        row["network_node_id"]: int(row["network_prominence_rank"]) for row in study_index
    }
    publication_rows.sort(key=lambda row: (prominence_by_node[row["network_node_id"]], row["network_node_id"]))

    dictionary_rows = [
        {
            "ordinal": index,
            "contract_key": contract["column_key"],
            "segment": contract["segment"],
            "label": contract["label"],
            "description": contract["description"],
            "completion_rule": contract["completion_rule"],
            "current_toolkit_support": contract["current_toolkit_support"],
            "required_components": " | ".join(contract["required_components"]),
            "conditional_components": " | ".join(
                contract.get("conditional_components", [])
            ),
            "partial_missing_components": " | ".join(
                contract.get("partial_missing_components", [])
            ),
            "normalization_vocabularies": " | ".join(
                contract.get("normalization_vocabularies", [])
            ),
            "controlled_vocabulary_json": json.dumps(
                {
                    vocabulary_name: controlled_vocabularies[vocabulary_name]
                    for vocabulary_name in contract.get(
                        "normalization_vocabularies", []
                    )
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "required_parent_fields": " | ".join(contract["required_parent_fields"]),
            "conditional_parent_fields": " | ".join(
                contract.get("conditional_parent_fields", [])
            ),
            "current_toolkit_paths": " | ".join(contract["current_toolkit_paths"]),
            "future_toolkit_paths": " | ".join(
                contract.get("future_toolkit_paths", [])
            ),
            "legacy_untyped_metadata_paths": " | ".join(
                contract.get("legacy_untyped_metadata_paths", [])
            ),
            "compiler_derived_outputs": " | ".join(
                contract.get("compiler_derived_outputs", [])
            ),
            "runtime_or_untyped_inputs": " | ".join(
                contract.get("runtime_or_untyped_inputs", [])
            ),
        }
        for index, contract in enumerate(contracts, start=1)
    ]
    summary_rows: list[dict[str, Any]] = []
    evidence_by_contract: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in evidence_rows:
        evidence_by_contract[row["contract_key"]].append(row)
    for contract in contracts:
        key = contract["column_key"]
        counts = Counter(row["evidence_status"] for row in evidence_by_contract[key])
        summary_rows.append(
            {
                "contract_key": key,
                "segment": contract["segment"],
                "label": contract["label"],
                "study_count": len(status_rows),
                **{status: counts[status] for status in STATUS_LEGEND if status != "mixed_across_studies"},
                "available_or_resolved_count": sum(
                    counts[status] for status in EMULATION_COVERAGE_STATUSES
                ),
                "available_or_resolved_pct": round(
                    100
                    * sum(counts[status] for status in EMULATION_COVERAGE_STATUSES)
                    / len(status_rows),
                    1,
                ),
                "toolkit_encoded_count": sum(
                    row["toolkit_encoding_status"] == "encoded_explicit_or_partial"
                    for row in evidence_by_contract[key]
                ),
            }
        )

    structure_rows, factor_level_rows, event_rows = _build_structure_tables(
        study_index=study_index,
        entries=structure_review_entries,
        evidence_rows=evidence_rows,
        contract=structure_contract,
        document_review_date=structure_review_date,
    )
    measurement_acquisition_rows = _build_measurement_acquisition_table(
        study_index=study_index,
        entries=measurement_review_entries,
        structure_entries=structure_review_entries,
        evidence_rows=evidence_rows,
        contract=measurement_contract,
    )

    # Keep the primary have/missing table genuinely compact. Join/debug IDs,
    # component counts, and profile scope remain in study_instance_index.csv
    # and parsimonious_contract_evidence.csv rather than becoming review
    # columns that a human has to scan past.
    status_identity_columns = [
        "study_row_id",
        "study_label",
        "year",
        "doi",
        "experiment_label",
        "evidence_stage",
        "toolkit_status",
    ]
    status_columns = [
        *status_identity_columns,
        "resolved_contracts",
        "contract_coverage_pct",
        *contract_keys,
    ]
    value_columns = [
        "study_row_id",
        "network_node_id",
        "record_id",
        "study_label",
        "title",
        "year",
        "doi",
        "experiment_letter",
        "experiment_label",
        "profile_id",
        "parameter_evidence_scope",
        "evidence_stage",
        "toolkit_status",
        *contract_keys,
    ]
    publication_columns = [
        "network_node_id",
        "title",
        "year",
        "doi",
        "toolkit_status",
        "study_instance_count",
        "study_row_ids",
        *contract_keys,
    ]
    evidence_columns = list(evidence_rows[0])
    review_columns = list(review_queue_rows[0])
    dictionary_columns = list(dictionary_rows[0])
    summary_columns = list(summary_rows[0])
    structure_columns = [
        "study_row_id",
        "network_node_id",
        "record_id",
        "study_label",
        "experiment_letter",
        "structure_review_status",
        "source_type",
        "review_date",
        "source_file",
        "page_or_section",
        "evidence_note",
        "derivation_note",
        "sample_and_assignment_status",
        "sample_and_assignment_summary",
        "population_summary",
        "inclusion_criteria",
        "exclusion_criteria",
        "planned_sample_n",
        "analyzed_sample_n",
        "cohort_or_arm_count",
        "per_arm_sample_json",
        "assignment_summary",
        "assignment_or_order_methods",
        "design_topology_status",
        "design_topology_summary",
        "pps_occasion_schedule_status",
        "pps_occasion_schedule_summary",
        "factor_scope_map_status",
        "factor_scope_map_summary",
        "protocol_binding_status",
        "protocol_binding_summary",
        "order_assignment_spacing_status",
        "order_assignment_spacing_summary",
        "intervention_schedule_status",
        "intervention_schedule_summary",
        "design_family",
        "assignment_scope",
        "pps_occurrence_pattern",
        "compiled_factor_count",
        "compiled_factor_level_count",
        "compiled_event_count",
        "compiled_pps_measurement_event_count",
        "compiled_distinct_visit_id_count",
        "compiled_distinct_session_id_count",
        "compiled_distinct_pps_occurrence_id_count",
        "normalized_structure_json",
        "component_status_json",
        "component_value_json",
        "current_toolkit_support",
        "current_toolkit_paths",
        "future_toolkit_paths",
        "legacy_untyped_metadata_paths",
        "compiler_derived_outputs",
    ]
    factor_level_columns = [
        "study_row_id",
        "network_node_id",
        "record_id",
        "study_label",
        "factor_id",
        "factor_label",
        "factor_role",
        "factor_scope",
        "assignment_method",
        "allocation_rule",
        "level_id",
        "level_label",
        "planned_n",
        "analyzed_n",
        "level_record_status",
        "source_type",
        "source_file",
        "page_or_section",
        "evidence_note",
        "current_toolkit_support",
        "future_toolkit_path",
    ]
    event_columns = [
        "study_row_id",
        "network_node_id",
        "record_id",
        "study_label",
        "event_id",
        "event_label",
        "order_index",
        "event_kind",
        "execution_mode",
        "relation",
        "relative_to_event_id",
        "compiled_predecessor_event_ids",
        "compiled_concurrent_event_ids",
        "visit_id",
        "session_id",
        "pps_occurrence_id",
        "timepoint_label",
        "repeat_count",
        "duration_s",
        "duration_text",
        "spacing_notes",
        "factor_level_bindings_json",
        "profile_or_protocol_ref",
        "parameter_overrides_json",
        "source_type",
        "source_file",
        "page_or_section",
        "evidence_note",
        "current_toolkit_support",
        "future_toolkit_path",
    ]
    measurement_acquisition_columns = [
        "study_row_id",
        "network_node_id",
        "record_id",
        "study_label",
        "acquisition_id",
        "acquisition_label",
        "outcome_family",
        "modality_or_signal",
        "primary_measure",
        "binding_mode",
        "device_or_system",
        "channels_or_sites_json",
        "event_trigger",
        "clock_sync_method",
        "acquisition_window",
        "primary_outcome_definition",
        "calibration_or_online_processing",
        "applies_to_event_ids",
        "applies_to_pps_occurrence_ids",
        "profile_or_protocol_ref",
        "source_type",
        "review_date",
        "source_file",
        "page_or_section",
        "evidence_note",
        "derivation_note",
        "current_toolkit_support",
        "current_toolkit_paths",
        "runtime_or_untyped_inputs",
        "future_toolkit_paths",
        "analysis_model_scope",
    ]
    legend_rows = [
        {
            "status": status,
            "description": description,
            "default_review_action": STATUS_ACTIONS[status],
        }
        for status, description in STATUS_LEGEND.items()
    ]

    _write_csv(
        output_dir / "study_instance_parsimonious_status_matrix.csv",
        status_rows,
        status_columns,
    )
    _write_csv(
        output_dir / "study_instance_parsimonious_value_matrix.csv",
        value_rows,
        value_columns,
    )
    _write_csv(
        output_dir / "publication_parsimonious_status_matrix.csv",
        publication_rows,
        publication_columns,
    )
    _write_csv(
        output_dir / "parsimonious_contract_evidence.csv",
        evidence_rows,
        evidence_columns,
    )
    _write_csv(
        output_dir / "parsimonious_contract_review_queue.csv",
        review_queue_rows,
        review_columns,
    )
    _write_csv(
        output_dir / "parsimonious_contract_dictionary.csv",
        dictionary_rows,
        dictionary_columns,
    )
    _write_csv(
        output_dir / "parsimonious_contract_summary.csv",
        summary_rows,
        summary_columns,
    )
    _write_csv(
        output_dir / "parsimonious_status_legend.csv",
        legend_rows,
        ["status", "description", "default_review_action"],
    )
    _write_csv(
        output_dir / "study_structure.csv",
        structure_rows,
        structure_columns,
    )
    _write_csv(
        output_dir / "study_factor_levels.csv",
        factor_level_rows,
        factor_level_columns,
    )
    _write_csv(
        output_dir / "study_schedule_events.csv",
        event_rows,
        event_columns,
    )
    _write_csv(
        output_dir / "study_measurement_acquisitions.csv",
        measurement_acquisition_rows,
        measurement_acquisition_columns,
    )

    return {
        "schema": contract_document["schema"],
        "contract_count": len(contracts),
        "study_count": len(status_rows),
        "publication_count": len(publication_rows),
        "evidence_cell_count": len(evidence_rows),
        "review_queue_count": len(review_queue_rows),
        "structure_review_count": len(structure_review_entries),
        "structure_factor_level_row_count": len(factor_level_rows),
        "structure_event_row_count": len(event_rows),
        "measurement_review_count": len(measurement_review_entries),
        "measurement_acquisition_row_count": len(measurement_acquisition_rows),
        "status_counts": dict(sorted(Counter(row["evidence_status"] for row in evidence_rows).items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    result = build(args.output.resolve())
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
