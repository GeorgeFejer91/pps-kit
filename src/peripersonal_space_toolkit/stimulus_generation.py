"""Stimulus generation for the audio-tactile PPS toolkit.

The generator creates Study 5-style audio-tactile stimuli and participant
sequence folders from repository-relative inputs and command-line path
overrides. Generated WAVs and participant schedules are written under
`artifacts/` by default and are not intended to be committed.

Public CLI:
    pps-generate --dry-run
    pps-generate --participants 50

Required local input when generating looming stimuli from scratch:
    assets/0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa

The SOFA/HRIR file is user-supplied because redistribution rights vary.
Pregenerated looming WAVs may also be supplied through `--use-pregenerated-looming`.
"""

import csv
import argparse
import os
import random
import sys
from itertools import permutations
from pathlib import Path

import numpy as np
import scipy.signal as signal
import soundfile as sf

try:
    from pydub import AudioSegment
    HAS_PYDUB = True
except ImportError:
    HAS_PYDUB = False

# Global cache for breathing instructions (to avoid slow resampling multiple times)
_BREATHING_CACHE = {}


# ========================================================================
# GLOBAL CONFIGURATION - CHANGE THESE DIRECTORIES
# ========================================================================

# Repository root when running from an editable checkout.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ROOT DIRECTORY: Base directory for generated stimulus artifacts.
ROOT_DIRECTORY = PROJECT_ROOT / "artifacts" / "stimuli"

# INPUT DIRECTORY: Where the required input files are located
# This folder should contain:
#   - 0. Head-Related Impulse Response (HRIR) model/FABIAN_HRIR_measured_HATO_0.sofa
#   - 0. BoxBreathingInstructions/Inhale-2-3-4-hold_FIXED.wav
#   - 0. BoxBreathingInstructions/Exhale-2-3-4-hold_FIXED.wav
INPUT_DIR = PROJECT_ROOT / "assets"

# Bundled breathing/audio instruction assets. HRIR or pregenerated looming
# stimuli remain user-supplied because their redistribution status differs.
BREATHING_DIR = PROJECT_ROOT / "assets" / "breathing"

# OUTPUT DIRECTORY: Where all generated stimuli will be saved
# The script will create all subdirectories here automatically
OUTPUT_DIR = ROOT_DIRECTORY

# Number of participant sequence folders to materialize.
NUM_PARTICIPANTS = 50
RANDOM_SEED = 20250604

# Sample rate for all audio
SAMPLE_RATE = 44100

# ========================================================================
# UPDATED LOOMING PARAMETERS (110 cm â†’ 10 cm)
# ========================================================================
INITIAL_DISTANCE = 1.1      # Starting distance in meters (110 cm)
FINAL_DISTANCE = 0.1        # Final distance in meters (10 cm)
LOOMING_DURATION = 3.0      # Duration of approach in seconds
APPROACH_VELOCITY = (INITIAL_DISTANCE - FINAL_DISTANCE) / LOOMING_DURATION  # 33.3 cm/s

# Spatial parameters
AZIMUTH_ANGLE = 0           # Frontal approach (0 degrees)
ELEVATION_ANGLE = 0         # At ear level

# Distance attenuation
USE_INVERSE_SQUARE_LAW = True  # Use physics-based distance attenuation

# Volume
VOLUME_LEVEL = 0.7          # Output volume (0.0 to 1.0)

# ========================================================================
# TACTILE STIMULUS PARAMETERS
# ========================================================================
TACTILE_DURATION = 0.1      # 100 ms
ATTACK_FREQ = 200           # Hz
DECAY_FREQ = 50             # Hz
ATTACK_DB = 4               # dB
DECAY_DB = -22              # dB

# Onset delays for tactile stimuli (SOAs)
ONSET_DELAYS_MS = [0, 300, 800, 1500, 2200, 2700]

# ========================================================================
# NOISE TYPES
# ========================================================================
NOISE_TYPES = ['pink', 'blue', 'white', 'brown']

# ========================================================================
# LOOMING STIMULI CONFIGURATION
# ========================================================================

# USE PRE-GENERATED LOOMING STIMULI (recommended - much faster!)
USE_PREGENERATED_LOOMING = False  # True uses user-supplied pregenerated looming WAVs.

# Choose which version of pre-generated looming stimuli to use:
# 'v1-padded' - Version 1 with padding (500ms silence before and after)
# 'v2-holds'  - Version 2 with holds (breathing holds integrated)
LOOMING_VERSION = 'v1-padded'  # Change to 'v2-holds' if you want the holds version

# Pre-generated looming stimuli directory (already 4 seconds, exactly 176,400 samples)
LOOMING_INPUT_DIR = INPUT_DIR / "1. Looming Stimuli"

# ========================================================================
# TRIAL PARAMETERS
# ========================================================================
TRIAL_DURATION = 8.0        # Total trial duration in seconds
BREATHING_DURATION = 4.0    # Breathing instruction duration (~4s)
STIMULUS_DURATION = 4.0     # Stimulus presentation duration (4s)

# ========================================================================
# PATHS TO REQUIRED INPUT FILES
# ========================================================================

# HRTF SOFA file (must be provided by user in INPUT_DIR)
SOFA_FILE = INPUT_DIR / "0. Head-Related Impulse Response (HRIR) model" / "FABIAN_HRIR_measured_HATO_0.sofa"

# Breathing instruction files (must be provided by user in INPUT_DIR)
INHALE_INSTRUCTION = BREATHING_DIR / "Inhale-2-3-4-hold_FIXED.wav"
EXHALE_INSTRUCTION = BREATHING_DIR / "Exhale-2-3-4-hold_FIXED.wav"

# ========================================================================
# OUTPUT DIRECTORIES (all created in OUTPUT_DIR)
# ========================================================================
def build_output_dirs(output_dir):
    """Return the generated-stimulus folder contract for an output root."""
    return {
        'tactile': output_dir / "1. TactileStimuli",
        'looming': output_dir / "2. LoomingStimuli",
        'looming_tactile': output_dir / "4. LoomingXTactile_Stimuli",
        'breathing_looming_tactile_inhale': output_dir / "5. Breathingphase+LoomingXTactile" / "Inhale",
        'breathing_looming_tactile_exhale': output_dir / "5. Breathingphase+LoomingXTactile" / "Exhale",
        'baseline_inhale': output_dir / "6. Baseline" / "Inhale",
        'baseline_exhale': output_dir / "6. Baseline" / "Exhale",
        'catch_inhale': output_dir / "7. Catch" / "Inhale",
        'catch_exhale': output_dir / "7. Catch" / "Exhale",
        'master_blocks': output_dir / "8.Master_Blocks",
        'experiment_blocks': output_dir / "9.Experiment_Blocks",
        'participant_sequences': output_dir / "10.Participant_Sequences",
    }


OUTPUT_DIRS = build_output_dirs(OUTPUT_DIR)


