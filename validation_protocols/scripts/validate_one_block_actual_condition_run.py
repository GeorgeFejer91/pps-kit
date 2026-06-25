"""Validate an actual-condition one-block runner session.

This script does not play audio or touch hardware. It audits the output folder
created after the real runner has administered exactly one prepared Segment 5/6
block under experiment-like conditions.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import soundfile as sf


SCHEMA = "pps-one-block-actual-condition-validation.v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _read_events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(path):
        payload_text = row.get("payload_json", "") or ""
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = {}
        merged: dict[str, Any] = dict(row)
        merged["payload"] = payload
        rows.append(merged)
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _event_type(row: dict[str, Any]) -> str:
    return str(row.get("event_type", "")).strip()


def _event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id", "")).strip()


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    return payload if isinstance(payload, dict) else {}


def _float(value: Any) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _ms_stats(values: list[float]) -> dict[str, Any]:
    values = [value for value in values if math.isfinite(value)]
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)
    return {
        "count": len(values),
        "mean_ms": statistics.fmean(values),
        "sd_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[p95_index],
        "min_ms": min(values),
        "max_ms": max(values),
    }


def _criterion(criteria: list[dict[str, Any]], key: str, passed: bool, evidence: str, *, required: bool = True) -> None:
    criteria.append(
        {
            "key": key,
            "required": bool(required),
            "passed": bool(passed),
            "status": "passed" if passed else ("failed" if required else "not_measured"),
            "evidence": evidence,
        }
    )


def _candidate_path(text: Any, session_dir: Path) -> Path:
    path = Path(str(text or ""))
    if not str(path):
        return path
    if path.is_absolute():
        return path
    session_relative = session_dir / path
    if session_relative.exists():
        return session_relative
    if path.exists():
        return path
    return session_relative


def _analysis_ready_path(session_dir: Path, manifest: dict[str, Any]) -> Path | None:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    analysis_dir = _candidate_path(outputs.get("analysis_dir", ""), session_dir) if outputs else session_dir / "analysis"
    candidates = sorted(analysis_dir.glob("*_analysis_ready_trials.csv")) if analysis_dir.exists() else []
    if candidates:
        return candidates[0]
    candidates = sorted(session_dir.glob("**/*_analysis_ready_trials.csv"))
    return candidates[0] if candidates else None


def _timing_qc_path(session_dir: Path, manifest: dict[str, Any]) -> Path | None:
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    analysis_dir = _candidate_path(outputs.get("analysis_dir", ""), session_dir) if outputs else session_dir / "analysis"
    candidates = sorted(analysis_dir.glob("*_timing_qc.csv")) if analysis_dir.exists() else []
    return candidates[0] if candidates else None


def _find_recordings(session_dir: Path) -> list[Path]:
    recordings: list[Path] = []
    recordings.extend(sorted(session_dir.glob("*.wav")))
    recordings_dir = session_dir / "recordings"
    if recordings_dir.exists():
        recordings.extend(sorted(recordings_dir.glob("*.wav")))
    return list(dict.fromkeys(recordings))


def _xdf_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"exists": False, "loaded": False, "sample_count": 0, "message": "missing"}
    try:
        import pyxdf  # type: ignore

        streams, _header = pyxdf.load_xdf(str(path))
    except Exception as exc:  # pragma: no cover - depends on optional native parser behavior
        return {"exists": True, "loaded": False, "sample_count": 0, "message": str(exc)}
    sample_count = 0
    for stream in streams:
        time_stamps = stream.get("time_stamps", [])
        sample_count += len(time_stamps)
    return {"exists": True, "loaded": True, "sample_count": sample_count, "message": "loaded with pyxdf"}


def _mouse_marker_deltas(events: list[dict[str, Any]]) -> list[float]:
    mouse_by_id = {_event_id(row): row for row in events if _event_type(row) == "mouse_click"}
    deltas = []
    for marker in events:
        if _event_type(marker) != "response_marker_start":
            continue
        mouse_id = str(_payload(marker).get("mouse_event_id", "")).strip()
        mouse = mouse_by_id.get(mouse_id)
        if not mouse:
            continue
        delta = (_float(marker.get("monotonic_time")) - _float(mouse.get("monotonic_time"))) * 1000.0
        if math.isfinite(delta):
            deltas.append(delta)
    return deltas


def _source_texts(manifest: dict[str, Any], block_rows: list[dict[str, str]]) -> list[str]:
    texts: list[str] = []
    for key in ("source_run_setup_manifest_path", "execution_mode"):
        value = manifest.get(key)
        if value:
            texts.append(str(value))
    for block in manifest.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        for key in ("label", "manifest_path", "wav_path"):
            value = block.get(key)
            if value:
                texts.append(str(value))
        metadata = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
        for key in ("source_block_csv_path", "source_block_label", "execution_mode"):
            value = metadata.get(key)
            if value:
                texts.append(str(value))
    for row in block_rows[:20]:
        for key in ("noise_type", "sequence_labels", "sequence_variant_key", "source_file_name", "trial_file_path"):
            value = row.get(key) or row.get(key.title())
            if value:
                texts.append(str(value))
    return texts


def _looks_like_actual_experiment_condition(manifest: dict[str, Any], block_rows: list[dict[str, str]]) -> tuple[bool, list[str]]:
    suspicious_terms = (
        "segment_fixture",
        "validation_rect_pulse",
        "validation pulse",
        "dummy_3ch",
        "dummy_pulse",
        "fake audio",
        "fake_audio",
    )
    findings = []
    for text in _source_texts(manifest, block_rows):
        lower = text.lower().replace("\\", "/")
        if any(term in lower for term in suspicious_terms):
            findings.append(text)
    return not findings, findings


def _has_value(row: dict[str, str], *keys: str) -> bool:
    for key in keys:
        if str(row.get(key, "")).strip() not in {"", "nan", "None", "none"}:
            return True
    return False


def _has_any_key(row: dict[str, str], *keys: str) -> bool:
    return any(key in row for key in keys)


def _trial_type(row: dict[str, str]) -> str:
    value = str(row.get("Trial_Type") or row.get("trial_type") or "").strip().lower().replace("_", "-")
    if value in {"audio-tactile", "audiotactile"}:
        return "Audio-Tactile"
    if value == "baseline":
        return "Baseline"
    if value == "catch":
        return "Catch"
    return str(row.get("Trial_Type") or row.get("trial_type") or "").strip()


def _explicit_or_inferred_count(
    block_rows: list[dict[str, str]],
    *,
    sample_keys: tuple[str, ...],
    second_keys: tuple[str, ...],
    inferred_trial_types: set[str],
) -> int:
    explicit_columns_exist = any(_has_any_key(row, *(sample_keys + second_keys)) for row in block_rows)
    if explicit_columns_exist:
        return sum(1 for row in block_rows if _has_value(row, *(sample_keys + second_keys)))
    return sum(1 for row in block_rows if _trial_type(row) in inferred_trial_types)


def _expected_event_counts(block_rows: list[dict[str, str]], trial_count: int) -> dict[str, int]:
    """Return event counts implied by the actual block CSV.

    Catch trials do not always have tactile onsets and baseline trials do not
    always have looming onsets, so publication-grade audits must compare
    against the prepared block design rather than total trial count alone.
    """

    if not block_rows:
        return {
            "trial_start": trial_count,
            "looming_onset": trial_count,
            "tactile_onset": trial_count,
            "response_window_onset": trial_count,
            "trial_end": trial_count,
        }

    return {
        "trial_start": len(block_rows),
        "looming_onset": _explicit_or_inferred_count(
            block_rows,
            sample_keys=("Looming_Onset_Sample", "looming_onset_sample"),
            second_keys=("Looming_Onset_S", "looming_onset_s"),
            inferred_trial_types={"Audio-Tactile", "Catch"},
        ),
        "tactile_onset": _explicit_or_inferred_count(
            block_rows,
            sample_keys=("Tactile_Onset_Sample", "tactile_onset_sample"),
            second_keys=("Tactile_Onset_S", "tactile_onset_s"),
            inferred_trial_types={"Audio-Tactile", "Baseline"},
        ),
        "response_window_onset": _explicit_or_inferred_count(
            block_rows,
            sample_keys=("Response_Window_Onset_Sample", "response_window_onset_sample"),
            second_keys=("Response_Window_Onset_S", "response_window_onset_s"),
            inferred_trial_types={"Audio-Tactile", "Baseline", "Catch"},
        ),
        "trial_end": len(block_rows),
    }


def validate_session(
    session_dir: Path,
    *,
    output_dir: Path | None = None,
    require_xdf: bool = True,
    require_lsl_marker_mirror: bool = True,
    require_trigger_dictionary: bool = True,
    require_response_markers: bool = True,
    require_backup_recording: bool = True,
    require_loopback_report: bool = False,
    lsl_probe_csv: Path | None = None,
    loopback_report_json: Path | None = None,
    allow_validation_fixture: bool = False,
) -> dict[str, Any]:
    session_dir = Path(session_dir)
    output_dir = Path(output_dir) if output_dir else session_dir / "analysis" / "actual_condition_validation"

    manifest_path = session_dir / "session_manifest.json"
    manifest = _read_json(manifest_path)
    events_csv = session_dir / "events.csv"
    events = _read_events(events_csv)
    event_counts = Counter(_event_type(row) for row in events)
    event_ids = [_event_id(row) for row in events if _event_id(row)]
    duplicate_event_ids = sorted({event_id for event_id in event_ids if event_ids.count(event_id) > 1})

    blocks = manifest.get("blocks") if isinstance(manifest.get("blocks"), list) else []
    block = blocks[0] if blocks and isinstance(blocks[0], dict) else {}
    block_csv_path = _candidate_path(block.get("manifest_path", ""), session_dir) if block else Path()
    block_wav_path = _candidate_path(block.get("wav_path", ""), session_dir) if block else Path()
    block_rows = _read_csv(block_csv_path)
    trial_count = int(block.get("trial_count") or len(block_rows) or event_counts.get("trial_start", 0) or 0)
    expected_event_counts = _expected_event_counts(block_rows, trial_count)

    analysis_ready = _analysis_ready_path(session_dir, manifest)
    analysis_rows = _read_csv(analysis_ready) if analysis_ready else []
    timing_qc = _timing_qc_path(session_dir, manifest)
    timing_qc_rows = _read_csv(timing_qc) if timing_qc else []

    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    xdf_path = _candidate_path(outputs.get("events_xdf", session_dir / "events.xdf"), session_dir)
    lsl_markers_path = _candidate_path(outputs.get("lsl_markers_csv", session_dir / "lsl_markers.csv"), session_dir)
    trigger_dictionary_path = _candidate_path(outputs.get("trigger_dictionary_json", session_dir / "trigger_dictionary.json"), session_dir)
    lsl_rows = _read_csv(lsl_markers_path)
    probe_rows = _read_csv(lsl_probe_csv) if lsl_probe_csv else []
    recordings = _find_recordings(session_dir)

    criteria: list[dict[str, Any]] = []
    _criterion(criteria, "session_manifest_exists", bool(manifest), f"{manifest_path}")
    _criterion(criteria, "participant_block_wavs_mode", manifest.get("execution_mode") == "participant_block_wavs", f"execution_mode={manifest.get('execution_mode')!r}")
    _criterion(criteria, "exactly_one_block", len(blocks) == 1, f"block_count={len(blocks)}")
    _criterion(criteria, "block_csv_exists", block_csv_path.is_file(), f"{block_csv_path}")
    _criterion(criteria, "block_wav_exists", block_wav_path.is_file(), f"{block_wav_path}")
    _criterion(criteria, "block_csv_trial_count", len(block_rows) == trial_count and trial_count > 0, f"block_rows={len(block_rows)} trial_count={trial_count}")

    wav_info: dict[str, Any] = {}
    if block_wav_path.is_file():
        try:
            info = sf.info(str(block_wav_path))
            wav_info = {"sample_rate": info.samplerate, "channels": info.channels, "frames": info.frames, "duration_s": info.duration}
        except Exception as exc:
            wav_info = {"error": str(exc)}
    _criterion(criteria, "three_channel_block_wav", wav_info.get("channels") == 3, f"wav_info={wav_info}")

    actual_ok, suspicious_sources = _looks_like_actual_experiment_condition(manifest, block_rows)
    if allow_validation_fixture:
        _criterion(
            criteria,
            "actual_experiment_sources",
            True,
            "validation fixture allowed by caller; this report is not publication-grade actual-condition evidence.",
            required=False,
        )
    else:
        _criterion(criteria, "actual_experiment_sources", actual_ok, f"suspicious_sources={suspicious_sources}")

    _criterion(criteria, "events_csv_exists", events_csv.is_file(), f"{events_csv}")
    _criterion(criteria, "no_duplicate_event_ids", not duplicate_event_ids, f"duplicate_event_ids={duplicate_event_ids}")
    _criterion(criteria, "one_block_start_end", event_counts.get("block_start", 0) == 1 and event_counts.get("block_end", 0) == 1, f"block_start={event_counts.get('block_start', 0)} block_end={event_counts.get('block_end', 0)}")
    for event_type in ("trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end"):
        expected_count = expected_event_counts.get(event_type, trial_count)
        _criterion(criteria, f"{event_type}_count", event_counts.get(event_type, 0) == expected_count, f"{event_type}={event_counts.get(event_type, 0)} expected={expected_count} trial_count={trial_count}")

    timestamp_quality_counts = Counter(str(_payload(row).get("timestamp_quality", "")).strip() for row in events if _payload(row).get("timestamp_quality"))
    fallback_count = event_counts.get("timing_anchor_fallback", 0) + timestamp_quality_counts.get("block_anchor_fallback", 0)
    scheduled_actual = [row for row in events if _event_type(row) in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end", "audio_sample_zero"}]
    dac_count = sum(1 for row in scheduled_actual if _payload(row).get("timestamp_quality") == "dac_time_sample_exact")
    _criterion(criteria, "no_timing_fallback", fallback_count == 0, f"fallback_count={fallback_count} timestamp_qualities={dict(timestamp_quality_counts)}")
    _criterion(criteria, "scheduled_events_sample_exact", dac_count == len(scheduled_actual) and bool(scheduled_actual), f"dac_time_sample_exact={dac_count}/{len(scheduled_actual)}")

    _criterion(criteria, "analysis_ready_csv", bool(analysis_ready and analysis_ready.is_file()), f"{analysis_ready}")
    _criterion(criteria, "analysis_ready_rows", len(analysis_rows) == event_counts.get("tactile_onset", 0) and bool(analysis_rows), f"analysis_rows={len(analysis_rows)} tactile_onsets={event_counts.get('tactile_onset', 0)}")

    xdf = _xdf_summary(xdf_path)
    _criterion(criteria, "events_xdf_loadable", bool(xdf.get("loaded")) and int(xdf.get("sample_count") or 0) > 0, f"{xdf}", required=require_xdf)
    _criterion(criteria, "lsl_marker_mirror_exists", lsl_markers_path.is_file() and bool(lsl_rows), f"{lsl_markers_path} rows={len(lsl_rows)}", required=require_lsl_marker_mirror)
    _criterion(criteria, "trigger_dictionary_exists", trigger_dictionary_path.is_file(), f"{trigger_dictionary_path}", required=require_trigger_dictionary)
    _criterion(criteria, "backup_recording_exists", bool(recordings), f"recordings={[str(path) for path in recordings]}", required=require_backup_recording)

    if require_response_markers:
        expected_response_count = expected_event_counts.get("tactile_onset", trial_count)
        mouse_count = event_counts.get("mouse_click", 0)
        response_marker_count = event_counts.get("response_marker_start", 0)
        _criterion(criteria, "response_mouse_clicks_present", mouse_count == expected_response_count, f"mouse_click={mouse_count} expected_tactile_responses={expected_response_count} trial_count={trial_count}")
        _criterion(criteria, "response_markers_present", response_marker_count == mouse_count and response_marker_count > 0, f"response_marker_start={response_marker_count} mouse_click={mouse_count}")
        _criterion(criteria, "timing_qc_rows", len(timing_qc_rows) == response_marker_count and response_marker_count > 0, f"timing_qc_rows={len(timing_qc_rows)} response_marker_start={response_marker_count}")
    else:
        _criterion(criteria, "response_markers_present", True, "response markers not required for this audit", required=False)

    if lsl_probe_csv:
        local_actual_ids = {_event_id(row) for row in events if _event_id(row)}
        probe_ids = {str(row.get("event_id", "")).strip() for row in probe_rows if str(row.get("event_id", "")).strip()}
        missing = sorted(local_actual_ids - probe_ids)
        _criterion(criteria, "external_lsl_probe_matches", not missing and bool(probe_rows), f"probe_rows={len(probe_rows)} missing_event_ids={missing}")

    if loopback_report_json:
        loopback = _read_json(loopback_report_json)
    else:
        candidates = sorted(session_dir.glob("**/response_marker_loopback_report.json"))
        loopback = _read_json(candidates[0]) if candidates else {}
    if require_loopback_report:
        _criterion(criteria, "physical_loopback_report_passed", bool(loopback.get("passed")), f"loopback_report={loopback_report_json or 'auto'}")

    mouse_marker_deltas = _mouse_marker_deltas(events)
    rt_values = [_float(row.get("rt_ms")) for row in analysis_rows if math.isfinite(_float(row.get("rt_ms")))]
    passed = all(row["passed"] or not row["required"] for row in criteria)

    report = {
        "schema": SCHEMA,
        "passed": passed,
        "session_dir": str(session_dir),
        "output_dir": str(output_dir),
        "evidence_level": "actual_experimental_condition_one_block" if actual_ok and not allow_validation_fixture else "development_or_fixture",
        "trial_count": trial_count,
        "expected_event_type_counts": expected_event_counts,
        "event_type_counts": dict(event_counts),
        "duplicate_event_ids": duplicate_event_ids,
        "timestamp_quality_counts": dict(timestamp_quality_counts),
        "analysis_ready_trials_csv": str(analysis_ready) if analysis_ready else "",
        "analysis_ready_trial_count": len(analysis_rows),
        "rt_ms": _ms_stats(rt_values),
        "marker_minus_mouse_ms": _ms_stats(mouse_marker_deltas),
        "events_xdf": str(xdf_path),
        "xdf": xdf,
        "lsl_markers_csv": str(lsl_markers_path),
        "lsl_marker_count": len(lsl_rows),
        "trigger_dictionary_json": str(trigger_dictionary_path),
        "recordings": [str(path) for path in recordings],
        "block_csv": str(block_csv_path),
        "block_wav": str(block_wav_path),
        "block_wav_info": wav_info,
        "suspicious_non_actual_sources": suspicious_sources,
        "criteria": criteria,
        "limitations": [
            "This script audits outputs from a completed one-block run; it does not play audio or touch hardware.",
            "Physical latency claims require a matching direct loopback or response-marker loopback report.",
            "Woojer mechanical vibration onset is not measured unless a sensor report is supplied.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "one_block_actual_condition_validation.json"
    markdown_path = output_dir / "one_block_actual_condition_validation.md"
    criteria_csv = output_dir / "one_block_actual_condition_criteria.csv"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown(report, markdown_path)
    _write_csv(criteria_csv, criteria, ["key", "required", "passed", "status", "evidence"])
    return report


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# One-Block Actual-Condition Validation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Evidence level: `{report.get('evidence_level')}`",
        f"- Session dir: `{report.get('session_dir')}`",
        f"- Trial count: `{report.get('trial_count')}`",
        f"- Analysis-ready rows: `{report.get('analysis_ready_trial_count')}`",
        f"- XDF: `{json.dumps(report.get('xdf'), sort_keys=True)}`",
        f"- RT ms: `{json.dumps(report.get('rt_ms'), sort_keys=True)}`",
        f"- Mouse to response-marker ms: `{json.dumps(report.get('marker_minus_mouse_ms'), sort_keys=True)}`",
        "",
        "## Criteria",
        "",
        "| Criterion | Required | Status | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in report.get("criteria") or []:
        evidence = str(row.get("evidence", "")).replace("|", "\\|")
        lines.append(f"| `{row.get('key')}` | {row.get('required')} | {row.get('status')} | {evidence} |")
    lines.extend(["", "## Limitations", ""])
    for limitation in report.get("limitations") or []:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit one actual-condition PPS runner block.")
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--lsl-probe-csv", type=Path, default=None)
    parser.add_argument("--loopback-report-json", type=Path, default=None)
    parser.add_argument("--no-require-xdf", action="store_true")
    parser.add_argument("--no-require-lsl-marker-mirror", action="store_true")
    parser.add_argument("--no-require-trigger-dictionary", action="store_true")
    parser.add_argument("--no-require-response-markers", action="store_true")
    parser.add_argument("--no-require-backup-recording", action="store_true")
    parser.add_argument("--require-loopback-report", action="store_true")
    parser.add_argument("--allow-validation-fixture", action="store_true")
    args = parser.parse_args(argv)

    report = validate_session(
        args.session_dir,
        output_dir=args.output_dir,
        require_xdf=not args.no_require_xdf,
        require_lsl_marker_mirror=not args.no_require_lsl_marker_mirror,
        require_trigger_dictionary=not args.no_require_trigger_dictionary,
        require_response_markers=not args.no_require_response_markers,
        require_backup_recording=not args.no_require_backup_recording,
        require_loopback_report=args.require_loopback_report,
        lsl_probe_csv=args.lsl_probe_csv,
        loopback_report_json=args.loopback_report_json,
        allow_validation_fixture=args.allow_validation_fixture,
    )
    print(f"Wrote {Path(report['output_dir']) / 'one_block_actual_condition_validation.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
