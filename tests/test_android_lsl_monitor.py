from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from peripersonal_space_toolkit import android_lsl_monitor as monitor
from peripersonal_space_toolkit.lsl_command_ack import LSLCommandAck, LSLCommandSignal, ack_to_sample, command_to_sample
from peripersonal_space_toolkit.timing_events import LSL_MARKER_CHANNELS, MARKER_VERSION


SCRIPT_PATH = Path("validation_protocols/scripts/validate_android_lsl_runtime_artifact.py")
spec = importlib.util.spec_from_file_location("validate_android_lsl_runtime_artifact_for_monitor", SCRIPT_PATH)
assert spec and spec.loader
validator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = validator
spec.loader.exec_module(validator)


def test_build_android_lsl_monitor_row_extracts_reconstruction_fields():
    row = monitor.build_android_lsl_monitor_row(
        stream_key="rich_markers",
        sample=_rich_marker_sample(event_type="block_start", event_code="10"),
        lsl_timestamp=123.0,
        source_id="android-phone",
        pc_received_unix_ms=1000,
        pc_received_perf_counter_s=10.0,
    )

    assert row["schema"] == monitor.PC_ANDROID_LSL_MONITOR_ROW_SCHEMA
    assert row["stream_name"] == "PPSMarkersV2"
    assert row["channel_labels"] == list(LSL_MARKER_CHANNELS)
    assert row["marker_version"] == MARKER_VERSION
    assert row["event_type"] == "block_start"
    assert row["event_code"] == 10
    assert row["session_id"] == "session-001"
    assert row["part_session_id"] == "part-001"
    assert json.loads(row["payload_json"])["package_id"] == "pkg-001"


def test_write_android_lsl_monitor_artifacts_and_report(tmp_path: Path):
    rows = [
        monitor.build_android_lsl_monitor_row(
            stream_key="rich_markers",
            sample=_rich_marker_sample(event_type="session_metadata", event_code="1"),
            lsl_timestamp=1.0,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="numeric_triggers",
            sample=[10],
            lsl_timestamp=1.1,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="command_acks",
            sample=ack_to_sample(
                LSLCommandAck(
                    command_id="cmd-1",
                    session_id="part-001",
                    receiver_id="android_runner",
                    status="applied",
                    reason="started",
                    received_lsl_time=1.2,
                    applied_lsl_time=1.3,
                    ack_lsl_time=1.4,
                    payload={"state": "running"},
                )
            ),
            lsl_timestamp=1.4,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="command_signals",
            sample=_command_signal_sample(command_id="cmd-2", command="pause"),
            lsl_timestamp=1.5,
        ),
    ]
    report = monitor.build_android_lsl_monitor_report(
        rows,
        required_streams=["rich_markers", "numeric_triggers", "command_acks", "command_signals"],
        output_dir=tmp_path,
    )

    events_path, report_path, status_path = monitor.write_android_lsl_monitor_artifacts(tmp_path, rows, report=report)

    assert events_path.name == monitor.PC_ANDROID_LSL_MONITOR_EVENTS
    assert report_path.name == monitor.PC_ANDROID_LSL_MONITOR_REPORT
    assert status_path.name == monitor.PC_ANDROID_LSL_MONITOR_STATUS
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved_report["ok"] is True
    assert saved_report["stream_counts"] == {
        "rich_markers": 1,
        "numeric_triggers": 1,
        "command_acks": 1,
        "command_signals": 1,
    }
    assert saved_report["observed_session_ids"] == ["part-001", "session-001"]
    assert saved_report["observed_command_ack_ids"] == ["cmd-1"]
    assert saved_report["observed_command_signal_ids"] == ["cmd-2"]
    assert saved_report["observed_command_signal_ids_without_ack"] == ["cmd-2"]
    assert saved_report["observed_command_ack_ids_without_signal"] == ["cmd-1"]
    assert saved_report["observed_command_names"] == {"pause": 1}
    assert saved_report["status"]["stream_descriptions"]["command_signals"]["role"] == "inlet"


def test_validator_accepts_pc_android_lsl_monitor_artifact(tmp_path: Path):
    rows = [
        monitor.build_android_lsl_monitor_row(
            stream_key="rich_markers",
            sample=_rich_marker_sample(event_type="block_start", event_code="10"),
            lsl_timestamp=1.0,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="numeric_triggers",
            sample=[10],
            lsl_timestamp=1.1,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="command_acks",
            sample=ack_to_sample(
                LSLCommandAck(
                    command_id="cmd-1",
                    session_id="part-001",
                    receiver_id="android_runner",
                    status="applied",
                    reason="started",
                    received_lsl_time=1.2,
                    applied_lsl_time=1.3,
                    ack_lsl_time=1.4,
                    payload={},
                )
            ),
            lsl_timestamp=1.4,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="command_signals",
            sample=_command_signal_sample(command_id="cmd-1", command="start_experiment"),
            lsl_timestamp=1.5,
        ),
    ]
    report = monitor.build_android_lsl_monitor_report(
        rows,
        required_streams=["rich_markers", "numeric_triggers", "command_acks", "command_signals"],
        output_dir=tmp_path,
    )
    monitor.write_android_lsl_monitor_artifacts(tmp_path, rows, report=report)

    result = validator.validate_run_artifact(
        tmp_path,
        expect_native_transport=True,
        expect_command_acks=True,
    )

    assert result.ok is True
    assert result.failures == []
    assert result.status["role"] == "pc_android_lsl_monitor"


