"""
PPS Breathing Experiment Runner - With WASAPI Loopback Recording
=================================================================
- Sequential block playback (1-6) with manual override
- Fixed audio routing: RIGHT channel â†’ Output 1 (Audio), LEFT channel â†’ Output 2 (Tactile)
- Low-latency mouse click tone (tactile only)
- Dedicated click area with 8-second recentering
- Global pause/resume: Ctrl+Alt+P
- WASAPI loopback recording of each block for verification
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import re
import threading
import time
import json
import ctypes
import argparse
from pathlib import Path

# Try to import pyaudiowpatch for WASAPI loopback recording
try:
    import pyaudiowpatch as pyaudio_wp
    PYAUDIOWPATCH_AVAILABLE = True
    print("pyaudiowpatch imported successfully - WASAPI loopback recording available")
except ImportError as e:
    print(f"WARNING: pyaudiowpatch not available: {e}")
    print("  Install with: pip install pyaudiowpatch")
    PYAUDIOWPATCH_AVAILABLE = False

# =============================================================================
# AUDIO PRIORITY AND PERFORMANCE SETTINGS
# =============================================================================
# Try to set process priority to high for better audio timing
try:
    import sys
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
REPO_ROOT = Path(__file__).resolve().parents[2]
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


def configure_runtime_paths(args):
    """Apply CLI path overrides before constructing the Tk app."""
    global STIMULI_DIR, CLICK_SOUND, INSTRUCTIONS_DIR, GENERAL_INSTRUCTIONS
    global PRE_BLOCK_INSTRUCTIONS, POST_BLOCK_INSTRUCTIONS, BACKGROUND_MUSIC
    global INTERIM_MESSAGE, FINISH_MESSAGE, TACTILE_TEST_STIMULUS
    global SETTINGS_FILE, DEMOGRAPHICS_DIR, RECORDINGS_DIR

    if args.stimuli_dir:
        STIMULI_DIR = str(args.stimuli_dir)
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


def build_arg_parser():
    parser = argparse.ArgumentParser(description="Launch the Windows PPS experiment app.")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit.")
    parser.add_argument("--stimuli-dir", type=Path, help="Participant sequence directory.")
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
AUDIO_BLOCKSIZE = 2048      # Samples per callback (was 1024)
AUDIO_BUFFERSIZE = 4        # Number of buffers to queue

# Latency settings for sounddevice streams
# 'low' = minimum latency, 'high' = maximum stability
# Numeric value = target latency in seconds (e.g., 0.1 = 100ms)
STREAM_LATENCY = 0.05       # 50ms latency - good balance for experiments

# For blocks (long playback) - prioritize stability
BLOCK_STREAM_LATENCY = 0.1  # 100ms for stable block playback
BLOCK_BLOCKSIZE = 4096      # Larger chunks for block playback

# For clicks (instant feedback) - prioritize low latency
CLICK_LATENCY = 'low'       # Lowest possible for instant response
CLICK_BLOCKSIZE = 256       # Small for responsive clicks

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
        "audio_volume": 100,    # Audio output channel volume (Output 1)
        "tactile_volume": 100   # Tactile output channel volume (Output 2)
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
def find_output_device():
    """Find 'Output 1/2 (Komplete Audio 6 MK2)' device, or fall back to system default."""
    devices = sd.query_devices()

    # First try to find Komplete Audio 6
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
        self.stop_flag = False
        self.paused = False
        self.pause_lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Not paused initially

        # Volume controls (0.0 to 1.0)
        self.audio_volume = 1.0      # Output 1 (Audio channel)
        self.tactile_volume = 1.0    # Output 2 (Tactile channel)

        # Click sound state
        self._click_data = None
        self._click_sr = 44100
        self._click_stream = None
        self._click_pos = 0
        self._click_active = False
        self._click_lock = threading.Lock()

        # Block playback state (callback-based)
        self._block_data = None
        self._block_sr = 44100
        self._block_stream = None
        self._block_pos = 0
        self._block_lock = threading.Lock()
        self._block_finished = threading.Event()
        self._block_progress_callback = None

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

        # WASAPI loopback recording state
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

        print(f"AudioEngine initialized with latency settings: block={BLOCK_STREAM_LATENCY}s, click={CLICK_LATENCY}")

        # Initialize WASAPI loopback device if available
        if PYAUDIOWPATCH_AVAILABLE and ENABLE_LOOPBACK_RECORDING:
            self._init_wasapi_loopback()
        
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
        """Start WASAPI loopback recording.

        Args:
            output_path: Intended save path (stored for use if recording is interrupted)
        """
        if not PYAUDIOWPATCH_AVAILABLE or not ENABLE_LOOPBACK_RECORDING:
            return False

        if self._recording_stream is not None:
            print("Recording already active")
            return True

        if self._loopback_device_info is None:
            print("ERROR: No loopback device available")
            return False

        try:
            # Clear any previous recording data and store path
            with self._recording_lock:
                self._recording_data.clear()
            self._recording_output_path = output_path
            self._recording_start_time = time.time()

            def recording_callback(in_data, frame_count, time_info, status):
                """Callback to capture audio data."""
                if status:
                    print(f"Recording status: {status}")

                # Convert bytes to numpy array
                audio_data = np.frombuffer(in_data, dtype=np.float32)

                with self._recording_lock:
                    self._recording_data.append(audio_data.copy())

                return (None, pyaudio_wp.paContinue)

            self._recording_stream = self._recording_pyaudio.open(
                format=pyaudio_wp.paFloat32,
                channels=self._recording_channels,
                rate=self._recording_sr,
                input=True,
                input_device_index=self._loopback_device_info["index"],
                frames_per_buffer=RECORDING_BUFFER_SIZE,
                stream_callback=recording_callback
            )

            self._recording_stream.start_stream()
            self._recording_active = True
            print("WASAPI loopback recording started")
            return True

        except Exception as e:
            print(f"ERROR starting WASAPI recording: {e}")
            import traceback
            traceback.print_exc()
            return False

    def stop_recording(self, output_path=None, interrupted=False):
        """Stop WASAPI recording and save to file.

        Args:
            output_path: Path to save WAV file (None = use stored path, or don't save)
            interrupted: If True, modify filename to indicate early stop with duration

        Returns:
            numpy array of recorded audio, or None on error
        """
        if self._recording_stream is None:
            print("Recording not active")
            return None

        try:
            self._recording_stream.stop_stream()
            self._recording_stream.close()
            self._recording_stream = None
            self._recording_active = False
            print("WASAPI recording stopped")

            # Concatenate all recorded chunks
            with self._recording_lock:
                if not self._recording_data:
                    print("Warning: No audio data recorded")
                    self._recording_output_path = None
                    self._recording_start_time = None
                    return None

                recorded_audio = np.concatenate(self._recording_data)
                self._recording_data.clear()

            # Reshape to stereo if needed
            if self._recording_channels > 1:
                recorded_audio = recorded_audio.reshape(-1, self._recording_channels)

            duration = len(recorded_audio) / self._recording_sr
            print(f"Recorded {duration:.1f} seconds of audio")

            # Determine save path
            save_path = output_path or self._recording_output_path

            if save_path:
                # If interrupted, modify the filename to include duration
                if interrupted:
                    # Convert duration to mm-ss format
                    mins = int(duration) // 60
                    secs = int(duration) % 60
                    duration_str = f"{mins:02d}m{secs:02d}s"

                    # Insert "_STOPPED_AT_{duration}" before the extension
                    base, ext = os.path.splitext(save_path)
                    save_path = f"{base}_STOPPED_AT_{duration_str}{ext}"
                    print(f"Recording was interrupted at {duration_str}")

                # Ensure directory exists
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                sf.write(save_path, recorded_audio, self._recording_sr)
                print(f"Recording saved: {save_path}")

            # Clear stored path
            self._recording_output_path = None
            self._recording_start_time = None

            return recorded_audio

        except Exception as e:
            print(f"ERROR stopping recording: {e}")
            import traceback
            traceback.print_exc()
            return None

    def is_recording(self):
        """Check if recording is currently active."""
        return self._recording_active

    def get_recording_duration(self):
        """Get current recording duration in seconds."""
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
            self._init_click_stream()
            return True
        except Exception as e:
            print(f"ERROR: Failed to load click sound: {e}")
            return False

    def _click_callback(self, outdata, frames, time_info, status):
        """Low-latency callback - click goes to BOTH outputs for testing.

        Stream channel mapping:
        - Channel 0 â†’ Output 1 (Audio)
        - Channel 1 â†’ Output 2 (Tactile)
        """
        outdata.fill(0)
        if not self._click_active or self._click_data is None:
            return

        with self._click_lock:
            remaining = len(self._click_data) - self._click_pos
            n = min(frames, remaining)
            if n > 0:
                click_samples = self._click_data[self._click_pos:self._click_pos + n, 0]
                # Output ONLY to Channel 1 (Tactile) - NOT audio
                # Channel 0 (Audio) stays silent for clicks
                outdata[:n, 1] = click_samples  # Output 2 (Tactile)
                self._click_pos += n
            if self._click_pos >= len(self._click_data):
                self._click_active = False
                self._click_pos = 0

    def _init_click_stream(self):
        """Initialize persistent low-latency click stream with optimized settings."""
        if self._click_data is None:
            print("DEBUG: _init_click_stream - no click data loaded")
            return
        try:
            print(f"DEBUG: Initializing click stream on device {self.device_idx}, sr={self._click_sr}, latency={CLICK_LATENCY}")
            self._click_stream = sd.OutputStream(
                samplerate=self._click_sr,
                channels=2,
                device=self.device_idx,
                latency=CLICK_LATENCY,
                blocksize=CLICK_BLOCKSIZE,
                callback=self._click_callback
            )
            self._click_stream.start()
            print(f"DEBUG: Click stream started successfully, active={self._click_stream.active}")
        except Exception as e:
            print(f"ERROR: Click stream init failed: {e}")
            import traceback
            traceback.print_exc()
    
    def trigger_click(self):
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
            print("DEBUG: Click triggered!")
    
    def _block_callback(self, outdata, frames, time_info, status):
        """Callback for block audio playback - ensures consistent timing."""
        if status:
            print(f"Block stream status: {status}")  # Log any underruns

        if self._block_data is None or self.stop_flag:
            outdata.fill(0)
            return

        # Handle pause - output silence but don't advance position
        if self.paused:
            outdata.fill(0)
            return

        with self._block_lock:
            remaining = len(self._block_data) - self._block_pos

            if remaining <= 0:
                # Playback finished
                outdata.fill(0)
                self._block_finished.set()
                return

            n = min(frames, remaining)
            # Copy data and apply volume in real-time
            outdata[:n] = self._block_data[self._block_pos:self._block_pos + n].copy()
            # Apply volume to each channel (0 = Audio, 1 = Tactile)
            outdata[:n, 0] *= self.audio_volume
            outdata[:n, 1] *= self.tactile_volume
            if n < frames:
                outdata[n:].fill(0)

            self._block_pos += n
            self.elapsed_time = self._block_pos / self._block_sr

            # Check if finished
            if self._block_pos >= len(self._block_data):
                self._block_finished.set()

    def play_block(self, path, progress_callback=None) -> bool:
        """Play a block WAV file with callback-based streaming for timing stability.

        WAV file has:
        - LEFT channel (index 0) = Tactile
        - RIGHT channel (index 1) = Audio

        Output mapping:
        - Output 1 = Audio (from WAV RIGHT)
        - Output 2 = Tactile (from WAV LEFT)

        So we swap: stream[0] = wav[1], stream[1] = wav[0]

        Uses callback-based streaming for consistent timing (no jitter from write() loop).
        """
        try:
            # Check cache first, otherwise load from file
            if path in self._audio_cache:
                data, sr = self._audio_cache[path]
                data = data.copy()  # Copy so we don't modify cached data
            else:
                data, sr = sf.read(path, dtype='float32')

            if data.ndim != 2 or data.shape[1] != 2:
                print(f"ERROR: Expected stereo file, got shape {data.shape}")
                return False

            # Swap channels: WAV[L,R] â†’ Output[R,L] so Output1=Audio, Output2=Tactile
            # Volume is applied in real-time in the callback for instant slider response
            data = np.ascontiguousarray(data[:, [1, 0]])

            # Setup state for callback
            self.stop_flag = False
            self.paused = False
            self.pause_event.set()
            self.elapsed_time = 0.0
            self._block_finished.clear()
            self._block_progress_callback = progress_callback

            with self._block_lock:
                self._block_data = data
                self._block_sr = sr
                self._block_pos = 0

            # Create callback-based stream for consistent timing
            self._block_stream = sd.OutputStream(
                samplerate=sr,
                channels=2,
                dtype='float32',
                device=self.device_idx,
                latency=BLOCK_STREAM_LATENCY,
                blocksize=BLOCK_BLOCKSIZE,
                callback=self._block_callback
            )

            print(f"Starting block playback: latency={BLOCK_STREAM_LATENCY}s, blocksize={BLOCK_BLOCKSIZE}")
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

            return not self.stop_flag

        except Exception as e:
            print(f"ERROR: Block playback failed: {e}")
            import traceback
            traceback.print_exc()
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

        # Stop any active recording and SAVE it with interrupted marker
        if self._recording_stream is not None:
            print("Saving interrupted recording...")
            self.stop_recording(interrupted=True)

    def shutdown(self):
        """Full shutdown - close all streams including click stream and recording."""
        self.stop()

        # Stop any active recording
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
            # Copy data and apply volume in real-time
            outdata[:n] = self._instr_data[self._instr_pos:self._instr_pos + n].copy()
            # Apply audio volume to channel 0 (instructions only play on audio channel)
            outdata[:n, 0] *= self.audio_volume
            if n < frames:
                outdata[n:].fill(0)

            self._instr_pos += n

            if self._instr_pos >= len(self._instr_data):
                self._instr_finished.set()

    def play_instruction(self, path, on_complete=None):
        """Play instruction audio (MP3) through audio channel only (Output 1).

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

                # Handle mono or stereo - we only want audio channel (Output 1)
                # Volume is applied in real-time in the callback for instant slider response
                if data.ndim == 1:
                    stereo_data = np.zeros((len(data), 2), dtype='float32')
                    stereo_data[:, 0] = data
                    data = stereo_data
                elif data.ndim == 2 and data.shape[1] == 2:
                    mono = (data[:, 0] + data[:, 1]) / 2
                    stereo_data = np.zeros((len(mono), 2), dtype='float32')
                    stereo_data[:, 0] = mono
                    data = stereo_data
                elif data.ndim == 2 and data.shape[1] == 1:
                    stereo_data = np.zeros((len(data), 2), dtype='float32')
                    stereo_data[:, 0] = data[:, 0]
                    data = stereo_data

                # Ensure C-contiguous
                data = np.ascontiguousarray(data)

                self.stop_flag = False
                self._instr_finished.clear()

                with self._instr_lock:
                    self._instr_data = data
                    self._instr_sr = sr
                    self._instr_pos = 0
                    self._instr_on_complete = on_complete

                # Create callback-based stream
                self._instr_stream = sd.OutputStream(
                    samplerate=sr,
                    channels=2,
                    dtype='float32',
                    device=self.device_idx,
                    latency=STREAM_LATENCY,
                    blocksize=AUDIO_BLOCKSIZE,
                    callback=self._instr_callback
                )
                self._instr_stream.start()

                # Wait for playback to finish
                while not self._instr_finished.is_set() and not self.stop_flag:
                    time.sleep(0.05)

                self._instr_stream.stop()
                self._instr_stream.close()
                self._instr_stream = None

                with self._instr_lock:
                    self._instr_data = None

                if on_complete:
                    on_complete(not self.stop_flag)

            except Exception as e:
                print(f"ERROR: Instruction playback failed: {e}")
                import traceback
                traceback.print_exc()
                if on_complete:
                    on_complete(False)

        threading.Thread(target=play_thread, daemon=True).start()

    def start_background_music(self, path, volume=0.5):
        """Start playing background music in a continuous loop.

        Plays through audio channel only (Output 1) at specified volume.
        Returns the stream object for control, or None on failure.
        """
        if not os.path.exists(path):
            print(f"ERROR: Background music not found: {path}")
            return None

        try:
            data, sr = sf.read(path, dtype='float32')

            # Convert mono to stereo if needed
            if len(data.shape) == 1:
                data = np.column_stack([data, np.zeros(len(data), dtype='float32')])
            elif data.shape[1] >= 2:
                # Take only first 2 channels, audio goes to channel 0 (Output 1)
                data = data[:, :2].copy()
                # Zero out channel 1 (Output 2 / tactile)
                data[:, 1] = 0

            # Apply volume
            data[:, 0] *= volume

            # Ensure C-contiguous
            data = np.ascontiguousarray(data)

            # Create looping playback
            self.bg_music_data = data
            self.bg_music_sr = sr
            self.bg_music_idx = 0
            self.bg_music_volume = volume
            self.bg_music_stop = False

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

            stream = sd.OutputStream(
                device=self.device_idx,
                samplerate=sr,
                channels=2,
                dtype='float32',
                latency=STREAM_LATENCY,
                blocksize=AUDIO_BLOCKSIZE,
                callback=callback
            )
            stream.start()
            print(f"Background music started (volume: {volume*100:.0f}%, latency={STREAM_LATENCY}s)")
            return stream

        except Exception as e:
            print(f"ERROR: Failed to start background music: {e}")
            return None

    def set_background_volume(self, volume):
        """Update the volume of background music (0.0 to 1.0)."""
        if hasattr(self, 'bg_music_data') and hasattr(self, 'bg_music_volume'):
            # Rescale the data based on new volume
            old_vol = self.bg_music_volume if self.bg_music_volume > 0 else 1.0
            self.bg_music_data[:, 0] = (self.bg_music_data[:, 0] / old_vol) * volume
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


# =============================================================================
# MAIN APPLICATION
# =============================================================================
class PPSExperimentApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PPS Experiment Runner")
        self.root.geometry("1200x850")  # Wide window: left panel controls, right panel click area + demographics
        self.root.resizable(False, False)

        # Load saved settings
        self.settings = load_settings()

        # Mouse lock state for between-block waiting
        self.mouse_locked = False
        self._mouse_lock_timer = None

        # State
        self.participant_id = None
        self.participant_folder = None
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
        
        # Audio engine
        self.device_idx, self.device_name, is_komplete = find_output_device()
        if self.device_idx is None:
            print("ERROR: Could not find any audio output device")
            messagebox.showerror("Audio Error", "Could not find any audio output device")
        elif is_komplete:
            print(f"Komplete Audio 6 found: [{self.device_idx}] {self.device_name}")
        else:
            print(f"Using system default audio: [{self.device_idx}] {self.device_name}")
        
        self.audio = AudioEngine(self.device_idx) if self.device_idx else None
        
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
        - P01_PPS_part1_1f_concatenated.wav â†’ Block 1 (number after 'part1_' or 'part2_')
        - 1.wav, 1a_concatenated.wav â†’ Block 1 (leading digit)
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
    
    def _build_ui(self):
        """Build the GUI with two-column layout."""
        # Main container
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill='both', expand=True)

        # Title
        ttk.Label(main, text="PPS Breathing Experiment",
                 font=('Arial', 18, 'bold')).pack(pady=(0, 10))

        # Two-column layout: left panel (controls) and right panel (click area + demographics)
        columns = ttk.Frame(main)
        columns.pack(fill='both', expand=True)

        # LEFT PANEL - Controls
        left_panel = ttk.Frame(columns)
        left_panel.pack(side='left', fill='both', expand=False, padx=(0, 10))

        # RIGHT PANEL - Click area + Demographics
        right_panel = ttk.Frame(columns)
        right_panel.pack(side='right', fill='both', expand=True)

        # =====================================================================
        # LEFT PANEL CONTENTS
        # =====================================================================

        # === General Instructions ===
        instr_frame = ttk.LabelFrame(left_panel, text="Instructions", padding=8)
        instr_frame.pack(fill='x', pady=3)

        self.general_instr_btn = ttk.Button(
            instr_frame, text="â–¶ Play General Instructions",
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
            bg_row, text="â–¶ Play", command=self._toggle_background_music, width=10
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

        # Audio channel volume (Output 1)
        audio_row = ttk.Frame(vol_frame)
        audio_row.pack(fill='x', pady=2)

        ttk.Label(audio_row, text="Audio (Out 1):", width=12).pack(side='left')
        saved_audio_vol = self.settings.get("audio_volume", 100)
        self.audio_volume_var = tk.DoubleVar(value=saved_audio_vol)
        self.audio_volume_scale = ttk.Scale(
            audio_row, from_=0, to=100, variable=self.audio_volume_var,
            orient='horizontal', length=150, command=self._on_audio_volume_change
        )
        self.audio_volume_scale.pack(side='left', padx=3)
        self.audio_volume_label = ttk.Label(audio_row, text=f"{int(saved_audio_vol)}%", width=4)
        self.audio_volume_label.pack(side='left')

        # Tactile channel volume (Output 2)
        tactile_row = ttk.Frame(vol_frame)
        tactile_row.pack(fill='x', pady=2)

        ttk.Label(tactile_row, text="Tactile (Out 2):", width=12).pack(side='left')
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
            test_row, text="ðŸ”Š Test Tactile (SOA 0)",
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

        self.play_btn = ttk.Button(btn_row, text="â–¶ Play Block", command=self._play_block,
                                   state='disabled', width=12)
        self.play_btn.pack(side='left', padx=5)

        self.next_btn = ttk.Button(btn_row, text="Next Block â†’", command=self._next_block,
                                   state='disabled', width=12)
        self.next_btn.pack(side='left', padx=5)

        self.pause_label = ttk.Label(btn_row, text="", foreground='orange')
        self.pause_label.pack(side='left', padx=10)

        # === Progress ===
        prog_frame = ttk.LabelFrame(left_panel, text="Progress", padding=8)
        prog_frame.pack(fill='x', pady=3)

        self.time_label = ttk.Label(prog_frame, text="0:00 / 5:52", font=('Arial', 12))
        self.time_label.pack()

        self.progress_bar = ttk.Progressbar(prog_frame, length=380, maximum=DEFAULT_BLOCK_DURATION)
        self.progress_bar.pack(pady=5)

        # === Info ===
        self.info_label = ttk.Label(left_panel, text="Shortcut: Ctrl+Alt+P to pause/resume",
                                   foreground='blue', font=('Arial', 9))
        self.info_label.pack(pady=5)

        # =====================================================================
        # RIGHT PANEL CONTENTS
        # =====================================================================

        # === Click Target (top of right panel) ===
        cf = ttk.LabelFrame(right_panel, text="Click Area (Participant Response)", padding=10)
        cf.pack(pady=5, anchor='n')

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
        gender_options = ["mÃ¤nnlich", "weiblich", "ander", "prefer not to say"]
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
            save_row, text="ðŸ’¾ Save Demographics",
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
        self.block_combo['state'] = 'disabled'
        self.jump_btn['state'] = 'disabled'
        self.play_btn['state'] = 'disabled'
        self.next_btn['state'] = 'disabled'
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
        self.instr_status_label.config(text="â–¶ Playing instructions...", foreground='green')
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
        self.instr_status_label.config(text="âœ“ Instructions complete", foreground='gray')
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
            self.bg_music_btn.config(text="â–¶ Play")
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
                self.bg_music_btn.config(text="â¹ Stop")
                self.bg_status_label.config(text="â™ª Playing", foreground='green')
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
            self.bg_music_btn.config(text="â¹ Stop")
            self.bg_status_label.config(text="â™ª Playing", foreground='green')
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
        """Play the tactile test stimulus (SOA 0ms) on Output 2 only."""
        if not os.path.exists(TACTILE_TEST_STIMULUS):
            messagebox.showerror("Error", f"Tactile test file not found:\n{TACTILE_TEST_STIMULUS}")
            return

        def play_tactile():
            try:
                data, sr = sf.read(TACTILE_TEST_STIMULUS, dtype='float32')
                # Ensure stereo
                if data.ndim == 1:
                    data = np.column_stack([data, np.zeros_like(data)])
                elif data.shape[1] == 1:
                    data = np.column_stack([data, np.zeros_like(data)])

                # Create output: Channel 0 = silence, Channel 1 = tactile
                stereo = np.zeros((len(data), 2), dtype='float32')
                stereo[:, 1] = data[:, 0] * self.audio.tactile_volume if self.audio else data[:, 0]

                sd.play(stereo, sr, device=self.audio.device_idx if self.audio else None)
                print("DEBUG: Playing tactile test stimulus (SOA 0ms)")
            except Exception as e:
                print(f"ERROR: Could not play tactile test: {e}")

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
            self.demo_status_label.config(text="âœ“ Saved!", foreground='green')
            self.demographics_completed = True
            # Enable all experiment controls now that demographics are complete
            self._enable_all_experiment_controls()
            # Start mouse listener now
            self._start_mouse_listener()
            # Clear status after 3 seconds
            self.root.after(3000, lambda: self.demo_status_label.config(text=""))
        else:
            self.demo_status_label.config(text="âœ— Save failed", foreground='red')

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
        self.status_label.config(text=f"âœ“ {pid} loaded", foreground='green')
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

        Also starts WASAPI loopback recording if enabled.
        """
        # Stop any existing recentering (from awaiting click phase) before starting fresh
        self._stop_recentering()

        self.is_instruction_playing = False
        self.is_playing = True
        self.is_paused = False
        self.awaiting_click_to_start = False  # Clear the awaiting state

        # Update UI
        self.click_target.set_active(True)
        self.pause_label.config(text="")

        # Prepare recording path
        recording_enabled = (PYAUDIOWPATCH_AVAILABLE and ENABLE_LOOPBACK_RECORDING
                            and self.audio is not None)
        recording_path = None

        if recording_enabled:
            # Get the original block filename for metadata
            block_filename = os.path.basename(block_path)
            block_name = os.path.splitext(block_filename)[0]

            # Create recording filename with full metadata
            # Format: {ParticipantID}_Part{X}_Block{Y}_{OriginalBlockName}_recording.wav
            recording_filename = f"{self.participant_id}_Part{self.current_part}_Block{block_num}_{block_name}_recording.wav"

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
                print("Starting WASAPI loopback recording...")
                if not self.audio.start_recording(output_path=recording_path):
                    print("WARNING: Failed to start recording, continuing without it")
                else:
                    # Small delay to ensure recording is capturing
                    time.sleep(RECORDING_PRE_BUFFER_SEC)

            def on_progress(elapsed):
                self.root.after(0, lambda: self._update_progress(elapsed))

            success = self.audio.play_block(block_path, progress_callback=on_progress)

            # Stop recording AFTER playback and save (only if still recording)
            # Note: If user stopped early, stop() already called stop_recording(interrupted=True)
            if recording_enabled and self.audio.is_recording():
                print("Stopping WASAPI recording (complete)...")
                self.audio.stop_recording(recording_path, interrupted=False)

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

        block_num = self.current_block + 1
        print(f"Finished block {block_num}")

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

            # Move mouse to click area and lock it there
            self._do_recenter()
            self._start_mouse_lock()

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
            self.pause_label.config(text="â¸ PAUSED")
            print(f"Paused block {block_num} at t = {elapsed:.1f}s")
    
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
    # Mouse Lock (keeps mouse locked to click area between blocks)
    # -------------------------------------------------------------------------
    def _start_mouse_lock(self):
        """Start locking mouse to click target center (between blocks)."""
        self.mouse_locked = True
        self._do_mouse_lock()

    def _do_mouse_lock(self):
        """Continuously move mouse to click target center while locked."""
        if not self.mouse_locked or not PYAUTOGUI_AVAILABLE:
            return

        try:
            x, y = self.click_target.get_center_coords()
            pyautogui.moveTo(x, y, duration=0)
        except Exception:
            pass

        # Schedule next lock check (every 50ms for smooth locking)
        self._mouse_lock_timer = self.root.after(50, self._do_mouse_lock)

    def _stop_mouse_lock(self):
        """Stop locking mouse to click target."""
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

            # Always play click tone for any click (zero-lag feedback)
            if self.audio:
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
    args = build_arg_parser().parse_args(argv)
    configure_runtime_paths(args)

    # List devices mode
    if args.list_devices:
        print("\n=== Audio Devices ===")
        for i, dev in enumerate(sd.query_devices()):
            out_ch = dev['max_output_channels']
            in_ch = dev['max_input_channels']
            if out_ch > 0 or in_ch > 0:
                print(f"[{i}] {dev['name']} (out:{out_ch}, in:{in_ch})")
        return 0
    
    root = tk.Tk()
    app = PPSExperimentApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

