"""Join the frozen archive to every shipped preset and full browser plan.

This development-only inventory does not render or execute trials. Its assertions
protect the input population and complete row contracts for the native audit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
RESOURCES = "packages/pps-resources"
PROJECTION = "apps/designer/frontend/publication_study_reviews.v1.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_by(items: list[dict], key: str) -> dict:
    result = {item[key]: item for item in items}
    if len(result) != len(items):
        raise ValueError(f"Duplicate {key}")
    return result


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
        presets.append({
            "template_id": template_id, "template_sha256": case["template_sha256"],
            "capture_sha256": case["capture_sha256"], "publication_status": profile["publication_status"],
            "configuration_eligible": eligible,
            "missing_inputs": profile.get("missing_publication_parameters", []),
            "unsupported_structures": profile.get("unsupported_toolkit_structures", []),
            "study_row_ids": sorted(k for k, row in studies.items() if template_id in row["templateIds"]),
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
        "input_hashes": {**receipt["input_hashes"], PROJECTION: sha256(root / PROJECTION)},
        "counts": {"publications": len(publications), "study_context_rows": len(studies),
                   "publications_with_presets": sum(bool(row["templateIds"]) for row in publications.values()),
                   "study_rows_with_presets": sum(bool(row["templateIds"]) for row in studies.values()),
                   "presets": len(presets), "configuration_eligible": sum(x["configuration_eligible"] for x in presets),
                   "blocked_as_shipped": sum(not x["configuration_eligible"] for x in presets),
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
