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


def test_android_lsl_runtime_validator_requires_stream_descriptions_in_strict_mode(tmp_path: Path):
    status = _status(native=True)
    status.pop("stream_descriptions")
    status_path = tmp_path / "lsl_runtime_status.json"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(status_path, expect_native_transport=True)

    assert result.ok is False
    assert "Android LSL stream descriptions are missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_stream_description_drift(tmp_path: Path):
    status = _status(native=True)
    status["stream_descriptions"]["rich_markers"]["channel_labels"] = ["marker_version"]
    status_path = tmp_path / "lsl_runtime_status.json"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(status_path, expect_native_transport=True)

    assert result.ok is False
    assert "rich_markers.channel_labels" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_requires_command_transport_in_strict_mode(tmp_path: Path):
    status = _status(native=True)
    status["native_bridge"]["command_transport"]["enabled"] = False
    status_path = tmp_path / "lsl_runtime_status.json"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(status_path, expect_native_transport=True)

    assert result.ok is False
    assert "command_transport is not enabled" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_native_marker_push_completeness(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir, native=True)

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_rejects_native_marker_push_count_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir, native=True)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["summary"]["native_lsl_pushed_count"] = 1
    completion["summary"]["native_lsl_failed_count"] = 2
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True)

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "completion summary native_lsl_pushed_count expected" in failures
    assert "completion summary native_lsl_failed_count expected 0, got 2" in failures


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
    catalog = _catalog_entry(native=True)
    archive_path = tmp_path / "phone-run.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("phone-run/lsl_runtime_status.json", json.dumps(status))
        archive.writestr("phone-run/phone_run_catalog_entry.json", json.dumps(catalog))
        _write_phone_run_catalog_to_zip(archive, catalog)

    result = validator.validate_run_artifact(
        archive_path,
        expect_native_transport=True,
        expect_run_catalog=True,
        expect_run_catalog_index=True,
    )

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_phone_run_catalog_index(tmp_path: Path):
    files_dir = tmp_path / "files"
    run_dir = files_dir / "phone_runs" / "phone-run-001"
    run_dir.mkdir(parents=True)
    status = _status(native=False)
    status.update(_catalog_identity())
    catalog = _catalog_entry(native=False)
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(json.dumps({"lsl_runtime_status": status}), encoding="utf-8")
    (run_dir / "phone_run_catalog_entry.json").write_text(json.dumps(catalog), encoding="utf-8")
    _write_phone_run_catalog_root(files_dir, catalog)

    result = validator.validate_run_artifact(
        run_dir,
        expect_run_catalog=True,
        expect_run_catalog_index=True,
    )

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_rejects_missing_phone_run_catalog_index_when_expected(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    status = _status(native=False)
    status.update(_catalog_identity())
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "phone_run_catalog_entry.json").write_text(json.dumps(_catalog_entry(native=False)), encoding="utf-8")

    result = validator.validate_run_artifact(
        run_dir,
        expect_run_catalog=True,
        expect_run_catalog_index=True,
    )

    assert result.ok is False
    assert "phone run catalog index is missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_catalog_runs_missing_current_run(tmp_path: Path):
    files_dir = tmp_path / "files"
    run_dir = files_dir / "phone_runs" / "phone-run-001"
    run_dir.mkdir(parents=True)
    status = _status(native=False)
    status.update(_catalog_identity())
    catalog = _catalog_entry(native=False)
    other_catalog = {**catalog, "run_id": "phone-run-other"}
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "phone_run_catalog_entry.json").write_text(json.dumps(catalog), encoding="utf-8")
    _write_phone_run_catalog_root(files_dir, other_catalog)

    result = validator.validate_run_artifact(
        run_dir,
        expect_run_catalog=True,
        expect_run_catalog_index=True,
    )

    assert result.ok is False
    assert "phone run catalog runs.jsonl is missing run_id phone-run-001" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_lightweight_materialization_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_lightweight_materializations=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_phone_run_provenance_consistency(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _inject_phone_run_provenance(run_dir)

    result = validator.validate_run_artifact(
        run_dir,
        expect_lightweight_materializations=True,
        expect_run_catalog=True,
    )

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_rejects_session_metadata_provenance_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _inject_phone_run_provenance(run_dir, session_seed="wrong-seed")

    result = validator.validate_run_artifact(run_dir, expect_run_catalog=True)

    assert result.ok is False
    assert "session_metadata package randomization_seed differs from run_package_manifest" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_phone_run_provenance_source_hash_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    bad_reconstruction_hashes = _phone_run_source_hash_summary(
        _phone_run_source_segment_hashes(source_segment5_hash="wrong-segment5hash")
    )
    bad_catalog_hashes = _phone_run_source_hash_summary(
        _phone_run_source_segment_hashes(order_hash="wrong-orderhash")
    )
    _inject_phone_run_provenance(
        run_dir,
        reconstruction_source_hashes=bad_reconstruction_hashes,
        catalog_source_hashes=bad_catalog_hashes,
    )

    result = validator.validate_run_artifact(run_dir, expect_run_catalog=True)

    failures = "\n".join(result.failures)
    assert result.ok is False
    assert "reconstruction_contract source_segment_hashes differ from run_package_manifest" in failures
    assert "phone_run_catalog_entry source_segment_hashes differ from run_package_manifest" in failures


def test_android_lsl_runtime_validator_rejects_catalog_index_provenance_drift(tmp_path: Path):
    files_dir = tmp_path / "files"
    run_dir = files_dir / "phone_runs" / "phone-run-001"
    run_dir.mkdir(parents=True)
    _write_lightweight_phone_run(run_dir)
    _inject_phone_run_provenance(run_dir)
    catalog = json.loads((run_dir / "phone_run_catalog_entry.json").read_text(encoding="utf-8"))
    catalog["randomization_seed"] = "wrong-seed"
    _write_phone_run_catalog_root(files_dir, catalog)

    result = validator.validate_run_artifact(
        run_dir,
        expect_run_catalog=True,
        expect_run_catalog_index=True,
    )

    failures = "\n".join(result.failures)
    assert result.ok is False
    assert "phone run catalog runs.jsonl randomization_seed differs from phone_run_catalog_entry.json" in failures
    assert "phone run catalog latest_run.json randomization_seed differs from phone_run_catalog_entry.json" in failures


def test_android_lsl_runtime_validator_rejects_stream_description_metadata_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _inject_phone_run_provenance(run_dir)
    status_path = run_dir / "lsl_runtime_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    metadata = json.loads(status["stream_descriptions"]["rich_markers"]["session_metadata_json"])
    metadata["randomization_seed"] = "wrong-seed"
    status["stream_descriptions"]["rich_markers"]["session_metadata_json"] = json.dumps(metadata)
    status_path.write_text(json.dumps(status), encoding="utf-8")
    _update_completion_payload(run_dir, lsl_runtime_status=status)

    result = validator.validate_run_artifact(run_dir, expect_run_catalog=True)

    assert result.ok is False
    assert "Android LSL stream description rich_markers.session_metadata_json randomization_seed differs" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_stream_description_participant_summary_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    status_path = run_dir / "lsl_runtime_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    metadata = json.loads(status["stream_descriptions"]["rich_markers"]["session_metadata_json"])
    metadata["participant_metadata_summary"]["handedness"] = "left"
    status["stream_descriptions"]["rich_markers"]["session_metadata_json"] = json.dumps(metadata)
    status_path.write_text(json.dumps(status), encoding="utf-8")
    _update_completion_payload(run_dir, lsl_runtime_status=status)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "participant_metadata_summary handedness differs from participant_metadata" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_stream_description_haptic_summary_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    status_path = run_dir / "lsl_runtime_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    metadata = json.loads(status["stream_descriptions"]["numeric_triggers"]["session_metadata_json"])
    metadata["haptic_capability_summary"]["recommended_amplitude"] = 200
    status["stream_descriptions"]["numeric_triggers"]["session_metadata_json"] = json.dumps(metadata)
    status_path.write_text(json.dumps(status), encoding="utf-8")
    _update_completion_payload(run_dir, lsl_runtime_status=status)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "haptic_capability_summary recommended_amplitude differs from haptic_capability" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_session_metadata_marker_participant_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    marker_rows = _read_csv_rows(run_dir / "lsl_marker_mirror.csv")
    session_row = next(row for row in marker_rows if row["event_type"] == "session_metadata")
    payload = json.loads(session_row["payload_json"])
    payload["participant_metadata"]["handedness"] = "left"
    session_row["payload_json"] = json.dumps(payload)
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", marker_rows)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "session_metadata participant_metadata handedness differs from participant_metadata.json" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_session_metadata_marker_haptic_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    marker_rows = _read_csv_rows(run_dir / "lsl_marker_mirror.csv")
    session_row = next(row for row in marker_rows if row["event_type"] == "session_metadata")
    payload = json.loads(session_row["payload_json"])
    payload["haptic"]["calibration_result"]["responses"][1]["amplitude"] = 50
    session_row["payload_json"] = json.dumps(payload)
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", marker_rows)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "session_metadata haptic calibration_result differs from haptic_capability.json" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_accepts_phone_topup_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_phone_topup_evidence=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_audiotrack_timing_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_audiotrack_timing_evidence=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_phone_owned_data_export(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _write_phone_owned_data_export(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_phone_owned_data_export=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_requires_phone_owned_data_export_when_expected(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_phone_owned_data_export=True)

    assert result.ok is False
    assert "phone-owned data export is missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_artifact_file_inventory(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _write_artifact_file_inventory(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_artifact_inventory=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_rejects_artifact_file_inventory_hash_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _write_artifact_file_inventory(run_dir)
    (run_dir / "events.csv").write_text("tampered\n", encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_artifact_inventory=True)

    assert result.ok is False
    assert "sha256 mismatch for events.csv" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_requires_completion_artifact_inventory_advertisement(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _write_artifact_file_inventory(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion.pop("artifact_file_inventory_artifact")
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_artifact_inventory=True)

    assert result.ok is False
    assert "completion artifact_file_inventory_artifact is required" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_artifact_inventory_advertised_filename_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _write_artifact_file_inventory(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["artifact_file_inventory_artifact"]["csv_filename"] = "wrong_inventory.csv"
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_artifact_inventory=True)

    assert result.ok is False
    assert "artifact_file_inventory_artifact csv_filename must be artifact_file_inventory.csv" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_missing_artifact_inventory_csv_sidecar(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    _write_artifact_file_inventory(run_dir)
    (run_dir / "artifact_file_inventory.csv").unlink()

    result = validator.validate_run_artifact(run_dir, expect_artifact_inventory=True)

    assert result.ok is False
    assert "advertised CSV sidecar artifact_file_inventory.csv is missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_artifact_inventory_from_zip(tmp_path: Path):
    source_dir = tmp_path / "phone-run-source"
    source_dir.mkdir()
    _write_lightweight_phone_run(source_dir)
    _write_artifact_file_inventory(source_dir)
    archive_path = tmp_path / "phone-run.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, f"phone-run/{path.relative_to(source_dir).as_posix()}")

    result = validator.validate_run_artifact(archive_path, expect_artifact_inventory=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_phone_event_diary(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_event_diary=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_requires_phone_event_diary_when_expected(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    status = _status(native=False)
    status.update(_catalog_identity())
    events = [_phone_event(1, "run_start")]
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(
        json.dumps({"lsl_runtime_status": status, "events": events}),
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(run_dir, expect_event_diary=True)

    assert result.ok is False
    assert "phone event diary events.csv is missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_phone_event_diary_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    events_path = run_dir / "events.csv"
    rows = _read_csv_rows(events_path)
    rows[0]["type"] = "wrong_event"
    _write_marker_csv(events_path, rows)

    result = validator.validate_run_artifact(run_dir, expect_event_diary=True)

    assert result.ok is False
    assert "events.csv row 1 type differs from completion event" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_trigger_code_mirror(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_trigger_code_mirror=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_requires_trigger_code_mirror_when_expected(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    status = _status(native=False)
    status.update(_catalog_identity())
    events = [_phone_event(1, "run_start")]
    markers = [_phone_marker(event) for event in events]
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(
        json.dumps({"lsl_runtime_status": status, "events": events, "lsl_marker_mirror": markers}),
        encoding="utf-8",
    )
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", markers)

    result = validator.validate_run_artifact(run_dir, expect_trigger_code_mirror=True)

    assert result.ok is False
    assert "phone trigger-code mirror trigger_codes.csv is missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_trigger_code_mirror_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    trigger_path = run_dir / "trigger_codes.csv"
    rows = _read_csv_rows(trigger_path)
    rows[0]["event_code"] = "999"
    _write_marker_csv(trigger_path, rows)

    result = validator.validate_run_artifact(run_dir, expect_trigger_code_mirror=True)

    assert result.ok is False
    assert "trigger_codes.csv row 1 event_code differs from lsl_marker_mirror" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_audiotrack_strategy_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    block_start = next(event for event in completion["events"] if event["type"] == "block_start")
    block_start["audio_timing_strategy"] = "mediaplayer_wall_clock"
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_audiotrack_timing_evidence=True)

    assert result.ok is False
    assert "audio_timing_strategy must be audiotrack_pcm_wav_playback_head" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_missing_audiotrack_playback_start(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["events"] = [event for event in completion["events"] if event["type"] != "audio_playback_start"]
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_audiotrack_timing_evidence=True)

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "AudioTrack timing validation requires audio_playback_start events" in failures
    assert "missing audio_playback_start for block identities" in failures


def test_android_lsl_runtime_validator_rejects_audiotrack_cue_jitter_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    cue = next(event for event in completion["events"] if event["type"] == "vibration_cue")
    cue["audio_cue_jitter_frames"] = 999
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_audiotrack_timing_evidence=True)

    assert result.ok is False
    assert "audio_cue_jitter_frames differs" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_audiotrack_scheduled_frame_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    cue = next(event for event in completion["events"] if event["type"] == "vibration_cue")
    cue["scheduled_audio_frame"] = 123
    cue["audio_playback_head_frame"] = 133
    cue["audio_cue_jitter_frames"] = 10
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_audiotrack_timing_evidence=True)

    assert result.ok is False
    assert "scheduled_audio_frame differs from scheduled_block_time_ms" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_audiotrack_cue_frame_outside_block(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    cue = next(event for event in completion["events"] if event["type"] == "vibration_cue")
    cue["scheduled_block_time_ms"] = 1001
    cue["scheduled_audio_frame"] = 44145
    cue["audio_playback_head_frame"] = 44155
    cue["audio_cue_jitter_frames"] = 10
    cue["audio_cue_jitter_ms"] = 10 * 1000.0 / 44100
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_audiotrack_timing_evidence=True)

    assert result.ok is False
    assert "scheduled_audio_frame exceeds block audio_frame_count" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_phone_topup_wav_hash_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    (run_dir / "phone_topup_block.wav").write_bytes(b"RIFFchangedWAVE")

    result = validator.validate_run_artifact(run_dir, expect_phone_topup_evidence=True)

    assert result.ok is False
    assert "phone_topup_materialization wav_sha256 does not match" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_phone_response_ledger_sidecar_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    ledger_path = run_dir / "phone_response_ledger.csv"
    rows = _read_csv_rows(ledger_path)
    rows[0]["status"] = "missed_needs_topup"
    _write_marker_csv(ledger_path, rows)

    result = validator.validate_run_artifact(run_dir, expect_phone_topup_evidence=True)

    assert result.ok is False
    assert "phone_response_ledger.csv rows differ" in "\n".join(result.failures)


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


def test_android_lsl_runtime_validator_rejects_reconstruction_hierarchy_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    artifact_path = run_dir / "reconstruction_contract.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["reconstruction"]["study_hierarchy"] = ["study_profile", "phone_runtime_package"]
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_lightweight_materializations=True)

    assert result.ok is False
    assert "reconstruction_contract study_hierarchy" in "\n".join(result.failures)


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


def test_android_lsl_runtime_validator_rejects_lightweight_materialized_trial_sequence_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    artifact_path = run_dir / "materialized_blocks" / "phone_materialized_block_01.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["trials"][0]["building_block_asset_id"] = "wrong-trial-asset"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_lightweight_materializations=True)

    assert result.ok is False
    assert "building_block_asset_id differs from run package" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_lightweight_materialized_trial_number_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    artifact_path = run_dir / "materialized_blocks" / "phone_materialized_block_01.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    artifact["trials"][0]["trial_number"] = 0
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_lightweight_materializations=True)

    assert result.ok is False
    assert "trial_number is not sequential" in "\n".join(result.failures)


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


def test_android_lsl_runtime_validator_rejects_haptic_threshold_drift_from_participant_metadata(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    metadata_path = run_dir / "participant_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["tactile_threshold_percent"] = "30"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    _update_completion_payload(run_dir, participant_metadata=metadata)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "tactile_threshold_percent differs from haptic_capability recommended_threshold_percent" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_haptic_amplitude_mapping_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    haptic_path = run_dir / "haptic_capability.json"
    haptic = json.loads(haptic_path.read_text(encoding="utf-8"))
    haptic["recommended_amplitude"] = 52
    haptic["calibration_result"]["recommended_amplitude"] = 52
    haptic_path.write_text(json.dumps(haptic), encoding="utf-8")
    _update_completion_payload(run_dir, haptic=haptic)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "haptic_capability recommended_amplitude does not match tactile_threshold_percent" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_haptic_response_amplitude_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_lightweight_phone_run(run_dir)
    haptic_path = run_dir / "haptic_capability.json"
    haptic = json.loads(haptic_path.read_text(encoding="utf-8"))
    haptic["calibration_result"]["responses"][1]["amplitude"] = 50
    haptic_path.write_text(json.dumps(haptic), encoding="utf-8")
    _update_completion_payload(run_dir, haptic=haptic)

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "calibration_result response 2 amplitude does not match threshold_percent" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_loads_lightweight_materialization_from_zip(tmp_path: Path):
    source_dir = tmp_path / "phone-run-source"
    source_dir.mkdir()
    _write_lightweight_phone_run(source_dir)
    archive_path = tmp_path / "phone-run.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, f"phone-run/{path.relative_to(source_dir).as_posix()}")

    result = validator.validate_run_artifact(
        archive_path,
        expect_event_diary=True,
        expect_trigger_code_mirror=True,
        expect_lightweight_materializations=True,
    )

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_loads_phone_owned_data_export_from_zip(tmp_path: Path):
    source_dir = tmp_path / "phone-run-source"
    source_dir.mkdir()
    _write_lightweight_phone_run(source_dir)
    _write_phone_owned_data_export(source_dir)
    archive_path = tmp_path / "phone-run.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in source_dir.rglob("*"):
            if path.is_file():
                archive.write(path, f"phone-run/{path.relative_to(source_dir).as_posix()}")
        export_root = source_dir.parent / "phone_owned_exports"
        for path in export_root.rglob("*"):
            if path.is_file():
                archive.write(path, f"phone_owned_exports/{path.relative_to(export_root).as_posix()}")

    result = validator.validate_run_artifact(archive_path, expect_phone_owned_data_export=True)

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


def test_android_lsl_runtime_validator_requires_controller_stream_descriptions_in_strict_mode(tmp_path: Path):
    controller_dir = tmp_path / "phone-controller"
    controller_dir.mkdir()
    status = _controller_status(native=True)
    status.pop("stream_descriptions")
    (controller_dir / "phone_controller_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(controller_dir, expect_native_transport=True)

    assert result.ok is False
    assert "Android controller LSL stream descriptions are missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_controller_stream_description_drift(tmp_path: Path):
    controller_dir = tmp_path / "phone-controller"
    controller_dir.mkdir()
    status = _controller_status(native=True)
    status["stream_descriptions"]["command_signals"]["role"] = "inlet"
    (controller_dir / "phone_controller_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")

    result = validator.validate_run_artifact(controller_dir, expect_native_transport=True)

    assert result.ok is False
    assert "command_signals.role" in "\n".join(result.failures)


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


def test_android_lsl_runtime_validator_accepts_controller_operator_note_payload(tmp_path: Path):
    controller_dir = tmp_path / "phone-controller"
    controller_dir.mkdir()
    status = _controller_status(native=True)
    status["command_protocol"]["supported_commands"].append("operator_note")
    (controller_dir / "phone_controller_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    row = _controller_row(native_sent=True, ack_received=True)
    note_payload = {"token": "secret", "package_id": "pkg-001", "note": "participant asked for a pause"}
    row["command"] = "operator_note"
    row["command_sample"][4] = "operator_note"
    row["command_sample"][6] = json.dumps(note_payload)
    row["payload"] = dict(note_payload)
    (controller_dir / "phone_controller_command_outbox.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = validator.validate_run_artifact(controller_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_rejects_controller_operator_note_missing_from_sample(tmp_path: Path):
    controller_dir = tmp_path / "phone-controller"
    controller_dir.mkdir()
    status = _controller_status(native=True)
    status["command_protocol"]["supported_commands"].append("operator_note")
    (controller_dir / "phone_controller_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    row = _controller_row(native_sent=True, ack_received=True)
    row["command"] = "operator_note"
    row["command_sample"][4] = "operator_note"
    row["command_sample"][6] = json.dumps({"token": "secret", "package_id": "pkg-001"})
    row["payload"] = {"token": "secret", "package_id": "pkg-001", "note": "participant asked for a pause"}
    (controller_dir / "phone_controller_command_outbox.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = validator.validate_run_artifact(controller_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "row payload differs from command sample payload" in failures
    assert "operator_note command payload is missing note" in failures


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


def test_android_lsl_runtime_validator_requires_pc_admin_stream_descriptions_in_strict_mode(tmp_path: Path):
    admin_dir = tmp_path / "pc-android-admin"
    admin_dir.mkdir()
    status = _pc_admin_status()
    status.pop("stream_descriptions")
    (admin_dir / "pc_android_lsl_admin_status.json").write_text(json.dumps(status), encoding="utf-8")
    (admin_dir / "pc_android_lsl_command_outbox.jsonl").write_text(
        json.dumps(_pc_admin_row(native_sent=True, ack_received=True)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(admin_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "PC Android LSL admin stream descriptions are missing" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_pc_admin_stream_description_drift(tmp_path: Path):
    admin_dir = tmp_path / "pc-android-admin"
    admin_dir.mkdir()
    status = _pc_admin_status()
    status["stream_descriptions"]["command_signals"]["role"] = "inlet"
    (admin_dir / "pc_android_lsl_admin_status.json").write_text(json.dumps(status), encoding="utf-8")
    (admin_dir / "pc_android_lsl_command_outbox.jsonl").write_text(
        json.dumps(_pc_admin_row(native_sent=True, ack_received=True)) + "\n",
        encoding="utf-8",
    )

    result = validator.validate_run_artifact(admin_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "command_signals.role" in "\n".join(result.failures)


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


def test_android_lsl_runtime_validator_rejects_pc_admin_payload_drift(tmp_path: Path):
    admin_dir = tmp_path / "pc-android-admin"
    admin_dir.mkdir()
    (admin_dir / "pc_android_lsl_admin_status.json").write_text(json.dumps(_pc_admin_status()), encoding="utf-8")
    row = _pc_admin_row(native_sent=True, ack_received=True)
    row["payload"] = {
        "token": "secret",
        "package_id": "pkg-001",
        "requested_by": "pc_runner_lsl_admin",
        "note": "console note",
    }
    (admin_dir / "pc_android_lsl_command_outbox.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    result = validator.validate_run_artifact(admin_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "PC admin outbox row 1 row payload differs from command sample payload" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_phone_run_command_diary_ack_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir)

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_accepts_idle_native_start_command_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir, row=_phone_native_start_command_row())

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_rejects_phone_run_ack_payload_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    row = _phone_native_command_row()
    row["ack_sample"][9] = json.dumps({"command": "pause", "package_id": "pkg-001", "run_id": "other-run"})
    _write_phone_run_with_native_command_diary(run_dir, row=row)

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    failures = "\n".join(result.failures)
    assert result.ok is False
    assert "phone command diary row 1 ack payload differs from diary row payload" in failures
    assert "phone command diary row 1 ack payload run_id differs from diary row" in failures


def test_android_lsl_runtime_validator_rejects_operator_command_payload_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    operator_event = next(event for event in completion["events"] if event["type"] == "operator_command")
    operator_event["payload"]["state_changed"] = False
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "phone command diary row 1 payload differs from matching operator_command event" in "\n".join(
        result.failures
    )


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


def test_android_lsl_runtime_validator_rejects_native_command_summary_count_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["summary"]["native_lsl_command_received_count"] = 0
    completion["summary"]["native_lsl_command_ack_count"] = 0
    completion["summary"]["native_lsl_command_ack_failed_count"] = 1
    completion["summary"]["native_lsl_command_rejected_count"] = 1
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "completion summary native_lsl_command_received_count expected 1, got 0" in failures
    assert "completion summary native_lsl_command_ack_count expected 1, got 0" in failures
    assert "completion summary native_lsl_command_ack_failed_count expected 0, got 1" in failures
    assert "completion summary native_lsl_command_rejected_count expected 0, got 1" in failures


def test_android_lsl_runtime_validator_requires_phone_run_operator_command_event_for_ack_evidence(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir, include_operator_event=False)

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "requires matching operator_command events" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_accepts_phone_ui_command_diary_source(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_command_diary(run_dir, _phone_ui_command_row())

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is True
    assert result.failures == []


def test_android_lsl_runtime_validator_requires_phone_command_source_to_match_operator_event(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_command_diary(
        run_dir,
        _phone_ui_command_row(),
        operator_command_source="phone_runtime",
    )

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "command_source differs from matching operator_command event" in "\n".join(result.failures)


def test_android_lsl_runtime_validator_rejects_embedded_command_diary_status_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_command_diary(run_dir, _phone_ui_command_row())
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["command_diary"][0]["status"] = "rejected"
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir)

    assert result.ok is False
    assert "command_diary.jsonl row 1 status differs from completion.json embedded command_diary" in "\n".join(
        result.failures
    )


def test_android_lsl_runtime_validator_rejects_embedded_command_diary_payload_drift(tmp_path: Path):
    run_dir = tmp_path / "phone-run"
    run_dir.mkdir()
    _write_phone_run_with_native_command_diary(run_dir)
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["command_diary"][0]["payload"]["state_changed"] = False
    completion_path.write_text(json.dumps(completion), encoding="utf-8")

    result = validator.validate_run_artifact(run_dir, expect_native_transport=True, expect_command_acks=True)

    assert result.ok is False
    assert "command_diary.jsonl row 1 payload differs from completion.json embedded command_diary" in "\n".join(
        result.failures
    )


def _write_phone_run_with_command_diary(
    run_dir: Path,
    row: dict,
    *,
    operator_command_source: str | None = None,
) -> None:
    status = _status(native=False)
    status.update(_catalog_identity())
    event_source = operator_command_source if operator_command_source is not None else row["command_source"]
    participant_metadata = _participant_metadata()
    haptic_capability = _haptic_capability()
    events = [
        _phone_session_metadata_event(
            1,
            status=status,
            participant_metadata=participant_metadata,
            haptic_capability=haptic_capability,
        ),
        _phone_event(2, "run_start"),
        _phone_event(
            3,
            "operator_command",
            command_id=row["command_id"],
            command_source=event_source,
            sender_id=row["sender_id"],
            command=row["command"],
            status=row["status"],
            reason=row["reason"],
            ack_sent=row["ack_sent"],
            payload=row["payload"],
        ),
    ]
    markers = [_phone_marker(event) for event in events]
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
    _write_android_events_csv(run_dir / "events.csv", events)
    (run_dir / "participant_metadata.json").write_text(json.dumps(participant_metadata), encoding="utf-8")
    (run_dir / "haptic_capability.json").write_text(json.dumps(haptic_capability), encoding="utf-8")
    (run_dir / "command_diary.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", markers)
    _write_trigger_codes_csv(run_dir / "trigger_codes.csv", markers)


def _write_phone_run_with_native_command_diary(
    run_dir: Path,
    *,
    ack_sent: bool = True,
    include_operator_event: bool = True,
    row: dict | None = None,
) -> None:
    status = _status(native=True)
    status.update(_catalog_identity())
    row = row or _phone_native_command_row(ack_sent=ack_sent)
    participant_metadata = _participant_metadata()
    haptic_capability = _haptic_capability()
    events = [
        _phone_session_metadata_event(
            1,
            status=status,
            participant_metadata=participant_metadata,
            haptic_capability=haptic_capability,
        ),
        _phone_event(2, "run_start"),
    ]
    if include_operator_event:
        events.append(
            _phone_event(
                3,
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
    summary = {
        "total_event_count": len(events),
        "lsl_marker_mirror_count": len(markers),
        "native_lsl_transport_available": True,
        "native_lsl_marker_transport_enabled": True,
        "native_lsl_command_receiver_available": True,
        "native_lsl_pushed_count": len(markers),
        "native_lsl_failed_count": 0,
        "native_lsl_command_received_count": 1,
        "native_lsl_command_ack_count": 1 if ack_sent else 0,
        "native_lsl_command_ack_failed_count": 0 if ack_sent else 1,
        "native_lsl_command_rejected_count": 0 if row["status"] == "applied" else 1,
    }
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(
        json.dumps(
            {
                "lsl_runtime_status": status,
                "events": events,
                "lsl_marker_mirror": markers,
                "summary": summary,
                "participant_metadata": participant_metadata,
                "haptic": haptic_capability,
                "command_diary": [row],
            }
        ),
        encoding="utf-8",
    )
    _write_android_events_csv(run_dir / "events.csv", events)
    (run_dir / "participant_metadata.json").write_text(json.dumps(participant_metadata), encoding="utf-8")
    (run_dir / "haptic_capability.json").write_text(json.dumps(haptic_capability), encoding="utf-8")
    (run_dir / "command_diary.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", markers)
    _write_trigger_codes_csv(run_dir / "trigger_codes.csv", markers)


def _phone_native_command_row(*, ack_sent: bool = True) -> dict:
    payload = {
        "command": "pause",
        "package_id": "pkg-001",
        "run_id": "phone-run-001",
        "state_changed": True,
    }
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
        json.dumps(payload),
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
        "payload": dict(payload),
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


def _phone_native_start_command_row() -> dict:
    ack_sample = [
        "pps-lsl-command-ack.v1",
        "cmd-phone-start-001",
        "part-001",
        "android_phone_idle_runner",
        "applied",
        "starting_phone_run",
        "41.010000000",
        "41.020000000",
        "41.030000000",
        json.dumps(
            {
                "command": "start_experiment",
                "package_id": "pkg-001",
                "idle_runner_listener": True,
                "state_changed": True,
            }
        ),
    ]
    return {
        "schema": "pps-android-command-diary.v1",
        "command_id": "cmd-phone-start-001",
        "command_source": "native_lsl",
        "sender_id": "pc_runner",
        "session_id": "part-001",
        "command": "start_experiment",
        "status": "applied",
        "reason": "starting_phone_run",
        "payload": {
            "command": "start_experiment",
            "package_id": "pkg-001",
            "idle_runner_listener": True,
            "state_changed": True,
        },
        "package_id": "pkg-001",
        "run_id": "phone-run-001",
        "received_lsl_time": 41.01,
        "applied_lsl_time": 41.02,
        "ack_lsl_time": 41.03,
        "ack_sent": True,
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


def _phone_ui_command_row() -> dict:
    return {
        "schema": "pps-android-command-diary.v1",
        "command_id": "phone-1",
        "command_source": "phone_ui",
        "sender_id": "android_phone_ui",
        "session_id": "part-001",
        "command": "start_experiment",
        "status": "applied",
        "reason": "",
        "payload": {
            "package_id": "pkg-001",
            "block_count": 6,
            "phone_owned_session": True,
            "operator_action": "start_phone_run",
            "operator_payload": {},
        },
        "package_id": "pkg-001",
        "run_id": "phone-run-001",
        "ack_sent": False,
        "phone_unix_ms": 1780000000000,
        "phone_elapsed_realtime_ms": 123456,
    }


PHONE_EVENT_CODES = {
    "session_metadata": 8,
    "run_start": 1,
    "run_complete": 2,
    "block_start": 10,
    "audio_playback_start": 12,
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


def _phone_session_metadata_event(
    event_id: int,
    *,
    status: dict | None = None,
    participant_metadata: dict | None = None,
    haptic_capability: dict | None = None,
    package: dict | None = None,
) -> dict:
    return _phone_event(
        event_id,
        "session_metadata",
        participant_metadata=participant_metadata or _participant_metadata(),
        haptic=haptic_capability or _haptic_capability(),
        package=package
        or {
            "package_id": "pkg-001",
            "participant_id": "P001",
            "session_id": "session-001",
            "session_group_id": "group-001",
            "part_session_id": "part-001",
            "part_number": "01",
            "asset_strategy": "trial_building_blocks_only",
            "schedule_hash": "schedulehash",
        },
        lsl_runtime_status=status or _status(native=False),
    )


def _phone_audiotrack_block_start_event(event_id: int, *, block_id: str, block_index: int, block_label: str) -> dict:
    return _phone_event(
        event_id,
        "block_start",
        block_id=block_id,
        block_index=block_index,
        block_label=block_label,
        duration_s=1.0,
        trial_count=1,
        audio_timing_strategy="audiotrack_pcm_wav_playback_head",
        audio_sample_rate_hz=44100,
        audio_channel_count=2,
        audio_bits_per_sample=16,
        audio_encoding="pcm_16bit",
        audio_frame_count=44100,
        audio_duration_ms=1000,
        audio_data_size_bytes=176400,
    )


def _phone_audiotrack_playback_start_event(event_id: int, *, block_id: str, block_index: int, block_label: str) -> dict:
    return _phone_event(
        event_id,
        "audio_playback_start",
        block_id=block_id,
        block_index=block_index,
        block_label=block_label,
        audio_timing_strategy="audiotrack_pcm_wav_playback_head",
        audio_playback_start_elapsed_realtime_ms=123456 + event_id,
        audio_start_playback_head_frame=0,
        audio_playback_start_state="playing",
        audio_track_buffer_size_frames=11025,
        audio_track_buffer_size_bytes=44100,
    )


def _phone_audiotrack_cue_event(event_id: int, *, block_id: str, block_index: int, trial_uid: str) -> dict:
    return _phone_event(
        event_id,
        "vibration_cue",
        block_id=block_id,
        block_index=block_index,
        cue_id=1,
        trial_number=1,
        trial_uid=trial_uid,
        scheduled_block_time_ms=500,
        actual_block_time_ms=501,
        soa_ms="100",
        row_label="inhale",
        noise_type="looming",
        audio_scheduler="audiotrack_playback_head",
        scheduled_audio_frame=22050,
        audio_playback_head_frame=22060,
        audio_delivery_elapsed_realtime_ms=123500,
        audio_cue_jitter_frames=10,
        audio_cue_jitter_ms=10 * 1000.0 / 44100,
    )


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


def _write_android_events_csv(path: Path, events: list[dict]) -> None:
    fieldnames: list[str] = []
    for event in events:
        for key, value in event.items():
            if (value is None or isinstance(value, (str, int, float, bool))) and key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for event in events:
            writer.writerow({key: _android_csv_cell(event.get(key)) for key in fieldnames})


def _write_trigger_codes_csv(path: Path, markers: list[dict]) -> None:
    rows = [
        {
            "event_id": marker.get("event_id", ""),
            "event_code": marker.get("event_code", ""),
            "event_type": marker.get("event_type", ""),
            "trigger_key": marker.get("trigger_key", ""),
            "phone_elapsed_realtime_ms": marker.get("phone_elapsed_realtime_ms", ""),
        }
        for marker in markers
    ]
    _write_marker_csv(path, rows)


def _android_csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _update_completion_payload(run_dir: Path, **updates) -> None:
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion.update(updates)
    completion_path.write_text(json.dumps(completion), encoding="utf-8")


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


def _phone_run_source_segment_hashes(
    *,
    setup_hash: str = "runhash",
    source_segment5_hash: str = "segment5hash",
    order_hash: str = "orderhash",
    block_hash: str = "blockhash",
) -> dict:
    return {
        "schema": "pps-mobile-source-segment-hashes.v1",
        "source_run_setup_manifest_sha256": setup_hash,
        "source_segment5_manifest_sha256": source_segment5_hash,
        "segment6_order_csv_sha256": order_hash,
        "segment5_block_csvs": [{"block_id": "block-01", "sha256": block_hash}],
    }


def _phone_run_source_hash_summary(source_hashes: dict) -> dict:
    block_csvs = source_hashes.get("segment5_block_csvs") if isinstance(source_hashes.get("segment5_block_csvs"), list) else []
    return {
        "schema": str(source_hashes.get("schema") or ""),
        "source_run_setup_manifest_sha256": str(source_hashes.get("source_run_setup_manifest_sha256") or ""),
        "source_segment5_manifest_sha256": str(source_hashes.get("source_segment5_manifest_sha256") or ""),
        "segment6_order_csv_sha256": str(source_hashes.get("segment6_order_csv_sha256") or ""),
        "segment5_block_csv_count": len(block_csvs),
    }


def _inject_phone_run_provenance(
    run_dir: Path,
    *,
    session_seed: str = "seed-123",
    reconstruction_seed: str = "seed-123",
    catalog_seed: str = "seed-123",
    reconstruction_source_hashes: dict | None = None,
    catalog_source_hashes: dict | None = None,
    session_source_hashes: dict | None = None,
) -> None:
    manifest_source_hashes = _phone_run_source_segment_hashes()
    phone_source_hashes = _phone_run_source_hash_summary(manifest_source_hashes)
    roster = ["P001", "P002"]

    manifest_path = run_dir / "run_package_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["participant_roster"] = roster
    manifest["randomization_seed"] = "seed-123"
    manifest["source_segment_hashes"] = manifest_source_hashes
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    status_path = run_dir / "lsl_runtime_status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    _update_stream_description_session_metadata(
        status,
        participant_roster_count=len(roster),
        randomization_seed="seed-123",
        source_hashes=phone_source_hashes,
    )
    status_path.write_text(json.dumps(status), encoding="utf-8")

    reconstruction_path = run_dir / "reconstruction_contract.json"
    reconstruction = json.loads(reconstruction_path.read_text(encoding="utf-8"))
    reconstruction["participant_roster_count"] = len(roster)
    reconstruction["randomization_seed"] = reconstruction_seed
    reconstruction["source_segment_hashes"] = reconstruction_source_hashes or phone_source_hashes
    reconstruction_path.write_text(json.dumps(reconstruction), encoding="utf-8")

    catalog = _catalog_entry(native=False)
    catalog["asset_strategy"] = "trial_building_blocks_only"
    catalog["participant_roster_count"] = len(roster)
    catalog["randomization_seed"] = catalog_seed
    catalog["source_segment_hashes"] = catalog_source_hashes or phone_source_hashes
    catalog["reconstruction"]["package_asset_strategy"] = "trial_building_blocks_only"
    (run_dir / "phone_run_catalog_entry.json").write_text(json.dumps(catalog), encoding="utf-8")

    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["lsl_runtime_status"] = status
    package_payload = {
        "package_id": "pkg-001",
        "participant_id": "P001",
        "asset_strategy": "trial_building_blocks_only",
        "schedule_hash": "schedulehash",
        "participant_roster_count": len(roster),
        "randomization_seed": session_seed,
        "source_segment_hashes": session_source_hashes or phone_source_hashes,
    }
    completion.setdefault("package", {}).update(package_payload)
    events = [event for event in completion.get("events", []) if isinstance(event, dict)]
    session_event = next((event for event in events if str(event.get("type") or "") == "session_metadata"), None)
    if session_event is not None:
        session_event["package"] = package_payload
    else:
        next_event_id = max((int(event.get("event_id") or 0) for event in events), default=0) + 1
        events.append(_phone_session_metadata_event(next_event_id, package=package_payload))
    markers = [_phone_marker(event) for event in events]
    completion["events"] = events
    completion["lsl_marker_mirror"] = markers
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    _write_android_events_csv(run_dir / "events.csv", events)
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", markers)
    _write_trigger_codes_csv(run_dir / "trigger_codes.csv", markers)


def _stream_session_metadata_json(
    *,
    participant_roster_count: int = 0,
    randomization_seed: str = "",
    source_hashes: dict | None = None,
    participant_metadata: dict | None = None,
    haptic_capability: dict | None = None,
) -> str:
    payload = {
        "package_id": "pkg-001",
        "asset_strategy": "trial_building_blocks_only",
        "schedule_hash": "schedulehash",
        "participant_roster_count": participant_roster_count,
        "randomization_seed": randomization_seed,
        "source_segment_hashes": source_hashes or _phone_run_source_hash_summary(_phone_run_source_segment_hashes()),
        "privacy_default": "metadata_payload_only",
        "demographics_in_stream_name": False,
    }
    metadata = participant_metadata if participant_metadata is not None else _participant_metadata()
    haptic = haptic_capability if haptic_capability is not None else _haptic_capability()
    payload["participant_metadata_summary"] = _lsl_participant_metadata_summary(metadata)
    payload["haptic_capability_summary"] = _lsl_haptic_capability_summary(haptic)
    return json.dumps(payload)


def _lsl_participant_metadata_summary(participant_metadata: dict) -> dict:
    return {
        "schema": "pps-android-lsl-participant-metadata-summary.v1",
        "participant_id": participant_metadata.get("participant_id", ""),
        "session_id": participant_metadata.get("session_id", ""),
        "session_group_id": participant_metadata.get("session_group_id", ""),
        "part_session_id": participant_metadata.get("part_session_id", ""),
        "part_number": participant_metadata.get("part_number", ""),
        "age_years": participant_metadata.get("age_years", ""),
        "handedness": participant_metadata.get("handedness", ""),
        "gender": participant_metadata.get("gender", ""),
        "tactile_threshold_percent": participant_metadata.get("tactile_threshold_percent"),
        "tactile_threshold_source": participant_metadata.get("tactile_threshold_source", ""),
        "tactile_threshold_calibration_status": participant_metadata.get("tactile_threshold_calibration_status", ""),
        "stream_privacy": participant_metadata.get("stream_privacy", "metadata_payload_only"),
    }


def _lsl_haptic_capability_summary(haptic_capability: dict) -> dict:
    return {
        "schema": "pps-android-lsl-haptic-capability-summary.v1",
        "has_vibrator": haptic_capability.get("has_vibrator", False),
        "has_amplitude_control": haptic_capability.get("has_amplitude_control", False),
        "calibration_policy": haptic_capability.get("calibration_policy", ""),
        "calibration_status": haptic_capability.get("calibration_status", ""),
        "recommended_threshold_percent": haptic_capability.get("recommended_threshold_percent"),
        "recommended_amplitude": haptic_capability.get("recommended_amplitude"),
    }


def _update_stream_description_session_metadata(
    status: dict,
    *,
    participant_roster_count: int,
    randomization_seed: str,
    source_hashes: dict,
) -> None:
    descriptions = status.get("stream_descriptions") if isinstance(status.get("stream_descriptions"), dict) else {}
    metadata_json = _stream_session_metadata_json(
        participant_roster_count=participant_roster_count,
        randomization_seed=randomization_seed,
        source_hashes=source_hashes,
    )
    for key in ("rich_markers", "numeric_triggers"):
        row = descriptions.get(key) if isinstance(descriptions.get(key), dict) else None
        if row is None:
            continue
        row["session_metadata_json"] = metadata_json


def _write_lightweight_phone_run(run_dir: Path, *, include_materialization_event: bool = True, native: bool = False) -> None:
    status = _status(native=native)
    status["asset_strategy"] = "trial_building_blocks_only"
    wav_bytes = b"RIFF....WAVE"
    wav_sha256 = hashlib.sha256(wav_bytes).hexdigest()
    topup_wav_bytes = b"RIFFtopupWAVE"
    topup_wav_sha256 = hashlib.sha256(topup_wav_bytes).hexdigest()
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
        "trials": [
            {
                "trial_number": 1,
                "trial_uid": "trial-001",
                "building_block_asset_id": "trial-asset-001",
                "trial_type": "audio_tactile",
                "family": "standard",
                "soa_ms": "100",
                "row_label": "inhale",
                "noise_type": "looming",
                "start_s": 0.0,
                "end_s": 1.0,
                "duration_s": 1.0,
                "tactile_onset_s": 0.5,
                "response_window_onset_s": 0.5,
            }
        ],
    }
    response_ledger = [
        {
            "schema": "pps-android-phone-response-ledger.v1",
            "ledger_role": "source_trial",
            "block_id": "block-01",
            "block_index": 1,
            "trial_number": 1,
            "trial_uid": "trial-001",
            "cue_id": 1,
            "scheduled_block_time_ms": 500,
            "response_window_start_ms": 600,
            "response_window_end_ms": 1800,
            "hit": False,
            "status": "missed_rescued_by_topup",
            "rt_ms": "",
            "tap_event_id": "",
            "building_block_asset_id": "trial-asset-001",
            "topup_eligible": True,
            "topup_attempted": True,
            "topup_trial_uid": "phone-topup-1-trial-001",
            "topup_hit": True,
            "topup_rt_ms": 200,
            "topup_tap_event_id": 12,
        },
        {
            "schema": "pps-android-phone-response-ledger.v1",
            "ledger_role": "topup_rescue",
            "source_trial_uid": "trial-001",
            "source_trial_number": 1,
            "trial_uid": "phone-topup-1-trial-001",
            "trial_number": 1,
            "block_id": "phone-topup-01",
            "block_index": "",
            "scheduled_block_time_ms": 500,
            "response_window_start_ms": 600,
            "response_window_end_ms": 1800,
            "hit": True,
            "status": "topup_hit",
            "rt_ms": 200,
            "tap_event_id": 10,
            "building_block_asset_id": "trial-asset-001",
        },
    ]
    response_summary = {
        "schema": "pps-android-phone-response-summary.v1",
        "response_policy": "first_touch_100_1300_ms_after_tactile",
        "eligible_trial_count": 1,
        "ledger_row_count": 2,
        "hit_count": 0,
        "missed_needs_topup_count": 1,
        "topup_rescue_count": 1,
        "topup_attempted_count": 1,
        "topup_hit_count": 1,
        "topup_miss_count": 0,
        "final_rescued_hit_count": 1,
        "final_unresolved_miss_count": 0,
    }
    topup_plan_trial = {
        "topup_role": "rescue",
        "source_block_id": "block-01",
        "source_block_index": 1,
        "source_trial_uid": "trial-001",
        "source_trial_number": 1,
        "building_block_asset_id": "trial-asset-001",
        "trial_type": "audio_tactile",
        "family": "standard",
        "soa_ms": "100",
        "row_label": "inhale",
        "noise_type": "looming",
        "duration_s": 1.0,
        "tactile_onset_s": 0.5,
        "response_window_onset_s": 0.5,
    }
    topup_plan = {
        "schema": "pps-android-phone-topup-plan.v1",
        "status": "played",
        "synthesis_strategy": "pcm_wav_concat_without_ffmpeg",
        "response_min_rt_ms": 100,
        "response_max_rt_ms": 1300,
        "missed_trial_count": 1,
        "topup_trial_count": 1,
        "topup_attempted_count": 1,
        "topup_hit_count": 1,
        "final_unresolved_miss_count": 0,
        "trials": [topup_plan_trial],
    }
    topup_materialization_trial = {
        **topup_plan_trial,
        "topup_trial_number": 1,
        "topup_trial_uid": "phone-topup-1-trial-001",
        "topup_start_s": 0.0,
        "topup_end_s": 1.0,
        "topup_duration_s": 1.0,
    }
    topup_materialization = {
        "schema": "pps-android-phone-topup-materialization.v1",
        "status": "materialized",
        "source_plan_schema": "pps-android-phone-topup-plan.v1",
        "synthesis_strategy": "pcm_wav_concat_without_ffmpeg",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "wav_filename": "phone_topup_block.wav",
        "wav_sha256": topup_wav_sha256,
        "sample_rate_hz": 44100,
        "channel_count": 2,
        "bits_per_sample": 16,
        "encoding": "PCM_16",
        "frame_count": 44100,
        "duration_ms": 1000,
        "trial_count": 1,
        "tactile_cue_count": 1,
        "trials": [topup_materialization_trial],
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
        "building_blocks": [
            {
                "asset_id": "trial-asset-001",
                "role": "trial_building_block",
                "filename": "trial.wav",
                "sha256": "source-sha",
                "trial_type": "audio_tactile",
                "family": "audio_tactile",
                "row_label": "inhale",
                "soa_ms": "100",
                "noise_type": "white",
                "duration_s": 1.0,
                "tactile_onset_s": 0.5,
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
                "tactile_cues": [{"cue_id": 1, "trial_uid": "trial-001", "time_s": 0.5}],
                "tactile_cue_count": 1,
            }
        ],
        "reconstruction": {
            "package_asset_strategy": "trial_building_blocks_only",
            "study_hierarchy": validator.ANDROID_REQUIRED_STUDY_HIERARCHY,
            "schedule_hash": "schedulehash",
            "building_block_count": 1,
            "block_count": 1,
            "trial_count": 1,
        },
    }
    reconstruction_artifact = {
        "schema": "pps-mobile-phone-run-reconstruction.v1",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "asset_strategy": "trial_building_blocks_only",
        "reconstruction": {
            "package_asset_strategy": "trial_building_blocks_only",
            "study_hierarchy": validator.ANDROID_REQUIRED_STUDY_HIERARCHY,
            "source_run_setup_manifest_path": "run_setup.json",
            "schedule_hash": "schedulehash",
            "building_block_count": 1,
            "block_count": 1,
            "trial_count": 1,
        },
    }
    participant_metadata = _participant_metadata()
    haptic_capability = _haptic_capability()
    events = [_phone_event(1, "run_start")]
    if include_materialization_event:
        events.append(_phone_event(2, "phone_scheduled_block_materialization", **materialization))
    events.append(_phone_audiotrack_block_start_event(3, block_id="block-01", block_index=1, block_label="Block 01"))
    events.append(_phone_audiotrack_playback_start_event(4, block_id="block-01", block_index=1, block_label="Block 01"))
    events.append(_phone_audiotrack_cue_event(5, block_id="block-01", block_index=1, trial_uid="trial-001"))
    events.append(_phone_event(6, "block_complete", block_id="block-01", block_index=1, trial_count=1))
    events.append(_phone_event(7, "phone_topup_materialization", **topup_materialization))
    events.append(_phone_audiotrack_block_start_event(8, block_id="phone-topup-01", block_index=2, block_label="Phone top-up"))
    events.append(_phone_audiotrack_playback_start_event(9, block_id="phone-topup-01", block_index=2, block_label="Phone top-up"))
    events.append(_phone_audiotrack_cue_event(10, block_id="phone-topup-01", block_index=2, trial_uid="phone-topup-1-trial-001"))
    events.append(_phone_event(11, "block_complete", block_id="phone-topup-01", block_index=2, trial_count=1))
    events.append(_phone_event(12, "tap", block_id="phone-topup-01", block_index=2, trial_uid="phone-topup-1-trial-001", rt_ms=200))
    events.append(
        _phone_session_metadata_event(
            13,
            status=status,
            participant_metadata=participant_metadata,
            haptic_capability=haptic_capability,
        )
    )
    markers = [_phone_marker(event) for event in events]
    summary = {
        "total_event_count": len(events),
        "lsl_marker_mirror_count": len(markers),
        "native_lsl_transport_available": native,
        "native_lsl_marker_transport_enabled": native,
        "native_lsl_command_receiver_available": native,
        "native_lsl_timestamp_strategy": "android_elapsed_realtime_plus_open_lsl_clock_offset",
        "native_lsl_clock_offset_s": 0.0,
        "native_lsl_pushed_count": len(markers) if native else 0,
        "native_lsl_failed_count": 0,
        "native_lsl_command_received_count": 0,
        "native_lsl_command_ack_count": 0,
        "native_lsl_command_ack_failed_count": 0,
        "native_lsl_command_rejected_count": 0,
    }
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
                "summary": summary,
                "participant_metadata": participant_metadata,
                "haptic": haptic_capability,
                "phone_response_summary": response_summary,
                "phone_response_ledger": response_ledger,
                "phone_topup_plan": topup_plan,
                "phone_topup_materialization": topup_materialization,
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "participant_metadata.json").write_text(json.dumps(participant_metadata), encoding="utf-8")
    (run_dir / "haptic_capability.json").write_text(json.dumps(haptic_capability), encoding="utf-8")
    _write_android_events_csv(run_dir / "events.csv", events)
    _write_marker_csv(run_dir / "lsl_marker_mirror.csv", markers)
    _write_trigger_codes_csv(run_dir / "trigger_codes.csv", markers)
    _write_marker_csv(run_dir / "phone_response_ledger.csv", response_ledger)
    (run_dir / "phone_topup_plan.json").write_text(json.dumps(topup_plan), encoding="utf-8")
    (run_dir / "phone_topup_materialization.json").write_text(json.dumps(topup_materialization), encoding="utf-8")
    (run_dir / "phone_topup_block.wav").write_bytes(topup_wav_bytes)
    (materialized_dir / "phone_materialized_block_01.json").write_text(json.dumps(materialization), encoding="utf-8")
    (materialized_dir / "phone_materialized_block_01.wav").write_bytes(wav_bytes)


def _write_artifact_file_inventory(run_dir: Path) -> None:
    completion_path = run_dir / "completion.json"
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["completed"] = True
    completion["artifact_file_inventory_artifact"] = {
        "filename": "artifact_file_inventory.json",
        "csv_filename": "artifact_file_inventory.csv",
        "schema": "pps-android-phone-run-artifact-file-inventory.v1",
        "self_included": False,
    }
    completion_path.write_text(json.dumps(completion), encoding="utf-8")
    rows = []
    for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
        rel = path.relative_to(run_dir).as_posix()
        if rel in {"artifact_file_inventory.json", "artifact_file_inventory.csv"}:
            continue
        rows.append(
            {
                "relative_path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "modified_unix_ms": int(path.stat().st_mtime * 1000),
            }
        )
    inventory = {
        "schema": "pps-android-phone-run-artifact-file-inventory.v1",
        "run_id": "phone-run-001",
        "package_id": "pkg-001",
        "complete": True,
        "generated_unix_ms": 1780000000000,
        "self_included": False,
        "file_count": len(rows),
        "files": rows,
    }
    (run_dir / "artifact_file_inventory.json").write_text(json.dumps(inventory), encoding="utf-8")
    with (run_dir / "artifact_file_inventory.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["relative_path", "size_bytes", "sha256", "modified_unix_ms"])
        writer.writeheader()
        writer.writerows(rows)


def _write_phone_owned_data_export(run_dir: Path) -> None:
    export_root = run_dir.parent / "phone_owned_exports"
    data_min = export_root / "1.Data_min"
    data_min.mkdir(parents=True)
    rows = [
        {
            "participant_id": "P001",
            "session_id": "session-001",
            "part_session_id": "part-001",
            "part_number": "01",
            "block_number": "1",
            "block_label": "Block 01",
            "trial_number": "1",
            "trial_number_global": "1",
            "trial_uid": "trial-001",
            "condition": "standard",
            "phase": "Inhale",
            "noise_type": "looming",
            "trial_type": "audio_tactile",
            "soa_ms": "100",
            "response_given": "false",
            "hit_miss": "Miss",
            "reaction_time_ms": "",
        },
        {
            "participant_id": "P001",
            "session_id": "session-001",
            "part_session_id": "part-001",
            "part_number": "01",
            "block_number": "2",
            "block_label": "Phone top-up",
            "trial_number": "1",
            "trial_number_global": "2",
            "trial_uid": "phone-topup-1-trial-001",
            "condition": "standard",
            "phase": "Inhale",
            "noise_type": "looming",
            "trial_type": "audio_tactile",
            "soa_ms": "100",
            "response_given": "true",
            "hit_miss": "Hit",
            "reaction_time_ms": "200",
        },
    ]
    for name in ("P001.csv", "master_successful_participants.csv"):
        with (data_min / name).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=validator.PHONE_DATA_MIN_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    data_max = export_root / "2.Data_max" / "P001" / "runs" / run_dir.name
    data_max.mkdir(parents=True)
    (data_max / "completion.json").write_text((run_dir / "completion.json").read_text(encoding="utf-8"), encoding="utf-8")
    export = {
        "schema": "pps-android-phone-owned-data-export.v1",
        "participant_id": "P001",
        "run_id": run_dir.name,
        "package_id": "pkg-001",
        "session_id": "session-001",
        "part_session_id": "part-001",
        "part_number": "01",
        "phone_owned_session": True,
        "data_min_schema": "pps-data-min-publication-trials.v1",
        "data_min_fieldnames": validator.PHONE_DATA_MIN_FIELDNAMES,
        "data_min_participant_csv": str(data_min / "P001.csv"),
        "data_min_master_successful_participants_csv": str(data_min / "master_successful_participants.csv"),
        "data_min_row_count": len(rows),
        "data_max_run_dir": str(data_max),
        "data_max_source_run_dir": str(run_dir),
        "privacy": {
            "scope": "app_private_phone_owned_export",
            "demographics_in_stream_name": False,
            "participant_names_exported": False,
        },
    }
    (run_dir / "phone_owned_data_export.json").write_text(json.dumps(export), encoding="utf-8")


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
        "stream_descriptions": _stream_descriptions(),
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


def _stream_descriptions() -> dict:
    return {
        "schema": "pps-android-lsl-stream-descriptions.v1",
        "runtime_authority": "android_phone",
        "privacy": {
            "default": "metadata_payload_only",
            "participant_demographics_location": "metadata_and_payload_artifacts",
            "demographics_in_stream_name": False,
        },
        "rich_markers": {
            "name": "PPSMarkersV2",
            "type": "Markers",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(validator.LSL_MARKER_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id": "pps-android-markers-v2-phone-run-001",
            "marker_version": "2.0",
            **_catalog_identity(),
            "session_metadata_json": _stream_session_metadata_json(),
            "channel_labels": list(validator.LSL_MARKER_CHANNELS),
        },
        "numeric_triggers": {
            "name": "PPSTriggerCodes",
            "type": "TriggerCodes",
            "role": "outlet",
            "channel_format": "int32",
            "channel_count": 1,
            "nominal_srate_hz": 0.0,
            "source_id": "pps-android-trigger-codes-phone-run-001",
            **_catalog_identity(),
            "session_metadata_json": _stream_session_metadata_json(),
            "channel_labels": ["event_code"],
        },
        "command_signals": {
            "name": "PPSCommandSignalsV1",
            "type": "CommandSignals",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(validator.LSL_COMMAND_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_pattern": "pps-*-command-signals-v1-*",
            "channel_labels": list(validator.LSL_COMMAND_CHANNELS),
            "token_required": True,
        },
        "command_acks": {
            "name": "PPSCommandAcksV1",
            "type": "CommandAcks",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(validator.LSL_ACK_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id": "pps-android-command-acks-v1-phone-run-001",
            "channel_labels": list(validator.LSL_ACK_CHANNELS),
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


def _catalog_index(entry: dict) -> dict:
    return {
        "schema": "pps-android-phone-run-catalog.v1",
        "updated_unix_ms": 1780000000100,
        "participant_count": 1,
        "run_count": 1,
        "participants": [
            {
                "participant_id": entry["participant_id"],
                "participant_dir": entry["participant_id"],
                "run_count": 1,
                "latest_run_id": entry["run_id"],
                "latest_completed": bool(entry.get("completed")),
                "latest_updated_unix_ms": entry.get("updated_unix_ms", 1780000000000),
            }
        ],
    }


def _write_phone_run_catalog_root(files_dir: Path, entry: dict) -> None:
    catalog_root = files_dir / "phone_run_catalog"
    participant_dir = catalog_root / entry["participant_id"]
    participant_dir.mkdir(parents=True)
    normalized_entry = {**entry, "updated_unix_ms": entry.get("updated_unix_ms", 1780000000000)}
    (participant_dir / "runs.jsonl").write_text(json.dumps(normalized_entry) + "\n", encoding="utf-8")
    (participant_dir / "latest_run.json").write_text(json.dumps(normalized_entry), encoding="utf-8")
    (catalog_root / "index.json").write_text(json.dumps(_catalog_index(normalized_entry)), encoding="utf-8")


def _write_phone_run_catalog_to_zip(archive: zipfile.ZipFile, entry: dict) -> None:
    normalized_entry = {**entry, "updated_unix_ms": entry.get("updated_unix_ms", 1780000000000)}
    participant_dir = f"phone_run_catalog/{normalized_entry['participant_id']}"
    archive.writestr("phone_run_catalog/index.json", json.dumps(_catalog_index(normalized_entry)))
    archive.writestr(f"{participant_dir}/runs.jsonl", json.dumps(normalized_entry) + "\n")
    archive.writestr(f"{participant_dir}/latest_run.json", json.dumps(normalized_entry))


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
        "stream_descriptions": _controller_stream_descriptions(),
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


def _controller_stream_descriptions() -> dict:
    return {
        "schema": "pps-android-lsl-stream-descriptions.v1",
        "runtime_authority": "android_controller",
        "role": "controller",
        "target_session_id": "part-001",
        "participant_id": "P001",
        "privacy": {
            "default": "metadata_payload_only",
            "participant_demographics_location": "metadata_and_payload_artifacts",
            "demographics_in_stream_name": False,
        },
        "command_signals": {
            "name": "PPSCommandSignalsV1",
            "type": "CommandSignals",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(validator.LSL_COMMAND_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id": "pps-android-controller-signals-v1-part-001-android_controller",
            "channel_labels": list(validator.LSL_COMMAND_CHANNELS),
            "token_required": True,
        },
        "command_acks": {
            "name": "PPSCommandAcksV1",
            "type": "CommandAcks",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(validator.LSL_ACK_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_pattern": "pps-*-command-acks-v1-*",
            "channel_labels": list(validator.LSL_ACK_CHANNELS),
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
        "stream_descriptions": _pc_admin_stream_descriptions(),
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


def _pc_admin_stream_descriptions() -> dict:
    return {
        "schema": "pps-android-lsl-stream-descriptions.v1",
        "runtime_authority": "pc_runner",
        "role": "pc_android_lsl_admin",
        "native_transport": "liblsl",
        "target_session_id": "part-001",
        "sender_id": "pc_runner",
        "privacy": {
            "default": "metadata_payload_only",
            "participant_demographics_location": "metadata_and_payload_artifacts",
            "demographics_in_stream_name": False,
        },
        "command_signals": {
            "name": "PPSCommandSignalsV1",
            "type": "CommandSignals",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(validator.LSL_COMMAND_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id": "pps-command-signals-v1-part-001-pc_runner",
            "channel_labels": list(validator.LSL_COMMAND_CHANNELS),
            "token_required": True,
        },
        "command_acks": {
            "name": "PPSCommandAcksV1",
            "type": "CommandAcks",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(validator.LSL_ACK_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_pattern": "pps-command-acks-v1-*-*",
            "channel_labels": list(validator.LSL_ACK_CHANNELS),
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
