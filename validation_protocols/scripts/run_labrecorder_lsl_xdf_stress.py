"""Record PPS LSL streams with LabRecorder and verify the resulting XDF.

This internal validation checks the external LSL recording path. It creates the
same rich/numeric streams used by the runner, records them with LabRecorderCLI,
loads the XDF with pyxdf, and reconciles recorded samples against local marker
records. It does not play audio or touch hardware outputs.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from peripersonal_space_toolkit.session_events import SessionEventLogger  # noqa: E402
from peripersonal_space_toolkit.output_layout import _filesystem_path  # noqa: E402
from peripersonal_space_toolkit.timing_events import (  # noqa: E402
    LSL_MARKER_CHANNELS,
    LSL_NUMERIC_SOURCE_ID_PREFIX,
    LSL_SOURCE_ID_PREFIX,
    TimingEventHub,
)


SCHEMA = "pps-labrecorder-lsl-xdf-stress.v1"


def _default_output_dir() -> Path:
    return Path("artifacts") / "validation_runs" / f"labrecorder_lsl_xdf_{time.strftime('%Y%m%d_%H%M%S')}"


def _mkdir(path: Path | str) -> None:
    os.makedirs(_filesystem_path(Path(path)), exist_ok=True)


def _path_exists(path: Path | str) -> bool:
    return os.path.exists(_filesystem_path(Path(path)))


def _path_is_file(path: Path | str) -> bool:
    return os.path.isfile(_filesystem_path(Path(path)))


def _path_size(path: Path | str) -> int:
    try:
        return os.path.getsize(_filesystem_path(Path(path)))
    except OSError:
        return 0


def _write_text(path: Path, text: str) -> None:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        handle.write(text)


def _find_labrecorder_cli(explicit: Path | None = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    for command in ("LabRecorderCLI", "LabRecorderCLI.exe"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found))
    candidates.extend(sorted(Path("local_data/software_tools/labrecorder").glob("**/LabRecorderCLI.exe")))
    for candidate in candidates:
        if _path_exists(candidate):
            return candidate
    raise FileNotFoundError(
        "LabRecorderCLI.exe was not found. Run validation_protocols/scripts/download_labrecorder.ps1 "
        "or pass --labrecorder-cli."
    )


def _stats(values: list[float]) -> dict[str, Any]:
    values = [float(value) for value in values if math.isfinite(float(value))]
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)
    return {
        "count": len(values),
        "min_ms": min(values),
        "mean_ms": statistics.fmean(values),
        "sd_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median_ms": statistics.median(values),
        "p95_ms": ordered[p95_index],
        "max_ms": max(values),
    }


def _flatten_sample(sample: Any) -> list[Any]:
    if hasattr(sample, "tolist"):
        sample = sample.tolist()
    if isinstance(sample, (list, tuple)):
        return list(sample)
    return [sample]


def _stream_name(stream: dict[str, Any]) -> str:
    name = ((stream.get("info") or {}).get("name") or [""])[0]
    return str(name)


def _load_xdf_streams(xdf_path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    import pyxdf  # type: ignore

    streams, header = pyxdf.load_xdf(_filesystem_path(xdf_path))
    rich_rows: list[dict[str, Any]] = []
    numeric_rows: list[dict[str, Any]] = []
    for stream in streams:
        name = _stream_name(stream)
        times_raw = stream.get("time_stamps")
        series_raw = stream.get("time_series")
        times = [] if times_raw is None else list(times_raw)
        series = [] if series_raw is None else list(series_raw)
        if name == "PPSMarkersV2":
            for index, sample in enumerate(series):
                values = _flatten_sample(sample)
                row = {field: str(values[pos]) if pos < len(values) else "" for pos, field in enumerate(LSL_MARKER_CHANNELS)}
                row["sample_lsl_timestamp"] = f"{float(times[index]):.9f}" if index < len(times) else ""
                try:
                    row["payload"] = json.loads(row.get("payload_json", "") or "{}")
                except json.JSONDecodeError:
                    row["payload"] = {}
                rich_rows.append(row)
        elif name == "PPSTriggerCodes":
            for index, sample in enumerate(series):
                values = _flatten_sample(sample)
                row = {
                    "event_code": str(int(float(values[0]))) if values else "",
                    "sample_lsl_timestamp": f"{float(times[index]):.9f}" if index < len(times) else "",
                }
                numeric_rows.append(row)
    return rich_rows, numeric_rows, header


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    _mkdir(path.parent)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _record_with_labrecorder(
    *,
    labrecorder_cli: Path,
    xdf_path: Path,
    rich_source_id: str,
    numeric_source_id: str,
    startup_s: float,
) -> subprocess.Popen:
    predicates = [f"source_id='{rich_source_id}'", f"source_id='{numeric_source_id}'"]
    creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        [str(labrecorder_cli), _filesystem_path(xdf_path), *predicates],
        cwd=str(REPO_ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=creationflags,
    )
    time.sleep(max(0.0, startup_s))
    return process


def _stop_labrecorder(process: subprocess.Popen, *, timeout_s: float) -> tuple[int | None, str, str]:
    if process.poll() is None:
        try:
            if process.stdin is not None:
                process.stdin.write("\n")
                process.stdin.flush()
            elif os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.send_signal(signal.SIGINT)
        except Exception:
            process.terminate()
    try:
        stdout, stderr = process.communicate(timeout=max(0.1, timeout_s))
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate(timeout=2.0)
    return process.returncode, stdout or "", stderr or ""


def _emit_markers(
    *,
    output_dir: Path,
    logger: SessionEventLogger,
    hub: TimingEventHub,
    session_id: str,
    participant_id: str,
    count: int,
    interval_s: float,
    warmup_s: float,
) -> tuple[SessionEventLogger, TimingEventHub, Path, Path, Path]:
    time.sleep(max(0.0, warmup_s))
    hub.log("session_start", validation_schema=SCHEMA, output_dir=str(output_dir))
    hub.log("block_start", block_index=1, block_number=1, block_label="labrecorder_lsl_xdf_stress")
    sample_rate = 44100
    for index in range(1, count + 1):
        sample_index = 44100 + index * 997
        event_type = "test_marker" if index % 2 else "response_marker_start"
        payload = {
            "validation_schema": SCHEMA,
            "block_index": 1,
            "block_number": 1,
            "trial_uid": f"LABREC_XDF_T{index:03d}",
            "trial_index": index,
            "sample_index": sample_index,
            "sample_rate": sample_rate,
            "timestamp_quality": "software_log",
            "labrecorder_xdf_index": index,
        }
        if event_type == "response_marker_start":
            payload.update({"mouse_event_id": index, "marker_channel": 3, "marker_gain": 0.05})
        hub.log(event_type, **payload)
        if interval_s > 0:
            time.sleep(interval_s)
    hub.log("block_end", block_index=1, block_number=1, block_label="labrecorder_lsl_xdf_stress")
    hub.log("session_end", validation_schema=SCHEMA)
    hub.flush_callback_events(timeout_s=2.0)
    events_csv = logger.write_csv(output_dir / "events.csv")
    lsl_markers_csv = hub.write_lsl_markers_csv(output_dir / "lsl_markers.csv")
    trigger_dictionary = hub.write_trigger_dictionary(output_dir / "trigger_dictionary.json")
    return logger, hub, events_csv, lsl_markers_csv, trigger_dictionary


def compare_xdf_to_local(
    *,
    rich_rows: list[dict[str, Any]],
    numeric_rows: list[dict[str, Any]],
    marker_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    def expected_marker_field(row: dict[str, Any], field: str) -> str:
        value = row.get(field, "")
        if value not in (None, ""):
            return str(value)
        try:
            payload = json.loads(str(row.get("payload_json", "") or "{}"))
        except json.JSONDecodeError:
            payload = {}
        payload_value = payload.get(field, "")
        return "" if payload_value is None else str(payload_value)

    expected = [row for row in marker_rows if str(row.get("pushed_to_lsl", "")).lower() in {"true", "1", "yes"}]
    expected_by_id = {str(row.get("event_id", "")): row for row in expected}
    rich_by_id = {str(row.get("event_id", "")): row for row in rich_rows if str(row.get("event_id", ""))}
    expected_ids = sorted(expected_by_id, key=lambda value: int(value) if value.isdigit() else value)
    rich_ids = sorted(rich_by_id, key=lambda value: int(value) if value.isdigit() else value)
    missing_ids = sorted(set(expected_ids) - set(rich_ids), key=lambda value: int(value) if value.isdigit() else value)
    extra_ids = sorted(set(rich_ids) - set(expected_ids), key=lambda value: int(value) if value.isdigit() else value)
    duplicate_rich_ids = sorted({value for value in [str(row.get("event_id", "")) for row in rich_rows] if value and [str(row.get("event_id", "")) for row in rich_rows].count(value) > 1})

    mismatches: list[dict[str, str]] = []
    for event_id in sorted(set(expected_ids) & set(rich_ids), key=lambda value: int(value) if value.isdigit() else value):
        expected_row = expected_by_id[event_id]
        rich_row = rich_by_id[event_id]
        for field in ("event_type", "event_code", "trigger_key", "session_id", "participant_id", "block_index", "trial_uid", "sample_index", "timestamp_quality"):
            expected_value = expected_marker_field(expected_row, field)
            observed_value = str(rich_row.get(field, "") or "")
            if expected_value != observed_value:
                mismatches.append({"event_id": event_id, "field": field, "expected": expected_value, "observed": observed_value})

    expected_codes = Counter(str(row.get("event_code", "")) for row in expected if str(row.get("event_code", "")))
    observed_codes = Counter(str(row.get("event_code", "")) for row in numeric_rows if str(row.get("event_code", "")))
    missing_codes = {code: expected_codes[code] - observed_codes.get(code, 0) for code in sorted(expected_codes) if expected_codes[code] > observed_codes.get(code, 0)}
    extra_codes = {code: observed_codes[code] - expected_codes.get(code, 0) for code in sorted(observed_codes) if observed_codes[code] > expected_codes.get(code, 0)}
    timestamp_deltas_ms = []
    for event_id, expected_row in expected_by_id.items():
        rich_row = rich_by_id.get(event_id)
        if not rich_row:
            continue
        try:
            timestamp_deltas_ms.append((float(rich_row["sample_lsl_timestamp"]) - float(expected_row["lsl_timestamp"])) * 1000.0)
        except (KeyError, TypeError, ValueError):
            pass

    pass_checks = {
        "rich_xdf_has_all_expected_event_ids": not missing_ids,
        "rich_xdf_has_no_extra_event_ids": not extra_ids,
        "rich_xdf_has_no_duplicate_event_ids": not duplicate_rich_ids,
        "rich_xdf_fields_match_local_marker_mirror": not mismatches,
        "numeric_xdf_codes_match_expected_counts": not missing_codes and not extra_codes and len(numeric_rows) == len(expected),
    }
    return {
        "expected_marker_count": len(expected),
        "rich_xdf_sample_count": len(rich_rows),
        "numeric_xdf_sample_count": len(numeric_rows),
        "missing_event_ids": missing_ids,
        "extra_event_ids": extra_ids,
        "duplicate_rich_event_ids": duplicate_rich_ids,
        "field_mismatches": mismatches,
        "missing_numeric_code_counts": missing_codes,
        "extra_numeric_code_counts": extra_codes,
        "event_type_counts_xdf": dict(Counter(str(row.get("event_type", "")) for row in rich_rows)),
        "timestamp_delta_xdf_minus_local_marker_ms": _stats(timestamp_deltas_ms),
        "pass_checks": pass_checks,
        "passed": all(pass_checks.values()),
    }


def run_stress(
    *,
    output_dir: Path,
    labrecorder_cli: Path | None = None,
    count: int = 12,
    interval_s: float = 0.05,
    outlet_warmup_s: float = 1.0,
    recorder_startup_s: float = 2.5,
    recorder_stop_timeout_s: float = 8.0,
) -> dict[str, Any]:
    _mkdir(output_dir)
    labrecorder_cli = _find_labrecorder_cli(labrecorder_cli)
    session_id = f"labrecorder_xdf_{time.strftime('%Y%m%d_%H%M%S')}"
    participant_id = "VALIDATION_LABRECORDER"
    rich_source_id = f"{LSL_SOURCE_ID_PREFIX}-{session_id}"
    numeric_source_id = f"{LSL_NUMERIC_SOURCE_ID_PREFIX}-{session_id}"
    xdf_path = output_dir / "labrecorder_lsl_capture.xdf"
    logger = SessionEventLogger(participant_id=participant_id)
    hub = TimingEventHub(logger, enable_lsl=True, session_id=session_id, participant_id=participant_id)
    time.sleep(max(0.0, outlet_warmup_s))
    process = _record_with_labrecorder(
        labrecorder_cli=labrecorder_cli,
        xdf_path=xdf_path,
        rich_source_id=rich_source_id,
        numeric_source_id=numeric_source_id,
        startup_s=recorder_startup_s,
    )
    try:
        logger, hub, events_csv, lsl_markers_csv, trigger_dictionary = _emit_markers(
            output_dir=output_dir,
            logger=logger,
            hub=hub,
            session_id=session_id,
            participant_id=participant_id,
            count=count,
            interval_s=interval_s,
            warmup_s=0.0,
        )
        time.sleep(0.5)
    finally:
        returncode, stdout, stderr = _stop_labrecorder(process, timeout_s=recorder_stop_timeout_s)
        _write_text(output_dir / "labrecorder_stdout.txt", stdout)
        _write_text(output_dir / "labrecorder_stderr.txt", stderr)
        hub.close()

    if not _path_exists(xdf_path) or _path_size(xdf_path) == 0:
        report = {
            "schema": SCHEMA,
            "passed": False,
            "labrecorder_returncode": returncode,
            "xdf_path": str(xdf_path),
            "error": "LabRecorder did not produce a non-empty XDF file.",
        }
    else:
        rich_rows, numeric_rows, _header = _load_xdf_streams(xdf_path)
        marker_rows = []
        with open(_filesystem_path(lsl_markers_csv), newline="", encoding="utf-8-sig") as handle:
            marker_rows = [dict(row) for row in csv.DictReader(handle)]
        comparison = compare_xdf_to_local(rich_rows=rich_rows, numeric_rows=numeric_rows, marker_rows=marker_rows)
        rich_csv_fields = [*LSL_MARKER_CHANNELS, "sample_lsl_timestamp"]
        _write_csv(output_dir / "labrecorder_rich_xdf_samples.csv", rich_rows, rich_csv_fields)
        _write_csv(output_dir / "labrecorder_numeric_xdf_samples.csv", numeric_rows, ["event_code", "sample_lsl_timestamp"])
        report = {
            "schema": SCHEMA,
            "passed": bool(comparison["passed"]),
            "output_dir": str(output_dir),
            "labrecorder_cli": str(labrecorder_cli),
            "labrecorder_returncode": returncode,
            "xdf_path": str(xdf_path),
            "events_csv": str(events_csv),
            "lsl_markers_csv": str(lsl_markers_csv),
            "trigger_dictionary_json": str(trigger_dictionary),
            "session_id": session_id,
            "participant_id": participant_id,
            "rich_source_id": rich_source_id,
            "numeric_source_id": numeric_source_id,
            "comparison": comparison,
            "limitations": [
                "This validates external LabRecorder/XDF preservation of PPS LSL streams, not physical audio/tactile signal arrival.",
                "The numeric stream verifies trigger-code counts; full reconstruction uses PPSMarkersV2 or trigger_dictionary.json.",
            ],
        }
    _write_text(output_dir / "labrecorder_lsl_xdf_report.json", json.dumps(report, indent=2))
    _write_markdown_report(report, output_dir / "labrecorder_lsl_xdf_report.md")
    return report


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    comparison = report.get("comparison") or {}
    lines = [
        "# LabRecorder LSL XDF Stress",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- XDF: `{report.get('xdf_path')}`",
        f"- LabRecorder return code: `{report.get('labrecorder_returncode')}`",
        f"- Expected markers: {comparison.get('expected_marker_count')}",
        f"- Rich XDF samples: {comparison.get('rich_xdf_sample_count')}",
        f"- Numeric XDF samples: {comparison.get('numeric_xdf_sample_count')}",
        f"- Missing event IDs: `{comparison.get('missing_event_ids') or []}`",
        f"- Extra event IDs: `{comparison.get('extra_event_ids') or []}`",
        f"- Field mismatches: `{comparison.get('field_mismatches') or []}`",
        f"- Numeric missing codes: `{comparison.get('missing_numeric_code_counts') or {}}`",
        f"- Numeric extra codes: `{comparison.get('extra_numeric_code_counts') or {}}`",
        f"- Timestamp delta XDF-local: `{json.dumps(comparison.get('timestamp_delta_xdf_minus_local_marker_ms') or {}, sort_keys=True)}`",
        "",
        "## Checks",
        "",
    ]
    for name, passed in sorted((comparison.get("pass_checks") or {}).items()):
        lines.append(f"- `{name}`: {passed}")
    lines.extend(["", "## Limitations", ""])
    for limitation in report.get("limitations") or []:
        lines.append(f"- {limitation}")
    if report.get("error"):
        lines.extend(["", "## Error", "", str(report["error"])])
    _write_text(path, "\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record PPS LSL streams with LabRecorderCLI and verify the XDF.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--labrecorder-cli", type=Path, default=None)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--interval-s", type=float, default=0.05)
    parser.add_argument("--outlet-warmup-s", type=float, default=1.0)
    parser.add_argument("--recorder-startup-s", type=float, default=2.5)
    parser.add_argument("--recorder-stop-timeout-s", type=float, default=8.0)
    args = parser.parse_args(argv)
    report = run_stress(
        output_dir=args.output_dir or _default_output_dir(),
        labrecorder_cli=args.labrecorder_cli,
        count=args.count,
        interval_s=args.interval_s,
        outlet_warmup_s=args.outlet_warmup_s,
        recorder_startup_s=args.recorder_startup_s,
        recorder_stop_timeout_s=args.recorder_stop_timeout_s,
    )
    print(f"Wrote {Path(report.get('output_dir') or args.output_dir or '.') / 'labrecorder_lsl_xdf_report.json'}")
    return 0 if report.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
