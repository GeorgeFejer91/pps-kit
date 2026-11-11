from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from peripersonal_space_toolkit import design, resource_limits, session_runner
from peripersonal_space_toolkit.resource_limits import ResourceLimit


def test_large_factor_product_is_rejected_before_trial_expansion():
    candidate = design.default_design()
    candidate.protocol.repetitions_per_condition = 10**12
    with pytest.raises(ResourceLimit, match="Audio-tactile trials"):
        design.protocol_trial_rows(candidate)


def test_repeated_blocks_cannot_multiply_a_bounded_pool_without_limit():
    candidate = design.default_design()
    candidate.protocol = design.ProtocolSpec(
        repetitions_per_condition=1000, soa_values_ms=[300], spatial_values_cm=[10],
        respiratory_phases=["Any"], tactile_sites=["hand"], auditory_motion_directions=["looming"],
        include_baseline_trials=False, include_catch_trials=False, catch_trial_percentage=0,
        repeat_trial_pool_per_block=True, blocks=1024, participants=1,
    )
    candidate.noises = candidate.noises[:1]
    with pytest.raises(ResourceLimit, match="Repeated block schedule"):
        design.block_trial_rows(candidate)


def test_low_storage_rejects_block_assembly_before_decoding(tmp_path: Path, monkeypatch):
    wav, csv = tmp_path / "source.wav", tmp_path / "source.csv"
    sf.write(wav, np.zeros((441, 3), dtype=np.float32), 44100)
    csv.write_text("trial_file_path\nsource.wav\n", encoding="utf-8")
    monkeypatch.setattr(resource_limits.shutil, "disk_usage", lambda _: SimpleNamespace(free=0))
    monkeypatch.setattr(sf, "read", lambda *args, **kwargs: pytest.fail("Audio decoded before storage preflight"))
    output = tmp_path / "prepared" / "block.wav"
    with pytest.raises(ResourceLimit, match="Free space"):
        session_runner._materialize_segment_block_wav(
            output, [{"trial_file_path": "source.wav", "block_trial_index": "1"}],
            participant_id="P001", session_id="test", part_number=1, phase="single", phase_label="Single",
            output_block_index=1, participant_block_position=1, source_block_index=1,
            source_block_label="Block 1", source_block_csv_path=csv,
        )
    assert not output.exists() and wav.exists()


def test_assembly_csv_row_limit_rejects_whole_input_instead_of_truncating(tmp_path: Path):
    csv = tmp_path / "plan.csv"
    csv.write_text("trial\n" + "one\n" * (resource_limits.MAX_PLAN_ROWS + 1), encoding="utf-8")
    with pytest.raises(ResourceLimit, match="Assembly CSV"):
        resource_limits.read_csv_rows(csv)


def test_block_assembly_streams_trials_with_bounded_memory_and_exact_pcm(tmp_path: Path, monkeypatch):
    rate = 1000
    stereo = np.full((100, 2), 1024, dtype=np.int16)
    three_channels = np.full((100, 3), -2048, dtype=np.int16)
    sf.write(tmp_path / "stereo.wav", stereo, rate, subtype="PCM_16")
    sf.write(tmp_path / "three.wav", three_channels, rate, subtype="PCM_16")
    csv = tmp_path / "source.csv"
    csv.write_text("trial_file_path\nstereo.wav\nthree.wav\n", encoding="utf-8")
    monkeypatch.setattr(resource_limits, "MAX_WORKING_AUDIO_BYTES", 5_000)
    rows = [
        {"trial_file_path": "three.wav", "block_trial_index": "2", "family": "catch"},
        {"trial_file_path": "stereo.wav", "block_trial_index": "1", "family": "catch", "iti_ms": "20"},
    ]

    output = tmp_path / "prepared" / "block.wav"
    duration, sample_rate, channels, schedule, _ = session_runner._materialize_segment_block_wav(
        output, rows, participant_id="P001", session_id="test", part_number=1,
        phase="single", phase_label="Single", output_block_index=1, participant_block_position=1,
        source_block_index=1, source_block_label="Block 1", source_block_csv_path=csv,
    )

    rendered, written_rate = sf.read(output, dtype="int16", always_2d=True)
    expected = np.concatenate((np.pad(stereo, ((0, 0), (0, 1))), np.zeros((20, 3), np.int16), three_channels))
    np.testing.assert_array_equal(rendered, expected)
    assert (sample_rate, written_rate, channels, duration) == (1000, 1000, 3, 0.22)
    assert [(r["Trial_Start_Sample"], r["Trial_End_Sample"]) for r in schedule] == [(0, 120), (120, 220)]


@pytest.mark.parametrize(
    ("onset_s", "audio_start", "tactile_start", "length"),
    [(-0.05, 50, 0, 150), (0.08, 0, 80, 120), (0.13, 0, 130, 170)],
)
def test_baked_trial_keeps_whole_tactile_cue_outside_audio_span(
    tmp_path: Path, monkeypatch, onset_s, audio_start, tactile_start, length,
):
    from peripersonal_space_toolkit import dashboard_app

    source = tmp_path / "stereo.wav"
    original = np.full((100, 2), 1024, dtype=np.int16)
    sf.write(source, original, 1000, subtype="PCM_16")
    monkeypatch.setattr(dashboard_app, "_load_tactile_cue", lambda _: np.full(40, 0.25, dtype=np.float32))
    monkeypatch.setattr(dashboard_app, "_ffmpeg_merge_three_channel", lambda *_: False)
    target = tmp_path / "trial.wav"
    layout = dashboard_app._tactile_trial_layout(source, onset_s)
    dashboard_app._write_three_channel_trial_wav(target, source, layout, tmp_path / "work")

    actual, rate = sf.read(target, dtype="int16", always_2d=True)
    expected = np.zeros((length, 3), dtype=np.int16)
    expected[audio_start:audio_start + len(original), :2] = original
    expected[tactile_start:tactile_start + 40, 2] = 8192
    assert rate == 1000
    np.testing.assert_array_equal(actual, expected)
