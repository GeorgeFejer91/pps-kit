"""Validate the runner contract for static near/far audio-tactile trials.

This is a capability smoke, not a paper-specific recreation. It builds a tiny
Segment 5/6-style fixture with stationary near and far sound labels,
tactile-only baselines, and sound-only catches, prepares a participant package,
runs SessionRunnerController with the fast validation audio engine, and injects
mouse-click responses after tactile onsets.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
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


SCHEMA = "pps-static-near-far-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_static_near_far_capability_20260715"
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for static near/far "
    "audio-tactile rows, tactile-only baselines, sound-only catches, generated "
    "3-channel WAVs, and mouse-click responses. It is not a paper-specific "
    "profile, not original-apparatus equivalence, and not participant evidence."
)


def run_smoke(*, output_dir: Path = DEFAULT_OUTPUT_DIR, participant_id: str = "P001") -> dict[str, Any]:
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_static_near_far_fixture(output_dir, participant_id=participant_id)
    package = prepare_segment_run_package(run_manifest, participant_id=participant_id)
    engine = runner_smoke.FastProfileSmokeAudioEngine(max_clicks_per_block=10_000, response_delay_s=0.12)
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

    def _click_after_tactile(_payload: dict[str, Any]) -> None:
        controller.events.flush_callback_events(timeout_s=0.5)
        if engine.response_delay_s:
            time.sleep(engine.response_delay_s)
        controller.log_click(x=320, y=240, in_target=True)

    engine.set_tactile_callback(_click_after_tactile)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)

    events = _read_csv(result.events_csv)
    event_counts = _event_counts(events)
    analysis_path = result.analysis_outputs.get("analysis_ready_trials", Path())
    analysis_rows = _read_csv(analysis_path)
    block_rows = [row for block in package.blocks for row in _read_csv(block.manifest_path)]
    families = _count_values(block_rows, "family")
    distance_labels = _distance_label_counts(block_rows)
    hit_count = sum(1 for row in analysis_rows if str(row.get("hit") or "").strip().lower() in {"true", "1", "yes"})
    rt_values = [_as_float(row.get("rt_ms")) for row in analysis_rows if str(row.get("rt_ms") or "").strip()]
    expected_clicks = families.get("audio_tactile", 0) + families.get("baseline", 0)
    criteria = {
        "completed": bool(result.completed and not result.interrupted),
        "block_wav_generated": len(package.blocks) == 1 and package.blocks[0].wav_path.is_file(),
        "near_and_far_audio_tactile_rows": distance_labels.get("near", 0) >= 2 and distance_labels.get("far", 0) >= 2,
        "baseline_and_catch_rows_present": families.get("baseline", 0) >= 2 and families.get("catch", 0) >= 2,
        "tactile_clicks_logged": event_counts.get("mouse_click", 0) == expected_clicks,
        "response_markers_logged": event_counts.get("response_marker_start", 0) == expected_clicks,
        "analysis_hits_written": hit_count == expected_clicks,
        "all_hits_in_response_window": bool(rt_values) and min(rt_values) >= 100.0 and max(rt_values) <= 1300.0,
        "events_csv_written": result.events_csv.is_file(),
        "internal_xdf_written": result.events_xdf.is_file(),
        "marker_mirror_written": bool(result.lsl_markers_csv and Path(result.lsl_markers_csv).is_file()),
        "trigger_dictionary_written": bool(result.trigger_dictionary_path and Path(result.trigger_dictionary_path).is_file()),
    }
    report = {
        "schema": SCHEMA,
        "generated_on": "2026-07-15",
        "passed": all(criteria.values()),
        "criteria": criteria,
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "participant_id": participant_id,
        "run_setup_manifest": str(run_manifest),
        "session_manifest": str(package.manifest_path),
        "session_dir": str(package.session_dir),
        "block_count": len(package.blocks),
        "block_wav": str(package.blocks[0].wav_path),
        "block_wav_facts": runner_smoke._wav_facts(package.blocks[0].wav_path),
        "block_row_family_counts": families,
        "audio_tactile_distance_label_counts": distance_labels,
        "expected_tactile_response_count": expected_clicks,
        "event_counts": event_counts,
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_ready_hit_count": hit_count,
        "rt_ms": _summary(rt_values),
        "outputs": {
            "events_csv": str(result.events_csv),
            "events_xdf": str(result.events_xdf),
            "analysis_ready_trials": str(analysis_path),
            "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
            "lsl_markers_csv": str(result.lsl_markers_csv or ""),
            "trigger_dictionary": str(result.trigger_dictionary_path or ""),
            "session_metadata": str(result.session_metadata_path or ""),
        },
        "report_json": str(output_dir / "static_near_far_capability_smoke_report.json"),
        "report_md": str(output_dir / "static_near_far_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_static_near_far_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "static_near_far_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for index, spec in enumerate(_trial_specs(), start=1):
        wav_path = stim_root / f"trial_{index:02d}_{spec['distance_label']}_{spec['family']}.wav"
        _write_trial_wav(wav_path, family=spec["family"], tactile_onset_s=spec["tactile_onset_s"])
        rows.append(
            {
                "block_trial_index": index,
                "family": spec["family"],
                "row_label": spec["row_label"],
                "noise_type": "static_validation_tone",
                "soa_ms": spec["soa_ms"],
                "sequence_labels": spec["sequence_labels"],
                "sequence_variant_key": spec["sequence_variant_key"],
                "source_file_name": wav_path.name,
                "trial_file_path": str(wav_path),
                "source_sha256": _sha256(wav_path),
                "duration_ms": 700,
                "duration_s": "0.700000000",
                "looming_segment_onset_s": "0.100000000",
                "tactile_onset_s": f"{spec['tactile_onset_s']:.9f}" if spec["tactile_onset_s"] is not None else "",
                "channels": 3,
                "tactile_channel": 3,
                "static_distance_label": spec["distance_label"],
                "source_distance_cm": spec["source_distance_cm"],
                "motion_mode": "stationary",
            }
        )

    block_csv = block_root / "block_01_final.csv"
    fieldnames = [
        "block_trial_index",
        "family",
        "row_label",
        "noise_type",
        "soa_ms",
        "sequence_labels",
        "sequence_variant_key",
        "source_file_name",
        "trial_file_path",
        "source_sha256",
        "duration_ms",
        "duration_s",
        "looming_segment_onset_s",
        "tactile_onset_s",
        "channels",
        "tactile_channel",
        "static_distance_label",
        "source_distance_cm",
        "motion_mode",
    ]
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
                "block_label": "Static near/far validation block",
                "block_csv_file": block_csv.name,
                "block_csv_path": str(block_csv),
                "trial_count": len(rows),
                "duration_ms": 700 * len(rows),
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


def _trial_specs() -> list[dict[str, Any]]:
    specs = []
    for distance_label, distance_cm in (("near", 30), ("far", 150)):
        for soa_ms in (0, 300):
            tactile_onset_s = 0.25 + (soa_ms / 1000.0)
            specs.append(
                {
                    "family": "audio_tactile",
                    "distance_label": distance_label,
                    "source_distance_cm": distance_cm,
                    "soa_ms": soa_ms,
                    "tactile_onset_s": tactile_onset_s,
                    "row_label": f"Static {distance_label} audio-tactile",
                    "sequence_labels": f"Stationary {distance_label} source | tactile SOA {soa_ms} ms",
                    "sequence_variant_key": f"stationary_{distance_label}_source_soa{soa_ms:03d}",
                }
            )
        specs.append(
            {
                "family": "baseline",
                "distance_label": distance_label,
                "source_distance_cm": distance_cm,
                "soa_ms": 0,
                "tactile_onset_s": 0.25,
                "row_label": f"Static {distance_label} tactile-only baseline",
                "sequence_labels": f"Stationary {distance_label} baseline without sound",
                "sequence_variant_key": f"stationary_{distance_label}_baseline",
            }
        )
        specs.append(
            {
                "family": "catch",
                "distance_label": distance_label,
                "source_distance_cm": distance_cm,
                "soa_ms": 0,
                "tactile_onset_s": None,
                "row_label": f"Static {distance_label} sound-only catch",
                "sequence_labels": f"Stationary {distance_label} source catch without tactile",
                "sequence_variant_key": f"stationary_{distance_label}_catch",
            }
        )
    return specs


def _write_trial_wav(path: Path, *, family: str, tactile_onset_s: float | None, sample_rate: int = 44100) -> None:
    frames = int(round(0.7 * sample_rate))
    data = np.zeros((frames, 3), dtype=np.float32)
    if family in {"audio_tactile", "catch"}:
        _add_pulse(data, 0, 0.100, sample_rate=sample_rate, amplitude=0.018)
        _add_pulse(data, 1, 0.102, sample_rate=sample_rate, amplitude=0.014)
    if tactile_onset_s is not None:
        _add_pulse(data, 2, tactile_onset_s, sample_rate=sample_rate, amplitude=0.016)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, data, sample_rate)


def _add_pulse(data: np.ndarray, channel: int, onset_s: float, *, sample_rate: int, amplitude: float) -> None:
    start = max(0, min(data.shape[0], int(round(onset_s * sample_rate))))
    stop = max(start, min(data.shape[0], start + max(1, int(round(0.025 * sample_rate)))))
    data[start:stop, channel] = amplitude


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
        "# Static Near/Far Capability Smoke",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Block rows: `{sum(report['block_row_family_counts'].values())}`",
        f"- Mouse clicks: `{report['event_counts'].get('mouse_click', 0)}`",
        f"- Response markers: `{report['event_counts'].get('response_marker_start', 0)}`",
        f"- Analysis hits: `{report['analysis_ready_hit_count']}`",
        "",
        EVIDENCE_BOUNDARY,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _event_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        event_type = str(row.get("event_type") or "")
        if event_type:
            counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items()))


def _count_values(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or row.get(key.title()) or "").strip().lower()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _distance_label_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        if str(row.get("family") or row.get("Family") or "").strip().lower() != "audio_tactile":
            continue
        label = str(row.get("static_distance_label") or row.get("Static_Distance_Label") or "").strip().lower()
        if not label:
            text = " ".join(
                str(row.get(key) or "")
                for key in ("row_label", "Row_Label", "sequence_labels", "Sequence_Labels", "sequence_variant_key", "Sequence_Variant_Key")
            ).lower()
            if "near" in text:
                label = "near"
            elif "far" in text:
                label = "far"
        if label:
            counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _summary(values: list[float]) -> dict[str, Any]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "min_ms": None, "max_ms": None, "mean_ms": None}
    return {
        "count": len(finite),
        "min_ms": min(finite),
        "max_ms": max(finite),
        "mean_ms": sum(finite) / len(finite),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a static near/far audio-tactile capability smoke.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args(argv)

    report = run_smoke(output_dir=args.output_dir, participant_id=args.participant_id)
    print(f"Wrote static near/far capability smoke report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
