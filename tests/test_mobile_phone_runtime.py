from __future__ import annotations

import csv
import json
from pathlib import Path

from peripersonal_space_toolkit.mobile_phone_runtime import (
    MOBILE_PACKAGE_SCHEMA,
    MOBILE_RUN_COMPLETE_SCHEMA,
    build_mobile_package_list,
    build_mobile_package_manifest,
    mobile_asset_path,
    mobile_package_id,
    write_mobile_runtime_events,
)
from peripersonal_space_toolkit.output_layout import output_runner_logs_dir
from peripersonal_space_toolkit.session_runner import RunBlock, RunPackage


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
        writer.writerow(
            {
                "Trial_Number": "2",
                "Trial_UID": "trial-b",
                "Trial_Type": "catch",
                "Family": "catch",
                "SOA_ms": "",
                "Row_Label": "exhale",
                "Noise_Type": "pink",
                "Trial_Start_S": "6.000",
                "Trial_Duration_S": "4.000",
                "Trial_End_S": "10.000",
                "Tactile_Onset_S": "",
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
                trial_count=2,
                duration_s=10.0,
            )
        ],
    )


def test_mobile_package_manifest_exports_assets_trials_and_phone_tactile_cues(tmp_path):
    package = _package(tmp_path)

    manifest = build_mobile_package_manifest(package)

    assert manifest["schema"] == MOBILE_PACKAGE_SCHEMA
    assert manifest["reconstruction"]["schema"] == "pps-mobile-reconstruction-contract.v1"
    assert manifest["lsl"]["stream_names"]["rich_markers"] == "PPSMarkersV2"
    assert manifest["building_blocks"][0]["role"] == "trial_building_block"
    assert manifest["schedule"]["execution_order"] == ["block-01"]
    assert manifest["package_id"] == mobile_package_id(package)
    assert manifest["mobile_runnable"] is True
    assert manifest["runtime"]["audio_playback_strategy"] == "audiotrack_pcm_wav_playback_head"
    assert manifest["runtime"]["tactile_cue_scheduler"] == "audiotrack_playback_head"
    assert manifest["assets"][0]["sha256"]
    assert manifest["blocks"][0]["trials"][0]["trial_uid"] == "trial-a"
    assert manifest["blocks"][0]["tactile_cues"] == [
        {
            "cue_id": 1,
            "trial_number": 1,
            "trial_uid": "trial-a",
            "time_s": 3.25,
            "trial_relative_time_s": 1.25,
            "soa_ms": "300",
            "row_label": "inhale",
            "noise_type": "white",
        }
    ]
    assert mobile_asset_path(package, manifest["package_id"], "block-01-audio") == package.blocks[0].wav_path


def test_mobile_package_list_and_manifest_can_mark_phone_owned_sessions(tmp_path):
    package = _package(tmp_path)

    listing = build_mobile_package_list(package, phone_owned_session=True)
    manifest = build_mobile_package_manifest(package, phone_owned_session=True)

    assert listing["packages"][0]["phone_owned_session"] is True
    assert manifest["phone_owned_session"] is True
    assert manifest["runtime"]["session_owner"] == "phone"


def test_mobile_runtime_upload_writes_runner_log_artifacts(tmp_path):
    package = _package(tmp_path)
    output_root = tmp_path / "output"
    payload = {
        "package_id": mobile_package_id(package),
        "participant_metadata": {"participant_id": "P001", "age_years": "30"},
        "events": [
            {"type": "block_start", "block_id": "block-01", "elapsed_ms": 0},
            {"type": "tap", "trial_uid": "trial-a", "elapsed_ms": 3500, "rt_ms": 250},
        ],
        "lsl_marker_mirror": [
            {"event_type": "block_start", "event_id": 1, "participant_id": "P001"},
            {"event_type": "tap", "event_id": 2, "participant_id": "P001", "trial_uid": "trial-a"},
        ],
        "command_diary": [
            {"command": "start_experiment", "status": "applied"},
        ],
    }

    result = write_mobile_runtime_events(
        package,
        output_root=output_root,
        run_id="run-001",
        payload=payload,
        complete=True,
    )

    assert result["schema"] == MOBILE_RUN_COMPLETE_SCHEMA
    artifact = Path(result["artifact_path"])
    assert artifact.is_file()
    loaded = json.loads(artifact.read_text(encoding="utf-8"))
    assert loaded["complete"] is True
    assert loaded["event_count"] == 2
    assert loaded["participant_metadata"]["age_years"] == "30"
    assert (output_runner_logs_dir(output_root) / "mobile_phone_runtime" / "P001").is_dir()
    assert (artifact.parent / "events.jsonl").read_text(encoding="utf-8").count("\n") == 2
    assert (artifact.parent / "events.csv").is_file()
    assert (artifact.parent / "lsl_marker_mirror.csv").is_file()
    assert (artifact.parent / "command_diary.jsonl").read_text(encoding="utf-8").count("\n") == 1
