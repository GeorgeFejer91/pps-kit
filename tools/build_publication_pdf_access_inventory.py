#!/usr/bin/env python3
"""Build the tracked PDF-access inventory from the final acquisition ledger.

The network JSON is the row authority, the completed local acquisition ledger
is the file authority, and ``paper_pdf_access_annotations.json`` is the manual
authority for publications that remain unresolved.  The builder performs no
network access and never copies or embeds publication text.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from pypdf import PdfReader


NETWORK_PATH = Path("src/peripersonal_space_toolkit/dashboard/publication_network.v3.json")
LEDGER_PATH = Path("artifacts/paper_metadata_audit/network_acquisition_status.json")
ANNOTATIONS_PATH = Path("tools/paper_pdf_access_annotations.json")
OUTPUT_DIR = Path("For-AI/audiotactile-paper-metadata-audit")
INVENTORY_FILENAME = "publication_pdf_access_inventory.csv"
REQUEST_FILENAME = "credential_access_request_list.csv"
REQUEST_MARKDOWN_FILENAME = "credential_access_request_list.md"
EXPECTED_NETWORK_SIZE = 94
EXPECTED_ANNOTATION_SCHEMA = "pps-paper-pdf-access-annotations.v1"
VERIFIED_IDENTITIES = {"doi_and_title_match", "doi_match", "title_match"}
NON_CREDENTIAL_CLASSES = {
    "abstract_or_scope_adjacent",
    "associated_or_alternate_full_text",
    "no_main_pdf_for_abstract_record",
    "no_main_pdf_for_project_record",
    "public_full_html",
    "public_full_text_non_pdf",
    "public_pdf_verified_not_local",
}
PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}

INVENTORY_FIELDS = [
    "node_id",
    "title",
    "year",
    "doi",
    "doi_url",
    "ledger_pdf_status",
    "ledger_last_status",
    "local_status",
    "local_path",
    "local_sha256",
    "local_page_count",
    "local_identity_status",
    "public_access_class",
    "public_source",
    "public_source_url",
    "public_license",
    "credentials_required",
    "credential_priority",
    "reason",
    "action",
    "alternate_full_text_notes",
    "checked_date",
]

REQUEST_FIELDS = [
    "credential_priority",
    "node_id",
    "title",
    "year",
    "doi",
    "doi_url",
    "local_target_path",
    "public_source",
    "public_source_url",
    "reason",
    "action",
    "alternate_full_text_notes",
    "checked_date",
]


def normalize_doi(value: str) -> str:
    doi = (value or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.rstrip(". ")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_by_doi(items: list[dict[str, Any]], *, label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in items:
        doi = normalize_doi(str(item.get("doi", "")))
        if not doi:
            raise ValueError(f"{label} contains an item without a DOI")
        if doi in result:
            raise ValueError(f"{label} contains duplicate DOI {doi}")
        result[doi] = item
    return result


def _validate_local_pdf(repo_root: Path, record: dict[str, Any]) -> tuple[str, int]:
    local_path = repo_root / str(record.get("local_file", ""))
    if not local_path.is_file():
        raise ValueError(f"Downloaded ledger record has no local file: {record.get('doi')} -> {local_path}")
    if local_path.read_bytes()[:5] != b"%PDF-":
        raise ValueError(f"Downloaded ledger file has no PDF signature: {local_path}")
    actual_hash = sha256_file(local_path)
    if actual_hash != str(record.get("sha256", "")):
        raise ValueError(f"Ledger SHA-256 does not match local file: {record.get('doi')}")
    reader = PdfReader(local_path, strict=False)
    actual_pages = len(reader.pages)
    if actual_pages <= 0 or actual_pages != int(record.get("page_count", 0)):
        raise ValueError(f"Ledger page count does not match local file: {record.get('doi')}")
    if record.get("identity_status") not in VERIFIED_IDENTITIES:
        raise ValueError(f"Downloaded PDF lacks verified publication identity: {record.get('doi')}")
    return actual_hash, actual_pages


def build_inventory(repo_root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
    network = load_json(repo_root / NETWORK_PATH)
    ledger = load_json(repo_root / LEDGER_PATH)
    annotations_payload = load_json(repo_root / ANNOTATIONS_PATH)

    nodes = network.get("nodes")
    records = ledger.get("records")
    annotations = annotations_payload.get("records")
    if not isinstance(nodes, list) or not isinstance(records, list) or not isinstance(annotations, list):
        raise ValueError("Network, ledger, and annotation files must each contain a record list")
    if len(nodes) != EXPECTED_NETWORK_SIZE:
        raise ValueError(f"Expected {EXPECTED_NETWORK_SIZE} network nodes, found {len(nodes)}")
    if not ledger.get("completed_at") or int(ledger.get("run_target_count", 0)) != EXPECTED_NETWORK_SIZE:
        raise ValueError("Acquisition ledger is not a completed 94-publication pass")
    if annotations_payload.get("schema") != EXPECTED_ANNOTATION_SCHEMA:
        raise ValueError(f"Unexpected annotation schema: {annotations_payload.get('schema')!r}")
    checked_date = str(annotations_payload.get("checked_date", ""))
    try:
        date.fromisoformat(checked_date)
    except ValueError as exc:
        raise ValueError(f"Invalid annotation checked_date: {checked_date!r}") from exc

    nodes_by_doi = _unique_by_doi(nodes, label="network")
    ledger_by_doi = _unique_by_doi(records, label="ledger")
    annotations_by_doi = _unique_by_doi(annotations, label="annotations")
    if set(nodes_by_doi) != set(ledger_by_doi):
        raise ValueError("Completed ledger DOI set does not exactly match the current network")
    unresolved = {doi for doi, record in ledger_by_doi.items() if record.get("pdf_status") != "downloaded"}
    if set(annotations_by_doi) != unresolved:
        missing = sorted(unresolved - set(annotations_by_doi))
        extra = sorted(set(annotations_by_doi) - unresolved)
        raise ValueError(f"Annotations must exactly cover unresolved DOI records; missing={missing}, extra={extra}")

    for doi, annotation in annotations_by_doi.items():
        needs_credentials = annotation.get("credentials_required") is True
        access_class = str(annotation.get("public_access_class", ""))
        priority = str(annotation.get("credential_priority", ""))
        required_text = ["public_source", "public_source_url", "public_license", "reason", "action", "alternate_full_text_notes"]
        if any(not str(annotation.get(field, "")).strip() for field in required_text):
            raise ValueError(f"Incomplete access annotation for {doi}")
        if access_class in NON_CREDENTIAL_CLASSES and needs_credentials:
            raise ValueError(f"Public/alternate access class cannot request credentials: {doi}")
        if needs_credentials and priority not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"Credential request lacks a valid priority: {doi}")
        if not needs_credentials and priority != "none":
            raise ValueError(f"Non-credential record must use priority 'none': {doi}")

    inventory: list[dict[str, str]] = []
    for node in nodes:
        doi = normalize_doi(str(node.get("doi", "")))
        record = ledger_by_doi[doi]
        downloaded = record.get("pdf_status") == "downloaded"
        common = {
            "node_id": str(node.get("id", "")),
            "title": str(node.get("title", "")),
            "year": str(node.get("year", "")),
            "doi": doi,
            "doi_url": f"https://doi.org/{doi}",
            "ledger_pdf_status": str(record.get("pdf_status", "")),
            "ledger_last_status": str(record.get("last_status", "")),
            "local_path": str(record.get("local_file", "")),
            "checked_date": checked_date,
        }
        if downloaded:
            actual_hash, actual_pages = _validate_local_pdf(repo_root, record)
            source = str(record.get("candidate_source", "")) or "pre-existing validated local artifact"
            source_url = str(record.get("downloaded_url", "")) or str(record.get("final_url", ""))
            license_value = str(record.get("license", "")) or "not_established"
            identity_basis = str(record.get("identity_basis", "")).strip()
            row = {
                **common,
                "local_status": "validated_local_main_pdf",
                "local_sha256": actual_hash,
                "local_page_count": str(actual_pages),
                "local_identity_status": str(record.get("identity_status", "")),
                "public_access_class": "valid_local_pdf",
                "public_source": source,
                "public_source_url": source_url,
                "public_license": license_value,
                "credentials_required": "no",
                "credential_priority": "none",
                "reason": "An identity-verified, structurally valid main-article PDF is present locally.",
                "action": "Use the validated local PDF for parameter extraction; review license terms before redistribution.",
                "alternate_full_text_notes": identity_basis or "Validated against the expected publication title or DOI.",
            }
        else:
            annotation = annotations_by_doi[doi]
            row = {
                **common,
                "local_status": "no_valid_local_main_pdf",
                "local_sha256": "",
                "local_page_count": "0",
                "local_identity_status": str(record.get("identity_status", "not_checked")),
                "public_access_class": str(annotation["public_access_class"]),
                "public_source": str(annotation["public_source"]),
                "public_source_url": str(annotation["public_source_url"]),
                "public_license": str(annotation["public_license"]),
                "credentials_required": "yes" if annotation["credentials_required"] else "no",
                "credential_priority": str(annotation["credential_priority"]),
                "reason": str(annotation["reason"]),
                "action": str(annotation["action"]),
                "alternate_full_text_notes": str(annotation["alternate_full_text_notes"]),
            }
        inventory.append(row)

    requests = [
        {
            "credential_priority": row["credential_priority"],
            "node_id": row["node_id"],
            "title": row["title"],
            "year": row["year"],
            "doi": row["doi"],
            "doi_url": row["doi_url"],
            "local_target_path": row["local_path"],
            "public_source": row["public_source"],
            "public_source_url": row["public_source_url"],
            "reason": row["reason"],
            "action": row["action"],
            "alternate_full_text_notes": row["alternate_full_text_notes"],
            "checked_date": row["checked_date"],
        }
        for row in inventory
        if row["credentials_required"] == "yes"
    ]
    requests.sort(key=lambda row: (PRIORITY_ORDER[row["credential_priority"]], int(row["year"] or 0), row["doi"]))
    summary = {
        "checked_date": checked_date,
        "network_count": len(inventory),
        "local_pdf_count": sum(row["local_status"] == "validated_local_main_pdf" for row in inventory),
        "unresolved_count": sum(row["local_status"] != "validated_local_main_pdf" for row in inventory),
        "credential_request_count": len(requests),
        "access_class_counts": dict(sorted(Counter(row["public_access_class"] for row in inventory).items())),
        "priority_counts": dict(sorted(Counter(row["credential_priority"] for row in requests).items(), key=lambda item: PRIORITY_ORDER[item[0]])),
        "ledger_completed_at": str(ledger["completed_at"]),
    }
    return inventory, requests, summary


def render_csv(rows: list[dict[str, str]], fields: list[str]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(requests: list[dict[str, str]], summary: dict[str, Any]) -> str:
    lines = [
        "# Publication PDF credential-access request list",
        "",
        f"Checked {summary['checked_date']} against the completed {summary['network_count']}-publication acquisition ledger "
        f"({summary['local_pdf_count']} validated local PDFs; {summary['unresolved_count']} without a local main PDF).",
        "",
        f"Exactly **{summary['credential_request_count']} publications** still need institutional or author access. "
        "Public PDFs/HTML, public non-PDF manuscripts, thesis/preprint substitutes, abstract/project records without a distinct main PDF, "
        "and scope-adjacent records are deliberately excluded.",
        "",
        "| Priority | Year | Publication | DOI | Why credentials are needed | Requested action |",
        "|---|---:|---|---|---|---|",
    ]
    for row in requests:
        title = _markdown_escape(row["title"])
        reason = _markdown_escape(row["reason"])
        action = _markdown_escape(row["action"])
        lines.append(
            f"| {row['credential_priority']} | {row['year']} | {title} | "
            f"[{row['doi']}]({row['doi_url']}) | {reason} | {action} |"
        )
    lines.extend(
        [
            "",
            "The companion CSV includes the exact local target path, current public source, and alternate-full-text note for each request. "
            "PDFs remain in the ignored local artifact tree and must not be committed or redistributed without a license review.",
            "",
        ]
    )
    return "\n".join(lines)


def generated_outputs(repo_root: Path) -> tuple[dict[str, str], dict[str, Any]]:
    inventory, requests, summary = build_inventory(repo_root)
    return (
        {
            INVENTORY_FILENAME: render_csv(inventory, INVENTORY_FIELDS),
            REQUEST_FILENAME: render_csv(requests, REQUEST_FIELDS),
            REQUEST_MARKDOWN_FILENAME: render_markdown(requests, summary),
        },
        summary,
    )


def write_or_check(repo_root: Path, output_dir: Path, *, check: bool) -> dict[str, Any]:
    outputs, summary = generated_outputs(repo_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    stale: list[str] = []
    for filename, content in outputs.items():
        path = output_dir / filename
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path))
        else:
            path.write_text(content, encoding="utf-8", newline="")
    if stale:
        raise SystemExit("Generated publication-access outputs are stale: " + ", ".join(stale))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--check", action="store_true", help="Fail if tracked outputs differ from a fresh build")
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else repo_root / OUTPUT_DIR
    summary = write_or_check(repo_root, output_dir, check=args.check)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
