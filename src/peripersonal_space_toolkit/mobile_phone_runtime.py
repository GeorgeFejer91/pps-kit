"""Mobile phone runtime package export/import helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from typing import Any

from .output_layout import _filesystem_path, output_runner_logs_dir


MOBILE_PACKAGE_LIST_SCHEMA = "pps-mobile-run-package-list.v2"
MOBILE_PACKAGE_SCHEMA = "pps-mobile-run-package.v2"
MOBILE_PACKAGE_LIST_SCHEMA_V1 = "pps-mobile-run-package-list.v1"
MOBILE_PACKAGE_SCHEMA_V1 = "pps-mobile-run-package.v1"
MOBILE_RUN_EVENTS_SCHEMA = "pps-mobile-run-events.v1"
MOBILE_RUN_COMPLETE_SCHEMA = "pps-mobile-run-complete.v1"
MOBILE_RUNTIME_ARTIFACT_SCHEMA = "pps-mobile-runtime-artifact.v1"
MOBILE_RECONSTRUCTION_SCHEMA = "pps-mobile-reconstruction-contract.v1"
MOBILE_LSL_CONTRACT_SCHEMA = "pps-mobile-lsl-contract.v1"
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
MOBILE_REQUIRED_PHONE_COMMANDS = {
    "start_experiment",
    "start_part",
    "pause",
    "resume",
    "continue_instruction",
    "stop_after_block",
    "request_snapshot",
    "operator_note",
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
) -> dict[str, Any]:
    packages: list[dict[str, Any]] = []
    active_id = ""
    for item in _coerce_packages(package):
        manifest = build_mobile_package_manifest(
            item,
            include_trials=False,
            include_sha256=False,
            phone_owned_session=phone_owned_session,
        )
        if not active_id:
            active_id = str(manifest.get("package_id") or "")
        packages.append(
            {
                "package_id": str(manifest.get("package_id") or ""),
                "participant_id": manifest.get("participant_id", ""),
                "session_id": manifest.get("session_id", ""),
                "part_number": manifest.get("part_number"),
                "part_session_id": manifest.get("part_session_id", ""),
                "title": manifest.get("title", ""),
                "block_count": len(manifest.get("blocks") or []),
                "trial_count": sum(int(block.get("trial_count") or 0) for block in manifest.get("blocks") or []),
                "asset_count": len(manifest.get("assets") or []),
                "total_asset_bytes": sum(int(asset.get("size_bytes") or 0) for asset in manifest.get("assets") or []),
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
    source_run_setup = getattr(package, "source_run_setup_manifest_path", None)
    source_run_setup_sha256 = _sha256(Path(source_run_setup)) if source_run_setup and Path(source_run_setup).is_file() else ""
    session_group_id = str(getattr(package, "session_group_id", "") or "")
    part_session_id = str(getattr(package, "part_session_id", "") or getattr(package, "session_id", "") or "")
    part_number = getattr(package, "part_number", None)
    reconstruction = {
        "schema": MOBILE_RECONSTRUCTION_SCHEMA,
        "authority": "android_phone",
        "fallback_execution_strategy": "prepared_block_wavs",
        "preferred_lightweight_strategy": "replay_schedule_from_trial_building_blocks",
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
            "Block WAV assets remain available for current Android playback compatibility.",
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
        "supported_commands": [
            "start_experiment",
            "start_part",
            "pause",
            "resume",
            "continue_instruction",
            "stop_after_block",
            "request_snapshot",
            "operator_note",
        ],
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
        "mobile_runnable": bool(blocks_payload and all(bool(asset.get("available")) for asset in assets)),
        "phone_owned_session": bool(phone_owned_session),
        "warnings": warnings,
        "runtime": {
            "mode": "mobile_phone_runtime",
            "audio_playback_strategy": "audiotrack_pcm_wav_playback_head",
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
    if not blocks:
        failures.append("package must contain at least one prepared block")
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
        if not block_id:
            failures.append(f"block {index} is missing block_id")
        if not audio_asset_id:
            failures.append(f"block {block_id or index} is missing audio_asset_id")
        elif audio_asset_id not in asset_by_id:
            failures.append(f"block {block_id or index} audio_asset_id {audio_asset_id!r} is not listed in assets")
        else:
            asset = asset_by_id[audio_asset_id]
            if str(asset.get("role") or "") != "block_audio":
                failures.append(f"asset {audio_asset_id!r} must have role='block_audio'")
            _validate_asset_availability(audio_asset_id, asset, failures, warnings, require_available=require_available_assets)
        trials = _json_list(block.get("trials"))
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
    _validate_reconstruction_contract(manifest, schedule_blocks, blocks, building_blocks, failures, warnings)
    _validate_lsl_contract(manifest, failures, warnings)
    _validate_runtime_contract(manifest, failures)

    summary = {
        "schema": schema,
        "package_id": str(manifest.get("package_id") or ""),
        "participant_id": str(manifest.get("participant_id") or ""),
        "phone_owned_session": bool(manifest.get("phone_owned_session")),
        "block_count": len(blocks),
        "trial_count": sum(len(_json_list(block.get("trials"))) for block in blocks if isinstance(block, dict)),
        "tactile_cue_count": sum(len(_json_list(block.get("tactile_cues"))) for block in blocks if isinstance(block, dict)),
        "asset_count": len(assets),
        "building_block_count": len(building_blocks),
        "schedule_hash": str((manifest.get("reconstruction") or {}).get("schedule_hash") or "") if isinstance(manifest.get("reconstruction"), dict) else "",
        "mobile_runnable": bool(manifest.get("mobile_runnable")),
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
        "package_id": package_id,
        "run_id": clean_run_id,
        "participant_id": str(getattr(package, "participant_id", "") or ""),
        "session_id": str(getattr(package, "session_id", "") or ""),
        "event_count": len(events),
        "phone_payload": payload,
        "participant_metadata": dict(payload.get("participant_metadata") or {}),
        "lsl_runtime_status": dict(payload.get("lsl_runtime_status") or {}),
        "lsl_marker_mirror": list(payload.get("lsl_marker_mirror") or []),
        "command_diary": list(payload.get("command_diary") or []),
        "paths": {
            "directory": str(out_dir),
            "events_jsonl": str(event_path),
            "events_csv": str(out_dir / "events.csv"),
            "lsl_marker_mirror_csv": str(out_dir / "lsl_marker_mirror.csv"),
            "command_diary_jsonl": str(out_dir / "command_diary.jsonl"),
        },
    }
    if artifact["lsl_runtime_status"]:
        lsl_status_path = out_dir / "lsl_runtime_status.json"
        with open(_filesystem_path(lsl_status_path), "w", encoding="utf-8") as handle:
            handle.write(json.dumps(artifact["lsl_runtime_status"], indent=2, sort_keys=True, default=str) + "\n")
        artifact["paths"]["lsl_runtime_status_json"] = str(lsl_status_path)
    _write_lsl_marker_mirror_csv(out_dir / "lsl_marker_mirror.csv", list(payload.get("lsl_marker_mirror") or events))
    _write_command_diary(out_dir / "command_diary.jsonl", list(payload.get("command_diary") or []))
    artifact_path = out_dir / ("completion.json" if complete else "latest_events_upload.json")
    with open(_filesystem_path(artifact_path), "w", encoding="utf-8") as handle:
        handle.write(json.dumps(artifact, indent=2, sort_keys=True, default=str) + "\n")
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


def _write_command_diary(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with open(_filesystem_path(path), "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


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
