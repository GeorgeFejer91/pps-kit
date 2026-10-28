"""Join the frozen archive to every shipped preset and full browser plan.

This development-only inventory does not render or execute trials. Its assertions
protect the input population and complete row contracts for the native audit.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
RESOURCES = "packages/pps-resources"
PROJECTION = "apps/designer/frontend/publication_study_reviews.v1.json"
ROW_CONTRACT_SOURCE = "packages/pps-runtime/src/peripersonal_space_toolkit/dashboard_app.py"
PUBLIC_PARAMETER_STATUSES = {"reported_complete", "derived_complete", "partial", "conflicting_evidence",
                             "approximation_required", "explicitly_absent", "not_applicable", "not_reported",
                             "source_unavailable", "not_assessed"}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_by(items: list[dict], key: str) -> dict:
    result = {item[key]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate {key}")
    return result


def saved_metadata_findings(capture: dict, allowed_fields: set[str]) -> list[dict]:
    """Compare declared row metadata without inventing missing source values."""
    strips = unique_by(capture["design"]["protocol"].get("trial_strips", []), "label")
    findings = Counter()
    for block in capture["block_csv_preview"].get("blocks", []):
        for row in block["preview_rows"]:
            metadata = strips[row["row_label"]].get("metadata", {})
            expected = {key: value for key, value in metadata.items()
                        if key in allowed_fields and value not in (None, "")}
            if row["family"] == "catch":
                # Existing dashboard family policy overrides target response metadata.
                if "expected_response" in expected:
                    expected["expected_response"] = "withhold"
                if "target_role" in expected:
                    expected["target_role"] = "catch_no_target"
            for key, value in expected.items():
                if row.get(key) != value:
                    findings[(row["row_label"], row["family"], key)] += 1
    return [{"row_label": label, "family": family, "field": field, "affected_rows": count}
            for (label, family, field), count in sorted(findings.items())]


def saved_block_label_findings(capture: dict) -> list[dict]:
    """Record label loss without inferring condition membership or multiplicity."""
    specs = capture["design"]["protocol"].get("block_specs", [])
    findings = []
    for index, block in enumerate(capture["block_csv_preview"].get("blocks", [])):
        declared = specs[index].get("label") if index < len(specs) else None
        captured = block.get("block_label")
        if not declared or declared == captured:
            continue
        def block_number(label):
            match = re.fullmatch(r"Block\s+(\d+)", label or "", flags=re.IGNORECASE)
            return int(match[1]) if match else None
        number = block_number(declared)
        formatting_only = number is not None and number == block_number(captured)
        findings.append({"block_index": block["block_index"], "declared_label": declared,
                         "captured_label": captured, "affected_rows": block["trial_count"],
                         "classification": "number_format_only" if formatting_only else "descriptive_label_replaced"})
    return findings


def source_duration_checks(root: Path, capture: dict) -> list[dict]:
    """Inspect actual shipped WAV headers, including native IEEE-float assets."""
    import soundfile
    checks = []
    for collection, path_key in (("noises", "prebaked_path"), ("custom_looming_files", "path")):
        for source in capture["design"].get(collection, []):
            reference = source.get(path_key)
            if not reference:
                continue
            info = soundfile.info(root / RESOURCES / reference)
            captured = source.get("duration_s")
            matches = isinstance(captured, (int, float)) and not isinstance(captured, bool) \
                and math.isfinite(captured) and abs(captured - info.duration) <= 1 / info.samplerate
            checks.append({"collection": collection, "label": source["label"], "path": reference,
                           "frames": info.frames, "sample_rate_hz": info.samplerate,
                           "actual_duration_s": info.duration, "captured_duration_s": captured,
                           "status": "match" if matches else "mismatch"})
    return checks


def checked_plan(template_id: str, eligible: bool, capture: dict) -> dict:
    """Never accept a same-sized partial/repeated pool as a complete block plan."""
    if capture["design"]["study_profile_id"] != template_id:
        raise ValueError(f"Wrong captured template: {template_id}")
    blocks = capture["block_csv_preview"].get("blocks", [])
    pool = capture["trial_pool_bake"].get("preview_rows", [])
    rows = [row for block in blocks for row in block["preview_rows"]]
    if not eligible:
        if rows or capture["custom_workflow"]["ready_to_prepare"]:
            raise ValueError(f"Blocked preset exposes a runnable plan: {template_id}")
        return {"status": "blocked_as_shipped", "source_trial_count": 0, "source_blocks": [],
                "native_preparation": "not_assessed", "native_execution": "not_assessed",
                "usable_runner_file_verified": False}
    if not rows or len(pool) != capture["trial_pool_bake"]["total_count"]:
        raise ValueError(f"Missing or truncated pool: {template_id}")
    pool_ids = [row["trial_pool_index"] for row in pool]
    if len(set(pool_ids)) != len(pool_ids) or Counter(pool_ids) != Counter(row["trial_pool_index"] for row in rows):
        raise ValueError(f"Blocks do not preserve every pool row once: {template_id}")
    pool_by_id = unique_by(pool, "trial_pool_index")
    fields = ("family", "soa_ms", "sequence_variant_key", "baseline_mode", "duration_ms",
              "tactile_onset_s", "looming_segment_onset_s", "source_file_name", "repetition_index")
    for block in blocks:
        if len(block["preview_rows"]) != block["trial_count"]:
            raise ValueError(f"Truncated block: {template_id}")
        for index, row in enumerate(block["preview_rows"], 1):
            if row["block_trial_index"] != index or row["block_index"] != block["block_index"]:
                raise ValueError(f"Changed block order/index: {template_id}")
            if any(row.get(key) != pool_by_id[row["trial_pool_index"]].get(key) for key in fields):
                raise ValueError(f"Changed pool timing/family/condition: {template_id}")
    setup = capture["design"].get("study_profile_reference_parameters", {}).get("dashboard_run_setup", {})
    return {
        "status": "complete_plan_captured",
        "source_trial_count": len(rows),
        "family_counts": dict(sorted(Counter(row["family"] for row in rows).items())),
        "source_blocks": [{"index": b["block_index"], "label": b["block_label"], "rows": b["trial_count"]} for b in blocks],
        "saved_experiment_structure": setup.get("experiment_structure", capture["run_sequence_setup"].get("experiment_structure")),
        "saved_participant_order_count": capture["design"]["protocol"].get("participants"),
        "enabled_instruction_slots": [slot["slot"] for slot in setup.get("instruction_profile", {}).get("slots", []) if slot.get("enabled")],
        "native_preparation": "not_assessed",
        "native_execution": "not_assessed",
        "usable_runner_file_verified": False,
    }


def build_report(root: Path, captures: Path) -> dict:
    projection = read_json(root / PROJECTION)
    status = read_json(root / RESOURCES / "assets/preloads/profile_recreation_status.json")
    templates = {path.stem: path for path in (root / RESOURCES / "study_templates").glob("*.json")}
    profiles = unique_by(status["profiles"], "template_id")
    receipt = read_json(captures / "capture-report.json")
    contract_source = root / ROW_CONTRACT_SOURCE
    syntax = ast.parse(contract_source.read_text(encoding="utf-8"))
    allowed_fields = set(next(ast.literal_eval(node.value) for node in syntax.body
                             if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "ROW_CONTRACT_FIELDS" for target in node.targets)))
    cases = unique_by(receipt["cases"], "template_id")
    if templates.keys() != profiles.keys() or templates.keys() != cases.keys():
        raise ValueError("Template/status/capture population mismatch")
    for path, expected in receipt["input_hashes"].items():
        if sha256(root / path) != expected:
            raise ValueError(f"Stale captured input: {path}")
    studies = unique_by(projection["studies"], "studyRowId")
    publications = unique_by(projection["publications"], "networkNodeId")
    for row in [*studies.values(), *publications.values()]:
        if set(row["templateIds"]) - templates.keys():
            raise ValueError("Archive references an unknown preset")
    presets = []
    for template_id, path in sorted(templates.items()):
        profile, case = profiles[template_id], cases[template_id]
        if sha256(path) != case["template_sha256"]:
            raise ValueError(f"Stale captured template: {template_id}")
        if case["status"] == "failed" or case["page_errors"]:
            raise ValueError(f"Browser capture failed: {template_id}")
        capture_path = captures / case["capture_file"]
        if sha256(capture_path) != case["capture_sha256"]:
            raise ValueError(f"Changed capture: {template_id}")
        capture = read_json(capture_path)
        eligible = profile["runner_readiness"] == "ready" and profile["profile_checks_passed"] is True
        plan = checked_plan(template_id, eligible, capture)
        plan["saved_metadata_findings"] = saved_metadata_findings(capture, allowed_fields)
        plan["saved_block_label_findings"] = saved_block_label_findings(capture)
        plan["source_duration_checks"] = source_duration_checks(root, capture)
        presets.append({
            "template_id": template_id, "template_sha256": case["template_sha256"],
            "capture_sha256": case["capture_sha256"], "publication_status": profile["publication_status"],
            "configuration_eligible": eligible,
            "missing_inputs": profile.get("missing_publication_parameters", []),
            "unsupported_structures": profile.get("unsupported_toolkit_structures", []),
            "study_row_ids": sorted(k for k, row in studies.items() if template_id in row["templateIds"]),
            "reviewed_schedule_contracts": [
                {"study_row_id": key, "key": contract["key"], "status": contract["status"],
                 "value": contract["value"], "source_url": contract["evidenceSourceUrl"],
                 "page_or_section": contract["pageOrSection"]}
                for key, row in sorted(studies.items()) if template_id in row["templateIds"]
                for contract in row["contracts"]
                if contract["key"] in {"repetition_allocation", "block_order_contract"}
            ],
            "published_protocol_equivalence": "not_established_by_software_audit",
            "plan": plan,
        })
    archive_rows = [{"study_row_id": key, "publication_id": row["networkNodeId"],
                     "experiment_label": row["experimentLabel"], "template_ids": row["templateIds"],
                     "parameter_status_counts": row["parameterStatusCounts"],
                     "preset_availability": "linked" if row["templateIds"] else "no_bundled_preset",
                     "all_contracts_not_applicable": row["parameterStatusCounts"].get("not_applicable") == 11,
                     "native_qualification": row["nativeQualification"]} for key, row in sorted(studies.items())]
    return {
        "schema": "pps-preset-population-audit.v1", "captured_at": receipt["captured_at"],
        "evidence_scope": "Complete shipped configuration inventory and browser plans. Native preparation/execution and published-method equivalence are separate gates.",
        "input_hashes": {**receipt["input_hashes"], PROJECTION: sha256(root / PROJECTION),
                         ROW_CONTRACT_SOURCE: sha256(contract_source)},
        "counts": {"publications": len(publications), "study_context_rows": len(studies),
                   "publications_with_presets": sum(bool(row["templateIds"]) for row in publications.values()),
                   "study_rows_with_presets": sum(bool(row["templateIds"]) for row in studies.values()),
                   "presets": len(presets), "configuration_eligible": sum(x["configuration_eligible"] for x in presets),
                   "blocked_as_shipped": sum(not x["configuration_eligible"] for x in presets),
                   "published_presets_without_study_assignment": sum(x["publication_status"] == "published" and not x["study_row_ids"] for x in presets),
                   "presets_with_saved_metadata_loss": sum(bool(x["plan"]["saved_metadata_findings"]) for x in presets),
                   "presets_with_descriptive_block_labels_replaced": sum(any(f["classification"] == "descriptive_label_replaced" for f in x["plan"]["saved_block_label_findings"]) for x in presets),
                   "descriptive_block_labels_replaced": sum(f["classification"] == "descriptive_label_replaced" for x in presets for f in x["plan"]["saved_block_label_findings"]),
                   "source_duration_checks": sum(len(x["plan"]["source_duration_checks"]) for x in presets),
                   "source_duration_mismatches": sum(c["status"] != "match" for x in presets for c in x["plan"]["source_duration_checks"]),
                   "native_preparation_verified": 0, "native_execution_verified": 0},
        "presets": presets, "archive_rows": archive_rows,
    }


def markdown(report: dict) -> str:
    counts = report["counts"]
    lines = ["# Shipped preset population audit", "", report["evidence_scope"], "",
             f"{counts['publications']} publications / {counts['study_context_rows']} study-context rows; "
             f"{counts['presets']} presets, {counts['configuration_eligible']} configuration-eligible, "
             f"{counts['blocked_as_shipped']} gated. {counts['study_rows_with_presets']} study rows link to presets. "
             "An archive entry without a bundled preset is not an executable experiment or an audit failure.", "",
             "| Preset | Shipped plan | Source rows / blocks | Parts policy | Native files / execution |", "|---|---|---:|---|---|"]
    for item in report["presets"]:
        plan = item["plan"]
        lines.append(f"| {item['template_id']} | {plan['status']} | {plan['source_trial_count']} / {len(plan['source_blocks'])} | {plan.get('saved_experiment_structure', 'gated')} | Not assessed / not assessed |")
    lines += ["", "## Saved plan contract observations", "",
              f"{counts['source_duration_checks']} actual stimulus WAV headers checked; {counts['source_duration_mismatches']} captured-duration mismatches. "
              f"{counts['presets_with_saved_metadata_loss']} presets lose declared allowlisted strip metadata. "
              f"{counts['descriptive_block_labels_replaced']} descriptive block labels are replaced across {counts['presets_with_descriptive_block_labels_replaced']} presets. "
              "These are separate observations; preserving counts does not establish condition allocation or published-method equivalence.", ""]
    for item in report["presets"]:
        labels = [f for f in item["plan"]["saved_block_label_findings"] if f["classification"] == "descriptive_label_replaced"]
        if labels:
            lines.append(f"- **{item['template_id']}**: " + "; ".join(f"{f['declared_label']} → {f['captured_label']}" for f in labels))
    lines += ["", "## Explicit missing inputs", "", "These are retained as-shipped gates. No source or apparatus values were supplied by the audit.", ""]
    for item in report["presets"]:
        if not item["configuration_eligible"]:
            lines.append(f"- **{item['template_id']}**: " + "; ".join(x["reason"] for x in item["missing_inputs"]))
    return "\n".join(lines) + "\n"


def public_token(value, pattern: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError("Invalid public identity or attribution")
    return value


def public_count(value) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid evidence count")
    return value


def build_public_report(root: Path, captures: Path, native_report: Path, candidate_manifest: Path,
                        source_commit: str, ci_run_url: str) -> dict:
    """Allowlisted projection of a terminal full run, never a second verdict ledger.

    The caller attributes the run to the exact candidate revision and CI URL;
    this offline projection does not query GitHub or qualify installed execution.
    Raw paths, participant data, receipt bodies and prose errors are never copied.
    """
    source_commit = public_token(source_commit, r"[a-f0-9]{40}")
    ci_run_url = public_token(ci_run_url, r"https://github\.com/GeorgeFejer91/pps-kit/actions/runs/[1-9][0-9]*(?:/attempts/[1-9][0-9]*)?")
    candidate = read_json(candidate_manifest)
    if candidate.get("schema") != "pps-native-windows-candidate.v1" or candidate.get("source_commit") != source_commit:
        raise ValueError("Candidate source attribution mismatch")
    captured = read_json(captures / "capture-report.json")
    if captured.get("schema") != "pps-preset-plan-capture.v1" or not captured["cases"]:
        raise ValueError("A complete preset inventory cannot be empty")
    for case in captured["cases"]:
        identity = public_token(case["template_id"], r"[a-z][a-z0-9_]*")
        if case["capture_file"] != identity + ".json":
            raise ValueError("Capture must be an identity-local file")
    for path, digest in captured["input_hashes"].items():
        if not path.startswith(("apps/", "packages/")) or "\\" in path or ":" in path or any(p in {"", ".", ".."} for p in path.split("/")):
            raise ValueError("Capture input must be a repository-relative product file")
        public_token(digest, r"[a-f0-9]{64}")
    population = build_report(root, captures)  # Existing full-plan and freshness owner.
    native = read_json(native_report)
    if (native.get("schema") != "pps-native-preset-pipeline-audit.v1"
            or native.get("all_capture_cases_selected") is not True
            or native.get("capture_report_sha256") != sha256(captures / "capture-report.json")
            or native.get("physical_timing_qualified") is not False
            or native.get("replication_qualified") is not False):
        raise ValueError("Native report is not bound to the complete software-only capture")
    native_cases = unique_by(native["cases"], "template_id")
    capture_cases = unique_by(captured["cases"], "template_id")
    if native_cases.keys() != capture_cases.keys():
        raise ValueError("Native/capture population mismatch")
    # Reuse the native driver's exact part/hash/response completeness check.
    spec = importlib.util.spec_from_file_location("preset_native_validator", Path(__file__).with_name("run_native_preset_pipeline.py"))
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    profiles = unique_by(read_json(root / RESOURCES / "assets/preloads/profile_recreation_status.json")["profiles"], "template_id")
    projection = read_json(root / PROJECTION)
    publications = unique_by(projection["publications"], "networkNodeId")
    doi_pattern = r"doi:10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]+"
    rows = []
    for preset in population["presets"]:
        identity = preset["template_id"]
        case, capture_case, profile = native_cases[identity], capture_cases[identity], profiles[identity]
        for key in ("template_sha256", "capture_sha256"):
            public_token(case[key], r"[a-f0-9]{64}")
            if case[key] != preset[key]:
                raise ValueError("Native template/capture hash mismatch")
        if capture_case["configuration_eligible"] is not preset["configuration_eligible"]:
            raise ValueError("Configuration eligibility mismatch")
        status = case.get("status")
        if status not in {"software_pipeline_passed", "blocked", "failed"}:
            raise ValueError("Public export requires a terminal full run, not preflight or preparation only")
        if case.get("capture_input_hashes", captured["input_hashes"]) != captured["input_hashes"]:
            raise ValueError("Native capture input hashes changed")
        if status != "failed" and (case.get("source_trial_count") != preset["plan"]["source_trial_count"]
                or case.get("source_block_rows") != preset["plan"]["source_blocks"]
                or case.get("capture_input_hashes") != captured["input_hashes"]):
            raise ValueError("Native full source counts or input identities changed")
        guard = "native_complete_block_plan_required"
        if status == "blocked" and (preset["configuration_eligible"] or case.get("source_trial_count") != 0
                                    or case.get("native_guard_error") != guard):
            raise ValueError("Blocked case does not prove the expected missing-plan guard")
        totals = {key: None for key in ("verified_parts", "executed_trial_rows", "executed_block_occurrences", "executed_stages", "executed_gates")}
        if status == "software_pipeline_passed":
            if (not preset["configuration_eligible"] or case.get("participant_index") != 1
                    or any(case.get(key) is not True for key in ("full_plan_preserved", "all_part_packages_verified", "all_block_schedules_compiled"))):
                raise ValueError("Native success lacks complete verified participant evidence")
            execution = case["execution"]
            receipt, independent = execution["receipt"], execution["independent_file_audit"]
            if (execution.get("status") != "completed_software" or receipt.get("synthetic_responses") is not True
                    or receipt.get("clock_basis") != "test-only-sample-paced-simulated-monotonic"
                    or receipt.get("physical_device_used") is not False or receipt.get("timing_qualification") != "unqualified"):
                raise ValueError("Unsupported native execution scope")
            public_token(case["handoff_sha256"], r"[a-f0-9]{64}")
            validator.validate_execution(case, receipt)
            expected_parts = 2 if preset["plan"]["saved_experiment_structure"] == "pre_post" else 1
            if len(case["parts"]) != expected_parts or any(
                    part["trial_count"] != preset["plan"]["source_trial_count"]
                    or part["block_count"] != len(preset["plan"]["source_blocks"]) for part in case["parts"]):
                raise ValueError("Native success does not preserve the complete configured parts")
            for part in case["parts"]:
                public_token(part["manifest_sha256"], r"[a-f0-9]{64}")
            totals = {"verified_parts": len(case["parts"]),
                      **{target: sum(public_count(part[source]) for part in receipt["parts"])
                         for target, source in (("executed_trial_rows", "trial_count"), ("executed_block_occurrences", "block_count"),
                                                ("executed_stages", "stage_count"), ("executed_gates", "gate_count"))}}
            if (independent.get("passed") is not True or independent.get("scoredTrialCount") != totals["executed_trial_rows"]
                    or independent.get("datasetRowCount") != totals["executed_trial_rows"]):
                raise ValueError("Independent results do not cover every executed row")
        generation = case.get("generation", {})
        customizations, algorithm = [], None
        if generation.get("status") == "generated" and generation.get("customized_controls") is not True:
            raise ValueError("Generated native controls require an explicit customization disposition")
        if generation.get("customized_controls") is True:
            if generation.get("legacy_numpy_seed_compatible") is not False:
                raise ValueError("Native source customization must retain the legacy incompatibility")
            algorithm = public_token(generation.get("source_algorithm"), r"[A-Za-z0-9][A-Za-z0-9_.-]{0,100}")
            customizations.append("nonlegacy_native_controls")
        if "toolkit_iti_resolution" in case:
            iti = case["toolkit_iti_resolution"]
            if (iti.get("accepted_for_software_audit") is not True or any(iti.get(key) is not False
                    for key in ("source_distribution_reported", "source_anchor_reported", "legacy_compatible"))):
                raise ValueError("Toolkit ITI customization must preserve source limitations")
            customizations.append("toolkit_iti_realization")
        publication_status = profile["publication_status"]
        if publication_status not in {"published", "unpublished_lab_profile"}:
            raise ValueError("Unknown preset publication scope")
        publication_id = public_token("doi:" + profile["doi"].lower(), doi_pattern) if profile.get("doi") else None
        if (publication_status == "published") != (publication_id is not None):
            raise ValueError("Publication status and citation disagree")
        if publication_id is not None and publication_id not in publications:
            raise ValueError("Preset citation is outside the frozen catalogue")
        reviews = []
        for study in projection["studies"]:
            if identity not in study["templateIds"]:
                continue
            counts = {public_token(key, r"[a-z_]+"): public_count(value) for key, value in study["parameterStatusCounts"].items()}
            if set(counts) - PUBLIC_PARAMETER_STATUSES or sum(counts.values()) != 11:
                raise ValueError("Expected eleven reviewed source dispositions per linked study")
            reviews.append({"study_row_id": public_token(study["studyRowId"], doi_pattern), "parameter_status_counts": counts})
        rows.append({"template_id": identity, "template_sha256": preset["template_sha256"], "capture_sha256": preset["capture_sha256"],
                     "configuration_eligible": preset["configuration_eligible"], "native_status": status,
                     "native_guard_code": guard if case.get("native_guard_error") == guard else None,
                     "source_trial_rows": preset["plan"]["source_trial_count"], "source_blocks": len(preset["plan"]["source_blocks"]),
                     **totals, "software_execution_verified": status == "software_pipeline_passed",
                     "customizations": customizations, "source_algorithm": algorithm,
                     "publication_status": publication_status, "publication_id": publication_id,
                     "study_mapping_status": "study_specific" if reviews else "publication_only" if publication_id else "local_unpublished",
                     "source_reviews": reviews, "published_protocol_equivalence": "not_established_by_software_audit"})
    return {"schema": "pps-public-preset-software-validation.v1", "source_commit": source_commit, "ci_run_url": ci_run_url,
            "evidence_scope": "Windows x64 native test hosts; complete configured parts for representative participant 1; simulated sample clock and synthetic responses. Not installed acquisition or paper replication.",
            "physical_timing_qualification": "not_assessed", "catalogue_native_qualification": "not_assessed",
            "input_sha256": {"native_report": sha256(native_report), "capture_report": sha256(captures / "capture-report.json"),
                             "candidate_manifest": sha256(candidate_manifest), "catalogue": sha256(root / PROJECTION),
                             "profile_status": sha256(root / RESOURCES / "assets/preloads/profile_recreation_status.json"),
                             **{key: public_token(native[key], r"[a-f0-9]{64}") for key in ("designer_test_exe_sha256", "runner_test_exe_sha256")}},
            "counts": {"presets": len(rows), "publications": len(publications), "study_context_rows": len(projection["studies"]),
                       "configuration_eligible": sum(row["configuration_eligible"] for row in rows),
                       "native_statuses": dict(sorted(Counter(row["native_status"] for row in rows).items()))}, "presets": rows}


def write_public_report(report: dict, output: Path) -> None:
    """Fresh output only; CSV carries the same attribution and allowlisted cells."""
    output.mkdir(parents=True, exist_ok=False)
    (output / "software-validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    common = {key: report[key] for key in ("source_commit", "ci_run_url", "evidence_scope", "physical_timing_qualification", "catalogue_native_qualification", "input_sha256")}
    with (output / "software-validation.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*common, *report["presets"][0]])
        writer.writeheader()
        for row in report["presets"]:
            writer.writerow({key: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
                             for key, value in {**common, **row}.items()})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=ROOT / "artifacts/preset-functional-audit")
    parser.add_argument("--public-output", type=Path, help="new directory for sanitized final native CSV/JSON; ordinary audit remains unchanged")
    parser.add_argument("--native-report", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--ci-run-url")
    args = parser.parse_args()
    export_args = (args.public_output, args.native_report, args.candidate_manifest, args.source_commit, args.ci_run_url)
    if any(value is not None for value in export_args):
        if not all(value is not None for value in export_args):
            parser.error("public export requires --public-output, --native-report, --candidate-manifest, --source-commit and --ci-run-url")
        report = build_public_report(ROOT, args.captures, args.native_report, args.candidate_manifest, args.source_commit, args.ci_run_url)
        write_public_report(report, args.public_output)
        print(json.dumps(report["counts"], sort_keys=True))
        return
    report = build_report(ROOT, args.captures)
    (args.captures / "population-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.captures / "population-audit.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
