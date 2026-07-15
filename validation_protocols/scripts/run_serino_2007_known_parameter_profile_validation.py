"""Validate the Serino 2007 known-parameter PPS profile through GUI bakes and runner.

This is a paper-specific known-parameter validation. It starts from the local
manual PDF audit, loads the Serino 2007 profile through DashboardController,
bakes Segments 2-6, prepares a participant package, and runs it with
mouse-click-simulated responses. The profile remains blocked for full
publication recreation because the paper did not report exact source/noise,
electrical pulse, ITI, or voice-key threshold parameters.
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

import numpy as np
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
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-serino-2007-known-parameter-validation.v1"
TEMPLATE_ID = "serino_2007_blind_cane_users"
MANUAL_REVIEW = REPO_ROOT / "For-AI" / "audiotactile-paper-metadata-audit" / "manual_reviews" / f"{TEMPLATE_ID}.json"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_serino_2007_known_parameter_20260715"
EVIDENCE_BOUNDARY = (
    "This validates the software-known parameter contract for Serino 2007: "
    "paper-extracted row counts, near/far SOAs, near/far distances, weak-target "
    "respond rows, strong-nontarget withhold rows, auditory-only catch rows, "
    "Segment 2-6 GUI materialization, generated WAV packages, software "
    "wired-loopback sidecars, and mouse-click simulated participant-like "
    "responses. It does not claim exact physical reproduction of the original "
    "white-noise asset, electrical pulse/current, ITI, response window, "
    "voice-key threshold, participant behavior, or the scientific PPS effect."
)


class FastLoopbackEngine(runner_smoke.FastProfileSmokeAudioEngine):
    def __init__(self, *, max_clicks_per_block: int = 10_000):
        super().__init__(max_clicks_per_block=max_clicks_per_block, response_delay_s=0.0)
        self.wired_loopback_mode = "off"
        self.wired_loopback_recordings: list[str] = []

    def set_wired_loopback_mode(self, mode: str) -> None:
        self.wired_loopback_mode = str(mode or "off")

    def start_wired_loopback_recording(self, output_path=None, mode=None, sample_rate=None) -> bool:
        if mode is not None:
            self.set_wired_loopback_mode(str(mode))
        if output_path:
            self.wired_loopback_recordings.append(str(output_path))
        return True

    def stop_wired_loopback_recording(self, output_path=None, interrupted=False):
        if not output_path:
            return None
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        source = getattr(self, "_current_block_path", None)
        if source is not None and Path(source).is_file():
            shutil.copyfile(source, target)
        else:
            sf.write(target, np.zeros((1, 3), dtype=np.float32), getattr(self, "_sample_rate", 44100))
        return None


def run_validation(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = _expected_contract_from_manual_review()
    materialized = _materialize_known_parameter_profile(output_dir=output_dir)
    run_manifest = Path(materialized["segment6_manifest_path"])
    package = prepare_segment_run_package(
        run_manifest,
        participant_id=participant_id,
        design=materialized["design"],
        session_root=output_dir / "sessions",
        use_block_cache=False,
    )
    engine = GoNoGoSmokeAudioEngine(max_clicks_per_block=10_000, response_delay_s=0.12)
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

    def _click_expected_targets(payload: dict[str, Any]) -> None:
        expected_response = _lower(_first(payload, "expected_response", "Expected_Response"))
        if expected_response != "respond":
            return
        controller.events.flush_callback_events(timeout_s=0.2)
        time.sleep(engine.response_delay_s)
        controller.log_click(x=320, y=240, in_target=True)
        engine._block_start_perf += engine.response_delay_s

    engine.set_tactile_callback(_click_expected_targets)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)

    observed = _observed_contract(materialized, package, result)
    criteria = _criteria(expected, materialized, observed, result, package)
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "template_id": TEMPLATE_ID,
        "passed": all(criteria.values()),
        "criteria": criteria,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "expected_contract": expected,
        "observed_contract": observed,
        "materialization": _json_ready({key: value for key, value in materialized.items() if key != "design"}),
        "participant_id": participant_id,
        "run_setup_manifest": str(run_manifest),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "runner_completed": bool(result.completed and not result.interrupted),
        "events_csv": str(result.events_csv),
        "events_xdf": str(result.events_xdf),
        "analysis_outputs": {key: str(value) for key, value in result.analysis_outputs.items()},
        "software_wired_loopback_wavs": [
            str(path)
            for path in package.session_dir.glob("*wired_loopback*.wav")
        ],
        "report_json": str(output_dir / "serino_2007_known_parameter_validation_report.json"),
        "report_md": str(output_dir / "serino_2007_known_parameter_validation_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _materialize_known_parameter_profile(*, output_dir: Path) -> dict[str, Any]:
    batch_root = output_dir / "dashboard_gui_materialization"
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
    block_manifest = dashboard_app._load_json(dashboard_app._block_csv_preview_manifest_path(project.project_dir))
    block_csv = Path(str(block_manifest["blocks"][0]["csv_path"]))
    block_rows = _read_csv(block_csv)
    return {
        "design": design,
        "project_dir": str(project.project_dir),
        "selected_template": state.get("selected_template", ""),
        "profile_read_only": not bool((state.get("custom_workflow") or {}).get("is_custom")),
        "profile_gate_runner_readiness": dashboard_app._profile_recreation_status_for_design(design).get(
            "runner_readiness",
            "",
        ),
        "profile_gate_segment_6_launchable": bool(
            dashboard_app._profile_recreation_status_for_design(design).get("segment_6_launchable", False)
        ),
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


def _expected_contract_from_manual_review() -> dict[str, Any]:
    review = _read_json(MANUAL_REVIEW)
    return {
        "source": str(MANUAL_REVIEW),
        "review_confidence": review.get("confidence", ""),
        "sound_duration_ms": 150,
        "sound_type": "white_noise",
        "sound_level_db_spl": 70,
        "near_soa_ms": 0,
        "far_soa_ms": 5,
        "near_distance_cm": 30.0,
        "far_distance_cm": 125.0,
        "audio_tactile_trial_count": 120,
        "catch_trial_count": 30,
        "total_trial_count": 150,
        "weak_target_count": 60,
        "strong_nontarget_count": 60,
        "respond_expected_count": 60,
        "withhold_expected_count": 90,
        "row_contract": {
            "weak_target_near": {"count": 30, "soa_ms": 0, "spatial_value_cm": 30.0, "expected_response": "respond"},
            "weak_target_far": {"count": 30, "soa_ms": 5, "spatial_value_cm": 125.0, "expected_response": "respond"},
            "strong_nontarget_near": {"count": 30, "soa_ms": 0, "spatial_value_cm": 30.0, "expected_response": "withhold"},
            "strong_nontarget_far": {"count": 30, "soa_ms": 5, "spatial_value_cm": 125.0, "expected_response": "withhold"},
            "auditory_only_catch": {"count": 30, "expected_response": "withhold", "target_role": "catch_no_target"},
        },
        "remaining_missing_publication_parameters": [
            "exact white-noise source asset, seed, and spectral recipe",
            "exact electrical tactile pulse duration, waveform, current, and electrode impedance calibration",
            "exact ITI or jitter distribution and numeric response window",
            "exact voice-key response capture threshold and latency correction",
        ],
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
        "segment3_catch_count": int(materialized["segment3"]["catch_count"]),
        "segment4_total_count": int(materialized["segment4"]["total_count"]),
        "segment4_audio_tactile_count": int(materialized["segment4"]["audio_tactile_count"]),
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
        "participant_target_role_counts": _count_values(participant_rows, "target_role"),
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_ready_expected_response_counts": _count_values(analysis_rows, "expected_response"),
        "mouse_click_count": _event_counts(events).get("mouse_click", 0),
        "response_marker_count": _event_counts(events).get("response_marker_start", 0),
        "software_wired_loopback_count": len(loopback_paths),
        "software_wired_loopback_facts": [runner_smoke._wav_facts(path) for path in loopback_paths],
        "runner_completed": bool(result.completed and not result.interrupted),
    }


def _criteria(expected: dict[str, Any], materialized: dict[str, Any], observed: dict[str, Any], result: Any, package: Any) -> dict[str, bool]:
    counts = observed["block_csv_counts"]
    return {
        "manual_review_loaded": Path(expected["source"]).is_file(),
        "gui_loaded_profile_read_only": materialized["selected_template"] == TEMPLATE_ID and bool(materialized["profile_read_only"]),
        "profile_gate_remains_blocked_for_unreported_parameters": materialized["profile_gate_runner_readiness"] == "blocked_missing_parameters"
        and materialized["profile_gate_segment_6_launchable"] is False,
        "segments_2_to_6_materialized": observed["segment2_variant_count"] == 4
        and observed["segment3_audio_tactile_count"] == 4
        and observed["segment3_catch_count"] == 4
        and observed["segment4_total_count"] == expected["total_trial_count"]
        and observed["segment5_total_count"] == expected["total_trial_count"]
        and observed["segment5_block_count"] == 1
        and Path(materialized["segment6_manifest_path"]).is_file(),
        "block_csv_matches_expected_trial_counts": counts["family"] == {"audio_tactile": 120, "catch": 30}
        and counts["expected_response"] == {"respond": 60, "withhold": 90}
        and counts["target_role"] == {"weak_target": 60, "strong_nontarget": 60, "catch_no_target": 30},
        "block_csv_matches_expected_row_parameters": counts["audio_row_contract"] == {
            "weak_target|0|30.0|respond": 30,
            "weak_target|5|125.0|respond": 30,
            "strong_nontarget|0|30.0|withhold": 30,
            "strong_nontarget|5|125.0|withhold": 30,
        },
        "package_wavs_generated": len(package.blocks) == 1
        and all(Path(block.wav_path).is_file() and runner_smoke._wav_facts(block.wav_path).get("readable") for block in package.blocks),
        "runner_completed": bool(result.completed and not result.interrupted),
        "mouse_clicks_match_expected_respond_rows": observed["mouse_click_count"] == expected["respond_expected_count"]
        and observed["response_marker_count"] == expected["respond_expected_count"],
        "participant_rows_preserve_expected_contract_and_click_budget": observed["participant_trial_count"] == expected["total_trial_count"]
        and observed["participant_expected_response_counts"] == {"respond": 60, "withhold": 90}
        and observed["participant_target_role_counts"] == {"catch_no_target": 30, "strong_nontarget": 60, "weak_target": 60}
        and observed["mouse_click_count"] == expected["respond_expected_count"],
        "software_wired_loopback_written": observed["software_wired_loopback_count"] >= 1
        and all(item.get("readable") for item in observed["software_wired_loopback_facts"]),
    }


def _block_contract_counts(rows: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    audio_rows = [row for row in rows if row.get("family") == "audio_tactile"]
    return {
        "family": _count_values(rows, "family"),
        "expected_response": _count_values(rows, "expected_response"),
        "target_role": _count_values(rows, "target_role"),
        "soa_ms": _count_values(rows, "soa_ms"),
        "spatial_value_cm": _count_values(rows, "spatial_value_cm"),
        "audio_row_contract": dict(
            sorted(
                Counter(
                    f"{row.get('target_role')}|{row.get('soa_ms')}|{row.get('spatial_value_cm')}|{row.get('expected_response')}"
                    for row in audio_rows
                ).items()
            )
        ),
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
        "# Serino 2007 Known-Parameter Validation",
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
            f"- Expected total trials: `{report['expected_contract']['total_trial_count']}`",
            f"- Observed block CSV counts: `{json.dumps(report['observed_contract']['block_csv_counts'], sort_keys=True)}`",
            f"- Observed event counts: `{json.dumps(report['observed_contract']['event_counts'], sort_keys=True)}`",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser = argparse.ArgumentParser(description="Run Serino 2007 known-parameter GUI/runner validation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args()
    report = run_validation(output_dir=args.output_dir, participant_id=args.participant_id)
    print(f"Wrote Serino 2007 validation report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
