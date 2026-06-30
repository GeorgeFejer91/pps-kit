"""PC-side monitor for Android phone-owned PPS LSL streams."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import time
from typing import Any

from .lsl_command_ack import (
    ACK_SCHEMA,
    COMMAND_SCHEMA,
    LSL_ACK_CHANNELS,
    LSL_ACK_STREAM_NAME,
    LSL_ACK_STREAM_TYPE,
    LSL_COMMAND_CHANNELS,
    LSL_COMMAND_STREAM_NAME,
    LSL_COMMAND_STREAM_TYPE,
    LSLCommandAckError,
)
from .timing_events import (
    LSL_MARKER_CHANNELS,
    LSL_NUMERIC_STREAM_NAME,
    LSL_NUMERIC_STREAM_TYPE,
    LSL_STREAM_NAME,
    LSL_STREAM_TYPE,
    MARKER_VERSION,
)


PC_ANDROID_LSL_MONITOR_ROW_SCHEMA = "pps-pc-android-lsl-monitor-row.v1"
PC_ANDROID_LSL_MONITOR_REPORT_SCHEMA = "pps-pc-android-lsl-monitor-report.v1"
PC_ANDROID_LSL_MONITOR_STATUS_SCHEMA = "pps-pc-android-lsl-monitor-status.v1"
PC_ANDROID_LSL_MONITOR_EVENTS = "pc_android_lsl_monitor_events.jsonl"
PC_ANDROID_LSL_MONITOR_REPORT = "pc_android_lsl_monitor_report.json"
PC_ANDROID_LSL_MONITOR_STATUS = "pc_android_lsl_monitor_status.json"

STREAM_DEFINITIONS: dict[str, dict[str, Any]] = {
    "rich_markers": {
        "stream_name": LSL_STREAM_NAME,
        "stream_type": LSL_STREAM_TYPE,
        "channel_format": "string",
        "channel_labels": list(LSL_MARKER_CHANNELS),
        "first_channel_schema": MARKER_VERSION,
    },
    "numeric_triggers": {
        "stream_name": LSL_NUMERIC_STREAM_NAME,
        "stream_type": LSL_NUMERIC_STREAM_TYPE,
        "channel_format": "int32",
        "channel_labels": ["event_code"],
        "first_channel_schema": "",
    },
    "command_acks": {
        "stream_name": LSL_ACK_STREAM_NAME,
        "stream_type": LSL_ACK_STREAM_TYPE,
        "channel_format": "string",
        "channel_labels": list(LSL_ACK_CHANNELS),
        "first_channel_schema": ACK_SCHEMA,
    },
    "command_signals": {
        "stream_name": LSL_COMMAND_STREAM_NAME,
        "stream_type": LSL_COMMAND_STREAM_TYPE,
        "channel_format": "string",
        "channel_labels": list(LSL_COMMAND_CHANNELS),
        "first_channel_schema": COMMAND_SCHEMA,
    },
}


@dataclass(frozen=True)
class AndroidLslMonitorResult:
    report: dict[str, Any]
    rows: list[dict[str, Any]]
    events_path: Path | None = None
    report_path: Path | None = None
    status_path: Path | None = None

    @property
    def ok(self) -> bool:
        return bool(self.report.get("ok"))


def android_lsl_monitor_status() -> dict[str, Any]:
    """Return the static PC monitor status/contract."""

    return {
        "schema": PC_ANDROID_LSL_MONITOR_STATUS_SCHEMA,
        "role": "pc_android_lsl_monitor",
        "native_transport": "liblsl",
        "current_pc_source_behavior": "pc_native_lsl_monitor_with_local_event_log",
        "streams": {
            key: str(definition["stream_name"])
            for key, definition in STREAM_DEFINITIONS.items()
        },
        "stream_descriptions": pc_android_lsl_monitor_stream_descriptions(),
        "marker_protocol": {
            "marker_version": MARKER_VERSION,
            "rich_marker_channels": list(LSL_MARKER_CHANNELS),
            "numeric_trigger_channels": ["event_code"],
        },
        "command_protocol": {
            "command_schema": COMMAND_SCHEMA,
            "ack_schema": ACK_SCHEMA,
            "command_channels": list(LSL_COMMAND_CHANNELS),
            "ack_channels": list(LSL_ACK_CHANNELS),
            "token_required_for_commands": True,
            "monitor_requires_token": False,
        },
        "privacy": {
            "demographics_in_stream_name": False,
            "monitor_creates_participant_stream_names": False,
        },
        "evidence_boundary": (
            "network_lsl_monitoring_only_not_physical_timing_or_labrecorder_persistence_proof"
        ),
    }


def pc_android_lsl_monitor_stream_descriptions() -> dict[str, Any]:
    """Describe the LSL streams a PC monitor can observe without creating participant-coded names."""

    return {
        "schema": "pps-android-lsl-stream-descriptions.v1",
        "runtime_authority": "pc_runner",
        "role": "pc_android_lsl_monitor",
        "native_transport": "liblsl",
        "privacy": {
            "default": "metadata_payload_only",
            "demographics_in_stream_name": False,
            "participant_demographics_location": "metadata_and_payload_artifacts",
        },
        "rich_markers": {
            "name": LSL_STREAM_NAME,
            "type": LSL_STREAM_TYPE,
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_MARKER_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_pattern": "pps-android-markers-v2-*",
            "marker_version": MARKER_VERSION,
            "channel_labels": list(LSL_MARKER_CHANNELS),
        },
        "numeric_triggers": {
            "name": LSL_NUMERIC_STREAM_NAME,
            "type": LSL_NUMERIC_STREAM_TYPE,
            "role": "inlet",
            "channel_format": "int32",
            "channel_count": 1,
            "nominal_srate_hz": 0.0,
            "source_id_pattern": "pps-android-trigger-codes-*",
            "channel_labels": ["event_code"],
        },
        "command_acks": {
            "name": LSL_ACK_STREAM_NAME,
            "type": LSL_ACK_STREAM_TYPE,
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_ACK_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_pattern": "pps-android-command-acks-v1-*",
            "channel_labels": list(LSL_ACK_CHANNELS),
        },
        "command_signals": {
            "name": LSL_COMMAND_STREAM_NAME,
            "type": LSL_COMMAND_STREAM_TYPE,
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_COMMAND_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_patterns": [
                "pps-command-signals-v1-*-*",
                "pps-android-controller-signals-v1-*-*",
            ],
            "channel_labels": list(LSL_COMMAND_CHANNELS),
            "token_required": True,
        },
    }


def build_android_lsl_monitor_row(
    *,
    stream_key: str,
    sample: list[Any],
    lsl_timestamp: float,
    source_id: str = "",
    stream_name: str = "",
    pc_received_unix_ms: int | None = None,
    pc_received_perf_counter_s: float | None = None,
) -> dict[str, Any]:
    """Build one durable monitor row from an LSL sample."""

    definition = _definition_for_key(stream_key)
    values = list(sample)
    channel_labels = list(definition["channel_labels"])
    row: dict[str, Any] = {
        "schema": PC_ANDROID_LSL_MONITOR_ROW_SCHEMA,
        "stream_key": stream_key,
        "stream_name": stream_name or str(definition["stream_name"]),
        "stream_type": str(definition["stream_type"]),
        "source_id": str(source_id or ""),
        "lsl_timestamp": float(lsl_timestamp or 0.0),
        "pc_received_unix_ms": int(pc_received_unix_ms if pc_received_unix_ms is not None else time.time() * 1000),
        "pc_received_perf_counter_s": float(
            pc_received_perf_counter_s if pc_received_perf_counter_s is not None else time.perf_counter()
        ),
        "channel_labels": channel_labels,
        "sample": values,
    }
    if stream_key == "rich_markers":
        row.update(_rich_marker_summary(values))
    elif stream_key == "numeric_triggers":
        row["event_code"] = _safe_int(values[0] if values else "", default=0)
    elif stream_key == "command_acks":
        row.update(_command_ack_summary(values))
    elif stream_key == "command_signals":
        row.update(_command_signal_summary(values))
    return row


def build_android_lsl_monitor_report(
    rows: list[dict[str, Any]],
    *,
    started_unix_ms: int | None = None,
    finished_unix_ms: int | None = None,
    duration_s: float = 0.0,
    resolve_status: dict[str, Any] | None = None,
    required_streams: list[str] | None = None,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Summarize a bounded Android LSL monitoring window."""

    status = android_lsl_monitor_status()
    counts = {key: 0 for key in STREAM_DEFINITIONS}
    first_timestamps: dict[str, float] = {}
    last_timestamps: dict[str, float] = {}
    session_ids: set[str] = set()
    part_session_ids: set[str] = set()
    participant_ids: set[str] = set()
    commands_acked: set[str] = set()
    commands_observed: set[str] = set()
    command_names: dict[str, int] = {}
    command_ack_statuses: dict[str, int] = {}
    for row in rows:
        key = str(row.get("stream_key") or "")
        if key in counts:
            counts[key] += 1
        timestamp = _safe_float(row.get("lsl_timestamp"), default=0.0)
        if timestamp:
            first_timestamps.setdefault(key, timestamp)
            last_timestamps[key] = timestamp
        for field, target in (
            ("session_id", session_ids),
            ("part_session_id", part_session_ids),
            ("participant_id", participant_ids),
        ):
            value = str(row.get(field) or "").strip()
            if value:
                target.add(value)
        command_id = str(row.get("command_id") or "").strip()
        if key == "command_acks" and command_id:
            commands_acked.add(command_id)
            ack_status = str(row.get("ack_status") or "").strip() or "unknown"
            command_ack_statuses[ack_status] = command_ack_statuses.get(ack_status, 0) + 1
        if key == "command_signals" and command_id:
            commands_observed.add(command_id)
            command_name = str(row.get("command") or "").strip() or "unknown"
            command_names[command_name] = command_names.get(command_name, 0) + 1

    required = list(required_streams or [])
    missing_required = [key for key in required if counts.get(key, 0) <= 0]
    observed_without_ack = sorted(commands_observed - commands_acked)
    ack_without_observed_command = sorted(commands_acked - commands_observed)
    output_root = Path(output_dir).resolve() if output_dir is not None else None
    return {
        "schema": PC_ANDROID_LSL_MONITOR_REPORT_SCHEMA,
        "ok": not missing_required,
        "role": "pc_android_lsl_monitor",
        "native_transport": "liblsl",
        "current_pc_source_behavior": "pc_native_lsl_monitor_with_local_event_log",
        "started_unix_ms": int(started_unix_ms if started_unix_ms is not None else time.time() * 1000),
        "finished_unix_ms": int(finished_unix_ms if finished_unix_ms is not None else time.time() * 1000),
        "duration_s": float(duration_s),
        "required_streams": required,
        "missing_required_streams": missing_required,
        "stream_counts": counts,
        "first_lsl_timestamps": first_timestamps,
        "last_lsl_timestamps": last_timestamps,
        "observed_session_ids": sorted(session_ids),
        "observed_part_session_ids": sorted(part_session_ids),
        "observed_participant_ids": sorted(participant_ids),
        "observed_command_signal_ids": sorted(commands_observed),
        "observed_command_names": command_names,
        "observed_command_ack_ids": sorted(commands_acked),
        "observed_command_signal_ids_without_ack": observed_without_ack,
        "observed_command_ack_ids_without_signal": ack_without_observed_command,
        "observed_command_ack_statuses": command_ack_statuses,
        "resolve_status": dict(resolve_status or {}),
        "status": status,
        "events_file": str(output_root / PC_ANDROID_LSL_MONITOR_EVENTS) if output_root else "",
        "status_file": str(output_root / PC_ANDROID_LSL_MONITOR_STATUS) if output_root else "",
        "privacy": dict(status["privacy"]),
        "evidence_boundary": status["evidence_boundary"],
    }


