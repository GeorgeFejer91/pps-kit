"""Low-latency LSL command/acknowledgement helpers.

The experiment runner uses LSL as a timestamped evidence bus, not as its timing
authority.  This module provides a small bidirectional command pattern for labs
that need a sender/receiver handshake over LSL: one irregular command stream and
one irregular acknowledgement stream, both keyed by a command id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import time
import uuid
from typing import Any, Callable


COMMAND_SCHEMA = "pps-lsl-command.v1"
ACK_SCHEMA = "pps-lsl-command-ack.v1"
LSL_COMMAND_STREAM_NAME = "PPSCommandSignalsV1"
LSL_ACK_STREAM_NAME = "PPSCommandAcksV1"
LSL_COMMAND_STREAM_TYPE = "CommandSignals"
LSL_ACK_STREAM_TYPE = "CommandAcks"
LSL_COMMAND_SOURCE_ID_PREFIX = "pps-command-signals-v1"
LSL_ACK_SOURCE_ID_PREFIX = "pps-command-acks-v1"
LSL_COMMAND_CHANNELS = [
    "schema",
    "command_id",
    "session_id",
    "sender_id",
    "command",
    "issued_lsl_time",
    "payload_json",
]
LSL_ACK_CHANNELS = [
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
]


class LSLCommandAckError(RuntimeError):
    """Raised when the optional LSL command/ack protocol cannot operate."""


@dataclass(frozen=True)
class LSLCommandSignal:
    command_id: str
    session_id: str
    sender_id: str
    command: str
    issued_lsl_time: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LSLCommandApplicationResult:
    status: str = "applied"
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LSLCommandAck:
    command_id: str
    session_id: str
    receiver_id: str
    status: str
    reason: str
    received_lsl_time: float
    applied_lsl_time: float
    ack_lsl_time: float
    payload: dict[str, Any] = field(default_factory=dict)


def command_to_sample(signal: LSLCommandSignal) -> list[str]:
    return [
        COMMAND_SCHEMA,
        signal.command_id,
        signal.session_id,
        signal.sender_id,
        signal.command,
        f"{float(signal.issued_lsl_time):.9f}",
        json.dumps(signal.payload, sort_keys=True, ensure_ascii=False),
    ]


def command_from_sample(sample: list[Any]) -> LSLCommandSignal:
    values = [str(value) for value in sample]
    if len(values) != len(LSL_COMMAND_CHANNELS) or values[0] != COMMAND_SCHEMA:
        raise LSLCommandAckError("Unsupported LSL command sample schema.")
    return LSLCommandSignal(
        command_id=values[1],
        session_id=values[2],
        sender_id=values[3],
        command=values[4],
        issued_lsl_time=_as_float(values[5], default=0.0),
        payload=_json_object(values[6]),
    )


def ack_to_sample(ack: LSLCommandAck) -> list[str]:
    return [
        ACK_SCHEMA,
        ack.command_id,
        ack.session_id,
        ack.receiver_id,
        ack.status,
        ack.reason,
        f"{float(ack.received_lsl_time):.9f}",
        f"{float(ack.applied_lsl_time):.9f}",
        f"{float(ack.ack_lsl_time):.9f}",
        json.dumps(ack.payload, sort_keys=True, ensure_ascii=False),
    ]


def ack_from_sample(sample: list[Any]) -> LSLCommandAck:
    values = [str(value) for value in sample]
    if len(values) != len(LSL_ACK_CHANNELS) or values[0] != ACK_SCHEMA:
        raise LSLCommandAckError("Unsupported LSL command ack sample schema.")
    return LSLCommandAck(
        command_id=values[1],
        session_id=values[2],
        receiver_id=values[3],
        status=values[4],
        reason=values[5],
        received_lsl_time=_as_float(values[6], default=0.0),
        applied_lsl_time=_as_float(values[7], default=0.0),
        ack_lsl_time=_as_float(values[8], default=0.0),
        payload=_json_object(values[9]),
    )


class LSLCommandOutlet:
    """Send command samples on a pre-created irregular LSL stream."""

    def __init__(
        self,
        *,
        session_id: str,
        sender_id: str,
        stream_name: str = LSL_COMMAND_STREAM_NAME,
        source_id: str | None = None,
        max_buffered: int = 1,
    ) -> None:
        pylsl = _load_pylsl()
        self.session_id = str(session_id)
        self.sender_id = str(sender_id)
        self.source_id = source_id or f"{LSL_COMMAND_SOURCE_ID_PREFIX}-{self.session_id}-{self.sender_id}"
        self._local_clock = getattr(pylsl, "local_clock", time.perf_counter)
        info = _stream_info(
            pylsl,
            name=stream_name,
            stream_type=LSL_COMMAND_STREAM_TYPE,
            channels=LSL_COMMAND_CHANNELS,
            schema=COMMAND_SCHEMA,
            source_id=self.source_id,
            session_id=self.session_id,
        )
        self._outlet = _stream_outlet(pylsl, info, max_buffered=max_buffered)

    def local_clock(self) -> float:
        return _local_clock_value(self._local_clock)

    def wait_for_consumers(self, timeout_s: float = 0.0) -> bool:
        wait = getattr(self._outlet, "wait_for_consumers", None)
        if wait is None:
            return True
        return bool(wait(float(timeout_s)))

    def send(
        self,
        command: str,
        *,
        payload: dict[str, Any] | None = None,
        command_id: str | None = None,
        issued_lsl_time: float | None = None,
    ) -> LSLCommandSignal:
        issued = self.local_clock() if issued_lsl_time is None else float(issued_lsl_time)
        signal = LSLCommandSignal(
            command_id=str(command_id or uuid.uuid4()),
            session_id=self.session_id,
            sender_id=self.sender_id,
            command=str(command),
            issued_lsl_time=issued,
            payload=dict(payload or {}),
        )
        _push_sample(self._outlet, command_to_sample(signal), timestamp=issued, pushthrough=True)
        return signal


class LSLCommandAckOutlet:
    """Send applied/rejected acknowledgements on a separate LSL stream."""

    def __init__(
        self,
        *,
        session_id: str,
        receiver_id: str,
        stream_name: str = LSL_ACK_STREAM_NAME,
        source_id: str | None = None,
        max_buffered: int = 1,
    ) -> None:
        pylsl = _load_pylsl()
        self.session_id = str(session_id)
        self.receiver_id = str(receiver_id)
        self.source_id = source_id or f"{LSL_ACK_SOURCE_ID_PREFIX}-{self.session_id}-{self.receiver_id}"
        self._local_clock = getattr(pylsl, "local_clock", time.perf_counter)
        info = _stream_info(
            pylsl,
            name=stream_name,
            stream_type=LSL_ACK_STREAM_TYPE,
            channels=LSL_ACK_CHANNELS,
            schema=ACK_SCHEMA,
            source_id=self.source_id,
            session_id=self.session_id,
        )
        self._outlet = _stream_outlet(pylsl, info, max_buffered=max_buffered)

    def local_clock(self) -> float:
        return _local_clock_value(self._local_clock)

    def wait_for_consumers(self, timeout_s: float = 0.0) -> bool:
        wait = getattr(self._outlet, "wait_for_consumers", None)
        if wait is None:
            return True
        return bool(wait(float(timeout_s)))

    def send_ack(
        self,
        signal: LSLCommandSignal,
        *,
        result: LSLCommandApplicationResult | dict[str, Any] | None = None,
        received_lsl_time: float | None = None,
        applied_lsl_time: float | None = None,
        ack_lsl_time: float | None = None,
    ) -> LSLCommandAck:
        resolved = _coerce_result(result)
        now = self.local_clock()
        received = now if received_lsl_time is None else float(received_lsl_time)
        applied = now if applied_lsl_time is None else float(applied_lsl_time)
        ack_time = self.local_clock() if ack_lsl_time is None else float(ack_lsl_time)
        ack = LSLCommandAck(
            command_id=signal.command_id,
            session_id=signal.session_id,
            receiver_id=self.receiver_id,
            status=resolved.status,
            reason=resolved.reason,
            received_lsl_time=received,
            applied_lsl_time=applied,
            ack_lsl_time=ack_time,
            payload=dict(resolved.payload or {}),
        )
        _push_sample(self._outlet, ack_to_sample(ack), timestamp=ack_time, pushthrough=True)
        return ack


class LSLCommandInlet:
    """Receive command samples from a resolved LSL stream."""

    def __init__(self, inlet: Any) -> None:
        self._inlet = inlet

    @classmethod
    def resolve(
        cls,
        *,
        source_id: str | None = None,
        stream_name: str = LSL_COMMAND_STREAM_NAME,
        timeout_s: float = 2.0,
        max_buflen: int = 1,
        max_chunklen: int = 1,
    ) -> "LSLCommandInlet":
        pylsl = _load_pylsl()
        info = _resolve_one(pylsl, source_id=source_id, stream_name=stream_name, timeout_s=timeout_s)
        return cls(_stream_inlet(pylsl, info, max_buflen=max_buflen, max_chunklen=max_chunklen))

    def pull(self, timeout_s: float = 0.0) -> LSLCommandSignal | None:
        sample, _timestamp = _pull_sample(self._inlet, timeout_s=timeout_s)
        if not sample:
            return None
        return command_from_sample(sample)

    def close(self) -> None:
        close = getattr(self._inlet, "close_stream", None)
        if close is not None:
            close()


class LSLCommandAckInlet:
    """Receive command acknowledgements from a resolved LSL stream."""

    def __init__(self, inlet: Any) -> None:
        self._inlet = inlet
        self._pending: dict[str, list[LSLCommandAck]] = {}

    @classmethod
    def resolve(
        cls,
        *,
        source_id: str | None = None,
        stream_name: str = LSL_ACK_STREAM_NAME,
        timeout_s: float = 2.0,
        max_buflen: int = 1,
        max_chunklen: int = 1,
    ) -> "LSLCommandAckInlet":
        pylsl = _load_pylsl()
        info = _resolve_one(pylsl, source_id=source_id, stream_name=stream_name, timeout_s=timeout_s)
        return cls(_stream_inlet(pylsl, info, max_buflen=max_buflen, max_chunklen=max_chunklen))

    def pull(self, timeout_s: float = 0.0) -> LSLCommandAck | None:
        sample, _timestamp = _pull_sample(self._inlet, timeout_s=timeout_s)
        if not sample:
            return None
        return ack_from_sample(sample)

    def close(self) -> None:
        close = getattr(self._inlet, "close_stream", None)
        if close is not None:
            close()

    def wait_for(self, command_id: str, *, timeout_s: float = 1.0) -> LSLCommandAck | None:
        pending = self._pending.get(str(command_id), [])
        if pending:
            return pending.pop(0)
        deadline = time.perf_counter() + max(0.0, float(timeout_s))
        while time.perf_counter() <= deadline:
            remaining = max(0.0, min(0.01, deadline - time.perf_counter()))
            ack = self.pull(timeout_s=remaining)
            if ack is not None and ack.command_id == str(command_id):
                return ack
            if ack is not None:
                self._pending.setdefault(ack.command_id, []).append(ack)
        return None


class LSLCommandAckServer:
    """Poll a command inlet, apply a handler, and emit an applied ack."""

    def __init__(
        self,
        *,
        command_inlet: LSLCommandInlet,
        ack_outlet: LSLCommandAckOutlet,
        handler: Callable[[LSLCommandSignal], LSLCommandApplicationResult | dict[str, Any] | None],
    ) -> None:
        self.command_inlet = command_inlet
        self.ack_outlet = ack_outlet
        self.handler = handler

    def poll_once(self, *, timeout_s: float = 0.0) -> LSLCommandAck | None:
        signal = self.command_inlet.pull(timeout_s=timeout_s)
        if signal is None:
            return None
        received = self.ack_outlet.local_clock()
        try:
            result = _coerce_result(self.handler(signal))
        except Exception as exc:  # noqa: BLE001 - converted to LSL rejection ack.
            result = LSLCommandApplicationResult(status="rejected", reason=str(exc), payload={"exception": type(exc).__name__})
        applied = self.ack_outlet.local_clock()
        return self.ack_outlet.send_ack(signal, result=result, received_lsl_time=received, applied_lsl_time=applied)


def _load_pylsl() -> Any:
    try:
        import pylsl  # type: ignore
    except Exception as exc:
        raise LSLCommandAckError(f"pylsl is required for LSL command/ack streams: {exc}") from exc
    return pylsl


def _stream_info(
    pylsl: Any,
    *,
    name: str,
    stream_type: str,
    channels: list[str],
    schema: str,
    source_id: str,
    session_id: str,
) -> Any:
    info = pylsl.StreamInfo(name, stream_type, len(channels), 0, "string", source_id)
    try:
        desc = info.desc()
        desc.append_child_value("schema", schema)
        desc.append_child_value("session_id", str(session_id))
        channel_root = desc.append_child("channels")
        for label in channels:
            channel = channel_root.append_child("channel")
            channel.append_child_value("label", label)
            channel.append_child_value("type", "Command")
    except Exception:
        pass
    return info


def _stream_outlet(pylsl: Any, info: Any, *, max_buffered: int) -> Any:
    try:
        return pylsl.StreamOutlet(info, chunk_size=0, max_buffered=int(max_buffered))
    except TypeError:
        try:
            return pylsl.StreamOutlet(info, 0, int(max_buffered))
        except TypeError:
            return pylsl.StreamOutlet(info)


def _stream_inlet(pylsl: Any, info: Any, *, max_buflen: int, max_chunklen: int) -> Any:
    try:
        inlet = pylsl.StreamInlet(info, max_buflen=int(max_buflen), max_chunklen=int(max_chunklen), recover=True)
    except TypeError:
        try:
            inlet = pylsl.StreamInlet(info, int(max_buflen), int(max_chunklen), True)
        except TypeError:
            inlet = pylsl.StreamInlet(info)
    try:
        inlet.open_stream(0.2)
    except Exception:
        pass
    return inlet


def _resolve_one(pylsl: Any, *, source_id: str | None, stream_name: str, timeout_s: float) -> Any:
    if source_id:
        infos = pylsl.resolve_byprop("source_id", str(source_id), 1, float(timeout_s))
    else:
        infos = pylsl.resolve_byprop("name", str(stream_name), 1, float(timeout_s))
    if not infos:
        label = f"source_id={source_id}" if source_id else f"name={stream_name}"
        raise LSLCommandAckError(f"Could not resolve LSL stream for {label}.")
    return infos[0]


def _push_sample(outlet: Any, sample: list[Any], *, timestamp: float, pushthrough: bool) -> None:
    try:
        outlet.push_sample(sample, timestamp=float(timestamp), pushthrough=bool(pushthrough))
    except TypeError:
        try:
            outlet.push_sample(sample, float(timestamp), bool(pushthrough))
        except TypeError:
            try:
                outlet.push_sample(sample, timestamp=float(timestamp))
            except TypeError:
                outlet.push_sample(sample, float(timestamp))


def _pull_sample(inlet: Any, *, timeout_s: float) -> tuple[list[Any] | None, float]:
    result = inlet.pull_sample(float(timeout_s))
    if isinstance(result, tuple) and len(result) == 2:
        sample, timestamp = result
        return sample, _as_float(timestamp, default=0.0)
    return result, 0.0


def _coerce_result(result: LSLCommandApplicationResult | dict[str, Any] | None) -> LSLCommandApplicationResult:
    if isinstance(result, LSLCommandApplicationResult):
        return result
    if isinstance(result, dict):
        payload = dict(result.get("payload") or {})
        return LSLCommandApplicationResult(
            status=str(result.get("status") or "applied"),
            reason=str(result.get("reason") or ""),
            payload=payload,
        )
    return LSLCommandApplicationResult()


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise LSLCommandAckError(f"Invalid command JSON payload: {exc}") from exc
    if not isinstance(value, dict):
        raise LSLCommandAckError("Command payload JSON must be an object.")
    return dict(value)


def _local_clock_value(clock: Callable[[], float]) -> float:
    try:
        return float(clock())
    except Exception:
        return time.perf_counter()


def _as_float(value: Any, *, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default
