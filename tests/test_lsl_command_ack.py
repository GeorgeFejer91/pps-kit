from __future__ import annotations

import sys
import types

import pytest

from peripersonal_space_toolkit.lsl_command_ack import (
    ACK_SCHEMA,
    COMMAND_SCHEMA,
    LSLCommandAck,
    LSLCommandAckError,
    LSLCommandAckInlet,
    LSLCommandAckOutlet,
    LSLCommandAckServer,
    LSLCommandApplicationResult,
    LSLCommandInlet,
    LSLCommandOutlet,
    LSLCommandSignal,
    ack_from_sample,
    ack_to_sample,
    command_from_sample,
    command_to_sample,
)


class _FakeDesc:
    def append_child_value(self, _key, _value):
        return self

    def append_child(self, _key):
        return self


class _FakeStreamInfo:
    def __init__(self, *args):
        self.args = args
        self._desc = _FakeDesc()

    def desc(self):
        return self._desc


class _FakeStreamOutlet:
    instances = []

    def __init__(self, info, *args, **kwargs):
        self.info = info
        self.args = args
        self.kwargs = kwargs
        self.samples = []
        _FakeStreamOutlet.instances.append(self)

    def push_sample(self, sample, timestamp=0.0, pushthrough=True):
        self.samples.append((sample, timestamp, pushthrough))

    def wait_for_consumers(self, _timeout):
        return True


class _FakeStreamInlet:
    def __init__(self, samples):
        self.samples = list(samples)

    def pull_sample(self, _timeout=0.0):
        if not self.samples:
            return None, 0.0
        return self.samples.pop(0)

    def open_stream(self, _timeout):
        return None


def _fake_pylsl():
    return types.SimpleNamespace(
        StreamInfo=_FakeStreamInfo,
        StreamOutlet=_FakeStreamOutlet,
        local_clock=lambda: 123.456,
    )


def test_command_and_ack_samples_round_trip():
    command = LSLCommandSignal(
        command_id="cmd-1",
        session_id="S001",
        sender_id="phone",
        command="start_part",
        issued_lsl_time=10.0,
        payload={"part_number": 1},
    )
    parsed_command = command_from_sample(command_to_sample(command))

    assert parsed_command.command_id == "cmd-1"
    assert parsed_command.command == "start_part"
    assert parsed_command.payload == {"part_number": 1}

    ack = LSLCommandAck(
        command_id=parsed_command.command_id,
        session_id=parsed_command.session_id,
        receiver_id="runner",
        status="applied",
        reason="",
        received_lsl_time=10.1,
        applied_lsl_time=10.2,
        ack_lsl_time=10.3,
        payload={"sequence": 4},
    )
    parsed_ack = ack_from_sample(ack_to_sample(ack))

    assert parsed_ack.command_id == "cmd-1"
    assert parsed_ack.status == "applied"
    assert parsed_ack.payload == {"sequence": 4}


def test_outlets_push_samples_with_lsl_pushthrough(monkeypatch):
    _FakeStreamOutlet.instances.clear()
    monkeypatch.setitem(sys.modules, "pylsl", _fake_pylsl())
    command_outlet = LSLCommandOutlet(session_id="S001", sender_id="phone")
    ack_outlet = LSLCommandAckOutlet(session_id="S001", receiver_id="runner")

    signal = command_outlet.send("continue_instruction", command_id="cmd-2")
    ack_outlet.send_ack(signal, result={"status": "applied", "payload": {"snapshot_sequence": 9}})

    command_stream, ack_stream = _FakeStreamOutlet.instances
    assert command_stream.samples[0][0][0] == COMMAND_SCHEMA
    assert command_stream.samples[0][0][1] == "cmd-2"
    assert command_stream.samples[0][2] is True
    assert ack_stream.samples[0][0][0] == ACK_SCHEMA
    assert ack_stream.samples[0][0][1] == "cmd-2"
    assert ack_stream.samples[0][2] is True


def test_ack_server_confirms_after_handler_effect(monkeypatch):
    _FakeStreamOutlet.instances.clear()
    monkeypatch.setitem(sys.modules, "pylsl", _fake_pylsl())
    command = LSLCommandOutlet(session_id="S001", sender_id="phone").send(
        "start_part",
        payload={"part_number": 2},
        command_id="cmd-3",
        issued_lsl_time=11.0,
    )
    ack_outlet = LSLCommandAckOutlet(session_id="S001", receiver_id="runner")
    inlet = LSLCommandInlet(_FakeStreamInlet([(command_to_sample(command), 11.0)]))
    server = LSLCommandAckServer(
        command_inlet=inlet,
        ack_outlet=ack_outlet,
        handler=lambda signal: {
            "status": "applied",
            "payload": {"command": signal.command, "state_changed": True},
        },
    )

    ack = server.poll_once(timeout_s=0.0)

    assert ack is not None
    assert ack.command_id == "cmd-3"
    assert ack.status == "applied"
    assert ack.payload == {"command": "start_part", "state_changed": True}
    assert _FakeStreamOutlet.instances[-1].samples[0][0][4] == "applied"


def test_ack_inlet_waits_for_matching_command_id():
    desired = [
        ACK_SCHEMA,
        "cmd-wanted",
        "S001",
        "runner",
        "applied",
        "",
        "1.0",
        "1.1",
        "1.2",
        "{}",
    ]
    other = [*desired]
    other[1] = "cmd-other"
    inlet = LSLCommandAckInlet(_FakeStreamInlet([(other, 1.0), (desired, 1.2)]))

    ack = inlet.wait_for("cmd-wanted", timeout_s=0.2)

    assert ack is not None
    assert ack.command_id == "cmd-wanted"
    assert inlet.wait_for("cmd-other", timeout_s=0.0).command_id == "cmd-other"


def test_invalid_schema_is_rejected():
    with pytest.raises(LSLCommandAckError):
        command_from_sample(["wrong"])
    with pytest.raises(LSLCommandAckError):
        ack_from_sample(["wrong"])
