from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path("validation_protocols/scripts/reconcile_android_command_admin_with_phone_run.py")
spec = importlib.util.spec_from_file_location("reconcile_android_command_admin_with_phone_run", SCRIPT_PATH)
assert spec and spec.loader
reconciler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = reconciler
spec.loader.exec_module(reconciler)


def test_reconcile_android_command_admin_accepts_matching_controller_and_phone_diary():
    sender = _sender_row()
    phone = _phone_command_row()

    result = reconciler.reconcile_command_admin_with_phone_run(
        [sender],
        [phone],
        sender_kind="controller",
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is True
    assert result.report["matched_command_count"] == 1
    assert result.report["reconciled_ack_pair_count"] == 1
    assert result.report["mismatch_count"] == 0


def test_reconcile_android_command_admin_loads_sender_and_phone_run_dirs(tmp_path: Path):
    sender_dir = tmp_path / "controller"
    sender_dir.mkdir()
    phone_dir = tmp_path / "phone-run"
    phone_dir.mkdir()
    sender = _sender_row()
    phone = _phone_command_row()
    (sender_dir / "phone_controller_runtime_status.json").write_text(
        json.dumps({"schema": "pps-android-controller-runtime-status.v1"}),
        encoding="utf-8",
    )
    (sender_dir / "phone_controller_command_outbox.jsonl").write_text(json.dumps(sender) + "\n", encoding="utf-8")
    _write_phone_run(phone_dir, [phone])

    sender_kind, sender_rows = reconciler.load_sender_command_artifact(sender_dir)
    phone_rows = reconciler.load_phone_command_diary(phone_dir)
    result = reconciler.reconcile_command_admin_with_phone_run(
        sender_rows,
        phone_rows,
        sender_kind=sender_kind,
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert sender_kind == "controller"
    assert result.ok is True
    assert result.report["failures"] == []


def test_reconcile_android_command_admin_accepts_pc_admin_sender_row():
    sender = _sender_row(schema=reconciler.PC_ANDROID_LSL_ADMIN_ROW_SCHEMA, sender_id="pc_runner")
    phone = _phone_command_row(sender_id="pc_runner")

    result = reconciler.reconcile_command_admin_with_phone_run(
        [sender],
        [phone],
        sender_kind="pc_admin",
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is True
    assert result.report["sender_kind"] == "pc_admin"


def test_reconcile_android_command_admin_reports_missing_phone_diary_row():
    result = reconciler.reconcile_command_admin_with_phone_run(
        [_sender_row(command_id="cmd-missing")],
        [],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    assert result.report["missing_phone_command_ids"] == ["cmd-missing"]
    assert "phone command diary is missing native rows" in "\n".join(result.report["failures"])


def test_reconcile_android_command_admin_reports_ack_payload_drift():
    phone = _phone_command_row()
    phone["ack_sample"][9] = json.dumps({"command": "resume", "package_id": "pkg-001", "run_id": "phone-run-001"})

    result = reconciler.reconcile_command_admin_with_phone_run(
        [_sender_row()],
        [phone],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    fields = {item["field"] for item in result.report["mismatches"]}
    assert "ack_sample" in fields
    assert "ack_payload" in fields


def test_reconcile_android_command_admin_reports_missing_phone_command_sample():
    phone = _phone_command_row()
    del phone["command_sample"]

    result = reconciler.reconcile_command_admin_with_phone_run(
        [_sender_row()],
        [phone],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    fields = {item["field"] for item in result.report["mismatches"]}
    assert "phone.command_sample.channel_count" in fields


def test_reconcile_android_command_admin_reports_received_command_sample_drift():
    phone = _phone_command_row()
    phone["command_sample"][4] = "resume"

    result = reconciler.reconcile_command_admin_with_phone_run(
        [_sender_row()],
        [phone],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    fields = {item["field"] for item in result.report["mismatches"]}
    assert "received_command_sample" in fields


def test_reconcile_android_command_admin_rejects_command_sample_missing_pairing_token():
    sender = _sender_row()
    sample_payload = json.loads(sender["command_sample"][6])
    sample_payload.pop("token")
    sender["command_sample"][6] = json.dumps(sample_payload, sort_keys=True)

    result = reconciler.reconcile_command_admin_with_phone_run(
        [sender],
        [_phone_command_row()],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    fields = {item["field"] for item in result.report["mismatches"]}
    assert "command_sample_payload.token_missing" in fields
    assert "sender_payload" in fields


def test_reconcile_android_command_admin_rejects_sender_payload_sample_drift():
    sender = _sender_row()
    sender["payload"]["target_part_number"] = "2"

    result = reconciler.reconcile_command_admin_with_phone_run(
        [sender],
        [_phone_command_row()],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    fields = {item["field"] for item in result.report["mismatches"]}
    assert "sender_payload" in fields


def test_reconcile_android_command_admin_rejects_ack_payload_token_echo():
    sender = _sender_row()
    phone = _phone_command_row()
    ack_payload = _ack_payload("pause")
    ack_payload["token"] = "secret"
    sender["ack_sample"] = _ack_sample("cmd-001", "pause", ack_payload)
    phone["ack_sample"] = _ack_sample("cmd-001", "pause", ack_payload)
    phone["payload"] = dict(ack_payload)

    result = reconciler.reconcile_command_admin_with_phone_run(
        [sender],
        [phone],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    fields = {item["field"] for item in result.report["mismatches"]}
    assert "sender_ack_payload.token_echo" in fields
    assert "phone_ack_payload.token_echo" in fields


def test_reconcile_android_command_admin_reports_missing_target_identity_in_phone_payload():
    phone = _phone_command_row()
    del phone["payload"]["target_part_session_id"]
    phone["ack_sample"] = _ack_sample("cmd-001", "pause", phone["payload"])

    result = reconciler.reconcile_command_admin_with_phone_run(
        [_sender_row()],
        [phone],
        expect_native_sends=True,
        expect_command_acks=True,
    )

    assert result.ok is False
    fields = {item["field"] for item in result.report["mismatches"]}
    assert "payload.target_part_session_id" in fields


def test_reconcile_android_command_admin_can_reject_extra_phone_native_commands():
    result = reconciler.reconcile_command_admin_with_phone_run(
        [_sender_row()],
        [_phone_command_row(), _phone_command_row(command_id="cmd-extra", command="resume")],
        expect_native_sends=True,
        expect_command_acks=True,
        require_no_extra_phone_native_commands=True,
    )

    assert result.ok is False
    assert result.report["extra_phone_native_command_ids"] == ["cmd-extra"]
    assert "without a matching sender outbox row" in "\n".join(result.report["failures"])


def _sender_row(
    *,
    command_id: str = "cmd-001",
    command: str = "pause",
    schema: str = "pps-android-controller-command-row.v1",
    sender_id: str = "android_controller",
) -> dict:
    command_payload = _command_payload()
    ack_payload = _ack_payload(command)
    return {
        "schema": schema,
        "command_id": command_id,
        "command": command,
        "package_id": "pkg-001",
        "participant_id": "P001",
        "target_session_id": "part-001",
        "sender_id": sender_id,
        "native_lsl_sent": True,
        "ack_received": True,
        "ack_status": "applied",
        "command_sample": _command_sample(command_id, sender_id, command),
        "payload": command_payload,
        "ack_sample": _ack_sample(command_id, command, ack_payload),
    }


def _phone_command_row(
    *,
    command_id: str = "cmd-001",
    command: str = "pause",
    sender_id: str = "android_controller",
) -> dict:
    ack_payload = _ack_payload(command)
    return {
        "schema": "pps-android-command-diary.v1",
        "command_id": command_id,
        "command_source": "native_lsl",
        "sender_id": sender_id,
        "session_id": "part-001",
        "command": command,
        "status": "applied",
        "reason": "phone_playback_paused" if command == "pause" else "command_applied",
        "payload": ack_payload,
        "package_id": "pkg-001",
        "run_id": "phone-run-001",
        "received_lsl_time": 42.01,
        "applied_lsl_time": 42.02,
        "ack_lsl_time": 42.03,
        "ack_sent": True,
        "command_sample": _command_sample(command_id, sender_id, command),
        "ack_sample": _ack_sample(command_id, command, ack_payload),
    }


def _command_payload() -> dict:
    return {
        "token": "secret",
        "package_id": "pkg-001",
        "participant_id": "P001",
        "target_session_id": "part-001",
        "target_part_session_id": "part-001",
        "target_session_group_id": "group-001",
        "target_part_number": "1",
    }


def _command_sample(command_id: str, sender_id: str, command: str) -> list[str]:
    return [
        "pps-lsl-command.v1",
        command_id,
        "part-001",
        sender_id,
        command,
        "42.000000000",
        json.dumps(_command_payload(), sort_keys=True),
    ]


def _ack_payload(command: str) -> dict:
    return {
        "command": command,
        "package_id": "pkg-001",
        "participant_id": "P001",
        "target_session_id": "part-001",
        "target_part_session_id": "part-001",
        "target_session_group_id": "group-001",
        "target_part_number": "1",
        "run_id": "phone-run-001",
        "state_changed": True,
    }


def _ack_sample(command_id: str, command: str, payload: dict) -> list[str]:
    return [
        "pps-lsl-command-ack.v1",
        command_id,
        "part-001",
        "android_phone",
        "applied",
        "phone_playback_paused" if command == "pause" else "command_applied",
        "42.010000000",
        "42.020000000",
        "42.030000000",
        json.dumps(payload, sort_keys=True),
    ]


def _write_phone_run(run_dir: Path, command_rows: list[dict]) -> None:
    status = {"schema": "pps-android-lsl-runtime-status.v1"}
    (run_dir / "lsl_runtime_status.json").write_text(json.dumps(status), encoding="utf-8")
    (run_dir / "completion.json").write_text(
        json.dumps({"lsl_runtime_status": status, "command_diary": command_rows}),
        encoding="utf-8",
    )
    (run_dir / "command_diary.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in command_rows),
        encoding="utf-8",
    )