def configure_paths(
    *,
    root_dir=None,
    input_dir=None,
    output_dir=None,
    breathing_dir=None,
    use_pregenerated_looming=None,
    looming_version=None,
    participants=None,
    seed=None,
):
    """Update module globals from CLI/config values before generation."""
    global ROOT_DIRECTORY, INPUT_DIR, OUTPUT_DIR, BREATHING_DIR
    global LOOMING_INPUT_DIR, SOFA_FILE, INHALE_INSTRUCTION, EXHALE_INSTRUCTION
    global OUTPUT_DIRS, USE_PREGENERATED_LOOMING, LOOMING_VERSION, NUM_PARTICIPANTS, RANDOM_SEED

    ROOT_DIRECTORY = Path(root_dir).expanduser().resolve() if root_dir else ROOT_DIRECTORY
    INPUT_DIR = Path(input_dir).expanduser().resolve() if input_dir else INPUT_DIR
    OUTPUT_DIR = Path(output_dir).expanduser().resolve() if output_dir else OUTPUT_DIR
    BREATHING_DIR = Path(breathing_dir).expanduser().resolve() if breathing_dir else BREATHING_DIR

    if use_pregenerated_looming is not None:
        USE_PREGENERATED_LOOMING = bool(use_pregenerated_looming)
    if looming_version:
        LOOMING_VERSION = looming_version
    if participants is not None:
        NUM_PARTICIPANTS = int(participants)
    if seed is not None:
        RANDOM_SEED = int(seed)

    LOOMING_INPUT_DIR = INPUT_DIR / "1. Looming Stimuli"
    SOFA_FILE = INPUT_DIR / "0. Head-Related Impulse Response (HRIR) model" / "FABIAN_HRIR_measured_HATO_0.sofa"
    INHALE_INSTRUCTION = BREATHING_DIR / "Inhale-2-3-4-hold_FIXED.wav"
    EXHALE_INSTRUCTION = BREATHING_DIR / "Exhale-2-3-4-hold_FIXED.wav"
    OUTPUT_DIRS = build_output_dirs(OUTPUT_DIR)


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Generate audio-tactile PPS experiment stimuli and participant sequences."
    )
    parser.add_argument("--root-dir", type=Path, default=ROOT_DIRECTORY, help="Base generated-artifact directory.")
    parser.add_argument("--input-dir", type=Path, default=INPUT_DIR, help="Directory for HRIR and optional looming inputs.")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Directory where generated stimuli are written.")
    parser.add_argument("--breathing-dir", type=Path, default=BREATHING_DIR, help="Directory containing bundled breathing WAV files.")
    parser.add_argument("--participants", type=int, default=NUM_PARTICIPANTS, help="Number of participant sequences to generate.")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Random seed for reproducible block randomization.")
    parser.add_argument("--use-pregenerated-looming", action="store_true", help="Use WAVs in '<input-dir>/1. Looming Stimuli' instead of generating from HRIR.")
    parser.add_argument("--looming-version", choices=["v1-padded", "v2-holds"], default=LOOMING_VERSION)
    parser.add_argument("--dry-run", action="store_true", help="Print resolved paths and required inputs without writing stimuli.")
    return parser


def missing_input_files():
    missing = []
    if USE_PREGENERATED_LOOMING:
        for noise_type in NOISE_TYPES:
            filename = f"Loom-{NOISE_TYPES.index(noise_type)+1}-{noise_type}-{LOOMING_VERSION}.wav"
            if not (LOOMING_INPUT_DIR / filename).exists():
                missing.append(f"Pregenerated looming stimulus: {LOOMING_INPUT_DIR / filename}")
    elif not SOFA_FILE.exists():
        missing.append(f"HRTF SOFA file: {SOFA_FILE}")
    if not INHALE_INSTRUCTION.exists():
        missing.append(f"Inhale instruction: {INHALE_INSTRUCTION}")
    if not EXHALE_INSTRUCTION.exists():
        missing.append(f"Exhale instruction: {EXHALE_INSTRUCTION}")
    return missing


# ========================================================================
# UTILITY FUNCTIONS
# ========================================================================

def create_directories():
    """Create all necessary output directories"""
    print("\n" + "=" * 70)
    print("CREATING DIRECTORY STRUCTURE")
    print("=" * 70)

    # Create INPUT_DIR if it doesn't exist (for user convenience)
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"âœ“ INPUT:  {INPUT_DIR}")

    # Create OUTPUT_DIR parent folder
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"âœ“ OUTPUT: {OUTPUT_DIR}")

    # Create all output subdirectories
    print("\nCreating output subdirectories:")
    for name, path in OUTPUT_DIRS.items():
        path.mkdir(parents=True, exist_ok=True)
        # Show relative to OUTPUT_DIR for cleaner display
        rel_path = path.relative_to(OUTPUT_DIR)
        print(f"  âœ“ {rel_path}")

    print("\nAll directories created successfully!")


def db_to_amplitude(db):
    """Convert decibels to linear amplitude"""
    return 10 ** (db / 20)


def generate_sinusoid(frequency, duration, sample_rate, amplitude):
    """Generate a sinusoidal signal"""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    signal = amplitude * np.sin(2 * np.pi * frequency * t)
    return signal, t


def apply_envelope(signal, ramp_duration=0.005):
    """Apply cosine-squared envelope to avoid clicks"""
    ramp_samples = int(ramp_duration * SAMPLE_RATE)
    envelope = np.ones(len(signal))

    # Fade in
    envelope[:ramp_samples] = np.sin(np.linspace(0, np.pi/2, ramp_samples)) ** 2

    # Fade out
    envelope[-ramp_samples:] = np.cos(np.linspace(0, np.pi/2, ramp_samples)) ** 2

    return signal * envelope


# ========================================================================
# NOISE GENERATION FUNCTIONS
# ========================================================================

def generate_white_noise(duration, sample_rate):
    """Generate white noise (equal power across all frequencies)"""
    samples = int(duration * sample_rate)
    return np.random.randn(samples)


def generate_pink_noise(duration, sample_rate):
    """Generate pink noise (1/f power spectrum)"""
    samples = int(duration * sample_rate)
    white = np.random.randn(samples)

    # Apply 1/f filter in frequency domain
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(samples, 1/sample_rate)
    freqs[0] = 1  # Avoid division by zero

    # Apply 1/sqrt(f) to get 1/f power spectrum
    fft = fft / np.sqrt(freqs)

    pink = np.fft.irfft(fft, n=samples)
    return pink


def generate_blue_noise(duration, sample_rate):
    """Generate blue noise (f power spectrum, opposite of pink)"""
    samples = int(duration * sample_rate)
    white = np.random.randn(samples)

    # Apply f filter in frequency domain
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(samples, 1/sample_rate)

    # Apply sqrt(f) to get f power spectrum
    fft = fft * np.sqrt(freqs)

    blue = np.fft.irfft(fft, n=samples)
    return blue


def generate_brown_noise(duration, sample_rate):
    """Generate brown noise (1/f^2 power spectrum, Brownian motion)"""
    samples = int(duration * sample_rate)
    white = np.random.randn(samples)

    # Cumulative sum approximates Brownian motion
    brown = np.cumsum(white)

    # Normalize
    brown = brown / np.max(np.abs(brown))
    return brown


def generate_noise(noise_type, duration, sample_rate):
    """Generate noise of specified type"""
    noise_generators = {
        'white': generate_white_noise,
        'pink': generate_pink_noise,
        'blue': generate_blue_noise,
        'brown': generate_brown_noise,
    }

    if noise_type not in noise_generators:
        raise ValueError(f"Unknown noise type: {noise_type}")

    noise = noise_generators[noise_type](duration, sample_rate)

    # Normalize to prevent clipping
    noise = noise / np.max(np.abs(noise)) * 0.95

    return noise


# ========================================================================
# HRTF FUNCTIONS
# ========================================================================

def load_hrtf(sofa_path):
    """Load HRTF data from SOFA file"""
    try:
        import sofar as sf_sofa
    except ImportError as exc:
        raise ImportError("sofar package required. Install with: pip install sofar") from exc

    if not os.path.exists(sofa_path):
        raise FileNotFoundError(f"SOFA file not found: {sofa_path}")

    print(f"\nLoading HRTF from: {sofa_path}")
    hrtf = sf_sofa.read_sofa(str(sofa_path))
    print(f"âœ“ HRTF loaded successfully")

    return hrtf


def find_frontal_hrtf(hrtf, target_azimuth=0, target_elevation=0):
    """Find the HRTF measurement closest to frontal position"""
    positions = hrtf.Source.Position.get_values()

    # Find closest match to target position
    azimuth_diff = np.abs(positions[:, 0] - target_azimuth)
    elevation_diff = np.abs(positions[:, 1] - target_elevation)

    # Combined distance metric
    distance = np.sqrt(azimuth_diff**2 + elevation_diff**2)
    nearest_idx = np.argmin(distance)

    nearest_pos = positions[nearest_idx]

    return nearest_idx, nearest_pos


def extract_hrtf_filters(hrtf, position_idx):
    """Extract left and right ear HRTF filters for a given position"""
    ir_data = hrtf.Data.IR.get_values()

    # Extract impulse responses for left (0) and right (1) ears
    hrtf_left = ir_data[position_idx, 0, :]
    hrtf_right = ir_data[position_idx, 1, :]

    return hrtf_left, hrtf_right


