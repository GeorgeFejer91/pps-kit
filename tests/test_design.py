from __future__ import annotations

import csv
import json
import xml.etree.ElementTree as ET
from collections import Counter
from importlib.resources import files
from pathlib import Path

import pytest

from peripersonal_space_toolkit import designer_app, qt_designer_app
from peripersonal_space_toolkit.app_assets import package_asset
from peripersonal_space_toolkit.design import (
    AudioFileSpec,
    BlockSpec,
    DEFAULT_SOFA_FILE,
    DEFAULT_TRAJECTORY_PLANE_HEIGHT_M,
    NoiseDefinition,
    PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
    ProtocolSpec,
    TrialStripElementSpec,
    TrialStripSpec,
    horizontal_point_from_distance_rotation,
    block_trial_rows,
    default_design,
    design_from_dict,
    design_to_dict,
    experiment_schedule_rows,
    export_protocol_csv,
    export_trajectory_csv,
    load_design,
    participant_block_orders,
    point_from_distance_rotation_height,
    protocol_summary,
    save_design,
    gold_standard_looming_source_parameters,
    trajectory_point_at_time,
    trajectory_points,
    trajectory_points_with_holds,
    validate_design,
)
from peripersonal_space_toolkit.qt_designer_app import (
    participant_order_preview_rows,
    runner_asset_status,
    runner_launch_command,
    trial_assembler_preview_rows,
)
from peripersonal_space_toolkit.render_backend import (
    DEFAULT_HEAD_DIAMETER_M,
    STANDARD_HRTF_RESOURCE,
    THREEDTI_COMMIT,
    app_to_3dti_coordinates,
    build_render_config,
    _dynaspace_burst_onsets,
    _generate_dynaspace_burst_train,
    load_render_design,
    postprocess_native_manifest,
    render_design_with_3dti,
    sha256_file,
)
from peripersonal_space_toolkit.templates import (
    load_templates,
    study_template_bibtex,
    study_template_citation_label,
    study_template_csl_json,
)


def test_packaged_app_icons_exist():
    for filename in ("pps_toolkit_logo.svg", "pps_toolkit_icon.png", "pps_toolkit_icon.ico"):
        asset = package_asset(filename)
        assert asset.is_file()
        assert len(asset.read_bytes()) > 100


def test_packaged_noise_mode_svgs_exist_and_parse():
    for filename in (
        "looming_burst_train_waveform.svg",
        "looming_smooth_linear_approach_waveform.svg",
    ):
        for asset in (
            package_asset(filename),
            files("peripersonal_space_toolkit.dashboard").joinpath(filename),
        ):
            assert asset.is_file()
            text = asset.read_text(encoding="utf-8")
            root = ET.fromstring(text)
            assert root.tag.endswith("svg")
            assert root.attrib["viewBox"] == "0 0 960 360"
            assert text.count("<path") >= 5
            assert "PEAK ENVELOPE" in text
            assert "CONTINUOUS NOISE CONTROL" not in text


def test_default_design_matches_four_second_study5_timing():
    design = default_design()
    assert validate_design(design) == []
    assert design.trajectory.movement_duration_s == 3.0
    assert design.trajectory.total_duration_s == 4.0
    assert [noise.source_profile for noise in design.noises] == [
        PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
        PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
    ]
    assert all(
        noise.source_profile_parameters["burst_count_mode"] == "duration_derived"
        for noise in design.noises
    )
    points = trajectory_points(design.trajectory, samples=5)
    assert points[0]["radius_m"] == pytest.approx(1.1)
    assert points[-1]["radius_m"] == pytest.approx(0.1)


def test_design_json_round_trip_and_trajectory_export(tmp_path: Path):
    design = default_design()
    design.custom_looming_files = [AudioFileSpec("custom pink", "C:/stimuli/custom_pink.wav", 4.0)]
    design.prestimulus_files = [
        AudioFileSpec(
            "inhale",
            "C:/stimuli/inhale.wav",
            4.0,
            placement="before",
            target_source_label="Pink frontal",
            phase="Inhale",
            gap_s=0.25,
            sequence_order=1,
            motion_mode="stationary",
        )
    ]
    design_path = tmp_path / "design.json"
    csv_path = tmp_path / "trajectory.csv"
    save_design(design, design_path)
    loaded = load_design(design_path)
    assert loaded.noises[0].noise_type == "pink"
    assert loaded.custom_looming_files[0].label == "custom pink"
    assert loaded.prestimulus_files[0].path.endswith("inhale.wav")
    assert loaded.prestimulus_files[0].placement == "before"
    assert loaded.prestimulus_files[0].target_source_label == "Pink frontal"
    assert loaded.prestimulus_files[0].phase == "Inhale"
    assert loaded.prestimulus_files[0].gap_s == pytest.approx(0.25)
    assert loaded.prestimulus_files[0].sequence_order == 1
    assert loaded.prestimulus_files[0].motion_mode == "stationary"

    export_trajectory_csv(loaded, csv_path, samples=7)
    text = csv_path.read_text(encoding="utf-8")
    assert "time_s,radius_m,azimuth_deg" in text
    assert len(text.strip().splitlines()) == 8


def test_cartesian_trajectory_uses_start_and_end_xyz_coordinates():
    design = default_design()
    design.trajectory.coordinate_mode = "cartesian"
    design.trajectory.start_x_m = -0.5
    design.trajectory.start_y_m = 0.8
    design.trajectory.start_z_m = 0.2
    design.trajectory.end_x_m = 0.5
    design.trajectory.end_y_m = 0.8
    design.trajectory.end_z_m = -0.1
    design.trajectory.path_length_m = 1.044
    design.trajectory.propagation_speed_mps = 0.348

    points = trajectory_points(design.trajectory, samples=3)

    assert validate_design(design) == []
    assert points[0]["x_m"] == pytest.approx(-0.5)
    assert points[0]["y_m"] == pytest.approx(0.8)
    assert points[0]["z_m"] == pytest.approx(0.2)
    assert points[-1]["x_m"] == pytest.approx(0.5)
    assert points[-1]["y_m"] == pytest.approx(0.8)
    assert points[-1]["z_m"] == pytest.approx(-0.1)
    assert points[0]["azimuth_deg"] < 0
    assert points[-1]["azimuth_deg"] > 0


