"""Validate Android phone-owned LSL runtime status artifacts."""

from __future__ import annotations

import argparse
import csv
import hashlib
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
ANDROID_PHONE_RUN_CATALOG_SCHEMA = "pps-android-phone-run-catalog.v1"
ANDROID_PHONE_RUN_CATALOG_ENTRY = "phone_run_catalog_entry.json"
ANDROID_PHONE_RUN_RECONSTRUCTION_ARTIFACT = "reconstruction_contract.json"
ANDROID_PHONE_PARTICIPANT_METADATA_SCHEMA = "pps-android-phone-participant-metadata.v1"
ANDROID_HAPTIC_CAPABILITY_SCHEMA = "pps-android-haptic-capability.v1"
ANDROID_HAPTIC_CALIBRATION_SCHEMA = "pps-android-phone-haptic-calibration.v1"
ANDROID_SCHEDULED_BLOCK_MATERIALIZATION_SCHEMA = "pps-android-phone-scheduled-block-materialization.v1"
ANDROID_PHONE_RESPONSE_LEDGER_SCHEMA = "pps-android-phone-response-ledger.v1"
ANDROID_PHONE_RESPONSE_SUMMARY_SCHEMA = "pps-android-phone-response-summary.v1"
ANDROID_PHONE_TOPUP_PLAN_SCHEMA = "pps-android-phone-topup-plan.v1"
ANDROID_PHONE_TOPUP_MATERIALIZATION_SCHEMA = "pps-android-phone-topup-materialization.v1"
ANDROID_PHONE_OWNED_DATA_EXPORT_SCHEMA = "pps-android-phone-owned-data-export.v1"
ANDROID_CONTROLLER_RUNTIME_STATUS_SCHEMA = "pps-android-controller-runtime-status.v1"
ANDROID_CONTROLLER_COMMAND_ROW_SCHEMA = "pps-android-controller-command-row.v1"
ANDROID_LSL_STREAM_DESCRIPTIONS_SCHEMA = "pps-android-lsl-stream-descriptions.v1"
ANDROID_AUDIO_TIMING_STRATEGY = "audiotrack_pcm_wav_playback_head"
ANDROID_CUE_AUDIO_SCHEDULER = "audiotrack_playback_head"
PHONE_RESPONSE_MIN_RT_MS = 100
PHONE_RESPONSE_MAX_RT_MS = 1300
PHONE_RESPONSE_POLICY = f"first_touch_{PHONE_RESPONSE_MIN_RT_MS}_{PHONE_RESPONSE_MAX_RT_MS}_ms_after_tactile"
PHONE_TOPUP_SYNTHESIS_STRATEGY = "pcm_wav_concat_without_ffmpeg"
PHONE_TOPUP_PLAN_STATUSES = {
    "not_needed",
    "skipped",
    "failed",
    "played",
    "materialized_not_played",
    "planned_not_played",
}
PHONE_TOPUP_MATERIALIZATION_STATUSES = {
    "materialized",
    "failed",
    "not_needed",
    "not_evaluated",
    "skipped",
}
PHONE_DATA_MIN_FIELDNAMES = [
    "participant_id",
    "session_id",
    "part_session_id",
    "part_number",
    "block_number",
    "block_label",
    "trial_number",
    "trial_number_global",
    "trial_uid",
    "condition",
    "phase",
    "noise_type",
    "trial_type",
    "soa_ms",
    "response_given",
    "hit_miss",
    "reaction_time_ms",
]
ANDROID_PHONE_EVENT_CODES = {
    "session_metadata": 8,
    "run_start": 1,
    "run_complete": 2,
    "block_start": 10,
    "block_complete": 11,
    "vibration_cue": 21,
    "tap": 30,
    "phone_scheduled_block_materialization": 34,
    "phone_topup_materialization": 35,
    "operator_command": 41,
    "phone_playback_pause": 42,
    "phone_playback_resume": 43,
    "phone_stop_after_block_request": 44,
    "phone_stop_after_block_boundary": 45,
}
ANDROID_UNKNOWN_EVENT_CODE = 500
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
    catalog_index: dict[str, Any] | None = None,
    catalog_runs_rows: list[dict[str, Any]] | None = None,
    catalog_latest_entries: list[dict[str, Any]] | None = None,
    package_manifest: dict[str, Any] | None = None,
    reconstruction_artifact: dict[str, Any] | None = None,
    participant_metadata: dict[str, Any] | None = None,
    haptic_capability: dict[str, Any] | None = None,
    event_rows: list[dict[str, Any]] | None = None,
    command_diary_rows: list[dict[str, Any]] | None = None,
    marker_mirror_rows: list[dict[str, Any]] | None = None,
    trigger_code_rows: list[dict[str, Any]] | None = None,
    materialization_manifests: list[dict[str, Any]] | None = None,
    materialized_wav_hashes: dict[str, str] | None = None,
    response_ledger_rows: list[dict[str, Any]] | None = None,
    topup_plan: dict[str, Any] | None = None,
    topup_materialization: dict[str, Any] | None = None,
    topup_wav_hashes: dict[str, str] | None = None,
    phone_owned_data_export: dict[str, Any] | None = None,
    phone_data_min_header: list[str] | None = None,
    phone_data_min_rows: list[dict[str, Any]] | None = None,
    phone_data_min_master_header: list[str] | None = None,
    phone_data_min_master_rows: list[dict[str, Any]] | None = None,
    phone_data_max_has_completion: bool = False,
    expect_native_transport: bool = False,
    expect_command_acks: bool = False,
    expect_run_catalog: bool = False,
    expect_run_catalog_index: bool = False,
    expect_event_diary: bool = False,
    expect_trigger_code_mirror: bool = False,
    expect_lightweight_materializations: bool = False,
    expect_phone_topup_evidence: bool = False,
    expect_audiotrack_timing_evidence: bool = False,
    expect_phone_owned_data_export: bool = False,
) -> AndroidLslValidationResult:
    failures: list[str] = []
    warnings: list[str] = []
    if status.get("schema") != ANDROID_LSL_RUNTIME_STATUS_SCHEMA:
        failures.append("lsl_runtime_status schema mismatch")

    streams = status.get("streams") if isinstance(status.get("streams"), dict) else {}
    for key, expected in EXPECTED_STREAMS.items():
        if streams.get(key) != expected:
            failures.append(f"stream {key} expected {expected!r}, got {streams.get(key)!r}")
    _validate_android_lsl_stream_descriptions(
        status=status,
        streams=streams,
        failures=failures,
        warnings=warnings,
        expect_native_transport=expect_native_transport,
    )

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
            embedded_descriptions = embedded.get("stream_descriptions") if isinstance(embedded.get("stream_descriptions"), dict) else {}
            descriptions = status.get("stream_descriptions") if isinstance(status.get("stream_descriptions"), dict) else {}
            if embedded_descriptions and descriptions and embedded_descriptions != descriptions:
                failures.append("completion.json embedded LSL stream descriptions differ from lsl_runtime_status.json")
        else:
            warnings.append("completion/latest-events artifact does not embed lsl_runtime_status")

    _validate_asset_strategy_consistency(
        status=status,
        completion=completion,
        catalog_entry=catalog_entry,
        package_manifest=package_manifest,
        reconstruction_artifact=reconstruction_artifact,
        failures=failures,
        warnings=warnings,
        expect_lightweight_materializations=expect_lightweight_materializations,
    )
    _validate_phone_run_catalog_entry(status, catalog_entry, failures, warnings, expect_run_catalog=expect_run_catalog)
    _validate_phone_run_catalog_index(
        status=status,
        catalog_entry=catalog_entry,
        catalog_index=catalog_index,
        catalog_runs_rows=catalog_runs_rows or [],
        catalog_latest_entries=catalog_latest_entries or [],
        failures=failures,
        warnings=warnings,
        expect_run_catalog_index=expect_run_catalog_index,
    )
    _validate_participant_and_haptic_metadata(
        status=status,
        completion=completion,
        catalog_entry=catalog_entry,
        participant_metadata=participant_metadata,
        haptic_capability=haptic_capability,
        failures=failures,
        warnings=warnings,
    )
    _validate_phone_event_diary(
        completion=completion,
        event_rows=event_rows or [],
        failures=failures,
        warnings=warnings,
        expect_event_diary=expect_event_diary,
    )
    _validate_phone_command_diary(
        status=status,
        completion=completion,
        command_diary_rows=command_diary_rows or [],
        failures=failures,
        warnings=warnings,
        expect_command_acks=expect_command_acks,
    )
    _validate_phone_marker_mirror(
        status=status,
        completion=completion,
        marker_mirror_rows=marker_mirror_rows or [],
        failures=failures,
        warnings=warnings,
        expect_native_transport=expect_native_transport,
    )
    _validate_phone_trigger_code_mirror(
        completion=completion,
        marker_mirror_rows=marker_mirror_rows or [],
        trigger_code_rows=trigger_code_rows or [],
        failures=failures,
        warnings=warnings,
        expect_trigger_code_mirror=expect_trigger_code_mirror,
    )
    _validate_phone_audiotrack_timing_evidence(
        completion=completion,
        package_manifest=package_manifest,
        failures=failures,
        warnings=warnings,
        expect_audiotrack_timing_evidence=expect_audiotrack_timing_evidence,
    )
    _validate_lightweight_materializations(
        completion=completion,
        package_manifest=package_manifest,
        materialization_manifests=materialization_manifests or [],
        materialized_wav_hashes=materialized_wav_hashes or {},
        failures=failures,
        warnings=warnings,
        expect_lightweight_materializations=expect_lightweight_materializations,
    )
    _validate_phone_response_topup_artifacts(
        completion=completion,
        response_ledger_rows=response_ledger_rows or [],
        topup_plan=topup_plan,
        topup_materialization=topup_materialization,
        topup_wav_hashes=topup_wav_hashes or {},
        failures=failures,
        warnings=warnings,
        expect_phone_topup_evidence=expect_phone_topup_evidence or expect_lightweight_materializations,
    )
    _validate_phone_owned_data_export(
        export=phone_owned_data_export,
        data_min_header=phone_data_min_header or [],
        data_min_rows=phone_data_min_rows or [],
        data_min_master_header=phone_data_min_master_header or [],
        data_min_master_rows=phone_data_min_master_rows or [],
        data_max_has_completion=phone_data_max_has_completion,
        completion=completion,
        response_ledger_rows=response_ledger_rows or [],
        failures=failures,
        warnings=warnings,
        expect_phone_owned_data_export=expect_phone_owned_data_export,
    )

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
    _validate_android_controller_lsl_stream_descriptions(
        status=status,
        streams=streams,
        failures=failures,
        warnings=warnings,
        expect_native_transport=expect_native_transport,
    )

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
    _validate_pc_admin_lsl_stream_descriptions(
        status=status,
        streams=streams,
        failures=failures,
        warnings=warnings,
        expect_native_transport=expect_native_transport,
    )

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
        _validate_pc_monitor_lsl_stream_descriptions(
            status=status,
            streams=streams,
            failures=failures,
            warnings=warnings,
            expect_native_transport=expect_native_transport,
        )
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
        effective_counts = {key: 0 for key in ("rich_markers", "numeric_triggers", "command_acks", "command_signals")}
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
    expect_run_catalog_index: bool = False,
    expect_event_diary: bool = False,
    expect_trigger_code_mirror: bool = False,
    expect_lightweight_materializations: bool = False,
    expect_phone_topup_evidence: bool = False,
    expect_audiotrack_timing_evidence: bool = False,
    expect_phone_owned_data_export: bool = False,
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
        catalog_index=loaded.get("catalog_index"),
        catalog_runs_rows=loaded.get("catalog_runs_rows") or [],
        catalog_latest_entries=loaded.get("catalog_latest_entries") or [],
        package_manifest=loaded.get("package_manifest"),
        reconstruction_artifact=loaded.get("reconstruction_artifact"),
        participant_metadata=loaded.get("participant_metadata"),
        haptic_capability=loaded.get("haptic_capability"),
        event_rows=loaded.get("event_rows") or [],
        command_diary_rows=loaded.get("command_diary_rows") or [],
        marker_mirror_rows=loaded.get("marker_mirror_rows") or [],
        trigger_code_rows=loaded.get("trigger_code_rows") or [],
        materialization_manifests=loaded.get("materialization_manifests") or [],
        materialized_wav_hashes=loaded.get("materialized_wav_hashes") or {},
        response_ledger_rows=loaded.get("response_ledger_rows") or [],
        topup_plan=loaded.get("topup_plan"),
        topup_materialization=loaded.get("topup_materialization"),
        topup_wav_hashes=loaded.get("topup_wav_hashes") or {},
        phone_owned_data_export=loaded.get("phone_owned_data_export"),
        phone_data_min_header=loaded.get("phone_data_min_header") or [],
        phone_data_min_rows=loaded.get("phone_data_min_rows") or [],
        phone_data_min_master_header=loaded.get("phone_data_min_master_header") or [],
        phone_data_min_master_rows=loaded.get("phone_data_min_master_rows") or [],
        phone_data_max_has_completion=bool(loaded.get("phone_data_max_has_completion")),
        expect_native_transport=expect_native_transport,
        expect_command_acks=expect_command_acks,
        expect_run_catalog=expect_run_catalog,
        expect_run_catalog_index=expect_run_catalog_index,
        expect_event_diary=expect_event_diary,
        expect_trigger_code_mirror=expect_trigger_code_mirror,
        expect_lightweight_materializations=expect_lightweight_materializations,
        expect_phone_topup_evidence=expect_phone_topup_evidence,
        expect_audiotrack_timing_evidence=expect_audiotrack_timing_evidence,
        expect_phone_owned_data_export=expect_phone_owned_data_export,
    )


