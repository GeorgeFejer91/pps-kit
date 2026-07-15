"""Validate the Noel 2015 walking PPS profile through GUI bakes and runner.

This paper-specific validator starts from the manual public-PDF review, loads
the Noel walking profile through DashboardController, bakes Segments 2-6,
prepares runnable block WAVs, runs the session with software wired-loopback
sidecars, injects mouse-click responses on tactile target/baseline rows,
withholds on sound-only catches, and compares the observed software contract
with the paper-extracted parameters.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_ready_profile_runner_smoke as runner_smoke  # noqa: E402
from run_tajadura_2009_known_parameter_profile_validation import (  # noqa: E402
    ResponseWindowClickEngine,
    _accept_segment5,
    _event_counts,
    _first,
    _json_ready,
    _read_csv,
    _read_json,
    _segment_status_map,
    _write_json,
)
from peripersonal_space_toolkit import dashboard_app  # noqa: E402
from peripersonal_space_toolkit.dashboard_app import DashboardController  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-noel-2015-known-parameter-validation.v1"
RECORD_ID = "noel_2015_walking"
TEMPLATE_ID = "noel_2015_walking_full_body_action"
MANUAL_REVIEW = (
    REPO_ROOT
    / "For-AI"
    / "audiotactile-paper-metadata-audit"
    / "manual_reviews"
    / f"{RECORD_ID}.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_noel_2015_known_parameter_20260715"
EVIDENCE_BOUNDARY = (
    "This validates the software-known parameter contract for Noel et al. "
    "(2015): paper-extracted white-noise motion, 2 m path, 0.75 m/s speed, "
    "standing/walking and looming/receding conditions, chest vibrotactile "
    "target rows, tactile-only baselines, sound-only catches, 512 trial rows, "
    "Segment 0-6 GUI materialization, generated WAV packages, software "
    "wired-loopback sidecars, and mouse-click simulated participant-like "
    "responses. It does not claim physical reproduction of treadmill walking, "
    "optic flow, the dual eight-speaker arrays, participant behavior, or the "
    "human walking-expanded PPS effect."
)


class TactileOnsetClickEngine(ResponseWindowClickEngine):
    """Inject responses after tactile onset so long-SOA audio-tactile rows score as hits."""

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self._current_block_path = Path(path)
        self.played_blocks.append(str(path))
        self._audio_event_callback = audio_event_callback
        self._clicks_this_block = 0
        info = sf.info(path)
        self._sample_rate = int(info.samplerate)
        frames_total = int(info.frames)
        self._block_start_perf = time.perf_counter()
        self._block_anchor_unix = time.time()
        if progress_callback is not None:
            progress_callback(0.0)
        if block_event_schedule is not None and audio_event_callback is not None:
            block_event_schedule.reset()
            for event in block_event_schedule.consume_buffer(0, frames_total + 1):
                if self._stopped:
                    break
                sample_index = int(event.sample_index)
                payload = dict(event.payload)
                payload.update(
                    {
                        "event_type": event.event_type,
                        "sample_rate": self._sample_rate,
                        "sample_index": sample_index,
                        "sample_offset_in_buffer": 0,
                        "scheduled_sample_index": sample_index,
                        "callback_perf_counter": self._block_start_perf,
                        "stream_current_time": self._block_start_perf,
                        "stream_output_buffer_dac_time": self._block_start_perf,
                        "trigger_key": event.trigger_key,
                    }
                )
                audio_event_callback(payload)
                if event.event_type == "tactile_onset" and _lower(_first(payload, "expected_response", "Expected_Response")) == "respond":
                    self._log_synthetic_click(payload, sample_index=sample_index)
        if progress_callback is not None:
            progress_callback(float(info.duration))
        return not self._stopped


def run_validation(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = _expected_contract_from_manual_review()
    materialized = _materialize_profile(output_dir=output_dir)
    run_manifest = Path(materialized["segment6_manifest_path"])
    package = prepare_segment_run_package(
        run_manifest,
        participant_id=participant_id,
        design=materialized["design"],
        session_root=output_dir / "sessions",
        use_block_cache=False,
    )
    engine = TactileOnsetClickEngine(response_delay_s=0.12)
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
        runner_metadata={"participant_code": participant_id, "source_profile_id": TEMPLATE_ID},
    )
    engine.attach_controller(controller)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=2.0)

    observed = _observed_contract(materialized, package, result)
    criteria = _criteria(expected, materialized, observed, result, package)
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "record_id": RECORD_ID,
        "template_id": TEMPLATE_ID,
        "passed": all(criteria.values()),
        "criteria": criteria,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "expected_contract": expected,
        "observed_contract": observed,
        "observed_vs_expected_outcome": {
            "expected_paper_outcome": expected["expected_scientific_outcome"],
            "software_contract_match": all(criteria.values()),
            "observed_emulated_outcome": (
                "All extracted runnable stimulus, locomotion-condition metadata, direction, timing, "
                "response, count, WAV, and runner contracts matched. The emulated run cannot estimate "
                "human walking-expanded PPS facilitation."
            ),
        },
        "materialization": _json_ready({key: value for key, value in materialized.items() if key != "design"}),
        "participant_id": participant_id,
        "run_setup_manifest": str(run_manifest),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "runner_completed": bool(result.completed and not result.interrupted),
        "events_csv": str(result.events_csv),
        "analysis_outputs": {key: str(value) for key, value in result.analysis_outputs.items()},
        "software_wired_loopback_wavs": [str(path) for path in package.session_dir.glob("*wired_loopback*.wav")],
        "report_json": str(output_dir / "noel_2015_known_parameter_validation_report.json"),
        "report_md": str(output_dir / "noel_2015_known_parameter_validation_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _materialize_profile(*, output_dir: Path) -> dict[str, Any]:
    batch_root = output_dir / "dashboard_gui_materialization" / TEMPLATE_ID
    if batch_root.exists():
        shutil.rmtree(batch_root)
    controller = DashboardController(
        design_path=batch_root / "active_design.json",
        render_dir=batch_root / "legacy_render",
        session_root=batch_root / "controller_sessions",
        import_dir=batch_root / "imports",
        preview_dir=batch_root / "previews",
        project_registry_root=batch_root / "0_study_project_registry",
        state_root=batch_root / "dashboard_state",
    )
    state = controller.load_template(TEMPLATE_ID)
    with controller._lock:
        project = controller._ensure_project_context(controller.design)
        design = controller.design
    initial_segment_status = _segment_status_map(project, design)
    segment2 = dashboard_app._bake_trial_sequence_variants(design, project.project_dir)
    segment3 = dashboard_app._bake_audio_tactile_trial_files(design, project.project_dir)
    segment4 = dashboard_app._bake_trial_repetition_pool(
        design,
        project.project_dir,
        {"kind": "trial_repetition_pool", "label": "4_trial_repetition_pool"},
    )
    block_count = int(getattr(design.protocol, "blocks", 1) or 1)
    segment5 = dashboard_app._bake_block_csv_preview(
        design,
        project.project_dir,
        {"kind": "block_csv_preview", "label": "5_block_csv_preview", "block_count": block_count},
    )
    _accept_segment5(project.project_dir)
    segment6 = dashboard_app._write_run_setup_outputs(project.project_dir, design)
    final_segment_status = _segment_status_map(project, design)
    block_manifest = dashboard_app._load_json(dashboard_app._block_csv_preview_manifest_path(project.project_dir))
    block_csvs = [Path(str(block["csv_path"])) for block in block_manifest.get("blocks", [])]
    block_rows = [row for csv_path in block_csvs for row in _read_csv(csv_path)]
    return {
        "design": design,
        "project_dir": str(project.project_dir),
        "selected_template": state.get("selected_template", ""),
        "profile_read_only": not bool((state.get("custom_workflow") or {}).get("is_custom")),
        "initial_segment_status": initial_segment_status,
        "final_segment_status": final_segment_status,
        "segment2": segment2,
        "segment3": segment3,
        "segment4": segment4,
        "segment5": segment5,
        "segment6": segment6,
        "segment6_manifest_path": segment6["manifest_path"],
        "segment5_manifest_path": str(dashboard_app._block_csv_preview_manifest_path(project.project_dir)),
        "segment5_block_csvs": [str(path) for path in block_csvs],
        "segment5_block_rows": block_rows,
        "block_csv_counts": _block_contract_counts(block_rows),
    }


def _expected_contract_from_manual_review() -> dict[str, Any]:
    review = _read_json(MANUAL_REVIEW)
    return {
        "source": str(MANUAL_REVIEW),
        "review_confidence_label": review.get("confidence_label", ""),
        "review_confidence_score": review.get("confidence_score", ""),
        "sound_type": "white_noise",
        "sound_level_db": 50,
        "sound_path_m": 2.0,
        "sound_velocity_mps": 0.75,
        "sound_duration_s": 2.666667,
        "tactile_delays_ms": [440, 880, 1330, 1770, 2220],
        "distance_table_cm": {"D1": 33, "D2": 66, "D3": 100, "D4": 133, "D5": 166},
        "looming_mapping": {
            "440|166.0": 32,
            "880|133.0": 32,
            "1330|100.0": 32,
            "1770|66.0": 32,
            "2220|33.0": 32,
        },
        "receding_mapping": {
            "440|33.0": 32,
            "880|66.0": 32,
            "1330|100.0": 32,
            "1770|133.0": 32,
            "2220|166.0": 32,
        },
        "trial_counts": {
            "total": 512,
            "audio_tactile": 320,
            "baseline": 128,
            "catch": 64,
            "respond": 448,
            "withhold": 64,
        },
        "condition_counts": {
            "locomotion_condition": {"standing_still": 256, "walking_treadmill_0.70_m_s": 256},
            "auditory_trajectory_direction": {"looming": 256, "receding": 256},
        },
        "expected_scientific_outcome": (
            "Standing facilitation is expected around D1-D2, walking expands facilitation through D5/166 cm, "
            "and receding sounds do not show the same space-dependent modulation. The software validator "
            "tests only the runnable parameter contract."
        ),
    }


def _observed_contract(materialized: dict[str, Any], package: Any, result: Any) -> dict[str, Any]:
    block_rows = materialized["segment5_block_rows"]
    events = _read_csv(result.events_csv)
    participant_rows = _read_csv(result.analysis_outputs.get("participant_trials", Path()))
    analysis_rows = _read_csv(result.analysis_outputs.get("analysis_ready_trials", Path()))
    loopback_paths = [path for path in package.session_dir.glob("*wired_loopback*.wav")]
    return {
        "segment2_variant_count": int(materialized["segment2"]["variant_count"]),
        "segment3_audio_tactile_count": int(materialized["segment3"]["audio_tactile_count"]),
        "segment3_baseline_count": int(materialized["segment3"]["baseline_count"]),
        "segment3_catch_count": int(materialized["segment3"]["catch_count"]),
        "segment3_auditory_only_count": int(materialized["segment3"].get("auditory_only_count", 0)),
        "segment4_total_count": int(materialized["segment4"]["total_count"]),
        "segment4_audio_tactile_count": int(materialized["segment4"]["audio_tactile_count"]),
        "segment4_baseline_count": int(materialized["segment4"]["baseline_count"]),
        "segment4_catch_count": int(materialized["segment4"]["catch_count"]),
        "segment5_block_count": int(materialized["segment5"]["block_count"]),
        "segment5_total_count": int(materialized["segment5"]["total_count"]),
        "block_csv_counts": materialized["block_csv_counts"],
        "package_block_count": len(package.blocks),
        "package_block_wavs": [str(block.wav_path) for block in package.blocks],
        "package_block_wav_facts": [runner_smoke._wav_facts(block.wav_path) for block in package.blocks],
        "event_counts": _event_counts(events),
        "participant_trial_count": len(participant_rows),
        "participant_outcome_counts": _count_values(participant_rows, "outcome"),
        "participant_expected_response_counts": _count_values(participant_rows, "expected_response"),
        "participant_response_given_counts": _count_values(participant_rows, "response_given"),
        "participant_family_counts": _count_values(participant_rows, "family"),
        "participant_locomotion_condition_counts": _count_values(participant_rows, "locomotion_condition"),
        "participant_auditory_trajectory_direction_counts": _count_values(participant_rows, "auditory_trajectory_direction"),
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_locomotion_condition_counts": _count_values(analysis_rows, "locomotion_condition"),
        "analysis_auditory_trajectory_direction_counts": _count_values(analysis_rows, "auditory_trajectory_direction"),
        "mouse_click_count": _event_counts(events).get("mouse_click", 0),
        "response_marker_count": _event_counts(events).get("response_marker_start", 0),
        "software_wired_loopback_count": len(loopback_paths),
        "software_wired_loopback_facts": [runner_smoke._wav_facts(path) for path in loopback_paths],
        "runner_completed": bool(result.completed and not result.interrupted),
    }


def _criteria(
    expected: dict[str, Any],
    materialized: dict[str, Any],
    observed: dict[str, Any],
    result: Any,
    package: Any,
) -> dict[str, bool]:
    counts = observed["block_csv_counts"]
    final_status = materialized["final_segment_status"]
    expected_trials = expected["trial_counts"]
    expected_conditions = expected["condition_counts"]
    return {
        "manual_review_loaded": Path(expected["source"]).is_file(),
        "gui_loaded_profile_read_only": materialized["selected_template"] == TEMPLATE_ID and bool(materialized["profile_read_only"]),
        "segments_0_to_6_ready": set(final_status) == {
            "0_profile",
            "1_core_audio_ingredients",
            "2_trial_sequence_designs",
            "3_tactile_and_baseline_trials",
            "4_trial_repetition_pool",
            "5_block_csv_preview",
            "6_experiment_run_setup",
        }
        and all(value == "ready" for value in final_status.values()),
        "segment_bakes_match_expected_counts": observed["segment2_variant_count"] == 4
        and observed["segment3_audio_tactile_count"] == 20
        and observed["segment3_baseline_count"] == 8
        and observed["segment3_catch_count"] == 4
        and observed["segment3_auditory_only_count"] == 0
        and observed["segment4_total_count"] == expected_trials["total"]
        and observed["segment4_audio_tactile_count"] == expected_trials["audio_tactile"]
        and observed["segment4_baseline_count"] == expected_trials["baseline"]
        and observed["segment4_catch_count"] == expected_trials["catch"]
        and observed["segment5_total_count"] == expected_trials["total"]
        and observed["segment5_block_count"] == 8,
        "block_csv_matches_paper_trial_counts": counts["family"] == {
            "audio_tactile": expected_trials["audio_tactile"],
            "baseline": expected_trials["baseline"],
            "catch": expected_trials["catch"],
        }
        and counts["expected_response"] == {"respond": expected_trials["respond"], "withhold": expected_trials["withhold"]}
        and counts["locomotion_condition"] == expected_conditions["locomotion_condition"]
        and counts["auditory_trajectory_direction"] == expected_conditions["auditory_trajectory_direction"],
        "block_csv_preserves_timing_distance_mapping": counts["audio_looming_soa_distance"] == expected["looming_mapping"]
        and counts["audio_receding_soa_distance"] == expected["receding_mapping"]
        and counts["baseline_soa_ms"] == {"440": 64, "2220": 64}
        and counts["catch_direction_counts"] == {
            "looming": 32,
            "receding": 32,
        },
        "block_csv_preserves_apparatus_context": counts["noise_type"] == {"white": 512}
        and counts["tactile_stimulation_modality"] == {"vibrotactile": 512}
        and counts["tactile_waveform_shape"] == {"sine": 512}
        and counts["tactile_duration_ms"] == {"0": 64, "100": 448}
        and counts["tactile_pulse_duration_ms"] == {"100": 512}
        and counts["response_capture_device"] == {"wireless Xbox 360 controller": 512},
        "package_wavs_generated": len(package.blocks) == 8
        and all(Path(block.wav_path).is_file() and runner_smoke._wav_facts(block.wav_path).get("readable") for block in package.blocks),
        "runner_completed": bool(result.completed and not result.interrupted),
        "runner_events_match_expected_counts": observed["event_counts"].get("trial_start", 0) == expected_trials["total"]
        and observed["event_counts"].get("trial_end", 0) == expected_trials["total"]
        and observed["event_counts"].get("looming_onset", 0) == 384
        and observed["event_counts"].get("tactile_onset", 0) == expected_trials["respond"]
        and observed["event_counts"].get("response_window_onset", 0) == expected_trials["total"]
        and observed["mouse_click_count"] == expected_trials["respond"]
        and observed["response_marker_count"] == expected_trials["respond"],
        "participant_rows_match_expected_contract": observed["participant_trial_count"] == expected_trials["total"]
        and observed["participant_outcome_counts"] == {"Hit": expected_trials["total"]}
        and observed["participant_expected_response_counts"] == {
            "respond": expected_trials["respond"],
            "withhold": expected_trials["withhold"],
        }
        and observed["participant_response_given_counts"] == {"false": expected_trials["withhold"], "true": expected_trials["respond"]}
        and observed["participant_family_counts"] == {
            "audio_tactile": expected_trials["audio_tactile"],
            "baseline": expected_trials["baseline"],
            "catch": expected_trials["catch"],
        }
        and observed["participant_locomotion_condition_counts"] == expected_conditions["locomotion_condition"]
        and observed["participant_auditory_trajectory_direction_counts"] == expected_conditions["auditory_trajectory_direction"],
        "analysis_rows_preserve_condition_metadata": observed["analysis_ready_trial_count"] == expected_trials["respond"]
        and observed["analysis_locomotion_condition_counts"] == {
            "standing_still": 224,
            "walking_treadmill_0.70_m_s": 224,
        }
        and observed["analysis_auditory_trajectory_direction_counts"] == {"looming": 224, "receding": 224},
        "software_wired_loopback_written": observed["software_wired_loopback_count"] >= 8
        and all(item.get("readable") for item in observed["software_wired_loopback_facts"]),
    }


def _block_contract_counts(rows: list[dict[str, str]]) -> dict[str, Any]:
    audio_rows = [row for row in rows if _lower(row.get("family")) == "audio_tactile"]
    baseline_rows = [row for row in rows if _lower(row.get("family")) == "baseline"]
    catch_rows = [row for row in rows if _lower(row.get("family")) == "catch"]
    looming_rows = [row for row in audio_rows if _lower(row.get("auditory_trajectory_direction")) == "looming"]
    receding_rows = [row for row in audio_rows if _lower(row.get("auditory_trajectory_direction")) == "receding"]
    return {
        "family": _count_values(rows, "family"),
        "expected_response": _count_values(rows, "expected_response"),
        "target_role": _count_values(rows, "target_role"),
        "noise_type": _count_values((row for row in rows if row.get("noise_type")), "noise_type"),
        "locomotion_condition": _count_values(rows, "locomotion_condition"),
        "auditory_trajectory_direction": _count_values(rows, "auditory_trajectory_direction"),
        "tactile_stimulation_modality": _count_values(rows, "tactile_stimulation_modality"),
        "tactile_waveform_shape": _count_values(rows, "tactile_waveform_shape"),
        "tactile_duration_ms": _count_values(rows, "tactile_duration_ms"),
        "tactile_pulse_duration_ms": _count_values(rows, "tactile_pulse_duration_ms"),
        "response_capture_device": _count_values(rows, "response_capture_device"),
        "audio_looming_soa_distance": _soa_distance_counts(looming_rows),
        "audio_receding_soa_distance": _soa_distance_counts(receding_rows),
        "baseline_soa_ms": _count_values(baseline_rows, "soa_ms"),
        "catch_direction_counts": _count_values(catch_rows, "auditory_trajectory_direction"),
    }


def _soa_distance_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                f"{_format_number(row.get('soa_ms'))}|{_format_number(row.get('spatial_value_cm'))}"
                for row in rows
            ).items()
        )
    )


def _count_values(rows: Any, key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return dict(sorted(counts.items()))


def _format_number(value: Any) -> str:
    text = str(value or "").strip()
    try:
        number = float(text)
    except ValueError:
        return text
    if number.is_integer() and "." not in text:
        return str(int(number))
    return f"{number:.1f}" if number.is_integer() else f"{number:g}"


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Noel 2015 Known-Parameter Validation",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Template: `{TEMPLATE_ID}`",
        f"- Evidence boundary: {EVIDENCE_BOUNDARY}",
        "",
        "## Criteria",
        "",
    ]
    for key, value in report["criteria"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Expected total trials: `{report['expected_contract']['trial_counts']['total']}`",
            f"- Observed block CSV counts: `{json.dumps(report['observed_contract']['block_csv_counts'], sort_keys=True)}`",
            f"- Event counts: `{json.dumps(report['observed_contract']['event_counts'], sort_keys=True)}`",
            f"- Observed-vs-expected: {report['observed_vs_expected_outcome']['observed_emulated_outcome']}",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Noel 2015 known-parameter GUI/runner validation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args()
    report = run_validation(output_dir=args.output_dir, participant_id=args.participant_id)
    print(f"Wrote Noel 2015 validation report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
