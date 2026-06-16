from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from tools.paper_metadata_parser import run_audit
from tools.paper_metadata_parser.parser import (
    CONFIDENCE_LABELS,
    EXTRACTION_STATUSES,
    FIELD_STATUSES,
    PDF_STATUSES,
    SUPPLEMENT_STATUSES,
)


ROOT = Path(__file__).resolve().parents[1]
COVERAGE_PATH = ROOT / "assets" / "preloads" / "audiotactile_literature_coverage.json"
AUDIT_DIR = ROOT / "For-AI" / "audiotactile-paper-metadata-audit"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_paper_metadata_audit_covers_literature_database():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    summary = json.loads((AUDIT_DIR / "audit_summary.json").read_text(encoding="utf-8"))
    audit_records = load_jsonl(AUDIT_DIR / "metadata_audit.jsonl")
    checklist_rows = load_csv(AUDIT_DIR / "running_checklist.csv")
    paper_audits = sorted((AUDIT_DIR / "paper_audits").glob("*.md"))

    coverage_ids = {record["record_id"] for record in coverage["literature_records"]}
    audit_ids = {record["record_id"] for record in audit_records}
    checklist_ids = {row["record_id"] for row in checklist_rows}

    assert summary["schema"] == "pps-paper-metadata-audit-summary.v1"
    assert summary["record_count"] == len(coverage["literature_records"]) == 74
    assert audit_ids == coverage_ids
    assert checklist_ids == coverage_ids
    assert len(paper_audits) == 74
    assert sum(summary["pdf_status_counts"].values()) == 74
    assert sum(summary["supplement_status_counts"].values()) == 74
    assert sum(summary["extraction_status_counts"].values()) == 74
    assert summary["pdf_status_counts"].get("not_applicable") == 5
    assert summary["supplement_status_counts"].get("not_applicable") == 5


def test_paper_metadata_schema_and_status_values_are_valid():
    schema = json.loads((AUDIT_DIR / "extraction_schema.json").read_text(encoding="utf-8"))
    tool_schema = json.loads((ROOT / "tools" / "paper_metadata_parser" / "schema.json").read_text(encoding="utf-8"))
    audit_records = load_jsonl(AUDIT_DIR / "metadata_audit.jsonl")

    assert set(schema["pdf_statuses"]) == set(PDF_STATUSES) == set(tool_schema["pdf_statuses"])
    assert set(schema["supplement_statuses"]) == set(SUPPLEMENT_STATUSES) == set(tool_schema["supplement_statuses"])
    assert set(schema["extraction_statuses"]) == set(EXTRACTION_STATUSES) == set(tool_schema["extraction_statuses"])
    assert set(schema["field_statuses"]) == set(FIELD_STATUSES) == set(tool_schema["field_statuses"])
    assert set(schema["confidence_labels"]) == set(CONFIDENCE_LABELS) == set(tool_schema["confidence_labels"])
    assert schema["local_artifact_conventions"]["main_pdf_filename"].startswith("artifacts/")

    for record in audit_records:
        assert record["pdf_status"] in PDF_STATUSES, record["record_id"]
        assert record["supplement_status"] in SUPPLEMENT_STATUSES, record["record_id"]
        assert record["extraction_status"] in EXTRACTION_STATUSES, record["record_id"]
        assert record["metadata_confidence_label"] in CONFIDENCE_LABELS, record["record_id"]
        assert 0.0 <= float(record["metadata_confidence_score"]) <= 1.0, record["record_id"]
        assert record["metadata_confidence_basis"], record["record_id"]
        assert record["schema"] == "pps-paper-metadata-audit-record.v1"
        assert record["review_attempts"], record["record_id"]
        for segment_fields in record["segment_field_audit"].values():
            for field in segment_fields.values():
                assert field["status"] in FIELD_STATUSES, record["record_id"]
                assert {"value", "source_file", "page_or_section", "evidence_note"} <= set(field)

        if record["coverage_category"] == "adjacent_out_of_scope":
            assert record["pdf_status"] == "not_applicable"
            assert record["supplement_status"] == "not_applicable"
            assert record["metadata_confidence_label"] == "not_applicable"
            for segment_fields in record["segment_field_audit"].values():
                assert {field["status"] for field in segment_fields.values()} == {"not_applicable"}
        else:
            assert record["pdf_status"] in set(PDF_STATUSES) - {"not_applicable"}
            assert record["supplement_status"] in set(SUPPLEMENT_STATUSES) - {"not_applicable"}
            if record["pdf_status"] == "downloaded":
                assert record["metadata_confidence_label"] in {
                    "source_acquired_unreviewed",
                    "partial_extraction",
                    "high_confidence_extraction",
                }


