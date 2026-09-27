"""Validate the Canzoneri 2013 tool-use PPS profile end to end.

This paper-specific validator starts from the public full-text/protocol-lineage
review, loads the profile through DashboardController, bakes Segments 2-6,
prepares runnable WAV packages, runs SessionRunnerController with software
wired-loopback sidecars, injects mouse-click responses for tactile target and
baseline rows, withholds responses for auditory-only catches, and compares the
observed software contract with the paper-extracted PPS assessment parameters.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_ready_profile_runner_smoke as runner_smoke  # noqa: E402
from run_canzoneri_2013_amputation_known_parameter_profile_validation import (  # noqa: E402
    TactileOnsetClickEngine,
)
from run_tajadura_2009_known_parameter_profile_validation import (  # noqa: E402
    _accept_segment5,
    _event_counts,
    _json_ready,
    _lower,
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


from peripersonal_space_toolkit.paper_audit import audit_paths  # noqa: E402


SCHEMA = "pps-canzoneri-2013-tool-use-known-parameter-validation.v1"
RECORD_ID = "canzoneri_2013_tool_use_reshaping"
TEMPLATE_ID = "canzoneri_2013_tool_use_reshaping"
MANUAL_REVIEW = audit_paths(REPO_ROOT).audit_dir / "manual_reviews" / f'{RECORD_ID}.json'
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT
    / "artifacts"
    / "validation_runs"
    / "current_goal_canzoneri_2013_tool_use_known_parameter_20260716"
)
EVIDENCE_BOUNDARY = (
    "This validates the software-known parameter contract for Canzoneri et al. "
    "(2013) tool-use PPS reshaping: public full-text and Canzoneri 2012 "
    "protocol-lineage parameters, 3000 ms IN/OUT pink-noise sounds, 1000 ms "
    "pre/post sound-silence metadata, right-forearm tactile target context, "
    "T1-T5 tactile delays, T0/T6 tactile-only baselines, 76 auditory-only "
    "catches, two assessment blocks, Segment 0-6 GUI materialization, "
    "generated WAV packages, software wired-loopback sidecars, and mouse-click "
    "simulated participant-like responses to tactile rows. The physical "
    "20-minute tool-use and pointing-control interventions are retained as "
    "source context and are not automated runner phases. This does not claim "
    "exact original SoundForge pink-noise/gain files, loudspeaker/room "
    "transfer equivalence, participant-level electrical current calibration, "
    "voice-key latency equivalence, collected human behavior, or the published "
    "PPS/body-representation effect replication."
)


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
        "generated_on": date.today().isoformat(),
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
                "All runnable stimulus, timing, catch, baseline, response, count, WAV, and runner "
                "contracts matched the source-derived PPS assessment contract. The emulated run cannot "
                "estimate tool-use-induced PPS/body-representation plasticity or participant behavior."
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
        "report_json": str(output_dir / "canzoneri_2013_tool_use_known_parameter_validation_report.json"),
        "report_md": str(output_dir / "canzoneri_2013_tool_use_known_parameter_validation_report.md"),
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
    segment5 = dashboard_app._bake_block_csv_preview(
        design,
        project.project_dir,
        {"kind": "block_csv_preview", "label": "5_block_csv_preview", "block_count": design.protocol.blocks},
    )
    _accept_segment5(project.project_dir)
    segment6 = dashboard_app._write_run_setup_outputs(project.project_dir, design)
    final_segment_status = _segment_status_map(project, design)
    block_manifest = dashboard_app._load_json(dashboard_app._block_csv_preview_manifest_path(project.project_dir))
    block_rows: list[dict[str, str]] = []
    for block in block_manifest.get("blocks", []):
        block_rows.extend(_read_csv(block.get("csv_path", "")))
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
        "segment5_block_rows": block_rows,
        "block_csv_counts": _block_contract_counts(block_rows),
    }


def _expected_contract_from_manual_review() -> dict[str, Any]:
    review = _read_json(MANUAL_REVIEW)
    return {
        "source": str(MANUAL_REVIEW),
        "review_confidence_label": review.get("confidence_label", ""),
        "review_confidence_score": review.get("confidence_score", ""),
        "source_url": "https://link.springer.com/article/10.1007/s00221-013-3532-2",
        "public_full_text_url": (
            "https://www.researchgate.net/publication/236614179_"
            "Tool-use_reshapes_the_boundaries_of_body_and_peripersonal_space_representations"
        ),
        "protocol_lineage_review": (
            "For-AI/research/literature/audiotactile-paper-metadata-audit/manual_reviews/canzoneri_2012_dynamic_sounds.json"
        ),
        "sound_type": "pink_noise_dynamic_in_out",
        "sound_duration_ms": 3000,
        "pre_sound_silence_ms": 1000,
        "post_sound_silence_ms": 1000,
        "soa_values_ms": [300, 800, 1500, 2200, 2700],
        "baseline_soa_values_ms": [-700, 3600],
        "spatial_distance_labels": ["D1", "D2", "D3", "D4", "D5"],
        "trajectory_count": 2,
        "trajectory_labels": ["IN/approaching", "OUT/receding"],
        "tactile_site": "right forearm",
        "tactile_modality": "electrical_stimulation_above_threshold",
        "target_repetitions_per_delay_direction": 8,
        "audio_tactile_trial_count": 80,
        "baseline_trial_count": 32,
        "tactile_target_trial_count": 112,
        "catch_trial_count": 76,
        "total_runnable_trial_count": 188,
        "block_count": 2,
        "expected_response_counts": {"respond": 112, "withhold": 76},
        "expected_family_counts": {"audio_tactile": 80, "baseline": 32, "catch": 76},
        "expected_scientific_outcome": (
            "Tool-use is expected to shift the fitted PPS boundary toward farther auditory locations "
            "and change forearm body-representation metrics; pointing control is not expected to "
            "produce the same PPS/BR shift. The software validator tests the runnable PPS assessment "
            "contract, not human training-induced plasticity."
        ),
    }


def _observed_contract(materialized: dict[str, Any], package: Any, result: Any) -> dict[str, Any]:
    block_rows = materialized["segment5_block_rows"]
    events = _read_csv(result.events_csv)
    participant_rows = _read_csv(result.analysis_outputs.get("participant_trials", Path()))
    analysis_rows = _read_csv(result.analysis_outputs.get("analysis_ready_trials", Path()))
    loopback_paths = [path for path in package.session_dir.glob("*wired_loopback*.wav")]
    event_counts = _event_counts(events)
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
        "event_counts": event_counts,
        "participant_trial_count": len(participant_rows),
        "participant_outcome_counts": _count_values(participant_rows, "outcome"),
        "participant_expected_response_counts": _count_values(participant_rows, "expected_response"),
        "participant_response_given_counts": _count_values(participant_rows, "response_given"),
        "participant_family_counts": _count_values(participant_rows, "family"),
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_outcome_counts": _count_values(analysis_rows, "outcome"),
        "mouse_click_count": event_counts.get("mouse_click", 0),
        "response_marker_count": event_counts.get("response_marker_start", 0),
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
    expected_total = expected["total_runnable_trial_count"]
    expected_tactile = expected["tactile_target_trial_count"]
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
        "segment_bakes_match_expected_counts": observed["segment2_variant_count"] == 2
        and observed["segment3_audio_tactile_count"] == 10
        and observed["segment3_baseline_count"] == 4
        and observed["segment3_catch_count"] == 2
        and observed["segment4_total_count"] == expected_total
        and observed["segment4_audio_tactile_count"] == expected["audio_tactile_trial_count"]
        and observed["segment4_baseline_count"] == expected["baseline_trial_count"]
        and observed["segment4_catch_count"] == expected["catch_trial_count"]
        and observed["segment5_total_count"] == expected_total
        and observed["segment5_block_count"] == expected["block_count"],
        "block_csv_matches_family_counts": counts["family"] == expected["expected_family_counts"],
        "block_csv_preserves_response_contract": counts["expected_response"] == expected["expected_response_counts"]
        and counts["target_role"] == {"catch_no_target": 76, "tactile_target": 112},
        "block_csv_preserves_soa_baseline_and_direction_factors": counts["audio_tactile_soa_ms"] == {
            "300": 16,
            "800": 16,
            "1500": 16,
            "2200": 16,
            "2700": 16,
        }
        and counts["baseline_soa_ms"] == {"-700": 16, "3600": 16}
        and counts["catch_soa_ms"] == {"0": 76}
        and counts["audio_tactile_sequence_variant_key"] == {
            "pink_moving_sound": 40,
            "pink_moving_sound_receding": 40,
        }
        and counts["baseline_sequence_variant_key"] == {
            "pink_moving_sound": 16,
            "pink_moving_sound_receding": 16,
        }
        and counts["catch_sequence_variant_key"] == {
            "pink_moving_sound": 38,
            "pink_moving_sound_receding": 38,
        },
        "block_csv_preserves_apparatus_response_metadata": counts["response_capture_device"] == {"microphone": 188}
        and counts["voice_key_enabled"] == {"true": 188}
        and counts["tactile_stimulation_modality"] == {"electrical": 188}
        and counts["tool_condition"] == {"tool_use_pps_assessment": 188},
        "package_wavs_generated": len(package.blocks) == expected["block_count"]
        and all(Path(block.wav_path).is_file() and runner_smoke._wav_facts(block.wav_path).get("readable") for block in package.blocks),
        "runner_completed": bool(result.completed and not result.interrupted),
        "runner_events_match_expected_counts": observed["event_counts"].get("trial_start", 0) == expected_total
        and observed["event_counts"].get("trial_end", 0) == expected_total
        and observed["event_counts"].get("tactile_onset", 0) == expected_tactile
        and observed["mouse_click_count"] == expected["expected_response_counts"]["respond"]
        and observed["response_marker_count"] == expected["expected_response_counts"]["respond"],
        "participant_rows_match_expected_contract": observed["participant_trial_count"] == expected_total
        and observed["participant_outcome_counts"] == {"Hit": expected_total}
        and observed["participant_expected_response_counts"] == expected["expected_response_counts"]
        and observed["participant_response_given_counts"] == {"false": 76, "true": 112}
        and observed["participant_family_counts"] == expected["expected_family_counts"],
        "software_wired_loopback_written": observed["software_wired_loopback_count"] >= expected["block_count"]
        and all(item.get("readable") for item in observed["software_wired_loopback_facts"]),
    }


def _block_contract_counts(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    audio_rows = [row for row in rows if _lower(row.get("family")) == "audio_tactile"]
    baseline_rows = [row for row in rows if _lower(row.get("family")) == "baseline"]
    catch_rows = [row for row in rows if _lower(row.get("family")) == "catch"]
    return {
        "family": _count_values(rows, "family"),
        "expected_response": _count_values(rows, "expected_response"),
        "target_role": _count_values(rows, "target_role"),
        "response_rule": _count_values(rows, "response_rule"),
        "soa_ms": _count_values(rows, "soa_ms"),
        "audio_tactile_soa_ms": _count_values(audio_rows, "soa_ms"),
        "baseline_soa_ms": _count_values(baseline_rows, "soa_ms"),
        "catch_soa_ms": _count_values(catch_rows, "soa_ms"),
        "sequence_variant_key": _count_values(rows, "sequence_variant_key"),
        "audio_tactile_sequence_variant_key": _count_values(audio_rows, "sequence_variant_key"),
        "baseline_sequence_variant_key": _count_values(baseline_rows, "sequence_variant_key"),
        "catch_sequence_variant_key": _count_values(catch_rows, "sequence_variant_key"),
        "sequence_labels": _count_values(rows, "sequence_labels"),
        "response_capture_device": _count_values(rows, "response_capture_device"),
        "voice_key_enabled": _count_values(rows, "voice_key_enabled"),
        "tactile_stimulation_modality": _count_values(rows, "tactile_stimulation_modality"),
        "electrical_stimulator_model": _count_values(rows, "electrical_stimulator_model"),
        "tool_condition": _count_values(rows, "tool_condition"),
        "tactile_enabled": _count_values(rows, "tactile_enabled"),
    }


def _count_values(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return dict(sorted(counts.items()))


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Canzoneri 2013 Tool-Use Known-Parameter Validation",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Record: `{RECORD_ID}`",
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
            "## Observed Contract",
            "",
            f"- Segment 5 counts: `{json.dumps(report['observed_contract']['block_csv_counts'], sort_keys=True)}`",
            f"- Event counts: `{json.dumps(report['observed_contract']['event_counts'], sort_keys=True)}`",
            f"- Participant outcomes: `{json.dumps(report['observed_contract']['participant_outcome_counts'], sort_keys=True)}`",
            f"- Observed-vs-expected: {report['observed_vs_expected_outcome']['observed_emulated_outcome']}",
            "",
            "## Intervention Boundary",
            "",
            "- The runner validation covers the reusable PPS assessment task; the physical tool-use and pointing-control training procedures remain source context.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Canzoneri 2013 tool-use known-parameter GUI/runner validation."
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args()
    report = run_validation(output_dir=args.output_dir, participant_id=args.participant_id)
    print(json.dumps({"passed": report["passed"], "report_json": report["report_json"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
