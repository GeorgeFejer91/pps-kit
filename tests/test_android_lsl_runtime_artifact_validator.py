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


def _status(*, native: bool) -> dict:
    return {
        "schema": "pps-android-lsl-runtime-status.v1",
        "native_transport_available": native,
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
        "privacy": {
            "default": "metadata_payload_only",
            "participant_demographics_location": "metadata_and_payload_artifacts",
            "demographics_in_stream_name": False,
        },
    }
