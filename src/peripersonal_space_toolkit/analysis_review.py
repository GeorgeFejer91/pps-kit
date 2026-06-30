"""Helpers for the post-run PPS analysis review window."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


MODEL_BEST = "best"
MODEL_COMPARE_ALL = "compare_all"
MODEL_SIGMOID = "sigmoid"
MODEL_LINEAR = "linear"
MODEL_LOGARITHMIC_DECAY = "logarithmic_decay"
PARTS_SEPARATE = "separate_parts"
PARTS_POOLED = "pooled_parts"
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
VIEW_DATA_BEHAVIOR = "data_behavior"
VIEW_MODEL_FITS = "model_fits"
VIEW_RESPONSES = "responses"
VIEW_TIMING_EVIDENCE = "timing_evidence"
VIEW_TOPUP = "topup"
VIEW_ARTIFACTS = "artifacts"
METRIC_FACILITATION = "facilitation_ms"
METRIC_MEAN_RT = "mean_rt_ms"
METRIC_HIT_RATE = "hit_rate"
METRIC_RESPONSE_COUNT = "response_count"
BASELINE_CORRECTION_METHOD_CONDITION_MEAN_POOLED_SOA = "condition_mean_pooled_soa"
SOURCE_FINAL = "final_analysis"
SOURCE_ORIGINAL = "original_trials"
SOURCE_TOPUP = "topup_rescues"
SOURCE_EXCLUDED = "excluded_logged_events"
GROUPING_SCOPE = "scope"
GROUPING_PHASE = "respiratory_phase"
GROUPING_NOISE = "noise_source"
GROUPING_DISTANCE_BIN = "soa_distance_bin"

SIGNAL_EXPECTED = "Expected pattern"
SIGNAL_MIXED = "Mixed / ambiguous"
SIGNAL_UNUSUAL = "Unusual pattern"
SIGNAL_INSUFFICIENT = "Insufficient evidence"
SIGNAL_TECHNICAL = "Technical caveat"

MODEL_ORDER = (MODEL_BEST, MODEL_COMPARE_ALL, MODEL_SIGMOID, MODEL_LINEAR, MODEL_LOGARITHMIC_DECAY)
MODEL_LABELS = {
    MODEL_BEST: "Best model",
    MODEL_COMPARE_ALL: "Compare all three",
    MODEL_SIGMOID: "Sigmoid",
    MODEL_LINEAR: "Linear",
    MODEL_LOGARITHMIC_DECAY: "Logarithmic decay",
}
MODEL_FIT_ORDER = (MODEL_SIGMOID, MODEL_LINEAR, MODEL_LOGARITHMIC_DECAY)
QUICK_MODEL_ORDER = (MODEL_SIGMOID, MODEL_LOGARITHMIC_DECAY, MODEL_LINEAR)
CONDITION_SERIES_COLORS = ("#246b55", "#4b5fa8", "#a4631b", "#8c2f2f", "#5f5a8a", "#2d6f8a")
PART_AGGREGATION_ORDER = (PARTS_SEPARATE, PARTS_POOLED)
PART_AGGREGATION_LABELS = {
    PARTS_SEPARATE: "Separate parts",
    PARTS_POOLED: "Pool parts",
}
VIEW_ORDER = (VIEW_DATA_BEHAVIOR, VIEW_MODEL_FITS, VIEW_RESPONSES, VIEW_TIMING_EVIDENCE, VIEW_TOPUP, VIEW_ARTIFACTS)
VIEW_LABELS = {
    VIEW_DATA_BEHAVIOR: "Data Behavior",
    VIEW_MODEL_FITS: "Model Fits",
    VIEW_RESPONSES: "Responses",
    VIEW_TIMING_EVIDENCE: "Timing Evidence",
    VIEW_TOPUP: "Top-Up",
    VIEW_ARTIFACTS: "Artifacts",
}
METRIC_ORDER = (METRIC_FACILITATION, METRIC_MEAN_RT, METRIC_HIT_RATE, METRIC_RESPONSE_COUNT)
METRIC_LABELS = {
    METRIC_FACILITATION: "Facilitation",
    METRIC_MEAN_RT: "Mean RT",
    METRIC_HIT_RATE: "Hit rate",
    METRIC_RESPONSE_COUNT: "Response count",
}
SOURCE_ORDER = (SOURCE_FINAL, SOURCE_ORIGINAL, SOURCE_TOPUP, SOURCE_EXCLUDED)
SOURCE_LABELS = {
    SOURCE_FINAL: "Final analysis",
    SOURCE_ORIGINAL: "Original trials only",
    SOURCE_TOPUP: "Top-up rescues only",
    SOURCE_EXCLUDED: "Logged but excluded events",
}
GROUPING_ORDER = (GROUPING_SCOPE, GROUPING_PHASE, GROUPING_NOISE, GROUPING_DISTANCE_BIN)
GROUPING_LABELS = {
    GROUPING_SCOPE: "Current scope",
    GROUPING_PHASE: "By respiratory phase",
    GROUPING_NOISE: "By noise/source",
    GROUPING_DISTANCE_BIN: "By SOA/distance bin",
}


@dataclass
class AnalysisReviewData:
    """Loaded analysis-review data for one completed runner session."""

    session_dir: Path | None = None
    dataset_id: str = ""
    dataset_label: str = ""
    dataset_kind: str = ""
    participant_id: str = ""
    quality_label: str = "Participant Run Quality"
    pool_included_count: int = 0
    pool_excluded_count: int = 0
    curve_rows: list[dict[str, Any]] = field(default_factory=list)
    model_fit_rows: list[dict[str, Any]] = field(default_factory=list)
    model_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_curve_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_model_fit_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_model_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    condition_lens_triage_summary: dict[str, Any] = field(default_factory=dict)
    recording_quality_gate: dict[str, Any] = field(default_factory=dict)
    assumption_checks: dict[str, Any] = field(default_factory=dict)
    summary_rows: list[dict[str, Any]] = field(default_factory=list)
    participant_trial_rows: list[dict[str, Any]] = field(default_factory=list)
    response_rows: list[dict[str, Any]] = field(default_factory=list)
    final_outcome_rows: list[dict[str, Any]] = field(default_factory=list)
    timing_qc_rows: list[dict[str, Any]] = field(default_factory=list)
    event_rows: list[dict[str, Any]] = field(default_factory=list)
    data_behavior_rows: list[dict[str, Any]] = field(default_factory=list)
    exploratory_quality_summary: dict[str, Any] = field(default_factory=dict)
    output_paths: dict[str, Path] = field(default_factory=dict)
    summary_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def has_analysis_tables(self) -> bool:
        return bool(
            self.curve_rows
            or self.model_fit_rows
            or self.model_comparison_rows
            or self.condition_lens_curve_rows
            or self.condition_lens_model_fit_rows
            or self.condition_lens_model_comparison_rows
            or self.summary_rows
        )

    @property
    def scopes(self) -> list[str]:
        return scopes_for_part_mode(self, self.default_part_mode)

    @property
    def part_modes(self) -> list[str]:
        modes = {_row_part_mode(row) for row in [*self.curve_rows, *self.model_fit_rows, *self.model_comparison_rows]}
        ordered = [mode for mode in PART_AGGREGATION_ORDER if mode in modes]
        extras = sorted(mode for mode in modes if mode not in PART_AGGREGATION_ORDER)
        return ordered + extras or [PARTS_SEPARATE]

    @property
    def default_part_mode(self) -> str:
        return PARTS_SEPARATE if PARTS_SEPARATE in self.part_modes else self.part_modes[0]


def load_analysis_review_data(
    analysis_outputs: Mapping[str, Any] | None,
    *,
    session_dir: str | Path | None = None,
    summary_text: str = "",
    dataset_metadata: Mapping[str, Any] | None = None,
) -> AnalysisReviewData:
    """Load existing immediate-analysis outputs for read-only review."""

    root = Path(session_dir) if session_dir not in (None, "") else None
    outputs = dict(analysis_outputs or {})
    metadata = dict(dataset_metadata or {})
    data = AnalysisReviewData(
        session_dir=root,
        dataset_id=str(metadata.get("dataset_id") or ""),
        dataset_label=str(metadata.get("dataset_label") or ""),
        dataset_kind=str(metadata.get("dataset_kind") or ""),
        participant_id=str(metadata.get("participant_id") or ""),
        quality_label=(
            "Participant Pool Quality"
            if str(metadata.get("dataset_kind") or "") == "participant_pool"
            else "Participant Run Quality"
        ),
        pool_included_count=_as_int(metadata.get("pool_included_count"), 0),
        pool_excluded_count=_as_int(metadata.get("pool_excluded_count"), 0),
        summary_text=str(summary_text or "").strip(),
    )

    curves_path = _output_path(outputs, "curves", root, "*_pps_curve_points.csv")
    fits_path = _output_path(outputs, "model_fits", root, "*_model_fits.csv")
    comparison_path = _output_path(outputs, "model_fit_comparison", root, "*_model_fit_comparison.csv")
    condition_curves_path = _output_path(outputs, "condition_lens_curves", root, "*_condition_lens_curve_points.csv")
    condition_fits_path = _output_path(outputs, "condition_lens_model_fits", root, "*_condition_lens_model_fits.csv")
    condition_comparison_path = _output_path(outputs, "condition_lens_model_fit_comparison", root, "*_condition_lens_model_fit_comparison.csv")
    condition_summary_path = _output_path(outputs, "condition_lens_triage_summary", root, "condition_lens_triage_summary.json")
    quality_gate_path = _output_path(outputs, "recording_quality_gate", root, "recording_quality_gate.v1.json")
    assumption_checks_path = _output_path(outputs, "basic_assumption_checks", root, "basic_assumption_checks.v1.json")
    summary_path = _output_path(outputs, "summary", root, "*_summary.csv")
    participant_trials_path = _output_path(outputs, "participant_trials", root, "*_trials.csv")
    responses_path = _output_path(outputs, "responses", root, "*_responses.csv")
    final_path = _output_path(outputs, "final_trial_outcomes", root, "*_final_trial_outcomes.csv")
    timing_qc_path = _output_path(outputs, "timing_qc", root, "*_timing_qc.csv")
    events_path = _output_path(outputs, "events_csv", root, "events.csv")
    behavior_path = _output_path(outputs, "data_behavior_by_scope", root, "data_behavior_by_scope.csv")
    behavior_summary_path = _output_path(outputs, "exploratory_quality_summary", root, "exploratory_quality_summary.json")

    data.curve_rows = _read_csv_rows(curves_path, data.warnings, "curve points")
    data.model_fit_rows = _read_csv_rows(fits_path, data.warnings, "model fits")
    data.model_comparison_rows = _read_csv_rows(comparison_path, data.warnings, "model comparison")
    data.condition_lens_curve_rows = _read_optional_csv_rows(condition_curves_path)
    data.condition_lens_model_fit_rows = _read_optional_csv_rows(condition_fits_path)
    data.condition_lens_model_comparison_rows = _read_optional_csv_rows(condition_comparison_path)
    data.condition_lens_triage_summary = _read_json(condition_summary_path)
    data.recording_quality_gate = _read_json(quality_gate_path)
    data.assumption_checks = _read_json(assumption_checks_path)
    data.summary_rows = _read_csv_rows(summary_path, data.warnings, "summary")
    data.participant_trial_rows = _read_optional_csv_rows(participant_trials_path)
    data.response_rows = _read_optional_csv_rows(responses_path)
    data.final_outcome_rows = _read_optional_csv_rows(final_path)
    data.timing_qc_rows = _read_optional_csv_rows(timing_qc_path)
    data.event_rows = _read_optional_csv_rows(events_path)
    data.data_behavior_rows = _read_optional_csv_rows(behavior_path)
    data.exploratory_quality_summary = _read_json(behavior_summary_path)
    data.output_paths = {
        key: path
        for key, path in {
            "curve points": curves_path,
            "model fits": fits_path,
            "model comparison": comparison_path,
            "condition lens curves": condition_curves_path,
            "condition lens model fits": condition_fits_path,
            "condition lens model comparison": condition_comparison_path,
            "condition lens triage": condition_summary_path,
            "recording quality gate": quality_gate_path,
            "basic assumption checks": assumption_checks_path,
            "summary": summary_path,
            "participant trials": participant_trials_path,
            "responses": responses_path,
            "final outcomes": final_path,
            "timing QC": timing_qc_path,
            "events": events_path,
            "data behavior": behavior_path,
            "exploratory summary": behavior_summary_path,
        }.items()
        if path is not None
    }

    if not data.summary_text and root is not None:
        summary_file = root / "analysis_summary.txt"
        if summary_file.is_file():
            data.summary_text = summary_file.read_text(encoding="utf-8").strip()
    return data


def scopes_for_part_mode(data: AnalysisReviewData, part_mode: str | None = None) -> list[str]:
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    scopes = {
        str(row.get("scope") or "").strip()
        for row in [*data.curve_rows, *data.model_fit_rows, *data.model_comparison_rows]
        if _row_part_mode(row) == mode and str(row.get("scope") or "").strip()
    }
    return sorted(scopes)


def best_model_for_scope(data: AnalysisReviewData, scope: str, part_mode: str | None = None) -> str:
    scope = str(scope or "").strip()
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    comparison = next(
        (
            row
            for row in data.model_comparison_rows
            if _row_part_mode(row) == mode and str(row.get("scope") or "").strip() == scope
        ),
        None,
    )
    if comparison is not None:
        model = str(comparison.get("best_model") or "").strip()
        if model:
            return model
    rows = [
        row
        for row in data.model_fit_rows
        if _row_part_mode(row) == mode and str(row.get("scope") or "").strip() == scope
    ]
    if not rows:
        return ""
    best = min(rows, key=lambda row: _as_float(row.get("aic"), math.inf))
    return str(best.get("model") or "").strip()


def fit_row_for_scope(data: AnalysisReviewData, scope: str, model: str, part_mode: str | None = None) -> dict[str, Any] | None:
    scope = str(scope or "").strip()
    model = str(model or "").strip()
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    if model == MODEL_BEST:
        model = best_model_for_scope(data, scope, mode)
    matches = [
        row
        for row in data.model_fit_rows
        if _row_part_mode(row) == mode
        and str(row.get("scope") or "").strip() == scope
        and str(row.get("model") or "").strip() == model
    ]
    if not matches:
        return None
    return min(matches, key=lambda row: _as_float(row.get("aic"), math.inf))


def available_models_for_scope(data: AnalysisReviewData, scope: str, part_mode: str | None = None) -> list[str]:
    scope = str(scope or "").strip()
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    models = {
        str(row.get("model") or "").strip()
        for row in data.model_fit_rows
        if _row_part_mode(row) == mode and str(row.get("scope") or "").strip() == scope and str(row.get("model") or "").strip()
    }
    output = [MODEL_BEST]
    if len(models.intersection(MODEL_FIT_ORDER)) >= 2:
        output.append(MODEL_COMPARE_ALL)
    output.extend(model for model in MODEL_FIT_ORDER if model in models)
    return output


def observed_points_for_scope(
    data: AnalysisReviewData,
    scope: str,
    part_mode: str | None = None,
    *,
    metric: str | None = None,
    source_mode: str = SOURCE_FINAL,
) -> list[dict[str, float | str]]:
    scope = str(scope or "").strip()
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    metric = _normalized_metric(metric)
    if metric in {METRIC_HIT_RATE, METRIC_RESPONSE_COUNT}:
        return _outcome_metric_points(data, scope, mode, metric, source_mode)
    points: list[dict[str, float | str]] = []
    for row in data.curve_rows:
        if _row_part_mode(row) != mode or str(row.get("scope") or "").strip() != scope:
            continue
        x = _as_float(row.get("soa_ms"), math.nan)
        if not math.isfinite(x):
            continue
        y = _metric_value(row, metric)
        if y is None:
            continue
        low, high, spread_label = _spread_bounds(row, metric, y)
        point: dict[str, float | str] = {"x": x, "y": y, "metric": metric or _metric_name(row)}
        n = _as_float(row.get("n"), math.nan)
        if math.isfinite(n):
            point["n"] = n
            if n < 3:
                point["low_n"] = "yes"
        if low is not None and high is not None:
            point["y_low"] = low
            point["y_high"] = high
            point["spread_label"] = spread_label
        points.append(point)
    return sorted(points, key=lambda item: float(item["x"]))


def prediction_points_for_scope(
    data: AnalysisReviewData,
    scope: str,
    model: str,
    *,
    part_mode: str | None = None,
    sample_count: int = 480,
) -> list[dict[str, float]]:
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    fit = fit_row_for_scope(data, scope, model, mode)
    observed = observed_points_for_scope(data, scope, mode)
    if fit is None or not observed:
        return []
    xs = [float(point["x"]) for point in observed]
    if len(xs) == 1 or min(xs) == max(xs):
        sample_xs = xs
    else:
        count = max(2, int(sample_count))
        x_min = min(xs)
        x_max = max(xs)
        sample_xs = [x_min + (x_max - x_min) * index / (count - 1) for index in range(count)]
    resolved_model = str(fit.get("model") or "").strip()
    points = []
    for x in sample_xs:
        y = _predict_y(fit, resolved_model, x)
        if y is not None and math.isfinite(y):
            points.append({"x": float(x), "y": float(y)})
    return points


def prediction_series_for_scope(
    data: AnalysisReviewData,
    scope: str,
    model: str,
    *,
    part_mode: str | None = None,
    sample_count: int = 480,
) -> list[dict[str, Any]]:
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    requested = str(model or "").strip()
    if requested == MODEL_COMPARE_ALL:
        models = [candidate for candidate in MODEL_FIT_ORDER if fit_row_for_scope(data, scope, candidate, mode) is not None]
    else:
        models = [best_model_for_scope(data, scope, mode) if requested == MODEL_BEST else requested]
    series: list[dict[str, Any]] = []
    for candidate in models:
        if not candidate:
            continue
        points = prediction_points_for_scope(data, scope, candidate, part_mode=mode, sample_count=sample_count)
        if points:
            series.append(
                {
                    "model": candidate,
                    "label": MODEL_LABELS.get(candidate, candidate),
                    "points": points,
                    "fit": fit_row_for_scope(data, scope, candidate, mode) or {},
                }
            )
    return series


def scope_comparison_row(data: AnalysisReviewData, scope: str, part_mode: str | None = None) -> dict[str, Any]:
    scope = str(scope or "").strip()
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    row = next(
        (
            item
            for item in data.model_comparison_rows
            if _row_part_mode(item) == mode and str(item.get("scope") or "").strip() == scope
        ),
        None,
    )
    return dict(row or {"scope": scope, "aggregation_mode": mode, "best_model": best_model_for_scope(data, scope, mode)})


def behavior_signals_for_scope(data: AnalysisReviewData, scope: str, part_mode: str | None = None) -> list[dict[str, Any]]:
    scope = str(scope or "").strip()
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    scoped = [
        row
        for row in data.data_behavior_rows
        if str(row.get("scope") or "").strip() == scope and _row_part_mode(row) == mode
    ]
    session_rows = [row for row in data.data_behavior_rows if str(row.get("scope") or "").strip() == "Session"]
    return scoped + session_rows


def behavior_signal_counts(data: AnalysisReviewData) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in data.data_behavior_rows:
        signal = str(row.get("signal") or "").strip()
        if signal:
            counts[signal] = counts.get(signal, 0) + 1
    if counts:
        return counts
    raw = data.exploratory_quality_summary.get("signal_counts", {})
    return {str(key): int(value) for key, value in raw.items()} if isinstance(raw, dict) else {}


def raw_points_for_scope(
    data: AnalysisReviewData,
    scope: str,
    part_mode: str | None = None,
    *,
    source_mode: str = SOURCE_FINAL,
) -> list[dict[str, float | str]]:
    rows = _source_response_rows(data, source_mode)
    mode = _normalized_part_mode(part_mode or data.default_part_mode)
    points: list[dict[str, float | str]] = []
    for row in rows:
        if _scope_from_response_row(row, mode) != scope:
            continue
        x = _as_float(row.get("soa_ms"), math.nan)
        y = _as_float(row.get("rt_ms"), math.nan)
        if math.isfinite(x) and math.isfinite(y):
            points.append({"x": x, "y": y, "metric": METRIC_MEAN_RT})
    return sorted(points, key=lambda item: (float(item["x"]), float(item["y"])))


def artifact_rows_for_review(data: AnalysisReviewData) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for label, path in sorted(data.output_paths.items()):
        rows.append({"artifact": label, "path": str(path), "available": "yes" if path.is_file() else "no"})
    return rows


def available_condition_lenses(data: AnalysisReviewData) -> list[str]:
    lenses = {str(row.get("analysis_lens") or "").strip() for row in data.condition_lens_curve_rows}
    ordered = [lens for lens in CONDITION_LENS_ORDER if lens in lenses and lens != CONDITION_LENS_OVERALL]
    return ordered or ([CONDITION_LENS_TWO_BY_TWO] if data.curve_rows else [])


def condition_lens_labels(data: AnalysisReviewData) -> dict[str, str]:
    raw = data.condition_lens_triage_summary.get("condition_lens_buttons", {})
    labels = {
        str(lens): str(payload.get("label") or "").strip()
        for lens, payload in raw.items()
        if isinstance(payload, dict) and str(payload.get("label") or "").strip()
    } if isinstance(raw, dict) else {}
    labels.setdefault(CONDITION_LENS_TWO_BY_TWO, _fallback_lens_label(data, CONDITION_LENS_TWO_BY_TWO))
    labels.setdefault(CONDITION_LENS_PART, _fallback_lens_label(data, CONDITION_LENS_PART))
    labels.setdefault(CONDITION_LENS_STATE, _fallback_lens_label(data, CONDITION_LENS_STATE))
    labels.setdefault(CONDITION_LENS_OVERALL, "Overall")
    return labels


def default_condition_lens(data: AnalysisReviewData) -> str:
    requested = str(data.condition_lens_triage_summary.get("default_lens") or "").strip()
    if requested and any(row.get("analysis_lens") == requested for row in data.condition_lens_curve_rows):
        return requested
    lenses = available_condition_lenses(data)
    return lenses[0] if lenses else CONDITION_LENS_TWO_BY_TWO


def default_condition_model(data: AnalysisReviewData) -> str:
    requested = str(data.condition_lens_triage_summary.get("default_model") or "").strip()
    if requested in QUICK_MODEL_ORDER:
        return requested
    overall = data.condition_lens_triage_summary.get("overall_model", {})
    if isinstance(overall, dict):
        model = str(overall.get("best_model") or "").strip()
        if model in QUICK_MODEL_ORDER:
            return model
    return MODEL_SIGMOID


def condition_lens_button_rows(data: AnalysisReviewData) -> list[dict[str, Any]]:
    labels = condition_lens_labels(data)
    summary = data.condition_lens_triage_summary.get("condition_lens_buttons", {})
    output = []
    for lens in (CONDITION_LENS_TWO_BY_TWO, CONDITION_LENS_PART, CONDITION_LENS_STATE):
        payload = summary.get(lens, {}) if isinstance(summary, dict) else {}
        payload = payload if isinstance(payload, dict) else {}
        output.append(
            {
                "lens": lens,
                "label": labels.get(lens, _fallback_lens_label(data, lens)),
                "curve_separation_winner": bool(payload.get("curve_separation_winner")),
                "boundary_shift_winner": bool(payload.get("boundary_shift_winner")),
                "curve_separation_score_ms": payload.get("curve_separation_score_ms"),
                "boundary_shift_score_ms": payload.get("boundary_shift_score_ms"),
            }
        )
    return output


def model_button_rows(data: AnalysisReviewData) -> list[dict[str, Any]]:
    raw = data.condition_lens_triage_summary.get("model_button_summaries", {})
    raw = raw if isinstance(raw, dict) else {}
    return [
        {
            "model": model,
            "label": "Log decay" if model == MODEL_LOGARITHMIC_DECAY else MODEL_LABELS.get(model, model),
            "evidence_tier": str((raw.get(model) or {}).get("evidence_tier") or MODEL_EVIDENCE_INSUFFICIENT) if isinstance(raw.get(model), dict) else MODEL_EVIDENCE_INSUFFICIENT,
            "overall_winner": bool((raw.get(model) or {}).get("overall_winner")) if isinstance(raw.get(model), dict) else False,
            "subcondition_wins": (raw.get(model) or {}).get("subcondition_wins", 0) if isinstance(raw.get(model), dict) else 0,
        }
        for model in QUICK_MODEL_ORDER
    ]


def recording_quality_status(data: AnalysisReviewData) -> tuple[str, str]:
    status = str(data.recording_quality_gate.get("status") or "").strip().upper()
    if status not in {QUALITY_PASS, QUALITY_FAIL}:
        return "UNKNOWN", "No recording-quality gate artifact was available."
    reason = str(data.recording_quality_gate.get("primary_reason") or "").strip()
    return status, reason or ("No serious exclusion criteria were triggered." if status == QUALITY_PASS else "A serious exclusion criterion was triggered.")


def response_quality_summary(data: AnalysisReviewData) -> dict[str, Any]:
    rows = _response_quality_source_rows(data)
    tactile_rows = [row for row in rows if _response_quality_row_is_tactile(row)]
    catch_rows = [row for row in rows if _response_quality_row_is_catch(row)]
    tactile_hits = sum(1 for row in tactile_rows if _response_quality_tactile_hit(row))
    catch_false_alarms = sum(1 for row in catch_rows if _response_quality_catch_false_alarm(row))
    tactile_total = len(tactile_rows)
    catch_total = len(catch_rows)
    return {
        "tactile": {
            "total": tactile_total,
            "hits": tactile_hits,
            "misses": max(0, tactile_total - tactile_hits),
            "hit_rate": tactile_hits / tactile_total if tactile_total else None,
            "miss_rate": (tactile_total - tactile_hits) / tactile_total if tactile_total else None,
        },
        "catch": {
            "total": catch_total,
            "correct": max(0, catch_total - catch_false_alarms),
            "false_alarms": catch_false_alarms,
            "correct_rate": (catch_total - catch_false_alarms) / catch_total if catch_total else None,
            "false_alarm_rate": catch_false_alarms / catch_total if catch_total else None,
        },
    }


def condition_lens_metric_label(data: AnalysisReviewData, lens: str) -> str:
    rows = _condition_lens_rows(data, lens)
    if any(_metric_name(row) == METRIC_FACILITATION for row in rows):
        return "Baseline-corrected facilitation (ms)"
    return "Mean RT (ms)"


def condition_lens_baseline_status(data: AnalysisReviewData, lens: str) -> str:
    rows = _condition_lens_rows(data, lens)
    corrected = [
        row
        for row in rows
        if _metric_name(row) == METRIC_FACILITATION
        and str(row.get("baseline_correction_method") or "").strip() == BASELINE_CORRECTION_METHOD_CONDITION_MEAN_POOLED_SOA
    ]
    if corrected:
        return "Baseline: pooled across SOAs within condition"
    if any(_metric_name(row) == METRIC_FACILITATION for row in rows):
        return "Baseline: corrected"
    return "Baseline: unavailable; plotting mean RT"


def condition_lens_observed_series(
    data: AnalysisReviewData,
    lens: str,
    *,
    metric: str = METRIC_FACILITATION,
) -> list[dict[str, Any]]:
    rows = _condition_lens_rows(data, lens)
    grouped: dict[str, list[dict[str, float | str]]] = {}
    for row in rows:
        scope = _condition_row_scope(row)
        x = _as_float(row.get("soa_ms"), math.nan)
        if not scope or not math.isfinite(x):
            continue
        y = _metric_value(row, metric)
        if y is None:
            continue
        low, high, spread_label = _spread_bounds(row, metric, y)
        point: dict[str, float | str] = {"x": x, "y": y, "metric": metric}
        n = _as_float(row.get("n"), math.nan)
        if math.isfinite(n):
            point["n"] = n
            if n < 3:
                point["low_n"] = "yes"
        if low is not None and high is not None:
            point["y_low"] = low
            point["y_high"] = high
            point["spread_label"] = spread_label
        grouped.setdefault(scope, []).append(point)
    series = []
    for index, (scope, points) in enumerate(sorted(grouped.items(), key=lambda item: _condition_scope_sort_key(item[0]))):
        series.append(
            {
                "label": scope,
                "scope": scope,
                "color": CONDITION_SERIES_COLORS[index % len(CONDITION_SERIES_COLORS)],
                "points": sorted(points, key=lambda item: float(item["x"])),
            }
        )
    return series


def condition_lens_prediction_series(
    data: AnalysisReviewData,
    lens: str,
    model: str,
    *,
    sample_count: int = 480,
) -> list[dict[str, Any]]:
    observed = condition_lens_observed_series(data, lens)
    by_scope = {str(series.get("scope") or series.get("label") or ""): series for series in observed}
    output: list[dict[str, Any]] = []
    for scope, observed_series in by_scope.items():
        fit = condition_lens_fit_row(data, lens, scope, model)
        if fit is None:
            continue
        points = list(observed_series.get("points") or [])
        xs = [float(point["x"]) for point in points]
        if not xs:
            continue
        if len(xs) == 1 or min(xs) == max(xs):
            sample_xs = xs
        else:
            count = max(2, int(sample_count))
            x_min = min(xs)
            x_max = max(xs)
            sample_xs = [x_min + (x_max - x_min) * index / (count - 1) for index in range(count)]
        resolved_model = str(fit.get("model") or "").strip()
        predicted = []
        for x in sample_xs:
            y = _predict_y(fit, resolved_model, x)
            if y is not None and math.isfinite(y):
                predicted.append({"x": float(x), "y": float(y)})
        if predicted:
            output.append(
                {
                    "model": resolved_model,
                    "label": scope,
                    "scope": scope,
                    "points": predicted,
                    "fit": fit,
                    "color": observed_series.get("color", ""),
                }
            )
    return output


def condition_lens_fit_row(data: AnalysisReviewData, lens: str, scope: str, model: str) -> dict[str, Any] | None:
    requested = str(model or "").strip()
    scope = str(scope or "").strip()
    if requested == MODEL_BEST:
        comparison = next(
            (
                row
                for row in data.condition_lens_model_comparison_rows
                if str(row.get("analysis_lens") or "") == lens and _condition_row_scope(row) == scope
            ),
            None,
        )
        requested = str((comparison or {}).get("best_model") or "").strip()
    matches = [
        row
        for row in data.condition_lens_model_fit_rows
        if str(row.get("analysis_lens") or "") == lens
        and _condition_row_scope(row) == scope
        and str(row.get("model") or "").strip() == requested
    ]
    if not matches:
        return None
    return min(matches, key=lambda row: _as_float(row.get("aicc"), _as_float(row.get("aic"), math.inf)))


def _condition_lens_rows(data: AnalysisReviewData, lens: str) -> list[dict[str, Any]]:
    rows = [row for row in data.condition_lens_curve_rows if str(row.get("analysis_lens") or "") == lens]
    if not rows and lens == CONDITION_LENS_TWO_BY_TWO:
        rows = [dict(row, analysis_lens=lens, display_scope=row.get("scope", "")) for row in data.curve_rows if _row_part_mode(row) == data.default_part_mode]
    return rows


def _fallback_lens_label(data: AnalysisReviewData, lens: str) -> str:
    rows = [row for row in data.condition_lens_curve_rows if str(row.get("analysis_lens") or "") == CONDITION_LENS_TWO_BY_TWO]
    parts = _ordered_unique(row.get("part_label") for row in rows if str(row.get("part_label") or "") not in {"", "All parts"})
    states = _ordered_unique(row.get("state_label") for row in rows if str(row.get("state_label") or "") not in {"", "All states"})
    if lens == CONDITION_LENS_TWO_BY_TWO:
        return "2 x 2" if len(parts) == 2 and len(states) == 2 else "Interaction"
    if lens == CONDITION_LENS_PART:
        return " | ".join(parts) if len(parts) == 2 else "Parts"
    if lens == CONDITION_LENS_STATE:
        return " | ".join(states) if len(states) == 2 else "States"
    return "Overall"


def _condition_row_scope(row: dict[str, Any]) -> str:
    return str(row.get("display_scope") or row.get("scope") or "").strip()


def _condition_scope_sort_key(scope: str) -> tuple[int, int, str]:
    part_match = scope.lower().split(" / ")[0] if scope else ""
    part_number = _as_int(part_match.replace("part", "").strip(), 999) if part_match.startswith("part") else 999
    state_rank = 0 if "inhale" in scope.lower() else 1 if "exhale" in scope.lower() else 9
    return (part_number, state_rank, scope)


def _ordered_unique(values: Any) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return sorted(output, key=lambda item: _condition_scope_sort_key(item))


def _output_path(outputs: dict[str, Any], key: str, session_dir: Path | None, pattern: str) -> Path | None:
    raw = outputs.get(key)
    if raw not in (None, ""):
        return Path(raw)
    if session_dir is None:
        return None
    analysis_dir = session_dir / "analysis"
    matches = sorted(analysis_dir.glob(pattern)) if analysis_dir.is_dir() else []
    if matches:
        return matches[0]
    direct = session_dir / pattern
    return direct if "*" not in pattern and direct.is_file() else None


def _read_csv_rows(path: Path | None, warnings: list[str], label: str) -> list[dict[str, Any]]:
    if path is None:
        warnings.append(f"Missing {label} CSV.")
        return []
    if not path.is_file():
        warnings.append(f"Missing {label} CSV: {path}")
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if len(rows) == 1 and set(rows[0].keys()) == {"empty"}:
        return []
    return rows


def _read_optional_csv_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    if len(rows) == 1 and set(rows[0].keys()) == {"empty"}:
        return []
    return rows


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _metric_name(row: dict[str, Any]) -> str:
    if row.get("facilitation_ms") not in (None, ""):
        return "facilitation_ms"
    return "mean_rt_ms"


def _row_part_mode(row: dict[str, Any]) -> str:
    return _normalized_part_mode(row.get("aggregation_mode") or PARTS_SEPARATE)


def _normalized_part_mode(value: Any) -> str:
    text = str(value or "").strip()
    if text in {PARTS_SEPARATE, PARTS_POOLED}:
        return text
    if text.lower() in {"pool", "pooled", "pooled_parts", "all_parts"}:
        return PARTS_POOLED
    return PARTS_SEPARATE


def _normalized_metric(value: Any) -> str:
    text = str(value or "").strip()
    if text in METRIC_ORDER:
        return text
    if text.lower() in {"mean rt", "rt", "reaction_time", "reaction time"}:
        return METRIC_MEAN_RT
    if text.lower() in {"hit", "hit_rate", "hit rate"}:
        return METRIC_HIT_RATE
    if text.lower() in {"n", "count", "response_count", "response count"}:
        return METRIC_RESPONSE_COUNT
    return METRIC_FACILITATION


def _metric_value(row: dict[str, Any], metric: str) -> float | None:
    candidates = [metric] if metric else []
    candidates.extend(["facilitation_ms", "mean_rt_ms"])
    for key in candidates:
        value = _as_float(row.get(key), math.nan)
        if math.isfinite(value):
            return value
    return None


def _outcome_metric_points(
    data: AnalysisReviewData,
    scope: str,
    part_mode: str,
    metric: str,
    source_mode: str,
) -> list[dict[str, float | str]]:
    grouped: dict[float, list[dict[str, Any]]] = {}
    for row in _source_response_rows(data, source_mode):
        if _scope_from_response_row(row, part_mode) != scope:
            continue
        soa = _as_float(row.get("soa_ms"), math.nan)
        if math.isfinite(soa):
            grouped.setdefault(soa, []).append(row)
    points: list[dict[str, float | str]] = []
    for soa, rows in grouped.items():
        if metric == METRIC_RESPONSE_COUNT:
            y = float(len(rows))
        else:
            y = sum(1 for row in rows if _truthy(row.get("hit"))) / max(1, len(rows))
        point: dict[str, float | str] = {"x": soa, "y": y, "metric": metric, "n": float(len(rows))}
        if len(rows) < 3:
            point["low_n"] = "yes"
        points.append(point)
    if points:
        return sorted(points, key=lambda item: float(item["x"]))
    if metric == METRIC_RESPONSE_COUNT:
        fallback = []
        for row in data.curve_rows:
            if _row_part_mode(row) != part_mode or str(row.get("scope") or "").strip() != scope:
                continue
            soa = _as_float(row.get("soa_ms"), math.nan)
            count = _as_float(row.get("n"), math.nan)
            if math.isfinite(soa) and math.isfinite(count):
                fallback.append({"x": soa, "y": count, "metric": metric, "n": count})
        return sorted(fallback, key=lambda item: float(item["x"]))
    return []


def _source_response_rows(data: AnalysisReviewData, source_mode: str) -> list[dict[str, Any]]:
    final_rows = data.final_outcome_rows or data.response_rows
    if source_mode == SOURCE_ORIGINAL:
        return [row for row in final_rows if not _truthy(row.get("is_topup"))]
    if source_mode == SOURCE_TOPUP:
        return [
            row
            for row in final_rows
            if _truthy(row.get("rescued_in_topup"))
            or str(row.get("final_outcome_source") or "").strip() in {"topup_rescue", "topup_rescue_orphan"}
        ]
    if source_mode == SOURCE_EXCLUDED:
        rows = [
            row
            for row in data.response_rows
            if not _truthy(row.get("primary_analysis_included", True)) or str(row.get("topup_role") or "").strip().lower() == "filler"
        ]
        return rows
    return final_rows


def _response_quality_source_rows(data: AnalysisReviewData) -> list[dict[str, Any]]:
    if data.participant_trial_rows:
        return list(data.participant_trial_rows)
    rows = list(data.response_rows or data.final_outcome_rows or [])
    if rows and not any(_response_quality_row_is_catch(row) for row in rows):
        catch_rows = [row for row in data.final_outcome_rows if _response_quality_row_is_catch(row)]
        if catch_rows:
            rows.extend(catch_rows)
    return rows


def _response_quality_row_is_catch(row: dict[str, Any]) -> bool:
    if _truthy(row.get("catch_trial")) or _truthy(row.get("is_catch")):
        return True
    text = _response_quality_row_text(row)
    return any(token in text for token in ("catch", "audio-only", "audio only", "auditory-only", "auditory only", "no-target", "no target"))


def _response_quality_row_is_tactile(row: dict[str, Any]) -> bool:
    if _response_quality_row_is_catch(row):
        return False
    if _truthy(row.get("tactile_present")) or _truthy(row.get("tactile_event")):
        return True
    text = _response_quality_row_text(row)
    if any(token in text for token in ("audio-tactile", "audio_tactile", "baseline", "tactile")):
        return True
    return any(_has_row_value(row, key) for key in ("hit", "rt_ms", "reaction_time_ms", "tactile_onset_unix_time", "tactile_cue_time_s"))


def _response_quality_tactile_hit(row: dict[str, Any]) -> bool:
    if _has_row_value(row, "hit"):
        return _truthy(row.get("hit"))
    outcome = str(row.get("outcome") or row.get("trial_outcome") or row.get("Outcome") or "").strip().lower()
    if "miss" in outcome:
        return False
    if "hit" in outcome or "response" in outcome:
        return True
    for key in ("response_given", "response_detected", "click_detected", "detected"):
        if _has_row_value(row, key):
            return _truthy(row.get(key))
    return any(_has_row_value(row, key) for key in ("rt_ms", "reaction_time_ms", "click_unix_time", "click_time_s"))


def _response_quality_catch_false_alarm(row: dict[str, Any]) -> bool:
    for key in ("false_alarm", "catch_false_alarm"):
        if _has_row_value(row, key):
            return _truthy(row.get(key))
    for key in ("response_given", "response_detected", "click_detected", "detected"):
        if _has_row_value(row, key):
            return _truthy(row.get(key))
    outcome = str(row.get("outcome") or row.get("trial_outcome") or row.get("Outcome") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if outcome in {"false_alarm", "catch_false_alarm", "responded", "response"}:
        return True
    if outcome in {"correct_rejection", "correct_no_response", "no_response", "hit", "correct"}:
        return False
    if _has_row_value(row, "hit"):
        return not _truthy(row.get("hit"))
    return False


def _response_quality_row_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key) or "").strip().lower()
        for key in (
            "trial_type",
            "Trial_Type",
            "family",
            "Family",
            "stimulus_modality",
            "SOA_type",
            "condition",
            "outcome",
        )
    )


def _has_row_value(row: dict[str, Any], key: str) -> bool:
    return row.get(key) not in (None, "")


def _scope_from_response_row(row: dict[str, Any], part_mode: str) -> str:
    part_number = _as_int(row.get("part_number"), None)
    raw_condition = row.get("condition", "")
    condition = _condition_without_part_label(raw_condition)
    phase = str(row.get("respiratory_phase", "") or "").strip()
    noise = str(row.get("noise_type", "") or "").strip()
    if part_mode == PARTS_POOLED:
        part_label = "All parts" if part_number is not None else ""
    else:
        part_label = f"Part {part_number}" if part_number is not None else ""
    return _scope_label(part_label, condition, phase, noise)


def _spread_bounds(row: dict[str, Any], metric: str, y: float) -> tuple[float | None, float | None, str]:
    metric_key = metric or _metric_name(row)
    if metric_key == "facilitation_ms":
        candidates = [
            ("facilitation_sem_ms", "SEM"),
            ("fit_metric_sem_ms", "SEM"),
            ("facilitation_sd_ms", "SD"),
            ("fit_metric_sd_ms", "SD"),
            ("sem_rt_ms", "SEM"),
            ("sd_rt_ms", "SD"),
        ]
    else:
        candidates = [
            ("sem_rt_ms", "SEM"),
            ("fit_metric_sem_ms", "SEM"),
            ("sd_rt_ms", "SD"),
            ("fit_metric_sd_ms", "SD"),
        ]
    for key, label in candidates:
        spread = _as_float(row.get(key), math.nan)
        if math.isfinite(spread) and spread > 0:
            return y - spread, y + spread, label
    explicit_low = _as_float(row.get("fit_metric_low_ms"), math.nan)
    explicit_high = _as_float(row.get("fit_metric_high_ms"), math.nan)
    if math.isfinite(explicit_low) and math.isfinite(explicit_high):
        return min(explicit_low, explicit_high), max(explicit_low, explicit_high), "range"
    return None, None, ""


def _predict_y(fit: dict[str, Any], model: str, x: float) -> float | None:
    if model == MODEL_LINEAR:
        intercept = _as_float(fit.get("intercept"), math.nan)
        slope = _as_float(fit.get("slope"), math.nan)
        if math.isfinite(intercept) and math.isfinite(slope):
            return intercept + slope * x
    if model == MODEL_LOGARITHMIC_DECAY and x > 0:
        intercept = _as_float(fit.get("intercept"), math.nan)
        slope = _as_float(fit.get("log_slope"), math.nan)
        if math.isfinite(intercept) and math.isfinite(slope):
            return intercept + slope * math.log(x)
    if model == MODEL_SIGMOID:
        lower = _as_float(fit.get("lower"), math.nan)
        upper = _as_float(fit.get("upper"), math.nan)
        boundary = _as_float(fit.get("pps_boundary_soa_ms"), math.nan)
        slope = _as_float(fit.get("slope"), math.nan)
        if all(math.isfinite(value) for value in (lower, upper, boundary, slope)):
            return lower + (upper - lower) / (1.0 + math.exp(-slope * (x - boundary)))
    return None


def _condition_without_part_label(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.lower().startswith("part ") and text[5:].strip().isdigit() else text


def _scope_label(part_label: Any, condition: Any, phase: Any, noise: Any) -> str:
    parts = [str(part) for part in (part_label, condition, phase, noise) if str(part).strip()]
    return " / ".join(parts) or "All audio-tactile"


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _as_int(value: Any, default: Any) -> Any:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default
