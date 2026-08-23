"""
Simple Looming Stimuli Generator
Directly based on Jupyter notebook code
"""

import numpy as np
import scipy.signal as signal
import soundfile as sf
import sofar
from pathlib import Path

# Set random seed
np.random.seed(42)

# Parameters
SAMPLE_RATE = 44100
INITIAL_DISTANCE = 1.1  # 110 cm
FINAL_DISTANCE = 0.1    # 10 cm
DURATION = 3.0
VELOCITY = (INITIAL_DISTANCE - FINAL_DISTANCE) / DURATION

# Paths
SCRIPT_DIR = Path(__file__).parent
SOFA_PATH = SCRIPT_DIR / "0. Head-Related Impulse Response (HRIR) model" / "FABIAN_HRIR_measured_HATO_0.sofa"
OUTPUT_DIR = SCRIPT_DIR / "1. Looming Stimuli"
OUTPUT_DIR.mkdir(exist_ok=True)

print("Loading HRTF...")
hrtf = sofar.read_sofa(str(SOFA_PATH))
print(f"✓ Loaded: {hrtf.GLOBAL_SOFAConventions}")

# Get source positions
source_positions = np.array(hrtf.SourcePosition)
if source_positions.shape[0] == 3:
    source_positions = source_positions.T

# Find frontal position (0°, 0°)
max_azimuth = np.max(np.abs(source_positions[:, 0]))
positions_in_degrees = max_azimuth > 6.28

if positions_in_degrees:
    az_target, el_target = 0, 0
else:
    az_target, el_target = 0, 0  # Already in radians

distances_to_target = np.sqrt(
    (source_positions[:, 0] - az_target)**2 + 
    (source_positions[:, 1] - el_target)**2
)
nearest_idx = np.argmin(distances_to_target)
print(f"✓ Using HRTF position: {source_positions[nearest_idx]}")

# Get HRTF filters
hrtf_left = hrtf.Data_IR[nearest_idx, 0, :]
hrtf_right = hrtf.Data_IR[nearest_idx, 1, :]

# Create distance envelope
num_samples = int(DURATION * SAMPLE_RATE)
distances = np.linspace(INITIAL_DISTANCE, FINAL_DISTANCE, num_samples)
amplitude_envelope = (1.0 / distances) / (1.0 / FINAL_DISTANCE) * 0.7

# Noise generators
def pink_noise(n):
    white = np.random.randn(n)
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1/SAMPLE_RATE)
    freqs[0] = 1
    fft = fft / np.sqrt(freqs)
    return np.fft.irfft(fft, n=n)

def blue_noise(n):
    white = np.random.randn(n)
    fft = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1/SAMPLE_RATE)
    fft = fft * np.sqrt(freqs)
    return np.fft.irfft(fft, n=n)

def white_noise(n):
    return np.random.randn(n)

def brown_noise(n):
    white = np.random.randn(n)
    brown = np.cumsum(white)
    return brown / np.max(np.abs(brown))

# Generate each noise type
noise_funcs = {
    'pink': pink_noise,
    'blue': blue_noise,
    'white': white_noise,
    'brown': brown_noise
}

for idx, (name, func) in enumerate(noise_funcs.items(), 1):
    print(f"\n[{idx}/4] Generating {name} noise...")
    
    # Generate noise
    noise = func(num_samples)
    noise = noise / np.max(np.abs(noise)) * 0.95
    
    # Apply HRTF
    print(f"  Applying HRTF convolution...")
    left = signal.fftconvolve(noise, hrtf_left, mode='same')
    right = signal.fftconvolve(noise, hrtf_right, mode='same')
    
    # Apply distance envelope
    left = left * amplitude_envelope
    right = right * amplitude_envelope
    
    # Combine to stereo
    stereo = np.column_stack([left, right])
    stereo = stereo / np.max(np.abs(stereo)) * 0.95
    
    # Save
    filename = f"Loom-{idx}-{name}.wav"
    sf.write(OUTPUT_DIR / filename, stereo, SAMPLE_RATE)
    print(f"  ✓ Saved: {filename}")

print(f"\n✓ All 4 looming stimuli saved to: {OUTPUT_DIR}")

