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
from typing import Any, Iterable

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit


DEFAULT_MIN_RESPONSE_RT_S = 0.1
DEFAULT_MAX_RESPONSE_RT_S = 4.0
AGGREGATION_SEPARATE_PARTS = "separate_parts"
AGGREGATION_POOL_PARTS = "pooled_parts"
DATA_BEHAVIOR_SCHEMA = "pps-exploratory-data-behavior.v1"

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
    result = SessionAnalysisResult()
    result.response_rows = _pair_tactile_responses(rows, min_rt_s=min_rt_s, max_rt_s=max_rt_s)
    result.final_outcome_rows = _build_final_outcomes(result.response_rows)
    analysis_rows = result.final_outcome_rows or result.response_rows
    result.summary_rows = _summarize_responses(analysis_rows)
    result.curve_rows, result.fit_rows, result.model_fit_rows, result.model_comparison_rows, curve_warnings = _build_pps_curves(analysis_rows)
    result.warnings.extend(curve_warnings)
    if not result.response_rows:
        result.warnings.append("No tactile response rows could be reconstructed from the event stream.")
    result.data_behavior_rows, result.exploratory_quality_summary = _build_data_behavior_review(result, rows)
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
        click = None
        for candidate in clicks:
            click_time = _as_float(candidate.get("unix_time"), 0.0)
            if candidate.get("event_id") in used_click_ids:
                continue
            if not _same_trial_context(tactile, candidate):
                continue
            if onset + min_rt_s <= click_time <= response_deadline:
                click = candidate
                used_click_ids.add(candidate.get("event_id"))
                break
        row = _response_base(tactile)
        row["tactile_unix_time"] = onset
        row["hit"] = click is not None
        if click is not None:
            click_time = _as_float(click.get("unix_time"), 0.0)
            row["click_unix_time"] = click_time
            row["rt_ms"] = (click_time - onset) * 1000.0
            row["click_x"] = click.get("x", "")
            row["click_y"] = click.get("y", "")
            row["click_event_id"] = click.get("event_id", "")
        else:
            row["click_unix_time"] = ""
            row["rt_ms"] = ""
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
        "noise_type": _field(event, "noise_type", "Noise_Type"),
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
    for key, rows in sorted(groups.items(), key=lambda item: tuple(str(part) for part in item[0])):
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
            base_stats = _lookup_baseline(baseline, part_label, condition, phase, noise, soa)
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


def _baseline_means(response_rows: list[dict[str, Any]], *, aggregation_mode: str) -> dict[tuple[Any, ...], dict[str, float]]:
    groups: dict[tuple[Any, ...], list[float]] = {}
    for row in response_rows:
        if row.get("trial_type") != "Baseline" or row.get("rt_ms") in (None, ""):
            continue
        rt = _as_float(row.get("rt_ms"), math.nan)
        soa = _as_int(row.get("soa_ms"), None)
        if soa is None or not math.isfinite(rt):
            continue
        part_label, condition, phase, noise = _analysis_context(row, aggregation_mode=aggregation_mode)
        for key in _baseline_lookup_keys(part_label, condition, phase, noise, soa):
            groups.setdefault(key, []).append(rt)
    return {key: _mean_sd_sem(values) for key, values in groups.items() if values}


def _lookup_baseline(
    baseline: dict[tuple[Any, ...], dict[str, float]],
    part_label: Any,
    condition: Any,
    phase: Any,
    noise: Any,
    soa: int,
) -> dict[str, float] | None:
    for key in _baseline_lookup_keys(part_label, condition, phase, noise, soa):
        if key in baseline:
            return baseline[key]
    return None


def _mean_sd_sem(values: list[float]) -> dict[str, float]:
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    sem = sd / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return {"mean": mean, "sd": sd, "sem": sem, "n": float(len(values))}


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
    return {"rss": rss, "rmse": rmse, "r2": r2, "aic": aic}


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
        part_label = f"Part {part_number}" if part_number is not None else ""
    return part_label, condition, phase, noise


def _condition_without_part_label(value: Any) -> str:
    text = str(value or "").strip()
    return "" if re.fullmatch(r"part\s+\d+", text, flags=re.IGNORECASE) else text


def _part_number_from_label(value: Any) -> int | None:
    match = re.fullmatch(r"part\s+(\d+)", str(value or "").strip(), flags=re.IGNORECASE)
    if not match:
        return None
    return int(match.group(1))


def _aggregation_label(value: str) -> str:
    if value == AGGREGATION_POOL_PARTS:
        return "Pool parts"
    return "Separate parts"


def _baseline_lookup_keys(part_label: Any, condition: Any, phase: Any, noise: Any, soa: int) -> list[tuple[Any, ...]]:
    part = str(part_label or "").strip()
    cond = str(condition or "").strip()
    ph = str(phase or "").strip()
    ns = str(noise or "").strip()
    keys = [
        (part, cond, ph, ns, soa),
        (part, cond, ph, "", soa),
        (part, "", ph, "", soa),
        (part, "", "", "", soa),
        ("", cond, ph, ns, soa),
        ("", cond, ph, "", soa),
        ("", "", ph, "", soa),
        ("", "", "", "", soa),
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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


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
