"""Validate Android phone-owned LSL runtime status artifacts."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.lsl_command_ack import (  # noqa: E402
    ACK_SCHEMA,
    COMMAND_SCHEMA,
    LSL_ACK_CHANNELS,
    LSL_ACK_STREAM_NAME,
    LSL_COMMAND_CHANNELS,
    LSL_COMMAND_STREAM_NAME,
)
from peripersonal_space_toolkit.android_lsl_admin import (  # noqa: E402
    PC_ANDROID_LSL_ADMIN_OUTBOX,
    PC_ANDROID_LSL_ADMIN_ROW_SCHEMA,
    PC_ANDROID_LSL_ADMIN_STATUS,
    PC_ANDROID_LSL_ADMIN_STATUS_SCHEMA,
)
from peripersonal_space_toolkit.android_lsl_monitor import (  # noqa: E402
    PC_ANDROID_LSL_MONITOR_EVENTS,
    PC_ANDROID_LSL_MONITOR_REPORT,
    PC_ANDROID_LSL_MONITOR_REPORT_SCHEMA,
    PC_ANDROID_LSL_MONITOR_ROW_SCHEMA,
    PC_ANDROID_LSL_MONITOR_STATUS,
    PC_ANDROID_LSL_MONITOR_STATUS_SCHEMA,
)
from peripersonal_space_toolkit.timing_events import (  # noqa: E402
    LSL_MARKER_CHANNELS,
    LSL_NUMERIC_STREAM_NAME,
    LSL_STREAM_NAME,
    MARKER_VERSION,
)


ANDROID_LSL_RUNTIME_STATUS_SCHEMA = "pps-android-lsl-runtime-status.v1"
ANDROID_PHONE_RUN_CATALOG_ENTRY_SCHEMA = "pps-android-phone-run-catalog-entry.v1"
ANDROID_PHONE_RUN_CATALOG_ENTRY = "phone_run_catalog_entry.json"
ANDROID_CONTROLLER_RUNTIME_STATUS_SCHEMA = "pps-android-controller-runtime-status.v1"
ANDROID_CONTROLLER_COMMAND_ROW_SCHEMA = "pps-android-controller-command-row.v1"
EXPECTED_STREAMS = {
    "rich_markers": "PPSMarkersV2",
    "numeric_triggers": "PPSTriggerCodes",
    "command_signals": LSL_COMMAND_STREAM_NAME,
    "command_acks": LSL_ACK_STREAM_NAME,
}
EXPECTED_CONTROLLER_STREAMS = {
    "command_signals": LSL_COMMAND_STREAM_NAME,
    "command_acks": LSL_ACK_STREAM_NAME,
}
EXPECTED_PC_ADMIN_STREAMS = {
    "command_signals": LSL_COMMAND_STREAM_NAME,
    "command_acks": LSL_ACK_STREAM_NAME,
}
EXPECTED_PC_MONITOR_STREAMS = {
    "rich_markers": LSL_STREAM_NAME,
    "numeric_triggers": LSL_NUMERIC_STREAM_NAME,
    "command_acks": LSL_ACK_STREAM_NAME,
    "command_signals": LSL_COMMAND_STREAM_NAME,
}


@dataclass(frozen=True)
class AndroidLslValidationResult:
    ok: bool
    source_path: str
    status: dict[str, Any]
    failures: list[str]
    warnings: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "pps-android-lsl-runtime-artifact-validation.v1",
            "ok": self.ok,
            "source_path": self.source_path,
            "failures": self.failures,
            "warnings": self.warnings,
            "status": self.status,
        }


def validate_runtime_status(
    status: dict[str, Any],
    *,
    source_path: str = "",
    completion: dict[str, Any] | None = None,
    catalog_entry: dict[str, Any] | None = None,
    expect_native_transport: bool = False,
    expect_run_catalog: bool = False,
) -> AndroidLslValidationResult:
    failures: list[str] = []
    warnings: list[str] = []
    if status.get("schema") != ANDROID_LSL_RUNTIME_STATUS_SCHEMA:
        failures.append("lsl_runtime_status schema mismatch")

    streams = status.get("streams") if isinstance(status.get("streams"), dict) else {}
    for key, expected in EXPECTED_STREAMS.items():
        if streams.get(key) != expected:
            failures.append(f"stream {key} expected {expected!r}, got {streams.get(key)!r}")

    protocol = status.get("command_protocol") if isinstance(status.get("command_protocol"), dict) else {}
    _validate_command_protocol(protocol, failures)

    privacy = status.get("privacy") if isinstance(status.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("participant demographics must not be encoded in discoverable stream names")

    native_available = bool(status.get("native_transport_available"))
    marker_enabled = bool(status.get("native_marker_transport_enabled"))
    receiver_available = bool(status.get("command_receiver_available"))
    native_bridge = status.get("native_bridge") if isinstance(status.get("native_bridge"), dict) else {}
    marker_transport = native_bridge.get("marker_transport") if isinstance(native_bridge.get("marker_transport"), dict) else {}
    command_transport = native_bridge.get("command_transport") if isinstance(native_bridge.get("command_transport"), dict) else {}
    if expect_native_transport:
        if not native_available:
            failures.append("native Android LSL transport was expected but is not available")
        if not marker_enabled:
            failures.append("native Android LSL marker transport was expected but is not enabled")
        if not marker_transport:
            failures.append("native bridge marker_transport status is missing")
        elif marker_transport.get("enabled") is not True:
            failures.append("native bridge marker_transport is not enabled")
        if not receiver_available:
            failures.append("native command receiver was expected but is not available")
        if not command_transport:
            failures.append("native bridge command_transport status is missing")
        elif command_transport.get("enabled") is not True:
            failures.append("native bridge command_transport is not enabled")
    elif native_available:
        warnings.append("native Android LSL transport is marked available; rerun with --expect-native-transport for strict checks")
    elif not str(status.get("reason") or "").strip():
        failures.append("missing reason for unavailable native Android LSL transport")

    if completion:
        embedded = completion.get("lsl_runtime_status")
        if isinstance(embedded, dict):
            if embedded.get("schema") != status.get("schema"):
                failures.append("completion.json embedded LSL status schema differs from lsl_runtime_status.json")
            embedded_streams = embedded.get("streams") if isinstance(embedded.get("streams"), dict) else {}
            if embedded_streams and embedded_streams != streams:
                failures.append("completion.json embedded LSL streams differ from lsl_runtime_status.json")
        else:
            warnings.append("completion/latest-events artifact does not embed lsl_runtime_status")

    _validate_phone_run_catalog_entry(status, catalog_entry, failures, warnings, expect_run_catalog=expect_run_catalog)

    return AndroidLslValidationResult(
        ok=not failures,
        source_path=source_path,
        status=status,
        failures=failures,
        warnings=warnings,
    )


def validate_controller_status(
    status: dict[str, Any],
    *,
    source_path: str = "",
    outbox_rows: list[dict[str, Any]] | None = None,
    expect_native_transport: bool = False,
    expect_command_acks: bool = False,
) -> AndroidLslValidationResult:
    failures: list[str] = []
    warnings: list[str] = []
    if status.get("schema") != ANDROID_CONTROLLER_RUNTIME_STATUS_SCHEMA:
        failures.append("phone_controller_runtime_status schema mismatch")
    if status.get("role") != "controller":
        failures.append("controller runtime status must declare role='controller'")

    streams = status.get("streams") if isinstance(status.get("streams"), dict) else {}
    for key, expected in EXPECTED_CONTROLLER_STREAMS.items():
        if streams.get(key) != expected:
            failures.append(f"controller stream {key} expected {expected!r}, got {streams.get(key)!r}")

    protocol = status.get("command_protocol") if isinstance(status.get("command_protocol"), dict) else {}
    _validate_command_protocol(protocol, failures)

    native_available = bool(status.get("native_transport_available"))
    controller_enabled = bool(status.get("native_controller_transport_enabled"))
    native_bridge = status.get("native_bridge") if isinstance(status.get("native_bridge"), dict) else {}
    controller_transport = native_bridge.get("controller_transport") if isinstance(native_bridge.get("controller_transport"), dict) else {}
    if expect_native_transport:
        if not native_available:
            failures.append("native Android LSL transport was expected for controller mode but is not available")
        if not controller_enabled:
            failures.append("native Android LSL controller transport was expected but is not enabled")
        if not controller_transport:
            failures.append("native bridge controller_transport status is missing")
        elif controller_transport.get("enabled") is not True:
            failures.append("native bridge controller_transport is not enabled")
    elif native_available:
        warnings.append("native Android LSL controller transport is marked available; rerun with --expect-native-transport for strict checks")
    elif not str(status.get("reason") or "").strip():
        failures.append("missing reason for unavailable native Android LSL controller transport")

    for index, row in enumerate(outbox_rows or [], start=1):
        _validate_controller_outbox_row(
            row,
            row_index=index,
            failures=failures,
            expect_native_transport=expect_native_transport,
            expect_command_acks=expect_command_acks,
        )

    return AndroidLslValidationResult(
        ok=not failures,
        source_path=source_path,
        status=status,
        failures=failures,
        warnings=warnings,
    )


def validate_pc_admin_status(
    status: dict[str, Any],
    *,
    source_path: str = "",
    outbox_rows: list[dict[str, Any]] | None = None,
    expect_native_transport: bool = False,
    expect_command_acks: bool = False,
) -> AndroidLslValidationResult:
    failures: list[str] = []
    warnings: list[str] = []
    if status.get("schema") != PC_ANDROID_LSL_ADMIN_STATUS_SCHEMA:
        failures.append("pc_android_lsl_admin_status schema mismatch")
    if status.get("role") != "pc_android_lsl_admin":
        failures.append("PC Android LSL admin status must declare role='pc_android_lsl_admin'")

    streams = status.get("streams") if isinstance(status.get("streams"), dict) else {}
    for key, expected in EXPECTED_PC_ADMIN_STREAMS.items():
        if streams.get(key) != expected:
            failures.append(f"PC admin stream {key} expected {expected!r}, got {streams.get(key)!r}")

    protocol = status.get("command_protocol") if isinstance(status.get("command_protocol"), dict) else {}
    _validate_command_protocol(protocol, failures)

    if status.get("native_transport") != "liblsl":
        message = "PC Android LSL admin status does not report native_transport='liblsl'"
        if expect_native_transport:
            failures.append(message)
        else:
            warnings.append(message)

    rows = outbox_rows or []
    if (expect_native_transport or expect_command_acks) and not rows:
        failures.append("PC admin strict validation requires at least one command outbox row")

    for index, row in enumerate(rows, start=1):
        _validate_pc_admin_outbox_row(
            row,
            row_index=index,
            failures=failures,
            expect_native_transport=expect_native_transport,
            expect_command_acks=expect_command_acks,
        )

    return AndroidLslValidationResult(
        ok=not failures,
        source_path=source_path,
        status=status,
        failures=failures,
        warnings=warnings,
    )


def validate_pc_monitor_report(
    report: dict[str, Any],
    *,
    source_path: str = "",
    event_rows: list[dict[str, Any]] | None = None,
    expect_native_transport: bool = False,
    expect_command_acks: bool = False,
) -> AndroidLslValidationResult:
    failures: list[str] = []
    warnings: list[str] = []
    if report.get("schema") != PC_ANDROID_LSL_MONITOR_REPORT_SCHEMA:
        failures.append("pc_android_lsl_monitor_report schema mismatch")
    if report.get("role") != "pc_android_lsl_monitor":
        failures.append("PC Android LSL monitor report must declare role='pc_android_lsl_monitor'")
    if report.get("native_transport") != "liblsl":
        failures.append("PC Android LSL monitor report must declare native_transport='liblsl'")

    status = report.get("status") if isinstance(report.get("status"), dict) else {}
    if status:
        if status.get("schema") != PC_ANDROID_LSL_MONITOR_STATUS_SCHEMA:
            failures.append("embedded PC Android LSL monitor status schema mismatch")
        streams = status.get("streams") if isinstance(status.get("streams"), dict) else {}
        for key, expected in EXPECTED_PC_MONITOR_STREAMS.items():
            if streams.get(key) != expected:
                failures.append(f"PC monitor stream {key} expected {expected!r}, got {streams.get(key)!r}")
        protocol = status.get("command_protocol") if isinstance(status.get("command_protocol"), dict) else {}
        _validate_command_protocol(protocol, failures, token_field="token_required_for_commands")
        marker_protocol = status.get("marker_protocol") if isinstance(status.get("marker_protocol"), dict) else {}
        if marker_protocol.get("marker_version") != MARKER_VERSION:
            failures.append("PC monitor marker_version does not match PPSMarkersV2")
        if list(marker_protocol.get("rich_marker_channels") or []) != list(LSL_MARKER_CHANNELS):
            failures.append("PC monitor rich marker channel order does not match PPSMarkersV2")
    else:
        failures.append("PC Android LSL monitor report is missing embedded status")

    rows = event_rows or []
    stream_counts = report.get("stream_counts") if isinstance(report.get("stream_counts"), dict) else {}
    if not rows and stream_counts and sum(int(stream_counts.get(key) or 0) for key in EXPECTED_PC_MONITOR_STREAMS) > 0:
        warnings.append("PC monitor report has nonzero stream counts but event rows were not loaded")
    if (expect_native_transport or expect_command_acks) and not rows:
        failures.append("PC monitor strict validation requires monitor event rows")
    for index, row in enumerate(rows, start=1):
        _validate_pc_monitor_event_row(row, row_index=index, failures=failures)

    effective_counts = dict(stream_counts)
    if rows:
        effective_counts = {key: 0 for key in ("rich_markers", "numeric_triggers", "command_acks")}
        for row in rows:
            key = str(row.get("stream_key") or "")
            if key in effective_counts:
                effective_counts[key] += 1

    if expect_native_transport:
        if int(effective_counts.get("rich_markers") or 0) <= 0:
            failures.append("PC monitor strict validation expected at least one PPSMarkersV2 sample")
        if int(effective_counts.get("numeric_triggers") or 0) <= 0:
            failures.append("PC monitor strict validation expected at least one PPSTriggerCodes sample")
    elif int(effective_counts.get("rich_markers") or 0) <= 0:
        warnings.append("PC monitor did not observe PPSMarkersV2 samples; rerun with --expect-native-transport for strict checks")

    if expect_command_acks and int(effective_counts.get("command_acks") or 0) <= 0:
        failures.append("PC monitor strict ack validation expected at least one PPSCommandAcksV1 sample")

    missing_required = list(report.get("missing_required_streams") or [])
    if missing_required:
        failures.append(f"PC monitor missing required streams: {', '.join(str(item) for item in missing_required)}")

    return AndroidLslValidationResult(
        ok=not failures,
        source_path=source_path,
        status=report,
        failures=failures,
        warnings=warnings,
    )


def validate_run_artifact(
    path: Path,
    *,
    expect_native_transport: bool = False,
    expect_command_acks: bool = False,
    expect_run_catalog: bool = False,
) -> AndroidLslValidationResult:
    loaded = _load_status_inputs(path)
    if loaded.get("kind") == "controller":
        return validate_controller_status(
            loaded["status"],
            source_path=str(path),
            outbox_rows=loaded.get("outbox_rows") or [],
            expect_native_transport=expect_native_transport,
            expect_command_acks=expect_command_acks,
        )
    if loaded.get("kind") == "pc_admin":
        return validate_pc_admin_status(
            loaded["status"],
            source_path=str(path),
            outbox_rows=loaded.get("outbox_rows") or [],
            expect_native_transport=expect_native_transport,
            expect_command_acks=expect_command_acks,
        )
    if loaded.get("kind") == "pc_monitor":
        return validate_pc_monitor_report(
            loaded["status"],
            source_path=str(path),
            event_rows=loaded.get("event_rows") or [],
            expect_native_transport=expect_native_transport,
            expect_command_acks=expect_command_acks,
        )
    return validate_runtime_status(
        loaded["status"],
        source_path=str(path),
        completion=loaded.get("completion"),
        catalog_entry=loaded.get("catalog_entry"),
        expect_native_transport=expect_native_transport,
        expect_run_catalog=expect_run_catalog,
    )


def _load_status_inputs(path: Path) -> dict[str, Any]:
    if path.is_dir():
        status_path = path / "lsl_runtime_status.json"
        if status_path.is_file():
            completion_path = path / "completion.json"
            if not completion_path.is_file():
                completion_path = path / "latest_events.json"
            catalog_path = path / ANDROID_PHONE_RUN_CATALOG_ENTRY
            return {
                "kind": "runner",
                "status": _read_json(status_path),
                "completion": _read_json(completion_path) if completion_path.is_file() else None,
                "catalog_entry": _read_json(catalog_path) if catalog_path.is_file() else None,
            }
        controller_status_path = path / "phone_controller_runtime_status.json"
        if controller_status_path.is_file():
            outbox_path = path / "phone_controller_command_outbox.jsonl"
            return {
                "kind": "controller",
                "status": _read_json(controller_status_path),
                "outbox_rows": _read_jsonl(outbox_path) if outbox_path.is_file() else [],
            }
        pc_admin_status_path = path / PC_ANDROID_LSL_ADMIN_STATUS
        if pc_admin_status_path.is_file():
            outbox_path = path / PC_ANDROID_LSL_ADMIN_OUTBOX
            return {
                "kind": "pc_admin",
                "status": _read_json(pc_admin_status_path),
                "outbox_rows": _read_jsonl(outbox_path) if outbox_path.is_file() else [],
            }
        pc_monitor_report_path = path / PC_ANDROID_LSL_MONITOR_REPORT
        if pc_monitor_report_path.is_file():
            events_path = path / PC_ANDROID_LSL_MONITOR_EVENTS
            return {
                "kind": "pc_monitor",
                "status": _read_json(pc_monitor_report_path),
                "event_rows": _read_jsonl(events_path) if events_path.is_file() else [],
            }
        raise FileNotFoundError(
            f"Missing {status_path}, {controller_status_path}, {pc_admin_status_path}, or {pc_monitor_report_path}"
        )
    if path.suffix.lower() == ".zip":
        return _load_from_zip(path)
    if path.suffix.lower() == ".jsonl":
        status_path = path.with_name("phone_controller_runtime_status.json")
        if status_path.is_file():
            return {
                "kind": "controller",
                "status": _read_json(status_path),
                "outbox_rows": _read_jsonl(path),
            }
        pc_admin_status_path = path.with_name(PC_ANDROID_LSL_ADMIN_STATUS)
        if pc_admin_status_path.is_file():
            return {
                "kind": "pc_admin",
                "status": _read_json(pc_admin_status_path),
                "outbox_rows": _read_jsonl(path),
            }
        pc_monitor_report_path = path.with_name(PC_ANDROID_LSL_MONITOR_REPORT)
        if pc_monitor_report_path.is_file() and path.name == PC_ANDROID_LSL_MONITOR_EVENTS:
            return {
                "kind": "pc_monitor",
                "status": _read_json(pc_monitor_report_path),
                "event_rows": _read_jsonl(path),
            }
        raise FileNotFoundError(f"Missing {status_path}, {pc_admin_status_path}, or {pc_monitor_report_path} beside JSONL artifact")
    data = _read_json(path)
    if data.get("schema") == ANDROID_LSL_RUNTIME_STATUS_SCHEMA:
        catalog_path = path.with_name(ANDROID_PHONE_RUN_CATALOG_ENTRY)
        return {
            "kind": "runner",
            "status": data,
            "completion": None,
            "catalog_entry": _read_json(catalog_path) if catalog_path.is_file() else None,
        }
    if data.get("schema") == ANDROID_CONTROLLER_RUNTIME_STATUS_SCHEMA:
        outbox_path = path.with_name("phone_controller_command_outbox.jsonl")
        return {
            "kind": "controller",
            "status": data,
            "outbox_rows": _read_jsonl(outbox_path) if outbox_path.is_file() else [],
        }
    if data.get("schema") == PC_ANDROID_LSL_ADMIN_STATUS_SCHEMA:
        outbox_path = path.with_name(PC_ANDROID_LSL_ADMIN_OUTBOX)
        return {
            "kind": "pc_admin",
            "status": data,
            "outbox_rows": _read_jsonl(outbox_path) if outbox_path.is_file() else [],
        }
    if data.get("schema") == PC_ANDROID_LSL_MONITOR_REPORT_SCHEMA:
        events_path = path.with_name(PC_ANDROID_LSL_MONITOR_EVENTS)
        return {
            "kind": "pc_monitor",
            "status": data,
            "event_rows": _read_jsonl(events_path) if events_path.is_file() else [],
        }
    if data.get("schema") == PC_ANDROID_LSL_MONITOR_STATUS_SCHEMA:
        report_path = path.with_name(PC_ANDROID_LSL_MONITOR_REPORT)
        events_path = path.with_name(PC_ANDROID_LSL_MONITOR_EVENTS)
        if not report_path.is_file():
            raise FileNotFoundError(f"Missing {report_path} beside PC Android monitor status")
        return {
            "kind": "pc_monitor",
            "status": _read_json(report_path),
            "event_rows": _read_jsonl(events_path) if events_path.is_file() else [],
        }
    embedded = data.get("lsl_runtime_status")
    if isinstance(embedded, dict):
        catalog_entry = data.get("phone_run_catalog_entry") if isinstance(data.get("phone_run_catalog_entry"), dict) else None
        if catalog_entry is None:
            catalog_path = path.with_name(ANDROID_PHONE_RUN_CATALOG_ENTRY)
            catalog_entry = _read_json(catalog_path) if catalog_path.is_file() else None
        return {"kind": "runner", "status": embedded, "completion": data, "catalog_entry": catalog_entry}
    raise ValueError(
        f"{path} is not an Android LSL status, completion, controller status, controller outbox, "
        "PC Android admin status/outbox, or PC Android LSL monitor artifact"
    )


def _load_from_zip(path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="pps-android-lsl-") as temp_dir:
        temp_root = Path(temp_dir)
        with zipfile.ZipFile(path) as archive:
            status_members = [name for name in archive.namelist() if name.endswith("lsl_runtime_status.json")]
            if not status_members:
                raise FileNotFoundError("ZIP does not contain lsl_runtime_status.json")
            status_name = sorted(status_members)[0]
            completion_members = [
                name for name in archive.namelist() if name.endswith("completion.json") or name.endswith("latest_events.json")
            ]
            catalog_members = [name for name in archive.namelist() if name.endswith(ANDROID_PHONE_RUN_CATALOG_ENTRY)]
            archive.extract(status_name, temp_root)
            completion = None
            if completion_members:
                completion_name = sorted(completion_members)[0]
                archive.extract(completion_name, temp_root)
                completion = _read_json(temp_root / completion_name)
            catalog_entry = None
            if catalog_members:
                catalog_name = sorted(catalog_members)[0]
                archive.extract(catalog_name, temp_root)
                catalog_entry = _read_json(temp_root / catalog_name)
            return {
                "kind": "runner",
                "status": _read_json(temp_root / status_name),
                "completion": completion,
                "catalog_entry": catalog_entry,
            }


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


def _validate_command_protocol(protocol: dict[str, Any], failures: list[str], *, token_field: str = "token_required") -> None:
    if protocol.get("command_schema") != COMMAND_SCHEMA:
        failures.append("command schema does not match PC runner protocol")
    if protocol.get("ack_schema") != ACK_SCHEMA:
        failures.append("ack schema does not match PC runner protocol")
    if list(protocol.get("command_channels") or []) != list(LSL_COMMAND_CHANNELS):
        failures.append("command channel order does not match PC runner protocol")
    if list(protocol.get("ack_channels") or []) != list(LSL_ACK_CHANNELS):
        failures.append("ack channel order does not match PC runner protocol")
    if protocol.get(token_field) is not True:
        failures.append("command protocol must require the pairing token")


def _validate_phone_run_catalog_entry(
    status: dict[str, Any],
    catalog_entry: dict[str, Any] | None,
    failures: list[str],
    warnings: list[str],
    *,
    expect_run_catalog: bool,
) -> None:
    if not catalog_entry:
        message = "phone run catalog entry is missing"
        if expect_run_catalog:
            failures.append(message)
        else:
            warnings.append(f"{message}; rerun with --expect-run-catalog for strict checks")
        return
    if catalog_entry.get("schema") != ANDROID_PHONE_RUN_CATALOG_ENTRY_SCHEMA:
        failures.append("phone run catalog entry schema mismatch")
    privacy = catalog_entry.get("privacy") if isinstance(catalog_entry.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("phone run catalog entry must keep demographics out of stream names")

    for field in (
        "package_id",
        "run_id",
        "participant_id",
        "session_id",
        "session_group_id",
        "part_session_id",
        "part_number",
    ):
        expected = str(status.get(field) or "").strip()
        observed = str(catalog_entry.get(field) or "").strip()
        if expected and observed and expected != observed:
            failures.append(f"phone run catalog entry {field} differs from lsl_runtime_status")

    bool_fields = {
        "native_lsl_transport_available": "native_transport_available",
        "native_lsl_marker_transport_enabled": "native_marker_transport_enabled",
        "native_lsl_command_receiver_available": "command_receiver_available",
    }
    for catalog_field, status_field in bool_fields.items():
        if status_field in status and catalog_field in catalog_entry:
            if bool(catalog_entry.get(catalog_field)) != bool(status.get(status_field)):
                failures.append(f"phone run catalog entry {catalog_field} differs from lsl_runtime_status")
    if not str(catalog_entry.get("artifact_file") or "").strip():
        failures.append("phone run catalog entry is missing artifact_file")
    reconstruction = catalog_entry.get("reconstruction") if isinstance(catalog_entry.get("reconstruction"), dict) else {}
    if not str(reconstruction.get("schedule_hash") or "").strip():
        warnings.append("phone run catalog entry does not include a reconstruction schedule_hash")


def _validate_controller_outbox_row(
    row: dict[str, Any],
    *,
    row_index: int,
    failures: list[str],
    expect_native_transport: bool,
    expect_command_acks: bool,
) -> None:
    prefix = f"controller outbox row {row_index}"
    if row.get("schema") != ANDROID_CONTROLLER_COMMAND_ROW_SCHEMA:
        failures.append(f"{prefix} schema mismatch")
    sample = list(row.get("command_sample") or [])
    if len(sample) != len(LSL_COMMAND_CHANNELS):
        failures.append(f"{prefix} command sample channel count mismatch")
        return
    if sample[0] != COMMAND_SCHEMA:
        failures.append(f"{prefix} command sample schema mismatch")
    if row.get("command_id") and sample[1] != row.get("command_id"):
        failures.append(f"{prefix} command_id differs from command sample")
    if row.get("target_session_id") and sample[2] != row.get("target_session_id"):
        failures.append(f"{prefix} target_session_id differs from command sample")
    if sample[3] != "android_controller":
        failures.append(f"{prefix} sender_id must be android_controller")
    if row.get("command") and sample[4] != row.get("command"):
        failures.append(f"{prefix} command differs from command sample")
    payload = _parse_json_object(sample[6], f"{prefix} command payload", failures)
    if payload is not None:
        token = str(payload.get("token") or payload.get("companion_token") or "")
        if not token:
            failures.append(f"{prefix} command payload is missing the pairing token")
    if expect_native_transport and row.get("native_lsl_sent") is not True:
        failures.append(f"{prefix} was expected to send over native LSL")
    if expect_command_acks:
        if row.get("ack_received") is not True:
            failures.append(f"{prefix} was expected to receive a matching command ack")
        ack_sample = list(row.get("ack_sample") or [])
        if len(ack_sample) != len(LSL_ACK_CHANNELS):
            failures.append(f"{prefix} ack sample channel count mismatch")
        else:
            if ack_sample[0] != ACK_SCHEMA:
                failures.append(f"{prefix} ack sample schema mismatch")
            if ack_sample[1] != sample[1]:
                failures.append(f"{prefix} ack command_id does not match command sample")


def _validate_pc_admin_outbox_row(
    row: dict[str, Any],
    *,
    row_index: int,
    failures: list[str],
    expect_native_transport: bool,
    expect_command_acks: bool,
) -> None:
    prefix = f"PC admin outbox row {row_index}"
    if row.get("schema") != PC_ANDROID_LSL_ADMIN_ROW_SCHEMA:
        failures.append(f"{prefix} schema mismatch")
    sample = list(row.get("command_sample") or [])
    if len(sample) != len(LSL_COMMAND_CHANNELS):
        failures.append(f"{prefix} command sample channel count mismatch")
        return
    if sample[0] != COMMAND_SCHEMA:
        failures.append(f"{prefix} command sample schema mismatch")
    if row.get("command_id") and sample[1] != row.get("command_id"):
        failures.append(f"{prefix} command_id differs from command sample")
    if row.get("target_session_id") and sample[2] != row.get("target_session_id"):
        failures.append(f"{prefix} target_session_id differs from command sample")
    if not str(sample[3]).strip():
        failures.append(f"{prefix} sender_id is empty")
    if row.get("sender_id") and sample[3] != row.get("sender_id"):
        failures.append(f"{prefix} sender_id differs from command sample")
    if row.get("command") and sample[4] != row.get("command"):
        failures.append(f"{prefix} command differs from command sample")
    payload = _parse_json_object(sample[6], f"{prefix} command payload", failures)
    if payload is not None:
        token = str(payload.get("token") or payload.get("companion_token") or "")
        if not token:
            failures.append(f"{prefix} command payload is missing the pairing token")
    if expect_native_transport and row.get("native_lsl_sent") is not True:
        failures.append(f"{prefix} was expected to send over native LSL")
    if expect_command_acks:
        if row.get("ack_received") is not True:
            failures.append(f"{prefix} was expected to receive a matching command ack")
        ack_sample = list(row.get("ack_sample") or [])
        if len(ack_sample) != len(LSL_ACK_CHANNELS):
            failures.append(f"{prefix} ack sample channel count mismatch")
        else:
            if ack_sample[0] != ACK_SCHEMA:
                failures.append(f"{prefix} ack sample schema mismatch")
            if ack_sample[1] != sample[1]:
                failures.append(f"{prefix} ack command_id does not match command sample")


def _validate_pc_monitor_event_row(row: dict[str, Any], *, row_index: int, failures: list[str]) -> None:
    prefix = f"PC monitor event row {row_index}"
    if row.get("schema") != PC_ANDROID_LSL_MONITOR_ROW_SCHEMA:
        failures.append(f"{prefix} schema mismatch")
    stream_key = str(row.get("stream_key") or "")
    sample = list(row.get("sample") or [])
    channel_labels = list(row.get("channel_labels") or [])
    if stream_key == "rich_markers":
        if row.get("stream_name") != LSL_STREAM_NAME:
            failures.append(f"{prefix} rich marker stream_name mismatch")
        if channel_labels != list(LSL_MARKER_CHANNELS):
            failures.append(f"{prefix} rich marker channel order mismatch")
        if len(sample) != len(LSL_MARKER_CHANNELS):
            failures.append(f"{prefix} rich marker sample channel count mismatch")
            return
        if str(sample[0]) != MARKER_VERSION:
            failures.append(f"{prefix} rich marker version mismatch")
        if row.get("event_type") and str(sample[2]) != str(row.get("event_type")):
            failures.append(f"{prefix} event_type differs from sample")
    elif stream_key == "numeric_triggers":
        if row.get("stream_name") != LSL_NUMERIC_STREAM_NAME:
            failures.append(f"{prefix} numeric trigger stream_name mismatch")
        if channel_labels != ["event_code"]:
            failures.append(f"{prefix} numeric trigger channel order mismatch")
        if len(sample) != 1:
            failures.append(f"{prefix} numeric trigger sample channel count mismatch")
        else:
            try:
                sample_code = int(float(sample[0]))
                row_code = int(row.get("event_code") or 0)
            except (TypeError, ValueError):
                failures.append(f"{prefix} numeric trigger sample is not an integer code")
            else:
                if str(row.get("event_code") or "") and sample_code != row_code:
                    failures.append(f"{prefix} event_code differs from sample")
    elif stream_key == "command_acks":
        if row.get("stream_name") != LSL_ACK_STREAM_NAME:
            failures.append(f"{prefix} command ack stream_name mismatch")
        if channel_labels != list(LSL_ACK_CHANNELS):
            failures.append(f"{prefix} command ack channel order mismatch")
        if len(sample) != len(LSL_ACK_CHANNELS):
            failures.append(f"{prefix} command ack sample channel count mismatch")
            return
        if sample[0] != ACK_SCHEMA:
            failures.append(f"{prefix} command ack schema mismatch")
        if row.get("command_id") and sample[1] != row.get("command_id"):
            failures.append(f"{prefix} command_id differs from ack sample")
    else:
        failures.append(f"{prefix} unsupported stream_key {stream_key!r}")


def _parse_json_object(raw: str, label: str, failures: list[str]) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError as error:
        failures.append(f"{label} is not valid JSON: {error.msg}")
        return None
    if not isinstance(parsed, dict):
        failures.append(f"{label} must be a JSON object")
        return None
    return parsed


def _write_report(result: AndroidLslValidationResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_json = output_dir / "android_lsl_runtime_artifact_validation.json"
    report_md = output_dir / "android_lsl_runtime_artifact_validation.md"
    is_controller = result.status.get("schema") == ANDROID_CONTROLLER_RUNTIME_STATUS_SCHEMA
    is_pc_admin = result.status.get("schema") == PC_ANDROID_LSL_ADMIN_STATUS_SCHEMA
    is_pc_monitor = result.status.get("schema") == PC_ANDROID_LSL_MONITOR_REPORT_SCHEMA
    report_json.write_text(json.dumps(result.to_json(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Android LSL Runtime Artifact Validation",
        "",
        f"- Source: `{result.source_path}`",
        f"- Result: `{'PASS' if result.ok else 'FAIL'}`",
    ]
    if is_pc_monitor:
        lines.extend(
            [
                f"- Native transport: `{result.status.get('native_transport', '')}`",
                f"- Role: `{result.status.get('role', '')}`",
                f"- Current PC source behavior: `{result.status.get('current_pc_source_behavior', '')}`",
                f"- Stream counts: `{json.dumps(result.status.get('stream_counts') or {}, sort_keys=True)}`",
                "",
            ]
        )
    elif is_pc_admin:
        lines.extend(
            [
                f"- Native transport: `{result.status.get('native_transport', '')}`",
                f"- Role: `{result.status.get('role', '')}`",
                f"- Current PC source behavior: `{result.status.get('current_pc_source_behavior', '')}`",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"- Native transport available: `{bool(result.status.get('native_transport_available'))}`",
                (
                    f"- Native controller transport enabled: `{bool(result.status.get('native_controller_transport_enabled'))}`"
                    if is_controller
                    else f"- Native marker transport enabled: `{bool(result.status.get('native_marker_transport_enabled'))}`"
                ),
                (
                    f"- Role: `{result.status.get('role', '')}`"
                    if is_controller
                    else f"- Command receiver available: `{bool(result.status.get('command_receiver_available'))}`"
                ),
                f"- Current Android source behavior: `{result.status.get('current_android_source_behavior', '')}`",
                "",
            ]
        )
    if result.failures:
        lines.extend(["## Failures", *[f"- {item}" for item in result.failures], ""])
    if result.warnings:
        lines.extend(["## Warnings", *[f"- {item}" for item in result.warnings], ""])
    report_md.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "artifact",
        type=Path,
        help=(
            "Phone run folder, ZIP, completion JSON, lsl_runtime_status.json, "
            "phone_controller_runtime_status.json, phone_controller_command_outbox.jsonl, "
            "pc_android_lsl_admin_status.json, pc_android_lsl_command_outbox.jsonl, "
            "or pc_android_lsl_monitor_report.json/events JSONL."
        ),
    )
    parser.add_argument("--expect-native-transport", action="store_true", help="Fail unless native Android LSL transport is active.")
    parser.add_argument(
        "--expect-command-acks",
        action="store_true",
        help="For controller, PC-admin, or monitor artifacts, fail unless matching command acknowledgements are present.",
    )
    parser.add_argument("--expect-run-catalog", action="store_true", help="For phone-run artifacts, fail unless phone_run_catalog_entry.json is present and consistent.")
    parser.add_argument("--output-dir", type=Path, help="Optional directory for JSON/Markdown validation reports.")
    args = parser.parse_args(argv)

    result = validate_run_artifact(
        args.artifact,
        expect_native_transport=args.expect_native_transport,
        expect_command_acks=args.expect_command_acks,
        expect_run_catalog=args.expect_run_catalog,
    )
    if args.output_dir:
        _write_report(result, args.output_dir)
    print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