def test_missing_pdf_request_list_tracks_main_pdfs_and_supplements():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    requests = load_csv(AUDIT_DIR / "missing_pdf_request_list.csv")
    in_scope_ids = {
        record["record_id"]
        for record in coverage["literature_records"]
        if record["coverage_category"] != "adjacent_out_of_scope"
    }

    assert len(in_scope_ids) == 69
    by_record: dict[str, set[str]] = {}
    for request in requests:
        by_record.setdefault(request["record_id"], set()).add(request["requested_item"])
        assert request["target_location"].startswith("artifacts/paper_metadata_audit/")
        assert not request["target_location"].startswith(str(ROOT))

    assert set(by_record) <= in_scope_ids
    records = {record["record_id"]: record for record in load_jsonl(AUDIT_DIR / "metadata_audit.jsonl")}
    for record_id in in_scope_ids:
        requested_items = by_record.get(record_id, set())
        record = records[record_id]
        if record["pdf_status"] != "downloaded":
            assert "publication_pdf" in requested_items
        if record["supplement_status"] not in {"downloaded", "not_found"}:
            assert "supplement_or_methods_files" in requested_items


def test_paper_metadata_parser_can_inventory_downloaded_local_files(tmp_path: Path):
    repo_root = tmp_path
    coverage_path = repo_root / "coverage.json"
    coverage_path.write_text(
        json.dumps(
            {
                "schema": "test",
                "literature_records": [
                    {
                        "record_id": "paper_with_pdf",
                        "citation_short": "Paper With PDF (2026)",
                        "doi": "10.0000/example",
                        "source_basis": ["fixture"],
                        "current_template_ids": [],
                        "coverage_category": "not_yet_templated_missing_publication_parameters",
                        "audiotactile_task_family": "fixture task",
                        "can_recreate_audiotactile_components_now": False,
                        "blocking_constraint_ids": ["missing_core_soa_iti_baseline_repetition_parameters"],
                        "missing_publication_parameters": ["fixture missing values"],
                    },
                    {
                        "record_id": "adjacent_record",
                        "citation_short": "Adjacent Record (2026)",
                        "doi": "",
                        "source_basis": ["fixture"],
                        "current_template_ids": [],
                        "coverage_category": "adjacent_out_of_scope",
                        "audiotactile_task_family": "not an audiotactile PPS task",
                        "can_recreate_audiotactile_components_now": False,
                        "blocking_constraint_ids": [],
                        "missing_publication_parameters": [],
                    },
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    pdf_dir = repo_root / "artifacts" / "paper_metadata_audit" / "publication_pdfs"
    supplement_dir = repo_root / "artifacts" / "paper_metadata_audit" / "supplements" / "paper_with_pdf"
    pdf_dir.mkdir(parents=True)
    supplement_dir.mkdir(parents=True)
    (pdf_dir / "paper_with_pdf.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (supplement_dir / "table.csv").write_text("field,value\n", encoding="utf-8")

    summary = run_audit(
        repo_root,
        coverage_path=Path("coverage.json"),
        audit_dir=Path("For-AI/audit"),
        artifact_dir=Path("artifacts/paper_metadata_audit"),
        parse_downloaded=False,
    )
    records = load_jsonl(repo_root / "For-AI" / "audit" / "metadata_audit.jsonl")
    by_id = {record["record_id"]: record for record in records}

    assert summary["record_count"] == 2
    assert by_id["paper_with_pdf"]["pdf_status"] == "downloaded"
    assert by_id["paper_with_pdf"]["supplement_status"] == "downloaded"
    assert by_id["paper_with_pdf"]["metadata_confidence_label"] == "source_acquired_unreviewed"
    assert by_id["paper_with_pdf"]["pdf_file"] == "artifacts/paper_metadata_audit/publication_pdfs/paper_with_pdf.pdf"
    assert by_id["adjacent_record"]["pdf_status"] == "not_applicable"
    assert by_id["adjacent_record"]["supplement_status"] == "not_applicable"


def test_tracked_audit_files_do_not_include_pdfs_or_extracted_full_text():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    tracked = set(result.stdout.splitlines())
    forbidden_suffixes = {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ods",
        ".zip",
        ".txt",
    }

    assert not [path for path in tracked if path.startswith("artifacts/paper_metadata_audit/")]
    assert not [
        path
        for path in tracked
        if path.startswith("For-AI/audiotactile-paper-metadata-audit/")
        and Path(path).suffix.lower() in forbidden_suffixes
    ]
    for path in AUDIT_DIR.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "C:\\" not in text
            assert "/Users/" not in text
