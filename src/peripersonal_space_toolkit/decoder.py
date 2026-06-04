#!/usr/bin/env python
"""Loopback WAV-to-CSV decoding for the audio-tactile PPS toolkit.

The decoder reads local loopback WAV recordings, detects tactile cue timing,
mouse-click timing, breathing-template timing, looming onset, SOA, noise type,
and block/trial structure, then writes diagnostics and analysis-ready CSVs
under `artifacts/decoded` by default.

Participant recordings stay local and should be placed under an ignored folder
such as `local_data/loopback_recordings`.

Public CLI:
    pps-decode --help
    pps-decode --input-dir local_data/loopback_recordings --output-dir artifacts/decoded
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import re
import statistics
import sys
import time
import wave
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = PROJECT_ROOT / "local_data" / "loopback_recordings"
OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "decoded"
DIAGNOSTICS_DIR = OUTPUT_DIR / "diagnostics"
FINAL_DIR = OUTPUT_DIR / "final"
SUMMARIES_DIR = OUTPUT_DIR / "summaries"
EVENT_INVENTORY_DIR = OUTPUT_DIR / "event_inventory"
REFERENCE_SEQUENCE_ROOT = PROJECT_ROOT / "artifacts" / "stimuli" / "10.Participant_Sequences"
CLICK_TONE_PATH = PROJECT_ROOT / "assets" / "click" / "mouse_click_tone_1200Hz_50ms.wav"
LOOMING_NOISE_ROOT = PROJECT_ROOT / "artifacts" / "stimuli" / "2. LoomingStimuli"
LOOMING_NOISE_FILES = {
    "pink": "Loom-1-pink-v1-padded.wav",
    "blue": "Loom-2-blue-v1-padded.wav",
    "white": "Loom-3-white-v1-padded.wav",
    "brown": "Loom-4-brown-v1-padded.wav",
}

# Like the breathing-instruction TTS, the four looming waveforms are
# pre-generated and played VERBATIM every trial (confirmed by reverse-
# engineering the stimulus pipeline). So the same deterministic cross-
# correlation trick used for Inhale/Exhale also works for looming: pick
# the max-scoring template at each peak, and its peak time is the
# looming onset in the recording.
LOOMING_TEMPLATE_MIN_SCORE = 0.20   # hard floor; adaptive threshold never goes below this
LOOMING_TEMPLATE_MAX_SCORE = 0.55   # hard ceiling for the adaptive threshold
LOOMING_TEMPLATE_EXPECTED_HITS = 300  # slight over-estimate of planned 288 (240 AT + 48 Catch)
LOOMING_TEMPLATE_MIN_SEPARATION_S = 6.0
LOOMING_TEMPLATE_DECIMATE = 4
# Cue-pairing window: a looming hit is considered to ANCHOR a tactile cue
# if the cue falls inside [peak_time + SOA_MIN, peak_time + SOA_MAX].
LOOMING_CUE_SOA_MIN_S = 0.20
LOOMING_CUE_SOA_MAX_S = 3.20

# The breathing instruction TTS files are FIXED â€” exactly the same audio is
# played every time the narrator says "Inhale / two / three / four / hold"
# or the Exhale equivalent. Background music is overlaid on top in the
# recording, but the TTS waveform itself is invariant. So we can do
# deterministic template matching: cross-correlate the source MP3 against
# the recording audio channel to locate every instance precisely. This is
# fully deterministic and much faster than any transcription-based approach.
BREATHING_INSTRUCTION_ROOT = PROJECT_ROOT / "assets" / "breathing"
BREATHING_INSTRUCTION_FILES = {
    "Inhale": "Inhale-2-3-4-hold_FIXED.wav",
    "Exhale": "Exhale-2-3-4-hold_FIXED.wav",
}
# Both templates are 4.037 s; the "hold" word starts around 3.5 s into each.
# Empirical burst analysis shows:
#   Inhale template: 'hold' burst at [3.445, 3.673] s
#   Exhale template: 'hold' burst at [3.550, 3.695] s
# Use a shared offset that lands inside both.
BREATHING_TEMPLATE_HOLD_OFFSET_S = 3.50

# Minimum normalized correlation for a breathing template peak to count.
# With numerically stable Pearson normalization on the raw 44.1 kHz audio,
# clean experimental breathing-instruction matches score 0.8-1.0. Ambient
# music / non-breathing sections of the recording score around 0.2. The
# 0.5 hard floor reliably separates the two in well-balanced recordings;
# the ADAPTIVE threshold (see detect_breathing_events_via_templates) picks
# a per-recording value between this floor and `BREATHING_TEMPLATE_MAX_SCORE`
# based on the shape of the correlation-peak distribution in the actual
# recording â€” so a quieter mic gain or louder music automatically gets a
# more permissive threshold.
BREATHING_TEMPLATE_MIN_SCORE = 0.30
BREATHING_TEMPLATE_MAX_SCORE = 0.60
BREATHING_TEMPLATE_EXPECTED_HITS = 450  # slight over-estimate: ~360 trials + warmup / inter-block
# Minimum absolute phase margin (inhale-head score minus exhale-head score)
# for the phase label to be considered confident. Below this we emit phase =
# "Unknown_template_ambiguous" so downstream code does not treat it as a
# trusted label.
BREATHING_TEMPLATE_MIN_PHASE_MARGIN = 0.15
# Downsample factor for the correlation. The TTS speech band is <4 kHz, so
# running the correlation at 44100 / 4 = 11025 Hz is lossless for this
# purpose and ~4x faster. Peak indices are converted back to the original
# sample rate.
BREATHING_TEMPLATE_DECIMATE = 4
# Minimum separation between adjacent breathing events (half a breathing
# cycle = 8 s; we use 6 s to be tolerant of timing jitter).
BREATHING_TEMPLATE_MIN_SEPARATION_S = 6.0
# For phase discrimination, use just the first ~0.8 s of each template
# (the distinguishing "Inhale" / "Exhale" portion; the "two three four hold"
# suffix is common to both). Primary detection still uses the full template
# for SNR; phase labeling at each peak uses the short discriminator.
BREATHING_DISCRIMINATOR_LENGTH_S = 0.80

# Output folders used by the unified pipeline. Every generated artifact
# lives under Output/ so the folder root stays source-only.
DECODED_DIAGNOSTICS_DIR = DIAGNOSTICS_DIR
DECODED_ANALYSIS_DIR = FINAL_DIR


def configure_paths(args: argparse.Namespace) -> None:
    """Apply CLI path overrides and refresh derived output directories."""
    global INPUT_DIR, OUTPUT_DIR, DIAGNOSTICS_DIR, FINAL_DIR, SUMMARIES_DIR
    global EVENT_INVENTORY_DIR, REFERENCE_SEQUENCE_ROOT, CLICK_TONE_PATH
    global LOOMING_NOISE_ROOT, BREATHING_INSTRUCTION_ROOT
    global DECODED_DIAGNOSTICS_DIR, DECODED_ANALYSIS_DIR

    if args.input_dir:
        INPUT_DIR = args.input_dir
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    if args.reference_sequence_root:
        REFERENCE_SEQUENCE_ROOT = args.reference_sequence_root
    if args.click_tone:
        CLICK_TONE_PATH = args.click_tone
    if args.looming_root:
        LOOMING_NOISE_ROOT = args.looming_root
    if args.breathing_dir:
        BREATHING_INSTRUCTION_ROOT = args.breathing_dir

    DIAGNOSTICS_DIR = OUTPUT_DIR / "diagnostics"
    FINAL_DIR = OUTPUT_DIR / "final"
    SUMMARIES_DIR = OUTPUT_DIR / "summaries"
    EVENT_INVENTORY_DIR = OUTPUT_DIR / "event_inventory"
    DECODED_DIAGNOSTICS_DIR = DIAGNOSTICS_DIR
    DECODED_ANALYSIS_DIR = FINAL_DIR

# Part split: gap in the middle of the recording that separates Part 1
# (viscereality VR) from Part 2 (minimal). Inter-block gaps within a
# session are typically â‰¤ 60 s, so 80 s reliably separates part boundaries
# from block boundaries. We additionally require the gap to fall inside
# the middle 20â€“80 % of the experimental window (handled below) so a
# participant pausing early doesn't get mistaken for a session boundary.
PART_SPLIT_MIN_GAP_S = 80.0

# Warmup cutoff fallback: when breathing templates are unavailable, everything
# before (first_tactile_cue_time - WARMUP_BUFFER_S) is treated as
# pre-experiment warmup / instructions. In normal production decoding the
# first standardized breathing-template hit is the experiment anchor instead.
WARMUP_BUFFER_S = 10.0

# Block-boundary heuristic.
BLOCK_GAP_THRESHOLD_S = 30.0

# Post-hold looming search window. The narrator says "hold" at the end of
# "Inhale / two / three / four / hold" (and likewise for Exhale). The looming
# stimulus is always played within 4 s of the hold. Max nominal SOA is 2700
# ms, so up to 2.7 s of audible looming before the cue.
HOLD_POST_WINDOW_S = 4.0

# Looming onset fallback window when "hold" was not transcribed. The cue is
# the anchor in that case, and we search backward up to 4 s.
LOOMING_FALLBACK_PRE_CUE_S = 4.0
LOOMING_FALLBACK_POST_CUE_S = 0.05

# Trial-type discrimination relies on a music-only reference slice of the
# post-hold window. The experimental timeline is:
#   trial[0 - ~4s]     : breathing instruction TTS
#   trial[~4 - ~4.5s]  : silent padding of the stimulus block (music only)
#   trial[~4.5 - cue]  : looming ramp (Audio-Tactile) or silence (Baseline)
#   cue                : tactile pulse fires
# The music-only slice [hold_word_end, hold_word_end + MUSIC_REF_S] sits
# inside the stimulus-block padding; it ALWAYS contains music alone (no
# looming yet) regardless of SOA. Comparing envelope RMS in the
# looming-possible window against envelope RMS in this music-only slice
# isolates the looming contribution cleanly.
MUSIC_REF_WINDOW_S = 0.60   # music-only reference slice after 'hold'
LOOMING_LEAD_GAP_S = 0.70   # gap between hold_word.end and looming-possible window start
PEAK_RATIO_THRESHOLD = 1.30
PEAK_RATIO_AMBIGUOUS_MAX = 1.15

# Click search: response must arrive within this many ms after the cue.
CLICK_SEARCH_POST_CUE_START_S = 0.030
CLICK_SEARCH_POST_CUE_END_S = 2.000

# Nominal SOAs (ms) for quantization of the raw measured SOA.
NOMINAL_SOAS_MS = (300, 800, 1500, 2200, 2700)

# Box-breathing paradigm constants. Each trial is an 8-second unit:
#   [Inhale|Exhale 4 s] + [hold 4 s, during which PPS events occur].
# Consecutive trials strictly alternate phase: Inhale, Exhale, Inhale, ...
# If the alternation breaks with a SHORT gap between tactile cues, it is an
# anomaly (missed template match, double-cued trial, or real protocol
# anomaly). If it breaks with a MEDIUM gap, a Catch trial (which has no
# tactile cue) likely sat between the two tactile trials and the phase swap
# skipped a slot.
TRIAL_UNIT_SECONDS = 8.0
BREATHING_CYCLE_SECONDS = 16.0  # Inhale+hold+Exhale+hold
PHASE_REPEAT_SHORT_GAP_MAX_S = 12.0    # below this, same-phase adjacent cues = anomaly
PHASE_REPEAT_CATCH_GAP_MAX_S = 20.0    # between short-gap and this: likely catch-skip

# PSD / spectral shape parameters.
PSD_NPERSEG = 4096  # roughly 93 ms at 44.1 kHz


# ---------------------------------------------------------------------------
# Self-contained signal helpers
# ---------------------------------------------------------------------------

@dataclass
class WavInfo:
    sample_rate: int
    channels: int
    sample_width: int
    nframes: int

    @property
    def duration_seconds(self) -> float:
        return self.nframes / float(self.sample_rate)


@dataclass
class EventRun:
    start_sample: int
    end_sample: int
    peak_abs: float
    threshold: float

    @property
    def duration_samples(self) -> int:
        return self.end_sample - self.start_sample

    def duration_ms(self, sample_rate: int) -> float:
        return self.duration_samples * 1000.0 / float(sample_rate)


@dataclass
class DetectionResult:
    response_detected: bool
    click_start_sample_abs: int | None
    click_start_seconds_abs: float | None
    click_corr_peak: float | None
    click_corr_threshold: float | None
    rt_ms: float | None
    outcome: str


def read_wav_info(path: Path) -> WavInfo:
    with closing(wave.open(str(path), "rb")) as wav_file:
        return WavInfo(
            sample_rate=wav_file.getframerate(),
            channels=wav_file.getnchannels(),
            sample_width=wav_file.getsampwidth(),
            nframes=wav_file.getnframes(),
        )


def read_wav_frames(
    path: Path,
    start_frame: int = 0,
    num_frames: int | None = None,
) -> tuple[np.ndarray, WavInfo]:
    info = read_wav_info(path)
    with closing(wave.open(str(path), "rb")) as wav_file:
        wav_file.setpos(start_frame)
        if num_frames is None:
            num_frames = info.nframes - start_frame
        raw = wav_file.readframes(num_frames)

    if info.sample_width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif info.sample_width == 4:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"Unsupported sample width for {path}: {info.sample_width}")

    if info.channels == 1:
        samples = samples.reshape(-1, 1)
    else:
        samples = samples.reshape(-1, info.channels)
    return samples, info


def smooth_abs_envelope(x: np.ndarray, window: int) -> np.ndarray:
    kernel = np.ones(window, dtype=np.float32) / float(window)
    return np.convolve(np.abs(x), kernel, mode="same")


def safe_standardize(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32, copy=False)
    x = x - float(np.mean(x))
    std = float(np.std(x))
    if std < 1e-8:
        return x
    return x / std


def mad(x: np.ndarray) -> float:
    med = float(np.median(x))
    return float(np.median(np.abs(x - med)))


def infer_recording_channel_roles(samples: np.ndarray) -> tuple[int, int]:
    if samples.shape[1] == 1:
        return 0, 0
    probe = samples[: min(len(samples), 44100 * 600)]
    rms = np.sqrt(np.mean(probe**2, axis=0))
    mean_abs = np.mean(np.abs(probe), axis=0)
    sparsity_ratio = mean_abs / np.maximum(rms, 1e-8)
    tactile_ch = int(np.argmin(sparsity_ratio))
    audio_candidates = [idx for idx in range(samples.shape[1]) if idx != tactile_ch]
    if not audio_candidates:
        return 0, 0
    audio_ch = int(max(audio_candidates, key=lambda idx: mean_abs[idx]))
    return audio_ch, tactile_ch


def detect_tactile_event_runs(
    tactile_signal: np.ndarray,
    sample_rate: int,
) -> tuple[list[EventRun], float]:
    if len(tactile_signal) == 0:
        return [], 0.0

    window = max(1, int(0.010 * sample_rate))
    env = smooth_abs_envelope(tactile_signal, window=window)
    env_peak = float(np.max(env)) if len(env) else 0.0
    threshold = max(0.08, min(0.35, env_peak * 0.45))
    above = env >= threshold
    edges = np.diff(above.astype(np.int8), prepend=0, append=0)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)

    runs: list[EventRun] = []
    for start, end in zip(starts, ends):
        if end <= start:
            continue
        peak = float(np.max(np.abs(tactile_signal[start:end])))
        if peak < 0.22:
            continue
        runs.append(
            EventRun(
                start_sample=int(start),
                end_sample=int(end),
                peak_abs=peak,
                threshold=threshold,
            )
        )
    return runs, threshold


def select_tactile_cue_runs(runs: Sequence[EventRun], sample_rate: int) -> list[EventRun]:
    min_samples = int(0.060 * sample_rate)
    return [
        run
        for run in runs
        if run.duration_samples >= min_samples and run.peak_abs >= 0.22
    ]


def _event_runs_from_envelope(
    tactile_signal: np.ndarray,
    envelope: np.ndarray,
    threshold: float,
    sample_offset: int = 0,
    min_peak_abs: float = 0.10,
) -> list[EventRun]:
    above = envelope >= threshold
    edges = np.diff(above.astype(np.int8), prepend=0, append=0)
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)

    runs: list[EventRun] = []
    for start, end in zip(starts, ends):
        if end <= start:
            continue
        peak = float(np.max(np.abs(tactile_signal[start:end])))
        if peak < min_peak_abs:
            continue
        runs.append(
            EventRun(
                start_sample=int(start + sample_offset),
                end_sample=int(end + sample_offset),
                peak_abs=peak,
                threshold=threshold,
            )
        )
    return runs


def _merge_event_runs(runs: Sequence[EventRun], sample_rate: int) -> list[EventRun]:
    if not runs:
        return []

    # Local-window detection intentionally overlaps. Merge runs that refer
    # to the same physical tactile pulse, while preserving truly distinct
    # cue/click pairs.
    max_gap = int(round(0.035 * sample_rate))
    merged: list[EventRun] = []
    for run in sorted(runs, key=lambda r: (r.start_sample, r.end_sample)):
        if not merged:
            merged.append(run)
            continue
        prev = merged[-1]
        if run.start_sample <= prev.end_sample + max_gap:
            merged[-1] = EventRun(
                start_sample=min(prev.start_sample, run.start_sample),
                end_sample=max(prev.end_sample, run.end_sample),
                peak_abs=max(prev.peak_abs, run.peak_abs),
                threshold=min(prev.threshold, run.threshold),
            )
        else:
            merged.append(run)
    return merged


def _cue_like_runs(runs: Sequence[EventRun], sample_rate: int) -> list[EventRun]:
    min_samples = int(round(0.055 * sample_rate))
    max_samples = int(round(0.180 * sample_rate))
    return [
        run
        for run in runs
        if min_samples <= run.duration_samples <= max_samples and run.peak_abs >= 0.10
    ]


def detect_tactile_cue_runs_adaptive(
    tactile_signal: np.ndarray,
    sample_rate: int,
) -> tuple[list[EventRun], dict[str, Any]]:
    """Recover tactile cue pulses before assigning trial labels.

    The original detector used a single threshold for the entire WAV. That
    fails when one part is recorded quieter than another: the weaker but
    plainly visible tactile pulses never become candidate events. This pass
    profiles the tactile channel in local windows and thresholds each window
    independently. Duration constraints keep the 1200 Hz, 50 ms response
    clicks out of the tactile-cue stream.
    """
    if len(tactile_signal) == 0:
        return [], {"method": "adaptive_local", "windows": 0, "threshold_min": 0.0, "threshold_max": 0.0}

    envelope_window = max(1, int(round(0.010 * sample_rate)))
    chunk_samples = max(envelope_window, int(round(300.0 * sample_rate)))
    overlap_samples = int(round(10.0 * sample_rate))
    thresholds: list[float] = []
    local_runs: list[EventRun] = []

    start = 0
    while start < len(tactile_signal):
        end = min(len(tactile_signal), start + chunk_samples)
        segment = tactile_signal[start:end]
        if len(segment) <= envelope_window:
            break
        env = smooth_abs_envelope(segment, window=envelope_window)
        env_peak = float(np.max(env)) if len(env) else 0.0
        if env_peak > 0:
            threshold = max(0.04, min(0.35, env_peak * 0.45))
            thresholds.append(threshold)
            local_runs.extend(
                _event_runs_from_envelope(
                    tactile_signal=segment,
                    envelope=env,
                    threshold=threshold,
                    sample_offset=start,
                    min_peak_abs=0.10,
                )
            )
        if end == len(tactile_signal):
            break
        start = max(end - overlap_samples, start + 1)

    merged = _merge_event_runs(local_runs, sample_rate)
    cue_runs = _cue_like_runs(merged, sample_rate)
    diagnostics = {
        "method": "adaptive_local",
        "windows": len(thresholds),
        "threshold_min": min(thresholds) if thresholds else 0.0,
        "threshold_max": max(thresholds) if thresholds else 0.0,
        "raw_runs": len(local_runs),
        "merged_runs": len(merged),
        "cue_runs": len(cue_runs),
    }
    return cue_runs, diagnostics


def load_click_template() -> tuple[np.ndarray, WavInfo]:
    click_samples, click_info = read_wav_frames(CLICK_TONE_PATH)
    return click_samples[:, 0], click_info


def detect_click_in_window(
    residual_tactile: np.ndarray,
    window_start_sample_abs: int,
    cue_sample_abs: int | None,
    trial_end_sample_abs: int,
    click_template: np.ndarray,
    sample_rate: int,
    trial_type: str,
    missing_outcome: str,
) -> DetectionResult:
    search_start_abs = window_start_sample_abs if cue_sample_abs is None else cue_sample_abs
    search_end_abs = trial_end_sample_abs
    if search_end_abs - search_start_abs <= len(click_template):
        return DetectionResult(False, None, None, None, None, None, missing_outcome)

    window = residual_tactile[search_start_abs:search_end_abs]
    click_z = safe_standardize(click_template)
    corr = np.correlate(window, click_z, mode="valid") / max(len(click_z), 1)
    local_med = float(np.median(corr))
    local_mad = mad(corr)
    threshold = max(0.04, local_med + 8.0 * max(local_mad, 1e-6))

    peak_idx = int(np.argmax(corr))
    peak_val = float(corr[peak_idx])
    if peak_val < threshold:
        return DetectionResult(
            False, None, None, peak_val, threshold, None, missing_outcome
        )

    click_start_abs = search_start_abs + peak_idx
    rt_ms = None
    outcome = "false_alarm" if trial_type == "Catch" else "hit"
    if cue_sample_abs is not None:
        rt_ms = (click_start_abs - cue_sample_abs) * 1000.0 / float(sample_rate)
        if rt_ms < 0:
            outcome = "precue_click"

    return DetectionResult(
        True,
        click_start_abs,
        click_start_abs / float(sample_rate),
        peak_val,
        threshold,
        rt_ms,
        outcome,
    )


class PPSShim:
    CLICK_MIN_SEPARATION_SECONDS = 0.10
    CLICK_MIN_CORR = 0.04
    CLICK_Z_THRESHOLD = 8.0

    read_wav_info = staticmethod(read_wav_info)
    read_wav_frames = staticmethod(read_wav_frames)
    smooth_abs_envelope = staticmethod(smooth_abs_envelope)
    safe_standardize = staticmethod(safe_standardize)
    mad = staticmethod(mad)
    infer_recording_channel_roles = staticmethod(infer_recording_channel_roles)
    detect_tactile_event_runs = staticmethod(detect_tactile_event_runs)
    select_tactile_cue_runs = staticmethod(select_tactile_cue_runs)
    detect_tactile_cue_runs_adaptive = staticmethod(detect_tactile_cue_runs_adaptive)
    load_click_template = staticmethod(load_click_template)
    detect_click_in_window = staticmethod(detect_click_in_window)


def load_pps_module() -> Any:
    return PPSShim


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def participant_id_from_filename(path: Path) -> str | None:
    """Map P10_MelinaTaboritzki.wav â†’ 'P10'; 22_LareReichel.wav â†’ 'P22'."""
    stem = path.stem
    m = re.match(r"^[Pp](\d{1,2})(?:[_\-\s]|$)", stem)
    if m:
        number = int(m.group(1))
        return None if number <= 0 else f"P{number:02d}"
    m = re.match(r"^(\d{1,2})(?:[_\-\s]|$)", stem)
    if m:
        number = int(m.group(1))
        return None if number <= 0 else f"P{number:02d}"
    return None


def participant_number_from_filename(path: Path) -> int | str:
    participant_id = participant_id_from_filename(path)
    return "" if not participant_id else int(participant_id[1:])


def experiment_half_from_part(part_number: object) -> str:
    try:
        part = int(part_number)
    except (TypeError, ValueError):
        return ""
    if part == 1:
        return "first_half"
    if part == 2:
        return "second_half"
    return ""


def condition_from_part(part_number: object) -> str:
    try:
        part = int(part_number)
    except (TypeError, ValueError):
        return ""
    if part == 1:
        return "Viscereality"
    if part == 2:
        return "Control"
    return ""


def canonical_output_stem(path: Path) -> str:
    """Normalize output filenames so every participant file starts with a
    canonical ``P##`` prefix while preserving the human-readable suffix from
    the source WAV name.
    """
    participant_id = participant_id_from_filename(path)
    if not participant_id:
        return path.stem
    suffix = re.sub(r"^(?:[Pp]?\d{1,2})(?:[_\-\s]+)?", "", path.stem).strip()
    suffix = suffix.strip("_- ")
    return participant_id if not suffix else f"{participant_id}_{suffix}"


def natural_key(path: Path) -> list[Any]:
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def should_process(path: Path, only_patterns: list[str]) -> bool:
    if not only_patterns:
        return True
    lower_name = path.name.lower()
    lower_stem = path.stem.lower()
    participant_id = (participant_id_from_filename(path) or "").lower()
    for raw_pattern in only_patterns:
        pattern = raw_pattern.strip().lower()
        if not pattern:
            continue
        if re.fullmatch(r"p?\d{1,2}", pattern):
            digits = re.sub(r"\D", "", pattern)
            expected_pid = f"p{int(digits):02d}"
            if participant_id == expected_pid:
                return True
            if re.match(rf"^{re.escape(pattern)}(?:[_\\-\\s]|$)", lower_stem):
                return True
            continue
        if pattern in (lower_name, lower_stem, participant_id):
            return True
        if pattern in lower_stem:
            return True
    return False


def write_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row.keys():
                if key not in seen:
                    seen.add(key)
                    ordered.append(key)
        fieldnames = ordered
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _nearest_cue_part_number(
    catch_time_s: float,
    cue_times_s: list[float],
    parts: list[int],
) -> int:
    """Return the part_number of the tactile cue adjacent (either side) to
    the given catch-trial time. Used when emitting Catch rows so they get
    the same Part 1 / Part 2 labelling as their neighbouring tactile cues.
    """
    if not cue_times_s or not parts:
        return 1
    import bisect
    idx = bisect.bisect_left(cue_times_s, catch_time_s)
    if idx == 0:
        return parts[0]
    if idx >= len(cue_times_s):
        return parts[-1]
    # Pick whichever neighbour is temporally closer.
    before_gap = catch_time_s - cue_times_s[idx - 1]
    after_gap = cue_times_s[idx] - catch_time_s
    return parts[idx - 1] if before_gap <= after_gap else parts[idx]


def quantize_soa_ms(raw_soa_ms: float) -> tuple[int, float]:
    nominal = min(NOMINAL_SOAS_MS, key=lambda s: abs(raw_soa_ms - s))
    return int(nominal), float(raw_soa_ms - nominal)


def format_rt_ms(value: Any) -> int | str:
    if value in ("", None):
        return ""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return ""


FINAL_FIELDNAMES = [
    "participant_id",
    "participant_number",
    "recording_file",
    "experiment_half",
    "condition",
    "part_number",
    "block_number",
    "trial_number",
    "trial_number_global",
    "tactile_event",
    "tactile_cue_time_s",
    "trial_type",
    "looming_detected",
    "phase",
    "phase_alternation_check",
    "SOA_ms",
    "SOA_raw_ms",
    "noise_type",
    "reaction_time_ms",
    "response_detected",
    "outcome",
    "data_source",
]

QC_NOMINAL_SOAS = ("soa_300ms", "soa_800ms", "soa_1500ms", "soa_2200ms", "soa_2700ms")


# ---------------------------------------------------------------------------
# Simple anchor used only by the looming fallback path. The primary decoder
# no longer depends on any ASR system.
# ---------------------------------------------------------------------------

@dataclass
class AnchorWord:
    text: str
    start: float
    end: float
    probability: float


# ---------------------------------------------------------------------------
# Deterministic breathing-instruction template matching
# ---------------------------------------------------------------------------

@dataclass
class BreathingTemplateHit:
    phase: str              # Inhale or Exhale
    start_sample: int       # onset of the TTS instruction in the recording
    start_s: float
    hold_sample: int        # onset of the 'hold' word inside this instance
    hold_s: float
    score: float            # normalized correlation at detection
    phase_margin: float     # inhale-score minus exhale-score at this offset (signed)


def first_breathing_anchor_hit(
    template_hits: Sequence[BreathingTemplateHit],
) -> BreathingTemplateHit | None:
    """Return the first standardized breathing instruction that anchors a run.

    The experiment blocks are rendered from fixed audio. Prefer the first
    detected Inhale phrase because the protocol begins with "Inhale two three
    four hold"; if that phase is missing, fall back to the earliest breathing
    template so recordings with imperfect phase discrimination still get a
    protocol-based anchor.
    """
    if not template_hits:
        return None
    ordered = sorted(template_hits, key=lambda hit: hit.start_s)
    for hit in ordered:
        if hit.phase == "Inhale":
            return hit
    return ordered[0]


def _decode_mp3_to_mono_float(path: Path, target_sample_rate: int) -> np.ndarray:
    """Decode an MP3 to mono float32 at the target sample rate via ffmpeg.

    ffmpeg is already on PATH on the lab machine. Returns samples in [-1, 1].
    """
    import subprocess, io
    r = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-i", str(path),
            "-f", "wav", "-ac", "1", "-ar", str(target_sample_rate), "pipe:1",
        ],
        capture_output=True,
        check=False,
    )
    if r.returncode != 0 or not r.stdout:
        raise RuntimeError(
            f"ffmpeg failed to decode {path.name}: {r.stderr.decode(errors='replace')[:400]}"
        )
    with wave.open(io.BytesIO(r.stdout), "rb") as w:
        frames = w.readframes(w.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    return audio


def load_breathing_templates(sample_rate: int) -> dict[str, np.ndarray] | None:
    """Load the Inhale / Exhale TTS templates as mono float32 at sample_rate.

    Returns a dict ``{"Inhale": samples, "Exhale": samples,
    "Inhale_head": ..., "Exhale_head": ...}`` where ``*_head`` is the first
    ~0.8 s used for phase discrimination. Returns None if any template is
    missing so the caller can fall back cleanly.
    """
    out: dict[str, np.ndarray] = {}
    for phase, filename in BREATHING_INSTRUCTION_FILES.items():
        path = BREATHING_INSTRUCTION_ROOT / filename
        if not path.exists():
            return None
        samples = _decode_mp3_to_mono_float(path, sample_rate)
        # Trim trailing silence so correlation isn't diluted.
        env = np.abs(samples)
        nonzero = np.flatnonzero(env > 0.01 * env.max())
        if len(nonzero) >= 2:
            samples = samples[nonzero[0]: nonzero[-1] + 1]
        out[phase] = samples.astype(np.float32, copy=False)
        head_len = int(round(BREATHING_DISCRIMINATOR_LENGTH_S * sample_rate))
        out[f"{phase}_head"] = samples[:head_len].astype(np.float32, copy=False)
    return out


def _adaptive_threshold_from_peak_distribution(
    correlation: np.ndarray,
    expected_count: int,
    min_distance_samples: int,
    floor: float,
    ceiling: float,
    low_floor_for_peak_pick: float = 0.15,
) -> float:
    """Self-calibrating threshold: pick the score of the ``expected_count``-th
    best correlation peak and clamp to ``[floor, ceiling]``.

    The underlying idea: every recording has a characteristic correlation
    distribution shaped by its music-to-signal ratio. Recordings with
    loud music have lower real-hit correlations (fundamental property of
    Pearson correlation against an additive-noise signal). Instead of
    guessing a threshold, we let the recording itself tell us where the
    transition from real hits to noise happens: the ``expected_count``-th
    best peak sits right at that boundary if our prior on the event count
    is even approximately correct.

    This is robust even if the prior is off by 30 %: the clamp
    ``[floor, ceiling]`` bounds the result. And the floor is the hard
    "never accept matches this weak" rule.
    """
    try:
        from scipy.signal import find_peaks
    except Exception:
        return floor

    peaks, _ = find_peaks(correlation, height=low_floor_for_peak_pick, distance=min_distance_samples)
    if len(peaks) == 0:
        return floor
    peak_scores = correlation[peaks]
    if len(peak_scores) <= expected_count:
        # Fewer peaks than the prior â€” recording is short or matches are
        # weak. Use the weakest peak as the threshold (accept all).
        adaptive = float(np.min(peak_scores))
    else:
        sorted_scores = np.sort(peak_scores)[::-1]
        adaptive = float(sorted_scores[expected_count - 1])
    return max(floor, min(ceiling, adaptive))


def _normalized_crosscorrelate(signal: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Sliding Pearson correlation between ``template`` and each length-N
    window of ``signal``, returned in valid mode (length ``len(signal) -
    N + 1``). Output values are bounded in [-1, 1].

    Numerically stable implementation: uses ``fftconvolve`` in float64 for
    the numerator AND for the sliding sum / sum-of-squares. (Cumulative
    sums over ~190M float32 samples lose precision catastrophically and
    produce correlations with absolute values in the millions. Don't.)
    """
    from scipy.signal import fftconvolve

    s = signal.astype(np.float64, copy=False)
    t = template.astype(np.float64, copy=False)
    n = len(t)
    if n == 0 or len(s) < n:
        return np.zeros(max(0, len(s) - n + 1), dtype=np.float32)

    t_centered = t - float(np.mean(t))
    t_norm = float(np.sqrt(np.sum(t_centered * t_centered)))
    if t_norm <= 0:
        return np.zeros(len(s) - n + 1, dtype=np.float32)

    ones = np.ones(n, dtype=np.float64)
    # Sliding sum and sum-of-squares of the signal (valid mode).
    s_sum = fftconvolve(s, ones, mode="valid")
    s_sq_sum = fftconvolve(s * s, ones, mode="valid")
    s_mean = s_sum / float(n)
    s_var = s_sq_sum / float(n) - s_mean * s_mean
    s_var = np.clip(s_var, 0.0, None)
    s_norm = np.sqrt(s_var * float(n))

    # Numerator: sum over the window of s_slice * t_centered. Because
    # t_centered has zero mean, this equals the centered cross-product.
    num = fftconvolve(s, t_centered[::-1], mode="valid")

    denom = s_norm * t_norm
    denom = np.where(denom > 1e-12, denom, 1e-12)
    r = num / denom
    return np.clip(r, -1.0, 1.0).astype(np.float32)