def test_validator_requires_pc_monitor_ack_for_observed_command_signal(tmp_path: Path):
    rows = [
        monitor.build_android_lsl_monitor_row(
            stream_key="rich_markers",
            sample=_rich_marker_sample(event_type="block_start", event_code="10"),
            lsl_timestamp=1.0,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="numeric_triggers",
            sample=[10],
            lsl_timestamp=1.1,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="command_acks",
            sample=ack_to_sample(
                LSLCommandAck(
                    command_id="cmd-other",
                    session_id="part-001",
                    receiver_id="android_runner",
                    status="applied",
                    reason="started",
                    received_lsl_time=1.2,
                    applied_lsl_time=1.3,
                    ack_lsl_time=1.4,
                    payload={},
                )
            ),
            lsl_timestamp=1.4,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="command_signals",
            sample=_command_signal_sample(command_id="cmd-expected", command="start_experiment"),
            lsl_timestamp=1.5,
        ),
    ]
    report = monitor.build_android_lsl_monitor_report(
        rows,
        required_streams=["rich_markers", "numeric_triggers", "command_acks", "command_signals"],
        output_dir=tmp_path,
    )
    monitor.write_android_lsl_monitor_artifacts(tmp_path, rows, report=report)

    result = validator.validate_run_artifact(
        tmp_path,
        expect_native_transport=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    assert "missing acks for observed command ids: cmd-expected" in "\n".join(result.failures)


def test_build_android_lsl_monitor_row_extracts_command_signal_fields():
    row = monitor.build_android_lsl_monitor_row(
        stream_key="command_signals",
        sample=_command_signal_sample(command_id="cmd-3", command="resume"),
        lsl_timestamp=2.0,
        source_id="pc-runner",
    )

    assert row["stream_name"] == "PPSCommandSignalsV1"
    assert row["command_schema"] == "pps-lsl-command.v1"
    assert row["command_id"] == "cmd-3"
    assert row["session_id"] == "part-001"
    assert row["sender_id"] == "pc_runner"
    assert row["command"] == "resume"
    assert row["package_id"] == "pkg-001"
    assert row["participant_id"] == "P001"
    assert row["target_session_id"] == "part-001"
    assert row["target_part_session_id"] == "part-001"
    assert row["target_session_group_id"] == "group-001"
    assert row["target_part_number"] == "1"
    assert json.loads(row["payload_json"])["token"] == "secret"


def test_build_android_lsl_monitor_row_extracts_command_ack_target_identity():
    row = monitor.build_android_lsl_monitor_row(
        stream_key="command_acks",
        sample=ack_to_sample(
            LSLCommandAck(
                command_id="cmd-ack-identity",
                session_id="part-001",
                receiver_id="android_runner",
                status="applied",
                reason="ok",
                received_lsl_time=2.01,
                applied_lsl_time=2.02,
                ack_lsl_time=2.03,
                payload={
                    "command": "pause",
                    "package_id": "pkg-001",
                    "participant_id": "P001",
                    "target_session_id": "part-001",
                    "target_part_session_id": "part-001",
                    "target_session_group_id": "group-001",
                    "target_part_number": "1",
                },
            )
        ),
        lsl_timestamp=2.03,
        source_id="android-phone",
    )

    assert row["stream_name"] == "PPSCommandAcksV1"
    assert row["command_id"] == "cmd-ack-identity"
    assert row["package_id"] == "pkg-001"
    assert row["participant_id"] == "P001"
    assert row["target_session_id"] == "part-001"
    assert row["target_part_session_id"] == "part-001"
    assert row["target_session_group_id"] == "group-001"
    assert row["target_part_number"] == "1"


def test_build_android_lsl_monitor_row_preserves_operator_note_payload():
    row = monitor.build_android_lsl_monitor_row(
        stream_key="command_signals",
        sample=_command_signal_sample(
            command_id="cmd-note-1",
            command="operator_note",
            payload={"token": "secret", "package_id": "pkg-001", "note": "participant asked for a pause"},
        ),
        lsl_timestamp=2.1,
        source_id="pc-runner",
    )

    assert row["command"] == "operator_note"
    payload = json.loads(row["payload_json"])
    assert payload["token"] == "secret"
    assert payload["note"] == "participant asked for a pause"


def test_validator_rejects_pc_monitor_operator_note_payload_drift(tmp_path: Path):
    rows = [
        monitor.build_android_lsl_monitor_row(
            stream_key="command_signals",
            sample=_command_signal_sample(command_id="cmd-note-2", command="operator_note"),
            lsl_timestamp=2.2,
        ),
    ]
    rows[0]["payload_json"] = json.dumps(
        {"token": "secret", "package_id": "pkg-001", "note": "participant asked for a pause"},
        sort_keys=True,
    )
    report = monitor.build_android_lsl_monitor_report(rows, required_streams=[], output_dir=tmp_path)
    monitor.write_android_lsl_monitor_artifacts(tmp_path, rows, report=report)

    result = validator.validate_run_artifact(tmp_path)

    assert result.ok is False
    failures = "\n".join(result.failures)
    assert "operator_note command signal payload is missing note" in failures
    assert "payload_json differs from command signal sample payload" in failures


def test_validator_rejects_pc_monitor_command_signal_without_token(tmp_path: Path):
    rows = [
        monitor.build_android_lsl_monitor_row(
            stream_key="command_signals",
            sample=_command_signal_sample(command_id="cmd-no-token", command="pause", payload={"package_id": "pkg-001"}),
            lsl_timestamp=2.3,
        ),
    ]
    report = monitor.build_android_lsl_monitor_report(rows, required_streams=[], output_dir=tmp_path)
    monitor.write_android_lsl_monitor_artifacts(tmp_path, rows, report=report)

    result = validator.validate_run_artifact(tmp_path)

    assert result.ok is False
    assert "command signal payload is missing the pairing token" in "\n".join(result.failures)


def test_validator_rejects_pc_monitor_stream_description_drift(tmp_path: Path):
    rows = [
        monitor.build_android_lsl_monitor_row(
            stream_key="rich_markers",
            sample=_rich_marker_sample(event_type="block_start", event_code="10"),
            lsl_timestamp=1.0,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="numeric_triggers",
            sample=[10],
            lsl_timestamp=1.1,
        ),
        monitor.build_android_lsl_monitor_row(
            stream_key="command_signals",
            sample=_command_signal_sample(command_id="cmd-4", command="pause"),
            lsl_timestamp=1.2,
        ),
    ]
    report = monitor.build_android_lsl_monitor_report(rows, required_streams=[], output_dir=tmp_path)
    report["status"]["stream_descriptions"]["command_signals"]["role"] = "outlet"
    monitor.write_android_lsl_monitor_artifacts(tmp_path, rows, report=report)

    result = validator.validate_run_artifact(tmp_path, expect_native_transport=True)

    assert result.ok is False
    assert "command_signals.role" in "\n".join(result.failures)


def test_validator_requires_monitor_samples_in_strict_mode(tmp_path: Path):
    monitor.write_android_lsl_monitor_artifacts(
        tmp_path,
        [],
        report=monitor.build_android_lsl_monitor_report([], required_streams=["rich_markers"], output_dir=tmp_path),
    )

    result = validator.validate_run_artifact(tmp_path, expect_native_transport=True)

    assert result.ok is False
    assert "expected at least one PPSMarkersV2 sample" in "\n".join(result.failures)
    assert "missing required streams" in "\n".join(result.failures)


def _command_signal_sample(
    *,
    command_id: str,
    command: str,
    payload: dict[str, str] | None = None,
) -> list[str]:
    return command_to_sample(
        LSLCommandSignal(
            command_id=command_id,
            session_id="part-001",
            sender_id="pc_runner",
            command=command,
            issued_lsl_time=1.5,
            payload=payload
            or {
                "token": "secret",
                "package_id": "pkg-001",
                "participant_id": "P001",
                "target_session_id": "part-001",
                "target_part_session_id": "part-001",
                "target_session_group_id": "group-001",
                "target_part_number": "1",
            },
        )
    )


def _rich_marker_sample(*, event_type: str, event_code: str) -> list[str]:
    values = {
        "marker_version": MARKER_VERSION,
        "event_id": "evt-001",
        "event_type": event_type,
        "event_code": event_code,
        "trigger_key": f"control:{event_type}",
        "marker_name": event_type,
        "session_id": "session-001",
        "participant_id": "P001",
        "session_group_id": "group-001",
        "part_session_id": "part-001",
        "part_number": "1",
        "block_index": "1",
        "trial_uid": "trial-001",
        "sample_index": "44100",
        "timestamp_quality": "android_elapsed_realtime_plus_open_lsl_clock_offset",
        "payload_json": json.dumps({"package_id": "pkg-001"}, sort_keys=True),
    }
    return [values[label] for label in LSL_MARKER_CHANNELS]
