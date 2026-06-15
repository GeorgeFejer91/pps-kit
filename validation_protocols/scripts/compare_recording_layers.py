"""Compare PPS recording layers against a physical loopback reference.

This internal validation compares three simultaneous records from one actual
block run:

- physical electrical loopback WAV: temporary validation reference
- local digital output evidence WAV: exact output buffers written by the runner
- callback-derived LSL marker mirrors / optional external LSL captures

It does not claim Woojer mechanical onset.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from compare_response_marker_loopback import compare_loopback as compare_response_marker_loopback  # noqa: E402
except Exception:  # pragma: no cover - script can still compare non-marker layers
    compare_response_marker_loopback = None


SCHEMA = "pps-recording-layer-alignment.v1"
MAX_LSL_TIMESTAMP_P95_ERROR_MS = 1.0
MAX_LEFT_RIGHT_SKEW_MS = 1.0
MAX_TACTILE_AUDIO_SKEW_MS = 2.0


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"recording_layer_alignment_{stamp}"


def _read_csv(path: Path | None) -> list[dict[str, str]]:
    if path is None or not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(str(row.get("payload_json", "") or "{}"))
    except json.JSONDecodeError:
        return {}


def _float(value: Any, default: float = math.nan) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _stats_ms(values: list[float]) -> dict[str, Any]:
    finite = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not finite:
        return {"count": 0}
    p95_index = min(len(finite) - 1, int(math.ceil(len(finite) * 0.95)) - 1)
    return {
        "count": len(finite),
        "mean_ms": statistics.fmean(finite),
        "sd_ms": statistics.stdev(finite) if len(finite) > 1 else 0.0,
        "median_ms": statistics.median(finite),
        "p95_ms": finite[p95_index],
        "min_ms": min(finite),
        "max_ms": max(finite),
    }


def _normalize(values: np.ndarray) -> np.ndarray:
    data = np.asarray(values, dtype=np.float64)
    if data.size == 0:
        return data
    data = data - float(np.mean(data))
    norm = float(np.linalg.norm(data))
    return data / norm if norm > 0 else data


def _lag_by_correlation(reference: np.ndarray, observed: np.ndarray, *, sample_rate: int, max_lag_ms: float) -> tuple[int, float]:
    ref = _normalize(reference)
    obs = _normalize(observed)
    if ref.size == 0 or obs.size == 0:
        return 0, math.nan
    corr = signal.correlate(obs, ref, mode="full", method="fft")
    lags = signal.correlation_lags(obs.size, ref.size, mode="full")
    max_lag = int(round(max_lag_ms / 1000.0 * sample_rate))
    mask = np.abs(lags) <= max_lag
    if not np.any(mask):
        return 0, math.nan
    masked_corr = corr[mask]
    masked_lags = lags[mask]
    best = int(np.argmax(np.abs(masked_corr)))
    return int(masked_lags[best]), float(masked_corr[best])


def compare_audio_layers(
    *,
    physical_wav: Path,
    digital_wav: Path,
    output_dir: Path,
    max_lag_ms: float = 250.0,
) -> dict[str, Any]:
    physical, physical_rate = sf.read(physical_wav, dtype="float32", always_2d=True)
    digital, digital_rate = sf.read(digital_wav, dtype="float32", always_2d=True)
    if int(physical_rate) != int(digital_rate):
        raise ValueError(f"Sample-rate mismatch: physical={physical_rate}, digital={digital_rate}")
    sample_rate = int(physical_rate)
    channel_count = min(int(physical.shape[1]), int(digital.shape[1]))
    rows: list[dict[str, Any]] = []
    lags_ms: dict[int, float] = {}
    for channel in range(channel_count):
        lag_samples, corr = _lag_by_correlation(
            digital[:, channel],
            physical[:, channel],
            sample_rate=sample_rate,
            max_lag_ms=max_lag_ms,
        )
        lag_ms = lag_samples / float(sample_rate) * 1000.0
        lags_ms[channel] = lag_ms
        rows.append(
            {
                "channel": channel + 1,
                "lag_samples_physical_minus_digital": lag_samples,
                "lag_ms_physical_minus_digital": lag_ms,
                "correlation": corr,
                "digital_peak": float(np.max(np.abs(digital[:, channel]))) if digital.size else 0.0,
                "physical_peak": float(np.max(np.abs(physical[:, channel]))) if physical.size else 0.0,
            }
        )
    skew = {}
    if 0 in lags_ms and 1 in lags_ms:
        skew["right_minus_left_ms"] = lags_ms[1] - lags_ms[0]
    if 0 in lags_ms and 1 in lags_ms and 2 in lags_ms:
        skew["tactile_minus_audio_mean_ms"] = lags_ms[2] - ((lags_ms[0] + lags_ms[1]) / 2.0)
    metadata = _read_json(digital_wav.with_name(digital_wav.stem + ".output_evidence.json"))
    digital_peaks = np.max(np.abs(digital), axis=0).astype(float).tolist() if digital.size else []
    physical_peaks = np.max(np.abs(physical), axis=0).astype(float).tolist() if physical.size else []
    _write_csv(output_dir / "recording_layer_audio_alignment.csv", rows)
    return {
        "physical_wav": str(physical_wav),
        "digital_wav": str(digital_wav),
        "sample_rate": sample_rate,
        "physical_shape": list(physical.shape),
        "digital_shape": list(digital.shape),
        "channel_alignment": rows,
        "physical_minus_digital_latency_ms": _stats_ms([row["lag_ms_physical_minus_digital"] for row in rows]),
        "interchannel_skew": skew,
        "digital_peak_by_channel": digital_peaks,
        "physical_peak_by_channel": physical_peaks,
        "digital_metadata": metadata,
    }


def compare_internal_lsl(*, events_csv: Path, lsl_markers_csv: Path, output_dir: Path) -> dict[str, Any]:
    events = _read_csv(events_csv)
    markers = _read_csv(lsl_markers_csv)
    event_ids = [str(row.get("event_id", "")).strip() for row in events if str(row.get("event_id", "")).strip()]
    marker_ids = [str(row.get("event_id", "")).strip() for row in markers if str(row.get("event_id", "")).strip()]
    event_set = set(event_ids)
    marker_set = set(marker_ids)
    duplicate_events = sorted({event_id for event_id in event_ids if event_ids.count(event_id) > 1})
    duplicate_markers = sorted({event_id for event_id in marker_ids if marker_ids.count(event_id) > 1})
    missing = sorted(event_set - marker_set, key=lambda item: int(item) if item.isdigit() else item)
    extra = sorted(marker_set - event_set, key=lambda item: int(item) if item.isdigit() else item)
    marker_by_block: dict[str, dict[str, str]] = {}
    for marker in markers:
        if marker.get("event_type") == "audio_sample_zero":
            block = str(marker.get("block_index", "") or _payload(marker).get("block_index") or _payload(marker).get("block_number") or "")
            if block and block not in marker_by_block:
                marker_by_block[block] = marker
    timestamp_errors: list[float] = []
    rows: list[dict[str, Any]] = []
    for marker in markers:
        if marker.get("event_type") not in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end", "response_marker_start"}:
            continue
        payload = _payload(marker)
        block = str(marker.get("block_index", "") or payload.get("block_index") or payload.get("block_number") or "")
        zero = marker_by_block.get(block)
        if not zero:
            continue
        sample_index = _float(marker.get("sample_index") or payload.get("sample_index"))
        zero_sample = _float(zero.get("sample_index") or _payload(zero).get("sample_index"), default=0.0)
        sample_rate = _float(payload.get("sample_rate"), default=_float(_payload(zero).get("sample_rate")))
        marker_lsl = _float(marker.get("lsl_timestamp"))
        zero_lsl = _float(zero.get("lsl_timestamp"))
        if not all(math.isfinite(value) for value in (sample_index, zero_sample, sample_rate, marker_lsl, zero_lsl)) or sample_rate <= 0:
            continue
        expected_lsl = zero_lsl + ((sample_index - zero_sample) / sample_rate)
        error_ms = (marker_lsl - expected_lsl) * 1000.0
        timestamp_errors.append(error_ms)
        rows.append(
            {
                "event_id": marker.get("event_id", ""),
                "event_type": marker.get("event_type", ""),
                "block_index": block,
                "sample_index": sample_index,
                "sample_rate": sample_rate,
                "lsl_timestamp": marker_lsl,
                "expected_lsl_from_audio_sample_zero": expected_lsl,
                "lsl_timestamp_error_ms": error_ms,
                "timestamp_quality": marker.get("timestamp_quality", ""),
            }
        )
    _write_csv(output_dir / "recording_layer_lsl_timestamp_errors.csv", rows)
    return {
        "events_csv": str(events_csv),
        "lsl_markers_csv": str(lsl_markers_csv),
        "event_count": len(events),
        "marker_count": len(markers),
        "missing_marker_event_ids": missing,
        "extra_marker_event_ids": extra,
        "duplicate_event_ids": duplicate_events,
        "duplicate_marker_event_ids": duplicate_markers,
        "event_type_counts_events": dict(Counter(row.get("event_type", "") for row in events)),
        "event_type_counts_markers": dict(Counter(row.get("event_type", "") for row in markers)),
        "lsl_timestamp_error_ms": _stats_ms(timestamp_errors),
    }


def compare_external_lsl(
    *,
    internal_markers_csv: Path,
    rich_lsl_csv: Path | None,
    numeric_lsl_csv: Path | None,
) -> dict[str, Any]:
    internal = _read_csv(internal_markers_csv)
    rich = _read_csv(rich_lsl_csv)
    numeric = _read_csv(numeric_lsl_csv)
    if not rich and not numeric:
        return {"checked": False, "passed": True}
    internal_pushed = [row for row in internal if str(row.get("pushed_to_lsl", "")).lower() in {"true", "1", "yes"}]
    expected_ids = [str(row.get("event_id", "")) for row in internal_pushed if str(row.get("event_id", ""))]
    rich_ids = [str(row.get("event_id", "")) for row in rich if str(row.get("event_id", ""))]
    missing_ids = sorted(set(expected_ids) - set(rich_ids), key=lambda item: int(item) if item.isdigit() else item)
    extra_ids = sorted(set(rich_ids) - set(expected_ids), key=lambda item: int(item) if item.isdigit() else item)
    expected_codes = Counter(str(row.get("event_code", "")) for row in internal_pushed if str(row.get("event_code", "")))
    observed_codes = Counter(str(row.get("event_code", "")) for row in numeric if str(row.get("event_code", "")))
    missing_codes = {code: expected_codes[code] - observed_codes.get(code, 0) for code in expected_codes if expected_codes[code] > observed_codes.get(code, 0)}
    extra_codes = {code: observed_codes[code] - expected_codes.get(code, 0) for code in observed_codes if observed_codes[code] > expected_codes.get(code, 0)}
    arrival_minus_sample = [_float(row.get("arrival_minus_sample_ms")) for row in rich if math.isfinite(_float(row.get("arrival_minus_sample_ms")))]
    return {
        "checked": True,
        "passed": not missing_ids and not extra_ids and not missing_codes and not extra_codes,
        "expected_internal_pushed_marker_count": len(internal_pushed),
        "rich_lsl_count": len(rich),
        "numeric_lsl_count": len(numeric),
        "missing_rich_event_ids": missing_ids,
        "extra_rich_event_ids": extra_ids,
        "missing_numeric_code_counts": missing_codes,
        "extra_numeric_code_counts": extra_codes,
        "arrival_minus_sample_ms": _stats_ms(arrival_minus_sample),
    }


def compare_layers(
    *,
    physical_wav: Path,
    digital_wav: Path,
    events_csv: Path,
    lsl_markers_csv: Path,
    output_dir: Path,
    rich_lsl_csv: Path | None = None,
    numeric_lsl_csv: Path | None = None,
    tactile_channel: int = 3,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio = compare_audio_layers(physical_wav=physical_wav, digital_wav=digital_wav, output_dir=output_dir)
    internal_lsl = compare_internal_lsl(events_csv=events_csv, lsl_markers_csv=lsl_markers_csv, output_dir=output_dir)
    external_lsl = compare_external_lsl(
        internal_markers_csv=lsl_markers_csv,
        rich_lsl_csv=rich_lsl_csv,
        numeric_lsl_csv=numeric_lsl_csv,
    )
    response_marker = {"checked": False, "passed": True}
    if compare_response_marker_loopback is not None:
        try:
            response_marker = compare_response_marker_loopback(
                events_csv=events_csv,
                recordings=[physical_wav],
                output_dir=output_dir / "response_marker_loopback",
                tactile_channel_1based=tactile_channel,
            )
            response_marker["checked"] = True
        except Exception as exc:
            response_marker = {"checked": True, "passed": False, "error": str(exc)}

    lsl_error = internal_lsl.get("lsl_timestamp_error_ms") or {}
    digital_metadata = audio.get("digital_metadata") or {}
    skew = audio.get("interchannel_skew") or {}
    pass_checks = {
        "internal_lsl_has_no_missing_duplicate_or_extra_event_ids": not internal_lsl["missing_marker_event_ids"]
        and not internal_lsl["extra_marker_event_ids"]
        and not internal_lsl["duplicate_event_ids"]
        and not internal_lsl["duplicate_marker_event_ids"],
        "external_lsl_matches_when_supplied": bool(external_lsl.get("passed")),
        "digital_evidence_has_no_dropped_buffers": int(digital_metadata.get("dropped_buffer_count") or 0) == 0,
        "digital_evidence_not_clipped": not digital_metadata.get("clipped_channels_1based"),
        "left_right_skew_within_1_ms": abs(float(skew.get("right_minus_left_ms", 0.0))) <= MAX_LEFT_RIGHT_SKEW_MS,
        "tactile_audio_skew_within_2_ms": abs(float(skew.get("tactile_minus_audio_mean_ms", 0.0))) <= MAX_TACTILE_AUDIO_SKEW_MS,
        "lsl_timestamp_p95_error_within_1_ms": float(lsl_error.get("p95_ms", 0.0) or 0.0) <= MAX_LSL_TIMESTAMP_P95_ERROR_MS,
        "response_marker_loopback_passes_when_checked": bool(response_marker.get("passed")),
    }
    report = {
        "schema": SCHEMA,
        "passed": all(pass_checks.values()),
        "output_dir": str(output_dir),
        "audio": audio,
        "internal_lsl": internal_lsl,
        "external_lsl": external_lsl,
        "response_marker_loopback": response_marker,
        "pass_checks": pass_checks,
        "interpretation": [
            "Physical loopback is the temporary validation reference for electrical signal arrival.",
            "The digital evidence WAV is the runner's local copy of the exact output buffers, not a physical measurement.",
            "Internal LSL marker mirrors are written from callback-derived marker records, not reconstructed from the planned CSV after the run.",
            "External LSL/XDF arrival timing is monitoring latency; explicit marker timestamps are the event timing source.",
            "Woojer mechanical vibration onset is not measured by this protocol.",
        ],
    }
    (output_dir / "recording_layer_alignment_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown(output_dir / "recording_layer_alignment_report.md", report)
    return report


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    audio = report.get("audio") or {}
    internal_lsl = report.get("internal_lsl") or {}
    external_lsl = report.get("external_lsl") or {}
    lines = [
        "# Recording Layer Alignment",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Physical minus digital latency ms: `{json.dumps(audio.get('physical_minus_digital_latency_ms') or {}, sort_keys=True)}`",
        f"- Interchannel skew: `{json.dumps(audio.get('interchannel_skew') or {}, sort_keys=True)}`",
        f"- Internal LSL timestamp error ms: `{json.dumps(internal_lsl.get('lsl_timestamp_error_ms') or {}, sort_keys=True)}`",
        f"- External LSL checked: `{external_lsl.get('checked')}`",
        f"- External LSL arrival-minus-sample ms: `{json.dumps(external_lsl.get('arrival_minus_sample_ms') or {}, sort_keys=True)}`",
        "",
        "## Checks",
        "",
    ]
    for name, passed in sorted((report.get("pass_checks") or {}).items()):
        lines.append(f"- `{name}`: {passed}")
    lines.extend(["", "## Interpretation", ""])
    for note in report.get("interpretation") or []:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _session_default_paths(session_dir: Path) -> dict[str, Path | None]:
    recordings = list(dict.fromkeys([*sorted(session_dir.glob("*.wav")), *sorted((session_dir / "recordings").glob("*.wav"))]))
    digital = next((path for path in recordings if "audio_evidence" in path.name.lower() or "output" in path.name.lower()), None)
    physical = next((path for path in recordings if "physical" in path.name.lower()), None)
    if physical is None:
        physical = next((path for path in recordings if "loopback" in path.name.lower() and path != digital), None)
    return {
        "events_csv": session_dir / "events.csv",
        "lsl_markers_csv": session_dir / "lsl_markers.csv",
        "digital_wav": digital,
        "physical_wav": physical,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare physical loopback, digital output evidence, and LSL marker records.")
    parser.add_argument("--session-dir", type=Path, default=None)
    parser.add_argument("--physical-loopback-wav", type=Path, default=None)
    parser.add_argument("--digital-evidence-wav", type=Path, default=None)
    parser.add_argument("--events-csv", type=Path, default=None)
    parser.add_argument("--lsl-markers-csv", type=Path, default=None)
    parser.add_argument("--rich-lsl-csv", type=Path, default=None)
    parser.add_argument("--numeric-lsl-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--tactile-channel", type=int, default=3)
    args = parser.parse_args(argv)

    defaults: dict[str, Path | None] = {}
    if args.session_dir:
        defaults = _session_default_paths(args.session_dir)
    physical = args.physical_loopback_wav or defaults.get("physical_wav")
    digital = args.digital_evidence_wav or defaults.get("digital_wav")
    events = args.events_csv or defaults.get("events_csv")
    lsl_markers = args.lsl_markers_csv or defaults.get("lsl_markers_csv")
    if not physical or not digital or not events or not lsl_markers:
        parser.error("--session-dir must resolve paths or provide --physical-loopback-wav, --digital-evidence-wav, --events-csv, and --lsl-markers-csv")
    output_dir = args.output_dir or _default_output_dir()
    report = compare_layers(
        physical_wav=Path(physical),
        digital_wav=Path(digital),
        events_csv=Path(events),
        lsl_markers_csv=Path(lsl_markers),
        rich_lsl_csv=args.rich_lsl_csv,
        numeric_lsl_csv=args.numeric_lsl_csv,
        output_dir=output_dir,
        tactile_channel=args.tactile_channel,
    )
    print(f"Wrote {output_dir / 'recording_layer_alignment_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
