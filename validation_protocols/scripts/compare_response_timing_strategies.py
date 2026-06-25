"""Compare local mouse timing, LSL probe timing, and response-marker timing.

This is an analysis-only validation helper. It does not inject clicks or play
audio. It reads an existing mouse/response stress run and asks how the timing
story changes if the response is reconstructed from local logs, LSL sample
timestamps, or LSL arrival times.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any


SCHEMA = "pps-response-timing-strategy-comparison.v1"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(str(row.get("payload_json", "") or "{}"))
    except json.JSONDecodeError:
        return {}


def _float(value: Any) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


def _event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id", "")).strip()


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
        "median_ms": finite[len(finite) // 2] if len(finite) % 2 else (finite[len(finite) // 2 - 1] + finite[len(finite) // 2]) / 2.0,
        "p95_ms": finite[p95_index],
        "max_ms": max(finite),
    }


def _event_rows(events_csv: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(events_csv):
        merged: dict[str, Any] = dict(row)
        merged["payload"] = _payload(row)
        rows.append(merged)
    return rows


def _by_event_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = _event_id(row)
        if event_id and event_id not in by_id:
            by_id[event_id] = row
    return by_id


def _click_index(row: dict[str, Any]) -> str:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else _payload(row)
    value = payload.get("click_index", row.get("click_index", ""))
    return "" if value is None else str(value)


def _planned_delay_ms(mouse: dict[str, Any], marker: dict[str, Any] | None) -> float:
    if marker is None:
        return math.nan
    payload = marker.get("payload") if isinstance(marker.get("payload"), dict) else _payload(marker)
    return _float(payload.get("planned_marker_delay_ms", ""))


def compare_strategies(
    *,
    events_csv: Path,
    rich_lsl_probe_csv: Path,
    output_dir: Path,
    timing_qc_csv: Path | None = None,
) -> dict[str, Any]:
    local_events = _event_rows(events_csv)
    rich_rows = [dict(row) for row in _read_csv(rich_lsl_probe_csv)]
    rich_by_id = _by_event_id(rich_rows)
    mouse_events = [row for row in local_events if row.get("event_type") == "mouse_click"]
    marker_events = [row for row in local_events if row.get("event_type") == "response_marker_start"]
    marker_by_mouse: dict[str, dict[str, Any]] = {}
    for marker in marker_events:
        payload = marker.get("payload") if isinstance(marker.get("payload"), dict) else _payload(marker)
        mouse_id = str(payload.get("mouse_event_id", "")).strip()
        if mouse_id and mouse_id not in marker_by_mouse:
            marker_by_mouse[mouse_id] = marker

    rows: list[dict[str, Any]] = []
    for mouse in mouse_events:
        mouse_id = _event_id(mouse)
        marker = marker_by_mouse.get(mouse_id)
        mouse_lsl = rich_by_id.get(mouse_id, {})
        marker_lsl = rich_by_id.get(_event_id(marker or {}), {}) if marker else {}
        mouse_local = _float(mouse.get("monotonic_time"))
        marker_local = _float((marker or {}).get("monotonic_time", ""))
        mouse_lsl_sample = _float(mouse_lsl.get("sample_lsl_timestamp", ""))
        mouse_lsl_arrival = _float(mouse_lsl.get("arrival_lsl_clock", ""))
        marker_lsl_sample = _float(marker_lsl.get("sample_lsl_timestamp", ""))
        marker_lsl_arrival = _float(marker_lsl.get("arrival_lsl_clock", ""))
        planned_ms = _planned_delay_ms(mouse, marker)
        local_marker_minus_mouse = (marker_local - mouse_local) * 1000.0 if math.isfinite(marker_local) and math.isfinite(mouse_local) else math.nan
        rows.append(
            {
                "mouse_event_id": mouse_id,
                "response_marker_event_id": _event_id(marker or {}),
                "click_index": _click_index(mouse),
                "planned_marker_delay_ms": planned_ms,
                "local_marker_minus_mouse_ms": local_marker_minus_mouse,
                "local_marker_delay_error_ms": local_marker_minus_mouse - planned_ms if math.isfinite(local_marker_minus_mouse) and math.isfinite(planned_ms) else math.nan,
                "lsl_mouse_sample_minus_local_mouse_ms": (mouse_lsl_sample - mouse_local) * 1000.0 if math.isfinite(mouse_lsl_sample) and math.isfinite(mouse_local) else math.nan,
                "lsl_mouse_arrival_minus_local_mouse_ms": (mouse_lsl_arrival - mouse_local) * 1000.0 if math.isfinite(mouse_lsl_arrival) and math.isfinite(mouse_local) else math.nan,
                "lsl_marker_sample_minus_local_mouse_ms": (marker_lsl_sample - mouse_local) * 1000.0 if math.isfinite(marker_lsl_sample) and math.isfinite(mouse_local) else math.nan,
                "lsl_marker_arrival_minus_local_mouse_ms": (marker_lsl_arrival - mouse_local) * 1000.0 if math.isfinite(marker_lsl_arrival) and math.isfinite(mouse_local) else math.nan,
                "lsl_marker_sample_minus_lsl_mouse_sample_ms": (marker_lsl_sample - mouse_lsl_sample) * 1000.0 if math.isfinite(marker_lsl_sample) and math.isfinite(mouse_lsl_sample) else math.nan,
                "lsl_marker_arrival_minus_lsl_mouse_arrival_ms": (marker_lsl_arrival - mouse_lsl_arrival) * 1000.0 if math.isfinite(marker_lsl_arrival) and math.isfinite(mouse_lsl_arrival) else math.nan,
                "mouse_lsl_arrival_minus_sample_ms": _float(mouse_lsl.get("arrival_minus_sample_ms", "")),
                "marker_lsl_arrival_minus_sample_ms": _float(marker_lsl.get("arrival_minus_sample_ms", "")),
            }
        )

    metric_names = [
        "local_marker_minus_mouse_ms",
        "local_marker_delay_error_ms",
        "lsl_mouse_sample_minus_local_mouse_ms",
        "lsl_mouse_arrival_minus_local_mouse_ms",
        "lsl_marker_sample_minus_local_mouse_ms",
        "lsl_marker_arrival_minus_local_mouse_ms",
        "lsl_marker_sample_minus_lsl_mouse_sample_ms",
        "lsl_marker_arrival_minus_lsl_mouse_arrival_ms",
        "mouse_lsl_arrival_minus_sample_ms",
        "marker_lsl_arrival_minus_sample_ms",
    ]
    metrics = {name: _stats([_float(row.get(name)) for row in rows]) for name in metric_names}
    missing_mouse_lsl = [row["mouse_event_id"] for row in rows if not math.isfinite(_float(row.get("lsl_mouse_sample_minus_local_mouse_ms")))]
    missing_marker_lsl = [row["response_marker_event_id"] for row in rows if row["response_marker_event_id"] and not math.isfinite(_float(row.get("lsl_marker_sample_minus_local_mouse_ms")))]
    pass_checks = {
        "all_local_clicks_have_response_marker": len(rows) == len(mouse_events) and all(row["response_marker_event_id"] for row in rows),
        "all_mouse_clicks_seen_in_rich_lsl": not missing_mouse_lsl,
        "all_response_markers_seen_in_rich_lsl": not missing_marker_lsl,
        "local_marker_delay_error_within_1_ms": max([abs(_float(row.get("local_marker_delay_error_ms"))) for row in rows if math.isfinite(_float(row.get("local_marker_delay_error_ms")))], default=0.0) <= 1.0,
    }
    report = {
        "schema": SCHEMA,
        "events_csv": str(events_csv),
        "timing_qc_csv": str(timing_qc_csv or ""),
        "rich_lsl_probe_csv": str(rich_lsl_probe_csv),
        "local_mouse_click_count": len(mouse_events),
        "local_response_marker_count": len(marker_events),
        "paired_click_marker_count": len(rows),
        "rich_mouse_click_count": len([row for row in rich_rows if row.get("event_type") == "mouse_click"]),
        "rich_response_marker_count": len([row for row in rich_rows if row.get("event_type") == "response_marker_start"]),
        "metrics": metrics,
        "missing_mouse_lsl_event_ids": missing_mouse_lsl,
        "missing_response_marker_lsl_event_ids": missing_marker_lsl,
        "pass_checks": pass_checks,
        "passed": all(pass_checks.values()),
        "interpretation": [
            "Local mouse-click logging is the primary response-time source because it records the input event immediately in the runner process.",
            "Rich LSL mouse-click sample timestamps closely follow local mouse times, but external LSL arrival times include network/client scheduling delay.",
            "Response-marker LSL sample timestamps represent callback/DAC-timed marker onset. Their arrival can precede that timestamp because the marker is pushed with an explicit future sample time.",
            "Physical tactile-channel loopback is still required to prove that the response-marker pulse actually reached the audio interface output.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "response_timing_strategy_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_rows_csv(output_dir / "response_timing_strategy_pairs.csv", rows)
    _write_markdown(output_dir / "response_timing_strategy_comparison.md", report)
    return report


def _write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Response Timing Strategy Comparison",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Local mouse clicks: {report.get('local_mouse_click_count')}",
        f"- Local response markers: {report.get('local_response_marker_count')}",
        f"- Paired click/marker rows: {report.get('paired_click_marker_count')}",
        f"- Rich LSL mouse clicks: {report.get('rich_mouse_click_count')}",
        f"- Rich LSL response markers: {report.get('rich_response_marker_count')}",
        "",
        "## Metrics",
        "",
    ]
    for name, stats in (report.get("metrics") or {}).items():
        lines.append(f"- `{name}`: `{json.dumps(stats, sort_keys=True)}`")
    lines.extend(["", "## Checks", ""])
    for name, passed in sorted((report.get("pass_checks") or {}).items()):
        lines.append(f"- `{name}`: {passed}")
    lines.extend(["", "## Interpretation", ""])
    for note in report.get("interpretation") or []:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare local, LSL, and response-marker timing strategies.")
    parser.add_argument("--events-csv", type=Path, required=True)
    parser.add_argument("--rich-lsl-probe-csv", type=Path, required=True)
    parser.add_argument("--timing-qc-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare_strategies(
        events_csv=args.events_csv,
        timing_qc_csv=args.timing_qc_csv,
        rich_lsl_probe_csv=args.rich_lsl_probe_csv,
        output_dir=args.output_dir,
    )
    print(f"Wrote {args.output_dir / 'response_timing_strategy_comparison.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
