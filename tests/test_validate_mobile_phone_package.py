from __future__ import annotations

import importlib.util
import csv
import json
import sys
from pathlib import Path

from peripersonal_space_toolkit.mobile_phone_runtime import (
    build_mobile_package_manifest,
    validate_mobile_package_manifest,
)
from peripersonal_space_toolkit.session_runner import RunBlock, RunPackage


SCRIPT_PATH = Path("validation_protocols/scripts/validate_mobile_phone_package.py")
spec = importlib.util.spec_from_file_location("validate_mobile_phone_package", SCRIPT_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def test_mobile_phone_package_validator_loads_manifest_from_folder(tmp_path: Path):
    manifest = build_mobile_package_manifest(_package(tmp_path), phone_owned_session=True)
    package_dir = tmp_path / "package-dir"
    package_dir.mkdir()
    (package_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    loaded = validator.load_mobile_manifest(package_dir)
    result = validate_mobile_package_manifest(
        loaded,
        require_phone_owned_session=True,
        require_building_blocks=True,
    )

    assert result.ok is True
    assert result.summary["package_id"] == manifest["package_id"]


def _package(tmp_path: Path) -> RunPackage:
    wav = tmp_path / "block_01.wav"
    wav.write_bytes(b"RIFF....WAVE")
    block_manifest = tmp_path / "block_01.csv"
    with block_manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "Trial_Number",
                "Trial_UID",
                "Trial_Type",
                "Family",
                "SOA_ms",
                "Row_Label",
                "Noise_Type",
                "Trial_Start_S",
                "Trial_Duration_S",
                "Trial_End_S",
                "Tactile_Onset_S",
                "Response_Window_Onset_S",
                "Trial_File_Path",
                "Source_SHA256",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "Trial_Number": "1",
                "Trial_UID": "trial-a",
                "Trial_Type": "audio_tactile",
                "Family": "audio_tactile",
                "SOA_ms": "300",
                "Row_Label": "inhale",
                "Noise_Type": "white",
                "Trial_Start_S": "2.000",
                "Trial_Duration_S": "4.000",
                "Trial_End_S": "6.000",
                "Tactile_Onset_S": "1.250",
                "Response_Window_Onset_S": "1.250",
                "Trial_File_Path": str(wav),
                "Source_SHA256": "",
            }
        )
    return RunPackage(
        participant_id="P001",
        session_id="session-001",
        created_at="2026-06-28T00:00:00Z",
        session_dir=tmp_path / "sessions" / "P001" / "session-001",
        design_path=tmp_path / "design.json",
        protocol_path=tmp_path / "protocol.json",
        manifest_path=tmp_path / "session_manifest.json",
        render_manifest_path=None,
        blocks=[
            RunBlock(
                index=1,
                label="Block 01",
                manifest_path=block_manifest,
                wav_path=wav,
                trial_count=1,
                duration_s=6.0,
            )
        ],
    )
