#!/usr/bin/env python
"""Materialize ready published profiles through dashboard Segments 1-6.

This tool uses the same local companion controller actions as the HTML
dashboard. It prepares Segment 6 manifests but never launches the experiment
runner.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
RESOURCE_ROOT = REPO_ROOT / "packages" / "pps-resources"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.dashboard_app import DashboardController  # noqa: E402
from peripersonal_space_toolkit.profile_recreation import profile_recreation_entry  # noqa: E402
from peripersonal_space_toolkit.templates import load_templates  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Batch-materialize GUI-ready preload profiles through local dashboard Segments 1-6."
    )
    parser.add_argument(
        "--template",
        action="append",
        default=[],
        help="Template ID to materialize. Repeat for multiple IDs. Defaults to all runner-ready profiles.",
    )
    parser.add_argument(
        "--include-blocked",
        action="store_true",
        help="Attempt blocked profiles too; failures are captured in the summary.",
    )
    parser.add_argument(
        "--registry-root",
        type=Path,
        default=REPO_ROOT / "local_data" / "dashboard_projects" / "0_study_project_registry",
        help="Dashboard project registry root.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "local_data" / "profile_recreation_batch" / "materialization_summary.json",
        help="Local summary JSON path.",
    )
    args = parser.parse_args()

    templates = load_templates(RESOURCE_ROOT / "study_templates")
    template_ids = args.template or [template.template_id for template in templates]
    known_ids = {template.template_id for template in templates}
    unknown = [template_id for template_id in template_ids if template_id not in known_ids]
    if unknown:
        raise SystemExit(f"Unknown template ID(s): {', '.join(unknown)}")

    results = []
    for template_id in template_ids:
        status = profile_recreation_entry(template_id, RESOURCE_ROOT)
        readiness = str(status.get("runner_readiness") or "").strip()
        if readiness != "ready" and not args.include_blocked:
            results.append(
                {
                    "template_id": template_id,
                    "status": "skipped",
                    "reason": f"runner_readiness={readiness or 'unknown'}",
                    "profile_parameters_manifest": status.get("profile_parameters_manifest", ""),
                }
            )
            continue
        results.append(materialize_template(template_id, registry_root=args.registry_root))

    summary = {
        "schema": "pps-profile-segment-materialization-summary.v1",
        "local_only": True,
        "runner_launched": False,
        "result_count": len(results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0 if all(item["status"] in {"prepared", "skipped"} for item in results) else 1


def materialize_template(template_id: str, *, registry_root: Path) -> dict[str, Any]:
    batch_root = REPO_ROOT / "local_data" / "profile_recreation_batch" / template_id
    controller = DashboardController(
        design_path=batch_root / "active_design.json",
        render_dir=batch_root / "legacy_render",
        session_root=batch_root / "sessions",
        import_dir=batch_root / "imports",
        preview_dir=batch_root / "previews",
        project_registry_root=registry_root,
    )
    try:
        state = controller.load_template(template_id)
        if (state.get("block_csv_preview") or {}).get("accepted"):
            state = controller.edit_block_csv_preview()
        design = state["design"]
        sequence = _wait_job(controller.start_bake_stimulus_job({"design": design, "bake_recipe": {"kind": "trial_sequence_batch"}}))
        tactile = _wait_job(controller.start_bake_stimulus_job({"design": design, "bake_recipe": {"kind": "audiotactile_trial_batch"}}))
        pool = _wait_job(controller.start_bake_stimulus_job({"design": design, "bake_recipe": {"kind": "trial_repetition_pool", "label": "4_trial_repetition_pool"}}))
        blocks = _wait_job(controller.start_bake_stimulus_job({"design": design, "bake_recipe": {"kind": "block_csv_preview", "label": "5_block_csv_preview"}}))
        accepted = controller.accept_block_csv_preview({})
        prepared = controller.prepare_experiment_run_setup({"design": accepted["design"]})
        return {
            "template_id": template_id,
            "status": "prepared",
            "project_dir": prepared["project"]["project_dir"],
            "segment2_variant_count": sequence["result"].get("variant_count", 0),
            "segment3_total_count": tactile["result"].get("total_count", 0),
            "segment4_total_count": pool["result"].get("total_count", 0),
            "segment5_block_count": blocks["result"].get("block_count", 0),
            "segment6_manifest_path": prepared["run_sequence_setup"].get("manifest_path", ""),
        }
    except Exception as exc:  # noqa: BLE001 - batch summaries should capture per-profile failures.
        return {"template_id": template_id, "status": "failed", "reason": str(exc)}


def _wait_job(job: Any, *, timeout_s: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if job.status in {"succeeded", "failed"}:
            break
        time.sleep(0.05)
    if job.status != "succeeded":
        raise RuntimeError(job.error or f"Job {job.job_id} did not succeed; status={job.status}")
    return {
        "job_id": job.job_id,
        "kind": job.kind,
        "status": job.status,
        "result": job.result or {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
