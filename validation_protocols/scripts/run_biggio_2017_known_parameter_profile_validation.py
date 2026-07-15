"""Validate the Biggio 2017 racket tool-use profiles through GUI bakes and runner.

This paper-specific validator starts from the manual PDF review, loads the
three session-context profiles through DashboardController, bakes Segments 2-6,
prepares runnable WAV packages, runs each package with software wired-loopback
sidecars, injects mouse-click responses on tactile target rows, withholds on
sound-only catches, and compares the observed software contract with the
paper-extracted parameters.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_ready_profile_runner_smoke as runner_smoke  # noqa: E402
from run_tajadura_2009_known_parameter_profile_validation import (  # noqa: E402
    ResponseWindowClickEngine,
    _event_counts,
    _json_ready,
    _materialize_profile,
    _read_csv,
    _read_json,
    _write_json,
)
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-biggio-2017-known-parameter-validation.v1"
RECORD_ID = "biggio_2017_racket_tool_use"
TEMPLATE_CONTEXTS = {
    "biggio_2017_no_racket": "no_racket",
    "biggio_2017_common_racket": "common_racket",
    "biggio_2017_personal_racket": "personal_racket",
}
TEMPLATE_IDS = list(TEMPLATE_CONTEXTS)
MANUAL_REVIEW = (
    REPO_ROOT
    / "For-AI"
    / "audiotactile-paper-metadata-audit"
    / "manual_reviews"
    / f"{RECORD_ID}.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_biggio_2017_known_parameter_20260715"
EVIDENCE_BOUNDARY = (
    "This validates the software-known parameter contract for Biggio et al. "
    "(2017): paper-extracted static near/far 150 ms pink-noise bursts, no-racket, "
    "common-racket, and personal-racket session profiles, 30 near target, 30 far "
    "target, and 30 sound-only catch trials per session, Segment 0-6 GUI "
    "materialization, generated WAV packages, software wired-loopback sidecars, "
    "and mouse-click simulated participant-like responses to tactile targets. "
    "It does not claim exact physical reproduction of the original pink-noise "
    "asset, electrical pulse/current, far-sound propagation lead, ITI, voice-key "
    "threshold, participant behavior, or the human tool-use PPS effect."
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
        "three_session_profiles_validated": len(profile_reports) == 3 and all(item["passed"] for item in profile_reports),
        "combined_trial_count_matches_paper": sum(item["observed_contract"]["segment5_total_count"] for item in profile_reports) == 270,
        "combined_target_click_count_matches_response_rows": sum(item["observed_contract"]["mouse_click_count"] for item in profile_reports) == 180,
        "combined_catch_withhold_count_matches_paper": sum(
            item["observed_contract"]["participant_expected_response_counts"].get("withhold", 0)
            for item in profile_reports
        )
        == 90,
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
        "report_json": str(output_dir / "biggio_2017_known_parameter_validation_report.json"),
        "report_md": str(output_dir / "biggio_2017_known_parameter_validation_report.md"),
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
            "All extracted runnable stimulus, session-context, response, count, WAV, and runner contracts matched. "
            "The emulated run cannot estimate human tool-use PPS facilitation."
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


def _expected_contract_from_manual_review() -> dict[str, Any]:
    review = _read_json(MANUAL_REVIEW)
    return {
        "source": str(MANUAL_REVIEW),
        "review_confidence_label": review.get("confidence_label", ""),
        "review_confidence_score": review.get("confidence_score", ""),
        "sound_type": "pink_noise_burst",
        "sound_duration_ms": 150,
        "sound_level_db_spl": 70,
        "near_sound_to_tactile_soa_ms": 0,
        "far_sound_to_tactile_lead_ms": "derived_2_ms_not_author_reported",
        "near_distance_cm": 30.0,
        "far_distance_cm": 98.5,
        "near_far_spacing_cm": 68.5,
        "per_session_trial_count": 90,
        "per_session_audio_tactile_count": 60,
        "per_session_catch_count": 30,
        "per_session_respond_expected_count": 60,
        "per_session_withhold_expected_count": 30,
        "target_rows_by_distance": {"30.0": 30, "98.5": 30},
        "catch_rows_by_distance": {"30.0": 15, "98.5": 15},
        "session_tool_conditions": dict(TEMPLATE_CONTEXTS),
        "expected_scientific_outcome": (
            "Near-versus-far reaction times and racket/tool context are expected to index PPS modulation; "
            "the software validator can test the runnable parameter contract, not the human RT effect."
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
        "block_csv_counts": _block_contract_counts(block_rows),
        "package_block_count": len(package.blocks),
        "package_block_wavs": [str(block.wav_path) for block in package.blocks],
        "package_block_wav_facts": [runner_smoke._wav_facts(block.wav_path) for block in package.blocks],
        "event_counts": _event_counts(events),
        "participant_trial_count": len(participant_rows),
        "participant_outcome_counts": _count_values(participant_rows, "outcome"),
        "participant_expected_response_counts": _count_values(participant_rows, "expected_response"),
        "participant_response_given_counts": _count_values(participant_rows, "response_given"),
        "participant_family_counts": _count_values(participant_rows, "family"),
        "participant_tool_condition_counts": _count_values(participant_rows, "tool_condition"),
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_tool_condition_counts": _count_values(analysis_rows, "tool_condition"),
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
    tool_condition = TEMPLATE_CONTEXTS[template_id]
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
        and observed["segment3_catch_count"] == 2
        and observed["segment3_baseline_count"] == 0
        and observed["segment3_auditory_only_count"] == 0
        and observed["segment4_total_count"] == expected["per_session_trial_count"]
        and observed["segment5_total_count"] == expected["per_session_trial_count"]
        and observed["segment5_block_count"] == 1,
        "block_csv_matches_paper_trial_counts": counts["family"] == {"audio_tactile": 60, "catch": 30}
        and counts["expected_response"] == {"respond": 60, "withhold": 30}
        and counts["target_role"] == {"catch_no_target": 30, "tactile_target": 60}
        and counts["target_rows_by_distance"] == expected["target_rows_by_distance"]
        and counts["catch_rows_by_distance"] == expected["catch_rows_by_distance"],
        "block_csv_preserves_stimulus_parameters": counts["duration_ms"] == {"150": 90}
        and counts["audio_tactile_soa_by_distance"] == {"30.0": {"0": 30}, "98.5": {"2": 30}}
        and counts["spatial_value_cm"] == {"30.0": 45, "98.5": 45}
        and counts["noise_type"] == {"pink": 90},
        "block_csv_preserves_tool_and_apparatus_context": counts["tool_condition"] == {tool_condition: 90}
        and counts["response_capture_device"] == {"microphone": 90}
        and counts["voice_key_enabled"] == {"true": 90}
        and counts["tactile_stimulation_modality"] == {"electrical": 90}
        and counts["electrical_stimulator_model"] == {"Digitimer DS7AH HV": 90},
        "package_wavs_generated": len(package.blocks) == 1
        and all(Path(block.wav_path).is_file() and runner_smoke._wav_facts(block.wav_path).get("readable") for block in package.blocks),
        "runner_completed": bool(result.completed and not result.interrupted),
        "runner_events_match_expected_counts": observed["event_counts"].get("trial_start", 0) == 90
        and observed["event_counts"].get("trial_end", 0) == 90
        and observed["event_counts"].get("looming_onset", 0) == 90
        and observed["event_counts"].get("tactile_onset", 0) == 60
        and observed["event_counts"].get("response_window_onset", 0) == 90
        and observed["mouse_click_count"] == 60
        and observed["response_marker_count"] == 60,
        "participant_rows_match_expected_contract": observed["participant_trial_count"] == 90
        and observed["participant_outcome_counts"] == {"Hit": 90}
        and observed["participant_expected_response_counts"] == {"respond": 60, "withhold": 30}
        and observed["participant_response_given_counts"] == {"false": 30, "true": 60}
        and observed["participant_tool_condition_counts"] == {tool_condition: 90},
        "analysis_rows_preserve_tool_condition": observed["analysis_ready_trial_count"] == 60
        and observed["analysis_tool_condition_counts"] == {tool_condition: 60},
        "software_wired_loopback_written": observed["software_wired_loopback_count"] >= 1
        and all(item.get("readable") for item in observed["software_wired_loopback_facts"]),
    }


def _block_contract_counts(rows: list[dict[str, str]]) -> dict[str, Any]:
    target_rows = [row for row in rows if _lower(row.get("family")) == "audio_tactile"]
    catch_rows = [row for row in rows if _lower(row.get("family")) == "catch"]
    return {
        "family": _count_values(rows, "family"),
        "expected_response": _count_values(rows, "expected_response"),
        "target_role": _count_values(rows, "target_role"),
        "response_rule": _count_values(rows, "response_rule"),
        "duration_ms": _count_values(rows, "duration_ms"),
        "noise_type": _count_values(rows, "noise_type"),
        "soa_ms": _count_values(rows, "soa_ms"),
        "spatial_value_cm": _count_values(rows, "spatial_value_cm"),
        "tool_condition": _count_values(rows, "tool_condition"),
        "response_capture_device": _count_values(rows, "response_capture_device"),
        "voice_key_enabled": _count_values(rows, "voice_key_enabled"),
        "tactile_stimulation_modality": _count_values(rows, "tactile_stimulation_modality"),
        "electrical_stimulator_model": _count_values(rows, "electrical_stimulator_model"),
        "target_rows_by_distance": _count_values(target_rows, "spatial_value_cm"),
        "catch_rows_by_distance": _count_values(catch_rows, "spatial_value_cm"),
        "audio_tactile_soa_by_distance": _nested_counts(target_rows, "spatial_value_cm", "soa_ms"),
    }


def _nested_counts(rows: list[dict[str, str]], outer_key: str, inner_key: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        outer = str(row.get(outer_key) or "")
        inner = str(row.get(inner_key) or "")
        result.setdefault(outer, {})
        result[outer][inner] = result[outer].get(inner, 0) + 1
    return {outer: dict(sorted(inner.items())) for outer, inner in sorted(result.items())}


def _count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return dict(sorted(counts.items()))


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Biggio 2017 Known-Parameter Validation",
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


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Biggio 2017 known-parameter GUI/runner validation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args()
    report = run_validation(output_dir=args.output_dir, participant_id=args.participant_id)
    print(f"Wrote Biggio 2017 validation report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
