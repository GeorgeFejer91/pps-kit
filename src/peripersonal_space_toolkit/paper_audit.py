"""Read-only helpers for the audio-tactile PPS paper metadata audit."""

from __future__ import annotations

import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .runtime_paths import repo_root


DEFAULT_AUDIT_DIR = Path("For-AI") / "audiotactile-paper-metadata-audit"
RAW_ARTIFACT_PREFIX = "artifacts/paper_metadata_audit/"
TRACKED_AUDIT_SCHEMA = "pps-paper-metadata-audit-record.v1"


@dataclass(frozen=True)
class PaperAuditPaths:
    """Resolved locations for tracked paper-audit ledgers."""

    repo_root: Path
    audit_dir: Path
    metadata_audit: Path
    audit_summary: Path
    manual_review_index: Path
    missing_request_list: Path


def audit_paths(root: Path | str | None = None, audit_dir: Path | str = DEFAULT_AUDIT_DIR) -> PaperAuditPaths:
    """Return resolved paths for the tracked paper-audit state."""

    resolved_root = Path(root).resolve() if root is not None else repo_root().resolve()
    resolved_audit = Path(audit_dir)
    if not resolved_audit.is_absolute():
        resolved_audit = resolved_root / resolved_audit
    return PaperAuditPaths(
        repo_root=resolved_root,
        audit_dir=resolved_audit,
        metadata_audit=resolved_audit / "metadata_audit.jsonl",
        audit_summary=resolved_audit / "audit_summary.json",
        manual_review_index=resolved_audit / "manual_review_index.csv",
        missing_request_list=resolved_audit / "missing_pdf_request_list.csv",
    )


def load_metadata_records(root: Path | str | None = None, audit_dir: Path | str = DEFAULT_AUDIT_DIR) -> list[dict[str, Any]]:
    """Load tracked paper-audit records from `metadata_audit.jsonl`."""

    paths = audit_paths(root, audit_dir)
    records = [
        json.loads(line)
        for line in paths.metadata_audit.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in records:
        schema = record.get("schema")
        if schema != TRACKED_AUDIT_SCHEMA:
            record_id = record.get("record_id", "<unknown>")
            raise ValueError(f"Unrecognized paper-audit schema for {record_id}: {schema}")
    return records


def load_audit_summary(root: Path | str | None = None, audit_dir: Path | str = DEFAULT_AUDIT_DIR) -> dict[str, Any]:
    """Load the tracked paper-audit summary JSON."""

    return json.loads(audit_paths(root, audit_dir).audit_summary.read_text(encoding="utf-8"))


def load_manual_review_index(root: Path | str | None = None, audit_dir: Path | str = DEFAULT_AUDIT_DIR) -> list[dict[str, str]]:
    """Load the compact tracked manual-review index."""

    path = audit_paths(root, audit_dir).manual_review_index
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def category_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count records by literature coverage category."""

    return dict(sorted(Counter(str(record.get("coverage_category", "")) for record in records).items()))


def blocker_counts(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    """Count task-mechanics blocker IDs across paper-audit records."""

    counts: Counter[str] = Counter()
    for record in records:
        for blocker in _record_blockers(record):
            counts[str(blocker)] += 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def profile_candidate_summary(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Summarize how audit records can feed future profile implementation work."""

    record_list = list(records)
    runnable: list[dict[str, Any]] = []
    missing_parameters: list[dict[str, Any]] = []
    toolkit_gaps: list[dict[str, Any]] = []
    adjacent: list[dict[str, Any]] = []

    for record in record_list:
        candidate = _candidate_payload(record)
        category = str(record.get("coverage_category") or "")
        if category == "adjacent_out_of_scope":
            adjacent.append(candidate)
        elif _record_is_runnable(record):
            runnable.append(candidate)
        elif "missing_publication_parameters" in category:
            missing_parameters.append(candidate)
        elif "toolkit_structure" in category:
            toolkit_gaps.append(candidate)

    return {
        "schema": "pps-paper-audit-profile-candidate-summary.v1",
        "record_count": len(record_list),
        "category_counts": category_counts(record_list),
        "runnable_profile_records": runnable,
        "missing_parameter_records": missing_parameters,
        "toolkit_structure_gap_records": toolkit_gaps,
        "adjacent_out_of_scope_records": adjacent,
        "blocker_counts": blocker_counts(record_list),
        "copyright_boundary": (
            "Tracked summaries contain source pointers and short metadata only; raw PDFs, "
            "supplements, extracted full text, page images, and resume ZIPs stay under ignored "
            f"{RAW_ARTIFACT_PREFIX}."
        ),
    }


def source_pointer_only_issues(records: Iterable[dict[str, Any]]) -> list[str]:
    """Return audit-record fields that appear to point outside the tracked-safe boundary."""

    issues: list[str] = []
    for record in records:
        record_id = str(record.get("record_id", "<unknown>"))
        for field_name in ("pdf_file",):
            value = str(record.get(field_name) or "")
            public_review_url = (
                field_name == "pdf_file"
                and record.get("pdf_status") == "public_pdf_reviewed"
                and value.startswith("https://")
            )
            if value and not value.startswith(RAW_ARTIFACT_PREFIX) and not public_review_url:
                issues.append(f"{record_id}.{field_name}={value}")
        for source_file in _iter_source_files(record):
            if source_file and not source_file.startswith(RAW_ARTIFACT_PREFIX):
                issues.append(f"{record_id}.source_file={source_file}")
    return issues


def _candidate_payload(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_id": str(record.get("record_id") or ""),
        "citation_short": str(record.get("citation_short") or ""),
        "coverage_category": str(record.get("coverage_category") or ""),
        "template_ids": list(record.get("current_template_ids") or []),
        "task_family": str(record.get("audiotactile_task_family") or ""),
        "metadata_confidence_label": str(record.get("metadata_confidence_label") or ""),
        "metadata_confidence_score": float(record.get("metadata_confidence_score") or 0.0),
        "blocker_ids": _record_blockers(record),
        "missing_publication_parameters": list(record.get("known_missing_or_unresolved_from_prior_ledger") or []),
    }


def _record_is_runnable(record: dict[str, Any]) -> bool:
    category = str(record.get("coverage_category") or "")
    template_ids = record.get("current_template_ids") or []
    return category == "covered_runnable_profile" or bool(
        template_ids and record.get("can_recreate_audiotactile_components_now") is True
    )


def _record_blockers(record: dict[str, Any]) -> list[str]:
    blockers = record.get("blocking_constraint_ids_from_prior_ledger")
    if blockers is None:
        blockers = record.get("blocking_constraint_ids")
    return [str(blocker) for blocker in blockers or []]


def _iter_source_files(record: dict[str, Any]) -> Iterable[str]:
    evidence = record.get("automated_evidence_mining") or {}
    for source_file in evidence.get("source_files") or []:
        yield str(source_file)
    for segment in (record.get("segment_field_audit") or {}).values():
        for field in segment.values():
            yield str(field.get("source_file") or "")
    visualization = record.get("pps_visualization_audit") or {}
    for candidate in visualization.get("visualization_candidates") or []:
        yield str(candidate.get("source_file") or "")
