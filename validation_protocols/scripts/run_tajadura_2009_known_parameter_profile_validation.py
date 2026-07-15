"""Validate the Collignon/Tajadura-Jimenez 2009 profiles through GUI bakes and runner.

The local literature ledger keeps the legacy record id
``tajadura_jimenez_2009_visual_deprivation`` although the DOI/PDF are
Collignon et al. (2009). This validator starts from that manual PDF review,
loads the two posture-specific study profiles through DashboardController,
bakes Segments 2-6, runs each prepared package with synthetic mouse-click
left/right responses, and compares the observed software contract with the
paper-extracted parameters.
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
from run_gonogo_capability_smoke import GoNoGoSmokeAudioEngine  # noqa: E402
from peripersonal_space_toolkit import dashboard_app  # noqa: E402
from peripersonal_space_toolkit.dashboard_app import DashboardController  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    RESPONSE_MARKER_GAIN,
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-tajadura-2009-known-parameter-validation.v1"
RECORD_ID = "tajadura_jimenez_2009_visual_deprivation"
TEMPLATE_IDS = [
    "tajadura_jimenez_2009_uncrossed_visual_deprivation",
    "tajadura_jimenez_2009_crossed_visual_deprivation",
]
MANUAL_REVIEW = (
    REPO_ROOT
    / "For-AI"
    / "audiotactile-paper-metadata-audit"
    / "manual_reviews"
    / f"{RECORD_ID}.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_tajadura_2009_known_parameter_20260715"
EVIDENCE_BOUNDARY = (
    "This validates the software-known parameter contract for Collignon et al. "
    "(2009; legacy local id Tajadura-Jimenez): paper-extracted static left/right "
    "pink-noise bursts, crossed/uncrossed posture profiles, auditory-only, "
    "tactile-only, congruent audio-tactile rows, Segment 0-6 GUI materialization, "
    "generated WAV packages, software wired-loopback sidecars, and mouse-click "
    "left/right simulated participant-like responses. It does not claim exact "
    "physical reproduction of the original Adobe Audition file, electrical "
    "stimulator waveform/current, ISI distribution, participant behavior, or the "
    "human posture-dependent facilitation effect."
)


class ResponseWindowClickEngine(GoNoGoSmokeAudioEngine):
    """Fast engine that injects valid left/right mouse clicks from response windows."""

    def __init__(self, *, response_delay_s: float = 0.12):
        super().__init__(max_clicks_per_block=10_000, response_delay_s=response_delay_s)
        self.controller: SessionRunnerController | None = None
        self._block_anchor_unix = 0.0

    def attach_controller(self, controller: SessionRunnerController) -> None:
        self.controller = controller

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
                if event.event_type == "response_window_onset" and _lower(_first(payload, "expected_response", "Expected_Response")) == "respond":
                    self._log_synthetic_click(payload, sample_index=sample_index)
        if progress_callback is not None:
            progress_callback(float(info.duration))
        return not self._stopped

    def _log_synthetic_click(self, payload: dict[str, Any], *, sample_index: int) -> None:
        if self.controller is None:
            return
        offset_s = (sample_index / float(self._sample_rate or 44100)) + self.response_delay_s
        event_unix = self._block_anchor_unix + offset_s
        event_perf = self._block_start_perf + offset_s
        correct = _lower(_first(payload, "correct_response", "Correct_Response"))
        x = 250 if correct == "left" else 750
        block_number = _first(payload, "block_number", "block_index", "Block_Number")
        block_payload = {
            "block_number": block_number,
            "block_index": block_number,
            "block_label": _first(payload, "block_label", "Block_Label"),
            "part_number": _first(payload, "part_number", "Part_Number"),
            "phase": _first(payload, "phase", "Phase"),
            "phase_label": _first(payload, "phase_label", "Phase_Label"),
            "is_topup": False,
        }
        mouse_event = self.controller.events.log(
            "mouse_click",
            unix_time=event_unix,
            monotonic_time=event_perf,
            x=x,
            y=240,
            in_target=True,
            during_playback=True,
            **block_payload,
            push_lsl=False,
        )
        self.controller.events.log(
            "response_marker_start",
            unix_time=event_unix,
            monotonic_time=event_perf,
            marker_channel=2,
            marker_gain=RESPONSE_MARKER_GAIN,
            mouse_event_id=mouse_event.event_id,
            mouse_event_unix_time=mouse_event.unix_time,
            mouse_event_monotonic_time=mouse_event.monotonic_time,
            **block_payload,
            push_lsl=False,
        )


def run_validation(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = _expected_contract_from_manual_review()
    profile_reports = [
        _validate_profile(template_id, output_dir=output_dir, participant_id=participant_id, expected=expected)
        for template_id in TEMPLATE_IDS
    ]
    criteria = {
        "manual_review_loaded": Path(expected["source"]).is_file(),
        "both_posture_profiles_validated": len(profile_reports) == 2 and all(item["passed"] for item in profile_reports),
        "combined_trial_count_matches_paper": sum(item["observed_contract"]["segment5_total_count"] for item in profile_reports) == 600,
        "combined_mouse_click_count_matches_response_rows": sum(item["observed_contract"]["mouse_click_count"] for item in profile_reports) == 600,
        "observed_scope_matches_expected_software_contract": all(
            item["observed_vs_expected_outcome"]["software_contract_match"] for item in profile_reports
        ),
    }
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "record_id": RECORD_ID,
        "template_ids": TEMPLATE_IDS,
        "passed": all(criteria.values()),
        "criteria": criteria,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "expected_contract": expected,
        "profiles": profile_reports,
        "report_json": str(output_dir / "tajadura_2009_known_parameter_validation_report.json"),
        "report_md": str(output_dir / "tajadura_2009_known_parameter_validation_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _validate_profile(
    template_id: str,
    *,
    output_dir: Path,
    participant_id: str,
    expected: dict[str, Any],
) -> dict[str, Any]:
    materialized = _materialize_profile(template_id, output_dir=output_dir)
    run_manifest = Path(materialized["segment6_manifest_path"])
    package = prepare_segment_run_package(
        run_manifest,
        participant_id=participant_id,
        design=materialized["design"],
        session_root=output_dir / "sessions" / template_id,
        use_block_cache=False,
    )
    engine = ResponseWindowClickEngine(response_delay_s=0.12)
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
        runner_metadata={"participant_code": participant_id, "source_profile_id": template_id},
    )
    engine.attach_controller(controller)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=2.0)
    observed = _observed_contract(materialized, package, result)
    criteria = _profile_criteria(template_id, expected, materialized, observed, result, package)
    outcome = {
        "expected_paper_outcome": expected["expected_scientific_outcome"],
        "software_contract_match": all(criteria.values()),
        "observed_emulated_outcome": (
            "All extracted runnable stimulus, modality, posture, response, count, WAV, and runner contracts matched. "
            "The emulated run cannot estimate human posture-dependent facilitation."
        ),
    }
    return {
        "template_id": template_id,
        "passed": all(criteria.values()),
        "criteria": criteria,
        "observed_vs_expected_outcome": outcome,
        "materialization": _json_ready({key: value for key, value in materialized.items() if key != "design"}),
        "observed_contract": observed,
        "participant_id": participant_id,
        "run_setup_manifest": str(run_manifest),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "runner_completed": bool(result.completed and not result.interrupted),
        "events_csv": str(result.events_csv),
        "analysis_outputs": {key: str(value) for key, value in result.analysis_outputs.items()},
        "software_wired_loopback_wavs": [str(path) for path in package.session_dir.glob("*wired_loopback*.wav")],
    }


def _materialize_profile(template_id: str, *, output_dir: Path) -> dict[str, Any]:
    batch_root = output_dir / "dashboard_gui_materialization" / template_id
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
    state = controller.load_template(template_id)
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
    segment5 = dashboard_app._bake_block_csv_preview(
        design,
        project.project_dir,
        {"kind": "block_csv_preview", "label": "5_block_csv_preview", "block_count": 1},
    )
    _accept_segment5(project.project_dir)
    segment6 = dashboard_app._write_run_setup_outputs(project.project_dir, design)
    final_segment_status = _segment_status_map(project, design)
    block_manifest = dashboard_app._load_json(dashboard_app._block_csv_preview_manifest_path(project.project_dir))
    block_csv = Path(str(block_manifest["blocks"][0]["csv_path"]))
    block_rows = _read_csv(block_csv)
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
        "segment5_block_csv": str(block_csv),
        "segment5_block_rows": block_rows,
        "block_csv_counts": _block_contract_counts(block_rows),
    }


def _accept_segment5(project_dir: Path) -> None:
    manifest_path = dashboard_app._block_csv_preview_manifest_path(project_dir)
    manifest = dashboard_app._load_json(manifest_path)
    manifest = dashboard_app._finalize_block_csv_manifest(manifest)
    manifest["accepted"] = True
    manifest["accepted_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    manifest["accepted_source_segment4_manifest_sha256"] = manifest.get("source_segment4_manifest_sha256", "")
    dashboard_app._write_json(manifest_path, manifest)


def _segment_status_map(project: Any, design: Any) -> dict[str, str]:
    return {
        key: str(value.get("status") or "")
        for key, value in dashboard_app._project_segments_status(project, design).items()
    }


def _expected_contract_from_manual_review() -> dict[str, Any]:
    review = _read_json(MANUAL_REVIEW)
    return {
        "source": str(MANUAL_REVIEW),
        "review_confidence_label": review.get("confidence_label", ""),
        "sound_type": "pink_noise_burst",
        "sound_duration_ms": 100,
        "sound_plateau_ms": 90,
        "sound_rise_fall_ms": 5,
        "sound_level_db_spl": 75,
        "soa_ms": 0,
        "speaker_offsets_cm": {"left_right_from_midline": 25, "forward_from_body": 30},
        "external_source_distance_cm": 39.1,
        "tactile_train": "five 1 ms biphasic square pulses every 25 ms, 40 Hz/100 ms",
        "per_posture_trial_count": 300,
        "per_posture_family_counts": {"audio_tactile": 100, "baseline": 100, "auditory_only": 100},
        "per_posture_side_counts": {"left": 150, "right": 150},
        "combined_test_trial_count": 600,
        "catch_trial_count": 0,
        "expected_response_count_per_posture": 300,
        "expected_scientific_outcome": (
            "Spatially congruent audio-tactile trials are expected to show posture-dependent facilitation; "
            "the software validator can only test the runnable parameter contract, not the human effect."
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
        "segment4_auditory_only_count": int(materialized["segment4"].get("auditory_only_count", 0)),
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
        "participant_family_counts": _count_values(participant_rows, "family"),
        "participant_stimulus_modality_counts": _count_values(participant_rows, "stimulus_modality"),
        "participant_response_choice_correct_counts": _count_values(participant_rows, "response_choice_correct"),
        "analysis_ready_trial_count": len(analysis_rows),
        "mouse_click_count": _event_counts(events).get("mouse_click", 0),
        "response_marker_count": _event_counts(events).get("response_marker_start", 0),
        "software_wired_loopback_count": len(loopback_paths),
        "software_wired_loopback_facts": [runner_smoke._wav_facts(path) for path in loopback_paths],
        "runner_completed": bool(result.completed and not result.interrupted),
    }


def _profile_criteria(
    template_id: str,
    expected: dict[str, Any],
    materialized: dict[str, Any],
    observed: dict[str, Any],
    result: Any,
    package: Any,
) -> dict[str, bool]:
    counts = observed["block_csv_counts"]
    final_status = materialized["final_segment_status"]
    posture = "crossed" if "crossed" in template_id and "uncrossed" not in template_id else "uncrossed"
    expected_body_by_side = (
        {"left": "right", "right": "left"} if posture == "crossed" else {"left": "left", "right": "right"}
    )
    return {
        "manual_review_loaded": Path(expected["source"]).is_file(),
        "gui_loaded_profile_read_only": materialized["selected_template"] == template_id and bool(materialized["profile_read_only"]),
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
        "segment_bakes_match_expected_counts": observed["segment2_variant_count"] == 2
        and observed["segment3_audio_tactile_count"] == 2
        and observed["segment3_baseline_count"] == 2
        and observed["segment3_auditory_only_count"] == 2
        and observed["segment3_catch_count"] == 0
        and observed["segment4_total_count"] == expected["per_posture_trial_count"]
        and observed["segment5_total_count"] == expected["per_posture_trial_count"]
        and observed["segment5_block_count"] == 1,
        "block_csv_matches_family_counts": counts["family"] == expected["per_posture_family_counts"],
        "block_csv_preserves_response_contract": counts["expected_response"] == {"respond": 300}
        and counts["correct_response"] == {"left": 150, "right": 150}
        and counts["response_rule"] == {"choose_external_stimulus_side": 300},
        "block_csv_preserves_posture_side_mapping": counts["body_side_by_correct_response"] == expected_body_by_side,
        "package_wavs_generated": len(package.blocks) == 1
        and all(Path(block.wav_path).is_file() and runner_smoke._wav_facts(block.wav_path).get("readable") for block in package.blocks),
        "runner_completed": bool(result.completed and not result.interrupted),
        "runner_events_match_expected_counts": observed["event_counts"].get("trial_start", 0) == 300
        and observed["event_counts"].get("trial_end", 0) == 300
        and observed["event_counts"].get("looming_onset", 0) == 200
        and observed["event_counts"].get("tactile_onset", 0) == 200
        and observed["event_counts"].get("response_window_onset", 0) == 300
        and observed["mouse_click_count"] == 300
        and observed["response_marker_count"] == 300,
        "participant_rows_match_expected_contract": observed["participant_trial_count"] == 300
        and observed["participant_outcome_counts"] == {"Hit": 300}
        and observed["participant_expected_response_counts"] == {"respond": 300}
        and observed["participant_response_choice_correct_counts"] == {"true": 300},
        "software_wired_loopback_written": observed["software_wired_loopback_count"] >= 1
        and all(item.get("readable") for item in observed["software_wired_loopback_facts"]),
    }


def _block_contract_counts(rows: list[dict[str, str]]) -> dict[str, Any]:
    body_side_by_choice: dict[str, str] = {}
    for choice in ("left", "right"):
        sides = {
            str(row.get("body_side") or row.get("Body_Side") or "").strip().lower()
            for row in rows
            if str(row.get("correct_response") or row.get("Correct_Response") or "").strip().lower() == choice
            and str(row.get("family") or row.get("Family") or "").strip().lower() == "audio_tactile"
        }
        if len(sides) == 1:
            body_side_by_choice[choice] = next(iter(sides))
    return {
        "family": _count_values(rows, "family"),
        "expected_response": _count_values(rows, "expected_response"),
        "correct_response": _count_values(rows, "correct_response"),
        "response_rule": _count_values(rows, "response_rule"),
        "target_role": _count_values(rows, "target_role"),
        "soa_ms": _count_values(rows, "soa_ms"),
        "spatial_value_cm": _count_values(rows, "spatial_value_cm"),
        "body_side_by_correct_response": body_side_by_choice,
    }


def _event_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    return _count_values(rows, "event_type")


def _count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return dict(sorted(counts.items()))


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    if not path:
        return []
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_json(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Collignon/Tajadura-Jimenez 2009 Known-Parameter Validation",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Record: `{RECORD_ID}`",
        f"- Templates: `{', '.join(TEMPLATE_IDS)}`",
        f"- Evidence boundary: {EVIDENCE_BOUNDARY}",
        "",
        "## Criteria",
        "",
    ]
    for key, value in report["criteria"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Profiles", ""])
    for profile in report["profiles"]:
        lines.append(f"### {profile['template_id']}")
        lines.append("")
        lines.append(f"- Passed: `{profile['passed']}`")
        lines.append(f"- Observed block CSV counts: `{json.dumps(profile['observed_contract']['block_csv_counts'], sort_keys=True)}`")
        lines.append(f"- Event counts: `{json.dumps(profile['observed_contract']['event_counts'], sort_keys=True)}`")
        lines.append(f"- Observed-vs-expected: {profile['observed_vs_expected_outcome']['observed_emulated_outcome']}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _first(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Collignon/Tajadura-Jimenez 2009 known-parameter GUI/runner validation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args()
    report = run_validation(output_dir=args.output_dir, participant_id=args.participant_id)
    print(f"Wrote Tajadura/Collignon 2009 validation report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
