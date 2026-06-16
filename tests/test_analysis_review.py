from __future__ import annotations

import csv
from pathlib import Path

import pytest

from peripersonal_space_toolkit.analysis_review import (
    MODEL_BEST,
    AnalysisReviewData,
    available_models_for_scope,
    best_model_for_scope,
    fit_row_for_scope,
    load_analysis_review_data,
    observed_points_for_scope,
    prediction_points_for_scope,
)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_analysis_review_loads_existing_outputs_and_predicts_model_curves(tmp_path: Path):
    analysis_dir = tmp_path / "analysis"
    curve_path = analysis_dir / "S001_pps_curve_points.csv"
    fit_path = analysis_dir / "S001_model_fits.csv"
    comparison_path = analysis_dir / "S001_model_fit_comparison.csv"
    summary_path = analysis_dir / "S001_summary.csv"
    scope = "Part 1 / Inhale / pink"
    _write_csv(
        curve_path,
        [
            {"scope": scope, "soa_ms": 100, "fit_metric": "facilitation_ms", "facilitation_ms": 10.0, "mean_rt_ms": 320},
            {"scope": scope, "soa_ms": 200, "fit_metric": "facilitation_ms", "facilitation_ms": 20.0, "mean_rt_ms": 300},
            {"scope": scope, "soa_ms": 400, "fit_metric": "facilitation_ms", "facilitation_ms": 35.0, "mean_rt_ms": 280},
            {"scope": scope, "soa_ms": 800, "fit_metric": "facilitation_ms", "facilitation_ms": 44.0, "mean_rt_ms": 260},
        ],
    )
    _write_csv(
        fit_path,
        [
            {"scope": scope, "model": "linear", "intercept": 8.0, "slope": 0.05, "aic": 14.0, "r2": 0.91, "rmse": 2.0, "fit_metric": "facilitation_ms", "n_points": 4},
            {"scope": scope, "model": "logarithmic_decay", "intercept": -12.0, "log_slope": 8.0, "aic": 12.0, "r2": 0.94, "rmse": 1.6, "fit_metric": "facilitation_ms", "n_points": 4},
            {"scope": scope, "model": "sigmoid", "lower": 5.0, "upper": 50.0, "pps_boundary_soa_ms": 300.0, "slope": 0.01, "aic": 10.0, "r2": 0.97, "rmse": 1.1, "fit_metric": "facilitation_ms", "n_points": 4},
        ],
    )
    _write_csv(
        comparison_path,
        [{"scope": scope, "best_model": "sigmoid", "best_aic": 10.0, "best_r2": 0.97, "fit_metric": "facilitation_ms", "n_points": 4}],
    )
    _write_csv(summary_path, [{"scope": scope, "n": 4, "hit_rate": 1.0}])

    data = load_analysis_review_data(
        {
            "curves": curve_path,
            "model_fits": fit_path,
            "model_fit_comparison": comparison_path,
            "summary": summary_path,
        },
        session_dir=tmp_path,
        summary_text="summary",
    )

    assert data.has_analysis_tables
    assert data.scopes == [scope]
    assert best_model_for_scope(data, scope) == "sigmoid"
    assert fit_row_for_scope(data, scope, MODEL_BEST)["model"] == "sigmoid"
    assert available_models_for_scope(data, scope) == ["best", "sigmoid", "linear", "logarithmic_decay"]
    assert [point["x"] for point in observed_points_for_scope(data, scope)] == [100.0, 200.0, 400.0, 800.0]
    linear = prediction_points_for_scope(data, scope, "linear", sample_count=3)
    assert linear[0]["y"] == pytest.approx(13.0)
    sigmoid = prediction_points_for_scope(data, scope, "sigmoid", sample_count=5)
    assert len(sigmoid) == 5
    assert sigmoid[0]["y"] < sigmoid[-1]["y"]


def test_analysis_review_handles_curve_points_without_model_fit():
    scope = "Part 1 / Exhale / pink"
    data = AnalysisReviewData(curve_rows=[{"scope": scope, "soa_ms": 300, "mean_rt_ms": 250, "fit_metric": "mean_rt_ms"}])

    assert data.has_analysis_tables
    assert data.scopes == [scope]
    assert best_model_for_scope(data, scope) == ""
    assert fit_row_for_scope(data, scope, "sigmoid") is None
    assert prediction_points_for_scope(data, scope, "sigmoid") == []
