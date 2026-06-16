from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


PARSER_VERSION = "0.2.0"

COVERAGE_PATH = Path("assets/preloads/audiotactile_literature_coverage.json")
AUDIT_DIR = Path("For-AI/audiotactile-paper-metadata-audit")
ARTIFACT_DIR = Path("artifacts/paper_metadata_audit")
PDF_DIR = ARTIFACT_DIR / "publication_pdfs"
SUPPLEMENT_DIR = ARTIFACT_DIR / "supplements"
EXTRACTED_DIR = ARTIFACT_DIR / "extracted"
ACQUISITION_STATUS_PATH = ARTIFACT_DIR / "acquisition_status.json"
LOCAL_JAVA_ROOT = ARTIFACT_DIR / "tooling" / "jdk"

PDF_STATUSES = (
    "downloaded",
    "open_access_unavailable",
    "paywalled",
    "needs_user_download",
    "not_applicable",
    "bad_pdf",
)
SUPPLEMENT_STATUSES = (
    "downloaded",
    "not_found",
    "needs_user_download",
    "paywalled",
    "not_applicable",
    "not_checked",
)
EXTRACTION_STATUSES = (
    "parsed",
    "parsed_with_warnings",
    "failed",
    "pending_pdf",
)
FIELD_STATUSES = (
    "reported",
    "derived",
    "inferred_low_confidence",
    "not_reported_after_review",
    "not_applicable",
    "source_unavailable",
)
CONFIDENCE_LABELS = (
    "not_applicable",
    "pending_source",
    "source_unavailable",
    "source_acquired_unreviewed",
    "partial_extraction",
    "high_confidence_extraction",
)

ADJACENT_CATEGORY = "adjacent_out_of_scope"

SEGMENT_FIELDS: dict[str, list[dict[str, str]]] = {
    "segment_1_stimulus_reconstruction": [
        {
            "key": "stimulus_type",
            "label": "Stimulus type",
            "description": "Noise, tone, ecological sound, speech, or custom/baked stimulus class.",
        },
        {
            "key": "source_provenance",
            "label": "Source/provenance",
            "description": "Original asset, generated stimulus, licensed set, apparatus source, or supplement file.",
        },
        {
            "key": "trajectory_count",
            "label": "Number of trajectories/tones",
            "description": "Distinct looming/receding/static paths, tones, or auditory conditions.",
        },
        {
            "key": "trajectory_path",
            "label": "Trajectory path",
            "description": "Start/end distance, direction, body anchor, azimuth/elevation, and spatial coordinate frame.",
        },
        {
            "key": "stimulus_duration",
            "label": "Duration",
            "description": "Auditory stimulus duration and any pre/post padding.",
        },
        {
            "key": "stimulus_speed",
            "label": "Speed/path length",
            "description": "Motion speed, path length, propagation timing, or distance-at-time mapping.",
        },
        {
            "key": "auditory_conditions",
            "label": "Auditory conditions",
            "description": "Valence, direction, semantic, movement, or apparatus conditions affecting the auditory stimulus.",
        },
        {
            "key": "gain_envelope",
            "label": "Gain/envelope",
            "description": "SPL, intensity law, gain curve, cross-fade, or amplitude-field information.",
        },
        {
            "key": "renderer_or_apparatus",
            "label": "Renderer/HRTF/speaker apparatus",
            "description": "Headphones, HRTF, Unity/3D Tune-In, physical speakers, arrays, or other rendering provenance.",
        },
    ],
    "segment_2_sequence_and_intermixing": [
        {
            "key": "trial_rows_families",
            "label": "Trial rows/families",
            "description": "Within-trial audio sequence families and task rows.",
        },
        {
            "key": "condition_intermixing",
            "label": "Condition intermixing",
            "description": "Whether systematic manipulations are intermixed with task trials or separated.",
        },
        {
            "key": "blocked_or_random_order",
            "label": "Blocked/random order",
            "description": "Blocked condition structure, random intermixing, and task-critical order constraints.",
        },
        {
            "key": "iti_jitter_policy",
            "label": "ITI/jitter policy",
            "description": "Fixed ITI, jitter values, jitter range, distribution, or hazard-control policy.",
        },
        {
            "key": "response_window",
            "label": "Response window",
            "description": "Allowed response interval, timeout, or scoring window.",
        },
        {
            "key": "task_sequence_rules",
            "label": "Task-critical sequence rules",
            "description": "Special trial scheduling, target/no-target logic, or expectancy controls.",
        },
    ],
    "segment_3_tactile_soa_baseline": [
        {
            "key": "tactile_stimulus",
            "label": "Tactile stimulus",
            "description": "Tactile modality, body site, waveform, duration, frequency, amplitude, and calibration.",
        },
        {
            "key": "soa_table",
            "label": "SOA/distance-at-touch table",
            "description": "SOA values, tactile timing values, or distance-at-tactile values.",
        },
        {
            "key": "baseline_strategy",
            "label": "Baseline strategy",
            "description": "Tactile-only, far/static, fastest-baseline, SOA-matched, direction-coupled, or other baseline type.",
        },
        {
            "key": "baseline_timing",
            "label": "Baseline SOAs/timing",
            "description": "Baseline SOA values, baseline timing relative to omitted sound, or fixed baseline schedule.",
        },
        {
            "key": "catch_trial_type",
            "label": "Catch-trial type",
            "description": "Auditory-only, tactile-only, omitted target, no-go, target-absent, or other catch rule.",
        },
    ],
    "segment_4_counts": [
        {
            "key": "repetitions_per_tactile_soa_condition",
            "label": "Repetitions per tactile SOA/condition",
            "description": "Trial repetitions for each tactile SOA crossed with relevant conditions.",
        },
        {
            "key": "baseline_count",
            "label": "Baseline count",
            "description": "Baseline trial count or percentage.",
        },
        {
            "key": "catch_count",
            "label": "Catch count",
            "description": "Catch/no-go/auditory-only trial count or percentage.",
        },
        {
            "key": "block_count",
            "label": "Block count",
            "description": "Number of blocks, sessions, or phases when task-relevant.",
        },
        {
            "key": "total_trial_count",
            "label": "Total trial count",
            "description": "Total trials per participant, block, condition, or experiment.",
        },
    ],
}

