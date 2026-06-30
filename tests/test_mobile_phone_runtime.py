from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from peripersonal_space_toolkit.mobile_phone_runtime import (
    MOBILE_PACKAGE_SCHEMA,
    MOBILE_RUN_COMPLETE_SCHEMA,
    build_mobile_package_list,
    build_mobile_package_manifest,
    validate_mobile_package_manifest,
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
    segment5_manifest = tmp_path / "segment5_manifest.json"
    segment5_manifest.write_text(json.dumps({"randomization_seed": "seed-123"}), encoding="utf-8")
    segment5_hash = hashlib.sha256(segment5_manifest.read_bytes()).hexdigest()
    order_csv = tmp_path / "segment6_order.csv"
    with order_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["participant_id", "phase", "block_index"])
        writer.writeheader()
        writer.writerow({"participant_id": "P001", "phase": "part_01", "block_index": "1"})
    source_run_setup_manifest = tmp_path / "source_run_setup_manifest.json"
    source_run_setup_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-experiment-run-setup.v1",
                "prepared": True,
                "csv_path": str(order_csv),
                "total_block_runs": 1,
                "source_segment5_manifest": str(segment5_manifest),
                "source_segment5_manifest_sha256": segment5_hash,
            }
        ),
        encoding="utf-8",
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
        source_run_setup_manifest_path=source_run_setup_manifest,
        blocks=[
            RunBlock(
                index=1,
                label="Block 01",
                manifest_path=block_manifest,
                wav_path=wav,
                trial_count=2,
                duration_s=10.0,
                metadata={
                    "source_block_csv_path": str(block_manifest),
                    "source_block_csv_sha256": hashlib.sha256(block_manifest.read_bytes()).hexdigest(),
                },
            )
        ],
    )


def test_mobile_package_manifest_exports_assets_trials_and_phone_tactile_cues(tmp_path):
    package = _package(tmp_path)

    manifest = build_mobile_package_manifest(package)

    assert manifest["schema"] == MOBILE_PACKAGE_SCHEMA
    assert manifest["reconstruction"]["schema"] == "pps-mobile-reconstruction-contract.v1"
    assert manifest["reconstruction"]["study_hierarchy"][6] == "segment_6_participant_part_order"
    assert manifest["lsl"]["stream_names"]["rich_markers"] == "PPSMarkersV2"
    assert manifest["building_blocks"][0]["role"] == "trial_building_block"
    assert manifest["schedule"]["execution_order"] == ["block-01"]
    assert manifest["participant_roster"] == ["P001"]
    assert manifest["randomization_seed"] == "seed-123"
    assert manifest["source_segment_hashes"]["schema"] == "pps-mobile-source-segment-hashes.v1"
    assert manifest["source_segment_hashes"]["segment5_block_csvs"][0]["block_id"] == "block-01"
    assert manifest["package_id"] == mobile_package_id(package)
    assert manifest["mobile_runnable"] is True
    assert manifest["runtime"]["audio_playback_strategy"] == "audiotrack_pcm_wav_playback_head"
    assert manifest["runtime"]["tactile_cue_scheduler"] == "audiotrack_playback_head"
    assert manifest["assets"][0]["sha256"]
    assert manifest["blocks"][0]["trials"][0]["building_block_asset_id"] == manifest["building_blocks"][0]["asset_id"]
    assert manifest["schedule"]["blocks"][0]["building_block_asset_ids"][0] == manifest["building_blocks"][0]["asset_id"]
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


def test_mobile_package_manifest_can_export_lightweight_building_block_only_package(tmp_path):
    package = _package(tmp_path)

    manifest = build_mobile_package_manifest(package, phone_owned_session=True, include_block_audio=False)
    result = validate_mobile_package_manifest(
        manifest,
        require_phone_owned_session=True,
        require_building_blocks=True,
        require_lightweight_scheduled_blocks=True,
    )

    assert result.ok is True
    assert manifest["asset_strategy"] == "trial_building_blocks_only"
    assert manifest["reconstruction"]["package_asset_strategy"] == "trial_building_blocks_only"
    assert manifest["mobile_runnable"] is True
    assert manifest["runtime"]["scheduled_block_materialization_strategy"] == "pcm_wav_concat_without_ffmpeg"
    assert {asset["role"] for asset in manifest["assets"]} == {"trial_building_block"}
    assert manifest["blocks"][0]["audio_asset_id"] == "block-01-audio"
    assert "block-01-audio" not in {asset["asset_id"] for asset in manifest["assets"]}
    assert result.summary["lightweight_scheduled_blocks"] is True
    assert result.summary["block_audio_asset_count"] == 0
    assert result.summary["trial_building_block_asset_count"] == 1
    assert any("audio_asset_id 'block-01-audio' is omitted" in warning for warning in result.warnings)