def create_amplitude_envelope(duration, sample_rate, initial_distance, final_distance, use_inverse_square=True):
    """
    Create distance-based amplitude envelope for looming sound

    Returns:
        amplitude_envelope: Array of amplitude values
        distances: Array of distance values over time
    """
    num_samples = int(duration * sample_rate)

    # Linear distance trajectory
    distances = np.linspace(initial_distance, final_distance, num_samples)

    if use_inverse_square:
        # Inverse square law: Intensity âˆ 1/distanceÂ²
        # Amplitude âˆ 1/distance
        amplitude_envelope = 1.0 / distances
    else:
        # Linear amplitude increase
        amplitude_envelope = np.linspace(1.0/initial_distance, 1.0/final_distance, num_samples)

    # Normalize to [0, 1] range
    amplitude_envelope = amplitude_envelope / np.max(amplitude_envelope)

    # Apply volume scaling
    amplitude_envelope = amplitude_envelope * VOLUME_LEVEL

    return amplitude_envelope, distances


# ========================================================================
# STEP 1: GENERATE TACTILE STIMULI
# ========================================================================

def generate_tactile_stimulus():
    """Generate base tactile stimulus (100ms, 200Hz + 50Hz)"""
    print("\n" + "=" * 70)
    print("STEP 1: GENERATING TACTILE STIMULI")
    print("=" * 70)

    # Convert dB to amplitude
    attack_amplitude = db_to_amplitude(ATTACK_DB)
    decay_amplitude = db_to_amplitude(DECAY_DB)

    print(f"\nTactile stimulus parameters:")
    print(f"  Attack: {ATTACK_FREQ} Hz at {ATTACK_DB} dB (amplitude: {attack_amplitude:.4f})")
    print(f"  Decay:  {DECAY_FREQ} Hz at {DECAY_DB} dB (amplitude: {decay_amplitude:.4f})")
    print(f"  Duration: {TACTILE_DURATION * 1000:.0f} ms")
    print(f"  Sample rate: {SAMPLE_RATE} Hz")

    # Generate attack signal (200 Hz)
    attack_signal, time = generate_sinusoid(ATTACK_FREQ, TACTILE_DURATION, SAMPLE_RATE, attack_amplitude)

    # Generate decay signal (50 Hz)
    decay_signal, _ = generate_sinusoid(DECAY_FREQ, TACTILE_DURATION, SAMPLE_RATE, decay_amplitude)

    # Combine signals
    tactile_signal = attack_signal + decay_signal

    # Apply envelope to avoid clicks
    tactile_signal = apply_envelope(tactile_signal)

    # Normalize to prevent clipping
    max_amplitude = np.max(np.abs(tactile_signal))
    if max_amplitude > 0:
        tactile_signal = tactile_signal / max_amplitude * 0.95

    # Save base stimulus (0ms delay)
    output_path = OUTPUT_DIRS['tactile'] / "tactile_stimulus_0ms.wav"
    sf.write(output_path, tactile_signal, SAMPLE_RATE)
    print(f"\nâœ“ Saved base tactile stimulus: {output_path.name}")

    # Generate delayed versions
    print(f"\nGenerating tactile stimuli with onset delays...")
    for delay_ms in ONSET_DELAYS_MS[1:]:  # Skip 0ms (already saved)
        delay_seconds = delay_ms / 1000.0
        silence_samples = int(delay_seconds * SAMPLE_RATE)

        # Create silence + stimulus
        silence = np.zeros(silence_samples)
        delayed_stimulus = np.concatenate([silence, tactile_signal])

        # Save
        output_filename = f"tactile_stimulus_{delay_ms}ms.wav"
        output_path = OUTPUT_DIRS['tactile'] / output_filename
        sf.write(output_path, delayed_stimulus, SAMPLE_RATE)
        print(f"  âœ“ {output_filename} (delay: {delay_ms}ms, total: {len(delayed_stimulus)/SAMPLE_RATE*1000:.0f}ms)")

    print(f"\nâœ“ Generated {len(ONSET_DELAYS_MS)} tactile stimuli")

    return tactile_signal


# ========================================================================
# STEP 2: GENERATE LOOMING STIMULI
# ========================================================================

def generate_looming_stimulus(hrtf, noise_type, verbose=True):
    """
    Generate a frontal looming stimulus with HRTF spatial filtering

    Processing chain:
    1. Generate noise signal
    2. Apply frontal HRTF (spatial filtering)
    3. Apply distance-based amplitude envelope
    4. Return stereo signal
    """
    if verbose:
        print(f"\n  Processing {noise_type} noise...")

    # Step 1: Generate source noise
    source_signal = generate_noise(noise_type, LOOMING_DURATION, SAMPLE_RATE)

    # Step 2: Find and apply frontal HRTF
    nearest_idx, nearest_pos = find_frontal_hrtf(hrtf, AZIMUTH_ANGLE, ELEVATION_ANGLE)
    hrtf_left, hrtf_right = extract_hrtf_filters(hrtf, nearest_idx)

    if verbose:
        print(f"    HRTF position: azimuth={nearest_pos[0]:.1f}Â°, elevation={nearest_pos[1]:.1f}Â°")

    # Apply HRTF filters (spectral coloring from head/pinnae)
    filtered_left = signal.fftconvolve(source_signal, hrtf_left, mode='same')
    filtered_right = signal.fftconvolve(source_signal, hrtf_right, mode='same')

    # Step 3: Create distance-based amplitude envelope
    amplitude_envelope, distances = create_amplitude_envelope(
        LOOMING_DURATION, SAMPLE_RATE, INITIAL_DISTANCE, FINAL_DISTANCE, USE_INVERSE_SQUARE_LAW
    )

    # Step 4: Apply amplitude envelope to both channels
    output_left = filtered_left * amplitude_envelope
    output_right = filtered_right * amplitude_envelope

    # Combine into stereo signal
    output_signal = np.column_stack([output_left, output_right])

    # Normalize
    max_val = np.max(np.abs(output_signal))
    if max_val > 0:
        output_signal = output_signal / max_val * 0.95

    return output_signal, distances


