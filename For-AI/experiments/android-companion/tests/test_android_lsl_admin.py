from __future__ import annotations

import json

import pytest

from peripersonal_space_toolkit import android_lsl_admin as admin
from peripersonal_space_toolkit.lsl_command_ack import (
    ACK_SCHEMA,
    LSLCommandAck,
    LSLCommandSignal,
    ack_to_sample,
)


class _FakeCommandOutlet:
    sent_signals: list[LSLCommandSignal] = []
    wait_result = True

    def __init__(self, *, session_id: str, sender_id: str, stream_name: str, max_buffered: int):
        self.session_id = session_id
        self.sender_id = sender_id
        self.stream_name = stream_name
        self.max_buffered = max_buffered

    def wait_for_consumers(self, _timeout_s: float) -> bool:
        return self.wait_result

    def local_clock(self) -> float:
        return 10.0

    def send(self, command: str, *, payload: dict, command_id: str, issued_lsl_time=None) -> LSLCommandSignal:
        signal = LSLCommandSignal(
            command_id=command_id,
            session_id=self.session_id,
            sender_id=self.sender_id,
            command=command,
            issued_lsl_time=issued_lsl_time or self.local_clock(),
            payload=payload,
        )
        self.sent_signals.append(signal)
        return signal


class _FakeAckInlet:
    ack: LSLCommandAck | None = None

    @classmethod
    def resolve(cls, *, stream_name: str, timeout_s: float):
        return cls()

    def wait_for(self, command_id: str, *, timeout_s: float) -> LSLCommandAck | None:
        if self.ack is None:
            return None
        if self.ack.command_id != command_id:
            return None
        return self.ack


def test_build_android_lsl_admin_payload_keeps_token_in_command_payload():
    payload = admin.build_android_lsl_admin_payload(
        token="secret",
        target_session_id="part-001",
        package_id="pkg-001",
        participant_id="P001",
        target_part_session_id="part-001",
        target_session_group_id="group-001",
        part_number="1",
        extra_payload={"note": "hello"},
    )

    assert payload["token"] == "secret"
    assert payload["target_session_id"] == "part-001"
    assert payload["package_id"] == "pkg-001"
    assert payload["participant_id"] == "P001"
    assert payload["target_part_session_id"] == "part-001"
    assert payload["target_session_group_id"] == "group-001"
    assert payload["target_part_number"] == "1"
    assert payload["note"] == "hello"
    assert payload["current_pc_source_behavior"] == "pc_native_lsl_admin_with_local_outbox"


