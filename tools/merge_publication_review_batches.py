#!/usr/bin/env python3
"""Validate and deterministically merge publication-review batch fragments.

The merge is intentionally fail-closed. Registry proposals are composed first,
because a formal-experiment split changes the valid ``study_row_id`` set. Review
fragments are then overlaid, validated against the proposed registry, and sorted
in the exact order used by ``study_instance_index.csv``.

Nothing is written unless ``--apply`` is supplied. All candidate documents are
validated before the first canonical file is replaced.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import build_parsimonious_publication_matrix as compact_builder


REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIT_DIR = REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit"
DEFAULT_BATCH_DIR = REPO_ROOT / "artifacts" / "paper_metadata_audit" / "review_batches"
NETWORK_PATH = (
    REPO_ROOT
    / "src"
    / "peripersonal_space_toolkit"
    / "dashboard"
    / "publication_network.v3.json"
)
REGISTRY_PATH = AUDIT_DIR / "study_instance_registry.json"
CONTRACT_PATH = AUDIT_DIR / "parsimonious_emulation_contract.v1.json"

REVIEW_SPECS = {
    "source": {
        "filename": "parsimonious_source_reviews.v1.json",
        "schema": "pps-parsimonious-source-reviews.v1",
    },
    "structure": {
        "filename": "study_structure_reviews.v1.json",
        "schema": "pps-study-structure-reviews.v1",
    },
    "measurement": {
        "filename": "measurement_acquisition_reviews.v1.json",
        "schema": "pps-measurement-acquisition-reviews.v1",
    },
}


class MergeError(RuntimeError):
    """Raised when a proposed merge is incomplete or ambiguous."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MergeError(f"Required file is absent: {path}") from exc
    except json.JSONDecodeError as exc:
        raise MergeError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise MergeError(f"Top-level JSON value must be an object: {path}")
    return document


