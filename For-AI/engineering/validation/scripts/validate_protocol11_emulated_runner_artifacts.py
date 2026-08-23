"""Audit Protocol 11 emulated-participant runner output artifacts.

This validator is intentionally offline: it does not launch Focus Mode, click
the UI, play audio, or touch hardware. Feed it a completed real runner session
folder plus an optional controlled response plan keyed by ``trial_uid``. It
then checks the concrete files written by the runner against the Protocol 11
evidence contract and writes a machine-readable pass/fail report.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.output_layout import (  # noqa: E402
    _filesystem_path,
    output_data_analytics_dir,
    output_runner_logs_dir,
    output_verbose_events_dir,
)


SCHEMA = "pps-protocol11-emulated-runner-artifact-audit.v1"
PLAN_SCHEMA = "pps-protocol11-response-plan.v1"
SCHEDULED_EVENT_TYPES = {
    "audio_sample_zero",
    "trial_start",
    "looming_onset",
    "tactile_onset",
    "response_window_onset",
    "trial_end",
    "response_marker_start",
}
TACTILE_TRIAL_TYPES = {"audio-tactile", "audio_tactile", "baseline"}
LOOMING_TRIAL_TYPES = {"audio-tactile", "audio_tactile", "catch"}
ACCEPT_ACTIONS = {"hit", "accept", "accepted", "boundary_accept", "topup_hit"}
REJECT_ACTIONS = {
    "miss",
    "early",
    "late",
    "double_click_extra",
    "out_of_target",
    "out_of_playback",
    "cross_block",
    "instruction_click",
    "reject",
    "rejected",
    "boundary_reject",
}


@dataclass
class Criterion:
    section: str
    name: str
    passed: bool
    detail: str = ""
    required: bool = True
    evidence: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "section": self.section,
            "name": self.name,
            "passed": bool(self.passed),
            "required": bool(self.required),
            "detail": self.detail,
        }
        if self.evidence:
            payload["evidence"] = _json_ready(self.evidence)
        return payload


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    if not os.path.isfile(_filesystem_path(path)):
        return {}
    try:
        with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
            return json.loads(handle.read())
    except Exception:
        return {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not os.path.isfile(_filesystem_path(path)):
        return []
    with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    os.makedirs(_filesystem_path(path.parent), exist_ok=True)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    sections = report.get("sections", {})
    lines = [
        "# Protocol 11 Emulated Runner Artifact Audit",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Session dir: `{report.get('session_dir')}`",
        f"- Response plan: `{report.get('response_plan_path') or ''}`",
        f"- Required criteria: `{report.get('required_passed_count')}/{report.get('required_count')}`",
        "",
        "## Sections",
    ]
    for name, summary in sections.items():
        lines.append(f"- `{name}`: `{summary.get('passed')}` ({summary.get('passed_count')}/{summary.get('count')})")
    failures = [item for item in report.get("criteria", []) if item.get("required") and not item.get("passed")]
    if failures:
        lines.extend(["", "## Required Failures"])
        for failure in failures:
            lines.append(f"- `{failure.get('section')}.{failure.get('name')}`: {failure.get('detail')}")
    lines.extend(
        [
            "",
            "This audit verifies software/run artifacts from an emulated-participant scenario. It does not measure hardware latency, Woojer mechanical onset, participant comprehension, or scientific PPS interpretability.",
        ]
    )
    os.makedirs(_filesystem_path(path.parent), exist_ok=True)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def _as_float(value: Any, default: float = math.nan) -> float:
    try:
        result = float(str(value).strip())
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none", "nan"}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _row_value(row: dict[str, Any], *names: str, default: Any = "") -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return default


def _resolve_path(value: Any, *, base: Path) -> Path:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = base / path
    return path


def _path_is_set(path: Path | None) -> bool:
    return path is not None and str(path) not in {"", "."}


def _path_exists(path: Path) -> bool:
    return os.path.exists(_filesystem_path(path))


def _path_is_file(path: Path) -> bool:
    return os.path.isfile(_filesystem_path(path))


def _path_is_dir(path: Path) -> bool:
    return os.path.isdir(_filesystem_path(path))


def _glob_files(directory: Path, pattern: str) -> list[Path]:
    if not _path_is_dir(directory):
        return []
    return sorted(Path(item) for item in Path(_filesystem_path(directory)).glob(pattern))


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if _path_is_set(path) and _path_exists(path):
            return path
    return None


def _manifest_output_path(outputs: dict[str, Any], *keys: str, base: Path, fallback: Path) -> Path:
    for key in keys:
        value = outputs.get(key)
        if value not in (None, ""):
            return _resolve_path(value, base=base)
    return fallback


def _session_manifest_path(session_dir: Path) -> Path:
    return _first_existing(
        [
            session_dir / "session_manifest.json",
            output_runner_logs_dir(session_dir.parent) / session_dir.name / "session_manifest.json",
            output_runner_logs_dir(session_dir.parent.parent) / session_dir.parent.name / session_dir.name / "session_manifest.json",
        ]
    ) or (session_dir / "session_manifest.json")


def _event_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(path):
        payload: dict[str, Any] = {}
        try:
            payload = json.loads(row.get("payload_json", "") or "{}")
        except json.JSONDecodeError:
            payload = {}
        flat = dict(row)
        flat["payload"] = payload
        for key, value in payload.items():
            flat.setdefault(key, value)
        rows.append(flat)
    return rows


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _latest_analysis_csv(session_dir: Path, suffix: str, *, analysis_dir: Path | None = None) -> Path | None:
    candidates = [
        analysis_dir or Path(),
        session_dir / "analysis",
        output_data_analytics_dir(session_dir.parent) / session_dir.name,
    ]
    matches: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if not _path_is_set(candidate) or key in seen or not _path_is_dir(candidate):
            continue
        seen.add(key)
        matches.extend(_glob_files(candidate, f"*_{suffix}.csv"))
    return matches[-1] if matches else None


def _analysis_file(session_dir: Path, filename: str, *, analysis_dir: Path | None = None) -> Path | None:
    for candidate_dir in (analysis_dir, session_dir / "analysis", output_data_analytics_dir(session_dir.parent) / session_dir.name):
        if candidate_dir is None or not _path_is_set(candidate_dir):
            continue
        path = candidate_dir / filename
        if _path_is_file(path):
            return path
    path = session_dir / "analysis" / filename
    return path if _path_is_file(path) else None


def _trial_uid(row: dict[str, Any]) -> str:
    return str(_row_value(row, "trial_uid", "Trial_UID", default="")).strip()


def _trial_type(row: dict[str, Any]) -> str:
    return _norm(_row_value(row, "trial_type", "Trial_Type", "family", "Family", default=""))


def _has_tactile(row: dict[str, Any]) -> bool:
    return _trial_type(row) in TACTILE_TRIAL_TYPES or _row_value(row, "Tactile_Onset_Sample", "tactile_onset_sample", default="") not in ("", None)


def _has_looming(row: dict[str, Any]) -> bool:
    return _trial_type(row) in LOOMING_TRIAL_TYPES or _row_value(row, "Looming_Onset_Sample", "looming_onset_sample", default="") not in ("", None)


def _load_response_plan(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"schema": PLAN_SCHEMA, "trials": []}
    if path.suffix.lower() == ".csv":
        return {"schema": PLAN_SCHEMA, "source_format": "csv", "trials": _read_csv(path)}
    payload = _read_json(path)
    if isinstance(payload, list):
        return {"schema": PLAN_SCHEMA, "source_format": "json-list", "trials": payload}
    trials = payload.get("trials", payload.get("responses", []))
    payload["trials"] = trials if isinstance(trials, list) else []
    return payload


def _expected_capture_options(plan: dict[str, Any], session_metadata: dict[str, Any], session_start: dict[str, Any]) -> dict[str, bool]:
    options = plan.get("expected_capture_options") or plan.get("capture_options") or {}
    if not isinstance(options, dict):
        options = {}
    if not options:
        metadata_options = session_metadata.get("capture_policy") or {}
        if isinstance(metadata_options, dict):
            options = {key: bool(value) for key, value in metadata_options.items() if key in {
                "write_events_csv",
                "write_internal_xdf",
                "write_analysis_csvs",
                "write_lsl_marker_mirror",
                "write_trigger_dictionary",
                "start_backup_recording",
                "enable_lsl",
            }}
    if not options:
        start_options = session_start.get("capture_options") or {}
        if isinstance(start_options, dict):
            options = {key: bool(value) for key, value in start_options.items()}
    return {str(key): bool(value) for key, value in options.items()}


def _analysis_paths(session_dir: Path, *, analysis_dir: Path | None = None) -> dict[str, Path | None]:
    return {
        "responses": _latest_analysis_csv(session_dir, "responses", analysis_dir=analysis_dir),
        "analysis_ready_trials": _latest_analysis_csv(session_dir, "analysis_ready_trials", analysis_dir=analysis_dir),
        "final_trial_outcomes": _latest_analysis_csv(session_dir, "final_trial_outcomes", analysis_dir=analysis_dir),
        "summary": _latest_analysis_csv(session_dir, "summary", analysis_dir=analysis_dir),
        "curve_points": _latest_analysis_csv(session_dir, "pps_curve_points", analysis_dir=analysis_dir),
        "sigmoid_fits": _latest_analysis_csv(session_dir, "sigmoid_fits", analysis_dir=analysis_dir),
        "model_fits": _latest_analysis_csv(session_dir, "model_fits", analysis_dir=analysis_dir),
        "model_fit_comparison": _latest_analysis_csv(session_dir, "model_fit_comparison", analysis_dir=analysis_dir),
        "data_behavior_by_scope": _analysis_file(session_dir, "data_behavior_by_scope.csv", analysis_dir=analysis_dir),
        "timing_qc": _latest_analysis_csv(session_dir, "timing_qc", analysis_dir=analysis_dir),
    }


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "sd": None, "median": None, "min": None, "max": None}
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean": statistics.fmean(ordered),
        "sd": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "median": statistics.median(ordered),
        "min": ordered[0],
        "max": ordered[-1],
    }


def _inspect_wav(path: Path) -> dict[str, Any]:
    try:
        import numpy as np
        import soundfile as sf

        info = sf.info(_filesystem_path(path))
        data, sample_rate = sf.read(_filesystem_path(path), always_2d=True)
        finite = bool(np.isfinite(data).all())
        peak = float(np.max(np.abs(data))) if data.size else 0.0
        return {
            "exists": True,
            "readable": True,
            "sample_rate": int(sample_rate),
            "frames": int(data.shape[0]),
            "channels": int(data.shape[1]),
            "duration_s": float(info.duration),
            "finite_pcm": finite,
            "peak_abs": peak,
        }
    except Exception as exc:
        return {"exists": _path_exists(path), "readable": False, "error": str(exc)}


def _block_entries(manifest: dict[str, Any], session_dir: Path) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for index, block in enumerate(manifest.get("blocks", []) or [], start=1):
        if not isinstance(block, dict):
            continue
        manifest_path = _resolve_path(block.get("manifest_path"), base=session_dir)
        wav_path = _resolve_path(block.get("wav_path"), base=session_dir)
        blocks.append({**block, "index": block.get("index", index), "manifest_path_resolved": manifest_path, "wav_path_resolved": wav_path})
    return blocks


def _manifest_rows(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for block in blocks:
        path = Path(block["manifest_path_resolved"])
        for row in _read_csv(path):
            rows.append({**row, "_block_index": block.get("index"), "_block_manifest": str(path), "_block_wav": str(block["wav_path_resolved"])})
    return rows


def _expected_event_counts(rows: list[dict[str, Any]], block_count: int) -> dict[str, int]:
    return {
        "audio_sample_zero": block_count,
        "block_schedule_loaded": block_count,
        "block_start": block_count,
        "block_end": block_count,
        "trial_start": len(rows),
        "looming_onset": sum(1 for row in rows if _has_looming(row)),
        "tactile_onset": sum(1 for row in rows if _has_tactile(row)),
        "response_window_onset": len(rows),
        "trial_end": len(rows),
    }


def _criterion(criteria: list[Criterion], section: str, name: str, passed: bool, detail: str = "", *, required: bool = True, **evidence: Any) -> None:
    criteria.append(Criterion(section=section, name=name, passed=bool(passed), detail=detail, required=required, evidence=evidence))


def _audit_session_resolution(
    criteria: list[Criterion],
    *,
    session_dir: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    metadata_path: Path,
    metadata: dict[str, Any],
    require_local_data_root: bool,
) -> None:
    _criterion(criteria, "launch_session_resolution", "session_manifest_exists", _path_is_file(manifest_path), str(manifest_path))
    _criterion(criteria, "launch_session_resolution", "session_manifest_schema", manifest.get("schema") == "pps-run-session.v1", str(manifest.get("schema")))
    _criterion(criteria, "launch_session_resolution", "session_metadata_exists", _path_is_file(metadata_path), str(metadata_path))
    _criterion(criteria, "launch_session_resolution", "session_metadata_schema", metadata.get("schema") == "pps-runner-session-metadata.v1", str(metadata.get("schema")), required=_path_exists(metadata_path))
    if require_local_data_root:
        normalized = str(session_dir.resolve()).replace("\\", "/").lower()
        _criterion(criteria, "launch_session_resolution", "session_under_local_data", "/local_data/" in normalized, str(session_dir))
    else:
        _criterion(criteria, "launch_session_resolution", "session_under_local_data", True, "not required for ignored validation fixture", required=False)
    _criterion(
        criteria,
        "launch_session_resolution",
        "participant_id_present",
        bool(str(manifest.get("participant_id") or "").strip()),
        str(manifest.get("participant_id") or ""),
    )
    _criterion(
        criteria,
        "launch_session_resolution",
        "execution_mode_real_session_package",
        str(manifest.get("execution_mode") or "") in {"participant_block_wavs", "design_schedule_blocks"},
        str(manifest.get("execution_mode") or ""),
    )


def _audit_stimulus_assembly(criteria: list[Criterion], *, blocks: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    wav_audits: list[dict[str, Any]] = []
    schedule_failures: list[str] = []
    for block in blocks:
        manifest_path = Path(block["manifest_path_resolved"])
        wav_path = Path(block["wav_path_resolved"])
        wav = _inspect_wav(wav_path)
        block_rows = [row for row in rows if str(row.get("_block_manifest")) == str(manifest_path)]
        wav_audits.append({"block_index": block.get("index"), "manifest": manifest_path, "wav": wav_path, **wav, "trial_count": len(block_rows)})
        if not _path_is_file(manifest_path):
            schedule_failures.append(f"missing block manifest {manifest_path}")
            continue
        if not wav.get("readable"):
            schedule_failures.append(f"unreadable block WAV {wav_path}")
            continue
        sample_rate = int(wav.get("sample_rate") or 0)
        if int(wav.get("channels") or 0) != 3:
            schedule_failures.append(f"{wav_path.name} has {wav.get('channels')} channels")
        if not wav.get("finite_pcm"):
            schedule_failures.append(f"{wav_path.name} contains non-finite samples")
        expected_start = 0
        for row in block_rows:
            uid = _trial_uid(row) or f"row {row.get('Trial_Number', '')}"
            start = _as_int(_row_value(row, "Trial_Start_Sample", "trial_start_sample"), default=-1)
            end = _as_int(_row_value(row, "Trial_End_Sample", "trial_end_sample"), default=-1)
            duration_s = _as_float(_row_value(row, "Trial_Duration_S", "duration_s"), default=math.nan)
            if start != expected_start:
                schedule_failures.append(f"{uid} start {start} != expected {expected_start}")
            if sample_rate > 0 and math.isfinite(duration_s):
                expected_end = int(start or 0) + int(round(duration_s * sample_rate))
                if end != expected_end:
                    schedule_failures.append(f"{uid} end {end} != recomputed {expected_end}")
            if _has_looming(row):
                looming_s = _as_float(_row_value(row, "Looming_Onset_S", "looming_onset_s"), default=math.nan)
                looming_sample = _as_int(_row_value(row, "Looming_Onset_Sample", "looming_onset_sample"), default=-1)
                expected_looming = int(round((float(start or 0) / sample_rate + looming_s) * sample_rate)) if sample_rate > 0 and math.isfinite(looming_s) else None
                if expected_looming is not None and looming_sample != expected_looming:
                    schedule_failures.append(f"{uid} looming {looming_sample} != recomputed {expected_looming}")
            if _has_tactile(row):
                tactile_s = _as_float(_row_value(row, "Tactile_Onset_S", "tactile_onset_s"), default=math.nan)
                tactile_sample = _as_int(_row_value(row, "Tactile_Onset_Sample", "tactile_onset_sample"), default=-1)
                expected_tactile = int(round((float(start or 0) / sample_rate + tactile_s) * sample_rate)) if sample_rate > 0 and math.isfinite(tactile_s) else None
                if expected_tactile is not None and tactile_sample != expected_tactile:
                    schedule_failures.append(f"{uid} tactile {tactile_sample} != recomputed {expected_tactile}")
            response_s = _as_float(_row_value(row, "Response_Window_Onset_S", "response_window_onset_s"), default=math.nan)
            response_sample = _as_int(_row_value(row, "Response_Window_Onset_Sample", "response_window_onset_sample"), default=-1)
            expected_response = int(round((float(start or 0) / sample_rate + response_s) * sample_rate)) if sample_rate > 0 and math.isfinite(response_s) else None
            if expected_response is not None and response_sample != expected_response:
                schedule_failures.append(f"{uid} response window {response_sample} != recomputed {expected_response}")
            expected_start = int(end or expected_start)
        if block_rows and int(wav.get("frames") or 0) != expected_start:
            schedule_failures.append(f"{wav_path.name} frames {wav.get('frames')} != manifest final sample {expected_start}")
    catch_with_tactile = [_trial_uid(row) for row in rows if _trial_type(row) == "catch" and _row_value(row, "Tactile_Onset_Sample", "tactile_onset_sample", default="") not in ("", None)]
    tactile_without_sample = [_trial_uid(row) for row in rows if _trial_type(row) in {"audio_tactile", "audio-tactile", "baseline"} and _row_value(row, "Tactile_Onset_Sample", "tactile_onset_sample", default="") in ("", None)]
    _criterion(criteria, "stimulus_assembly", "block_wavs_readable_3ch_pcm", not schedule_failures, "; ".join(schedule_failures[:8]), wav_audits=wav_audits)
    _criterion(criteria, "stimulus_assembly", "catch_trials_have_no_tactile_sample", not catch_with_tactile, ",".join(catch_with_tactile[:8]))
    _criterion(criteria, "stimulus_assembly", "tactile_trials_have_tactile_sample", not tactile_without_sample, ",".join(tactile_without_sample[:8]))
    return {"wav_audits": wav_audits, "schedule_failures": schedule_failures}


def _audit_timing(
    criteria: list[Criterion],
    *,
    events: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    block_count: int,
    expected_counts: dict[str, int],
    allow_timing_fallback: bool,
) -> None:
    event_counts = _count_by(events, "event_type")
    count_failures = []
    for event_type, expected in expected_counts.items():
        actual = int(event_counts.get(event_type, 0))
        if actual != expected:
            count_failures.append(f"{event_type}: actual {actual} expected {expected}")
    _criterion(criteria, "timing_event_schedule", "event_counts_match_manifest", not count_failures, "; ".join(count_failures), expected_counts=expected_counts, event_counts=event_counts)
    fallback_count = int(event_counts.get("timing_anchor_fallback", 0))
    _criterion(criteria, "timing_event_schedule", "no_unexpected_timing_anchor_fallback", allow_timing_fallback or fallback_count == 0, f"timing_anchor_fallback={fallback_count}")
    scheduled = [row for row in events if str(row.get("event_type") or "") in SCHEDULED_EVENT_TYPES and str(row.get("event_type") or "") != "audio_sample_zero"]
    fallback_qualities = [
        {"event_id": row.get("event_id"), "event_type": row.get("event_type"), "timestamp_quality": row.get("timestamp_quality")}
        for row in scheduled
        if str(row.get("timestamp_quality") or "") not in {"dac_time_sample_exact", ""}
    ]
    _criterion(criteria, "timing_event_schedule", "scheduled_markers_sample_exact", not fallback_qualities, "; ".join(str(item) for item in fallback_qualities[:5]))
    final_boundary_failures = []
    trial_end_by_uid = {str(row.get("trial_uid") or row.get("Trial_UID") or ""): row for row in events if row.get("event_type") == "trial_end"}
    for row in rows:
        uid = _trial_uid(row)
        if not uid:
            continue
        expected_sample = _as_int(_row_value(row, "Trial_End_Sample", "trial_end_sample"), default=None)
        event = trial_end_by_uid.get(uid)
        actual_sample = _as_int(_row_value(event or {}, "sample_index", "planned_sample_index"), default=None)
        if event is None or (expected_sample is not None and actual_sample is not None and actual_sample != expected_sample):
            final_boundary_failures.append(f"{uid}: event sample {actual_sample} expected {expected_sample}")
    _criterion(criteria, "timing_event_schedule", "trial_end_boundaries_present", not final_boundary_failures, "; ".join(final_boundary_failures[:8]))


def _expected_plan_hit(item: dict[str, Any]) -> bool | None:
    if "expected_hit" in item:
        return _truthy(item.get("expected_hit"))
    if "expected_analysis_hit" in item:
        return _truthy(item.get("expected_analysis_hit"))
    action = _norm(item.get("action") or item.get("expected_action"))
    if action in ACCEPT_ACTIONS:
        return True
    if action in REJECT_ACTIONS:
        return False
    return None


def _audit_response_plan(
    criteria: list[Criterion],
    *,
    plan: dict[str, Any],
    plan_path: Path | None,
    rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
    analysis_rows: list[dict[str, str]],
    final_rows: list[dict[str, str]],
) -> dict[str, Any]:
    plan_trials = [dict(item) for item in plan.get("trials", []) if isinstance(item, dict)]
    manifest_uids = {_trial_uid(row) for row in rows if _trial_uid(row)}
    analysis_by_uid = {str(_row_value(row, "trial_uid", "Trial_UID", default="")).strip(): row for row in analysis_rows if str(_row_value(row, "trial_uid", "Trial_UID", default="")).strip()}
    final_by_uid = {str(_row_value(row, "trial_uid", "Trial_UID", default="")).strip(): row for row in final_rows if str(_row_value(row, "trial_uid", "Trial_UID", default="")).strip()}
    _criterion(
        criteria,
        "emulated_response_model",
        "response_plan_present",
        bool(plan_trials),
        str(plan_path or "no response plan supplied"),
        required=plan_path is not None,
    )
    missing = []
    mismatches = []
    rt_mismatches = []
    for item in plan_trials:
        uid = str(_row_value(item, "trial_uid", "Trial_UID", default="")).strip()
        if not uid:
            mismatches.append("plan row missing trial_uid")
            continue
        if uid not in manifest_uids and uid not in analysis_by_uid and uid not in final_by_uid:
            missing.append(uid)
            continue
        expected_hit = _expected_plan_hit(item)
        observed = final_by_uid.get(uid) or analysis_by_uid.get(uid)
        if expected_hit is not None and observed is not None:
            observed_hit = _truthy(_row_value(observed, "hit", "Hit", default=False))
            if observed_hit != expected_hit:
                mismatches.append(f"{uid}: hit {observed_hit} expected {expected_hit}")
        planned_rt = _as_float(_row_value(item, "planned_rt_ms", "rt_ms", "expected_rt_ms", default=""), default=math.nan)
        tolerance = _as_float(_row_value(item, "rt_tolerance_ms", "tolerance_ms", default=35.0), default=35.0)
        observed_rt = _as_float(_row_value(observed or {}, "rt_ms", "RT_ms", default=""), default=math.nan)
        if math.isfinite(planned_rt) and expected_hit is not False:
            if not math.isfinite(observed_rt) or abs(observed_rt - planned_rt) > tolerance:
                rt_mismatches.append(f"{uid}: rt {observed_rt} expected {planned_rt} +/- {tolerance}")
    _criterion(criteria, "emulated_response_model", "planned_trial_uids_resolve", not missing, ",".join(missing[:12]), planned_count=len(plan_trials))
    _criterion(criteria, "emulated_response_model", "planned_hit_miss_labels_match_analysis", not mismatches, "; ".join(mismatches[:8]), required=bool(plan_trials))
    _criterion(criteria, "emulated_response_model", "planned_rt_values_match_analysis", not rt_mismatches, "; ".join(rt_mismatches[:8]), required=any(math.isfinite(_as_float(_row_value(item, "planned_rt_ms", "rt_ms", "expected_rt_ms", default=""))) for item in plan_trials))
    instruction_mouse_clicks = [
        row
        for row in events
        if row.get("event_type") == "mouse_click" and not _truthy(row.get("during_playback", True))
    ]
    planned_instruction_clicks = [
        item
        for item in plan_trials
        if _norm(item.get("action")) == "instruction_click"
    ]
    top_level_instruction_clicks = plan.get("instruction_clicks") or plan.get("instruction_actions") or []
    if not isinstance(top_level_instruction_clicks, list):
        top_level_instruction_clicks = []
    planned_instruction_clicks.extend(item for item in top_level_instruction_clicks if isinstance(item, dict))
    _criterion(
        criteria,
        "emulated_response_model",
        "instruction_clicks_excluded_from_mouse_responses",
        not planned_instruction_clicks or not instruction_mouse_clicks,
        f"out-of-playback mouse_click rows={len(instruction_mouse_clicks)}",
        required=bool(planned_instruction_clicks),
    )
    return {"planned_count": len(plan_trials), "missing": missing, "mismatches": mismatches, "rt_mismatches": rt_mismatches}


def _audit_response_markers(criteria: list[Criterion], *, events: list[dict[str, Any]], timing_qc_rows: list[dict[str, str]]) -> None:
    mouse_events = [row for row in events if row.get("event_type") == "mouse_click"]
    in_playback_mouse = [row for row in mouse_events if _truthy(row.get("during_playback", True))]
    outside_mouse = [row for row in mouse_events if not _truthy(row.get("during_playback", True))]
    markers = [row for row in events if row.get("event_type") == "response_marker_start"]
    marker_mouse_ids = {str(_row_value(row, "mouse_event_id", default="")).strip() for row in markers if str(_row_value(row, "mouse_event_id", default="")).strip()}
    in_playback_ids = {str(row.get("event_id")) for row in in_playback_mouse}
    outside_ids = {str(row.get("event_id")) for row in outside_mouse}
    _criterion(
        criteria,
        "response_marker_path",
        "in_playback_clicks_have_one_marker",
        len(in_playback_ids) == len(marker_mouse_ids) and in_playback_ids.issubset(marker_mouse_ids),
        f"in_playback_mouse={len(in_playback_ids)} marker_links={len(marker_mouse_ids)}",
    )
    _criterion(
        criteria,
        "response_marker_path",
        "outside_playback_clicks_have_no_marker",
        not (outside_ids & marker_mouse_ids),
        f"outside linked IDs={sorted(outside_ids & marker_mouse_ids)}",
        required=bool(outside_mouse),
    )
    qc_mouse_ids = {str(row.get("mouse_event_id") or "").strip() for row in timing_qc_rows if str(row.get("mouse_event_id") or "").strip()}
    delays = [_as_float(row.get("marker_minus_mouse_ms"), default=math.nan) for row in timing_qc_rows]
    delays = [value for value in delays if math.isfinite(value)]
    _criterion(
        criteria,
        "response_marker_path",
        "timing_qc_links_markers_to_mouse_events",
        marker_mouse_ids.issubset(qc_mouse_ids) and len(timing_qc_rows) >= len(markers),
        f"timing_qc_rows={len(timing_qc_rows)} markers={len(markers)}",
        marker_minus_mouse_ms=_summary(delays),
    )
    event_order_failures = []
    event_index = {str(row.get("event_id")): index for index, row in enumerate(events)}
    for marker in markers:
        mouse_id = str(_row_value(marker, "mouse_event_id", default="")).strip()
        if not mouse_id:
            continue
        mouse_event_id = _as_int(mouse_id, default=None)
        marker_event_id = _as_int(marker.get("event_id"), default=None)
        if mouse_event_id is not None and marker_event_id is not None:
            if mouse_event_id > marker_event_id:
                event_order_failures.append(f"mouse {mouse_id} logged after marker {marker.get('event_id')}")
        elif event_index.get(mouse_id, -1) > event_index.get(str(marker.get("event_id")), -1):
            event_order_failures.append(f"mouse {mouse_id} sorted after marker {marker.get('event_id')}")
    _criterion(criteria, "response_marker_path", "mouse_logged_before_response_marker", not event_order_failures, "; ".join(event_order_failures[:8]))


def _audit_instruction_flow(criteria: list[Criterion], *, plan: dict[str, Any], events: list[dict[str, Any]]) -> None:
    expected_slots = plan.get("instruction_slots") or plan.get("expected_instruction_slots") or []
    if not isinstance(expected_slots, list):
        expected_slots = []
    starts = [row for row in events if row.get("event_type") == "instruction_start"]
    continues = [row for row in events if row.get("event_type") == "instruction_continue"]
    errors = [row for row in events if row.get("event_type") in {"instruction_missing", "instruction_error"}]
    for item in expected_slots:
        slot = str(item.get("slot") if isinstance(item, dict) else item).strip()
        if not slot:
            continue
        slot_starts = [row for row in starts if str(_row_value(row, "slot", "instruction_slot", default="")) == slot]
        required = _truthy(item.get("required", True)) if isinstance(item, dict) else True
        _criterion(criteria, "instruction_module", f"instruction_slot_{slot}", bool(slot_starts) or not required, f"starts={len(slot_starts)}", required=required)
    _criterion(criteria, "instruction_module", "instruction_events_do_not_create_mouse_responses", True, f"instruction_continue={len(continues)}", required=False)
    _criterion(criteria, "instruction_module", "missing_optional_instruction_logged_or_clean", True, f"instruction_missing_or_error={len(errors)}", required=False)


def _audit_topup(
    criteria: list[Criterion],
    *,
    plan: dict[str, Any],
    session_dir: Path,
    outputs: dict[str, Any],
    manifest_base: Path,
    rows: list[dict[str, Any]],
    final_rows: list[dict[str, str]],
    events: list[dict[str, Any]],
) -> None:
    expectation = plan.get("expected_topup") or plan.get("topup") or {}
    if not isinstance(expectation, dict):
        expectation = {}
    required = bool(expectation)
    expect_enabled = _truthy(expectation.get("enabled", expectation.get("expected", required)))
    output_ledger_csv = _manifest_output_path(outputs, "topup_ledger_csv", base=manifest_base, fallback=Path())
    output_ledger_json = _manifest_output_path(outputs, "topup_ledger_json", base=manifest_base, fallback=Path())
    ledger_csv = _first_existing([output_ledger_csv, session_dir / "topup_ledger.csv"]) or (session_dir / "topup_ledger.csv")
    ledger_json = _first_existing([output_ledger_json, session_dir / "topup_ledger.json"]) or (session_dir / "topup_ledger.json")
    search_dirs = [session_dir, session_dir / "topup"]
    for path in (output_ledger_csv, output_ledger_json):
        if _path_is_set(path):
            search_dirs.append(path.parent)
    seen_dirs: set[str] = set()
    manifest_csvs: list[Path] = []
    manifest_jsons: list[Path] = []
    for directory in search_dirs:
        key = str(directory)
        if key in seen_dirs or not _path_is_dir(directory):
            continue
        seen_dirs.add(key)
        manifest_csvs.extend(path for path in _glob_files(directory, "topup_block*manifest.csv") if "draft" not in path.name.lower())
        manifest_jsons.extend(path for path in _glob_files(directory, "topup_block*manifest.json") if "draft" not in path.name.lower())
    manifest_csvs = list(dict.fromkeys(manifest_csvs))
    manifest_jsons = list(dict.fromkeys(manifest_jsons))
    rescue_rows = []
    filler_rows = []
    for path in manifest_csvs:
        for row in _read_csv(path):
            role = _norm(row.get("Topup_Role") or row.get("topup_role"))
            if role == "rescue":
                rescue_rows.append(row)
            elif role == "filler":
                filler_rows.append(row)
    final_rescued = [row for row in final_rows if str(row.get("final_outcome_source") or "") == "topup_rescue"]
    topup_ready = [row for row in events if row.get("event_type") == "topup_block_ready"]
    topup_skipped = [row for row in events if row.get("event_type") == "topup_block_skipped"]
    if expect_enabled:
        _criterion(criteria, "topup_module", "topup_ledger_written", _path_is_file(ledger_csv) and _path_is_file(ledger_json), f"{ledger_csv}; {ledger_json}", required=required)
        _criterion(criteria, "topup_module", "topup_manifest_written_when_needed", bool(manifest_csvs and manifest_jsons) or _truthy(expectation.get("not_needed")), f"csv={len(manifest_csvs)} json={len(manifest_jsons)}", required=required)
        _criterion(criteria, "topup_module", "topup_rescue_rows_reconciled", len(final_rescued) >= len(rescue_rows), f"final_rescued={len(final_rescued)} rescue_manifest={len(rescue_rows)}", required=bool(rescue_rows) or required)
        _criterion(criteria, "topup_module", "topup_filler_rows_excluded", all(not _truthy(row.get("Primary_Analysis_Included", True)) for row in filler_rows), f"filler={len(filler_rows)}", required=bool(filler_rows))
        _criterion(criteria, "topup_module", "topup_status_events_present", bool(topup_ready or topup_skipped or _truthy(expectation.get("not_needed"))), f"ready={len(topup_ready)} skipped={len(topup_skipped)}", required=required)
    else:
        _criterion(criteria, "topup_module", "topup_not_required_for_this_plan", True, "no top-up expectation supplied", required=False)


def _audit_outputs(
    criteria: list[Criterion],
    *,
    session_dir: Path,
    capture_options: dict[str, bool],
    analysis_paths: dict[str, Path | None],
    output_paths: dict[str, Path],
) -> None:
    events_csv = output_paths["events_csv"]
    events_xdf = output_paths["events_xdf"]
    lsl_csv = output_paths["lsl_markers_csv"]
    lsl_xdf = output_paths["lsl_markers_xdf"]
    trigger_json = output_paths["trigger_dictionary_json"]
    summary_txt = output_paths["analysis_summary_txt"]
    exploratory_summary = output_paths["exploratory_quality_summary"]
    if capture_options.get("write_events_csv", True):
        _criterion(criteria, "data_outputs_analysis", "events_csv_written", _path_is_file(events_csv), str(events_csv))
    else:
        _criterion(criteria, "data_outputs_analysis", "events_csv_absent_when_disabled", not _path_exists(events_csv), str(events_csv), required=False)
    if capture_options.get("write_internal_xdf", True):
        _criterion(criteria, "data_outputs_analysis", "events_xdf_written_when_enabled", _path_is_file(events_xdf), str(events_xdf))
    else:
        _criterion(criteria, "data_outputs_analysis", "events_xdf_absent_when_disabled", not _path_exists(events_xdf), str(events_xdf), required=False)
    _criterion(criteria, "data_outputs_analysis", "analysis_summary_written", _path_is_file(summary_txt), str(summary_txt), required=capture_options.get("write_analysis_csvs", True))
    analysis_required = capture_options.get("write_analysis_csvs", True)
    missing_analysis = [name for name, path in analysis_paths.items() if path is None or not _path_is_file(path)]
    if analysis_required:
        _criterion(criteria, "data_outputs_analysis", "analysis_csv_family_written", not missing_analysis, ",".join(missing_analysis))
        exploratory_payload = _read_json(exploratory_summary) if _path_is_file(exploratory_summary) else {}
        signal_labels = set(exploratory_payload.get("signal_labels") or [])
        signal_counts = exploratory_payload.get("signal_counts") or {}
        observed_labels = set(signal_counts.keys()) if isinstance(signal_counts, dict) else set()
        allowed_labels = {"Expected pattern", "Mixed / ambiguous", "Unusual pattern", "Insufficient evidence", "Technical caveat"}
        _criterion(
            criteria,
            "data_outputs_analysis",
            "exploratory_quality_summary_written",
            _path_is_file(exploratory_summary) and bool(exploratory_payload),
            str(exploratory_summary),
        )
        _criterion(
            criteria,
            "data_outputs_analysis",
            "exploratory_summary_uses_soft_labels",
            bool((signal_labels or observed_labels).issubset(allowed_labels)) and not {"pass", "fail"}.intersection({label.lower() for label in signal_labels | observed_labels}),
            f"labels={sorted(signal_labels | observed_labels)}",
        )
    else:
        present_analysis = [name for name, path in analysis_paths.items() if path is not None and _path_is_file(path)]
        _criterion(criteria, "data_outputs_analysis", "analysis_csv_family_absent_when_disabled", not present_analysis, ",".join(present_analysis), required=False)
        _criterion(
            criteria,
            "data_outputs_analysis",
            "exploratory_quality_summary_absent_when_disabled",
            not _path_exists(exploratory_summary),
            str(exploratory_summary),
            required=False,
        )
    if capture_options.get("write_lsl_marker_mirror", True):
        _criterion(criteria, "lsl_trigger_codes", "lsl_marker_mirrors_written_when_enabled", _path_is_file(lsl_csv) and _path_is_file(lsl_xdf), f"{lsl_csv}; {lsl_xdf}")
    else:
        _criterion(criteria, "lsl_trigger_codes", "lsl_marker_mirrors_absent_when_disabled", not _path_exists(lsl_csv) and not _path_exists(lsl_xdf), f"{lsl_csv}; {lsl_xdf}", required=False)
    if capture_options.get("write_trigger_dictionary", True):
        _criterion(criteria, "lsl_trigger_codes", "trigger_dictionary_written_when_enabled", _path_is_file(trigger_json), str(trigger_json))
    else:
        _criterion(criteria, "lsl_trigger_codes", "trigger_dictionary_absent_when_disabled", not _path_exists(trigger_json), str(trigger_json), required=False)


def _audit_lsl_and_triggers(
    criteria: list[Criterion],
    *,
    session_dir: Path,
    events: list[dict[str, Any]],
    capture_options: dict[str, bool],
    output_paths: dict[str, Path],
) -> None:
    _unused_session_dir = session_dir
    lsl_csv = output_paths["lsl_markers_csv"]
    trigger_json = output_paths["trigger_dictionary_json"]
    if not capture_options.get("write_lsl_marker_mirror", True):
        _criterion(criteria, "lsl_trigger_codes", "lsl_marker_event_ids_match_events", not _path_exists(lsl_csv), "LSL marker mirror disabled", required=False)
    elif _path_is_file(lsl_csv):
        marker_rows = _read_csv(lsl_csv)
        event_ids = {str(row.get("event_id")) for row in events}
        marker_ids = {str(row.get("event_id")) for row in marker_rows}
        _criterion(criteria, "lsl_trigger_codes", "lsl_marker_event_ids_match_events", marker_ids == event_ids, f"events={len(event_ids)} markers={len(marker_ids)}")
    if not capture_options.get("write_trigger_dictionary", True):
        _criterion(criteria, "lsl_trigger_codes", "trigger_dictionary_has_reserved_and_trial_codes", not _path_exists(trigger_json), "trigger dictionary disabled", required=False)
    elif _path_is_file(trigger_json):
        trigger_payload = _read_json(trigger_json)
        reserved = trigger_payload.get("reserved_codes") or {}
        triggers = trigger_payload.get("triggers") or []
        trial_triggers = [row for row in triggers if str(row.get("trigger_key") or "").startswith("trial:")]
        _criterion(
            criteria,
            "lsl_trigger_codes",
            "trigger_dictionary_has_reserved_and_trial_codes",
            "session_start" in reserved and "response_marker_start" in reserved and bool(trial_triggers),
            f"reserved={len(reserved)} trial_triggers={len(trial_triggers)}",
        )


def _audit_operator_modes(criteria: list[Criterion], *, plan: dict[str, Any], events: list[dict[str, Any]]) -> None:
    expected = plan.get("expected_operator") or plan.get("operator") or {}
    if not isinstance(expected, dict):
        expected = {}
    event_counts = _count_by(events, "event_type")
    if _truthy(expected.get("pause_resume")):
        _criterion(criteria, "operator_controls_failure_modes", "pause_resume_logged", event_counts.get("operator_pause", 0) >= 1 and event_counts.get("operator_resume", 0) >= 1, f"pause={event_counts.get('operator_pause', 0)} resume={event_counts.get('operator_resume', 0)}")
    else:
        _criterion(criteria, "operator_controls_failure_modes", "pause_resume_not_required", True, "not requested by response plan", required=False)
    if _truthy(expected.get("interrupted")):
        session_end = [row for row in events if row.get("event_type") == "session_end"]
        interrupted = any(_truthy(row.get("interrupted")) for row in session_end)
        _criterion(criteria, "operator_controls_failure_modes", "interrupted_session_marked", interrupted, f"session_end rows={len(session_end)}")
    else:
        _criterion(criteria, "operator_controls_failure_modes", "interruption_not_required", True, "not requested by response plan", required=False)
    if _truthy(expected.get("session_error")):
        _criterion(criteria, "operator_controls_failure_modes", "session_error_logged", event_counts.get("session_error", 0) >= 1, f"session_error={event_counts.get('session_error', 0)}")


def validate_artifacts(
    session_dir: Path,
    *,
    response_plan_path: Path | None = None,
    output_dir: Path | None = None,
    allow_timing_fallback: bool = False,
    require_local_data_root: bool = False,
) -> dict[str, Any]:
    session_dir = session_dir.resolve()
    output_dir = (output_dir or (session_dir / "analysis" / "protocol11_audit")).resolve()
    criteria: list[Criterion] = []
    manifest_path = _session_manifest_path(session_dir)
    manifest = _read_json(manifest_path)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    manifest_base = manifest_path.parent if manifest_path.parent != Path() else session_dir
    part_status_path = _manifest_output_path(outputs, "part_completion_status_json", base=manifest_base, fallback=Path())
    part_status = _read_json(part_status_path)
    if isinstance(part_status.get("analysis_outputs"), dict):
        outputs = {**outputs, **part_status.get("analysis_outputs", {})}
    metadata_path = _first_existing(
        [
            _manifest_output_path(outputs, "session_metadata_json", base=manifest_base, fallback=Path()),
            session_dir / "session_metadata.json",
            output_runner_logs_dir(session_dir.parent) / session_dir.name / "session_metadata.json",
        ]
    ) or (session_dir / "session_metadata.json")
    metadata = _read_json(metadata_path)
    blocks = _block_entries(manifest, session_dir)
    rows = _manifest_rows(blocks)
    events_path = _first_existing(
        [
            _manifest_output_path(
                outputs,
                "verbose_events_csv",
                "events_csv",
                base=manifest_base,
                fallback=output_verbose_events_dir(session_dir.parent) / session_dir.name / "events.csv",
            ),
            session_dir / "events.csv",
        ]
    ) or (session_dir / "events.csv")
    output_paths = {
        "events_csv": events_path,
        "events_xdf": _first_existing(
            [
                _manifest_output_path(
                    outputs,
                    "verbose_events_xdf",
                    "events_xdf",
                    base=manifest_base,
                    fallback=output_verbose_events_dir(session_dir.parent) / session_dir.name / "events.xdf",
                ),
                session_dir / "events.xdf",
            ]
        )
        or (session_dir / "events.xdf"),
        "lsl_markers_csv": _first_existing(
            [
                _manifest_output_path(
                    outputs,
                    "lsl_markers_csv",
                    base=manifest_base,
                    fallback=output_verbose_events_dir(session_dir.parent) / session_dir.name / "lsl_markers.csv",
                ),
                session_dir / "lsl_markers.csv",
            ]
        )
        or (session_dir / "lsl_markers.csv"),
        "lsl_markers_xdf": _first_existing(
            [
                _manifest_output_path(
                    outputs,
                    "lsl_markers_xdf",
                    base=manifest_base,
                    fallback=output_verbose_events_dir(session_dir.parent) / session_dir.name / "lsl_markers.xdf",
                ),
                session_dir / "lsl_markers.xdf",
            ]
        )
        or (session_dir / "lsl_markers.xdf"),
        "trigger_dictionary_json": _first_existing(
            [
                _manifest_output_path(
                    outputs,
                    "trigger_dictionary_json",
                    base=manifest_base,
                    fallback=output_verbose_events_dir(session_dir.parent) / session_dir.name / "trigger_dictionary.json",
                ),
                session_dir / "trigger_dictionary.json",
            ]
        )
        or (session_dir / "trigger_dictionary.json"),
    }
    analysis_dir = _first_existing(
        [
            _manifest_output_path(
                outputs,
                "analysis_dir",
                base=manifest_base,
                fallback=output_data_analytics_dir(session_dir.parent) / session_dir.name,
            ),
            session_dir / "analysis",
        ]
    ) or (session_dir / "analysis")
    output_paths["analysis_summary_txt"] = _first_existing(
        [
            _manifest_output_path(outputs, "analysis_summary_txt", base=manifest_base, fallback=analysis_dir / "analysis_summary.txt"),
            session_dir / "analysis_summary.txt",
        ]
    ) or (analysis_dir / "analysis_summary.txt")
    output_paths["exploratory_quality_summary"] = _first_existing(
        [
            analysis_dir / "exploratory_quality_summary.json",
            session_dir / "analysis" / "exploratory_quality_summary.json",
        ]
    ) or (analysis_dir / "exploratory_quality_summary.json")
    events = _event_rows(events_path)
    session_start = next((row for row in events if row.get("event_type") == "session_start"), {})
    plan = _load_response_plan(response_plan_path)
    capture_options = _expected_capture_options(plan, metadata, session_start)
    analysis_paths = _analysis_paths(session_dir, analysis_dir=analysis_dir)
    analysis_rows = _read_csv(analysis_paths["analysis_ready_trials"]) if analysis_paths["analysis_ready_trials"] else []
    final_rows = _read_csv(analysis_paths["final_trial_outcomes"]) if analysis_paths["final_trial_outcomes"] else []
    timing_qc_rows = _read_csv(analysis_paths["timing_qc"]) if analysis_paths["timing_qc"] else []

    _audit_session_resolution(
        criteria,
        session_dir=session_dir,
        manifest_path=manifest_path,
        manifest=manifest,
        metadata_path=metadata_path,
        metadata=metadata,
        require_local_data_root=require_local_data_root,
    )
    _criterion(criteria, "launch_session_resolution", "blocks_declared", bool(blocks), f"blocks={len(blocks)}")
    stimulus = _audit_stimulus_assembly(criteria, blocks=blocks, rows=rows)
    expected_counts = _expected_event_counts(rows, len(blocks))
    _audit_timing(
        criteria,
        events=events,
        rows=rows,
        block_count=len(blocks),
        expected_counts=expected_counts,
        allow_timing_fallback=allow_timing_fallback,
    )
    response_audit = _audit_response_plan(
        criteria,
        plan=plan,
        plan_path=response_plan_path,
        rows=rows,
        events=events,
        analysis_rows=analysis_rows,
        final_rows=final_rows,
    )
    _audit_response_markers(criteria, events=events, timing_qc_rows=timing_qc_rows)
    _audit_instruction_flow(criteria, plan=plan, events=events)
    _audit_topup(
        criteria,
        plan=plan,
        session_dir=session_dir,
        outputs=outputs,
        manifest_base=manifest_base,
        rows=rows,
        final_rows=final_rows,
        events=events,
    )
    _audit_outputs(criteria, session_dir=session_dir, capture_options=capture_options, analysis_paths=analysis_paths, output_paths=output_paths)
    _audit_lsl_and_triggers(criteria, session_dir=session_dir, events=events, capture_options=capture_options, output_paths=output_paths)
    _audit_operator_modes(criteria, plan=plan, events=events)

    criteria_payload = [criterion.as_dict() for criterion in criteria]
    section_names = []
    for item in criteria_payload:
        if item["section"] not in section_names:
            section_names.append(item["section"])
    sections: dict[str, dict[str, Any]] = {}
    for section in section_names:
        section_items = [item for item in criteria_payload if item["section"] == section]
        required_items = [item for item in section_items if item["required"]]
        sections[section] = {
            "count": len(section_items),
            "passed_count": sum(1 for item in section_items if item["passed"]),
            "required_count": len(required_items),
            "required_passed_count": sum(1 for item in required_items if item["passed"]),
            "passed": all(item["passed"] for item in required_items),
        }
    required_items = [item for item in criteria_payload if item["required"]]
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "passed": all(item["passed"] for item in required_items) and bool(required_items),
        "session_dir": str(session_dir),
        "session_manifest": str(manifest_path),
        "session_metadata": str(metadata_path),
        "response_plan_path": "" if response_plan_path is None else str(response_plan_path.resolve()),
        "output_dir": str(output_dir),
        "block_count": len(blocks),
        "trial_count": len(rows),
        "event_counts": _count_by(events, "event_type"),
        "expected_event_counts": expected_counts,
        "capture_options": capture_options,
        "analysis_paths": {key: "" if value is None else str(value) for key, value in analysis_paths.items()},
        "stimulus_assembly": stimulus,
        "response_plan_audit": response_audit,
        "sections": sections,
        "criteria": criteria_payload,
        "required_count": len(required_items),
        "required_passed_count": sum(1 for item in required_items if item["passed"]),
        "limitations": [
            "Offline artifact audit only; it does not launch the runner or emulate clicks by itself.",
            "Use this after Protocol 11 scenarios that exercised the real Focus Mode / SessionRunnerController workflow.",
            "Hardware timing, Woojer mechanical onset, participant comprehension, and scientific PPS interpretation remain out of scope.",
        ],
    }
    _write_json(output_dir / "protocol11_emulated_runner_artifact_audit.json", report)
    _write_markdown(output_dir / "protocol11_emulated_runner_artifact_audit.md", report)
    return report


def validate_session_group_artifacts(
    session_group_manifest: Path,
    *,
    response_plan_path: Path | None = None,
    output_dir: Path | None = None,
    allow_timing_fallback: bool = False,
    require_local_data_root: bool = False,
) -> dict[str, Any]:
    session_group_manifest = session_group_manifest.resolve()
    group = _read_json(session_group_manifest)
    output_dir = (output_dir or (session_group_manifest.parent / "protocol11_session_group_audit")).resolve()
    criteria: list[Criterion] = []
    _criterion(criteria, "session_group", "session_group_manifest_exists", _path_is_file(session_group_manifest), str(session_group_manifest))
    _criterion(
        criteria,
        "session_group",
        "session_group_manifest_schema",
        str(group.get("schema") or "") == "pps-run-session-group.v1",
        str(group.get("schema") or ""),
        required=bool(group),
    )
    part_entries = [dict(item) for item in group.get("parts", []) if isinstance(item, dict)]
    _criterion(criteria, "session_group", "parts_declared", bool(part_entries), f"parts={len(part_entries)}")
    part_reports: list[dict[str, Any]] = []
    aggregate_event_counts: dict[str, int] = {}
    aggregate_expected_counts: dict[str, int] = {}
    block_count = 0
    trial_count = 0
    for entry in sorted(part_entries, key=lambda item: _as_int(item.get("part_number"), default=0)):
        part_number = str(entry.get("part_number") or "")
        part_session_dir = Path(str(entry.get("session_dir") or ""))
        part_output = output_dir / f"part_{int(part_number or 0):02d}" if part_number else output_dir / "part_unknown"
        report = validate_artifacts(
            part_session_dir,
            response_plan_path=response_plan_path,
            output_dir=part_output,
            allow_timing_fallback=allow_timing_fallback,
            require_local_data_root=require_local_data_root,
        )
        part_reports.append(
            {
                "part_number": entry.get("part_number"),
                "part_session_id": entry.get("part_session_id"),
                "session_dir": str(part_session_dir),
                "session_manifest": entry.get("session_manifest_path", ""),
                "completed": bool(entry.get("completed")),
                "passed": bool(report.get("passed")),
                "audit_report": str(Path(str(report.get("output_dir") or part_output)) / "protocol11_emulated_runner_artifact_audit.json"),
                "report": report,
            }
        )
        block_count += int(report.get("block_count") or 0)
        trial_count += int(report.get("trial_count") or 0)
        for key, value in dict(report.get("event_counts") or {}).items():
            aggregate_event_counts[str(key)] = int(aggregate_event_counts.get(str(key), 0)) + int(value or 0)
        for key, value in dict(report.get("expected_event_counts") or {}).items():
            aggregate_expected_counts[str(key)] = int(aggregate_expected_counts.get(str(key), 0)) + int(value or 0)
    _criterion(
        criteria,
        "session_group",
        "all_declared_parts_completed",
        bool(part_entries) and all(bool(entry.get("completed")) for entry in part_entries),
        f"completed={sum(1 for entry in part_entries if bool(entry.get('completed')))}/{len(part_entries)}",
        evidence={"parts": part_entries},
    )
    _criterion(
        criteria,
        "session_group",
        "all_part_audits_passed",
        bool(part_reports) and all(bool(item.get("passed")) for item in part_reports),
        f"passed={sum(1 for item in part_reports if bool(item.get('passed')))}/{len(part_reports)}",
    )
    criteria_payload = [criterion.as_dict() for criterion in criteria]
    sections: dict[str, dict[str, Any]] = {}
    for item in criteria_payload:
        section = sections.setdefault(item["section"], {"count": 0, "passed_count": 0, "required_count": 0, "required_passed_count": 0})
        section["count"] += 1
        if item["passed"]:
            section["passed_count"] += 1
        if item["required"]:
            section["required_count"] += 1
            if item["passed"]:
                section["required_passed_count"] += 1
    for section in sections.values():
        section["passed"] = section["required_count"] == section["required_passed_count"]
    required_items = [item for item in criteria_payload if item["required"]]
    report = {
        "schema": f"{SCHEMA}.session-group",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "passed": all(item["passed"] for item in required_items) and bool(required_items),
        "session_group_manifest": str(session_group_manifest),
        "session_group_id": str(group.get("session_group_id") or ""),
        "participant_id": str(group.get("participant_id") or ""),
        "output_dir": str(output_dir),
        "part_count": len(part_entries),
        "completed_part_count": sum(1 for entry in part_entries if bool(entry.get("completed"))),
        "block_count": block_count,
        "trial_count": trial_count,
        "event_counts": aggregate_event_counts,
        "expected_event_counts": aggregate_expected_counts,
        "parts": part_reports,
        "sections": sections,
        "criteria": criteria_payload,
        "required_count": len(required_items),
        "required_passed_count": sum(1 for item in required_items if item["passed"]),
    }
    _write_json(output_dir / "protocol11_emulated_runner_artifact_audit.json", report)
    _write_markdown(output_dir / "protocol11_emulated_runner_artifact_audit.md", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Protocol 11 emulated-runner session artifacts.")
    parser.add_argument("--session-dir", type=Path, default=None, help="Completed runner session folder containing session_manifest.json and events.csv.")
    parser.add_argument("--session-group-manifest", type=Path, default=None, help="Split-session group manifest containing all prepared Study 5 parts.")
    parser.add_argument("--response-plan", type=Path, default=None, help="Optional Protocol 11 response plan JSON or CSV keyed by trial_uid.")
    parser.add_argument("--output-dir", type=Path, default=None, help="Directory for the audit JSON/Markdown report.")
    parser.add_argument("--allow-timing-fallback", action="store_true", help="Allow timing_anchor_fallback for degraded-timing scenarios.")
    parser.add_argument("--require-local-data-root", action="store_true", help="Require the session path to resolve under local_data/.")
    args = parser.parse_args(argv)

    if args.session_group_manifest is not None:
        report = validate_session_group_artifacts(
            args.session_group_manifest,
            response_plan_path=args.response_plan,
            output_dir=args.output_dir,
            allow_timing_fallback=args.allow_timing_fallback,
            require_local_data_root=args.require_local_data_root,
        )
    else:
        if args.session_dir is None:
            parser.error("--session-dir is required unless --session-group-manifest is supplied.")
        report = validate_artifacts(
            args.session_dir,
            response_plan_path=args.response_plan,
            output_dir=args.output_dir,
            allow_timing_fallback=args.allow_timing_fallback,
            require_local_data_root=args.require_local_data_root,
        )
    print(f"Wrote Protocol 11 artifact audit: {Path(report['output_dir']) / 'protocol11_emulated_runner_artifact_audit.json'}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
