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
