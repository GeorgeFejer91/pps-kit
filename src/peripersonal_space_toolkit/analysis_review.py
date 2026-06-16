"""Helpers for the post-run PPS analysis review window."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


MODEL_BEST = "best"
MODEL_SIGMOID = "sigmoid"
MODEL_LINEAR = "linear"
MODEL_LOGARITHMIC_DECAY = "logarithmic_decay"

MODEL_ORDER = (MODEL_BEST, MODEL_SIGMOID, MODEL_LINEAR, MODEL_LOGARITHMIC_DECAY)
MODEL_LABELS = {
    MODEL_BEST: "Best model",
    MODEL_SIGMOID: "Sigmoid",
    MODEL_LINEAR: "Linear",
    MODEL_LOGARITHMIC_DECAY: "Logarithmic decay",
}


@dataclass
class AnalysisReviewData:
    """Loaded analysis-review data for one completed runner session."""

    session_dir: Path | None = None
    curve_rows: list[dict[str, Any]] = field(default_factory=list)
    model_fit_rows: list[dict[str, Any]] = field(default_factory=list)
    model_comparison_rows: list[dict[str, Any]] = field(default_factory=list)
    summary_rows: list[dict[str, Any]] = field(default_factory=list)
    summary_text: str = ""
    warnings: list[str] = field(default_factory=list)

    @property
    def has_analysis_tables(self) -> bool:
        return bool(self.curve_rows or self.model_fit_rows or self.model_comparison_rows or self.summary_rows)

    @property
    def scopes(self) -> list[str]:
        scopes = {
            str(row.get("scope") or "").strip()
            for row in [*self.curve_rows, *self.model_fit_rows, *self.model_comparison_rows]
            if str(row.get("scope") or "").strip()
        }
        return sorted(scopes)


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

    data.curve_rows = _read_csv_rows(curves_path, data.warnings, "curve points")
    data.model_fit_rows = _read_csv_rows(fits_path, data.warnings, "model fits")
    data.model_comparison_rows = _read_csv_rows(comparison_path, data.warnings, "model comparison")
    data.summary_rows = _read_csv_rows(summary_path, data.warnings, "summary")

    if not data.summary_text and root is not None:
        summary_file = root / "analysis_summary.txt"
        if summary_file.is_file():
            data.summary_text = summary_file.read_text(encoding="utf-8").strip()
    return data


def best_model_for_scope(data: AnalysisReviewData, scope: str) -> str:
    scope = str(scope or "").strip()
    comparison = next((row for row in data.model_comparison_rows if str(row.get("scope") or "").strip() == scope), None)
    if comparison is not None:
        model = str(comparison.get("best_model") or "").strip()
        if model:
            return model
    rows = [row for row in data.model_fit_rows if str(row.get("scope") or "").strip() == scope]
    if not rows:
        return ""
    best = min(rows, key=lambda row: _as_float(row.get("aic"), math.inf))
    return str(best.get("model") or "").strip()


def fit_row_for_scope(data: AnalysisReviewData, scope: str, model: str) -> dict[str, Any] | None:
    scope = str(scope or "").strip()
    model = str(model or "").strip()
    if model == MODEL_BEST:
        model = best_model_for_scope(data, scope)
    matches = [
        row
        for row in data.model_fit_rows
        if str(row.get("scope") or "").strip() == scope and str(row.get("model") or "").strip() == model
    ]
    if not matches:
        return None
    return min(matches, key=lambda row: _as_float(row.get("aic"), math.inf))


def available_models_for_scope(data: AnalysisReviewData, scope: str) -> list[str]:
    scope = str(scope or "").strip()
    models = {
        str(row.get("model") or "").strip()
        for row in data.model_fit_rows
        if str(row.get("scope") or "").strip() == scope and str(row.get("model") or "").strip()
    }
    return [model for model in MODEL_ORDER if model == MODEL_BEST or model in models]


def observed_points_for_scope(data: AnalysisReviewData, scope: str) -> list[dict[str, float | str]]:
    scope = str(scope or "").strip()
    points: list[dict[str, float | str]] = []
    for row in data.curve_rows:
        if str(row.get("scope") or "").strip() != scope:
            continue
        x = _as_float(row.get("soa_ms"), math.nan)
        if not math.isfinite(x):
            continue
        metric = str(row.get("fit_metric") or "").strip()
        y = _metric_value(row, metric)
        if y is None:
            continue
        points.append({"x": x, "y": y, "metric": metric or _metric_name(row)})
    return sorted(points, key=lambda item: float(item["x"]))


def prediction_points_for_scope(
    data: AnalysisReviewData,
    scope: str,
    model: str,
    *,
    sample_count: int = 120,
) -> list[dict[str, float]]:
    fit = fit_row_for_scope(data, scope, model)
    observed = observed_points_for_scope(data, scope)
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


def scope_comparison_row(data: AnalysisReviewData, scope: str) -> dict[str, Any]:
    scope = str(scope or "").strip()
    row = next((item for item in data.model_comparison_rows if str(item.get("scope") or "").strip() == scope), None)
    return dict(row or {"scope": scope, "best_model": best_model_for_scope(data, scope)})


def _output_path(outputs: dict[str, Any], key: str, session_dir: Path | None, pattern: str) -> Path | None:
    raw = outputs.get(key)
    if raw not in (None, ""):
        return Path(raw)
    if session_dir is None:
        return None
    analysis_dir = session_dir / "analysis"
    matches = sorted(analysis_dir.glob(pattern)) if analysis_dir.is_dir() else []
    return matches[0] if matches else None


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


def _metric_name(row: dict[str, Any]) -> str:
    if row.get("facilitation_ms") not in (None, ""):
        return "facilitation_ms"
    return "mean_rt_ms"


def _metric_value(row: dict[str, Any], metric: str) -> float | None:
    candidates = [metric] if metric else []
    candidates.extend(["facilitation_ms", "mean_rt_ms"])
    for key in candidates:
        value = _as_float(row.get(key), math.nan)
        if math.isfinite(value):
            return value
    return None


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


def _as_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default
