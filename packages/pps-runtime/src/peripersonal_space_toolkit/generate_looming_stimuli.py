"""
========================================================================
LOOMING STIMULI GENERATOR - STANDALONE SCRIPT
========================================================================

This script generates frontal looming audio stimuli with HRTF spatial filtering.

PARAMETERS:
- Initial distance: 110 cm (1.1 m)
- Final distance: 10 cm (0.1 m)
- Duration: 3 seconds
- Velocity: 33.3 cm/s
- Noise types: Pink, Blue, White, Brown
- HRTF: Frontal approach (0° azimuth, 0° elevation)

USAGE:
    python generate_looming_stimuli.py

OUTPUT:
    Creates 4 WAV files (continuous 3-second looming sounds):
    - Loom-1-pink.wav   (3.0s continuous approach)
    - Loom-2-blue.wav   (3.0s continuous approach)
    - Loom-3-white.wav  (3.0s continuous approach)
    - Loom-4-brown.wav  (3.0s continuous approach)

    NOTE: These are continuous sounds, NOT with SOAs.
    SOAs are applied to tactile stimuli when combined later.

REQUIREMENTS:
    - numpy
    - scipy
    - soundfile
    - sofar (or pysofaconventions)
    - FABIAN_HRIR_measured_HATO_0.sofa file in subdirectory

Author: George Fejer
Date: 2025
========================================================================
"""

import numpy as np
import scipy.signal as signal
import soundfile as sf
from pathlib import Path
import sys

# Try to import SOFA library
try:
    import sofar as sf_sofa
    HAS_SOFA = True
    print("✓ Using sofar library")
except ImportError:
    try:
        import pysofaconventions as sofa
        HAS_SOFA = True
        print("✓ Using pysofaconventions library")
    except ImportError:
        print("✗ ERROR: No SOFA library found!")
        print("  Install with: pip install sofar")
        print("  Or: pip install pysofaconventions")
        sys.exit(1)

# ========================================================================
# CONFIGURATION
# ========================================================================

# Directories
SCRIPT_DIR = Path(__file__).parent
SOFA_FILE = SCRIPT_DIR / "0. Head-Related Impulse Response (HRIR) model" / "FABIAN_HRIR_measured_HATO_0.sofa"
OUTPUT_DIR = SCRIPT_DIR / "1. Looming Stimuli"  # Save to dedicated looming stimuli folder

# Audio parameters
SAMPLE_RATE = 44100

# Looming parameters (UPDATED: 110 cm → 10 cm)
INITIAL_DISTANCE = 1.1      # 110 cm
FINAL_DISTANCE = 0.1        # 10 cm
LOOMING_DURATION = 3.0      # 3 seconds
APPROACH_VELOCITY = (INITIAL_DISTANCE - FINAL_DISTANCE) / LOOMING_DURATION  # 33.3 cm/s

# Spatial parameters
AZIMUTH_ANGLE = 0           # Frontal (0 degrees)
ELEVATION_ANGLE = 0         # Ear level

# Distance attenuation
USE_INVERSE_SQUARE_LAW = True

# Volume
VOLUME_LEVEL = 0.7

# Noise types
NOISE_TYPES = ['pink', 'blue', 'white', 'brown']

# ========================================================================
# NOISE GENERATION FUNCTIONS
# ========================================================================

def generate_white_noise(duration, sample_rate):
    """Generate white noise"""
    samples = int(duration * sample_rate)
    return np.random.randn(samples)


def generate_pink_noise(duration, sample_rate):
    """Generate pink noise (1/f power spectrum)"""
    samples = int(duration * sample_rate)
    white = np.random.randn(samples)
    
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(samples, 1/sample_rate)
    freqs[0] = 1  # Avoid division by zero
    
    fft = fft / np.sqrt(freqs)
    pink = np.fft.irfft(fft, n=samples)
    return pink


def generate_blue_noise(duration, sample_rate):
    """Generate blue noise (f power spectrum)"""
    samples = int(duration * sample_rate)
    white = np.random.randn(samples)
    
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(samples, 1/sample_rate)
    
    fft = fft * np.sqrt(freqs)
    blue = np.fft.irfft(fft, n=samples)
    return blue


def generate_brown_noise(duration, sample_rate):
    """Generate brown noise (1/f^2 power spectrum)"""
    samples = int(duration * sample_rate)
    white = np.random.randn(samples)
    
    brown = np.cumsum(white)
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
    noise = noise / np.max(np.abs(noise)) * 0.95
    
    return noise