def test_mobile_package_list_can_report_lightweight_transfer_assets(tmp_path):
    package = _package(tmp_path)

    listing = build_mobile_package_list(package, phone_owned_session=True, include_block_audio=False)
    package_row = listing["packages"][0]

    assert package_row["mobile_runnable"] is True
    assert package_row["asset_strategy"] == "trial_building_blocks_only"
    assert package_row["asset_count"] == 1
    assert package_row["total_asset_bytes"] == package.blocks[0].wav_path.stat().st_size


def test_mobile_package_list_and_manifest_can_mark_phone_owned_sessions(tmp_path):
    package = _package(tmp_path)

    listing = build_mobile_package_list(package, phone_owned_session=True)
    manifest = build_mobile_package_manifest(package, phone_owned_session=True)

    assert listing["packages"][0]["phone_owned_session"] is True
    assert manifest["phone_owned_session"] is True
    assert manifest["runtime"]["session_owner"] == "phone"


def test_mobile_package_validation_accepts_strict_phone_owned_hierarchy(tmp_path):
    package = _package(tmp_path)

    manifest = build_mobile_package_manifest(package, phone_owned_session=True)
    result = validate_mobile_package_manifest(
        manifest,
        require_phone_owned_session=True,
        require_building_blocks=True,
    )

    assert result.ok is True
    assert result.failures == []
    assert result.summary["block_count"] == 1
    assert result.summary["building_block_count"] == 1
    assert result.summary["participant_roster_count"] == 1
    assert result.summary["randomization_seed"] == "seed-123"
    assert result.summary["schedule_hash"] == manifest["reconstruction"]["schedule_hash"]


def test_mobile_package_validation_rejects_source_provenance_drift(tmp_path):
    package = _package(tmp_path)
    manifest = build_mobile_package_manifest(package, phone_owned_session=True)
    manifest["participant_roster"] = ["P002"]
    manifest["source_segment_hashes"]["source_run_setup_manifest_sha256"] = "wrong"
    manifest["source_segment_hashes"]["segment5_block_csvs"][0]["sha256"] = "wrong"

    result = validate_mobile_package_manifest(
        manifest,
        require_phone_owned_session=True,
        require_building_blocks=True,
    )

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "participant_roster" in failures
    assert "source_run_setup_manifest_sha256" in failures
    assert "SHA-256 differs from schedule.blocks" in failures


def test_mobile_package_validation_rejects_hierarchy_and_schedule_drift(tmp_path):
    package = _package(tmp_path)
    manifest = build_mobile_package_manifest(package, phone_owned_session=True)
    manifest["schedule"]["execution_order"] = ["wrong-block"]
    manifest["reconstruction"]["study_hierarchy"] = ["study_profile", "phone_runtime_package"]
    manifest["reconstruction"]["schedule_hash"] = "wrong"

    result = validate_mobile_package_manifest(
        manifest,
        require_phone_owned_session=True,
        require_building_blocks=True,
    )

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "execution_order" in failures
    assert "study_hierarchy" in failures
    assert "schedule_hash" in failures


