from __future__ import annotations

import importlib.util
import json
import sys
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
