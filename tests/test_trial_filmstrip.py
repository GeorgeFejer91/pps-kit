from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf

from peripersonal_space_toolkit.design import (
    AudioFileSpec,
    NoiseDefinition,
    ProtocolSpec,
    TrialStripElementSpec,
    TrialStripSpec,
    block_trial_rows,
    default_design,
    design_from_dict,
    design_to_dict,
    export_protocol_csv,
)
from peripersonal_space_toolkit.session_runner import prepare_run_package


def _filmstrip_design(source_count: int = 4):
    design = default_design()
    colors = ["pink", "blue", "white", "brown"][:source_count]
    design.noises = [NoiseDefinition(label=color.title(), noise_type=color) for color in colors]
    design.prestimulus_files = [
        AudioFileSpec(label="Inhale", path="local_data/audio/inhale.wav", motion_mode="stationary"),
        AudioFileSpec(label="Exhale", path="local_data/audio/exhale.wav", motion_mode="stationary"),
    ]
    source_labels = [noise.label for noise in design.noises]
    design.protocol = ProtocolSpec(
        repetitions_per_condition=1,
        soa_values_ms=[100, 200, 300, 400, 500],
        spatial_values_cm=[],
        pair_spatial_values_with_soas=False,
        auditory_motion_directions=["looming"],
        tactile_sites=["hand"],
        include_catch_trials=False,
        catch_trial_percentage=0.0,
        include_baseline_trials=False,
        respiratory_phases=[],
        blocks=1,
        participants=2,
        random_seed=20250604,
        trial_strips=[
            TrialStripSpec(
                strip_id="inhale-row",
                label="Inhale trial type",
                elements=[
                    TrialStripElementSpec(kind="fixed_audio", label="Inhale", source_label="Inhale"),
                    TrialStripElementSpec(kind="looming_stimulus", label="Looming Stimulus", source_labels=source_labels, randomized=True),
                ],
            ),
            TrialStripSpec(
                strip_id="exhale-row",
                label="Exhale trial type",
                elements=[
                    TrialStripElementSpec(kind="fixed_audio", label="Exhale", source_label="Exhale"),
                    TrialStripElementSpec(kind="looming_stimulus", label="Looming Stimulus", source_labels=source_labels, randomized=True),
                ],
            ),
        ],
    )
    return design


def test_trial_strips_round_trip_and_interleave_within_block_event_sequences():
    design = design_from_dict(design_to_dict(_filmstrip_design()))

    rows = block_trial_rows(design)

    assert len(rows) == 2 * 4 * 5
    assert rows[0]["trial_type_label"] == "Inhale trial type"
    assert rows[1]["trial_type_label"] == "Exhale trial type"
    assert rows[2]["trial_type_label"] == "Inhale trial type"
    assert rows[3]["trial_type_label"] == "Exhale trial type"
    assert rows[0]["trial_type"] == "Audio-Tactile"
    assert rows[0]["trial_strip_label"] == rows[0]["trial_type_label"]
    assert sum(1 for row in rows if row["trial_type_label"] == "Inhale trial type") == 20
    assert sum(1 for row in rows if row["trial_type_label"] == "Exhale trial type") == 20
    assert all(" | " in row["sequence_labels"] for row in rows)


def test_trial_sequence_jitter_multiplies_sequence_variants():
    design = _filmstrip_design(source_count=1)
    design.protocol.soa_values_ms = [100, 200, 300, 400]
    for strip in design.protocol.trial_strips:
        strip.elements.insert(
            1,
            TrialStripElementSpec(kind="jitter", label="Jitter", jitter_values_ms=[500, 700], randomized=True),
        )

    rows = [row for row in block_trial_rows(design) if row["trial_type"] == "Audio-Tactile"]

    assert len(rows) == 2 * 1 * 2 * 4
    assert {row["jitter_labels"] for row in rows} == {"Jitter"}
    assert {row["jitter_values_ms"] for row in rows} == {"500", "700"}
    assert {row["jitter_total_ms"] for row in rows} == {500, 700}
    for label in {"Inhale trial type", "Exhale trial type"}:
        label_values = [row["jitter_values_ms"] for row in rows if row["trial_type_label"] == label]
        assert label_values.count("500") == 4
        assert label_values.count("700") == 4
    assert all("Jitter (" in row["sequence_labels"] for row in rows)