def test_distance_rotation_controls_accept_full_360_degree_input():
    forward_zero = horizontal_point_from_distance_rotation(110.0, 0.0)
    forward_full = horizontal_point_from_distance_rotation(110.0, 360.0)
    right = horizontal_point_from_distance_rotation(110.0, 90.0)
    left = horizontal_point_from_distance_rotation(110.0, 270.0)

    assert forward_zero["x_m"] == pytest.approx(forward_full["x_m"])
    assert forward_zero["y_m"] == pytest.approx(forward_full["y_m"])
    assert forward_zero["z_m"] == pytest.approx(0.0)
    assert right["x_m"] == pytest.approx(1.1)
    assert right["y_m"] == pytest.approx(0.0, abs=1e-12)
    assert left["x_m"] == pytest.approx(-1.1)
    assert left["y_m"] == pytest.approx(0.0, abs=1e-12)


def test_endpoint_height_is_head_plane_offset_and_preserves_distance():
    elevated = point_from_distance_rotation_height(100.0, 90.0, 50.0)

    assert elevated["x_m"] == pytest.approx(0.8660254)
    assert elevated["y_m"] == pytest.approx(0.0, abs=1e-12)
    assert elevated["z_m"] == pytest.approx(0.5)
    assert (elevated["x_m"] ** 2 + elevated["y_m"] ** 2 + elevated["z_m"] ** 2) ** 0.5 == pytest.approx(1.0)
    with pytest.raises(ValueError, match="Height from the head plane"):
        point_from_distance_rotation_height(10.0, 0.0, 20.0)


def test_qt_endpoint_controls_build_viewer_payload_with_model_coordinates():
    design = qt_designer_app.create_design_from_endpoint_controls(
        default_design(),
        start_distance_cm=110.0,
        start_rotation_deg=270.0,
        end_distance_cm=10.0,
        end_rotation_deg=360.0,
        movement_duration_s=3.0,
        lead_padding_s=0.5,
        tail_padding_s=0.5,
    )
    payload = qt_designer_app.trajectory_viewer_payload(design)

    assert design.trajectory.start_x_m == pytest.approx(-1.1)
    assert design.trajectory.start_y_m == pytest.approx(0.0, abs=1e-12)
    assert design.trajectory.end_x_m == pytest.approx(0.0, abs=1e-12)
    assert design.trajectory.end_y_m == pytest.approx(0.1)
    assert payload["start"]["x_m"] == pytest.approx(design.trajectory.start_x_m)
    assert payload["end"]["y_m"] == pytest.approx(design.trajectory.end_y_m)


def test_qt_endpoint_controls_default_to_head_plane_unless_3d_height_is_given():
    flat = qt_designer_app.create_design_from_endpoint_controls(
        default_design(),
        start_distance_cm=110.0,
        start_rotation_deg=0.0,
        end_distance_cm=10.0,
        end_rotation_deg=0.0,
        movement_duration_s=3.0,
        lead_padding_s=0.5,
        tail_padding_s=0.5,
    )
    raised = qt_designer_app.create_design_from_endpoint_controls(
        default_design(),
        start_distance_cm=110.0,
        start_rotation_deg=0.0,
        end_distance_cm=10.0,
        end_rotation_deg=0.0,
        movement_duration_s=3.0,
        lead_padding_s=0.5,
        tail_padding_s=0.5,
        start_height_cm=20.0,
        end_height_cm=-5.0,
    )

    assert flat.trajectory.start_z_m == pytest.approx(0.0)
    assert flat.trajectory.end_z_m == pytest.approx(0.0)
    assert raised.trajectory.start_z_m == pytest.approx(0.2)
    assert raised.trajectory.end_z_m == pytest.approx(-0.05)
    assert raised.trajectory.path_length_m > flat.trajectory.path_length_m


def test_trajectory_viewer_payload_can_flatten_height_for_2d_preview():
    design = default_design()
    design.trajectory.coordinate_mode = "cartesian"
    design.trajectory.start_x_m = -0.5
    design.trajectory.start_y_m = 0.8
    design.trajectory.start_z_m = 0.25
    design.trajectory.end_x_m = 0.2
    design.trajectory.end_y_m = 0.1
    design.trajectory.end_z_m = -0.4
    design.trajectory.path_length_m = 1.184
    design.trajectory.propagation_speed_mps = 0.592

    payload_2d = qt_designer_app.trajectory_viewer_payload(design, preview_mode="2d")
    payload_3d = qt_designer_app.trajectory_viewer_payload(design, preview_mode="3d")

    assert payload_2d["preview_mode"] == "2d"
    assert payload_2d["height_visible"] is False
    assert payload_2d["start"]["z_m"] == pytest.approx(0.0)
    assert payload_2d["end"]["z_m"] == pytest.approx(0.0)
    assert payload_3d["preview_mode"] == "3d"
    assert payload_3d["height_visible"] is True
    assert payload_3d["start"]["z_m"] == pytest.approx(0.25)
    assert payload_3d["end"]["z_m"] == pytest.approx(-0.4)


def test_qt_workspace_splitter_defaults_cover_all_tabs():
    defaults = qt_designer_app.SPLITTER_DEFAULT_SIZES

    assert set(defaults) == {
        "stimulus/main",
        "stimulus/left",
        "stimulus/right",
        "trial/main",
        "trial/left",
        "trial/right",
        "runner/main",
        "runner/right",
    }
    assert defaults["stimulus/main"][1] > defaults["stimulus/main"][0]
    assert defaults["trial/right"][1] > defaults["trial/right"][0]
    assert defaults["runner/right"][0] > defaults["runner/right"][1]
    for sizes in defaults.values():
        assert all(value > 0 for value in sizes)


def test_trajectory_sampling_includes_start_hold_linear_motion_and_end_hold():
    design = qt_designer_app.create_design_from_endpoint_controls(
        default_design(),
        start_distance_cm=110.0,
        start_rotation_deg=270.0,
        end_distance_cm=10.0,
        end_rotation_deg=0.0,
        movement_duration_s=2.0,
        lead_padding_s=1.0,
        tail_padding_s=1.0,
    )

    at_start = trajectory_point_at_time(design.trajectory, 0.5)
    halfway = trajectory_point_at_time(design.trajectory, 2.0)
    at_end = trajectory_point_at_time(design.trajectory, 3.5)
    samples = trajectory_points_with_holds(design.trajectory, samples_per_second=2.0)

    assert at_start["phase"] == "start_hold"
    assert at_start["x_m"] == pytest.approx(-1.1)
    assert at_start["y_m"] == pytest.approx(0.0, abs=1e-12)
    assert halfway["phase"] == "movement"
    assert halfway["u"] == pytest.approx(0.5)
    assert halfway["x_m"] == pytest.approx(-0.55)
    assert halfway["y_m"] == pytest.approx(0.05)
    assert at_end["phase"] == "end_hold"
    assert at_end["x_m"] == pytest.approx(0.0, abs=1e-12)
    assert at_end["y_m"] == pytest.approx(0.1)
    assert samples[0]["phase"] == "start_hold"
    assert samples[-1]["phase"] == "end_hold"
    assert samples[-1]["u"] == pytest.approx(1.0)


