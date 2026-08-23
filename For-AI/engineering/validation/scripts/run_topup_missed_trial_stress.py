"""Stress missed-trial top-up behavior with emulated participant responses.

This internal validation harness does not touch hardware. It builds small
Segment 5/6-style experimental sessions, runs them through the real
SessionRunnerController with top-up enabled, deliberately withholds responses on
selected tactile trials, auto-approves the final top-up block, and verifies that
the final analysis table reflects rescued misses.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import shutil
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf


REPO_ROOT = Path(__file__).resolve().parents[4]
SRC_ROOT = REPO_ROOT / "packages" / "pps-runtime" / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from peripersonal_space_toolkit.session_runner import (  # noqa: E402
    SessionCaptureOptions,
    SessionRunnerController,
    prepare_segment_run_package,
)


SCHEMA = "pps-topup-missed-trial-stress.v1"
SCENARIOS = ("balanced_misses", "row_imbalanced_misses", "dense_mixed_misses")


@dataclass(frozen=True)
class ResponsePlan:
    trial_uid: str
    source_trial_uid: str
    tactile_event_id: int
    is_topup: bool
    topup_role: str
    action: str
    due_monotonic_time: float
    planned_delay_ms: float


def _default_output_dir() -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("artifacts") / "validation_runs" / f"topup_missed_trial_stress_{stamp}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fieldnames or sorted({key for row in rows for key in row.keys()}) or ["empty"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _add_pulse(data: np.ndarray, channel: int, onset_s: float, *, sample_rate: int, amplitude: float) -> None:
    start = max(0, min(data.shape[0], int(round(onset_s * sample_rate))))
    width = max(1, int(round(0.020 * sample_rate)))
    stop = max(start, min(data.shape[0], start + width))
    data[start:stop, channel] = amplitude


def _build_segment_fixture(
    output_dir: Path,
    *,
    participant_id: str,
    block_count: int,
    trials_per_block: int,
    sample_rate: int,
    trial_duration_s: float,
) -> Path:
    project_root = output_dir / "segment_fixture"
    block_root = project_root / "5_block_csv_preview"
    run_root = project_root / "6_experiment_run_setup"
    stim_root = output_dir / "stimuli"
    block_root.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True, exist_ok=True)
    stim_root.mkdir(parents=True, exist_ok=True)

    block_manifest_rows: list[dict[str, Any]] = []
    order_rows: list[dict[str, Any]] = []
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
    ]
    soa_values = [10, 30, 50, 70, 90]
    looming_onset_s = 0.100
    for block_index in range(1, block_count + 1):
        block_rows: list[dict[str, Any]] = []
        for trial_index in range(1, trials_per_block + 1):
            soa_ms = soa_values[(block_index + trial_index - 2) % len(soa_values)]
            tactile_onset_s = looming_onset_s + (soa_ms / 1000.0)
            frames = int(round(trial_duration_s * sample_rate))
            data = np.zeros((frames, 3), dtype=np.float32)
            _add_pulse(data, 0, looming_onset_s, sample_rate=sample_rate, amplitude=0.018)
            _add_pulse(data, 1, looming_onset_s + 0.002, sample_rate=sample_rate, amplitude=0.016)
            _add_pulse(data, 2, tactile_onset_s, sample_rate=sample_rate, amplitude=0.014)
            row_label = "Inhale" if trial_index % 2 else "Exhale"
            wav_path = stim_root / f"block{block_index:02d}_trial{trial_index:02d}_{row_label.lower()}_soa{soa_ms:03d}.wav"
            sf.write(wav_path, data, sample_rate)
            block_rows.append(
                {
                    "block_trial_index": trial_index,
                    "family": "audio_tactile",
                    "row_label": row_label,
                    "noise_type": "topup_validation_rect_pulse",
                    "soa_ms": soa_ms,
                    "sequence_labels": f"{row_label} validation pulse | SOA {soa_ms} ms",
                    "sequence_variant_key": f"{row_label.lower()}_soa{soa_ms:03d}",
                    "source_file_name": wav_path.name,
                    "trial_file_path": str(wav_path),
                    "source_sha256": _sha256(wav_path),
                    "duration_ms": int(round(trial_duration_s * 1000.0)),
                    "duration_s": f"{trial_duration_s:.9f}",
                    "looming_segment_onset_s": f"{looming_onset_s:.9f}",
                    "tactile_onset_s": f"{tactile_onset_s:.9f}",
                    "channels": 3,
                    "tactile_channel": 3,
                }
            )
        block_csv = block_root / f"block_{block_index:02d}_final.csv"
        _write_csv(block_csv, block_rows, fieldnames)
        block_manifest_rows.append(
            {
                "block_index": block_index,
                "csv_path": str(block_csv),
                "csv_file_name": block_csv.name,
                "trial_count": len(block_rows),
            }
        )
        order_rows.append(
            {
                "participant_id": participant_id,
                "participant_index": 1,
                "experiment_structure": "single",
                "phase": "single",
                "phase_label": "Single",
                "phase_index": 1,
                "participant_block_position": block_index,
                "source_block_index": block_index,
                "block_label": f"Top-up Stress Block {block_index:02d}",
                "block_csv_file": block_csv.name,
                "block_csv_path": str(block_csv),
                "trial_count": len(block_rows),
                "duration_ms": int(round(trials_per_block * trial_duration_s * 1000.0)),
                "sequence_seed": 20260613 + block_index,
            }
        )

    block_manifest = block_root / "block_csv_preview_manifest.json"
    block_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-block-csv-preview.v1",
                "accepted": True,
                "blocks": block_manifest_rows,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    order_csv = run_root / "experiment_block_order.csv"
    _write_csv(
        order_csv,
        order_rows,
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
    run_manifest.write_text(
        json.dumps(
            {
                "schema": "pps-experiment-run-setup.v1",
                "status": "prepared",
                "prepared": True,
                "csv_path": str(order_csv),
                "experiment_structure": "single",
                "participant_count": 1,
                "parts_per_participant": 1,
                "blocks_per_part": block_count,
                "total_block_runs": block_count,
                "seed": 20260613,
                "source_segment5_manifest": str(block_manifest),
                "source_segment5_manifest_sha256": _sha256(block_manifest),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return run_manifest


class TopUpStressAudioEngine:
    """Realtime fake engine that emits callback-shaped scheduled events."""

    def __init__(self, *, sample_rate: int, blocksize: int, response_marker_delay_ms: float):
        self.sample_rate = int(sample_rate)
        self.blocksize = int(blocksize)
        self.response_marker_delay_ms = float(response_marker_delay_ms)
        self.played_paths: list[str] = []
        self.trigger_records: list[dict[str, Any]] = []
        self.recording_paths: list[str] = []
        self._audio_event_callback = None
        self._play_start_perf = 0.0
        self._last_block_path: Path | None = None
        self._stop_requested = threading.Event()

    def play_block(self, path: str, progress_callback=None, audio_event_callback=None, block_event_schedule=None) -> bool:
        self.played_paths.append(path)
        self._last_block_path = Path(path)
        info = sf.info(path)
        frames_total = int(info.frames)
        self.sample_rate = int(info.samplerate)
        self._audio_event_callback = audio_event_callback
        self._play_start_perf = time.perf_counter()
        if block_event_schedule is not None:
            block_event_schedule.reset()
        cursor = 0
        while cursor < frames_total and not self._stop_requested.is_set():
            frames = min(self.blocksize, frames_total - cursor)
            now = time.perf_counter()
            if audio_event_callback is not None and block_event_schedule is not None:
                event_frames = frames + 1 if cursor + frames >= frames_total else frames
                for event in block_event_schedule.consume_buffer(cursor, event_frames):
                    offset = int(event.sample_index) - cursor
                    payload = dict(event.payload)
                    payload.update(
                        {
                            "event_type": event.event_type,
                            "sample_index": event.sample_index,
                            "buffer_start_sample": cursor,
                            "sample_offset_in_buffer": offset,
                            "sample_rate": self.sample_rate,
                            "trigger_key": event.trigger_key,
                            "callback_perf_counter": now,
                            "stream_current_time": now,
                            "stream_output_buffer_dac_time": now,
                        }
                    )
                    audio_event_callback(payload)
            if progress_callback is not None:
                progress_callback(cursor / self.sample_rate)
            cursor += frames
            target = self._play_start_perf + (cursor / self.sample_rate)
            sleep_s = target - time.perf_counter()
            if sleep_s > 0:
                time.sleep(min(sleep_s, 0.010))
        if progress_callback is not None:
            progress_callback(min(cursor, frames_total) / self.sample_rate)
        return not self._stop_requested.is_set()

    def trigger_click(self, metadata=None, marker_gain=None) -> None:
        now = time.perf_counter()
        elapsed_samples = max(0, int(round((now - self._play_start_perf) * self.sample_rate)))
        offset = max(0, int(round((self.response_marker_delay_ms / 1000.0) * self.sample_rate)))
        payload = {
            "event_type": "response_marker_start",
            "sample_index": elapsed_samples + offset,
            "buffer_start_sample": elapsed_samples,
            "sample_offset_in_buffer": offset,
            "sample_rate": self.sample_rate,
            "callback_perf_counter": now,
            "stream_current_time": now,
            "stream_output_buffer_dac_time": now,
            "marker_channel": 2,
            "marker_gain": marker_gain,
            **dict(metadata or {}),
        }
        self.trigger_records.append(payload)
        if self._audio_event_callback is not None:
            self._audio_event_callback(payload)

    def start_recording(self, output_path: str) -> bool:
        self.recording_paths.append(output_path)
        return True

    def stop_recording(self, output_path: str | None = None, interrupted: bool = False) -> None:
        target = Path(output_path) if output_path else None
        if target is None:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if self._last_block_path is not None and self._last_block_path.exists():
            shutil.copyfile(self._last_block_path, target)
        else:
            sf.write(target, np.zeros((1, 3), dtype=np.float32), self.sample_rate)

    def stop(self) -> None:
        self._stop_requested.set()

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None

    def shutdown(self) -> None:
        self.stop()


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    return str(value).strip().lower() not in {"0", "false", "no", "none"}


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean_ms": None, "sd_ms": None, "median_ms": None, "p95_ms": None, "min_ms": None, "max_ms": None}
    ordered = sorted(float(value) for value in values)
    p95_index = min(len(ordered) - 1, int(math.ceil(len(ordered) * 0.95)) - 1)
    return {
        "count": len(ordered),
        "mean_ms": statistics.fmean(ordered),
        "sd_ms": statistics.stdev(ordered) if len(ordered) > 1 else 0.0,
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
        "min_ms": min(ordered),
        "max_ms": max(ordered),
    }


def _event_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _read_csv(path):
        try:
            payload = json.loads(row.get("payload_json", "") or "{}")
        except json.JSONDecodeError:
            payload = {}
        rows.append({**row, "payload": payload})
    return rows


def _event_type_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts


def _original_tactile_rows(package: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for block in package.blocks:
        if block.metadata.get("is_topup_block"):
            continue
        for row in _read_csv(block.manifest_path):
            family = str(row.get("Family") or row.get("family") or "").lower()
            trial_type = str(row.get("Trial_Type") or row.get("trial_type") or "").lower()
            if family in {"audio_tactile", "baseline"} or trial_type in {"audio-tactile", "baseline"}:
                rows.append(row)
    return rows


def _select_misses(rows: list[dict[str, str]], scenario: str) -> set[str]:
    if scenario == "balanced_misses":
        selected: list[str] = []
        seen_rows: set[str] = set()
        for row in rows:
            label = str(row.get("Row_Label") or row.get("Row") or "")
            if label in seen_rows:
                continue
            selected.append(str(row["Trial_UID"]))
            seen_rows.add(label)
            if len(selected) >= 2:
                break
        return set(selected)
    if scenario == "row_imbalanced_misses":
        selected = [str(row["Trial_UID"]) for row in rows if str(row.get("Row_Label") or row.get("Row")) == "Inhale"]
        return set(selected[: max(2, min(3, len(selected)))])
    if scenario == "dense_mixed_misses":
        selected = [str(row["Trial_UID"]) for index, row in enumerate(rows, start=1) if index % 3 == 0]
        if rows:
            selected.append(str(rows[-1]["Trial_UID"]))
        return set(selected)
    raise ValueError(f"Unknown top-up stress scenario: {scenario}")


def _run_response_emulator(
    *,
    controller: SessionRunnerController,
    thread: threading.Thread,
    missed_trial_uids: set[str],
    click_log: list[dict[str, Any]],
    response_timeout_s: float,
) -> None:
    scheduled: dict[int, ResponsePlan] = {}
    clicked_event_ids: set[int] = set()
    standard_delay_ms = [125.0, 150.0, 175.0, 140.0, 160.0, 135.0]
    topup_delay_ms = [120.0, 150.0, 170.0, 135.0]
    deadline = time.perf_counter() + response_timeout_s
    while thread.is_alive() and time.perf_counter() < deadline:
        now = time.perf_counter()
        for event in controller.logger.events:
            if event.event_type != "tactile_onset" or event.event_id in scheduled:
                continue
            payload = dict(event.payload or {})
            trial_uid = str(payload.get("trial_uid") or payload.get("Trial_UID") or event.event_id)
            source_uid = str(payload.get("source_trial_uid") or payload.get("Source_Trial_UID") or payload.get("Original_Trial_UID") or "")
            is_topup = _truthy(payload.get("is_topup") or payload.get("Is_Topup"))
            topup_role = str(payload.get("topup_role") or payload.get("Topup_Role") or "").lower()
            if is_topup:
                action = "topup_click"
                delay = topup_delay_ms[len([item for item in scheduled.values() if item.is_topup]) % len(topup_delay_ms)]
            elif trial_uid in missed_trial_uids:
                action = "deliberate_miss"
                delay = 0.0
            else:
                action = "standard_click"
                delay = standard_delay_ms[len([item for item in scheduled.values() if not item.is_topup]) % len(standard_delay_ms)]
            scheduled[event.event_id] = ResponsePlan(
                trial_uid=trial_uid,
                source_trial_uid=source_uid,
                tactile_event_id=event.event_id,
                is_topup=is_topup,
                topup_role=topup_role,
                action=action,
                due_monotonic_time=float(event.monotonic_time) + (delay / 1000.0),
                planned_delay_ms=delay,
            )
        for event_id, plan in list(scheduled.items()):
            if event_id in clicked_event_ids or plan.action == "deliberate_miss" or now < plan.due_monotonic_time:
                continue
            controller.log_click(x=320 + len(clicked_event_ids), y=240, in_target=True)
            clicked_event_ids.add(event_id)
            click_log.append(
                {
                    "trial_uid": plan.trial_uid,
                    "source_trial_uid": plan.source_trial_uid,
                    "tactile_event_id": plan.tactile_event_id,
                    "is_topup": str(plan.is_topup).lower(),
                    "topup_role": plan.topup_role,
                    "action": plan.action,
                    "planned_delay_ms": f"{plan.planned_delay_ms:.3f}",
                    "actual_click_monotonic_time": f"{time.perf_counter():.9f}",
                }
            )
        time.sleep(0.002)
    if thread.is_alive():
        controller.stop()


def _write_markdown_report(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Missed-Trial Top-Up Stress",
        "",
        f"- Passed: `{report.get('passed')}`",
        f"- Scenario count: `{report.get('scenario_count')}`",
        f"- Passed scenarios: `{report.get('passed_scenario_count')}`",
        "",
        "## Scenarios",
    ]
    for scenario in report.get("scenario_reports", []):
        lines.extend(
            [
                "",
                f"### {scenario.get('scenario')}",
                f"- Passed: `{scenario.get('passed')}`",
                f"- Expected misses: `{scenario.get('expected_missed_count')}`",
                f"- Top-up played: `{scenario.get('topup_played')}`",
                f"- Rescue rows: `{scenario.get('topup_rescue_count')}`",
                f"- Filler rows: `{scenario.get('topup_filler_count')}`",
                f"- Final rescued outcomes: `{scenario.get('final_rescued_count')}`",
                f"- RT ms: `{json.dumps(scenario.get('rt_ms'), sort_keys=True)}`",
            ]
        )
    lines.extend(
        [
            "",
            "This is an internal software stress test. It uses existing prepared trial WAVs and a realtime fake audio engine; it does not measure hardware latency, electrical loopback, or Woojer mechanical onset.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_scenario(
    *,
    output_dir: Path,
    scenario: str,
    scenario_index: int,
    participant_id: str,
    block_count: int,
    trials_per_block: int,
    sample_rate: int,
    trial_duration_s: float,
    blocksize: int,
    enable_lsl: bool,
    response_marker_delay_ms: float,
) -> dict[str, Any]:
    scenario_dir = output_dir / scenario
    scenario_dir.mkdir(parents=True, exist_ok=True)
    run_manifest = _build_segment_fixture(
        scenario_dir,
        participant_id=participant_id,
        block_count=block_count,
        trials_per_block=trials_per_block,
        sample_rate=sample_rate,
        trial_duration_s=trial_duration_s,
    )
    package = prepare_segment_run_package(
        run_manifest,
        participant_id,
        session_root=scenario_dir / "sessions",
        created_at=datetime(2026, 6, 13, 12, 0, 0) + timedelta(seconds=scenario_index),
    )
    original_rows = _original_tactile_rows(package)
    original_uids = {str(row["Trial_UID"]) for row in original_rows}
    missed_uids = _select_misses(original_rows, scenario)
    engine = TopUpStressAudioEngine(sample_rate=sample_rate, blocksize=blocksize, response_marker_delay_ms=response_marker_delay_ms)
    approval_requests: list[dict[str, Any]] = []
    controller = SessionRunnerController(
        package,
        audio_engine=engine,
        capture_options=SessionCaptureOptions(enable_lsl=enable_lsl, start_backup_recording=True),
        enable_topup=True,
        topup_approval_callback=lambda summary: approval_requests.append(dict(summary)) or True,
    )
    result_holder: dict[str, Any] = {}
    click_log: list[dict[str, Any]] = []

    def _run_controller() -> None:
        result_holder["result"] = controller.run()

    thread = threading.Thread(target=_run_controller, name=f"pps-topup-stress-{scenario}", daemon=True)
    thread.start()
    timeout_s = max(20.0, (block_count + 2) * trials_per_block * trial_duration_s + 15.0)
    _run_response_emulator(
        controller=controller,
        thread=thread,
        missed_trial_uids=missed_uids,
        click_log=click_log,
        response_timeout_s=timeout_s,
    )
    thread.join(timeout=5.0)
    if thread.is_alive():
        controller.stop()
        thread.join(timeout=2.0)
        raise RuntimeError(f"Top-up stress controller did not finish for {scenario}.")
    result = result_holder["result"]
    controller.events.flush_callback_events()

    events = _event_rows(result.events_csv)
    event_counts = _event_type_counts(events)
    ledger_csv = result.analysis_outputs.get("topup_ledger_csv", package.session_dir / "topup_ledger.csv")
    topup_manifest_csv = result.analysis_outputs.get("topup_block_manifest", package.session_dir / "topup_block_manifest.csv")
    topup_manifest_json = result.analysis_outputs.get("topup_block_manifest_json", package.session_dir / "topup_block_manifest.json")
    final_outcomes_csv = result.analysis_outputs.get("final_trial_outcomes", package.session_dir / "analysis" / f"{package.session_id}_final_trial_outcomes.csv")
    analysis_ready_csv = result.analysis_outputs.get("analysis_ready_trials", package.session_dir / "analysis" / f"{package.session_id}_analysis_ready_trials.csv")
    model_fits_csv = result.analysis_outputs.get("model_fits", package.session_dir / "analysis" / f"{package.session_id}_model_fits.csv")
    ledger_rows = _read_csv(ledger_csv)
    manifest_rows = _read_csv(topup_manifest_csv)
    manifest_json = _read_json(topup_manifest_json)
    final_rows = _read_csv(final_outcomes_csv)
    analysis_rows = _read_csv(analysis_ready_csv)
    model_rows = _read_csv(model_fits_csv)

    rescue_rows = [row for row in manifest_rows if str(row.get("Topup_Role") or "") == "rescue"]
    filler_rows = [row for row in manifest_rows if str(row.get("Topup_Role") or "") == "filler"]
    rescue_source_uids = {str(row.get("Source_Trial_UID") or "") for row in rescue_rows}
    final_by_uid = {str(row.get("trial_uid") or row.get("Trial_UID") or ""): row for row in final_rows}
    final_rescued = [
        row
        for uid, row in final_by_uid.items()
        if uid in missed_uids and str(row.get("final_outcome_source") or "") == "topup_rescue" and str(row.get("hit") or "").lower() == "true"
    ]
    original_hit_rows = [
        row
        for uid, row in final_by_uid.items()
        if uid in (original_uids - missed_uids) and str(row.get("final_outcome_source") or "") == "original" and str(row.get("hit") or "").lower() == "true"
    ]
    original_miss_ledger = [
        row
        for row in ledger_rows
        if str(row.get("trial_uid") or "") in missed_uids and str(row.get("status") or "") == "missed_needs_topup"
    ]
    topup_rescue_ledger_hits = [
        row
        for row in ledger_rows
        if str(row.get("is_topup") or "").lower() == "true"
        and str(row.get("topup_role") or "") == "rescue"
        and str(row.get("source_trial_uid") or "") in missed_uids
        and str(row.get("status") or "") == "hit"
    ]
    block_start_events = [row for row in events if row.get("event_type") == "block_start"]
    played_standard_count = sum(1 for path in engine.played_paths if "topup" not in Path(path).name.lower())
    played_topup_count = sum(1 for path in engine.played_paths if "topup" in Path(path).name.lower())
    topup_played_after_standard = bool(
        len(engine.played_paths) == block_count + 1
        and played_standard_count == block_count
        and played_topup_count == 1
        and "topup" in Path(engine.played_paths[-1]).name.lower()
    )
    rt_values = [float(row["rt_ms"]) for row in final_rows if str(row.get("rt_ms") or "").strip()]
    passed_checks = {
        "runner_completed": bool(result.completed and not result.interrupted),
        "topup_approval_requested": bool(approval_requests),
        "topup_played_after_standard_blocks": topup_played_after_standard,
        "one_topup_only": played_topup_count == 1,
        "expected_misses_ledgered": len(original_miss_ledger) == len(missed_uids),
        "rescue_manifest_matches_misses": rescue_source_uids == missed_uids,
        "topup_rescue_ledger_hits": len(topup_rescue_ledger_hits) == len(missed_uids),
        "final_rows_are_original_pool": len(final_rows) == len(original_uids),
        "analysis_ready_rows_are_original_pool": len(analysis_rows) == len(original_uids),
        "final_misses_rescued": len(final_rescued) == len(missed_uids),
        "standard_hits_preserved": len(original_hit_rows) == len(original_uids - missed_uids),
        "filler_present_when_imbalanced": scenario != "row_imbalanced_misses" or len(filler_rows) > 0,
        "model_fits_written": Path(model_fits_csv).exists(),
        "model_fit_rows_present": bool(model_rows),
        "events_written": result.events_csv.exists() and bool(events),
        "no_duplicate_event_ids": len({row.get("event_id") for row in events}) == len(events),
    }
    scenario_report = {
        "schema": f"{SCHEMA}.scenario",
        "scenario": scenario,
        "passed": all(passed_checks.values()),
        "checks": passed_checks,
        "participant_id": participant_id,
        "session_dir": str(package.session_dir),
        "run_setup_manifest": str(run_manifest),
        "block_count": block_count,
        "trials_per_block": trials_per_block,
        "original_tactile_trial_count": len(original_uids),
        "expected_missed_count": len(missed_uids),
        "expected_missed_trial_uids": sorted(missed_uids),
        "topup_played": played_topup_count == 1,
        "topup_played_after_standard": topup_played_after_standard,
        "played_paths": engine.played_paths,
        "approval_requests": approval_requests,
        "topup_rescue_count": len(rescue_rows),
        "topup_filler_count": len(filler_rows),
        "topup_manifest_json_summary": {key: manifest_json.get(key) for key in ("missed_trial_count", "rescue_trial_count", "filler_trial_count", "row_order")},
        "final_rescued_count": len(final_rescued),
        "original_hit_preserved_count": len(original_hit_rows),
        "event_type_counts": event_counts,
        "block_start_event_count": len(block_start_events),
        "mouse_click_count": event_counts.get("mouse_click", 0),
        "response_marker_start_count": event_counts.get("response_marker_start", 0),
        "rt_ms": _summary(rt_values),
        "events_csv": str(result.events_csv),
        "ledger_csv": str(ledger_csv),
        "topup_manifest_csv": str(topup_manifest_csv),
        "topup_manifest_json": str(topup_manifest_json),
        "final_trial_outcomes_csv": str(final_outcomes_csv),
        "analysis_ready_trials_csv": str(analysis_ready_csv),
        "model_fits_csv": str(model_fits_csv),
        "recording_paths": [str(path) for path in result.recording_paths],
        "limitations": [
            "Software stress only: fake realtime audio engine, no hardware loopback.",
            "Top-up playback is auto-authorized by the harness to stress seamless end-of-session playback.",
        ],
    }
    _write_csv(
        scenario_dir / "emulated_response_plan.csv",
        click_log,
        [
            "trial_uid",
            "source_trial_uid",
            "tactile_event_id",
            "is_topup",
            "topup_role",
            "action",
            "planned_delay_ms",
            "actual_click_monotonic_time",
        ],
    )
    (scenario_dir / "topup_stress_scenario_report.json").write_text(json.dumps(scenario_report, indent=2), encoding="utf-8")
    return scenario_report


def run_stress(
    *,
    output_dir: Path,
    participant_id: str = "P001",
    scenarios: list[str] | None = None,
    block_count: int = 2,
    trials_per_block: int = 6,
    sample_rate: int = 44100,
    trial_duration_s: float = 0.650,
    blocksize: int = 256,
    enable_lsl: bool = False,
    response_marker_delay_ms: float = 8.0,
) -> dict[str, Any]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_names = list(scenarios or SCENARIOS)
    scenario_reports = [
        run_scenario(
            output_dir=output_dir,
            scenario=scenario,
            scenario_index=index,
            participant_id=participant_id,
            block_count=block_count,
            trials_per_block=trials_per_block,
            sample_rate=sample_rate,
            trial_duration_s=trial_duration_s,
            blocksize=blocksize,
            enable_lsl=enable_lsl,
            response_marker_delay_ms=response_marker_delay_ms,
        )
        for index, scenario in enumerate(scenario_names, start=1)
    ]
    passed_count = sum(1 for report in scenario_reports if report.get("passed"))
    aggregate = {
        "schema": SCHEMA,
        "passed": passed_count == len(scenario_reports) and bool(scenario_reports),
        "scenario_count": len(scenario_reports),
        "passed_scenario_count": passed_count,
        "scenario_names": scenario_names,
        "output_dir": str(output_dir),
        "scenario_reports": scenario_reports,
        "aggregate": {
            "total_expected_misses": sum(int(report.get("expected_missed_count") or 0) for report in scenario_reports),
            "total_final_rescued": sum(int(report.get("final_rescued_count") or 0) for report in scenario_reports),
            "total_topup_fillers": sum(int(report.get("topup_filler_count") or 0) for report in scenario_reports),
            "all_topup_played": all(bool(report.get("topup_played")) for report in scenario_reports),
            "all_topup_played_after_standard": all(bool(report.get("topup_played_after_standard")) for report in scenario_reports),
        },
    }
    (output_dir / "topup_missed_trial_stress_report.json").write_text(json.dumps(aggregate, indent=2), encoding="utf-8")
    _write_markdown_report(aggregate, output_dir / "topup_missed_trial_stress_report.md")
    return aggregate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run missed-trial top-up stress scenarios with emulated participant behavior.")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--participant-id", default="P001")
    parser.add_argument("--scenario", action="append", choices=SCENARIOS, help="Scenario to run; repeat to run a subset.")
    parser.add_argument("--block-count", type=int, default=2)
    parser.add_argument("--trials-per-block", type=int, default=6)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--trial-duration-s", type=float, default=0.650)
    parser.add_argument("--blocksize", type=int, default=256)
    parser.add_argument("--response-marker-delay-ms", type=float, default=8.0)
    parser.add_argument("--enable-lsl", action="store_true")
    args = parser.parse_args(argv)

    output_dir = args.output_dir or _default_output_dir()
    report = run_stress(
        output_dir=output_dir,
        participant_id=args.participant_id,
        scenarios=args.scenario,
        block_count=args.block_count,
        trials_per_block=args.trials_per_block,
        sample_rate=args.sample_rate,
        trial_duration_s=args.trial_duration_s,
        blocksize=args.blocksize,
        enable_lsl=args.enable_lsl,
        response_marker_delay_ms=args.response_marker_delay_ms,
    )
    print(f"Wrote top-up missed-trial stress report: {output_dir / 'topup_missed_trial_stress_report.json'}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
