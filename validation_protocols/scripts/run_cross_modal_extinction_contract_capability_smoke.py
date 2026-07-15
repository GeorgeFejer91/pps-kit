"""Validate cross-modal extinction tactile-report response contracts.

This smoke targets early audiotactile PPS/extinction studies where the
participant report is not a simple detection RT but a tactile percept report
such as left, right, bilateral, or none. It builds a tiny Segment 5/6-style
fixture, declares the parsimonious response-report fields in the rows, runs the
real SessionRunnerController path, and scores simulated participant-like mouse
clicks through quadrant mapping.
"""

from __future__ import annotations

import argparse
import csv
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
    _lower,
    _payload,
    _read_csv,
    _read_json,
    _sha256,
    _truthy,
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


SCHEMA = "pps-cross-modal-extinction-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_cross_modal_extinction_contract_20260715"
)
CONTRACT_FIELDS = {
    "response_mode": "Response_Mode",
    "response_choice_set": "Response_Choice_Set",
    "correct_response": "Correct_Response",
    "response_scoring_policy": "Response_Scoring_Policy",
    "response_rule": "Response_Rule",
    "target_role": "Target_Role",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "auditory-tactile extinction tactile-report mapping. It verifies prepared "
    "block CSVs, deterministic trial trigger metadata, local marker CSV/XDF "
    "output, participant rows, analysis rows, software wired-loopback sidecars, "
    "and mouse-click simulated participant-like percept reports. It is not "
    "clinical neglect/extinction behavior, patient evidence, tactile perception, "
    "physical timing loopback, exact original apparatus reconstruction, or "
    "scientific PPS-effect replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "cross_modal_extinction_response_mapping",
    "example_record_ids": [
        "ladavas_2001_auditory_tactile_extinction",
        "farne_ladavas_2002_auditory_pps_humans",
    ],
    "supported_contract": {
        "response_mode": "cross_modal_extinction_report",
        "response_choice_set": "paper-reported tactile percept alternatives such as left|right|bilateral|none",
        "correct_response": "paper-reported expected percept/report label for the row",
        "response_scoring_policy": "mouse_quadrant_extinction_report for emulated runs",
        "response_rule": "row-level auditory-tactile tactile-report rule",
        "target_role": "paper-specific tactile target and auditory distractor role labels",
    },
    "remaining_boundary": (
        "paper-specific patient/healthy-control procedures, physical response "
        "mapping, tactile perception, and clinical extinction behavior remain "
        "outside this software contract smoke"
    ),
}
CLICK_BY_REPORT = {
    "left": (250, 250),
    "right": (750, 250),
    "bilateral": (250, 750),
    "none": (750, 750),
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

    def _click_for_extinction_report(payload: dict[str, Any]) -> None:
        expected = _lower(_first(payload, "correct_response", "Correct_Response"))
        coords = CLICK_BY_REPORT.get(expected)
        if coords is None:
            return
        controller.events.flush_callback_events(timeout_s=0.5)
        time.sleep(engine.response_delay_s)
        controller.log_click(x=coords[0], y=coords[1], in_target=True)

    engine.set_tactile_callback(_click_for_extinction_report)
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
        "prepared_rows_preserve_cross_modal_extinction_contract": _rows_preserve_contract(
            block_rows,
            expected_count=4,
        ),
        "marker_payloads_preserve_cross_modal_extinction_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_cross_modal_extinction_contract": _trigger_dictionary_preserves_contract(
            trigger_dictionary
        ),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_score_cross_modal_extinction_contract": _rows_score_choices(
            participant_rows,
            expected_count=4,
        ),
        "analysis_rows_score_cross_modal_extinction_contract": _rows_score_choices(
            analysis_rows,
            expected_count=4,
        ),
        "mouse_clicks_logged_for_extinction_rows": _event_counts(events).get("mouse_click", 0) == 4,
        "response_markers_logged_for_extinction_rows": _event_counts(events).get("response_marker_start", 0)
        == 4,
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
        "block_row_response_modes": _count_values(block_rows, "Response_Mode"),
        "block_row_correct_responses": _count_values(block_rows, "Correct_Response"),
        "event_counts": _event_counts(events),
        "marker_event_counts": _event_counts(markers),
        "participant_trial_count": len(participant_rows),
        "analysis_ready_trial_count": len(analysis_rows),
        "participant_choice_counts": _count_values(participant_rows, "observed_response_choice"),
        "analysis_choice_counts": _count_values(analysis_rows, "observed_response_choice"),
        "software_wired_loopback": str(loopback_path),
        "analysis_ready_trials": str(result.analysis_outputs.get("analysis_ready_trials", "")),
        "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
        "trigger_dictionary_path": str(result.trigger_dictionary_path or ""),
        "lsl_markers_csv": str(result.lsl_markers_csv or ""),
        "lsl_markers_xdf": str(result.lsl_markers_xdf or ""),
        "events_xdf": str(result.events_xdf),
        "report_json": str(output_dir / "cross_modal_extinction_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "cross_modal_extinction_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "cross_modal_extinction_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_wav = _write_wav(stim_root / "cross_modal_extinction_proxy.wav", duration_s=0.56)
    rows = [
        _row(
            1,
            wav_path=audio_wav,
            duration_s=0.56,
            soa_ms=120.0,
            tactile_onset_s=0.120,
            correct_response="left",
            body_side="left",
            target_role="left_tactile_target_with_right_auditory_distractor",
            label="Extinction report left tactile percept",
        ),
        _row(
            2,
            wav_path=audio_wav,
            duration_s=0.56,
            soa_ms=180.0,
            tactile_onset_s=0.180,
            correct_response="right",
            body_side="right",
            target_role="right_tactile_target_with_left_auditory_distractor",
            label="Extinction report right tactile percept",
        ),
        _row(
            3,
            wav_path=audio_wav,
            duration_s=0.56,
            soa_ms=240.0,
            tactile_onset_s=0.240,
            correct_response="bilateral",
            body_side="bilateral",
            target_role="bilateral_tactile_report_target",
            label="Extinction report bilateral tactile percept",
        ),
        _row(
            4,
            wav_path=audio_wav,
            duration_s=0.56,
            soa_ms=300.0,
            tactile_onset_s=0.300,
            correct_response="none",
            body_side="bilateral",
            target_role="auditory_distractor_with_no_tactile_percept_report",
            label="Extinction report no tactile percept",
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
                "block_label": "Cross-modal extinction response-report contract validation",
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
    wav_path: Path,
    duration_s: float,
    soa_ms: float,
    tactile_onset_s: float,
    correct_response: str,
    body_side: str,
    target_role: str,
    label: str,
) -> dict[str, str]:
    return {
        "block_trial_index": str(trial_number),
        "trial_pool_index": str(trial_number),
        "family": "audio_tactile",
        "trial_type": "Audio-Tactile",
        "row_label": label,
        "noise_type": "auditory_distractor",
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
        "spatial_coordinate_frame": "body_part_anchored",
        "body_anchor": "head",
        "body_part": "hand",
        "body_side": body_side,
        "spatial_hemifield": body_side,
        "body_relative_axis": "left_right",
        "expected_response": "respond",
        "response_rule": "report perceived tactile side during auditory-tactile extinction row",
        "target_role": target_role,
        "response_mode": "cross_modal_extinction_report",
        "response_choice_set": "left|right|bilateral|none",
        "correct_response": correct_response,
        "response_scoring_policy": "mouse_quadrant_extinction_report",
        "primary_analysis_included": "true",
        "configured_repetitions": "1",
        "repetition_index": "1",
        "fractional_extra": "0",
    }


def _rows_preserve_contract(rows: list[dict[str, Any]], *, expected_count: int) -> bool:
    return len(rows) == expected_count and all(_row_has_contract(row) for row in rows)


def _rows_score_choices(rows: list[dict[str, Any]], *, expected_count: int) -> bool:
    if len(rows) != expected_count:
        return False
    if not all(_row_has_contract(row) for row in rows):
        return False
    for row in rows:
        expected = _lower(_first(row, "correct_response", "Correct_Response"))
        observed = _lower(_first(row, "observed_response_choice", "Observed_Response_Choice"))
        if not expected or observed != expected:
            return False
        if not _truthy(_first(row, "response_choice_correct", "Response_Choice_Correct")):
            return False
        if str(_first(row, "outcome", "Outcome", "hit", "Hit")).strip().lower() not in {"hit", "true"}:
            return False
    return True


def _marker_payloads_preserve_contract(rows: list[dict[str, Any]]) -> bool:
    choices: set[str] = set()
    modes: set[str] = set()
    for row in rows:
        payload = _payload(row)
        event_type = str(
            row.get("event_type") or row.get("Event_Type") or payload.get("event_type") or payload.get("Event_Type") or ""
        ).strip()
        if event_type not in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end"}:
            continue
        if not _row_has_contract(payload):
            continue
        choices.add(str(payload.get("correct_response") or payload.get("Correct_Response") or "").strip())
        modes.add(str(payload.get("response_mode") or payload.get("Response_Mode") or "").strip())
    return choices == {"left", "right", "bilateral", "none"} and modes == {"cross_modal_extinction_report"}


def _trigger_dictionary_preserves_contract(data: dict[str, Any]) -> bool:
    triggers = data.get("triggers") if isinstance(data, dict) else None
    if not isinstance(triggers, list):
        return False
    choices = {
        str(item.get("correct_response") or item.get("Correct_Response") or "").strip()
        for item in triggers
        if isinstance(item, dict) and str(item.get("trigger_key") or "").startswith("trial:") and _row_has_contract(item)
    }
    return choices == {"left", "right", "bilateral", "none"}


def _row_has_contract(row: dict[str, Any]) -> bool:
    for lower, title in CONTRACT_FIELDS.items():
        value = row.get(lower, row.get(title, ""))
        if value in (None, ""):
            return False
    return True


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Cross-Modal Extinction Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Block rows: `{report['block_row_family_counts']}`",
        f"- Response modes: `{report['block_row_response_modes']}`",
        f"- Correct responses: `{report['block_row_correct_responses']}`",
        f"- Participant choices: `{report['participant_choice_counts']}`",
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
