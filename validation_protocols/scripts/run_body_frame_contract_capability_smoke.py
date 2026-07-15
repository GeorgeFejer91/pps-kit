"""Validate body-part anchored coordinate-frame metadata through the runner."""

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


SCHEMA = "pps-body-frame-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_body_frame_contract_20260715"
CONTRACT_FIELDS = {
    "spatial_coordinate_frame": "Spatial_Coordinate_Frame",
    "body_anchor": "Body_Anchor",
    "body_part": "Body_Part",
    "body_side": "Body_Side",
    "spatial_hemifield": "Spatial_Hemifield",
    "body_relative_axis": "Body_Relative_Axis",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "body-part anchored coordinate-frame metadata. It verifies prepared block "
    "CSVs, deterministic trial trigger metadata, local marker CSV/XDF output, "
    "participant rows, analysis rows, software wired-loopback sidecars, and "
    "mouse-click simulated participant-like responses. It is not physical "
    "body-tracking, exact body-scaled spatialization, physical speaker-array "
    "geometry validation, collected participant evidence, physical timing "
    "loopback, or scientific PPS-effect replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "body_part_anchored_coordinate_frames",
    "example_record_ids": [
        "ladavas_2001_auditory_tactile_extinction",
        "farne_ladavas_2002_auditory_pps_humans",
        "tajadura_jimenez_2009_visual_deprivation",
        "serino_2015_exps_4_to_6",
        "hobeika_2018_anisotropy",
        "teraoka_2024_front_rear",
        "amiel_2025_front_rear",
        "teramoto_2013_beyond_head_audiotactile",
    ],
    "supported_contract": {
        "spatial_coordinate_frame": "paper-declared frame such as head_centered, hand_centered, trunk_centered",
        "body_anchor": "body landmark anchoring the auditory/tactile spatial relation",
        "body_part": "tactile or referenced body part",
        "body_side": "left, right, midline, ipsilesional, or contralesional when reported",
        "spatial_hemifield": "front, rear, left, right, ipsilateral, contralateral, or paper-specific hemifield",
        "body_relative_axis": "front_back, left_right, near_far, or other paper-declared axis",
    },
    "remaining_boundary": (
        "paper-specific geometry extraction, exact body-scaled transforms, physical tracking, and "
        "speaker-array hardware validation remain outside this software metadata smoke"
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

    def _click_after_tactile(_payload: dict[str, Any]) -> None:
        controller.events.flush_callback_events(timeout_s=0.5)
        time.sleep(engine.response_delay_s)
        controller.log_click(x=320, y=240, in_target=True)

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
        "prepared_rows_preserve_body_frame_contract": _rows_preserve_contract(block_rows, expected_count=4),
        "marker_payloads_preserve_body_frame_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_body_frame_contract": _trigger_dictionary_preserves_contract(trigger_dictionary),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_preserve_body_frame_contract": _rows_preserve_contract(
            participant_rows,
            expected_count=4,
            require_tactile_only=False,
        ),
        "analysis_rows_preserve_body_frame_contract": _rows_preserve_contract(
            analysis_rows,
            expected_count=3,
            require_tactile_only=True,
        ),
        "mouse_clicks_logged_for_tactile_rows": _event_counts(events).get("mouse_click", 0) == 3,
        "response_markers_logged_for_tactile_rows": _event_counts(events).get("response_marker_start", 0) == 3,
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
        "block_row_body_anchors": _count_values(block_rows, "Body_Anchor"),
        "block_row_coordinate_frames": _count_values(block_rows, "Spatial_Coordinate_Frame"),
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
        "report_json": str(output_dir / "body_frame_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "body_frame_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "body_frame_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_wav = _write_wav(stim_root / "body_frame_looming_proxy.wav", duration_s=0.50)
    baseline_wav = _write_wav(stim_root / "body_frame_baseline_proxy.wav", duration_s=0.42, gain=0.0)
    rows = [
        _row(
            1,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.50,
            soa_ms=120.0,
            tactile_onset_s=0.120,
            spatial_coordinate_frame="head_centered",
            body_anchor="head",
            body_part="cheek",
            body_side="left",
            spatial_hemifield="ipsilesional",
            body_relative_axis="near_far",
            label="Head anchored near tactile target",
        ),
        _row(
            2,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.50,
            soa_ms=260.0,
            tactile_onset_s=0.260,
            spatial_coordinate_frame="hand_centered",
            body_anchor="hand",
            body_part="hand",
            body_side="right",
            spatial_hemifield="lateral",
            body_relative_axis="left_right",
            label="Hand anchored lateral tactile target",
        ),
        _row(
            3,
            family="baseline",
            wav_path=baseline_wav,
            duration_s=0.42,
            soa_ms=0.0,
            tactile_onset_s=0.100,
            spatial_coordinate_frame="trunk_centered",
            body_anchor="trunk",
            body_part="trunk",
            body_side="midline",
            spatial_hemifield="rear",
            body_relative_axis="front_back",
            label="Trunk anchored rear tactile baseline",
        ),
        _row(
            4,
            family="catch",
            wav_path=audio_wav,
            duration_s=0.50,
            soa_ms=0.0,
            tactile_onset_s=None,
            spatial_coordinate_frame="head_centered",
            body_anchor="head",
            body_part="cheek",
            body_side="left",
            spatial_hemifield="contralesional",
            body_relative_axis="near_far",
            label="Head anchored auditory catch",
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
                "block_label": "Body-frame contract validation",
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
    spatial_coordinate_frame: str,
    body_anchor: str,
    body_part: str,
    body_side: str,
    spatial_hemifield: str,
    body_relative_axis: str,
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
        "spatial_coordinate_frame": spatial_coordinate_frame,
        "body_anchor": body_anchor,
        "body_part": body_part,
        "body_side": body_side,
        "spatial_hemifield": spatial_hemifield,
        "body_relative_axis": body_relative_axis,
        "expected_response": "respond" if has_tactile else "withhold",
        "response_rule": "mouse-click emulation of paper response",
        "target_role": "target" if has_tactile else "catch_no_target",
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
    data[:, 1] = gain * np.sin(2.0 * np.pi * 550.0 * t)
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
    anchors = {
        str(payload.get("body_anchor") or payload.get("Body_Anchor") or "").strip()
        for payload in trial_payloads
        if _row_has_contract(payload)
    }
    return {"head", "hand", "trunk"}.issubset(anchors)


def _trigger_dictionary_preserves_contract(data: dict[str, Any]) -> bool:
    triggers = data.get("triggers") if isinstance(data, dict) else None
    if not isinstance(triggers, list):
        return False
    anchors = {
        str(item.get("body_anchor") or item.get("Body_Anchor") or "").strip()
        for item in triggers
        if isinstance(item, dict) and str(item.get("trigger_key") or "").startswith("trial:") and _row_has_contract(item)
    }
    return {"head", "hand", "trunk"}.issubset(anchors)


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
        "# Body-Frame Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Body anchors: `{report['block_row_body_anchors']}`",
        f"- Coordinate frames: `{report['block_row_coordinate_frames']}`",
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
