from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path


SCRIPT_PATH = Path("validation_protocols/scripts/validate_android_lsl_runtime_artifact.py")
spec = importlib.util.spec_from_file_location("validate_android_lsl_runtime_artifact", SCRIPT_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def test_android_lsl_runtime_validator_accepts_current_non_native_status(tmp_path: Path):
    status = _status(native=False)
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(json.dumps({"lsl_runtime_status": status}), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is True
    assert result.failures == []
    assert result.status["current_android_source_behavior"] == "local_lsl_marker_mirror"


def test_android_lsl_runtime_validator_fails_when_native_expected_but_missing(tmp_path: Path):
    status_path = tmp_path / "lsl_runtime_status.json"
    status_path.write_text(json.dumps(_status(native=False)), encoding="utf-8")

    result = validator.validate_run_artifact(status_path, expect_native_transport=True)

    assert result.ok is False
    assert "native Android LSL transport was expected" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_command_channel_drift(tmp_path: Path):
    status = _status(native=False)
    status["command_protocol"]["command_channels"] = ["schema", "command_id"]
    status_path = tmp_path / "lsl_runtime_status.json"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(status_path)

    assert result.ok is False
    assert "command channel order" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_requires_command_transport_in_strict_mode(tmp_path: Path):
    status = _status(native=True)
    status["native_bridge"]["command_transport"]["enabled"] = False
    status_path = tmp_path / "lsl_runtime_status.json"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(status_path, expect_native_transport=True)

    assert result.ok is False
    assert "command_transport is not enabled" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_phone_run_catalog_entry(tmp_path: Path):
    status = _status(native=False)
    status.update(_catalog_identity())
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(json.dumps({"lsl_runtime_status": status}), encoding="utf-8")
    (run_dir / "phone_run_catalog_entry.json").write_text(json.dumps(_catalog_entry(native=False)), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_run_catalog=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_can_require_phone_run_catalog_entry(tmp_path: Path):
    status = _status(native=False)
    status.update(_catalog_identity())
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_run_catalog=True)

    assert result.ok is False
    assert "phone run catalog entry is missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_phone_run_catalog_identity_drift(tmp_path: Path):
    status = _status(native=False)
    status.update(_catalog_identity())
    catalog = _catalog_entry(native=False)
    catalog["part_session_id"] = "other-part"
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "phone_run_catalog_entry.json").write_text(json.dumps(catalog), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "part_session_id differs" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_loads_phone_run_catalog_from_zip(tmp_path: Path):
    status = _status(native=True)
    status.update(_catalog_identity())
    archive_path = tmp_path / "phone-run.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("phone-run/lsl_runtime_status.json", json.dumps(status))
        archive.writestr("phone-run/phone_run_catalog_entry.json", json.dumps(_catalog_entry(native=True)))

    result = validator.validate_run_artifact(archive_path, expect_native_transport=True, expect_run_catalog=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_lightweight_materialization_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_lightweight_materializations=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_rejects_asset_strategy_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    manifest_path = run_dir / "run_package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["asset_strategy"] = "prepared_block_wavs_plus_trial_building_blocks"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "asset_strategy differs across phone run artifacts" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_requires_status_strategy_for_strict_lightweight_runs(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    status_path = run_dir / "lsl_runtime_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status.pop("asset_strategy")
    status_path.write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_lightweight_materializations=True)

    assert result.ok is False
    assert "lsl_runtime_status.asset_strategy is missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_missing_lightweight_materialization_event(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir, include_materialization_event=False)

    result = validator.validate_run_artifact(run_dir, expect_lightweight_materializations=True)

    assert result.ok is False
    assert "missing phone_scheduled_block_materialization event" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_phone_marker_mirror_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    marker_path = run_dir / "lsl_marker_mirror.csv"
    rows = _read_csv_rows(marker_path)
    rows[0]["event_type"] = "wrong_event"
    _write_marker_csv(marker_path, rows)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "payload type differs from marker event_type" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_participant_metadata_privacy_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    metadata_path = run_dir / "participant_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["stream_privacy"] = "discoverable_stream_name"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "stream_privacy" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_invalid_haptic_capability(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    haptic_path = run_dir / "haptic_capability.json"
    haptic = json.loads(haptic_path.read_text(encoding="utf-8"))
    haptic["recommended_amplitude"] = 999
    haptic_path.write_text(json.dumps(haptic), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "recommended_amplitude" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_loads_lightweight_materialization_from_zip(tmp_path: Path):
    source_dir = tmp_path / "phone-run-source"
    source_dir.mkdir()
    _write_lightweight_phone_run(source_dir)
    archive_path = tmp_path / "phone-run.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, f"phone-run/{path.relative_to(source_dir).as_posix()}")

    result = validator.validate_run_artifact(archive_path, expect_lightweight_materializations=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_controller_outbox_artifact(tmp_path: Path):
    controller_dir = tmp_path / "phone-controller"
    controller_dir.mkdir()
    (controller_dir / "phone_controller_runtime_status.json").write_text(json.dumps(_controller_status(native=False)), encoding="utf-8")
    (controller_dir / "phone_controller_command_outbox.jsonl").write_text(
        json.dumps(_controller_row(native_sent=False, ack_received=False)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(controller_dir)

    assert result.ok is True
    assert result.failures == []
    assert result.status["role"] == "controller"


def test_android_lsl_runtime_validator_requires_native_controller_send_in_strict_mode(tmp_path: Path):
    controller_dir = tmp_path / "phone-controller"
    controller_dir.mkdir()
    (controller_dir / "phone_controller_runtime_status.json").write_text(json.dumps(_controller_status(native=True)), encoding="utf-8")
    (controller_dir / "phone_controller_command_outbox.jsonl").write_text(
        json.dumps(_controller_row(native_sent=False, ack_received=False)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(controller_dir, expect_native_transport=True)

    assert result.ok is False
    assert "expected to send over native LSL" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_can_require_controller_acks(tmp_path: Path):
    controller_dir = tmp_path / "phone-controller"
    controller_dir.mkdir()
    (controller_dir / "phone_controller_runtime_status.json").write_text(json.dumps(_controller_status(native=True)), encoding="utf-8")
    (controller_dir / "phone_controller_command_outbox.jsonl").write_text(
        json.dumps(_controller_row(native_sent=True, ack_received=False)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(controller_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "expected to receive a matching command ack" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_pc_admin_outbox_artifact(tmp_path: Path):
    admin_dir = tmp_path / "pc-android-admin"
    admin_dir.mkdir()
    (admin_dir / "pc_android_lsl_admin_status.json").write_text(json.dumps(_pc_admin_status()), encoding="utf-8")
    (admin_dir / "pc_android_lsl_command_outbox.jsonl").write_text(
        json.dumps(_pc_admin_row(native_sent=True, ack_received=True)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(admin_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is True
    assert result.failures == []
    assert result.status["role"] == "pc_android_lsl_admin"


def test_android_lsl_runtime_validator_requires_pc_admin_rows_in_strict_mode(tmp_path: Path):
    status_path = tmp_path / "pc_android_lsl_admin_status.json"
    status_path.write_text(json.dumps(_pc_admin_status()), encoding="utf-8")

    result = validator.validate_run_artifact(status_path, expect_native_transport=True)

    assert result.ok is False
    assert "requires at least one command outbox row" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_requires_pc_admin_native_send_in_strict_mode(tmp_path: Path):
    admin_dir = tmp_path / "pc-android-admin"
    admin_dir.mkdir()
    (admin_dir / "pc_android_lsl_admin_status.json").write_text(json.dumps(_pc_admin_status()), encoding="utf-8")
    (admin_dir / "pc_android_lsl_command_outbox.jsonl").write_text(
        json.dumps(_pc_admin_row(native_sent=False, ack_received=False)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(admin_dir, expect_native_transport=True)

    assert result.ok is False
    assert "expected to send over native LSL" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_can_require_pc_admin_acks(tmp_path: Path):
    outbox_path = tmp_path / "pc_android_lsl_command_outbox.jsonl"
    (tmp_path / "pc_android_lsl_admin_status.json").write_text(json.dumps(_pc_admin_status()), encoding="utf-8")
    outbox_path.write_text(
        json.dumps(_pc_admin_row(native_sent=True, ack_received=False)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(outbox_path, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "expected to receive a matching command ack" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_phone_run_command_diary_ack_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_requires_phone_run_command_diary_when_acks_expected(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    status = _status(native=True)
    status.update(_catalog_identity())
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(json.dumps({"lsl_runtime_status": status}), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "requires command_diary rows" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_requires_phone_run_ack_sent_in_strict_mode(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir, ack_sent=False)

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "expected to send a PPSCommandAcksV1 sample" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_requires_phone_run_operator_command_event_for_ack_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir, include_operator_event=False)

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "requires matching operator_command events" in "\n".join(result.failures)


def _write_phone_run_with_native_command_diary(
    run_dir: Path,
    *,
    ack_sent: bool = True,
    include_operator_event: bool = True,
) -> None:
    status = _status(native=True)
    status.update(_catalog_identity())
    row = _phone_native_command_row(ack_sent=ack_sent)
    events = [_phone_event(1, "run_start")]
    if include_operator_event:
        events.append(
            _phone_event(
                2,
                "operator_command",
                command_id=row["command_id"],
                command_source="native_lsl",
                sender_id=row["sender_id"],
                command=row["command"],
                status=row["status"],
                reason=row["reason"],
                ack_sent=row["ack_sent"],
                payload=row["payload"],
            )
        )
    markers = [_phone_marker(event) for event in events]
    participant_metadata = _participant_metadata()
    haptic_capability = _haptic_capability()
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(
        json.dumps(
            {
                "lsl_runtime_status": status,
                "events": events,
                "lsl_marker_mirror": markers,
                "participant_metadata": participant_metadata,
                "haptic": haptic_capability,
                "command_diary": [row],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "participant_metadata.json").write_text(json.dumps(participant_metadata), encoding="utf-8")
    (run_dir / "haptic_capability.json").write_text(json.dumps(haptic_capability), encoding="utf-8")
    (run_dir / "command_diary.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", markers)


def _phone_native_command_row(*, ack_sent: bool = True) -> dict:
    ack_sample = [
        "pps-lsl-command-ack.v1",
        "cmd-phone-001",
        "part-001",
        "android_phone",
        "applied",
        "phone_playback_paused",
        "42.010000000",
        "42.020000000",
        "42.030000000",
        json.dumps({"command": "pause", "state_changed": True}),
    ]
    return {
        "schema": "pps-android-command-diary.v1",
        "command_id": "cmd-phone-001",
        "command_source": "native_lsl",
        "sender_id": "pc_runner",
        "session_id": "part-001",
        "command": "pause",
        "status": "applied",
        "reason": "phone_playback_paused",
        "payload": {"command": "pause", "state_changed": True},
        "package_id": "pkg-001",
        "run_id": "phone-run-001",
        "received_lsl_time": 42.01,
        "applied_lsl_time": 42.02,
        "ack_lsl_time": 42.03,
        "ack_sent": ack_sent,
        "ack_channels": [
            "schema",
            "command_id",
            "session_id",
            "receiver_id",
            "status",
            "reason",
            "received_lsl_time",
            "applied_lsl_time",
            "ack_lsl_time",
            "payload_json",
        ],
        "ack_sample": ack_sample,
        "phone_unix_ms": 1780000000000,
        "phone_elapsed_realtime_ms": 123456,
    }


PHONE_EVENT_CODES = {
    "session_metadata": 8,
    "run_start": 1,
    "run_complete": 2,
    "block_start": 10,
    "block_complete": 11,
    "vibration_cue": 21,
    "tap": 30,
    "phone_scheduled_block_materialization": 34,
    "phone_topup_materialization": 35,
    "operator_command": 41,
    "phone_playback_pause": 42,
    "phone_playback_resume": 43,
    "phone_stop_after_block_request": 44,
    "phone_stop_after_block_boundary": 45,
}


def _phone_event(event_id: int, event_type: str, **extra: object) -> dict:
    event = {
        "type": event_type,
        "event_id": event_id,
        "package_id": "pkg-001",
        "run_id": "phone-run-001",
        "phone_unix_ms": 1780000000000 + event_id,
        "phone_elapsed_realtime_ms": 123456 + event_id,
    }
    event.update(extra)
    return event


def _phone_marker(event: dict) -> dict:
    event_type = str(event.get("type") or "")
    event_id = int(event.get("event_id") or 0)
    block_index = str(event.get("block_index") or event.get("block_id") or "")
    trial_uid = str(event.get("trial_uid") or "")
    return {
        "marker_version": "2.0",
        "event_id": event_id,
        "event_type": event_type,
        "event_code": PHONE_EVENT_CODES.get(event_type, 500),
        "trigger_key": f"trial:{trial_uid}:{event_type}" if trial_uid else (f"block:{block_index}:{event_type}" if block_index else f"control:{event_type}"),
        "marker_name": f"P001_{block_index or 'blockXX'}_{trial_uid}_{event_type}".replace("__", "_").strip("_"),
        "session_id": "session-001",
        "participant_id": "P001",
        "session_group_id": "group-001",
        "part_session_id": "part-001",
        "part_number": "01",
        "block_index": block_index,
        "trial_uid": trial_uid,
        "timestamp_quality": "android_elapsed_realtime",
        "phone_unix_ms": event.get("phone_unix_ms"),
        "phone_elapsed_realtime_ms": event.get("phone_elapsed_realtime_ms"),
        "payload_json": json.dumps(event, sort_keys=True),
    }


def _write_marker_csv(path: Path, rows: list[dict]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _participant_metadata() -> dict:
    return {
        "schema": "pps-android-phone-participant-metadata.v1",
        "participant_id": "P001",
        "session_id": "session-001",
        "session_group_id": "group-001",
        "part_session_id": "part-001",
        "part_number": "01",
        "age_years": "30",
        "handedness": "right",
        "gender": "prefer_not_to_say",
        "tactile_threshold_percent": "20",
        "tactile_threshold_source": "android_haptic_calibration",
        "stream_privacy": "metadata_payload_only",
        "tactile_threshold_calibration_schema": "pps-android-phone-haptic-calibration.v1",
        "tactile_threshold_calibration_status": "threshold_detected",
    }


def _haptic_capability() -> dict:
    calibration = {
        "schema": "pps-android-phone-haptic-calibration.v1",
        "status": "threshold_detected",
        "calibration_policy": "ascending_detection_threshold_percent",
        "has_vibrator": True,
        "has_amplitude_control": True,
        "recommended_threshold_percent": 20,
        "recommended_amplitude": 51,
        "responses": [
            {"trial_index": 1, "threshold_percent": 5, "amplitude": 13, "felt": False},
            {"trial_index": 2, "threshold_percent": 20, "amplitude": 51, "felt": True},
        ],
    }
    return {
        "schema": "pps-android-haptic-capability.v1",
        "has_vibrator": True,
        "has_amplitude_control": True,
        "calibration_policy": "amplitude_percent_supported",
        "device_model": "test-phone",
        "android_sdk": 30,
        "calibration_result": calibration,
        "calibration_status": "threshold_detected",
        "recommended_threshold_percent": 20,
        "recommended_amplitude": 51,
    }


def _write_lightweight_phone_run(run_dir: Path, *, include_materialization_event: bool = True) -> None:
    status = _status(native=False)
    status["asset_strategy"] = "trial_building_blocks_only"
    wav_bytes = b"RIFF....WAVE"
    wav_sha256 = hashlib.sha256(wav_bytes).hexdigest()
    materialization = {
        "schema": "pps-android-phone-scheduled-block-materialization.v1",
        "status": "materialized",
        "synthesis_strategy": "pcm_wav_concat_without_ffmpeg",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "source_block_id": "block-01",
        "source_block_index": 1,
        "source_block_label": "Block 01",
        "wav_filename": "phone_materialized_block_01.wav",
        "wav_sha256": wav_sha256,
        "sample_rate_hz": 44100,
        "channel_count": 2,
        "bits_per_sample": 16,
        "encoding": "PCM_16",
        "frame_count": 44100,
        "duration_ms": 1000,
        "trial_count": 1,
        "tactile_cue_count": 1,
    }
    package_manifest = {
        "schema": "pps-mobile-run-package.v2",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "asset_strategy": "trial_building_blocks_only",
        "assets": [
            {
                "asset_id": "trial-asset-001",
                "role": "trial_building_block",
                "filename": "trial.wav",
                "available": True,
                "size_bytes": 12,
                "sha256": "source-sha",
            }
        ],
        "blocks": [
            {
                "block_id": "block-01",
                "index": 1,
                "label": "Block 01",
                "trial_count": 1,
                "audio_asset_id": "block-01-audio",
                "trials": [{"trial_uid": "trial-001", "building_block_asset_id": "trial-asset-001"}],
            }
        ],
        "reconstruction": {"package_asset_strategy": "trial_building_blocks_only"},
    }
    reconstruction_artifact = {
        "schema": "pps-mobile-phone-run-reconstruction.v1",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "asset_strategy": "trial_building_blocks_only",
        "reconstruction": {
            "package_asset_strategy": "trial_building_blocks_only",
            "schedule_hash": "schedulehash",
            "building_block_count": 1,
            "block_count": 1,
            "trial_count": 1,
        },
    }
    events = [_phone_event(1, "run_start")]
    if include_materialization_event:
        events.append(_phone_event(2, "phone_scheduled_block_materialization", **materialization))
    markers = [_phone_marker(event) for event in events]
    participant_metadata = _participant_metadata()
    haptic_capability = _haptic_capability()
    materialized_dir = run_dir / "materialized_blocks"
    materialized_dir.mkdir()
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "run_package_manifest.json").write_text(json.dumps(package_manifest), encoding="utf-8")
    (run_dir / "reconstruction_contract.json").write_text(json.dumps(reconstruction_artifact), encoding="utf-8")
    (run_dir / "completion.json").write_text(
        json.dumps(
            {
                "lsl_runtime_status": status,
                "package": {"asset_strategy": "trial_building_blocks_only"},
                "events": events,
                "lsl_marker_mirror": markers,
                "participant_metadata": participant_metadata,
                "haptic": haptic_capability,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "participant_metadata.json").write_text(json.dumps(participant_metadata), encoding="utf-8")
    (run_dir / "haptic_capability.json").write_text(json.dumps(haptic_capability), encoding="utf-8")
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", markers)
    (materialized_dir / "phone_materialized_block_01.json").write_text(json.dumps(materialization), encoding="utf-8")
    (materialized_dir / "phone_materialized_block_01.wav").write_bytes(wav_bytes)


def _status(*, native: bool) -> dict:
    return {
        "schema": "pps-android-lsl-runtime-status.v1",
        "native_transport_available": native,
        "native_marker_transport_enabled": native,
        "command_receiver_available": native,
        "current_android_source_behavior": "native_lsl" if native else "local_lsl_marker_mirror",
        "reason": "" if native else "native_liblsl_android_layer_not_present",
        "streams": {
            "rich_markers": "PPSMarkersV2",
            "numeric_triggers": "PPSTriggerCodes",
            "command_signals": "PPSCommandSignalsV1",
            "command_acks": "PPSCommandAcksV1",
        },
        "command_protocol": {
            "command_schema": "pps-lsl-command.v1",
            "ack_schema": "pps-lsl-command-ack.v1",
            "command_channels": [
                "schema",
                "command_id",
                "session_id",
                "sender_id",
                "command",
                "issued_lsl_time",
                "payload_json",
            ],
            "ack_channels": [
                "schema",
                "command_id",
                "session_id",
                "receiver_id",
                "status",
                "reason",
                "received_lsl_time",
                "applied_lsl_time",
                "ack_lsl_time",
                "payload_json",
            ],
            "supported_commands": ["start_experiment", "pause"],
            "token_required": True,
            "token_payload_fields": ["token", "companion_token"],
        },
        "native_bridge": {
            "bridge": {
                "schema": "pps-android-native-lsl-bridge-status.v1",
                "available": native,
                "enabled": False,
                "backend": "liblsl-android-reflection",
                "reason": "" if native else "native_liblsl_android_layer_not_present",
            },
            "marker_transport": {
                "schema": "pps-android-native-lsl-bridge-status.v1",
                "available": native,
                "enabled": native,
                "backend": "liblsl-android-reflection",
                "reason": "" if native else "native_liblsl_android_layer_not_present",
            },
            "command_transport": {
                "schema": "pps-android-native-lsl-bridge-status.v1",
                "available": native,
                "enabled": native,
                "backend": "liblsl-android-reflection",
                "reason": "" if native else "native_liblsl_android_layer_not_present",
            },
        },
        "privacy": {
            "default": "metadata_payload_only",
            "participant_demographics_location": "metadata_and_payload_artifacts",
            "demographics_in_stream_name": False,
        },
    }


def _catalog_identity() -> dict:
    return {
        "package_id": "pkg-001",
        "run_id": "phone-run-001",
        "participant_id": "P001",
        "session_id": "session-001",
        "session_group_id": "group-001",
        "part_session_id": "part-001",
        "part_number": "01",
    }


def _catalog_entry(*, native: bool) -> dict:
    return {
        "schema": "pps-android-phone-run-catalog-entry.v1",
        **_catalog_identity(),
        "completed": True,
        "completion_reason": "completed",
        "artifact_file": "completion.json",
        "native_lsl_transport_available": native,
        "native_lsl_marker_transport_enabled": native,
        "native_lsl_command_receiver_available": native,
        "participant_metadata_summary": {
            "participant_id": "P001",
            "age_years": "30",
            "handedness": "right",
            "gender": "prefer_not_to_say",
        },
        "privacy": {
            "scope": "app_private_local_catalog",
            "demographics_in_stream_name": False,
        },
        "reconstruction": {
            "schedule_hash": "schedulehash",
            "building_block_count": 6,
            "block_count": 6,
            "trial_count": 180,
        },
    }


def _controller_status(*, native: bool) -> dict:
    return {
        "schema": "pps-android-controller-runtime-status.v1",
        "session_id": "session-001",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "role": "controller",
        "native_transport": "liblsl",
        "native_transport_available": native,
        "native_controller_transport_enabled": native,
        "current_android_source_behavior": "native_lsl_controller_with_local_outbox" if native else "local_controller_outbox_only",
        "reason": "" if native else "liblsl_android_class_unavailable",
        "native_bridge": {
            "bridge": {
                "schema": "pps-android-native-lsl-bridge-status.v1",
                "available": native,
                "enabled": False,
                "backend": "liblsl-android-reflection",
                "reason": "" if native else "liblsl_android_class_unavailable",
            },
            "marker_transport": None,
            "command_transport": None,
            "controller_transport": {
                "schema": "pps-android-native-lsl-bridge-status.v1",
                "available": native,
                "enabled": native,
                "backend": "liblsl-android-reflection",
                "reason": "" if native else "liblsl_android_class_unavailable",
            },
        },
        "streams": {
            "command_signals": "PPSCommandSignalsV1",
            "command_acks": "PPSCommandAcksV1",
        },
        "command_protocol": {
            "command_schema": "pps-lsl-command.v1",
            "ack_schema": "pps-lsl-command-ack.v1",
            "command_channels": [
                "schema",
                "command_id",
                "session_id",
                "sender_id",
                "command",
                "issued_lsl_time",
                "payload_json",
            ],
            "ack_channels": [
                "schema",
                "command_id",
                "session_id",
                "receiver_id",
                "status",
                "reason",
                "received_lsl_time",
                "applied_lsl_time",
                "ack_lsl_time",
                "payload_json",
            ],
            "supported_commands": ["start_experiment", "pause", "resume"],
            "token_required": True,
        },
    }


def _controller_row(*, native_sent: bool, ack_received: bool) -> dict:
    command_id = "cmd-controller-001"
    command_sample = [
        "pps-lsl-command.v1",
        command_id,
        "part-001",
        "android_controller",
        "pause",
        "42.000000000",
        json.dumps({"token": "secret", "package_id": "pkg-001"}),
    ]
    row = {
        "schema": "pps-android-controller-command-row.v1",
        "command_id": command_id,
        "command": "pause",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "target_session_id": "part-001",
        "native_transport_available": native_sent,
        "native_controller_transport_enabled": native_sent,
        "native_lsl_sent": native_sent,
        "current_android_source_behavior": "native_lsl_controller_with_local_outbox" if native_sent else "local_controller_outbox_only",
        "command_channels": [
            "schema",
            "command_id",
            "session_id",
            "sender_id",
            "command",
            "issued_lsl_time",
            "payload_json",
        ],
        "command_sample": command_sample,
        "payload": {"token": "secret", "package_id": "pkg-001"},
        "ack_received": ack_received,
    }
    if ack_received:
        row["ack_sample"] = [
            "pps-lsl-command-ack.v1",
            command_id,
            "part-001",
            "android_phone",
            "applied",
            "",
            "42.010000000",
            "42.020000000",
            "42.030000000",
            json.dumps({"command": "pause"}),
        ]
    return row


def _pc_admin_status() -> dict:
    return {
        "schema": "pps-pc-android-lsl-admin-status.v1",
        "role": "pc_android_lsl_admin",
        "native_transport": "liblsl",
        "current_pc_source_behavior": "pc_native_lsl_admin_with_local_outbox",
        "streams": {
            "command_signals": "PPSCommandSignalsV1",
            "command_acks": "PPSCommandAcksV1",
        },
        "command_protocol": {
            "command_schema": "pps-lsl-command.v1",
            "ack_schema": "pps-lsl-command-ack.v1",
            "command_channels": [
                "schema",
                "command_id",
                "session_id",
                "sender_id",
                "command",
                "issued_lsl_time",
                "payload_json",
            ],
            "ack_channels": [
                "schema",
                "command_id",
                "session_id",
                "receiver_id",
                "status",
                "reason",
                "received_lsl_time",
                "applied_lsl_time",
                "ack_lsl_time",
                "payload_json",
            ],
            "supported_commands": ["start_experiment", "pause", "resume"],
            "token_required": True,
            "token_payload_fields": ["token", "companion_token"],
        },
    }


def _pc_admin_row(*, native_sent: bool, ack_received: bool) -> dict:
    command_id = "cmd-pc-admin-001"
    command_sample = [
        "pps-lsl-command.v1",
        command_id,
        "part-001",
        "pc_runner",
        "pause",
        "42.000000000",
        json.dumps({"token": "secret", "package_id": "pkg-001", "requested_by": "pc_runner_lsl_admin"}),
    ]
    row = {
        "schema": "pps-pc-android-lsl-admin-command-row.v1",
        "ok": bool(native_sent and ack_received),
        "status": "ack_applied" if ack_received else ("sent_no_ack" if native_sent else "send_failed"),
        "reason": "",
        "command_id": command_id,
        "command": "pause",
        "target_session_id": "part-001",
        "sender_id": "pc_runner",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "native_transport": "liblsl",
        "command_stream": "PPSCommandSignalsV1",
        "ack_stream": "PPSCommandAcksV1",
        "consumer_ready": native_sent,
        "native_lsl_sent": native_sent,
        "ack_required": ack_received,
        "ack_received": ack_received,
        "ack_status": "applied" if ack_received else "",
        "command_channels": [
            "schema",
            "command_id",
            "session_id",
            "sender_id",
            "command",
            "issued_lsl_time",
            "payload_json",
        ],
        "ack_channels": [
            "schema",
            "command_id",
            "session_id",
            "receiver_id",
            "status",
            "reason",
            "received_lsl_time",
            "applied_lsl_time",
            "ack_lsl_time",
            "payload_json",
        ],
        "command_sample": command_sample,
        "ack_sample": [],
        "payload": {"token": "secret", "package_id": "pkg-001", "requested_by": "pc_runner_lsl_admin"},
    }
    if ack_received:
        row["ack_sample"] = [
            "pps-lsl-command-ack.v1",
            command_id,
            "part-001",
            "android_phone",
            "applied",
            "",
            "42.010000000",
            "42.020000000",
            "42.030000000",
            json.dumps({"command": "pause"}),
        ]
    return row
