"""Run a full Study 5 mock rehearsal into a fresh Desktop output folder.

This validation orchestrates the normal packaged Focus Mode runner with a
scripted participant, hardware audio, wired loopback, local WAV/CSV/XDF outputs,
and optional continuous external LabRecorder XDF capture.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_full_realtime_participant_emulation as emulator  # noqa: E402
from run_labrecorder_lsl_xdf_stress import (  # noqa: E402
    _find_labrecorder_cli,
    _load_xdf_streams,
    _stats,
    _write_csv,
    compare_xdf_to_local,
)
from peripersonal_space_toolkit.focus_app import initiate_data_collection_environment  # noqa: E402
from peripersonal_space_toolkit.output_layout import output_validation_reports_dir  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
    WIRED_LOOPBACK_OFF,
    normalize_wired_loopback_mode,
)
from peripersonal_space_toolkit.timing_events import LSL_MARKER_CHANNELS  # noqa: E402


SCHEMA = "pps-desktop-full-mock-rehearsal.v1"


def _default_desktop_output_parent() -> Path:
    home = Path(os.environ.get("USERPROFILE") or Path.home()).expanduser()
    desktop = home / "Desktop"
    return desktop if desktop.exists() else home


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return value


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _resolve_path(value: Any, *, base: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return Path()
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return (base / path).resolve()


def _audio_route_preflight() -> dict[str, Any]:
    os.environ.setdefault("SD_ENABLE_ASIO", "1")
    try:
        import sounddevice as sd  # type: ignore
    except Exception as exc:
        return {"checked": True, "komplete_asio_4x4_ready": False, "error": str(exc), "candidates": []}
    try:
        hostapis = sd.query_hostapis()
        devices = sd.query_devices()
    except Exception as exc:
        return {"checked": True, "komplete_asio_4x4_ready": False, "error": str(exc), "candidates": []}
    candidates: list[dict[str, Any]] = []
    for index, device in enumerate(devices):
        hostapi_index = int(device.get("hostapi", -1))
        hostapi_name = str(hostapis[hostapi_index].get("name", "")) if 0 <= hostapi_index < len(hostapis) else ""
        name = str(device.get("name", ""))
        candidate = {
            "index": index,
            "name": name,
            "hostapi": hostapi_name,
            "max_input_channels": int(device.get("max_input_channels", 0)),
            "max_output_channels": int(device.get("max_output_channels", 0)),
        }
        if "komplete" in name.lower() or "komplete" in hostapi_name.lower():
            candidates.append(candidate)
    ready = any(
        "asio" in row["hostapi"].lower()
        and row["max_input_channels"] >= 4
        and row["max_output_channels"] >= 4
        for row in candidates
    )
    return {"checked": True, "komplete_asio_4x4_ready": bool(ready), "error": "", "candidates": candidates}


def build_emulator_argv(args: argparse.Namespace, *, output_dir: Path) -> list[str]:
    argv = [
        "--output-dir",
        str(output_dir),
        "--runner",
        str(args.runner),
        "--runner-mode",
        str(args.runner_mode),
        "--profile",
        str(args.profile),
        "--participant-id",
        str(args.participant_id),
        "--timeout-s",
        str(float(args.timeout_s)),
        "--miss-rate",
        str(float(args.miss_rate)),
        "--min-misses",
        str(int(args.min_misses)),
        "--seed",
        str(int(args.seed)),
        "--mouse-backend",
        str(args.mouse_backend),
        "--validation-lane",
        str(args.validation_lane),
        "--audio-mode",
        str(args.audio_mode),
        "--validation-audio-chunk-frames",
        str(int(args.validation_audio_chunk_frames)),
        "--wired-loopback",
        str(args.wired_loopback),
    ]
    if args.audio_device_index is not None:
        argv.extend(["--audio-device-index", str(int(args.audio_device_index))])
    if bool(args.external_labrecorder):
        argv.append("--external-labrecorder")
        if args.labrecorder_cli is not None:
            argv.extend(["--labrecorder-cli", str(args.labrecorder_cli)])
        argv.extend(
            [
                "--labrecorder-stream-timeout-s",
                str(float(args.labrecorder_stream_timeout_s)),
                "--labrecorder-startup-s",
                str(float(args.labrecorder_startup_s)),
                "--labrecorder-stop-timeout-s",
                str(float(args.labrecorder_stop_timeout_s)),
            ]
        )
    if bool(args.strict_study5_readiness):
        argv.append("--strict-study5-readiness")
    return argv


def _create_rehearsal_environment(args: argparse.Namespace) -> dict[str, Any]:
    capture_options = SessionCaptureOptions(
        wired_loopback_mode=normalize_wired_loopback_mode(args.wired_loopback),
        start_external_labrecorder=bool(args.external_labrecorder),
        external_labrecorder_cli=str(args.labrecorder_cli or ""),
        external_labrecorder_stream_timeout_s=float(args.labrecorder_stream_timeout_s),
        external_labrecorder_startup_s=float(args.labrecorder_startup_s),
        external_labrecorder_stop_timeout_s=float(args.labrecorder_stop_timeout_s),
    )
    return initiate_data_collection_environment(
        parent_folder=Path(args.desktop_output_parent).expanduser(),
        profile_id=str(args.profile),
        session_name=str(args.session_name),
        participant_id=str(args.participant_id),
        capture_options=capture_options,
    )


def _session_output_paths(validation_dir: Path) -> dict[str, Path]:
    focus_report = _read_json(validation_dir / "focus_validation_report.json")
    session_manifest = _resolve_path(focus_report.get("session_manifest"), base=validation_dir)
    manifest = _read_json(session_manifest)
    outputs = manifest.get("outputs") if isinstance(manifest.get("outputs"), dict) else {}
    manifest_base = session_manifest.parent if session_manifest.parent != Path() else validation_dir
    session_dir = _resolve_path(focus_report.get("session_dir"), base=validation_dir)
    events_csv = _resolve_path(focus_report.get("events_csv") or outputs.get("verbose_events_csv"), base=manifest_base)
    lsl_markers_csv = _resolve_path(outputs.get("lsl_markers_csv"), base=manifest_base)
    return {
        "session_dir": session_dir,
        "session_manifest": session_manifest,
        "events_csv": events_csv,
        "lsl_markers_csv": lsl_markers_csv,
    }


def reconcile_external_labrecorder_xdf(
    *,
    validation_dir: Path,
    xdf_path: Path,
    labrecorder_cli: Path | None,
    labrecorder_command: list[str],
    labrecorder_returncode: int | None,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    output_dir = validation_dir / "external_labrecorder_reconciliation"
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = _session_output_paths(validation_dir)
    if not xdf_path.is_file() or xdf_path.stat().st_size == 0:
        report = {
            "schema": "pps-desktop-rehearsal-external-labrecorder.v1",
            "passed": False,
            "xdf_path": str(xdf_path),
            "labrecorder_cli": str(labrecorder_cli or ""),
            "labrecorder_command": labrecorder_command,
            "labrecorder_returncode": labrecorder_returncode,
            "stdout": str(stdout_path),
            "stderr": str(stderr_path),
            "error": "External LabRecorder did not produce a non-empty XDF file.",
        }
        _write_json(output_dir / "external_labrecorder_reconciliation_report.json", report)
        _write_markdown_report(output_dir / "external_labrecorder_reconciliation_report.md", report)
        return report

    rich_rows, numeric_rows, _header = _load_xdf_streams(xdf_path)
    _write_csv(output_dir / "external_labrecorder_rich_xdf_samples.csv", rich_rows, [*LSL_MARKER_CHANNELS, "sample_lsl_timestamp"])
    _write_csv(output_dir / "external_labrecorder_numeric_xdf_samples.csv", numeric_rows, ["event_code", "sample_lsl_timestamp"])
    marker_rows = _read_csv(paths["lsl_markers_csv"])
    rich_event_ids = [
        int(str(row.get("event_id") or ""))
        for row in rich_rows
        if str(row.get("event_id") or "").isdigit()
    ]
    capture_min_event_id = min(rich_event_ids) if rich_event_ids else None
    capture_max_event_id = max(rich_event_ids) if rich_event_ids else None
    if capture_min_event_id is not None and capture_max_event_id is not None:
        marker_rows_in_capture = [
            row
            for row in marker_rows
            if str(row.get("event_id") or "").isdigit()
            and capture_min_event_id <= int(str(row.get("event_id") or "")) <= capture_max_event_id
        ]
        ignored_marker_event_ids = [
            str(row.get("event_id") or "")
            for row in marker_rows
            if str(row.get("pushed_to_lsl", "")).lower() in {"true", "1", "yes"}
            and str(row.get("event_id") or "").isdigit()
            and not (capture_min_event_id <= int(str(row.get("event_id") or "")) <= capture_max_event_id)
        ]
    else:
        marker_rows_in_capture = marker_rows
        ignored_marker_event_ids = []
    comparison = compare_xdf_to_local(rich_rows=rich_rows, numeric_rows=numeric_rows, marker_rows=marker_rows_in_capture)
    event_type_counts = comparison.get("event_type_counts_xdf") or {}
    block_indices = sorted(
        {
            str(row.get("block_index", "")).strip()
            for row in rich_rows
            if str(row.get("block_index", "")).strip()
        }
    )
    timestamp_deltas = [
        (float(rich["sample_lsl_timestamp"]) - float(marker["lsl_timestamp"])) * 1000.0
        for rich, marker in zip(rich_rows, marker_rows_in_capture)
        if str(rich.get("sample_lsl_timestamp", "")).strip() and str(marker.get("lsl_timestamp", "")).strip()
    ]
    report = {
        "schema": "pps-desktop-rehearsal-external-labrecorder.v1",
        "passed": bool(comparison.get("passed")),
        "xdf_path": str(xdf_path),
        "labrecorder_cli": str(labrecorder_cli or ""),
        "labrecorder_command": labrecorder_command,
        "labrecorder_returncode": labrecorder_returncode,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "session_dir": str(paths["session_dir"]),
        "session_manifest": str(paths["session_manifest"]),
        "events_csv": str(paths["events_csv"]),
        "lsl_markers_csv": str(paths["lsl_markers_csv"]),
        "rich_xdf_samples_csv": str(output_dir / "external_labrecorder_rich_xdf_samples.csv"),
        "numeric_xdf_samples_csv": str(output_dir / "external_labrecorder_numeric_xdf_samples.csv"),
        "block_indices_observed": block_indices,
        "event_type_counts_xdf": event_type_counts,
        "timestamp_delta_xdf_minus_local_marker_ms": _stats(timestamp_deltas),
        "capture_event_id_range": [capture_min_event_id, capture_max_event_id],
        "ignored_out_of_capture_event_ids": ignored_marker_event_ids,
        "comparison": comparison,
        "limitations": [
            "This is one continuous external XDF for the whole rehearsal; block identity is preserved by LSL marker fields.",
            "This validates external LSL/XDF capture and metadata reconciliation, not tactile perception or Woojer mechanical onset.",
        ],
    }
    _write_json(output_dir / "external_labrecorder_reconciliation_report.json", report)
    _write_markdown_report(output_dir / "external_labrecorder_reconciliation_report.md", report)
    return report


def _criterion_passed(readiness: dict[str, Any], section: str, name: str, *, default: bool | None = None) -> bool | None:
    for item in readiness.get("criteria") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("section") or "") == section and str(item.get("name") or "") == name:
            return bool(item.get("passed"))
    return default


def _section_passed(readiness: dict[str, Any], section: str, *, default: bool | None = None) -> bool | None:
    sections = readiness.get("sections") if isinstance(readiness.get("sections"), dict) else {}
    item = sections.get(section) if isinstance(sections.get(section), dict) else {}
    if item:
        return bool(item.get("passed"))
    return default


def _payload(row: dict[str, str]) -> dict[str, Any]:
    try:
        payload = row.get("payload_json") or "{}"
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _wired_loopback_event_summary(events_csv: Path) -> dict[str, Any]:
    rows = _read_csv(events_csv)
    starts: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("event_type") or "") != "wired_loopback_start":
            continue
        payload = _payload(row)
        item = {
            "block_number": payload.get("block_number"),
            "started": bool(payload.get("started")),
            "path": str(payload.get("path") or ""),
            "message": str(payload.get("message") or ""),
        }
        starts.append(item)
        if not item["started"]:
            failures.append(item)
    return {
        "start_count": len(starts),
        "started_count": sum(1 for item in starts if item.get("started")),
        "failed_count": len(failures),
        "failures": failures,
    }


def _wired_sidecar_summary(session_dir: Path) -> dict[str, Any]:
    sidecars = sorted(session_dir.glob("*wired_loopback_input4.output_evidence.json")) if session_dir.is_dir() else []
    records: list[dict[str, Any]] = []
    healthy_count = 0
    signaled_count = 0
    for sidecar in sidecars:
        payload = _read_json(sidecar)
        wav_path = _resolve_path(payload.get("path"), base=sidecar.parent)
        frames = int(payload.get("frames") or payload.get("frames_seen") or 0)
        dropped = int(payload.get("dropped_buffer_count") or 0)
        interrupted = bool(payload.get("interrupted"))
        peaks = payload.get("peak_by_channel") if isinstance(payload.get("peak_by_channel"), list) else []
        input_channel = int(payload.get("input_channel_1based") or 0)
        if input_channel > 0 and len(peaks) >= input_channel:
            signal_peak = float(peaks[input_channel - 1] or 0.0)
        elif len(peaks) == 1:
            signal_peak = float(peaks[0] or 0.0)
        else:
            signal_peak = max((float(value or 0.0) for value in peaks), default=0.0)
        healthy = (
            bool(payload.get("started"))
            and wav_path.is_file()
            and wav_path.stat().st_size > 80
            and frames > 0
            and not interrupted
            and dropped == 0
        )
        signaled = healthy and signal_peak > 1e-7
        healthy_count += 1 if healthy else 0
        signaled_count += 1 if signaled else 0
        records.append(
            {
                "sidecar": str(sidecar),
                "wav": str(wav_path),
                "started": bool(payload.get("started")),
                "frames": frames,
                "duration_s": float(payload.get("duration_s") or 0.0),
                "channels": int(payload.get("channels") or 0),
                "input_channel_1based": input_channel,
                "signal_peak": signal_peak,
                "dropped_buffer_count": dropped,
                "interrupted": interrupted,
                "healthy": healthy,
                "signal_present": signaled,
            }
        )
    return {
        "sidecar_count": len(sidecars),
        "healthy_count": healthy_count,
        "signaled_count": signaled_count,
        "records": records,
    }


def _write_cross_stream_markdown(path: Path, report: dict[str, Any]) -> None:
    criteria = report.get("criteria") if isinstance(report.get("criteria"), dict) else {}
    wired_events = report.get("wired_loopback_events") if isinstance(report.get("wired_loopback_events"), dict) else {}
    wired_sidecars = report.get("wired_loopback_sidecars") if isinstance(report.get("wired_loopback_sidecars"), dict) else {}
    lines = [
        "# Cross-Stream Reconciliation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Checked: `{report.get('checked')}`",
        f"- Session dir: `{report.get('session_dir', '')}`",
        f"- Expected played blocks: `{report.get('expected_played_blocks')}`",
        f"- Audio-evidence WAVs: `{report.get('audio_evidence_wav_count')}`",
        f"- Wired loopback WAVs: `{report.get('wired_loopback_wav_count')}`",
        f"- Wired loopback started blocks: `{wired_events.get('started_count', '')}`",
        f"- Healthy wired sidecars: `{wired_sidecars.get('healthy_count', '')}`",
        f"- Wired sidecars with input signal: `{wired_sidecars.get('signaled_count', '')}`",
        "",
        "## Criteria",
    ]
    for key, value in criteria.items():
        lines.append(f"- `{key}`: `{value}`")
    paths = report.get("reports") if isinstance(report.get("reports"), dict) else {}
    if paths:
        lines.extend(["", "## Reports"])
        for key, value in paths.items():
            lines.append(f"- `{key}`: `{value}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cross_stream_reconciliation_report(
    *,
    validation_dir: Path,
    harness_report: dict[str, Any],
    focus_report: dict[str, Any],
    external_report: dict[str, Any],
    wired_loopback_requested: bool,
) -> dict[str, Any]:
    output_dir = validation_dir / "cross_stream_reconciliation"
    output_dir.mkdir(parents=True, exist_ok=True)
    readiness = harness_report.get("readiness_audit") if isinstance(harness_report.get("readiness_audit"), dict) else {}
    paths = _session_output_paths(validation_dir)
    session_dir = paths["session_dir"]
    expected_counts = readiness.get("expected_event_counts") if isinstance(readiness.get("expected_event_counts"), dict) else {}
    event_counts = readiness.get("event_counts") if isinstance(readiness.get("event_counts"), dict) else {}
    if not event_counts:
        evaluation = harness_report.get("evaluation") if isinstance(harness_report.get("evaluation"), dict) else {}
        event_counts = evaluation.get("event_counts") if isinstance(evaluation.get("event_counts"), dict) else {}
    expected_played_blocks = int(expected_counts.get("block_start") or event_counts.get("block_start") or 0)
    audio_evidence = readiness.get("audio_evidence") if isinstance(readiness.get("audio_evidence"), dict) else {}
    audio_evidence_wav_count = int(audio_evidence.get("record_count") or 0)
    if audio_evidence_wav_count <= 0 and session_dir.is_dir():
        audio_evidence_wav_count = len(sorted(session_dir.glob("*audio_evidence.wav")))
    wired_loopback_wav_count = len(sorted(session_dir.glob("*wired_loopback_input4.wav"))) if session_dir.is_dir() else 0
    wired_events = _wired_loopback_event_summary(paths["events_csv"])
    wired_sidecars = _wired_sidecar_summary(session_dir)
    external_checked = bool(external_report.get("checked"))
    external_file_ok = bool(external_report.get("passed")) and Path(str(external_report.get("xdf_path") or "")).is_file()
    external_returncode = external_report.get("labrecorder_returncode")
    external_stop_error = str(external_report.get("labrecorder_stop_error") or "").strip()
    external_mode = str(external_report.get("labrecorder_mode") or "").strip().lower()
    if external_returncode in ("", None):
        external_process_ok = external_file_ok
    else:
        try:
            code = int(external_returncode)
            external_process_ok = code == 0 or (
                external_file_ok
                and not external_stop_error
                and external_mode in {"rcs", "remote_control", "labrecorder_rcs"}
                and code in {1, -15}
            )
        except (TypeError, ValueError):
            external_process_ok = False
    readiness_checked = bool(readiness)
    strict_required = bool(
        harness_report.get("strict_study5_readiness_requested")
        or str(harness_report.get("validation_lane") or "") == emulator.VALIDATION_LANE_FULL_STACK
    )
    criteria: dict[str, bool] = {
        "strict_readiness_audit_present": readiness_checked or not strict_required,
        "strict_readiness_audit_passed": bool(readiness.get("passed")) if readiness_checked else True,
        "events_csv_matches_events_xdf": bool(
            _criterion_passed(readiness, "lsl_xdf_trigger_logging", "events_xdf_loadable_and_complete", default=not readiness_checked)
        ),
        "lsl_marker_csv_matches_lsl_marker_xdf": bool(
            _criterion_passed(readiness, "lsl_xdf_trigger_logging", "lsl_marker_xdf_dual_streams_complete", default=not readiness_checked)
        ),
        "events_csv_matches_lsl_marker_csv": bool(
            _criterion_passed(readiness, "lsl_xdf_trigger_logging", "events_and_lsl_marker_csvs_match", default=not readiness_checked)
        ),
        "audio_evidence_wavs_cover_played_blocks": bool(
            _criterion_passed(readiness, "local_recorder_audio_evidence", "audio_evidence_files_cover_played_blocks", default=not readiness_checked)
        ),
        "audio_xdf_reconciliation_passed": bool(
            _criterion_passed(readiness, "local_recorder_audio_evidence", "lsl_xdf_audio_reconciliation_passed", default=not readiness_checked)
        ),
        "response_markers_match_mouse_clicks_and_wav_pulses": bool(
            _section_passed(readiness, "response_marker_path", default=not readiness_checked)
        ),
        "analysis_rt_matches_emulated_plan": bool(
            _criterion_passed(readiness, "analysis_outputs", "emulated_rt_values_match_plan_tolerance", default=not readiness_checked)
        ),
        "external_labrecorder_xdf_matches_local_lsl_markers": (not external_checked) or bool(external_report.get("passed")),
        "external_labrecorder_process_clean_exit": (not external_checked) or bool(external_process_ok),
        "wired_loopback_wavs_cover_played_blocks": (
            not wired_loopback_requested
            or not readiness_checked
            or (expected_played_blocks > 0 and wired_loopback_wav_count >= expected_played_blocks)
        ),
        "wired_loopback_started_for_played_blocks": (
            not wired_loopback_requested
            or not readiness_checked
            or (expected_played_blocks > 0 and int(wired_events.get("started_count") or 0) >= expected_played_blocks)
        ),
        "wired_loopback_sidecars_nonempty_clean": (
            not wired_loopback_requested
            or not readiness_checked
            or (expected_played_blocks > 0 and int(wired_sidecars.get("healthy_count") or 0) >= expected_played_blocks)
        ),
        "wired_loopback_input_signal_present": (
            not wired_loopback_requested
            or not readiness_checked
            or (expected_played_blocks > 0 and int(wired_sidecars.get("signaled_count") or 0) >= expected_played_blocks)
        ),
    }
    checked = readiness_checked or external_checked or wired_loopback_requested
    report = {
        "schema": "pps-desktop-rehearsal-cross-stream-reconciliation.v1",
        "checked": bool(checked),
        "passed": bool(all(criteria.values())),
        "validation_dir": str(validation_dir),
        "session_dir": str(session_dir),
        "session_manifest": str(paths["session_manifest"]),
        "events_csv": str(paths["events_csv"]),
        "lsl_markers_csv": str(paths["lsl_markers_csv"]),
        "expected_played_blocks": expected_played_blocks,
        "audio_evidence_wav_count": audio_evidence_wav_count,
        "wired_loopback_requested": bool(wired_loopback_requested),
        "wired_loopback_wav_count": wired_loopback_wav_count,
        "wired_loopback_events": wired_events,
        "wired_loopback_sidecars": wired_sidecars,
        "event_counts": event_counts,
        "criteria": criteria,
        "reports": {
            "readiness_audit": str((readiness.get("output_dir") or "") and Path(str(readiness.get("output_dir"))) / "protocol11_study5_readiness_audit.json"),
            "local_lsl_xdf_audio": str((readiness.get("output_dir") or "") and Path(str(readiness.get("output_dir"))) / "lsl_xdf_audio_reconciliation_report.json"),
            "external_labrecorder": str(validation_dir / "external_labrecorder_reconciliation" / "external_labrecorder_reconciliation_report.json"),
        },
        "focus_report": str(validation_dir / "focus_validation_report.json"),
        "harness_report": str(validation_dir / "full_realtime_participant_emulation_report.json"),
        "external_labrecorder": external_report,
        "limitations": [
            "This cross-check reconciles software timing streams, local runtime WAV evidence, and the wired tactile proxy when requested.",
            "It does not prove human perception, fatigue, or Woojer mechanical vibration onset.",
        ],
    }
    _write_json(output_dir / "cross_stream_reconciliation_report.json", report)
    _write_cross_stream_markdown(output_dir / "cross_stream_reconciliation_report.md", report)
    return report


def _write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Desktop Full Mock Rehearsal",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Output root: `{report.get('environment_root', '')}`",
        f"- Validation dir: `{report.get('validation_dir', report.get('output_dir', ''))}`",
        f"- External XDF: `{report.get('xdf_path', '')}`",
        f"- Error: `{report.get('error', '')}`" if report.get("error") else "",
    ]
    comparison = report.get("comparison") if isinstance(report.get("comparison"), dict) else {}
    if comparison:
        lines.extend(
            [
                "",
                "## External XDF",
                "",
                f"- Expected markers: `{comparison.get('expected_marker_count')}`",
                f"- Rich XDF samples: `{comparison.get('rich_xdf_sample_count')}`",
                f"- Numeric XDF samples: `{comparison.get('numeric_xdf_sample_count')}`",
                f"- Missing event IDs: `{comparison.get('missing_event_ids') or []}`",
                f"- Field mismatches: `{comparison.get('field_mismatches') or []}`",
            ]
        )
    limitations = report.get("limitations") or []
    if limitations:
        lines.extend(["", "## Limitations", ""])
        for limitation in limitations:
            lines.append(f"- {limitation}")
    path.write_text("\n".join(line for line in lines if line != "") + "\n", encoding="utf-8")


def run_rehearsal(args: argparse.Namespace) -> dict[str, Any]:
    parent = Path(args.desktop_output_parent).expanduser()
    if not parent.is_dir():
        raise ValueError(f"Desktop output parent does not exist: {parent}")
    runner = Path(args.runner).expanduser()
    if args.runner_mode == "packaged" and not runner.is_file():
        raise FileNotFoundError(f"Packaged runner exe was not found: {runner}")
    if args.wired_loopback != WIRED_LOOPBACK_OFF and args.audio_mode != "hardware":
        raise ValueError("Wired loopback rehearsal requires --audio-mode hardware.")
    audio_preflight = _audio_route_preflight() if not args.skip_audio_preflight else {"checked": False}
    if (
        not args.skip_audio_preflight
        and args.validation_lane == emulator.VALIDATION_LANE_FULL_STACK
        and not audio_preflight.get("komplete_asio_4x4_ready")
    ):
        raise RuntimeError("Komplete Audio ASIO 4-input/4-output route was not found; inspect the audio_preflight field.")
    labrecorder_cli: Path | None = None
    if args.external_labrecorder:
        labrecorder_cli = _find_labrecorder_cli(args.labrecorder_cli)
        args.labrecorder_cli = labrecorder_cli

    environment = _create_rehearsal_environment(args)
    environment_root = Path(environment["environment_root"]).resolve()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    validation_dir = output_validation_reports_dir(environment_root) / f"mock_rehearsal_{stamp}"
    validation_dir.mkdir(parents=True, exist_ok=True)

    labrecorder_command: list[str] = []
    labrecorder_returncode: int | None = None
    stdout_path = validation_dir / "external_labrecorder_stdout.txt"
    stderr_path = validation_dir / "external_labrecorder_stderr.txt"
    external_report: dict[str, Any] = {"checked": False, "passed": True}
    xdf_path = validation_dir / "session_external_labrecorder.xdf"
    _write_json(
        validation_dir / "desktop_full_mock_rehearsal_preflight.json",
        {
            "schema": SCHEMA + ".preflight",
            "environment": environment,
            "audio_preflight": audio_preflight,
            "external_labrecorder_requested": bool(args.external_labrecorder),
            "labrecorder_cli": str(labrecorder_cli or ""),
            "wired_loopback": str(args.wired_loopback),
        },
    )

    emulator_argv = build_emulator_argv(args, output_dir=validation_dir)
    harness_exit_code = 1
    harness_error = ""
    try:
        harness_exit_code = int(emulator.main(emulator_argv))
    except Exception as exc:
        harness_error = str(exc)

    focus_report = _read_json(validation_dir / "focus_validation_report.json")
    if args.external_labrecorder:
        analysis_outputs = focus_report.get("analysis_outputs") if isinstance(focus_report.get("analysis_outputs"), dict) else {}
        xdf_path = _resolve_path(
            focus_report.get("external_labrecorder_xdf") or analysis_outputs.get("external_labrecorder_xdf"),
            base=validation_dir,
        )
        runner_labrecorder_report_path = _resolve_path(
            focus_report.get("external_labrecorder_report") or analysis_outputs.get("external_labrecorder_report"),
            base=validation_dir,
        )
        runner_labrecorder_report = _read_json(runner_labrecorder_report_path)
        start_info = runner_labrecorder_report.get("start") if isinstance(runner_labrecorder_report.get("start"), dict) else {}
        stop_info = runner_labrecorder_report.get("stop") if isinstance(runner_labrecorder_report.get("stop"), dict) else {}
        labrecorder_command = list(start_info.get("command") or stop_info.get("command") or [])
        labrecorder_returncode = stop_info.get("returncode") if "returncode" in stop_info else None
        stdout_path = _resolve_path(
            focus_report.get("external_labrecorder_stdout") or analysis_outputs.get("external_labrecorder_stdout") or stop_info.get("stdout_path"),
            base=validation_dir,
        )
        stderr_path = _resolve_path(
            focus_report.get("external_labrecorder_stderr") or analysis_outputs.get("external_labrecorder_stderr") or stop_info.get("stderr_path"),
            base=validation_dir,
        )
        external_report = reconcile_external_labrecorder_xdf(
            validation_dir=validation_dir,
            xdf_path=xdf_path,
            labrecorder_cli=labrecorder_cli,
            labrecorder_command=labrecorder_command,
            labrecorder_returncode=labrecorder_returncode,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        external_report["checked"] = True
        external_report["labrecorder_mode"] = str(start_info.get("mode") or ("rcs" if start_info.get("labrecorder_exe") else "cli"))
        external_report["labrecorder_stop_error"] = str(stop_info.get("error") or "")
        external_report["labrecorder_capture_report"] = str(runner_labrecorder_report_path)

    harness_report = _read_json(validation_dir / "full_realtime_participant_emulation_report.json")
    cross_stream_report = cross_stream_reconciliation_report(
        validation_dir=validation_dir,
        harness_report=harness_report,
        focus_report=focus_report,
        external_report=external_report,
        wired_loopback_requested=args.wired_loopback != WIRED_LOOPBACK_OFF,
    )
    passed = (
        harness_exit_code == 0
        and bool(harness_report.get("passed"))
        and bool(external_report.get("passed", True))
        and bool(cross_stream_report.get("passed"))
        and not harness_error
    )
    report = {
        "schema": SCHEMA,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "passed": bool(passed),
        "full_mock_rehearsal_ready": bool(passed),
        "environment_root": str(environment_root),
        "validation_dir": str(validation_dir),
        "profile_id": str(args.profile),
        "participant_id": str(args.participant_id),
        "session_name": str(args.session_name),
        "runner": str(runner),
        "runner_mode": str(args.runner_mode),
        "audio_mode": str(args.audio_mode),
        "validation_lane": str(args.validation_lane),
        "mouse_backend": str(args.mouse_backend),
        "wired_loopback": str(args.wired_loopback),
        "external_labrecorder_requested": bool(args.external_labrecorder),
        "audio_preflight": audio_preflight,
        "emulator_argv": emulator_argv,
        "harness_exit_code": harness_exit_code,
        "harness_error": harness_error,
        "harness_report": str(validation_dir / "full_realtime_participant_emulation_report.json"),
        "focus_report": str(validation_dir / "focus_validation_report.json"),
        "session_dir": str(focus_report.get("session_dir") or ""),
        "external_labrecorder": external_report,
        "cross_stream_reconciliation": cross_stream_report,
        "limitations": [
            "Emulated participant responses prove operational data-shape and capture behavior, not human perception or fatigue.",
            "The wired loopback records an analog duplicate tactile proxy from Output 4 to Input 4, not Woojer mechanical onset.",
        ],
    }
    _write_json(validation_dir / "desktop_full_mock_rehearsal_report.json", report)
    _write_markdown_report(validation_dir / "desktop_full_mock_rehearsal_report.md", report)
    print(f"Wrote desktop full mock rehearsal report: {validation_dir / 'desktop_full_mock_rehearsal_report.json'}")
    return report


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a full Desktop Study 5 mock rehearsal with emulated participant responses.")
    parser.add_argument("--desktop-output-parent", type=Path, default=_default_desktop_output_parent())
    parser.add_argument("--session-name", default="study_5_full_mock_rehearsal")
    parser.add_argument("--profile", default=emulator.STUDY5_TEMPLATE_ID)
    parser.add_argument("--participant-id", default="P050")
    parser.add_argument("--runner", type=Path, default=REPO_ROOT / "dist" / "PPSExperimentRunner" / "PPSExperimentRunner.exe")
    parser.add_argument("--runner-mode", default="packaged", choices=["packaged", "source"])
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument("--miss-rate", type=float, default=0.06)
    parser.add_argument("--min-misses", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260615)
    parser.add_argument("--mouse-backend", default="pynput", choices=["pynput", "win32", "pyautogui", "qtest"])
    parser.add_argument(
        "--validation-lane",
        default=emulator.VALIDATION_LANE_FULL_STACK,
        choices=[emulator.VALIDATION_LANE_SOFTWARE_ONLY, emulator.VALIDATION_LANE_FULL_STACK],
    )
    parser.add_argument("--audio-mode", default="hardware", choices=["validation-realtime", "hardware"])
    parser.add_argument("--validation-audio-chunk-frames", type=int, default=4096)
    parser.add_argument("--audio-device-index", type=int, default=None)
    parser.add_argument(
        "--wired-loopback",
        default=WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY,
        choices=[WIRED_LOOPBACK_OFF, WIRED_LOOPBACK_CLI_OUTPUT4_TACTILE_PROXY],
    )
    parser.add_argument("--external-labrecorder", action="store_true")
    parser.add_argument("--labrecorder-cli", type=Path, default=None)
    parser.add_argument("--labrecorder-stream-timeout-s", type=float, default=10.0)
    parser.add_argument("--labrecorder-startup-s", type=float, default=1.0)
    parser.add_argument("--labrecorder-stop-timeout-s", type=float, default=8.0)
    parser.add_argument("--strict-study5-readiness", dest="strict_study5_readiness", action="store_true", default=True)
    parser.add_argument("--no-strict-study5-readiness", dest="strict_study5_readiness", action="store_false")
    parser.add_argument("--skip-audio-preflight", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    report = run_rehearsal(args)
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
