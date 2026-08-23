from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from peripersonal_space_toolkit.analysis_catalog import (
    PARTICIPANT_POOL_DIRNAME,
    analysis_catalog_path,
    load_analysis_dataset,
    refresh_analysis_browser_outputs,
)
from peripersonal_space_toolkit.analysis_review import (
    CONDITION_LENS_TWO_BY_TWO,
    METRIC_HIT_RATE,
    MODEL_BEST,
    MODEL_COMPARE_ALL,
    PARTS_POOLED,
    PARTS_SEPARATE,
    SIGNAL_EXPECTED,
    AnalysisReviewData,
    artifact_rows_for_review,
    available_models_for_scope,
    behavior_signal_counts,
    behavior_signals_for_scope,
    best_model_for_scope,
    condition_lens_baseline_status,
    condition_lens_button_rows,
    condition_lens_metric_label,
    condition_lens_observed_series,
    condition_lens_prediction_series,
    default_condition_model,
    fit_row_for_scope,
    load_analysis_review_data,
    model_button_rows,
    observed_points_for_scope,
    prediction_points_for_scope,
    prediction_series_for_scope,
    raw_points_for_scope,
    recording_quality_status,
    scopes_for_part_mode,
)
from peripersonal_space_toolkit.output_layout import output_data_analytics_dir, output_runner_logs_dir
from peripersonal_space_toolkit.session_analysis import analyze_analysis_ready_trials, analyze_session_events, write_analysis_csvs


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _basic_assumption_rows(
    *,
    baseline_kind: str = "flat",
    audio_kind: str = "flat",
    soas: tuple[int, ...] = (100, 200, 400, 800),
    baseline_repeats: int = 8,
    audio_repeats: int = 10,
    nuisance_imbalance: bool = False,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    trial_index = 0
    for repeat in range(baseline_repeats):
        for soa_index, soa in enumerate(soas):
            trial_index += 1
            if baseline_kind == "sloped":
                rt = 470.0 - soa_index * 35.0 + (repeat % 3 - 1) * 1.0
            else:
                rt = 410.0 + (repeat % 3 - 1) * 2.0
            rows.append(
                _basic_assumption_row(
                    trial_index,
                    "Baseline",
                    soa,
                    rt,
                    repeat=repeat,
                    soa_index=soa_index,
                    nuisance_imbalance=nuisance_imbalance,
                )
            )
    for repeat in range(audio_repeats):
        for soa_index, soa in enumerate(soas):
            trial_index += 1
            if audio_kind == "pps":
                rt = 480.0 - soa_index * 55.0 + (repeat % 4 - 1.5) * 3.0
            elif audio_kind == "opposite":
                rt = 300.0 + soa_index * 35.0 + (repeat % 4 - 1.5) * 3.0
            else:
                rt = 390.0 + (repeat % 4 - 1.5) * 3.0
            rows.append(
                _basic_assumption_row(
                    trial_index,
                    "Audio-Tactile",
                    soa,
                    rt,
                    repeat=repeat,
                    soa_index=soa_index,
                    nuisance_imbalance=nuisance_imbalance,
                )
            )
    return rows


def _basic_assumption_row(
    trial_index: int,
    trial_type: str,
    soa: int,
    rt: float,
    *,
    repeat: int,
    soa_index: int,
    nuisance_imbalance: bool,
) -> dict[str, object]:
    if nuisance_imbalance:
        part_number = 1 if soa_index == 0 else 2
        phase = "Inhale" if soa_index != 1 else "Exhale"
        noise = "pink" if repeat % 2 else "white"
    else:
        part_number = 1
        phase = "Inhale"
        noise = "pink"
    return {
        "trial_uid": f"{trial_type[:1]}{trial_index:03d}",
        "trial_type": trial_type,
        "hit": True,
        "soa_ms": soa,
        "rt_ms": rt,
        "part_number": part_number,
        "respiratory_phase": phase,
        "noise_type": noise,
        "primary_analysis_included": True,
    }


def test_analysis_review_loads_existing_outputs_and_predicts_model_curves(tmp_path: Path):
    analysis_dir = tmp_path / "analysis"
    curve_path = analysis_dir / "S001_pps_curve_points.csv"
    fit_path = analysis_dir / "S001_model_fits.csv"
    comparison_path = analysis_dir / "S001_model_fit_comparison.csv"
    summary_path = analysis_dir / "S001_summary.csv"
    final_path = analysis_dir / "S001_final_trial_outcomes.csv"
    behavior_path = analysis_dir / "data_behavior_by_scope.csv"
    behavior_summary_path = analysis_dir / "exploratory_quality_summary.json"
    scope = "Part 1 / Inhale / pink"
    _write_csv(
        curve_path,
        [
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "soa_ms": 100, "fit_metric": "facilitation_ms", "facilitation_ms": 10.0, "facilitation_sem_ms": 2.0, "mean_rt_ms": 320},
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "soa_ms": 200, "fit_metric": "facilitation_ms", "facilitation_ms": 20.0, "facilitation_sem_ms": 2.0, "mean_rt_ms": 300},
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "soa_ms": 400, "fit_metric": "facilitation_ms", "facilitation_ms": 35.0, "facilitation_sem_ms": 2.0, "mean_rt_ms": 280},
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "soa_ms": 800, "fit_metric": "facilitation_ms", "facilitation_ms": 44.0, "facilitation_sem_ms": 2.0, "mean_rt_ms": 260},
            {"scope": "All parts / Inhale / pink", "aggregation_mode": PARTS_POOLED, "soa_ms": 100, "fit_metric": "facilitation_ms", "facilitation_ms": 12.0, "facilitation_sem_ms": 3.0, "mean_rt_ms": 318},
        ],
    )
    _write_csv(
        fit_path,
        [
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "model": "linear", "intercept": 8.0, "slope": 0.05, "aic": 14.0, "r2": 0.91, "rmse": 2.0, "fit_metric": "facilitation_ms", "n_points": 4},
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "model": "logarithmic_decay", "intercept": -12.0, "log_slope": 8.0, "aic": 12.0, "r2": 0.94, "rmse": 1.6, "fit_metric": "facilitation_ms", "n_points": 4},
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "model": "sigmoid", "lower": 5.0, "upper": 50.0, "pps_boundary_soa_ms": 300.0, "slope": 0.01, "aic": 10.0, "r2": 0.97, "rmse": 1.1, "fit_metric": "facilitation_ms", "n_points": 4},
            {"scope": "All parts / Inhale / pink", "aggregation_mode": PARTS_POOLED, "model": "linear", "intercept": 10.0, "slope": 0.04, "aic": 20.0, "r2": 0.80, "rmse": 4.0, "fit_metric": "facilitation_ms", "n_points": 4},
        ],
    )
    _write_csv(
        comparison_path,
        [
            {"scope": scope, "aggregation_mode": PARTS_SEPARATE, "best_model": "sigmoid", "best_aic": 10.0, "best_r2": 0.97, "fit_metric": "facilitation_ms", "n_points": 4},
            {"scope": "All parts / Inhale / pink", "aggregation_mode": PARTS_POOLED, "best_model": "linear", "best_aic": 20.0, "best_r2": 0.80, "fit_metric": "facilitation_ms", "n_points": 4},
        ],
    )
    _write_csv(summary_path, [{"scope": scope, "n": 4, "hit_rate": 1.0}])
    _write_csv(
        final_path,
        [
            {"part_number": 1, "condition": "", "respiratory_phase": "Inhale", "noise_type": "pink", "soa_ms": 100, "rt_ms": 310, "hit": True},
            {"part_number": 1, "condition": "", "respiratory_phase": "Inhale", "noise_type": "pink", "soa_ms": 100, "rt_ms": 330, "hit": True},
            {"part_number": 1, "condition": "", "respiratory_phase": "Inhale", "noise_type": "pink", "soa_ms": 200, "rt_ms": 300, "hit": True},
            {"part_number": 1, "condition": "", "respiratory_phase": "Inhale", "noise_type": "pink", "soa_ms": 200, "rt_ms": "", "hit": False},
        ],
    )
    _write_csv(
        behavior_path,
        [
            {
                "scope": scope,
                "aggregation_mode": PARTS_SEPARATE,
                "signal": SIGNAL_EXPECTED,
                "feature": "RT or facilitation by SOA/distance",
                "message": "The recording has enough SOA/distance points for common PPS curve review.",
                "evidence": "points=4",
            }
        ],
    )
    behavior_summary_path.write_text(
        json.dumps(
            {
                "schema": "pps-exploratory-data-behavior.v1",
                "interpretation_note": "Exploratory data-behavior signals are not scientific conclusions.",
                "signal_counts": {SIGNAL_EXPECTED: 1},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    data = load_analysis_review_data(
        {
            "curves": curve_path,
            "model_fits": fit_path,
            "model_fit_comparison": comparison_path,
            "summary": summary_path,
            "final_trial_outcomes": final_path,
            "data_behavior_by_scope": behavior_path,
            "exploratory_quality_summary": behavior_summary_path,
        },
        session_dir=tmp_path,
        summary_text="summary",
    )

    assert data.has_analysis_tables
    assert data.scopes == [scope]
    assert data.part_modes == [PARTS_SEPARATE, PARTS_POOLED]
    assert scopes_for_part_mode(data, PARTS_POOLED) == ["All parts / Inhale / pink"]
    assert best_model_for_scope(data, scope) == "sigmoid"
    assert best_model_for_scope(data, "All parts / Inhale / pink", PARTS_POOLED) == "linear"
    assert fit_row_for_scope(data, scope, MODEL_BEST)["model"] == "sigmoid"
    assert available_models_for_scope(data, scope) == ["best", "compare_all", "sigmoid", "linear", "logarithmic_decay"]
    observed = observed_points_for_scope(data, scope)
    assert [point["x"] for point in observed] == [100.0, 200.0, 400.0, 800.0]
    assert observed[0]["y_low"] == pytest.approx(8.0)
    assert observed[0]["y_high"] == pytest.approx(12.0)
    assert observed[0]["spread_label"] == "SEM"
    linear = prediction_points_for_scope(data, scope, "linear", sample_count=3)
    assert linear[0]["y"] == pytest.approx(13.0)
    sigmoid = prediction_points_for_scope(data, scope, "sigmoid", sample_count=5)
    assert len(sigmoid) == 5
    assert sigmoid[0]["y"] < sigmoid[-1]["y"]
    comparison_series = prediction_series_for_scope(data, scope, MODEL_COMPARE_ALL, sample_count=7)
    assert [series["model"] for series in comparison_series] == ["sigmoid", "linear", "logarithmic_decay"]
    assert all(len(series["points"]) == 7 for series in comparison_series)
    assert behavior_signal_counts(data)[SIGNAL_EXPECTED] == 1
    assert behavior_signals_for_scope(data, scope)[0]["signal"] == SIGNAL_EXPECTED
    hit_rate_points = observed_points_for_scope(data, scope, metric=METRIC_HIT_RATE)
    assert [point["y"] for point in hit_rate_points] == [1.0, 0.5]
    raw_points = raw_points_for_scope(data, scope)
    assert [point["y"] for point in raw_points] == [310.0, 330.0, 300.0]
    artifacts = artifact_rows_for_review(data)
    assert any(row["artifact"] == "data behavior" and row["available"] == "yes" for row in artifacts)
    assert "not scientific conclusions" in data.exploratory_quality_summary["interpretation_note"]


def test_analysis_review_handles_curve_points_without_model_fit():
    scope = "Part 1 / Exhale / pink"
    data = AnalysisReviewData(curve_rows=[{"scope": scope, "soa_ms": 300, "mean_rt_ms": 250, "fit_metric": "mean_rt_ms"}])

    assert data.has_analysis_tables
    assert data.scopes == [scope]
    assert best_model_for_scope(data, scope) == ""
    assert fit_row_for_scope(data, scope, "sigmoid") is None
    assert prediction_points_for_scope(data, scope, "sigmoid") == []


def test_session_analysis_writes_condition_lens_outputs_and_quality_gate(tmp_path: Path):
    events = []
    event_id = 1
    soas = (100, 200, 400, 800)
    for part in (1, 2):
        for state_index, state in enumerate(("Inhale", "Exhale")):
            for repeat in range(2):
                for soa_index, soa in enumerate(soas):
                    onset = len(events) * 0.5 + 10.0
                    rt_s = 0.42 - soa_index * 0.035 + state_index * 0.005 + repeat * 0.002
                    context = {
                        "participant_id": "S001",
                        "part_number": part,
                        "block_number": part,
                        "trial_number": len(events) + 1,
                        "trial_uid": f"P{part}_{state}_{repeat}_{soa}",
                        "trial_type": "Audio-Tactile",
                        "soa_ms": soa,
                        "respiratory_phase": state,
                        "noise_type": "pink" if repeat == 0 else "white",
                        "sequence_labels": "Pink moving sound - receding" if repeat == 0 else "White moving sound - looming",
                        "sequence_variant_key": "pink_receding" if repeat == 0 else "white_looming",
                        "timestamp_quality": "dac_time_sample_exact",
                    }
                    events.append({"event_id": event_id, "event_type": "trial_start", "unix_time": onset - 0.25, **context})
                    event_id += 1
                    events.append({"event_id": event_id, "event_type": "tactile_onset", "unix_time": onset, **context})
                    event_id += 1
                    events.append(
                        {
                            "event_id": event_id,
                            "event_type": "mouse_click",
                            "unix_time": onset + rt_s,
                            "in_target": True,
                            "during_playback": True,
                            "part_number": part,
                            "block_number": part,
                        }
                    )
                    event_id += 1

    result = analyze_session_events(events)
    outputs = write_analysis_csvs(result, tmp_path, "S001")

    assert result.response_rows[0]["sequence_labels"] == "Pink moving sound - receding"
    assert result.response_rows[0]["sequence_variant_key"] == "pink_receding"
    assert outputs["condition_lens_curves"].exists()
    assert outputs["condition_lens_model_fits"].exists()
    assert outputs["condition_lens_model_fit_comparison"].exists()
    assert outputs["condition_lens_triage_summary"].exists()
    assert outputs["recording_quality_gate"].exists()
    assert outputs["basic_assumption_checks"].exists()
    assert result.recording_quality_gate["status"] == "PASS"
    assert result.basic_assumption_checks["schema"] == "pps-basic-assumption-checks.v1"
    assert {row["analysis_lens"] for row in result.condition_lens_curve_rows}.issuperset({"two_by_two", "part", "state", "overall"})
    two_by_two_scopes = {row["display_scope"] for row in result.condition_lens_curve_rows if row["analysis_lens"] == "two_by_two"}
    assert two_by_two_scopes == {"Part 1 / Inhale", "Part 1 / Exhale", "Part 2 / Inhale", "Part 2 / Exhale"}
    assert all(row["noise_type"] == "All sources" for row in result.condition_lens_curve_rows)

    data = load_analysis_review_data(outputs, session_dir=tmp_path)
    status, reason = recording_quality_status(data)
    assert status == "PASS"
    assert "No serious exclusion criteria" in reason
    assert data.assumption_checks["schema"] == "pps-basic-assumption-checks.v1"
    assert default_condition_model(data) in {"linear", "logarithmic_decay", "sigmoid"}
    observed = condition_lens_observed_series(data, CONDITION_LENS_TWO_BY_TWO)
    assert [series["label"] for series in observed] == ["Part 1 / Inhale", "Part 1 / Exhale", "Part 2 / Inhale", "Part 2 / Exhale"]
    predictions = condition_lens_prediction_series(data, CONDITION_LENS_TWO_BY_TWO, default_condition_model(data), sample_count=5)
    assert predictions
    assert {row["label"] for row in condition_lens_button_rows(data)} == {"2 x 2", "Part 1 | Part 2", "Inhale | Exhale"}
    assert {row["model"] for row in model_button_rows(data)} == {"sigmoid", "logarithmic_decay", "linear"}
    analysis_rows = list(csv.DictReader(outputs["analysis_ready_trials"].open(encoding="utf-8")))
    assert analysis_rows[0]["sequence_labels"] == "Pink moving sound - receding"
    assert analysis_rows[0]["sequence_variant_key"] == "pink_receding"


def test_analysis_displays_part_labels_while_preserving_part_number_order():
    rows: list[dict[str, object]] = []
    for part_number, part_label in ((1, "Pre"), (2, "Post")):
        for trial_type, rt_base in (("Baseline", 500.0), ("Audio-Tactile", 430.0)):
            for soa in (100, 200, 400, 800):
                for repeat in range(4):
                    rows.append(
                        {
                            "trial_uid": f"P{part_number}-{trial_type[0]}-{soa}-{repeat}",
                            "trial_type": trial_type,
                            "hit": True,
                            "soa_ms": soa,
                            "rt_ms": rt_base - (soa / 100.0) + repeat,
                            "part_number": part_number,
                            "part_label": part_label,
                            "respiratory_phase": "Inhale",
                            "noise_type": "pink",
                            "primary_analysis_included": True,
                        }
                    )

    result = analyze_analysis_ready_trials(rows)

    two_by_two = [
        row
        for row in result.condition_lens_curve_rows
        if row.get("analysis_lens") == CONDITION_LENS_TWO_BY_TWO and int(float(row.get("soa_ms"))) == 100
    ]
    assert [row["part_label"] for row in two_by_two] == ["Pre (Part 1)", "Post (Part 2)"]
    assert [int(row["part_number"]) for row in two_by_two] == [1, 2]
    assert [row["display_scope"] for row in two_by_two] == ["Pre (Part 1) / Inhale", "Post (Part 2) / Inhale"]
    separate = [
        row
        for row in result.curve_rows
        if row.get("aggregation_mode") == PARTS_SEPARATE and int(float(row.get("soa_ms"))) == 100
    ]
    assert [int(row["part_number"]) for row in separate] == [1, 2]
    assert [row["scope"] for row in separate] == ["Pre (Part 1) / Inhale / pink", "Post (Part 2) / Inhale / pink"]


def test_basic_assumption_baseline_green_when_no_significant_proximity_trend():
    result = analyze_analysis_ready_trials(_basic_assumption_rows(audio_kind="flat"))
    baseline = result.basic_assumption_checks["baseline_assumption"]

    assert baseline["status"] == "PASS"
    assert baseline["reason_code"] == "baseline_proximity_not_significant"
    assert baseline["coverage"]["n"] == 32
    assert baseline["coverage"]["distinct_soa_count"] == 4
    assert baseline["p_two_sided"] >= 0.05


def test_basic_assumption_baseline_red_when_baseline_varies_by_proximity():
    result = analyze_analysis_ready_trials(_basic_assumption_rows(baseline_kind="sloped", audio_kind="flat"))
    baseline = result.basic_assumption_checks["baseline_assumption"]

    assert baseline["status"] == "FAIL"
    assert baseline["reason_code"] == "baseline_proximity_significant"
    assert baseline["beta"] < 0
    assert baseline["p_two_sided"] < 0.05


def test_basic_assumption_pps_green_when_audio_tactile_speeds_up_more_than_baseline():
    result = analyze_analysis_ready_trials(_basic_assumption_rows(audio_kind="pps"))
    pps = result.basic_assumption_checks["peripersonal_space_assumption"]

    assert pps["status"] == "PASS"
    assert pps["reason_code"] == "interaction_predicted_significant"
    assert pps["interaction_beta"] < 0
    assert pps["p_one_sided_negative"] < 0.05
    assert pps["pps_far_to_near_gain_ms"] > 0


def test_basic_assumption_pps_red_when_flat_opposite_or_undercovered():
    flat = analyze_analysis_ready_trials(_basic_assumption_rows(audio_kind="flat")).basic_assumption_checks["peripersonal_space_assumption"]
    opposite = analyze_analysis_ready_trials(_basic_assumption_rows(audio_kind="opposite")).basic_assumption_checks["peripersonal_space_assumption"]
    undercovered = analyze_analysis_ready_trials(
        _basic_assumption_rows(audio_kind="pps", soas=(100, 200), baseline_repeats=3, audio_repeats=4)
    ).basic_assumption_checks["peripersonal_space_assumption"]

    assert flat["status"] == "FAIL"
    assert flat["reason_code"] == "interaction_not_significant"
    assert opposite["status"] == "FAIL"
    assert opposite["reason_code"] == "interaction_sign_opposite_or_zero"
    assert undercovered["status"] == "FAIL"
    assert undercovered["reason_code"] in {"audio_tactile_valid_rt_count_low", "audio_tactile_distinct_soa_count_low"}


def test_basic_assumption_handles_unequal_repetitions_and_missing_middle_soas():
    rows: list[dict[str, object]] = []
    trial_index = 0
    soas = (100, 400, 1200)
    for repeat, soa in enumerate([100, 100, 100, 400, 1200, 1200, 1200, 1200]):
        trial_index += 1
        rows.append(
            _basic_assumption_row(
                trial_index,
                "Baseline",
                soa,
                410.0 + (repeat % 2) * 2.0,
                repeat=repeat,
                soa_index=soas.index(soa),
                nuisance_imbalance=True,
            )
        )
    for repeat, soa in enumerate([100] * 4 + [400] * 5 + [1200] * 6):
        trial_index += 1
        soa_index = soas.index(soa)
        rows.append(
            _basic_assumption_row(
                trial_index,
                "Audio-Tactile",
                soa,
                480.0 - soa_index * 70.0 + (repeat % 3 - 1) * 3.0,
                repeat=repeat,
                soa_index=soa_index,
                nuisance_imbalance=True,
            )
        )

    checks = analyze_analysis_ready_trials(rows).basic_assumption_checks
    pps = checks["peripersonal_space_assumption"]

    assert checks["proximity_coding"]["method"] == "centered_soa_rank"
    assert checks["proximity_coding"]["levels"] == [100.0, 400.0, 1200.0]
    assert pps["status"] == "PASS"
    assert pps["coverage"]["audio_tactile"]["counts_by_soa_ms"] == {"100": 4, "400": 5, "1200": 6}
    assert pps["coverage"]["baseline"]["counts_by_soa_ms"] == {"100": 3, "400": 1, "1200": 4}
    assert set(pps["dropped_nuisance_terms"]).issuperset({"noise_type", "respiratory_phase"})


def test_basic_assumption_nuisance_imbalance_only_changes_nuisance_adjusted_estimation():
    balanced = analyze_analysis_ready_trials(_basic_assumption_rows(audio_kind="pps")).basic_assumption_checks["peripersonal_space_assumption"]
    imbalanced = analyze_analysis_ready_trials(
        _basic_assumption_rows(audio_kind="pps", nuisance_imbalance=True)
    ).basic_assumption_checks["peripersonal_space_assumption"]

    assert balanced["status"] == "PASS"
    assert imbalanced["status"] == "PASS"
    assert imbalanced["interaction_beta"] == pytest.approx(balanced["interaction_beta"], abs=1e-12)
    assert set(imbalanced["included_nuisance_terms"]).issuperset({"part_number", "respiratory_phase", "noise_type"})


def test_session_analysis_quality_gate_fails_serious_exclusion_criteria():
    events = []
    for index, soa in enumerate((100, 200, 400, 800), start=1):
        events.append(
            {
                "event_id": index,
                "event_type": "tactile_onset",
                "unix_time": float(index),
                "trial_uid": f"T{index}",
                "trial_type": "Audio-Tactile",
                "soa_ms": soa,
                "part_number": 1,
                "respiratory_phase": "Inhale",
            }
        )

    result = analyze_session_events(events)

    assert result.recording_quality_gate["status"] == "FAIL"
    failure_codes = {row["code"] for row in result.recording_quality_gate["failures"]}
    assert "overall_hit_rate_below_70pct" in failure_codes


def test_session_analysis_writes_exploratory_data_behavior_outputs(tmp_path: Path):
    events = []
    event_id = 1

    def add_trial(index: int, trial_type: str, soa_ms: int, onset_s: float, rt_s: float) -> None:
        nonlocal event_id
        payload = {
            "participant_id": "S001",
            "part_number": 1,
            "block_number": 1,
            "trial_number": index,
            "trial_uid": f"T{index:03d}",
            "trial_type": trial_type,
            "soa_ms": soa_ms,
            "respiratory_phase": "Inhale",
            "noise_type": "pink",
            "timestamp_quality": "dac_time_sample_exact",
        }
        events.append({"event_id": event_id, "event_type": "trial_start", "unix_time": onset_s - 0.1, **payload})
        event_id += 1
        events.append({"event_id": event_id, "event_type": "tactile_onset", "unix_time": onset_s, **payload})
        event_id += 1
        events.append(
            {
                "event_id": event_id,
                "event_type": "mouse_click",
                "unix_time": onset_s + rt_s,
                "in_target": True,
                "during_playback": True,
                "part_number": 1,
                "block_number": 1,
                "timestamp_quality": "dac_time_sample_exact",
            }
        )
        event_id += 1

    for index, soa in enumerate((100, 200, 400, 800), start=1):
        add_trial(index, "Baseline", soa, index * 10.0, 0.42)
        add_trial(index + 10, "Audio-Tactile", soa, index * 10.0 + 5.0, 0.36 - index * 0.025)

    result = analyze_session_events(events)
    outputs = write_analysis_csvs(result, tmp_path, "S001")

    assert outputs["data_behavior_by_scope"].exists()
    assert outputs["exploratory_quality_summary"].exists()
    rows = list(csv.DictReader(outputs["data_behavior_by_scope"].open(encoding="utf-8")))
    summary = json.loads(outputs["exploratory_quality_summary"].read_text(encoding="utf-8"))
    assert rows
    assert summary["schema"] == "pps-exploratory-data-behavior.v1"
    assert "not scientific conclusions" in summary["interpretation_note"]
    assert {row["signal"] for row in rows}.intersection({"Expected pattern", "Mixed / ambiguous", "Insufficient evidence"})
    assert "pass" not in json.dumps(summary).lower()
    assert "fail" not in json.dumps(summary).lower()


def test_session_analysis_pools_baseline_across_soas_within_condition_scope() -> None:
    events = []
    event_id = 1

    def add_trial(
        *,
        index: int,
        trial_type: str,
        soa_ms: int,
        onset_s: float,
        rt_s: float,
        part_number: int,
        phase: str,
        noise: str = "pink",
    ) -> None:
        nonlocal event_id
        payload = {
            "participant_id": "S001",
            "part_number": part_number,
            "block_number": 1,
            "trial_number": index,
            "trial_uid": f"T{index:03d}",
            "trial_type": trial_type,
            "soa_ms": soa_ms,
            "respiratory_phase": phase,
            "noise_type": noise,
            "timestamp_quality": "dac_time_sample_exact",
        }
        events.append({"event_id": event_id, "event_type": "trial_start", "unix_time": onset_s - 0.1, **payload})
        event_id += 1
        events.append({"event_id": event_id, "event_type": "tactile_onset", "unix_time": onset_s, **payload})
        event_id += 1
        events.append(
            {
                "event_id": event_id,
                "event_type": "mouse_click",
                "unix_time": onset_s + rt_s,
                "in_target": True,
                "during_playback": True,
                "part_number": part_number,
                "block_number": 1,
                "timestamp_quality": "dac_time_sample_exact",
            }
        )
        event_id += 1

    add_trial(index=1, trial_type="Baseline", soa_ms=100, onset_s=1.0, rt_s=0.400, part_number=1, phase="Inhale")
    add_trial(index=2, trial_type="Baseline", soa_ms=800, onset_s=2.0, rt_s=0.500, part_number=1, phase="Inhale")
    add_trial(index=3, trial_type="Audio-Tactile", soa_ms=100, onset_s=3.0, rt_s=0.350, part_number=1, phase="Inhale")
    add_trial(index=4, trial_type="Audio-Tactile", soa_ms=800, onset_s=4.0, rt_s=0.300, part_number=1, phase="Inhale")
    add_trial(index=5, trial_type="Baseline", soa_ms=100, onset_s=5.0, rt_s=0.610, part_number=1, phase="Exhale")
    add_trial(index=6, trial_type="Audio-Tactile", soa_ms=100, onset_s=6.0, rt_s=0.500, part_number=1, phase="Exhale")

    result = analyze_session_events(events)

    inhale_rows = [
        row
        for row in result.condition_lens_curve_rows
        if row.get("analysis_lens") == CONDITION_LENS_TWO_BY_TWO and row.get("display_scope") == "Part 1 / Inhale"
    ]
    assert {int(row["soa_ms"]) for row in inhale_rows} == {100, 800}
    assert [float(row["baseline_mean_rt_ms"]) for row in inhale_rows] == pytest.approx([450.0, 450.0])
    assert {row["baseline_source_soas_ms"] for row in inhale_rows} == {"100;800"}
    assert {row["baseline_n"] for row in inhale_rows} == {2}
    assert {row["baseline_correction_method"] for row in inhale_rows} == {"condition_mean_pooled_soa"}
    assert {int(row["soa_ms"]): float(row["facilitation_ms"]) for row in inhale_rows} == pytest.approx({100: 100.0, 800: 150.0})

    exhale_row = next(
        row
        for row in result.condition_lens_curve_rows
        if row.get("analysis_lens") == CONDITION_LENS_TWO_BY_TWO and row.get("display_scope") == "Part 1 / Exhale"
    )
    assert float(exhale_row["baseline_mean_rt_ms"]) == 610.0
    assert float(exhale_row["facilitation_ms"]) == 110.0

    legacy_inhale = [
        row
        for row in result.curve_rows
        if row.get("aggregation_mode") == PARTS_SEPARATE and row.get("scope") == "Part 1 / Inhale / pink"
    ]
    assert [float(row["baseline_mean_rt_ms"]) for row in legacy_inhale] == pytest.approx([450.0, 450.0])
    assert {row["baseline_source_soas_ms"] for row in legacy_inhale} == {"100;800"}


def test_condition_lens_metric_label_reports_baseline_corrected_status() -> None:
    data = AnalysisReviewData(
        condition_lens_curve_rows=[
            {
                "analysis_lens": CONDITION_LENS_TWO_BY_TWO,
                "display_scope": "Part 1 / Inhale",
                "fit_metric": "facilitation_ms",
                "facilitation_ms": 25,
                "baseline_correction_method": "condition_mean_pooled_soa",
            }
        ]
    )

    assert condition_lens_metric_label(data, CONDITION_LENS_TWO_BY_TWO) == "Baseline-corrected facilitation (ms)"
    assert condition_lens_baseline_status(data, CONDITION_LENS_TWO_BY_TWO) == "Baseline: pooled across SOAs within condition"


def _write_saved_trial_analysis(
    output_root: Path,
    leaf: Path,
    stem: str,
    participant_id: str,
    *,
    baseline_rt: float,
    audio_rt_by_soa: dict[int, float],
    audio_repeats: int = 1,
    quality_status: str = "PASS",
) -> dict[str, Path]:
    rows: list[dict[str, object]] = []
    trial = 1
    for soa in sorted(audio_rt_by_soa):
        for repeat in range(audio_repeats):
            rows.append(
                {
                    "participant_id": participant_id,
                    "trial_uid": f"{participant_id}_A{trial:03d}_{repeat}",
                    "trial_type": "Audio-Tactile",
                    "part_number": 1,
                    "respiratory_phase": "Inhale",
                    "noise_type": "pink",
                    "soa_ms": soa,
                    "rt_ms": audio_rt_by_soa[soa],
                    "hit": True,
                    "primary_analysis_included": True,
                }
            )
        trial += 1
    for soa in sorted(audio_rt_by_soa):
        rows.append(
            {
                "participant_id": participant_id,
                "trial_uid": f"{participant_id}_B{trial:03d}",
                "trial_type": "Baseline",
                "part_number": 1,
                "respiratory_phase": "Inhale",
                "noise_type": "pink",
                "soa_ms": soa,
                "rt_ms": baseline_rt,
                "hit": True,
                "primary_analysis_included": True,
            }
        )
        trial += 1
    result = analyze_analysis_ready_trials(rows)
    analysis_dir = output_data_analytics_dir(output_root) / leaf
    outputs = write_analysis_csvs(result, analysis_dir, stem)
    quality = {
        "schema": "pps-recording-quality-gate.v1",
        "status": quality_status,
        "primary_reason": "No serious exclusion criteria were triggered." if quality_status == "PASS" else "Injected test exclusion.",
        "failures": [] if quality_status == "PASS" else [{"code": "test_fail", "message": "Injected test exclusion.", "evidence": "test"}],
        "warnings": [],
        "metrics": {"overall_hit_rate": 1.0},
    }
    outputs["recording_quality_gate"].write_text(json.dumps(quality, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (analysis_dir / "analysis_summary.txt").write_text("Saved participant analysis\n", encoding="utf-8")
    return outputs


def test_analysis_catalog_builds_pass_only_participant_balanced_pool(tmp_path: Path) -> None:
    soas = {100: 400.0, 200: 390.0, 400: 380.0, 800: 370.0}
    _write_saved_trial_analysis(
        tmp_path,
        Path("P001_session"),
        "P001_session",
        "P001",
        baseline_rt=500.0,
        audio_rt_by_soa=soas,
        audio_repeats=1,
        quality_status="PASS",
    )
    _write_saved_trial_analysis(
        tmp_path,
        Path("P002_session"),
        "P002_session",
        "P002",
        baseline_rt=600.0,
        audio_rt_by_soa={100: 590.0, 200: 580.0, 400: 570.0, 800: 560.0},
        audio_repeats=10,
        quality_status="PASS",
    )
    _write_saved_trial_analysis(
        tmp_path,
        Path("P003_session"),
        "P003_session",
        "P003",
        baseline_rt=700.0,
        audio_rt_by_soa={100: 100.0, 200: 100.0, 400: 100.0, 800: 100.0},
        audio_repeats=10,
        quality_status="FAIL",
    )

    catalog = refresh_analysis_browser_outputs(tmp_path)

    assert analysis_catalog_path(tmp_path).exists()
    assert (output_data_analytics_dir(tmp_path) / "P001").exists()
    assert (output_data_analytics_dir(tmp_path) / "P002").exists()
    assert (output_data_analytics_dir(tmp_path) / "P003").exists()
    participant_entries = [entry for entry in catalog.selectable_entries if entry["dataset_kind"] == "participant"]
    assert [entry["participant_id"] for entry in participant_entries] == ["P001", "P002", "P003"]
    pool_entry = next(entry for entry in catalog.selectable_entries if entry["dataset_kind"] == "participant_pool")
    assert pool_entry["pool_included_count"] == 2
    assert pool_entry["pool_excluded_count"] == 1
    assert Path(pool_entry["analysis_dir"]).parent == output_data_analytics_dir(tmp_path)
    assert Path(pool_entry["analysis_dir"]).name == PARTICIPANT_POOL_DIRNAME
    data = load_analysis_dataset(pool_entry)
    pool_row = next(
        row
        for row in data.condition_lens_curve_rows
        if row.get("analysis_lens") == CONDITION_LENS_TWO_BY_TWO
        and row.get("display_scope") == "Part 1 / Inhale"
        and int(float(row.get("soa_ms"))) == 100
    )
    assert float(pool_row["facilitation_ms"]) == pytest.approx(55.0)
    assert int(float(pool_row["n"])) == 2
    assert data.quality_label == "Participant Pool Quality"
    assert recording_quality_status(data)[0] == "PASS"


def test_analysis_catalog_waits_for_complete_split_participant_before_combining(tmp_path: Path) -> None:
    group = "P001_20260613_120000"
    _write_saved_trial_analysis(
        tmp_path,
        Path(group) / "part_01",
        f"{group}_part01",
        "P001",
        baseline_rt=500.0,
        audio_rt_by_soa={100: 410.0, 200: 400.0, 400: 390.0, 800: 380.0},
        quality_status="PASS",
    )
    _write_saved_trial_analysis(
        tmp_path,
        Path(group) / "part_02",
        f"{group}_part02",
        "P001",
        baseline_rt=510.0,
        audio_rt_by_soa={100: 420.0, 200: 410.0, 400: 400.0, 800: 390.0},
        quality_status="PASS",
    )
    manifest = output_runner_logs_dir(tmp_path) / group / "session_group_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "pps-session-group-manifest.v1",
        "session_group_id": group,
        "participant_id": "P001",
        "parts": [
            {"part_number": 1, "part_folder_name": "part_01", "completed": True},
            {"part_number": 2, "part_folder_name": "part_02", "completed": False},
        ],
    }
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    incomplete = refresh_analysis_browser_outputs(tmp_path)
    assert not any(entry["dataset_kind"] == "participant" for entry in incomplete.selectable_entries)
    assert not (output_data_analytics_dir(tmp_path) / "P001").exists()

    payload["parts"][1]["completed"] = True
    manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    complete = refresh_analysis_browser_outputs(tmp_path)

    combined_dir = output_data_analytics_dir(tmp_path) / "P001"
    pool_dir = output_data_analytics_dir(tmp_path) / PARTICIPANT_POOL_DIRNAME
    assert combined_dir.exists()
    assert (combined_dir / "P001_analysis_ready_trials.csv").exists()
    assert pool_dir.exists()
    participant_entries = [entry for entry in complete.selectable_entries if entry["dataset_kind"] == "participant"]
    assert [entry["participant_id"] for entry in participant_entries] == ["P001"]