def generate_all_looming_stimuli():
    """Generate or load all looming stimuli (4 noise types)"""
    print("\n" + "=" * 70)
    print("STEP 2: LOOMING STIMULI")
    print("=" * 70)

    print(f"\nLooming parameters:")
    print(f"  Initial distance: {INITIAL_DISTANCE} m ({INITIAL_DISTANCE*100:.0f} cm)")
    print(f"  Final distance: {FINAL_DISTANCE} m ({FINAL_DISTANCE*100:.0f} cm)")
    print(f"  Duration: {LOOMING_DURATION} s (extended to 4.0s for trials)")
    print(f"  Approach velocity: {APPROACH_VELOCITY:.3f} m/s ({APPROACH_VELOCITY*100:.1f} cm/s)")
    print(f"  Distance model: {'Inverse square law' if USE_INVERSE_SQUARE_LAW else 'Linear'}")

    if USE_PREGENERATED_LOOMING:
        # ===== LOAD PRE-GENERATED LOOMING STIMULI =====
        print(f"\nâœ“ Using PRE-GENERATED looming stimuli")
        print(f"  Version: {LOOMING_VERSION}")
        print(f"  Source: {LOOMING_INPUT_DIR}")

        # Check if input directory exists
        if not LOOMING_INPUT_DIR.exists():
            print(f"\nâœ— ERROR: Looming input directory not found: {LOOMING_INPUT_DIR}")
            print("  Please generate looming stimuli first or set USE_PREGENERATED_LOOMING = False")
            return

        # Copy pre-generated files to output directory
        generated_files = []
        for idx, noise_type in enumerate(NOISE_TYPES, start=1):
            # Input filename with version
            input_filename = f"Loom-{idx}-{noise_type}-{LOOMING_VERSION}.wav"
            input_path = LOOMING_INPUT_DIR / input_filename

            # Output filename (standard naming)
            output_filename = f"Loom-{idx}-{noise_type}.wav"
            output_path = OUTPUT_DIRS['looming'] / output_filename

            if not input_path.exists():
                print(f"\nâœ— ERROR: Pre-generated file not found: {input_filename}")
                print(f"  Expected at: {input_path}")
                continue

            # Load and verify the file
            audio, sr = sf.read(input_path)

            # Verify it's exactly 4 seconds (176,400 samples at 44,100 Hz)
            expected_samples = int(STIMULUS_DURATION * SAMPLE_RATE)
            actual_samples = len(audio)

            if actual_samples != expected_samples:
                print(f"\nâš  Warning: {input_filename} has {actual_samples} samples (expected {expected_samples})")
                print(f"  Duration: {actual_samples/SAMPLE_RATE:.4f}s (expected {STIMULUS_DURATION}s)")

            # Save to output directory
            sf.write(output_path, audio, SAMPLE_RATE)
            generated_files.append(output_filename)
            print(f"  âœ“ Loaded: {input_filename} â†’ {output_filename}")

    else:
        # ===== GENERATE LOOMING STIMULI FROM SCRATCH =====
        print(f"\nâœ“ GENERATING looming stimuli from scratch (this will take several minutes)")

        # Load HRTF
        if not SOFA_FILE.exists():
            print(f"\nâœ— ERROR: SOFA file not found at {SOFA_FILE}")
            print("  Please ensure the HRTF file is in the correct location.")
            return

        hrtf = load_hrtf(SOFA_FILE)

        # Generate each noise type
        generated_files = []
        for idx, noise_type in enumerate(NOISE_TYPES, start=1):
            print(f"\n[{idx}/{len(NOISE_TYPES)}] Generating {noise_type} noise looming stimulus...")

            # Generate looming stimulus (3 seconds)
            output_signal, distances = generate_looming_stimulus(hrtf, noise_type, verbose=True)

            # Extend from 3s to 4s (add 500ms before and after)
            target_samples = int(STIMULUS_DURATION * SAMPLE_RATE)
            prepend_samples = int(0.5 * SAMPLE_RATE)
            current_samples = len(output_signal)
            append_samples = target_samples - current_samples - prepend_samples

            padding_prepend = np.zeros((prepend_samples, 2))
            padding_append = np.zeros((append_samples, 2))
            output_signal = np.vstack([padding_prepend, output_signal, padding_append])

            # Save audio file
            filename = f"Loom-{idx}-{noise_type}.wav"
            output_path = OUTPUT_DIRS['looming'] / filename
            sf.write(output_path, output_signal, SAMPLE_RATE)
            print(f"    âœ“ Saved: {filename}")
            generated_files.append(filename)

    print(f"\nâœ“ Processed {len(generated_files)} looming stimuli")

    # Print SOA-to-distance mapping
    print(f"\nSOA-to-Distance Mapping (at {APPROACH_VELOCITY*100:.1f} cm/s):")
    for delay_ms in ONSET_DELAYS_MS[1:]:  # Skip 0ms
        time_at_tactile = delay_ms / 1000.0
        distance_at_tactile = INITIAL_DISTANCE - (APPROACH_VELOCITY * time_at_tactile)
        print(f"  SOA {delay_ms:4d} ms â†’ Distance: {distance_at_tactile*100:5.1f} cm")


# ========================================================================
# STEP 3: COMBINE LOOMING Ã— TACTILE STIMULI
# ========================================================================

def combine_looming_tactile_stimuli():
    """Combine looming and tactile stimuli into stereo files"""
    print("\n" + "=" * 70)
    print("STEP 3: COMBINING LOOMING Ã— TACTILE STIMULI")
    print("=" * 70)

    print("\nStereo channel layout:")
    print("  LEFT channel:  Tactile stimulus")
    print("  RIGHT channel: Looming audio (binaural)")

    # Get tactile files (skip 0ms)
    tactile_files = [f"tactile_stimulus_{delay}ms.wav" for delay in ONSET_DELAYS_MS[1:]]

    # Get looming files
    looming_files = [f"Loom-{idx}-{noise}.wav" for idx, noise in enumerate(NOISE_TYPES, start=1)]

    success_count = 0
    total_combinations = len(tactile_files) * len(looming_files)

    print(f"\nGenerating {total_combinations} combinations ({len(tactile_files)} tactile Ã— {len(looming_files)} looming)...")

    for tactile_file in tactile_files:
        # Load tactile stimulus
        tactile_path = OUTPUT_DIRS['tactile'] / tactile_file
        tactile_audio, tactile_sr = sf.read(tactile_path)

        for looming_file in looming_files:
            # Load looming stimulus
            looming_path = OUTPUT_DIRS['looming'] / looming_file
            looming_audio, looming_sr = sf.read(looming_path)

            # Ensure same sample rate
            if tactile_sr != looming_sr or tactile_sr != SAMPLE_RATE:
                print(f"  âœ— Sample rate mismatch: {tactile_file} ({tactile_sr}) vs {looming_file} ({looming_sr})")
                continue

            # Match lengths (pad shorter one)
            max_length = max(len(tactile_audio), len(looming_audio))

            # Pad tactile (mono)
            if len(tactile_audio) < max_length:
                tactile_padded = np.pad(tactile_audio, (0, max_length - len(tactile_audio)))
            else:
                tactile_padded = tactile_audio[:max_length]

            # Pad looming (stereo)
            if len(looming_audio) < max_length:
                padding = np.zeros((max_length - len(looming_audio), 2))
                looming_padded = np.vstack([looming_audio, padding])
            else:
                looming_padded = looming_audio[:max_length]

            # Create stereo output: LEFT=tactile, RIGHT=looming
            # Looming is already stereo, so we take the right channel
            stereo_output = np.column_stack([tactile_padded, looming_padded[:, 1]])

            # Create output filename
            output_filename = f"Stereo_LEFT_{tactile_file[:-4]}__RIGHT_{looming_file}"
            output_path = OUTPUT_DIRS['looming_tactile'] / output_filename

            # Save
            sf.write(output_path, stereo_output, SAMPLE_RATE)
            success_count += 1

    print(f"\nâœ“ Generated {success_count}/{total_combinations} combined stimuli")


# ========================================================================
# STEP 4: ADD BREATHING INSTRUCTIONS
# ========================================================================

def load_breathing_instruction(audio_path, phase_name):
    """Load a breathing-instruction WAV/MP3 with caching to avoid repeated resampling."""
    # Check cache first
    cache_key = str(audio_path)
    if cache_key in _BREATHING_CACHE:
        print(f"  âœ“ Using cached {phase_name} instruction ({audio_path.name})")
        return _BREATHING_CACHE[cache_key]

    if not audio_path.exists():
        raise FileNotFoundError(f"Breathing instruction not found: {audio_path}")

    print(f"  Loading {phase_name} instruction: {audio_path.name}")

    if audio_path.suffix.lower() == ".mp3":
        if not HAS_PYDUB:
            raise ImportError("pydub is required for MP3 loading. Use the bundled WAV assets or install pydub.")
        audio = AudioSegment.from_mp3(str(audio_path))

        # Convert to numpy array
        samples = np.array(audio.get_array_of_samples(), dtype=np.float32)

        # Normalize
        samples = samples / (2**15)  # 16-bit audio

        # Convert to stereo if mono
        if audio.channels == 1:
            samples = samples.reshape(-1, 1)
        else:
            samples = samples.reshape(-1, 2)
        frame_rate = audio.frame_rate
    else:
        samples, frame_rate = sf.read(str(audio_path), dtype="float32", always_2d=True)

    # Resample if needed (with progress indicator since this is SLOW)
    if frame_rate != SAMPLE_RATE:
        print(f"    âš  Resampling from {frame_rate} Hz to {SAMPLE_RATE} Hz...")
        from scipy import signal as sp_signal
        num_samples = int(len(samples) * SAMPLE_RATE / frame_rate)
        samples = sp_signal.resample(samples, num_samples)
        print(f"    âœ“ Resampling complete!")

    # Create stereo: LEFT=silence, RIGHT=instruction
    stereo_breathing = np.zeros((len(samples), 2))
    if samples.shape[1] == 1:
        stereo_breathing[:, 1] = samples[:, 0]  # Mono to right channel
    else:
        stereo_breathing[:, 1] = samples[:, 0]  # Take left channel of stereo

    print(f"    Duration: {len(stereo_breathing)/SAMPLE_RATE:.2f}s, Sample rate: {SAMPLE_RATE} Hz")

    # Cache the result to avoid resampling again in Steps 5 and 6
    _BREATHING_CACHE[cache_key] = stereo_breathing
    print(f"    âœ“ Cached for future use")

    return stereo_breathing


