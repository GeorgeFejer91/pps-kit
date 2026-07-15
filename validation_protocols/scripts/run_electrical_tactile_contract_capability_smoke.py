"""Validate electrical tactile calibration metadata through the runner.

This smoke targets audiotactile PPS studies that report electrocutaneous or
electrical tactile stimulation/calibration parameters. It validates the
parsimonious software contract: row-level electrical tactile metadata can be
represented in a profile, propagated through the real runner path, and paired
with mouse-click simulated participant-like responses.
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


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SRC_ROOT, SCRIPT_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import run_ready_profile_runner_smoke as runner_smoke  # noqa: E402
from run_response_choice_contract_capability_smoke import ResponseChoiceSmokeAudioEngine  # noqa: E402
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-electrical-tactile-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_electrical_tactile_contract_20260715"
CONTRACT_FIELDS = {
    "tactile_stimulation_modality": "Tactile_Stimulation_Modality",
    "tactile_calibration_method": "Tactile_Calibration_Method",
    "tactile_threshold_reference": "Tactile_Threshold_Reference",
    "tactile_intensity": "Tactile_Intensity",
    "tactile_intensity_unit": "Tactile_Intensity_Unit",
    "tactile_pulse_duration_ms": "Tactile_Pulse_Duration_ms",
    "electrical_stimulator_model": "Electrical_Stimulator_Model",
    "electrical_electrode_site": "Electrical_Electrode_Site",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "electrical tactile stimulation and calibration metadata. It verifies "
    "prepared block CSVs, deterministic trial trigger metadata, local marker "
    "CSV/XDF output, participant rows, analysis rows, software wired-loopback "
    "sidecars, and mouse-click simulated participant-like responses. It is not "
    "physical electrical stimulation, current delivery, participant threshold "
    "finding, electrode impedance validation, physical stimulator "
    "synchronization, collected participant evidence, physical timing loopback, "
    "or scientific PPS-effect replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "electrical_tactile_calibration",
    "example_record_ids": [
        "serino_2007_blind_cane_users",
        "ronga_2021_newborn_erp",
        "serino_2015_toolless_sync_training",
        "canzoneri_2013_amputation_prosthesis",
    ],
    "supported_contract": {
        "tactile_stimulation_modality": "electrical or electrocutaneous tactile modality label",
        "tactile_calibration_method": "participant threshold, detection threshold, or paper calibration label",
        "tactile_threshold_reference": "paper-reported sensory/detection/pain threshold reference",
        "tactile_intensity": "paper-reported current or threshold multiple",
        "tactile_intensity_unit": "mA, threshold_multiple, or paper unit label",
        "tactile_pulse_duration_ms": "paper-reported pulse/stimulus duration",
        "electrical_stimulator_model": "paper-reported stimulator model when available",
        "electrical_electrode_site": "paper-reported electrode/body site",
    },
    "remaining_boundary": (
        "physical electrical current delivery, participant thresholding, "
        "electrode placement/impedance, and hardware synchronization remain "
        "outside this software metadata smoke"
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

    def _click_for_electrical_tactile(payload: dict[str, Any]) -> None:
        modality = _lower(_first(payload, "tactile_stimulation_modality", "Tactile_Stimulation_Modality"))
        expected = _lower(_first(payload, "expected_response", "Expected_Response"))
        if modality != "electrical" or expected == "withhold":
            return
        controller.events.flush_callback_events(timeout_s=0.5)
        time.sleep(engine.response_delay_s)
        controller.log_click(x=320, y=240, in_target=True)

    engine.set_tactile_callback(_click_for_electrical_tactile)
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
        "prepared_rows_preserve_electrical_tactile_contract": _rows_preserve_contract(block_rows, expected_count=4),
        "marker_payloads_preserve_electrical_tactile_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_electrical_tactile_contract": _trigger_dictionary_preserves_contract(
            trigger_dictionary
        ),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_preserve_electrical_tactile_contract": _rows_preserve_contract(
            participant_rows,
            expected_count=4,
            require_tactile_only=False,
        ),
        "analysis_rows_preserve_electrical_tactile_contract": _rows_preserve_contract(
            analysis_rows,
            expected_count=3,
            require_tactile_only=True,
        ),
        "mouse_clicks_logged_for_electrical_tactile_rows": _event_counts(events).get("mouse_click", 0) == 3,
        "response_markers_logged_for_electrical_tactile_rows": _event_counts(events).get("response_marker_start", 0)
        == 3,
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
        "block_row_stimulation_modalities": _count_values(block_rows, "Tactile_Stimulation_Modality"),
        "block_row_calibration_methods": _count_values(block_rows, "Tactile_Calibration_Method"),
        "block_row_threshold_references": _count_values(block_rows, "Tactile_Threshold_Reference"),
        "block_row_stimulator_models": _count_values(block_rows, "Electrical_Stimulator_Model"),
        "block_row_electrode_sites": _count_values(block_rows, "Electrical_Electrode_Site"),
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
        "report_json": str(output_dir / "electrical_tactile_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "electrical_tactile_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "electrical_tactile_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_wav = _write_wav(stim_root / "electrical_tactile_looming_proxy.wav", duration_s=0.50)
    baseline_wav = _write_wav(stim_root / "electrical_tactile_baseline_proxy.wav", duration_s=0.42, gain=0.0)
    rows = [
        _row(
            1,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.50,
            soa_ms=120.0,
            tactile_onset_s=0.120,
            threshold_reference="sensory_threshold",
            intensity="1.2",
            intensity_unit="threshold_multiple",
            pulse_duration_ms="100",
            electrode_site="right_index_finger",
            label="Electrical tactile looming target",
        ),
        _row(
            2,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.50,
            soa_ms=260.0,
            tactile_onset_s=0.260,
            threshold_reference="detection_threshold",
            intensity="2.5",
            intensity_unit="mA",
            pulse_duration_ms="100",
            electrode_site="right_wrist",
            label="Electrical tactile delayed looming target",
        ),
        _row(
            3,
            family="baseline",
            wav_path=baseline_wav,
            duration_s=0.42,
            soa_ms=0.0,
            tactile_onset_s=0.100,
            threshold_reference="participant_threshold",
            intensity="paper_reported",
            intensity_unit="threshold_multiple",
            pulse_duration_ms="200",
            electrode_site="right_index_finger",
            label="Electrical tactile-only baseline",
        ),
        _row(
            4,
            family="catch",
            wav_path=audio_wav,
            duration_s=0.50,
            soa_ms=0.0,
            tactile_onset_s=None,
            threshold_reference="condition_level_calibration",
            intensity="withhold",
            intensity_unit="threshold_multiple",
            pulse_duration_ms="100",
            electrode_site="right_index_finger",
            label="Electrical tactile calibration catch withhold",
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
                "block_label": "Electrical tactile contract validation",
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
    threshold_reference: str,
    intensity: str,
    intensity_unit: str,
    pulse_duration_ms: str,
    electrode_site: str,
    label: str,
) -> dict[str, str]:
    has_tactile = family in {"audio_tactile", "baseline"}
    return {
        "block_trial_index": str(trial_number),
        "trial_pool_index": str(trial_number),
        "family": family,
        "trial_type": {"audio_tactile": "Audio-Tactile", "baseline": "Baseline", "catch": "Catch"}[family],
        "row_label": label,
        "noise_type": "looming" if family in {"audio_tactile", "catch"} else "tactile_only",
        "soa_ms": f"{soa_ms:.0f}",
        "source_file_name": wav_path.name,
        "trial_file_path": str(wav_path),
        "source_sha256": _sha256(wav_path),
        "duration_ms": str(int(round(duration_s * 1000))),
        "duration_s": f"{duration_s:.6f}",
        "looming_segment_onset_s": "0.000",
        "tactile_onset_s": "" if tactile_onset_s is None else f"{tactile_onset_s:.6f}",
        "channels": "2",
        "tactile_channel": "3" if has_tactile else "",
        "tactile_stimulation_modality": "electrical",
        "tactile_calibration_method": "participant_threshold",
        "tactile_threshold_reference": threshold_reference,
        "tactile_intensity": intensity,
        "tactile_intensity_unit": intensity_unit,
        "tactile_pulse_duration_ms": pulse_duration_ms,
        "electrical_stimulator_model": "DS7A",
        "electrical_electrode_site": electrode_site,
        "expected_response": "respond" if has_tactile else "withhold",
        "response_rule": "mouse-click emulation of electrical tactile target detection",
        "target_role": "target" if has_tactile else "catch_no_target",
        "response_mode": "tactile_detection" if has_tactile else "withhold",
        "response_capture_device": "mouse_click_emulation",
        "response_input_modality": "manual",
        "primary_analysis_included": "true" if has_tactile else "false",
        "configured_repetitions": "1",
        "repetition_index": "1",
        "fractional_extra": "0",
    }


def _write_wav(path: Path, *, duration_s: float, gain: float = 0.03, sample_rate: int = 44100) -> Path:
    frames = max(1, int(round(duration_s * sample_rate)))
    t = np.arange(frames, dtype=np.float32) / float(sample_rate)
    data = np.zeros((frames, 2), dtype=np.float32)
    data[:, 0] = gain * np.sin(2.0 * np.pi * 440.0 * t)
    data[:, 1] = gain * np.sin(2.0 * np.pi * 620.0 * t)
    sf.write(path, data, sample_rate)
    return path


def _rows_preserve_contract(
    rows: list[dict[str, Any]],
    *,
    expected_count: int,
    require_tactile_only: bool = False,
) -> bool:
    if len(rows) != expected_count:
        return False
    checked = []
    for row in rows:
        if require_tactile_only and _family(row) == "catch":
            continue
        checked.append(row)
    return bool(checked) and all(_row_has_contract(row) for row in checked)


def _marker_payloads_preserve_contract(rows: list[dict[str, Any]]) -> bool:
    trial_payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = _payload(row)
        event_type = str(
            row.get("event_type") or row.get("Event_Type") or payload.get("event_type") or payload.get("Event_Type") or ""
        ).strip()
        if event_type in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end"}:
            trial_payloads.append(payload)
    electrode_sites = {
        str(payload.get("electrical_electrode_site") or payload.get("Electrical_Electrode_Site") or "").strip()
        for payload in trial_payloads
        if _row_has_contract(payload)
    }
    return {"right_index_finger", "right_wrist"}.issubset(electrode_sites)


def _trigger_dictionary_preserves_contract(data: dict[str, Any]) -> bool:
    triggers = data.get("triggers") if isinstance(data, dict) else None
    if not isinstance(triggers, list):
        return False
    electrode_sites = {
        str(item.get("electrical_electrode_site") or item.get("Electrical_Electrode_Site") or "").strip()
        for item in triggers
        if isinstance(item, dict) and str(item.get("trigger_key") or "").startswith("trial:") and _row_has_contract(item)
    }
    return {"right_index_finger", "right_wrist"}.issubset(electrode_sites)


def _row_has_contract(row: dict[str, Any]) -> bool:
    for lower, title in CONTRACT_FIELDS.items():
        value = row.get(lower, row.get(title, ""))
        if value in (None, ""):
            return False
    return True


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload_json") or row.get("Payload_JSON") or row.get("payload") or ""
    if isinstance(payload, dict):
        return dict(payload)
    try:
        data = json.loads(str(payload))
    except (TypeError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _first(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _family(row: dict[str, Any]) -> str:
    return str(row.get("family") or row.get("Family") or row.get("trial_type") or row.get("Trial_Type") or "").strip().lower()


def _family_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        family = _family(row)
        if family:
            counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _count_values(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field) or "").strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _event_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        event_type = str(row.get("event_type") or row.get("Event_Type") or "").strip()
        if not event_type:
            payload = _payload(row)
            event_type = str(payload.get("event_type") or payload.get("Event_Type") or "").strip()
        if event_type:
            counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items()))


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path or not Path(path).is_file():
        return []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_json(path: Path) -> dict[str, Any]:
    if not path or not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Electrical Tactile Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Stimulation modalities: `{report['block_row_stimulation_modalities']}`",
        f"- Calibration methods: `{report['block_row_calibration_methods']}`",
        f"- Stimulator models: `{report['block_row_stimulator_models']}`",
        f"- Electrode sites: `{report['block_row_electrode_sites']}`",
        f"- Event counts: `{report['event_counts']}`",
        "",
        "## Criteria",
    ]
    for key, value in report["criteria"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Evidence Boundary", "", report["evidence_boundary"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
