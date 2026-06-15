"""Audio channel routing helpers for PPS playback.

The configurable renderer writes multichannel WAVs as:

- channel 0: binaural left ear
- channel 1: binaural right ear
- channel 2: vibrotactile cue

The locked Study 5 generator still writes legacy stereo WAVs as:

- channel 0: vibrotactile cue
- channel 1: mono/single-ear looming audio

These helpers keep the two layouts explicit and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata as metadata
import os
import re
from typing import Any

import numpy as np


LEGACY_STEREO_CHANNELS = 2
BINAURAL_TACTILE_CHANNELS = 3
BINAURAL_TACTILE_PADDED_CHANNELS = 4
SPATIAL_AUDIO_CHANNELS = (0, 1)
LEGACY_AUDIO_CHANNELS = (0,)
LEGACY_TACTILE_CHANNEL = 1
SPATIAL_TACTILE_CHANNEL = 2
MIN_SOUNDDEVICE_VERSION = "0.4.7"
NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL = "https://www.native-instruments.com/en/support/downloads/drivers-other-files/"
FLEXASIO_RELEASES_URL = "https://github.com/dechamps/FlexASIO/releases"
STEINBERG_BUILTIN_ASIO_DRIVER_URL = (
    "https://helpcenter.steinberg.de/hc/en-us/articles/"
    "17863730844946-Steinberg-built-in-ASIO-Driver-information-download"
)


@dataclass(frozen=True)
class PreparedBlockAudio:
    data: np.ndarray
    layout: str
    channels: int
    source_channels: int
    audio_channels: tuple[int, ...]
    tactile_channel: int


@dataclass(frozen=True)
class AudioRuntimeReadiness:
    """User-facing audio dependency and route diagnosis."""

    ready: bool
    publication_ready: bool
    severity: str
    summary: str
    details: tuple[str, ...]
    actions: tuple[str, ...]
    sounddevice_available: bool
    sounddevice_version: str
    asio_hostapi_present: bool
    preferred_devices: tuple[str, ...]
    fallback_devices: tuple[str, ...]

    def message(self) -> str:
        lines = [self.summary]
        if self.details:
            lines.extend(self.details)
        if self.actions:
            lines.append("Next steps: " + " ".join(self.actions))
        return "\n".join(line for line in lines if line)


def _version_parts(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value)[:4])


def _version_at_least(value: str, minimum: str) -> bool:
    actual = _version_parts(value)
    required = _version_parts(minimum)
    if not actual:
        return False
    length = max(len(actual), len(required))
    return actual + (0,) * (length - len(actual)) >= required + (0,) * (length - len(required))


def _sounddevice_version(sd_module: Any | None) -> str:
    version = str(getattr(sd_module, "__version__", "") or "")
    if version:
        return version
    try:
        return metadata.version("sounddevice")
    except metadata.PackageNotFoundError:
        return ""


def assess_audio_runtime_readiness(
    *,
    sounddevice_module: Any | None = None,
    device_query: str = "Komplete",
    min_output_channels: int = BINAURAL_TACTILE_CHANNELS,
) -> AudioRuntimeReadiness:
    """Assess whether the validated multichannel ASIO playback route is visible.

    The publication-grade route is the native Komplete Audio ASIO endpoint with
    at least three outputs so left/right/tactile samples share one hardware
    clock. Generic ASIO wrappers are reported as fallbacks, not as validation
    substitutes.
    """
    os.environ.setdefault("SD_ENABLE_ASIO", "1")
    if sounddevice_module is None:
        try:
            import sounddevice as sounddevice_module  # type: ignore[import-not-found]
        except Exception as exc:
            return AudioRuntimeReadiness(
                ready=False,
                publication_ready=False,
                severity="error",
                summary="Audio preflight: Python sounddevice is not installed or cannot load.",
                details=(f"Import error: {exc}",),
                actions=(
                    'Install the full PPS runtime package: python -m pip install -e ".[gui,web,lsl,validation]".',
                    f"Then install the official Komplete Audio ASIO driver from {NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL}.",
                ),
                sounddevice_available=False,
                sounddevice_version="",
                asio_hostapi_present=False,
                preferred_devices=(),
                fallback_devices=(),
            )

    sd = sounddevice_module
    version = _sounddevice_version(sd)
    if version and not _version_at_least(version, MIN_SOUNDDEVICE_VERSION):
        return AudioRuntimeReadiness(
            ready=False,
            publication_ready=False,
            severity="error",
            summary=f"Audio preflight: sounddevice {version} is too old for the validated ASIO route.",
            details=(f"PPS requires sounddevice >= {MIN_SOUNDDEVICE_VERSION}; older builds may not expose the ASIO-enabled PortAudio path reliably.",),
            actions=('Upgrade the PPS runtime dependencies with python -m pip install --upgrade -e ".[gui,web,lsl,validation]".',),
            sounddevice_available=True,
            sounddevice_version=version,
            asio_hostapi_present=False,
            preferred_devices=(),
            fallback_devices=(),
        )

    try:
        hostapis_raw = list(sd.query_hostapis())
        devices_raw = list(sd.query_devices())
    except Exception as exc:
        return AudioRuntimeReadiness(
            ready=False,
            publication_ready=False,
            severity="error",
            summary="Audio preflight: sounddevice loaded, but audio devices could not be queried.",
            details=(f"Device query error: {exc}",),
            actions=("Reconnect the audio interface, restart Windows if the driver was just installed, then reopen PPSExperimentRunner.exe.",),
            sounddevice_available=True,
            sounddevice_version=version,
            asio_hostapi_present=False,
            preferred_devices=(),
            fallback_devices=(),
        )

    def hostapi_name(device_info: Any) -> str:
        try:
            index = int(dict(device_info).get("hostapi", 0))
            return str(dict(hostapis_raw[index]).get("name", ""))
        except Exception:
            return ""

    query = device_query.lower().strip()
    asio_hostapi_present = any("asio" in str(dict(api).get("name", "")).lower() for api in hostapis_raw)
    preferred: list[str] = []
    asio_fallbacks: list[str] = []
    non_asio_multichannel: list[str] = []
    stereo_komplete: list[str] = []

    for index, raw in enumerate(devices_raw):
        dev = dict(raw)
        name = str(dev.get("name", ""))
        hostapi = hostapi_name(dev)
        outputs = int(dev.get("max_output_channels", 0) or 0)
        label = f"[{index}] {name} ({hostapi}, {outputs} out)"
        is_asio = "asio" in hostapi.lower()
        is_target = bool(query and query in name.lower())
        if outputs >= min_output_channels and is_asio and is_target:
            preferred.append(label)
        elif outputs >= min_output_channels and is_asio:
            asio_fallbacks.append(label)
        elif outputs >= min_output_channels:
            non_asio_multichannel.append(label)
        elif outputs >= LEGACY_STEREO_CHANNELS and is_target:
            stereo_komplete.append(label)

    if preferred:
        return AudioRuntimeReadiness(
            ready=True,
            publication_ready=True,
            severity="ok",
            summary="Audio preflight: validated Komplete multichannel ASIO output is visible.",
            details=(f"Using candidate: {preferred[0]}",),
            actions=("Run pps-audio-stress --device-query Komplete --channels 3 before participant timing validation.",),
            sounddevice_available=True,
            sounddevice_version=version,
            asio_hostapi_present=asio_hostapi_present,
            preferred_devices=tuple(preferred),
            fallback_devices=tuple(asio_fallbacks + non_asio_multichannel + stereo_komplete),
        )

    if asio_fallbacks:
        return AudioRuntimeReadiness(
            ready=True,
            publication_ready=False,
            severity="warning",
            summary="Audio preflight: a multichannel ASIO output is visible, but the validated Komplete ASIO route is not.",
            details=(f"Fallback ASIO candidate: {asio_fallbacks[0]}",),
            actions=(
                f"For the validated lab route, install/select the official Komplete Audio ASIO driver from {NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL}.",
                "Do not use generic ASIO wrappers as publication timing evidence until the physical route is revalidated.",
            ),
            sounddevice_available=True,
            sounddevice_version=version,
            asio_hostapi_present=asio_hostapi_present,
            preferred_devices=(),
            fallback_devices=tuple(asio_fallbacks + non_asio_multichannel + stereo_komplete),
        )

    details: list[str] = []
    if stereo_komplete:
        details.append(f"Only a stereo Komplete endpoint is visible: {stereo_komplete[0]}")
    elif non_asio_multichannel:
        details.append(f"Non-ASIO multichannel output is visible, but not valid for PPS timing claims: {non_asio_multichannel[0]}")
    elif not asio_hostapi_present:
        details.append("No ASIO host API is visible to sounddevice.")
    else:
        details.append("ASIO is visible, but no output exposes at least three synchronized channels.")

    return AudioRuntimeReadiness(
        ready=False,
        publication_ready=False,
        severity="error",
        summary="Audio preflight: Komplete Audio ASIO is missing or not exposing a 3+ channel output.",
        details=tuple(details),
        actions=(
            f"Install the official Native Instruments Komplete Audio 6 MK2 Windows driver from {NI_KOMPLETE_AUDIO_DRIVER_PAGE_URL}, then restart PPSExperimentRunner.exe.",
            f"FlexASIO ({FLEXASIO_RELEASES_URL}) can be cached as an optional diagnostic fallback, but it does not replace the native Komplete ASIO timing route.",
        ),
        sounddevice_available=True,
        sounddevice_version=version,
        asio_hostapi_present=asio_hostapi_present,
        preferred_devices=(),
        fallback_devices=tuple(non_asio_multichannel + stereo_komplete),
    )


def audio_runtime_preflight_message() -> str:
    """Return a concise experimenter-facing dependency message."""
    return assess_audio_runtime_readiness().message()


def ensure_2d_float32(data: np.ndarray) -> np.ndarray:
    """Return audio as C-contiguous 2D float32 samples."""
    array = np.asarray(data, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    if array.ndim != 2:
        raise ValueError(f"Expected mono or 2D audio samples, got shape {array.shape}.")
    return np.ascontiguousarray(array)


def tactile_output_channel_for_channels(channels: int) -> int:
    """Return the physical output channel index used for tactile cues."""
    return SPATIAL_TACTILE_CHANNEL if channels >= BINAURAL_TACTILE_CHANNELS else LEGACY_TACTILE_CHANNEL


def audio_output_channels_for_channels(channels: int) -> tuple[int, ...]:
    """Return physical output channel indices used for auditory playback."""
    return SPATIAL_AUDIO_CHANNELS if channels >= BINAURAL_TACTILE_CHANNELS else LEGACY_AUDIO_CHANNELS


def preferred_runtime_output_channels(max_output_channels: int) -> int:
    """Prefer a single 3-channel stream when the device supports it."""
    return BINAURAL_TACTILE_CHANNELS if max_output_channels >= BINAURAL_TACTILE_CHANNELS else LEGACY_STEREO_CHANNELS


def prepare_block_audio_for_output(data: np.ndarray, *, output_channels: int | None = None) -> PreparedBlockAudio:
    """Map a rendered/legacy block WAV into physical output-channel order.

    For 3+ channel rendered files, the first three source channels are already
    in physical order: left, right, tactile. For 2-channel legacy files, the
    original Study 5 mapping is preserved by swapping source right to output 0
    and source left to output 1.

    If ``output_channels`` is 4 or greater for rendered files, channel 3+ is
    padded with silence. This supports ASIO drivers that prefer even channel
    counts while keeping tactile on physical output channel 3.
    """
    array = ensure_2d_float32(data)
    source_channels = int(array.shape[1])
    if source_channels == 1:
        raise ValueError("Block WAVs must be legacy stereo or 3-channel binaural+tactile files.")

    if source_channels >= BINAURAL_TACTILE_CHANNELS:
        requested_channels = output_channels or BINAURAL_TACTILE_CHANNELS
        if requested_channels < BINAURAL_TACTILE_CHANNELS:
            raise ValueError("Binaural+tactile blocks require at least 3 output channels.")
        routed = np.zeros((array.shape[0], requested_channels), dtype=np.float32)
        routed[:, :BINAURAL_TACTILE_CHANNELS] = array[:, :BINAURAL_TACTILE_CHANNELS]
        return PreparedBlockAudio(
            data=np.ascontiguousarray(routed),
            layout="binaural_left_right_plus_tactile",
            channels=requested_channels,
            source_channels=source_channels,
            audio_channels=SPATIAL_AUDIO_CHANNELS,
            tactile_channel=SPATIAL_TACTILE_CHANNEL,
        )

    if output_channels is not None and output_channels != LEGACY_STEREO_CHANNELS:
        raise ValueError("Legacy stereo Study 5 blocks must be played through a 2-channel output stream.")
    routed = np.ascontiguousarray(array[:, [1, 0]])
    return PreparedBlockAudio(
        data=routed,
        layout="legacy_study5_stereo_audio_tactile",
        channels=LEGACY_STEREO_CHANNELS,
        source_channels=source_channels,
        audio_channels=LEGACY_AUDIO_CHANNELS,
        tactile_channel=LEGACY_TACTILE_CHANNEL,
    )


def apply_output_volumes(
    data: np.ndarray,
    audio_volume: float,
    tactile_volume: float,
    *,
    audio_channels: tuple[int, ...] | None = None,
    tactile_channel: int | None = None,
) -> np.ndarray:
    """Apply auditory and tactile gains to already-routed output data."""
    routed = ensure_2d_float32(data).copy()
    channels = routed.shape[1]
    audio_targets = audio_channels or audio_output_channels_for_channels(channels)
    tactile_target = tactile_output_channel_for_channels(channels) if tactile_channel is None else tactile_channel

    for channel in audio_targets:
        if 0 <= channel < channels:
            routed[:, channel] *= float(audio_volume)
    if 0 <= tactile_target < channels:
        routed[:, tactile_target] *= float(tactile_volume)
    return np.ascontiguousarray(routed)


def center_audio_for_output(data: np.ndarray, output_channels: int) -> np.ndarray:
    """Route mono/stereo instruction audio to auditory channels only."""
    array = ensure_2d_float32(data)
    if array.shape[1] == 1:
        mono = array[:, 0]
    else:
        mono = np.mean(array[:, :2], axis=1)

    routed = np.zeros((array.shape[0], output_channels), dtype=np.float32)
    if output_channels >= BINAURAL_TACTILE_CHANNELS:
        routed[:, 0] = mono
        routed[:, 1] = mono
    else:
        routed[:, 0] = mono
    return np.ascontiguousarray(routed)


def tactile_probe_for_output(data: np.ndarray, output_channels: int, tactile_volume: float = 1.0) -> np.ndarray:
    """Route a mono tactile probe to the active tactile output channel only."""
    array = ensure_2d_float32(data)
    tactile = array[:, 0]
    routed = np.zeros((array.shape[0], output_channels), dtype=np.float32)
    routed[:, tactile_output_channel_for_channels(output_channels)] = tactile * float(tactile_volume)
    return np.ascontiguousarray(routed)
