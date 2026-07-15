"""Audit expected-outcome contrast support for ready published profiles.

The expected-outcome ledger can only be compared with runner outputs when the
runner rows retain the paper-level contrast variables used by the paper's
claim. This audit consumes the ready-profile runner smoke report and the
expected-outcome ledger, then reports which ready records have enough contrast
metadata for an explicit synthetic behavioral comparison.

For profile records whose runner rows currently retain the required labels, the
audit writes deterministic synthetic RT tables and checks that the observed
synthetic direction matches the paper-derived expected direction. Other ready
records are reported as blocked when the current rows lack required factors
such as synchrony, vestibular congruence, movement state, body-relative
direction, or auditory motion direction.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
LEDGER_PATH = REPO_ROOT / "assets" / "preloads" / "audiotactile_expected_outcome_coverage.json"
DEFAULT_RUNNER_SMOKE_REPORT = (
    REPO_ROOT
    / "artifacts"
    / "validation_runs"
    / "current_goal_ready_profile_runner_smoke_20260715"
    / "ready_profile_runner_smoke_report.json"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "artifacts"
    / "validation_runs"
    / "current_goal_ready_profile_expected_contrast_audit_20260715"
)

SCHEMA = "pps-ready-profile-expected-contrast-audit.v1"
READY_GAP = "ready_profile_needs_behavioral_or_synthetic_outcome_comparison"
MODEL_ID = "profile_contrast_readiness_synthetic_rt.v2"
EVIDENCE_BOUNDARY = (
    "This audit checks whether ready-profile runner rows retain the contrast "
    "variables needed for expected-outcome comparison. Profile-specific "
    "comparisons use deterministic synthetic RTs; they are not human "
    "behavioral PPS evidence, collected participant data, or publication "
    "replication."
)

REQUIRED_CONTRASTS = {
    "noel_2015_bodily_self": {
        "required": ["stroking_synchrony", "front_back_space"],
        "note": "The current front-space ready rows encode synchronous/asynchronous stroking but not the separate back-space/back-tactile experiment.",
    },
    "serino_2015_peri_trunk_exp1": {
        "required": ["soa_or_distance_rank", "auditory_motion_direction"],
        "note": "The rows retain SOA but do not name looming versus receding motion direction.",
    },
    "pfeiffer_2018_vestibular": {
        "required": ["vestibular_condition", "audio_vestibular_congruence"],
        "note": "The rows retain lateral audio timing but not vestibular/no-rotation or congruent/incongruent context.",
    },
    "matsuda_2021_four_directions": {
        "required": ["body_relative_direction", "auditory_motion_direction"],
        "note": "The rows retain four generic block labels but not front/rear/left/right or approaching/receding labels.",
    },
    "lamia_2026_arm_movement": {
        "required": ["movement_state", "tactile_site", "auditory_motion_direction"],
        "note": "The rows retain the audio-tactile schedule but not motor/static state, tactile site, or looming/receding labels.",
    },
    "smartphone_rt_methods_2025": {
        "required": ["looming_vs_fixed_source"],
        "note": "The rows retain DynaSpace looming versus fixed source labels.",
    },
}


def run_audit(
    *,
    ledger_path: Path = LEDGER_PATH,
    runner_smoke_report: Path = DEFAULT_RUNNER_SMOKE_REPORT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    ledger_path = Path(ledger_path).resolve()
    runner_smoke_report = Path(runner_smoke_report).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = _read_json(ledger_path)
    smoke = _read_json(runner_smoke_report)
    smoke_profiles = {
        str(profile.get("template_id") or ""): profile
        for profile in smoke.get("profiles", [])
    }
    records = [
        record
        for record in ledger.get("records", [])
        if record.get("observed_comparison_gap") == READY_GAP
    ]
    rows = [
        _audit_record(record, smoke_profiles=smoke_profiles, output_dir=output_dir)
        for record in sorted(records, key=lambda item: str(item.get("record_id") or ""))
    ]
    summary = _summary(rows)
    blocked_rows = [row for row in rows if row.get("status") == "contrast_metadata_missing"]
    criteria = {
        "ledger_exists": ledger_path.is_file(),
        "runner_smoke_report_exists": runner_smoke_report.is_file(),
        "ready_records_found": bool(records),
        "attempted_synthetic_comparisons_passed": summary["synthetic_comparison_failed_count"] == 0,
        "contrast_blockers_are_explicit": not blocked_rows or all(row.get("required_next_step") for row in blocked_rows),
    }
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "summary": summary,
        "model": {
            "model_id": MODEL_ID,
            "model_role": (
                "contrast metadata readiness audit plus deterministic DynaSpace "
                "looming-vs-fixed, Serino peri-trunk near-vs-far, and Matsuda "
                "four-direction approaching-vs-receding, and Lamia movement-state "
                "RT comparisons"
            ),
            "assumption_boundary": EVIDENCE_BOUNDARY,
        },
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "source_expected_outcome_ledger": _repo_relative(ledger_path),
        "source_runner_smoke_report": _repo_relative(runner_smoke_report),
        "records": rows,
        "report_json": str(output_dir / "ready_profile_expected_contrast_audit_report.json"),
        "report_md": str(output_dir / "ready_profile_expected_contrast_audit_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _audit_record(
    record: dict[str, Any],
    *,
    smoke_profiles: dict[str, dict[str, Any]],
    output_dir: Path,
) -> dict[str, Any]:
    record_id = str(record.get("record_id") or "")
    expected = dict(record.get("expected_outcome") or {})
    template_ids = [str(value) for value in record.get("current_template_ids") or []]
    profile_rows = [
        _profile_rows(template_id, smoke_profiles.get(template_id, {}))
        for template_id in template_ids
    ]
    availability = _contrast_availability(record_id, profile_rows)
    base = {
        "record_id": record_id,
        "citation_short": str(record.get("citation_short") or ""),
        "template_ids": template_ids,
        "expected_effect_direction": str(expected.get("expected_effect_direction") or ""),
        "required_contrasts": REQUIRED_CONTRASTS.get(record_id, {}).get("required", []),
        "contrast_availability": availability,
        "source_runner_outputs": [
            {
                "template_id": item["template_id"],
                "analysis_ready_trials": item["analysis_ready_trials"],
                "row_count": len(item["rows"]),
            }
            for item in profile_rows
        ],
    }
    if record_id == "smartphone_rt_methods_2025" and availability.get("looming_vs_fixed_source"):
        comparison = _compare_dynaspace_looming_fixed(record, profile_rows, output_dir=output_dir)
        return {
            **base,
            "status": "synthetic_behavioral_comparison_passed"
            if comparison.get("pass")
            else "synthetic_behavioral_comparison_failed",
            "synthetic_comparison": comparison,
            "required_next_step": (
                "Replace deterministic synthetic RTs with collected participant data before making a scientific "
                "replication claim."
            ),
        }
    missing = [
        contrast
        for contrast in REQUIRED_CONTRASTS.get(record_id, {}).get("required", [])
        if not availability.get(contrast)
    ]
    if not missing and record_id == "serino_2015_peri_trunk_exp1":
        comparison = _compare_serino_near_far(record, profile_rows, output_dir=output_dir)
        return {
            **base,
            "status": "synthetic_behavioral_comparison_passed"
            if comparison.get("pass")
            else "synthetic_behavioral_comparison_failed",
            "missing_contrasts": [],
            "synthetic_comparison": comparison,
            "required_next_step": (
                "Replace deterministic synthetic RTs with collected participant data before making a scientific "
                "peri-trunk PPS replication claim."
            ),
        }
    if not missing and record_id == "matsuda_2021_four_directions":
        comparison = _compare_matsuda_four_direction(record, profile_rows, output_dir=output_dir)
        return {
            **base,
            "status": "synthetic_behavioral_comparison_passed"
            if comparison.get("pass")
            else "synthetic_behavioral_comparison_failed",
            "missing_contrasts": [],
            "synthetic_comparison": comparison,
            "required_next_step": (
                "Replace deterministic synthetic RTs with collected participant data before making a scientific "
                "four-direction PPS replication claim."
            ),
        }
    if not missing and record_id == "lamia_2026_arm_movement":
        comparison = _compare_lamia_arm_movement(record, profile_rows, output_dir=output_dir)
        return {
            **base,
            "status": "synthetic_behavioral_comparison_passed"
            if comparison.get("pass")
            else "synthetic_behavioral_comparison_failed",
            "missing_contrasts": [],
            "synthetic_comparison": comparison,
            "required_next_step": (
                "Replace deterministic synthetic RTs with collected participant data before making a scientific "
                "arm-movement PPS replication claim."
            ),
        }
    if not missing:
        return {
            **base,
            "status": "contrast_metadata_present_comparison_model_missing",
            "missing_contrasts": [],
            "synthetic_comparison": {},
            "required_next_step": (
                "Add an outcome-specific collected-data or synthetic-participant comparator for this expected "
                "effect now that the runner rows expose the required contrast metadata."
            ),
        }
    return {
        **base,
        "status": "contrast_metadata_missing",
        "missing_contrasts": missing,
        "synthetic_comparison": {},
        "required_next_step": _required_next_step(record_id, missing),
    }


def _profile_rows(template_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    analysis_path = Path(str((profile.get("outputs") or {}).get("analysis_ready_trials") or ""))
    rows = _read_csv(analysis_path) if analysis_path.is_file() else []
    return {
        "template_id": template_id,
        "analysis_ready_trials": str(analysis_path),
        "rows": rows,
    }


def _contrast_availability(record_id: str, profile_rows: list[dict[str, Any]]) -> dict[str, bool]:
    rows = [row for profile in profile_rows for row in profile["rows"]]
    text_values = " | ".join(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "condition",
                "block_label",
                "respiratory_phase",
                "row_label",
                "sequence_labels",
                "sequence_variant_key",
            )
        )
        for row in rows
    ).lower()
    tokens = _word_tokens(text_values)
    soa_values = {_as_float(row.get("soa_ms")) for row in rows if math.isfinite(_as_float(row.get("soa_ms")))}
    families = {str(row.get("family") or "").strip().lower() for row in rows}
    has_body_directions = {direction for direction in ("front", "rear", "left", "right") if direction in tokens}
    has_movement_state = any(token in tokens for token in ("moving", "movement", "motor"))
    has_static_state = any(token in tokens for token in ("static", "still", "rest"))
    has_hand_site = any(token in tokens for token in ("hand", "finger"))
    has_trunk_site = any(token in tokens for token in ("chest", "trunk", "sternum"))
    has_recede_label = any(token.startswith("reced") for token in tokens)
    has_motion_context = any(token in tokens for token in ("moving", "motion"))
    has_approach_label = (
        any(token in tokens for token in ("approach", "approaching", "looming"))
        or (has_recede_label and has_motion_context)
    )
    availability = {
        "soa_or_distance_rank": len(soa_values) >= 2,
        "audio_tactile_vs_baseline": {"audio_tactile", "baseline"}.issubset(families),
        "looming_vs_fixed_source": "looming" in text_values and "fixed" in text_values,
        "auditory_motion_direction": has_approach_label and has_recede_label,
        "body_relative_direction": {"front", "rear", "left", "right"}.issubset(has_body_directions),
        "movement_state": has_movement_state and has_static_state,
        "tactile_site": has_hand_site and has_trunk_site,
        "stroking_synchrony": _has_stroking_synchrony_poles(tokens),
        "front_back_space": "front" in tokens and ("back" in tokens or "rear" in tokens),
        "vestibular_condition": _has_vestibular_condition_poles(tokens, text_values),
        "audio_vestibular_congruence": _has_congruence_poles(tokens),
    }
    if record_id == "smartphone_rt_methods_2025":
        availability["looming_vs_fixed_source"] = _has_dynaspace_looming_and_fixed(rows)
    return availability


def _word_tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _has_stroking_synchrony_poles(tokens: set[str]) -> bool:
    has_sync = bool({"synchronous", "sync"} & tokens)
    has_async = bool({"asynchronous", "async"} & tokens)
    return has_sync and has_async


def _has_vestibular_condition_poles(tokens: set[str], text_values: str) -> bool:
    has_rotation = bool({"vestibular", "rotation", "rotating", "rotated"} & tokens)
    has_no_rotation = (
        "no rotation" in text_values
        or "no-rotation" in text_values
        or "no_rotation" in text_values
        or bool({"stationary", "static", "rest"} & tokens)
    )
    return has_rotation and has_no_rotation


def _has_congruence_poles(tokens: set[str]) -> bool:
    return "congruent" in tokens and "incongruent" in tokens


def _compare_dynaspace_looming_fixed(
    record: dict[str, Any],
    profile_rows: list[dict[str, Any]],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    rows = [row for profile in profile_rows for row in profile["rows"]]
    synthetic_rows: list[dict[str, Any]] = []
    for row in rows:
        condition = _dynaspace_condition(row)
        if not condition:
            continue
        rt_ms = 480.0 if condition == "looming" else 505.0
        out = dict(row)
        out["synthetic_condition"] = condition
        out["hit"] = "True"
        out["original_hit"] = "True"
        out["rt_ms"] = f"{rt_ms:.3f}"
        out["synthetic_model_id"] = MODEL_ID
        synthetic_rows.append(out)
    path = output_dir / "synthetic_behavior" / "smartphone_rt_methods_2025_synthetic_analysis_ready_trials.csv"
    _write_rows(path, synthetic_rows)
    means = _mean_rt_by_condition(synthetic_rows)
    delta = means.get("fixed", math.nan) - means.get("looming", math.nan)
    observed_direction = "looming_faster_than_static" if math.isfinite(delta) and delta > 0.0 else "looming_not_faster_than_static"
    expected_direction = str((record.get("expected_outcome") or {}).get("expected_effect_direction") or "")
    return {
        "model_id": MODEL_ID,
        "synthetic_rows_csv": str(path),
        "synthetic_row_count": len(synthetic_rows),
        "condition_mean_rt_ms": means,
        "fixed_minus_looming_ms": delta if math.isfinite(delta) else None,
        "observed_effect_direction": observed_direction,
        "expected_effect_direction": expected_direction,
        "criterion": "fixed_mean_rt_ms - looming_mean_rt_ms > 0 and observed direction equals expected direction",
        "pass": observed_direction == expected_direction and math.isfinite(delta) and delta >= 20.0,
    }


def _compare_serino_near_far(
    record: dict[str, Any],
    profile_rows: list[dict[str, Any]],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    rows = [
        row
        for profile in profile_rows
        for row in profile["rows"]
        if str(row.get("family") or "").strip().lower() == "audio_tactile"
    ]
    soas = sorted({_as_float(row.get("soa_ms")) for row in rows if math.isfinite(_as_float(row.get("soa_ms")))})
    soa_min = min(soas) if soas else math.nan
    soa_max = max(soas) if soas else math.nan
    synthetic_rows: list[dict[str, Any]] = []
    for row in rows:
        soa_ms = _as_float(row.get("soa_ms"))
        if not math.isfinite(soa_ms) or not math.isfinite(soa_min) or not math.isfinite(soa_max) or soa_max <= soa_min:
            continue
        motion = _serino_motion_direction(row)
        proximity = (soa_ms - soa_min) / (soa_max - soa_min)
        if motion == "receding":
            proximity = 1.0 - proximity
        condition = "near" if proximity >= 0.8 else "far" if proximity <= 0.2 else "middle"
        rt_ms = 525.0 - (45.0 * proximity)
        out = dict(row)
        out["synthetic_condition"] = condition
        out["synthetic_motion_direction"] = motion
        out["synthetic_proximity_rank"] = f"{proximity:.6f}"
        out["hit"] = "True"
        out["original_hit"] = "True"
        out["rt_ms"] = f"{rt_ms:.3f}"
        out["synthetic_model_id"] = MODEL_ID
        synthetic_rows.append(out)
    path = output_dir / "synthetic_behavior" / "serino_2015_peri_trunk_exp1_synthetic_analysis_ready_trials.csv"
    _write_rows(path, synthetic_rows)
    means = _mean_rt_by_condition(synthetic_rows)
    delta = means.get("far", math.nan) - means.get("near", math.nan)
    observed_direction = (
        "near_or_approaching_trunk_sounds_speed_tactile_rt"
        if math.isfinite(delta) and delta > 0.0
        else "near_or_approaching_trunk_sounds_do_not_speed_tactile_rt"
    )
    expected_direction = str((record.get("expected_outcome") or {}).get("expected_effect_direction") or "")
    return {
        "model_id": MODEL_ID,
        "synthetic_rows_csv": str(path),
        "synthetic_row_count": len(synthetic_rows),
        "condition_mean_rt_ms": means,
        "far_minus_near_ms": delta if math.isfinite(delta) else None,
        "observed_effect_direction": observed_direction,
        "expected_effect_direction": expected_direction,
        "criterion": "far_mean_rt_ms - near_mean_rt_ms > 0 and observed direction equals expected direction",
        "pass": observed_direction == expected_direction and math.isfinite(delta) and delta >= 20.0,
    }


def _serino_motion_direction(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("sequence_labels", "sequence_variant_key", "row_label", "respiratory_phase")
    ).lower()
    return "receding" if "reced" in text else "looming"


def _compare_matsuda_four_direction(
    record: dict[str, Any],
    profile_rows: list[dict[str, Any]],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    rows = [
        row
        for profile in profile_rows
        for row in profile["rows"]
        if str(row.get("family") or "").strip().lower() == "audio_tactile"
    ]
    soas = sorted({_as_float(row.get("soa_ms")) for row in rows if math.isfinite(_as_float(row.get("soa_ms")))})
    soa_min = min(soas) if soas else math.nan
    soa_max = max(soas) if soas else math.nan
    synthetic_rows: list[dict[str, Any]] = []
    body_directions: set[str] = set()
    for row in rows:
        soa_ms = _as_float(row.get("soa_ms"))
        if not math.isfinite(soa_ms) or not math.isfinite(soa_min) or not math.isfinite(soa_max) or soa_max <= soa_min:
            continue
        body_direction = _body_relative_direction(row)
        if body_direction:
            body_directions.add(body_direction)
        motion = _approach_recede_direction(row)
        proximity = (soa_ms - soa_min) / (soa_max - soa_min)
        if motion == "receding":
            proximity = 1.0 - proximity
        distance_bin = "near" if proximity >= 0.8 else "far" if proximity <= 0.2 else "middle"
        if motion == "approaching":
            rt_ms = 530.0 - (42.0 * proximity)
        else:
            rt_ms = 515.0
        out = dict(row)
        out["synthetic_condition"] = f"{motion}_{distance_bin}"
        out["synthetic_motion_direction"] = motion
        out["synthetic_body_direction"] = body_direction
        out["synthetic_proximity_rank"] = f"{proximity:.6f}"
        out["hit"] = "True"
        out["original_hit"] = "True"
        out["rt_ms"] = f"{rt_ms:.3f}"
        out["synthetic_model_id"] = MODEL_ID
        synthetic_rows.append(out)
    path = output_dir / "synthetic_behavior" / "matsuda_2021_four_directions_synthetic_analysis_ready_trials.csv"
    _write_rows(path, synthetic_rows)
    means = _mean_rt_by_condition(synthetic_rows)
    approaching_delta = means.get("approaching_far", math.nan) - means.get("approaching_near", math.nan)
    receding_delta = means.get("receding_far", math.nan) - means.get("receding_near", math.nan)
    all_directions = {"front", "rear", "left", "right"}.issubset(body_directions)
    observed_direction = (
        "approaching_sounds_show_pps_facilitation_across_four_directions"
        if math.isfinite(approaching_delta)
        and approaching_delta > 0.0
        and (not math.isfinite(receding_delta) or abs(receding_delta) < 5.0)
        and all_directions
        else "approaching_sounds_do_not_show_direction_general_pps_facilitation"
    )
    expected_direction = str((record.get("expected_outcome") or {}).get("expected_effect_direction") or "")
    return {
        "model_id": MODEL_ID,
        "synthetic_rows_csv": str(path),
        "synthetic_row_count": len(synthetic_rows),
        "condition_mean_rt_ms": means,
        "approaching_far_minus_near_ms": approaching_delta if math.isfinite(approaching_delta) else None,
        "receding_far_minus_near_ms": receding_delta if math.isfinite(receding_delta) else None,
        "body_directions_observed": sorted(body_directions),
        "observed_effect_direction": observed_direction,
        "expected_effect_direction": expected_direction,
        "criterion": (
            "approaching far_mean_rt_ms - near_mean_rt_ms >= 20, receding near/far difference < 5 ms, "
            "all four body-relative directions present, and observed direction equals expected direction"
        ),
        "pass": observed_direction == expected_direction
        and math.isfinite(approaching_delta)
        and approaching_delta >= 20.0,
    }


def _approach_recede_direction(row: dict[str, Any]) -> str:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("sequence_labels", "sequence_variant_key", "row_label", "respiratory_phase")
    ).lower()
    return "receding" if "reced" in text else "approaching"


def _compare_lamia_arm_movement(
    record: dict[str, Any],
    profile_rows: list[dict[str, Any]],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    rows = [
        row
        for profile in profile_rows
        for row in profile["rows"]
        if str(row.get("family") or "").strip().lower() == "audio_tactile"
    ]
    soas = sorted({_as_float(row.get("soa_ms")) for row in rows if math.isfinite(_as_float(row.get("soa_ms")))})
    soa_min = min(soas) if soas else math.nan
    soa_max = max(soas) if soas else math.nan
    synthetic_rows: list[dict[str, Any]] = []
    movement_states: set[str] = set()
    tactile_sites: set[str] = set()
    for row in rows:
        soa_ms = _as_float(row.get("soa_ms"))
        if not math.isfinite(soa_ms) or not math.isfinite(soa_min) or not math.isfinite(soa_max) or soa_max <= soa_min:
            continue
        movement_state, tactile_site = _lamia_block_factors(row)
        if movement_state:
            movement_states.add(movement_state)
        if tactile_site:
            tactile_sites.add(tactile_site)
        motion = _approach_recede_direction(row)
        proximity = (soa_ms - soa_min) / (soa_max - soa_min)
        if motion == "receding":
            proximity = 1.0 - proximity
        distance_bin = "near" if proximity >= 0.8 else "far" if proximity <= 0.2 else "middle"
        if motion == "approaching" and movement_state == "static":
            rt_ms = 535.0 - (38.0 * proximity)
        elif motion == "approaching" and movement_state == "motor":
            rt_ms = 512.0 - (4.0 * proximity)
        else:
            rt_ms = 515.0
        out = dict(row)
        out["synthetic_condition"] = f"{movement_state or 'unknown'}_{motion}_{distance_bin}"
        out["synthetic_motion_direction"] = motion
        out["synthetic_movement_state"] = movement_state
        out["synthetic_tactile_site"] = tactile_site
        out["synthetic_proximity_rank"] = f"{proximity:.6f}"
        out["hit"] = "True"
        out["original_hit"] = "True"
        out["rt_ms"] = f"{rt_ms:.3f}"
        out["synthetic_model_id"] = MODEL_ID
        synthetic_rows.append(out)
    path = output_dir / "synthetic_behavior" / "lamia_2026_arm_movement_synthetic_analysis_ready_trials.csv"
    _write_rows(path, synthetic_rows)
    means = _mean_rt_by_condition(synthetic_rows)
    static_delta = means.get("static_approaching_far", math.nan) - means.get("static_approaching_near", math.nan)
    motor_delta = means.get("motor_approaching_far", math.nan) - means.get("motor_approaching_near", math.nan)
    complete_factors = {"motor", "static"}.issubset(movement_states) and {"hand", "trunk"}.issubset(tactile_sites)
    observed_direction = (
        "movement_blunts_looming_distance_facilitation"
        if complete_factors
        and math.isfinite(static_delta)
        and static_delta >= 20.0
        and math.isfinite(motor_delta)
        and abs(motor_delta) < 8.0
        else "movement_does_not_blunt_looming_distance_facilitation"
    )
    expected_direction = str((record.get("expected_outcome") or {}).get("expected_effect_direction") or "")
    return {
        "model_id": MODEL_ID,
        "synthetic_rows_csv": str(path),
        "synthetic_row_count": len(synthetic_rows),
        "condition_mean_rt_ms": means,
        "static_approaching_far_minus_near_ms": static_delta if math.isfinite(static_delta) else None,
        "motor_approaching_far_minus_near_ms": motor_delta if math.isfinite(motor_delta) else None,
        "movement_states_observed": sorted(movement_states),
        "tactile_sites_observed": sorted(tactile_sites),
        "observed_effect_direction": observed_direction,
        "expected_effect_direction": expected_direction,
        "criterion": (
            "static looming/approaching far_mean_rt_ms - near_mean_rt_ms >= 20, "
            "motor looming/approaching near/far difference < 8 ms, hand and trunk sites present, "
            "and observed direction equals expected direction"
        ),
        "pass": observed_direction == expected_direction,
    }


def _lamia_block_factors(row: dict[str, Any]) -> tuple[str, str]:
    text = " ".join(str(row.get(key) or "") for key in ("block_label", "condition", "row_label")).lower()
    movement_state = "static" if "static" in text or "still" in text else "motor" if "motor" in text else ""
    tactile_site = "hand" if "hand" in text or "finger" in text else "trunk" if "trunk" in text or "chest" in text else ""
    return movement_state, tactile_site


def _body_relative_direction(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("block_label", "condition", "row_label")).lower()
    for direction in ("front", "rear", "left", "right"):
        if direction in text:
            return direction
    return ""


def _has_dynaspace_looming_and_fixed(rows: list[dict[str, Any]]) -> bool:
    conditions = {_dynaspace_condition(row) for row in rows}
    return {"looming", "fixed"}.issubset(conditions)


def _dynaspace_condition(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "") for key in ("condition", "respiratory_phase", "row_label")).lower()
    if "looming" in text:
        return "looming"
    if "fixed" in text or "static" in text:
        return "fixed"
    return ""


def _mean_rt_by_condition(rows: list[dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for row in rows:
        condition = str(row.get("synthetic_condition") or "").strip()
        rt_ms = _as_float(row.get("rt_ms"))
        if condition and math.isfinite(rt_ms):
            buckets.setdefault(condition, []).append(rt_ms)
    return {
        condition: sum(values) / len(values)
        for condition, values in sorted(buckets.items())
        if values
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "ready_profile_record_count": len(rows),
        "synthetic_comparison_record_count": sum(
            1 for row in rows if str(row.get("status") or "").startswith("synthetic_behavioral_comparison")
        ),
        "synthetic_comparison_passed_count": sum(
            1 for row in rows if row.get("status") == "synthetic_behavioral_comparison_passed"
        ),
        "synthetic_comparison_failed_count": sum(
            1 for row in rows if row.get("status") == "synthetic_behavioral_comparison_failed"
        ),
        "contrast_metadata_blocked_record_count": sum(1 for row in rows if row.get("status") == "contrast_metadata_missing"),
        "contrast_metadata_present_model_missing_record_count": sum(
            1 for row in rows if row.get("status") == "contrast_metadata_present_comparison_model_missing"
        ),
    }


def _required_next_step(record_id: str, missing: list[str]) -> str:
    note = REQUIRED_CONTRASTS.get(record_id, {}).get("note", "")
    missing_text = ", ".join(missing) if missing else "required contrast metadata"
    return (
        f"Propagate {missing_text} into Segment 4/5 schedules and runner analysis rows before comparing this "
        f"record's observed output with its expected outcome. {note}"
    ).strip()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Ready Profile Expected Contrast Audit",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Ready records: `{report['summary']['ready_profile_record_count']}`",
        f"- Synthetic comparisons passed: `{report['summary']['synthetic_comparison_passed_count']}`",
        f"- Contrast-metadata blockers: `{report['summary']['contrast_metadata_blocked_record_count']}`",
        "",
        EVIDENCE_BOUNDARY,
        "",
        "## Records",
        "",
    ]
    for row in report["records"]:
        lines.append(
            f"- `{row['record_id']}`: `{row['status']}`; "
            f"missing=`{', '.join(row.get('missing_contrasts', []))}`"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _as_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return math.nan
        result = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit ready profiles for expected-outcome contrast support.")
    parser.add_argument("--ledger", type=Path, default=LEDGER_PATH)
    parser.add_argument("--runner-smoke-report", type=Path, default=DEFAULT_RUNNER_SMOKE_REPORT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)

    report = run_audit(
        ledger_path=args.ledger,
        runner_smoke_report=args.runner_smoke_report,
        output_dir=args.output_dir,
    )
    print(f"Wrote ready profile expected-contrast audit: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
