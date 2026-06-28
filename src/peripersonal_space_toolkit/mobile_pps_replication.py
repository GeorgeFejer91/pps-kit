"""Behavioral replication checks for mobile-style audio-tactile PPS data."""

from __future__ import annotations

import csv
import json
import math
import statistics
import warnings as py_warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.optimize import OptimizeWarning, curve_fit
from scipy.special import expit
from scipy import stats

SCHEMA = "pps-mobile-pps-replication.v1"
INPUT_KIND_AUTO = "auto"
INPUT_KIND_OSF_MASTER = "osf-master"
INPUT_KIND_ANALYSIS_READY = "analysis-ready"
TRIAL_AUDIO_TACTILE = "Audio-Tactile"
TRIAL_BASELINE = "Baseline"
TRIAL_CATCH = "Catch"
STATUS_PASS = "PASS"
STATUS_SIGNAL = "SIGNAL"
STATUS_NO_SIGNAL = "NO_SIGNAL"
STATUS_FAIL = "FAIL"
STATUS_DOCUMENT = "DOCUMENT"

DEFAULT_SOA_DISTANCE_MAP = {
    300: 100.0,
    800: 73.0,
    1500: 50.0,
    2200: 27.0,
    2700: 10.0,
}

DISCOVERY_PATTERNS = (
    "**/master_successful_participants.csv",
    "**/*analysis_ready_trials.csv",
    "**/*final_trial_outcomes.csv",
    "**/*_trials.csv",
)


@dataclass(frozen=True)
class ReplicationOptions:
    input_kind: str = INPUT_KIND_AUTO
    soa_distance_map: Mapping[int, float] = field(default_factory=lambda: dict(DEFAULT_SOA_DISTANCE_MAP))
    min_hit_rate: float = 0.70
    max_catch_fa_rate: float = 0.30
    anticipation_ms: float = 200.0
    outlier_sd: float = 2.5
    sigmoid_r2_threshold: float = 0.70
    alpha: float = 0.05


@dataclass
class TrialRow:
    participant_id: str
    trial_type: str
    soa_ms: int | None
    distance_cm: float | None
    condition: str
    phase: str
    noise_type: str
    part_number: int | None
    rt_ms: float | None
    response_detected: bool
    primary_included: bool
    raw_row_index: int


@dataclass
class ReplicationResult:
    schema: str
    input_path: str
    input_kind: str
    options: dict[str, Any]
    warnings: list[str]
    sample: dict[str, Any]
    participant_qc_rows: list[dict[str, Any]]
    criteria_rows: list[dict[str, Any]]
    facilitation_by_soa_rows: list[dict[str, Any]]
    participant_slope_rows: list[dict[str, Any]]
    model_comparison_rows: list[dict[str, Any]]
    summary: dict[str, Any]
    report_markdown: str


def parse_soa_distance_map(text: str | None) -> dict[int, float]:
    if not text:
        return dict(DEFAULT_SOA_DISTANCE_MAP)
    result: dict[int, float] = {}
    for chunk in text.split(","):
        item = chunk.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Invalid SOA distance item {item!r}; expected SOA:DISTANCE_CM.")
        soa_text, distance_text = item.split(":", 1)
        result[int(float(soa_text.strip()))] = float(distance_text.strip())
    if not result:
        raise ValueError("SOA distance map cannot be empty.")
    return result


def analyze_csv(
    input_csv: str | Path,
    *,
    options: ReplicationOptions | None = None,
) -> ReplicationResult:
    options = options or ReplicationOptions()
    input_path = Path(input_csv)
    rows = _read_csv(input_path)
    input_kind = detect_input_kind(rows, requested=options.input_kind)
    trials, warnings = normalize_rows(rows, input_kind=input_kind, options=options)
    return analyze_trials(
        trials,
        input_path=str(input_path),
        input_kind=input_kind,
        options=options,
        warnings=warnings,
    )


def discover_input_csvs(path: str | Path) -> list[Path]:
    root = Path(path)
    if root.is_file():
        return [root]
    if not root.exists():
        raise FileNotFoundError(root)
    discovered: dict[str, Path] = {}
    for pattern in DISCOVERY_PATTERNS:
        for candidate in root.glob(pattern):
            if candidate.is_file():
                discovered[str(candidate.resolve())] = candidate
    return [discovered[key] for key in sorted(discovered)]


def detect_input_kind(rows: list[dict[str, str]], *, requested: str = INPUT_KIND_AUTO) -> str:
    if requested != INPUT_KIND_AUTO:
        if requested not in {INPUT_KIND_OSF_MASTER, INPUT_KIND_ANALYSIS_READY}:
            raise ValueError(f"Unsupported input kind: {requested}")
        return requested
    if not rows:
        raise ValueError("Input CSV has no rows.")
    fields = {key.lower() for row in rows[:20] for key in row}
    if "reaction_time_ms" in fields and "soa_ms" in fields and (
        "response_detected_bool" in fields or "response_detected" in fields
    ):
        return INPUT_KIND_OSF_MASTER
    if {"rt_ms", "hit", "soa_ms"}.issubset(fields) or {"rt_ms", "outcome", "soa_ms"}.issubset(fields):
        return INPUT_KIND_ANALYSIS_READY
    raise ValueError(
        "Could not auto-detect input schema. Use --input-kind osf-master or --input-kind analysis-ready."
    )


