"""Compare an actual one-block loopback recording against its source block WAV.

This analyzer is for internal validation after
``run_one_block_actual_condition_validation.py``. It does not assume dummy
rectangular pulses. Instead, it uses FFT correlation between each source channel
and the corresponding captured channel, then reports per-channel capture
alignment offsets and paired inter-channel skew.

The absolute offset includes the validation capture lead-in plus output/input
latency. Inter-channel differences cancel that common lead-in and are the main
multichannel synchronization evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from scipy import signal


SCHEMA = "pps-actual-block-loopback-comparison.v1"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _float(value: Any, default: float = math.nan) -> float:
    try:
        result = float(str(value))
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _stats_ms(values: list[float]) -> dict[str, Any]:
    values = [float(value) for value in values if math.isfinite(float(value))]
    if not values:
        return {"count": 0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(arr.size),
        "mean_ms": float(np.mean(arr)),
        "sd_ms": float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0,
        "median_ms": float(np.median(arr)),
        "p95_ms": float(np.percentile(arr, 95)),
        "min_ms": float(np.min(arr)),
        "max_ms": float(np.max(arr)),
    }


def _normalize(samples: np.ndarray) -> np.ndarray:
    data = np.asarray(samples, dtype=np.float64)
    data = data - float(np.mean(data)) if data.size else data
    norm = float(np.linalg.norm(data))
    if norm <= 0:
        return data
    return data / norm


def _valid_lag(source: np.ndarray, capture: np.ndarray, *, max_lag_samples: int | None = None) -> tuple[int, float]:
    if capture.size < source.size:
        raise ValueError("capture segment is shorter than source segment")
    valid = signal.correlate(_normalize(capture), _normalize(source), mode="valid", method="fft")
    if max_lag_samples is not None:
        valid = valid[: max(1, min(valid.size, int(max_lag_samples) + 1))]
    lag = int(np.argmax(np.abs(valid)))
    return lag, float(valid[lag])


def _channel_pair_name(a: int, b: int) -> str:
    labels = {0: "left", 1: "right", 2: "tactile"}
    return f"{labels.get(b, f'ch{b + 1}')}_minus_{labels.get(a, f'ch{a + 1}')}"


def _resolve_from_session(session_dir: Path) -> tuple[Path, Path, Path]:
    manifest = _read_json(session_dir / "session_manifest.json")
    blocks = manifest.get("blocks") if isinstance(manifest.get("blocks"), list) else []
    if not blocks:
        raise ValueError(f"No block in session manifest: {session_dir}")
    block = blocks[0]
    source_wav = Path(str(block.get("wav_path", "")))
    block_csv = Path(str(block.get("manifest_path", "")))
    if not source_wav.is_absolute() and not source_wav.exists():
        source_wav = session_dir / source_wav
    if not block_csv.is_absolute() and not block_csv.exists():
        block_csv = session_dir / block_csv
    recordings = sorted((session_dir / "recordings").glob("*.wav"))
    physical_recordings = [
        path
        for path in recordings
        if ("physical" in path.name.lower() or "loopback" in path.name.lower()) and "audio_evidence" not in path.name.lower()
    ]
    if not physical_recordings:
        raise ValueError(f"No loopback recording found in {session_dir / 'recordings'}")
    return source_wav, physical_recordings[0], block_csv


def compare_loopback(
    *,
    source_wav: Path,
    capture_wav: Path,
    block_csv: Path,
    output_dir: Path,
    max_global_lag_ms: float = 120.0,
    local_search_ms: float = 20.0,
    min_source_peak: float = 0.001,
    min_capture_peak: float = 0.0005,
    min_trial_correlation: float = 0.25,
) -> dict[str, Any]:
    source, source_rate = sf.read(source_wav, dtype="float32", always_2d=True)
    capture, capture_rate = sf.read(capture_wav, dtype="float32", always_2d=True)
    if int(source_rate) != int(capture_rate):
        raise ValueError(f"Sample-rate mismatch: source={source_rate}, capture={capture_rate}")
    sample_rate = int(source_rate)
    rows = _read_csv(block_csv)
    channel_count = min(3, source.shape[1], capture.shape[1])
    max_global_lag_samples = int(round(max_global_lag_ms / 1000.0 * sample_rate))
    local_radius = int(round(local_search_ms / 1000.0 * sample_rate))

    global_rows: list[dict[str, Any]] = []
    global_lags: dict[int, int] = {}
    for channel in range(channel_count):
        src = source[:, channel]
        cap = capture[:, channel]
        source_peak = float(np.max(np.abs(src))) if src.size else 0.0
        capture_peak = float(np.max(np.abs(cap))) if cap.size else 0.0
        if source_peak < min_source_peak or capture_peak < min_capture_peak:
            global_rows.append(
                {
                    "channel": channel + 1,
                    "used": False,
                    "reason": "low_signal",
                    "source_peak": source_peak,
                    "capture_peak": capture_peak,
                    "global_lag_samples": "",
                    "global_lag_ms": "",
                    "correlation": "",
                }
            )
            continue
        lag, corr = _valid_lag(src, cap, max_lag_samples=max_global_lag_samples)
        global_lags[channel] = lag
        global_rows.append(
            {
                "channel": channel + 1,
                "used": True,
                "reason": "",
                "source_peak": source_peak,
                "capture_peak": capture_peak,
                "global_lag_samples": lag,
                "global_lag_ms": lag / sample_rate * 1000.0,
                "correlation": corr,
            }
        )

    trial_rows: list[dict[str, Any]] = []
    per_trial: dict[tuple[int, int], float] = {}
    for fallback_trial, row in enumerate(rows, start=1):
        trial_number = int(_float(row.get("Trial_Number") or fallback_trial, default=fallback_trial))
        start = int(_float(row.get("Trial_Start_Sample"), default=math.nan))
        end = int(_float(row.get("Trial_End_Sample"), default=math.nan))
        if not math.isfinite(start) or not math.isfinite(end) or end <= start:
            start_s = _float(row.get("Trial_Start_S"), default=math.nan)
            end_s = _float(row.get("Trial_End_S"), default=math.nan)
            if not math.isfinite(start_s) or not math.isfinite(end_s) or end_s <= start_s:
                continue
            start = int(round(start_s * sample_rate))
            end = int(round(end_s * sample_rate))
        source_len = end - start
        for channel, global_lag in global_lags.items():
            src_segment = source[start:end, channel]
            source_peak = float(np.max(np.abs(src_segment))) if src_segment.size else 0.0
            if source_peak < min_source_peak:
                continue
            window_start = max(0, start + global_lag - local_radius)
            window_end = min(capture.shape[0], end + global_lag + local_radius)
            cap_segment = capture[window_start:window_end, channel]
            capture_peak = float(np.max(np.abs(cap_segment))) if cap_segment.size else 0.0
            if cap_segment.size < source_len or capture_peak < min_capture_peak:
                continue
            local_lag, corr = _valid_lag(src_segment, cap_segment)
            lag = window_start + local_lag - start
            lag_ms = lag / sample_rate * 1000.0
            residual_ms = (lag - global_lag) / sample_rate * 1000.0
            used_for_summary = abs(corr) >= min_trial_correlation
            if used_for_summary:
                per_trial[(trial_number, channel)] = lag_ms
            trial_rows.append(
                {
                    "trial_number": trial_number,
                    "trial_uid": row.get("Trial_UID", ""),
                    "trial_type": row.get("Trial_Type", ""),
                    "channel": channel + 1,
                    "used_for_summary": used_for_summary,
                    "lag_samples": lag,
                    "lag_ms": lag_ms,
                    "residual_vs_global_ms": residual_ms,
                    "source_peak": source_peak,
                    "capture_peak": capture_peak,
                    "correlation": corr,
                }
            )

    channel_summaries = []
    for channel in range(channel_count):
        lags = [row["lag_ms"] for row in trial_rows if row["channel"] == channel + 1 and row.get("used_for_summary")]
        residuals = [abs(row["residual_vs_global_ms"]) for row in trial_rows if row["channel"] == channel + 1 and row.get("used_for_summary")]
        channel_summaries.append(
            {
                "channel": channel + 1,
                "trial_lag_ms": _stats_ms(lags),
                "abs_residual_vs_global_ms": _stats_ms(residuals),
            }
        )

    pair_rows = []
    pair_summaries: dict[str, dict[str, Any]] = {}
    for a, b in ((0, 1), (0, 2), (1, 2)):
        values = []
        for trial_number in sorted({key[0] for key in per_trial}):
            if (trial_number, a) not in per_trial or (trial_number, b) not in per_trial:
                continue
            skew_ms = per_trial[(trial_number, b)] - per_trial[(trial_number, a)]
            values.append(skew_ms)
            pair_rows.append(
                {
                    "pair": _channel_pair_name(a, b),
                    "trial_number": trial_number,
                    "skew_ms": skew_ms,
                }
            )
        pair_summaries[_channel_pair_name(a, b)] = _stats_ms(values)

    tactile_audio_values = []
    for trial_number in sorted({key[0] for key in per_trial}):
        audio_lags = [per_trial[(trial_number, channel)] for channel in (0, 1) if (trial_number, channel) in per_trial]
        if not audio_lags or (trial_number, 2) not in per_trial:
            continue
        tactile_audio_values.append(per_trial[(trial_number, 2)] - float(np.mean(audio_lags)))
    pair_summaries["tactile_minus_audio_mean"] = _stats_ms(tactile_audio_values)

    capture_peaks = np.max(np.abs(capture), axis=0).astype(float).tolist() if capture.size else []
    report = {
        "schema": SCHEMA,
        "passed": bool(global_lags) and not any(peak >= 0.98 for peak in capture_peaks[:channel_count]),
        "source_wav": str(source_wav),
        "capture_wav": str(capture_wav),
        "block_csv": str(block_csv),
        "output_dir": str(output_dir),
        "sample_rate": sample_rate,
        "source_shape": list(source.shape),
        "capture_shape": list(capture.shape),
        "capture_peak_by_channel": capture_peaks,
        "min_trial_correlation": min_trial_correlation,
        "global_channel_alignment": global_rows,
        "channel_summaries": channel_summaries,
        "interchannel_skew_ms": pair_summaries,
        "limitations": [
            "Absolute lag includes validation capture lead-in plus output/input latency.",
            "Inter-channel skew is the primary synchronization estimate because common capture lead-in cancels.",
            "Woojer mechanical vibration onset is not measured.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "actual_block_loopback_global_alignment.csv", global_rows)
    _write_csv(output_dir / "actual_block_loopback_trial_lags.csv", trial_rows)
    _write_csv(output_dir / "actual_block_loopback_pair_skews.csv", pair_rows)
    (output_dir / "actual_block_loopback_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_markdown(output_dir / "actual_block_loopback_report.md", report)
    return report


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Actual Block Loopback Comparison",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Source WAV: `{report.get('source_wav')}`",
        f"- Capture WAV: `{report.get('capture_wav')}`",
        f"- Capture peaks: `{report.get('capture_peak_by_channel')}`",
        "",
        "## Global Alignment",
        "",
    ]
    for row in report.get("global_channel_alignment") or []:
        lines.append(
            f"- Channel {row['channel']}: used={row['used']}, lag={row['global_lag_ms']} ms, corr={row['correlation']}"
        )
    lines.extend(["", "## Inter-Channel Skew", ""])
    for key, stats in (report.get("interchannel_skew_ms") or {}).items():
        lines.append(f"- {key}: `{stats}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare actual one-block source WAV against direct loopback capture.")
    parser.add_argument("--session-dir", type=Path, default=None)
    parser.add_argument("--source-wav", type=Path, default=None)
    parser.add_argument("--capture-wav", type=Path, default=None)
    parser.add_argument("--block-csv", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--max-global-lag-ms", type=float, default=120.0)
    parser.add_argument("--local-search-ms", type=float, default=20.0)
    parser.add_argument("--min-source-peak", type=float, default=0.001)
    parser.add_argument("--min-capture-peak", type=float, default=0.0005)
    parser.add_argument("--min-trial-correlation", type=float, default=0.25)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.session_dir:
        source_wav, capture_wav, block_csv = _resolve_from_session(args.session_dir)
        output_dir = args.output_dir or (args.session_dir / "analysis" / "actual_block_loopback")
    else:
        if not (args.source_wav and args.capture_wav and args.block_csv):
            parser.error("--session-dir or all of --source-wav/--capture-wav/--block-csv is required")
        source_wav, capture_wav, block_csv = args.source_wav, args.capture_wav, args.block_csv
        output_dir = args.output_dir or Path("artifacts") / "validation_runs" / "actual_block_loopback"
    report = compare_loopback(
        source_wav=Path(source_wav),
        capture_wav=Path(capture_wav),
        block_csv=Path(block_csv),
        output_dir=Path(output_dir),
        max_global_lag_ms=args.max_global_lag_ms,
        local_search_ms=args.local_search_ms,
        min_source_peak=args.min_source_peak,
        min_capture_peak=args.min_capture_peak,
        min_trial_correlation=args.min_trial_correlation,
    )
    print(f"Wrote {Path(output_dir) / 'actual_block_loopback_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