# ========================================================================
# HRTF FUNCTIONS
# ========================================================================

def load_hrtf(sofa_path):
    """Load HRTF data from SOFA file"""
    if not sofa_path.exists():
        raise FileNotFoundError(f"SOFA file not found: {sofa_path}")

    print(f"\nLoading HRTF from: {sofa_path.name}")

    # Load using sofar
    hrtf = sf_sofa.read_sofa(str(sofa_path))

    print(f"✓ HRTF loaded successfully")
    print(f"  Convention: {hrtf.GLOBAL_SOFAConventions} v{hrtf.GLOBAL_SOFAConventionsVersion}")
    print(f"  HRTF shape: {hrtf.Data_IR.shape}")

    return hrtf


def find_frontal_hrtf(hrtf, target_azimuth=0, target_elevation=0):
    """Find the HRTF measurement closest to frontal position"""
    # Get source positions from SOFA file
    source_positions = np.array(hrtf.SourcePosition)

    # Handle different array shapes
    if source_positions.shape[0] == 3 and len(source_positions.shape) == 2:
        source_positions = source_positions.T

    # Determine if positions are in degrees or radians
    max_azimuth = np.max(np.abs(source_positions[:, 0]))
    positions_in_degrees = max_azimuth > 6.28

    if positions_in_degrees:
        az_target = target_azimuth
        el_target = target_elevation
    else:
        az_target = np.deg2rad(target_azimuth)
        el_target = np.deg2rad(target_elevation)

    # Find nearest position
    distances = np.sqrt(
        (source_positions[:, 0] - az_target)**2 +
        (source_positions[:, 1] - el_target)**2
    )

    nearest_idx = np.argmin(distances)
    nearest_pos = source_positions[nearest_idx]

    return nearest_idx, nearest_pos


def extract_hrtf_filters(hrtf, position_idx):
    """Extract left and right ear HRTF filters"""
    # Get HRTF impulse response data
    hrtf_data = hrtf.Data_IR

    # Extract left and right ear filters
    # Data_IR shape is typically (measurements, receivers, samples)
    # receivers: 0=left ear, 1=right ear
    hrtf_left = hrtf_data[position_idx, 0, :]
    hrtf_right = hrtf_data[position_idx, 1, :]

    return hrtf_left, hrtf_right


def create_amplitude_envelope(duration, sample_rate, initial_distance, final_distance, use_inverse_square=True):
    """Create distance-based amplitude envelope for looming sound"""
    num_samples = int(duration * sample_rate)

    # Linear distance trajectory
    distances = np.linspace(initial_distance, final_distance, num_samples)

    if use_inverse_square:
        # Inverse square law: Amplitude ∝ 1/distance
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
# LOOMING STIMULUS GENERATION
# ========================================================================

def generate_looming_stimulus(hrtf, noise_type):
    """
    Generate a frontal looming stimulus with HRTF spatial filtering

    Processing chain:
    1. Generate noise signal
    2. Apply frontal HRTF (spatial filtering)
    3. Apply distance-based amplitude envelope
    4. Return stereo signal
    """
    print(f"\n  Processing {noise_type} noise...")

    # Step 1: Generate source noise
    print(f"    1. Generating {noise_type} noise ({LOOMING_DURATION}s)...")
    source_signal = generate_noise(noise_type, LOOMING_DURATION, SAMPLE_RATE)

    # Step 2: Find and apply frontal HRTF
    print(f"    2. Finding frontal HRTF position...")
    nearest_idx, nearest_pos = find_frontal_hrtf(hrtf, AZIMUTH_ANGLE, ELEVATION_ANGLE)
    print(f"       Position: azimuth={nearest_pos[0]:.1f}°, elevation={nearest_pos[1]:.1f}°")

    print(f"    3. Extracting HRTF filters...")
    hrtf_left, hrtf_right = extract_hrtf_filters(hrtf, nearest_idx)

    print(f"    4. Applying HRTF convolution (this may take a moment)...")
    # Apply HRTF filters (spectral coloring from head/pinnae)
    filtered_left = signal.fftconvolve(source_signal, hrtf_left, mode='same')
    filtered_right = signal.fftconvolve(source_signal, hrtf_right, mode='same')

    # Step 3: Create distance-based amplitude envelope
    print(f"    5. Creating distance-based amplitude envelope...")
    amplitude_envelope, distances = create_amplitude_envelope(
        LOOMING_DURATION, SAMPLE_RATE, INITIAL_DISTANCE, FINAL_DISTANCE, USE_INVERSE_SQUARE_LAW
    )

    # Step 4: Apply amplitude envelope to both channels
    print(f"    6. Applying amplitude envelope...")
    output_left = filtered_left * amplitude_envelope
    output_right = filtered_right * amplitude_envelope

    # Combine into stereo signal
    output_signal = np.column_stack([output_left, output_right])

    # Normalize
    max_val = np.max(np.abs(output_signal))
    if max_val > 0:
        output_signal = output_signal / max_val * 0.95

    print(f"    ✓ Complete!")

    return output_signal, distances


