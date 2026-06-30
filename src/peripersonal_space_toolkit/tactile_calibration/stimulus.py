"""Transient WAV generation for tactile calibration trials."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import wave

import numpy as np

from .schema import (
    DEFAULT_CHANNEL_COUNT,
    DEFAULT_POST_SILENCE_MS,
    DEFAULT_PRE_SILENCE_MS,
    DEFAULT_PULSE_DURATION_MS,
    DEFAULT_SAMPLE_RATE_HZ,
)


@dataclass(frozen=True)
class TactileStimulusInfo:
    path: str
    sample_rate_hz: int
    channels: int
    duration_ms: float
    pre_silence_ms: float
    pulse_duration_ms: float
    post_silence_ms: float
    level_percent: float
    pulse_scale_percent: float
    is_catch: bool
    source_pulse_path: str
    used_fallback_pulse: bool
    peak_abs_int16: int


def _read_mono_pcm16(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as handle:
        channels = int(handle.getnchannels())
        sample_rate = int(handle.getframerate())
        sample_width = int(handle.getsampwidth())
        frames = int(handle.getnframes())
        raw = handle.readframes(frames)
    if sample_width != 2:
        raise ValueError(f"Expected 16-bit PCM tactile cue, got sample width {sample_width}.")
    data = np.frombuffer(raw, dtype="<i2").astype(np.float32)
    if channels > 1:
        data = data.reshape((-1, channels))[:, 0]
    return data / 32767.0, sample_rate


def _fallback_pulse(sample_rate_hz: int, duration_ms: float) -> np.ndarray:
    frames = max(1, int(round(sample_rate_hz * duration_ms / 1000.0)))
    t = np.arange(frames, dtype=np.float32) / float(sample_rate_hz)
    attack_frames = max(1, int(round(frames * 0.3)))
    attack = np.sin(2.0 * math.pi * 200.0 * t[:attack_frames])
    decay = np.sin(2.0 * math.pi * 50.0 * t[attack_frames:])
    envelope = np.ones(frames, dtype=np.float32)
    envelope[:attack_frames] = np.linspace(0.0, 1.0, attack_frames, dtype=np.float32)
    if frames > attack_frames:
        envelope[attack_frames:] = np.linspace(0.85, 0.0, frames - attack_frames, dtype=np.float32)
    pulse = np.concatenate([attack, decay]).astype(np.float32) * envelope
    peak = float(np.max(np.abs(pulse))) if pulse.size else 1.0
    return pulse / max(peak, 1e-6)


def _source_or_fallback_pulse(
    *,
    source_pulse_path: Path | None,
    sample_rate_hz: int,
    pulse_duration_ms: float,
) -> tuple[np.ndarray, bool, str]:
    source_text = ""
    if source_pulse_path is not None and Path(source_pulse_path).is_file():
        source_text = str(Path(source_pulse_path))
        try:
            pulse, source_rate = _read_mono_pcm16(Path(source_pulse_path))
            if int(source_rate) != int(sample_rate_hz):
                raise ValueError(f"source sample rate {source_rate} does not match {sample_rate_hz}")
            desired_frames = max(1, int(round(sample_rate_hz * pulse_duration_ms / 1000.0)))
            if pulse.shape[0] > desired_frames:
                pulse = pulse[:desired_frames]
            elif pulse.shape[0] < desired_frames:
                pulse = np.pad(pulse, (0, desired_frames - pulse.shape[0]))
            return pulse.astype(np.float32), False, source_text
        except Exception:
            pass
    return _fallback_pulse(sample_rate_hz, pulse_duration_ms), True, source_text


def write_calibration_trial_wav(
    path: Path,
    *,
    level_percent: float,
    is_catch: bool = False,
    source_pulse_path: Path | None = None,
    sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ,
    channels: int = DEFAULT_CHANNEL_COUNT,
    pre_silence_ms: float = DEFAULT_PRE_SILENCE_MS,
    pulse_duration_ms: float = DEFAULT_PULSE_DURATION_MS,
    post_silence_ms: float = DEFAULT_POST_SILENCE_MS,
    pulse_scale_percent: float | None = None,
) -> TactileStimulusInfo:
    """Write a transient 3-channel calibration WAV and return its geometry."""

    if channels < 3:
        raise ValueError("Tactile calibration WAVs require at least three channels.")
    level = max(0.0, min(100.0, float(level_percent)))
    pulse_scale = level if pulse_scale_percent is None else max(0.0, min(100.0, float(pulse_scale_percent)))
    pre_frames = max(0, int(round(sample_rate_hz * float(pre_silence_ms) / 1000.0)))
    post_frames = max(0, int(round(sample_rate_hz * float(post_silence_ms) / 1000.0)))
    pulse, used_fallback, source_text = _source_or_fallback_pulse(
        source_pulse_path=source_pulse_path,
        sample_rate_hz=sample_rate_hz,
        pulse_duration_ms=pulse_duration_ms,
    )
    if is_catch:
        pulse = np.zeros_like(pulse)
    else:
        pulse = np.clip(pulse * (pulse_scale / 100.0), -1.0, 1.0)
    frames = pre_frames + int(pulse.shape[0]) + post_frames
    data = np.zeros((frames, channels), dtype=np.float32)
    if pulse.size:
        data[pre_frames : pre_frames + pulse.shape[0], 2] = pulse
    int_data = np.clip(data * 32767.0, -32768.0, 32767.0).astype("<i2")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate_hz)
        handle.writeframes(int_data.tobytes())
    return TactileStimulusInfo(
        path=str(path),
        sample_rate_hz=int(sample_rate_hz),
        channels=int(channels),
        duration_ms=frames / float(sample_rate_hz) * 1000.0,
        pre_silence_ms=float(pre_silence_ms),
        pulse_duration_ms=float(pulse.shape[0]) / float(sample_rate_hz) * 1000.0,
        post_silence_ms=float(post_silence_ms),
        level_percent=level,
        pulse_scale_percent=pulse_scale,
        is_catch=bool(is_catch),
        source_pulse_path=source_text,
        used_fallback_pulse=bool(used_fallback),
        peak_abs_int16=int(np.max(np.abs(int_data))) if int_data.size else 0,
    )