def test_3dti_render_config_preserves_app_coordinate_convention(tmp_path: Path):
    design = qt_designer_app.create_design_from_endpoint_controls(
        default_design(),
        start_distance_cm=110.0,
        start_rotation_deg=90.0,
        end_distance_cm=10.0,
        end_rotation_deg=0.0,
        movement_duration_s=2.0,
        lead_padding_s=1.0,
        tail_padding_s=1.0,
    )

    config = build_render_config(design, seed=1234, output_dir=tmp_path, samples_per_second=4.0)

    assert config["renderer"]["commit"] == THREEDTI_COMMIT
    assert config["coordinate_convention"]["app"] == "X right positive, Y front positive, Z up positive"
    assert config["coordinate_convention"]["adapter_mapping"] == {
        "3dti_x_m": "app_y_m",
        "3dti_y_m": "-app_x_m",
        "3dti_z_m": "app_z_m",
    }
    assert config["listener"]["stationary"] is True
    assert config["listener"]["x_m"] == pytest.approx(0.0)
    assert config["listener"]["y_m"] == pytest.approx(0.0)
    assert config["listener"]["z_m"] == pytest.approx(0.0)
    assert config["listener"]["head_diameter_m"] == pytest.approx(DEFAULT_HEAD_DIAMETER_M)
    assert config["listener"]["head_radius_m"] == pytest.approx(DEFAULT_HEAD_DIAMETER_M / 2.0)
    assert config["renderer"]["spatialization_mode"] == "HighQuality"
    assert config["renderer"]["acoustic_model"]["customized_itd"] is True
    assert config["renderer"]["acoustic_model"]["propagation_delay"] is True
    assert config["renderer"]["level_model"]["noise_gain_unit"] == "linear_amplitude_multiplier"
    assert config["renderer"]["level_model"]["absolute_spl_calibrated"] is False
    assert config["source"]["seed"] == 1234
    assert config["source"]["hrtf_resource"]["id"] == STANDARD_HRTF_RESOURCE["id"]
    assert config["source"]["hrtf_resource"]["experimenter_visible"] is False
    assert config["tactile"]["channels"] == {
        "0": "binaural_left",
        "1": "binaural_right",
        "2": "vibrotactile",
    }
    assert config["tactile"]["events"][0]["soa_ms"] == default_design().protocol.soa_values_ms[0]
    assert config["tactile"]["events"][0]["tactile_onset_s"] == pytest.approx(0.3)
    assert config["trajectory"]["mode"] == "linear_cartesian_with_endpoint_holds"
    assert config["trajectory"]["samples"][0]["phase"] == "start_hold"
    assert config["trajectory"]["samples"][0]["x_m"] == pytest.approx(1.1)
    assert config["trajectory"]["samples"][-1]["y_m"] == pytest.approx(0.1)
    assert app_to_3dti_coordinates(1.1, 0.0, 0.25) == {
        "x_m": pytest.approx(0.0),
        "y_m": pytest.approx(-1.1),
        "z_m": pytest.approx(0.25),
    }


def test_source_profile_round_trips_and_reaches_render_config(tmp_path: Path):
    design = default_design()
    design.noises = design.noises[:1]
    design.noises[0].source_profile = PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
    design.noises[0].source_profile_parameters = gold_standard_looming_source_parameters({"onset_s": 0.125})

    loaded = design_from_dict(design_to_dict(design))
    config = build_render_config(loaded, seed=987, output_dir=tmp_path)

    assert loaded.noises[0].source_profile == PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
    assert loaded.noises[0].source_profile_parameters["burst_count_mode"] == "duration_derived"
    assert loaded.noises[0].source_profile_parameters["onset_s"] == pytest.approx(0.125)
    assert config["source"]["noises"][0]["source_profile"] == PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
    assert config["source"]["noises"][0]["source_profile_parameters"]["target_period_s"] == pytest.approx(0.095)
    assert config["source"]["noises"][0]["source_profile_parameters"]["active_window_s"] == pytest.approx(
        design.trajectory.movement_duration_s
    )
    assert (
        config["source"]["noises"][0]["source_profile_parameters"]["active_window_s_source"]
        == "trajectory.movement_duration_s"
    )


def test_continuous_noise_source_profile_is_explicit_opt_out(tmp_path: Path):
    design = default_design()
    design.noises = [
        NoiseDefinition("Continuous pink", "pink", source_profile="continuous_noise")
    ]

    loaded = design_from_dict(design_to_dict(design))
    config = build_render_config(loaded, seed=4321, output_dir=tmp_path)

    assert loaded.noises[0].source_profile == "continuous_noise"
    assert loaded.noises[0].source_profile_parameters == {}
    assert config["source"]["noises"][0]["source_profile"] == "continuous_noise"
    assert "source_profile_parameters" not in config["source"]["noises"][0]


def test_dynaspace_burst_train_derives_symmetric_spacing_from_active_window():
    import numpy as np

    sample_rate = 10_000
    samples = int(round(0.800 * sample_rate))
    parameters = gold_standard_looming_source_parameters(
        {
            "active_window_s": 0.475,
            "burst_duration_s": 0.030,
            "onset_s": 0.100,
            "rise_fall_s": 0.002,
            "target_period_s": 0.095,
        }
    )

    onsets, resolved = _dynaspace_burst_onsets(samples=samples, sample_rate=sample_rate, parameters=parameters)
    source = _generate_dynaspace_burst_train("white", samples, sample_rate, 123, parameters)
    active_indices = np.flatnonzero(np.abs(source) > 1e-8)
    breaks = np.where(np.diff(active_indices) > int(round(0.010 * sample_rate)))[0]
    starts = np.r_[active_indices[0], active_indices[breaks + 1]]
    stops = np.r_[active_indices[breaks], active_indices[-1]]

    assert len(onsets) == 6
    assert resolved["actual_period_s"] == pytest.approx(0.089, abs=1e-9)
    assert onsets[0] == pytest.approx(0.100)
    assert onsets[-1] + resolved["burst_duration_s"] == pytest.approx(0.575)
    assert len(starts) == 6
    assert np.median(np.diff(starts) / sample_rate) == pytest.approx(0.089, abs=1.0 / sample_rate)
    assert (stops[-1] + 1) / sample_rate <= 0.575 + (1.0 / sample_rate)


