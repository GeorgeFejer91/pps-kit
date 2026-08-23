"""Reconcile Android phone-run marker mirrors with PC-observed LSL monitor rows."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.android_lsl_monitor import (  # noqa: E402
    PC_ANDROID_LSL_MONITOR_EVENTS,
    PC_ANDROID_LSL_MONITOR_REPORT,
    PC_ANDROID_LSL_MONITOR_ROW_SCHEMA,
    STREAM_DEFINITIONS,
    build_android_lsl_monitor_row,
)


RECONCILIATION_SCHEMA = "pps-android-lsl-monitor-reconciliation.v1"
REPORT_JSON = "android_lsl_monitor_reconciliation.json"
REPORT_MD = "android_lsl_monitor_reconciliation.md"
COMMAND_ACK_PAYLOAD_IDENTITY_FIELDS = (
    "package_id",
    "participant_id",
    "target_session_id",
    "target_part_session_id",
    "target_session_group_id",
    "target_part_number",
)
COMMAND_ACK_PAIRING_TOKEN_FIELDS = ("token", "companion_token")
COMMANDS_REQUIRING_NOTE = {"operator_note"}
ANDROID_COMMAND_REJECTION_PAYLOAD_SCHEMA = "pps-android-phone-command-rejection.v1"
ANDROID_COMMAND_HANDLER_REJECTION_PAYLOAD_SCHEMA = "pps-android-phone-command-handler-rejection.v1"
REJECTED_ACK_REQUIRED_FIELDS = (
    "package_id",
    "participant_id",
    "session_id",
    "part_session_id",
    "session_group_id",
    "part_number",
    "requested_session_id",
    "requested_package_id",
    "requested_participant_id",
    "requested_target_session_id",
    "requested_target_part_session_id",
    "requested_target_session_group_id",
    "requested_target_part_number",
)


@dataclass(frozen=True)
class AndroidLslMonitorReconciliation:
    ok: bool
    report: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return self.report


def reconcile_android_lsl_monitor(
    phone_markers: list[dict[str, Any]],
    monitor_rows: list[dict[str, Any]],
    *,
    phone_source_path: str = "",
    monitor_source_path: str = "",
    expect_numeric_triggers: bool = False,
    expect_command_acks: bool = False,
) -> AndroidLslMonitorReconciliation:
    rich_rows = [row for row in monitor_rows if row.get("stream_key") == "rich_markers"]
    numeric_rows = [row for row in monitor_rows if row.get("stream_key") == "numeric_triggers"]
    command_rows = [row for row in monitor_rows if row.get("stream_key") == "command_signals"]
    ack_rows = [row for row in monitor_rows if row.get("stream_key") == "command_acks"]
    failures: list[str] = []
    warnings: list[str] = []
    if not phone_markers:
        failures.append("phone marker mirror is empty")
    if not rich_rows:
        failures.append("PC monitor did not capture any PPSMarkersV2 rows")
    if expect_numeric_triggers and not numeric_rows:
        failures.append("PC monitor did not capture any PPSTriggerCodes rows")
    if expect_command_acks and not ack_rows:
        failures.append("PC monitor did not capture any PPSCommandAcksV1 rows")

    phone_by_id = _rows_by_event_id(phone_markers)
    rich_by_id = _rows_by_event_id(rich_rows)
    phone_ids = [_event_id(row) for row in phone_markers if _event_id(row)]
    rich_ids = [_event_id(row) for row in rich_rows if _event_id(row)]
    missing = sorted(set(phone_ids) - set(rich_ids), key=_event_id_sort_key)
    extra = sorted(set(rich_ids) - set(phone_ids), key=_event_id_sort_key)
    duplicate_phone = _duplicates(phone_ids)
    duplicate_monitor = _duplicates(rich_ids)
    if missing:
        failures.append(f"PC monitor is missing {len(missing)} phone marker event ids")
    if extra:
        failures.append(f"PC monitor has {len(extra)} extra rich marker event ids")
    if duplicate_phone:
        failures.append(f"phone marker mirror has duplicate event ids: {', '.join(duplicate_phone[:10])}")
    if duplicate_monitor:
        failures.append(f"PC monitor has duplicate rich marker event ids: {', '.join(duplicate_monitor[:10])}")

    mismatches: list[dict[str, Any]] = []
    for event_id in sorted(set(phone_ids) & set(rich_ids), key=_event_id_sort_key):
        phone = phone_by_id[event_id]
        rich = rich_by_id[event_id]
        for field in (
            "event_type",
            "event_code",
            "trigger_key",
            "marker_name",
            "session_id",
            "participant_id",
            "session_group_id",
            "part_session_id",
            "part_number",
            "block_index",
            "trial_uid",
            "timestamp_quality",
        ):
            expected = _clean(phone.get(field))
            observed = _clean(rich.get(field))
            if expected != observed:
                mismatches.append(
                    {
                        "event_id": event_id,
                        "field": field,
                        "expected": expected,
                        "observed": observed,
                    }
                )
        expected_payload = _canonical_payload_json(phone.get("payload_json"))
        observed_payload = _canonical_payload_json(rich.get("payload_json"))
        if expected_payload != observed_payload:
            mismatches.append(
                {
                    "event_id": event_id,
                    "field": "payload_json",
                    "expected": expected_payload,
                    "observed": observed_payload,
                }
            )
    if mismatches:
        failures.append(f"PC monitor rich markers have {len(mismatches)} field mismatches")

    numeric_summary = _numeric_summary(phone_markers, numeric_rows)
    if numeric_rows and not numeric_summary["sequence_matches_phone_markers"]:
        failures.append("PC monitor numeric trigger sequence does not match phone marker event_code sequence")
    elif not numeric_rows and not expect_numeric_triggers:
        warnings.append("PC monitor has no numeric trigger rows; rerun with --expect-numeric-triggers for strict checks")

    ack_summary = {
        "ack_count": len(ack_rows),
        "ack_status_counts": dict(Counter(str(row.get("ack_status") or "unknown") for row in ack_rows)),
        "ack_command_ids": sorted({str(row.get("command_id") or "") for row in ack_rows if row.get("command_id")}),
    }
    command_pair_summary = _command_ack_pair_summary(command_rows, ack_rows)
    if expect_command_acks and command_pair_summary["command_ids_without_ack"]:
        failures.append(
            "PC monitor command signals are missing matching ack ids: "
            + ", ".join(command_pair_summary["command_ids_without_ack"][:10])
        )
    if command_rows and command_pair_summary["ack_ids_without_command"]:
        failures.append(
            "PC monitor command acks are missing matching command signal ids: "
            + ", ".join(command_pair_summary["ack_ids_without_command"][:10])
        )
    if command_pair_summary["duplicate_command_signal_ids"]:
        failures.append(
            "PC monitor has duplicate command signal ids: "
            + ", ".join(command_pair_summary["duplicate_command_signal_ids"][:10])
        )
    if command_pair_summary["duplicate_command_ack_ids"]:
        failures.append(
            "PC monitor has duplicate command ack ids: "
            + ", ".join(command_pair_summary["duplicate_command_ack_ids"][:10])
        )
    if command_pair_summary["mismatch_count"]:
        failures.append(f"PC monitor command/ack pairs have {command_pair_summary['mismatch_count']} mismatches")

    report = {
        "schema": RECONCILIATION_SCHEMA,
        "ok": not failures,
        "phone_source_path": phone_source_path,
        "monitor_source_path": monitor_source_path,
        "phone_marker_count": len(phone_markers),
        "monitor_rich_marker_count": len(rich_rows),
        "monitor_numeric_trigger_count": len(numeric_rows),
        "monitor_command_signal_count": len(command_rows),
        "monitor_command_ack_count": len(ack_rows),
        "compared_event_count": len(set(phone_ids) & set(rich_ids)),
        "missing_event_ids": missing,
        "extra_event_ids": extra,
        "duplicate_phone_event_ids": duplicate_phone,
        "duplicate_monitor_event_ids": duplicate_monitor,
        "field_mismatch_count": len(mismatches),
        "field_mismatches": mismatches[:100],
        "phone_event_type_counts": dict(Counter(str(row.get("event_type") or "") for row in phone_markers)),
        "monitor_event_type_counts": dict(Counter(str(row.get("event_type") or "") for row in rich_rows)),
        "numeric_trigger_summary": numeric_summary,
        "command_ack_summary": ack_summary,
        "command_ack_pair_summary": command_pair_summary,
        "failures": failures,
        "warnings": warnings,
        "evidence_boundary": (
            "pc_lsl_monitor_reconciliation_only_not_physical_timing_or_labrecorder_persistence_proof"
        ),
    }
    return AndroidLslMonitorReconciliation(ok=not failures, report=report)


def load_phone_markers(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        csv_path = path / "lsl_marker_mirror.csv"
        if csv_path.is_file():
            return _read_csv(csv_path)
        completion_path = path / "completion.json"
        if not completion_path.is_file():
            completion_path = path / "latest_events.json"
        if completion_path.is_file():
            return _markers_from_json(_read_json(completion_path))
        raise FileNotFoundError(f"Missing lsl_marker_mirror.csv or completion/latest_events JSON in {path}")
    if path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="pps-android-monitor-reconcile-") as temp_dir:
            temp_root = Path(temp_dir)
            with zipfile.ZipFile(path) as archive:
                marker_members = [name for name in archive.namelist() if name.endswith("lsl_marker_mirror.csv")]
                if marker_members:
                    marker_name = sorted(marker_members)[0]
                    archive.extract(marker_name, temp_root)
                    return _read_csv(temp_root / marker_name)
                completion_members = [
                    name for name in archive.namelist() if name.endswith("completion.json") or name.endswith("latest_events.json")
                ]
                if completion_members:
                    completion_name = sorted(completion_members)[0]
                    archive.extract(completion_name, temp_root)
                    return _markers_from_json(_read_json(temp_root / completion_name))
        raise FileNotFoundError(f"{path} does not contain lsl_marker_mirror.csv or completion/latest_events JSON")
    if path.suffix.lower() == ".csv":
        return _read_csv(path)
    data = _read_json(path)
    return _markers_from_json(data)


def load_monitor_rows(path: Path) -> list[dict[str, Any]]:
    if path.is_dir():
        events_path = path / PC_ANDROID_LSL_MONITOR_EVENTS
        if events_path.is_file():
            return _read_jsonl(events_path)
        raise FileNotFoundError(f"Missing {PC_ANDROID_LSL_MONITOR_EVENTS} in {path}")
    if path.suffix.lower() == ".jsonl":
        return _read_jsonl(path)
    if path.suffix.lower() == ".xdf":
        return _load_monitor_rows_from_xdf(path)
    data = _read_json(path)
    if data.get("schema") == PC_ANDROID_LSL_MONITOR_ROW_SCHEMA:
        return [data]
    if data.get("schema") and path.name == PC_ANDROID_LSL_MONITOR_REPORT:
        events_path = path.with_name(PC_ANDROID_LSL_MONITOR_EVENTS)
        if events_path.is_file():
            return _read_jsonl(events_path)
        raise FileNotFoundError(f"Missing {events_path} beside monitor report")
    rows = data.get("events") or data.get("monitor_rows")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    raise ValueError(f"{path} is not a PC Android LSL monitor events artifact")


def _markers_from_json(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = data.get("lsl_marker_mirror")
    if not isinstance(rows, list):
        raise ValueError("JSON artifact does not contain lsl_marker_mirror array")
    return [dict(row) for row in rows if isinstance(row, dict)]


def _load_monitor_rows_from_xdf(path: Path) -> list[dict[str, Any]]:
    try:
        import pyxdf  # type: ignore
    except Exception as exc:  # noqa: BLE001 - optional validation dependency.
        raise RuntimeError("pyxdf is required to read LabRecorder/XDF Android LSL monitor artifacts") from exc

    streams, _header = pyxdf.load_xdf(str(path))
    rows: list[dict[str, Any]] = []
    for stream in streams or []:
        if not isinstance(stream, dict):
            continue
        info = stream.get("info") if isinstance(stream.get("info"), dict) else {}
        stream_key = _stream_key_from_xdf_info(info)
        if not stream_key:
            continue
        samples = _as_list(stream.get("time_series"))
        timestamps = _as_list(stream.get("time_stamps"))
        source_id = _xdf_info_value(info, "source_id")
        stream_name = _xdf_info_value(info, "name")
        for index, sample in enumerate(samples):
            sample_values = _as_sample_values(sample)
            timestamp = timestamps[index] if index < len(timestamps) else 0.0
            rows.append(
                build_android_lsl_monitor_row(
                    stream_key=stream_key,
                    sample=sample_values,
                    lsl_timestamp=_safe_float(timestamp, default=0.0),
                    source_id=source_id,
                    stream_name=stream_name,
                )
            )
    return rows


def _stream_key_from_xdf_info(info: dict[str, Any]) -> str:
    stream_name = _xdf_info_value(info, "name")
    stream_type = _xdf_info_value(info, "type")
    for key, definition in STREAM_DEFINITIONS.items():
        if stream_name == str(definition["stream_name"]):
            return key
    for key, definition in STREAM_DEFINITIONS.items():
        if stream_type and stream_type == str(definition["stream_type"]):
            return key
    return ""


def _xdf_info_value(info: dict[str, Any], key: str) -> str:
    raw = info.get(key)
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    return "" if raw is None else str(raw)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        converted = value.tolist()
        return converted if isinstance(converted, list) else [converted]
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_sample_values(sample: Any) -> list[Any]:
    values = _as_list(sample)
    if len(values) == 1 and isinstance(values[0], list):
        return values[0]
    return values


def _numeric_summary(phone_markers: list[dict[str, Any]], numeric_rows: list[dict[str, Any]]) -> dict[str, Any]:
    phone_codes = [_clean_code(row.get("event_code")) for row in phone_markers]
    monitor_codes = [_clean_code(row.get("event_code")) for row in numeric_rows]
    phone_codes = [code for code in phone_codes if code != ""]
    monitor_codes = [code for code in monitor_codes if code != ""]
    return {
        "phone_marker_code_count": len(phone_codes),
        "monitor_numeric_code_count": len(monitor_codes),
        "sequence_matches_phone_markers": bool(phone_codes) and phone_codes == monitor_codes,
        "phone_code_counts": dict(Counter(phone_codes)),
        "monitor_code_counts": dict(Counter(monitor_codes)),
        "first_mismatch_index": _first_mismatch_index(phone_codes, monitor_codes),
    }


def _command_ack_pair_summary(command_rows: list[dict[str, Any]], ack_rows: list[dict[str, Any]]) -> dict[str, Any]:
    command_ids = [_command_id(row) for row in command_rows if _command_id(row)]
    ack_ids = [_command_id(row) for row in ack_rows if _command_id(row)]
    command_by_id = _rows_by_command_id(command_rows)
    ack_by_id = _rows_by_command_id(ack_rows)
    missing_ack = sorted(set(command_ids) - set(ack_ids), key=_event_id_sort_key)
    ack_without_command = sorted(set(ack_ids) - set(command_ids), key=_event_id_sort_key) if command_rows else []
    mismatches: list[dict[str, Any]] = []
    for command_row in command_rows:
        _append_command_signal_payload_mismatches(mismatches, command_row)
    for ack_row in ack_rows:
        ack_payload = _payload_object(ack_row.get("payload_json"))
        for field in _ack_pairing_token_fields(ack_payload):
            mismatches.append(_command_ack_mismatch(_command_id(ack_row), f"payload.{field}", "", "<redacted>"))
        receiver_role = _clean(ack_payload.get("receiver_role"))
        if receiver_role != "runner":
            mismatches.append(_command_ack_mismatch(_command_id(ack_row), "payload.receiver_role", "runner", receiver_role))
        if _clean(ack_row.get("ack_status")) == "rejected":
            _append_rejected_ack_payload_mismatches(mismatches, ack_row, ack_payload)
    for command_id in sorted(set(command_ids) & set(ack_ids), key=_event_id_sort_key):
        command_row = command_by_id[command_id]
        ack_row = ack_by_id[command_id]
        command_session = _clean(command_row.get("session_id"))
        ack_session = _clean(ack_row.get("session_id"))
        if command_session and ack_session and command_session != ack_session:
            mismatches.append(_command_ack_mismatch(command_id, "session_id", command_session, ack_session))

        command_name = _clean(command_row.get("command"))
        command_payload = _payload_object(command_row.get("payload_json"))
        ack_payload = _payload_object(ack_row.get("payload_json"))
        ack_status = _clean(ack_row.get("ack_status"))
        payload_command = _clean(ack_payload.get("command"))
        if payload_command and command_name and payload_command != command_name:
            mismatches.append(_command_ack_mismatch(command_id, "payload.command", command_name, payload_command))
        elif command_name and ack_status == "applied" and not payload_command:
            mismatches.append(_command_ack_mismatch(command_id, "payload.command", command_name, ""))

        for field in COMMAND_ACK_PAYLOAD_IDENTITY_FIELDS:
            _append_command_ack_payload_mismatch(
                mismatches,
                command_id,
                field,
                command_payload,
                ack_payload,
                ack_status=ack_status,
            )

    return {
        "command_signal_count": len(command_rows),
        "ack_count": len(ack_rows),
        "command_signal_ids": sorted(set(command_ids), key=_event_id_sort_key),
        "ack_ids": sorted(set(ack_ids), key=_event_id_sort_key),
        "command_ids_without_ack": missing_ack,
        "ack_ids_without_command": ack_without_command,
        "duplicate_command_signal_ids": _duplicates(command_ids),
        "duplicate_command_ack_ids": _duplicates(ack_ids),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:100],
    }


def _append_command_signal_payload_mismatches(mismatches: list[dict[str, Any]], command_row: dict[str, Any]) -> None:
    command_id = _command_id(command_row)
    sample_payload, has_sample_payload = _sample_payload_json(command_row, fallback_index=6)
    if has_sample_payload:
        row_payload = _canonical_payload_json(command_row.get("payload_json"))
        raw_sample_payload = _canonical_payload_json(sample_payload)
        if row_payload != raw_sample_payload:
            mismatches.append(
                _command_ack_mismatch(
                    command_id,
                    "payload_json.sample",
                    "<sample_payload>",
                    "<row_payload>",
                )
            )

    command_payload = _payload_object(sample_payload if has_sample_payload else command_row.get("payload_json"))
    if not _payload_has_pairing_token(command_payload):
        mismatches.append(_command_ack_mismatch(command_id, "payload.token", "<required>", ""))

    command_name = _clean(command_row.get("command"))
    if command_name in COMMANDS_REQUIRING_NOTE and not _clean(command_payload.get("note")):
        mismatches.append(_command_ack_mismatch(command_id, "payload.note", "<required_for_operator_note>", ""))


def _command_ack_mismatch(command_id: str, field: str, expected: str, observed: str) -> dict[str, Any]:
    return {
        "command_id": command_id,
        "field": field,
        "expected": expected,
        "observed": observed,
    }


def _append_command_ack_payload_mismatch(
    mismatches: list[dict[str, Any]],
    command_id: str,
    field: str,
    command_payload: dict[str, Any],
    ack_payload: dict[str, Any],
    *,
    ack_status: str,
) -> None:
    expected = _clean(command_payload.get(field))
    if not expected:
        return
    observed = _clean(ack_payload.get(field))
    if observed and expected != observed:
        mismatches.append(_command_ack_mismatch(command_id, f"payload.{field}", expected, observed))
    elif ack_status == "applied" and not observed:
        mismatches.append(_command_ack_mismatch(command_id, f"payload.{field}", expected, ""))


def _append_rejected_ack_payload_mismatches(
    mismatches: list[dict[str, Any]],
    ack_row: dict[str, Any],
    ack_payload: dict[str, Any],
) -> None:
    command_id = _command_id(ack_row)
    if not ack_payload:
        mismatches.append(_command_ack_mismatch(command_id, "payload.rejected_payload", "structured rejection payload", ""))
        return
    schema = _clean(ack_payload.get("schema"))
    if schema == ANDROID_COMMAND_HANDLER_REJECTION_PAYLOAD_SCHEMA:
        _append_handler_rejected_ack_payload_mismatches(mismatches, ack_row, ack_payload)
        return
    if schema != ANDROID_COMMAND_REJECTION_PAYLOAD_SCHEMA:
        mismatches.append(
            _command_ack_mismatch(
                command_id,
                "payload.schema",
                f"{ANDROID_COMMAND_REJECTION_PAYLOAD_SCHEMA} or {ANDROID_COMMAND_HANDLER_REJECTION_PAYLOAD_SCHEMA}",
                _clean(ack_payload.get("schema")),
            )
        )
    if _clean(ack_payload.get("status")) != "rejected":
        mismatches.append(_command_ack_mismatch(command_id, "payload.status", "rejected", _clean(ack_payload.get("status"))))
    reason = _clean(ack_row.get("ack_reason"))
    if reason and _clean(ack_payload.get("reason")) != reason:
        mismatches.append(_command_ack_mismatch(command_id, "payload.reason", reason, _clean(ack_payload.get("reason"))))
    if ack_payload.get("rejected_before_handler") is not True:
        mismatches.append(
            _command_ack_mismatch(
                command_id,
                "payload.rejected_before_handler",
                "true",
                _clean(ack_payload.get("rejected_before_handler")),
            )
        )
    for field in REJECTED_ACK_REQUIRED_FIELDS:
        if field not in ack_payload:
            mismatches.append(_command_ack_mismatch(command_id, f"payload.{field}", "<present>", ""))
    supported = ack_payload.get("supported_commands")
    if not isinstance(supported, list) or not supported:
        mismatches.append(_command_ack_mismatch(command_id, "payload.supported_commands", "nonempty array", ""))


def _append_handler_rejected_ack_payload_mismatches(
    mismatches: list[dict[str, Any]],
    ack_row: dict[str, Any],
    ack_payload: dict[str, Any],
) -> None:
    command_id = _command_id(ack_row)
    if _clean(ack_payload.get("status")) != "rejected":
        mismatches.append(_command_ack_mismatch(command_id, "payload.status", "rejected", _clean(ack_payload.get("status"))))
    reason = _clean(ack_row.get("ack_reason"))
    if reason and _clean(ack_payload.get("reason")) != reason:
        mismatches.append(_command_ack_mismatch(command_id, "payload.reason", reason, _clean(ack_payload.get("reason"))))
    if ack_payload.get("rejected_before_handler") is not False:
        mismatches.append(
            _command_ack_mismatch(
                command_id,
                "payload.rejected_before_handler",
                "false",
                _clean(ack_payload.get("rejected_before_handler")),
            )
        )
    if not isinstance(ack_payload.get("handler_completed"), bool):
        mismatches.append(_command_ack_mismatch(command_id, "payload.handler_completed", "boolean", ""))
    for field in REJECTED_ACK_REQUIRED_FIELDS:
        if field not in ack_payload:
            mismatches.append(_command_ack_mismatch(command_id, f"payload.{field}", "<present>", ""))
    supported = ack_payload.get("supported_commands")
    if not isinstance(supported, list) or not supported:
        mismatches.append(_command_ack_mismatch(command_id, "payload.supported_commands", "nonempty array", ""))
    handler_payload = ack_payload.get("handler_payload")
    if not isinstance(handler_payload, dict):
        mismatches.append(_command_ack_mismatch(command_id, "payload.handler_payload", "object", ""))
    else:
        for field in _ack_pairing_token_fields(handler_payload):
            mismatches.append(_command_ack_mismatch(command_id, f"payload.handler_payload.{field}", "", "<redacted>"))


def _ack_pairing_token_fields(payload: dict[str, Any]) -> list[str]:
    return [field for field in COMMAND_ACK_PAIRING_TOKEN_FIELDS if _clean(payload.get(field))]


def _payload_has_pairing_token(payload: dict[str, Any]) -> bool:
    return bool(_ack_pairing_token_fields(payload))


def _sample_payload_json(row: dict[str, Any], *, fallback_index: int) -> tuple[Any, bool]:
    sample = row.get("sample")
    if not isinstance(sample, list):
        return "", False
    labels = row.get("channel_labels")
    index = fallback_index
    if isinstance(labels, list):
        normalized = [str(label) for label in labels]
        if "payload_json" in normalized:
            index = normalized.index("payload_json")
    if 0 <= index < len(sample):
        return sample[index], True
    return "", True


def _first_mismatch_index(left: list[str], right: list[str]) -> int | None:
    for index, (left_value, right_value) in enumerate(zip(left, right), start=1):
        if left_value != right_value:
            return index
    if len(left) != len(right):
        return min(len(left), len(right)) + 1
    return None


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


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


def _rows_by_event_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        event_id = _event_id(row)
        if event_id and event_id not in result:
            result[event_id] = row
    return result


def _rows_by_command_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        command_id = _command_id(row)
        if command_id and command_id not in result:
            result[command_id] = row
    return result


def _event_id(row: dict[str, Any]) -> str:
    return _clean(row.get("event_id"))


def _command_id(row: dict[str, Any]) -> str:
    return _clean(row.get("command_id"))


def _event_id_sort_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if str(value).isdigit() else (1, str(value))


def _duplicates(values: list[str]) -> list[str]:
    counts = Counter(value for value in values if value)
    return sorted([value for value, count in counts.items() if count > 1], key=_event_id_sort_key)


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _clean_code(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        return str(int(float(raw)))
    except ValueError:
        return raw


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _canonical_payload_json(value: Any) -> str:
    raw = _clean(value)
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _payload_object(value: Any) -> dict[str, Any]:
    raw = _clean(value)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_report(result: AndroidLslMonitorReconciliation, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_json = output_dir / REPORT_JSON
    report_md = output_dir / REPORT_MD
    report_json.write_text(json.dumps(result.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = result.report
    lines = [
        "# Android LSL Monitor Reconciliation",
        "",
        f"- Result: `{'PASS' if result.ok else 'FAIL'}`",
        f"- Phone markers: `{report.get('phone_marker_count')}`",
        f"- Monitor rich markers: `{report.get('monitor_rich_marker_count')}`",
        f"- Monitor numeric triggers: `{report.get('monitor_numeric_trigger_count')}`",
        f"- Monitor command signals: `{report.get('monitor_command_signal_count')}`",
        f"- Monitor command acks: `{report.get('monitor_command_ack_count')}`",
        f"- Compared events: `{report.get('compared_event_count')}`",
        "",
    ]
    if report.get("failures"):
        lines.extend(["## Failures", *[f"- {item}" for item in report["failures"]], ""])
    if report.get("warnings"):
        lines.extend(["## Warnings", *[f"- {item}" for item in report["warnings"]], ""])
    report_md.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phone_run", type=Path, help="Phone run folder, ZIP, lsl_marker_mirror.csv, completion.json, or latest_events.json.")
    parser.add_argument("monitor_artifact", type=Path, help="PC monitor folder, pc_android_lsl_monitor_events.jsonl, or report JSON.")
    parser.add_argument("--expect-numeric-triggers", action="store_true")
    parser.add_argument("--expect-command-acks", action="store_true")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for JSON/Markdown reconciliation reports.")
    args = parser.parse_args(argv)

    result = reconcile_android_lsl_monitor(
        load_phone_markers(args.phone_run),
        load_monitor_rows(args.monitor_artifact),
        phone_source_path=str(args.phone_run),
        monitor_source_path=str(args.monitor_artifact),
        expect_numeric_triggers=args.expect_numeric_triggers,
        expect_command_acks=args.expect_command_acks,
    )
    if args.output_dir:
        _write_report(result, args.output_dir)
    print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