def test_trial_sequence_crosses_repeated_audio_and_jitter_boxes_in_one_row():
    design = _filmstrip_design(source_count=2)
    design.protocol.trial_strips = [design.protocol.trial_strips[0]]
    design.protocol.soa_values_ms = [100, 200]
    source_labels = [noise.label for noise in design.noises]
    design.protocol.trial_strips[0].elements = [
        TrialStripElementSpec(kind="fixed_audio", label="Inhale", source_label="Inhale"),
        TrialStripElementSpec(kind="jitter", label="Jitter", jitter_values_ms=[500, 700], randomized=True),
        TrialStripElementSpec(kind="looming_stimulus", label="First sound", source_labels=source_labels, randomized=True),
        TrialStripElementSpec(kind="fixed_audio", label="Exhale", source_label="Exhale"),
        TrialStripElementSpec(kind="jitter", label="Jitter", jitter_values_ms=[1100, 2700], randomized=True),
        TrialStripElementSpec(kind="looming_stimulus", label="Second sound", source_labels=source_labels, randomized=True),
    ]

    rows = [row for row in block_trial_rows(design) if row["trial_type"] == "Audio-Tactile"]

    assert len(rows) == 1 * 2 * 2 * 2 * 2 * 2
    assert all(row["sequence_labels"].count("Jitter") == 2 for row in rows)
    assert all("Inhale | Jitter" in row["sequence_labels"] for row in rows)
    assert all("Exhale | Jitter" in row["sequence_labels"] for row in rows)
    assert {row["jitter_values_ms"] for row in rows} == {"500; 1100", "500; 2700", "700; 1100", "700; 2700"}
    assert {row["sequence_source_labels"] for row in rows} == {"Pink; Pink", "Pink; Blue", "Blue; Pink", "Blue; Blue"}


def test_trial_strips_repetitions_and_catches_disable_tactile():
    design = _filmstrip_design(source_count=1)
    design.protocol.soa_values_ms = [250]
    design.protocol.repetitions_per_condition = 2
    design.protocol.catch_trial_percentage = 50

    rows = block_trial_rows(design)
    noncatch = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    catches = [row for row in rows if row["trial_type"] == "Catch"]

    assert len(noncatch) == 4
    assert len(catches) == 4
    assert all(row["tactile_enabled"] is True for row in noncatch)
    assert all(row["tactile_enabled"] is False for row in catches)


def test_trial_strips_add_baseline_events_inside_the_same_block():
    design = _filmstrip_design(source_count=4)
    design.protocol.include_baseline_trials = True
    design.protocol.baseline_strategy = "soa_zero"
    design.protocol.baseline_trial_percentage = 20

    rows = block_trial_rows(design)
    audio_tactile = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    baselines = [row for row in rows if row["trial_type"] == "Baseline"]

    assert len(audio_tactile) == 40
    assert len(baselines) == 10
    assert {row["block_label"] for row in baselines} == {"Block 1"}
    assert {row["trial_type_label"] for row in baselines} == {"Inhale trial type", "Exhale trial type"}
    assert {row["soa_ms"] for row in baselines} == {0}
    assert all(row["tactile_enabled"] is True for row in baselines)
    assert all("Baseline tactile" in row["sequence_labels"] for row in baselines)


def test_trial_strips_row_mix_percentages_control_block_composition():
    design = _filmstrip_design(source_count=4)
    design.protocol.include_baseline_trials = True
    design.protocol.baseline_strategy = "soa_zero"
    design.protocol.catch_trial_percentage = 0
    design.protocol.baseline_trial_percentage = 0
    for strip in design.protocol.trial_strips:
        strip.audio_tactile_percentage = 80.0
        strip.catch_percentage = 10.0
        strip.baseline_percentage = 10.0

    rows = block_trial_rows(design)
    audio_tactile = [row for row in rows if row["trial_type"] == "Audio-Tactile"]
    catches = [row for row in rows if row["trial_type"] == "Catch"]
    baselines = [row for row in rows if row["trial_type"] == "Baseline"]

    assert len(audio_tactile) == 40
    assert len(catches) == 6
    assert len(baselines) == 6
    for label in {"Inhale trial type", "Exhale trial type"}:
        label_rows = [row for row in rows if row["trial_type_label"] == label]
        assert sum(1 for row in label_rows if row["trial_type"] == "Audio-Tactile") == 20
        assert sum(1 for row in label_rows if row["trial_type"] == "Catch") == 3
        assert sum(1 for row in label_rows if row["trial_type"] == "Baseline") == 3
    assert {row["row_audio_tactile_percent"] for row in rows} == {80.0}
    assert {row["row_catch_percent"] for row in rows} == {10.0}
    assert {row["row_baseline_percent"] for row in rows} == {10.0}
    assert all(row["tactile_enabled"] is False for row in catches)
    assert all(row["tactile_enabled"] is True for row in baselines)


