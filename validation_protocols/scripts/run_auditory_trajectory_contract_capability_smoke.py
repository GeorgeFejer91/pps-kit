"""Validate row-level auditory trajectory-family metadata through the runner."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_ready_profile_runner_smoke as runner_smoke  # noqa: E402
from run_response_choice_contract_capability_smoke import (  # noqa: E402
    ResponseChoiceSmokeAudioEngine,
    _count_values,
    _event_counts,
    _family_counts,
    _first,
    _payload,
    _read_csv,
    _read_json,
    _sha256,
    _write_csv,
    _write_json,
    _write_wav,
)
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-auditory-trajectory-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_auditory_trajectory_contract_20260715"
CONTRACT_FIELDS = {
    "auditory_trajectory_family": "Auditory_Trajectory_Family",
    "auditory_trajectory_direction": "Auditory_Trajectory_Direction",
    "trajectory_coordinate_frame": "Trajectory_Coordinate_Frame",
    "trajectory_start_hemifield": "Trajectory_Start_Hemifield",
    "trajectory_end_hemifield": "Trajectory_End_Hemifield",
    "trajectory_start_distance_cm": "Trajectory_Start_Distance_cm",
    "trajectory_end_distance_cm": "Trajectory_End_Distance_cm",
    "trajectory_start_azimuth_deg": "Trajectory_Start_Azimuth_deg",
    "trajectory_end_azimuth_deg": "Trajectory_End_Azimuth_deg",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "auditory trajectory-family metadata. It verifies prepared block CSVs, "
    "marker payloads, trigger dictionaries, local marker XDF mirrors, "
    "participant rows, analysis rows, software wired-loopback sidecars, and "
    "mouse-click simulated participant-like responses. It is not physical "
    "speaker or HRTF spatialization validation, exact front/rear apparatus "
    "reconstruction, room-acoustic calibration, physical timing loopback, "
    "collected participant behavior, or scientific PPS-effect replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "rear_hemifield_trajectory_families",
    "example_record_ids": ["amiel_2025_front_rear"],
    "supported_contract": {
        "auditory_trajectory_family": "paper-level trajectory family such as front_rear_distance_profile",
        "auditory_trajectory_direction": "row-level direction such as front_to_rear or rear_to_front",
        "trajectory_coordinate_frame": "body_relative, room_relative, or paper-declared frame",
        "trajectory_start_hemifield": "front, rear, left, right, or paper-specific hemifield",
        "trajectory_end_hemifield": "front, rear, left, right, or paper-specific hemifield",
        "trajectory_start_distance_cm": "paper-reported or derived start distance",
        "trajectory_end_distance_cm": "paper-reported or derived end distance",
        "trajectory_start_azimuth_deg": "paper/body-relative start azimuth when available",
        "trajectory_end_azimuth_deg": "paper/body-relative end azimuth when available",
    },
    "remaining_boundary": (
        "paper-specific front/rear spatialization method, distance levels, tactile timing, "
        "and exact body-relative mappings still need source extraction before profile creation"
    ),
}


def run_smoke(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_fixture(output_dir, participant_id=participant_id)
    package = prepare_segment_run_package(run_manifest, participant_id=participant_id, use_block_cache=False)
    engine = ResponseChoiceSmokeAudioEngine(max_clicks_per_block=100, response_delay_s=0.12)
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
            wired_loopback_mode=WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
            start_external_labrecorder=False,
        ),
        enable_topup=False,
        instruction_continue_callback=lambda _context: True,
        runner_metadata={"participant_code": participant_id},
    )

    def _click_after_tactile(_payload: dict[str, Any]) -> None:
        controller.events.flush_callback_events(timeout_s=0.5)
        time.sleep(engine.response_delay_s)
        controller.log_click(x=460, y=260, in_target=True)

    engine.set_tactile_callback(_click_after_tactile)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)

    block_rows = [row for block in package.blocks for row in _read_csv(block.manifest_path)]
    events = _read_csv(result.events_csv)
    markers = _read_csv(result.lsl_markers_csv or Path())
    participant_rows = _read_csv(result.analysis_outputs.get("participant_trials", Path()))
    analysis_rows = _read_csv(result.analysis_outputs.get("analysis_ready_trials", Path()))
    trigger_dictionary = _read_json(result.trigger_dictionary_path or Path())
    loopback_path = package.session_dir / "block_01_wired_loopback_input4.wav"
    criteria = {
        "completed": bool(result.completed and not result.interrupted),
        "block_wav_generated": len(package.blocks) == 1 and package.blocks[0].wav_path.is_file(),
        "software_wired_loopback_written": loopback_path.is_file()
        and bool(runner_smoke._wav_facts(loopback_path).get("readable")),
        "prepared_rows_preserve_auditory_trajectory_contract": _rows_preserve_contract(block_rows, expected_count=3),
        "marker_payloads_preserve_auditory_trajectory_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_auditory_trajectory_contract": _trigger_dictionary_preserves_contract(
            trigger_dictionary
        ),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_preserve_auditory_trajectory_contract": _rows_preserve_contract(
            participant_rows,
            expected_count=3,
        ),
        "analysis_rows_preserve_auditory_trajectory_contract": _rows_preserve_contract(
            analysis_rows,
            expected_count=3,
        ),
        "mouse_clicks_logged_for_tactile_rows": _event_counts(events).get("mouse_click", 0) == 3,
        "response_markers_logged_for_tactile_rows": _event_counts(events).get("response_marker_start", 0) == 3,
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
        "block_row_trajectory_families": _count_values(block_rows, "Auditory_Trajectory_Family"),
        "block_row_trajectory_directions": _count_values(block_rows, "Auditory_Trajectory_Direction"),
        "block_row_start_hemifields": _count_values(block_rows, "Trajectory_Start_Hemifield"),
        "block_row_end_hemifields": _count_values(block_rows, "Trajectory_End_Hemifield"),
        "event_counts": _event_counts(events),
        "marker_event_counts": _event_counts(markers),
        "participant_trial_count": len(participant_rows),
        "analysis_ready_trial_count": len(analysis_rows),
        "software_wired_loopback": str(loopback_path),
        "analysis_ready_trials": str(result.analysis_outputs.get("analysis_ready_trials", "")),
        "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
        "trigger_dictionary_path": str(result.trigger_dictionary_path or ""),
        "lsl_markers_csv": str(result.lsl_markers_csv or ""),
        "lsl_markers_xdf": str(result.lsl_markers_xdf or ""),
        "events_xdf": str(result.events_xdf),
        "report_json": str(output_dir / "auditory_trajectory_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "auditory_trajectory_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "auditory_trajectory_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_wav = _write_wav(stim_root / "front_rear_trajectory_proxy.wav", duration_s=0.55, gain=0.04)
    baseline_wav = _write_wav(stim_root / "front_rear_tactile_baseline.wav", duration_s=0.45, gain=0.0)
    rows = [
        _row(
            1,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.55,
            soa_ms=180,
            tactile_onset_s=0.180,
            direction="front_to_rear",
            start_hemifield="front",
            end_hemifield="rear",
            start_distance_cm="120",
            end_distance_cm="30",
            start_azimuth_deg="0",
            end_azimuth_deg="180",
            label="Front-to-rear body-relative trajectory row",
        ),
        _row(
            2,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.55,
            soa_ms=300,
            tactile_onset_s=0.300,
            direction="rear_to_front",
            start_hemifield="rear",
            end_hemifield="front",
            start_distance_cm="120",
            end_distance_cm="30",
            start_azimuth_deg="180",
            end_azimuth_deg="0",
            label="Rear-to-front body-relative trajectory row",
        ),
        _row(
            3,
            family="baseline",
            wav_path=baseline_wav,
            duration_s=0.45,
            soa_ms=0,
            tactile_onset_s=0.140,
            direction="rear_static_baseline",
            start_hemifield="rear",
            end_hemifield="rear",
            start_distance_cm="30",
            end_distance_cm="30",
            start_azimuth_deg="180",
            end_azimuth_deg="180",
            label="Rear tactile-only baseline trajectory row",
        ),
    ]
    block_csv = block_root / "block_01_final.csv"
    _write_csv(block_csv, rows, list(rows[0].keys()))
    _write_json(
        block_root / "block_csv_preview_manifest.json",
        {
            "schema": "pps-block-csv-preview.v1",
            "accepted": True,
            "blocks": [{"block_index": 1, "csv_path": str(block_csv), "trial_count": len(rows)}],
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
                "block_label": "Auditory trajectory contract validation",
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
            "participants": [participant_id],
            "blocks": [{"block_index": 1, "csv_path": str(block_csv), "trial_count": len(rows)}],
        },
    )
    return run_manifest


def _row(
    trial_number: int,
    *,
    family: str,
    wav_path: Path,
    duration_s: float,
    soa_ms: float,
    tactile_onset_s: float,
    direction: str,
    start_hemifield: str,
    end_hemifield: str,
    start_distance_cm: str,
    end_distance_cm: str,
    start_azimuth_deg: str,
    end_azimuth_deg: str,
    label: str,
) -> dict[str, str]:
    return {
        "block_trial_index": str(trial_number),
        "trial_pool_index": str(trial_number),
        "family": family,
        "trial_type": "Audio-Tactile" if family == "audio_tactile" else "Baseline",
        "row_label": label,
        "noise_type": "front_rear_proxy" if family == "audio_tactile" else "tactile_only",
        "soa_ms": f"{soa_ms:.0f}",
        "source_file_name": wav_path.name,
        "trial_file_path": str(wav_path),
        "source_sha256": _sha256(wav_path),
        "duration_ms": str(int(round(duration_s * 1000))),
        "duration_s": f"{duration_s:.6f}",
        "looming_segment_onset_s": "0.000",
        "tactile_onset_s": f"{tactile_onset_s:.6f}",
        "channels": "2",
        "tactile_channel": "3",
        "spatial_coordinate_frame": "body_relative",
        "body_anchor": "trunk",
        "body_part": "trunk",
        "body_side": "midline",
        "spatial_hemifield": start_hemifield if family == "audio_tactile" else "rear",
        "body_relative_axis": "front_back",
        "auditory_trajectory_family": "front_rear_distance_profile",
        "auditory_trajectory_direction": direction,
        "trajectory_coordinate_frame": "body_relative",
        "trajectory_start_hemifield": start_hemifield,
        "trajectory_end_hemifield": end_hemifield,
        "trajectory_start_distance_cm": start_distance_cm,
        "trajectory_end_distance_cm": end_distance_cm,
        "trajectory_start_azimuth_deg": start_azimuth_deg,
        "trajectory_end_azimuth_deg": end_azimuth_deg,
        "expected_response": "respond",
        "response_rule": "detect tactile target on body-relative front/rear trajectory row",
        "target_role": "target",
        "primary_analysis_included": "true",
        "configured_repetitions": "1",
        "repetition_index": "1",
        "fractional_extra": "0",
    }


def _rows_preserve_contract(rows: list[dict[str, Any]], *, expected_count: int) -> bool:
    return len(rows) == expected_count and all(_row_has_contract(row) for row in rows)


def _row_has_contract(row: dict[str, Any]) -> bool:
    for lower, title in CONTRACT_FIELDS.items():
        value = _first(row, lower, title)
        if value in (None, ""):
            return False
    return True


def _marker_payloads_preserve_contract(rows: list[dict[str, Any]]) -> bool:
    directions: set[str] = set()
    for row in rows:
        payload = _payload(row)
        event_type = str(
            row.get("event_type") or row.get("Event_Type") or payload.get("event_type") or payload.get("Event_Type") or ""
        ).strip()
        if event_type not in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end"}:
            continue
        if _row_has_contract(payload):
            directions.add(str(payload.get("auditory_trajectory_direction") or payload.get("Auditory_Trajectory_Direction")))
    return {"front_to_rear", "rear_to_front", "rear_static_baseline"}.issubset(directions)


def _trigger_dictionary_preserves_contract(data: dict[str, Any]) -> bool:
    triggers = data.get("triggers") if isinstance(data, dict) else None
    if not isinstance(triggers, list):
        return False
    directions = {
        str(item.get("auditory_trajectory_direction") or item.get("Auditory_Trajectory_Direction") or "")
        for item in triggers
        if isinstance(item, dict) and str(item.get("trigger_key") or "").startswith("trial:") and _row_has_contract(item)
    }
    return {"front_to_rear", "rear_to_front", "rear_static_baseline"}.issubset(directions)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Auditory Trajectory Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Trajectory families: `{report['block_row_trajectory_families']}`",
        f"- Trajectory directions: `{report['block_row_trajectory_directions']}`",
        f"- Start hemifields: `{report['block_row_start_hemifields']}`",
        f"- End hemifields: `{report['block_row_end_hemifields']}`",
        f"- Event counts: `{report['event_counts']}`",
        "",
        "## Criteria",
    ]
    for key, value in report["criteria"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Evidence Boundary", "", report["evidence_boundary"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args()
    report = run_smoke(output_dir=args.output_dir, participant_id=args.participant_id)
    print(json.dumps({"passed": report["passed"], "report_json": report["report_json"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
