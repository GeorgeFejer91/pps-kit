"""Reconcile local PPS event logs with external LSL probe captures.

This validation answers a narrow but important question: if an external recorder
captures the rich PPSMarkersV2 stream, can it reconstruct the same actual event
set as the local event log?
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any


SCHEMA = "pps-lsl-local-reconciliation.v1"


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _payload(row: dict[str, str]) -> dict[str, Any]:
    try:
        return json.loads(row.get("payload_json", "") or "{}")
    except json.JSONDecodeError:
        return {}


def _event_id(row: dict[str, Any]) -> str:
    return str(row.get("event_id", "")).strip()


def _event_type(row: dict[str, Any]) -> str:
    return str(row.get("event_type", "")).strip()


def _event_id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if str(value).isdigit() else (1, str(value))


def _is_planned(row: dict[str, Any]) -> bool:
    payload = row.get("payload", {}) if isinstance(row.get("payload"), dict) else _payload(row)
    return str(payload.get("planned", "")).strip().lower() in {"1", "true", "yes"}


def _float(value: Any) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return math.nan
    return result if math.isfinite(result) else math.nan


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
        "median_ms": ordered[len(ordered) // 2],
        "p95_ms": ordered[p95_index],
        "max_ms": max(values),
    }


def _as_event_rows(events_csv: Path) -> list[dict[str, Any]]:
    rows = []
    for row in _read_csv(events_csv):
        merged: dict[str, Any] = dict(row)
        merged["payload"] = _payload(row)
        rows.append(merged)
    return rows


def _rows_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for row in rows:
        event_id = _event_id(row)
        if event_id and event_id not in result:
            result[event_id] = row
    return result


def _duplicates(values: list[str]) -> list[str]:
    return sorted({value for value in values if value and values.count(value) > 1}, key=_event_id_sort_key)


def _payload_value(row: dict[str, Any], key: str) -> str:
    payload = row.get("payload", {}) if isinstance(row.get("payload"), dict) else _payload(row)
    value = payload.get(key, row.get(key, ""))
    return "" if value is None else str(value)


def _expected_event_code(row: dict[str, Any]) -> str:
    return _payload_value(row, "event_code") or str(row.get("event_code", "")).strip()


def _expected_trigger_key(row: dict[str, Any]) -> str:
    return _payload_value(row, "trigger_key") or str(row.get("trigger_key", "")).strip()


def _expected_timestamp_quality(row: dict[str, Any]) -> str:
    return _payload_value(row, "timestamp_quality") or "software_log"


def _compare_rich_rows(
    local_events: list[dict[str, Any]],
    rich_rows: list[dict[str, str]],
    marker_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    actual_events = [row for row in local_events if not _is_planned(row)]
    local_by_id = _rows_by_id(actual_events)
    rich_by_id = _rows_by_id(rich_rows)
    marker_by_id = _rows_by_id(marker_rows)

    local_ids = [_event_id(row) for row in actual_events if _event_id(row)]
    rich_ids = [_event_id(row) for row in rich_rows if _event_id(row)]
    missing = sorted(set(local_ids) - set(rich_ids), key=_event_id_sort_key)
    extra = sorted(set(rich_ids) - set(local_ids), key=_event_id_sort_key)
    duplicate_local = _duplicates(local_ids)
    duplicate_rich = _duplicates(rich_ids)

    mismatch_rows: list[dict[str, Any]] = []
    compared = 0
    for event_id in sorted(set(local_ids) & set(rich_ids), key=_event_id_sort_key):
        local = local_by_id[event_id]
        rich = rich_by_id[event_id]
        marker = marker_by_id.get(event_id, {})
        checks = {
            "event_type": (_event_type(local), _event_type(rich)),
            "event_code": (_expected_event_code(local), str(rich.get("event_code", "")).strip()),
            "trigger_key": (_expected_trigger_key(local), str(rich.get("trigger_key", "")).strip()),
            "session_id": (_payload_value(local, "session_id"), str(rich.get("session_id", "")).strip()),
            "participant_id": (_payload_value(local, "participant_id"), str(rich.get("participant_id", "")).strip()),
            "sample_index": (_payload_value(local, "sample_index") or _payload_value(local, "planned_sample_index"), str(rich.get("sample_index", "")).strip()),
            "timestamp_quality": (_expected_timestamp_quality(local), str(rich.get("timestamp_quality", "")).strip()),
        }
        for field, (expected, observed) in checks.items():
            expected = "" if expected is None else str(expected)
            observed = "" if observed is None else str(observed)
            if expected != observed:
                # Empty local sample_index is allowed for non-sample software events.
                if field == "sample_index" and not expected and not observed:
                    continue
                mismatch_rows.append(
                    {
                        "event_id": event_id,
                        "event_type": _event_type(local),
                        "field": field,
                        "expected": expected,
                        "observed": observed,
                    }
                )
        marker_timestamp = str(marker.get("lsl_timestamp", "")).strip()
        probe_timestamp = str(rich.get("sample_lsl_timestamp", "")).strip()
        if marker_timestamp and probe_timestamp:
            delta_ms = (_float(probe_timestamp) - _float(marker_timestamp)) * 1000.0
            if math.isfinite(delta_ms) and abs(delta_ms) > 0.05:
                mismatch_rows.append(
                    {
                        "event_id": event_id,
                        "event_type": _event_type(local),
                        "field": "lsl_timestamp",
                        "expected": marker_timestamp,
                        "observed": probe_timestamp,
                        "delta_ms": f"{delta_ms:.6f}",
                    }
                )
        compared += 1

    arrival_by_quality: dict[str, list[float]] = defaultdict(list)
    arrival_by_type: dict[str, list[float]] = defaultdict(list)
    for row in rich_rows:
        value = _float(row.get("arrival_minus_sample_ms", ""))
        if not math.isfinite(value):
            continue
        arrival_by_quality[str(row.get("timestamp_quality", "") or "unknown")].append(value)
        arrival_by_type[str(row.get("event_type", "") or "unknown")].append(value)

    summary = {
        "actual_local_event_count": len(actual_events),
        "rich_lsl_sample_count": len(rich_rows),
        "compared_event_count": compared,
        "missing_event_ids": missing,
        "extra_event_ids": extra,
        "duplicate_local_event_ids": duplicate_local,
        "duplicate_rich_event_ids": duplicate_rich,
        "field_mismatch_count": len(mismatch_rows),
        "event_type_counts_local": dict(Counter(_event_type(row) for row in actual_events)),
        "event_type_counts_rich": dict(Counter(_event_type(row) for row in rich_rows)),
        "timestamp_quality_counts_rich": dict(Counter(str(row.get("timestamp_quality", "")) for row in rich_rows if row.get("timestamp_quality", ""))),
        "arrival_minus_sample_by_quality_ms": {key: _stats(values) for key, values in sorted(arrival_by_quality.items())},
        "arrival_minus_sample_by_event_type_ms": {key: _stats(values) for key, values in sorted(arrival_by_type.items())},
    }
    return mismatch_rows, summary


def _compare_numeric_rows(
    local_events: list[dict[str, Any]],
    numeric_rows: list[dict[str, str]],
) -> dict[str, Any]:
    if not numeric_rows:
        return {
            "checked": False,
            "numeric_lsl_sample_count": 0,
            "missing_code_counts": {},
            "extra_code_counts": {},
            "passed": True,
        }
    actual_events = [row for row in local_events if not _is_planned(row)]
    expected_codes = Counter(_expected_event_code(row) for row in actual_events if _expected_event_code(row))
    observed_codes = Counter(str(row.get("event_code", "")).strip() for row in numeric_rows if str(row.get("event_code", "")).strip())
    missing = {
        code: expected_codes[code] - observed_codes.get(code, 0)
        for code in sorted(expected_codes)
        if expected_codes[code] > observed_codes.get(code, 0)
    }
    extra = {
        code: observed_codes[code] - expected_codes.get(code, 0)
        for code in sorted(observed_codes)
        if observed_codes[code] > expected_codes.get(code, 0)
    }
    return {
        "checked": True,
        "numeric_lsl_sample_count": len(numeric_rows),
        "expected_code_counts": dict(expected_codes),
        "observed_code_counts": dict(observed_codes),
        "missing_code_counts": missing,
        "extra_code_counts": extra,
        "passed": not missing and not extra and len(numeric_rows) == len(actual_events),
    }


def reconcile(
    *,
    events_csv: Path,
    rich_lsl_probe_csv: Path,
    output_dir: Path,
    lsl_markers_csv: Path | None = None,
    numeric_lsl_probe_csv: Path | None = None,
) -> dict[str, Any]:
    local_events = _as_event_rows(events_csv)
    rich_rows = [dict(row) for row in _read_csv(rich_lsl_probe_csv)]
    marker_rows = [dict(row) for row in _read_csv(lsl_markers_csv)] if lsl_markers_csv else []
    numeric_rows = [dict(row) for row in _read_csv(numeric_lsl_probe_csv)] if numeric_lsl_probe_csv else []

    mismatch_rows, rich_summary = _compare_rich_rows(local_events, rich_rows, marker_rows)
    numeric_summary = _compare_numeric_rows(local_events, numeric_rows)
    pass_checks = {
        "no_missing_rich_event_ids": not rich_summary["missing_event_ids"],
        "no_extra_rich_event_ids": not rich_summary["extra_event_ids"],
        "no_duplicate_local_event_ids": not rich_summary["duplicate_local_event_ids"],
        "no_duplicate_rich_event_ids": not rich_summary["duplicate_rich_event_ids"],
        "no_field_mismatches": rich_summary["field_mismatch_count"] == 0,
        "numeric_codes_match_when_checked": bool(numeric_summary["passed"]),
    }
    report = {
        "schema": SCHEMA,
        "events_csv": str(events_csv),
        "rich_lsl_probe_csv": str(rich_lsl_probe_csv),
        "lsl_markers_csv": str(lsl_markers_csv or ""),
        "numeric_lsl_probe_csv": str(numeric_lsl_probe_csv or ""),
        "rich": rich_summary,
        "numeric": numeric_summary,
        "pass_checks": pass_checks,
        "passed": all(pass_checks.values()),
        "limitations": [
            "This reconciles marker metadata and LSL probe timing, not physical signal arrival.",
            "The numeric trigger stream cannot reconstruct event identity alone; it verifies trigger-code counts and relies on trigger_dictionary.json for decoding.",
            "Negative arrival-minus-sample values are expected for callback-derived future DAC timestamps when markers are pushed before the sample reaches the output.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "lsl_local_reconciliation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_mismatches(output_dir / "lsl_local_reconciliation_mismatches.csv", mismatch_rows)
    _write_markdown(output_dir / "lsl_local_reconciliation_report.md", report)
    return report


def _write_mismatches(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = ["event_id", "event_type", "field", "expected", "observed", "delta_ms"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    rich = report.get("rich", {})
    numeric = report.get("numeric", {})
    lines = [
        "# LSL Local Reconciliation",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Local actual events: {rich.get('actual_local_event_count')}",
        f"- Rich LSL samples: {rich.get('rich_lsl_sample_count')}",
        f"- Compared events: {rich.get('compared_event_count')}",
        f"- Missing rich event IDs: `{rich.get('missing_event_ids') or []}`",
        f"- Extra rich event IDs: `{rich.get('extra_event_ids') or []}`",
        f"- Field mismatches: {rich.get('field_mismatch_count')}",
        f"- Numeric stream checked: `{numeric.get('checked')}`",
        f"- Numeric samples: {numeric.get('numeric_lsl_sample_count')}",
        f"- Numeric missing code counts: `{numeric.get('missing_code_counts') or {}}`",
        f"- Numeric extra code counts: `{numeric.get('extra_code_counts') or {}}`",
        "",
        "## Arrival Timing",
        "",
    ]
    for quality, stats in (rich.get("arrival_minus_sample_by_quality_ms") or {}).items():
        lines.append(f"- `{quality}`: `{json.dumps(stats, sort_keys=True)}`")
    lines.extend(["", "## Checks", ""])
    for name, passed in sorted((report.get("pass_checks") or {}).items()):
        lines.append(f"- `{name}`: {passed}")
    lines.extend(["", "## Limitations", ""])
    for limitation in report.get("limitations") or []:
        lines.append(f"- {limitation}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile PPS local events with external LSL probe captures.")
    parser.add_argument("--events-csv", type=Path, required=True)
    parser.add_argument("--rich-lsl-probe-csv", type=Path, required=True)
    parser.add_argument("--lsl-markers-csv", type=Path, default=None)
    parser.add_argument("--numeric-lsl-probe-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    report = reconcile(
        events_csv=args.events_csv,
        rich_lsl_probe_csv=args.rich_lsl_probe_csv,
        lsl_markers_csv=args.lsl_markers_csv,
        numeric_lsl_probe_csv=args.numeric_lsl_probe_csv,
        output_dir=args.output_dir,
    )
    print(f"Wrote {args.output_dir / 'lsl_local_reconciliation_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