def combine_breathing_and_stimulus(breathing_audio, stimulus_audio, target_duration=8.0):
    """
    Combine breathing instruction with stimulus to create EXACTLY target_duration trial

    Structure:
    - 0-~4s: Breathing instruction (LEFT=silence, RIGHT=instruction)
    - ~4-8s: Stimulus (LEFT=tactile, RIGHT=looming or silence)

    The stimulus portion is padded/trimmed to ensure the total is exactly target_duration.
    """
    breathing_duration = len(breathing_audio) / SAMPLE_RATE
    stimulus_duration_needed = target_duration - breathing_duration

    # Calculate required samples for stimulus portion (exact)
    stimulus_samples_needed = int(stimulus_duration_needed * SAMPLE_RATE)
    current_stimulus_samples = len(stimulus_audio)

    # Pad or trim stimulus to fit exactly
    if current_stimulus_samples < stimulus_samples_needed:
        # Pad with silence at the end
        padding = np.zeros((stimulus_samples_needed - current_stimulus_samples, 2))
        stimulus_padded = np.vstack([stimulus_audio, padding])
    elif current_stimulus_samples > stimulus_samples_needed:
        # Trim (should rarely happen if stimulus is already 4.0s)
        stimulus_padded = stimulus_audio[:stimulus_samples_needed]
    else:
        # Perfect match
        stimulus_padded = stimulus_audio

    # Concatenate breathing + stimulus
    combined = np.vstack([breathing_audio, stimulus_padded])

    # Verify exact duration (within 1ms tolerance)
    actual_duration = len(combined) / SAMPLE_RATE
    if abs(actual_duration - target_duration) > 0.001:
        print(f"    âš  Warning: Trial duration {actual_duration:.4f}s (target: {target_duration:.4f}s)")

    return combined


def generate_breathing_looming_tactile_trials():
    """Generate trials with breathing instructions + looming-tactile stimuli"""
    print("\n" + "=" * 70)
    print("STEP 4: GENERATING BREATHING + LOOMING-TACTILE TRIALS")
    print("=" * 70)

    # Load breathing instructions
    print("\nLoading breathing instructions...")
    inhale_audio = load_breathing_instruction(INHALE_INSTRUCTION, "INHALE")
    exhale_audio = load_breathing_instruction(EXHALE_INSTRUCTION, "EXHALE")

    # Get all looming-tactile files
    looming_tactile_files = sorted(OUTPUT_DIRS['looming_tactile'].glob("Stereo_LEFT_*.wav"))

    print(f"\nProcessing {len(looming_tactile_files)} looming-tactile stimuli...")

    inhale_count = 0
    exhale_count = 0

    for lt_file in looming_tactile_files:
        # Load looming-tactile stimulus
        lt_audio, lt_sr = sf.read(lt_file)

        if lt_sr != SAMPLE_RATE:
            print(f"  âœ— Sample rate mismatch: {lt_file.name}")
            continue

        # Ensure stereo
        if lt_audio.ndim == 1:
            lt_audio = np.column_stack([lt_audio, np.zeros_like(lt_audio)])

        # The looming-tactile stimuli should already be 4 seconds (from pre-generated looming files)
        # Just ensure they are exactly 4.0 seconds
        target_samples = int(STIMULUS_DURATION * SAMPLE_RATE)  # Exactly 4.0 seconds
        current_samples = len(lt_audio)

        # Pad or trim to exactly 4.0 seconds
        if current_samples < target_samples:
            # Pad with silence at the end
            padding = np.zeros((target_samples - current_samples, 2))
            lt_extended = np.vstack([lt_audio, padding])
        elif current_samples > target_samples:
            # Trim to exact length
            lt_extended = lt_audio[:target_samples]
        else:
            # Already perfect length
            lt_extended = lt_audio

        # Verify exact duration
        actual_duration = len(lt_extended) / SAMPLE_RATE
        if abs(actual_duration - STIMULUS_DURATION) > 0.001:  # Within 1ms tolerance
            print(f"  âš  Warning: {lt_file.name} stimulus duration {actual_duration:.4f}s (target: {STIMULUS_DURATION}s)")

        # Combine with INHALE
        inhale_trial = combine_breathing_and_stimulus(inhale_audio, lt_extended, TRIAL_DURATION)
        inhale_output = OUTPUT_DIRS['breathing_looming_tactile_inhale'] / lt_file.name
        sf.write(inhale_output, inhale_trial, SAMPLE_RATE)
        inhale_count += 1

        # Combine with EXHALE
        exhale_trial = combine_breathing_and_stimulus(exhale_audio, lt_extended, TRIAL_DURATION)
        exhale_output = OUTPUT_DIRS['breathing_looming_tactile_exhale'] / lt_file.name
        sf.write(exhale_output, exhale_trial, SAMPLE_RATE)
        exhale_count += 1

    print(f"\nâœ“ Generated {inhale_count} INHALE trials")
    print(f"âœ“ Generated {exhale_count} EXHALE trials")
    print(f"âœ“ Total: {inhale_count + exhale_count} trials")


# ========================================================================
# STEP 5: GENERATE BASELINE TRIALS (TACTILE ONLY)
# ========================================================================

def generate_baseline_trials():
    """Generate baseline trials (breathing + tactile only, no looming)"""
    print("\n" + "=" * 70)
    print("STEP 5: GENERATING BASELINE TRIALS (TACTILE ONLY)")
    print("=" * 70)

    # Load breathing instructions
    print("\nLoading breathing instructions...")
    inhale_audio = load_breathing_instruction(INHALE_INSTRUCTION, "INHALE")
    exhale_audio = load_breathing_instruction(EXHALE_INSTRUCTION, "EXHALE")

    # Get tactile files (skip 0ms)
    tactile_files = [f"tactile_stimulus_{delay}ms.wav" for delay in ONSET_DELAYS_MS[1:]]

    print(f"\nProcessing {len(tactile_files)} tactile stimuli...")

    inhale_count = 0
    exhale_count = 0

    for tactile_file in tactile_files:
        # Load tactile stimulus
        tactile_path = OUTPUT_DIRS['tactile'] / tactile_file
        tactile_audio, tactile_sr = sf.read(tactile_path)

        if tactile_sr != SAMPLE_RATE:
            print(f"  âœ— Sample rate mismatch: {tactile_file}")
            continue

        # Create EXACTLY 4-second baseline stimulus (500ms padding + tactile + remainder)
        # Stereo: LEFT=tactile, RIGHT=silence
        target_samples = int(STIMULUS_DURATION * SAMPLE_RATE)  # Exactly 4.0 seconds
        prepend_samples = int(0.5 * SAMPLE_RATE)  # 500ms before
        current_samples = len(tactile_audio)

        # Calculate append padding to reach exactly 4.0 seconds
        append_samples = target_samples - current_samples - prepend_samples

        # Create stereo baseline with exact duration
        baseline_stereo = np.zeros((target_samples, 2))

        # Add tactile to left channel with 500ms offset
        baseline_stereo[prepend_samples:prepend_samples + current_samples, 0] = tactile_audio

        # Verify exact duration
        actual_duration = len(baseline_stereo) / SAMPLE_RATE
        if abs(actual_duration - STIMULUS_DURATION) > 0.001:  # Within 1ms tolerance
            print(f"  âš  Warning: {tactile_file} baseline duration {actual_duration:.4f}s (target: {STIMULUS_DURATION}s)")

        # Combine with INHALE
        inhale_trial = combine_breathing_and_stimulus(inhale_audio, baseline_stereo, TRIAL_DURATION)
        inhale_output = OUTPUT_DIRS['baseline_inhale'] / f"baseline_{tactile_file}"
        sf.write(inhale_output, inhale_trial, SAMPLE_RATE)
        inhale_count += 1

        # Combine with EXHALE
        exhale_trial = combine_breathing_and_stimulus(exhale_audio, baseline_stereo, TRIAL_DURATION)
        exhale_output = OUTPUT_DIRS['baseline_exhale'] / f"baseline_{tactile_file}"
        sf.write(exhale_output, exhale_trial, SAMPLE_RATE)
        exhale_count += 1

    print(f"\nâœ“ Generated {inhale_count} INHALE baseline trials")
    print(f"âœ“ Generated {exhale_count} EXHALE baseline trials")
    print(f"âœ“ Total: {inhale_count + exhale_count} baseline trials")


