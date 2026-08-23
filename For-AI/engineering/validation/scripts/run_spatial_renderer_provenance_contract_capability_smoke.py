"""Validate row-level spatial renderer/HRTF provenance metadata through the runner."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
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


SCHEMA = "pps-spatial-renderer-provenance-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / (
    "current_goal_spatial_renderer_provenance_contract_20260715"
)
CONTRACT_FIELDS = {
    "spatial_renderer_engine": "Spatial_Renderer_Engine",
    "spatial_renderer_version": "Spatial_Renderer_Version",
    "hrtf_database": "HRTF_Database",
    "hrtf_subject_id": "HRTF_Subject_ID",
    "hrtf_filter_id": "HRTF_Filter_ID",
    "hrtf_near_field_compensation": "HRTF_Near_Field_Compensation",
    "source_asset_equivalence": "Source_Asset_Equivalence",
    "renderer_equivalence_boundary": "Renderer_Equivalence_Boundary",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "spatial renderer and HRTF provenance metadata. It verifies prepared block "
    "CSVs, marker payloads, trigger dictionaries, local marker XDF mirrors, "
    "participant rows, analysis rows, software wired-loopback sidecars, and "
    "mouse-click simulated participant-like responses. It is not bit-matched "
    "MATLAB or HRTF rendering, not physical speaker/headphone spatialization "
    "validation, not room-acoustic calibration, not collected participant "
    "behavior, not physical timing loopback, and not scientific PPS-effect "
    "replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "hrtf_database_or_binaural_engine_mismatch",
    "example_record_ids": ["looming_duration_2025"],
    "supported_contract": {
        "spatial_renderer_engine": "paper/toolkit renderer family or named software engine",
        "spatial_renderer_version": "paper/toolkit renderer version when reported",
        "hrtf_database": "paper-reported HRTF database or declared unresolved value",
        "hrtf_subject_id": "paper-reported HRTF listener/subject/filter identity",
        "hrtf_filter_id": "paper-reported filter/profile identifier",
        "hrtf_near_field_compensation": "paper/toolkit near-field compensation state",
        "source_asset_equivalence": "bitmatched/proxy/unresolved source equivalence status",
        "renderer_equivalence_boundary": "explicit boundary for unvalidated spatialization equivalence",
    },
    "remaining_boundary": (
        "exact original MATLAB HRTF/right-lateral renderer implementation and source equivalence "
        "still need source extraction or physical/acoustic validation before exact-profile claims"
    ),
}


def run_smoke(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_fixture(output_dir, participant_id=participant_id)
    package = prepare_segment_run_package(run_manifest, participant_id=participant_id, use_block_cache=False)
    engine = ResponseChoiceSmokeAudioEngine(max_clicks_per_block=100, response_delay_s=0.08)
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
        controller.log_click(x=430, y=250, in_target=True)

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
        "prepared_rows_preserve_spatial_renderer_contract": _rows_preserve_contract(block_rows, expected_count=3),
        "marker_payloads_preserve_spatial_renderer_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_spatial_renderer_contract": _trigger_dictionary_preserves_contract(
            trigger_dictionary
        ),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_preserve_spatial_renderer_contract": _rows_preserve_contract(
            participant_rows,
            expected_count=3,
        ),
        "analysis_rows_preserve_spatial_renderer_contract": _rows_preserve_contract(
            analysis_rows,
            expected_count=2,
        ),
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
        "block_row_renderer_engines": _count_values(block_rows, "Spatial_Renderer_Engine"),
        "block_row_hrtf_databases": _count_values(block_rows, "HRTF_Database"),
        "block_row_source_equivalence": _count_values(block_rows, "Source_Asset_Equivalence"),
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
        "report_json": str(output_dir / "spatial_renderer_provenance_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "spatial_renderer_provenance_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "spatial_renderer_provenance_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_2s = _write_wav(stim_root / "right_lateral_hrtf_proxy_2s.wav", duration_s=0.60, gain=0.035)
    audio_3s = _write_wav(stim_root / "right_lateral_hrtf_proxy_3s.wav", duration_s=0.70, gain=0.035)
    rows = [
        _row(
            1,
            family="audio_tactile",
            wav_path=audio_2s,
            duration_s=0.60,
            soa_ms=375,
            tactile_onset_s=0.375,
            variant_key="duration_2s_right_lateral_proxy",
            label="2 s right-lateral HRTF provenance proxy row",
        ),
        _row(
            2,
            family="audio_tactile",
            wav_path=audio_3s,
            duration_s=0.70,
            soa_ms=562.5,
            tactile_onset_s=0.5625,
            variant_key="duration_3s_right_lateral_proxy",
            label="3 s right-lateral HRTF provenance proxy row",
        ),
        _row(
            3,
            family="catch",
            wav_path=audio_3s,
            duration_s=0.70,
            soa_ms=0,
            tactile_onset_s=None,
            variant_key="duration_3s_right_lateral_auditory_only_catch",
            label="Auditory-only HRTF provenance catch row",
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
                "block_label": "Spatial renderer provenance contract validation",
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
    tactile_onset_s: float | None,
    variant_key: str,
    label: str,
) -> dict[str, str]:
    has_tactile = family != "catch"
    return {
        "block_trial_index": str(trial_number),
        "trial_pool_index": str(trial_number),
        "family": family,
        "trial_type": "Audio-Tactile" if has_tactile else "Catch",
        "row_label": label,
        "noise_type": "right_lateral_hrtf_proxy",
        "soa_ms": f"{soa_ms:g}",
        "source_file_name": wav_path.name,
        "trial_file_path": str(wav_path),
        "source_sha256": _sha256(wav_path),
        "duration_ms": str(int(round(duration_s * 1000))),
        "duration_s": f"{duration_s:.6f}",
        "looming_segment_onset_s": "0.000",
        "tactile_onset_s": "" if tactile_onset_s is None else f"{tactile_onset_s:.6f}",
        "channels": "2",
        "tactile_channel": "3",
        "spatial_coordinate_frame": "body_relative",
        "body_anchor": "trunk",
        "body_part": "trunk",
        "body_side": "right",
        "spatial_hemifield": "right",
        "body_relative_axis": "right_lateral",
        "auditory_trajectory_family": "right_lateral_looming_duration_profile",
        "auditory_trajectory_direction": "right_lateral_approach",
        "trajectory_coordinate_frame": "body_relative",
        "trajectory_start_hemifield": "right_far",
        "trajectory_end_hemifield": "right_near",
        "trajectory_start_distance_cm": "150",
        "trajectory_end_distance_cm": "0",
        "trajectory_start_azimuth_deg": "90",
        "trajectory_end_azimuth_deg": "90",
        "spatial_renderer_engine": "original_matlab_hrtf_renderer",
        "spatial_renderer_version": "source_unresolved",
        "hrtf_database": "paper_reported_or_unresolved_hrtf_database",
        "hrtf_subject_id": "unreported",
        "hrtf_filter_id": "right_lateral_profile",
        "hrtf_near_field_compensation": "unresolved",
        "source_asset_equivalence": "proxy_binaural_runner_smoke_not_bitmatched",
        "renderer_equivalence_boundary": "metadata_preserved_no_physical_hrtf_equivalence",
        "expected_response": "respond" if has_tactile else "withhold",
        "response_rule": "detect tactile target on renderer-provenance row",
        "target_role": "target" if has_tactile else "catch",
        "primary_analysis_included": "true" if has_tactile else "false",
        "sequence_variant_key": variant_key,
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
    variants: set[str] = set()
    for row in rows:
        payload = _payload(row)
        event_type = str(
            row.get("event_type") or row.get("Event_Type") or payload.get("event_type") or payload.get("Event_Type") or ""
        ).strip()
        if event_type not in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end"}:
            continue
        if _row_has_contract(payload):
            variants.add(str(payload.get("sequence_variant_key") or payload.get("Sequence_Variant_Key") or ""))
    return {
        "duration_2s_right_lateral_proxy",
        "duration_3s_right_lateral_proxy",
        "duration_3s_right_lateral_auditory_only_catch",
    }.issubset(variants)


def _trigger_dictionary_preserves_contract(data: dict[str, Any]) -> bool:
    triggers = data.get("triggers") if isinstance(data, dict) else None
    if not isinstance(triggers, list):
        return False
    labels = {
        str(item.get("row_label") or item.get("Row_Label") or "")
        for item in triggers
        if isinstance(item, dict) and str(item.get("trigger_key") or "").startswith("trial:") and _row_has_contract(item)
    }
    return {
        "2 s right-lateral HRTF provenance proxy row",
        "3 s right-lateral HRTF provenance proxy row",
        "Auditory-only HRTF provenance catch row",
    }.issubset(labels)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Spatial Renderer Provenance Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Renderer engines: `{report['block_row_renderer_engines']}`",
        f"- HRTF databases: `{report['block_row_hrtf_databases']}`",
        f"- Source equivalence: `{report['block_row_source_equivalence']}`",
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
