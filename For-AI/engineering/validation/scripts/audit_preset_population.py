"""Join the frozen archive to every shipped preset and full browser plan.

This development-only inventory does not render or execute trials. Its assertions
protect the input population and complete row contracts for the native audit.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[4]
RESOURCES = "packages/pps-resources"
PROJECTION = "apps/designer/frontend/publication_study_reviews.v1.json"
ROW_CONTRACT_SOURCE = "packages/pps-runtime/src/peripersonal_space_toolkit/dashboard_app.py"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--captures", type=Path, default=ROOT / "artifacts/preset-functional-audit")
    args = parser.parse_args()
    report = build_report(ROOT, args.captures)
    (args.captures / "population-audit.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.captures / "population-audit.md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()
