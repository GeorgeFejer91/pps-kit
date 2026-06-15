from __future__ import annotations

import numpy as np
import pytest

from peripersonal_space_toolkit.audio_routing import (
    NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL,
    assess_audio_runtime_readiness,
    apply_output_volumes,
    center_audio_for_output,
    prepare_block_audio_for_output,
    tactile_probe_for_output,
)
from peripersonal_space_toolkit.audio_device_stress import _sounddevice_latency


class FakeSoundDevice:
    __version__ = "0.4.7"

    def __init__(self, hostapis, devices):
        self._hostapis = hostapis
        self._devices = devices

    def query_hostapis(self):
        return self._hostapis

    def query_devices(self):
        return self._devices


def _device(name: str, hostapi: int, outputs: int):
    return {"name": name, "hostapi": hostapi, "max_output_channels": outputs, "max_input_channels": 0}


def test_audio_preflight_accepts_native_komplete_multichannel_asio():
    sd = FakeSoundDevice(
        [{"name": "Windows WASAPI"}, {"name": "ASIO"}],
        [_device("Komplete Audio ASIO Driver", 1, 6)],
    )

    readiness = assess_audio_runtime_readiness(sounddevice_module=sd)

    assert readiness.ready is True
    assert readiness.publication_ready is True
    assert "validated Komplete" in readiness.summary


def test_audio_preflight_flags_komplete_stereo_without_asio_route():
    sd = FakeSoundDevice(
        [{"name": "Windows WASAPI"}],
        [_device("Output 1/2 (Komplete Audio 6 MK2)", 0, 2)],
    )

    readiness = assess_audio_runtime_readiness(sounddevice_module=sd)

    assert readiness.ready is False
    assert readiness.publication_ready is False
    assert "Only a stereo Komplete endpoint" in readiness.message()
    assert NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL in readiness.message()


def test_audio_preflight_allows_generic_asio_only_as_unvalidated_fallback():
    sd = FakeSoundDevice(
        [{"name": "ASIO"}],
        [_device("FlexASIO", 0, 4)],
    )

    readiness = assess_audio_runtime_readiness(sounddevice_module=sd)

    assert readiness.ready is True
    assert readiness.publication_ready is False
    assert "fallback" in readiness.message().lower()
    assert "publication timing evidence" in readiness.message()


def test_audio_preflight_rejects_old_sounddevice_version():
    sd = FakeSoundDevice([{"name": "ASIO"}], [_device("Komplete Audio ASIO Driver", 0, 6)])
    sd.__version__ = "0.4.6"

    readiness = assess_audio_runtime_readiness(sounddevice_module=sd)

    assert readiness.ready is False
    assert "too old" in readiness.summary


def test_legacy_study5_stereo_swaps_tactile_and_audio_channels():
    source = np.array(
        [
            [1.0, 10.0],
            [2.0, 20.0],
        ],
        dtype=np.float32,
    )

    prepared = prepare_block_audio_for_output(source)

    assert prepared.layout == "legacy_study5_stereo_audio_tactile"
    assert prepared.channels == 2
    assert prepared.audio_channels == (0,)
    assert prepared.tactile_channel == 1
    np.testing.assert_array_equal(prepared.data, np.array([[10.0, 1.0], [20.0, 2.0]], dtype=np.float32))


def test_binaural_tactile_render_preserves_first_three_channels():
    source = np.array(
        [
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ],
        dtype=np.float32,
    )

    prepared = prepare_block_audio_for_output(source)

    assert prepared.layout == "binaural_left_right_plus_tactile"
    assert prepared.channels == 3
    assert prepared.audio_channels == (0, 1)
    assert prepared.tactile_channel == 2
    np.testing.assert_array_equal(prepared.data, source)


def test_binaural_tactile_render_can_pad_silent_fourth_channel():
    source = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)

    prepared = prepare_block_audio_for_output(source, output_channels=4)

    assert prepared.channels == 4
    np.testing.assert_array_equal(prepared.data, np.array([[0.1, 0.2, 0.3, 0.0]], dtype=np.float32))


def test_volume_scaling_uses_binaural_audio_pair_and_tactile_channel():
    routed = np.array([[1.0, 2.0, 3.0, 4.0]], dtype=np.float32)

    scaled = apply_output_volumes(routed, audio_volume=0.5, tactile_volume=0.25)

    np.testing.assert_array_equal(scaled, np.array([[0.5, 1.0, 0.75, 4.0]], dtype=np.float32))


def test_instruction_audio_routes_to_binaural_outputs_only():
    source = np.array([[1.0], [2.0]], dtype=np.float32)

    routed = center_audio_for_output(source, output_channels=3)

    np.testing.assert_array_equal(routed, np.array([[1.0, 1.0, 0.0], [2.0, 2.0, 0.0]], dtype=np.float32))


def test_tactile_probe_uses_legacy_or_spatial_tactile_channel():
    source = np.array([1.0, 2.0], dtype=np.float32)

    legacy = tactile_probe_for_output(source, output_channels=2)
    spatial = tactile_probe_for_output(source, output_channels=3, tactile_volume=0.5)

    np.testing.assert_array_equal(legacy, np.array([[0.0, 1.0], [0.0, 2.0]], dtype=np.float32))
    np.testing.assert_array_equal(spatial, np.array([[0.0, 0.0, 0.5], [0.0, 0.0, 1.0]], dtype=np.float32))


def test_mono_block_wavs_are_rejected():
    with pytest.raises(ValueError, match="legacy stereo or 3-channel"):
        prepare_block_audio_for_output(np.array([1.0, 2.0], dtype=np.float32))


def test_stress_tool_converts_numeric_latency_strings():
    assert _sounddevice_latency("low") == "low"
    assert _sounddevice_latency("0.003") == pytest.approx(0.003)
