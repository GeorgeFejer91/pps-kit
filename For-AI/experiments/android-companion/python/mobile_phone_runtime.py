"""Mobile phone runtime package export/import helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from .lsl_command_ack import (
    ACK_SCHEMA,
    COMMAND_SCHEMA,
    LSL_ACK_CHANNELS,
    LSL_ACK_STREAM_NAME,
    LSL_COMMAND_CHANNELS,
    LSL_COMMAND_STREAM_NAME,
)
from .output_layout import _filesystem_path, output_runner_logs_dir
from .timing_events import LSL_MARKER_CHANNELS, LSL_NUMERIC_STREAM_NAME, LSL_STREAM_NAME, MARKER_VERSION


MOBILE_PACKAGE_LIST_SCHEMA = "pps-mobile-run-package-list.v2"
MOBILE_PACKAGE_SCHEMA = "pps-mobile-run-package.v2"
MOBILE_PACKAGE_LIST_SCHEMA_V1 = "pps-mobile-run-package-list.v1"
MOBILE_PACKAGE_SCHEMA_V1 = "pps-mobile-run-package.v1"
MOBILE_RUN_EVENTS_SCHEMA = "pps-mobile-run-events.v1"
MOBILE_RUN_COMPLETE_SCHEMA = "pps-mobile-run-complete.v1"
MOBILE_RUNTIME_ARTIFACT_SCHEMA = "pps-mobile-runtime-artifact.v1"
MOBILE_RECONSTRUCTION_SCHEMA = "pps-mobile-reconstruction-contract.v1"
MOBILE_LSL_CONTRACT_SCHEMA = "pps-mobile-lsl-contract.v1"
MOBILE_SOURCE_SEGMENT_HASHES_SCHEMA = "pps-mobile-source-segment-hashes.v1"
MOBILE_PHONE_OWNED_DATA_EXPORT_SCHEMA = "pps-android-phone-owned-data-export.v1"
MOBILE_PHONE_RUN_RECONSTRUCTION_ARTIFACT_SCHEMA = "pps-mobile-phone-run-reconstruction.v1"
MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_SCHEMA = "pps-android-phone-run-artifact-file-inventory.v1"
MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_JSON = "artifact_file_inventory.json"
MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_CSV = "artifact_file_inventory.csv"
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
PHONE_RESPONSE_LEDGER_FIELDNAMES = [
    "schema",
    "ledger_role",
    "source_trial_uid",
    "source_trial_number",
    "trial_uid",
    "trial_number",
    "block_id",
    "block_index",
    "cue_id",
    "scheduled_block_time_ms",
    "response_window_start_ms",
    "response_window_end_ms",
    "status",
    "hit",
    "rt_ms",
    "tap_event_id",
    "building_block_asset_id",
    "topup_eligible",
    "topup_attempted",
    "topup_trial_uid",
    "topup_hit",
    "topup_rt_ms",
    "topup_tap_event_id",
]
PHONE_ARTIFACT_FILE_INVENTORY_FIELDNAMES = [
    "relative_path",
    "size_bytes",
    "sha256",
    "modified_unix_ms",
]
MOBILE_RUNTIME_LIMITATIONS = [
    "Phone runtime plays prepared PCM block WAVs locally through Android AudioTrack and records phone touch timestamps.",
    "Phone vibration is driven by Android vibrator timing and is not equivalent to the PC tactile audio output.",
    "Phone runtime writes a local LSL-compatible marker mirror; native Android LSL broadcast requires the optional liblsl Android layer.",
    "Phone runtime does not own LabRecorder, Woojer, or hardware loopback evidence.",
]
MOBILE_REQUIRED_STUDY_HIERARCHY = [
    "study_profile",
    "segment_1_audio_ingredients",
    "segment_2_trial_sequence_designs",
    "segment_3_tactile_baseline_catch_trials",
    "segment_4_trial_repetition_pool",
    "segment_5_block_csv_preview",
    "segment_6_participant_part_order",
    "phone_runtime_package",
    "phone_runtime_events",
]
MOBILE_REQUIRED_LSL_STREAM_NAMES = {
    "rich_markers": "PPSMarkersV2",
    "numeric_triggers": "PPSTriggerCodes",
    "command_signals": "PPSCommandSignalsV1",
    "command_acks": "PPSCommandAcksV1",
}
MOBILE_REQUIRED_PHONE_COMMAND_ORDER = [
    "start_experiment",
    "start_part",
    "pause",
    "resume",
    "continue_instruction",
    "stop_after_block",
    "request_snapshot",
    "operator_note",
]
MOBILE_REQUIRED_PHONE_COMMANDS = {
    *MOBILE_REQUIRED_PHONE_COMMAND_ORDER,
}


class MobileRuntimePackageError(RuntimeError):
    """Raised when a prepared runner package cannot be exported for phone runtime."""


@dataclass(frozen=True)
class MobilePackageValidationResult:
    ok: bool
    failures: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema": "pps-mobile-run-package-validation.v1",
            "ok": self.ok,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "summary": dict(self.summary),
        }


def mobile_package_id(package: Any) -> str:
    raw = (
        str(getattr(package, "part_session_id", "") or "").strip()
        or str(getattr(package, "session_id", "") or "").strip()
        or str(getattr(package, "participant_id", "") or "").strip()
        or "active-package"
    )
    part = getattr(package, "part_number", None)
    if part not in (None, "") and f"part{part}" not in raw.lower():
        raw = f"{raw}-part{part}"
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    return clean or "active-package"


def build_mobile_package_list(
    package: Any | Sequence[Any] | None,
    *,
    phone_owned_session: bool = False,
    include_block_audio: bool = True,
) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    active_id = ""
    for item in _coerce_packages(package):
        manifest = build_mobile_package_manifest(
            item,
            include_trials=not include_block_audio,
            include_sha256=False,
            phone_owned_session=phone_owned_session,
            include_block_audio=include_block_audio,
        )
        if not active_id:
            active_id = str(manifest.get("package_id") or "")
        packages.append(
            {
                "package_id": str(manifest.get("package_id") or ""),
                "participant_id": manifest.get("participant_id", ""),
                "session_id": manifest.get("session_id", ""),
                "session_group_id": manifest.get("session_group_id", ""),
                "part_number": manifest.get("part_number"),
                "part_session_id": manifest.get("part_session_id", ""),
                "title": manifest.get("title", ""),
                "asset_strategy": str(manifest.get("asset_strategy") or ""),
                "block_count": len(manifest.get("blocks") or []),
                "trial_count": sum(int(block.get("trial_count") or 0) for block in manifest.get("blocks") or []),
                "asset_count": len(manifest.get("assets") or []),
                "total_asset_bytes": sum(int(asset.get("size_bytes") or 0) for asset in manifest.get("assets") or []),
                "participant_roster_count": len(manifest.get("participant_roster") or []),
                "randomization_seed": str(manifest.get("randomization_seed") or ""),
                "mobile_runnable": bool(manifest.get("mobile_runnable")),
                "phone_owned_session": bool(manifest.get("phone_owned_session")),
                "warnings": list(manifest.get("warnings") or []),
                "runtime_limitations": list(MOBILE_RUNTIME_LIMITATIONS),
            }
        )
    return {
        "schema": MOBILE_PACKAGE_LIST_SCHEMA,
        "generated_at": _utc_now(),
        "active_package_id": active_id,
        "packages": packages,
    }


def _coerce_packages(package: Any | Sequence[Any] | None) -> list[Any]:
    if package is None:
        return []
    if isinstance(package, Sequence) and not isinstance(package, (str, bytes, bytearray)):
        return [item for item in package if item is not None]
    return [package]


def build_mobile_package_manifest(
    package: Any,
    *,
    include_trials: bool = True,
    include_sha256: bool = True,
    phone_owned_session: bool = False,
    include_block_audio: bool = True,
) -> dict[str, Any]:
    package_id = mobile_package_id(package)
    blocks_payload: list[dict[str, Any]] = []
    assets: list[dict[str, Any]] = []
    building_blocks_by_asset: dict[str, dict[str, Any]] = {}
    schedule_blocks: list[dict[str, Any]] = []
    warnings: list[str] = []
    tactile_cue_count = 0
    for block in list(getattr(package, "blocks", []) or []):
        wav_path = Path(getattr(block, "wav_path", "") or "")
        block_audio_asset_id = f"block-{int(getattr(block, 'index', len(blocks_payload) + 1)):02d}-audio"
        if include_block_audio:
            asset = _asset_payload(block_audio_asset_id, wav_path, include_sha256=include_sha256)
            if not bool(asset.get("available")):
                warnings.append(f"Missing audio asset for block {getattr(block, 'index', '?')}: {wav_path}")
            assets.append(asset)

        trials, cues = _block_trial_payloads(block) if include_trials else ([], [])
        for trial in trials:
            trial_asset_id, building_block = _building_block_from_trial(trial)
            if trial_asset_id and building_block:
                building_blocks_by_asset.setdefault(trial_asset_id, building_block)
        tactile_cue_count += len(cues)
        block_payload = {
            "block_id": f"block-{int(getattr(block, 'index', len(blocks_payload) + 1)):02d}",
            "index": int(getattr(block, "index", len(blocks_payload) + 1) or len(blocks_payload) + 1),
            "label": str(getattr(block, "label", "") or f"Block {len(blocks_payload) + 1:02d}"),
            "duration_s": _float(getattr(block, "duration_s", 0.0)),
            "trial_count": int(getattr(block, "trial_count", 0) or len(trials)),
            "audio_asset_id": block_audio_asset_id,
            "manifest_filename": Path(getattr(block, "manifest_path", "") or "").name,
            "trials": trials,
            "tactile_cues": cues,
            "metadata": dict(getattr(block, "metadata", {}) or {}),
        }
        blocks_payload.append(block_payload)
        schedule_blocks.append(
            {
                "block_id": block_payload["block_id"],
                "index": block_payload["index"],
                "label": block_payload["label"],
                "duration_s": block_payload["duration_s"],
                "trial_count": block_payload["trial_count"],
                "compatibility_audio_asset_id": block_audio_asset_id,
                "trial_uids": [trial.get("trial_uid", "") for trial in trials],
                "building_block_asset_ids": [trial.get("building_block_asset_id", "") for trial in trials],
                "tactile_cue_count": len(cues),
                "source_block_csv_path": str((getattr(block, "metadata", {}) or {}).get("source_block_csv_path", "")),
                "source_block_csv_sha256": str((getattr(block, "metadata", {}) or {}).get("source_block_csv_sha256", "")),
            }
        )

    if not blocks_payload:
        warnings.append("No prepared block WAVs are available for phone runtime.")
    if include_trials and tactile_cue_count <= 0:
        warnings.append("No phone-vibration tactile cues were found in the block manifests.")

    building_blocks = list(building_blocks_by_asset.values())
    known_asset_ids = {str(asset.get("asset_id") or "") for asset in assets}
    for building_block in building_blocks:
        asset_id = str(building_block.get("asset_id") or "")
        if asset_id and asset_id not in known_asset_ids:
            assets.append(
                {
                    "asset_id": asset_id,
                    "filename": str(building_block.get("filename") or ""),
                    "media_type": str(building_block.get("media_type") or "audio/wav"),
                    "role": "trial_building_block",
                    "size_bytes": int(building_block.get("size_bytes") or 0),
                    "sha256": str(building_block.get("sha256") or ""),
                    "available": bool(building_block.get("available")),
                }
            )
            known_asset_ids.add(asset_id)
    asset_by_id_for_runnable = {str(asset.get("asset_id") or ""): asset for asset in assets}
    lightweight_materializable = _all_blocks_reference_available_building_blocks(
        blocks_payload,
        building_blocks,
        asset_by_id_for_runnable,
    )
    if not include_block_audio and blocks_payload and not lightweight_materializable:
        warnings.append("Lightweight package cannot materialize every scheduled block from trial_building_block assets.")
    source_run_setup = getattr(package, "source_run_setup_manifest_path", None)
    source_run_setup_sha256 = _sha256(Path(source_run_setup)) if source_run_setup and Path(source_run_setup).is_file() else ""
    provenance = _mobile_source_provenance(
        package,
        schedule_blocks=schedule_blocks,
        source_run_setup_sha256=source_run_setup_sha256,
    )
    session_group_id = str(getattr(package, "session_group_id", "") or "")
    part_session_id = str(getattr(package, "part_session_id", "") or getattr(package, "session_id", "") or "")
    part_number = getattr(package, "part_number", None)
    asset_strategy = "prepared_block_wavs_plus_trial_building_blocks" if include_block_audio else "trial_building_blocks_only"
    reconstruction = {
        "schema": MOBILE_RECONSTRUCTION_SCHEMA,
        "authority": "android_phone",
        "fallback_execution_strategy": "prepared_block_wavs",
        "preferred_lightweight_strategy": "replay_schedule_from_trial_building_blocks",
        "package_asset_strategy": asset_strategy,
        "study_hierarchy": [
            "study_profile",
            "segment_1_audio_ingredients",
            "segment_2_trial_sequence_designs",
            "segment_3_tactile_baseline_catch_trials",
            "segment_4_trial_repetition_pool",
            "segment_5_block_csv_preview",
            "segment_6_participant_part_order",
            "phone_runtime_package",
            "phone_runtime_events",
        ],
        "source_run_setup_manifest_path": str(source_run_setup or ""),
        "source_run_setup_sha256": source_run_setup_sha256,
        "session_group_id": session_group_id,
        "part_session_id": part_session_id,
        "part_number": part_number,
        "participant_id": str(getattr(package, "participant_id", "") or ""),
        "schedule_hash": _json_sha256(schedule_blocks),
        "building_block_count": len(building_blocks),
        "block_count": len(blocks_payload),
        "trial_count": sum(int(block.get("trial_count") or 0) for block in blocks_payload),
        "notes": [
            (
                "Block WAV assets remain available for current Android playback compatibility."
                if include_block_audio
                else "Prepared block WAV assets are omitted; Android must materialize scheduled blocks from reusable trial WAVs."
            ),
            "Building-block records identify reusable Segment 3 trial WAVs when source block CSVs expose Trial_File_Path.",
        ],
    }
    lsl_contract = {
        "schema": MOBILE_LSL_CONTRACT_SCHEMA,
        "runtime_authority": "android_phone",
        "privacy_default": "metadata_payload_only",
        "stream_names": {
            "rich_markers": "PPSMarkersV2",
            "numeric_triggers": "PPSTriggerCodes",
            "command_signals": "PPSCommandSignalsV1",
            "command_acks": "PPSCommandAcksV1",
        },
        "source_id_prefixes": {
            "rich_markers": "pps-android-markers-v2",
            "numeric_triggers": "pps-android-trigger-codes",
            "command_signals": "pps-android-command-signals-v1",
            "command_acks": "pps-android-command-acks-v1",
        },
        "session_metadata_policy": "Emit one session_metadata marker before run_start and mirror every marker to local CSV/JSON.",
        "command_policy": "Commands must carry the pairing token and receive an applied/rejected acknowledgement after local state transition.",
        "supported_commands": list(MOBILE_REQUIRED_PHONE_COMMAND_ORDER),
        "native_android_lsl_required": True,
        "current_android_source_behavior": "local_lsl_marker_mirror",
    }
    return {
        "schema": MOBILE_PACKAGE_SCHEMA,
        "legacy_schemas": [MOBILE_PACKAGE_SCHEMA_V1],
        "package_id": package_id,
        "generated_at": _utc_now(),
        "title": _package_title(package),
        "participant_id": str(getattr(package, "participant_id", "") or ""),
        "session_id": str(getattr(package, "session_id", "") or ""),
        "session_group_id": str(getattr(package, "session_group_id", "") or ""),
        "part_number": getattr(package, "part_number", None),
        "part_session_id": str(getattr(package, "part_session_id", "") or ""),
        "execution_mode": str(getattr(package, "execution_mode", "") or ""),
        "manifest_path": str(getattr(package, "manifest_path", "") or ""),
        "design_path": str(getattr(package, "design_path", "") or ""),
        "blocks": blocks_payload,
        "assets": assets,
        "building_blocks": building_blocks,
        "asset_strategy": asset_strategy,
        "participant_roster": provenance["participant_roster"],
        "randomization_seed": provenance["randomization_seed"],
        "source_segment_hashes": provenance["source_segment_hashes"],
        "schedule": {
            "blocks": schedule_blocks,
            "execution_order": [block["block_id"] for block in schedule_blocks],
            "row_order_preserved": True,
        },
        "reconstruction": reconstruction,
        "lsl": lsl_contract,
        "participant_fields": {
            "participant_id": str(getattr(package, "participant_id", "") or ""),
            "age_years": "",
            "handedness": "",
            "gender": "",
            "tactile_threshold_value": "",
            "name_sharing_opt_in": False,
        },
        "mobile_runnable": bool(
            blocks_payload
            and all(bool(asset.get("available")) for asset in assets)
            and (include_block_audio or lightweight_materializable)
        ),
        "phone_owned_session": bool(phone_owned_session),
        "warnings": warnings,
        "runtime": {
            "mode": "mobile_phone_runtime",
            "audio_playback_strategy": "audiotrack_pcm_wav_playback_head",
            "scheduled_block_materialization_strategy": "pcm_wav_concat_without_ffmpeg",
            "tactile_cue_scheduler": "audiotrack_playback_head",
            "response_input": "touch",
            "tactile_output": "android_vibrator",
            "clock": "android_elapsed_realtime",
            "session_owner": "phone" if phone_owned_session else "pc_runner_bridge",
            "lsl_strategy": "local_marker_mirror_with_native_liblsl_hook",
            "limitations": list(MOBILE_RUNTIME_LIMITATIONS),
        },
    }


def validate_mobile_package_manifest(
    manifest: dict[str, Any],
    *,
    require_v2: bool = True,
    require_phone_owned_session: bool = False,
    require_building_blocks: bool = False,
    require_available_assets: bool = True,
    require_lightweight_scheduled_blocks: bool = False,
) -> MobilePackageValidationResult:
    """Validate the Android phone-owned run package hierarchy and replay contract."""

    failures: list[str] = []
    warnings: list[str] = []
    schema = str(manifest.get("schema") or "")
    if require_v2 and schema != MOBILE_PACKAGE_SCHEMA:
        failures.append(f"package schema must be {MOBILE_PACKAGE_SCHEMA!r}, got {schema!r}")
    elif schema not in {MOBILE_PACKAGE_SCHEMA, MOBILE_PACKAGE_SCHEMA_V1}:
        failures.append(f"unsupported mobile package schema {schema!r}")
    if require_phone_owned_session and manifest.get("phone_owned_session") is not True:
        failures.append("phone-owned validation requires phone_owned_session=true")

    blocks = _json_list(manifest.get("blocks"))
    assets = _json_list(manifest.get("assets"))
    building_blocks = _json_list(manifest.get("building_blocks"))
    schedule = manifest.get("schedule") if isinstance(manifest.get("schedule"), dict) else {}
    schedule_blocks = _json_list(schedule.get("blocks"))
    execution_order = [str(item) for item in _json_list(schedule.get("execution_order"))]
    asset_by_id = {str(asset.get("asset_id") or ""): asset for asset in assets if isinstance(asset, dict)}
    building_block_by_id = {
        str(block.get("asset_id") or ""): block
        for block in building_blocks
        if isinstance(block, dict)
    }
    block_ids = [str(block.get("block_id") or "") for block in blocks if isinstance(block, dict)]
    block_audio_assets = [asset for asset in assets if isinstance(asset, dict) and str(asset.get("role") or "") == "block_audio"]
    if not blocks:
        failures.append("package must contain at least one prepared block")
    if require_lightweight_scheduled_blocks and block_audio_assets:
        failures.append("lightweight scheduled-block validation requires omitting block_audio assets")
    if execution_order and execution_order != block_ids:
        failures.append("schedule.execution_order must match prepared block order")
    if schedule_blocks and [str(block.get("block_id") or "") for block in schedule_blocks if isinstance(block, dict)] != block_ids:
        failures.append("schedule.blocks block_id order must match prepared blocks")

    for index, block in enumerate(blocks, start=1):
        if not isinstance(block, dict):
            failures.append(f"block {index} is not a JSON object")
            continue
        block_id = str(block.get("block_id") or "")
        audio_asset_id = str(block.get("audio_asset_id") or "")
        trials = _json_list(block.get("trials"))
        block_materializable = _block_can_materialize_from_building_blocks(
            trials,
            building_block_by_id,
            asset_by_id,
            require_available_assets=require_available_assets,
        )
        if require_lightweight_scheduled_blocks and not block_materializable:
            failures.append(f"block {block_id or index} cannot be materialized from trial_building_block assets")
        if not block_id:
            failures.append(f"block {index} is missing block_id")
        if not audio_asset_id:
            failures.append(f"block {block_id or index} is missing audio_asset_id")
        elif audio_asset_id not in asset_by_id:
            if block_materializable:
                warnings.append(
                    f"block {block_id or index} audio_asset_id {audio_asset_id!r} is omitted; "
                    "Android must materialize the scheduled block from trial_building_block assets"
                )
            else:
                failures.append(f"block {block_id or index} audio_asset_id {audio_asset_id!r} is not listed in assets")
        else:
            asset = asset_by_id[audio_asset_id]
            if str(asset.get("role") or "") != "block_audio":
                failures.append(f"asset {audio_asset_id!r} must have role='block_audio'")
            elif _asset_is_available_for_runtime(asset, require_sha=require_available_assets):
                _validate_asset_availability(audio_asset_id, asset, failures, warnings, require_available=require_available_assets)
            elif block_materializable:
                warnings.append(
                    f"block {block_id or index} block_audio asset {audio_asset_id!r} is unavailable; "
                    "Android can materialize the scheduled block from trial_building_block assets"
                )
            else:
                _validate_asset_availability(audio_asset_id, asset, failures, warnings, require_available=require_available_assets)
        tactile_cues = _json_list(block.get("tactile_cues"))
        trial_by_uid = {str(trial.get("trial_uid") or ""): trial for trial in trials if isinstance(trial, dict)}
        if int(block.get("trial_count") or 0) != len(trials):
            failures.append(f"block {block_id or index} trial_count does not match trials length")
        for trial_index, trial in enumerate(trials, start=1):
            if not isinstance(trial, dict):
                failures.append(f"block {block_id or index} trial {trial_index} is not a JSON object")
                continue
            trial_uid = str(trial.get("trial_uid") or "")
            if not trial_uid:
                failures.append(f"block {block_id or index} trial {trial_index} is missing trial_uid")
            asset_id = str(trial.get("building_block_asset_id") or "")
            if asset_id:
                _validate_building_block_reference(asset_id, building_block_by_id, asset_by_id, failures, warnings, require_available_assets)
            elif require_building_blocks and _trial_needs_building_block(trial):
                failures.append(f"trial {trial_uid or trial_index} is missing building_block_asset_id")
        for cue_index, cue in enumerate(tactile_cues, start=1):
            if not isinstance(cue, dict):
                failures.append(f"block {block_id or index} tactile cue {cue_index} is not a JSON object")
                continue
            trial_uid = str(cue.get("trial_uid") or "")
            if trial_uid not in trial_by_uid:
                failures.append(f"tactile cue {cue_index} in block {block_id or index} references unknown trial_uid {trial_uid!r}")
            else:
                trial = trial_by_uid[trial_uid]
                cue_time = _float(cue.get("time_s"))
                start_s = _float(trial.get("start_s"))
                end_s = _float(trial.get("end_s"))
                if cue_time < start_s or (end_s > start_s and cue_time > end_s):
                    warnings.append(f"tactile cue {cue_index} in block {block_id or index} falls outside its trial window")

    if require_building_blocks and not building_blocks:
        failures.append("reconstructable phone package requires trial_building_block records")
    for asset_id, building_block in building_block_by_id.items():
        if not asset_id:
            failures.append("building block is missing asset_id")
            continue
        _validate_building_block_reference(asset_id, building_block_by_id, asset_by_id, failures, warnings, require_available_assets)
        if str(building_block.get("role") or "") != "trial_building_block":
            failures.append(f"building block {asset_id!r} must have role='trial_building_block'")

    _validate_schedule_building_blocks(schedule_blocks, building_block_by_id, failures, require_building_blocks=require_building_blocks)
    _validate_source_provenance(manifest, schedule_blocks, failures, warnings)
    _validate_reconstruction_contract(manifest, schedule_blocks, blocks, building_blocks, failures, warnings)
    _validate_lsl_contract(manifest, failures, warnings)
    _validate_runtime_contract(manifest, failures)

    participant_roster = [str(item) for item in _json_list(manifest.get("participant_roster"))]
    source_segment_hashes = manifest.get("source_segment_hashes") if isinstance(manifest.get("source_segment_hashes"), dict) else {}
    summary = {
        "schema": schema,
        "package_id": str(manifest.get("package_id") or ""),
        "participant_id": str(manifest.get("participant_id") or ""),
        "phone_owned_session": bool(manifest.get("phone_owned_session")),
        "asset_strategy": str(manifest.get("asset_strategy") or ""),
        "block_count": len(blocks),
        "trial_count": sum(len(_json_list(block.get("trials"))) for block in blocks if isinstance(block, dict)),
        "tactile_cue_count": sum(len(_json_list(block.get("tactile_cues"))) for block in blocks if isinstance(block, dict)),
        "asset_count": len(assets),
        "block_audio_asset_count": len(block_audio_assets),
        "trial_building_block_asset_count": len(
            [asset for asset in assets if isinstance(asset, dict) and str(asset.get("role") or "") == "trial_building_block"]
        ),
        "building_block_count": len(building_blocks),
        "participant_roster_count": len(participant_roster),
        "randomization_seed": str(manifest.get("randomization_seed") or ""),
        "source_segment_hash_schema": str(source_segment_hashes.get("schema") or "") if source_segment_hashes else "",
        "source_segment_block_csv_count": len(_json_list(source_segment_hashes.get("segment5_block_csvs"))) if source_segment_hashes else 0,
        "schedule_hash": str((manifest.get("reconstruction") or {}).get("schedule_hash") or "") if isinstance(manifest.get("reconstruction"), dict) else "",
        "mobile_runnable": bool(manifest.get("mobile_runnable")),
        "lightweight_scheduled_blocks": bool(blocks) and len(block_audio_assets) == 0 and all(
            isinstance(block, dict) and _block_can_materialize_from_building_blocks(
                _json_list(block.get("trials")),
                building_block_by_id,
                asset_by_id,
                require_available_assets=require_available_assets,
            )
            for block in blocks
        ),
    }
    return MobilePackageValidationResult(
        ok=not failures,
        failures=failures,
        warnings=warnings,
        summary=summary,
    )


def mobile_asset_path(package: Any, package_id: str, asset_id: str) -> Path:
    expected_package_id = mobile_package_id(package)
    if str(package_id) != expected_package_id:
        raise MobileRuntimePackageError("Unknown mobile package.")
    for block in list(getattr(package, "blocks", []) or []):
        candidate_id = f"block-{int(getattr(block, 'index', 0) or 0):02d}-audio"
        if str(asset_id) == candidate_id:
            path = Path(getattr(block, "wav_path", "") or "")
            if not path.is_file():
                raise MobileRuntimePackageError("Mobile package asset is missing.")
            return path
        for trial in _block_trial_payloads(block)[0]:
            candidate_id, _building_block = _building_block_from_trial(trial)
            if str(asset_id) == candidate_id:
                trial_path = Path(str(trial.get("trial_file_path") or ""))
                if not trial_path.is_file():
                    raise MobileRuntimePackageError("Mobile package building-block asset is missing.")
                return trial_path
    raise MobileRuntimePackageError("Unknown mobile package asset.")


def write_mobile_runtime_events(
    package: Any,
    *,
    output_root: Path,
    run_id: str,
    payload: dict[str, Any],
    complete: bool,
) -> dict[str, Any]:
    package_id = str(payload.get("package_id") or mobile_package_id(package))
    if package_id != mobile_package_id(package):
        raise MobileRuntimePackageError("Uploaded events target a different mobile package.")
    clean_run_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(run_id or "phone-run")).strip("-._") or "phone-run"
    out_dir = (
        output_runner_logs_dir(output_root)
        / "mobile_phone_runtime"
        / str(getattr(package, "participant_id", "") or "participant")
        / package_id
        / clean_run_id
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    accepted_at = _utc_now()
    events = [dict(item) for item in list(payload.get("events") or []) if isinstance(item, dict)]
    marker_rows = [dict(item) for item in list(payload.get("lsl_marker_mirror") or events) if isinstance(item, dict)]
    trigger_code_rows = _trigger_code_rows_from_markers(
        [dict(item) for item in list(payload.get("trigger_codes") or marker_rows) if isinstance(item, dict)]
    )
    command_rows = [dict(item) for item in list(payload.get("command_diary") or []) if isinstance(item, dict)]
    participant_metadata = _json_dict(payload.get("participant_metadata"))
    haptic_metadata = _json_dict(payload.get("haptic")) or _json_dict(payload.get("haptic_capability"))
    response_summary = _json_dict(payload.get("phone_response_summary"))
    response_ledger_rows = _json_dict_rows(payload.get("phone_response_ledger"))
    topup_plan = _json_dict(payload.get("phone_topup_plan"))
    topup_materialization = _json_dict(payload.get("phone_topup_materialization"))
    run_package_manifest = _mobile_runtime_upload_package_manifest(package, payload)
    run_package_manifest_path = out_dir / "run_package_manifest.json"
    with open(_filesystem_path(run_package_manifest_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(run_package_manifest, indent=2, sort_keys=True, default=str) + "\n")
    run_package_manifest_sha256 = _sha256(run_package_manifest_path)
    reconstruction_artifact = _mobile_runtime_upload_reconstruction_artifact(
        package,
        manifest=run_package_manifest,
        manifest_sha256=run_package_manifest_sha256,
    )
    reconstruction_artifact_path = out_dir / "reconstruction_contract.json"
    with open(_filesystem_path(reconstruction_artifact_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(reconstruction_artifact, indent=2, sort_keys=True, default=str) + "\n")
    lsl_runtime_status = _mobile_runtime_upload_lsl_runtime_status(
        package,
        payload=payload,
        manifest=run_package_manifest,
        run_id=clean_run_id,
    )
    event_path = out_dir / "events.jsonl"
    if events:
        with open(_filesystem_path(event_path), "a", encoding="utf-8") as handle:
            for event in events:
                row = dict(event)
                row.setdefault("accepted_at", accepted_at)
                row.setdefault("package_id", package_id)
                row.setdefault("run_id", clean_run_id)
                handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")
        _write_events_csv(out_dir / "events.csv", events)

    artifact = {
        "schema": MOBILE_RUNTIME_ARTIFACT_SCHEMA,
        "accepted_at": accepted_at,
        "complete": bool(complete),
        "completed": bool(complete),
        "package_id": package_id,
        "run_id": clean_run_id,
        "participant_id": str(getattr(package, "participant_id", "") or ""),
        "session_id": str(getattr(package, "session_id", "") or ""),
        "event_count": len(events),
        "phone_payload": payload,
        "package_manifest": {
            "filename": run_package_manifest_path.name,
            "schema": str(run_package_manifest.get("schema") or ""),
            "sha256": run_package_manifest_sha256,
        },
        "reconstruction_artifact": {
            "filename": reconstruction_artifact_path.name,
            "schema": MOBILE_PHONE_RUN_RECONSTRUCTION_ARTIFACT_SCHEMA,
        },
        "lsl_runtime_status": lsl_runtime_status,
        "lsl_marker_mirror": marker_rows,
        "trigger_codes": trigger_code_rows,
        "command_diary": command_rows,
        "paths": {
            "directory": str(out_dir),
            "run_package_manifest_json": str(run_package_manifest_path),
            "reconstruction_contract_json": str(reconstruction_artifact_path),
            "events_jsonl": str(event_path),
            "events_csv": str(out_dir / "events.csv"),
            "lsl_marker_mirror_csv": str(out_dir / "lsl_marker_mirror.csv"),
            "trigger_codes_csv": str(out_dir / "trigger_codes.csv"),
            "command_diary_jsonl": str(out_dir / "command_diary.jsonl"),
        },
    }
    if participant_metadata:
        artifact["participant_metadata"] = participant_metadata
    if haptic_metadata:
        artifact["haptic"] = haptic_metadata
    if artifact["lsl_runtime_status"]:
        lsl_status_path = out_dir / "lsl_runtime_status.json"
        with open(_filesystem_path(lsl_status_path), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(artifact["lsl_runtime_status"], indent=2, sort_keys=True, default=str) + "\n")
        artifact["paths"]["lsl_runtime_status_json"] = str(lsl_status_path)
    _write_lsl_marker_mirror_csv(out_dir / "lsl_marker_mirror.csv", marker_rows)
    _write_trigger_codes_csv(out_dir / "trigger_codes.csv", trigger_code_rows)
    _write_command_diary(out_dir / "command_diary.jsonl", command_rows)
    if response_summary:
        artifact["phone_response_summary"] = response_summary
    if response_ledger_rows:
        response_ledger_path = out_dir / "phone_response_ledger.csv"
        _write_rows_csv(
            response_ledger_path,
            response_ledger_rows,
            _dynamic_fieldnames(response_ledger_rows, preferred=PHONE_RESPONSE_LEDGER_FIELDNAMES),
        )
        artifact["phone_response_ledger"] = response_ledger_rows
        artifact["paths"]["phone_response_ledger_csv"] = str(response_ledger_path)
    if topup_plan:
        topup_plan_path = out_dir / "phone_topup_plan.json"
        with open(_filesystem_path(topup_plan_path), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(topup_plan, indent=2, sort_keys=True, default=str) + "\n")
        artifact["phone_topup_plan"] = topup_plan
        artifact["paths"]["phone_topup_plan_json"] = str(topup_plan_path)
    if topup_materialization:
        topup_materialization_path = out_dir / "phone_topup_materialization.json"
        with open(_filesystem_path(topup_materialization_path), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(topup_materialization, indent=2, sort_keys=True, default=str) + "\n")
        artifact["phone_topup_materialization"] = topup_materialization
        artifact["paths"]["phone_topup_materialization_json"] = str(topup_materialization_path)
    phone_owned_data_export = None
    if complete and response_ledger_rows:
        phone_owned_data_export = _write_phone_owned_upload_export(
            package,
            out_dir=out_dir,
            run_id=clean_run_id,
            response_ledger_rows=response_ledger_rows,
            accepted_at=accepted_at,
        )
        artifact["phone_owned_data_export"] = phone_owned_data_export
        artifact["paths"]["phone_owned_data_export_json"] = str(out_dir / "phone_owned_data_export.json")
        artifact["paths"]["phone_owned_data_min_participant_csv"] = str(
            phone_owned_data_export.get("data_min_participant_csv") or ""
        )
        artifact["paths"]["phone_owned_data_min_master_csv"] = str(
            phone_owned_data_export.get("data_min_master_successful_participants_csv") or ""
        )
        artifact["paths"]["phone_owned_data_max_run_dir"] = str(phone_owned_data_export.get("data_max_run_dir") or "")
    if complete:
        artifact_inventory_path = out_dir / MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_JSON
        artifact_inventory_csv_path = out_dir / MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_CSV
        artifact["artifact_file_inventory_artifact"] = {
            "filename": artifact_inventory_path.name,
            "csv_filename": artifact_inventory_csv_path.name,
            "schema": MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_SCHEMA,
            "self_included": False,
            "generated_by": "pc_mobile_runtime_upload_mirror",
        }
        artifact["paths"]["artifact_file_inventory_json"] = str(artifact_inventory_path)
        artifact["paths"]["artifact_file_inventory_csv"] = str(artifact_inventory_csv_path)
    artifact_path = out_dir / ("completion.json" if complete else "latest_events_upload.json")
    with open(_filesystem_path(artifact_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(artifact, indent=2, sort_keys=True, default=str) + "\n")
    if complete:
        _write_mobile_runtime_artifact_file_inventory(
            out_dir,
            run_id=clean_run_id,
            package_id=package_id,
            complete=complete,
        )
    if phone_owned_data_export:
        _copy_phone_owned_data_max(out_dir, Path(str(phone_owned_data_export.get("data_max_run_dir") or "")))
    return {
        "schema": MOBILE_RUN_COMPLETE_SCHEMA if complete else MOBILE_RUN_EVENTS_SCHEMA,
        "status": "accepted",
        "accepted_at": accepted_at,
        "package_id": package_id,
        "run_id": clean_run_id,
        "event_count": len(events),
        "artifact_path": str(artifact_path),
        "artifact_dir": str(out_dir),
    }


def _asset_payload(asset_id: str, path: Path, *, include_sha256: bool) -> dict[str, Any]:
    available = path.is_file()
    size = path.stat().st_size if available else 0
    return {
        "asset_id": asset_id,
        "filename": path.name,
        "media_type": "audio/wav",
        "role": "block_audio",
        "size_bytes": int(size),
        "sha256": _sha256(path) if include_sha256 and available else "",
        "available": bool(available),
    }


def _validate_asset_availability(
    asset_id: str,
    asset: dict[str, Any],
    failures: list[str],
    warnings: list[str],
    *,
    require_available: bool,
) -> None:
    if require_available and asset.get("available") is not True:
        failures.append(f"asset {asset_id!r} is not available")
    if require_available and int(asset.get("size_bytes") or 0) <= 0:
        failures.append(f"asset {asset_id!r} has no recorded size_bytes")
    if not str(asset.get("sha256") or "").strip():
        message = f"asset {asset_id!r} has no sha256"
        if require_available:
            failures.append(message)
        else:
            warnings.append(message)


def _asset_is_available_for_runtime(asset: dict[str, Any], *, require_sha: bool) -> bool:
    if asset.get("available") is not True:
        return False
    if int(asset.get("size_bytes") or 0) <= 0:
        return False
    if require_sha and not str(asset.get("sha256") or "").strip():
        return False
    return True


def _all_blocks_reference_available_building_blocks(
    blocks: list[dict[str, Any]],
    building_blocks: list[dict[str, Any]],
    asset_by_id: dict[str, dict[str, Any]],
) -> bool:
    building_block_by_id = {
        str(block.get("asset_id") or ""): block
        for block in building_blocks
        if isinstance(block, dict)
    }
    return bool(blocks) and all(
        isinstance(block, dict) and _block_can_materialize_from_building_blocks(
            _json_list(block.get("trials")),
            building_block_by_id,
            asset_by_id,
            require_available_assets=True,
            require_sha=False,
        )
        for block in blocks
    )


def _block_can_materialize_from_building_blocks(
    trials: list[Any],
    building_block_by_id: dict[str, dict[str, Any]],
    asset_by_id: dict[str, dict[str, Any]],
    *,
    require_available_assets: bool,
    require_sha: bool | None = None,
) -> bool:
    if not trials:
        return False
    for trial in trials:
        if not isinstance(trial, dict):
            return False
        asset_id = str(trial.get("building_block_asset_id") or "")
        if not asset_id or asset_id not in building_block_by_id:
            return False
        asset = asset_by_id.get(asset_id)
        if asset is None or str(asset.get("role") or "") != "trial_building_block":
            return False
        if require_available_assets and not _asset_is_available_for_runtime(
            asset,
            require_sha=require_available_assets if require_sha is None else require_sha,
        ):
            return False
    return True


def _validate_building_block_reference(
    asset_id: str,
    building_block_by_id: dict[str, dict[str, Any]],
    asset_by_id: dict[str, dict[str, Any]],
    failures: list[str],
    warnings: list[str],
    require_available_assets: bool,
) -> None:
    if asset_id not in building_block_by_id:
        failures.append(f"building_block_asset_id {asset_id!r} is not listed in building_blocks")
    asset = asset_by_id.get(asset_id)
    if asset is None:
        failures.append(f"building_block_asset_id {asset_id!r} is not listed in assets")
        return
    if str(asset.get("role") or "") != "trial_building_block":
        failures.append(f"asset {asset_id!r} must have role='trial_building_block'")
    _validate_asset_availability(asset_id, asset, failures, warnings, require_available=require_available_assets)


def _validate_schedule_building_blocks(
    schedule_blocks: list[Any],
    building_block_by_id: dict[str, dict[str, Any]],
    failures: list[str],
    *,
    require_building_blocks: bool,
) -> None:
    for index, block in enumerate(schedule_blocks, start=1):
        if not isinstance(block, dict):
            failures.append(f"schedule block {index} is not a JSON object")
            continue
        trial_uids = _json_list(block.get("trial_uids"))
        asset_ids = [str(value) for value in _json_list(block.get("building_block_asset_ids"))]
        if trial_uids and len(asset_ids) != len(trial_uids):
            failures.append(f"schedule block {block.get('block_id') or index} building-block list length does not match trial_uids")
        for asset_id in asset_ids:
            if asset_id and asset_id not in building_block_by_id:
                failures.append(f"schedule references unknown building block asset {asset_id!r}")
            elif require_building_blocks and not asset_id:
                failures.append(f"schedule block {block.get('block_id') or index} has an empty building-block asset id")


def _validate_source_provenance(
    manifest: dict[str, Any],
    schedule_blocks: list[Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    participant_roster = [str(item).strip() for item in _json_list(manifest.get("participant_roster")) if str(item).strip()]
    if len(participant_roster) != len(set(participant_roster)):
        failures.append("participant_roster contains duplicate participant ids")
    participant_id = str(manifest.get("participant_id") or "").strip()
    if participant_roster and participant_id and participant_id not in participant_roster:
        failures.append("participant_roster does not include package participant_id")
    if not participant_roster:
        warnings.append("participant_roster is missing from mobile package provenance")

    if not str(manifest.get("randomization_seed") or "").strip():
        warnings.append("randomization_seed is missing from mobile package provenance")

    source_segment_hashes = manifest.get("source_segment_hashes") if isinstance(manifest.get("source_segment_hashes"), dict) else {}
    if not source_segment_hashes:
        warnings.append("source_segment_hashes is missing from mobile package provenance")
        return
    if source_segment_hashes.get("schema") != MOBILE_SOURCE_SEGMENT_HASHES_SCHEMA:
        failures.append("source_segment_hashes schema mismatch")
    reconstruction = manifest.get("reconstruction") if isinstance(manifest.get("reconstruction"), dict) else {}
    source_hash = str(source_segment_hashes.get("source_run_setup_manifest_sha256") or "").strip()
    reconstruction_hash = str(reconstruction.get("source_run_setup_sha256") or "").strip()
    if source_hash and reconstruction_hash and source_hash != reconstruction_hash:
        failures.append("source_segment_hashes source_run_setup_manifest_sha256 differs from reconstruction")

    schedule_by_id = {
        str(block.get("block_id") or ""): block
        for block in schedule_blocks
        if isinstance(block, dict)
    }
    for index, row in enumerate(_json_list(source_segment_hashes.get("segment5_block_csvs")), start=1):
        if not isinstance(row, dict):
            failures.append(f"source_segment_hashes segment5_block_csvs row {index} is not a JSON object")
            continue
        block_id = str(row.get("block_id") or "")
        if not block_id:
            failures.append(f"source_segment_hashes segment5_block_csvs row {index} is missing block_id")
            continue
        schedule_block = schedule_by_id.get(block_id)
        if schedule_block is None:
            failures.append(f"source_segment_hashes references unknown schedule block {block_id!r}")
            continue
        observed_hash = str(row.get("sha256") or "").strip()
        expected_hash = str(schedule_block.get("source_block_csv_sha256") or "").strip()
        if observed_hash and expected_hash and observed_hash != expected_hash:
            failures.append(f"source_segment_hashes block {block_id} SHA-256 differs from schedule.blocks")


def _validate_reconstruction_contract(
    manifest: dict[str, Any],
    schedule_blocks: list[Any],
    blocks: list[Any],
    building_blocks: list[Any],
    failures: list[str],
    warnings: list[str],
) -> None:
    reconstruction = manifest.get("reconstruction") if isinstance(manifest.get("reconstruction"), dict) else {}
    if not reconstruction:
        failures.append("reconstruction contract is missing")
        return
    if reconstruction.get("schema") != MOBILE_RECONSTRUCTION_SCHEMA:
        failures.append("reconstruction schema mismatch")
    hierarchy = [str(item) for item in _json_list(reconstruction.get("study_hierarchy"))]
    if hierarchy != MOBILE_REQUIRED_STUDY_HIERARCHY:
        failures.append("reconstruction study_hierarchy must preserve Segment 0-6 -> phone runtime order")
    if reconstruction.get("preferred_lightweight_strategy") != "replay_schedule_from_trial_building_blocks":
        failures.append("reconstruction preferred_lightweight_strategy must use trial building blocks")
    if reconstruction.get("fallback_execution_strategy") != "prepared_block_wavs":
        failures.append("reconstruction fallback_execution_strategy must preserve prepared block WAV replay")
    strategy = str(reconstruction.get("package_asset_strategy") or "")
    manifest_strategy = str(manifest.get("asset_strategy") or "")
    if strategy and strategy not in {"prepared_block_wavs_plus_trial_building_blocks", "trial_building_blocks_only"}:
        failures.append("reconstruction package_asset_strategy is not recognized")
    if strategy and manifest_strategy and strategy != manifest_strategy:
        failures.append("reconstruction package_asset_strategy does not match manifest asset_strategy")
    expected_hash = _json_sha256(schedule_blocks)
    observed_hash = str(reconstruction.get("schedule_hash") or "")
    if observed_hash != expected_hash:
        failures.append("reconstruction schedule_hash does not match schedule.blocks")
    if int(reconstruction.get("building_block_count") or 0) != len(building_blocks):
        failures.append("reconstruction building_block_count does not match building_blocks length")
    if int(reconstruction.get("block_count") or 0) != len(blocks):
        failures.append("reconstruction block_count does not match blocks length")
    trial_count = sum(len(_json_list(block.get("trials"))) for block in blocks if isinstance(block, dict))
    if int(reconstruction.get("trial_count") or 0) != trial_count:
        failures.append("reconstruction trial_count does not match block trial payloads")
    if not str(reconstruction.get("source_run_setup_sha256") or "").strip():
        warnings.append("reconstruction source_run_setup_sha256 is missing")


def _validate_lsl_contract(manifest: dict[str, Any], failures: list[str], warnings: list[str]) -> None:
    lsl = manifest.get("lsl") if isinstance(manifest.get("lsl"), dict) else {}
    if not lsl:
        failures.append("Android LSL contract is missing")
        return
    if lsl.get("schema") != MOBILE_LSL_CONTRACT_SCHEMA:
        failures.append("Android LSL contract schema mismatch")
    if lsl.get("runtime_authority") != "android_phone":
        failures.append("Android LSL contract runtime_authority must be android_phone")
    if lsl.get("privacy_default") != "metadata_payload_only":
        failures.append("Android LSL contract privacy_default must be metadata_payload_only")
    streams = lsl.get("stream_names") if isinstance(lsl.get("stream_names"), dict) else {}
    for key, expected in MOBILE_REQUIRED_LSL_STREAM_NAMES.items():
        if streams.get(key) != expected:
            failures.append(f"Android LSL stream {key} expected {expected!r}, got {streams.get(key)!r}")
    participant_id = str(manifest.get("participant_id") or "")
    if participant_id:
        for key, value in streams.items():
            if participant_id in str(value):
                failures.append(f"Android LSL stream {key} must not contain the participant id")
    commands = {str(item) for item in _json_list(lsl.get("supported_commands"))}
    missing_commands = sorted(MOBILE_REQUIRED_PHONE_COMMANDS - commands)
    if missing_commands:
        failures.append(f"Android LSL contract is missing supported commands: {', '.join(missing_commands)}")
    if lsl.get("native_android_lsl_required") is not True:
        warnings.append("Android LSL contract does not require native Android LSL")


def _validate_runtime_contract(manifest: dict[str, Any], failures: list[str]) -> None:
    runtime = manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else {}
    if not runtime:
        failures.append("runtime contract is missing")
        return
    if runtime.get("audio_playback_strategy") != "audiotrack_pcm_wav_playback_head":
        failures.append("runtime audio playback must use AudioTrack playback-head timing")
    if runtime.get("tactile_cue_scheduler") != "audiotrack_playback_head":
        failures.append("runtime tactile scheduler must use AudioTrack playback-head timing")
    if manifest.get("phone_owned_session") is True and runtime.get("session_owner") != "phone":
        failures.append("phone-owned package runtime.session_owner must be phone")


def _trial_needs_building_block(trial: dict[str, Any]) -> bool:
    text = f"{trial.get('family', '')} {trial.get('trial_type', '')}".lower()
    return "catch" not in text


def _json_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _mobile_source_provenance(
    package: Any,
    *,
    schedule_blocks: list[dict[str, Any]],
    source_run_setup_sha256: str,
) -> dict[str, Any]:
    source_run_setup = Path(getattr(package, "source_run_setup_manifest_path", "") or "")
    source_run_setup_text = str(getattr(package, "source_run_setup_manifest_path", "") or "")
    source_run_setup_manifest = _read_json_object(source_run_setup) if source_run_setup.is_file() else {}
    order_csv_path = _resolve_relative_source_path(source_run_setup_manifest.get("csv_path"), source_run_setup.parent)
    order_rows = _read_csv_dicts(order_csv_path) if order_csv_path.is_file() else []
    participant_roster = _unique_ordered(
        str(row.get("participant_id") or row.get("Participant_ID") or "").strip()
        for row in order_rows
    )
    participant_id = str(getattr(package, "participant_id", "") or "").strip()
    if participant_id and participant_id not in participant_roster:
        participant_roster.append(participant_id)

    source_segment5_manifest = _resolve_relative_source_path(
        source_run_setup_manifest.get("source_segment5_manifest"),
        source_run_setup.parent,
    )
    source_segment5_manifest_sha256 = str(source_run_setup_manifest.get("source_segment5_manifest_sha256") or "").strip()
    if not source_segment5_manifest_sha256 and source_segment5_manifest.is_file():
        source_segment5_manifest_sha256 = _sha256(source_segment5_manifest)
    segment5_manifest = _read_json_object(source_segment5_manifest) if source_segment5_manifest.is_file() else {}
    randomization_seed = str(
        source_run_setup_manifest.get("randomization_seed")
        or segment5_manifest.get("randomization_seed")
        or ""
    )

    block_csvs = []
    for block in schedule_blocks:
        path_text = str(block.get("source_block_csv_path") or "").strip()
        hash_text = str(block.get("source_block_csv_sha256") or "").strip()
        if not path_text and not hash_text:
            continue
        block_csvs.append(
            {
                "block_id": str(block.get("block_id") or ""),
                "index": int(block.get("index") or 0),
                "path": path_text,
                "sha256": hash_text,
            }
        )

    source_segment_hashes = {
        "schema": MOBILE_SOURCE_SEGMENT_HASHES_SCHEMA,
        "source_run_setup_manifest": source_run_setup_text,
        "source_run_setup_manifest_sha256": source_run_setup_sha256,
        "source_segment5_manifest": str(source_segment5_manifest) if source_segment5_manifest != source_run_setup.parent else "",
        "source_segment5_manifest_sha256": source_segment5_manifest_sha256,
        "segment6_order_csv": str(order_csv_path) if order_csv_path != source_run_setup.parent else "",
        "segment6_order_csv_sha256": _sha256(order_csv_path) if order_csv_path.is_file() else "",
        "segment5_block_csvs": block_csvs,
    }
    return {
        "participant_roster": participant_roster,
        "randomization_seed": randomization_seed,
        "source_segment_hashes": source_segment_hashes,
    }


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        with open(_filesystem_path(path), "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
    try:
        with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return []


def _resolve_relative_source_path(value: Any, base_dir: Path) -> Path:
    text = str(value or "").strip()
    if not text:
        return base_dir
    path = Path(text).expanduser()
    if path.is_absolute():
        return path
    return base_dir / path


def _unique_ordered(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            result.append(text)
            seen.add(text)
    return result


def _building_block_from_trial(trial: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    trial_file = str(trial.get("trial_file_path") or "").strip()
    if not trial_file:
        return "", None
    path = Path(trial_file)
    source_hash = str(trial.get("source_sha256") or "").strip()
    asset_id = "trial-" + hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
    return asset_id, {
        "asset_id": asset_id,
        "role": "trial_building_block",
        "filename": path.name,
        "media_type": "audio/wav",
        "path": str(path),
        "available": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
        "sha256": source_hash or (_sha256(path) if path.is_file() else ""),
        "trial_type": str(trial.get("trial_type") or ""),
        "family": str(trial.get("family") or ""),
        "row_label": str(trial.get("row_label") or ""),
        "soa_ms": str(trial.get("soa_ms") or ""),
        "noise_type": str(trial.get("noise_type") or ""),
        "duration_s": trial.get("duration_s", 0.0),
        "tactile_onset_s": trial.get("tactile_onset_s"),
        "response_window_onset_s": trial.get("response_window_onset_s"),
    }


def _block_trial_payloads(block: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = Path(getattr(block, "manifest_path", "") or "")
    if not manifest_path.is_file():
        return [], []
    rows: list[dict[str, str]] = []
    try:
        with open(_filesystem_path(manifest_path), newline="", encoding="utf-8-sig") as handle:
            rows = [dict(row) for row in csv.DictReader(handle)]
    except Exception:
        return [], []
    trials: list[dict[str, Any]] = []
    cues: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        trial_number = _int(_first(row, "Trial_Number", "trial_number"), index)
        start_s = _float(_first(row, "Trial_Start_S", "start_s", "trial_start_s"))
        duration_s = _float(_first(row, "Trial_Duration_S", "duration_s"))
        end_s = _float(_first(row, "Trial_End_S", "end_s"))
        if end_s <= 0.0 and duration_s > 0.0:
            end_s = start_s + duration_s
        family = _first(row, "Family", "family")
        trial_type = _first(row, "Trial_Type", "trial_type")
        tactile_onset = _optional_float(_first(row, "Tactile_Onset_S", "tactile_onset_s"))
        response_onset = _optional_float(_first(row, "Response_Window_Onset_S", "response_window_onset_s"))
        trial_uid = _first(row, "Trial_UID", "trial_uid") or f"trial-{trial_number:03d}"
        trial_payload = {
            "trial_number": trial_number,
            "trial_uid": trial_uid,
            "trial_type": trial_type,
            "family": family,
            "soa_ms": _first(row, "SOA_ms", "soa_ms"),
            "row_label": _first(row, "Row_Label", "Row", "row_label"),
            "noise_type": _first(row, "Noise_Type", "noise_type"),
            "start_s": start_s,
            "end_s": max(end_s, start_s),
            "duration_s": max(0.0, duration_s if duration_s > 0.0 else end_s - start_s),
            "tactile_onset_s": tactile_onset,
            "response_window_onset_s": response_onset,
            "trial_file_path": _first(row, "Trial_File_Path", "trial_file_path"),
            "source_sha256": _first(row, "Source_SHA256", "source_sha256", "Trial_File_SHA256", "trial_file_sha256"),
            "source_file_name": _first(row, "Source_File_Name", "source_file_name"),
        }
        building_block_asset_id, _building_block = _building_block_from_trial(trial_payload)
        if building_block_asset_id:
            trial_payload["building_block_asset_id"] = building_block_asset_id
        trials.append(trial_payload)
        if tactile_onset is not None and _has_tactile(row, family=family, trial_type=trial_type):
            cues.append(
                {
                    "cue_id": len(cues) + 1,
                    "trial_number": trial_number,
                    "trial_uid": trial_uid,
                    "time_s": max(0.0, start_s + tactile_onset),
                    "trial_relative_time_s": max(0.0, tactile_onset),
                    "soa_ms": trial_payload["soa_ms"],
                    "row_label": trial_payload["row_label"],
                    "noise_type": trial_payload["noise_type"],
                }
            )
    return trials, sorted(cues, key=lambda cue: float(cue.get("time_s") or 0.0))


def _has_tactile(row: dict[str, Any], *, family: str, trial_type: str) -> bool:
    explicit = _first(row, "Tactile_Enabled", "tactile_enabled", "Has_Tactile", "has_tactile").strip().lower()
    if explicit in {"false", "0", "no", "n"}:
        return False
    if explicit in {"true", "1", "yes", "y"}:
        return True
    text = f"{family} {trial_type}".lower()
    return "baseline" in text or "audio_tactile" in text or "tactile" in text


def _write_events_csv(path: Path, events: list[dict[str, Any]]) -> None:
    keys: list[str] = []
    for event in events:
        for key in event:
            if key not in keys and isinstance(event.get(key), (str, int, float, bool, type(None))):
                keys.append(key)
    if not keys:
        return
    existing_rows: list[dict[str, Any]] = []
    if path.is_file():
        try:
            with open(_filesystem_path(path), newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                for key in reader.fieldnames or []:
                    if key not in keys:
                        keys.append(key)
                existing_rows = [dict(row) for row in reader]
        except Exception:
            existing_rows = []
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for row in existing_rows:
            writer.writerow(row)
        for event in events:
            writer.writerow({key: event.get(key, "") for key in keys})


def _write_lsl_marker_mirror_csv(path: Path, markers: list[dict[str, Any]]) -> None:
    fieldnames = [
        "marker_version",
        "event_id",
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
        "phone_unix_ms",
        "phone_elapsed_realtime_ms",
        "payload_json",
    ]
    _write_rows_csv(path, markers, fieldnames)


def _trigger_code_rows_from_markers(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for marker in markers:
        rows.append(
            {
                "event_id": marker.get("event_id", ""),
                "event_code": marker.get("event_code", ""),
                "event_type": marker.get("event_type", ""),
                "trigger_key": marker.get("trigger_key", ""),
                "phone_elapsed_realtime_ms": marker.get("phone_elapsed_realtime_ms", ""),
            }
        )
    return rows


def _write_trigger_codes_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "event_id",
        "event_code",
        "event_type",
        "trigger_key",
        "phone_elapsed_realtime_ms",
    ]
    _write_rows_csv(path, rows, fieldnames)


def _write_command_diary(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _mobile_runtime_upload_package_manifest(package: Any, payload: dict[str, Any]) -> dict[str, Any]:
    package_payload = payload.get("package") if isinstance(payload.get("package"), dict) else {}
    asset_strategy = str(package_payload.get("asset_strategy") or payload.get("asset_strategy") or "").strip()
    include_block_audio = asset_strategy != "trial_building_blocks_only"
    return build_mobile_package_manifest(
        package,
        phone_owned_session=bool(payload.get("phone_owned_session") or package_payload.get("phone_owned_session")),
        include_block_audio=include_block_audio,
    )


def _mobile_runtime_upload_reconstruction_artifact(
    package: Any,
    *,
    manifest: dict[str, Any],
    manifest_sha256: str,
) -> dict[str, Any]:
    reconstruction = manifest.get("reconstruction") if isinstance(manifest.get("reconstruction"), dict) else {}
    lsl = manifest.get("lsl") if isinstance(manifest.get("lsl"), dict) else {}
    stream_names = lsl.get("stream_names") if isinstance(lsl.get("stream_names"), dict) else {}
    return {
        "schema": MOBILE_PHONE_RUN_RECONSTRUCTION_ARTIFACT_SCHEMA,
        "package_id": str(manifest.get("package_id") or mobile_package_id(package)),
        "participant_id": str(manifest.get("participant_id") or getattr(package, "participant_id", "") or ""),
        "session_id": str(manifest.get("session_id") or getattr(package, "session_id", "") or ""),
        "session_group_id": str(manifest.get("session_group_id") or getattr(package, "session_group_id", "") or ""),
        "part_session_id": str(manifest.get("part_session_id") or getattr(package, "part_session_id", "") or ""),
        "part_number": manifest.get("part_number", getattr(package, "part_number", "")),
        "asset_strategy": str(manifest.get("asset_strategy") or ""),
        "run_package_manifest_sha256": str(manifest_sha256 or ""),
        "participant_roster_count": len(_json_list(manifest.get("participant_roster"))),
        "randomization_seed": str(manifest.get("randomization_seed") or ""),
        "source_segment_hashes": dict(manifest.get("source_segment_hashes") or {}),
        "reconstruction": dict(reconstruction),
        "lsl": {
            "schema": str(lsl.get("schema") or ""),
            "runtime_authority": str(lsl.get("runtime_authority") or ""),
            "rich_markers_name": str(stream_names.get("rich_markers") or ""),
            "numeric_triggers_name": str(stream_names.get("numeric_triggers") or ""),
            "command_signals_name": str(stream_names.get("command_signals") or ""),
            "command_acks_name": str(stream_names.get("command_acks") or ""),
            "native_android_lsl_required": bool(lsl.get("native_android_lsl_required")),
            "current_android_source_behavior": str(lsl.get("current_android_source_behavior") or ""),
        },
        "assets": [
            {
                "asset_id": str(asset.get("asset_id") or ""),
                "filename": str(asset.get("filename") or ""),
                "role": str(asset.get("role") or ""),
                "media_type": str(asset.get("media_type") or ""),
                "size_bytes": int(asset.get("size_bytes") or 0),
                "sha256": str(asset.get("sha256") or ""),
            }
            for asset in _json_list(manifest.get("assets"))
            if isinstance(asset, dict)
        ],
        "building_blocks": [
            dict(building_block)
            for building_block in _json_list(manifest.get("building_blocks"))
            if isinstance(building_block, dict)
        ],
        "blocks": [
            {
                "block_id": str(block.get("block_id") or ""),
                "index": block.get("index", ""),
                "label": str(block.get("label") or ""),
                "duration_s": block.get("duration_s", ""),
                "trial_count": block.get("trial_count", ""),
                "audio_asset_id": str(block.get("audio_asset_id") or ""),
                "trial_building_block_asset_ids": [
                    str(trial.get("building_block_asset_id") or "")
                    for trial in _json_list(block.get("trials"))
                    if isinstance(trial, dict)
                ],
                "tactile_cue_count": len(_json_list(block.get("tactile_cues"))),
            }
            for block in _json_list(manifest.get("blocks"))
            if isinstance(block, dict)
        ],
    }


def _mobile_runtime_upload_lsl_runtime_status(
    package: Any,
    *,
    payload: dict[str, Any],
    manifest: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    uploaded = _json_dict(payload.get("lsl_runtime_status"))
    lsl = manifest.get("lsl") if isinstance(manifest.get("lsl"), dict) else {}
    reconstruction = manifest.get("reconstruction") if isinstance(manifest.get("reconstruction"), dict) else {}
    streams = _mobile_runtime_lsl_streams(lsl)
    native_available = bool(uploaded.get("native_transport_available", False))
    marker_enabled = bool(uploaded.get("native_marker_transport_enabled", False))
    receiver_available = bool(uploaded.get("command_receiver_available", False))
    reason = "" if marker_enabled and receiver_available else "native_lsl_transport_not_fully_enabled"
    participant_metadata = _json_dict(payload.get("participant_metadata"))
    haptic_capability = _json_dict(payload.get("haptic")) or _json_dict(payload.get("haptic_capability"))
    defaults = {
        "schema": "pps-android-lsl-runtime-status.v1",
        "role": "runner",
        "package_id": str(manifest.get("package_id") or mobile_package_id(package)),
        "run_id": str(run_id or ""),
        "participant_id": str(manifest.get("participant_id") or getattr(package, "participant_id", "") or ""),
        "session_id": str(manifest.get("session_id") or getattr(package, "session_id", "") or ""),
        "session_group_id": str(manifest.get("session_group_id") or getattr(package, "session_group_id", "") or ""),
        "part_session_id": str(manifest.get("part_session_id") or getattr(package, "part_session_id", "") or ""),
        "part_number": manifest.get("part_number", getattr(package, "part_number", "")),
        "asset_strategy": str(manifest.get("asset_strategy") or reconstruction.get("package_asset_strategy") or ""),
        "runtime_authority": str(lsl.get("runtime_authority") or "android_phone"),
        "native_android_lsl_required": bool(lsl.get("native_android_lsl_required", True)),
        "native_transport": "liblsl",
        "native_transport_available": native_available,
        "native_marker_transport_enabled": marker_enabled,
        "native_marker_timestamp_strategy": "android_elapsed_realtime_plus_open_lsl_clock_offset",
        "command_receiver_available": receiver_available,
        "current_android_source_behavior": str(lsl.get("current_android_source_behavior") or "local_lsl_marker_mirror"),
        "reason": reason,
        "native_bridge": {
            "required_local_aar": "For-AI/experiments/android-companion/runner-companion/app/libs/liblsl-Android.aar",
            "stream_names": dict(streams),
            "marker_channels": list(LSL_MARKER_CHANNELS),
            "command_channels": list(LSL_COMMAND_CHANNELS),
            "ack_channels": list(LSL_ACK_CHANNELS),
        },
        "streams": streams,
        "command_protocol": {
            "command_schema": COMMAND_SCHEMA,
            "ack_schema": ACK_SCHEMA,
            "command_channels": list(LSL_COMMAND_CHANNELS),
            "ack_channels": list(LSL_ACK_CHANNELS),
            "supported_commands": [
                str(item)
                for item in _json_list(lsl.get("supported_commands"))
                if str(item).strip()
            ] or list(MOBILE_REQUIRED_PHONE_COMMAND_ORDER),
            "token_required": True,
            "token_payload_fields": ["token", "companion_token"],
        },
        "privacy": {
            "default": str(lsl.get("privacy_default") or "metadata_payload_only"),
            "participant_demographics_location": "metadata_and_payload_artifacts",
            "demographics_in_stream_name": False,
        },
        "stream_descriptions": _mobile_runtime_lsl_stream_descriptions(
            manifest=manifest,
            streams=streams,
            run_id=run_id,
            participant_metadata=participant_metadata,
            haptic_capability=haptic_capability,
        ),
    }
    participant_summary = _mobile_runtime_participant_metadata_summary(participant_metadata)
    if participant_summary:
        defaults["participant_metadata_summary"] = participant_summary
    haptic_summary = _mobile_runtime_haptic_capability_summary(haptic_capability)
    if haptic_summary:
        defaults["haptic_capability_summary"] = haptic_summary
    status = _deep_fill_missing(dict(uploaded), defaults)
    if not str(status.get("reason") or "").strip() and not (
        bool(status.get("native_marker_transport_enabled")) and bool(status.get("command_receiver_available"))
    ):
        status["reason"] = reason
    return status


def _mobile_runtime_lsl_streams(lsl: dict[str, Any]) -> dict[str, str]:
    stream_names = lsl.get("stream_names") if isinstance(lsl.get("stream_names"), dict) else {}
    return {
        "rich_markers": str(stream_names.get("rich_markers") or LSL_STREAM_NAME),
        "numeric_triggers": str(stream_names.get("numeric_triggers") or LSL_NUMERIC_STREAM_NAME),
        "command_signals": str(stream_names.get("command_signals") or LSL_COMMAND_STREAM_NAME),
        "command_acks": str(stream_names.get("command_acks") or LSL_ACK_STREAM_NAME),
    }


def _mobile_runtime_lsl_stream_descriptions(
    *,
    manifest: dict[str, Any],
    streams: dict[str, str],
    run_id: str,
    participant_metadata: dict[str, Any],
    haptic_capability: dict[str, Any],
) -> dict[str, Any]:
    run_token = _safe_lsl_source_token(run_id)
    session_metadata_json = json.dumps(
        _mobile_runtime_lsl_session_metadata(
            manifest,
            participant_metadata=participant_metadata,
            haptic_capability=haptic_capability,
        ),
        sort_keys=True,
        default=str,
    )
    common_identity = {
        "session_id": str(manifest.get("session_id") or ""),
        "participant_id": str(manifest.get("participant_id") or ""),
        "session_group_id": str(manifest.get("session_group_id") or ""),
        "part_session_id": str(manifest.get("part_session_id") or ""),
        "part_number": manifest.get("part_number", ""),
        "run_id": str(run_id or ""),
        "session_metadata_json": session_metadata_json,
    }
    return {
        "schema": "pps-android-lsl-stream-descriptions.v1",
        "runtime_authority": str((manifest.get("lsl") or {}).get("runtime_authority") or "android_phone")
        if isinstance(manifest.get("lsl"), dict)
        else "android_phone",
        "role": "runner",
        "privacy": {
            "default": str((manifest.get("lsl") or {}).get("privacy_default") or "metadata_payload_only")
            if isinstance(manifest.get("lsl"), dict)
            else "metadata_payload_only",
            "demographics_in_stream_name": False,
            "participant_demographics_location": "metadata_and_payload_artifacts",
        },
        "rich_markers": {
            "name": streams["rich_markers"],
            "type": "Markers",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(LSL_MARKER_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id": f"pps-android-markers-v2-{run_token}",
            "marker_version": MARKER_VERSION,
            "channel_labels": list(LSL_MARKER_CHANNELS),
            **common_identity,
        },
        "numeric_triggers": {
            "name": streams["numeric_triggers"],
            "type": "TriggerCodes",
            "role": "outlet",
            "channel_format": "int32",
            "channel_count": 1,
            "nominal_srate_hz": 0.0,
            "source_id": f"pps-android-trigger-codes-{run_token}",
            "channel_labels": ["event_code"],
            **common_identity,
        },
        "command_signals": {
            "name": streams["command_signals"],
            "type": "CommandSignals",
            "role": "inlet",
            "channel_format": "string",
            "channel_count": len(LSL_COMMAND_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id_pattern": "pps-*-command-signals-v1-*",
            "channel_labels": list(LSL_COMMAND_CHANNELS),
            "token_required": True,
        },
        "command_acks": {
            "name": streams["command_acks"],
            "type": "CommandAcks",
            "role": "outlet",
            "channel_format": "string",
            "channel_count": len(LSL_ACK_CHANNELS),
            "nominal_srate_hz": 0.0,
            "source_id": f"pps-android-command-acks-v1-{run_token}",
            "channel_labels": list(LSL_ACK_CHANNELS),
        },
    }


def _mobile_runtime_lsl_session_metadata(
    manifest: dict[str, Any],
    *,
    participant_metadata: dict[str, Any],
    haptic_capability: dict[str, Any],
) -> dict[str, Any]:
    reconstruction = manifest.get("reconstruction") if isinstance(manifest.get("reconstruction"), dict) else {}
    lsl = manifest.get("lsl") if isinstance(manifest.get("lsl"), dict) else {}
    payload: dict[str, Any] = {
        "package_id": str(manifest.get("package_id") or ""),
        "asset_strategy": str(manifest.get("asset_strategy") or reconstruction.get("package_asset_strategy") or ""),
        "schedule_hash": str(reconstruction.get("schedule_hash") or ""),
        "participant_roster_count": len(_json_list(manifest.get("participant_roster"))),
        "randomization_seed": str(manifest.get("randomization_seed") or ""),
        "source_segment_hashes": dict(manifest.get("source_segment_hashes") or {}),
        "package_asset_strategy": str(
            reconstruction.get("package_asset_strategy") or manifest.get("asset_strategy") or ""
        ),
        "study_hierarchy": [str(item) for item in _json_list(reconstruction.get("study_hierarchy"))],
        "source_run_setup_manifest_path": str(reconstruction.get("source_run_setup_manifest_path") or ""),
        "source_run_setup_sha256": str(reconstruction.get("source_run_setup_sha256") or ""),
        "privacy_default": str(lsl.get("privacy_default") or "metadata_payload_only"),
        "demographics_in_stream_name": False,
    }
    participant_summary = _mobile_runtime_participant_metadata_summary(participant_metadata)
    if participant_summary:
        payload["participant_metadata_summary"] = participant_summary
    haptic_summary = _mobile_runtime_haptic_capability_summary(haptic_capability)
    if haptic_summary:
        payload["haptic_capability_summary"] = haptic_summary
    return payload


def _mobile_runtime_participant_metadata_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    if not metadata:
        return {}
    return {
        "schema": "pps-android-lsl-participant-metadata-summary.v1",
        "participant_id": str(metadata.get("participant_id") or ""),
        "session_id": str(metadata.get("session_id") or ""),
        "session_group_id": str(metadata.get("session_group_id") or ""),
        "part_session_id": str(metadata.get("part_session_id") or ""),
        "part_number": str(metadata.get("part_number") or ""),
        "age_years": str(metadata.get("age_years") or ""),
        "handedness": str(metadata.get("handedness") or ""),
        "gender": str(metadata.get("gender") or ""),
        "tactile_threshold_percent": metadata.get("tactile_threshold_percent"),
        "tactile_threshold_source": str(metadata.get("tactile_threshold_source") or ""),
        "tactile_threshold_calibration_status": str(metadata.get("tactile_threshold_calibration_status") or ""),
        "stream_privacy": str(metadata.get("stream_privacy") or "metadata_payload_only"),
    }


def _mobile_runtime_haptic_capability_summary(haptic: dict[str, Any]) -> dict[str, Any]:
    if not haptic:
        return {}
    return {
        "schema": "pps-android-lsl-haptic-capability-summary.v1",
        "has_vibrator": bool(haptic.get("has_vibrator", False)),
        "has_amplitude_control": bool(haptic.get("has_amplitude_control", False)),
        "calibration_policy": str(haptic.get("calibration_policy") or ""),
        "calibration_status": str(haptic.get("calibration_status") or ""),
        "recommended_threshold_percent": haptic.get("recommended_threshold_percent"),
        "recommended_amplitude": haptic.get("recommended_amplitude"),
    }


def _deep_fill_missing(target: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    for key, value in defaults.items():
        if key not in target or target.get(key) in (None, ""):
            target[key] = value
            continue
        if isinstance(target.get(key), dict) and isinstance(value, dict):
            target[key] = _deep_fill_missing(dict(target[key]), value)
    return target


def _safe_lsl_source_token(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-._") or "phone-run"


def _write_mobile_runtime_artifact_file_inventory(
    out_dir: Path,
    *,
    run_id: str,
    package_id: str,
    complete: bool,
) -> dict[str, Any]:
    inventory_path = out_dir / MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_JSON
    inventory_csv_path = out_dir / MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_CSV
    rows: list[dict[str, Any]] = []
    for file_path in sorted(item for item in out_dir.rglob("*") if item.is_file()):
        relative_path = file_path.relative_to(out_dir).as_posix()
        if relative_path in {
            MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_JSON,
            MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_CSV,
        }:
            continue
        stat = file_path.stat()
        rows.append(
            {
                "relative_path": relative_path,
                "size_bytes": int(stat.st_size),
                "sha256": _sha256(file_path),
                "modified_unix_ms": int(stat.st_mtime * 1000),
            }
        )
    inventory = {
        "schema": MOBILE_PHONE_RUN_ARTIFACT_FILE_INVENTORY_SCHEMA,
        "run_id": str(run_id or ""),
        "package_id": str(package_id or ""),
        "complete": bool(complete),
        "generated_unix_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "self_included": False,
        "file_count": len(rows),
        "files": rows,
    }
    with open(_filesystem_path(inventory_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(inventory, indent=2, sort_keys=True, default=str) + "\n")
    _write_rows_csv(
        inventory_csv_path,
        rows,
        _dynamic_fieldnames(rows, preferred=PHONE_ARTIFACT_FILE_INVENTORY_FIELDNAMES),
    )
    return inventory


def _write_phone_owned_upload_export(
    package: Any,
    *,
    out_dir: Path,
    run_id: str,
    response_ledger_rows: list[dict[str, Any]],
    accepted_at: str,
) -> dict[str, Any]:
    export_root = out_dir.parent / "phone_owned_exports"
    data_min_dir = export_root / "1.Data_min"
    participant_id = _safe_phone_export_name(str(getattr(package, "participant_id", "") or "participant"))
    participant_csv = data_min_dir / f"{participant_id}.csv"
    cleaned_run_id = _safe_phone_export_name(run_id)
    data_max_run_dir = export_root / "2.Data_max" / participant_id / "runs" / cleaned_run_id
    rows = _phone_data_min_rows_from_response_ledger(package, response_ledger_rows)
    _write_phone_data_min_csv(participant_csv, rows)
    master_csv = _refresh_phone_data_min_master(data_min_dir)
    data_max_archive_path = f"phone_owned_exports/2.Data_max/{participant_id}/runs/{cleaned_run_id}"
    export_path = out_dir / "phone_owned_data_export.json"
    export = {
        "schema": MOBILE_PHONE_OWNED_DATA_EXPORT_SCHEMA,
        "accepted_at": accepted_at,
        "participant_id": participant_id,
        "run_id": cleaned_run_id,
        "package_id": mobile_package_id(package),
        "session_id": str(getattr(package, "session_id", "") or ""),
        "session_group_id": str(getattr(package, "session_group_id", "") or ""),
        "part_session_id": str(getattr(package, "part_session_id", "") or ""),
        "part_number": _package_part_number(package),
        "phone_owned_session": True,
        "pc_upload_mirror": True,
        "data_min_schema": "pps-data-min-publication-trials.v1",
        "data_min_fieldnames": list(PHONE_DATA_MIN_FIELDNAMES),
        "data_min_participant_csv": str(participant_csv),
        "data_min_master_successful_participants_csv": str(master_csv),
        "data_min_row_count": len(rows),
        "data_max_run_dir": str(data_max_run_dir),
        "data_max_source_run_dir": str(out_dir),
        "artifact_path": str(export_path),
        "portable_paths": {
            "archive_run_root": ".",
            "phone_owned_data_export": export_path.name,
            "phone_owned_exports_root": "phone_owned_exports",
            "data_min_participant_csv": f"phone_owned_exports/1.Data_min/{participant_csv.name}",
            "data_min_master_successful_participants_csv": (
                f"phone_owned_exports/1.Data_min/{master_csv.name}"
            ),
            "data_max_run_dir": data_max_archive_path,
            "data_max_completion_json": f"{data_max_archive_path}/completion.json",
            "data_max_phone_owned_data_export": f"{data_max_archive_path}/{export_path.name}",
            "data_max_artifact_file_inventory": f"{data_max_archive_path}/artifact_file_inventory.json",
            "data_max_artifact_file_inventory_csv": f"{data_max_archive_path}/artifact_file_inventory.csv",
        },
        "privacy": {
            "scope": "pc_mobile_runtime_phone_owned_upload_mirror",
            "demographics_in_stream_name": False,
            "participant_names_exported": False,
        },
    }
    with open(_filesystem_path(export_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(export, indent=2, sort_keys=True, default=str) + "\n")
    return export


def _copy_phone_owned_data_max(out_dir: Path, data_max_run_dir: Path) -> None:
    if not str(data_max_run_dir):
        return
    if data_max_run_dir.exists():
        shutil.rmtree(_filesystem_path(data_max_run_dir))
    data_max_run_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(_filesystem_path(out_dir), _filesystem_path(data_max_run_dir))


def _phone_data_min_rows_from_response_ledger(
    package: Any,
    response_ledger_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    trial_lookup = _mobile_trial_lookup(package)
    max_block_index = max(
        [_int(getattr(block, "index", 0), 0) for block in list(getattr(package, "blocks", []) or [])] or [0]
    )
    rows: list[dict[str, str]] = []
    global_index = 1
    for ledger_row in response_ledger_rows:
        role = str(ledger_row.get("ledger_role") or "source_trial")
        if role not in {"source_trial", "topup_rescue"}:
            continue
        source_trial_uid = (
            str(ledger_row.get("source_trial_uid") or "").strip()
            if role == "topup_rescue"
            else str(ledger_row.get("trial_uid") or "").strip()
        )
        block, trial = trial_lookup.get(source_trial_uid, (None, {}))
        hit = _truthy(ledger_row.get("hit"))
        trial_type = str(trial.get("trial_type") or "")
        family = str(trial.get("family") or "")
        block_index = max_block_index + 1 if role == "topup_rescue" else _int(
            ledger_row.get("block_index") or getattr(block, "index", 0),
            0,
        )
        row = {
            "participant_id": str(getattr(package, "participant_id", "") or ""),
            "session_id": str(getattr(package, "session_id", "") or ""),
            "part_session_id": str(getattr(package, "part_session_id", "") or ""),
            "part_number": _package_part_number(package),
            "block_number": str(block_index),
            "block_label": (
                "Phone top-up"
                if role == "topup_rescue"
                else str(getattr(block, "label", "") or ledger_row.get("block_id") or "")
            ),
            "trial_number": str(ledger_row.get("trial_number") or trial.get("trial_number") or ""),
            "trial_number_global": str(global_index),
            "trial_uid": str(ledger_row.get("trial_uid") or ""),
            "condition": family or trial_type,
            "phase": _normalize_phone_data_min_phase(trial.get("row_label")),
            "noise_type": str(trial.get("noise_type") or ""),
            "trial_type": trial_type,
            "soa_ms": str(trial.get("soa_ms") or ""),
            "response_given": "true" if hit else "false",
            "hit_miss": "Hit" if hit else "Miss",
            "reaction_time_ms": str(ledger_row.get("rt_ms") or ""),
        }
        rows.append(row)
        global_index += 1
    return rows


def _mobile_trial_lookup(package: Any) -> dict[str, tuple[Any, dict[str, Any]]]:
    lookup: dict[str, tuple[Any, dict[str, Any]]] = {}
    for block in list(getattr(package, "blocks", []) or []):
        trials, _cues = _block_trial_payloads(block)
        for trial in trials:
            trial_uid = str(trial.get("trial_uid") or "").strip()
            if trial_uid:
                lookup[trial_uid] = (block, trial)
    return lookup


def _write_phone_data_min_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PHONE_DATA_MIN_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in PHONE_DATA_MIN_FIELDNAMES})


def _refresh_phone_data_min_master(data_min_dir: Path) -> Path:
    master_csv = data_min_dir / "master_successful_participants.csv"
    data_min_dir.mkdir(parents=True, exist_ok=True)
    participant_csvs = [
        path for path in sorted(data_min_dir.glob("*.csv"), key=lambda item: item.name.lower())
        if path.name != master_csv.name
    ]
    with open(_filesystem_path(master_csv), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PHONE_DATA_MIN_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for participant_csv in participant_csvs:
            try:
                with open(_filesystem_path(participant_csv), newline="", encoding="utf-8-sig") as input_handle:
                    for row in csv.DictReader(input_handle):
                        writer.writerow({field: row.get(field, "") for field in PHONE_DATA_MIN_FIELDNAMES})
            except Exception:
                continue
    return master_csv


def _json_dict_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _json_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _dynamic_fieldnames(rows: list[dict[str, Any]], *, preferred: list[str] | tuple[str, ...] = ()) -> list[str]:
    fieldnames: list[str] = []
    for key in preferred:
        if key not in fieldnames:
            fieldnames.append(str(key))
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(str(key))
    return fieldnames


def _safe_phone_export_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-._")
    return clean or "participant"


def _package_part_number(package: Any) -> str:
    value = getattr(package, "part_number", "")
    return "" if value in (None, "") else str(value)


def _normalize_phone_data_min_phase(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in {"inhale", "inhalation", "inspiration"}:
        return "Inhale"
    if lowered in {"exhale", "exhalation", "expiration"}:
        return "Exhale"
    return text


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "hit"}


def _write_rows_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(_filesystem_path(path), "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            payload = dict(row)
            if "payload_json" not in payload:
                payload["payload_json"] = json.dumps(row, sort_keys=True, default=str)
            writer.writerow({key: payload.get(key, "") for key in fieldnames})


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(str(value).strip())
    except Exception:
        return default
    if not (number == number):
        return default
    return float(number)


def _optional_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    number = _float(text, default=float("nan"))
    if not (number == number):
        return None
    return float(number)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(_filesystem_path(path), "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _package_title(package: Any) -> str:
    part = getattr(package, "part_number", None)
    base = f"Participant {getattr(package, 'participant_id', '')}".strip()
    if part not in (None, ""):
        return f"{base} Part {part}"
    return base


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