def test_trial_strips_sound_offset_baseline_uses_stimulus_window_timing():
    design = _filmstrip_design(source_count=1)
    design.protocol.include_baseline_trials = True
    design.protocol.baseline_strategy = "sound_offset"
    design.protocol.baseline_trial_percentage = 10

    baselines = [row for row in block_trial_rows(design) if row["trial_type"] == "Baseline"]

    assert baselines
    assert {row["soa_ms"] for row in baselines} == {4000}
    assert {row["baseline_strategy"] for row in baselines} == {"sound_offset"}


def test_trial_strips_min_max_baseline_uses_first_and_last_soas():
    design = _filmstrip_design(source_count=4)
    design.protocol.include_baseline_trials = True
    design.protocol.baseline_strategy = "min_max"
    design.protocol.baseline_trial_percentage = 20

    rows = block_trial_rows(design)
    baselines = [row for row in rows if row["trial_type"] == "Baseline"]

    assert len(baselines) == 10
    assert {row["soa_ms"] for row in baselines} == {100, 500}
    assert {row["baseline_strategy"] for row in baselines} == {"min_max"}


def test_filmstrip_protocol_csv_and_block_manifest_include_sequence_columns(tmp_path: Path):
    design = _filmstrip_design(source_count=1)
    design.protocol.soa_values_ms = [250]
    design.protocol.participants = 1
    render_dir = tmp_path / "render"
    render_dir.mkdir()
    wav_path = render_dir / "looming_pink.wav"
    sf.write(wav_path, np.zeros((441, 3), dtype=np.float32), 44100)

    protocol_path = tmp_path / "protocol.csv"
    export_protocol_csv(design, protocol_path)
    protocol_rows = list(csv.DictReader(protocol_path.open(encoding="utf-8")))

    assert protocol_rows[0]["trial_type_label"] in {"Inhale trial type", "Exhale trial type"}
    assert protocol_rows[0]["trial_type"] == "Audio-Tactile"
    assert protocol_rows[0]["sequence_labels"]
    assert "trial_type_label" in protocol_rows[0]
    assert "row_audio_tactile_percent" in protocol_rows[0]
    assert "row_catch_percent" in protocol_rows[0]
    assert "row_baseline_percent" in protocol_rows[0]
    assert "jitter_labels" in protocol_rows[0]
    assert "jitter_values_ms" in protocol_rows[0]
    assert "jitter_total_ms" in protocol_rows[0]
    assert "baseline_strategy" in protocol_rows[0]
    assert protocol_rows[0]["tactile_enabled"] == "True"

    package = prepare_run_package(
        design,
        "P001",
        render_dir=render_dir,
        session_root=tmp_path / "sessions",
        created_at=datetime(2026, 6, 7, 12, 0, 0),
    )
    block_rows = list(csv.DictReader(package.blocks[0].manifest_path.open(encoding="utf-8")))

    assert "Trial_Strip_Label" in block_rows[0]
    assert "Trial_Type_Label" in block_rows[0]
    assert "Sequence_Labels" in block_rows[0]
    assert "Tactile_Enabled" in block_rows[0]
    assert "Row_Audio_Tactile_Percent" in block_rows[0]
    assert "Row_Catch_Percent" in block_rows[0]
    assert "Row_Baseline_Percent" in block_rows[0]
    assert "Jitter_Labels" in block_rows[0]
    assert "Jitter_Values_Ms" in block_rows[0]
    assert "Jitter_Total_Ms" in block_rows[0]
    assert "Baseline_Strategy" in block_rows[0]
    assert block_rows[0]["Trial_Type_Label"] in {"Inhale trial type", "Exhale trial type"}
    assert block_rows[0]["Trial_Type"] == "Audio-Tactile"
    assert block_rows[0]["Sequence_Labels"]
