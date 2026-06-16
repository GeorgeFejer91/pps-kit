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
    curve_rows: list[dict[str, Any]] = field(default_factory=list)
    model_fit_rows: list[dict[str, Any]] = field(default_factory=list)
    model_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    summary_rows: list[dict[str, Any]] = field(default_factory=list)
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
        return bool(self.curve_rows or self.model_fit_rows or self.model_comparison_rows or self.summary_rows)

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
) -> AnalysisReviewData:
    """Load existing immediate-analysis outputs for read-only review."""

    root = Path(session_dir) if session_dir not in (None, "") else None
    outputs = dict(analysis_outputs or {})
    data = AnalysisReviewData(session_dir=root, summary_text=str(summary_text or "").strip())

    curves_path = _output_path(outputs, "curves", root, "*_pps_curve_points.csv")
    fits_path = _output_path(outputs, "model_fits", root, "*_model_fits.csv")
    comparison_path = _output_path(outputs, "model_fit_comparison", root, "*_model_fit_comparison.csv")
    summary_path = _output_path(outputs, "summary", root, "*_summary.csv")
    responses_path = _output_path(outputs, "responses", root, "*_responses.csv")
    final_path = _output_path(outputs, "final_trial_outcomes", root, "*_final_trial_outcomes.csv")
    timing_qc_path = _output_path(outputs, "timing_qc", root, "*_timing_qc.csv")
    events_path = _output_path(outputs, "events_csv", root, "events.csv")
    behavior_path = _output_path(outputs, "data_behavior_by_scope", root, "data_behavior_by_scope.csv")
    behavior_summary_path = _output_path(outputs, "exploratory_quality_summary", root, "exploratory_quality_summary.json")

    data.curve_rows = _read_csv_rows(curves_path, data.warnings, "curve points")
    data.model_fit_rows = _read_csv_rows(fits_path, data.warnings, "model fits")
    data.model_comparison_rows = _read_csv_rows(comparison_path, data.warnings, "model comparison")
    data.summary_rows = _read_csv_rows(summary_path, data.warnings, "summary")
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
            "summary": summary_path,
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
