"""Validate audiovisual/trisensory row metadata through the runner."""

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


SCHEMA = "pps-audiovisual-trisensory-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / (
    "current_goal_audiovisual_trisensory_contract_20260715"
)
CONTRACT_FIELDS = {
    "multisensory_trial_family": "Multisensory_Trial_Family",
    "exteroceptive_modality_set": "Exteroceptive_Modality_Set",
    "visual_stimulus_type": "Visual_Stimulus_Type",
    "visual_motion_profile": "Visual_Motion_Profile",
    "visual_start_distance_cm": "Visual_Start_Distance_cm",
    "visual_end_distance_cm": "Visual_End_Distance_cm",
    "visual_speed_cm_s": "Visual_Speed_cm_s",
    "visual_duration_ms": "Visual_Duration_ms",
    "visual_renderer_engine": "Visual_Renderer_Engine",
    "visual_display_device": "Visual_Display_Device",
    "mixed_reality_context": "Mixed_Reality_Context",
    "body_rendering_mode": "Body_Rendering_Mode",
    "audiovisual_synchrony_policy": "Audiovisual_Synchrony_Policy",
    "mixed_reality_equivalence_boundary": "Mixed_Reality_Equivalence_Boundary",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "audiovisual, visual, and mixed-reality provenance metadata. It verifies "
    "prepared block CSVs, marker payloads, trigger dictionaries, local marker "
    "XDF mirrors, participant rows, analysis rows, generated audio/tactile WAV "
    "sidecars, software wired-loopback sidecars, and mouse-click simulated "
    "participant-like responses. It is not VR/HMD rendering, not physical "
    "mixed-reality synchronization, not visual stimulus presentation, not "
    "binaural capture equivalence, not collected participant behavior, not "
    "physical timing loopback, and not scientific PPS-effect replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "audiovisual_or_trisensory_trial_family",
    "example_record_ids": ["serino_2018_mixed_reality_pps"],
    "supported_contract": {
        "multisensory_trial_family": "audiovisuotactile, visuotactile, audiotactile, or unimodal baseline/catch family",
        "exteroceptive_modality_set": "visual, auditory, audiovisual, none, or paper-declared set",
        "visual_stimulus_type": "paper-reported visual object such as virtual looming ball",
        "visual_motion_profile": "paper-reported visual trajectory profile",
        "visual_start_distance_cm": "paper-reported visual start distance",
        "visual_end_distance_cm": "paper-reported visual end/contact distance",
        "visual_speed_cm_s": "paper-reported visual speed",
        "visual_duration_ms": "paper-reported visual movement duration",
        "visual_renderer_engine": "paper-reported visual/MR engine or declared unresolved value",
        "visual_display_device": "paper-reported HMD/display device",
        "mixed_reality_context": "paper-reported MR/VR scene context",
        "body_rendering_mode": "paper-reported own-body/avatar/body-rendering mode",
        "audiovisual_synchrony_policy": "paper-reported simultaneity or alignment policy",
        "mixed_reality_equivalence_boundary": "explicit boundary for unvalidated MR/visual equivalence",
    },
    "remaining_boundary": (
        "exact video/3D assets, ExpyVR/RealiSM scripts, physical HMD presentation, "
        "binaural source tracks, and exact temporal-delay table still need source "
        "extraction or apparatus validation before exact-profile claims"
    ),
}
PAPER_PARAMETER_BASIS = {
    "paper": "Serino et al. 2018 Frontiers in ICT, DOI 10.3389/fict.2017.00031",
    "source_url": "https://www.frontiersin.org/journals/ict/articles/10.3389/fict.2017.00031/pdf",
    "experiment_2_core_parameters": {
        "trial_family": "trimodal audiovisuotactile PPS task",
        "visual_object": "3D virtual tennis ball",
        "visual_path": "2 m approach toward face",
        "visual_speed_cm_s": 75,
        "visual_duration_ms": 2600,
        "dynamic_sound_policy": "same velocity and direction as the virtual ball, simultaneously presented",
        "sound_delivery": "pre-recorded binaural sounds via noise-canceling headphones",
        "tactile_site": "right cheek",
        "tactile_device": "MSTC-3 mechanical solenoid tapper",
        "tactile_duration_ms": 10,
        "delay_levels": 5,
        "trial_counts": "540 total: 12 trials per delay for each trimodal condition, 12 per delay for each unimodal condition, 60 catch; 4 blocks of 135",
    },
    "expected_outcome": (
        "Audiovisuotactile RTs become progressively faster at decreasing ball/sound "
        "distances; D1-D3 are faster than fastest tactile baseline while D4-D5 are not; "
        "PPS boundary lies between D3 and D4; average sigmoid central point is 105 cm; "
        "audiovisuotactile fitting has higher goodness-of-fit than visual-only fitting."
    ),
}