def _normalize_doi(value: Any) -> str:
    doi = str(value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi


def _parse_review_date(value: Any, *, context: str) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise MergeError(f"Review date must be ISO YYYY-MM-DD: {context}: {text!r}") from exc


def _experiment_letter(index: int) -> str:
    value = index + 1
    result = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        result = chr(97 + remainder) + result
    return result


def _validate_registry_entry(
    entry: dict[str, Any],
    *,
    network_by_id: dict[str, dict[str, Any]],
    context: str,
) -> None:
    node_id = str(entry.get("network_node_id") or "").strip()
    if not node_id:
        raise MergeError(f"Blank network_node_id: {context}")
    node = network_by_id.get(node_id)
    if node is None:
        raise MergeError(f"Registry node is absent from the publication network: {node_id}")
    if _normalize_doi(entry.get("doi")) != _normalize_doi(node.get("doi")):
        raise MergeError(f"Registry DOI mismatch: {node_id}")
    for field in ("inventory_status", "instance_count_basis", "evidence_pointer"):
        if not str(entry.get(field) or "").strip():
            raise MergeError(f"Registry entry lacks {field}: {node_id}")
    instances = entry.get("instances")
    if not isinstance(instances, list) or not instances:
        raise MergeError(f"Registry entry needs at least one instance: {node_id}")
    suffixes = [str(instance.get("suffix") or "") for instance in instances]
    expected = [_experiment_letter(index) for index in range(len(instances))]
    if suffixes != expected:
        raise MergeError(
            f"Registry suffixes must be sequential lowercase letters on {node_id}: "
            f"expected {expected}, found {suffixes}"
        )
    known_record_ids = {
        str(record.get("recordId") or "")
        for record in (node.get("toolkit") or {}).get("records", [])
    }
    record_counts: dict[str, int] = {}
    for index, instance in enumerate(instances):
        instance_context = f"{context}/instances[{index}]"
        if not isinstance(instance, dict):
            raise MergeError(f"Registry instance must be an object: {instance_context}")
        for field in (
            "instance_kind",
            "experiment_label",
            "toolkit_scope",
            "disaggregation_status",
        ):
            if not str(instance.get(field) or "").strip():
                raise MergeError(f"Registry instance lacks {field}: {instance_context}")
        record_id = str(instance.get("record_id") or "").strip()
        if record_id and record_id not in known_record_ids:
            raise MergeError(
                f"Registry record {record_id!r} is not joined to network node {node_id}"
            )
        if record_id:
            record_counts[record_id] = record_counts.get(record_id, 0) + 1
    for instance in instances:
        record_id = str(instance.get("record_id") or "").strip()
        if (
            record_id
            and record_counts[record_id] > 1
            and instance.get("disaggregation_status")
            not in {
                "combined_record_requires_experiment_specific_review",
                "experiment_specific_source_review_available",
            }
        ):
            raise MergeError(
                f"Reused composite record {record_id} lacks the disaggregation flag on {node_id}"
            )


def _compose_registry(
    canonical: dict[str, Any],
    proposal_paths: list[Path],
    network: dict[str, Any],
) -> tuple[dict[str, Any], set[str], int]:
    if canonical.get("schema") != "pps-publication-study-instance-registry.v1":
        raise MergeError("Unexpected canonical study-instance registry schema")
    network_by_id = {str(node.get("id") or ""): node for node in network.get("nodes", [])}
    entries = canonical.get("entries")
    if not isinstance(entries, list):
        raise MergeError("Canonical registry entries must be a list")
    result_entries = json.loads(json.dumps(entries))
    positions: dict[str, int] = {}
    for index, entry in enumerate(result_entries):
        if not isinstance(entry, dict):
            raise MergeError(f"Registry entry must be an object: canonical entries[{index}]")
        node_id = str(entry.get("network_node_id") or "").strip()
        if node_id in positions:
            raise MergeError(f"Duplicate canonical registry node: {node_id}")
        positions[node_id] = index
        _validate_registry_entry(
            entry, network_by_id=network_by_id, context=f"canonical entries[{index}]"
        )

    changed_nodes: set[str] = set()
    proposal_origins: dict[str, Path] = {}
    proposal_count = 0
    for path in proposal_paths:
        fragment = _load_json(path)
        if fragment.get("schema") not in {
            "pps-publication-study-instance-registry.v1",
            "pps-publication-study-instance-registry-fragment.v1",
        }:
            raise MergeError(f"Unexpected registry-fragment schema: {path}")
        fragment_entries = fragment.get("entries")
        if not isinstance(fragment_entries, list):
            raise MergeError(f"Registry-fragment entries must be a list: {path}")
        for index, entry in enumerate(fragment_entries):
            if not isinstance(entry, dict):
                raise MergeError(f"Registry proposal must be an object: {path} entries[{index}]")
            _validate_registry_entry(
                entry,
                network_by_id=network_by_id,
                context=f"{path} entries[{index}]",
            )
            node_id = str(entry["network_node_id"])
            if node_id in proposal_origins:
                prior = result_entries[positions[node_id]]
                if prior != entry:
                    raise MergeError(
                        f"Conflicting registry proposals for {node_id}: "
                        f"{proposal_origins[node_id]} and {path}"
                    )
                continue
            proposal_origins[node_id] = path
            proposal_count += 1
            candidate = json.loads(json.dumps(entry))
            if node_id in positions:
                prior = result_entries[positions[node_id]]
                if len(candidate["instances"]) < len(prior["instances"]):
                    raise MergeError(
                        f"Registry proposal contracts {node_id} from "
                        f"{len(prior['instances'])} to {len(candidate['instances'])} instances"
                    )
                if candidate != prior:
                    result_entries[positions[node_id]] = candidate
                    changed_nodes.add(node_id)
            else:
                positions[node_id] = len(result_entries)
                result_entries.append(candidate)
                changed_nodes.add(node_id)

    result = json.loads(json.dumps(canonical))
    result["entries"] = result_entries
    return result, changed_nodes, proposal_count


def _study_row_order(
    network: dict[str, Any], registry: dict[str, Any]
) -> list[str]:
    registry_by_node = {
        str(entry["network_node_id"]): entry for entry in registry.get("entries", [])
    }
    prominence_order = sorted(
        network.get("nodes", []),
        key=lambda node: (
            -float((node.get("network") or {}).get("prominence") or 0),
            str(node.get("id") or ""),
        ),
    )
    rows: list[str] = []
    for node in prominence_order:
        node_id = str(node.get("id") or "")
        registry_entry = registry_by_node.get(node_id)
        if registry_entry is not None:
            units = registry_entry["instances"]
            suffixes = [str(instance["suffix"]) for instance in units]
        else:
            records = (node.get("toolkit") or {}).get("records", [])
            units = records or [None]
            suffixes = [_experiment_letter(index) for index in range(len(units))]
        if len(units) > 1:
            rows.extend(f"{node_id}::{suffix}" for suffix in suffixes)
        else:
            rows.append(node_id)
    if len(rows) != len(set(rows)):
        raise MergeError("Proposed registry produces duplicate study_row_id values")
    return rows


def _entry_review_date(entry: dict[str, Any], document: dict[str, Any], path: Path) -> date:
    return _parse_review_date(
        entry.get("review_date") or document.get("review_date"),
        context=f"{path}::{entry.get('study_row_id', '')}",
    )


def _has_primary_pdf_evidence(entry: dict[str, Any]) -> bool:
    source_type = str(entry.get("source_type") or "").lower()
    source_file = str(entry.get("source_file") or "").lower()
    page = str(entry.get("page_or_section") or "").lower()
    return (
        "publication_pdf" in source_type
        or source_file.endswith(".pdf")
        or "publication_pdfs/" in source_file
        or page.startswith("pdf ")
        or " pdf " in f" {page} "
        or "appendix p." in page
        or "appendix pp." in page
    )


def _compose_review(
    *,
    kind: str,
    canonical: dict[str, Any],
    fragment_paths: list[Path],
    valid_order: list[str],
    changed_registry_nodes: set[str],
) -> tuple[dict[str, Any], dict[str, int]]:
    spec = REVIEW_SPECS[kind]
    if canonical.get("schema") != spec["schema"]:
        raise MergeError(f"Unexpected canonical {kind} review schema")
    canonical_entries = canonical.get("entries")
    if not isinstance(canonical_entries, list):
        raise MergeError(f"Canonical {kind} review entries must be a list")

    merged: dict[str, dict[str, Any]] = {}
    origins: dict[str, tuple[str, Path, date]] = {}
    canonical_path = AUDIT_DIR / spec["filename"]
    canonical_document_date = _parse_review_date(
        canonical.get("review_date"), context=str(canonical_path)
    )
    for index, entry in enumerate(canonical_entries):
        if not isinstance(entry, dict):
            raise MergeError(f"Canonical {kind} entry must be an object: entries[{index}]")
        row_id = str(entry.get("study_row_id") or "").strip()
        if not row_id or row_id in merged:
            raise MergeError(f"Duplicate or blank canonical {kind} row: {row_id}")
        merged[row_id] = json.loads(json.dumps(entry))
        origins[row_id] = (
            "canonical",
            canonical_path,
            _entry_review_date(entry, canonical, canonical_path),
        )

    incoming_ids: set[str] = set()
    replacements = 0
    additions = 0
    latest_date = canonical_document_date
    for path in fragment_paths:
        fragment = _load_json(path)
        if fragment.get("schema") != spec["schema"]:
            raise MergeError(f"Unexpected {kind} review-fragment schema: {path}")
        entries = fragment.get("entries")
        if not isinstance(entries, list):
            raise MergeError(f"{kind.title()} fragment entries must be a list: {path}")
        seen_in_file: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                raise MergeError(
                    f"{kind.title()} fragment entry must be an object: {path}[{index}]"
                )
            row_id = str(entry.get("study_row_id") or "").strip()
            if not row_id or row_id in seen_in_file:
                raise MergeError(f"Duplicate or blank {kind} fragment row in {path}: {row_id}")
            seen_in_file.add(row_id)
            incoming_ids.add(row_id)
            incoming_date = _entry_review_date(entry, fragment, path)
            latest_date = max(latest_date, incoming_date)
            if row_id not in merged:
                merged[row_id] = json.loads(json.dumps(entry))
                origins[row_id] = ("fragment", path, incoming_date)
                additions += 1
                continue
            if merged[row_id] == entry:
                continue
            prior_kind, prior_path, prior_date = origins[row_id]
            if prior_kind == "fragment":
                if incoming_date <= prior_date:
                    raise MergeError(
                        f"Ambiguous duplicate {kind} fragments for {row_id}: "
                        f"{prior_path} and {path}"
                    )
            elif incoming_date < prior_date:
                raise MergeError(
                    f"Older {kind} fragment cannot replace canonical row {row_id}: "
                    f"{incoming_date} < {prior_date}"
                )
            if not _has_primary_pdf_evidence(entry):
                raise MergeError(
                    f"Changed {kind} row {row_id} lacks explicit primary-PDF evidence; "
                    f"refusing replacement from {path}"
                )
            merged[row_id] = json.loads(json.dumps(entry))
            origins[row_id] = ("fragment", path, incoming_date)
            replacements += 1

    valid_ids = set(valid_order)
    obsolete = sorted(set(merged) - valid_ids)
    dropped = 0
    for row_id in obsolete:
        node_id = row_id.split("::", 1)[0]
        if node_id not in changed_registry_nodes:
            raise MergeError(f"Unknown {kind} review study_row_id: {row_id}")
        replacement_ids = {
            candidate for candidate in valid_order if candidate.split("::", 1)[0] == node_id
        }
        if not replacement_ids.issubset(incoming_ids):
            missing = sorted(replacement_ids - incoming_ids)
            raise MergeError(
                f"Registry split would orphan {kind} row {row_id}; batch lacks replacements: "
                + ", ".join(missing)
            )
        del merged[row_id]
        dropped += 1

    remaining_unknown = sorted(set(merged) - valid_ids)
    if remaining_unknown:
        raise MergeError(f"Unknown {kind} review rows: {', '.join(remaining_unknown)}")
    order_index = {row_id: index for index, row_id in enumerate(valid_order)}
    result = json.loads(json.dumps(canonical))
    result["review_date"] = latest_date.isoformat()
    result["entries"] = sorted(
        merged.values(), key=lambda entry: order_index[str(entry["study_row_id"])]
    )
    return result, {
        "canonical": len(canonical_entries),
        "additions": additions,
        "replacements": replacements,
        "dropped_obsolete": dropped,
        "result": len(result["entries"]),
    }


def _validate_source_document(
    document: dict[str, Any],
    *,
    valid_ids: set[str],
    contracts: list[dict[str, Any]],
) -> None:
    allowed_keys = {
        key
        for keys in compact_builder.SOURCE_KEYS_BY_CONTRACT.values()
        for key in keys
    } | {"trajectory_geometry", "looming_duration_kinematics", "trial_sequence_response"}
    valid_statuses = (
        set(compact_builder.STATUS_LEGEND)
        | set(compact_builder.LEGACY_SOURCE_STATUSES)
    ) - {"mixed_across_studies"}
    seen: set[str] = set()
    review_lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for index, entry in enumerate(document.get("entries", [])):
        row_id = str(entry.get("study_row_id") or "").strip()
        if not row_id or row_id in seen:
            raise MergeError(f"Duplicate or blank source-review row: entries[{index}]/{row_id}")
        seen.add(row_id)
        if row_id not in valid_ids:
            raise MergeError(f"Unknown source-review study_row_id: {row_id}")
        for field in ("source_type", "source_file"):
            if not str(entry.get(field) or "").strip():
                raise MergeError(f"Source-review entry lacks {field}: {row_id}")
        reviews = entry.get("contracts")
        if not isinstance(reviews, dict):
            raise MergeError(f"Source-review contracts must be an object: {row_id}")
        unknown = sorted(set(reviews) - allowed_keys)
        if unknown:
            raise MergeError(f"Unknown source contract(s) on {row_id}: {', '.join(unknown)}")
        for source_key, review in reviews.items():
            if not isinstance(review, dict):
                raise MergeError(f"Source contract review must be an object: {row_id}/{source_key}")
            status = str(review.get("status") or "")
            if status not in valid_statuses:
                raise MergeError(f"Unknown source-review status {status}: {row_id}/{source_key}")
            if not str(review.get("page_or_section") or "").strip():
                raise MergeError(f"Source review lacks page_or_section: {row_id}/{source_key}")
            compact_builder._validate_source_component_reviews(
                row_id, source_key, review, contracts
            )
            review_lookup[(row_id, source_key)] = review

    for row_id in seen:
        for contract in contracts:
            if contract["column_key"] in {
                compact_builder.STRUCTURE_CONTRACT_KEY,
                compact_builder.MEASUREMENT_CONTRACT_KEY,
            }:
                continue
            override = compact_builder._source_override_for_contract(
                row_id, contract, review_lookup
            )
            if override is None:
                continue
            finalized = compact_builder._finalize_source_override(contract, override)
            compact_builder._validate_source_override(row_id, contract, finalized)


def _validate_structured_documents(
    *,
    structure: dict[str, Any],
    measurement: dict[str, Any],
    valid_ids: set[str],
    contract_document: dict[str, Any],
) -> None:
    contracts = {
        contract["column_key"]: contract for contract in contract_document["contracts"]
    }
    vocabularies = contract_document.get("controlled_vocabularies", {})
    with tempfile.TemporaryDirectory(prefix="pps-review-merge-") as temp_name:
        temp_dir = Path(temp_name)
        structure_path = temp_dir / "study_structure_reviews.v1.json"
        measurement_path = temp_dir / "measurement_acquisition_reviews.v1.json"
        structure_path.write_text(json.dumps(structure), encoding="utf-8")
        measurement_path.write_text(json.dumps(measurement), encoding="utf-8")
        old_structure_path = compact_builder.STRUCTURE_REVIEW_PATH
        old_measurement_path = compact_builder.MEASUREMENT_REVIEW_PATH
        try:
            compact_builder.STRUCTURE_REVIEW_PATH = structure_path
            compact_builder.MEASUREMENT_REVIEW_PATH = measurement_path
            compact_builder._load_structure_reviews(
                valid_study_row_ids=valid_ids,
                contract=contracts[compact_builder.STRUCTURE_CONTRACT_KEY],
                controlled_vocabularies=vocabularies,
            )
            compact_builder._load_measurement_reviews(
                valid_study_row_ids=valid_ids,
                contract=contracts[compact_builder.MEASUREMENT_CONTRACT_KEY],
                controlled_vocabularies=vocabularies,
            )
        finally:
            compact_builder.STRUCTURE_REVIEW_PATH = old_structure_path
            compact_builder.MEASUREMENT_REVIEW_PATH = old_measurement_path


def _atomic_write_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _parse_batches(raw: str) -> list[str]:
    batches = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not batches or len(batches) != len(set(batches)):
        raise MergeError("--expected-batches must contain unique comma-separated names")
    for batch in batches:
        if not batch.replace("_", "").isalnum():
            raise MergeError(f"Unsafe batch name: {batch!r}")
    return batches


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-dir", type=Path, default=DEFAULT_BATCH_DIR, help="Directory containing fragments"
    )
    parser.add_argument(
        "--expected-batches",
        required=True,
        help="Comma-separated batch names; all three review fragments are required for each",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Atomically replace canonical files after the complete candidate validates",
    )
    args = parser.parse_args()

    batches = _parse_batches(args.expected_batches)
    batch_dir = args.batch_dir.resolve()
    fragment_paths: dict[str, list[Path]] = {kind: [] for kind in REVIEW_SPECS}
    registry_paths: list[Path] = []
    for batch in batches:
        for kind in REVIEW_SPECS:
            path = batch_dir / f"batch_{batch}_{kind}_reviews.json"
            if not path.is_file():
                raise MergeError(f"Batch {batch} is incomplete; missing {path}")
            fragment_paths[kind].append(path)
        registry_path = batch_dir / f"batch_{batch}_registry_entries.json"
        if registry_path.is_file():
            registry_paths.append(registry_path)

    network = _load_json(NETWORK_PATH)
    if network.get("schema") != "pps-publication-citation-network.v3":
        raise MergeError("Unexpected publication-network schema")
    contract_document = _load_json(CONTRACT_PATH)
    canonical_registry = _load_json(REGISTRY_PATH)
    registry, changed_nodes, proposal_count = _compose_registry(
        canonical_registry, registry_paths, network
    )
    valid_order = _study_row_order(network, registry)
    valid_ids = set(valid_order)

    candidates: dict[str, dict[str, Any]] = {}
    stats: dict[str, dict[str, int]] = {}
    canonical_reviews = {
        kind: _load_json(AUDIT_DIR / spec["filename"])
        for kind, spec in REVIEW_SPECS.items()
    }
    for kind, spec in REVIEW_SPECS.items():
        candidates[kind], stats[kind] = _compose_review(
            kind=kind,
            canonical=canonical_reviews[kind],
            fragment_paths=fragment_paths[kind],
            valid_order=valid_order,
            changed_registry_nodes=changed_nodes,
        )

    for node_id in changed_nodes:
        replacement_ids = {
            row_id for row_id in valid_order if row_id.split("::", 1)[0] == node_id
        }
        for kind, canonical in canonical_reviews.items():
            canonical_ids = {
                str(entry.get("study_row_id") or "")
                for entry in canonical.get("entries", [])
            }
            obsolete_ids = {
                row_id
                for row_id in canonical_ids
                if row_id.split("::", 1)[0] == node_id and row_id not in valid_ids
            }
            if not obsolete_ids:
                continue
            incoming_ids = {
                str(entry.get("study_row_id") or "")
                for path in fragment_paths[kind]
                for entry in _load_json(path).get("entries", [])
            }
            if not replacement_ids.issubset(incoming_ids):
                missing = sorted(replacement_ids - incoming_ids)
                raise MergeError(
                    f"Registry split would delete canonical {kind} row(s) "
                    f"{', '.join(sorted(obsolete_ids))} without all replacement IDs: "
                    + ", ".join(missing)
                )

    _validate_source_document(
        candidates["source"],
        valid_ids=valid_ids,
        contracts=contract_document["contracts"],
    )
    _validate_structured_documents(
        structure=candidates["structure"],
        measurement=candidates["measurement"],
        valid_ids=valid_ids,
        contract_document=contract_document,
    )

    if args.apply:
        _atomic_write_json(REGISTRY_PATH, registry)
        for kind, spec in REVIEW_SPECS.items():
            _atomic_write_json(AUDIT_DIR / spec["filename"], candidates[kind])

    report = {
        "mode": "apply" if args.apply else "check",
        "expected_batches": batches,
        "registry_fragment_count": len(registry_paths),
        "registry_proposal_count": proposal_count,
        "changed_registry_node_count": len(changed_nodes),
        "resulting_study_row_count": len(valid_order),
        "reviews": stats,
        "written": bool(args.apply),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
