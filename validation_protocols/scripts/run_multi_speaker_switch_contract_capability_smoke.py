"""Validate row-level multi-speaker switching contracts.

This smoke targets published PPS paradigms that used physical speaker arrays
or switched loudspeaker routes. It builds a tiny Segment 5/6-style fixture,
declares a parsimonious speaker-switch schedule in each row, materializes a
real runnable multichannel block WAV, runs the real SessionRunnerController
path, and checks simulated participant-like mouse clicks.
"""

from __future__ import annotations

import argparse
import csv
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


SCHEMA = "pps-multi-speaker-switch-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_multi_speaker_switch_contract_20260715"
)
CONTRACT_FIELDS = {
    "audio_output_mode": "Audio_Output_Mode",
    "speaker_array_id": "Speaker_Array_ID",
    "speaker_array_layout": "Speaker_Array_Layout",
    "speaker_switch_sequence": "Speaker_Switch_Sequence",
    "speaker_switch_times_ms": "Speaker_Switch_Times_ms",
    "speaker_switch_channels": "Speaker_Switch_Channels",
    "speaker_switch_gains": "Speaker_Switch_Gains",
    "speaker_source_channel": "Speaker_Source_Channel",
    "speaker_switch_generated": "Speaker_Switch_Generated",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "multi-speaker switching. It verifies that declared channel/time/gain "
    "schedules become runnable multichannel block WAVs and survive prepared "
    "block CSVs, marker payloads, trigger dictionaries, local marker XDF "
    "mirrors, participant rows, analysis rows, software wired-loopback "
    "sidecars, and mouse-click simulated participant-like responses. It is "
    "not physical loudspeaker-array validation, room acoustics, SPL transfer, "
    "hardware route calibration, collected participant behavior, physical "
    "timing loopback, exact original apparatus reconstruction, or scientific "
    "PPS-effect replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "multi_speaker_array_switching",
    "example_record_ids": ["serino_2015_exps_4_to_6"],
    "supported_contract": {
        "audio_output_mode": "switched_speaker_array",
        "speaker_switch_channels": "1-based output channel sequence such as 1|2|4",
        "speaker_switch_times_ms": "N+1 switch boundaries, or N segment starts plus implicit row end",
        "speaker_switch_gains": "optional one gain per switched segment",
        "speaker_source_channel": "source channel number or mixdown",
    },
    "remaining_boundary": (
        "paper-specific distance, body site, speaker layout, gain/SPL transfer, "
        "and exact physical apparatus validation remain outside this software smoke"
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

    def _click_for_tactile(_payload: dict[str, Any]) -> None:
        controller.events.flush_callback_events(timeout_s=0.5)
        time.sleep(engine.response_delay_s)
        controller.log_click(x=500, y=250, in_target=True)

    engine.set_tactile_callback(_click_for_tactile)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)

    block_rows = [row for block in package.blocks for row in _read_csv(block.manifest_path)]
    events = _read_csv(result.events_csv)
    markers = _read_csv(result.lsl_markers_csv or Path())
    participant_rows = _read_csv(result.analysis_outputs.get("participant_trials", Path()))
    analysis_rows = _read_csv(result.analysis_outputs.get("analysis_ready_trials", Path()))
    trigger_dictionary = _read_json(result.trigger_dictionary_path or Path())
    loopback_path = package.session_dir / "block_01_wired_loopback_input4.wav"
    block_wav_path = package.blocks[0].wav_path if package.blocks else Path()
    wav_energy = _speaker_switch_wav_energy_summary(block_wav_path, block_rows)
    criteria = {
        "completed": bool(result.completed and not result.interrupted),
        "block_wav_generated": len(package.blocks) == 1 and block_wav_path.is_file(),
        "block_wav_has_multichannel_speaker_routes": bool(wav_energy.get("passed")),
        "software_wired_loopback_written": loopback_path.is_file()
        and bool(runner_smoke._wav_facts(loopback_path).get("readable")),
        "prepared_rows_preserve_multi_speaker_switch_contract": _rows_preserve_contract(block_rows, expected_count=2),
        "marker_payloads_preserve_multi_speaker_switch_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_multi_speaker_switch_contract": _trigger_dictionary_preserves_contract(
            trigger_dictionary
        ),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_preserve_multi_speaker_switch_contract": _rows_preserve_contract(
            participant_rows,
            expected_count=2,
        ),
        "analysis_rows_preserve_multi_speaker_switch_contract": _rows_preserve_contract(
            analysis_rows,
            expected_count=2,
        ),
        "mouse_clicks_logged_for_switched_rows": _event_counts(events).get("mouse_click", 0) == 2,
        "response_markers_logged_for_switched_rows": _event_counts(events).get("response_marker_start", 0) == 2,
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
        "block_wav": str(block_wav_path),
        "block_wav_facts": runner_smoke._wav_facts(block_wav_path),
        "speaker_switch_energy_summary": wav_energy,
        "block_row_family_counts": _family_counts(block_rows),
        "block_row_audio_output_modes": _count_values(block_rows, "Audio_Output_Mode"),
        "block_row_switch_channels": _count_values(block_rows, "Speaker_Switch_Channels"),
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
        "report_json": str(output_dir / "multi_speaker_switch_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "multi_speaker_switch_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "multi_speaker_switch_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_wav = _write_wav(stim_root / "speaker_switch_source.wav", duration_s=0.60, gain=0.08)
    rows = [
        _row(
            1,
            wav_path=audio_wav,
            channel_sequence="1|2|4",
            label_sequence="front_near|front_mid|front_far",
            gains="1|0.7|0.4",
            label="Front speaker switch approaching row",
        ),
        _row(
            2,
            wav_path=audio_wav,
            channel_sequence="4|2|1",
            label_sequence="rear_far|rear_mid|rear_near",
            gains="0.4|0.7|1",
            label="Rear speaker switch receding row",
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
                "block_label": "Multi-speaker switching contract validation",
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
    channel_sequence: str,
    label_sequence: str,
    gains: str,
    label: str,
) -> dict[str, str]:
    duration_s = 0.60
    return {
        "block_trial_index": str(trial_number),
        "trial_pool_index": str(trial_number),
        "family": "audio_tactile",
        "trial_type": "Audio-Tactile",
        "row_label": label,
        "noise_type": "pink_noise_proxy",
        "soa_ms": "300",
        "source_file_name": wav_path.name,
        "trial_file_path": str(wav_path),
        "source_sha256": _sha256(wav_path),
        "duration_ms": str(int(round(duration_s * 1000))),
        "duration_s": f"{duration_s:.6f}",
        "looming_segment_onset_s": "0.000",
        "tactile_onset_s": "0.300000",
        "channels": "2",
        "tactile_channel": "3",
        "tactile_waveform_shape": "sine",
        "tactile_frequency_hz": "80",
        "tactile_duration_ms": "100",
        "tactile_amplitude": "0.18",
        "audio_output_mode": "switched_speaker_array",
        "speaker_array_id": "four_output_validation_array",
        "speaker_array_layout": "front_rear_serial_proxy",
        "speaker_switch_sequence": label_sequence,
        "speaker_switch_times_ms": "0|200|400|600",
        "speaker_switch_channels": channel_sequence,
        "speaker_switch_gains": gains,
        "speaker_source_channel": "mixdown",
        "expected_response": "respond",
        "response_rule": "detect tactile target during switched-speaker audio row",
        "target_role": "audio_tactile_target",
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
    return _truthy(_first(row, "speaker_switch_generated", "Speaker_Switch_Generated"))


def _marker_payloads_preserve_contract(rows: list[dict[str, Any]]) -> bool:
    sequences: set[str] = set()
    for row in rows:
        payload = _payload(row)
        event_type = str(
            row.get("event_type") or row.get("Event_Type") or payload.get("event_type") or payload.get("Event_Type") or ""
        ).strip()
        if event_type not in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end"}:
            continue
        if _row_has_contract(payload):
            sequences.add(str(payload.get("speaker_switch_channels") or payload.get("Speaker_Switch_Channels") or ""))
    return sequences == {"1|2|4", "4|2|1"}


def _trigger_dictionary_preserves_contract(data: dict[str, Any]) -> bool:
    triggers = data.get("triggers") if isinstance(data, dict) else None
    if not isinstance(triggers, list):
        return False
    sequences = {
        str(item.get("speaker_switch_channels") or item.get("Speaker_Switch_Channels") or "")
        for item in triggers
        if isinstance(item, dict) and str(item.get("trigger_key") or "").startswith("trial:") and _row_has_contract(item)
    }
    return sequences == {"1|2|4", "4|2|1"}


def _speaker_switch_wav_energy_summary(block_wav: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not block_wav or not Path(block_wav).is_file() or not rows:
        return {"passed": False, "reason": "missing block WAV or rows"}
    data, sample_rate = sf.read(block_wav, dtype="float32", always_2d=True)
    checks: list[dict[str, Any]] = []
    passed = True
    for row in rows:
        start = int(float(_first(row, "Trial_Start_Sample") or 0))
        times = [float(value) for value in str(_first(row, "Speaker_Switch_Times_ms")).split("|") if value]
        channels = [int(float(value)) for value in str(_first(row, "Speaker_Switch_Channels")).split("|") if value]
        if len(times) != len(channels) + 1:
            passed = False
            checks.append({"trial_uid": _first(row, "Trial_UID"), "passed": False, "reason": "bad schedule shape"})
            continue
        for index, channel in enumerate(channels):
            seg_start = start + int(round((times[index] / 1000.0) * sample_rate))
            seg_stop = start + int(round((times[index + 1] / 1000.0) * sample_rate))
            active_rms = _rms(data[seg_start:seg_stop, channel - 1])
            inactive = []
            for other in {1, 2, 4} - {channel}:
                if other <= data.shape[1]:
                    inactive.append(_rms(data[seg_start:seg_stop, other - 1]))
            inactive_max = max(inactive) if inactive else 0.0
            ok = active_rms > 0.005 and inactive_max < max(0.001, active_rms * 0.2)
            passed = passed and ok
            checks.append(
                {
                    "trial_uid": _first(row, "Trial_UID"),
                    "segment_index": index + 1,
                    "channel": channel,
                    "active_rms": round(active_rms, 8),
                    "inactive_max_rms": round(inactive_max, 8),
                    "passed": ok,
                }
            )
    return {"passed": bool(passed), "sample_rate": int(sample_rate), "channels": int(data.shape[1]), "checks": checks}


def _rms(values: Any) -> float:
    array = np.asarray(values, dtype=np.float32)
    if array.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(array))))


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Multi-Speaker Switch Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Block rows: `{report['block_row_family_counts']}`",
        f"- Audio output modes: `{report['block_row_audio_output_modes']}`",
        f"- Switch channels: `{report['block_row_switch_channels']}`",
        f"- Event counts: `{report['event_counts']}`",
        f"- WAV energy passed: `{report['speaker_switch_energy_summary'].get('passed')}`",
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