def _load_status_inputs(path: Path) -> dict[str, Any]:
    if path.is_dir():
        status_path = path / "lsl_runtime_status.json"
        if status_path.is_file():
            completion_path = path / "completion.json"
            if not completion_path.is_file():
                completion_path = path / "latest_events.json"
            catalog_path = path / ANDROID_PHONE_RUN_CATALOG_ENTRY
            sidecars = _load_phone_run_sidecars_from_dir(path)
            return {
                "kind": "runner",
                "status": _read_json(status_path),
                "completion": _read_json(completion_path) if completion_path.is_file() else None,
                "catalog_entry": _read_json(catalog_path) if catalog_path.is_file() else None,
                **sidecars,
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
        sidecars = _load_phone_run_sidecars_from_dir(path.parent)
        completion_path = path.with_name("completion.json")
        if not completion_path.is_file():
            completion_path = path.with_name("latest_events.json")
        return {
            "kind": "runner",
            "status": data,
            "completion": _read_json(completion_path) if completion_path.is_file() else None,
            "catalog_entry": _read_json(catalog_path) if catalog_path.is_file() else None,
            **sidecars,
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
        return {
            "kind": "runner",
            "status": embedded,
            "completion": data,
            "catalog_entry": catalog_entry,
            **_load_phone_run_sidecars_from_dir(path.parent),
        }
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
            catalog_index_members = [
                name
                for name in archive.namelist()
                if name.replace("\\", "/").endswith("phone_run_catalog/index.json")
            ]
            catalog_runs_members = [
                name
                for name in archive.namelist()
                if "phone_run_catalog/" in name.replace("\\", "/") and name.endswith("/runs.jsonl")
            ]
            catalog_latest_members = [
                name
                for name in archive.namelist()
                if "phone_run_catalog/" in name.replace("\\", "/") and name.endswith("/latest_run.json")
            ]
            package_manifest_members = [name for name in archive.namelist() if name.endswith("run_package_manifest.json")]
            reconstruction_members = [name for name in archive.namelist() if name.endswith(ANDROID_PHONE_RUN_RECONSTRUCTION_ARTIFACT)]
            participant_metadata_members = [name for name in archive.namelist() if name.endswith("participant_metadata.json")]
            haptic_capability_members = [name for name in archive.namelist() if name.endswith("haptic_capability.json")]
            event_members = [name for name in archive.namelist() if name.endswith("events.csv")]
            command_diary_members = [name for name in archive.namelist() if name.endswith("command_diary.jsonl")]
            marker_mirror_members = [name for name in archive.namelist() if name.endswith("lsl_marker_mirror.csv")]
            trigger_code_members = [name for name in archive.namelist() if name.endswith("trigger_codes.csv")]
            response_ledger_members = [name for name in archive.namelist() if name.endswith("phone_response_ledger.csv")]
            data_export_members = [name for name in archive.namelist() if name.endswith("phone_owned_data_export.json")]
            data_min_members = [
                name
                for name in archive.namelist()
                if "phone_owned_exports/1.Data_min/" in name.replace("\\", "/")
                and name.endswith(".csv")
                and not name.endswith("master_successful_participants.csv")
            ]
            data_min_master_members = [
                name
                for name in archive.namelist()
                if name.replace("\\", "/").endswith("phone_owned_exports/1.Data_min/master_successful_participants.csv")
            ]
            data_max_completion_members = [
                name
                for name in archive.namelist()
                if "phone_owned_exports/2.Data_max/" in name.replace("\\", "/")
                and (name.endswith("completion.json") or name.endswith("latest_events.json"))
            ]
            topup_plan_members = [name for name in archive.namelist() if name.endswith("phone_topup_plan.json")]
            topup_materialization_members = [
                name
                for name in archive.namelist()
                if name.endswith("phone_topup_materialization.json")
                and "materialized_blocks/" not in name.replace("\\", "/")
            ]
            topup_wav_members = [name for name in archive.namelist() if name.endswith("phone_topup_block.wav")]
            materialization_members = [
                name
                for name in archive.namelist()
                if "materialized_blocks/" in name.replace("\\", "/") and name.endswith(".json")
            ]
            materialized_wav_members = [
                name
                for name in archive.namelist()
                if "materialized_blocks/" in name.replace("\\", "/") and name.endswith(".wav")
            ]
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
            catalog_index = None
            if catalog_index_members:
                catalog_index_name = sorted(catalog_index_members)[0]
                archive.extract(catalog_index_name, temp_root)
                catalog_index = _read_json(temp_root / catalog_index_name)
            catalog_runs_rows: list[dict[str, Any]] = []
            for member in sorted(catalog_runs_members):
                archive.extract(member, temp_root)
                participant_dir = Path(member.replace("\\", "/")).parent.name
                for row in _read_jsonl(temp_root / member):
                    row.setdefault("_catalog_participant_dir", participant_dir)
                    catalog_runs_rows.append(row)
            catalog_latest_entries: list[dict[str, Any]] = []
            for member in sorted(catalog_latest_members):
                archive.extract(member, temp_root)
                participant_dir = Path(member.replace("\\", "/")).parent.name
                latest = _read_json(temp_root / member)
                latest.setdefault("_catalog_participant_dir", participant_dir)
                catalog_latest_entries.append(latest)
            package_manifest = None
            if package_manifest_members:
                package_manifest_name = sorted(package_manifest_members)[0]
                archive.extract(package_manifest_name, temp_root)
                package_manifest = _read_json(temp_root / package_manifest_name)
            reconstruction_artifact = None
            if reconstruction_members:
                reconstruction_name = sorted(reconstruction_members)[0]
                archive.extract(reconstruction_name, temp_root)
                reconstruction_artifact = _read_json(temp_root / reconstruction_name)
            participant_metadata = None
            if participant_metadata_members:
                participant_metadata_name = sorted(participant_metadata_members)[0]
                archive.extract(participant_metadata_name, temp_root)
                participant_metadata = _read_json(temp_root / participant_metadata_name)
            haptic_capability = None
            if haptic_capability_members:
                haptic_capability_name = sorted(haptic_capability_members)[0]
                archive.extract(haptic_capability_name, temp_root)
                haptic_capability = _read_json(temp_root / haptic_capability_name)
            event_rows: list[dict[str, Any]] = []
            if event_members:
                event_name = sorted(event_members)[0]
                archive.extract(event_name, temp_root)
                event_rows = _read_csv(temp_root / event_name)
            materialization_manifests: list[dict[str, Any]] = []
            for member in sorted(materialization_members):
                archive.extract(member, temp_root)
                materialization_manifests.append(_read_json(temp_root / member))
            materialized_wav_hashes = {
                Path(member).name: _sha256_bytes(archive.read(member))
                for member in materialized_wav_members
            }
            command_diary_rows: list[dict[str, Any]] = []
            if command_diary_members:
                command_diary_name = sorted(command_diary_members)[0]
                archive.extract(command_diary_name, temp_root)
                command_diary_rows = _read_jsonl(temp_root / command_diary_name)
            marker_mirror_rows: list[dict[str, Any]] = []
            if marker_mirror_members:
                marker_mirror_name = sorted(marker_mirror_members)[0]
                archive.extract(marker_mirror_name, temp_root)
                marker_mirror_rows = _read_csv(temp_root / marker_mirror_name)
            trigger_code_rows: list[dict[str, Any]] = []
            if trigger_code_members:
                trigger_code_name = sorted(trigger_code_members)[0]
                archive.extract(trigger_code_name, temp_root)
                trigger_code_rows = _read_csv(temp_root / trigger_code_name)
            response_ledger_rows: list[dict[str, Any]] = []
            if response_ledger_members:
                response_ledger_name = sorted(response_ledger_members)[0]
                archive.extract(response_ledger_name, temp_root)
                response_ledger_rows = _read_csv(temp_root / response_ledger_name)
            phone_owned_data_export = None
            if data_export_members:
                data_export_name = sorted(data_export_members)[0]
                archive.extract(data_export_name, temp_root)
                phone_owned_data_export = _read_json(temp_root / data_export_name)
            phone_data_min_header: list[str] = []
            phone_data_min_rows: list[dict[str, Any]] = []
            for member in sorted(data_min_members):
                archive.extract(member, temp_root)
                header, rows = _read_csv_with_header(temp_root / member)
                if not phone_data_min_header:
                    phone_data_min_header = header
                phone_data_min_rows.extend(rows)
            phone_data_min_master_header: list[str] = []
            phone_data_min_master_rows: list[dict[str, Any]] = []
            if data_min_master_members:
                data_min_master_name = sorted(data_min_master_members)[0]
                archive.extract(data_min_master_name, temp_root)
                phone_data_min_master_header, phone_data_min_master_rows = _read_csv_with_header(temp_root / data_min_master_name)
            topup_plan = None
            if topup_plan_members:
                topup_plan_name = sorted(topup_plan_members)[0]
                archive.extract(topup_plan_name, temp_root)
                topup_plan = _read_json(temp_root / topup_plan_name)
            topup_materialization = None
            if topup_materialization_members:
                topup_materialization_name = sorted(topup_materialization_members)[0]
                archive.extract(topup_materialization_name, temp_root)
                topup_materialization = _read_json(temp_root / topup_materialization_name)
            topup_wav_hashes = {
                Path(member).name: _sha256_bytes(archive.read(member))
                for member in topup_wav_members
            }
            return {
                "kind": "runner",
                "status": _read_json(temp_root / status_name),
                "completion": completion,
                "catalog_entry": catalog_entry,
                "catalog_index": catalog_index,
                "catalog_runs_rows": catalog_runs_rows,
                "catalog_latest_entries": catalog_latest_entries,
                "package_manifest": package_manifest,
                "reconstruction_artifact": reconstruction_artifact,
                "participant_metadata": participant_metadata,
                "haptic_capability": haptic_capability,
                "event_rows": event_rows,
                "command_diary_rows": command_diary_rows,
                "marker_mirror_rows": marker_mirror_rows,
                "trigger_code_rows": trigger_code_rows,
                "materialization_manifests": materialization_manifests,
                "materialized_wav_hashes": materialized_wav_hashes,
                "response_ledger_rows": response_ledger_rows,
                "phone_owned_data_export": phone_owned_data_export,
                "phone_data_min_header": phone_data_min_header,
                "phone_data_min_rows": phone_data_min_rows,
                "phone_data_min_master_header": phone_data_min_master_header,
                "phone_data_min_master_rows": phone_data_min_master_rows,
                "phone_data_max_has_completion": bool(data_max_completion_members),
                "topup_plan": topup_plan,
                "topup_materialization": topup_materialization,
                "topup_wav_hashes": topup_wav_hashes,
            }


def _load_phone_run_sidecars_from_dir(path: Path) -> dict[str, Any]:
    package_manifest_path = path / "run_package_manifest.json"
    reconstruction_artifact_path = path / ANDROID_PHONE_RUN_RECONSTRUCTION_ARTIFACT
    participant_metadata_path = path / "participant_metadata.json"
    haptic_capability_path = path / "haptic_capability.json"
    event_diary_path = path / "events.csv"
    command_diary_path = path / "command_diary.jsonl"
    marker_mirror_path = path / "lsl_marker_mirror.csv"
    trigger_code_path = path / "trigger_codes.csv"
    response_ledger_path = path / "phone_response_ledger.csv"
    data_export_path = path / "phone_owned_data_export.json"
    topup_plan_path = path / "phone_topup_plan.json"
    topup_materialization_path = path / "phone_topup_materialization.json"
    topup_wav_path = path / "phone_topup_block.wav"
    materialized_dir = path / "materialized_blocks"
    materialization_manifests: list[dict[str, Any]] = []
    materialized_wav_hashes: dict[str, str] = {}
    if materialized_dir.is_dir():
        for manifest_path in sorted(materialized_dir.glob("*.json")):
            materialization_manifests.append(_read_json(manifest_path))
        for wav_path in sorted(materialized_dir.glob("*.wav")):
            materialized_wav_hashes[wav_path.name] = _sha256_file(wav_path)
    export_root = _find_phone_owned_export_root(path)
    phone_data_min_header: list[str] = []
    phone_data_min_rows: list[dict[str, Any]] = []
    phone_data_min_master_header: list[str] = []
    phone_data_min_master_rows: list[dict[str, Any]] = []
    phone_data_max_has_completion = False
    if export_root:
        phone_data_min_header, phone_data_min_rows = _load_phone_data_min_rows(export_root)
        phone_data_min_master_header, phone_data_min_master_rows = _load_phone_data_min_master_rows(export_root)
        phone_data_max_has_completion = _phone_data_max_has_completion(export_root)

    sidecars = {
        "package_manifest": _read_json(package_manifest_path) if package_manifest_path.is_file() else None,
        "reconstruction_artifact": _read_json(reconstruction_artifact_path) if reconstruction_artifact_path.is_file() else None,
        "participant_metadata": _read_json(participant_metadata_path) if participant_metadata_path.is_file() else None,
        "haptic_capability": _read_json(haptic_capability_path) if haptic_capability_path.is_file() else None,
        "event_rows": _read_csv(event_diary_path) if event_diary_path.is_file() else [],
        "command_diary_rows": _read_jsonl(command_diary_path) if command_diary_path.is_file() else [],
        "marker_mirror_rows": _read_csv(marker_mirror_path) if marker_mirror_path.is_file() else [],
        "trigger_code_rows": _read_csv(trigger_code_path) if trigger_code_path.is_file() else [],
        "materialization_manifests": materialization_manifests,
        "materialized_wav_hashes": materialized_wav_hashes,
        "response_ledger_rows": _read_csv(response_ledger_path) if response_ledger_path.is_file() else [],
        "phone_owned_data_export": _read_json(data_export_path) if data_export_path.is_file() else None,
        "phone_data_min_header": phone_data_min_header,
        "phone_data_min_rows": phone_data_min_rows,
        "phone_data_min_master_header": phone_data_min_master_header,
        "phone_data_min_master_rows": phone_data_min_master_rows,
        "phone_data_max_has_completion": phone_data_max_has_completion,
        "topup_plan": _read_json(topup_plan_path) if topup_plan_path.is_file() else None,
        "topup_materialization": _read_json(topup_materialization_path) if topup_materialization_path.is_file() else None,
        "topup_wav_hashes": {topup_wav_path.name: _sha256_file(topup_wav_path)} if topup_wav_path.is_file() else {},
    }
    catalog_root = _find_phone_run_catalog_root(path)
    if catalog_root:
        sidecars.update(_load_phone_run_catalog_root(catalog_root))
    return sidecars


def _find_phone_run_catalog_root(path: Path) -> Path | None:
    candidates: list[Path] = []
    for candidate in (
        path / "phone_run_catalog",
        path.parent / "phone_run_catalog",
        path.parent.parent / "phone_run_catalog",
        path.parent.parent.parent / "phone_run_catalog",
    ):
        if candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        if (candidate / "index.json").is_file() or any(candidate.glob("*/runs.jsonl")):
            return candidate
    return None


def _find_phone_owned_export_root(path: Path) -> Path | None:
    candidates: list[Path] = []
    for candidate in (
        path / "phone_owned_exports",
        path.parent / "phone_owned_exports",
        path.parent.parent / "phone_owned_exports",
        path.parent.parent.parent / "phone_owned_exports",
    ):
        if candidate not in candidates:
            candidates.append(candidate)
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        if (candidate / "1.Data_min").is_dir() or (candidate / "2.Data_max").is_dir():
            return candidate
    return None


def _load_phone_data_min_rows(export_root: Path) -> tuple[list[str], list[dict[str, Any]]]:
    data_min = export_root / "1.Data_min"
    rows: list[dict[str, Any]] = []
    header: list[str] = []
    for csv_path in sorted(data_min.glob("*.csv")):
        if csv_path.name == "master_successful_participants.csv":
            continue
        observed_header, observed_rows = _read_csv_with_header(csv_path)
        if not header:
            header = observed_header
        rows.extend(observed_rows)
    return header, rows


def _load_phone_data_min_master_rows(export_root: Path) -> tuple[list[str], list[dict[str, Any]]]:
    master = export_root / "1.Data_min" / "master_successful_participants.csv"
    if not master.is_file():
        return [], []
    return _read_csv_with_header(master)


def _phone_data_max_has_completion(export_root: Path) -> bool:
    data_max = export_root / "2.Data_max"
    return any(data_max.glob("*/runs/*/completion.json")) or any(data_max.glob("*/runs/*/latest_events.json"))


def _load_phone_run_catalog_root(root: Path) -> dict[str, Any]:
    catalog_index_path = root / "index.json"
    catalog_runs_rows: list[dict[str, Any]] = []
    catalog_latest_entries: list[dict[str, Any]] = []
    for runs_path in sorted(root.glob("*/runs.jsonl")):
        participant_dir = runs_path.parent.name
        for row in _read_jsonl(runs_path):
            row.setdefault("_catalog_participant_dir", participant_dir)
            catalog_runs_rows.append(row)
    for latest_path in sorted(root.glob("*/latest_run.json")):
        latest = _read_json(latest_path)
        latest.setdefault("_catalog_participant_dir", latest_path.parent.name)
        catalog_latest_entries.append(latest)
    return {
        "catalog_index": _read_json(catalog_index_path) if catalog_index_path.is_file() else None,
        "catalog_runs_rows": catalog_runs_rows,
        "catalog_latest_entries": catalog_latest_entries,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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


def _read_csv(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_csv_with_header(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [dict(row) for row in reader]


def _clean_int(value: Any) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any, *, fallback: float = float("nan")) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _metadata_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _duplicate_ints(values: list[int]) -> list[int]:
    seen: set[int] = set()
    duplicates: list[int] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _validate_android_lsl_stream_descriptions(
    *,
    status: dict[str, Any],
    streams: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    expect_native_transport: bool,
) -> None:
    descriptions = status.get("stream_descriptions") if isinstance(status.get("stream_descriptions"), dict) else None
    if descriptions is None:
        message = "Android LSL stream descriptions are missing"
        if expect_native_transport:
            failures.append(message)
        elif status.get("native_transport_available") is True:
            warnings.append(f"{message}; rerun with --expect-native-transport for strict checks")
        return
    if descriptions.get("schema") != ANDROID_LSL_STREAM_DESCRIPTIONS_SCHEMA:
        failures.append("Android LSL stream descriptions schema mismatch")
    privacy = descriptions.get("privacy") if isinstance(descriptions.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("Android LSL stream descriptions must keep demographics out of stream names")
    expected = {
        "rich_markers": {
            "name": streams.get("rich_markers") or EXPECTED_STREAMS["rich_markers"],
            "type": "Markers",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(LSL_MARKER_CHANNELS),
            "channel_labels": list(LSL_MARKER_CHANNELS),
            "source_id_prefix": "pps-android-markers-v2-",
            "marker_version": MARKER_VERSION,
        },
        "numeric_triggers": {
            "name": streams.get("numeric_triggers") or EXPECTED_STREAMS["numeric_triggers"],
            "type": "TriggerCodes",
            "role": "outlet",
            "channel_format": "int32",
            "channel_count": 1,
            "channel_labels": ["event_code"],
            "source_id_prefix": "pps-android-trigger-codes-",
        },
        "command_signals": {
            "name": streams.get("command_signals") or EXPECTED_STREAMS["command_signals"],
            "type": "CommandSignals",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_COMMAND_CHANNELS),
            "channel_labels": list(LSL_COMMAND_CHANNELS),
            "source_id_pattern": "pps-*-command-signals-v1-*",
            "token_required": True,
        },
        "command_acks": {
            "name": streams.get("command_acks") or EXPECTED_STREAMS["command_acks"],
            "type": "CommandAcks",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(LSL_ACK_CHANNELS),
            "channel_labels": list(LSL_ACK_CHANNELS),
            "source_id_prefix": "pps-android-command-acks-v1-",
        },
    }
    for key, spec in expected.items():
        row = descriptions.get(key) if isinstance(descriptions.get(key), dict) else None
        if row is None:
            failures.append(f"Android LSL stream description {key} is missing")
            continue
        for field in ("name", "type", "role", "channel_format"):
            if str(row.get(field) or "") != str(spec[field]):
                failures.append(
                    f"Android LSL stream description {key}.{field} expected {spec[field]!r}, got {row.get(field)!r}"
                )
        if _clean_int(row.get("channel_count")) != int(spec["channel_count"]):
            failures.append(
                f"Android LSL stream description {key}.channel_count expected {spec['channel_count']}, got {row.get('channel_count')!r}"
            )
        labels = [str(item) for item in row.get("channel_labels") or []] if isinstance(row.get("channel_labels"), list) else []
        if labels != list(spec["channel_labels"]):
            failures.append(f"Android LSL stream description {key}.channel_labels differ from the PC-compatible channel order")
        nominal = _safe_float(row.get("nominal_srate_hz"), fallback=-1.0)
        if nominal != 0.0:
            failures.append(f"Android LSL stream description {key}.nominal_srate_hz must be 0.0 for irregular marker/command streams")
        if "source_id_prefix" in spec:
            source_id = str(row.get("source_id") or "")
            if not source_id.startswith(str(spec["source_id_prefix"])):
                failures.append(f"Android LSL stream description {key}.source_id must start with {spec['source_id_prefix']!r}")
        if "source_id_pattern" in spec and str(row.get("source_id_pattern") or "") != str(spec["source_id_pattern"]):
            failures.append(
                f"Android LSL stream description {key}.source_id_pattern expected {spec['source_id_pattern']!r}"
            )
        if "marker_version" in spec and str(row.get("marker_version") or "") != str(spec["marker_version"]):
            failures.append(f"Android LSL stream description {key}.marker_version expected {spec['marker_version']!r}")
        if "token_required" in spec and row.get("token_required") is not spec["token_required"]:
            failures.append(f"Android LSL stream description {key}.token_required must be true")


def _validate_android_controller_lsl_stream_descriptions(
    *,
    status: dict[str, Any],
    streams: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    expect_native_transport: bool,
) -> None:
    descriptions = status.get("stream_descriptions") if isinstance(status.get("stream_descriptions"), dict) else None
    if descriptions is None:
        message = "Android controller LSL stream descriptions are missing"
        if expect_native_transport:
            failures.append(message)
        elif status.get("native_transport_available") is True:
            warnings.append(f"{message}; rerun with --expect-native-transport for strict checks")
        return
    if descriptions.get("schema") != ANDROID_LSL_STREAM_DESCRIPTIONS_SCHEMA:
        failures.append("Android controller LSL stream descriptions schema mismatch")
    if descriptions.get("role") != "controller":
        failures.append("Android controller LSL stream descriptions must declare role='controller'")
    privacy = descriptions.get("privacy") if isinstance(descriptions.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("Android controller LSL stream descriptions must keep demographics out of stream names")
    expected = {
        "command_signals": {
            "name": streams.get("command_signals") or EXPECTED_CONTROLLER_STREAMS["command_signals"],
            "type": "CommandSignals",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(LSL_COMMAND_CHANNELS),
            "channel_labels": list(LSL_COMMAND_CHANNELS),
            "source_id_prefix": "pps-android-controller-signals-v1-",
            "token_required": True,
        },
        "command_acks": {
            "name": streams.get("command_acks") or EXPECTED_CONTROLLER_STREAMS["command_acks"],
            "type": "CommandAcks",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_ACK_CHANNELS),
            "channel_labels": list(LSL_ACK_CHANNELS),
            "source_id_pattern": "pps-*-command-acks-v1-*",
        },
    }
    for key, spec in expected.items():
        row = descriptions.get(key) if isinstance(descriptions.get(key), dict) else None
        if row is None:
            failures.append(f"Android controller LSL stream description {key} is missing")
            continue
        for field in ("name", "type", "role", "channel_format"):
            if str(row.get(field) or "") != str(spec[field]):
                failures.append(
                    f"Android controller LSL stream description {key}.{field} expected {spec[field]!r}, got {row.get(field)!r}"
                )
        if _clean_int(row.get("channel_count")) != int(spec["channel_count"]):
            failures.append(
                f"Android controller LSL stream description {key}.channel_count expected {spec['channel_count']}, got {row.get('channel_count')!r}"
            )
        labels = [str(item) for item in row.get("channel_labels") or []] if isinstance(row.get("channel_labels"), list) else []
        if labels != list(spec["channel_labels"]):
            failures.append(f"Android controller LSL stream description {key}.channel_labels differ from the PC-compatible channel order")
        nominal = _safe_float(row.get("nominal_srate_hz"), fallback=-1.0)
        if nominal != 0.0:
            failures.append(f"Android controller LSL stream description {key}.nominal_srate_hz must be 0.0 for irregular command streams")
        if "source_id_prefix" in spec:
            source_id = str(row.get("source_id") or "")
            if not source_id.startswith(str(spec["source_id_prefix"])):
                failures.append(f"Android controller LSL stream description {key}.source_id must start with {spec['source_id_prefix']!r}")
        if "source_id_pattern" in spec and str(row.get("source_id_pattern") or "") != str(spec["source_id_pattern"]):
            failures.append(
                f"Android controller LSL stream description {key}.source_id_pattern expected {spec['source_id_pattern']!r}"
            )
        if "token_required" in spec and row.get("token_required") is not spec["token_required"]:
            failures.append(f"Android controller LSL stream description {key}.token_required must be true")


def _validate_pc_admin_lsl_stream_descriptions(
    *,
    status: dict[str, Any],
    streams: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    expect_native_transport: bool,
) -> None:
    descriptions = status.get("stream_descriptions") if isinstance(status.get("stream_descriptions"), dict) else None
    if descriptions is None:
        message = "PC Android LSL admin stream descriptions are missing"
        if expect_native_transport:
            failures.append(message)
        else:
            warnings.append(f"{message}; rerun with --expect-native-transport for strict checks")
        return
    if descriptions.get("schema") != ANDROID_LSL_STREAM_DESCRIPTIONS_SCHEMA:
        failures.append("PC Android LSL admin stream descriptions schema mismatch")
    if descriptions.get("role") != "pc_android_lsl_admin":
        failures.append("PC Android LSL admin stream descriptions must declare role='pc_android_lsl_admin'")
    if descriptions.get("native_transport") != "liblsl":
        failures.append("PC Android LSL admin stream descriptions must declare native_transport='liblsl'")
    privacy = descriptions.get("privacy") if isinstance(descriptions.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("PC Android LSL admin stream descriptions must keep demographics out of stream names")
    expected = {
        "command_signals": {
            "name": streams.get("command_signals") or EXPECTED_PC_ADMIN_STREAMS["command_signals"],
            "type": "CommandSignals",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(LSL_COMMAND_CHANNELS),
            "channel_labels": list(LSL_COMMAND_CHANNELS),
            "source_id_prefix": "pps-command-signals-v1-",
            "source_id_pattern": "pps-command-signals-v1-*-*",
            "token_required": True,
        },
        "command_acks": {
            "name": streams.get("command_acks") or EXPECTED_PC_ADMIN_STREAMS["command_acks"],
            "type": "CommandAcks",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_ACK_CHANNELS),
            "channel_labels": list(LSL_ACK_CHANNELS),
            "source_id_pattern": "pps-command-acks-v1-*-*",
        },
    }
    for key, spec in expected.items():
        row = descriptions.get(key) if isinstance(descriptions.get(key), dict) else None
        if row is None:
            failures.append(f"PC Android LSL admin stream description {key} is missing")
            continue
        for field in ("name", "type", "role", "channel_format"):
            if str(row.get(field) or "") != str(spec[field]):
                failures.append(
                    f"PC Android LSL admin stream description {key}.{field} expected {spec[field]!r}, got {row.get(field)!r}"
                )
        if _clean_int(row.get("channel_count")) != int(spec["channel_count"]):
            failures.append(
                f"PC Android LSL admin stream description {key}.channel_count expected {spec['channel_count']}, got {row.get('channel_count')!r}"
            )
        labels = [str(item) for item in row.get("channel_labels") or []] if isinstance(row.get("channel_labels"), list) else []
        if labels != list(spec["channel_labels"]):
            failures.append(f"PC Android LSL admin stream description {key}.channel_labels differ from the PC-compatible channel order")
        nominal = _safe_float(row.get("nominal_srate_hz"), fallback=-1.0)
        if nominal != 0.0:
            failures.append(f"PC Android LSL admin stream description {key}.nominal_srate_hz must be 0.0 for irregular command streams")
        source_id = str(row.get("source_id") or "")
        source_pattern = str(row.get("source_id_pattern") or "")
        if "source_id_prefix" in spec and source_id and not source_id.startswith(str(spec["source_id_prefix"])):
            failures.append(f"PC Android LSL admin stream description {key}.source_id must start with {spec['source_id_prefix']!r}")
        if "source_id_pattern" in spec and not source_id and source_pattern != str(spec["source_id_pattern"]):
            failures.append(
                f"PC Android LSL admin stream description {key}.source_id_pattern expected {spec['source_id_pattern']!r}"
            )
        if "token_required" in spec and row.get("token_required") is not spec["token_required"]:
            failures.append(f"PC Android LSL admin stream description {key}.token_required must be true")


def _validate_pc_monitor_lsl_stream_descriptions(
    *,
    status: dict[str, Any],
    streams: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    expect_native_transport: bool,
) -> None:
    descriptions = status.get("stream_descriptions") if isinstance(status.get("stream_descriptions"), dict) else None
    if descriptions is None:
        message = "PC Android LSL monitor stream descriptions are missing"
        if expect_native_transport:
            failures.append(message)
        else:
            warnings.append(f"{message}; rerun with --expect-native-transport for strict checks")
        return
    if descriptions.get("schema") != ANDROID_LSL_STREAM_DESCRIPTIONS_SCHEMA:
        failures.append("PC Android LSL monitor stream descriptions schema mismatch")
    if descriptions.get("role") != "pc_android_lsl_monitor":
        failures.append("PC Android LSL monitor stream descriptions must declare role='pc_android_lsl_monitor'")
    if descriptions.get("native_transport") != "liblsl":
        failures.append("PC Android LSL monitor stream descriptions must declare native_transport='liblsl'")
    privacy = descriptions.get("privacy") if isinstance(descriptions.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("PC Android LSL monitor stream descriptions must keep demographics out of stream names")
    expected = {
        "rich_markers": {
            "name": streams.get("rich_markers") or EXPECTED_PC_MONITOR_STREAMS["rich_markers"],
            "type": "Markers",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_MARKER_CHANNELS),
            "channel_labels": list(LSL_MARKER_CHANNELS),
            "source_id_pattern": "pps-android-markers-v2-*",
            "marker_version": MARKER_VERSION,
        },
        "numeric_triggers": {
            "name": streams.get("numeric_triggers") or EXPECTED_PC_MONITOR_STREAMS["numeric_triggers"],
            "type": "TriggerCodes",
            "role": "inlet",
            "channel_format": "int32",
            "channel_count": 1,
            "channel_labels": ["event_code"],
            "source_id_pattern": "pps-android-trigger-codes-*",
        },
        "command_acks": {
            "name": streams.get("command_acks") or EXPECTED_PC_MONITOR_STREAMS["command_acks"],
            "type": "CommandAcks",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_ACK_CHANNELS),
            "channel_labels": list(LSL_ACK_CHANNELS),
            "source_id_pattern": "pps-android-command-acks-v1-*",
        },
        "command_signals": {
            "name": streams.get("command_signals") or EXPECTED_PC_MONITOR_STREAMS["command_signals"],
            "type": "CommandSignals",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_COMMAND_CHANNELS),
            "channel_labels": list(LSL_COMMAND_CHANNELS),
            "source_id_patterns": [
                "pps-command-signals-v1-*-*",
                "pps-android-controller-signals-v1-*-*",
            ],
            "token_required": True,
        },
    }
    for key, spec in expected.items():
        row = descriptions.get(key) if isinstance(descriptions.get(key), dict) else None
        if row is None:
            failures.append(f"PC Android LSL monitor stream description {key} is missing")
            continue
        for field in ("name", "type", "role", "channel_format"):
            if str(row.get(field) or "") != str(spec[field]):
                failures.append(
                    f"PC Android LSL monitor stream description {key}.{field} expected {spec[field]!r}, got {row.get(field)!r}"
                )
        if _clean_int(row.get("channel_count")) != int(spec["channel_count"]):
            failures.append(
                f"PC Android LSL monitor stream description {key}.channel_count expected {spec['channel_count']}, got {row.get('channel_count')!r}"
            )
        labels = [str(item) for item in row.get("channel_labels") or []] if isinstance(row.get("channel_labels"), list) else []
        if labels != list(spec["channel_labels"]):
            failures.append(f"PC Android LSL monitor stream description {key}.channel_labels differ from the PC-compatible channel order")
        nominal = _safe_float(row.get("nominal_srate_hz"), fallback=-1.0)
        if nominal != 0.0:
            failures.append(f"PC Android LSL monitor stream description {key}.nominal_srate_hz must be 0.0 for irregular marker/command streams")
        if "source_id_pattern" in spec and str(row.get("source_id_pattern") or "") != str(spec["source_id_pattern"]):
            failures.append(
                f"PC Android LSL monitor stream description {key}.source_id_pattern expected {spec['source_id_pattern']!r}"
            )
        if "source_id_patterns" in spec:
            observed_patterns = [str(item) for item in row.get("source_id_patterns") or []] if isinstance(row.get("source_id_patterns"), list) else []
            if observed_patterns != list(spec["source_id_patterns"]):
                failures.append(
                    f"PC Android LSL monitor stream description {key}.source_id_patterns expected {spec['source_id_patterns']!r}"
                )
        if "marker_version" in spec and str(row.get("marker_version") or "") != str(spec["marker_version"]):
            failures.append(f"PC Android LSL monitor stream description {key}.marker_version expected {spec['marker_version']!r}")
        if "token_required" in spec and row.get("token_required") is not spec["token_required"]:
            failures.append(f"PC Android LSL monitor stream description {key}.token_required must be true")


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


def _validate_asset_strategy_consistency(
    *,
    status: dict[str, Any],
    completion: dict[str, Any] | None,
    catalog_entry: dict[str, Any] | None,
    package_manifest: dict[str, Any] | None,
    reconstruction_artifact: dict[str, Any] | None,
    failures: list[str],
    warnings: list[str],
    expect_lightweight_materializations: bool,
) -> None:
    package_summary = completion.get("package") if isinstance(completion, dict) and isinstance(completion.get("package"), dict) else {}
    manifest_reconstruction = (
        package_manifest.get("reconstruction")
        if isinstance(package_manifest, dict) and isinstance(package_manifest.get("reconstruction"), dict)
        else {}
    )
    artifact_reconstruction = (
        reconstruction_artifact.get("reconstruction")
        if isinstance(reconstruction_artifact, dict) and isinstance(reconstruction_artifact.get("reconstruction"), dict)
        else {}
    )
    catalog_reconstruction = (
        catalog_entry.get("reconstruction")
        if isinstance(catalog_entry, dict) and isinstance(catalog_entry.get("reconstruction"), dict)
        else {}
    )
    sources = {
        "lsl_runtime_status.asset_strategy": status.get("asset_strategy"),
        "completion.package.asset_strategy": package_summary.get("asset_strategy"),
        "run_package_manifest.asset_strategy": package_manifest.get("asset_strategy") if isinstance(package_manifest, dict) else "",
        "run_package_manifest.reconstruction.package_asset_strategy": manifest_reconstruction.get("package_asset_strategy"),
        "reconstruction_contract.asset_strategy": reconstruction_artifact.get("asset_strategy") if isinstance(reconstruction_artifact, dict) else "",
        "reconstruction_contract.reconstruction.package_asset_strategy": artifact_reconstruction.get("package_asset_strategy"),
        "phone_run_catalog_entry.asset_strategy": catalog_entry.get("asset_strategy") if isinstance(catalog_entry, dict) else "",
        "phone_run_catalog_entry.reconstruction.package_asset_strategy": catalog_reconstruction.get("package_asset_strategy"),
    }
    present = {name: str(value).strip() for name, value in sources.items() if str(value or "").strip()}
    if not present:
        return
    unique = sorted(set(present.values()))
    if len(unique) > 1:
        observed = ", ".join(f"{name}={value!r}" for name, value in sorted(present.items()))
        failures.append(f"asset_strategy differs across phone run artifacts: {observed}")
        return

    strategy = unique[0]
    if expect_lightweight_materializations:
        if strategy != "trial_building_blocks_only":
            failures.append("lightweight materialization evidence must use asset_strategy='trial_building_blocks_only'")
        for required in (
            "lsl_runtime_status.asset_strategy",
            "run_package_manifest.asset_strategy",
            "run_package_manifest.reconstruction.package_asset_strategy",
        ):
            if not str(sources.get(required) or "").strip():
                failures.append(f"{required} is missing from lightweight phone-run artifact")
        if completion and not str(sources.get("completion.package.asset_strategy") or "").strip():
            failures.append("completion.package.asset_strategy is missing from lightweight phone-run artifact")
        if reconstruction_artifact:
            for required in (
                "reconstruction_contract.asset_strategy",
                "reconstruction_contract.reconstruction.package_asset_strategy",
            ):
                if not str(sources.get(required) or "").strip():
                    failures.append(f"{required} is missing from lightweight phone-run artifact")
        if catalog_entry:
            for required in (
                "phone_run_catalog_entry.asset_strategy",
                "phone_run_catalog_entry.reconstruction.package_asset_strategy",
            ):
                if not str(sources.get(required) or "").strip():
                    failures.append(f"{required} is missing from lightweight phone-run artifact")
    elif (
        isinstance(package_manifest, dict)
        and str(package_manifest.get("asset_strategy") or "").strip()
        and not str(status.get("asset_strategy") or "").strip()
    ):
        warnings.append("run package declares asset_strategy but lsl_runtime_status does not mirror it")


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


def _validate_phone_run_catalog_index(
    *,
    status: dict[str, Any],
    catalog_entry: dict[str, Any] | None,
    catalog_index: dict[str, Any] | None,
    catalog_runs_rows: list[dict[str, Any]],
    catalog_latest_entries: list[dict[str, Any]],
    failures: list[str],
    warnings: list[str],
    expect_run_catalog_index: bool,
) -> None:
    has_catalog_index_evidence = bool(catalog_index) or bool(catalog_runs_rows) or bool(catalog_latest_entries)
    if not has_catalog_index_evidence:
        message = "phone run catalog index is missing"
        if expect_run_catalog_index:
            failures.append(message)
        elif catalog_entry:
            warnings.append(f"{message}; rerun with --expect-run-catalog-index for strict checks")
        return

    if not catalog_index:
        if expect_run_catalog_index:
            failures.append("phone run catalog index is missing")
        return
    if catalog_index.get("schema") != ANDROID_PHONE_RUN_CATALOG_SCHEMA:
        failures.append("phone run catalog index schema mismatch")

    participants = catalog_index.get("participants") if isinstance(catalog_index.get("participants"), list) else []
    if "participant_count" in catalog_index and _clean_int(catalog_index.get("participant_count")) != len(participants):
        failures.append("phone run catalog index participant_count differs from participants list length")
    if "run_count" in catalog_index and catalog_runs_rows and _clean_int(catalog_index.get("run_count")) != len(catalog_runs_rows):
        failures.append("phone run catalog index run_count differs from loaded runs.jsonl row count")

    participant_id = _first_nonblank(
        catalog_entry.get("participant_id") if catalog_entry else "",
        status.get("participant_id"),
    )
    run_id = _first_nonblank(
        catalog_entry.get("run_id") if catalog_entry else "",
        status.get("run_id"),
    )
    participant_row = None
    if participant_id:
        for row in participants:
            if isinstance(row, dict) and _catalog_text(row.get("participant_id")) == participant_id:
                participant_row = row
                break
        if participant_row is None:
            message = f"phone run catalog index is missing participant_id {participant_id}"
            if expect_run_catalog_index:
                failures.append(message)
            else:
                warnings.append(message)

    if participant_row is not None:
        participant_dir = _catalog_text(participant_row.get("participant_dir"))
        if not participant_dir:
            failures.append("phone run catalog index participant row is missing participant_dir")
        if _clean_int(participant_row.get("run_count")) <= 0:
            failures.append("phone run catalog index participant row has no runs")
        if not _catalog_text(participant_row.get("latest_run_id")):
            failures.append("phone run catalog index participant row is missing latest_run_id")

    matching_run_rows = [row for row in catalog_runs_rows if _catalog_text(row.get("run_id")) == run_id] if run_id else []
    if not catalog_runs_rows:
        if expect_run_catalog_index:
            failures.append("phone run catalog runs.jsonl rows are missing")
    elif run_id and not matching_run_rows:
        message = f"phone run catalog runs.jsonl is missing run_id {run_id}"
        if expect_run_catalog_index:
            failures.append(message)
        else:
            warnings.append(message)
    elif matching_run_rows and catalog_entry:
        _compare_phone_run_catalog_entry(
            label="phone run catalog runs.jsonl",
            observed=matching_run_rows[-1],
            expected=catalog_entry,
            failures=failures,
        )

    if not catalog_latest_entries:
        if expect_run_catalog_index:
            failures.append("phone run catalog latest_run.json entries are missing")
        return

    latest_for_participant = None
    if participant_id:
        for latest in catalog_latest_entries:
            if _catalog_text(latest.get("participant_id")) == participant_id:
                latest_for_participant = latest
                break
            if participant_row is not None and _catalog_text(latest.get("_catalog_participant_dir")) == _catalog_text(participant_row.get("participant_dir")):
                latest_for_participant = latest
                break
    if latest_for_participant is None:
        message = f"phone run catalog latest_run.json is missing participant_id {participant_id}" if participant_id else "phone run catalog latest_run.json cannot be matched to this participant"
        if expect_run_catalog_index:
            failures.append(message)
        else:
            warnings.append(message)
        return

    latest_run_id = _catalog_text(participant_row.get("latest_run_id")) if participant_row is not None else ""
    if latest_run_id and _catalog_text(latest_for_participant.get("run_id")) != latest_run_id:
        failures.append("phone run catalog latest_run.json run_id differs from index latest_run_id")
    if catalog_entry and run_id and (not latest_run_id or latest_run_id == run_id):
        _compare_phone_run_catalog_entry(
            label="phone run catalog latest_run.json",
            observed=latest_for_participant,
            expected=catalog_entry,
            failures=failures,
        )


def _compare_phone_run_catalog_entry(
    *,
    label: str,
    observed: dict[str, Any],
    expected: dict[str, Any],
    failures: list[str],
) -> None:
    for field in (
        "schema",
        "package_id",
        "run_id",
        "participant_id",
        "session_id",
        "session_group_id",
        "part_session_id",
        "part_number",
        "artifact_file",
        "asset_strategy",
        "completed",
        "completion_reason",
    ):
        expected_value = _catalog_text(expected.get(field))
        observed_value = _catalog_text(observed.get(field))
        if expected_value and observed_value and expected_value != observed_value:
            failures.append(f"{label} {field} differs from phone_run_catalog_entry.json")
    expected_reconstruction = expected.get("reconstruction") if isinstance(expected.get("reconstruction"), dict) else {}
    observed_reconstruction = observed.get("reconstruction") if isinstance(observed.get("reconstruction"), dict) else {}
    expected_hash = _catalog_text(expected_reconstruction.get("schedule_hash"))
    observed_hash = _catalog_text(observed_reconstruction.get("schedule_hash"))
    if expected_hash and observed_hash and expected_hash != observed_hash:
        failures.append(f"{label} reconstruction.schedule_hash differs from phone_run_catalog_entry.json")


def _first_nonblank(*values: Any) -> str:
    for value in values:
        text = _catalog_text(value)
        if text:
            return text
    return ""


def _catalog_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value or "").strip()


def _validate_participant_and_haptic_metadata(
    *,
    status: dict[str, Any],
    completion: dict[str, Any] | None,
    catalog_entry: dict[str, Any] | None,
    participant_metadata: dict[str, Any] | None,
    haptic_capability: dict[str, Any] | None,
    failures: list[str],
    warnings: list[str],
) -> None:
    embedded_participant = (
        completion.get("participant_metadata")
        if isinstance(completion, dict) and isinstance(completion.get("participant_metadata"), dict)
        else None
    )
    embedded_haptic = (
        completion.get("haptic")
        if isinstance(completion, dict) and isinstance(completion.get("haptic"), dict)
        else None
    )
    participant = participant_metadata or embedded_participant
    haptic = haptic_capability or embedded_haptic
    if participant_metadata and embedded_participant:
        _compare_metadata_fields(
            participant_metadata,
            embedded_participant,
            fields=[
                "schema",
                "participant_id",
                "session_id",
                "session_group_id",
                "part_session_id",
                "part_number",
                "age_years",
                "handedness",
                "gender",
                "tactile_threshold_percent",
                "tactile_threshold_source",
                "stream_privacy",
                "tactile_threshold_calibration_schema",
                "tactile_threshold_calibration_status",
            ],
            label="participant_metadata sidecar",
            other_label="completion participant_metadata",
            failures=failures,
        )
    elif embedded_participant and not participant_metadata:
        warnings.append("completion embeds participant_metadata but participant_metadata.json sidecar is missing")
    if haptic_capability and embedded_haptic:
        _compare_metadata_fields(
            haptic_capability,
            embedded_haptic,
            fields=[
                "schema",
                "has_vibrator",
                "has_amplitude_control",
                "calibration_policy",
                "device_model",
                "android_sdk",
                "calibration_status",
                "recommended_threshold_percent",
                "recommended_amplitude",
            ],
            label="haptic_capability sidecar",
            other_label="completion haptic",
            failures=failures,
        )
    elif embedded_haptic and not haptic_capability:
        warnings.append("completion embeds haptic capability but haptic_capability.json sidecar is missing")

    if participant is None:
        if completion and isinstance(completion.get("events"), list):
            warnings.append("phone run artifact does not include participant metadata")
    else:
        _validate_participant_metadata(status, catalog_entry, participant, failures, warnings)

    if haptic is None:
        if completion and isinstance(completion.get("events"), list):
            warnings.append("phone run artifact does not include haptic capability metadata")
    else:
        _validate_haptic_capability(haptic, failures)


def _validate_participant_metadata(
    status: dict[str, Any],
    catalog_entry: dict[str, Any] | None,
    participant: dict[str, Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    if participant.get("schema") != ANDROID_PHONE_PARTICIPANT_METADATA_SCHEMA:
        failures.append("participant_metadata schema mismatch")
    if participant.get("stream_privacy") != "metadata_payload_only":
        failures.append("participant_metadata stream_privacy must be metadata_payload_only")
    forbidden_name_fields = [field for field in ("name", "participant_name", "full_name") if str(participant.get(field) or "").strip()]
    if forbidden_name_fields:
        failures.append(f"participant_metadata must not include direct name fields: {', '.join(forbidden_name_fields)}")
    for field in ("participant_id", "session_id", "session_group_id", "part_session_id", "part_number"):
        status_value = str(status.get(field) or "").strip()
        metadata_value = str(participant.get(field) or "").strip()
        if status_value and metadata_value and status_value != metadata_value:
            failures.append(f"participant_metadata {field} differs from lsl_runtime_status")
    source = str(participant.get("tactile_threshold_source") or "").strip()
    if source and source not in {"manual_entry", "android_haptic_calibration"}:
        failures.append("participant_metadata tactile_threshold_source is not recognized")
    threshold = participant.get("tactile_threshold_percent")
    threshold_text = str(threshold if threshold is not None else "").strip()
    if threshold_text:
        value = _safe_float(threshold)
        if value != value or value < 0.0 or value > 100.0:
            failures.append("participant_metadata tactile_threshold_percent must be between 0 and 100")
    elif source == "android_haptic_calibration":
        failures.append("android haptic calibration participant metadata requires tactile_threshold_percent")
    if source == "android_haptic_calibration":
        if participant.get("tactile_threshold_calibration_schema") != ANDROID_HAPTIC_CALIBRATION_SCHEMA:
            failures.append("participant_metadata tactile_threshold_calibration_schema mismatch")
        if not str(participant.get("tactile_threshold_calibration_status") or "").strip():
            failures.append("participant_metadata is missing tactile_threshold_calibration_status")
    if catalog_entry:
        summary = catalog_entry.get("participant_metadata_summary") if isinstance(catalog_entry.get("participant_metadata_summary"), dict) else {}
        for field in ("participant_id", "age_years", "handedness", "gender", "tactile_threshold_percent", "tactile_threshold_source"):
            metadata_value = str(participant.get(field) or "").strip()
            summary_value = str(summary.get(field) or "").strip()
            if metadata_value and summary_value and metadata_value != summary_value:
                failures.append(f"phone run catalog participant_metadata_summary {field} differs from participant_metadata")
        privacy = catalog_entry.get("privacy") if isinstance(catalog_entry.get("privacy"), dict) else {}
        if privacy.get("demographics_in_stream_name") is not False:
            failures.append("phone run catalog privacy must keep demographics out of stream names")
    else:
        warnings.append("participant metadata cannot be compared to phone run catalog summary because catalog entry is missing")


def _validate_haptic_capability(haptic: dict[str, Any], failures: list[str]) -> None:
    if haptic.get("schema") != ANDROID_HAPTIC_CAPABILITY_SCHEMA:
        failures.append("haptic_capability schema mismatch")
    for field in ("has_vibrator", "has_amplitude_control"):
        if not isinstance(haptic.get(field), bool):
            failures.append(f"haptic_capability {field} must be boolean")
    policy = str(haptic.get("calibration_policy") or "")
    if policy not in {"amplitude_percent_supported", "binary_detection_only"}:
        failures.append("haptic_capability calibration_policy is not recognized")
    if haptic.get("has_amplitude_control") is True and policy != "amplitude_percent_supported":
        failures.append("haptic_capability amplitude control requires amplitude_percent_supported policy")
    if haptic.get("has_amplitude_control") is False and policy != "binary_detection_only":
        failures.append("haptic_capability no-amplitude devices must use binary_detection_only policy")
    if "recommended_threshold_percent" in haptic and haptic.get("recommended_threshold_percent") not in (None, ""):
        value = _safe_float(haptic.get("recommended_threshold_percent"))
        if value != value or value < 0.0 or value > 100.0:
            failures.append("haptic_capability recommended_threshold_percent must be between 0 and 100")
    if "recommended_amplitude" in haptic and haptic.get("recommended_amplitude") not in (None, ""):
        amplitude = _safe_int(haptic.get("recommended_amplitude"))
        if amplitude != -1 and not (1 <= amplitude <= 255):
            failures.append("haptic_capability recommended_amplitude must be -1 or 1..255")
    calibration = haptic.get("calibration_result") if isinstance(haptic.get("calibration_result"), dict) else None
    if calibration is not None:
        if calibration.get("schema") != ANDROID_HAPTIC_CALIBRATION_SCHEMA:
            failures.append("haptic_capability calibration_result schema mismatch")
        if not str(calibration.get("status") or "").strip():
            failures.append("haptic_capability calibration_result is missing status")
        if "recommended_threshold_percent" in calibration and calibration.get("recommended_threshold_percent") not in (None, ""):
            value = _safe_float(calibration.get("recommended_threshold_percent"))
            if value != value or value < 0.0 or value > 100.0:
                failures.append("haptic_capability calibration_result recommended_threshold_percent must be between 0 and 100")
        if "recommended_amplitude" in calibration:
            amplitude = _safe_int(calibration.get("recommended_amplitude"))
            if amplitude != -1 and not (1 <= amplitude <= 255):
                failures.append("haptic_capability calibration_result recommended_amplitude must be -1 or 1..255")
        responses = calibration.get("responses")
        if responses is not None and not isinstance(responses, list):
            failures.append("haptic_capability calibration_result responses must be an array")


def _compare_metadata_fields(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    fields: list[str],
    label: str,
    other_label: str,
    failures: list[str],
) -> None:
    for field in fields:
        left_present = field in left and left.get(field) is not None
        right_present = field in right and right.get(field) is not None
        if not left_present and not right_present:
            continue
        if _metadata_value(left.get(field)) != _metadata_value(right.get(field)):
            failures.append(f"{label} {field} differs from {other_label}")


def _validate_phone_event_diary(
    *,
    completion: dict[str, Any] | None,
    event_rows: list[dict[str, Any]],
    failures: list[str],
    warnings: list[str],
    expect_event_diary: bool,
) -> None:
    embedded_events = [
        event
        for event in list((completion or {}).get("events") or [])
        if isinstance(event, dict)
    ]
    if not event_rows:
        message = "phone event diary events.csv is missing"
        if expect_event_diary:
            failures.append(message)
        elif embedded_events:
            warnings.append(f"{message}; rerun with --expect-event-diary for strict checks")
        return

    event_ids = [_clean_int(row.get("event_id")) for row in event_rows if _clean_int(row.get("event_id")) > 0]
    duplicate_ids = _duplicate_ints(event_ids)
    if duplicate_ids:
        failures.append(f"events.csv has duplicate event ids: {', '.join(str(item) for item in duplicate_ids[:10])}")

    required_fields = ("event_id", "type", "package_id", "run_id", "phone_unix_ms", "phone_elapsed_realtime_ms")
    for index, row in enumerate(event_rows, start=1):
        prefix = f"events.csv row {index}"
        for field in required_fields:
            if field not in row or not str(row.get(field) or "").strip():
                failures.append(f"{prefix} is missing {field}")

    if not embedded_events:
        warnings.append("events.csv was present without completion events; only event-diary self-consistency was checked")
        return

    embedded_ids = [_clean_int(event.get("event_id")) for event in embedded_events if _clean_int(event.get("event_id")) > 0]
    if event_ids != embedded_ids:
        failures.append("events.csv event ids differ from completion.json embedded events")
    if len(event_rows) != len(embedded_events):
        failures.append("events.csv row count differs from completion events")

    embedded_by_id = {
        _clean_int(event.get("event_id")): event
        for event in embedded_events
        if _clean_int(event.get("event_id")) > 0
    }
    missing_event_ids = sorted(set(embedded_by_id) - set(event_ids))
    extra_event_ids = sorted(set(event_ids) - set(embedded_by_id))
    if missing_event_ids:
        failures.append(f"events.csv is missing event ids: {', '.join(str(item) for item in missing_event_ids[:10])}")
    if extra_event_ids:
        failures.append(f"events.csv has extra event ids: {', '.join(str(item) for item in extra_event_ids[:10])}")

    for index, row in enumerate(event_rows, start=1):
        event_id = _clean_int(row.get("event_id"))
        event = embedded_by_id.get(event_id)
        if event is None:
            continue
        prefix = f"events.csv row {index}"
        for field, expected_value in _primitive_event_fields(event).items():
            if field not in row:
                failures.append(f"{prefix} is missing primitive field {field}")
                continue
            observed = _csv_scalar(row.get(field))
            expected = _csv_scalar(expected_value)
            if observed != expected:
                failures.append(f"{prefix} {field} differs from completion event")


def _primitive_event_fields(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if value is None or isinstance(value, (str, int, float, bool))
    }


def _csv_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value).strip()


def _validate_phone_command_diary(
    *,
    status: dict[str, Any],
    completion: dict[str, Any] | None,
    command_diary_rows: list[dict[str, Any]],
    failures: list[str],
    warnings: list[str],
    expect_command_acks: bool,
) -> None:
    embedded_rows = [
        row
        for row in list((completion or {}).get("command_diary") or [])
        if isinstance(row, dict)
    ]
    rows = command_diary_rows or embedded_rows
    if not rows:
        if expect_command_acks:
            failures.append("phone-run command ack validation requires command_diary rows")
        return
    if command_diary_rows and embedded_rows:
        file_ids = [str(row.get("command_id") or "") for row in command_diary_rows]
        embedded_ids = [str(row.get("command_id") or "") for row in embedded_rows]
        if file_ids != embedded_ids:
            failures.append("command_diary.jsonl command ids differ from completion.json embedded command_diary")

    operator_events = [
        event
        for event in list((completion or {}).get("events") or [])
        if isinstance(event, dict) and event.get("type") == "operator_command"
    ]
    event_by_command_id = {
        str(event.get("command_id") or ""): event
        for event in operator_events
        if str(event.get("command_id") or "").strip()
    }
    native_rows = 0
    native_ack_rows = 0
    for index, row in enumerate(rows, start=1):
        prefix = f"phone command diary row {index}"
        if row.get("schema") != "pps-android-command-diary.v1":
            failures.append(f"{prefix} schema mismatch")
        command_id = str(row.get("command_id") or "")
        command = str(row.get("command") or "")
        command_source = str(row.get("command_source") or "")
        row_status = str(row.get("status") or "")
        if not command_id:
            failures.append(f"{prefix} is missing command_id")
        if not command:
            failures.append(f"{prefix} is missing command")
        if command_source not in {"native_lsl", "phone_ui_or_runtime"}:
            failures.append(f"{prefix} command_source must be native_lsl or phone_ui_or_runtime")
        if row_status not in {"applied", "rejected"}:
            failures.append(f"{prefix} status must be applied or rejected")
        if status.get("package_id") and row.get("package_id") and str(row.get("package_id")) != str(status.get("package_id")):
            failures.append(f"{prefix} package_id differs from lsl_runtime_status")
        if status.get("run_id") and row.get("run_id") and str(row.get("run_id")) != str(status.get("run_id")):
            failures.append(f"{prefix} run_id differs from lsl_runtime_status")
        if command_id and operator_events:
            event = event_by_command_id.get(command_id)
            if event is None:
                failures.append(f"{prefix} is missing matching operator_command event")
            else:
                if command and str(event.get("command") or "") != command:
                    failures.append(f"{prefix} command differs from matching operator_command event")
                if row_status and str(event.get("status") or "") != row_status:
                    failures.append(f"{prefix} status differs from matching operator_command event")
                if command_source == "native_lsl" and str(event.get("command_source") or "") != "native_lsl":
                    failures.append(f"{prefix} native_lsl source differs from matching operator_command event")

        if command_source != "native_lsl":
            continue
        native_rows += 1
        ack_channels = list(row.get("ack_channels") or [])
        if ack_channels and ack_channels != list(LSL_ACK_CHANNELS):
            failures.append(f"{prefix} ack channel order mismatch")
        ack_sample = list(row.get("ack_sample") or [])
        if len(ack_sample) != len(LSL_ACK_CHANNELS):
            failures.append(f"{prefix} ack sample channel count mismatch")
        else:
            native_ack_rows += 1
            if ack_sample[0] != ACK_SCHEMA:
                failures.append(f"{prefix} ack sample schema mismatch")
            if command_id and ack_sample[1] != command_id:
                failures.append(f"{prefix} ack command_id does not match diary command_id")
            if row.get("session_id") and ack_sample[2] != row.get("session_id"):
                failures.append(f"{prefix} ack session_id differs from diary row")
            if row_status and ack_sample[4] != row_status:
                failures.append(f"{prefix} ack status differs from diary row")
            row_reason = str(row.get("reason") or "")
            if ack_sample[5] != row_reason:
                failures.append(f"{prefix} ack reason differs from diary row")
            for time_index, field in ((6, "received_lsl_time"), (7, "applied_lsl_time"), (8, "ack_lsl_time")):
                try:
                    sample_value = float(ack_sample[time_index])
                    row_value = float(row.get(field))
                except (TypeError, ValueError):
                    failures.append(f"{prefix} {field} is not numeric")
                    continue
                if abs(sample_value - row_value) > 1e-6:
                    failures.append(f"{prefix} ack {field} differs from diary row")
            _parse_json_object(str(ack_sample[9] or "{}"), f"{prefix} ack payload", failures)
        if expect_command_acks and row.get("ack_sent") is not True:
            failures.append(f"{prefix} was expected to send a PPSCommandAcksV1 sample")

    if expect_command_acks:
        if native_rows <= 0:
            failures.append("phone-run command ack validation expected at least one native_lsl command diary row")
        elif not operator_events:
            failures.append("phone-run command ack validation requires matching operator_command events")
        if native_ack_rows <= 0:
            failures.append("phone-run command ack validation expected at least one PPSCommandAcksV1 ack sample")
    elif native_rows > 0 and native_ack_rows <= 0:
        warnings.append("native_lsl command diary rows do not include ack samples; rerun with --expect-command-acks for strict checks")


def _validate_phone_marker_mirror(
    *,
    status: dict[str, Any],
    completion: dict[str, Any] | None,
    marker_mirror_rows: list[dict[str, Any]],
    failures: list[str],
    warnings: list[str],
    expect_native_transport: bool,
) -> None:
    embedded_rows = [
        row
        for row in list((completion or {}).get("lsl_marker_mirror") or [])
        if isinstance(row, dict)
    ]
    events = [
        event
        for event in list((completion or {}).get("events") or [])
        if isinstance(event, dict)
    ]
    rows = marker_mirror_rows or embedded_rows
    if not rows:
        if events:
            failures.append("phone marker mirror is missing while completion events are present")
        return
    if marker_mirror_rows and embedded_rows:
        file_ids = [_clean_int(row.get("event_id")) for row in marker_mirror_rows]
        embedded_ids = [_clean_int(row.get("event_id")) for row in embedded_rows]
        if file_ids != embedded_ids:
            failures.append("lsl_marker_mirror.csv event ids differ from completion.json embedded marker mirror")

    event_ids = [_clean_int(row.get("event_id")) for row in rows if _clean_int(row.get("event_id")) > 0]
    duplicate_ids = _duplicate_ints(event_ids)
    if duplicate_ids:
        failures.append(f"phone marker mirror has duplicate event ids: {', '.join(str(item) for item in duplicate_ids[:10])}")
    if events and len(rows) != len(events):
        failures.append("phone marker mirror row count differs from completion events")

    events_by_id = {
        _clean_int(event.get("event_id")): event
        for event in events
        if _clean_int(event.get("event_id")) > 0
    }
    if events:
        missing_event_ids = sorted(set(events_by_id) - set(event_ids))
        extra_marker_ids = sorted(set(event_ids) - set(events_by_id))
        if missing_event_ids:
            failures.append(f"phone marker mirror is missing event ids: {', '.join(str(item) for item in missing_event_ids[:10])}")
        if extra_marker_ids:
            failures.append(f"phone marker mirror has extra event ids: {', '.join(str(item) for item in extra_marker_ids[:10])}")

    required_marker_fields = [
        field for field in LSL_MARKER_CHANNELS if field != "sample_index"
    ]
    for index, row in enumerate(rows, start=1):
        prefix = f"phone marker mirror row {index}"
        for field in required_marker_fields:
            if field not in row:
                failures.append(f"{prefix} is missing {field}")
        event_id = _clean_int(row.get("event_id"))
        event_type = str(row.get("event_type") or "")
        if str(row.get("marker_version") or "") != MARKER_VERSION:
            failures.append(f"{prefix} marker_version mismatch")
        expected_code = ANDROID_PHONE_EVENT_CODES.get(event_type, ANDROID_UNKNOWN_EVENT_CODE)
        if _clean_int(row.get("event_code")) != expected_code:
            failures.append(f"{prefix} event_code does not match Android phone event type")
        if str(row.get("timestamp_quality") or "") != "android_elapsed_realtime":
            failures.append(f"{prefix} timestamp_quality must be android_elapsed_realtime")
        if not str(row.get("trigger_key") or "").strip():
            failures.append(f"{prefix} is missing trigger_key")
        if not str(row.get("marker_name") or "").strip():
            failures.append(f"{prefix} is missing marker_name")
        payload = _parse_json_object(str(row.get("payload_json") or "{}"), f"{prefix} payload_json", failures)
        if payload is None:
            continue
        if event_id and _clean_int(payload.get("event_id")) != event_id:
            failures.append(f"{prefix} payload event_id differs from marker")
        if event_type and str(payload.get("type") or "") != event_type:
            failures.append(f"{prefix} payload type differs from marker event_type")
        for field in ("package_id", "run_id"):
            marker_value = str(row.get(field) or "")
            payload_value = str(payload.get(field) or "")
            if marker_value and payload_value and marker_value != payload_value:
                failures.append(f"{prefix} payload {field} differs from marker")
            status_value = str(status.get(field) or "")
            if expect_native_transport and status_value and marker_value and marker_value != status_value:
                failures.append(f"{prefix} {field} differs from lsl_runtime_status")
        for field in ("session_id", "participant_id", "session_group_id", "part_session_id", "part_number"):
            status_value = str(status.get(field) or "")
            marker_value = str(row.get(field) or "")
            if expect_native_transport and status_value and marker_value and marker_value != status_value:
                failures.append(f"{prefix} {field} differs from lsl_runtime_status")
        event = events_by_id.get(event_id)
        if event is not None:
            if str(event.get("type") or "") != event_type:
                failures.append(f"{prefix} event_type differs from completion event")
            if str(event.get("package_id") or "") and str(payload.get("package_id") or "") != str(event.get("package_id") or ""):
                failures.append(f"{prefix} payload package_id differs from completion event")
            if str(event.get("run_id") or "") and str(payload.get("run_id") or "") != str(event.get("run_id") or ""):
                failures.append(f"{prefix} payload run_id differs from completion event")

    if rows and not events:
        warnings.append("phone marker mirror was present without completion events; only marker self-consistency was checked")


def _validate_phone_trigger_code_mirror(
    *,
    completion: dict[str, Any] | None,
    marker_mirror_rows: list[dict[str, Any]],
    trigger_code_rows: list[dict[str, Any]],
    failures: list[str],
    warnings: list[str],
    expect_trigger_code_mirror: bool,
) -> None:
    embedded_markers = [
        row
        for row in list((completion or {}).get("lsl_marker_mirror") or [])
        if isinstance(row, dict)
    ]
    marker_rows = marker_mirror_rows or embedded_markers
    if not trigger_code_rows:
        message = "phone trigger-code mirror trigger_codes.csv is missing"
        if expect_trigger_code_mirror:
            failures.append(message)
        elif marker_rows:
            warnings.append(f"{message}; rerun with --expect-trigger-code-mirror for strict checks")
        return

    required_fields = ("event_id", "event_code", "event_type", "trigger_key", "phone_elapsed_realtime_ms")
    for index, row in enumerate(trigger_code_rows, start=1):
        prefix = f"trigger_codes.csv row {index}"
        for field in required_fields:
            if field not in row or not str(row.get(field) or "").strip():
                failures.append(f"{prefix} is missing {field}")

    event_ids = [_clean_int(row.get("event_id")) for row in trigger_code_rows if _clean_int(row.get("event_id")) > 0]
    duplicate_ids = _duplicate_ints(event_ids)
    if duplicate_ids:
        failures.append(f"trigger_codes.csv has duplicate event ids: {', '.join(str(item) for item in duplicate_ids[:10])}")

    if not marker_rows:
        warnings.append("trigger_codes.csv was present without marker mirror rows; only trigger-code self-consistency was checked")
        return

    marker_ids = [_clean_int(row.get("event_id")) for row in marker_rows if _clean_int(row.get("event_id")) > 0]
    if event_ids != marker_ids:
        failures.append("trigger_codes.csv event ids differ from lsl_marker_mirror event ids")
    if len(trigger_code_rows) != len(marker_rows):
        failures.append("trigger_codes.csv row count differs from lsl_marker_mirror rows")

    marker_by_id = {
        _clean_int(row.get("event_id")): row
        for row in marker_rows
        if _clean_int(row.get("event_id")) > 0
    }
    missing_marker_ids = sorted(set(marker_by_id) - set(event_ids))
    extra_trigger_ids = sorted(set(event_ids) - set(marker_by_id))
    if missing_marker_ids:
        failures.append(f"trigger_codes.csv is missing marker event ids: {', '.join(str(item) for item in missing_marker_ids[:10])}")
    if extra_trigger_ids:
        failures.append(f"trigger_codes.csv has extra marker event ids: {', '.join(str(item) for item in extra_trigger_ids[:10])}")

    for index, row in enumerate(trigger_code_rows, start=1):
        event_id = _clean_int(row.get("event_id"))
        marker = marker_by_id.get(event_id)
        if marker is None:
            continue
        prefix = f"trigger_codes.csv row {index}"
        for field in ("event_code", "event_type", "trigger_key", "phone_elapsed_realtime_ms"):
            observed = _csv_scalar(row.get(field))
            expected = _csv_scalar(marker.get(field))
            if observed and expected and observed != expected:
                failures.append(f"{prefix} {field} differs from lsl_marker_mirror")
        if not _clean_int(row.get("event_code")):
            failures.append(f"{prefix} event_code must be an integer trigger code")


def _validate_phone_audiotrack_timing_evidence(
    *,
    completion: dict[str, Any] | None,
    package_manifest: dict[str, Any] | None,
    failures: list[str],
    warnings: list[str],
    expect_audiotrack_timing_evidence: bool,
) -> None:
    events = [
        event
        for event in list((completion or {}).get("events") or [])
        if isinstance(event, dict)
    ]
    if not events:
        if expect_audiotrack_timing_evidence:
            failures.append("AudioTrack timing validation requires completion events")
        return

    block_starts = [event for event in events if event.get("type") == "block_start"]
    cue_events = [event for event in events if event.get("type") == "vibration_cue"]
    if not block_starts:
        if expect_audiotrack_timing_evidence:
            failures.append("AudioTrack timing validation requires block_start events")
        return
    blocks_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for index, event in enumerate(block_starts, start=1):
        prefix = f"AudioTrack block_start event {index}"
        key = _phone_event_block_key(event)
        if key in blocks_by_key:
            failures.append(f"{prefix} duplicates block identity {key}")
        else:
            blocks_by_key[key] = event
        strategy = str(event.get("audio_timing_strategy") or "")
        if strategy != ANDROID_AUDIO_TIMING_STRATEGY:
            if expect_audiotrack_timing_evidence or strategy:
                failures.append(f"{prefix} audio_timing_strategy must be {ANDROID_AUDIO_TIMING_STRATEGY}")
            continue
        _validate_positive_int_fields(
            event,
            fields=[
                "audio_sample_rate_hz",
                "audio_channel_count",
                "audio_bits_per_sample",
                "audio_frame_count",
                "audio_duration_ms",
                "audio_data_size_bytes",
            ],
            label=prefix,
            failures=failures,
            require_all=expect_audiotrack_timing_evidence,
        )
        sample_rate = _safe_int(event.get("audio_sample_rate_hz"))
        frame_count = _safe_int(event.get("audio_frame_count"))
        duration_ms = _safe_int(event.get("audio_duration_ms"))
        if sample_rate > 0 and frame_count > 0 and duration_ms > 0:
            expected_duration_ms = round(frame_count * 1000.0 / sample_rate)
            if abs(duration_ms - expected_duration_ms) > 2:
                failures.append(f"{prefix} audio_duration_ms differs from frame_count/sample_rate")

    expected_cue_count = _package_manifest_tactile_cue_count(package_manifest)
    if expect_audiotrack_timing_evidence:
        if expected_cue_count > 0 and len(cue_events) < expected_cue_count:
            failures.append(
                f"AudioTrack timing validation expected at least {expected_cue_count} vibration_cue events, got {len(cue_events)}"
            )
        elif expected_cue_count == 0 and not cue_events:
            warnings.append("AudioTrack timing strict mode found no tactile cues declared or observed")

    for index, event in enumerate(cue_events, start=1):
        prefix = f"AudioTrack vibration_cue event {index}"
        scheduler = str(event.get("audio_scheduler") or "")
        if scheduler != ANDROID_CUE_AUDIO_SCHEDULER:
            if expect_audiotrack_timing_evidence or scheduler:
                failures.append(f"{prefix} audio_scheduler must be {ANDROID_CUE_AUDIO_SCHEDULER}")
            continue
        _validate_positive_int_fields(
            event,
            fields=[
                "audio_delivery_elapsed_realtime_ms",
            ],
            label=prefix,
            failures=failures,
            require_all=expect_audiotrack_timing_evidence,
        )
        _validate_nonnegative_int_fields(
            event,
            fields=[
                "scheduled_audio_frame",
                "audio_playback_head_frame",
                "audio_cue_jitter_frames",
            ],
            label=prefix,
            failures=failures,
            require_all=expect_audiotrack_timing_evidence,
        )
        scheduled_frame = _safe_int(event.get("scheduled_audio_frame"), fallback=-1)
        head_frame = _safe_int(event.get("audio_playback_head_frame"), fallback=-1)
        jitter_frames = _safe_int(event.get("audio_cue_jitter_frames"), fallback=-1)
        if scheduled_frame >= 0 and head_frame >= 0:
            if head_frame < scheduled_frame:
                failures.append(f"{prefix} audio_playback_head_frame precedes scheduled_audio_frame")
            expected_jitter = head_frame - scheduled_frame
            if jitter_frames >= 0 and jitter_frames != expected_jitter:
                failures.append(f"{prefix} audio_cue_jitter_frames differs from playback_head-scheduled frame")

        block = blocks_by_key.get(_phone_event_block_key(event))
        if block is None:
            if expect_audiotrack_timing_evidence:
                failures.append(f"{prefix} has no matching block_start event")
            continue
        sample_rate = _safe_int(block.get("audio_sample_rate_hz"))
        jitter_ms = _safe_float(event.get("audio_cue_jitter_ms"))
        if sample_rate > 0 and jitter_frames >= 0 and jitter_ms == jitter_ms:
            expected_jitter_ms = jitter_frames * 1000.0 / sample_rate
            if abs(jitter_ms - expected_jitter_ms) > 0.25:
                failures.append(f"{prefix} audio_cue_jitter_ms differs from frame jitter and sample rate")


def _phone_event_block_key(event: dict[str, Any]) -> tuple[str, str]:
    return (str(event.get("block_id") or ""), str(event.get("block_index") or ""))


def _package_manifest_tactile_cue_count(package_manifest: dict[str, Any] | None) -> int:
    if not isinstance(package_manifest, dict):
        return 0
    count = 0
    for block in list(package_manifest.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("tactile_cues"), list):
            count += len(block.get("tactile_cues") or [])
        else:
            count += _safe_int(block.get("tactile_cue_count"))
    return count


def _validate_positive_int_fields(
    row: dict[str, Any],
    *,
    fields: list[str],
    label: str,
    failures: list[str],
    require_all: bool,
) -> None:
    for field in fields:
        if field not in row or str(row.get(field) if row.get(field) is not None else "").strip() == "":
            if require_all:
                failures.append(f"{label} is missing {field}")
            continue
        if _safe_int(row.get(field)) <= 0:
            failures.append(f"{label} {field} must be positive")


def _validate_nonnegative_int_fields(
    row: dict[str, Any],
    *,
    fields: list[str],
    label: str,
    failures: list[str],
    require_all: bool,
) -> None:
    for field in fields:
        if field not in row or str(row.get(field) if row.get(field) is not None else "").strip() == "":
            if require_all:
                failures.append(f"{label} is missing {field}")
            continue
        if _safe_int(row.get(field), fallback=-1) < 0:
            failures.append(f"{label} {field} must be nonnegative")


def _validate_phone_response_topup_artifacts(
    *,
    completion: dict[str, Any] | None,
    response_ledger_rows: list[dict[str, Any]],
    topup_plan: dict[str, Any] | None,
    topup_materialization: dict[str, Any] | None,
    topup_wav_hashes: dict[str, str],
    failures: list[str],
    warnings: list[str],
    expect_phone_topup_evidence: bool,
) -> None:
    embedded_summary = (
        completion.get("phone_response_summary")
        if isinstance(completion, dict) and isinstance(completion.get("phone_response_summary"), dict)
        else None
    )
    embedded_ledger = [
        row
        for row in list((completion or {}).get("phone_response_ledger") or [])
        if isinstance(row, dict)
    ]
    embedded_plan = (
        completion.get("phone_topup_plan")
        if isinstance(completion, dict) and isinstance(completion.get("phone_topup_plan"), dict)
        else None
    )
    embedded_materialization = (
        completion.get("phone_topup_materialization")
        if isinstance(completion, dict) and isinstance(completion.get("phone_topup_materialization"), dict)
        else None
    )

    rows = response_ledger_rows or embedded_ledger
    plan = topup_plan or embedded_plan
    materialization = topup_materialization or embedded_materialization
    has_any_artifact = bool(rows or embedded_summary or plan or materialization)
    if not has_any_artifact:
        if expect_phone_topup_evidence:
            failures.append("phone response/top-up validation requires response ledger, top-up plan, and top-up materialization artifacts")
        elif completion and isinstance(completion.get("events"), list):
            warnings.append("phone run completion does not include response/top-up reconstruction artifacts")
        return

    if response_ledger_rows and embedded_ledger:
        file_signature = [_response_ledger_signature(row) for row in response_ledger_rows]
        embedded_signature = [_response_ledger_signature(row) for row in embedded_ledger]
        if file_signature != embedded_signature:
            failures.append("phone_response_ledger.csv rows differ from completion.json embedded phone_response_ledger")
    elif embedded_ledger and not response_ledger_rows:
        warnings.append("completion embeds phone_response_ledger but phone_response_ledger.csv sidecar is missing")

    if topup_plan and embedded_plan:
        _compare_metadata_fields(
            topup_plan,
            embedded_plan,
            fields=[
                "schema",
                "status",
                "synthesis_strategy",
                "response_min_rt_ms",
                "response_max_rt_ms",
                "missed_trial_count",
                "topup_trial_count",
                "topup_attempted_count",
                "topup_hit_count",
                "final_unresolved_miss_count",
            ],
            label="phone_topup_plan sidecar",
            other_label="completion phone_topup_plan",
            failures=failures,
        )
        if [_topup_plan_trial_signature(row) for row in list(topup_plan.get("trials") or []) if isinstance(row, dict)] != [
            _topup_plan_trial_signature(row) for row in list(embedded_plan.get("trials") or []) if isinstance(row, dict)
        ]:
            failures.append("phone_topup_plan.json trials differ from completion.json embedded phone_topup_plan")
    elif embedded_plan and not topup_plan:
        warnings.append("completion embeds phone_topup_plan but phone_topup_plan.json sidecar is missing")

    if topup_materialization and embedded_materialization:
        _compare_metadata_fields(
            topup_materialization,
            embedded_materialization,
            fields=[
                "schema",
                "status",
                "synthesis_strategy",
                "reason",
                "wav_filename",
                "wav_sha256",
                "sample_rate_hz",
                "channel_count",
                "bits_per_sample",
                "frame_count",
                "trial_count",
                "tactile_cue_count",
            ],
            label="phone_topup_materialization sidecar",
            other_label="completion phone_topup_materialization",
            failures=failures,
        )
    elif embedded_materialization and not topup_materialization:
        warnings.append("completion embeds phone_topup_materialization but phone_topup_materialization.json sidecar is missing")

    if expect_phone_topup_evidence:
        if embedded_summary is None:
            failures.append("strict phone response/top-up validation requires completion phone_response_summary")
        if not rows:
            failures.append("strict phone response/top-up validation requires phone_response_ledger rows")
        if plan is None:
            failures.append("strict phone response/top-up validation requires phone_topup_plan")
        if materialization is None:
            failures.append("strict phone response/top-up validation requires phone_topup_materialization")

    ledger_stats = _validate_phone_response_ledger(rows, failures) if rows else _empty_response_ledger_stats()
    if embedded_summary is not None:
        _validate_phone_response_summary(embedded_summary, ledger_stats, failures)
    if plan is not None:
        _validate_phone_topup_plan(plan, ledger_stats, failures)
    if materialization is not None:
        _validate_phone_topup_materialization(
            materialization,
            topup_plan=plan,
            topup_wav_hashes=topup_wav_hashes,
            completion=completion,
            failures=failures,
        )


def _validate_phone_owned_data_export(
    *,
    export: dict[str, Any] | None,
    data_min_header: list[str],
    data_min_rows: list[dict[str, Any]],
    data_min_master_header: list[str],
    data_min_master_rows: list[dict[str, Any]],
    data_max_has_completion: bool,
    completion: dict[str, Any] | None,
    response_ledger_rows: list[dict[str, Any]],
    failures: list[str],
    warnings: list[str],
    expect_phone_owned_data_export: bool,
) -> None:
    if export is None:
        message = "phone-owned data export is missing"
        if expect_phone_owned_data_export:
            failures.append(message)
        elif completion:
            warnings.append(f"{message}; rerun with --expect-phone-owned-data-export for strict checks")
        return
    if export.get("schema") != ANDROID_PHONE_OWNED_DATA_EXPORT_SCHEMA:
        failures.append("phone-owned data export schema mismatch")
    privacy = export.get("privacy") if isinstance(export.get("privacy"), dict) else {}
    if privacy.get("demographics_in_stream_name") is not False:
        failures.append("phone-owned data export must keep demographics out of stream names")
    if privacy.get("participant_names_exported") is not False:
        failures.append("phone-owned data export must not export participant names")
    fieldnames = export.get("data_min_fieldnames") if isinstance(export.get("data_min_fieldnames"), list) else []
    if fieldnames and [str(item) for item in fieldnames] != PHONE_DATA_MIN_FIELDNAMES:
        failures.append("phone-owned data export data_min_fieldnames differ from the 17-column PC runner schema")
    if data_min_header and data_min_header != PHONE_DATA_MIN_FIELDNAMES:
        failures.append("phone-owned 1.Data_min participant CSV header differs from the 17-column PC runner schema")
    elif expect_phone_owned_data_export and not data_min_header:
        failures.append("strict phone-owned data export requires a 1.Data_min participant CSV")
    if data_min_master_header and data_min_master_header != PHONE_DATA_MIN_FIELDNAMES:
        failures.append("phone-owned master_successful_participants.csv header differs from the 17-column PC runner schema")
    elif expect_phone_owned_data_export and not data_min_master_header:
        failures.append("strict phone-owned data export requires master_successful_participants.csv")
    if expect_phone_owned_data_export and not data_min_rows:
        failures.append("strict phone-owned data export requires at least one 1.Data_min participant row")
    exported_count = _clean_int(export.get("data_min_row_count"))
    if exported_count and data_min_rows and exported_count != len(data_min_rows):
        failures.append(f"phone-owned data export data_min_row_count expected {len(data_min_rows)}, got {exported_count}")
    if response_ledger_rows and data_min_rows and len(data_min_rows) != len(response_ledger_rows):
        failures.append("phone-owned 1.Data_min row count differs from phone_response_ledger row count")
    if data_min_rows:
        for index, row in enumerate(data_min_rows, start=1):
            prefix = f"phone-owned 1.Data_min row {index}"
            missing = [field for field in PHONE_DATA_MIN_FIELDNAMES if field not in row]
            if missing:
                failures.append(f"{prefix} is missing fields: {', '.join(missing)}")
            if str(row.get("response_given") or "").lower() not in {"true", "false"}:
                failures.append(f"{prefix} response_given must be true or false")
            if str(row.get("hit_miss") or "") not in {"Hit", "Miss"}:
                failures.append(f"{prefix} hit_miss must be Hit or Miss")
            if not str(row.get("trial_uid") or "").strip():
                failures.append(f"{prefix} is missing trial_uid")
    if data_min_rows and data_min_master_rows:
        missing_in_master = {
            str(row.get("trial_uid") or "")
            for row in data_min_rows
            if str(row.get("trial_uid") or "")
        } - {
            str(row.get("trial_uid") or "")
            for row in data_min_master_rows
            if str(row.get("trial_uid") or "")
        }
        if missing_in_master:
            failures.append(f"phone-owned master CSV is missing participant trial_uids: {sorted(missing_in_master)}")
    if expect_phone_owned_data_export and not data_max_has_completion:
        failures.append("strict phone-owned data export requires a 2.Data_max run-folder completion copy")


def _empty_response_ledger_stats() -> dict[str, int]:
    return {
        "ledger_row_count": 0,
        "eligible_trial_count": 0,
        "hit_count": 0,
        "missed_count": 0,
        "topup_rescue_count": 0,
        "topup_attempted_count": 0,
        "topup_hit_count": 0,
        "topup_miss_count": 0,
        "final_unresolved_miss_count": 0,
    }


def _validate_phone_response_ledger(rows: list[dict[str, Any]], failures: list[str]) -> dict[str, int]:
    source_rows = 0
    source_hits = 0
    source_misses = 0
    topup_eligible = 0
    topup_rows = 0
    topup_hits = 0
    seen_keys: set[tuple[str, str, str]] = set()
    for index, row in enumerate(rows, start=1):
        prefix = f"phone response ledger row {index}"
        if row.get("schema") != ANDROID_PHONE_RESPONSE_LEDGER_SCHEMA:
            failures.append(f"{prefix} schema mismatch")
        role = str(row.get("ledger_role") or "")
        if role not in {"source_trial", "topup_rescue"}:
            failures.append(f"{prefix} ledger_role must be source_trial or topup_rescue")
        trial_uid = str(row.get("trial_uid") or "")
        source_trial_uid = str(row.get("source_trial_uid") or "")
        if role == "source_trial" and not trial_uid:
            failures.append(f"{prefix} source_trial is missing trial_uid")
        if role == "topup_rescue" and (not trial_uid or not source_trial_uid):
            failures.append(f"{prefix} topup_rescue is missing trial_uid or source_trial_uid")
        key = (role, trial_uid, source_trial_uid)
        if key in seen_keys:
            failures.append(f"{prefix} duplicates another response ledger row")
        seen_keys.add(key)

        hit = _parse_boolish(row.get("hit"), f"{prefix} hit", failures)
        window_start = _safe_int(row.get("response_window_start_ms"))
        window_end = _safe_int(row.get("response_window_end_ms"))
        if window_start and window_end and window_end <= window_start:
            failures.append(f"{prefix} response window end must be after start")
        status = str(row.get("status") or "")
        if not status:
            failures.append(f"{prefix} is missing status")
        if role == "source_trial":
            source_rows += 1
            if not str(row.get("block_id") or ""):
                failures.append(f"{prefix} source_trial is missing block_id")
            if hit is True:
                source_hits += 1
                if status != "hit":
                    failures.append(f"{prefix} hit source_trial must use status='hit'")
                _validate_rt_field(row.get("rt_ms"), f"{prefix} rt_ms", failures)
            else:
                source_misses += 1
                if status not in {"missed_needs_topup", "missed_rescued_by_topup", "missed_topup_missed"}:
                    failures.append(f"{prefix} missed source_trial status is not recognized")
            if _parse_boolish(row.get("topup_eligible"), f"{prefix} topup_eligible", failures) is True:
                topup_eligible += 1
                if not str(row.get("building_block_asset_id") or ""):
                    failures.append(f"{prefix} topup_eligible source trial is missing building_block_asset_id")
        elif role == "topup_rescue":
            topup_rows += 1
            if not str(row.get("building_block_asset_id") or ""):
                failures.append(f"{prefix} topup_rescue is missing building_block_asset_id")
            if status not in {"topup_hit", "topup_miss"}:
                failures.append(f"{prefix} topup_rescue status is not recognized")
            if hit is True:
                topup_hits += 1
                _validate_rt_field(row.get("rt_ms"), f"{prefix} rt_ms", failures)
            elif hit is False and status == "topup_hit":
                failures.append(f"{prefix} status topup_hit requires hit=true")
    topup_misses = topup_rows - topup_hits
    return {
        "ledger_row_count": len(rows),
        "eligible_trial_count": source_rows,
        "hit_count": source_hits,
        "missed_count": source_misses,
        "topup_rescue_count": topup_eligible,
        "topup_attempted_count": topup_rows,
        "topup_hit_count": topup_hits,
        "topup_miss_count": topup_misses,
        "final_unresolved_miss_count": max(source_misses - topup_hits, 0),
    }


def _validate_phone_response_summary(summary: dict[str, Any], stats: dict[str, int], failures: list[str]) -> None:
    if summary.get("schema") != ANDROID_PHONE_RESPONSE_SUMMARY_SCHEMA:
        failures.append("phone_response_summary schema mismatch")
    if summary.get("response_policy") != PHONE_RESPONSE_POLICY:
        failures.append("phone_response_summary response_policy mismatch")
    for field in (
        "eligible_trial_count",
        "ledger_row_count",
        "hit_count",
        "topup_rescue_count",
        "topup_attempted_count",
        "topup_hit_count",
        "topup_miss_count",
        "final_rescued_hit_count",
        "final_unresolved_miss_count",
    ):
        expected = stats["topup_hit_count"] if field == "final_rescued_hit_count" else stats.get(field)
        if expected is None:
            continue
        observed = _safe_int(summary.get(field))
        if observed != expected:
            failures.append(f"phone_response_summary {field} expected {expected}, got {observed}")
    missed = _safe_int(summary.get("missed_needs_topup_count"))
    if missed != stats["missed_count"]:
        failures.append(f"phone_response_summary missed_needs_topup_count expected {stats['missed_count']}, got {missed}")


def _validate_phone_topup_plan(plan: dict[str, Any], stats: dict[str, int], failures: list[str]) -> None:
    if plan.get("schema") != ANDROID_PHONE_TOPUP_PLAN_SCHEMA:
        failures.append("phone_topup_plan schema mismatch")
    status = str(plan.get("status") or "")
    if status not in PHONE_TOPUP_PLAN_STATUSES:
        failures.append("phone_topup_plan status is not recognized")
    if plan.get("synthesis_strategy") != PHONE_TOPUP_SYNTHESIS_STRATEGY:
        failures.append("phone_topup_plan synthesis_strategy must be pcm_wav_concat_without_ffmpeg")
    if _safe_int(plan.get("response_min_rt_ms")) != PHONE_RESPONSE_MIN_RT_MS:
        failures.append("phone_topup_plan response_min_rt_ms mismatch")
    if _safe_int(plan.get("response_max_rt_ms")) != PHONE_RESPONSE_MAX_RT_MS:
        failures.append("phone_topup_plan response_max_rt_ms mismatch")
    trials = [row for row in list(plan.get("trials") or []) if isinstance(row, dict)]
    if _safe_int(plan.get("topup_trial_count")) != len(trials):
        failures.append("phone_topup_plan topup_trial_count differs from trials length")
    if stats["eligible_trial_count"]:
        expected = {
            "missed_trial_count": stats["missed_count"],
            "topup_trial_count": stats["topup_rescue_count"],
            "topup_attempted_count": stats["topup_attempted_count"],
            "topup_hit_count": stats["topup_hit_count"],
            "final_unresolved_miss_count": stats["final_unresolved_miss_count"],
        }
        for field, value in expected.items():
            if _safe_int(plan.get(field)) != value:
                failures.append(f"phone_topup_plan {field} expected {value}, got {_safe_int(plan.get(field))}")
    seen_source_trials: set[str] = set()
    for index, row in enumerate(trials, start=1):
        prefix = f"phone_topup_plan trial {index}"
        if str(row.get("topup_role") or "") != "rescue":
            failures.append(f"{prefix} topup_role must be rescue")
        for field in ("source_block_id", "source_trial_uid", "building_block_asset_id"):
            if not str(row.get(field) or ""):
                failures.append(f"{prefix} is missing {field}")
        source_trial_uid = str(row.get("source_trial_uid") or "")
        if source_trial_uid in seen_source_trials:
            failures.append(f"{prefix} duplicates source_trial_uid {source_trial_uid!r}")
        seen_source_trials.add(source_trial_uid)
    if status == "not_needed" and trials:
        failures.append("phone_topup_plan status not_needed must not include rescue trials")
    if status in {"played", "materialized_not_played", "planned_not_played"} and not trials:
        failures.append(f"phone_topup_plan status {status} requires at least one rescue trial")


def _validate_phone_topup_materialization(
    materialization: dict[str, Any],
    *,
    topup_plan: dict[str, Any] | None,
    topup_wav_hashes: dict[str, str],
    completion: dict[str, Any] | None,
    failures: list[str],
) -> None:
    if materialization.get("schema") != ANDROID_PHONE_TOPUP_MATERIALIZATION_SCHEMA:
        failures.append("phone_topup_materialization schema mismatch")
    status = str(materialization.get("status") or "")
    if status not in PHONE_TOPUP_MATERIALIZATION_STATUSES:
        failures.append("phone_topup_materialization status is not recognized")
    if materialization.get("synthesis_strategy") != PHONE_TOPUP_SYNTHESIS_STRATEGY:
        failures.append("phone_topup_materialization synthesis_strategy must be pcm_wav_concat_without_ffmpeg")
    if status in {"failed", "skipped"} and not str(materialization.get("reason") or ""):
        failures.append(f"phone_topup_materialization status {status} requires a reason")

    events = [event for event in list((completion or {}).get("events") or []) if isinstance(event, dict)]
    latest_event = [event for event in events if event.get("type") == "phone_topup_materialization"]
    if latest_event:
        event = latest_event[-1]
        for field in ("schema", "status", "synthesis_strategy", "wav_filename", "wav_sha256", "trial_count", "tactile_cue_count"):
            event_value = str(event.get(field) or "")
            materialization_value = str(materialization.get(field) or "")
            if event_value and materialization_value and event_value != materialization_value:
                failures.append(f"phone_topup_materialization {field} differs from phone_topup_materialization event")

    plan_status = str((topup_plan or {}).get("status") or "")
    plan_trial_count = _safe_int((topup_plan or {}).get("topup_trial_count"))
    if plan_status == "played" and status != "materialized":
        failures.append("phone_topup_plan status played requires materialized phone_topup_materialization")
    if plan_status == "materialized_not_played" and status != "materialized":
        failures.append("phone_topup_plan status materialized_not_played requires materialized phone_topup_materialization")
    if plan_status == "failed" and status != "failed":
        failures.append("phone_topup_plan status failed requires failed phone_topup_materialization")
    if plan_status == "skipped" and status != "skipped":
        failures.append("phone_topup_plan status skipped requires skipped phone_topup_materialization")
    if plan_status == "not_needed" and status not in {"not_needed", "not_evaluated"}:
        failures.append("phone_topup_plan status not_needed requires not_needed phone_topup_materialization")
    if plan_status == "played" and events:
        has_topup_block_complete = any(
            event.get("type") == "block_complete" and event.get("block_id") == "phone-topup-01"
            for event in events
        )
        if not has_topup_block_complete:
            failures.append("phone_topup_plan status played requires a phone-topup-01 block_complete event")

    if status != "materialized":
        return
    wav_filename = str(materialization.get("wav_filename") or "")
    wav_sha256 = str(materialization.get("wav_sha256") or "")
    if not wav_filename:
        failures.append("phone_topup_materialization materialized status is missing wav_filename")
    if not wav_sha256:
        failures.append("phone_topup_materialization materialized status is missing wav_sha256")
    observed_hash = topup_wav_hashes.get(wav_filename)
    if wav_filename and not observed_hash:
        failures.append(f"phone_topup_materialization referenced WAV {wav_filename!r} is missing")
    elif observed_hash and observed_hash != wav_sha256:
        failures.append(f"phone_topup_materialization wav_sha256 does not match {wav_filename!r}")
    for field in ("sample_rate_hz", "channel_count", "bits_per_sample", "frame_count", "duration_ms", "trial_count"):
        if _safe_int(materialization.get(field)) <= 0:
            failures.append(f"phone_topup_materialization materialized status requires positive {field}")
    trials = [row for row in list(materialization.get("trials") or []) if isinstance(row, dict)]
    if _safe_int(materialization.get("trial_count")) != len(trials):
        failures.append("phone_topup_materialization trial_count differs from trials length")
    if plan_trial_count and _safe_int(materialization.get("trial_count")) != plan_trial_count:
        failures.append("phone_topup_materialization trial_count differs from phone_topup_plan")
    for index, row in enumerate(trials, start=1):
        prefix = f"phone_topup_materialization trial {index}"
        for field in ("source_trial_uid", "topup_trial_uid", "building_block_asset_id", "topup_start_s", "topup_end_s", "topup_duration_s"):
            if field not in row or row.get(field) is None or str(row.get(field)).strip() == "":
                failures.append(f"{prefix} is missing {field}")


def _validate_rt_field(value: Any, label: str, failures: list[str]) -> None:
    rt_ms = _safe_int(value)
    if not (PHONE_RESPONSE_MIN_RT_MS <= rt_ms <= PHONE_RESPONSE_MAX_RT_MS):
        failures.append(f"{label} must be within {PHONE_RESPONSE_MIN_RT_MS}-{PHONE_RESPONSE_MAX_RT_MS} ms")


def _parse_boolish(value: Any, label: str, failures: list[str]) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    if text in {"", "null", "none"}:
        failures.append(f"{label} must be a boolean")
        return None
    failures.append(f"{label} must be a boolean")
    return None


def _response_ledger_signature(row: dict[str, Any]) -> tuple[str, ...]:
    fields = (
        "schema",
        "ledger_role",
        "source_trial_uid",
        "trial_uid",
        "block_id",
        "trial_number",
        "status",
        "hit",
        "rt_ms",
        "topup_trial_uid",
        "topup_hit",
        "topup_rt_ms",
        "building_block_asset_id",
    )
    return tuple(_normalized_artifact_value(row.get(field)) for field in fields)


def _topup_plan_trial_signature(row: dict[str, Any]) -> tuple[str, ...]:
    fields = (
        "topup_role",
        "source_block_id",
        "source_block_index",
        "source_trial_uid",
        "source_trial_number",
        "building_block_asset_id",
        "trial_type",
        "family",
        "soa_ms",
        "row_label",
        "noise_type",
        "duration_s",
        "tactile_onset_s",
        "response_window_onset_s",
    )
    return tuple(_normalized_artifact_value(row.get(field)) for field in fields)


def _normalized_artifact_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    if text.lower() in {"true", "false"}:
        return text.lower()
    return text


def _validate_lightweight_materializations(
    *,
    completion: dict[str, Any] | None,
    package_manifest: dict[str, Any] | None,
    materialization_manifests: list[dict[str, Any]],
    materialized_wav_hashes: dict[str, str],
    failures: list[str],
    warnings: list[str],
    expect_lightweight_materializations: bool,
) -> None:
    if not package_manifest:
        if expect_lightweight_materializations:
            failures.append("lightweight materialization validation requires run_package_manifest.json")
        return

    reconstruction = package_manifest.get("reconstruction") if isinstance(package_manifest.get("reconstruction"), dict) else {}
    strategy = str(package_manifest.get("asset_strategy") or reconstruction.get("package_asset_strategy") or "")
    assets = [asset for asset in list(package_manifest.get("assets") or []) if isinstance(asset, dict)]
    block_audio_assets = [asset for asset in assets if str(asset.get("role") or "") == "block_audio"]
    is_lightweight = strategy == "trial_building_blocks_only"
    if not is_lightweight:
        if expect_lightweight_materializations:
            failures.append("run package is not marked asset_strategy='trial_building_blocks_only'")
        return
    if block_audio_assets:
        failures.append("lightweight run package still contains block_audio assets")
    if not expect_lightweight_materializations:
        warnings.append("lightweight phone package detected; rerun with --expect-lightweight-materializations for strict checks")
        return

    blocks = [block for block in list(package_manifest.get("blocks") or []) if isinstance(block, dict)]
    if not blocks:
        failures.append("lightweight run package has no scheduled blocks")
        return
    events = [event for event in list((completion or {}).get("events") or []) if isinstance(event, dict)]
    if not events:
        failures.append("lightweight materialization validation requires completion events")
        return

    materialization_events = [event for event in events if event.get("type") == "phone_scheduled_block_materialization"]
    event_by_block = _unique_by_source_block_id(materialization_events, label="phone_scheduled_block_materialization event", failures=failures)
    manifest_by_block = _unique_by_source_block_id(materialization_manifests, label="scheduled-block materialization manifest", failures=failures)

    for block in blocks:
        block_id = str(block.get("block_id") or "")
        if not block_id:
            failures.append("lightweight run package block is missing block_id")
            continue
        expected_trial_count = _safe_int(block.get("trial_count"), fallback=len(list(block.get("trials") or [])))
        expected_index = _safe_int(block.get("index"))
        event = event_by_block.get(block_id)
        if event is None:
            failures.append(f"block {block_id} is missing phone_scheduled_block_materialization event")
        else:
            _validate_scheduled_block_materialization_record(
                event,
                label=f"block {block_id} materialization event",
                expected_block_id=block_id,
                expected_block_index=expected_index,
                expected_trial_count=expected_trial_count,
                materialized_wav_hashes=materialized_wav_hashes,
                failures=failures,
            )
        manifest = manifest_by_block.get(block_id)
        if manifest is None:
            failures.append(f"block {block_id} is missing materialized_blocks JSON manifest")
        else:
            _validate_scheduled_block_materialization_record(
                manifest,
                label=f"block {block_id} materialized_blocks manifest",
                expected_block_id=block_id,
                expected_block_index=expected_index,
                expected_trial_count=expected_trial_count,
                materialized_wav_hashes=materialized_wav_hashes,
                failures=failures,
            )
            if event is not None:
                for key in ("wav_filename", "wav_sha256", "trial_count", "tactile_cue_count"):
                    if str(event.get(key) or "") != str(manifest.get(key) or ""):
                        failures.append(f"block {block_id} materialization event {key} differs from materialized_blocks manifest")


def _unique_by_source_block_id(rows: list[dict[str, Any]], *, label: str, failures: list[str]) -> dict[str, dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        block_id = str(row.get("source_block_id") or "")
        if not block_id:
            failures.append(f"{label} is missing source_block_id")
            continue
        if block_id in by_id:
            failures.append(f"duplicate {label} for source_block_id {block_id!r}")
            continue
        by_id[block_id] = row
    return by_id


def _validate_scheduled_block_materialization_record(
    record: dict[str, Any],
    *,
    label: str,
    expected_block_id: str,
    expected_block_index: int,
    expected_trial_count: int,
    materialized_wav_hashes: dict[str, str],
    failures: list[str],
) -> None:
    if record.get("schema") != ANDROID_SCHEDULED_BLOCK_MATERIALIZATION_SCHEMA:
        failures.append(f"{label} schema mismatch")
    if record.get("status") != "materialized":
        failures.append(f"{label} status must be materialized")
    if record.get("synthesis_strategy") != "pcm_wav_concat_without_ffmpeg":
        failures.append(f"{label} synthesis_strategy must be pcm_wav_concat_without_ffmpeg")
    if str(record.get("source_block_id") or "") != expected_block_id:
        failures.append(f"{label} source_block_id differs from run package")
    observed_index = _safe_int(record.get("source_block_index"))
    if expected_block_index and observed_index and observed_index != expected_block_index:
        failures.append(f"{label} source_block_index differs from run package")
    observed_trial_count = _safe_int(record.get("trial_count"))
    if observed_trial_count != expected_trial_count:
        failures.append(f"{label} trial_count differs from run package")
    wav_filename = str(record.get("wav_filename") or "")
    wav_sha256 = str(record.get("wav_sha256") or "")
    if not wav_filename:
        failures.append(f"{label} is missing wav_filename")
        return
    if not wav_sha256:
        failures.append(f"{label} is missing wav_sha256")
        return
    observed_hash = materialized_wav_hashes.get(wav_filename)
    if not observed_hash:
        failures.append(f"{label} referenced materialized WAV {wav_filename!r} is missing")
    elif observed_hash != wav_sha256:
        failures.append(f"{label} wav_sha256 does not match materialized WAV {wav_filename!r}")


def _safe_int(value: Any, *, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


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
    elif stream_key == "command_signals":
        if row.get("stream_name") != LSL_COMMAND_STREAM_NAME:
            failures.append(f"{prefix} command signal stream_name mismatch")
        if channel_labels != list(LSL_COMMAND_CHANNELS):
            failures.append(f"{prefix} command signal channel order mismatch")
        if len(sample) != len(LSL_COMMAND_CHANNELS):
            failures.append(f"{prefix} command signal sample channel count mismatch")
            return
        if sample[0] != COMMAND_SCHEMA:
            failures.append(f"{prefix} command signal schema mismatch")
        if row.get("command_id") and sample[1] != row.get("command_id"):
            failures.append(f"{prefix} command_id differs from command signal sample")
        if row.get("session_id") and sample[2] != row.get("session_id"):
            failures.append(f"{prefix} session_id differs from command signal sample")
        if row.get("sender_id") and sample[3] != row.get("sender_id"):
            failures.append(f"{prefix} sender_id differs from command signal sample")
        if row.get("command") and sample[4] != row.get("command"):
            failures.append(f"{prefix} command differs from command signal sample")
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
        help=(
            "For phone-run, controller, PC-admin, or monitor artifacts, fail unless matching "
            "command acknowledgement evidence is present."
        ),
    )
    parser.add_argument("--expect-run-catalog", action="store_true", help="For phone-run artifacts, fail unless phone_run_catalog_entry.json is present and consistent.")
    parser.add_argument(
        "--expect-run-catalog-index",
        action="store_true",
        help=(
            "For phone-run artifacts, fail unless the app-private phone_run_catalog index, "
            "participant runs.jsonl, and latest_run.json snapshot are present and consistent."
        ),
    )
    parser.add_argument(
        "--expect-event-diary",
        action="store_true",
        help="For phone-run artifacts, fail unless events.csv is present and matches completion/latest-events event rows.",
    )
    parser.add_argument(
        "--expect-trigger-code-mirror",
        action="store_true",
        help="For phone-run artifacts, fail unless trigger_codes.csv is present and matches the local PPSTriggerCodes sequence implied by lsl_marker_mirror.csv.",
    )
    parser.add_argument(
        "--expect-lightweight-materializations",
        action="store_true",
        help="For building-block-only phone runs, fail unless every scheduled block has materialization event/JSON/WAV evidence.",
    )
    parser.add_argument(
        "--expect-phone-topup-evidence",
        action="store_true",
        help=(
            "For phone-run artifacts, fail unless response ledger, top-up plan, "
            "top-up materialization JSON, and any materialized top-up WAV hash evidence are present and consistent."
        ),
    )
    parser.add_argument(
        "--expect-audiotrack-timing-evidence",
        action="store_true",
        help=(
            "For phone-run artifacts, fail unless block_start and vibration_cue events carry "
            "AudioTrack playback-head timing fields and coherent frame/jitter metadata."
        ),
    )
    parser.add_argument(
        "--expect-phone-owned-data-export",
        action="store_true",
        help=(
            "For phone-run artifacts, fail unless phone_owned_data_export.json, 1.Data_min participant/master CSVs, "
            "and a 2.Data_max run-folder completion copy are present and internally consistent."
        ),
    )
    parser.add_argument("--output-dir", type=Path, help="Optional directory for JSON/Markdown validation reports.")
    args = parser.parse_args(argv)

    result = validate_run_artifact(
        args.artifact,
        expect_native_transport=args.expect_native_transport,
        expect_command_acks=args.expect_command_acks,
        expect_run_catalog=args.expect_run_catalog,
        expect_run_catalog_index=args.expect_run_catalog_index,
        expect_event_diary=args.expect_event_diary,
        expect_trigger_code_mirror=args.expect_trigger_code_mirror,
        expect_lightweight_materializations=args.expect_lightweight_materializations,
        expect_phone_topup_evidence=args.expect_phone_topup_evidence,
        expect_audiotrack_timing_evidence=args.expect_audiotrack_timing_evidence,
        expect_phone_owned_data_export=args.expect_phone_owned_data_export,
    )
    if args.output_dir:
        _write_report(result, args.output_dir)
    print(json.dumps(result.to_json(), indent=2, sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
