"""Run ready profiles with participant-like mouse clicks and compare outcomes.

This audit is the software participant-emulation layer for ready published
profiles. It materializes each ready profile, runs it through
SessionRunnerController with the fast validation audio engine, injects
deterministic condition-dependent mouse clicks after tactile onsets, and
compares the runner-produced analysis RTs with the paper-derived expected
effect directions.

The generated rows are not human participant data. They are mouse-click
simulated participant-like runner data intended to prove that expected-outcome
comparisons can be exercised through the experiment runner rather than through
post-hoc RT table rewriting.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_profile_recreation_interface_matrix as protocol12  # noqa: E402
import run_ready_profile_expected_contrast_audit as contrast  # noqa: E402
import run_ready_profile_runner_smoke as runner_smoke  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    load_run_package,
)


SCHEMA = "pps-ready-profile-mouse-click-expected-outcome-audit.v1"
MODEL_ID = "profile_expected_outcome_mouse_click_participant_like.v1"
READY_GAP = contrast.READY_GAP
LEDGER_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "artifacts"
    / "validation_runs"
    / "current_goal_ready_profile_mouse_click_expected_outcome_20260715"
)
EVIDENCE_BOUNDARY = (
    "This audit uses actual SessionRunnerController.log_click() calls after tactile "
    "onsets to create participant-like mouse-click data and then evaluates the "
    "runner-produced analysis RTs against structured paper outcome directions. "
    "It is deterministic software validation only: not human participant data, "
    "not physical loopback evidence, and not a scientific PPS-effect replication claim."
)

CONTEXTS_BY_RECORD = {
    "tonelli_2019_echolocation": ["pre_echolocation", "post_echolocation"],
    "galli_2015_wheelchair": ["active_nonexpert", "visible_passive", "blindfolded_passive"],
}


class PlannerStats:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        audio_soas = [
            contrast._as_float(row.get("soa_ms"))
            for row in rows
            if _family(row) == "audio_tactile" and math.isfinite(contrast._as_float(row.get("soa_ms")))
        ]
        self.soa_min = min(audio_soas) if audio_soas else math.nan
        self.soa_max = max(audio_soas) if audio_soas else math.nan
        self.soa_center = (
            (self.soa_min + self.soa_max) / 2.0
            if math.isfinite(self.soa_min) and math.isfinite(self.soa_max)
            else math.nan
        )
        self.max_center_offset = (
            max(abs(value - self.soa_center) for value in audio_soas)
            if audio_soas and math.isfinite(self.soa_center)
            else math.nan
        )


class MouseClickResponsePlanner:
    def __init__(
        self,
        *,
        record_id: str,
        context: str,
        rows: list[dict[str, Any]],
        max_samples_per_key: int,
    ) -> None:
        self.record_id = record_id
        self.context = context
        self.stats = PlannerStats(rows)
        self.max_samples_per_key = None if int(max_samples_per_key) <= 0 else max(1, int(max_samples_per_key))
        self.counts_by_key: dict[str, int] = {}

    def plan(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = _normalize_row(payload)
        plan = _model_response(self.record_id, row, self.context, self.stats)
        if not plan:
            plan = _plan(
                "unmodeled_tactile_control",
                150.0,
                sample_key=str(row.get("trial_uid") or f"unmodeled_{len(self.counts_by_key)}"),
                comparison_excluded="true",
            )
        sample_key = str(plan.get("sample_key") or plan.get("synthetic_condition") or "")
        if not sample_key:
            return None
        if self.max_samples_per_key is not None and self.counts_by_key.get(sample_key, 0) >= self.max_samples_per_key:
            return None
        self.counts_by_key[sample_key] = self.counts_by_key.get(sample_key, 0) + 1
        plan["sample_key"] = sample_key
        return plan


def run_audit(
    *,
    ledger_path: Path = LEDGER_PATH,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    records: list[str] | None = None,
    max_samples_per_condition: int = 0,
    keep_materialized: bool = False,
) -> dict[str, Any]:
    ledger_path = Path(ledger_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = _read_json(ledger_path)
    target_records = [
        record
        for record in ledger.get("records", [])
        if record.get("observed_comparison_gap") == READY_GAP
    ]
    if records:
        wanted = set(records)
        target_records = [record for record in target_records if str(record.get("record_id") or "") in wanted]

    record_results = [
        _run_record(
            record,
            output_dir=output_dir,
            max_samples_per_condition=max_samples_per_condition,
            keep_materialized=keep_materialized,
        )
        for record in sorted(target_records, key=lambda item: str(item.get("record_id") or ""))
    ]
    summary = _summary(record_results)
    criteria = {
        "ledger_exists": ledger_path.is_file(),
        "ready_records_found": bool(record_results),
        "all_record_mouse_click_comparisons_passed": bool(record_results)
        and all(result.get("passed") for result in record_results),
        "all_runner_clicks_have_response_markers": all(
            result.get("mouse_click_count") == result.get("response_marker_start_count")
            for result in record_results
        ),
    }
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "model": {
            "model_id": MODEL_ID,
            "model_role": "deterministic participant-like mouse-click response model over ready profile runner rows",
            "max_samples_per_condition": int(max_samples_per_condition),
            "sampling_mode": "all_modeled_tactile_trials"
            if int(max_samples_per_condition) <= 0
            else "capped_per_condition",
            "contexts_by_record": CONTEXTS_BY_RECORD,
            "assumption_boundary": EVIDENCE_BOUNDARY,
        },
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "source_expected_outcome_ledger": _repo_relative(ledger_path),
        "summary": summary,
        "records": record_results,
        "report_json": str(output_dir / "ready_profile_mouse_click_expected_outcome_audit_report.json"),
        "report_md": str(output_dir / "ready_profile_mouse_click_expected_outcome_audit_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _run_record(
    record: dict[str, Any],
    *,
    output_dir: Path,
    max_samples_per_condition: int,
    keep_materialized: bool,
) -> dict[str, Any]:
    record_id = str(record.get("record_id") or "")
    contexts = CONTEXTS_BY_RECORD.get(record_id, [""])
    runs: list[dict[str, Any]] = []
    observed_rows: list[dict[str, Any]] = []
    for template_id in [str(value) for value in record.get("current_template_ids") or []]:
        for context in contexts:
            run = _run_template_context(
                record_id=record_id,
                template_id=template_id,
                context=context,
                output_dir=output_dir,
                max_samples_per_condition=max_samples_per_condition,
                keep_materialized=keep_materialized,
            )
            runs.append(run)
            observed_rows.extend(run.pop("_observed_rows", []))
    observed_path = output_dir / "observed_mouse_click_analysis" / f"{record_id}_observed_rows.csv"
    _write_rows(observed_path, observed_rows)
    comparison = _evaluate_record(record, observed_rows)
    mouse_click_count = sum(int((run.get("event_counts") or {}).get("mouse_click") or 0) for run in runs)
    response_marker_count = sum(
        int((run.get("event_counts") or {}).get("response_marker_start") or 0)
        for run in runs
    )
    planned_click_count = sum(int(run.get("planned_click_count") or 0) for run in runs)
    observed_hit_count = len(observed_rows)
    run_passed = bool(runs) and all(run.get("passed") for run in runs)
    passed = bool(
        run_passed
        and comparison.get("pass")
        and planned_click_count > 0
        and observed_hit_count == planned_click_count
        and mouse_click_count == planned_click_count
        and response_marker_count == planned_click_count
    )
    return {
        "record_id": record_id,
        "citation_short": str(record.get("citation_short") or ""),
        "template_ids": [str(value) for value in record.get("current_template_ids") or []],
        "passed": passed,
        "status": "mouse_click_simulated_participant_like_comparison_passed"
        if passed
        else "mouse_click_simulated_participant_like_comparison_failed",
        "planned_click_count": planned_click_count,
        "mouse_click_count": mouse_click_count,
        "response_marker_start_count": response_marker_count,
        "observed_analysis_hit_count": observed_hit_count,
        "observed_rows_csv": str(observed_path),
        "comparison": comparison,
        "runs": runs,
        "required_next_step": (
            "Replace deterministic mouse-click simulated participant-like data with collected participant data "
            "before making a scientific PPS-effect replication claim."
        ),
    }


def _run_template_context(
    *,
    record_id: str,
    template_id: str,
    context: str,
    output_dir: Path,
    max_samples_per_condition: int,
    keep_materialized: bool,
) -> dict[str, Any]:
    label = context or "default"
    run_dir = output_dir / "runs" / record_id / template_id / label
    materialized = protocol12._materialize_ready_profile(template_id, output_dir=run_dir)
    if materialized.get("status") != "prepared":
        return {
            "template_id": template_id,
            "context": context,
            "passed": False,
            "materialization": materialized,
            "failure": "profile materialization did not prepare a session package",
        }
    package = load_run_package(Path(str(materialized["session_manifest_path"])))
    package_rows = [_normalize_row(row) for block in package.blocks for row in _read_csv(block.manifest_path)]
    planner = MouseClickResponsePlanner(
        record_id=record_id,
        context=context,
        rows=package_rows,
        max_samples_per_key=max_samples_per_condition,
    )
    planned_clicks: list[dict[str, Any]] = []
    engine = runner_smoke.FastProfileSmokeAudioEngine(
        max_clicks_per_block=1_000_000,
        response_delay_s=0.0,
    )
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_events_csv=True,
            write_internal_xdf=True,
            write_analysis_csvs=True,
            write_lsl_marker_mirror=True,
            write_trigger_dictionary=True,
            start_backup_recording=False,
            start_external_labrecorder=False,
        ),
        enable_topup=False,
        instruction_continue_callback=lambda _context: True,
        runner_metadata={"participant_code": package.participant_id},
    )

    def _click_after_tactile(payload: dict[str, Any]) -> None:
        plan = planner.plan(payload)
        if plan is None:
            return
        row = _normalize_row(payload)
        controller.events.flush_callback_events(timeout_s=0.5)
        planned_rt_ms = float(plan["planned_rt_ms"])
        time.sleep(planned_rt_ms / 1000.0)
        controller.log_click(x=320 + len(planned_clicks), y=240, in_target=True)
        planned_clicks.append(
            {
                "record_id": record_id,
                "template_id": template_id,
                "context": context,
                "trial_uid": str(row.get("trial_uid") or ""),
                "block_label": str(row.get("block_label") or ""),
                "family": str(row.get("family") or ""),
                "soa_ms": str(row.get("soa_ms") or ""),
                "row_label": str(row.get("row_label") or ""),
                "sequence_labels": str(row.get("sequence_labels") or ""),
                "sequence_variant_key": str(row.get("sequence_variant_key") or ""),
                **plan,
            }
        )

    engine.set_tactile_callback(_click_after_tactile)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)
    event_rows = _read_csv(result.events_csv)
    event_counts = runner_smoke._event_counts(event_rows)
    analysis_path = result.analysis_outputs.get("analysis_ready_trials", Path())
    analysis_rows = _read_csv(analysis_path)
    observed_rows = _join_planned_clicks_to_analysis(planned_clicks, analysis_rows)
    planned_path = run_dir / "planned_mouse_clicks.csv"
    observed_path = run_dir / "observed_mouse_click_rows.csv"
    _write_rows(planned_path, planned_clicks)
    _write_rows(observed_path, observed_rows)
    hit_count = sum(1 for row in analysis_rows if str(row.get("hit") or "").strip().lower() in {"true", "1", "yes"})
    passed = bool(
        result.completed
        and not result.interrupted
        and planned_clicks
        and len(observed_rows) == len(planned_clicks)
        and event_counts.get("mouse_click", 0) == len(planned_clicks)
        and event_counts.get("response_marker_start", 0) == len(planned_clicks)
        and hit_count >= len(planned_clicks)
        and Path(result.events_csv).is_file()
        and Path(result.events_xdf).is_file()
        and Path(analysis_path).is_file()
    )
    profile = {
        "template_id": template_id,
        "context": context,
        "passed": passed,
        "materialization": materialized,
        "session_manifest_path": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "block_count": len(package.blocks),
        "played_block_count": len(engine.played_blocks),
        "planned_click_count": len(planned_clicks),
        "observed_click_hit_count": len(observed_rows),
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_ready_hit_count": hit_count,
        "event_counts": event_counts,
        "outputs": {
            "events_csv": str(result.events_csv),
            "events_xdf": str(result.events_xdf),
            "analysis_ready_trials": str(analysis_path),
            "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
            "lsl_markers_csv": str(result.lsl_markers_csv or ""),
            "trigger_dictionary": str(result.trigger_dictionary_path or ""),
            "session_metadata": str(result.session_metadata_path or ""),
            "planned_mouse_clicks": str(planned_path),
            "observed_mouse_click_rows": str(observed_path),
        },
        "warnings": list(result.warnings),
        "_observed_rows": observed_rows,
    }
    if not keep_materialized:
        profile = runner_smoke._compact_profile_evidence(profile, output_dir=run_dir)
    return profile


def _model_response(
    record_id: str,
    row: dict[str, Any],
    context: str,
    stats: PlannerStats,
) -> dict[str, Any] | None:
    family = _family(row)
    if record_id == "smartphone_rt_methods_2025" and family == "audio_tactile":
        condition = contrast._dynaspace_condition(row)
        if not condition:
            return None
        rt_ms = 115.0 if condition == "looming" else 150.0
        return _plan(condition, rt_ms, synthetic_source_condition=condition)

    if record_id == "noel_2015_bodily_self" and family == "audio_tactile":
        proximity = _linear_proximity(row, stats)
        space = contrast._noel_space(row)
        synchrony = contrast._noel_synchrony(row)
        if not space or not synchrony or not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        rt_ms = 160.0 - (35.0 * proximity)
        if space == "front" and synchrony == "synchronous":
            rt_ms -= 20.0
        elif space == "back" and synchrony == "synchronous":
            rt_ms += 25.0 * proximity
        return _plan(
            f"{space}_{synchrony}_{distance_bin}",
            rt_ms,
            synthetic_space=space,
            synthetic_synchrony=synchrony,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "serino_2015_peri_trunk_exp1" and family == "audio_tactile":
        motion = contrast._serino_motion_direction(row)
        proximity = _linear_proximity(row, stats, flip=motion == "receding")
        if not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        return _plan(
            distance_bin,
            160.0 - (45.0 * proximity),
            synthetic_motion_direction=motion,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "serino_2015_peri_hand_exp3" and family == "audio_tactile":
        motion = contrast._serino_motion_direction(row)
        proximity = _linear_proximity(row, stats, flip=motion == "receding")
        if not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        rt_ms = 158.0 - (40.0 * proximity)
        if motion == "looming":
            rt_ms -= 8.0 * proximity
        return _plan(
            f"{motion}_{distance_bin}",
            rt_ms,
            synthetic_motion_direction=motion,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "serino_2015_front_back_trunk_exp2":
        if family == "baseline":
            return _plan("baseline", 165.0, synthetic_distance_bin="baseline")
        if family != "audio_tactile":
            return None
        path = contrast._front_back_trunk_path(row)
        proximity = _center_proximity(row, stats)
        if not math.isfinite(proximity):
            return None
        distance_bin = "near_crossing" if proximity >= 0.8 else "far_endpoint" if proximity <= 0.2 else "middle"
        return _plan(
            f"{path or 'unknown'}_{distance_bin}",
            160.0 - (46.0 * proximity),
            synthetic_front_back_path=path,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "canzoneri_2012_dynamic_sounds" and family == "audio_tactile":
        motion = contrast._approach_recede_direction(row)
        proximity = _linear_proximity(row, stats, flip=motion == "receding")
        if not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        rt_ms = 160.0 - (46.0 * proximity) if motion == "approaching" else 142.0 - (6.0 * proximity)
        return _plan(
            f"{motion}_{distance_bin}",
            rt_ms,
            synthetic_motion_direction=motion,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "matsuda_2021_four_directions" and family == "audio_tactile":
        body_direction = contrast._body_relative_direction(row)
        motion = contrast._approach_recede_direction(row)
        proximity = _linear_proximity(row, stats, flip=motion == "receding")
        if not body_direction or not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        rt_ms = 160.0 - (42.0 * proximity) if motion == "approaching" else 140.0
        return _plan(
            f"{motion}_{distance_bin}",
            rt_ms,
            sample_key=f"{body_direction}_{motion}_{distance_bin}",
            synthetic_motion_direction=motion,
            synthetic_body_direction=body_direction,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "lamia_2026_arm_movement" and family == "audio_tactile":
        movement_state, tactile_site = contrast._lamia_block_factors(row)
        motion = contrast._approach_recede_direction(row)
        proximity = _linear_proximity(row, stats, flip=motion == "receding")
        if not movement_state or not tactile_site or not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        if motion == "approaching" and movement_state == "static":
            rt_ms = 162.0 - (38.0 * proximity)
        elif motion == "approaching" and movement_state == "motor":
            rt_ms = 140.0 - (4.0 * proximity)
        else:
            rt_ms = 142.0
        return _plan(
            f"{movement_state}_{motion}_{distance_bin}",
            rt_ms,
            sample_key=f"{movement_state}_{tactile_site}_{motion}_{distance_bin}",
            synthetic_motion_direction=motion,
            synthetic_movement_state=movement_state,
            synthetic_tactile_site=tactile_site,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "pfeiffer_2018_vestibular" and family == "audio_tactile":
        condition = contrast._pfeiffer_vestibular_condition(row)
        proximity = _linear_proximity(row, stats)
        if not condition or not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        rt_ms = 160.0 - (12.0 * proximity)
        if condition in {"congruent_rotation", "incongruent_rotation"}:
            rt_ms -= 8.0
        if condition == "congruent_rotation":
            rt_ms -= 26.0 * (1.0 - proximity)
        elif condition == "incongruent_rotation":
            rt_ms -= 4.0 * (1.0 - proximity)
        return _plan(
            f"{condition}_{distance_bin}",
            rt_ms,
            synthetic_pfeiffer_condition=condition,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "tonelli_2019_echolocation":
        if context not in {"pre_echolocation", "post_echolocation"}:
            return None
        if family == "baseline":
            return _plan(f"{context}_baseline", 165.0, synthetic_training_session=context, synthetic_distance_bin="baseline")
        if family != "audio_tactile":
            return None
        proximity = _linear_proximity(row, stats)
        if not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        rt_ms = 160.0 - ((18.0 if context == "pre_echolocation" else 36.0) * proximity)
        if context == "post_echolocation" and distance_bin == "middle":
            rt_ms -= 7.0
        return _plan(
            f"{context}_{distance_bin}",
            rt_ms,
            synthetic_training_session=context,
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "galli_2015_wheelchair":
        if context not in {"active_nonexpert", "visible_passive", "blindfolded_passive"}:
            return None
        if family == "baseline":
            return _plan(
                f"{context}_baseline",
                165.0,
                synthetic_training_context=context,
                synthetic_wheelchair_path=contrast._wheelchair_path(row),
                synthetic_distance_bin="baseline",
            )
        if family != "audio_tactile":
            return None
        proximity = _linear_proximity(row, stats)
        if not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        rt_ms = 160.0 - (18.0 * proximity)
        if context == "visible_passive":
            if distance_bin == "far":
                rt_ms -= 18.0
            elif distance_bin == "middle":
                rt_ms -= 10.0
            else:
                rt_ms -= 4.0
        return _plan(
            f"{context}_{distance_bin}",
            rt_ms,
            synthetic_training_context=context,
            synthetic_wheelchair_path=contrast._wheelchair_path(row),
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    if record_id == "lerner_2021_3d_boundary" and family == "audio_tactile":
        source_type = contrast._lerner_source_type(row)
        direction = contrast._lerner_direction(row)
        proximity = _linear_proximity(row, stats)
        if not source_type or direction is None or not math.isfinite(proximity):
            return None
        distance_bin = _distance_bin(proximity)
        direction_offset = (((direction * 7) % 13) - 6) * 0.55
        favored_source = "dynamic" if direction % 2 == 0 else "flat"
        source_offset = -3.0 if source_type == favored_source else 3.0
        return _plan(
            f"{source_type}_{distance_bin}",
            160.0 - (32.0 * proximity) + direction_offset + source_offset,
            sample_key=f"{source_type}_{direction}_{distance_bin}",
            synthetic_source_type=source_type,
            synthetic_direction=str(direction),
            synthetic_distance_bin=distance_bin,
            synthetic_proximity_rank=f"{proximity:.6f}",
        )

    return None


def _evaluate_record(record: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    record_id = str(record.get("record_id") or "")
    expected_direction = str((record.get("expected_outcome") or {}).get("expected_effect_direction") or "")
    means = contrast._mean_rt_by_condition(rows)
    base = {
        "model_id": MODEL_ID,
        "observed_row_count": len(rows),
        "condition_mean_rt_ms": means,
        "expected_effect_direction": expected_direction,
    }
    if record_id == "smartphone_rt_methods_2025":
        delta = means.get("fixed", math.nan) - means.get("looming", math.nan)
        direction = "looming_faster_than_static" if math.isfinite(delta) and delta > 0.0 else "looming_not_faster_than_static"
        return _comparison(base, direction, expected_direction, math.isfinite(delta) and delta >= 20.0, fixed_minus_looming_ms=delta)
    if record_id == "noel_2015_bodily_self":
        front_delta = means.get("front_asynchronous_far", math.nan) - means.get("front_synchronous_far", math.nan)
        back_delta = means.get("back_synchronous_near", math.nan) - means.get("back_asynchronous_near", math.nan)
        spaces = {str(row.get("synthetic_space") or "") for row in rows}
        syncs = {str(row.get("synthetic_synchrony") or "") for row in rows}
        ok = {"front", "back"}.issubset(spaces) and {"synchronous", "asynchronous"}.issubset(syncs)
        direction = (
            "synchronous_front_expansion_and_back_reduction"
            if ok and math.isfinite(front_delta) and front_delta > 0.0 and math.isfinite(back_delta) and back_delta > 0.0
            else "front_back_synchrony_contrast_not_recovered"
        )
        return _comparison(base, direction, expected_direction, ok and front_delta >= 10.0 and back_delta >= 10.0, front_async_minus_sync_far_ms=front_delta, back_sync_minus_async_near_ms=back_delta)
    if record_id == "serino_2015_peri_trunk_exp1":
        delta = means.get("far", math.nan) - means.get("near", math.nan)
        direction = "near_or_approaching_trunk_sounds_speed_tactile_rt" if math.isfinite(delta) and delta > 0.0 else "near_or_approaching_trunk_sounds_do_not_speed_tactile_rt"
        return _comparison(base, direction, expected_direction, math.isfinite(delta) and delta >= 20.0, far_minus_near_ms=delta)
    if record_id == "serino_2015_peri_hand_exp3":
        looming_delta = means.get("looming_far", math.nan) - means.get("looming_near", math.nan)
        receding_delta = means.get("receding_far", math.nan) - means.get("receding_near", math.nan)
        motions = {str(row.get("synthetic_motion_direction") or "") for row in rows}
        ok = {"looming", "receding"}.issubset(motions)
        direction = (
            "near_hand_sounds_speed_hand_tactile_rt"
            if ok and math.isfinite(looming_delta) and looming_delta > 0.0 and (not math.isfinite(receding_delta) or receding_delta > 0.0)
            else "near_hand_sounds_do_not_speed_hand_tactile_rt"
        )
        return _comparison(base, direction, expected_direction, ok and looming_delta >= 20.0, looming_far_minus_near_ms=looming_delta, receding_far_minus_near_ms=receding_delta)
    if record_id == "serino_2015_front_back_trunk_exp2":
        distance_means = contrast._mean_rt_by_field(rows, "synthetic_distance_bin")
        delta = distance_means.get("far_endpoint", math.nan) - distance_means.get("near_crossing", math.nan)
        paths = {str(row.get("synthetic_front_back_path") or "") for row in rows}
        baseline = any(str(row.get("synthetic_distance_bin") or "") == "baseline" for row in rows)
        ok = {"front_to_back", "back_to_front"}.issubset(paths) and baseline
        direction = "near_trunk_front_back_sounds_speed_corresponding_tactile_rt" if ok and math.isfinite(delta) and delta > 0.0 else "near_trunk_front_back_sound_facilitation_not_recovered"
        return _comparison(base, direction, expected_direction, ok and delta >= 20.0, distance_bin_mean_rt_ms=distance_means, far_endpoint_minus_near_crossing_ms=delta)
    if record_id == "canzoneri_2012_dynamic_sounds":
        approaching_delta = means.get("approaching_far", math.nan) - means.get("approaching_near", math.nan)
        motions = {str(row.get("synthetic_motion_direction") or "") for row in rows}
        ok = {"approaching", "receding"}.issubset(motions)
        direction = "approaching_near_body_sounds_speed_tactile_rt" if ok and math.isfinite(approaching_delta) and approaching_delta > 0.0 else "approaching_near_body_sounds_do_not_speed_tactile_rt"
        return _comparison(base, direction, expected_direction, ok and approaching_delta >= 20.0, approaching_far_minus_near_ms=approaching_delta)
    if record_id == "matsuda_2021_four_directions":
        approaching_delta = means.get("approaching_far", math.nan) - means.get("approaching_near", math.nan)
        receding_delta = means.get("receding_far", math.nan) - means.get("receding_near", math.nan)
        directions = {str(row.get("synthetic_body_direction") or "") for row in rows}
        all_dirs = {"front", "rear", "left", "right"}.issubset(directions)
        direction = (
            "approaching_sounds_show_pps_facilitation_across_four_directions"
            if all_dirs and math.isfinite(approaching_delta) and approaching_delta > 0.0 and (not math.isfinite(receding_delta) or abs(receding_delta) < 8.0)
            else "approaching_sounds_do_not_show_direction_general_pps_facilitation"
        )
        return _comparison(base, direction, expected_direction, all_dirs and approaching_delta >= 20.0, approaching_far_minus_near_ms=approaching_delta, receding_far_minus_near_ms=receding_delta)
    if record_id == "lamia_2026_arm_movement":
        static_delta = means.get("static_approaching_far", math.nan) - means.get("static_approaching_near", math.nan)
        motor_delta = means.get("motor_approaching_far", math.nan) - means.get("motor_approaching_near", math.nan)
        movement_states = {str(row.get("synthetic_movement_state") or "") for row in rows}
        tactile_sites = {str(row.get("synthetic_tactile_site") or "") for row in rows}
        ok = {"motor", "static"}.issubset(movement_states) and {"hand", "trunk"}.issubset(tactile_sites)
        direction = "movement_blunts_looming_distance_facilitation" if ok and math.isfinite(static_delta) and static_delta >= 20.0 and math.isfinite(motor_delta) and abs(motor_delta) < 8.0 else "movement_does_not_blunt_looming_distance_facilitation"
        return _comparison(base, direction, expected_direction, ok, static_approaching_far_minus_near_ms=static_delta, motor_approaching_far_minus_near_ms=motor_delta)
    if record_id == "pfeiffer_2018_vestibular":
        congruent_far = means.get("congruent_rotation_far", math.nan)
        incongruent_far = means.get("incongruent_rotation_far", math.nan)
        no_rotation_far = means.get("no_rotation_far", math.nan)
        control = (incongruent_far + no_rotation_far) / 2.0 if math.isfinite(incongruent_far) and math.isfinite(no_rotation_far) else math.nan
        advantage = control - congruent_far if math.isfinite(control) and math.isfinite(congruent_far) else math.nan
        conditions = {str(row.get("synthetic_pfeiffer_condition") or "") for row in rows}
        ok = {"congruent_rotation", "incongruent_rotation", "no_rotation"}.issubset(conditions)
        direction = "congruent_audio_vestibular_motion_expands_pps" if ok and math.isfinite(advantage) and advantage > 0.0 else "congruent_audio_vestibular_motion_expansion_not_recovered"
        return _comparison(base, direction, expected_direction, ok and advantage >= 15.0, congruent_far_control_minus_congruent_ms=advantage)
    if record_id == "tonelli_2019_echolocation":
        pre_near = means.get("pre_echolocation_near", math.nan)
        post_near = means.get("post_echolocation_near", math.nan)
        pre_middle = means.get("pre_echolocation_middle", math.nan)
        post_middle = means.get("post_echolocation_middle", math.nan)
        pre_baseline = means.get("pre_echolocation_baseline", math.nan)
        post_baseline = means.get("post_echolocation_baseline", math.nan)
        near_gain = pre_near - post_near if math.isfinite(pre_near) and math.isfinite(post_near) else math.nan
        middle_gain = pre_middle - post_middle if math.isfinite(pre_middle) and math.isfinite(post_middle) else math.nan
        baseline_shift = post_baseline - pre_baseline if math.isfinite(pre_baseline) and math.isfinite(post_baseline) else math.nan
        direction = "echolocation_training_changes_lateral_head_pps_boundary" if math.isfinite(near_gain) and near_gain >= 15.0 and math.isfinite(middle_gain) and middle_gain >= 8.0 and (not math.isfinite(baseline_shift) or abs(baseline_shift) <= 8.0) else "echolocation_training_change_not_recovered"
        return _comparison(base, direction, expected_direction, True, near_pre_minus_post_ms=near_gain, middle_pre_minus_post_ms=middle_gain, baseline_post_minus_pre_ms=baseline_shift)
    if record_id == "galli_2015_wheelchair":
        visible_far = means.get("visible_passive_far", math.nan)
        active_far = means.get("active_nonexpert_far", math.nan)
        blind_far = means.get("blindfolded_passive_far", math.nan)
        controls = (active_far + blind_far) / 2.0 if math.isfinite(active_far) and math.isfinite(blind_far) else math.nan
        advantage = controls - visible_far if math.isfinite(controls) and math.isfinite(visible_far) else math.nan
        paths = {str(row.get("synthetic_wheelchair_path") or "") for row in rows}
        ok = {"front", "back"}.issubset(paths)
        direction = "visible_passive_wheelchair_exploration_extends_full_body_pps" if ok and math.isfinite(advantage) and advantage > 0.0 else "visible_passive_wheelchair_extension_not_recovered"
        return _comparison(base, direction, expected_direction, ok and advantage >= 15.0, visible_passive_far_control_minus_visible_ms=advantage)
    if record_id == "lerner_2021_3d_boundary":
        source_means = contrast._mean_rt_by_field(rows, "synthetic_source_type")
        dynamic_minus_flat = source_means.get("dynamic", math.nan) - source_means.get("flat", math.nan)
        directions = {int(str(row.get("synthetic_direction"))) for row in rows if str(row.get("synthetic_direction") or "").isdigit()}
        direction_source_means = {
            direction: contrast._mean_rt_by_field(
                [row for row in rows if str(row.get("synthetic_direction") or "") == str(direction)],
                "synthetic_source_type",
            )
            for direction in directions
        }
        dynamic_closer = sum(1 for item in direction_source_means.values() if item.get("dynamic", math.inf) < item.get("flat", -math.inf))
        flat_closer = sum(1 for item in direction_source_means.values() if item.get("flat", math.inf) < item.get("dynamic", -math.inf))
        balanced = abs(dynamic_closer - flat_closer) <= 1
        ok = {"dynamic", "flat"}.issubset({str(row.get("synthetic_source_type") or "") for row in rows}) and len(directions) >= 12
        direction = "individual_3d_pps_maps_without_systematic_dynamic_flat_advantage" if ok and balanced and math.isfinite(dynamic_minus_flat) and abs(dynamic_minus_flat) <= 5.0 else "systematic_dynamic_flat_3d_boundary_advantage_recovered"
        return _comparison(base, direction, expected_direction, ok and balanced and math.isfinite(dynamic_minus_flat) and abs(dynamic_minus_flat) <= 5.0, source_mean_rt_ms=source_means, dynamic_minus_flat_mean_rt_ms=dynamic_minus_flat, directions_observed=len(directions), dynamic_closer_direction_count=dynamic_closer, flat_closer_direction_count=flat_closer)
    return _comparison(base, "comparison_model_missing", expected_direction, False)


def _comparison(base: dict[str, Any], observed_direction: str, expected_direction: str, criterion_passed: bool, **extra: Any) -> dict[str, Any]:
    return {
        **base,
        **extra,
        "observed_effect_direction": observed_direction,
        "pass": observed_direction == expected_direction and bool(criterion_passed),
    }


def _plan(condition: str, rt_ms: float, **extra: Any) -> dict[str, Any]:
    planned = max(105.0, min(225.0, float(rt_ms)))
    return {
        "synthetic_condition": condition,
        "planned_rt_ms": round(planned, 3),
        "synthetic_model_id": MODEL_ID,
        **extra,
    }


def _linear_proximity(row: dict[str, Any], stats: PlannerStats, *, flip: bool = False) -> float:
    soa_ms = contrast._as_float(row.get("soa_ms"))
    if not math.isfinite(soa_ms) or not math.isfinite(stats.soa_min) or not math.isfinite(stats.soa_max):
        return math.nan
    if stats.soa_max <= stats.soa_min:
        return math.nan
    proximity = (soa_ms - stats.soa_min) / (stats.soa_max - stats.soa_min)
    proximity = max(0.0, min(1.0, proximity))
    return 1.0 - proximity if flip else proximity


def _center_proximity(row: dict[str, Any], stats: PlannerStats) -> float:
    soa_ms = contrast._as_float(row.get("soa_ms"))
    if not math.isfinite(soa_ms) or not math.isfinite(stats.soa_center) or not math.isfinite(stats.max_center_offset):
        return math.nan
    if stats.max_center_offset <= 0.0:
        return math.nan
    proximity = 1.0 - (abs(soa_ms - stats.soa_center) / stats.max_center_offset)
    return max(0.0, min(1.0, proximity))


def _distance_bin(proximity: float) -> str:
    if proximity >= 0.8:
        return "near"
    if proximity <= 0.2:
        return "far"
    return "middle"


def _join_planned_clicks_to_analysis(
    planned_clicks: list[dict[str, Any]],
    analysis_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    hits_by_uid = {
        str(row.get("trial_uid") or ""): row
        for row in analysis_rows
        if str(row.get("hit") or "").strip().lower() in {"true", "1", "yes"}
    }
    observed = []
    for plan in planned_clicks:
        trial_uid = str(plan.get("trial_uid") or "")
        row = hits_by_uid.get(trial_uid)
        if not row:
            continue
        actual_rt = contrast._as_float(row.get("rt_ms"))
        observed.append(
            {
                **plan,
                "actual_rt_ms": f"{actual_rt:.6f}" if math.isfinite(actual_rt) else "",
                "rt_ms": f"{actual_rt:.6f}" if math.isfinite(actual_rt) else "",
                "click_event_id": str(row.get("click_event_id") or ""),
                "hit": str(row.get("hit") or ""),
            }
        )
    return observed


def _summary(record_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "record_count": len(record_results),
        "passed_record_count": sum(1 for result in record_results if result.get("passed")),
        "failed_record_count": sum(1 for result in record_results if not result.get("passed")),
        "template_context_run_count": sum(len(result.get("runs") or []) for result in record_results),
        "planned_click_count": sum(int(result.get("planned_click_count") or 0) for result in record_results),
        "mouse_click_count": sum(int(result.get("mouse_click_count") or 0) for result in record_results),
        "response_marker_start_count": sum(int(result.get("response_marker_start_count") or 0) for result in record_results),
        "observed_analysis_hit_count": sum(int(result.get("observed_analysis_hit_count") or 0) for result in record_results),
    }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    for key, value in list(row.items()):
        normalized[str(key).lower()] = value
    source_label = str(normalized.get("source_block_label") or "").strip()
    block_label = str(normalized.get("block_label") or "").strip()
    if source_label and (not block_label or _is_generic_block_label(block_label)):
        normalized["runner_block_label"] = block_label
        normalized["block_label"] = source_label
    return normalized


def _is_generic_block_label(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("block ") or lowered.startswith("block_")


def _family(row: dict[str, Any]) -> str:
    return str(row.get("family") or row.get("Family") or "").strip().lower()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_csv(path: Path | str) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Ready Profile Mouse-Click Expected-Outcome Audit",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Records: `{report['summary']['passed_record_count']}/{report['summary']['record_count']}`",
        f"- Template/context runs: `{report['summary']['template_context_run_count']}`",
        f"- Mouse clicks: `{report['summary']['mouse_click_count']}`",
        f"- Response markers: `{report['summary']['response_marker_start_count']}`",
        "",
        EVIDENCE_BOUNDARY,
        "",
        "## Records",
        "",
    ]
    for record in report["records"]:
        comparison = record.get("comparison") or {}
        lines.append(
            f"- `{record['record_id']}`: passed=`{record['passed']}`, "
            f"clicks=`{record.get('mouse_click_count')}`, "
            f"observed=`{comparison.get('observed_effect_direction')}`, "
            f"expected=`{comparison.get('expected_effect_direction')}`"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _repo_relative(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ready profiles with participant-like mouse-click outcome simulation.")
    parser.add_argument("--ledger-path", type=Path, default=LEDGER_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--record", action="append", default=[])
    parser.add_argument(
        "--max-samples-per-condition",
        type=int,
        default=0,
        help="Use 0 to click every modeled tactile trial; positive values cap samples per model condition.",
    )
    parser.add_argument("--keep-materialized", action="store_true")
    args = parser.parse_args(argv)

    report = run_audit(
        ledger_path=args.ledger_path,
        output_dir=args.output_dir,
        records=args.record or None,
        max_samples_per_condition=args.max_samples_per_condition,
        keep_materialized=args.keep_materialized,
    )
    print(f"Wrote ready profile mouse-click expected-outcome audit: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
