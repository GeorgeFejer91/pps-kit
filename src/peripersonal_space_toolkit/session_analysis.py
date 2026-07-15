"""Immediate session analysis for PPS runner event logs."""

from __future__ import annotations

import csv
import json
import math
import os
import re
import statistics
import sys
import warnings as py_warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit
from scipy import stats as scipy_stats

from .response_policy import TACTILE_RESPONSE_MAX_RT_S, TACTILE_RESPONSE_MIN_RT_S

DEFAULT_MIN_RESPONSE_RT_S = TACTILE_RESPONSE_MIN_RT_S
DEFAULT_MAX_RESPONSE_RT_S = TACTILE_RESPONSE_MAX_RT_S
AGGREGATION_SEPARATE_PARTS = "separate_parts"
AGGREGATION_POOL_PARTS = "pooled_parts"
DATA_BEHAVIOR_SCHEMA = "pps-exploratory-data-behavior.v1"
CONDITION_LENS_SCHEMA = "pps-condition-lens-triage.v1"
RECORDING_QUALITY_GATE_SCHEMA = "pps-recording-quality-gate.v1"
BASIC_ASSUMPTION_CHECKS_SCHEMA = "pps-basic-assumption-checks.v1"
CONDITION_LENS_TWO_BY_TWO = "two_by_two"
CONDITION_LENS_PART = "part"
CONDITION_LENS_STATE = "state"
CONDITION_LENS_OVERALL = "overall"
CONDITION_LENS_ORDER = (CONDITION_LENS_TWO_BY_TWO, CONDITION_LENS_PART, CONDITION_LENS_STATE, CONDITION_LENS_OVERALL)
MODEL_EVIDENCE_STRONG = "strong"
MODEL_EVIDENCE_MIXED = "mixed"
MODEL_EVIDENCE_INSUFFICIENT = "insufficient"
QUALITY_PASS = "PASS"
QUALITY_FAIL = "FAIL"
BASELINE_CORRECTION_METHOD_CONDITION_MEAN_POOLED_SOA = "condition_mean_pooled_soa"

SIGNAL_EXPECTED = "Expected pattern"
SIGNAL_MIXED = "Mixed / ambiguous"
SIGNAL_UNUSUAL = "Unusual pattern"
SIGNAL_INSUFFICIENT = "Insufficient evidence"
SIGNAL_TECHNICAL = "Technical caveat"

COMMON_PPS_VISUALIZATION_FEATURES = [
    "RT or facilitation by SOA/distance",
    "Near/far or distance-bin separation",
    "Condition/group summaries",
    "PPS boundary or size-index estimates",
    "Sigmoid, linear, and logarithmic-decay model fits",
    "Uncertainty/range around means",
    "Model parameter or fit tables",
]


def _filesystem_path(path: str | Path) -> str:
    resolved = Path(path).resolve()
    text = str(resolved)
    if sys.platform == "win32" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _mkdir(path: str | Path) -> None:
    os.makedirs(_filesystem_path(path), exist_ok=True)


@dataclass
class SessionAnalysisResult:
    response_rows: list[dict[str, Any]] = field(default_factory=list)
    final_outcome_rows: list[dict[str, Any]] = field(default_factory=list)
    summary_rows: list[dict[str, Any]] = field(default_factory=list)
    curve_rows: list[dict[str, Any]] = field(default_factory=list)
    fit_rows: list[dict[str, Any]] = field(default_factory=list)
    model_fit_rows: list[dict[str, Any]] = field(default_factory=list)
    model_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_curve_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_model_fit_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_model_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_triage_summary: dict[str, Any] = field(default_factory=dict)
    recording_quality_gate: dict[str, Any] = field(default_factory=dict)
    basic_assumption_checks: dict[str, Any] = field(default_factory=dict)
    data_behavior_rows: list[dict[str, Any]] = field(default_factory=list)
    exploratory_quality_summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def analyze_session_events(
    events: Iterable[Any],
    *,
    min_rt_s: float = DEFAULT_MIN_RESPONSE_RT_S,
    max_rt_s: float = DEFAULT_MAX_RESPONSE_RT_S,
) -> SessionAnalysisResult:
    rows = sorted((_as_row(event) for event in events), key=lambda row: (_as_float(row.get("unix_time"), 0.0), row.get("event_id", 0)))
    result = _analyze_response_rows(
        _pair_tactile_responses(rows, min_rt_s=min_rt_s, max_rt_s=max_rt_s),
        event_rows=rows,
        rows_are_final=False,
    )
    if not result.response_rows:
        result.warnings.append("No tactile response rows could be reconstructed from the event stream.")
    return result


def analyze_analysis_ready_trials(
    rows: Iterable[Mapping[str, Any]],
    *,
    event_rows: Iterable[Mapping[str, Any]] | None = None,
    recording_quality_gate: dict[str, Any] | None = None,
) -> SessionAnalysisResult:
    """Analyze saved analysis-ready trial rows without reconstructing raw events."""

    trial_rows = [_coerce_analysis_ready_row(dict(row)) for row in rows]
    result = _analyze_response_rows(
        trial_rows,
        event_rows=[dict(row) for row in event_rows or []],
        rows_are_final=True,
    )
    if recording_quality_gate is not None:
        result.recording_quality_gate = dict(recording_quality_gate)
    if not result.response_rows:
        result.warnings.append("No analysis-ready trial rows were available.")
    return result


def _analyze_response_rows(
    response_rows: list[dict[str, Any]],
    *,
    event_rows: list[dict[str, Any]],
    rows_are_final: bool,
) -> SessionAnalysisResult:
    result = SessionAnalysisResult()
    result.response_rows = response_rows
    result.final_outcome_rows = list(response_rows) if rows_are_final else _build_final_outcomes(result.response_rows)
    analysis_rows = result.final_outcome_rows or result.response_rows
    result.summary_rows = _summarize_responses(analysis_rows)
    result.curve_rows, result.fit_rows, result.model_fit_rows, result.model_comparison_rows, curve_warnings = _build_pps_curves(analysis_rows)
    result.warnings.extend(curve_warnings)
    (
        result.condition_lens_curve_rows,
        result.condition_lens_model_fit_rows,
        result.condition_lens_model_comparison_rows,
        result.condition_lens_triage_summary,
    ) = _build_condition_lens_outputs(analysis_rows)
    result.recording_quality_gate = _build_recording_quality_gate(result, event_rows)
    result.basic_assumption_checks = _build_basic_assumption_checks(analysis_rows)
    result.data_behavior_rows, result.exploratory_quality_summary = _build_data_behavior_review(result, event_rows)
    return result


def write_analysis_csvs(result: SessionAnalysisResult, output_dir: str | Path, stem: str) -> dict[str, Path]:
    output_dir = Path(output_dir)
    _mkdir(output_dir)
    outputs = {
        "responses": output_dir / f"{stem}_responses.csv",
        "analysis_ready_trials": output_dir / f"{stem}_analysis_ready_trials.csv",
        "final_trial_outcomes": output_dir / f"{stem}_final_trial_outcomes.csv",
        "summary": output_dir / f"{stem}_summary.csv",
        "curves": output_dir / f"{stem}_pps_curve_points.csv",
        "fits": output_dir / f"{stem}_sigmoid_fits.csv",
        "model_fits": output_dir / f"{stem}_model_fits.csv",
        "model_fit_comparison": output_dir / f"{stem}_model_fit_comparison.csv",
        "condition_lens_curves": output_dir / f"{stem}_condition_lens_curve_points.csv",
        "condition_lens_model_fits": output_dir / f"{stem}_condition_lens_model_fits.csv",
        "condition_lens_model_fit_comparison": output_dir / f"{stem}_condition_lens_model_fit_comparison.csv",
        "condition_lens_triage_summary": output_dir / "condition_lens_triage_summary.json",
        "recording_quality_gate": output_dir / "recording_quality_gate.v1.json",
        "basic_assumption_checks": output_dir / "basic_assumption_checks.v1.json",
        "data_behavior_by_scope": output_dir / "data_behavior_by_scope.csv",
        "exploratory_quality_summary": output_dir / "exploratory_quality_summary.json",
    }
    _write_rows(outputs["responses"], result.response_rows)
    _write_rows(outputs["analysis_ready_trials"], result.final_outcome_rows or result.response_rows)
    _write_rows(outputs["final_trial_outcomes"], result.final_outcome_rows)
    _write_rows(outputs["summary"], result.summary_rows)
    _write_rows(outputs["curves"], result.curve_rows)
    _write_rows(outputs["fits"], result.fit_rows)
    _write_rows(outputs["model_fits"], result.model_fit_rows)
    _write_rows(outputs["model_fit_comparison"], result.model_comparison_rows)
    _write_rows(outputs["condition_lens_curves"], result.condition_lens_curve_rows)
    _write_rows(outputs["condition_lens_model_fits"], result.condition_lens_model_fit_rows)
    _write_rows(outputs["condition_lens_model_fit_comparison"], result.condition_lens_model_comparison_rows)
    _write_json(outputs["condition_lens_triage_summary"], result.condition_lens_triage_summary)
    _write_json(outputs["recording_quality_gate"], result.recording_quality_gate)
    _write_json(outputs["basic_assumption_checks"], result.basic_assumption_checks)
    _write_rows(outputs["data_behavior_by_scope"], result.data_behavior_rows)
    _write_json(outputs["exploratory_quality_summary"], result.exploratory_quality_summary)
    return outputs


def format_analysis_summary(result: SessionAnalysisResult) -> str:
    total = len(result.response_rows)
    hits = sum(1 for row in result.response_rows if row.get("hit"))
    clicks = [float(row["rt_ms"]) for row in result.response_rows if row.get("rt_ms") not in (None, "")]
    lines = [
        f"Tactile trials reconstructed: {total}",
        f"Detected responses: {hits} ({(hits / total * 100.0):.1f}% hit rate)" if total else "Detected responses: 0",
    ]
    if clicks:
        lines.append(f"Mean RT: {statistics.mean(clicks):.1f} ms")
    if result.fit_rows:
        lines.append("")
        lines.append("Sigmoid PPS fits")
        for fit in result.fit_rows[:8]:
            boundary = _fmt(fit.get("pps_boundary_soa_ms"), 1)
            slope = _fmt(fit.get("slope"), 5)
            r2 = _fmt(fit.get("r2"), 3)
            lines.append(f"- {fit.get('scope', '')}: boundary {boundary} ms, slope {slope}, R2 {r2}")
    else:
        lines.append("No sigmoid fit yet; at least four usable SOA points are needed per condition.")
    if result.model_comparison_rows:
        lines.append("")
        lines.append("Best model by AIC")
        for row in result.model_comparison_rows[:8]:
            lines.append(f"- {row.get('scope', '')}: {row.get('best_model', '')}, R2 {_fmt(row.get('best_r2'), 3)}")
    if result.warnings:
        lines.append("")
        lines.append("Warnings")
        lines.extend(f"- {warning}" for warning in result.warnings[:8])
    return "\n".join(lines)


