"""Validate row-level external trigger contracts through the runner.

This smoke targets the physiology/synchronization contract blocker in the
audiotactile PPS literature ledger. It proves that a profile row can declare
which trial event an external system should synchronize to, and that the
contract survives prepared block CSVs, trigger dictionaries, local marker CSVs,
local XDF mirrors, participant rows, and analysis rows.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_ready_profile_runner_smoke as runner_smoke  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-external-trigger-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_external_trigger_contract_20260715"
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "external event-trigger metadata. It verifies deterministic trial trigger "
    "keys/codes, local marker CSV/XDF output, participant rows, analysis rows, "
    "and mouse-click simulated responses. It is not EEG, TMS, fMRI, iEEG, sleep "
    "recorder, hardware TTL, LabRecorder, or physiological endpoint validation."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "external_event_trigger_sync_contract",
    "example_record_ids": [
        "serino_2009_tms",
        "avenanti_2012_motor_cortex",
        "ronga_2021_newborn_erp",
        "spadone_2021_connectivity",
        "interoception_exteroception_2025",
    ],
    "supported_contract": {
        "external_trigger_required": True,
        "external_trigger_modality": "EEG/TMS/fMRI/iEEG/sleep",
        "external_trigger_role": "trial_start | looming_onset | tactile_onset | response_window_onset | trial_end",
        "external_trigger_channel": "PPSMarkersV2 + PPSTriggerCodes local mirror",
    },
    "remaining_boundary": "paper-specific physiology apparatus setup and physical trigger/recorder validation",
}


def run_smoke(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_fixture(output_dir, participant_id=participant_id)
    package = prepare_segment_run_package(run_manifest, participant_id=participant_id, use_block_cache=False)
    engine = runner_smoke.FastProfileSmokeAudioEngine(max_clicks_per_block=100, response_delay_s=0.0)
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options=SessionCaptureOptions(
            enable_lsl=False,
            write_events_csv=True,
            write_internal_xdf=True,
            write_analysis_csvs=True,
            write_lsl_marker_mirror=True,
            write_trigger_dictionary=True,
            start_backup_recording=False,
            start_external_labrecorder=False,
        ),
        enable_topup=False,
        instruction_continue_callback=lambda _context: True,
        runner_metadata={"participant_code": participant_id},
    )

    def _click_after_tactile(_payload: dict[str, Any]) -> None:
        controller.events.flush_callback_events(timeout_s=0.5)
        time.sleep(0.12)
        controller.log_click(x=320, y=240, in_target=True)

    engine.set_tactile_callback(_click_after_tactile)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)

    block_rows = [row for block in package.blocks for row in _read_csv(block.manifest_path)]
    events = _read_csv(result.events_csv)
    markers = _read_csv(result.lsl_markers_csv or Path())
    participant_rows = _read_csv(result.analysis_outputs.get("participant_trials", Path()))
    analysis_rows = _read_csv(result.analysis_outputs.get("analysis_ready_trials", Path()))
    trigger_dictionary = _read_json(result.trigger_dictionary_path or Path())
    criteria = {
        "completed": bool(result.completed and not result.interrupted),
        "prepared_rows_preserve_external_trigger_contract": _prepared_rows_preserve_contract(block_rows),
        "marker_payloads_preserve_external_trigger_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_external_trigger_contract": _trigger_dictionary_preserves_contract(
            trigger_dictionary
        ),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_preserve_external_trigger_contract": _participant_rows_preserve_contract(participant_rows),
        "analysis_rows_preserve_external_trigger_contract": _analysis_rows_preserve_contract(analysis_rows),
        "mouse_clicks_logged_for_tactile_rows": _event_counts(events).get("mouse_click", 0) == 2,
        "response_markers_logged_for_tactile_rows": _event_counts(events).get("response_marker_start", 0) == 2,
    }
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "source_parameter_target": SOURCE_PARAMETER_TARGET,
        "run_setup_manifest": str(run_manifest),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "block_count": len(package.blocks),
        "block_row_family_counts": _family_counts(block_rows),
        "event_counts": _event_counts(events),
        "marker_event_counts": _event_counts(markers),
        "participant_trial_count": len(participant_rows),
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_ready_trials": str(result.analysis_outputs.get("analysis_ready_trials", "")),
        "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
        "trigger_dictionary_path": str(result.trigger_dictionary_path or ""),
        "lsl_markers_csv": str(result.lsl_markers_csv or ""),
        "lsl_markers_xdf": str(result.lsl_markers_xdf or ""),
        "events_xdf": str(result.events_xdf),
        "report_json": str(output_dir / "external_trigger_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "external_trigger_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "external_trigger_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_wav = _write_wav(stim_root / "looming_proxy.wav", duration_s=0.60)
    baseline_wav = _write_wav(stim_root / "baseline_proxy.wav", duration_s=0.45, gain=0.0)
    rows = [
        _row(
            1,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.60,
            soa_ms=200.0,
            tactile_onset_s=0.200,
            trigger_role="tactile_onset",
            trigger_code="EEG_TACTILE_TARGET",
            label="EEG tactile target trigger",
        ),
        _row(
            2,
            family="baseline",
            wav_path=baseline_wav,
            duration_s=0.45,
            soa_ms=0.0,
            tactile_onset_s=0.100,
            trigger_role="tactile_onset",
            trigger_code="EEG_BASELINE_TACTILE",
            label="EEG tactile-only baseline trigger",
        ),
        _row(
            3,
            family="catch",
            wav_path=audio_wav,
            duration_s=0.60,
            soa_ms=0.0,
            tactile_onset_s=None,
            trigger_role="looming_onset",
            trigger_code="EEG_AUDIO_ONLY_CATCH",
            label="EEG auditory-only catch trigger",
        ),
    ]
    block_csv = block_root / "block_01_final.csv"
    _write_csv(block_csv, rows, list(rows[0].keys()))
    block_manifest = block_root / "block_csv_preview_manifest.json"
    _write_json(
        block_manifest,
        {
            "schema": "pps-block-csv-preview.v1",
            "accepted": True,
            "blocks": [
                {
                    "block_index": 1,
                    "csv_path": str(block_csv),
                    "csv_file_name": block_csv.name,
                    "trial_count": len(rows),
                }
            ],
        },
    )
    order_csv = run_root / "experiment_block_order.csv"
    _write_csv(
        order_csv,
        [
            {
                "participant_id": participant_id,
                "participant_index": 1,
                "experiment_structure": "single",
                "phase": "single",
                "phase_label": "Single",
                "phase_index": 1,
                "participant_block_position": 1,
                "source_block_index": 1,
                "block_label": "External trigger contract validation",
                "block_csv_file": block_csv.name,
                "block_csv_path": str(block_csv),
                "trial_count": len(rows),
                "duration_ms": int(sum(float(row["duration_s"]) for row in rows) * 1000.0),
                "sequence_seed": 20260715,
            }
        ],
        [
            "participant_id",
            "participant_index",
            "experiment_structure",
            "phase",
            "phase_label",
            "phase_index",
            "participant_block_position",
            "source_block_index",
            "block_label",
            "block_csv_file",
            "block_csv_path",
            "trial_count",
            "duration_ms",
            "sequence_seed",
        ],
    )
    run_manifest = run_root / "experiment_run_setup_manifest.json"
    _write_json(
        run_manifest,
        {
            "schema": "pps-experiment-run-setup.v1",
            "status": "prepared",
            "prepared": True,
            "csv_path": str(order_csv),
            "experiment_structure": "single",
            "participant_count": 1,
            "parts_per_participant": 1,
            "blocks_per_part": 1,
            "total_block_runs": 1,
            "seed": 20260715,
            "source_segment5_manifest": str(block_manifest),
            "source_segment5_manifest_sha256": _sha256(block_manifest),
        },
    )
    return run_manifest


def _row(
    index: int,
    *,
    family: str,
    wav_path: Path,
    duration_s: float,
    soa_ms: float,
    tactile_onset_s: float | None,
    trigger_role: str,
    trigger_code: str,
    label: str,
) -> dict[str, Any]:
    has_tactile = family in {"audio_tactile", "baseline"}
    return {
        "block_trial_index": index,
        "family": family,
        "row_label": label,
        "noise_type": "sync_contract_proxy",
        "soa_ms": f"{soa_ms:g}",
        "sequence_labels": label,
        "sequence_variant_key": f"sync_contract_{family}_{index}",
        "source_file_name": wav_path.name,
        "trial_file_path": str(wav_path),
        "source_sha256": _sha256(wav_path),
        "duration_ms": int(round(duration_s * 1000.0)),
        "duration_s": f"{duration_s:.9f}",
        "looming_segment_onset_s": "0.000000000" if family in {"audio_tactile", "catch"} else "",
        "tactile_onset_s": "" if tactile_onset_s is None else f"{tactile_onset_s:.9f}",
        "channels": 3,
        "expected_response": "respond" if has_tactile else "withhold",
        "response_rule": "respond_to_tactile_target" if has_tactile else "withhold_response",
        "target_role": "target" if has_tactile else "no_target",
        "external_trigger_required": "true",
        "external_trigger_modality": "EEG",
        "external_trigger_role": trigger_role,
        "external_trigger_code": trigger_code,
        "external_trigger_tolerance_ms": "5",
        "external_trigger_channel": "PPSMarkersV2+PPSTriggerCodes",
    }


def _write_wav(path: Path, *, duration_s: float, gain: float = 0.02, sample_rate: int = 44100) -> Path:
    frames = int(round(duration_s * sample_rate))
    t = np.arange(frames, dtype=np.float32) / float(sample_rate)
    left = np.sin(2.0 * np.pi * 440.0 * t) * gain
    right = np.sin(2.0 * np.pi * 660.0 * t) * gain
    tactile = np.zeros(frames, dtype=np.float32)
    data = np.column_stack([left, right, tactile]).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sample_rate)
    return path


def _prepared_rows_preserve_contract(rows: list[dict[str, str]]) -> bool:
    return len(rows) == 3 and all(_row_has_contract(row, prefix="External_Trigger_") for row in rows)


def _marker_payloads_preserve_contract(rows: list[dict[str, str]]) -> bool:
    matches = 0
    for row in rows:
        try:
            payload = json.loads(row.get("payload_json") or "{}")
        except json.JSONDecodeError:
            continue
        event_type = row.get("event_type", "")
        if _role_matches_event(payload, event_type) and _row_has_contract(payload, prefix="external_trigger_"):
            matches += 1
    return matches >= 3


def _trigger_dictionary_preserves_contract(payload: dict[str, Any]) -> bool:
    matches = 0
    for trigger in payload.get("triggers", []):
        if not isinstance(trigger, dict):
            continue
        if _role_matches_event(trigger, str(trigger.get("event_type") or "")) and _row_has_contract(
            trigger,
            prefix="external_trigger_",
        ):
            matches += 1
    return matches >= 3


def _participant_rows_preserve_contract(rows: list[dict[str, str]]) -> bool:
    return len(rows) == 3 and all(_row_has_contract(row, prefix="external_trigger_") for row in rows)


def _analysis_rows_preserve_contract(rows: list[dict[str, str]]) -> bool:
    tactile_rows = [
        row
        for row in rows
        if str(row.get("family") or row.get("Family") or "").strip().lower() in {"audio_tactile", "baseline"}
    ]
    return len(tactile_rows) == 2 and all(_row_has_contract(row, prefix="external_trigger_") for row in tactile_rows)


def _role_matches_event(row: dict[str, Any], event_type: str) -> bool:
    role = str(row.get("external_trigger_role") or row.get("External_Trigger_Role") or "").strip()
    code = str(row.get("external_trigger_code") or row.get("External_Trigger_Code") or "").strip()
    required = str(row.get("external_trigger_required") or row.get("External_Trigger_Required") or "").lower()
    return bool(role and code and required in {"true", "1", "yes"} and role == event_type)


def _row_has_contract(row: dict[str, Any], *, prefix: str) -> bool:
    return (
        str(row.get(f"{prefix}required") or row.get(f"{prefix}Required") or "").lower() in {"true", "1", "yes"}
        and str(row.get(f"{prefix}modality") or row.get(f"{prefix}Modality") or "").strip() == "EEG"
        and str(row.get(f"{prefix}role") or row.get(f"{prefix}Role") or "").strip()
        in {"tactile_onset", "looming_onset"}
        and str(row.get(f"{prefix}code") or row.get(f"{prefix}Code") or "").strip().startswith("EEG_")
        and str(row.get(f"{prefix}channel") or row.get(f"{prefix}Channel") or "").strip()
        == "PPSMarkersV2+PPSTriggerCodes"
    )


def _family_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        family = str(row.get("Family") or row.get("family") or "").strip().lower()
        if family:
            counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _event_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        event_type = str(row.get("event_type") or "")
        if event_type:
            counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items()))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path | str) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# External Trigger Contract Capability Smoke",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Block rows: `{report['block_row_family_counts']}`",
        f"- Trigger dictionary: `{report['trigger_dictionary_path']}`",
        f"- Mouse clicks: `{report['event_counts'].get('mouse_click', 0)}`",
        "",
        EVIDENCE_BOUNDARY,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args(argv)
    report = run_smoke(output_dir=args.output_dir, participant_id=args.participant_id)
    print(json.dumps({"passed": report["passed"], "report_json": report["report_json"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