def run_smoke(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_fixture(output_dir, participant_id=participant_id)
    package = prepare_segment_run_package(run_manifest, participant_id=participant_id, use_block_cache=False)
    engine = ResponseChoiceSmokeAudioEngine(max_clicks_per_block=100, response_delay_s=0.10)
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
        controller.log_click(x=440, y=245, in_target=True)

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
        "prepared_rows_preserve_audiovisual_contract": _rows_preserve_contract(block_rows, expected_count=3),
        "marker_payloads_preserve_audiovisual_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_audiovisual_contract": _trigger_dictionary_preserves_contract(trigger_dictionary),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_preserve_audiovisual_contract": _rows_preserve_contract(
            participant_rows,
            expected_count=3,
        ),
        "analysis_rows_preserve_audiovisual_contract": _rows_preserve_contract(
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
        "paper_parameter_basis": PAPER_PARAMETER_BASIS,
        "run_setup_manifest": str(run_manifest),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "block_count": len(package.blocks),
        "block_row_family_counts": _family_counts(block_rows),
        "block_row_multisensory_families": _count_values(block_rows, "Multisensory_Trial_Family"),
        "block_row_exteroceptive_sets": _count_values(block_rows, "Exteroceptive_Modality_Set"),
        "block_row_visual_stimuli": _count_values(block_rows, "Visual_Stimulus_Type"),
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
        "report_json": str(output_dir / "audiovisual_trisensory_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "audiovisual_trisensory_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "audiovisual_trisensory_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    av_audio = _write_wav(stim_root / "serino_exp2_audiovisual_proxy.wav", duration_s=0.72, gain=0.035)
    tactile_baseline = _write_wav(stim_root / "serino_exp2_tactile_baseline_carrier.wav", duration_s=0.72, gain=0.0)
    catch_audio = _write_wav(stim_root / "serino_exp2_audiovisual_catch_proxy.wav", duration_s=0.72, gain=0.035)
    rows = [
        _row(
            1,
            family="audio_tactile",
            wav_path=av_audio,
            duration_s=0.72,
            soa_ms=390,
            tactile_onset_s=0.390,
            variant_key="serino_exp2_audiovisuotactile_d3_proxy",
            multisensory_family="audiovisuotactile",
            exteroceptive_set="auditory+visual",
            label="Serino Exp. 2 audiovisuotactile D3 proxy",
        ),
        _row(
            2,
            family="baseline",
            wav_path=tactile_baseline,
            duration_s=0.72,
            soa_ms=390,
            tactile_onset_s=0.390,
            variant_key="serino_exp2_unimodal_tactile_baseline_proxy",
            multisensory_family="unimodal_tactile_baseline",
            exteroceptive_set="none",
            label="Serino Exp. 2 tactile baseline proxy",
        ),
        _row(
            3,
            family="catch",
            wav_path=catch_audio,
            duration_s=0.72,
            soa_ms=390,
            tactile_onset_s=None,
            variant_key="serino_exp2_audiovisual_catch_proxy",
            multisensory_family="audiovisual_catch",
            exteroceptive_set="auditory+visual",
            label="Serino Exp. 2 audiovisual catch proxy",
        ),
    ]
    fieldnames = list(rows[0].keys())
    block_csv = block_root / "block_01.csv"
    _write_csv(block_csv, rows, fieldnames)
    order_csv = run_root / "experiment_order.csv"
    _write_csv(
        order_csv,
        [
            {
                "participant_id": participant_id,
                "phase": "single",
                "phase_label": "Serino Exp. 2 audiovisual contract proxy",
                "phase_index": "1",
                "participant_block_position": "1",
                "source_block_index": "1",
                "block_label": "Block 01",
                "block_csv_file": block_csv.name,
                "block_csv_path": str(block_csv),
                "trial_count": str(len(rows)),
                "duration_ms": "2160",
                "sequence_seed": "20260715",
            }
        ],
        [
            "participant_id",
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
    multisensory_family: str,
    exteroceptive_set: str,
    label: str,
) -> dict[str, str]:
    has_tactile = family != "catch"
    has_visual = exteroceptive_set != "none"
    return {
        "block_trial_index": str(trial_number),
        "trial_pool_index": str(trial_number),
        "family": family,
        "trial_type": "Audio-Tactile" if family == "audio_tactile" else ("Tactile-Only" if has_tactile else "Catch"),
        "row_label": label,
        "noise_type": "serino_exp2_audiovisual_proxy",
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
        "multisensory_trial_family": multisensory_family,
        "exteroceptive_modality_set": exteroceptive_set,
        "visual_stimulus_type": "virtual_looming_tennis_ball" if has_visual else "not_applicable",
        "visual_motion_profile": "2m_frontal_constant_speed_approach" if has_visual else "not_applicable",
        "visual_start_distance_cm": "200" if has_visual else "not_applicable",
        "visual_end_distance_cm": "0" if has_visual else "not_applicable",
        "visual_speed_cm_s": "75" if has_visual else "not_applicable",
        "visual_duration_ms": "2600" if has_visual else "not_applicable",
        "visual_renderer_engine": "RealiSM_plus_ExpyVR" if has_visual else "not_applicable",
        "visual_display_device": "Oculus_Rift_DK2" if has_visual else "not_applicable",
        "mixed_reality_context": "own_body_in_panorama_with_virtual_ball" if has_visual else "not_applicable",
        "body_rendering_mode": "first_person_own_body_video_merge" if has_visual else "not_applicable",
        "audiovisual_synchrony_policy": (
            "dynamic_sound_same_velocity_direction_simultaneous_with_ball" if has_visual else "not_applicable"
        ),
        "mixed_reality_equivalence_boundary": (
            "metadata_preserved_no_vr_hmd_or_visual_rendering_equivalence" if has_visual else "not_applicable"
        ),
        "spatial_coordinate_frame": "body_relative",
        "body_anchor": "face",
        "body_part": "right_cheek",
        "body_side": "right",
        "spatial_hemifield": "front",
        "body_relative_axis": "frontal_depth",
        "auditory_trajectory_family": "binaural_prerecorded_approach" if family != "baseline" else "none",
        "auditory_trajectory_direction": "front_to_face" if family != "baseline" else "none",
        "trajectory_coordinate_frame": "body_relative",
        "trajectory_start_hemifield": "front_far" if family != "baseline" else "not_applicable",
        "trajectory_end_hemifield": "front_near" if family != "baseline" else "not_applicable",
        "trajectory_start_distance_cm": "200" if family != "baseline" else "not_applicable",
        "trajectory_end_distance_cm": "0" if family != "baseline" else "not_applicable",
        "trajectory_start_azimuth_deg": "0" if family != "baseline" else "not_applicable",
        "trajectory_end_azimuth_deg": "0" if family != "baseline" else "not_applicable",
        "spatial_renderer_engine": "RealiSM_prerecorded_binaural_playback" if family != "baseline" else "none",
        "spatial_renderer_version": "source_unresolved",
        "hrtf_database": "3Dio_Omni_Binaural_recording",
        "hrtf_subject_id": "not_applicable",
        "hrtf_filter_id": "not_applicable",
        "hrtf_near_field_compensation": "unreported",
        "source_asset_equivalence": "proxy_runner_smoke_not_original_video_or_binaural_tracks",
        "renderer_equivalence_boundary": "metadata_preserved_no_binaural_capture_or_mr_equivalence",
        "tactile_stimulation_modality": "mechanical_solenoid_tapper",
        "tactile_calibration_method": "paper_reported_MSTC3_tapper",
        "tactile_threshold_reference": "not_reported",
        "tactile_intensity": "not_reported",
        "tactile_intensity_unit": "not_reported",
        "tactile_pulse_duration_ms": "10",
        "expected_response": "respond" if has_tactile else "withhold",
        "response_rule": "detect right-cheek tactile target in Serino Exp. 2 proxy",
        "target_role": "target" if has_tactile else "catch_no_target",
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
        "serino_exp2_audiovisuotactile_d3_proxy",
        "serino_exp2_unimodal_tactile_baseline_proxy",
        "serino_exp2_audiovisual_catch_proxy",
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
        "Serino Exp. 2 audiovisuotactile D3 proxy",
        "Serino Exp. 2 tactile baseline proxy",
        "Serino Exp. 2 audiovisual catch proxy",
    }.issubset(labels)


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Audiovisual/Trisensory Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Block rows: `{report['block_row_family_counts']}`",
        f"- Multisensory families: `{report['block_row_multisensory_families']}`",
        f"- Exteroceptive sets: `{report['block_row_exteroceptive_sets']}`",
        f"- Event counts: `{report['event_counts']}`",
        "",
        "## Criteria",
    ]
    for key, value in report["criteria"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Evidence Boundary",
            "",
            report["evidence_boundary"],
            "",
            "## Expected Outcome Boundary",
            "",
            report["paper_parameter_basis"]["expected_outcome"],
            "",
        ]
    )
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
