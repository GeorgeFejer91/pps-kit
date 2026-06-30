"""Reconcile Android/PC command-admin outboxes with a phone-run command diary."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_android_lsl_runtime_artifact import (  # noqa: E402
    ACK_SCHEMA,
    ANDROID_CONTROLLER_COMMAND_ROW_SCHEMA,
    LSL_ACK_CHANNELS,
    LSL_COMMAND_CHANNELS,
    PC_ANDROID_LSL_ADMIN_ROW_SCHEMA,
    COMMAND_SCHEMA,
    _load_status_inputs,
)


RECONCILIATION_SCHEMA = "pps-android-command-admin-phone-run-reconciliation.v1"
REPORT_JSON = "android_command_admin_phone_run_reconciliation.json"
REPORT_MD = "android_command_admin_phone_run_reconciliation.md"


@dataclass(frozen=True)
class AndroidCommandAdminPhoneRunReconciliation:
    ok: bool
    report: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return self.report


def reconcile_command_admin_with_phone_run(
    sender_rows: list[dict[str, Any]],
    phone_command_rows: list[dict[str, Any]],
    *,
    sender_kind: str = "",
    sender_source_path: str = "",
    phone_source_path: str = "",
    expect_native_sends: bool = False,
    expect_command_acks: bool = False,
    require_no_extra_phone_native_commands: bool = False,
) -> AndroidCommandAdminPhoneRunReconciliation:
    failures: list[str] = []
    warnings: list[str] = []
    sender_native_rows = [row for row in sender_rows if row.get("native_lsl_sent") is True]
    sender_queued_rows = [row for row in sender_rows if row.get("native_lsl_sent") is not True]
    phone_native_rows = [
        row
        for row in phone_command_rows
        if str(row.get("command_source") or "") == "native_lsl"
    ]

    if expect_native_sends and sender_queued_rows:
        failures.append(f"{len(sender_queued_rows)} sender command rows were expected to use native LSL but did not")
    if not sender_native_rows:
        if expect_native_sends or expect_command_acks:
            failures.append("no native-sent controller/PC-admin command rows were available to reconcile")
        else:
            warnings.append("no native-sent controller/PC-admin command rows were available to reconcile")
    if expect_command_acks and not phone_native_rows:
        failures.append("no native_lsl phone-run command diary rows were available to reconcile")

    phone_by_id = _rows_by_command_id(phone_native_rows)
    sender_by_id = _rows_by_command_id(sender_native_rows)
    sender_ids = [_command_id(row) for row in sender_native_rows if _command_id(row)]
    phone_ids = [_command_id(row) for row in phone_native_rows if _command_id(row)]
    duplicate_sender_ids = _duplicates(sender_ids)
    duplicate_phone_ids = _duplicates(phone_ids)
    if duplicate_sender_ids:
        failures.append(f"sender outbox has duplicate native command ids: {', '.join(duplicate_sender_ids[:10])}")
    if duplicate_phone_ids:
        failures.append(f"phone command diary has duplicate native command ids: {', '.join(duplicate_phone_ids[:10])}")

    missing_phone_ids = sorted(set(sender_ids) - set(phone_ids), key=_id_sort_key)
    extra_phone_ids = sorted(set(phone_ids) - set(sender_ids), key=_id_sort_key)
    if missing_phone_ids:
        failures.append(
            "phone command diary is missing native rows for sender command ids: "
            + ", ".join(missing_phone_ids[:10])
        )
    if extra_phone_ids:
        message = (
            "phone command diary has native rows without a matching sender outbox row: "
            + ", ".join(extra_phone_ids[:10])
        )
        if require_no_extra_phone_native_commands:
            failures.append(message)
        else:
            warnings.append(message)

    mismatches: list[dict[str, Any]] = []
    matched_ids = sorted(set(sender_ids) & set(phone_ids), key=_id_sort_key)
    ack_pair_count = 0
    for command_id in matched_ids:
        sender = sender_by_id[command_id]
        phone = phone_by_id[command_id]
        mismatches.extend(_compare_sender_phone_command_pair(command_id, sender, phone))
        if _truthy(sender.get("ack_received")) and _truthy(phone.get("ack_sent")):
            ack_pair_count += 1
        elif expect_command_acks:
            mismatches.append(
                _mismatch(
                    command_id,
                    "ack_presence",
                    "sender ack_received=true and phone ack_sent=true",
                    f"sender={sender.get('ack_received')!r}, phone={phone.get('ack_sent')!r}",
                )
            )

    if mismatches:
        failures.append(f"sender outbox and phone command diary have {len(mismatches)} command mismatches")
    if expect_command_acks and ack_pair_count <= 0:
        failures.append("expected at least one reconciled sender/phone command ack pair")

    report = {
        "schema": RECONCILIATION_SCHEMA,
        "ok": not failures,
        "sender_source_path": sender_source_path,
        "phone_source_path": phone_source_path,
        "sender_kind": sender_kind,
        "sender_row_count": len(sender_rows),
        "sender_native_sent_count": len(sender_native_rows),
        "sender_queued_or_local_count": len(sender_queued_rows),
        "phone_command_diary_count": len(phone_command_rows),
        "phone_native_command_count": len(phone_native_rows),
        "matched_command_count": len(matched_ids),
        "reconciled_ack_pair_count": ack_pair_count,
        "missing_phone_command_ids": missing_phone_ids,
        "extra_phone_native_command_ids": extra_phone_ids,
        "duplicate_sender_command_ids": duplicate_sender_ids,
        "duplicate_phone_command_ids": duplicate_phone_ids,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:100],
        "failures": failures,
        "warnings": warnings,
        "evidence_boundary": (
            "offline_command_artifact_reconciliation_only_not_live_lsl_network_or_physical_timing_proof"
        ),
    }
    return AndroidCommandAdminPhoneRunReconciliation(ok=not failures, report=report)


def load_sender_command_artifact(path: Path) -> tuple[str, list[dict[str, Any]]]:
    try:
        loaded = _load_status_inputs(path)
    except Exception:
        if path.suffix.lower() != ".jsonl":
            raise
        rows = _read_jsonl(path)
        return _sender_kind_from_rows(rows), rows

    kind = str(loaded.get("kind") or "")
    if kind not in {"controller", "pc_admin"}:
        raise ValueError(f"{path} is not a controller or PC-admin command artifact")
    return kind, [dict(row) for row in list(loaded.get("outbox_rows") or []) if isinstance(row, dict)]


def load_phone_command_diary(path: Path) -> list[dict[str, Any]]:
    loaded = _load_status_inputs(path)
    if loaded.get("kind") != "runner":
        raise ValueError(f"{path} is not an Android phone-run artifact")
    rows = [dict(row) for row in list(loaded.get("command_diary_rows") or []) if isinstance(row, dict)]
    if rows:
        return rows
    completion = loaded.get("completion") if isinstance(loaded.get("completion"), dict) else {}
    return [dict(row) for row in list(completion.get("command_diary") or []) if isinstance(row, dict)]


def _compare_sender_phone_command_pair(
    command_id: str,
    sender: dict[str, Any],
    phone: dict[str, Any],
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    sample = _sender_command_sample(sender)
    sample_payload = _sample_payload(sample)
    if len(sample) != len(LSL_COMMAND_CHANNELS):
        mismatches.append(_mismatch(command_id, "command_sample.channel_count", len(LSL_COMMAND_CHANNELS), len(sample)))
        return mismatches
    if sample[0] != COMMAND_SCHEMA:
        mismatches.append(_mismatch(command_id, "command_sample.schema", COMMAND_SCHEMA, sample[0]))
    _compare_field(mismatches, command_id, "command", _first_nonblank(sender.get("command"), sample[4]), phone.get("command"))
    _compare_field(mismatches, command_id, "session_id", sample[2], phone.get("session_id"))
    _compare_field(mismatches, command_id, "sender_id", sample[3], phone.get("sender_id"))
    package_id = _first_nonblank(sender.get("package_id"), sample_payload.get("package_id"))
    if package_id:
        _compare_field(mismatches, command_id, "package_id", package_id, phone.get("package_id"))
    if str(phone.get("command_source") or "") != "native_lsl":
        mismatches.append(_mismatch(command_id, "phone.command_source", "native_lsl", phone.get("command_source")))

    sender_ack_sample = _json_list(sender.get("ack_sample"))
    phone_ack_sample = _json_list(phone.get("ack_sample"))
    phone_payload = phone.get("payload") if isinstance(phone.get("payload"), dict) else {}
    _compare_required_field(
        mismatches,
        command_id,
        "payload.target_session_id",
        _first_nonblank(sender.get("target_session_id"), sample_payload.get("target_session_id"), sample[2]),
        _first_nonblank(phone_payload.get("target_session_id"), phone.get("target_session_id"), phone.get("session_id")),
    )
    for field in ["target_part_session_id", "target_session_group_id", "target_part_number", "participant_id"]:
        _compare_required_field(
            mismatches,
            command_id,
            f"payload.{field}",
            _first_nonblank(sender.get(field), sample_payload.get(field)),
            _first_nonblank(phone_payload.get(field), phone.get(field)),
        )
    if sender.get("ack_received") is True or phone.get("ack_sent") is True:
        if len(sender_ack_sample) != len(LSL_ACK_CHANNELS):
            mismatches.append(
                _mismatch(command_id, "sender.ack_sample.channel_count", len(LSL_ACK_CHANNELS), len(sender_ack_sample))
            )
        if len(phone_ack_sample) != len(LSL_ACK_CHANNELS):
            mismatches.append(
                _mismatch(command_id, "phone.ack_sample.channel_count", len(LSL_ACK_CHANNELS), len(phone_ack_sample))
            )
        if len(sender_ack_sample) == len(LSL_ACK_CHANNELS) and len(phone_ack_sample) == len(LSL_ACK_CHANNELS):
            if sender_ack_sample[0] != ACK_SCHEMA:
                mismatches.append(_mismatch(command_id, "sender.ack_sample.schema", ACK_SCHEMA, sender_ack_sample[0]))
            if phone_ack_sample[0] != ACK_SCHEMA:
                mismatches.append(_mismatch(command_id, "phone.ack_sample.schema", ACK_SCHEMA, phone_ack_sample[0]))
            if _canonical_json(sender_ack_sample) != _canonical_json(phone_ack_sample):
                mismatches.append(_mismatch(command_id, "ack_sample", sender_ack_sample, phone_ack_sample))
            _compare_field(mismatches, command_id, "ack_status", sender_ack_sample[4], phone.get("status"))
            _compare_field(mismatches, command_id, "ack_reason", sender_ack_sample[5], phone.get("reason"))
            ack_payload = _safe_json_object(sender_ack_sample[9])
            phone_ack_payload = _safe_json_object(phone_ack_sample[9])
            if ack_payload and phone_ack_payload and _canonical_json(ack_payload) != _canonical_json(phone_ack_payload):
                mismatches.append(_mismatch(command_id, "ack_payload", ack_payload, phone_ack_payload))
            if ack_payload and phone_payload and _canonical_json(ack_payload) != _canonical_json(phone_payload):
                mismatches.append(_mismatch(command_id, "sender_ack_payload", ack_payload, phone_payload))
            if phone_ack_payload and phone_payload and _canonical_json(phone_ack_payload) != _canonical_json(phone_payload):
                mismatches.append(_mismatch(command_id, "phone_ack_payload", phone_ack_payload, phone_payload))
    return mismatches


def _sender_kind_from_rows(rows: list[dict[str, Any]]) -> str:
    schemas = {str(row.get("schema") or "") for row in rows}
    if ANDROID_CONTROLLER_COMMAND_ROW_SCHEMA in schemas:
        return "controller"
    if PC_ANDROID_LSL_ADMIN_ROW_SCHEMA in schemas:
        return "pc_admin"
    raise ValueError("JSONL artifact is not a controller or PC-admin command outbox")


def _sender_command_sample(row: dict[str, Any]) -> list[str]:
    return [str(value) for value in _json_list(row.get("command_sample"))]


def _sample_payload(sample: list[str]) -> dict[str, Any]:
    if len(sample) <= 6:
        return {}
    return _safe_json_object(sample[6])


def _compare_field(
    mismatches: list[dict[str, Any]],
    command_id: str,
    field: str,
    expected: Any,
    observed: Any,
) -> None:
    expected_value = _clean(expected)
    observed_value = _clean(observed)
    if expected_value and observed_value and expected_value != observed_value:
        mismatches.append(_mismatch(command_id, field, expected_value, observed_value))


def _compare_required_field(
    mismatches: list[dict[str, Any]],
    command_id: str,
    field: str,
    expected: Any,
    observed: Any,
) -> None:
    expected_value = _clean(expected)
    if not expected_value:
        return
    observed_value = _clean(observed)
    if observed_value != expected_value:
        mismatches.append(_mismatch(command_id, field, expected_value, observed_value))


def _mismatch(command_id: str, field: str, expected: Any, observed: Any) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "field": field,
        "expected": expected,
        "observed": observed,
    }


def _rows_by_command_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        command_id = _command_id(row)
        if command_id and command_id not in result:
            result[command_id] = row
    return result


def _command_id(row: dict[str, Any]) -> str:
    value = _clean(row.get("command_id"))
    if value:
        return value
    sample = _json_list(row.get("command_sample"))
    if len(sample) > 1:
        return _clean(sample[1])
    return ""


def _duplicates(values: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return sorted([value for value, count in counts.items() if count > 1], key=_id_sort_key)


def _id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if str(value).isdigit() else (1, str(value))


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def _first_nonblank(*values: Any) -> str:
    for value in values:
        cleaned = _clean(value)
        if cleaned:
            return cleaned
    return ""


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _safe_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    try:
        parsed = json.loads(str(raw or "{}"))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            raw = line.strip()
            if not raw:
                continue
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError(f"{path}:{line_number} did not contain a JSON object")
            rows.append(data)
    return rows


def _write_report(result: AndroidCommandAdminPhoneRunReconciliation, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / REPORT_JSON).write_text(json.dumps(result.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = result.report
    lines = [
        "# Android Command Admin / Phone Run Reconciliation",
        "",
        f"- Result: `{'PASS' if result.ok else 'FAIL'}`",
        f"- Sender kind: `{report.get('sender_kind')}`",
        f"- Sender native rows: `{report.get('sender_native_sent_count')}`",
        f"- Phone native command rows: `{report.get('phone_native_command_count')}`",
        f"- Matched commands: `{report.get('matched_command_count')}`",
        f"- Reconciled ack pairs: `{report.get('reconciled_ack_pair_count')}`",
        "",
    ]
    if report.get("failures"):
        lines.extend(["## Failures", *[f"- {item}" for item in report["failures"]], ""])
    if report.get("warnings"):
        lines.extend(["## Warnings", *[f"- {item}" for item in report["warnings"]], ""])
    (output_dir / REPORT_MD).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sender_artifact",
        type=Path,
        help="Controller/PC-admin directory, status JSON, or command outbox JSONL.",
    )
    parser.add_argument(
        "phone_run",
        type=Path,
        help="Phone-run directory, ZIP, completion JSON, or lsl_runtime_status.json.",
    )
    parser.add_argument("--expect-native-sends", action="store_true", help="Fail unless sender rows were sent over native LSL.")
    parser.add_argument("--expect-command-acks", action="store_true", help="Fail unless matched sender/phone ack evidence is present.")
    parser.add_argument(
        "--require-no-extra-phone-native-commands",
        action="store_true",
        help="Fail if the phone run contains native_lsl command diary rows not present in the sender outbox.",
    )
    parser.add_argument("--output-dir", type=Path, help="Optional directory for JSON/Markdown reconciliation reports.")
    args = parser.parse_args(argv)

    sender_kind, sender_rows = load_sender_command_artifact(args.sender_artifact)
    result = reconcile_command_admin_with_phone_run(
        sender_rows,
        load_phone_command_diary(args.phone_run),
        sender_kind=sender_kind,
        sender_source_path=str(args.sender_artifact),
        phone_source_path=str(args.phone_run),
        expect_native_sends=args.expect_native_sends,
        expect_command_acks=args.expect_command_acks,
        require_no_extra_phone_native_commands=args.require_no_extra_phone_native_commands,
    )
    if args.output_dir:
        _write_report(result, args.output_dir)
    print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
