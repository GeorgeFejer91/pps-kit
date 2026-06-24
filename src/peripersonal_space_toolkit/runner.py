"""
PPS Breathing Experiment Runner - With Digital Output Evidence Recording
=================================================================
- Sequential block playback (1-6) with manual override
- Legacy Study 5 routing: WAV right -> Output 1 audio, WAV left -> Output 2 tactile
- Rendered trajectory routing: Output 1/2 binaural audio, Output 3 tactile
- Low-latency mouse click tone (tactile only)
- Dedicated click area with 8-second recentering
- Global pause/resume: Ctrl+Alt+P
- optional local WAV recording of the exact multichannel output buffers
"""

if __name__ == "__main__":
    import sys as _sys

    print(
        "The legacy Tk participant runner has been retired as a public entry point.\n"
        "Use the active packaged experiment runner: "
        "`dist\\PPSExperimentRunner\\PPSExperimentRunner.exe` or `windows\\Launch_Experiment_Runner.bat`."
    )
    print("For device checks, use `pps-audio-stress --dry-run --device-query Komplete`.")
    _sys.exit(2)

import tkinter as tk
from tkinter import ttk, messagebox
import os
import sys

# Enable the ASIO-enabled PortAudio DLL from python-sounddevice when available.
# This must be set before importing sounddevice. The Komplete Audio ASIO driver
# exposes one clock-synchronized 6-output endpoint, while the Windows WDM/WASAPI
# endpoints expose only separate stereo pairs.
os.environ.setdefault("SD_ENABLE_ASIO", "1")

import sounddevice as sd
import soundfile as sf
import numpy as np
import re
import threading
import time
import json
import ctypes
import argparse
import subprocess
from pathlib import Path

from .audio_routing import (
    BINAURAL_TACTILE_CHANNELS,
    audio_output_channels_for_channels,
    audio_runtime_preflight_message,
    apply_output_volumes,
    center_audio_for_output,
    default_tactile_duplicate_channel,
    output_channel_map_from_env,
    prepare_block_audio_for_output,
    preferred_runtime_output_channels,
    tactile_output_channel_for_channels,
    tactile_probe_for_output,
)
from .session_runner import (
    DEFAULT_SESSION_ROOT,
    RESPONSE_MARKER_GAIN,
    SessionCaptureOptions,
    WIRED_LOOPBACK_OFF,
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    normalize_wired_loopback_mode,
    _block_event_schedules,
    _write_timing_qc_csv,
    find_latest_dashboard_run_setup,
    prepare_all_segment_run_packages,
    prepare_segment_run_package,
    segment_run_setup_participants,
)
from .session_analysis import analyze_session_events, format_analysis_summary, write_analysis_csvs
from .session_events import SessionEventLogger
from .output_evidence import OutputEvidenceRecorder
from .timing_events import TimingEventHub, TriggerDictionary
from .runtime_paths import repo_root

# Try to import pyaudiowpatch for legacy WASAPI diagnostics. Normal runner
# evidence recording uses the callback output tap because ASIO playback can
# bypass the Windows endpoint that WASAPI records.
try:
    import pyaudiowpatch as pyaudio_wp
    PYAUDIOWPATCH_AVAILABLE = True
    print("pyaudiowpatch imported successfully - legacy WASAPI diagnostics available")
except ImportError as e:
    print(f"WARNING: pyaudiowpatch not available: {e}")
    print("  Install with: pip install pyaudiowpatch")
    PYAUDIOWPATCH_AVAILABLE = False

# =============================================================================
# AUDIO PRIORITY AND PERFORMANCE SETTINGS
# =============================================================================
# Try to set process priority to high for better audio timing
try:
    if sys.platform == 'win32':
        # Set process priority to HIGH_PRIORITY_CLASS
        kernel32 = ctypes.windll.kernel32
        HIGH_PRIORITY_CLASS = 0x00000080
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), HIGH_PRIORITY_CLASS)
        print("Process priority set to HIGH for audio stability")
except Exception as e:
    print(f"Warning: Could not set process priority: {e}")

# Optional imports for mouse control
try:
    import pyautogui
    pyautogui.FAILSAFE = False
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    from pynput import mouse, keyboard
    PYNPUT_AVAILABLE = True
    print("pynput imported successfully")
except ImportError as e:
    print(f"WARNING: pynput import failed: {e}")
    PYNPUT_AVAILABLE = False
except Exception as e:
    print(f"WARNING: pynput import error: {e}")
    PYNPUT_AVAILABLE = False


# =============================================================================
# CONFIGURATION
# =============================================================================
REPO_ROOT = repo_root()
STIMULI_DIR = str(REPO_ROOT / "artifacts" / "stimuli" / "10.Participant_Sequences")
CLICK_SOUND = str(REPO_ROOT / "assets" / "click" / "mouse_click_tone_1200Hz_50ms.wav")

# Instruction audio files
INSTRUCTIONS_DIR = str(REPO_ROOT / "assets" / "breathing")
GENERAL_INSTRUCTIONS = os.path.join(INSTRUCTIONS_DIR, "General_Instructions.wav")
PRE_BLOCK_INSTRUCTIONS = os.path.join(INSTRUCTIONS_DIR, "Pre-Block_Instruction.wav")
POST_BLOCK_INSTRUCTIONS = os.path.join(INSTRUCTIONS_DIR, "Post-Block_Instruction.wav")

# Optional background music. Empty by default to avoid bundling third-party audio.
BACKGROUND_MUSIC = ""

# Interim and Finish messages
INTERIM_MESSAGE = os.path.join(INSTRUCTIONS_DIR, "InterimMessage.wav")
FINISH_MESSAGE = os.path.join(INSTRUCTIONS_DIR, "FinishMessage.wav")

# Tactile test stimulus (SOA 0ms)
TACTILE_TEST_STIMULUS = str(REPO_ROOT / "artifacts" / "stimuli" / "1. TactileStimuli" / "tactile_stimulus_0ms.wav")

DEFAULT_BLOCK_DURATION = 352  # Default 5:52 in seconds (used if WAV duration can't be read)
RECENTER_START = 4    # First recenter at 4 seconds
RECENTER_INTERVAL = 8 # Then every 8 seconds

# Settings file (stores volume preference)
SETTINGS_FILE = str(REPO_ROOT / "local_data" / "experiment_settings.json")

# Demographics data folder
DEMOGRAPHICS_DIR = str(REPO_ROOT / "local_data" / "demographics")

# Loopback recording output folder
RECORDINGS_DIR = str(REPO_ROOT / "local_data" / "loopback_recordings")
SESSION_ROOT = str(DEFAULT_SESSION_ROOT)
RUN_SETUP_MANIFEST = ""


def configure_runtime_paths(args):
    """Apply CLI path overrides before constructing the Tk app."""
    global STIMULI_DIR, CLICK_SOUND, INSTRUCTIONS_DIR, GENERAL_INSTRUCTIONS
    global PRE_BLOCK_INSTRUCTIONS, POST_BLOCK_INSTRUCTIONS, BACKGROUND_MUSIC
    global INTERIM_MESSAGE, FINISH_MESSAGE, TACTILE_TEST_STIMULUS
    global SETTINGS_FILE, DEMOGRAPHICS_DIR, RECORDINGS_DIR, SESSION_ROOT, RUN_SETUP_MANIFEST

    if args.stimuli_dir:
        STIMULI_DIR = str(args.stimuli_dir)
    if args.session_root:
        SESSION_ROOT = str(args.session_root)
    if args.run_setup_manifest:
        RUN_SETUP_MANIFEST = str(args.run_setup_manifest)
    elif args.latest_dashboard_setup:
        latest = find_latest_dashboard_run_setup()
        RUN_SETUP_MANIFEST = str(latest) if latest else ""
    elif not args.stimuli_dir:
        latest = find_latest_dashboard_run_setup()
        if latest:
            RUN_SETUP_MANIFEST = str(latest)
    if args.click_sound:
        CLICK_SOUND = str(args.click_sound)
    if args.instructions_dir:
        INSTRUCTIONS_DIR = str(args.instructions_dir)
        GENERAL_INSTRUCTIONS = os.path.join(INSTRUCTIONS_DIR, "General_Instructions.wav")
        PRE_BLOCK_INSTRUCTIONS = os.path.join(INSTRUCTIONS_DIR, "Pre-Block_Instruction.wav")
        POST_BLOCK_INSTRUCTIONS = os.path.join(INSTRUCTIONS_DIR, "Post-Block_Instruction.wav")
        INTERIM_MESSAGE = os.path.join(INSTRUCTIONS_DIR, "InterimMessage.wav")
        FINISH_MESSAGE = os.path.join(INSTRUCTIONS_DIR, "FinishMessage.wav")
    if args.background_music:
        BACKGROUND_MUSIC = str(args.background_music)
    if args.tactile_test_stimulus:
        TACTILE_TEST_STIMULUS = str(args.tactile_test_stimulus)
    if args.settings_file:
        SETTINGS_FILE = str(args.settings_file)
    if args.demographics_dir:
        DEMOGRAPHICS_DIR = str(args.demographics_dir)
    if args.recordings_dir:
        RECORDINGS_DIR = str(args.recordings_dir)

    Path(SETTINGS_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(DEMOGRAPHICS_DIR).mkdir(parents=True, exist_ok=True)
    Path(RECORDINGS_DIR).mkdir(parents=True, exist_ok=True)
    Path(SESSION_ROOT).mkdir(parents=True, exist_ok=True)


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Launch the Windows PPS experiment app.")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit.")
    parser.add_argument("--stimuli-dir", type=Path, help="Participant sequence directory.")
    parser.add_argument("--run-setup-manifest", type=Path, help="Prepared Segment 6 experiment_run_setup_manifest.json.")
    parser.add_argument("--latest-dashboard-setup", action="store_true", help="Use the newest prepared dashboard Segment 6 setup.")
    parser.add_argument("--session-root", type=Path, help="Directory for generated participant sessions.")
    parser.add_argument("--click-sound", type=Path, help="Click-tone WAV path.")
    parser.add_argument("--instructions-dir", type=Path, help="Directory containing generated 4-second instruction WAVs.")
    parser.add_argument("--background-music", type=Path, help="Optional background music file.")
    parser.add_argument("--tactile-test-stimulus", type=Path, help="Generated tactile SOA 0ms test WAV.")
    parser.add_argument("--settings-file", type=Path, help="Runtime settings JSON path.")
    parser.add_argument("--demographics-dir", type=Path, help="Directory for local demographics JSON.")
    parser.add_argument("--recordings-dir", type=Path, help="Directory for local loopback recordings.")
    return parser

# =============================================================================
# AUDIO PERFORMANCE CONFIGURATION
# =============================================================================
# These settings prioritize timing stability over CPU usage

# Buffer sizes (in samples) - larger = more stable, higher latency
AUDIO_BLOCKSIZE = 256       # Stable 3-channel ASIO callback size on Komplete Audio 6 MK2
AUDIO_BUFFERSIZE = 4        # Number of buffers to queue

# Latency settings for sounddevice streams
# 'low' = minimum latency, 'high' = maximum stability
# Numeric value = target latency in seconds (e.g., 0.1 = 100ms)
STREAM_LATENCY = 0.010      # 10ms request; Komplete ASIO measures ~16.5ms actual

# For blocks (long playback) - prioritize stability
BLOCK_STREAM_LATENCY = 0.010
BLOCK_BLOCKSIZE = 256

# For clicks (instant feedback) - prioritize low latency
CLICK_LATENCY = 0.010       # Lower 0.003/64 passed short tests but failed long persistent-stream tests
CLICK_BLOCKSIZE = 256       # Small enough for response feedback; stable in long callback tests

# Pre-buffer all audio to avoid I/O during playback
PREBUFFER_AUDIO = True

# =============================================================================
# WASAPI LOOPBACK RECORDING CONFIGURATION
# =============================================================================
RECORDING_BUFFER_SIZE = 2048     # Frames per recording callback
RECORDING_PRE_BUFFER_SEC = 0.5   # Start recording this many seconds before block
ENABLE_LOOPBACK_RECORDING = True # Set to False to disable recording entirely


# =============================================================================
# SETTINGS PERSISTENCE
# =============================================================================
def load_settings():
    """Load settings from file, return defaults if not found."""
    defaults = {
        "volume": 50,           # Background music volume
        "audio_volume": 100,    # Audio output volume (Output 1/2 for binaural)
        "tactile_volume": 100,  # Tactile output volume (Output 3 for spatial files)
        "enable_lsl": True,
        "write_internal_xdf": True,
        "write_analysis_csvs": True,
        "start_backup_recording": True,
    }
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                # Merge with defaults to handle missing keys
                return {**defaults, **settings}
    except Exception as e:
        print(f"Warning: Could not load settings: {e}")
    return defaults