@dataclass(frozen=True)
class AuditPaths:
    repo_root: Path
    coverage_path: Path
    audit_dir: Path
    artifact_dir: Path
    pdf_dir: Path
    supplement_dir: Path
    extracted_dir: Path


def ascii_safe(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "; ".join(ascii_safe(item) for item in value)
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def resolve_paths(
    repo_root: Path,
    coverage_path: Path = COVERAGE_PATH,
    audit_dir: Path = AUDIT_DIR,
    artifact_dir: Path = ARTIFACT_DIR,
) -> AuditPaths:
    repo_root = repo_root.resolve()
    return AuditPaths(
        repo_root=repo_root,
        coverage_path=(repo_root / coverage_path),
        audit_dir=(repo_root / audit_dir),
        artifact_dir=(repo_root / artifact_dir),
        pdf_dir=(repo_root / artifact_dir / "publication_pdfs"),
        supplement_dir=(repo_root / artifact_dir / "supplements"),
        extracted_dir=(repo_root / artifact_dir / "extracted"),
    )


def ensure_directories(paths: AuditPaths) -> None:
    for folder in (
        paths.audit_dir,
        paths.audit_dir / "paper_audits",
        paths.pdf_dir,
        paths.supplement_dir,
        paths.extracted_dir,
    ):
        folder.mkdir(parents=True, exist_ok=True)


def local_java_executable(repo_root: Path) -> Path | None:
    java_root = repo_root / LOCAL_JAVA_ROOT
    if not java_root.exists():
        return None
    candidates = sorted(java_root.rglob("bin/java.exe")) + sorted(java_root.rglob("bin/java"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def ensure_java_on_path(repo_root: Path) -> Path | None:
    existing = shutil.which("java")
    if existing:
        return Path(existing)
    local_java = local_java_executable(repo_root)
    if local_java is None:
        return None
    java_bin = str(local_java.parent)
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if java_bin not in path_parts:
        os.environ["PATH"] = java_bin + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("JAVA_HOME", str(local_java.parent.parent))
    return local_java


def detect_environment(repo_root: Path | None = None) -> dict[str, Any]:
    repo_root = (repo_root or Path(".")).resolve()
    path_java = shutil.which("java")
    local_java = local_java_executable(repo_root)
    java_available = path_java is not None or local_java is not None
    opendataloader_installed = importlib.util.find_spec("opendataloader_pdf") is not None
    pdfplumber_installed = importlib.util.find_spec("pdfplumber") is not None
    pypdf_installed = importlib.util.find_spec("pypdf") is not None
    pdftoppm_available = shutil.which("pdftoppm") is not None
    pdfinfo_available = shutil.which("pdfinfo") is not None
    return {
        "schema": "pps-paper-metadata-environment.v1",
        "parser_version": PARSER_VERSION,
        "checked_on": date.today().isoformat(),
        "java_available": java_available,
        "java_source": "PATH" if path_java else ("local_artifact_jdk" if local_java else ""),
        "opendataloader_pdf_installed": opendataloader_installed,
        "opendataloader_ready": java_available and opendataloader_installed,
        "fallback_extractors": {
            "pdfplumber_installed": pdfplumber_installed,
            "pypdf_installed": pypdf_installed,
            "pdftoppm_available": pdftoppm_available,
            "pdfinfo_available": pdfinfo_available,
        },
        "notes": [
            "OpenDataLoader PDF is the primary extraction route when Java and opendataloader_pdf are available.",
            "Fallback extractor output is written only under ignored artifacts/paper_metadata_audit/extracted.",
            "No executable paths are stored here to avoid local absolute paths in tracked project memory.",
        ],
    }


def is_valid_pdf(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    with path.open("rb") as handle:
        prefix = handle.read(1024)
    return b"%PDF-" in prefix[:128]


def find_pdf(record_id: str, pdf_dir: Path) -> tuple[Path | None, str]:
    candidates = sorted(pdf_dir.glob(f"{record_id}*.pdf"))
    if not candidates:
        return None, "needs_user_download"
    valid = [candidate for candidate in candidates if is_valid_pdf(candidate)]
    if valid:
        return valid[0], "downloaded"
    return candidates[0], "bad_pdf"


def load_acquisition_status(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    payload = load_json(path)
    records = payload.get("records", [])
    return {
        str(record.get("record_id")): record
        for record in records
        if record.get("record_id")
    }


def find_supplements(record_id: str, supplement_dir: Path) -> tuple[list[Path], str]:
    folder = supplement_dir / record_id
    if not folder.exists():
        return [], "not_checked"
    files = sorted(path for path in folder.rglob("*") if path.is_file())
    if files:
        return files, "downloaded"
    return [], "not_checked"


def artifact_rel(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.name


def doi_url(doi: str) -> str:
    return f"https://doi.org/{doi}" if doi else ""


def initial_field_audit(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "value": "",
        "source_file": "",
        "page_or_section": "",
        "evidence_note": "",
    }


def make_field_template(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    status = "not_applicable" if record["coverage_category"] == ADJACENT_CATEGORY else "source_unavailable"
    return {
        segment: {field["key"]: initial_field_audit(status) for field in fields}
        for segment, fields in SEGMENT_FIELDS.items()
    }


def metadata_confidence(
    record: dict[str, Any],
    pdf_status: str,
    extraction_status: str,
) -> tuple[float, str, str]:
    if record["coverage_category"] == ADJACENT_CATEGORY:
        return (
            0.0,
            "not_applicable",
            "Record is adjacent/out of scope for audiotactile PPS Segment 1-4 extraction.",
        )
    if pdf_status == "downloaded" and extraction_status in {"parsed", "parsed_with_warnings"}:
        return (
            0.2,
            "source_acquired_unreviewed",
            "Publication PDF is locally available and parsed, but Segment 1-4 values still require critical manual review.",
        )
    if pdf_status in {"open_access_unavailable", "paywalled"}:
        return (
            0.0,
            "source_unavailable",
            "Automated open-access acquisition did not produce a locally inspectable publication PDF.",
        )
    return (
        0.0,
        "pending_source",
        "Main publication PDF is not yet locally available for Segment 1-4 inspection.",
    )


def make_review_attempts(record: dict[str, Any], pdf_status: str, supplement_status: str) -> list[dict[str, str]]:
    if record["coverage_category"] == ADJACENT_CATEGORY:
        return [
            {
                "attempt": "scope check",
                "status": "complete_from_existing_ledger",
                "note": "Existing literature ledger marks this record adjacent/out of scope for audiotactile PPS metadata extraction.",
            }
        ]
    return [
        {
            "attempt": "main PDF OpenDataLoader extraction",
            "status": "pending" if pdf_status == "needs_user_download" else "available_for_run",
            "note": "Run parser after placing the publication PDF in artifacts/paper_metadata_audit/publication_pdfs.",
        },
        {
            "attempt": "targeted methods/table search",
            "status": "pending_pdf" if pdf_status == "needs_user_download" else "pending_review",
            "note": "Search methods, procedure, apparatus, stimuli, trial design, and tables for Segment 1-4 parameters.",
        },
        {
            "attempt": "supplement search",
            "status": "pending_download_or_check" if supplement_status == "not_checked" else "available_for_review",
            "note": "Check supplementary PDFs, spreadsheets, methods appendices, and task scripts when main-paper fields are absent.",
        },
        {
            "attempt": "fallback extractor/source check",
            "status": "pending_pdf" if pdf_status == "needs_user_download" else "pending_review",
            "note": "Use pdfplumber/pypdf, rendered pages, publisher HTML, or supplement files before marking a field missing.",
        },
    ]


def fallback_extract_pdf(pdf_path: Path, output_dir: Path) -> tuple[str, list[str]]:
    warnings: list[str] = []
    text = ""
    if importlib.util.find_spec("pdfplumber") is not None:
        try:
            import pdfplumber  # type: ignore

            chunks: list[str] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for index, page in enumerate(pdf.pages, start=1):
                    page_text = page.extract_text() or ""
                    chunks.append(f"\n\n[page {index}]\n{page_text}")
            text = "".join(chunks)
        except Exception as exc:  # pragma: no cover - exercised only with real PDFs
            warnings.append(f"pdfplumber failed: {exc}")
    if not text and importlib.util.find_spec("pypdf") is not None:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(pdf_path))
            chunks = [
                f"\n\n[page {index}]\n{page.extract_text() or ''}"
                for index, page in enumerate(reader.pages, start=1)
            ]
            text = "".join(chunks)
        except Exception as exc:  # pragma: no cover - exercised only with real PDFs
            warnings.append(f"pypdf failed: {exc}")
    if not text:
        raise RuntimeError("; ".join(warnings) or "No fallback PDF extractor available")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{pdf_path.stem}.fallback.txt"
    out_path.write_text(text, encoding="utf-8", errors="replace")
    return out_path.name, warnings


def run_opendataloader(pdf_paths: list[Path], output_dir: Path, repo_root: Path) -> tuple[bool, str]:
    if not pdf_paths:
        return True, "no PDFs to parse"
    java_path = ensure_java_on_path(repo_root)
    if not (java_path and importlib.util.find_spec("opendataloader_pdf")):
        return False, "Java and/or opendataloader_pdf unavailable"
    try:
        import opendataloader_pdf  # type: ignore

        output_dir.mkdir(parents=True, exist_ok=True)
        opendataloader_pdf.convert(
            input_path=[str(path) for path in pdf_paths],
            output_dir=str(output_dir),
            format="markdown,json",
        )
    except Exception as exc:  # pragma: no cover - exercised only when dependency is installed
        return False, f"OpenDataLoader failed: {exc}"
    return True, "OpenDataLoader conversion completed"


def extract_downloaded_pdfs(records: list[dict[str, Any]], paths: AuditPaths) -> dict[str, dict[str, Any]]:
    downloaded = []
    pdf_by_record: dict[str, Path] = {}
    for record in records:
        if record["coverage_category"] == ADJACENT_CATEGORY:
            continue
        pdf_path, pdf_status = find_pdf(record["record_id"], paths.pdf_dir)
        if pdf_path is not None and pdf_status == "downloaded":
            downloaded.append(pdf_path)
            pdf_by_record[record["record_id"]] = pdf_path

    extraction_log: dict[str, dict[str, Any]] = {}
    success, message = run_opendataloader(downloaded, paths.extracted_dir / "opendataloader", paths.repo_root)
    for record_id, pdf_path in pdf_by_record.items():
        extraction_log[record_id] = {
            "primary_extractor": "opendataloader_pdf",
            "primary_success": success,
            "primary_message": message,
            "fallback_output": "",
            "warnings": [],
            "status": "parsed" if success else "parsed_with_warnings",
        }
        if not success:
            try:
                fallback_output, warnings = fallback_extract_pdf(
                    pdf_path,
                    paths.extracted_dir / "fallback" / record_id,
                )
                extraction_log[record_id].update(
                    {
                        "fallback_output": fallback_output,
                        "warnings": warnings,
                        "status": "parsed_with_warnings",
                    }
                )
            except Exception as exc:  # pragma: no cover - exercised only with bad local PDFs
                extraction_log[record_id].update(
                    {
                        "warnings": [str(exc)],
                        "status": "failed",
                    }
                )
    return extraction_log


def build_records(
    literature_records: list[dict[str, Any]],
    paths: AuditPaths,
    extraction_log: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    audit_records: list[dict[str, Any]] = []
    missing_requests: list[dict[str, Any]] = []
    acquisition_by_record = load_acquisition_status(paths.repo_root / ACQUISITION_STATUS_PATH)
    for record in literature_records:
        record_id = record["record_id"]
        is_adjacent = record["coverage_category"] == ADJACENT_CATEGORY
        acquisition_status = acquisition_by_record.get(record_id, {})
        pdf_path, pdf_status = (None, "not_applicable") if is_adjacent else find_pdf(record_id, paths.pdf_dir)
        if not is_adjacent and pdf_path is None:
            acquired_status = acquisition_status.get("pdf_status")
            if acquired_status in PDF_STATUSES and acquired_status != "downloaded":
                pdf_status = acquired_status
        supplement_files, supplement_status = (
            ([], "not_applicable") if is_adjacent else find_supplements(record_id, paths.supplement_dir)
        )
        if is_adjacent:
            extraction_status = "parsed_with_warnings"
        elif pdf_status == "bad_pdf":
            extraction_status = "failed"
        elif pdf_status != "downloaded":
            extraction_status = "pending_pdf"
        else:
            extraction_status = extraction_log.get(record_id, {}).get("status", "parsed_with_warnings")
        confidence_score, confidence_label, confidence_basis = metadata_confidence(
            record,
            pdf_status,
            extraction_status,
        )

        audit_record = {
            "schema": "pps-paper-metadata-audit-record.v1",
            "record_id": record_id,
            "citation_short": ascii_safe(record["citation_short"]),
            "doi": record.get("doi", ""),
            "doi_url": doi_url(record.get("doi", "")),
            "coverage_category": record["coverage_category"],
            "audiotactile_task_family": ascii_safe(record.get("audiotactile_task_family", "")),
            "source_basis": record.get("source_basis", []),
            "current_template_ids": record.get("current_template_ids", []),
            "pdf_status": pdf_status,
            "pdf_file": artifact_rel(pdf_path, paths.repo_root) if pdf_path else "",
            "pdf_acquisition_attempt_count": acquisition_status.get("attempt_count", 0),
            "pdf_acquisition_last_status": acquisition_status.get("last_status", ""),
            "supplement_status": supplement_status,
            "supplement_files": [artifact_rel(path, paths.repo_root) for path in supplement_files],
            "extraction_status": extraction_status,
            "metadata_confidence_score": confidence_score,
            "metadata_confidence_label": confidence_label,
            "metadata_confidence_basis": confidence_basis,
            "extraction_outputs": {
                "primary": "artifacts/paper_metadata_audit/extracted/opendataloader/",
                "fallback": f"artifacts/paper_metadata_audit/extracted/fallback/{record_id}/",
            },
            "known_missing_or_unresolved_from_prior_ledger": [
                ascii_safe(item) for item in record.get("missing_publication_parameters", [])
            ],
            "blocking_constraint_ids_from_prior_ledger": record.get("blocking_constraint_ids", []),
            "segment_field_audit": make_field_template(record),
            "review_attempts": make_review_attempts(record, pdf_status, supplement_status),
        }
        audit_records.append(audit_record)

        if not is_adjacent and pdf_status in {"needs_user_download", "bad_pdf", "open_access_unavailable", "paywalled"}:
            missing_requests.append(
                {
                    "record_id": record_id,
                    "citation_short": ascii_safe(record["citation_short"]),
                    "doi": record.get("doi", ""),
                    "doi_url": doi_url(record.get("doi", "")),
                    "requested_item": "publication_pdf",
                    "current_status": pdf_status,
                    "target_location": f"artifacts/paper_metadata_audit/publication_pdfs/{record_id}.pdf",
                    "note": "Download the main publication PDF here for exact Segment 1-4 inspection.",
                }
            )
        if not is_adjacent and supplement_status == "not_checked":
            missing_requests.append(
                {
                    "record_id": record_id,
                    "citation_short": ascii_safe(record["citation_short"]),
                    "doi": record.get("doi", ""),
                    "doi_url": doi_url(record.get("doi", "")),
                    "requested_item": "supplement_or_methods_files",
                    "current_status": supplement_status,
                    "target_location": f"artifacts/paper_metadata_audit/supplements/{record_id}/",
                    "note": "Check publisher/PMC/OSF/project pages for supplementary PDFs, tables, scripts, or appendices.",
                }
            )
    return audit_records, missing_requests


def summary_from_records(audit_records: list[dict[str, Any]], missing_requests: list[dict[str, Any]]) -> dict[str, Any]:
    def count_by(key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for record in audit_records:
            counts[record[key]] = counts.get(record[key], 0) + 1
        return dict(sorted(counts.items()))

    return {
        "schema": "pps-paper-metadata-audit-summary.v1",
        "generated_on": date.today().isoformat(),
        "parser_version": PARSER_VERSION,
        "record_count": len(audit_records),
        "pdf_status_counts": count_by("pdf_status"),
        "supplement_status_counts": count_by("supplement_status"),
        "extraction_status_counts": count_by("extraction_status"),
        "metadata_confidence_label_counts": count_by("metadata_confidence_label"),
        "missing_download_request_count": len(missing_requests),
        "tracked_pdf_folder": "artifacts/paper_metadata_audit/publication_pdfs/",
        "tracked_supplement_folder": "artifacts/paper_metadata_audit/supplements/",
        "tracked_extraction_folder": "artifacts/paper_metadata_audit/extracted/",
        "copyright_boundary": "PDFs, supplements, extracted text, and long quoted passages stay in ignored artifacts; tracked files store only metadata, statuses, and short evidence pointers.",
    }


def schema_payload() -> dict[str, Any]:
    return {
        "schema": "pps-paper-metadata-extraction-schema.v1",
        "parser_version": PARSER_VERSION,
        "pdf_statuses": list(PDF_STATUSES),
        "supplement_statuses": list(SUPPLEMENT_STATUSES),
        "extraction_statuses": list(EXTRACTION_STATUSES),
        "field_statuses": list(FIELD_STATUSES),
        "confidence_labels": list(CONFIDENCE_LABELS),
        "segment_fields": SEGMENT_FIELDS,
        "review_rule": {
            "missing_value_rule": "Only mark not_reported_after_review after main PDF extraction, targeted methods/table search, supplement search, and fallback extractor/source check have all been attempted.",
            "copyright_boundary": "Do not commit PDFs, supplements, extracted full text, screenshots of pages, or long verbatim passages.",
        },
        "local_artifact_conventions": {
            "main_pdf_filename": "artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf",
            "supplement_folder": "artifacts/paper_metadata_audit/supplements/<record_id>/",
            "extracted_output_folder": "artifacts/paper_metadata_audit/extracted/",
        },
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ascii_safe(row.get(key, "")) for key in fieldnames})


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")


def readme_text(summary: dict[str, Any], environment: dict[str, Any]) -> str:
    return f"""# Audiotactile Paper Metadata Audit

This folder is dedicated to metadata extraction from published audio-tactile PPS papers. It is intentionally independent from GUI/profile recreation: the goal is to inspect papers and supplements and record whether Segment 1-4 metadata can be extracted.

## Local Artifact Folders

- `artifacts/paper_metadata_audit/publication_pdfs/`: place publication PDFs here as `<record_id>.pdf`.
- `artifacts/paper_metadata_audit/supplements/<record_id>/`: place supplementary PDFs, DOCX, XLSX, ODS, ZIPs, scripts, or appendices here.
- `artifacts/paper_metadata_audit/extracted/`: parser output from OpenDataLoader PDF and fallback extractors.

The `artifacts/` tree is ignored by Git. Do not commit PDFs, supplements, extracted full text, page images, or long copied passages.

## Current Inventory

- Literature records: {summary["record_count"]}
- PDF status counts: `{json.dumps(summary["pdf_status_counts"], sort_keys=True)}`
- Supplement status counts: `{json.dumps(summary["supplement_status_counts"], sort_keys=True)}`
- Extraction status counts: `{json.dumps(summary["extraction_status_counts"], sort_keys=True)}`
- Metadata confidence counts: `{json.dumps(summary["metadata_confidence_label_counts"], sort_keys=True)}`
- Missing download/check requests: {summary["missing_download_request_count"]}

## Environment Readiness

- Java available: `{environment["java_available"]}`
- `opendataloader_pdf` installed: `{environment["opendataloader_pdf_installed"]}`
- OpenDataLoader ready: `{environment["opendataloader_ready"]}`
- Fallback extractors: `{json.dumps(environment["fallback_extractors"], sort_keys=True)}`

## How To Use

1. Download each available publication PDF into `artifacts/paper_metadata_audit/publication_pdfs/<record_id>.pdf`.
2. Download supplements into `artifacts/paper_metadata_audit/supplements/<record_id>/`.
3. Run `python -m tools.paper_metadata_parser --refresh` from the repo root.
4. Review `running_checklist.csv`, `missing_pdf_request_list.csv`, and `paper_audits/<record_id>.md`.
5. Fill `metadata_audit.jsonl` or the per-paper summaries with extracted Segment 1-4 values using short evidence pointers only.

Before marking any value `not_reported_after_review`, inspect the main PDF, methods/tables, supplements, and at least one fallback/source route.
"""


def checklist_text() -> str:
    lines = [
        "# Segment 1-4 Metadata Checklist",
        "",
        "Use this checklist for every in-scope publication. Each field must carry one of the schema statuses and a short source pointer when a value is present.",
        "",
    ]
    for segment, fields in SEGMENT_FIELDS.items():
        title = segment.replace("_", " ").title()
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| Field | What to extract |")
        lines.append("|---|---|")
        for field in fields:
            lines.append(f"| `{field['key']}` | {field['description']} |")
        lines.append("")
    lines.extend(
        [
            "## Missing-Value Rule",
            "",
            "A field can be marked `not_reported_after_review` only after all of these attempts are logged:",
            "",
            "1. Main publication PDF extraction with OpenDataLoader PDF.",
            "2. Targeted review of methods, apparatus, procedure, trial-design tables, and figures.",
            "3. Supplement search, including PDFs, spreadsheets, appendices, scripts, and project pages.",
            "4. Fallback extraction or source check using pdfplumber/pypdf, publisher HTML, rendered pages, or a second source route.",
            "",
            "Keep tracked evidence short. Store raw PDF/text artifacts only under ignored `artifacts/paper_metadata_audit/`.",
            "",
        ]
    )
    return "\n".join(lines)


def paper_audit_text(record: dict[str, Any]) -> str:
    lines = [
        f"# {ascii_safe(record['citation_short'])}",
        "",
        f"- Record ID: `{record['record_id']}`",
        f"- DOI: `{record['doi'] or 'not recorded'}`",
        f"- DOI URL: {record['doi_url'] or 'not recorded'}",
        f"- Coverage category: `{record['coverage_category']}`",
        f"- Task family: {ascii_safe(record['audiotactile_task_family'])}",
        f"- PDF status: `{record['pdf_status']}`",
        f"- Supplement status: `{record['supplement_status']}`",
        f"- Extraction status: `{record['extraction_status']}`",
        f"- Metadata confidence: `{record['metadata_confidence_score']}` (`{record['metadata_confidence_label']}`)",
        f"- Confidence basis: {ascii_safe(record['metadata_confidence_basis'])}",
        "",
        "## Known Prior Gaps",
        "",
    ]
    gaps = record["known_missing_or_unresolved_from_prior_ledger"]
    if gaps:
        lines.extend(f"- {ascii_safe(gap)}" for gap in gaps)
    else:
        lines.append("- None recorded in the prior coverage ledger.")
    lines.extend(["", "## Review Attempts", ""])
    for attempt in record["review_attempts"]:
        lines.append(f"- `{attempt['attempt']}`: `{attempt['status']}` - {ascii_safe(attempt['note'])}")
    lines.extend(["", "## Segment Field Status", ""])
    lines.append("| Segment | Field | Status | Value | Source pointer |")
    lines.append("|---|---|---|---|---|")
    for segment, fields in record["segment_field_audit"].items():
        for field_key, field in fields.items():
            source = field.get("source_file") or field.get("page_or_section") or ""
            lines.append(
                f"| `{segment}` | `{field_key}` | `{field['status']}` | {ascii_safe(field.get('value', ''))} | {ascii_safe(source)} |"
            )
    lines.append("")
    lines.append("Do not paste long source text here; use short page/section pointers and concise paraphrases.")
    lines.append("")
    return "\n".join(lines)


def write_audit_files(
    audit_records: list[dict[str, Any]],
    missing_requests: list[dict[str, Any]],
    summary: dict[str, Any],
    environment: dict[str, Any],
    paths: AuditPaths,
) -> None:
    write_json(paths.audit_dir / "extraction_schema.json", schema_payload())
    write_json(paths.audit_dir / "environment_readiness.json", environment)
    write_json(paths.audit_dir / "audit_summary.json", summary)
    (paths.audit_dir / "README.md").write_text(readme_text(summary, environment), encoding="utf-8")
    (paths.audit_dir / "parameter_checklist.md").write_text(checklist_text(), encoding="utf-8")
    write_jsonl(paths.audit_dir / "metadata_audit.jsonl", audit_records)

    checklist_rows = [
        {
            "record_id": record["record_id"],
            "citation_short": record["citation_short"],
            "doi": record["doi"],
            "coverage_category": record["coverage_category"],
            "pdf_status": record["pdf_status"],
            "supplement_status": record["supplement_status"],
            "extraction_status": record["extraction_status"],
            "pdf_file": record["pdf_file"],
            "supplement_file_count": len(record["supplement_files"]),
            "known_prior_gap_count": len(record["known_missing_or_unresolved_from_prior_ledger"]),
            "metadata_confidence_score": record["metadata_confidence_score"],
            "metadata_confidence_label": record["metadata_confidence_label"],
        }
        for record in audit_records
    ]
    write_csv(
        paths.audit_dir / "running_checklist.csv",
        checklist_rows,
        [
            "record_id",
            "citation_short",
            "doi",
            "coverage_category",
            "pdf_status",
            "supplement_status",
            "extraction_status",
            "pdf_file",
            "supplement_file_count",
            "known_prior_gap_count",
            "metadata_confidence_score",
            "metadata_confidence_label",
        ],
    )
    write_csv(
        paths.audit_dir / "missing_pdf_request_list.csv",
        missing_requests,
        [
            "record_id",
            "citation_short",
            "doi",
            "doi_url",
            "requested_item",
            "current_status",
            "target_location",
            "note",
        ],
    )
    paper_dir = paths.audit_dir / "paper_audits"
    for old_file in paper_dir.glob("*.md"):
        old_file.unlink()
    for record in audit_records:
        (paper_dir / f"{record['record_id']}.md").write_text(
            paper_audit_text(record),
            encoding="utf-8",
        )


def run_audit(
    repo_root: Path | str = Path("."),
    *,
    coverage_path: Path = COVERAGE_PATH,
    audit_dir: Path = AUDIT_DIR,
    artifact_dir: Path = ARTIFACT_DIR,
    parse_downloaded: bool = True,
) -> dict[str, Any]:
    paths = resolve_paths(Path(repo_root), coverage_path, audit_dir, artifact_dir)
    ensure_directories(paths)
    coverage = load_json(paths.coverage_path)
    records = list(coverage["literature_records"])
    environment = detect_environment(paths.repo_root)
    extraction_log = extract_downloaded_pdfs(records, paths) if parse_downloaded else {}
    audit_records, missing_requests = build_records(records, paths, extraction_log)
    summary = summary_from_records(audit_records, missing_requests)
    write_audit_files(audit_records, missing_requests, summary, environment, paths)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inventory and scaffold paper metadata extraction for audio-tactile PPS publications."
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="Repository root.")
    parser.add_argument("--coverage-path", type=Path, default=COVERAGE_PATH, help="Literature coverage JSON path.")
    parser.add_argument("--audit-dir", type=Path, default=AUDIT_DIR, help="Tracked audit output folder.")
    parser.add_argument("--artifact-dir", type=Path, default=ARTIFACT_DIR, help="Ignored local artifact folder.")
    parser.add_argument(
        "--no-parse-downloaded",
        action="store_true",
        help="Only inventory PDFs/supplements; do not extract downloaded PDFs.",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refresh audit files. Kept explicit for readable command history.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    summary = run_audit(
        args.repo_root,
        coverage_path=args.coverage_path,
        audit_dir=args.audit_dir,
        artifact_dir=args.artifact_dir,
        parse_downloaded=not args.no_parse_downloaded,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    return 0