def write_android_lsl_monitor_artifacts(
    output_dir: Path | str,
    rows: list[dict[str, Any]],
    *,
    report: dict[str, Any] | None = None,
) -> tuple[Path, Path, Path]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    events_path = output_root / PC_ANDROID_LSL_MONITOR_EVENTS
    with events_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    status_path = output_root / PC_ANDROID_LSL_MONITOR_STATUS
    status_path.write_text(json.dumps(android_lsl_monitor_status(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    resolved_report = dict(
        report
        or build_android_lsl_monitor_report(
            rows,
            output_dir=output_root,
        )
    )
    resolved_report["events_file"] = str(events_path.resolve())
    resolved_report["status_file"] = str(status_path.resolve())
    report_path = output_root / PC_ANDROID_LSL_MONITOR_REPORT
    report_path.write_text(json.dumps(resolved_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return events_path, report_path, status_path


def monitor_android_lsl_streams(
    *,
    duration_s: float = 10.0,
    output_dir: Path | str | None = None,
    resolve_timeout_s: float = 1.0,
    pull_timeout_s: float = 0.0,
    poll_interval_s: float = 0.01,
    stream_keys: list[str] | None = None,
    required_streams: list[str] | None = None,
    max_samples_per_stream: int = 10000,
) -> AndroidLslMonitorResult:
    """Resolve Android PPS streams and write a bounded PC-side monitor diary."""

    pylsl = _load_pylsl()
    selected_keys = stream_keys or list(STREAM_DEFINITIONS)
    for key in selected_keys:
        _definition_for_key(key)
    started_ms = int(time.time() * 1000)
    started_perf = time.perf_counter()
    rows: list[dict[str, Any]] = []
    inlets: dict[str, Any] = {}
    resolve_status: dict[str, Any] = {}
    for key in selected_keys:
        definition = _definition_for_key(key)
        stream_name = str(definition["stream_name"])
        try:
            infos = pylsl.resolve_byprop("name", stream_name, 1, float(resolve_timeout_s))
        except Exception as exc:  # noqa: BLE001 - retained in monitor report.
            infos = []
            resolve_status[key] = {"resolved": False, "stream_name": stream_name, "reason": str(exc)}
        if not infos:
            resolve_status.setdefault(
                key,
                {"resolved": False, "stream_name": stream_name, "reason": "stream_not_found"},
            )
            continue
        info = infos[0]
        source_id = _info_value(info, "source_id")
        try:
            inlet = _stream_inlet(pylsl, info, max_buflen=1, max_chunklen=1)
        except Exception as exc:  # noqa: BLE001 - retained in monitor report.
            resolve_status[key] = {
                "resolved": True,
                "stream_name": stream_name,
                "source_id": source_id,
                "inlet_open": False,
                "reason": str(exc),
            }
            continue
        inlets[key] = inlet
        resolve_status[key] = {
            "resolved": True,
            "stream_name": stream_name,
            "source_id": source_id,
            "inlet_open": True,
        }

    counts = {key: 0 for key in selected_keys}
    deadline = started_perf + max(0.0, float(duration_s))
    while time.perf_counter() <= deadline:
        pulled_any = False
        for key, inlet in list(inlets.items()):
            if counts.get(key, 0) >= int(max_samples_per_stream):
                continue
            sample, timestamp = _pull_sample(inlet, timeout_s=pull_timeout_s)
            if not sample:
                continue
            counts[key] = counts.get(key, 0) + 1
            pulled_any = True
            rows.append(
                build_android_lsl_monitor_row(
                    stream_key=key,
                    sample=list(sample),
                    lsl_timestamp=timestamp,
                    source_id=str(resolve_status.get(key, {}).get("source_id") or ""),
                    pc_received_unix_ms=int(time.time() * 1000),
                    pc_received_perf_counter_s=time.perf_counter(),
                )
            )
        if not pulled_any:
            time.sleep(max(0.0, float(poll_interval_s)))
    for inlet in inlets.values():
        close = getattr(inlet, "close_stream", None)
        if close is not None:
            try:
                close()
            except Exception:
                pass

    finished_ms = int(time.time() * 1000)
    report = build_android_lsl_monitor_report(
        rows,
        started_unix_ms=started_ms,
        finished_unix_ms=finished_ms,
        duration_s=time.perf_counter() - started_perf,
        resolve_status=resolve_status,
        required_streams=required_streams or [],
        output_dir=output_dir,
    )
    events_path = report_path = status_path = None
    if output_dir is not None:
        events_path, report_path, status_path = write_android_lsl_monitor_artifacts(output_dir, rows, report=report)
        report["events_file"] = str(events_path.resolve())
        report["status_file"] = str(status_path.resolve())
    return AndroidLslMonitorResult(
        report=report,
        rows=rows,
        events_path=events_path,
        report_path=report_path,
        status_path=status_path,
    )


def _definition_for_key(stream_key: str) -> dict[str, Any]:
    try:
        return STREAM_DEFINITIONS[str(stream_key)]
    except KeyError as exc:
        valid = ", ".join(sorted(STREAM_DEFINITIONS))
        raise ValueError(f"Unsupported Android LSL monitor stream {stream_key!r}; expected one of {valid}") from exc


def _rich_marker_summary(values: list[Any]) -> dict[str, Any]:
    padded = [str(value) for value in values] + [""] * max(0, len(LSL_MARKER_CHANNELS) - len(values))
    payload_json = padded[15] if len(padded) > 15 else ""
    return {
        "marker_version": padded[0],
        "event_id": padded[1],
        "event_type": padded[2],
        "event_code": _safe_int(padded[3], default=0),
        "trigger_key": padded[4],
        "marker_name": padded[5],
        "session_id": padded[6],
        "participant_id": padded[7],
        "session_group_id": padded[8],
        "part_session_id": padded[9],
        "part_number": padded[10],
        "block_index": padded[11],
        "trial_uid": padded[12],
        "sample_index": padded[13],
        "timestamp_quality": padded[14],
        "payload_json": payload_json,
    }


def _command_ack_summary(values: list[Any]) -> dict[str, Any]:
    padded = [str(value) for value in values] + [""] * max(0, len(LSL_ACK_CHANNELS) - len(values))
    payload_json = padded[9]
    row = {
        "ack_schema": padded[0],
        "command_id": padded[1],
        "session_id": padded[2],
        "receiver_id": padded[3],
        "ack_status": padded[4],
        "ack_reason": padded[5],
        "received_lsl_time": _safe_float(padded[6], default=0.0),
        "applied_lsl_time": _safe_float(padded[7], default=0.0),
        "ack_lsl_time": _safe_float(padded[8], default=0.0),
        "payload_json": payload_json,
    }
    row.update(_command_payload_identity_summary(payload_json))
    return row


def _command_signal_summary(values: list[Any]) -> dict[str, Any]:
    padded = [str(value) for value in values] + [""] * max(0, len(LSL_COMMAND_CHANNELS) - len(values))
    payload_json = padded[6]
    row = {
        "command_schema": padded[0],
        "command_id": padded[1],
        "session_id": padded[2],
        "sender_id": padded[3],
        "command": padded[4],
        "issued_lsl_time": _safe_float(padded[5], default=0.0),
        "payload_json": payload_json,
    }
    row.update(_command_payload_identity_summary(payload_json))
    return row


def _command_payload_identity_summary(payload_json: str) -> dict[str, str]:
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    fields = (
        "package_id",
        "participant_id",
        "target_session_id",
        "target_part_session_id",
        "target_session_group_id",
        "target_part_number",
        "requested_by",
        "current_android_source_behavior",
        "current_pc_source_behavior",
    )
    return {field: str(payload.get(field) or "") for field in fields if str(payload.get(field) or "").strip()}


def _load_pylsl() -> Any:
    try:
        import pylsl  # type: ignore
    except Exception as exc:
        raise LSLCommandAckError(f"pylsl is required for Android LSL monitoring: {exc}") from exc
    return pylsl


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


def _pull_sample(inlet: Any, *, timeout_s: float) -> tuple[list[Any] | None, float]:
    result = inlet.pull_sample(float(timeout_s))
    if isinstance(result, tuple) and len(result) == 2:
        sample, timestamp = result
        return sample, _safe_float(timestamp, default=0.0)
    return result, 0.0


def _info_value(info: Any, method_name: str) -> str:
    method = getattr(info, method_name, None)
    if method is None:
        return ""
    try:
        return str(method() or "")
    except Exception:
        return ""


def _safe_int(value: Any, *, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _stream_key_list(raw: str) -> list[str]:
    values = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    for value in values:
        _definition_for_key(value)
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration-s", type=float, default=10.0)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/android_lsl_monitor"))
    parser.add_argument("--resolve-timeout-s", type=float, default=1.0)
    parser.add_argument("--pull-timeout-s", type=float, default=0.0)
    parser.add_argument("--poll-interval-s", type=float, default=0.01)
    parser.add_argument("--stream-keys", type=_stream_key_list, default=list(STREAM_DEFINITIONS))
    parser.add_argument("--require-markers", action="store_true", help="Fail unless PPSMarkersV2 samples are observed.")
    parser.add_argument("--require-triggers", action="store_true", help="Fail unless PPSTriggerCodes samples are observed.")
    parser.add_argument("--require-acks", action="store_true", help="Fail unless PPSCommandAcksV1 samples are observed.")
    parser.add_argument("--require-commands", action="store_true", help="Fail unless PPSCommandSignalsV1 samples are observed.")
    args = parser.parse_args(argv)

    required: list[str] = []
    if args.require_markers:
        required.append("rich_markers")
    if args.require_triggers:
        required.append("numeric_triggers")
    if args.require_acks:
        required.append("command_acks")
    if args.require_commands:
        required.append("command_signals")
    result = monitor_android_lsl_streams(
        duration_s=args.duration_s,
        output_dir=args.output_dir,
        resolve_timeout_s=args.resolve_timeout_s,
        pull_timeout_s=args.pull_timeout_s,
        poll_interval_s=args.poll_interval_s,
        stream_keys=args.stream_keys,
        required_streams=required,
    )
    print(json.dumps(result.report, indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