def normalize_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    input_kind: str,
    options: ReplicationOptions,
) -> tuple[list[TrialRow], list[str]]:
    trials: list[TrialRow] = []
    warnings: list[str] = []
    distance_map = {int(soa): float(distance) for soa, distance in options.soa_distance_map.items()}
    for index, row in enumerate(rows, start=1):
        lowered = {str(key).lower(): value for key, value in row.items()}
        trial_type = _canonical_trial_type(
            _first(lowered, "trial_type", "trialtype", "family", "stimulus_modality", "modality")
        )
        if not trial_type:
            warnings.append(f"Row {index} skipped because trial type was not recognized.")
            continue
        primary_included = _primary_included(lowered)
        soa = _as_int(_first(lowered, "soa_ms", "soa", "soa ms"), None)
        distance = distance_map.get(soa) if soa is not None else None
        if input_kind == INPUT_KIND_OSF_MASTER:
            rt = _as_float(_first(lowered, "reaction_time_ms", "rt_ms", "rt"), None)
            response = _truthy(_first(lowered, "response_detected_bool", "response_detected", "detected"))
            phase = str(_first(lowered, "phase", "respiratory_phase") or "").strip()
        elif input_kind == INPUT_KIND_ANALYSIS_READY:
            rt = _as_float(_first(lowered, "rt_ms", "reaction_time_ms", "rt"), None)
            explicit_response = _first(
                lowered,
                "response_detected_bool",
                "response_detected",
                "detected",
                "click_detected",
            )
            if explicit_response not in (None, ""):
                response = _truthy(explicit_response)
            else:
                hit = _hit_value(lowered)
                response = (not hit) if trial_type == TRIAL_CATCH else hit
            phase = str(_first(lowered, "respiratory_phase", "phase") or "").strip()
        else:
            raise ValueError(f"Unsupported input kind: {input_kind}")
        trials.append(
            TrialRow(
                participant_id=str(_first(lowered, "participant_id", "participant", "subject") or "").strip(),
                trial_type=trial_type,
                soa_ms=soa,
                distance_cm=distance,
                condition=str(_first(lowered, "condition", "condition_label") or "").strip(),
                phase=phase,
                noise_type=str(_first(lowered, "noise_type", "source", "source_label") or "").strip(),
                part_number=_as_int(_first(lowered, "part_number", "part", "block_part"), None),
                rt_ms=rt,
                response_detected=response,
                primary_included=primary_included,
                raw_row_index=index,
            )
        )
    if any(trial.soa_ms is not None and trial.distance_cm is None for trial in trials):
        missing = sorted({trial.soa_ms for trial in trials if trial.soa_ms is not None and trial.distance_cm is None})
        warnings.append(f"No distance mapping was provided for SOA values: {', '.join(str(item) for item in missing)}.")
    return trials, warnings


def analyze_trials(
    trials: Iterable[TrialRow],
    *,
    input_path: str,
    input_kind: str,
    options: ReplicationOptions,
    warnings: Iterable[str] = (),
) -> ReplicationResult:
    trial_rows = [trial for trial in trials if trial.primary_included]
    participant_qc_rows = _participant_qc(trial_rows, options=options)
    clean_rows = _clean_response_trials(trial_rows, participant_qc_rows, options=options)
    at_rows, baseline_rows = _facilitation_rows(clean_rows)
    facilitation_by_soa_rows = _facilitation_by_soa(at_rows)
    participant_slope_rows = _participant_slopes(at_rows)
    model_comparison_rows, model_summary = _model_comparison(at_rows, options=options)
    criteria_rows = _criteria_rows(
        trials=trial_rows,
        clean_rows=clean_rows,
        at_rows=at_rows,
        participant_qc_rows=participant_qc_rows,
        facilitation_by_soa_rows=facilitation_by_soa_rows,
        participant_slope_rows=participant_slope_rows,
        model_summary=model_summary,
        options=options,
    )
    sample = _sample_summary(trial_rows, clean_rows, at_rows, baseline_rows)
    summary = {
        "schema": SCHEMA,
        "input_path": input_path,
        "input_kind": input_kind,
        "sample": sample,
        "criteria_status_counts": _counts(row["status"] for row in criteria_rows),
        "basic_facilitation_replicated": _criterion_status(criteria_rows, "multisensory_facilitation_overall") == STATUS_PASS,
        "approach_gradient_status": _criterion_status(criteria_rows, "approach_gradient"),
        "sigmoid_boundary_status": _criterion_status(criteria_rows, "sigmoid_boundary_viability"),
        "selected_shape_model": model_summary.get("selected_model", ""),
        "warnings": list(warnings),
    }
    report = _report_markdown(
        summary=summary,
        criteria_rows=criteria_rows,
        facilitation_by_soa_rows=facilitation_by_soa_rows,
        participant_qc_rows=participant_qc_rows,
    )
    return ReplicationResult(
        schema=SCHEMA,
        input_path=input_path,
        input_kind=input_kind,
        options=_options_dict(options),
        warnings=list(warnings),
        sample=sample,
        participant_qc_rows=participant_qc_rows,
        criteria_rows=criteria_rows,
        facilitation_by_soa_rows=facilitation_by_soa_rows,
        participant_slope_rows=participant_slope_rows,
        model_comparison_rows=model_comparison_rows,
        summary=summary,
        report_markdown=report,
    )


