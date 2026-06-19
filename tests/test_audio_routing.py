from __future__ import annotations

import numpy as np
import pytest

from peripersonal_space_toolkit.audio_routing import (
    NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL,
    assess_audio_runtime_readiness,
    apply_output_volumes,
    center_audio_for_output,
    komplete_audio_asio_install_message,
    komplete_audio_asio_install_steps,
    output_channel_map_from_env,
    prepare_block_audio_for_output,
    preferred_runtime_output_channels,
    tactile_output_channel_for_channels,
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
    assert "Retry Audio Detection" in readiness.message()
    assert "automatically selects" in readiness.message()


def test_komplete_asio_install_message_has_actionable_steps_and_links():
    steps = komplete_audio_asio_install_steps()
    message = komplete_audio_asio_install_message()

    assert steps[0].startswith("Disconnect the Komplete Audio 6 MK2")
    assert any("setup.exe" in step for step in steps)
    assert any("Retry Audio Detection" in step for step in steps)
    assert "Driver page:" in message
    assert NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL in message


def test_audio_preflight_distinguishes_registered_driver_without_visible_interface():
    sd = FakeSoundDevice([{"name": "ASIO"}], [])

    readiness = assess_audio_runtime_readiness(sounddevice_module=sd, komplete_asio_registered=True)

    assert readiness.ready is False
    assert readiness.komplete_asio_driver_registered is True
    assert "driver is installed" in readiness.summary
    assert "installed/registered in Windows" in readiness.message()
    assert "Reconnect or power-cycle" in readiness.message()
    assert "automatically selects" in readiness.message()


def test_audio_preflight_lists_unvalidated_multichannel_outputs_with_channel_map():
    sd = FakeSoundDevice(
        [{"name": "ASIO"}, {"name": "Windows WDM-KS"}],
        [
            _device("ASIO4ALL v2", 0, 2),
            _device("Speakers (Nahimic Easy Surround)", 1, 8),
        ],
    )

    readiness = assess_audio_runtime_readiness(sounddevice_module=sd, komplete_asio_registered=True)

    assert readiness.ready is False
    assert "driver is installed" in readiness.summary
    assert "not connected or not ready" in readiness.message()
    assert readiness.unvalidated_output_devices == (
        "[1] Speakers (Nahimic Easy Surround) (Windows WDM-KS, 8 out; outputs 1-8 available; PPS uses 1=L, 2=R, 3=tactile)",
    )
    assert "Non-ASIO multichannel output is visible" in readiness.message()


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
    assert readiness.unvalidated_output_devices == (
        "[0] FlexASIO (ASIO, 4 out; outputs 1-4 available; PPS uses 1=L, 2=R, 3=tactile)",
    )


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
    assert prepared.tactile_channel == 2
    np.testing.assert_array_equal(prepared.data, np.array([[0.1, 0.2, 0.3, 0.0]], dtype=np.float32))


def test_manual_output_channel_map_routes_left_right_tactile_to_selected_outputs():
    source = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)

    prepared = prepare_block_audio_for_output(source, output_channels=6, output_channel_map=(3, 4, 5))
    instruction = center_audio_for_output(np.array([[0.5]], dtype=np.float32), 6, audio_channels=prepared.audio_channels)
    probe = tactile_probe_for_output(np.array([1.0], dtype=np.float32), 6, tactile_channel=prepared.tactile_channel)

    assert prepared.audio_channels == (3, 4)
    assert prepared.tactile_channel == 5
    np.testing.assert_array_equal(prepared.data, np.array([[0.0, 0.0, 0.0, 0.1, 0.2, 0.3]], dtype=np.float32))
    np.testing.assert_array_equal(instruction, np.array([[0.0, 0.0, 0.0, 0.5, 0.5, 0.0]], dtype=np.float32))
    np.testing.assert_array_equal(probe, np.array([[0.0, 0.0, 0.0, 0.0, 0.0, 1.0]], dtype=np.float32))


def test_manual_output_channel_map_allows_duplicate_mixed_outputs():
    source = np.array([[0.1, 0.2, 0.3]], dtype=np.float32)

    prepared = prepare_block_audio_for_output(source, output_channels=3, output_channel_map=(0, 0, 0))
    scaled = apply_output_volumes(
        prepared.data,
        audio_volume=0.5,
        tactile_volume=0.25,
        audio_channels=prepared.audio_channels,
        tactile_channel=prepared.tactile_channel,
    )

    assert prepared.audio_channels == (0, 0)
    assert prepared.tactile_channel == 0
    np.testing.assert_allclose(prepared.data, np.array([[0.6, 0.0, 0.0]], dtype=np.float32))
    np.testing.assert_allclose(scaled, np.array([[0.3, 0.0, 0.0]], dtype=np.float32))


def test_manual_output_channel_env_uses_one_based_channels_and_allows_duplicates():
    assert output_channel_map_from_env(8, value="4,4,6") == (3, 3, 5)

    with pytest.raises(ValueError, match="between 1 and 8"):
        output_channel_map_from_env(8, value="1,2,9")


def test_komplete_asio_prefers_silent_fourth_channel_padding():
    assert preferred_runtime_output_channels(6, "ASIO") == 4
    assert tactile_output_channel_for_channels(4) == 2

    instruction = center_audio_for_output(np.array([[0.5], [0.25]], dtype=np.float32), output_channels=4)
    np.testing.assert_array_equal(
        instruction,
        np.array([[0.5, 0.5, 0.0, 0.0], [0.25, 0.25, 0.0, 0.0]], dtype=np.float32),
    )

    tactile_probe = tactile_probe_for_output(np.array([1.0], dtype=np.float32), output_channels=4)
    np.testing.assert_array_equal(tactile_probe, np.array([[0.0, 0.0, 1.0, 0.0]], dtype=np.float32))


def test_output4_tactile_proxy_duplicates_scaled_tactile_channel_only_when_requested():
    routed = np.array([[0.1, 0.2, 0.4, 0.0]], dtype=np.float32)

    default = apply_output_volumes(routed, audio_volume=1.0, tactile_volume=0.5)
    mirrored = apply_output_volumes(
        routed,
        audio_volume=1.0,
        tactile_volume=0.5,
        duplicate_tactile_channel=3,
    )
    probe = tactile_probe_for_output(
        np.array([1.0], dtype=np.float32),
        output_channels=4,
        tactile_volume=0.25,
        duplicate_tactile_channel=3,
    )

    np.testing.assert_array_equal(default, np.array([[0.1, 0.2, 0.2, 0.0]], dtype=np.float32))
    np.testing.assert_array_equal(mirrored, np.array([[0.1, 0.2, 0.2, 0.2]], dtype=np.float32))
    np.testing.assert_array_equal(probe, np.array([[0.0, 0.0, 0.25, 0.25]], dtype=np.float32))


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
