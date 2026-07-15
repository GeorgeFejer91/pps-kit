import math
import wave
from pathlib import Path

import numpy as np
import pytest

from peripersonal_space_toolkit import decoder


def _write_mono_wav(path: Path, sample_rate: int = 44100) -> None:
    t = np.arange(int(sample_rate * 0.25), dtype=np.float32) / float(sample_rate)
    samples = (0.4 * np.sin(2.0 * math.pi * 440.0 * t)).astype(np.float32)
    pcm = np.clip(samples * 32767.0, -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm.tobytes())


def test_load_breathing_templates_reads_wav_without_ffmpeg(monkeypatch, tmp_path):
    _write_mono_wav(tmp_path / "Inhale-2-3-4-hold_FIXED.wav")
    _write_mono_wav(tmp_path / "Exhale-2-3-4-hold_FIXED.wav")

    def fail_if_mp3_path_is_used(*_args, **_kwargs):
        pytest.fail("WAV templates should not require ffmpeg decoding")

    monkeypatch.setattr(decoder, "BREATHING_INSTRUCTION_ROOT", tmp_path)
    monkeypatch.setattr(decoder, "_decode_mp3_to_mono_float", fail_if_mp3_path_is_used)

    templates = decoder.load_breathing_templates(44100)

    assert templates is not None
    assert set(templates) == {"Inhale", "Exhale", "Inhale_head", "Exhale_head"}
    assert templates["Inhale"].dtype == np.float32
    assert templates["Exhale"].size > 0
