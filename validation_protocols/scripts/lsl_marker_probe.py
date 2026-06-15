"""External LSL marker probe for internal PPS validation runs."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import sys
import time
from pathlib import Path
from typing import Any


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"lsl_probe_{stamp}"


def _payload_value(payload_json: str, key: str) -> Any:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return ""
    return payload.get(key, "")


def parse_marker_sample(sample: list[Any]) -> dict[str, Any]:
    """Normalize current rich markers and older compact markers for comparison."""
    values = ["" if item is None else str(item) for item in sample]
    normalized = {
        "marker_version": "",
        "event_id": "",
        "event_type": "",
        "event_code": "",
        "trigger_key": "",
        "session_id": "",
        "participant_id": "",
        "block_index": "",
        "trial_uid": "",
        "sample_index": "",
        "timestamp_quality": "",
        "payload_json": "",
        "raw_sample_json": json.dumps(values, ensure_ascii=True),
    }

    if len(values) >= 12:
        normalized.update(
            {
                "marker_version": values[0],
                "event_id": values[1],
                "event_type": values[2],
                "event_code": values[3],
                "trigger_key": values[4],
                "session_id": values[5],
                "participant_id": values[6],
                "block_index": values[7],
                "trial_uid": values[8],
                "sample_index": values[9],
                "timestamp_quality": values[10],
                "payload_json": values[11],
            }
        )
        return normalized

    if len(values) >= 3:
        normalized.update(
            {
                "event_type": values[0],
                "event_id": values[1],
                "payload_json": values[2],
            }
        )
        for key in ("session_id", "participant_id", "block_number", "block_index", "trial_uid", "sample_index", "timestamp_quality"):
            value = _payload_value(values[2], key)
            if value != "":
                normalized["block_index" if key == "block_number" else key] = value
        return normalized

    if len(values) == 1:
        normalized["event_code"] = values[0]
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record PPS LSL marker samples for internal validation.")
    parser.add_argument("--stream-name", default="PPSMarkersV2")
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--resolve-timeout-s", type=float, default=10.0)
    parser.add_argument("--pull-timeout-s", type=float, default=0.1)
    parser.add_argument("--expected-count", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        from pylsl import StreamInlet, local_clock, resolve_byprop  # type: ignore
    except Exception as exc:
        print(f"pylsl is required for this probe: {exc}", file=sys.stderr)
        return 2

    output_dir = args.output_dir or _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "lsl_marker_probe.csv"
    summary_path = output_dir / "lsl_marker_probe_summary.json"

    print(f"Resolving LSL stream name={args.stream_name!r}...")
    streams = resolve_byprop("name", args.stream_name, timeout=args.resolve_timeout_s)
    if not streams:
        summary = {
            "schema": "pps-lsl-marker-probe-summary.v1",
            "stream_name": args.stream_name,
            "resolved": False,
            "sample_count": 0,
            "output_csv": str(csv_path),
        }
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"No LSL stream named {args.stream_name!r} was resolved.", file=sys.stderr)
        return 1

    inlet = StreamInlet(streams[0])
    rows: list[dict[str, Any]] = []
    start_clock = local_clock()
    end_clock = start_clock + max(0.0, args.duration_s)
    print(f"Recording LSL markers for {args.duration_s:.1f} s into {csv_path}")

    while local_clock() < end_clock:
        sample, sample_timestamp = inlet.pull_sample(timeout=args.pull_timeout_s)
        arrival_clock = local_clock()
        if sample is None:
            continue
        marker = parse_marker_sample(sample)
        rows.append(
            {
                "arrival_lsl_clock": f"{arrival_clock:.9f}",
                "sample_lsl_timestamp": f"{float(sample_timestamp):.9f}" if sample_timestamp is not None else "",
                "arrival_minus_sample_ms": (
                    f"{(arrival_clock - float(sample_timestamp)) * 1000.0:.3f}"
                    if sample_timestamp is not None
                    else ""
                ),
                **marker,
            }
        )
        if args.expected_count and len(rows) >= args.expected_count:
            break

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fieldnames = [
            "arrival_lsl_clock",
            "sample_lsl_timestamp",
            "arrival_minus_sample_ms",
            "marker_version",
            "event_type",
            "event_id",
            "event_code",
            "trigger_key",
            "session_id",
            "participant_id",
            "block_index",
            "trial_uid",
            "sample_index",
            "timestamp_quality",
            "payload_json",
            "raw_sample_json",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    event_ids = [row["event_id"] for row in rows if row.get("event_id")]
    duplicate_event_ids = sorted({event_id for event_id in event_ids if event_ids.count(event_id) > 1})
    summary = {
        "schema": "pps-lsl-marker-probe-summary.v1",
        "stream_name": args.stream_name,
        "resolved": True,
        "sample_count": len(rows),
        "duplicate_event_ids": duplicate_event_ids,
        "event_type_counts": dict(Counter(row.get("event_type", "") for row in rows)),
        "timestamp_quality_counts": dict(Counter(row.get("timestamp_quality", "") for row in rows if row.get("timestamp_quality"))),
        "expected_count": args.expected_count,
        "duration_s": args.duration_s,
        "output_csv": str(csv_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Recorded {len(rows)} LSL samples.")
    return 0 if not args.expected_count or len(rows) >= args.expected_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