def _build_data_behavior_review(
    result: SessionAnalysisResult,
    event_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build exploratory, non-gating behavior signals from immediate outputs."""

    rows: list[dict[str, Any]] = []
    curves_by_scope: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in result.curve_rows:
        scope = str(row.get("scope") or "").strip()
        mode = str(row.get("aggregation_mode") or AGGREGATION_SEPARATE_PARTS).strip()
        if scope:
            curves_by_scope.setdefault((mode, scope), []).append(row)

    fits_by_scope: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in result.model_fit_rows:
        scope = str(row.get("scope") or "").strip()
        mode = str(row.get("aggregation_mode") or AGGREGATION_SEPARATE_PARTS).strip()
        if scope:
            fits_by_scope.setdefault((mode, scope), []).append(row)

    comparison_by_scope = {
        (str(row.get("aggregation_mode") or AGGREGATION_SEPARATE_PARTS).strip(), str(row.get("scope") or "").strip()): row
        for row in result.model_comparison_rows
        if str(row.get("scope") or "").strip()
    }

    final_by_scope = _final_outcomes_by_scope(result.final_outcome_rows or result.response_rows)
    for (mode, scope), curve_rows in sorted(curves_by_scope.items(), key=lambda item: item[0]):
        _extend_scope_behavior_rows(
            rows,
            scope=scope,
            aggregation_mode=mode,
            curve_rows=curve_rows,
            fit_rows=fits_by_scope.get((mode, scope), []),
            comparison_row=comparison_by_scope.get((mode, scope), {}),
            response_rows=final_by_scope.get((mode, scope), []),
        )

    if not curves_by_scope:
        rows.append(
            _behavior_row(
                scope="Session",
                aggregation_mode="",
                signal=SIGNAL_INSUFFICIENT,
                feature="RT or facilitation by SOA/distance",
                message="No analyzable SOA/distance curve rows were written for this session.",
                evidence="curve_points=0",
            )
        )

    rows.extend(_session_level_behavior_rows(result, event_rows))
    summary = _behavior_summary(rows, result, event_rows)
    return rows, summary


def _extend_scope_behavior_rows(
    rows: list[dict[str, Any]],
    *,
    scope: str,
    aggregation_mode: str,
    curve_rows: list[dict[str, Any]],
    fit_rows: list[dict[str, Any]],
    comparison_row: dict[str, Any],
    response_rows: list[dict[str, Any]],
) -> None:
    points = sorted(
        (
            (_as_float(row.get("soa_ms"), math.nan), _metric_value_for_row(row))
            for row in curve_rows
        ),
        key=lambda item: item[0],
    )
    points = [(x, y) for x, y in points if math.isfinite(x) and math.isfinite(y)]
    x_values = [x for x, _y in points]
    y_values = [y for _x, y in points]
    point_count = len(set(x_values))
    n_values = [_as_float(row.get("n"), math.nan) for row in curve_rows]
    low_n = [value for value in n_values if math.isfinite(value) and value < 3]

    if point_count < 2:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_INSUFFICIENT,
                feature="RT or facilitation by SOA/distance",
                message="Too few SOA/distance points were available to inspect a curve tendency.",
                evidence=f"points={point_count}",
            )
        )
    elif point_count < 4:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_INSUFFICIENT,
                feature="Model parameter or fit tables",
                message="The curve can be plotted, but common PPS model comparisons are underpowered with fewer than four sampled points.",
                evidence=f"points={point_count}",
            )
        )
    elif y_values and max(y_values) - min(y_values) < 5.0:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_UNUSUAL,
                feature="RT or facilitation by SOA/distance",
                message="The observed SOA/distance curve is nearly flat, which is unusual relative to common PPS facilitation displays.",
                evidence=f"range_ms={max(y_values) - min(y_values):.3f}; points={point_count}",
            )
        )
    else:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_EXPECTED,
                feature="RT or facilitation by SOA/distance",
                message="The recording has enough SOA/distance points and a visible response-metric range for common PPS curve review.",
                evidence=f"points={point_count}; range_ms={max(y_values) - min(y_values):.3f}" if y_values else f"points={point_count}",
            )
        )

    if low_n:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_MIXED,
                feature="Condition/group summaries",
                message="Some SOA/distance means are based on sparse observations, so visual trends should be treated as exploratory.",
                evidence=f"low_n_points={len(low_n)}; min_n={min(low_n):.0f}",
            )
        )

    spread_ratios = _spread_ratios(curve_rows)
    if spread_ratios:
        max_ratio = max(spread_ratios)
        signal = SIGNAL_MIXED if max_ratio > 0.75 else SIGNAL_EXPECTED
        message = (
            "Uncertainty bands are wide relative to the observed curve range."
            if signal == SIGNAL_MIXED
            else "Uncertainty/range columns are available for visual inspection around the means."
        )
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=signal,
                feature="Uncertainty/range around means",
                message=message,
                evidence=f"max_spread_to_curve_range={max_ratio:.3f}",
            )
        )

    best_model = str(comparison_row.get("best_model") or "").strip()
    if fit_rows:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_EXPECTED,
                feature="Sigmoid, linear, and logarithmic-decay model fits",
                message="At least one common PPS model family was fit for this scope.",
                evidence=f"models={';'.join(sorted({str(row.get('model') or '').strip() for row in fit_rows if str(row.get('model') or '').strip()}))}; best={best_model}",
            )
        )
        _extend_model_stability_rows(rows, scope, aggregation_mode, fit_rows, comparison_row, x_values)
    elif point_count >= 2:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_INSUFFICIENT,
                feature="Sigmoid, linear, and logarithmic-decay model fits",
                message="No model-fit rows were available for this plotted scope.",
                evidence=f"points={point_count}",
            )
        )

    if response_rows:
        hit_rate = sum(1 for row in response_rows if _truthy(row.get("hit"))) / len(response_rows)
        if hit_rate < 0.6:
            signal = SIGNAL_UNUSUAL
            message = "The selected response distribution is unusually sparse for this scope."
        elif hit_rate < 0.8:
            signal = SIGNAL_MIXED
            message = "The selected response distribution is uneven, so curve interpretation should stay cautious."
        else:
            signal = SIGNAL_EXPECTED
            message = "The selected response yield is sufficient for exploratory plotting in this scope."
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=signal,
                feature="Condition/group summaries",
                message=message,
                evidence=f"hit_rate={hit_rate:.3f}; trials={len(response_rows)}",
            )
        )


def _extend_model_stability_rows(
    rows: list[dict[str, Any]],
    scope: str,
    aggregation_mode: str,
    fit_rows: list[dict[str, Any]],
    comparison_row: dict[str, Any],
    x_values: list[float],
) -> None:
    finite_aic = sorted(
        (_as_float(row.get("aic"), math.inf), str(row.get("model") or "").strip())
        for row in fit_rows
        if math.isfinite(_as_float(row.get("aic"), math.inf))
    )
    if len(finite_aic) >= 2 and finite_aic[1][0] - finite_aic[0][0] <= 2.0:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_MIXED,
                feature="Sigmoid, linear, and logarithmic-decay model fits",
                message="Model fits are close by AIC, so the best model should be read as an exploratory tendency.",
                evidence=f"best={finite_aic[0][1]}; delta_aic={finite_aic[1][0] - finite_aic[0][0]:.3f}",
            )
        )

    sigmoid = next((row for row in fit_rows if str(row.get("model") or "").strip() == "sigmoid"), None)
    if sigmoid is None:
        return
    boundary = _as_float(sigmoid.get("pps_boundary_soa_ms"), math.nan)
    if not math.isfinite(boundary) or not x_values:
        return
    if min(x_values) <= boundary <= max(x_values):
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_EXPECTED,
                feature="PPS boundary or size-index estimates",
                message="The sigmoid boundary estimate falls inside the sampled SOA/distance range.",
                evidence=f"boundary={boundary:.3f}; sampled_min={min(x_values):.3f}; sampled_max={max(x_values):.3f}",
            )
        )
    else:
        rows.append(
            _behavior_row(
                scope=scope,
                aggregation_mode=aggregation_mode,
                signal=SIGNAL_UNUSUAL,
                feature="PPS boundary or size-index estimates",
                message="The sigmoid boundary estimate falls outside the sampled SOA/distance range.",
                evidence=f"boundary={boundary:.3f}; sampled_min={min(x_values):.3f}; sampled_max={max(x_values):.3f}",
            )
        )


def _session_level_behavior_rows(
    result: SessionAnalysisResult,
    event_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    event_types = [str(row.get("event_type") or "").strip() for row in event_rows]
    payload_qualities = [str(row.get("timestamp_quality") or "").strip() for row in event_rows if str(row.get("timestamp_quality") or "").strip()]
    fallback_count = sum(1 for event_type in event_types if event_type == "timing_anchor_fallback")
    fallback_count += sum(1 for quality in payload_qualities if "fallback" in quality.lower())
    if fallback_count:
        rows.append(
            _behavior_row(
                scope="Session",
                aggregation_mode="",
                signal=SIGNAL_TECHNICAL,
                feature="Timing evidence",
                message="Timing fallback evidence was logged, so plotted response timing should be reviewed with the timing artifacts.",
                evidence=f"fallback_count={fallback_count}",
            )
        )
    elif payload_qualities:
        exact = sum(1 for quality in payload_qualities if quality == "dac_time_sample_exact")
        rows.append(
            _behavior_row(
                scope="Session",
                aggregation_mode="",
                signal=SIGNAL_EXPECTED,
                feature="Timing evidence",
                message="Scheduled timing markers report sample-exact DAC timestamps where timing quality was recorded.",
                evidence=f"dac_time_sample_exact={exact}; timestamp_quality_rows={len(payload_qualities)}",
            )
        )

    mouse_events = [row for row in event_rows if str(row.get("event_type") or "").strip() == "mouse_click"]
    selected_clicks = {
        str(row.get("click_event_id") or "").strip()
        for row in result.final_outcome_rows or result.response_rows
        if str(row.get("click_event_id") or "").strip()
    }
    extra_clicks = [row for row in mouse_events if str(row.get("event_id") or "").strip() not in selected_clicks]
    tactile_count = sum(1 for row in event_rows if str(row.get("event_type") or "").strip() == "tactile_onset")
    if mouse_events and tactile_count:
        ratio = len(extra_clicks) / max(1, tactile_count)
        if ratio > 0.2:
            signal = SIGNAL_UNUSUAL
            message = "Extra logged clicks are frequent relative to tactile events; inspect excluded-event behavior before interpreting curves."
        elif ratio > 0.05:
            signal = SIGNAL_MIXED
            message = "Extra logged clicks are present but selected analysis responses remain traceable."
        else:
            signal = SIGNAL_EXPECTED
            message = "Logged click behavior is close to the selected response set."
        rows.append(
            _behavior_row(
                scope="Session",
                aggregation_mode="",
                signal=signal,
                feature="Rejected / extra clicks",
                message=message,
                evidence=f"mouse_clicks={len(mouse_events)}; selected_clicks={len(selected_clicks)}; extra_clicks={len(extra_clicks)}; tactile_events={tactile_count}",
            )
        )

    final_rows = result.final_outcome_rows or result.response_rows
    if final_rows:
        final_hits = sum(1 for row in final_rows if _truthy(row.get("hit")))
        hit_rate = final_hits / len(final_rows)
        if hit_rate < 0.6:
            signal = SIGNAL_UNUSUAL
            message = "The final response yield is unusually sparse across the session."
        elif hit_rate < 0.8:
            signal = SIGNAL_MIXED
            message = "The final response yield is mixed and should be interpreted condition-by-condition."
        else:
            signal = SIGNAL_EXPECTED
            message = "The final response yield is sufficient for exploratory review."
        rows.append(
            _behavior_row(
                scope="Session",
                aggregation_mode="",
                signal=signal,
                feature="Response distribution",
                message=message,
                evidence=f"final_hits={final_hits}; final_trials={len(final_rows)}; hit_rate={hit_rate:.3f}",
            )
        )

    rescued = [row for row in final_rows if _truthy(row.get("rescued_in_topup"))]
    unresolved = [row for row in final_rows if not _truthy(row.get("hit"))]
    if rescued:
        rows.append(
            _behavior_row(
                scope="Session",
                aggregation_mode="",
                signal=SIGNAL_MIXED if unresolved else SIGNAL_EXPECTED,
                feature="Top-up rescues",
                message=(
                    "Top-up rescued missed trials, with some misses still unresolved."
                    if unresolved
                    else "Top-up rescue rows are present and final outcomes reflect the recovered responses."
                ),
                evidence=f"rescued={len(rescued)}; unresolved_final_misses={len(unresolved)}",
            )
        )
    elif unresolved:
        rows.append(
            _behavior_row(
                scope="Session",
                aggregation_mode="",
                signal=SIGNAL_MIXED,
                feature="Top-up rescues",
                message="Some final tactile trials remain misses; this may be expected if top-up was disabled or declined.",
                evidence=f"unresolved_final_misses={len(unresolved)}",
            )
        )
    return rows


def _behavior_summary(
    rows: list[dict[str, Any]],
    result: SessionAnalysisResult,
    event_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in rows:
        signal = str(row.get("signal") or "").strip()
        counts[signal] = counts.get(signal, 0) + 1
    return {
        "schema": DATA_BEHAVIOR_SCHEMA,
        "interpretation_note": (
            "Exploratory data-behavior signals describe tendencies in the recorded PPS outputs. "
            "They are not scientific conclusions, participant-readiness certification, or a replacement for manual review."
        ),
        "common_pps_visualization_features": list(COMMON_PPS_VISUALIZATION_FEATURES),
        "signal_labels": [SIGNAL_EXPECTED, SIGNAL_MIXED, SIGNAL_UNUSUAL, SIGNAL_INSUFFICIENT, SIGNAL_TECHNICAL],
        "signal_counts": counts,
        "scope_count": len({(row.get("aggregation_mode", ""), row.get("scope", "")) for row in rows if row.get("scope") not in ("", "Session")}),
        "curve_scope_count": len({(row.get("aggregation_mode", ""), row.get("scope", "")) for row in result.curve_rows if row.get("scope")}),
        "response_row_count": len(result.response_rows),
        "final_outcome_row_count": len(result.final_outcome_rows),
        "event_count": len(event_rows),
    }


def _behavior_row(
    *,
    scope: str,
    aggregation_mode: str,
    signal: str,
    feature: str,
    message: str,
    evidence: str,
) -> dict[str, Any]:
    return {
        "scope": scope,
        "aggregation_mode": aggregation_mode,
        "signal": signal,
        "feature": feature,
        "message": message,
        "evidence": evidence,
    }


def _metric_value_for_row(row: dict[str, Any]) -> float:
    metric = str(row.get("fit_metric") or "").strip()
    candidates = [metric] if metric else []
    candidates.extend(["facilitation_ms", "mean_rt_ms"])
    for key in candidates:
        value = _as_float(row.get(key), math.nan)
        if math.isfinite(value):
            return value
    return math.nan


def _spread_ratios(rows: list[dict[str, Any]]) -> list[float]:
    y_values = [_metric_value_for_row(row) for row in rows]
    y_values = [value for value in y_values if math.isfinite(value)]
    if len(y_values) < 2:
        return []
    y_range = max(y_values) - min(y_values)
    if y_range <= 0:
        return []
    ratios = []
    for row in rows:
        y = _metric_value_for_row(row)
        if not math.isfinite(y):
            continue
        metric = str(row.get("fit_metric") or "").strip()
        candidates = (
            ["facilitation_sem_ms", "fit_metric_sem_ms", "facilitation_sd_ms", "fit_metric_sd_ms", "sem_rt_ms", "sd_rt_ms"]
            if metric == "facilitation_ms"
            else ["sem_rt_ms", "fit_metric_sem_ms", "sd_rt_ms", "fit_metric_sd_ms"]
        )
        for key in candidates:
            spread = _as_float(row.get(key), math.nan)
            if math.isfinite(spread) and spread > 0:
                ratios.append((spread * 2.0) / y_range)
                break
    return ratios


def _final_outcomes_by_scope(response_rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in response_rows:
        for mode in (AGGREGATION_SEPARATE_PARTS, AGGREGATION_POOL_PARTS):
            part_label, condition, phase, noise = _analysis_context(row, aggregation_mode=mode)
            scope = _scope(part_label, condition, phase, noise)
            grouped.setdefault((mode, scope), []).append(row)
    return grouped


def _pair_tactile_responses(events: list[dict[str, Any]], *, min_rt_s: float, max_rt_s: float) -> list[dict[str, Any]]:
    tactile_events = [row for row in events if row.get("event_type") == "tactile_onset"]
    clicks = [row for row in events if row.get("event_type") == "mouse_click" and _truthy(row.get("in_target", True))]
    clicks = [row for row in clicks if _truthy(row.get("during_playback", True))]
    clicks = sorted(clicks, key=lambda row: (_as_float(row.get("unix_time"), 0.0), row.get("event_id", 0)))
    used_click_ids: set[Any] = set()
    response_rows = []
    for tactile in tactile_events:
        onset = _as_float(tactile.get("unix_time"), 0.0)
        response_deadline = onset + max_rt_s
        response_required = _trial_requires_response(tactile)
        click = None
        for candidate in clicks:
            click_time = _as_float(candidate.get("unix_time"), 0.0)
            if candidate.get("event_id") in used_click_ids:
                continue
            if not _same_trial_context(tactile, candidate):
                continue
            valid_start = onset + min_rt_s if response_required else onset
            if click_time < valid_start or click_time > response_deadline:
                continue
            click = candidate
            used_click_ids.add(candidate.get("event_id"))
            break
        row = _response_base(tactile)
        row["tactile_unix_time"] = onset
        row["response_required"] = response_required
        row["expected_response"] = row.get("expected_response") or ("respond" if response_required else "withhold")
        observed_response_choice = _response_choice_from_click(click, row) if click is not None else ""
        response_choice_correct = _response_choice_correctness(observed_response_choice, row.get("correct_response", ""))
        row["observed_response_choice"] = observed_response_choice
        row["response_choice_correct"] = "" if response_choice_correct is None else bool(response_choice_correct)
        if response_required and _trial_requires_choice_scoring(row):
            row["hit"] = click is not None and response_choice_correct is True
        else:
            row["hit"] = (click is not None) if response_required else (click is None)
        if click is not None:
            click_time = _as_float(click.get("unix_time"), 0.0)
            row["click_unix_time"] = click_time
            if response_required:
                row["rt_ms"] = round((click_time - onset) * 1000.0, 6)
                row["false_alarm_rt_ms"] = ""
            else:
                row["rt_ms"] = ""
                row["false_alarm_rt_ms"] = round((click_time - onset) * 1000.0, 6)
            row["click_x"] = click.get("x", "")
            row["click_y"] = click.get("y", "")
            row["click_event_id"] = click.get("event_id", "")
        else:
            row["click_unix_time"] = ""
            row["rt_ms"] = ""
            row["false_alarm_rt_ms"] = ""
            row["click_x"] = ""
            row["click_y"] = ""
            row["click_event_id"] = ""
        response_rows.append(row)
    return response_rows


def _response_base(event: dict[str, Any]) -> dict[str, Any]:
    part_number = _as_int(_field(event, "part_number", "Part_Number"), None)
    condition = _field(event, "condition") or (f"Part {part_number}" if part_number else "")
    return {
        "participant_id": _field(event, "participant_id", "Participant_ID"),
        "condition": condition,
        "part_number": part_number if part_number is not None else "",
        "block_number": _as_int(_field(event, "block_number", "Block_Number"), ""),
        "block_label": _field(event, "block_label", "Block_Label"),
        "trial_number": _as_int(_field(event, "trial_number", "Trial_Number"), ""),
        "trial_uid": _field(event, "trial_uid", "Trial_UID"),
        "trial_type": _field(event, "trial_type", "Trial_Type"),
        "family": _field(event, "family", "Family"),
        "row_label": _field(event, "row_label", "Row_Label", "Row"),
        "soa_ms": _as_int(_field(event, "soa_ms", "SOA_ms"), ""),
        "expected_response": _field(
            event,
            "expected_response",
            "Expected_Response",
            "response_expected",
            "Response_Expected",
            "required_response",
            "Required_Response",
        ),
        "response_rule": _field(
            event,
            "response_rule",
            "Response_Rule",
            "response_mapping",
            "Response_Mapping",
            "task_response_rule",
            "Task_Response_Rule",
        ),
        "target_role": _field(
            event,
            "target_role",
            "Target_Role",
            "go_nogo_role",
            "Go_NoGo_Role",
            "stimulus_role",
            "Stimulus_Role",
            "tactile_role",
            "Tactile_Role",
        ),
        "response_mode": _field(event, "response_mode", "Response_Mode", "choice_mode", "Choice_Mode"),
        "response_choice_set": _field(
            event,
            "response_choice_set",
            "Response_Choice_Set",
            "choice_set",
            "Choice_Set",
            "response_choices",
            "Response_Choices",
            "response_options",
            "Response_Options",
        ),
        "correct_response": _field(
            event,
            "correct_response",
            "Correct_Response",
            "correct_choice",
            "Correct_Choice",
            "target_choice",
            "Target_Choice",
            "expected_choice",
            "Expected_Choice",
        ),
        "response_scoring_policy": _field(
            event,
            "response_scoring_policy",
            "Response_Scoring_Policy",
            "choice_scoring_policy",
            "Choice_Scoring_Policy",
            "response_mapping_policy",
            "Response_Mapping_Policy",
        ),
        "response_capture_device": _field(
            event,
            "response_capture_device",
            "Response_Capture_Device",
            "response_device",
            "Response_Device",
            "response_capture",
            "Response_Capture",
        ),
        "response_input_modality": _field(
            event,
            "response_input_modality",
            "Response_Input_Modality",
            "response_modality",
            "Response_Modality",
            "input_modality",
            "Input_Modality",
        ),
        "tool_condition": _field(event, "tool_condition", "Tool_Condition"),
        "locomotion_condition": _field(event, "locomotion_condition", "Locomotion_Condition"),
        "multisensory_trial_family": _field(
            event,
            "multisensory_trial_family",
            "Multisensory_Trial_Family",
            "trial_modality_family",
            "Trial_Modality_Family",
        ),
        "exteroceptive_modality_set": _field(
            event,
            "exteroceptive_modality_set",
            "Exteroceptive_Modality_Set",
            "external_stimulus_modality_set",
            "External_Stimulus_Modality_Set",
        ),
        "visual_stimulus_type": _field(event, "visual_stimulus_type", "Visual_Stimulus_Type"),
        "visual_motion_profile": _field(event, "visual_motion_profile", "Visual_Motion_Profile"),
        "visual_start_distance_cm": _field(event, "visual_start_distance_cm", "Visual_Start_Distance_cm"),
        "visual_end_distance_cm": _field(event, "visual_end_distance_cm", "Visual_End_Distance_cm"),
        "visual_speed_cm_s": _field(event, "visual_speed_cm_s", "Visual_Speed_cm_s"),
        "visual_duration_ms": _field(event, "visual_duration_ms", "Visual_Duration_ms"),
        "visual_renderer_engine": _field(event, "visual_renderer_engine", "Visual_Renderer_Engine"),
        "visual_display_device": _field(event, "visual_display_device", "Visual_Display_Device"),
        "mixed_reality_context": _field(event, "mixed_reality_context", "Mixed_Reality_Context"),
        "body_rendering_mode": _field(event, "body_rendering_mode", "Body_Rendering_Mode"),
        "audiovisual_synchrony_policy": _field(
            event,
            "audiovisual_synchrony_policy",
            "Audiovisual_Synchrony_Policy",
        ),
        "mixed_reality_equivalence_boundary": _field(
            event,
            "mixed_reality_equivalence_boundary",
            "Mixed_Reality_Equivalence_Boundary",
        ),
        "audio_output_mode": _field(
            event,
            "audio_output_mode",
            "Audio_Output_Mode",
            "speaker_array_mode",
            "Speaker_Array_Mode",
        ),
        "speaker_array_id": _field(event, "speaker_array_id", "Speaker_Array_ID"),
        "speaker_array_layout": _field(event, "speaker_array_layout", "Speaker_Array_Layout"),
        "speaker_switch_sequence": _field(event, "speaker_switch_sequence", "Speaker_Switch_Sequence"),
        "speaker_switch_times_ms": _field(
            event,
            "speaker_switch_times_ms",
            "Speaker_Switch_Times_ms",
            "speaker_switch_boundaries_ms",
            "Speaker_Switch_Boundaries_ms",
        ),
        "speaker_switch_channels": _field(
            event,
            "speaker_switch_channels",
            "Speaker_Switch_Channels",
            "speaker_output_channels",
            "Speaker_Output_Channels",
        ),
        "speaker_switch_gains": _field(event, "speaker_switch_gains", "Speaker_Switch_Gains"),
        "speaker_source_channel": _field(event, "speaker_source_channel", "Speaker_Source_Channel"),
        "speaker_switch_generated": _field(event, "speaker_switch_generated", "Speaker_Switch_Generated"),
        "voice_key_enabled": _field(
            event,
            "voice_key_enabled",
            "Voice_Key_Enabled",
            "voice_key_required",
            "Voice_Key_Required",
            "vocal_response_required",
            "Vocal_Response_Required",
        ),
        "voice_key_response_label": _field(
            event,
            "voice_key_response_label",
            "Voice_Key_Response_Label",
            "vocal_response_label",
            "Vocal_Response_Label",
            "spoken_response_label",
            "Spoken_Response_Label",
        ),
        "voice_key_threshold": _field(
            event,
            "voice_key_threshold",
            "Voice_Key_Threshold",
            "voice_key_threshold_db",
            "Voice_Key_Threshold_dB",
            "microphone_threshold",
            "Microphone_Threshold",
        ),
        "voice_key_latency_correction_ms": _field(
            event,
            "voice_key_latency_correction_ms",
            "Voice_Key_Latency_Correction_ms",
            "voice_key_latency_ms",
            "Voice_Key_Latency_ms",
            "vocal_onset_correction_ms",
            "Vocal_Onset_Correction_ms",
        ),
        "tactile_stimulation_modality": _field(
            event,
            "tactile_stimulation_modality",
            "Tactile_Stimulation_Modality",
            "tactile_modality",
            "Tactile_Modality",
            "stimulation_modality",
            "Stimulation_Modality",
        ),
        "tactile_calibration_method": _field(
            event,
            "tactile_calibration_method",
            "Tactile_Calibration_Method",
            "calibration_method",
            "Calibration_Method",
            "electrical_calibration_method",
            "Electrical_Calibration_Method",
        ),
        "tactile_threshold_reference": _field(
            event,
            "tactile_threshold_reference",
            "Tactile_Threshold_Reference",
            "tactile_threshold",
            "Tactile_Threshold",
            "threshold_reference",
            "Threshold_Reference",
            "electrical_threshold_reference",
            "Electrical_Threshold_Reference",
        ),
        "tactile_intensity": _field(
            event,
            "tactile_intensity",
            "Tactile_Intensity",
            "electrical_current",
            "Electrical_Current",
            "tactile_current",
            "Tactile_Current",
        ),
        "tactile_intensity_unit": _field(
            event,
            "tactile_intensity_unit",
            "Tactile_Intensity_Unit",
            "electrical_current_unit",
            "Electrical_Current_Unit",
            "tactile_current_unit",
            "Tactile_Current_Unit",
        ),
        "tactile_pulse_duration_ms": _field(
            event,
            "tactile_pulse_duration_ms",
            "Tactile_Pulse_Duration_ms",
            "electrical_pulse_duration_ms",
            "Electrical_Pulse_Duration_ms",
            "pulse_duration_ms",
            "Pulse_Duration_ms",
        ),
        "electrical_stimulator_model": _field(
            event,
            "electrical_stimulator_model",
            "Electrical_Stimulator_Model",
            "stimulator_model",
            "Stimulator_Model",
            "tactile_stimulator_model",
            "Tactile_Stimulator_Model",
        ),
        "electrical_electrode_site": _field(
            event,
            "electrical_electrode_site",
            "Electrical_Electrode_Site",
            "electrode_site",
            "Electrode_Site",
            "tactile_electrode_site",
            "Tactile_Electrode_Site",
        ),
        "spatial_coordinate_frame": _field(
            event,
            "spatial_coordinate_frame",
            "Spatial_Coordinate_Frame",
            "coordinate_frame",
            "Coordinate_Frame",
            "reference_frame",
            "Reference_Frame",
        ),
        "body_anchor": _field(
            event,
            "body_anchor",
            "Body_Anchor",
            "anchored_body_part",
            "Anchored_Body_Part",
            "body_reference_anchor",
            "Body_Reference_Anchor",
        ),
        "body_part": _field(
            event,
            "body_part",
            "Body_Part",
            "tactile_body_part",
            "Tactile_Body_Part",
            "tactile_site",
            "Tactile_Site",
        ),
        "body_side": _field(
            event,
            "body_side",
            "Body_Side",
            "reference_side",
            "Reference_Side",
            "tactile_side",
            "Tactile_Side",
        ),
        "spatial_hemifield": _field(
            event,
            "spatial_hemifield",
            "Spatial_Hemifield",
            "hemifield",
            "Hemifield",
            "field",
            "Field",
        ),
        "body_relative_axis": _field(
            event,
            "body_relative_axis",
            "Body_Relative_Axis",
            "trajectory_axis",
            "Trajectory_Axis",
            "spatial_axis",
            "Spatial_Axis",
        ),
        "auditory_trajectory_family": _field(
            event,
            "auditory_trajectory_family",
            "Auditory_Trajectory_Family",
            "trajectory_family",
            "Trajectory_Family",
        ),
        "auditory_trajectory_direction": _field(
            event,
            "auditory_trajectory_direction",
            "Auditory_Trajectory_Direction",
            "trajectory_direction",
            "Trajectory_Direction",
        ),
        "trajectory_coordinate_frame": _field(
            event,
            "trajectory_coordinate_frame",
            "Trajectory_Coordinate_Frame",
        ),
        "trajectory_start_hemifield": _field(
            event,
            "trajectory_start_hemifield",
            "Trajectory_Start_Hemifield",
        ),
        "trajectory_end_hemifield": _field(
            event,
            "trajectory_end_hemifield",
            "Trajectory_End_Hemifield",
        ),
        "trajectory_start_distance_cm": _field(
            event,
            "trajectory_start_distance_cm",
            "Trajectory_Start_Distance_cm",
        ),
        "trajectory_end_distance_cm": _field(
            event,
            "trajectory_end_distance_cm",
            "Trajectory_End_Distance_cm",
        ),
        "trajectory_start_azimuth_deg": _field(
            event,
            "trajectory_start_azimuth_deg",
            "Trajectory_Start_Azimuth_deg",
        ),
        "trajectory_end_azimuth_deg": _field(
            event,
            "trajectory_end_azimuth_deg",
            "Trajectory_End_Azimuth_deg",
        ),
        "spatial_renderer_engine": _field(
            event,
            "spatial_renderer_engine",
            "Spatial_Renderer_Engine",
            "renderer_engine",
            "Renderer_Engine",
        ),
        "spatial_renderer_version": _field(
            event,
            "spatial_renderer_version",
            "Spatial_Renderer_Version",
            "renderer_version",
            "Renderer_Version",
        ),
        "hrtf_database": _field(event, "hrtf_database", "HRTF_Database"),
        "hrtf_subject_id": _field(event, "hrtf_subject_id", "HRTF_Subject_ID"),
        "hrtf_filter_id": _field(event, "hrtf_filter_id", "HRTF_Filter_ID"),
        "hrtf_near_field_compensation": _field(
            event,
            "hrtf_near_field_compensation",
            "HRTF_Near_Field_Compensation",
        ),
        "source_asset_equivalence": _field(
            event,
            "source_asset_equivalence",
            "Source_Asset_Equivalence",
        ),
        "renderer_equivalence_boundary": _field(
            event,
            "renderer_equivalence_boundary",
            "Renderer_Equivalence_Boundary",
        ),
        "tactile_channel": _field(event, "tactile_channel", "Tactile_Channel"),
        "tactile_waveform_shape": _field(event, "tactile_waveform_shape", "Tactile_Waveform_Shape"),
        "tactile_frequency_hz": _field(
            event,
            "tactile_frequency_hz",
            "Tactile_Frequency_Hz",
            "tactile_waveform_frequency_hz",
            "Tactile_Waveform_Frequency_Hz",
        ),
        "tactile_duration_ms": _field(
            event,
            "tactile_duration_ms",
            "Tactile_Duration_ms",
            "tactile_waveform_duration_ms",
            "Tactile_Waveform_Duration_ms",
        ),
        "tactile_amplitude": _field(event, "tactile_amplitude", "Tactile_Amplitude"),
        "tactile_waveform_generated": _field(event, "tactile_waveform_generated", "Tactile_Waveform_Generated"),
        "external_trigger_required": _field(event, "external_trigger_required", "External_Trigger_Required"),
        "external_trigger_modality": _field(event, "external_trigger_modality", "External_Trigger_Modality"),
        "external_trigger_role": _field(event, "external_trigger_role", "External_Trigger_Role"),
        "external_trigger_code": _field(event, "external_trigger_code", "External_Trigger_Code"),
        "external_trigger_tolerance_ms": _field(
            event,
            "external_trigger_tolerance_ms",
            "External_Trigger_Tolerance_ms",
        ),
        "external_trigger_channel": _field(event, "external_trigger_channel", "External_Trigger_Channel"),
        "noise_type": _field(event, "noise_type", "Noise_Type"),
        "sequence_labels": _field(event, "sequence_labels", "Sequence_Labels"),
        "sequence_variant_key": _field(event, "sequence_variant_key", "Sequence_Variant_Key"),
        "iti_policy": _field(event, "iti_policy", "ITI_Policy"),
        "iti_ms": _field(event, "iti_ms", "ITI_ms", "Intertrial_Interval_ms"),
        "foreperiod_ms": _field(event, "foreperiod_ms", "Foreperiod_ms"),
        "hazard_control_policy": _field(event, "hazard_control_policy", "Hazard_Control_Policy"),
        "expectancy_control_role": _field(event, "expectancy_control_role", "Expectancy_Control_Role"),
        "respiratory_phase": _field(event, "respiratory_phase", "Respiratory_Phase"),
        "stimulus_modality": _field(event, "stimulus_modality"),
        "is_topup": _truthy(_field(event, "is_topup", "Is_Topup")),
        "topup_role": str(_field(event, "topup_role", "Topup_Role") or "").strip().lower(),
        "source_trial_uid": _field(event, "source_trial_uid", "Source_Trial_UID", "Original_Trial_UID"),
        "primary_analysis_included": _primary_analysis_included(event),
        "topup_attempt_number": _field(event, "topup_attempt_number", "Topup_Attempt_Number"),
    }


def _same_trial_context(tactile: dict[str, Any], click: dict[str, Any]) -> bool:
    """Prevent later-block/top-up clicks from being credited to earlier trials."""
    tactile_block = _field(tactile, "block_number", "Block_Number")
    click_block = _field(click, "block_number", "Block_Number")
    if tactile_block not in (None, "") and click_block not in (None, ""):
        if str(_as_int(tactile_block, tactile_block)) != str(_as_int(click_block, click_block)):
            return False

    tactile_part = _field(tactile, "part_number", "Part_Number")
    click_part = _field(click, "part_number", "Part_Number")
    if tactile_part not in (None, "") and click_part not in (None, ""):
        if str(_as_int(tactile_part, tactile_part)) != str(_as_int(click_part, click_part)):
            return False

    return True


def _build_final_outcomes(response_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    originals: list[dict[str, Any]] = []
    rescue_by_source: dict[str, dict[str, Any]] = {}
    orphan_rescues: list[dict[str, Any]] = []
    for row in response_rows:
        is_topup = _truthy(row.get("is_topup"))
        role = str(row.get("topup_role") or "").strip().lower()
        if is_topup and role == "filler":
            continue
        if is_topup and role == "rescue":
            source_uid = str(row.get("source_trial_uid") or "").strip()
            if source_uid:
                rescue_by_source[source_uid] = row
            else:
                orphan_rescues.append(row)
            continue
        originals.append(row)

    final_rows: list[dict[str, Any]] = []
    original_uids = {str(row.get("trial_uid") or "") for row in originals}
    for row in originals:
        final = dict(row)
        trial_uid = str(row.get("trial_uid") or "")
        rescue = rescue_by_source.get(trial_uid)
        final["original_hit"] = bool(row.get("hit"))
        final["rescued_in_topup"] = False
        final["topup_trial_uid"] = ""
        final["topup_click_event_id"] = ""
        final["topup_rt_ms"] = ""
        final["final_outcome_source"] = "original"
        final["analysis_exclude_reason"] = "" if _truthy(row.get("primary_analysis_included", True)) else "primary_analysis_included_false"
        if rescue is not None and not bool(row.get("hit")):
            final["rescued_in_topup"] = True
            final["topup_trial_uid"] = rescue.get("trial_uid", "")
            final["topup_click_event_id"] = rescue.get("click_event_id", "")
            final["topup_rt_ms"] = rescue.get("rt_ms", "")
            final["topup_hit"] = bool(rescue.get("hit"))
            final["hit"] = bool(rescue.get("hit"))
            final["click_unix_time"] = rescue.get("click_unix_time", "") if rescue.get("hit") else ""
            final["click_event_id"] = rescue.get("click_event_id", "") if rescue.get("hit") else ""
            final["rt_ms"] = rescue.get("rt_ms", "") if rescue.get("hit") else ""
            final["final_outcome_source"] = "topup_rescue"
        final_rows.append(final)

    for rescue in orphan_rescues:
        source_uid = str(rescue.get("source_trial_uid") or "")
        if source_uid and source_uid in original_uids:
            continue
        final = dict(rescue)
        final["final_outcome_source"] = "topup_rescue_orphan"
        final["rescued_in_topup"] = True
        final["original_hit"] = ""
        final["topup_trial_uid"] = rescue.get("trial_uid", "")
        final_rows.append(final)
    return final_rows


def _summarize_responses(response_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in response_rows:
        key = (
            row.get("participant_id", ""),
            row.get("part_number", ""),
            row.get("condition", ""),
            row.get("trial_type", ""),
            row.get("respiratory_phase", ""),
            row.get("noise_type", ""),
            row.get("soa_ms", ""),
        )
        groups.setdefault(key, []).append(row)

    summary = []
    for key, rows in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
        rts = [_as_float(row.get("rt_ms"), math.nan) for row in rows if row.get("rt_ms") not in (None, "")]
        rts = [rt for rt in rts if math.isfinite(rt)]
        hits = sum(1 for row in rows if row.get("hit"))
        summary.append(
            {
                "participant_id": key[0],
                "part_number": key[1],
                "condition": key[2],
                "trial_type": key[3],
                "respiratory_phase": key[4],
                "noise_type": key[5],
                "soa_ms": key[6],
                "aggregation_mode": AGGREGATION_SEPARATE_PARTS,
                "n": len(rows),
                "hits": hits,
                "hit_rate": hits / len(rows) if rows else "",
                "mean_rt_ms": statistics.mean(rts) if rts else "",
                "sd_rt_ms": statistics.stdev(rts) if len(rts) > 1 else "",
            }
        )
    return summary


def _build_condition_lens_outputs(
    response_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    curve_rows: list[dict[str, Any]] = []
    model_fit_rows: list[dict[str, Any]] = []
    model_comparison_rows: list[dict[str, Any]] = []
    for lens in CONDITION_LENS_ORDER:
        lens_curves, lens_models, lens_comparisons = _build_condition_lens_curves_for_lens(response_rows, analysis_lens=lens)
        curve_rows.extend(lens_curves)
        model_fit_rows.extend(lens_models)
        model_comparison_rows.extend(lens_comparisons)
    return curve_rows, model_fit_rows, model_comparison_rows, _condition_lens_triage_summary(curve_rows, model_fit_rows, model_comparison_rows)


def _build_condition_lens_curves_for_lens(
    response_rows: list[dict[str, Any]],
    *,
    analysis_lens: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    baseline = _condition_lens_baseline_means(response_rows, analysis_lens=analysis_lens)
    audio_rows = [row for row in response_rows if row.get("trial_type") == "Audio-Tactile" and row.get("rt_ms") not in (None, "")]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in audio_rows:
        scope, part_label, state_label = _condition_lens_context(row, analysis_lens=analysis_lens)
        groups.setdefault((scope, part_label, state_label), []).append(row)

    curve_rows: list[dict[str, Any]] = []
    model_fit_rows: list[dict[str, Any]] = []
    model_comparison_rows: list[dict[str, Any]] = []
    for (scope, part_label, state_label), rows in sorted(
        groups.items(),
        key=lambda item: (_part_number_from_label(item[0][1]) or 999, tuple(str(part) for part in item[0])),
    ):
        by_soa: dict[int, list[float]] = {}
        for row in rows:
            soa = _as_int(row.get("soa_ms"), None)
            rt = _as_float(row.get("rt_ms"), math.nan)
            if soa is None or not math.isfinite(rt):
                continue
            by_soa.setdefault(soa, []).append(rt)

        xs: list[float] = []
        ys: list[float] = []
        metric = "facilitation_ms"
        for soa, values in sorted(by_soa.items()):
            mean_rt = statistics.mean(values)
            rt_sd = statistics.stdev(values) if len(values) > 1 else 0.0
            rt_sem = rt_sd / math.sqrt(len(values)) if len(values) > 1 else 0.0
            base_stats = baseline.get(scope)
            base_rt = base_stats.get("mean") if base_stats is not None else None
            facilitation = base_rt - mean_rt if base_rt is not None else None
            baseline_sem = _as_float((base_stats or {}).get("sem"), math.nan)
            facilitation_sem = math.sqrt(rt_sem**2 + baseline_sem**2) if facilitation is not None and math.isfinite(baseline_sem) else math.nan
            baseline_sd = _as_float((base_stats or {}).get("sd"), math.nan)
            facilitation_sd = math.sqrt(rt_sd**2 + baseline_sd**2) if facilitation is not None and math.isfinite(baseline_sd) else math.nan
            y = facilitation if facilitation is not None else mean_rt
            if facilitation is None:
                metric = "mean_rt_ms"
            curve_rows.append(
                {
                    "analysis_lens": analysis_lens,
                    "analysis_lens_label": _condition_lens_label(analysis_lens),
                    "display_scope": scope,
                    "scope": scope,
                    "aggregation_mode": analysis_lens,
                    "aggregation_label": _aggregation_label(analysis_lens),
                    "part_label": part_label,
                    "state_label": state_label,
                    "pooled_factors": _condition_lens_pooled_factors(analysis_lens),
                    "part_number": "" if _part_number_from_label(part_label) is None else _part_number_from_label(part_label),
                    "condition": "" if analysis_lens in {CONDITION_LENS_STATE, CONDITION_LENS_OVERALL} else part_label,
                    "respiratory_phase": "" if state_label == "All states" else state_label,
                    "noise_type": "All sources",
                    "soa_ms": soa,
                    "n": len(values),
                    "mean_rt_ms": mean_rt,
                    "sd_rt_ms": rt_sd if len(values) > 1 else "",
                    "sem_rt_ms": rt_sem if len(values) > 1 else "",
                    "baseline_mean_rt_ms": "" if base_rt is None else base_rt,
                    "baseline_sd_rt_ms": "" if not math.isfinite(baseline_sd) or base_rt is None else baseline_sd,
                    "baseline_sem_rt_ms": "" if not math.isfinite(baseline_sem) or base_rt is None else baseline_sem,
                    "baseline_n": "" if base_rt is None else base_stats.get("n", ""),
                    "baseline_source_soas_ms": "" if base_rt is None else base_stats.get("source_soas_ms", ""),
                    "baseline_correction_method": "" if base_rt is None else BASELINE_CORRECTION_METHOD_CONDITION_MEAN_POOLED_SOA,
                    "facilitation_ms": "" if facilitation is None else facilitation,
                    "facilitation_sd_ms": "" if not math.isfinite(facilitation_sd) else facilitation_sd,
                    "facilitation_sem_ms": "" if not math.isfinite(facilitation_sem) else facilitation_sem,
                    "fit_metric": metric,
                    "fit_metric_sd_ms": rt_sd if metric == "mean_rt_ms" and len(values) > 1 else ("" if not math.isfinite(facilitation_sd) else facilitation_sd),
                    "fit_metric_sem_ms": rt_sem if metric == "mean_rt_ms" and len(values) > 1 else ("" if not math.isfinite(facilitation_sem) else facilitation_sem),
                }
            )
            xs.append(float(soa))
            ys.append(float(y))

        model_rows = _fit_model_family(
            np.asarray(xs),
            np.asarray(ys),
            scope=scope,
            part_label=part_label,
            condition="",
            phase="" if state_label == "All states" else state_label,
            noise="All sources",
            metric=metric,
            aggregation_mode=analysis_lens,
        )
        for model_row in model_rows:
            model_row.update(
                {
                    "analysis_lens": analysis_lens,
                    "analysis_lens_label": _condition_lens_label(analysis_lens),
                    "display_scope": scope,
                    "part_label": part_label,
                    "state_label": state_label,
                    "pooled_factors": _condition_lens_pooled_factors(analysis_lens),
                    "evidence_tier": MODEL_EVIDENCE_INSUFFICIENT,
                }
            )
        _mark_model_evidence_tiers(model_rows)
        model_fit_rows.extend(model_rows)
        if model_rows:
            comparison = _model_comparison_from_rows(model_rows, scope=scope, analysis_lens=analysis_lens, part_label=part_label, state_label=state_label, metric=metric)
            model_comparison_rows.append(comparison)
    return curve_rows, model_fit_rows, model_comparison_rows


def _condition_lens_baseline_means(response_rows: list[dict[str, Any]], *, analysis_lens: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[tuple[float, int]]] = {}
    for row in response_rows:
        if row.get("trial_type") != "Baseline" or row.get("rt_ms") in (None, ""):
            continue
        rt = _as_float(row.get("rt_ms"), math.nan)
        soa = _as_int(row.get("soa_ms"), None)
        if soa is None or not math.isfinite(rt):
            continue
        scope, _part_label, _state_label = _condition_lens_context(row, analysis_lens=analysis_lens)
        groups.setdefault(scope, []).append((rt, soa))
    return {key: _baseline_mean_sd_sem(values) for key, values in groups.items() if values}


def _condition_lens_context(row: dict[str, Any], *, analysis_lens: str) -> tuple[str, str, str]:
    part_number = _as_int(row.get("part_number"), None)
    part_label = _part_display_label(row) if part_number is not None else "All parts"
    state_label = _state_label(row)
    if analysis_lens == CONDITION_LENS_TWO_BY_TWO:
        scope = _condition_lens_scope(part_label, state_label)
        return scope, part_label, state_label
    if analysis_lens == CONDITION_LENS_PART:
        return part_label, part_label, "All states"
    if analysis_lens == CONDITION_LENS_STATE:
        return state_label, "All parts", state_label
    return "All conditions", "All parts", "All states"


def _state_label(row: dict[str, Any]) -> str:
    for key in ("respiratory_phase", "row_label", "condition"):
        value = str(row.get(key) or "").strip()
        if value and not _condition_without_part_label(value) == "":
            return value
    return "All states"


def _condition_lens_scope(part_label: Any, state_label: Any) -> str:
    parts = [str(part) for part in (part_label, state_label) if str(part).strip() and str(part).strip() not in {"All parts", "All states"}]
    return " / ".join(parts) or "All conditions"


def _condition_lens_label(analysis_lens: str) -> str:
    if analysis_lens == CONDITION_LENS_TWO_BY_TWO:
        return "2 x 2"
    if analysis_lens == CONDITION_LENS_PART:
        return "Parts"
    if analysis_lens == CONDITION_LENS_STATE:
        return "States"
    return "Overall"


def _condition_lens_pooled_factors(analysis_lens: str) -> str:
    if analysis_lens == CONDITION_LENS_TWO_BY_TWO:
        return "noise/source"
    if analysis_lens == CONDITION_LENS_PART:
        return "state;noise/source"
    if analysis_lens == CONDITION_LENS_STATE:
        return "part;noise/source"
    return "part;state;noise/source"


def _mark_model_evidence_tiers(model_rows: list[dict[str, Any]]) -> None:
    finite = sorted(
        (_row_aicc(row), index)
        for index, row in enumerate(model_rows)
        if math.isfinite(_row_aicc(row))
    )
    if not finite:
        return
    best_aicc, best_index = finite[0]
    delta = finite[1][0] - best_aicc if len(finite) > 1 else math.inf
    tier = MODEL_EVIDENCE_STRONG if math.isfinite(delta) and delta > 4.0 else MODEL_EVIDENCE_MIXED
    if not math.isfinite(delta):
        tier = MODEL_EVIDENCE_INSUFFICIENT
    for row in model_rows:
        row["delta_aicc"] = ""
        row["evidence_tier"] = MODEL_EVIDENCE_INSUFFICIENT
    model_rows[best_index]["delta_aicc"] = "" if not math.isfinite(delta) else delta
    model_rows[best_index]["evidence_tier"] = tier


def _model_comparison_from_rows(
    model_rows: list[dict[str, Any]],
    *,
    scope: str,
    analysis_lens: str,
    part_label: str,
    state_label: str,
    metric: str,
) -> dict[str, Any]:
    finite = sorted(((_row_aicc(row), row) for row in model_rows if math.isfinite(_row_aicc(row))), key=lambda item: item[0])
    best_row = finite[0][1] if finite else min(model_rows, key=lambda row: _as_float(row.get("aic"), math.inf))
    delta = finite[1][0] - finite[0][0] if len(finite) > 1 else math.inf
    if len(finite) < 2:
        tier = MODEL_EVIDENCE_INSUFFICIENT
    else:
        tier = MODEL_EVIDENCE_STRONG if delta > 4.0 else MODEL_EVIDENCE_MIXED
    return {
        "analysis_lens": analysis_lens,
        "analysis_lens_label": _condition_lens_label(analysis_lens),
        "scope": scope,
        "display_scope": scope,
        "aggregation_mode": analysis_lens,
        "aggregation_label": _aggregation_label(analysis_lens),
        "part_label": part_label,
        "state_label": state_label,
        "pooled_factors": _condition_lens_pooled_factors(analysis_lens),
        "fit_metric": metric,
        "n_points": best_row.get("n_points", ""),
        "best_model": best_row.get("model", ""),
        "best_aic": best_row.get("aic", ""),
        "best_aicc": best_row.get("aicc", ""),
        "best_r2": best_row.get("r2", ""),
        "best_rmse": best_row.get("rmse", ""),
        "delta_aicc": "" if not math.isfinite(delta) else delta,
        "evidence_tier": tier,
        "candidate_models": ";".join(str(row.get("model", "")) for row in sorted(model_rows, key=lambda item: str(item.get("model", "")))),
    }


def _condition_lens_triage_summary(
    curve_rows: list[dict[str, Any]],
    model_fit_rows: list[dict[str, Any]],
    model_comparison_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    labels = _condition_lens_display_labels(curve_rows)
    lens_scores = {
        lens: {
            "label": labels.get(lens, _condition_lens_label(lens)),
            "curve_separation_score_ms": _lens_curve_separation_score(curve_rows, lens),
            "boundary_shift_score_ms": _lens_boundary_shift_score(curve_rows, model_fit_rows, lens),
        }
        for lens in (CONDITION_LENS_TWO_BY_TWO, CONDITION_LENS_PART, CONDITION_LENS_STATE)
    }
    curve_winner = _score_winner(lens_scores, "curve_separation_score_ms")
    boundary_winner = _score_winner(lens_scores, "boundary_shift_score_ms")
    for lens, payload in lens_scores.items():
        payload["curve_separation_winner"] = lens == curve_winner
        payload["boundary_shift_winner"] = lens == boundary_winner

    overall = next((row for row in model_comparison_rows if row.get("analysis_lens") == CONDITION_LENS_OVERALL), {})
    per_cell_counts: dict[str, int] = {}
    for row in model_comparison_rows:
        if row.get("analysis_lens") == CONDITION_LENS_OVERALL:
            continue
        model = str(row.get("best_model") or "").strip()
        if model and str(row.get("evidence_tier") or "") != MODEL_EVIDENCE_INSUFFICIENT:
            per_cell_counts[model] = per_cell_counts.get(model, 0) + 1
    default_model = str(overall.get("best_model") or "").strip()
    if not default_model or str(overall.get("evidence_tier") or "") == MODEL_EVIDENCE_INSUFFICIENT:
        default_model = "sigmoid"
    model_buttons = _model_button_summaries(default_model, overall, per_cell_counts)
    return {
        "schema": CONDITION_LENS_SCHEMA,
        "interpretation_note": (
            "Condition and model winners are exploratory triage cues for the just-finished participant. "
            "They summarize curve visibility and model support, not confirmatory statistics."
        ),
        "default_lens": CONDITION_LENS_TWO_BY_TWO if any(row.get("analysis_lens") == CONDITION_LENS_TWO_BY_TWO for row in curve_rows) else CONDITION_LENS_OVERALL,
        "default_model": default_model,
        "overall_model": dict(overall),
        "model_button_summaries": model_buttons,
        "condition_lens_buttons": lens_scores,
        "curve_separation_winner": curve_winner,
        "boundary_shift_winner": boundary_winner,
        "model_wins_by_subcondition": per_cell_counts,
    }


def _condition_lens_display_labels(curve_rows: list[dict[str, Any]]) -> dict[str, str]:
    parts = _ordered_unique(row.get("part_label") for row in curve_rows if row.get("analysis_lens") == CONDITION_LENS_TWO_BY_TWO)
    states = _ordered_unique(row.get("state_label") for row in curve_rows if row.get("analysis_lens") == CONDITION_LENS_TWO_BY_TWO)
    parts = [part for part in parts if part and part != "All parts"]
    states = [state for state in states if state and state != "All states"]
    return {
        CONDITION_LENS_TWO_BY_TWO: "2 x 2" if len(parts) == 2 and len(states) == 2 else "Interaction",
        CONDITION_LENS_PART: " | ".join(parts) if len(parts) == 2 else "Parts",
        CONDITION_LENS_STATE: " | ".join(states) if len(states) == 2 else "States",
        CONDITION_LENS_OVERALL: "Overall",
    }


def _ordered_unique(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    preferred = {"inhale": 0, "exhale": 1}
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return sorted(output, key=lambda item: (preferred.get(item.lower(), 99), _part_number_from_label(item) or 999, item))


def _lens_curve_separation_score(curve_rows: list[dict[str, Any]], lens: str) -> float | None:
    by_soa: dict[float, dict[str, float]] = {}
    for row in curve_rows:
        if row.get("analysis_lens") != lens:
            continue
        scope = str(row.get("scope") or "").strip()
        soa = _as_float(row.get("soa_ms"), math.nan)
        y = _metric_value_for_row(row)
        if scope and math.isfinite(soa) and math.isfinite(y):
            by_soa.setdefault(soa, {})[scope] = y
    ranges = [max(values.values()) - min(values.values()) for values in by_soa.values() if len(values) >= 2]
    return statistics.mean(ranges) if ranges else None


def _lens_boundary_shift_score(curve_rows: list[dict[str, Any]], model_fit_rows: list[dict[str, Any]], lens: str) -> float | None:
    sampled_ranges: dict[str, tuple[float, float]] = {}
    for row in curve_rows:
        if row.get("analysis_lens") != lens:
            continue
        scope = str(row.get("scope") or "").strip()
        soa = _as_float(row.get("soa_ms"), math.nan)
        if not scope or not math.isfinite(soa):
            continue
        old = sampled_ranges.get(scope)
        sampled_ranges[scope] = (soa, soa) if old is None else (min(old[0], soa), max(old[1], soa))
    boundaries = []
    for row in model_fit_rows:
        if row.get("analysis_lens") != lens or row.get("model") != "sigmoid":
            continue
        scope = str(row.get("scope") or "").strip()
        boundary = _as_float(row.get("pps_boundary_soa_ms"), math.nan)
        sampled = sampled_ranges.get(scope)
        if sampled is not None and math.isfinite(boundary) and sampled[0] <= boundary <= sampled[1]:
            boundaries.append(boundary)
    return max(boundaries) - min(boundaries) if len(boundaries) >= 2 else None


def _score_winner(scores: dict[str, dict[str, Any]], key: str) -> str:
    scored = [(float(payload[key]), lens) for lens, payload in scores.items() if payload.get(key) is not None]
    if not scored:
        return ""
    value, lens = max(scored, key=lambda item: item[0])
    return lens if value > 0 else ""


def _model_button_summaries(default_model: str, overall: dict[str, Any], per_cell_counts: dict[str, int]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for model in ("sigmoid", "logarithmic_decay", "linear"):
        if model == default_model:
            tier = str(overall.get("evidence_tier") or MODEL_EVIDENCE_MIXED)
        elif per_cell_counts.get(model, 0):
            tier = MODEL_EVIDENCE_MIXED
        else:
            tier = MODEL_EVIDENCE_INSUFFICIENT
        summaries[model] = {
            "evidence_tier": tier,
            "overall_winner": model == default_model,
            "subcondition_wins": per_cell_counts.get(model, 0),
        }
    return summaries


def _build_recording_quality_gate(result: SessionAnalysisResult, event_rows: list[dict[str, Any]]) -> dict[str, Any]:
    final_rows = result.final_outcome_rows or result.response_rows
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    metrics: dict[str, Any] = {
        "response_rows": len(result.response_rows),
        "final_outcome_rows": len(final_rows),
    }
    if not final_rows:
        failures.append(_quality_issue("no_usable_tactile_responses", "No usable analysis-ready tactile responses were reconstructed.", "final_outcome_rows=0"))
    hits = sum(1 for row in final_rows if _truthy(row.get("hit")))
    hit_rate = hits / len(final_rows) if final_rows else 0.0
    metrics["overall_hit_rate"] = hit_rate
    if final_rows and hit_rate < 0.70:
        failures.append(_quality_issue("overall_hit_rate_below_70pct", "Overall valid in-target tactile hit rate is below 70%.", f"hit_rate={hit_rate:.3f}"))

    cell_rows = _quality_condition_cells(final_rows)
    metrics["condition_cell_count"] = len(cell_rows)
    for cell, rows in sorted(cell_rows.items()):
        cell_hits = sum(1 for row in rows if _truthy(row.get("hit")))
        cell_hit_rate = cell_hits / len(rows) if rows else 0.0
        if cell_hit_rate < 0.50:
            failures.append(_quality_issue("condition_cell_hit_rate_below_50pct", f"{cell} has valid in-target hit rate below 50%.", f"hit_rate={cell_hit_rate:.3f}; trials={len(rows)}"))
        audio_hits = [row for row in rows if row.get("trial_type") == "Audio-Tactile" and _truthy(row.get("hit")) and row.get("rt_ms") not in (None, "")]
        soas = {_as_int(row.get("soa_ms"), None) for row in audio_hits}
        soas.discard(None)
        if audio_hits and (len(soas) < 4 or len(audio_hits) < 8):
            failures.append(
                _quality_issue(
                    "condition_cell_audio_tactile_coverage_low",
                    f"{cell} has too little valid audio-tactile coverage for a serious per-cell curve.",
                    f"valid_audio_tactile={len(audio_hits)}; distinct_soas={len(soas)}",
                )
            )

    baseline_rows = [row for row in final_rows if row.get("trial_type") == "Baseline"]
    if baseline_rows and not any(row.get("rt_ms") not in (None, "") and _truthy(row.get("hit")) for row in baseline_rows):
        failures.append(_quality_issue("baseline_unreconstructable", "Baseline trials were present but no valid baseline responses were reconstructable.", f"baseline_rows={len(baseline_rows)}"))

    timing_rows = [row for row in event_rows if str(row.get("event_type") or "").strip() in {"trial_start", "tactile_onset", "trial_end"}]
    tactile_events = [row for row in event_rows if str(row.get("event_type") or "").strip() == "tactile_onset"]
    if final_rows and event_rows and not tactile_events:
        failures.append(_quality_issue("missing_tactile_timing_anchors", "No primary tactile timing anchors were logged.", "tactile_onset_events=0"))
    qualities = [str(row.get("timestamp_quality") or "").strip().lower() for row in timing_rows if str(row.get("timestamp_quality") or "").strip()]
    fallback_count = sum(1 for quality in qualities if "fallback" in quality or "invalid" in quality)
    fallback_rate = fallback_count / len(qualities) if qualities else 0.0
    metrics["timing_quality_rows"] = len(qualities)
    metrics["timing_fallback_rate"] = fallback_rate
    if qualities and fallback_rate > 0.20:
        failures.append(_quality_issue("timing_fallback_rate_above_20pct", "Timing-critical event rows show pervasive fallback or invalid timestamp quality.", f"fallback_rate={fallback_rate:.3f}; timing_quality_rows={len(qualities)}"))

    accepted_rts = [_as_float(row.get("rt_ms"), math.nan) for row in final_rows if _truthy(row.get("hit")) and row.get("rt_ms") not in (None, "")]
    accepted_rts = [value for value in accepted_rts if math.isfinite(value)]
    if accepted_rts:
        median_rt = statistics.median(accepted_rts)
        metrics["median_accepted_rt_ms"] = median_rt
        if median_rt < 150.0 or median_rt > 2500.0:
            failures.append(_quality_issue("accepted_rt_median_outside_compliance_range", "Accepted RT median suggests likely noncompliance.", f"median_rt_ms={median_rt:.3f}"))

    mouse_events = [row for row in event_rows if str(row.get("event_type") or "").strip() == "mouse_click" and _truthy(row.get("during_playback", True))]
    selected_clicks = {str(row.get("click_event_id") or "").strip() for row in final_rows if str(row.get("click_event_id") or "").strip()}
    extra_clicks = [row for row in mouse_events if str(row.get("event_id") or "").strip() not in selected_clicks]
    tactile_count = len(tactile_events) or len(final_rows)
    extra_click_ratio = len(extra_clicks) / max(1, tactile_count)
    metrics["extra_playback_click_ratio"] = extra_click_ratio
    if tactile_count and extra_click_ratio > 0.50:
        failures.append(_quality_issue("extra_playback_clicks_above_50pct", "Extra playback clicks exceed 50% of tactile trial count.", f"extra_clicks={len(extra_clicks)}; tactile_count={tactile_count}"))
    anticipatory = _anticipatory_target_click_count(mouse_events, tactile_events)
    anticipatory_ratio = anticipatory / max(1, tactile_count)
    metrics["anticipatory_target_click_ratio"] = anticipatory_ratio
    if tactile_count and anticipatory_ratio > 0.15:
        failures.append(_quality_issue("anticipatory_target_clicks_above_15pct", "Anticipatory target clicks exceed 15% of tactile trials.", f"anticipatory_clicks={anticipatory}; tactile_count={tactile_count}"))

    if not failures and not result.condition_lens_curve_rows:
        warnings.append(_quality_issue("no_condition_lens_curves", "Condition-lens curves were unavailable, so the GUI will fall back to legacy review tables.", "condition_lens_curve_rows=0"))

    status = QUALITY_FAIL if failures else QUALITY_PASS
    return {
        "schema": RECORDING_QUALITY_GATE_SCHEMA,
        "status": status,
        "primary_reason": failures[0]["message"] if failures else "No serious exclusion criteria were triggered.",
        "failures": failures,
        "warnings": warnings,
        "metrics": metrics,
        "criteria": {
            "overall_hit_rate_min": 0.70,
            "condition_cell_hit_rate_min": 0.50,
            "condition_cell_distinct_soa_min": 4,
            "condition_cell_valid_audio_tactile_min": 8,
            "timing_fallback_rate_max": 0.20,
            "accepted_rt_median_range_ms": [150.0, 2500.0],
            "anticipatory_target_click_ratio_max": 0.15,
            "extra_playback_click_ratio_max": 0.50,
        },
    }


def _build_basic_assumption_checks(response_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows = _assumption_valid_rt_rows(response_rows)
    proximity = _assumption_proximity_payload(rows)
    for row in rows:
        row["proximity"] = proximity["row_scores"].get(row["_assumption_row_id"], math.nan)
    rows = [row for row in rows if math.isfinite(_as_float(row.get("proximity"), math.nan))]
    baseline_rows = [row for row in rows if row.get("trial_type") == "Baseline"]
    audio_tactile_rows = [row for row in rows if row.get("trial_type") == "Audio-Tactile"]
    baseline = _baseline_assumption_check(baseline_rows)
    pps = _pps_assumption_check(baseline_rows, audio_tactile_rows)
    return {
        "schema": BASIC_ASSUMPTION_CHECKS_SCHEMA,
        "alpha": 0.05,
        "outcome": "log_rt_ms",
        "statistical_note": (
            "Pragmatic post-run QC only: baseline green means no detected SOA/proximity trend at alpha=.05; "
            "PPS green means the baseline-adjusted audio-tactile proximity interaction has the predicted negative sign "
            "with one-sided p<.05."
        ),
        "proximity_coding": {key: value for key, value in proximity.items() if key != "row_scores"},
        "nuisance_terms_requested": ["part_number", "respiratory_phase", "noise_type"],
        "rows_used": {
            "baseline": len(baseline_rows),
            "audio_tactile": len(audio_tactile_rows),
            "total": len(rows),
        },
        "baseline_assumption": baseline,
        "peripersonal_space_assumption": pps,
    }


def _baseline_assumption_check(rows: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = _assumption_coverage(rows)
    payload = _assumption_base_payload(
        "Baseline Assumption",
        "baseline_log_rt_proximity_slope",
        "log(RT_ms) ~ proximity + nuisance_terms",
        coverage,
    )
    insufficient = _baseline_coverage_failure(coverage)
    if insufficient:
        payload.update(
            {
                "status": QUALITY_FAIL,
                "passed": False,
                "reason_code": insufficient,
                "summary": _baseline_insufficient_summary(coverage),
            }
        )
        return payload
    y = np.asarray([math.log(float(row["rt_ms"])) for row in rows], dtype=float)
    model = _fit_assumption_ols(
        rows,
        y,
        primary_columns=[("proximity", lambda row: _as_float(row.get("proximity"), math.nan))],
    )
    payload["model"] = _assumption_model_payload(model)
    if model.get("error"):
        payload.update(
            {
                "status": QUALITY_FAIL,
                "passed": False,
                "reason_code": str(model.get("error")),
                "summary": str(model.get("message") or "Baseline proximity slope was not estimable."),
            }
        )
        return payload
    if int(model.get("df_resid", 0)) < 2:
        payload.update(
            {
                "status": QUALITY_FAIL,
                "passed": False,
                "reason_code": "residual_df_low",
                "summary": "Insufficient baseline residual degrees of freedom for the proximity slope check.",
            }
        )
        return payload
    stats = _assumption_coefficient_stats(model, "proximity")
    p_value = stats.get("p_two_sided")
    significant = p_value is not None and float(p_value) < 0.05
    payload.update(
        {
            "beta": stats.get("beta"),
            "se": stats.get("se"),
            "t": stats.get("t"),
            "p_two_sided": p_value,
            "df_resid": model.get("df_resid"),
            "included_nuisance_terms": model.get("included_nuisance_terms", []),
            "dropped_nuisance_terms": model.get("dropped_nuisance_terms", []),
            "status": QUALITY_FAIL if significant else QUALITY_PASS,
            "passed": not significant,
            "reason_code": "baseline_proximity_significant" if significant else "baseline_proximity_not_significant",
            "summary": (
                "Baseline RTs showed a significant proximity/SOA trend, so the pragmatic flatness check failed."
                if significant
                else "No significant baseline proximity/SOA trend was detected; pragmatic baseline flatness was accepted."
            ),
        }
    )
    return payload


def _pps_assumption_check(
    baseline_rows: list[dict[str, Any]],
    audio_tactile_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = list(baseline_rows) + list(audio_tactile_rows)
    coverage = {
        "baseline": _assumption_coverage(baseline_rows),
        "audio_tactile": _assumption_coverage(audio_tactile_rows),
        "combined": _assumption_coverage(rows),
    }
    payload = _assumption_base_payload(
        "Peripersonal Space Assumption",
        "audio_tactile_by_proximity_interaction",
        "log(RT_ms) ~ pps_trial + proximity + pps_trial:proximity + nuisance_terms",
        coverage,
    )
    insufficient = _pps_coverage_failure(coverage)
    if insufficient:
        payload.update(
            {
                "status": QUALITY_FAIL,
                "passed": False,
                "reason_code": insufficient,
                "summary": _pps_insufficient_summary(coverage),
            }
        )
        return payload
    y = np.asarray([math.log(float(row["rt_ms"])) for row in rows], dtype=float)
    model = _fit_assumption_ols(
        rows,
        y,
        primary_columns=[
            ("pps_trial", lambda row: 1.0 if row.get("trial_type") == "Audio-Tactile" else 0.0),
            ("proximity", lambda row: _as_float(row.get("proximity"), math.nan)),
            (
                "pps_trial:proximity",
                lambda row: (1.0 if row.get("trial_type") == "Audio-Tactile" else 0.0)
                * _as_float(row.get("proximity"), math.nan),
            ),
        ],
    )
    payload["model"] = _assumption_model_payload(model)
    if model.get("error"):
        payload.update(
            {
                "status": QUALITY_FAIL,
                "passed": False,
                "reason_code": str(model.get("error")),
                "summary": str(model.get("message") or "The PPS proximity interaction was not estimable."),
            }
        )
        return payload
    if int(model.get("df_resid", 0)) < 2:
        payload.update(
            {
                "status": QUALITY_FAIL,
                "passed": False,
                "reason_code": "residual_df_low",
                "summary": "Insufficient residual degrees of freedom for the PPS interaction check.",
            }
        )
        return payload
    stats = _assumption_coefficient_stats(model, "pps_trial:proximity")
    p_value = stats.get("p_one_sided_negative")
    beta = stats.get("beta")
    predicted_sign = beta is not None and float(beta) < 0.0
    significant = p_value is not None and float(p_value) < 0.05
    effects = _pps_far_to_near_effects(model, rows)
    passed = bool(predicted_sign and significant)
    if not predicted_sign:
        reason_code = "interaction_sign_opposite_or_zero"
        summary = "The audio-tactile proximity interaction did not have the predicted negative sign."
    elif not significant:
        reason_code = "interaction_not_significant"
        summary = "The audio-tactile proximity interaction had the predicted sign but was not significant at one-sided p<.05."
    else:
        reason_code = "interaction_predicted_significant"
        summary = "Audio-tactile RTs sped up from far to near more than baseline, with the predicted significant interaction."
    payload.update(
        {
            "interaction_beta": beta,
            "interaction_se": stats.get("se"),
            "interaction_t": stats.get("t"),
            "p_one_sided_negative": p_value,
            "p_two_sided": stats.get("p_two_sided"),
            "df_resid": model.get("df_resid"),
            "included_nuisance_terms": model.get("included_nuisance_terms", []),
            "dropped_nuisance_terms": model.get("dropped_nuisance_terms", []),
            "baseline_slope_beta": effects.get("baseline_slope_beta"),
            "audio_tactile_slope_beta": effects.get("audio_tactile_slope_beta"),
            "baseline_far_to_near_speedup_ms": effects.get("baseline_far_to_near_speedup_ms"),
            "audio_tactile_far_to_near_speedup_ms": effects.get("audio_tactile_far_to_near_speedup_ms"),
            "pps_far_to_near_gain_ms": effects.get("pps_far_to_near_gain_ms"),
            "status": QUALITY_PASS if passed else QUALITY_FAIL,
            "passed": passed,
            "reason_code": reason_code,
            "summary": summary,
        }
    )
    return payload


def _assumption_base_payload(label: str, test: str, formula: str, coverage: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "test": test,
        "formula": formula,
        "status": QUALITY_FAIL,
        "passed": False,
        "alpha": 0.05,
        "coverage": coverage,
        "summary": "Insufficient evidence for this assumption check.",
    }


def _baseline_coverage_failure(coverage: dict[str, Any]) -> str:
    if int(coverage.get("n", 0)) < 6:
        return "baseline_valid_rt_count_low"
    if int(coverage.get("distinct_soa_count", 0)) < 2:
        return "baseline_distinct_soa_count_low"
    return ""


def _pps_coverage_failure(coverage: dict[str, Any]) -> str:
    baseline = dict(coverage.get("baseline") or {})
    audio = dict(coverage.get("audio_tactile") or {})
    if int(audio.get("n", 0)) < 12:
        return "audio_tactile_valid_rt_count_low"
    if int(audio.get("distinct_soa_count", 0)) < 3:
        return "audio_tactile_distinct_soa_count_low"
    if int(baseline.get("n", 0)) < 6:
        return "baseline_valid_rt_count_low"
    if int(baseline.get("distinct_soa_count", 0)) < 2:
        return "baseline_distinct_soa_count_low"
    return ""


def _baseline_insufficient_summary(coverage: dict[str, Any]) -> str:
    return (
        "Insufficient baseline coverage for the pragmatic flatness check "
        f"(valid RTs={coverage.get('n', 0)}, SOA levels={coverage.get('distinct_soa_count', 0)})."
    )


def _pps_insufficient_summary(coverage: dict[str, Any]) -> str:
    baseline = dict(coverage.get("baseline") or {})
    audio = dict(coverage.get("audio_tactile") or {})
    return (
        "Insufficient coverage for the PPS interaction check "
        f"(audio-tactile valid RTs={audio.get('n', 0)}, audio-tactile SOA levels={audio.get('distinct_soa_count', 0)}, "
        f"baseline valid RTs={baseline.get('n', 0)}, baseline SOA levels={baseline.get('distinct_soa_count', 0)})."
    )


def _assumption_valid_rt_rows(response_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, source in enumerate(response_rows):
        if not _primary_analysis_included(source):
            continue
        trial_type = _assumption_trial_type(source.get("trial_type"))
        if trial_type not in {"Baseline", "Audio-Tactile"}:
            continue
        if "hit" in source and source.get("hit") not in (None, "") and not _truthy(source.get("hit")):
            continue
        rt = _as_float(source.get("rt_ms"), math.nan)
        soa = _as_float(source.get("soa_ms"), math.nan)
        if not (math.isfinite(rt) and rt > 0.0 and math.isfinite(soa)):
            continue
        row = dict(source)
        row["_assumption_row_id"] = f"row_{index}"
        row["trial_type"] = trial_type
        row["rt_ms"] = float(rt)
        row["soa_ms"] = float(soa)
        rows.append(row)
    return rows


def _assumption_trial_type(value: Any) -> str:
    text = str(value or "").strip()
    lowered = re.sub(r"[\s_]+", "-", text.lower())
    if lowered == "baseline":
        return "Baseline"
    if lowered in {"audio-tactile", "audiotactile"} or ("audio" in lowered and "tactile" in lowered):
        return "Audio-Tactile"
    return text


def _assumption_proximity_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    distance_key = _assumption_distance_key(rows)
    row_scores: dict[str, float] = {}
    if distance_key:
        logs = [_assumption_log_distance(row, distance_key) for row in rows]
        finite_logs = [value for value in logs if math.isfinite(value)]
        mean_log = statistics.mean(finite_logs)
        sd_log = statistics.pstdev(finite_logs)
        if sd_log > 0:
            for row, value in zip(rows, logs):
                row_scores[str(row["_assumption_row_id"])] = -((value - mean_log) / sd_log)
            return {
                "method": "-z(log(distance_cm))",
                "distance_column": distance_key,
                "levels": sorted({float(_as_float(row.get(distance_key), math.nan)) for row in rows if math.isfinite(_as_float(row.get(distance_key), math.nan))}),
                "row_scores": row_scores,
            }
    soas = sorted({float(row["soa_ms"]) for row in rows if math.isfinite(_as_float(row.get("soa_ms"), math.nan))})
    center = (len(soas) - 1) / 2.0 if soas else 0.0
    scores = {soa: float(index - center) for index, soa in enumerate(soas)}
    for row in rows:
        row_scores[str(row["_assumption_row_id"])] = scores.get(float(row["soa_ms"]), math.nan)
    return {
        "method": "centered_soa_rank",
        "orientation": "sorted_unique_soa_as_far_to_near",
        "levels": soas,
        "scores_by_soa_ms": {str(_assumption_soa_key(soa)): score for soa, score in scores.items()},
        "row_scores": row_scores,
    }


def _assumption_distance_key(rows: list[dict[str, Any]]) -> str:
    for key in ("distance_cm", "source_distance_cm", "sound_distance_cm", "distance_at_touch_cm"):
        values = [_as_float(row.get(key), math.nan) for row in rows]
        finite = [value for value in values if math.isfinite(value) and value > 0.0]
        if rows and len(finite) == len(rows) and len({round(value, 9) for value in finite}) >= 2:
            return key
    return ""


def _assumption_log_distance(row: dict[str, Any], key: str) -> float:
    value = _as_float(row.get(key), math.nan)
    return math.log(value) if math.isfinite(value) and value > 0.0 else math.nan


def _assumption_soa_key(value: float) -> int | float:
    return int(value) if float(value).is_integer() else float(value)


def _assumption_coverage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    soas = sorted({float(row["soa_ms"]) for row in rows if math.isfinite(_as_float(row.get("soa_ms"), math.nan))})
    proximities = sorted({float(row["proximity"]) for row in rows if math.isfinite(_as_float(row.get("proximity"), math.nan))})
    by_soa: dict[str, int] = {}
    for row in rows:
        soa = _as_float(row.get("soa_ms"), math.nan)
        if math.isfinite(soa):
            key = str(_assumption_soa_key(soa))
            by_soa[key] = by_soa.get(key, 0) + 1
    return {
        "n": len(rows),
        "distinct_soa_count": len(soas),
        "distinct_proximity_count": len(proximities),
        "soas_ms": [_assumption_soa_key(soa) for soa in soas],
        "counts_by_soa_ms": by_soa,
    }


def _fit_assumption_ols(
    rows: list[dict[str, Any]],
    y: np.ndarray,
    *,
    primary_columns: list[tuple[str, Any]],
) -> dict[str, Any]:
    try:
        X, names, term_by_column, included_terms, dropped_terms = _assumption_design_matrix(rows, primary_columns)
    except ValueError as exc:
        return {"error": "primary_design_not_estimable", "message": str(exc)}
    n = int(X.shape[0])
    rank = int(np.linalg.matrix_rank(X))
    if rank < X.shape[1]:
        return {
            "error": "primary_design_rank_deficient",
            "message": "Primary assumption terms were rank-deficient after nuisance terms were dropped.",
            "rank": rank,
            "column_count": int(X.shape[1]),
            "n": n,
            "included_nuisance_terms": included_terms,
            "dropped_nuisance_terms": dropped_terms,
        }
    df_resid = n - rank
    try:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        residual = y - X @ beta
        xtx_inv = np.linalg.pinv(X.T @ X)
        leverage = np.sum((X @ xtx_inv) * X, axis=1)
        denom = np.maximum(1.0 - leverage, 1e-8)
        hc3_weights = (residual / denom) ** 2
        meat = X.T @ (X * hc3_weights[:, None])
        covariance = xtx_inv @ meat @ xtx_inv
    except Exception as exc:  # noqa: BLE001 - this is a QC artifact, so return a readable failure.
        return {"error": "ols_fit_failed", "message": str(exc)}
    coefficients = {name: float(value) for name, value in zip(names, beta)}
    covariance_diag = {name: float(covariance[index, index]) for index, name in enumerate(names)}
    return {
        "n": n,
        "rank": rank,
        "column_count": int(X.shape[1]),
        "df_resid": int(df_resid),
        "columns": names,
        "term_by_column": term_by_column,
        "coefficients": coefficients,
        "covariance_diag": covariance_diag,
        "included_nuisance_terms": included_terms,
        "dropped_nuisance_terms": dropped_terms,
    }


def _assumption_design_matrix(
    rows: list[dict[str, Any]],
    primary_columns: list[tuple[str, Any]],
) -> tuple[np.ndarray, list[str], list[str], list[str], list[str]]:
    if not rows:
        raise ValueError("No valid rows were available.")
    primary_data: list[np.ndarray] = []
    primary_names: list[str] = []
    for name, getter in primary_columns:
        values = np.asarray([float(getter(row)) for row in rows], dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError(f"Primary column {name} contained non-finite values.")
        primary_names.append(name)
        primary_data.append(values)
    nuisance_specs = _assumption_nuisance_columns(rows)
    included_terms = [term for term, _names, _columns in nuisance_specs]
    dropped_terms: list[str] = []
    while True:
        X, names, term_by_column = _assumption_matrix_from_terms(primary_names, primary_data, nuisance_specs, included_terms)
        if np.linalg.matrix_rank(X) >= X.shape[1]:
            return X, names, term_by_column, included_terms, dropped_terms
        droppable = next((term for term in ("noise_type", "respiratory_phase", "part_number") if term in included_terms), "")
        if not droppable:
            return X, names, term_by_column, included_terms, dropped_terms
        included_terms = [term for term in included_terms if term != droppable]
        dropped_terms.append(droppable)


def _assumption_nuisance_columns(rows: list[dict[str, Any]]) -> list[tuple[str, list[str], list[np.ndarray]]]:
    specs: list[tuple[str, list[str], list[np.ndarray]]] = []
    for term in ("part_number", "respiratory_phase", "noise_type"):
        values = [_assumption_nuisance_value(row, term) for row in rows]
        levels = sorted({value for value in values if value})
        if len(levels) < 2:
            continue
        names: list[str] = []
        columns: list[np.ndarray] = []
        for level in levels[1:]:
            names.append(f"{term}[{level}]")
            columns.append(np.asarray([1.0 if value == level else 0.0 for value in values], dtype=float))
        if columns:
            specs.append((term, names, columns))
    return specs


def _assumption_nuisance_value(row: dict[str, Any], term: str) -> str:
    if term == "part_number":
        part = _as_int(row.get("part_number"), None)
        return "" if part is None else f"Part {part}"
    return str(row.get(term) or "").strip()


def _assumption_matrix_from_terms(
    primary_names: list[str],
    primary_data: list[np.ndarray],
    nuisance_specs: list[tuple[str, list[str], list[np.ndarray]]],
    included_terms: list[str],
) -> tuple[np.ndarray, list[str], list[str]]:
    n = len(primary_data[0]) if primary_data else sum(1 for _ in [])
    columns = [np.ones(n, dtype=float), *primary_data]
    names = ["intercept", *primary_names]
    term_by_column = ["intercept", *primary_names]
    included = set(included_terms)
    for term, nuisance_names, nuisance_columns in nuisance_specs:
        if term not in included:
            continue
        columns.extend(nuisance_columns)
        names.extend(nuisance_names)
        term_by_column.extend([term] * len(nuisance_columns))
    return np.column_stack(columns), names, term_by_column


def _assumption_model_payload(model: dict[str, Any]) -> dict[str, Any]:
    if model.get("error"):
        return dict(model)
    return {
        "n": model.get("n"),
        "rank": model.get("rank"),
        "column_count": model.get("column_count"),
        "df_resid": model.get("df_resid"),
        "columns": model.get("columns", []),
        "included_nuisance_terms": model.get("included_nuisance_terms", []),
        "dropped_nuisance_terms": model.get("dropped_nuisance_terms", []),
    }


def _assumption_coefficient_stats(model: dict[str, Any], name: str) -> dict[str, float | None]:
    coefficients = dict(model.get("coefficients") or {})
    covariance_diag = dict(model.get("covariance_diag") or {})
    beta = _as_float(coefficients.get(name), math.nan)
    variance = _as_float(covariance_diag.get(name), math.nan)
    df = int(model.get("df_resid", 0) or 0)
    if not math.isfinite(beta) or df <= 0:
        return {"beta": None, "se": None, "t": None, "p_two_sided": None, "p_one_sided_negative": None}
    if not math.isfinite(variance) or variance < 0.0:
        return {"beta": beta, "se": None, "t": None, "p_two_sided": None, "p_one_sided_negative": None}
    se = math.sqrt(max(0.0, variance))
    if se <= 1e-12:
        t_value = 0.0 if abs(beta) <= 1e-12 else math.copysign(math.inf, beta)
    else:
        t_value = beta / se
    if math.isinf(t_value):
        p_two = 0.0
        p_one_negative = 0.0 if t_value < 0 else 1.0
    else:
        p_two = float(2.0 * scipy_stats.t.sf(abs(t_value), df))
        p_one_negative = float(scipy_stats.t.cdf(t_value, df))
    return {
        "beta": float(beta),
        "se": float(se),
        "t": float(t_value),
        "p_two_sided": p_two,
        "p_one_sided_negative": p_one_negative,
    }


def _pps_far_to_near_effects(model: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, float | None]:
    coefficients = dict(model.get("coefficients") or {})
    intercept = _as_float(coefficients.get("intercept"), math.nan)
    pps_beta = _as_float(coefficients.get("pps_trial"), math.nan)
    proximity_beta = _as_float(coefficients.get("proximity"), math.nan)
    interaction_beta = _as_float(coefficients.get("pps_trial:proximity"), math.nan)
    proximities = [_as_float(row.get("proximity"), math.nan) for row in rows]
    proximities = [value for value in proximities if math.isfinite(value)]
    if len(proximities) < 2 or not all(math.isfinite(value) for value in (intercept, pps_beta, proximity_beta, interaction_beta)):
        return {
            "baseline_slope_beta": None,
            "audio_tactile_slope_beta": None,
            "baseline_far_to_near_speedup_ms": None,
            "audio_tactile_far_to_near_speedup_ms": None,
            "pps_far_to_near_gain_ms": None,
        }
    far = min(proximities)
    near = max(proximities)
    baseline_slope = proximity_beta
    audio_slope = proximity_beta + interaction_beta
    baseline_far = math.exp(intercept + baseline_slope * far)
    baseline_near = math.exp(intercept + baseline_slope * near)
    audio_far = math.exp(intercept + pps_beta + audio_slope * far)
    audio_near = math.exp(intercept + pps_beta + audio_slope * near)
    baseline_speedup = baseline_far - baseline_near
    audio_speedup = audio_far - audio_near
    return {
        "baseline_slope_beta": float(baseline_slope),
        "audio_tactile_slope_beta": float(audio_slope),
        "baseline_far_to_near_speedup_ms": float(baseline_speedup),
        "audio_tactile_far_to_near_speedup_ms": float(audio_speedup),
        "pps_far_to_near_gain_ms": float(audio_speedup - baseline_speedup),
    }


def _quality_condition_cells(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    cells: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        part_number = _as_int(row.get("part_number"), None)
        part_label = _part_display_label(row) if part_number is not None else "All parts"
        state = _state_label(row)
        cells.setdefault(_condition_lens_scope(part_label, state), []).append(row)
    return cells


def _quality_issue(code: str, message: str, evidence: str) -> dict[str, Any]:
    return {"code": code, "message": message, "evidence": evidence}


def _anticipatory_target_click_count(mouse_events: list[dict[str, Any]], tactile_events: list[dict[str, Any]]) -> int:
    if not mouse_events or not tactile_events:
        return 0
    tactile_sorted = sorted(tactile_events, key=lambda row: _as_float(row.get("unix_time"), math.inf))
    count = 0
    for click in mouse_events:
        if not _truthy(click.get("in_target", True)):
            continue
        click_time = _as_float(click.get("unix_time"), math.nan)
        if not math.isfinite(click_time):
            continue
        for tactile in tactile_sorted:
            tactile_time = _as_float(tactile.get("unix_time"), math.nan)
            if not math.isfinite(tactile_time):
                continue
            if 0.0 < tactile_time - click_time <= 0.15 and _same_trial_context(tactile, click):
                count += 1
                break
    return count


def _build_pps_curves(
    response_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    curve_rows: list[dict[str, Any]] = []
    fit_rows: list[dict[str, Any]] = []
    model_fit_rows: list[dict[str, Any]] = []
    model_comparison_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for aggregation_mode in (AGGREGATION_SEPARATE_PARTS, AGGREGATION_POOL_PARTS):
        mode_curves, mode_fits, mode_model_fits, mode_comparisons, mode_warnings = _build_pps_curves_for_mode(
            response_rows,
            aggregation_mode=aggregation_mode,
        )
        curve_rows.extend(mode_curves)
        fit_rows.extend(mode_fits)
        model_fit_rows.extend(mode_model_fits)
        model_comparison_rows.extend(mode_comparisons)
        warnings.extend(mode_warnings)
    return curve_rows, fit_rows, model_fit_rows, model_comparison_rows, warnings


def _build_pps_curves_for_mode(
    response_rows: list[dict[str, Any]],
    *,
    aggregation_mode: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    baseline = _baseline_means(response_rows, aggregation_mode=aggregation_mode)
    audio_rows = [row for row in response_rows if row.get("trial_type") == "Audio-Tactile" and row.get("rt_ms") not in (None, "")]
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in audio_rows:
        key = _analysis_context(row, aggregation_mode=aggregation_mode)
        groups.setdefault(key, []).append(row)

    curve_rows: list[dict[str, Any]] = []
    fit_rows: list[dict[str, Any]] = []
    model_fit_rows: list[dict[str, Any]] = []
    model_comparison_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for key, rows in sorted(
        groups.items(),
        key=lambda item: (_part_number_from_label(item[0][0]) or 999, tuple(str(part) for part in item[0])),
    ):
        part_label, condition, phase, noise = key
        part_number = _part_number_from_label(part_label)
        by_soa: dict[int, list[float]] = {}
        for row in rows:
            soa = _as_int(row.get("soa_ms"), None)
            rt = _as_float(row.get("rt_ms"), math.nan)
            if soa is None or not math.isfinite(rt):
                continue
            by_soa.setdefault(soa, []).append(rt)
        xs = []
        ys = []
        metric = "facilitation_ms"
        for soa, values in sorted(by_soa.items()):
            mean_rt = statistics.mean(values)
            rt_sd = statistics.stdev(values) if len(values) > 1 else 0.0
            rt_sem = rt_sd / math.sqrt(len(values)) if len(values) > 1 else 0.0
            base_stats = _lookup_baseline(baseline, part_label, condition, phase, noise)
            base_rt = base_stats.get("mean") if base_stats is not None else None
            facilitation = base_rt - mean_rt if base_rt is not None else None
            baseline_sem = _as_float((base_stats or {}).get("sem"), math.nan)
            facilitation_sem = math.sqrt(rt_sem**2 + baseline_sem**2) if facilitation is not None and math.isfinite(baseline_sem) else math.nan
            baseline_sd = _as_float((base_stats or {}).get("sd"), math.nan)
            facilitation_sd = math.sqrt(rt_sd**2 + baseline_sd**2) if facilitation is not None and math.isfinite(baseline_sd) else math.nan
            y = facilitation if facilitation is not None else mean_rt
            if facilitation is None:
                metric = "mean_rt_ms"
            curve_rows.append(
                {
                    "scope": _scope(part_label, condition, phase, noise),
                    "aggregation_mode": aggregation_mode,
                    "aggregation_label": _aggregation_label(aggregation_mode),
                    "part_number": "" if part_number is None else part_number,
                    "condition": condition,
                    "respiratory_phase": phase,
                    "noise_type": noise,
                    "soa_ms": soa,
                    "n": len(values),
                    "mean_rt_ms": mean_rt,
                    "sd_rt_ms": rt_sd if len(values) > 1 else "",
                    "sem_rt_ms": rt_sem if len(values) > 1 else "",
                    "baseline_mean_rt_ms": "" if base_rt is None else base_rt,
                    "baseline_sd_rt_ms": "" if not math.isfinite(baseline_sd) or base_rt is None else baseline_sd,
                    "baseline_sem_rt_ms": "" if not math.isfinite(baseline_sem) or base_rt is None else baseline_sem,
                    "baseline_n": "" if base_rt is None else base_stats.get("n", ""),
                    "baseline_source_soas_ms": "" if base_rt is None else base_stats.get("source_soas_ms", ""),
                    "baseline_correction_method": "" if base_rt is None else BASELINE_CORRECTION_METHOD_CONDITION_MEAN_POOLED_SOA,
                    "facilitation_ms": "" if facilitation is None else facilitation,
                    "facilitation_sd_ms": "" if not math.isfinite(facilitation_sd) else facilitation_sd,
                    "facilitation_sem_ms": "" if not math.isfinite(facilitation_sem) else facilitation_sem,
                    "fit_metric": metric,
                    "fit_metric_sd_ms": rt_sd if metric == "mean_rt_ms" and len(values) > 1 else ("" if not math.isfinite(facilitation_sd) else facilitation_sd),
                    "fit_metric_sem_ms": rt_sem if metric == "mean_rt_ms" and len(values) > 1 else ("" if not math.isfinite(facilitation_sem) else facilitation_sem),
                }
            )
            xs.append(float(soa))
            ys.append(float(y))
        scope = _scope(part_label, condition, phase, noise)
        model_rows = _fit_model_family(
            np.asarray(xs),
            np.asarray(ys),
            scope=scope,
            part_label=part_label,
            condition=condition,
            phase=phase,
            noise=noise,
            metric=metric,
            aggregation_mode=aggregation_mode,
        )
        model_fit_rows.extend(model_rows)
        if model_rows:
            best = sorted(model_rows, key=lambda row: _as_float(row.get("aic"), math.inf))[0]
            model_comparison_rows.append(
                {
                    "scope": scope,
                    "aggregation_mode": aggregation_mode,
                    "aggregation_label": _aggregation_label(aggregation_mode),
                    "part_number": "" if part_number is None else part_number,
                    "condition": condition,
                    "respiratory_phase": phase,
                    "noise_type": noise,
                    "fit_metric": metric,
                    "n_points": best.get("n_points", ""),
                    "best_model": best.get("model", ""),
                    "best_aic": best.get("aic", ""),
                    "best_aicc": best.get("aicc", ""),
                    "best_r2": best.get("r2", ""),
                    "candidate_models": ";".join(str(row.get("model", "")) for row in sorted(model_rows, key=lambda item: str(item.get("model", "")))),
                }
            )
        if len(xs) >= 4:
            fit = _fit_sigmoid(np.asarray(xs), np.asarray(ys))
            if fit:
                fit_rows.append(
                    {
                        "scope": scope,
                        "aggregation_mode": aggregation_mode,
                        "aggregation_label": _aggregation_label(aggregation_mode),
                        "part_number": "" if part_number is None else part_number,
                        "condition": condition,
                        "respiratory_phase": phase,
                        "noise_type": noise,
                        "fit_metric": metric,
                        **fit,
                    }
                )
            else:
                warnings.append(f"Sigmoid fit did not converge for {scope}.")
        elif xs:
            warnings.append(f"Only {len(xs)} SOA point(s) for {scope}; sigmoid fit skipped.")
    return curve_rows, fit_rows, model_fit_rows, model_comparison_rows, warnings


def _baseline_means(response_rows: list[dict[str, Any]], *, aggregation_mode: str) -> dict[tuple[Any, ...], dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[tuple[float, int]]] = {}
    for row in response_rows:
        if row.get("trial_type") != "Baseline" or row.get("rt_ms") in (None, ""):
            continue
        rt = _as_float(row.get("rt_ms"), math.nan)
        soa = _as_int(row.get("soa_ms"), None)
        if soa is None or not math.isfinite(rt):
            continue
        part_label, condition, phase, noise = _analysis_context(row, aggregation_mode=aggregation_mode)
        for key in _baseline_lookup_keys(part_label, condition, phase, noise):
            groups.setdefault(key, []).append((rt, soa))
    return {key: _baseline_mean_sd_sem(values) for key, values in groups.items() if values}


def _lookup_baseline(
    baseline: dict[tuple[Any, ...], dict[str, Any]],
    part_label: Any,
    condition: Any,
    phase: Any,
    noise: Any,
) -> dict[str, Any] | None:
    for key in _baseline_lookup_keys(part_label, condition, phase, noise):
        if key in baseline:
            return baseline[key]
    return None


def _mean_sd_sem(values: list[float]) -> dict[str, float]:
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    sem = sd / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"mean": mean, "sd": sd, "sem": sem, "n": float(len(values))}


def _baseline_mean_sd_sem(samples: list[tuple[float, int]]) -> dict[str, Any]:
    values = [float(value) for value, _soa in samples]
    stats = _mean_sd_sem(values)
    source_soas = sorted({int(soa) for _value, soa in samples})
    return {
        **stats,
        "n": len(values),
        "source_soas_ms": ";".join(str(soa) for soa in source_soas),
    }


def _fit_sigmoid(x: np.ndarray, y: np.ndarray) -> dict[str, float] | None:
    if len(x) < 4 or len(set(x.tolist())) < 4:
        return None
    lower0 = float(np.min(y))
    upper0 = float(np.max(y))
    x00 = float(np.median(x))
    direction = 1.0 if y[-1] >= y[0] else -1.0
    p0 = [lower0, upper0, x00, direction * 0.004]
    bounds = ([-np.inf, -np.inf, float(np.min(x)), -1.0], [np.inf, np.inf, float(np.max(x)), 1.0])
    try:
        with py_warnings.catch_warnings():
            py_warnings.simplefilter("ignore", OptimizeWarning)
            params, _ = curve_fit(_sigmoid, x, y, p0=p0, bounds=bounds, maxfev=20000)
    except Exception:
        return None
    predicted = _sigmoid(x, *params)
    metrics = _fit_metrics(y, predicted, parameter_count=4)
    return {
        "lower": float(params[0]),
        "upper": float(params[1]),
        "pps_boundary_soa_ms": float(params[2]),
        "slope": float(params[3]),
        **metrics,
    }


def _fit_model_family(
    x: np.ndarray,
    y: np.ndarray,
    *,
    scope: str,
    part_label: Any,
    condition: Any,
    phase: Any,
    noise: Any,
    metric: str,
    aggregation_mode: str,
) -> list[dict[str, Any]]:
    if len(x) < 2 or len(set(x.tolist())) < 2:
        return []
    rows: list[dict[str, Any]] = []
    linear = _fit_linear_model(x, y)
    if linear is not None:
        rows.append(
            _model_row(
                "linear",
                linear,
                scope,
                part_label,
                condition,
                phase,
                noise,
                metric,
                len(x),
                aggregation_mode=aggregation_mode,
                parameter_count=2,
            )
        )
    if np.all(x > 0):
        logarithmic = _fit_log_model(x, y)
        if logarithmic is not None:
            rows.append(
                _model_row(
                    "logarithmic_decay",
                    logarithmic,
                    scope,
                    part_label,
                    condition,
                    phase,
                    noise,
                    metric,
                    len(x),
                    aggregation_mode=aggregation_mode,
                    parameter_count=2,
                )
            )
    sigmoid = _fit_sigmoid(x, y)
    if sigmoid is not None:
        rows.append(
            _model_row(
                "sigmoid",
                sigmoid,
                scope,
                part_label,
                condition,
                phase,
                noise,
                metric,
                len(x),
                aggregation_mode=aggregation_mode,
                parameter_count=4,
            )
        )
    return rows


def _fit_linear_model(x: np.ndarray, y: np.ndarray) -> dict[str, float] | None:
    try:
        slope, intercept = np.polyfit(x, y, 1)
    except Exception:
        return None
    predicted = intercept + slope * x
    metrics = _fit_metrics(y, predicted, parameter_count=2)
    return {"intercept": float(intercept), "slope": float(slope), **metrics}


def _fit_log_model(x: np.ndarray, y: np.ndarray) -> dict[str, float] | None:
    try:
        slope, intercept = np.polyfit(np.log(x), y, 1)
    except Exception:
        return None
    predicted = intercept + slope * np.log(x)
    metrics = _fit_metrics(y, predicted, parameter_count=2)
    return {"intercept": float(intercept), "log_slope": float(slope), **metrics}


def _fit_metrics(y: np.ndarray, predicted: np.ndarray, *, parameter_count: int) -> dict[str, float]:
    residual = y - predicted
    rss = float(np.sum(residual**2))
    n = int(len(y))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - (rss / ss_tot) if ss_tot else 1.0
    rmse = math.sqrt(rss / n) if n else math.nan
    aic = n * math.log(max(rss / max(n, 1), 1e-12)) + (2 * parameter_count) if n else math.inf
    aicc = _aicc(aic, n, parameter_count)
    return {"rss": rss, "rmse": rmse, "r2": r2, "aic": aic, "aicc": "" if not math.isfinite(aicc) else aicc}


def _aicc(aic: float, n: int, parameter_count: int) -> float:
    if not math.isfinite(aic) or n <= parameter_count + 1:
        return math.inf
    return aic + (2.0 * parameter_count * (parameter_count + 1.0)) / (n - parameter_count - 1.0)


def _row_aicc(row: dict[str, Any]) -> float:
    aicc = _as_float(row.get("aicc"), math.nan)
    if math.isfinite(aicc):
        return aicc
    aic = _as_float(row.get("aic"), math.inf)
    n = _as_int(row.get("n_points"), None)
    parameter_count = _as_int(row.get("parameter_count"), None)
    if n is None or parameter_count is None:
        return math.inf
    return _aicc(aic, int(n), int(parameter_count))


def _model_row(
    model: str,
    fit: dict[str, Any],
    scope: str,
    part_label: Any,
    condition: Any,
    phase: Any,
    noise: Any,
    metric: str,
    n_points: int,
    *,
    aggregation_mode: str,
    parameter_count: int,
) -> dict[str, Any]:
    part_number = _part_number_from_label(part_label)
    return {
        "scope": scope,
        "aggregation_mode": aggregation_mode,
        "aggregation_label": _aggregation_label(aggregation_mode),
        "part_number": "" if part_number is None else part_number,
        "condition": condition,
        "respiratory_phase": phase,
        "noise_type": noise,
        "fit_metric": metric,
        "model": model,
        "n_points": n_points,
        "parameter_count": parameter_count,
        **fit,
    }


def _sigmoid(x: np.ndarray, lower: float, upper: float, x0: float, slope: float) -> np.ndarray:
    return lower + (upper - lower) / (1.0 + np.exp(-slope * (x - x0)))


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()}) if rows else ["empty"]
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return str(value)


def _analysis_context(row: dict[str, Any], *, aggregation_mode: str) -> tuple[str, str, str, str]:
    part_number = _as_int(row.get("part_number"), None)
    raw_condition = row.get("condition", "")
    condition = _condition_without_part_label(raw_condition)
    phase = str(row.get("respiratory_phase", "") or "").strip()
    noise = str(row.get("noise_type", "") or "").strip()
    if aggregation_mode == AGGREGATION_POOL_PARTS:
        part_label = "All parts" if part_number is not None else ""
    else:
        part_label = _part_display_label(row) if part_number is not None else ""
    return part_label, condition, phase, noise


def _part_display_label(row: dict[str, Any]) -> str:
    part_number = _as_int(row.get("part_number"), None)
    label = str(row.get("part_label") or row.get("Part_Label") or "").strip()
    if label and part_number is not None:
        return f"{label} (Part {part_number})"
    if label:
        return label
    return f"Part {part_number}" if part_number is not None else "All parts"


def _condition_without_part_label(value: Any) -> str:
    text = str(value or "").strip()
    return "" if re.fullmatch(r"part\s+\d+", text, flags=re.IGNORECASE) else text


def _part_number_from_label(value: Any) -> int | None:
    match = re.search(r"\bpart\s+(\d+)\b", str(value or "").strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _aggregation_label(value: str) -> str:
    if value == AGGREGATION_POOL_PARTS:
        return "Pool parts"
    if value == CONDITION_LENS_TWO_BY_TWO:
        return "2 x 2"
    if value == CONDITION_LENS_PART:
        return "Part lens"
    if value == CONDITION_LENS_STATE:
        return "State lens"
    if value == CONDITION_LENS_OVERALL:
        return "Overall lens"
    return "Separate parts"


def _baseline_lookup_keys(part_label: Any, condition: Any, phase: Any, noise: Any) -> list[tuple[Any, ...]]:
    part = str(part_label or "").strip()
    cond = str(condition or "").strip()
    ph = str(phase or "").strip()
    ns = str(noise or "").strip()
    keys = [
        (part, cond, ph, ns),
        (part, cond, ph, ""),
        (part, "", ph, ""),
        (part, "", "", ""),
        ("", cond, ph, ns),
        ("", cond, ph, ""),
        ("", "", ph, ""),
        ("", "", "", ""),
    ]
    return list(dict.fromkeys(keys))


def _scope(part_label: Any, condition: Any, phase: Any, noise: Any) -> str:
    parts = [str(part) for part in (part_label, condition, phase, noise) if str(part).strip()]
    return " / ".join(parts) or "All audio-tactile"


def _as_row(event: Any) -> dict[str, Any]:
    if hasattr(event, "as_flat_dict"):
        return dict(event.as_flat_dict())
    if isinstance(event, dict):
        row = dict(event)
        payload = row.pop("payload", None)
        if isinstance(payload, dict):
            row.update(payload)
        return row
    raise TypeError(f"Unsupported event type: {type(event)!r}")


def _field(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return ""


def _trial_requires_choice_scoring(row: dict[str, Any]) -> bool:
    correct_response = str(_field(row, "correct_response", "Correct_Response") or "").strip()
    response_choice_set = str(_field(row, "response_choice_set", "Response_Choice_Set") or "").strip()
    if not correct_response or not response_choice_set:
        return False
    mode = _response_choice_token(_field(row, "response_mode", "Response_Mode"))
    if not mode:
        return True
    return bool(
        {
            "choice",
            "discrimination",
            "localization",
            "localisation",
            "tactile_discrimination",
            "tactile_localization",
            "tactile_localisation",
            "spatial_choice",
            "extinction",
            "cross_modal_extinction",
            "cross_modal_extinction_report",
            "tactile_extinction",
            "tactile_report",
            "percept_report",
            "forced_choice",
            "two_alternative_forced_choice",
            "2afc",
        }.intersection({mode, *mode.split("_")})
    )


def _response_choice_from_click(click: dict[str, Any] | None, row: dict[str, Any]) -> str:
    if click is None:
        return ""
    explicit = _field(click, "response_choice", "Response_Choice", "choice", "Choice", "button_label", "Button_Label")
    if explicit not in (None, ""):
        return str(explicit).strip()
    choices = _split_response_choice_set(_field(row, "response_choice_set", "Response_Choice_Set"))
    if not choices:
        return ""
    if len(choices) == 1:
        return choices[0]
    policy = _response_choice_token(_field(row, "response_scoring_policy", "Response_Scoring_Policy"))
    mode = _response_choice_token(_field(row, "response_mode", "Response_Mode"))
    if "mouse_quadrant" in policy or ("quadrant" in policy and "mouse" in policy):
        return _choice_by_mouse_quadrant(click, choices)
    if "mouse_y_split" in policy or ("vertical" in policy and "mouse" in policy):
        axis_value = _as_float(click.get("y"), math.nan)
        low_side = "up"
        high_side = "down"
    elif "mouse_x_split" in policy or "mouse" in policy or "localization" in mode or "localisation" in mode:
        axis_value = _as_float(click.get("x"), math.nan)
        low_side = "left"
        high_side = "right"
    else:
        axis_value = _as_float(click.get("x"), math.nan)
        low_side = "left"
        high_side = "right"
    if not math.isfinite(axis_value):
        return ""
    threshold = 0.5 if abs(axis_value) <= 1.0 else 500.0
    side = low_side if axis_value < threshold else high_side
    labelled = _choice_by_side(choices, side)
    if labelled:
        return labelled
    return choices[0] if axis_value < threshold else choices[1]


def _choice_by_mouse_quadrant(click: dict[str, Any], choices: list[str]) -> str:
    x = _as_float(click.get("x"), math.nan)
    y = _as_float(click.get("y"), math.nan)
    if not math.isfinite(x) or not math.isfinite(y):
        return ""
    x_threshold = 0.5 if abs(x) <= 1.0 else 500.0
    y_threshold = 0.5 if abs(y) <= 1.0 else 500.0
    if x < x_threshold and y < y_threshold:
        label = "left"
    elif x >= x_threshold and y < y_threshold:
        label = "right"
    elif x < x_threshold and y >= y_threshold:
        label = "bilateral"
    else:
        label = "none"
    labelled = _choice_by_report_label(choices, label)
    if labelled:
        return labelled
    index = {"left": 0, "right": 1, "bilateral": 2, "none": 3}[label]
    return choices[index] if index < len(choices) else choices[-1]


def _split_response_choice_set(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*(?:\||/|,|;)\s*", text) if part.strip()]


def _choice_by_side(choices: list[str], side: str) -> str:
    side_token = _response_choice_token(side)
    for choice in choices:
        token = _response_choice_token(choice)
        if token == side_token or side_token in token.split("_"):
            return choice
    return ""


def _choice_by_report_label(choices: list[str], label: str) -> str:
    aliases = {
        "left": {"left", "left_side", "contralesional_left", "ipsilesional_left"},
        "right": {"right", "right_side", "contralesional_right", "ipsilesional_right"},
        "bilateral": {"bilateral", "both", "both_sides", "left_and_right", "right_and_left", "double"},
        "none": {"none", "no_touch", "absent", "nothing", "no_report", "not_detected", "undetected"},
    }
    wanted = aliases.get(label, {_response_choice_token(label)})
    for choice in choices:
        token = _response_choice_token(choice)
        parts = set(token.split("_"))
        if token in wanted or wanted.intersection(parts):
            return choice
    return ""


def _response_choice_correctness(observed: Any, expected: Any) -> bool | None:
    expected_token = _response_choice_token(expected)
    if not expected_token:
        return None
    observed_token = _response_choice_token(observed)
    if not observed_token:
        return False
    return observed_token == expected_token


def _response_choice_token(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _trial_requires_response(row: dict[str, Any]) -> bool:
    expected = _field(
        row,
        "expected_response",
        "Expected_Response",
        "response_expected",
        "Response_Expected",
        "required_response",
        "Required_Response",
    )
    decision = _response_expectation_decision(expected)
    if decision is not None:
        return decision
    for value in (
        _field(
            row,
            "target_role",
            "Target_Role",
            "go_nogo_role",
            "Go_NoGo_Role",
            "stimulus_role",
            "Stimulus_Role",
            "tactile_role",
            "Tactile_Role",
        ),
        _field(
            row,
            "response_rule",
            "Response_Rule",
            "response_mapping",
            "Response_Mapping",
            "task_response_rule",
            "Task_Response_Rule",
        ),
        _field(row, "trial_type", "Trial_Type"),
        _field(row, "family", "Family"),
    ):
        decision = _response_expectation_decision(value)
        if decision is not None:
            return decision
    return True


def _response_expectation_decision(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    token = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    if not token:
        return None
    if token in {
        "0",
        "false",
        "no",
        "none",
        "withhold",
        "withhold_response",
        "no_response",
        "noresponse",
        "no_go",
        "nogo",
        "no_target",
        "not_target",
        "non_target",
        "nontarget",
        "strong",
        "strong_nontarget",
        "strong_non_target",
        "distractor",
    }:
        return False
    if token in {
        "1",
        "true",
        "yes",
        "respond",
        "response",
        "click",
        "button_press",
        "go",
        "target",
        "weak",
        "weak_target",
        "weak_go",
    }:
        return True
    parts = set(token.split("_"))
    has_no_marker = (
        "no_response" in token
        or "no_target" in token
        or "non_target" in token
        or "nontarget" in token
        or parts.intersection({"withhold", "nogo", "not", "none", "strong", "distractor", "nontarget"})
    )
    strong_response_marker = "respond" in parts or "click" in parts or "go" in parts or "weak" in parts
    has_response_marker = strong_response_marker or ("target" in parts and not has_no_marker)
    if has_no_marker and strong_response_marker:
        return None
    if has_no_marker:
        return False
    if has_response_marker:
        return True
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _coerce_analysis_ready_row(row: dict[str, Any]) -> dict[str, Any]:
    boolean_fields = {
        "hit",
        "original_hit",
        "rescued_in_topup",
        "topup_hit",
        "is_topup",
        "primary_analysis_included",
        "in_target",
        "during_playback",
        "catch_trial",
        "baseline_trial",
        "response_required",
        "response_choice_correct",
        "tactile_waveform_generated",
        "external_trigger_required",
    }
    for field in boolean_fields:
        if field in row and row[field] not in (None, ""):
            row[field] = _truthy(row[field])
    if "hit" not in row or row.get("hit") in (None, ""):
        outcome = str(row.get("outcome") or row.get("Outcome") or "").strip().lower()
        if outcome:
            row["hit"] = outcome == "hit"
    if "trial_type" not in row and "Trial_Type" in row:
        row["trial_type"] = row.get("Trial_Type")
    if "respiratory_phase" not in row and "Respiratory_Phase" in row:
        row["respiratory_phase"] = row.get("Respiratory_Phase")
    if "noise_type" not in row and "Noise_Type" in row:
        row["noise_type"] = row.get("Noise_Type")
    if "sequence_labels" not in row and "Sequence_Labels" in row:
        row["sequence_labels"] = row.get("Sequence_Labels")
    if "sequence_variant_key" not in row and "Sequence_Variant_Key" in row:
        row["sequence_variant_key"] = row.get("Sequence_Variant_Key")
    if "iti_policy" not in row and "ITI_Policy" in row:
        row["iti_policy"] = row.get("ITI_Policy")
    if "iti_ms" not in row and "ITI_ms" in row:
        row["iti_ms"] = row.get("ITI_ms")
    if "foreperiod_ms" not in row and "Foreperiod_ms" in row:
        row["foreperiod_ms"] = row.get("Foreperiod_ms")
    if "hazard_control_policy" not in row and "Hazard_Control_Policy" in row:
        row["hazard_control_policy"] = row.get("Hazard_Control_Policy")
    if "expectancy_control_role" not in row and "Expectancy_Control_Role" in row:
        row["expectancy_control_role"] = row.get("Expectancy_Control_Role")
    if "soa_ms" not in row and "SOA_ms" in row:
        row["soa_ms"] = row.get("SOA_ms")
    if "response_mode" not in row and "Response_Mode" in row:
        row["response_mode"] = row.get("Response_Mode")
    if "response_choice_set" not in row and "Response_Choice_Set" in row:
        row["response_choice_set"] = row.get("Response_Choice_Set")
    if "correct_response" not in row and "Correct_Response" in row:
        row["correct_response"] = row.get("Correct_Response")
    if "response_scoring_policy" not in row and "Response_Scoring_Policy" in row:
        row["response_scoring_policy"] = row.get("Response_Scoring_Policy")
    if "observed_response_choice" not in row and "Observed_Response_Choice" in row:
        row["observed_response_choice"] = row.get("Observed_Response_Choice")
    if "response_choice_correct" not in row and "Response_Choice_Correct" in row:
        row["response_choice_correct"] = row.get("Response_Choice_Correct")
    if "response_capture_device" not in row and "Response_Capture_Device" in row:
        row["response_capture_device"] = row.get("Response_Capture_Device")
    if "response_input_modality" not in row and "Response_Input_Modality" in row:
        row["response_input_modality"] = row.get("Response_Input_Modality")
    if "tool_condition" not in row and "Tool_Condition" in row:
        row["tool_condition"] = row.get("Tool_Condition")
    if "locomotion_condition" not in row and "Locomotion_Condition" in row:
        row["locomotion_condition"] = row.get("Locomotion_Condition")
    if "multisensory_trial_family" not in row and "Multisensory_Trial_Family" in row:
        row["multisensory_trial_family"] = row.get("Multisensory_Trial_Family")
    if "exteroceptive_modality_set" not in row and "Exteroceptive_Modality_Set" in row:
        row["exteroceptive_modality_set"] = row.get("Exteroceptive_Modality_Set")
    if "visual_stimulus_type" not in row and "Visual_Stimulus_Type" in row:
        row["visual_stimulus_type"] = row.get("Visual_Stimulus_Type")
    if "visual_motion_profile" not in row and "Visual_Motion_Profile" in row:
        row["visual_motion_profile"] = row.get("Visual_Motion_Profile")
    if "visual_start_distance_cm" not in row and "Visual_Start_Distance_cm" in row:
        row["visual_start_distance_cm"] = row.get("Visual_Start_Distance_cm")
    if "visual_end_distance_cm" not in row and "Visual_End_Distance_cm" in row:
        row["visual_end_distance_cm"] = row.get("Visual_End_Distance_cm")
    if "visual_speed_cm_s" not in row and "Visual_Speed_cm_s" in row:
        row["visual_speed_cm_s"] = row.get("Visual_Speed_cm_s")
    if "visual_duration_ms" not in row and "Visual_Duration_ms" in row:
        row["visual_duration_ms"] = row.get("Visual_Duration_ms")
    if "visual_renderer_engine" not in row and "Visual_Renderer_Engine" in row:
        row["visual_renderer_engine"] = row.get("Visual_Renderer_Engine")
    if "visual_display_device" not in row and "Visual_Display_Device" in row:
        row["visual_display_device"] = row.get("Visual_Display_Device")
    if "mixed_reality_context" not in row and "Mixed_Reality_Context" in row:
        row["mixed_reality_context"] = row.get("Mixed_Reality_Context")
    if "body_rendering_mode" not in row and "Body_Rendering_Mode" in row:
        row["body_rendering_mode"] = row.get("Body_Rendering_Mode")
    if "audiovisual_synchrony_policy" not in row and "Audiovisual_Synchrony_Policy" in row:
        row["audiovisual_synchrony_policy"] = row.get("Audiovisual_Synchrony_Policy")
    if "mixed_reality_equivalence_boundary" not in row and "Mixed_Reality_Equivalence_Boundary" in row:
        row["mixed_reality_equivalence_boundary"] = row.get("Mixed_Reality_Equivalence_Boundary")
    if "voice_key_enabled" not in row and "Voice_Key_Enabled" in row:
        row["voice_key_enabled"] = row.get("Voice_Key_Enabled")
    if "voice_key_response_label" not in row and "Voice_Key_Response_Label" in row:
        row["voice_key_response_label"] = row.get("Voice_Key_Response_Label")
    if "voice_key_threshold" not in row and "Voice_Key_Threshold" in row:
        row["voice_key_threshold"] = row.get("Voice_Key_Threshold")
    if "voice_key_latency_correction_ms" not in row and "Voice_Key_Latency_Correction_ms" in row:
        row["voice_key_latency_correction_ms"] = row.get("Voice_Key_Latency_Correction_ms")
    if "tactile_stimulation_modality" not in row and "Tactile_Stimulation_Modality" in row:
        row["tactile_stimulation_modality"] = row.get("Tactile_Stimulation_Modality")
    if "tactile_calibration_method" not in row and "Tactile_Calibration_Method" in row:
        row["tactile_calibration_method"] = row.get("Tactile_Calibration_Method")
    if "tactile_threshold_reference" not in row and "Tactile_Threshold_Reference" in row:
        row["tactile_threshold_reference"] = row.get("Tactile_Threshold_Reference")
    if "tactile_intensity" not in row and "Tactile_Intensity" in row:
        row["tactile_intensity"] = row.get("Tactile_Intensity")
    if "tactile_intensity_unit" not in row and "Tactile_Intensity_Unit" in row:
        row["tactile_intensity_unit"] = row.get("Tactile_Intensity_Unit")
    if "tactile_pulse_duration_ms" not in row and "Tactile_Pulse_Duration_ms" in row:
        row["tactile_pulse_duration_ms"] = row.get("Tactile_Pulse_Duration_ms")
    if "electrical_stimulator_model" not in row and "Electrical_Stimulator_Model" in row:
        row["electrical_stimulator_model"] = row.get("Electrical_Stimulator_Model")
    if "electrical_electrode_site" not in row and "Electrical_Electrode_Site" in row:
        row["electrical_electrode_site"] = row.get("Electrical_Electrode_Site")
    if "spatial_coordinate_frame" not in row and "Spatial_Coordinate_Frame" in row:
        row["spatial_coordinate_frame"] = row.get("Spatial_Coordinate_Frame")
    if "body_anchor" not in row and "Body_Anchor" in row:
        row["body_anchor"] = row.get("Body_Anchor")
    if "body_part" not in row and "Body_Part" in row:
        row["body_part"] = row.get("Body_Part")
    if "body_side" not in row and "Body_Side" in row:
        row["body_side"] = row.get("Body_Side")
    if "spatial_hemifield" not in row and "Spatial_Hemifield" in row:
        row["spatial_hemifield"] = row.get("Spatial_Hemifield")
    if "body_relative_axis" not in row and "Body_Relative_Axis" in row:
        row["body_relative_axis"] = row.get("Body_Relative_Axis")
    if "auditory_trajectory_family" not in row and "Auditory_Trajectory_Family" in row:
        row["auditory_trajectory_family"] = row.get("Auditory_Trajectory_Family")
    if "auditory_trajectory_direction" not in row and "Auditory_Trajectory_Direction" in row:
        row["auditory_trajectory_direction"] = row.get("Auditory_Trajectory_Direction")
    if "trajectory_coordinate_frame" not in row and "Trajectory_Coordinate_Frame" in row:
        row["trajectory_coordinate_frame"] = row.get("Trajectory_Coordinate_Frame")
    if "trajectory_start_hemifield" not in row and "Trajectory_Start_Hemifield" in row:
        row["trajectory_start_hemifield"] = row.get("Trajectory_Start_Hemifield")
    if "trajectory_end_hemifield" not in row and "Trajectory_End_Hemifield" in row:
        row["trajectory_end_hemifield"] = row.get("Trajectory_End_Hemifield")
    if "trajectory_start_distance_cm" not in row and "Trajectory_Start_Distance_cm" in row:
        row["trajectory_start_distance_cm"] = row.get("Trajectory_Start_Distance_cm")
    if "trajectory_end_distance_cm" not in row and "Trajectory_End_Distance_cm" in row:
        row["trajectory_end_distance_cm"] = row.get("Trajectory_End_Distance_cm")
    if "trajectory_start_azimuth_deg" not in row and "Trajectory_Start_Azimuth_deg" in row:
        row["trajectory_start_azimuth_deg"] = row.get("Trajectory_Start_Azimuth_deg")
    if "trajectory_end_azimuth_deg" not in row and "Trajectory_End_Azimuth_deg" in row:
        row["trajectory_end_azimuth_deg"] = row.get("Trajectory_End_Azimuth_deg")
    if "spatial_renderer_engine" not in row and "Spatial_Renderer_Engine" in row:
        row["spatial_renderer_engine"] = row.get("Spatial_Renderer_Engine")
    if "spatial_renderer_version" not in row and "Spatial_Renderer_Version" in row:
        row["spatial_renderer_version"] = row.get("Spatial_Renderer_Version")
    if "hrtf_database" not in row and "HRTF_Database" in row:
        row["hrtf_database"] = row.get("HRTF_Database")
    if "hrtf_subject_id" not in row and "HRTF_Subject_ID" in row:
        row["hrtf_subject_id"] = row.get("HRTF_Subject_ID")
    if "hrtf_filter_id" not in row and "HRTF_Filter_ID" in row:
        row["hrtf_filter_id"] = row.get("HRTF_Filter_ID")
    if "hrtf_near_field_compensation" not in row and "HRTF_Near_Field_Compensation" in row:
        row["hrtf_near_field_compensation"] = row.get("HRTF_Near_Field_Compensation")
    if "source_asset_equivalence" not in row and "Source_Asset_Equivalence" in row:
        row["source_asset_equivalence"] = row.get("Source_Asset_Equivalence")
    if "renderer_equivalence_boundary" not in row and "Renderer_Equivalence_Boundary" in row:
        row["renderer_equivalence_boundary"] = row.get("Renderer_Equivalence_Boundary")
    if "rt_ms" not in row and "RT_ms" in row:
        row["rt_ms"] = row.get("RT_ms")
    if "participant_id" not in row and "Participant_ID" in row:
        row["participant_id"] = row.get("Participant_ID")
    if "part_number" not in row and "Part_Number" in row:
        row["part_number"] = row.get("Part_Number")
    if "part_label" not in row and "Part_Label" in row:
        row["part_label"] = row.get("Part_Label")
    return row


def _primary_analysis_included(row: dict[str, Any]) -> bool:
    value = _field(row, "primary_analysis_included", "Primary_Analysis_Included")
    if value in (None, ""):
        return not (_truthy(_field(row, "is_topup", "Is_Topup")) and str(_field(row, "topup_role", "Topup_Role")).strip().lower() == "filler")
    return _truthy(value)


def _as_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _as_int(value: Any, default: Any) -> Any:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _fmt(value: Any, digits: int) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"