def test_mobile_package_validation_rejects_missing_building_block_reference(tmp_path):
    package = _package(tmp_path)
    manifest = build_mobile_package_manifest(package, phone_owned_session=True)
    manifest["building_blocks"] = []
    manifest["assets"] = [asset for asset in manifest["assets"] if asset["role"] != "trial_building_block"]

    result = validate_mobile_package_manifest(
        manifest,
        require_phone_owned_session=True,
        require_building_blocks=True,
    )

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "trial_building_block records" in failures
    assert "not listed in building_blocks" in failures


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
            {
                "event_type": "block_start",
                "event_id": 1,
                "event_code": 110,
                "trigger_key": "block_start",
                "participant_id": "P001",
                "phone_elapsed_realtime_ms": 1000,
            },
            {
                "event_type": "tap",
                "event_id": 2,
                "event_code": 310,
                "trigger_key": "tap_response",
                "participant_id": "P001",
                "trial_uid": "trial-a",
                "phone_elapsed_realtime_ms": 3500,
            },
        ],
        "command_diary": [
            {"command": "start_experiment", "status": "applied"},
        ],
        "lsl_runtime_status": {
            "schema": "pps-android-lsl-runtime-status.v1",
            "native_transport_available": False,
            "current_android_source_behavior": "local_lsl_marker_mirror",
        },
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
    trigger_rows = list(csv.DictReader((artifact.parent / "trigger_codes.csv").open(encoding="utf-8")))
    assert [row["event_code"] for row in trigger_rows] == ["110", "310"]
    assert [row["trigger_key"] for row in trigger_rows] == ["block_start", "tap_response"]
    assert loaded["trigger_codes"] == [
        {
            "event_id": 1,
            "event_code": 110,
            "event_type": "block_start",
            "trigger_key": "block_start",
            "phone_elapsed_realtime_ms": 1000,
        },
        {
            "event_id": 2,
            "event_code": 310,
            "event_type": "tap",
            "trigger_key": "tap_response",
            "phone_elapsed_realtime_ms": 3500,
        },
    ]
    assert (artifact.parent / "command_diary.jsonl").read_text(encoding="utf-8").count("\n") == 1
    assert loaded["lsl_runtime_status"]["schema"] == "pps-android-lsl-runtime-status.v1"
    assert (artifact.parent / "lsl_runtime_status.json").is_file()
    assert loaded["package_manifest"]["filename"] == "run_package_manifest.json"
    assert loaded["reconstruction_artifact"]["filename"] == "reconstruction_contract.json"
    assert loaded["artifact_file_inventory_artifact"] == {
        "filename": "artifact_file_inventory.json",
        "csv_filename": "artifact_file_inventory.csv",
        "schema": "pps-android-phone-run-artifact-file-inventory.v1",
        "self_included": False,
        "generated_by": "pc_mobile_runtime_upload_mirror",
    }
    inventory = json.loads((artifact.parent / "artifact_file_inventory.json").read_text(encoding="utf-8"))
    assert inventory["schema"] == "pps-android-phone-run-artifact-file-inventory.v1"
    assert inventory["run_id"] == "run-001"
    assert inventory["package_id"] == mobile_package_id(package)
    assert inventory["self_included"] is False
    inventory_paths = {row["relative_path"] for row in inventory["files"]}
    assert {
        "completion.json",
        "run_package_manifest.json",
        "reconstruction_contract.json",
        "events.csv",
        "lsl_runtime_status.json",
        "lsl_marker_mirror.csv",
        "trigger_codes.csv",
        "command_diary.jsonl",
    }.issubset(inventory_paths)
    assert "artifact_file_inventory.json" not in inventory_paths
    assert "artifact_file_inventory.csv" not in inventory_paths
    completion_row = next(row for row in inventory["files"] if row["relative_path"] == "completion.json")
    assert completion_row["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
    inventory_csv_rows = list(csv.DictReader((artifact.parent / "artifact_file_inventory.csv").open(encoding="utf-8")))
    assert {row["relative_path"] for row in inventory_csv_rows} == inventory_paths


def test_mobile_runtime_completion_upload_mirrors_phone_owned_response_export(tmp_path):
    package = _package(tmp_path)
    output_root = tmp_path / "output"
    manifest = build_mobile_package_manifest(package)
    building_block_asset_id = manifest["blocks"][0]["trials"][0]["building_block_asset_id"]
    response_ledger = [
        {
            "schema": "pps-android-phone-response-ledger.v1",
            "ledger_role": "source_trial",
            "block_id": "block-01",
            "block_index": 1,
            "trial_number": 1,
            "trial_uid": "trial-a",
            "cue_id": 1,
            "scheduled_block_time_ms": 3250,
            "response_window_start_ms": 3350,
            "response_window_end_ms": 4550,
            "hit": True,
            "status": "hit",
            "rt_ms": 250,
            "tap_event_id": 2,
            "building_block_asset_id": building_block_asset_id,
            "topup_eligible": False,
            "topup_attempted": False,
            "topup_trial_uid": "",
            "topup_hit": "",
            "topup_rt_ms": "",
            "topup_tap_event_id": "",
        }
    ]
    payload = {
        "package_id": mobile_package_id(package),
        "participant_metadata": {"participant_id": "P001", "age_years": "30"},
        "events": [
            {"type": "run_complete", "completion_reason": "completed"},
        ],
        "lsl_runtime_status": {
            "schema": "pps-android-lsl-runtime-status.v1",
            "native_transport_available": False,
            "current_android_source_behavior": "local_lsl_marker_mirror",
        },
        "phone_response_summary": {
            "schema": "pps-android-phone-response-summary.v1",
            "response_policy": "first_touch_100_1300_ms_after_tactile",
            "eligible_trial_count": 1,
            "ledger_row_count": 1,
            "hit_count": 1,
            "missed_needs_topup_count": 0,
            "topup_rescue_count": 0,
            "topup_attempted_count": 0,
            "topup_hit_count": 0,
            "topup_miss_count": 0,
            "final_rescued_hit_count": 0,
            "final_unresolved_miss_count": 0,
        },
        "phone_response_ledger": response_ledger,
        "phone_topup_plan": {
            "schema": "pps-android-phone-topup-plan.v1",
            "status": "not_needed",
            "synthesis_strategy": "pcm_wav_concat_without_ffmpeg",
            "response_min_rt_ms": 100,
            "response_max_rt_ms": 1300,
            "missed_trial_count": 0,
            "topup_trial_count": 0,
            "topup_attempted_count": 0,
            "topup_hit_count": 0,
            "final_unresolved_miss_count": 0,
            "trials": [],
        },
        "phone_topup_materialization": {
            "schema": "pps-android-phone-topup-materialization.v1",
            "status": "not_needed",
            "synthesis_strategy": "pcm_wav_concat_without_ffmpeg",
            "reason": "no_phone_topup_trials",
        },
    }

    result = write_mobile_runtime_events(
        package,
        output_root=output_root,
        run_id="phone-run-001",
        payload=payload,
        complete=True,
    )

    artifact = Path(result["artifact_path"])
    run_dir = artifact.parent
    loaded = json.loads(artifact.read_text(encoding="utf-8"))
    assert loaded["phone_response_summary"]["ledger_row_count"] == 1
    assert loaded["phone_response_ledger"][0]["trial_uid"] == "trial-a"
    assert (run_dir / "phone_response_ledger.csv").is_file()
    assert (run_dir / "phone_topup_plan.json").is_file()
    assert (run_dir / "phone_topup_materialization.json").is_file()

    export = json.loads((run_dir / "phone_owned_data_export.json").read_text(encoding="utf-8"))
    assert export["schema"] == "pps-android-phone-owned-data-export.v1"
    assert export["pc_upload_mirror"] is True
    data_min_rows = list(csv.DictReader(Path(export["data_min_participant_csv"]).open(encoding="utf-8")))
    assert len(data_min_rows) == 1
    assert data_min_rows[0]["participant_id"] == "P001"
    assert data_min_rows[0]["trial_uid"] == "trial-a"
    assert data_min_rows[0]["phase"] == "Inhale"
    assert data_min_rows[0]["response_given"] == "true"
    assert data_min_rows[0]["hit_miss"] == "Hit"
    master_rows = list(csv.DictReader(Path(export["data_min_master_successful_participants_csv"]).open(encoding="utf-8")))
    assert [row["trial_uid"] for row in master_rows] == ["trial-a"]
    data_max_run_dir = Path(export["data_max_run_dir"])
    assert (data_max_run_dir / "completion.json").is_file()
    assert (data_max_run_dir / "phone_owned_data_export.json").is_file()
    assert (data_max_run_dir / "artifact_file_inventory.json").is_file()
    assert (data_max_run_dir / "artifact_file_inventory.csv").is_file()
    inventory = json.loads((run_dir / "artifact_file_inventory.json").read_text(encoding="utf-8"))
    inventory_paths = {row["relative_path"] for row in inventory["files"]}
    assert "phone_owned_data_export.json" in inventory_paths
    assert "run_package_manifest.json" in inventory_paths
    assert "reconstruction_contract.json" in inventory_paths
