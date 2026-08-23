from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_master_blocks_have_expected_columns_and_rows():
    expected_columns = ["Trial_Number", "Trial_Type", "SOA_ms", "Noise_Type", "Respiratory_Phase"]
    for filename in ["Master_Block_1.csv", "Master_Block_2.csv"]:
        path = ROOT / "packages" / "pps-resources" / "assets" / "master_blocks" / filename
        with path.open(newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        assert rows
        assert list(rows[0]) == expected_columns
        assert len(rows) >= 30


def test_sample_analysis_data_is_deidentified_enough_for_public_seed():
    path = ROOT / "packages" / "pps-resources" / "data" / "sample" / "audio_tactile_with_facilitation_preregistered_2p5sd.csv"
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert "participant_id" in rows[0]
    assert "facilitation_ms" in rows[0]