# ========================================================================
# STEP 6: GENERATE CATCH TRIALS (LOOMING ONLY)
# ========================================================================

def generate_catch_trials():
    """Generate catch trials (breathing + looming only, no tactile)"""
    print("\n" + "=" * 70)
    print("STEP 6: GENERATING CATCH TRIALS (LOOMING ONLY)")
    print("=" * 70)

    # Load breathing instructions
    print("\nLoading breathing instructions...")
    inhale_audio = load_breathing_instruction(INHALE_INSTRUCTION, "INHALE")
    exhale_audio = load_breathing_instruction(EXHALE_INSTRUCTION, "EXHALE")

    # Get looming files
    looming_files = {
        'pink': 'Loom-1-pink.wav',
        'blue': 'Loom-2-blue.wav',
        'white': 'Loom-3-white.wav',
        'brown': 'Loom-4-brown.wav',
    }

    # SOAs for catch trials
    catch_soas = ONSET_DELAYS_MS[1:]  # Skip 0ms

    print(f"\nGenerating catch trials for {len(catch_soas)} SOAs Ã— {len(looming_files)} noise types...")

    inhale_count = 0
    exhale_count = 0

    for soa_ms in catch_soas:
        for noise_name, looming_file in looming_files.items():
            # Load looming stimulus
            looming_path = OUTPUT_DIRS['looming'] / looming_file
            looming_audio, looming_sr = sf.read(looming_path)

            if looming_sr != SAMPLE_RATE:
                print(f"  âœ— Sample rate mismatch: {looming_file}")
                continue

            # The looming stimuli should already be 4 seconds (from pre-generated files)
            # Just ensure they are exactly 4.0 seconds
            target_samples = int(STIMULUS_DURATION * SAMPLE_RATE)  # Exactly 4.0 seconds
            current_samples = len(looming_audio)

            # Pad or trim to exactly 4.0 seconds
            if current_samples < target_samples:
                # Pad with silence at the end
                padding = np.zeros((target_samples - current_samples, 2))
                looming_extended = np.vstack([looming_audio, padding])
            elif current_samples > target_samples:
                # Trim to exact length
                looming_extended = looming_audio[:target_samples]
            else:
                # Already perfect length
                looming_extended = looming_audio

            # Verify exact duration
            actual_duration = len(looming_extended) / SAMPLE_RATE
            if abs(actual_duration - STIMULUS_DURATION) > 0.001:  # Within 1ms tolerance
                print(f"  âš  Warning: Catch {noise_name} SOA{soa_ms} duration {actual_duration:.4f}s (target: {STIMULUS_DURATION}s)")

            # Create catch stimulus: LEFT=silence, RIGHT=looming
            catch_stereo = np.zeros_like(looming_extended)
            catch_stereo[:, 1] = looming_extended[:, 1]  # Right channel only

            # Create filename
            catch_filename = f"catch_SOA{soa_ms}ms_{noise_name}.wav"

            # Combine with INHALE
            inhale_trial = combine_breathing_and_stimulus(inhale_audio, catch_stereo, TRIAL_DURATION)
            inhale_output = OUTPUT_DIRS['catch_inhale'] / catch_filename
            sf.write(inhale_output, inhale_trial, SAMPLE_RATE)
            inhale_count += 1

            # Combine with EXHALE
            exhale_trial = combine_breathing_and_stimulus(exhale_audio, catch_stereo, TRIAL_DURATION)
            exhale_output = OUTPUT_DIRS['catch_exhale'] / catch_filename
            sf.write(exhale_output, exhale_trial, SAMPLE_RATE)
            exhale_count += 1

    print(f"\nâœ“ Generated {inhale_count} INHALE catch trials")
    print(f"âœ“ Generated {exhale_count} EXHALE catch trials")
    print(f"âœ“ Total: {inhale_count + exhale_count} catch trials")


# ========================================================================
# STEP 7: GENERATE MASTER BLOCKS
# ========================================================================

