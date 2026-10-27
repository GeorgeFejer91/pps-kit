"""Development fixture capture only; never imported by the shipped Rust app.

Run with an existing NumPy environment after reviewing changes in the named
Python reference methods. Noise samples deliberately have no seed-parity claim.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "packages/pps-runtime/src"))
from peripersonal_space_toolkit.render_backend import _dynaspace_burst_onsets, _tactile_waveform, _raised_cosine_edge
from peripersonal_space_toolkit.design import TrajectorySpec, trajectory_point_at_time
from peripersonal_space_toolkit.loudness import calibration_window_samples, calibration_window_target_rms_dbfs, relative_loudness_envelope
import numpy as np

rate = 8000
onsets, resolved = _dynaspace_burst_onsets(samples=8000, sample_rate=rate, parameters={
    "onset_s": 0.1, "active_window_s": 0.48, "burst_duration_s": 0.03,
    "rise_fall_s": 0.01, "target_period_s": 0.095,
    "burst_count_mode": "duration_derived", "spacing_policy": "symmetric_fit",
})
tactile = _tactile_waveform({"tactile": {"waveform": {
    "duration_s": 0.05, "attack_frequency_hz": 250.0,
    "decay_frequency_hz": 150.0, "peak_normalization": 0.5,
}}}, rate)
policy = {"start_spl_db": 55.0, "end_spl_db": 75.0, "estimated_full_scale_spl_db": 95.0,
    "pre_hold_s": 0.2, "movement_duration_s": 0.6, "calibration_window_s": 0.3}
envelope = relative_loudness_envelope(policy, 8000, rate)
fixture = {
    "schema": "pps-generation-reference-fixture.v1",
    "reference_commit": "ae8a4aa43e6046aa5e12e632496410a5dd41b2ca",
    "numpy_version": np.__version__, "noise_seed_parity": False,
    "burst_onset_frames": [round(onset * rate) for onset in onsets],
    "tactile_pcm": tactile.tolist(),
    "calibration_window_frames": calibration_window_samples(policy, rate, 8000),
    "target_window_rms_dbfs": calibration_window_target_rms_dbfs(policy, rate, 8000),
    "envelope_samples": {str(i): envelope[i] for i in [0, 1599, 1600, 3200, 4000, 6399, 6400, 7999]},
    "burst_envelope": _raised_cosine_edge(240, 80).tolist(),
    "polar_points": [trajectory_point_at_time(TrajectorySpec(
        start_radius_m=2.0, end_radius_m=1.0, azimuth_start_deg=170.0, azimuth_end_deg=-170.0,
        elevation_deg=30.0, padding_pre_s=0.2, padding_post_s=0.2, path_length_m=0.6,
        propagation_speed_mps=1.0), t) for t in [0.0, 0.2, 0.35, 0.5, 0.65, 0.8, 1.0]],
}
shared_white = np.asarray([np.sin(i * 0.19) + 0.3 * np.cos(i * 0.47) + 0.1 * np.sin(i * 1.3) for i in range(129)], dtype=np.float32)
shared_white /= np.max(np.abs(shared_white))
spectral = {"white_input": shared_white.tolist(), "sample_rate_hz": 8000, "outputs": {}}
for color, exponent in [("pink", -0.5), ("blue", 0.5), ("violet", 1.0), ("brown", None)]:
    if exponent is None:
        result = np.cumsum(shared_white.astype(float))
    else:
        frequencies = np.fft.rfftfreq(len(shared_white), 1.0 / 8000)
        frequencies[0] = frequencies[1]
        result = np.fft.irfft(np.fft.rfft(shared_white.astype(float)) * frequencies ** exponent, n=len(shared_white))
    spectral["outputs"][color] = (result / np.max(np.abs(result))).tolist()
Path(__file__).with_name("spectral_reference.json").write_text(json.dumps(spectral, separators=(",", ":")) + "\n", encoding="utf-8")
Path(__file__).with_name("python_reference.json").write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
