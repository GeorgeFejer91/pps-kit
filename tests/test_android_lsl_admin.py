from __future__ import annotations

import json

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
        package_id="pkg-001",
        participant_id="P001",
        part_number="1",
        extra_payload={"note": "hello"},
    )

    assert payload["token"] == "secret"
    assert payload["package_id"] == "pkg-001"
    assert payload["participant_id"] == "P001"
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
        payload={"state_changed": True},
    )
    monkeypatch.setattr(admin, "LSLCommandOutlet", _FakeCommandOutlet)
    monkeypatch.setattr(admin, "LSLCommandAckInlet", _FakeAckInlet)

    result = admin.send_android_lsl_command(
        target_session_id="part-001",
        token="secret",
        command="start_experiment",
        package_id="pkg-001",
        participant_id="P001",
        command_id="cmd-1",
        output_dir=tmp_path,
        require_ack=True,
    )

    assert result.ok is True
    assert result.row["status"] == "ack_applied"
    assert result.row["native_lsl_sent"] is True
    assert result.row["ack_received"] is True
    assert result.row["command_sample"][0] == "pps-lsl-command.v1"
    assert result.row["command_sample"][1] == "cmd-1"
    assert result.row["command_sample"][2] == "part-001"
    assert json.loads(result.row["command_sample"][6])["token"] == "secret"
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