def test_send_android_lsl_command_writes_auditable_ack_row(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-1",
        session_id="part-001",
        receiver_id="android_phone",
        status="applied",
        reason="starting_phone_run",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={
            "receiver_role": "runner",
            "command": "start_experiment",
            "package_id": "pkg-001",
            "participant_id": "P001",
            "target_session_id": "part-001",
            "target_part_session_id": "part-001",
            "target_session_group_id": "group-001",
            "target_part_number": "1",
            "requested_by": "pc_runner_lsl_admin",
            "current_pc_source_behavior": "pc_native_lsl_admin_with_local_outbox",
            "state_changed": True,
        },
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="start_experiment",
        package_id="pkg-001",
        participant_id="P001",
        target_part_session_id="part-001",
        target_session_group_id="group-001",
        part_number="1",
        command_id="cmd-1",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is True
    assert result.row["status"] == "ack_applied"
    assert result.row["native_lsl_sent"] is True
    assert result.row["ack_received"] is True
    assert result.row["ack_valid"] is True
    assert result.row["ack_validation_status"] == "valid_ack"
    assert result.row["ack_validation_reason"] == ""
    assert result.row["command_sample"][0] == "pps-lsl-command.v1"
    assert result.row["command_sample"][1] == "cmd-1"
    assert result.row["command_sample"][2] == "part-001"
    command_payload = json.loads(result.row["command_sample"][6])
    assert command_payload["token"] == "secret"
    assert command_payload["target_session_id"] == "part-001"
    assert command_payload["target_part_session_id"] == "part-001"
    assert command_payload["target_session_group_id"] == "group-001"
    assert command_payload["target_part_number"] == "1"
    assert result.row["target_part_session_id"] == "part-001"
    assert result.row["target_session_group_id"] == "group-001"
    assert result.row["target_part_number"] == "1"
    assert result.row["ack_sample"] == ack_to_sample(_FakeAckInlet.ack)
    outbox_rows = (tmp_path / admin.PC_ANDROID_LSL_ADMIN_OUTBOX).read_text(encoding="utf-8").strip().splitlines()
    assert len(outbox_rows) == 1
    assert json.loads(outbox_rows[0])["command_id"] == "cmd-1"
    status = json.loads((tmp_path / admin.PC_ANDROID_LSL_ADMIN_STATUS).read_text(encoding="utf-8"))
    assert status["schema"] == admin.PC_ANDROID_LSL_ADMIN_STATUS_SCHEMA
    descriptions = status["stream_descriptions"]
    assert descriptions["schema"] == "pps-android-lsl-stream-descriptions.v1"
    assert descriptions["role"] == "pc_android_lsl_admin"
    assert descriptions["privacy"]["demographics_in_stream_name"] is False
    assert descriptions["command_signals"]["role"] == "outlet"
    assert descriptions["command_signals"]["source_id"] == "pps-command-signals-v1-part-001-pc_runner"
    assert descriptions["command_signals"]["channel_labels"] == list(admin.LSL_COMMAND_CHANNELS)
    assert descriptions["command_acks"]["role"] == "inlet"
    assert descriptions["command_acks"]["source_id_pattern"] == "pps-command-acks-v1-*-*"
    assert descriptions["command_acks"]["channel_labels"] == list(admin.LSL_ACK_CHANNELS)


def test_send_android_lsl_command_records_handler_rejection_as_valid_ack(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-handler-reject",
        session_id="part-001",
        receiver_id="android_phone",
        status="rejected",
        reason="no_active_phone_block_to_pause",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={
            "schema": "pps-android-phone-command-handler-rejection.v1",
            "receiver_role": "runner",
            "status": "rejected",
            "reason": "no_active_phone_block_to_pause",
            "rejected_before_handler": False,
            "handler_completed": True,
            "command": "pause",
            "package_id": "pkg-001",
            "participant_id": "P001",
            "session_id": "phone-session-001",
            "part_session_id": "part-001",
            "session_group_id": "group-001",
            "part_number": "1",
            "target_session_id": "part-001",
            "target_part_session_id": "part-001",
            "target_session_group_id": "group-001",
            "target_part_number": "1",
            "requested_by": "pc_runner_lsl_admin",
            "current_pc_source_behavior": "pc_native_lsl_admin_with_local_outbox",
            "requested_session_id": "part-001",
            "requested_package_id": "pkg-001",
            "requested_participant_id": "P001",
            "requested_target_session_id": "part-001",
            "requested_target_part_session_id": "part-001",
            "requested_target_session_group_id": "group-001",
            "requested_target_part_number": "1",
            "handler_payload_schema": "pps-android-phone-runtime-command-state.v1",
            "handler_payload": {
                "schema": "pps-android-phone-runtime-command-state.v1",
                "command": "pause",
                "run_id": "phone-run-001",
            },
            "supported_commands": ["start_experiment", "pause", "resume"],
        },
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="pause",
        command_id="cmd-handler-reject",
        package_id="pkg-001",
        participant_id="P001",
        target_part_session_id="part-001",
        target_session_group_id="group-001",
        part_number="1",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is False
    assert result.row["status"] == "ack_rejected"
    assert result.row["reason"] == "no_active_phone_block_to_pause"
    assert result.row["ack_received"] is True
    assert result.row["ack_valid"] is True
    assert result.row["ack_validation_status"] == "valid_ack"
    assert result.row["ack_validation_reason"] == ""
    assert result.row["ack_sample"] == ack_to_sample(_FakeAckInlet.ack)


def test_send_android_lsl_command_can_require_ack(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = None
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="pause",
        command_id="cmd-2",
        output_dir=tmp_path,
        require_ack=True,
        ack_timeout_s=0.01,
    )

    assert result.ok is False
    assert result.row["status"] == "missing_ack"
    assert result.row["native_lsl_sent"] is True
    assert result.row["ack_received"] is False


def test_send_android_lsl_command_rejects_ack_session_drift(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-session-drift",
        session_id="other-part",
        receiver_id="android_phone",
        status="applied",
        reason="wrong_session",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={"command": "pause", "target_session_id": "other-part"},
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="pause",
        command_id="cmd-session-drift",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is False
    assert result.row["status"] == "invalid_ack"
    assert result.row["ack_received"] is True
    assert result.row["ack_sample"] == ack_to_sample(_FakeAckInlet.ack)
    assert result.row["ack_valid"] is False
    assert result.row["ack_validation_status"] == "invalid_ack"
    assert "session_id does not match" in result.row["reason"]


def test_send_android_lsl_command_rejects_ack_token_echo(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-token-echo",
        session_id="part-001",
        receiver_id="android_phone",
        status="applied",
        reason="bad_ack",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={"command": "pause", "token": "secret"},
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="pause",
        command_id="cmd-token-echo",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is False
    assert result.row["status"] == "invalid_ack"
    assert result.row["ack_received"] is True
    assert result.row["ack_valid"] is False
    assert result.row["ack_validation_status"] == "invalid_ack"
    assert "pairing token" in result.row["reason"]


def test_send_android_lsl_command_rejects_ack_receiver_role_drift(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-role-drift",
        session_id="part-001",
        receiver_id="android_phone",
        status="applied",
        reason="bad_ack",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={"receiver_role": "controller", "command": "pause", "target_session_id": "part-001"},
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="pause",
        command_id="cmd-role-drift",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is False
    assert result.row["status"] == "invalid_ack"
    assert result.row["ack_received"] is True
    assert result.row["ack_valid"] is False
    assert result.row["ack_validation_status"] == "invalid_ack"
    assert "receiver_role must be runner" in result.row["reason"]


def test_send_android_lsl_command_rejects_missing_ack_identity(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-missing-identity",
        session_id="part-001",
        receiver_id="android_phone",
        status="applied",
        reason="missing_package",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={
            "receiver_role": "runner",
            "command": "pause",
            "target_session_id": "part-001",
            "requested_by": "pc_runner_lsl_admin",
            "current_pc_source_behavior": "pc_native_lsl_admin_with_local_outbox",
        },
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="pause",
        command_id="cmd-missing-identity",
        package_id="pkg-001",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is False
    assert result.row["status"] == "invalid_ack"
    assert result.row["ack_received"] is True
    assert result.row["ack_valid"] is False
    assert result.row["ack_validation_status"] == "invalid_ack"
    assert "missing package_id" in result.row["reason"]


def test_send_android_lsl_command_rejects_unrecognized_ack_status(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-unknown-status",
        session_id="part-001",
        receiver_id="android_phone",
        status="queued",
        reason="ambiguous",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={"command": "pause", "target_session_id": "part-001"},
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="pause",
        command_id="cmd-unknown-status",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is False
    assert result.row["status"] == "invalid_ack"
    assert result.row["ack_valid"] is False
    assert result.row["ack_validation_status"] == "invalid_ack"
    assert "status is not recognized" in result.row["ack_validation_reason"]


def test_send_android_lsl_operator_note_requires_note():
    with pytest.raises(ValueError, match="operator_note requires"):
        admin.send_android_lsl_command(
            target_session_id="part-001",
            token="secret",
            command="operator_note",
        )


def test_android_lsl_admin_cli_rejects_operator_note_without_note(capsys):
    with pytest.raises(SystemExit) as exc_info:
        admin.main(["operator_note", "--session-id", "part-001", "--token", "secret"])

    assert exc_info.value.code == 2
    assert "operator_note requires" in capsys.readouterr().err


def test_send_android_lsl_operator_note_writes_note_payload(tmp_path, monkeypatch):
    _FakeCommandOutlet.sent_signals.clear()
    _FakeAckInlet.ack = LSLCommandAck(
        command_id="cmd-note-1",
        session_id="part-001",
        receiver_id="android_phone",
        status="applied",
        reason="operator_note_recorded",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={
            "receiver_role": "runner",
            "command": "operator_note",
            "target_session_id": "part-001",
            "requested_by": "pc_runner_lsl_admin",
            "current_pc_source_behavior": "pc_native_lsl_admin_with_local_outbox",
            "note": "participant asked for a pause",
        },
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="operator_note",
        command_id="cmd-note-1",
        note="participant asked for a pause",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is True
    assert result.row["command"] == "operator_note"
    payload = json.loads(result.row["command_sample"][6])
    assert payload["token"] == "secret"
    assert payload["note"] == "participant asked for a pause"
    assert result.row["payload"]["note"] == "participant asked for a pause"


def test_android_lsl_admin_status_matches_command_ack_protocol():
    status = admin.android_lsl_admin_status()

    assert status["streams"]["command_signals"] == "PPSCommandSignalsV1"
    assert status["streams"]["command_acks"] == "PPSCommandAcksV1"
    assert status["stream_descriptions"]["command_signals"]["source_id_pattern"] == "pps-command-signals-v1-*-*"
    assert status["stream_descriptions"]["command_acks"]["source_id_pattern"] == "pps-command-acks-v1-*-*"
    assert status["command_protocol"]["command_schema"] == "pps-lsl-command.v1"
    assert status["command_protocol"]["ack_schema"] == ACK_SCHEMA
    assert status["command_protocol"]["token_required"] is True
    assert "start_experiment" in status["command_protocol"]["supported_commands"]
