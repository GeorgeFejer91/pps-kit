#!/usr/bin/env python
"""Protocol 12 matrix for published-profile interface recreation.

This validation is intentionally local-only. It uses the same DashboardController
actions as the browser companion to prove that ready published profiles can move
from preload selection through Segment 6 materialization without claiming
hardware timing or exact author-stimulus equivalence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
RESOURCE_ROOT = REPO_ROOT / "packages" / "pps-resources"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.dashboard_app import DashboardController  # noqa: E402
from peripersonal_space_toolkit.profile_recreation import (  # noqa: E402
    BLOCKED_MISSING,
    BLOCKED_UNSUPPORTED,
    CATEGORY_MISSING_PUBLICATION_PARAMETERS,
    CATEGORY_TOOLKIT_STRUCTURAL_GAP,
    PROFILE_PARAMETERS_SCHEMA,
    READY_RUNNER,
    load_profile_recreation_status,
)
from peripersonal_space_toolkit.templates import load_templates  # noqa: E402


SCHEMA = "pps-protocol12-profile-recreation-interface-matrix.v1"


@dataclass
class Criterion:
    section: str
    name: str
    passed: bool
    detail: str = ""
    required: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "section": self.section,
            "name": self.name,
            "passed": bool(self.passed),
            "required": bool(self.required),
            "detail": self.detail,
        }
        if self.evidence:
            payload["evidence"] = _json_ready(self.evidence)
        return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Protocol 12 published-profile recreation interface matrix.")
    parser.add_argument(
        "--template",
        action="append",
        default=[],
        help="Template ID to validate. Repeat for multiple IDs. Defaults to ready published profiles.",
    )
    parser.add_argument(
        "--profile-set",
        choices=["ready-published", "ready-all", "all"],
        default="ready-published",
        help="Default target set when --template is omitted.",
    )
    parser.add_argument(
        "--blocked-template",
        action="append",
        default=[],
        help="Blocked template ID to use as a negative launch/materialization test. Defaults to one missing and one structural sample.",
    )
    parser.add_argument("--skip-blocked-samples", action="store_true", help="Do not add blocked-profile negative checks.")
    parser.add_argument(
        "--try-blocked",
        action="store_true",
        help="Attempt Segment materialization for blocked profiles and require it to fail. Default only checks the gate.",
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Validate profile gates and blocked negative checks without baking Segment artifacts.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Validation output folder. Defaults to artifacts/validation_runs/profile_recreation_interface_matrix_<stamp>.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    output_dir = args.output_dir or (REPO_ROOT / "artifacts" / "validation_runs" / f"profile_recreation_interface_matrix_{time.strftime('%Y%m%d_%H%M%S')}")
    report = run_matrix(
        output_dir=output_dir,
        templates=args.template,
        profile_set=args.profile_set,
        blocked_templates=args.blocked_template,
        skip_blocked_samples=args.skip_blocked_samples,
        try_blocked=args.try_blocked,
        metadata_only=args.metadata_only,
    )
    print(f"Wrote Protocol 12 profile recreation matrix: {Path(report['report_json'])}")
    return 0 if report["passed"] else 1


def run_matrix(
    *,
    output_dir: Path,
    templates: list[str] | None = None,
    profile_set: str = "ready-published",
    blocked_templates: list[str] | None = None,
    skip_blocked_samples: bool = False,
    try_blocked: bool = False,
    metadata_only: bool = False,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    status = load_profile_recreation_status(RESOURCE_ROOT)
    template_objs = load_templates(RESOURCE_ROOT / "study_templates")
    known_ids = {template.template_id for template in template_objs}
    profiles = {str(profile.get("template_id")): profile for profile in status.get("profiles", [])}
    target_ids = templates or _target_template_ids(status, profile_set=profile_set)
    unknown = sorted(set(target_ids) - known_ids)
    if unknown:
        raise SystemExit(f"Unknown template ID(s): {', '.join(unknown)}")

    blocked_ids = [] if skip_blocked_samples else (blocked_templates or _default_blocked_samples(status, exclude=set(target_ids)))
    unknown_blocked = sorted(set(blocked_ids) - known_ids)
    if unknown_blocked:
        raise SystemExit(f"Unknown blocked template ID(s): {', '.join(unknown_blocked)}")

    criteria: list[Criterion] = []
    profile_results = []
    for template_id in target_ids:
        profile = profiles.get(template_id, {})
        profile_result = _validate_ready_profile_gate(template_id, profile, criteria)
        if metadata_only:
            profile_result["materialization"] = {"status": "skipped", "reason": "metadata_only"}
            criteria.append(
                Criterion(
                    "segment_materialization",
                    f"{template_id}:metadata_only_materialization_skipped",
                    True,
                    "Segment materialization intentionally skipped by --metadata-only.",
                    required=False,
                )
            )
        elif profile_result["gate_passed"]:
            materialized = _materialize_ready_profile(template_id, output_dir=output_dir)
            profile_result["materialization"] = materialized
            _audit_materialization(template_id, materialized, criteria)
        else:
            profile_result["materialization"] = {"status": "skipped", "reason": "profile_gate_failed"}
        profile_results.append(profile_result)

    blocked_results = []
    for template_id in blocked_ids:
        profile = profiles.get(template_id, {})
        result = _validate_blocked_profile(template_id, profile, criteria)
        if try_blocked:
            materialized = _materialize_ready_profile(template_id, output_dir=output_dir)
            result["materialization_attempt"] = materialized
            criteria.append(
                Criterion(
                    "blocked_profile_negative_tests",
                    f"{template_id}:blocked_materialization_fails",
                    materialized.get("status") != "prepared",
                    "Blocked profile must not complete Segment materialization when forced.",
                    evidence=materialized,
                )
            )
        blocked_results.append(result)

    sections = _section_summaries(criteria)
    required = [criterion for criterion in criteria if criterion.required]
    passed = all(criterion.passed for criterion in required)
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "repo_root": str(REPO_ROOT),
        "output_dir": str(output_dir),
        "profile_set": profile_set,
        "metadata_only": metadata_only,
        "passed": passed,
        "required_count": len(required),
        "required_passed_count": sum(1 for criterion in required if criterion.passed),
        "ready_profile_count": len(target_ids),
        "blocked_profile_sample_count": len(blocked_ids),
        "ready_profiles": target_ids,
        "blocked_profile_samples": blocked_ids,
        "profile_results": profile_results,
        "blocked_results": blocked_results,
        "criteria": [criterion.as_dict() for criterion in criteria],
        "sections": sections,
        "report_json": str(output_dir / "profile_recreation_interface_matrix_report.json"),
        "report_md": str(output_dir / "profile_recreation_interface_matrix_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _target_template_ids(status: dict[str, Any], *, profile_set: str) -> list[str]:
    profiles = list(status.get("profiles") or [])
    if profile_set == "all":
        return [str(profile.get("template_id")) for profile in profiles if str(profile.get("template_id") or "")]
    ready = [
        str(profile.get("template_id"))
        for profile in profiles
        if str(profile.get("runner_readiness") or "") == READY_RUNNER
    ]
    if profile_set == "ready-all":
        return ready
    return [
        template_id
        for template_id in ready
        if _is_published_profile(status, template_id=template_id)
    ]


def _is_published_profile(status: dict[str, Any], *, template_id: str) -> bool:
    profile = next(
        (item for item in status.get("profiles", []) if str(item.get("template_id") or "") == template_id),
        {},
    )
    return str(profile.get("publication_status") or "published") != "unpublished_lab_profile"


def _default_blocked_samples(status: dict[str, Any], *, exclude: set[str]) -> list[str]:
    categories = status.get("categories") or {}
    missing = [template_id for template_id in categories.get(CATEGORY_MISSING_PUBLICATION_PARAMETERS, []) if template_id not in exclude]
    structural = [template_id for template_id in categories.get(CATEGORY_TOOLKIT_STRUCTURAL_GAP, []) if template_id not in exclude]
    selected: list[str] = []
    if missing:
        selected.append(next((template_id for template_id in missing if template_id not in structural), missing[0]))
    if structural:
        candidate = next((template_id for template_id in structural if template_id not in selected), structural[0])
        if candidate not in selected:
            selected.append(candidate)
    return selected


def _validate_ready_profile_gate(template_id: str, profile: dict[str, Any], criteria: list[Criterion]) -> dict[str, Any]:
    manifest_path = _profile_manifest_path(template_id)
    manifest = _read_json(manifest_path)
    gate_passed = (
        manifest_path.is_file()
        and manifest.get("schema") == PROFILE_PARAMETERS_SCHEMA
        and str(profile.get("runner_readiness") or "") == READY_RUNNER
        and bool(profile.get("profile_checks_passed"))
        and bool(profile.get("segment_0_to_4_profile_checks_passed"))
        and int(profile.get("missing_parameter_count") or 0) == 0
        and int(profile.get("unsupported_structure_count") or 0) == 0
    )
    criteria.append(
        Criterion(
            "profile_gate",
            f"{template_id}:ready_profile_gate",
            gate_passed,
            "Ready profiles must pass the Segment 0-4 recreation gate and have no blockers.",
            evidence={
                "profile_parameters_manifest": str(manifest_path),
                "manifest_exists": manifest_path.is_file(),
                "manifest_schema": manifest.get("schema", ""),
                "runner_readiness": profile.get("runner_readiness", ""),
                "profile_checks_passed": profile.get("profile_checks_passed", False),
                "segment_0_to_4_profile_checks_passed": profile.get("segment_0_to_4_profile_checks_passed", False),
                "missing_parameter_count": profile.get("missing_parameter_count", ""),
                "unsupported_structure_count": profile.get("unsupported_structure_count", ""),
            },
        )
    )
    published_profile = str(profile.get("publication_status") or manifest.get("publication_status") or "published") != "unpublished_lab_profile"
    caveat_text = str(manifest.get("notes") or "")
    caveat_ok = bool(caveat_text) and ((not published_profile) or "original authors" in caveat_text)
    criteria.append(
        Criterion(
            "profile_gate",
            f"{template_id}:published_recreation_caveat_present",
            caveat_ok,
            "Profile manifest must carry the toolkit-recreation caveat.",
            evidence={"notes": caveat_text, "published_profile": published_profile},
        )
    )
    return {
        "template_id": template_id,
        "title": profile.get("title", ""),
        "doi": profile.get("doi", ""),
        "profile_parameters_manifest": str(manifest_path),
        "gate_passed": gate_passed,
    }


def _validate_blocked_profile(template_id: str, profile: dict[str, Any], criteria: list[Criterion]) -> dict[str, Any]:
    readiness = str(profile.get("runner_readiness") or "")
    reasons = [str(item.get("reason") or "") for item in profile.get("missing_publication_parameters", [])]
    reasons.extend(str(item.get("reason") or "") for item in profile.get("unsupported_toolkit_structures", []))
    blocked = readiness in {BLOCKED_MISSING, BLOCKED_UNSUPPORTED} and bool(reasons)
    criteria.append(
        Criterion(
            "blocked_profile_negative_tests",
            f"{template_id}:blocked_profile_has_reason",
            blocked,
            "Blocked profile must stay non-launchable and expose concrete blocker reasons.",
            evidence={
                "runner_readiness": readiness,
                "missing_parameter_count": profile.get("missing_parameter_count", ""),
                "unsupported_structure_count": profile.get("unsupported_structure_count", ""),
                "reasons": reasons,
            },
        )
    )
    return {
        "template_id": template_id,
        "runner_readiness": readiness,
        "blocked": blocked,
        "reasons": reasons,
    }


def _materialize_ready_profile(template_id: str, *, output_dir: Path) -> dict[str, Any]:
    batch_root = output_dir / "materialized_profiles" / template_id
    session_root = batch_root / "sessions"
    state_root = batch_root / "dashboard_state"
    controller = DashboardController(
        design_path=batch_root / "active_design.json",
        render_dir=batch_root / "legacy_render",
        session_root=session_root,
        import_dir=batch_root / "imports",
        preview_dir=batch_root / "previews",
        project_registry_root=output_dir / "dashboard_projects" / "0_study_project_registry",
        state_root=state_root,
    )
    try:
        state = controller.load_template(template_id)
        profile_state = _profile_state_summary(state)
        progress: list[dict[str, Any]] = []
        with controller._lock:  # Validation harness: use the same controller-owned profile materializer without launching Focus Mode.
            project = controller._ensure_project_context(controller.design)
            design = controller.design
        materialization = controller._ensure_profile_run_artifacts(project, design, progress_callback=progress.append)
        session_state = controller.prepare_session(
            {"participant_id": "P001"},
            progress_callback=progress.append,
        )
        run_setup = session_state.get("run_sequence_setup") or {}
        project_payload = session_state.get("project") or {}
        session_payload = session_state.get("session") or {}
        segments = session_state.get("project_segments") or {}
        counts = _profile_segment_counts(session_state)
        return {
            "template_id": template_id,
            "status": "prepared",
            "project_dir": project_payload.get("project_dir", ""),
            "selected_template": profile_state.get("selected_template", ""),
            "profile_read_only": profile_state.get("profile_read_only", False),
            "profile_notice": profile_state.get("profile_notice", ""),
            "profile_materialization_status": materialization.get("status", ""),
            "profile_materialization_steps": materialization.get("steps", []),
            "progress_phase_count": len(progress),
            "segment_statuses": {
                key: value.get("status", "")
                for key, value in segments.items()
                if isinstance(value, dict)
            },
            "segment2_variant_count": counts.get("segment2_variant_count", 0),
            "segment3_total_count": counts.get("segment3_total_count", 0),
            "segment4_total_count": counts.get("segment4_total_count", 0),
            "segment5_block_count": counts.get("segment5_block_count", 0),
            "segment6_manifest_path": run_setup.get("manifest_path", ""),
            "segment6_csv_path": run_setup.get("csv_path", ""),
            "session_manifest_path": session_payload.get("manifest_path", ""),
            "session_dir": session_payload.get("session_dir", ""),
            "expected_session_root": str(session_root),
            "controller_state_root": str(state_root),
            "participant_id": session_payload.get("participant_id", ""),
        }
    except Exception as exc:  # noqa: BLE001 - validation report should retain per-profile failure details.
        return {
            "template_id": template_id,
            "status": "failed",
            "reason": str(exc),
            "expected_session_root": str(session_root),
            "controller_state_root": str(state_root),
        }


def _profile_state_summary(state: dict[str, Any]) -> dict[str, Any]:
    custom_workflow = state.get("custom_workflow") or {}
    selected_template = str(state.get("selected_template") or "")
    inventory = state.get("preload_inventory") or {}
    notice = str(inventory.get("message") or inventory.get("notes") or "")
    return {
        "selected_template": selected_template,
        "profile_read_only": bool(selected_template and not custom_workflow.get("is_custom")),
        "profile_notice": notice,
    }


def _audit_materialization(template_id: str, materialized: dict[str, Any], criteria: list[Criterion]) -> None:
    project_dir = Path(str(materialized.get("project_dir") or ""))
    segment6_manifest = Path(str(materialized.get("segment6_manifest_path") or ""))
    segment6_csv = Path(str(materialized.get("segment6_csv_path") or ""))
    session_manifest = Path(str(materialized.get("session_manifest_path") or ""))
    session_dir = Path(str(materialized.get("session_dir") or ""))
    expected_session_root = Path(str(materialized.get("expected_session_root") or ""))
    prepared = materialized.get("status") == "prepared"
    counts_ok = all(int(materialized.get(key) or 0) > 0 for key in ("segment2_variant_count", "segment3_total_count", "segment4_total_count", "segment5_block_count"))
    paths_ok = (
        _path_is_dir(project_dir)
        and _path_is_file(segment6_manifest)
        and _path_is_file(segment6_csv)
        and _path_is_file(session_manifest)
        and _path_is_dir(session_dir)
    )
    outside_preloads = "assets\\preloads" not in str(project_dir).lower() and "assets/preloads" not in str(project_dir).lower()
    session_paths_profile_local = (
        _path_is_dir(expected_session_root)
        and _path_is_within(session_dir, expected_session_root)
        and _path_is_within(session_manifest, expected_session_root)
    )
    criteria.append(
        Criterion(
            "segment_materialization",
            f"{template_id}:segments_1_to_6_materialized",
            prepared and counts_ok and paths_ok and outside_preloads,
            "Ready profile must materialize through Segments 1-6 under writable validation output paths.",
            evidence=materialized,
        )
    )
    criteria.append(
        Criterion(
            "segment_materialization",
            f"{template_id}:participant_package_profile_local",
            prepared and session_paths_profile_local,
            "Prepared participant session package must stay under this template's validation session root.",
            evidence={
                "expected_session_root": str(expected_session_root),
                "session_dir": str(session_dir),
                "session_manifest_path": str(session_manifest),
                "session_dir_profile_local": _path_is_within(session_dir, expected_session_root),
                "session_manifest_profile_local": _path_is_within(session_manifest, expected_session_root),
            },
        )
    )
    criteria.append(
        Criterion(
            "interface_profile_behavior",
            f"{template_id}:profile_selection_read_only",
            materialized.get("selected_template") == template_id and bool(materialized.get("profile_read_only")),
            "Published preload should load as the selected read-only profile.",
            evidence={
                "selected_template": materialized.get("selected_template", ""),
                "profile_read_only": materialized.get("profile_read_only", False),
                "profile_notice": materialized.get("profile_notice", ""),
            },
        )
    )


def _profile_segment_counts(state: dict[str, Any]) -> dict[str, int]:
    trial_sequence = state.get("trial_sequence_bake") or {}
    trial_files = state.get("trial_file_bake") or {}
    trial_pool = state.get("trial_pool_bake") or {}
    block_preview = state.get("block_csv_preview") or {}
    return {
        "segment2_variant_count": _first_int(trial_sequence, ("variant_count", "sequence_count", "file_count")),
        "segment3_total_count": _first_int(trial_files, ("total_count", "file_count", "trial_file_count")),
        "segment4_total_count": _first_int(trial_pool, ("total_count", "row_count", "trial_count")),
        "segment5_block_count": _first_int(block_preview, ("block_count", "blocks")),
    }


def _first_int(payload: dict[str, Any], keys: Iterable[str]) -> int:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0


def _profile_manifest_path(template_id: str) -> Path:
    return (
        REPO_ROOT
        / "packages"
        / "pps-resources"
        / "assets"
        / "preloads"
        / template_id
        / "01_profile"
        / "profile_parameters_manifest.json"
    )


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _path_is_file(path: str | Path) -> bool:
    try:
        return os.path.isfile(_filesystem_path(path))
    except OSError:
        return False


def _path_is_dir(path: str | Path) -> bool:
    try:
        return os.path.isdir(_filesystem_path(path))
    except OSError:
        return False


def _path_is_within(path: str | Path, root: str | Path) -> bool:
    try:
        resolved_path = Path(path).resolve()
        resolved_root = Path(root).resolve()
        return resolved_path == resolved_root or resolved_root in resolved_path.parents
    except OSError:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _section_summaries(criteria: Iterable[Criterion]) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    for criterion in criteria:
        section = sections.setdefault(criterion.section, {"count": 0, "passed_count": 0, "required_count": 0, "required_passed_count": 0})
        section["count"] += 1
        if criterion.passed:
            section["passed_count"] += 1
        if criterion.required:
            section["required_count"] += 1
            if criterion.passed:
                section["required_passed_count"] += 1
    for section in sections.values():
        section["passed"] = section["required_count"] == section["required_passed_count"]
    return sections


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Protocol 12 Profile Recreation Interface Matrix",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Required criteria: `{report.get('required_passed_count')}/{report.get('required_count')}`",
        f"- Ready profiles: `{report.get('ready_profile_count')}`",
        f"- Blocked profile samples: `{report.get('blocked_profile_sample_count')}`",
        f"- Metadata only: `{report.get('metadata_only')}`",
        "",
        "## Ready Profiles",
    ]
    for result in report.get("profile_results", []):
        materialization = result.get("materialization") or {}
        lines.append(f"- `{result.get('template_id')}`: gate=`{result.get('gate_passed')}`, materialization=`{materialization.get('status', '')}`")
    lines.extend(["", "## Blocked Samples"])
    for result in report.get("blocked_results", []):
        lines.append(f"- `{result.get('template_id')}`: blocked=`{result.get('blocked')}`, readiness=`{result.get('runner_readiness')}`")
    failures = [criterion for criterion in report.get("criteria", []) if criterion.get("required") and not criterion.get("passed")]
    if failures:
        lines.extend(["", "## Required Failures"])
        for failure in failures:
            lines.append(f"- `{failure.get('section')}.{failure.get('name')}`: {failure.get('detail')}")
    lines.extend(
        [
            "",
            "This protocol validates toolkit interface recreation and Segment handoff. It does not prove physical timing, Woojer mechanical onset, or exact reuse of authors' private stimulus assets.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
