"""Offline signal-level QC for dummy route-sweep captures.

This is an analysis-only helper. It does not play audio and is safe to run on
existing validation artifacts. It distinguishes "visible above the noise floor"
from "acceptable as a final latency-baseline channel".
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from compare_dummy_pulse_recordings import MIN_PEAK, MIN_SHAPE_CORRELATION, _normalized_correlation  # noqa: E402


SCHEMA = "pps-dummy-signal-level-qc.v1"
MIN_VISIBLE_SNR = 10.0
MIN_BASELINE_SNR = 50.0


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _median(values: list[float]) -> float:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    return float(np.median(np.asarray(finite, dtype=np.float64))) if finite else math.nan


def _db_ratio(numerator: float, denominator: float) -> float:
    if numerator <= 0 or denominator <= 0:
        return math.nan
    return 20.0 * math.log10(numerator / denominator)


def _expected_samples(planned_rows: list[dict[str, str]]) -> list[int]:
    rows = [row for row in planned_rows if int(row.get("channel", 0)) == 0]
    rows.sort(key=lambda row: int(row.get("pulse_index", 0)))
    return [int(row["expected_sample_index"]) for row in rows]


def _pulse_template(stimulus: np.ndarray, output_channel: int, sample_rate: int) -> np.ndarray:
    signal = stimulus[:, output_channel]
    nonzero = np.flatnonzero(np.abs(signal) > 0)
    if nonzero.size == 0:
        return signal[: max(1, int(round(0.035 * sample_rate)))]
    start = int(nonzero[0])
    return signal[start : start + max(1, int(round(0.035 * sample_rate)))]


def _noise_signal(signal: np.ndarray, expected: list[int], *, sample_rate: int, exclusion_ms: float) -> np.ndarray:
    mask = np.ones(len(signal), dtype=bool)
    half_width = int(round((exclusion_ms / 1000.0) * sample_rate))
    for sample in expected:
        mask[max(0, sample - half_width) : min(len(signal), sample + half_width)] = False
    return signal[mask]


def _channel_level_summary(
    capture: np.ndarray,
    stimulus: np.ndarray,
    *,
    output_channel: int,
    input_channel: int,
    expected: list[int],
    sample_rate: int,
    search_pre_ms: float,
    search_post_ms: float,
    noise_exclusion_ms: float,
) -> dict[str, Any]:
    signal = capture[:, input_channel]
    template = _pulse_template(stimulus, output_channel, sample_rate)
    noise = _noise_signal(signal, expected, sample_rate=sample_rate, exclusion_ms=noise_exclusion_ms)
    noise_abs = np.abs(noise.astype(np.float64, copy=False))
    noise_rms = float(np.sqrt(np.mean(noise.astype(np.float64) ** 2))) if noise.size else math.nan
    noise_p999 = float(np.percentile(noise_abs, 99.9)) if noise_abs.size else math.nan
    noise_peak = float(np.max(noise_abs)) if noise_abs.size else math.nan
    pre = int(round((search_pre_ms / 1000.0) * sample_rate))
    post = int(round((search_post_ms / 1000.0) * sample_rate))
    pulse_peaks: list[float] = []
    snrs: list[float] = []
    corrs: list[float] = []
    peak_latencies_ms: list[float] = []

    for sample in expected:
        start = max(0, int(sample) - pre)
        stop = min(len(signal), int(sample) + post)
        if stop <= start:
            continue
        window = signal[start:stop]
        local_index = int(np.argmax(np.abs(window)))
        detected = start + local_index
        peak = float(np.max(np.abs(window)))
        segment = signal[detected : detected + len(template)]
        corr = abs(_normalized_correlation(segment, template))
        pulse_peaks.append(peak)
        corrs.append(corr)
        peak_latencies_ms.append((detected - sample) / float(sample_rate) * 1000.0)
        snrs.append(peak / noise_rms if math.isfinite(noise_rms) and noise_rms > 0 else math.nan)

    median_peak = _median(pulse_peaks)
    median_snr = _median(snrs)
    median_corr = _median(corrs)
    clipped = bool(np.max(np.abs(signal)) >= 0.98) if signal.size else False
    visible_above_noise = bool(math.isfinite(median_snr) and median_snr >= MIN_VISIBLE_SNR)
    accepted_for_baseline = bool(
        visible_above_noise
        and median_snr >= MIN_BASELINE_SNR
        and math.isfinite(median_peak)
        and median_peak >= MIN_PEAK
        and math.isfinite(median_corr)
        and median_corr >= MIN_SHAPE_CORRELATION
        and not clipped
    )
    return {
        "output_channel_1based": output_channel + 1,
        "expected_input_channel_1based": input_channel + 1,
        "pulse_count": len(expected),
        "noise_rms": noise_rms,
        "noise_p999": noise_p999,
        "noise_peak": noise_peak,
        "median_pulse_peak": median_peak,
        "min_pulse_peak": min(pulse_peaks) if pulse_peaks else math.nan,
        "median_peak_to_noise_rms": median_snr,
        "median_shape_correlation": median_corr,
        "median_peak_latency_ms": _median(peak_latencies_ms),
        "clipped": clipped,
        "visible_above_noise": visible_above_noise,
        "accepted_for_latency_baseline": accepted_for_baseline,
        "minimum_visible_snr": MIN_VISIBLE_SNR,
        "minimum_baseline_snr": MIN_BASELINE_SNR,
        "minimum_baseline_peak": MIN_PEAK,
        "minimum_shape_correlation": MIN_SHAPE_CORRELATION,
        "per_pulse_peak": pulse_peaks,
        "per_pulse_peak_to_noise_rms": snrs,
        "per_pulse_shape_correlation": corrs,
        "per_pulse_peak_latency_ms": peak_latencies_ms,
    }


def analyze_run(
    run_dir: Path,
    *,
    search_pre_ms: float = 25.0,
    search_post_ms: float = 200.0,
    noise_exclusion_ms: float = 250.0,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "dummy_pulse_manifest.json").read_text(encoding="utf-8"))
    planned_rows = _read_csv(run_dir / "planned_pulses.csv")
    stimulus, stimulus_rate = sf.read(run_dir / "dummy_3ch_pulses.wav", dtype="float32", always_2d=True)
    sample_rate = int(manifest["sample_rate"])
    if int(stimulus_rate) != sample_rate:
        raise ValueError(f"Stimulus sample rate {stimulus_rate} does not match manifest {sample_rate}")
    expected = _expected_samples(planned_rows)
    rows: list[dict[str, Any]] = []
    output_channels = int(manifest.get("output_channels") or manifest.get("channels") or stimulus.shape[1])
    for output_channel in range(min(3, output_channels)):
        capture_path = run_dir / f"output_{output_channel + 1}_capture.wav"
        if not capture_path.exists():
            continue
        capture, capture_rate = sf.read(capture_path, dtype="float32", always_2d=True)
        if int(capture_rate) != sample_rate:
            raise ValueError(f"{capture_path} sample rate {capture_rate} does not match manifest {sample_rate}")
        input_channel = output_channel
        if input_channel >= capture.shape[1]:
            continue
        summary = _channel_level_summary(
            capture,
            stimulus,
            output_channel=output_channel,
            input_channel=input_channel,
            expected=expected,
            sample_rate=sample_rate,
            search_pre_ms=search_pre_ms,
            search_post_ms=search_post_ms,
            noise_exclusion_ms=noise_exclusion_ms,
        )
        summary["capture_path"] = str(capture_path)
        rows.append(summary)

    strongest_peak = max([float(row["median_pulse_peak"]) for row in rows if math.isfinite(float(row["median_pulse_peak"]))], default=math.nan)
    for row in rows:
        row["relative_to_strongest_peak_db"] = _db_ratio(float(row["median_pulse_peak"]), strongest_peak)

    report = {
        "schema": SCHEMA,
        "run_dir": str(run_dir),
        "sample_rate": sample_rate,
        "search_window_ms": {"pre": search_pre_ms, "post": search_post_ms},
        "noise_exclusion_ms": noise_exclusion_ms,
        "channels": rows,
        "all_visible_above_noise": all(row["visible_above_noise"] for row in rows) if rows else False,
        "all_accepted_for_latency_baseline": all(row["accepted_for_latency_baseline"] for row in rows) if rows else False,
        "interpretation": _interpret(rows),
        "limitations": [
            "This is offline signal-level analysis of existing captures; it does not play audio.",
            "A channel can be visible above noise but still fail final latency-baseline criteria if it is too low or shape correlation is unstable.",
            "Woojer mechanical vibration onset is not measured.",
        ],
    }
    (run_dir / "dummy_signal_level_qc.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_csv(run_dir / "dummy_signal_level_qc.csv", rows)
    _write_markdown(run_dir / "dummy_signal_level_qc.md", report)
    return report


def _interpret(rows: list[dict[str, Any]]) -> list[str]:
    notes = []
    for row in rows:
        label = f"Output {row['output_channel_1based']} / input {row['expected_input_channel_1based']}"
        if row["accepted_for_latency_baseline"]:
            notes.append(f"{label} is acceptable for latency-baseline detection.")
        elif row["visible_above_noise"]:
            notes.append(
                f"{label} is visible above noise but does not meet final baseline criteria "
                f"(peak={float(row['median_pulse_peak']):.6f}, SNR={float(row['median_peak_to_noise_rms']):.1f}, "
                f"corr={float(row['median_shape_correlation']):.3f})."
            )
        else:
            notes.append(f"{label} is not reliably visible above the measured noise floor.")
    return notes


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = [
        "output_channel_1based",
        "expected_input_channel_1based",
        "pulse_count",
        "noise_rms",
        "noise_p999",
        "noise_peak",
        "median_pulse_peak",
        "min_pulse_peak",
        "median_peak_to_noise_rms",
        "median_shape_correlation",
        "median_peak_latency_ms",
        "relative_to_strongest_peak_db",
        "clipped",
        "visible_above_noise",
        "accepted_for_latency_baseline",
        "capture_path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Dummy Signal-Level QC",
        "",
        f"- Run dir: `{report['run_dir']}`",
        f"- All visible above noise: `{report['all_visible_above_noise']}`",
        f"- All accepted for latency baseline: `{report['all_accepted_for_latency_baseline']}`",
        "",
        "## Channels",
        "",
    ]
    for row in report["channels"]:
        lines.append(
            "- Output {out}/input {inp}: peak={peak:.6f}, SNR={snr:.1f}, corr={corr:.3f}, "
            "relative={rel:.1f} dB, visible={visible}, accepted={accepted}".format(
                out=row["output_channel_1based"],
                inp=row["expected_input_channel_1based"],
                peak=float(row["median_pulse_peak"]),
                snr=float(row["median_peak_to_noise_rms"]),
                corr=float(row["median_shape_correlation"]),
                rel=float(row["relative_to_strongest_peak_db"]),
                visible=row["visible_above_noise"],
                accepted=row["accepted_for_latency_baseline"],
            )
        )
    lines.extend(["", "## Interpretation", ""])
    for note in report["interpretation"]:
        lines.append(f"- {note}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze dummy route-sweep signal levels without playing audio.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--search-pre-ms", type=float, default=25.0)
    parser.add_argument("--search-post-ms", type=float, default=200.0)
    parser.add_argument("--noise-exclusion-ms", type=float, default=250.0)
    args = parser.parse_args(argv)
    report = analyze_run(
        args.run_dir,
        search_pre_ms=args.search_pre_ms,
        search_post_ms=args.search_post_ms,
        noise_exclusion_ms=args.noise_exclusion_ms,
    )
    print(f"Wrote {Path(report['run_dir']) / 'dummy_signal_level_qc.json'}")
    return 0 if report["all_accepted_for_latency_baseline"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