def write_outputs(result: ReplicationResult, output_dir: str | Path) -> dict[str, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json": output / "mobile_pps_replication_summary.json",
        "report_md": output / "mobile_pps_replication_report.md",
        "criteria_csv": output / "replication_criteria.csv",
        "participant_qc_csv": output / "participant_qc.csv",
        "facilitation_by_soa_csv": output / "facilitation_by_soa.csv",
        "participant_slopes_csv": output / "participant_slopes.csv",
        "model_comparison_csv": output / "model_comparison.csv",
    }
    payload = {
        "schema": result.schema,
        "input_path": result.input_path,
        "input_kind": result.input_kind,
        "options": result.options,
        "warnings": result.warnings,
        "sample": result.sample,
        "summary": result.summary,
        "criteria": result.criteria_rows,
    }
    paths["summary_json"].write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    paths["report_md"].write_text(result.report_markdown, encoding="utf-8")
    _write_csv(paths["criteria_csv"], result.criteria_rows)
    _write_csv(paths["participant_qc_csv"], result.participant_qc_rows)
    _write_csv(paths["facilitation_by_soa_csv"], result.facilitation_by_soa_rows)
    _write_csv(paths["participant_slopes_csv"], result.participant_slope_rows)
    _write_csv(paths["model_comparison_csv"], result.model_comparison_rows)
    return paths


def _participant_qc(trials: list[TrialRow], *, options: ReplicationOptions) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for participant in sorted({trial.participant_id for trial in trials}):
        group = [trial for trial in trials if trial.participant_id == participant]
        at = [trial for trial in group if trial.trial_type == TRIAL_AUDIO_TACTILE]
        baseline = [trial for trial in group if trial.trial_type == TRIAL_BASELINE]
        catch = [trial for trial in group if trial.trial_type == TRIAL_CATCH]
        catch_fa = sum(1 for trial in catch if trial.response_detected)
        at_hits = sum(1 for trial in at if trial.response_detected)
        baseline_hits = sum(1 for trial in baseline if trial.response_detected)
        at_hit_rate = _safe_div(at_hits, len(at))
        baseline_hit_rate = _safe_div(baseline_hits, len(baseline))
        catch_fa_rate = _safe_div(catch_fa, len(catch))
        rows.append(
            {
                "participant_id": participant,
                "n_rows": len(group),
                "n_audio_tactile": len(at),
                "n_baseline": len(baseline),
                "n_catch": len(catch),
                "at_hit_rate": at_hit_rate,
                "baseline_hit_rate": baseline_hit_rate,
                "catch_false_alarms": catch_fa,
                "catch_false_alarm_rate": "" if catch_fa_rate is None else catch_fa_rate,
                "exclude_catch_fa": bool(catch and catch_fa_rate is not None and catch_fa_rate > options.max_catch_fa_rate),
                "flag_low_at_hit": bool(at and at_hit_rate is not None and at_hit_rate < options.min_hit_rate),
                "flag_low_baseline_hit": bool(
                    baseline and baseline_hit_rate is not None and baseline_hit_rate < options.min_hit_rate
                ),
            }
        )
    return rows


def _clean_response_trials(
    trials: list[TrialRow],
    participant_qc_rows: list[dict[str, Any]],
    *,
    options: ReplicationOptions,
) -> list[TrialRow]:
    excluded = {row["participant_id"] for row in participant_qc_rows if row.get("exclude_catch_fa")}
    candidates = [
        trial
        for trial in trials
        if trial.trial_type in {TRIAL_AUDIO_TACTILE, TRIAL_BASELINE}
        and trial.response_detected
        and trial.rt_ms is not None
        and math.isfinite(trial.rt_ms)
        and trial.participant_id not in excluded
    ]
    if options.outlier_sd <= 0:
        return candidates
    by_participant: dict[str, list[float]] = {}
    for trial in candidates:
        by_participant.setdefault(trial.participant_id, []).append(float(trial.rt_ms))
    bounds: dict[str, tuple[float, float]] = {}
    for participant, values in by_participant.items():
        if len(values) < 2:
            bounds[participant] = (-math.inf, math.inf)
            continue
        mean = statistics.fmean(values)
        sd = statistics.stdev(values)
        bounds[participant] = (mean - options.outlier_sd * sd, mean + options.outlier_sd * sd)
    return [
        trial
        for trial in candidates
        if bounds[trial.participant_id][0] <= float(trial.rt_ms) <= bounds[trial.participant_id][1]
    ]