def detect_breathing_events_via_templates(
    audio_signal: np.ndarray,
    sample_rate: int,
    templates: dict[str, np.ndarray],
    min_score: float = BREATHING_TEMPLATE_MIN_SCORE,
    min_separation_s: float = BREATHING_TEMPLATE_MIN_SEPARATION_S,
    hold_offset_s: float = BREATHING_TEMPLATE_HOLD_OFFSET_S,
    decimate: int = BREATHING_TEMPLATE_DECIMATE,
) -> list[BreathingTemplateHit]:
    """Deterministically locate every Inhale/Exhale TTS instance in the
    audio channel by cross-correlating the full templates.

    Fast path: we decimate the audio and the templates by ``decimate`` (4Ã—
    â†’ 11025 Hz) before correlating. The TTS band is below 4 kHz so this is
    lossless for our purpose and ~4Ã— faster. Peak sample indices are
    converted back to the original sample rate for the returned hits.

    For every peak above ``min_score`` that is separated from neighbouring
    peaks by at least ``min_separation_s``, we decide the phase by
    comparing the short discriminator-head scores (first ~0.8 s of each,
    where 'Inhale' vs 'Exhale' actually differs) at that same offset.
    """
    try:
        from scipy.signal import find_peaks, resample_poly
    except Exception:
        return []

    if decimate and decimate > 1:
        ds = int(decimate)
        # Anti-alias + decimate the signal and all four templates in lockstep.
        audio_ds = resample_poly(audio_signal.astype(np.float32, copy=False), 1, ds)
        templates_ds = {
            "Inhale": resample_poly(templates["Inhale"], 1, ds).astype(np.float32),
            "Exhale": resample_poly(templates["Exhale"], 1, ds).astype(np.float32),
            "Inhale_head": resample_poly(templates["Inhale_head"], 1, ds).astype(np.float32),
            "Exhale_head": resample_poly(templates["Exhale_head"], 1, ds).astype(np.float32),
        }
        ds_sample_rate = sample_rate // ds
    else:
        ds = 1
        audio_ds = audio_signal.astype(np.float32, copy=False)
        templates_ds = templates
        ds_sample_rate = sample_rate

    inhale_full = templates_ds["Inhale"]
    exhale_full = templates_ds["Exhale"]
    inhale_head = templates_ds["Inhale_head"]
    exhale_head = templates_ds["Exhale_head"]

    cc_inhale_full = _normalized_crosscorrelate(audio_ds, inhale_full)
    cc_exhale_full = _normalized_crosscorrelate(audio_ds, exhale_full)

    n = min(len(cc_inhale_full), len(cc_exhale_full))
    cc_inhale_full = cc_inhale_full[:n]
    cc_exhale_full = cc_exhale_full[:n]
    combined = np.maximum(cc_inhale_full, cc_exhale_full)

    min_distance_samples_ds = max(1, int(round(min_separation_s * ds_sample_rate)))

    # Adaptive threshold: let the recording's own correlation distribution
    # dictate where the boundary between real breathing matches and noise
    # sits. The static ``min_score`` argument acts as a hard floor; the
    # adaptive threshold is the max of that floor and the peak-distribution
    # estimate, clamped at BREATHING_TEMPLATE_MAX_SCORE.
    adaptive_thr = _adaptive_threshold_from_peak_distribution(
        combined,
        expected_count=BREATHING_TEMPLATE_EXPECTED_HITS,
        min_distance_samples=min_distance_samples_ds,
        floor=max(min_score, BREATHING_TEMPLATE_MIN_SCORE),
        ceiling=BREATHING_TEMPLATE_MAX_SCORE,
    )
    peaks, _props = find_peaks(combined, height=adaptive_thr, distance=min_distance_samples_ds)
    if len(peaks) == 0:
        return []

    def _head_score_at(peak_ds: int, head: np.ndarray) -> float:
        end = peak_ds + len(head)
        if end > len(audio_ds):
            return float("-inf")
        window = audio_ds[peak_ds:end]
        wc = window - float(np.mean(window))
        w_norm = float(np.sqrt(np.sum(wc * wc)))
        h = head - float(np.mean(head))
        h_norm = float(np.sqrt(np.sum(h * h)))
        if w_norm <= 1e-12 or h_norm <= 1e-12:
            return 0.0
        return float(np.sum(wc * h) / (w_norm * h_norm))

    hits: list[BreathingTemplateHit] = []
    for peak_ds in peaks:
        peak_ds = int(peak_ds)
        inh_head_score = _head_score_at(peak_ds, inhale_head)
        exh_head_score = _head_score_at(peak_ds, exhale_head)
        phase = "Inhale" if inh_head_score >= exh_head_score else "Exhale"
        phase_margin = inh_head_score - exh_head_score
        score = float(cc_inhale_full[peak_ds] if phase == "Inhale" else cc_exhale_full[peak_ds])
        # Convert peak index back to the original sample-rate indexing.
        peak_full = peak_ds * ds
        hold_sample = peak_full + int(round(hold_offset_s * sample_rate))
        hits.append(
            BreathingTemplateHit(
                phase=phase,
                start_sample=peak_full,
                start_s=peak_full / float(sample_rate),
                hold_sample=hold_sample,
                hold_s=hold_sample / float(sample_rate),
                score=score,
                phase_margin=phase_margin,
            )
        )
    return hits


