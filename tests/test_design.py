from __future__ import annotations

from pathlib import Path

import pytest

from peripersonal_space_toolkit import designer_app
from peripersonal_space_toolkit.design import (
    AudioFileSpec,
    BlockSpec,
    block_trial_rows,
    default_design,
    design_from_dict,
    experiment_schedule_rows,
    export_protocol_csv,
    export_trajectory_csv,
    load_design,
    participant_block_orders,
    protocol_summary,
    save_design,
    trajectory_points,
    validate_design,
)
from peripersonal_space_toolkit.templates import load_templates


def test_default_design_matches_four_second_study5_timing():
    design = default_design()
    assert validate_design(design) == []
    assert design.trajectory.movement_duration_s == 3.0
    assert design.trajectory.total_duration_s == 4.0
    points = trajectory_points(design.trajectory, samples=5)
    assert points[0]["radius_m"] == pytest.approx(1.1)
    assert points[-1]["radius_m"] == pytest.approx(0.1)


def test_design_json_round_trip_and_trajectory_export(tmp_path: Path):
    design = default_design()
    design.custom_looming_files = [AudioFileSpec("custom pink", "C:/stimuli/custom_pink.wav", 4.0)]
    design.prestimulus_files = [AudioFileSpec("inhale", "C:/stimuli/inhale.wav", 4.0)]
    design_path = tmp_path / "design.json"
    csv_path = tmp_path / "trajectory.csv"
    save_design(design, design_path)
    loaded = load_design(design_path)
    assert loaded.noises[0].noise_type == "pink"
    assert loaded.custom_looming_files[0].label == "custom pink"
    assert loaded.prestimulus_files[0].path.endswith("inhale.wav")

    export_trajectory_csv(loaded, csv_path, samples=7)
    text = csv_path.read_text(encoding="utf-8")
    assert "time_s,radius_m,azimuth_deg" in text
    assert len(text.strip().splitlines()) == 8


def test_design_loads_string_audio_preload_paths():
    design = design_from_dict(
        {
            "custom_looming_files": ["assets/custom_looming.wav"],
            "prestimulus_files": ["assets/custom_prestimulus.wav"],
        }
    )
    assert design.custom_looming_files[0].label == "custom_looming"
    assert design.prestimulus_files[0].target_duration_s == 4.0


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
    assert summary["audio_tactile_trials"] == 16
    assert summary["baseline_trials"] == 4
    assert summary["catch_trials"] == 5
    assert summary["total_trials"] == 25
    assert summary["trials_per_block"] == 9
    assert summary["total_participant_trials"] == 100

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


def test_all_study_templates_load_and_summarize():
    templates = load_templates(Path(__file__).resolve().parents[1] / "study_templates")
    assert len(templates) >= 5
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


def test_designer_parser_can_be_built_without_opening_window():
    parser = designer_app.build_arg_parser()
    args = parser.parse_args(["--design", "configs/stimulus_design.example.json"])
    assert args.design.name == "stimulus_design.example.json"
