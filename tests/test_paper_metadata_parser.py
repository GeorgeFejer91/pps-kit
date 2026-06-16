from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from tools.paper_metadata_parser import run_audit
from tools.paper_metadata_parser.bundle import build_inventory
from tools.paper_metadata_parser.parser import (
    CONFIDENCE_LABELS,
    EXTRACTION_STATUSES,
    FIELD_STATUSES,
    PDF_STATUSES,
    SEGMENT_FIELDS,
    SUPPLEMENT_STATUSES,
    TOTAL_SEGMENT_FIELD_COUNT,
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
    assert sum(summary["automated_evidence_status_counts"].values()) == 74
    assert summary["automated_evidence_field_total"] == sum(
        int(record["automated_evidence_mining"]["field_count"]) for record in audit_records
    )
    assert summary["semantic_review_strategy_count"] == 5
    assert summary["semantic_review_pass_total"] == 5 * summary["record_count"]
    assert sum(summary["semantic_review_pass_status_counts"].values()) == summary["semantic_review_pass_total"]


def test_paper_metadata_schema_and_status_values_are_valid():
    schema = json.loads((AUDIT_DIR / "extraction_schema.json").read_text(encoding="utf-8"))
    tool_schema = json.loads((ROOT / "tools" / "paper_metadata_parser" / "schema.json").read_text(encoding="utf-8"))
    audit_records = load_jsonl(AUDIT_DIR / "metadata_audit.jsonl")

    assert set(schema["pdf_statuses"]) == set(PDF_STATUSES) == set(tool_schema["pdf_statuses"])
    assert set(schema["supplement_statuses"]) == set(SUPPLEMENT_STATUSES) == set(tool_schema["supplement_statuses"])
    assert set(schema["extraction_statuses"]) == set(EXTRACTION_STATUSES) == set(tool_schema["extraction_statuses"])
    assert set(schema["field_statuses"]) == set(FIELD_STATUSES) == set(tool_schema["field_statuses"])
    assert set(schema["confidence_labels"]) == set(CONFIDENCE_LABELS) == set(tool_schema["confidence_labels"])
    assert schema["automated_evidence"] == tool_schema["automated_evidence"]
    assert schema["supplement_extraction"] == tool_schema["supplement_extraction"]
    assert ".pdf" in schema["supplement_extraction"]["supported_local_formats"]
    assert schema["manual_reviews"] == tool_schema["manual_reviews"]
    assert schema["local_artifact_conventions"]["main_pdf_filename"].startswith("artifacts/")

    for record in audit_records:
        assert record["pdf_status"] in PDF_STATUSES, record["record_id"]
        assert record["supplement_status"] in SUPPLEMENT_STATUSES, record["record_id"]
        assert record["extraction_status"] in EXTRACTION_STATUSES, record["record_id"]
        assert record["metadata_confidence_label"] in CONFIDENCE_LABELS, record["record_id"]
        assert 0.0 <= float(record["metadata_confidence_score"]) <= 1.0, record["record_id"]
        assert record["metadata_confidence_basis"], record["record_id"]
        assert isinstance(record["supplement_extracted_text_files"], list), record["record_id"]
        assert isinstance(record["supplement_extraction_status_counts"], dict), record["record_id"]
        for extracted_file in record["supplement_extracted_text_files"]:
            assert extracted_file.startswith("artifacts/paper_metadata_audit/extracted/supplements/"), record["record_id"]
        evidence = record["automated_evidence_mining"]
        assert evidence["status"] in schema["automated_evidence"]["status_values"], record["record_id"]
        assert 0 <= int(evidence["field_count"]) <= TOTAL_SEGMENT_FIELD_COUNT, record["record_id"]
        assert 0.0 <= float(evidence["coverage_ratio"]) <= 1.0, record["record_id"]
        review_passes = evidence["semantic_review_passes"]
        assert len(review_passes) == schema["automated_evidence"]["semantic_review_strategy_count"], record["record_id"]
        assert len({review_pass["strategy"] for review_pass in review_passes}) == len(review_passes), record["record_id"]
        for review_pass in review_passes:
            assert review_pass["status"] in schema["automated_evidence"]["semantic_review_pass_status_values"]
            assert review_pass["purpose"], record["record_id"]
            assert int(review_pass["hit_count"]) >= 0, record["record_id"]
        assert record["schema"] == "pps-paper-metadata-audit-record.v1"
        assert record["review_attempts"], record["record_id"]
        for segment_fields in record["segment_field_audit"].values():
            for field in segment_fields.values():
                assert field["status"] in FIELD_STATUSES, record["record_id"]
                assert {"value", "source_file", "page_or_section", "evidence_note"} <= set(field)
                assert len(field["value"]) <= 320, record["record_id"]
                if field["status"] == "inferred_low_confidence":
                    assert field["value"].startswith("Auto-mined candidates:"), record["record_id"]
                    assert field["source_file"].startswith("artifacts/paper_metadata_audit/extracted/"), record["record_id"]
                    assert field["page_or_section"], record["record_id"]

        if record["coverage_category"] == "adjacent_out_of_scope":
            assert record["pdf_status"] == "not_applicable"
            assert record["supplement_status"] == "not_applicable"
            assert record["metadata_confidence_label"] == "not_applicable"
            assert record["automated_evidence_mining"]["status"] == "not_applicable"
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
                assert record["automated_evidence_mining"]["status"] in {"source_mined", "no_extracted_source"}
                if record["automated_evidence_mining"]["status"] == "source_mined":
                    assert {
                        review_pass["status"]
                        for review_pass in record["automated_evidence_mining"]["semantic_review_passes"]
                    } <= {"completed", "completed_no_hits"}


def test_doi_inventory_tracks_every_literature_record():
    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    summary = json.loads((AUDIT_DIR / "audit_summary.json").read_text(encoding="utf-8"))
    doi_rows = load_csv(AUDIT_DIR / "doi_inventory.csv")
    coverage_ids = {record["record_id"] for record in coverage["literature_records"]}
    doi_ids = {row["record_id"] for row in doi_rows}

    assert doi_ids == coverage_ids
    assert len(doi_rows) == summary["record_count"] == 74
    assert summary["doi_record_count"] == sum(1 for row in doi_rows if row["doi"])
    assert summary["missing_doi_record_count"] == sum(1 for row in doi_rows if not row["doi"])
    for row in doi_rows:
        assert row["coverage_category"]
        if row["doi"]:
            assert row["doi_url"] == f"https://doi.org/{row['doi']}"
        else:
            assert row["doi_url"] == ""


def test_manual_reviews_are_schema_valid_and_source_pointer_only():
    manual_dir = AUDIT_DIR / "manual_reviews"
    review_paths = sorted(manual_dir.glob("*.json"))
    assert review_paths

    coverage = json.loads(COVERAGE_PATH.read_text(encoding="utf-8"))
    coverage_ids = {record["record_id"] for record in coverage["literature_records"]}
    index_rows = load_csv(AUDIT_DIR / "manual_review_index.csv")
    indexed_ids = {row["record_id"] for row in index_rows}
    review_ids = {path.stem for path in review_paths}
    expected_segments = set(SEGMENT_FIELDS)
    expected_field_count = sum(len(fields) for fields in SEGMENT_FIELDS.values())

    assert indexed_ids == review_ids
    assert expected_field_count == TOTAL_SEGMENT_FIELD_COUNT

    for path in review_paths:
        review = json.loads(path.read_text(encoding="utf-8"))
        assert review["schema"] == "pps-paper-metadata-manual-review.v1"
        assert review["record_id"] == path.stem
        assert review["record_id"] in coverage_ids
        assert review["confidence_label"] in CONFIDENCE_LABELS
        assert 0.0 <= float(review["confidence_score"]) <= 1.0
        assert len(review["review_attempts"]) >= 5
        assert len(review["source_checks"]) >= 3
        assert not json.dumps(review).count("\n\n")

        for source_check in review["source_checks"]:
            source = source_check["source"]
            assert "C:\\" not in source
            assert "/Users/" not in source
            if source.startswith("artifacts/"):
                assert source.startswith("artifacts/paper_metadata_audit/")

        segment_audit = review["segment_field_audit"]
        assert set(segment_audit) == expected_segments
        status_counts: dict[str, int] = {}
        field_count = 0
        for segment, fields in SEGMENT_FIELDS.items():
            expected_fields = {field["key"] for field in fields}
            assert set(segment_audit[segment]) == expected_fields
            for field_key, field in segment_audit[segment].items():
                field_count += 1
                status = field["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
                assert status in FIELD_STATUSES, f"{path.name}:{field_key}"
                assert len(field["value"]) <= 500
                assert len(field["evidence_note"]) <= 260
                assert "C:\\" not in field["source_file"]
                assert "/Users/" not in field["source_file"]
                assert not field["value"].startswith("Auto-mined candidates:")
                if status in {"reported", "derived", "not_reported_after_review"}:
                    assert field["source_file"], f"{path.name}:{field_key}"
                    assert field["page_or_section"], f"{path.name}:{field_key}"

        assert field_count == TOTAL_SEGMENT_FIELD_COUNT
        assert review["field_status_counts"] == dict(sorted(status_counts.items()))


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


def test_paper_metadata_parser_mines_fallback_pdf_text(tmp_path: Path):
    repo_root = tmp_path
    coverage_path = repo_root / "coverage.json"
    coverage_path.write_text(
        json.dumps(
            {
                "schema": "test",
                "literature_records": [
                    {
                        "record_id": "fallback_paper",
                        "citation_short": "Fallback Paper (2026)",
                        "doi": "10.0000/fallback",
                        "source_basis": ["fixture"],
                        "current_template_ids": [],
                        "coverage_category": "not_yet_templated_missing_publication_parameters",
                        "audiotactile_task_family": "audio-tactile PPS fixture",
                        "can_recreate_audiotactile_components_now": False,
                        "blocking_constraint_ids": ["missing_core_soa_iti_baseline_repetition_parameters"],
                        "missing_publication_parameters": [],
                    }
                ],
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    pdf_dir = repo_root / "artifacts" / "paper_metadata_audit" / "publication_pdfs"
    fallback_dir = repo_root / "artifacts" / "paper_metadata_audit" / "extracted" / "fallback" / "fallback_paper"
    pdf_dir.mkdir(parents=True)
    fallback_dir.mkdir(parents=True)
    (pdf_dir / "fallback_paper.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (fallback_dir / "fallback_paper.fallback.txt").write_text(
        "\n\n[page 3]\n"
        "Methods described white noise approaching from 75 cm with a 300 ms stimulus duration. "
        "The audio-tactile trials used tactile stimulation for 100 ms and SOA values of 300 ms. "
        "Catch trials and randomized blocks contained 250 trials in total.\n",
        encoding="utf-8",
    )

    summary = run_audit(
        repo_root,
        coverage_path=Path("coverage.json"),
        audit_dir=Path("For-AI/audit"),
        artifact_dir=Path("artifacts/paper_metadata_audit"),
        parse_downloaded=False,
    )
    record = load_jsonl(repo_root / "For-AI" / "audit" / "metadata_audit.jsonl")[0]

    assert summary["automated_evidence_status_counts"] == {"source_mined": 1}
    assert record["metadata_confidence_label"] == "partial_extraction"
    assert record["automated_evidence_mining"]["source_files"] == [
        "artifacts/paper_metadata_audit/extracted/fallback/fallback_paper/fallback_paper.fallback.txt"
    ]
    stimulus = record["segment_field_audit"]["segment_1_stimulus_reconstruction"]["stimulus_type"]
    assert stimulus["status"] == "inferred_low_confidence"
    assert stimulus["source_file"].endswith("fallback_paper.fallback.txt")
    assert stimulus["page_or_section"] == "source page/section(s) 3"


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


def test_local_artifact_inventory_is_github_safe():
    inventory_path = AUDIT_DIR / "local_artifact_inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))

    assert inventory["schema"] == "pps-paper-metadata-local-artifact-inventory.v1"
    assert inventory["artifact_root"] == "artifacts/paper_metadata_audit"
    assert inventory["artifact_file_count"] == len(inventory["files"])
    assert inventory["local_bundle"]["relative_path"].startswith("artifacts/paper_metadata_audit/resume_bundles/")
    assert "copyright_boundary" in inventory
    for entry in inventory["files"]:
        assert entry["relative_path"].startswith("artifacts/paper_metadata_audit/")
        assert not entry["relative_path"].startswith(str(ROOT))
        assert "C:\\" not in entry["relative_path"]
        assert len(entry["sha256"]) == 64
        assert entry["size_bytes"] >= 0


def test_bundle_inventory_excludes_tooling_and_creates_local_zip(tmp_path: Path):
    repo_root = tmp_path
    artifact_root = repo_root / "artifacts" / "paper_metadata_audit"
    (artifact_root / "publication_pdfs").mkdir(parents=True)
    (artifact_root / "tooling" / "jdk").mkdir(parents=True)
    (artifact_root / "publication_pdfs" / "example.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    (artifact_root / "tooling" / "jdk" / "java.exe").write_bytes(b"local runtime")

    inventory = build_inventory(repo_root)

    assert inventory["artifact_file_count"] == 1
    assert inventory["category_counts"] == {"publication_pdf": 1}
    assert inventory["files"][0]["relative_path"] == "artifacts/paper_metadata_audit/publication_pdfs/example.pdf"
    bundle_path = repo_root / inventory["local_bundle"]["relative_path"]
    assert bundle_path.exists()