def _facilitation_rows(clean_rows: list[TrialRow]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline_groups: dict[tuple[str, str, str], list[float]] = {}
    baseline_soas: dict[tuple[str, str, str], set[int]] = {}
    baseline_rows: list[dict[str, Any]] = []
    for trial in clean_rows:
        if trial.trial_type != TRIAL_BASELINE or trial.rt_ms is None:
            continue
        key = (trial.participant_id, trial.condition, trial.phase)
        baseline_groups.setdefault(key, []).append(float(trial.rt_ms))
        if trial.soa_ms is not None:
            baseline_soas.setdefault(key, set()).add(trial.soa_ms)
    for key, values in sorted(baseline_groups.items()):
        baseline_rows.append(
            {
                "participant_id": key[0],
                "condition": key[1],
                "phase": key[2],
                "baseline_rt_ms": statistics.fmean(values),
                "baseline_n": len(values),
                "baseline_source_soas_ms": ";".join(str(soa) for soa in sorted(baseline_soas.get(key, set()))),
            }
        )
    at_rows: list[dict[str, Any]] = []
    for trial in clean_rows:
        if trial.trial_type != TRIAL_AUDIO_TACTILE or trial.rt_ms is None:
            continue
        baseline = _lookup_baseline(baseline_groups, trial)
        if baseline is None:
            continue
        baseline_rt = statistics.fmean(baseline)
        at_rows.append(
            {
                "participant_id": trial.participant_id,
                "condition": trial.condition,
                "phase": trial.phase,
                "noise_type": trial.noise_type,
                "part_number": "" if trial.part_number is None else trial.part_number,
                "soa_ms": "" if trial.soa_ms is None else trial.soa_ms,
                "distance_cm": "" if trial.distance_cm is None else trial.distance_cm,
                "rt_ms": float(trial.rt_ms),
                "baseline_rt_ms": baseline_rt,
                "baseline_n": len(baseline),
                "facilitation_ms": float(trial.rt_ms) - baseline_rt,
            }
        )
    return at_rows, baseline_rows


def _lookup_baseline(groups: dict[tuple[str, str, str], list[float]], trial: TrialRow) -> list[float] | None:
    keys = [
        (trial.participant_id, trial.condition, trial.phase),
        (trial.participant_id, trial.condition, ""),
        (trial.participant_id, "", trial.phase),
        (trial.participant_id, "", ""),
    ]
    for key in keys:
        values = groups.get(key)
        if values:
            return values
    return None


def _facilitation_by_soa(at_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    participant_means = _participant_soa_means(at_rows)
    for soa in sorted({row["soa_ms"] for row in participant_means if row["soa_ms"] != ""}, key=lambda value: float(value)):
        values = [float(row["mean_facilitation_ms"]) for row in participant_means if row["soa_ms"] == soa]
        summary = _one_sample_summary(values, alternative="less")
        rows.append(
            {
                "soa_ms": soa,
                "n_participants": summary["n"],
                "mean_facilitation_ms": summary["mean"],
                "sd_participant_means": summary["sd"],
                "sem_participant_means": summary["sem"],
                "ci95_low": summary["ci95_low"],
                "ci95_high": summary["ci95_high"],
                "t_vs_zero": summary["t"],
                "p_two_sided": summary["p_two_sided"],
                "p_one_sided_facilitation_lt_zero": summary["p_one_sided"],
                "cohen_dz": summary["cohen_dz"],
            }
        )
    return rows


def _participant_slopes(at_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    means = _participant_soa_means(at_rows)
    for participant in sorted({str(row["participant_id"]) for row in means}):
        group = [row for row in means if row["participant_id"] == participant and row["soa_ms"] != ""]
        if len(group) < 2:
            continue
        group = sorted(group, key=lambda row: float(row["soa_ms"]))
        x_soa = np.asarray([float(row["soa_ms"]) for row in group], dtype=float)
        y = np.asarray([float(row["mean_facilitation_ms"]) for row in group], dtype=float)
        slope_soa, intercept_soa = np.polyfit(x_soa, y, 1)
        row = {
            "participant_id": participant,
            "n_soa_means": len(group),
            "intercept_soa": float(intercept_soa),
            "slope_facilitation_per_soa_ms": float(slope_soa),
        }
        if all(row_item["distance_cm"] != "" for row_item in group):
            x_distance = np.asarray([float(row_item["distance_cm"]) for row_item in group], dtype=float)
            slope_distance, intercept_distance = np.polyfit(x_distance, y, 1)
            row["intercept_distance"] = float(intercept_distance)
            row["slope_facilitation_per_cm"] = float(slope_distance)
        rows.append(row)
    return rows


def _participant_soa_means(at_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, Any], list[dict[str, Any]]] = {}
    for row in at_rows:
        soa = row.get("soa_ms", "")
        if soa == "":
            continue
        groups.setdefault((str(row.get("participant_id", "")), soa), []).append(row)
    result: list[dict[str, Any]] = []
    for (participant, soa), rows in sorted(groups.items(), key=lambda item: (item[0][0], float(item[0][1]))):
        values = [float(row["facilitation_ms"]) for row in rows]
        distances = [row.get("distance_cm", "") for row in rows if row.get("distance_cm", "") != ""]
        result.append(
            {
                "participant_id": participant,
                "soa_ms": soa,
                "distance_cm": statistics.fmean(float(distance) for distance in distances) if distances else "",
                "mean_facilitation_ms": statistics.fmean(values),
                "n_trials": len(values),
            }
        )
    return result


def _model_comparison(
    at_rows: list[dict[str, Any]],
    *,
    options: ReplicationOptions,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    means = _participant_soa_means(at_rows)
    for participant in sorted({str(row["participant_id"]) for row in means}):
        group = [row for row in means if row["participant_id"] == participant and row["soa_ms"] != ""]
        if len(group) < 3:
            continue
        group = sorted(group, key=lambda row: float(row["soa_ms"]))
        x = np.asarray([float(row["soa_ms"]) for row in group], dtype=float)
        y = np.asarray([float(row["mean_facilitation_ms"]) for row in group], dtype=float)
        fits = [_fit_model(x, y, model) for model in ("linear_soa", "log_linear_soa", "sigmoid3_zero_far_soa")]
        converged = [fit for fit in fits if fit.get("converged")]
        best_aicc = min((_as_float(fit.get("aicc"), math.inf) for fit in converged), default=math.inf)
        for fit in fits:
            row = {
                "level": "participant",
                "participant_id": participant,
                "model": fit["model"],
                "n_points": len(group),
                "winner": bool(fit.get("converged") and math.isfinite(best_aicc) and _as_float(fit.get("aicc"), math.inf) == best_aicc),
                **fit,
            }
            row["sigmoid_r2_valid"] = bool(
                row["model"] == "sigmoid3_zero_far_soa"
                and row.get("converged")
                and _as_float(row.get("r2"), math.nan) >= options.sigmoid_r2_threshold
                and _as_float(row.get("x0_ms"), math.nan) >= float(np.min(x))
                and _as_float(row.get("x0_ms"), math.nan) <= float(np.max(x))
            )
            rows.append(row)
    summary: dict[str, Any] = {"selected_model": "", "model_aicc_sums": {}, "participant_count": 0, "sigmoid_valid_count": 0}
    participant_ids = sorted({row["participant_id"] for row in rows if row.get("level") == "participant"})
    summary["participant_count"] = len(participant_ids)
    summary["sigmoid_valid_count"] = sum(
        1 for row in rows if row.get("model") == "sigmoid3_zero_far_soa" and row.get("sigmoid_r2_valid")
    )
    for model in ("linear_soa", "log_linear_soa", "sigmoid3_zero_far_soa"):
        model_rows = [row for row in rows if row.get("model") == model and row.get("converged")]
        participant_set = {row["participant_id"] for row in model_rows}
        eligible = bool(participant_ids) and participant_set == set(participant_ids)
        aicc_sum = sum(float(row["aicc"]) for row in model_rows if row.get("aicc") not in ("", None))
        summary["model_aicc_sums"][model] = aicc_sum if eligible else math.inf
        rows.append(
            {
                "level": "summary",
                "participant_id": "",
                "model": model,
                "participant_count": len(model_rows),
                "eligible_all_participants": eligible,
                "sum_aicc": aicc_sum if eligible else "",
            }
        )
    finite = {model: value for model, value in summary["model_aicc_sums"].items() if math.isfinite(value)}
    if finite:
        selected = min(finite.items(), key=lambda item: item[1])[0]
        summary["selected_model"] = selected
        delta = {model: value - finite[selected] for model, value in finite.items()}
        weights_raw = {model: math.exp(-0.5 * value) for model, value in delta.items()}
        denom = sum(weights_raw.values())
        summary["model_aicc_weights"] = {model: value / denom for model, value in weights_raw.items()} if denom else {}
    else:
        summary["model_aicc_weights"] = {}
    return rows, summary


def _fit_model(x: np.ndarray, y: np.ndarray, model: str) -> dict[str, Any]:
    try:
        if model == "linear_soa":
            slope, intercept = np.polyfit(x, y, 1)
            predicted = intercept + slope * x
            return {
                "model": model,
                "converged": True,
                "intercept": float(intercept),
                "slope_soa": float(slope),
                **_fit_metrics(y, predicted, parameter_count=2),
            }
        if model == "log_linear_soa":
            slope, intercept = np.polyfit(np.log(x), y, 1)
            predicted = intercept + slope * np.log(x)
            return {
                "model": model,
                "converged": True,
                "intercept": float(intercept),
                "slope_log_soa": float(slope),
                **_fit_metrics(y, predicted, parameter_count=2),
            }
        if model == "sigmoid3_zero_far_soa":
            return _fit_sigmoid3(x, y)
    except Exception as exc:
        return {"model": model, "converged": False, "fit_error": str(exc)}
    raise ValueError(model)


def _fit_sigmoid3(x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    if len(x) < 4 or len(set(x.tolist())) < 4 or float(np.nanstd(y)) == 0.0:
        return {"model": "sigmoid3_zero_far_soa", "converged": False, "fit_error": "too few points or zero variance"}
    bounds = ([-500.0, float(np.min(x)), 1.0], [500.0, float(np.max(x)), 5000.0])
    p0_grid = [
        [float(np.min(y)), float(np.median(x)), 500.0],
        [float(y[-1]), float(np.median(x)), 500.0],
        [float(np.min(y)), float(np.mean(x)), 1000.0],
    ]
    best: dict[str, Any] | None = None
    for p0 in p0_grid:
        try:
            with py_warnings.catch_warnings():
                py_warnings.simplefilter("ignore", OptimizeWarning)
                params, _ = curve_fit(_sigmoid3_zero_far_soa, x, y, p0=p0, bounds=bounds, maxfev=100000)
            predicted = _sigmoid3_zero_far_soa(x, *params)
            fit = {
                "model": "sigmoid3_zero_far_soa",
                "converged": True,
                "near_asymptote": float(params[0]),
                "x0_ms": float(params[1]),
                "k_ms": float(params[2]),
                **_fit_metrics(y, predicted, parameter_count=3),
            }
            if best is None or _as_float(fit.get("aicc"), math.inf) < _as_float(best.get("aicc"), math.inf):
                best = fit
        except Exception:
            continue
    return best if best is not None else {"model": "sigmoid3_zero_far_soa", "converged": False, "fit_error": "fit failed"}


def _sigmoid3_zero_far_soa(x: np.ndarray, near_asymptote: float, x0_ms: float, k_ms: float) -> np.ndarray:
    return near_asymptote * expit((x - x0_ms) / k_ms)


def _fit_metrics(y: np.ndarray, predicted: np.ndarray, *, parameter_count: int) -> dict[str, Any]:
    residual = y - predicted
    rss = float(np.sum(residual**2))
    n = int(len(y))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - (rss / ss_tot) if ss_tot else 1.0
    rmse = math.sqrt(rss / n) if n else math.nan
    aic = n * math.log(max(rss / max(n, 1), 1e-12)) + 2 * parameter_count if n else math.inf
    aicc = math.inf
    if math.isfinite(aic) and n > parameter_count + 1:
        aicc = aic + (2.0 * parameter_count * (parameter_count + 1.0)) / (n - parameter_count - 1.0)
    return {"rss": rss, "rmse": rmse, "r2": r2, "aic": aic, "aicc": "" if not math.isfinite(aicc) else aicc}


def _criteria_rows(
    *,
    trials: list[TrialRow],
    clean_rows: list[TrialRow],
    at_rows: list[dict[str, Any]],
    participant_qc_rows: list[dict[str, Any]],
    facilitation_by_soa_rows: list[dict[str, Any]],
    participant_slope_rows: list[dict[str, Any]],
    model_summary: dict[str, Any],
    options: ReplicationOptions,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    participant_count = len({trial.participant_id for trial in trials})
    trial_counts = _counts(trial.trial_type for trial in trials)
    inventory_pass = participant_count > 0 and trial_counts.get(TRIAL_AUDIO_TACTILE, 0) > 0 and trial_counts.get(TRIAL_BASELINE, 0) > 0
    rows.append(
        _criterion(
            "data_inventory",
            STATUS_PASS if inventory_pass else STATUS_FAIL,
            f"{len(trials)} rows; {participant_count} participants; AT={trial_counts.get(TRIAL_AUDIO_TACTILE, 0)}; baseline={trial_counts.get(TRIAL_BASELINE, 0)}; catch={trial_counts.get(TRIAL_CATCH, 0)}",
            "Audio-tactile and tactile-only baseline rows are required for this replication check.",
        )
    )
    mean_at = _mean_from_qc(participant_qc_rows, "at_hit_rate")
    mean_baseline = _mean_from_qc(participant_qc_rows, "baseline_hit_rate")
    low_hit_count = sum(1 for row in participant_qc_rows if row.get("flag_low_at_hit") or row.get("flag_low_baseline_hit"))
    integrity_status = STATUS_PASS if _gte(mean_at, options.min_hit_rate) and _gte(mean_baseline, options.min_hit_rate) else STATUS_FAIL
    rows.append(
        _criterion(
            "performance_integrity",
            integrity_status,
            f"mean AT hit={_fmt(mean_at, 3)}; mean baseline hit={_fmt(mean_baseline, 3)}; low-hit participants={low_hit_count}",
            "Participants should reliably detect tactile targets in audio-tactile and baseline trials.",
        )
    )
    catch_rows = [row for row in participant_qc_rows if int(row.get("n_catch") or 0) > 0]
    if catch_rows:
        high_catch_count = sum(1 for row in catch_rows if row.get("exclude_catch_fa"))
        mean_catch = _mean_from_qc(catch_rows, "catch_false_alarm_rate")
        catch_status = STATUS_PASS if high_catch_count == 0 else STATUS_FAIL
        catch_result = f"mean catch FA={_fmt(mean_catch, 3)}; high-catch participants={high_catch_count}"
    else:
        catch_status = STATUS_DOCUMENT
        catch_result = "No catch trials were present."
    rows.append(
        _criterion(
            "catch_false_alarm_control",
            catch_status,
            catch_result,
            "Catch trials guard against simple response expectancy when available.",
        )
    )
    analyzable_responses = [
        trial
        for trial in trials
        if trial.trial_type in {TRIAL_AUDIO_TACTILE, TRIAL_BASELINE}
        and trial.response_detected
        and trial.rt_ms is not None
        and math.isfinite(trial.rt_ms)
    ]
    anticipation_count = sum(1 for trial in analyzable_responses if float(trial.rt_ms) < options.anticipation_ms)
    anticipation_rate = _safe_div(anticipation_count, len(analyzable_responses)) or 0.0
    rows.append(
        _criterion(
            "anticipations",
            STATUS_PASS if anticipation_rate <= 0.01 else STATUS_FAIL,
            f"{anticipation_count}/{len(analyzable_responses)} analyzable responses below {options.anticipation_ms:.0f} ms",
            "Very early responses should be rare for a speeded tactile-detection task.",
        )
    )
    participant_overall = _participant_overall_facilitation(at_rows)
    overall = _one_sample_summary(participant_overall, alternative="less")
    rows.append(
        _criterion(
            "multisensory_facilitation_overall",
            STATUS_PASS if overall["n"] > 1 and overall["mean"] < 0 and overall["p_one_sided"] < options.alpha else STATUS_NO_SIGNAL,
            f"mean AT-baseline facilitation={_fmt(overall['mean'], 2)} ms; p_one_sided={_fmt_p(overall['p_one_sided'])}; n={overall['n']}",
            "Negative values mean audio-tactile RTs are faster than matched tactile-only baseline.",
        )
    )
    negative_soas = sum(1 for row in facilitation_by_soa_rows if _as_float(row.get("mean_facilitation_ms"), math.nan) < 0)
    if facilitation_by_soa_rows and negative_soas == len(facilitation_by_soa_rows):
        by_soa_status = STATUS_PASS
    elif facilitation_by_soa_rows and negative_soas >= math.ceil(len(facilitation_by_soa_rows) / 2):
        by_soa_status = STATUS_SIGNAL
    else:
        by_soa_status = STATUS_NO_SIGNAL
    rows.append(
        _criterion(
            "multisensory_facilitation_by_soa",
            by_soa_status,
            f"{negative_soas}/{len(facilitation_by_soa_rows)} SOA means are negative after matched baseline correction.",
            "A basic audio-tactile PPS task should show facilitation across at least part of the SOA range.",
        )
    )
    slopes = [float(row["slope_facilitation_per_soa_ms"]) for row in participant_slope_rows if row.get("slope_facilitation_per_soa_ms") not in (None, "")]
    slope_summary = _one_sample_summary(slopes, alternative="less")
    mean_slope = _as_float(slope_summary["mean"], math.nan)
    rows.append(
        _criterion(
            "approach_gradient",
            STATUS_SIGNAL
            if slope_summary["n"] > 1
            and _meaningfully_negative(mean_slope, epsilon=1e-6)
            and slope_summary["p_one_sided"] < options.alpha
            else STATUS_NO_SIGNAL,
            f"mean SOA slope={_fmt(slope_summary['mean'], 5)} ms facilitation per SOA-ms; p_one_sided={_fmt_p(slope_summary['p_one_sided'])}; n={slope_summary['n']}",
            "A negative SOA slope means facilitation becomes stronger as the looming sound approaches the body.",
        )
    )
    selected_model = str(model_summary.get("selected_model") or "")
    selected_status = STATUS_PASS if selected_model else STATUS_NO_SIGNAL
    rows.append(
        _criterion(
            "collapsed_model_shape",
            selected_status,
            f"AICc-selected model={selected_model or 'none'}",
            "The selected shape describes participant-collapsed SOA means; it is a model-selection summary, not a boundary claim.",
        )
    )
    participant_count = int(model_summary.get("participant_count") or 0)
    sigmoid_valid = int(model_summary.get("sigmoid_valid_count") or 0)
    sigmoid_status = STATUS_PASS if participant_count > 0 and sigmoid_valid == participant_count else STATUS_FAIL
    rows.append(
        _criterion(
            "sigmoid_boundary_viability",
            sigmoid_status,
            f"{sigmoid_valid}/{participant_count} participants meet sigmoid R2 >= {options.sigmoid_r2_threshold:.2f} with in-range boundary.",
            "Sigmoid PPS boundary/D50 estimation is defensible only when the sampled curve supports that shape.",
        )
    )
    rows.append(
        _criterion(
            "clean_trial_inventory",
            STATUS_PASS if clean_rows and at_rows else STATUS_FAIL,
            f"{len(clean_rows)} clean AT/baseline response rows; {len(at_rows)} baseline-corrected AT rows.",
            "The replication checks require clean RT-bearing trials after catch and outlier rules.",
        )
    )
    return rows


def _participant_overall_facilitation(at_rows: list[dict[str, Any]]) -> list[float]:
    groups: dict[str, list[float]] = {}
    for row in at_rows:
        groups.setdefault(str(row.get("participant_id", "")), []).append(float(row["facilitation_ms"]))
    return [statistics.fmean(values) for values in groups.values() if values]


def _sample_summary(
    trials: list[TrialRow],
    clean_rows: list[TrialRow],
    at_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "raw_rows": len(trials),
        "participants": len({trial.participant_id for trial in trials}),
        "trial_type_counts": _counts(trial.trial_type for trial in trials),
        "clean_audio_tactile_baseline_rows": len(clean_rows),
        "baseline_corrected_audio_tactile_rows": len(at_rows),
        "baseline_cells": len(baseline_rows),
    }


def _report_markdown(
    *,
    summary: dict[str, Any],
    criteria_rows: list[dict[str, Any]],
    facilitation_by_soa_rows: list[dict[str, Any]],
    participant_qc_rows: list[dict[str, Any]],
) -> str:
    facilitation_status = summary.get("basic_facilitation_replicated")
    gradient_status = summary.get("approach_gradient_status")
    sigmoid_status = summary.get("sigmoid_boundary_status")
    selected_model = summary.get("selected_shape_model") or "not selected"
    if facilitation_status:
        bottom = "Basic audio-tactile PPS facilitation is present in this dataset."
    else:
        bottom = "Basic audio-tactile PPS facilitation is not supported by this dataset."
    lines = [
        "# Mobile PPS Replication Report",
        "",
        "## Bottom Line",
        "",
        f"- {bottom}",
        f"- Approach/SOA gradient status: `{gradient_status}`.",
        f"- Sigmoid boundary viability: `{sigmoid_status}`.",
        f"- Selected collapsed SOA model: `{selected_model}`.",
        "",
        "## Sample",
        "",
        f"- Rows: {summary.get('sample', {}).get('raw_rows', 0)}",
        f"- Participants: {summary.get('sample', {}).get('participants', 0)}",
        f"- Clean AT/baseline RT rows: {summary.get('sample', {}).get('clean_audio_tactile_baseline_rows', 0)}",
        f"- Baseline-corrected AT rows: {summary.get('sample', {}).get('baseline_corrected_audio_tactile_rows', 0)}",
        "",
        "## Criteria",
        "",
    ]
    for row in criteria_rows:
        lines.append(f"- `{row['status']}` | `{row['criterion']}`: {row['result']}")
    lines.extend(["", "## Facilitation By SOA", ""])
    if facilitation_by_soa_rows:
        for row in facilitation_by_soa_rows:
            lines.append(
                f"- SOA {row['soa_ms']} ms: mean={_fmt(row['mean_facilitation_ms'], 2)} ms, "
                f"95% CI {_fmt(row['ci95_low'], 2)} to {_fmt(row['ci95_high'], 2)}, "
                f"p={_fmt_p(row['p_two_sided'])}"
            )
    else:
        lines.append("- No SOA-level facilitation table could be built.")
    lines.extend(["", "## Participant QC", ""])
    if participant_qc_rows:
        low_hit = sum(1 for row in participant_qc_rows if row.get("flag_low_at_hit") or row.get("flag_low_baseline_hit"))
        high_catch = sum(1 for row in participant_qc_rows if row.get("exclude_catch_fa"))
        lines.append(f"- Participants flagged for low hit rate: {low_hit}")
        lines.append(f"- Participants flagged for catch false alarms: {high_catch}")
    else:
        lines.append("- No participant QC rows were available.")
    lines.extend(
        [
            "",
            "## Interpretation Notes",
            "",
            "- Facilitation is computed as audio-tactile RT minus matched tactile-only baseline RT; negative values mean faster audio-tactile detection.",
            "- The smartphone/DynaSpace paper is treated here as a methods/behavioral validation anchor, not as an exact published-study preload profile.",
            "- This script does not validate audio hardware timing, XDF/LSL preservation, or raw WAV decoding fidelity.",
        ]
    )
    return "\n".join(lines) + "\n"


def _one_sample_summary(values: list[float], *, alternative: str) -> dict[str, Any]:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    n = len(clean)
    if not clean:
        return {
            "n": 0,
            "mean": math.nan,
            "sd": math.nan,
            "sem": math.nan,
            "ci95_low": math.nan,
            "ci95_high": math.nan,
            "t": math.nan,
            "p_two_sided": math.nan,
            "p_one_sided": math.nan,
            "cohen_dz": math.nan,
        }
    mean = statistics.fmean(clean)
    if n == 1:
        return {
            "n": n,
            "mean": mean,
            "sd": 0.0,
            "sem": 0.0,
            "ci95_low": mean,
            "ci95_high": mean,
            "t": math.nan,
            "p_two_sided": math.nan,
            "p_one_sided": math.nan,
            "cohen_dz": math.nan,
        }
    sd = statistics.stdev(clean)
    sem = sd / math.sqrt(n) if sd else 0.0
    if sd == 0.0:
        t_stat = math.copysign(math.inf, mean) if mean else 0.0
        p_two = 0.0 if mean else 1.0
    else:
        t_stat, p_two = stats.ttest_1samp(clean, 0.0)
        t_stat = float(t_stat)
        p_two = float(p_two)
    if alternative == "less":
        p_one = p_two / 2.0 if mean < 0 else 1.0 - p_two / 2.0
    elif alternative == "greater":
        p_one = p_two / 2.0 if mean > 0 else 1.0 - p_two / 2.0
    else:
        p_one = p_two
    ci_delta = stats.t.ppf(0.975, n - 1) * sem if sem else 0.0
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "sem": sem,
        "ci95_low": mean - ci_delta,
        "ci95_high": mean + ci_delta,
        "t": t_stat,
        "p_two_sided": p_two,
        "p_one_sided": p_one,
        "cohen_dz": mean / sd if sd else math.copysign(math.inf, mean) if mean else 0.0,
    }


def _criterion(criterion: str, status: str, result: str, interpretation: str) -> dict[str, str]:
    return {
        "criterion": criterion,
        "status": status,
        "result": result,
        "interpretation": interpretation,
    }


def _criterion_status(rows: list[dict[str, Any]], criterion: str) -> str:
    for row in rows:
        if row.get("criterion") == criterion:
            return str(row.get("status") or "")
    return ""


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(_json_ready(row) for row in rows)


def _canonical_trial_type(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    text = " ".join(text.split())
    if text in {"audio-tactile", "audio tactile", "audiotactile", "at", "bimodal"}:
        return TRIAL_AUDIO_TACTILE
    if text in {"baseline", "tactile-only", "tactile only", "tactile", "no-sound tactile"}:
        return TRIAL_BASELINE
    if text in {"catch", "audio-only", "audio only", "auditory-only", "auditory only", "no-target"}:
        return TRIAL_CATCH
    return ""


def _primary_included(row: Mapping[str, Any]) -> bool:
    value = _first(row, "primary_analysis_included", "primary_included", "include", "included")
    if value in (None, ""):
        is_topup = _truthy(_first(row, "is_topup", "topup"))
        role = str(_first(row, "topup_role", "role") or "").strip().lower()
        return not (is_topup and role == "filler")
    return _truthy(value)


def _hit_value(row: Mapping[str, Any]) -> bool:
    value = _first(row, "hit", "Hit", "response_hit")
    if value not in (None, ""):
        return _truthy(value)
    outcome = str(_first(row, "outcome", "response_category") or "").strip().lower()
    if outcome:
        if outcome in {"hit", "baseline_hit", "catch_hit", "correct"}:
            return True
        if outcome in {"miss", "baseline_miss", "catch_miss", "incorrect"}:
            return False
    return False


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        lowered = key.lower()
        if lowered in row and row[lowered] not in (None, ""):
            return row[lowered]
    return ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none", "nan"}


def _as_int(value: Any, default: Any) -> Any:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: Any) -> Any:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _safe_div(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def _counts(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _mean_from_qc(rows: list[dict[str, Any]], field: str) -> float:
    values = [_as_float(row.get(field), math.nan) for row in rows if row.get(field) not in (None, "")]
    values = [value for value in values if math.isfinite(value)]
    return statistics.fmean(values) if values else math.nan


def _gte(value: float, threshold: float) -> bool:
    return math.isfinite(value) and value >= threshold


def _meaningfully_negative(value: float, *, epsilon: float) -> bool:
    return math.isfinite(value) and value < -abs(epsilon)


def _fmt(value: Any, digits: int) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return f"{number:.{digits}f}" if math.isfinite(number) else "n/a"


def _fmt_p(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if not math.isfinite(number):
        return "n/a"
    if number < 0.001:
        return "< .001"
    return f"{number:.3f}"


def _options_dict(options: ReplicationOptions) -> dict[str, Any]:
    return {
        "input_kind": options.input_kind,
        "soa_distance_map": {str(key): value for key, value in sorted(options.soa_distance_map.items())},
        "min_hit_rate": options.min_hit_rate,
        "max_catch_fa_rate": options.max_catch_fa_rate,
        "anticipation_ms": options.anticipation_ms,
        "outlier_sd": options.outlier_sd,
        "sigmoid_r2_threshold": options.sigmoid_r2_threshold,
        "alpha": options.alpha,
    }


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
    if isinstance(value, np.generic):
        return _json_ready(value.item())
    return str(value)
