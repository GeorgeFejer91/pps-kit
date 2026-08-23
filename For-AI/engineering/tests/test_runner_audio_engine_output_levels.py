import threading

import numpy as np

from peripersonal_space_toolkit.runner import AudioEngine


class _InactiveRecorder:
    active = False


def _bare_engine() -> AudioEngine:
    engine = object.__new__(AudioEngine)
    engine.audio_volume = 0.5
    engine.tactile_volume = 0.25
    engine.runtime_output_channels = 4
    engine.audio_output_channels = (0, 1)
    engine.tactile_output_channel = 2
    engine._output_evidence = _InactiveRecorder()
    return engine


def test_audio_engine_instruction_callback_uses_output12_master_gain():
    engine = _bare_engine()
    engine._instr_data = np.array(
        [[1.0, 1.0, 0.0, 0.0], [0.5, 0.25, 0.0, 0.0]],
        dtype=np.float32,
    )
    engine._instr_pos = 0
    engine._instr_lock = threading.Lock()
    engine._instr_finished = threading.Event()
    engine.stop_flag = False

    out = np.zeros((2, 4), dtype=np.float32)
    engine._instr_callback(out, frames=2, time_info=None, status=None)

    np.testing.assert_allclose(
        out,
        np.array([[0.5, 0.5, 0.0, 0.0], [0.25, 0.125, 0.0, 0.0]], dtype=np.float32),
    )


def test_audio_engine_block_callback_uses_output12_and_output34_master_gains():
    engine = _bare_engine()
    engine._block_data = np.array([[1.0, 2.0, 4.0, 0.0]], dtype=np.float32)
    engine._block_pos = 0
    engine._block_sr = 44100
    engine._block_lock = threading.Lock()
    engine._block_finished = threading.Event()
    engine._block_event_schedule = None
    engine._audio_sample_zero_emitted = False
    engine._audio_event_callback = None
    engine.paused = False
    engine.stop_flag = False

    out = np.zeros((1, 4), dtype=np.float32)
    engine._block_callback(out, frames=1, time_info=None, status=None)

    np.testing.assert_allclose(out, np.array([[0.5, 1.0, 1.0, 1.0]], dtype=np.float32))


def test_audio_engine_response_marker_uses_output34_master_gain_and_mirror():
    engine = _bare_engine()
    engine._instr_data = None
    engine._block_data = None
    engine._click_data = np.array([[0.8], [0.4]], dtype=np.float32)
    engine._click_pos = 0
    engine._click_active = True
    engine._click_metadata = {"click_id": "C001"}
    engine._click_gain = 0.5
    engine._click_lock = threading.Lock()
    engine._click_sr = 44100
    engine._block_sr = 44100
    engine.stop_flag = False
    emitted: list[dict[str, object]] = []
    engine._audio_event_callback = emitted.append

    out = np.zeros((2, 4), dtype=np.float32)
    engine._click_callback(out, frames=2, time_info=None, status=None)

    np.testing.assert_allclose(
        out,
        np.array([[0.0, 0.0, 0.1, 0.1], [0.0, 0.0, 0.05, 0.05]], dtype=np.float32),
    )
    assert emitted[0]["event_type"] == "response_marker_start"
    assert emitted[0]["marker_gain"] == 0.125
    assert emitted[0]["marker_duplicate_channel_1based"] == 4


def test_audio_engine_background_music_uses_content_volume_and_output12_master_gain():
    engine = _bare_engine()
    engine.audio_volume = 0.2
    engine.bg_music_base_data = np.array(
        [[1.0, 0.5, 0.0, 0.0], [0.5, 0.25, 0.0, 0.0]],
        dtype=np.float32,
    )
    engine.bg_music_idx = 0
    engine.bg_music_volume = 0.5

    chunk = engine._next_background_music_chunk(3)

    np.testing.assert_allclose(
        chunk,
        np.array(
            [[0.1, 0.05, 0.0, 0.0], [0.05, 0.025, 0.0, 0.0], [0.1, 0.05, 0.0, 0.0]],
            dtype=np.float32,
        ),
    )
    assert engine.bg_music_idx == 1
