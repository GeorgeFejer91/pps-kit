import math
from pathlib import Path

import numpy as np

from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.loudness import (
    LOUDNESS_POLICY_KEY,
    calibration_window_samples,
    envelope_db_for_time,
    normalize_loudness_policy,
    relative_loudness_envelope,
)
from peripersonal_space_toolkit.render_backend import (
    _apply_calibrated_loudness_target,
    build_render_config,
)


def test_loudness_envelope_keeps_padding_holds_constant():
    policy = normalize_loudness_policy(
        None,
        pre_hold_s=0.5,
        movement_duration_s=3.0,
        post_hold_s=0.5,
    )

    assert envelope_db_for_time(policy, 0.0) == 55.0
    assert envelope_db_for_time(policy, 0.49) == 55.0
    assert math.isclose(envelope_db_for_time(policy, 2.0), 65.0)
    assert envelope_db_for_time(policy, 3.5) == 75.0
    assert envelope_db_for_time(policy, 3.99) == 75.0

    envelope = relative_loudness_envelope(policy, samples=4000, sample_rate=1000)
    assert math.isclose(envelope[0], 0.1, rel_tol=1e-6)
    assert math.isclose(envelope[499], 0.1, rel_tol=1e-6)
    assert math.isclose(envelope[3500], 1.0, rel_tol=1e-6)


def test_loudness_policy_disables_hidden_peak_normalization_in_render_config(tmp_path: Path):
    design = default_design()
    design.study_profile_reference_parameters = {
        LOUDNESS_POLICY_KEY: normalize_loudness_policy(
            None,
            pre_hold_s=design.trajectory.padding_pre_s,
            movement_duration_s=design.trajectory.movement_duration_s,
            post_hold_s=design.trajectory.padding_post_s,
        )
    }

    config = build_render_config(design, seed=123, output_dir=tmp_path, include_tactile=False)

    assert config["renderer"]["level_model"]["toolkit_loudness_control_enabled"] is True
    assert config["renderer"]["level_model"]["output_audio_peak_normalization"] is None
    assert config["source"]["gain_law"] is False
    assert config["loudness_policy"]["end_spl_db"] == 75.0


def test_calibrated_loudness_targets_endpoint_hold_rms():
    sample_rate = 1000
    total_samples = 4000
    policy = normalize_loudness_policy(
        {
            "start_spl_db": 60,
            "end_spl_db": 80,
            "estimated_full_scale_spl_db": 100,
        },
        pre_hold_s=0.5,
        movement_duration_s=3.0,
        post_hold_s=0.5,
    )
    envelope = np.asarray(relative_loudness_envelope(policy, total_samples, sample_rate), dtype=float)
    stereo = np.column_stack([envelope, envelope])

    scaled, metadata = _apply_calibrated_loudness_target(stereo, policy, sample_rate, total_samples)
    start, stop = calibration_window_samples(policy, sample_rate, total_samples)
    endpoint_rms = float(np.sqrt(np.mean(scaled[start:stop, :] ** 2)))

    assert math.isclose(20 * math.log10(endpoint_rms), -20.0, abs_tol=0.02)
    assert metadata["loudness_peak_status"] == "within_ceiling"