def test_dynaspace_burst_train_keeps_legacy_fixed_interval_parameters():
    onsets, resolved = _dynaspace_burst_onsets(
        samples=10_000,
        sample_rate=10_000,
        parameters={
            "burst_count": 4,
            "burst_duration_s": 0.020,
            "inter_burst_interval_s": 0.080,
            "onset_s": 0.050,
        },
    )

    assert resolved["spacing_policy"] == "fixed_period_truncate"
    assert resolved["actual_period_s"] == pytest.approx(0.100)
    assert onsets == pytest.approx([0.050, 0.150, 0.250, 0.350])


def test_dynaspace_burst_train_source_profile_renders_pulsed_audio(tmp_path: Path):
    import numpy as np
    import soundfile as sf
    from scipy import signal

    design = default_design()
    design.noises = [
        NoiseDefinition(
            label="DynaSpace burst source",
            noise_type="white",
            azimuth_deg=-45.0,
            motion_mode="stationary",
            source_profile=PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE,
            source_profile_parameters=gold_standard_looming_source_parameters(
                {
                    "burst_count": 6,
                    "burst_count_mode": "fixed",
                    "active_window_s": 0.505,
                    "onset_s": 0.100,
                    "rise_fall_s": 0.005,
                }
            ),
        )
    ]
    design.trajectory.path_length_m = 0.2
    design.trajectory.propagation_speed_mps = 1.0
    design.trajectory.padding_pre_s = 0.1
    design.trajectory.padding_post_s = 0.4
    design.protocol.soa_values_ms = [150]
    design.protocol.spatial_values_cm = [100.0]

    design_path = tmp_path / "dynaspace_burst.design.json"
    output_dir = tmp_path / "rendered"
    save_design(design, design_path)
    result = render_design_with_3dti(
        design_path,
        output_dir,
        seed=31415,
        engine="python-sofa-reference",
        include_tactile=False,
    )

    assert result.status == "rendered_reference"
    audio, sample_rate = sf.read(result.wav_paths[0], always_2d=True)
    mono = np.mean(audio[:, :2], axis=1)
    frame = int(round(0.020 * sample_rate))
    hop = int(round(0.0025 * sample_rate))
    rms = np.array(
        [
            np.sqrt(np.mean(mono[start : start + frame] * mono[start : start + frame]))
            for start in range(0, len(mono) - frame, hop)
        ]
    )
    peaks, _properties = signal.find_peaks(rms, distance=int(round(0.060 * sample_rate / hop)), prominence=np.max(rms) * 0.08)
    peak_times = peaks * hop / sample_rate

    assert len(peaks) >= 5
    assert np.median(np.diff(peak_times[:6])) == pytest.approx(0.095, abs=0.018)
    with result.qc_path.open(newline="", encoding="utf-8") as f:
        qc_rows = list(csv.DictReader(f))
    assert qc_rows[0]["source_profile"] == PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
    assert '"burst_count": 6' in qc_rows[0]["source_profile_parameters"]


def test_gui_style_saved_design_round_trip_controls_noise_trajectory_and_soas(tmp_path: Path):
    base = default_design()
    base.name = "Custom GUI looming profile"
    base.noises = [
        NoiseDefinition(
            label="GUI pink test",
            noise_type="pink",
            azimuth_deg=0.0,
            elevation_deg=0.0,
            gain=0.7,
        )
    ]
    base.protocol = ProtocolSpec(
        repetitions_per_condition=3,
        soa_values_ms=[120, 480],
        spatial_values_cm=[95.0, 15.0],
        pair_spatial_values_with_soas=True,
        auditory_motion_directions=["custom linear"],
        tactile_sites=["hand"],
        catch_trial_percentage=10.0,
        include_baseline_trials=True,
        baseline_soa_values_ms=[480],
        respiratory_phases=["Any"],
        participants=2,
        random_seed=4242,
    )
    design = qt_designer_app.create_design_from_endpoint_controls(
        base,
        start_distance_cm=110.0,
        start_rotation_deg=270.0,
        end_distance_cm=10.0,
        end_rotation_deg=0.0,
        movement_duration_s=2.5,
        lead_padding_s=0.25,
        tail_padding_s=0.75,
    )
    design_path = tmp_path / "gui_saved_design.json"
    save_design(design, design_path)

    loaded = load_design(design_path)
    config = build_render_config(loaded, seed=9001, output_dir=tmp_path, samples_per_second=10.0)

    assert loaded.name == "Custom GUI looming profile"
    assert loaded.noises[0].label == "GUI pink test"
    assert loaded.noises[0].noise_type == "pink"
    assert loaded.noises[0].gain == pytest.approx(0.7)
    assert loaded.trajectory.start_x_m == pytest.approx(-1.1)
    assert loaded.trajectory.start_y_m == pytest.approx(0.0, abs=1e-12)
    assert loaded.trajectory.end_x_m == pytest.approx(0.0, abs=1e-12)
    assert loaded.trajectory.end_y_m == pytest.approx(0.1)
    assert loaded.trajectory.padding_pre_s == pytest.approx(0.25)
    assert loaded.trajectory.movement_duration_s == pytest.approx(2.5)
    assert loaded.trajectory.padding_post_s == pytest.approx(0.75)
    assert loaded.protocol.soa_values_ms == [120, 480]
    assert loaded.protocol.spatial_values_cm == [95.0, 15.0]
    assert loaded.protocol.repetitions_per_condition == 3
    assert len(config["source"]["noises"]) == 1
    config_noise = config["source"]["noises"][0]
    assert config_noise["label"] == "GUI pink test"
    assert config_noise["noise_type"] == "pink"
    assert config_noise["tone_type"] == "pink"
    assert config_noise["gain"] == pytest.approx(0.7)
    assert config_noise["motion_mode"] == "looming"
    assert config_noise["source_profile"] == PPS_LOOMING_GOLD_STANDARD_SOURCE_PROFILE
    assert config_noise["source_profile_parameters"]["burst_count_mode"] == "duration_derived"
    assert config_noise["source_profile_parameters"]["active_window_s"] == pytest.approx(2.5)
    assert (
        config_noise["source_profile_parameters"]["active_window_s_source"]
        == "trajectory.movement_duration_s"
    )
    assert config["protocol"]["soa_values_ms"] == [120, 480]
    assert config["protocol"]["spatial_values_cm"] == [95.0, 15.0]
    assert [event["soa_ms"] for event in config["tactile"]["events"]] == [120, 480]
    assert [event["tactile_onset_s"] for event in config["tactile"]["events"]] == [pytest.approx(0.12), pytest.approx(0.48)]
    assert config["tactile"]["channels"]["2"] == "vibrotactile"


