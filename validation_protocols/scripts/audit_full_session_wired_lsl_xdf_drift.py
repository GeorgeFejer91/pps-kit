"""Audit a full Study 5 rehearsal's wired tactile proxy against LSL/XDF.

This final-condition gate is intentionally narrower than the older exploratory
hardwired peak audit. For Study 5 readiness, the Output-4-to-Input-4 tactile
proxy is the hardwired timing reference. Response-marker pulses are accepted
through the runtime digital audio-evidence recovery report, because the weak
hardwired response-marker proxy is not a stable peak-picking target.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time
from typing import Any

import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
SRC_ROOT = REPO_ROOT / "src"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from run_labrecorder_lsl_xdf_stress import _load_xdf_streams  # noqa: E402


SCHEMA = "pps-full-session-wired-lsl-xdf-tactile-drift-audit.v1"

TACTILE_EVENT_TYPE = "tactile_onset"
RESPONSE_MARKER_EVENT_TYPE = "response_marker_start"

MAX_XDF_LOCAL_LSL_ABS_MS = 0.1
MAX_TACTILE_RESIDUAL_P95_MS = 1.0
MAX_TACTILE_RESIDUAL_ABS_MS = 2.0
MAX_TACTILE_ADJACENT_STEP_MS = 2.0


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"full_session_wired_lsl_xdf_drift_{stamp}"


def _filesystem_path(path: Path) -> str:
    text = str(Path(path).resolve())
    if os.name == "nt" and not text.startswith("\\\\?\\"):
        if text.startswith("\\\\"):
            return "\\\\?\\UNC\\" + text.lstrip("\\")
        return "\\\\?\\" + text
    return text


def _mkdir(path: Path) -> None:
    os.makedirs(_filesystem_path(path), exist_ok=True)


def _is_file(path: Path | None) -> bool:
    if path is None or not str(path):
        return False
    return os.path.isfile(_filesystem_path(path))


def _read_text(path: Path) -> str:
    with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
        return handle.read()


def _write_text(path: Path, text: str) -> None:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _read_json(path: Path | None) -> dict[str, Any]:
    if not _is_file(path):
        return {}
    try:
        return json.loads(_read_text(path))
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key) if str(key) else "(blank)": _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if not _is_file(path):
        return []
    with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(str(row.get("payload_json", "") or "{}"))
    except json.JSONDecodeError:
        return {}


def _as_int(value: Any, *, default: int | None = None) -> int | None:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, *, default: float = math.nan) -> float:
    try:
        if value in (None, ""):
            return default
        result = float(str(value))
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _stats(values: list[float]) -> dict[str, Any]:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return {"count": 0}
    p95_index = min(len(finite) - 1, int(math.ceil(len(finite) * 0.95)) - 1)
    return {
        "count": len(finite),
        "min_ms": min(finite),
        "mean_ms": statistics.fmean(finite),
        "sd_ms": statistics.stdev(finite) if len(finite) > 1 else 0.0,
        "median_ms": statistics.median(finite),
        "p95_ms": finite[p95_index],
        "max_ms": max(finite),
        "abs_p95_ms": sorted(abs(value) for value in finite)[p95_index],
        "abs_max_ms": max(abs(value) for value in finite),
    }


def _resolve_path(value: Any, *, base: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _latest_validation_dir(root: Path) -> Path:
    reports_dir = root / "Experiment_context_folder_DO_NOT_DELETE" / "validation_reports"
    candidates = sorted(
        [path for path in reports_dir.glob("mock_rehearsal_*") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(f"No mock_rehearsal_* validation directory found under {reports_dir}")
    return candidates[0]


def _discover_context(
    *,
    rehearsal_root: Path | None,
    validation_dir: Path | None,
    session_dir: Path | None,
    events_csv: Path | None,
    lsl_markers_csv: Path | None,
    external_xdf: Path | None,
    output_dir: Path | None,
) -> dict[str, Any]:
    validation_dir = validation_dir.resolve() if validation_dir else None
    rehearsal_root = rehearsal_root.resolve() if rehearsal_root else None
    if validation_dir is None:
        if rehearsal_root is None:
            raise ValueError("--rehearsal-root or --validation-dir is required")
        validation_dir = _latest_validation_dir(rehearsal_root).resolve()
    if rehearsal_root is None:
        try:
            rehearsal_root = validation_dir.parents[2]
        except IndexError:
            rehearsal_root = validation_dir

    rehearsal_report_path = validation_dir / "desktop_full_mock_rehearsal_report.json"
    harness_report_path = validation_dir / "full_realtime_participant_emulation_report.json"
    focus_report_path = validation_dir / "focus_validation_report.json"
    cross_stream_report_path = validation_dir / "cross_stream_reconciliation" / "cross_stream_reconciliation_report.json"
    readiness_report_path = validation_dir / "protocol11_study5_readiness_audit" / "protocol11_study5_readiness_audit.json"
    response_marker_report_path = (
        validation_dir
        / "protocol11_study5_readiness_audit"
        / "response_marker_audio_evidence_validation"
        / "response_marker_loopback_report.json"
    )

    rehearsal_report = _read_json(rehearsal_report_path)
    harness_report = _read_json(harness_report_path)
    focus_report = _read_json(focus_report_path)
    readiness_report = _read_json(readiness_report_path)
    cross_stream_report = _read_json(cross_stream_report_path)

    manifest_base = validation_dir
    if session_dir is None:
        session_dir = _resolve_path(
            focus_report.get("session_dir")
            or rehearsal_report.get("session_dir")
            or (harness_report.get("evaluation") or {}).get("session_dir"),
            base=manifest_base,
        )
    else:
        session_dir = session_dir.resolve()

    if events_csv is None:
        events_csv = _resolve_path(
            focus_report.get("events_csv")
            or rehearsal_report.get("events_csv")
            or (cross_stream_report.get("events_csv") if isinstance(cross_stream_report, dict) else "")
            or (readiness_report.get("paths") or {}).get("events_csv"),
            base=manifest_base,
        )
    else:
        events_csv = events_csv.resolve()

    if not events_csv or not _is_file(events_csv):
        candidates = sorted(rehearsal_root.glob("Experiment_context_folder_DO_NOT_DELETE/verbose_events/*/events.csv"))
        if candidates:
            events_csv = candidates[-1]
    if lsl_markers_csv is None and events_csv:
        lsl_markers_csv = events_csv.with_name("lsl_markers.csv")
    elif lsl_markers_csv is not None:
        lsl_markers_csv = lsl_markers_csv.resolve()

    if external_xdf is None:
        external_xdf = _resolve_path(
            focus_report.get("external_labrecorder_xdf")
            or (focus_report.get("analysis_outputs") or {}).get("external_labrecorder_xdf")
            or (rehearsal_report.get("external_labrecorder") or {}).get("xdf_path")
            or (cross_stream_report.get("external_labrecorder") or {}).get("xdf_path"),
            base=manifest_base,
        )
    else:
        external_xdf = external_xdf.resolve()
    if (not external_xdf or not _is_file(external_xdf)) and events_csv:
        candidate = events_csv.with_name("session_external_labrecorder.xdf")
        if _is_file(candidate):
            external_xdf = candidate

    if output_dir is None:
        output_dir = validation_dir / "wired_lsl_xdf_tactile_drift_gate"
    else:
        output_dir = output_dir.resolve()

    return {
        "rehearsal_root": rehearsal_root,
        "validation_dir": validation_dir,
        "session_dir": session_dir,
        "events_csv": events_csv,
        "lsl_markers_csv": lsl_markers_csv,
        "external_xdf": external_xdf,
        "output_dir": output_dir,
        "reports": {
            "desktop_full_mock_rehearsal": rehearsal_report_path,
            "full_realtime_participant_emulation": harness_report_path,
            "focus_validation": focus_report_path,
            "cross_stream_reconciliation": cross_stream_report_path,
            "protocol11_study5_readiness": readiness_report_path,
            "response_marker_audio_evidence": response_marker_report_path,
        },
        "report_payloads": {
            "desktop_full_mock_rehearsal": rehearsal_report,
            "full_realtime_participant_emulation": harness_report,
            "focus_validation": focus_report,
            "cross_stream_reconciliation": cross_stream_report,
            "protocol11_study5_readiness": readiness_report,
            "response_marker_audio_evidence": _read_json(response_marker_report_path),
        },
    }


def _event_records(events_csv: Path, event_type: str) -> list[dict[str, Any]]:
    rows = []
    for row in _read_csv(events_csv):
        if row.get("event_type") != event_type:
            continue
        payload = _payload(row)
        sample_index = _as_int(payload.get("sample_index") or row.get("sample_index"), default=None)
        block_number = _as_int(payload.get("block_number") or payload.get("block_index") or row.get("block_index"), default=None)
        if sample_index is None or block_number is None:
            continue
        rows.append(
            {
                "event_id": str(row.get("event_id", "")).strip(),
                "event_type": event_type,
                "block_number": int(block_number),
                "sample_index": int(sample_index),
                "sample_rate": int(_as_int(payload.get("sample_rate") or payload.get("sample_rate_hz"), default=44100) or 44100),
                "trial_uid": str(payload.get("trial_uid") or payload.get("Trial_UID") or row.get("trial_uid") or ""),
                "marker_name": str(payload.get("marker_name") or ""),
                "timestamp_quality": str(payload.get("timestamp_quality") or row.get("timestamp_quality") or ""),
                "local_lsl_timestamp": _as_float(payload.get("lsl_timestamp"), default=math.nan),
            }
        )
    rows.sort(key=lambda item: (item["block_number"], item["sample_index"], int(item["event_id"]) if item["event_id"].isdigit() else 0))
    return rows


def _markers_by_event_id(lsl_markers_csv: Path | None) -> dict[str, dict[str, Any]]:
    markers = {}
    for row in _read_csv(lsl_markers_csv):
        event_id = str(row.get("event_id", "")).strip()
        if event_id:
            markers[event_id] = row
    return markers


def _xdf_summary(external_xdf: Path | None, lsl_markers_csv: Path | None, event_ids: set[str]) -> dict[str, Any]:
    if not _is_file(external_xdf):
        return {"checked": False, "passed": False, "error": "external XDF missing"}
    try:
        rich_rows, numeric_rows, _header = _load_xdf_streams(external_xdf)
    except Exception as exc:
        return {"checked": True, "passed": False, "error": str(exc), "xdf_path": str(external_xdf)}
    marker_rows = _read_csv(lsl_markers_csv)
    local_by_id = {str(row.get("event_id", "")).strip(): row for row in marker_rows if str(row.get("event_id", "")).strip()}
    rich_by_id = {str(row.get("event_id", "")).strip(): row for row in rich_rows if str(row.get("event_id", "")).strip()}
    numeric_count = len(numeric_rows)
    deltas_ms: list[float] = []
    missing_ids: list[str] = []
    for event_id in sorted(event_ids, key=lambda value: int(value) if value.isdigit() else value):
        rich = rich_by_id.get(event_id)
        local = local_by_id.get(event_id)
        if not rich or not local:
            missing_ids.append(event_id)
            continue
        rich_ts = _as_float(rich.get("sample_lsl_timestamp"))
        local_ts = _as_float(local.get("lsl_timestamp"))
        if math.isfinite(rich_ts) and math.isfinite(local_ts):
            deltas_ms.append((rich_ts - local_ts) * 1000.0)
    stats = _stats(deltas_ms)
    abs_max = float(stats.get("abs_max_ms") or math.inf)
    passed = not missing_ids and abs_max <= MAX_XDF_LOCAL_LSL_ABS_MS
    return {
        "checked": True,
        "passed": bool(passed),
        "xdf_path": str(external_xdf),
        "rich_xdf_sample_count": len(rich_rows),
        "numeric_xdf_sample_count": numeric_count,
        "requested_event_count": len(event_ids),
        "matched_event_count": len(deltas_ms),
        "missing_requested_event_ids": missing_ids,
        "xdf_minus_local_lsl_ms": stats,
        "criteria": {
            "xdf_local_lsl_abs_max_ms": MAX_XDF_LOCAL_LSL_ABS_MS,
        },
        "streams": {
            "PPSMarkersV2": len(rich_rows),
            "PPSTriggerCodes": numeric_count,
        },
    }


def _wav_block_number(path: Path) -> int | None:
    match = re.search(r"block[_\-\s]*(\d+)", path.name, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _sidecar_for_wav(path: Path) -> Path:
    return path.with_name(path.stem + ".output_evidence.json")


def _detect_segments(
    signal: np.ndarray,
    *,
    sample_rate: int,
    min_peak: float,
    threshold_fraction: float,
    min_gap_ms: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = np.asarray(signal, dtype=np.float64)
    abs_data = np.abs(data)
    if abs_data.size == 0:
        return [], {"peak": 0.0, "threshold": math.inf, "low_signal": True}
    peak = float(np.max(abs_data))
    median = float(np.median(abs_data))
    mad = float(np.median(np.abs(abs_data - median)))
    adaptive = median + 12.0 * max(mad, 1e-9)
    threshold = max(float(min_peak), float(peak) * float(threshold_fraction), adaptive)
    if peak < min_peak:
        return [], {"peak": peak, "threshold": threshold, "low_signal": True, "median": median, "mad": mad}
    above = np.flatnonzero(abs_data >= threshold)
    if above.size == 0:
        return [], {"peak": peak, "threshold": threshold, "low_signal": True, "median": median, "mad": mad}
    min_gap = max(1, int(round(float(min_gap_ms) / 1000.0 * sample_rate)))
    segments: list[dict[str, Any]] = []
    start = int(above[0])
    previous = int(above[0])
    for raw in above[1:]:
        sample = int(raw)
        if sample > previous + min_gap:
            chunk = abs_data[start : previous + 1]
            peak_offset = int(np.argmax(chunk)) if chunk.size else 0
            segments.append(
                {
                    "start_sample": start,
                    "end_sample": previous,
                    "peak_sample": start + peak_offset,
                    "peak_abs": float(abs_data[start + peak_offset]) if chunk.size else 0.0,
                }
            )
            start = sample
        previous = sample
    chunk = abs_data[start : previous + 1]
    peak_offset = int(np.argmax(chunk)) if chunk.size else 0
    segments.append(
        {
            "start_sample": start,
            "end_sample": previous,
            "peak_sample": start + peak_offset,
            "peak_abs": float(abs_data[start + peak_offset]) if chunk.size else 0.0,
        }
    )
    return segments, {"peak": peak, "threshold": threshold, "low_signal": False, "median": median, "mad": mad}


def _estimate_offset(
    events: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    *,
    sample_rate: int,
    search_pre_ms: float,
    search_post_ms: float,
    detection_key: str,
) -> float | None:
    if not events or not segments:
        return None
    pre = int(round(search_pre_ms / 1000.0 * sample_rate))
    post = int(round(search_post_ms / 1000.0 * sample_rate))
    bin_width = max(1, int(round(0.001 * sample_rate)))
    bins: dict[int, list[int]] = {}
    for event in events:
        expected = int(event["sample_index"])
        for segment in segments:
            observed = int(segment[detection_key])
            if expected - pre <= observed <= expected + post:
                offset = observed - expected
                bins.setdefault(int(round(offset / bin_width)), []).append(offset)
    if not bins:
        return None
    _bin, offsets = max(bins.items(), key=lambda item: (len(item[1]), -abs(statistics.median(item[1]))))
    if len(offsets) < max(2, int(math.ceil(len(events) * 0.25))):
        return None
    return float(statistics.median(offsets))


def _pair_events(
    events: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    *,
    sample_rate: int,
    search_pre_ms: float,
    search_post_ms: float,
    detection_key: str,
) -> tuple[list[dict[str, Any]], float | None]:
    pre = int(round(search_pre_ms / 1000.0 * sample_rate))
    post = int(round(search_post_ms / 1000.0 * sample_rate))
    offset = _estimate_offset(
        events,
        segments,
        sample_rate=sample_rate,
        search_pre_ms=search_pre_ms,
        search_post_ms=search_post_ms,
        detection_key=detection_key,
    )
    used: set[int] = set()
    pairs: list[dict[str, Any]] = []
    raw_offsets: list[int] = []
    for event in events:
        expected = int(event["sample_index"])
        candidates: list[tuple[int, dict[str, Any]]] = []
        for index, segment in enumerate(segments):
            if index in used:
                continue
            observed = int(segment[detection_key])
            if expected - pre <= observed <= expected + post:
                candidates.append((index, segment))
        selected_index: int | None = None
        selected: dict[str, Any] | None = None
        if candidates:
            target = expected + (offset if offset is not None else 0.0)
            selected_index, selected = min(candidates, key=lambda item: abs(int(item[1][detection_key]) - target))
            used.add(selected_index)
            raw_offsets.append(int(selected[detection_key]) - expected)
        median_offset = float(statistics.median(raw_offsets)) if raw_offsets else offset
        residual_ms = ""
        raw_offset_ms = ""
        observed_value = ""
        if selected is not None:
            observed_value = int(selected[detection_key])
            raw_offset_samples = int(selected[detection_key]) - expected
            raw_offset_ms = raw_offset_samples / float(sample_rate) * 1000.0
            if median_offset is not None:
                residual_ms = (raw_offset_samples - median_offset) / float(sample_rate) * 1000.0
        pairs.append(
            {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "block_number": event["block_number"],
                "trial_uid": event["trial_uid"],
                "expected_sample_index": expected,
                "detected": selected is not None,
                "detected_sample_index": observed_value,
                "raw_offset_ms": raw_offset_ms,
                "residual_ms": residual_ms,
                "timestamp_quality": event["timestamp_quality"],
            }
        )
    final_offset = float(statistics.median(raw_offsets)) if raw_offsets else offset
    for pair in pairs:
        if not pair.get("detected") or final_offset is None:
            continue
        raw_offset_samples = int(pair["detected_sample_index"]) - int(pair["expected_sample_index"])
        pair["residual_ms"] = (raw_offset_samples - final_offset) / float(sample_rate) * 1000.0
    return pairs, final_offset


def _block_wav_path(session_dir: Path, block_number: int) -> Path:
    direct = session_dir / f"block_{block_number:02d}_wired_loopback_input4.wav"
    if _is_file(direct):
        return direct
    candidates = sorted(session_dir.glob(f"*{block_number:02d}*wired_loopback_input4.wav"))
    return candidates[0] if candidates else direct


def _audit_tactile_wired_proxy(
    *,
    session_dir: Path,
    tactile_events: list[dict[str, Any]],
    input_channel_1based: int | None,
    min_peak: float,
    threshold_fraction: float,
    min_gap_ms: float,
    search_pre_ms: float,
    search_post_ms: float,
) -> dict[str, Any]:
    by_block: dict[int, list[dict[str, Any]]] = {}
    for event in tactile_events:
        by_block.setdefault(int(event["block_number"]), []).append(event)

    blocks: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    all_peak_residual_abs: list[float] = []
    all_onset_residual_abs: list[float] = []
    all_detected = 0
    all_expected = 0
    failed_blocks: list[dict[str, Any]] = []

    for block_number in sorted(by_block):
        events = by_block[block_number]
        wav_path = _block_wav_path(session_dir, block_number)
        sidecar_path = _sidecar_for_wav(wav_path)
        sidecar = _read_json(sidecar_path)
        channel = input_channel_1based or _as_int(sidecar.get("input_channel_1based"), default=4) or 4
        block_report: dict[str, Any] = {
            "block_number": block_number,
            "wav_path": str(wav_path),
            "sidecar_path": str(sidecar_path),
            "expected_tactile_count": len(events),
            "input_channel_1based": channel,
            "sidecar": {
                "started": sidecar.get("started"),
                "dropped_buffer_count": sidecar.get("dropped_buffer_count"),
                "interrupted": sidecar.get("interrupted"),
                "peak_by_channel": sidecar.get("peak_by_channel"),
                "rms_by_channel": sidecar.get("rms_by_channel"),
            },
        }
        all_expected += len(events)
        if not _is_file(wav_path):
            block_report.update({"passed": False, "error": "wired loopback WAV missing"})
            failed_blocks.append({"block_number": block_number, "reason": "missing_wav"})
            blocks.append(block_report)
            continue
        try:
            samples, sample_rate = sf.read(_filesystem_path(wav_path), dtype="float32", always_2d=True)
        except Exception as exc:
            block_report.update({"passed": False, "error": str(exc)})
            failed_blocks.append({"block_number": block_number, "reason": "wav_read_failed", "error": str(exc)})
            blocks.append(block_report)
            continue
        if channel < 1 or channel > samples.shape[1]:
            block_report.update({"passed": False, "error": f"input channel {channel} outside WAV channel count {samples.shape[1]}"})
            failed_blocks.append({"block_number": block_number, "reason": "bad_channel"})
            blocks.append(block_report)
            continue
        signal = samples[:, channel - 1]
        segments, threshold_profile = _detect_segments(
            signal,
            sample_rate=int(sample_rate),
            min_peak=min_peak,
            threshold_fraction=threshold_fraction,
            min_gap_ms=min_gap_ms,
        )
        peak_pairs, peak_offset = _pair_events(
            events,
            segments,
            sample_rate=int(sample_rate),
            search_pre_ms=search_pre_ms,
            search_post_ms=search_post_ms,
            detection_key="peak_sample",
        )
        onset_pairs, onset_offset = _pair_events(
            events,
            segments,
            sample_rate=int(sample_rate),
            search_pre_ms=search_pre_ms,
            search_post_ms=search_post_ms,
            detection_key="start_sample",
        )
        detected_peak = [pair for pair in peak_pairs if pair.get("detected")]
        peak_residuals = [abs(_as_float(pair.get("residual_ms"))) for pair in detected_peak]
        onset_residuals = [abs(_as_float(pair.get("residual_ms"))) for pair in onset_pairs if pair.get("detected")]
        raw_offsets = [_as_float(pair.get("raw_offset_ms")) for pair in peak_pairs if pair.get("detected")]
        adjacent_steps = [
            raw_offsets[index] - raw_offsets[index - 1]
            for index in range(1, len(raw_offsets))
            if math.isfinite(raw_offsets[index]) and math.isfinite(raw_offsets[index - 1])
        ]
        peak_stats = _stats(peak_residuals)
        onset_stats = _stats(onset_residuals)
        step_stats = _stats(adjacent_steps)
        detected_count = len(detected_peak)
        all_detected += detected_count
        all_peak_residual_abs.extend(peak_residuals)
        all_onset_residual_abs.extend(onset_residuals)
        block_passed = (
            detected_count == len(events)
            and float(peak_stats.get("abs_p95_ms") or math.inf) <= MAX_TACTILE_RESIDUAL_P95_MS
            and float(peak_stats.get("abs_max_ms") or math.inf) <= MAX_TACTILE_RESIDUAL_ABS_MS
            and float(step_stats.get("abs_max_ms") or 0.0) <= MAX_TACTILE_ADJACENT_STEP_MS
            and not bool(sidecar.get("interrupted"))
            and int(sidecar.get("dropped_buffer_count") or 0) == 0
        )
        if not block_passed:
            failed_blocks.append(
                {
                    "block_number": block_number,
                    "detected": detected_count,
                    "expected": len(events),
                    "peak_abs_p95_ms": peak_stats.get("abs_p95_ms"),
                    "peak_abs_max_ms": peak_stats.get("abs_max_ms"),
                    "adjacent_step_abs_max_ms": step_stats.get("abs_max_ms"),
                }
            )
        block_report.update(
            {
                "passed": bool(block_passed),
                "sample_rate": int(sample_rate),
                "wav_frames": int(samples.shape[0]),
                "detected_segment_count": len(segments),
                "detected_tactile_count": detected_count,
                "threshold_profile": threshold_profile,
                "peak_offset_samples": peak_offset,
                "onset_offset_samples": onset_offset,
                "peak_residual_abs_ms": peak_stats,
                "onset_residual_abs_ms": onset_stats,
                "peak_adjacent_offset_step_ms": step_stats,
            }
        )
        for pair in peak_pairs:
            pair_rows.append({**pair, "detection_metric": "peak", "wav_path": str(wav_path)})
        for pair in onset_pairs:
            pair_rows.append({**pair, "detection_metric": "onset", "wav_path": str(wav_path)})
        blocks.append(block_report)

    global_peak_stats = _stats(all_peak_residual_abs)
    global_onset_stats = _stats(all_onset_residual_abs)
    passed = (
        all_expected > 0
        and all_detected == all_expected
        and not failed_blocks
        and float(global_peak_stats.get("abs_p95_ms") or math.inf) <= MAX_TACTILE_RESIDUAL_P95_MS
        and float(global_peak_stats.get("abs_max_ms") or math.inf) <= MAX_TACTILE_RESIDUAL_ABS_MS
    )
    return {
        "passed": bool(passed),
        "session_dir": str(session_dir),
        "expected_tactile_count": all_expected,
        "detected_tactile_count": all_detected,
        "missing_tactile_count": max(0, all_expected - all_detected),
        "global_peak_residual_abs_ms": global_peak_stats,
        "global_onset_residual_abs_ms": global_onset_stats,
        "failed_blocks": failed_blocks,
        "blocks": blocks,
        "pairs": pair_rows,
        "criteria": {
            "per_block_peak_residual_abs_p95_ms": MAX_TACTILE_RESIDUAL_P95_MS,
            "per_block_peak_residual_abs_max_ms": MAX_TACTILE_RESIDUAL_ABS_MS,
            "per_block_adjacent_peak_step_abs_max_ms": MAX_TACTILE_ADJACENT_STEP_MS,
            "all_tactile_events_detected": True,
        },
    }


def _audit_response_clicks(focus_report: dict[str, Any]) -> dict[str, Any]:
    actions = [item for item in focus_report.get("validation_mouse_clicks") or [] if isinstance(item, dict)]
    planned_clicks = [item for item in actions if item.get("action") in {"standard_click", "topup_click"}]
    external = [item for item in actions if item.get("label") == "external_mouse_click_process"]
    bad = [
        item
        for item in external
        if item.get("backend") != "pynput"
        or not bool(item.get("raw_input_sent"))
        or bool(item.get("window_message_sent"))
        or bool(item.get("window_message_only"))
        or not bool(item.get("ok"))
    ]
    return {
        "checked": bool(actions),
        "passed": bool(actions) and len(external) >= len(planned_clicks) and not bad,
        "planned_response_click_count": len(planned_clicks),
        "external_mouse_click_process_count": len(external),
        "bad_delivery_count": len(bad),
        "backend_counts": dict(Counter(str(item.get("backend") or "") for item in actions)),
        "bad_delivery_samples": bad[:10],
        "criteria": {
            "backend": "pynput",
            "raw_input_sent": True,
            "window_message_sent": False,
        },
    }


def _audit_response_marker_audio(report: dict[str, Any]) -> dict[str, Any]:
    expected = _as_int(report.get("expected_marker_count"), default=0) or 0
    detected = _as_int(report.get("detected_marker_count"), default=0) or 0
    return {
        "checked": bool(report),
        "passed": bool(report.get("passed")) and expected > 0 and detected == expected,
        "expected_marker_count": expected,
        "detected_marker_count": detected,
        "detection_rate": report.get("detection_rate"),
        "offset_ms": report.get("offset_ms"),
        "abs_residual_ms": report.get("abs_residual_ms"),
        "source_report_passed": report.get("passed"),
        "criteria": {
            "all_response_markers_detected_in_runtime_audio_evidence": True,
            "hardwired_response_marker_peak_metric_blocks_readiness": False,
        },
    }


def _audit_wrapper_reports(payloads: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rehearsal = payloads.get("desktop_full_mock_rehearsal") or {}
    harness = payloads.get("full_realtime_participant_emulation") or {}
    readiness = payloads.get("protocol11_study5_readiness") or {}
    cross = payloads.get("cross_stream_reconciliation") or {}
    external = rehearsal.get("external_labrecorder") if isinstance(rehearsal.get("external_labrecorder"), dict) else {}
    criteria = {
        "desktop_full_mock_rehearsal_passed": bool(rehearsal.get("passed")),
        "full_realtime_participant_emulation_passed": bool(harness.get("passed")),
        "final_condition_ready": bool(harness.get("final_condition_ready")),
        "runner_mode_packaged": str(harness.get("runner_mode") or rehearsal.get("runner_mode")) == "packaged",
        "audio_mode_hardware": str(harness.get("audio_mode") or rehearsal.get("audio_mode")) == "hardware",
        "validation_lane_full_stack": str(harness.get("validation_lane") or rehearsal.get("validation_lane")) == "full-stack",
        "protocol11_strict_readiness_passed": bool(readiness.get("passed")) and bool(readiness.get("full_study5_realtime_ready")),
        "cross_stream_reconciliation_passed": bool(cross.get("passed")),
        "external_labrecorder_reconciliation_passed": bool((external or {}).get("passed", False)),
    }
    return {
        "passed": all(criteria.values()),
        "criteria": criteria,
        "event_counts": harness.get("evaluation", {}).get("event_counts") if isinstance(harness.get("evaluation"), dict) else {},
        "session_dir": (harness.get("evaluation") or {}).get("session_dir") if isinstance(harness.get("evaluation"), dict) else "",
    }


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    criteria = report.get("criteria") if isinstance(report.get("criteria"), dict) else {}
    tactile = report.get("tactile_wired_proxy") if isinstance(report.get("tactile_wired_proxy"), dict) else {}
    xdf = report.get("external_xdf") if isinstance(report.get("external_xdf"), dict) else {}
    response = report.get("response_marker_audio_evidence") if isinstance(report.get("response_marker_audio_evidence"), dict) else {}
    lines = [
        "# Full Session Wired LSL/XDF Tactile Drift Audit",
        "",
        f"- Overall pass: `{report.get('passed')}`",
        f"- Rehearsal root: `{report.get('rehearsal_root', '')}`",
        f"- Validation dir: `{report.get('validation_dir', '')}`",
        f"- Session dir: `{report.get('session_dir', '')}`",
        f"- Tactile pulses detected: `{tactile.get('detected_tactile_count')}/{tactile.get('expected_tactile_count')}`",
        f"- XDF/local LSL abs max: `{(xdf.get('xdf_minus_local_lsl_ms') or {}).get('abs_max_ms')}` ms",
        f"- Tactile peak residual abs p95: `{(tactile.get('global_peak_residual_abs_ms') or {}).get('abs_p95_ms')}` ms",
        f"- Tactile peak residual abs max: `{(tactile.get('global_peak_residual_abs_ms') or {}).get('abs_max_ms')}` ms",
        f"- Response markers in runtime audio evidence: `{response.get('detected_marker_count')}/{response.get('expected_marker_count')}`",
        "",
        "## Criteria",
    ]
    for key, value in criteria.items():
        lines.append(f"- {key}: `{value}`")
    failed_blocks = tactile.get("failed_blocks") or []
    if failed_blocks:
        lines.extend(["", "## Failed Tactile Blocks"])
        for item in failed_blocks:
            lines.append(f"- Block {item.get('block_number')}: `{json.dumps(item, sort_keys=True)}`")
    lines.extend(
        [
            "",
            "## Scope",
            "",
            "This gate accepts the Output-4-to-Input-4 tactile proxy as the hardwired timing reference. "
            "Response-marker pulse recovery is decided from runtime digital audio evidence; hardwired response-marker peak variation is informational only. "
            "This does not measure Woojer mechanical vibration onset or human behavioral validity.",
        ]
    )
    _write_text(path, "\n".join(lines) + "\n")


def audit_gate(
    *,
    rehearsal_root: Path | None,
    validation_dir: Path | None,
    session_dir: Path | None,
    events_csv: Path | None,
    lsl_markers_csv: Path | None,
    external_xdf: Path | None,
    output_dir: Path | None,
    input_channel_1based: int | None,
    min_peak: float,
    threshold_fraction: float,
    min_gap_ms: float,
    search_pre_ms: float,
    search_post_ms: float,
) -> dict[str, Any]:
    context = _discover_context(
        rehearsal_root=rehearsal_root,
        validation_dir=validation_dir,
        session_dir=session_dir,
        events_csv=events_csv,
        lsl_markers_csv=lsl_markers_csv,
        external_xdf=external_xdf,
        output_dir=output_dir,
    )
    output_dir = Path(context["output_dir"])
    _mkdir(output_dir)
    events_csv = Path(context["events_csv"])
    lsl_markers_csv = Path(context["lsl_markers_csv"])
    external_xdf = Path(context["external_xdf"])
    session_dir = Path(context["session_dir"])

    tactile_events = _event_records(events_csv, TACTILE_EVENT_TYPE)
    response_events = _event_records(events_csv, RESPONSE_MARKER_EVENT_TYPE)
    local_markers = _markers_by_event_id(lsl_markers_csv)
    for event in tactile_events:
        marker = local_markers.get(event["event_id"])
        if marker:
            event["local_lsl_timestamp"] = _as_float(marker.get("lsl_timestamp"), default=event.get("local_lsl_timestamp", math.nan))

    xdf = _xdf_summary(external_xdf, lsl_markers_csv, {event["event_id"] for event in tactile_events})
    tactile = _audit_tactile_wired_proxy(
        session_dir=session_dir,
        tactile_events=tactile_events,
        input_channel_1based=input_channel_1based,
        min_peak=min_peak,
        threshold_fraction=threshold_fraction,
        min_gap_ms=min_gap_ms,
        search_pre_ms=search_pre_ms,
        search_post_ms=search_post_ms,
    )
    payloads = context["report_payloads"]
    wrappers = _audit_wrapper_reports(payloads)
    clicks = _audit_response_clicks(payloads.get("focus_validation") or {})
    response_audio = _audit_response_marker_audio(payloads.get("response_marker_audio_evidence") or {})

    criteria = {
        "desktop_and_protocol11_reports_passed": bool(wrappers.get("passed")),
        "external_xdf_tactile_events_match_local_lsl": bool(xdf.get("passed")),
        "all_tactile_proxy_pulses_detected": tactile.get("detected_tactile_count") == tactile.get("expected_tactile_count") and int(tactile.get("expected_tactile_count") or 0) > 0,
        "tactile_proxy_peak_residual_p95_lte_1ms": float((tactile.get("global_peak_residual_abs_ms") or {}).get("abs_p95_ms") or math.inf) <= MAX_TACTILE_RESIDUAL_P95_MS,
        "tactile_proxy_peak_residual_max_lte_2ms": float((tactile.get("global_peak_residual_abs_ms") or {}).get("abs_max_ms") or math.inf) <= MAX_TACTILE_RESIDUAL_ABS_MS,
        "no_per_block_tactile_proxy_step_gt_2ms": not bool(tactile.get("failed_blocks")),
        "response_clicks_used_pynput_raw_input_without_window_messages": bool(clicks.get("passed")),
        "response_markers_recovered_from_runtime_audio_evidence": bool(response_audio.get("passed")),
    }
    passed = all(criteria.values())
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "passed": bool(passed),
        "rehearsal_root": str(context["rehearsal_root"]),
        "validation_dir": str(context["validation_dir"]),
        "session_dir": str(session_dir),
        "events_csv": str(events_csv),
        "lsl_markers_csv": str(lsl_markers_csv),
        "external_xdf_path": str(external_xdf),
        "criteria": criteria,
        "wrapper_reports": wrappers,
        "external_xdf": xdf,
        "tactile_wired_proxy": {key: value for key, value in tactile.items() if key != "pairs"},
        "response_click_delivery": clicks,
        "response_marker_audio_evidence": response_audio,
        "counts": {
            "tactile_events": len(tactile_events),
            "response_marker_events": len(response_events),
        },
        "reports": {key: str(value) for key, value in context["reports"].items()},
        "limitations": [
            "Output 4 patched to Input 4 is an analog duplicate tactile proxy, not Woojer mechanical vibration onset.",
            "Hardwired response-marker peak variation is informational; runtime digital audio evidence is the response-marker recovery gate.",
            "Human participant comprehension, comfort, and behavioral PPS interpretability remain Protocol 10 concerns.",
        ],
    }
    pair_fields = [
        "detection_metric",
        "wav_path",
        "event_id",
        "event_type",
        "block_number",
        "trial_uid",
        "expected_sample_index",
        "detected",
        "detected_sample_index",
        "raw_offset_ms",
        "residual_ms",
        "timestamp_quality",
    ]
    _write_csv(output_dir / "tactile_proxy_pulse_offsets.csv", tactile.get("pairs", []), pair_fields)
    _write_json(output_dir / "full_session_wired_lsl_xdf_tactile_drift_audit.json", report)
    _write_markdown(output_dir / "full_session_wired_lsl_xdf_tactile_drift_audit.md", report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit full-session Study 5 wired tactile proxy drift against LSL/XDF.")
    parser.add_argument("--rehearsal-root", type=Path, help="Desktop rehearsal root containing Experiment_context_folder_DO_NOT_DELETE.")
    parser.add_argument("--validation-dir", type=Path, help="Specific mock_rehearsal_* validation report directory.")
    parser.add_argument("--session-dir", type=Path)
    parser.add_argument("--events-csv", type=Path)
    parser.add_argument("--lsl-markers-csv", type=Path)
    parser.add_argument("--external-xdf", type=Path)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--input-channel", type=int, default=None, help="1-based input channel to audit; defaults to sidecar input_channel_1based.")
    parser.add_argument("--min-peak", type=float, default=0.05)
    parser.add_argument("--threshold-fraction", type=float, default=0.20)
    parser.add_argument("--min-gap-ms", type=float, default=50.0)
    parser.add_argument("--search-pre-ms", type=float, default=50.0)
    parser.add_argument("--search-post-ms", type=float, default=800.0)
    args = parser.parse_args(argv)
    report = audit_gate(
        rehearsal_root=args.rehearsal_root,
        validation_dir=args.validation_dir,
        session_dir=args.session_dir,
        events_csv=args.events_csv,
        lsl_markers_csv=args.lsl_markers_csv,
        external_xdf=args.external_xdf,
        output_dir=args.output_dir,
        input_channel_1based=args.input_channel,
        min_peak=args.min_peak,
        threshold_fraction=args.threshold_fraction,
        min_gap_ms=args.min_gap_ms,
        search_pre_ms=args.search_pre_ms,
        search_post_ms=args.search_post_ms,
    )
    output_dir = Path(args.output_dir) if args.output_dir else Path(report["validation_dir"]) / "wired_lsl_xdf_tactile_drift_gate"
    print(f"Wrote full-session wired tactile drift audit: {output_dir / 'full_session_wired_lsl_xdf_tactile_drift_audit.json'}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
