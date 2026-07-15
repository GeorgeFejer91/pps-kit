"""Validate row-level tactile waveform profiles through the runner.

This smoke targets the remaining tactile-waveform gap exposed by the 2025
looming-duration PPS paper: an 80 Hz, 200 ms sawtooth tactile cue paired with
2 s and 3 s right-lateral looming conditions. It proves the Segment 5/6 runner
path can synthesize the tactile channel from row metadata, preserve the metadata
in manifests and analysis rows, and produce mouse-click simulated outcomes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
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
from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-tactile-waveform-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_tactile_waveform_capability_20260715"
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "tactile waveform synthesis: 80 Hz, 200 ms sawtooth tactile cues are "
    "generated into channel 3, preserved in prepared manifests and analysis "
    "rows, and runnable with mouse-click simulated responses. It is not an "
    "exact MATLAB HRTF recreation, not physical tactile calibration, not "
    "hardware loopback evidence, and not collected participant evidence."
)

SOURCE_PARAMETER_TARGET = {
    "record_id": "looming_duration_2025",
    "doi": "10.61782/fa.2025.0866",
    "duration_conditions_s": [2.0, 3.0],
    "delay_cells_per_duration": 7,
    "reported_repetitions_per_delay_condition": 16,
    "reported_auditory_only_catch_trials": 21,
    "tactile_waveform_shape": "sawtooth",
    "tactile_frequency_hz": 80.0,
    "tactile_duration_ms": 200.0,
    "expected_effect_direction": (
        "both_2s_and_3s_looming_sounds_facilitate_late_tactile_rt_with_duration_specific_boundaries"
    ),
    "remaining_nonvalidated_boundary": "exact original MATLAB HRTF/right-lateral rendering implementation",
}

DURATION_SOAS_MS = {
    2.0: [375.0, 625.0, 875.0, 1125.0, 1375.0, 1625.0, 1875.0],
    3.0: [562.5, 937.5, 1312.5, 1687.5, 2062.5, 2437.5, 2812.5],
}
LATE_BOUNDARY_MS = {2.0: 1125.0, 3.0: 1312.5}


def run_smoke(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_fixture(output_dir, participant_id=participant_id)
    package = prepare_segment_run_package(run_manifest, participant_id=participant_id, use_block_cache=False)
    engine = runner_smoke.FastProfileSmokeAudioEngine(max_clicks_per_block=10_000, response_delay_s=0.0)
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
            start_external_labrecorder=False,
        ),
        enable_topup=False,
        instruction_continue_callback=lambda _context: True,
        runner_metadata={"participant_code": participant_id},
    )

    def _click_with_expected_pattern(payload: dict[str, Any]) -> None:
        controller.events.flush_callback_events(timeout_s=0.5)
        delay_s = _simulated_response_delay_s(payload)
        time.sleep(delay_s)
        controller.log_click(x=320, y=240, in_target=True)

    engine.set_tactile_callback(_click_with_expected_pattern)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)

    block_rows = [row for block in package.blocks for row in _read_csv(block.manifest_path)]
    events = _read_csv(result.events_csv)
    analysis_rows = _read_csv(result.analysis_outputs.get("analysis_ready_trials", Path()))
    participant_rows = _read_csv(result.analysis_outputs.get("participant_trials", Path()))
    prepared_waveform_rows = [row for row in block_rows if row.get("Tactile_Waveform_Generated") == "true"]
    direction = _observed_direction(analysis_rows)
    criteria = {
        "completed": bool(result.completed and not result.interrupted),
        "all_duration_delay_cells_executed": _duration_delay_cells(block_rows) == {
            "duration_2s": 7,
            "duration_3s": 7,
        },
        "baseline_and_catch_controls_executed": _family_counts(block_rows).get("baseline") == 2
        and _family_counts(block_rows).get("catch") == 2,
        "tactile_waveform_generated_for_all_tactile_rows": len(prepared_waveform_rows) == 16
        and all(_is_80hz_200ms_sawtooth(row) for row in prepared_waveform_rows),
        "block_wav_contains_sawtooth_resets": _block_wav_has_sawtooth(package.blocks[0].wav_path, block_rows),
        "participant_rows_preserve_waveform_metadata": _participant_rows_preserve_waveform(participant_rows),
        "analysis_rows_preserve_waveform_metadata": _analysis_rows_preserve_waveform(analysis_rows),
        "mouse_clicks_logged_for_tactile_rows": _event_counts(events).get("mouse_click", 0) == 16,
        "response_markers_logged_for_tactile_rows": _event_counts(events).get("response_marker_start", 0) == 16,
        "observed_late_facilitation_matches_expected_direction": direction["passed"],
    }
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "source_parameter_target": SOURCE_PARAMETER_TARGET,
        "executed_smoke_matrix": {
            "audio_tactile_rows": 14,
            "baseline_rows": 2,
            "auditory_only_catch_rows": 2,
            "duration_delay_cells": _duration_delay_cells(block_rows),
            "note": "Compact one-repetition execution of every duration-delay cell; full paper count target remains documented.",
        },
        "remaining_record_boundary": SOURCE_PARAMETER_TARGET["remaining_nonvalidated_boundary"],
        "run_setup_manifest": str(run_manifest),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "block_count": len(package.blocks),
        "block_wav": str(package.blocks[0].wav_path),
        "block_wav_facts": runner_smoke._wav_facts(package.blocks[0].wav_path),
        "block_row_family_counts": _family_counts(block_rows),
        "event_counts": _event_counts(events),
        "participant_trial_count": len(participant_rows),
        "analysis_ready_trial_count": len(analysis_rows),
        "observed_direction": direction,
        "outputs": {
            "events_csv": str(result.events_csv),
            "analysis_ready_trials": str(result.analysis_outputs.get("analysis_ready_trials", "")),
            "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
            "lsl_markers_csv": str(result.lsl_markers_csv or ""),
            "trigger_dictionary": str(result.trigger_dictionary_path or ""),
            "session_metadata": str(result.session_metadata_path or ""),
        },
        "report_json": str(output_dir / "tactile_waveform_capability_smoke_report.json"),
        "report_md": str(output_dir / "tactile_waveform_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "tactile_waveform_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)

    source_wavs = {
        duration_s: _write_lateral_source_wav(stim_root / f"right_lateral_pink_{duration_s:g}s.wav", duration_s=duration_s)
        for duration_s in DURATION_SOAS_MS
    }
    baseline_wav = _write_silent_wav(stim_root / "tactile_only_baseline.wav", duration_s=0.55)
    rows: list[dict[str, Any]] = []
    index = 1
    for duration_s, soas in DURATION_SOAS_MS.items():
        for soa_ms in soas:
            source = source_wavs[duration_s]
            rows.append(
                _row(
                    index,
                    family="audio_tactile",
                    wav_path=source,
                    duration_s=duration_s,
                    soa_ms=soa_ms,
                    tactile_onset_s=soa_ms / 1000.0,
                    variant_key=f"duration_{duration_s:g}s_soa_{_soa_token(soa_ms)}",
                    label=f"{duration_s:g} s right-lateral looming | SOA {soa_ms:g} ms",
                )
            )
            index += 1
        rows.append(
            _row(
                index,
                family="baseline",
                wav_path=baseline_wav,
                duration_s=0.55,
                soa_ms=0.0,
                tactile_onset_s=0.1,
                variant_key=f"duration_{duration_s:g}s_baseline",
                label=f"{duration_s:g} s tactile-only baseline",
            )
        )
        index += 1
        rows.append(
            _row(
                index,
                family="catch",
                wav_path=source_wavs[duration_s],
                duration_s=duration_s,
                soa_ms=0.0,
                tactile_onset_s=None,
                variant_key=f"duration_{duration_s:g}s_auditory_only_catch",
                label=f"{duration_s:g} s auditory-only catch",
            )
        )
        index += 1

    block_csv = block_root / "block_01_final.csv"
    fieldnames = list(rows[0].keys())
    _write_csv(block_csv, rows, fieldnames)
    block_manifest = block_root / "block_csv_preview_manifest.json"
    _write_json(
        block_manifest,
        {
            "schema": "pps-block-csv-preview.v1",
            "accepted": True,
            "blocks": [
                {
                    "block_index": 1,
                    "csv_path": str(block_csv),
                    "csv_file_name": block_csv.name,
                    "trial_count": len(rows),
                }
            ],
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
                "block_label": "Looming duration tactile waveform validation",
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
            "participant_count": 1,
            "parts_per_participant": 1,
            "blocks_per_part": 1,
            "total_block_runs": 1,
            "seed": 20260715,
            "source_segment5_manifest": str(block_manifest),
            "source_segment5_manifest_sha256": _sha256(block_manifest),
        },
    )
    return run_manifest


def _row(
    index: int,
    *,
    family: str,
    wav_path: Path,
    duration_s: float,
    soa_ms: float,
    tactile_onset_s: float | None,
    variant_key: str,
    label: str,
) -> dict[str, Any]:
    has_tactile = family in {"audio_tactile", "baseline"}
    duration_label = _duration_label(variant_key)
    return {
        "block_trial_index": index,
        "family": family,
        "row_label": label,
        "noise_type": "right_lateral_pink_noise",
        "soa_ms": f"{soa_ms:g}",
        "sequence_labels": label,
        "sequence_variant_key": variant_key,
        "source_file_name": wav_path.name,
        "trial_file_path": str(wav_path),
        "source_sha256": _sha256(wav_path),
        "duration_ms": int(round(duration_s * 1000.0)),
        "duration_s": f"{duration_s:.9f}",
        "looming_segment_onset_s": "0.000000000" if family in {"audio_tactile", "catch"} else "",
        "tactile_onset_s": "" if tactile_onset_s is None else f"{tactile_onset_s:.9f}",
        "channels": 2,
        "tactile_channel": 3 if has_tactile else "",
        "tactile_waveform_shape": "sawtooth" if has_tactile else "",
        "tactile_frequency_hz": "80" if has_tactile else "",
        "tactile_duration_ms": "200" if has_tactile else "",
        "tactile_amplitude": "0.35" if has_tactile else "",
        "expected_response": "respond" if has_tactile else "withhold",
        "response_rule": "respond_to_tactile_target" if has_tactile else "withhold_response",
        "target_role": "target" if has_tactile else "no_target",
        "duration_condition_s": duration_label,
        "source_start_distance_cm": "100" if duration_label == "2" else "150",
        "source_end_distance_cm": "0",
        "source_speed_cm_s": "50",
        "motion_mode": "right_lateral_looming",
    }


def _write_lateral_source_wav(path: Path, *, duration_s: float, sample_rate: int = 44100) -> Path:
    frames = int(round(duration_s * sample_rate))
    rng = np.random.default_rng(int(duration_s * 1000))
    noise = rng.normal(0.0, 0.012, frames).astype(np.float32)
    ramp = np.linspace(0.55, 1.0, frames, dtype=np.float32)
    right = noise * ramp
    left = right * 0.65
    data = np.column_stack([left, right]).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sample_rate)
    return path


def _write_silent_wav(path: Path, *, duration_s: float, sample_rate: int = 44100) -> Path:
    data = np.zeros((int(round(duration_s * sample_rate)), 2), dtype=np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sample_rate)
    return path


def _simulated_response_delay_s(payload: dict[str, Any]) -> float:
    family = str(payload.get("family") or payload.get("Family") or "").strip().lower()
    if family == "baseline":
        return 0.165
    variant = str(payload.get("sequence_variant_key") or payload.get("Sequence_Variant_Key") or "")
    duration_s, soa_ms = _parse_variant(variant)
    if duration_s and soa_ms >= LATE_BOUNDARY_MS.get(duration_s, 999999.0):
        return 0.112
    return 0.145


def _observed_direction(rows: list[dict[str, str]]) -> dict[str, Any]:
    groups: dict[str, list[float]] = {
        "duration_2s_early": [],
        "duration_2s_late": [],
        "duration_2s_baseline": [],
        "duration_3s_early": [],
        "duration_3s_late": [],
        "duration_3s_baseline": [],
    }
    for row in rows:
        rt = _as_float(row.get("rt_ms"))
        if rt is None:
            continue
        variant = str(row.get("sequence_variant_key") or "")
        family = str(row.get("family") or "").strip().lower()
        duration_s, soa_ms = _parse_variant(variant)
        if duration_s not in {2.0, 3.0}:
            continue
        prefix = f"duration_{int(duration_s)}s"
        if family == "baseline":
            groups[f"{prefix}_baseline"].append(rt)
        elif soa_ms >= LATE_BOUNDARY_MS[duration_s]:
            groups[f"{prefix}_late"].append(rt)
        else:
            groups[f"{prefix}_early"].append(rt)
    means = {key: _mean(value) for key, value in groups.items()}
    checks = {
        "duration_2s_late_faster_than_early": means["duration_2s_late"] < means["duration_2s_early"],
        "duration_2s_late_faster_than_baseline": means["duration_2s_late"] < means["duration_2s_baseline"],
        "duration_3s_late_faster_than_early": means["duration_3s_late"] < means["duration_3s_early"],
        "duration_3s_late_faster_than_baseline": means["duration_3s_late"] < means["duration_3s_baseline"],
    }
    return {
        "passed": all(checks.values()),
        "mean_rt_ms": means,
        "checks": checks,
        "expected_effect_direction": SOURCE_PARAMETER_TARGET["expected_effect_direction"],
    }


def _block_wav_has_sawtooth(path: Path, block_rows: list[dict[str, str]]) -> bool:
    data, _rate = sf.read(path, always_2d=True)
    for row in block_rows:
        if row.get("Tactile_Waveform_Generated") != "true":
            continue
        start = _as_int(row.get("Tactile_Drive_Onset_Sample"))
        stop = start + int(round(float(row.get("Tactile_Duration_ms") or 0.0) / 1000.0 * _rate))
        tactile = data[start:stop, 2] if data.shape[1] >= 3 else np.asarray([])
        if tactile.size < 100:
            return False
        resets = int(np.count_nonzero(np.diff(tactile) < -0.45))
        return resets >= 10 and float(np.max(tactile)) > 0.3 and float(np.min(tactile)) < -0.3
    return False


def _is_80hz_200ms_sawtooth(row: dict[str, str]) -> bool:
    return (
        row.get("Tactile_Waveform_Shape") == "sawtooth"
        and _as_float(row.get("Tactile_Frequency_Hz")) == 80.0
        and _as_float(row.get("Tactile_Duration_ms")) == 200.0
        and row.get("Tactile_Channel") == "3"
    )


def _participant_rows_preserve_waveform(rows: list[dict[str, str]]) -> bool:
    tactile_rows = [row for row in rows if row.get("tactile_present") == "true"]
    return bool(tactile_rows) and all(
        row.get("tactile_waveform_shape") == "sawtooth"
        and _as_float(row.get("tactile_frequency_hz")) == 80.0
        and _as_float(row.get("tactile_duration_ms")) == 200.0
        and row.get("tactile_waveform_generated") == "true"
        for row in tactile_rows
    )


def _analysis_rows_preserve_waveform(rows: list[dict[str, str]]) -> bool:
    return bool(rows) and all(
        row.get("tactile_waveform_shape") == "sawtooth"
        and _as_float(row.get("tactile_frequency_hz")) == 80.0
        and _as_float(row.get("tactile_duration_ms")) == 200.0
        and str(row.get("tactile_waveform_generated")).lower() in {"true", "1"}
        for row in rows
    )


def _duration_delay_cells(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, set[str]] = {"duration_2s": set(), "duration_3s": set()}
    for row in rows:
        if row.get("Family") != "audio_tactile":
            continue
        duration_s, soa_ms = _parse_variant(str(row.get("Sequence_Variant_Key") or ""))
        if duration_s in {2.0, 3.0}:
            counts[f"duration_{int(duration_s)}s"].add(f"{soa_ms:g}")
    return {key: len(value) for key, value in counts.items()}


def _family_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        family = str(row.get("Family") or row.get("family") or "").strip().lower()
        if family:
            counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _event_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        event_type = str(row.get("event_type") or "")
        if event_type:
            counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items()))


def _parse_variant(value: str) -> tuple[float | None, float]:
    match = re.search(r"duration_(2|3)s_soa_([0-9p]+)", value)
    if not match:
        match = re.search(r"duration_(2|3)s_baseline", value)
        return (float(match.group(1)) if match else None), 0.0
    return float(match.group(1)), float(match.group(2).replace("p", "."))


def _duration_label(value: str) -> str:
    match = re.search(r"duration_(2|3)s", value)
    return match.group(1) if match else ""


def _soa_token(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values)) if values else float("nan")


def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result


def _as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv(path: Path | str) -> list[dict[str, str]]:
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Tactile Waveform Capability Smoke",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Audio-tactile rows: `{report['block_row_family_counts'].get('audio_tactile', 0)}`",
        f"- Mouse clicks: `{report['event_counts'].get('mouse_click', 0)}`",
        f"- Expected direction matched: `{report['observed_direction']['passed']}`",
        f"- Remaining boundary: `{report['remaining_record_boundary']}`",
        "",
        EVIDENCE_BOUNDARY,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args(argv)
    report = run_smoke(output_dir=args.output_dir, participant_id=args.participant_id)
    print(json.dumps({"passed": report["passed"], "report_json": report["report_json"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