def test_pfeiffer_study_profile_controls_trajectory_not_hrtf(tmp_path: Path):
    templates = load_templates(Path(__file__).resolve().parents[1] / "study_templates")
    pfeiffer = next(template for template in templates if template.template_id == "pfeiffer_2018_lateral_perihead_left_to_right")
    design = pfeiffer.design

    assert design.study_profile_id == pfeiffer.template_id
    assert design.study_profile_title == "Pfeiffer EJN2018 bilateral lateral trajectory profile"
    assert design.protocol.auditory_motion_directions == ["left_to_right", "right_to_left"]
    assert design.study_profile_reference_parameters["trajectory_plane_height_m"] == pytest.approx(
        DEFAULT_TRAJECTORY_PLANE_HEIGHT_M
    )
    assert design.noises[0].noise_type == "pink"
    assert design.trajectory.start_x_m == pytest.approx(-0.4)
    assert design.trajectory.end_x_m == pytest.approx(0.4)
    assert design.trajectory.start_y_m == pytest.approx(0.05)
    assert design.trajectory.end_y_m == pytest.approx(0.05)
    assert design.trajectory.start_z_m == pytest.approx(0.0)
    assert design.trajectory.end_z_m == pytest.approx(0.0)
    assert design.trajectory.propagation_speed_mps == pytest.approx(0.2)
    assert design.trajectory.movement_duration_s == pytest.approx(4.0)

    config = build_render_config(design, seed=2018, output_dir=tmp_path)

    assert config["study_profile"]["id"] == pfeiffer.template_id
    assert config["study_profile"]["reference_parameters"]["front_offset_y_m"] == pytest.approx(0.05)
    assert config["listener"]["head_diameter_m"] == pytest.approx(0.18)
    assert config["listener"]["head_radius_m"] == pytest.approx(0.09)
    assert config["listener"]["head_model_source"] == (
        "pfeiffer_2018_lateral_perihead_left_to_right.reference_parameters.head_diameter_m"
    )
    assert config["renderer"]["level_model"]["absolute_spl_calibrated"] is False
    for event in config["tactile"]["events"]:
        assert event["planned_spatial_value_cm"] == pytest.approx(event["source_radius_at_tactile_cm"], abs=1e-5)
    assert config["source"]["hrtf_resource"]["id"] == STANDARD_HRTF_RESOURCE["id"]
    assert config["source"]["hrtf_resource"]["sofa_file"] == DEFAULT_SOFA_FILE
    assert config["source"]["hrtf_resource"]["experimenter_visible"] is False


def test_render_loader_accepts_study_profile_json():
    root = Path(__file__).resolve().parents[1]
    design = load_render_design(root / "study_templates" / "pfeiffer_2018_lateral_perihead_left_to_right.json")

    assert design.study_profile_id == "pfeiffer_2018_lateral_perihead_left_to_right"
    assert design.noises[0].noise_type == "pink"
    assert design.trajectory.start_x_m == pytest.approx(-0.4)
    assert design.trajectory.end_x_m == pytest.approx(0.4)


