"""Summarize internal PPS validation artifacts without modifying runtime code."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any


def _read_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            payload_json = row.get("payload_json", "") or ""
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                payload = {}
            merged = dict(row)
            merged["payload"] = payload
            rows.append(merged)
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id", "")).strip()


def _event_type(row: dict[str, Any]) -> str:
    return str(row.get("event_type", "")).strip()


def _event_id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)


def _is_planned(row: dict[str, Any]) -> bool:
    payload = row.get("payload", {}) or {}
    value = payload.get("planned", False)
    return str(value).strip().lower() in {"1", "true", "yes"}


def _float_value(value: Any) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _load_json_reports(root: Path, filename: str) -> list[dict[str, Any]]:
    reports = []
    if not root.exists():
        return reports
    for path in root.rglob(filename):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        data["_path"] = str(path)
        reports.append(data)
    return reports


def _mouse_marker_deltas(events: list[dict[str, Any]]) -> list[float]:
    mouse_by_id = {_event_id(row): row for row in events if _event_type(row) == "mouse_click"}
    deltas = []
    for marker in events:
        if _event_type(marker) != "response_marker_start":
            continue
        payload = marker.get("payload", {}) or {}
        mouse_id = str(payload.get("mouse_event_id", "")).strip()
        mouse = mouse_by_id.get(mouse_id)
        if not mouse:
            continue
        delta = (_float_value(marker.get("monotonic_time")) - _float_value(mouse.get("monotonic_time"))) * 1000.0
        if math.isfinite(delta):
            deltas.append(delta)
    return deltas


def _format_ms_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"count": 0}
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)
    return {
        "count": len(values),
        "min_ms": min(values),
        "mean_ms": statistics.fmean(values),
        "sd_ms": statistics.stdev(values) if len(values) > 1 else 0.0,
        "median_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[p95_index],
        "max_ms": max(values),
    }


def _summarize(args: argparse.Namespace) -> dict[str, Any]:
    session_dir = Path(args.session_dir) if args.session_dir else None
    run_dir = Path(args.run_dir) if args.run_dir else None
    output_dir = Path(args.output_dir) if args.output_dir else (
        (session_dir / "analysis" / "validation_summary") if session_dir else Path("artifacts") / "validation_runs" / "summary"
    )

    events_path = Path(args.events_csv) if args.events_csv else (session_dir / "events.csv" if session_dir else None)
    lsl_path = Path(args.lsl_probe_csv) if args.lsl_probe_csv else None
    timing_qc_path = Path(args.timing_qc_csv) if args.timing_qc_csv else (session_dir / "analysis" / "timing_qc.csv" if session_dir else None)

    events = _read_events(events_path) if events_path else []
    lsl_rows = _read_csv(lsl_path) if lsl_path else []
    timing_qc_rows = _read_csv(timing_qc_path) if timing_qc_path else []

    event_ids = [_event_id(row) for row in events if _event_id(row)]
    duplicate_event_ids = sorted({event_id for event_id in event_ids if event_ids.count(event_id) > 1})
    actual_events = [row for row in events if not _is_planned(row)]
    lsl_ids = [str(row.get("event_id", "")).strip() for row in lsl_rows if str(row.get("event_id", "")).strip()]
    actual_ids = [_event_id(row) for row in actual_events if _event_id(row)]

    missing_from_lsl = sorted(set(actual_ids) - set(lsl_ids), key=_event_id_sort_key)
    extra_in_lsl = sorted(set(lsl_ids) - set(actual_ids), key=_event_id_sort_key)
    duplicate_lsl_ids = sorted({event_id for event_id in lsl_ids if lsl_ids.count(event_id) > 1})

    roots = [path for path in (session_dir, run_dir) if path is not None]
    latency_reports: list[dict[str, Any]] = []
    session_latency_reports: list[dict[str, Any]] = []
    for root in roots:
        latency_reports.extend(_load_json_reports(root, "latency_validation_report.json"))
        session_latency_reports.extend(_load_json_reports(root, "session_latency_validation_report.json"))

    marker_delta_values = _mouse_marker_deltas(events)
    qc_deltas = [
        _float_value(row.get("marker_minus_mouse_ms"))
        for row in timing_qc_rows
        if math.isfinite(_float_value(row.get("marker_minus_mouse_ms")))
    ]

    return {
        "schema": "pps-internal-validation-summary.v1",
        "session_dir": str(session_dir) if session_dir else "",
        "run_dir": str(run_dir) if run_dir else "",
        "events_csv": str(events_path) if events_path else "",
        "lsl_probe_csv": str(lsl_path) if lsl_path else "",
        "timing_qc_csv": str(timing_qc_path) if timing_qc_path else "",
        "event_count": len(events),
        "actual_event_count": len(actual_events),
        "planned_event_count": len(events) - len(actual_events),
        "event_type_counts": dict(Counter(_event_type(row) for row in events)),
        "duplicate_event_ids": duplicate_event_ids,
        "timing_anchor_fallback_count": sum(1 for row in events if _event_type(row) == "timing_anchor_fallback"),
        "lsl_sample_count": len(lsl_rows),
        "lsl_missing_actual_event_ids": missing_from_lsl if lsl_rows else [],
        "lsl_extra_event_ids": extra_in_lsl if lsl_rows else [],
        "lsl_duplicate_event_ids": duplicate_lsl_ids if lsl_rows else [],
        "mouse_click_count": sum(1 for row in events if _event_type(row) == "mouse_click"),
        "response_marker_start_count": sum(1 for row in events if _event_type(row) == "response_marker_start"),
        "mouse_to_marker_from_events": _format_ms_stats(marker_delta_values),
        "mouse_to_marker_from_timing_qc": _format_ms_stats(qc_deltas),
        "latency_reports": [
            {
                "path": report.get("_path", ""),
                "status": report.get("status", ""),
                "passed": report.get("passed", ""),
            }
            for report in latency_reports
        ],
        "session_latency_reports": [
            {
                "path": report.get("_path", ""),
                "status": report.get("status", ""),
                "passed": report.get("passed", ""),
            }
            for report in session_latency_reports
        ],
        "limitations": [
            "Woojer mechanical vibration onset is not measured by these scripts.",
            "WASAPI loopback is diagnostic only for ASIO multichannel runs.",
            "LSL probe arrival timing is a monitoring metric, not physical output timing.",
        ],
        "output_dir": str(output_dir),
    }


def _write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# Internal Validation Summary",
        "",
        f"- Session dir: `{summary.get('session_dir') or 'not provided'}`",
        f"- Run dir: `{summary.get('run_dir') or 'not provided'}`",
        f"- Event count: {summary.get('event_count')}",
        f"- Actual events: {summary.get('actual_event_count')}",
        f"- Planned events: {summary.get('planned_event_count')}",
        f"- Timing anchor fallback count: {summary.get('timing_anchor_fallback_count')}",
        f"- LSL sample count: {summary.get('lsl_sample_count')}",
        "",
        "## Event Types",
        "",
    ]
    for event_type, count in sorted((summary.get("event_type_counts") or {}).items()):
        lines.append(f"- `{event_type}`: {count}")
    lines.extend(
        [
            "",
            "## Integrity",
            "",
            f"- Duplicate local event IDs: {summary.get('duplicate_event_ids') or 'none'}",
            f"- Missing actual event IDs from LSL: {summary.get('lsl_missing_actual_event_ids') or 'not checked/none'}",
            f"- Extra LSL event IDs: {summary.get('lsl_extra_event_ids') or 'not checked/none'}",
            f"- Duplicate LSL event IDs: {summary.get('lsl_duplicate_event_ids') or 'not checked/none'}",
            "",
            "## Mouse To Marker",
            "",
            f"- From events: `{json.dumps(summary.get('mouse_to_marker_from_events'), sort_keys=True)}`",
            f"- From timing QC: `{json.dumps(summary.get('mouse_to_marker_from_timing_qc'), sort_keys=True)}`",
            "",
            "## Latency Reports",
            "",
        ]
    )
    reports = list(summary.get("latency_reports") or []) + list(summary.get("session_latency_reports") or [])
    if reports:
        for report in reports:
            lines.append(f"- `{report.get('path')}`: status={report.get('status')} passed={report.get('passed')}")
    else:
        lines.append("- No latency reports found.")
    lines.extend(["", "## Limitations", ""])
    for limitation in summary.get("limitations") or []:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize internal PPS validation artifacts.")
    parser.add_argument("--session-dir", type=Path, default=None)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--events-csv", type=Path, default=None)
    parser.add_argument("--lsl-probe-csv", type=Path, default=None)
    parser.add_argument("--timing-qc-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    summary = _summarize(args)
    output_dir = Path(summary["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "validation_summary.json"
    markdown_path = output_dir / "validation_summary.md"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _write_markdown(summary, markdown_path)
    print(f"Wrote {json_path}")
    print(f"Wrote {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
