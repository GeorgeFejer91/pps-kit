"""Measure DynaSpace smartphone PPS audio features against PPS-kit proxies.

This script intentionally does not copy or redistribute the upstream
DynaSpace WAV files. By default it expects a sibling checkout named
``dynaspace-private`` next to this repository, or a path passed via
``--dynaspace-root`` / ``DYNASPACE_ROOT``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy import signal
from scipy.io import wavfile


EPS = 1e-12
BANDS_HZ = [
    (20, 100),
    (100, 250),
    (250, 500),
    (500, 1000),
    (1000, 2000),
    (2000, 4000),
    (4000, 8000),
    (8000, 16000),
    (16000, None),
]


def db20(value: float) -> float:
    return float(20.0 * math.log10(max(float(value), EPS)))


def db10(value: float) -> float:
    return float(10.0 * math.log10(max(float(value), EPS)))


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_wav_float(path: Path) -> tuple[int, np.ndarray, str]:
    sr, data = wavfile.read(path)
    dtype = str(data.dtype)
    if data.ndim == 1:
        data = data[:, None]
    if np.issubdtype(data.dtype, np.integer):
        info = np.iinfo(data.dtype)
        scale = max(abs(info.min), info.max)
        audio = data.astype(np.float64) / float(scale)
    else:
        audio = data.astype(np.float64)
    return int(sr), audio, dtype


def frame_rms(signal_mono: np.ndarray, sr: int, frame_ms: float = 20.0, hop_ms: float = 10.0):
    frame = max(1, int(round(sr * frame_ms / 1000.0)))
    hop = max(1, int(round(sr * hop_ms / 1000.0)))
    if len(signal_mono) < frame:
        padded = np.pad(signal_mono, (0, frame - len(signal_mono)))
        values = np.array([math.sqrt(float(np.mean(padded * padded)))])
        times = np.array([0.0])
        return times, values
    starts = np.arange(0, len(signal_mono) - frame + 1, hop)
    values = np.array(
        [math.sqrt(float(np.mean(signal_mono[start : start + frame] ** 2))) for start in starts]
    )
    times = (starts + frame / 2.0) / float(sr)
    return times, values


def smooth_abs_envelope(signal_mono: np.ndarray, sr: int, smooth_ms: float = 5.0) -> np.ndarray:
    envelope = np.abs(signal.hilbert(signal_mono))
    win = max(1, int(round(sr * smooth_ms / 1000.0)))
    kernel = np.ones(win, dtype=np.float64) / float(win)
    return np.convolve(envelope, kernel, mode="same")


def detect_bursts(signal_mono: np.ndarray, sr: int):
    frame = max(1, int(round(sr * 0.020)))
    hop = max(1, int(round(sr * 0.0025)))
    starts = np.arange(0, max(1, len(signal_mono) - frame + 1), hop)
    rms = np.array(
        [
            math.sqrt(float(np.mean(signal_mono[start : start + frame] ** 2)))
            for start in starts
            if len(signal_mono[start : start + frame]) == frame
        ]
    )
    times = (starts[: len(rms)] + frame / 2.0) / float(sr)
    rms_db = 20.0 * np.log10(np.maximum(rms, EPS))
    min_distance = max(1, int(round(0.055 / (hop / sr))))
    peaks, _props = signal.find_peaks(rms_db, distance=min_distance, prominence=3.0)

    if len(peaks):
        widths, _heights, left_ips, right_ips = signal.peak_widths(rms_db, peaks, rel_height=0.5)
        peak_times = times[peaks]
        onset_times = (left_ips * hop + frame / 2.0) / float(sr)
        durations_ms = list(1000.0 * widths * hop / float(sr))
        iois_ms = [1000.0 * (peak_times[idx] - peak_times[idx - 1]) for idx in range(1, len(peaks))]
    else:
        peak_times = np.array([])
        onset_times = np.array([])
        durations_ms = []
        iois_ms = []

    return {
        "detector": "20ms_rms_2p5ms_hop_find_peaks_prominence_3db_min_spacing_55ms",
        "count": int(len(peaks)),
        "first_10_onsets_s": [round(float(value), 6) for value in onset_times[:10]],
        "first_10_peak_times_s": [round(float(value), 6) for value in peak_times[:10]],
        "median_duration_ms": float(np.median(durations_ms)) if durations_ms else None,
        "median_ioi_ms": float(np.median(iois_ms)) if iois_ms else None,
        "durations_ms_first_10": [round(value, 3) for value in durations_ms[:10]],
    }


def spectral_metrics(signal_mono: np.ndarray, sr: int):
    nperseg = min(8192, max(1024, int(2 ** math.floor(math.log2(max(1024, len(signal_mono) // 16))))))
    freqs, pxx = signal.welch(
        signal_mono,
        fs=sr,
        window="hann",
        nperseg=nperseg,
        noverlap=nperseg // 2,
        detrend="constant",
        scaling="spectrum",
    )
    valid = freqs >= 20
    total = float(np.sum(pxx[valid]))
    centroid = float(np.sum(freqs[valid] * pxx[valid]) / max(total, EPS))
    cumulative = np.cumsum(pxx[valid])
    rolloff_85 = float(freqs[valid][np.searchsorted(cumulative, 0.85 * total)])
    rolloff_95 = float(freqs[valid][np.searchsorted(cumulative, 0.95 * total)])
    flatness = float(math.exp(np.mean(np.log(pxx[valid] + EPS))) / max(np.mean(pxx[valid]), EPS))

    band_power = {}
    powers = []
    nyquist = sr / 2.0
    for low, high in BANDS_HZ:
        high_eff = nyquist if high is None else min(high, nyquist)
        label = f"{low}-Nyquist" if high is None else f"{low}-{int(high_eff)}"
        mask = (freqs >= low) & (freqs < high_eff)
        power = float(np.sum(pxx[mask]))
        band_power[label] = power
        powers.append(power)
    max_power = max(powers) if powers else EPS
    band_relative_db = {label: db10(power / max_power) for label, power in band_power.items()}

    slope_mask = (freqs >= 100) & (freqs <= min(16000, nyquist - 1))
    if np.count_nonzero(slope_mask) > 2:
        x = np.log2(freqs[slope_mask])
        y = 10.0 * np.log10(pxx[slope_mask] + EPS)
        spectral_slope_db_per_octave = float(np.polyfit(x, y, 1)[0])
    else:
        spectral_slope_db_per_octave = None

    return {
        "centroid_hz": centroid,
        "rolloff_85_hz": rolloff_85,
        "rolloff_95_hz": rolloff_95,
        "flatness": flatness,
        "spectral_slope_db_per_octave_100_16000": spectral_slope_db_per_octave,
        "band_relative_db": band_relative_db,
    }


def lag_metrics(left: np.ndarray, right: np.ndarray, sr: int, max_lag_s: float = 0.001):
    left_z = left - np.mean(left)
    right_z = right - np.mean(right)
    denom = math.sqrt(float(np.sum(left_z * left_z) * np.sum(right_z * right_z)))
    if denom <= EPS:
        return {"lag_us": None, "iacc_abs": None, "iacc_signed": None}
    corr = signal.correlate(left_z, right_z, mode="full", method="fft") / denom
    lags = signal.correlation_lags(len(left_z), len(right_z), mode="full")
    limit = int(round(max_lag_s * sr))
    mask = np.abs(lags) <= limit
    local_corr = corr[mask]
    local_lags = lags[mask]
    idx = int(np.argmax(np.abs(local_corr)))
    return {
        "lag_us": float(1e6 * local_lags[idx] / sr),
        "iacc_abs": float(abs(local_corr[idx])),
        "iacc_signed": float(local_corr[idx]),
    }


def binaural_metrics(audio: np.ndarray, sr: int):
    if audio.shape[1] < 2:
        return None
    left = audio[:, 0]
    right = audio[:, 1]
    left_rms = math.sqrt(float(np.mean(left * left)))
    right_rms = math.sqrt(float(np.mean(right * right)))
    base = lag_metrics(left, right, sr)
    base["ild_left_minus_right_db"] = db20(left_rms / max(right_rms, EPS))
    base["pearson_lr"] = float(np.corrcoef(left, right)[0, 1])

    frame = int(round(sr * 0.100))
    hop = int(round(sr * 0.050))
    rows = []
    for start in range(0, max(1, len(audio) - frame + 1), hop):
        chunk = audio[start : start + frame]
        if len(chunk) < frame:
            break
        l = chunk[:, 0]
        r = chunk[:, 1]
        lrms = math.sqrt(float(np.mean(l * l)))
        rrms = math.sqrt(float(np.mean(r * r)))
        metrics = lag_metrics(l, r, sr)
        rows.append(
            {
                "time_s": float((start + frame / 2.0) / sr),
                "ild_left_minus_right_db": db20(lrms / max(rrms, EPS)),
                "itd_lag_us": metrics["lag_us"],
                "iacc_abs": metrics["iacc_abs"],
            }
        )
    if rows:
        ilds = np.array([row["ild_left_minus_right_db"] for row in rows])
        itds = np.array([row["itd_lag_us"] if row["itd_lag_us"] is not None else np.nan for row in rows], dtype=float)
        iaccs = np.array([row["iacc_abs"] if row["iacc_abs"] is not None else np.nan for row in rows], dtype=float)
        base["moving_100ms"] = {
            "window_count": len(rows),
            "ild_min_db": float(np.nanmin(ilds)),
            "ild_max_db": float(np.nanmax(ilds)),
            "ild_first_db": float(ilds[0]),
            "ild_last_db": float(ilds[-1]),
            "itd_min_us": float(np.nanmin(itds)),
            "itd_max_us": float(np.nanmax(itds)),
            "itd_first_us": float(itds[0]),
            "itd_last_us": float(itds[-1]),
            "iacc_min": float(np.nanmin(iaccs)),
            "iacc_max": float(np.nanmax(iaccs)),
            "iacc_first": float(iaccs[0]),
            "iacc_last": float(iaccs[-1]),
        }
    else:
        base["moving_100ms"] = None
    return base


def measure_one(label: str, path: Path):
    sr, audio, dtype = read_wav_float(path)
    mono = np.mean(audio, axis=1)
    times, rms = frame_rms(mono, sr)
    rms_db = 20.0 * np.log10(np.maximum(rms, EPS))
    active_threshold_db = -85.0
    active = rms_db > active_threshold_db
    active_pct = 100.0 * float(np.mean(active)) if len(active) else 0.0
    if np.any(active):
        active_times = times[active]
        active_db = rms_db[active]
        slope = float(np.polyfit(active_times, active_db, 1)[0]) if len(active_db) > 1 else None
        active_summary = {
            "threshold_dbfs": active_threshold_db,
            "percent_active": active_pct,
            "first_active_s": float(active_times[0]),
            "last_active_s": float(active_times[-1]),
            "p10_dbfs": float(np.quantile(active_db, 0.10)),
            "p50_dbfs": float(np.quantile(active_db, 0.50)),
            "p90_dbfs": float(np.quantile(active_db, 0.90)),
            "p90_minus_p10_db": float(np.quantile(active_db, 0.90) - np.quantile(active_db, 0.10)),
            "first_dbfs": float(active_db[0]),
            "last_dbfs": float(active_db[-1]),
            "linear_slope_db_per_s": slope,
        }
    else:
        active_summary = {
            "threshold_dbfs": active_threshold_db,
            "percent_active": active_pct,
            "first_active_s": None,
            "last_active_s": None,
            "p10_dbfs": None,
            "p50_dbfs": None,
            "p90_dbfs": None,
            "p90_minus_p10_db": None,
            "first_dbfs": None,
            "last_dbfs": None,
            "linear_slope_db_per_s": None,
        }

    peak = float(np.max(np.abs(audio)))
    rms_full = math.sqrt(float(np.mean(audio * audio)))
    clipped = int(np.count_nonzero(np.abs(audio) >= 0.999969))

    result = {
        "label": label,
        "path_hint": path.name,
        "sha256": sha256_file(path),
        "sample_rate_hz": sr,
        "dtype": dtype,
        "channels": int(audio.shape[1]),
        "frames": int(audio.shape[0]),
        "duration_s": float(audio.shape[0] / sr),
        "peak_dbfs": db20(peak),
        "rms_dbfs": db20(rms_full),
        "crest_factor_db": db20(peak / max(rms_full, EPS)),
        "dc_offset_by_channel": [float(np.mean(audio[:, idx])) for idx in range(audio.shape[1])],
        "clipped_samples": clipped,
        "frame_rms": {
            "frame_ms": 20.0,
            "hop_ms": 10.0,
            "max_dbfs": float(np.max(rms_db)),
            "min_dbfs": float(np.min(rms_db)),
        },
        "active_rms_summary": active_summary,
        "burst_structure": detect_bursts(mono, sr),
        "spectral": spectral_metrics(mono, sr),
        "binaural": binaural_metrics(audio, sr),
    }
    return result, {"time_s": times.tolist(), "rms_dbfs": rms_db.tolist()}


def resolve_inputs(dynaspace_root: Path | None):
    root = repo_root()
    dyn_root = dynaspace_root or root.parent / "dynaspace-private"
    return {
        "dynaspace_raw_looming": dyn_root
        / "DynaSpaceIrcam"
        / "app"
        / "src"
        / "main"
        / "res"
        / "raw"
        / "bursttrainlooming.wav",
        "dynaspace_raw_fixed": dyn_root
        / "DynaSpaceIrcam"
        / "app"
        / "src"
        / "main"
        / "res"
        / "raw"
        / "bursttrainfixe.wav",
        "pps_proxy_looming": root
        / "assets"
        / "preloads"
        / "roussel_2025_dynaspace_mobile_pps"
        / "02_looming_stimuli"
        / "looming_DynaSpace_proxy_looming_burst_train.wav",
        "pps_proxy_fixed": root
        / "assets"
        / "preloads"
        / "roussel_2025_dynaspace_mobile_pps"
        / "02_looming_stimuli"
        / "looming_DynaSpace_proxy_fixed_640_cm_burst_train.wav",
    }


def write_summary_csv(metrics: dict, path: Path):
    rows = []
    for label, item in metrics.items():
        active = item["active_rms_summary"]
        spectral = item["spectral"]
        binaural = item["binaural"] or {}
        moving = binaural.get("moving_100ms") or {}
        rows.append(
            {
                "label": label,
                "sample_rate_hz": item["sample_rate_hz"],
                "duration_s": item["duration_s"],
                "peak_dbfs": item["peak_dbfs"],
                "rms_dbfs": item["rms_dbfs"],
                "crest_factor_db": item["crest_factor_db"],
                "burst_count": item["burst_structure"]["count"],
                "median_burst_duration_ms": item["burst_structure"]["median_duration_ms"],
                "median_burst_ioi_ms": item["burst_structure"]["median_ioi_ms"],
                "active_p90_minus_p10_db": active["p90_minus_p10_db"],
                "active_slope_db_per_s": active["linear_slope_db_per_s"],
                "spectral_centroid_hz": spectral["centroid_hz"],
                "rolloff_95_hz": spectral["rolloff_95_hz"],
                "spectral_flatness": spectral["flatness"],
                "ild_left_minus_right_db": binaural.get("ild_left_minus_right_db"),
                "itd_lag_us": binaural.get("lag_us"),
                "iacc_abs": binaural.get("iacc_abs"),
                "moving_ild_min_db": moving.get("ild_min_db"),
                "moving_ild_max_db": moving.get("ild_max_db"),
                "moving_iacc_min": moving.get("iacc_min"),
                "moving_iacc_max": moving.get("iacc_max"),
            }
        )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_feature_matrix_csv(metrics: dict, path: Path):
    android = metrics["dynaspace_raw_looming"]
    proxy = metrics["pps_proxy_looming"]
    rows = [
        ("duration_s", android["duration_s"], proxy["duration_s"], "match window length before timing offsets"),
        ("sample_rate_hz", android["sample_rate_hz"], proxy["sample_rate_hz"], "raw Android file differs from 44.1 kHz profile"),
        ("peak_dbfs", android["peak_dbfs"], proxy["peak_dbfs"], "proxy is normalized closer to full scale"),
        ("rms_dbfs", android["rms_dbfs"], proxy["rms_dbfs"], "proxy is much higher average level"),
        ("crest_factor_db", android["crest_factor_db"], proxy["crest_factor_db"], "raw file has stronger pulse-like crest"),
        (
            "burst_count",
            android["burst_structure"]["count"],
            proxy["burst_structure"]["count"],
            "post-implementation proxy now matches the 33-burst temporal structure",
        ),
        (
            "active_p90_minus_p10_db",
            android["active_rms_summary"]["p90_minus_p10_db"],
            proxy["active_rms_summary"]["p90_minus_p10_db"],
            "proxy carries a larger smooth gain ramp",
        ),
        (
            "spectral_centroid_hz",
            android["spectral"]["centroid_hz"],
            proxy["spectral"]["centroid_hz"],
            "raw file is higher and brighter",
        ),
        (
            "ild_left_minus_right_db",
            android["binaural"]["ild_left_minus_right_db"],
            proxy["binaural"]["ild_left_minus_right_db"],
            "sign and magnitude differ; coordinate/channel convention needs audit",
        ),
        ("itd_lag_us", android["binaural"]["lag_us"], proxy["binaural"]["lag_us"], "lag differs materially"),
        (
            "iacc_abs",
            android["binaural"]["iacc_abs"],
            proxy["binaural"]["iacc_abs"],
            "raw file is far more decorrelated, consistent with room/reverb rendering",
        ),
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["feature", "dynaspace_raw_looming", "pps_proxy_looming", "interpretation"])
        writer.writerows(rows)


def make_plots(metrics: dict, rms_series: dict, out_dir: Path):
    figures = out_dir / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(10, 5))
    for label, series in rms_series.items():
        plt.plot(series["time_s"], series["rms_dbfs"], linewidth=1.2, label=label)
    plt.xlabel("Time (s)")
    plt.ylabel("20 ms RMS (dBFS)")
    plt.title("Time-varying level envelope")
    plt.grid(True, alpha=0.25)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(figures / "rms_envelope_comparison.png", dpi=180)
    plt.close()

    labels = list(metrics.keys())
    band_labels = list(next(iter(metrics.values()))["spectral"]["band_relative_db"].keys())
    x = np.arange(len(band_labels))
    width = 0.18
    plt.figure(figsize=(11, 5))
    for idx, label in enumerate(labels):
        values = [metrics[label]["spectral"]["band_relative_db"][band] for band in band_labels]
        plt.bar(x + (idx - 1.5) * width, values, width, label=label)
    plt.xticks(x, band_labels, rotation=45, ha="right")
    plt.ylabel("Relative band power (dB; max band = 0)")
    plt.title("Spectral band balance")
    plt.grid(True, axis="y", alpha=0.25)
    plt.legend(fontsize=8)
    plt.tight_layout()
    plt.savefig(figures / "spectral_band_comparison.png", dpi=180)
    plt.close()

    summary_labels = ["dynaspace_raw_looming", "pps_proxy_looming"]
    ild = [metrics[label]["binaural"]["ild_left_minus_right_db"] for label in summary_labels]
    iacc = [metrics[label]["binaural"]["iacc_abs"] for label in summary_labels]
    fig, ax1 = plt.subplots(figsize=(7, 4))
    x = np.arange(len(summary_labels))
    ax1.bar(x - 0.18, ild, 0.36, label="ILD L-R (dB)", color="#4062bb")
    ax1.set_ylabel("ILD L-R (dB)")
    ax1.axhline(0, color="black", linewidth=0.8)
    ax2 = ax1.twinx()
    ax2.bar(x + 0.18, iacc, 0.36, label="IACC abs", color="#d95f02")
    ax2.set_ylabel("IACC abs")
    ax2.set_ylim(0, 1)
    ax1.set_xticks(x)
    ax1.set_xticklabels(["DynaSpace raw loom", "PPS-kit proxy loom"], rotation=10)
    ax1.set_title("Binaural balance and coherence")
    ax1.grid(True, axis="y", alpha=0.2)
    handles1, labels1 = ax1.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(handles1 + handles2, labels1 + labels2, loc="upper left", fontsize=8)
    fig.tight_layout()
    fig.savefig(figures / "binaural_summary.png", dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dynaspace-root", type=Path, default=None)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Output directory for metrics and figures.",
    )
    args = parser.parse_args()

    inputs = resolve_inputs(args.dynaspace_root)
    missing = [str(path) for path in inputs.values() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required audio files:\n" + "\n".join(missing))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    metrics = {}
    rms_series = {}
    for label, path in inputs.items():
        result, series = measure_one(label, path)
        metrics[label] = result
        rms_series[label] = series

    metrics_path = args.out_dir / "dynaspace_audio_feature_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    write_summary_csv(metrics, args.out_dir / "dynaspace_audio_feature_summary.csv")
    write_feature_matrix_csv(metrics, args.out_dir / "looming_feature_comparison_matrix.csv")
    make_plots(metrics, rms_series, args.out_dir)
    print(f"Wrote {metrics_path}")


if __name__ == "__main__":
    main()