def test_pfeiffer_style_example_designs_encode_mirrored_looming_parameters(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    left = load_design(root / "configs" / "pfeiffer_style_left_approach.design.json")
    right = load_design(root / "configs" / "pfeiffer_style_right_approach.design.json")

    for design in (left, right):
        assert validate_design(design) == []
        assert design.noises[0].noise_type == "pink"
        assert design.trajectory.padding_pre_s == pytest.approx(1.0)
        assert design.trajectory.movement_duration_s == pytest.approx(2.0)
        assert design.trajectory.padding_post_s == pytest.approx(1.0)
        assert design.trajectory.total_duration_s == pytest.approx(4.0)
        assert design.trajectory.end_x_m == pytest.approx(0.0)
        assert design.trajectory.end_y_m == pytest.approx(0.1)
        config = build_render_config(design, seed=2026, output_dir=tmp_path)
        assert config["source"]["sample_rate"] == 44100
        assert config["tactile"]["waveform"]["duration_s"] == pytest.approx(0.1)
        assert len(config["tactile"]["events"]) == len(design.protocol.soa_values_ms)

    assert left.trajectory.start_x_m == pytest.approx(-right.trajectory.start_x_m)
    assert left.trajectory.start_y_m == pytest.approx(right.trajectory.start_y_m)
    assert left.trajectory.path_length_m == pytest.approx(right.trajectory.path_length_m)


def test_native_3dti_engine_reports_missing_backend_without_wav_fallback(tmp_path: Path):
    design_path = tmp_path / "design.json"
    output_dir = tmp_path / "rendered"
    save_design(default_design(), design_path)

    result = render_design_with_3dti(
        design_path,
        output_dir,
        seed=99,
        backend_executable=tmp_path / "missing" / "pps-3dti-renderer.exe",
        engine="native-3dti",
    )

    assert result.status == "backend_missing"
    assert result.exit_code == 2
    assert result.config_path.exists()
    assert result.manifest_path.exists()
    assert result.qc_path.exists()
    assert (output_dir / "render_trajectory_samples.csv").exists()
    assert result.tactile_events_path == output_dir / "render_tactile_events.csv"
    assert result.tactile_events_path.exists()

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "backend_missing"
    assert manifest["renderer"]["commit"] == THREEDTI_COMMIT
    assert manifest["tactile_events"]["count"] == len(default_design().protocol.soa_values_ms)
    with result.qc_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert {row["status"] for row in rows} == {"backend_missing"}


def test_auto_render_writes_reference_wav_with_binaural_and_tactile_channels(tmp_path: Path):
    import numpy as np
    import soundfile as sf

    design = default_design()
    design.noises = design.noises[:1]
    design.noises[0].label = "Pink lateral test"
    design.trajectory.coordinate_mode = "cartesian"
    design.trajectory.start_radius_m = 0.4031128874
    design.trajectory.end_radius_m = 0.4031128874
    design.trajectory.start_x_m = -0.4
    design.trajectory.start_y_m = 0.05
    design.trajectory.start_z_m = 0.0
    design.trajectory.end_x_m = 0.4
    design.trajectory.end_y_m = 0.05
    design.trajectory.end_z_m = 0.0
    design.trajectory.path_length_m = 0.8
    design.trajectory.propagation_speed_mps = 1.0
    design.trajectory.padding_pre_s = 0.0
    design.trajectory.padding_post_s = 0.0
    design.protocol.soa_values_ms = [50]
    design.protocol.spatial_values_cm = [20.0]
    design.protocol.pair_spatial_values_with_soas = True
    design_path = tmp_path / "design.json"
    output_dir = tmp_path / "rendered"
    save_design(design, design_path)

    result = render_design_with_3dti(
        design_path,
        output_dir,
        seed=123,
        backend_executable=tmp_path / "missing" / "pps-3dti-renderer.exe",
    )

    assert result.status == "rendered_reference"
    assert result.exit_code == 0
    assert len(result.wav_paths) == 1
    assert result.tactile_events_path and result.tactile_events_path.exists()
    audio, sample_rate = sf.read(result.wav_paths[0], always_2d=True)
    assert sample_rate == 44100
    assert audio.shape == (35280, 3)
    assert np.max(np.abs(audio[:, 0])) > 0.01
    assert np.max(np.abs(audio[:, 1])) > 0.01
    onset = int(0.05 * sample_rate)
    assert np.max(np.abs(audio[:onset, 2])) == pytest.approx(0.0)
    assert np.max(np.abs(audio[onset:, 2])) > 0.1

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "rendered_reference"
    assert manifest["render_engine"] == "python-sofa-reference"
    assert manifest["tactile_events"]["path"] == str(result.tactile_events_path)
    assert manifest["tactile_events"]["sha256"]
    assert manifest["wav_outputs"][0]["path"] == str(result.wav_paths[0])
    assert manifest["wav_outputs"][0]["sha256"]
    with result.tactile_events_path.open(newline="", encoding="utf-8") as f:
        tactile_rows = list(csv.DictReader(f))
    assert tactile_rows[0]["soa_ms"] == "50"
    assert tactile_rows[0]["tactile_onset_sample"] == str(onset)
    assert tactile_rows[0]["tactile_channel"] == "2"
    with result.qc_path.open(newline="", encoding="utf-8") as f:
        qc_rows = list(csv.DictReader(f))
    assert qc_rows[0]["channels"] == "3"
    assert qc_rows[0]["tactile_events"] == "1"
    assert float(qc_rows[0]["first_half_left_rms"]) > float(qc_rows[0]["first_half_right_rms"])
    assert float(qc_rows[0]["second_half_right_rms"]) > float(qc_rows[0]["second_half_left_rms"])


def test_imported_looming_audio_can_render_as_experiment_source(tmp_path: Path):
    import numpy as np
    import soundfile as sf

    source_path = tmp_path / "already_looming.wav"
    source = np.zeros((2205, 2), dtype=np.float32)
    source[:, 0] = 0.2
    source[:, 1] = -0.2
    sf.write(source_path, source, 44100)

    design = default_design()
    design.noises = []
    design.custom_looming_files = [AudioFileSpec("Already looming", str(source_path), 0.05)]
    design.trajectory.path_length_m = 0.05
    design.trajectory.propagation_speed_mps = 1.0
    design.trajectory.padding_pre_s = 0.0
    design.trajectory.padding_post_s = 0.0
    design.protocol.soa_values_ms = [25]
    design.protocol.spatial_values_cm = [20.0]
    design.protocol.pair_spatial_values_with_soas = True
    design.protocol.include_baseline_trials = False
    design.protocol.catch_trial_percentage = 0
    design.protocol.respiratory_phases = ["Inhale"]
    design.protocol.tactile_sites = ["hand"]

    rows = experiment_schedule_rows(design)
    assert rows
    assert rows[0]["noise_label"] == "Already looming"
    assert rows[0]["noise_type"] == "custom_audio"

    design_path = tmp_path / "design.json"
    output_dir = tmp_path / "rendered"
    save_design(design, design_path)
    result = render_design_with_3dti(
        design_path,
        output_dir,
        seed=123,
        backend_executable=tmp_path / "present" / "pps-3dti-renderer.exe",
    )

    assert result.status == "rendered_reference"
    assert len(result.wav_paths) == 1
    audio, sample_rate = sf.read(result.wav_paths[0], always_2d=True)
    assert sample_rate == 44100
    assert audio.shape == (2205, 3)
    assert np.max(np.abs(audio[:, 0])) > 0.1
    assert np.max(np.abs(audio[:, 1])) > 0.1
    assert np.max(np.abs(audio[:, 2])) > 0.1

    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"]["type"] == "imported_audio"
    assert manifest["source"]["imported_audio_count"] == 1
    with result.qc_path.open(newline="", encoding="utf-8") as f:
        qc_rows = list(csv.DictReader(f))
    assert qc_rows[0]["source_kind"] == "imported_audio"


def test_native_manifest_postprocess_replaces_placeholder_hashes(tmp_path: Path):
    design = default_design()
    design.noises = design.noises[:1]
    config = build_render_config(design, seed=777, output_dir=tmp_path, samples_per_second=2.0)
    backend = tmp_path / "pps-3dti-renderer.exe"
    wav = tmp_path / "looming_Pink_noise.wav"
    tactile_events = tmp_path / "render_tactile_events.csv"
    manifest_path = tmp_path / "render_manifest.json"
    backend.write_bytes(b"native backend")
    wav.write_bytes(b"RIFF fake native wav")
    tactile_events.write_text("soa_ms,tactile_channel\n300,2\n", encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "status": "rendered_3dti",
                "wav_outputs": [
                    {
                        "path": str(wav),
                        "sha256": "native-wrapper-does-not-compute-sha256-yet",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    postprocess_native_manifest(
        manifest_path,
        config=config,
        backend_executable=backend,
        wav_paths=[wav],
        tactile_events_path=tactile_events,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "rendered_3dti"
    assert manifest["render_engine"] == "native-3dti"
    assert manifest["backend_executable_sha256"] == sha256_file(backend)
    assert manifest["listener"] == config["listener"]
    assert manifest["tactile_events"]["sha256"] == sha256_file(tactile_events)
    assert manifest["wav_outputs"][0]["sha256"] == sha256_file(wav)


def test_design_loads_string_audio_preload_paths():
    design = design_from_dict(
        {
            "sofa_file": "",
            "custom_looming_files": ["assets/custom_looming.wav"],
            "prestimulus_files": ["assets/custom_prestimulus.wav"],
        }
    )
    assert design.sofa_file == DEFAULT_SOFA_FILE
    assert design.custom_looming_files[0].label == "custom_looming"
    assert design.prestimulus_files[0].target_duration_s == 4.0
    assert design.prestimulus_files[0].placement == "before"
    assert design.custom_looming_files[0].motion_mode == "looming"
    assert design.prestimulus_files[0].motion_mode == "stationary"


def test_render_config_records_custom_stimulus_assembly(tmp_path: Path):
    design = default_design()
    design.noises = design.noises[:1]
    design.prestimulus_files = [
        AudioFileSpec(
            "inhale instruction",
            "assets/breathing/Inhale.wav",
            4.0,
            placement="before",
            target_source_label="Pink frontal",
            phase="Inhale",
            gap_s=0.15,
            sequence_order=3,
            motion_mode="stationary",
        )
    ]
    design.noises[0].sequence_order = 2
    design.noises[0].motion_mode = "stationary"

    config = build_render_config(design, seed=20250604, output_dir=tmp_path)

    components = config["source"]["stimulus_assembly"]["components"]
    snippets = config["source"]["stimulus_assembly"]["snippets"]
    assert config["source"]["stimulus_assembly"]["integration"] == "recorded_for_session_assembly"
    assert [component["component_kind"] for component in components[:2]] == ["generated_noise", "instruction_snippet"]
    assert components[0]["sequence_order"] == 2
    assert components[0]["motion_mode"] == "stationary"
    assert snippets[0]["label"] == "inhale instruction"
    assert snippets[0]["placement"] == "before"
    assert snippets[0]["target_source_label"] == "Pink frontal"
    assert snippets[0]["phase"] == "Inhale"
    assert snippets[0]["gap_s"] == pytest.approx(0.15)
    assert snippets[0]["sequence_order"] == 3
    assert snippets[0]["motion_mode"] == "stationary"


def test_protocol_summary_and_export_use_repetitions_soas_spatial_values_and_catches(tmp_path: Path):
    design = default_design()
    design.protocol.repetitions_per_condition = 2
    design.protocol.soa_values_ms = [100, 300]
    design.protocol.spatial_values_cm = [90.0, 70.0]
    design.protocol.pair_spatial_values_with_soas = True
    design.protocol.catch_trial_percentage = 20.0
    design.protocol.include_baseline_trials = True
    design.protocol.respiratory_phases = ["Inhale"]
    design.protocol.blocks = 3
    design.protocol.participants = 4

    summary = protocol_summary(design)
    assert summary["audio_tactile_trials"] == 8
    assert summary["baseline_trials"] == 4
    assert summary["catch_trials"] == 3
    assert summary["total_trials"] == 15
    assert summary["trials_per_block"] == 5
    assert summary["total_participant_trials"] == 60

    protocol_path = tmp_path / "protocol.csv"
    export_protocol_csv(design, protocol_path)
    text = protocol_path.read_text(encoding="utf-8")
    assert "Audio-Tactile" in text
    assert "Catch" in text


def test_protocol_can_use_full_factorial_soa_by_spatial_values():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol.soa_values_ms = [100, 300]
    design.protocol.spatial_values_cm = [40.0, 80.0, 120.0]
    design.protocol.pair_spatial_values_with_soas = False
    design.protocol.include_baseline_trials = False
    design.protocol.catch_trial_percentage = 0.0
    design.protocol.respiratory_phases = ["Any"]
    summary = protocol_summary(design)
    assert summary["audio_tactile_trials"] == 6
    assert summary["total_trials"] == 6


def test_non_target_controls_can_skip_sequence_variant_crossing():
    design = default_design()
    design.noises = [
        NoiseDefinition("Approach", "pink", 0.0),
        NoiseDefinition("Recede", "pink", 0.0),
    ]
    design.protocol = ProtocolSpec(
        repetitions_per_condition=1,
        soa_values_ms=[0, 4000],
        spatial_values_cm=[93.0, 5.0],
        pair_spatial_values_with_soas=True,
        include_catch_trials=True,
        catch_trial_percentage=0.0,
        catch_trials_exact=1,
        catch_crosses_sequence_variants=False,
        include_baseline_trials=True,
        baseline_soa_values_ms=[0, 4000],
        baseline_crosses_sequence_variants=False,
        respiratory_phases=["Any"],
        blocks=1,
        trial_strips=[
            TrialStripSpec(
                strip_id="moving-sound",
                label="Moving sound",
                elements=[
                    TrialStripElementSpec(
                        kind="looming_stimulus",
                        label="Moving sound",
                        source_labels=["Approach", "Recede"],
                    )
                ],
            )
        ],
    )

    rows = block_trial_rows(design)
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row["trial_type"])] = counts.get(str(row["trial_type"]), 0) + 1

    assert counts == {"Audio-Tactile": 4, "Baseline": 2, "Catch": 1}
    assert protocol_summary(design)["total_trials"] == 7


def test_block_specs_partition_trial_pool_by_stimulus_type():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol.repetitions_per_condition = 1
    design.protocol.soa_values_ms = [100, 300]
    design.protocol.spatial_values_cm = [80.0, 40.0]
    design.protocol.respiratory_phases = ["Any"]
    design.protocol.participants = 3
    design.protocol.block_specs = [
        BlockSpec("Multisensory", ["Audio-Tactile"]),
        BlockSpec("Baseline", ["Baseline"]),
        BlockSpec("Catch", ["Catch"]),
    ]

    rows = block_trial_rows(design)
    by_block = {}
    for row in rows:
        by_block.setdefault(row["block_label"], set()).add(row["trial_type"])

    assert by_block["Multisensory"] == {"Audio-Tactile"}
    assert by_block["Baseline"] == {"Baseline"}
    assert by_block["Catch"] == {"Catch"}
    assert len(rows) == protocol_summary(design)["total_trials"]


def test_repeat_trial_pool_per_block_repeats_eligible_rows_in_each_block():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol.repetitions_per_condition = 1
    design.protocol.soa_values_ms = [100, 300]
    design.protocol.spatial_values_cm = [80.0, 40.0]
    design.protocol.respiratory_phases = ["Any"]
    design.protocol.include_baseline_trials = False
    design.protocol.catch_trial_percentage = 0.0
    design.protocol.block_specs = [
        BlockSpec("Congruent", ["Audio-Tactile"]),
        BlockSpec("Incongruent", ["Audio-Tactile"]),
    ]
    design.protocol.repeat_trial_pool_per_block = True

    rows = block_trial_rows(design)
    soas_by_block: dict[str, set[int]] = {}
    for row in rows:
        soas_by_block.setdefault(str(row["block_label"]), set()).add(int(row["soa_ms"]))

    assert soas_by_block == {
        "Congruent": {100, 300},
        "Incongruent": {100, 300},
    }
    assert protocol_summary(design)["total_trials"] == 4


def test_canzoneri_profile_distributes_reported_trial_pool_across_two_blocks():
    templates = load_templates(Path(__file__).resolve().parents[1] / "study_templates")
    canzoneri = next(template for template in templates if template.template_id == "canzoneri_2012_dynamic_sounds")

    rows = block_trial_rows(canzoneri.design)

    assert len(rows) == 188
    assert Counter(row["trial_type"] for row in rows) == {
        "Audio-Tactile": 80,
        "Baseline": 32,
        "Catch": 76,
    }
    assert Counter(row["block_label"] for row in rows) == {"Block 1": 94, "Block 2": 94}
    assert Counter(
        row["motion_direction"] for row in rows if row["trial_type"] == "Audio-Tactile"
    ) == {"looming": 40, "receding": 40}
    assert Counter(
        row["motion_direction"] for row in rows if row["trial_type"] == "Baseline"
    ) == {"looming": 16, "receding": 16}


def test_participant_block_order_is_randomized_but_block_contents_are_fixed():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol.participants = 4
    design.protocol.block_specs = [
        BlockSpec("Near", ["Audio-Tactile", "Catch"]),
        BlockSpec("Baseline", ["Baseline"]),
        BlockSpec("Far", ["Audio-Tactile", "Catch"]),
    ]
    design.protocol.block_order_randomization = "counterbalanced_rotation"

    orders = participant_block_orders(design)
    assert len({tuple(order) for order in orders.values()}) > 1
    assert {tuple(sorted(order)) for order in orders.values()} == {("Baseline", "Far", "Near")}

    fixed_counts = {}
    for row in block_trial_rows(design):
        fixed_counts[row["block_label"]] = fixed_counts.get(row["block_label"], 0) + 1
    for participant_id in orders:
        participant_rows = [row for row in experiment_schedule_rows(design) if row["participant_id"] == participant_id]
        participant_counts = {}
        for row in participant_rows:
            participant_counts[row["block_label"]] = participant_counts.get(row["block_label"], 0) + 1
        assert participant_counts == fixed_counts


def test_trial_assembler_preview_rows_follow_block_schedule():
    design = default_design()
    design.noises = design.noises[:1]
    design.protocol.participants = 2
    design.protocol.block_specs = [
        BlockSpec("Multisensory", ["Audio-Tactile", "Catch"]),
        BlockSpec("Baseline", ["Baseline"]),
    ]

    trial_rows = trial_assembler_preview_rows(design, limit=5)
    order_rows = participant_order_preview_rows(design)

    assert trial_rows
    assert set(trial_rows[0]) == {"block", "trial", "type", "phase", "soa_ms", "space_cm", "tactile_site", "noise"}
    assert {row["block"] for row in trial_rows}.issubset({"Multisensory", "Baseline"})
    assert len(order_rows) == 2
    assert order_rows[0]["participant"] == "P001"
    assert "Multisensory" in order_rows[0]["block_order"]


def test_runner_asset_status_and_launch_command(tmp_path: Path):
    stimuli = tmp_path / "Participant_Sequences"
    participant = stimuli / "P001" / "Part1"
    participant.mkdir(parents=True)
    (participant / "P001_PPS_part1_1a_concatenated.wav").write_bytes(b"RIFF")

    status = runner_asset_status(stimuli)
    command = runner_launch_command(
        stimuli_dir=stimuli,
        instructions_dir=tmp_path / "instructions",
        settings_file=tmp_path / "settings.json",
        demographics_dir=tmp_path / "demographics",
        recordings_dir=tmp_path / "recordings",
        list_devices=True,
        python_executable="python-test",
    )

    assert status["ready"] is True
    assert status["participants"] == 1
    assert status["block_wavs"] == 1
    assert command[:3] == ["python-test", "-m", "peripersonal_space_toolkit.audio_device_stress"]
    assert "--dry-run" in command
    assert "--device-query" in command
    assert "Komplete" in command


def test_all_study_templates_load_and_summarize():
    templates = load_templates(Path(__file__).resolve().parents[1] / "study_templates")
    assert len(templates) >= 20
    template_ids = {template.template_id for template in templates}
    assert len(template_ids) == len(templates)
    assert {
        "canzoneri_2012_dynamic_sounds",
        "canzoneri_2013_amputation_prosthesis",
        "canzoneri_2013_tool_use_reshaping",
        "ferri_2015_artificial_looming_valence",
        "ferri_2015_ecological_looming_valence",
        "galli_2015_wheelchair_full_body",
        "lerner_2021_3d_audio_tactile_boundary",
        "matsuda_2021_four_directions",
        "noel_2015_bodily_self",
        "noel_2015_bodily_self_back_space",
        "noel_2015_walking_full_body_action",
        "pfeiffer_2018_lateral_perihead_left_to_right",
        "serino_2015_front_back_trunk_exp2",
        "serino_2015_peri_hand_exp3",
        "serino_2015_peri_trunk_exp1",
        "serino_2015_toolless_sync_training",
        "taffou_2014_cynophobic_rear_looming",
        "teneggi_2013_social_face_pps",
        "tonelli_2019_echolocation",
    }.issubset(template_ids)
    verified = {template.verification_status for template in templates}
    assert "verified" in verified
    assert "partial" in verified
    for template in templates:
        warnings = validate_design(template.design)
        assert all("Unsupported" not in warning for warning in warnings)
        summary = protocol_summary(template.design)
        assert summary["total_trials"] > 0
        assert template.citation
        assert template.source_url


def test_study_template_citation_exports_use_paper_metadata():
    templates = load_templates(Path(__file__).resolve().parents[1] / "study_templates")
    canzoneri = next(template for template in templates if template.template_id == "canzoneri_2012_dynamic_sounds")

    label = study_template_citation_label(canzoneri)
    bibtex = study_template_bibtex(canzoneri)
    csl = json.loads(study_template_csl_json(canzoneri))

    assert "Canzoneri" in label
    assert "(2012)" in label
    assert "Dynamic sounds capture" in label
    assert "@article{canzoneri_2012_dynamic_sounds" in bibtex
    assert "doi = {10.1371/journal.pone.0044306}" in bibtex
    assert "original citation" in bibtex
    assert csl["id"] == "canzoneri_2012_dynamic_sounds"
    assert csl["DOI"] == "10.1371/journal.pone.0044306"
    assert csl["issued"]["date-parts"] == [[2012]]


def test_designer_parser_can_be_built_without_opening_window():
    parser = designer_app.build_arg_parser()
    args = parser.parse_args(["--design", "configs/stimulus_design.example.json"])
    assert args.design.name == "stimulus_design.example.json"
