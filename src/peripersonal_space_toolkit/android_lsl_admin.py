"""PC-side LSL administration commands for Android phone-owned PPS runs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import time
import uuid
from typing import Any

from .lsl_command_ack import (
    ACK_SCHEMA,
    COMMAND_SCHEMA,
    LSL_ACK_CHANNELS,
    LSL_ACK_SOURCE_ID_PREFIX,
    LSL_ACK_STREAM_NAME,
    LSL_ACK_STREAM_TYPE,
    LSL_COMMAND_CHANNELS,
    LSL_COMMAND_SOURCE_ID_PREFIX,
    LSL_COMMAND_STREAM_NAME,
    LSL_COMMAND_STREAM_TYPE,
    LSLCommandAck,
    LSLCommandAckError,
    LSLCommandAckInlet,
    LSLCommandOutlet,
    LSLCommandSignal,
    ack_to_sample,
    command_to_sample,
)


PC_ANDROID_LSL_ADMIN_ROW_SCHEMA = "pps-pc-android-lsl-admin-command-row.v1"
PC_ANDROID_LSL_ADMIN_STATUS_SCHEMA = "pps-pc-android-lsl-admin-status.v1"
PC_ANDROID_LSL_ADMIN_OUTBOX = "pc_android_lsl_command_outbox.jsonl"
PC_ANDROID_LSL_ADMIN_STATUS = "pc_android_lsl_admin_status.json"

ANDROID_ADMIN_COMMANDS = (
    "start_experiment",
    "start_part",
    "pause",
    "resume",
    "continue_instruction",
    "stop_after_block",
    "request_snapshot",
    "operator_note",
)


@dataclass(frozen=True)
class AndroidLslAdminSendResult:
    row: dict[str, Any]
    outbox_path: Path | None = None
    status_path: Path | None = None

    @property
    def ok(self) -> bool:
        return bool(self.row.get("ok"))


def build_android_lsl_admin_payload(
    *,
    token: str,
    target_session_id: str = "",
    package_id: str = "",
    participant_id: str = "",
    target_part_session_id: str = "",
    target_session_group_id: str = "",
    part_number: str = "",
    requested_by: str = "pc_runner_lsl_admin",
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(extra_payload or {})
    payload.update(
        {
            "token": str(token),
            "target_session_id": str(target_session_id or payload.get("target_session_id", "")),
            "package_id": str(package_id or payload.get("package_id", "")),
            "participant_id": str(participant_id or payload.get("participant_id", "")),
            "target_part_session_id": str(target_part_session_id or payload.get("target_part_session_id", "")),
            "target_session_group_id": str(target_session_group_id or payload.get("target_session_group_id", "")),
            "target_part_number": str(part_number or payload.get("target_part_number", "")),
            "requested_by": requested_by,
            "current_pc_source_behavior": "pc_native_lsl_admin_with_local_outbox",
        }
    )
    return payload


def build_android_lsl_admin_row(
    *,
    signal: LSLCommandSignal,
    package_id: str = "",
    participant_id: str = "",
    command_stream_name: str = LSL_COMMAND_STREAM_NAME,
    ack_stream_name: str = LSL_ACK_STREAM_NAME,
    consumer_ready: bool = False,
    native_lsl_sent: bool = False,
    ack: LSLCommandAck | None = None,
    ack_error: str = "",
    require_ack: bool = False,
) -> dict[str, Any]:
    command_sample = command_to_sample(signal)
    ack_sample = ack_to_sample(ack) if ack is not None else []
    ack_valid = ack is not None and not ack_error
    ok = bool(native_lsl_sent and (ack is not None or not require_ack))
    if ack is not None:
        if ack_error:
            status = "invalid_ack"
            reason = ack_error
            ok = False
        else:
            status = f"ack_{ack.status or 'received'}"
            reason = ack.reason
            ok = ok and ack.status == "applied"
    elif native_lsl_sent and require_ack:
        status = "missing_ack"
        reason = ack_error or "No matching PPSCommandAcksV1 sample received."
    elif native_lsl_sent:
        status = "sent_no_ack"
        reason = ack_error
    else:
        status = "send_failed"
        reason = ack_error or "Command was not sent over LSL."
    row = {
        "schema": PC_ANDROID_LSL_ADMIN_ROW_SCHEMA,
        "ok": ok,
        "status": status,
        "reason": reason,
        "command_id": signal.command_id,
        "command": signal.command,
        "target_session_id": signal.session_id,
        "target_part_session_id": signal.payload.get("target_part_session_id", ""),
        "target_session_group_id": signal.payload.get("target_session_group_id", ""),
        "target_part_number": signal.payload.get("target_part_number", ""),
        "sender_id": signal.sender_id,
        "package_id": package_id or signal.payload.get("package_id", ""),
        "participant_id": participant_id or signal.payload.get("participant_id", ""),
        "pc_unix_ms": int(time.time() * 1000),
        "pc_perf_counter_s": time.perf_counter(),
        "native_transport": "liblsl",
        "command_stream": command_stream_name,
        "ack_stream": ack_stream_name,
        "consumer_ready": bool(consumer_ready),
        "native_lsl_sent": bool(native_lsl_sent),
        "ack_required": bool(require_ack),
        "ack_received": ack is not None,
        "ack_status": ack.status if ack is not None else "",
        "ack_reason": ack.reason if ack is not None else "",
        "command_channels": list(LSL_COMMAND_CHANNELS),
        "ack_channels": list(LSL_ACK_CHANNELS),
        "command_sample": command_sample,
        "ack_sample": ack_sample,
        "payload": dict(signal.payload),
    }
    if ack is not None:
        row.update(
            {
                "ack_valid": ack_valid,
                "ack_validation_status": "valid_ack" if ack_valid else "invalid_ack",
                "ack_validation_reason": "" if ack_valid else ack_error,
            }
        )
    return row


def send_android_lsl_command(
    *,
    target_session_id: str,
    token: str,
    command: str,
    package_id: str = "",
    participant_id: str = "",
    target_part_session_id: str = "",
    target_session_group_id: str = "",
    part_number: str = "",
    sender_id: str = "pc_runner",
    command_id: str | None = None,
    command_stream_name: str = LSL_COMMAND_STREAM_NAME,
    ack_stream_name: str = LSL_ACK_STREAM_NAME,
    extra_payload: dict[str, Any] | None = None,
    note: str = "",
    output_dir: Path | str | None = None,
    consumer_timeout_s: float = 2.0,
    ack_timeout_s: float = 1.5,
    require_ack: bool = False,
) -> AndroidLslAdminSendResult:
    if command not in ANDROID_ADMIN_COMMANDS:
        raise ValueError(f"Unsupported Android LSL admin command: {command}")
    clean_session = str(target_session_id).strip()
    clean_token = str(token).strip()
    if not clean_session:
        raise ValueError("target_session_id is required.")
    if not clean_token:
        raise ValueError("token is required for Android LSL admin commands.")

    payload_extra = dict(extra_payload or {})
    clean_note = str(note or "").strip()
    if clean_note:
        payload_extra["note"] = clean_note
    if command == "operator_note" and not str(payload_extra.get("note") or "").strip():
        raise ValueError("operator_note requires --note or a payload_json note.")

    payload = build_android_lsl_admin_payload(
        token=clean_token,
        target_session_id=clean_session,
        package_id=package_id,
        participant_id=participant_id,
        target_part_session_id=target_part_session_id,
        target_session_group_id=target_session_group_id,
        part_number=part_number,
        extra_payload=payload_extra,
    )
    native_lsl_sent = False
    consumer_ready = False
    ack: LSLCommandAck | None = None
    ack_error = ""
    signal = LSLCommandSignal(
        command_id=str(command_id or uuid.uuid4()),
        session_id=clean_session,
        sender_id=sender_id,
        command=command,
        issued_lsl_time=time.perf_counter(),
        payload=payload,
    )
    try:
        outlet = LSLCommandOutlet(
            session_id=clean_session,
            sender_id=sender_id,
            stream_name=command_stream_name,
            max_buffered=1,
        )
        consumer_ready = outlet.wait_for_consumers(float(consumer_timeout_s))
        signal = outlet.send(command, payload=payload, command_id=signal.command_id)
        native_lsl_sent = True
        ack = _wait_for_ack(
            command_id=signal.command_id,
            ack_stream_name=ack_stream_name,
            timeout_s=ack_timeout_s,
        )
        if ack is not None:
            ack_error = _validate_ack_for_signal(signal, ack)
    except Exception as exc:  # noqa: BLE001 - persisted in the admin row for field debugging.
        ack_error = str(exc)

    if native_lsl_sent and ack is None and not ack_error and ack_timeout_s > 0:
        ack_error = "No matching command ack received before timeout."
    row = build_android_lsl_admin_row(
        signal=signal,
        package_id=package_id,
        participant_id=participant_id,
        command_stream_name=command_stream_name,
        ack_stream_name=ack_stream_name,
        consumer_ready=consumer_ready,
        native_lsl_sent=native_lsl_sent,
        ack=ack,
        ack_error=ack_error,
        require_ack=require_ack,
    )
    outbox_path = None
    status_path = None
    if output_dir is not None:
        outbox_path, status_path = write_android_lsl_admin_artifacts(Path(output_dir), row)
        row["outbox_path"] = str(outbox_path)
        row["runtime_status_path"] = str(status_path)
    return AndroidLslAdminSendResult(row=row, outbox_path=outbox_path, status_path=status_path)


def write_android_lsl_admin_artifacts(output_dir: Path, row: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outbox_path = output_dir / PC_ANDROID_LSL_ADMIN_OUTBOX
    with outbox_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    status = android_lsl_admin_status(row=row)
    status_path = output_dir / PC_ANDROID_LSL_ADMIN_STATUS
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return outbox_path, status_path


def android_lsl_admin_status(row: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": PC_ANDROID_LSL_ADMIN_STATUS_SCHEMA,
        "role": "pc_android_lsl_admin",
        "native_transport": "liblsl",
        "current_pc_source_behavior": "pc_native_lsl_admin_with_local_outbox",
        "streams": {
            "command_signals": LSL_COMMAND_STREAM_NAME,
            "command_acks": LSL_ACK_STREAM_NAME,
        },
        "stream_descriptions": pc_android_lsl_admin_stream_descriptions(row=row),
        "command_protocol": {
            "command_schema": COMMAND_SCHEMA,
            "ack_schema": ACK_SCHEMA,
            "command_channels": list(LSL_COMMAND_CHANNELS),
            "ack_channels": list(LSL_ACK_CHANNELS),
            "supported_commands": list(ANDROID_ADMIN_COMMANDS),
            "token_required": True,
            "token_payload_fields": ["token", "companion_token"],
        },
    }


def pc_android_lsl_admin_stream_descriptions(row: dict[str, Any] | None = None) -> dict[str, Any]:
    target_session_id = str((row or {}).get("target_session_id") or "")
    sender_id = str((row or {}).get("sender_id") or "")
    command_source_id = ""
    if target_session_id and sender_id:
        command_source_id = f"{LSL_COMMAND_SOURCE_ID_PREFIX}-{target_session_id}-{sender_id}"
    return {
        "schema": "pps-android-lsl-stream-descriptions.v1",
        "runtime_authority": "pc_runner",
        "role": "pc_android_lsl_admin",
        "native_transport": "liblsl",
        "target_session_id": target_session_id,
        "sender_id": sender_id,
        "privacy": {
            "default": "metadata_payload_only",
            "demographics_in_stream_name": False,
            "participant_demographics_location": "metadata_and_payload_artifacts",
        },
        "command_signals": {
            "name": str((row or {}).get("command_stream") or LSL_COMMAND_STREAM_NAME),
            "type": LSL_COMMAND_STREAM_TYPE,
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(LSL_COMMAND_CHANNELS),
            "nominal_srate_hz": 0.0,
            **({"source_id": command_source_id} if command_source_id else {"source_id_pattern": f"{LSL_COMMAND_SOURCE_ID_PREFIX}-*-*"}),
            "channel_labels": list(LSL_COMMAND_CHANNELS),
            "token_required": True,
        },
        "command_acks": {
            "name": str((row or {}).get("ack_stream") or LSL_ACK_STREAM_NAME),
            "type": LSL_ACK_STREAM_TYPE,
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_ACK_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_pattern": f"{LSL_ACK_SOURCE_ID_PREFIX}-*-*",
            "channel_labels": list(LSL_ACK_CHANNELS),
        },
    }


def _wait_for_ack(*, command_id: str, ack_stream_name: str, timeout_s: float) -> LSLCommandAck | None:
    timeout = max(0.0, float(timeout_s))
    if timeout <= 0.0:
        return None
    deadline = time.perf_counter() + timeout
    last_error: Exception | None = None
    while time.perf_counter() <= deadline:
        remaining = max(0.0, deadline - time.perf_counter())
        try:
            inlet = LSLCommandAckInlet.resolve(stream_name=ack_stream_name, timeout_s=min(0.25, remaining))
            return inlet.wait_for(command_id, timeout_s=max(0.0, deadline - time.perf_counter()))
        except LSLCommandAckError as exc:
            last_error = exc
            time.sleep(min(0.05, remaining))
    if last_error is not None:
        return None
    return None


def _validate_ack_for_signal(signal: LSLCommandSignal, ack: LSLCommandAck) -> str:
    if ack.command_id != signal.command_id:
        return "Received command ack id does not match the sent command id."
    if ack.session_id != signal.session_id:
        return "Received command ack session_id does not match the sent command session_id."
    if ack.status not in {"applied", "rejected"}:
        return "Received command ack status is not recognized."
    payload = dict(ack.payload or {})
    if str(payload.get("token") or payload.get("companion_token") or "").strip():
        return "Received command ack payload echoed the pairing token."
    receiver_role = str(payload.get("receiver_role") or "").strip()
    if not receiver_role:
        return "Received command ack payload is missing receiver_role."
    if receiver_role != "runner":
        return "Received command ack payload receiver_role must be runner."
    payload_command = str(payload.get("command") or "").strip()
    if not payload_command:
        return "Received command ack payload is missing command."
    if payload_command != signal.command:
        return "Received command ack payload command does not match the sent command."
    expected_payload = dict(signal.payload or {})
    identity_fields = (
        "package_id",
        "participant_id",
        "target_part_session_id",
        "target_session_group_id",
        "target_part_number",
        "requested_by",
        "current_pc_source_behavior",
    )
    for field in identity_fields:
        expected = str(expected_payload.get(field) or "").strip()
        observed = str(payload.get(field) or "").strip()
        if not expected:
            continue
        if not observed:
            return f"Received command ack payload is missing {field}."
        if observed != expected:
            return f"Received command ack payload {field} does not match the sent command."
    target_session = str(payload.get("target_session_id") or "").strip()
    if not target_session:
        return "Received command ack payload is missing target_session_id."
    if target_session != signal.session_id:
        return "Received command ack payload target_session_id does not match the sent command."
    return ""


def _json_payload(value: str) -> dict[str, Any]:
    if not value:
        return {}
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("--payload-json must decode to an object")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=ANDROID_ADMIN_COMMANDS)
    parser.add_argument("--session-id", required=True, help="Android target session id, part_session_id, session_group_id, or package id.")
    parser.add_argument("--token", required=True, help="Pairing token for the Android receiver.")
    parser.add_argument("--package-id", default="")
    parser.add_argument("--participant-id", default="")
    parser.add_argument("--target-part-session-id", default="")
    parser.add_argument("--target-session-group-id", default="")
    parser.add_argument("--part-number", default="")
    parser.add_argument("--sender-id", default="pc_runner")
    parser.add_argument("--command-id", default="")
    parser.add_argument("--payload-json", type=_json_payload, default={})
    parser.add_argument("--note", default="", help="Operator note text for the operator_note command.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/android_lsl_admin"))
    parser.add_argument("--consumer-timeout-s", type=float, default=2.0)
    parser.add_argument("--ack-timeout-s", type=float, default=1.5)
    parser.add_argument("--require-ack", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = send_android_lsl_command(
            target_session_id=args.session_id,
            token=args.token,
            command=args.command,
            package_id=args.package_id,
            participant_id=args.participant_id,
            target_part_session_id=args.target_part_session_id,
            target_session_group_id=args.target_session_group_id,
            part_number=args.part_number,
            sender_id=args.sender_id,
            command_id=args.command_id or None,
            extra_payload=args.payload_json,
            note=args.note,
            output_dir=args.output_dir,
            consumer_timeout_s=args.consumer_timeout_s,
            ack_timeout_s=args.ack_timeout_s,
            require_ack=args.require_ack,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result.row, indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
