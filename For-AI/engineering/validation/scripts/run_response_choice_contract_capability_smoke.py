"""Validate tactile discrimination/localization response-choice contracts.

This smoke targets audiotactile PPS studies that require a tactile
discrimination or localization response rather than simple target detection. It
builds a tiny Segment 5/6-style fixture, declares the parsimonious response
choice fields in the rows, runs the real SessionRunnerController path, and
scores simulated participant-like mouse clicks as left/right choices.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
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
    WIRED_LOOPBACK_OUTPUT4_TACTILE_PROXY,
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-response-choice-contract-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_response_choice_contract_20260715"
CONTRACT_FIELDS = {
    "response_mode": "Response_Mode",
    "response_choice_set": "Response_Choice_Set",
    "correct_response": "Correct_Response",
    "response_scoring_policy": "Response_Scoring_Policy",
}
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "tactile discrimination/localization response choices. It verifies prepared "
    "block CSVs, deterministic trial trigger metadata, local marker CSV/XDF "
    "output, participant rows, analysis rows, software wired-loopback sidecars, "
    "and mouse-click simulated participant-like choices. It is not a physical "
    "button-box/localization device validation, collected participant evidence, "
    "physical timing loopback, exact original randomization reconstruction, or "
    "scientific PPS-effect replication."
)
SOURCE_PARAMETER_TARGET = {
    "constraint_id": "tactile_discrimination_or_localization_response",
    "example_record_ids": [
        "kitagawa_2005_sound_complexity",
        "tajadura_jimenez_2009_visual_deprivation",
        "teramoto_2013_visual_deprivation",
        "teramoto_2013_beyond_head_audiotactile",
    ],
    "supported_contract": {
        "response_mode": "choice | discrimination | localization",
        "response_choice_set": "paper-reported alternatives such as left|right",
        "correct_response": "paper-reported correct response label for the row",
        "response_scoring_policy": "mouse_x_split or mouse_y_split for emulated runs",
    },
    "remaining_boundary": (
        "paper-specific response-button geometry, physical device calibration, and "
        "any human discrimination/localization performance must be validated outside "
        "this software smoke"
    ),
}


class ResponseChoiceSmokeAudioEngine(runner_smoke.FastProfileSmokeAudioEngine):
    """Fast fake engine with a software wired-loopback sidecar path."""

    def __init__(self, *, max_clicks_per_block: int = 10_000, response_delay_s: float = 0.12):
        super().__init__(max_clicks_per_block=max_clicks_per_block, response_delay_s=response_delay_s)
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

    def _click_for_choice(payload: dict[str, Any]) -> None:
        expected = _lower(_first(payload, "correct_response", "Correct_Response"))
        if not expected:
            return
        controller.events.flush_callback_events(timeout_s=0.5)
        time.sleep(engine.response_delay_s)
        x = 250 if expected == "left" else 750
        controller.log_click(x=x, y=240, in_target=True)

    engine.set_tactile_callback(_click_for_choice)
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
        "prepared_rows_preserve_response_choice_contract": _rows_preserve_contract(
            block_rows,
            expected_count=4,
            require_tactile_only=True,
        ),
        "marker_payloads_preserve_response_choice_contract": _marker_payloads_preserve_contract(markers),
        "trigger_dictionary_preserves_response_choice_contract": _trigger_dictionary_preserves_contract(
            trigger_dictionary
        ),
        "local_marker_xdf_written": bool(result.lsl_markers_xdf and Path(result.lsl_markers_xdf).is_file()),
        "internal_events_xdf_written": Path(result.events_xdf).is_file(),
        "participant_rows_score_mouse_choice_contract": _rows_score_choices(participant_rows, expected_count=4),
        "analysis_rows_score_mouse_choice_contract": _rows_score_choices(
            analysis_rows,
            expected_count=3,
            require_no_catch=True,
        ),
        "mouse_clicks_logged_for_choice_rows": _event_counts(events).get("mouse_click", 0) == 3,
        "response_markers_logged_for_choice_rows": _event_counts(events).get("response_marker_start", 0) == 3,
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
        "block_row_correct_responses": _count_values(block_rows, "Correct_Response"),
        "event_counts": _event_counts(events),
        "marker_event_counts": _event_counts(markers),
        "participant_trial_count": len(participant_rows),
        "analysis_ready_trial_count": len(analysis_rows),
        "participant_choice_counts": _count_values(participant_rows, "observed_response_choice"),
        "analysis_choice_counts": _count_values(analysis_rows, "observed_response_choice"),
        "software_wired_loopback": str(loopback_path),
        "analysis_ready_trials": str(result.analysis_outputs.get("analysis_ready_trials", "")),
        "participant_trials": str(result.analysis_outputs.get("participant_trials", "")),
        "trigger_dictionary_path": str(result.trigger_dictionary_path or ""),
        "lsl_markers_csv": str(result.lsl_markers_csv or ""),
        "lsl_markers_xdf": str(result.lsl_markers_xdf or ""),
        "events_xdf": str(result.events_xdf),
        "report_json": str(output_dir / "response_choice_contract_capability_smoke_report.json"),
        "report_md": str(output_dir / "response_choice_contract_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "response_choice_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)
    audio_wav = _write_wav(stim_root / "choice_looming_proxy.wav", duration_s=0.52)
    baseline_wav = _write_wav(stim_root / "choice_baseline_proxy.wav", duration_s=0.42, gain=0.0)
    rows = [
        _row(
            1,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.52,
            soa_ms=120.0,
            tactile_onset_s=0.120,
            correct_response="left",
            label="Localization left target",
        ),
        _row(
            2,
            family="audio_tactile",
            wav_path=audio_wav,
            duration_s=0.52,
            soa_ms=260.0,
            tactile_onset_s=0.260,
            correct_response="right",
            label="Localization right target",
        ),
        _row(
            3,
            family="baseline",
            wav_path=baseline_wav,
            duration_s=0.42,
            soa_ms=0.0,
            tactile_onset_s=0.100,
            correct_response="left",
            label="Tactile-only localization baseline",
        ),
        _row(
            4,
            family="catch",
            wav_path=audio_wav,
            duration_s=0.52,
            soa_ms=0.0,
            tactile_onset_s=None,
            correct_response="",
            label="Auditory catch no response",
        ),
    ]
    block_csv = block_root / "block_01_final.csv"
    _write_csv(block_csv, rows, list(rows[0].keys()))
    _write_json(
        block_root / "block_csv_preview_manifest.json",
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
                "block_label": "Response-choice contract validation",
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
    correct_response: str,
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
        "expected_response": "respond" if has_tactile else "withhold",
        "response_rule": "score row-level response choice after tactile onset",
        "target_role": "target" if has_tactile else "catch_no_target",
        "response_mode": "localization" if has_tactile else "",
        "response_choice_set": "left|right" if has_tactile else "",
        "correct_response": correct_response,
        "response_scoring_policy": "mouse_x_split" if has_tactile else "",
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
    data[:, 1] = gain * np.sin(2.0 * np.pi * 660.0 * t)
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


def _rows_score_choices(
    rows: list[dict[str, Any]],
    *,
    expected_count: int,
    require_no_catch: bool = False,
) -> bool:
    if len(rows) != expected_count:
        return False
    checked = [row for row in rows if not (require_no_catch and _family(row) == "catch")]
    tactile_rows = [row for row in checked if _row_has_contract(row)]
    if len(tactile_rows) != 3:
        return False
    for row in tactile_rows:
        expected = _lower(_first(row, "correct_response", "Correct_Response"))
        observed = _lower(_first(row, "observed_response_choice", "Observed_Response_Choice"))
        if not expected or observed != expected:
            return False
        if not _truthy(_first(row, "response_choice_correct", "Response_Choice_Correct")):
            return False
        if str(_first(row, "outcome", "Outcome", "hit", "Hit")).strip().lower() not in {"hit", "true"}:
            return False
    return True


def _marker_payloads_preserve_contract(rows: list[dict[str, Any]]) -> bool:
    trial_payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = _payload(row)
        event_type = str(
            row.get("event_type") or row.get("Event_Type") or payload.get("event_type") or payload.get("Event_Type") or ""
        ).strip()
        if event_type in {"trial_start", "looming_onset", "tactile_onset", "response_window_onset", "trial_end"}:
            trial_payloads.append(payload)
    choices = {
        str(payload.get("correct_response") or payload.get("Correct_Response") or "").strip()
        for payload in trial_payloads
        if _row_has_contract(payload)
    }
    return {"left", "right"}.issubset(choices)


def _trigger_dictionary_preserves_contract(data: dict[str, Any]) -> bool:
    triggers = data.get("triggers") if isinstance(data, dict) else None
    if not isinstance(triggers, list):
        return False
    choices = {
        str(item.get("correct_response") or item.get("Correct_Response") or "").strip()
        for item in triggers
        if isinstance(item, dict) and str(item.get("trigger_key") or "").startswith("trial:") and _row_has_contract(item)
    }
    return {"left", "right"}.issubset(choices)


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
    if isinstance(data, dict):
        return data
    return {}


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


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


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
        "# Response-Choice Contract Capability Smoke",
        "",
        f"- Schema: `{report['schema']}`",
        f"- Passed: `{report['passed']}`",
        f"- Block rows: `{report['block_row_family_counts']}`",
        f"- Correct responses: `{report['block_row_correct_responses']}`",
        f"- Participant choices: `{report['participant_choice_counts']}`",
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
