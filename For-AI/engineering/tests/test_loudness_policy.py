import math
import json
from pathlib import Path

import numpy as np
import pytest

from peripersonal_space_toolkit.design import default_design
from peripersonal_space_toolkit.loudness import (
    LOUDNESS_POLICY_KEY,
    calibration_window_target_rms_dbfs,
    calibration_window_samples,
    db_to_linear,
    envelope_db_for_time,
    hold_window_samples,
    loudness_manifest_payload,
    loudness_protocol_warnings,
    normalize_loudness_policy,
    relative_loudness_envelope,
)
from peripersonal_space_toolkit.render_backend import (
    _apply_calibrated_loudness_target,
    build_render_config,
)


def _rms_dbfs(data: np.ndarray) -> float:
    rms = float(np.sqrt(np.mean(data * data)))
    return 20.0 * math.log10(rms) if rms > 0 else float("-inf")


def test_db_to_linear_conversion_is_amplitude_based():
    assert math.isclose(db_to_linear(0), 1.0)
    assert math.isclose(db_to_linear(20), 10.0)
    assert math.isclose(db_to_linear(-6), 0.5011872336, rel_tol=1e-9)


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
    assert calibration_window_samples(policy, 1000, 4000) == (3000, 3500)


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


def test_calibrated_loudness_targets_final_active_window_without_using_padding():
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
    pre_start, pre_stop = hold_window_samples(policy, sample_rate, total_samples, which="pre")
    post_start, post_stop = hold_window_samples(policy, sample_rate, total_samples, which="post")

    final_active_rms_dbfs = _rms_dbfs(scaled[start:stop, :])
    pre_hold_rms_dbfs = _rms_dbfs(scaled[pre_start:pre_stop, :])
    post_hold_rms_dbfs = _rms_dbfs(scaled[post_start:post_stop, :])

    assert (start, stop) == (3000, 3500)
    assert math.isclose(final_active_rms_dbfs, calibration_window_target_rms_dbfs(policy, sample_rate, total_samples), abs_tol=0.02)
    assert math.isclose(post_hold_rms_dbfs, -20.0, abs_tol=0.02)
    assert math.isclose(post_hold_rms_dbfs - pre_hold_rms_dbfs, 20.0, abs_tol=0.02)
    assert metadata["loudness_calibration_window_role"] == "final_active_movement_excluding_trajectory_padding"
    assert metadata["loudness_peak_status"] == "within_ceiling"


def test_final_active_window_rms_is_matched_across_white_and_pink_noise():
    sample_rate = 1000
    total_samples = 4000
    policy = normalize_loudness_policy(None, pre_hold_s=0.5, movement_duration_s=3.0, post_hold_s=0.5)
    envelope = np.asarray(relative_loudness_envelope(policy, total_samples, sample_rate), dtype=float)
    rng = np.random.default_rng(20260620)
    white = rng.normal(size=(total_samples, 2))
    pink = np.cumsum(rng.normal(size=(total_samples, 2)), axis=0)
    pink = pink - np.mean(pink, axis=0, keepdims=True)
    results = []
    for raw in (white, pink):
        raw = raw / float(np.sqrt(np.mean(raw * raw)))
        shaped = raw * envelope[:, None]
        scaled, _metadata = _apply_calibrated_loudness_target(shaped, policy, sample_rate, total_samples)
        start, stop = calibration_window_samples(policy, sample_rate, total_samples)
        results.append(_rms_dbfs(scaled[start:stop, :]))
        assert float(np.max(np.abs(scaled))) < db_to_linear(float(policy["audio_peak_ceiling_dbfs"]))

    assert abs(results[0] - results[1]) < 0.02


def test_instruction_loudness_gain_uses_configured_offset():
    dashboard_app = pytest.importorskip("peripersonal_space_toolkit.dashboard_app")
    design = dashboard_app._sync_loudness_policy_with_trajectory(default_design())

    assert math.isclose(20.0 * math.log10(dashboard_app._instruction_loudness_gain(design)), -6.0, abs_tol=0.001)


def test_loudness_manifest_payload_and_runner_manifest_record_protocol(tmp_path: Path):
    from peripersonal_space_toolkit.session_runner import (
        RenderedWav,
        RunPackage,
        _loudness_manifest_path,
        _write_session_manifest,
    )

    policy = normalize_loudness_policy({"hardware": {"runner_audio_volume_percent": 75}})
    warnings = loudness_protocol_warnings(policy)
    assert any("100%" in warning for warning in warnings)

    payload = loudness_manifest_payload(policy, created_at="2026-06-20T12:00:00", source_context="unit_test")
    assert payload["schema"] == "pps-loudness-manifest.v1"
    assert payload["calibration"]["window"] == "final_500ms_active_movement_excluding_padding"
    assert payload["renderer"]["normalization_status"] == "hidden_peak_normalization_disabled_in_loudness_control_mode"

    runner_log_dir = tmp_path / "Experiment_context_folder_DO_NOT_DELETE" / "runner_logs" / "P001_20260620_120000"
    runner_log_dir.mkdir(parents=True)
    package = RunPackage(
        participant_id="P001",
        session_id="P001_20260620_120000",
        created_at="2026-06-20T12:00:00",
        session_dir=tmp_path / "P001_20260620_120000",
        design_path=runner_log_dir / "design.json",
        protocol_path=runner_log_dir / "protocol_schedule.csv",
        manifest_path=runner_log_dir / "session_manifest.json",
        render_manifest_path=None,
        loudness_policy=policy,
    )
    _write_session_manifest(
        package,
        [RenderedWav(path=tmp_path / "looming_white.wav", label="white", duration_s=4.0, sample_rate=44100, channels=2)],
    )

    manifest = json.loads(package.manifest_path.read_text(encoding="utf-8"))
    loudness_manifest_path = _loudness_manifest_path(package)
    loudness_manifest = json.loads(loudness_manifest_path.read_text(encoding="utf-8"))
    assert manifest["outputs"]["loudness_manifest_json"] == str(loudness_manifest_path)
    assert loudness_manifest["targets"]["endpoint_spl_db"] == 75.0
    assert loudness_manifest["hardware_protocol"]["runner_audio_volume_percent"] == 75