# ========================================================================
# MAIN EXECUTION
# ========================================================================

def main():
    """Main execution function"""
    print("\n" + "=" * 70)
    print("LOOMING STIMULI GENERATOR")
    print("=" * 70)

    print("\nPARAMETERS:")
    print(f"  Initial distance: {INITIAL_DISTANCE*100:.0f} cm")
    print(f"  Final distance: {FINAL_DISTANCE*100:.0f} cm")
    print(f"  Duration: {LOOMING_DURATION} seconds")
    print(f"  Approach velocity: {APPROACH_VELOCITY*100:.1f} cm/s")
    print(f"  Sample rate: {SAMPLE_RATE} Hz")
    print(f"  Distance model: {'Inverse square law' if USE_INVERSE_SQUARE_LAW else 'Linear'}")

    print("\nDIRECTORIES:")
    print(f"  Script: {SCRIPT_DIR}")
    print(f"  SOFA file: {SOFA_FILE}")
    print(f"  Output: {OUTPUT_DIR}")

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"  ✓ Output directory created/verified")

    # Check SOFA file exists
    if not SOFA_FILE.exists():
        print(f"\n✗ ERROR: SOFA file not found!")
        print(f"  Expected: {SOFA_FILE}")
        print(f"\n  Please ensure the HRTF file is in the correct location.")
        return

    # Load HRTF
    print("\n" + "=" * 70)
    print("LOADING HRTF")
    print("=" * 70)

    try:
        hrtf = load_hrtf(SOFA_FILE)
    except Exception as e:
        print(f"\n✗ ERROR loading HRTF: {e}")
        import traceback
        traceback.print_exc()
        return

    # Generate each noise type
    print("\n" + "=" * 70)
    print("GENERATING LOOMING STIMULI")
    print("=" * 70)

    generated_files = []

    for idx, noise_type in enumerate(NOISE_TYPES, start=1):
        print(f"\n[{idx}/{len(NOISE_TYPES)}] Generating {noise_type} noise looming stimulus...")

        try:
            # Generate looming stimulus
            output_signal, distances = generate_looming_stimulus(hrtf, noise_type)

            # Save audio file
            filename = f"Loom-{idx}-{noise_type}.wav"
            output_path = OUTPUT_DIR / filename

            print(f"    7. Saving to: {filename}")
            sf.write(output_path, output_signal, SAMPLE_RATE)

            print(f"    ✓ Saved: {filename}")
            generated_files.append(filename)

        except Exception as e:
            print(f"    ✗ ERROR: {e}")
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 70)
    print("GENERATION COMPLETE!")
    print("=" * 70)

    print(f"\n✓ Generated {len(generated_files)}/{len(NOISE_TYPES)} looming stimuli:")
    for filename in generated_files:
        print(f"  - {filename}")

    print(f"\nFiles saved to: {OUTPUT_DIR}")

    # Print SOA-to-distance mapping (for reference when combining with tactile stimuli)
    print("\n" + "=" * 70)
    print("REFERENCE: SOA-TO-DISTANCE MAPPING")
    print("=" * 70)
    print(f"\nNOTE: Looming stimuli are continuous 3-second sounds.")
    print(f"When combined with tactile stimuli (which have SOAs),")
    print(f"the looming sound will be at these distances when tactile occurs:")
    print(f"\nAt {APPROACH_VELOCITY*100:.1f} cm/s velocity:")

    soas = [300, 800, 1500, 2200, 2700]
    for soa_ms in soas:
        time_at_tactile = soa_ms / 1000.0
        distance_at_tactile = INITIAL_DISTANCE - (APPROACH_VELOCITY * time_at_tactile)
        print(f"  Tactile SOA {soa_ms:4d} ms → Looming distance: {distance_at_tactile*100:5.1f} cm")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    # Set random seed for reproducibility
    np.random.seed(42)

    # Run main
    main()