def generate_master_blocks():
    """Generate master block trial structures"""
    print("\n" + "=" * 70)
    print("STEP 7: GENERATING MASTER BLOCKS")
    print("=" * 70)

    # Master Block 1 structure (44 trials)
    master_block_1 = [
        # Audio-Tactile trials (20 trials: 10 Inhale, 10 Exhale)
        ['Audio-Tactile', 300, 'Pink', 'Inhale'],
        ['Audio-Tactile', 300, 'Blue', 'Exhale'],
        ['Audio-Tactile', 300, 'White', 'Inhale'],
        ['Audio-Tactile', 300, 'Brown', 'Exhale'],
        ['Audio-Tactile', 800, 'Pink', 'Inhale'],
        ['Audio-Tactile', 800, 'Blue', 'Exhale'],
        ['Audio-Tactile', 800, 'White', 'Inhale'],
        ['Audio-Tactile', 800, 'Brown', 'Exhale'],
        ['Audio-Tactile', 1500, 'Pink', 'Inhale'],
        ['Audio-Tactile', 1500, 'Blue', 'Exhale'],
        ['Audio-Tactile', 1500, 'White', 'Inhale'],
        ['Audio-Tactile', 1500, 'Brown', 'Exhale'],
        ['Audio-Tactile', 2200, 'Pink', 'Inhale'],
        ['Audio-Tactile', 2200, 'Blue', 'Exhale'],
        ['Audio-Tactile', 2200, 'White', 'Inhale'],
        ['Audio-Tactile', 2200, 'Brown', 'Exhale'],
        ['Audio-Tactile', 2700, 'Pink', 'Inhale'],
        ['Audio-Tactile', 2700, 'Blue', 'Exhale'],
        ['Audio-Tactile', 2700, 'White', 'Inhale'],
        ['Audio-Tactile', 2700, 'Brown', 'Exhale'],

        # Baseline trials (20 trials: 10 Inhale, 10 Exhale)
        ['Baseline', 300, 'N/A', 'Inhale'],
        ['Baseline', 300, 'N/A', 'Exhale'],
        ['Baseline', 800, 'N/A', 'Inhale'],
        ['Baseline', 800, 'N/A', 'Exhale'],
        ['Baseline', 1500, 'N/A', 'Inhale'],
        ['Baseline', 1500, 'N/A', 'Exhale'],
        ['Baseline', 2200, 'N/A', 'Inhale'],
        ['Baseline', 2200, 'N/A', 'Exhale'],
        ['Baseline', 2700, 'N/A', 'Inhale'],
        ['Baseline', 2700, 'N/A', 'Exhale'],
        ['Baseline', 300, 'N/A', 'Inhale'],
        ['Baseline', 300, 'N/A', 'Exhale'],
        ['Baseline', 800, 'N/A', 'Inhale'],
        ['Baseline', 800, 'N/A', 'Exhale'],
        ['Baseline', 1500, 'N/A', 'Inhale'],
        ['Baseline', 1500, 'N/A', 'Exhale'],
        ['Baseline', 2200, 'N/A', 'Inhale'],
        ['Baseline', 2200, 'N/A', 'Exhale'],
        ['Baseline', 2700, 'N/A', 'Inhale'],
        ['Baseline', 2700, 'N/A', 'Exhale'],

        # Catch trials (4 trials: 2 Inhale, 2 Exhale)
        ['Catch', 800, 'Pink', 'Inhale'],
        ['Catch', 1500, 'Brown', 'Exhale'],
        ['Catch', 2200, 'White', 'Inhale'],
        ['Catch', 2700, 'Blue', 'Exhale'],
    ]

    # Master Block 2 structure (complementary to Block 1)
    master_block_2 = [
        # Audio-Tactile trials (20 trials: 10 Inhale, 10 Exhale)
        ['Audio-Tactile', 300, 'Pink', 'Exhale'],
        ['Audio-Tactile', 300, 'Blue', 'Inhale'],
        ['Audio-Tactile', 300, 'White', 'Exhale'],
        ['Audio-Tactile', 300, 'Brown', 'Inhale'],
        ['Audio-Tactile', 800, 'Pink', 'Exhale'],
        ['Audio-Tactile', 800, 'Blue', 'Inhale'],
        ['Audio-Tactile', 800, 'White', 'Exhale'],
        ['Audio-Tactile', 800, 'Brown', 'Inhale'],
        ['Audio-Tactile', 1500, 'Pink', 'Exhale'],
        ['Audio-Tactile', 1500, 'Blue', 'Inhale'],
        ['Audio-Tactile', 1500, 'White', 'Exhale'],
        ['Audio-Tactile', 1500, 'Brown', 'Inhale'],
        ['Audio-Tactile', 2200, 'Pink', 'Exhale'],
        ['Audio-Tactile', 2200, 'Blue', 'Inhale'],
        ['Audio-Tactile', 2200, 'White', 'Exhale'],
        ['Audio-Tactile', 2200, 'Brown', 'Inhale'],
        ['Audio-Tactile', 2700, 'Pink', 'Exhale'],
        ['Audio-Tactile', 2700, 'Blue', 'Inhale'],
        ['Audio-Tactile', 2700, 'White', 'Exhale'],
        ['Audio-Tactile', 2700, 'Brown', 'Inhale'],

        # Baseline trials (20 trials: 10 Inhale, 10 Exhale)
        ['Baseline', 300, 'N/A', 'Exhale'],
        ['Baseline', 300, 'N/A', 'Inhale'],
        ['Baseline', 800, 'N/A', 'Exhale'],
        ['Baseline', 800, 'N/A', 'Inhale'],
        ['Baseline', 1500, 'N/A', 'Exhale'],
        ['Baseline', 1500, 'N/A', 'Inhale'],
        ['Baseline', 2200, 'N/A', 'Exhale'],
        ['Baseline', 2200, 'N/A', 'Inhale'],
        ['Baseline', 2700, 'N/A', 'Exhale'],
        ['Baseline', 2700, 'N/A', 'Inhale'],
        ['Baseline', 300, 'N/A', 'Exhale'],
        ['Baseline', 300, 'N/A', 'Inhale'],
        ['Baseline', 800, 'N/A', 'Exhale'],
        ['Baseline', 800, 'N/A', 'Inhale'],
        ['Baseline', 1500, 'N/A', 'Exhale'],
        ['Baseline', 1500, 'N/A', 'Inhale'],
        ['Baseline', 2200, 'N/A', 'Exhale'],
        ['Baseline', 2200, 'N/A', 'Inhale'],
        ['Baseline', 2700, 'N/A', 'Exhale'],
        ['Baseline', 2700, 'N/A', 'Inhale'],

        # Catch trials (4 trials: 2 Inhale, 2 Exhale)
        ['Catch', 300, 'Blue', 'Inhale'],
        ['Catch', 800, 'Pink', 'Exhale'],
        ['Catch', 1500, 'Brown', 'Inhale'],
        ['Catch', 2700, 'White', 'Exhale'],
    ]

    # Save master blocks
    header = ['Trial_Type', 'SOA_ms', 'Noise_Type', 'Respiratory_Phase']

    # Save Master Block 1
    block1_path = OUTPUT_DIRS['master_blocks'] / "Master_Block_1.csv"
    with open(block1_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(master_block_1)
    print(f"âœ“ Saved Master_Block_1.csv ({len(master_block_1)} trials)")

    # Save Master Block 2
    block2_path = OUTPUT_DIRS['master_blocks'] / "Master_Block_2.csv"
    with open(block2_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(master_block_2)
    print(f"âœ“ Saved Master_Block_2.csv ({len(master_block_2)} trials)")

    print(f"\nâœ“ Generated 2 master blocks")


# ========================================================================
# STEP 8: GENERATE EXPERIMENT BLOCKS
# ========================================================================

def generate_experiment_blocks():
    """Generate 6 experiment blocks (a-f) with randomized trial orders"""
    print("\n" + "=" * 70)
    print("STEP 8: GENERATING EXPERIMENT BLOCKS")
    print("=" * 70)

    # Load master blocks
    block1_path = OUTPUT_DIRS['master_blocks'] / "Master_Block_1.csv"
    block2_path = OUTPUT_DIRS['master_blocks'] / "Master_Block_2.csv"

    master_block_1 = []
    with open(block1_path, 'r') as f:
        reader = csv.reader(f)
        header = next(reader)
        master_block_1 = list(reader)

    master_block_2 = []
    with open(block2_path, 'r') as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        master_block_2 = list(reader)

    # Create 6 blocks (3 Ã— Block1, 3 Ã— Block2)
    blocks = {
        'block_a': master_block_1.copy(),
        'block_b': master_block_2.copy(),
        'block_c': master_block_1.copy(),
        'block_d': master_block_2.copy(),
        'block_e': master_block_1.copy(),
        'block_f': master_block_2.copy(),
    }

    # Randomize each block
    print(f"\nRandomizing trial orders with seed {RANDOM_SEED}...")
    rng = random.Random(RANDOM_SEED)
    for block_name, trials in blocks.items():
        rng.shuffle(trials)

        # Save CSV
        csv_path = OUTPUT_DIRS['experiment_blocks'] / f"{block_name}.csv"
        with open(csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(trials)

        print(f"  âœ“ {block_name}.csv ({len(trials)} trials)")

    print(f"\nâœ“ Generated {len(blocks)} experiment blocks")


# ========================================================================
# STEP 9: GENERATE PARTICIPANT SEQUENCES
# ========================================================================

def _read_experiment_block(block_letter):
    """Read one randomized experiment block CSV as dictionaries."""
    path = OUTPUT_DIRS['experiment_blocks'] / f"block_{block_letter}.csv"
    with open(path, 'r', newline='') as f:
        return list(csv.DictReader(f))


def _noise_index(noise_type):
    noise = noise_type.strip().lower()
    return NOISE_TYPES.index(noise) + 1


def _trial_audio_path(trial):
    """Resolve a trial-row dictionary to its generated 8-second WAV."""
    trial_type = trial['Trial_Type'].strip()
    phase = trial['Respiratory_Phase'].strip().lower()
    soa_ms = str(int(float(trial['SOA_ms'])))
    noise = trial['Noise_Type'].strip().lower()

    if phase not in {"inhale", "exhale"}:
        raise ValueError(f"Unsupported respiratory phase: {trial['Respiratory_Phase']}")

    if trial_type == "Audio-Tactile":
        idx = _noise_index(noise)
        filename = f"Stereo_LEFT_tactile_stimulus_{soa_ms}ms__RIGHT_Loom-{idx}-{noise}.wav"
        return OUTPUT_DIRS[f'breathing_looming_tactile_{phase}'] / filename

    if trial_type == "Baseline":
        return OUTPUT_DIRS[f'baseline_{phase}'] / f"baseline_tactile_stimulus_{soa_ms}ms.wav"

    if trial_type == "Catch":
        return OUTPUT_DIRS[f'catch_{phase}'] / f"catch_SOA{soa_ms}ms_{noise}.wav"

    raise ValueError(f"Unsupported trial type: {trial_type}")


def _load_trial_audio(path):
    audio, sr = sf.read(path, always_2d=True)
    if sr != SAMPLE_RATE:
        raise ValueError(f"Sample-rate mismatch in {path}: {sr} Hz")
    if audio.shape[1] == 1:
        audio = np.column_stack([audio[:, 0], np.zeros(len(audio))])
    elif audio.shape[1] > 2:
        audio = audio[:, :2]
    return audio


def _write_participant_block(participant_dir, participant_id, position, block_letter, rows):
    """Write one ordered block CSV and its concatenated WAV."""
    block_label = f"{position}{block_letter}"
    csv_path = participant_dir / f"{block_label}.csv"
    wav_path = participant_dir / f"{block_label}_concatenated.wav"
    fieldnames = [
        "Trial_Number",
        "Block_Number",
        "Block_Letter",
        "Trial_Type",
        "SOA_ms",
        "Noise_Type",
        "Respiratory_Phase",
        "Audio_File",
    ]

    manifest_rows = []
    audio_chunks = []
    for trial_number, row in enumerate(rows, start=1):
        audio_path = _trial_audio_path(row)
        if not audio_path.exists():
            raise FileNotFoundError(f"Generated trial WAV not found: {audio_path}")
        audio_chunks.append(_load_trial_audio(audio_path))
        manifest_rows.append(
            {
                "Trial_Number": trial_number,
                "Block_Number": position,
                "Block_Letter": block_letter.upper(),
                "Trial_Type": row["Trial_Type"],
                "SOA_ms": row["SOA_ms"],
                "Noise_Type": row["Noise_Type"],
                "Respiratory_Phase": row["Respiratory_Phase"],
                "Audio_File": str(audio_path.relative_to(OUTPUT_DIR)),
            }
        )

    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    block_audio = np.vstack(audio_chunks).astype(np.float32)
    sf.write(wav_path, block_audio, SAMPLE_RATE)
    print(f"    {participant_id}: wrote {wav_path.name} ({len(manifest_rows)} trials)")
    return manifest_rows


def generate_participant_sequences(num_participants=50):
    """Generate counterbalanced block sequences and playable block WAVs."""
    print("\n" + "=" * 70)
    print("STEP 9: GENERATING PARTICIPANT SEQUENCES")
    print("=" * 70)

    # All possible block orders (6! = 720 permutations, but we'll use Latin square)
    blocks = ['a', 'b', 'c', 'd', 'e', 'f']

    # Generate Latin square counterbalancing
    # Each participant gets all 6 blocks in a different order
    all_orders = list(permutations(blocks))

    print(f"\nGenerating sequences for {num_participants} participants...")
    print(f"Total possible orders: {len(all_orders)}")

    order_rows = []
    readme_path = OUTPUT_DIRS['participant_sequences'] / "README.txt"
    with open(readme_path, 'w', newline='') as f:
        f.write("Participant folders contain numbered block CSVs and matching concatenated WAVs.\n")
        f.write("Run blocks in filename order: 1a, 2f, 3b, and so on.\n")
        f.write("Generated artifacts are local outputs and are ignored by Git.\n")

    # Assign orders to participants (cycle through if needed)
    for p in range(1, num_participants + 1):
        # Select order (cycle through all possible orders)
        order_idx = (p - 1) % len(all_orders)
        participant_order = all_orders[order_idx]
        participant_id = f"P{p:02d}"

        # Create participant directory
        participant_dir = OUTPUT_DIRS['participant_sequences'] / participant_id
        participant_dir.mkdir(parents=True, exist_ok=True)

        full_rows = []
        for position, block in enumerate(participant_order, start=1):
            block_rows = _read_experiment_block(block)
            full_rows.extend(
                _write_participant_block(participant_dir, participant_id, position, block, block_rows)
            )

        full_sequence_path = participant_dir / f"{participant_id}_full_sequence.csv"
        with open(full_sequence_path, 'w', newline='') as f:
            fieldnames = ["Global_Trial_Number"] + list(full_rows[0])
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for global_trial, row in enumerate(full_rows, start=1):
                writer.writerow({"Global_Trial_Number": global_trial, **row})

        summary_path = participant_dir / f"{participant_id}_summary.txt"
        with open(summary_path, 'w') as f:
            f.write(f"{participant_id}\n")
            f.write(f"Block order: {' -> '.join(participant_order)}\n")
            f.write(f"Total blocks: {len(participant_order)}\n")
            f.write(f"Total trials: {len(full_rows)}\n")
            f.write(f"Estimated block duration: {len(block_rows) * TRIAL_DURATION:.1f} seconds\n")

        order_rows.append(
            {
                "Participant_ID": participant_id,
                **{f"Block_{idx}": block.upper() for idx, block in enumerate(participant_order, start=1)},
            }
        )

    order_path = OUTPUT_DIRS['participant_sequences'] / "participant_block_orders.csv"
    with open(order_path, 'w', newline='') as f:
        fieldnames = ["Participant_ID"] + [f"Block_{idx}" for idx in range(1, 7)]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(order_rows)

    print(f"\nâœ“ Generated sequences for {num_participants} participants")


# ========================================================================
# MAIN EXECUTION
# ========================================================================

def main():
    """Main execution function - runs entire stimulus generation pipeline"""
    print("\n" + "=" * 70)
    print("PERIPERSONAL SPACE EXPERIMENT - STIMULUS GENERATOR")
    print("=" * 70)

    print("\nDIRECTORY CONFIGURATION:")
    print(f"  ROOT:   {ROOT_DIRECTORY.resolve()}")
    print(f"  INPUT:  {INPUT_DIR.resolve()}")
    print(f"  OUTPUT: {OUTPUT_DIR.resolve()}")
    print("  (Use pps-generate CLI flags to override these paths.)")

    print("\nUPDATED PARAMETERS:")
    print(f"  Looming distance: {INITIAL_DISTANCE*100:.0f} cm â†’ {FINAL_DISTANCE*100:.0f} cm")
    print(f"  Duration: {LOOMING_DURATION} seconds")
    print(f"  Velocity: {APPROACH_VELOCITY*100:.1f} cm/s")
    print(f"  Sample rate: {SAMPLE_RATE} Hz")
    print("\n" + "=" * 70)

    # Check for required input files
    print("\nChecking required input files...")
    missing_files = []

    if not SOFA_FILE.exists():
        missing_files.append(f"HRTF SOFA file: {SOFA_FILE}")
    else:
        print(f"  âœ“ HRTF file found: {SOFA_FILE.name}")

    if not INHALE_INSTRUCTION.exists():
        missing_files.append(f"Inhale instruction: {INHALE_INSTRUCTION}")
    else:
        print(f"  âœ“ Inhale instruction found: {INHALE_INSTRUCTION.name}")

    if not EXHALE_INSTRUCTION.exists():
        missing_files.append(f"Exhale instruction: {EXHALE_INSTRUCTION}")
    else:
        print(f"  âœ“ Exhale instruction found: {EXHALE_INSTRUCTION.name}")

    if missing_files:
        print("\nâœ— ERROR: Missing required files:")
        for file in missing_files:
            print(f"    {file}")
        print("\nPlease ensure all required files are in place before running.")
        return

    # Create directory structure
    create_directories()

    # Execute pipeline steps
    try:
        # Step 1: Generate tactile stimuli
        generate_tactile_stimulus()

        # Step 2: Generate looming stimuli
        generate_all_looming_stimuli()

        # Step 3: Combine looming Ã— tactile
        combine_looming_tactile_stimuli()

        # Step 4: Add breathing instructions to looming-tactile trials
        generate_breathing_looming_tactile_trials()

        # Step 5: Generate baseline trials
        generate_baseline_trials()

        # Step 6: Generate catch trials
        generate_catch_trials()

        # Step 7: Generate master blocks
        generate_master_blocks()

        # Step 8: Generate experiment blocks
        generate_experiment_blocks()

        # Step 9: Generate participant sequences
        generate_participant_sequences(num_participants=50)

        # Final summary
        print("\n" + "=" * 70)
        print("STIMULUS GENERATION COMPLETE!")
        print("=" * 70)

        print("\nGenerated stimuli:")
        print(f"  âœ“ Tactile stimuli: {len(ONSET_DELAYS_MS)} files")
        print(f"  âœ“ Looming stimuli: {len(NOISE_TYPES)} files")
        print(f"  âœ“ Looming Ã— Tactile: {len(ONSET_DELAYS_MS[1:]) * len(NOISE_TYPES)} files")
        print(f"  âœ“ Audio-tactile trials: {len(ONSET_DELAYS_MS[1:]) * len(NOISE_TYPES) * 2} files (Inhale + Exhale)")
        print(f"  âœ“ Baseline trials: {len(ONSET_DELAYS_MS[1:]) * 2} files (Inhale + Exhale)")
        print(f"  âœ“ Catch trials: {len(ONSET_DELAYS_MS[1:]) * len(NOISE_TYPES) * 2} files (Inhale + Exhale)")
        print(f"  âœ“ Master blocks: 2 files")
        print(f"  âœ“ Experiment blocks: 6 files")
        print(f"  âœ“ Participant sequences: 50 participants")

        print("\nAll stimuli saved to:")
        print(f"  OUTPUT: {OUTPUT_DIR}")
        print(f"\nInput files used from:")
        print(f"  INPUT:  {INPUT_DIR}")

        print("\n" + "=" * 70)
        print("You can now use these stimuli for your experiment!")
        print("=" * 70)

    except Exception as e:
        print(f"\nâœ— ERROR during stimulus generation:")
        print(f"  {e}")
        import traceback
        traceback.print_exc()
        return


if __name__ == "__main__":
    # Set random seed for reproducibility
    np.random.seed(42)

    # Run main pipeline
    main()
