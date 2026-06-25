#!/usr/bin/env python
"""Compare a generated Pfeiffer-style WAV against the bundled original WAV."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.io import wavfile


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINAL = REPO_ROOT / "artifacts" / "pfeiffer_original" / "Pfeiffer_EJN2018" / "left2right_4sec.wav"
DEFAULT_GENERATED = REPO_ROOT / "artifacts" / "pfeiffer_verification" / "looming_Pink_lateral_source.wav"


def read_wav(path: Path) -> tuple[int, np.ndarray, str]:
    sample_rate, data = wavfile.read(path)
    if data.ndim == 1:
        data = data[:, None]
    dtype = str(data.dtype)
    if np.issubdtype(data.dtype, np.integer):
        data = data.astype(np.float64) / float(np.iinfo(data.dtype).max)
    else:
        data = data.astype(np.float64)
    return sample_rate, data, dtype


def rms(values: np.ndarray) -> float:
    return float(np.sqrt(np.mean(values * values))) if values.size else 0.0


def db(value: float) -> float:
    return -math.inf if value <= 0 else 20.0 * math.log10(value)


def corr(a: np.ndarray, b: np.ndarray) -> float | None:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    mask = np.isfinite(a) & np.isfinite(b)
    a = a[mask]
    b = b[mask]
    if len(a) < 3 or np.std(a) == 0 or np.std(b) == 0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def frame_rows(audio: np.ndarray, sample_rate: int, win_ms: float = 50.0, hop_ms: float = 10.0) -> np.ndarray:
    win = max(1, int(round(sample_rate * win_ms / 1000.0)))
    hop = max(1, int(round(sample_rate * hop_ms / 1000.0)))
    rows: list[tuple[float, float, float, float, float]] = []
    for start in range(0, max(1, len(audio) - win + 1), hop):
        frame = audio[start : start + win, :2]
        if len(frame) < win:
            break
        left = rms(frame[:, 0])
        right = rms(frame[:, 1])
        mono = rms(np.mean(frame[:, :2], axis=1))
        ild = db(left / right) if right > 0 else math.inf
        rows.append((start / sample_rate, left, right, mono, ild))
    return np.asarray(rows, dtype=np.float64)


def channel_summary(data: np.ndarray, sample_rate: int) -> dict[str, float | int]:
    n = len(data)
    audio = data[:, :2] if data.shape[1] >= 2 else np.repeat(data[:, :1], 2, axis=1)
    first = audio[: n // 2]
    second = audio[n // 2 :]
    first_left = rms(first[:, 0])
    first_right = rms(first[:, 1])
    second_left = rms(second[:, 0])
    second_right = rms(second[:, 1])
    left = rms(audio[:, 0])
    right = rms(audio[:, 1])
    peak = float(np.max(np.abs(data))) if data.size else 0.0
    return {
        "duration_s": n / sample_rate,
        "channels": int(data.shape[1]),
        "peak_abs": peak,
        "peak_dbfs": db(peak),
        "full_scale_or_clipped_samples": int(np.sum(np.abs(data) >= 0.999999)),
        "left_rms": left,
        "right_rms": right,
        "overall_ild_db_left_minus_right": db(left / right) if right > 0 else math.inf,
        "first_half_left_rms": first_left,
        "first_half_right_rms": first_right,
        "first_half_ild_db_left_minus_right": db(first_left / first_right) if first_right > 0 else math.inf,
        "second_half_left_rms": second_left,
        "second_half_right_rms": second_right,
        "second_half_ild_db_left_minus_right": db(second_left / second_right) if second_right > 0 else math.inf,
    }


def spectral_correlation(original: np.ndarray, generated: np.ndarray, sample_rate: int) -> float | None:
    original_mono = np.mean(original[:, :2], axis=1)
    generated_mono = np.mean(generated[:, :2], axis=1)
    f_original, p_original = signal.welch(original_mono, fs=sample_rate, nperseg=min(4096, len(original_mono)))
    f_generated, p_generated = signal.welch(generated_mono, fs=sample_rate, nperseg=min(4096, len(generated_mono)))
    generated_interp = np.interp(f_original, f_generated, p_generated)
    band = (f_original >= 100.0) & (f_original <= 12000.0)
    return corr(np.log10(p_original[band] + 1e-20), np.log10(generated_interp[band] + 1e-20))


def compare(original_path: Path, generated_path: Path) -> dict:
    original_sr, original, original_dtype = read_wav(original_path)
    generated_sr, generated, generated_dtype = read_wav(generated_path)
    if original_sr != generated_sr:
        raise ValueError(f"sample-rate mismatch: original={original_sr}, generated={generated_sr}")

    original_audio = original[:, :2]
    generated_audio = generated[:, :2]
    compared_samples = min(len(original_audio), len(generated_audio))
    original_compared = original_audio[:compared_samples]
    generated_compared = generated_audio[:compared_samples]

    original_frames = frame_rows(original_compared, original_sr)
    generated_frames = frame_rows(generated_compared, generated_sr)
    compared_frames = min(len(original_frames), len(generated_frames))
    original_frames = original_frames[:compared_frames]
    generated_frames = generated_frames[:compared_frames]

    return {
        "schema": "pps-pfeiffer-original-comparison.v1",
        "interpretation": (
            "Sample-level waveform identity is not expected when comparing the native 3DTI/FABIAN render "
            "with Pfeiffer's baked MATLAB spherical-head WAV. Use this report to inspect format, duration, "
            "level, channel dominance, envelope, spectrum, and ILD-curve differences."
        ),
        "files": {
            "original": str(original_path),
            "generated": str(generated_path),
        },
        "formats": {
            "sample_rate": original_sr,
            "original_dtype": original_dtype,
            "generated_dtype": generated_dtype,
        },
        "original_summary": channel_summary(original, original_sr),
        "generated_summary": channel_summary(generated, generated_sr),
        "similarity": {
            "compared_duration_s": compared_samples / original_sr,
            "sample_level_mono_correlation": corr(
                np.mean(original_compared, axis=1),
                np.mean(generated_compared, axis=1),
            ),
            "mono_rms_envelope_correlation_50ms": corr(original_frames[:, 3], generated_frames[:, 3])
            if compared_frames
            else None,
            "left_rms_envelope_correlation_50ms": corr(original_frames[:, 1], generated_frames[:, 1])
            if compared_frames
            else None,
            "right_rms_envelope_correlation_50ms": corr(original_frames[:, 2], generated_frames[:, 2])
            if compared_frames
            else None,
            "ild_curve_correlation_50ms": corr(original_frames[:, 4], generated_frames[:, 4])
            if compared_frames
            else None,
            "log_power_spectrum_correlation_100hz_12khz": spectral_correlation(
                original_compared,
                generated_compared,
                original_sr,
            ),
            "original_ild_start_end_db": [float(original_frames[0, 4]), float(original_frames[-1, 4])]
            if compared_frames
            else [],
            "generated_ild_start_end_db": [float(generated_frames[0, 4]), float(generated_frames[-1, 4])]
            if compared_frames
            else [],
        },
        "generated_tactile_channel": {
            "present": bool(generated.shape[1] >= 3),
            "nonzero_samples": int(np.count_nonzero(np.abs(generated[:, 2]) > 1e-9))
            if generated.shape[1] >= 3
            else 0,
            "peak_abs": float(np.max(np.abs(generated[:, 2]))) if generated.shape[1] >= 3 else 0.0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=DEFAULT_ORIGINAL)
    parser.add_argument("--generated", type=Path, default=DEFAULT_GENERATED)
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "artifacts" / "pfeiffer_verification" / "pfeiffer_original_similarity_report.json",
    )
    args = parser.parse_args(argv)

    report = compare(args.original, args.generated)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote comparison report: {args.output}")
    print(json.dumps(report["similarity"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
