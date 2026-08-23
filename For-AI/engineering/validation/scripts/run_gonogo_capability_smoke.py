"""Validate runner support for weak/strong/no-target Go/NoGo PPS rows.

This is a capability smoke, not a paper-specific recreation. It builds a tiny
Segment 5/6-style fixture with weak tactile targets, strong tactile no-go rows,
one deliberate no-go false alarm, and sound-only catches. The run uses
SessionRunnerController, generated WAVs, software wired-loopback sidecars, and
mouse-click simulation through the runner's real click path.
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


SCHEMA = "pps-gonogo-capability-smoke.v1"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "artifacts" / "validation_runs" / "current_goal_gonogo_capability_20260715"
EVIDENCE_BOUNDARY = (
    "This smoke proves the software runner/package contract for row-level "
    "respond-vs-withhold tactile expectations, weak target hits, strong no-go "
    "correct rejections, strong no-go false alarms, sound-only catches, "
    "software wired-loopback sidecars, and mouse-click simulation through "
    "SessionRunnerController.log_click(). It is not a paper-specific profile, "
    "not physical hardware-loopback timing evidence, not participant data, and "
    "not a scientific PPS-effect replication claim."
)


class GoNoGoSmokeAudioEngine(runner_smoke.FastProfileSmokeAudioEngine):
    """Fast fake engine with a software wired-loopback sidecar path."""

    def __init__(self, *, max_clicks_per_block: int = 10_000, response_delay_s: float = 0.12):
        super().__init__(max_clicks_per_block=max_clicks_per_block, response_delay_s=response_delay_s)
        self.wired_loopback_mode = "off"
        self.wired_loopback_recordings: list[str] = []

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self._current_block_path = Path(path)
        self.played_blocks.append(str(path))
        self._audio_event_callback = audio_event_callback
        self._clicks_this_block = 0
        info = sf.info(path)
        self._sample_rate = int(info.samplerate)
        frames_total = int(info.frames)
        self._block_start_perf = time.perf_counter()
        if progress_callback is not None:
            progress_callback(0.0)
        if block_event_schedule is not None and audio_event_callback is not None:
            block_event_schedule.reset()
            for event in block_event_schedule.consume_buffer(0, frames_total + 1):
                if self._stopped:
                    break
                scheduled_perf = self._block_start_perf + (int(event.sample_index) / float(self._sample_rate))
                if event.event_type == "tactile_onset":
                    delay_s = scheduled_perf - time.perf_counter()
                    if delay_s > 0:
                        time.sleep(delay_s)
                now = time.perf_counter()
                payload = dict(event.payload)
                payload.update(
                    {
                        "event_type": event.event_type,
                        "sample_rate": self._sample_rate,
                        "sample_index": int(event.sample_index),
                        "sample_offset_in_buffer": 0,
                        "scheduled_sample_index": int(event.sample_index),
                        "callback_perf_counter": now,
                        "stream_current_time": now,
                        "stream_output_buffer_dac_time": scheduled_perf,
                        "trigger_key": event.trigger_key,
                    }
                )
                audio_event_callback(payload)
                if event.event_type == "tactile_onset" and self._clicks_this_block < self.max_clicks_per_block:
                    self._clicks_this_block += 1
                    if self._on_tactile is not None:
                        self._invoke_tactile_callback(payload)
        remaining_s = self._block_start_perf + float(info.duration) - time.perf_counter()
        if remaining_s > 0:
            time.sleep(remaining_s)
        if progress_callback is not None:
            progress_callback(float(info.duration))
        return not self._stopped

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
    run_manifest = _build_gonogo_fixture(output_dir, participant_id=participant_id)
    package = prepare_segment_run_package(run_manifest, participant_id=participant_id, use_block_cache=False)
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
        enable_topup=True,
        instruction_continue_callback=lambda _context: True,
        runner_metadata={"participant_code": participant_id},
    )

    def _click_for_selected_tactile(payload: dict[str, Any]) -> None:
        role = _lower(_first(payload, "target_role", "Target_Role", "go_nogo_role", "Go_NoGo_Role"))
        expected = _lower(_first(payload, "expected_response", "Expected_Response", "response_expected", "Response_Expected"))
        should_click = "false_alarm" in role or expected == "respond" or "weak" in role
        if not should_click:
            return
        controller.events.flush_callback_events(timeout_s=0.5)
        if engine.response_delay_s:
            time.sleep(engine.response_delay_s)
        controller.log_click(x=320, y=240, in_target=True)

    engine.set_tactile_callback(_click_for_selected_tactile)
    result = controller.run()
    controller.events.flush_callback_events(timeout_s=1.0)

    events = _read_csv(result.events_csv)
    event_counts = _event_counts(events)
    participant_path = result.analysis_outputs.get("participant_trials", Path())
    participant_rows = _read_csv(participant_path)
    analysis_path = result.analysis_outputs.get("analysis_ready_trials", Path())
    analysis_rows = _read_csv(analysis_path)
    block_rows = [row for block in package.blocks for row in _read_csv(block.manifest_path)]
    loopback_path = package.session_dir / "block_01_wired_loopback_input4.wav"
    target_rows = [row for row in participant_rows if _lower(row.get("expected_response")) == "respond"]
    no_go_tactile_rows = [
        row
        for row in participant_rows
        if _lower(row.get("expected_response")) == "withhold" and _truthy(row.get("tactile_present"))
    ]
    no_go_withheld_rows = [row for row in no_go_tactile_rows if not _truthy(row.get("response_given"))]
    no_go_false_alarm_rows = [row for row in no_go_tactile_rows if _truthy(row.get("response_given"))]
    catch_rows = [row for row in participant_rows if _truthy(row.get("catch_trial"))]
    no_go_analysis_rows = [
        row
        for row in analysis_rows
        if _lower(row.get("expected_response")) == "withhold"
        or "strong" in _lower(row.get("target_role"))
        or "nontarget" in _lower(row.get("target_role"))
    ]
    false_alarm_analysis_rows = [row for row in no_go_analysis_rows if _lower(row.get("target_role")).find("false_alarm") >= 0]
    withheld_analysis_rows = [row for row in no_go_analysis_rows if _lower(row.get("target_role")).find("false_alarm") < 0]
    topup_summary = dict(result.topup_summary or {})

    criteria = {
        "completed": bool(result.completed and not result.interrupted),
        "block_wav_generated": len(package.blocks) == 1 and package.blocks[0].wav_path.is_file(),
        "block_wav_readable": bool(runner_smoke._wav_facts(package.blocks[0].wav_path).get("readable")),
        "software_wired_loopback_written": loopback_path.is_file() and bool(runner_smoke._wav_facts(loopback_path).get("readable")),
        "response_contract_persisted_to_segment_manifest": all(
            str(row.get("Expected_Response") or "").strip() and str(row.get("Target_Role") or "").strip()
            for row in block_rows
        ),
        "event_counts_match_expected": event_counts.get("trial_start", 0) == 7
        and event_counts.get("tactile_onset", 0) == 5
        and event_counts.get("mouse_click", 0) == 3
        and event_counts.get("response_marker_start", 0) == 3
        and event_counts.get("trial_end", 0) == 7,
        "participant_target_hits": len(target_rows) == 2
        and all(row.get("outcome") == "Hit" and _truthy(row.get("response_given")) for row in target_rows),
        "participant_no_go_correct_rejections": len(no_go_withheld_rows) == 2
        and all(row.get("outcome") == "Hit" and "withhold" in _lower(row.get("correctness_rule")) for row in no_go_withheld_rows),
        "participant_no_go_false_alarm": len(no_go_false_alarm_rows) == 1
        and all(row.get("outcome") == "Miss" for row in no_go_false_alarm_rows),
        "participant_catch_correct_rejections": len(catch_rows) == 2
        and all(row.get("outcome") == "Hit" and not _truthy(row.get("response_given")) for row in catch_rows),
        "analysis_no_go_correctness": len(withheld_analysis_rows) == 2
        and all(_truthy(row.get("hit")) and not _truthy(row.get("primary_analysis_included")) for row in withheld_analysis_rows)
        and len(false_alarm_analysis_rows) == 1
        and all(not _truthy(row.get("hit")) and str(row.get("rt_ms") or "") == "" for row in false_alarm_analysis_rows),
        "topup_tracks_only_response_required_tactile_targets": int(topup_summary.get("tracked_tactile_trials") or 0) == 2
        and int(topup_summary.get("hit_count", topup_summary.get("hit")) or 0) == 2
        and int(topup_summary.get("missed_needs_topup_count", topup_summary.get("missed_needs_topup")) or 0) == 0,
        "core_outputs_written": result.events_csv.is_file()
        and result.events_xdf.is_file()
        and Path(analysis_path).is_file()
        and Path(participant_path).is_file()
        and bool(result.lsl_markers_csv and Path(result.lsl_markers_csv).is_file())
        and bool(result.trigger_dictionary_path and Path(result.trigger_dictionary_path).is_file()),
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
        "software_wired_loopback_wav": str(loopback_path),
        "software_wired_loopback_wav_facts": runner_smoke._wav_facts(loopback_path),
        "block_row_family_counts": _count_values(block_rows, "Family"),
        "block_row_expected_response_counts": _count_values(block_rows, "Expected_Response"),
        "block_row_target_role_counts": _count_values(block_rows, "Target_Role"),
        "event_counts": event_counts,
        "participant_trial_count": len(participant_rows),
        "participant_outcome_counts": _count_values(participant_rows, "outcome"),
        "analysis_ready_trial_count": len(analysis_rows),
        "analysis_ready_hit_count": sum(1 for row in analysis_rows if _truthy(row.get("hit"))),
        "analysis_ready_expected_response_counts": _count_values(analysis_rows, "expected_response"),
        "topup_summary": topup_summary,
        "outputs": {
            "events_csv": str(result.events_csv),
            "events_xdf": str(result.events_xdf),
            "analysis_ready_trials": str(analysis_path),
            "participant_trials": str(participant_path),
            "lsl_markers_csv": str(result.lsl_markers_csv or ""),
            "trigger_dictionary": str(result.trigger_dictionary_path or ""),
            "session_metadata": str(result.session_metadata_path or ""),
            "topup_ledger_csv": str(result.analysis_outputs.get("topup_ledger_csv", "")),
            "topup_ledger_json": str(result.analysis_outputs.get("topup_ledger_json", "")),
        },
        "report_json": str(output_dir / "gonogo_capability_smoke_report.json"),
        "report_md": str(output_dir / "gonogo_capability_smoke_report.md"),
    }
    _write_json(Path(report["report_json"]), report)
    _write_markdown(Path(report["report_md"]), report)
    return report


def _build_gonogo_fixture(output_dir: Path, *, participant_id: str) -> Path:
    project_root = output_dir / "gonogo_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)

    rows = []
    for index, spec in enumerate(_trial_specs(), start=1):
        wav_path = stim_root / f"trial_{index:02d}_{spec['target_role']}_{spec['family']}.wav"
        _write_trial_wav(wav_path, family=spec["family"], tactile_onset_s=spec["tactile_onset_s"])
        rows.append(
            {
                "block_trial_index": index,
                "family": spec["family"],
                "row_label": spec["row_label"],
                "noise_type": "gonogo_validation_tone",
                "soa_ms": spec["soa_ms"],
                "expected_response": spec["expected_response"],
                "response_rule": "respond_to_weak_targets_withhold_strong_nontargets_and_catches",
                "target_role": spec["target_role"],
                "primary_analysis_included": spec["primary_analysis_included"],
                "sequence_labels": spec["sequence_labels"],
                "sequence_variant_key": spec["sequence_variant_key"],
                "source_file_name": wav_path.name,
                "trial_file_path": str(wav_path),
                "source_sha256": _sha256(wav_path),
                "duration_ms": 1700,
                "duration_s": "1.700000000",
                "looming_segment_onset_s": "0.100000000" if spec["family"] in {"audio_tactile", "catch"} else "",
                "tactile_onset_s": f"{spec['tactile_onset_s']:.9f}" if spec["tactile_onset_s"] is not None else "",
                "channels": 3,
                "tactile_channel": 3,
            }
        )

    block_csv = block_root / "block_01_final.csv"
    fieldnames = [
        "block_trial_index",
        "family",
        "row_label",
        "noise_type",
        "soa_ms",
        "expected_response",
        "response_rule",
        "target_role",
        "primary_analysis_included",
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
                "block_label": "Go/NoGo validation block",
                "block_csv_file": block_csv.name,
                "block_csv_path": str(block_csv),
                "trial_count": len(rows),
                "duration_ms": 1700 * len(rows),
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
    return [
        {
            "family": "audio_tactile",
            "soa_ms": 0,
            "tactile_onset_s": 0.25,
            "expected_response": "respond",
            "target_role": "weak_target",
            "primary_analysis_included": "true",
            "row_label": "Weak audio-tactile target",
            "sequence_labels": "Weak target with sound",
            "sequence_variant_key": "weak_target_audio_tactile",
        },
        {
            "family": "audio_tactile",
            "soa_ms": 0,
            "tactile_onset_s": 0.25,
            "expected_response": "withhold",
            "target_role": "strong_nontarget",
            "primary_analysis_included": "false",
            "row_label": "Strong audio-tactile no-go withheld",
            "sequence_labels": "Strong no-go with sound",
            "sequence_variant_key": "strong_nontarget_audio_tactile_withheld",
        },
        {
            "family": "audio_tactile",
            "soa_ms": 0,
            "tactile_onset_s": 0.25,
            "expected_response": "withhold",
            "target_role": "strong_nontarget_false_alarm",
            "primary_analysis_included": "false",
            "row_label": "Strong audio-tactile no-go false alarm",
            "sequence_labels": "Strong no-go with deliberate false alarm",
            "sequence_variant_key": "strong_nontarget_audio_tactile_false_alarm",
        },
        {
            "family": "baseline",
            "soa_ms": 0,
            "tactile_onset_s": 0.25,
            "expected_response": "respond",
            "target_role": "weak_target",
            "primary_analysis_included": "true",
            "row_label": "Weak tactile-only target baseline",
            "sequence_labels": "Weak tactile target without sound",
            "sequence_variant_key": "weak_target_baseline",
        },
        {
            "family": "baseline",
            "soa_ms": 0,
            "tactile_onset_s": 0.25,
            "expected_response": "withhold",
            "target_role": "strong_nontarget",
            "primary_analysis_included": "false",
            "row_label": "Strong tactile-only no-go withheld",
            "sequence_labels": "Strong tactile no-go without sound",
            "sequence_variant_key": "strong_nontarget_baseline_withheld",
        },
        {
            "family": "catch",
            "soa_ms": 0,
            "tactile_onset_s": None,
            "expected_response": "withhold",
            "target_role": "no_target",
            "primary_analysis_included": "false",
            "row_label": "Sound-only catch",
            "sequence_labels": "Sound-only catch without tactile target",
            "sequence_variant_key": "sound_only_catch",
        },
        {
            "family": "catch",
            "soa_ms": 0,
            "tactile_onset_s": None,
            "expected_response": "withhold",
            "target_role": "no_target",
            "primary_analysis_included": "false",
            "row_label": "Second sound-only catch",
            "sequence_labels": "Second sound-only catch without tactile target",
            "sequence_variant_key": "sound_only_catch_repeat",
        },
    ]


def _write_trial_wav(path: Path, *, family: str, tactile_onset_s: float | None, sample_rate: int = 44100) -> None:
    frames = int(round(1.7 * sample_rate))
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
        "# Go/NoGo Capability Smoke",
        "",
        f"- Passed: `{report['passed']}`",
        f"- Participant trials: `{report['participant_trial_count']}`",
        f"- Mouse clicks: `{report['event_counts'].get('mouse_click', 0)}`",
        f"- Response markers: `{report['event_counts'].get('response_marker_start', 0)}`",
        f"- Analysis hits: `{report['analysis_ready_hit_count']}`",
        f"- Top-up tracked tactile targets: `{(report['topup_summary'] or {}).get('tracked_tactile_trials', 0)}`",
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
        value = str(row.get(key) or row.get(key.lower()) or "").strip().lower()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _lower(value: Any) -> str:
    return str(value or "").strip().lower()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Go/NoGo tactile response capability smoke.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--participant-id", default="P001")
    args = parser.parse_args(argv)

    report = run_smoke(output_dir=args.output_dir, participant_id=args.participant_id)
    print(f"Wrote Go/NoGo capability smoke report: {report['report_json']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