def find_breathing_hit_before_cue(
    cue_time_s: float,
    hits: list[BreathingTemplateHit],
    max_pre_cue_s: float = 10.0,
    min_pre_cue_s: float = 0.05,
    earliest_hold_s: float = 0.0,
) -> BreathingTemplateHit | None:
    """Return the most recent breathing template hit whose ``hold_s`` lies
    in ``(earliest_hold_s, cue_time_s - min_pre_cue_s]`` and within
    ``cue_time_s - max_pre_cue_s`` of the cue.

    ``earliest_hold_s`` is the crucial cross-trial constraint: when
    decoding cue N+1 we pass the previous cue's time here so a single
    breathing hit cannot be claimed as the anchor for two consecutive
    cues. If the breathing template matcher missed the Exhale/Inhale
    instance that should have sat between cue N and cue N+1, the lookup
    for N+1 returns None and phase = Unknown, which is honest.
    """
    best: BreathingTemplateHit | None = None
    latest = -math.inf
    window_start = max(cue_time_s - max_pre_cue_s, earliest_hold_s)
    window_end = cue_time_s - min_pre_cue_s
    for hit in hits:
        if hit.hold_s <= window_start or hit.hold_s > window_end:
            continue
        if hit.hold_s > latest:
            latest = hit.hold_s
            best = hit
    return best


# ---------------------------------------------------------------------------
# Deterministic LOOMING template matching (same approach as breathing,
# applied to the pre-generated Loom-*-v1-padded WAVs). This is the primary
# Audio-Tactile detector AND noise-type classifier AND SOA measurer.
# ---------------------------------------------------------------------------

@dataclass
class LoomingTemplateHit:
    noise_type: str          # "pink" | "blue" | "white" | "brown"
    start_sample: int        # looming noise onset in the recording
    start_s: float
    score: float             # normalized cross-correlation at peak
    runner_up_score: float   # second-best template score at this peak
    # Tactile-cue pairing populated after cues are known:
    paired_cue_sample: int | None = None
    paired_cue_time_s: float | None = None
    soa_ms: float | None = None


def load_looming_waveform_templates(sample_rate: int, pps: Any) -> dict[str, np.ndarray] | None:
    """Load the four Loom-*-v1-padded.wav files as mono float32 templates
    at the recording's sample rate, with leading/trailing silence trimmed.

    The RIGHT channel is used (per the reverse-engineered stimulus
    pipeline, the right channel of the source WAV is what plays on the
    audio output). Returns None if any template is missing.
    """
    out: dict[str, np.ndarray] = {}
    for colour, filename in LOOMING_NOISE_FILES.items():
        path = LOOMING_NOISE_ROOT / filename
        if not path.exists():
            return None
        samples, info = pps.read_wav_frames(path)
        if info.sample_rate != sample_rate:
            # Leave a loud clue if sample-rate-wise mismatch; callers can
            # detect None and gracefully fall back, but in practice the
            # pilot recordings are all 44.1 kHz so this branch is unused.
            return None
        mono = samples[:, 1] if samples.shape[1] > 1 else samples[:, 0]
        mono = mono.astype(np.float32, copy=False)
        env = np.abs(mono)
        if env.size == 0 or env.max() <= 0:
            return None
        nonzero = np.flatnonzero(env > 0.005 * env.max())
        if len(nonzero) < 2:
            return None
        out[colour] = mono[nonzero[0]: nonzero[-1] + 1]
    return out


def detect_looming_events_via_templates(
    audio_signal: np.ndarray,
    sample_rate: int,
    templates: dict[str, np.ndarray],
    min_score: float = LOOMING_TEMPLATE_MIN_SCORE,
    min_separation_s: float = LOOMING_TEMPLATE_MIN_SEPARATION_S,
    decimate: int = LOOMING_TEMPLATE_DECIMATE,
) -> list[LoomingTemplateHit]:
    """Locate every looming instance in the audio channel by correlating
    the four noise-colour templates and peak-finding on the per-sample
    maximum. At each peak the winning template determines noise_type, and
    the peak time is the looming onset.

    Fast path: we decimate by 4 (44.1 kHz -> 11.025 kHz) before
    correlating. Looming noise is broadband but mostly below 4 kHz for our
    purposes; decimation to 11 kHz keeps the discriminating spectral
    content intact and is ~4x faster. Peak indices are converted back to
    the original sample rate for the returned hits.
    """
    try:
        from scipy.signal import find_peaks, resample_poly
    except Exception:
        return []

    if not templates:
        return []

    if decimate and decimate > 1:
        ds = int(decimate)
        audio_ds = resample_poly(audio_signal.astype(np.float32, copy=False), 1, ds)
        templates_ds = {
            c: resample_poly(t, 1, ds).astype(np.float32, copy=False)
            for c, t in templates.items()
        }
        ds_sample_rate = sample_rate // ds
    else:
        ds = 1
        audio_ds = audio_signal.astype(np.float32, copy=False)
        templates_ds = {c: t.astype(np.float32, copy=False) for c, t in templates.items()}
        ds_sample_rate = sample_rate

    # Cross-correlate each template against the full (decimated) audio.
    ccs: dict[str, np.ndarray] = {}
    for colour, tpl in templates_ds.items():
        ccs[colour] = _normalized_crosscorrelate(audio_ds, tpl)

    # Truncate to the common length and stack.
    n = min(len(c) for c in ccs.values())
    colours = list(ccs.keys())
    mat = np.stack([ccs[c][:n] for c in colours], axis=0)  # [4, n]
    combined = mat.max(axis=0)
    winners = mat.argmax(axis=0)

    min_distance_samples = max(1, int(round(min_separation_s * ds_sample_rate)))

    # Adaptive threshold: let the recording's own correlation distribution
    # dictate the looming acceptance threshold. This is the only way to
    # make P05/P06/P08-style under-detecting recordings recover without a
    # per-recording hand-tuning. The static ``min_score`` argument is the
    # hard floor; the adaptive threshold clamps between it and the ceiling.
    adaptive_thr = _adaptive_threshold_from_peak_distribution(
        combined,
        expected_count=LOOMING_TEMPLATE_EXPECTED_HITS,
        min_distance_samples=min_distance_samples,
        floor=max(min_score, LOOMING_TEMPLATE_MIN_SCORE),
        ceiling=LOOMING_TEMPLATE_MAX_SCORE,
    )
    peaks, _props = find_peaks(combined, height=adaptive_thr, distance=min_distance_samples)
    if len(peaks) == 0:
        return []

    hits: list[LoomingTemplateHit] = []
    for pk_ds in peaks:
        pk_ds = int(pk_ds)
        winner_idx = int(winners[pk_ds])
        winner_colour = colours[winner_idx]
        winner_score = float(mat[winner_idx, pk_ds])
        # Second-best score at this same offset (for confidence margin).
        col_scores = mat[:, pk_ds].copy()
        col_scores[winner_idx] = -np.inf
        runner_up = float(col_scores.max()) if np.isfinite(col_scores).any() else 0.0
        peak_full = pk_ds * ds
        hits.append(
            LoomingTemplateHit(
                noise_type=winner_colour,
                start_sample=peak_full,
                start_s=peak_full / float(sample_rate),
                score=winner_score,
                runner_up_score=runner_up,
            )
        )
    return hits


def pair_looming_hits_with_cues(
    hits: list[LoomingTemplateHit],
    cue_samples: list[int],
    sample_rate: int,
    soa_min_s: float = LOOMING_CUE_SOA_MIN_S,
    soa_max_s: float = LOOMING_CUE_SOA_MAX_S,
) -> dict[str, int]:
    """One-to-one pairing between detected looming and tactile events.

    The physical event streams are decoded first. Pairing then asks whether
    each looming onset has exactly one plausible tactile cue at a nominal SOA.
    Greedy matching by SOA quantization error prevents several looming hits
    from claiming the same tactile event and leaves unmatched looming events
    as Catch candidates.
    """
    for hit in hits:
        hit.paired_cue_sample = None
        hit.paired_cue_time_s = None
        hit.soa_ms = None

    cue_samples_sorted = sorted(cue_samples)
    import bisect

    candidates: list[tuple[float, float, int, int, int, float]] = []
    for hit_idx, hit in enumerate(hits):
        window_start_sample = hit.start_sample + int(round(soa_min_s * sample_rate))
        window_end_sample = hit.start_sample + int(round(soa_max_s * sample_rate))
        start_idx = bisect.bisect_left(cue_samples_sorted, window_start_sample)
        end_idx = bisect.bisect_right(cue_samples_sorted, window_end_sample)
        for cue_idx in range(start_idx, end_idx):
            cue_sample = cue_samples_sorted[cue_idx]
            raw_soa_ms = (cue_sample - hit.start_sample) * 1000.0 / float(sample_rate)
            _nominal, soa_error_ms = quantize_soa_ms(raw_soa_ms)
            candidates.append(
                (
                    abs(soa_error_ms),
                    -float(hit.score),
                    int(hit.start_sample),
                    hit_idx,
                    cue_sample,
                    raw_soa_ms,
                )
            )

    claimed_hits: set[int] = set()
    claimed_cues: set[int] = set()
    for _error, _neg_score, _start, hit_idx, cue_sample, raw_soa_ms in sorted(candidates):
        if hit_idx in claimed_hits or cue_sample in claimed_cues:
            continue
        hit = hits[hit_idx]
        hit.paired_cue_sample = cue_sample
        hit.paired_cue_time_s = cue_sample / float(sample_rate)
        hit.soa_ms = raw_soa_ms
        claimed_hits.add(hit_idx)
        claimed_cues.add(cue_sample)

    return {
        "looming_events": len(hits),
        "tactile_events": len(cue_samples_sorted),
        "paired_events": len(claimed_hits),
        "unpaired_looming_events": len(hits) - len(claimed_hits),
        "unpaired_tactile_events": len(cue_samples_sorted) - len(claimed_cues),
        "pair_candidates": len(candidates),
    }


def find_looming_hit_for_cue(
    cue_sample: int,
    hits: list[LoomingTemplateHit],
) -> LoomingTemplateHit | None:
    """Reverse lookup: given a tactile cue sample, find the looming hit
    (if any) that claimed this cue during pair_looming_hits_with_cues."""
    for hit in hits:
        if hit.paired_cue_sample == cue_sample:
            return hit
    return None


def write_event_pairing_inventory(
    recording_wav: Path,
    cue_runs: Sequence[EventRun],
    cue_parts: Sequence[int],
    cue_blocks: Sequence[int],
    cue_trials: Sequence[int],
    looming_hits: Sequence[LoomingTemplateHit],
    breathing_hits: Sequence[BreathingTemplateHit],
    sample_rate: int,
) -> Path:
    """Write the physical-event audit table for one recording.

    This table is intentionally closer to the WAV than the trial CSV. It has
    one row per recovered tactile cue and one row per recovered looming onset,
    with explicit one-to-one pairing status. It lets us audit whether a trial
    was missed because an event was not detected, or because pairing/labeling
    failed later.
    """
    rows: list[dict[str, Any]] = []
    cue_to_looming = {
        int(hit.paired_cue_sample): hit
        for hit in looming_hits
        if hit.paired_cue_sample is not None
    }
    cue_times_s = [run.start_sample / float(sample_rate) for run in cue_runs]

    for idx, cue_run in enumerate(cue_runs):
        cue_sample = int(cue_run.start_sample)
        cue_time_s = cue_sample / float(sample_rate)
        part_number = cue_parts[idx] if idx < len(cue_parts) else ""
        block_number = cue_blocks[idx] if idx < len(cue_blocks) else ""
        trial_number = cue_trials[idx] if idx < len(cue_trials) else ""
        loom_hit = cue_to_looming.get(cue_sample)
        breath_hit = find_breathing_hit_before_cue(cue_time_s, list(breathing_hits))
        raw_soa = "" if loom_hit is None or loom_hit.soa_ms is None else float(loom_hit.soa_ms)
        nominal_soa = ""
        soa_error = ""
        if raw_soa != "":
            nominal_soa, soa_error = quantize_soa_ms(float(raw_soa))
        rows.append(
            {
                "recording_file": recording_wav.name,
                "event_stream": "tactile",
                "event_index": idx + 1,
                "event_time_s": round(cue_time_s, 6),
                "event_sample": cue_sample,
                "part_number": part_number,
                "block_number": block_number,
                "trial_number": trial_number,
                "experiment_half": experiment_half_from_part(part_number),
                "condition": condition_from_part(part_number),
                "phase": "" if breath_hit is None else breath_hit.phase,
                "paired": loom_hit is not None,
                "pair_status": "paired_audio_tactile" if loom_hit is not None else "unpaired_tactile_baseline",
                "paired_event_stream": "looming" if loom_hit is not None else "",
                "paired_event_time_s": "" if loom_hit is None else round(float(loom_hit.start_s), 6),
                "paired_event_sample": "" if loom_hit is None else int(loom_hit.start_sample),
                "looming_detected": loom_hit is not None,
                "noise_type": "N/A" if loom_hit is None else loom_hit.noise_type,
                "SOA_ms": nominal_soa,
                "SOA_raw_ms": "" if raw_soa == "" else round(float(raw_soa), 2),
                "SOA_quantization_error_ms": "" if soa_error == "" else round(float(soa_error), 2),
                "event_peak_abs": round(float(cue_run.peak_abs), 6),
                "event_threshold": round(float(cue_run.threshold), 6),
                "event_duration_ms": round(cue_run.duration_ms(sample_rate), 3),
                "template_score": "",
                "template_runner_up_score": "",
            }
        )

    for idx, hit in enumerate(looming_hits):
        paired = hit.paired_cue_sample is not None
        paired_time = "" if hit.paired_cue_time_s is None else float(hit.paired_cue_time_s)
        part_number = _nearest_cue_part_number(hit.start_s, cue_times_s, list(cue_parts))
        raw_soa = "" if hit.soa_ms is None else float(hit.soa_ms)
        nominal_soa = ""
        soa_error = ""
        if raw_soa != "":
            nominal_soa, soa_error = quantize_soa_ms(float(raw_soa))
        breath_hit = find_breathing_hit_before_cue(hit.start_s, list(breathing_hits))
        rows.append(
            {
                "recording_file": recording_wav.name,
                "event_stream": "looming",
                "event_index": idx + 1,
                "event_time_s": round(float(hit.start_s), 6),
                "event_sample": int(hit.start_sample),
                "part_number": part_number,
                "block_number": "",
                "trial_number": "",
                "experiment_half": experiment_half_from_part(part_number),
                "condition": condition_from_part(part_number),
                "phase": "" if breath_hit is None else breath_hit.phase,
                "paired": paired,
                "pair_status": "paired_audio_tactile" if paired else "unpaired_looming_catch",
                "paired_event_stream": "tactile" if paired else "",
                "paired_event_time_s": "" if paired_time == "" else round(paired_time, 6),
                "paired_event_sample": "" if hit.paired_cue_sample is None else int(hit.paired_cue_sample),
                "looming_detected": True,
                "noise_type": hit.noise_type,
                "SOA_ms": nominal_soa,
                "SOA_raw_ms": "" if raw_soa == "" else round(float(raw_soa), 2),
                "SOA_quantization_error_ms": "" if soa_error == "" else round(float(soa_error), 2),
                "event_peak_abs": "",
                "event_threshold": "",
                "event_duration_ms": "",
                "template_score": round(float(hit.score), 6),
                "template_runner_up_score": round(float(hit.runner_up_score), 6),
            }
        )

    inventory_path = EVENT_INVENTORY_DIR / f"{canonical_output_stem(recording_wav)}.events.csv"
    fieldnames = [
        "recording_file",
        "event_stream",
        "event_index",
        "event_time_s",
        "event_sample",
        "part_number",
        "block_number",
        "trial_number",
        "experiment_half",
        "condition",
        "phase",
        "paired",
        "pair_status",
        "paired_event_stream",
        "paired_event_time_s",
        "paired_event_sample",
        "looming_detected",
        "noise_type",
        "SOA_ms",
        "SOA_raw_ms",
        "SOA_quantization_error_ms",
        "event_peak_abs",
        "event_threshold",
        "event_duration_ms",
        "template_score",
        "template_runner_up_score",
    ]
    rows.sort(key=lambda row: (float(row["event_time_s"]), str(row["event_stream"])))
    write_rows(inventory_path, rows, fieldnames=fieldnames)
    return inventory_path


# ---------------------------------------------------------------------------
# Noise-colour spectral templates (derived from source looming WAVs)
# ---------------------------------------------------------------------------