def save_settings(settings):
    """Save settings to file."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save settings: {e}")


def save_demographics(participant_id, demographics):
    """Save demographics data to JSON file in demographics folder."""
    try:
        # Create demographics folder if it doesn't exist
        os.makedirs(DEMOGRAPHICS_DIR, exist_ok=True)

        # Add metadata
        from datetime import datetime
        demographics["participant_id"] = participant_id
        demographics["experiment_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Save to file named by participant ID
        filepath = os.path.join(DEMOGRAPHICS_DIR, f"{participant_id}_demographics.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(demographics, f, indent=2, ensure_ascii=False)
        print(f"Demographics saved: {filepath}")
        return True
    except Exception as e:
        print(f"Error saving demographics: {e}")
        return False


def load_demographics(participant_id):
    """Load demographics data for a participant if it exists."""
    try:
        filepath = os.path.join(DEMOGRAPHICS_DIR, f"{participant_id}_demographics.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load demographics: {e}")
    return None


# =============================================================================
# AUDIO DEVICE DETECTION
# =============================================================================
def _hostapi_name_for_device(device_info):
    try:
        return sd.query_hostapis()[int(device_info["hostapi"])]["name"]
    except Exception:
        return ""


def output_extra_settings_for_device(device_idx, channels):
    """Return host-API-specific output settings for a stream, if needed."""
    if device_idx is None:
        return None
    try:
        device_info = sd.query_devices(device_idx)
        if _hostapi_name_for_device(device_info).lower() == "asio" and hasattr(sd, "AsioSettings"):
            return sd.AsioSettings(channel_selectors=list(range(int(channels))))
    except Exception as exc:
        print(f"Warning: Could not prepare host-specific audio settings: {exc}")
    return None


def input_extra_settings_for_device(device_idx, channels):
    """Return host-API-specific input settings for a stream, if needed."""
    if device_idx is None:
        return None
    try:
        device_info = sd.query_devices(device_idx)
        if _hostapi_name_for_device(device_info).lower() == "asio" and hasattr(sd, "AsioSettings"):
            return sd.AsioSettings(channel_selectors=list(range(int(channels))))
    except Exception as exc:
        print(f"Warning: Could not prepare host-specific input settings: {exc}")
    return None


def find_output_device():
    """Find the best output device.

    Preference order:
    0. PPS_AUDIO_DEVICE_INDEX override for validation/lab diagnostics.
    1. Komplete Audio ASIO endpoint with >=3 outputs for binaural+tactile.
    2. Any ASIO endpoint with >=3 outputs.
    3. Any non-ASIO endpoint with >=3 outputs.
    4. Legacy Komplete Output 1/2 stereo endpoint.
    5. System default output device.
    """
    devices = sd.query_devices()

    override = os.environ.get("PPS_AUDIO_DEVICE_INDEX", "").strip()
    if override:
        try:
            override_idx = int(override)
            dev = sd.query_devices(override_idx)
            hostapi = _hostapi_name_for_device(dev)
            if int(dev.get("max_output_channels", 0)) >= BINAURAL_TACTILE_CHANNELS:
                print(
                    "Audio device override: "
                    f"[{override_idx}] {dev.get('name', '')} ({hostapi}, {dev.get('max_output_channels', 0)} out)"
                )
                return override_idx, dev["name"], "komplete" in str(dev.get("name", "")).lower()
            print(
                "Warning: PPS_AUDIO_DEVICE_INDEX does not expose enough outputs: "
                f"[{override_idx}] {dev.get('name', '')} ({hostapi}, {dev.get('max_output_channels', 0)} out)"
            )
        except Exception as exc:
            print(f"Warning: Ignoring invalid PPS_AUDIO_DEVICE_INDEX={override!r}: {exc}")

    def output_candidates(min_channels):
        rows = []
        for i, dev in enumerate(devices):
            if dev["max_output_channels"] >= min_channels:
                rows.append((i, dev, _hostapi_name_for_device(dev)))
        return rows

    for i, dev, hostapi in output_candidates(BINAURAL_TACTILE_CHANNELS):
        name = dev["name"].lower()
        if "komplete" in name and hostapi.lower() == "asio":
            return i, dev["name"], True

    for i, dev, hostapi in output_candidates(BINAURAL_TACTILE_CHANNELS):
        if hostapi.lower() == "asio":
            return i, dev["name"], "komplete" in dev["name"].lower()

    for i, dev, _hostapi in output_candidates(BINAURAL_TACTILE_CHANNELS):
        name = dev["name"].lower()
        if "komplete" in name:
            return i, dev["name"], True

    for i, dev, _hostapi in output_candidates(BINAURAL_TACTILE_CHANNELS):
        return i, dev["name"], "komplete" in dev["name"].lower()

    # Legacy Study 5 fallback: Komplete stereo pair.
    for i, dev in enumerate(devices):
        name = dev['name'].lower()
        if 'output 1/2' in name and 'komplete' in name and dev['max_output_channels'] >= 2:
            return i, dev['name'], True  # True = Komplete found

    # Fall back to system default output device
    try:
        default_idx = sd.default.device[1]  # [1] is output device
        if default_idx is not None and default_idx >= 0:
            default_dev = sd.query_devices(default_idx)
            return default_idx, default_dev['name'], False  # False = using fallback
    except Exception as e:
        print(f"Warning: Could not get default device: {e}")

    return None, None, False


# =============================================================================
# AUDIO ENGINE - OPTIMIZED FOR TIMING STABILITY
# =============================================================================
class _PersistentPlaybackHandle:
    """Small stop/close handle for playback mixed into the persistent output stream."""

    def __init__(self, stop_callback):
        self._stop_callback = stop_callback

    def stop(self):
        self._stop_callback()

    def close(self):
        pass


class AudioEngine:
    """Handles block playback and low-latency click feedback.

    Optimized for timing stability:
    - Callback-based streaming for consistent timing
    - Pre-buffered audio data
    - Configurable latency/buffer settings
    - Thread-safe state management
    """

    def __init__(self, device_idx):
        self.device_idx = device_idx
        self.device_info = sd.query_devices(device_idx) if device_idx is not None else {}
        self.device_hostapi = _hostapi_name_for_device(self.device_info) if self.device_info else ""
        self.max_output_channels = int(self.device_info.get("max_output_channels", 0)) if self.device_info else 0
        self.max_input_channels = int(self.device_info.get("max_input_channels", 0)) if self.device_info else 0
        try:
            self.output_channel_map = output_channel_map_from_env(self.max_output_channels)
        except ValueError as exc:
            print(f"Warning: Ignoring invalid PPS_AUDIO_OUTPUT_CHANNELS: {exc}")
            self.output_channel_map = None
        if self.output_channel_map is not None:
            self.runtime_output_channels = max(BINAURAL_TACTILE_CHANNELS, max(self.output_channel_map) + 1)
            self.audio_output_channels = self.output_channel_map[:2]
            self.tactile_output_channel = self.output_channel_map[2]
        else:
            self.runtime_output_channels = preferred_runtime_output_channels(self.max_output_channels, self.device_hostapi)
            self.audio_output_channels = audio_output_channels_for_channels(self.runtime_output_channels)
            self.tactile_output_channel = tactile_output_channel_for_channels(self.runtime_output_channels)
        self.stop_flag = False
        self.paused = False
        self.pause_lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Not paused initially

        # Volume controls (0.0 to 1.0)
        self.audio_volume = 1.0      # Output 1/2 for binaural; Output 1 for legacy
        self.tactile_volume = 1.0    # Output 3 for binaural+tactile; Output 2 for legacy

        # Click sound state
        self._click_data = None
        self._click_sr = 44100
        self._click_stream = None
        self._click_pos = 0
        self._click_active = False
        self._click_metadata = {}
        self._click_gain = None
        self._click_lock = threading.Lock()

        # Block playback state (callback-based)
        self._block_data = None
        self._block_sr = 44100
        self._block_stream = None
        self._block_pos = 0
        self._block_lock = threading.Lock()
        self._block_finished = threading.Event()
        self._block_progress_callback = None
        self._audio_event_callback = None
        self._audio_sample_zero_emitted = False
        self._block_event_schedule = None

        # Instruction playback state (callback-based)
        self._instr_data = None
        self._instr_sr = 44100
        self._instr_stream = None
        self._instr_pos = 0
        self._instr_lock = threading.Lock()
        self._instr_finished = threading.Event()
        self._instr_on_complete = None

        # Pre-loaded instruction audio cache
        self._audio_cache = {}

        # Current playback state
        self.elapsed_time = 0.0

        # Digital output evidence recording state. This captures the exact
        # multichannel output buffers sent by the callback, including low-gain
        # tactile-channel response markers.
        self._output_evidence = OutputEvidenceRecorder()
        self._output_evidence_summary = {}

        # Optional physical analog proxy recording. When enabled, output 4 is a
        # duplicate tactile drive and input 4 is captured as a wired loopback.
        self.wired_loopback_mode = WIRED_LOOPBACK_OFF
        self._wired_loopback = OutputEvidenceRecorder()
        self._wired_loopback_stream = None
        self._wired_loopback_summary = {}
        self._wired_loopback_output_path = None
        self._wired_loopback_start_time = None
        self._wired_loopback_last_error = ""
        self._click_stream_is_duplex = False

        # Legacy WASAPI diagnostic state. Kept for operator diagnostics only;
        # not used as the core ASIO multichannel recording path.
        self._recording_pyaudio = None     # PyAudio instance for recording
        self._recording_stream = None       # Recording stream
        self._recording_data = []           # Recorded audio chunks
        self._recording_lock = threading.Lock()
        self._recording_active = False
        self._recording_sr = 44100          # Recording sample rate
        self._recording_channels = 2        # Recording channels
        self._loopback_device_info = None   # Cached loopback device
        self._recording_output_path = None  # Intended save path for current recording
        self._recording_start_time = None   # Time when recording started

        print(
            "AudioEngine initialized: "
            f"device=[{self.device_idx}] {self.device_info.get('name', 'default')} "
            f"hostapi={self.device_hostapi or 'unknown'} max_out={self.max_output_channels} "
            f"runtime_channels={self.runtime_output_channels} tactile_out={self.tactile_output_channel + 1} "
            f"audio_out={tuple(channel + 1 for channel in self.audio_output_channels)} "
            f"latency block={BLOCK_STREAM_LATENCY}s click={CLICK_LATENCY}"
        )

        # Initialize WASAPI diagnostics if available. The user-facing backup
        # recording path is the digital output evidence tap.
        if PYAUDIOWPATCH_AVAILABLE and ENABLE_LOOPBACK_RECORDING:
            self._init_wasapi_loopback()

    def _make_output_stream(self, *, samplerate, channels, latency, blocksize, callback):
        """Create an output stream with host-specific channel selection when available."""
        return sd.OutputStream(
            samplerate=samplerate,
            channels=channels,
            dtype='float32',
            device=self.device_idx,
            latency=latency,
            blocksize=blocksize,
            extra_settings=output_extra_settings_for_device(self.device_idx, channels),
            callback=callback,
        )

    def _wired_loopback_duplex_available(self) -> bool:
        return (
            self.wired_loopback_mode == WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY
            and self.runtime_output_channels >= 4
            and self.max_input_channels >= 4
            and self.device_hostapi.lower() == "asio"
        )

    def _make_duplex_click_stream(self, *, samplerate, output_channels, latency, blocksize):
        """Create one ASIO stream that owns output playback and input-4 capture."""

        input_channels = 4

        def _duplex_callback(indata, outdata, frames, time_info, status):
            if getattr(self, "_wired_loopback", None) is not None and self._wired_loopback.active:
                self._wired_loopback.write_buffer(indata, sample_rate=samplerate)
            self._click_callback(outdata, frames, time_info, status)

        return sd.Stream(
            samplerate=samplerate,
            device=(self.device_idx, self.device_idx),
            channels=(input_channels, output_channels),
            dtype="float32",
            latency=(BLOCK_STREAM_LATENCY, latency),
            blocksize=blocksize,
            extra_settings=(
                input_extra_settings_for_device(self.device_idx, input_channels),
                output_extra_settings_for_device(self.device_idx, output_channels),
            ),
            callback=_duplex_callback,
        )

    def set_wired_loopback_mode(self, mode):
        """Configure optional input-4 recording of the output-4 tactile proxy."""
        normalized = normalize_wired_loopback_mode(mode)
        self.wired_loopback_mode = normalized
        if (
            normalized == WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY
            and self.runtime_output_channels < 4
            and self.max_output_channels >= 4
        ):
            self.runtime_output_channels = 4
            if self.output_channel_map is None:
                self.audio_output_channels = audio_output_channels_for_channels(self.runtime_output_channels)
                self.tactile_output_channel = tactile_output_channel_for_channels(self.runtime_output_channels)
        if normalized == WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY and self.runtime_output_channels < 4:
            print(
                "Warning: Wired loopback requested but the selected output route has fewer than "
                "4 output channels; output 4 tactile proxy is unavailable."
            )

    def _duplicate_tactile_channel(self):
        return default_tactile_duplicate_channel(
            self.runtime_output_channels,
            tactile_channel=self.tactile_output_channel,
            audio_channels=self.audio_output_channels,
        )

    def _persistent_output_available(self, *, samplerate, channels) -> bool:
        return (
            self._click_stream is not None
            and self._click_stream.active
            and int(samplerate) == int(self._click_sr)
            and int(channels) == int(self.runtime_output_channels)
        )

    def persistent_output_ready(self) -> bool:
        """Return whether the shared click/block/instruction output stream is live."""
        return self._click_stream is not None and bool(getattr(self._click_stream, "active", False))

    def _close_persistent_output(self):
        if self._click_stream is not None:
            try:
                self._click_stream.stop()
                self._click_stream.close()
            except Exception:
                pass
            self._click_stream = None
            self._click_stream_is_duplex = False

    def _restart_persistent_output(self):
        if self._click_data is not None and self._click_stream is None:
            self._init_click_stream()

    def _promote_runtime_to_four_channels(self) -> bool:
        """Use a tactile-mirror fourth channel when a driver rejects 3-channel ASIO streams."""
        if self.runtime_output_channels == 3 and self.max_output_channels >= 4:
            self.runtime_output_channels = 4
            if self.output_channel_map is None:
                self.audio_output_channels = audio_output_channels_for_channels(self.runtime_output_channels)
                self.tactile_output_channel = tactile_output_channel_for_channels(self.runtime_output_channels)
            print("Audio routing: 3-channel stream failed; retrying with 4 channels (Output 4 tactile mirror).")
            return True
        return False
        
    def preload_audio(self, paths):
        """Pre-load audio files into cache for instant playback.

        This eliminates I/O latency during playback.
        """
        for path in paths:
            if not os.path.exists(path):
                print(f"Warning: Audio file not found for preload: {path}")
                continue
            try:
                data, sr = sf.read(path, dtype='float32')
                # Ensure C-contiguous memory layout
                data = np.ascontiguousarray(data)
                self._audio_cache[path] = (data, sr)
                print(f"Pre-loaded: {os.path.basename(path)} ({len(data)/sr:.1f}s)")
            except Exception as e:
                print(f"Warning: Failed to preload {path}: {e}")
        print(f"Audio cache: {len(self._audio_cache)} files pre-loaded")

    # =========================================================================
    # WASAPI LOOPBACK RECORDING
    # =========================================================================
    def _init_wasapi_loopback(self):
        """Initialize WASAPI loopback device for Komplete Audio 6 Output 1/2.

        Hardcoded to always use Komplete Audio 6 MK2 Output 1/2 as the recording source,
        regardless of Windows default audio device settings.
        """
        if self.device_hostapi.lower() == "asio":
            print(
                "NOTE: WASAPI loopback records the Windows Output 1/2 endpoint and may not capture "
                "an ASIO multichannel stream. Use hardware loopback for full binaural+tactile QC."
            )

        if not PYAUDIOWPATCH_AVAILABLE:
            print("WASAPI loopback not available (pyaudiowpatch not installed)")
            return False

        try:
            self._recording_pyaudio = pyaudio_wp.PyAudio()

            # Find loopback device for Komplete Audio 6 Output 1/2 specifically
            loopback_device = None
            for loopback in self._recording_pyaudio.get_loopback_device_info_generator():
                name_lower = loopback["name"].lower()
                # Match "Output 1/2 (Komplete Audio 6 MK2)" loopback device
                if "output 1/2" in name_lower and "komplete" in name_lower:
                    loopback_device = loopback
                    print(f"Found Komplete Audio 6 loopback: {loopback['name']}")
                    break

            if loopback_device is None:
                print("ERROR: No WASAPI loopback device found for Komplete Audio 6 Output 1/2")
                print("Available loopback devices:")
                for loopback in self._recording_pyaudio.get_loopback_device_info_generator():
                    print(f"  - {loopback['name']}")
                return False

            self._loopback_device_info = loopback_device
            self._recording_sr = int(loopback_device["defaultSampleRate"])
            self._recording_channels = loopback_device["maxInputChannels"]

            print(f"WASAPI loopback device found: {loopback_device['name']}")
            print(f"  Sample rate: {self._recording_sr} Hz, Channels: {self._recording_channels}")
            return True

        except Exception as e:
            print(f"ERROR initializing WASAPI loopback: {e}")
            import traceback
            traceback.print_exc()
            return False

    def start_recording(self, output_path=None):
        """Start local digital output evidence recording.

        Args:
            output_path: WAV path for the exact mixed output-buffer copy.
        """
        if output_path is None:
            print("ERROR: Digital output evidence recording requires an output path")
            return False
        metadata = {
            "device_index": self.device_idx,
            "device_name": str(self.device_info.get("name", "")),
            "hostapi": self.device_hostapi,
            "runtime_output_channels": self.runtime_output_channels,
            "tactile_output_channel_1based": self.tactile_output_channel + 1,
            "wired_loopback_mode": self.wired_loopback_mode,
            "duplicate_tactile_output_channel_1based": (
                self._duplicate_tactile_channel() + 1 if self._duplicate_tactile_channel() is not None else ""
            ),
            "audio_volume": float(self.audio_volume),
            "tactile_volume": float(self.tactile_volume),
            "sample_rate_hz": int(self._block_sr or self._click_sr or 44100),
        }
        try:
            started = self._output_evidence.start(output_path, metadata=metadata)
            self._recording_active = bool(started)
            self._recording_output_path = output_path
            self._recording_start_time = time.time()
            print(f"Digital output evidence recording started: {output_path}")
            return bool(started)
        except Exception as e:
            print(f"ERROR starting digital output evidence recording: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_recording(self, output_path=None, interrupted=False):
        """Stop local digital output evidence recording and save it to WAV."""
        if not self._output_evidence.active:
            print("Recording not active")
            return None
        try:
            summary = self._output_evidence.stop(interrupted=interrupted)
            self._output_evidence_summary = dict(summary)
            self._recording_active = False
            self._recording_output_path = None
            self._recording_start_time = None
            print(
                "Digital output evidence saved: "
                f"{summary.get('path')} ({summary.get('duration_s', 0):.1f}s, "
                f"dropped_buffers={summary.get('dropped_buffer_count')})"
            )
            path = str(summary.get("path") or output_path or "")
            if path:
                try:
                    data, _sample_rate = sf.read(path, dtype="float32", always_2d=True)
                    return data
                except Exception:
                    return None
            return None
        except Exception as e:
            print(f"ERROR stopping digital output evidence recording: {e}")
            import traceback
            traceback.print_exc()
            return None

    def start_wired_loopback_recording(self, output_path=None, mode=None, sample_rate=None):
        """Start physical input recording for output-4 tactile proxy loopback."""
        self._wired_loopback_last_error = ""
        if mode is not None:
            self.set_wired_loopback_mode(mode)
        if self.wired_loopback_mode != WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY:
            return False
        if output_path is None:
            print("ERROR: Wired loopback recording requires an output path")
            return False
        if self.runtime_output_channels < 4:
            print("ERROR: Wired loopback requires a 4+ channel output route with output 4 available")
            return False
        if self.max_input_channels < 4:
            print("ERROR: Wired loopback requires input 4 on the selected audio interface")
            return False
        sample_rate = int(sample_rate or self._block_sr or self._click_sr or 44100)
        input_channels = 4
        metadata = {
            "schema": "pps-wired-loopback-evidence.v1",
            "mode": "wired_loopback_output4_tactile_proxy",
            "device_index": self.device_idx,
            "device_name": str(self.device_info.get("name", "")),
            "hostapi": self.device_hostapi,
            "runtime_output_channels": self.runtime_output_channels,
            "source_output_channel_1based": 4,
            "input_channel_1based": 4,
            "tactile_output_channel_1based": self.tactile_output_channel + 1,
            "sample_rate_hz": sample_rate,
            "scope": "analog_duplicate_tactile_proxy_not_woojer_mechanical_onset",
            "wiring": "Komplete Output 4 patched to Komplete Input 4",
        }

        def _start_recorder() -> bool:
            started = self._wired_loopback.start(output_path, metadata=metadata)
            if started:
                self._wired_loopback_output_path = output_path
                self._wired_loopback_start_time = time.time()
            return bool(started)

        if self._click_data is not None:
            try:
                if self.persistent_output_ready() and not self._click_stream_is_duplex:
                    self._close_persistent_output()
                started = _start_recorder()
                if not started:
                    self._wired_loopback_last_error = "wired_loopback_recorder_start_failed"
                    self._restart_persistent_output()
                    return False
                if not self.persistent_output_ready():
                    self._init_click_stream()
                if self.persistent_output_ready() and self._click_stream_is_duplex:
                    print(f"Wired output-4 loopback recording started on duplex stream: {output_path}")
                    return True
                self._wired_loopback_last_error = "persistent_output_stream_not_duplex_for_wired_loopback"
                self._wired_loopback.stop(interrupted=True)
                self._wired_loopback_output_path = None
                self._wired_loopback_start_time = None
                if not self.persistent_output_ready():
                    self._restart_persistent_output()
                return False
            except Exception as e:
                self._wired_loopback_last_error = str(e)
                print(f"ERROR starting duplex wired loopback recording: {e}")
                try:
                    if self._wired_loopback.active:
                        self._wired_loopback.stop(interrupted=True)
                except Exception:
                    pass
                self._wired_loopback_output_path = None
                self._wired_loopback_start_time = None
                if not self.persistent_output_ready():
                    self._restart_persistent_output()
                import traceback
                traceback.print_exc()
                return False

        def _input_callback(indata, frames, time_info, status):
            if status:
                print(f"Wired loopback input stream status: {status}")
            self._wired_loopback.write_buffer(indata, sample_rate=sample_rate)

        try:
            started = _start_recorder()
            self._wired_loopback_stream = sd.InputStream(
                samplerate=sample_rate,
                channels=input_channels,
                dtype="float32",
                device=self.device_idx,
                latency=BLOCK_STREAM_LATENCY,
                blocksize=RECORDING_BUFFER_SIZE,
                extra_settings=input_extra_settings_for_device(self.device_idx, input_channels),
                callback=_input_callback,
            )
            self._wired_loopback_stream.start()
            print(f"Wired output-4 loopback recording started: {output_path}")
            return bool(started)
        except Exception as e:
            self._wired_loopback_last_error = str(e)
            print(f"ERROR starting wired loopback recording: {e}")
            try:
                if self._wired_loopback_stream is not None:
                    self._wired_loopback_stream.close()
            except Exception:
                pass
            self._wired_loopback_stream = None
            self._wired_loopback.stop(interrupted=True)
            import traceback
            traceback.print_exc()
            return False

    def stop_wired_loopback_recording(self, output_path=None, interrupted=False):
        """Stop physical input recording for output-4 tactile proxy loopback."""
        if self._wired_loopback_stream is not None:
            try:
                self._wired_loopback_stream.stop()
                self._wired_loopback_stream.close()
            except Exception:
                pass
            self._wired_loopback_stream = None
        if not self._wired_loopback.active:
            print("Wired loopback recording not active")
            return None
        try:
            summary = self._wired_loopback.stop(interrupted=interrupted)
            self._wired_loopback_summary = dict(summary)
            self._wired_loopback_output_path = None
            self._wired_loopback_start_time = None
            print(
                "Wired output-4 loopback evidence saved: "
                f"{summary.get('path')} ({summary.get('duration_s', 0):.1f}s, "
                f"dropped_buffers={summary.get('dropped_buffer_count')})"
            )
            return summary
        except Exception as e:
            print(f"ERROR stopping wired loopback recording: {e}")
            import traceback
            traceback.print_exc()
            return None

    def is_recording(self):
        """Check if recording is currently active."""
        return bool(self._output_evidence.active or self._recording_active or self._wired_loopback.active)

    def get_recording_duration(self):
        """Get current recording duration in seconds."""
        if self._output_evidence.active:
            return self._output_evidence.elapsed_s
        if self._wired_loopback.active:
            return self._wired_loopback.elapsed_s
        if self._recording_start_time is None:
            return 0.0
        return time.time() - self._recording_start_time

    def load_click_sound(self, path):
        """Preload click sound for instant playback."""
        if not os.path.exists(path):
            print(f"ERROR: Click sound not found: {path}")
            return False
        try:
            data, sr = sf.read(path, dtype='float32')
            # Ensure stereo (even if mono source)
            if data.ndim == 1:
                data = data.reshape(-1, 1)
            # Ensure C-contiguous
            data = np.ascontiguousarray(data)
            self._click_data = data
            self._click_sr = sr
            return bool(self._init_click_stream())
        except Exception as e:
            print(f"ERROR: Failed to load click sound: {e}")
            return False

    def _stream_time_value(self, time_info, name: str):
        if time_info is None:
            return None
        if hasattr(time_info, name):
            try:
                return float(getattr(time_info, name))
            except (TypeError, ValueError):
                return None
        try:
            return float(time_info.get(name))
        except Exception:
            return None

    def _record_output_evidence_buffer(self, outdata, *, sample_rate=None):
        """Copy the final callback output buffer into the local evidence recorder."""
        if not getattr(self, "_output_evidence", None) or not self._output_evidence.active:
            return
        self._output_evidence.write_buffer(outdata, sample_rate=sample_rate or self._block_sr or self._click_sr)

    def _emit_audio_event(self, event_type, time_info=None, **payload):
        callback = self._audio_event_callback
        if callback is None:
            return
        payload.setdefault("event_type", event_type)
        payload.setdefault("callback_perf_counter", time.perf_counter())
        payload.setdefault("callback_unix_time", time.time())
        payload.setdefault("stream_output_buffer_dac_time", self._stream_time_value(time_info, "outputBufferDacTime"))
        payload.setdefault("stream_current_time", self._stream_time_value(time_info, "currentTime"))
        payload.setdefault("stream_input_buffer_adc_time", self._stream_time_value(time_info, "inputBufferAdcTime"))
        try:
            callback(payload)
        except Exception as exc:
            print(f"Audio event callback failed for {event_type}: {exc}")

    def _emit_audio_sample_zero_once(self, time_info=None):
        if self._audio_sample_zero_emitted:
            return
        self._audio_sample_zero_emitted = True
        self._emit_audio_event(
            "audio_sample_zero",
            time_info,
            sample_index=0,
            buffer_start_sample=0,
            sample_offset_in_buffer=0,
            sample_rate=self._block_sr,
            output_channels=self.runtime_output_channels,
            tactile_output_channel=self.tactile_output_channel,
        )

    def _emit_scheduled_block_events(self, buffer_start_sample, frames, time_info=None):
        schedule = self._block_event_schedule
        if schedule is None:
            return False
        emitted = False
        for scheduled_event in schedule.consume_buffer(buffer_start_sample, frames):
            sample_offset = max(0, int(scheduled_event.sample_index) - int(buffer_start_sample))
            payload = dict(scheduled_event.payload)
            payload.update(
                sample_index=int(scheduled_event.sample_index),
                buffer_start_sample=int(buffer_start_sample),
                sample_offset_in_buffer=int(sample_offset),
                sample_rate=self._block_sr,
                trigger_key=scheduled_event.trigger_key,
                output_channels=self.runtime_output_channels,
                tactile_output_channel=self.tactile_output_channel,
            )
            self._emit_audio_event(scheduled_event.event_type, time_info, **payload)
            if scheduled_event.event_type == "audio_sample_zero":
                self._audio_sample_zero_emitted = True
            emitted = True
        return emitted

    def _click_callback(self, outdata, frames, time_info, status):
        """Persistent output callback: background/instructions/blocks plus tactile click overlay."""
        if status:
            print(f"Click stream status: {status}")
        outdata.fill(0)
        block_buffer_start_sample = None

        if hasattr(self, "bg_music_data") and not getattr(self, "bg_music_stop", True):
            try:
                remaining = len(self.bg_music_data) - self.bg_music_idx
                if remaining >= frames:
                    outdata[:] += self.bg_music_data[self.bg_music_idx:self.bg_music_idx + frames]
                    self.bg_music_idx += frames
                else:
                    outdata[:remaining] += self.bg_music_data[self.bg_music_idx:]
                    outdata[remaining:] += self.bg_music_data[:frames - remaining]
                    self.bg_music_idx = frames - remaining
            except Exception as exc:
                print(f"Background mix error: {exc}")
                self.bg_music_stop = True

        if self._instr_data is not None and not self.stop_flag:
            with self._instr_lock:
                remaining = len(self._instr_data) - self._instr_pos
                if remaining <= 0:
                    self._instr_finished.set()
                else:
                    n = min(frames, remaining)
                    outdata[:n] += apply_output_volumes(
                        self._instr_data[self._instr_pos:self._instr_pos + n],
                        self.audio_volume,
                        0.0,
                        audio_channels=self.audio_output_channels,
                        tactile_channel=self.tactile_output_channel,
                        duplicate_tactile_channel=self._duplicate_tactile_channel(),
                    )
                    self._instr_pos += n
                    if self._instr_pos >= len(self._instr_data):
                        self._instr_finished.set()

        if self._block_data is not None and not self.stop_flag:
            if self.paused:
                pass
            else:
                with self._block_lock:
                    remaining = len(self._block_data) - self._block_pos
                    if remaining <= 0:
                        self._block_finished.set()
                    else:
                        n = min(frames, remaining)
                        block_buffer_start_sample = self._block_pos
                        if n > 0 and self._block_event_schedule is not None:
                            event_frames = n + 1 if self._block_pos + n >= len(self._block_data) else n
                            self._emit_scheduled_block_events(block_buffer_start_sample, event_frames, time_info)
                        elif n > 0 and self._block_pos == 0:
                            self._emit_audio_sample_zero_once(time_info)
                        outdata[:n] += apply_output_volumes(
                            self._block_data[self._block_pos:self._block_pos + n],
                            self.audio_volume,
                            self.tactile_volume,
                            audio_channels=self.audio_output_channels,
                            tactile_channel=self.tactile_output_channel,
                            duplicate_tactile_channel=self._duplicate_tactile_channel(),
                        )
                        self._block_pos += n
                        self.elapsed_time = self._block_pos / self._block_sr
                        if self._block_pos >= len(self._block_data):
                            self._block_finished.set()

        if not self._click_active or self._click_data is None:
            np.clip(outdata, -1.0, 1.0, out=outdata)
            self._record_output_evidence_buffer(outdata, sample_rate=self._block_sr if self._block_data is not None else self._click_sr)
            return

        with self._click_lock:
            remaining = len(self._click_data) - self._click_pos
            n = min(frames, remaining)
            if n > 0:
                click_samples = self._click_data[self._click_pos:self._click_pos + n, 0]
                tactile_channel = min(self.tactile_output_channel, outdata.shape[1] - 1)
                duplicate_tactile_channel = self._duplicate_tactile_channel()
                if duplicate_tactile_channel is not None and duplicate_tactile_channel >= outdata.shape[1]:
                    duplicate_tactile_channel = None
                effective_click_gain = (self._click_gain if self._click_gain is not None else 1.0) * self.tactile_volume
                if self._click_pos == 0:
                    metadata = dict(self._click_metadata or {})
                    marker_sample_rate = self._block_sr if block_buffer_start_sample is not None else self._click_sr
                    self._emit_audio_event(
                        "response_marker_start",
                        time_info,
                        sample_index=block_buffer_start_sample if block_buffer_start_sample is not None else "",
                        buffer_start_sample=block_buffer_start_sample if block_buffer_start_sample is not None else "",
                        sample_offset_in_buffer=0,
                        sample_rate=marker_sample_rate,
                        marker_channel=tactile_channel,
                        marker_duplicate_channel=duplicate_tactile_channel if duplicate_tactile_channel is not None else "",
                        marker_duplicate_channel_1based=(duplicate_tactile_channel + 1) if duplicate_tactile_channel is not None else "",
                        marker_gain=effective_click_gain,
                        **metadata,
                    )
                outdata[:n, tactile_channel] = click_samples * effective_click_gain
                if duplicate_tactile_channel is not None and duplicate_tactile_channel != tactile_channel:
                    outdata[:n, duplicate_tactile_channel] = outdata[:n, tactile_channel]
                self._click_pos += n
            if self._click_pos >= len(self._click_data):
                self._click_active = False
                self._click_pos = 0
                self._click_metadata = {}
                self._click_gain = None
        np.clip(outdata, -1.0, 1.0, out=outdata)
        self._record_output_evidence_buffer(outdata, sample_rate=self._block_sr if self._block_data is not None else self._click_sr)

    def _init_click_stream(self):
        """Initialize persistent low-latency click stream with optimized settings."""
        if self._click_data is None:
            print("DEBUG: _init_click_stream - no click data loaded")
            return False
        try:
            print(f"DEBUG: Initializing click stream on device {self.device_idx}, sr={self._click_sr}, latency={CLICK_LATENCY}")
            self._click_stream_is_duplex = False
            try:
                if self._wired_loopback_duplex_available():
                    self._click_stream = self._make_duplex_click_stream(
                        samplerate=self._click_sr,
                        output_channels=self.runtime_output_channels,
                        latency=CLICK_LATENCY,
                        blocksize=CLICK_BLOCKSIZE,
                    )
                    self._click_stream_is_duplex = True
                else:
                    self._click_stream = self._make_output_stream(
                        samplerate=self._click_sr,
                        channels=self.runtime_output_channels,
                        latency=CLICK_LATENCY,
                        blocksize=CLICK_BLOCKSIZE,
                        callback=self._click_callback
                    )
            except Exception:
                if self._promote_runtime_to_four_channels():
                    if self._wired_loopback_duplex_available():
                        self._click_stream = self._make_duplex_click_stream(
                            samplerate=self._click_sr,
                            output_channels=self.runtime_output_channels,
                            latency=CLICK_LATENCY,
                            blocksize=CLICK_BLOCKSIZE,
                        )
                        self._click_stream_is_duplex = True
                    else:
                        self._click_stream = self._make_output_stream(
                            samplerate=self._click_sr,
                            channels=self.runtime_output_channels,
                            latency=CLICK_LATENCY,
                            blocksize=CLICK_BLOCKSIZE,
                            callback=self._click_callback
                        )
                else:
                    raise
            self._click_stream.start()
            print(
                "DEBUG: Click stream started successfully, "
                f"active={self._click_stream.active}, duplex={self._click_stream_is_duplex}"
            )
            return self.persistent_output_ready()
        except Exception as e:
            print(f"ERROR: Click stream init failed: {e}")
            import traceback
            traceback.print_exc()
            self._click_stream = None
            self._click_stream_is_duplex = False
            if self._wired_loopback_duplex_available():
                self._wired_loopback_last_error = str(e)
                try:
                    print("Warning: Falling back to output-only click stream after duplex init failed.")
                    self._click_stream = self._make_output_stream(
                        samplerate=self._click_sr,
                        channels=self.runtime_output_channels,
                        latency=CLICK_LATENCY,
                        blocksize=CLICK_BLOCKSIZE,
                        callback=self._click_callback,
                    )
                    self._click_stream.start()
                    return self.persistent_output_ready()
                except Exception as fallback_exc:
                    print(f"ERROR: Output-only click stream fallback failed: {fallback_exc}")
                    traceback.print_exc()
                    self._click_stream = None
            return False
    
    def trigger_click(self, metadata=None, marker_gain=None):
        """Trigger instant click playback."""
        if self._click_data is None:
            print("DEBUG: trigger_click - no click data")
            return
        if self._click_stream is None:
            print("DEBUG: trigger_click - no click stream")
            return
        if not self._click_stream.active:
            print("DEBUG: trigger_click - click stream not active, restarting...")
            try:
                self._click_stream.start()
            except Exception as e:
                print(f"DEBUG: Failed to restart click stream: {e}")
                return
        with self._click_lock:
            self._click_pos = 0
            self._click_active = True
            self._click_metadata = dict(metadata or {})
            self._click_gain = marker_gain
            print("DEBUG: Click triggered!")
    
    def _block_callback(self, outdata, frames, time_info, status):
        """Callback for block audio playback - ensures consistent timing."""
        if status:
            print(f"Block stream status: {status}")  # Log any underruns

        if self._block_data is None or self.stop_flag:
            outdata.fill(0)
            self._record_output_evidence_buffer(outdata, sample_rate=self._block_sr)
            return

        # Handle pause - output silence but don't advance position
        if self.paused:
            outdata.fill(0)
            self._record_output_evidence_buffer(outdata, sample_rate=self._block_sr)
            return

        with self._block_lock:
            remaining = len(self._block_data) - self._block_pos

            if remaining <= 0:
                # Playback finished
                outdata.fill(0)
                self._block_finished.set()
                self._record_output_evidence_buffer(outdata, sample_rate=self._block_sr)
                return

            n = min(frames, remaining)
            buffer_start_sample = self._block_pos
            if n > 0 and self._block_event_schedule is not None:
                event_frames = n + 1 if self._block_pos + n >= len(self._block_data) else n
                self._emit_scheduled_block_events(buffer_start_sample, event_frames, time_info)
            elif n > 0 and self._block_pos == 0:
                self._emit_audio_sample_zero_once(time_info)
            # Apply volume in real time for instant slider response.
            outdata[:n] = apply_output_volumes(
                self._block_data[self._block_pos:self._block_pos + n],
                self.audio_volume,
                self.tactile_volume,
                audio_channels=self.audio_output_channels,
                tactile_channel=self.tactile_output_channel,
                duplicate_tactile_channel=self._duplicate_tactile_channel(),
            )
            if n < frames:
                outdata[n:].fill(0)

            self._block_pos += n
            self.elapsed_time = self._block_pos / self._block_sr

            # Check if finished
            if self._block_pos >= len(self._block_data):
                self._block_finished.set()
        self._record_output_evidence_buffer(outdata, sample_rate=self._block_sr)

    def play_block(self, path, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        """Play a block WAV file with callback-based streaming for timing stability.

        Supported layouts:
        - legacy Study 5 stereo: WAV left=tactile, WAV right=audio; routed to Output 2/1.
        - rendered spatial blocks: WAV channels left/right/tactile; routed to Output 1/2/3.

        Uses callback-based streaming for consistent timing (no jitter from write() loop).
        """
        try:
            # Check cache first, otherwise load from file
            if path in self._audio_cache:
                data, sr = self._audio_cache[path]
                data = data.copy()  # Copy so we don't modify cached data
            else:
                data, sr = sf.read(path, dtype='float32')

            source_channels = 1 if data.ndim == 1 else int(data.shape[1])
            if source_channels >= BINAURAL_TACTILE_CHANNELS and self.max_output_channels < BINAURAL_TACTILE_CHANNELS:
                print(
                    "ERROR: This rendered binaural+tactile block requires one synchronized "
                    "3+ channel output device. Enable/select the Komplete ASIO driver or another "
                    "multichannel output endpoint. Separate Windows stereo endpoints are not safe "
                    "for binaural+tactile timing."
                )
                return False

            requested_channels = self.runtime_output_channels if source_channels >= BINAURAL_TACTILE_CHANNELS else 2
            try:
                prepared = prepare_block_audio_for_output(
                    data,
                    output_channels=requested_channels,
                    output_channel_map=self.output_channel_map,
                )
            except ValueError as exc:
                print(f"ERROR: Unsupported block WAV layout for {path}: {exc}")
                return False

            # Setup state for callback
            self.stop_flag = False
            self.paused = False
            self.pause_event.set()
            self.elapsed_time = 0.0
            self._block_finished.clear()
            self._block_progress_callback = progress_callback
            self._audio_event_callback = audio_event_callback
            self._audio_sample_zero_emitted = False
            self._block_event_schedule = block_event_schedule
            if self._block_event_schedule is not None and hasattr(self._block_event_schedule, "reset"):
                self._block_event_schedule.reset()

            with self._block_lock:
                self._block_data = prepared.data
                self._block_sr = sr
                self._block_pos = 0

            use_persistent_output = self._persistent_output_available(
                samplerate=sr,
                channels=prepared.channels,
            )

            if use_persistent_output:
                print(
                    "Starting block playback on persistent ASIO stream: "
                    f"layout={prepared.layout}, source_channels={prepared.source_channels}, "
                    f"output_channels={prepared.channels}, tactile_out={prepared.tactile_channel + 1}, "
                    f"latency={STREAM_LATENCY}s, blocksize={AUDIO_BLOCKSIZE}"
                )

                def update_progress():
                    while not self._block_finished.is_set() and not self.stop_flag:
                        if progress_callback:
                            progress_callback(self.elapsed_time)
                        time.sleep(0.1)

                progress_thread = threading.Thread(target=update_progress, daemon=True)
                progress_thread.start()

                while not self._block_finished.is_set() and not self.stop_flag:
                    time.sleep(0.05)

                with self._block_lock:
                    self._block_data = None
                self._audio_event_callback = None
                self._block_event_schedule = None

                return not self.stop_flag

            self._close_persistent_output()

            # Create callback-based stream for consistent timing
            try:
                self._block_stream = self._make_output_stream(
                    samplerate=sr,
                    channels=prepared.channels,
                    latency=BLOCK_STREAM_LATENCY,
                    blocksize=BLOCK_BLOCKSIZE,
                    callback=self._block_callback,
                )
            except Exception:
                if prepared.channels == 3 and self._promote_runtime_to_four_channels():
                    prepared = prepare_block_audio_for_output(
                        data,
                        output_channels=4,
                        output_channel_map=self.output_channel_map,
                    )
                    with self._block_lock:
                        self._block_data = prepared.data
                        self._block_pos = 0
                    self._block_stream = self._make_output_stream(
                        samplerate=sr,
                        channels=prepared.channels,
                        latency=BLOCK_STREAM_LATENCY,
                        blocksize=BLOCK_BLOCKSIZE,
                        callback=self._block_callback,
                    )
                else:
                    raise

            print(
                "Starting block playback: "
                f"layout={prepared.layout}, source_channels={prepared.source_channels}, "
                f"output_channels={prepared.channels}, tactile_out={prepared.tactile_channel + 1}, "
                f"latency={BLOCK_STREAM_LATENCY}s, blocksize={BLOCK_BLOCKSIZE}"
            )
            self._block_stream.start()

            # Progress update thread
            def update_progress():
                while not self._block_finished.is_set() and not self.stop_flag:
                    if progress_callback:
                        progress_callback(self.elapsed_time)
                    time.sleep(0.1)  # Update 10x per second

            progress_thread = threading.Thread(target=update_progress, daemon=True)
            progress_thread.start()

            # Wait for playback to finish or stop
            while not self._block_finished.is_set() and not self.stop_flag:
                time.sleep(0.05)

            # Cleanup
            self._block_stream.stop()
            self._block_stream.close()
            self._block_stream = None

            with self._block_lock:
                self._block_data = None

            self._restart_persistent_output()
            self._audio_event_callback = None
            self._block_event_schedule = None
            return not self.stop_flag

        except Exception as e:
            print(f"ERROR: Block playback failed: {e}")
            import traceback
            traceback.print_exc()
            self._restart_persistent_output()
            self._audio_event_callback = None
            self._block_event_schedule = None
            return False
    
    def pause(self):
        """Pause playback."""
        self.paused = True
        self.pause_event.clear()
    
    def resume(self):
        """Resume playback."""
        self.paused = False
        self.pause_event.set()
    
    def stop(self):
        """Stop block/instruction playback (but keep click stream alive for zero-lag clicks)."""
        self.stop_flag = True
        self.pause_event.set()  # Release pause if waiting
        self._block_finished.set()  # Signal block playback to stop
        self._instr_finished.set()  # Signal instruction playback to stop
        # NOTE: We do NOT stop/close the click stream here - it must stay open for instant clicks

        # Stop block stream if active
        if self._block_stream is not None:
            try:
                self._block_stream.stop()
                self._block_stream.close()
            except Exception:
                pass
            self._block_stream = None

        # Stop instruction stream if active
        if self._instr_stream is not None:
            try:
                self._instr_stream.stop()
                self._instr_stream.close()
            except Exception:
                pass
            self._instr_stream = None

        # Stop any active output evidence recording and save it as interrupted.
        if self._output_evidence.active:
            print("Saving interrupted digital output evidence recording...")
            self.stop_recording(interrupted=True)

        if self._wired_loopback.active or self._wired_loopback_stream is not None:
            print("Saving interrupted wired loopback recording...")
            self.stop_wired_loopback_recording(interrupted=True)

        # Stop any legacy diagnostic recording and SAVE it with interrupted marker
        if self._recording_stream is not None:
            print("Saving interrupted recording...")
            self.stop_recording(interrupted=True)

    def shutdown(self):
        """Full shutdown - close all streams including click stream and recording."""
        self.stop()

        # Stop any active output evidence recording.
        if self._output_evidence.active:
            self.stop_recording(interrupted=True)

        if self._wired_loopback.active or self._wired_loopback_stream is not None:
            self.stop_wired_loopback_recording(interrupted=True)

        # Stop any active legacy diagnostic recording
        if self._recording_stream is not None:
            try:
                self._recording_stream.stop_stream()
                self._recording_stream.close()
            except Exception:
                pass
            self._recording_stream = None

        # Close PyAudio instance
        if self._recording_pyaudio is not None:
            try:
                self._recording_pyaudio.terminate()
            except Exception:
                pass
            self._recording_pyaudio = None

        if self._click_stream:
            try:
                self._click_stream.stop()
                self._click_stream.close()
            except Exception:
                pass
            self._click_stream = None

        # Clear audio cache
        self._audio_cache.clear()

    def _instr_callback(self, outdata, frames, time_info, status):
        """Callback for instruction audio playback."""
        if status:
            print(f"Instruction stream status: {status}")

        if self._instr_data is None or self.stop_flag:
            outdata.fill(0)
            return

        with self._instr_lock:
            remaining = len(self._instr_data) - self._instr_pos

            if remaining <= 0:
                outdata.fill(0)
                self._instr_finished.set()
                return

            n = min(frames, remaining)
            outdata[:n] = apply_output_volumes(
                self._instr_data[self._instr_pos:self._instr_pos + n],
                self.audio_volume,
                0.0,
                audio_channels=self.audio_output_channels,
                tactile_channel=self.tactile_output_channel,
                duplicate_tactile_channel=self._duplicate_tactile_channel(),
            )
            if n < frames:
                outdata[n:].fill(0)

            self._instr_pos += n

            if self._instr_pos >= len(self._instr_data):
                self._instr_finished.set()

    def play_instruction(self, path, on_complete=None):
        """Play instruction audio through auditory output channels only.

        Uses callback-based streaming for consistent timing.
        Returns immediately, calls on_complete when finished.
        """
        if not os.path.exists(path):
            print(f"ERROR: Instruction file not found: {path}")
            if on_complete:
                on_complete(False)
            return

        def play_thread():
            try:
                # Check cache first
                if path in self._audio_cache:
                    data, sr = self._audio_cache[path]
                    data = data.copy()
                else:
                    data, sr = sf.read(path, dtype='float32')

                data = center_audio_for_output(
                    data,
                    self.runtime_output_channels,
                    audio_channels=self.audio_output_channels,
                )

                self.stop_flag = False
                self._instr_finished.clear()

                with self._instr_lock:
                    self._instr_data = data
                    self._instr_sr = sr
                    self._instr_pos = 0
                    self._instr_on_complete = on_complete

                if self._persistent_output_available(samplerate=sr, channels=data.shape[1]):
                    print(
                        "Starting instruction playback on persistent ASIO stream: "
                        f"channels={data.shape[1]}, latency={STREAM_LATENCY}s, blocksize={AUDIO_BLOCKSIZE}"
                    )
                    while not self._instr_finished.is_set() and not self.stop_flag:
                        time.sleep(0.05)

                    with self._instr_lock:
                        self._instr_data = None

                    if on_complete:
                        on_complete(not self.stop_flag)
                    return

                self._close_persistent_output()

                # Create callback-based stream
                try:
                    self._instr_stream = self._make_output_stream(
                        samplerate=sr,
                        channels=data.shape[1],
                        latency=STREAM_LATENCY,
                        blocksize=AUDIO_BLOCKSIZE,
                        callback=self._instr_callback,
                    )
                except Exception:
                    if data.shape[1] == 3 and self._promote_runtime_to_four_channels():
                        data = center_audio_for_output(
                            data[:, :2],
                            self.runtime_output_channels,
                            audio_channels=self.audio_output_channels,
                        )
                        with self._instr_lock:
                            self._instr_data = data
                            self._instr_pos = 0
                        self._instr_stream = self._make_output_stream(
                            samplerate=sr,
                            channels=data.shape[1],
                            latency=STREAM_LATENCY,
                            blocksize=AUDIO_BLOCKSIZE,
                            callback=self._instr_callback,
                        )
                    else:
                        raise
                self._instr_stream.start()

                # Wait for playback to finish
                while not self._instr_finished.is_set() and not self.stop_flag:
                    time.sleep(0.05)

                self._instr_stream.stop()
                self._instr_stream.close()
                self._instr_stream = None

                with self._instr_lock:
                    self._instr_data = None

                self._restart_persistent_output()

                if on_complete:
                    on_complete(not self.stop_flag)

            except Exception as e:
                print(f"ERROR: Instruction playback failed: {e}")
                import traceback
                traceback.print_exc()
                self._restart_persistent_output()
                if on_complete:
                    on_complete(False)

        threading.Thread(target=play_thread, daemon=True).start()

    def start_background_music(self, path, volume=0.5):
        """Start playing background music in a continuous loop.

        Plays through auditory output channels only at specified volume.
        Returns the stream object for control, or None on failure.
        """
        if not os.path.exists(path):
            print(f"ERROR: Background music not found: {path}")
            return None

        try:
            data, sr = sf.read(path, dtype='float32')
            base_data = center_audio_for_output(
                data,
                self.runtime_output_channels,
                audio_channels=self.audio_output_channels,
            )
            data = apply_output_volumes(
                base_data,
                volume,
                0.0,
                audio_channels=self.audio_output_channels,
                tactile_channel=self.tactile_output_channel,
                duplicate_tactile_channel=self._duplicate_tactile_channel(),
            )

            # Create looping playback
            self.bg_music_base_data = base_data
            self.bg_music_data = data
            self.bg_music_sr = sr
            self.bg_music_idx = 0
            self.bg_music_volume = volume
            self.bg_music_stop = False

            if self._persistent_output_available(samplerate=sr, channels=data.shape[1]):
                print(
                    f"Background music started on persistent ASIO stream "
                    f"(channels={data.shape[1]}, volume: {volume*100:.0f}%)"
                )
                return _PersistentPlaybackHandle(lambda: setattr(self, "bg_music_stop", True))

            def callback(outdata, frames, time_info, status):
                remaining = len(self.bg_music_data) - self.bg_music_idx
                if remaining >= frames:
                    outdata[:] = self.bg_music_data[self.bg_music_idx:self.bg_music_idx + frames]
                    self.bg_music_idx += frames
                else:
                    # Loop: fill with remaining, then restart from beginning
                    outdata[:remaining] = self.bg_music_data[self.bg_music_idx:]
                    outdata[remaining:] = self.bg_music_data[:frames - remaining]
                    self.bg_music_idx = frames - remaining

            self._close_persistent_output()

            try:
                stream = self._make_output_stream(
                    samplerate=sr,
                    channels=data.shape[1],
                    latency=STREAM_LATENCY,
                    blocksize=AUDIO_BLOCKSIZE,
                    callback=callback,
                )
            except Exception:
                if data.shape[1] == 3 and self._promote_runtime_to_four_channels():
                    base_data = center_audio_for_output(
                        base_data[:, :2],
                        self.runtime_output_channels,
                        audio_channels=self.audio_output_channels,
                    )
                    data = apply_output_volumes(
                        base_data,
                        volume,
                        0.0,
                        audio_channels=self.audio_output_channels,
                        tactile_channel=self.tactile_output_channel,
                        duplicate_tactile_channel=self._duplicate_tactile_channel(),
                    )
                    self.bg_music_base_data = base_data
                    self.bg_music_data = data
                    stream = self._make_output_stream(
                        samplerate=sr,
                        channels=data.shape[1],
                        latency=STREAM_LATENCY,
                        blocksize=AUDIO_BLOCKSIZE,
                        callback=callback,
                    )
                else:
                    raise
            stream.start()
            print(
                f"Background music started (channels={data.shape[1]}, "
                f"volume: {volume*100:.0f}%, latency={STREAM_LATENCY}s)"
            )
            return stream

        except Exception as e:
            print(f"ERROR: Failed to start background music: {e}")
            return None

    def set_background_volume(self, volume):
        """Update the volume of background music (0.0 to 1.0)."""
        if hasattr(self, 'bg_music_base_data') and hasattr(self, 'bg_music_volume'):
            self.bg_music_data = apply_output_volumes(
                self.bg_music_base_data,
                volume,
                0.0,
                audio_channels=self.audio_output_channels,
                tactile_channel=self.tactile_output_channel,
                duplicate_tactile_channel=self._duplicate_tactile_channel(),
            )
            self.bg_music_volume = volume

    def set_main_volume(self, volume):
        """Set the main audio volume for instructions and blocks (0.0 to 1.0)."""
        self.audio_volume = volume
        print(f"Main audio volume set to {volume*100:.0f}%")


# =============================================================================
# CLICK TARGET WIDGET
# =============================================================================
class ClickTarget(tk.Canvas):
    """Visual click target area with feedback."""

    def __init__(self, parent, size=220):
        super().__init__(parent, width=size, height=size, bg='#1a1a2e',
                        highlightthickness=4, highlightbackground='#444')
        self.size = size
        self.center = size // 2
        self.active = False
        self._draw()

    def _draw(self):
        """Draw concentric target rings."""
        c = self.center
        # Outer rings
        for r, col in [(90, '#333'), (65, '#444'), (40, '#555')]:
            self.create_oval(c-r, c-r, c+r, c+r, outline=col, width=2)
        # Center dot
        self.create_oval(c-10, c-10, c+10, c+10, fill='#666', outline='#888')
        # Label
        self.create_text(c, self.size - 18, text="CLICK HERE", fill='#555', font=('Arial', 10, 'bold'))
    
    def flash(self):
        """Visual feedback on click."""
        self.config(bg='#0d7377', highlightbackground='#14ffec')
        self.after(120, lambda: self.config(
            bg='#1a1a2e',
            highlightbackground='#0d7377' if self.active else '#444'
        ))
    
    def set_active(self, active):
        """Set active state (during block playback)."""
        self.active = active
        self.config(highlightbackground='#0d7377' if active else '#444')
    
    def get_center_coords(self):
        """Get screen coordinates of center."""
        return (self.winfo_rootx() + self.center,
                self.winfo_rooty() + self.center)

    def get_mouse_bounds(self):
        """Get click-target bounds in the same coordinate space as pynput."""
        x1 = self.winfo_rootx()
        y1 = self.winfo_rooty()
        x2 = x1 + self.winfo_width()
        y2 = y1 + self.winfo_height()
        scale = self._mouse_coordinate_scale()
        return (
            int(round(x1 * scale)),
            int(round(y1 * scale)),
            int(round(x2 * scale)),
            int(round(y2 * scale)),
        )

    def _mouse_coordinate_scale(self):
        """Return Windows DPI scale between Tk logical coords and OS mouse coords."""
        if sys.platform != "win32":
            return 1.0
        scales = [1.0]
        try:
            dpi = ctypes.windll.user32.GetDpiForWindow(int(self.winfo_id()))
            if dpi:
                scales.append(max(0.5, float(dpi) / 96.0))
        except Exception:
            pass
        try:
            factor = ctypes.windll.shcore.GetScaleFactorForDevice(0)
            if factor:
                scales.append(max(0.5, float(factor) / 100.0))
        except Exception:
            pass
        return max(scales)


# =============================================================================
# MAIN APPLICATION
# =============================================================================
class PPSExperimentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PPS Experiment Runner")
        self.root.geometry("1200x960")
        self.root.minsize(1050, 760)
        self.root.resizable(True, True)

        # Load saved settings
        self.settings = load_settings()

        # Mouse lock state for between-block waiting
        self.mouse_locked = False
        self._mouse_lock_timer = None

        # State
        self.participant_id = None
        self.participant_folder = None
        self.current_run_package = None
        self.run_setup_manifest = RUN_SETUP_MANIFEST
        self.run_event_logger = None
        self.run_events = None
        self.block_schedules = {}
        self.trigger_dictionary = None
        self._run_block_by_path = {}
        self._active_run_block = None
        self._active_block_start_unix = 0.0
        self._active_block_start_monotonic = 0.0
        self._active_planned_logged = False
        self._accepting_segment_responses = False
        self._session_outputs_written = False
        self.current_part = 1  # 1 or 2 (Part1 or Part2)
        self.part1_files = []  # Block files for Part 1
        self.part2_files = []  # Block files for Part 2
        self.block_files = []  # Current active block files (points to part1 or part2)
        self.current_block = 0  # 0-indexed within current part
        self.current_block_duration = DEFAULT_BLOCK_DURATION  # Duration of current block in seconds
        self.is_playing = False
        self.is_paused = False
        self.is_instruction_playing = False  # True when instruction audio is playing
        self.awaiting_click_to_start = False  # True when waiting for click to start next block
        self.demographics_completed = False  # True when demographics have been saved
        self._operator_stop_requested = False
        
        # Audio engine
        self.device_idx, self.device_name, is_komplete = find_output_device()
        if self.device_idx is None:
            print("ERROR: Could not find any audio output device")
            messagebox.showerror("Audio Error", audio_runtime_preflight_message())
        elif is_komplete:
            print(f"Komplete Audio 6 found: [{self.device_idx}] {self.device_name}")
        else:
            print(f"Using system default audio: [{self.device_idx}] {self.device_name}")
        
        self.audio = AudioEngine(self.device_idx) if self.device_idx is not None else None
        if self.audio:
            if self.audio.max_output_channels >= BINAURAL_TACTILE_CHANNELS:
                print(
                    "Audio routing mode: spatial rendered files use Output 1/2 for binaural audio "
                    f"and Output {self.audio.tactile_output_channel + 1} for tactile."
                )
            else:
                print("Audio routing mode: legacy stereo only; rendered binaural+tactile files require ASIO 3+ outputs.")
        
        # Load click sound
        if self.audio:
            if self.audio.load_click_sound(CLICK_SOUND):
                print("Click sound loaded successfully")

            # Pre-load all instruction audio files for instant playback
            if PREBUFFER_AUDIO:
                print("Pre-loading instruction audio files...")
                instruction_files = [
                    GENERAL_INSTRUCTIONS,
                    PRE_BLOCK_INSTRUCTIONS,
                    POST_BLOCK_INSTRUCTIONS,
                    INTERIM_MESSAGE,
                    FINISH_MESSAGE,
                ]
                self.audio.preload_audio(instruction_files)

        # Mouse listener for click feedback
        self.mouse_listener = None
        
        # Keyboard listener for pause shortcut
        self.keyboard_listener = None
        
        # Recentering state
        self.recenter_timer = None
        self.next_recenter_time = 0
        self.recentering_active = False

        # Background music state
        self.bg_music_playing = False
        self.bg_music_stream = None
        self.bg_music_volume = 0.5  # Default 50%
        
        # Scan participants
        self.participants = self._scan_participants()
        print(f"Found {len(self.participants)} participant folders")
        
        # Build UI
        self._build_ui()
        
        # Setup keyboard shortcut
        self._setup_keyboard_listener()
        
        # Cleanup on close
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _scan_participants(self):
        """Scan for all Pxx folders (dynamically detects any participant number)."""
        if self.run_setup_manifest:
            try:
                participants = segment_run_setup_participants(Path(self.run_setup_manifest))
                print(f"Segment 6 runner setup loaded: {self.run_setup_manifest}")
                return participants
            except Exception as exc:
                print(f"ERROR: Could not read Segment 6 run setup: {exc}")
                return []

        participants = []
        if not os.path.exists(STIMULI_DIR):
            print(f"ERROR: Stimuli directory not found: {STIMULI_DIR}")
            return participants

        pattern = re.compile(r'^P(\d+)$')
        for item in os.listdir(STIMULI_DIR):
            full_path = os.path.join(STIMULI_DIR, item)
            if os.path.isdir(full_path) and pattern.match(item):
                participants.append(item)

        return sorted(participants, key=lambda x: int(x[1:]))
    
    def _find_block_files(self, folder):
        """Find block WAV files in a folder.

        Looks for block number in filename patterns like:
        - P01_PPS_part1_1f_concatenated.wav -> Block 1 (number after 'part1_' or 'part2_')
        - 1.wav, 1a_concatenated.wav -> Block 1 (leading digit)
        Returns list of found block files (may have None for missing blocks).
        """
        import re

        if not os.path.exists(folder):
            return []

        # Pattern to find block number: either after 'part1_' / 'part2_' or at start of filename
        # Matches: part1_1, part2_3, or filename starting with digit
        block_pattern = re.compile(r'part[12]_(\d+)|^(\d+)')

        # First pass: find all block numbers and max
        block_nums_found = []
        for f in os.listdir(folder):
            if not f.endswith('.wav'):
                continue

            match = block_pattern.search(f.lower())
            if match:
                # Get the block number from either group
                block_num = int(match.group(1) or match.group(2))
                block_nums_found.append(block_num)

        if not block_nums_found:
            return []

        max_block = max(block_nums_found)
        block_files = [None] * max_block

        # Second pass: assign files to block slots
        for f in os.listdir(folder):
            if not f.endswith('.wav'):
                continue

            match = block_pattern.search(f.lower())
            if match:
                block_num = int(match.group(1) or match.group(2))
                if 1 <= block_num <= max_block:
                    idx = block_num - 1
                    block_files[idx] = os.path.join(folder, f)

        return block_files

    def _get_wav_duration(self, wav_path):
        """Get duration of WAV file in seconds."""
        try:
            info = sf.info(wav_path)
            return info.duration
        except Exception as e:
            print(f"Warning: Could not read WAV duration: {e}")
            return DEFAULT_BLOCK_DURATION

    def _run_source_summary(self) -> str:
        if self.run_setup_manifest:
            path = Path(self.run_setup_manifest)
            try:
                project_name = path.parents[1].name
            except IndexError:
                project_name = path.parent.name
            return f"Prepared setup: {project_name} / {path.name}"
        return f"Legacy stimuli folder: {STIMULI_DIR}"

    def _runtime_status_summary(self) -> str:
        if self.run_events is not None:
            lsl = "LSL: active" if self.run_events.lsl_status.enabled else f"LSL: {self.run_events.lsl_status.message}"
        else:
            lsl = "LSL: armed after participant selection" if self._capture_options().enable_lsl else "LSL: disabled"
        evidence_allowed = self._capture_options().start_backup_recording
        evidence = "Audio evidence WAV: on" if evidence_allowed else "Audio evidence WAV: off"
        buffer = f"Buffer: {AUDIO_BLOCKSIZE} frames, latency {int(STREAM_LATENCY * 1000)} ms"
        return f"{lsl} | {evidence} | {buffer}"

    def _capture_options(self) -> SessionCaptureOptions:
        def _var(name: str, default: bool) -> bool:
            variable = getattr(self, name, None)
            if variable is None:
                return bool(self.settings.get(name.replace("_var", ""), default))
            try:
                return bool(variable.get())
            except Exception:
                return default

        return SessionCaptureOptions(
            enable_lsl=_var("enable_lsl_var", True),
            write_internal_xdf=_var("write_internal_xdf_var", True),
            write_analysis_csvs=_var("write_analysis_csvs_var", True),
            start_backup_recording=_var("start_backup_recording_var", True),
        )

    def _on_capture_option_changed(self) -> None:
        options = self._capture_options()
        self.settings.update(options.as_dict())
        save_settings(self.settings)
        if hasattr(self, "runtime_status_label"):
            self.runtime_status_label.config(text=self._runtime_status_summary())

    def _set_event_stream_status(self, text: str) -> None:
        if not hasattr(self, "event_stream_label"):
            return
        def update() -> None:
            self.event_stream_label.config(text=text)
        if threading.current_thread() is threading.main_thread():
            try:
                update()
            except RuntimeError:
                pass
            return
        try:
            self.root.after(0, update)
        except RuntimeError:
            pass

    def _current_session_folder(self) -> Path | None:
        if self.current_run_package is not None:
            return Path(self.current_run_package.session_dir)
        if self.participant_folder:
            return Path(self.participant_folder)
        return None

    def _open_session_folder(self):
        folder = self._current_session_folder()
        if folder is None or not folder.exists():
            messagebox.showwarning("No Session Folder", "Select a participant and prepare a session first.")
            return
        try:
            os.startfile(str(folder))  # type: ignore[attr-defined]
        except AttributeError:
            subprocess.Popen(["explorer.exe", str(folder)])
        except Exception as exc:
            messagebox.showerror("Open Folder Failed", str(exc))

    def _format_block_order_summary(self) -> str:
        if self.current_run_package is None:
            if self.participant_folder:
                return f"Legacy folder: {self.participant_folder}"
            return "No session prepared."

        def _part_summary(part_number: int, files: list[str]) -> str:
            if not files:
                return f"Part {part_number}: none"
            names = [Path(path).stem for path in files[:4]]
            suffix = "" if len(files) <= 4 else f" + {len(files) - 4} more"
            return f"Part {part_number}: {len(files)} blocks ({', '.join(names)}{suffix})"

        return " | ".join([_part_summary(1, self.part1_files), _part_summary(2, self.part2_files)])

    def _initialize_segment_event_logging(self):
        if self.current_run_package is None:
            self.run_event_logger = None
            self.run_events = None
            return
        package = self.current_run_package
        self.run_event_logger = SessionEventLogger(package.participant_id)
        self.run_event_logger.session_id = package.session_id
        self.block_schedules = _block_event_schedules(package)
        self.trigger_dictionary = TriggerDictionary.from_schedules(self.block_schedules.values())
        self.run_events = TimingEventHub(
            self.run_event_logger,
            enable_lsl=self._capture_options().enable_lsl,
            session_id=package.session_id,
            participant_id=package.participant_id,
            trigger_dictionary=self.trigger_dictionary,
        )
        self._session_outputs_written = False
        self.run_events.log(
            "session_start",
            session_dir=str(package.session_dir),
            session_manifest=str(package.manifest_path),
            execution_mode=package.execution_mode,
            lsl_enabled=self.run_events.lsl_status.enabled,
            lsl_message=self.run_events.lsl_status.message,
            capture_options=self._capture_options().as_dict(),
        )
        if hasattr(self, "runtime_status_label"):
            self.runtime_status_label.config(text=self._runtime_status_summary())
        self._set_event_stream_status("Event stream: session armed, waiting for block playback")

    def _segment_event_metadata(self, block) -> dict[str, object]:
        metadata = dict(getattr(block, "metadata", {}) or {})
        return {
            f"block_{key}": value
            for key, value in metadata.items()
            if isinstance(key, str) and key and isinstance(value, (str, int, float, bool))
        }

    def _find_run_block_for_path(self, block_path: str | Path):
        try:
            return self._run_block_by_path.get(str(Path(block_path).resolve()))
        except Exception:
            return None

    def _trial_duration_default(self, block) -> float:
        trial_count = int(getattr(block, "trial_count", 0) or 0)
        duration = float(getattr(block, "duration_s", 0.0) or 0.0)
        if trial_count > 0 and duration > 0:
            return duration / trial_count
        return DEFAULT_BLOCK_DURATION

    def _handle_segment_audio_event(self, payload: dict[str, object]):
        if self.run_events is None or self.run_event_logger is None or self._active_run_block is None:
            return
        event_payload = dict(payload)
        event_type = str(event_payload.get("event_type", "audio_event"))
        event_payload.setdefault("block_number", self._active_run_block.index)
        event_payload.setdefault("block_index", self._active_run_block.index)
        event_payload.setdefault("block_label", self._active_run_block.label)
        event_payload.setdefault("block_path", str(self._active_run_block.wav_path))
        event_payload.update(self._segment_event_metadata(self._active_run_block))
        if event_type == "audio_sample_zero":
            self._accepting_segment_responses = True
        self.run_events.enqueue_callback_event(event_payload)

    def _has_segment_event(self, event_type: str, block_number: int) -> bool:
        if self.run_event_logger is None:
            return False
        return any(
            event.event_type == event_type
            and str(event.payload.get("block_number", event.payload.get("block_index", ""))) == str(block_number)
            for event in self.run_event_logger.events
        )

    def _log_block_anchor_fallback_events(self):
        if self.run_event_logger is None or self._active_run_block is None:
            return
        self.run_event_logger.extend_planned_block_events(
            self._active_run_block.manifest_path,
            block_start_unix=self._active_block_start_unix,
            block_start_monotonic=self._active_block_start_monotonic,
            participant_id=self.current_run_package.participant_id if self.current_run_package else self.participant_id,
            part_number=int(self._active_run_block.metadata.get("part_number", self.current_part)),
            block_number=self._active_run_block.index,
            trial_duration_s=self._trial_duration_default(self._active_run_block),
            stimulus_segment_onset_s=0.0,
        )

    def _fallback_segment_planned_events_if_needed(self):
        if (
            self.run_events is None
            or self.run_event_logger is None
            or self._active_run_block is None
        ):
            return
        self.run_events.flush_callback_events()
        if self._has_segment_event("audio_sample_zero", self._active_run_block.index):
            return
        self.run_events.log(
            "timing_anchor_fallback",
            block_number=self._active_run_block.index,
            block_index=self._active_run_block.index,
            block_label=self._active_run_block.label,
            reason="audio_sample_zero was not emitted by the audio engine",
            timestamp_quality="block_anchor_fallback",
        )
        self._log_block_anchor_fallback_events()

    def _record_segment_mouse_click(self, x=None, y=None, *, in_target=True):
        if self.run_events is None:
            return None
        during_playback = bool(self.is_playing and self._accepting_segment_responses)
        event = self.run_events.log(
            "mouse_click",
            x=x if x is not None else "",
            y=y if y is not None else "",
            in_target=bool(in_target),
            during_playback=during_playback,
            block_number=self._active_run_block.index if self._active_run_block else "",
            block_label=self._active_run_block.label if self._active_run_block else "",
            push_lsl=False,
        )
        self._set_event_stream_status("Event stream: mouse_click logged")
        if during_playback:
            return {
                "mouse_event_id": event.event_id,
                "mouse_event_unix_time": event.unix_time,
                "mouse_event_monotonic_time": event.monotonic_time,
                "_deferred_lsl_event": event,
            }
        self.run_events.push_deferred_event_marker(event)
        return None

    def _write_segment_event_outputs(self, *, completed: bool = False, interrupted: bool = False):
        if self.current_run_package is None or self.run_event_logger is None or self.run_events is None:
            return
        if self._session_outputs_written:
            return
        self.run_events.flush_callback_events()
        package = self.current_run_package
        if completed or interrupted:
            self.run_events.log("session_end", completed=bool(completed), interrupted=bool(interrupted))
        events_csv = package.session_dir / "events.csv"
        events_xdf = package.session_dir / "events.xdf"
        lsl_markers_csv = package.session_dir / "lsl_markers.csv"
        lsl_markers_xdf = package.session_dir / "lsl_markers.xdf"
        trigger_dictionary_path = package.session_dir / "trigger_dictionary.json"
        self.run_event_logger.write_csv(events_csv)
        options = self._capture_options()
        if options.write_internal_xdf:
            self.run_event_logger.write_xdf(
                events_xdf,
                metadata={
                    "participant_id": package.participant_id,
                    "session_id": package.session_id,
                    "session_manifest": str(package.manifest_path),
                    "lsl_status": dict(self.run_events.lsl_status.__dict__),
                    "capture_options": options.as_dict(),
                },
            )
        if options.write_lsl_marker_mirror:
            self.run_events.write_lsl_markers_csv(lsl_markers_csv)
            self.run_events.write_lsl_markers_xdf(lsl_markers_xdf)
        if options.write_trigger_dictionary:
            self.run_events.write_trigger_dictionary(trigger_dictionary_path)
        analysis = analyze_session_events(self.run_event_logger.events)
        if options.write_analysis_csvs:
            outputs = write_analysis_csvs(analysis, package.session_dir / "analysis", package.session_id)
            outputs["timing_qc"] = _write_timing_qc_csv(
                self.run_event_logger.events,
                package.session_dir / "analysis" / f"{package.session_id}_timing_qc.csv",
            )
        summary = format_analysis_summary(analysis)
        (package.session_dir / "analysis_summary.txt").write_text(summary + "\n", encoding="utf-8")
        self._session_outputs_written = True
        if hasattr(self, "runtime_status_label"):
            self.runtime_status_label.config(text=self._runtime_status_summary())
        self._set_event_stream_status(f"Event stream: wrote {len(self.run_event_logger.events)} events to session folder")
        print(f"Segment runner events written: {events_csv}")
    
    def _build_ui(self):
        """Build the GUI with two-column layout."""
        # Main container
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill='both', expand=True)

        # Title
        ttk.Label(main, text="PPS Experiment Runner",
                 font=('Arial', 18, 'bold')).pack(pady=(0, 10))

        # Two-column layout: left panel (controls) and right panel (click area + demographics)
        columns = ttk.Frame(main)
        columns.pack(fill='both', expand=True)

        # LEFT PANEL - Controls
        left_panel = ttk.Frame(columns, width=520)
        left_panel.pack(side='left', fill='y', expand=False, padx=(0, 10))
        left_panel.pack_propagate(False)

        # RIGHT PANEL - Click area + Demographics
        right_panel = ttk.Frame(columns)
        right_panel.pack(side='right', fill='both', expand=True)

        # =====================================================================
        # LEFT PANEL CONTENTS
        # =====================================================================

        # === Dashboard Setup / Runtime Mode ===
        setup_frame = ttk.LabelFrame(left_panel, text="Runner Source", padding=8)
        setup_frame.pack(fill='x', pady=3)

        mode_text = (
            "Mode: Segment 5/6 participant block WAVs"
            if self.run_setup_manifest
            else "Mode: legacy participant WAV folder"
        )
        ttk.Label(setup_frame, text=mode_text, foreground='blue').pack(anchor='w')
        source_text = self._run_source_summary()
        self.run_source_label = ttk.Label(setup_frame, text=source_text, wraplength=390, foreground='gray')
        self.run_source_label.pack(anchor='w', pady=(3, 0))
        route_text = f"Audio route: {self.device_name or 'not detected'}"
        self.audio_route_label = ttk.Label(setup_frame, text=route_text, wraplength=390, foreground='gray')
        self.audio_route_label.pack(anchor='w', pady=(3, 0))
        self.runtime_status_label = ttk.Label(
            setup_frame,
            text=self._runtime_status_summary(),
            wraplength=490,
            foreground='gray',
        )
        self.runtime_status_label.pack(anchor='w', pady=(3, 0))
        self.event_stream_label = ttk.Label(
            setup_frame,
            text="Event stream: waiting for participant session",
            wraplength=490,
            foreground='gray',
        )
        self.event_stream_label.pack(anchor='w', pady=(3, 0))

        capture_frame = ttk.LabelFrame(left_panel, text="Recording", padding=8)
        capture_frame.pack(fill='x', pady=3)
        self.enable_lsl_var = tk.BooleanVar(value=bool(self.settings.get("enable_lsl", True)))
        self.write_internal_xdf_var = tk.BooleanVar(value=bool(self.settings.get("write_internal_xdf", True)))
        self.write_analysis_csvs_var = tk.BooleanVar(value=bool(self.settings.get("write_analysis_csvs", True)))
        self.start_backup_recording_var = tk.BooleanVar(value=bool(self.settings.get("start_backup_recording", True)))
        for text, variable in (
            ("LSL streams", self.enable_lsl_var),
            ("events.xdf", self.write_internal_xdf_var),
            ("analysis CSVs", self.write_analysis_csvs_var),
            ("audio evidence WAV", self.start_backup_recording_var),
        ):
            ttk.Checkbutton(
                capture_frame,
                text=text,
                variable=variable,
                command=self._on_capture_option_changed,
            ).pack(side='left', padx=(0, 12))
        ttk.Label(capture_frame, text="CSV on", foreground='gray').pack(side='left', padx=(4, 0))

        # === General Instructions ===
        instr_frame = ttk.LabelFrame(left_panel, text="Instructions", padding=8)
        instr_frame.pack(fill='x', pady=3)

        self.general_instr_btn = ttk.Button(
            instr_frame, text="Play General Instructions",
            command=self._play_general_instructions, width=25
        )
        self.general_instr_btn.pack(side='left', padx=5)

        self.instr_status_label = ttk.Label(instr_frame, text="", foreground='blue')
        self.instr_status_label.pack(side='left', padx=10)

        # === Background Music ===
        bg_frame = ttk.LabelFrame(left_panel, text="Background Music", padding=8)
        bg_frame.pack(fill='x', pady=3)

        bg_row = ttk.Frame(bg_frame)
        bg_row.pack(fill='x')

        self.bg_music_btn = ttk.Button(
            bg_row, text="Play", command=self._toggle_background_music, width=10
        )
        self.bg_music_btn.pack(side='left', padx=5)

        ttk.Label(bg_row, text="Vol:").pack(side='left', padx=(10, 3))

        saved_volume = self.settings.get("volume", 50)
        self.bg_volume_var = tk.DoubleVar(value=saved_volume)
        self.bg_volume_scale = ttk.Scale(
            bg_row, from_=0, to=100, variable=self.bg_volume_var,
            orient='horizontal', length=120, command=self._on_volume_change
        )
        self.bg_volume_scale.pack(side='left', padx=3)

        self.bg_volume_label = ttk.Label(bg_row, text=f"{int(saved_volume)}%", width=4)
        self.bg_volume_label.pack(side='left')

        self.bg_status_label = ttk.Label(bg_row, text="", foreground='gray')
        self.bg_status_label.pack(side='left', padx=10)

        # === Output Volume Controls ===
        vol_frame = ttk.LabelFrame(left_panel, text="Output Volume", padding=8)
        vol_frame.pack(fill='x', pady=3)

        # Audio channel volume
        audio_row = ttk.Frame(vol_frame)
        audio_row.pack(fill='x', pady=2)

        audio_label = "Audio L/R:" if self.audio and self.audio.runtime_output_channels >= 3 else "Audio (Out 1):"
        ttk.Label(audio_row, text=audio_label, width=14).pack(side='left')
        saved_audio_vol = self.settings.get("audio_volume", 100)
        self.audio_volume_var = tk.DoubleVar(value=saved_audio_vol)
        self.audio_volume_scale = ttk.Scale(
            audio_row, from_=0, to=100, variable=self.audio_volume_var,
            orient='horizontal', length=150, command=self._on_audio_volume_change
        )
        self.audio_volume_scale.pack(side='left', padx=3)
        self.audio_volume_label = ttk.Label(audio_row, text=f"{int(saved_audio_vol)}%", width=4)
        self.audio_volume_label.pack(side='left')

        # Tactile channel volume
        tactile_row = ttk.Frame(vol_frame)
        tactile_row.pack(fill='x', pady=2)

        tactile_out = self.audio.tactile_output_channel + 1 if self.audio else 2
        ttk.Label(tactile_row, text=f"Tactile (Out {tactile_out}):", width=14).pack(side='left')
        saved_tactile_vol = self.settings.get("tactile_volume", 100)
        self.tactile_volume_var = tk.DoubleVar(value=saved_tactile_vol)
        self.tactile_volume_scale = ttk.Scale(
            tactile_row, from_=0, to=100, variable=self.tactile_volume_var,
            orient='horizontal', length=150, command=self._on_tactile_volume_change
        )
        self.tactile_volume_scale.pack(side='left', padx=3)
        self.tactile_volume_label = ttk.Label(tactile_row, text=f"{int(saved_tactile_vol)}%", width=4)
        self.tactile_volume_label.pack(side='left')

        # Apply saved volumes to audio engine
        if self.audio:
            self.audio.audio_volume = saved_audio_vol / 100.0
            self.audio.tactile_volume = saved_tactile_vol / 100.0

        # Test tactile button
        test_row = ttk.Frame(vol_frame)
        test_row.pack(fill='x', pady=(8, 2))
        self.test_tactile_btn = ttk.Button(
            test_row, text="Test Tactile (SOA 0)",
            command=self._test_tactile_stimulus
        )
        self.test_tactile_btn.pack(side='left')

        # === Participant Selection ===
        pf = ttk.LabelFrame(left_panel, text="Participant", padding=8)
        pf.pack(fill='x', pady=3)

        row = ttk.Frame(pf)
        row.pack(fill='x')

        ttk.Label(row, text="Select:").pack(side='left')
        self.participant_var = tk.StringVar()
        self.participant_combo = ttk.Combobox(
            row, textvariable=self.participant_var,
            values=self.participants, width=8, state='readonly'
        )
        self.participant_combo.pack(side='left', padx=5)
        self.participant_combo.bind('<<ComboboxSelected>>', self._on_participant_selected)

        self.status_label = ttk.Label(row, text="No participant", foreground='gray')
        self.status_label.pack(side='left', padx=10)

        self.generate_all_btn = ttk.Button(
            pf,
            text="Generate All Sessions",
            command=self._generate_all_participant_sessions,
            state="normal" if self.run_setup_manifest else "disabled",
        )
        self.generate_all_btn.pack(anchor='w', pady=(8, 0))

        participant_actions = ttk.Frame(pf)
        participant_actions.pack(fill='x', pady=(8, 0))
        self.open_session_btn = ttk.Button(
            participant_actions,
            text="Open Session Folder",
            command=self._open_session_folder,
            state="disabled",
        )
        self.open_session_btn.pack(side='left')
        self.block_order_label = ttk.Label(
            pf,
            text="No session prepared.",
            wraplength=390,
            foreground='gray',
        )
        self.block_order_label.pack(anchor='w', pady=(6, 0))

        # === Part Selector ===
        self.part_frame = tk.Frame(left_panel, bg='#000000', padx=15, pady=8)
        self.part_frame.pack(fill='x', pady=3)

        part_buttons_frame = tk.Frame(self.part_frame, bg='#000000')
        part_buttons_frame.pack()

        self.part1_btn = tk.Button(
            part_buttons_frame, text="PART 1",
            font=('Arial', 14, 'bold'),
            bg='#00FF88', fg='#000000',
            activebackground='#00CC66', activeforeground='#000000',
            width=8, height=1, relief='raised', bd=3,
            command=lambda: self._switch_to_part(1)
        )
        self.part1_btn.pack(side='left', padx=5)

        self.part2_btn = tk.Button(
            part_buttons_frame, text="PART 2",
            font=('Arial', 14, 'bold'),
            bg='#555555', fg='#888888',
            activebackground='#666666', activeforeground='#999999',
            width=8, height=1, relief='sunken', bd=3,
            command=lambda: self._switch_to_part(2)
        )
        self.part2_btn.pack(side='left', padx=5)

        # === Block Control ===
        bf = ttk.LabelFrame(left_panel, text="Block Control", padding=8)
        bf.pack(fill='x', pady=3)

        row = ttk.Frame(bf)
        row.pack(fill='x')

        ttk.Label(row, text="Block:").pack(side='left')
        self.block_var = tk.StringVar(value='1')
        self.block_combo = ttk.Combobox(
            row, textvariable=self.block_var,
            values=['1', '2', '3', '4', '5', '6'], width=4, state='disabled'
        )
        self.block_combo.pack(side='left', padx=5)

        self.jump_btn = ttk.Button(row, text="Jump", command=self._jump_to_block, state='disabled')
        self.jump_btn.pack(side='left', padx=5)

        self.block_display = ttk.Label(row, text="Block: - / 6", font=('Arial', 11, 'bold'))
        self.block_display.pack(side='left', padx=15)

        # Play and Next buttons
        btn_row = ttk.Frame(bf)
        btn_row.pack(fill='x', pady=(8, 0))

        self.play_btn = ttk.Button(btn_row, text="Play Block", command=self._play_block,
                                   state='disabled', width=12)
        self.play_btn.pack(side='left', padx=5)

        self.next_btn = ttk.Button(btn_row, text="Next Block", command=self._next_block,
                                   state='disabled', width=12)
        self.next_btn.pack(side='left', padx=5)

        self.pause_label = ttk.Label(btn_row, text="", foreground='orange')
        self.pause_label.pack(side='left', padx=10)

        aux_btn_row = ttk.Frame(bf)
        aux_btn_row.pack(fill='x', pady=(6, 0))
        self.pause_control_btn = ttk.Button(
            aux_btn_row, text="Pause / Resume", command=self._toggle_pause, state='disabled', width=16
        )
        self.pause_control_btn.pack(side='left', padx=5)
        self.stop_btn = ttk.Button(
            aux_btn_row, text="Stop Block", command=self._stop_current_block, state='disabled', width=12
        )
        self.stop_btn.pack(side='left', padx=5)
        self.test_marker_btn = ttk.Button(
            aux_btn_row, text="Send Test Marker", command=self._send_test_marker, state='disabled', width=16
        )
        self.test_marker_btn.pack(side='left', padx=5)

        # === Progress ===
        prog_frame = ttk.LabelFrame(left_panel, text="Progress", padding=8)
        prog_frame.pack(fill='x', pady=3)

        self.time_label = ttk.Label(prog_frame, text="0:00 / 5:52", font=('Arial', 12))
        self.time_label.pack()

        self.progress_bar = ttk.Progressbar(prog_frame, length=380, maximum=DEFAULT_BLOCK_DURATION)
        self.progress_bar.pack(pady=5)

        # === Info ===
        self.info_label = ttk.Label(
            left_panel,
            text="Shortcut: Ctrl+Alt+P to pause/resume",
            foreground='blue',
            font=('Arial', 9),
            wraplength=490,
        )
        self.info_label.pack(pady=5)

        # Keep the operational controls in the first visible window area.
        for widget in (capture_frame, instr_frame, bg_frame, vol_frame, pf, self.part_frame, bf, prog_frame, self.info_label):
            widget.pack_forget()
        capture_frame.pack(fill='x', pady=3)
        pf.pack(fill='x', pady=3)
        self.part_frame.pack(fill='x', pady=3)
        bf.pack(fill='x', pady=3)
        prog_frame.pack(fill='x', pady=3)
        instr_frame.pack(fill='x', pady=3)
        vol_frame.pack(fill='x', pady=3)
        bg_frame.pack(fill='x', pady=3)
        self.info_label.pack(fill='x', pady=5)

        # =====================================================================
        # RIGHT PANEL CONTENTS
        # =====================================================================

        # === Click Target (top of right panel) ===
        cf = ttk.LabelFrame(right_panel, text="Click Area (Participant Response)", padding=10)
        cf.pack(pady=5, padx=10, anchor='nw')

        self.click_target = ClickTarget(cf)
        self.click_target.pack()

        ttk.Label(cf, text="Mouse recenters every 8 seconds during playback",
                 foreground='gray', font=('Arial', 8)).pack(pady=3)

        # === Demographics Section ===
        demo_frame = ttk.LabelFrame(right_panel, text="Participant Demographics", padding=10)
        demo_frame.pack(fill='x', pady=10, padx=5)

        # Name
        name_row = ttk.Frame(demo_frame)
        name_row.pack(fill='x', pady=3)
        ttk.Label(name_row, text="Name:", width=12).pack(side='left')
        self.demo_name_var = tk.StringVar()
        self.demo_name_entry = ttk.Entry(name_row, textvariable=self.demo_name_var, width=30)
        self.demo_name_entry.pack(side='left', padx=5)

        # Age
        age_row = ttk.Frame(demo_frame)
        age_row.pack(fill='x', pady=3)
        ttk.Label(age_row, text="Age:", width=12).pack(side='left')
        self.demo_age_var = tk.StringVar()
        self.demo_age_entry = ttk.Entry(age_row, textvariable=self.demo_age_var, width=10)
        self.demo_age_entry.pack(side='left', padx=5)

        # Gender
        gender_row = ttk.Frame(demo_frame)
        gender_row.pack(fill='x', pady=3)
        ttk.Label(gender_row, text="Gender:", width=12).pack(side='left')
        self.demo_gender_var = tk.StringVar()
        gender_options = ["male", "female", "other", "prefer not to say"]
        self.demo_gender_combo = ttk.Combobox(
            gender_row, textvariable=self.demo_gender_var,
            values=gender_options, width=18, state='readonly'
        )
        self.demo_gender_combo.pack(side='left', padx=5)

        # Handedness
        hand_row = ttk.Frame(demo_frame)
        hand_row.pack(fill='x', pady=3)
        ttk.Label(hand_row, text="Handedness:", width=12).pack(side='left')
        self.demo_hand_var = tk.StringVar()
        hand_options = ["right", "left", "ambidextrous"]
        self.demo_hand_combo = ttk.Combobox(
            hand_row, textvariable=self.demo_hand_var,
            values=hand_options, width=18, state='readonly'
        )
        self.demo_hand_combo.pack(side='left', padx=5)

        # Save Demographics button
        save_row = ttk.Frame(demo_frame)
        save_row.pack(fill='x', pady=(10, 3))
        self.save_demo_btn = ttk.Button(
            save_row, text="Save Demographics",
            command=self._save_demographics, width=20
        )
        self.save_demo_btn.pack(side='left')
        self.demo_status_label = ttk.Label(save_row, text="", foreground='gray')
        self.demo_status_label.pack(side='left', padx=10)

        # Initially disable most controls - only participant selection is enabled
        self._set_initial_disabled_state()

    def _set_initial_disabled_state(self):
        """Set initial state: only participant selection enabled."""
        # Disable everything except participant selection
        self.general_instr_btn['state'] = 'disabled'
        if hasattr(self, "generate_all_btn"):
            self.generate_all_btn["state"] = "normal" if self.run_setup_manifest else "disabled"
        if hasattr(self, "open_session_btn"):
            self.open_session_btn["state"] = "disabled"
        self.block_combo['state'] = 'disabled'
        self.jump_btn['state'] = 'disabled'
        self.play_btn['state'] = 'disabled'
        self.next_btn['state'] = 'disabled'
        self.pause_control_btn['state'] = 'disabled'
        self.stop_btn['state'] = 'disabled'
        self.test_marker_btn['state'] = 'disabled'
        self.bg_music_btn['state'] = 'disabled'
        self.part1_btn['state'] = 'disabled'
        self.part2_btn['state'] = 'disabled'
        # Demographics fields disabled until participant selected
        self.demo_name_entry['state'] = 'disabled'
        self.demo_age_entry['state'] = 'disabled'
        self.demo_gender_combo['state'] = 'disabled'
        self.demo_hand_combo['state'] = 'disabled'
        self.save_demo_btn['state'] = 'disabled'
        # Show guidance
        self.info_label.config(text="Step 1: Select a participant to begin")
        if hasattr(self, "block_order_label"):
            self.block_order_label.config(text="No session prepared.", foreground='gray')

    def _enable_demographics_only(self):
        """Enable demographics section after participant is selected."""
        self.demo_name_entry['state'] = 'normal'
        self.demo_age_entry['state'] = 'normal'
        self.demo_gender_combo['state'] = 'readonly'
        self.demo_hand_combo['state'] = 'readonly'
        self.save_demo_btn['state'] = 'normal'
        # Update guidance
        self.info_label.config(text="Step 2: Fill out demographics and click Save")

    def _enable_all_experiment_controls(self):
        """Enable all experiment controls after demographics are saved."""
        self.general_instr_btn['state'] = 'normal'
        self.bg_music_btn['state'] = 'normal'
        self.part1_btn['state'] = 'normal'
        self.part2_btn['state'] = 'normal'
        if self.participant_id and self.block_files:
            self.block_combo['state'] = 'readonly'
            self.jump_btn['state'] = 'normal'
            self.play_btn['state'] = 'normal'
            self.test_marker_btn['state'] = 'normal'
            self._update_block_display()
        self.info_label.config(text="Ready. Click 'Play Block' or use mouse click to start.")

    def _disable_all_controls(self):
        """Disable all GUI controls during instruction playback."""
        self.general_instr_btn['state'] = 'disabled'
        self.participant_combo['state'] = 'disabled'
        self.block_combo['state'] = 'disabled'
        self.jump_btn['state'] = 'disabled'
        self.play_btn['state'] = 'disabled'
        self.next_btn['state'] = 'disabled'
        self.pause_control_btn['state'] = 'disabled'
        self.stop_btn['state'] = 'disabled'
        self.test_marker_btn['state'] = 'disabled'

    def _enable_controls_after_instruction(self):
        """Re-enable GUI controls after instruction playback."""
        self.participant_combo['state'] = 'readonly'
        # Only re-enable experiment controls if demographics are complete
        if self.demographics_completed:
            self.general_instr_btn['state'] = 'normal'
            if self.participant_id:
                self.block_combo['state'] = 'readonly'
                self.jump_btn['state'] = 'normal'
                self.play_btn['state'] = 'normal'
                self.test_marker_btn['state'] = 'normal'
                self._update_block_display()

    def _play_general_instructions(self):
        """Play general instructions audio, disabling all controls."""
        if self.is_instruction_playing or self.is_playing or not self.audio:
            return

        if not os.path.exists(GENERAL_INSTRUCTIONS):
            messagebox.showerror("Error", f"Instruction file not found:\n{GENERAL_INSTRUCTIONS}")
            return

        self.is_instruction_playing = True
        self._disable_all_controls()
        self.instr_status_label.config(text="Playing instructions...", foreground='green')
        print("Playing General Instructions...")

        # Auto-start background music when audio plays
        self._ensure_background_music_playing()

        def on_complete(success):
            self.root.after(0, self._on_instruction_finished)

        self.audio.play_instruction(GENERAL_INSTRUCTIONS, on_complete)

    def _on_instruction_finished(self):
        """Handle instruction playback completion."""
        self.is_instruction_playing = False
        self._enable_controls_after_instruction()
        self.instr_status_label.config(text="Instructions complete", foreground='gray')
        print("General Instructions finished")

    def _toggle_background_music(self):
        """Toggle background music playback on/off."""
        if not self.audio:
            return

        if self.bg_music_playing:
            # Stop background music
            if self.bg_music_stream:
                try:
                    self.bg_music_stream.stop()
                    self.bg_music_stream.close()
                except Exception:
                    pass
                self.bg_music_stream = None
            self.bg_music_playing = False
            self.bg_music_btn.config(text="Play")
            self.bg_status_label.config(text="Stopped", foreground='gray')
            print("Background music stopped")
        else:
            # Start background music
            if not BACKGROUND_MUSIC:
                self.bg_status_label.config(text="No file configured", foreground='gray')
                return
            if not os.path.exists(BACKGROUND_MUSIC):
                messagebox.showerror("Error", f"Background music not found:\n{BACKGROUND_MUSIC}")
                return

            volume = self.bg_volume_var.get() / 100.0
            self.bg_music_stream = self.audio.start_background_music(BACKGROUND_MUSIC, volume)

            if self.bg_music_stream:
                self.bg_music_playing = True
                self.bg_music_btn.config(text="Stop")
                self.bg_status_label.config(text="Playing", foreground='green')
            else:
                self.bg_status_label.config(text="Error", foreground='red')

    def _ensure_background_music_playing(self):
        """Ensure background music is playing. Called when any audio starts."""
        if self.bg_music_playing:
            return  # Already playing

        if not self.audio:
            return

        if not BACKGROUND_MUSIC:
            return

        if not os.path.exists(BACKGROUND_MUSIC):
            print(f"Warning: Background music not found: {BACKGROUND_MUSIC}")
            return

        # Start background music automatically
        volume = self.bg_volume_var.get() / 100.0
        self.bg_music_stream = self.audio.start_background_music(BACKGROUND_MUSIC, volume)

        if self.bg_music_stream:
            self.bg_music_playing = True
            self.bg_music_btn.config(text="Stop")
            self.bg_status_label.config(text="Playing", foreground='green')
            print("Background music auto-started")

    def _on_volume_change(self, value):
        """Handle background music volume slider change."""
        vol = float(value)
        self.bg_volume_label.config(text=f"{int(vol)}%")

        if self.bg_music_playing and self.audio:
            self.audio.set_background_volume(vol / 100.0)

        # Save the volume setting for next session
        self.settings["volume"] = int(vol)
        save_settings(self.settings)

    def _on_audio_volume_change(self, value):
        """Handle audio channel volume slider change."""
        vol = float(value)
        self.audio_volume_label.config(text=f"{int(vol)}%")

        if self.audio:
            self.audio.audio_volume = vol / 100.0

        # Save the setting for next session
        self.settings["audio_volume"] = int(vol)
        save_settings(self.settings)

    def _on_tactile_volume_change(self, value):
        """Handle tactile channel volume slider change."""
        vol = float(value)
        self.tactile_volume_label.config(text=f"{int(vol)}%")

        if self.audio:
            self.audio.tactile_volume = vol / 100.0

        # Save the setting for next session
        self.settings["tactile_volume"] = int(vol)
        save_settings(self.settings)

    def _test_tactile_stimulus(self):
        """Play the tactile test stimulus on the active tactile output only."""
        if not os.path.exists(TACTILE_TEST_STIMULUS):
            messagebox.showerror("Error", f"Tactile test file not found:\n{TACTILE_TEST_STIMULUS}")
            return

        def play_tactile():
            try:
                data, sr = sf.read(TACTILE_TEST_STIMULUS, dtype='float32')
                output_channels = self.audio.runtime_output_channels if self.audio else 2
                tactile_channel = self.audio.tactile_output_channel if self.audio else None
                probe = tactile_probe_for_output(
                    data,
                    output_channels,
                    1.0,
                    tactile_channel=tactile_channel,
                    duplicate_tactile_channel=self.audio._duplicate_tactile_channel() if self.audio else None,
                )
                device_idx = self.audio.device_idx if self.audio else None

                if self.audio and self.audio._persistent_output_available(samplerate=sr, channels=probe.shape[1]):
                    self.audio.stop_flag = False
                    self.audio.paused = False
                    self.audio._block_finished.clear()
                    with self.audio._block_lock:
                        self.audio._block_data = probe
                        self.audio._block_sr = sr
                        self.audio._block_pos = 0
                    while not self.audio._block_finished.is_set() and not self.audio.stop_flag:
                        time.sleep(0.01)
                    with self.audio._block_lock:
                        self.audio._block_data = None
                    output_label = (tactile_channel if tactile_channel is not None else tactile_output_channel_for_channels(probe.shape[1])) + 1
                    print(f"DEBUG: Playing tactile test stimulus on Output {output_label}")
                    return

                if self.audio:
                    self.audio._close_persistent_output()

                try:
                    stream = sd.OutputStream(
                        samplerate=sr,
                        channels=probe.shape[1],
                        dtype='float32',
                        device=device_idx,
                        latency=STREAM_LATENCY,
                        blocksize=AUDIO_BLOCKSIZE,
                        extra_settings=output_extra_settings_for_device(device_idx, probe.shape[1]),
                    )
                except Exception:
                    if self.audio and probe.shape[1] == 3 and self.audio._promote_runtime_to_four_channels():
                        tactile_channel = self.audio.tactile_output_channel
                        probe = tactile_probe_for_output(
                            data,
                            self.audio.runtime_output_channels,
                            self.audio.tactile_volume,
                            tactile_channel=tactile_channel,
                            duplicate_tactile_channel=self.audio._duplicate_tactile_channel(),
                        )
                        stream = sd.OutputStream(
                            samplerate=sr,
                            channels=probe.shape[1],
                            dtype='float32',
                            device=device_idx,
                            latency=STREAM_LATENCY,
                            blocksize=AUDIO_BLOCKSIZE,
                            extra_settings=output_extra_settings_for_device(device_idx, probe.shape[1]),
                        )
                    else:
                        raise

                with stream:
                    stream.write(
                        apply_output_volumes(
                            probe,
                            1.0,
                            self.audio.tactile_volume if self.audio else 1.0,
                            tactile_channel=tactile_channel,
                            duplicate_tactile_channel=self.audio._duplicate_tactile_channel() if self.audio else None,
                        )
                    )
                output_label = (tactile_channel if tactile_channel is not None else tactile_output_channel_for_channels(probe.shape[1])) + 1
                print(f"DEBUG: Playing tactile test stimulus on Output {output_label}")
            except Exception as e:
                print(f"ERROR: Could not play tactile test: {e}")
            finally:
                if self.audio:
                    self.audio._restart_persistent_output()

        # Play in background thread to not block UI
        threading.Thread(target=play_tactile, daemon=True).start()

    def _save_demographics(self):
        """Save demographics data for the current participant."""
        if not self.participant_id:
            messagebox.showwarning("Warning", "Please select a participant first.")
            return

        # Collect demographics data
        demographics = {
            "name": self.demo_name_var.get().strip(),
            "age": self.demo_age_var.get().strip(),
            "gender": self.demo_gender_var.get(),
            "handedness": self.demo_hand_var.get()
        }

        # Validate - at least some data should be entered
        if not any([demographics["name"], demographics["age"],
                    demographics["gender"], demographics["handedness"]]):
            messagebox.showwarning("Warning", "Please enter at least some demographic data.")
            return

        # Save the demographics
        if save_demographics(self.participant_id, demographics):
            self.demo_status_label.config(text="Saved", foreground='green')
            self.demographics_completed = True
            # Enable all experiment controls now that demographics are complete
            self._enable_all_experiment_controls()
            # Start mouse listener now
            self._start_mouse_listener()
            # Clear status after 3 seconds
            self.root.after(3000, lambda: self.demo_status_label.config(text=""))
        else:
            self.demo_status_label.config(text="Save failed", foreground='red')

    def _load_demographics_for_participant(self, participant_id):
        """Load and display demographics for a participant if they exist."""
        demographics = load_demographics(participant_id)
        if demographics:
            self.demo_name_var.set(demographics.get("name", ""))
            self.demo_age_var.set(demographics.get("age", ""))
            self.demo_gender_var.set(demographics.get("gender", ""))
            self.demo_hand_var.set(demographics.get("handedness", ""))
            self.demo_status_label.config(text="(Loaded existing data)", foreground='blue')
            # Check if demographics are sufficiently filled in (at least one field)
            if any([demographics.get("name"), demographics.get("age"),
                    demographics.get("gender"), demographics.get("handedness")]):
                self.demographics_completed = True
            # Clear status after 3 seconds
            self.root.after(3000, lambda: self.demo_status_label.config(text=""))
        else:
            # Clear fields for new participant
            self.demo_name_var.set("")
            self.demo_age_var.set("")
            self.demo_gender_var.set("")
            self.demo_hand_var.set("")
            self.demo_status_label.config(text="")
            self.demographics_completed = False

    def _on_participant_selected(self, event=None):
        """Handle participant selection."""
        pid = self.participant_var.get()
        if not pid:
            return

        if self.run_setup_manifest:
            self._prepare_segment_participant(pid)
            return

        self.current_run_package = None
        self.run_event_logger = None
        self.run_events = None
        self._run_block_by_path = {}
        self._session_outputs_written = False

        folder = os.path.join(STIMULI_DIR, pid)
        if not os.path.exists(folder):
            messagebox.showerror("Error", f"Folder not found: {folder}")
            return

        # Find block files. Newer study exports may use Part1/Part2 subfolders;
        # the public generator writes the classic flat Pxx folder by default.
        part1_folder = os.path.join(folder, "Part1")
        part2_folder = os.path.join(folder, "Part2")

        self.part1_files = self._find_block_files(part1_folder)
        self.part2_files = self._find_block_files(part2_folder)
        if not self.part1_files:
            self.part1_files = self._find_block_files(folder)

        # Check Part1 files
        missing1 = [i+1 for i, f in enumerate(self.part1_files) if f is None] if self.part1_files else []
        if not self.part1_files or missing1:
            messagebox.showerror("Error", f"Missing Part1 block files for {pid}: {missing1 if missing1 else 'No files found'}")
            return

        # Check Part2 files (optional warning if missing)
        missing2 = [i+1 for i, f in enumerate(self.part2_files) if f is None] if self.part2_files else []
        if not self.part2_files or missing2:
            print(f"Warning: Part2 blocks incomplete for {pid}: {missing2 if missing2 else 'No files found'}")

        # Set state - start with Part 1
        self.participant_id = pid
        self.participant_folder = folder
        self.current_part = 1
        self.block_files = self.part1_files
        self.current_block = 0

        # Update display
        self.status_label.config(text=f"OK {pid} loaded", foreground='green')
        if hasattr(self, "open_session_btn"):
            self.open_session_btn["state"] = "normal"
        if hasattr(self, "block_order_label"):
            self.block_order_label.config(text=self._format_block_order_summary(), foreground='gray')
        self._update_block_display()
        self._update_part_display()

        # Load demographics if they exist for this participant
        # This also checks if demographics are complete
        self._load_demographics_for_participant(pid)

        # Enable demographics section (Step 2)
        self._enable_demographics_only()

        # If demographics were previously saved, enable all controls
        if self.demographics_completed:
            self._enable_all_experiment_controls()
            # Start mouse listener only when experiment controls are available
            self._start_mouse_listener()

        print(f"Selected participant: {pid} (path: {folder})")
        print(f"  Part1: {len(self.part1_files)} blocks, Part2: {len(self.part2_files)} blocks")

    def _prepare_segment_participant(self, pid):
        """Generate/load one participant session from the Segment 5/6 dashboard manifests."""
        try:
            package = prepare_segment_run_package(
                Path(self.run_setup_manifest),
                pid,
                session_root=Path(SESSION_ROOT),
            )
        except Exception as exc:
            messagebox.showerror("Session Prepare Error", str(exc))
            self.status_label.config(text="Prepare failed", foreground='red')
            return

        self.current_run_package = package
        self.participant_id = package.participant_id
        self.participant_folder = str(package.session_dir)
        self._run_block_by_path = {str(block.wav_path.resolve()): block for block in package.blocks}
        self._initialize_segment_event_logging()
        self.current_part = 1
        self.current_block = 0
        self.part1_files = [
            str(block.wav_path)
            for block in package.blocks
            if str(block.metadata.get("phase") or "single").lower() in {"single", "pre"}
        ]
        self.part2_files = [
            str(block.wav_path)
            for block in package.blocks
            if str(block.metadata.get("phase") or "").lower() == "post"
        ]
        self.block_files = self.part1_files
        missing1 = [i + 1 for i, path in enumerate(self.part1_files) if not os.path.exists(path)]
        if not self.part1_files or missing1:
            messagebox.showerror("Error", f"Prepared Part1 block files are missing: {missing1 if missing1 else 'No files found'}")
            return

        self.status_label.config(text=f"OK {pid} prepared", foreground='green')
        if hasattr(self, "open_session_btn"):
            self.open_session_btn["state"] = "normal"
        if hasattr(self, "block_order_label"):
            self.block_order_label.config(text=self._format_block_order_summary(), foreground='gray')
        self._update_block_display()
        self._update_part_display()
        self._load_demographics_for_participant(package.participant_id)
        self._enable_demographics_only()
        if self.demographics_completed:
            self._enable_all_experiment_controls()
            self._start_mouse_listener()
        self.info_label.config(text=f"Session ready: {package.session_dir.name}")
        print(f"Prepared participant session: {package.manifest_path}")
        print(f"  Part1: {len(self.part1_files)} blocks, Part2: {len(self.part2_files)} blocks")

    def _generate_all_participant_sessions(self):
        """Generate every participant session from Segment 6 on demand."""
        if not self.run_setup_manifest:
            messagebox.showwarning("No Segment 6 Setup", "Open the runner from a prepared dashboard setup first.")
            return
        self.generate_all_btn["state"] = "disabled"
        self.status_label.config(text="Generating all...", foreground='blue')

        def worker():
            try:
                packages = prepare_all_segment_run_packages(
                    Path(self.run_setup_manifest),
                    session_root=Path(SESSION_ROOT),
                )
                self.root.after(
                    0,
                    lambda: self._on_generate_all_finished(packages=packages, error=None),
                )
            except Exception as exc:
                self.root.after(
                    0,
                    lambda exc=exc: self._on_generate_all_finished(packages=[], error=exc),
                )

        threading.Thread(target=worker, daemon=True).start()

    def _on_generate_all_finished(self, *, packages, error):
        self.generate_all_btn["state"] = "normal" if self.run_setup_manifest else "disabled"
        if error is not None:
            self.status_label.config(text="Bulk generation failed", foreground='red')
            messagebox.showerror("Bulk Generation Error", str(error))
            return
        self.status_label.config(text=f"Generated {len(packages)} sessions", foreground='green')
        if packages:
            self.info_label.config(text=f"Generated sessions under {packages[0].session_dir.parent}")
    
    def _update_block_display(self):
        """Update block counter display."""
        total_blocks = len(self.block_files)
        self.block_display.config(text=f"Block: {self.current_block + 1} / {total_blocks}")
        self.block_var.set(str(self.current_block + 1))
        self.progress_bar['value'] = 0

        # Get duration of current block WAV file
        if self.block_files and self.current_block < len(self.block_files):
            block_path = self.block_files[self.current_block]
            if block_path and os.path.exists(block_path):
                self.current_block_duration = self._get_wav_duration(block_path)
            else:
                self.current_block_duration = DEFAULT_BLOCK_DURATION

        # Update time display and progress bar max
        dur_mins = int(self.current_block_duration) // 60
        dur_secs = int(self.current_block_duration) % 60
        self.time_label.config(text=f"0:00 / {dur_mins}:{dur_secs:02d}")
        self.progress_bar['maximum'] = self.current_block_duration

        # Update block combobox values based on current part
        self.block_combo['values'] = [str(i+1) for i in range(total_blocks)]

        # Next button state
        self.next_btn['state'] = 'normal' if self.current_block < total_blocks - 1 and not self.is_playing else 'disabled'

    def _update_part_display(self):
        """Update the Part button styles based on current_part."""
        if self.current_part == 1:
            # Part 1 active (bright green), Part 2 inactive (gray)
            self.part1_btn.config(
                bg='#00FF88', fg='#000000',
                relief='raised', bd=3
            )
            self.part2_btn.config(
                bg='#555555', fg='#888888',
                relief='sunken', bd=3
            )
        else:
            # Part 2 active (white), Part 1 inactive (gray)
            self.part1_btn.config(
                bg='#555555', fg='#888888',
                relief='sunken', bd=3
            )
            self.part2_btn.config(
                bg='#FFFFFF', fg='#000000',
                relief='raised', bd=3
            )

    def _switch_to_part(self, part_num):
        """Manually switch to Part 1 or Part 2."""
        if self.is_playing:
            messagebox.showwarning("Cannot Switch", "Cannot switch parts while playing. Stop playback first.")
            return

        if not self.participant_var.get():
            messagebox.showwarning("No Participant", "Please select a participant first.")
            return

        # Check if requested part has files
        if part_num == 1 and not self.part1_files:
            messagebox.showwarning("No Files", "No Part 1 files found for this participant.")
            return
        if part_num == 2 and not self.part2_files:
            messagebox.showwarning("No Files", "No Part 2 files found for this participant.")
            return

        # Switch to the requested part
        self.current_part = part_num
        self.current_block = 0

        if part_num == 1:
            self.block_files = self.part1_files
        else:
            self.block_files = self.part2_files

        self._update_part_display()
        self._update_block_display()
        if hasattr(self, "block_order_label"):
            self.block_order_label.config(text=self._format_block_order_summary(), foreground='gray')
        print(f"Manually switched to Part {part_num}")

    def _jump_to_block(self):
        """Jump to selected block."""
        if self.is_playing:
            return
        try:
            block_num = int(self.block_var.get())
            total_blocks = len(self.block_files)
            if 1 <= block_num <= total_blocks:
                self.current_block = block_num - 1
                self._update_block_display()
                print(f"Switched to block {block_num} manually")
        except ValueError:
            pass
    
    def _next_block(self):
        """Advance to next block."""
        total_blocks = len(self.block_files)
        if self.is_playing or self.current_block >= total_blocks - 1:
            return
        self.current_block += 1
        self._update_block_display()
    
    def _play_block(self):
        """Start playing current block (with pre-block instruction first)."""
        if self.is_playing or self.is_instruction_playing or not self.audio or not self.block_files:
            return

        block_path = self.block_files[self.current_block]
        block_num = self.current_block + 1

        if not os.path.exists(block_path):
            messagebox.showerror("Error", f"Block file not found: {block_path}")
            return

        # Disable all controls during block sequence
        self._disable_all_controls()
        self.general_instr_btn['state'] = 'disabled'
        self.awaiting_click_to_start = False

        # Auto-start background music when audio plays
        self._ensure_background_music_playing()

        # First play pre-block instruction
        if os.path.exists(PRE_BLOCK_INSTRUCTIONS):
            self.is_instruction_playing = True
            self.info_label.config(text=f"Playing pre-block instruction for Block {block_num}...")
            print(f"Playing Pre-Block Instruction for block {block_num}")

            def on_pre_block_complete(success):
                self.root.after(0, lambda: self._start_actual_block_playback(block_path, block_num))

            self.audio.play_instruction(PRE_BLOCK_INSTRUCTIONS, on_pre_block_complete)
        else:
            # No pre-block instruction, start block directly
            self._start_actual_block_playback(block_path, block_num)

    def _start_actual_block_playback(self, block_path, block_num):
        """Start the actual block audio playback (after pre-block instruction).

        Also starts local digital output evidence recording if enabled.
        """
        # Stop any existing recentering (from awaiting click phase) before starting fresh
        self._stop_recentering()

        self.is_instruction_playing = False
        self.is_playing = True
        self.is_paused = False
        self._operator_stop_requested = False
        self.awaiting_click_to_start = False  # Clear the awaiting state

        # Update UI
        self.click_target.set_active(True)
        self.pause_label.config(text="")
        self.pause_control_btn['state'] = 'normal'
        self.stop_btn['state'] = 'normal'
        self.test_marker_btn['state'] = 'normal'

        # Prepare recording path
        recording_enabled = (self._capture_options().start_backup_recording
                            and PYAUDIOWPATCH_AVAILABLE and ENABLE_LOOPBACK_RECORDING
                            and self.audio is not None)
        recording_path = None
        self._active_run_block = self._find_run_block_for_path(block_path)
        self._active_planned_logged = False
        self._accepting_segment_responses = False
        self._active_block_start_unix = time.time()
        self._active_block_start_monotonic = time.perf_counter()
        block_event_schedule = None
        if self.run_events is not None and self._active_run_block is not None:
            block_event_schedule = self.block_schedules.get(self._active_run_block.index)
            self.run_events.log(
                "block_start",
                unix_time=self._active_block_start_unix,
                monotonic_time=self._active_block_start_monotonic,
                block_number=self._active_run_block.index,
                block_index=self._active_run_block.index,
                block_label=self._active_run_block.label,
                block_path=str(self._active_run_block.wav_path),
                trial_count=self._active_run_block.trial_count,
                **self._segment_event_metadata(self._active_run_block),
            )
            if block_event_schedule is not None:
                self.run_events.log(
                    "block_schedule_loaded",
                    block_number=self._active_run_block.index,
                    block_index=self._active_run_block.index,
                    block_label=self._active_run_block.label,
                    block_path=str(self._active_run_block.wav_path),
                    manifest_path=str(self._active_run_block.manifest_path),
                    scheduled_event_count=len(block_event_schedule),
                )

        if recording_enabled:
            # Get the original block filename for metadata
            block_filename = os.path.basename(block_path)
            block_name = os.path.splitext(block_filename)[0]

            # Create local audio-evidence filename with full metadata.
            recording_filename = f"{self.participant_id}_Part{self.current_part}_Block{block_num}_{block_name}_audio_evidence.wav"

            # Create participant subfolder in recordings directory
            participant_recordings_dir = os.path.join(RECORDINGS_DIR, self.participant_id)
            recording_path = os.path.join(participant_recordings_dir, recording_filename)

            self.info_label.config(text=f"Playing Block {block_num}... (Recording)")
        else:
            self.info_label.config(text=f"Playing Block {block_num}...")

        # Bring window to front
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after(100, lambda: self.root.attributes('-topmost', False))

        # Start fresh recentering for the new block
        self._start_recentering()

        print(f"Starting block {block_num} for participant {self.participant_id}")
        if recording_path:
            print(f"Recording to: {recording_path}")

        # Play in thread with recording
        def play_thread():
            # Start recording BEFORE playback (with small pre-buffer)
            # Pass recording_path so it's stored for interrupted saves
            if recording_enabled:
                print("Starting digital output evidence recording...")
                if not self.audio.start_recording(output_path=recording_path):
                    print("WARNING: Failed to start recording, continuing without it")
                else:
                    # Small delay to ensure the output evidence tap is active.
                    time.sleep(RECORDING_PRE_BUFFER_SEC)

            def on_progress(elapsed):
                self.root.after(0, lambda: self._update_progress(elapsed))

            success = self.audio.play_block(
                block_path,
                progress_callback=on_progress,
                audio_event_callback=self._handle_segment_audio_event if self._active_run_block is not None else None,
                block_event_schedule=block_event_schedule,
            )
            if self.run_events is not None:
                self.run_events.flush_callback_events()
            self._fallback_segment_planned_events_if_needed()

            # Stop recording AFTER playback and save (only if still recording)
            # Note: If user stopped early, stop() already called stop_recording(interrupted=True)
            if recording_enabled and self.audio.is_recording():
                print("Stopping digital output evidence recording (complete)...")
                self.audio.stop_recording(recording_path, interrupted=False)

            if self.run_events is not None and self._active_run_block is not None:
                self.run_events.log(
                    "block_end",
                    block_number=self._active_run_block.index,
                    block_label=self._active_run_block.label,
                    completed=bool(success),
                )
            self._accepting_segment_responses = False
            self._active_run_block = None
            self.root.after(0, lambda: self._on_block_finished(success))

        threading.Thread(target=play_thread, daemon=True).start()
    
    def _update_progress(self, elapsed):
        """Update progress bar and time display."""
        if not self.is_playing:
            return

        mins = int(elapsed) // 60
        secs = int(elapsed) % 60
        dur_mins = int(self.current_block_duration) // 60
        dur_secs = int(self.current_block_duration) % 60
        self.time_label.config(text=f"{mins}:{secs:02d} / {dur_mins}:{dur_secs:02d}")
        self.progress_bar['value'] = min(elapsed, self.current_block_duration)
    
    def _on_block_finished(self, success):
        """Handle block playback completion - plays post-block instruction."""
        # Don't stop recentering here - keep it active until next block starts
        # Recentering will continue during "awaiting click" phase

        self.is_playing = False
        self.is_paused = False
        self.pause_label.config(text="")
        self.pause_control_btn['state'] = 'disabled'
        self.stop_btn['state'] = 'disabled'

        block_num = self.current_block + 1
        print(f"Finished block {block_num}")

        if not success or self._operator_stop_requested:
            self._operator_stop_requested = False
            self._stop_recentering()
            self._stop_mouse_lock()
            self.awaiting_click_to_start = False
            self.click_target.set_active(False)
            self.info_label.config(text=f"Block {block_num} stopped. Press 'Play Block' to restart it.")
            self._enable_controls_after_instruction()
            return

        # Play post-block instruction
        if os.path.exists(POST_BLOCK_INSTRUCTIONS):
            self.is_instruction_playing = True
            self.info_label.config(text=f"Playing post-block instruction...")
            print(f"Playing Post-Block Instruction for block {block_num}")

            def on_post_block_complete(success):
                self.root.after(0, lambda: self._on_post_block_instruction_finished(block_num))

            self.audio.play_instruction(POST_BLOCK_INSTRUCTIONS, on_post_block_complete)
        else:
            # No post-block instruction
            self._on_post_block_instruction_finished(block_num)

    def _on_post_block_instruction_finished(self, finished_block_num):
        """Handle post-block instruction completion - set up click-to-start or switch parts."""
        self.is_instruction_playing = False
        self.click_target.set_active(False)

        total_blocks = len(self.block_files)

        # Check if there are more blocks in current part
        if self.current_block < total_blocks - 1:
            self.current_block += 1
            self._update_block_display()

            # Set up click-to-start-next-block
            self.awaiting_click_to_start = True
            self.click_target.set_active(True)
            self.info_label.config(text=f"Block {finished_block_num} complete. CLICK to start Block {self.current_block + 1}")

            # Move once for the next start click. Never pin or lock the cursor.
            self._do_recenter()

            # Keep controls disabled - click will start next block
            print(f"Awaiting click to start block {self.current_block + 1}")

        elif self.current_part == 1 and self.part2_files:
            # Part 1 complete - play interim message then switch to Part 2
            self.info_label.config(text="Part 1 complete! Playing interim message...")
            print("Playing Interim Message...")

            def on_interim_complete(success):
                self.root.after(0, self._on_interim_message_finished)

            if self.audio and os.path.exists(INTERIM_MESSAGE):
                self.is_instruction_playing = True
                self.audio.play_instruction(INTERIM_MESSAGE, on_interim_complete)
            else:
                print(f"Warning: Interim message not found: {INTERIM_MESSAGE}")
                self._on_interim_message_finished()

        else:
            # Part 2 complete (or Part 1 complete with no Part 2) - play finish message
            self.info_label.config(text="All blocks complete! Playing finish message...")
            print("Playing Finish Message...")

            def on_finish_complete(success):
                self.root.after(0, self._on_finish_message_finished)

            if self.audio and os.path.exists(FINISH_MESSAGE):
                self.is_instruction_playing = True
                self.audio.play_instruction(FINISH_MESSAGE, on_finish_complete)
            else:
                print(f"Warning: Finish message not found: {FINISH_MESSAGE}")
                self._on_finish_message_finished()

    def _on_interim_message_finished(self):
        """Handle interim message completion - switch to Part 2."""
        self.is_instruction_playing = False
        self._stop_recentering()  # Stop recentering - Part 2 requires Play Block button

        # Switch to Part 2
        self.current_part = 2
        self.block_files = self.part2_files
        self.current_block = 0
        self._update_part_display()
        self._update_block_display()

        # Do NOT set awaiting_click_to_start - require Play Block button instead
        self.awaiting_click_to_start = False
        self.click_target.set_active(False)
        self.info_label.config(text="Part 2 ready. Press 'Play Block' to start Block 1")

        # Enable controls so user can press Play Block button
        self._enable_controls_after_instruction()

        print("Switched to Part 2 - press Play Block button to start")

    def _on_finish_message_finished(self):
        """Handle finish message completion - experiment complete."""
        self.is_instruction_playing = False
        self._stop_recentering()  # Stop recentering - experiment is complete

        part_text = "Part 2" if self.current_part == 2 else "Part 1"
        self.info_label.config(text=f"Experiment complete! ({part_text} finished)")
        self.click_target.set_active(False)
        self.awaiting_click_to_start = False
        self._enable_controls_after_instruction()
        self.next_btn['state'] = 'disabled'
        self.play_btn['state'] = 'disabled'
        self._write_segment_event_outputs(completed=True, interrupted=False)
        print(f"Experiment complete! ({part_text})")
    
    def _toggle_pause(self):
        """Toggle pause/resume (Ctrl+Alt+P handler)."""
        if not self.is_playing:
            return
        
        block_num = self.current_block + 1
        elapsed = self.audio.elapsed_time if self.audio else 0
        
        if self.is_paused:
            # Resume
            self.is_paused = False
            self.audio.resume()
            self._resume_recentering()
            self.pause_label.config(text="")
            print(f"Resumed block {block_num} at t = {elapsed:.1f}s")
        else:
            # Pause
            self.is_paused = True
            self.audio.pause()
            self._pause_recentering()
            self.pause_label.config(text="PAUSED")
            print(f"Paused block {block_num} at t = {elapsed:.1f}s")

    def _stop_current_block(self):
        """Stop current block playback and return controls to the operator."""
        if not self.audio or not (self.is_playing or self.is_instruction_playing):
            return
        self._operator_stop_requested = True
        if self.run_events is not None:
            self.run_events.log(
                "operator_stop",
                block_number=self._active_run_block.index if self._active_run_block else "",
                block_label=self._active_run_block.label if self._active_run_block else "",
            )
        self.info_label.config(text="Stopping current block...")
        self.audio.stop()

    def _send_test_marker(self):
        """Send a visible operator test marker and tactile marker pulse."""
        marker_metadata = None
        if self.run_events is not None:
            event = self.run_events.log(
                "test_marker",
                block_number=self._active_run_block.index if self._active_run_block else "",
                block_index=self._active_run_block.index if self._active_run_block else "",
                block_label=self._active_run_block.label if self._active_run_block else "",
                during_playback=bool(self.is_playing),
            )
            marker_metadata = {
                "mouse_event_id": event.event_id,
                "mouse_event_unix_time": event.unix_time,
                "mouse_event_monotonic_time": event.monotonic_time,
                "operator_marker": True,
            }
            self._set_event_stream_status("Event stream: test_marker logged")
        if self.audio:
            self.audio.trigger_click(metadata=marker_metadata, marker_gain=RESPONSE_MARKER_GAIN if marker_metadata else None)
        self.info_label.config(text="Test marker sent.")
    
    # -------------------------------------------------------------------------
    # Mouse Recentering
    # -------------------------------------------------------------------------
    def _start_recentering(self):
        """Start the recentering schedule: 4s, then every 8s."""
        self._stop_recentering()
        # Reset the next recenter time to RECENTER_START for each new block
        self.next_recenter_time = RECENTER_START
        self.recentering_active = True
        print(f"Recentering started for block {self.current_block + 1} (first at {RECENTER_START}s, then every {RECENTER_INTERVAL}s)")
        self._schedule_recenter()

    def _schedule_recenter(self):
        """Schedule next recenter check."""
        if not self.is_playing or not self.recentering_active:
            return

        # Check every 100ms
        self.recenter_timer = self.root.after(100, self._check_recenter)

    def _check_recenter(self):
        """Check if it's time to recenter."""
        if not self.is_playing or not self.recentering_active:
            return

        if self.is_paused:
            # While paused, just keep checking
            self._schedule_recenter()
            return

        elapsed = self.audio.elapsed_time if self.audio else 0

        if elapsed >= self.next_recenter_time:
            self._do_recenter()
            print(f"  Recentered at t={elapsed:.1f}s (next at {self.next_recenter_time + RECENTER_INTERVAL:.0f}s)")
            self.next_recenter_time += RECENTER_INTERVAL

        if elapsed < self.current_block_duration:
            self._schedule_recenter()

    def _do_recenter(self):
        """Move mouse to center of click target and bring window to front."""
        # Always bring window to front forcefully
        try:
            self.root.lift()
            self.root.focus_force()
            self.root.attributes('-topmost', True)
            self.root.after(200, lambda: self.root.attributes('-topmost', False))
        except Exception:
            pass

        # Move mouse to click target center
        if not PYAUTOGUI_AVAILABLE:
            return
        try:
            x, y = self.click_target.get_center_coords()
            pyautogui.moveTo(x, y, duration=0.05)
        except Exception as e:
            print(f"  Warning: Could not move mouse: {e}")

    def _pause_recentering(self):
        """Temporarily pause recentering."""
        if self.recenter_timer:
            self.root.after_cancel(self.recenter_timer)
            self.recenter_timer = None

    def _resume_recentering(self):
        """Resume recentering after pause."""
        self._schedule_recenter()

    def _stop_recentering(self):
        """Stop recentering completely."""
        self.recentering_active = False
        if self.recenter_timer:
            self.root.after_cancel(self.recenter_timer)
            self.recenter_timer = None
        if self.is_playing:
            print(f"Recentering stopped for block {self.current_block + 1}")

    # -------------------------------------------------------------------------
    # Deprecated Mouse Lock Guard
    # -------------------------------------------------------------------------
    def _start_mouse_lock(self):
        """Deprecated no-op: never pin the cursor to the click target."""
        self._stop_mouse_lock()

    def _do_mouse_lock(self):
        """Deprecated no-op retained for old validation imports."""
        self._stop_mouse_lock()

    def _stop_mouse_lock(self):
        """Clear any stale mouse-lock timer without moving the cursor."""
        self.mouse_locked = False
        if self._mouse_lock_timer:
            self.root.after_cancel(self._mouse_lock_timer)
            self._mouse_lock_timer = None

    # -------------------------------------------------------------------------
    # Mouse Listener (for click feedback and click-to-start)
    # -------------------------------------------------------------------------
    def _start_mouse_listener(self):
        """Start listening for mouse clicks."""
        if not PYNPUT_AVAILABLE or self.mouse_listener:
            return

        def on_click(x, y, button, pressed):
            if not pressed:
                return

            # Check if click is within click target area
            click_in_target = self._is_click_in_target(x, y)
            response_metadata = self._record_segment_mouse_click(x, y, in_target=click_in_target)

            # Always play click tone for any click (zero-lag feedback)
            if self.audio:
                if response_metadata:
                    deferred_event = response_metadata.pop("_deferred_lsl_event", None)
                    self.audio.trigger_click(metadata=response_metadata, marker_gain=RESPONSE_MARKER_GAIN)
                    if deferred_event is not None and self.run_events is not None:
                        self.run_events.push_deferred_event_marker(deferred_event)
                else:
                    self.audio.trigger_click()
                if click_in_target:
                    self.root.after(0, self.click_target.flash)

            # If awaiting click to start next block
            if self.awaiting_click_to_start and click_in_target:
                self.root.after(0, self._on_click_to_start)

        self.mouse_listener = mouse.Listener(on_click=on_click)
        self.mouse_listener.start()

    def _is_click_in_target(self, x, y):
        """Check if screen coordinates are within the click target area."""
        try:
            # pynput reports OS mouse coordinates. On DPI-scaled Windows
            # desktops, Tk widget positions can be logical coordinates, so use
            # the ClickTarget's DPI-adjusted bounds and keep the unscaled check
            # as a fallback for non-scaled or DPI-aware environments.
            mx1, my1, mx2, my2 = self.click_target.get_mouse_bounds()
            if mx1 <= x <= mx2 and my1 <= y <= my2:
                return True
            tx = self.click_target.winfo_rootx()
            ty = self.click_target.winfo_rooty()
            tw = self.click_target.winfo_width()
            th = self.click_target.winfo_height()
            return tx <= x <= tx + tw and ty <= y <= ty + th
        except Exception:
            return False

    def _on_click_to_start(self):
        """Handle click to start next block."""
        if not self.awaiting_click_to_start:
            return

        self.awaiting_click_to_start = False
        self._stop_mouse_lock()  # Release mouse lock when starting next block
        self.click_target.flash()
        print(f"Click detected - starting block {self.current_block + 1}")

        # Start the next block
        self._play_block()
    
    # -------------------------------------------------------------------------
    # Keyboard Shortcut (Ctrl+Alt+P)
    # -------------------------------------------------------------------------
    def _setup_keyboard_listener(self):
        """Setup global keyboard listener for Ctrl+Alt+P."""
        if not PYNPUT_AVAILABLE:
            print("WARNING: pynput not available, Ctrl+Alt+P shortcut disabled")
            return
        
        current_keys = set()
        
        def on_press(key):
            current_keys.add(key)
            # Check for Ctrl+Alt+P
            ctrl = keyboard.Key.ctrl_l in current_keys or keyboard.Key.ctrl_r in current_keys
            alt = keyboard.Key.alt_l in current_keys or keyboard.Key.alt_r in current_keys or keyboard.Key.alt_gr in current_keys
            try:
                p_pressed = hasattr(key, 'char') and key.char and key.char.lower() == 'p'
            except AttributeError:
                p_pressed = False
            
            if ctrl and alt and p_pressed:
                self.root.after(0, self._toggle_pause)
        
        def on_release(key):
            current_keys.discard(key)
        
        self.keyboard_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.keyboard_listener.start()
    
    # -------------------------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------------------------
    def _on_close(self):
        """Clean up on window close."""
        self._write_segment_event_outputs(completed=False, interrupted=bool(self.run_event_logger and not self._session_outputs_written))
        # Stop background music
        if self.bg_music_stream:
            try:
                self.bg_music_stream.stop()
                self.bg_music_stream.close()
            except Exception:
                pass
        self._stop_mouse_lock()  # Stop mouse lock if active
        if self.audio:
            self.audio.shutdown()  # Full shutdown including click stream
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()
        self.root.destroy()


# =============================================================================
# MAIN
# =============================================================================
def main(argv=None):
    _ = build_arg_parser().parse_args(argv)
    print(
        "The legacy Tk participant runner has been retired as a public entry point.\n"
        "Use the active packaged experiment runner: "
        "`dist\\PPSExperimentRunner\\PPSExperimentRunner.exe` or `windows\\Launch_Experiment_Runner.bat`."
    )
    print("For device checks, use `pps-audio-stress --dry-run --device-query Komplete`.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

