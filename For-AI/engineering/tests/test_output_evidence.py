from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from peripersonal_space_toolkit.output_evidence import OutputEvidenceRecorder


def test_output_evidence_recorder_writes_exact_callback_buffers(tmp_path: Path):
    path = tmp_path / "Block_01_audio_evidence.wav"
    recorder = OutputEvidenceRecorder(queue_size=8)
    first = np.array([[0.1, -0.2, 0.3], [0.4, 0.0, -0.4]], dtype=np.float32)
    second = np.array([[0.0, 0.2, 0.0]], dtype=np.float32)

    assert recorder.start(path, metadata={"block_index": 1, "sample_rate_hz": 1000})
    recorder.write_buffer(first, sample_rate=1000)
    recorder.write_buffer(second, sample_rate=1000)
    summary = recorder.stop()

    data, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    np.testing.assert_allclose(data, np.vstack([first, second]), atol=1e-6)
    assert sample_rate == 1000
    assert summary["frames"] == 3
    assert summary["channels"] == 3
    assert summary["dropped_buffer_count"] == 0
    metadata = json.loads((tmp_path / "Block_01_audio_evidence.output_evidence.json").read_text(encoding="utf-8"))
    assert metadata["mode"] == "digital_output_evidence_wav"
    assert metadata["block_index"] == 1