def build_noise_spectral_templates(
    sample_rate: int,
    pps: Any,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Compute a normalized PSD per noise colour using the last second of
    each looming WAV (the final ramp-up, where the noise is loudest).
    """
    try:
        from scipy.signal import welch
    except Exception as exc:
        raise RuntimeError("scipy is required for noise-type classification") from exc

    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for colour, filename in LOOMING_NOISE_FILES.items():
        path = LOOMING_NOISE_ROOT / filename
        if not path.exists():
            continue
        samples, info = pps.read_wav_frames(path)
        mono = samples[:, 1 if samples.shape[1] > 1 else 0].astype(np.float32)
        tail = mono[-int(1.0 * info.sample_rate):]
        if len(tail) < PSD_NPERSEG:
            continue
        f, P = welch(tail, fs=info.sample_rate, nperseg=PSD_NPERSEG)
        # Normalize so the PSD shape is what we compare, not overall level.
        P = P / max(float(P.sum()), 1e-12)
        out[colour] = (f, P.astype(np.float32))
    return out


def bhattacharyya_coefficient(p: np.ndarray, q: np.ndarray) -> float:
    """Similarity between two normalized distributions, in [0, 1]."""
    return float(np.sum(np.sqrt(np.clip(p, 0.0, None) * np.clip(q, 0.0, None))))


# ---------------------------------------------------------------------------
# Looming detection using the "hold" anchor
# ---------------------------------------------------------------------------

@dataclass
class LoomingVerdict:
    detected: bool
    trial_type_confidence: str  # "high" | "medium" | "low_no_hold_anchor"
    peak_ratio: float           # primary: env peak over post-hold / ref RMS
    ramp_ratio: float           # legacy: RMS of last 250 ms / ref RMS (reported for comparison)
    onset_sample: int | None
    onset_time_s: float | None
    noise_type: str
    noise_type_confidence: float
    hold_word_time_s: float | None


def detect_looming_between_hold_and_cue(
    audio_signal: np.ndarray,
    sample_rate: int,
    cue_time_s: float,
    hold_word: AnchorWord | None,
    noise_templates: dict[str, tuple[np.ndarray, np.ndarray]],
) -> LoomingVerdict:
    """Decide Audio-Tactile vs Baseline using the hold anchor.

    Strategy:

        * Post-hold window = [hold_end, cue_time]. Looming, if any, lives
          here.
        * Pre-hold reference window = [hold_start - 1.0 s, hold_start].
          During this interval the narrator is speaking and the background
          music is playing, but no looming is active. Comparing envelope
          and spectrum of the post-hold window against this reference lets
          us isolate the looming contribution from the ambient audio
          (music + narrator tail).
        * Fallback when no 'hold' anchor is available: use
          [cue - 4 s, cue - 0.05 s] as post-hold window and
          [cue - 7 s, cue - 5.5 s] as reference. The confidence drops.
    """
    try:
        from scipy.signal import welch
    except Exception:
        welch = None  # noqa: N806

    have_hold = hold_word is not None
    if have_hold:
        # Music-only reference: right after 'hold' word end but before any
        # looming can start (stimulus block is hold_word.end + ~0.5 s of
        # silence padding, then looming noise begins).
        music_ref_start_s = max(0.0, hold_word.end)
        music_ref_end_s = music_ref_start_s + MUSIC_REF_WINDOW_S
        # Looming-possible window: start after LOOMING_LEAD_GAP so we sit
        # past the stimulus-block silence padding, end just before the cue.
        post_start_s = music_ref_start_s + LOOMING_LEAD_GAP_S
        post_end_s = max(post_start_s + 0.05, cue_time_s - 0.05)
        confidence_label = "high"
    else:
        # No hold anchor: fall back on cue-relative windows. The music-only
        # reference becomes the earliest slice of the pre-cue window, and
        # looming-possible is the rest.
        music_ref_start_s = max(0.0, cue_time_s - LOOMING_FALLBACK_PRE_CUE_S)
        music_ref_end_s = music_ref_start_s + MUSIC_REF_WINDOW_S
        post_start_s = music_ref_start_s + LOOMING_LEAD_GAP_S
        post_end_s = cue_time_s - LOOMING_FALLBACK_POST_CUE_S
        confidence_label = "low_no_hold_anchor"

    post_start = int(round(post_start_s * sample_rate))
    post_end = int(round(post_end_s * sample_rate))
    ref_start = int(round(music_ref_start_s * sample_rate))
    ref_end = int(round(music_ref_end_s * sample_rate))

    post_seg = audio_signal[post_start:post_end].astype(np.float32, copy=False)
    ref_seg = audio_signal[ref_start:ref_end].astype(np.float32, copy=False)
    if len(post_seg) == 0 or len(ref_seg) == 0:
        return LoomingVerdict(
            detected=False,
            trial_type_confidence=confidence_label,
            peak_ratio=0.0,
            ramp_ratio=0.0,
            onset_sample=None,
            onset_time_s=None,
            noise_type="N/A",
            noise_type_confidence=0.0,
            hold_word_time_s=None if not have_hold else float(hold_word.end),
        )

    # --- RMS-ratio discriminator (vs music-only reference). ---
    # Both windows contain background music. The looming-possible window
    # additionally contains the looming ramp on Audio-Tactile trials.
    # RMS is used rather than envelope peak because music beats produce
    # transient peaks that add variance to a peak-based ratio; looming
    # produces a SUSTAINED elevation that RMS captures cleanly.
    ref_rms = float(np.sqrt(np.mean(ref_seg * ref_seg))) or 1e-9
    post_rms = float(np.sqrt(np.mean(post_seg * post_seg))) if len(post_seg) else ref_rms
    peak_ratio = post_rms / max(ref_rms, 1e-9)  # "peak_ratio" kept as column name for schema stability

    # 50 ms-smoothed envelope (used for onset detection below and as a
    # reported diagnostic).
    env_win_samples = max(1, int(round(0.050 * sample_rate)))
    env_full = np.convolve(
        np.abs(post_seg),
        np.ones(env_win_samples, dtype=np.float32) / env_win_samples,
        mode="same",
    )
    env_peak = float(np.max(env_full)) if len(env_full) else ref_rms
    # Legacy tail-RMS metric, kept for reporting / QC.
    last_250ms = max(int(round(0.250 * sample_rate)), 1)
    post_tail = post_seg[-last_250ms:]
    post_tail_rms = float(np.sqrt(np.mean(post_tail * post_tail)))
    ramp_ratio = post_tail_rms / max(ref_rms, 1e-9)

    if peak_ratio >= PEAK_RATIO_THRESHOLD:
        detected = True
        if have_hold:
            confidence_label = "high"
    elif peak_ratio >= PEAK_RATIO_AMBIGUOUS_MAX:
        detected = True
        confidence_label = "medium"
    else:
        detected = False

    if not detected:
        return LoomingVerdict(
            detected=False,
            trial_type_confidence=confidence_label,
            peak_ratio=peak_ratio,
            ramp_ratio=ramp_ratio,
            onset_sample=None,
            onset_time_s=None,
            noise_type="N/A",
            noise_type_confidence=0.0,
            hold_word_time_s=float(hold_word.end) if have_hold else None,
        )

    # --- onset: earliest point in the post-hold window where the smoothed
    # envelope rises and stays above a low threshold relative to the
    # reference floor. We use 10% of (peak - ref) as threshold so the true
    # ramp onset is found early. The crossing must be sustained for >= 30 ms
    # to reject a single envelope glitch. Envelope `env_full` was already
    # computed above for peak-ratio detection. ---
    onset_threshold = ref_rms + 0.10 * max(env_peak - ref_rms, 1e-9)
    above_mask = env_full >= onset_threshold
    min_hold_samples = max(1, int(round(0.030 * sample_rate)))
    onset_sample = None
    onset_time_s = None
    if above_mask.any():
        run_start = -1
        for i in range(len(above_mask)):
            if above_mask[i]:
                if run_start < 0:
                    run_start = i
                if i - run_start + 1 >= min_hold_samples:
                    onset_local = run_start
                    onset_sample = int(post_start + onset_local)
                    onset_time_s = onset_sample / float(sample_rate)
                    onset_time_s = min(onset_time_s, cue_time_s - 0.05)
                    onset_sample = int(round(onset_time_s * sample_rate))
                    break
            else:
                run_start = -1

    # --- noise-type classification via excess PSD ---
    noise_type = "N/A"
    noise_margin = 0.0
    if welch is not None and noise_templates and len(post_seg) >= PSD_NPERSEG and len(ref_seg) >= PSD_NPERSEG:
        f_post, P_post = welch(post_seg, fs=sample_rate, nperseg=PSD_NPERSEG)
        f_ref, P_ref = welch(ref_seg, fs=sample_rate, nperseg=PSD_NPERSEG)
        # Normalize both and compute excess.
        P_post_n = P_post / max(float(P_post.sum()), 1e-12)
        P_ref_n = P_ref / max(float(P_ref.sum()), 1e-12)
        excess = np.clip(P_post_n - P_ref_n, 0.0, None)
        if excess.sum() > 0:
            excess = excess / float(excess.sum())
            scores: list[tuple[str, float]] = []
            for colour, (fn, Pn) in noise_templates.items():
                Pn_i = np.interp(f_post, fn, Pn)
                Pn_i = Pn_i / max(float(Pn_i.sum()), 1e-12)
                scores.append((colour, bhattacharyya_coefficient(excess, Pn_i)))
            scores.sort(key=lambda t: t[1], reverse=True)
            noise_type = scores[0][0]
            noise_margin = scores[0][1] - scores[1][1] if len(scores) >= 2 else scores[0][1]

    return LoomingVerdict(
        detected=True,
        trial_type_confidence=confidence_label,
        peak_ratio=peak_ratio,
        ramp_ratio=ramp_ratio,
        onset_sample=onset_sample,
        onset_time_s=onset_time_s,
        noise_type=noise_type,
        noise_type_confidence=round(noise_margin, 4),
        hold_word_time_s=float(hold_word.end) if have_hold else None,
    )


# ---------------------------------------------------------------------------
# Part / block numbering from inter-cue gaps
# ---------------------------------------------------------------------------

def assign_part_and_block_numbers(
    cue_times_s: list[float],
    part_split_min_gap_s: float,
    block_gap_threshold_s: float,
    part_split_middle_fraction: tuple[float, float] = (0.20, 0.80),
) -> tuple[list[int], list[int], list[int]]:
    """Partition cues into parts (1 = viscereality VR, 2 = minimal) and
    blocks. Part boundary is the longest gap whose TIMING falls inside the
    middle ``part_split_middle_fraction`` of the experimental window and
    exceeds ``part_split_min_gap_s``. Restricting to the middle rejects
    false part-splits caused by an early participant pause (e.g., the
    ~100 s gap that once put P1=8 / P2=415 on P13 and P23) or a late
    between-block break.
    """
    n = len(cue_times_s)
    parts = [1] * n
    blocks = [0] * n
    trials_in_block = [0] * n

    if n == 0:
        return parts, blocks, trials_in_block

    gaps = [cue_times_s[i] - cue_times_s[i - 1] for i in range(1, n)]
    # Identify part-split index: the largest gap above threshold AND inside
    # the middle portion of the experimental window (by cue index, which
    # tracks time since cues are roughly uniformly spaced).
    part_split_idx: int | None = None
    if gaps:
        lo_idx = int(round(part_split_middle_fraction[0] * n))
        hi_idx = int(round(part_split_middle_fraction[1] * n))
        best_gap = -1.0
        best_idx: int | None = None
        for g_idx, g in enumerate(gaps):
            cue_after = g_idx + 1  # index of the cue after the gap
            if cue_after < lo_idx or cue_after > hi_idx:
                continue
            if g < part_split_min_gap_s:
                continue
            if g > best_gap:
                best_gap = g
                best_idx = cue_after
        part_split_idx = best_idx

    if part_split_idx is not None:
        for i in range(part_split_idx, n):
            parts[i] = 2

    # Block numbering resets at each part boundary.
    current_block = 1
    current_trial = 0
    for i in range(n):
        if i == 0:
            current_trial = 1
        else:
            if parts[i] != parts[i - 1]:
                current_block = 1
                current_trial = 1
            else:
                gap = cue_times_s[i] - cue_times_s[i - 1]
                if gap > block_gap_threshold_s:
                    current_block += 1
                    current_trial = 1
                else:
                    current_trial += 1
        blocks[i] = current_block
        trials_in_block[i] = current_trial
    return parts, blocks, trials_in_block


def _parse_time_s(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_anchor_time_s(row: dict[str, Any]) -> float | None:
    """Preferred chronological anchor for an exported interval row."""
    for key in ("trial_unit_start_s", "tactile_cue_time_s", "looming_onset_time_s"):
        t = _parse_time_s(row.get(key, ""))
        if t is not None:
            return t
    return None


def reconstruct_interval_sequence(
    rows: list[dict[str, Any]],
    template_hits: list[BreathingTemplateHit],
) -> list[dict[str, Any]]:
    """Rebuild the exported row stream as a chronological 8-second interval
    sequence.

    The original bottom-up decoder detects tactile rows first, then appends
    Catch rows later. That preserves the evidence but breaks the visible trial
    order: Catch intervals float to the end of the CSV, no longer sitting
    between the neighbouring inhale/exhale intervals where they actually
    occurred. This helper keeps the existing detections intact and only
    rewrites the *assembly layer*:

    1. Sort every emitted row by its WAV-derived interval anchor time.
    2. Re-assign ``part_number`` / ``block_number`` from the breathing-event
       blocks detected in the WAV itself.
    3. Re-assign ``trial_number`` by chronological position within each WAV-
       derived block.
    4. Set the exported ``phase`` from interval parity within block, so the
       final row sequence is always Inhale, Exhale, Inhale, Exhale ...

    The original template-derived phase evidence remains in the diagnostic
    columns (``phase_template*``), so we do not throw away detector evidence;
    we simply expose the rows in the correct temporal order.
    """
    sortable: list[dict[str, Any]] = []
    unsortable: list[dict[str, Any]] = []
    for row in rows:
        if _row_anchor_time_s(row) is None:
            unsortable.append(row)
        else:
            sortable.append(row)
    if not sortable:
        return rows

    sortable.sort(
        key=lambda row: (
            _row_anchor_time_s(row),
            _parse_time_s(row.get("looming_onset_time_s", "")) or math.inf,
            _parse_time_s(row.get("tactile_cue_time_s", "")) or math.inf,
        )
    )

    starts = [_row_anchor_time_s(row) for row in sortable]
    assert all(t is not None for t in starts)
    starts_f = [float(t) for t in starts]

    breathing_blocks, _legacy_part2_start = group_breathing_hits_into_blocks(template_hits)
    if breathing_blocks:
        block_sizes = [len(block) for block in breathing_blocks]
        median_block_size = statistics.median(block_sizes)
        min_real_block_size = max(4, int(round(0.25 * median_block_size)))
        breathing_blocks = [block for block in breathing_blocks if len(block) >= min_real_block_size]
        if breathing_blocks:
            filtered_sizes = [len(block) for block in breathing_blocks]
            filtered_median = statistics.median(filtered_sizes)
            highly_irregular = [
                size for size in filtered_sizes
                if size < 0.5 * filtered_median or size > 1.5 * filtered_median
            ]
            if highly_irregular:
                breathing_blocks = []

    block_windows: list[tuple[float, float, int, int]] = []
    if breathing_blocks:
        group_starts = [float(block[0].start_s) for block in breathing_blocks]
        group_ends = [float(block[-1].start_s) + TRIAL_UNIT_SECONDS for block in breathing_blocks]
        inter_block_gaps = [
            group_starts[idx] - group_ends[idx - 1]
            for idx in range(1, len(breathing_blocks))
        ]
        part2_start = None
        if inter_block_gaps:
            lo_idx = max(1, int(round(0.20 * len(breathing_blocks))))
            hi_idx = min(len(breathing_blocks) - 1, int(round(0.80 * len(breathing_blocks))))
            candidate_gaps = [
                (idx, gap)
                for idx, gap in enumerate(inter_block_gaps, start=1)
                if lo_idx <= idx <= hi_idx
            ]
            if candidate_gaps:
                gap_values = [gap for _idx, gap in candidate_gaps]
                gap_median = statistics.median(gap_values)
                gap_best_idx, gap_best = max(candidate_gaps, key=lambda item: item[1])
                if gap_best >= max(2.5 * max(gap_median, 1.0), 3.0 * TRIAL_UNIT_SECONDS):
                    part2_start = gap_best_idx

        for block_idx, block in enumerate(breathing_blocks):
            window_start = float(block[0].start_s) - 0.5 * TRIAL_UNIT_SECONDS
            if block_idx + 1 < len(breathing_blocks):
                next_start = float(breathing_blocks[block_idx + 1][0].start_s)
                window_end = 0.5 * (float(block[-1].start_s) + TRIAL_UNIT_SECONDS + next_start)
            else:
                window_end = float(block[-1].start_s) + 1.5 * TRIAL_UNIT_SECONDS

            if part2_start is None or block_idx < part2_start:
                part_number = 1
                block_number = block_idx + 1
            else:
                part_number = 2
                block_number = block_idx - part2_start + 1
            block_windows.append((window_start, window_end, part_number, block_number))

    parts = [0] * len(sortable)
    blocks = [0] * len(sortable)
    trials = [0] * len(sortable)
    if block_windows:
        block_members: dict[tuple[int, int], list[int]] = {}
        window_idx = 0
        for row_idx, start_s in enumerate(starts_f):
            while window_idx + 1 < len(block_windows) and start_s >= block_windows[window_idx][1]:
                window_idx += 1
            part_number, block_number = block_windows[window_idx][2], block_windows[window_idx][3]
            parts[row_idx] = part_number
            blocks[row_idx] = block_number
            block_members.setdefault((part_number, block_number), []).append(row_idx)
        for member_idxs in block_members.values():
            for trial_pos, row_idx in enumerate(member_idxs, start=1):
                trials[row_idx] = trial_pos
    else:
        gaps = [starts_f[idx] - starts_f[idx - 1] for idx in range(1, len(starts_f))]
        short_gaps = [gap for gap in gaps if gap <= 1.5 * TRIAL_UNIT_SECONDS]
        median_short_gap = statistics.median(short_gaps) if short_gaps else TRIAL_UNIT_SECONDS
        adaptive_block_gap_s = max(2.5 * median_short_gap, 18.0)
        adaptive_part_gap_s = max(4.0 * adaptive_block_gap_s, PART_SPLIT_MIN_GAP_S)
        parts, blocks, trials = assign_part_and_block_numbers(
            starts_f,
            adaptive_part_gap_s,
            adaptive_block_gap_s,
        )

    for idx, row in enumerate(sortable):
        start_s = starts_f[idx]
        structural_phase = "Inhale" if trials[idx] % 2 == 1 else "Exhale"
        original_phase = row.get("phase")

        row["part_number"] = parts[idx]
        row["block_number"] = blocks[idx]
        row["trial_number"] = trials[idx]
        row["trial_number_global"] = idx + 1
        row["trial_unit_start_s"] = round(start_s, 3)
        row["trial_unit_end_s"] = round(start_s + TRIAL_UNIT_SECONDS, 3)

        if original_phase not in ("Inhale", "Exhale"):
            row["phase"] = structural_phase
            if "phase_source" in row:
                row["phase_source"] = "interval_parity"
            if "phase_agreement" in row:
                row["phase_agreement"] = "interval_parity_only"
        elif original_phase != structural_phase:
            row["phase"] = structural_phase
            if "phase_source" in row:
                row["phase_source"] = "interval_parity"
            if "phase_agreement" in row:
                row["phase_agreement"] = "template_structural_conflict"

    return sortable + unsortable


# ---------------------------------------------------------------------------
# Click / reaction time
# ---------------------------------------------------------------------------

def _first_click_in_window(
    tactile_signal: np.ndarray,
    search_start: int,
    search_end: int,
    click_template: np.ndarray,
    sample_rate: int,
    pps: Any,
) -> tuple[bool, int | None, float | None, float | None]:
    """Return (detected, click_start_sample_abs, peak_score, threshold).

    Finds the FIRST click-template peak above the adaptive threshold in
    the window â€” not the strongest. This matters when a participant
    accidentally double-clicks: we want RT against the first press, not
    the louder one.
    """
    try:
        from scipy.signal import find_peaks
    except Exception:
        return False, None, None, None

    window = tactile_signal[search_start:search_end]
    if len(window) <= len(click_template):
        return False, None, None, None
    click_z = pps.safe_standardize(click_template)
    corr = np.correlate(window, click_z, mode="valid") / max(len(click_z), 1)
    if len(corr) == 0:
        return False, None, None, None

    local_med = float(np.median(corr))
    local_mad = pps.mad(corr)
    threshold = max(pps.CLICK_MIN_CORR, local_med + pps.CLICK_Z_THRESHOLD * max(local_mad, 1e-6))

    # Enforce a minimum separation so accidental double-clicks
    # (mouse bounce) do not each get registered as a separate peak within
    # the same click event. CLICK_MIN_SEPARATION_SECONDS in pps defaults
    # to ~100 ms, which comfortably exceeds mouse-switch debounce times.
    min_distance = max(1, int(round(pps.CLICK_MIN_SEPARATION_SECONDS * sample_rate)))
    peaks, _props = find_peaks(corr, height=threshold, distance=min_distance)
    if len(peaks) == 0:
        # Fall back to the argmax/peak-val comparison; if still below threshold,
        # no click detected.
        peak_idx = int(np.argmax(corr))
        peak_val = float(corr[peak_idx])
        if peak_val < threshold:
            return False, None, peak_val, threshold
        return True, search_start + peak_idx, peak_val, threshold

    # First peak in time = earliest click â†’ RT against first press.
    first_peak_idx = int(peaks[0])
    return True, search_start + first_peak_idx, float(corr[first_peak_idx]), threshold


def measure_reaction_time(
    tactile_signal: np.ndarray,
    cue_run: Any,
    sample_rate: int,
    click_template: np.ndarray,
    pps: Any,
) -> dict[str, Any]:
    """Detect the response click and return both start-to-start and
    midpoint-to-midpoint RT. Midpoint-to-midpoint is the project's primary
    RT per stakeholder instruction.

    The tactile cue has already been located by ``detect_tactile_event_runs``
    so its start and end are known. For the click, we correlate the click
    template; the detected start sample plus half the template length
    approximates the click midpoint.
    """
    search_start = cue_run.end_sample + int(round(CLICK_SEARCH_POST_CUE_START_S * sample_rate))
    search_end = min(
        len(tactile_signal),
        cue_run.start_sample + int(round(CLICK_SEARCH_POST_CUE_END_S * sample_rate)),
    )
    # Use the first-click variant rather than pps.detect_click_in_window
    # (which returns the strongest click in the window â€” not what we want
    # when a participant double-clicks, since RT should be measured from
    # the FIRST press).
    detected, click_start_abs, _peak, _thr = _first_click_in_window(
        tactile_signal=tactile_signal,
        search_start=search_start,
        search_end=search_end,
        click_template=click_template,
        sample_rate=sample_rate,
        pps=pps,
    )

    cue_start_s = cue_run.start_sample / float(sample_rate)
    cue_end_s = cue_run.end_sample / float(sample_rate)
    cue_mid_s = 0.5 * (cue_start_s + cue_end_s)

    click_start_s = click_start_abs / float(sample_rate) if (detected and click_start_abs is not None) else None
    click_mid_s = None
    rt_mid_ms = None
    rt_start_ms = None
    if detected and click_start_s is not None:
        click_length_s = len(click_template) / float(sample_rate)
        click_mid_s = click_start_s + 0.5 * click_length_s
        rt_start_ms = (click_start_s - cue_start_s) * 1000.0
        rt_mid_ms = (click_mid_s - cue_mid_s) * 1000.0

    return {
        "response_detected": bool(detected),
        "click_start_s": click_start_s,
        "click_mid_s": click_mid_s,
        "cue_start_s": cue_start_s,
        "cue_mid_s": cue_mid_s,
        "rt_mid_ms": rt_mid_ms,
        "rt_start_ms": rt_start_ms,
        "click_outcome": "hit" if detected else "no_click_detected",
    }


# ---------------------------------------------------------------------------
# Cross-verification of the box-breathing structure
# ---------------------------------------------------------------------------

def cross_verify_breathing_structure(
    rows: list[dict[str, Any]],
    template_hits: list[BreathingTemplateHit],
) -> dict[str, Any]:
    """Check that the decoded trials look like a box-breathing session.

    Two independent streams:

        1. **Breathing template events**: Inhale / Exhale instruction hits on
           the audio channel. Under box breathing, consecutive Inhale hits should be
           ~16 s apart (one full cycle), and Inhale / Exhale words should
           strictly alternate.
        2. **Tactile-cue-anchored phase labels**: one per decoded trial.

    Each row gets a ``cross_verification_status`` reflecting whether the
    trial's phase is consistent with the adjacent trial's phase given the
    inter-cue gap. The recording summary reports the overall alternation
    rate and the median breathing cycle period.
    """
    # --- stream 1: breathing-event periodicity from deterministic templates ---
    phase_events: list[tuple[float, str]] = []
    for hit in template_hits:
        phase_events.append((float(hit.start_s), hit.phase))
    phase_events.sort()

    inhale_times = [t for t, p in phase_events if p == "Inhale"]
    exhale_times = [t for t, p in phase_events if p == "Exhale"]
    def median_diff(xs: list[float]) -> float | None:
        if len(xs) < 2:
            return None
        diffs = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
        # Only keep diffs within 1.5x of BREATHING_CYCLE_SECONDS to reject
        # inter-block pauses when computing the "within-block" median.
        close = [d for d in diffs if d <= 1.5 * BREATHING_CYCLE_SECONDS]
        if not close:
            return None
        s = sorted(close)
        return s[len(s) // 2]

    breathing_period_s = median_diff(inhale_times)
    # Alternation of the raw word stream (inhale/exhale events).
    alternation_ok = 0
    alternation_total = 0
    for i in range(1, len(phase_events)):
        prev_t, prev_p = phase_events[i - 1]
        cur_t, cur_p = phase_events[i]
        # Only audit "adjacent" events within one breathing cycle.
        if cur_t - prev_t > 1.5 * BREATHING_CYCLE_SECONDS:
            continue
        alternation_total += 1
        if prev_p != cur_p:
            alternation_ok += 1
    breathing_alternation_rate = (
        alternation_ok / alternation_total if alternation_total else None
    )

    # --- stream 2: per-trial cross-verification ---
    cue_alt_total = 0
    cue_alt_ok = 0
    for i, row in enumerate(rows):
        status = "consistent"
        cur_phase = row.get("phase")
        cue_t = _row_anchor_time_s(row)

        if cur_phase == "Unknown":
            status = "unknown_phase"
        elif i == 0:
            status = "first_trial"
        else:
            prev = rows[i - 1]
            prev_phase = prev.get("phase")
            prev_t = _row_anchor_time_s(prev)
            if prev_phase == "Unknown":
                status = "prev_unknown_phase"
            elif cue_t is not None and prev_t is not None:
                gap = float(cue_t) - float(prev_t)
                cue_alt_total += 1
                if cur_phase != prev_phase:
                    status = "consistent"
                    cue_alt_ok += 1
                else:
                    if gap <= PHASE_REPEAT_SHORT_GAP_MAX_S:
                        status = "phase_repeat_short_gap_ANOMALY"
                    elif gap <= PHASE_REPEAT_CATCH_GAP_MAX_S:
                        status = "phase_repeat_probably_catch_between"
                    else:
                        status = "phase_repeat_large_gap"
        row["cross_verification_status"] = status

    cue_alternation_rate = cue_alt_ok / cue_alt_total if cue_alt_total else None

    return {
        "breathing_period_s": round(breathing_period_s, 3) if breathing_period_s is not None else None,
        "breathing_alternation_rate": round(breathing_alternation_rate, 3) if breathing_alternation_rate is not None else None,
        "inhale_events": len(inhale_times),
        "exhale_events": len(exhale_times),
        "cue_phase_alternation_rate": round(cue_alternation_rate, 3) if cue_alternation_rate is not None else None,
    }


# ---------------------------------------------------------------------------
# Alternation-based phase imputation
# ---------------------------------------------------------------------------

def _flip_phase(phase: str) -> str:
    if phase == "Inhale":
        return "Exhale"
    if phase == "Exhale":
        return "Inhale"
    return phase


def impute_unknown_phases_by_block_parity(rows: list[dict[str, Any]]) -> int:
    """Deterministic fallback: every block of the experiment starts with
    Inhale and alternates thereafter. Verified to hold across all 426
    planned blocks Ã— participants in the stimulus generator â€” it is a
    structural property of the design, not a per-participant detail, so
    we are allowed to rely on it without re-using the planned per-trial
    sequences.

    Applied to tactile rows (Audio-Tactile / Baseline) with a valid
    ``trial_number``. Catch rows are handled separately (their phase comes
    from the preceding breathing template hit, then alternation if
    needed).

    Rule:  phase = Inhale if trial_number is odd, Exhale if even.
    """
    n_imputed = 0
    for row in rows:
        if row.get("phase") in ("Inhale", "Exhale"):
            continue
        if row.get("trial_type") not in ("Audio-Tactile", "Baseline"):
            continue
        tn_raw = row.get("trial_number", "")
        if tn_raw in ("", None):
            continue
        try:
            tn = int(tn_raw)
        except (TypeError, ValueError):
            continue
        row["phase"] = "Inhale" if tn % 2 == 1 else "Exhale"
        row["phase_alternation_check"] = "imputed_from_block_parity"
        if "phase_source" in row:
            row["phase_source"] = "imputed_block_parity"
        n_imputed += 1
    return n_imputed


def impute_unknown_phases_within_block(rows: list[dict[str, Any]]) -> int:
    """Fill in ``phase = Unknown`` rows using the box-breathing alternation
    constraint: every 8 s trial-unit alternates Inhale/Exhale strictly.

    Imputation rule, for an Unknown row at ``trial_unit_start_s = t_u``:

        Find the nearest row with a Known phase in the SAME block. Call its
        time ``t_k`` and its phase ``P_k``. Count the number of 8-second
        trial-unit slots between them:

            n = round((t_u - t_k) / 8)

        Then the imputed phase is ``P_k`` if ``n`` is even, else flipped.

    Restricted to same block (same ``part_number`` AND same ``block_number``)
    so a between-block pause cannot propagate a stale phase across a
    possibly-resynchronised breathing clock. Catch rows are also skipped
    (they have an empty ``block_number``) â€” their phase is either
    template-derived or stays Unknown.

    The row is mutated in-place:
        * ``phase`` becomes ``Inhale`` / ``Exhale``
        * ``phase_alternation_check`` becomes ``imputed_from_alternation``
        * if diagnostic columns are present, ``phase_source`` becomes
          ``imputed_alternation``.

    Returns the number of rows whose phase was filled in.
    """
    def _t(row: dict[str, Any]) -> float | None:
        """Prefer tactile_cue_time_s (always precise). Fall back to
        trial_unit_start_s (which for Unknown rows is cue_end - 8, good
        to about Â±2 s â€” well within our Â±4 s rounding tolerance)."""
        for key in ("tactile_cue_time_s", "trial_unit_start_s"):
            v = row.get(key, "")
            if v not in ("", None):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    n_imputed = 0
    for idx, row in enumerate(rows):
        if row.get("phase") != "Unknown":
            continue
        if row.get("trial_type") == "Catch":
            # Catch rows use a different phase pathway; leave them alone.
            continue

        block_key = (row.get("part_number"), row.get("block_number"))
        t_u = _t(row)
        if t_u is None:
            continue

        # Search backward then forward for the nearest Known phase in the
        # same block. Prefer the closer one by absolute time distance.
        best_ref: tuple[float, str] | None = None  # (t_k, P_k)
        best_abs_dt = math.inf
        for direction in (-1, +1):
            j = idx + direction
            while 0 <= j < len(rows):
                r = rows[j]
                # Stop if we leave the block (either part or block changed).
                if (r.get("part_number"), r.get("block_number")) != block_key:
                    break
                phase_j = r.get("phase")
                if phase_j in ("Inhale", "Exhale") and r.get("trial_type") != "Catch":
                    t_k = _t(r)
                    if t_k is not None:
                        dt = abs(t_u - t_k)
                        if dt < best_abs_dt:
                            best_abs_dt = dt
                            best_ref = (t_k, phase_j)
                    break
                j += direction

        if best_ref is None:
            continue  # nothing to impute from

        t_k, p_k = best_ref
        n_steps = int(round((t_u - t_k) / TRIAL_UNIT_SECONDS))
        imputed = p_k if n_steps % 2 == 0 else _flip_phase(p_k)
        row["phase"] = imputed
        row["phase_alternation_check"] = "imputed_from_alternation"
        if "phase_source" in row:
            row["phase_source"] = "imputed_alternation"
        n_imputed += 1
    return n_imputed


# ---------------------------------------------------------------------------
# Per-recording pipeline
# ---------------------------------------------------------------------------

def decode_recording(
    recording_wav: Path,
    pps: Any,
    overwrite: bool,
) -> dict[str, Any]:
    DECODED_DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    output_csv = DECODED_DIAGNOSTICS_DIR / f"{canonical_output_stem(recording_wav)}.csv"
    if output_csv.exists() and not overwrite:
        return {
            "recording_file": recording_wav.name,
            "participant_id": participant_id_from_filename(recording_wav) or "",
            "status": "skipped_existing_csv",
            "csv_file": str(output_csv),
            "message": "Use --overwrite to regenerate.",
        }

    t_start = time.time()
    print(f"[{recording_wav.name}] loading recording")
    recording_samples, recording_info = pps.read_wav_frames(recording_wav)
    sample_rate = recording_info.sample_rate

    audio_channel, tactile_channel = pps.infer_recording_channel_roles(recording_samples)
    print(f"[{recording_wav.name}] audio_ch={audio_channel}, tactile_ch={tactile_channel}, sr={sample_rate}")

    tactile_signal = recording_samples[:, tactile_channel]
    audio_signal = recording_samples[:, audio_channel]

    # --- 1. Tactile cues ---
    # Primary event recovery starts from the tactile channel. The legacy
    # global threshold works for stable recordings, but it can miss an entire
    # quieter part when the earlier part has louder pulses. Profile the WAV
    # locally first, then use the richer tactile event stream when it clearly
    # recovers real cue-like events.
    runs, cue_threshold = pps.detect_tactile_event_runs(tactile_signal, sample_rate)
    legacy_cue_runs = pps.select_tactile_cue_runs(runs, sample_rate)
    adaptive_cue_runs, tactile_profile = pps.detect_tactile_cue_runs_adaptive(
        tactile_signal, sample_rate
    )
    cue_runs = legacy_cue_runs
    tactile_detection_method = "global_threshold"
    expected_cues_hi = 300
    if (
        len(legacy_cue_runs) < expected_cues_hi
        and len(adaptive_cue_runs) > len(legacy_cue_runs) * 1.2
        and len(adaptive_cue_runs) <= 520
    ):
        cue_runs = adaptive_cue_runs
        tactile_detection_method = "adaptive_local_threshold"
        cue_threshold = float(tactile_profile.get("threshold_max", cue_threshold))
        print(
            f"[{recording_wav.name}] tactile cue detection: adaptive local profile "
            f"recovered {len(adaptive_cue_runs)} cue-like events "
            f"(global={len(legacy_cue_runs)}, thresholds="
            f"{float(tactile_profile.get('threshold_min', 0.0)):.3f}-"
            f"{float(tactile_profile.get('threshold_max', 0.0)):.3f})"
        )
    elif len(cue_runs) < expected_cues_hi and recording_info.duration_seconds >= 3000:
        min_samples_relaxed = int(round(0.040 * sample_rate))   # was 0.060
        peak_floor_relaxed = 0.10                                # was 0.22 (TACTILE_CUE_MIN_PEAK)
        relaxed = [
            r for r in runs
            if r.duration_samples >= min_samples_relaxed and r.peak_abs >= peak_floor_relaxed
        ]
        # Keep the relaxed list only if it's clearly larger (i.e. recovers
        # cues rather than fabricating them). Otherwise stick with pps.
        if len(relaxed) > len(cue_runs) * 1.2 and len(relaxed) <= 480:
            cue_runs = relaxed
            tactile_detection_method = "global_threshold_relaxed_filter"
            print(
                f"[{recording_wav.name}] tactile cue detection: adaptive relax "
                f"rescued {len(relaxed) - sum(1 for _ in pps.select_tactile_cue_runs(runs, sample_rate))} "
                f"additional cues"
            )
    all_cue_times_s = [run.start_sample / float(sample_rate) for run in cue_runs]
    print(
        f"[{recording_wav.name}] {len(cue_runs)} tactile cues before protocol anchor "
        f"(method={tactile_detection_method}, threshold={cue_threshold:.3f})"
    )

    # --- 2. Deterministic breathing-template detection (fast, music-robust).
    template_hits: list[BreathingTemplateHit] = []
    template_status = "disabled"
    templates_audio = load_breathing_templates(sample_rate)
    if templates_audio is not None:
        try:
            t_tpl = time.time()
            template_hits = detect_breathing_events_via_templates(
                audio_signal=audio_signal,
                sample_rate=sample_rate,
                templates=templates_audio,
            )
            template_status = f"ok_{len(template_hits)}_hits"
            print(
                f"[{recording_wav.name}] template match: {len(template_hits)} breathing "
                f"instances in {time.time() - t_tpl:.1f}s"
            )
        except Exception as exc:
            template_status = f"failed: {type(exc).__name__}: {exc}"
            print(f"[{recording_wav.name}] template match failed: {exc}", file=sys.stderr)
    else:
        print(f"[{recording_wav.name}] breathing templates missing; template match skipped")

    # --- 3. Protocol anchor + Part / block numbering ---
    # The runner plays standardized block WAVs containing fixed breathing
    # instructions. Use the first recovered breathing phrase as the true
    # experiment anchor, then ignore tactile/looming events before its hold
    # point. This keeps pre-run tests or loopback startup artifacts out of
    # the trial stream while still allowing the first cue to claim that
    # breathing template for phase labeling.
    breathing_anchor = first_breathing_anchor_hit(template_hits)
    if breathing_anchor is not None:
        breathing_anchor_start_s = max(0.0, float(breathing_anchor.start_s))
        experiment_start_s = max(0.0, float(breathing_anchor.hold_s))
        experiment_anchor_source = f"first_{breathing_anchor.phase.lower()}_breathing_template_hold"
    else:
        experiment_start_s = max(
            0.0,
            (all_cue_times_s[0] - WARMUP_BUFFER_S) if all_cue_times_s else 0.0,
        )
        breathing_anchor_start_s = experiment_start_s
        experiment_anchor_source = "first_tactile_cue_fallback"

    tactile_events_before_anchor = sum(
        1 for run in cue_runs
        if (run.start_sample / float(sample_rate)) < experiment_start_s
    )
    if tactile_events_before_anchor:
        cue_runs = [
            run for run in cue_runs
            if (run.start_sample / float(sample_rate)) >= experiment_start_s
        ]
    cue_times_s = [run.start_sample / float(sample_rate) for run in cue_runs]
    print(
        f"[{recording_wav.name}] protocol anchor={experiment_anchor_source} "
        f"at {experiment_start_s:.2f}s; trimmed {tactile_events_before_anchor} "
        f"pre-anchor tactile events; {len(cue_runs)} remain"
    )

    parts, blocks, trials_in_block = assign_part_and_block_numbers(
        cue_times_s, PART_SPLIT_MIN_GAP_S, BLOCK_GAP_THRESHOLD_S
    )

    template_hits_exp = [
        h for h in template_hits
        if h.start_s >= breathing_anchor_start_s
    ]
    warmup_template_hits = len(template_hits) - len(template_hits_exp)

    # --- 4. Looming waveform templates + click template ---
    # Looming: deterministic waveform correlation using the four
    # Loom-*-v1-padded.wav source files. This replaces the envelope-ratio
    # + excess-PSD approach -- waveform correlation gives us Audio-Tactile
    # classification, noise type, AND precise SOA in one pass.
    looming_waveform_templates = load_looming_waveform_templates(sample_rate, pps)
    looming_hits: list[LoomingTemplateHit] = []
    looming_events_before_anchor = 0
    event_pairing_summary = {
        "looming_events": 0,
        "tactile_events": len(cue_runs),
        "paired_events": 0,
        "unpaired_looming_events": 0,
        "unpaired_tactile_events": len(cue_runs),
        "pair_candidates": 0,
    }
    if looming_waveform_templates is not None:
        try:
            t_loom = time.time()
            looming_hits = detect_looming_events_via_templates(
                audio_signal=audio_signal,
                sample_rate=sample_rate,
                templates=looming_waveform_templates,
            )
            looming_events_before_anchor = sum(
                1 for hit in looming_hits
                if float(hit.start_s) < experiment_start_s
            )
            if looming_events_before_anchor:
                looming_hits = [
                    hit for hit in looming_hits
                    if float(hit.start_s) >= experiment_start_s
                ]
            event_pairing_summary = pair_looming_hits_with_cues(
                looming_hits,
                [int(run.start_sample) for run in cue_runs],
                sample_rate,
            )
            print(
                f"[{recording_wav.name}] event pairing: "
                f"{event_pairing_summary['tactile_events']} tactile + "
                f"{event_pairing_summary['looming_events']} looming; "
                f"{event_pairing_summary['paired_events']} paired, "
                f"{event_pairing_summary['unpaired_tactile_events']} baseline-candidate tactile, "
                f"{event_pairing_summary['unpaired_looming_events']} catch-candidate looming; "
                f"trimmed {looming_events_before_anchor} pre-anchor looming "
                f"in {time.time() - t_loom:.1f}s"
            )
        except Exception as exc:
            print(f"[{recording_wav.name}] looming template match failed: {exc}", file=sys.stderr)
    else:
        print(
            f"[{recording_wav.name}] WARNING: looming waveform templates missing or "
            "sample-rate mismatch; all trials will be reported as Baseline.",
            file=sys.stderr,
        )

    # Legacy PSD noise templates + click template (PSD kept for a potential
    # fallback; click template still used for response detection).
    noise_templates = build_noise_spectral_templates(sample_rate, pps)
    click_template, _ = pps.load_click_template()

    event_inventory_path = write_event_pairing_inventory(
        recording_wav=recording_wav,
        cue_runs=cue_runs,
        cue_parts=parts,
        cue_blocks=blocks,
        cue_trials=trials_in_block,
        looming_hits=looming_hits,
        breathing_hits=template_hits_exp,
        sample_rate=sample_rate,
    )
    print(f"[{recording_wav.name}] wrote event inventory: {event_inventory_path}")

    # --- 5. Per-cue decoding ---
    rows: list[dict[str, Any]] = []
    prev_cue_time_s: float | None = None  # used to gate breathing-hit lookup
    for idx, cue_run in enumerate(cue_runs):
        cue_sample = int(cue_run.start_sample)
        cue_time_s = cue_sample / float(sample_rate)

        # 5a. Template-based phase + hold (deterministic, primary source).
        # Look only at template hits inside the experimental window so the
        # warmup practice doesn't get attached to real trial 1. Also use
        # ``earliest_hold_s = prev_cue_time_s`` so a single breathing hit
        # cannot be claimed by two consecutive cues â€” if the template
        # matcher missed the Inhale/Exhale between cue N and cue N+1, we
        # will honestly emit phase = Unknown for cue N+1 rather than
        # re-using cue N's breathing hit.
        template_hit = find_breathing_hit_before_cue(
            cue_time_s,
            template_hits_exp,
            earliest_hold_s=prev_cue_time_s if prev_cue_time_s is not None else 0.0,
        )
        prev_cue_time_s = cue_time_s
        if template_hit is not None:
            phase_template = template_hit.phase
            if abs(template_hit.phase_margin) < BREATHING_TEMPLATE_MIN_PHASE_MARGIN:
                phase_template_confidence = "ambiguous"
            elif template_hit.score >= BREATHING_TEMPLATE_MIN_SCORE + 0.2:
                phase_template_confidence = "high"
            else:
                phase_template_confidence = "medium"
        else:
            phase_template = "Unknown"
            phase_template_confidence = "no_template_hit"

        if phase_template in ("Inhale", "Exhale") and phase_template_confidence in ("high", "medium"):
            primary_phase = phase_template
            primary_phase_source = "template"
        else:
            primary_phase = "Unknown"
            primary_phase_source = "none"
        phase_agreement = "template_only" if primary_phase != "Unknown" else "neither"

        if template_hit is not None:
            hold_for_looming = AnchorWord(
                text="hold",
                start=template_hit.hold_s,
                end=template_hit.hold_s + 0.25,
                probability=1.0,
            )
            hold_source = "template"
        else:
            hold_for_looming = None
            hold_source = "none"

        # Hand the unified hold word to the looming detector.
        hold_word = hold_for_looming

        # 5b. Looming (Audio-Tactile vs Baseline, SOA, noise_type).
        # Primary path: deterministic template-correlation hit paired to
        # this cue. If a hit is paired, trial is Audio-Tactile; the hit's
        # winning template gives noise_type and the peak time gives SOA.
        # Fallback: the old envelope-ratio detector, only used when no
        # waveform templates are loaded (e.g. sample-rate mismatch).
        loom_hit = find_looming_hit_for_cue(cue_sample, looming_hits)

        if loom_hit is not None:
            trial_type = "Audio-Tactile"
            raw_soa_ms = float(loom_hit.soa_ms) if loom_hit.soa_ms is not None else (cue_time_s - loom_hit.start_s) * 1000.0
            nominal_soa_ms, soa_err_ms = quantize_soa_ms(raw_soa_ms)
            soa_type = f"soa_{nominal_soa_ms}ms"
            looming_onset_time_s = loom_hit.start_s
            looming_noise_type = loom_hit.noise_type
            looming_score = loom_hit.score
            looming_margin = loom_hit.score - loom_hit.runner_up_score
            trial_type_confidence = "high"
            # Populate the legacy verdict fields for reporting (envelope
            # ratios are not used for the decision here; we leave them
            # empty so they are not misread as the primary signal).
            verdict = None
        elif looming_waveform_templates is None:
            # Fallback envelope detector â€” only hit when waveform
            # correlation was unavailable.
            verdict = detect_looming_between_hold_and_cue(
                audio_signal=audio_signal,
                sample_rate=sample_rate,
                cue_time_s=cue_time_s,
                hold_word=hold_word,
                noise_templates=noise_templates,
            )
            if verdict.detected and verdict.onset_time_s is not None:
                raw_soa_ms = (cue_time_s - verdict.onset_time_s) * 1000.0
                nominal_soa_ms, soa_err_ms = quantize_soa_ms(raw_soa_ms)
                soa_type = f"soa_{nominal_soa_ms}ms"
                trial_type = "Audio-Tactile"
                looming_onset_time_s = verdict.onset_time_s
                looming_noise_type = verdict.noise_type
                looming_score = ""
                looming_margin = verdict.noise_type_confidence
                trial_type_confidence = verdict.trial_type_confidence
            else:
                raw_soa_ms = None
                nominal_soa_ms = None
                soa_err_ms = None
                soa_type = "baseline"
                trial_type = "Baseline"
                looming_onset_time_s = None
                looming_noise_type = "N/A"
                looming_score = ""
                looming_margin = 0.0
                trial_type_confidence = verdict.trial_type_confidence if verdict else "high"
        else:
            # Templates were available but this cue did not pair with a
            # looming hit -> Baseline.
            trial_type = "Baseline"
            raw_soa_ms = None
            nominal_soa_ms = None
            soa_err_ms = None
            soa_type = "baseline"
            looming_onset_time_s = None
            looming_noise_type = "N/A"
            looming_score = ""
            looming_margin = 0.0
            trial_type_confidence = "high"
            verdict = None

        # 5d. RT / response
        rt = measure_reaction_time(
            tactile_signal=tactile_signal,
            cue_run=cue_run,
            sample_rate=sample_rate,
            click_template=click_template,
            pps=pps,
        )
        if rt["response_detected"]:
            outcome = "hit"
        else:
            outcome = "no_click_detected" if trial_type == "Audio-Tactile" else "baseline_no_click"

        # 5e. Trial unit bin (8-second box-breathing unit).
        # The unit nominally starts at the breathing-instruction onset and
        # ends 8 s later. If the template match is missing, fall back to
        # (cue_end - 8 s, cue_end).
        if template_hit is not None:
            trial_unit_start_s = round(float(template_hit.start_s), 3)
        else:
            trial_unit_start_s = round(cue_run.end_sample / float(sample_rate) - TRIAL_UNIT_SECONDS, 3)
        trial_unit_end_s = round(trial_unit_start_s + TRIAL_UNIT_SECONDS, 3)

        row = {
            "participant_id": participant_id_from_filename(recording_wav) or "",
            "participant_number": participant_number_from_filename(recording_wav),
            "recording_file": recording_wav.name,
            "experiment_half": experiment_half_from_part(parts[idx]),
            "condition": condition_from_part(parts[idx]),
            "part_number": parts[idx],
            "block_number": blocks[idx],
            "trial_number": trials_in_block[idx],
            "trial_number_global": idx + 1,
            "tactile_event": True,
            "trial_unit_start_s": trial_unit_start_s,
            "trial_unit_end_s": trial_unit_end_s,
            "trial_type": trial_type,
            "trial_type_confidence": trial_type_confidence,
            "looming_detected": trial_type == "Audio-Tactile",
            "phase": primary_phase,
            "phase_source": primary_phase_source,
            "phase_agreement": phase_agreement,
            "phase_template": phase_template,
            "phase_template_confidence": phase_template_confidence,
            "phase_template_score": (
                "" if template_hit is None else round(float(template_hit.score), 4)
            ),
            "phase_template_margin": (
                "" if template_hit is None else round(float(template_hit.phase_margin), 4)
            ),
            "SOA_ms": "" if nominal_soa_ms is None else nominal_soa_ms,
            "SOA_type": soa_type,
            "SOA_raw_ms": "" if raw_soa_ms is None else round(raw_soa_ms, 2),
            "SOA_quantization_error_ms": "" if soa_err_ms is None else round(soa_err_ms, 2),
            "noise_type": looming_noise_type,
            "noise_type_confidence": round(float(looming_margin), 4),
            "noise_type_source": "waveform_template" if loom_hit is not None else ("envelope_fallback" if verdict is not None else "none"),
            "looming_template_score": looming_score,
            "reaction_time_ms": format_rt_ms(rt["rt_mid_ms"]),
            "reaction_time_start_to_start_ms": format_rt_ms(rt["rt_start_ms"]),
            "response_detected": bool(rt["response_detected"]),
            "outcome": outcome,
            "tactile_cue_time_s": round(rt["cue_start_s"], 6),
            "tactile_cue_midpoint_s": round(rt["cue_mid_s"], 6),
            "tactile_cue_sample": cue_sample,
            "looming_onset_time_s": "" if looming_onset_time_s is None else round(looming_onset_time_s, 6),
            "looming_peak_ratio": "" if verdict is None else round(verdict.peak_ratio, 3),
            "looming_ramp_ratio": "" if verdict is None else round(verdict.ramp_ratio, 3),
            "click_time_s": "" if rt["click_start_s"] is None else round(rt["click_start_s"], 6),
            "click_midpoint_s": "" if rt["click_mid_s"] is None else round(rt["click_mid_s"], 6),
            "hold_word_time_s": (
                round(float(hold_for_looming.end), 3) if hold_for_looming is not None else ""
            ),
            "hold_source": hold_source,
            "hold_time_template_s": (
                "" if template_hit is None else round(float(template_hit.hold_s), 3)
            ),
            "data_source": "observed",
        }
        rows.append(row)

    # ---- 6. Catch trials: looming hits that didn't pair with a cue ----
    # A Catch trial plays the looming noise but never delivers the tactile
    # pulse. The participant should therefore NOT click; any click during
    # the 2 s response window is a false alarm.
    catch_rows: list[dict[str, Any]] = []
    next_global_idx = len(rows)
    for hit in looming_hits:
        if hit.paired_cue_sample is not None:
            continue  # paired -> an Audio-Tactile trial, already emitted
        if hit.start_s < experiment_start_s:
            continue  # warmup / pre-experiment, skip

        next_global_idx += 1
        catch_time_s = hit.start_s
        # Look for a spurious click on the tactile channel inside the 2 s
        # response window anchored at the looming onset.
        resp_start_sample = int(round(catch_time_s * sample_rate))
        resp_end_sample = resp_start_sample + int(round(CLICK_SEARCH_POST_CUE_END_S * sample_rate))
        click = pps.detect_click_in_window(
            residual_tactile=tactile_signal,
            window_start_sample_abs=resp_start_sample,
            cue_sample_abs=resp_start_sample,
            trial_end_sample_abs=min(len(tactile_signal), resp_end_sample),
            click_template=click_template,
            sample_rate=sample_rate,
            trial_type="Catch",
            missing_outcome="correct_rejection",
        )

        # Phase anchor: nearest breathing template hit before this catch.
        breath_hit = find_breathing_hit_before_cue(catch_time_s, template_hits_exp)
        if breath_hit is not None:
            catch_phase = breath_hit.phase
            trial_unit_start = round(float(breath_hit.start_s), 3)
        else:
            catch_phase = "Unknown"
            trial_unit_start = round(catch_time_s - TRIAL_UNIT_SECONDS, 3)

        catch_part_number = _nearest_cue_part_number(catch_time_s, cue_times_s, parts)
        catch_row: dict[str, Any] = {
            "participant_id": participant_id_from_filename(recording_wav) or "",
            "participant_number": participant_number_from_filename(recording_wav),
            "recording_file": recording_wav.name,
            "experiment_half": experiment_half_from_part(catch_part_number),
            "condition": condition_from_part(catch_part_number),
            "part_number": catch_part_number,
            "block_number": "",
            "trial_number": "",
            "trial_number_global": next_global_idx,
            "tactile_event": False,
            "trial_unit_start_s": trial_unit_start,
            "trial_unit_end_s": round(trial_unit_start + TRIAL_UNIT_SECONDS, 3),
            "trial_type": "Catch",
            "trial_type_confidence": "high",
            "looming_detected": True,
            "phase": catch_phase,
            "phase_source": "template" if breath_hit is not None else "none",
            "phase_agreement": "template_only" if breath_hit is not None else "neither",
            "phase_template": catch_phase,
            "phase_template_confidence": "high" if breath_hit is not None else "no_template_hit",
            "phase_template_score": (
                round(float(breath_hit.score), 4) if breath_hit is not None else ""
            ),
            "phase_template_margin": (
                round(float(breath_hit.phase_margin), 4) if breath_hit is not None else ""
            ),
            "cross_verification_status": "catch_trial",
            "SOA_ms": "",
            "SOA_type": "catch",
            "SOA_raw_ms": "",
            "SOA_quantization_error_ms": "",
            "noise_type": hit.noise_type,
            "noise_type_confidence": round(float(hit.score - hit.runner_up_score), 4),
            "noise_type_source": "waveform_template",
            "looming_template_score": round(float(hit.score), 4),
            "reaction_time_ms": "",
            "reaction_time_start_to_start_ms": "",
            "response_detected": bool(click.response_detected),
            "outcome": "false_alarm" if click.response_detected else "correct_rejection",
            "tactile_cue_time_s": "",
            "tactile_cue_midpoint_s": "",
            "tactile_cue_sample": "",
            "looming_onset_time_s": round(catch_time_s, 6),
            "looming_peak_ratio": "",
            "looming_ramp_ratio": "",
            "click_time_s": (
                "" if click.click_start_seconds_abs is None else round(click.click_start_seconds_abs, 6)
            ),
            "click_midpoint_s": "",
            "hold_word_time_s": (
                round(float(breath_hit.hold_s), 3) if breath_hit is not None else ""
            ),
            "hold_source": "template" if breath_hit is not None else "none",
            "hold_time_template_s": (
                round(float(breath_hit.hold_s), 3) if breath_hit is not None else ""
            ),
            "data_source": "observed",
        }
        catch_rows.append(catch_row)

    rows.extend(catch_rows)
    rows = reconstruct_interval_sequence(rows, template_hits_exp)

    # Cross-verification (filtered to experimental window).
    xv = cross_verify_breathing_structure(rows, template_hits_exp)

    # Parsimonious analysis schema by default. Every column below is
    # directly used in the downstream analysis: trial identifiers, trial
    # type, phase, SOA, noise, RT, hit/miss. QC / diagnostic fields are
    # available via --diagnostic-columns.
    # Alternation-based phase imputation. Fills `phase = Unknown` rows
    # using the strict box-breathing alternation constraint within the
    # same block. Done AFTER cross_verify_breathing_structure so the
    # initial cross-verification statuses reflect the raw detector
    # output; imputed rows then get their own distinct status below.
    n_imputed = impute_unknown_phases_within_block(rows)
    if n_imputed:
        print(f"[{recording_wav.name}] imputed phase for {n_imputed} Unknown row(s) via within-block alternation")

    # Belt-and-suspenders structural fallback: every block starts with
    # Inhale and alternates. This guarantees zero Unknown phases on
    # tactile rows (Audio-Tactile / Baseline) even when all template
    # matches for an entire block failed.
    n_parity = impute_unknown_phases_by_block_parity(rows)
    if n_parity:
        print(f"[{recording_wav.name}] imputed phase for {n_parity} remaining row(s) via block-parity structural rule")

    # Compact alternation label derived from cross_verification_status.
    # Values:
    #   ok             â€” phase alternated with the previous trial as expected
    #   catch_between  â€” same phase as previous, 12-20 s gap (catch trial sat
    #                    between the two cues; alternation still holds at the
    #                    breathing-cycle level)
    #   large_gap      â€” same phase as previous but a big gap (block / part
    #                    boundary crossed; not an anomaly)
    #   anomaly        â€” same phase as previous with a short gap. This is
    #                    suspicious and the only value the user should audit.
    #   first          â€” first trial, nothing to compare against
    #   unknown        â€” phase is Unknown on this trial
    #   prev_unknown   â€” previous trial's phase was Unknown, cannot audit
    _ALT_MAP = {
        "consistent": "ok",
        "phase_repeat_probably_catch_between": "catch_between",
        "phase_repeat_large_gap": "large_gap",
        "phase_repeat_short_gap_ANOMALY": "anomaly",
        "first_trial": "first",
        "unknown_phase": "unknown",
        "prev_unknown_phase": "prev_unknown",
        "catch_trial": "catch_trial",
    }
    for r in rows:
        # Rows whose phase was filled in by alternation imputation already
        # have phase_alternation_check = "imputed_from_alternation"; keep
        # that rather than overwriting with the raw cross-verification
        # label (which would say "unknown" because cross-verification ran
        # on the pre-imputation data).
        if r.get("phase_alternation_check") == "imputed_from_alternation":
            continue
        r["phase_alternation_check"] = _ALT_MAP.get(
            r.get("cross_verification_status", ""), r.get("cross_verification_status", "")
        )

    parsimonious_fieldnames = [
        "participant_id",
        "participant_number",
        "recording_file",
        "experiment_half",
        "condition",
        "part_number",
        "block_number",
        "trial_number",
        "trial_number_global",
        "tactile_event",
        "tactile_cue_time_s",
        "trial_type",
        "looming_detected",
        "phase",
        "phase_alternation_check",
        "SOA_ms",
        "SOA_raw_ms",
        "noise_type",
        "reaction_time_ms",
        "response_detected",
        "outcome",
        "data_source",
    ]

    diagnostic_fieldnames = [
        "participant_id",
        "participant_number",
        "recording_file",
        "experiment_half",
        "condition",
        "part_number",
        "block_number",
        "trial_number",
        "trial_number_global",
        "tactile_event",
        "trial_unit_start_s",
        "trial_unit_end_s",
        "trial_type",
        "trial_type_confidence",
        "looming_detected",
        "phase",
        "phase_source",
        "phase_agreement",
        "phase_template",
        "phase_template_confidence",
        "phase_template_score",
        "phase_template_margin",
        "cross_verification_status",
        "SOA_ms",
        "SOA_type",
        "SOA_raw_ms",
        "SOA_quantization_error_ms",
        "noise_type",
        "noise_type_confidence",
        "noise_type_source",
        "looming_template_score",
        "reaction_time_ms",
        "reaction_time_start_to_start_ms",
        "response_detected",
        "outcome",
        "tactile_cue_time_s",
        "tactile_cue_midpoint_s",
        "tactile_cue_sample",
        "looming_onset_time_s",
        "looming_peak_ratio",
        "looming_ramp_ratio",
        "click_time_s",
        "click_midpoint_s",
        "hold_word_time_s",
        "hold_source",
        "hold_time_template_s",
        "data_source",
    ]
    write_rows(output_csv, rows, fieldnames=diagnostic_fieldnames)

    n_at = sum(1 for row in rows if row["trial_type"] == "Audio-Tactile")
    n_bl = sum(1 for row in rows if row["trial_type"] == "Baseline")
    n_hit = sum(1 for row in rows if row["outcome"] == "hit")
    n_miss = sum(1 for row in rows if row["outcome"] in ("no_click_detected", "baseline_no_click"))
    n_part2 = sum(1 for row in rows if row.get("part_number") == 2)
    elapsed = time.time() - t_start
    print(
        f"[{recording_wav.name}] done in {elapsed:.1f}s: "
        f"{n_at} AT + {n_bl} BL; hits={n_hit}, misses={n_miss}; Part2={n_part2}"
    )

    # Cross-verification anomalies surfaced in the summary.
    n_anomaly_short_gap = sum(
        1 for row in rows
        if row.get("cross_verification_status") == "phase_repeat_short_gap_ANOMALY"
    )
    n_catch_gap = sum(
        1 for row in rows
        if row.get("cross_verification_status") == "phase_repeat_probably_catch_between"
    )

    return {
        "recording_file": recording_wav.name,
        "participant_id": participant_id_from_filename(recording_wav) or "",
        "status": "decoded",
        "csv_file": str(output_csv),
        "sample_rate": sample_rate,
        "duration_s": round(recording_info.duration_seconds, 1),
        "cues_detected": len(cue_runs),
        "tactile_events_before_anchor": tactile_events_before_anchor,
        "looming_events_before_anchor": looming_events_before_anchor,
        "experiment_anchor_source": experiment_anchor_source,
        "breathing_anchor_start_s": round(breathing_anchor_start_s, 2),
        "tactile_detection_method": tactile_detection_method,
        "adaptive_tactile_cues": int(tactile_profile.get("cue_runs", 0)),
        "adaptive_tactile_threshold_min": round(float(tactile_profile.get("threshold_min", 0.0)), 4),
        "adaptive_tactile_threshold_max": round(float(tactile_profile.get("threshold_max", 0.0)), 4),
        "looming_events_detected": event_pairing_summary["looming_events"],
        "event_pairs": event_pairing_summary["paired_events"],
        "unpaired_tactile_events": event_pairing_summary["unpaired_tactile_events"],
        "unpaired_looming_events": event_pairing_summary["unpaired_looming_events"],
        "event_inventory_csv": str(event_inventory_path),
        "audio_tactile_trials": n_at,
        "baseline_trials": n_bl,
        "hits": n_hit,
        "misses": n_miss,
        "part1_cues": len(rows) - n_part2,
        "part2_cues": n_part2,
        "experiment_start_s": round(experiment_start_s, 2),
        "warmup_template_hits": warmup_template_hits,
        "template_match_status": template_status,
        "template_hits_experimental": len(template_hits_exp),
        "breathing_period_s": xv["breathing_period_s"],
        "breathing_alternation_rate": xv["breathing_alternation_rate"],
        "inhale_events": xv["inhale_events"],
        "exhale_events": xv["exhale_events"],
        "cue_phase_alternation_rate": xv["cue_phase_alternation_rate"],
        "phase_repeat_short_gap_anomalies": n_anomaly_short_gap,
        "phase_repeat_probable_catch_gaps": n_catch_gap,
        "elapsed_seconds": round(elapsed, 2),
        "message": "",
    }


# ---------------------------------------------------------------------------
# Built-in QC and reference rescue
# ---------------------------------------------------------------------------

def wav_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def wav_duration_min(path: Path) -> float:
    return read_wav_info(path).duration_seconds / 60.0


def build_duplicate_map(wav_paths: Sequence[Path]) -> dict[Path, str]:
    by_hash: dict[str, list[Path]] = {}
    for wav_path in wav_paths:
        by_hash.setdefault(wav_md5(wav_path), []).append(wav_path)

    duplicate_map: dict[Path, str] = {}
    for paths in by_hash.values():
        if len(paths) <= 1:
            continue
        preferred = sorted(paths, key=lambda p: (-wav_duration_min(p), p.name))
        master = preferred[0]
        for dup in preferred[1:]:
            duplicate_map[dup] = master.name
    return duplicate_map


def cleanup_output_artifacts_for_wav(wav_path: Path) -> None:
    stems = {wav_path.stem, canonical_output_stem(wav_path)}
    for stem in stems:
        for path in (
            DECODED_DIAGNOSTICS_DIR / f"{stem}.csv",
            DECODED_DIAGNOSTICS_DIR / f"{stem}.rescued.csv",
            FINAL_DIR / f"{stem}.csv",
            EVENT_INVENTORY_DIR / f"{stem}.events.csv",
        ):
            if path.exists():
                path.unlink()


def _soa_label(row: dict[str, Any]) -> str:
    lbl = str(row.get("SOA_type", "")).strip()
    if lbl:
        return lbl
    soa = str(row.get("SOA_ms", "")).strip()
    if not soa:
        return ""
    return f"soa_{soa}ms"


def evaluate_qc(csv_path: Path, wav_path: Path, duplicate_of: str | None) -> dict[str, Any]:
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    tt = Counter(r["trial_type"] for r in rows)
    ph = Counter(r["phase"] for r in rows)
    alt = Counter(r.get("phase_alternation_check", "") for r in rows)
    outcomes = Counter(r["outcome"] for r in rows)
    parts = Counter(str(r.get("part_number", "")) for r in rows)
    block_sizes = Counter(
        (str(r.get("part_number", "")).strip(), str(r.get("block_number", "")).strip())
        for r in rows
        if str(r.get("part_number", "")).strip() and str(r.get("block_number", "")).strip()
    )

    rts = [
        int(r["reaction_time_ms"])
        for r in rows
        if r.get("response_detected") == "True" and str(r.get("reaction_time_ms", "")).strip()
    ]
    at_rows = [
        r for r in rows
        if r["trial_type"] == "Audio-Tactile"
        and _soa_label(r) in QC_NOMINAL_SOAS
        and r.get("phase") in ("Inhale", "Exhale")
    ]
    cell_counts = Counter((_soa_label(r), r["phase"]) for r in at_rows)
    min_cell = min(cell_counts.values()) if cell_counts else 0
    at = tt.get("Audio-Tactile", 0)
    bl = tt.get("Baseline", 0)
    catches = tt.get("Catch", 0)
    false_alarms = outcomes.get("false_alarm", 0)
    correct_rejections = outcomes.get("correct_rejection", 0)
    fa_rate = false_alarms / max(false_alarms + correct_rejections, 1)
    anomalies = alt.get("anomaly", 0)
    duration_min = wav_duration_min(wav_path)
    unknown_phases = ph.get("Unknown", 0)
    block_size_values = list(block_sizes.values())
    median_block_size = statistics.median(block_size_values) if block_size_values else 0
    tiny_blocks = [
        (part_num, block_num, size)
        for (part_num, block_num), size in block_sizes.items()
        if median_block_size and size < 0.5 * median_block_size
    ]
    irregular_blocks = [
        (part_num, block_num, size)
        for (part_num, block_num), size in block_sizes.items()
        if median_block_size and (size < 0.8 * median_block_size or size > 1.2 * median_block_size)
    ]

    reasons: list[str] = []
    fail = False
    warn = False
    if duplicate_of:
        reasons.append(f"duplicate_of_{duplicate_of}")
        fail = True
    if duration_min < 50.0:
        reasons.append(f"duration_short({duration_min:.1f}_min)")
        fail = True
    elif duration_min < 60.0:
        reasons.append(f"duration_single_session({duration_min:.1f}_min)")
        warn = True
    if at < 180:
        reasons.append(f"AT_count_low({at})")
        fail = True
    elif at < 220:
        reasons.append(f"AT_count_mild({at})")
        warn = True
    if bl < 90:
        reasons.append(f"BL_count_low({bl})")
        fail = True
    elif bl < 105:
        reasons.append(f"BL_count_mild({bl})")
        warn = True
    if min_cell == 0:
        reasons.append("empty_cell_in_phase_x_SOA")
        fail = True
    elif min_cell < 5:
        reasons.append(f"min_cell_thin({min_cell})")
        warn = True
    if unknown_phases > 0:
        reasons.append(f"unknown_phases({unknown_phases})")
        fail = True
    if fa_rate > 0.30:
        reasons.append(f"catch_FA_rate_{fa_rate:.2f}_over_0.30")
        fail = True
    elif fa_rate > 0.10:
        reasons.append(f"catch_FA_rate_{fa_rate:.2f}")
        warn = True
    if anomalies > 1:
        reasons.append(f"alternation_anomalies_{anomalies}")
        fail = True
    elif anomalies == 1:
        reasons.append("alternation_anomaly_1")
        warn = True
    if tiny_blocks:
        reasons.append(f"tiny_block_fragments({len(tiny_blocks)})")
        fail = True
    elif irregular_blocks:
        reasons.append(f"irregular_block_sizes({len(irregular_blocks)})")
        fail = True

    p1 = parts.get("1", 0)
    p2 = parts.get("2", 0)
    if p1 == 0 or p2 == 0:
        reasons.append(f"part_imbalance(P1={p1},P2={p2})")
        warn = True
    elif min(p1, p2) < 50:
        reasons.append(f"part_imbalance(P1={p1},P2={p2})")
        warn = True

    status = "FAIL" if fail else ("WARN" if warn else "PASS")
    return {
        "recording_file": wav_path.name,
        "participant_id": participant_id_from_filename(wav_path) or "",
        "wav_duration_min": round(duration_min, 1),
        "wav_md5_prefix": wav_md5(wav_path)[:12],
        "rows": len(rows),
        "AT": at,
        "BL": bl,
        "Catch": catches,
        "Inhale": ph.get("Inhale", 0),
        "Exhale": ph.get("Exhale", 0),
        "Unknown": ph.get("Unknown", 0),
        "alternation_anomalies": anomalies,
        "hits": outcomes.get("hit", 0) + outcomes.get("hit_inferred", 0),
        "misses": outcomes.get("no_click_detected", 0) + outcomes.get("baseline_no_click", 0),
        "false_alarms": false_alarms,
        "correct_rejections": correct_rejections,
        "catch_fa_rate": round(fa_rate, 3),
        "rt_median_ms": round(statistics.median(rts)) if rts else "",
        "part1_cues": p1,
        "part2_cues": p2,
        "min_phaseSOA_cell_AT": min_cell,
        "status": status,
        "reasons": "; ".join(reasons) if reasons else "all_checks_passed",
    }


def qc_is_rescue_eligible(qc_row: dict[str, Any], wav_path: Path) -> bool:
    if qc_row["status"] != "FAIL":
        return False
    if "duplicate_of_" in str(qc_row["reasons"]):
        return False
    if "duration_short(" in str(qc_row["reasons"]):
        return False
    pid = participant_id_from_filename(wav_path)
    if not pid or not (REFERENCE_SEQUENCE_ROOT / pid).exists():
        return False
    rescue_markers = (
        "AT_count_low(",
        "BL_count_low(",
        "empty_cell_in_phase_x_SOA",
        "part_imbalance(",
        "catch_FA_rate_",
        "unknown_phases(",
        "tiny_block_fragments(",
        "irregular_block_sizes(",
    )
    return any(marker in str(qc_row["reasons"]) for marker in rescue_markers)


def promote_final_csv(src_csv: Path, dst_csv: Path) -> int:
    rows = list(csv.DictReader(src_csv.open(encoding="utf-8")))
    dst_csv.parent.mkdir(parents=True, exist_ok=True)
    with dst_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FINAL_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            if not row.get("data_source"):
                row["data_source"] = "observed"
            if not row.get("experiment_half"):
                row["experiment_half"] = experiment_half_from_part(row.get("part_number"))
            if not row.get("condition"):
                row["condition"] = condition_from_part(row.get("part_number"))
            if not row.get("tactile_event"):
                row["tactile_event"] = row.get("trial_type") != "Catch"
            if not row.get("looming_detected"):
                row["looming_detected"] = row.get("trial_type") in ("Audio-Tactile", "Catch")
            writer.writerow(row)
    return len(rows)


def parse_block_sequence(txt: Path) -> dict[int, list[str]]:
    text = txt.read_text(encoding="utf-8")
    out: dict[int, list[str]] = {}
    for part_num, pattern in ((1, r"Part1 Block Sequence:\s*([^\n]+)"), (2, r"Part2 Block Sequence:\s*([^\n]+)")):
        m = re.search(pattern, text)
        if not m:
            continue
        out[part_num] = [s.strip() for s in m.group(1).split("->") if s.strip()]
    return out


def load_planned_trial_table(pid: str) -> list[dict[str, Any]] | None:
    participant_dir = REFERENCE_SEQUENCE_ROOT / pid
    seq_txt = participant_dir / "block_sequence.txt"
    if not seq_txt.exists():
        return None
    parts_order = parse_block_sequence(seq_txt)
    if not parts_order:
        return None

    def find_block_csv(part_num: int, letter: str) -> Path | None:
        part_dir = participant_dir / f"Part{part_num}"
        if not part_dir.exists():
            return None
        for csv_path in part_dir.glob("*.csv"):
            if re.search(rf"_part{part_num}_\d+{letter}\.csv$", csv_path.name, re.IGNORECASE):
                return csv_path
        return None

    flat: list[dict[str, Any]] = []
    for part_num in (1, 2):
        for block_idx, letter in enumerate(parts_order.get(part_num, []), start=1):
            csv_path = find_block_csv(part_num, letter)
            if csv_path is None:
                continue
            rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
            for trial_idx, row in enumerate(rows, start=1):
                flat.append(
                    {
                        "part_number": part_num,
                        "block_number_in_part": block_idx,
                        "block_letter": letter,
                        "trial_number_in_block": trial_idx,
                        "Trial_Type": row["Trial_Type"],
                        "SOA_ms": row["SOA_ms"],
                        "Noise_Type": row["Noise_Type"],
                        "Respiratory_Phase": row["Respiratory_Phase"],
                    }
                )
    return flat or None


def group_breathing_hits_into_blocks(
    hits: list[BreathingTemplateHit],
    min_block_gap_s: float = 24.0,
    min_part_gap_s: float = 100.0,
) -> tuple[list[list[BreathingTemplateHit]], int | None]:
    if not hits:
        return [], None
    hits_sorted = sorted(hits, key=lambda h: h.start_s)
    block_groups: list[list[BreathingTemplateHit]] = [[hits_sorted[0]]]
    for prev, cur in zip(hits_sorted, hits_sorted[1:]):
        if cur.start_s - prev.start_s > min_block_gap_s:
            block_groups.append([])
        block_groups[-1].append(cur)

    block_start_gaps: list[tuple[int, float]] = []
    for group_idx in range(1, len(block_groups)):
        prev_last = block_groups[group_idx - 1][-1]
        first = block_groups[group_idx][0]
        block_start_gaps.append((group_idx, first.start_s - prev_last.start_s))

    part2_start = None
    if block_start_gaps:
        gidx, gap = max(block_start_gaps, key=lambda item: item[1])
        if gap >= min_part_gap_s:
            part2_start = gidx
    return block_groups, part2_start


def find_observed_tactile_cue(
    cue_samples: np.ndarray,
    expected_time_s: float,
    sample_rate: int,
    window_s: float = 0.4,
) -> int | None:
    if len(cue_samples) == 0:
        return None
    expected_sample = int(round(expected_time_s * sample_rate))
    diffs = np.abs(cue_samples - expected_sample)
    closest = int(np.argmin(diffs))
    if diffs[closest] <= int(round(window_s * sample_rate)):
        return int(cue_samples[closest])
    return None


def find_observed_click(
    tactile_signal: np.ndarray,
    anchor_sample: int,
    sample_rate: int,
    click_template: np.ndarray,
    pps: Any,
    search_pre_s: float = 0.03,
    search_post_s: float = 2.0,
) -> int | None:
    search_start = max(0, anchor_sample + int(round(search_pre_s * sample_rate)))
    search_end = min(len(tactile_signal), anchor_sample + int(round(search_post_s * sample_rate)))
    detected, click_start_abs, _peak, _thr = _first_click_in_window(
        tactile_signal=tactile_signal,
        search_start=search_start,
        search_end=search_end,
        click_template=click_template,
        sample_rate=sample_rate,
        pps=pps,
    )
    return click_start_abs if detected else None


def rescue_recording(recording_wav: Path, pps: Any, overwrite: bool) -> dict[str, Any] | None:
    pid = participant_id_from_filename(recording_wav)
    if pid is None:
        return None
    planned = load_planned_trial_table(pid)
    if planned is None:
        return None

    rescue_csv = DECODED_DIAGNOSTICS_DIR / f"{canonical_output_stem(recording_wav)}.rescued.csv"
    if rescue_csv.exists() and not overwrite:
        return {"status": "skipped_existing_rescue", "csv_file": str(rescue_csv)}

    print(f"[{recording_wav.name}] rescue: loading recording")
    recording_samples, recording_info = pps.read_wav_frames(recording_wav)
    sample_rate = recording_info.sample_rate
    audio_channel, tactile_channel = pps.infer_recording_channel_roles(recording_samples)
    audio_signal = recording_samples[:, audio_channel].astype(np.float32)
    tactile_signal = recording_samples[:, tactile_channel].astype(np.float32)

    templates_audio = load_breathing_templates(sample_rate)
    if templates_audio is None:
        return None
    breathing_hits = detect_breathing_events_via_templates(
        audio_signal=audio_signal,
        sample_rate=sample_rate,
        templates=templates_audio,
    )
    breathing_hits = [h for h in breathing_hits if h.start_s >= 60.0]
    block_groups, part2_start = group_breathing_hits_into_blocks(breathing_hits)
    kept_groups: list[list[BreathingTemplateHit]] = []
    kept_part2_start: int | None = None
    for group_idx, group in enumerate(block_groups):
        if len(group) < 20:
            continue
        if part2_start is not None and group_idx >= part2_start and kept_part2_start is None:
            kept_part2_start = len(kept_groups)
        kept_groups.append(group)
    block_groups = kept_groups
    part2_start = kept_part2_start
    if len(block_groups) < 2:
        return None
    if part2_start is None or part2_start > len(block_groups):
        part2_start = len(block_groups) // 2

    planned_part1_blocks = [
        [t for t in planned if t["part_number"] == 1 and t["block_number_in_part"] == b]
        for b in sorted({t["block_number_in_part"] for t in planned if t["part_number"] == 1})
    ]
    planned_part2_blocks = [
        [t for t in planned if t["part_number"] == 2 and t["block_number_in_part"] == b]
        for b in sorted({t["block_number_in_part"] for t in planned if t["part_number"] == 2})
    ]
    observed_part1 = block_groups[:part2_start]
    observed_part2 = block_groups[part2_start:]

    runs, _cue_threshold = pps.detect_tactile_event_runs(tactile_signal, sample_rate)
    cue_runs = pps.select_tactile_cue_runs(runs, sample_rate)
    cue_samples = np.array([run.start_sample for run in cue_runs], dtype=np.int64)
    click_template, _ = pps.load_click_template()

    trial_unit_s = 8.0
    stimulus_offset_s = 4.0
    looming_pre_cue_pad_s = 0.5
    rows: list[dict[str, Any]] = []
    global_idx = 0

    for part_num, observed_blocks, planned_blocks in (
        (1, observed_part1, planned_part1_blocks),
        (2, observed_part2, planned_part2_blocks),
    ):
        for block_idx, (obs_block, plan_block) in enumerate(zip(observed_blocks, planned_blocks), start=1):
            if not obs_block:
                continue
            block_start_s = obs_block[0].start_s
            for trial in plan_block:
                global_idx += 1
                trial_idx = trial["trial_number_in_block"]
                trial_start_s = block_start_s + (trial_idx - 1) * trial_unit_s
                trial_type = trial["Trial_Type"]
                phase = trial["Respiratory_Phase"]
                soa_ms = int(trial["SOA_ms"]) if str(trial["SOA_ms"]).strip().isdigit() else None
                noise_type = trial["Noise_Type"]
                row: dict[str, Any] = {
                    "participant_id": pid,
                    "participant_number": int(pid[1:]),
                    "recording_file": recording_wav.name,
                    "experiment_half": experiment_half_from_part(part_num),
                    "condition": condition_from_part(part_num),
                    "part_number": part_num,
                    "block_number": block_idx,
                    "trial_number": trial_idx,
                    "trial_number_global": global_idx,
                    "tactile_event": trial_type != "Catch",
                    "trial_unit_start_s": round(trial_start_s, 3),
                    "trial_unit_end_s": round(trial_start_s + trial_unit_s, 3),
                    "trial_type": trial_type,
                    "trial_type_confidence": "reference_rescue",
                    "looming_detected": trial_type in ("Audio-Tactile", "Catch"),
                    "phase": phase,
                    "phase_source": "reference_rescue",
                    "phase_agreement": "reference_rescue",
                    "phase_template": phase,
                    "phase_template_confidence": "reference_rescue",
                    "phase_template_score": "",
                    "phase_template_margin": "",
                    "cross_verification_status": "rescued",
                    "SOA_ms": "" if trial_type in ("Baseline", "Catch") else soa_ms,
                    "SOA_type": ("baseline" if trial_type == "Baseline" else ("catch" if trial_type == "Catch" else f"soa_{soa_ms}ms")),
                    "SOA_raw_ms": "",
                    "SOA_quantization_error_ms": "",
                    "noise_type": noise_type if noise_type != "N/A" else "N/A",
                    "noise_type_confidence": "",
                    "noise_type_source": "reference_rescue",
                    "looming_template_score": "",
                    "reaction_time_ms": "",
                    "reaction_time_start_to_start_ms": "",
                    "response_detected": False,
                    "outcome": "",
                    "tactile_cue_time_s": "",
                    "tactile_cue_midpoint_s": "",
                    "tactile_cue_sample": "",
                    "looming_onset_time_s": "",
                    "looming_peak_ratio": "",
                    "looming_ramp_ratio": "",
                    "click_time_s": "",
                    "click_midpoint_s": "",
                    "hold_word_time_s": "",
                    "hold_source": "reference_rescue",
                    "hold_time_template_s": "",
                    "data_source": "inferred_from_reference",
                }

                if trial_type in ("Audio-Tactile", "Baseline") and soa_ms is not None:
                    expected_cue_s = trial_start_s + stimulus_offset_s + looming_pre_cue_pad_s + (soa_ms / 1000.0)
                    cue_sample = find_observed_tactile_cue(cue_samples, expected_cue_s, sample_rate)
                    if cue_sample is not None:
                        row["tactile_cue_time_s"] = round(cue_sample / sample_rate, 6)
                        row["tactile_cue_midpoint_s"] = round((cue_sample + int(round(0.05 * sample_rate))) / sample_rate, 6)
                        row["tactile_cue_sample"] = cue_sample
                        click_sample = find_observed_click(tactile_signal, cue_sample, sample_rate, click_template, pps)
                        row["data_source"] = "observed"
                        if click_sample is not None:
                            row["click_time_s"] = round(click_sample / sample_rate, 6)
                            row["click_midpoint_s"] = round((click_sample + len(click_template) / 2.0) / sample_rate, 6)
                            row["reaction_time_ms"] = int(round((click_sample - cue_sample) * 1000.0 / sample_rate))
                            row["reaction_time_start_to_start_ms"] = row["reaction_time_ms"]
                            row["response_detected"] = True
                            row["outcome"] = "hit"
                        else:
                            row["data_source"] = "observed_partial"
                            row["outcome"] = "no_click_detected" if trial_type == "Audio-Tactile" else "baseline_no_click"
                    else:
                        anchor_sample = int(round(expected_cue_s * sample_rate))
                        click_sample = find_observed_click(tactile_signal, anchor_sample, sample_rate, click_template, pps)
                        if click_sample is not None:
                            row["click_time_s"] = round(click_sample / sample_rate, 6)
                            row["click_midpoint_s"] = round((click_sample + len(click_template) / 2.0) / sample_rate, 6)
                            row["reaction_time_ms"] = int(round((click_sample - anchor_sample) * 1000.0 / sample_rate))
                            row["reaction_time_start_to_start_ms"] = row["reaction_time_ms"]
                            row["response_detected"] = True
                            row["outcome"] = "hit_inferred"
                        else:
                            row["outcome"] = "no_click_detected" if trial_type == "Audio-Tactile" else "baseline_no_click"
                elif trial_type == "Catch":
                    anchor_s = trial_start_s + stimulus_offset_s + looming_pre_cue_pad_s + 0.5
                    click_sample = find_observed_click(
                        tactile_signal,
                        int(round(anchor_s * sample_rate)),
                        sample_rate,
                        click_template,
                        pps,
                    )
                    if click_sample is not None:
                        row["click_time_s"] = round(click_sample / sample_rate, 6)
                        row["click_midpoint_s"] = round((click_sample + len(click_template) / 2.0) / sample_rate, 6)
                        row["response_detected"] = True
                        row["outcome"] = "false_alarm"
                        row["data_source"] = "observed"
                    else:
                        row["outcome"] = "correct_rejection"
                rows.append(row)

    write_rows(rescue_csv, rows)
    return {
        "status": "rescued",
        "csv_file": str(rescue_csv),
        "rows": len(rows),
        "observed_rows": sum(1 for row in rows if row["data_source"] == "observed"),
        "inferred_rows": sum(1 for row in rows if row["data_source"] == "inferred_from_reference"),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def qc_status_rank(status: str) -> int:
    return {"FAIL": 0, "WARN": 1, "PASS": 2}.get(status, -1)


def should_prefer_rescue_qc(bottom_up_qc: dict[str, Any], rescue_qc: dict[str, Any]) -> bool:
    """Choose the rescue result only when it is genuinely stronger.

    A rescue PASS always wins. Otherwise, if rescue is only one rank better
    but reconstructs substantially fewer rows than the bottom-up decode, keep
    the fuller bottom-up result for diagnostics and avoid silently replacing it
    with a shorter partial rescue.
    """
    bottom_rank = qc_status_rank(str(bottom_up_qc.get("status", "")))
    rescue_rank = qc_status_rank(str(rescue_qc.get("status", "")))
    if rescue_rank <= bottom_rank:
        return False
    if str(rescue_qc.get("status", "")) == "PASS":
        return True

    bottom_rows = int(bottom_up_qc.get("rows", 0) or 0)
    rescue_rows = int(rescue_qc.get("rows", 0) or 0)
    if bottom_rows and rescue_rows < 0.90 * bottom_rows:
        return False
    return True


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decode local PPS loopback WAV recordings into analysis-ready CSV files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Only process files whose names contain this text. Can be repeated.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate diagnostics, rescue, final, and summary outputs.",
    )
    parser.add_argument("--input-dir", type=Path, help="Directory containing loopback WAV recordings.")
    parser.add_argument("--output-dir", type=Path, help="Directory for decoded outputs.")
    parser.add_argument("--reference-sequence-root", type=Path, help="Generated participant sequence directory.")
    parser.add_argument("--click-tone", type=Path, help="Click-tone WAV template path.")
    parser.add_argument("--looming-root", type=Path, help="Directory containing generated looming WAV templates.")
    parser.add_argument("--breathing-dir", type=Path, help="Directory containing generated 4-second breathing WAV templates.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    configure_paths(args)
    pps = load_pps_module()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARIES_DIR.mkdir(parents=True, exist_ok=True)
    EVENT_INVENTORY_DIR.mkdir(parents=True, exist_ok=True)

    wav_paths = [
        path
        for path in sorted(INPUT_DIR.glob("*.wav"), key=natural_key)
        if should_process(path, args.only)
    ]
    if not wav_paths:
        print("No matching WAV files found.")
        return 0

    duplicate_map = build_duplicate_map(wav_paths)
    recordings_summaries: list[dict[str, Any]] = []
    qc_rows: list[dict[str, Any]] = []
    pipeline_rows: list[dict[str, Any]] = []

    for wav_path in wav_paths:
        participant_id = participant_id_from_filename(wav_path) or ""
        output_stem = canonical_output_stem(wav_path)
        diagnostics_csv = DECODED_DIAGNOSTICS_DIR / f"{output_stem}.csv"
        rescue_csv = DECODED_DIAGNOSTICS_DIR / f"{output_stem}.rescued.csv"
        final_csv = FINAL_DIR / f"{output_stem}.csv"

        if args.overwrite:
            cleanup_output_artifacts_for_wav(wav_path)

        if wav_path in duplicate_map:
            if final_csv.exists():
                final_csv.unlink()
            duplicate_of = duplicate_map[wav_path]
            qc_row = {
                "recording_file": wav_path.name,
                "participant_id": participant_id,
                "wav_duration_min": round(wav_duration_min(wav_path), 1),
                "wav_md5_prefix": wav_md5(wav_path)[:12],
                "rows": 0,
                "AT": 0,
                "BL": 0,
                "Catch": 0,
                "Inhale": 0,
                "Exhale": 0,
                "Unknown": 0,
                "alternation_anomalies": 0,
                "hits": 0,
                "misses": 0,
                "false_alarms": 0,
                "correct_rejections": 0,
                "catch_fa_rate": "",
                "rt_median_ms": "",
                "part1_cues": 0,
                "part2_cues": 0,
                "min_phaseSOA_cell_AT": 0,
                "status": "FAIL",
                "reasons": f"duplicate_of_{duplicate_of}",
                "source_csv": "",
                "decode_source": "duplicate_skipped",
                "promoted_to_final": False,
                "final_csv": "",
                "rescue_status": "not_attempted",
            }
            qc_rows.append(qc_row)
            pipeline_rows.append(
                {
                    "recording_file": wav_path.name,
                    "participant_id": participant_id,
                    "diagnostics_csv": "",
                    "rescue_csv": "",
                    "final_csv": "",
                    "bottom_up_status": "duplicate_skipped",
                    "rescue_status": "not_attempted",
                    "final_status": "FAIL",
                    "pipeline_status": "duplicate_skipped",
                    "message": f"Skipped duplicate of {duplicate_of}.",
                }
            )
            continue

        bottom_up_summary: dict[str, Any] | None = None
        bottom_up_qc: dict[str, Any] | None = None
        rescue_result: dict[str, Any] | None = None
        rescue_qc: dict[str, Any] | None = None
        selected_qc: dict[str, Any] | None = None
        selected_csv = diagnostics_csv
        selected_source = "bottom_up"

        try:
            bottom_up_summary = decode_recording(
                recording_wav=wav_path,
                pps=pps,
                overwrite=args.overwrite,
            )
            recordings_summaries.append(bottom_up_summary)
            bottom_up_qc = evaluate_qc(Path(bottom_up_summary["csv_file"]), wav_path, duplicate_of=None)
            bottom_up_qc["source_csv"] = str(Path(bottom_up_summary["csv_file"]).resolve())
            bottom_up_qc["decode_source"] = "bottom_up"
            bottom_up_qc["promoted_to_final"] = False
            bottom_up_qc["final_csv"] = ""
            bottom_up_qc["rescue_status"] = "not_attempted"

            if qc_is_rescue_eligible(bottom_up_qc, wav_path):
                rescue_result = rescue_recording(wav_path, pps, overwrite=args.overwrite)
                if rescue_result and rescue_result.get("csv_file"):
                    rescue_csv_path = Path(rescue_result["csv_file"])
                    if rescue_csv_path.exists():
                        rescue_qc = evaluate_qc(rescue_csv_path, wav_path, duplicate_of=None)
                        rescue_qc["source_csv"] = str(rescue_csv_path.resolve())
                        rescue_qc["decode_source"] = "rescued"
                        rescue_qc["promoted_to_final"] = False
                        rescue_qc["final_csv"] = ""
                        rescue_qc["rescue_status"] = rescue_result["status"]

            selected_qc = bottom_up_qc
            if rescue_qc is not None and should_prefer_rescue_qc(bottom_up_qc, rescue_qc):
                selected_qc = rescue_qc
                selected_csv = Path(rescue_qc["source_csv"])
                selected_source = "rescued"

            if selected_qc["status"] == "PASS":
                n_written = promote_final_csv(selected_csv, final_csv)
                selected_qc["promoted_to_final"] = True
                selected_qc["final_csv"] = str(final_csv.resolve())
                print(f"[{wav_path.name}] promoted final CSV ({n_written} rows) from {selected_source}")
            elif final_csv.exists():
                final_csv.unlink()

            selected_qc["rescue_status"] = rescue_result["status"] if rescue_result is not None else "not_attempted"
            qc_rows.append(selected_qc)
            pipeline_rows.append(
                {
                    "recording_file": wav_path.name,
                    "participant_id": participant_id,
                    "diagnostics_csv": str(diagnostics_csv.resolve()) if diagnostics_csv.exists() else "",
                    "rescue_csv": str(rescue_csv.resolve()) if rescue_csv.exists() else "",
                    "final_csv": str(final_csv.resolve()) if final_csv.exists() else "",
                    "bottom_up_status": bottom_up_qc["status"] if bottom_up_qc else "",
                    "rescue_status": rescue_result["status"] if rescue_result is not None else "not_attempted",
                    "final_status": selected_qc["status"],
                    "pipeline_status": (
                        "promoted_final"
                        if final_csv.exists()
                        else ("rescued_but_not_promoted" if selected_source == "rescued" else "decoded_not_promoted")
                    ),
                    "message": selected_qc["reasons"],
                }
            )
        except Exception as exc:
            if final_csv.exists():
                final_csv.unlink()
            failure_row = {
                "recording_file": wav_path.name,
                "participant_id": participant_id,
                "wav_duration_min": round(wav_duration_min(wav_path), 1),
                "wav_md5_prefix": wav_md5(wav_path)[:12],
                "rows": 0,
                "AT": 0,
                "BL": 0,
                "Catch": 0,
                "Inhale": 0,
                "Exhale": 0,
                "Unknown": 0,
                "alternation_anomalies": 0,
                "hits": 0,
                "misses": 0,
                "false_alarms": 0,
                "correct_rejections": 0,
                "catch_fa_rate": "",
                "rt_median_ms": "",
                "part1_cues": 0,
                "part2_cues": 0,
                "min_phaseSOA_cell_AT": 0,
                "status": "FAIL",
                "reasons": f"decoder_exception({type(exc).__name__}: {exc})",
                "source_csv": "",
                "decode_source": "exception",
                "promoted_to_final": False,
                "final_csv": "",
                "rescue_status": "not_attempted",
            }
            qc_rows.append(failure_row)
            recordings_summaries.append(
                {
                    "recording_file": wav_path.name,
                    "participant_id": participant_id,
                    "status": "failed_exception",
                    "csv_file": "",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            pipeline_rows.append(
                {
                    "recording_file": wav_path.name,
                    "participant_id": participant_id,
                    "diagnostics_csv": "",
                    "rescue_csv": "",
                    "final_csv": "",
                    "bottom_up_status": "failed_exception",
                    "rescue_status": "not_attempted",
                    "final_status": "FAIL",
                    "pipeline_status": "failed_exception",
                    "message": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[{wav_path.name}] failed: {exc}", file=sys.stderr)

    if recordings_summaries:
        recordings_summary_path = SUMMARIES_DIR / "recordings_summary.csv"
        write_rows(recordings_summary_path, recordings_summaries)
        print(f"Wrote summary: {recordings_summary_path}")

    if qc_rows:
        qc_report_path = SUMMARIES_DIR / "qc_report.csv"
        write_rows(qc_report_path, qc_rows)
        print(f"Wrote QC report: {qc_report_path}")

    if pipeline_rows:
        pipeline_report_path = SUMMARIES_DIR / "pipeline_report.csv"
        write_rows(pipeline_report_path, pipeline_rows)
        print(f"Wrote pipeline report: {pipeline_report_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
